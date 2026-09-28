"""Both ends of the probe service: the HTTP server that scores, generates, encodes, decodes and renders, plus the check client and the loop's client."""
# venv: any at import; probe to serve
from __future__ import annotations

import argparse
import json
import math
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


# check's own fixtures: a minimal conversation for /render and a minimal
# probe input for /score and /gen. Every other request input check makes
# comes straight off the frozen setting it already loaded.
_CHECK_RENDER_MESSAGES = [
    {"role": "system", "content": "check fixture: a minimal render smoke test."},
    {"role": "user", "content": "check fixture: say ready."},
]
_CHECK_PROBE_TEXT = "check fixture: call apis.example.sample_api()"

_RETRIES = 3
_RETRY_BASE_S = 1.0


def _softmax_max(logits: list[float], temperature: float) -> float:
    scaled = [v / temperature for v in logits]
    peak = max(scaled)
    exps = [math.exp(v - peak) for v in scaled]
    total = sum(exps)
    return max(e / total for e in exps)


def _endpoint_path(run_dir: Path) -> Path:
    return run_dir / "service_probe_0.json"


def _write_endpoint_file(path: Path, *, base_url: str, host: str, port: int, pid: int,
                          flags: dict, claims: dict) -> None:
    doc = {
        "kind": "probe", "replica": 0, "base_url": base_url, "host": host, "port": port,
        "pid": pid, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "flags": flags, "claims": claims, "attached_to": None,
    }
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(doc))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Server half (venv: probe). Every heavy or repo-internal import sits inside
# serve(), so the module itself imports under every venv.
# ---------------------------------------------------------------------------

def serve(args) -> None:
    import http.server
    import threading

    import models

    m = models.agent(args.agent_model)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(m.weights_path)

    score_probe = gen_probe = None
    call_sep = None
    max_len = score_train_key = gen_train_key = None
    temperature = None
    device = "cpu"

    if not args.render_only:
        from models.probe_models import base

        device = args.device
        temperature = args.temperature

        gen_dir = Path(args.gen_ckpt) / "best"
        gen_meta = json.loads((gen_dir / "meta.json").read_text())
        if gen_meta.get("param_only"):
            raise SystemExit(
                f"models.probe_models.service: {gen_dir} is an argument-only checkpoint "
                "(param_only: true) and cannot serve /gen; refusing before any card is taken"
            )
        call_sep = gen_meta["call_sep"]
        gen_train_key = gen_meta["train_key"]

        score_dir = Path(args.score_ckpt) / "best"
        score_meta = json.loads((score_dir / "meta.json").read_text())
        max_len = score_meta["max_len"]
        score_train_key = score_meta["train_key"]

        score_probe = base.load(None, None, probe_kind="classifier", ckpt_dir=score_dir, device=device)
        gen_probe = base.load(None, None, probe_kind="generator", ckpt_dir=gen_dir, device=device)

    health_doc = {
        "family": m.family, "weights": m.weights, "render": "ids", "encode_special": True,
        "decode": True, "temperature": temperature, "agent_model": args.agent_model,
        "score_train_key": score_train_key, "gen_train_key": gen_train_key, "max_len": max_len,
        "device": device,
    }
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:
            pass

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self) -> None:  # noqa: N802 - http.server's naming
            if self.path == "/health":
                self._send(200, dict(health_doc))
            else:
                self._send(404, {"error": f"no such route: {self.path}"})

        def do_POST(self) -> None:  # noqa: N802 - http.server's naming
            t0 = time.monotonic()
            try:
                body = self._read_json()
                if self.path == "/score":
                    if score_probe is None:
                        self._send(503, {"error": "no score checkpoint is loaded (--render-only)"})
                        return
                    with lock:
                        logits, names = score_probe.score([body["text"]])
                    conf = _softmax_max(logits[0], temperature)
                    self._send(200, {"conf": conf, "label": names[0], "wall_s": time.monotonic() - t0})
                elif self.path == "/gen":
                    if gen_probe is None:
                        self._send(503, {"error": "no gen checkpoint is loaded (--render-only)"})
                        return
                    with lock:
                        calls = gen_probe.generate([body["text"]], body["max_new"], call_sep)
                    self._send(200, {"call": calls[0], "wall_s": time.monotonic() - t0})
                elif self.path == "/render":
                    ids = m.module.render_ids(body["messages"], body["effort"], body["date"])
                    self._send(200, {"prefix_ids": ids, "n_tokens": len(ids),
                                      "wall_s": time.monotonic() - t0})
                elif self.path == "/encode":
                    ids = tokenizer.encode(body["text"], add_special_tokens=False,
                                           split_special_tokens=(not body["special"]))
                    self._send(200, {"ids": ids, "wall_s": time.monotonic() - t0})
                elif self.path == "/decode":
                    text = tokenizer.decode(body["ids"], skip_special_tokens=False)
                    self._send(200, {"text": text, "wall_s": time.monotonic() - t0})
                else:
                    self._send(404, {"error": f"no such route: {self.path}"})
            except Exception as e:
                self._send(500, {"error": str(e)})

    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    host = socket.gethostname()
    base_url = f"http://{host}:{args.port}"
    claims = {"family": m.family, "weights": m.weights, "score_train_key": score_train_key,
              "gen_train_key": gen_train_key, "max_len": max_len, "temperature": temperature}
    _write_endpoint_file(
        _endpoint_path(Path(args.run_dir)), base_url=base_url, host=host, port=args.port,
        pid=os.getpid(), flags=vars(args), claims=claims,
    )
    server.serve_forever()


# ---------------------------------------------------------------------------
# check: a client against an already-running service, not a second server.
# ---------------------------------------------------------------------------

