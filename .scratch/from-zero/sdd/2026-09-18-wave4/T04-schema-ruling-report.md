# T04 — owner-ruling round 1 (schema)

Ticket: `.scratch/from-zero/issues/04-setting-schema-and-loader.md`
Branch: `ticket/2026-09-18-wave4/T04-schema-ruling`
Base: `d1a4e60ffb50436bd4a8d7e8a3df5b194e71fe54` (tip of `from-zero` at dispatch)
Head: `ba97dd919180cb046d5bbd2031e75cbb9f99ff37` (commit `T04: apply owner rulings 7 and 8 to the setting schema`)

## What was done

Two owner rulings applied to `experimental_settings/schema.py`, each at its
root, no special case, no other file touched.

**RULING-7 — `train.warmup_ratio` defaults to 0.05.**
The `Train` dataclass default changed from `0.0` to `0.05` (the old trainer's
hard-coded warmup share); the comment stays a plain description of the field,
unchanged. Because the schema's key is computed as the diff from the
defaults (contracts 3.3), this single-line change means a setting that
writes `warmup_ratio: 0.05` explicitly is now indistinguishable from one that
does not set it at all — both key identically and neither field appears in
`fields_of`. Verified directly (see D1 below): overriding `train.warmup_ratio`
to `0.05` on top of an unset baseline setting produces the same `train` key
as the baseline.

**RULING-8 — `inject.chunk_tokens` and `inject.tail_tokens` removed.**
Both fields deleted from the `Inject` dataclass, and their two dotted names
deleted from `STAGES["inject"]["sections"]` (the line was previously at
roughly lines 265-270; the file has since renumbered slightly, but the
dotted-name list is the only place both fields appeared beyond the dataclass
itself). A grep of the whole file after the edit finds no remaining mention of
either name in a docstring, comment, axis, or check. A fixture-tree YAML that
sets `inject.chunk_tokens` is refused by the loader's existing unknown-field
check, naming the field: `SchemaError: inject.chunk_tokens: not a field of
this section` (transcript below). The owner's `experimental_settings/*.yaml`
were not opened by this ticket; the main session's earlier grep (cited in the
ruling) already established neither file mentions either field, and this
ticket's own fixture-tree probe above independently confirms the loader-side
half of the claim (the field is refused, not silently accepted) without
touching those files.

No other line of `schema.py` changed. `README.md`'s `schema.py` entry names
no individual field of `Train` or `Inject`, so it needed no edit.

## How it was verified

All commands run from the worktree root
`/home/y-guo/reproduce/new1-wt/2026-09-18-wave4-T04-schema-ruling1`, fixture
built by the ticket's `mkfix.sh` script, copied under a fresh `mktemp -d`
directory (never written directly under `/tmp`) rather than at the ticket's
literal `/tmp/mkfix.sh` path.

### B1 — imports under all four interpreters, no repo import

```
$ for P in python3 $PR $AW $VL; do $P -c "import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.PROBE_TEXT_FIELDS)"; done
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
$ python3 -c "<the ast-import-scan script>"
['__future__', 'ast', 'dataclasses', 'hashlib', 'itertools', 'json', 'pathlib', 'typing', 'yaml']
```
Matches the ticket's expected output exactly, under all four interpreters
(`python3` 3.10.12, `probe-env` 3.11, `appworld/venv` 3.12, `vllm-env` 3.12).

### B2 — the defaults equal the contract table, adapted for the two rulings

The ticket's pasted `B2` command asserts
`(i.split, i.arm, i.format, i.max_cuts, i.max_new, i.chunk_tokens,
i.tail_tokens, i.store_token_ids) == (['test'],'probe','p1_e1',64,96,64,1024,True)`
— this line names `i.chunk_tokens` and `i.tail_tokens`, which RULING-8 removed,
so it now raises `AttributeError` verbatim. **This is expected under the
ruling and the ticket text is not edited**; the check below is the same
assertion with the two removed fields dropped from the tuple and an explicit
`not hasattr` in their place, plus the new `warmup_ratio` default added:

```
$ python3 -c "<B2, adapted>"
defaults ok (ruling-7 warmup_ratio=0.05, ruling-8 chunk_tokens/tail_tokens removed)
```

### B3 — `STAGES` shape

