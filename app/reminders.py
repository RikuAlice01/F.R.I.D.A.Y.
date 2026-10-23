"""Reminders, timers and alarms (PLAN §50). Times are worked out HERE from Thai/English words, never by the model.
Stored in data/reminders.json (survives a restart, never in git). friday.py fires them."""
import datetime as dt, json, os, re, threading, uuid

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.environ.get("FRIDAY_REMINDERS", os.path.join(ROOT, "data", "reminders.json"))
_lock = threading.Lock()

TH_NUM = {"หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9, "สิบ": 10,
          "สิบเอ็ด": 11, "สิบสอง": 12, "ยี่สิบ": 20, "สามสิบ": 30, "สี่สิบ": 40, "สี่สิบห้า": 45, "ครึ่ง": 30, "สิบห้า": 15}
_ONES = "หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า"
# any Thai number word 1-99 ("ยี่สิบห้า", "สิบสาม", "สามสิบเอ็ด") or digits — longest first (code review §58: "ยี่สิบห้า" read as 5)
NUM = r"(\d{1,3}|(?:(?:ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?สิบ(?:เอ็ด|" + _ONES + r")?)|" + _ONES + r"|ครึ่ง)"
ONES = {w: i + 1 for i, w in enumerate(_ONES.split("|"))}


def _n(w):
    """'25' / 'ยี่สิบห้า' / 'สิบสาม' / 'ห้า' / 'ครึ่ง' -> int."""
    w = str(w)
    if w.isdigit():
        return int(w)
    if w in TH_NUM and "สิบ" not in w[1:]:
        return TH_NUM[w]
    if "สิบ" in w:
        tens, _, ones = w.partition("สิบ")
        t = 2 if tens == "ยี่" else ONES.get(tens, 1)
        o = 1 if ones == "เอ็ด" else ONES.get(ones, 0)
        return t * 10 + o
    return ONES[w]


# ---------- durations: "อีก 10 นาที", "in 2 hours", "25 นาที" ----------
UNIT = {"วินาที": 1, "วิ": 1, "second": 1, "seconds": 1, "sec": 1, "นาที": 60, "minute": 60, "minutes": 60, "min": 60, "mins": 60,
        "ชั่วโมง": 3600, "ชม": 3600, "ชม.": 3600, "hour": 3600, "hours": 3600, "hr": 3600}
DUR = re.compile(NUM + r"\s*(ชั่วโมง|ชม\.?|นาที|วินาที|วิ|hours?|hr|minutes?|mins?|min|seconds?|sec)(?:\s*(ครึ่ง))?", re.I)


