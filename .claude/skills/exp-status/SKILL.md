---
name: exp-status
description: >-
  Explain "where this project currently stands" until the user actually understands it,
  then commit it to a document and a web page. Engineering-side inventory of experiments
  already run; does not look at external literature. Workflow: set the scope → the main
  conversation reads the three-layer ledger itself
  (TIMELINE/RESULTS/runs.jsonl/jobs.json/plans) → walk through it block by block and check
  the user actually understood (ask "which word tripped you up," not "did you get it") →
  finalize and write to plans/STATUS_*.md (the whole document split in half: the top half
  is all facts, the bottom half is all interpretation, no switching back and forth. Each
  experiment carries a paragraph of natural-language experiment description: how it was
  done + why this design counts + one real sample freshly pulled from the raw data +
  anything worth noting, with no command lines or parameters) → self-check (including
  mechanical verification: grep every number in the bottom half back against the top half,
  hand-recompute every count) → dispatch a swarm of sonnet subagents to check section by
  section for "is there a word you don't understand," plus one checker whose only job is
  to verify the arithmetic (given only the preceding text, no background, run until hard
  items hit zero new findings) → render to an artifact with a deterministic converter and
  verify it character by character (not a single character may change). A second run on
  the same line goes into "update mode": only the changed sections get sent for review.
  Five hard rules apply throughout: facts and interpretation are separated with facts
  first, every number carries a referent and a source, describing an experiment quotes the
  original text, no sentence component is omitted and every concept word must be welded to
  something concrete, and the tone is plain and rigorous colloquial speech. humanizer-gyb
  is also mandatory. Invoke when the user asks "where are we" or "experiment status."
  Chinese triggers: "现在跑到哪了" / "我们现在什么情况" / "盘点一下实验" / "捋一遍实验" / "做了哪些实验" / "实验现状" /
  "研究现状" / "复盘一下" / "出个状态书" / "现状图".
version: 1.1.0
---

# exp-status: explain the project status until the user understands it

This skill answers one question: **what experiments has this project run, what did each one conclude, and what's still missing.**

Engineering side only, looking only at our own ledger. Wanting to know what other people out there have done is the job of `update-knowledge-map`; don't do that here.

Produces three things, in an order that must not be reversed:

1. A written version the user has **accepted block by block and actually understood**, saved to `plans/STATUS_<YYYYMMDD_HHMM>_<slug>.md`
2. Every experiment in the written version carries an **experiment description** — plain language explaining how it was done and why this design counts, so that an outsider reading only it could redesign the same experiment
3. An artifact, rendered by a subagent from the finalized written version, not a single character changed

## Why this skill exists (not just a formality)

There's already a `plans/archive/STATUS_20260730_1833_all_lines.md` in the project (retired and archived). It was complete and the numbers were accurate, and the user couldn't understand it. The reason wasn't the user: the body was packed with `best_calA_weighted_acc`, `θ=0.8 v2fix`, `Sp@k`, `L2minus`, and two dozen commit hashes, each one a compressed index that the reader has to decompress before they can get to the content.

So the main function of this skill isn't "organizing information," it's **saying it in plain words**. Organizing information is just a side effect of that.

## First action: load the plain-language rules (do not skip)

Read this file in full, don't rely on memory:

- `~/.claude/skills/humanizer-gyb/SKILL.md`

This one checklist carries all the entries by itself (51 rules in five categories: words, sentences, paragraphs, the whole piece, layout); stripping out AI-tells and gyb's personal preferences are both handled in it, no need to stack another writing checklist on top. This set of rules doesn't just constrain the final document — **it applies equally to every round of explanation in chat.**

## Five hard rules that run through everything

Apply in chat, in the written version, and on the artifact, without exception.

### One: facts and analysis are separate, facts first

**First honestly report what the experiment actually measured, interpret only at the end. No evaluative word may appear in the experiment-results section** — words like "shows," "proves," "surprising," "beyond expectations," "the cleanest tier," "the easiest to misread" are all banned there; save them for the interpretation section.

Reason: once facts and interpretation are welded together, the reader has no way to accept the facts without also accepting the interpretation. Interpretation can be argued with; facts can't. Mixing them forces the reader to swallow the interpretation along with the facts. The writer also loses sight of the fact that a conclusion might not actually be backed by numbers.

**Test**: delete the whole interpretation section. What's left should stand completely on its own, without changing a single character. If you need to change a character, that means evaluation has leaked into the facts layer.

### Two: every number must be traceable to a source, and must say clearly what it refers to

For every number that appears in the body text, the reader must know two things on the spot: **what it refers to**, and **where it came from**.

- **Written version**: use parentheses right after the number. Write it as "Episode 0 (the first of ten consecutive episodes, when memory is still empty) took 5 steps on both sides, read in 2901 tokens, and wrote out 3765 (in the raw record, the `steps`/`tokens_in`/`tokens_out` fields, one copy each for memory-on and memory-off, seed 0's first entry)."
- **Artifact**: attach a clickable or hoverable annotation to the number, with content matching what's in the written version's parentheses. Don't just pile an attribution table at the bottom of the page — the reader must be able to look it up the moment they see the number.

**Sequence numbers need the same treatment.** The reader doesn't know whether "episode" counts from 0 or from 1, or whose "5 steps" this is. The first time such a sequence number appears, spell it out in parentheses.

