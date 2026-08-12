# research-loop plugin — design spec

**Status:** needs-triage
**Date:** 2026-08-13 (finalized via brainstorming; five revision rounds the same day:
four layer-isolated audits → rev 1, two acceptance audits (coverage check + five-scenario
replay) → rev 2, recheck of ten defects → rev 3, final check of eight defects → rev 4,
recheck of five defects → rev 5. Full trail in `audit-merge.md`.)
**Form:** machine-level plugin (travels with the machine); project rails hook in
through a config file at the repo root.
**Language note:** this file is the English rendition of `spec.md` (Chinese, authoritative
design draft). The plugin itself — SKILL.md files, schema field docs, script messages —
is written in English per user instruction (2026-08-13).

## 0 One sentence

Turn the research loop (talk ideas → set principles → set engineering goals → build →
run experiments → story rulings → writing) into a layered plugin: three layers do the
work, four channels carry the communication, criterion gates guard the claims,
structured ledgers keep the memory, and one independent oversight plane lets the user
personally verify every detail.

## 1 Three layers + the oversight plane

Layers are cut by **command authority**. Each layer minds only its own business;
across layers, only files on the channels count.

| Layer | Does what | Ledger write authority (complete list, 1:1 with §7 owners) |
|---|---|---|
| idea layer | talk ideas, set principles, rule on what enters the story, approve computations | principles doc, story ledger, TIMELINE, literature ledger (KNOWLEDGE_MAP) |
| deploy layer | principles → spec → code → launch experiments → collect numbers | spec, tickets, decisions ledger, launch orders, batch reports, error classification table, schema directory (incl. runs schema), code map, dataset inventory (DATA.md) |
| run layer | mechanical execution: run commands, drop logs, pin versions | runs.jsonl normal rows (written against the deploy-layer-defined schema; criterion reduced rows belong to the deploy layer, §5), job ledger, RUNMETA, raw outputs, cluster slow-variables file |

- Write authority names **which layer the ledger content belongs to**, not which script
  entry point writes it: every ledger is written through registry scripts (R7), any
  layer's session may run the scripts, and the scripts enforce schema validation.
  A user's authorization can therefore be recorded into the decisions ledger on the
  spot from an idea-layer session (the audit-D7 definitional clarification).
- **Single-layer exclusivity has three written exceptions**: the blocked ledger
  (per-transition write authority; who may flip which state is fixed in §5), the
  feedback ledger (append-only co-writing; entries carry a layer field), and
  runs.jsonl (split by row type: normal rows belong to the run layer via the project
  bookkeeping script, criterion reduced rows belong to the deploy layer via
  `ledger.py runs-append`, §5). Apart from these three, one ledger, one layer.
- The **oversight plane** is not a layer: it sits outside the command chain, commands
  no one, reads everything (all ledgers + code + raw outputs), and has zero write
  authority over any layer's ledgers. It touches disk in exactly two ways — its
  dedicated report area `reports/`, and, as a participant under the first two written
  exceptions above, the shared ledgers (opening questions in the blocked ledger,
  appending suggestions to the feedback ledger). Its only product is evidence reports
  for the user. Oversight must run in an independent context; the session that did
  the work may never audit itself.
- **Interpretation never crosses layers**: only facts travel upward; all interpretation
  happens in the idea layer and is ruled on by the user. Derived-quantity computation
  (means, ratios, …) is an idea-layer activity: propose, approve, compute, and attach
  the command — all in the idea layer (R4); the deploy layer only runs pre-existing
  mechanical aggregation pipelines and invents no new math.

## 2 Channels

| # | Direction | Genre | Rules |
|---|---|---|---|
| 1 | idea → deploy | principles doc + spec | every spec item points back to a principle_id; if it can't, the principles are incomplete — go back to the idea layer first |
| 2 | deploy → idea | numbers ledger, batch reports, blocked entries | reports carry zero interpretation; on a principle gap or a code decision point, stop and open a blocked entry |
| 3 | deploy → run | registry commands, **launch orders**, tickets | nothing runs unless it's in the registry; **a dirty tree always refuses launch and escalates to the deploy layer** (exemption globs in config); artifacts pinned with RUNMETA |
| 4 | run → deploy | logs, RUNMETA, job ledger, sampler verdicts (into the job ledger), blocked entries (fault escalation) | escalation must carry evidence: verbatim error, log paths, table of attempted actions |

**Blocked ledger `blocked.jsonl`** (the bidirectional genre spanning channels 2/4;
schema and transition rules in §5).
**Two mandatory reads at session start** (hard-coded in every layer's SKILL.md skeleton):
① this layer's pending queue (open entries with to_layer = this layer, plus answered
entries with from_layer = this layer — both count as unresolved);
② the active-grants view (decisions ledger entries with kind=grant, unexpired,
unrevoked).

