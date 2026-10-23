"""FRIDAY's brain switch (PLAN §84): the model that thinks, answers, calls tools and looks at the screen.

Who FRIDAY is (system prompt), what she remembers (vault notes), rules, sessions and every safety gate stay in
friday.py on this PC — only the model behind chat() changes. Providers:
  ollama     a model on this PC (default qwen3.5:4b) — nothing leaves the PC
  anthropic  Claude through the Anthropic API (brain_claude.py)       — API key in DPAPI secrets
  openai     OpenAI chat models (brain_openai.py)                     — API key in DPAPI secrets
Messages go in and come out in Ollama's shape ({"role", "content", "tool_calls", "images"}); each cloud adapter
converts. A cloud failure (no internet, no credit, wrong key) answers with the local model instead and says why.
"""
import json, os, threading, time

import requests

import rules, security

OLLAMA = os.environ.get("FRIDAY_OLLAMA", "http://127.0.0.1:11434")
LOCAL = os.environ.get("FRIDAY_MODEL", "qwen3.5:4b")
NAMES = {"ollama": "ในเครื่อง", "anthropic": "Claude", "openai": "OpenAI"}
KEY = {"anthropic": "anthropic_api_key", "openai": "openai_api_key"}  # DPAPI secret names — never settings.json
COOLDOWN_S = 60  # after a cloud failure, use the local model this long before trying the cloud again
_down = {}  # provider -> (until, reason)
_models = {}  # provider -> (time, [ids])


def current():
    """(provider, model) from settings.json "brain" — default the local model."""
    b = rules.settings().get("brain") or {}
    p = b.get("provider") if b.get("provider") in NAMES else "ollama"
    return p, b.get("model") or (LOCAL if p == "ollama" else "")


def is_cloud():
    return current()[0] != "ollama"


def label(provider=None, model=None):
    p, m = (provider, model) if provider else current()
    return f"{'☁ ' if p != 'ollama' else ''}{NAMES[p]} · {m}"


DEFAULT = {"anthropic": "claude-opus-5-5"}  # OpenAI: picked from its list (no safe default name)


def set_brain(provider, model):
    last = dict(rules.settings().get("brain_last") or {}, **{provider: model})
    with security.own_write(rules.SETTINGS):
        rules.set_setting("brain", {"provider": provider, "model": model})
        rules.set_setting("brain_last", last)


def model_for(provider):
    """The model to use when switching to `provider` by name: the one used last, else a default, else its first chat model."""
    if provider == "ollama":
        return (rules.settings().get("brain_last") or {}).get("ollama") or LOCAL
    last = (rules.settings().get("brain_last") or {}).get(provider)
    if last:
        return last
    if provider in DEFAULT:
        return DEFAULT[provider]
    ids = [i for i in models(provider) if i.startswith("gpt-")]
    return ids[-1] if ids else ""


def key(provider):
    return security.secret(KEY[provider]) if provider in KEY else None


def set_key(provider, value):
    security.set_secret(KEY[provider], value or None)
    _models.pop(provider, None)


def models(provider, refresh=False, wait=True):
    """Model ids this provider offers now (cached 10 min; [] when unreachable or no key). wait=False (the tray menu)
    never blocks: it returns what is cached and refreshes in the background."""
    hit = _models.get(provider)
    if hit and not refresh and time.time() - hit[0] < 600:
        return hit[1]
    if not wait:
        threading.Thread(target=models, args=(provider, True), daemon=True).start()
        return hit[1] if hit else []
    try:
        if provider == "ollama":
            ids = sorted(m["name"] for m in requests.get(f"{OLLAMA}/api/tags", timeout=5).json().get("models", [])
                         if not any(w in m["name"].lower() for w in ("embed", "bge", "minilm", "rerank", "nomic")))
        elif not key(provider):
            ids = []
        elif provider == "anthropic":
            import brain_claude
            ids = brain_claude.models(key(provider))
        else:
            import brain_openai
            ids = brain_openai.models(key(provider))
    except Exception:
        _models[provider] = (time.time() - 570, hit[1] if hit else [])  # retry in 30 s, keep the last good list
        return _models[provider][1]
    _models[provider] = (time.time(), ids)
    return ids


