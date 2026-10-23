"""FRIDAY side panel: right 20% of the screen, blurred glass, Siri-style orb, chat preview.

Separate process (friday.py starts it); reads JSON lines on stdin:
    {"state": "idle|listening|thinking|speaking"}   {"msg": {"role": "user|assistant|tool", "text": "..."}}
    {"open": true|false|"toggle"}   {"sessions": [...]}   {"reset": [msgs]}
and writes what the user does in the panel as JSON lines on stdout: {"input": "..."} {"cmd": "sub|clone|main|switch", ...}
Passive (default): any non-idle state slides the panel in, IDLE_HIDE_S of idle slides it out; click-through, never
focused, so it can't get in the way. Interactive ("open", from the tray icon): takes clicks and keyboard, shows the
session bar and an input box, until Esc / ✕ / tray click again / INTERACTIVE_HIDE_S without activity.
"""
import base64, ctypes, io, json, os, re, sys, threading, time
from ctypes import wintypes

import webview

WIDTH = float(os.environ.get("FRIDAY_UI_WIDTH", "0.20"))  # fraction of the screen width
IDLE_HIDE_S = float(os.environ.get("FRIDAY_UI_HIDE_S", "15"))
INTERACTIVE_HIDE_S = 180
IMG_MAX = 8 * 2**20  # bytes per image sent to the page
VAULT = os.environ.get("FRIDAY_VAULT", os.path.join(os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vault"))
IMG_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
IMG_REF = re.compile(r"!\[[^\]]*\]\(<?([^)>]+)>?\)|!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]|([A-Za-z]:\\[^\s\"'<>|*?]+?\.(?:png|jpe?g|gif|webp|bmp))", re.I)


def local_images(texts):
    """{ref: data URI} for image references in messages: absolute paths, Markdown ![](path), Obsidian ![[name.png]]
    (searched in the vault). The page can't load file:// itself, so the bytes travel inline. Images only, size-capped."""
    out = {}
    for text in texts:
        for m in IMG_REF.finditer(text or ""):
            ref = (m.group(1) or m.group(2) or m.group(3)).strip()
            if ref in out:
                continue
            path = ref if os.path.isabs(ref) else None
            if path is None:  # Obsidian embed / relative: first match by file name inside the vault
                for root, _, files in os.walk(VAULT):
                    if os.path.basename(ref) in files:
                        path = os.path.join(root, os.path.basename(ref))
                        break
            ext = os.path.splitext(path or "")[1].lower()
            if path and ext in IMG_EXT and os.path.isfile(path) and os.path.getsize(path) <= IMG_MAX:
                with open(path, "rb") as f:
                    out[ref] = f"data:{IMG_EXT[ext]};base64," + base64.b64encode(f.read()).decode()
    return out


BACKDROP_S = 2.0  # refresh of the blurred desktop behind the chat bubbles, only while the panel is shown
BLUR = os.environ.get("FRIDAY_UI_BLUR", "0") == "1"  # default: see-through glass (owner's choice), 1 = frosted blur
SLIDE_S = 0.28

user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
GWL_EXSTYLE, HWND_TOPMOST = -20, -1
WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x08000000
WS_EX_APPWINDOW = 0x40000
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x10, 0x40
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]


class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENTPOLICY)), ("SizeOfData", ctypes.c_size_t)]


def log(msg):
    print(f"ui {time.strftime('%H:%M:%S')}: {msg}", file=sys.stderr, flush=True)


def work_area():
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA: screen minus taskbar
    return r.left, r.top, r.right, r.bottom