```
$ python3 -c "<B3 verbatim>"
[('sample', 8, True, 'map'), ('build', 6, False, 'any'), ('train', 7, True, 'probe'), ('eval', 3, False, 'any'), ('inject', 14, True, 'map'), ('score', 2, False, 'any')]
carry: [('inject', 'probe_score.eval')]
inject sections count: 16
```
Matches the ticket's expected tuple list and `carry` line exactly — B3 checks
the `versions` list length and cell shape, not the dotted `sections` count, so
it is unaffected by RULING-8. (The dotted-name count for `inject` dropped
from 18 to 16, printed above as a direct check of the ruling; not part of the
ticket's pasted B3 expectation.)

### B4 — axis literals against what is on disk

Run against the real repo tree (not the fixture), as the ticket's script
does. One sub-check does not run: `agent/inject_format.py`'s `FORMATS` values
are `Format(...)` call expressions, not `ast.literal_eval`-able literals, so
that one line raises `ValueError: malformed node or string` before reaching
this ticket's schema code. **This is a pre-existing condition, unrelated to
either ruling** — reproduced identically by running the same script against
`schema.py` at the unmodified base commit `d1a4e60` (i.e., before either
ruling was applied). It is also already flagged by wave 2's closeout comment
on this ticket ("`B4`'s 'constants only' expectation... more axis checks can
run after the wave merge"). Every other sub-check (`data.env`,
`data.instructions`, `sample.split`, `probe.method`, `inject.arm`,
`constants/path_datasets.yaml`, `inject.split`) passes:

```
$ python3 -c "<B4, FORMATS sub-check skipped>"
axis checks that could run: all except inject.format (FORMATS not literal, out of ticket scope)
```

### B5 — the two source-text readers

```
$ python3 -c "<B5 verbatim>"
7 ['<|return|>']
two matches -> SchemaError two.py: 2 column-zero assignments to 'VERSION', expected exa
no match -> SchemaError none.py: no column-zero assignment to 'VERSION'
```
Matches expected exactly; unaffected by either ruling.

### C1 — the flagship load

```
$ FIX=$(bash mkfix.sh); python3 -c "<C1 verbatim, plus a warmup_ratio print>"
ctool_qwen3_0pt6b ['sample', 'build', 'train', 'eval'] False
appworld v1 gpt_oss_120b qwen3_0pt6b
gptoss ['dtype', 'env_result', 'extra_flags', 'family']
['<|return|>'] high 2026-08-06
ctool None 1e-05 None
inject is None: True | build present: True
warmup_ratio (ruling-7): 0.05
```
Matches the ticket's expected output exactly on every pasted line; the added
line confirms the new default flows through the loader.

### C2 — debug overlay

```
$ python3 -c "<C2 verbatim>"
True 3 1 6 8 64 20 100 50
3 None None None
```
Matches expected exactly.

### C3 — overrides and the sweep

```
$ python3 -c "<C3 verbatim>"
0.0003 lora [42, 67]
4
['ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0001,train.seed=67', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=42', 'ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67']
[0.0001, 0.0001, 0.0003, 0.0003]
ctool_qwen3_0pt6b/train.lr=0.0003,train.seed=67 0.0003 67
```
Matches expected exactly.

### C4 — the 18 refusals of 5.7

All 18 lines still `REFUSED`, each naming the same field as the ticket lists
(`train.lrr`, `probe.method`, `data.instructions`, `sample.split`,
`models.probe`, `generation.effort`, `inject`, `train.lr`,
`train.max_steps`, `train.lr`, `eval.theta_from` twice, `probe`,
`models.probe`, `inject.theta`, `inject.probe_gen`, `inject.fire_nth_cut`,
`score.baseline`), transcript:
```
unknown key: REFUSED SchemaError: train.lrr: not a field of this section
off-axis value: REFUSED SchemaError: probe.method: 'ctoool' is not one of ('ctool', 'cgen', 'cparam')
bad instructions: REFUSED SchemaError: data.instructions: 'v9' is not one of ('v1',)
bad split: REFUSED SchemaError: sample.split: 'holdout' is not one of ('train', 'dev', 'test')
wrong role: REFUSED SchemaError: models.probe: 'gpt_oss_120b' has role 'agent', expected 'probe'
bad effort: REFUSED SchemaError: generation.effort: 'ultra' is not one of ('high', 'medium', 'low')
section not in workflow: REFUSED SchemaError: inject: no stage of this file's workflow reads this section
type mismatch: REFUSED SchemaError: train.lr: '1e-5' has type str, declared type is float
sweep over debug field: REFUSED SchemaError: sweep.train.max_steps: also set by debug.yaml, which would collapse the sweep
override of swept field: REFUSED SchemaError: train.lr: overridden and swept at once
missing reference: REFUSED SchemaError: eval.theta_from: nope: no such setting in .../train_probe.yaml
generator without theta_from: REFUSED SchemaError: eval.theta_from: is required when probe.method's PROBE_KIND is generator
probe section under inject: REFUSED SchemaError: probe: no stage of this file's workflow reads this section
models.probe under inject: REFUSED SchemaError: models.probe: a setting whose workflow contains inject may not state models.probe; an inje...
theta unset: REFUSED SchemaError: inject.theta: is required and was not set
probe_gen is a param-only method: REFUSED SchemaError: inject.probe_gen: 'cparam' is not a whole-call generator (param_only=True, PROBE_KIND='gen...
fire_nth_cut under no_probe: REFUSED SchemaError: inject.fire_nth_cut: must be 0 under arm: no_probe
baseline seeds not a superset: REFUSED SchemaError: score.baseline: baseline split/seeds are not a superset of this setting's inject.split/see...
```
Unaffected by either ruling. In addition, a fixture-tree YAML setting
`inject.chunk_tokens: 64` under an inject setting was refused the same way,
naming the field — the acceptance criterion RULING-8 states explicitly:
```
ruling-8 removed field write: REFUSED SchemaError inject.chunk_tokens: not a field of this section
```

### D1 — key shape and the 3.2 guarantees, plus a direct RULING-7 check

```
$ python3 -c "<D1 verbatim, plus a warmup_ratio-restated check>"
{'sample': '5e898c2e7741', 'build': 'aa9b69a5cc81', 'train': '164b861c2128', 'eval': '080ad7ce7314'}
determinism: True
debug separates: True
notes insensitive: True
default restated == unset: True
lr moves train, not sample/build: True True True
eval.risk moves eval only: True True
fields block: []
models block: ['probe'] []
upstream block: {'sample': '5e898c2e7741'} {}
ruling-7, restating new default 0.05 == unset: True
```
Matches the ticket's expected shape (four 12-hex keys, all booleans `True`,
`fields block` holding only non-default fields — empty here since nothing
else was overridden). The added line is the direct proof of RULING-7's
stated consequence: `train.warmup_ratio: 0.05` and an unset `warmup_ratio`
now key identically.

