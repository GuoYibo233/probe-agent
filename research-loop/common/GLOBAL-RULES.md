rules_version: 1

# Global rules and design principles for every role

<!-- Sources: rule-NN is 09 L(36+NN), i.e. rule-01 = 09 L37 ... rule-09 = 09 L45; the irreversible-action note is 09 L51; numbering discipline 09 L49; the un-numbered session discipline 09 L53; principle-NN is 00 L(20+NN), i.e. principle-01 = 00 L21 ... principle-11 = 00 L31. The first line of this file is the only source of rules_version (09 L59): `rl session start` reads it, `rl feedback accept` increments it, nothing else writes to this file by machine. -->

Every role session reads this file before doing anything else. Role skills point here; they never copy these entries. Numbers `rule-NN` and `principle-NN` never change once assigned: a retired entry leaves its number empty, a new entry takes the next number, a changed entry keeps its number and only its text changes. Feedback targets and decision sources cite these numbers, so an old citation still resolves.

## Rules

### rule-01 Default at an unwritten fork
When the spec does not cover a fork, the role keeps working by the eleven principles below and appends one decision whose source states the basis. Writes made in gyb's voice (`--as-gyb`, approving an evaluation, ruling on feedback) stop hard unless gyb said it in person just now. Irreversible actions stop hard and carry gyb's words or a reason: withdrawing an order is `rl handoff withdraw --reason` (with `--quote` when done for gyb), retiring a decision is `rl decision retire` and always carries a reason, whoever retires it and from whichever terminal; the reason is recorded on that version of the decision row.

### rule-02 A self-made decision leaves a trace
Every decision a role makes on its own goes into that role's own decisions file, and its source is never empty. Only choices that change experimental results count as self-made decisions; pure writing choices do not. A verdict gyb gives in person inside a role session counts as gyb's decision: it goes into the same ledger with actor `gyb` and a quote.

### rule-03 Numbers enter the ledger only through scripts
Only run's scripts write the runs ledger (gyb excepted). Experimental data has one schema. Reading a log by eye and typing numbers in is forbidden.

### rule-04 Evidence carries a path
Every number carries a reproducible execution path. Statistical evidence goes through analysis's notebook. A single run's raw metric may be cited directly; any comparison, aggregation or figure across runs goes through an analysis order.

### rule-05 No invented metrics
analysis computes only the numbers gyb said to look at and draws only the figures gyb said to draw. Writing code is not computing; producing a number is what requires an `approved` evaluation.

### rule-06 Faults are handled by domain
deploy and idea, on receiving a problem, first judge whether the cause lies in their own domain and fix it in place when it does. run, on any problem, opens an issue to deploy and never retries on its own; a redo is the next attempt on the launch order. analysis, when stuck, opens an issue to the role where the problem lies. reviewer opens no issues; when stuck it only writes into its list for gyb.

### rule-07 Rule changes go through the feedback ledger
Roles never edit the shared templates or specs themselves. After filing feedback, keep working under the current templates without waiting for the verdict. A verdict takes effect only for sessions loaded afterwards.

### rule-08 Leaving your lane leaves a trace
What the hook blocks: the hook's own message tells the model which issue to open. What the hook lets through but exceeds your `writes` column (host files, Bash writes the hook cannot parse): list it in your report, leave a decision, and keep the host repository's rules. Reading ledgers always goes through `rl` query commands, which anyone may call. Writes the hook cannot see (a script writing files internally, `python -c`, heredocs, any Bash command whose target path the hook cannot parse) never go into the four role directories or `loop/`; to write there use Write/Edit or a Bash form the hook can see, and ledgers only ever go through `rl`. reviewer checks this afterwards with git history against the sessions ledger.

### rule-09 A fix closes its case
Whatever you fix that was reported as an issue on the ledger: reply to and close that issue when the fix is done. Silent fixes are forbidden.

## Discipline without a number
One session loads one role. To switch roles, open another session. The machine does not enforce this; what happens on a second load in the same session is undefined and has no fallback.

## Design principles
Every rule above and every rule in a role skill traces back to one of these eleven. At a fork no document covers, reason from them (rule-01).

### principle-01 Who types the command and which role the session carries are two different things
Every ledger write has an actor: one of the five roles, or gyb. gyb is the superuser: the hook, the who-may-call checks in ledger validation and the who-may-write column of the transition table never apply to gyb, and gyb exercises gyb's own powers from any terminal and inside any role session. A ledger row records both the actor and the session as they are. Corollary (second round): `rl` recognizes sessions, not fingers. All `rl` can see is which session a command came from, never who sits at the keyboard, so every identity rule is decided by session alone. A command from a bare terminal (session id `cli`) has actor gyb, with no flag and no quote. A command from a role session has that role as its default actor and writes as gyb only with `--as-gyb`, which always requires `--quote` no matter who typed it (gyb typing in person quotes what gyb just said); the quote is the trace left for reviewer, and `rl` refuses the row without it. gyb's exemption covers permissions only (who may call, who may write), never row integrity: required fields, existing paths and existing references apply to gyb too; to force a write gyb adds `--force --reason`, and `rl` writes the row with the reason recorded in it. Grants are written by gyb only: directly from a bare terminal, or from a role session with `--as-gyb --quote` on gyb's behalf.

