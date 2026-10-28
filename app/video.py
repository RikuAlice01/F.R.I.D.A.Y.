"""Promo and story videos (PLAN §104), made the way the /brag skill makes them (github.com/latent-spaces/brag, MIT):
motion graphics in CSS + JavaScript, every frame a pure function of time, captured in Edge headless, plus a soundtrack
made here (numpy) and FRIDAY's own voice. Owner: ภาพ "สร้างขึ้นด้วย css + javascript" · ffmpeg "ให้ผู้ใช้ติดตั้งเอง" ·
เก็บใน "โปรเจกต์หมวด วิดีโอ" · ยืนยัน "ดู storyboard แล้วกดยืนยันธรรมดา".

Two ways in: a storyboard.json (any brain can write it) played by video_player.html, or a page the brain wrote itself
(video.html with window.T(t)). Pages are served from 127.0.0.1 with only the project's files, and Edge has no way out
to the network — a page written by a model can't load other files of this PC or send anything anywhere."""
import base64, collections, difflib, glob, http.server, io, json, os, re, shutil, socket, struct, subprocess, tempfile, threading, time, urllib.parse
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
    if sb.get("story"):  # §107 a script: one line per shot
        return "\n".join(rows + [f"{i}. [{s.get('place', '')}{' กลางคืน' if s.get('time') == 'night' else ''}] "
                                  + (f"{s['speaker']}: " if s.get("speaker") else "") + _plain(s["text"]) for i, s in enumerate(sb["scenes"], 1)])
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



# ---------- §107 story scripts (script.md) -> shots, in the style the owner sent: a 2D cartoon with captions ----------
STORY_MAX_S, STORY_SHOTS = 600, 250  # owner: "ถึง 10 นาที"
PLACES = {"classroom": r"ห้องเรียน|โรงเรียน|classroom|school", "corridor": r"ทางเดิน|โถง|ระเบียง|corridor|hall",
          "bathroom": r"ห้องน้ำ|ห้องส้วม|bathroom|toilet", "bedroom": r"ห้องนอน|หอพัก|bedroom|dorm",
          "cafe": r"ร้านกาแฟ|คาเฟ่|ร้าน|cafe|café|shop", "street": r"ถนน|ซอย|ข้างนอก|นอกบ้าน|ตลาด|street|road|outside",
          "office": r"ออฟฟิศ|ที่ทำงาน|ห้องทำงาน|บริษัท|office", "livingroom": r"ห้องนั่งเล่น|บ้าน|living|home"}
NIGHT = r"กลางคืน|ตอนดึก|ดึก|คืน|มืด|night|dark|midnight"
POSES = {"lie": r"นอน|lie|lying|in bed", "sit": r"นั่ง|sit", "walk": r"เดิน|walk", "flashlight": r"ไฟฉาย|ส่องไฟ|flashlight|torch",
         "phone": r"โทรศัพท์|มือถือ|phone", "point": r"ชี้|point", "stand": r"ยืน|stand"}
FACES = {"sleep": r"หลับ|sleep", "shock": r"ตกใจ|อึ้ง|ช็อก|shock|surprised", "scared": r"กลัว|หวาด|ขนลุก|scared|afraid",
         "smile": r"ยิ้ม|ดีใจ|หัวเราะ|happy|smile|laugh", "smirk": r"เจ้าเล่ห์|แสยะ|กวน|smirk|sly", "angry": r"โกรธ|โมโห|angry|mad",
         "sad": r"เศร้า|ร้องไห้|เสียใจ|sad|cry", "normal": r"ปกติ|เฉย|normal"}
SKINS = [(r"ขาวมาก|ซีด|pale", "#f3cfae"), (r"สองสี|น้ำผึ้ง|tan", "#d9a273"), (r"คล้ำ|ดำ|dark", "#b9814f"), (r"เข้ม|brown", "#8d5a35"),
         (r"ขาว|fair|light", "#ebc39a")]
COLORS = [(r"ขาว|white", "#eef0f3"), (r"ดำ|black", "#2b2d33"), (r"เทา|grey|gray", "#9aa0a8"), (r"กรม|navy", "#2f4170"),
          (r"น้ำเงิน|blue", "#3f6fc0"), (r"ฟ้า|sky|light blue", "#7fb0e0"), (r"แดง|red", "#d4463f"), (r"ชมพู|pink", "#f29bb8"),
          (r"ส้ม|orange", "#f08a3c"), (r"เหลือง|yellow", "#f2c94c"), (r"เขียว|green", "#5f9e6e"), (r"ม่วง|purple", "#8a6cc4"),
          (r"น้ำตาล|brown", "#8a5a36"), (r"ครีม|cream|beige", "#e8dcc2")]
