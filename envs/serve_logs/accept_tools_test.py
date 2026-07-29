"""Acceptance: chat completion with tools + tool_choice=auto must not 400,
and message.reasoning must be non-empty."""
import json
import sys
import urllib.error
import urllib.request

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"],
            },
        },
    }
]


def check(port: int, model: str) -> bool:
    url = f"http://tokyo108:{port}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Use the tool to check tomorrow's weather in Tokyo.",
            }
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": 8192,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.load(r)
            status = r.status
    except urllib.error.HTTPError as e:
        print(f"[{port}] HTTP {e.code}: {e.read()[:500]!r}")
        return False

    choice = resp["choices"][0]
    msg = choice["message"]
    reasoning = msg.get("reasoning") or ""
    tool_calls = msg.get("tool_calls") or []
    content = msg.get("content") or ""
    print(
        f"[{port}] http={status} finish={choice.get('finish_reason')} "
        f"reasoning={len(reasoning)} chars, tool_calls={len(tool_calls)}, "
        f"content={len(content)} chars"
    )
    print(f"[{port}] reasoning head: {reasoning[:200]!r}")
    if tool_calls:
        print(f"[{port}] tool_call[0]: {json.dumps(tool_calls[0])[:300]}")
    city_ok = False
    if tool_calls:
        try:
            args = json.loads(tool_calls[0]["function"]["arguments"])
            city_ok = args.get("city") == "Tokyo"
            print(f"[{port}] parsed arguments: {args}")
        except Exception as e:
            print(f"[{port}] arguments parse error: {e}")
    ok = status == 200 and bool(reasoning.strip()) and city_ok
    print(f"[{port}] " + ("PASS" if ok else "FAIL"))
    return ok


if __name__ == "__main__":
    ok1 = check(8101, "qwen3.5-27b")
    ok2 = check(8102, "qwen3.6-27b")
    sys.exit(0 if (ok1 and ok2) else 1)
