# T06 report — the model table, the entrance, the gpt-oss family and the probe object

Branch `ticket/2026-09-17-wave2/T06`, base `1895873b76c8614db0b7ea52dd103adae9e23a80`,
head `fde660f5d68ea76d37a39a8631aff23510f9896e`. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T06`, removed after the
commit; branch kept.

Note on `base`: `git rev-parse HEAD` at the very start of this task read
`943af829b83f8f66d4b4a6434f4a685b2b2f9c10`, but the main session committed
two more commits to `from-zero` (`464e143`, `1895873`, both contracts/constants
edits, no code) before I ran `git worktree add`. The worktree therefore
branched from `1895873`, which is the sha I report as `base`.

## 1. What was done

Seven files, all under `models/`, plus this ticket's seven README lines.

- **`models/table.yaml`** — the four rows exactly as the ticket specifies
  (`gptoss120b`, `qwen06`, `qwen17`, `qwen4`), including both errata
  (`gptoss120b.result.dtype: auto`, `qwen06.result.dtype: float32`).
- **`models/__init__.py`** — `AgentModel`/`ProbeModel` dataclasses, `agent(alias)`
  and `probe(alias)`. `weights` is always the alias (`row["result"]["weights"]`);
  `weights_path` is resolved against `constants/path_models.yaml`, raising
  `FileNotFoundError` on a missing absolute path and passing a non-`/`-prefixed
  value (a hub id) through unchecked. `agent()` imports
  `models.agent_models.<family>` by name inside the function and raises
  `ModuleNotFoundError` naming the expected file path when it's missing.
  Both `agent()`/`probe()` raise `KeyError` on an unknown alias (naming the
  sorted known aliases of that role) and `ValueError` on a row of the wrong
  role (naming the row's actual role). Both YAML files are located through
  `Path(__file__).resolve().parents[1]`. No `VERSION`.
- **`models/agent_models/__init__.py`**, **`models/probe_models/__init__.py`** —
  one-line docstring, nothing else.
- **`models/agent_models/gptoss.py`** — `render_ids`, `parse`, `end_of_turn`,
  `wrap_prefetch`, plus `STOP`/`EFFORTS`/`DEFAULT_EFFORT`/`DEFAULT_DATE`/`NAME`/
  `END_IDS`, all as specified. `render_ids` refuses `effort=None`, `date=None`,
  and an effort outside `EFFORTS`; `openai_harmony` is imported only inside
  `render_ids` (and the two helpers it calls). `parse` accumulates raw text in
  `state["raw"]` and re-derives the two channels from the whole accumulated
  text each call, porting `live_appworld.py`'s `parse_step` logic verbatim
  (split on `<|return|>`, then on `<|end|>`; a valid header is
  `[<|start|>assistant[ to=x]]<|channel|>CH<|message|>`; `analysis` → `reasoning`,
  `final`/recipient-less `commentary` → `content`, joined with `\n`; a
  half-written header contributes nothing).
- **`models/probe_models/qwen.py`** — `prepare_tokenizer` (pad token, 
  `truncation_side="left"`, `padding_side="right"`), `attach_head` (a
  `torch.nn.Linear(hidden_size, n_labels, dtype=torch.float32)`, `torch`
  imported inside the function per the ticket's own import list for this
  file), `DTYPE`, `LORA_TARGETS`, `HEAD_LAYER`.
- **`models/probe_models/base.py`** — `Probe(torch.nn.Module)` with `backbone`,
  `head`, `tokenizer`, `max_len`, `labels`, `probe_kind`, `lora`; `save`,
  `forward`, `score`, `generate`, `trainable_parameters`, `set_training`,
  `grad_checkpointing`; module-level `load(row, cfg, *, probe_kind, n_labels,
  labels, ckpt_dir, device="cpu")`, `Batch`, `Outputs`.
  - `load` imports the backbone module by name inside the function
    (`row["family"]` on a fresh load, `models.probe(meta["backbone"]).family`
    on a restore).
  - Fresh-load dtype is `row["dtype"]`; restore dtype is the backbone module's
    `DTYPE` on a cuda device and `"float32"` on cpu.
  - `probe.tuning` is dispatched over `("full", "lora")`, raising on anything
    else and naming the axis and the value; the `lora` branch imports `peft`
    inside itself only, wraps with `peft.LoraConfig(r=cfg.probe.lora_r,
    lora_alpha=cfg.probe.lora_alpha, lora_dropout=cfg.probe.lora_dropout,
    target_modules=<cfg.probe.lora_targets or the backbone's LORA_TARGETS>,
    bias="none")`, and keeps the wrapper in `self.lora`; `self.backbone` stays
    the pre-wrap variable, which keeps working directly because
    `get_peft_model` swaps the target `nn.Linear` submodules in place.
  - `forward`: classifier reads `getattr(out, HEAD_LAYER)` (dotted-path aware)
    at `event_end` positions and returns `hidden` as the full `[B, T, dim]`
    tensor; generator calls the inner transformer (`model.get_base_model()` if
    present, else `model` itself, then `.model`/`.lm_head`) so the LM head is
    only ever applied at the gathered `event_end` positions, never over the
    full sequence (this ports the technique of
    `train_causal_share.py:128-137,140-176`, cited here in the report per the
    "no legacy citation in shipped source" rule).
  - `save`: LoRA present → deep-copy, `merge_and_unload()`, save, free, empty
    the cuda cache if the copy was on cuda; else `backbone.save_pretrained`
    directly (the restore path never re-wraps LoRA, since the checkpoint is
    already merged, so `self.lora` is always `None` after a restore). Writes
    tokenizer, `head.pt` for a classifier, and `meta.json` = `{"labels":
    labels, **meta, **extra}`, read by neither `meta` nor `extra`.
  - `score`: batched, truncation+padding, each row's true last token via
    `attention_mask.sum(dim=1) - 1`, head applied under `no_grad`, softmax and
    temperature intentionally absent (service's job, ticket 07).
  - `generate`: `text + call_sep`, `add_special_tokens=False`, greedy,
    `skip_special_tokens=True`, first line stripped.
  - `trainable_parameters`/`set_training`/`grad_checkpointing` are the three
    names `train/utils/trainer.py` will call; `grad_checkpointing(True)` also
    calls `enable_input_require_grads()` once under LoRA (guarded by the
    model's own `_require_grads_hook` attribute, the same idempotency check
    the legacy helper used).

README.md: appended a "Ticket 06" section under the existing "Ticket 03"
section, with the seven contract lines for these files copied from contracts
0.2 verbatim (the `models/`, `agent_models/`, `probe_models/` group headers
included, since this ticket is the first to introduce them; the two
`service.py` lines are explicitly left for ticket 07 and a one-line note says
so, to avoid the reader assuming they're missing by mistake).

## 2. How it was verified

All commands run from the worktree root
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T06` (now removed), interpreters
by absolute path into the main repo's `external/`.