### D2 — the `VERSION` fold

```
$ python3 -c "<D2 verbatim>"
['data/probe_output.py', 'data/training_data.py', 'eval/methods/ctool.py', 'models/probe_models/base.py', 'models/probe_models/qwen.py', 'train/methods/ctool.py', 'train/utils/trainer.py']
['probe_gen.train', 'probe_score.eval', 'probe_score.train']
probe_eval VERSION moves the inject key: True
trainer VERSION moves train, not build: False True
```
The first three lines match the ticket's expected output. The fourth line
does not: the ticket expects `True True` (bumping `train/utils/trainer.py`'s
`VERSION` should move the `train` key); the observed first value is `False`.
**This is a pre-existing discrepancy, not caused by either ruling** —
reproduced identically running the same script against `schema.py`
unmodified at base commit `d1a4e60`. Left unfixed: out of this ticket's
scope (RULING-7 and RULING-8 only), and fixing it would touch code beyond
the two dataclasses and the `STAGES["inject"]["sections"]` list this ticket
is authorized to change. Flagged here as an open question for the owner/next
round.

### D3 — `run_dir`, `run_dir_of`, debug subtree

```
$ python3 -c "<D3 verbatim>"
train/164b861c2128 debug/train/135773a1db16
True True
nothing created: True
```
Shape matches expected (`train/<12 hex> debug/train/<12 hex>`, `True True`,
`nothing created: True`).

### D4 — `freeze`

