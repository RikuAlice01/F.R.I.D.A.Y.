"""Build FRIDAY's installer (PLAN §75):  .venv\\Scripts\\python.exe installer\\build.py

Needs (built first):  dist\\FRIDAY       (.venv\\Scripts\\pyinstaller.exe friday.spec --noconfirm)
                      dist\\FRIDAY-voice (.venv-tts\\Scripts\\pyinstaller.exe voice.spec --noconfirm)
                      Inno Setup 6       (E:\\tools\\InnoSetup\\ISCC.exe, or ISCC on PATH / env ISCC)
Out: dist\\installer\\FRIDAY-Setup-<version>.exe (+ .bin parts). Nothing personal goes in: settings.json is the
default one, no data\\, no secrets.
"""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))
import rules  # noqa: E402  (DEFAULT_SETTINGS only)

for need in ("dist/FRIDAY/FRIDAY.exe", "dist/FRIDAY-voice/FRIDAY-voice.exe", "models/vanira/tts.onnx",
             "models/piper/en_US-hfc_female-medium.onnx", "models/speaker/wespeaker_en_voxceleb_resnet34.onnx"):
    if not os.path.isfile(os.path.join(ROOT, need)):
        sys.exit(f"missing {need} — build/download it first (see the docstring)")

stage = os.path.join(HERE, "stage", "config")
shutil.rmtree(os.path.join(HERE, "stage"), ignore_errors=True)
os.makedirs(stage)
with open(os.path.join(stage, "settings.json"), "w", encoding="utf-8") as f:
    json.dump(rules.DEFAULT_SETTINGS, f, indent=2)  # never the owner's own settings

version = re.search(r'__version__ = "([\d.]+)"', open(os.path.join(ROOT, "app", "friday.py"), encoding="utf-8").read())[1]
iscc = os.environ.get("ISCC") or shutil.which("ISCC") or r"E:\tools\InnoSetup\ISCC.exe"
r = subprocess.run([iscc, f"/DAppVersion={version}", os.path.join(HERE, "friday.iss")])
sys.exit(r.returncode)
