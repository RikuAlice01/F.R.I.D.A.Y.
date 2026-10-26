"""Project spaces (PLAN §102), like Claude Code / Codex: the owner opens a folder and FRIDAY works only inside it —
list, read, search, edit files (diff first) and run commands with the project as the working directory.
Owner: "อ่าน + แก้ไฟล์ + รันคำสั่ง" · "Hello ครั้งเดียวต่อคำสั่ง" (gate in friday.py) · project instructions
(FRIDAY.md / CLAUDE.md / AGENTS.md) "อ่านเลยไม่ถาม" · cloud brain "ถามครั้งเดียวต่อโปรเจกต์".
Every path goes through inside(): realpath under the root (no '..', symlink or junction escape), never .git internals,
never secret files."""
import difflib, fnmatch, os, re, subprocess

IGNORE = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target", ".idea", ".vs",
          ".gradle", ".pytest_cache", ".mypy_cache", "bin", "obj"}
SECRET = re.compile(r"(^|[\\/])(\.env(\..*)?|.*\.(pem|key|pfx|p12|keystore|jks)|id_(rsa|ed25519|ecdsa)(\.pub)?|"
                    r".*secret.*|.*credential.*|secrets\.dat)$", re.I)
INSTRUCTIONS = ("FRIDAY.md", "CLAUDE.md", "AGENTS.md")
MAX_FILES, MAX_READ, MAX_FILE_BYTES, MAX_OUT = 400, 220, 2_000_000, 4000
RUN_TIMEOUT_S = 120

ROOT = None  # the open project (absolute, real path) or None


class OutsideProject(ValueError):
    pass


def _real(p):
    return os.path.normcase(os.path.realpath(p))


def forbidden_root(path):
    """A folder too big to be a project: a drive root, Windows, Program Files, the user's home itself."""
    p = _real(path)
    bad = {_real(os.path.expanduser("~"))}
    for v in ("WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "APPDATA", "LOCALAPPDATA"):
        if os.environ.get(v):
            bad.add(_real(os.environ[v]))
    return os.path.dirname(p) == p or p in bad or any(p.startswith(b + os.sep) for b in bad if "windows" in b or "program" in b)


def open_project(path):
    """-> the real root. ValueError when it isn't a usable folder."""
    global ROOT
    p = os.path.expandvars(os.path.expanduser(str(path).strip().strip('"')))
    if not os.path.isdir(p):
        raise ValueError(f"not a folder: {path}")
    if forbidden_root(p):
        raise ValueError("too wide for a project (a drive root, Windows, Program Files or your home folder)")
    ROOT = os.path.realpath(p)
    return ROOT


def close_project():
    global ROOT
    ROOT = None


def name():
    return os.path.basename(ROOT) if ROOT else ""


def inside(rel):
    """Absolute path of rel inside the project, or OutsideProject."""
    if not ROOT:
        raise OutsideProject("no project is open")
    rel = str(rel or ".").strip().strip('"')
    full = os.path.realpath(rel if os.path.isabs(rel) else os.path.join(ROOT, rel))
    root = _real(ROOT)
    if _real(full) != root and not _real(full).startswith(root + os.sep):
        raise OutsideProject(f"outside the project: {rel}")
    parts = os.path.relpath(full, ROOT).split(os.sep)
    if ".git" in parts:
        raise OutsideProject("FRIDAY does not touch .git internals")
    if SECRET.search(os.path.relpath(full, ROOT)):
        raise OutsideProject(f"secret file, not opened: {os.path.basename(full)}")
    return full


def rel(full):
    return os.path.relpath(full, ROOT).replace(os.sep, "/")


def files(pattern=""):
    """Project files matching pattern (glob like '*.py' or words in the path), ignoring build/vendor folders."""
    root = inside(".")
    pat = str(pattern or "").strip().lower()
    out = []
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in IGNORE and not x.startswith("."))
        for n in sorted(names):
            r = rel(os.path.join(d, n))
            if SECRET.search(r):
                continue
            if pat and not (fnmatch.fnmatch(n.lower(), pat) or fnmatch.fnmatch(r.lower(), pat) or all(w in r.lower() for w in pat.split())):
                continue
            out.append(r)
            if len(out) >= MAX_FILES:
                return out + [f"… (more than {MAX_FILES} — narrow the pattern)"]
    return out


def _decode(full):
    """-> (text, encoding to write it back with): utf-8-sig only when the file had a BOM; Thai TIS-620 stays cp874."""
    if os.path.getsize(full) > MAX_FILE_BYTES:
        raise ValueError("file too large to read (> 2 MB)")
    with open(full, "rb") as f:
        b = f.read()
    if b"\0" in b[:4096]:
        raise ValueError("binary file")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace"), "utf-8-sig"
    for enc in ("utf-8", "cp874", "latin-1"):
        try:
            return b.decode(enc), enc
        except UnicodeDecodeError:
            continue


