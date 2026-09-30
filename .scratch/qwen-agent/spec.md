# Qwen as the agent model: plan

Written 2026-10-01 while gyb is away (his instruction: "keep everything else the same, but
substitute gpt-oss with Qwen; for Qwen's distinct settings, research them"). The
collection settings are those of `.scratch/full-history-probe/spec.md`; only the agent
model and what is specific to it change.

Status labels: DECIDED (gyb's word), PROPOSED (mine, waiting for his word), FACT.

## 1. What the research found (one Opus agent, own knowledge first, then fetched sources)

- The model closest to gpt-oss-120b's role (open weights, reasoning on, one card) is a
  Qwen mixture-of-experts model with about 3B active parameters: Qwen3-30B-A3B-Thinking-2507
  (thinking always on, 262,144-token native window, 61 GB in bf16) or Qwen3.5-35B-A3B
  (thinking switchable, 72 GB in bf16, carries a vision encoder). Neither was on the net
  disk; both are being downloaded to `/net/tokyo100-10g/data/str01_01/y-guo/models/`.
- The cached Qwen3-32B and Qwen3-30B-A3B have a 32,768-token native window and reach
  131,072 only with YaRN, which the tree's vLLM 0.26 takes through `--hf-overrides`.
- Qwen has no reasoning tiers; a thinking budget is a cap applied from outside. So the
  family has no effort values and the setting names none.
- The Qwen3 cards prescribe temperature 0.6, top_p 0.95, top_k 20 for thinking mode and
  say "DO NOT use greedy decoding"; the Qwen3.5 card prescribes temperature 1.0, top_p
  0.95, top_k 20, presence penalty 1.5 for general tasks. AppWorld's own config for
  Qwen3-235B-A22B-Thinking-2507 uses temperature 0 and 50 steps.
- A silent default: Qwen's `generation_config.json` holds top_p 0.95 and top_k 20, and
  vLLM applies a model-file value to every field a request leaves out. Our client sends
  temperature only, so a Qwen run samples with top_p 0.95 and top_k 20 unless the server
  is started with `--generation-config vllm`. gpt-oss's file holds no sampling values, so
  its runs used neither.
- The ChatML template has no date slot; the loop's `developer` message has to be sent as
  `system` (the Qwen3 template drops an unknown role silently, the Qwen3.5 template
  raises). Thinking is `<think>…</think>` before the content; the 2507-Thinking and
  Qwen3.5 templates put `<think>` in the prompt so the output holds only `</think>`.
- Both venvs already hold transformers 5.14.1 with the Qwen3 and Qwen3.5 classes; vLLM
  0.26 registers the model classes and has the `qwen3` reasoning parser (not needed, the
  loop parses text itself).

## 2. Settings for the Qwen collection

| Setting | Value | Status |
|---|---|---|
| Agent model | Qwen3-30B-A3B-Thinking-2507 first; Qwen3.5-35B-A3B second | PROPOSED |
| Temperature | 0.6 for Qwen3-2507, 1.0 for Qwen3.5 (each card's value) | PROPOSED; gyb's "distinct settings" clause |
| top_p / top_k | the model file's 0.95 / 20 (left to vLLM's model-file default) | PROPOSED |
| Thinking | on, no budget | PROPOSED |
| Date | first line of the system text, "Current date: <task date>" | PROPOSED |
| Window | 131,072 (native 262,144 for both candidates; no YaRN) | FACT |
| Everything else | as the gpt-oss collection: 50 steps, 30,000 tokens per step, replies cut at 20,000 characters, 5 runs per task, v2 wording | DECIDED |

## 3. What the repo needs (recipe 7)

- `models/agent_models/qwen3.py`: the family module (in progress, an Opus implementer).
- `constants/path_models.yaml`: two rows (in progress).
- `models/table.yaml`: two rows, gyb's file; the implementer's report carries the text.
- `experimental_settings/draft/`: a Qwen setting block beside the gpt-oss one, once the
  table rows exist.
- Servers run on tokyo108 only (the vLLM venv does not run on the 47 GiB machines).

## 4. Open points for gyb

1. Which model first (section 2's proposal, or the cached Qwen3-32B with YaRN).
2. Temperature: the card's value per model, or 1.0 everywhere for sameness with gpt-oss.
3. top_p and top_k: the model file's values, or truly unsent (`--generation-config vllm`).
