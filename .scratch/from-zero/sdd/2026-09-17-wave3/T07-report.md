# T07 report — the two model services

Branch `ticket/2026-09-17-wave3/T07`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T07` (removed at the end of
this ticket per the worktree protocol). Base `28735bb2437f34af4f85d915b9de22f22530cfaa`,
head `e5d8a93` (`git log` on the branch, one commit).

## What was done

Two files, per the ticket's `## What to do`, contracts 7.1, 7.2, 7.4, 1.5, 1.6.

### `models/agent_models/service.py` (contracts 7.1)

- `VERSION = 1` at column zero.
- `build_command(row, serving, weights_path, port, gpus, date) -> (argv, env)`: assembles
  `<sys.executable's dir>/vllm serve <weights_path> --served-model-name ... --host 0.0.0.0
  --port ... --gpu-memory-utilization ... --tensor-parallel-size ... --max-model-len ...
  --dtype ...`, appends `--quantization` only when set, and appends `shlex.split(extra_flags)`.
  `env` is `serving.env` + `row.env_result` + `VLLM_SYSTEM_START_DATE=<date>` +
  `CUDA_VISIBLE_DEVICES=<gpus>` — exactly the seven keys A14 expects, nothing else. Ported
  from `legacy/serve_preset.py:41-52`, `legacy/envs/serve_logs/launch_vllm_awdiag.py:55-62`
  (the env-variable convention), plus `VLLM_SYSTEM_START_DATE` (6.1), which legacy never set.
- `serve(args)`: `cfg = schema.load_frozen(run_dir)`; `row = cfg.models.agent_row`;
  `m = models.agent(args.model)`; refuses on `m.family != row["family"]` or
  `m.weights != row["weights"]`, naming both pairs (the 6.2 exception this service is not
  covered by, per errata). Under `--attach-only`: asks `GET /v1/models`, compares the served
  model name and `max_model_len` against the frozen row (the wave-3 precheck's narrower
  reading of "every keyed column", since the model card carries only those two of the row's
  fields) and refuses on a difference; writes `service_agent_<replica>.json` with
  `attached_to` set and `pid: null` (nothing is started on this side). Otherwise: starts the
  `vllm serve` subprocess with `build_command`'s argv and `os.environ` overlaid with its env;
  polls `/health` (its own request timeout, no `jobs.registry` import — the deadline over the
  whole start is `jobs/launch.py`'s alive check, per the wave-3 precheck errata); checks
  `GET /v1/models` names the row's `served_model_name`; checks `render_ids(CHECK_MESSAGES,
  cfg.generation.effort, cfg.generation.date)` computed in this venv against
  `POST /v1/chat/completions`'s `prompt_token_ids` for the same four-message fixture (a system
  message, a user message, an assistant turn with empty content, and an assistant turn
  containing the literal `<|end|>` — the two shapes 7.1 names); writes
  `service_agent_<replica>.json` with `claims = dict(row)` (already exactly the frozen
  `result:` block plus `role` and `family`) and `pid` the vllm subprocess's; then
  `proc.wait()` and exits with its return code, so the tmux piece lives as long as the server.
- `Stream` / `_open_stream`: SSE lines, `(text, ids)` handed out together per chunk,
  `usage`/`finish_reason`/`stop_reason` from the stream, `close()` on demand — shape of
  `legacy/pipeline/inject/live_appworld.py:188-239`. Retries three times with exponential
  backoff on connection errors and 5xx; a 400 is re-raised (`urllib.error.HTTPError`)
  immediately, not retried, for the caller to record `abort="context_overflow_400"`.
- `Client.stream`: request body is `model`, `prompt` (ids), `max_tokens`, `temperature`,
  `add_special_tokens: false`, `skip_special_tokens: false`, `return_token_ids: true`,
  `stream: true`, `stream_options: {include_usage: true}`, plus `top_p`, `stop`, `seed` only
  when not `None` — the "only when set" rule of `live_appworld.py:252-270`.
- `Client.health`: `{"up": bool, "served_model_names": [str]}` from `GET /health` +
  `GET /v1/models`.

### `models/probe_models/service.py` (contracts 7.2, 7.4)

- `VERSION = 1` at column zero.
- `serve(args)`: reads no `settings.yaml`. `m = models.agent(args.agent_model)` resolves
  `family`/`weights` live (the one exception 6.2 names) and gives `render_ids` and the HF
  tokenizer at `m.weights_path`. Under `--render-only` (the three probe flags and `--device`
  absent, `param_only` refusal and checkpoint loading skipped, `device = "cpu"`): only
  `/render`, `/encode`, `/decode`, `/health` answer; `/score` and `/gen` return 503. Otherwise:
  reads the gen checkpoint's `best/meta.json` first and refuses (naming the checkpoint) when
  `param_only` is true, **before** `base.load` is called for either checkpoint — so the
  refusal fires before any card is taken; then loads `call_sep`, `score_train_key` (`train_key`
  of the score checkpoint), `gen_train_key`, `max_len`, and loads both probes with
  `models.probe_models.base.load(None, None, probe_kind=..., ckpt_dir=..., device=args.device)`.
  `ThreadingHTTPServer` bound to `0.0.0.0`, one `threading.Lock` held around every `/score` and
  `/gen` model call (errata: one service answers many loop pieces at once). Routes exactly
  7.2's table, every response carrying `wall_s`, an exception becoming a 500 whose body carries
  `{"error": "..."}`. `/health` echoes the twelve fields (`family`, `weights`, `render: "ids"`,
  `encode_special: true`, `decode: true`, `temperature`, `agent_model`, `score_train_key`,
  `gen_train_key`, `max_len`, `device`, `version`), with the four probe-only fields `null` under
  `--render-only`. Writes `service_probe_0.json` with `host = socket.gethostname()` (the host
  the piece landed on — the probe alias's `serving:` block in `models/table.yaml` is empty, so
  there is no table host to read), `base_url` **not** ending in `/v1`, and
  `claims = {family, weights, score_train_key, gen_train_key, max_len, temperature}`.
- `check(args)`: a client, not a second server. Reads the run directory's frozen
  `settings.yaml`, compares `cfg.models.agent_row["family"]`/`["weights"]`,
  `cfg._upstream["probe_score.train"]`/`["probe_gen.train"]`, `cfg._resolved["probe_temperature"]`,
  `render == "ids"` and `encode_special is True` against the `/health` echo — the last three
  expected as `null` when `cfg.inject is None` (a `sample` run's render-only probe piece) — plus
  both directions of the `<|end|>` fixture: `special=false` must give **more** ids than
  `special=true` (the collapse a real control token produces) and the `special=false` encoding
  must round-trip through `/decode` to the original text. Prints each field's expected/seen
  pair and returns non-zero on any mismatch.
- `Client`: `score`, `generate`, `render`, `encode`, `decode`, `health` — every method returns
  the route's decoded JSON dict (errata: `render` too, a caller takes `["prefix_ids"]`). Every
  call retries three times with exponential backoff on connection errors and 5xx and raises on
  a body carrying `error` (`live_appworld.py:272-289`).

### `README.md`

Added the `## Ticket 07` section with the two files' tree lines (contracts 0.2,
copied verbatim except for the legacy citations, which stay out of the shipped
source and out of README per spec section 5) under the `agent_models/` and
`probe_models/` groups ticket 06 already introduced, plus a "How to run" note.

