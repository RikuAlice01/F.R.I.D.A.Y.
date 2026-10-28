"""Promo and story videos (PLAN §104), made the way the /brag skill makes them (github.com/latent-spaces/brag, MIT):
motion graphics in CSS + JavaScript, every frame a pure function of time, captured in Edge headless, plus a soundtrack
made here (numpy) and FRIDAY's own voice. Owner: ภาพ "สร้างขึ้นด้วย css + javascript" · ffmpeg "ให้ผู้ใช้ติดตั้งเอง" ·
เก็บใน "โปรเจกต์หมวด วิดีโอ" · ยืนยัน "ดู storyboard แล้วกดยืนยันธรรมดา".

Two ways in: a storyboard.json (any brain can write it) played by video_player.html, or a page the brain wrote itself
(video.html with window.T(t)). Pages are served from 127.0.0.1 with only the project's files, and Edge has no way out
to the network — a page written by a model can't load other files of this PC or send anything anywhere."""
import base64, glob, http.server, io, json, os, re, shutil, socket, struct, subprocess, tempfile, threading, time, urllib.parse
import urllib.request, wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080)}
FPS, SR, MAX_S = 30, 48000, 120
TYPES = ("title", "lines", "cards", "stat", "quote", "image", "outro", "bars", "donut", "line", "steps", "icons")
CHARTS = ("bars", "donut", "line")  # §106 infographics drawn from data: [{label, value}]
TONES = ("default", "polished", "cinematic", "chaotic", "deadpan", "app-store", "dark")
MOODS = ("bright", "calm", "epic", "none")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
INSTALL_FFMPEG = "winget install Gyan.FFmpeg"
FLAGS = 0x08000000 | 0x00004000  # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS: the rest of the PC comes first


class Cancelled(Exception):
    pass


def ffmpeg():
    """The owner installs ffmpeg (winget puts it outside PATH until the next sign-in, so look there too)."""
    hits = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\*\bin\ffmpeg.exe"))
    return shutil.which("ffmpeg") or (hits[0] if hits else None)


