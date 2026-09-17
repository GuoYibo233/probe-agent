"""Both ends of the served agent model: start or attach to the vLLM server for a table row and check it, plus the loop's raw token-stream client."""
# venv: any at import; vllm to serve
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = 1

# The two message shapes the 2026-08-18 investigation found the jinja text path
# diverging on: an assistant turn with empty content, and a literal `<|end|>`
# inside content. render_ids is compared against the chat endpoint on exactly
# this fixture.
CHECK_MESSAGES = [
    {"role": "system", "content": "You are a careful assistant."},
    {"role": "user", "content": "Reply with one word."},
    {"role": "assistant", "content": ""},
    {"role": "assistant", "content": "<|end|>"},
]

_RETRIES = 3
_RETRY_BASE_S = 1.0


# ---------------------------------------------------------------------------
# Server half (venv: vllm). Every heavy or repo-internal import sits inside
# the functions below, so the module itself imports under every venv.
# ---------------------------------------------------------------------------

def build_command(row: dict, serving: dict, weights_path: str, port: int,
                   gpus: str, date: str | None) -> tuple[list[str], dict[str, str]]:
    """The vllm serve argv and its environment for one agent-model row."""
    vllm_bin = str(Path(sys.executable).parent / "vllm")
    argv = [
        vllm_bin, "serve", weights_path,
        "--served-model-name", str(row["served_model_name"]),
        "--host", "0.0.0.0",
        "--port", str(port),
        "--gpu-memory-utilization", str(serving["gpu_memory_utilization"]),
        "--tensor-parallel-size", str(serving["tensor_parallel_size"]),
        "--max-model-len", str(row["max_model_len"]),
        "--dtype", str(row["dtype"]),
    ]
    if row.get("quantization") is not None:
        argv += ["--quantization", str(row["quantization"])]
    extra_flags = row.get("extra_flags") or ""
    if extra_flags:
        argv += shlex.split(extra_flags)

    env: dict[str, str] = {}
    for k, v in (serving.get("env") or {}).items():
        env[str(k)] = str(v)
    for k, v in (row.get("env_result") or {}).items():
        env[str(k)] = str(v)
    env["VLLM_SYSTEM_START_DATE"] = str(date)
    env["CUDA_VISIBLE_DEVICES"] = str(gpus)
    return argv, env


def _endpoint_path(run_dir: Path, replica: int) -> Path:
    return run_dir / f"service_agent_{replica}.json"


def _write_endpoint_file(path: Path, *, replica: int, base_url: str, host: str, port: int,
                          pid: int | None, flags: dict, claims: dict,
                          attached_to: str | None) -> None:
    doc = {
        "kind": "agent", "replica": replica, "base_url": base_url, "host": host, "port": port,
        "pid": pid, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "flags": flags, "claims": claims, "attached_to": attached_to,
    }
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(doc))
    tmp.replace(path)


def _request(url: str, payload: dict | None, timeout: float, retries: int = _RETRIES):
    """A GET (payload None) or POST, decoded from JSON; retries connection errors and 5xx, raises at once on 4xx."""
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers,
                                          method="GET" if body is None else "POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries - 1:
                raise
            last_exc = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == retries - 1:
                raise
            last_exc = e
        time.sleep(_RETRY_BASE_S * (2 ** attempt))
    raise last_exc  # pragma: no cover - unreachable, every branch above raises or returns


def _attach(base_url: str, row: dict) -> None:
    """Ask GET /v1/models and refuse to attach unless the served model name and max_model_len match the frozen row."""
    data = _request(base_url + "/models", None, timeout=30.0)
    cards = data.get("data") or []
    if not cards:
        raise SystemExit(f"models.agent_models.service: --attach-only: {base_url}/models lists no model")
    card = cards[0]
    mismatches = []
    if card.get("id") != row["served_model_name"]:
        mismatches.append(f"served_model_name: expected {row['served_model_name']!r}, got {card.get('id')!r}")
    if card.get("max_model_len") != row["max_model_len"]:
        mismatches.append(f"max_model_len: expected {row['max_model_len']!r}, got {card.get('max_model_len')!r}")
    if mismatches:
        raise SystemExit("models.agent_models.service: --attach-only refuses on a difference: "
                          + "; ".join(mismatches))


def _wait_healthy(root_url: str, proc: subprocess.Popen, poll_s: float = 2.0) -> None:
    while True:
        if proc.poll() is not None:
            raise SystemExit(
                f"models.agent_models.service: the vllm process exited with code {proc.returncode} "
                "before /health answered"
            )
        try:
            _request(root_url + "/health", None, timeout=5.0, retries=1)
            return
        except Exception:
            time.sleep(poll_s)


def _check_model(base_url: str, row: dict) -> None:
    data = _request(base_url + "/models", None, timeout=30.0)
    names = [c.get("id") for c in (data.get("data") or [])]
    if row["served_model_name"] not in names:
        raise SystemExit(
            f"models.agent_models.service: GET /v1/models does not name "
            f"{row['served_model_name']!r} (has {names})"
        )


def _check_render(base_url: str, row: dict, m, cfg) -> None:
    """render_ids computed in this venv must equal the chat endpoint's prompt_token_ids, id for id."""
    local_ids = m.module.render_ids(CHECK_MESSAGES, cfg.generation.effort, cfg.generation.date)
    resp = _request(base_url + "/chat/completions", {
        "model": row["served_model_name"], "messages": CHECK_MESSAGES, "max_tokens": 1,
        "reasoning_effort": cfg.generation.effort, "return_token_ids": True,
    }, timeout=120.0)
    server_ids = resp.get("prompt_token_ids")
    if local_ids != server_ids:
        raise SystemExit(
            "models.agent_models.service: render_ids diverges from the chat endpoint "
            f"({len(local_ids)} local ids, {len(server_ids) if server_ids is not None else 0} server ids)"
        )


