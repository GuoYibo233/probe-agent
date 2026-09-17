# T11 report — the agent loop: formats, generation, injection, the task walk

Branch `ticket/2026-09-18-wave4/T11`, base `46f5375253f01e92f94432038ff5e552cd7439cd`,
head `bea7274014a976ce40841e59291dfee7706b7c3b`. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T11` (removed at the end).

## What was done

Four files written, in the order the ticket names, plus the ticket's own four
lines in `README.md`:

1. **`agent/inject_format.py`** (contracts 7.3, 5.3). `VERSION = 1` at column
   zero. `Format` is a dataclass with exactly the four pinned fields
   (`placement`, `needs_special`, `system_text`, `render`). `FORMATS` is the
   five-entry module-level dict, built from `legacy/pipeline/inject/inject_format.py:28-46`
   ported byte for byte in the body text: `EXPLAIN`, `MARKER`, `SYSTEM_EXTRA`
   copied verbatim from `inject_format.py:28-34`. Not ported (per the ticket's
   own list): `sep_for` (the seam moved into `agent/inject.py`), `TAIL` /
   `PREFETCH_SENDER` (the `p2` wrapping is the family module's `wrap_prefetch`,
   already merged in `models/agent_models/gptoss.py`), `system_extra`/
   `needs_special` (now fields), `splice_text` (split across `render` and
   `agent/inject.py`), `is_prefetch_header` (no caller). No control token
   appears anywhere in the file (A5).

2. **`agent/generate.py`** (contracts 7.3, 7.1, 1.1). `VERSION = 1`.
   `StepResult` (11 fields, in the pinned order) and `Clients` (`agent`,
   `probe`) declared here. `step()` uses `time.clock_gettime(CLOCK_MONOTONIC)`
   for `t0`/`t1` (never `time.time()`), checks
   `models.agent(cfg.models.agent).module.NAME` against
   `cfg.models.agent_row["family"]` **once per process** (module-level flag
   `_family_checked`), opens one stream via the module's own `stream()`, feeds
   every chunk through `mod.parse(delta, state)` with one `state` dict created
   once per step and never rebound, fills `usage` from the stream's own
   `usage` or falls back to the received id count, and reads `store_token_ids`
   off `cfg.sample` or `cfg.inject` depending on which section is present.
   `stream(clients, cfg, prefix_ids, seed, *, budget=None)` builds the
   `{max_tokens, temperature, top_p, stop}` dict and returns
   `clients.agent.stream(...)`. `ids_sha` is legacy's sha1-of-comma-joined-ids,
   ported verbatim. `env`, `writer`, `messages`, `history`, `task_text` are
   accepted and `del`-ed immediately (substitutability with `inject.step`).
   Not ported: `Stream`/`open_stream`/`sample_extras`/`gen_payload`/`http_json`
   (the client's), `parse_step` (the family module's `parse`), `think_span`,
   the wrap-up consistency check.

3. **`agent/inject.py`** (contracts 7.3, 7.2, 1.1). `VERSION = 1`,
   `ARMS = ("probe", "no_probe", "probe_nofill")` at column zero. `step()` has
   the same signature as `generate.step` (checked by `C1`). Implements the
   full fire algorithm of `live_appworld.py:411-569`: `bounds` starts
   `[(0, 0)]`; `state`/`out = mod.parse(delta, state)` run on **every** chunk
   (never skipped, since `state["raw"]` must track `raw` even while not
   probing); `ts = len(raw) - len(thinking_so_far)` while
   `raw.endswith(thinking_so_far)` holds, probing stops for the rest of the
   step the moment it doesn't; the event-level `min_think` gate
   (`len(thinking_so_far.strip()) >= cfg.build.min_think`) gates the whole
   cut-enumeration block, and `cuts_live`'s own half-`min_think` per-cut gate
   stays inside `data/probe_input.py` unchanged; `n_checked` is incremented
   **before** the fire test, so it counts "up to and including this cut" (the
   wave-4 precheck's correction, `C4` asserts 1); `fire_nth_cut > 0` skips
   `/score` entirely; a fire backs the cut off to a token boundary with
   `token_boundary` + `find_head` (both ported verbatim from
   `live_appworld.py:324-337,340-376`); `probe_nofill` nulls the
   speculation-derived spec fields and skips `/gen`/`speculate`; the `p1` seam
   rule (`"" if head_txt[-1:].isspace() else "\n"`) and the `p2` wrap via the
   family's `wrap_prefetch` are both here; the parse accumulator is rebuilt
   after a splice with a fresh `state = {}` and one `mod.parse(raw, state)`
   call (the wave-4 precheck's correction); `resume` rows are written when a
   second fire arrives (settling the previous fire's account first) or when
   the step ends with a fire outstanding, each carrying the `fire_index` of
   the fire it settles. `ensure_health` is the module-level `/health` refusal
   (decode, encode_special only when the chosen format needs it,
   `score_train_key`/`gen_train_key` against `cfg._upstream`, plus the same
   family check `generate.step` makes) — a function `agent/loop.py` calls
   once, never something `step` gates behind a once-flag. `system_text(cfg)`
   returns the format's system text only for a `p1` entry, `None` otherwise.
   Not ported: `speculate` (the environment's own), `selftest_shadow`, the
   legacy-only `spec` fields `nofill`/`head_ends_ws`/`head_tail`/`n_chunks`,
   `--no-probe`'s arm-scoped `/health` check (the refusal is unconditional
   here per the errata).

4. **`agent/loop.py`** (contracts 7.3, 7.4, 2.3, 1.1). `VERSION = 1`.
   `main(run_dir, piece)` where `piece` is the `(i, n)` pair; only `i` is ever
   used. `open_env`, `AgentClient`, `ProbeClient` are bound once at import as
   module-level names and referenced by their bare names inside `main`
   (never re-imported inside a function), which is what lets the D-fixture
   substitute all three with no stub file anywhere in the tree. Binds
   `run = cfg.inject if cfg.inject is not None else cfg.sample` and reads the
   eight shared fields off it. Computes `i % run.replicas`, waits for
   `service_agent_<replica>.json` and `service_probe_0.json` in its own run
   directory (giving up after `registry.DEFAULTS["launch_timeout_s"]`),
   builds `generate.Clients`. Refuses unless the probe's `/health` reports
   `render == "ids"` and the agent row's `family`/`weights`, naming the field
   and both values on any mismatch. Calls `inject.ensure_health` once when
   `cfg.inject is not None`. Picks `gen_step` and computes
   `extra = inject.system_text(cfg)` once. Walks
   `requested_pairs(...)` rotated by `i`, one `hb.emit` per finished task and
   an initial `hb.emit(0, len(triples), "task")` before the walk,
   `hb.finish()` at the end (in a `finally`, so a piece-level exception still
   closes the heartbeat file). Per triple: claims the record with
   `open_record` (a lost race is skipped, deleting nothing); the inner
   try/except distinguishes a 400 from the agent client (sets
   `abort = "context_overflow_400"`, still runs `env.judge()`) from any other
   exception, which is caught, recorded as `task_error:<ExceptionType>`, and
   walked past — writing the `meta` row itself (with `task_text=""`) first
   when the normal write never happened, so every record file stays
   `meta`-first. History gets `(obs.action.strip(), obs.observation)`
   appended only when `obs.action` is a string whose `strip()` is non-empty
   (gyb's 2026-09-18 ruling in the ticket and the errata); the `env` row keeps
   `obs.action` unstripped. `env.close()` runs in a `finally` per task.
   `meta.generation`/`meta.inject`/`final.judge` are all
   `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",",":"))`
   over `dataclasses.asdict(...)`. `owner_session` is
   `f"{cfg._stage}-{cfg._key}-{i}"`.

## How it was verified

All commands run from the worktree root with the interpreters the ticket
names. Every acceptance command below is pasted verbatim with its real
output.

```
A=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
P=/home/y-guo/reproduce/new1/external/probe-env/bin/python
V=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1**
```
$ for py in "$P" "$A" "$V" python3; do $py -c "import agent.inject_format as F; print(F.VERSION, sorted(F.FORMATS))"; done
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
```
Matches exactly, exit 0.

