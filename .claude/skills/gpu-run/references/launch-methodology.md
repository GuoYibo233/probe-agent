# 发射方法论（gpu-run reference）

Generic launcher playbook for GPU work on the tokyo cluster — probe, allocate,
shard, launch in tmux, verify, report.

由 `.claude/agents/gpu-runner.md` 和 gpu-run Phase 2/4 引用。原为全局
`launch-gpu-job` skill，2026-07-30 迁入项目内。项目级流程与铁律以
`.claude/skills/gpu-run/SKILL.md` 为准，本文件只提供方法论细节。

## Ground rules

1. **Usable pool = tokyo105-108, any card with no OTHER user's process on it.** Another user's process (even 0% util) = off-limits, no exceptions. Your own leftover process = candidate to reuse or kill — ask if unclear whether it's a warm server someone (you) still wants.
2. **Everything runs inside tmux.** Never bare `ssh host 'python ...'`, never `nohup` gymnastics.
3. **Claude's own host varies (shiga or tokyo108).** Run `hostname` first; ssh to every target that isn't local. `/home/y-guo/` is NFS-shared across shiga + all tokyo hosts — same paths everywhere.

## Host inventory

| Host | GPUs | VRAM each | Tier |
|---|---|---|---|
| tokyo105 | 8× RTX A6000 (idx 0-7) | 48G | workhorse |
| tokyo106 | 10× RTX A6000 (idx 0-9) | 48G | workhorse |
| tokyo107 | 4× RTX 6000 Ada (idx 0-3) | 48G | workhorse (faster than A6000) |
| tokyo108 | 3× H100 NVL (idx 0-2) + 3× H200 NVL (idx 3-5) | 95G / 143G | big-model / fast lane |

## Step 1 — Probe

```bash
# new1 首选（带台账信息，约 6 秒）：
python3 /home/y-guo/reproduce/new1/ops/gpu_jobs.py free

# 底层脚本（等价探测，本机只有 python3，没有 python）：
bash /home/y-guo/reproduce/new1/.claude/skills/gpu-run/scripts/gpu_status.sh          # 四台全探
bash /home/y-guo/reproduce/new1/.claude/skills/gpu-run/scripts/gpu_status.sh tokyo108 # 单台
```

Output: one line per GPU with `OWNERS` column — `FREE`, `y-guo`, or another username. Build the candidate list from `FREE` cards (plus own-process cards after deciding reuse/kill).

## Step 2 — Allocate

Estimate VRAM need before picking cards:
- bf16 weights ≈ `2 × params` GB (7B ≈ 15G, 14B ≈ 30G, 32B ≈ 65G, 70B ≈ 140G), plus KV cache / activations.
- A vLLM server grabs ~90% of the card by default → one server = one whole card regardless of model size.

Rules, in order:
1. **Fits in 48G → tokyo105/106/107 first.** Keep tokyo108's big cards free for jobs that actually need them.
2. **Needs >48G → tokyo108** (H200 143G > H100 95G). Multi-GPU tensor parallel must stay on one host.
3. **Latency-critical single job** (interactive pilot, quick turnaround) → tokyo107 or tokyo108, they're the fastest cards.
4. **Fill, don't hoard**: take exactly as many cards as shards/jobs; prefer packing one host before spilling to the next (fewer ssh targets, simpler logs).

## Step 3 — Shard if it pays

Shard when the work is many independent items (dataset rows, prompts, seeds, configs) AND single-GPU wall time would exceed ~1h.

- `S = min(free suitable GPUs, ceil(total_items / reasonable_chunk))` — don't create 30s shards.
- The script must accept a shard spec — `--shard-id i --num-shards S` or an index range — and write to **distinct output files** (`out.shard3of8.jsonl`). Add the flag to the script first if it doesn't have one; never let two shards write the same path.
- Prefer resumable scripts (skip already-done items) so a dead shard can be relaunched without redoing work.
- Merge shard outputs after all sessions finish, then sanity-check merged count == total_items.

## Step 4 — Launch in tmux

