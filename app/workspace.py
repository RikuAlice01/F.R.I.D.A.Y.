"""'เปิดหน้าต่างทำงาน' (PLAN §42): VS Code's last project + the last YouTube song, found on this PC only.
Read-only: VS Code's own storage.json, and a temp copy of each browser's History database (the browser keeps it locked).
Opening them goes through friday.py (permissions, safe mode, audit)."""
import glob, json, os, re, shutil, sqlite3, subprocess, tempfile, urllib.parse

APPDATA, LOCAL = os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")
VSCODE_STATE = os.path.join(APPDATA, "Code", "User", "globalStorage", "storage.json")
CODE_EXE = os.path.join(LOCAL, "Programs", "Microsoft VS Code", "Code.exe")
BROWSERS = {"Chrome": r"Google\Chrome\User Data", "Edge": r"Microsoft\Edge\User Data", "Brave": r"BraveSoftware\Brave-Browser\User Data"}


def code_env(env=None):
    """Environment for starting VS Code. FRIDAY started from inside VS Code inherits ELECTRON_RUN_AS_NODE=1 (and
    VSCODE_*): Code.exe then runs as plain Node and exits — no window (owner: "vscode ไม่เปิด app", §42)."""
    return {k: v for k, v in (env if env is not None else os.environ).items()
            if k != "ELECTRON_RUN_AS_NODE" and not k.startswith(("VSCODE_", "ELECTRON_"))}


def _uri_path(uri):
    """file:///e%3A/friday -> E:\\friday"""
    p = urllib.parse.unquote(urllib.parse.urlsplit(uri).path).lstrip("/")
    return os.path.normpath(p[0].upper() + p[1:]) if len(p) > 1 and p[1] == ":" else os.path.normpath(p)


def last_vscode_project(state=None):
    """The folder (or .code-workspace) of VS Code's last active window, or None."""
    try:
        with open(state or VSCODE_STATE, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return None
    w = s.get("windowsState", {}).get("lastActiveWindow", {})
    uri = w.get("folder") or (w.get("workspace") or {}).get("configPath")
    if not uri:
        folders = s.get("backupWorkspaces", {}).get("folders", [])
        uri = folders[0].get("folderUri") if folders else None
    return _uri_path(uri) if uri else None


def _history_files():
    for name, rel in BROWSERS.items():
        for h in glob.glob(os.path.join(LOCAL, rel, "*", "History")):  # Default, Profile 1, ...
            yield name, h


def last_youtube_song(histories=None):
    """(url, title, browser) of the newest YouTube Music watch page; else the newest YouTube video; else None."""
    best = {}  # kind -> (time, url, title, browser)
    for browser, path in histories if histories is not None else _history_files():
        tmp = os.path.join(tempfile.mkdtemp(), "History")
        try:
            shutil.copy2(path, tmp)  # the browser holds a lock on the live file
            with sqlite3.connect(f"file:{tmp}?mode=ro", uri=True) as db:
                for kind, like in (("music", "https://music.youtube.com/watch%"), ("video", "https://www.youtube.com/watch%")):
                    row = db.execute("SELECT last_visit_time, url, title FROM urls WHERE url LIKE ? ORDER BY last_visit_time DESC LIMIT 1",
                                     (like,)).fetchone()
                    if row and (kind not in best or row[0] > best[kind][0]):
                        best[kind] = (row[0], row[1], row[2], browser)
        except (OSError, sqlite3.Error):
            continue
        finally:
            shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    hit = best.get("music") or best.get("video")
    return (hit[1], hit[2], hit[3]) if hit else None


# §62 read-only git. A repo's own config can run programs (core.fsmonitor on status, diff.external / textconv on
# diff, gpg.program with log.showSignature, filter.*.clean via .gitattributes): the known ones are turned off on every
# call, and a repo whose .git/config has any program-running setting is not touched at all (review §66).
# Fixed argument lists only — nothing from the user or the model reaches git.
GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=NUL", "-c", "diff.external=", "-c", "log.showSignature=false",
       "--no-pager"]
RISKY_GIT = re.compile(r"^\s*\[\s*(?:include|includeif|filter|gpg|credential|alias)\b|^\s*(?:fsmonitor|showsignature|textconv|external|"
                       r"sshcommand|askpass|pager|editor|hookspath|program|clean|smudge|process)\s*=", re.I | re.M)


def _git_config(path):
    """Text of the repo's own config ('' if none). A .git *file* (worktree/submodule) points at the real git dir."""
    g = os.path.join(path, ".git")
    try:
        if os.path.isfile(g):
            with open(g, encoding="utf-8", errors="replace") as f:
                g = os.path.join(path, f.read().split("gitdir:", 1)[1].strip())
        with open(os.path.join(g, "config"), encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IndexError):
        return ""


