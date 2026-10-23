"""Neural TTS in child processes. synth_mixed(text) / synth_vanira / synth_vachana / synth_en / synth_th -> RIFF bytes.

Thai phonemizers hold memory Python can't unload (Vachana/Vanira: pythainlp ~300 MB, Piper Thai: TLTK+pandas ~400 MB),
so each engine+voice runs in a worker (python tts_th.py --serve <engine> <voice>); release() kills them -> idle RAM 0.
Up to MAX_WORKERS stay warm at once, so a reply that alternates Thai and English doesn't cold-start on every switch.

vanira   VaniraTTS (VIZINTZOR, MixerTTS/ONNX), speaker 1 = default female voice. Runs on the main venv.
vachana  VachanaTTS (VIZINTZOR, MIT, VITS/ONNX), voices th_f_1 th_f_2 (female) th_m_1 th_m_2. Main venv.
piper    models/piper/<voice>.onnx in .venv-tts (tltk pins numpy<2): "tsync2" = Thai (drops Latin letters),
         en_US-hfc_female-medium etc. = English voices for the English parts of mixed replies.
synth_mixed  Thai parts -> Thai voice, English runs ("YouTube", "Visual Studio Code") -> English voice, joined:
         the Thai voices only approximate English through a Thai transliteration, which garbles it.
"""
import io, json, os, re, shutil, struct, subprocess, sys, threading, wave

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root; code lives in app/
MODEL = os.environ.get("TTS_TH_MODEL", os.path.join(ROOT, "models", "piper", "th_TH-tsync2-medium.onnx"))
PIPER_DIR = os.path.join(ROOT, "models", "piper")
PYTHON = os.environ.get("TTS_TH_PYTHON", os.path.join(ROOT, ".venv-tts", "Scripts", "python.exe"))  # Piper's own venv


def voice_exe():
    """§75 Piper as its own program (installed: <app>\voice, built here: dist\FRIDAY-voice), or ''."""
    for d in (os.path.join(ROOT, "voice"), os.path.join(ROOT, "dist", "FRIDAY-voice")):
        if os.path.isfile(os.path.join(d, "FRIDAY-voice.exe")):
            return os.path.join(d, "FRIDAY-voice.exe")
    return ""


CONSOLE_PY = os.path.join(os.path.dirname(sys.executable), "python.exe")  # not pythonw: worker needs sys.stdout
if getattr(sys, "frozen", False):
    CONSOLE_PY = sys.executable
VACHANA_DIR = os.path.join(ROOT, "models", "vachana")
EN_VOICE = os.environ.get("FRIDAY_EN_TTS", "en_US-hfc_female-medium")
MAX_WORKERS = 2
_procs, _lock = {}, threading.Lock()  # (engine, voice) -> Popen, oldest first


def _request(key, python, text):
    """Send one line to the worker for `key` (engine, voice), starting it if needed; return the WAV."""
    with _lock:
        p = _procs.get(key)
        if p is None or p.poll() is not None:
            while len(_procs) >= MAX_WORKERS:  # evict the least recently started worker
                old = _procs.pop(next(iter(_procs)))
                old.kill(); old.wait()
            # FRIDAY.exe (§69) serves Vanira/Vachana itself; Piper: FRIDAY-voice.exe when installed (§75), else its
            # own venv runs this file from app\ on disk
            if getattr(sys, "frozen", False) and python == CONSOLE_PY:
                cmd = [sys.executable, "--serve", *key]
            elif python == PYTHON and not os.path.isfile(PYTHON) and voice_exe():
                cmd = [voice_exe(), "--serve", *key]
            else:
                cmd = [python, os.path.join(ROOT, "app", "tts_th.py"), "--serve", *key]
            # stderr: FRIDAY.exe is a GUI program — an inherited console stderr can't be passed on (WinError 50, §69)
            p = _procs[key] = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            p.stdin.write(" ".join(text.split()).encode() + b"\n"); p.stdin.flush()
            hdr = p.stdout.read(4)
            n = struct.unpack("<I", hdr)[0] if len(hdr) == 4 else -1
            data = p.stdout.read(n) if n >= 0 else b""
            if len(data) != n:  # died before or mid-reply: don't hand back a truncated WAV
                raise RuntimeError("tts_th worker died")
            return data
        except BaseException:  # incl. Ctrl+C mid-reply: an unread WAV left in the pipe would desync every later call
            p.kill(); _procs.pop(key, None)
            raise