Global rules: **the traceability chain runs both ways** (forward: ticket → spec →
principle item; backward: run → launch order → ticket, via RUNMETA.launch_order_ref
and job-ledger backrefs; decision → run via launch-order decision_refs);
**escalation climbs the stairs, never skips a layer**; **all communication lands on
disk, never in session memory**; **every ledger is readable by every layer; write
authority is single-layer exclusive** (except the three written exceptions of §1).

### 2.5 Where the human sits (top of the idea layer)

The user is the top of the idea layer, the endpoint of all judgment. Between the human
and the system there are also only fixed genres:

**Downward (you → system), five kinds:**
- **Ruling**: finalizing principles, approving specs, story rulings, **answering blocked
  entries** — recorded into the corresponding ledger with a date; blocked answers are
  transcribed by the session at hand (answered_by = user);
- **Authorization**: R4 computation approval, R6 self-decision grants — your literal
  words recorded on the spot into the decisions ledger (kind=grant, with structured
  scope and expiry);
- **Revocation/correction**: any recorded ruling can be withdrawn — entry status change
  + `superseded_by` (script-transcribed); the corresponding principles-doc item gets
  the 【revoked】 tag;
- **Trigger**: any sentence in the routing table (§6);
- **Send-back**: acceptance failed, return to the responsible layer for redo; the
  reason lands in the batch report.

**Upward (system → you), six kinds:**
- **Proposals**: computation proposals (R4), option choices (R5) — anything that needs
  your ruling must arrive as "proposal + evidence", never as a fait accompli;
- **Evidence reports**: the R3 genre (oversight reports, observation reports, and
  criterion acceptance reports are all its subtypes);
- **Spot-check lists**: fixed-seed samples with direct paths + a population fingerprint;
- **Pending queue**: the rendered view of blocked.jsonl — the first thing you look at
  when you return;
- **Regression alerts**: the list produced when new batch numbers conflict with active
  story claims (facts only, no verdicts);
- **Numbers ledger**: batch reports + the RESULTS rendering.

**When you are absent**: only self-decisions inside an active grant (kind=grant, scope
covers, unexpired) may proceed (with R6 traces); everything else stops as an open
blocked entry. No "do it first, ask later."

## 3 Ten hard rules (plugin-wide)

- **R1 The principle triple**: every principle = `principle_id` + `scope` + a
  one-sentence principle + a criterion (`criterion_cmd`, must be a registry command)
  + latest measurement. **The latest measurement is never hand-filled**: every
  criterion execution is a run, entering runs.jsonl with its principle_id; the
  "latest measurement + date" in the principles doc is back-filled by the rendering
  script. The principles doc carries a revision number.
  **Criteria must be lightweight and read-only** (no GPU; runnable on the spot by a
  deploy-layer session); evidence that needs heavy compute is first produced by a
  normal run, and criterion_cmd checks the artifact paths.
  A principle whose lightweight criterion cannot be written goes back to the idea
  layer for renegotiation.
- **R2 Machine checks, human judges**: criteria run by machine, verdicts come from
  the human. In acceptance, the AI does exactly two things: run the checks, and lay
  the raw evidence in front of the user.
- **R3 The evidence genre**: criterion/oversight/observation output may only contain —
  counts, difference localization (the diverging originals side by side, **each side
  with path + line number**), and openable file paths (with line/record numbers).
  **Every number must come with a paste-and-run reproduction command** whose output
  equals the reported number. A zero-count negative claim must attach the full scan
  scope list and total line count. Report headers carry a provenance block: generation
  time, git HEAD, line counts/hashes of ledgers read.
  Verdict words like "passed / fine / as expected" are banned. Double gate:
  lint + mechanical verifier (§4).
- **R4 Computation authorization**: data may only be presented faithfully as raw
  values. Any derived quantity is proposed first — formula, denominator, filter
  conditions, files acted on — computed only after the user approves, and the command
  is attached beside the result (story-ledger entries record derivation_command).
- **R5 Decision points come to the table**: when construction hits an option fork,
  stop, write a blocked entry, await ruling. Mechanical three-question test (any yes
  = stop): does it change any criterion's output? does it introduce a new constraint
  with no principles-doc item? is it irreversible (GPU hours / NFS writes / artifacts
  consumed downstream)? Only three no's is construction freedom. **A ledger schema
  change always counts as yes on question two** — always on the table.
  After the ruling: ledger.py **synchronously generates a decisions-ledger entry**
  from the answered R5 item (chosen holds a grep-able concrete value) — this is the
  mandatory intake for the decisions ledger; a free-text answer alone is not allowed.
- **R6 Authorized self-decisions leave traces**: self-decision is allowed only under
  an active grant (scope covers the fork at hand, unexpired); every self-decision
  point writes to the decisions ledger (decided_by=agent, authorized_by pointing back
  to the grant entry).
