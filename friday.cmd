@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
"%~dp0.venv\Scripts\python.exe" "%~dp0app\friday.py" %*
