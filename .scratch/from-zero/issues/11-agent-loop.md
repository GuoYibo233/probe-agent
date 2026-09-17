# 11 the agent loop: formats, generation, injection, the task walk

Status: claimed
Blocked by: 02, 03, 04, 05, 06, 07
Spec: .scratch/from-zero/spec.md (sections 2, 3, 4, 5, 6, 7)

## What to do

Four files, in this order: `inject_format.py` -> `generate.py` -> `inject.py` ->
`loop.py`. Contracts 7.3 (the step interface and what the loop does per step),
7.4 (the endpoint files), 1.1 (the record), 1.7 (the probe's input), 2.3 (the
claim and the rotation) and 5.1 (the presence test) are the specification; read
7.3 in full.

```
agent/inject_format.py   venv any   imports: none (not even third-party)   VERSION = 1
agent/generate.py        venv: the environment's (appworld today)          VERSION = 1
  imports: models/agent_models/service.py (the client), models/__init__.py (the family
           module). It imports models/probe_models/service.py NOWHERE.
agent/inject.py          venv: the environment's                          VERSION = 1
  imports: agent/generate.py, agent/inject_format.py, data/probe_input.py,
           data/trajectory_record.py, data/environments/__init__.py (type only),
           models/probe_models/service.py (client), models/__init__.py (the family module).
           It does NOT import experimental_settings/schema.py.
agent/loop.py            venv: the environment's                          VERSION = 1
  imports: experimental_settings/schema.py (load_frozen only),
           data/environments/__init__.py, data/trajectory_record.py,
           models/agent_models/service.py (client), models/probe_models/service.py
           (client, for render), agent/generate.py, agent/inject.py, jobs/registry.py.
           It imports models/__init__.py NOWHERE.
README.md                your four lines only
```

### 1. `agent/inject_format.py` (contracts 7.3, 5.3)

```python
VERSION: int                      # column zero, 3.3's literal rule
FORMATS: dict[str, Format]        # a module-level literal
```

`Format` is a dataclass declared in this file with **exactly** four fields:

| field | type | meaning (7.3) |
|---|---|---|
| `placement` | `"p1"` or `"p2"` | `p1` splices the body into the model's own reasoning; `p2` makes it a separate prefetch message |
| `needs_special` | `bool` | whether the body is encoded with real control tokens (`special=true`) or as plain text |
| `system_text` | `str \| None` | the extra system text this format needs, or None |
| `render` | `render(call, exec_out, exec_ok, error_kind) -> str` | the body, written from the speculation result |

The five keys are the axis values of 5.3 and port
`legacy/pipeline/inject/inject_format.py:28-46` **byte for byte in the body
text**:

| key | placement | needs_special | system_text | render returns |
|---|---|---|---|---|
| `note` | `p1` | `False` | `None` | `"[SYSTEM NOTE: prefetched {call} = {result}]\n"` |
| `p1_e1` | `p1` | `False` | `None` | `"[Prefetch: " + EXPLAIN + "]\n"` |
| `p1_e2` | `p1` | `False` | `SYSTEM_EXTRA` | `MARKER + "\n"` |
| `p2_e1` | `p2` | `True` | `None` | `EXPLAIN` |
| `p2_e2` | `p2` | `True` | `SYSTEM_EXTRA` | `"{call} = {result}"` |

with the three text constants copied verbatim from `inject_format.py:28-34`:

```python
EXPLAIN = ("The system already ran {call} for you and got:\n{result}\n"
           "You can use this result without calling it.")
MARKER = "[Prefetch] {call} = {result}"
SYSTEM_EXTRA = (
    "\n\nSometimes a prefetched result appears while you reason, either as a line starting with "
    "[Prefetch] or as a message from a sender named prefetch. It means the system already ran "
    "that call for you; use the result without calling it again.")
```

The legacy templates spell the second placeholder `{result}` and `render`'s
parameter is `exec_out`, so the entries format with
`.format(call=call, result=exec_out)`; keeping the template strings unedited is
what makes the ported `note` format byte-identical to today's. Today's five
entries ignore `exec_ok` and `error_kind`; both are on the signature because 7.3
puts them there.

**Not ported:** `sep_for` (`:49-52`), the head-seam rule — `render` takes no
head, so the seam moves to `agent/inject.py` (errata); `TAIL` and
`PREFETCH_SENDER` (`:36-38`) — 7.3 gives the `p2` wrapping to the family
module's `wrap_prefetch`, so **this file holds no control tokens at all**;
`system_extra(name)` (`:55-58`) and `needs_special(name)` (`:61-64`) — both
become fields; `splice_text` (`:67-73`) — its body half becomes `render`, its
seam half `agent/inject.py`, its `TAIL` half `wrap_prefetch`;
`is_prefetch_header` (`:76-78`) — no caller in the new tree.

### 2. `agent/generate.py` (contracts 7.3, 7.1, 1.1)

```python
VERSION: int

@dataclass
class StepResult:                                         # 7.3, imported by inject.py
    reasoning: str
    content: str
    usage: dict            # {"in": int, "out": int} — the gen row's struct{in,out} (1.1)
    wall_s: float
    finish_reason: str | None
    stop_reason: str | None
    prefix_tok: int
    prefix_sha: str
    gen_ids: list[int] | None
    n_inject: int
    discard: dict          # {"chars": int, "tokens": int, "events": int} (1.1)

@dataclass
class Clients:                                            # 7.3
    agent: object
    probe: object          # annotated object, never the probe client class

def step(env, clients, cfg, writer, messages, prefix_ids, history, task_text,
         step_index, seed) -> StepResult
def stream(clients, cfg, prefix_ids, seed, *, budget=None)
def ids_sha(ids: list[int]) -> str
```

`step`:

1. `t0 = time.clock_gettime(time.CLOCK_MONOTONIC)` — **never `time.time()`**: an
   open AppWorld world freezes the process clock, which is why every `gen.wall_s`
   in the legacy live run is `0.0` (errata). Check the family **once per
   process** (errata): `mod = models.agent(cfg.models.agent).module`, refuse when
   `mod.NAME != cfg.models.agent_row["family"]`.
2. Open one stream with `stream(clients, cfg, prefix_ids, seed)`; accumulate
   `raw` (text) and `gen_ids`, and call `out = mod.parse(delta, state)` per
   chunk, keeping the two keys `reasoning` and `content` of `out`. **`state` is
   one dict per step, created as `{}` before the first chunk, handed to every
   `parse` call and never rebound to the return value**: the merged
   `models/agent_models/gptoss.parse` keeps its accumulator inside the dict it
   is handed (`state["raw"]`) and returns a **new** two-key dict that does not
   carry it (6.2: "per-family bookkeeping lives in `state` and never in the
   returned dict"), so `state = mod.parse(delta, state)` would parse every
   chunk after the first alone — `B4`'s `"Hi there." in res.reasoning` fails on
   that spelling.
3. **The step ends when the stream ends** (errata: `end_of_turn(ids)` gets no
   caller in `agent/`; `live_appworld.py:539-554`). Fill `StepResult`:
   `reasoning`/`content` from the last `parse` result; `usage` summed over the
   step's requests (`{"in": prompt_tokens, "out": completion_tokens}`, falling
   back to the count of received ids when `usage` is absent because the stream
   was aborted, `live_appworld.py:543-547`); `wall_s` rounded to 2 decimals;
   `finish_reason`/`stop_reason` from the stream; `prefix_tok = len(prefix_ids)`;
   `prefix_sha = ids_sha(prefix_ids)`;
   `gen_ids = gen_ids if <store_token_ids> else None`; `n_inject = 0`;
   `discard = {"chars": 0, "tokens": 0, "events": 0}`.
