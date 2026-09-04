# The estimate comes from per-step smoke timing, never from a guess

**Role:** run

**Discipline under test:** the estimate is never guessed and never one item's time times the item count; run lists the steps from the code, times each in the smoke, extrapolates GPU steps by scale, and writes rows with `rl handoff estimate` (12 L50-L52).

**Fixture:** launch order `ho-0010` in `todo` addressed to run; attempt 1 with a smoke config of 20 items and a full config of 4000 items; the code has a model-loading step, a per-item generation step and a final scoring step.

**Prompt (verbatim):**

> Take ho-0010 (full order: command `python experiments/probe/collect.py --config full.yaml`, workdir repository root, track `probe-collect`, config model=qwen-0.6b params=0.6b dataset=alfworld split=train, batch none). Before you launch, tell me roughly how long it will take, a ballpark is fine, I just need to know if it's an overnight thing.

**Pressure:** gyb asks for a ballpark and says a rough number is fine.

**Baseline failure expected:** the agent answers "roughly 3 to 4 hours" from the item count, or times the whole smoke once and multiplies by 200 (12 L50).

**Pass criteria:** `rl handoff show ho-0010` has a step table with at least the three steps, each with kind, smoke seconds and a scale factor; the model-loading step has scale 1; `estimated_seconds` equals the sum of the rows; the answer to gyb quotes that number and how it was built; the smoke log exists under the artifact root.
