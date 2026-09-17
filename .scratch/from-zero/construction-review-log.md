# Construction review log

What each review round found against the tickets in
`.scratch/from-zero/issues/`, the spec and the construction plan, and what was
applied or refused in response.

## Ticket review round 1

2026-09-17. Two reviewers read the eighteen tickets, the spec and the
construction plan and returned 43 findings, many of them the same defect seen
twice. Below: what was applied, then what was refused and why. Every change is in
place in the ticket, the spec, the plan or
`.scratch/from-zero/contract-errata.md`; the contracts document was not touched.

### Applied — blocking

**Ticket 08, `A5`: the temperature fixture could not pass.** `lg[arange, y] = 4.0;
lg = lg * 2.0` puts logit 8.0 on the true class of all 4,000 rows, so the mean
NLL is `log(1 + 2*exp(-8/T))`, monotonically increasing in `T`, and the minimiser
sits at the grid floor. Measured with the exact algorithm the ticket specifies:
`T = 0.0202`, and `assert 1.0 < T < 20.0` fails. The fixture is now
over-confident rather than correct — about 35% of the rows put the 8.0 logit on a
wrong class — and the analytic optimum is `8 / ln(2(1-q)/q)`. Measured on the new
fixture: `q = 0.347`, `T = 6.0359` (grid alone: `e^1.8 = 6.05`). The assertion
band `1.0 < T < 20.0` stays and now holds; the ticket names the expected value
and says a `T` at either end of the grid is a report, not something to clamp.

**Ticket 10, `A6`: the reference eval could not resolve, twice over.** It pointed
`_upstream["theta_from.eval"]` at ticket 08's `A4` fixture, which is built at
`debug=True`, while `probe_eval.run` step 6 resolves a reference with
`run_dir_of(..., debug=False)` — so the reference named a directory that never
existed. The build-key gate then reads `ref_eval_dir/meta.json`, which no stage
program writes and which `A4` did not write either. `A6` now builds its **own**
reference: a new `A6a` writes a non-debug train run (`4444dddd4444`) and a
non-debug eval run (`5555eeee5555`), runs `eval.methods.ctool` over it, and
writes the `meta.json` that `run.py` / `jobs/launch.py` would have written. Both
tickets now say in so many words that a *referenced* eval fixture is a non-debug
directory, and ticket 08's `A4` says why its own `debug=True` is right (nothing
references it). Both tickets also delete their fixture directories and list the
keys in the report.

**Ticket 14: wave 5 cannot key a `train` stage.** `C4`, `C5` and `C6` keyed
`train_probe … train`, `… eval` and the `inject` settings, and
`schema.key("train", cfg)` reads `train/utils/trainer.py` and
`train/methods/<m>.py` as source text — files ticket 13 writes in the *same*
wave, which the plan's section 1 forbids assuming. The three checks are now cut
to `baseline`'s two stages and `train_probe`'s `sample` and `build`; the full
sweeps move to ticket 15 as new `D6` (the `where` sweep, 28 paths) and `D7` (the
load-key-freeze sweep over all three workflow files), which run in wave 6. The
wave table is unchanged and the plan's section 3 now says why.

**Ticket 17: `C7` and `C12` contradicted each other.** `C12` requires the four
`ticket-run` prompts to be byte-identical to `.scratch/from-zero/prompts/*.md`,
and `implementer.md` carries the token `legacy/` on lines 9 and 50, which `C7`
scans for across every `*.md` under `.claude/`. Ticket 17 now rewrites those two
lines in the source prompt **before** copying — ticket 18 deletes `legacy/` in
the same wave, so the advice is stale anyway — and the source file is in its
"files you may touch" list and in the plan's wave table row. The instruction
greps for the token rather than naming line numbers, so it survives any further
edit to that prompt. Verified by grep on 2026-09-17: `implementer.md` is the only
one of the four prompts with a retired token, and the four `.md` files under
`.claude/` that ticket 17 does not edit (`RESUME.md`, `agents/deploy-scout.md`,
`agents/paper-verifier.md`, `skills/paper-write/references/writing-structure.md`)
carry none — stated in the ticket so the implementer does not go hunting.

