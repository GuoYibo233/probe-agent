# Wave 5 post-merge fix — `models/probe_models/base.py` (SEAMS-6, SEAMS-7)

Base `9c3b963` (the tree of `df3c473` plus the untracked review record, which that commit
added; `git diff df3c473 9c3b963` touches only
`.scratch/from-zero/sdd/2026-09-18-wave5/post-merge-review.json`). Branch
`fix/2026-09-18-wave5-probe`, head `5298502`, one commit. Worktree
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave5-fix-probe-r1` (removed at the end; the branch
stays). One file changed: `models/probe_models/base.py`. `README.md` is untouched — its
`base.py` block states the file's sentence, imports, used-by, reads, writes and venv, and none
of the six changed.

Every command below was run from the worktree root with
`PYTHONPATH=<worktree>` and the interpreter
`/home/y-guo/reproduce/new1/external/probe-env/bin/python` (`external/` is git-ignored and is
not materialised in a worktree, errata entry "0.1 (the interpreter in an acceptance command)").
The "before" runs use the same scripts against the main tree at `9c3b963`, read-only. No GPU
process was started: the one cuda measurement wraps `from_pretrained` so it records the dtype it
was asked for and raises before `base.load` reaches `instance.to(device)`.

---

## SEAMS-6 — a LoRA run could not resume

### Root cause

`load` built the peft adapter only on the fresh path:

```python
    lora = None
    if ckpt_dir is None:
        if tuning == "full":
            ...
        elif tuning == "lora":
            lora = peft.get_peft_model(model, peft_cfg)
```

`ckpt_dir` says where the weights come from; it does not say which form of probe is being
built. `trainer.run` restores twice with the model row and the frozen setting in hand (the
resume from `last/` at `trainer.py:176-177` and the reload of `best/` before the prediction step
at `:323-325`), so both restores fell into the branch written for the probe service. A restored
LoRA probe therefore had `lora=None`, `trainable_parameters()` returned every backbone and head
tensor instead of the adapter's, and `opt.load_state_dict(torch.load(last/optimizer.pt)["opt"])`
at `trainer.py:223` raised. `grad_checkpointing(True)` also skipped
`enable_input_require_grads()` on every resume, since that call is guarded on `self.lora`.

### The change

The tuning is now built whenever the frozen setting is given, restore or not, with the tuning
value read off the checkpoint's own `meta.json` on a restore (`meta["tuning"]`, already read at
the top of `load`). The four `lora_*` hyperparameters live in `cfg.probe` and nowhere else, so
the frozen setting is what a load needs to rebuild the adapter; a load handed no frozen setting
is the served form and serves the merged weights.

```python
    lora = None
    if cfg is not None:
        if tuning == "full":
            ...