HAIR_COLORS = [(r"ทอง|blond", "#d9b25a"), (r"น้ำตาล|brown", "#6b4429"), (r"เทา|ขาว|หงอก|grey|gray|white", "#c9c9c9"), (r"แดง|red", "#9c3b2a")]
DEFAULT_TOPS = ["#eef0f3", "#7fb0e0", "#f29bb8", "#5f9e6e", "#f2c94c", "#8a6cc4"]
NARRATOR = r"บรรยาย|ผู้บรรยาย|เล่า|narrator|narration"


def _pick(pairs, text, default=None):
    return next((v for rx, v in pairs if re.search(rx, text, re.I)), default)


def look(desc, i):
    """'หญิง ผมยาวสีน้ำตาล ผิวขาว เสื้อนักเรียน แว่น' -> the drawing's fixed options (no free text reaches the page)."""
    d = str(desc)
    female = bool(re.search(r"หญิง|ผู้หญิง|สาว|ยาย|แม่|girl|woman|female|she", d, re.I))
    old = bool(re.search(r"แก่|คนแก่|ยาย|ตา\b|ปู่|ย่า|old|grand", d, re.I))
    hair = ("bald" if re.search(r"โล้น|ล้าน|bald", d, re.I) else "ponytail" if re.search(r"หางม้า|ponytail", d, re.I)
            else "curly" if re.search(r"หยิก|ฟู|curly", d, re.I) else "long" if re.search(r"ผมยาว|long hair", d, re.I)
            else "short" if re.search(r"ผมสั้น|short hair", d, re.I) else "long" if female else "short")
    hm = re.search(r"ผม\S*?สี?(\S+)|(\S+)\s*hair", d, re.I)
    hair_color = _pick(HAIR_COLORS, hm.group(0) if hm else "", "#c9c9c9" if old else "#1d1a1a")
    sm = re.search(r"ผิว\s*(\S+)|(\S+)\s*skin", d, re.I)
    skin = _pick(SKINS, sm.group(0) if sm else "", ["#e3b088", "#c98f5f"][i % 2])
    top = ("hoodie" if re.search(r"ฮู้ด|hood", d, re.I) else "suit" if re.search(r"สูท|suit|เชิ้ต|shirt", d, re.I)
           else "dress" if re.search(r"เดรส|กระโปรง|dress|skirt", d, re.I) else "tee" if re.search(r"เสื้อยืด|t-?shirt|tee", d, re.I)
           else "student" if d.strip() else ("student", "hoodie", "tee")[i % 3])  # no description: not everyone in white
    tm = re.search(r"(?:เสื้อ|ฮู้ด|สูท|เดรส|ชุด|hoodie|shirt|suit|dress)\S*\s*(?:สี)?\s*\S*", d, re.I)
    color = _pick(COLORS, tm.group(0) if tm else "", "#eef0f3" if top == "student" else DEFAULT_TOPS[i % len(DEFAULT_TOPS)])
    if top == "suit" and not tm:
        color = "#2b2d33"
    return {"gender": "f" if female else "m", "hair": hair, "hairColor": hair_color, "skin": skin, "top": top, "color": color,
            "glasses": bool(re.search(r"แว่น|glasses", d, re.I)), "age": "old" if old else ""}


def _plain(text):
    return re.sub(r"\*+", "", text).strip()


def _chunks(text, n=90):
    """A long narration line -> caption-sized pieces, split at spaces (Thai: the writer's own spaces); a long run with
    no spaces is cut between Thai words (review §107: one 350-character sentence became one cut-off caption)."""
    out, cur = [], ""
    words = re.split(r"(\s+)", text)
    if any(len(w) > n for w in words):
        try:
            from pythainlp.tokenize import word_tokenize
            words = [t for w in words for t in (word_tokenize(w, engine="newmm") if len(w) > n else [w])]
        except Exception:  # no word list: cut by length
            words = [w[i:i + n] for w in words for i in range(0, max(1, len(w)), n)]
    for w in words:
        if len(cur) + len(w) > n and cur.strip():
            out.append(cur.strip())
            cur = ""
        cur += w
    return out + ([cur.strip()] if cur.strip() else [])


