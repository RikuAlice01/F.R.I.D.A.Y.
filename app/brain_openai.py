"""OpenAI chat models as FRIDAY's brain (PLAN §84) — Chat Completions over HTTPS, called only from brain.py."""
import json

import requests

from brain import pairs, strict

API = "https://api.openai.com/v1"
SKIP = ("audio", "realtime", "embedding", "tts", "whisper", "image", "transcribe", "search", "moderation", "dall-e", "davinci", "babbage")


def models(key):
    r = requests.get(f"{API}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json()["data"] if m["id"].startswith(("gpt-", "o", "chatgpt")) and not any(s in m["id"] for s in SKIP))


def render(messages):
    out = [{"role": "system", "content": m["content"]} for m in messages if m.get("role") == "system"]
    for kind, m, *rest in pairs(messages):
        if kind == "user":
            imgs = m.get("images") or []
            out.append({"role": "user", "content": [{"type": "text", "text": m.get("content") or "…"}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in imgs]} if imgs
                       else {"role": "user", "content": m.get("content") or "…"})
        elif kind == "assistant":
            out.append({"role": "assistant", "content": m["content"]})
        else:
            ids, results = rest
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": [
                {"id": i, "type": "function", "function": {"name": c["function"]["name"],
                                                           "arguments": json.dumps(c["function"].get("arguments") or {}, ensure_ascii=False)}}
                for i, c in zip(ids, m["tool_calls"])]})
            out += [{"role": "tool", "tool_call_id": i, "content": r.get("content") or ""} for i, r in zip(ids, results)]
    return out


def chat(key, model, messages, tools, schema, max_tokens):
    body = {"model": model, "messages": render(messages), "max_completion_tokens": max_tokens}
    if tools:
        body["tools"] = [{"type": "function", "function": t["function"]} for t in tools]
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": strict(schema)}}
    r = requests.post(f"{API}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
    r.raise_for_status()
    m = r.json()["choices"][0]["message"]
    msg = {"role": "assistant", "content": m.get("content") or "", "_provider": "openai"}
    calls = [{"id": c["id"], "function": {"name": c["function"]["name"], "arguments": json.loads(c["function"].get("arguments") or "{}")}}
             for c in m.get("tool_calls") or []]
    if calls:
        msg["tool_calls"] = calls
    return msg
