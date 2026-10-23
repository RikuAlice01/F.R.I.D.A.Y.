"""FRIDAY long-term memory as an Obsidian vault: <vault>/Memory/<Category>/<Sub>.md, one fact per "- " line.

Only Core.md and the category index go into every prompt; the LLM opens other notes with recall/search_docs
and follows [[links]] between them, so a question never needs the whole memory in context.
"""
import os, re

VAULT = os.environ.get("FRIDAY_VAULT", os.path.join(os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vault"))
CORE = "Core"       # always in the prompt: identity, language, key preferences
CORE_MAX = 8
NOTE_MAX = 30       # facts per note; beyond this the LLM must use a sub-category
INDEX_MAX = 150     # notes listed in the prompt
DEPTH_MAX = 4
OUT_MAX = 2500      # chars per tool result (8K context)

INSTRUCTIONS = """Long-term memory is an Obsidian vault of category notes (index below; number = facts in note).
- The index shows only note NAMES. Notes that look relevant to the current message are attached automatically under
  "Relevant notes"; for anything else about the user, their people, projects, preferences, health or history, call recall
  on the relevant note(s) (or search_docs) BEFORE answering, and answer only from notes you have seen.
  If nothing is found, say you don't know yet. Never guess facts about the user. (General knowledge needs no notes.)
  For broad or multi-part questions, look things up step by step: recall a note, then follow its [[links]] and "Linked from" notes.
- When the user tells you lasting facts/preferences, or asks you to remember: call remember ONCE with every fact as its own item,
  each filed under its own most specific category: "Health/<Topic>", "Preferences/<Topic>", "Work/Projects/<Project>",
  "People/<Person>", "Places/<Place>", ... "Core" is ONLY for name, nickname and how to address the user.
  Prefer existing categories from the index; create a sub-category instead of letting one note grow large.
  Write each fact in the language the user spoke, in third person ("ผู้ใช้...", "User ...", or the person's name),
  and link related notes with [[<Note>]]
  (format only: "<Person> is User's <relation>; works on [[<Project>]]").
- Facts describe the USER: answer with "you/คุณ", never as if they were about yourself.
- forget when the user asks you to forget something.
Core facts:
{core}
Memory index:
{index}"""

TOOLS = [
    {"type": "function", "function": {
        "name": "remember", "description": "Save lasting facts about the user. Each item = one short third-person fact + its own category note.",
        "parameters": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
            "category": {"type": "string", "description": "Most specific category path, e.g. 'Health/Allergies', 'Work/Projects/SEDA', 'People/Mint'"},
            "fact": {"type": "string"}}, "required": ["category", "fact"]}}}, "required": ["items"]}}},
    {"type": "function", "function": {
        "name": "recall", "description": "Read one memory note (or list a category folder) from the index. Also accepts a [[link]] target.",
        "parameters": {"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]}}},
    {"type": "function", "function": {
        "name": "forget", "description": "Delete remembered facts that contain the given text (in all notes).",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
]


def root():
    return os.path.join(VAULT, "Memory")


def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)).strip()


def _link_target(link):
    """'Work/SEDA#Roadmap|the app' / 'SEDA.md' / 'SEDA#^block' -> 'Work/SEDA' / 'SEDA' (Obsidian link syntax)."""
    return re.split(r"[#|]", link)[0].strip().removesuffix(".md")


def _name(category):
    """'Work/Projects/SEDA' -> safe relative name; never escapes the Memory folder."""
    category = _link_target(re.sub(r"^\[\[|\]\]$", "", category.strip()))  # accept [[Link#Heading|alias]] and .md
    parts = [re.sub(r'[<>:"|?*#^\[\]\x00-\x1f]', "", p).strip(" .") for p in re.split(r"[\\/]+", category)]
    parts = [p for p in parts if p][:DEPTH_MAX]
    if parts and parts[0].lower() == "memory":
        parts = parts[1:]
    return "/".join(parts) or CORE


def _path(name):
    return os.path.join(root(), *name.split("/")) + ".md"


def _notes():
    """{name: path} for every note, e.g. {'Work/Projects/SEDA': '...\\SEDA.md'}."""
    out = {}
    for dirpath, _, files in os.walk(root()):
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(dirpath, f)
                out[os.path.relpath(p, root())[:-3].replace(os.sep, "/")] = p
    return out


def _matches(name):
    """Exact path, else Obsidian-style suffix matches ([[SEDA]] -> Work/Projects/SEDA)."""
    notes = _notes()
    if name in notes:
        return [name]
    return sorted(n for n in notes if n.lower() == name.lower() or n.lower().endswith("/" + name.lower()))


def _resolve(name):
    hits = _matches(name)
    return hits[0] if len(hits) == 1 else None  # ambiguous ([[Mint]] in People/ and Pets/) -> caller must be specific


def _read(name):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []


def _write(name, lines):
    p = _path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    os.replace(p + ".tmp", p)  # atomic: a crash mid-write never corrupts a note


def _facts(lines):
    return [l[2:].strip() for l in lines if l.startswith(("- ", "* ")) and l[2:].strip()]


def names():
    return sorted(n for n in _notes() if n != CORE)


def prompt():
    notes = sorted(n for n in _notes() if n != CORE)
    index = "\n".join(f"- {n} ({len(_facts(_read(n)))})" for n in notes[:INDEX_MAX]) or "(empty)"
    if len(notes) > INDEX_MAX:
        index += f"\n... {len(notes) - INDEX_MAX} more notes, use search_docs"
    core = "\n".join(f"- {f}" for f in _facts(_read(CORE))) or "(nothing yet)"
    return INSTRUCTIONS.format(core=core, index=index)


def remember(items):
    groups = {}
    for it in items:
        if isinstance(it, dict) and str(it.get("fact", "")).strip():
            groups.setdefault(str(it.get("category") or CORE), []).append(str(it["fact"]))
    return "\n".join(remember_in(c, f) for c, f in groups.items()) or "No facts given."


def remember_in(category, facts):
    asked = _name(category)
    if asked != CORE and "/" not in asked:  # checked before resolving, so a bare 'Mint' can't slip past via [[Mint]] lookup
        return f"'{asked}' is too broad. Use '{asked}/<topic>' (e.g. '{asked}/<specific subject>') and call remember again."
    name = _resolve(asked) or asked
    new = [_clean(f) for f in ([facts] if isinstance(facts, str) else facts)]
    lines = _read(name) or [f"# {name.split('/')[-1]}", ""]
    known = set(_facts(lines))
    new = [f for f in new if f and f not in known]
    limit = CORE_MAX if name == CORE else NOTE_MAX
    if len(known) + len(new) > limit:
        return (f"Note '{name}' is full ({len(known)} facts). Save these under a more specific sub-category, "
                f"e.g. '{name}/<topic>', or under another category.")
    _write(name, lines + [f"- {f}" for f in new])
    return f"Saved to {name}: " + "; ".join(new) if new else f"Already known in {name}."


def recall(category):
    name = category if category in _notes() else _name(category)  # exact names from names() skip sanitizing
    hits = _matches(name)
    if len(hits) > 1:
        return f"'{name}' is ambiguous, recall one of: " + ", ".join(hits)
    found = hits[0] if hits else None
    if found:
        return (f"[{found}]\n" + "\n".join(_read(found)) + backlinks(found))[:OUT_MAX]
    folder = os.path.join(root(), *name.split("/"))
    if os.path.isdir(folder):
        kids = sorted(n for n in _notes() if n.lower().startswith(name.lower() + "/"))
        return f"Category {name} contains notes: " + ", ".join(kids)
    return f"No note '{name}'. Check the index or use search_docs."


def backlinks(name):
    """Facts in other notes that link here ([[SEDA]] or [[Work/Projects/SEDA|alias]]), like Obsidian's backlinks pane."""
    targets = {name.lower(), name.split("/")[-1].lower()}
    hits = [f"[{n}] {f}" for n in _notes() if n != name for f in _facts(_read(n))
            if any(_link_target(t).lower() in targets for t in re.findall(r"\[\[([^\]]+)\]\]", f))]
    return "\nLinked from:\n" + "\n".join(hits) if hits else ""


def forget(text):
    text, removed = text.lower().strip(), 0
    if not text:
        return "Nothing to forget."
    for name in _notes():
        lines = _read(name)
        keep = [l for l in lines if not (l.startswith(("- ", "* ")) and text in l.lower())]
        if len(keep) != len(lines):
            removed += len(lines) - len(keep)
            _write(name, keep)
    return f"Forgot {removed} fact(s)."


HANDLERS = {"remember": remember, "recall": recall, "forget": forget}


if __name__ == "__main__":
    import tempfile
    VAULT = tempfile.mkdtemp()
    assert _name("..\\..\\Windows/System32") == "Windows/System32" and _name("[[SEDA|x]]") == "SEDA"
    assert _name("Memory/Core.md") == "Core" and _path("a/b").startswith(root())
    print(remember([{"category": "Core", "fact": "User's name is Ton"},
                    {"category": "Work/Projects/SEDA", "fact": "SEDA is a solar dashboard"},
                    {"category": "Work/Projects/SEDA", "fact": "Ton is lead dev of SEDA"},
                    {"category": "Preferences/Food", "fact": "Likes black coffee"},
                    {"category": "Preferences/Food", "fact": "Allergic to shrimp, see [[SEDA]]"}]))
    _write("Preferences/Food", _read("Preferences/Food") + ["", "my own note [[Link]]"])  # user edit in Obsidian
    assert "full" in remember_in("Core", [f"x{i}" for i in range(CORE_MAX)])
    assert recall("[[SEDA]]").startswith("[Work/Projects/SEDA]") and "SEDA" in recall("Work")
    assert "Linked from:\n[Preferences/Food] Allergic to shrimp" in recall("SEDA")
    # review findings: heading/alias/.md links, ambiguous short names, bare category via resolve
    remember([{"category": "People/Ton", "fact": "Ton plans the [[SEDA#Roadmap|roadmap]] and reads [[SEDA.md]]"},
              {"category": "Pets/Mint", "fact": "Mint is a cat"}, {"category": "People/Mint", "fact": "Mint is a doctor"}])
    assert recall("[[SEDA#Roadmap]]").startswith("[Work/Projects/SEDA]") and "[People/Ton]" in recall("SEDA")
    assert "ambiguous" in recall("Mint") and "cat" in recall("Pets/Mint")
    assert "too broad" in remember([{"category": "Mint", "fact": "x"}])
    assert forget("coffee") == "Forgot 1 fact(s)." and "[[Link]]" in recall("Preferences/Food")
    p = prompt()
    assert "User's name is Ton" in p and "Work/Projects/SEDA (2)" in p and "solar" not in p
    print(p)
    print("MEMORY SELFTEST OK")