**Ticket 18: the `.gitignore` "Removed" list would have unignored `envs/`.** The
stated ground was that those rules "name paths that stop existing when `legacy/`
goes". They do not: `envs/` is a **top-level sibling** of `legacy/`,
`external/appworld -> ../envs/appworld` and `external/vllm-env ->
../envs/vllm-env` point into it, and ticket 06's `models/table.yaml` sets
`LD_LIBRARY_PATH: …/envs/cuda-compat-13.0`. Checked on disk 2026-09-17: `envs/`
holds nine directories and three NFS symlinks, and `envs/alfworld/splits/` is
tracked (4 files). Every `envs/…` rule is back in the "Kept" block, spelled out;
the "Removed" list now holds only `legacy/…` rules plus rules whose directory is
absent from this machine (`ls -d` finds no `paper/`, `related_work/`,
`jacobian-lens/`, `fig1_pilot/`, `traj_pipeline/`, `benchmark_design/`,
`envs/bert_runs`, `envs/bert_data`, `*/results`), and the ticket tells the
implementer to run `ls -d` before removing any of them. `C9`'s grep drops `envs/`
and `C10` now check-ignores fourteen paths and counts the tracked `envs/` files.

**Ticket 13: `ctool.batches` had no route to the class order.** 2.6 pins
`batches(df, tok, cfg)` while `Batch["target"]` must be "class indices in
`labels` order", and neither a split frame nor `cfg` carries that order — so
recomputing it inside `batches` gives a different order from `head_labels` over
the whole frame, the exact silent mislabelling 1.3 exists to prevent. Settled:
`Batch["target"]` carries the class **name**, and `loss(probe, batch)` and
`reference_loss(probe, df)` map it through `probe.labels`, which `trainer.run`
passed into `base.load`; `validate` and `predict` read the order off
`probe.labels` too. Errata line added.

**The plan's section 1 armed the hook one wave too early.** `models/table.yaml`
is written by ticket 06 in wave 2, and the hook refuses every `Write`/`Edit` to
it; the hook matches on the path's **tail**, so ticket 04's fixture script, which
`cp`s `experimental_settings/*.yaml` into a temp tree, is refused as well. The
row now reads "after wave 2", with the reason; ticket 06's sentence claiming it
is "dispatched before that happens" is replaced by "the hook is armed after this
wave merges".

### Applied — major

**Ticket 10, `A6`'s arithmetic.** `text_pred = call if ev % 4 else <wrong call>`
is wrong when `ev % 4 == 0`; over the ten test events `ev = 10..19` that is
`ev = 12` and `ev = 16`, so two of ten joined rows are wrong and every rate is
`0.8`, not the pinned `0.75`. The expectations are now `0.8`, the prose says
which two events, and the plan's section 2.7 index says `0.8` too. The rewritten
`A6` also runs both generator methods (`cgen` and `cparam`) as one parameterised
script instead of leaving the cparam half in prose.

**Ticket 16, `gpu_state.md`'s cut point.** The sampler block runs through line
54, not 46: lines 45-48 are the "Port 8377 is already held by this resident
process" bullet and 49-54 the "restart the resident session" note. Now "delete
lines 1-55, keep 56-97", the kept block starting at
`Surveyed on: 2026-07-29 (measured, not hearsay).`, and `W1` expects **42** lines
and checks the first one.

**Ticket 16 and 17, `C7`'s exemption was dead code.** `EXEMPT = {("./…",
<first line>, <last line>)}` is a syntax error; the `./` prefix never matches
`str(p)` from `rglob`; and the two tickets unpacked the tuple differently
(`for f, lo, hi` vs `for f, (lo, hi)`). Both scripts now compute the range from
the heading text with one `section_range(path, heading)` helper, drop the `./`,
and use the same unpacking. Ticket 16 pins the heading as exactly
`## What is gone` so the lookup is deterministic.

**Ticket 12, `B4` was time-dependent and one expectation was wrong.** Every row's
`t` is now built from `time.localtime(now - …)`, so the answers do not move with
the wall clock. The deeper problem: with an empty live-session set the row's only
piece is not alive, and 2.5 drops the third clause "only while no piece of that
row has been observed `dead`" — but 8.5 makes a piece dead on `alive is False`
alone, which would drop the clause for every freshly launched run and let two
`run.py` calls a second apart both pass, the race that clause exists to prevent.
Settled by 2.5's own words ("covers a piece that has not appeared yet and not one
that has already gone"): a piece counts as observed dead only when it is not
alive **and** has emitted at least one beat. `gate_open_row` takes a fifth
argument, `beats`, which also supplies the second clause; `B4` is now six lines
covering all of it. Errata line added.

