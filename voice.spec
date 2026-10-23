# PyInstaller spec for FRIDAY-voice.exe (PLAN §75) — Piper's English voice from its own venv (.venv-tts: numpy<2).
# build:  .venv-tts\Scripts\pyinstaller.exe voice.spec --noconfirm   ->  dist\FRIDAY-voice\
# FRIDAY.exe starts it as "FRIDAY-voice.exe --serve piper <voice>" (tts_th._request). Thai Piper (tltk + gensim,
# sklearn, pandas: ~400 MB) is left out: it is only a fallback engine; the Thai voice is Vanira inside FRIDAY.exe.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for pkg in ("piper", "onnxruntime"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hidden += h
a = Analysis(["app/tts_th.py"], pathex=["app"], datas=datas, binaries=binaries, hiddenimports=hidden,
             excludes=["tltk", "gensim", "sklearn", "pandas", "nltk", "scipy", "matplotlib", "tkinter"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FRIDAY-voice", console=True, icon="assets/friday.ico", upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="FRIDAY-voice", upx=False)