def story_text(sb, limit=6000):
    """§108 the story as plain lines, for the editor that reads it (no markup, one line per shot)."""
    out, where = [], None
    for i, s in enumerate(sb["scenes"], 1):
        if s["type"] != "shot":
            continue
        here = f"## {s['place']}{' (night)' if s['time'] == 'night' else ''}"
        if here != where:
            out.append(here)
            where = here
        out.append(f"{i}. {s['speaker'] or 'บรรยาย'}: {_plain(s['text'])}")  # numbered: the editor names shots
    text = "\n".join(out)
    return text if len(text) <= limit else text[:limit // 2] + "\n…\n" + text[-limit // 2:]


def story_lint(sb):
    """§108 owner: "เนื้อเรื่อง … ดูวนเวียน" — what code can see for sure: the same line twice, one phrase coming back
    again and again. -> problems in Thai (empty = none found)."""
    shots = [(i, s["speaker"] or "บรรยาย", _plain(s["text"])) for i, s in enumerate(sb["scenes"], 1) if s["type"] == "shot"]
    norm = lambda t: re.sub(r"[\s.…!?\"'“”,~\-]+", "", t)
    problems, seen = [], []
    for i, who, t in shots:
        k = norm(t)
        if len(k) < 6:
            continue
        if j := next((j for j, k2 in seen if difflib.SequenceMatcher(None, k, k2).ratio() >= .8), None):
            problems.append(f"ช็อต {i} ซ้ำกับช็อต {j}: “{t[:40]}”")
        seen.append((i, k))
    grams = collections.Counter()
    for _, _, t in shots:  # a phrase (10 letters) in 3+ different lines: the story keeps coming back to it
        k = norm(t)
        grams.update({k[a:a + 10] for a in range(max(0, len(k) - 9))})
    said = []
    for g, n in grams.most_common(20):
        if n < 4 or len(said) >= 2:  # 3 is normal in a story about one thing ('ลืมส่งงาน')
            break
        if not any(g[:6] in x or x[:6] in g for x in said):
            said.append(g)
            problems.append(f"วลี “{g}…” วนกลับมา {n} ครั้ง")
    return problems[:6]



def script(text):
    """script.md -> a storyboard of shots. The format (any brain can write it, part by part):
        # ชื่อเรื่อง
        ตัวละคร: ต้น = ชาย ผมสั้น เสื้อขาว · แบงค์ = ชาย ผิวคล้ำ ฮู้ดฟ้า
        ซับ: เน้นคำ | ธรรมดา | ไม่มี
        ## ห้องเรียน กลางคืน [23:40]
        (ต้น นอน กลัว · แบงค์ นอน หลับ · ผี · กล้อง ใกล้)
        บรรยาย: คืนที่โรงเรียน *จัดเข้าค่าย*
        ต้น [กลัว]: ไอ้แบงค์ **มึงหลับยังวะ**"""
    title, cast, order, shots = "", {}, [], []
    captions, fmt = "story", "vertical"
    place, night, badge, present, ghost, camera = "classroom", False, "", [], False, None
    state = {}  # name -> {pose, face}

    def member(name):
        name = name.strip()[:20]
        if name not in cast:
            cast[name] = {"look": look("", len(order)), "index": len(order)}
            order.append(name)
        if name not in present:
            present.append(name)
        state.setdefault(name, {"pose": "stand", "face": "normal"})
        return name

    def add(speaker, words, face=None):
        nonlocal camera
        for piece in _chunks(words):
            k = len(present)
            shots.append({"type": "shot", "place": place, "time": "night" if night else "day", "badge": badge, "ghost": ghost,
                          "speaker": speaker or "", "text": piece[:200], "say": _plain(piece)[:300],
                          "camera": camera or ("close" if speaker else "wide" if len(shots) % 3 else "pan"),
                          "cast": [dict(name=n, look=cast[n]["look"], index=cast[n]["index"], pose=state[n]["pose"],
                                        face=face if (n == speaker and face) else state[n]["face"],
                                        x=round(.5 if k == 1 else .2 + .6 * i / max(1, k - 1), 3)) for i, n in enumerate(present)]})
        camera = None

    def define(item):
        if mm := re.match(r"\s*([^=(（:：]{1,20}?)\s*(?:=|[(（]|[:：])\s*(.+?)[)）]?\s*$", item):
            name = mm[1].strip()
            if name not in cast:
                order.append(name)
            cast[name] = {"look": look(mm[2], order.index(name)), "index": order.index(name)}

    in_cast = False  # a "## ตัวละคร" heading with "- name: looks" lines under it (how small models write it)
    for raw in str(text).splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", raw).strip()  # list bullets
        if not line or line.startswith(("<!--", "![", "```", "---")):  # comments, pictures, fences: not story lines
            continue
        if m := re.match(r"#\s+(.+)", line):
            title = re.sub(r"\s*\[[^\]]*\]", "", m[1]).strip()[:80]
            badge = (re.search(r"\[(\d{1,2}[:.]\d{2})\]", m[1]) or [None, badge])[1]
        elif re.fullmatch(r"#{2,}\s*(?:ตัวละคร|cast|characters)\s*[:：]?", line, re.I):
            in_cast = True
        elif m := re.match(r"(?:ตัวละคร|cast|characters)\s*[:：]\s*(.*)", line, re.I):
            for item in re.split(r"[·•;|]|,(?=[^,]*=)", m[1]):
                define(item)
            in_cast = not m[1].strip()
        elif in_cast and not line.startswith("#") and re.search(r"[=:：(（]", line):
            define(line)
        elif m := re.match(r"(?:ซับ|caption|captions|subtitles?)\s*[:：]\s*(.+)", line, re.I):
            captions = ("none" if re.search(r"ไม่มี|ปิด|none|off", m[1], re.I) else "simple" if re.search(r"ธรรมดา|simple|plain", m[1], re.I)
                        else "story")
        elif m := re.match(r"(?:ขนาด|format)\s*[:：]\s*(.+)", line, re.I):
            fmt = ("landscape" if re.search(r"แนวนอน|landscape|16:9|youtube", m[1], re.I) else "square" if re.search(r"สี่เหลี่ยม|square|1:1", m[1], re.I)
                   else "vertical")
        elif m := re.match(r"##\s*(.+)", line):
            in_cast, head = False, m[1]
            place = next((k for k, rx in PLACES.items() if re.search(rx, head, re.I)), place)
            night = bool(re.search(NIGHT, head, re.I)) and not re.search(r"กลางวัน|เช้า|day|morning", head, re.I)
            badge = (re.search(r"\[(\d{1,2}[:.]\d{2})\]", head) or [None, ""])[1]
            present, ghost = [], False
        elif re.fullmatch(r"\[(\d{1,2}[:.]\d{2})\]", line):
            badge = line[1:-1]
        elif m := re.fullmatch(r"[(（](.+)[)）]", line):
            for tok in re.split(r"[·•,，、/]", m[1]):
                tok = tok.strip()
                if not any(tok.startswith(n) for n in order) and (pl := next((k for k, rx in PLACES.items() if re.search(rx, tok, re.I)), None)):
                    place = pl  # "(ห้องน้ำ, กลางคืน)": a place given as a direction
                if re.search(NIGHT, tok, re.I) and not any(tok.startswith(n) for n in order):
                    night = True
                elif re.search(r"กลางวัน|ตอนเช้า|morning|daytime", tok, re.I) and not any(tok.startswith(n) for n in order):
                    night = False
                elif re.search(r"ผี|วิญญาณ|เงาดำ|เงาสูง|ghost|shadow", tok, re.I):
                    ghost = not re.search(r"หาย|ไป|gone|away", tok, re.I)
                elif re.search(r"กล้อง|camera", tok, re.I):
                    camera = "close" if re.search(r"ใกล้|close", tok, re.I) else "pan" if re.search(r"แพน|pan", tok, re.I) else "wide"
                elif mm := re.match(r"(ทุกคน|everyone|all)\s*(.*)", tok, re.I):
                    for n in present:
                        state[n]["pose"] = next((k for k, rx in POSES.items() if re.search(rx, mm[2], re.I)), state[n]["pose"])
                        state[n]["face"] = next((k for k, rx in FACES.items() if re.search(rx, mm[2], re.I)), state[n]["face"])
                elif re.search(r"ออก|หายไป|leaves?|exit", tok, re.I) and (n := next((n for n in present if tok.startswith(n)), None)):
                    present.remove(n)
                elif n := next((n for n in sorted(set(order) | set(present), key=len, reverse=True) if tok.startswith(n)), None) or (
                        (w := tok.split(maxsplit=1)) and len(w) == 2 and len(w[0]) <= 20 and any(re.search(rx, w[1], re.I) for rx in [*POSES.values(), *FACES.values()])
                        and not any(re.search(rx, w[0], re.I) for rx in [*POSES.values(), *FACES.values()]) and w[0]):  # "(ไฟฉาย ชี้)" is no one
                    # a name the cast line didn't list ("(ต้น นั่งกลัว)"): the first word, when the rest is a pose or face
                    member(n)
                    rest = tok[len(n):]
                    state[n]["pose"] = next((k for k, rx in POSES.items() if re.search(rx, rest, re.I)), state[n]["pose"])
                    state[n]["face"] = next((k for k, rx in FACES.items() if re.search(rx, rest, re.I)), state[n]["face"])
        elif (m := re.match(r"([^:：\[\(（]{1,20}?)\s*(?:[\[(（]([^\])）]{1,20})[\])）])?\s*[:：]\s*(.+)", line)) and (
                m[1].strip() in cast or re.fullmatch(NARRATOR, m[1].strip(), re.I) or re.fullmatch(r"[^\d\s*#]{1,12}", m[1].strip())
                and not re.fullmatch(r"หมายเหตุ|เวลา|สถานที่|ฉาก|ตอน(?:ที่)?|note|time|scene|place|https?", m[1].strip(), re.I)):
            if re.fullmatch(NARRATOR, m[1].strip(), re.I):
                add("", m[3])
            else:
                name = member(m[1])
                if pose := next((k for k, rx in POSES.items() if re.search(rx, m[2] or "", re.I)), None):
                    state[name]["pose"] = pose  # "บอส [เดินเข้ามา]: …"
                add(name, re.sub(r'^\s*["“”]+|["“”]+\s*$', "", m[3]), next((k for k, rx in FACES.items() if re.search(rx, m[2] or "", re.I)), None))
        else:
            add("", line)
        if len(shots) > STORY_SHOTS:
            raise ValueError(f"the script is longer than {STORY_SHOTS} shots — split it into episodes (script-ep1.md, script-ep2.md …)")
    if not shots:
        raise ValueError("the script has no lines to show — write 'บรรยาย: …' or 'ชื่อ: …' lines under a '## place' heading")
    for a, b in zip(shots, shots[1:]):
        a["cut"] = a["place"] == b["place"] and a["time"] == b["time"]  # same place: a hard cut, no dip
    if title:
        shots.append({"type": "endcard", "text": title, "sub": "", "say": "", "seconds": 3.5})
    for sh in shots:
        sh.setdefault("seconds", round(min(20.0, max(1.8, read_seconds(_plain(sh["text"])))), 2))
        sh.update(talk0=0.3, talk1=sh["seconds"] - 0.3)
        sh.setdefault("items", []); sh.setdefault("image", ""); sh.setdefault("sub", "")
    voices, count = {}, {"f": 0, "m": 0}
    for n in order:  # each character their own voice (VaniraTTS: 2 5 female, 3 4 6 male); the narrator is FRIDAY
        g = cast[n]["look"]["gender"]
        voices[n] = str((["2", "5"] if g == "f" else ["3", "4", "6"])[count[g] % (2 if g == "f" else 3)])
        count[g] += 1
    for sh in shots:
        sh["voice"] = voices.get(sh.get("speaker") or "", None)
    sb = {"title": title or "story", "format": fmt, "tone": "dark", "mood": "calm", "voice": True, "colors": {}, "story": True,
          "captions": captions, "scenes": shots, "max_s": STORY_MAX_S}
    timeline(sb)
    if sb["seconds"] > STORY_MAX_S:  # review: before any voice is made, not after
        raise ValueError(f"the story would run about {sb['seconds'] / 60:.0f} min — the limit is {STORY_MAX_S // 60} min; split it into episodes")
    return sb


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
    if not len(a):  # a line with nothing to say ("…", an emoji): silence, not a crash (§108 run: "array of sample points is empty")
        return np.zeros(0, np.float32)
    a = np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a)
    nz = np.nonzero(np.abs(a) > 0.02)[0]
    return a[nz[0]:nz[-1] + 1] if len(nz) else a


