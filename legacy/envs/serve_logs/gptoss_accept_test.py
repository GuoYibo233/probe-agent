"""Acceptance check for the gpt-oss-120b vLLM server on tokyo108:8103.

Checks /v1/models returns 200, then sends one two-step reasoning question and
reports whether `reasoning` / `reasoning_content` and `content` are non-empty.
"""

import json
import urllib.request

BASE = "http://tokyo108:8103/v1"
QUESTION = (
    "A train leaves at 09:00 travelling 60 km/h. A second train leaves the same "
    "station at 10:30 travelling 90 km/h on the same track. At what clock time "
    "does the second train catch the first? Show the two steps."
)


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.status, json.load(resp)


def post_json(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return resp.status, json.load(resp)


def main() -> None:
    status, models = get_json(f"{BASE}/models")
    print("GET /v1/models ->", status)
    print("model ids:", [m["id"] for m in models.get("data", [])])

    status, out = post_json(
        f"{BASE}/chat/completions",
        {
            "model": "gpt-oss-120b",
            "messages": [{"role": "user", "content": QUESTION}],
            "max_tokens": 4096,
            "temperature": 0.0,
        },
    )
    print("POST /v1/chat/completions ->", status)

    msg = out["choices"][0]["message"]
    print("finish_reason:", out["choices"][0].get("finish_reason"))
    print("message keys:", sorted(msg.keys()))
    for field in ("reasoning", "reasoning_content", "content"):
        val = msg.get(field)
        if val is None:
            print(f"{field}: <absent>")
        else:
            text = val if isinstance(val, str) else json.dumps(val)
            print(f"{field}: len={len(text)} nonempty={bool(text.strip())}")
            print(f"{field}[:80]: {text[:80]!r}")
    print("usage:", out.get("usage"))


if __name__ == "__main__":
    main()
