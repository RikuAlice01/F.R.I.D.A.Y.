"""Security layers (PLAN §33): Windows Hello for dangerous actions, DPAPI-encrypted secrets, tamper detection of FRIDAY's
own files, safe mode, audit log. Threat model: other accounts / programs editing FRIDAY's files, other people or a TV
speaking commands, text in documents steering the model, data leaving the PC. Malware running as the owner can do
whatever the owner can — that is Windows Defender's job, not this module's."""
import ctypes, datetime, hashlib, json, os, threading
from ctypes import wintypes

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root; code lives in app/
SECRETS = os.environ.get("FRIDAY_SECRETS", os.path.join(ROOT, "config", "secrets.dat"))
BASELINE = os.environ.get("FRIDAY_BASELINE", os.path.join(ROOT, "data", "integrity.dat"))
AUDIT = os.environ.get("FRIDAY_AUDIT", os.path.join(ROOT, "data", "logs", "audit.log"))
_lock = threading.RLock()  # approve() -> set_secret() takes it again


# ---------- DPAPI: only this Windows account on this PC can decrypt ----------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
    src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    entropy = b"FRIDAY-local-assistant"
    ent = _Blob(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy, len(entropy)), ctypes.POINTER(ctypes.c_char)))
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out))  # CRYPTPROTECT_UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI failed (file from another account or PC, or damaged)")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _load(path):
    try:
        with open(path, "rb") as f:
            return json.loads(_dpapi(f.read(), False))
    except FileNotFoundError:
        return {}


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dpapi(json.dumps(obj, ensure_ascii=False).encode(), True))
    os.replace(tmp, path)


def secret(key, default=None):
    return _load(SECRETS).get(key, default)


def set_secret(key, value):
    with _lock:
        s = _load(SECRETS)
        if value is None:
            s.pop(key, None)
        else:
            s[key] = value
        _save(SECRETS, s)


# ---------- Windows Hello ----------
def hello(message):
    """True only when the owner verifies (PIN / fingerprint / face). None when Hello is not set up on this PC."""
    import asyncio
    from winrt.windows.security.credentials.ui import (UserConsentVerifier, UserConsentVerifierAvailability as A,
                                                       UserConsentVerificationResult as R)

    async def go():
        if await UserConsentVerifier.check_availability_async() != A.AVAILABLE:
            return None
        return await UserConsentVerifier.request_verification_async(message[:200]) == R.VERIFIED
    return asyncio.run(go())


# ---------- tamper detection ----------
def _extra():
    """Live permission/rule/skill files wherever FRIDAY_SETTINGS / FRIDAY_VAULT / FRIDAY_SKILLS put them (code review §33)."""
    import rules, skills
    files = [rules.SETTINGS, rules.rules_file()]
    for root, dirs, names in os.walk(skills.DIR):
        files += [os.path.join(root, n) for n in names]
    return files


def watched():
    """FRIDAY's code, launchers, permissions, rules, skills, and the venvs' auto-run hooks (.pth / sitecustomize):
    what an attacker would change to gain power. __pycache__ is not trusted at all: friday.py deletes it at start."""
    files = [os.path.join(ROOT, f) for f in ("friday.cmd", "friday-tray.pyw", os.path.join("config", "settings.json"),
                                              os.path.join("data", "vault", "Rules.md"))]
    for top in ("app", "skills"):
        for root, dirs, names in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            files += [os.path.join(root, n) for n in names if not n.endswith((".pyc", ".tmp"))]
    # §69 FRIDAY.exe: our Python code is inside the exe (PyInstaller's archive); the interpreter beside it.
    # ponytail: not every DLL in _internal (2 GB to hash on each check) — the folder is ACL-locked with the rest (§33)
    dist = os.path.join(ROOT, "dist", "FRIDAY")
    files += [os.path.join(dist, f) for f in ("FRIDAY.exe", os.path.join("_internal", "python311.dll"),
                                              os.path.join("_internal", "base_library.zip"))]
    for venv in (".venv", ".venv-tts"):
        site = os.path.join(ROOT, venv, "Lib", "site-packages")
        if os.path.isdir(site):
            files += [os.path.join(site, n) for n in os.listdir(site) if n.endswith(".pth") or n in ("sitecustomize.py", "usercustomize.py")]
    files += _extra()
    return sorted({os.path.abspath(f) for f in files if os.path.isfile(f)})


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _key(p):
    """Relative to ROOT when inside it, else the absolute path (settings/vault/skills may live elsewhere)."""
    a = os.path.abspath(p)
    return os.path.relpath(a, ROOT) if a.lower().startswith(ROOT.lower() + os.sep) else a


def snapshot():
    return {_key(p): _digest(p) for p in watched()}


def changes():
    """[] when everything matches the approved baseline; else ['changed: app/x.py', 'new: skills/y/SKILL.md', ...].
    First run ever = trust what is there and remember that a baseline exists (in the encrypted secrets): a deleted
    baseline later is reported, not silently re-trusted."""
    base = _load(BASELINE)
    now = snapshot()
    if not base:
        if secret("integrity_baseline"):
            return ["missing: data\\integrity.dat (approved-files list deleted)"]
        _save(BASELINE, now)
        set_secret("integrity_baseline", True)
        return []
    out = [f"changed: {k}" for k in now if k in base and now[k] != base[k]]
    out += [f"new: {k}" for k in now if k not in base] + [f"removed: {k}" for k in base if k not in now]
    return sorted(out)


def approve(snap=None):
    """The owner approved (Windows Hello): the baseline becomes `snap` — the exact state they were shown — or now."""
    with _lock:
        _save(BASELINE, snap if snap is not None else snapshot())
        set_secret("integrity_baseline", True)


