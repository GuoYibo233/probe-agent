# 13 `where`, `kill`, `retry` and `refire` accept a stage the named setting never runs, and act on another setting's run

Status: needs-triage
Severity: important
File: run.py:168-170, run.py:673-682, run.py:705-721, run.py:778-789
Contract: 8.6 (the four subcommands' argv and what each prints), 3.4 (a directory is named by its key alone, reached from several settings)
Errata: not recorded. The errata entry "wave-6 close: kill / refire / retry take no `--debug`" records the neighbouring argv gap and not this one.

## Finding

The only test on the `<stage>` word is that it names one of the six stages:

```python
def _check_stage_name(stage: str) -> None:
    if stage not in schema.STAGES:
        sys.exit(f"run.py: {stage!r} is not a stage; one of {sorted(schema.STAGES)}")
```

Nothing compares it against `cfg._workflow`, the setting's own stage list, which the
loader puts on every `Setting` (5.1). `schema.key(stage, cfg)` then computes a key from
whatever sections happen to be present: a section the workflow does not build is `None`
and is skipped by `fields_of` (`schema.py:1176-1177`), so the key comes out of the
defaults.

## Failure scenario

Measured with the shipped files:

- `run.py where inject probe_p1_e1_theta_0pt80 sample` prints
  `.../outputs/sample/a7d8b62ee953`, which is `baseline/gpt_oss_120b_appworld`'s sample
  directory. The inject setting has no `sample` section and never collects anything; the
  path is another setting's run.
- `run.py kill inject probe_p1_e1_theta_0pt80 sample` computes the same key, builds
  `run_id = "sample-a7d8b62ee953"` and hands it to `registry.kill`, which ends that
  baseline collection's tmux pieces and appends its `killed` finish row. One mistyped
  word ends a GPU run belonging to a different setting.
- `run.py where baseline gpt_oss_120b_appworld train` ends in
  `AttributeError: 'NoneType' object has no attribute 'method'` from
  `schema._substitute` (`schema.py:1205`), because the stage table's `train` row names
  `train/methods/{method}.py` and the setting has no `probe` section. A traceback, not
  the message 8.6 asks for.
- `run.py retry inject probe_p1_e1_theta_0pt80 sample` goes further: it clears
  `done.json` and `consumed.json` out of the baseline's sample directory
  (`run.py:757-775`) before `_stage_step` fails, so the foreign run loses the markers
  that certify it and the next walk of `baseline` re-finalises it.

## Proposed fix

Refuse a stage the setting does not run, in the one place the four subcommands already
share. Give `_check_stage_name` the setting it is checking for — or add a second check
beside it in `cmd_where`, `cmd_kill`, `cmd_refire` and `cmd_retry`, after `_load_one`
returns — and require `stage in cfg._workflow`, exiting with a message naming the
setting, the stage and the workflow's stage list. That is the same fact `_walk_one`
already trusts when it iterates `cfg._workflow`.
