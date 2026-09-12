# env_locks -- version-lock snapshots

The `*.txt` files in this directory are pip freeze snapshots of every
experiment environment used by this project (audit E26, generated
2026-08-02), used so that when "some environment suddenly can't install a
package / behaves differently than before" comes up, the exact package
whose version changed can be pinned down against these, instead of guessing.
"Every experiment environment used" = the ones listed in the mapping table
below; the third-party clones' own venvs under `related_work/` are not
included, since they take no part in this project's experiments and are not
snapshotted either.

## Generation command

This project's venvs are all built with `uv venv`, and a venv usually has no
pip module body installed inside it (`<venv>/bin/python -m pip` reports
`No module named pip`), so `pip freeze` cannot be used directly. Use
`uv pip freeze` against the venv's python interpreter instead, with the same
effect:

```bash
uv pip freeze --color never --python <venv>/bin/python > ops/env_locks/<name>.txt
```

`--color never` is required: uv stuffs ANSI color codes into non-tty output
by default, and without this flag, redirecting to a file writes control
characters into the snapshot, polluting the diff.

Mapping (venv path -> snapshot file name):

| venv path | snapshot file |
|---|---|
| `cprobe-env` | `cprobe-env.txt` |
| `mbert-env` | `mbert-env.txt` |
| `jlens-env` | `jlens-env.txt` |
| `envs/appworld/venv` | `appworld.txt` |
| `envs/alfworld/venv` | `alfworld.txt` |
| `envs/tales/venv` | `tales.txt` |
| `envs/tau2-bench/.venv` | `tau2.txt` |
| `envs/toolhop-env` | `toolhop.txt` |
| `envs/stb-server-env` | `stb-server.txt` |
| `envs/vllm-env` | `vllm.txt` |
| `envs/bfcl/venv` | `bfcl.txt` |

## The two-environment iron rule

`mbert-env` and `cprobe-env` each run one experiment line, their versions do
not accommodate each other, and under no circumstances is either allowed to
be upgraded or downgraded just to resolve a conflict:

- `mbert-env`: transformers is pinned to **4.57.6**.
- `cprobe-env`: transformers stays at **>=5.14**.

Older transformers versions silently compute the wrong result for chunked
incremental forward passes on hybrid architectures (no error, just a wrong
result); the two lines are split apart specifically to isolate this trap.
Upgrading the wrong side invalidates every experiment conclusion run so far,
and nobody notices right away. The snapshot files for these two environments
carry an extra line at the top stating this iron rule; the snapshots for the
other environments do not.

## Usage

- **Regenerate the snapshot and commit before a major upgrade**: before any
  operation that changes a venv's package versions, such as `uv pip install` /
  `uv sync`, regenerate the corresponding environment's snapshot using the
  command above, `git diff` to see clearly which packages are about to change,
  confirm none of the red-line packages are touched (especially transformers
  in mbert-env / cprobe-env), then commit this snapshot update before
  installing anything.
- When suspecting that some environment "used to work and now doesn't", first
  `git log -p ops/env_locks/<name>.txt` to page through the historical
  snapshots and compare, which is faster than redoing the whole install
  process.
- These snapshots are read-only records, not environment definition files, and
  cannot be fed to `uv pip install -r` to restore an environment directly
  (some packages are editable installs / local-path installs, and a line
  produced by freeze does not necessarily install back the same way).
