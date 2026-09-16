# Splice-method replay experiment (splice_replay): plan

2026-08-18. Answers one question: when the probe fires, which **way of
splicing the prefetched result back in** makes the model think less about
it, move straight on, and not discuss the injection itself. The probe
weights have been deleted, so this first uses a god's-eye replay: take 5
chat baseline trajectories (`cmp_chat_noprobe_5/chat`), cut the thinking at
four positions in each step, splice in that step's code block's real
execution output using ten splicing methods, and let gpt-oss-120b continue
writing for one step, measuring only single-step behavior. Not run to
completion, not evaluated, and prediction correctness is not judged.

## 1. Events

- Source: the 5 files
  `cmp_chat_noprobe_5/chat/appworld_gptoss/appworld_<tid>.jsonl`.
- Selecting steps: content contains exactly one ```python block, and the
  block contains exactly one `apis.x.y(` call (52 of 68 steps qualify; 1
  step has no code, 13 steps have multiple calls or no call, 2 steps are
  byte-for-byte duplicates of another step in the same task; a multi-call
  block's stdout is not "the return value of that one call," so no arm can
  splice together the same CALL/RESULT). Of the 52 steps, 40 have a code
  block that is bare `print(CALL)` (`code_is_print_call`), the other 12
  have an assignment/extra print, with RESULT being the whole block's
  stdout; 3 steps hit the 8192 cap during collection (`baseline_capped`);
  25 steps have a next-step tool different from this step's
  (`next_distinct`), the remaining 27 steps use the same tool with
  different parameters.
- Deduplication: 3d9a636_1/2/3 are the same task, and the prompt + thinking
  of the first few steps are byte-for-byte identical; deduplicated by
  hashing `(prefix_ids, reasoning)`, keeping only one copy (a continuation
  from identical input gives no new information).
- Each event stores: traj/step, the prefix messages (up to before that
  step), the full reasoning text, CALL (the complete `apis.x.y(...)` in the
  code, balanced by `parse_call.complete_call`), CODE (the raw code block),
  RESULT (env.result, already truncated to 4000 at collection time),
  baseline_out_tok (that step's usage.out), next_tool (the first called
  tool's name in the next step's code block, or None if there is none).
- Steps whose thinking is too short (`< MIN_THINK`=40 characters) are not
  taken.

## 2. Cuts (axis three)

- Ratios 66 / 75 / 80 / 100, computed by the reasoning's **character
  count**.
- 66/75/80: the nearest sentence end **before** that ratio point (the same
  kind as `live_appworld.sent_cuts`: the `m.end()` of
  `SENT_RE=(?<=[.!?])\s+|\n`, with the `MIN_THINK//2` filter). If two ratios
  land on the same sentence end, they are merged into one record, and the
  `fracs` field lists which ratios it represents.
- 100 = the end of the reasoning's full text (the model has finished
  thinking, the NOTE is appended at the end of the thinking, before the
  body).
- head = reasoning[:cut]. The head for 66/75/80 ends in whitespace, the
  head for 100 does not end in whitespace.

## 3. Arms (axis one x axis two)

