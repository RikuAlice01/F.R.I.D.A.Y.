"""To-do list in the Obsidian vault (PLAN §52): data/vault/Tasks.md, one "- [ ] task 📅 YYYY-MM-DD" per line (the Obsidian
Tasks plugin style, editable by hand). FRIDAY only appends lines and ticks boxes; it never deletes or rewrites the owner's."""
import datetime as dt, os, re, threading

import memory

_lock = threading.Lock()
HEADER = "# Tasks\n\nงานที่ต้องทำ — FRIDAY เพิ่ม/ติ๊กให้ แก้เองได้ (`- [ ]` = ยังไม่เสร็จ · `📅` = กำหนดส่ง)\n\n"
TASK = re.compile(r"^(\s*[-*] \[)( |x|X)(\] )(.*)$")
DUE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
TH_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
TH_DAY_RE = ["จันทร์", "อังคาร", "พุธ", "พฤหัส(?:บดี)?", "ศุกร์", "เสาร์", "อาทิตย์"]
EN_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def path():
    return os.path.join(memory.VAULT, "Tasks.md")


def due_date(text, today=None):
    """(date or None, text without the date words). วันนี้/พรุ่งนี้/มะรืน · (วัน)จันทร์..อาทิตย์ · today/tomorrow/monday · 2026-10-25."""
    today = today or dt.date.today()
    t = text
    when = None
    if m := re.search(r"\d{4}-\d{2}-\d{2}", t):
        when, t = dt.date.fromisoformat(m[0]), t.replace(m[0], " ")
    elif m := re.search(r"มะรืน(?:นี้)?|day after tomorrow", t, re.I):
        when, t = today + dt.timedelta(days=2), t.replace(m[0], " ")
    elif m := re.search(r"พรุ่งนี้|tomorrow", t, re.I):
        when, t = today + dt.timedelta(days=1), t.replace(m[0], " ")
    elif m := re.search(r"วันนี้|today|tonight|คืนนี้", t, re.I):
        when, t = today, t.replace(m[0], " ")
    else:
        # weekdays: Thai "(วัน)ศุกร์(นี้|หน้า)" · English only after on/by/next/this (code review §58: the project
        # name "FRIDAY" became a due date)
        for i, (th, en) in enumerate(zip(TH_DAY_RE, EN_DAYS)):
            m = re.search(rf"(?:ภายใน|ก่อน)?(?:วัน)?(?:{th})(?:นี้|หน้า)?", t) or \
                re.search(rf"\b(?:on|by|next|this|before)\s+{en}\b", t, re.I)
            if m:
                if re.search(r"หน้า|next", m[0], re.I):  # "พุธหน้า" = that day of NEXT week (Monday-based)
                    when = today - dt.timedelta(days=today.weekday()) + dt.timedelta(days=7 + i)
                else:
                    when = today + dt.timedelta(days=(i - today.weekday()) % 7 or 7)  # the next one, never today
                t = t.replace(m[0], " ")
                break
    return when, " ".join(t.split()).strip(" ,.")


def _read():
    try:
        with open(path(), encoding="utf-8") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []


def _write(lines):
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, path())


def add(text, today=None):
    when, what = due_date(text, today)
    if not what:
        raise ValueError("empty task")
    with _lock:
        lines = _read() or HEADER.rstrip("\n").split("\n")
        lines.append(f"- [ ] {what}" + (f" 📅 {when.isoformat()}" if when else ""))
        _write(lines)
    return what, when


def items():
    """[(done, text, due date or None)] in file order."""
    out = []
    for l in _read():
        if m := TASK.match(l):
            d = DUE.search(m[4])
            out.append((m[2] != " ", DUE.sub("", m[4]).replace("✅", "").strip(), dt.date.fromisoformat(d[1]) if d else None))
    return out


def open_for(day=None):
    """Open tasks for `day`: due that day or overdue, plus undated ones."""
    day = day or dt.date.today()
    return [(t, d) for done, t, d in items() if not done and (d is None or d <= day)]