**Ticket 03, `slowed` was unreachable.** The pinned piece dict carried no rate
while `judge`'s `slowed` rule reads `recent_rate` and `avg_rate`
(`legacy/ops/verdicts.py:110-113`), so one of 8.5's six verdicts could never
print and `slow_ratio` was a dead constant. The dict now carries `avg_rate` and
`recent_rate`, computed by `ls` through `rates()`, and `A6` grew a `rates` line,
a `warming up` line and a `slowed` line — fourteen pinned lines, all six
verdicts. Errata line added.

**Ticket 09, `F2`-`F7` had no runnable commands.** Six of seven checks carried
`<fixture build dir>` placeholders and a prose description. The ticket now
carries `/tmp/mkbuildfix.sh`: a scratch copy of the code tree with its own
outputs root and its own copies of the three split files, six records written
through the real `data/task_record.py` writers, five steps apiece covering a
normal step, a null action, an api-less code block and a short-thinking step, and
a hand-written frozen `settings.yaml` for the build run. `F3` is seven named
variants of it, one command per gate; the two gates that exist to catch a
defective repo file (`build_call`'s round trip, `assemble`'s thinking prefix) are
fired by patching the **scratch copy** of `data/environments/appworld.py` and
`data/probe_input.py`, which is the only honest way to fire them.

**Ticket 06, `A11` and `A12` were not commands.** `A11`'s heredoc opened with
`# … rebuild the A10 fixture` and then used an undefined `p`; `A12` was a
paragraph with a pasted expected output. `A11` is now the tail of `A10`'s one
script (printing `forward (2, 2) 64`), and `A12` is a full heredoc that builds
the tiny Qwen3 checkpoint, substitutes `models.probe` so `load` takes the tiny
weights path, wraps with LoRA, saves, reloads and compares every backbone tensor.
Its count is of distinct **target names** (7), not instances (14 in a two-layer
model) — the old wording would have failed a correct implementation.

**Ticket 07, `A13` and `A15` were not commands.** `A13` backgrounded the server
and then said `# wait for … to appear`; it now polls for
`service_probe_0.json` for 60 s, prints the log and gives up if it never lands,
and kills by recorded pid instead of `%1`, which a non-interactive bash has no
job control for. `A15`'s stub server is written out in full: a
`ThreadingHTTPServer` on port 0 that records the POSTed body and replies with two
SSE chunks in the shape `live_appworld.py:210-227` parses, plus `[DONE]`; both
request bodies are printed, and the expected block is exact.

**Ticket 11, four checks were not runnable and one asked for an illegal file.**
`C5` is written out in full (C4's fixture, a raising `FakeProbe`, both control
arms, a fresh run directory each). `D3`, `D5` and `D6` share a new
`/tmp/loopfix.py` that substitutes `agent.loop.open_env`, `agent.loop.AgentClient`
and `agent.loop.ProbeClient` — **no stub environment file**, which would be
outside the fixed tree and would move `schema.AXES["data.env"]`. Section 4 now
pins those three as module-level names, which is what makes the substitution
legal. `D4` reads the run directory `D3` wrote to `/tmp/d3_run_dir.txt`.

**Ticket 15, check 2 could not be green and `D4` fought the hook.** The three
normalisation rules are now stated: `imports_of` joins `module.name` for an
`ImportFrom` only when the join is a repo file; `readme_entries` strips the
bracketed third-party list and every parenthetical; and an entry ending
`(by name)` or reading `none (program)` takes its own test instead of the graph
equality. `D2`'s pinned `['data.example', 'os']` now has a stated reason and a
second fixture line (`from dataclasses import dataclass -> ['dataclasses',
'os']`). `D4`'s breakage 8 moved to the unprotected side of the same check
(delete an alias from `constants/path_models.yaml`) and breakage 11 uses `touch`,
which the hook's Bash rule does not block and which is all check 11 needs; the
ticket states that the hook matches on the path tail, so a temp copy does not
escape it.

**Ticket 13, `A3.4`'s stub `Probe` had no `labels`.** `validate` and `predict`
reach the class order only through `probe.labels`, so the script raised
`AttributeError` before its first expected line. Both stub `Probe` classes
(`A3.3` and `A3.4`) now carry `labels` and `probe_kind`.

