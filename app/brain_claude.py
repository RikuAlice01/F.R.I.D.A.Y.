"""Claude as FRIDAY's brain (PLAN §84) — Anthropic Python SDK, called only from brain.py.

One turn's tool loop sends Claude's own content blocks back unchanged (thinking included); across turns FRIDAY's
history keeps text and tool calls only, so no thinking block is ever replayed from an earlier, rebuilt prompt
(FRIDAY rebuilds the system prompt every turn — time, memory notes — which would invalidate replayed blocks).
"""
import anthropic

from brain import pairs, strict

# Current models take an effort level (thinking depth); FRIDAY answers in voice, so keep it quick
EFFORT = ("claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5",
          "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")
# server-side refusal fallback ("default" routing) on the models that support it
FALLBACKS = ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5")


def _client(key):
    return anthropic.Anthropic(api_key=key, timeout=120.0, max_retries=1)


def models(key):
    return [m.id for m in _client(key).models.list()]


def _user(m):
    blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in m.get("images") or []]
    return blocks + [{"type": "text", "text": m.get("content") or "…"}]


def render(messages):
    """Ollama-shaped history -> Messages API `messages` (system goes separately)."""
    out = []
    for kind, m, *rest in pairs(messages):
        if kind == "user":
            out.append({"role": "user", "content": _user(m)})
        elif kind == "assistant":
            out.append({"role": "assistant", "content": [{"type": "text", "text": m["content"]}]})
        else:  # calls + their results
            ids, results = rest
            if m.get("_raw") and m.get("_provider") == "anthropic":
                content = m["_raw"]  # this turn: Claude's own blocks, unchanged
            else:
                content = ([{"type": "text", "text": m["content"]}] if m.get("content") else []) + [
                    {"type": "tool_use", "id": i, "name": c["function"]["name"], "input": c["function"].get("arguments") or {}}
                    for i, c in zip(ids, m["tool_calls"])]
            out.append({"role": "assistant", "content": content})
            out.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": r.get("content") or ""}
                                                    for i, r in zip(ids, results)]})
    return out


def chat(key, model, messages, tools, schema, max_tokens):
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    kw = {"model": model, "max_tokens": max_tokens, "messages": render(messages)}
    if system:
        kw["system"] = system
    if tools:
        kw["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                        "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}} for t in tools]
    out_cfg = {}
    if model.startswith(EFFORT):
        out_cfg["effort"] = "low"
    if schema:
        out_cfg["format"] = {"type": "json_schema", "schema": strict(schema)}
    if out_cfg:
        kw["output_config"] = out_cfg
    client = _client(key)
    if model.startswith(FALLBACKS):
        r = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}, **kw)
    else:
        r = client.messages.create(**kw)
    if r.stop_reason == "refusal":
        return {"role": "assistant", "content": "ขออภัยค่ะ คำขอนี้ Claude ไม่ตอบ", "_provider": "anthropic"}
    text = "".join(b.text for b in r.content if b.type == "text")
    calls = [{"id": b.id, "function": {"name": b.name, "arguments": dict(b.input or {})}} for b in r.content if b.type == "tool_use"]
    msg = {"role": "assistant", "content": text, "_provider": "anthropic",
           "_raw": [b.model_dump(exclude_none=True) for b in r.content]}
    if calls:
        msg["tool_calls"] = calls
    return msg
