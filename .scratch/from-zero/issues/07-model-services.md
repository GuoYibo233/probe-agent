# 07 the two model services

Status: ready-for-agent
Blocked by: 04, 06
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7)

## What to do

Two files. Contracts 7.1 (the agent service), 7.2 (the probe service), 7.4
(ports and endpoint files), 1.5 (the endpoint file) and 1.6 (the checkpoint
layout it reads) are the specification; read 7.1, 7.2 and 7.4 in full.

```
models/agent_models/service.py   venv: any at import; vllm to serve     VERSION = 1
  imports: models/__init__.py (the family through agent(alias), inside the server main),
           experimental_settings/schema.py (load_frozen)
  used by: agent/generate.py (client), agent/loop.py (health); jobs/launch.py starts it
           as a tmux piece, which is not an import
  reads:   models/table.yaml (the serving block only), constants/path_models.yaml,
           the run directory's settings.yaml (models.agent_row — every keyed column —
           plus generation.date and generation.effort)
  writes:  service_agent_<replica>.json and its piece log in the run directory

models/probe_models/service.py   venv: any at import; probe to serve    VERSION = 1
  imports: models/__init__.py; experimental_settings/schema.py (load_frozen, for the
           check client's expected values); models/probe_models/base.py inside serve();
           [http.server, transformers and torch inside serve()]
  used by: agent/loop.py (client: render), agent/inject.py (client: score, generate,
           encode, decode); jobs/launch.py starts it as a piece
  reads:   the checkpoint directories named on its command line, including each
           best/meta.json; the run directory's settings.yaml (the check client only)
  writes:  service_probe_0.json and its piece log in the run directory

README.md                        your two lines only
```

**Every heavy import sits inside the serving function**, so each file imports as
`any` — that is what lets the loop's client half run in the AppWorld venv.
Both files carry `VERSION = 1`, folded into the `sample` and `inject` keys (2.2).

### 1. `models/agent_models/service.py` (contracts 7.1)

```python
VERSION = 1

# server half
def build_command(row: dict, serving: dict, weights_path: str, port: int,
                  gpus: str, date: str | None) -> tuple[list[str], dict[str, str]]
def serve(args) -> None
def main(argv=None) -> int                 # python -m models.agent_models.service serve ...

# client half (standard library only)
class Stream:                              # yields (text_delta, token_ids_delta)
    finish_reason: str | None
    stop_reason: str | None
    usage: dict | None
    n_chunks: int
    n_ids: int
    def __iter__(self): ...
    def close(self) -> None: ...

class Client:
    def __init__(self, base_url: str, served_model_name: str) -> None: ...
    def stream(self, prompt_ids: list[int], generation: dict,
               seed: int | None) -> Stream: ...
    def health(self) -> dict: ...          # {"up": bool, "served_model_names": [str]}
```

