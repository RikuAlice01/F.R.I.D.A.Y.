"""Windows on the desktop (PLAN §55): find by app or title, bring to front, move to another monitor, maximize,
minimize. Win32 calls only — no simulated clicks or keys."""
import ctypes, os
from ctypes import wintypes

u = ctypes.windll.user32
u.GetWindowLongW.restype = ctypes.c_long
ALIASES = {"vscode": "code.exe", "vs code": "code.exe", "visual studio code": "code.exe", "โค้ด": "code.exe",
           "chrome": "chrome.exe", "โครม": "chrome.exe", "brave": "brave.exe", "เบรฟ": "brave.exe", "edge": "msedge.exe",
           "explorer": "explorer.exe", "file explorer": "explorer.exe", "ไฟล์": "explorer.exe", "spotify": "spotify.exe",
           "obsidian": "obsidian.exe", "discord": "discord.exe", "line": "line.exe", "word": "winword.exe", "excel": "excel.exe",
           "notepad": "notepad.exe", "โน้ตแพด": "notepad.exe", "terminal": "windowsterminal.exe"}


def _proc_name(hwnd):
    import psutil
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return pid.value, psutil.Process(pid.value).name().lower()
    except Exception:
        return pid.value, ""


def windows():
    """[(hwnd, title, exe)] of the visible app windows (taskbar-type: titled, no owner, not tool windows)."""
    out, own = [], os.getpid()
    import psutil
    mine = {own} | {c.pid for c in psutil.Process(own).children(recursive=True)}
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def one(h, _):
        if not u.IsWindowVisible(h) or u.GetWindow(h, 4) or u.GetWindowLongW(h, -20) & 0x80:  # owner / WS_EX_TOOLWINDOW
            return True
        cloaked = ctypes.c_int(0)  # suspended UWP / other-desktop windows look visible but aren't on screen
        ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        n = u.GetWindowTextLengthW(h)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        pid, exe = _proc_name(h)
        if pid not in mine and buf.value not in ("Program Manager", "FRIDAY"):
            out.append((h, buf.value, exe))
        return True
    u.EnumWindows(cb(one), 0)
    return out


def find(query, wins=None):
    """Best window for "vscode" / "youtube" / part of a title. App alias first, then title words."""
    q = " ".join(str(query).lower().split())
    wins = windows() if wins is None else wins
    exe = ALIASES.get(q)
    if exe:
        hits = [w for w in wins if w[2] == exe]
        if hits:
            return hits[0]
    words = [x for x in q.split() if x]
    for w in wins:  # EnumWindows lists front-most first
        hay = (w[1] + " " + w[2]).lower()
        if words and all(x in hay for x in words):
            return w
    return None


def focus(hwnd):
    """Bring to front without fake input: restore if minimized, then borrow the foreground thread's input for a moment."""
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg = u.GetForegroundWindow()
    k = ctypes.windll.kernel32
    a, b = u.GetWindowThreadProcessId(fg, None), k.GetCurrentThreadId()
    attached = a and a != b and u.AttachThreadInput(b, a, True)
    try:
        u.BringWindowToTop(hwnd)
        ok = bool(u.SetForegroundWindow(hwnd))
    finally:
        if attached:
            u.AttachThreadInput(b, a, False)
    return ok or u.GetForegroundWindow() == hwnd


def show(hwnd, how):
    """maximize | minimize | restore."""
    u.ShowWindow(hwnd, {"maximize": 3, "minimize": 6, "restore": 9}[how])


def move_to(hwnd, where, monitors):
    """where: left | right | main | 1 | 2 ... -> moves the window there, keeping it maximized if it was."""
    if not monitors:
        return False
    if where in ("left", "right"):
        target = (min if where == "left" else max)(monitors, key=lambda m: m[0])
    elif where == "main":
        target = next((m for m in monitors if m[0] == 0 and m[1] == 0), monitors[0])
    else:
        i = int(where) - 1
        if not 0 <= i < len(monitors):
            return False
        target = sorted(monitors, key=lambda m: m[0])[i]
    was_max = bool(u.IsZoomed(hwnd))
    u.ShowWindow(hwnd, 9)
    x, y, w, h = target
    u.SetWindowPos(hwnd, None, x + 40, y + 40, int(w * .8), int(h * .8), 0x0004 | 0x0040)  # NOZORDER | SHOWWINDOW
    if was_max:
        u.ShowWindow(hwnd, 3)
    return True


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


def _info(hmon):
    mi = _MonitorInfo()
    mi.cbSize = ctypes.sizeof(mi)
    u.GetMonitorInfoW(hmon, ctypes.byref(mi))
    w, m = mi.rcWork, mi.rcMonitor
    return {"name": mi.szDevice, "primary": bool(mi.dwFlags & 1), "work": (w.left, w.top, w.right, w.bottom),
            "size": (m.right - m.left, m.bottom - m.top)}


def screens():
    """§105 every monitor, left to right (= "จอ 1, จอ 2 …" like move_to): {name, primary, work (minus taskbar), size}."""
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    u.EnumDisplayMonitors(None, None, cb(lambda h, *_: out.append(_info(h)) or 1), 0)
    return sorted(out, key=lambda m: m["work"][0])


def screen_at_cursor():
    p = wintypes.POINT()
    u.GetCursorPos(ctypes.byref(p))
    return _info(u.MonitorFromPoint(p, 2))  # MONITOR_DEFAULTTONEAREST


def panel_screen(choice, all_screens=None):
    """§105 where the chat panel goes: "primary" (default) · "mouse" (the screen the pointer is on) · a device name
    (\\\\.\\DISPLAY2). A screen that is gone (unplugged) -> the primary one."""
    if choice == "mouse":
        return screen_at_cursor()
    ss = all_screens if all_screens is not None else screens()
    return next((s for s in ss if s["name"] == choice), None) or next((s for s in ss if s["primary"]), ss[0] if ss else None)


if __name__ == "__main__":
    ss = screens()
    assert ss and sum(s["primary"] for s in ss) == 1 and all(s["work"][2] > s["work"][0] for s in ss)
    fake = [{"name": "A", "primary": False, "work": (-1920, 0, 0, 1032)}, {"name": "B", "primary": True, "work": (0, 0, 1920, 1032)}]
    assert panel_screen("A", fake)["name"] == "A" and panel_screen("primary", fake)["name"] == "B"
    assert panel_screen(r"\\.\DISPLAY9", fake)["name"] == "B" and panel_screen("mouse")["name"] in [s["name"] for s in ss]
    print("screens:", [(s["name"], s["work"], "primary" if s["primary"] else "") for s in ss])
    fake = [(1, "friday - Visual Studio Code", "code.exe"), (2, "Khalid - Better - YouTube - Brave", "brave.exe"),
            (3, "Downloads", "explorer.exe")]
    assert find("vscode", fake)[0] == 1 and find("youtube", fake)[0] == 2 and find("brave", fake)[0] == 2
    assert find("downloads", fake)[0] == 3 and find("spotify", fake) is None and find("", fake) is None
    ws = windows()  # real desktop, read-only: nothing is moved or focused here
    assert all(t != "FRIDAY" for _, t, _ in ws)
    print("windows:", [(t[:30], e) for _, t, e in ws[:6]])
    print("WINDOWS SELFTEST OK")
