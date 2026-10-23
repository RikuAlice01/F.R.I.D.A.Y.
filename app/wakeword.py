"""Hands-free activation for FRIDAY + Silero VAD end-of-speech. Two wake engines (FRIDAY_WAKE):

    hey_friday (default)  Silero VAD cuts speech segments -> Whisper tiny.en (CPU int8, 2 threads) -> text starts with
                          "hey/hi/ok friday". Silence costs ~1% of one core; only talk costs (~25% of a core while
                          people/TV keep talking). No training: the phrase is just a regex (WAKE_RE).
    hey_jarvis / <.onnx>  openWakeWord model (ONNX, CPU, 1 thread, ~4% of a core all the time).

    wait_for_wake()      -> True when the wake word is heard (blocks on the mic, ~1-2% of one core)
    record_utterance()   -> np.float32 16 kHz mono, from wake until ~0.8 s of silence (max 15 s)

Both read the same open mic stream, so a command spoken in one breath ("Hey Jarvis, what time is it") is not cut.
The mic is closed after record_utterance(), so nothing listens while the LLM/TTS runs.
Both take an optional `frames` iterator of int16 blocks (1280 samples) for testing without a mic.

python wakeword.py   -> selftest (TTS-synthesized clips, no speakers, no human) + 20 s live-mic idle CPU/RAM.
"""
import os, re, sys, types
import numpy as np
import sounddevice as sd
# openwakeword/__init__ imports its verifier trainer (scikit-learn + scipy: ~75 MB RSS, ~1 s) though we never use it
sys.modules.setdefault("openwakeword.custom_verifier_model",
                       types.SimpleNamespace(train_custom_verifier=None))
import openwakeword, openwakeword.utils
from openwakeword.model import Model
from openwakeword.vad import VAD

SR, FRAME = 16000, 1280                                  # openWakeWord wants 80 ms int16 blocks
WAKE = os.environ.get("FRIDAY_WAKE", "hey_friday")      # "hey_jarvis" or a path to a custom openWakeWord .onnx
# "hey friday" as Whisper tiny writes it ("High Friday", "He Friday" measured); must START the segment so
# "see you on Friday" / "next Friday" never wake it
WAKE_RE = re.compile(r"^\W*(?:(?:hey|hi|high|he|hay|okay|ok|a|yo)\W*)fri\W?day\b|^\W*friday\W*$", re.I)
KWS_END_SILENCE, KWS_CHECK_AT, KWS_PREROLL = 0.35, 2.4, 0.3  # s
WAKE_THRESHOLD = float(os.environ.get("FRIDAY_WAKE_THRESHOLD", "0.4"))  # owner's real voice scored 0.48; non-wake TTS max 0.34
NEAR_MISS = 0.15  # scores above this but below the threshold get logged
SPEECH_PROB = 0.5        # Silero prob above this = speech
END_SILENCE = 0.8        # s of silence that ends the utterance
NO_SPEECH_TIMEOUT = 4.0  # s after wake with no speech at all -> give up (returns empty)
MAX_UTTERANCE = 15.0     # s hard cap

_oww = _vad = _mic = _tiny = None
_pending = None  # (audio float32, complete) left over from the wake segment: the command said in the same breath


def _load():
    global _oww, _vad, _tiny
    if WAKE == "hey_friday":
        if _tiny is None:
            from faster_whisper import WhisperModel
            _tiny = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=2)  # ~75 MB, no VRAM
        _vad = _vad or VAD()
        return
    if _oww is None:
        models = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
        if not os.path.exists(os.path.join(models, "embedding_model.onnx")):
            openwakeword.utils.download_models([WAKE])   # one-time ~5 MB from GitHub releases
        _oww = Model(wakeword_models=[WAKE], inference_framework="onnx")  # tflite has no Windows wheel
        _vad = _vad or VAD()                              # silero_vad.onnx shipped with openWakeWord, 1 thread


def mic_frames():
    """Yields int16 blocks from the default mic until the generator is closed (which closes the stream)."""
    with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME) as s:
        while True:
            yield s.read(FRAME)[0][:, 0]