def clean(messages):
    """What any provider may see: no private bookkeeping keys (raw cloud blocks travel only inside one turn)."""
    return [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]


def _ollama(model, messages, tools, schema, temperature, max_tokens):
    body = {"model": model, "messages": clean(messages), "stream": False, "think": False,
            "options": {"temperature": temperature} | ({"num_predict": max_tokens} if max_tokens else {})}
    if tools:
        body["tools"] = tools
    if schema:
        body["format"] = schema
    r = requests.post(f"{OLLAMA}/api/chat", timeout=300, json=body)
    r.raise_for_status()
    return r.json()["message"]


def chat(messages, tools=None, schema=None, temperature=0.3, max_tokens=None, source="typed"):
    """One model call. Returns an Ollama-shaped assistant message; "tool_calls" carry an "id"; a cloud answer
    also carries "_raw" (that provider's own blocks, sent back unchanged within the same turn) and a failed cloud
    call "_fallback" (why the local model answered instead)."""
    provider, model = current()
    if provider != "ollama":
        until, why = _down.get(provider, (0, ""))
        if time.time() >= until:
            try:
                k = key(provider)
                if not k:
                    raise PermissionError("ยังไม่ได้ใส่ API key")
                if provider == "anthropic":
                    import brain_claude
                    msg = brain_claude.chat(k, model, messages, tools, schema, max_tokens or 8000)
                else:
                    import brain_openai
                    msg = brain_openai.chat(k, model, messages, tools, schema, max_tokens or 8000)
                security.audit(source, "brain_cloud", f"{provider}:{model}", "done", f"{len(messages)} messages")
                _down.pop(provider, None)
                return msg
            except Exception as e:
                why = reason(e)
                _down[provider] = (time.time() + COOLDOWN_S, why)
                security.audit(source, "brain_cloud", f"{provider}:{model}", "error", why)
        msg = _ollama(LOCAL, messages, tools, schema, temperature, max_tokens)
        msg["_fallback"] = f"{NAMES[provider]} ใช้ไม่ได้ ({why}) — ตอบด้วยสมองในเครื่องแทน"
        return msg
    try:
        msg = _ollama(model, messages, tools, schema, temperature, max_tokens)
    except requests.HTTPError as e:
        if model == LOCAL:
            raise
        msg = _ollama(LOCAL, messages, tools, schema, temperature, max_tokens)  # e.g. a model that can't chat/use tools
        msg["_fallback"] = f"{model} ใช้ไม่ได้ ({reason(e)}) — ตอบด้วย {LOCAL} แทน"
    for i, c in enumerate(msg.get("tool_calls") or []):
        c.setdefault("id", f"call_{int(time.time() * 1000)}_{i}")
    return msg


def reason(e):
    """Short Thai reason for the panel (never the key, never a body)."""
    s = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(e, PermissionError):
        return str(e)
    if s in (401, 403):
        return "API key ไม่ถูกต้องหรือไม่มีสิทธิ์"
    if s == 402 or "credit" in str(e).lower() or "quota" in str(e).lower():
        return "เครดิตหมด"
    if s == 404:
        return "ไม่มีโมเดลนี้"
    if s == 429:
        return "ถูกจำกัดการใช้ชั่วคราว"
    if s and s >= 500:
        return f"เซิร์ฟเวอร์ขัดข้อง ({s})"
    if isinstance(e, (requests.ConnectionError, requests.Timeout)) or "connect" in type(e).__name__.lower() or "timeout" in type(e).__name__.lower():
        return "ต่อเน็ตไม่ได้"
    return type(e).__name__


def strict(schema):
    """Cloud structured output wants closed objects with every property required; drop counts they don't support."""
    if isinstance(schema, dict):
        out = {k: strict(v) for k, v in schema.items() if k not in ("maxItems", "minItems")}
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out
    if isinstance(schema, list):
        return [strict(x) for x in schema]
    return schema