- **R7 Deterministic things get scripts**: ledger writes, schema validation, trace
  checks, sampling, lint, rendering — all done by scripts; the LLM only does work that
  needs judgment. Rendered artifacts are never hand-edited.
  **Numbers enter runs.jsonl through exactly two registry-script paths**: normal
  experiments via the launch order's `metrics_cmd`, criterion runs via
  `criterion_cmd`'s structured output — **no layer may fill numbers by eyeballing
  logs**. (Derived quantities never enter runs.jsonl; they go through R4 to the
  story ledger.)
- **R8 Self-heal first, escalate second**: failures are first handled within the
  layer's own duties and write authority per the **error classification table**
  (three feature kinds: exit code, output_check verdict, log regex; a hit yields a
  self-heal action or an escalation instruction — the script decides, no LLM);
  resolved leaves a trace; unresolved writes a blocked entry one layer up
  (run → deploy → idea → you), with evidence. No layer-skipping, no silent
  swallowing, no cross-layer fixes. "Re-ran once, output still empty" always
  escalates.
- **R9 Skill evolution lands in the ledger**: at the close of each loop, every layer
  writes "where the skill chafed, how to change it" into the feedback ledger.
  Suggestions never take effect automatically: the user reviews periodically (routing
  sentence "review the feedback"); approved ones change the skill body (into git),
  rejected ones record the reason — reviews land as appended review rows (§5, the
  ledger is pure append) and may only be written by the user's review session via
  the script.
- **R10 Skill bodies load on demand**: SKILL.md holds only the skeleton (duties,
  channels, ledger write authority, mandatory reads, phase index); per-phase
  operating detail is split into `references/<phase>.md`, read only when that phase
  begins. Feedback methodology used only at close-out loads only in the close-out
  section. Context isolation cuts across time, not just layers.

## 4 Component structure (one dedicated piece per layer)

```
research-loop/                      # plugin root
├── .claude-plugin/plugin.json
├── skills/
│   ├── research-loop/SKILL.md      # thin routing shell: recognize phase → hand to layer; holds the routing table (§6)
│   ├── idea-layer/SKILL.md         # idea-talk procedure, principle template, story rulings, R4, revocation genre
│   ├── deploy-layer/SKILL.md       # spec genre, ticketing, R5/R6, criterion acceptance, launch orders
│   ├── run-layer/SKILL.md          # run-layer contract: launch-order execution, error classification, artifact checks
│   └── oversight/SKILL.md          # oversight plane: report genre, independence discipline, spot-check flow
│   (each skill dir carries references/<phase>.md, loaded per phase per R10)
├── agents/
│   └── inspector.md                # read-only inspector: writes only reports/, R3 genre
│                                   #   (the oversight plane's two shared-ledger slots
│                                   #    belong to the oversight session, not this agent);
│                                   # frontmatter pins model: opus (dispatch must name a model)
├── schemas/                        # JSON Schemas for five ledgers + launch order (plugin ships
│                                   # defaults, project may override; changes go through R5 +
│                                   # schema_version bump)
└── scripts/                        # all deterministic, grouped by owning layer
    ├── ledger.py                   # ledger front door: story/decisions(incl. grant)/blocked/feedback
    │                               #   writes + schema validation + state machine + per-transition
    │                               #   write-authority checks + rendering
    │                               #   (rendering incl.: pending-queue view, active-grants view,
    │                               #    principles-doc "latest measurement" back-fill, ledger→md);
    │                               #   plus three cross-ledger duties: launch-order writes (same
    │                               #   action back-fills affects, §5), criterion reduced-row
    │                               #   intake (runs-append, §5), init (generate research-loop.json
    │                               #   skeleton from template)
    ├── trace_check.py              # (deploy) traceability: spec→principle_id, ticket→spec,
    │                               #   backward run→launch order→ticket, decision→run (scans
    │                               #   launch-order decision_refs + decisions-ledger affects)
    ├── output_check.py             # (run) artifact checks: expected_outputs item by item
    ├── error_classify.py           # (run) error classification: table-driven self-heal/escalate,
    │                               #   fed the three feature kinds
    ├── spotcheck.py                # (oversight) fixed-seed sampling: direct-path list + population fingerprint
    ├── evidence_lint.py            # (oversight) banned verdict words + "number without repro command"
    ├── verify_report.py            # (oversight) mechanical verifier: path stat, verbatim excerpt
    │                               #   re-comparison, repro-command value re-comparison
    └── regression_check.py         # (oversight) regression contrast: new batch vs active story
                                    #   claims, same-basis recompare; conflict list lands in
                                    #   reports/ (consumed by the idea layer)
```
runs.jsonl has exactly two write entry points, split by row type: **normal experiment
rows** go through the project-side bookkeeping script (new1: record.py loading
runs.schema.json for validation; the plugin only ships the schema and validation
functions — it does not replace this entry point); **criterion reduced rows** go
through `ledger.py runs-append` (§5). Both entry points load the same schema and
share the same file lock.