**Command line** (7.1, with `--replica` added by errata — 7.4 names the endpoint
file `service_agent_<replica>.json` and 7.1's line had no replica):

```
python -m models.agent_models.service serve --run-dir <dir> --model <alias> \
    --port <n> --gpus <ids> --replica <i> [--attach-only]
```

Server behaviour, clause by clause:

1. `cfg = schema.load_frozen(run_dir)`; the keyed columns come from
   `cfg.models.agent_row` — `role`, `family` and the whole `result:` block — and
   **never live from `models/table.yaml`**.
2. `m = models.agent(args.model)` gives the family module, `weights_path` and the
   live `serving:` block. **Compare `m.family` against
   `cfg.models.agent_row["family"]` and `m.weights` against
   `cfg.models.agent_row["weights"]`, and refuse on a difference, naming both**
   (errata: 6.2 lists two exceptions to "every keyed column is read from the
   frozen setting" and leaves out the agent service, which 0.2 gives the
   `models/__init__.py` import).
3. `build_command` assembles
   `<sys.executable's directory>/vllm serve <weights_path>
   --served-model-name <served_model_name> --host 0.0.0.0 --port <port>
   --gpu-memory-utilization <g> --tensor-parallel-size <t>
   --max-model-len <max_model_len> --dtype <dtype> [--quantization <q>]
   [<extra_flags>]` and the environment `serving.env` (locations) `+
   result.env_result` (keyed) `+ VLLM_SYSTEM_START_DATE=<date>` `+
   CUDA_VISIBLE_DEVICES=<gpus>`. `quantization` is omitted when null;
   `extra_flags` is split with `shlex`. Ported from
   `legacy/serve_preset.py:41-52`, plus `VLLM_SYSTEM_START_DATE` (6.1), which
   legacy never set.
4. `--attach-only`: do not start a server; ask `GET /v1/models` on
   `http://<serving.host>:<port>/v1`, compare the served model name and every
   keyed column against `cfg.models.agent_row`, and refuse to attach on any
   difference. `jobs/launch.py` decides when to pass the flag (7.4).
5. The check table, before reporting healthy (7.1): `/health` answers within
   `registry.DEFAULTS["launch_timeout_s"]`; `GET /v1/models` names the row's
   `served_model_name`; and **render equals server** —
   `m.module.render_ids(CHECK_MESSAGES, cfg.generation.effort, cfg.generation.date)`
   computed in this venv equals the `prompt_token_ids` the chat endpoint returns
   for the same conversation (`POST /v1/chat/completions`, `max_tokens: 1`,
   `reasoning_effort`, `return_token_ids: true`), id for id. `CHECK_MESSAGES` is a
   module-level literal of four messages: a system message, a user message, an
   assistant turn with **empty** content, and an assistant turn containing a
   literal `<|end|>` — the two shapes the 2026-08-18 investigation found
   diverging (`legacy/pipeline/inject/harmony_render.py:1-18`).
6. Write `service_agent_<replica>.json` into the run directory. **Its fields
   (errata; 1.5 names them in prose only):** `kind`, `replica`, `base_url`,
   `host`, `port`, `pid`, `started_at`, `flags`, `claims`, `attached_to`, where
   `claims` is the frozen `result:` block plus `role` and `family`, the
   `base_url` **ends in `/v1`**, and `attached_to` is the owning row's `run_id`
   when `--attach-only` was used and null otherwise.
7. Then `exec`/wait on the vLLM process, so the tmux piece lives as long as the
   server.

Client behaviour: `Stream` is
`legacy/pipeline/inject/live_appworld.py:188-239` verbatim in shape — SSE lines,
`usage` when `include_usage` gives it, `finish_reason` / `stop_reason` from the
choice, and `(text, ids)` handed out **together per chunk** because the text lags
the ids when vLLM withholds bytes. The request body is `model`, `prompt` (ids),
`max_tokens`, `temperature`, `stop`, `top_p` and `seed` **only when set**,
`add_special_tokens: false`, `skip_special_tokens: false`,
`return_token_ids: true`, `stream: true`,
`stream_options: {include_usage: true}` (7.1; `live_appworld.py:252-270` for the
"only when set" rule). **`generation` is a plain dict carrying exactly
`max_tokens`, `temperature`, `top_p`, `stop`** (errata; `agent/generate.py`
builds it, and the per-request `max_tokens` is `max_step_tokens` minus the ids
already generated, `live_appworld.py:449`). Opening the stream retries three
times with exponential backoff on connection errors and 5xx
(`live_appworld.py:241-249`); **a 400 is re-raised as `urllib.error.HTTPError`**
for the caller to record as `abort="context_overflow_400"`.

Legacy sources: `legacy/serve_preset.py:32-56`;
`legacy/envs/serve_logs/launch_vllm_awdiag.py:55-62`;
`live_appworld.py:188-270`.
Not ported: `serve_preset.py:53-56,68-81` — the ssh + tmux + `tee` assembly, the
`WORKDIR` log convention, `--session`, `--dry-run` and the
`<session>.preset.json` copy (starting a piece is `jobs/launch.py`'s and the
settings copy is `settings.yaml`); every handwritten launcher under
`legacy/envs/serve_logs/` (all eighteen); `legacy/preset_loader.py`'s
`merge_client`, `require_temperature`, `validate`, `list_presets`.

### 2. `models/probe_models/service.py` (contracts 7.2, 7.4)

```python
VERSION = 1

def serve(args) -> None
def check(args) -> int                     # 0 on success, non-zero on any mismatch
def main(argv=None) -> int

class Client:                              # standard library only
    def __init__(self, base_url: str) -> None: ...
    def score(self, text: str) -> dict              # {"conf","label","wall_s"}
    def generate(self, text: str, max_new: int) -> dict   # {"call","wall_s"}
    def render(self, messages: list[dict], effort: str, date: str) -> dict
                                                    # {"prefix_ids","n_tokens","wall_s"}
    def encode(self, text: str, special: bool) -> dict    # {"ids","wall_s"}
    def decode(self, ids: list[int]) -> dict              # {"text","wall_s"}
    def health(self) -> dict
```

**Decision already made (errata):** every client method returns the route's
**decoded JSON dict**, `render` included, and a caller takes `["prefix_ids"]`.
7.3 writes `probe_client.render(...) -> prefix_ids` while 7.2's route returns a
body; the dict is what crosses.

**Command line** (7.2, verbatim):

```
python -m models.probe_models.service serve --run-dir <dir> \
    --agent-model <alias> --port <n> \
    [--score-ckpt <dir> --gen-ckpt <dir> --temperature <f>] \
    [--device cuda:0] [--render-only]
python -m models.probe_models.service check --base-url <url> --run-dir <dir>
```

Server behaviour:

- The three probe flags and `--device` are **absent under `--render-only`**,
  which loads no probe and runs on the CPU.
- Both checkpoint flags take the **train run directory**; the service opens
  `<dir>/best/` and `<dir>/best/meta.json` inside it. From the gen checkpoint's
  `meta.json` it reads `call_sep` (passed into `Probe.generate` on every `/gen`)
  and `param_only`: **when `param_only` is true the service refuses to start**,
  naming the checkpoint. From the score checkpoint's `meta.json` it reads
  `max_len` and `train_key`.
- The agent side: `m = models.agent(args.agent_model)` resolves `family` and
  `weights` **live** — the one exception 6.2 allows, closed by the `/health` echo
  and `agent/loop.py`'s comparison — and gives `render_ids` and the HF tokenizer
  at `m.weights_path`. It never imports a family file by name.
- The server **binds `0.0.0.0`**, and `service_probe_0.json`'s `base_url` carries
  the host the piece was placed on, because an inject run's probe piece sits on a
  GPU host while the loop pieces run on `login_host`. The probe `base_url` does
  **not** end in `/v1`.
- **`ThreadingHTTPServer`, with one lock around every model call** (errata; one
  probe service answers `sample.pieces` / `inject.pieces` loop processes at once,
  while legacy served one driver, `probe_server.py:277`).
- Routes, exactly 7.2's table: `POST /score` -> `{"conf","label","wall_s"}`,
  `conf` being `max softmax(logits / temperature)` over what `Probe.score`
  returned and `label` the argmax class name; `POST /gen` with a `max_new` in the
  body -> `{"call","wall_s"}`; `POST /render` -> `{"prefix_ids","n_tokens"}`;
  `POST /encode` -> `{"ids"}` from
  `encode(text, add_special_tokens=False, split_special_tokens=(not special))`;
  `POST /decode` -> `{"text"}` from `decode(ids, skip_special_tokens=False)`;
  `GET /health` -> the startup echo `family`, `weights`, `render` (`"ids"`),
  `encode_special`, `decode`, `temperature`, `agent_model`, `score_train_key`,
  `gen_train_key`, `max_len`, `device`, `version`. Under `--render-only`,
  `/score` and `/gen` return **503** and `temperature`, `score_train_key`,
  `gen_train_key` and `max_len` are null. Every response carries `wall_s`
  (`probe_server.py:271`), and an exception becomes a 500 whose body carries the
  original error text (`:273-274`).
- Writes `service_probe_0.json` with the same ten keys as the agent endpoint file
  (errata), where `claims` is
  `{family, weights, score_train_key, gen_train_key, max_len, temperature}`.

`check --base-url <url> --run-dir <dir>` is a **client**, not a second server. It
reads the run directory's frozen `settings.yaml` through `schema.load_frozen` and
compares, one request per route:

| expected, from `settings.yaml` | against the echo |
|---|---|
| `cfg.models.agent_row["family"]` | `family` |
| `cfg.models.agent_row["weights"]` | `weights` |
| `cfg._upstream["probe_score.train"]` | `score_train_key` |
| `cfg._upstream["probe_gen.train"]` | `gen_train_key` |
| `cfg._resolved["probe_temperature"]` | `temperature` |
| — | `render == "ids"`, `encode_special is True` |

plus **both directions of the `<|end|>` fixture** (9(d)):
`encode("a<|end|>b", special=false)` must contain no control-token id and decode
back to the same text; `encode(..., special=true)` must contain the `<|end|>` id.
When the frozen setting holds no `inject` section (a `sample` run, whose probe
piece is the render-only case), the last three expectation rows are required to
be **null** instead. Any mismatch prints the field, the expected and the seen
value and exits non-zero — which `jobs/launch.py` turns into the `service_check`
outcome of 8.1.

Client behaviour: every call retries three times with exponential backoff on
connection errors and 5xx, and raises on a body carrying `error`
(`live_appworld.py:272-289`).

Legacy sources: `probe_server.py:88-95` (`encode_ids`), `:136-161` (the
render-only branch), `:195-215` (render, encode, decode), `:217-225` (the health
echo), `:228-277` (the HTTP server and the handler); `live_appworld.py:272-289`.
Not ported: `probe_server.py:8,176` — `fired` in `/score`'s response and the
`--theta` flag (theta lives in the setting and `agent/inject.py` compares);
`:280-343` — the whole `selftest` subcommand, replaced by `check`; `:83-85` — the
hardcoded `CTOOL`, `CGEN`, `GPTOSS_TOK` defaults; `:205` — `prefix`, the decoded
text in `/render`'s response; `:225` — `start_date` in the health echo (the date
arrives per request on `/render`); `:218-224` — `theta`, `ctool`, `cgen`,
`render_only`, `n_labels` in the echo, replaced by 7.2's twelve fields.