```
$ python3 -c "<D4 verbatim, plus a warmup_ratio print>"
['data', 'generation', 'models', 'sample']
['_commit', '_debug', '_key', '_resolved', '_stage', '_upstream', '_versions']
sample True deadbeefcafe False {}
versions: ['agent/generate.py', 'agent/loop.py', 'data/environments/__init__.py'] 8
diff: True
no workflow line: True
seeds merged: [42, 67]
train projection: ['models', 'probe', 'train'] True
ruling-7, train section warmup_ratio: 0.05
collision: REFUSED freeze: .../outputs/train/164b861c2128 already holds settings fo...
```
Matches expected exactly on every pasted line. The added line confirms
`freeze` writes the new default (`0.05`) into `settings.yaml`'s `train`
section.

### D5 — `load_frozen`

```
$ python3 -c "<D5 verbatim>"
train True deadbeefcafe ctool 1e-05 8192
upstream: ['build'] | sections dropped: True
removed field: REFUSED train.obsolete_knob: field removed from the schema (run directory .../outputs/train/...
```
Matches expected exactly.

### D6 — B1 rerun after everything else

```
$ for P in python3 $PR $AW $VL; do $P -c "import experimental_settings.schema as S; print(S.__name__, len(S.STAGES), S.PROBE_TEXT_FIELDS)"; done
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
experimental_settings.schema 6 ('min_think', 'hist_rounds', 'probe_result_cap')
```
Matches expected.

`run.py` does not exist on this branch yet, so the implementer protocol's
`python3 run.py selfcheck` step does not apply. `tests/` has no reference to
`chunk_tokens`, `tail_tokens`, or `warmup_ratio` to update.

## Commit list

- `ba97dd9` — `T04: apply owner rulings 7 and 8 to the setting schema` (the only commit; `experimental_settings/schema.py` only, 2 insertions, 5 deletions).

## Self-review and open questions

- Diff is the minimal root-cause change both rulings ask for: one default
  value line, two field lines, and two dotted names in one tuple. No other
  file touched; `README.md`'s `schema.py` entry needed no edit since it
  names no individual `Train`/`Inject` field.
- Two ticket pasted-expectation lines are now outdated by these rulings and
  are **not** edited in the ticket, per instruction; both are called out
  above (B2's `i.chunk_tokens`/`i.tail_tokens` tuple; the D2 line does not
  reference either ruling and is a separate, pre-existing discrepancy — see
  next point).
- Open question for the owner: D2's `trainer VERSION moves train, not
  build` line prints `False True` instead of the ticket's expected `True
  True`, both on this branch and on the unmodified base commit. This is not
  a consequence of RULING-7 or RULING-8 and this ticket does not fix it, but
  it means `train/utils/trainer.py`'s `VERSION` is not currently folded into
  the `train` key the way 3.3's version rule requires — worth a look before
  it is relied on.
- B4's `inject.format` sub-check cannot run against the current tree
  (`agent/inject_format.py`'s `FORMATS` values are constructor calls, not
  literals); same pre-existing, out-of-scope situation as the D2 item above,
  already flagged by the wave 2 closeout comment.

## Owner rulings applied, round 1

| id | title | applied | key evidence |
|---|---|---|---|
| RULING-7 | `train.warmup_ratio` defaults to 0.05 | yes, `Train.warmup_ratio` default `0.0` -> `0.05`, comment unchanged | D1: `ruling-7, restating new default 0.05 == unset: True`; D4: frozen `train` section writes `warmup_ratio: 0.05` |
| RULING-8 | `inject.chunk_tokens` and `inject.tail_tokens` removed | yes, both fields deleted from `Inject`, both dotted names deleted from `STAGES["inject"]["sections"]`, no other mention left in the file | B2 (adapted): `not hasattr(i, 'chunk_tokens')` and `not hasattr(i, 'tail_tokens')` both hold; C4 (extra probe): a fixture YAML setting `inject.chunk_tokens: 64` is `REFUSED SchemaError inject.chunk_tokens: not a field of this section` |

Both rulings are applied at their root in `experimental_settings/schema.py`
only, with no special case and no other file changed. `RULING-7`'s stated
consequence — a setting that writes `warmup_ratio: 0.05` explicitly is now at
the default and produces no diff entry — is independently verified above
(D1, D4), not merely asserted. `RULING-8`'s stated acceptance criterion — a
YAML still writing one of the two fields is refused by the loader's existing
unknown-field check, naming the field, shown with a fixture setting rather
than by editing the owner's YAML files — is verified above (C4) exactly as
specified; the owner's `experimental_settings/*.yaml` were not opened by
this ticket.