## 5 Ledger schemas (single-writer multi-reader, keys threaded through)

Conventions: **every entity row in a jsonl ledger carries `schema_version`** (omitted
in the examples below); validators validate against the in-row version, renderers read
compatibly. **md-genre ledgers (principles doc / spec / tickets / batch reports) keep
the version in the file header** (principles doc = revision number), not per row.
Schema files ship with the plugin as defaults, projects may override (§7
`ledgers.schemas`); **a schema change = mandatory R5 table item** + version bump.
Ledger ids (S/D/B/F prefixes) are auto-assigned by ledger.py; writes are atomic
appends under a file lock.
**Every ledger.py write requires the `--layer` self-report parameter** (each layer's
SKILL.md skeleton hard-codes its own value; the sole fifth value `user` is accepted
only by the feedback review subcommand, see the feedback ledger below). Write-authority
and transition checks are **foolproofing, not tamper-proofing** — they catch misuse
(a session forgetting who it is), not malicious misreporting; misreporting is outside
the threat model.

**Principles-doc entry** (idea layer writes; md table):
`principle_id | scope | one-sentence principle | criterion_cmd (registry command) |
latest measurement (back-filled by ledger.py, never hand-filled)`
Doc header carries the revision number; entries tagged with the four states:
【current】/【decided-to-change】/【idea-pending】/【revoked】.

**spec** (deploy layer writes): file header
`{approved_by, approved_date, approved_against_principles_version}` — approval state
on disk; a new session may not treat a draft as approved.
Each item: `{item_id, principle_id, content, acceptance, depends_on[], priority,
droppable}`.

**Tickets** (deploy layer writes; minimal field contract, new1 hooks the existing
issue-tracker convention):
`issue_id, spec_item (backref to item_id), Status line, acceptance (copied from or
referencing the spec item), Blocked by`.

**Batch report** (deploy layer writes; md): header
`{batch_id, spec_items[], run_ids[], date}`; batch_id rule
`<spec-item>-<YYYYMMDD>-<seq>`; body carries zero interpretation (what happened,
what the numbers are, evidence paths) — evidence_lint covers it too.

**Story ledger `story.jsonl`** (idea layer writes):
```json
{"claim_id": "S001", "claim": "one-sentence claim",
 "evidence_runs": ["run_id"], "baseline_runs": ["run_id"],
 "candidate_runs": ["run_id"], "selection_rule": "how candidates were picked",
 "derivation_command": "recompute command for derived quantities", "principle_id": "P003",
 "role": "main-result|ablation|counterexample|motivation", "decided_by": "user",
 "date": "YYYY-MM-DD", "status": "active|retired", "retired_reason": "",
 "retired_date": "", "superseded_by": "", "note": ""}
```
Write validation: every referenced run_id must exist in runs.jsonl **with status=ok**.

**Decisions ledger `decisions.jsonl`** (a deploy-layer ledger; any layer's session
writes via the script):
```json
{"decision_id": "D001", "kind": "decision|grant",
 "where": "file path | spec item | ticket id (may be empty for kind=grant)",
 "question": "the decision point, or the category of things being granted",
 "options": ["... (may be empty for grant)"], "chosen": "grep-able concrete value (may be empty for grant)",
 "reason": "...", "authorized_by": "user's literal words | discussed | grant:D00x",
 "scope": {"desc": "what class it governs", "path_globs": ["..."], "expires_at": "ISO|null"},
 "principle_ref": "P00x|null", "affects": ["spec item / ticket / run_id"],
 "decided_by": "user|agent", "raised_at": "ISO-seconds", "decided_at": "ISO-seconds",
 "status": "open|decided|withdrawn", "superseded_by": ""}
```
- `kind=grant` is the pre-authorization genre: where/options/chosen may be empty,
  **scope must be fully structured**. Active-grants view = kind=grant, status=decided,
  unexpired, no superseded_by.
- **decision_refs is authoritative; affects is its materialized index**: the same
  ledger.py action that writes a launch order back-fills the run_id into the affects
  of every decision named in decision_refs (the trigger is the deploy-layer session
  writing the launch order — not a separate step); on divergence the launch order
  wins, and trace_check verifies consistency.
- R5 rulings are force-recorded (§3 R5) — a ruling living only in blocked.answer
  free text is not allowed.

