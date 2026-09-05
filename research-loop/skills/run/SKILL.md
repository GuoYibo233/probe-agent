---
name: run
description: Use when gyb has assigned this session the run role of the research loop, by loading this skill in person or by starting a run subagent from a launch order. Not for any other request.
---

# run

<!-- Sources: 12 L9-L15 (what run does, model, hook), 12 L19 (no inbox), 12 L23-L27 (start, adopt, batch), 12 L31-L40 (the eight phases against gpu-run), 12 L46 (gpu state, free GPUs, picking), 12 L50-L56 (smoke and step timing), 12 L60-L64 (commit and launch), 12 L68-L76 (the three run versions), 12 L80-L94 (watchdog and anomaly), 12 L98-L113 (the four failure issues), 12 L117-L129 (finish and interrupt), 12 L135-L137 (withdrawn, reclaimed, session end), 12 L143-L149 (json), 12 L161 (host relation), D-13 (a role loads only on gyb's word). -->

gyb assigns roles. If gyb has not named this session as run and no launch order dispatched it, stop here and say so.

## 1. Role definition

run watches the servers, launches and finishes long-running experiments, and reports problems. It takes one kind of order only, the `launch_order` deploy opens. run never writes code, never fixes code and never retries: every problem becomes an issue to deploy, and a redo is the next attempt on the same order. run is small and fast. One GPU per run; several GPUs for one job is the exception.

For a session that loaded run, this skill is the whole of the host's GPU procedure: the host's "single entry point" rule reads as this skill. The host's own record layers are never touched by run; only `rl run finish` writes the host's run ledger through the configured finish command.

Started by deploy as a subagent from a launch order, or by gyb loading this skill. As a subagent the model is opus; loaded by hand it follows the session's model.

## 2. Use cases

| Use case | Reads | Writes | `rl` write commands |
|---|---|---|---|
| Take the launch order, or adopt a launched attempt | `handoffs`, `runs` | none | `rl handoff start` |
| Read the GPU state file, probe free GPUs, pick GPUs | `ops/gpu_state.md` | none | none |
| Smoke and fill the step table | `handoffs`, `experiments/` | `artifact_root` | `rl handoff estimate` |
| Commit, launch through the host launcher, record the launch | `handoffs` | `artifact_root` | `rl run add` |
| Watch the job | `handoffs` | `artifact_root` | none |
| Finish and deliver | `runs`, `handoffs` | `artifact_root` | `rl run finish`, `rl handoff done` |
| Report a failure and mark the order stuck | `issues`, `handoffs` | none | `rl issue open`, `rl handoff stuck` |
| Interrupted: withdrawn, reclaimed with kill, crashed | `handoffs`, `issues` | none | `rl run finish`, `rl issue open`, `rl handoff stuck` |
| Record a rare self-made decision (which GPU and why) | `runs` | none | `rl decision add` |
| Propose a change to the shared rules | `feedback` | none | `rl feedback add` |

**Take the order.** `rl handoff start ID [--batch B]` moves the order from `todo` to `in_progress` with this session as holder; it requires the session's role to be the order's target and the holder to be empty (exit 2 names the current holder). At start `rl` decides on its own whether this is an adoption: when the latest attempt already has a `launched` run row without a `finished` version, the start version records adoption and `rl` appends an `adopted` version to that run row. Read the result of start: adopted means no new smoke and no new launch, only taking over the watchdog and the finish. For a batch, one run session takes the whole batch with `--batch`: one smoke, one step table copied to the others, one probe and pick, N launches by the host launcher's own sharding, N run rows.

**GPU state, free GPUs, picking.** First read the slow-variable file `ops/gpu_state.md` (its path is the `research-loop.json` key for the GPU state file). Probe free GPUs with the configured free command, never from a cached view. Pick and shard by the host's launch methodology reference; do not rewrite it here.

**Smoke and the step table.** The estimate is never guessed and never one item's time times the item count. Read the code and list what each step does; run the smoke with per-step timing; extrapolate GPU steps by scale (loading a large model once is a GPU step counted once), ignore short CPU steps; write each row with `rl handoff estimate ID --step NAME --kind gpu|cpu --smoke-seconds S --scale F`, and for the other orders of the batch `rl handoff estimate ID --copy-from ID2 [--scale F]`. Smoke standard output goes to the smoke log under `artifact_root`, named by the run id, so an issue can point at it with `--log-tail`. A failed smoke stops here: the step table and the estimate are not prerequisites for marking the order stuck.

**Commit, launch, record.** Commit before launching, because the recorded commit is only traceable when the tree is clean; the ledger files are on the host's dirty-tree allow list. Launch through the configured host launch command; the run id and track are copied from the order's attempt, never composed: the run id is assigned by `rl` and is the artifact directory name, the tmux session name, the host ledger name and the commit message alike. On success, `rl run add --handoff ID --attempt N --commit ... --host ... --gpus ... --log ... --tmux ... --watch-cmd ...` writes the `launched` version; command, `config` and run id are copied from the order, run adds only the machine and the GPUs. The attempt number is the number of the order's latest attempt, read at start; run never counts attempts itself (proxy decision D-31). The watch command is what gyb uses to look at the job from `rl status`.

**Watch.** The watchdog is a separate process started when run comes on duty; it only judges and writes its own state file, never a ledger, and calls only `rl` query commands. This session reads the state file each round; killing processes and writing ledgers are done by this session. Stall (no new log line, no new file in the artifact directory, GPU utilisation at zero) is judged independently of the estimate; timeout is the latest attempt's `estimated_seconds` times the configured factor. Every round the watchdog also checks whether the order became `withdrawn` or was reclaimed, and if so this session runs the interrupt path.

**Finish and deliver.** In order: report; `rl run finish RUN_ID --exit ok --metric k=v ... --data-path P`, which computes `actual_seconds` from the two timestamps, runs the anomaly check in the same process, and calls the configured host finish command so the host's ledger is written too; release the GPU; the host's own sign-off; commit. Then `rl handoff done ID`, which requires a `finished` version with exit status ok on the latest attempt. Numbers enter the ledger only through `rl run finish`; typing numbers read by eye is forbidden.

**Report a failure.** Three failures go to deploy: `rl issue open --to deploy --kind failed --stage smoke`, `--stage launch` or `--stage crash`, each with the last 40 log lines and the traceback (`--log-tail FILE` or `--log-text -`) and the order id. Then `rl handoff stuck ID --issue ID`, which requires the issue to point back at this order; the issue is written first so the order can cite it. After marking stuck this round of run is over: fixing, appending an attempt, replying and restarting are deploy's. A result that looks wrong on a completed run is `rl issue open --to gyb --kind anomaly`, opened by the anomaly check at finish; it does not mark the order stuck, and an order with exit status ok is still delivered.

**Interrupt.** Crash: `rl run finish RUN_ID --exit failed` (the host finish command is called as well), then the `crash` issue and `rl handoff stuck`. Withdrawn or reclaimed with kill: `rl run finish RUN_ID --exit killed` plus the wrap-up (kill, release the GPU, the configured host abort command, skipped when unset); the order's status is not changed by run, the withdrawal or reclaim already changed it. `actual_seconds` is recorded whatever the exit status.

**Withdrawn while holding.** The half-finished artifact directory under `artifact_root` stays in place for gyb to decide. Answering the `withdrawn` notice with its path, as deploy and analysis do, needs an issue reply that run's ledger writes do not include: PENDING(issue 50).

**Session end.** The hook releases orders this session holds back to `todo` with an `orphaned` notice to the owner. A launch order whose latest attempt is `launched` and not `finished` keeps its process running for the next run session to adopt; hours of waiting happen only in tmux.

**Self-made decisions.** Rare, for example why a particular GPU was chosen: `rl decision add` in run's own ledger. Where run reads its own decisions back: PENDING(part 12 L178).

## 3. Available tools

Reads, writes, ledger write commands and dispatch targets for this role are in `research-loop/tables/roles/run.json`.

## 4. Constraints

- run does not check the inbox: it works the one order that dispatched it. `handoffs` is read for that order only; `issues` for those addressed to run.
- run writes only under `artifact_root`, outside the repository; the host launcher's own ledger writes are not run's writes and are let through.
- run dispatches to nobody.
- Copy run id, track, command and `config` from the order; never compose them.
- Writes the hook cannot see (a script writing files internally, `python -c`, heredocs, any Bash command whose target path the hook cannot parse) never go into the four role directories or `loop/`; to write there use Write/Edit or a Bash form the hook can see, and ledgers only ever go through `rl`.
- One session loads one role. To switch roles, open another session. The machine does not enforce this; what happens on a second load in the same session is undefined and has no fallback.
- In the exit dialog choose to stay, never to move the session to the background: a moved session gets a new id with no role state, and the old id's session end has already released its orders; the other two choices kill any dispatched subagent; after a move, load the role again and continue (proxy decision D-20; plans/2026-09-05-research-loop-verify.md sections 3.2 and 3.4).
- In Bash do not change directory; write every path from the repository root, because the hook judges a relative path against the shell's current directory (plans/2026-09-05-research-loop-verify.md section 7.4; proxy decision D-30).
- Follow `common/`.

## 5. Output style

run produces the step table and estimate on the attempt, a `launched` run row with host, GPUs, log path, tmux session and watch command, a `finished` run row with metrics and data path written by the finish command, `failed` issues with log tails, and a delivery on the launch order. Its report to deploy names the run id, the exit status and where the artifacts are.
