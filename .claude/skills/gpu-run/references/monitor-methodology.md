# 测速与 ETA 方法论（gpu-run reference）

Read tqdm rate, compute real ETA, decide next step. Never guess from memory.

由 `.claude/agents/job-monitor.md` 和 gpu-run Phase 5 引用。原为全局
`monitor-job` skill，2026-07-30 迁入项目内；下面的示例路径来自旧项目，
**new1 里一律以 `python ops/gpu_jobs.py json` 的台账输出和
`<workdir>/logs/` 为准**。

## When to invoke

- After a wakeup fires checking on a daemonized job
- User asks "how's it going", "ETA?", "is it stuck"
- About to quote an ETA or wall-time estimate to the user

## Mandatory rules

**Never quote ETAs from memory.** Past guesses missed by 5-60× (paraphrase 4×, pipeline 5×, augmentation 60×) — that is why every ETA must come from freshly measured s/it.

Before stating any ETA:
1. Find the running job's log directory (`logs/<scope>/`)
2. For each per-job log, read tqdm rate from the last ~5 progress lines
3. Multiply remaining items × measured s/it = real ETA
4. If no tqdm yet (model still loading), say "ETA TBD — measuring" and schedule next wakeup +5 min

## Standard procedure

new1 首选：`python /home/y-guo/reproduce/new1/ops/gpu_jobs.py json`
已经把每个分片的进度、实测速率、tqdm ETA、tmux 存活状态算好了。
台账查不到时才手动走下面这套：

```bash
# 1. 确认 tmux session 还活着（逐 host）
ssh <host> 'tmux ls'

# 2. 对每个分片日志抽 tqdm 尾行
for f in <workdir>/logs/*.log; do
  name=$(basename $f .log)
  [[ "$name" == "scheduler" ]] && continue
  echo "=== $name ==="
  tail -c 500 $f | tr '\r' '\n' | grep -vE "^$|Loading weights" | tail -3
done
```

## Reading tqdm output

A typical line:
```
Generating paraphrases:  35%|███▍      | 1043/3000 [1:37:04<2:39:48,  4.90s/it]
```

Parse:
- `1043/3000` = current/total
- `1:37:04` = elapsed
- `2:39:48` = tqdm-projected remaining (often misleading for sharded jobs — see below)
- `4.90s/it` = **the ground truth** for current rate

Real ETA = `(total - current) × s_per_it / 60` minutes.

## Sharded-job caveat

For sharded jobs (e.g., witqa shards in `self_paraphrase.py`), tqdm shows `current/total_dataset_size` (e.g., 4500), but each shard only processes its slice (e.g., 1500). The skipped-via-`continue` items zip past instantly, making tqdm ETA misleading.

To get real shard ETA:
- shard_size = total_dataset_size / num_shards
- real_progress = items_in_my_shard_done = (current_idx - shard_start)
- real_remaining = shard_size - real_progress
- real_eta = real_remaining × s_per_it

For shard 1 of `[1500, 3000)` showing `tqdm: 2186/4500`:
- shard_start = 1500
- real_progress = 686
- real_remaining = 814
- at 5.6s/it → 814 × 5.6 / 60 = ~76 min

## Decision tree

After computing ETA:

| Condition | Action |
|---|---|
| ETA reasonable (< target wall) | Schedule wakeup at next milestone (default +1h or until 10% more progress) |
| ETA too long (> 2× user expectation) | Report; give Dungeon♂Master 3 options: wait / kill+shrink scope / kill+revisit method |
| Rate degrading over time (later items slower) | Common for verbose-output datasets (mintaka 4B) — note + extrapolate average |
| Rate improving | Likely still in warm-up; report and check again in 15 min |
| GPUs at low util (<20%) | Job may be stalled in preprocessing — investigate before estimating |
| Process count != expected | Some jobs may have died — `tail` failed jobs' log for traceback |

## Wakeup scheduling guidance

Use `ScheduleWakeup` after monitoring:

| Phase | Suggested wakeup |
|---|---|
| First 5 min after launch (model loading) | +30-60 min (don't burn cache) |
| Mid-job, healthy progress | +1h |
| Final 30% of progress | +30 min |
| Job nearly done | +15 min |
| Idle GPU phase (waiting for one slow job) | +1h |

Use the `prompt: <<autonomous-loop-dynamic>>` sentinel for autonomous chains.

## Gotchas

- `tail -c 1000 | tr '\r' '\n'` — the `\r` translation is essential because tqdm uses `\r` to overwrite the same line; without it you'll see one giant line.
- Filter out `Loading weights` and `examples/s` progress bars (model loading or dataset saving), not the actual generation tqdm.
- `process count = 9` is normal for 4-active-job scheduler (4 sh wrappers + 4 python children + 1 scheduler).
- A scheduler exiting normally is silent — the only signal is `Done N Failed 0` line in scheduler.log.