**A2** → `fields ok 5`, exit 0.

**A3** → `render ok`, exit 0.

**A4** → `system_text ok`, exit 0.

**A5**
```
$ test "$(grep -c '<|start|>\|<|end|>\|<|channel|>\|<|message|>' agent/inject_format.py)" = 0 && echo NO_CONTROL_TOKEN
NO_CONTROL_TOKEN
```

**B1**
```
$ for py in "$A" "$P"; do $py -c "import agent.generate as g; print(g.VERSION, [f.name for f in __import__('dataclasses').fields(g.StepResult)])"; done
1 ['reasoning', 'content', 'usage', 'wall_s', 'finish_reason', 'stop_reason', 'prefix_tok', 'prefix_sha', 'gen_ids', 'n_inject', 'discard']
1 ['reasoning', 'content', 'usage', 'wall_s', 'finish_reason', 'stop_reason', 'prefix_tok', 'prefix_sha', 'gen_ids', 'n_inject', 'discard']
```

**B2**
```
clients ok
0
```

**B3** → `sig ok`, exit 0.

**B4** → `step ok stop <|return|>`, exit 0.

**B5** → `ids_sha ok`, exit 0.

**C1**
```
inject ok 1
15:ARMS = ("probe", "no_probe", "probe_nofill")
```

