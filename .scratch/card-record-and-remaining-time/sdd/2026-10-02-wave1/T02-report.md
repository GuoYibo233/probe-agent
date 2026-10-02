# T02 report: memory and phase in the trainer's beats; the probe service's memory line

Branch `ticket/2026-10-02-wave1/T02`, base `757d0067c7e90636d75f5bfafbdc27b6088f4f19`,
head `337a028d0dedb64a7b1e55fa4ca500524d3b0d49`. The worktree is removed and the branch is kept.

## 1. What was done

1. **`mem_gib` in every train beat.** `jobs/registry.py`: `Heartbeat._write` writes `mem_gib`
   when it is given and not None, in the same loop that writes `tok_in`, `tok_out` and `loss`
   (`("tok_in", "tok_out", "loss", "mem_gib")`). A beat without it is the line it was before.
   `train/utils/trainer.py`: a new module helper `_emit(hb, done, total, unit, **extra)` calls
   `hb.emit(..., mem_gib=round(torch.cuda.max_memory_reserved() / 2**30, 2), **extra)`, and all
   14 `hb.emit` calls of the file go through it: the training beats, the beats that bracket
   validation, the checkpoint beat, the prediction beats, and the two beats of the
   `train.import_from` path. On the cpu the figure is 0.0, because `max_memory_reserved()`
   returns 0 without initialising CUDA (checked in torch 2.11.0's source,
   `memory_stats_as_nested_dict` returns `{}` while CUDA is uninitialised).
   Touches (`hb.touch(phase)`) carry no `mem_gib`: the ticket names the beats the trainer
   emits, and a touch repeats only the last done/total/unit.
2. **The prediction phase has its own unit.** A module constant
   `PREDICTION_UNIT = "prediction split"`; the three prediction beats (`emit(0, predict_total)`,
   one per finished split but the last, and the closing `emit(predict_total, predict_total)`)
   use it instead of `"step"`. The training beats keep `"step"`. The comment above the
   prediction pass, which said "the unit stays 8.4's word for the train stage", now says the
   prediction beats count in `PREDICTION_UNIT` so a reader of the beats tells the two phases
   apart.
3. **The probe service prints its memory.** `models/probe_models/service.py`, inside the
   `not args.render_only` branch of `serve()`, right after both `base.load` calls:
   `print(f"probe service memory: {torch.cuda.memory_reserved(device) / 2**30:.2f} GiB reserved after loading", flush=True)`.
   The serve line pipes stdout into the piece log (`2>&1 | tee -a <log>`, `jobs/launch.py`),
   so the line lands in `<run_dir>/log/<index>.txt`. `torch` is imported beside `base`, inside
   `serve()`, as the README's import note already said.
   Deviation from the ticket's literal call: the ticket says `torch.cuda.memory_reserved()`;
   the code passes the service's `device`. The launcher starts the probe service with
   `--device cuda:<id>` and no `CUDA_VISIBLE_DEVICES` (`jobs/launch.py:1262`), so the no-argument
   call reads the current device, cuda:0, which is not the service's card whenever `<id>` is
   not 0. The trainer's call keeps no argument because the trainer is scoped to its one card
   through `CUDA_VISIBLE_DEVICES`.
4. **README section 2.** The `train/utils/trainer.py` entry's `writes:` says every beat carries
   `mem_gib` and names the two units; the `models/probe_models/service.py` entry's `writes:`
   names the log line; the `tests/` entry names the new test case. The `jobs/registry.py`
   entry is left to ticket 01, as the ticket says.
5. **The unit test.** A new class `HeartbeatLineTest` in
   `tests/test_registry_concurrent_append.py` (placed before `PieceVerdictTest`, so an append
   at the end of the file by ticket 01 does not touch the same lines). It opens a heartbeat
   with the real `registry.beat()` in a temporary directory, emits a beat with `mem_gib=61.2`,
   one with `loss` only, one with nothing extra, and `finish()`; it checks the first row
   carries `mem_gib == 61.2`, the exact key set of each row, and that the stdout copy of every
   beat equals the file line. The module docstring names the new check.
