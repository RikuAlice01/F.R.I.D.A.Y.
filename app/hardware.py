"""This PC's hardware and devices on the LAN (PLAN §32). Each function does one thing and returns a short sentence;
permission checks and confirm() live in friday.py (hardware_action), never here.
System sound/mic: pycaw (Core Audio) · brightness: monitorcontrol (DDC/CI) · Wi-Fi/Bluetooth: WinRT Radios (no admin) ·
power: powrprof / shutdown / powercfg · Arduino/ESP32: pyserial · smart home: Home Assistant / Tasmota over HTTP, LAN only."""
import asyncio, ctypes, ipaddress, json, os, re, socket, subprocess, urllib.parse, urllib.request

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args, timeout=15):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)


# ---------- system sound + mic ----------
def _endpoint(mic=False):
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    comtypes.CoInitialize()  # tools run on worker threads
    dev = AudioUtilities.GetMicrophone() if mic else AudioUtilities.GetSpeakers()
    dev = getattr(dev, "_dev", dev)  # newer pycaw wraps the IMMDevice
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return iface.QueryInterface(IAudioEndpointVolume)  # not ctypes.cast: two owners of one pointer = double Release = crash


def sound(level=None, mute=None):
    ep = _endpoint()
    if level is not None:
        ep.SetMasterVolumeLevelScalar(min(100, max(0, int(level))) / 100, None)
        ep.SetMute(0, None)
    if mute is not None:
        ep.SetMute(int(bool(mute)), None)
    return f"System volume {round(ep.GetMasterVolumeLevelScalar() * 100)}%{' (muted)' if ep.GetMute() else ''}."


def mic(mute=None):
    ep = _endpoint(mic=True)
    if mute is not None:
        ep.SetMute(int(bool(mute)), None)
    return f"Microphone {'muted' if ep.GetMute() else 'on'}."


# ---------- display ----------
def brightness(level=None):
    """level: 0-100, or "+20" / "-20" relative to each monitor's current value, or None to read."""
    from monitorcontrol import get_monitors
    out = []
    rel = level is not None and str(level).strip()[:1] in "+-"
    for i, m in enumerate(get_monitors(), 1):
        try:
            with m:
                if level is not None:
                    v = (m.get_luminance() if rel else 0) + int(float(level))
                    m.set_luminance(min(100, max(0, v)))
                out.append(f"monitor {i}: {m.get_luminance()}%")
        except Exception as e:  # a monitor without DDC/CI (or switched off)
            out.append(f"monitor {i}: no brightness control ({type(e).__name__})")
    if not out or all("no brightness control" in o for o in out):
        return "Not done: no monitor with brightness control (DDC/CI off, or the screen is asleep)."
    return "Brightness: " + ", ".join(out) + "."


def monitors():
    """(x, y, w, h) of every connected monitor in real pixels, read fresh each time (screens can be plugged in)."""
    from ctypes import wintypes
    rects = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def one(h, dc, r, lp):
        rects.append((r[0].left, r[0].top, r[0].right - r[0].left, r[0].bottom - r[0].top))
        return 1
    ctypes.windll.user32.EnumDisplayMonitors(None, None, cb(one), 0)
    return rects


class Curtain:
    """Borderless black windows, one per monitor (§44: a single window across screens of different size/DPI gets
    scaled wrongly), at `alpha` 0 clear .. 1 black. No taskbar buttons. Create, use and destroy on one thread."""

    def __init__(self, alpha=0.0, area=None):
        import tkinter as tk
        u = ctypes.windll.user32
        try:  # real pixels per monitor for this thread's windows, so each curtain fits its screen exactly
            u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        except (AttributeError, OSError):
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.windows = []
        for x, y, w, h in ([area] if area else monitors()):
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", alpha)
            win.configure(bg="black", cursor="none")
            win.geometry(f"{w}x{h}{x:+d}{y:+d}")
            self.windows.append(win)
        self.root.update()

    def attributes(self, name, value):  # every screen fades together
        for win in self.windows:
            win.attributes(name, value)

    def update(self):
        self.root.update()

    def destroy(self):
        self.root.destroy()


def curtain(alpha=0.0, area=None):
    return Curtain(alpha, area)


def ease(seconds, step):
    """step(k) for k going 0 -> 1 over `seconds` on a smoothstep curve (soft start, soft end), ~60 times a second."""
    import time
    t0 = time.perf_counter()
    while True:
        k = min(1.0, (time.perf_counter() - t0) / max(seconds, 0.01))
        step(k * k * (3 - 2 * k))
        if k >= 1:
            return
        time.sleep(1 / 60)


def fade_to_black(seconds=1.5, area=None, also=None):
    """Curtain from clear to black over `seconds`; also(k) runs each step (the sound fades with it). Returns it."""
    root = curtain(0.0, area)
    try:
        ease(seconds, lambda k: (root.attributes("-alpha", k), also and also(k), root.update()))
        return root
    except Exception:
        root.destroy()
        raise