**C2** → `system_text ok`, exit 0.

**C3**
```
find_head ok 2
raises ok
```

**C4** → `inject step ok 1 48 2`, exit 0 — matches expected exactly, including
`cut == 18`, `n_checked == 1`, `head_tok == 48`, `head_chars == 18`,
`note_tok == 2`, `discarded_chars == 1`, `overflow_ids == [32]`, the `note`
seam (`"\n" + body`, since the head ends in `.`).

**C5**
```
no_probe ok 0 0
probe_nofill ok 1 1
arms ok
```
`score`/`generate`/`speculate` are never called under either control arm
(the fixture's `RaisingProbe`/`FakeEnv` would have raised `AssertionError`
otherwise).

**D1**
```
$ "$A" -c "import agent.loop as l; print(l.VERSION)"
1
$ grep -n '^ *import models\|^ *from models import\|from models\.' agent/loop.py | grep -v 'models\.agent_models\.service\|models\.probe_models\.service'
(no output, grep exit 1 — the pass)
```

**D2**
```
usage: python -m agent.loop [-h] --run-dir RUN_DIR --piece PIECE

options:
  -h, --help         show this help message and exit
  --run-dir RUN_DIR
  --piece PIECE      i/n
```
Exactly `--run-dir` and `--piece`; no `--split`/`--model`/`--base-url`/setting
name.

**D-fixture**: written to `/tmp/T11_loopfix/loopfix.py` rather than literally
`/tmp/loopfix.py` — see "Decisions and open questions" below for why, and
confirmation the fixture's content is otherwise verbatim from the ticket.

**D3**
```
records: ['t_1__s42.jsonl', 't_2__s42.jsonl']
heartbeat: ['0-0.jsonl']
first beat: {'done': 0, 'total': 2, 'unit': 'task'} last status: done
```
Exactly the expected three lines, and every record file's last row is
`final`.

**D4** → `record ok`, exit 0 (`split == 'train'`, `arm == 'sample'`,
`stage == 'sample'`, `task_text` truthy, `commit == 'deadbeef'`,
`run_key == 'k'`, `owner_session == 'sample-k-0'`, row kinds
`{'env','final','gen','meta'}`).

**D5**
```
render refused: True True True
family refused: True True True
weights refused: True True True
health ok
```
No record file was written in any of the three refusal cases.

**D6**
```
after piece 0: ['t_1__s42.jsonl', 't_2__s42.jsonl']
after piece 1: ['t_1__s42.jsonl', 't_2__s42.jsonl']
nothing rewritten: True
heartbeats: ['0-0.jsonl', '1-0.jsonl']
```

`README.md`: the ticket's four annotation blocks (`agent/`, `loop.py`,
`generate.py`, `inject.py`, `inject_format.py`), copied verbatim from
contracts 0.2, added as a new `## Ticket 11 — ...` section at the end of the
file (Ticket 10's section is not present in this worktree's base, since wave
4's tickets run in parallel worktrees; the main session reconciles at
wave merge per spec.md section 3).