### principle-02 Constraints come in three layers, each with its own job
The hook governs three tools, Write, Edit and Bash (Bash added 2026-08-18: the hook parses redirections, `tee`, `sed -i` and the target paths of `mv`/`cp` out of the command; whatever it cannot parse falls to discipline). It judges only by paths relative to the research repository and blocks only two outrageous things: writing into another role's directory, and writing `loop/` directly. Ledger validation governs every row of the nine ledgers and is hard. Everything else (Bash forms the hook cannot parse, the host launcher's own ledgers, what to read and how) rests on the discipline in each SKILL.md plus reviewer's checks afterwards. Corollary (second round): reading is never gated. Anyone may call the query commands of the nine ledgers; the `reads` column of a role json is discipline, not a gate; the machine check only verifies that the write commands named in a SKILL.md appear in that role's `ledger_writes`.

### principle-03 Every handoff has an owner and a holder
The owner is the role that opened the order and answers for it from open to close: pulling up the downstream role, accepting, withdrawing. The holder is the session currently working the order. Corollary (second round): the holder is non-empty exactly when the order is in progress. Every transition that leaves in-progress (done, stuck, reject, withdraw, release, reclaim) clears the holder and records the previous holder in a separate field; in-progress can only be entered from an empty holder; reclaim looks only at in-progress orders. The owner is a role, not a session: when the owner role has no live session, gyb pulls the order up, and `rl status` lists these separately. An order may be marked at open as accepted by gyb manually; when marked, the owner starts no subagent.

### principle-04 The nine ledgers are all event streams
Append-only, every row versioned; a change always means appending a new version; whether a field is required depends on the status of that version, never on a global rule. Corollary (second round): every one of the nine ledgers has a status field and validation checks by status, runs and sessions included; changing an order's content (swapping the command, adding a report path, adding a reference) is also a new version, and the states that allow it are in the transition table; prerequisites are checked at delivery, not at open: open only checks that the order can say what it is, delivery checks that everything is there.

### principle-05 Permissions derive from actions
Each role's reads, writes and callable commands are derived row by row from its use-case table and written into the role json; the json is never written first with work found afterwards to fit it. Corollary (second round): gyb also has a use-case table (first look of the day, approve, accept, pull up, reclaim, repair ledgers), and the sections of `rl status` and the filter dimensions of the list commands derive from that table, not from the five roles' tables.

### principle-06 In and out are symmetric, and whatever waits on someone has an inbox
Whatever can be written into a ledger can be queried out of it. Corollary (second round): there are two inboxes, `rl status` for gyb and `rl inbox` for roles. Whenever a version moves a row into a waiting state (waiting for gyb's approval, for the owner's acceptance, for the assignee's reply, for the owner to pull up, for someone to read a notice), that row must appear in that person's inbox. Desktop notifications are not built in this version (gyb 2026-08-21: keep only the one thing gyb has to look at, and gyb checks it by hand periodically), so gyb's inbox has a single outlet, `rl status`, which gyb checks by hand. `rl inbox` is a query, not an on-duty action: a role that has just been pulled up does not check its inbox first, it works the order that pulled it up; whoever needs `rl inbox` runs it.

### principle-07 The quick lane has an explicit entrance and exit, and both are ledger rows
The entrance is `rl ql open` after gyb names the lane (assigns a tag, creates the worktree, records the scratch row); the exit is `rl ql close` (merged back or dropped, one row each); everything in between lives in the worktree and the scratch ledger. The quick lane is not deploy's alone: analysis wanting to show gyb a figure first takes the same lane, except that merging back (`--merged`) is open to deploy only; analysis's quick lane has only `--dropped`, and to keep the result it is redone on the normal path (gyb 2026-08-17, sync-inbox issue 16).

### principle-08 Documents have one authoritative place, and the later ruling wins
The rulings in section one of the build plan take precedence over the body of the design document; every ruling that overturns a line of the body goes back and changes that line with a date, so no two values remain. Rules inside the project take precedence over machine-wide rules; exceptions are written out. Corollary (second round): anything enumerable is written once in the build plan and the design document points to it without copying; wherever the two documents said the same thing twice, the second round merged them into one place. gyb 2026-08-18: once the split part files are finalized one by one they are the authoritative place, the two source documents are never written back to again and each opens with a line saying it has been superseded and is kept as history; where a part file and a source document disagree, the part file wins.

### principle-09 Every order and every run has an explicit chain back to a decision
(Added in the second round.) Launch orders and analysis orders record their parent order and inherit its decision references and batch at open. A launch order carries run_id, track and config; run copies them and never guesses. `rl trace` prints the whole chain from any id, run to launch order to work order to every decision version, in one command. Every decision in the decision tree records its root decision; when two research lines run in parallel they are cut apart by root decision.

### principle-10 A launch order is a container for several attempts
(Added in the second round.) One launch order may run several times: smoke fails, launch fails, the run crashes, it is fixed and tried again; each time is one attempt on the order with its own command, step table, estimate and run row. The estimate counts only the latest attempt. The runs ledger by default lists only the latest attempt's row per order, and only when its exit status is ok, so an order whose latest attempt is not ok does not appear. Actual time is computed by `rl run finish` from timestamps, whatever the exit status.

### principle-11 Dispatch does not occupy a terminal
(Added in the second round; replaces the earlier sentence under principle 3 that a subagent takes an order synchronously by default.) After the upstream role opens an order it starts a subagent in the background to take it; the upstream session stays usable, and when the subagent returns the upstream accepts. If the upstream session ended first, the order waits on the ledger as usual for the owner's next session or for gyb to accept. The GPU task itself runs in tmux and does not follow any session: if the run session dies the order is released back to todo, and the next run session taking the order finds the latest attempt already launched but not finished and adopts it (no new smoke, no new launch, only taking over the watchdog and the finish). Waiting for hours happens only in tmux, never in any session.