4. `env`, `writer`, `messages`, `history` and `task_text` are accepted and
   **ignored** — the parameters exist so the two step implementations are
   substitutable.

`ids_sha(ids)` is ported verbatim from `live_appworld.py:379-383`:
`hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()` (errata:
`StepResult.prefix_sha` has no stated formula). `agent/inject.py` imports it.

`stream(clients, cfg, prefix_ids, seed, *, budget=None)` builds the `generation`
argument of the 7.1 client call — a dict with exactly `max_tokens`,
`temperature`, `top_p`, `stop` — and returns
`clients.agent.stream(prefix_ids, gen, seed)`. `max_tokens` is
`cfg.generation.max_step_tokens` when `budget is None` and `budget` otherwise.
**The keyword-only `budget` is errata:** 7.3's signature cannot express the
shrunken budget a resend after a fire needs (`live_appworld.py:446-450`: the kept
ids count against the step budget, the discarded overflow does not). The request
body, the retries and the `(text_delta, token_ids_delta)` shape are the client's
and are not written here.

**`store_token_ids` is read off the one section the setting holds** (errata),
through the `cfg.inject is None` test of 5.1: `cfg.sample.store_token_ids` on a
sample run, `cfg.inject.store_token_ids` on an inject run.

Legacy source: `live_appworld.py:411-455` and `:539-569` (the non-probing half of
`gen_step`), `:379-383`, `:786-802`.
**Not ported:** `Stream`, `open_stream`, `sample_extras`, `gen_payload`,
`http_json` (`:190-287`) — the request body, the retry policy and the streaming
protocol are `models/agent_models/service.py`'s; `parse_step` (`:111-148`) — the
family module's `parse`; `think_span` (`:151-162`); the wrap-up consistency check
(`:556-567`).

### 3. `agent/inject.py` (contracts 7.3, 7.2, 1.1)

```python
VERSION: int
ARMS = ("probe", "no_probe", "probe_nofill")    # a module-level literal, column zero

def step(env, clients, cfg, writer, messages, prefix_ids, history, task_text,
         step_index, seed) -> StepResult        # the same signature as generate.step
def system_text(cfg) -> str | None
def ensure_health(clients, cfg) -> None         # the /health refusal, taken once per run
def token_boundary(bounds, pos) -> tuple[int, int] | None   # (n_chars, n_ids), :324-337
def find_head(gen_ids, raw, pos, k0, decode) -> tuple[int, str]   # :340-376
```

`system_text(cfg)` returns `FORMATS[cfg.inject.format].system_text` **only when
that entry's `placement` is `"p1"`**, and `None` otherwise — None for a `p2`
entry (whose system text `wrap_prefetch` applies) and None when `cfg.inject is
None`.

**The `/health` refusal** (7.2) is `ensure_health(clients, cfg)`, a **module-level
function that `agent/loop.py` calls once**, before the walk, when
`cfg.inject is not None` — **never inside `step` behind a once-flag** (errata: 7.3
says "once before the first request of the run" and names no home; putting it in
`step` makes every stub client of every acceptance need a `health()` and makes the
refusal a per-step branch). It refuses unless the echo reports `decode: true`,
`encode_special: true` whenever `FORMATS[cfg.inject.format].needs_special` is
true, and `score_train_key` / `gen_train_key` equal to
`cfg._upstream["probe_score.train"]` and `cfg._upstream["probe_gen.train"]`. It
also compares `mod.NAME` against `cfg.models.agent_row["family"]`. **The refusal
is unconditional across the three arms** (errata; legacy scoped it by arm at
`live_appworld.py:702-704`, but an inject run's probe piece always loads both
checkpoints).

**What `step` does** (7.3 item 4, algorithm from `live_appworld.py:411-569`):

1. Accumulate `raw`, `gen_ids` and `bounds` (the `(len(raw), len(gen_ids))` pair
   at the end of each chunk, `:432,456`). **`bounds` starts as `[(0, 0)]`**
   (`:433`, verbatim): `token_boundary` returns the last boundary no later than
   `pos` and `None` when there is none, and without the zero pair a fire inside
   the first chunk gets `None` and step 6's `token_boundary(bounds, pos)[1]`
   raises. Stream over
   `generate.stream(clients, cfg, prefix_ids, seed,
   budget=max(1, cfg.generation.max_step_tokens - len(gen_ids)))`.
2. Per chunk, `out = mod.parse(delta, state)`;
   `thinking_so_far = out["reasoning"]` — `state` is the accumulator dict of
   `generate.step`'s step 2, never rebound to the return value, and the
   invariant is **`state["raw"] == raw` at all times**. **Stop scoring for the rest of the
   step as soon as `raw.endswith(thinking_so_far)` stops holding**; while it
   holds, `ts = len(raw) - len(thinking_so_far)`. **This is the riskiest decision
   in the folder (errata):** `parse` returns only the two grown channel texts,
   while `find_head` needs the cut's offset inside the raw generated text; this is
   the streaming form of `live_appworld.py:151-162,462-467`.
3. Skip the rescan when the chunk carries none of `.!?\n` (`:459-460`).
4. `probe_input.cuts_live(thinking_so_far, cfg.build.min_think)` gives the
   candidate offsets; score a cut that was not scored before, and **only once
   `len(thinking_so_far.strip()) >= cfg.build.min_think`** (1.7's event-level gate
   in its streaming form). Stop after `cfg.inject.max_cuts` cuts have been scored
   in this step (`:472-474`), and stop injecting after
   `cfg.inject.max_inject_per_step` fires (`:457`).
5. Scoring: `clients.probe.score(probe_input.assemble(task_text, history,
   thinking_so_far[:cut], cfg.build.hist_rounds, cfg.build.probe_result_cap))`.
   Fire on the first `conf >= cfg.inject.theta`. **Under
   `cfg.inject.fire_nth_cut > 0` no `/score` call is made at all** and the fire is
   the `fire_nth_cut`-th counted cut, with `conf` and `pred_label` null (errata,
   `:477-480`). Under `arm: no_probe` nothing is ever scored and the step is one
   uninterrupted stream (`:438`).
