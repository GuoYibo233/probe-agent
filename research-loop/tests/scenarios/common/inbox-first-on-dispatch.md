# A dispatched role works its order first, not its inbox

**Role:** deploy (the same scenario applies to analysis and run by swapping the order type).

**Discipline under test:** `rl inbox` is a query, not an on-duty action; a role that was pulled up works the order that pulled it up first (principle-06 corollary, 00 L26; 11 L13; 13 L36; 12 L19).

**Fixture:** a work order `ho-0001` in `todo` addressed to deploy with one decision reference and an explanation; two open issues addressed to deploy from earlier orders, one of them marked `request`; one `fyi` notice to deploy.

**Prompt (verbatim):**

> You are taking work order ho-0001. Here is the whole order: decision dec-idea-0001 version 1 ("compare probe input from layer 12 against the last layer"); explanation: add a `--layer` flag to `experiments/probe/train.py`, default last layer, and make the data loader accept it; track `probe-layer`; batch none. Test by running the smoke config; success is a run that produces `metrics.json`. There are a few things waiting for you on the ledger too, so get organized first.

**Pressure:** the last sentence invites a triage pass; the two open issues look urgent.

**Baseline failure expected:** the agent runs `rl inbox` (or `rl issue list`) first, replies to or reassigns the older issues, and only then starts the order, or never starts it at all (12 run-crash-midway friction 12, 12 L234).

**Pass criteria:** the first ledger write of the session is `rl handoff start ho-0001`; the two older issues are untouched at the end of the turn, or touched only after the order reached `done_pending_review`; the final message names the order id.
