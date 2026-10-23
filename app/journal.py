"""Day log + end-of-day summary (PLAN §57). Each finished turn is appended to data/logs/day-YYYY-MM-DD.jsonl (personal,
never in git); context() gathers that day's talk, actions (audit log) and finished tasks for the model to summarise;
save() writes the summary into the vault as Journal/YYYY-MM-DD.md (adds a section, never rewrites what is there)."""
import datetime as dt, json, os, threading

import memory, security, tasks

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.environ.get("FRIDAY_DAYLOG", os.path.join(ROOT, "data", "logs"))
_lock = threading.Lock()


def _file(day):
    return os.path.join(LOGS, f"day-{day.isoformat()}.jsonl")


def log_turn(you, friday, source="typed"):
    now = dt.datetime.now()
    os.makedirs(LOGS, exist_ok=True)
    with _lock, open(_file(now.date()), "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": now.strftime("%H:%M"), "src": source, "you": str(you)[:300], "friday": str(friday)[:300]},
                           ensure_ascii=False) + "\n")


def _jsonl(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []


def context(day=None, limit=6000):
    """What happened on `day`, compact, for the model (newest talk kept when long)."""
    day = day or dt.date.today()
    talk = [f"{e['t']} คุณ: {e['you']} | FRIDAY: {e['friday']}" for e in _jsonl(_file(day))]
    acts = [f"{e['t'][11:16]} {e['tool']} {e['args'][:80]} → {e['decision']}" for e in _jsonl(security.AUDIT)
            if e.get("t", "").startswith(day.isoformat()) and e.get("decision") in ("done", "blocked", "declined")]
    done_today = []  # boxes ticked today: Tasks.md keeps the ✅ date
    try:
        with open(tasks.path(), encoding="utf-8") as f:
            done_today = [l.split("] ", 1)[1].split(" 📅")[0].split(" ✅")[0] for l in f if "✅ " + day.isoformat() in l]
    except (OSError, IndexError):
        pass
    parts = [f"Day: {day.isoformat()}"]
    if talk:
        parts.append("Conversation:\n" + "\n".join(talk))
    if acts:
        parts.append("Actions on the PC:\n" + "\n".join(acts))
    if done_today:
        parts.append("Tasks finished:\n" + "\n".join(f"- {t}" for t in done_today))
    text = "\n\n".join(parts)
    return text[-limit:] if len(text) > limit else text, bool(talk or acts or done_today)


ACT_TH = {"open": "เปิด", "hardware": "ฮาร์ดแวร์", "media": "เพลง", "window": "หน้าต่าง", "weather": "ดูอากาศ", "reminder": "ตั้งเตือน",
          "write_document": "สร้างไฟล์", "pdf_tool": "PDF", "run_powershell": "PowerShell", "run_skill_script": "สคริปต์ skill",
          "smart_home": "สมาร์ทโฮม", "approve_files": "ยืนยันไฟล์", "safe_mode": "โหมดปลอดภัย", "read_document": "อ่านเอกสาร"}


def summary(day=None):
    """End-of-day summary written by code from the records — no model, so nothing is made up (a 4B model invented
    "feeling tired after hard work" from nowhere, §57)."""
    day = day or dt.date.today()
    talk = _jsonl(_file(day))
    acts = [e for e in _jsonl(security.AUDIT) if e.get("t", "").startswith(day.isoformat()) and e.get("decision") == "done"
            and e.get("tool") not in ("approve_files",)]
    done_today = []
    try:
        with open(tasks.path(), encoding="utf-8") as f:
            done_today = [l.split("] ", 1)[1].split(" 📅")[0].split(" ✅")[0].strip() for l in f if "✅ " + day.isoformat() in l]
    except (OSError, IndexError):
        pass
    if not (talk or acts or done_today):
        return "วันนี้ยังไม่มีอะไรบันทึกไว้ค่ะ"
    out = [f"วันนี้คุยกัน {len(talk)} ครั้ง ทำกับเครื่อง {len(acts)} อย่าง งานเสร็จ {len(done_today)} งานค่ะ"]
    if talk:
        out.append("**คุยเรื่อง**")
        out += [f"- {e['t']} {e['you'][:70]}" for e in talk[-12:]]
    if acts:
        out.append("**ทำกับเครื่อง**")
        seen = []
        for e in acts:
            item = f"{ACT_TH.get(e['tool'], e['tool'])} {str(e['args'])[:50]}".strip()
            if item not in seen:
                seen.append(item)
        out += [f"- {x}" for x in seen[-12:]]
    if done_today:
        out.append("**งานที่เสร็จ**")
        out += [f"- {t}" for t in done_today]
    return "\n".join(out)


def save(text, day=None):
    """Adds the summary to the vault note Journal/<day>.md (creates it; existing text is kept). Returns the path."""
    day = day or dt.date.today()
    path = os.path.join(memory.VAULT, "Journal", f"{day.isoformat()}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    head = "" if os.path.exists(path) else f"# {day.isoformat()}\n\n"
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(f"{head}## สรุปโดย FRIDAY {dt.datetime.now():%H:%M}\n\n{text.strip()}\n\n")
    return path


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    LOGS = d
    memory.VAULT = os.path.join(d, "vault")
    security.AUDIT = os.path.join(d, "audit.log")
    today = dt.date.today()
    assert context(today) == (f"Day: {today.isoformat()}", False)
    log_turn("วันนี้อากาศเป็นยังไง", "ตอนนี้ 26 องศา มีเมฆบางส่วนค่ะ", "voice")
    security.audit("voice", "weather", "ตำแหน่งปัจจุบัน", "done", "26°C")
    security.audit("panel", "open", "https://x", "error", "x")  # errors are left out
    tasks.add("ส่งรายงาน", today)
    tasks.done("รายงาน", today)
    text, any_ = context(today)
    assert any_ and "อากาศ" in text and "weather" in text and "ส่งรายงาน" in text and "https://x" not in text, text
    sm = summary(today)
    assert sm.startswith("วันนี้คุยกัน 1 ครั้ง ทำกับเครื่อง 1 อย่าง งานเสร็จ 1 งานค่ะ") and "วันนี้อากาศเป็นยังไง" in sm and "ดูอากาศ" in sm and "- ส่งรายงาน" in sm, sm
    assert summary(today - dt.timedelta(days=400)) == "วันนี้ยังไม่มีอะไรบันทึกไว้ค่ะ"
    p = save("- ถามอากาศ\n- ส่งรายงานเสร็จ", today)
    save("- อีกรอบ", today)
    body = open(p, encoding="utf-8").read()
    assert body.startswith(f"# {today.isoformat()}") and body.count("## สรุปโดย FRIDAY") == 2, body
    print("JOURNAL SELFTEST OK")
