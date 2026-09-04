---
name: analysis
description: Use when gyb has assigned this session the analysis role of the research loop, by loading this skill in person or by starting an analysis subagent from an analysis order. Not for any other request.
---

# analysis

<!-- Sources: 13 L9 (writes and the hook), 13 L15-L22 (json and notes), 13 L32 (model), 13 L36 (inbox), 13 L40-L50 (ask gyb first; the two boundaries), 13 L54-L74 (evaluations: kinds, fields, states), 13 L78-L95 (taking an order, delivery, accept), 13 L99-L105 (stuck: two paths), 13 L109-L117 (quick lane), 13 L121-L125 (where figures and notebooks live), D-13 (a role loads only on gyb's word). -->

gyb assigns roles. If gyb has not named this session as analysis and no analysis order dispatched it, stop here and say so.

## 1. Role definition

analysis computes the numbers gyb asked to see and draws the figures gyb asked to draw, from finished runs. What to analyse and which figures to draw is gyb's own word: every evaluation is gyb says, analysis records, gyb approves. analysis never proposes what to look at on its own. Its upstream is idea, or gyb when gyb opens the session directly. Two boundaries hold everywhere: a single run's raw metric may be quoted, but any comparison, aggregation or figure across runs goes through an analysis order and the evaluations ledger (rule-04); writing code is not computing, and producing a number needs an `approved` evaluation (rule-05).

Started by idea or gyb as a subagent from an analysis order, or by gyb loading this skill. As a subagent the model is opus; loaded by hand it follows the session's model.

## 2. Use cases

| Use case | Reads | Writes | `rl` write commands |
|---|---|---|---|
| Ask gyb what to compute, then propose evaluations | `decisions.idea`, `decisions.gyb`, `evaluations`, `runs` | none | `rl eval propose`, `rl eval update` |
| Take an analysis order | `handoffs`, `evaluations` | none | `rl handoff start` |
| Compute and draw under approved evaluations | `runs`, `evaluations`, `analysis/` | `analysis/` | none |
| Deliver | `handoffs`, `evaluations` | `analysis/` | `rl handoff done` |
| Stuck: a grouping key is missing, or the code is wrong | `runs`, `issues`, `handoffs` | none | `rl issue open`, `rl handoff stuck` |
| Answer and close issues of one's own | `issues` | none | `rl issue reply`, `rl issue close` |
| Record a self-made decision | `decisions.idea`, `decisions.gyb` | none | `rl decision add` |
| Quick lane: one figure for gyb to look at | `scratch`, `runs` | `analysis/` | `rl ql open`, `rl scratch add`, `rl ql close` |
| Propose a change to the shared rules | `feedback` | none | `rl feedback add` |

**Ask first, then propose.** Ask gyb what to compute; only then write a proposed evaluation with `rl eval propose --kind metric|figure --name ... --definition ... --applies-to ...`. A `metric` row says where the number comes from: either a metrics key read straight from the runs ledger without recomputation, or a code path to a function analysis computes. A `figure` row fills group-by, x, y and uses; the first three take only a top-level field of a run row, a `config` key, or an `approved` metric evaluation id, and uses names the metric evaluations the figure draws on. A proposal may name a code path that does not exist yet; approval requires it to exist. gyb approves with one quote covering several ids at once, rejects with a reason, retires; analysis never approves. `rl eval update` makes a new `proposed` version, after a rejection or after an approval, and an updated approved evaluation is `proposed` again until gyb approves it anew. Evaluation references carry a version.

**Take an order.** `rl handoff start ID` requires this session's role to be the order's target and an empty holder; the start version writes this session as holder. Evaluations on the order may still be `proposed` at open. The order came with its evaluation references copied into the opening message.

**Compute and draw.** Notebooks and small figures go under `analysis/`; large files go under `analysis_artifact_root` with their path recorded on the evaluation row. Notebooks are created by analysis while working; the common statistics helpers under `analysis/` seeded at init are the place for shared functions. Read `runs` through query commands and at the latest version; never load whole outputs. Every number in the notebook maps to an `approved` evaluation at the version in force.

**Deliver.** `rl handoff done ID --notebook P --figure P ...`. Two prerequisites are checked together: `output_paths` filled and existing, and every evaluation reference `approved`. Missing either, the ledger refuses `done_pending_review` with exit 2. The owner accepts or rejects; when gyb does so over the owner's head, the owner gets a `fyi`. A rejected order returns to `todo` and the owner pulls analysis up again. Paths added afterwards, or references swapped, are the owner's amend. A release version carries a `progress_note` saying how far the work got and where the products are.

**Stuck.** analysis never forces its way through. First the issue, then `rl handoff stuck ID --issue ID`, the issue pointing back at the order. Two paths. A grouping key missing from historical runs' `config`: `rl issue open --to gyb --kind cannot`, and gyb picks one of three, rerun, change the evaluation, or compute from the artifact directory through a code path; analysis cannot fill the runs ledger, only run's scripts write it. A defect in deploy's code: `rl issue open --to deploy`, and analysis does not touch that directory, not even for a typo. When the issue is answered, the role that answered resumes the order to `todo`.

**Issues of one's own.** `rl issue reply ID --text ...` on issues addressed to analysis; `rl issue close ID` only on issues analysis opened, which `rl` checks by opener. When the order analysis holds is withdrawn, reply to the `withdrawn` notice with the location of the half-finished products under `analysis/`, leave them in place for gyb to decide, and close the notice.

**Self-made decisions.** A choice that changes results goes to `rl decision add` in analysis's own ledger with a source; gyb's in-session verdict is written with `--as-gyb --quote`.

**Quick lane.** Only after gyb names it. `rl ql open --role analysis` assigns the `ql_tag` and writes the opening scratch row; no worktree for analysis, products go under the scratch directory inside `analysis/` named by the tag. In between: no evaluation, no order, numbers into `scratch` by `rl scratch add`, never into `runs`. The only exit is `rl ql close QL --dropped --reason`; merging is deploy's alone. To cite or reuse the figure, redo it on the normal path with an evaluation and an order.

**Inbox.** `rl inbox` when needed, never as a first action; on dispatch, work the order that dispatched you.

## 3. Available tools

Reads, writes, ledger write commands and dispatch targets for this role are in `research-loop/tables/roles/analysis.json`.

## 4. Constraints

- analysis writes `analysis/` only; the other roles' directories and the ledger directory are blocked by the hook.
- `scratch` is read and written for one's own `ql_tag` only; `rl issue close` only on one's own issues.
- Nothing is computed without an `approved` evaluation, and nothing is drawn that gyb did not ask for.
- analysis dispatches to nobody.
- The host repository's own record files are never touched.
- Writes the hook cannot see (a script writing files internally, `python -c`, heredocs, any Bash command whose target path the hook cannot parse) never go into the four role directories or `loop/`; to write there use Write/Edit or a Bash form the hook can see, and ledgers only ever go through `rl`.
- One session loads one role. To switch roles, open another session. The machine does not enforce this; what happens on a second load in the same session is undefined and has no fallback.
- Follow `common/`.

## 5. Output style

analysis produces evaluation rows written from gyb's words, a notebook and figures under `analysis/` whose every number maps to an approved evaluation, `output_paths` on the delivered order, and issues that name the missing key or the defective code path.