**Whenever a raw field name is written out, you must also say clearly what that field holds.** Just throwing out `tokens_in` isn't enough — the reader can't tell from the name alone whether it counts the prompt length for one step or the summed prompt length for every step in the episode, and the two can differ by a factor of ten or more. Write it as "read in 2901 tokens (the raw record's `tokens_in` field, which holds the summed prompt token count across every step in this episode)."

The role of a field name is to let someone look the same number up in the raw file — it's a key, not an explanation. Both the key and the explanation must be given.

### Three: quote the original text when describing what the experiment does

When describing what this experiment is actually doing, **quote the original wherever you can**: the task's original English sentence, the exact string from the prompt template, the model's actual output action sequence — paste them verbatim and mark which file they came from.

Reason: a paraphrase can't be checked by the reader, and paraphrasing quietly changes meaning — the difference between "put the paper on the shelf" and `put a toiletpaper in toiletpaperhanger.` might be exactly where this experiment succeeds or fails. With the original text pasted in, the reader can judge for themselves.

Never translate the original text. If it needs explaining, write a separate explanatory sentence below the original — don't replace the original with a translation.

### Four: don't omit sentence components, don't leave an unexplained concept word

**Every sentence's subject, verb, and object must all be present, and no modifier may be omitted.** A reader can only guess at an omitted component, and a wrong guess flips the meaning of the whole sentence.

**Any concept word must be made concrete on the spot, or annotated on the spot.** Just writing "evidence" won't do — write "evidence **of what**," and that "what" must be concrete enough to be checked.

- ❌ This is direct evidence of seed alignment.
- ✅ This is direct evidence that "the memory-on run and the memory-off run got the exact same task order": episode 0 (the first of ten consecutive episodes) has identical digits between the two runs, and that can only happen if the order is identical.

**Self-coined abbreviations may never be used bare.** Words like "input tax" or "memory hunger" must either be spelled out in a full sentence on the spot explaining what they refer to, or not used at all. Using one without explaining it makes the reader think it's an already-established formal concept, and they'll read on with whatever meaning they've guessed at.

**Test**: circle every abstract noun in the draft — evidence, signal, criterion, dividend, upper bound, variance, transfer, tax, hunger. Every circled word must either be immediately followed by "...of ___" welding it to something concrete, or have a parenthetical explanation right after it. Not one may be left bare.

### Five: tone — plain, rigorous, spoken language, like an expert talking face to face

Write the whole thing in **sentences as spoken**, not sentences as written. This matters especially when explaining something — the moment an explanation puts on a written-register voice, the reader first has to translate the written language back into ordinary speech in their head before they can start to understand, which is an extra barrier for nothing.

**Test: read it aloud.** If it sounds awkward, if it doesn't sound like something a person would say, that's written-register — rewrite it.

Specific to word choice:

- Replace written-register connectives with spoken ones. "Therefore" becomes "so," "however" becomes "but," "moreover" becomes "also," "in summary" becomes "so overall."
- Tear down any "carry out / conduct / perform + verb" construction. "Carry out verification" becomes "check it," "provide clarification" becomes "make it clear."
- Cut every four-character written-register stock phrase: "of the utmost importance," "cannot be overlooked," "at a glance," "proven effective," "self-evident" — all deleted.
- Split long modifiers into two sentences. A sentence with three layers of "that" nested inside it runs out of breath when read aloud.

**An expert's tone is: no pleasantries, no preamble, no false modesty — state the conclusion and the basis directly.** Don't write "as we can see," "it's worth mentioning that," "next let's look at" — say what you mean to say, directly.

**"Spoken" is about how the sentence is put together, not about the content being allowed to be vague.** Numbers, units, and qualifiers can never be dropped just because "it sounds smoother" — rule four still governs this. Plainness and rigor coexist: the words are everyday speech, the facts are nailed down.

## Phase 0: set the scope

Ask one question, then stop and wait for the answer: is this round **the whole picture** (every experiment the project has run to date), or **one line** (a given topic or a given run prefix)?

Reason: the whole picture and a single line differ in information volume by an order of magnitude. Doing the whole picture in detail is too much, doing one line covers too little — get the choice wrong and every subsequent round talks about things the user doesn't care about.

## Phase 0.5: determine whether this is a first run or a rerun

First check whether there's already a `STATUS_*.md` for this same line under `plans/`. If there is, it's a **rerun**, go into update mode; if not, only then start from scratch.

This step was added on 2026-07-31: that time was a second run on the same line, but the skill assumed throughout it was a first run, so the whole document got resent for review, doubling the cost, and sections already accepted in the previous version got reported all over again.

**How to run update mode:**

1. Read the previous `STATUS_*.md` in full, note its timestamp, and diff the ledger only from that point forward (`git log`, new lines added to `ops/runs.jsonl`, artifact files newer than that timestamp).
2. **Sections already accepted in the previous version that weren't changed this time are not sent for review again.** They already passed; reviewing them again would only report the same soft issues again.
3. Only send two kinds of section for review: newly written this time, and changed this time.
4. The new version's markdown **is created as a new file under the new timestamp** (`plans/STATUS_<new timestamp>_<slug>.md`), not overwriting the old one — the old version is history, the same principle as `runs.jsonl` being append-only. Open with a line saying which version this replaces and what's new.
5. The artifact **must reuse the same HTML file path**, so the URL doesn't change. The user finds the page by that link — changing the URL loses the page for them.

## Phase 1: the main conversation reads the ledger itself

Read these, all at the project root:

- `TIMELINE.md` — why things were decided the way they were
- `RESULTS.md` — the rendered numbers (read-only, never hand-edited)
- `ops/runs.jsonl` — the raw record of the numbers, keyed by run_id
- `ops/jobs.json` — the job ledger, what's running, what's finished
- the most recent `STATUS_*.md` and plan files under `plans/`
- `git log --oneline` (the most recent thirty to fifty)
- `plans/PLAINWORDS.md` — the sticking-point word list, see Phase 2; if the file doesn't exist, this is a first run

**The main conversation reads these itself, does not dispatch a subagent to read through them.** These few files add up to a few hundred lines; reading them yourself costs far less than the distortion cost of explaining from secondhand notes, and every subsequent round of explanation needs to check back against the raw numbers at any time — you only know where to look if you've read them.

The subagent does exactly one dirty job: digging scattered numbers and experiment settings out of NFS run directories and logs — flipping through dozens of files and reporting back only the essentials, which is the most cost-effective use of a subagent. **Any number it reports back is marked "reported by an agent," and the main conversation must personally open the original file and check it before putting it into the written version.** A subagent's numbers fabricate just as easily as a search summary's do, and it fabricates the single most load-bearing number in particular.

Whatever isn't in the ledger doesn't exist. Never fill in a plausible-looking number by inference.

## Phase 2: explain block by block, verify understanding (the core of this skill)

This isn't a report, it's teaching. Each round covers exactly **one block**: one experiment, or one conclusion.

Each round has two fixed parts, with a clear boundary between them, body text under 300 characters:

1. **What the experiment measured** — facts only. Every number followed by a sentence on what it refers to and how it was measured. No evaluation of any kind in this part.
2. **My interpretation** — open by saying explicitly "here's my interpretation." What these numbers show, where it's shaky, where it's still uncertain.

The boundary must let the user see at a glance where the facts end. The first part is what they can trust directly; the second part is what they can argue with me about.

### Terminology rule (hard rule)

- Introduce **at most one** new term per round; explain it in plain language first, with the term attached afterward as a label.
- **run_id, commit hashes, and file paths do not go into the body text.** They're an index, not content — put them all in a single "Index:" line at the end of this block.
- **A metric field name is never used bare.** The body text writes "weighted accuracy on the calibration set"; the raw field name `best_calA_weighted_acc` goes in the index line, along with a sentence there on what it holds.
- An abbreviation coined earlier in this same conversation, reused in a later round, counts as its first appearance again — either redefine it, or don't use it.
- One entity gets exactly one name for the whole session, never switch words or use a nickname ("graduated," "opened fire," and the like are all banned).

### Acceptance actions (do not skip)

