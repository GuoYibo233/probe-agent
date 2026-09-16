# GPU cluster slow-variable log (new1)

> Only records things that do not change on a minute-to-minute basis. **A
> card's live occupancy is always probed on the spot**:
> `python3 run.py gpu-jobs free` (scans the whole cluster in about 6 seconds,
> run from the repo root). The job ledger is `ops/jobs.json`, read and
> written only through `run.py gpu-jobs register/finish`. The sampler
> resident on the login machine computes verdicts:
> `python3 run.py sampler --interval 60 --port 8377`; the web page is
> `http://localhost:8377` (ssh port forwarding), and `/json` gives the
> machine-readable verdict.
> When to update this file: driver upgrades, hardware changes, discovering a
> new trap.

## Sampler deployment facts (went live 2026-08-08, appended 2026-08-09 at final review)

- The resident tmux session is named `new1_sampler`, runs on the login
  machine, cwd points at the main repo `/home/y-guo/reproduce/new1` (not any
  worktree -- a worktree gets deleted at wrap-up, and pointing there leaves it
  dangling).
- The watchdog is a crontab entry, probing every 5 minutes for the session and
  bringing it back if it is gone (verbatim from `crontab -l`, measured
  2026-08-09):
  `*/5 * * * * tmux has-session -t new1_sampler 2>/dev/null || tmux new-session -d -s new1_sampler 'cd /home/y-guo/reproduce/new1 && python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'`.
  The `cd` runs inside the session tmux starts -- cron's default cwd is
  `$HOME`, and without this `cd`, `run.py` would not be found.
- **Cron's environment PATH usually does not inherit the login shell's
  config** -- the incident agent (`spawn_agent` in `ops/sampler.py`) resolves
  the absolute path through `shutil.which("claude")`, and if `claude` is not
  on PATH, it raises `RuntimeError` directly (caught by
  `maybe_trigger_incidents` and recorded into the incident record, which does
  not bring down the sampling loop, but that particular incident then never
  actually spawns an agent). The crontab line either needs `claude`'s
  directory prepended into a `PATH=` prefix, or confirmation that cron's
  default PATH already covers it -- otherwise this incident-agent chain never
  works under cron.
  - **2026-08-10 field verification (z1 batch)**: three incidents (two
    training OOMs plus one manual service kill) were all correctly judged
    "dead" and written into `incidents.jsonl`; all three times the incident
    agent failed to spawn because of the above PATH problem
    (`spawn_error` recorded accurately). As of today, adding PATH to crontab
    still has not been done.
- The sampler's own log is teed to NFS:
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log`.
- **Port 8377 is already held by this resident process** -- hand-typing
  `python3 run.py sampler --port 8377` or bare-starting a second `sampler.py`
  will conflict with it (`OSError: Address already in use`); use a different
  port for debugging or a temporary second instance.
- After T12 (incident triggering) and T13 (vLLM service log) merged into
  main, this resident session was still running the pre-merge code and needs
  a restart to pick up the new code -- the same applies to this batch of
  final-review changes (C1/C3's spawn_agent, sample_once's write-order),
  restarted and recorded by the main session once merged, out of scope for
  this fix.

Surveyed on: 2026-07-29 (measured, not hearsay).

## Hardware and drivers

| Host | Alias | GPUs | VRAM per card | Driver | CUDA | Python | RAM |
|---|---|---|---|---|---|---|---|
| tokyo105 | shiga | 8x RTX A6000 (idx 0-7) | 48G | 575.64.03 | **12.9** | 3.10.12 | 251G |
| tokyo106 | -- | 10x RTX A6000 (idx 0-9) | 48G | 535.230.02 | **12.2** | 3.10.12 | 251G |
| tokyo107 | -- | 4x RTX 6000 Ada (idx 0-3) | 48G | 535.113.01 | **12.2** | 3.10.12 | 251G |
| tokyo108 | saitama | 3x H100 NVL (idx 0-2, 95G) + 3x H200 NVL (idx 3-5, 143G) | see left | 570.195.03 | **12.8** | 3.12.3 | 503G |

## Known traps

1. **tokyo106/107 drivers only go up to CUDA 12.2** -- newer vLLM/torch
   builds needing cu124+ wheels may report driver incompatibility on these
   two; when a package install reports a CUDA version error, think of this
   first, and switch to tokyo105/108 or downgrade the wheel version.
   - **Measured exception (2026-07-29)**: cu128-wheel torch runs fine on
     106/107 as usual (CUDA minor-version forward compatibility kicks in), so
     do not automatically avoid these two just because of this trap; counting
     them, the training pool actually has 19 usable cards. Only downgrade the
     wheel version when a driver error actually shows up.
2. **Dedupe the aliases**: shiga=tokyo105, saitama=tokyo108, only four
   physical machines. Always use tokyo names for probing and allocation,
   never treat an alias as a fifth machine and double-count a card.
3. **tokyo108 has mixed card types**: idx 0-2 are H100 (95G), idx 3-5 are
   H200 (143G); pick idx by VRAM need, do not default to starting from 0.
4. `/home` is shared over NFS across the whole cluster, paths are consistent
   everywhere; logs can be read locally, no need for ssh.
5. The HF cache is on NFS: `HF_HOME=/net/tokyo100-10g/data/str01_01/y-guo/hf`
   (Qwen3.5-4B/9B, the whole Qwen3 family, the whole Qwen2.5 family already
   cached); model weights also download here, not to /home.
6. hf_server port convention: `8712 + gpu_id` (a historical convention on
   tokyo108).

## Machines outside the pool (do not use)

- tokyo104: 8x Quadro RTX 8000 46G, old Turing cards with no bf16, last
  resort.
- tokyo101: driver broken (NVML mismatch), needs a reboot, leave it alone.
- tokyo100/102/103/199, yebis, setagaya: ssh unreachable (measured
  2026-07-25).