## How it was verified

Run from the worktree root, with the four interpreters named by their absolute
path under the main tree (`external/` is git-ignored and not materialised in
the worktree, per spec section 4).

**A1 — both files import as `any` under four interpreters.**
```
$ for P in python3 <appworld> <probe> <vllm>; do $P -c "import models.agent_models.service as a, models.probe_models.service as p; print(a.VERSION, p.VERSION)"; done
1 1
1 1
1 1
1 1
```
Exit 0 on all four, matching "four lines `1 1`".

**A13 — the probe service end to end on the CPU, render-only.**
```
$ D=$(mktemp -d)
$ "$PR" -m models.probe_models.service serve --run-dir $D --agent-model gpt_oss_120b --port 8599 --render-only > $D/srv.log 2>&1 &
$ ... (wait for $D/service_probe_0.json, then the Client script)
gptoss gpt-oss-120b ids True None None None
[64, 27, 91, 419, 91, 29, 65]
[64, 200007, 65]
a<|end|>b
83 83
score refused
['attached_to', 'base_url', 'claims', 'flags', 'host', 'kind', 'pid', 'port', 'replica', 'started_at']
```
Matches the ticket's expected output exactly, including the two encode lines
measured 2026-09-17 against the gpt-oss-120b tokenizer.

**A14 — the agent service's command and environment, without a GPU.**
```
$ "$VL" -c "... build_command ..."
serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --host 0.0.0.0 --port 8103 --gpu-memory-utilization 0.92 --tensor-parallel-size 1 --max-model-len 131072 --dtype auto
[('CUDA_DEVICE_ORDER', 'PCI_BUS_ID'), ('CUDA_VISIBLE_DEVICES', '0'), ('LD_LIBRARY_PATH', '/home/y-guo/reproduce/new1/envs/cuda-compat-13.0'), ('TRITON_CACHE_DIR', '/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton'), ('VLLM_CACHE_ROOT', '/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache'), ('VLLM_SYSTEM_START_DATE', '2026-08-06'), ('VLLM_USE_FLASHINFER_SAMPLER', '0')]
```
No `--quantization` present; the seven env keys match exactly.