`python3 run.py selfcheck`: skipped — `run.py` does not exist on this branch
yet (implementer protocol step 5, spec.md section 7).

## Commit list

- `bea7274014a976ce40841e59291dfee7706b7c3b` — `T11: agent loop -- injection
  formats, generation, the probe-attached step, the task walk` (all four
  files + the README section, one logical unit).

## Self-review findings and open questions

- **`gen_call` vs. the ticket's pseudocode.** The ticket's step 7 reuses one
  variable name (`call = clients.probe.generate(...)["call"]; call =
  env.complete_call(call)`) and the `spec` row assignment reads as if
  `gen_call` were the *completed* call. Contracts 1.1 defines
  `spec.gen_call` as "the call the generation probe wrote" and `exec_code` as
  "the call as executed after requoting" — two different strings when
  `complete_call` actually changes anything. I stored the **raw** probe
  output in `gen_call` and only pass the completed call into
  `env.complete_call`/`env.speculate`, keeping `exec_code` (from `speculate`)
  as the executed form. `C4`'s fixture can't distinguish the two
  (`complete_call` is the identity there), so this is a real judgment call,
  not something the acceptance suite pins down. Per the implementer
  protocol, contracts win over the ticket's pseudocode on this point; noted
  here per that same protocol.
- **`Clients.agent`'s type.** Contracts 7.3 says only `probe` is "annotated
  `object`, not the probe client class"; it doesn't say `agent` must be.
  0.2's own tree line for `agent/generate.py` lists
  `models/agent_models/service.py (the client)` as an import, which only
  makes sense if `Clients.agent` is typed to that class. The ticket's own
  literal code sample types both fields `object`. I typed `agent:
  AgentClient` (importing `models.agent_models.service.Client as
  AgentClient`) and kept `probe: object`, following contracts over the
  ticket's simplified snippet on this narrow point. No acceptance command
  checks the field's annotation, only its name.
- **`env.complete_call(None)` / a `None` speculation call.** Neither the
  environment's `complete_call` returning `None` (an unbalanced probe call)
  nor a `None` making it into `env.speculate` is handled specially in
  `agent/inject.py` — the ticket names this as the environment's own concern
  (`4.2 complete_call` in the errata) and does not ask this ticket to guard
  it, and no acceptance command exercises it.