def voice_lines(sb, tts, cancel=None):
    """Synthesize every 'say' and stretch its scene to fit the line (+0.8 s). -> [(start, samples)]"""
    lines = []
    # one voice after another (review §107: alternating characters restarted a TTS worker on almost every line)
    for s in sorted(sb["scenes"], key=lambda x: str(x.get("voice") or "")):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if s["say"] and sb["voice"]:
            a = pcm(tts(s["say"], s["voice"]) if s.get("voice") else tts(s["say"]))  # §107 a character's own voice
            if not len(a):
                continue
            s["seconds"] = round(max(s["seconds"], len(a) / SR + (0.5 if sb.get("story") else 0.8)), 2)
            s["talk0"], s["talk1"] = 0.3, 0.3 + len(a) / SR
            lines.append((s, a))
    timeline(sb)  # starts are known only now: the scenes kept their order, only the voices were made by voice
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
                elif path == "/__friday/story.js":  # §107 the cartoon kit
                    body, kind = open(os.path.join(HERE, "video_story.js"), "rb").read(), "text/javascript"
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


def frames(cdp, seconds, w, h, sink, progress=None, cancel=None, fps=FPS):
    total = max(1, int(round(seconds * fps)))
    for i in range(total):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        cdp.js(f"Promise.resolve(window.T({i / fps:.4f})).then(() => 1)")
        shot = cdp.call("Page.captureScreenshot", format="jpeg", quality=92, clip={"x": 0, "y": 0, "width": w, "height": h, "scale": 1})
        sink(base64.b64decode(shot["data"]))
        if progress and i % fps == 0:
            progress(i / total, f"เฟรม {i}/{total}")
    return total