class Panel:
    def __init__(self, window):
        self.w, self.hwnd, self.shown, self.idle_since = window, None, False, time.time()
        self.lock = threading.Lock()
        self.interactive, self.active_at = False, 0.0
        self.refresh = threading.Event()

    def setup(self):
        for _ in range(300):  # native form exists only once the window is shown (it starts off-screen, not hidden)
            if self.w.native is not None:
                break
            time.sleep(0.05)
        self.hwnd = int(self.w.native.Handle.ToInt64())
        log("native window ready")
        # pywebview's transparent-window hack re-shows the form when the page starts loading: wait for that first,
        # or it pops back up (with a taskbar button) after we hide it
        log("page loaded" if self.w.events.loaded.wait(15) else "page load timeout (15 s)")
        user32.ShowWindow(self.hwnd, SW_HIDE)
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        # click-through, never activated, no taskbar button: WinForms sets WS_EX_APPWINDOW, which forces a button
        # even on a tool window, so it must be cleared (the change applies on the next show)
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE,
                                 (ex | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
        user32.SetLayeredWindowAttributes(self.hwnd, 0, 255, 2)  # LWA_ALPHA 255: layered but fully visible
        # DWM composites the window over the desktop: 2 = ACCENT_ENABLE_TRANSPARENTGRADIENT with a fully transparent
        # tint (see-through), 3 = ACCENT_ENABLE_BLURBEHIND (frosted). The page itself adds the 0->80% black fade.
        accent = ACCENTPOLICY(3 if BLUR else 2, 2, 0x00000000, 0)  # flags 2: use GradientColor
        data = WINCOMPATTRDATA(19, ctypes.pointer(accent), ctypes.sizeof(accent))  # WCA_ACCENT_POLICY
        user32.SetWindowCompositionAttribute(self.hwnd, ctypes.byref(data))
        pref = ctypes.c_int(1)  # DWMWCP_DONOTROUND: flush against the screen edge
        dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        no_border = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_BORDER_COLOR = DWMWA_COLOR_NONE: no Windows 11 1-px frame
        dwmapi.DwmSetWindowAttribute(self.hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
        # WinForms paints its form background opaque (white): make the whole client area DWM "glass" and paint it
        # black, so pixels the transparent WebView leaves empty show the blurred desktop instead
        margins = (ctypes.c_int * 4)(-1, -1, -1, -1)
        dwmapi.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(margins))
        from System import Action
        from System.Drawing import Color
        self.w.native.Invoke(Action(lambda: setattr(self.w.native, "BackColor", Color.Black)))
        user32.ShowWindow(self.hwnd, SW_HIDE)
        log("setup done")

    def _geometry(self):
        left, top, right, bottom = work_area()
        width = int((right - left) * WIDTH)
        return right, top, width, bottom - top

    def slide(self, show):
        with self.lock:
            if show == self.shown or not self.hwnd:
                return
            right, top, width, height = self._geometry()
            if show:
                user32.ShowWindow(self.hwnd, 5 if self.interactive else SW_SHOWNOACTIVATE)  # 5 = SW_SHOW
            t0 = time.perf_counter()
            while True:
                p = min(1.0, (time.perf_counter() - t0) / SLIDE_S)
                ease = 1 - (1 - p) ** 3  # easeOutCubic
                frac = ease if show else 1 - ease
                user32.SetWindowPos(self.hwnd, HWND_TOPMOST, right - int(width * frac), top, width, height,
                                    SWP_NOACTIVATE | SWP_SHOWWINDOW)
                if p >= 1:
                    break
                time.sleep(1 / 120)
            if not show:
                user32.ShowWindow(self.hwnd, SW_HIDE)
            self.shown = show
        self.js({"visible": show})  # the orb stops drawing while the panel is away (§35)
        if show:
            self.refresh.set()  # new backdrop right away, not at the next tick

    def set_interactive(self, on):
        if on == self.interactive or not self.hwnd:
            return
        self.interactive, self.active_at = on, time.time()
        self.w.focus = on  # pywebview re-adds WS_EX_NOACTIVATE on every activation while focus=False: typing went nowhere
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        passive = WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, (ex & ~passive) if on else (ex | passive))
        self.js({"interactive": on})
        if on:
            self.slide(True)
            fg = user32.SetForegroundWindow(self.hwnd)  # friday.py granted this via AllowSetForegroundWindow
            try:  # keyboard focus must reach the WebView2 control, not just the form
                from System import Action
                self.w.native.Invoke(Action(lambda: self.w.native.browser.webview.Focus()))
            except Exception as e:
                log(f"webview focus failed: {e}")
            time.sleep(0.3)  # typing problems: what had focus when the user started to type (§27)
            page = self.w.evaluate_js("document.hasFocus() + ' ' + (document.activeElement || {}).id")
            log(f"interactive: SetForegroundWindow={fg} foreground={user32.GetForegroundWindow() == self.hwnd} page={page}")
        else:
            self.slide(False)
            self.idle_since = time.time()
            emit({"closed": True})  # the user closed the drawer (Esc, tray click, typing timeout) = stop listening

    def js(self, e):
        self.w.evaluate_js(f"window.friday && friday.event({json.dumps(e, ensure_ascii=False)})")

    def handle(self, e):
        if "open" in e:
            self.set_interactive(not self.interactive if e["open"] == "toggle" else bool(e["open"]))
        self.active_at = time.time()
        if "state" in e:
            if e["state"] == "idle":
                self.idle_since = time.time()
            else:
                self.idle_since = None
                self.slide(True)
        if "msg" in e:
            self.slide(True)
            if self.idle_since is not None:
                self.idle_since = time.time()
        texts = [e["msg"]["text"]] if "msg" in e else [m["text"] for m in e.get("reset", []) + e.get("older", [])]
        imgs = local_images(texts)
        if imgs:
            e["images"] = imgs
        self.js({k: v for k, v in e.items() if k != "open"})

    def backdrop(self):
        """Blurred copy of the desktop behind the panel, for the chat bubbles only (the rest stays see-through).
        Windows can blur a whole window or nothing, and CSS backdrop-filter can't see the desktop, so: grab the screen
        under the panel with the panel excluded from capture, blur it, and hand it to the page as a fixed background."""
        from PIL import ImageFilter, ImageGrab
        r = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        user32.SetWindowDisplayAffinity(self.hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE: the grab sees what is behind us
        try:
            img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
        finally:
            user32.SetWindowDisplayAffinity(self.hwnd, 0)  # screenshots/screen sharing still show the panel
        small = img.convert("RGB").resize((max(1, img.width // 4), max(1, img.height // 4)))  # cheap blur, ~10 KB
        buf = io.BytesIO()
        small.filter(ImageFilter.GaussianBlur(4)).save(buf, "JPEG", quality=70)
        self.js({"backdrop": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()})

    def backdrop_loop(self):
        while True:
            self.refresh.wait(BACKDROP_S)
            self.refresh.clear()
            if self.shown:
                try:
                    self.backdrop()
                except Exception as ex:
                    log(f"backdrop: {type(ex).__name__}: {ex}")

    def run(self):
        self.setup()
        threading.Thread(target=self.autohide, daemon=True).start()
        threading.Thread(target=self.backdrop_loop, daemon=True).start()
        for line in sys.stdin:  # parent closes the pipe -> EOF -> quit
            try:
                self.handle(json.loads(line))
            except Exception as ex:
                print(f"ui: {type(ex).__name__}: {ex}", file=sys.stderr)
        os._exit(0)  # w.destroy() can hang WebView2 shutdown from this thread; nothing to save

    def autohide(self):
        while True:
            time.sleep(0.5)
            if self.interactive:
                if time.time() - self.active_at > INTERACTIVE_HIDE_S:
                    self.set_interactive(False)
            elif self.shown and self.idle_since is not None and time.time() - self.idle_since > IDLE_HIDE_S:
                self.slide(False)


class Api:
    """Called from the page (window.pywebview.api.post): forwarded to friday.py as a JSON line on stdout."""

    def __init__(self):
        self._panel = None  # underscore: pywebview walks public attributes to expose them to JS (and chokes on WebView2)

    def post(self, obj):
        self._panel.active_at = time.time()
        if obj.get("close"):
            threading.Thread(target=self._panel.set_interactive, args=(False,), daemon=True).start()
            return
        emit(obj)


def emit(obj):
    """One JSON line to friday.py. A single write: print() writes text and newline apart, threads could interleave."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    api = Api()
    html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.html"), encoding="utf-8").read()
    left, top, right, bottom = work_area()
    w = webview.create_window("FRIDAY", html=html, width=int((right - left) * WIDTH), height=bottom - top,
                              x=right, y=top, frameless=True, transparent=True, on_top=True, focus=False,
                              resizable=False, background_color="#000000", js_api=api,  # x=right edge: off-screen
                              easy_drag=False)  # a docked panel: mouse-down must not start dragging the window
    panel = api._panel = Panel(w)
    webview.start(panel.run, private_mode=True)


if __name__ == "__main__":
    main()
