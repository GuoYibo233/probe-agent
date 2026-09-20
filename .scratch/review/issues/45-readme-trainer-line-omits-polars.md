# 45 README's trainer.py annotation omits polars from its imports

Status: needs-triage
Severity: minor
File: README.md:253
Contract: 0.1 (the five-line annotation format), 0.2 (the tree's annotation lines)
Errata: touched by "0.2 (`train/utils/trainer.py` third-party imports): `[torch, peft]` -> `[torch]`; LoRA lives in `models/probe_models/base.py` and the LR schedule is a `torch.optim.lr_scheduler.LambdaLR`" — that entry took `peft` off the line; it did not rule on `polars`, which the file imports

## Finding

README section 2's entry for the trainer states its third-party imports as
`torch` alone:

```
train/utils/trainer.py — the training loop every method shares: ...
  imports: experimental_settings/schema.py, models/__init__.py, models/probe_models/base.py, data/training_data.py, data/probe_output.py, jobs/registry.py; [torch]
```
(`README.md:252-253`)

The file imports polars at module level and uses it in four places:

```python
import polars as pl
import torch
```
(`train/utils/trainer.py:13-14`)

`pl.DataFrame` in the signature of `_dropped_overlong_events`
(`train/utils/trainer.py:110`) and of `_run_alignment_gate`
(`train/utils/trainer.py:442`), `pl.col` for the split filters
(`train/utils/trainer.py:227-228`, `:415`, `:425-428`), and `pl.DataFrame` for
the prediction frame (`train/utils/trainer.py:423`). Every other file that
imports polars carries it in its own bracket list — `data/training_data.py`
(`README.md:132`), `data/probe_output.py` (`README.md:139`),
`data/build_training_dataset.py` (`README.md:153`), `eval/score_run.py`
(`README.md:290`).

`run.py selfcheck`'s check 2 compares the repo-file fragments of the line
against the `ast` import graph and ignores the bracketed third-party list
(errata "wave-6 precheck, ticket 15": a fragment counts as an entry only when
the whole trimmed fragment is a repo file path), so nothing on the machine
catches this.

## Failure scenario

README section 2 is the tree's index and the statement the extension recipes of
section 3 are followed against. An agent or a person sizing the `probe` venv
from these lines — the venv `train/utils/trainer.py` declares at
`README.md:257` — reads that the trainer needs torch and not polars, so a venv
rebuild that installs the listed packages produces an environment in which
`external/probe-env/bin/python -m train.methods.ctool --run-dir <dir>` fails at
import with `ModuleNotFoundError: No module named 'polars'`, before the run
reaches its first beat. The same line is what a reader consults to decide
whether a change to `data/training_data.py`'s polars schema reaches the
trainer.

## Proposed fix

Write the file's real third-party imports on its own README line: change the
bracket list at `README.md:253` from `[torch]` to `[polars, torch]`, the order
the neighbouring entries use (alphabetical inside the brackets, as at
`README.md:153`). The repo-file half of the line is already correct and stays
as it is.