## Acceptance

Run from the repo root and paste the real output.

```bash
SYS=python3
PR=/home/y-guo/reproduce/new1/external/probe-env/bin/python
AW=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
VL=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1 — both files import as `any` under four interpreters.**
```bash
for P in "$SYS" "$AW" "$PR" "$VL"; do
  $P -c "import models.agent_models.service as a, models.probe_models.service as p; print(a.VERSION, p.VERSION)" || exit 1; done
```
Expected: four lines `1 1`, exit 0. A failure here means a heavy import escaped
its serving function.

**A13 — the probe service end to end on the CPU, render-only** (no GPU). The
`--run-dir` is a fresh temporary directory, since the server half reads no
`settings.yaml`.
```bash
D=$(mktemp -d)
"$PR" -m models.probe_models.service serve \
  --run-dir $D --agent-model gptoss120b --port 8599 --render-only > $D/srv.log 2>&1 &
SRV=$!
for i in $(seq 1 60); do [ -f "$D/service_probe_0.json" ] && break; sleep 1; done
test -f "$D/service_probe_0.json" || { echo "no endpoint file after 60 s"; cat "$D/srv.log"; kill $SRV; exit 1; }
"$PR" -c "
from models.probe_models.service import Client
c = Client('http://127.0.0.1:8599')
h = c.health(); print(h['family'], h['weights'], h['render'], h['encode_special'],
                      h['temperature'], h['score_train_key'], h['max_len'])