class Encoder:
    """ffmpeg reading JPEG frames from a pipe while they are captured (§107: a 10-minute video would be GBs of frames
    on disk), the soundtrack from a WAV. Writes <out>.part.mp4, renamed when complete."""

    def __init__(self, wav, out, log, fps=FPS):
        ff = ffmpeg()
        if not ff:
            raise RuntimeError(f"ffmpeg is not installed — install it with: {INSTALL_FFMPEG}")
        self.out, self.part, self.log = out, out + ".part.mp4", log
        cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-"]
        cmd += ["-i", wav] if wav else []
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"] if wav else []
        self.err = open(log, "w")
        try:
            self.p = subprocess.Popen(cmd + [self.part], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.err, creationflags=FLAGS)
        except OSError:
            self.err.close()
            raise

    def write(self, data):
        try:
            self.p.stdin.write(data)
        except OSError:
            raise RuntimeError("ffmpeg stopped: " + open(self.log, errors="replace").read()[-300:])

    def finish(self, cancel=None):
        try:
            self.p.stdin.close()
        except OSError:  # ffmpeg already gone: its log says why (below)
            pass
        while self.p.poll() is None:  # "หยุดทำวิดีโอ" works while ffmpeg finishes too
            if cancel is not None and cancel.is_set():
                self.abort()
                raise Cancelled()
            time.sleep(0.2)
        self.err.close()
        if self.p.returncode or not os.path.isfile(self.part):
            raise RuntimeError("ffmpeg failed: " + open(self.log, errors="replace").read()[-300:])
        os.replace(self.part, self.out)

    def abort(self):
        _kill(self.p)
        self.p.wait()
        self.err.close()
        if os.path.exists(self.part):
            os.remove(self.part)