def _git(path, *args):
    r = subprocess.run(GIT + ["-C", path, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"git exit {r.returncode}")
    return r.stdout


def git_report(path):
    """Thai: branch, changed files (up to 8), last 3 commits. The first line is the spoken one."""
    name = os.path.basename(os.path.normpath(path))
    if RISKY_GIT.search(_git_config(path)):
        return f"ไม่อ่าน git ของ {name} ค่ะ — ตั้งค่าใน .git/config สั่งรันโปรแกรมได้ (เปิดดูเองใน VS Code)"
    try:
        st = _git(path, "status", "--porcelain=v1", "-b", "--untracked-files=normal").splitlines()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        return f"อ่าน git ของ {name} ไม่ได้ค่ะ ({e})"
    head = st[0][3:] if st and st[0].startswith("## ") else "?"
    branch = head.split("...")[0].replace("No commits yet on ", "")
    ahead = " ".join(f"{'ยังไม่ push' if k == 'ahead' else 'ตามหลัง'} {n}" for k, n in re.findall(r"(ahead|behind) (\d+)", head))
    ahead += " สาขาบน remote ถูกลบแล้ว" if "[gone]" in head else ""
    files = [l for l in st[1:] if l.strip()]
    kind = lambda c: "ใหม่" if c == "??" else "ลบ" if "D" in c else "เพิ่ม" if "A" in c else "แก้"
    rows = [f"- {kind(l[:2])}: {l[3:]}" for l in files[:8]] + ([f"- …อีก {len(files) - 8} ไฟล์"] if len(files) > 8 else [])
    try:
        log = _git(path, "log", "-3", "--format=%h %s (%ad)", "--date=format:%d/%m %H:%M").strip().splitlines()
    except (RuntimeError, subprocess.TimeoutExpired):
        log = []  # no commits yet
    first = (f"โปรเจกต์ {name} อยู่ branch {branch}" + (f" ({ahead})" if ahead else "") +
             (f" มีไฟล์เปลี่ยน {len(files)} ไฟล์ที่ยังไม่ commit" if files else " ไม่มีไฟล์ค้าง commit"))
    out = [first] + rows
    if log:
        out += ["", "commit ล่าสุด:"] + [f"- {l}" for l in log]
    return "\n".join(out)


if __name__ == "__main__":
    d = tempfile.mkdtemp()
    st = os.path.join(d, "storage.json")
    json.dump({"windowsState": {"lastActiveWindow": {"folder": "file:///e%3A/my%20project"}}}, open(st, "w"))
    assert last_vscode_project(st) == os.path.normpath("E:/my project"), last_vscode_project(st)
    json.dump({"backupWorkspaces": {"folders": [{"folderUri": "file:///c%3A/code/app"}]}}, open(st, "w"))
    assert last_vscode_project(st) == os.path.normpath("C:/code/app")
    assert last_vscode_project(os.path.join(d, "missing.json")) is None
    # two fake browser histories: the newest music page wins over a newer plain video
    def hist(name, rows):
        p = os.path.join(d, name)
        with sqlite3.connect(p) as db:
            db.execute("CREATE TABLE urls (url TEXT, title TEXT, last_visit_time INTEGER)")
            db.executemany("INSERT INTO urls VALUES (?,?,?)", rows)
        return p
    a = hist("a", [("https://music.youtube.com/watch?v=OLD", "old song", 100), ("https://www.youtube.com/watch?v=VID", "video", 900)])
    b = hist("b", [("https://music.youtube.com/watch?v=NEW", "new song", 500), ("https://example.com/", "x", 999)])
    assert last_youtube_song([("A", a), ("B", b)]) == ("https://music.youtube.com/watch?v=NEW", "new song", "B")
    c = hist("c", [("https://www.youtube.com/watch?v=ONLY", "only video", 5)])
    assert last_youtube_song([("C", c)])[0].endswith("ONLY") and last_youtube_song([]) is None
    assert last_youtube_song([("X", os.path.join(d, "nope"))]) is None
    e = code_env({"PATH": "x", "ELECTRON_RUN_AS_NODE": "1", "VSCODE_PID": "1", "VSCODE_IPC_HOOK": "y", "HOME": "z"})
    assert e == {"PATH": "x", "HOME": "z"}, e
    # §62 a throw-away repo: branch, new/changed files, commits; a non-repo folder says so
    g = os.path.join(d, "repo")
    os.makedirs(g)
    run = lambda *a: subprocess.run(["git", "-C", g, *a], capture_output=True, check=True)
    run("init", "-b", "main")
    open(os.path.join(g, "a.txt"), "w").write("1")
    run("add", "a.txt")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "first commit")
    open(os.path.join(g, "a.txt"), "w").write("2")
    open(os.path.join(g, "b.txt"), "w").write("x")
    rep = git_report(g)
    assert rep.startswith("โปรเจกต์ repo อยู่ branch main มีไฟล์เปลี่ยน 2 ไฟล์") and "- แก้: a.txt" in rep and "- ใหม่: b.txt" in rep, rep
    assert "first commit" in rep, rep
    assert git_report(d).startswith("อ่าน git ของ"), git_report(d)
    with open(os.path.join(g, ".git", "config"), "a") as f:
        f.write("[log]\n\tshowSignature = true\n[gpg]\n\tprogram = C:/evil.exe\n")
    assert git_report(g).startswith("ไม่อ่าน git"), git_report(g)  # a program-running repo config: git never runs
    assert not RISKY_GIT.search('[core]\n\trepositoryformatversion = 0\n\tbare = false\n[remote "origin"]\n\turl = x\n'
                                '[branch "main"]\n\tremote = origin\n')
    # real PC, read-only (prints only what would open)
    print("VS Code:", last_vscode_project(), "| exists:", os.path.isfile(CODE_EXE))
    song = last_youtube_song()
    print("YouTube:", (song[2], song[0][:60]) if song else None)
    print("WORKSPACE SELFTEST OK")