Notation: `A_OPEN = <|channel|>analysis<|message|>`, `SWITCH =
<|end|><|start|>assistant<|channel|>final<|message|>`, `NOTE(x) =
"[SYSTEM NOTE: prefetched CALL = RESULT]"`; the other wordings are in the
table below. Every arm's prompt prefix = `harmony_render.render_ids(msgs up
to that step)` (the same ids as the chat endpoint).

| Arm | Prompt tail (after prefix_ids) | Note |
|---|---|---|
| nofill | `A_OPEN + head` | anchor: continuation with nothing injected |
| p1_n0 | `A_OPEN + head + sep + "[SYSTEM NOTE: prefetched CALL = RESULT]\n"` | current setup |
| p1_n1 | ... `"I already ran:\nCODE\nand got:\nRESULT\n"` | first person (splices in CODE, every sentence true) |
| p1_n2 | ... "```python\nCODE\n```\nExecution output:\nRESULT\n" | environment's voice (splices in CODE) |
| p1_n3 | ... `RESULT + "\n"` | bare result |
| p1_n0p | same as p1_n0, plus a `PERMIT` sentence appended to the end of the system prompt | announced in advance |
| p2_n0 | `A_OPEN + head + sep + "[SYSTEM NOTE: prefetched CALL = RESULT]" + SWITCH` | force-cut into the body right after splicing (`inject_stop`) |
| p2_n1 | same as above, wording swapped to n1 (the NOTE has no trailing newline, goes straight into SWITCH) | |
| p3k | openai_harmony rendering: ..., assistant/analysis(head.rstrip()), assistant/final(CODE block content), user("Execution output:\nRESULT"), `<|start|>assistant` | faking a whole turn, **keeping** the thinking |
| p4 | openai_harmony rendering: system declares the python tool, ..., assistant/analysis(head.rstrip()), assistant->python/analysis(CODE)`<|call|>`, python->assistant/analysis(RESULT), `<|start|>assistant` | harmony's native python tool |

`sep` (the seam fix, applying only to p1/p2): if head ends in whitespace
(the 66/75/80 cuts) -> `""`, with the NOTE going right after the whitespace
(a newline cut starts a new line, a whitespace cut is inline); if head has
no trailing whitespace (the 100% cut) -> `"\n"`. Reason: `.\n\n` + `\n[`
would merge into `.\n\n\n`, replacing the model's own last token; `. ` +
`\n[` keeps the `.` but adds an odd ` \n` token; `.\n\n` + `[S` and `. ` +
`[S` are both clean, `.` stays as is. Of the actual 178 cuts, 88 end in a
space, 38 end in a newline, and 52 (the 100% ones) have no trailing
whitespace.

Not included in this batch (they degenerate under the god's-eye view): p3
(faking a whole turn that drops the thinking = jumping straight to the next
step of the original trajectory), p5 (the result arrives together with the
next turn's user message = baseline itself). These only become distinct
once there's a real probe (whose prediction might be wrong, and which only
injects one result).

## 4. Continuation

- `/v1/completions`, the prompt is token ids, `temperature=0`,
  `stop=["<|return|>"]`, `skip_special_tokens=False`, `max_tokens=8192`
  (the whole-step cap used at collection time; p3k/p4 are a new assistant
  message, same cap).
- Events ≈ 50 x cuts <= 4 x arms 10 ≈ 2000 total, concurrency 16, one H200.
- Each one is recorded in raw.jsonl: event, frac, arm, prompt_tok, gen_tok,
  text, finish_reason.
- All prompts are first dry-run to produce the decoded text, and one
  example per arm is checked by eye.

## 5. Metrics (per arm x per cut)

Action = a ```python block in the body; when there's no body but the model
itself issues a python call (p4's natural continuation, which harmony puts
on the analysis channel, `to=python`, ending in `<|call|>`) that also
counts as an action (`action = final_code | python_call`). Tool-level =
`apis.x.y`; call-level = the whole call compared character for character
after stripping whitespace.

1. Token: `own_tok = head_tok + gen_tok` (the spliced-in string doesn't
   count, only what the model itself wrote); the main reference is
   **nofill on the same event and same cut** (`vs_nofill_own`);
   `saved_own = baseline_out - own_tok` is only supporting evidence, since
   baseline's usage.out doesn't reconcile the commentary segment against
   the message-header accounting, so nofill has a constant offset of a few
   tokens against baseline (the reviewer measured it at ≈ +7); don't treat
   that as a pipeline bug.
2. `has_action`; `python_call` (the model itself called python).
3. `repeated` / `repeated_call`: whether the tool / whole call in the
   action == the one that was spliced in (it ran again).
4. `next_hit` / `next_hit_call`: whether it == the first tool / whole call
   of the original trajectory's next step (moved forward); 27/52 events
   have the same tool in the next step as the current one, so tool-level
   next_hit can only be read on the `next_distinct` subset (25 events, as
   `next_hit_distinct`); call-level can be read on both sides.
5. `uses_result`: a string literal from the code appears in RESULT and is
   not present in the prompt text before the cut.
6. `mentions`: `system note` / `prefetch` / `the note says` and so on;
   `mentions_already`: `already ran/called/executed`. **This is only
   meaningful for arms whose prompt actually gives these words
   (n0/n0p/n1)**; the other arms sitting near 0 is because the words
   aren't there, not a behavior; p2 closes the analysis channel, so this
   kind of talk has nowhere to be written in the first place.
7. Structure: `reopen_analysis` (analysis reopened after p2),
   `stopped_on_call` (any arm stopping on `<|call|>`, which is the model's
   generation_config eos, so vLLM stops on it for every arm,
   stop_reason=200012), `truncated` (finish_reason == length),
   `think_chars_after` (how many more characters the model itself thought,
   excluding the spliced-in NOTE and excluding the python-call segment).
8. Breakdowns: `by_arm` / `by_arm_uncapped` / `by_arm_print_call` /
   `by_arm_not_print_call` / `by_frac`.

Produces `SPLICE_REPORT.{json,md}` + `per_row.jsonl`.

## 6. Decision points that affect the results (my choice / alternative)

| # | Decision | My choice | Alternative |
|---|---|---|---|
| D1 | Events only take single-call blocks | Yes (54 steps) | Take all 67 steps, RESULT labeling is biased for multi-call blocks |
| D2 | Deduplicate repeated steps in the same task | Yes | Don't deduplicate (n would be inflated) |
| D3 | What to use for CALL | the complete `apis.x.y(...)` in the code | the whole code block |
| D4 | What to use for RESULT | that step's raw env.result (the block's stdout, including effects from assignment logic beyond print) | there's no more precise source |
| D5 | Seam fix, sep | if head ends in whitespace, don't add a leading `\n` (a whitespace cut has the NOTE inline, a newline cut starts a new line) | always add `\n` (as things stood: a newline cut swallows one token, a whitespace cut gets an extra ` \n` token) |
| D6 | Stripping trailing whitespace from head for arms that close analysis | p2 doesn't strip it (the NOTE goes right after the whitespace); p3k/p4 do `rstrip()` before `<|end|>` | never strip it (`\n\n<|end|>` is a form the model has never seen) |
| D7 | p4's system prompt declaring the python tool | declare it (that's part of the training format) | don't declare it, just splice in the tool round-trip |
| D8 | max_tokens | always 8192 | 8192 - tokens already used |
| D9 | p3/p5 not included in this batch | don't include them (they degenerate under the god's-eye view) | include them, as an upper-bound anchor |
| D10 | The 100% cut | the end of reasoning (no sentence-end requirement) | the last sentence end |
| D11 | p4's stop token | add `<|call|>` in addition to `<|return|>`: if the model calls python again, it stops, recorded as `python_again` | don't add it (the model would make up a tool return itself and keep writing) |
| D12 | Steps that hit the 8192 cap during collection (3/52) | keep them, marked `baseline_capped`, the report gives one version each for by_arm and by_arm_uncapped | drop them |
| D3' | Which value each wording splices in | n0 uses that call, CALL (the current-setup anchor, not entirely true for the 12/52 non-bare-print blocks, broken out in the report); n1/n2/p3k/p4 splice in the raw code block, CODE (every sentence true) | use CALL everywhere |
| D13 | Reviewer pointed out that n1's "I already ran print(CALL)" is a false statement for 12 blocks | n1 changed to `I already ran:\nCODE\nand got:\nRESULT` | keep the print(CALL) wording, break it out in the report |
| D14 | Reference frame for the seam | the reference is **the ids the model generated** (the sentence-end space belongs to the discarded next token ` Then`), not `enc(head)` (which would encode the trailing space as a standalone ` ` token); under D5', `.` stays as is and the space merges into ` [`, the same structure as the model's own ` Then` | compare against enc(head) (the reviewer's method of comparison, which found 138 of 178 cuts "different," but that standalone ` ` token was never generated by the model) |

## 7. Deliverables

- `pipeline/inject/splice_replay.py`: three subcommands, `events` / `run` /
  `score`.
- `tests/test_splice_replay.py`: each arm's byte-level form (once with a
  fake tokenizer, once with the real one), cut placement, the sep rule,
  boundary samples for the scoring functions.
- `run.py` registers `splice-events` (CPU), `splice-run` (handoff),
  `splice-score` (CPU).
- Output directory: `/net/.../pipeline/inject/runs/splice_replay_v1/`.
