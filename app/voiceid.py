"""Owner's voice (PLAN §59): a small speaker-recognition model on CPU (ONNX through sherpa-onnx, no PyTorch). Only the
voice print — a list of numbers — is kept, encrypted with DPAPI (security.set_secret). No recordings are stored."""
import os
import numpy as np

import security

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# wespeaker ResNet34 (26 MB): told 6 synthetic voices apart (owner 0.91-0.93, others ≤ 0.73) where CAM++ could not (all ~0.85)
MODEL = os.environ.get("FRIDAY_SPK_MODEL", os.path.join(ROOT, "models", "speaker", "wespeaker_en_voxceleb_resnet34.onnx"))
THRESHOLD_ENV = os.environ.get("FRIDAY_SPK_THRESHOLD")  # fixed cosine threshold; else set from the owner's own clips at enrolment
MIN_SAMPLES = 4800  # 0.3 s: shorter is not judged (friday.py then rejects it when enrolled)
_ext = None


def _extractor():
    global _ext
    if _ext is None:
        import sherpa_onnx
        _ext = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=MODEL, num_threads=1, provider="cpu"))
    return _ext


def embed(audio16k):
    """Unit-length voice vector for float32 16 kHz mono audio (≥ ~1 s)."""
    ext = _extractor()
    st = ext.create_stream()
    st.accept_waveform(16000, np.asarray(audio16k, dtype=np.float32))
    st.input_finished()
    v = np.array(ext.compute(st), dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def enroll(clips):
    """Voice print from several clips of the owner (mean of their vectors) — saved encrypted. Returns the clip agreement."""
    vs = [embed(c) for c in clips if len(c) >= 16000]
    if len(vs) < 3:
        raise ValueError("need at least 3 clips of 1 s or more")
    p = np.mean(vs, axis=0)
    p /= np.linalg.norm(p)
    # how alike the owner's own clips are (each against the mean of the others) sets the bar: 0.15 below the least alike
    loo = []
    for i, v in enumerate(vs):
        q = np.mean([w for j, w in enumerate(vs) if j != i], axis=0)
        loo.append(float(v @ (q / np.linalg.norm(q))))
    security.set_secret("voice_print", [round(float(x), 6) for x in p])
    security.set_secret("voice_threshold", round(max(0.35, min(loo) - 0.15), 3))
    return min(loo)


def threshold():
    return float(THRESHOLD_ENV) if THRESHOLD_ENV else float(security.secret("voice_threshold", 0.5))


def enrolled():
    return security.secret("voice_print") is not None


def forget():
    security.set_secret("voice_print", None)
    security.set_secret("voice_threshold", None)


def score(audio16k):
    """Cosine similarity to the owner's print (-1..1), or None when not enrolled / too short to judge."""
    p = security.secret("voice_print")
    if p is None or len(audio16k) < MIN_SAMPLES:
        return None
    return float(embed(audio16k) @ np.array(p, dtype=np.float32))


def is_owner(audio16k):
    """True / False — and True when not enrolled or too short (the feature is then simply off)."""
    s = score(audio16k)
    return True if s is None else s >= threshold()


if __name__ == "__main__":
    import asyncio, io, sys, tempfile, time, wave
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    security.SECRETS = os.path.join(tempfile.mkdtemp(), "s.dat")
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader

    async def tts(text, voice):
        s = SpeechSynthesizer()
        s.voice = next(v for v in SpeechSynthesizer.all_voices if voice in v.display_name)
        st = await s.synthesize_text_to_stream_async(text)
        r = DataReader(st.get_input_stream_at(0))
        await r.load_async(st.size)
        b = bytearray(st.size)
        r.read_bytes(b)
        with wave.open(io.BytesIO(bytes(b))) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
            rate = w.getframerate()
        return np.interp(np.arange(0, len(a), rate / 16000), np.arange(len(a)), a).astype(np.float32)

    lines = ["Hey Friday, what time is it?", "Open YouTube and play some music please", "Remind me in ten minutes to call mom",
             "What is the weather like today?", "Switch to Visual Studio Code", "Summarise what I copied",
             "Turn off the screen for a while", "How many tasks do I have today?"]
    voices = [v.display_name for v in SpeechSynthesizer.all_voices]
    owner, others = "David", [v for v in ("Zira", "Mark", "George", "Hazel", "Susan") if any(v in x for x in voices)]
    clips = {v: [asyncio.run(tts(t, v)) for t in lines] for v in [owner] + others}
    t0 = time.perf_counter()
    agree = enroll(clips[owner][:5])
    same = [score(c) for c in clips[owner][5:]]
    diff = {v: max(score(c) for c in clips[v][5:]) for v in others}
    dt = (time.perf_counter() - t0) / (5 + 3 + 3 * len(others))
    print(f"enrol self-agreement {agree:.2f} -> threshold {threshold():.2f} · owner (unseen lines) {min(same):.2f}-{max(same):.2f} · "
          f"others max {diff} · {dt * 1000:.0f} ms/clip")
    assert min(same) >= threshold() and max(diff.values()) < threshold(), (same, diff)
    assert score(np.zeros(3000, np.float32)) is None  # too short to judge
    forget()
    assert not enrolled() and is_owner(clips["Zira"][0])  # not enrolled: the feature is off
    print("VOICEID SELFTEST OK (synthetic voices only — the owner's real voice is tested by enrolling)")