def frames_until(stop):
    """Mic blocks until `stop` (threading.Event) is set — for listening for the wake word while FRIDAY speaks (§54)."""
    with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME) as s:
        while not stop.is_set():
            yield s.read(FRAME)[0][:, 0]


def close_mic():
    global _mic
    if _mic is not None:
        _mic.close()
        _mic = None


def _tiny_text(audio):
    segs, _ = _tiny.transcribe(audio, language="en", beam_size=1, vad_filter=False, condition_on_previous_text=False,
                               without_timestamps=True)
    return "".join(x.text for x in segs).strip()


def _wait_hey_friday(frames):
    """Speech segment -> one tiny pass at KWS_CHECK_AT s (or at its end if shorter) and, if that missed, one more at its
    end (noise can start the segment early). Sets _pending when the command came in the same breath."""
    global _pending
    _vad.reset_states()
    buf, pre, speaking, sil, checks = [], [], False, 0.0, 0
    for f in frames:
        p = _vad.predict(f, frame_size=640)
        if not speaking:
            pre = (pre + [f])[-int(KWS_PREROLL * SR / FRAME):]
            if p >= SPEECH_PROB:
                speaking, buf, sil, checks = True, list(pre), 0.0, 0
            continue
        buf.append(f)
        sil = sil + FRAME / SR if p < SPEECH_PROB else 0.0
        dur, ended = len(buf) * FRAME / SR, sil >= KWS_END_SILENCE
        if (checks == 0 and (ended or dur >= KWS_CHECK_AT)) or (checks == 1 and ended and dur <= 6.0):
            checks += 1
            a = np.concatenate(buf).astype(np.float32) / 32768
            text = _tiny_text(a if checks == 2 else a[: int(KWS_CHECK_AT * SR)])
            m = WAKE_RE.search(text)
            if m:
                print(f"  (ได้ยิน Hey Friday: \"{text}\")")
                rest = text[m.end():].strip(" ,.!?")
                # nothing after the name: just a call, wait for the command · something after it: keep that audio,
                # complete if the speaker already stopped, else record_utterance continues it
                _pending = (a, ended) if rest else None
                return True
            if text and re.search(r"fri\W?day", text, re.I):
                print(f"  (เกือบได้ยิน Hey Friday: \"{text}\")")
        if ended:
            speaking, pre = False, []
    return False


def wait_for_wake(frames=None):
    """Blocks until the wake word is heard -> True. Returns False only if a finite `frames` source runs out."""
    global _mic, _pending
    _load()
    _pending = None
    if frames is None:
        close_mic()              # drop a stale stream (buffered audio from while we were talking)
        _mic = frames = mic_frames()
    if WAKE == "hey_friday":
        return _wait_hey_friday(frames)
    _oww.reset()
    near = 0.0  # best score of the current "almost": logged once it fades, to tune FRIDAY_WAKE_THRESHOLD
    for f in frames:
        score = max(_oww.predict(f).values())
        if score >= WAKE_THRESHOLD:
            print(f"  (ได้ยิน Hey Jarvis: {score:.2f})")
            _oww.reset()
            return True
        if score >= NEAR_MISS:
            near = max(near, score)
        elif near:
            print(f"  (เกือบได้ยิน Hey Jarvis: {near:.2f} < {WAKE_THRESHOLD}) — พูดชัดขึ้น หรือลด FRIDAY_WAKE_THRESHOLD")
            near = 0.0
    return False


def level(frame):
    """0..1 loudness of one int16 frame for the orb: quiet room ~0.05, normal speech ~0.4-0.8."""
    rms = float(np.sqrt(np.mean(np.square(frame.astype(np.float32))))) if len(frame) else 0.0
    return min(1.0, (rms / 4000) ** .7)