print(c.encode('a<|end|>b', False)['ids'])
print(c.encode('a<|end|>b', True)['ids'])
print(c.decode(c.encode('a<|end|>b', False)['ids'])['text'])
r = c.render([{'role':'system','content':'SYS rules'},
              {'role':'user','content':'Task from supervisor: Do X.'}], 'high', '2026-08-06')
print(r['n_tokens'], len(r['prefix_ids']))
try: c.score('x'); print('NO 503')
except Exception as e: print('score refused')"
python3 -c "import json,sys; print(sorted(json.load(open('$D/service_probe_0.json'))))"
kill $SRV        # by recorded pid: a non-interactive bash has no job control for %1
```
Expected exactly (the two encode lines were measured on 2026-09-17 with
transformers 5.14.1 and the gpt-oss-120b tokenizer):
```
gptoss gpt-oss-120b ids True None None None
[64, 27, 91, 419, 91, 29, 65]
[64, 200007, 65]
a<|end|>b
83 83
score refused
```
and the endpoint file listing
`['attached_to', 'base_url', 'claims', 'flags', 'host', 'kind', 'pid', 'port', 'replica', 'started_at']`.

**A14 — the agent service's command and environment, without a GPU.**
```bash
"$VL" -c "
from models.agent_models.service import build_command
import models
m = models.agent('gptoss120b')
row = dict(role='agent', family='gptoss', weights='gpt-oss-120b', dtype='auto',
           quantization=None, max_model_len=131072, served_model_name='gpt-oss-120b',
           env_result={'VLLM_USE_FLASHINFER_SAMPLER': '0'}, extra_flags='')
