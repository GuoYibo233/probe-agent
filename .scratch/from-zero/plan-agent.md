# Build plan: `agent/` (loop.py, generate.py, inject.py, inject_format.py)

Planner: agent folder. Written 2026-09-17 against
`notes/plans/2026-09-14-structure-from-zero.md` (Part 1 tree, fixed),
`notes/plans/2026-09-17-contracts.md` (Parts 0.2, 1.1, 1.7, 2.1, 2.3, 2.5, 2.6,
4.1, 4.2, 5.1, 5.2, 5.3, 6.2, 7.1, 7.2, 7.3, 7.4, 8.0, 8.4) and the legacy code
under `legacy/`.

Four files, no more. Every signature below is copied from the contracts with the
section cited. Where the contracts left a detail open for this folder the
decision is marked **[D-n]** and repeated in section 6.

---

## 1. Files

### 1.1 `agent/inject_format.py`

One sentence: the table of the five ways an early result is written back into the
token stream, as one module-level literal.

- **venv**: `any` (0.2) — imports under `external/probe-env/bin/python`,
  `external/appworld/venv/bin/python`, `external/vllm-env/bin/python` and system
  `python3`. **Zero imports, repo or third-party** (0.2's `imports: none`).
- **used by** (0.2): `agent/inject.py`; its keys are cross-checked against
  `schema.py`'s `inject.format` axis by `run.py selfcheck` (5.3, 7.3).
- **reads / writes**: nothing.

**Module-level names it must offer.**

```python
VERSION: int                      # 0.2 ("carries VERSION"); 3.3's literal rule: assigned at column zero
FORMATS: dict[str, Format]        # 7.3 ("a module-level literal")
```

`Format` is a dataclass declared in this file with **exactly** these four fields
and nothing else (7.3, the "What an entry of `FORMATS` is" table):

| field | type | meaning (7.3) |
|---|---|---|
| `placement` | `"p1"` or `"p2"` | `p1` splices the body into the model's own reasoning; `p2` makes it a separate prefetch message |
| `needs_special` | `bool` | whether the body is encoded with real control tokens (`special=true`) or as plain text (`special=false`, the `p1` direction, 7.2) |
| `system_text` | `str \| None` | the extra system text this format needs, or None |
| `render` | `render(call: str, exec_out: str, exec_ok: bool, error_kind: str \| None) -> str` | the body, written from the speculation result |

The five keys and their values are the axis values of 5.3
(`note`, `p1_e1`, `p1_e2`, `p2_e1`, `p2_e2`) and port
`legacy/pipeline/inject/inject_format.py:28-46` **byte for byte in the body
text**:

| key | placement | needs_special | system_text | render returns |
|---|---|---|---|---|
| `note` | `p1` | `False` | `None` | `"[SYSTEM NOTE: prefetched {call} = {exec_out}]\n"` |
| `p1_e1` | `p1` | `False` | `None` | `"[Prefetch: " + EXPLAIN + "]\n"` |
| `p1_e2` | `p1` | `False` | `SYSTEM_EXTRA` | `MARKER + "\n"` |
| `p2_e1` | `p2` | `True` | `None` | `EXPLAIN` |
| `p2_e2` | `p2` | `True` | `SYSTEM_EXTRA` | `"{call} = {exec_out}"` |

with the three text constants copied verbatim from
`legacy/pipeline/inject/inject_format.py:28-34`:

```python
EXPLAIN = ("The system already ran {call} for you and got:\n{result}\n"
           "You can use this result without calling it.")
MARKER = "[Prefetch] {call} = {result}"
SYSTEM_EXTRA = (
    "\n\nSometimes a prefetched result appears while you reason, either as a line starting with "
    "[Prefetch] or as a message from a sender named prefetch. It means the system already ran "
    "that call for you; use the result without calling it again.")
```

(The legacy templates spell the second placeholder `{result}`; `render`'s
parameter is named `exec_out`, so the entries format with
`.format(call=call, result=exec_out)`. Keeping the legacy template strings
unedited is what makes the ported `note` format byte-identical to today's.)
Today's five entries ignore `exec_ok` and `error_kind`; the two parameters are on
the signature because 7.3 puts them there, and a sixth entry may use them.

**Legacy source**: `legacy/pipeline/inject/inject_format.py:1-78` (the whole
file).

**Not ported, stated:**
- `sep_for` (`:49-52`), the head-seam rule. `render` takes no head, so the seam
  moves to `agent/inject.py` **[D-1]**.
- `TAIL` and `PREFETCH_SENDER` (`:36-38`), the harmony control-token wrapper.
  7.3 gives the `p2` wrapping to the family module's `wrap_prefetch(body,
  system_text)` (6.2), so this file holds **no control tokens at all**. The
  `models/` planner ports `TAIL` into `models/agent_models/gptoss.py`.
- `system_extra(name)` (`:55-58`) — becomes the `system_text` field.
- `needs_special(name)` (`:61-64`) — becomes the `needs_special` field (legacy
  derived it from the placement; both entries with `p2` carry `True`, so the
  table stays consistent).
- `splice_text(name, head, call, result)` (`:67-73`) — its body half becomes
  `render`, its seam half `agent/inject.py`, its `TAIL` half `wrap_prefetch`.
- `is_prefetch_header(hdr)` (`:76-78`) — dropped: no caller in the new tree
  (legacy's caller was the scoring/replay side, which is `eval/score_run.py`'s
  business and reads records, not raw streams).

### 1.2 `agent/generate.py`

One sentence: the plain generation step — stream tokens from the agent model to
the end of the turn — and the three declarations the inject step borrows.

- **venv**: the environment's (0.2, 2.1) — today `external/appworld/venv`. Its
  imports are stdlib + repo only, so it also imports under `probe-env`.
- **imports** (0.2): `models/agent_models/service.py` (the client),
  `models/__init__.py` (the family module, through `agent(alias)`). It imports
  `models/probe_models/service.py` **nowhere** — the `probe` field of the
  `Clients` dataclass is annotated `object` (7.3).
- **used by** (0.2): `agent/loop.py`, `agent/inject.py`.
- **reads / writes**: nothing on disk.

**Names it must offer.**

```python
VERSION: int                                              # 0.2; folded into the sample and inject keys (2.2)

@dataclass
class StepResult:                                         # 7.3, declared here, imported by inject.py
    reasoning: str
    content: str
    usage: dict            # {"in": int, "out": int}      — the gen row's struct{in,out} (1.1)
    wall_s: float
    finish_reason: str | None
    stop_reason: str | None
    prefix_tok: int
    prefix_sha: str
    gen_ids: list[int] | None
    n_inject: int
    discard: dict          # {"chars": int, "tokens": int, "events": int} (1.1)

@dataclass
class Clients:                                            # 7.3: "a dataclass declared in agent/generate.py
    agent: object          # the 7.1 client                #  beside StepResult, with two fields"
    probe: object          # annotated object, never the probe client class (7.3)

def step(env, clients, cfg, writer, messages, prefix_ids, history, task_text,
         step_index, seed) -> StepResult                  # 7.3, identical in inject.py

def stream(clients, cfg, prefix_ids, seed, *, budget=None)
    # 7.3: "agent/generate.py exposes stream(clients, cfg, prefix_ids, seed), which returns the
    # agent client's iterator of (text_delta, ids_delta) pairs with its close()". The keyword-only
    # budget is [D-2].
```

Behaviour of `step` (7.3 items 2 and 3, and 1.1's `gen` row):

1. `t0 = time.monotonic()`; check the family once: `mod = models.agent(cfg.models.agent).module`,
   refuse when `mod.NAME != cfg.models.agent_row["family"]` (6.2's second
   exception) **[D-3 caches this per process]**.
2. Open one stream with `stream(clients, cfg, prefix_ids, seed)`; accumulate
   `raw` (text) and `gen_ids`, and call `state = mod.parse(delta, state)` per
   chunk, keeping the two keys `reasoning` and `content` (6.2).
3. The step ends when the stream ends. Fill `StepResult`:
   `reasoning`/`content` from the last `parse` result; `usage` summed over the
   step's requests (`{"in": prompt_tokens, "out": completion_tokens}`, falling
   back to the count of received ids when `usage` is absent because the stream
   was aborted, `legacy/pipeline/inject/live_appworld.py:543-547`); `wall_s`
   rounded to 2 decimals; `finish_reason`/`stop_reason` from the stream;
   `prefix_tok = len(prefix_ids)`; `prefix_sha = ids_sha(prefix_ids)`;
   `gen_ids = gen_ids if <store_token_ids> else None` **[D-4]**;
   `n_inject = 0`; `discard = {"chars": 0, "tokens": 0, "events": 0}` (7.3: "on
   a sample run `n_inject` is 0 and `discard` is zeroed").
4. `env`, `writer`, `messages`, `history` and `task_text` are accepted and
   **ignored** (7.3: "`generate.step` ignores both"); the parameters exist so the
   two step implementations are substitutable.

`ids_sha(ids)` is a module-level helper in this file, ported verbatim from
`legacy/pipeline/inject/live_appworld.py:379-383`:
`hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()`. `agent/inject.py`
imports it **[D-5]**.

`stream(clients, cfg, prefix_ids, seed, *, budget=None)` builds the `generation`
argument of the 7.1 client call and returns
`clients.agent.stream(prefix_ids, gen, seed)`, where `gen` is `cfg.generation`
when `budget is None` and
`dataclasses.replace(cfg.generation, max_step_tokens=budget)` otherwise. The
request body, the retries and the `(text_delta, token_ids_delta)` shape are the
client's (7.1) and are **not** written here.

**Legacy source**: `legacy/pipeline/inject/live_appworld.py:411-455` and
`:539-569` (the non-probing half of `gen_step`), `:379-383` (`ids_sha`),
`:786-802` (the timing and the `gen` record's fields, which become `StepResult`).

**Not ported, stated:**
- `Stream`, `open_stream`, `sample_extras`, `gen_payload`, `http_json`
  (`:190-287`) — the request body, the retry policy and the streaming protocol
  are `models/agent_models/service.py`'s (7.1).
- `parse_step` (`:111-148`) — channel splitting is the family module's `parse`
  (6.2); this file only carries the two keys it returns.
- `think_span` (`:151-162`) — replaced by the streaming invariant in
  `agent/inject.py` **[D-6]**.
- The wrap-up consistency check (`:556-567`, `text_ids_consistent`) — the `gen`
  row of 1.1 has no such column, so the check and the warning are dropped.
- `end_of_turn(ids)` (6.2) has **no caller in `agent/`** **[D-7]**.

### 1.3 `agent/inject.py`

One sentence: the generation step with the probe — score at each live cut, fire,
speculate, splice the result in and resume from the spliced prefix.

- **venv**: the environment's (0.2).
- **imports** (0.2): `agent/generate.py`, `agent/inject_format.py`,
  `data/probe_input.py`, `data/task_record.py`,
  `data/environments/__init__.py` (type only; the object is passed in),
  `models/probe_models/service.py` (client), `models/__init__.py` (the family
  module). **It does not import `experimental_settings/schema.py`** — the
  setting is passed in by `loop.py`.
- **used by**: `agent/loop.py`.
- **reads**: nothing. **writes**: `spec` and `resume` rows, through
  `data/task_record.py`'s writer it was handed (0.2, 1.1's "who writes").

**Names it must offer.**

```python
VERSION: int                                    # 0.2
ARMS = ("probe", "no_probe", "probe_nofill")    # 5.3: a module-level literal, column zero, parsed with ast

def step(env, clients, cfg, writer, messages, prefix_ids, history, task_text,
         step_index, seed) -> StepResult        # 7.3, the same signature as generate.step

def system_text(cfg) -> str | None              # 7.3
```

`system_text(cfg)` returns `FORMATS[cfg.inject.format].system_text` **only when
that entry's `placement` is `"p1"`**, and `None` otherwise — None for a `p2`
entry (whose system text `wrap_prefetch` applies) and None when
`cfg.inject is None` (7.3, 5.1's presence test).

**The `/health` refusal** (7.2), taken once before the first request of the
run: refuse unless the echo reports `decode: true`, `encode_special: true`
whenever `FORMATS[cfg.inject.format].needs_special` is true, and
`score_train_key` / `gen_train_key` equal to `cfg._upstream["probe_score.train"]`
and `cfg._upstream["probe_gen.train"]` (1.5's naming). It also compares
`mod.NAME` against `cfg.models.agent_row["family"]` (6.2's second exception).
The refusal is **unconditional across the three arms** **[D-8]**.

**What `step` does** (7.3 item 4, with the algorithm from
`legacy/pipeline/inject/live_appworld.py:411-569`):

1. Accumulate `raw`, `gen_ids` and `bounds` (the `(len(raw), len(gen_ids))` pair
   at the end of each chunk, `:432,456`) over
   `generate.stream(clients, cfg, prefix_ids, seed, budget=max(1, cfg.generation.max_step_tokens - len(gen_ids)))`.
   The **kept** ids count against the step budget and the discarded overflow
   does not (`:446-450`).
2. Per chunk, `state = mod.parse(delta, state)`; `thinking_so_far =
   state["reasoning"]`. Stop scoring for the rest of the step as soon as
   `raw.endswith(thinking_so_far)` stops holding (the streaming form of legacy's
   `te < len(raw)` test, `:462-467`) **[D-6]**; while it holds,
   `ts = len(raw) - len(thinking_so_far)`.
3. Skip the rescan when the chunk carries none of `.!?\n` (`:459-460`).
4. `probe_input.cuts_live(thinking_so_far, cfg.build.min_think)` (1.7) gives the
   candidate offsets; score a cut that was not scored before, and **only once
   `len(thinking_so_far.strip()) >= cfg.build.min_think`** (1.7's event-level
   gate in its streaming form). Stop after `cfg.inject.max_cuts` cuts have been
   scored in this step (`:472-474`), and stop injecting after
   `cfg.inject.max_inject_per_step` fires (`:457`).
5. Scoring: `clients.probe.score(probe_input.assemble(task_text, history,
   thinking_so_far[:cut], cfg.build.hist_rounds, cfg.build.probe_result_cap))`
   (7.3, 1.7). Fire on the first `conf >= cfg.inject.theta`. Under
   `cfg.inject.fire_nth_cut > 0` no `/score` call is made at all and the fire is
   the `fire_nth_cut`-th counted cut, with `conf` and `pred_label` null
   (`:477-480`) **[D-9]**. Under `arm: no_probe` nothing is ever scored and the
   step is one uninterrupted stream (`:438`).
6. On a fire: `pos = ts + cut` (raw coordinates); `k0 = token_boundary(bounds,
   pos)`; `k, head_txt = find_head(gen_ids, raw, pos, k0, clients.probe.decode)`
   — both ported verbatim from `:324-337` and `:340-376`, `decode` being one
   `POST /decode` per candidate id. `head_ids = gen_ids[:k]`,
   `overflow_ids = gen_ids[k:]`.
7. Under `arm: probe_nofill` nothing is generated or executed: `note = ""`,
   `note_ids = []`, and the `spec` row's `gen_call`, `exec_code`, `arg_modes`,
   `exec_out`, `exec_ok`, `error_kind` are null (`:495-498`). Otherwise:
   `call = clients.probe.generate(<the probe's text at the cut>, cfg.inject.max_new)`
   (7.2), `call = env.complete_call(call)`, `spec = env.speculate(call)` — whose
   returned dict is **copied into the `spec` row unchanged** (4.3) — then
   `body = FORMATS[fmt].render(call, spec["exec_out"], spec["exec_ok"], spec["error_kind"])`
   and
   - `placement == "p1"`: `note = ("" if head_txt[-1:].isspace() else "\n") + body` **[D-1]**;
   - `placement == "p2"`: `note = mod.wrap_prefetch(body, FORMATS[fmt].system_text)` (7.3, 6.2).
   `note_ids = clients.probe.encode(note, special=FORMATS[fmt].needs_special)`
   (7.2, `:508-510`).
8. Write the `spec` row (1.1's columns, all of them):
   `fire_index` (0-based within the step), `cut`, `n_checked`, `conf`,
   `pred_label`, `gen_call`, `exec_code`, `arg_modes`, `exec_out`, `exec_ok`,
   `error_kind`, `note`, `format` (`cfg.inject.format`), `head_tok` (`k`),
   `head_chars` (`len(head_txt) - ts`), `note_tok` (`len(note_ids)`),
   `discarded_chars` (`max(0, len(raw) - len(head_txt))`),
   `overflow_ids` (null unless store_token_ids, **[D-4]**), `spec_s`.
9. Reset the stream state exactly as `:529-535`: `raw = head_txt + note`,
   `gen_ids = head_ids + note_ids`, `bounds = [(len(raw), len(gen_ids))]`, the
   scored-cut set cleared, `accepted = (len(head_txt) - ts) + len(note)` so the
   text before the splice is not re-scored; close the stream and re-issue.
10. The `resume` row is written when the next fire arrives or when the step ends
    with a fire outstanding (`:396-408`, `:527-528`, `:548-550`):
    `fire_index` (which fire this resend follows), `overflow_tok`, `new_tok`,
    `match_len`, `identical`, `stop_reason`.
11. Return a `StepResult` whose `n_inject` is the fire count and whose `discard`
    accumulates `chars`, `tokens` and `events` (`:512-514`). Everything else is
    filled exactly as `generate.step` fills it.

**Legacy source**: `legacy/pipeline/inject/live_appworld.py:324-337`
(`token_boundary`), `:340-376` (`find_head`), `:396-408` (`log_resume`),
`:411-569` (`gen_step`, the probing half), `:572-587` (`probe_cfg_problem`, the
`decode` / `encode_special` half), `:386-393` (the seam and the system text).

**Not ported, stated:**
- `speculate` (`:305-321`) — the three-step guarantee is
  `data/environments/appworld.py`'s `speculate` (4.3); this file calls it and
  copies the returned dict in.
- `selftest_shadow` (`:841-872`) — becomes the deferred `tests/` check ("a
  speculated call leaves the world unchanged"), which the tree defers.
- The `spec` row's legacy-only fields `nofill`, `head_ends_ws`, `head_tail`,
  `n_chunks` — not columns of 1.1's record.
- `--no-probe`'s scoping of the `/health` checks (`:702-704`) — **[D-8]**.
- `cfg.inject.chunk_tokens` and `cfg.inject.tail_tokens` are **read by nothing**
  **[D-10]**.

### 1.4 `agent/loop.py`

One sentence: run each requested (split, task, seed) triple — claim, open, step,
act, judge, close — and write the record.

- **venv**: the environment's (0.2, 2.1).
- **imports** (0.2): `experimental_settings/schema.py` (`load_frozen` only),
  `data/environments/__init__.py`, `data/task_record.py`,
  `models/agent_models/service.py` (client), `models/probe_models/service.py`
  (client, for `render`), `agent/generate.py`, `agent/inject.py`,
  `jobs/registry.py`. **It imports `models/__init__.py` nowhere** (0.2, and the
  index's row for it) — it renders through the probe service and compares the
  family the service echoes.
- **used by**: none (program).
- **reads**: its run directory's `settings.yaml`; the environment's split
  task-id files, through `requested_pairs`; `service_agent_<replica>.json` and
  `service_probe_0.json` in its own run directory (7.4) and **no other file**.
- **writes**: task records (jsonl), heartbeat.

**Names it must offer.**

```python
VERSION: int                          # 0.2; folded into the sample and inject keys (2.2)
def main(run_dir, piece) -> None      # 2.1's program column: "agent.loop, main(run_dir, piece)"
```

Command shape (2.6, 3.4): `<venv python> -m agent.loop --run-dir <dir> --piece
<i>/<n>`, repo root as the working directory, **no setting name anywhere**. The
`__main__` block parses those two flags and nothing else.

**What it does, in order.**

1. `cfg = schema.load_frozen(run_dir)` (2.6). Bind
   `run = cfg.inject if cfg.inject is not None else cfg.sample` and read
   `run.split`, `run.seeds`, `run.tasks`, `run.n_tasks`, `run.max_steps`,
   `run.store_token_ids`, `run.replicas` off it **[D-11]**.
2. `env = open_env(cfg.data.env)` (4.1).
3. Endpoint files (7.4): compute `i mod run.replicas` from its own `--piece
   i/n`, open `service_agent_<that>.json` and `service_probe_0.json` in its own
   run directory, waiting for both and giving up after
   `registry.DEFAULTS["launch_timeout_s"]`. Build
   `clients = generate.Clients(agent=AgentClient(base_url,
   cfg.models.agent_row["served_model_name"]), probe=ProbeClient(base_url))`
   (7.1, 7.2, 7.4).
4. `/health` refusal (7.2): refuse unless the probe service reports
   `render == "ids"`, `family == cfg.models.agent_row["family"]` and
   `weights == cfg.models.agent_row["weights"]`.
5. Pick the step: `gen_step = inject.step if cfg.inject is not None else
   generate.step` (0.2, 5.1's presence test). `extra = inject.system_text(cfg)`,
   recomputed per call is unnecessary — the value is constant for a run, but it
   is passed on **every** `to_messages` call (1.1, 7.3).
6. `triples = requested_pairs(env, run.split, run.tasks, run.n_tasks,
   run.seeds)` (4.1, 2.3). Walk them rotated by the piece index:
   `triples[piece:] + triples[:piece]` (2.3, today's pool mode,
   `legacy/pipeline/inject/live_appworld.py:718-723`).
7. `hb = registry.beat(run_dir, piece)`; `hb.emit(0, len(triples), "task")`
   before the walk; one `emit(done, len(triples), "task", tok_in=…, tok_out=…)`
   per finished task; `hb.finish()` at the end (8.0, 8.4). `total` is the whole
   requested count for every piece (8.4).
8. Per triple `(split, task_id, seed)`:
   - `writer = open_record(run_dir / "records", task_id, seed)` (1.1); `None`
     means another piece holds it — move on, deleting nothing.
   - `env.open(task_id, seed)`; capture `task_text` (4.2, 1.1's `meta.task_text`).
   - `writer.row("meta", …)` with every column of 1.1's `meta` block:
     `record_id` (`data.record_id(task_id, seed)`), `stage` (`cfg._stage`),
     `env` (`cfg.data.env`), `task_id`, `seed`, `env_seed` (`env.SEED`),
     `split` (the triple's first element, 2.3), `arm` (`"sample"` when
     `cfg.inject is None`, else `cfg.inject.arm`) **[D-12]**, `instructions`
     (`cfg.data.instructions`), `task_text`, `agent_model` (`cfg.models.agent`),
     `generation` and `inject` (canonical JSON text, **[D-13]**), `commit`
     (`cfg._commit`, never probed from git), `run_key` (`cfg._key`),
     `owner_session` (`f"{cfg._stage}-{cfg._key}-{piece}"`, 3.4's session name,
     **[D-14]**). `version` and `ts` are stamped by the writer **[D-15]**.
   - For `step_index` in `range(run.max_steps)`:
     `messages = to_messages(writer.frame(), step_index, task_text,
     env.INSTRUCTIONS[cfg.data.instructions], env.NO_CODE_MESSAGE, extra)`
     (1.1, `upto_step` exclusive **[D-16]**);
     `prefix_ids = clients.probe.render(messages, cfg.generation.effort,
     cfg.generation.date)` — **once per step**, and nothing below renders again
     (7.3 item 1);
     `res = gen_step(env, clients, cfg, writer, messages, prefix_ids, history,
     task_text, step_index, seed)`;
     `writer.row("gen", step=step_index, **asdict(res))` (7.3: "the loop writes
     the `gen` row from it");
     `obs = env.step(res.content)` (4.2 — the extraction, the execution, the
     clip and the completion test are all the environment's);
     `writer.row("env", step=step_index, action=obs.action,
     result=obs.observation, error_kind=obs.error_kind)`;
     append `(obs.action, obs.observation)` to `history` **only when
     `obs.action` is not None** **[D-17]**; break when `obs.completed`.
   - A 400 from the agent client sets `abort = "context_overflow_400"` and ends
     the trajectory (7.1); any other exception from one task is caught, recorded
     and walked past **[D-18]**.
   - `judge = env.judge()`; `writer.row("final", steps=…, completed=…,
     abort=…, judge=<canonical JSON of the dict>, success=<the dict's own
     `success`>, tokens_in=…, tokens_out=…, wall_s=…, finished_at=…)` (1.1,
     4.2). `writer.close()`.
   - `env.close()` in a `finally` (4.2: "leave the world and delete the per-task
     outputs").

**Legacy source**: `legacy/pipeline/inject/live_appworld.py:606-757` (the
program: the task list, the rotation, the claim, the per-task guard, the output
cleanup) and `:759-838` (`run_task`: the world, the meta record, the step loop,
the 400 handling, the evaluation and the `final` record);
`legacy/envs/collect/run_appworld.py:109-244` (the sample-side walk, the
heartbeat calls at `:169-172,183-184,240-244`, the world open and instruction
capture at `:186-190`, the abort capture at `:221-228`, the evaluation and
`final` row at `:229-238`).

**Not ported, stated:**
- The `--preset` merge (`live_appworld.py:663-684`,
  `legacy/envs/collect/common.py:278-332`) — generation settings come from the
  frozen `settings.yaml` (2.6, 5.2); no piece reads a preset file.
- `--split/--n/--task-ids/--shard-id/--num-shards/--pool/--resume/--keep-outputs/--exp/--model/--base-url/--probe-url`
  (`:606-659`) — every one of them is now a frozen setting field or an endpoint
  file; the command line is `--run-dir` and `--piece` only (2.6).
- `claim` (`:590-603`, the `.claims/` `mkdir` ticket) — replaced by
  `open_record`'s `O_EXCL` create (1.1).
- `is_done` / `--resume` (`run_appworld.py:79-82`,
  `live_appworld.py:732-736`) — the loop skips every file that exists (1.1); the
  completeness check and the claim release are the login machine's (1.1, 2.3).
- `resolve_seeds`, `traj_path`, `exp_name`, `traj_meta`
  (`run_appworld.py:48-106`) — seeds come from `requested_pairs`, the path from
  `data/task_record.py`, and the benchmark's experiment name from
  `Environment.open` (4.2).
- The code-block regex, the no-code reply and the `world.execute` call
  (`run_appworld.py:45,204-217`; `live_appworld.py:804-816`) — `Environment.step`
  owns them (4.2's "`step` owns two things a reader might expect in the loop").
- `system_prompt(fmt)` (`live_appworld.py:389-393`) — the developer message is
  `env.INSTRUCTIONS[...]` plus `to_messages`'s `extra_developer` (1.1, 7.3).
- `probe_cfg_problem`'s `render == "harmony_ids"` and `p2_*` literals
  (`:572-587`) — 7.2 replaces both with `render == "ids"` and a comparison
  against `cfg.models.agent_row`.
- `heartbeat.emit` from `legacy/ops/heartbeat.py` — the heartbeat now goes
  through `registry.beat` into `heartbeat/<piece>-<launch>.jsonl` (8.4).

---

## 2. Order of construction, and what must exist first

Inside the folder: **`inject_format.py` → `generate.py` → `inject.py` →
`loop.py`**. `inject_format.py` stands alone; `inject.py` imports both of the
first two; `loop.py` imports the three.

What each file needs from other folders, by file and function:

| file | needs first |
|---|---|
| `inject_format.py` | nothing |
| `generate.py` | `models/__init__.py` (`agent(alias) -> AgentModel`, field `module`); `models/agent_models/gptoss.py` (`NAME`, `parse(text_delta, state)`); `models/agent_models/service.py` (the client half: `Client(base_url, served_model_name)`, `stream(prompt_ids, generation, seed)`, `health()`); `experimental_settings/schema.py` for the `generation` dataclass `dataclasses.replace` is applied to (imported by nobody in this file — it arrives as `cfg`) |
| `inject.py` | everything `generate.py` needs, plus `models/agent_models/gptoss.py` (`wrap_prefetch(body, system_text)`); `models/probe_models/service.py` (the client half: `Client(base_url)`, `score(text)`, `generate(text, max_new)`, `encode(text, special)`, `decode(ids)`, `health()`); `data/probe_input.py` (`cuts_live(thinking_so_far, min_think)`, `assemble(task, history, thinking_prefix, hist_rounds, probe_result_cap)`); `data/task_record.py` (`Writer.row`); `data/environments/__init__.py` (`Environment` for the type annotation; the object is passed in, and its `speculate`, `complete_call`, `build_call` are called on it) |
| `loop.py` | everything the three need, plus `experimental_settings/schema.py` (`load_frozen(run_dir) -> Setting`); `data/environments/__init__.py` (`open_env(name)`, `requested_pairs(env, splits, tasks, n_tasks, seeds)`, `StepObservation`); `data/task_record.py` (`open_record(dir, task_id, seed)`, `Writer.row`, `Writer.frame`, `Writer.close`, `to_messages(df, upto_step, task_text, instructions, no_code, extra_developer)`); `data/__init__.py` (`record_id`); `models/probe_models/service.py` (the client's `render(messages, effort, date)` and `health()`); `jobs/registry.py` (`beat(run_dir, piece)`, `Heartbeat.emit`, `Heartbeat.finish`, `DEFAULTS["launch_timeout_s"]`) |

---

## 3. Acceptance, CPU

Every command is run from the repo root, `/home/y-guo/reproduce/new1`. Two
interpreters appear: `A=external/appworld/venv/bin/python` (the environment's
venv, which `agent/loop.py`, `generate.py` and `inject.py` declare) and
`P=external/probe-env/bin/python`. `inject_format.py` is `venv: any`, so it is
checked under four.

### A. `agent/inject_format.py`

**A1 — imports under every interpreter of the `venvs:` map plus system python3
(0.1's `any`).**

```bash
for py in external/probe-env/bin/python external/appworld/venv/bin/python \
          external/vllm-env/bin/python python3; do
  $py -c "import agent.inject_format as F; print('$py', F.VERSION, sorted(F.FORMATS))" || exit 1
done
```
Expected: four lines, each ending
`['note', 'p1_e1', 'p1_e2', 'p2_e1', 'p2_e2']`, exit 0.

**A2 — the four fields, and the placement/needs_special agreement.**

```bash
python3 -c "
from agent.inject_format import FORMATS
import dataclasses
for k, f in FORMATS.items():
    assert set(dataclasses.asdict(f)) == {'placement','needs_special','system_text','render'} or \
           [x.name for x in dataclasses.fields(f)] == ['placement','needs_special','system_text','render'], k
    assert f.placement in ('p1','p2'), k
    assert f.needs_special == (f.placement == 'p2'), k
    assert callable(f.render), k
print('fields ok', len(FORMATS))
"
```
Expected: `fields ok 5`, exit 0.

**A3 — the rendered bodies are byte-identical to the legacy table.** (The
`note` entry is the pre-2026-09-12 text and is the one the old runs used.)

```bash
python3 -c "
from agent.inject_format import FORMATS
c, r = 'apis.spotify.login(username=x)', 'OK'
got = {k: f.render(c, r, True, None) for k, f in FORMATS.items()}
want = {
 'note': '[SYSTEM NOTE: prefetched apis.spotify.login(username=x) = OK]\n',
 'p1_e1': '[Prefetch: The system already ran apis.spotify.login(username=x) for you and got:\nOK\nYou can use this result without calling it.]\n',
 'p1_e2': '[Prefetch] apis.spotify.login(username=x) = OK\n',
 'p2_e1': 'The system already ran apis.spotify.login(username=x) for you and got:\nOK\nYou can use this result without calling it.',
 'p2_e2': 'apis.spotify.login(username=x) = OK',
}
assert got == want, {k: (got[k], want[k]) for k in want if got[k] != want[k]}
print('render ok')
"
```
Expected: `render ok`, exit 0.

**A4 — `system_text` is set on exactly the two `*_e2` entries, and its text is
the legacy paragraph.**

```bash
python3 -c "
from agent.inject_format import FORMATS
have = sorted(k for k,f in FORMATS.items() if f.system_text)
assert have == ['p1_e2','p2_e2'], have
t = FORMATS['p1_e2'].system_text
assert t == FORMATS['p2_e2'].system_text
assert t.startswith('\n\nSometimes a prefetched result appears while you reason') and t.endswith('use the result without calling it again.'), repr(t[:40])
print('system_text ok')
"
```
Expected: `system_text ok`, exit 0.

**A5 — no control token anywhere in this file** (the `p2` wrapper is the
family's, 7.3).

```bash
grep -c '<|start|>\|<|end|>\|<|channel|>\|<|message|>' agent/inject_format.py
```
Expected: `0`.

**A6 — selfcheck's axis cross-check** (needs `schema.py`; run it once that file
exists):

```bash
external/probe-env/bin/python run.py selfcheck
```
Expected: exit 0, and no line mentioning `inject.format`. The rule being proved
is 5.3's: `schema.py`'s `inject.format` literals equal `FORMATS.keys()`, parsed
with `ast`.

### B. `agent/generate.py`

**B1 — imports under the environment's venv and under probe-env.**

```bash
for py in external/appworld/venv/bin/python external/probe-env/bin/python; do
  $py -c "import agent.generate as g; print(g.VERSION, [f.name for f in __import__('dataclasses').fields(g.StepResult)])" || exit 1
done
```
Expected: two lines, each listing exactly
`['reasoning', 'content', 'usage', 'wall_s', 'finish_reason', 'stop_reason', 'prefix_tok', 'prefix_sha', 'gen_ids', 'n_inject', 'discard']`.

**B2 — `Clients` has two fields and `generate.py` names the probe client
nowhere** (7.3, 0.2).

```bash
external/appworld/venv/bin/python -c "
import dataclasses, agent.generate as g
assert [f.name for f in dataclasses.fields(g.Clients)] == ['agent','probe']
print('clients ok')"
grep -c 'probe_models' agent/generate.py
```
Expected: `clients ok`, then `0`.

**B3 — `step` has the pinned signature, identical to `inject.step`** (7.3).

```bash
external/appworld/venv/bin/python -c "
import inspect, agent.generate as g
sig = list(inspect.signature(g.step).parameters)
assert sig == ['env','clients','cfg','writer','messages','prefix_ids','history','task_text','step_index','seed'], sig
print('sig ok')"
```
Expected: `sig ok`, exit 0.

**B4 — the real entry point on a fake agent client.** The fixture is built in
the command: a stub client whose `stream` yields two `(text, ids)` chunks, a
stub family module, a stub `cfg`.

```bash
external/appworld/venv/bin/python - <<'PY'
import types, dataclasses, agent.generate as g

class FakeStream:
    finish_reason, stop_reason = "stop", "<|return|>"
    usage = {"prompt_tokens": 7, "completion_tokens": 4}
    def __iter__(self):
        yield "<|channel|>analysis<|message|>Hi there. ", [1, 2]
        yield "Done.<|end|><|start|>assistant<|channel|>final<|message|>ok", [3, 4]
    def close(self): pass

class FakeAgent:
    def stream(self, ids, generation, seed): return FakeStream()

@dataclasses.dataclass
class Gen:
    temperature: float = 1.0
    top_p: object = None
    max_step_tokens: int = 8192
    stop: object = None
    effort: str = "high"
    date: str = "2026-08-06"

cfg = types.SimpleNamespace(
    generation=Gen(), inject=None,
    sample=types.SimpleNamespace(store_token_ids=False),
    models=types.SimpleNamespace(agent="gptoss120b",
                                 agent_row={"family": "gptoss", "weights": "gptoss120b",
                                            "served_model_name": "gpt-oss-120b"}))
res = g.step(None, g.Clients(agent=FakeAgent(), probe=None), cfg, None, [], [11, 12],
             [], "task text", 0, 42)
assert res.n_inject == 0 and res.discard == {"chars": 0, "tokens": 0, "events": 0}, res
assert res.usage == {"in": 7, "out": 4}, res.usage
assert res.prefix_tok == 2 and len(res.prefix_sha) == 40, res
assert res.gen_ids is None, res.gen_ids            # store_token_ids False
assert "Hi there." in res.reasoning and "ok" in res.content, res
print("step ok", res.finish_reason, res.stop_reason)
PY
```
Expected: `step ok stop <|return|>`, exit 0. (The stub family module is reached
through `models/__init__.py`; when that file is not yet on disk the implementer
runs the same script with `models` stubbed into `sys.modules` — the check to
keep is the field values, not the import path.)

**B5 — `ids_sha` reproduces the legacy hash** (`live_appworld.py:379-383`).

```bash
external/appworld/venv/bin/python -c "
import hashlib, agent.generate as g
ids=[11,12,13]
assert g.ids_sha(ids) == hashlib.sha1(b'11,12,13').hexdigest()
print('ids_sha ok')"
```
Expected: `ids_sha ok`, exit 0.

### C. `agent/inject.py`

**C1 — imports, and the two literals.**

```bash
external/appworld/venv/bin/python -c "
import inspect, agent.inject as i, agent.generate as g
assert i.ARMS == ('probe','no_probe','probe_nofill'), i.ARMS
assert list(inspect.signature(i.step).parameters) == list(inspect.signature(g.step).parameters)
print('inject ok', i.VERSION)"
grep -n '^ARMS' agent/inject.py
```
Expected: `inject ok <n>`, and one `ARMS = (...)` match **at column zero**
(3.3's literal rule, so `schema.py` can read it with `ast`).

**C2 — `system_text` returns the text for `p1_e2` only, and None for a `p2`
entry and for a sample setting** (7.3).

```bash
external/appworld/venv/bin/python -c "
import types, agent.inject as inj
from agent.inject_format import FORMATS
mk=lambda f: types.SimpleNamespace(inject=types.SimpleNamespace(format=f))
assert inj.system_text(types.SimpleNamespace(inject=None)) is None
assert inj.system_text(mk('note')) is None
assert inj.system_text(mk('p1_e1')) is None
assert inj.system_text(mk('p1_e2')) == FORMATS['p1_e2'].system_text
assert inj.system_text(mk('p2_e1')) is None
assert inj.system_text(mk('p2_e2')) is None
print('system_text ok')"
```
Expected: `system_text ok`, exit 0.

**C3 — `find_head` and `token_boundary` on a fixture with the legacy lag.** The
fixture is the failure legacy's docstring names: the streamed text runs about
nine characters behind the ids.

```bash
external/appworld/venv/bin/python - <<'PY'
import agent.inject as inj
toks = ["Hello", " world.", " Then", " more."]
def decode(ids): return "".join(toks[i] for i in ids)
gen_ids = [0, 1, 2, 3]
raw = "Hello world."                      # the stream is behind the ids
pos = len("Hello world.")                 # the cut right after the punctuation
k0 = inj.token_boundary([(0, 0), (12, 2)], pos)[1]
k, head = inj.find_head(gen_ids, raw, pos, k0, decode)
assert (k, head) == (2, "Hello world."), (k, head)
print("find_head ok", k)
PY
```
Expected: `find_head ok 2`, exit 0. A mismatch between `decode(ids[:k])` and the
streamed text must raise, never pass silently (`live_appworld.py:372-375`):

```bash
external/appworld/venv/bin/python - <<'PY'
import agent.inject as inj
try:
    inj.find_head([0], "XYZ", 3, 1, lambda ids: "ABC")
except RuntimeError as e:
    print("raises ok")
else:
    raise SystemExit("find_head accepted a mismatched decode")
PY
```
Expected: `raises ok`, exit 0.

**C4 — a whole fired step against stub clients and a real record writer.** This
is the acceptance that matters: it exercises `inject.step` end to end on CPU and
reads the rows back with `data/task_record.read`.

```bash
external/appworld/venv/bin/python - <<'PY'
import dataclasses, tempfile, types
from pathlib import Path
import agent.generate as g, agent.inject as inj
from data.task_record import open_record, read

class FakeStream:
    finish_reason, stop_reason = "stop", "<|return|>"
    usage = {"prompt_tokens": 5, "completion_tokens": 6}
    def __init__(self, chunks): self.chunks = chunks
    def __iter__(self):
        for c in self.chunks: yield c
    def close(self): pass

class FakeAgent:                      # first stream fires, the resend finishes the turn
    def __init__(self): self.n = 0
    def stream(self, ids, generation, seed):
        self.n += 1
        if self.n == 1:
            return FakeStream([("<|channel|>analysis<|message|>I will look it up. ", [1,2]),
                               ("Next I check the profile. ", [3,4])])
        return FakeStream([("Done.<|end|><|start|>assistant<|channel|>final<|message|>```python\nx=1\n```", [5,6])])

class FakeProbe:
    def score(self, text): return {"conf": 0.99, "label": "apis.supervisor.show_profile", "wall_s": 0.01}
    def generate(self, text, max_new): return {"call": "apis.supervisor.show_profile()", "wall_s": 0.02}
    def encode(self, text, special): return {"ids": [90, 91]}
    def decode(self, ids): return {"text": "".join("abcdefg"[i % 7] for i in ids)}

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
    _stage="inject", _key="k", _commit="deadbeef", _debug=True,
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
    models=types.SimpleNamespace(agent="gptoss120b",
        agent_row={"family": "gptoss", "weights": "gptoss120b", "served_model_name": "gpt-oss-120b"}))

d = Path(tempfile.mkdtemp()) / "records"; d.mkdir(parents=True)
w = open_record(d, "50e1ac9_1", 42)
w.row("meta", record_id="50e1ac9_1__s42", stage="inject", env="appworld", task_id="50e1ac9_1",
      seed=42, env_seed=100, split="test", arm="probe", instructions="v1",
      task_text="do the thing", agent_model="gptoss120b", generation="{}", inject="{}",
      commit="deadbeef", run_key="k", owner_session="inject-k-0")
res = inj.step(FakeEnv(), g.Clients(agent=FakeAgent(), probe=FakeProbe()), cfg, w,
               [], [11, 12], [("print(1)", "1")], "do the thing", 0, 42)
w.close()
df = read(next(d.glob("*.jsonl")))
kinds = df["type"].to_list()
assert kinds.count("spec") == 1 and kinds.count("resume") == 1, kinds
spec = df.filter(df["type"] == "spec").to_dicts()[0]
assert spec["fire_index"] == 0 and spec["format"] == "p1_e1" and spec["exec_ok"] is True
assert spec["gen_call"] == "apis.supervisor.show_profile()"
assert spec["note"].startswith("[Prefetch: The system already ran"), spec["note"]
assert spec["overflow_ids"], spec["overflow_ids"]        # store_token_ids: true
assert res.n_inject == 1 and res.discard["events"] == 1, res
print("inject step ok", res.n_inject, spec["head_tok"], spec["note_tok"])
PY
```
Expected: one line `inject step ok 1 <k> 2`, exit 0. What it proves: a fire
writes exactly one `spec` row and one `resume` row through the record writer, the
`p1` body is the legacy text, the speculation dict is copied in unchanged, and
`StepResult` carries the fire count and the discard account.

**C5 — the two control arms never call the probe.**

```bash
# same fixture as C4, with cfg.inject.arm swapped
external/appworld/venv/bin/python - <<'PY'
... (C4's fixture, with a FakeProbe whose score/generate raise AssertionError)
for arm, fires in (("no_probe", 0), ("probe_nofill", 1)):
    cfg.inject.arm = arm
    if arm == "probe_nofill": cfg.inject.fire_nth_cut = 1
    res = inj.step(...)
    assert res.n_inject == fires, (arm, res.n_inject)
print("arms ok")
PY
```
Expected: `arms ok`, exit 0, with `score` and `generate` never reached under
`no_probe`, and `generate` never reached under `probe_nofill` (which fires,
interrupts and injects nothing — the `spec` row's `gen_call`, `exec_code`,
`exec_out`, `exec_ok` and `error_kind` are all null).

### D. `agent/loop.py`

**D1 — imports under the environment's venv, and the forbidden import is
absent** (0.2: `loop.py` imports `models/__init__.py` nowhere).

```bash
external/appworld/venv/bin/python -c "import agent.loop as l; print(l.VERSION)"
grep -n '^ *import models\|^ *from models import\|from models\.' agent/loop.py | grep -v 'models\.agent_models\.service\|models\.probe_models\.service'
```
Expected: a version number, then **no output** from the grep (exit 1 from grep
is the pass).

**D2 — the command shape** (2.6, 3.4: `-m agent.loop --run-dir <dir> --piece
<i>/<n>` and nothing else).

```bash
external/appworld/venv/bin/python -m agent.loop --help
```
Expected: a usage line naming exactly `--run-dir` and `--piece`; no `--split`,
no `--model`, no `--base-url`, no setting name.

**D3 — a whole `--debug`-sized sample walk on stubs.** The fixture builds a run
directory with a frozen `settings.yaml`, two endpoint files, a stub environment
module under `data/environments/`, and stub service clients; the check is the
record files that appear.

```bash
external/appworld/venv/bin/python - <<'PY'
# writes <tmp>/settings.yaml, <tmp>/service_agent_0.json, <tmp>/service_probe_0.json,
# monkeypatches the two client classes onto agent.loop, then:
import agent.loop as loop
loop.main(run_dir, piece=(0, 1))
PY
ls <tmp>/records/
```
Expected: one `<task_id>__s<seed>.jsonl` per requested triple, each ending in a
`final` row; `<tmp>/heartbeat/0-0.jsonl` present with a first line
`{"done": 0, "total": <n>, "unit": "task", ...}` and a last line carrying
`"status": "done"`.

**D4 — the record's own columns, read back through the format's reader.**

```bash
external/appworld/venv/bin/python -c "
from data.task_record import read
df = read('<tmp>/records/<task_id>__s42.jsonl')
m = df.filter(df['type']=='meta').to_dicts()[0]
assert m['split'] == 'train' and m['arm'] == 'sample' and m['stage'] == 'sample'
assert m['task_text'] and m['commit'] == 'deadbeef' and m['run_key'] == 'k'
assert m['owner_session'] == 'sample-k-0'
assert sorted(set(df['type'].to_list())) == ['env','final','gen','meta']
print('record ok')"
```
Expected: `record ok`, exit 0. The `split` value proves 2.3's triple is carried
(`meta.split` is what `build` maps through `SPLIT_ROLE`); `arm == "sample"` is
**[D-12]**; the four row kinds prove a sample run writes no `spec` or `resume`.

**D5 — the `/health` refusal**: point the stub probe client at an echo with
`render: "jinja"`, then at one whose `family` differs from
`cfg.models.agent_row["family"]`.

```bash
external/appworld/venv/bin/python - <<'PY'
... loop.main with a probe stub echoing {"render": "jinja", ...}
PY
echo "exit=$?"
```
Expected: a non-zero exit and a message naming the field and both values, for
each of the three cases (`render`, `family`, `weights`).

**D6 — a second piece claims nothing another piece holds.** Run `main` twice
over the same run directory with `piece=(0,2)` and `piece=(1,2)` and check that
no `(task, seed)` file is written twice and that the two pieces between them
cover the whole requested list.

Expected: `len(list(records.glob('*.jsonl'))) == len(triples)`, exit 0 for both.

**D7 — `run.py selfcheck`** (once `run.py` and `README.md` exist): it parses
every file's imports with `ast` and fails on an annotation line that disagrees
(0.1, 8.6).

```bash
external/probe-env/bin/python run.py selfcheck
```
Expected: exit 0. The four lines it proves for this folder are the `imports:`,
`used by:`, `reads:`, `writes:` and `venv:` annotations of 0.2 reproduced in
`README.md`, plus 5.3's `inject.format` / `inject.arm` literal comparisons.

---

## 4. Acceptance, GPU or cross-host (for the main session, not the implementer)

All four need real cards and real services, so an implementer returns BLOCKED
with the command.

**G1 — a `--debug` sample walk end to end.**

```bash
external/probe-env/bin/python run.py train_probe ctool_q06 --debug --stage sample
```
Must show: a vLLM piece and a render-only probe piece up, six loop pieces
writing `records/*.jsonl`, and `run.py ls` reporting `done` with 9 records (3
tasks per split over `train`/`dev`/`test`, 2.3's per-split cap). Then
`run.py where sample <key>` and `head -1 <dir>/records/<any>.jsonl` must show a
`meta` row whose `split` is one of `train`/`dev`/`test` and whose
`owner_session` matches a session name `run.py ls` prints — the check for
**[D-14]**, which is the one value `loop.py` and `jobs/launch.py` must spell
identically.

**G2 — a `--debug` inject walk.**

```bash
external/probe-env/bin/python run.py inject <setting> --debug
```
Must show: the probe piece loading both checkpoints, `jobs/launch.py`'s `check`
client passing, and at least one `spec` row in the records
(`grep -c '"type": "spec"' <dir>/records/*.jsonl` above 0). A run that produces
zero `spec` rows with `arm: probe` and a low `theta` means the live cut
enumeration never fired — which is exactly the divergence **[D-6]** guards, so
it is a stop, not a warning.

**G3 — the arm comparison, one task, three arms.** Run the same setting with
`arm: no_probe` and with `arm: probe`, same seed, same task:
`no_probe` must produce `n_inject == 0` on every `gen` row and no `spec` row;
`probe` must produce at least one. Both must produce the same `meta.generation`
text (the same-setup rule, 1.1).

**G4 — the resume account.** On an inject run, every `spec` row must be followed
by exactly one `resume` row with the same `fire_index`:

```bash
external/probe-env/bin/python - <<'PY'
from data.task_record import read_dir
df = read_dir('<dir>/records', pairs)
s = df.filter(df['type']=='spec'); r = df.filter(df['type']=='resume')
assert s.height == r.height
PY
```
Expected: exit 0. Under `arm: probe_nofill` the same command must additionally
show `identical` true on a majority of rows — that is the ident3 control
(`live_appworld.py:53-57`), and a sudden collapse means the head back-off is
wrong.

---

## 5. Tickets

Four tickets, one per file, in the order of section 2.

### Ticket A — `agent/inject_format.py`: the five injection formats

- **Files**: `agent/inject_format.py` (new).
- **What to do**: section 1.1 of this plan. One dataclass `Format` with the four
  fields of 7.3, one `FORMATS` literal with the five entries of 5.3, `VERSION`
  at column zero. Body text copied from
  `legacy/pipeline/inject/inject_format.py:28-46`; no control tokens, no seam
  rule, no helper functions.
- **Acceptance**: A1, A2, A3, A4, A5.
- **Needs from other folders**: nothing.

### Ticket B — `agent/generate.py`: the plain generation step

- **Files**: `agent/generate.py` (new).
- **What to do**: section 1.2. `StepResult`, `Clients`, `step`, `stream`,
  `ids_sha`, `VERSION`. The step opens one stream, accumulates text and ids,
  splits channels through the family's `parse`, and fills the eleven
  `StepResult` fields; `n_inject` 0 and `discard` zeroed.
- **Acceptance**: B1, B2, B3, B4, B5.
- **Needs from other folders**: `models/__init__.py` (`agent(alias)`,
  `AgentModel.module`); `models/agent_models/gptoss.py` (`NAME`, `parse`);
  `models/agent_models/service.py` (client: `Client(base_url,
  served_model_name)`, `stream(prompt_ids, generation, seed)`, `health()`).

### Ticket C — `agent/inject.py`: the generation step with the probe

- **Files**: `agent/inject.py` (new).
- **What to do**: section 1.3. `ARMS`, `system_text`, `step`, plus the two
  ported helpers `token_boundary` and `find_head`, the resume account and the
  `/health` refusal. Follow the eleven numbered steps; the four `FORMATS` fields
  are the only thing read out of `agent/inject_format.py`.
- **Acceptance**: C1, C2, C3, C4, C5 (and A1 re-run, since C imports A).
- **Needs from other folders**: `agent/generate.py` (ticket B);
  `agent/inject_format.py` (ticket A); `data/probe_input.py` (`cuts_live`,
  `assemble`); `data/task_record.py` (`Writer.row`, `open_record`, `read` for
  the acceptance); `data/environments/__init__.py` (`Environment`, and the
  object's `speculate`, `complete_call`, `build_call`);
  `models/probe_models/service.py` (client: `score`, `generate`, `encode`,
  `decode`, `health`); `models/__init__.py` and
  `models/agent_models/gptoss.py` (`parse`, `wrap_prefetch`, `NAME`).

### Ticket D — `agent/loop.py`: the task walk and the record

- **Files**: `agent/loop.py` (new).
- **What to do**: section 1.4. `main(run_dir, piece)`, the endpoint wait, the
  `/health` refusal, the step choice, the triple walk with the piece rotation
  and the `O_EXCL` claim, the six-column `meta` row, the per-step
  render/step/act cycle, the history rule **[D-17]**, the per-task guard
  **[D-18]**, the `final` row and the heartbeat.
- **Acceptance**: D1, D2, D3, D4, D5, D6.
- **Needs from other folders**: `experimental_settings/schema.py`
  (`load_frozen`); `data/environments/__init__.py` (`open_env`,
  `requested_pairs`, `StepObservation`); `data/task_record.py` (`open_record`,
  `Writer.row`, `Writer.frame`, `Writer.close`, `to_messages`, `read` for the
  acceptance); `data/__init__.py` (`record_id`);
  `models/agent_models/service.py` and `models/probe_models/service.py` (both
  client halves, the probe one for `render` and `health`); `jobs/registry.py`
  (`beat`, `Heartbeat.emit`, `Heartbeat.finish`, `DEFAULTS["launch_timeout_s"]`);
  plus tickets B and C.

---

## 6. Contract errata settled here

Each line below is appended to
`.scratch/from-zero/contract-errata.md` in the required format.

- **[D-1] 7.3** — a `FORMATS` entry has four fields and `render` takes no head,
  so legacy's head-seam rule has no home in the table. `agent/inject.py` applies
  it, since it holds the head text.
- **[D-2] 7.3** — `stream(clients, cfg, prefix_ids, seed)` cannot express the
  shrunken budget a resend after a fire needs (`live_appworld.py:446-450`: the
  kept ids count against the step budget, the discarded overflow does not), so
  the exported function takes a keyword-only `budget=None`.
- **[D-3] 6.2** — the family comparison ("both compare `module.NAME` against
  `cfg.models.agent_row["family"]` before their first use") is taken once per
  process, not once per step.
- **[D-4] 1.1 / 5.2** — `gen.gen_ids` and `spec.overflow_ids` are "null unless
  `store_token_ids`", and the field is spelled twice
  (`sample.store_token_ids`, `inject.store_token_ids`); the producing step reads
  it off the one section the setting holds, through the `cfg.inject is None`
  test of 5.1.
- **[D-5] 7.3** — `StepResult.prefix_sha` has no stated formula; the build uses
  legacy's, sha1 of the comma-joined decimal ids
  (`live_appworld.py:379-383`), as `ids_sha` in `agent/generate.py`, which
  `agent/inject.py` imports.
- **[D-6] 7.3 / 6.2** — `parse` returns only the two grown channel texts, while
  `find_head` needs the cut's offset inside the raw generated text. The build
  derives `ts = len(raw) - len(thinking_so_far)` while
  `raw.endswith(thinking_so_far)` holds, and stops scoring for the rest of the
  step when it stops holding (the streaming form of
  `live_appworld.py:151-162,462-467`).
- **[D-7] 6.2** — `end_of_turn(ids)` gets no caller in `agent/`: a step ends
  when its stream ends (`live_appworld.py:539-554`).
- **[D-8] 7.2** — the injector's `/health` refusal (`decode`, `encode_special`,
  the two train keys) is taken under all three arms, not scoped by arm the way
  legacy scoped it (`live_appworld.py:702-704`), because an inject run's probe
  piece always loads both checkpoints (2.3).
- **[D-9] 5.2** — under `inject.fire_nth_cut > 0` no `/score` call is made at
  all and the fire is the `fire_nth_cut`-th counted cut, with `conf` and
  `pred_label` null (`live_appworld.py:477-480`).
- **[D-10] 5.2** — `inject.chunk_tokens` and `inject.tail_tokens` are keyed
  fields with no reader: legacy's v4 rewrite to one stream per step left them
  unused (`live_appworld.py:95-108,442-455`), and the port follows v4, so they
  are carried in the setting and echoed into `meta.inject` only. **Worth the
  owner's eye**: either they get a reader or they leave the key.
- **[D-11] 5.2** — `split`, `seeds`, `tasks`, `n_tasks`, `max_steps`,
  `store_token_ids`, `pieces` and `replicas` are spelled once under `sample` and
  once under `inject`; `agent/loop.py` binds the one section the setting holds
  and reads all eight off it.
- **[D-12] 1.1 / 5.3** — `meta.arm` has four values and the `inject.arm` axis
  three; `agent/loop.py` writes `"sample"` when `cfg.inject is None` and
  `cfg.inject.arm` otherwise, and `ARMS` holds only the three axis values.
- **[D-13] 1.1** — "canonical JSON text" is unspelled for `meta.generation`,
  `meta.inject` and `final.judge`, while a string equality compares two of them;
  the build writes
  `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
- **[D-14] 1.1 / 3.4** — nothing says where the loop gets `meta.owner_session`,
  and a loop piece reads no `meta.json` (7.4); it computes 3.4's session name,
  `f"{cfg._stage}-{cfg._key}-{piece}"`. `jobs/launch.py` must spell it the same.
- **[D-15] 1.1** — `meta.version` and every row's `ts` are stamped by
  `data/task_record.py`'s writer, not passed in by `agent/loop.py`, the way
  `data/prediction.py`'s writer stamps `version` (2.6).
- **[D-16] 1.1** — `to_messages`'s `upto_step` is exclusive: the messages for
  step N carry the rows of steps 0..N-1.
- **[D-17] 1.7 / 7.3** — 7.3 says the loop appends
  `(observation.action, observation.observation)` "after each
  `Environment.step`", but both legacy sides append only for a step that
  produced an action (`live_appworld.py:816` inside the code-block branch,
  `legacy/pipeline/annotate/build.py:81-82,117` skipping before the append), and
  the offline and live histories must be identical (1.7). The loop appends only
  when `observation.action` is not None, and `data/build_dataset.py` must do the
  same.
- **[D-18] 1.1 / 7.1** — `final.abort` is defined only for the 400 case; a task
  that raises anything else would leave a record with no `final` row, which
  `is_done` never accepts and the release deletes forever. The loop keeps
  legacy's guard (`live_appworld.py:739-756`): it writes a `final` row with
  `abort=f"task_error:{type(e).__name__}"`, `success=false` and a `judge` of
  `{"success": false, "task_error": "..."}`, and walks on; a failing `judge()`
  writes `{"success": false, "eval_error": "..."}` the same way
  (`run_appworld.py:229-235`).