def record_utterance(frames=None, no_speech_timeout=NO_SPEECH_TIMEOUT, on_audio=None, every=1.0, stop=None, on_level=None):
    """Records until END_SILENCE of silence after speech, MAX_UTTERANCE cap (counted from speech start),
    or no_speech_timeout with no speech. Starts with the wake segment's leftover command, if any.
    on_audio(audio so far) every `every` s while speaking (live captions); it must return at once.
    stop (threading.Event) set -> returns empty audio at once (the panel was closed: stop listening)."""
    global _pending
    _load()
    prefix, _pending = _pending, None
    if prefix is not None and prefix[1]:  # "Hey Friday, what time is it" + silence: the command is already complete
        return prefix[0]
    own = frames is None
    if own:
        frames = _mic or mic_frames()
    _vad.reset_states()
    out, spoke, silent, t, talk, shown = [], False, 0.0, 0.0, 0.0, 0.0
    dt = FRAME / SR
    try:
        for f in frames:
            if stop is not None and stop.is_set():
                return np.zeros(0, np.float32)
            t += dt
            if spoke:
                talk += dt
            out = (out + [f])[-int(0.5 * SR / FRAME):] if not spoke else out + [f]  # before speech keep only 0.5 s pre-roll
            if _vad.predict(f, frame_size=640) >= SPEECH_PROB:
                spoke, silent = True, 0.0
            else:
                silent += dt
            if (spoke and silent >= END_SILENCE) or talk >= MAX_UTTERANCE or (not spoke and t >= no_speech_timeout):
                break
            if on_level:
                on_level(level(f))  # every 80 ms frame: the orb follows the voice
            if on_audio and spoke and talk - shown >= every:
                shown = talk
                a = np.concatenate(out).astype(np.float32) / 32768
                on_audio(np.concatenate([prefix[0], a]) if prefix is not None else a)
    finally:
        if own:
            close_mic()
            frames.close()
    audio = np.concatenate(out).astype(np.float32) / 32768 if spoke else np.zeros(0, np.float32)
    return np.concatenate([prefix[0], audio]) if prefix is not None else audio


# ---------------------------------------------------------------- selftest
def _frames_of(a):
    a = np.concatenate([a, np.zeros(-len(a) % FRAME, np.int16)])
    return iter(a.reshape(-1, FRAME))