**Blocked ledger `blocked.jsonl`** (per-transition write authority):
```json
{"blocked_id": "B001", "from_layer": "idea|deploy|run|oversight",
 "to_layer": "user|idea|deploy",
 "kind": "principle-gap|r5-choice|failure|other",
 "ref": "spec item / ticket / run_id", "question": "what is stuck, what is missing",
 "where": "(required for kind=r5-choice)", "options": ["(required for kind=r5-choice)"],
 "evidence": ["log paths", "attempted actions"], "raised_at": "ISO-seconds",
 "status": "open|answered|closed|withdrawn",
 "answer": "", "answered_at": "", "answered_by": "",
 "grant_ref": "D00x|null (required for r5-choice when answered_by≠user)",
 "decision_ref": "D00x|null"}
```
- Per-transition write authority (enforced by ledger.py against --layer): open may
  only be written by from_layer; answered only by to_layer — **the to_layer=user
  special case**: any layer's on-the-spot session may transcribe, but field-level
  checks force answered_by=user and answer containing the user's literal words;
  closed/withdrawn only by from_layer.
- Rendering: open goes to to_layer's to-do, answered goes to from_layer's
  to-confirm — **both count as unresolved**; closed/withdrawn are hidden.
- **kind=r5-choice entries**: where/options required at open; the answer transition
  requires `--chosen` (a grep-able concrete value) — ledger.py **mechanically
  assembles** the decision entry from the four structured pieces
  where/options/chosen/answer (no free-text guessing), with `decision_ref` pointing
  back. The assembly's field mapping is written down: reason = the answer verbatim;
  decided_by = user when answered_by is user, else agent; authorized_by = the answer
  (user's literal words) when answered_by is user, else `grant:<grant_ref>` —
  **an r5-choice answered by anyone other than the user must pass `--grant`**
  (landing in grant_ref, pointing to the active grant covering this fork), otherwise
  rejected. This is exactly R6's machine-check anchor.

**Feedback ledger `feedback.jsonl`** (append-only co-writing, entries carry layer;
two row types):
```json
{"fb_id": "F001", "kind": "suggestion", "date": "YYYY-MM-DD",
 "layer": "idea|deploy|run|oversight",
 "context": "which phase / which loop", "problem": "where it chafed",
 "suggestion": "proposed change"}
{"fb_id": "F002", "kind": "review", "ref": "F001", "layer": "user",
 "verdict": "accepted|rejected", "note": "", "date": "YYYY-MM-DD"}
```
Reviews never rewrite old rows: the user's review session **appends kind=review rows**
via ledger.py (routing sentence "review the feedback"); a review row's layer is always
`user` — hence `--layer` has a fifth legal value `user`, accepted only by the feedback
review subcommand (all other writes still accept only the four layer/plane values).
A suggestion's effective status = the verdict of the latest review row pointing at it;
no review row = pending (the renderer merges the view). The ledger body is pure
append, so the shared-append machine check (validator admits appends only) holds.

**Launch order `launch_orders/<run_id>.json`** (deploy layer writes, run layer
read-only):
```json
{"run_id": "assigned by the deploy layer per project naming rules; the run layer must not invent one",
 "spec_ref": "item_id", "issue_ref": "ticket", "decision_refs": ["D00x"], "batch_id": "...",
 "registry_task": "registry task name", "argv": [...], "env_name": "...", "workdir": "...",
 "expected_commit": "...", "seed": 0, "dataset_version": "...",
 "resources": {"gpus": 1, "min_vram_gb": 0, "exclusive": false},
 "expected_runtime_s": 0, "depends_on": ["run_id"],
 "expected_outputs": [{"path_glob": "...", "min_bytes": 0, "min_lines": 0, "required_keys": []}],
 "metrics_cmd": "structured number-extraction command", "smoke_cmd": "...",
 "retry": {"max_attempts": 2, "retriable_errors": [], "allow_card_swap": true},
 "mutable_params": ["whitelist of argv parameters only; seed never included; resource allocation belongs to retry"],
 "artifact_dir": "...", "created_by": "...", "created_at": "ISO-seconds"}
```
- **Structured extraction contract (shared by metrics_cmd and criterion_cmd)**: the
  last line of stdout must be a single JSON object — criterion_cmd at least
  `{"value":…, "evidence_path":…}` (evidence_path lands in the reduced row's
  output_dir); metrics_cmd at least `{"metric_name":…, "value":…, "n":…}`. The intake
  script parses only this last line; a parse failure = intake refused and escalated
  per R8 — no eyeballing logs to fill numbers.
- Timeout verdicts use expected_runtime_s (× config factor); "stalled" verdicts use
  the config stall_thresholds — separate jobs.
- **Ordering against the project job ledger**: deploy layer writes the launch order →
  run-layer rails read it, launch, and register the job ledger → RUNMETA/job ledger
  backref launch_order_ref. The launch order does not replace the job ledger: launch
  order = what to run (prospective), job ledger = how it went (retrospective).

**runs.jsonl** (definition authority: deploy layer via `runs.schema.json`; write
authority split by row type — normal rows to the run layer, criterion reduced rows to
the deploy layer, §1 third exception; script-validated before write):
rows carry at least `run_id, status(ok|failed|oom|timeout|empty-output|killed|partial),
output_dir, runmeta_path, metric_name, value, n(denominator), filter, seed,
dataset_version, batch_id, arm(treatment|control),
principle_id (criterion reduced rows only, always null on normal rows),
commit (criterion reduced rows; null on normal rows — their commit lives in RUNMETA),
elapsed_s, gpu_count, schema_version`.
**Rows with status≠ok may have null metric_name/value/n.**
**A criterion run is a reduced row** (principle_id non-null ⇔ reduced row, one-to-one):
required fields are only run_id, status, principle_id, value (the criterion's
count/verdict value), output_dir (evidence file path), commit (runs-append grabs git
HEAD automatically, `-dirty` suffix on a dirty tree), elapsed_s, schema_version; all
else may be null. run_id is assigned by ledger.py as
`chk-<principle_id>-<YYYYMMDD>-<seq>`, and that date segment is the date source for
the rendering script's "latest measurement + date" back-fill (criterion runs open no
launch order — the one written exception to "run_id is assigned by the deploy
layer"). **Execution contract**: a **deploy-layer session** executes criterion_cmd on
the spot (registry commands carry their own interpreter and environment; no launch
order env_name/workdir needed); criteria are always lightweight and read-only (R1
hard constraint) — no GPU, no dirty-tree launch gate, no job-ledger registration, no
RUNMETA. Evidence needing heavy compute is first produced by a normal run;
criterion_cmd then checks the artifact paths (output_dir may point at an evidence
file inside that artifact). Provenance is the reduced row itself
(principle_id → principles doc + commit + output_dir evidence file).
Intake goes through `ledger.py runs-append` (--layer deploy, §1 third exception),
consuming criterion_cmd's structured output (contract above), with the same schema
validation. **A row lands only on exit code 0 with a parseable JSON tail line
(status=ok)** — nonzero exit or parse failure lands no row and escalates per R8:
a criterion that didn't run is not a measurement, and the principles doc's "latest
measurement" does not update.
**trace_check backward-chain exemption**: rows with non-null principle_id skip the
run → launch order → ticket backref check; instead verify principle_id exists in the
principles doc and criterion_cmd is in the registry.

**RUNMETA** (run layer writes; **location convention: `RUNMETA.json` at the
artifact_dir root**, back-referenced by runs.jsonl.runmeta_path): commit + argv +
dirty-file list + `launch_order_ref` + `attempt_no` + `env_name` +
`outputs: [{file, format, fields:{field name: meaning}}]` (the artifact field
dictionary, auto-generated by the code that writes each file — the oversight plane's
sole authority for reading formats).

**Job ledger**: add `status enum (same as runs), exit_code, attempt_no, gpu_ids,
host, tmux_session, started_at, ended_at, log_path, artifact_dir, launch_order_ref,
escalation_ref (blocked_id), sampler verdict (stall|dead|ok + verdict time)`.

**Error classification table** (deploy layer writes, error_classify.py decides):
`{feature: {exit_code | output_check verdict | log_regex} → action: retry|swap-card|escalate}`.
**Cluster slow-variables file**: run-layer write authority (new1 hookup:
ops/gpu_state.md).

## 6 Routing table (the entire content of the research-loop thin shell)

| User says | Phase | Route to |
|---|---|---|
| I have an idea / discuss direction | ① | idea-layer (talk; literature verification via rails.literature) |
| set a principle / this goes into the principles | ② | idea-layer (principle template + R1) |
| what do we do this round / produce the spec | ③ | deploy-layer (spec + trace_check) |
| build / execute tickets | ④ | deploy-layer → rails.build (new1: ticket-run) |
| run experiments | ⑤ | deploy-layer writes launch orders → rails.gpu / rails.pipeline |
| does this result enter the story | ⑥ | idea-layer (user rules → ledger.py story) |
| write the paper | ⑦ | rails.paper (new1: paper-write), sourcing numbers against the story ledger |
| check X / let me see for myself | any | oversight → inspector |
| what's in the outputs | any | oversight → inspector (observation report = R3 subtype) |
| what's waiting on me | any | ledger.py blocked rendering (pending-queue view) |
| you decide this class of things (grant) | any | ledger.py grant intake (structured scope, on the spot) |
| I withdraw that decision | any | revocation genre → status change + superseded_by in the ledger |
| this won't do, redo it (send-back) | any | return to the responsible layer, reason into the batch report |
| review the feedback | after close-out | ledger.py feedback review (R9) |

## 7 Project hookup (plugin generic ↔ project rails)

Repo-root `research-loop.json` (write authority: user/main session; changes go
through git):
```json
{"ledgers": {
   "principles": "METHOD.md", "story": "ops/story.jsonl", "timeline": "TIMELINE.md",
   "literature": "KNOWLEDGE_MAP.md",
   "specs": ".scratch/", "issues": ".scratch/*/issues/",
   "decisions": "ops/decisions.jsonl", "blocked": "ops/blocked.jsonl",
   "feedback": "ops/feedback.jsonl", "launch_orders": "ops/launch_orders/",
   "batch_reports": "plans/", "codemap": "MAP.md",
   "runs": "ops/runs.jsonl", "jobs": "ops/jobs.json",
   "schemas": "ops/schemas/", "runs_schema": "ops/schemas/runs.schema.json",
   "error_classes": "ops/error_classes.json", "cluster_state": "ops/gpu_state.md",
   "datasets": "DATA.md", "reports": "reports/",
   "runmeta": "<artifact_dir>/RUNMETA.json", "raw_data": "<raw_data_roots>/**"},
 "owners": {"principles": "idea", "story": "idea", "timeline": "idea", "literature": "idea",
   "specs": "deploy", "issues": "deploy", "decisions": "deploy",
   "feedback": "shared-append", "blocked": "per-transition",
   "launch_orders": "deploy", "batch_reports": "deploy", "codemap": "deploy",
   "schemas": "deploy", "runs_schema": "deploy", "error_classes": "deploy",
   "datasets": "deploy",
   "runs": "per-row-type", "jobs": "run", "cluster_state": "run", "runmeta": "run",
   "raw_data": "run", "reports": "oversight"},
 "registry_cmd": "python3 run.py",
 "registry_query": "python3 run.py show --list",
 "dirty_exempt_globs": ["ops/jobs.json*", "ops/runs.jsonl", "RESULTS.md", "*.lock"],
 "stall_thresholds": {"no_log_growth_s": 0, "gpu_idle_s": 0, "startup_grace_s": 0},
 "runtime_factor": 3,
 "rails": {"build": "ticket-run", "gpu": "gpu-run", "pipeline": "probe-pipeline",
           "paper": "paper-write", "literature": "update-knowledge-map"},
 "raw_data_roots": ["/net/.../reproduce/new1/"]}
```
- `ledgers` is the **complete ledger registry** (the oversight plane's traceability
  root); every ledger in the §1 write-authority table has a path here; values may be
  path templates (`<artifact_dir>`, `<raw_data_roots>` placeholders).
- `owners`' **key set is strictly equal to ledgers'** (the config validator checks
  this); values map 1:1 to the §1 write-authority conventions (three-layer table +
  the oversight-plane item). **Value domain, written down**: layer names
  `idea|deploy|run`, plane name `oversight`, rule names `per-transition`
  (machine-checked per §5 transition rules) | `shared-append` (appends only; entries
  self-certify via layer) | `per-row-type` (runs.jsonl only, §1 third exception:
  normal rows to the run layer via the project bookkeeping script, criterion reduced
  rows to the deploy layer via runs-append; machine check = runs-append accepts only
  `--layer deploy`) — the validator admits these seven values and nothing else.
- `registry_query` must be a **read-only action exempt from the dirty-tree gate**;
  the sample value awaits new1 verification (§9 hookup list item 5); if it doesn't
  qualify, add a read-only entry point.
- No config file = project not wired: rail actions and all bookkeeping are refused —
  ledger paths all come from `ledgers`; no config, no landing spot; only talk is
  available. Wiring step one: `ledger.py init` generates a research-loop.json
  skeleton from the plugin's template; a human fills in the paths, then it passes
  config validation.
- The dataset inventory hooks DATA.md (new1 side adds a structured header:
  dataset_id / path / generating commit / row count / checksum / current version).

## 8 End-to-end script (walked at acceptance)

1. "I have an idea" → idea-layer talks it through; literature enters KNOWLEDGE_MAP
   (rails.literature). Output: candidate hypotheses.
2. Talked through → write/amend principles, each passing R1. User rules.
3. Produce the spec (with acceptance/depends_on; approval in the file header) →
   trace_check all green. User rules.
4. Spec → tickets (§5 ticket contract) → rails.build constructs. Decision points run
   the R5 three questions; self-decisions first consult the active-grants view
   (mandatory read ②) and only proceed on a hit, with R6 traces.
5. Deploy layer writes launch orders (with seed/dataset_version/decision_refs; the
   same action back-fills run_id into the affects of referenced decisions) → smoke →
   criterion live run (criterion_cmd structured output into runs.jsonl with
   principle_id) → evidence report (R3) → evidence_lint + verify_report pass → user
   verifies in person → batch launch via rails.gpu (rails read the launch order,
   register the job ledger, RUNMETA backrefs); output_check guards against empty
   artifacts; numbers enter only via metrics_cmd/criterion_cmd.
6. Runs done → inspector observation report (formats read from RUNMETA.outputs) +
   spotcheck list → user reads the originals. regression_check contrasts against the
   story ledger; conflict lists land in reports/.
7. User rules a result into the story → ledger.py story intake (run existence +
   status=ok validation).
8. Back to 1, or on to rails.paper with numbers sourced against the story ledger.
9. At any moment "check X" → inspector digs through the ledger registry to the raw
   files (runmeta_path → RUNMETA → outputs dictionary); "what's waiting on me" →
   pending-queue rendering.
10. Close-out: every layer's feedback enters the feedback ledger; "review the
    feedback" runs the R9 review. All failures climb the R8 stairs throughout
    (error_classify.py decides, no LLM).

## 9 Acceptance criteria

- Five skills + inspector agent + eight scripts + schemas/ all present; plugin
  installs; routing table triggers.
- Every script has a runnable self-test. Key cases:
  - trace_check: spec item with no principle_id backref → error; run→ticket broken
    chain → error; criterion reduced row (non-null principle_id) → not reported as a
    broken chain, instead verify principle_id in the principles doc and criterion_cmd
    in the registry; decision→run reverse lookup (via decision_refs and affects)
    returns the correct set.
  - ledger.py story: run_id missing or status≠ok → refused; revocation →
    status + superseded_by.
  - ledger.py blocked: state machine and per-transition write authority (wrong
    --layer → refused), illegal transitions → refused; opening r5-choice without
    where/options → refused; answer without --chosen → refused; answered entries
    auto-sync a decision entry and back-fill decision_ref (mechanical assembly, no
    free-text parsing); r5-choice answered with answered_by≠user and no --grant →
    refused; to_layer=user special case: answered_by≠user → refused.
  - ledger.py grant: no structured scope → refused; expired/superseded grants stay
    out of the active-grants view.
  - ledger.py feedback: review rows only via the review subcommand (--layer user);
    review row with layer≠user, or any rewrite of an old row → refused.
  - ledger.py runs-append: --layer≠deploy → refused; criterion_cmd nonzero exit or
    non-JSON tail line → no row, escalate.
  - output_check: exit code 0 + empty artifact → verdict empty-output, must not be
    recorded ok.
  - error_classify: one rule per feature kind (exit_code / output_check verdict /
    log_regex) hits the right action; no hit → escalate.
  - evidence_lint: contains "passed"; or a number with no repro command → flagged.
  - verify_report: fabricated counts / nonexistent paths / altered excerpts → each
    caught.
  - spotcheck: population fingerprint changed, same seed resampled → reports
    "population changed", never silently yields different samples.
  - regression_check: new number conflicts with an active claim → list lands in
    reports/.
- After the new1 hookup, steps 1–3 of the §8 script (no GPU) walk through for real.
- **Rails compatibility promise (revised)**: the outward flows and current behavior
  of ticket-run/gpu-run/probe-pipeline/paper-write do not change; the incremental
  changes the new1 hookup needs go on a **separate hookup list** in the
  implementation plan. Five known items: ① launchers write back launch_order_ref
  etc.; ② record.py gains runs-schema validation (the normal-row entry point; the
  criterion reduced-row entry point is ledger.py runs-append — same schema, shared
  file lock; record.py's current lock protocol needs a compatibility check);
  ③ RUNMETA gains the outputs dictionary; ④ launchers accept a deploy-layer-assigned
  run_id (new1 launchers currently take a task name as input — likely zero change,
  needs verification); ⑤ verify/add the read-only gate-exempt registry_query entry
  point. Each item passes the project self-check; if ①③④ turn out to change flows,
  they return to this spec through R5 first.

## 10 What we don't do (YAGNI)

- No rewriting of any existing rail skill's content — routing hookup only
  (incremental fields per the §9 hookup list).
- No parallel multi-research-line directory trees (schemas already carry primary
  keys; a future migration won't be rework).
- No web UI; the oversight plane's product is text reports.
- No automatic triggers (hooks); routing is conversation-triggered.
- **Deferred (audit P2 + round-2 acceptance's non-blocking items)**: notifications /
  deadlines for reports/ and the blocked ledger (covered for now by mandatory reads
  and session-exit reporting); a dedicated downward "provisional instruction /
  evidence request" genre (covered by the spec's exploratory marker and routing
  sentences); a feasibility-cost query view over the job ledger (elapsed_s/gpu_count
  already recorded, view deferred); hook-level verification of oversight sessions'
  read-only-ness.
- Final shape of the md system (what renders to the repo root, under what names)
  is settled during implementation, not locked in the spec.