```

`save()` is untouched: it still deep-copies the wrapper, merges and writes full weights with no
`adapter_*` file, as ticket 06 pins. Because peft initialises B at zero, the adapter a restore
rebuilds over those merged weights leaves the model's outputs exactly where the saved probe left
them (measured below: max abs logit difference 2.4e-07 for the classifier, 0.0 for the
generator).

### The finding's own repro, rerun

`/tmp/seams6_repro.py` (the verifier's script: a LoRA classifier through the real `base.load`,
`Probe.save` into `last/`, `torch.save` of the optimizer state, then the restore and
`opt.load_state_dict`).

Before, at `9c3b963`:

```
first launch : lora wrapper is None? False | trainable tensors: 30
checkpoint   : meta.tuning = lora | adapter files: []
after resume : lora wrapper is None? True | trainable tensors: 26
RESULT       : ValueError: loaded state dict contains a parameter group that doesn't match the size of optimizer's group
control full : load_state_dict succeeded, 26 -> 26 tensors
```

After, on `fix/2026-09-18-wave5-probe`:

```
first launch : lora wrapper is None? False | trainable tensors: 30
checkpoint   : meta.tuning = lora | adapter files: []
after resume : lora wrapper is None? False | trainable tensors: 30
RESULT       : load_state_dict succeeded (no crash)
control full : load_state_dict succeeded, 26 -> 26 tensors
```

### The CPU LoRA save / restore / resume round trip

`/tmp/wave5fix-probe/lora_resume_roundtrip.py` walks `trainer.run`'s sequence with the tickets'
tiny two-layer 64-hidden Qwen3: three real optimizer steps over `Probe.forward`, the checkpoint
`trainer.py:296-300` writes, the restore at `:176-177`, the optimizer and scheduler load at
`:218-224`, one more step, and one more save.

```
first launch : backbone dtype torch.float32 | adapter built: True | trainable tensors: 30
first launch : losses [0.944, 0.55575, 0.40883] | lr now 0.000125
checkpoint   : meta.tuning lora | adapter files [] | full weights ['model.safetensors']
after resume : backbone dtype torch.float32 | adapter built: True | trainable tensors: 30
after resume : trainable shapes equal the pre-crash list: True
after resume : optimizer state loaded, groups 30 | step counter 3 | lr 0.000125
after resume : restored logits equal the saved probe's: True | max abs diff 2.384185791015625e-07
resumed step : loss 0.32824 (the fourth step of the run)
resumed save : adapter files [] | full weights ['model.safetensors'] | head.pt True
```

The optimizer state loads with its 30 tensors and its step counter 3, the scheduler resumes at
the learning rate it had, the loss goes on falling (0.40883 -> 0.32824), and the next checkpoint
is merged full weights again.

The generator half of the same path (the reload of `best/` before the prediction step for a
cgen/cparam run whose tuning is lora), `/tmp/wave5fix-probe/generator_lora_restore.py`:

```
restored generator: adapter built: True | backbone dtype torch.float32 | trainable tensors 28 (fresh: 28 )
restored generator: forward (2, 151936) | equals the saved probe: True | max abs diff 0.0
restored generator: generate 1 True
```

---

## SEAMS-7 — a restored checkpoint came back in the serving dtype

### Root cause

```python
    dtype_name = row["dtype"] if ckpt_dir is None else (
        backbone_module.DTYPE if str(device).startswith("cuda") else "float32")
```

Ticket 06 (lines 306-307) and errata entry "6.2" both scope the serving-dtype rule to **a
restore with no row**; the code keyed it on `ckpt_dir` alone and never looked at `row`. Both of
`trainer.run`'s restoring calls pass `cfg.models.probe_row` and `device="cuda"` on a card, so a
resumed run switched from the row's float32 to `qwen.DTYPE` (bfloat16) mid-run: a silent
numerics change for ctool and a hard failure for cgen/cparam, whose `Probe.forward` generator
branch casts the picked hidden state to float32 and feeds a bfloat16 `lm_head`.

### The change

The dtype is the model row's whenever a row is given, restore or not. The served form
(`models/probe_models/service.py`, which calls `base.load(None, None, ..., ckpt_dir=..., device=...)`)
is handed no row and keeps its own choice: the family's `DTYPE` on a card, float32 on the cpu.

```python
    dtype_name = row["dtype"] if row is not None else (
        backbone_module.DTYPE if str(device).startswith("cuda") else "float32")