**Ticket 04, `M-G3` would have overwritten the owner's setting files.** `C3`,
`C4` and `C5` write mutated YAML into `$FIX/experimental_settings/*.yaml`;
rerunning them with `S.ROOT` at the repo root re-dumps the owner's files. `M-G3`
is now restricted to `B4`, `C1`, `C2` and `D1`-`D5`, and the ticket says `C3`,
`C4` and `C5` run against a `$FIX` copy always. Same edit in the plan's 2.1.

**Ticket 14, `D2` expected 34 files in a worktree that holds 30.** It now expects
`30`, names the arithmetic, says `README.md` still carries all 34 entries (`D1`
counts them), and forbids the two wrong fixes — dropping a `train/` line or
adding `train` to the `find` list. The 34-file check stays ticket 15's `D3` and
ticket 18's `C6`.

**`.claude/skills/repo-review/SKILL.md` had no ticket.** The tree's Part 1 and
contracts 0.2 both name it and `.scratch/review/issues/`, and none of the
eighteen tickets wrote it, so the build would have ended with the fixed tree
incomplete and no check noticing. It is now ticket 16's third file, with a
five-point brief drawn from the tree's own one line, and a new `W2` that proves
the file exists and names its output directory. The plan's 2.9 table and the wave
table row list it.

### Applied — minor

- **24 -> 34 api-less actions**, corrected in ticket 09 step 12, ticket 05's `B4`
  note, the plan's section 5 item 2 and section 6 item 2, and the errata line.
  Re-measured today over all 315 p1 trajectories with the legacy `AW_CALL` +
  paren-walk rule: **4,074 non-null actions, 24 with no `apis.<app>.<api>(` match
  (13 trajectories), 10 whose call never closes (9 trajectories), 34 in all
  (0.83%) across 22 trajectories, 4,040 parsed.** Ticket 05's `4074 4040 4040`
  was right all along; the 24 was the wrong half of the number.
- **Ticket 04**: a new Behaviour bullet says `load` resolves
  `generation.{stop, effort, date}` onto the `Setting` from the family module,
  and why `probe.lora_targets` is the deliberate exception (every stage program
  reads the first three off the frozen file; none reads the fourth). Errata line
  added.
- **Ticket 13**: the continue-rule table's `train_log.jsonl` row now says the
  message names `run.py retry`, which is what `A3.5` case (c) asserts.
- **Ticket 11**: `FORMATS['note']`'s template spelled `{result}`, matching the
  legacy template, the prose and `A3` (the table said `{exec_out}`, which would
  `KeyError`); step 6 writes `token_boundary(bounds, pos)[1]` and
  `find_head(..., lambda ids: clients.probe.decode(ids)["text"])`;
  `token_boundary`, `find_head` and `ensure_health` are in the file's names
  block; the `/health` refusal is pinned as a module-level `ensure_health` that
  `agent/loop.py` calls once, never inside `step`, and `C4`/`C5`'s stubs carry a
  `health()` anyway.
- **Ticket 10**: `A8`'s `meta` row no longer passes `record_id`, matching ticket
  02's `D1`; ticket 02 now states that passing any of the four stamped columns
  (`type`, `ts`, `version`, `record_id`) raises, with a check in `D1`. Errata
  line added.
- **Ticket 03**: `ls` calls `live_sessions()` only over a non-empty folded row
  set, so `run.py ls` and `method_table.table()` issue no `ssh` against an empty
  ledger; a new `A10` proves it by making `live_sessions` raise. Ticket 14's `C3`
  and ticket 10's `A9` say the no-ssh path is itself the check. Errata line
  added.
- **Spec section 5** gains "no citation of `legacy/` in the shipped source": the
  citation lives in the ticket and the report, because `legacy/` is deleted and
  ticket 18's `C9` greps for the word. The same line is in
  `.scratch/from-zero/prompts/implementer.md`, which every implementer reads.
- **Ticket 17**: the `exp-status` line-number list is now explicitly a map, not
  the rule — every occurrence of `TIMELINE.md`, `RESULTS.md`, `runs.jsonl`,
  `jobs.json`, `WORKPLAN.md`, `DATA.md` and `plans/` takes its new path, lines
  235 and 248 named as the two the list missed, and a new `C15` greps for any
  bare spelling that survives.
