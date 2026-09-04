# Pressure scenarios for the five role skills

<!-- Source: proxy decision D-19 (scenario prompts live here, one file per scenario under <role>/; run results are summarized outside the plugin, raw transcripts stay outside the repository); 30 section 2 test 13 and the writing-skills method (baseline without the skill first, then with the skill, record the rationalizations verbatim). Every scenario targets the third layer of constraint (principle-02): what the hook and ledger validation do not enforce. A scenario that the hook or `rl` would refuse anyway proves nothing about the skill and is not written. -->

## What a scenario is

One file, one discipline, one prompt. Each file has the same sections: the role, the discipline under test with its source line, the fixture the sandbox must be in, the prompt given verbatim, the pressure the prompt applies, the failure the baseline is expected to show (with the simulation friction that recorded it), and the observable pass criteria for the run with the skill.

## How to run one

1. Never in the research repository itself. Use a throwaway repository under a temporary directory: run `rl init` there from a bare terminal, then seed the ledgers the fixture section asks for through `rl` commands, never by editing files under `loop/`.
2. Baseline: a general-purpose subagent with no research-loop skill loaded, the same model the role json names for `as_subagent`, the prompt verbatim, working directory the sandbox. Record every rationalization it writes when it crosses the discipline, word for word.
3. With the skill: a subagent of the plugin agent type `research-loop:<role>` with the same prompt and sandbox. Both arms start in the same turn so they finish together.
   When the runner itself is a non-interactive session started with `-p`, set `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` first: by default such a session stops waiting for background subagents after 600 seconds, and a scenario that dispatches (the common ones, the deploy ones) would be cut off (plans/2026-09-05-research-loop-verify.md section 3.7). In an interactive runner, never answer the exit dialog with anything but "stay" while scenario subagents run; the other two choices kill them (section 3.2).
4. Judge by the pass criteria only. Read the ledgers afterwards through `rl` query commands and the sandbox tree through git; do not judge from the subagent's final message alone.
5. Write the comparison into the run summary outside the plugin; leave the raw transcripts outside the repository.

## Layout

```
tests/scenarios/
  README.md
  common/      disciplines every dispatched role shares
  idea/
  deploy/
  run/
  analysis/
  reviewer/
```
