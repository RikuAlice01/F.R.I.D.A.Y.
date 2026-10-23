"""Chat sessions: one main session, sub-sessions (branch off the current one, inheriting its recent context) and
clones (full independent copy). Each session is sessions/<id>.json; the active one's messages live in a list the
caller keeps a reference to (`self.history`), so switching replaces its contents in place.
"""
import datetime, json, os, re

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root; code lives in app/
DIR = os.environ.get("FRIDAY_SESSIONS", os.path.join(ROOT, "data", "sessions"))
MAIN = "main"
SUB_CONTEXT = 6  # parent messages (user/assistant only) a sub-session starts with


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _chat_only(msgs):
    """user/assistant text messages only: tool_calls/tool results can't be cut without breaking their pairing."""
    return [{"role": m["role"], "content": m["content"]} for m in msgs
            if m.get("role") in ("user", "assistant") and m.get("content") and not m.get("tool_calls")]


class Sessions:
    def __init__(self):
        os.makedirs(DIR, exist_ok=True)
        self.meta = {}  # id -> {id, title, parent, created, updated, kind}
        for f in os.listdir(DIR):
            if f.endswith(".json"):
                try:
                    s = self._read(f[:-5])
                    self.meta[s["id"]] = {k: s.get(k) for k in ("id", "title", "parent", "created", "updated", "kind", "summary", "summarized", "cleared_at")}
                except (OSError, ValueError, KeyError):
                    pass  # a broken file must not stop FRIDAY; it stays on disk for the user to inspect
        if MAIN not in self.meta:
            self._write({"id": MAIN, "title": "หลัก", "parent": None, "kind": "main", "created": _now(),
                         "updated": _now(), "messages": []})
        self.current = MAIN
        self.history = list(self._read(MAIN)["messages"])

    # ---------- storage ----------
    def _path(self, sid):
        return os.path.join(DIR, sid + ".json")

    def _read(self, sid):
        with open(self._path(sid), encoding="utf-8") as f:
            return json.load(f)

    def _write(self, s):
        tmp = self._path(s["id"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path(s["id"]))  # atomic: a crash never leaves a half-written session
        self.meta[s["id"]] = {k: s.get(k) for k in ("id", "title", "parent", "created", "updated", "kind", "summary", "summarized", "cleared_at")}

    def save(self):
        s = dict(self.meta[self.current], messages=self.history, updated=_now())
        self._write(s)

    def _new_id(self):
        base = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        sid, n = base, 1
        while sid in self.meta:
            n += 1
            sid = f"{base}-{n}"
        return sid

    # ---------- operations ----------
    def _create(self, title, kind, messages):
        self.save()
        sid = self._new_id()
        self._write({"id": sid, "title": title, "parent": self.current, "kind": kind,
                     "created": _now(), "updated": _now(), "messages": messages})
        return self.switch(sid)

    def sub(self, title=""):
        """Branch for a side topic: starts with the parent's last few chat messages as context."""
        parent = self.meta[self.current]["title"]
        return self._create(title.strip() or f"ย่อยของ {parent}", "sub", _chat_only(self.history)[-SUB_CONTEXT:])

    def clone(self, title=""):
        """Independent full copy of the current session (tool messages included)."""
        return self._create(title.strip() or f"{self.meta[self.current]['title']} (สำเนา)", "clone",
                            json.loads(json.dumps(self.history)))

    def switch(self, sid):
        sid = self.resolve(sid)
        if sid is None:
            return None
        if sid != self.current:
            self.save()
            self.current = sid
            self.history[:] = self._read(sid)["messages"]  # in place: callers hold this list
        return sid

    def main(self):
        return self.switch(MAIN)

    def rename(self, title):
        if title.strip():
            self.meta[self.current]["title"] = title.strip()
            self.save()

    def resolve(self, key):
        """id, exact title, or 1-based number from tree()."""
        key = str(key).strip()
        if key in self.meta:
            return key
        rows = self.tree()
        if key.isdigit() and 1 <= int(key) <= len(rows):
            return rows[int(key) - 1]["id"]
        hits = [m["id"] for m in self.meta.values() if (m["title"] or "").lower() == key.lower()]
        return hits[0] if len(hits) == 1 else None

    def tree(self):
        """Depth-first list: main first, children under their parent, newest last."""
        kids = {}
        for m in self.meta.values():
            kids.setdefault(m["parent"], []).append(m)
        out = []

        def walk(pid, depth):
            for m in sorted(kids.get(pid, []), key=lambda m: m["created"] or ""):
                out.append({"id": m["id"], "title": m["title"], "kind": m["kind"], "depth": depth,
                            "current": m["id"] == self.current})
                walk(m["id"], depth + 1)
        walk(None, 0)
        seen = {r["id"] for r in out}  # sessions whose parent file was deleted: show them at top level
        for m in self.meta.values():
            if m["id"] not in seen:
                out.append({"id": m["id"], "title": m["title"], "kind": m["kind"], "depth": 0,
                            "current": m["id"] == self.current})
        return out

    def describe(self):
        return "\n".join(f"{i}. {'  ' * r['depth']}{'▶ ' if r['current'] else ''}{r['title']} [{r['kind']}]"
                         for i, r in enumerate(self.tree(), 1))

    def preview(self, n=20):
        return self.page(0, n)[0]

    def page(self, have, n=20):
        """Chat messages before the `have` newest ones, n at a time, oldest first -> (messages, more_older_left)."""
        chat = _chat_only(self.history)
        end = len(chat) - have
        rows = chat[max(0, end - n):max(0, end)]
        return [{"role": m["role"], "text": m["content"]} for m in rows], end - n > 0


if __name__ == "__main__":
    import tempfile
    DIR = tempfile.mkdtemp()
    s = Sessions()
    h = s.history
    h += [{"role": "user", "content": "สวัสดี"}, {"role": "assistant", "content": "สวัสดีค่ะ"},
          {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x"}}]},
          {"role": "tool", "tool_name": "x", "content": "ok"}]
    s.save()
    sub = s.sub("งาน SEDA")
    assert s.current == sub and s.history is h and h == [{"role": "user", "content": "สวัสดี"}, {"role": "assistant", "content": "สวัสดีค่ะ"}]
    h.append({"role": "user", "content": "เรื่องย่อย"})
    s.save()
    s.main()
    assert len(h) == 4 and s.current == MAIN
    c = s.clone()
    assert len(h) == 4 and s.meta[c]["parent"] == MAIN and s.meta[c]["kind"] == "clone"
    h.append({"role": "user", "content": "เฉพาะสำเนา"})
    s.save()
    s.switch("1")
    assert len(h) == 4  # main untouched by the clone's new message
    rows = s.tree()
    assert [r["depth"] for r in rows] == [0, 1, 1] and rows[0]["current"]
    assert s.switch("งาน SEDA") == sub and h[-1]["content"] == "เรื่องย่อย"
    s.history[:] = [{"role": "user", "content": str(i)} for i in range(45)]
    p1, m1 = s.page(0, 20); p2, m2 = s.page(20, 20); p3, m3 = s.page(40, 20)
    assert [x["text"] for x in p1] == [str(i) for i in range(25, 45)] and m1 and m2 and not m3
    assert p2[0]["text"] == "5" and [x["text"] for x in p3] == ["0", "1", "2", "3", "4"] and s.page(45, 20) == ([], False)
    s.switch(sub)
    s2 = Sessions()  # reload from disk
    assert len(s2.meta) == 3 and s2.current == MAIN and len(s2.history) == 4
    open(os.path.join(DIR, "broken.json"), "w").write("{")
    assert len(Sessions().meta) == 3
    print(s.describe())
    print("SESSIONS SELFTEST OK")