**A15 — the completion request body.**
```
$ "$AW" - <<'PY' ...
pairs: [('he', [123]), ('llo', [456])]
body1: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'skip_special_tokens', 'stream', 'stream_options', 'temperature']
usage: {'prompt_tokens': 7, 'completion_tokens': 2} finish: stop stop: <|return|>
body2: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'seed', 'skip_special_tokens', 'stop', 'stream', 'stream_options', 'temperature', 'top_p']
prompt is ids: True model: gpt-oss-120b path hits: 2
```
Matches exactly: `top_p`, `stop`, `seed` absent from `body1`, present in `body2`.

**A16 — the annotation lines for these two files.**
```
$ python3 - <<'PY' ... PY
Traceback (most recent call last):
  ...
AttributeError: 'Import' object has no attribute 'module'
$ grep -n "/home/\|/net/" models/agent_models/service.py models/probe_models/service.py || echo NO_ABS_PATH
NO_ABS_PATH
```
The `AttributeError` is the **known script defect** the ticket's Comments section
names (`top = {a.module or a.names[0].name for a in t.body if isinstance(a, (ast.Import, ast.ImportFrom))}`
reads `.module` on plain `ast.Import` nodes, which has no such attribute — the
same defect as ticket 05's `B6` and ticket 06's `A16`). Not bent around, per the
ticket's instruction. I re-ran the check's two live assertions by hand, bypassing
only the buggy line, to confirm the two files actually satisfy what the script
intends:
```
models/agent_models/service.py forbid hit: set()
models/agent_models/service.py heavy at top level: set()
models/agent_models/service.py VERSION lines: 1
models/probe_models/service.py forbid hit: set()
models/probe_models/service.py heavy at top level: set()
models/probe_models/service.py VERSION lines: 1
```
Neither file imports `jobs.registry` in any spelling; neither has `torch`,
`transformers` or `vllm` as a top-level import; each has exactly one
`VERSION = ` line. `NO_ABS_PATH` confirms no `/home/` or `/net/` literal.

Also run: `python3 -m py_compile` on both files (clean); `python3 -m
models.agent_models.service --help` and `... models.probe_models.service
--help` (both print their subcommands cleanly). `run.py` does not exist yet on
this branch (later wave), so "Update README.md ... Run `python3 run.py
selfcheck`" is not applicable, per the ticket's own "Selfcheck lines that apply
later" section.

## The commit list

- `e5d8a93` — `T07: the two model services (contracts 7.1, 7.2, 7.4)`: both
  files, the README tree lines, in one commit.

(base `28735bb2437f34af4f85d915b9de22f22530cfaa`; the branch `ticket/2026-09-17-wave3/T07`
has exactly this one commit on top of it.)

## Self-review findings and open questions

- **A real contract gap, filled with a decision, not a guess.** 1.5 says a
  service's endpoint file carries `attached_to`, "the `run_id` of the run that
  owns the server", written when this piece attached rather than started one.
  Neither 7.1's command line nor 7.4's description gives the attaching piece
  any channel to that run_id: `GET /v1/models` exposes only the served model
  name and `max_model_len` (the wave-3 precheck errata already narrows the
  attach comparison to those two), never a run_id. `jobs/launch.py` is the one
  side that already knows the answer — it is the process that searched the
  registry and found the owning row — so I added `--attached-to <run_id>` to
  the `serve --attach-only` command line, following the same shape as the
  `--replica` fix the contracts errata already made to this same command line.
  `serve()` now refuses `--attach-only` without `--attached-to`. This is a
  decision for the owner to confirm or override before `jobs/launch.py` (a
  later ticket) is written against it.
- **`pid` under `--attach-only`.** I write `pid: null`, since this piece starts
  no process of its own and has no way to learn the remote server's pid over
  HTTP. Worth the owner's eye alongside the point above, since `run.py kill`
  (8.6, out of this ticket's scope) will need to know it should never try to
  kill by this piece's `pid` when `attached_to` is set.
- **The render-equals-server check's fixture** (`CHECK_MESSAGES`) is my own
  literal, since the ticket names the two diverging shapes (empty-content
  assistant turn, literal `<|end|>` in content) but not exact message text.
  Built from a system message, a user message, an assistant turn with `content:
  ""`, and an assistant turn with `content: "<|end|>"` — the two cases 7.1 and
  `legacy/pipeline/inject/harmony_render.py:1-18` name. This path is GPU-only
  (`M-M1`, `M-M2`) and not exercised by any CPU acceptance command; worth a
  second look before the first real launch.
- **The `check` subcommand's `<|end|>` fixture check** is implemented as "the
  `special=true` encoding has strictly fewer ids than `special=false`" plus a
  round-trip on the `special=false` side, since `check` only has the four HTTP
  routes to work with and no way to ask the server which token id is `<|end|>`.
  This is weaker than A13's exact-id assertion (which is only possible because
  A13 is run against a real tokenizer and can hardcode today's measured ids);
  `check` has to stay model-agnostic since it runs against whatever agent
  family the run names.
- No test file was added — every requirement of this ticket is proven by an
  acceptance command, per spec section 2, and the ticket names no `tests/`
  seam for these two files.
- YAGNI check: nothing beyond the ticket's two files and the two README lines
  was touched. Kept the two files' retry/JSON-request helpers separate rather
  than sharing one (no `utils.py` exists on this tree, and nothing on either
  file's tree line permits adding one).

## Fix round 1

Branch `ticket/2026-09-17-wave3/T07` (same branch, continued), worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T07-fix1` (removed at the end
of this round). Base of this round: `e5d8a93` (the ticket's first commit,
above).