Session name: `<proj>_<task>_<host>g<gpu>` (e.g. `new1_probe_t105g0`), log to a per-project log dir on NFS (e.g. `<workdir>/logs/<session>.log`).

Assemble commands with python `subprocess.run` — bash-in-bash quoting is the #1 typo source here:

```python
import subprocess, shlex
local = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()

def launch(host, gpu, session, workdir, cmd, log):
    inner = (f"cd {workdir} && CUDA_VISIBLE_DEVICES={gpu} "
             f"{cmd} 2>&1 | tee {log}")
    tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
    if host == local:
        subprocess.run(["bash", "-c", tmux], check=True)
    else:
        subprocess.run(["ssh", "-n", host, tmux], check=True)
```

`shlex.quote(inner)` is not optional — hand-wrapping `inner` in single quotes breaks the moment `cmd` itself contains one (e.g. any `python -c "... print('x')"`), and the session dies silently with no log. Verified 2026-07-27.

- `cd <workdir>` is **mandatory** — ssh lands in `/home/y-guo`, not the project.
- Use the project venv's **absolute** python (uv envs on NFS work on every host, all x86_64): e.g. `/home/y-guo/reproduce/new1/<env>/bin/python`.
- `CUDA_VISIBLE_DEVICES` pins each shard to its card; inside the process the card is always `cuda:0`.
- Multi-card single job: `CUDA_VISIBLE_DEVICES=2,3` and let the framework (vLLM `-tp 2`, torchrun) spread.
- Check for session-name collisions first: `tmux has-session -t <name>` (via ssh for remote).

### When jobs > free cards: chain, don't schedule

No scheduler daemon. Group jobs per card and chain them with `&&` inside ONE session — each card becomes a serial queue:

```python
# 20 jobs, 8 free cards -> 8 sessions, each running its slice back-to-back
inner = " && ".join(f"CUDA_VISIBLE_DEVICES={gpu} {cmd} >> {log} 2>&1" for cmd in my_slice)
inner = f"cd {workdir} && ({inner})"
```

- Balance slices by expected runtime, not count, if jobs differ in size.
- `&&` stops the chain on first failure (usually what you want — a broken env fails everything). Use `;` instead only when jobs are truly independent.
- Session name drops the task part: `<proj>_q_<host>g<gpu>` (q = queue). Progress check = count finished output files, not tmux state.

## Step 5 — Verify (always)

```bash
sleep 5  # once, as part of the launch command chain is fine
ssh <host> 'tmux ls' | grep <session>       # session alive?
tail -20 <log>                               # started cleanly? CUDA OOM? import error?
```

A missing session = crash at startup; the log has the traceback. Fix and relaunch — don't report "launched" until every session is alive and its log shows real progress (model loading, first batch, tqdm line).

## Step 6 — Monitor without polling

No `sleep N; check` loops in the foreground. For "tell me when done":

```bash
# Bash run_in_background=true
until ! ssh <host> "pgrep -u y-guo -f '<distinctive_cmd_fragment>'" >/dev/null; do sleep 60; done; echo DONE
```

Or check back on wakeup by reading log tails / output file counts. ETA claims need ≥60s of tqdm observation (see monitor-job skill).

## Step 7 — Report

- Table: shard → host/GPU → tmux session → log path.
- Watch live: `ssh <host>` then `tmux attach -t <session>` (detach: `C-b d`).
- Stop one: `ssh <host> 'tmux kill-session -t <session>'`; stop all: loop over sessions, then re-probe to confirm cards released.

## Gotchas

- 0% util ≠ free — an idle vLLM server still holds its memory. Only the OWNERS column decides.
- Own stale processes (crashed script holding VRAM): `ssh <host> 'kill <pid>'`, wait 5s, re-probe.
- Two shards on one card "fit" until KV cache grows — default to one job per card; pack two only when both are provably small (<20G peak).
- tmux session dying instantly usually = quoting bug in `inner` or wrong venv path; run the `inner` string directly via ssh once to see the error.
- H100/H200 (t108) and A6000 (t105/106) run the same torch build fine; no per-host env needed.
- Don't leave finished sessions around for days — dead sessions make `tmux ls` useless for the next launch.
