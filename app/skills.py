"""Skills, like Claude Code: skills/<name>/SKILL.md = frontmatter (name, description) + step-by-step instructions.
The model sees only names + descriptions; use_skill loads the full text when a request matches. "/<name> ..." forces one.
A skill gets no extra rights: what it asks for still goes through rules.check / confirm(). Scripts (.ps1) in its folder
run only through run_skill_script in friday.py, which asks every time unless settings.json allows SkillScript(<name>/<file>)."""
import os, re

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root; code lives in app/
DIR = os.environ.get("FRIDAY_SKILLS", os.path.join(ROOT, "skills"))
DESC_MAX, BODY_MAX, FILE_MAX = 160, 3000, 3000  # qwen3.5:4b has an 8k context: the index stays small
FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")

TOOLS = [
    {"type": "function", "function": {
        "name": "use_skill", "description": "Load a skill's full instructions (see the Skills list), then follow them. "
                                            "file = optional other file in the skill folder.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "file": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "run_skill_script", "description": "Run a .ps1 script that a skill's instructions name. The user must approve.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "script": {"type": "string"}},
                       "required": ["name", "script"]}}},
]


def load():
    """{name: {"description", "body", "dir"}}; a SKILL.md without name/description frontmatter is skipped."""
    out = {}
    if not os.path.isdir(DIR):
        return out
    for d in sorted(os.listdir(DIR)):
        try:
            with open(os.path.join(DIR, d, "SKILL.md"), encoding="utf-8") as f:
                m = FRONT.match(f.read().replace("\r\n", "\n"))
        except OSError:
            continue
        if not m:
            continue
        meta = dict(re.findall(r"^(\w+):\s*(.+?)\s*$", m[1], re.M))
        name = meta.get("name", "").strip().lower()
        if NAME.fullmatch(name) and meta.get("description") and name not in out:
            out[name] = {"description": meta["description"][:DESC_MAX], "body": m[2].strip(), "dir": os.path.join(DIR, d)}
    return out


def prompt():
    s = load()
    if not s:
        return ""
    # names only: friday.pick_skill reads the descriptions; the full list cost ~700 tokens of the 8k context every turn
    return f"Skills: {', '.join(s)} (a matching one is loaded for you as ACTIVE SKILL; use_skill reads a skill or a file in its folder)."


def _in_dir(skill, file):
    """A file inside the skill's own folder, or None (no ../ or absolute paths)."""
    path = os.path.realpath(os.path.join(skill["dir"], file))
    return path if path.startswith(os.path.realpath(skill["dir"]) + os.sep) and os.path.isfile(path) else None


def use_skill(name, file=""):
    skill = load().get(str(name).strip().lstrip("/").lower())
    if not skill:
        return f"No skill named '{name}'. Available: {', '.join(load()) or 'none'}."
    if file:
        path = _in_dir(skill, file)
        if not path:
            return f"No file '{file}' in skill '{name}'."
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()[:FILE_MAX]
    files = [f for f in os.listdir(skill["dir"]) if f != "SKILL.md"]
    return skill["body"][:BODY_MAX] + (f"\n\n(Files in this skill: {', '.join(files)})" if files else "")


def script_path(name, script):
    skill = load().get(str(name).strip().lower())
    path = skill and _in_dir(skill, script)
    # only scripts directly in the skill folder: the permission key is <name>/<file name>
    return path if path and path.lower().endswith(".ps1") and os.path.dirname(path) == os.path.realpath(skill["dir"]) else None


def draft(name, description, steps):
    """SKILL.md text for a new skill, or raise ValueError (bad name, already exists, empty)."""
    name = str(name).strip().lower()
    if not NAME.fullmatch(name):
        raise ValueError("name: lowercase English letters, digits and '-' only (e.g. 'water-plants')")
    if name in load() or os.path.exists(os.path.join(DIR, name)):
        raise ValueError(f"skill '{name}' already exists; the user can edit {os.path.join(DIR, name, 'SKILL.md')}")
    description = " ".join(str(description).split())[:DESC_MAX]
    if not description or not str(steps).strip():
        raise ValueError("description and steps are required")
    return f"---\nname: {name}\ndescription: {description}\n---\n{str(steps).strip()}\n"