_asleep = {}  # sound before "พักจอ": {"level": 0..1, "muted": bool}; empty when the screens are awake


def _sound_fader(level_from, level_to):
    """also(k) for ease(): system volume from -> to, on this thread's own COM endpoint."""
    ep = _endpoint()
    return lambda k: ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level_from + (level_to - level_from) * k)), None)


def display_off(fade=1.5, area=None, power=True):
    """Screens and the PC's sound fade out together over `fade` s, then the screens switch off and the sound is muted
    (§41, §43). The sound level is kept under the mute; display_on / any mouse or key use brings both back softly."""
    import threading, time
    fader = None
    try:
        ep = _endpoint()
        if not _asleep:
            _asleep.update(level=ep.GetMasterVolumeLevelScalar(), muted=bool(ep.GetMute()))
        if not _asleep["muted"]:
            fader = _sound_fader(_asleep["level"], 0.0)
    except Exception:
        pass  # no audio device: the screens still go dark
    shade = None
    try:
        shade = fade_to_black(fade, area, fader) if fade else None
    except Exception:
        pass  # no fade is better than no screen-off
    try:
        ep = _endpoint()
        ep.SetMute(1, None)
        ep.SetMasterVolumeLevelScalar(_asleep.get("level", ep.GetMasterVolumeLevelScalar()), None)  # silent, level kept
    except Exception:
        pass
    if power:
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)  # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, off
    if shade is not None:
        time.sleep(1.0 if power else 0.2)  # monitors go dark under the curtain, then it is removed
        shade.destroy()
    if power:
        threading.Thread(target=_wake_watch, args=(_last_input(),), daemon=True).start()
    return "Screens and sound off (say \"เปิดจอ\" or move the mouse)."


def _last_input():
    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    li = LII(ctypes.sizeof(LII), 0)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
    return li.dwTime


def _wake_watch(since):
    """Woken by the mouse/keyboard instead of "เปิดจอ": Windows lights the screens at once; bring the sound back softly."""
    import time
    while _asleep:
        if _last_input() != since:
            restore_sound(1.0)
            return
        time.sleep(0.5)


def restore_sound(seconds=1.5, also=None):
    """Sound back to its level before "พักจอ", rising softly (left muted if it was muted before)."""
    state = dict(_asleep)
    _asleep.clear()
    if not state:
        if also:
            ease(seconds, also)
        return
    ep = _endpoint()
    if state["muted"]:
        if also:
            ease(seconds, also)
        return
    ep.SetMasterVolumeLevelScalar(0.0, None)
    ep.SetMute(0, None)
    fader = _sound_fader(0.0, state["level"])
    ease(seconds, lambda k: (fader(k), also and also(k)))


def display_on(fade=1.5, area=None, power=True):
    """§43 "เปิดจอ": black curtain, wake the screens (no fake mouse/keys), then curtain clears as the sound comes back."""
    shade = curtain(1.0, area)
    try:
        if power:
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, -1)  # SC_MONITORPOWER: on
            ctypes.windll.kernel32.SetThreadExecutionState(0x00000002)  # ES_DISPLAY_REQUIRED: reset the display idle timer
            import time
            time.sleep(0.6)  # monitors take a moment to show a picture
        restore_sound(fade, lambda k: (shade.attributes("-alpha", 1 - k), shade.update()))
    finally:
        shade.destroy()
    return "Screens and sound back on."


def lock():
    ctypes.windll.user32.LockWorkStation()
    return "PC locked."


# ---------- network ----------
def radio(kind, on=None):
    """kind 'wifi'|'bluetooth'. Works only on PCs that have that radio."""
    from winrt.windows.devices.radios import Radio, RadioKind, RadioState
    want = {"wifi": RadioKind.WI_FI, "bluetooth": RadioKind.BLUETOOTH}[kind]

    async def go():
        await Radio.request_access_async()
        found = [r for r in await Radio.get_radios_async() if r.kind == want]
        for r in found:
            if on is not None:
                await r.set_state_async(RadioState.ON if on else RadioState.OFF)
        return [RadioState(r.state).name.lower() for r in found]
    states = asyncio.run(go())
    name = "Wi-Fi" if kind == "wifi" else "Bluetooth"
    return f"{name}: {', '.join(states)}." if states else f"Not done: this PC has no {name} radio."


def network():
    import psutil
    up = [f"{n} ({next((a.address for a in psutil.net_if_addrs().get(n, []) if a.family == socket.AF_INET), 'no IPv4')})"
          for n, st in psutil.net_if_stats().items() if st.isup and not n.lower().startswith(("loopback", "vethernet"))]
    return "Connected adapters: " + (", ".join(up) or "none") + ". " + radio("wifi") + " " + radio("bluetooth")


