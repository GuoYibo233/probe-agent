# Glossary: one name per thing, in every ledger, skill and conversation

<!-- Source: build plan 2026-08-16 section 2 (plans/2026-08-16-research-loop-build-plan.md L27-L53), carried into 09 L14. The third column is the draft gyb has not walked through yet: PENDING(part 09 L19). -->

Every thing in this system has one name, the one in the first column, and that name is used in code, ledgers, skills and conversation alike. The second column says what the thing is. The third column says what it is not.

## Roles and actors

| Term | What it is | What it is not (draft) |
|---|---|---|
| `idea` | The role that talks ideas through with gyb and opens work orders to deploy and analysis orders to analysis. | Not a coder; it never edits experiment code. |
| `deploy` | The role that writes the code: turns an idea into a runnable implementation and hands the launch to run. | Not the role that launches or watches GPU jobs. |
| `run` | The role that watches the servers, launches and finishes long-running experiments, and reports problems. | Not a fixer; every problem becomes an issue to deploy. |
| `analysis` | The role that computes the numbers and draws the figures gyb asked for, from finished runs. | Not a source of new metrics; nothing is computed without an approved evaluation. |
| `reviewer` | The role that checks whether the whole chain did what gyb and idea decided. | Not a fixer and not an issue opener; it only writes lists for gyb. |
| `gyb` | The person. The superuser: no permission check applies, every ledger row can carry gyb as actor. | Not a role; gyb has no role json and no skill. |
| actor | Who a ledger row is written as: one of the five roles or `gyb`. | Not the session; a role session can write a row whose actor is `gyb` with `--as-gyb --quote`. |
| session | One loaded role in one terminal, registered in the sessions ledger. | Not the person typing; `rl` decides identity by session only (principle-01). |
| `cli` | The session name a bare terminal writes under; its actor is always `gyb`. | Not a role session; `--as-gyb` is not needed there. |

## The nine ledgers

| Term | What it is | What it is not (draft) |
|---|---|---|
| `decisions` | The decision ledger, one file per actor: `loop/decisions.<actor>.jsonl`, six files for five roles plus gyb. | Not one shared file; the file is chosen by who decided. |
| `issues` | The issue ledger, `loop/issues.jsonl`: problems reported from one role to another. | Not a task list; an issue asks someone to answer, it does not assign work. |
| `handoffs` | The handoff ledger, `loop/handoffs.jsonl`: orders passed between roles. | Not a chat; every change to an order is a new version with a status. |
| `runs` | The runs ledger, `loop/runs.jsonl`: numbers from experiments, written only by run's scripts, gyb excepted. | Not typed in by a role from a log read by eye (rule-03). |
| `grants` | The grants ledger, `loop/grants.jsonl`: permissions gyb hands out. | Not writable by any role; only gyb writes it. Schema reserved: PENDING(issue 43c). |
| `feedback` | The feedback ledger, `loop/feedback.jsonl`: proposed changes to the shared rules and templates. | Not a place to change a rule; the rule changes only after gyb accepts. |
| `evaluations` | The evaluations ledger, `loop/evaluations.jsonl`: metrics and figures gyb agreed to see. | Not results; it holds what may be computed, not what was computed. |
| `sessions` | The sessions ledger, `loop/sessions.jsonl`: which session loaded which role, when, under which `rules_version`. | Not a log of what the session did. |
| `scratch` | The scratch ledger, `loop/scratch.jsonl`: quick-lane entries and other side notes. | Not a decision ledger; nothing in scratch counts as decided. |
| `loop/` | The directory holding the nine ledger files. | Not opened directly by any role; ledgers are read through `rl` query commands only. |

## Handoffs

| Term | What it is | What it is not (draft) |
|---|---|---|
| `work_order` | An order from idea to deploy to build something; on the quick lane, from deploy to deploy to backfill. | Not a launch; deploy opens a separate launch order for that. |
| `analysis_order` | An order from idea or gyb to analysis to compute or draw something. | Not a request for a new metric; the evaluation must already be approved. |
| `launch_order` | An order from deploy to run to launch an experiment; a container for one or more attempts. | Not one run; the same order may hold several attempts. |
| `todo` | Order state: opened, nobody working it. | Not "waiting for approval"; that state does not exist for orders. |
| `in_progress` | Order state: a session holds it and is working it. | Not entered from any state with a non-empty holder. |
| `stuck` | Order state: the holder stopped because something outside the order is needed. | Not failed; a stuck order resumes. |
| `done_pending_review` | Order state: the work is delivered and waits for the owner's acceptance. | Not accepted; the owner may still reject. |
| `accepted` | Order state: the owner accepted the delivery. Terminal. | Not reopened; further work is a new order. |
| `rejected` | Order state: the owner sent the delivery back. | Not terminal; the order goes back to work. |
| `withdrawn` | Order state: the owner or gyb pulled the order. Terminal. | Not a rejection; nothing was delivered. |
| `owner` | The role that opened the order and answers for it from open to close. Recorded as `gyb` for quick-lane backfills and gyb's own orders. | Not a session; the owner role's current session, or gyb, acts for it. |
| `holder` | The session id currently working the order; non-empty exactly in `in_progress`. | Not the owner. |
| `last_holder` | The session id that held the order before the holder was cleared. | Not the current holder. |
| `dispatch` | How the order is handed on: `auto` (the owner starts a subagent in the background), `manual` (gyb takes it in person), `none` (not handed on yet). | Not the model that runs the subagent; that is in the role json. |
| `parent_id` | The order this order was opened under; decision references and batch are inherited from it. | Not the decision; the decision chain is reached through the parent. |
| `supersedes` | The order this order replaces. | Not a parent. |
| `attempt` | One try on a launch order: its own command, step table, estimate and run row. | Not a new order. |
| `code_paths` | The list of code files a delivered work order changed; required at `done_pending_review`, filled by deploy. | Not report paths; reports are separate. |
| `step_table` | The stages of an attempt with their expected timing. | Not the progress note. |
| `estimated_seconds` | The estimate for the latest attempt. | Not the sum over attempts. |
| `actual_seconds` | The measured duration, computed by `rl run finish` from timestamps whatever the exit status. | Not typed in by anyone. |
| `output_paths` | The deliverables of an analysis order. | Not the notebook alone; every produced file is listed. |
| `config` | The configuration dictionary on a launch-order attempt; run copies it and never guesses. | Not the host's config file. |
| `progress_note` | Free text on an order version saying where the work stands. | Not a status; the status field is separate. |
| `batch` | Free text passed by the caller to group orders and runs; `rl` never assigns it. | Not a queue; it has sharding meaning only. |
| `line` | A research line, identified by its root decision id. | Not a batch. |
| `reclaim` | The command that returns orders whose holder session is dead to `todo`. | Not a delete. |
| `adopt` | What the next run session does with an attempt that was launched but never finished: takes over the watchdog and the finish without relaunching. | Not a retry. |