**A1 — every `any` file imports under four interpreters.**
```
$ for P in "$SYS" "$AW" "$PR" "$VL"; do $P -c "import models, models.agent_models.gptoss; print('ok')" || exit 1; done
ok
ok
ok
ok
```
Pass.

**A2 — the two entrances resolve.**
```
$ python3 -c "..."
agent gptoss gpt-oss-120b gptoss tokyo108 8103
probe qwen qwen3-0.6b-base False
True True
```
Matches exactly.

**A3 — the entrances refuse.**
```
$ python3 -c "..."
ValueError models.agent: 'qwen06' has role 'probe', not 'agent'
ValueError models.probe: 'gptoss120b' has role 'agent', not 'probe'
KeyError "models.agent: 'nosuch' is not a known agent alias; known agent aliases: ['gptoss120b']"
```
Three refusals, none `NO REFUSAL`; the first two name the actual role, the
third lists the known agent aliases. Pass.

**A4 — the literals are readable the way `schema.py` reads them.**
```
$ python3 -c "..." (gptoss.py)
[('DEFAULT_DATE', '2026-08-06'), ('DEFAULT_EFFORT', 'high'), ('EFFORTS', ('high', 'medium', 'low')), ('NAME', 'gptoss'), ('STOP', ['<|return|>']), ('VERSION', 1)]
$ python3 -c "..." (qwen.py)
1 7 ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']
```
Matches exactly.

**A5 — `parse` over a chunked stream.**
```
['content', 'reasoning']
'I will look it up. Then act.'
'Here is the code.'
'' ''
```
Matches exactly.

**A6 — `end_of_turn`, and its ids against the library.**
```
True True False False
end ids ok
```
Matches exactly.

**A7 — `wrap_prefetch`.**
```
'<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>show_playlists() = [..]<|end|><|start|>assistant'
'<|end|><|start|>prefetch to=assistant<|channel|>analysis<|message|>Sometimes a prefetch appears.\n\nshow_playlists() = [..]<|end|><|start|>assistant'
```
Matches exactly.

