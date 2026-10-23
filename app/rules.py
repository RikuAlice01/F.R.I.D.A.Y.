"""User rules, Claude Code style.

Rules.md (in the Obsidian vault)  ~ CLAUDE.md : instructions injected into every prompt. Add with "# <rule>".
settings.json                     ~ .claude/settings.json : permission rules enforced in code, not by the LLM.
    {"permissions": {"allow": ["PowerShell(Get-Process*)", "Open(*.pdf)"], "deny": ["PowerShell(*Stop-Computer*)"]}}
    deny  = blocked, never asks.  allow = runs without asking.  anything else = asks y/N.  deny wins.
"""
import fnmatch, json, os, re

import memory

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root; code lives in app/
SETTINGS = os.environ.get("FRIDAY_SETTINGS", os.path.join(ROOT, "config", "settings.json"))
RULES_MAX = 4000  # chars of Rules.md sent with every request
RULES_HEADER = "# Rules\n\nกฎที่ FRIDAY ต้องทำตามทุกครั้ง (เหมือน CLAUDE.md) — 1 บรรทัด `- ` = 1 กฎ เขียนอิสระได้\n"
DEFAULT_SETTINGS = {"permissions": {
    "allow": ["PowerShell(Get-Date*)", "PowerShell(Get-Process*)", "PowerShell(Get-ChildItem*)", "PowerShell(Get-Content*)",
              "PowerShell(Sort-Object*)", "PowerShell(Select-Object*)", "PowerShell(Measure-Object*)", "PowerShell(Format-Table*)"],
    "deny": ["PowerShell(*Format-Volume*)", "PowerShell(*Clear-Disk*)", "PowerShell(*Stop-Computer*)",
             "PowerShell(*Restart-Computer*)", "PowerShell(*Remove-Item*-r*)",  # -r* = -Recurse and its abbreviations
             "PowerShell(ri *-r*)", "PowerShell(rm *-r*)", "PowerShell(del *-r*)", "PowerShell(erase *-r*)",
             "PowerShell(rd *)", "PowerShell(rmdir *)"]}}  # no leading * = the segment starts with this alias
# allow = every | segment matches an allow rule AND uses only these characters: no ( ) @ $ { } ; & ` < > % etc.,
# so no subexpressions, variables, script blocks, chaining or redirection can ride along with a "read-only" cmdlet
PLAIN = re.compile(r"[\w\s\-.\\/:*,'\"]*")
# PowerShell treats these as '-' and quotes; normalize so deny/allow patterns see what PowerShell will run
LOOKALIKES = str.maketrans({c: "-" for c in "‐‑‒–—―−"} |
                           {c: "'" for c in "‘’‚‛"} | {c: '"' for c in "“”„"})


def rules_file():
    return os.path.join(memory.VAULT, "Rules.md")