def check(args) -> int:
    from experimental_settings import schema

    cfg = schema.load_frozen(Path(args.run_dir))
    client = Client(args.base_url)
    health = client.health()

    has_inject = cfg.inject is not None
    expected = {
        "family": cfg.models.agent_row["family"],
        "weights": cfg.models.agent_row["weights"],
        "score_train_key": cfg._upstream.get("probe_score.train") if has_inject else None,
        "gen_train_key": cfg._upstream.get("probe_gen.train") if has_inject else None,
        "temperature": cfg._resolved.get("probe_temperature") if has_inject else None,
        "render": "ids",
        "encode_special": True,
    }
    ok = True
    for field_name, want in expected.items():
        got = health.get(field_name)
        print(f"check: {field_name} expected={want!r} got={got!r}")
        if got != want:
            ok = False

    plain = client.encode("a<|end|>b", False)
    special = client.encode("a<|end|>b", True)
    control_ids = client.encode("<|end|>", True)["ids"]
    if len(control_ids) != 1:
        print(f"check: <|end|> fixture: encoding '<|end|>' alone with special=true did not "
              f"give a single control-token id, got {control_ids!r}")
        ok = False
    else:
        control_id = control_ids[0]
        if control_id in plain["ids"]:
            print(f"check: <|end|> fixture: the special=false encoding contains the "
                  f"control-token id {control_id}")
            ok = False
        if control_id not in special["ids"]:
            print(f"check: <|end|> fixture: the special=true encoding does not contain the "
                  f"control-token id {control_id}")
            ok = False
    back = client.decode(plain["ids"])
    if back["text"] != "a<|end|>b":
        print("check: <|end|> fixture: the special=false encoding does not round-trip")
        ok = False

    render = client.render(_CHECK_RENDER_MESSAGES, cfg.generation.effort, cfg.generation.date)
    prefix_ids = render.get("prefix_ids")
    render_ok = (isinstance(prefix_ids, list) and len(prefix_ids) > 0
                 and all(isinstance(i, int) for i in prefix_ids))
    print(f"check: /render prefix_ids is a non-empty list of ints: {render_ok} "
          f"(got {prefix_ids!r})")
    if not render_ok:
        ok = False

    if has_inject:
        score = client.score(_CHECK_PROBE_TEXT)
        conf = score.get("conf")
        label = score.get("label")
        conf_ok = isinstance(conf, (int, float)) and not isinstance(conf, bool) and 0.0 <= conf <= 1.0
        label_ok = isinstance(label, str) and label != ""
        print(f"check: /score conf is a float in [0,1]: {conf_ok} (got {conf!r})")
        print(f"check: /score label is a non-empty str: {label_ok} (got {label!r})")
        if not (conf_ok and label_ok):
            ok = False

        gen = client.generate(_CHECK_PROBE_TEXT, cfg.inject.max_new)
        call = gen.get("call")
        call_ok = isinstance(call, str)
        print(f"check: /gen call is a str: {call_ok} (got {call!r})")
        if not call_ok:
            ok = False

    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m models.probe_models.service")
    sub = ap.add_subparsers(dest="command", required=True)

    srv = sub.add_parser("serve")
    srv.add_argument("--run-dir", required=True)
    srv.add_argument("--agent-model", required=True)
    srv.add_argument("--port", type=int, required=True)
    srv.add_argument("--score-ckpt", default=None)
    srv.add_argument("--gen-ckpt", default=None)
    srv.add_argument("--temperature", type=float, default=None)
    srv.add_argument("--device", default=None)
    srv.add_argument("--render-only", action="store_true")

    chk = sub.add_parser("check")
    chk.add_argument("--base-url", required=True)
    chk.add_argument("--run-dir", required=True)

    args = ap.parse_args(argv)
    if args.command == "serve":
        serve(args)
        return 0
    return check(args)


# ---------------------------------------------------------------------------
# Client half (standard library only), imported by agent/run_tasks.py (render)
# and agent/step_with_probe.py (score, generate, encode, decode).
# ---------------------------------------------------------------------------

def _request(url: str, payload: dict | None, timeout: float, retries: int = _RETRIES):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers,
                                          method="GET" if body is None else "POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read())
            if isinstance(out, dict) and out.get("error"):
                raise RuntimeError(f"{url}: {out['error']}")
            return out
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries - 1:
                try:
                    err_body = json.loads(e.read())
                    msg = err_body.get("error", str(e))
                except Exception:
                    msg = str(e)
                raise RuntimeError(f"{url}: {msg}") from e
            last_exc = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == retries - 1:
                raise
            last_exc = e
        time.sleep(_RETRY_BASE_S * (2 ** attempt))
    raise last_exc  # pragma: no cover - unreachable, every branch above raises or returns


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def score(self, text: str) -> dict:
        return self._post("/score", {"text": text})

    def generate(self, text: str, max_new: int) -> dict:
        return self._post("/gen", {"text": text, "max_new": max_new})

    def render(self, messages: list[dict], effort: str, date: str) -> dict:
        return self._post("/render", {"messages": messages, "effort": effort, "date": date})

    def encode(self, text: str, special: bool) -> dict:
        return self._post("/encode", {"text": text, "special": special})

    def decode(self, ids: list[int]) -> dict:
        return self._post("/decode", {"ids": ids})

    def health(self) -> dict:
        return _request(self.base_url + "/health", None, timeout=30.0)

    def _post(self, path: str, payload: dict) -> dict:
        return _request(self.base_url + path, payload, timeout=120.0)


if __name__ == "__main__":
    raise SystemExit(main())