def duration(text):
    """Seconds in phrases like "1 ชั่วโมง 30 นาที", "ชั่วโมงครึ่ง", "2 hours" — or None."""
    total, hit, end = 0, False, None
    for m in DUR.finditer(text):
        if end is not None and text[end:m.start()].strip(" และand,") != "":
            break  # a second, separate duration belongs to the message ("ต้มไข่ 7 นาที"), not to the time
        sec = UNIT[m[2].lower().rstrip(".") if m[2].lower().rstrip(".") in UNIT else m[2].lower()]
        total += _n(m[1]) * sec + (sec // 2 if m[3] else 0)
        hit, end = True, m.end()
    if re.search(r"ชั่วโมงครึ่ง", text) and not hit:
        return 5400
    return total if hit else None


# ---------- clock times: "ตี 6", "บ่ายสาม(ครึ่ง)", "6 โมงเย็น", "2 ทุ่ม", "15:30", "3 pm", "เที่ยง" ----------
def clock(text, now):
    """The next datetime matching a clock time in `text` (tomorrow if "พรุ่งนี้"/"tomorrow" or already past), or None."""
    t = text.lower()
    h = mi = None
    half = 30 if re.search(r"ครึ่ง", t) else 0
    m = re.search(r"(\d{1,2})[:.](\d{2})", t)
    if m and int(m[1]) < 24 and int(m[2]) < 60:
        h, mi = int(m[1]), int(m[2])
    elif m := re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t):
        h, mi = int(m[1]) % 12 + (12 if m[3].startswith("p") else 0), int(m[2] or 0)
    elif re.search(r"เที่ยงคืน|midnight", t):
        h, mi = 0, 0
    elif re.search(r"เที่ยง(?!คืน)|noon", t):
        h, mi = 12, half
    elif m := re.search(r"ตี\s*" + NUM, t):
        h, mi = _n(m[1]) % 24, half
    elif m := re.search(r"บ่าย\s*" + NUM + r"?", t):
        h, mi = 12 + (_n(m[1]) if m[1] else 1), half
    elif m := re.search(NUM + r"\s*โมงเย็น", t):
        h, mi = 12 + _n(m[1]) if _n(m[1]) < 12 else _n(m[1]), half
    elif m := re.search(NUM + r"\s*ทุ่ม", t):
        h, mi = 18 + _n(m[1]), half
    elif m := re.search(NUM + r"\s*โมงเช้า", t):
        h, mi = _n(m[1]), half
    elif m := re.search(NUM + r"\s*(?:โมง|นาฬิกา|o'?clock)", t):
        n = _n(m[1])
        h, mi = n, half
        if n < 12 and "นาฬิกา" not in t:  # "6 โมง": 06:00 or 18:00 — whichever comes next
            a = now.replace(hour=n, minute=half, second=0, microsecond=0)
            if a <= now:
                h = n + 12 if n + 12 < 24 and now.replace(hour=n + 12, minute=half, second=0, microsecond=0) > now else n
    if h is None or not 0 <= h < 24:
        return None
    when = now.replace(hour=h, minute=mi or 0, second=0, microsecond=0)
    if re.search(r"พรุ่งนี้|tomorrow", t):
        when += dt.timedelta(days=1)
    elif when <= now:
        when += dt.timedelta(days=1)
    return when


# ---------- whole commands ----------
FILLER = re.compile(r"(?:ช่วย|ฉัน|ผม|หน่อย|ด้วย|นะ|ค่ะ|คะ|ครับ|ให้|ที|please|me|to|that|about|the|at|in|on|for|ตอน|เวลา|อีก|วันนี้|พรุ่งนี้|tomorrow|today)", re.I)


def _message(text, cuts):
    """What to say when it fires: the text minus the trigger words and the time."""
    for c in cuts:
        text = re.sub(c, " ", text, flags=re.I)
    words = [w for w in re.split(r"\s+", text) if w and not FILLER.fullmatch(w)]
    msg = " ".join(words).strip(" ,.")
    # Thai has no spaces: "กินยาตอน 2 ทุ่ม" leaves "กินยาตอน" — drop a glued time word at either end
    return re.sub(r"^(?:ช่วย|ให้)+|(?:ตอน|เวลา|ช่วง|ภายใน|ให้|ด้วย|หน่อย)+$", "", msg).strip() or ""


TIME_PART = (DUR.pattern, r"\d{1,2}[:.]\d{2}", r"\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)", r"ตี\s*" + NUM, r"บ่าย\s*" + NUM + "?",
             NUM + r"\s*(?:โมงเย็น|โมงเช้า|ทุ่ม|โมง|นาฬิกา|o'?clock)", r"เที่ยงคืน|เที่ยง|midnight|noon", r"ครึ่ง")


