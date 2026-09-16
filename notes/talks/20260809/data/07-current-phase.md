# What the current phase has in hand

Source: the working tree's `METHOD.md` (finalized 2026-08-08), `RESULTS.md`, `WORKPLAN.md`.

## The method's characterization changed: from a fixed method to an experiment space

The main loop is fixed (the agent does the task in the environment step by step; when the thinking advances to a
sentence cut, a side-channel probe looks at the prefix; when the trigger rule says fire, it produces the predicted
tool call and gets a result; the result is fed back into the cut as text; the model keeps writing). Eight other axes
are queued for trying: what the probe reads, what model the probe uses, where parameters come from, the trigger
rule, what gets fed back, when to feed it back, how to split tool types, and when to stop within a single step.

Two hard rules override every axis: the same-setup rule (baseline and method use the same set of settings, checked
by the no-probe control) and injection-format equivalence (the injected content, at the token level, is fully
equivalent to thinking the model wrote itself, broken into four criteria, R1 through R4). θ is always given by
hand, if it is not given, startup is refused.

The current instantiation: gpt-oss-120b + AppWorld, the live-run driver `pipeline/inject/live_appworld.py` plus the
probe server `pipeline/inject/probe_server.py`.

## The current ledger has only one run, and it verifies the infrastructure, not the method's effect

Run `hcap` (2026-08-06): verified that a client assembling harmony by hand over /v1/completions is end-to-end
equivalent to the chat path (for the same set of messages, the prompt and output token counts, and the reasoning
and content, match exactly, character for character), and captured a real token-by-token stream for 13 steps of one
AppWorld trajectory, of which 3 steps hit the 8192-output cap.

## What's queued next (`WORKPLAN.md`)

1. Deployment session: make all four alignment items match per `METHOD.md` §6, then run a 2-question smoke test,
   and check off three things (every fire can be pinpointed, the R3 token comparison, the no-probe control).
2. Direction session: discuss new ideas on the axes (new schemes for what to feed back, having the probe read
   hidden state instead, splitting tool types into read-only and write).

The current phase has not yet trained any probe, and has no method-effect numbers of any kind.