6. **No `jobs/versions.yaml` row** on this branch, as the ticket and the spec ("Code-era
   rows") say: the main conversation writes the `--same` rows for `train`, `sample` and
   `inject` after the merge.

## 2. How it was verified

All commands ran in the worktree with the main repo's interpreter
(`/home/y-guo/reproduce/new1/external/probe-env/bin/python`, since `external/` is not in git
and a worktree has none), on yebis.

The new test fails against the old registry (the base commit's `jobs/registry.py` copied into
a scratch tree beside the new test module):

```
KeyError: 'mem_gib'
Ran 1 test in 0.029s
FAILED (errors=1)
```

`run.py selfcheck` (after both commits):

```
selfcheck: 32 python files, 0 problems
```

All eight test modules, each in its own process (the tree has eight now; the project
CLAUDE.md still says seven):

```
== test_registry_concurrent_append   Ran 10 tests in 0.319s   OK
== test_packed_loss                  Ran 3 tests in 2.967s    OK
== test_settings_keys                Ran 25 tests in 23.611s  OK
== test_probe_input                  Ran 19 tests in 1.970s   OK
== test_record_formats               Ran 16 tests in 0.246s   OK
== test_probe_eval                   Ran 15 tests in 2.065s   OK
== test_environment_and_build        Ran 22 tests in 0.072s   OK
== test_qwen3_family                 Ran 13 tests in 25.009s  OK
```

An ad-hoc cpu check of the trainer helper (not committed): `trainer._emit` on a real
`registry.beat()` file, then a touch and `finish()`:

```
cuda available: False
{"done": 3, "total": 10, "unit": "step", "ts": 1790943889.5029852, "loss": 0.25, "mem_gib": 0.0}
{"done": 0, "total": 2, "unit": "prediction split", "ts": 1790943889.5030577, "mem_gib": 0.0}
{"done": 0, "total": 2, "unit": "prediction split", "ts": 1790943889.5030785, "phase": "predict"}
{"done": 0, "total": 2, "unit": "prediction split", "ts": 1790943889.5030906, "status": "done"}
memory_reserved(cuda:3) uninitialised: 0
```

`git diff --stat 757d006..HEAD` (no `jobs/versions.yaml`):

```
 README.md                                |  6 ++---
 jobs/registry.py                         |  4 ++-
 models/probe_models/service.py           |  8 ++++++
 tests/test_registry_concurrent_append.py | 32 +++++++++++++++++++++--
 train/utils/trainer.py                   | 44 ++++++++++++++++++++------------
```

**Not run (GPU step, BLOCKED):** the `--debug` walk of one `train_probe` setting. The
ready-to-run command, from the repo root after this branch is merged and committed, with the
cards the main conversation picks through the gpu-run skill:

```
external/probe-env/bin/python run.py train_probe cgen_qwen3_0pt6b --debug --cards <host>:<id>
```

`cgen_qwen3_0pt6b` is a generator method, so its walk exercises both the training beats and
the prediction phase's touches. What to read afterwards: the train run's
`heartbeat/0-<n>.jsonl` (every counting row has `mem_gib`; the rows after training have
`"unit": "prediction split"`), and `run.py ls` printing `prediction split` during that phase.
The probe service's line is exercised only by an `inject` walk (for example
`external/probe-env/bin/python run.py inject <setting> --debug --cards ...`), whose probe
service piece log should hold `probe service memory: <x> GiB reserved after loading`.

## 3. Commits

- `521c1cf` T02: mem_gib on every train beat, and the prediction phase beats in its own unit
  (registry, trainer, test, README trainer and tests lines)
- `337a028` T02: the probe service prints its reserved memory after loading its checkpoints
  (service, README service line)

## 4. Self-review and open questions

- **Contracts 8.4 disagree on the unit word.** `notes/plans/2026-09-17-contracts.md` 8.4 says
  "`unit` is the stage's own word: ... `step` for train", and the trainer's old comment kept
  `step` on that ground. The implementer procedure says the contracts win on a name. I
  followed the ticket instead, because the user approved this exact change when he said "go"
  to the six tickets ("the prediction phase gets its own progress count"), the spec of
  2026-10-02 builds on it ("ticket 02 gives the prediction phase its own unit"), and ticket 05
  reads it. Contracts 8.4 also lists `tok_in`, `tok_out`, `loss` as the optional fields;
  `mem_gib` extends that list. Both contract lines are gyb's to update (`notes/` is his).
- **The probe service reads its own device**, not the current one (section 1, item 3); this
  is a change to the ticket's literal call, made because the literal call reads the wrong card.
- **Touches carry no `mem_gib`.** A train piece that dies of memory inside a long validation
  or prediction pass has, as its newest `mem_gib`, the figure of the counting beat before that
  pass. The spec accepts "the last beat before its death"; a touch carrying the figure would
  tighten it but changes `Heartbeat.touch`'s signature and the method files, which the ticket
  does not ask for.
- **The registry's rates still read across the phase change.** `registry.rates` uses every
  counting beat of the incarnation whatever its unit; when done drops from the step total to
  0 at the prediction phase, both rates read None until the recent window lies within the
  prediction beats (the existing guard `last.done >= first.done`). This was already so before
  the unit changed; ticket 05 (remaining time per phase) is where a reader splits by unit.
- **README `jobs/registry.py` entry** is untouched, per the ticket; ticket 01 edits it. Its
  description does not need the new field, but the merge should check that ticket 01's entry
  stays true.
- **Merge note:** ticket 01 also edits `jobs/registry.py` and very likely
  `tests/test_registry_concurrent_append.py` and the README `tests/` line; this branch's
  registry change is the one-line tuple and comment inside `Heartbeat._write`, and its test
  class sits before `PieceVerdictTest`.
- **Stale project fact:** the project CLAUDE.md says `tests/` holds seven modules; there are
  eight (`test_qwen3_family.py`). Not changed here.