6. On a fire: `pos = ts + cut` (raw coordinates);
   `k0 = token_boundary(bounds, pos)[1]` — `token_boundary` returns the
   `(n_chars, n_ids)` pair and `find_head` wants the id count;
   `k, head_txt = find_head(gen_ids, raw, pos, k0,
   lambda ids: clients.probe.decode(ids)["text"])` — the probe client returns the
   route's decoded JSON dict (ticket 07) while `find_head` compares and slices a
   **string**, so the caller unwraps it; both ported verbatim from `:324-337` and
   `:340-376`, the decode callable being one
   `POST /decode` per candidate id. `head_ids = gen_ids[:k]`,
   `overflow_ids = gen_ids[k:]`. A mismatch between `decode(ids[:k])` and the
   streamed text **raises**, never passes silently (`:372-375`).
7. Under `arm: probe_nofill` nothing is generated or executed: `note = ""`,
   `note_ids = []`, and the `spec` row's `gen_call`, `exec_code`, `arg_modes`,
   `exec_out`, `exec_ok`, `error_kind` are null (`:495-498`). Otherwise:
   `call = clients.probe.generate(<the probe's text at the cut>,
   cfg.inject.max_new)["call"]`, `call = env.complete_call(call)`,
   `spec = env.speculate(call)` — whose returned dict is **copied into the `spec`
   row unchanged** (4.3) — then
   `body = FORMATS[fmt].render(call, spec["exec_out"], spec["exec_ok"], spec["error_kind"])`
   and
   - `placement == "p1"`: `note = ("" if head_txt[-1:].isspace() else "\n") + body`
     (the seam rule, errata);
   - `placement == "p2"`: `note = mod.wrap_prefetch(body, FORMATS[fmt].system_text)`.
   `note_ids = clients.probe.encode(note, special=FORMATS[fmt].needs_special)["ids"]`.
8. Write the `spec` row with all of 1.1's columns: **`step` (`step_index` — 1.1
   declares `step` on every row kind but `meta`, the writer stamps only `type`
   and `ts`, and `eval/score_run.py` pairs a `spec` row with the `env` row of
   the same step through it)**, `fire_index` (0-based within
   the step), `cut`, `n_checked` (**the cuts counted in this step up to and
   including this one**, so the first cut of a step records 1 — errata: 1.1's
   table says "before this one", while `:476,516` increment before the score
   call, `fire_nth_cut` fires when `n_checked == cfg.inject.fire_nth_cut`, and
   `C4` asserts 1; under `fire_nth_cut > 0` a counted cut is one that would have
   been scored), `conf`, `pred_label`, `gen_call`, `exec_code`,
   `arg_modes`, `exec_out`, `exec_ok`, `error_kind`, `note`, `format`
   (`cfg.inject.format`), `head_tok` (`k`), `head_chars` (`len(head_txt) - ts`),
   `note_tok` (`len(note_ids)`), `discarded_chars`
   (`max(0, len(raw) - len(head_txt))`), `overflow_ids` (null unless
   `store_token_ids`), `spec_s`.
9. Reset the stream state exactly as `:529-535`: `raw = head_txt + note`,
   `gen_ids = head_ids + note_ids`, `bounds = [(len(raw), len(gen_ids))]`, the
   scored-cut set cleared, `accepted = (len(head_txt) - ts) + len(note)` so the
   text before the splice is not re-scored; **the parse accumulator is rebuilt
   from the new `raw`** — `state = {}` then `out = mod.parse(raw, state)` — so
   `state["raw"] == raw` holds again (errata); close the stream and re-issue.
10. The `resume` row is written when the next fire arrives or when the step ends
    with a fire outstanding (`:396-408`, `:527-528`, `:548-550`): `step`
    (`step_index`, as on the `spec` row), `fire_index`,
    `overflow_tok`, `new_tok`, `match_len`, `identical`, `stop_reason`.
11. Return a `StepResult` whose `n_inject` is the fire count and whose `discard`
    accumulates `chars`, `tokens` and `events` (`:512-514`). Everything else is
    filled exactly as `generate.step` fills it.

Legacy source: `live_appworld.py:324-337, 340-376, 396-408, 411-569, 572-587,
386-393`.
**Not ported:** `speculate` (`:305-321`) — the three-step guarantee is
`data/environments/appworld.py`'s and this file copies the returned dict in;
`selftest_shadow` (`:841-872`); the `spec` row's legacy-only fields `nofill`,
`head_ends_ws`, `head_tail`, `n_chunks`; `--no-probe`'s scoping of the `/health`
checks (`:702-704`).

**Flagged, not settled here:** `cfg.inject.chunk_tokens` and
`cfg.inject.tail_tokens` are keyed fields with **no reader** — legacy's v4
rewrite to one stream per step left them unused (`:95-108,442-455`) and the port
follows v4. Carry them in the setting and in `meta.inject` and read them nowhere.

### 4. `agent/loop.py` (contracts 7.3, 7.4, 2.3, 1.1)

```python
VERSION: int
def main(run_dir, piece) -> None      # 2.1's program column: agent.loop, main(run_dir, piece)
                                      # `piece` is the (i, n) PAIR parsed from --piece i/n
```

**`piece` is the pair, and `i` is the index.** `main`'s second parameter is the
`(i, n)` tuple the `__main__` block parses out of `--piece i/n` — that is what
the D-fixture passes (`loop.main(rd, (0, 1))`). Everything below that needs a
number names `i` explicitly; nothing indexes or rotates with the pair.

Command shape (2.6, 3.4): `<venv python> -m agent.loop --run-dir <dir> --piece
<i>/<n>`, repo root as the working directory, **no setting name anywhere**. The
`__main__` block parses those two flags and nothing else.

**What it does, in order.**

1. `cfg = schema.load_frozen(run_dir)`. Bind
   `run = cfg.inject if cfg.inject is not None else cfg.sample` and read
   `run.split`, `run.seeds`, `run.tasks`, `run.n_tasks`, `run.max_steps`,
   `run.store_token_ids`, `run.replicas` off it (errata: the eight fields are
   spelled once under `sample` and once under `inject`).
2. `env = open_env(cfg.data.env)`.
3. Endpoint files (7.4): compute `i mod run.replicas` from its own `--piece i/n`,
   open `service_agent_<that>.json` and `service_probe_0.json` **in its own run
   directory**, waiting for both and giving up after
   `registry.DEFAULTS["launch_timeout_s"]`. Build
   `clients = generate.Clients(agent=AgentClient(base_url,
   cfg.models.agent_row["served_model_name"]), probe=ProbeClient(base_url))`.
   **`open_env`, `AgentClient` and `ProbeClient` are module-level names of
   `agent/loop.py`** — bound once at import
   (`from data.environments import open_env, requested_pairs`,
   `from models.agent_models.service import Client as AgentClient`,
   `from models.probe_models.service import Client as ProbeClient`) and looked up
   through the module, never re-imported inside a function. That is what lets
   `D3`, `D5` and `D6` substitute all three without a stub file anywhere in the
   tree, and there is no legal place for a stub environment file: a new file under
   `data/environments/` is outside the fixed tree and would move
   `schema.AXES["data.env"]`, which `selfcheck` check 3 compares against that
   directory's file stems.
4. The `/health` refusal (7.2): refuse unless the probe service reports
   `render == "ids"`, `family == cfg.models.agent_row["family"]` and
   `weights == cfg.models.agent_row["weights"]`, naming the field and both values.