**A8 — `render_ids` equals vLLM's own renderer.**
```
base high equal: True
base low equal: True
two high equal: True
two low equal: True
empty_assistant high equal: True
empty_assistant low equal: True
literal_marker high equal: True
literal_marker low equal: True
```
Eight lines, all `equal: True`. Pass.

**A9 — `render_ids` refuses an unpinned effort or date.**
```
ValueError effort is required: render_ids refuses an unpinned reasoning effort
ValueError date is required: render_ids refuses an unpinned date
ValueError effort must be one of ('high', 'medium', 'low'), got 'ultra'
```
Three refusals, no `NO REFUSAL`. Pass.

**A10 — the probe object on a tiny CPU checkpoint, and A11 (its tail).**
```
score 2 2 True 256 True
gen 1 True
save ['backbone', 'call_sep', 'labels', 'max_len', 'param_only', 'train_key', 'tuning'] True
forward (2, 2) 64
```
Matches exactly (including A11's `forward (2, 2) 64` line). Pass.

**A12 — the LoRA merge equals the base on a fresh adapter.**
```
7 lora targets ['down_proj', 'gate_proj', 'k_proj', 'o_proj', 'q_proj', 'up_proj', 'v_proj']
merge allclose True
no adapter file True
tuning lora
```
Matches exactly. Pass.

**A16 — the annotation and literal rules for these seven files.**

The verbatim script as pasted in the ticket **crashes** on its second block:
```
$ python3 - <<'PY'
...
top = [a.module or a.names[0].name for a in g.body if isinstance(a, (ast.Import, ast.ImportFrom))]
...
PY
Traceback (most recent call last):
  ...
AttributeError: 'Import' object has no attribute 'module'
```
This is a bug in the ticket's own check, not in the code under test: it walks
every top-level `ast.Import` *or* `ast.ImportFrom` node and unconditionally
reads `.module`, but a plain `ast.Import` node (e.g. `import re`) has no
`.module` attribute — only `ast.ImportFrom` does. `models/agent_models/gptoss.py`
has a top-level `import re` (stdlib, needed by `parse`'s header regex), which
is exactly the kind of statement section 4's `any`-venv rule says belongs at
module level (`data/probe_input.py`, already on the branch, does the same for
the same reason). I did not edit the acceptance command; I ran it verbatim and
it failed as shown above.

To check the two assertions the script intended (no repo-file import besides
`models`/no `experimental_settings`/`jobs` import in `base.py`; no top-level
`openai_harmony` in `gptoss.py`) I ran the same script with the one line
patched to `getattr(a, "module", None) or a.names[0].name`, and reran the rest
unmodified:
```
$ python3 - <<'PY'
... (a.module or a.names[0].name  ->  getattr(a, "module", None) or a.names[0].name)
PY
A16 ok (with the AttributeError line patched to handle plain `import` nodes)
```
```
$ grep -n "/home/\|/net/" models/*.py models/agent_models/*.py models/probe_models/*.py || echo NO_ABS_PATH
NO_ABS_PATH
```
The grep line (the part of A16 that isn't affected by the bug) passes as
given. I'm reporting `A16` as passing in substance, with the one line of the
check script broken as described; nothing in my code needed to change for it
to pass.

## 3. Commits

```
$ git -C /home/y-guo/reproduce/new1 log --oneline -1 ticket/2026-09-17-wave2/T06
fde660f T06: models/table.yaml, the entrance, the gpt-oss family and the probe object
```

One commit, `fde660f5d68ea76d37a39a8631aff23510f9896e`, containing all seven
files plus the README addition.

## 4. Self-review findings and open questions

- **A16's `ast.Import`/`.module` bug** — documented above in section 2; no
  code change made on my side, since the bug is in the check script, not in
  my files.
- **`gptoss.py`'s declared third-party import list.** Contracts 0.2 and the
  ticket both write `imports: none (repo); [openai_harmony, inside
  render_ids()]` for this file, but say nothing about `re`, which the ported
  `parse()` needs at module level (the same way `data/probe_input.py` already
  does on this branch). I read this as an omission in the annotation's bracket
  list rather than a real disagreement — `re` is stdlib, always allowed under
  `venv: any`, and doesn't change what the line is trying to convey (only
  `openai_harmony` is deferred). I did not add `re` to the README bracket
  list, to keep the line an exact copy of contracts 0.2; flagging it here in
  case ticket 14 (which assembles the final `README.md` from contracts 0.2)
  or `run.py selfcheck` (ticket 15) wants it added.
- **`models/probe_models/qwen.py`'s declared third-party import list** has the
  same shape of gap: contracts 0.2 says `[transformers]` only, but
  `attach_head` needs `torch.nn.Linear`. I kept `import torch` inside
  `attach_head` (matching the file's own venv being `probe`, not `any`, so
  this isn't required by the heavy-import-deferral rule — I did it anyway to
  stay literally consistent with the stated bracket list). Flagging the same
  way as the `gptoss.py` case above.
- **`row["dtype"]` on the fresh-load path.** The ticket's prose says base.py
  "reads exactly `cfg.probe.tuning`, the four `cfg.probe.lora_*` fields,
  `cfg.train.max_len` and `cfg.models.probe`" from `cfg`, and separately that
  `row` is `cfg.models.probe_row` — "role, family and the result: block." I
  read a row's dtype off `row["dtype"]` directly (the flattened `result:`
  block), which A12's test fixture (`row = {"role": ..., "family": ...,
  "weights": ..., "dtype": "float32"}`) confirms is the right shape. Noting it
  since the ticket's own prose doesn't spell out this specific key path in as
  many words.
- **No test file added.** Per spec section 2, `tests/` only grows for the two
  named exceptions (neither is this ticket), so everything here is verified
  by the acceptance commands above, none by a new test file.
- **`run.py selfcheck`** does not exist yet on this branch (confirmed:
  `ls run.py` fails), so I did not run it, per the protocol and the ticket's
  own "selfcheck lines that apply later" section.
- Nothing found that belongs in another ticket beyond the two annotation gaps
  above (worth a look at ticket 14/15 time).

## 5. Fix round 1

Branch `ticket/2026-09-17-wave2/T06`, taking over from the round above at head
`fde660f`. Worktree `/home/y-guo/reproduce/new1-wt/2026-09-17-wave2-T06-fix1`,
removed after the commit; branch kept. Fix head
`7d2f53f6...` (`git log --oneline -1` output pasted in section 5.3 below).

### 5.1 F1 (critical) — `Probe.generate()` corrupts output for shorter texts in a mixed-length batch

**Root cause.** `qwen.prepare_tokenizer` sets `tok.padding_side = "right"`
once, at load time, on the tokenizer instance both `score()` and `generate()`
share. `score()` is unaffected by the side because it explicitly locates each
row's true last token via `attention_mask.sum(dim=1) - 1` — a formula that in
fact **depends on** right-padding (it assumes the real tokens are contiguous
from index 0). `generate()` had no such explicit handling: it tokenized the
batch with whatever `padding_side` the shared tokenizer currently held (right,
from load time) and handed the result straight to
`self.backbone.generate()`. transformers' decoder-only `generate()` reads the
next-token distribution from the physically last column of the sequence
(`outputs.logits[:, -1]`), which under right-padding is a PAD position for
every row shorter than the batch's longest row — so shorter rows in a
mixed-length batch were generated from the wrong position, silently. I
reproduced this on the branch before touching any code: `generate(['hi'], 6,
sep)` alone gave one continuation for `'hi'`; `generate(['hi', <a much longer
text>], 6, sep)` together (mixed lengths, right-padded) gave a *different*
continuation for `'hi'`, and transformers itself printed `"A decoder-only
architecture is being used, but right-padding was detected!"` during that
call.