def _text(full):
    return _decode(full)[0]


def read(path, start=1, count=MAX_READ):
    full = inside(path)
    if os.path.isdir(full):
        return "Folder: " + ", ".join(sorted(os.listdir(full))[:100])
    lines = _text(full).splitlines()
    start = max(1, int(start or 1))
    chunk = lines[start - 1:start - 1 + min(int(count or MAX_READ), MAX_READ)]
    end = start + len(chunk) - 1
    more = f"\n… lines {end + 1}-{len(lines)} not shown: read again with start={end + 1}" if end < len(lines) else ""
    return f"{rel(full)} (lines {start}-{end} of {len(lines)}):\n" + "\n".join(f"{start + i}: {l}" for i, l in enumerate(chunk)) + more


def search(text, pattern=""):
    """Lines containing text (case-insensitive) in project files: 'path:line: content', at most 60."""
    q = str(text).lower()
    if not q.strip():
        raise ValueError("search needs text")
    hits = []
    for r in files(pattern):
        if r.startswith("…"):
            break
        try:
            body = _text(inside(r))
        except (ValueError, OSError, OutsideProject):
            continue
        for i, line in enumerate(body.splitlines(), 1):
            if q in line.lower():
                hits.append(f"{r}:{i}: {line.strip()[:200]}")
                if len(hits) >= 60:
                    return hits + ["… (more — search for something more specific)"]
    return hits


