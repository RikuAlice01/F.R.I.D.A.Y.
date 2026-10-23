"""Windowless launcher for the tray mode (what the Ctrl+Alt+J shortcut runs, with the *base* pythonw.exe).

uv's .venv\\Scripts\\pythonw.exe starts a console python.exe, so Windows 11 flashes a Terminal window.
Starting the venv python with CREATE_NO_WINDOW gives it a hidden console instead — no window at all.
Stdlib only: runs before (and outside) the venv.
"""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
subprocess.Popen([os.path.join(HERE, ".venv", "Scripts", "python.exe"), os.path.join(HERE, "app", "friday.py"), "--tray"],
                 cwd=HERE, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