def _selftest():
    global WAKE
    import asyncio, io, itertools, tempfile, time, wave, zlib, psutil
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader

    async def synth(text, voice, rate):
        s = SpeechSynthesizer()
        s.voice = next(v for v in SpeechSynthesizer.all_voices if voice in v.display_name)
        s.options.speaking_rate = rate
        st = await s.synthesize_text_to_stream_async(text)
        r = DataReader(st.get_input_stream_at(0))
        await r.load_async(st.size)
        b = bytearray(st.size)
        r.read_bytes(b)
        with wave.open(io.BytesIO(bytes(b))) as w:
            sr, ch = w.getframerate(), w.getnchannels()
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32).reshape(-1, ch).mean(1)
        return np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a).astype(np.int16)

    clips = os.path.join(tempfile.gettempdir(), "friday_wake_clips")  # cache, outside the repo
    os.makedirs(clips, exist_ok=True)

    def clip(text, voice, rate=1.0):
        p = os.path.join(clips, f"{voice}_{rate}_{zlib.crc32(text.encode())}.wav")
        if os.path.exists(p):
            with wave.open(p) as w:
                return np.frombuffer(w.readframes(w.getnframes()), np.int16)
        a = asyncio.run(synth(text, voice, rate))
        with wave.open(p, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR), w.writeframes(a.tobytes())
        return a

    rng = np.random.default_rng(0)
    sil = lambda s: np.zeros(int(s * SR), np.int16)
    noisy = lambda a: np.clip(a + rng.normal(0, 300, len(a)), -32768, 32767).astype(np.int16)  # ~20 dB SNR hiss

    def score(a):
        _oww.reset()
        return max(max(_oww.predict(f).values()) for f in _frames_of(np.concatenate([sil(1), a, sil(1)])))

    WAKE = "hey_jarvis"  # ---- openWakeWord engine ----
    _load()
    en = ["David", "George", "Hazel", "Zira", "Susan", "Mark"]
    pos = [(v, r, n) for v in en for r in (0.8, 1.0, 1.25) for n in (False, True)]
    hits = 0
    for v, r, n in pos:
        a = clip("Hey Jarvis, what time is it?", v, r)
        s = score(noisy(a) if n else a)
        hits += s >= WAKE_THRESHOLD
        print(f"  POS {v:6} rate={r:<4} noise={n!s:5} score={s:.3f}")
    print(f"detection: {hits}/{len(pos)}")

    neg_en = ["What's the weather like today?", "Hey Travis, can you pass me the salt?", "Hey Friday, what time is it?",
              "Open the garage door please.", "The jars of jam are on the shelf.", "Harvest season starts in March.",
              "I need to finish this report before Friday.", "Turn off the lights in the living room.",
              "Jarvis Cocker is a singer.", "Hey, are you listening to me?"]
    neg_th = ["สวัสดีครับ วันนี้อากาศดีมาก", "ช่วยเปิดเพลงให้หน่อย", "ตอนนี้กี่โมงแล้ว", "พรุ่งนี้มีประชุมตอนเก้าโมงเช้า",
              "เฮ้ ฟรายเดย์ ช่วยเปิดไฟหน่อย", "ฉันจะไปซื้อของที่ตลาด", "จาร์ดีนกำลังเดินทางมา", "ราคาน้ำมันขึ้นอีกแล้ว"]
    false, total_s, negs = 0, 0.0, [(t, v) for t in neg_en for v in ("David", "Hazel")] + [(t, "Pattara") for t in neg_th]
    for t, v in negs:
        a = clip(t, v)
        total_s += len(a) / SR
        s = score(a)
        false += s >= WAKE_THRESHOLD
        print(f"  NEG {v:7} score={s:.3f}  {t}")
    print(f"false triggers: {false}/{len(negs)} clips ({total_s:.0f} s of speech)")
    th = [score(clip("เฮ้ จาร์วิส ตอนนี้กี่โมง", "Pattara"))]
    print(f"Thai-voice 'เฮ้ จาร์วิส' score={th[0]:.3f} (informational)")
    assert hits >= 0.8 * len(pos) and false == 0, (hits, false)

    # end-to-end: stream = silence, wake+command, silence, more speech that must NOT be included
    cmd = clip("Hey Jarvis, what time is it?", "Hazel")
    later = clip("I need to finish this report before Friday.", "David")
    stream = _frames_of(np.concatenate([sil(2), cmd, sil(2), later]))
    t0 = time.perf_counter()
    assert wait_for_wake(stream)
    u = record_utterance(stream)
    print(f"utterance after wake: {len(u) / SR:.2f} s (clip {len(cmd) / SR:.2f} s); processed in {time.perf_counter() - t0:.2f} s")
    assert 0.8 <= len(u) / SR <= len(cmd) / SR + 1.2, len(u)          # got the command tail + ~0.8 s silence, not `later`

    trim = lambda a: a[np.flatnonzero(abs(a) > 500)[0]:np.flatnonzero(abs(a) > 500)[-1]]  # drop TTS lead/tail silence
    long = np.concatenate([trim(clip(t, "David")) for t in neg_en] * 2)  # ~30 s non-stop talk
    assert -0.1 < len(record_utterance(_frames_of(long))) / SR - MAX_UTTERANCE < 0.6  # cap + up to 0.5 s pre-roll
    assert len(record_utterance(_frames_of(np.concatenate([sil(8), cmd])), no_speech_timeout=10)) / SR > 0.8  # late speaker
    assert len(record_utterance(_frames_of(sil(10)))) == 0                # nobody spoke -> empty after 4 s
    assert not wait_for_wake(_frames_of(sil(3)))                          # finite source, no wake -> False

    # ---- hey_friday engine (default): VAD segments -> Whisper tiny.en ----
    WAKE = "hey_friday"
    _load()
    pos_f = [(t, v) for v in ("David", "Zira", "Hazel") for t in ("Hey Friday", "Hey Friday, what time is it?", "Hi Friday, open YouTube")]
    neg_f = ["See you on Friday.", "Friday is my favorite day of the week.", "Hey Freddie, how are you?", "Hey Jarvis, what time is it?",
             "The meeting moved to next Friday afternoon.", "I fried some eggs for breakfast."]
    hits_f = sum(wait_for_wake(_frames_of(np.concatenate([sil(1), clip(t, v), sil(1)]))) for t, v in pos_f)
    false_f = sum(wait_for_wake(_frames_of(np.concatenate([sil(1), clip(t, v), sil(1)]))) for t in neg_f for v in ("David", "Hazel"))
    print(f"hey_friday: detection {hits_f}/{len(pos_f)}, false triggers {false_f}/{len(neg_f) * 2}")
    assert hits_f >= len(pos_f) - 1 and false_f == 0, (hits_f, false_f)
    # command in the same breath + silence -> the wake segment IS the utterance (no 4 s wait for more speech)
    one = clip("Hey Friday, what time is it?", "Zira")
    s1 = _frames_of(np.concatenate([sil(1), one, sil(2)]))
    assert wait_for_wake(s1) and _pending and _pending[1]
    u = record_utterance(s1)
    assert abs(len(u) / SR - len(one) / SR) < 1.0, len(u) / SR
    # just the name, pause, then the command -> nothing pending, the command is recorded after the wake
    s2 = _frames_of(np.concatenate([sil(1), clip("Hey Friday", "Zira"), sil(1.2), clip("Open YouTube please", "Zira"), sil(2)]))
    assert wait_for_wake(s2) and _pending is None
    assert len(record_utterance(s2)) / SR > 0.8
    # live captions: growing audio every 0.5 s of speech, none before speech, final recording is the longest
    long = clip("Open YouTube and play some relaxing music for me please", "Zira")
    seen = []
    u = record_utterance(_frames_of(np.concatenate([sil(1.5), long, sil(2)])), on_audio=lambda a: seen.append(len(a)), every=0.5)
    assert len(seen) >= 3 and seen == sorted(seen) and seen[-1] <= len(u), (seen, len(u))
    # panel closed mid-sentence: stop at once, drop what was heard
    import threading
    closed = threading.Event()
    fs = _frames_of(np.concatenate([sil(1.5), long, sil(2)]))
    u = record_utterance(fs, on_audio=lambda a: closed.set(), every=0.5, stop=closed)
    assert len(u) == 0 and len(list(fs)) > 20, len(u)  # returned mid-speech, frames left unread
    # orb level: one value per frame, quiet low, speech higher, all within 0..1
    lv = []
    record_utterance(_frames_of(np.concatenate([sil(1), long, sil(2)])), on_level=lv.append)
    assert lv and all(0 <= v <= 1 for v in lv) and max(lv) > 0.2 and min(lv) < 0.05, (min(lv), max(lv))

    # per-frame cost, then 20 s live mic (just reading the mic, nothing played)
    WAKE = "hey_jarvis"
    f = np.zeros(FRAME, np.int16)
    t0 = time.perf_counter()
    for _ in range(200):
        _oww.predict(f)
    print(f"wake inference: {(time.perf_counter() - t0) / 200 * 1000:.2f} ms per 80 ms frame")
    t0 = time.perf_counter()
    for _ in range(200):
        _vad.predict(f, frame_size=640)
    print(f"VAD inference: {(time.perf_counter() - t0) / 200 * 1000:.2f} ms per 80 ms frame")

    WAKE = "hey_friday"  # live idle cost of the default engine
    p = psutil.Process()
    rss0 = p.memory_info().rss
    gen = mic_frames()
    mic = itertools.islice(gen, int(20 * SR / FRAME))
    c0, t0 = p.cpu_times(), time.perf_counter()
    woke = wait_for_wake(mic)
    c1, el = p.cpu_times(), time.perf_counter() - t0
    gen.close()
    cpu = (c1.user + c1.system - c0.user - c0.system) / el * 100
    print(f"live mic {el:.1f} s: woke={woke}  CPU {cpu:.2f}% of one core ({cpu / psutil.cpu_count():.2f}% of total)  "
          f"RSS {rss0 / 2**20:.0f} -> {p.memory_info().rss / 2**20:.0f} MB")
    assert el > 15 and cpu < 10
    print("SELFTEST OK")


if __name__ == "__main__":
    _selftest()
