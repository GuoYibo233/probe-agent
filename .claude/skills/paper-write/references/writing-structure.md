# Writing-structure checklist (adapted from Master-cai/Research-Paper-Writing-Skills)

> The source repo is already cloned at `related_work/Research-Paper-Writing-Skills/`;
> this file only keeps the three load-bearing pieces; model examples and the guides for other sections
> are at the paths below, use them as needed.

## I. Before drafting the introduction: work backward through seven questions

Before writing the intro, write out the answer to each of the seven questions as one line first —
**whichever question you can't answer is a hole in the story line**; fill the hole before drafting:

- [ ] What technical problem are we solving? Why doesn't an existing solution already handle it?
- [ ] What is the contribution (a new task / a new metric / a new technical problem / a new technique)?
- [ ] Why does the contribution solve this problem? What new insight does it bring?
- [ ] Which existing methods lead the reader to our challenge?
- [ ] What is the technical reason (not just the symptom) that existing methods fail?
- [ ] Why does our mechanism work at a fundamental level?
- [ ] Which claim above do the main experiment numbers support?

Draft the five paragraphs forward from there: the task and its application → existing methods leading
to the challenge (limitations + technical reasons) → our approach and mechanism → the main experiment
result → the list of contributions.
Every paragraph's first sentence must state its point directly; one paragraph makes exactly one point.

## II. Two reviewer red lines (check on every revision pass)

- [ ] **No "naive solution → we improve on it" framing.** Presenting a naive solution first and then the
  improvement makes the reader see the work as an incremental patch, and curiosity drops to zero. Never
  write it this way even when the work genuinely is incremental: jump directly from "existing methods
  fail because of X" to "our mechanism."
- [ ] **No "abstract insight only, no mechanism" framing.** The intro must contain concrete mechanism
  steps ("Specifically, ..."); piling on new terminology without explaining the mechanism gets judged as
  shallow / a novelty illusion.

## III. Related-work paragraph template

Each topic paragraph follows four steps; skip a step and it needs to be rewritten:

1. Scope sentence: what line of work this topic covers.
2. Representative work: one sentence per paper stating clearly **what it does** (not just listing citations).
3. Limitations: the limitations directly relevant to **the challenge we solve**, plus the technical reason.
4. Difference sentence: a closing sentence stating our difference from this line of work, in mechanism
   language, not promotional language.

2-4 topics, grouped by technical theme rather than by chronology; never hide the strongest competing work.

## IV. Paths to the guides for the remaining sections (read when you get there)

| Section | Path (relative to related_work/Research-Paper-Writing-Skills/research-paper-writing/) |
|---|---|
| Abstract | references/abstract.md + examples/abstract/ (three templates) |
| Method | references/method.md |
| Experiments | references/experiments.md |
| Conclusion | references/conclusion.md |
| Flow | references/does-my-writing-flow-source.md |
| Self-review | references/paper-review.md |
| Intro example library | references/examples/introduction/ (13 examples) |