def text():
    try:
        with open(rules_file(), encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def prompt():
    t = text()
    return f"User rules (from Rules.md; always follow them, they override the defaults above):\n{t[:RULES_MAX]}" if t else ""


def ensure_file():
    if not os.path.exists(rules_file()):
        os.makedirs(memory.VAULT, exist_ok=True)
        with open(rules_file(), "w", encoding="utf-8") as f:
            f.write(RULES_HEADER)
    return rules_file()


def add(rule):
    rule = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", rule)).strip()
    if not rule:
        return "Empty rule."
    body = text() if os.path.exists(ensure_file()) else ""
    with open(rules_file(), "w", encoding="utf-8") as f:
        f.write(f"{body}\n- {rule}\n")
    return f"Rule added: {rule}"


OLD_DEFAULT_DENY = ["PowerShell(*Format-Volume*)", "PowerShell(*Clear-Disk*)", "PowerShell(*Stop-Computer*)",
                    "PowerShell(*Restart-Computer*)", "PowerShell(*Remove-Item*-Recurse*)"]


def settings():
    try:  # upgrade an untouched first-version settings.json to the stronger deny list
        with open(SETTINGS, encoding="utf-8") as f:
            old = json.load(f).get("permissions", {}).get("deny") == OLD_DEFAULT_DENY
        if old:
            os.remove(SETTINGS)
    except (OSError, ValueError, AttributeError):
        pass
    if not os.path.exists(SETTINGS):
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  ⚠  settings.json อ่านไม่ได้ ({e}) — ทุกอย่างจะถามก่อน")
        return {}


def set_setting(key, value):
    """Store a preference (e.g. "voice_volume") in settings.json next to the permissions; atomic write."""
    s = settings() or {}
    s[key] = value
    with open(SETTINGS + ".tmp", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(SETTINGS + ".tmp", SETTINGS)


def check(tool, arg):
    """'deny' | 'allow' | 'ask' for e.g. check('PowerShell', 'Get-Process')."""
    perms = settings().get("permissions", {})

    def hits(kind, values):
        for pat in perms.get(kind, []):
            m = re.fullmatch(r"\s*(\w+)\((.*)\)\s*", pat)
            if m and m[1].lower() == tool.lower() and any(fnmatch.fnmatch(v.lower(), m[2].lower()) for v in values):
                return True
        return False

    arg = arg.translate(LOOKALIKES).strip()
    segments = [s.strip() for s in re.split(r"[;&|\n\r(){}]+", arg)]  # also the inside of (...) and {...}
    if hits("deny", [arg] + segments):
        return "deny"
    if tool.lower() == "powershell":
        if all(PLAIN.fullmatch(s) and hits("allow", [s.strip()]) for s in arg.split("|")):
            return "allow"
    elif hits("allow", [arg]):
        return "allow"
    return "ask"


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    memory.VAULT, SETTINGS = d, os.path.join(d, "settings.json")
    assert check("PowerShell", "Get-Process") == "allow"
    assert check("PowerShell", "Get-Process; Remove-Item C:\\x") == "ask"      # chaining never auto-allowed
    assert check("PowerShell", "Get-Date; Stop-Computer") == "deny"            # denied segment inside a chain
    assert check("PowerShell", "remove-item C:\\x -recurse -force") == "deny"  # case-insensitive
    assert check("PowerShell", "Get-Process $(Remove-Item x)") == "ask"
    # review findings: subexpressions, Unicode dashes, aliases/abbreviations
    assert check("PowerShell", "Get-Date (Start-Process calc)") == "ask"
    assert check("PowerShell", "Get-Process @(Remove-Item x)") == "ask"
    assert check("PowerShell", "Get-Date $env:USERPROFILE") == "ask"
    assert check("PowerShell", "Get-Process (Remove-Item X \u2013Recurse -Force)") == "deny"
    assert check("PowerShell", "Remove-Item X \u2014Recurse") == "deny"
    for c in ("ri C:\\x -r -Force", "rm C:\\x -Recurse", "del C:\\x -Recurse", "Remove-Item C:\\x -Rec", "rd C:\\x", "rmdir C:\\x"):
        assert check("PowerShell", c) == "deny", c
    assert check("PowerShell", "Get-Content 'C:\\hard drive.txt'") == "allow"  # alias patterns don't hit inside paths
    assert check("PowerShell", "Get-ChildItem C:\\Users\\x\\Downloads | Select-Object -First 5") == "allow"
    assert check("PowerShell", "Get-Process | Sort-Object WS -Descending | Select-Object -First 3") == "allow"
    assert check("PowerShell", "Get-Process | Stop-Process") == "ask"                      # one segment not allowed
    assert check("PowerShell", "Get-ChildItem | Sort-Object { Remove-Item x }") == "ask"   # script block
    assert check("Open", "C:\\a.pdf") == "ask"
    assert prompt() == "" and add("ตอบสั้นที่สุด") and add("Call me boss") and "- Call me boss" in prompt()
    assert text().startswith("# Rules")
    print("RULES SELFTEST OK")