def pairs(messages):
    """Ollama-shaped history -> list of (kind, payload) the adapters render, with tool calls and their results paired.
    A window cut that starts mid tool exchange, or a call whose results are missing, keeps only the text — both APIs
    reject a tool result without its call (and the reverse)."""
    out, i = [], 0
    msgs = [m for m in messages if m.get("role") != "system"]
    while i < len(msgs):
        m = msgs[i]
        if m["role"] == "user":
            out.append(("user", m))
        elif m["role"] == "assistant":
            calls = m.get("tool_calls") or []
            j = i + 1
            results = []
            while j < len(msgs) and msgs[j]["role"] == "tool":
                results.append(msgs[j])
                j += 1
            if calls and len(results) == len(calls):
                ids = [c.get("id") or f"call_{i}_{k}" for k, c in enumerate(calls)]
                out.append(("calls", m, ids, results))
                i = j
                continue
            if m.get("content"):
                out.append(("assistant", m))
            i = j  # orphan results (no matching call) are dropped with it
            continue
        i += 1  # a leading tool result whose call fell out of the window
    while out and out[0][0] != "user":
        out.pop(0)  # both APIs: the conversation starts with the user
    return out


if __name__ == "__main__":  # selftest: conversion + routing without any key or network to the cloud
    import sys, tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    tmp = tempfile.mkdtemp()
    rules.SETTINGS, security.SECRETS, security.AUDIT = (os.path.join(tmp, "s.json"), os.path.join(tmp, "x.dat"),
                                                        os.path.join(tmp, "a.log"))
    rules.settings()
    assert current() == ("ollama", LOCAL) and not is_cloud()
    hist = [{"role": "system", "content": "You are FRIDAY"},
            {"role": "tool", "tool_name": "x", "content": "orphan from a cut window"},
            {"role": "user", "content": "เปิด notepad", "images": ["AAAA"]},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "open", "arguments": {"target": "notepad"}}}]},
            {"role": "tool", "tool_name": "open", "content": "Opened notepad"},
            {"role": "assistant", "content": "เปิดแล้วค่ะ"},
            {"role": "user", "content": "แล้วปิดด้วย"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c9", "function": {"name": "x", "arguments": {}}}]}]  # no result yet
    p = pairs(hist)
    assert [x[0] for x in p] == ["user", "calls", "assistant", "user"], [x[0] for x in p]
    assert p[1][2] == ["call_2_0"] and p[1][3][0]["content"] == "Opened notepad"
    s = strict({"type": "object", "properties": {"notes": {"type": "array", "items": {"type": "string", "enum": ["a"]}, "maxItems": 3}}})
    assert s["additionalProperties"] is False and s["required"] == ["notes"] and "maxItems" not in s["properties"]["notes"]
    import brain_claude, brain_openai
    c = brain_claude.render(hist)
    assert c[0]["role"] == "user" and c[0]["content"][0]["type"] == "image" and c[0]["content"][1]["text"] == "เปิด notepad"
    assert c[1]["content"][0] == {"type": "tool_use", "id": "call_2_0", "name": "open", "input": {"target": "notepad"}}
    assert c[2]["content"][0] == {"type": "tool_result", "tool_use_id": "call_2_0", "content": "Opened notepad"}
    o = brain_openai.render(hist)
    assert o[0] == {"role": "system", "content": "You are FRIDAY"} and o[1]["content"][1]["type"] == "image_url"
    assert o[2]["tool_calls"][0]["function"] == {"name": "open", "arguments": json.dumps({"target": "notepad"}, ensure_ascii=False)}
    assert o[3] == {"role": "tool", "tool_call_id": "call_2_0", "content": "Opened notepad"}
    # a cloud brain with no key falls back to the local model and says why (needs Ollama running)
    set_brain("anthropic", "claude-opus-5-5")
    assert is_cloud() and label().startswith("☁ Claude")
    try:
        m = chat([{"role": "user", "content": "reply with: ok"}], max_tokens=20)
        assert "ยังไม่ได้ใส่ API key" in m["_fallback"], m
        print("fallback:", m["_fallback"], "|", m.get("content", "")[:40])
    except requests.ConnectionError:
        print("(Ollama is not running: fallback path not exercised)")
    set_key("anthropic", "sk-ant-test")
    assert key("anthropic") == "sk-ant-test" and "sk-ant-test" not in open(rules.SETTINGS, encoding="utf-8").read()
    print("BRAIN SELFTEST OK")
