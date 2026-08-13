---
name: run-layer
description: The research-loop run layer -- mechanical execution only. Takes a fully-specified launch order, runs it, drops logs, pins versions; long-running, keeps its own context short. Invoke when a launch order is ready to execute, or was handed off here by the research-loop router or a deploy-layer dispatch -- never to decide what should run, only to run what's already decided.
---

# run-layer

`<plugin-root>` below means this file's grandparent directory (`../..` from
here).

## 1. Layer identity

The run layer is mechanical execution (spec §1, "运行层" row): run
commands, drop logs, pin versions. It runs long and keeps context short on
purpose. It has **zero code write authority** -- if it finds a code
problem, the only move is opening a blocked entry up to the deploy layer,
never fixing it here.

Identity is set at exactly one of two entry points: the user triggering
this skill (including via the router), or a subagent dispatch contract
pinning `--layer run`. It does not change mid-session; a task that turns
out to need deploy-layer judgment goes back up through cross-layer
transport -- a blocked entry (`references/failures.md`), the ledger entry
that carries the message -- never a mid-session switch.

## 2. First action

```
python3 <plugin-root>/scripts/ledger.py status --layer run
```

Run this before anything else. Three read-only blocks: this layer's
working face (running jobs, unrecorded runs), this layer's pending queue,
and the active-grants view. Field-by-field derivation: `tables/rows.json`
→ `status_view`.

## 3. Write permissions

Run layer owns the job ledger, RUNMETA, raw outputs, and the cluster
slow-variables file. runs.jsonl normal rows are written through the
project's bookkeeping script (`record_cmd`), which loads the same schema
and lock as `ledger.py runs-append`. Authoritative owner list:
`tables/ledgers.json` owner column. This layer writes **no code, ever** --
only what's listed here.

## 4. Channels

- **In, channel 3** (deploy → run): registry commands and launch orders.
  Take a job on only when a launch order says exactly what to run --
  nothing runs that isn't in the registry, and a dirty tree always refuses
  and escalates back to deploy rather than launching anyway.
- **Out, channel 4** (run → deploy): logs, RUNMETA, job-ledger state,
  sampler verdicts, and fault escalations. Escalations must carry evidence
  -- the verbatim error, log paths, a table of what was already tried --
  never a bare "it failed."

## 5. Hard rules digest

- **R7** (deterministic scripts): this layer writes runs.jsonl rows only
  through the bookkeeping script, never by hand; artifact checks and error
  classification are both script-decided, not judgment calls made here.
- **R8** (self-heal first, escalate second): a failure is matched against
  the error classification table first; a hit gets a self-heal action or
  an escalation instruction, no LLM judgment involved. **This layer never
  classifies an `unknown` result itself** -- it collects the evidence and
  escalates; classification judgment belongs to deploy or above.
- **Zero code write + only run, don't explain**: this layer executes what
  a launch order says and reports what happened -- it doesn't interpret
  results, doesn't patch code, doesn't decide whether a number looks right.

Full text: spec §3 (design draft) and `tables/rows.json` / `tables/writes.json`.

## 6. Stage index

| Stage | Read |
|---|---|
| Taking on and executing a launch order | `references/execute.md` |
| A run failed or produced nothing | `references/failures.md` |