argv, env = build_command(row, m.serving, m.weights_path, 8103, '0', '2026-08-06')
print(' '.join(argv[1:]))
print(sorted(env.items()))"
```
Expected: the argv line reads
`serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b
--served-model-name gpt-oss-120b --host 0.0.0.0 --port 8103
--gpu-memory-utilization 0.92 --tensor-parallel-size 1 --max-model-len 131072
--dtype auto`, with **no** `--quantization`; and the env holds
`CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=0`, `LD_LIBRARY_PATH`,
`TRITON_CACHE_DIR`, `VLLM_CACHE_ROOT`, `VLLM_SYSTEM_START_DATE=2026-08-06`,
`VLLM_USE_FLASHINFER_SAMPLER=0`.

**A15 — the completion request body.** A stub SSE server on an ephemeral port
records what the client POSTs; the client then streams against it twice, once
with `top_p`, `stop` and `seed` unset and once with all three set.
```bash
"$AW" - <<'PY'
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from models.agent_models.service import Client

RECORDED = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        RECORDED.append(json.loads(self.rfile.read(n) or b"{}"))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in [{"choices": [{"text": "he", "token_ids": [123],
                                "finish_reason": None, "stop_reason": None}]},
                  {"choices": [{"text": "llo", "token_ids": [456],
                                "finish_reason": "stop", "stop_reason": "<|return|>"}]},
                  {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}]:
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

c = Client("http://127.0.0.1:%d/v1" % port, "gpt-oss-120b")
s = c.stream([11, 12], {"max_tokens": 64, "temperature": 1.0, "top_p": None, "stop": None}, None)
print("pairs:", [pair for pair in s])
print("body1:", sorted(RECORDED[-1]))
print("usage:", s.usage, "finish:", s.finish_reason, "stop:", s.stop_reason)
s2 = c.stream([11, 12], {"max_tokens": 64, "temperature": 1.0, "top_p": 0.9,
                         "stop": ["<|return|>"]}, 42)
list(s2)
print("body2:", sorted(RECORDED[-1]))
print("prompt is ids:", RECORDED[-1]["prompt"] == [11, 12],
      "model:", RECORDED[-1]["model"], "path hits:", len(RECORDED))