def plan_edit(path, old, new):
    """-> (full path, new text, unified diff). old='' creates a new file; otherwise old must appear exactly once."""
    full = inside(path)
    if os.path.isdir(full):
        raise ValueError("that is a folder")
    exists = os.path.exists(full)
    raw, enc = _decode(full) if exists else ("", "utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"  # Windows files: match on \n (what the model writes), write back with \r\n
    before = raw.replace("\r\n", "\n")
    old, new = str(old).replace("\r\n", "\n"), str(new).replace("\r\n", "\n")
    if old:
        if not exists:
            raise ValueError("file does not exist (use old='' to create it)")
        if before.count(old) == 0 and re.match(r"\s*\d+: ", old):  # copied from project_read with its "N: " line numbers
            old, new = (re.sub(r"(?m)^\s*\d+: ", "", t) for t in (old, new))
        n = before.count(old)
        if n != 1:
            raise ValueError(f"the old text must appear exactly once (found {n}) — include more surrounding lines")
        after = before.replace(old, new, 1)
    else:
        if exists:
            raise ValueError("file already exists — give old text to change it")
        after = new
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{rel(full)}", f"b/{rel(full)}"))
    after = after.replace("\n", nl) if nl != "\n" else after
    try:
        after.encode(enc)
    except UnicodeEncodeError:
        raise ValueError(f"the new text has characters this file's encoding ({enc}) cannot hold")
    return full, (after, enc), diff or "(no change)"


def apply_edit(full, after):
    """after = (text, encoding) from plan_edit."""
    text, enc = after if isinstance(after, tuple) else (after, "utf-8")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    tmp = full + ".friday-tmp"
    with open(tmp, "w", encoding=enc, newline="") as f:
        f.write(text)
    os.replace(tmp, full)


def run(command):
    """PowerShell in the project folder; output (stdout+stderr) cut to MAX_OUT. The gate is in friday.py."""
    root = inside(".")
    nw = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", str(command)], cwd=root,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=nw)
    try:
        out, _ = p.communicate(timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=nw)  # children too
        return f"Stopped: still running after {RUN_TIMEOUT_S} s (long-running commands such as dev servers don't belong here)"
    out = (out or "").strip()
    cut = f"\n… ({len(out) - MAX_OUT} more characters)" if len(out) > MAX_OUT else ""
    return f"exit {p.returncode}\n{out[:MAX_OUT]}{cut}"


def instructions(limit=3000):
    """Project instruction files at the root, read as-is (owner: "อ่านเลยไม่ถาม")."""
    if not ROOT:
        return ""
    parts = []
    for n in INSTRUCTIONS:
        try:
            f = inside(n)
            if os.path.isfile(f):
                parts.append(f"--- {n} ---\n{_text(f)}")
        except (ValueError, OSError, OutsideProject):
            pass
    text = "\n".join(parts)
    return text[:limit] + ("\n… (cut)" if len(text) > limit else "")


if __name__ == "__main__":
    import tempfile
    base = tempfile.mkdtemp()
    proj = os.path.join(base, "demo")
    os.makedirs(os.path.join(proj, "src"))
    os.makedirs(os.path.join(proj, "node_modules", "x"))
    os.makedirs(os.path.join(proj, ".git"))
    open(os.path.join(proj, "src", "app.py"), "w", encoding="utf-8").write("print('hello')\nx = 1\n")
    open(os.path.join(proj, "README.md"), "w", encoding="utf-8").write("# Demo\nสวัสดี\n")
    open(os.path.join(proj, "CLAUDE.md"), "w", encoding="utf-8").write("Use tabs.\n")
    open(os.path.join(proj, ".env"), "w").write("TOKEN=abc\n")
    open(os.path.join(proj, "node_modules", "x", "i.js"), "w").write("x")
    open(os.path.join(proj, ".git", "config"), "w").write("[core]\n")
    open(os.path.join(base, "outside.txt"), "w").write("secret outside")
    assert open_project(proj) == os.path.realpath(proj) and name() == "demo"
    # the fence: .. / absolute / .git / secrets refuse; inside works
    for bad in ("../outside.txt", os.path.join(base, "outside.txt"), ".git/config", ".env", "src/../../outside.txt"):
        try:
            inside(bad)
            raise AssertionError(bad)
        except OutsideProject:
            pass
    assert inside("src/app.py").endswith("app.py")
    # a junction pointing outside is outside (Windows; skipped when mklink isn't allowed)
    j = os.path.join(proj, "link")
    if subprocess.run(["cmd", "/c", "mklink", "/J", j, base], capture_output=True).returncode == 0:
        try:
            inside("link/outside.txt")
            raise AssertionError("junction escape")
        except OutsideProject:
            pass
        os.rmdir(j)
    fs = files()
    assert "src/app.py" in fs and "README.md" in fs and not any("node_modules" in f or ".env" in f or ".git" in f for f in fs), fs
    assert files("*.py") == ["src/app.py"] and files("readme") == ["README.md"]
    assert "2: x = 1" in read("src/app.py") and "สวัสดี" in read("README.md")
    assert search("HELLO") == ["src/app.py:1: print('hello')"]
    full, after, diff = plan_edit("src/app.py", "x = 1", "x = 2")
    assert "-x = 1" in diff and "+x = 2" in diff and open(full).read().count("x = 1") == 1  # nothing written yet
    apply_edit(full, after)
    assert "x = 2" in open(full).read()
    full, after, diff = plan_edit("src/app.py", "2: x = 2", "2: x = 3")  # old copied with read()'s line numbers
    assert "+x = 3" in diff and "2:" not in after, diff
    apply_edit(full, after)
    with open(os.path.join(proj, "win.txt"), "wb") as f:  # a Windows (CRLF) file: the model's \n text still matches
        f.write(b"a = 1\r\nb = 2\r\n")
    full, after, diff = plan_edit("win.txt", "a = 1\nb = 2", "a = 1\nb = 3")
    apply_edit(full, after)
    assert open(full, "rb").read() == b"a = 1\r\nb = 3\r\n", open(full, "rb").read()
    with open(os.path.join(proj, "thai.txt"), "wb") as f:  # TIS-620 and BOM files keep their encoding
        f.write("สวัสดี\n".encode("cp874"))
    with open(os.path.join(proj, "bom.ps1"), "wb") as f:
        f.write(b"\xef\xbb\xbfWrite-Output 1\n")
    full, after, _ = plan_edit("thai.txt", "สวัสดี", "สวัสดีค่ะ")
    apply_edit(full, after)
    assert open(full, "rb").read() == "สวัสดีค่ะ\n".encode("cp874")
    full, after, _ = plan_edit("bom.ps1", "Write-Output 1", "Write-Output 2")
    apply_edit(full, after)
    assert open(full, "rb").read() == b"\xef\xbb\xbfWrite-Output 2\n"
    # a project whose own folder name says "secret" still works; its secret files still don't
    sp = os.path.join(base, "secret-santa")
    os.makedirs(sp)
    open(os.path.join(sp, "a.txt"), "w").write("x")
    open_project(sp)
    assert files() == ["a.txt"] and inside("a.txt")
    open_project(proj)
    # a command that outlives the timeout is stopped with its children
    RUN_TIMEOUT_S, keep = 2, RUN_TIMEOUT_S
    assert run("Start-Sleep 30").startswith("Stopped"), "timeout"
    RUN_TIMEOUT_S = keep
    try:
        plan_edit("src/app.py", "nothing like this", "y")
        raise AssertionError("missing old text")
    except ValueError:
        pass
    full, after, diff = plan_edit("docs/new.md", "", "hi\n")
    apply_edit(full, after)
    assert os.path.exists(os.path.join(proj, "docs", "new.md"))
    out = run("(Get-Location).Path")
    assert out.startswith("exit 0") and os.path.realpath(proj).lower() in out.lower(), out
    assert "Use tabs." in instructions()
    for wide in (os.path.splitdrive(proj)[0] + "\\", os.path.expanduser("~"), os.environ.get("WINDIR", "C:\\Windows")):
        try:
            open_project(wide)
            raise AssertionError(wide)
        except ValueError:
            pass
    close_project()
    try:
        files()
        raise AssertionError("closed")
    except OutsideProject:
        pass
    print("PROJECT SELFTEST OK")