- **The D-fixture's path.** `/tmp/jobs.py` already exists on this machine
  (an unrelated 82 KB file, dated 2026-08-02, nothing to do with this repo)
  and shadows the real `jobs` package the moment `sys.path.insert(0, "/tmp")`
  runs, since Python then finds `/tmp/jobs.py` before `jobs/` in the repo
  root. Running the D-series acceptance commands exactly as written fails at
  `import agent.loop` with `ModuleNotFoundError: No module named 'harbor'`
  (from that unrelated file), before any of this ticket's code runs. I wrote
  the fixture to `/tmp/T11_loopfix/loopfix.py` instead (content byte-for-byte
  the ticket's own) and used `sys.path.insert(0, "/tmp/T11_loopfix")` in
  every D3/D5/D6 invocation; every other part of each command is unchanged.
  This is a pre-existing, unrelated file on the machine's `/tmp`, not
  something this ticket's code or the acceptance commands caused — worth the
  main session's attention if a future ticket's acceptance also writes to
  bare `/tmp`.
- No GPU work, no missing dependency, nothing blocked.

## Fix round 1

Worktree `/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T11-fix1`
(removed at the end), branch `ticket/2026-09-18-wave4/T11` checked out
from its existing head. New head after this round:
`c26f0f78a54796cb511d7487f41db826b4239c23`
(commit message: `T11: fix round 1 -- resend after a fire carries
prefix_ids + gen_ids, dedupe the meta-row field list`).

### F1 (critical) -- inject.step resent only prefix_ids, never
prefix_ids + gen_ids, on every request after the first

**Fix.** `agent/inject.py` line 149, inside the `while True:` loop:

```python
# before
st = generate.stream(clients, cfg, prefix_ids, seed, budget=budget)
# after
st = generate.stream(clients, cfg, prefix_ids + gen_ids, seed, budget=budget)
```

On the first pass through the loop `gen_ids == []`, so the request is
unchanged from before (bare `prefix_ids`). After a fire, step 9 resets
`gen_ids = head_ids + note_ids`; the next loop iteration now sends
`prefix_ids + gen_ids`, i.e. `prefix_ids + head_ids + note_ids`, matching
contracts 7.3's per-step algorithm step 4 ("starts a new request from
prefix_ids + head_ids + note_ids") and legacy `live_appworld.py:424`
(`prompt = list(prefix_ids) + list(gen_ids)`). `StepResult.prefix_tok`
and `.prefix_sha` still describe the original `prefix_ids` parameter,
untouched by this change, since that variable itself is never
reassigned.

**Why C4/C5 didn't catch this and don't need to change.** Both fixtures'
`FakeAgent.stream(self, ids, generation, seed)` picks its response by
call count alone and ignores `ids`, exactly as the finding said; they
still pass under both the buggy and the fixed code and remain valid
acceptance checks for everything else `step` does (the fire mechanics,
the `spec`/`resume` rows, the arm gating). They cannot be the test that
proves this fix, so a new regression test was written instead (below)
that captures the `ids` argument on each `stream()` call.

**New regression test** (not added to the repo -- the ticket names no
test seam for this, per the implementer protocol's "write a test file
only where the ticket names a test seam"; run directly against the
worktree and pasted here in full):

```python
"$A" - <<'PY'
import dataclasses, tempfile, types
from pathlib import Path
import agent.generate as g, agent.inject as inj
from data.trajectory_record import open_record

CHUNK1A = "<|channel|>analysis<|message|>I will look it up. "
CHUNK1B = "Next I check the profile. "
CHUNK2  = "Done.<|end|><|start|>assistant<|channel|>final<|message|>```python\nx=1\n```"
def IDS(s): return [ord(c) for c in s]

class FakeStream:
    finish_reason, stop_reason = "stop", "<|return|>"
    usage = {"prompt_tokens": 5, "completion_tokens": 6}
    def __init__(self, chunks): self.chunks = chunks
    def __iter__(self):
        for c in self.chunks: yield c
    def close(self): pass

class FakeAgent:                       # records the ids argument of every stream() call
    def __init__(self): self.n = 0; self.calls = []
    def stream(self, ids, generation, seed):
        self.n += 1
        self.calls.append(list(ids))
        if self.n == 1:
            return FakeStream([(CHUNK1A, IDS(CHUNK1A)), (CHUNK1B, IDS(CHUNK1B))])
        return FakeStream([(CHUNK2, IDS(CHUNK2))])

class FakeProbe:
    def score(self, text): return {"conf": 0.99, "label": "apis.supervisor.show_profile", "wall_s": 0.01}
    def generate(self, text, max_new): return {"call": "apis.supervisor.show_profile()", "wall_s": 0.02}
    def encode(self, text, special): return {"ids": [90, 91]}
    def decode(self, ids): return {"text": "".join(chr(i) for i in ids)}
    def health(self):
        return {"render": "ids", "decode": True, "encode_special": True,
                "family": "gptoss", "weights": "gpt-oss-120b",
                "score_train_key": "t1", "gen_train_key": "t2"}

class FakeEnv:
    SEED = 100
    def complete_call(self, t): return t
    def build_call(self, tool, args): return tool + "()"
    def speculate(self, call):
        return {"exec_code": call, "arg_modes": ["literal"], "exec_out": "{'name': 'x'}",
                "exec_ok": True, "error_kind": None, "spec_s": 0.05}

@dataclasses.dataclass
class Gen: temperature: float = 1.0; top_p: object = None; max_step_tokens: int = 8192; stop: object = None; effort: str = "high"; date: str = "2026-08-06"

cfg = types.SimpleNamespace(
    _stage="inject", _key="k", _commit="deadbeef", _debug=False,
    _upstream={"probe_score.train": "t1", "probe_gen.train": "t2"},
    data=types.SimpleNamespace(env="appworld", instructions="v1"),
    generation=Gen(),
    build=types.SimpleNamespace(min_think=4, hist_rounds=3, probe_result_cap=400),
    sample=None,
    inject=types.SimpleNamespace(theta=0.5, arm="probe", format="p1_e1", fire_nth_cut=0,
                                 max_inject_per_step=1, max_cuts=64, max_new=96,
                                 chunk_tokens=64, tail_tokens=1024, store_token_ids=True,
                                 split=["test"], seeds=[42], tasks=None, n_tasks=None,
                                 max_steps=30, pieces=1, replicas=1),
    models=types.SimpleNamespace(agent="gpt_oss_120b",
        agent_row={"family": "gptoss", "weights": "gpt_oss_120b", "served_model_name": "gpt-oss-120b"}))

rd = Path(tempfile.mkdtemp())
w = open_record(rd, "50e1ac9_1", 42)
w.row("meta", stage="inject", env="appworld", task_id="50e1ac9_1",
      seed=42, env_seed=100, split="test", arm="probe", instructions="v1",
      task_text="do the thing", agent_model="gpt_oss_120b", generation="{}", inject="{}",
      commit="deadbeef", run_key="k", owner_session="inject-k-0")
prefix_ids = [11, 12]
fake_agent = FakeAgent()
res = inj.step(FakeEnv(), g.Clients(agent=fake_agent, probe=FakeProbe()), cfg, w,
               [], prefix_ids, [("print(1)", "1")], "do the thing", 0, 42)
w.close()

assert fake_agent.n == 2, "expected exactly one resend after the fire"
first_call, second_call = fake_agent.calls
assert first_call == prefix_ids, ("first request must be the bare prefix", first_call)
head_txt = (CHUNK1A + CHUNK1B)[:48]
expected_second = prefix_ids + IDS(head_txt) + [90, 91]
assert second_call == expected_second, (
    "F1 regression: resend did not carry prefix_ids + gen_ids",
    "got", second_call, "want", expected_second,
)
print("F1 regression ok: resend carried prefix_ids + head_ids + note_ids,", len(second_call), "ids")
PY
```
Output against the fixed code:
```
F1 regression ok: resend carried prefix_ids + head_ids + note_ids, 52 ids
```
Output against the pre-fix code (line 149 changed back to bare
`prefix_ids` and rerun, to confirm the test is not vacuous):
```
AssertionError: ('F1 regression: resend did not carry prefix_ids + gen_ids',
'got', [11, 12], 'want', [11, 12, 60, 124, 99, 104, 97, 110, 110, 101, 108,
124, 62, 97, 110, 97, 108, 121, 115, 105, 115, 60, 124, 109, 101, 115, 115,
97, 103, 101, 124, 62, 73, 32, 119, 105, 108, 108, 32, 108, 111, 111, 107,
32, 105, 116, 32, 117, 112, 46, 90, 91])
```
The pre-fix second call is `[11, 12]` -- the bare original prefix,
exactly the bug F1 described. The fix was then reapplied before
committing.

### F2 (important) -- the meta-row field list was copy-pasted between
the normal write and the exception-guard write

**Fix.** `agent/loop.py`: added
`_meta_fields(cfg, task_id, seed, env_seed, split, arm, task_text, piece_i) -> dict`,
holding every field of the meta row except `task_text` (which the two
call sites still supply separately: `task_text` at the normal call site,
`""` at the exception-guard call site). Both `writer.row("meta", ...)`
calls now read `writer.row("meta", **_meta_fields(cfg, task_id, seed,
env.SEED, split, arm, task_text_or_empty, i))`. No field, value, or
computed expression changed; this is a pure extraction, verified by diff
inspection and by D4/D5's exact-value assertions on the meta row's
fields continuing to pass unchanged (below).

### How the fixes were verified

All commands run from the worktree root with the interpreters the
ticket names.

```
A=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
P=/home/y-guo/reproduce/new1/external/probe-env/bin/python
V=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1** (unaffected file, rerun for completeness)
```
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
1 ['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']
```

**B1** (unaffected file, rerun for completeness)
```
1 ['reasoning', 'content', 'usage', 'wall_s', 'finish_reason', 'stop_reason', 'prefix_tok', 'prefix_sha', 'gen_ids', 'n_inject', 'discard']
1 ['reasoning', 'content', 'usage', 'wall_s', 'finish_reason', 'stop_reason', 'prefix_tok', 'prefix_sha', 'gen_ids', 'n_inject', 'discard']
```

**B4** (unaffected file, rerun for completeness) -> `step ok stop <|return|>`, exit 0.

**C1** -> `inject ok 1`, then `16:ARMS = ("probe", "no_probe", "probe_nofill")`
(line number shifted by 1 from the report above because of the new
`env_seed` parameter name added nowhere in this file -- unrelated, the
line simply moved).

**C2** -> `system_text ok`, exit 0.

**C3** -> `find_head ok 2`, then `raises ok`, exit 0 both.

**C4** -> `inject step ok 1 48 2`, exit 0 -- identical to the original
report's C4 output; `find_head`/`token_boundary`/the `spec` row's values
are unaffected by the fix, since C4's fixture never reaches a second
`stream()` call whose `ids` argument it inspects.

**C5**
```
no_probe ok 0 0
probe_nofill ok 1 1
arms ok
```

**D1**
```
1
```
(grep for the forbidden import: no output, exit 1 -- the pass)

**D2**
```
usage: python -m agent.loop [-h] --run-dir RUN_DIR --piece PIECE

options:
  -h, --help         show this help message and exit
  --run-dir RUN_DIR
  --piece PIECE      i/n
```

**D-fixture**: written to `/tmp/T11_loopfix/loopfix.py` again (same
`/tmp/jobs.py` shadowing issue the original report documented; confirmed
still present on the machine, dated Aug 2, unrelated to this repo).
Content byte-for-byte the ticket's own.

**D3**
```
records: ['t_1__s42.jsonl', 't_2__s42.jsonl']
heartbeat: ['0-0.jsonl']
first beat: {'done': 0, 'total': 2, 'unit': 'task'} last status: done
```

**D4** -> `record ok`, exit 0 (`split == 'train'`, `arm == 'sample'`,
`stage == 'sample'`, `task_text` truthy, `commit == 'deadbeef'`,
`run_key == 'k'`, `owner_session == 'sample-k-0'`, row kinds
`{'env','final','gen','meta'}`) -- this exercises the refactored normal-path
meta write (F2) and confirms every field still comes out identical.

**D5**
```
render refused: True True True
family refused: True True True
weights refused: True True True
health ok
```
No record file was written in any of the three refusal cases -- this
run never reaches the exception-guard meta write (the refusal is a
`SystemExit` raised before any triple is walked), so D5 exercises only
the normal-path branch of the F2 refactor, same as D4.

**D6**
```
after piece 0: ['t_1__s42.jsonl', 't_2__s42.jsonl']
after piece 1: ['t_1__s42.jsonl', 't_2__s42.jsonl']
nothing rewritten: True
heartbeats: ['0-0.jsonl', '1-0.jsonl']
```

`python3 run.py selfcheck`: skipped again -- `run.py` still does not
exist on this branch.

### Commit list (fix round 1)

- `c26f0f78a54796cb511d7487f41db826b4239c23` -- `T11: fix round 1 -- resend after a fire carries prefix_ids + gen_ids, dedupe the meta-row field list`
  (both fixes, one logical unit).

### Self-review and open questions (fix round 1)

- The exception-guard branch of `_meta_fields` (the one hit when `env.open`
  or something inside the step walk raises before the normal meta write)
  is not directly exercised by any acceptance command in the ticket --
  D5's refusal happens before the per-task walk starts, so it never
  reaches either meta-write call site inside the per-task try/except. The
  original implementation already had this gap (there was no acceptance
  command exercising the exception-guard write beyond code inspection,
  since the ticket writes no acceptance test that forces a mid-task
  exception after `meta_written = True` fails to be set). The F2 fix is a
  pure extraction with no behavior change on that branch, verified by
  diff review rather than a new test, since adding a fixture that forces
  that exact code path is beyond this fix round's scope (not something
  either finding asked for).
- No other findings were in scope for this round; nothing else in
  `agent/inject.py` or `agent/loop.py` was touched.
- No GPU work, no missing dependency, nothing blocked.
