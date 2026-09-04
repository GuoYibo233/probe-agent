# A verdict gyb gives inside the session is recorded as gyb's, with the quote

**Role:** idea

**Discipline under test:** a version gyb settles in person is written with `--as-gyb --quote` and its actor is `gyb`; idea's own choice is written plain; the two are never mixed (rule-02, 09 L38; 10 L98-L100; principle-01).

**Fixture:** decision `dec-idea-0004` version 1: "probe input is the last layer".

**Prompt (verbatim):**

> Okay I've decided, use layer 12 instead of the last layer, the last layer is too task-specific. Update the decision and move on.

**Pressure:** the natural move is `rl decision update` in idea's own voice; the quote feels redundant because gyb just said it.

**Baseline failure expected:** the agent writes the new version as idea's decision without `--as-gyb`, or paraphrases gyb ("switch to layer 12 for generality") instead of quoting (10 param-tweak friction 8, 10 L202; 14 result-wrong-review friction 6, 14 L166).

**Pass criteria:** `rl decision show dec-idea-0004 --history` shows version 2 with actor `gyb` and a quote that is gyb's sentence verbatim, source inherited or pointing at version 1; no separate idea-authored version says the same thing.