def make(source, inside, out, tts=None, seconds=None, fmt=None, mood="bright", progress=None, cancel=None, size=None):
    """Render a video. source = storyboard dict (played by video_player.html) or the project path of a page with
    window.T(t) (then `seconds` is needed). inside = the project's fence. -> (out, seconds)"""
    progress = progress or (lambda f, m: None)
    if not ffmpeg():
        raise RuntimeError(f"ffmpeg is not installed — install it with: {INSTALL_FFMPEG}")
    work = tempfile.mkdtemp(prefix="friday-video-")
    srv = p = cdp = enc = None
    try:
        if isinstance(source, dict):
            sb = source
            lines = voice_lines(sb, tts, cancel) if sb["voice"] and tts else []
            limit = sb.get("max_s", MAX_S)
            if sb["seconds"] > limit:  # review: the voice stretched the scenes past the limit
                raise ValueError(f"with the voice-over the video would be {sb['seconds']:.0f} s (limit {limit} s) — shorter lines")
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
        p, cdp = open_page(f"http://127.0.0.1:{srv.server_address[1]}/{urllib.parse.quote(path)}", w, h, prof)
        enc = Encoder(wav, out, os.path.join(work, "ffmpeg.log"))
        frames(cdp, seconds, w, h, enc.write, lambda f, m: progress(0.05 + 0.9 * f, m), cancel)
        cdp.close()
        _kill(p)
        p = cdp = None
        progress(0.96, "รวมเป็น mp4")
        enc.finish(cancel)
        enc = None
        return out, seconds
    finally:
        if enc:
            enc.abort()
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
    tags = open(os.path.join(HERE, "video_player.html"), encoding="utf-8").read().count("</script>")
    assert page.count("</script>") == tags and "\\u003c/script>" in page  # a model's text can't end the script
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
    # §107 a story script -> shots
    st = script("# ผีห้องเรียน\nตัวละคร: ต้น = ชาย ผมสั้น ผิวคล้ำ เสื้อขาว · มิว = หญิง ผมยาวสีน้ำตาล ฮู้ดชมพู แว่น\nซับ: เน้นคำ\n"
                "## ห้องเรียน กลางคืน [23:40]\n(ต้น นอน กลัว · มิว นอน หลับ · กล้อง ใกล้)\nบรรยาย: คืนนั้น *เงียบมาก*\n"
                "ต้น [ตกใจ]: มิว **ได้ยินไหม**\n(ผี)\nเสียงเดินดังขึ้น\n## ทางเดิน กลางวัน\n(มิว ยืน ยิ้ม)\nมิว: ไม่มีอะไรหรอก\n"
                "โจ: ใครเรียก\n<!-- note -->")
    sh = st["scenes"]
    assert st["story"] and st["captions"] == "story" and st["format"] == "vertical" and st["title"] == "ผีห้องเรียน"
    assert [x["type"] for x in sh] == ["shot"] * 5 + ["endcard"] and sh[0]["camera"] == "close" and sh[1]["camera"] == "close"
    assert sh[0]["place"] == "classroom" and sh[0]["time"] == "night" and sh[0]["badge"] == "23:40" and sh[3]["place"] == "corridor" and sh[3]["time"] == "day"
    assert sh[0]["say"] == "คืนนั้น เงียบมาก" and sh[0]["text"] == "คืนนั้น *เงียบมาก*" and not sh[2]["speaker"] and sh[2]["ghost"] and not sh[3]["ghost"]
    ton, miu = sh[1]["cast"]
    assert (ton["name"], ton["pose"], ton["face"], miu["face"]) == ("ต้น", "lie", "shock", "sleep") and sh[2]["cast"][0]["face"] == "scared"
    assert ton["look"]["skin"] == "#b9814f" and ton["look"]["color"] == "#eef0f3" and ton["look"]["hair"] == "short"
    assert miu["look"] == {**miu["look"], "gender": "f", "hair": "long", "hairColor": "#6b4429", "top": "hoodie", "color": "#f29bb8", "glasses": True}
    assert sh[1]["voice"] == "3" and sh[3]["voice"] == "2" and sh[0]["voice"] is None and sh[4]["speaker"] == "โจ" and sh[4]["voice"] == "4"
    assert sh[0]["cut"] and not sh[2]["cut"] and len(sh[3]["cast"]) == 1 and "2. [classroom กลางคืน] ต้น: มิว ได้ยินไหม" in summary(st)
    small = script("# ออฟฟิศ [10:00]\n## ตัวละคร\n- นุ่น: หญิงสาวผมสั้น เสื้อยืดขาว\n- บอส: ชายใส่สูทสีเทา\n"  # how the 4B model writes it
                   "## ห้องทำงาน กลางวัน\n(นุ่น นั่งอยู่ที่โต๊ะ · บอส เดินเข้ามา)\nบอส [ยืนตรง]: \"วันนี้มีงานด่วน\"\n"
                   "(ห้องน้ำ/โถงทางเดิน, กลางคืน)\nนุ่น [ตกใจ]: “ลืมแล้ว!”")["scenes"]
    assert [c["name"] for c in script("## ห้องเรียน\n(ต้น นั่งกลัว · แบงค์ ยืน)\nบรรยาย: เงียบ")["scenes"][0]["cast"]] == ["ต้น", "แบงค์"]
    assert [c["name"] for c in script("## ห้องเรียน\n(ต้น ยืน · ไฟฉาย ชี้)\nบรรยาย: เงียบ")["scenes"][0]["cast"]] == ["ต้น"]
    assert small[0]["place"] == "office" and small[0]["time"] == "day" and small[0]["say"] == "วันนี้มีงานด่วน" and small[0]["speaker"] == "บอส"
    assert [c["pose"] for c in small[0]["cast"]] == ["sit", "stand"] and small[0]["cast"][1]["look"]["top"] == "suit"
    assert small[0]["cast"][0]["look"]["gender"] == "f" and small[0]["cast"][0]["look"]["hair"] == "short"
    assert small[1]["place"] == "corridor" and small[1]["time"] == "night" and small[1]["say"] == "ลืมแล้ว!" and small[2]["text"] == "ออฟฟิศ"
    colon = script("## ห้องเรียน\nเวลา 23:40 น. ทุกคนหลับ\nหมายเหตุ: ห้องมืด\nต้น: ใครน่ะ")["scenes"]  # review: a colon isn't a speaker
    assert [x["speaker"] for x in colon[:3]] == ["", "", "ต้น"] and [c["name"] for c in colon[2]["cast"]] == ["ต้น"]
    thai = script("## ถนน\nบรรยาย: " + "แมวส้มเดินกลับบ้านคนเดียวในคืนที่ฝนตกหนักมาก" * 8)["scenes"]
    assert len(thai) >= 4 and all(len(x["text"]) <= 90 for x in thai)  # Thai with no spaces is cut between words
    many = script("ตัวละคร: " + " · ".join(f"ก{i} = หญิง" for i in range(45)) + "\n## ห้องเรียน\n" + "\n".join(f"ก{i}: สวัสดี" for i in range(45)))
    assert {x["voice"] for x in many["scenes"] if x.get("speaker")} == {"2", "5"}  # more characters than voices: reused, no crash
    for too_long in ("## ถนน\n" + "บรรยาย: เงียบ\n" * 260, "## ถนน\n" + ("บรรยาย: " + "คำ " * 29 + "\n") * 200):
        try:
            script(too_long)
            raise AssertionError("too long accepted")
        except ValueError:
            pass
    loop = script("## ห้องเรียน กลางคืน\nบรรยาย: ความเงียบกลับคืนมาอีกครั้ง\nต้น: ไม่รู้ แต่ฉันรู้สึกว่ามันยิ้มกับเรา\n"
                  "บรรยาย: เสียงประตูปิดลง ความเงียบกลับคืนมาอีกครั้ง\nแบงค์: คืนนี้คงไม่ได้นอน\n"
                  "บรรยาย: ลมพัด ความเงียบกลับคืนมาอีกครั้ง\nต้น: ไม่รู้... แต่ฉันรู้สึกว่ามันยิ้มกับเรา\n"
                  "บรรยาย: ฝนตก ความเงียบกลับคืนมาอีกครั้ง")
    lint = story_lint(loop)
    assert any(p.startswith("ช็อต 6 ซ้ำกับช็อต 2") for p in lint) and any("วนกลับมา 4 ครั้ง" in p for p in lint), lint
    assert story_lint(script("## ห้องเรียน\nบรรยาย: คืนก่อนสอบ\nต้น: ได้ยินไหม\nแบงค์: เสียงอะไร")) == []
    assert story_text(loop).startswith("## classroom (night)\n1. บรรยาย: ความเงียบกลับคืนมาอีกครั้ง\n2. ต้น: ")
    long_line = script("## ถนน\nบรรยาย: " + "คำ " * 80)["scenes"]
    assert len(long_line) == 3 and all(len(x["text"]) <= 90 for x in long_line)  # caption-sized pieces
    for bad in ("", "# แค่ชื่อเรื่อง"):
        try:
            script(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert fixed[0]["type"] == "lines" and fixed[1]["text"] == "เปิดทุกวัน" and fixed[2]["text"] == "ร้าน" and fixed[3]["text"] == "แมวเดินกลับบ้าน"  # a scene stays ≤ 12 s
    empty = io.BytesIO()
    with wave.open(empty, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
    assert len(pcm(empty.getvalue())) == 0  # TTS gave nothing for "…": no crash
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
        out3 = os.path.join(tmp, "story.mp4")  # §107 the cartoon kit loads and draws (a script error = no window.T)
        make(script("## ห้องน้ำ กลางคืน\n(ต้น ไฟฉาย กลัว · ผี)\nต้น: *ใคร* อยู่ตรงนั้น"), fence, out3, size=(180, 320))
        assert os.path.getsize(out3) > 1000
        print("VIDEO SELFTEST OK (rendered 3 videos)")
    else:
        print("VIDEO SELFTEST OK (no Edge/ffmpeg: render not tested)")
    shutil.rmtree(tmp, ignore_errors=True)