# ---------- power ----------
def sleep():
    ctypes.windll.powrprof.SetSuspendState(False, False, False)
    return "Going to sleep."


def power_off(restart, minutes=0):
    secs = max(0, int(float(minutes or 0) * 60))
    r = _run(["shutdown", "/r" if restart else "/s", "/t", str(secs), "/c", "FRIDAY"])
    what = "Restart" if restart else "Shutdown"
    return r.stdout.strip() or r.stderr.strip() or f"{what} in {secs // 60} min {secs % 60} s. Say \"cancel shutdown\" to stop it."


def cancel_power_off():
    r = _run(["shutdown", "/a"])
    return "Cancelled the scheduled shutdown/restart." if r.returncode == 0 else "Not done: nothing was scheduled."


PLAN_WORDS = {"ultimate": ("ultimate", "สูงสุด"), "balanced": ("balanced", "สมดุล"),  # ultimate first: "ประสิทธิภาพสูงสุด"
              "high": ("high performance", "ประสิทธิภาพสูง"), "saver": ("power saver", "ประหยัด")}


def _plans():
    return [(g, n, star == "*") for g, n, star in re.findall(r"([0-9a-f-]{36})\s+\((.+?)\)\s*(\*?)", _run(["powercfg", "/list"]).stdout)]


def power_plan(name=None):
    plans = _plans()
    if name:
        n = str(name).lower()
        words = next((w for k, w in PLAN_WORDS.items() if k in n or any(x in n for x in w)), (n,))
        # longest Thai name first: "ประสิทธิภาพสูง" is inside "ทำงานได้ประสิทธิภาพสูงสุด"
        hit = next((g for w in words for g, label, _ in sorted(plans, key=lambda p: len(p[1])) if w in label.lower()), None)
        if not hit:
            return "Not done: no such power plan. Plans: " + ", ".join(label for _, label, _ in plans)
        _run(["powercfg", "/setactive", hit])
        plans = _plans()
    return "Power plans: " + ", ".join(f"{label}{' (active)' if act else ''}" for _, label, act in plans) + "."


def battery():
    import psutil
    b = psutil.sensors_battery()
    return f"Battery {b.percent:.0f}%{' charging' if b.power_plugged else ''}." if b else "No battery (desktop PC)."


def status():
    parts = []
    for f in (sound, mic, brightness, power_plan, battery):
        try:
            parts.append(f())
        except Exception as e:
            parts.append(f"{f.__name__}: unavailable ({type(e).__name__})")
    return " ".join(parts)


# ---------- Arduino / ESP32 over USB serial ----------
def serial_ports():
    import serial.tools.list_ports
    return [f"{p.device} ({p.description})" for p in serial.tools.list_ports.comports()]


def serial_send(text, port, baud=115200, wait=1.5):
    """One line to the board, then whatever it answers within `wait` seconds."""
    import serial
    if not port:
        return "Not done: no serial port set. Ports: " + (", ".join(serial_ports()) or "none") + '. Add "serial_port" to "hardware" in settings.json.'
    with serial.Serial(port, int(baud), timeout=wait) as s:
        s.write((str(text).strip() + "\n").encode())
        s.flush()
        reply = s.read(4096).decode(errors="replace").strip()
    return f"Sent to {port}: {text}. Reply: {reply or '(none)'}"


