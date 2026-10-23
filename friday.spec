# PyInstaller spec for FRIDAY.exe (PLAN §69) — build:  .venv\Scripts\pyinstaller.exe friday.spec --noconfirm
# One folder, windowed: dist\FRIDAY\FRIDAY.exe + _internal\ (Python + libraries + CUDA DLLs).
# Not inside: models\, data\, config\, skills\, .venv-tts (Piper's numpy<2 venv) — the exe finds them in E:\friday.
import glob, os
from PyInstaller.utils.hooks import collect_all, collect_data_files
import PyInstaller.building.build_main as _bm

# PyInstaller imports every collected package in ONE process to learn their DLL folders: our native libraries crash
# each other there (fastembed.text, openwakeword, onnxruntime.quantization — the import-order trap in
# docs/knowledge/traps.md). Only packages that add a DLL folder at import (delvewheel's <name>.libs: numpy, scipy, av)
# need that step, so only they get it.
SITE = os.path.join(".venv", "Lib", "site-packages")
_find = _bm.find_binary_dependencies
_bm.find_binary_dependencies = lambda binaries, packages, *rest: _find(
    binaries, [p for p in packages if os.path.isdir(os.path.join(SITE, p.split(".")[0] + ".libs"))], *rest)

datas, binaries, hidden = [("app/ui.html", ".")], [], []
for pkg in ("ctranslate2", "faster_whisper", "onnxruntime", "sherpa_onnx", "openwakeword", "webview",
            "pystray", "winrt", "clr_loader", "pythonnet", "docx", "pptx", "openpyxl", "pypdf",
            "sounddevice", "_sounddevice_data", "monitorcontrol", "comtypes", "pycaw", "qrcode",
            "vaniratts", "vachanatts", "vachana_g2p", "pythainlp", "pycrfsuite", "ssg",
            "cryptography", "segno", "anthropic"):  # Thai voice + its word data · phone TLS · QR · §84 Claude brain
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue  # not installed in this venv
    datas += d
    binaries += b
    hidden += h
datas += collect_data_files("fastembed")  # collect_all imports fastembed.text, which crashes the analysis
site = os.path.join(".venv", "Lib", "site-packages")
for dll in glob.glob(os.path.join(site, "nvidia", "*", "bin", "*.dll")):  # cuBLAS / cuDNN for Whisper on the GPU
    binaries.append((dll, os.path.relpath(os.path.dirname(dll), site)))
# modules friday.py imports by name at run time
hidden += ["ui", "tts_th", "memory", "rules", "docsearch", "wakeword", "sessions", "skills", "documents", "hardware",
           "security", "workspace", "weather", "reminders", "media", "tasks", "windows", "journal", "voiceid",
           "remote", "brain", "brain_claude", "brain_openai", "computer"]

a = Analysis(["app/friday.py"], pathex=["app"], datas=datas, binaries=binaries, hiddenimports=hidden,
             excludes=["torch", "tensorflow", "matplotlib", "IPython", "pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FRIDAY", console=False, icon="assets/friday.ico",
          upx=False, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="FRIDAY", upx=False)