- **Plan section 2**: the index now names the owning ticket beside each
  identifier, because identifiers are unique inside a ticket and not across the
  eighteen. `F7` added to 2.2; `A6a` and the `0.8` correction in 2.7; ticket 16's
  `C9`/`C10` renamed `W3`/`W4` so they stop clashing with ticket 18's; 2.9
  rewritten as one line per real check with its ticket; 2.7's ghost `A10` replaced
  by a pointer to the two tickets' "Selfcheck lines that apply later" sections.
- **Plan section 5** now counts 123 errata entries and names the six added by
  this review.

### Refused

**"Move ticket 14 to wave 6, with 15 following in wave 7."** The finding offered
this and a split as alternatives; the split is what was applied. Moving 14 alone
pushes 15 and 16 to wave 7 and 17 and 18 to wave 8, serializing four waves for a
dependency that exists only in the acceptance — `run.py` itself imports nothing
from `train/`. The second reviewer said the same ("do not re-order the waves").
The restriction is written into ticket 14, and the two dropped sweeps are ticket
15's `D6` and `D7`, so nothing is lost, only deferred by one wave.

**"Plan 2.4's `A16` has no matching command in the tickets."** Misreading.
`A16` is defined twice on purpose, once in ticket 06 over its seven files and
once in ticket 07 over its two — both are real commands with real expected
output. The plan's line now says so rather than being deleted. (Plan 2.7's `A10`
*is* a ghost and was replaced.)

**"Drop `legacy/` from `C7`'s RETIRED list, or exempt
`.claude/skills/ticket-run/prompts/`."** Refused. `legacy/` is the token that
matters most after ticket 18 deletes the directory — a document still telling an
agent to read `legacy/` is exactly the failure `C7` exists to catch — and an
exemption for a whole directory is the "loosening the token list" the ticket
already forbids for the gpu-run skill. Rewriting the two stale prompt lines costs
two sentences and leaves the check sharp.

**"State explicitly that `slowed` is dropped with the sampler, and remove
`slow_ratio` from `DEFAULTS`."** Refused in favour of the other option the same
finding offered. `slowed` is one of the six verdicts CONTEXT defines and 8.5
pins in priority order, and `run.py ls` is the only monitoring surface left;
dropping a verdict to avoid two dictionary keys is a worse trade than computing
two rates `ls` already has the beat files for.

**"Give `D4`'s breakage 8 a command that gets past the hook."** Half refused.
Breakage 11 does use `touch`, which the hook's Bash verb list does not cover and
which is all that check needs. Breakage 8 is not worth teaching an implementer to
slip past the hook: the check is "every `models/table.yaml` row's
`result.weights` is a key of `constants/path_models.yaml`", and deleting the
alias from the unprotected side fires exactly the same check. The ticket says
plainly that no breakage in the list needs a way around the hook.

**"Use 20 test events so exactly a quarter is wrong and `0.75` holds."** Refused
in favour of the same finding's first option. The pinned `n: 10` also ties `A6`
to the reference report's ten test fires, which is the join this check is really
about; changing the fixture size to preserve a round number would have moved that
too. The expectation is `0.8`, with the arithmetic written out.

**"`gate_open_row` should return `None` for a young row whose only piece has no
live session."** Half refused. That reading follows 8.5's `dead` rule literally,
and it breaks 2.5's stated purpose for the same clause and the `M-J8` scenario:
at the moment a second `run.py` takes the lock there is a start row, no live
session and no heartbeat, and under that reading the second caller passes the
gate and launches a second set of pieces into the directory the first is using.
The rule applied instead is 2.5's own sentence — the timeout "covers a piece that
has not appeared yet and not one that has already gone" — with a first beat as
what tells the two apart. `B4` now pins both cases side by side, lines 2 and 3.

---

## Ticket review round 2