**Fix (root-cause, not a patch).** `generate()`'s own tokenizer call now
passes `padding_side="left"` — a per-call override transformers 5.14.1
supports directly on `tokenizer.__call__` (confirmed by reading
`PreTrainedTokenizerBase.__call__`'s signature and body: the kwarg flows into
the padding strategy without touching the tokenizer's stored
`padding_side`). This replaces the wrong logic (batch tokenized under
whatever side the tokenizer happens to hold) with the correct one (batched
autoregressive generation is always left-padded), scoped to exactly the one
method that needs it; `score()`'s tokenizer call is untouched and keeps
relying on the shared tokenizer's right-padding default, since its own
position formula requires it. Diff, `models/probe_models/base.py`:

```diff
@@ class Probe.generate
         prompts = [t + call_sep for t in texts]
+        # batched autoregressive generation reads the next-token logits from the
+        # physically last column of the sequence, so the batch must be left-padded
+        # regardless of the tokenizer's stored padding_side (score()'s right-padding,
+        # which its attention_mask.sum(dim=1)-1 rule depends on)
         enc = self.tokenizer(prompts, add_special_tokens=False, truncation=True,
                              max_length=max(self.max_len - max_new, 1), padding=True,
-                             return_tensors="pt").to(device)
+                             padding_side="left", return_tensors="pt").to(device)
```

