"""Acceptance test: /v1/models + logic-puzzle chat completion.

Pass criteria: reasoning_content non-empty AND content non-empty.
"""
import json
import sys
import urllib.request

PUZZLE = (
    "Four friends - Alice, Bob, Carol, and Dave - each own exactly one pet: "
    "a cat, a dog, a parrot, or a fish. Alice is allergic to fur, so her pet "
    "has no fur. Bob's pet cannot fly. Carol's pet is larger than a parrot. "
    "Dave's pet lives in water. Who owns which pet? Answer briefly."
)


def post(url: str, payload: dict, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def check(port: int, model: str) -> bool:
    base = f"http://tokyo108:{port}"
    models = get(f"{base}/v1/models")
    names = [m["id"] for m in models["data"]]
    print(f"[{port}] /v1/models -> {names}")

    resp = post(
        f"{base}/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": PUZZLE}],
            "max_tokens": 16384,
        },
    )
    msg = resp["choices"][0]["message"]
    rc = msg.get("reasoning_content") or ""
    ct = msg.get("content") or ""
    fin = resp["choices"][0].get("finish_reason")
    print(
        f"[{port}] finish={fin} reasoning_content={len(rc)} chars, "
        f"content={len(ct)} chars"
    )
    print(f"[{port}] reasoning head: {rc[:200]!r}")
    print(f"[{port}] content head:   {ct[:300]!r}")
    ok = bool(rc.strip()) and bool(ct.strip())
    print(f"[{port}] PASS" if ok else f"[{port}] FAIL")
    return ok


if __name__ == "__main__":
    ok1 = check(8101, "qwen3.5-27b")
    ok2 = check(8102, "qwen3.6-27b")
    sys.exit(0 if (ok1 and ok2) else 1)
