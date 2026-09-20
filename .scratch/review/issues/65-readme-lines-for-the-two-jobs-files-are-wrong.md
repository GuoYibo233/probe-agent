# 65 The README annotation lines for jobs/registry.py and jobs/launch.py name files neither reads and miss files both do

Status: needs-triage
Severity: minor
File: README.md:309
Contract: 0.1 (the five-line annotation format), 8.6 check 1-2
Errata: not recorded

## Finding

Four claims on three lines are false of the code. `run.py selfcheck` does not catch them:
check 2 holds the `imports:` and `used by:` lines equal to the `ast` import graph at file
level, and the `reads:`/`writes:` lines and the parenthesised name lists are checked by
nobody.

1. README.md:309, `jobs/registry.py` `reads:` — "constants/path_outputs.yaml, jobs/runs.jsonl,
   run directories' meta.json, done.json and heartbeat, ssh, tmux, nvidia-smi". It also reads
   every live run's endpoint files: `_attached_elsewhere` globs
   `run_dir.glob("service_*.json")` and reads each one (jobs/registry.py:1047-1050) for
   `kill`'s `attached_to` refusal (8.6). The `jobs/launch.py` line names that same read on its
   own side ("its own and other live runs' service_<kind>_<replica>.json"), so the omission is
   only on the registry line.

2. README.md:316, `jobs/launch.py` `reads:` — "the run directory's settings.yaml and
   meta.json". `jobs/launch.py` never opens `settings.yaml`; the string does not occur in the
   file. It is handed the loaded `Setting` by `run.py` (`launch(stage, setting, run_dir,
   resolved, git)`, :913) and reads `meta.json` through `_read_json` (:947, :789, :1165).

3. README.md:316 again, the same `reads:` line omits the environment's split task-id files.
   `_resolve_split_files` reads each one twice — through `env.tasks(split)` / `requested_pairs`
   (:705, :717) and as bytes for the sha1 it writes into `meta.json.split_files`
   (`hashlib.sha1(path.read_bytes())`, :725).

4. README.md:314, `jobs/launch.py` `imports:` — "data/environments/__init__.py (tasks and
   requested_pairs)". The imported names are `open_env` and `requested_pairs`
   (`from data.environments import open_env, requested_pairs`, :27); `tasks` is a method on
   the environment object `open_env` returns, not an imported name.

## Failure scenario

README section 2 is the tree's index and the file an agent reads before touching a file
("read it before touching a file, and update the file's own line whenever you change it"). An
agent asked to change who may read `settings.yaml`, or to add a reader to the endpoint files,
greps the README's `reads:` lines, finds `jobs/launch.py` listed as a `settings.yaml` reader
and `jobs/registry.py` listed as no endpoint-file reader, and edits the wrong file — or leaves
`registry.kill`'s refusal out of the change entirely. Nothing fails loudly: `selfcheck` stays
green either way.

## Proposed fix

Correct the four claims on the two annotation entries in README.md section 2: add
`run directories' service_<kind>_<replica>.json (kill's attached_to refusal)` to
`jobs/registry.py`'s `reads:`; drop `settings.yaml` from `jobs/launch.py`'s `reads:` and add
`the environment's split task-id files (through data/environments.requested_pairs and
env.tasks, for meta.json's split_files)`; and spell `jobs/launch.py`'s `imports:` qualifier
`data/environments/__init__.py (open_env, requested_pairs)`.