def parse(text, now=None):
    """{"kind": remind|alarm|timer, "when": datetime, "text": what to say} for a reminder command, else None."""
    now = now or dt.datetime.now()
    t = " ".join(str(text).split())
    if re.search(r"แจ้งเตือน|ทำไม|ยังไง|อย่างไร|ได้ไหม|ไหม\b|มั้ย|หรือเปล่า|\?|^(?:why|how|what|when|does|do|can|is)\b", t, re.I):
        return None  # a question about reminders/notifications, not a command (code review §58)
    lead = r"^(?:(?:ช่วย|ฉัน|ผม|please|hey friday,?)\s*)*(?:อีก\s*\S+\s*\S*\s*)?"  # the trigger must start the sentence
    if not re.search(lead + r"(?:ตั้ง)?(?:เตือน|ปลุก|จับเวลา|ตั้งเวลา)|^(?:please )?(?:remind|set|wake|start)", t, re.I):
        return None
    if re.search(r"^(?:ตั้ง)?(?:จับเวลา|ตั้งเวลา)|^(?:set (?:a |the )?)?timer|^start (?:a )?timer", t, re.I):
        sec = duration(t)
        return {"kind": "timer", "when": now + dt.timedelta(seconds=sec), "text": "หมดเวลาแล้วค่ะ"} if sec else None
    if re.search(r"ปลุก|^(?:set (?:an |the )?)?alarm|wake me", t, re.I):
        sec = duration(t) if re.search(r"อีก|^in\b|\bin \d", t, re.I) else None
        when = now + dt.timedelta(seconds=sec) if sec else clock(t, now)
        return {"kind": "alarm", "when": when, "text": "ถึงเวลาปลุกแล้วค่ะ"} if when else None
    if re.search(r"เตือน|remind", t, re.I):
        sec = duration(t) if re.search(r"อีก|\bin\s+\d|\bin\s+(?:an?|one)\b", t, re.I) else None
        when = now + dt.timedelta(seconds=sec) if sec else clock(t, now)
        if not when:
            return None
        msg = _message(t, (r"(?:ช่วย)?เตือน(?:ความจำ)?", r"remind(?:er)?", r"set (?:a )?") + TIME_PART)
        return {"kind": "remind", "when": when, "text": msg or "ถึงเวลาที่ให้เตือนแล้วค่ะ"}
    return None


# ---------- storage ----------
def _load():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save(items):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def add(item):
    with _lock:
        items = _load()
        rec = {"id": uuid.uuid4().hex[:8], "kind": item["kind"], "when": item["when"].isoformat(timespec="seconds"), "text": item["text"]}
        items.append(rec)
        _save(sorted(items, key=lambda r: r["when"]))
        return rec


def pending():
    return _load()


def cancel(words):
    """Removes reminders whose text/kind contains all `words`. No words = nothing (code review §58: an empty
    "ยกเลิกเตือน" wiped tomorrow's alarm too) — use cancel_all() for that. Returns how many."""
    w = [x for x in re.split(r"\s+", str(words).lower()) if x and not FILLER.fullmatch(x)]
    if not w:
        return 0
    with _lock:
        items = _load()
        keep = [r for r in items if not all(x in (r["text"] + " " + r["kind"]).lower() for x in w)]
        _save(keep)
        return len(items) - len(keep)


def cancel_all():
    with _lock:
        n = len(_load())
        _save([])
        return n


def due(now=None):
    """Pops and returns everything whose time has come."""
    now = (now or dt.datetime.now()).isoformat(timespec="seconds")
    with _lock:
        items = _load()
        ready = [r for r in items if r["when"] <= now]
        if ready:
            _save([r for r in items if r["when"] > now])
        return ready


