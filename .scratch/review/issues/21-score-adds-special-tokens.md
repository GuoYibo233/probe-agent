# 21 Probe.score tokenizes with special tokens while every training path tokenizes without them

Status: needs-triage
Severity: important
File: models/probe_models/base.py:136-137
Contract: 6.2 (`Probe.score`: "the served form of the same rule `event_end` carries on the packed path")
Errata: not recorded

## Finding

`Probe.score` leaves `add_special_tokens` at the tokenizer's default, which is
True:

```python
133     def score(self, texts: list[str]) -> tuple[list[list[float]], list[str]]:
134         """The class logits in labels order and the argmax class name, one event per text at its last token."""
135         device = next(self.backbone.parameters()).device
136         enc = self.tokenizer(texts, truncation=True, max_length=self.max_len, padding=True,
137                              return_tensors="pt")
```

Every path that produced the weights it scores with passes False:
`train/methods/ctool.py:60`, `:66`, `:231` and `:236` all tokenize the probe
text with `add_special_tokens=False`, and so do `cgen.py:60,66,73`,
`cparam.py:75,86,92` and `train/utils/trainer.py:115`. `Probe.generate`, eleven
lines below `score` in the same file, also passes it:

```python
163             enc = self.tokenizer(prompts[i:i + GENERATE_BATCH], add_special_tokens=False,
```

So `score` is the one place in the repo that shows the backbone a sequence
built by a different rule from the one it was trained on.

Today's backbone hides it. Measured on 2026-09-21 with
`external/probe-env/bin/python` against
`/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base`: for the text
`call apis.example.sample_api()` both settings give the same 6 ids, and
`bos_token_id` is None. Measured on
`/net/tokyo100-10g/data/str01_01/y-guo/models/LFM2.5-350M-Base`, which
`constants/path_models.yaml` already registers as `lfm2.5-350m-base`: the same
text gives 9 ids without special tokens and 10 with, the extra one being
`bos_token_id = 1` at the front.

## Failure scenario

Extension recipe 6 in `README.md:377-381` says a new probe backbone is
`models/probe_models/<backbone>.py` plus one row in `models/table.yaml` and one
in `constants/path_models.yaml`. Add `lfm2` that way and train a `ctool` probe
on it: `train/methods/ctool.py` packs every event with
`add_special_tokens=False`, so the classifier never sees id 1, and the
alignment gate passes because `loss` and `reference_loss` tokenize the same way.
`eval/utils/probe_eval.py` fits the temperature and theta over
`predictions.parquet`, which `ctool.predict` also produced through the packed
path (errata "6.2 (`Probe.score` and `predict`)"). The inject run then serves
that checkpoint, and every `POST /score` goes through `Probe.score`, which
prepends id 1 to the probe text. The probe is queried off its training
distribution at every live cut: `conf` moves, the theta frozen from the eval
report no longer sits where the report put it, the fire rate changes, and
nothing reports a difference — `/health` matches, `check` passes, the train keys
match, and the only visible trace is a fire rate that does not reproduce the
eval report's coverage.

## Proposed fix

Tokenize the served text by the same rule the trained text was tokenized with:
add `add_special_tokens=False` to the call at
`models/probe_models/base.py:136`, so `score`, `generate` and every method's
`batches` state one rule. The three lines the change touches are
`score`'s tokenizer call only; no checkpoint, key or report shape moves, and on
Qwen3 the ids are identical (measured above), so no existing output changes and
no `VERSION` bump is owed.