def synth_vachana(text, voice="th_f_1"):
    """Female/male Thai voice, ~0.07 s per sentence warm; first call ~7 s (worker start + pythainlp)."""
    return _request(("vachana", voice), CONSOLE_PY, text)


def synth_vanira(text, speaker="1"):
    """VaniraTTS (VIZINTZOR, MixerTTS/ONNX) speakers 1 2 5 = female, 3 4 6 = male. ~0.08 s per sentence warm."""
    return _request(("vanira", str(speaker)), CONSOLE_PY, text)


def vanira_ids(text, speaker="1"):
    """§73 the phoneme ids Vanira would speak — the phone app runs the same model on them (tiny vs a WAV)."""
    return json.loads(_request(("vanira", str(speaker)), CONSOLE_PY, "\x01" + text) or b"[]")


def synth_th(text):
    """Piper Thai voice, ~0.4 s per 2 sentences warm; first call ~6 s."""
    return _request(("piper", "tsync2"), PYTHON, text)


def synth_en(text, voice=EN_VOICE):
    """Piper English voice (no TLTK loaded for it), for English-only text and the English runs of mixed text."""
    return _request(("piper", voice), PYTHON, text)


# a run of Latin words, digits allowed after the first word ("Visual Studio Code", "Windows 11", "C++")
EN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9'’+#.\-]*(?:[ \t]+[A-Za-z0-9][A-Za-z0-9'’+#.\-]*)*")


def split_mixed(text):
    """'เปิด YouTube ให้แล้วค่ะ' -> [('th', 'เปิด'), ('en', 'YouTube'), ('th', 'ให้แล้วค่ะ')]; punctuation-only bits dropped."""
    out, pos = [], 0
    for m in EN_RUN.finditer(text):
        out.append(("th", text[pos:m.start()]))
        out.append(("en", m.group().rstrip(".")))
        pos = m.end()
    out.append(("th", text[pos:]))
    return [(k, t.strip()) for k, t in out if re.search(r"[0-9A-Za-z\u0E00-\u0E7F]", t)]


def _pcm(wav, rate):
    import numpy as np
    with wave.open(io.BytesIO(wav)) as r:
        sr, a = r.getframerate(), np.frombuffer(r.readframes(r.getnframes()), np.int16).astype(np.float32)
    if len(a) and sr != rate:
        a = np.interp(np.arange(0, len(a), sr / rate), np.arange(len(a)), a)
    peak = float(np.abs(a).max()) if len(a) else 0.0
    return a * (0.9 * 32767 / peak) if peak > 0 else a  # same loudness for both voices


def synth_mixed(text, thai=synth_vanira, en_voice=EN_VOICE, rate=22050, gap_s=0.06):
    """Thai voice for Thai, English voice for English runs, one WAV."""
    import numpy as np
    parts = split_mixed(text)
    if len(parts) <= 1:
        return synth_en(text, en_voice) if parts and parts[0][0] == "en" else thai(text)
    gap = np.zeros(int(rate * gap_s), np.float32)
    pcm = []
    for kind, t in parts:
        pcm += [_pcm(synth_en(t, en_voice) if kind == "en" else thai(t), rate), gap]
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(np.clip(np.concatenate(pcm), -32768, 32767).astype(np.int16).tobytes())
    return b.getvalue()


def release():
    """Kill every worker; frees all their RAM. Next call cold-starts again."""
    with _lock:
        while _procs:
            p = _procs.pop(next(iter(_procs)))
            p.kill(); p.wait()


def _quiet_session(path):
    # ORT default spin-waits ~6 cores for ~1s after every run (measured ~6 CPU-s burned per reply while idle)
    import onnxruntime as ort
    so = ort.SessionOptions(); so.intra_op_num_threads = 4
    so.add_session_config_entry("session.intra_op.allow_spinning", "0")
    return ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])