No signature change (`generate(self, texts, max_new, call_sep) -> list[str]`
is unchanged), no new imports, no other file touched. `score()`,
`prepare_tokenizer` and the checkpoint layout are all unchanged; the fix does
not need a README update.

### 5.2 Verification

**Bug reproduction, before the fix** (temp script, same tiny-CPU-checkpoint
shape as the ticket's A10, `models.probe_models.base.load` with
`probe_kind="generator"`), run from the worktree with `PYTHONPATH=.`:
```
$ PYTHONPATH=. external/probe-env/bin/python /tmp/repro_f1.py
[transformers] A decoder-only architecture is being used, but right-padding was detected! For correct generation results, please set `padding_side='left'` when initializing the tokenizer.
alone short:  'Und capsulescompileatementGrünvirtual'
mixed short:  'בא Baltenumer\tpanic造福ينة'
DIFFERENT
```
`generate([short], ...)` and `generate([short, long], ...)`'s continuation for
`short` disagreed, and transformers' own right-padding warning fired.

**Same script, after the fix:**
```
$ PYTHONPATH=. external/probe-env/bin/python /tmp/repro_f1.py
alone short:  'ไฮappingspcb鳟ที่น่าสนใจ regenerated'
mixed short:  'ไฮappingspcb鳟ที่น่าสนใจ regenerated'
SAME
```
No right-padding warning; the batched and solo continuations for the short
text now agree exactly.

**A10/A11 rerun** (ticket's own script, verbatim, probe-env interpreter,
`PYTHONPATH=.`):
```
score 2 2 True 256 True
gen 1 True
save ['backbone', 'call_sep', 'labels', 'max_len', 'param_only', 'train_key', 'tuning'] True
forward (2, 2) 64
```
Matches the ticket's expected output exactly. Pass.

**A12 rerun** (LoRA merge, ticket's own script, verbatim):
```
7 lora targets ['down_proj', 'gate_proj', 'k_proj', 'o_proj', 'q_proj', 'up_proj', 'v_proj']
merge allclose True
no adapter file True
tuning lora
```
Matches exactly. Pass (confirms the fix, scoped to `generate()`, left
`load()`/`save()`/LoRA merging untouched).

**A1 rerun** (import check under all four interpreters):
```
ok
ok
ok
ok
```
Pass.

**A16 rerun** (annotation/literal rules; same one-line patch to the check
script's own `ast.Import`/`.module` bug documented in section 2 above, not
re-litigated here):
```
A16 ok (with the AttributeError line patched to handle plain `import` nodes)
```
```
$ grep -n "/home/\|/net/" models/*.py models/agent_models/*.py models/probe_models/*.py || echo NO_ABS_PATH
NO_ABS_PATH
```
Pass.

`run.py selfcheck` still does not exist on this branch (`ls run.py` fails);
not run, same as round 1.

### 5.3 Commit

```
$ git -C /home/y-guo/reproduce/new1 log --oneline -1 ticket/2026-09-17-wave2/T06
7d2f53f T06: fix Probe.generate() right-padding corrupting shorter batched texts
```
One commit, on top of `fde660f`, touching only
`models/probe_models/base.py`.

### 5.4 Self-review and open questions

- The fix is scoped to the one line finding F1 named; nothing else in
  `base.py`, `qwen.py` or `gptoss.py` changed.
- `score()`'s reliance on right-padding is now load-bearing in a way it
  wasn't spelled out to be before this round (its `attention_mask.sum(dim=1)
  - 1` formula only locates the true last token because the tokenizer's
  *default* padding side is right); I left it as is, since changing that
  default would be a scope change beyond F1 and `score()` was never broken.
  Flagging in case a later ticket ever changes `qwen.prepare_tokenizer`'s
  `padding_side` default without noticing `score()` depends on it.
- No new test file added — same reasoning as round 1 (spec section 2's
  `tests/` exceptions don't cover this file), and F1's fix is covered by the
  reproduction script plus the rerun acceptance commands above.
- No other open findings from this round; F1 was the only one in scope.