def say_when(when, now=None):
    """Thai: "15:00 (อีก 2 ชั่วโมง 5 นาที)" / "พรุ่งนี้ 06:00"."""
    now = now or dt.datetime.now()
    left = int((when - now).total_seconds())
    h, m = divmod((max(0, left) + 59) // 60, 60)  # 9:59 left says "10 นาที", not 9
    rel = (f"{h} ชั่วโมง " if h else "") + (f"{m} นาที" if m or not h else "")
    if left < 60:
        rel = f"{max(left, 1)} วินาที"
    day = "พรุ่งนี้ " if when.date() > now.date() else ""
    return f"{day}{when:%H:%M} (อีก {rel.strip()})"


if __name__ == "__main__":
    import tempfile
    FILE = os.path.join(tempfile.mkdtemp(), "r.json")
    now = dt.datetime(2026, 10, 23, 9, 0)  # Friday 09:00
    def at(text):
        r = parse(text, now)
        return (r["kind"], r["when"].strftime("%d %H:%M"), r["text"]) if r else None
    cases = {
        "อีก 10 นาทีเตือนเอาผ้าออก": ("remind", "23 09:10", "เอาผ้าออก"),
        "ช่วยเตือนประชุมบ่ายสามหน่อย": ("remind", "23 15:00", "ประชุม"),
        "เตือนกินยาตอน 2 ทุ่มครึ่ง": ("remind", "23 20:30", "กินยา"),
        "เตือนโทรหาแม่ 18:45": ("remind", "23 18:45", "โทรหาแม่"),
        "ปลุกตี 6": ("alarm", "24 06:00", "ถึงเวลาปลุกแล้วค่ะ"),
        "ปลุกพรุ่งนี้ 7 โมงเช้า": ("alarm", "24 07:00", "ถึงเวลาปลุกแล้วค่ะ"),
        "จับเวลา 25 นาที": ("timer", "23 09:25", "หมดเวลาแล้วค่ะ"),
        "ตั้งเวลา 1 ชั่วโมง 30 นาที": ("timer", "23 10:30", "หมดเวลาแล้วค่ะ"),
        "remind me in 20 minutes to check the oven": ("remind", "23 09:20", "check oven"),
        "remind me at 3 pm to call John": ("remind", "23 15:00", "call John"),
        "set a timer for 5 minutes": ("timer", "23 09:05", "หมดเวลาแล้วค่ะ"),
        "wake me up at 6:30": ("alarm", "24 06:30", "ถึงเวลาปลุกแล้วค่ะ"),
        "เตือนส่งงานเที่ยง": ("remind", "23 12:00", "ส่งงาน"),
        "เตือนรดน้ำต้นไม้ 6 โมงเย็น": ("remind", "23 18:00", "รดน้ำต้นไม้"),
        "เตือนเก็บผ้า 6 โมง": ("remind", "23 18:00", "เก็บผ้า"),  # 06:00 already past at 09:00 -> 18:00 today
    }
    bad = {k: (at(k), v) for k, v in cases.items() if at(k) != v}
    assert not bad, bad
    for t in ("ตอนนี้กี่โมง", "วันนี้อากาศเป็นยังไง", "เตือนฉันหน่อย", "ปลุกหน่อย", "จับเวลา"):
        assert parse(t, now) is None, (t, parse(t, now))
    a = add(parse("อีก 10 นาทีเตือนเอาผ้าออก", now)); add(parse("ปลุกตี 6", now))
    assert len(pending()) == 2 and due(now) == [] and [r["text"] for r in due(now + dt.timedelta(minutes=11))] == ["เอาผ้าออก"]
    assert len(pending()) == 1 and cancel("ผ้า") == 0 and cancel("ปลุก") == 1 and pending() == []  # "ยกเลิกปลุก"
    add(parse("จับเวลา 5 นาที", now)); add(parse("เตือนกินยา 2 ทุ่ม", now))
    assert cancel("") == 0 and cancel("ให้ หน่อย") == 0 and len(pending()) == 2  # nothing named = nothing removed
    assert cancel_all() == 2 and pending() == []  # "ยกเลิกเตือนทั้งหมด"
    # code review §58: compound numbers, one duration only, questions are not commands
    assert at("อีกยี่สิบห้านาทีเตือนเอาผ้าออก") == ("remind", "23 09:25", "เอาผ้าออก")
    assert at("อีกสิบสามนาทีเตือนดูเตา") == ("remind", "23 09:13", "ดูเตา")
    assert at("อีก 10 นาทีเตือนต้มไข่ 7 นาที")[1] == "23 09:10"
    assert at("remind me in 5 minutes to take a 10 minute break")[1] == "23 09:05"
    assert parse("ทำไมแจ้งเตือน LINE ไม่ดังตอน 6 โมงเย็น", now) is None and parse("ตั้งเตือนได้ไหม", now) is None
    assert parse("เมื่อวานลืมตั้งปลุกตี 6", now) is None  # telling, not asking FRIDAY to set one
    assert say_when(dt.datetime(2026, 10, 23, 9, 10), now - dt.timedelta(seconds=-1)) == "09:10 (อีก 10 นาที)"
    assert say_when(dt.datetime(2026, 10, 23, 11, 5), now) == "11:05 (อีก 2 ชั่วโมง 5 นาที)" and say_when(dt.datetime(2026, 10, 24, 6, 0), now).startswith("พรุ่งนี้ 06:00")
    print("REMINDERS SELFTEST OK")