class _Vanira:
    """Adapts VaniraTTS to the Piper-style synthesize_wav(text, wav, set_wav_format) the worker loop uses."""

    def __init__(self, speaker):
        import types
        from vaniratts import VaniraTTS
        from vachanatts.en2th import eng_to_th_transliteration
        d = os.path.join(ROOT, "models", "vanira")
        if not os.path.exists(os.path.join(d, "tts.onnx")):  # first use: ~185 MB download
            from huggingface_hub import hf_hub_download
            os.makedirs(d, exist_ok=True)
            for f in ("tts.onnx", "vocab.json"):
                shutil.copy(hf_hub_download("VIZINTZOR/VaniraTTS", f), os.path.join(d, f))
        self.tts, self.speaker = VaniraTTS(local_path=d), int(speaker)
        self.tts.ort_session = _quiet_session(os.path.join(d, "tts.onnx"))
        self.e2t = eng_to_th_transliteration
        self.config = types.SimpleNamespace(sample_rate=44100)

    def ids(self, text):
        import re
        # Vanira's own English transliteration garbles words ("YouTube" -> "OU"); Vachana's reads them right
        return self.tts.text_to_ids(re.sub(r"[A-Za-z][A-Za-z0-9'\-]*", lambda m: self.e2t(m[0]), text))

    def synthesize_wav(self, text, w, set_wav_format=False):
        import numpy as np
        t = self.tts
        ids = np.array([self.ids(text)], dtype=np.int64)
        audio = np.squeeze(t.ort_session.run(None, {
            "token_ids": ids, "pace": np.array([1.0], np.float32), "speaker": np.array([self.speaker - 1], np.int32),
            "emotion": np.array([0], np.int32), "pitch_mul": np.array([1.0], np.float32), "pitch_add": np.array([0.0], np.float32),
        })[0]).astype(np.float32)
        audio = audio / max(float(np.abs(audio).max()), 1e-6) * 0.9
        w.writeframes((audio * 32767).astype(np.int16).tobytes())


def _load(engine, voice):
    if engine == "vanira":
        return _Vanira(voice)
    if engine == "vachana":
        from vachanatts.voice import Voice
        path, cfg = os.path.join(VACHANA_DIR, voice + ".onnx"), os.path.join(VACHANA_DIR, "speaker_config.json")
        if not (os.path.exists(path) and os.path.exists(cfg)):  # first use of a voice: ~63 MB download
            from huggingface_hub import hf_hub_download
            os.makedirs(VACHANA_DIR, exist_ok=True)
            for f in (f"voices/{voice}.onnx", "speaker_config.json"):
                shutil.copy(hf_hub_download("VIZINTZOR/VachanaTTS", f), os.path.join(VACHANA_DIR, os.path.basename(f)))
        v = Voice.load(path, cfg)
        v.session = _quiet_session(path)
        return v
    import logging
    from piper import PiperVoice
    logging.getLogger("piper").setLevel(logging.ERROR)  # else one "Dropping non-Thai character" line per Latin char
    path = MODEL if voice == "tsync2" else os.path.join(PIPER_DIR, voice + ".onnx")
    v = PiperVoice.load(path)
    v.session = _quiet_session(path)
    return v


def _serve(engine, voice):
    out, sys.stdout = sys.stdout.buffer, sys.stderr  # keep stray library prints off the binary pipe
    v = _load(engine, voice)
    for line in sys.stdin.buffer:
        text, b = line.decode().strip(), io.BytesIO()
        if text.startswith("\x01") and hasattr(v, "ids"):  # §73 phoneme ids for the phone, not audio
            try:
                data = json.dumps(v.ids(text[1:])).encode()
            except Exception as e:
                print(f"tts_th: {type(e).__name__}: {e}", file=sys.stderr)
                data = b"[]"
            out.write(struct.pack("<I", len(data)) + data); out.flush()
            continue
        with wave.open(b, "wb") as w:  # header set here so empty/failed text still yields valid RIFF
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(v.config.sample_rate)
            try:
                if text:  # Vachana's g2p raises IndexError on ""
                    v.synthesize_wav(text, w, set_wav_format=False)
            except Exception as e:  # one odd sentence must not kill the warm worker (next call would cold-start ~7 s)
                print(f"tts_th: {type(e).__name__}: {e}", file=sys.stderr)
        out.write(struct.pack("<I", len(b.getvalue())) + b.getvalue()); out.flush()