```

This is also the sentence `qwen.DTYPE` already carries on its own line: "the restore/serving
dtype; a row's result.dtype overrides at training".

### The finding's own repro, rerun

`/tmp/seams7/dtype_select.py` (the verifier's script: what dtype `base.load` asks
`from_pretrained` for, on each path, for the calls `trainer.run` makes — always with a row).

Before, at `9c3b963`:

```
checkpoint weights dtype on disk: torch.float32
classifier fresh  (ckpt_dir=None)  device=cpu  -> torch.float32
classifier fresh  (ckpt_dir=None)  device=cuda -> torch.float32
classifier restore(ckpt_dir=best/)  device=cpu  -> torch.float32
classifier restore(ckpt_dir=best/)  device=cuda -> torch.bfloat16
generator  fresh  (ckpt_dir=None)  device=cpu  -> torch.float32
generator  fresh  (ckpt_dir=None)  device=cuda -> torch.float32
generator  restore(ckpt_dir=best/)  device=cpu  -> torch.float32
generator  restore(ckpt_dir=best/)  device=cuda -> torch.bfloat16
```

After:

```
checkpoint weights dtype on disk: torch.float32
classifier fresh  (ckpt_dir=None)  device=cpu  -> torch.float32
classifier fresh  (ckpt_dir=None)  device=cuda -> torch.float32
classifier restore(ckpt_dir=best/)  device=cpu  -> torch.float32
classifier restore(ckpt_dir=best/)  device=cuda -> torch.float32
generator  fresh  (ckpt_dir=None)  device=cpu  -> torch.float32
generator  fresh  (ckpt_dir=None)  device=cuda -> torch.float32
generator  restore(ckpt_dir=best/)  device=cpu  -> torch.float32
generator  restore(ckpt_dir=best/)  device=cuda -> torch.float32
```

The two lines the finding named, the cuda restores, now read `torch.float32`, the dtype of the
row they were handed; the six others are what they were.

The second half of the finding's repro, `/tmp/seams7/forward_dtype.py`, builds its probes by
hand and is unchanged by this fix; it is what says why the dtype matters, so it is rerun as
recorded:

```
ctool   backbone=torch.float32    -> loss 4.42784
ctool   backbone=torch.bfloat16   -> loss 4.42732
cgen    backbone=torch.float32    -> loss 71.26468
cgen    backbone=torch.bfloat16   -> RuntimeError: expected m1 and m2 to have the same dtype, but got: float != c10::BFloat16
cparam  backbone=torch.float32    -> loss 71.58787
cparam  backbone=torch.bfloat16   -> RuntimeError: expected m1 and m2 to have the same dtype, but got: float != c10::BFloat16
```

With the fix, `base.load` never hands the trainer the bfloat16 arm of that table.

### The served form is unchanged

`/tmp/wave5fix-probe/served_form.py` makes `models/probe_models/service.py`'s own call,
`base.load(None, None, probe_kind=..., ckpt_dir=<ckpt>/best, device=...)`, over a checkpoint
whose `meta.json` records `tuning: lora`:

```
serving fixture: meta.tuning lora | family serving DTYPE bfloat16
served form: classifier device=cpu  -> torch.float32
served form: classifier device=cuda -> torch.bfloat16
served form: generator  device=cpu  -> torch.float32
served form: generator  device=cuda -> torch.bfloat16
served form: adapter built: False False | backbone dtype torch.float32
served form: /score 2 2 True | /gen 1 True
```

Both halves of the service's behaviour are kept: bfloat16 on a card, float32 on the cpu, and the
merged weights with no adapter even though the checkpoint was trained with LoRA.

---

## VERSION

`VERSION` goes 1 -> 2 with one `VERSION_HISTORY` entry, `stale: ("train",)`. A fresh train run
is byte-for-byte what it was (a load with `ckpt_dir=None` takes the same dtype and the same
tuning as before), but every train run reloads `best/` before its prediction step, and that
reload now comes back in the row's dtype and with its adapter, so `predictions.parquet` from a
GPU run would differ. The stage table lists `models/probe_models/base.py` on the `train` and
`inject` rows; the probe service's own load is unchanged, so the inject row's outputs are
untouched and inject's effective version stays 1.

```
$ "$PR" -c "import models.probe_models.base as b; print('base VERSION', b.VERSION, 'history', b.VERSION_HISTORY)"
base VERSION 2 history {2: {'why': "A restore that is handed the model row and the frozen setting keeps the row's dtype and rebuilds the adapter its tuning names, so a resumed run and the reload of best/ before the prediction step carry the form the fresh load built.", 'stale': ('train',)}}

$ "$PR" -c "
from experimental_settings import schema
print('history', schema.version_history('models/probe_models/base.py'))
for st in ('train','inject'):
    print(st, 'effective', schema.effective_version('models/probe_models/base.py', st))