def edge():
    for p in (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
              r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"):
        if os.path.isfile(p := os.path.expandvars(p)):
            return p
    return None


# ---------- storyboard ----------
def read_seconds(text):
    """Time to read a line (/brag: ~0.3 s a word; Thai has no spaces, ~12 characters a second)."""
    words = len(str(text).split())
    thai = len(re.findall(r"[฀-๿]", str(text)))
    return 1.2 + max(words * 0.3, thai / 12)


def storyboard(data):
    """Check and fill a storyboard (dict or JSON text). ValueError says what to fix, in words the model can act on."""
    try:
        return _storyboard(json.loads(data) if isinstance(data, str) else dict(data))
    except (AttributeError, TypeError, KeyError) as e:  # valid JSON of the wrong shape (a list, "items": 3 …)
        raise ValueError(f"wrong shape ({e}) — it must be an object like {{\"scenes\": [{{\"type\": \"title\", \"text\": \"...\"}}]}}")


def _storyboard(sb):
    scenes = sb.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('storyboard needs "scenes": a list of {type, text, ...}')
    out = []
    for i, s in enumerate(scenes[:30]):
        if not isinstance(s, dict):
            raise ValueError(f"scene {i + 1} must be an object")
        kind = str(s.get("type", "lines")).lower()
        if kind not in TYPES:
            raise ValueError(f"scene {i + 1}: type must be one of {', '.join(TYPES)}")
        items = [str(x)[:80] for x in (s.get("items") or [])][:8]
        text, sub = str(s.get("text", ""))[:160], str(s.get("sub", ""))[:160]
        image = str(s.get("image", "")).replace("\\", "/").strip()
        if kind == "image" and not image:  # small models pick "image" with no picture: show the words instead
            kind = "lines"
        data, unit = chart_data(s, items) if kind in CHARTS + ("steps",) else ([], "")
        unit = str(s.get("unit") or unit)[:12]
        if kind == "donut":
            data = [d for d in data if d["value"] > 0]
        if kind in CHARTS and len(data) < 2 and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*%\s*", text):
            kind = "stat"  # "donut" with just "92%": a gauge
        elif kind in CHARTS and len(data) < 2 or kind == "steps" and len(items or data) < 2 or kind == "icons" and not items:
            kind = "cards" if items else "lines"  # not enough to draw: words instead of an empty chart
        if kind in CHARTS + ("steps", "icons") and not text and not s.get("text"):
            text = " "  # a chart may have no heading
        if not text and kind != "image":  # a missing main line: take the next words there are
            say = str(s.get("say", ""))[:160]
            text, sub = ((sub, "") if sub else (items.pop(0), sub) if items and kind != "cards" else (say, sub) if say
                         else (str(sb.get("title", ""))[:160], sub))
        if not text and kind != "image":
            raise ValueError(f"scene {i + 1} ({kind}) needs text")
        if kind == "image" and (not image or not image.lower().endswith(IMAGE_EXT) or re.search(r'["\'()<>]|^[a-z]+:', image, re.I)):
            raise ValueError(f"scene {i + 1}: image must be a picture file in the project (png/jpg/webp/gif/svg)")
        need = read_seconds(" ".join([text, sub] + items + [d["label"] for d in data])) + (
            0.4 * len(items) if kind in ("cards", "icons") else 0.5 * len(items or data) if kind == "steps" else 2.0 if kind in CHARTS else 0)
        try:
            seconds = float(s.get("seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        out.append({"type": kind, "text": text.strip(), "sub": sub, "items": items, "image": image, "say": str(s.get("say", ""))[:300],
                    "data": data, "unit": unit,
                    "seconds": round(min(12.0, max(seconds, need, 1.5)), 2)})
    out = infographics(out)
    fmt = str(sb.get("format", "landscape")).lower()
    colors = {k: v for k, v in (sb.get("colors") or {}).items() if k in ("bg", "ink", "accent") and re.fullmatch(r"#[0-9a-fA-F]{6}", str(v))}
    res = {"title": str(sb.get("title", "video"))[:80], "format": fmt if fmt in SIZES else "landscape",
           "tone": str(sb.get("tone", "default")).lower(), "mood": str(sb.get("mood", "bright")).lower(),
           "voice": bool(sb.get("voice", any(s["say"] for s in out))), "colors": colors, "scenes": out}
    res["tone"] = res["tone"] if res["tone"] in TONES else "default"
    res["mood"] = res["mood"] if res["mood"] in MOODS else "bright"
    timeline(res)
    if res["seconds"] > MAX_S:
        raise ValueError(f"the video would be {res['seconds']:.0f} s — keep it under {MAX_S} s (fewer or shorter scenes)")
    return res


def _number(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


STAT = re.compile(r"\s*([^\d\s]*)\s*(\d[\d,]*(?:\.\d+)?)\s*(.*?)\s*")


def infographics(scenes):
    """§106 small models tell numbers one "stat" scene at a time: a run of them becomes one chart (the owner's numbers,
    labelled by each scene's sub line). Parts of a whole (% adding up to ~100) -> donut · 3+ with one unit -> bars."""
    out, i = [], 0
    while i < len(scenes):
        j = i
        while j < len(scenes) and scenes[j]["type"] == "stat" and scenes[j]["sub"] and STAT.fullmatch(scenes[j]["text"]):
            j += 1
        run = scenes[i:j]
        if len(run) < 2:
            out.append(scenes[i])
            i += 1
            continue
        nums = [STAT.fullmatch(s["text"]) for s in run]
        vals, units = [_number(m[2]) for m in nums], [m[3].lstrip("+ ").strip() for m in nums]  # "420+ แก้ว" ~ "310 แก้ว"
        k = 0
        while k < len(run):  # inside the run: the first window of % adding up to ~100 -> donut
            win = next((e for e in range(k + 2, len(run) + 1) if all(u == "%" for u in units[k:e]) and 95 <= sum(vals[k:e]) <= 105), None)
            same = k
            while same < len(run) and units[same] == units[k]:
                same += 1
            if win or units[k] != "%" and same - k >= 3:
                end, kind = (win, "donut") if win else (same, "bars")
                part = run[k:end]
                out.append({"type": kind, "text": "", "sub": "", "items": [], "image": "", "say": " ".join(s["say"] for s in part if s["say"]),
                            "data": [{"label": s["sub"][:40], "value": v} for s, v in zip(part, vals[k:end])],
                            "unit": "" if kind == "donut" else (" " + units[k] if units[k] and not units[k].startswith(("%", "+")) else units[k]),
                            "seconds": round(min(12.0, max(4.0, sum(s["seconds"] for s in part) * 0.7)), 2)})
                k = end
            else:
                out.append(run[k])
                k += 1
        i = j
    return out


def chart_data(s, items):
    """§106 [{label, value}] from "data" ({label, value} or [label, value]) or from items like "ลาเต้: 45" / "2024 120%".
    -> (data, unit found in the items)"""
    out, units = [], set()
    for d in s.get("data") or [] if isinstance(s.get("data"), list) else []:
        label, value = (d.get("label"), d.get("value")) if isinstance(d, dict) else d if isinstance(d, (list, tuple)) and len(d) == 2 else (None, None)
        if (v := _number(value)) is not None:
            out.append({"label": str(label or "")[:40], "value": v})
    if not out:
        for it in items:
            m = re.fullmatch(r"\s*(.+?)\s*[:：=]?\s*(-?[\d,]+(?:\.\d+)?)\s*(%|[^\d\s]{1,8})?\s*", it)
            if m and (v := _number(m[2])) is not None:
                out.append({"label": m[1].strip(" :-")[:40], "value": v})
                units.add(m[3] or "")
    return out[:8], (units.pop() if len(units) == 1 else "")


def timeline(sb):
    t = 0.0
    for s in sb["scenes"]:
        s["start"] = round(t, 3)
        t += s["seconds"]
    sb["seconds"] = round(t, 3)


def summary(sb):
    """What the owner sees before saying yes."""
    w, h = SIZES[sb["format"]]
    rows = [f"{sb['title']} · {sb['seconds']:.0f} วิ · {w}×{h} · โทน {sb['tone']} · เพลง {sb['mood']}" + (" · พากย์" if sb["voice"] else "")]
    for i, s in enumerate(sb["scenes"], 1):
        data = ", ".join(f"{d['label']} {d['value']:g}{s['unit']}" for d in s.get("data") or [])
        rows.append(f"{i}. [{s['type']}] {s['text'] or s['image']}" + (f" — {s['sub']}" if s["sub"] else "")
                    + (f" ({', '.join(s['items'])})" if s["items"] else "") + (f" [{data}]" if data else "")
                    + (f" 🔊 {s['say']}" if s["say"] else ""))
    return "\n".join(rows)


def player_html(sb):
    page = open(os.path.join(HERE, "video_player.html"), encoding="utf-8").read()
    scenes = [dict(s, image="/" + urllib.parse.quote(s["image"].lstrip("/")) if s["image"] else "") for s in sb["scenes"]]
    data = json.dumps(dict(sb, scenes=scenes), ensure_ascii=False).replace("<", "\\u003c")  # no </script> from a model
    return page.replace("/*STORYBOARD*/{}", data, 1)


# ---------- sound ----------
CHORDS = {  # mood: (bpm, chords as (root, triad) midi, drums, pluck)
    "bright": (120, [(48, [48, 52, 55]), (55, [55, 59, 62]), (57, [57, 60, 64]), (53, [53, 57, 60])], True, True),  # C G Am F
    "calm": (84, [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [48, 52, 55]), (55, [55, 59, 62])], False, True),   # Am F C G
    "epic": (96, [(50, [50, 53, 57]), (46, [46, 50, 53]), (53, [53, 57, 60]), (48, [48, 52, 55])], True, False),   # Dm Bb F C
}


def _hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def _lp(x, fc):
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (f / fc) ** 4), len(x))