- **Ordinary block**: ask "which word in this block tripped you up." Never ask "did you get it" — asking "did you get it" only ever gets "yes."
- **Load-bearing block** (this block's conclusion decides what happens next): ask the user to restate the conclusion in their own words. Listen, point out any deviation first, and if there's no deviation say so explicitly — don't let a misunderstanding slide by out of politeness.
- **User says they don't understand**: never just repeat the same sentence. Re-explain with a shorter causal chain, and record the word that tripped them up in the sticking-point word list.

### What to do when the user isn't present (offline mode)

In reality there are plenty of cases where "the user said just do it, then walked away." Phase 2 can't run in that case, but you must not pretend it ran.

- Phase 2's acceptance duty is substituted by Phase 4.5's checker — the checker is "a reader who never heard the explanation," and the words it reports as not understood are equivalent to the words the user would trip on.
- **The produced document must state at the top that "this version has not been accepted block by block by the user."** Without this sentence, the reader will assume it passed that gate.
- Next time the user is back, pick the two or three blocks the checker flagged most heavily and walk through them in person, filling in the missed acceptance step.

### Sticking-point word list

`plans/PLAINWORDS.md`, four columns, append-only:

| Original term in the project | The one name used throughout | Aliases that are always a violation | Aliases that depend on context |
|---|---|---|---|

The last two columns must be kept separate — this is a lesson learned in practice on 2026-07-31: at the time a three-column table had 139 banned aliases, and a mechanical search hit 31 words, of which only 7 were real violations. All the false positives came from words like "data," "eval," "once," "precision," "launch" — words that **are only a violation in a specific context** — mixed into the same column, drowning the search results.

- **Aliases that are always a violation**: wrong wherever they appear, mechanical search only runs against this column, fix on any hit.
- **Aliases that depend on context**: this word has other legitimate uses (e.g. "launch" meaning launching a GPU job is legitimate, but meaning a probe firing is a violation) — search for it, but have a human eyeball the results.

Read it first every time this skill runs. For words already read, use the name already settled on — don't reinvent it every time. This is the only way to prevent the same word from tripping people up repeatedly — once the user has gotten stuck on a word, they shouldn't get stuck on the same word a second time.

The third column, "banned aliases," is for Phase 4.5's string search; its role is explained in that section. Fill in this table before writing the written version, don't go back and patch it in after writing is done.

## Phase 3: write the document to disk

Path: `plans/STATUS_<YYYYMMDD_HHMM>_<slug>.md`.

**Split the whole document in half, the top half all facts, the bottom half all interpretation.** Never switch back and forth between experiments — never lay it out as "experiment 1's numbers, experiment 1's interpretation, experiment 2's numbers, experiment 2's interpretation." Only after every experiment's numbers are laid out does it become my turn to speak.

Put a clear boundary between the two halves, stating "everything above is what the experiments measured, everything below is my judgment, and it can be argued with."

**The space allocation is fixed: facts take up the vast majority, my words take up only the last section.** What the experiments did and what they measured has to be spelled out experiment by experiment; once it's my turn to make a judgment, write it in one section. If the writer's own words end up longer than the experiment facts, the document has gone wrong.

### Top half: facts (five sections, the main body is here)

**Section 1 · What experiments were run in total.** One line per experiment: what question this experiment asked, whether it finished. Let the reader know the total count of things first, before going into detail.

**Section 2 · Detail on every experiment.** This is the main body of the whole document, one entry per experiment, six items inside each entry, in this fixed order:

1. What question this experiment asks
2. How it was done
3. Why this design counts (the judging criteria were set before the run started, which counts as setup, not as interpretation)
4. One real sample
5. Experiment results: pure numbers, each number with a referent and a source, **not a single word of evaluation allowed**
6. ⚠ Worth noting: setup details

**This section must not be compressed.** Cut your own words to save space; never cut the experiment's facts.

**Section 3 · Numbers side by side.** Lay side by side the numbers from different experiments that are comparable, showing only, not commenting. Which is higher and which is lower is visible to the reader on its own; they don't need to be told what it means.

**Section 4 · Decision record.** Taken from `TIMELINE.md`, each entry writes only two facts: how the decision was made at the time, and which experiment later produced what number. **Don't write "so that decision turned out right or wrong"** — that sentence belongs in the bottom half.

**Section 5 · Ledger status.** Which experiments finished, which are still running, which haven't run, which failed, which lost data. All checkable facts, one line per item.

### Bottom half: interpretation (just one section, at the end)

**Section 6 · My judgment.** Say everything here: what these numbers show, what the conclusion is, how far each research question got answered, which earlier decisions got overturned, where it's shaky, what needs to be filled in next.

A few constraints:

- Open by stating explicitly "everything below is my judgment, and it can be argued with."
- Every judgment must point back to a specific number in the top half, so the reader can flip back and check.
- When saying a research question was answered, say clearly which half was answered and which half was never even tested. "Partially supported" with no follow-up is banned.
- **A decision that's already been overturned by the numbers, but that `TIMELINE.md` hasn't recorded yet, gets called out separately** — that's a hole in the ledger.
- This section must not be longer than section 2. If it is, that means there's too much talk — cut it.

### Why the whole document has to be split, not split experiment by experiment

If a single experiment is split internally, by the time the reader finishes reading experiment 1's interpretation, my judgment is already loaded into their head, and when they go look at experiment 2's numbers, what they see isn't clean numbers anymore. Splitting the whole document lets the reader read through all the numbers in one go, form their own view, and then come compare it against my view to see where they differ. That's the entire point of the split; splitting it incompletely is the same as not splitting it at all.

The written version is self-contained: anyone (including the next session with its context compressed away) can pick up the current state by reading only it.

### How to write the experiment description (items 2 and 3)

There's only one standard: **someone who has never been involved in this project, reading only this description, should be able to redesign the same experiment themselves.**

Write it as flowing natural-language paragraphs, not a field table. **Don't write in command lines, file paths, weight paths, or hyperparameter values** — those already live in the code and the ledger; bringing them in here only turns the description into a config file, and the reader still won't know what this experiment is actually doing after reading it.

Two things need to be made clear: how it was done, and why this design counts.

**How it was done.** What data was used, how many items, how it was split; which model (name and size, not path); what's being compared against what; how many times each condition was repeated, and what guarantees the resulting difference isn't random noise; and finally, which number was measured, on which batch of data. Write until "an outsider could repeat the process back."

**Why this design counts.** Three things must be covered:

- **What changes, what stays the same.** A difference is only attributable to one thing if exactly one thing differs between the two compared conditions. If two things actually changed at once, say so plainly — don't write it as if only one changed.
- **What result counts as supporting the conclusion, what result counts as overturning it.** This should ideally be decided before the run starts; if it was decided after the fact, flag that.
- **What this design can't control for.** Which factors are tangled together and can't be separated, and how far the conclusion actually generalizes.

Written like this (this example is illustrative in form; the content is made up):

> This experiment asks "does the reasoning text in the training data actually do anything." The approach was to delete the reasoning segments entirely, leave everything else unchanged, retrain, and compare accuracy on the same test questions against a model trained on the full data. The two sides differ only in "whether the reasoning segment is present." If accuracy drops noticeably after deleting it, that means the reasoning segment carries information the model actually uses; if it barely drops, that means it's just decoration. The result was accuracy dropping from seventy-five percent to thirty-four percent — a bigger drop than expected, so the eval report needs a second look to make sure it isn't the training itself that went wrong.

#### One real sample

**Pull one real record fresh from the raw data and paste it in — never make one up, never write "illustrative."** Give at least three things:

- **The input the model actually saw**: the original task text, and the actual content of the most load-bearing part of the prompt. If that content is assembled by code (e.g. stitching together experience from earlier episodes and pasting it into the prompt), reconstruct it by following the code's logic and say that it's a reconstruction.
- **The output the model actually produced**: which steps it actually executed.
- **This record's real numbers**, and whether they match the aggregate numbers.

Paste the original verbatim; English stays English, **never translate it** — a translated sample can't be checked against the raw data. Note which file it was pulled from and which entry.

**The sample must also be labeled with which run it belongs to, and where to look up that run's software/hardware configuration.** It's common for one line of experiments to run in several batches, and the inference service, GPU model, and framework version can differ across batches — numbers across batches can't be subtracted from each other. This is exactly how a problem was caught in practice on 2026-07-31: the same arm didn't match seed-by-seed across two batches, with a max difference of 121479 tokens, and tracking it down found that one batch went through a server started directly with transformers and the other went through vLLM. Just labeling "which file, which entry" isn't enough — that can't tell you the batch.

Why this section is essential: however accurate a description of the process is, it's still abstract, and what the reader imagines often looks very different from the real data. Pasting in one real sample lets the reader check at a glance whether their understanding matches; and in the process of pulling it, the writer will discover the vague spots in their own process description — if it can't be pulled out, that means it was never actually understood.

**A single sample must never be used as evidence.** It's there to let people see clearly "what one piece of data looks like." A single number not matching the aggregate number is normal — if they don't match, say so plainly and explain why the aggregate is what counts.

#### Experiment results (facts only)

Report the measured numbers, that's it. Every number carries a referent and a source per rule two above.

**The test for this section: not a single refutable sentence appears anywhere in it.** A number by itself can't be refuted; "this shows memory is useful" can be — that's interpretation, move it out. Also to be moved out: which tier is "the cleanest," which result is "more than expected," which number "needs care."

Objective comparisons between numbers can stay ("memory-on read in 2669, memory-off read in 2115"); causal statements cannot ("read in more because experience was pasted in" — that's an explanation, it belongs in interpretation).

#### ⚠ Worth noting

**Still part of the facts section**, so what's written here is the objective properties of the setup and the data, not an evaluation of them. Write "these two numbers aren't on the same basis: one counts only tokens written out, the other counts read-in tokens too" — don't write "this is the easiest place to misread."

Open a small subsection for the unusual points in this experiment. The previous two layers can be written just by following the ledger and memory; this one has to be thought through yourself: where would an outsider following the earlier description get a different result when redoing it.

- Choices that deviate from the norm, and why they were made at the time (a learning rate that was tuned, a truncation length that was changed, a default-on acceleration that was turned off)
- Patches applied to work around a known trap (pinning a specific version, turning off a certain computation path, switching a service to single-threaded) — the patch itself is evidence the trap exists
- Special handling on the data (deduplication done, ordering fixed, some category of samples filtered out)
- Basis traps: this number and the one next to it are **not on the same basis**, comparing them directly leads to a wrong conclusion
- Known impurities: code changed partway through a run, one seed's data got lost, one cell was backfilled later

Write this section in complete plain-language sentences too, never as a half-sentence like "lr=1e-5 (changed)" — an outsider can't tell what it was before the change or why it was changed. If there's nothing worth noting, write "none"; writing "none" is itself a judgment, and it only earns the right to be written after actually thinking it through.

**The relationship between the experiment description and the body text**: the body text gives only a one-line conclusion plus the key numbers; the experiment description expands on the method and the logic. Both are in plain language and both are bound by the plain-language rules — the only difference is how much detail. Neither layer may fall back to a pile of parameters.

## Phase 4: read through it yourself once it's generated

Don't hand over the written version right after finishing it — read through from the top, going item by item:

- **Does every noun get explained the first time it appears?** If not, add a plain-language sentence, or just delete the word and use a plain-language phrase instead.
- **Does the logic connect?** Can every conclusion be derived by following the numbers above it. If it can't, that means a step is missing in between: either fill in that step, or downgrade the conclusion to "still unknown."
- Go through **humanizer-gyb's quick checklist** in full.
- **Are facts and interpretation actually separated?** Delete the whole bottom half — the top half should stand without changing a single character. If it doesn't stand, that means an evaluation leaked into the top half; pick it out and move it to the bottom.
- **Is there any adjective-style judgment in the top half?** Scan every sentence in the top half; any sentence that could be refuted by someone shouldn't be there.
- **Does every raw field name come with an explanation?** Every field name that appears needs a sentence after it saying what it holds; giving just the name doesn't count.
- **Does every number have a referent and a source?** Go through each number one by one, including sequence numbers (which episode, which step). Fill in any that's missing.
- **Is every abstract noun welded to something concrete?** Words like evidence, signal, criterion, upper bound — if one isn't followed by "...of ___" and has no parenthetical explanation either, fill it in on the spot.
- **Are any sentence components missing?** Are subject, verb, and object all present, has any modifier been dropped.
- **Read the whole thing aloud.** Anywhere it sounds awkward is written-register — rewrite it into something you'd actually say, on the spot.
- **For every experiment description**: pretend to be someone who's never seen this project before — could they redesign the same experiment from it? Wherever a step can't be worked out, that step is missing. Also check for any command line, path, or parameter value that snuck in — delete it and replace with plain language.
- **For every sample**: is it really pulled from the raw data, is the source noted, can it be checked back against that source. A sample written from memory is the most dangerous thing in this document — it looks the most concrete, so it's the most likely to be mistaken for a fact.
- **Recompute every aggregate number yourself**: take the raw data and recompute the key reported numbers, check them against what's recorded in the ledger. If they don't match, either the ledger is wrong or the understanding is wrong — either way it must be tracked down on the spot before continuing.

The last two must be run with a script, never by eyeballing:

- **Grep every number in the bottom half back against the top half.** Regex out every number that appears in the bottom half, and search for each one in the top half. If it can't be found, that means the bottom half is citing something the top half never gave, and it must either be added to the top half or deleted from the bottom half. This rule was already in the skill ("every judgment must point back to a number in the top half"), but there was never an enforcement mechanism, so it got broken three rounds running on 2026-07-31 — "the previous version was 4 copies," "the task list's dependency graph," "the review only trusts real timing" all leaked through this way. This doesn't need an agent at all, regex plus grep is enough.
- **Hand-recompute every count and total.** How many rows a table has, how many "cells," "cards," "copies," "entries" a sentence claims — count and add them up one by one. All four hard errors caught on 2026-07-31 came from this step: writing three cells as four, "nine cards" not matching a ten-row table, the bottom half saying "two methods met the bar" while the top half's table showed three, and counting a still-running cell into "all failed to meet the bar." **Not one of these errors could have been surfaced by asking "which word don't you understand."**

Tell the user in one or two sentences what this pass fixed. Never fix silently.

## Phase 4.5: dispatch a swarm of subagents to review section by section (do not skip)

Self-review can't be trusted. The writer already knows what they meant to say, so their own words always read as clear to them — that's the illusion of familiarity, not real clarity. So after self-review, it still has to go through an outsider's check.

**Method: split the written version into sections, dispatch one `sonnet`-model subagent per section, all in parallel.**

### Hard rule: give it the preceding text, not the background

Each subagent receives **the section to check, plus every section before it**, plus the checklist below. **Give it no project background whatsoever** — don't say what project this is, don't explain the terms in it, don't paste code or raw data.

Give it the preceding text because a real reader reads from the top down. A word explained in section two is already understood by someone reading section five; pull section five out on its own to check, and the checker will report that word as "not understood," which is a false alarm caused by the checking method, not a flaw in the text. **This was learned in practice on 2026-07-30**: when sections were sent for review individually, four out of six checkers reported "memory-on," "cell," and "token" as not understood, even though all three had already been defined in earlier sections.

Give it no background because once given background, the checker can guess the meaning from it and report back "understood." A real reader has no background in hand. **The checker has to be as ignorant as the reader for its findings to count.**

Write the boundary explicitly into the prompt, listing both sides:

- **It already knows this, reporting it doesn't count**: model, prompt, token, random seed, decoding method, accuracy, baseline, ablation, eval set, and public model names like Qwen and Llama and public dataset names.
- **It couldn't possibly know this, and if it's unexplained that's a real gap**: names coined inside this project ("memory-on," "cell," "canonical id," and the like), self-coined abbreviations, experiment run numbers, raw record field names, self-defined metrics, numbers with no stated origin.

Use `sonnet` as the model. It understands basic domain vocabulary, so what it reports back is genuinely stuff that wasn't written clearly.

**When processing the reports, check the preceding text first.** If a reported word really was explained in an earlier section, it doesn't count, skip it; if it wasn't explained earlier, it's a real gap and must be filled in.

### What each subagent is tasked with

Send it something along these lines:

> You're an NLP researcher who has never touched this project. You already know words like model, prompt, token, random seed, decoding method, accuracy, baseline, ablation, and eval set, and you recognize public model names like Qwen and Llama and public dataset names — never report these. What you don't know are names this project coined internally, self-coined abbreviations, experiment run numbers, raw record field names, self-defined metrics, and numbers with no stated origin — report these if they're unexplained.
>
> Below is a document's full content from the beginning up to a certain section, and you have no background information beyond this and may not go look anything up.
>
> [Paste here: all the text from the start of the document to this section, marking which section is the one to focus on checking]
>
> Read it sentence by sentence, focus on checking the last section, then honestly answer:
> 1. **Which words don't you understand?** List every word whose exact meaning you can't state — including anything that looks like a technical term, an abbreviation, or an internal project name. **Don't report words already explained in earlier sections.** You should already know general domain words (model, prompt, accuracy, etc.), don't report those either. Better to over-report than let something slide.
> 2. **Which concepts are just thrown out with no explanation?** The kind of thing the author assumes you already know.
> 3. **Is there any metaphor?** List any statement that uses one thing to stand in for another.
> 4. **Which numbers do you not know the referent or the source of?** Check every number one by one, including sequence markers like "which one" or "how many steps."
> 5. **Does any raw field name appear without saying what it holds?**
> 6. **Which sentences are missing a subject, missing an object, or need two reads to tell who's being talked about?**
> 7. **Which sentences read like a written report, not like something a person would say?**
> 8. **Is there any evaluation of facts in this section?** Things like "most important," "surprising," "worked well" — judgments like that.
> 9. **Is there anything in this section called by a different name than what an earlier section used for it?** Match them one by one, list every case of "called X earlier, Y here." You only have the preceding text, so only check in this direction — report whatever you find.
> 10. **After reading it, restate in your own words what this section is saying.** If you can't restate it, say so directly.
>
> Don't be polite about it, and don't let something slide just because "you can probably guess it." If you had to guess, that means the author didn't write it clearly.

### Also dispatch a separate accounting checker (this one is the most valuable)

Besides the section-by-section checkers, **dispatch one separate subagent whose only job is to hand-recompute every count, total, ratio, and table row count in the document.** It doesn't ask about words, doesn't flag metaphors, doesn't care about tone.

Send it something along these lines:

> Use Read to read this document. Your only job is to **hand-recompute every count and total in it.**
>
> Specifically what to compute: how many rows a table has, whether the body text's claims of "how many cells," "how many entries," "how many cards," "how many copies" are correct, whether percentages and ratios divide out correctly, whether the parts add up to the stated total, whether the same number appearing in different subsections is the same value each time.
>
> Compute each one and write out the arithmetic. Say so even when it matches. **When it doesn't match, report both sides' numbers along with your arithmetic.**
>
> Don't comment on whether the writing reads well, don't flag word choice, don't flag metaphors. Only do the accounting.

Why dispatch it separately: on 2026-07-31, ten section-by-section checkers reported back over two hundred items, and not one of them caught a single counting error; a single "count it one by one" pass found four hard errors. Counting was only an incidental part of question 4 in the section-by-section checkers' prompt, and attention was already used up by the first three questions. **In terms of output density, this one accounting checker outweighs every other checker combined.**

### Triage rule: how to handle the reports (don't re-decide it every time)

On 2026-07-31, the first round of ten checkers reported back over two hundred items, fewer than 20 of them real problems, a signal-to-noise ratio of about 1:10. More effort went into triage than into actually fixing the draft. So the triage rule is fixed here, don't re-decide it every time.

**Automatically rejected, no action needed:**

1. **A substring inside a field name.** `prior_baseline_event_acc` contains "baseline," `best_calA_weighted_acc` contains "calA" — the checker reports the substring as a bare term, which is a false alarm from the search method.
2. **Content already explicitly marked as a quotation of the original.** Quotations are never changed (rule three above); if the checker reports "this sentence reads like a written report" or "there's a metaphor here" but it's inside quotes or a code block and marked with its source, skip it.
3. **General domain terms.** Words like model, prompt, accuracy, eval. The checker will occasionally still report these no matter how precisely its persona is written.

**Must be accepted, no arguing:**

1. **A count that doesn't match.** Fix it unconditionally, and go back to the raw data to verify which number is correct.
2. **A number with no source.** Either add the source, or delete the number.
3. **Evaluation, inference, or attribution mixed into the top half.** Move it to the bottom half, or rewrite it as pure fact.
4. **The same thing called by two different names in different places.** Unify them.
5. **A metaphor.** Always defer to the checker's judgment, never reject it yourself (reason in the next section).

Everything else (whether a single word is plain enough, whether a given sentence sounds like something a person would say) is handled as a soft item, see the convergence criterion below.

### How to process what comes back

- **Every word that gets reported must be dealt with, none ignored.** There are only two ways to deal with it: replace it with plain language, or add an explanatory sentence on the spot. If you feel the word absolutely has to stay, add an explanation in the written version — don't just assume in your head that "everyone should already know this."
- **A section that can't be restated must be rewritten.** A wrong restatement is more serious than an impossible one — it means that section is actively misleading.
- **After revising a section, dispatch a new subagent to re-check it** — use a fresh subagent, don't let the original one see the revised draft (it's already been contaminated by your own explanation).
- **After each round of edits, pull out just the sentences that were changed and look at them again.** Check only two things: whether the newly written words this round were defined earlier, and whether this word has already been claimed by something else. **A revision introduces just as many new problems as the original draft had, but nobody specifically checks for them.** As observed on 2026-07-31: after changing the word "reference upper bound," "upper bound" ended up meaning two different things in two sections (one meaning the most that could be saved, one meaning the most that could be put into the prompt) — a problem the first round of edits created by itself.
- **The convergence criterion has two tiers; don't hold everything to one single standard until it dies.** Split what comes back into hard items and soft items:
  - **Hard items** — whether counts are correct, whether numbers have sources, whether interpretation leaked into the top half, whether the same thing got renamed across sections. Hard items require **two consecutive rounds with zero new findings**; if that's not reached yet, keep running.
  - **Soft items** — metaphors, written-register tone, whether a given word is plain enough. Soft items **are allowed to be carried forward**, but must be listed in a "known unaddressed items" section at the end of the document, one item at a time, not buried.

  Why split them: on 2026-07-31 it took three rounds, and every round had new findings (over two hundred in round one, a dozen or so in round two, 2 in round three) — going by the literal meaning of "zero new findings" would loop forever, because the previous round's edits were themselves generating new soft items. The only thing that should actually be held to zero is hard items — those four categories are errors, everything else is style.
- **"Why is this number this particular value" also counts as a real question.** The checker often asks "why ten episodes," "why five random seeds." These questions are asking about the basis for the experiment design, which the written version should already be accounting for — don't dismiss it as noise.
- **The checker catches metaphors more accurately than self-review does.** In practice, three metaphors the writer didn't notice on their own read-through (chess terminology, trading language, describing something continuous as if it were cells) were all caught in one pass by the checker. Always defer to the checker's judgment on metaphors, never reject it yourself.

### How to check one-name-per-thing across sections (can't be done by dispatching an agent, needs three layers)

**First recognize the section-by-section checker's limits: it only gets the preceding text, not what comes after.** So a new name that shows up in section 8 is invisible when checking section 2; conversely, the checker reviewing section 8 does have section 2 in hand, and can catch "this thing wasn't called this name earlier." Conclusion: **section-by-section checking can only catch a later section changing the name, not an earlier section changing it — relying on it alone is guaranteed to miss things.**

So cross-section consistency is split into three layers, each doing what it's actually capable of.

**Layer one: settle the glossary first, write it to disk.** Before writing the written version, settle the glossary and write it into `plans/PLAINWORDS.md`, four columns:

| Original term in the project | The one name used throughout | Aliases that are always a violation | Aliases that depend on context |
|---|---|---|---|
| episode | a round | an episode, one episode | one time |
| the mem / nomem arms | solution-stored / solution-not-stored | memory-on, memory-off, with-memory, memory arm | — |

The last two columns record **words that slip out by hand while writing**, including ones used in a previous version, ones that are metaphorical, ones that just roll off the tongue in speech. Append-only, gets more accurate over time. See the Phase 2 section for why it's split into two columns.

**Layer two: run a string search against the always-violation column.** Search the written version for every word in the third column; a hit is a violation. This layer is mechanical, never misses a known alias, and costs nothing — so it always runs first, no agent needed as a substitute. Also search the fourth column (context-dependent), but the hits need a human eye on them, don't auto-fix them as violations.

**Layer three: dispatch a subagent to read straight through the whole document, with exactly one job — find aliases not yet in the glossary.** Have it list every group of words that "look like they refer to the same thing but are written differently," **don't have it judge which one is correct** — that judgment is made by the main conversation. This is the one thing an agent is better at than a search here: finding an alias the writer didn't think of. Any new alias it reports gets added to the glossary's third column, then layer two reruns.

**Why layer three alone isn't enough**: a long document can have dozens of instances of synonym substitution, and if one agent is asked to find them all in one pass, it'll pick a few obvious ones and call it done. A search won't.

### Also dispatch one to check the split between the two halves

Dispatch another subagent to read straight through the whole document, checking exactly one thing: whether interpretation has leaked into the top half, and whether the bottom half has mixed in a new fact that never appeared in the top half. List every suspect sentence one by one.

### Report to the user

The result of this stage must be reported to the user: **how many not-understood words came back in total, which sections got sent back for rewriting, how many rounds it took to converge.** These numbers are direct evidence of whether this document is readable — don't leave them out of the report.

## Phase 5: render the artifact (deterministic conversion + character-by-character verification)

This stage used to say "hand it to a subagent to render," changed on 2026-07-31. **Reason: the only hard rule at this stage is "not a single character may change," and only a deterministic conversion can prove that.** Have a model copy out a long document and it will inevitably shift a few characters without meaning to — in practice the very first render dropped 19 characters (a collapsed heading ate the trailing period, and one heading got swapped for a phrase the model made up itself). Having a human check it afterward just hands verification back to the same thing that makes the mistakes.

So it's split into two steps, and the first time and every time after that do different things.

### The first time: have a subagent build a converter, not a page

Dispatch a subagent with clear instructions:

- Load the `artifact-design` skill before doing anything else.
- What it produces is **not HTML, it's a markdown → HTML conversion script**, which takes this written version as input and produces the page as output. Layout requirements are in the section below.
- The script must be purely deterministic: the same input always produces the same output, with no room for "let me smooth this over a bit here."
- Block types the script must handle include at least: headings, paragraphs, tables, code fences, blockquotes, unordered lists, horizontal rules; inline types include at least: bold, backtick code, escapes.

### Every time after that: just run the script, then verify character by character

1. Run the converter to get the HTML.
2. **Extract the visible text from the HTML (strip all tags, restore entities), and compare it character by character against the markdown's text with its markup stripped.** They must be exactly identical after ignoring whitespace. Use `difflib` to print the diff blocks.
3. **Do not publish if they don't match.** First find out whether the converter dropped characters, or the markdown has syntax the converter doesn't recognize.

This step ran successfully twice on 2026-07-31, both times reporting "md 36082 / html 36082 → character-for-character identical." With that number, "not a single character may change" is provable, not just a verbal promise.

### Layout requirements (for the converter to implement)

- Keep the six-section, two-half structure as is; the order of five fact sections on top, one interpretation section on the bottom, must not change.
- Experiment descriptions are collapsed by default, expand to see them (the page gives the numbers first, the method and logic are for clicking into). **The collapsed heading must be taken verbatim from that bold line of text in the markdown, not even punctuation may change** — the 19 characters dropped last time were lost exactly here.
- **The two halves must be visually distinguishable at a glance on the page** — background color, a border, or a banner heading spanning the width all work, but it can't rely on just a small label to tell them apart. The bottom half must open with a clear statement that "everything below is interpretation, and it can be argued with."
- **Every number carries an annotation**, viewable by clicking or hovering, showing what it refers to and where it's from, with content matching what's in the written version's parentheses. Implement the annotation with pure HTML and CSS (e.g. `<details>` or a `:hover`-revealed block), no external script. There's no hover on a phone, so a tap must also be able to open it.
- Both light and dark themes must be readable: write colors as custom properties on `:root`, redefined once each under `@media (prefers-color-scheme: dark)` and under `:root[data-theme="dark"]` / `:root[data-theme="light"]`.
- Wide tables scroll horizontally inside their own container, the page itself never scrolls horizontally; CJK text uses the system font stack, no external webfont.
- The favicon is fixed and doesn't change across re-publishes. A status page for the same line **is re-published to the same file path**, keeping the same URL (see Phase 0.5).

## Red lines

- **No number may appear that isn't in the ledger.** If it's missing, say it's missing.
- **"Did you get it" doesn't count as acceptance.**
- **Subagents may not change a single character of the written version.**
- **One entity gets exactly one name for the whole session.**
- **No external literature review.** What other people have done is the job of `update-knowledge-map`.
- **Never touch `RESULTS.md`.** It's a rendered artifact, a hand edit destroys it.
- **The bottom half may not contain any number or fact the top half never gave.** Check with a script, don't rely on self-discipline.
- **The artifact may not be published without passing character-by-character verification.**
- If a conclusion changes any judgment in `WORKPLAN.md` → remind the user to add a `TIMELINE.md` entry, but don't write the TIMELINE entry yourself — that's for a human to write.