"
history {2: {'why': "A restore that is handed the model row and the frozen setting keeps the row's dtype and rebuilds the adapter its tuning names, so a resumed run and the reload of best/ before the prediction step carry the form the fresh load built.", 'stale': ('train',)}}
train effective 2
inject effective 1
```

What the bump moves, measured on both trees with `run.py where ... --debug`:

```
$ for S in train eval; do echo "-- $S"; "$PR" run.py where train_probe ctool_qwen3_0pt6b $S --debug; done
-- train (worktree, VERSION 2)
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/train/22a0980de899
-- eval (worktree, VERSION 2)
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/eval/61c95c5e5d9e
== same at HEAD ==
-- train (HEAD, VERSION 1)
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/train/79f74a7f74d0
-- eval (HEAD, VERSION 1)
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/eval/a8b67d485d63

$ "$PR" run.py where inject probe_p1_e1_theta_0pt80 inject --debug
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/inject/d6e2ebd3d7f4
== HEAD ==
/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/debug/inject/0526b23c02b4
```

`base.py` is not on the eval row of the stage table at all (that row lists
`eval/utils/probe_eval.py` and `data/probe_output.py`), and its effective version for inject is
1, so the eval and inject keys move only through the keys they fold. The full inject key payload
diffed between the two trees (`/tmp/wave5fix-probe/key_payload.py`):

```
22,24c22,24
<   "probe_gen.train": "7d2b29f8d708",
<   "probe_score.eval": "834b3a696768",
<   "probe_score.train": "d54f9e0199cc"
---
>   "probe_gen.train": "df43b5d7c091",
>   "probe_score.eval": "a4a903bff5de",
>   "probe_score.train": "61b4c576b703"
43c43
< inject key: d6e2ebd3d7f4
---
> inject key: 0526b23c02b4
```

Its `fields`, `models` and `versions` blocks are identical; only the three train and eval keys
it points at moved. No run directory exists yet, so nothing is orphaned.

---

## Acceptance commands rerun

The changed file is `models/probe_models/base.py`, whose ticket is 06; the wave-5 tickets touch
it only by importing it. Ticket 06's acceptance items that exercise this file are A10, A11, A12
and A16 (A1 covers the `venv: any` files and explicitly excludes `base.py`). From ticket 13, A3.2
(the import) and A3.6 (the permanent test over `Probe.forward`) load it; A3.3, A3.4 and A3.5
stub `base.load` or `Probe` out entirely.

### A10 + A11 — the probe object on a tiny CPU checkpoint (ticket 06)

```
score 2 2 True 256 True
gen 1 True
save ['backbone', 'call_sep', 'labels', 'max_len', 'param_only', 'train_key', 'tuning'] True
forward (2, 2) 64
```

Exactly the ticket's expected four lines. (transformers also prints a `Qwen3Model LOAD REPORT`
noting `lm_head.weight | UNEXPECTED`, which is the fixture's causal-LM checkpoint read back as an
`AutoModel`, not part of the check.)

### A12 — the LoRA merge equals the base on a fresh adapter (ticket 06)

```
7 lora targets ['down_proj', 'gate_proj', 'k_proj', 'o_proj', 'q_proj', 'up_proj', 'v_proj']
merge allclose True
no adapter file True
tuning lora
```

Exactly the ticket's expected four lines.

### A16 — the annotation and literal rules (ticket 06)

Run verbatim, the script raises before it reaches any assertion about `base.py`:

```
Traceback (most recent call last):
  File "<stdin>", line 10, in <module>
  File "<stdin>", line 10, in <listcomp>
AttributeError: 'Import' object has no attribute 'module'
NO_ABS_PATH
```

This is the defect ticket 06's own Comments record ("`A16` reads `.module` on an `ast.Import`
node"), not a consequence of this change: the same line fails the same way at `9c3b963`.

```
$ python3 -c "...a.module or a.names[0].name for a in g.body..."   # at HEAD
HEAD, same line, same failure: AttributeError 'Import' object has no attribute 'module'
```

Rerun with that one line corrected to
`a.module if isinstance(a, ast.ImportFrom) else a.names[0].name`, everything else verbatim:

```
A16 ok
NO_ABS_PATH
```

So `base.py` still imports `models` and neither `experimental_settings` nor `jobs`, still carries
exactly one column-zero `VERSION`, and still holds no `/home/` or `/net/` path.

### A3.2 — import under the probe venv (ticket 13)

```
1 classifier generator generator True
```

### A3.6 — the permanent packed-loss test (ticket 13)

```
test_cgen (tests.test_packed_loss.TestPackedLoss.test_cgen) ... ok
test_cparam (tests.test_packed_loss.TestPackedLoss.test_cparam) ... ok
test_ctool (tests.test_packed_loss.TestPackedLoss.test_ctool) ... ok