2026-09-17, after round 1's fixes landed. Twenty findings came back, three of
them the same defect seen twice (the `agent/inject.py` stubs, ticket 14's `C5`).
**All twenty were applied**; two were applied with their arithmetic or their
scope corrected, and those two corrections are written out below. The contracts
document was not edited; eight lines went into
`.scratch/from-zero/contract-errata.md` under `planner: reviewer round 2`,
taking the errata list from 123 entries to 131.

### Applied — blocking

**Ticket 11, `C4` and `C5`: the stub decoder was not the inverse of the stub
stream, so the whole `inject.step` acceptance was unreachable.** `find_head` is
ported verbatim from `live_appworld.py:340-376`: it advances an id prefix until
the decoded text covers the cut, backs off to the shortest that still does, and
raises when the decoded head does not match the streamed text character for
character. The old stubs streamed `[1,2]` for a 49-character chunk and decoded
ids as `"abcdefg"[i % 7]`, so the fire path raised before a single `spec` row was
written and every assertion after `res = inj.step(...)` was dead. `C3` in the
same ticket asserts that raise fires, so no implementation could satisfy both.
Both stubs now carry one id per character — `IDS(s) = [ord(c) for c in s]` and
`decode(ids) = "".join(chr(i) for i in ids)` — which makes the decoder an exact
inverse and every derived number computable by hand.

**The two findings disagreed on the arithmetic and one of them was wrong.** The
first put the cut at 17 and `pos` at 47; the second put `pos` at 48. Recomputed
from `data/probe_input.SENT_RE` and `token_boundary`, and measured:
`len(chunk) = 49`, `len(reasoning) = 19`, `ts = 30`; `cuts_live` returns
`m.start()`, which is the whitespace **after** the full stop, so `cut = 18` (not
17, which is the full stop itself — that offset is `cuts`'s `m.end()`
convention, and the two coordinates differing is exactly what ticket 02's `C1`
pins); `pos = 48`; `k = 48`; `head_chars = 18`; `overflow_ids = [32]`;
`discarded_chars = 1`. `C4` now pins those instead of `<k>`, and the ticket
carries the table that derives them. The expected line is `inject step ok 1 48 2`.

**The `note` assertion was wrong for a second reason.** `spec["note"].startswith(
"[Prefetch: ")` contradicts step 7's own `p1` seam rule: the head ends in `.`,
which is not whitespace, so the note is `"\n" + body`. `C4` now compares against
`FORMATS["p1_e1"].render(...)` with the seam spelled out. `C5` takes the same
stub and one extra assertion, `head_tok == 48`, because the `probe_nofill` arm
reaches `find_head` by the same path.

**Two gaps the stub fix exposed, both closed in the ticket and the errata.**
`bounds` had no stated initial value while step 6 subscripts
`token_boundary(bounds, pos)`, which returns `None` when no boundary is at or
before `pos` — a fire inside the first chunk would raise on a `None` subscript.
It now starts `[(0, 0)]`, verbatim from `live_appworld.py:433`. And
`agent/loop.main`'s `piece` had two incompatible readings: the prose rotated with
`triples[piece:]` and beat with `registry.beat(run_dir, piece)`, both needing an
integer, while the D-fixture passes `(0, 1)`. The signature block now says
`piece` is the `(i, n)` pair, and the rotation, the heartbeat and
`meta.owner_session` all name `i`.

**Ticket 02, `REQUIRED`: four columns in it are absent from a legitimate record —
and, on inspection, eleven are.** The finding is right that `step`, `reasoning`,
`content` and `result` are all-null in a record that aborts before its first
`gen` row (a 400 on step 0, or any other exception through the `task_error`
guard), that an all-null column reads as **absent** per the round-1 errata, and
that `is_done` is true for such a file so `data/build_dataset.read_dir` reads it
and raises before the abort-share gate can run.

**The proposed replacement set was still wrong, and the same ticket proves it.**
It kept `steps`, `completed`, `judge`, `success`, `tokens_in`, `tokens_out` and
`wall_s`, every one of which lives on the `final` row — and `D2` writes a `meta`
row and a `gen` row, drops the writer without closing it, and asserts
`tr.read(p).height == 2`. A killed writer's file has no `final` row at all, so
those seven are absent there and `read` would raise on the check that exists to
prove the flush rule. `REQUIRED` is therefore the twelve columns every record
file carries, which are exactly the `meta`-row columns the loop always writes:
`{type, ts, version, record_id, stage, env, task_id, seed, split, task_text,
agent_model, owner_session}`. The ticket now carries the rule ("a name may be in
`REQUIRED` only when every record file `read` must accept carries at least one
non-null value for it") and a table giving, per exclusion, the valid file that
would otherwise be refused. `D1` gained the two-row `meta`+`final` abort case the
finding asked for.

**One consequence, closed in ticket 11.** The twelve hold only if every record
file starts with a `meta` row and every `final` row is complete, so the per-task
guard now writes the `meta` row first when it fires before the normal one did
(an exception out of `env.open` would otherwise leave a `final`-only file that
`read` cannot attribute), and writes every column of 1.1's `final` block whatever
the abort — `completed=False`, `steps`, and the token and wall accumulators.

### Applied — major

**Ticket 09, `F3`: the seven gate variants could not fail.** `( … | tail -3 )`
followed by `echo "exit=${PIPESTATUS[0]}"` reads the **subshell's** status, which
is `tail`'s, which is always 0. Measured here: `( false | tail -3 ); echo
"exit=${PIPESTATUS[0]}"` prints `exit=0`. Every variant reported a pass, a
missing gate included. The loop now redirects the builder's output to a file
inside the subshell and reads `$?` directly, with the measurement written into
the ticket so nobody restores the pipeline form.

**Tickets 16 and 17, `C8`: the check fails on text the same ticket orders
written.** Section 1 requires the gpu-run skill to carry a `## What is gone` list
naming `run.py gpu-jobs …`, `run.py record …`, `run.py launch`, `run.py runmeta`
and `python3 run.py sampler`; `C8`'s regex collects all five and none is in
`run.py --help`. `C7` already had a heading-located exemption and `C8` did not.
Both `C8` scripts now reuse `section_range(GONE, "## What is gone")` and scan
line by line, skipping that range — the same `str(p) == f` comparison with no
`./` prefix and the same `for f, lo, hi in EXEMPT` unpacking `C7` uses, so
ticket 16's and ticket 17's copies stay interchangeable.

**Ticket 14, `C5`: an acceptance command renamed the shared NFS outputs root.**
It was the only command in the eighteen tickets that wrote to the real root
rather than a temp one, it ran with `set -e` still in force from `C4`, and a
non-zero exit from the `run.py where` in between — the exact failure `C5` exists
to detect — would have left the root named `<root>.hidden` for every wave and
every debug walk downstream. `C5` now copies the tree to `mktemp -d`, repoints
that copy's `constants/path_outputs.yaml` `root` at a path that does not exist,
and compares the 12-hex last segment of `run.py where` inside and outside the
copy. It also asserts the nonexistent root stays absent, which proves `where`
prints a path rather than creating one, and it opens with `set +e`.

**Ticket 12, `B7`: the one check of the refire liveness gate needed an `ssh` an
implementer is forbidden to run.** Ticket 03 pinned `session_alive` as one
`ssh -o BatchMode=yes` per host with no local case, so `B7`'s local tmux session
was probed over `ssh` to this machine, and a refused or timed-out `ssh` returns
**alive** fail-closed — the check would have passed for the wrong reason.
`legacy/ops/launch_common.py:41-67` already has the short-circuit (`bash -c` when
the host equals `local_host()`, for the session test and the tmux launch alike).
Ticket 03's `live_sessions` / `session_alive` bullet now carries it, with both
sides normalised through the `hosts:` `alias` column, and it is an erratum
against 8.0/3.4. `B7` now runs with a shim `ssh` on `PATH` that touches a marker
and exits 255, and asserts the marker does not exist — so "no ssh was issued" is
proved, not assumed.

### Applied — minor

- **Ticket 12, `B3`** dirtied the real `jobs/RESULTS.md`, which spec section 9
  forbids outright, and left the worktree dirty between two statements. The
  exemption is now a pure test: `jobs/launch.py` offers `is_ledger_path(path)`
  (pinned in the ticket's module-internal list and recorded as an erratum against
  2.5) and `B3` runs it over a fabricated path list. The refusal half runs
  against the worktree as it stands, which in an implementer's worktree is dirty
  by construction; the fallback dirties `README.md`, this ticket's own file,
  never a ledger.
- **Three `grep -c` checks expected `0` and therefore exited 1** — ticket 02's
  `A3`, ticket 11's `A5`, ticket 12's `B8` — so a correct implementation looked
  like a failed command under spec section 7. All three are now
  `test "$(grep -c …)" = 0 && echo <TOKEN>`, each with the reason written beside
  it.
- **Ticket 16, `W1`** required `.claude/skills/probe-pipeline/references` to be
  gone while the file list named only the four `.md` files inside it. The list
  now says "(and the empty references/ dir once these four files are gone)",
  matching the wording already used for `gpu-run/scripts/`.
- **Ticket 17, section 4** said `legacy/` appears on two lines of
  `.scratch/from-zero/prompts/implementer.md`. Grepped today it is on three: 9,
  50 and **52**. The count is replaced by the grep instruction, the three hits
  are named, and line 52 gets its replacement text — without it `C7`, which
  ticket 17 runs over all of `.claude/`, fails on a file ticket 17 just
  installed, while `C12` forbids fixing it in the copy.
- **`docs/` never moved.** The fixed tree's `notes/` line says notes holds
  "plans/ and docs/ (moved whole)" and contracts 0.2's tree lists no root-level
  `docs/`, but no ticket performed the move, so ticket 16's repo-review skill and
  ticket 17's `CLAUDE.md` both cited `docs/agents/issue-tracker.md` at a path the
  tree says should be `notes/docs/...`. Of the finding's two options the move is
  the one the owner's tree asks for: ticket 18 gains a section 0
  (`git mv docs notes/docs`, a rename with no file inside it opened) and a `C16`,
  the plan's wave table and section 2.9 name it, and tickets 16 and 17 both cite
  `notes/docs/agents/issue-tracker.md` and `notes/docs/agents/triage-labels.md`.
  Recorded as an erratum against 0.2. Spec section 9 now says ticket 18 makes
  that move, so the "`notes/` is the owner's" rule is not read as forbidding it.
- **Ticket 14's `--help` layout is now pinned** — one subcommand per line,
  indented exactly two spaces, name first — because tickets 16 and 17 both
  recover the existing subcommand set with `^\s{2,}([a-z][a-z0-9_-]*)` over the
  rendered help and would otherwise fail for something ticket 14 did. Pinned in
  section 1, repeated in `C1`'s expectation, named in both `C8`s, and recorded as
  an erratum against 8.6.
- **Ticket 14, `C6`**: the prose said `schema.load` must succeed "for every
  setting of all three files" while `CASES` walks two. It now names the two and
  says why the third cannot be loaded in wave 5 — an inject setting's references
  resolve to key chains that read `train/`'s `VERSION` lines — and points at
  ticket 15's `D7` for the unrestricted sweep.
- **The wave-5 `README.md` merge would have shipped four duplicate entries.**
  Ticket 13 adds four `train/*.py` blocks; ticket 14, in the same wave, rewrites
  `README.md` whole and already carries them. "Keep every ticket's lines" now
  applies to waves 1-4 only; at the wave-5 merge ticket 14's file is taken
  wholesale and ticket 13's four blocks discarded. Stated in the plan's section 1
  and in ticket 13, which also tells the implementer to spell the four blocks
  exactly as contracts 0.2 does so the discard is provably safe.
- **Spec section 9** said ticket 01 is the one ticket that writes both protected
  files. Ticket 06 writes `models/table.yaml`, which is why the hook is armed
  after wave 2 and not after wave 1. The sentence is split, and the note about
  the tail match and the directory-not-glob copy is kept with it.
- **Ticket 15, `D4` breakage 11** had no undo: the hook blocks
  `rm <scratch>/experimental_settings/free.yaml`. The table entry now says to
  delete the whole scratch copy (`rm -rf "$S"`, which names no protected tail)
  and re-copy. The plan's `M-G3` gained the matching parenthesis: `/tmp/mkfix.sh`
  is re-created with the **Write tool**, because its body carries
  `cp experimental_settings/*.yaml` and a Bash heredoc naming that text is
  refused.
- **The plan's section 2 index missed six identifiers and misnamed one.** Added:
  ticket 09's `A1` and `A3` (2.2's lines now say which ticket each belongs to),
  ticket 05's `C3`, ticket 03's `A9` and `A10`, ticket 12's `B8`, ticket 15's
  `D5`. 2.7's `A7` is now `A7a` (ticket 08) / `A7` (ticket 10). Ticket 15's files
  column gained `README.md (only when a line is wrong)`. **No wave changed**:
  ticket 16 touches no `README.md`, so wave 6 still has no shared file.

### Refused

Nothing was refused. Two findings were applied with a correction, both recorded
above: the `agent/inject.py` stub arithmetic (`cut = 18`, `pos = 48`, not 17/47),
and ticket 02's `REQUIRED`, whose proposed replacement set still broke the same
ticket's `D2`.

### What was not touched

`notes/plans/2026-09-17-contracts.md`. Every disagreement above is an errata
line, eight of them, appended under `planner: reviewer round 2`.