def save(name, text):
    path = os.path.join(DIR, str(name).strip().lower(), "SKILL.md")
    os.makedirs(os.path.dirname(path))  # exists -> error: never overwrite
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def command(text):
    """'/skills' -> ("reply", listing): answered without the LLM.
    '/<name> rest' -> ("system", the skill's instructions for this turn's system prompt): history keeps only what was typed.
    Else None."""
    if text.strip() == "/skills":
        s = load()
        return ("reply", "\n".join(f"/{n} — {v['description']}" for n, v in s.items()) or f"ยังไม่มี skill — เพิ่มที่ {DIR}")
    m = re.fullmatch(r"/([a-z0-9-]+)\b.*", text.strip(), re.S)
    if m and m[1] in load():
        return ("system", instructions(m[1]))
    return None


def instructions(name):
    """The skill's text for this turn's system prompt (forced by /name or picked by friday.pick_skill)."""
    return (f"ACTIVE SKILL '{name}' (already loaded, do not call use_skill for it). Do every numbered step, "
            f"calling the tools it names BEFORE you answer; never say you did something a tool did not confirm:\n"
            f"{use_skill(name)}")


if __name__ == "__main__":
    import tempfile
    DIR = tempfile.mkdtemp()

    def put(folder, text, extra=None):
        os.makedirs(os.path.join(DIR, folder), exist_ok=True)
        with open(os.path.join(DIR, folder, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(text)
        for k, v in (extra or {}).items():
            with open(os.path.join(DIR, folder, k), "w", encoding="utf-8") as f:
                f.write(v)

    assert prompt() == "" and command("/skills")[0] == "reply"
    put("brief", "---\nname: morning-brief\ndescription: สรุปเช้า\n---\n1. call system_status\n", {"check.ps1": "Get-Date", "notes.md": "x"})
    put("dup", "---\nname: morning-brief\ndescription: duplicate\n---\nsecond\n")
    put("bad", "no frontmatter at all")
    put("badname", "---\nname: ../../evil\ndescription: x\n---\nbody\n")
    put("crlf", "---\r\nname: Meeting-Notes\r\ndescription: จดประชุม\r\n---\r\nsteps\r\n")
    s = load()
    assert list(s) == ["morning-brief", "meeting-notes"], list(s)                  # first of a duplicate wins, bad ones skipped
    assert s["morning-brief"]["body"] == "1. call system_status"
    assert "morning-brief, meeting-notes" in prompt() and "duplicate" not in prompt()
    assert use_skill("/Morning-Brief").startswith("1. call system_status") and "check.ps1" in use_skill("morning-brief")
    assert use_skill("morning-brief", "notes.md") == "x"
    assert use_skill("morning-brief", "..\\dup\\SKILL.md").startswith("No file") and use_skill("nope").startswith("No skill")
    assert use_skill("morning-brief", os.path.join(DIR, "dup", "SKILL.md")).startswith("No file")  # absolute path outside
    assert script_path("morning-brief", "check.ps1") and script_path("morning-brief", "notes.md") is None
    assert script_path("morning-brief", "..\\..\\x.ps1") is None and script_path("nope", "check.ps1") is None
    assert script_path("morning-brief", ".\\check.ps1") == script_path("morning-brief", "check.ps1")  # same file, same key
    os.makedirs(os.path.join(DIR, "brief", "sub"))
    open(os.path.join(DIR, "brief", "sub", "deep.ps1"), "w").close()
    assert script_path("morning-brief", "sub\\deep.ps1") is None
    kind, msg = command("/morning-brief วันนี้")
    assert kind == "system" and "1. call system_status" in msg and command("/morning-brief")[0] == "system"
    assert command("/volume 40") is None and command("hello") is None
    assert command("/skills")[1].startswith("/morning-brief — สรุปเช้า")
    t = draft("water-plants", "รดน้ำต้นไม้\nทุกเช้า", "1. remind the user")
    assert t.startswith("---\nname: water-plants\ndescription: รดน้ำต้นไม้ ทุกเช้า\n---\n1. remind")
    save("water-plants", t)
    assert load()["water-plants"]["body"] == "1. remind the user"
    for bad in [("Water Plants", "d", "s"), ("morning-brief", "d", "s"), ("water-plants", "d", "s"), ("ok-name", "", "s")]:
        try:
            draft(*bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    print("SKILLS SELFTEST OK")