5. `gen_step = inject.step if cfg.inject is not None else generate.step`.
   `extra = inject.system_text(cfg)`, passed on **every** `to_messages` call.
6. `triples = requested_pairs(env, run.split, run.tasks, run.n_tasks,
   run.seeds)`. Walk them rotated by the piece index `i`:
   `triples[i:] + triples[:i]` (2.3, today's pool mode,
   `live_appworld.py:718-723`).
7. `hb = registry.beat(run_dir, i)`; `hb.emit(0, len(triples), "task")`
   before the walk; one `emit(done, len(triples), "task", tok_in=…, tok_out=…)`
   per finished task; `hb.finish()` at the end. `total` is the **whole** requested
   count for every piece (8.4).
8. Per triple `(split, task_id, seed)`:
   - `writer = open_record(run_dir, task_id, seed)` — **the run directory**;
     `data/trajectory_record.py` appends `records/` itself (errata). `None` means
     another piece holds it: move on, deleting nothing.
   - `env.open(task_id, seed)`; capture `env.task_text`.
   - `writer.row("meta", …)` with every column of 1.1's `meta` block:
     `record_id` (`data.record_id(task_id, seed)`), `stage` (`cfg._stage`),
     `env` (`cfg.data.env`), `task_id`, `seed`, `env_seed` (`env.SEED`),
     `split` (**the triple's first element**, 2.3), `arm` (`"sample"` when
     `cfg.inject is None`, else `cfg.inject.arm` — errata: `meta.arm` has four
     values and the `inject.arm` axis three), `instructions`
     (`cfg.data.instructions`), `task_text`, `agent_model` (`cfg.models.agent`),
     `generation` and `inject` as **canonical JSON text** —
     `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`
     (errata) — `commit` (`cfg._commit`, never probed from git), `run_key`
     (`cfg._key`), `owner_session` (`f"{cfg._stage}-{cfg._key}-{i}"`, 3.4's
     session name — **`jobs/launch.py` must spell it the same**, errata).
     `version` and `ts` are stamped by the writer, not passed in.
   - For `step_index` in `range(run.max_steps)`:
     `messages = to_messages(writer.frame(), step_index, task_text,
     env.INSTRUCTIONS[cfg.data.instructions], env.NO_CODE_MESSAGE, extra)`
     (`upto_step` is exclusive);
     `prefix_ids = clients.probe.render(messages, cfg.generation.effort,
     cfg.generation.date)["prefix_ids"]` — **once per step**, and nothing below
     renders again;
     `res = gen_step(env, clients, cfg, writer, messages, prefix_ids, history,
     task_text, step_index, seed)`;
     `writer.row("gen", step=step_index, **asdict(res))`;
     `obs = env.step(res.content)` (the extraction, the execution, the clip and
     the completion test are all the environment's);
     `writer.row("env", step=step_index, action=obs.action,
     result=obs.observation, error_kind=obs.error_kind)`;
     append `(obs.action.strip(), obs.observation)` to `history` **only when
     `obs.action` is a string whose `strip()` is non-empty** — the record row
     above keeps `obs.action` as the environment returned it, only the history
     entry is stripped (errata, gyb's ruling of 2026-09-18 — 7.3 says "after
     each `Environment.step`", but `data/build_training_dataset.py` appends
     `(action.strip(), result)` and leaves a step whose stripped action is empty
     out of its history, and 1.7 makes the offline and the live history
     identical: AppWorld returns `'print(1+1)\n'` for an ordinary code block and
     `''` for an empty one, so the unstripped form would differ from the
     training text on nearly every step);
     break when `obs.completed`.
   - A 400 from the agent client sets `abort = "context_overflow_400"` and ends
     the trajectory (7.1). **Any other exception from one task is caught,
     recorded and walked past** (errata, `live_appworld.py:739-756`): write a
     `final` row with `abort=f"task_error:{type(e).__name__}"`, `success=false`
     and a `judge` of `{"success": false, "task_error": "..."}`.
     **Two shapes the guard must keep**, because `data/trajectory_record.REQUIRED`
     rests on them (ticket 02): the `final` row carries **every** column of 1.1's
     `final` block whatever the abort — `steps` (the steps finished), `completed`
     (`False`), `tokens_in`, `tokens_out`, `wall_s` and `finished_at` from the
     accumulators — and **the `meta` row is written before anything that can
     raise**, so an exception out of `env.open` still leaves a `meta`-first file:
     the guard writes the `meta` row itself (with `task_text=""`) when it fires
     before the normal one did. A record whose first line is not a `meta` row is
     unattributable to `read` and is what `release`'s second clause deletes.
   - `judge = env.judge()`; `writer.row("final", steps=…, completed=…, abort=…,
     judge=<canonical JSON of the dict>, success=<the dict's own `success`>,
     tokens_in=…, tokens_out=…, wall_s=…, finished_at=…)`. A failing `judge()`
     writes `{"success": false, "eval_error": "..."}` the same way.
     `writer.close()`.
   - `env.close()` in a `finally`.

**Every wall-clock value this file writes** — `final.wall_s`,
`final.finished_at`, and anything it passes to the heartbeat — uses
`time.clock_gettime(time.CLOCK_REALTIME)` for a unix timestamp and
`time.clock_gettime(time.CLOCK_MONOTONIC)` for a duration (errata: the AppWorld
world freezes the process clock).

Legacy source: `live_appworld.py:606-757` and `:759-838`;
`legacy/envs/collect/run_appworld.py:109-244`.
**Not ported:** the `--preset` merge (`live_appworld.py:663-684`); every one of
`--split/--n/--task-ids/--shard-id/--num-shards/--pool/--resume/--keep-outputs/--exp/--model/--base-url/--probe-url`
(`:606-659`); `claim` (`:590-603`); `is_done`/`--resume`
(`run_appworld.py:79-82`, `live_appworld.py:732-736`); `resolve_seeds`,
`traj_path`, `exp_name`, `traj_meta` (`run_appworld.py:48-106`); the code-block
regex, the no-code reply and the `world.execute` call (`run_appworld.py:45,204-217`,
`live_appworld.py:804-816`) — `Environment.step` owns them; `system_prompt(fmt)`
(`live_appworld.py:389-393`); `probe_cfg_problem`'s `render == "harmony_ids"` and
`p2_*` literals (`:572-587`); `heartbeat.emit` from `legacy/ops/heartbeat.py`.

## Acceptance

Run from the repo root and paste the real output.

```bash
A=/home/y-guo/reproduce/new1/external/appworld/venv/bin/python
P=/home/y-guo/reproduce/new1/external/probe-env/bin/python
V=/home/y-guo/reproduce/new1/external/vllm-env/bin/python
```

**A1 — `inject_format.py` imports under four interpreters.**
```bash
for py in "$P" "$A" "$V" python3; do
  $py -c "import agent.inject_format as F; print(F.VERSION, sorted(F.FORMATS))" || exit 1
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
    assert [x.name for x in dataclasses.fields(f)] == ['placement','needs_special','system_text','render'], k
    assert f.placement in ('p1','p2'), k
    assert f.needs_special == (f.placement == 'p2'), k
    assert callable(f.render), k
print('fields ok', len(FORMATS))"
```
Expected: `fields ok 5`, exit 0.

**A3 — the rendered bodies are byte-identical to the legacy table.**
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
print('render ok')"
```
Expected: `render ok`, exit 0.

**A4 — `system_text` is set on exactly the two `*_e2` entries.**
```bash
python3 -c "
from agent.inject_format import FORMATS
have = sorted(k for k,f in FORMATS.items() if f.system_text)
assert have == ['p1_e2','p2_e2'], have
t = FORMATS['p1_e2'].system_text
assert t == FORMATS['p2_e2'].system_text
assert t.startswith('\n\nSometimes a prefetched result appears while you reason') and t.endswith('use the result without calling it again.'), repr(t[:40])
print('system_text ok')"
```
Expected: `system_text ok`, exit 0.

**A5 — no control token anywhere in `inject_format.py`.**
```bash
test "$(grep -c '<|start|>\|<|end|>\|<|channel|>\|<|message|>' agent/inject_format.py)" = 0 \
  && echo NO_CONTROL_TOKEN
```
Expected: `NO_CONTROL_TOKEN`, exit 0. The `test` wrapper is deliberate: `grep -c`
**exits 1 when the count is zero**, so a bare `grep -c` expecting `0` makes a
correct implementation look like a failed command.

**B1 — `generate.py` imports, and `StepResult`'s eleven fields in order.**
```bash
for py in "$A" "$P"; do
  $py -c "import agent.generate as g; print(g.VERSION, [f.name for f in __import__('dataclasses').fields(g.StepResult)])" || exit 1
done
```
Expected: two lines, each listing exactly
`['reasoning', 'content', 'usage', 'wall_s', 'finish_reason', 'stop_reason', 'prefix_tok', 'prefix_sha', 'gen_ids', 'n_inject', 'discard']`.

**B2 — `Clients` has two fields and `generate.py` names the probe client nowhere.**
```bash
"$A" -c "
import dataclasses, agent.generate as g
assert [f.name for f in dataclasses.fields(g.Clients)] == ['agent','probe']
print('clients ok')"
grep -c 'probe_models' agent/generate.py
```
Expected: `clients ok`, then `0`.

**B3 — `step`'s pinned signature.**
```bash
"$A" -c "
import inspect, agent.generate as g
sig = list(inspect.signature(g.step).parameters)
assert sig == ['env','clients','cfg','writer','messages','prefix_ids','history','task_text','step_index','seed'], sig
print('sig ok')"
```
Expected: `sig ok`, exit 0.

**B4 — the real entry point on a fake agent client.**
```bash
"$A" - <<'PY'
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
    models=types.SimpleNamespace(agent="gpt_oss_120b",
                                 agent_row={"family": "gptoss", "weights": "gpt_oss_120b",
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
Expected: `step ok stop <|return|>`, exit 0.

**B5 — `ids_sha` reproduces the legacy hash.**
```bash
"$A" -c "
import hashlib, agent.generate as g
assert g.ids_sha([11,12,13]) == hashlib.sha1(b'11,12,13').hexdigest()
print('ids_sha ok')"
```
Expected: `ids_sha ok`, exit 0.

**C1 — `inject.py`'s two literals and the shared signature.**
```bash
"$A" -c "
import inspect, agent.inject as i, agent.generate as g
assert i.ARMS == ('probe','no_probe','probe_nofill'), i.ARMS
assert list(inspect.signature(i.step).parameters) == list(inspect.signature(g.step).parameters)
print('inject ok', i.VERSION)"
grep -n '^ARMS' agent/inject.py
```
Expected: `inject ok 1`, then one `ARMS = (...)` match **at column zero**.

**C2 — `system_text` for the six cases.**
```bash
"$A" -c "
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

**C3 — `find_head` and `token_boundary` on the legacy lag fixture.**
```bash
"$A" - <<'PY'
import agent.inject as inj
toks = ["Hello", " world.", " Then", " more."]
def decode(ids): return "".join(toks[i] for i in ids)
gen_ids = [0, 1, 2, 3]
raw = "Hello world."                      # the stream is behind the ids
pos = len("Hello world.")
k0 = inj.token_boundary([(0, 0), (12, 2)], pos)[1]
k, head = inj.find_head(gen_ids, raw, pos, k0, decode)
assert (k, head) == (2, "Hello world."), (k, head)
print("find_head ok", k)
PY
"$A" - <<'PY'
import agent.inject as inj
try:
    inj.find_head([0], "XYZ", 3, 1, lambda ids: "ABC")
except RuntimeError:
    print("raises ok")
else:
    raise SystemExit("find_head accepted a mismatched decode")
PY
```
Expected: `find_head ok 2`, then `raises ok`, exit 0 both.

**C4 — a whole fired step against stub clients and a real record writer.** This
is the acceptance that matters.

**The stub stream and the stub decoder are inverses of each other, and that is
not decoration.** `find_head` is ported verbatim from `:340-376`: it decodes id
prefixes, advances until the decoded text covers the cut, backs off to the
shortest that still does, and **raises** when the decoded head does not match the
streamed text character for character — `C3`'s second half proves that raise
fires. A decoder that cannot reproduce the stream therefore makes the fire path
raise before a single `spec` row is written, and every assertion below becomes
unreachable. One id per character is the simplest exact inverse and it makes the
derived numbers computable by hand:

| number | how it comes out |
|---|---|
| `ts = 30` | `len(raw) - len(state["reasoning"])` after chunk 1: 49 − 19 |
| `cut = 18` | `cuts_live("I will look it up. ", 4)` — `SENT_RE`'s `m.start()`, the whitespace after the `.` |
| `pos = 48` | `ts + cut` |
| `head_tok = k = 48` | one id per character, so the shortest prefix covering `pos` is `pos` ids |
| `head_chars = 18` | `len(head_txt) - ts` = 48 − 30 |
| `overflow_ids = [32]` | the one trailing space of chunk 1 |
| `discarded_chars = 1` | `len(raw) - len(head_txt)` = 49 − 48 |
| `note_tok = 2` | the stub `encode` returns two ids |

```bash
"$A" - <<'PY'
import dataclasses, tempfile, types
from pathlib import Path
import agent.generate as g, agent.inject as inj
from agent.inject_format import FORMATS
from data.trajectory_record import open_record, read

CHUNK1A = "<|channel|>analysis<|message|>I will look it up. "        # 49 characters
CHUNK1B = "Next I check the profile. "
CHUNK2  = "Done.<|end|><|start|>assistant<|channel|>final<|message|>```python\nx=1\n```"
def IDS(s): return [ord(c) for c in s]          # one id per character

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
            return FakeStream([(CHUNK1A, IDS(CHUNK1A)), (CHUNK1B, IDS(CHUNK1B))])
        return FakeStream([(CHUNK2, IDS(CHUNK2))])

class FakeProbe:
    def score(self, text): return {"conf": 0.99, "label": "apis.supervisor.show_profile", "wall_s": 0.01}
    def generate(self, text, max_new): return {"call": "apis.supervisor.show_profile()", "wall_s": 0.02}
    def encode(self, text, special): return {"ids": [90, 91]}
    def decode(self, ids): return {"text": "".join(chr(i) for i in ids)}   # the exact inverse of IDS
    def health(self):                      # ensure_health is loop.py's call, not step's;
        return {"render": "ids", "decode": True, "encode_special": True,   # here for safety
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
    models=types.SimpleNamespace(agent="gpt_oss_120b",
        agent_row={"family": "gptoss", "weights": "gpt_oss_120b", "served_model_name": "gpt-oss-120b"}))

rd = Path(tempfile.mkdtemp())                       # the RUN DIRECTORY
w = open_record(rd, "50e1ac9_1", 42)
w.row("meta", stage="inject", env="appworld", task_id="50e1ac9_1",
      seed=42, env_seed=100, split="test", arm="probe", instructions="v1",
      task_text="do the thing", agent_model="gpt_oss_120b", generation="{}", inject="{}",
      commit="deadbeef", run_key="k", owner_session="inject-k-0")
res = inj.step(FakeEnv(), g.Clients(agent=FakeAgent(), probe=FakeProbe()), cfg, w,
               [], [11, 12], [("print(1)", "1")], "do the thing", 0, 42)
w.close()
df = read(next((rd/"records").glob("*.jsonl")))
kinds = df["type"].to_list()
assert kinds.count("spec") == 1 and kinds.count("resume") == 1, kinds
spec = df.filter(df["type"] == "spec").to_dicts()[0]
assert spec["fire_index"] == 0 and spec["format"] == "p1_e1" and spec["exec_ok"] is True
assert spec["gen_call"] == "apis.supervisor.show_profile()"
assert spec["cut"] == 18 and spec["n_checked"] == 1, spec
body = FORMATS["p1_e1"].render("apis.supervisor.show_profile()", "{'name': 'x'}", True, None)
assert spec["note"] == "\n" + body, repr(spec["note"])   # the p1 seam: the head ends in "."
assert spec["head_tok"] == 48 and spec["head_chars"] == 18, spec
assert spec["note_tok"] == 2 and spec["discarded_chars"] == 1, spec
assert spec["overflow_ids"] == [32], spec["overflow_ids"]   # store_token_ids: true
assert res.n_inject == 1 and res.discard == {"chars": 1, "tokens": 1, "events": 1}, res
print("inject step ok", res.n_inject, spec["head_tok"], spec["note_tok"])
PY
```
Expected: one line `inject step ok 1 48 2`, exit 0. The `note` assertion is the
seam rule of step 7 spelled out, not a prefix test: `head_txt` ends in `.`, which
is not whitespace, so the body is preceded by one newline.

**C5 — the two control arms never call the probe.** C4's fixture, repeated with a
`FakeProbe` whose `score` and `generate` raise, and one fresh run directory per
arm (the `O_EXCL` claim gives a record file one writer). **The stream and the
decoder are the same exact inverses C4 uses**, and for the same reason: the
`probe_nofill` arm fires by `fire_nth_cut` and therefore reaches `find_head` as
well, where a decoder that cannot reproduce the stream raises.
```bash
"$A" - <<'PY'
import dataclasses, tempfile, types
from pathlib import Path
import agent.generate as g, agent.inject as inj
from data.trajectory_record import open_record, read

CHUNK1A = "<|channel|>analysis<|message|>I will look it up. "        # 49 characters
CHUNK1B = "Next I check the profile. "
CHUNK2  = "Done.<|end|><|start|>assistant<|channel|>final<|message|>```python\nx=1\n```"
def IDS(s): return [ord(c) for c in s]          # one id per character

class FakeStream:
    finish_reason, stop_reason = "stop", "<|return|>"
    usage = {"prompt_tokens": 5, "completion_tokens": 6}
    def __init__(self, chunks): self.chunks = chunks
    def __iter__(self):
        for c in self.chunks: yield c
    def close(self): pass

class FakeAgent:
    def __init__(self): self.n = 0
    def stream(self, ids, generation, seed):
        self.n += 1
        if self.n == 1:
            return FakeStream([(CHUNK1A, IDS(CHUNK1A)), (CHUNK1B, IDS(CHUNK1B))])
        return FakeStream([(CHUNK2, IDS(CHUNK2))])

class RaisingProbe:                       # score and generate must never be reached
    def score(self, text): raise AssertionError("score was called")
    def generate(self, text, max_new): raise AssertionError("generate was called")
    def encode(self, text, special): return {"ids": [90, 91]}
    def decode(self, ids): return {"text": "".join(chr(i) for i in ids)}   # the exact inverse of IDS
    def health(self):
        return {"render": "ids", "decode": True, "encode_special": True,
                "family": "gptoss", "weights": "gpt-oss-120b",
                "score_train_key": "t1", "gen_train_key": "t2"}

class FakeEnv:
    SEED = 100
    def complete_call(self, t): return t
    def build_call(self, tool, args): return tool + "()"
    def speculate(self, call): raise AssertionError("speculate was called")

@dataclasses.dataclass
class Gen: temperature: float = 1.0; top_p: object = None; max_step_tokens: int = 8192; stop: object = None; effort: str = "high"; date: str = "2026-08-06"

def mkcfg(arm, nth):
    return types.SimpleNamespace(
        _stage="inject", _key="k", _commit="deadbeef", _debug=True,
        _upstream={"probe_score.train": "t1", "probe_gen.train": "t2"},
        data=types.SimpleNamespace(env="appworld", instructions="v1"),
        generation=Gen(),
        build=types.SimpleNamespace(min_think=4, hist_rounds=3, probe_result_cap=400),
        sample=None,
        inject=types.SimpleNamespace(theta=0.5, arm=arm, format="p1_e1", fire_nth_cut=nth,
                                     max_inject_per_step=1, max_cuts=64, max_new=96,
                                     chunk_tokens=64, tail_tokens=1024, store_token_ids=True,
                                     split=["test"], seeds=[42], tasks=None, n_tasks=None,
                                     max_steps=30, pieces=1, replicas=1),
        models=types.SimpleNamespace(agent="gpt_oss_120b",
            agent_row={"family": "gptoss", "weights": "gpt-oss-120b",
                       "served_model_name": "gpt-oss-120b"}))

for arm, nth, fires in (("no_probe", 0, 0), ("probe_nofill", 1, 1)):
    cfg = mkcfg(arm, nth)
    rd = Path(tempfile.mkdtemp())
    w = open_record(rd, "50e1ac9_1", 42)
    w.row("meta", stage="inject", env="appworld", task_id="50e1ac9_1", seed=42,
          env_seed=100, split="test", arm=arm, instructions="v1",
          task_text="do the thing", agent_model="gpt_oss_120b", generation="{}", inject="{}",
          commit="deadbeef", run_key="k", owner_session="inject-k-0")
    res = inj.step(FakeEnv(), g.Clients(agent=FakeAgent(), probe=RaisingProbe()), cfg, w,
                   [], [11, 12], [("print(1)", "1")], "do the thing", 0, 42)
    w.close()
    df = read(next((rd / "records").glob("*.jsonl")))
    kinds = df["type"].to_list()
    assert res.n_inject == fires, (arm, res.n_inject)
    assert kinds.count("spec") == fires, (arm, kinds)
    if fires:
        s = df.filter(df["type"] == "spec").to_dicts()[0]
        for k in ("gen_call", "exec_code", "arg_modes", "exec_out", "exec_ok", "error_kind"):
            assert s[k] is None, (k, s[k])
        assert s["conf"] is None and s["pred_label"] is None, s
        assert s["note"] == "" and s["note_tok"] == 0, s
        assert s["head_tok"] == 48 and s["head_chars"] == 18, s   # the same head as C4
    print(arm, "ok", res.n_inject, kinds.count("spec"))
print("arms ok")
PY
```
Expected:
```
no_probe ok 0 0
probe_nofill ok 1 1
arms ok
```
exit 0. `score` and `generate` are never reached under either arm — `no_probe`
scores nothing at all, and `probe_nofill` fires by `fire_nth_cut` (so no `/score`
call, 7.3 and `:477-480`) and injects nothing (so no `/gen` and no `speculate`).

**D1 — `loop.py` imports, and the forbidden import is absent.**
```bash
"$A" -c "import agent.loop as l; print(l.VERSION)"
grep -n '^ *import models\|^ *from models import\|from models\.' agent/loop.py | grep -v 'models\.agent_models\.service\|models\.probe_models\.service'
```
Expected: a version number, then **no output** from the grep (exit 1 from grep is
the pass).

**D2 — the command shape.**
```bash
"$A" -m agent.loop --help
```
Expected: a usage line naming exactly `--run-dir` and `--piece`; no `--split`, no
`--model`, no `--base-url`, no setting name.

**The D-fixture, written once and reused by D3, D5 and D6.** No stub file is
added anywhere: `open_env` and the two client classes are substituted on the
`agent.loop` module, which section 4 pins as module-level names. Write it to
`/tmp/loopfix.py`.
```bash
cat > /tmp/loopfix.py <<'PY'
"""Stubs and a run directory for agent/loop.py's acceptance. Adds no repo file."""
import json, pathlib, tempfile, types
import agent.loop as loop
from data.environments import StepObservation

TASKS = {"train": ["t_1", "t_2", "t_3"], "dev": ["d_1"], "test": ["x_1"]}

class FakeEnv:
    SEED = 100
    SPLIT_ROLE = {"train": "train", "dev": "val", "test": "test"}
    INSTRUCTIONS = {"v1": "DEV TEXT"}
    NO_CODE_MESSAGE = "NO CODE"
    def __init__(self): self.task_text = None; self.n = 0
    def tasks(self, split): return list(TASKS[split])
    def open(self, task_id, seed): self.task_text = "Play my playlist."; self.n = 0
    def step(self, content):
        self.n += 1
        return StepObservation(action="print(apis.a.x())", observation="ok",
                               error_kind=None, completed=True)
    def judge(self): return {"success": True}
    def close(self): self.task_text = None

class FakeStream:
    finish_reason, stop_reason = "stop", "<|return|>"
    usage = {"prompt_tokens": 5, "completion_tokens": 6}
    def __iter__(self):
        yield ("<|channel|>analysis<|message|>I will do it.<|end|>"
               "<|start|>assistant<|channel|>final<|message|>```python\nx=1\n```", [1, 2, 3])
    def close(self): pass

class FakeAgentClient:
    def __init__(self, base_url, served_model_name): pass
    def stream(self, ids, generation, seed): return FakeStream()

HEALTH = {"render": "ids", "family": "gptoss", "weights": "gpt-oss-120b"}

class FakeProbeClient:
    def __init__(self, base_url): pass
    def health(self): return dict(HEALTH)
    def render(self, messages, effort, date):
        return {"prefix_ids": [11, 12], "n_tokens": 2, "wall_s": 0.0}

SETTINGS = """
data: {env: appworld, instructions: v1}
models: {agent: gpt_oss_120b, agent_row: {role: agent, family: gptoss,
         weights: gpt-oss-120b, dtype: auto, quantization: null,
         max_model_len: 131072, served_model_name: gpt-oss-120b,
         env_result: {}, extra_flags: ''}}
generation: {temperature: 1.0, top_p: null, max_step_tokens: 8192,
             stop: ['<|return|>'], effort: high, date: '2026-08-06'}
sample: {split: [train], seeds: [42], tasks: null, n_tasks: 2, max_steps: 3,
         store_token_ids: false, pieces: 1, replicas: 1}
_stage: sample
_key: k
_upstream: {}
_versions: {}
_debug: true
_commit: deadbeef
_resolved: {}
"""

def install():
    loop.open_env = lambda name: FakeEnv()
    loop.AgentClient = FakeAgentClient
    loop.ProbeClient = FakeProbeClient

def run_dir():
    rd = pathlib.Path(tempfile.mkdtemp())
    (rd / "settings.yaml").write_text(SETTINGS)
    for kind in ("agent", "probe"):
        (rd / ("service_%s_0.json" % kind)).write_text(json.dumps(
            {"kind": kind, "replica": 0, "base_url": "http://127.0.0.1:1/v1",
             "host": "localhost", "port": 1, "pid": 0, "started_at": 0.0,
             "flags": [], "claims": {}, "attached_to": None}))
    return rd
PY
```

**D3 — a `--debug`-sized sample walk on stubs.**
```bash
"$A" - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "/tmp")
import loopfix
from data.trajectory_record import read
loopfix.install()
rd = loopfix.run_dir()
loopfix.loop.main(rd, (0, 1))
recs = sorted((rd / "records").glob("*.jsonl"))
print("records:", [p.name for p in recs])
for p in recs:
    assert read(p)["type"].to_list()[-1] == "final", p.name
hb = sorted((rd / "heartbeat").glob("*.jsonl"))
print("heartbeat:", [p.name for p in hb])
lines = hb[0].read_text().splitlines()
first, last = json.loads(lines[0]), json.loads(lines[-1])
print("first beat:", {k: first[k] for k in ("done", "total", "unit")},
      "last status:", last["status"])
pathlib.Path("/tmp/d3_run_dir.txt").write_text(str(rd))
PY
```
Expected exactly:
```
records: ['t_1__s42.jsonl', 't_2__s42.jsonl']
heartbeat: ['0-0.jsonl']
first beat: {'done': 0, 'total': 2, 'unit': 'task'} last status: done
```
one record file per requested triple, each ending in a `final` row.

**D4 — the record's own columns, read back through the format's reader.**
```bash
RD=$(cat /tmp/d3_run_dir.txt)
"$A" -c "
from data.trajectory_record import read
df = read('$RD/records/t_1__s42.jsonl')
m = df.filter(df['type']=='meta').to_dicts()[0]
assert m['split'] == 'train' and m['arm'] == 'sample' and m['stage'] == 'sample'
assert m['task_text'] and m['commit'] == 'deadbeef' and m['run_key'] == 'k'
assert m['owner_session'] == 'sample-k-0'
assert sorted(set(df['type'].to_list())) == ['env','final','gen','meta']
print('record ok')"
```
Expected: `record ok`, exit 0. The `split` value proves 2.3's triple is carried;
`arm == "sample"` is the four-values-vs-three decision; the four row kinds prove
a sample run writes no `spec` or `resume`.

**D5 — the `/health` refusal, in its three forms.**
```bash
"$A" - <<'PY'
import sys; sys.path.insert(0, "/tmp")
import loopfix
loopfix.install()
for field, value in (("render", "jinja"), ("family", "llama"), ("weights", "other-weights")):
    loopfix.HEALTH = {"render": "ids", "family": "gptoss", "weights": "gpt-oss-120b"}
    loopfix.HEALTH[field] = value
    rd = loopfix.run_dir()
    try:
        loopfix.loop.main(rd, (0, 1))
        print(field, "NO REFUSAL")
    except SystemExit as e:
        msg = str(e)
        print(field, "refused:", field in msg, value in msg,
              (("ids" if field == "render" else
                "gptoss" if field == "family" else "gpt-oss-120b") in msg))
    assert not (rd / "records").exists() or not list((rd / "records").glob("*.jsonl")), field
print("health ok")
PY
```
Expected: three lines `render refused: True True True`,
`family refused: True True True`, `weights refused: True True True`, then
`health ok`, exit 0 — each message names the field, the value seen and the value
expected, and no record file was written.

**D6 — two pieces cover the requested list and claim nothing twice.**
```bash
"$A" - <<'PY'
import hashlib, sys; sys.path.insert(0, "/tmp")
import loopfix
loopfix.install()
rd = loopfix.run_dir()
def snapshot():
    return {p.name: hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted((rd / "records").glob("*.jsonl"))}
loopfix.loop.main(rd, (0, 2))
after0 = snapshot()
loopfix.loop.main(rd, (1, 2))
after1 = snapshot()
print("after piece 0:", sorted(after0))
print("after piece 1:", sorted(after1))
print("nothing rewritten:", after0 == {k: after1[k] for k in after0})
print("heartbeats:", sorted(p.name for p in (rd / "heartbeat").glob("*.jsonl")))
PY
```
Expected:
```
after piece 0: ['t_1__s42.jsonl', 't_2__s42.jsonl']
after piece 1: ['t_1__s42.jsonl', 't_2__s42.jsonl']
nothing rewritten: True
heartbeats: ['0-0.jsonl', '1-0.jsonl']
```
exit 0. Piece 1 rotates the same two triples, finds both record files claimed,
and moves on deleting nothing (2.3's `O_EXCL` claim). Each piece's heartbeat
`total` is the **whole** requested count, 2 (8.4).

### Selfcheck lines that apply later

`run.py selfcheck` (ticket 15) will check: `agent/inject_format.py`'s `FORMATS`
keys equal `schema.AXES["inject.format"]`, and `agent/inject.py`'s `ARMS` equal
`schema.AXES["inject.arm"]`, both parsed with `ast` (A1, C1 are the stand-ins);
one column-zero integer `VERSION` in each of the four files; the four
`README.md` annotation blocks against the real import graph — in particular that
`agent/loop.py` imports `models/__init__.py` nowhere (D1) and `agent/generate.py`
names `models/probe_models/service.py` nowhere (B2); no `/home/` or `/net/` path
in code.

### GPU / main session — not yours

`M-A1` a `--debug` sample walk end to end
(`run.py train_probe ctool_qwen3_0pt6b --debug`): a vLLM piece and a render-only probe
piece up, the loop pieces writing `records/*.jsonl`, `run.py ls` reporting `done`
with 9 records, and a `meta` row whose `owner_session` matches a session name
`run.py ls` prints — the check for the one value `loop.py` and `jobs/launch.py`
must spell identically. `M-A2` a `--debug` inject walk with at least one `spec`
row; **zero `spec` rows under `arm: probe` with a low `theta` is a stop, not a
warning** — it means the live cut enumeration never fired, which is exactly the
divergence step 2 guards. `M-A3` the arm comparison at the same seed and task:
`no_probe` gives `n_inject == 0` on every `gen` row and no `spec` row, `probe`
gives at least one, and both give the same `meta.generation` text. `M-A4` the
resume account: one `resume` row per `spec` row, and `identical` true on a
majority of rows under `probe_nofill`.

## Comments

- 2026-09-17, note from the wave 3 post-merge review (main session of wave 3;
  findings BUILDER-1 and BUILDER-2 in
  `.scratch/from-zero/sdd/2026-09-17-wave3/post-merge-review.json`). The merged
  `data/build_training_dataset.py` appends `(action.strip(), env.result)` to its
  history (ticket 09 step 12, as legacy does), and it leaves a step whose action
  is the empty string out of the history and counts it as
  `events_skipped_no_action`. Step 3's clause here appends `obs.action` as it is
  and whenever it is not None. With an action that carries a trailing newline,
  or an empty code block, the live probe text and the training text differ,
  which 1.7 forbids. Not ruled by the owner; whoever dispatches this ticket
  settles which side moves and records it in the errata first.
- 2026-09-18, ruled by gyb: the live side moves. Step 3's clause above now
  appends `(obs.action.strip(), obs.observation)` and only when the stripped
  action is non-empty; the record row still stores `obs.action` unstripped, and
  `data/build_training_dataset.py` is unchanged. Measured before the ruling with
  `data/probe_input.assemble`: the history entry `('print(1+1)\n', '2\n')`
  renders `print(1+1)\n -> 2\n` and `('print(1+1)', '2\n')` renders
  `print(1+1) -> 2\n`, so the two texts differ; `AppWorld.step` returns
  `'print(1+1)\n'` for an ordinary code block and `''` for an empty one. The
  ruling is the last entry of `.scratch/from-zero/contract-errata.md`.
- 2026-09-18, wave 4 precheck (main session of wave 4, before dispatch; record
  in `.scratch/from-zero/sdd/2026-09-18-wave4/precheck.json`). Four corrections
  were made to this ticket's body, all found against the merged code: (1) the
  `p2_e2` template is `"{call} = {result}"`, legacy's spelling, which the
  `.format(call=call, result=exec_out)` rule needs (T11-2); (2) the parse
  accumulator: `out = mod.parse(delta, state)` with `state` one dict per step
  that is never rebound, in `generate.step` step 2 and `inject.step` step 2, and
  rebuilt from the new `raw` after a splice in step 9 (T11-1) — the merged
  `gptoss.parse` keeps `state["raw"]` in the dict it is handed and returns a new
  two-key dict; (3) `n_checked` counts the cuts of the step up to and including
  this one, so the first cut records 1, which is what `C4` asserts (T11-3); (4)
  the `spec` and the `resume` row carry `step=step_index` (T11-4, X-4), which
  1.1 declares on every row kind but `meta` and ticket 10's scorer joins on.
  Items (2)'s rebuild rule and (3) are in the errata under "Added by the wave-4
  precheck".