### F1 (critical) — the `check` subcommand's `<|end|>` fixture was a bare
count comparison, not the ticket's verbatim containment check

Root cause: `check()` compared `len(special["ids"])` against
`len(plain["ids"])`, which can pass even when the special-mode encoding never
actually contains the control-token id and the plain-mode encoding does — the
exact class of divergence 9(d) exists to catch. Replaced the count comparison
with the ticket's literal requirement, made model-agnostic by deriving the
control-token id from the client's own routes: encode `"<|end|>"` alone with
`special=true` (which must collapse to exactly one id, since the whole string
is that one control token), then assert that id is present in the
`special=true` encoding of the fixture and absent from the `special=false`
encoding. The round-trip assertion on the `special=false` side is unchanged.

`models/probe_models/service.py`, `check()`:
```python
plain = client.encode("a<|end|>b", False)
special = client.encode("a<|end|>b", True)
control_ids = client.encode("<|end|>", True)["ids"]
if len(control_ids) != 1:
    ok = False   # prints the unexpected control_ids
else:
    control_id = control_ids[0]
    if control_id in plain["ids"]:
        ok = False   # special=false must contain no control-token id
    if control_id not in special["ids"]:
        ok = False   # special=true must contain the <|end|> id
back = client.decode(plain["ids"])
if back["text"] != "a<|end|>b":
    ok = False
```

### F2 (important) — the undocumented `--attached-to` flag on the agent
service's pinned command line

This is a genuine contract gap, not a coding bug: 1.5 requires `attached_to`
to hold the run_id of the run that *owns* the server, and neither 7.1's
command line nor 7.4's description gives an attaching piece any channel to
that run_id (`GET /v1/models` exposes only the served model name and
`max_model_len`, per the wave-3 precheck errata). Removing the flag would
leave `attached_to` impossible to fill correctly, which is a worse
deviation than the one the finding flags. The finding's actual risk is
silent divergence for the tickets that build this command line later
(`jobs/launch.py`, ticket 08+), since the decision lived only in this
ticket's own report where a later implementer would not see it.

Root-cause fix: formalized the decision the same way the pre-existing
`--replica` gap on this same command line was formalized — as an entry in
`.scratch/from-zero/contract-errata.md`, the file `.scratch/from-zero/spec.md`
section 1 names as the record of exactly this class of decision and the file
a later ticket that depends on one is expected to cite. Added, immediately
after the existing `--replica` entry:

```
- 7.1 / 1.5: `--attach-only` writes `attached_to: <the owning run's run_id>`
  into the endpoint file while the pinned command line gives the attaching
  piece no channel to that run_id (`GET /v1/models` exposes only the served
  model name and `max_model_len`, 7.4's precheck errata) -> `serve
  --attach-only` also takes `--attached-to <run_id>`, required alongside
  `--attach-only` and refused without it, on the same command line as
  `--replica`; `jobs/launch.py` is the side that already knows the answer,
  from the live registry row it searched to find the attachable server
  (7.4), and passes it (planner: models)
```

The code itself (`models/agent_models/service.py`) was already correct
against this decision (the `--attached-to` argument and the `--attach-only`
refusal without it, added in the first round) and needed no change; only the
undocumented-decision part of the finding was open, and it is now closed.

### How the fixes were verified

Reran every acceptance command in the ticket verbatim, from the worktree
root, plus targeted checks for the two findings (no acceptance command in
the ticket exercises `check()` or `--attach-only` directly, so these are
additional, not a replacement for the ticket's own suite).

**A1** (all four interpreters):
```
1 1
1 1
1 1
1 1
```

**A13** (probe service end to end, render-only), unchanged from the first
round:
```
gptoss gpt-oss-120b ids True None None None
[64, 27, 91, 419, 91, 29, 65]
[64, 200007, 65]
a<|end|>b
83 83
score refused
['attached_to', 'base_url', 'claims', 'flags', 'host', 'kind', 'pid', 'port', 'replica', 'started_at']
```

**A14** (agent service command/env), unchanged:
```
serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --host 0.0.0.0 --port 8103 --gpu-memory-utilization 0.92 --tensor-parallel-size 1 --max-model-len 131072 --dtype auto
[('CUDA_DEVICE_ORDER', 'PCI_BUS_ID'), ('CUDA_VISIBLE_DEVICES', '0'), ('LD_LIBRARY_PATH', '/home/y-guo/reproduce/new1/envs/cuda-compat-13.0'), ('TRITON_CACHE_DIR', '/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton'), ('VLLM_CACHE_ROOT', '/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache'), ('VLLM_SYSTEM_START_DATE', '2026-08-06'), ('VLLM_USE_FLASHINFER_SAMPLER', '0')]
```

**A15** (completion request body), unchanged:
```
pairs: [('he', [123]), ('llo', [456])]
body1: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'skip_special_tokens', 'stream', 'stream_options', 'temperature']
usage: {'prompt_tokens': 7, 'completion_tokens': 2} finish: stop stop: <|return|>
body2: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'seed', 'skip_special_tokens', 'stop', 'stream', 'stream_options', 'temperature', 'top_p']
prompt is ids: True model: gpt-oss-120b path hits: 2
```

**A16** (annotation lines): the same known script defect as the first round
(`AttributeError: 'Import' object has no attribute 'module'`, ticket 05's B6
/ ticket 06's A16), reproduced identically and not bent around; the hand
bypass of the buggy line gives the same clean result as the first round
(`forbid hit: set()`, `heavy at top level: set()`, `VERSION lines: 1` for
both files) and `grep -n "/home/\|/net/"` still finds nothing.

**F1, targeted.** Started the render-only probe service (A13's setup) and
called `check()` directly against it with `schema.load_frozen` patched to a
stub `cfg` (`inject=None`, matching a render-only piece):
```
check: family expected='gptoss' got='gptoss'
check: weights expected='gpt-oss-120b' got='gpt-oss-120b'
check: score_train_key expected=None got=None
check: gen_train_key expected=None got=None
check: temperature expected=None got=None
check: render expected='ids' got='ids'
check: encode_special expected=True got=True
RC: 0
```
Then, to confirm the fix actually catches the class of failure the bare
count comparison missed, patched `Client.encode`/`decode`/`health` to a
fake tokenizer where the special-mode encoding is shorter than the
plain-mode one (so the **old** check would have passed) but the control-token
id never appears in the special encoding and a stray control id leaks into
the plain one:
```
check: <|end|> fixture: the special=false encoding contains the control-token id 999
check: <|end|> fixture: the special=true encoding does not contain the control-token id 999
RC: 1
```
Confirms the new check fails exactly where the old one would have silently
passed.

**F2, targeted.** Called `serve()` with `attach_only=True`, `attached_to=None`
(`schema.load_frozen` and `models.agent` patched to stubs so no real run
directory or model table is needed):
```
refused as expected: models.agent_models.service: --attach-only requires --attached-to <run_id>
```

`python3 -m py_compile` on both files: clean. `python3 -m
models.agent_models.service --help` and `... models.probe_models.service
--help`: both print cleanly. `run.py` still does not exist on this branch, so
`run.py selfcheck` remains not applicable, as the first round noted.

### The fix-round commit list

- `74d2a6c` — `T07: fix round 1 (F1 check's <|end|> fixture checks id
  containment not a count; F2 records the --attached-to decision in
  contract-errata.md)`

(base of the round `e5d8a93`; the branch `ticket/2026-09-17-wave3/T07` now
has these two commits on top of the wave-3 base.)

### Self-review

- YAGNI check: touched only `models/probe_models/service.py` (F1) and
  `.scratch/from-zero/contract-errata.md` (F2's documentation); no other
  file, and no refactor beyond the two findings.
- `models/agent_models/service.py` needed no code change for F2 — the first
  round's implementation was already correct against the decision; what was
  missing was the decision's visibility to later tickets, which the errata
  entry now provides.
- Open item carried forward, unchanged from the first round: the
  render-equals-server check's fixture (`CHECK_MESSAGES`) is a literal built
  from the ticket's prose, not exercised by any CPU acceptance command
  (`M-M1`/`M-M2` are GPU-only); still worth a second look before the first
  real launch.

## Post-merge fix round 1

Branch `ticket/2026-09-17-wave3/T07-postfix` (the post-merge fix branch, not a
continuation of the merged `ticket/2026-09-17-wave3/T07`, which no longer
exists as a ref after the merge), worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave3-T07-postfix1` (removed at the
end of this round). Base `cff38ef5d56d11e7c55c3b69fddd90138bfb8ad0` (`from-zero`
HEAD at dispatch, which already carries the merged ticket 07 code). Fixing the
two findings the wave-3 post-merge review verified as real against
`models/agent_models/service.py` and `models/probe_models/service.py`
(`.scratch/from-zero/sdd/2026-09-17-wave3/post-merge-review.json`); the
review's third finding, `SERVICES-2` (the dead `except Exception:
proc.terminate()` guard), was refuted in the same review record (its own
stub run shows the guard does fire on every non-`SystemExit` failure, and no
contract requires the service itself to tear down its child on a check
failure — that is `jobs/launch.launch`'s `teardown_services` per contracts
2.3/8.1) and is out of this round's scope.

### SERVICES-1 (critical) — `build_command` resolved the vllm binary outside the venv

Root cause: `vllm_bin = str(Path(sys.executable).resolve().parent / "vllm")`.
`sys.executable` under an `external/*/bin/python` interpreter is a symlink
into the uv-managed base install (`external/vllm-env/bin/python ->
~/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12`), and
`.resolve()` follows that symlink before taking `.parent`, so `vllm_bin`
pointed at the base interpreter's directory, which holds no `vllm` binary,
while the venv's own `bin/vllm` does. Every non-attach `serve` would raise
`FileNotFoundError` at `subprocess.Popen`, after the card was already
reserved and the start row already appended.

Fix, in `models/agent_models/service.py`, `build_command`: dropped
`.resolve()`, so `vllm_bin` is `Path(sys.executable).parent / "vllm"` — the
directory `sys.executable` itself names, unresolved, which is the venv's
`bin/` for every one of the three `external/*/bin/python` interpreters and
for a bare `python3` alike. No other line of `build_command` changed.

### SERVICES-3 (important) — `check` issued no `/render`, `/score` or `/gen` request

Root cause: `check()` compared the `/health` echo and exercised `/encode` and
`/decode` only, so a probe service whose `/render`, `/score` or `/gen` route
was broken — wrong argument name, wrong shape, an exception the route
mishandles — still passed `check` and let `jobs/launch.py` treat the piece as
up.

Fix, in `models/probe_models/service.py`:
- Two module-level literal fixtures, next to `VERSION`:
  `_CHECK_RENDER_MESSAGES` (a two-message system/user conversation) for
  `/render`, and `_CHECK_PROBE_TEXT` (one line of fixture text) for `/score`
  and `/gen`.
- `check()` now issues, after the existing `/health` and `<|end|>` `/encode`
  /`/decode` checks:
  - `/render` **always** (the render-only case included, since `/render` is
    the route a `sample` run's probe piece actually serves), called as
    `client.render(_CHECK_RENDER_MESSAGES, cfg.generation.effort,
    cfg.generation.date)` — both inputs taken from the frozen setting `check`
    already loaded, matching the agent service's own render check. Validates
    `prefix_ids` is a non-empty list of ints.
  - `/score` and `/gen`, only when `has_inject` (already computed for the
    `/health` comparison rows) — an inject run's probe piece always loads
    both checkpoints, so both routes are live exactly when `has_inject` is
    true. `client.score(_CHECK_PROBE_TEXT)` validates `conf` is a float in
    `[0, 1]` and `label` is a non-empty string. `client.generate(
    _CHECK_PROBE_TEXT, cfg.inject.max_new)` validates `call` is a string —
    `max_new` taken from `cfg.inject.max_new`, the same field
    `agent/inject.py` sends on every real call (contracts 7.2's `/gen` row).
  - Each check prints the route and the value it saw (`check: /render ...`,
    `check: /score ...`, `check: /gen ...`) and clears `ok` to `False` on a
    mismatch, so a failure both names its route in the printed output and
    drives `check`'s exit code non-zero, unchanged from the existing pattern
    the `/health` and `<|end|>` checks already use.
- Not implemented as written in the finding: the finding's shape line reads
  "label one of the labels `/health` echoes." Contracts 7.2's `GET /health`
  field list (`family`, `weights`, `render`, `encode_special`, `decode`,
  `temperature`, `agent_model`, `score_train_key`, `gen_train_key`,
  `max_len`, `device`, `version` — `notes/plans/2026-09-17-contracts.md:4043`)
  carries no `labels` field, and the ticket's `/health` echo line (07,
  around line 214) names the same twelve fields; a class list lives only in
  the checkpoint's own `best/meta.json`, which `check` has no path to (it
  reads only the run directory's `settings.yaml`). Validating `label`
  against a list `/health` does not carry would either always fail or
  require adding a thirteenth `/health` field outside this round's two
  files' scope and outside what any contract or errata entry asks for. Fixed
  at the root against what `check` can actually observe: `label` is checked
  to be a non-empty string, the shape `/score`'s route contract actually
  promises ("the argmax class name," contracts 7.2's `/score` row); worth
  the owner's eye if a stronger check is wanted.

### How the fixes were verified

Reran every acceptance command in the ticket verbatim from the worktree
root, plus targeted checks for both findings.

**A1** (all four interpreters):
```
1 1
1 1
1 1
1 1
```

**A13** (probe service end to end, render-only), unchanged:
```
gptoss gpt-oss-120b ids True None None None
[64, 27, 91, 419, 91, 29, 65]
[64, 200007, 65]
a<|end|>b
83 83
score refused
['attached_to', 'base_url', 'claims', 'flags', 'host', 'kind', 'pid', 'port', 'replica', 'started_at']
```

**A14** (agent service command/env), unchanged:
```
serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --host 0.0.0.0 --port 8103 --gpu-memory-utilization 0.92 --tensor-parallel-size 1 --max-model-len 131072 --dtype auto
[('CUDA_DEVICE_ORDER', 'PCI_BUS_ID'), ('CUDA_VISIBLE_DEVICES', '0'), ('LD_LIBRARY_PATH', '/home/y-guo/reproduce/new1/envs/cuda-compat-13.0'), ('TRITON_CACHE_DIR', '/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton'), ('VLLM_CACHE_ROOT', '/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache'), ('VLLM_SYSTEM_START_DATE', '2026-08-06'), ('VLLM_USE_FLASHINFER_SAMPLER', '0')]
```

**SERVICES-1, targeted.** `A14`'s script prints only `argv[1:]`, which is
exactly why the review says "the CPU acceptance did not see it"; extended it
to print `argv[0]` and check it on disk, under the vllm interpreter:
```
$ "$VL" -c "
import os
from models.agent_models.service import build_command
import models
m = models.agent('gpt_oss_120b')
row = dict(role='agent', family='gptoss', weights='gpt-oss-120b', dtype='auto',
           quantization=None, max_model_len=131072, served_model_name='gpt-oss-120b',
           env_result={'VLLM_USE_FLASHINFER_SAMPLER': '0'}, extra_flags='')
argv, env = build_command(row, m.serving, m.weights_path, 8103, '0', '2026-08-06')
print('argv[0]:', argv[0])
print('exists on disk:', os.path.exists(argv[0]))
"
argv[0]: /home/y-guo/reproduce/new1/external/vllm-env/bin/vllm
exists on disk: True
```
For contrast, the pre-fix formula on the same interpreter:
```
old (broken) argv[0]: /home/y-guo/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/vllm
old exists on disk: False
```

**A15** (completion request body), unchanged:
```
pairs: [('he', [123]), ('llo', [456])]
body1: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'skip_special_tokens', 'stream', 'stream_options', 'temperature']
usage: {'prompt_tokens': 7, 'completion_tokens': 2} finish: stop stop: <|return|>
body2: ['add_special_tokens', 'max_tokens', 'model', 'prompt', 'return_token_ids', 'seed', 'skip_special_tokens', 'stop', 'stream', 'stream_options', 'temperature', 'top_p']
prompt is ids: True model: gpt-oss-120b path hits: 2
```

**A16** (annotation lines): the same known script defect as both earlier
rounds (`AttributeError: 'Import' object has no attribute 'module'`, ticket
05's `B6` / ticket 06's `A16`), reproduced identically and not bent around;
the hand bypass of the buggy line gives the same clean result as both earlier
rounds (`forbid hit: set()`, `heavy at top level: set()`, `VERSION lines: 1`
for both files) and `grep -n "/home/\|/net/"` still finds nothing
(`NO_ABS_PATH`).

**SERVICES-3, targeted — render-only (`has_inject=False`).** Started the
probe service exactly as in `A13` (render-only, CPU), then ran `check` against
it with `schema.load_frozen` patched to a stub frozen setting (`inject=None`):
```
check: family expected='gptoss' got='gptoss'
check: weights expected='gpt-oss-120b' got='gpt-oss-120b'
check: score_train_key expected=None got=None
check: gen_train_key expected=None got=None
check: temperature expected=None got=None
check: render expected='ids' got='ids'
check: encode_special expected=True got=True
check: /render prefix_ids is a non-empty list of ints: True (got [200006, 17360, ... 173781])
RC: 0
```
`/render` is now issued and validated even under `has_inject=False`; `/score`
and `/gen` are correctly not called (no score/gen checkpoint is loaded under
`--render-only`, so calling them would 503).

**SERVICES-3, targeted — inject mode (`has_inject=True`), all four routes.**
A hand-written stub HTTP server implementing `/health`, `/score`, `/gen`,
`/render`, `/encode`, `/decode` with well-formed responses, `check` run
against it with `schema.load_frozen` patched to a stub setting carrying a
non-`None` `inject` and `cfg.inject.max_new = 64`:
```
check: family expected='gptoss' got='gptoss'
check: weights expected='gpt-oss-120b' got='gpt-oss-120b'
check: score_train_key expected='deadbeef' got='deadbeef'
check: gen_train_key expected='cafef00d' got='cafef00d'
check: temperature expected=0.7 got=0.7
check: render expected='ids' got='ids'
check: encode_special expected=True got=True
check: /render prefix_ids is a non-empty list of ints: True (got [1, 2, 3])
check: /score conf is a float in [0,1]: True (got 0.73)
check: /score label is a non-empty str: True (got 'read_email')
check: /gen call is a str: True (got 'apis.example.sample_api(x=1)')
RC: 0
```
All four routes (`/render`, `/score`, `/gen`, plus the pre-existing
`/health`/`/encode`/`/decode` checks) are now exercised in inject mode.

**SERVICES-3, targeted — the failure path names its route.** Same stub
server, with `/render` answering an empty `prefix_ids` and `/score` answering
a `conf` of `1.5` (out of `[0, 1]`):
```
check: /render prefix_ids is a non-empty list of ints: False (got [])
check: /score conf is a float in [0,1]: False (got 1.5)
check: /score label is a non-empty str: True (got 'read_email')
check: /gen call is a str: True (got 'apis.example.sample_api(x=1)')
RC: 1
```
Confirms a broken `/render` or `/score` route now fails `check` with the
route named in the printed line and the exit code non-zero, which
`jobs/launch.py` reads as `service_check` (contracts 8.1).

`python3 -m py_compile` on both files: clean. `python3 -m
models.agent_models.service --help` and `... models.probe_models.service
--help`: both print cleanly. `run.py` still does not exist on this branch, so
`run.py selfcheck` remains not applicable, unchanged from both earlier
rounds.

### The fix-round commit list

- `e75eb38` — `T07: post-merge fix round 1 (SERVICES-1, SERVICES-3)`

(base of this round `cff38ef5d56d11e7c55c3b69fddd90138bfb8ad0`, the
`from-zero` HEAD the dispatch named; the branch
`ticket/2026-09-17-wave3/T07-postfix` has this one commit on top of it.)

### Self-review

- YAGNI check: touched only `models/agent_models/service.py` (SERVICES-1) and
  `models/probe_models/service.py` (SERVICES-3); no other file, no refactor
  beyond the two findings, `README.md` left unchanged since no line of it
  describes `.resolve()` or `check`'s exact route list and none became
  wrong.
- `SERVICES-2` (the `terminate()` guard) is not touched: the review's own
  verdict on that finding says it is not real, and neither this dispatch's
  "Open findings" list nor the errata names it, so it is out of scope for
  this round.
- Open item carried forward from the first round and both fix rounds,
  unchanged: the render-equals-server check's fixture (`CHECK_MESSAGES` in
  the agent service) is a literal built from the ticket's prose, not
  exercised by any CPU acceptance command (`M-M1`/`M-M2` are GPU-only);
  still worth a second look before the first real launch.
- New, this round: `check`'s two new fixtures (`_CHECK_RENDER_MESSAGES`,
  `_CHECK_PROBE_TEXT`) are literals of my own choosing, since neither the
  ticket nor the finding names exact fixture text for these two routes (only
  `CHECK_MESSAGES` on the agent-service side has ticket-specified content);
  they are exercised by the targeted verification above but not by any GPU
  run yet.