def done(words, today=None):
    """Ticks the first open task containing every word. Returns its text or None."""
    w = [x for x in str(words).lower().split() if x]
    if not w:
        return None
    with _lock:
        lines = _read()
        for i, l in enumerate(lines):
            m = TASK.match(l)
            name = DUE.sub("", m[4]).lower() if m else ""
            if m and m[2] == " " and all(x in name for x in w) and len("".join(w)) * 2 >= len(name.replace(" ", "")):
                lines[i] = f"{m[1]}x{m[3]}{m[4]} ✅ {(today or dt.date.today()).isoformat()}"
                _write(lines)
                return DUE.sub("", m[4]).strip()
    return None


def say_due(d, today=None):
    today = today or dt.date.today()
    if d is None:
        return ""
    if d < today:
        return f" (เลยกำหนด {d:%d/%m})"
    return " (วันนี้)" if d == today else " (พรุ่งนี้)" if d == today + dt.timedelta(days=1) else f" ({TH_DAYS[d.weekday()]} {d:%d/%m})"


if __name__ == "__main__":
    import tempfile
    memory.VAULT = tempfile.mkdtemp()
    fri = dt.date(2026, 10, 23)  # a Friday
    assert due_date("ส่งรายงานพรุ่งนี้", fri) == (dt.date(2026, 10, 24), "ส่งรายงาน")
    assert due_date("ส่งรายงานวันจันทร์", fri) == (dt.date(2026, 10, 26), "ส่งรายงาน")
    assert due_date("ประชุมทีมศุกร์หน้า", fri) == (dt.date(2026, 10, 30), "ประชุมทีม")
    assert due_date("call mom tomorrow", fri) == (dt.date(2026, 10, 24), "call mom")
    assert due_date("ซื้อนม", fri) == (None, "ซื้อนม") and due_date("จ่ายค่าไฟ 2026-11-01", fri)[0] == dt.date(2026, 11, 1)
    # the owner's own lines are kept exactly
    os.makedirs(memory.VAULT, exist_ok=True)
    open(path(), "w", encoding="utf-8").write("# Tasks\nโน้ตของฉันเอง\n- [ ] งานเดิมของฉัน\n")
    add("ส่งรายงานพรุ่งนี้", fri); add("ซื้อนม", fri); add("จ่ายค่าไฟ 2026-10-20", fri)
    text = open(path(), encoding="utf-8").read()
    assert text.startswith("# Tasks\nโน้ตของฉันเอง\n- [ ] งานเดิมของฉัน\n- [ ] ส่งรายงาน 📅 2026-10-24\n"), text
    assert [t for t, _ in open_for(fri)] == ["งานเดิมของฉัน", "ซื้อนม", "จ่ายค่าไฟ"]  # tomorrow's not yet; overdue yes
    assert done("รายงาน", fri) == "ส่งรายงาน" and done("รายงาน", fri) is None and done("", fri) is None
    assert "- [x] ส่งรายงาน 📅 2026-10-24 ✅ 2026-10-23" in open(path(), encoding="utf-8").read()
    assert say_due(dt.date(2026, 10, 20), fri).startswith(" (เลยกำหนด") and say_due(fri, fri) == " (วันนี้)"
    # code review §58
    assert due_date("แก้บั๊ก FRIDAY ให้เสร็จ", fri) == (None, "แก้บั๊ก FRIDAY ให้เสร็จ")
    assert due_date("ส่งงานวันพฤหัสบดี", fri) == (dt.date(2026, 10, 29), "ส่งงาน")
    mon = dt.date(2026, 10, 26)
    assert due_date("ประชุมพุธหน้า", mon)[0] == dt.date(2026, 11, 4) and due_date("ประชุมพุธ", mon)[0] == dt.date(2026, 10, 28)
    assert due_date("demo on friday", fri)[0] == dt.date(2026, 10, 30)
    add("ส่งงานลูกค้า", fri)
    assert done("งาน", fri) is None and done("ส่งงานลูกค้า", fri) == "ส่งงานลูกค้า"  # a fragment doesn't tick it
    print("TASKS SELFTEST OK")