# ---------- smart home on the LAN (never the internet: CLAUDE.md "everything local") ----------
def lan_only(url):
    """The URL with its host replaced by the checked private/loopback/link-local IP (no second DNS lookup that could
    answer differently), else ValueError."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    ips = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in socket.getaddrinfo(host, None)}
    for ip in ips:
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            raise ValueError(f"{host} is not on the local network ({ip}); FRIDAY only talks to devices on the LAN")
    ip = sorted(ips, key=lambda a: a.version)[0]
    netloc = (f"[{ip}]" if ip.version == 6 else str(ip)) + (f":{parts.port}" if parts.port else "")
    return urllib.parse.urlunsplit(parts._replace(netloc=netloc))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise ValueError("redirect refused: the device tried to send FRIDAY elsewhere")


def _http(url, data=None, token=None, timeout=5):
    req = urllib.request.Request(lan_only(url), data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
        body = r.read().decode(errors="replace")
    return json.loads(body) if body[:1] in "[{" else body


def home(action, target, cfg):
    """action: list | status | on | off | toggle. target: words of an entity id / Tasmota name. cfg = settings "smart_home"."""
    ha, tas = cfg.get("home_assistant") or {}, cfg.get("tasmota") or {}
    if not ha and not tas:
        return ('Not done: smart home is not set up. In settings.json add "smart_home": {"home_assistant": {"url": "http://192.168.x.x:8123", '
                '"token": "<long-lived token>"}, "tasmota": {"<name>": "192.168.x.y"}}.')
    words = [w for w in re.split(r"\W+", str(target).lower()) if w]
    for name, ip in tas.items():  # Tasmota: by its name in settings.json
        if words and all(w in name.lower() for w in words) or action == "list":
            if action == "list":
                continue
            cmd = {"on": "Power On", "off": "Power Off", "toggle": "Power Toggle"}.get(action, "Power")
            r = _http(f"http://{ip}/cm?cmnd={urllib.parse.quote(cmd)}")
            return f"{name}: {r}"
    if ha:
        url, token = ha["url"].rstrip("/"), ha.get("token")
        states = _http(f"{url}/api/states", token=token)
        hits = [s for s in states if all(w in (s["entity_id"] + " " + s["attributes"].get("friendly_name", "")).lower() for w in words)]
        if action in ("list", "status") or not hits:
            rows = [f"{s['entity_id']} ({s['attributes'].get('friendly_name', '')}): {s['state']}" for s in (hits or states)][:15]
            names = ", ".join(tas)
            return ("No match. " if action not in ("list", "status") else "") + "; ".join(rows) + (f". Tasmota: {names}" if names else "")
        if len(hits) > 1:
            return "Several match, say which: " + ", ".join(s["entity_id"] for s in hits[:8])
        service = {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[action]
        _http(f"{url}/api/services/homeassistant/{service}", {"entity_id": hits[0]["entity_id"]}, token)
        return f"{hits[0]['entity_id']}: {service.replace('_', ' ')}."
    return "No device matches. Tasmota devices: " + ", ".join(tas)


if __name__ == "__main__":
    # read-only checks on this PC + logic with fakes; nothing is switched, muted, locked or slept
    print(status())
    v = sound()
    assert v.startswith("System volume") and mic().startswith("Microphone"), v
    assert power_plan().startswith("Power plans:") and "(active)" in power_plan()
    assert battery().startswith(("Battery", "No battery"))
    assert radio("wifi").endswith(".") and network().startswith("Connected adapters:")
    plans = [("g1", "สมดุล", True), ("g2", "ประสิทธิภาพสูง", False), ("g3", "ทำงานได้ประสิทธิภาพสูงสุด", False), ("g4", "ประหยัดพลังงาน", False)]
    set_to = []
    real_plans, real_run = _plans, _run
    _plans = lambda: plans
    _run = lambda args, timeout=15: set_to.append(args[-1]) or subprocess.CompletedProcess(args, 0, "", "")
    for ask, guid in (("high performance", "g2"), ("ประสิทธิภาพสูง", "g2"), ("ultimate", "g3"), ("ประสิทธิภาพสูงสุด", "g3"), ("ประหยัดไฟ", "g4"), ("Balanced", "g1")):
        power_plan(ask)
        assert set_to[-1] == guid, (ask, set_to)
    assert power_plan("turbo").startswith("Not done: no such power plan")
    assert "60 s" in power_off(False, 1) or "1 min" in power_off(False, 1)
    _plans, _run = real_plans, real_run
    for bad in ("http://8.8.8.8/api", "http://example.com/"):
        try:
            lan_only(bad)
            raise AssertionError(bad)
        except (ValueError, OSError):
            pass
    assert lan_only("http://127.0.0.1:8123/api") == "http://127.0.0.1:8123/api" and lan_only("http://localhost:8123/x").startswith("http://127.0.0.1:8123")
    assert lan_only("http://192.168.1.20/cm?cmnd=Power") == "http://192.168.1.20/cm?cmnd=Power"
    # §44 one curtain per connected monitor, each the size of its screen
    ms = monitors()
    assert ms and all(w > 0 and h > 0 for _, _, w, h in ms), ms
    c = Curtain(0.0)
    assert len(c.windows) == len(ms)
    c.update()
    got = sorted((wn.winfo_rootx(), wn.winfo_rooty(), wn.winfo_width(), wn.winfo_height()) for wn in c.windows)
    c.destroy()
    assert got == sorted(ms), (got, ms)
    print("monitors:", ms)
    # §43 sleep/wake the screens on a small curtain without powering the monitors off; the sound must end where it began
    before = sound()
    display_off(0.4, area=(40, 40, 200, 120), power=False)
    ep = _endpoint()
    was_muted = "(muted)" in before
    assert bool(ep.GetMute()) or was_muted and _asleep  # muted while "asleep"
    display_on(0.4, area=(40, 40, 200, 120), power=False)
    assert sound() == before and not _asleep, (before, sound())
    assert home("on", "lamp", {}).startswith("Not done: smart home is not set up")
    assert serial_send("LED ON", "").startswith("Not done: no serial port set")
    assert cancel_power_off().startswith(("Cancelled", "Not done"))  # nothing scheduled here -> "Not done"
    print("HARDWARE SELFTEST OK")