def serve(args) -> None:
    import models
    from experimental_settings import schema

    run_dir = Path(args.run_dir)
    cfg = schema.load_frozen(run_dir)
    row = cfg.models.agent_row
    m = models.agent(args.model)
    if m.family != row["family"] or m.weights != row["weights"]:
        raise SystemExit(
            f"models.agent_models.service: live family/weights for {args.model!r} "
            f"({m.family!r}, {m.weights!r}) differ from the frozen models.agent_row "
            f"({row['family']!r}, {row['weights']!r}); refusing"
        )

    host = m.serving["host"]
    root_url = f"http://{host}:{args.port}"
    base_url = root_url + "/v1"
    claims = dict(row)
    endpoint_path = _endpoint_path(run_dir, args.replica)

    if args.attach_only:
        if not args.attached_to:
            raise SystemExit(
                "models.agent_models.service: --attach-only requires --attached-to <run_id>"
            )
        _attach(base_url, row)
        _write_endpoint_file(
            endpoint_path, replica=args.replica, base_url=base_url, host=host, port=args.port,
            pid=None, flags=vars(args), claims=claims, attached_to=args.attached_to,
        )
        return

    argv, built_env = build_command(row, m.serving, m.weights_path, args.port, args.gpus,
                                     cfg.generation.date)
    env = dict(os.environ)
    env.update(built_env)
    proc = subprocess.Popen(argv, env=env)
    try:
        _wait_healthy(root_url, proc)
        _check_model(base_url, row)
        _check_render(base_url, row, m, cfg)
    except Exception:
        proc.terminate()
        raise
    _write_endpoint_file(
        endpoint_path, replica=args.replica, base_url=base_url, host=host, port=args.port,
        pid=proc.pid, flags=vars(args), claims=claims, attached_to=None,
    )
    raise SystemExit(proc.wait())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m models.agent_models.service")
    sub = ap.add_subparsers(dest="command", required=True)
    srv = sub.add_parser("serve")
    srv.add_argument("--run-dir", required=True)
    srv.add_argument("--model", required=True)
    srv.add_argument("--port", type=int, required=True)
    srv.add_argument("--gpus", required=True)
    srv.add_argument("--replica", type=int, default=0)
    srv.add_argument("--attach-only", action="store_true")
    srv.add_argument("--attached-to", default=None,
                      help="the run_id of the row that owns the server being attached to "
                           "(passed by jobs/launch.py, which is the one side that knows it)")
    args = ap.parse_args(argv)
    if args.command == "serve":
        serve(args)
    return 0


# ---------------------------------------------------------------------------
# Client half (standard library only), imported by agent/generate.py and
# agent/loop.py.
# ---------------------------------------------------------------------------

class Stream:
    """Iterate (text_delta, token_ids_delta) pairs from a running /v1/completions stream."""

    def __init__(self, resp) -> None:
        self._resp = resp
        self.finish_reason: str | None = None
        self.stop_reason: str | None = None
        self.usage: dict | None = None
        self.n_chunks = 0
        self.n_ids = 0

    def __iter__(self):
        for line in self._resp:
            if not line.startswith(b"data: "):
                continue
            data = line[6:].strip()
            if data == b"[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("usage"):
                self.usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                if choice.get("finish_reason"):
                    self.finish_reason = choice["finish_reason"]
                    self.stop_reason = choice.get("stop_reason")
                text = choice.get("text") or ""
                ids = choice.get("token_ids") or []
                if text or ids:
                    self.n_chunks += 1
                    self.n_ids += len(ids)
                    yield text, ids
        self.close()

    def close(self) -> None:
        try:
            self._resp.close()
        except Exception:
            pass


def _open_stream(url: str, payload: dict, timeout: float) -> Stream:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    last_exc: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=timeout)
            return Stream(resp)
        except urllib.error.HTTPError as e:
            if e.code == 400 or attempt == _RETRIES - 1:
                raise
            last_exc = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == _RETRIES - 1:
                raise
            last_exc = e
        time.sleep(_RETRY_BASE_S * (2 ** attempt))
    raise last_exc  # pragma: no cover - unreachable, every branch above raises or returns


class Client:
    def __init__(self, base_url: str, served_model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.served_model_name = served_model_name

    def stream(self, prompt_ids: list[int], generation: dict, seed: int | None) -> Stream:
        payload = {
            "model": self.served_model_name,
            "prompt": prompt_ids,
            "max_tokens": generation["max_tokens"],
            "temperature": generation["temperature"],
            "add_special_tokens": False,
            "skip_special_tokens": False,
            "return_token_ids": True,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if generation["top_p"] is not None:
            payload["top_p"] = generation["top_p"]
        if generation["stop"] is not None:
            payload["stop"] = generation["stop"]
        if seed is not None:
            payload["seed"] = seed
        return _open_stream(self.base_url + "/completions", payload, timeout=600.0)

    def health(self) -> dict:
        root = self.base_url[:-len("/v1")] if self.base_url.endswith("/v1") else self.base_url
        up = True
        try:
            _request(root + "/health", None, timeout=10.0, retries=1)
        except Exception:
            up = False
        names: list[str] = []
        try:
            data = _request(self.base_url + "/models", None, timeout=10.0, retries=1)
            names = [c.get("id") for c in (data.get("data") or [])]
        except Exception:
            pass
        return {"up": up, "served_model_names": names}


if __name__ == "__main__":
    raise SystemExit(main())