srv.shutdown()
PY
```
Expected exactly:
```
pairs: [('he', [123]), ('llo', [456])]
body1: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'skip_special_tokens', 'stream', 'stream_options', 'temperature']
usage: {'prompt_tokens': 7, 'completion_tokens': 2} finish: stop stop: <|return|>
body2: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'seed', 'skip_special_tokens', 'stop', 'stream', 'stream_options', 'temperature', 'top_p']
prompt is ids: True model: gpt-oss-120b path hits: 2
```
`top_p`, `stop` and `seed` are **absent** from the first body and present in the
second — the "only when set" rule of `live_appworld.py:252-270`. The client posts
to `<base_url>/completions`, so the stub answers any path.

**A16 — the annotation lines for these two files.**
```bash
python3 - <<'PY'
import ast, pathlib
for f, need, forbid in [
    ('models/agent_models/service.py', {'models', 'experimental_settings.schema'}, {'jobs.registry'}),
    ('models/probe_models/service.py', {'models', 'experimental_settings.schema'}, {'jobs.registry'})]:
    t = ast.parse(pathlib.Path(f).read_text())
    mods = {n.module for n in ast.walk(t) if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name for n in ast.walk(t) if isinstance(n, ast.Import) for a in n.names}
    assert not (mods & forbid), (f, mods & forbid)
    top = {a.module or a.names[0].name for a in t.body if isinstance(a, (ast.Import, ast.ImportFrom))}
    assert not any(m.split('.')[0] in {'torch','transformers','vllm'} for m in top), (f, top)
    n = sum(1 for l in pathlib.Path(f).read_text().splitlines() if l.startswith('VERSION = '))
    assert n == 1, (f, n)
print('A16 ok')
PY
grep -n "/home/\|/net/" models/agent_models/service.py models/probe_models/service.py || echo NO_ABS_PATH
```
Expected: `A16 ok`, then `NO_ABS_PATH`.

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: both files import under every
interpreter of the `venvs:` map (A1); one column-zero `VERSION` each; their
README annotation lines against the `ast`-parsed import graph, in particular that
neither imports `jobs/registry.py` and that torch, transformers and vllm are
never module-level imports (A16).

### GPU / main session — not yours

An implementer that reaches any of these returns BLOCKED with the command.

- `M-M1` on `tokyo108`, with a run directory whose `settings.yaml` names
  `gptoss120b`:
  `<vllm python> -m models.agent_models.service serve --run-dir <run_dir> --model gptoss120b --port 8103 --gpus 0 --replica 0`
  must pass all three check-table lines and write `service_agent_0.json` with
  `base_url: http://tokyo108:8103/v1`, the pid, and `claims` equal to the frozen
  `result:` block plus `role` and `family`.
- `M-M2` with `generation.date: 2026-08-06` the render-equals-server check
  passes; restarting with `VLLM_SYSTEM_START_DATE` unset must make the **same**
  check fail, proving the variable pins the prefix and not the machine clock.
- `M-M3` a second run's service piece started with `--attach-only` on the same
  host and port exits 0, writes `attached_to: <the first run_id>` and takes no
  card; the same command against a server whose `served_model_name` differs exits
  non-zero without attaching.
- `M-M4` from `login_host`, in the AppWorld venv,
  `Client('http://tokyo108:8103/v1', 'gpt-oss-120b').stream(prefix_ids, {'max_tokens': 64, 'temperature': 1.0, 'top_p': None, 'stop': ['<|return|>']}, 42)`
  yields `(text, ids)` pairs whose ids concatenate to a sequence
  `gptoss.end_of_turn` reports True for, `usage` is filled, and `close()` partway
  through returns immediately with `usage is None`.
- `M-M5` the probe service with real checkpoints on a card, and
  `check --base-url http://<that host>:8500 --run-dir <inject run dir>` issued
  **from `login_host`** (which proves the server bound `0.0.0.0`): `check` exits
  0 and prints each compared field, `/score` returns a `conf` in [0,1] and a
  `label` from the checkpoint's `labels`, `/gen` returns one line of call text.
- `M-M6` the two refusals: a `--gen-ckpt` whose `best/meta.json` says
  `param_only: true` exits non-zero naming that checkpoint **before any card is
  taken**; `check` against a service started with the wrong checkpoints exits
  non-zero on `score_train_key` / `gen_train_key`.

## Comments