if __name__ == "__main__" and "--serve" in sys.argv:
    _serve(*sys.argv[sys.argv.index("--serve") + 1:][:2])
elif __name__ == "__main__":
    import time, psutil
    rss = lambda pid: sum(q.memory_info().rss for q in [psutil.Process(pid)] + psutil.Process(pid).children(True)) / 2**20
    ids = vanira_ids("สวัสดีค่ะ YouTube")  # §73 what the phone app speaks from
    assert len(ids) > 10 and all(isinstance(i, int) for i in ids), ids
    for name, f in (("vanira", synth_vanira), ("vachana", synth_vachana), ("piper", synth_th)):
        t = time.perf_counter(); w = f("สวัสดีค่ะ"); cold = time.perf_counter() - t
        assert w[:4] == b"RIFF" and w[8:12] == b"WAVE" and len(w) > 10000, len(w)
        two = "ได้เลยค่ะ ฉันเปิดโปรแกรมให้แล้ว\nถ้าต้องการอะไรเพิ่มเติมบอกได้เลยนะคะ"
        t = time.perf_counter(); w2 = f(two); warm = time.perf_counter() - t
        with wave.open(io.BytesIO(w2)) as r:
            dur = r.getnframes() / r.getframerate()
            assert r.getnchannels() == 1 and r.getsampwidth() == 2
        assert 3 < dur < 15, dur
        assert len(f("ประชุมตอน 14 นาฬิกา 30 นาที")) > 40000  # digits expanded
        assert f("")[:4] == b"RIFF"
        proc = list(_procs.values())[-1]
        child = rss(proc.pid)
        cpu = lambda: sum(sum(q.cpu_times()[:2]) for q in [psutil.Process(proc.pid)] + psutil.Process(proc.pid).children(True))
        c0 = cpu(); time.sleep(2); idle_cpu = cpu() - c0
        assert idle_cpu < 0.1, f"worker burns {idle_cpu:.2f} CPU-s while idle"  # ORT spin-wait regression
        print(f"{name}: cold {cold:.2f}s, warm 2-sentence {warm:.2f}s (audio {dur:.1f}s), worker {child:.0f}MB, idle CPU {idle_cpu:.2f}s/2s")
    for f in (synth_vanira, synth_vachana):  # English words are spoken, not dropped (Piper drops them)
        assert len(f("เปิด YouTube ให้แล้วค่ะ")) > len(f("เปิดให้แล้วค่ะ")) * 1.15
    assert split_mixed("เปิด YouTube ให้แล้วค่ะ ตอนนี้ CPU ใช้ไป 10%") == [
        ("th", "เปิด"), ("en", "YouTube"), ("th", "ให้แล้วค่ะ ตอนนี้"), ("en", "CPU"), ("th", "ใช้ไป 10%")]
    assert split_mixed("เปิด Visual Studio Code กับ Windows 11 แล้วค่ะ.") == [
        ("th", "เปิด"), ("en", "Visual Studio Code"), ("th", "กับ"), ("en", "Windows 11"), ("th", "แล้วค่ะ.")]
    assert split_mixed("Hello.") == [("en", "Hello")] and split_mixed("") == []
    t = time.perf_counter(); m = synth_mixed("เปิด YouTube ให้แล้วค่ะ"); mixed = time.perf_counter() - t
    assert m[:4] == b"RIFF" and len(_procs) <= MAX_WORKERS
    print(f"mixed Thai+English: {mixed:.2f}s with {len(_procs)} warm workers")
    pids = [p.pid for p in _procs.values()]; release()
    assert not _procs and all(not psutil.pid_exists(x) or psutil.Process(x).status() == "zombie" for x in pids)
    print("selftest OK")