def _env(n, a=0.005, d=0.2, s=0.0, r=0.05):
    t = np.arange(n) / SR
    e = np.where(t < a, t / a, s + (1 - s) * np.exp(-(t - a) / d))
    return e * (1 - np.clip((t - (n / SR - r)) / r, 0, 1))


def _saw(f, n, det=0.004):
    t = np.arange(n) / SR
    return sum(2 * ((f * (1 + d) * t) % 1) - 1 for d in (-det, det)) / 2


def music(seconds, mood="bright", seed=104):
    """A soundtrack on one beat grid from frame 0 (/brag "Sound"): pad, bass, drums, plucks. Stereo float, SR."""
    n = int(SR * seconds)
    L, R = np.zeros(n), np.zeros(n)
    if mood == "none" or n == 0:
        return np.stack([L, R], 1)
    bpm, chords, drums, pluck = CHORDS.get(mood, CHORDS["bright"])
    beat, rng = 60 / bpm, np.random.default_rng(seed)

    def add(sig, t, g, pan=0.0):
        i = int(t * SR)
        if i >= n:
            return
        sig = sig[: n - i] * g
        L[i:i + len(sig)] += sig * (1 - max(pan, 0))
        R[i:i + len(sig)] += sig * (1 + min(pan, 0))

    bar = 4 * beat
    for b in range(int(seconds / bar) + 1):
        root, triad = chords[b % 4]
        m = int((bar + 0.4) * SR)
        add(_lp(sum(_saw(_hz(x + 12), m) for x in triad) / 3, 1200) * _env(m, a=0.3, d=9, s=1, r=0.4), b * bar, 0.11)
        for e in range(8):
            t = b * bar + e * beat / 2
            k = int(0.24 * SR)
            add(_lp(_saw(_hz(root - 24 + (12 if e % 4 == 3 else 0)), k, 0), 450) * _env(k, d=0.18, r=0.03), t, 0.2 if drums else 0.1)
            if pluck and e % 2:
                notes = [triad[0] + 24, triad[1] + 24, triad[2] + 24, triad[1] + 24]
                k = int(0.3 * SR)
                tone = np.sin(2 * np.pi * _hz(notes[(e // 2) % 4]) * np.arange(k) / SR)
                add(tone * _env(k, a=0.002, d=0.12), t, 0.05, pan=-0.3 if e % 4 == 1 else 0.3)
    if drums:
        for k in range(int(seconds / beat)):
            t, m = k * beat, int(0.35 * SR)
            tt = np.arange(m) / SR
            add(np.sin(2 * np.pi * (45 * tt + 2 * (1 - np.exp(-tt * 30)))) * np.exp(-tt * 9), t, 0.5)
            if k % 2:
                c = int(0.18 * SR)
                add(_lp(rng.standard_normal(c), 3500) * _env(c, a=0.002, d=0.05), t, 0.05)
            h = int(0.05 * SR)
            add(_lp(np.diff(rng.standard_normal(h + 1)), 9000) * _env(h, a=0.001, d=0.012), t + beat / 2, 0.014, pan=0.25)
    mix = np.stack([L, R], 1)
    t = np.arange(n) / SR
    mix *= (np.clip(t / 0.05, 0, 1) * np.clip((seconds - t) / 1.2, 0, 1))[:, None]
    mix = np.tanh(mix * 1.2) / 1.2
    return mix * (0.8 / max(np.abs(mix).max(), 1e-9))


def pcm(wav_bytes):
    """WAV bytes -> mono float at SR, silence trimmed so a line starts where it is placed."""
    with wave.open(io.BytesIO(wav_bytes)) as r:
        sr, ch = r.getframerate(), r.getnchannels()
        a = np.frombuffer(r.readframes(r.getnframes()), np.int16).astype(np.float32) / 32768
    if ch == 2:
        a = a.reshape(-1, 2).mean(1)
    a = np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a)
    nz = np.nonzero(np.abs(a) > 0.02)[0]
    return a[nz[0]:nz[-1] + 1] if len(nz) else a


def voice_lines(sb, tts, cancel=None):
    """Synthesize every 'say' and stretch its scene to fit the line (+0.8 s). -> [(start, samples)]"""
    lines = []
    for s in sb["scenes"]:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if s["say"] and sb["voice"]:
            a = pcm(tts(s["say"]))
            s["seconds"] = round(max(s["seconds"], len(a) / SR + 0.8), 2)
            lines.append((s, a))
    timeline(sb)
    return [(s["start"] + 0.3, a) for s, a in lines]


def mixdown(seconds, mood, lines, path):
    """Music ducked 9 dB under the voice (/brag + §90), written as 16-bit stereo WAV."""
    mix = music(seconds, mood)
    voice = np.zeros(len(mix))
    for start, a in lines:
        i = int(start * SR)
        voice[i:i + len(a)] += (a / (np.abs(a).max() + 1e-9) * 0.8)[: max(0, len(voice) - i)]
    if lines:
        on = np.clip(np.convolve((np.abs(voice) > 0.01).astype(np.float32), np.ones(int(0.12 * SR)) / int(0.12 * SR), "same") * 4, 0, 1)
        hold = np.maximum.accumulate(np.where(on > 0.5, np.arange(len(on)), -10 ** 9))
        level = np.clip(1 - (np.arange(len(on)) - hold) / (0.3 * SR), 0, 1)
        mix = mix * (1 - (1 - 10 ** (-9 / 20)) * np.maximum(on, level))[:, None] + voice[:, None] * 0.75
    peak = np.abs(mix).max()
    mix = mix * (0.89 / peak) if peak > 0 else mix
    with wave.open(path, "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())


# ---------- the page server: the project's files only ----------
def serve(inside, player=None):
    """http://127.0.0.1:<port>/ -> files through `inside(rel)` (raises outside the project) · /__friday/ -> the player and
    its fonts. Returns the server; .server_address[1] is the port."""
    fonts = os.path.join(HERE, "fonts")

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            try:
                if path == "/__friday/player.html" and player is not None:
                    body, kind = player.encode("utf-8"), "text/html; charset=utf-8"
                else:
                    if path.startswith("/__friday/fonts/") and re.fullmatch(r"[\w.-]+\.ttf", name := path.rsplit("/", 1)[1]):
                        full = os.path.join(fonts, name)
                    else:
                        full = inside(path.lstrip("/"))
                    if not os.path.isfile(full):
                        raise FileNotFoundError(path)
                    body = open(full, "rb").read()
                    kind = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
                            ".json": "application/json", ".ttf": "font/ttf", ".woff2": "font/woff2", ".png": "image/png",
                            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
                            ".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------- Edge over the DevTools protocol (a small websocket client, stdlib only) ----------
class CDP:
    def __init__(self, url, timeout=60):
        u = urllib.parse.urlsplit(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("DevTools closed the connection")
            head += chunk
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head.split(b"\r\n")[0].decode(errors="replace"))
        self.buf, self.id = head.split(b"\r\n\r\n", 1)[1], 0

    def _exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("DevTools closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, op, data):
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                     else bytes([0x80 | 127]) + struct.pack(">Q", n))
        body = (np.frombuffer(data, np.uint8) ^ np.resize(np.frombuffer(mask, np.uint8), n)).tobytes()
        self.sock.sendall(head + mask + body)

    def _message(self):
        parts = []
        while True:
            b1, b2 = self._exact(2)
            n = b2 & 0x7F
            n = struct.unpack(">H", self._exact(2))[0] if n == 126 else struct.unpack(">Q", self._exact(8))[0] if n == 127 else n
            data = self._exact(n)
            op = b1 & 0x0F
            if op == 8:
                raise ConnectionError("DevTools closed the connection")
            if op == 9:
                self._frame(10, data)
                continue
            if op in (0, 1, 2):
                parts.append(data)
                if b1 & 0x80:
                    return json.loads(b"".join(parts))

    def call(self, method, **params):
        self.id += 1
        self._frame(1, json.dumps({"id": self.id, "method": method, "params": params}).encode())
        while True:
            m = self._message()
            if m.get("id") == self.id:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error'].get('message')}")
                return m.get("result", {})

    def js(self, expression):
        r = self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError("page error: " + str((d.get("exception") or {}).get("description") or d.get("text"))[:300])
        return (r.get("result") or {}).get("value")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _start_edge(w, h, prof, port):
    exe = edge()
    if not exe:
        raise RuntimeError("Microsoft Edge was not found")
    # no way out: every host but 127.0.0.1 fails to resolve, and everything — 127.0.0.1 too (Ollama, FRIDAY's own
    # servers) — goes to a dead proxy, except the page server's own port (review §104)
    p = subprocess.Popen([exe, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={prof}", f"--window-size={w},{h}",
                          "--hide-scrollbars", "--mute-audio", "--no-first-run", "--no-default-browser-check", "--disable-gpu",
                          "--disable-extensions", "--disable-sync", "--disable-background-networking", "--disable-component-update",
                          "--disable-features=Translate,OptimizationHints,MediaRouter,AutofillServerCommunication",
                          "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1", "--proxy-server=http://127.0.0.1:9",
                          f"--proxy-bypass-list=<-loopback>;127.0.0.1:{port}",
                          "about:blank"], creationflags=FLAGS, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_file = os.path.join(prof, "DevToolsActivePort")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(150):
        time.sleep(0.2)
        if p.poll() is not None:
            raise RuntimeError("Edge closed right after starting")
        try:
            port = open(port_file).read().split()[0]
            pages = json.load(opener.open(f"http://127.0.0.1:{port}/json/list", timeout=2))
            ws = next(t["webSocketDebuggerUrl"] for t in pages if t.get("type") == "page")
            return p, CDP(ws)
        except (OSError, ValueError, StopIteration, IndexError):
            continue
    _kill(p)
    raise RuntimeError("Edge did not start in 30 s")


def _kill(p):
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=0x08000000)


def open_page(url, w, h, prof):
    p, cdp = _start_edge(w, h, prof, urllib.parse.urlsplit(url).port)
    try:
        cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=url)
        for _ in range(150):
            try:
                if cdp.js("document.readyState === 'complete' && typeof window.T === 'function'"):
                    break
            except RuntimeError:  # review: the old about:blank context going away mid-navigation
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("the page has no window.T(t) — every frame must come from window.T(seconds)")
        cdp.js("Promise.all([document.fonts.ready, window.READY]).then(() => 1)")
        return p, cdp
    except Exception:
        cdp.close()
        _kill(p)
        raise


def frames(cdp, seconds, w, h, out_dir, progress=None, cancel=None, fps=FPS):
    total = max(1, int(round(seconds * fps)))
    for i in range(total):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        cdp.js(f"Promise.resolve(window.T({i / fps:.4f})).then(() => 1)")
        shot = cdp.call("Page.captureScreenshot", format="jpeg", quality=92, clip={"x": 0, "y": 0, "width": w, "height": h, "scale": 1})
        with open(os.path.join(out_dir, f"{i:06d}.jpg"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        if progress and i % fps == 0:
            progress(i / total, f"เฟรม {i}/{total}")
    return total


def encode(frame_dir, wav, out, fps=FPS, cancel=None):
    ff = ffmpeg()
    if not ff:
        raise RuntimeError(f"ffmpeg is not installed — install it with: {INSTALL_FFMPEG}")
    part = out + ".part.mp4"
    cmd = [ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(frame_dir, "%06d.jpg")]
    cmd += ["-i", wav] if wav else []
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"] if wav else []
    log = os.path.join(frame_dir, "ffmpeg.log")
    with open(log, "w") as err:
        p = subprocess.Popen(cmd + [part], stdout=subprocess.DEVNULL, stderr=err, creationflags=FLAGS)
        while p.poll() is None:  # "หยุดทำวิดีโอ" works while encoding too
            if cancel is not None and cancel.is_set():
                _kill(p)
                p.wait()
                if os.path.exists(part):
                    os.remove(part)
                raise Cancelled()
            time.sleep(0.3)
    if p.returncode or not os.path.isfile(part):
        raise RuntimeError("ffmpeg failed: " + open(log, errors="replace").read()[-300:])
    os.replace(part, out)


def make(source, inside, out, tts=None, seconds=None, fmt=None, mood="bright", progress=None, cancel=None, size=None):
    """Render a video. source = storyboard dict (played by video_player.html) or the project path of a page with
    window.T(t) (then `seconds` is needed). inside = the project's fence. -> (out, seconds)"""
    progress = progress or (lambda f, m: None)
    if not ffmpeg():
        raise RuntimeError(f"ffmpeg is not installed — install it with: {INSTALL_FFMPEG}")
    work = tempfile.mkdtemp(prefix="friday-video-")
    srv = p = cdp = None
    try:
        if isinstance(source, dict):
            sb = source
            lines = voice_lines(sb, tts, cancel) if sb["voice"] and tts else []
            if sb["seconds"] > MAX_S:  # review: the voice stretched the scenes past the limit
                raise ValueError(f"with the voice-over the video would be {sb['seconds']:.0f} s (limit {MAX_S} s) — shorter 'say' lines")
            seconds, fmt, mood, player = sb["seconds"], sb["format"], sb["mood"], player_html(sb)
            path = "__friday/player.html"
        else:
            lines, player, path = [], None, str(source).replace("\\", "/").lstrip("/")
            inside(path)
            if not seconds or not 1 <= float(seconds) <= MAX_S:
                raise ValueError(f"say how long the page runs: seconds between 1 and {MAX_S}")
            seconds = float(seconds)
        w, h = size or SIZES.get(fmt or "landscape", SIZES["landscape"])
        progress(0.02, "เสียง")
        wav = os.path.join(work, "audio.wav")
        mixdown(seconds, mood, lines, wav)
        srv = serve(inside, player)
        os.makedirs(prof := os.path.join(work, "edge"))
        os.makedirs(fdir := os.path.join(work, "frames"))
        p, cdp = open_page(f"http://127.0.0.1:{srv.server_address[1]}/{urllib.parse.quote(path)}", w, h, prof)
        frames(cdp, seconds, w, h, fdir, lambda f, m: progress(0.05 + 0.85 * f, m), cancel)
        cdp.close()
        _kill(p)
        p = cdp = None
        progress(0.92, "รวมเป็น mp4")
        encode(fdir, wav, out, cancel=cancel)
        return out, seconds
    finally:
        if cdp:
            cdp.close()
        _kill(p)
        if srv:
            srv.shutdown()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sb = storyboard({"title": "ทดสอบ", "tone": "dark", "scenes": [{"type": "title", "text": "สวัสดี", "sub": "FRIDAY"},
                                                                   {"type": "stat", "text": "1,200+", "sub": "users"}]})
    assert sb["scenes"][0]["start"] == 0 and sb["seconds"] > 3 and sb["format"] == "landscape" and not sb["voice"]
    page = player_html(storyboard({"scenes": [{"type": "title", "text": "</script><script>x()"}]}))
    assert page.count("</script>") == 1 and "\\u003c/script>" in page  # a model's text can't end the script
    for bad in ({"scenes": []}, {"scenes": [{"type": "boom", "text": "x"}]}, {"scenes": [{"type": "image", "image": "a.exe"}]}, {"scenes": [{"type": "lines"}]}, [1, 2], {"scenes": [{"type": "cards", "text": "x", "items": 3}]}, {"scenes": "x"},
                {"scenes": [{"type": "image", "image": 'x".png'}]}, {"scenes": [{"type": "image", "image": "file:///c:/x.png"}]},
                {"scenes": [{"type": "lines", "text": "x", "seconds": 12}] * 11}):
        try:
            storyboard(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    assert storyboard({"scenes": [{"type": "lines", "text": "x", "seconds": 99}]})["seconds"] == 12
    fixed = storyboard({"title": "ร้าน", "scenes": [{"type": "image", "text": "ไม่มีรูป"}, {"type": "outro", "sub": "เปิดทุกวัน"}, {"type": "outro"},
                                                    {"type": "image", "say": "แมวเดินกลับบ้าน"}]})["scenes"]
    info = storyboard({"title": "ร้าน", "scenes": [
        {"type": "bars", "text": "ยอดขาย", "items": ["ลาเต้: 45%", "มอคค่า 30%", "อเมริกาโน่ 25%"]},
        {"type": "donut", "data": [{"label": "ไทย", "value": 60}, ["ต่างชาติ", "40"], {"label": "x", "value": "abc"}]},
        {"type": "line", "data": [{"label": "ม.ค.", "value": 1}]},  # one point can't be a line
        {"type": "steps", "items": ["2024: เปิดร้าน", "2025: สาขา 2"]}, {"type": "icons", "items": ["☕ คั่วเอง", "📶 Wi-Fi"]},
        {"type": "donut", "items": ["ไม่มีตัวเลข"]}]})["scenes"]
    assert info[0]["data"][1] == {"label": "มอคค่า", "value": 30} and info[0]["unit"] == "%" and info[0]["text"] == "ยอดขาย"
    assert [d["label"] for d in info[1]["data"]] == ["ไทย", "ต่างชาติ"] and info[1]["text"] == ""
    assert info[2]["type"] == "lines" and info[3]["type"] == "steps" and info[4]["type"] == "icons" and info[5]["type"] == "cards"
    assert "[ลาเต้ 45%, มอคค่า 30%, อเมริกาโน่ 25%]" in summary({"title": "x", "seconds": 9, "format": "square", "tone": "dark",
                                                                   "mood": "calm", "voice": False, "scenes": info})
    auto = storyboard({"title": "ร้าน", "scenes": [{"type": "stat", "text": "420+ แก้ว", "sub": "ลาเต้"}, {"type": "stat", "text": "310 แก้ว", "sub": "มอคค่า"},
                                                  {"type": "stat", "text": "250 แก้ว", "sub": "โกโก้"}, {"type": "donut", "text": "92%", "sub": "กลับมาซ้ำ"},
                                                  {"type": "stat", "text": "55%", "sub": "คนในพื้นที่"}, {"type": "stat", "text": "45%", "sub": "นักท่องเที่ยว"},
                                                  {"type": "stat", "text": "1,200+", "sub": "ผู้ติดตาม"}]})["scenes"]
    assert [s["type"] for s in auto] == ["bars", "stat", "donut", "stat"], [s["type"] for s in auto]
    assert auto[0]["data"][0] == {"label": "ลาเต้", "value": 420} and auto[0]["unit"] == " แก้ว" and auto[2]["data"][1]["value"] == 45
    assert fixed[0]["type"] == "lines" and fixed[1]["text"] == "เปิดทุกวัน" and fixed[2]["text"] == "ร้าน" and fixed[3]["text"] == "แมวเดินกลับบ้าน"  # a scene stays ≤ 12 s
    m = music(2.0, "bright")
    assert m.shape == (2 * SR, 2) and 0.5 < np.abs(m).max() <= 0.81 and not np.abs(music(1.0, "none")).any()
    assert "1. [title] สวัสดี — FRIDAY" in summary(sb)

    tmp = tempfile.mkdtemp()
    root = os.path.realpath(tmp)
    open(os.path.join(tmp, "page.html"), "w", encoding="utf-8").write(
        "<body style='margin:0'><div id=b style='width:100%;height:100vh'></div><script>"
        "window.T = t => { b.style.background = t < .5 ? '#ff0000' : '#0000ff' };</script>")

    def fence(rel):
        full = os.path.realpath(os.path.join(root, rel))
        if not full.startswith(root + os.sep):
            raise ValueError("outside")
        return full

    srv = serve(fence)
    port = srv.server_address[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    assert b"window.T" in opener.open(f"http://127.0.0.1:{port}/page.html").read()
    for bad in ("/../video.py", "/%2e%2e/video.py", "/__friday/fonts/../video.py"):
        try:
            opener.open(f"http://127.0.0.1:{port}{bad}")
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 404
    srv.shutdown()

    if edge() and ffmpeg():
        work = tempfile.mkdtemp()
        srv = serve(fence)
        p, cdp = open_page(f"http://127.0.0.1:{srv.server_address[1]}/page.html", 320, 180, os.path.join(work, "edge"))
        try:  # a page can't reach the network or this PC's other files
            got = cdp.js("Promise.all([fetch('http://example.com').then(() => 'open', () => 'blocked'),"
                         "fetch('http://127.0.0.1:11434/api/tags').then(() => 'open', () => 'blocked'),"
                         "new Promise(r => { const i = new Image(); i.onload = () => r('open'); i.onerror = () => r('blocked');"
                         "i.src = 'file:///C:/Windows/win.ini' })])")
            assert got == ["blocked", "blocked", "blocked"], got  # the internet · Ollama on 127.0.0.1 · other files
        finally:
            cdp.close()
            _kill(p)
            srv.shutdown()
        out = os.path.join(tmp, "out.mp4")
        make("page.html", fence, out, seconds=1, mood="calm", size=(320, 180))
        assert os.path.getsize(out) > 1000
        out2 = os.path.join(tmp, "sb.mp4")
        make(storyboard({"format": "vertical", "scenes": [{"type": "cards", "text": "เมนู", "items": ["ลาเต้", "มอคค่า"], "seconds": 2}]}),
             fence, out2, size=(180, 320))
        assert os.path.getsize(out2) > 1000
        print("VIDEO SELFTEST OK (rendered 2 videos)")
    else:
        print("VIDEO SELFTEST OK (no Edge/ffmpeg: render not tested)")
    shutil.rmtree(tmp, ignore_errors=True)
