# The user wants the whole set at once, skipping lesson-by-lesson calibration

On 2026-08-04, after Lesson 2 went out, gyb said "don't worry about my quiz answers for now, just publish all the lessons."
So lessons 3 through 5 were written and published in one batch, without adjusting difficulty based on how he had answered.

## Evidence

- Five for five on Lesson 1 (see [[0002-lesson-1-full-marks]]); he asked for the rest without answering Lesson 2's quiz at all.
- His pattern of use looks like "stockpiling as reference material," not "working through it lesson by lesson at a set pace."

## Implications

- These five lessons need to **stand independently**: opening any single one on its own must still make sense; none can depend on
  "we just covered this in the last lesson." Lessons 3 through 5 all restate the prerequisite concepts they use at the start; links are supplementary, not required reading.
- Since there is no lesson-by-lesson calibration, difficulty is set uniformly at the level where Lesson 1 went five for five, with no more probing lesson by lesson.
- Reference cards need to carry more weight; someone stockpiling material for reference flips through the cards, not the lessons.
  So this batch added `reference/request-params.html`, and all three cards were published as separate artifacts
  (a local link inside a lesson page is dead on the artifact; a card needs its own URL).
- If more lessons get added later, still pick from the candidate list in `NOTES.md`, but the default is to deliver the whole batch at once rather than waiting for feedback again.