## Decisions and evaluations

| Term | What it is | What it is not (draft) |
|---|---|---|
| `decision` (source kind) | A source that points at an earlier decision by id and version. | Not a file path. |
| `file` (source kind) | A source that points at a path inside the repository, optionally with a `#anchor`. | Not an external link. |
| `run` (source kind) | A source that points at a run id in the runs ledger. | Not a launch order. |
| `root_id` | The root decision of a decision's tree; two parallel research lines are separated by it. | Not the parent decision. |
| `stale` | A reference on an order or a decision whose recorded version is lower than the latest non-confirm version of the decision it cites (02 L85; 10 L110). | Not retired; the cited decision still exists, and the order keeps working at the version it cited until gyb withdraws or reissues it. |
| `retired` | A decision or evaluation taken out of force with a reason. | Not deleted; the rows stay in the ledger. |
| `metric` | Evaluation kind: a number to compute. | Not a figure. |
| `figure` | Evaluation kind: a plot to draw, with its grouping and axes. | Not a metric. |
| `proposed` | Evaluation state: analysis proposed it, gyb has not decided. | Not usable yet; nothing is computed under it. |
| `approved` | Evaluation state: gyb approved it; numbers may be produced. | Not permanent; it can be retired. |
| `rejected` (evaluation) | Evaluation state: gyb turned it down. | Not retired; it was never in force. |

## Issues

| Term | What it is | What it is not (draft) |
|---|---|---|
| `cannot` | Issue kind: the assignee cannot do the order as written. | Not a refusal of ownership; that is `not_mine`. |
| `not_mine` | Issue kind: the order belongs to another role. | Not a capability problem. |
| `denied` | Issue kind: the hook blocked a write; the hook's message names the issue to open. | Not a permission request; that is `request`. |
| `failed` | Issue kind: an attempt failed, with `stage` set to `smoke`, `launch` or `crash`. | Not an anomaly in results; the run did not complete. |
| `stage` | On a `failed` issue: which step failed. | Not a handoff status. |
| `smoke` | Stage value: the smoke run before launch failed. | Not the launch itself. |
| `launch` | Stage value: the launch command failed. | Not a crash after a successful launch. |
| `crash` | Stage value: the job died after launching. | Not a wrong result; a completed run with odd numbers is `anomaly`. |
| `anomaly` | Issue kind: the run completed but the result looks wrong. | Not a failure. |
| `request` | Issue kind: asking for something (a grant, a file, a decision). | Not a report of a problem. |
| `withdrawn` (issue) | Notice kind: the order you held was withdrawn. | Not something to answer; it is a notification. |
| `orphaned` | Notice kind: the holder session died and the order was returned to `todo`. | Not a failure of the work. |
| `fyi` | Notice kind: gyb handled your order over the owner's head. | Not an assignment. |

## Reports, lanes, trees and the command

| Term | What it is | What it is not (draft) |
|---|---|---|
| `deploy_report` | deploy's two delivery reports. | Not one document; there are two. |
| `method` | The report without files: what was done and how, quoting verbatim every decision id and version the order cites. | Not the file list. |
| `detail` | The report with files: every file touched, including host files outside the role directory. | Not the method summary. |
| `quick_lane` | The path gyb names for a quick look: `rl ql open` in, `rl ql close` out, everything between in a worktree and the scratch ledger. | Not a shortcut around orders for normal work; gyb has to name it. |
| `ql_tag` | The quick-lane tag, shaped like `ql-20260816-01`, assigned by `rl` under a lock. | Not chosen by the role. |
| `artifact_root` | The root directory for experiment artifacts, outside the repository. | Not the role directory. |
| `analysis_artifact_root` | The root directory for analysis artifacts, outside the repository. | Not `analysis/` inside the repository. |
| `research-loop.json` | The per-repository configuration file: roots, thresholds. | Not the plugin's own manifest. |
| `bin/rl` | The command entry point; every ledger write and every ledger query goes through it. | Not a library to import from role code. |
| `--as-gyb` | The flag that writes a row as gyb from a role session; always with `--quote`. | Not needed from `cli`, where the actor is gyb already. |
| `--quote` | gyb's own words from the moment, kept for reviewer. | Not a paraphrase. |
| `--force --reason` | gyb's override of a data validation failure; the reason is written into the row. | Not a permission override; gyb never needs one. |
| `rules_version` | The integer on the first line of `common/GLOBAL-RULES.md`; sessions record the value they loaded. | Not a plugin version. |