----------------------------------------------------------------------
Ran 3 tests in 2.275s

OK
```

`run.py selfcheck` was not run: it is a stub on this branch
(`run.py:459-460`, "selfcheck arrives in ticket 15").

---

## Decisions the requirements did not make

1. **How the served form asks for the serving dtype.** SEAMS-7's guidance says to give the
   service "an explicit way to ask for the serving dtype rather than by inferring from device",
   and my area is `base.py` alone — a new keyword would have to be passed from
   `models/probe_models/service.py`, which I may not edit. The explicit channel is therefore the
   one ticket 06 and errata entry "6.2" already pin: **a load with no row** takes the family's
   serving dtype (on a card) and float32 (on the cpu). The service already calls
   `base.load(None, None, ...)`, so its behaviour is unchanged and the wrong test (the device
   string) is gone. If the owner wants a named keyword instead, it is a two-line follow-up in
   `base.py` plus the two call sites in `service.py`.
2. **What tells a restore which form to build.** The tuning is rebuilt when `cfg` is given and
   the dtype comes from `row`; each condition names the object it reads its value from
   (`cfg.probe.lora_*`, `row["dtype"]`). The trainer passes both and the service passes neither,
   so the two forms stay separated without a new parameter.
3. **The tuning value on a restore comes from the checkpoint's `meta.json`**, not from
   `cfg.probe.tuning` — per SEAMS-6's guidance ("read the checkpoint's meta to know the
   tuning"). On a resume the two agree (the frozen setting is the same run's), and the
   `meta.json` value is what the weights on disk were produced with. A `meta.json` whose
   `tuning` is neither `full` nor `lora` now raises the same `ValueError` a bad
   `cfg.probe.tuning` raises; the message keeps the words `probe.tuning:` because
   `meta["tuning"]` records exactly that field.
4. **`VERSION` 2 with `stale: ("train",)`**, reasoned above. The alternative readings were no
   bump (wrong: a train run's `predictions.parquet` would change on a card) and a bump with no
   `stale` (needlessly stales sample, build, inject and score, none of which changes).
5. **The predict-only reload of `best/` now also rebuilds an adapter** when the run's tuning is
   lora. It costs the adapter's memory for the prediction pass and changes no number (peft's B
   is zero-initialised over already-merged weights; measured 0.0 max abs difference for the
   generator, 2.4e-07 for the classifier after three training steps). Keeping one rule for
   every restore is what removes the class of bug SEAMS-6 and SEAMS-7 are two instances of, so I
   did not special-case the prediction reload.
6. **A second defect fixed by the same line, not separately reported:** `grad_checkpointing(True)`
   guards its `enable_input_require_grads()` call on `self.lora`, so before this change a
   resumed LoRA run with `train.grad_ckpt` on would have built no graph through the adapter. It
   is gone because the restored probe now carries its adapter.

## Open, for the reviewer

- `Probe.save` on a restored LoRA probe merges an adapter whose B is zero into weights that were
  already merged, so a run that is interrupted and resumed many times accumulates no adapter
  state across incarnations: each incarnation trains a fresh adapter over the previous one's
  merged weights. That is what ticket 06's "LoRA was merged at save time, so a restore is a
  plain `from_pretrained`" prescribes, and the optimizer state now matches it tensor for tensor;
  whether a long LoRA run should instead carry its adapter across a resume (keeping the
  optimizer moments attached to the same A and B matrices) is the owner's call and would change
  the checkpoint layout 1.6 pins.