def _clean(path, base):
    k = _key(path)
    return (k in base and os.path.isfile(path) and _digest(path) == base[k]) or (k not in base and not os.path.exists(path))


class own_write:
    """with security.own_write(path): <FRIDAY writes path> — the new content is approved only if the file was untouched
    before; a file someone else had changed stays flagged (else a volume change would launder an attacker's edit)."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        base = _load(BASELINE)
        watched_now = os.path.abspath(self.path) in watched()  # a file FRIDAY does not watch (a test's temp settings) is
        self.ok = watched_now and (not base or _clean(self.path, base))  # never added: it would read as "removed" later
        return self

    def __exit__(self, *exc):
        if exc[0] is None and self.ok:
            with _lock:
                base = _load(BASELINE)
                if not base:
                    return
                if os.path.isfile(self.path):
                    base[_key(self.path)] = _digest(self.path)
                else:
                    base.pop(_key(self.path), None)
                _save(BASELINE, base)


# ---------- audit log ----------
def audit(source, tool, args, decision, result=""):
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    line = json.dumps({"t": datetime.datetime.now().isoformat(timespec="seconds"), "src": source, "tool": tool,
                       "args": str(args)[:300], "decision": decision, "result": str(result)[:200]}, ensure_ascii=False)
    with _lock, open(AUDIT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- folder permissions (owner + SYSTEM + Administrators only) ----------
def lock_folder(apply=False):
    """The icacls command that limits ROOT to this account; runs it when apply=True. Old ACL saved for undo."""
    import subprocess
    sid = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip().split(",")[-1].strip('"')
    cmd = ["icacls", ROOT, "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"]
    if apply:
        backup = os.path.join(ROOT, "data", "acl-before-lock.txt")
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        subprocess.run(["icacls", ROOT, "/save", backup], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode, (r.stdout + r.stderr).strip()[-300:]
    return cmd


if __name__ == "__main__":
    import sys, tempfile
    if "--approve" in sys.argv:  # after the owner changed/updated FRIDAY's files on purpose
        print("\n".join(changes()) or "no changes")
        ok = hello("FRIDAY: ยืนยันว่าไฟล์ที่เปลี่ยนเป็นของคุณเอง")
        if ok:
            approve()
        print("approved" if ok else "not approved")
        sys.exit(0 if ok else 1)
    d = tempfile.mkdtemp()
    SECRETS, BASELINE, AUDIT = os.path.join(d, "s.dat"), os.path.join(d, "b.dat"), os.path.join(d, "a.log")
    assert _dpapi(_dpapi(b"hello", True), False) == b"hello"
    set_secret("ha_token", "abc123")
    assert secret("ha_token") == "abc123" and b"abc123" not in open(SECRETS, "rb").read()  # encrypted at rest
    set_secret("ha_token", None)
    assert secret("ha_token") is None
    with open(SECRETS, "wb") as f:
        f.write(b"garbage")
    try:
        secret("x")
        raise AssertionError("tampered secrets must not load")
    except OSError:
        pass
    os.remove(SECRETS)
    # tamper detection on a fake project
    ROOT = os.path.join(d, "proj")
    _extra = lambda: []  # the fake project only
    for rel in ("app/friday.py", "skills/a/SKILL.md", "config/settings.json"):
        os.makedirs(os.path.dirname(os.path.join(ROOT, rel)), exist_ok=True)
        open(os.path.join(ROOT, rel), "w").write("v1")
    assert changes() == []                                   # first run: baseline taken
    open(os.path.join(ROOT, "app", "friday.py"), "w").write("evil")
    open(os.path.join(ROOT, "skills", "a", "run.ps1"), "w").write("Remove-Item C:\\")
    os.remove(os.path.join(ROOT, "config", "settings.json"))
    c = changes()
    assert c == ["changed: app\\friday.py", "new: skills\\a\\run.ps1", "removed: config\\settings.json"], c
    snap = snapshot()
    open(os.path.join(ROOT, "skills", "a", "late.ps1"), "w").write("x")  # appears while the owner is verifying
    approve(snap)                                             # only what was shown is approved
    assert changes() == ["removed: skills\\a\\late.ps1"] or changes() == ["new: skills\\a\\late.ps1"], changes()
    os.remove(os.path.join(ROOT, "skills", "a", "late.ps1"))
    assert changes() == []
    # FRIDAY's own write to a clean file is approved; to a file someone else changed first, it is not (laundering)
    cfg = os.path.join(ROOT, "skills", "a", "SKILL.md")
    with own_write(cfg):
        open(cfg, "w").write("v2 by FRIDAY")
    assert changes() == []
    open(cfg, "w").write("attacker")
    with own_write(cfg):
        open(cfg, "w").write("attacker + FRIDAY volume change")
    assert changes() == ["changed: skills\\a\\SKILL.md"]
    approve()
    # writing a file that is not watched never touches the baseline
    stray = os.path.join(d, "elsewhere.json")
    with own_write(stray):
        open(stray, "w").write("{}")
    os.remove(stray)
    assert changes() == []
    # a deleted baseline is reported, not re-trusted
    os.remove(BASELINE)
    assert changes()[0].startswith("missing:")
    approve()
    assert changes() == []
    audit("voice", "hardware", {"action": "shutdown"}, "denied", "User declined.")
    assert json.loads(open(AUDIT, encoding="utf-8").read())["decision"] == "denied"
    assert lock_folder()[0] == "icacls" and "/inheritance:r" in lock_folder()
    print("SECURITY SELFTEST OK")
