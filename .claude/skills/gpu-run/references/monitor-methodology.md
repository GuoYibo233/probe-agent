# 测速与 ETA 方法论（gpu-run reference）

Read the sampler's verdict, decide next step. Never guess from memory, and
don't re-derive it by hand from raw logs either — that's the sampler's job.

由 `.claude/agents/job-monitor.md` 和 gpu-run Phase 5 引用。原为一个全局
skill，2026-07-30 迁入项目内、全局那份已作废；下面的示例路径来自旧项目，
**new1 里一律以 `python3 run.py gpu-jobs json` 的台账输出和
`<workdir>/logs/` 为准**。

## When to invoke

- After a wakeup fires checking on a daemonized job
- User asks "how's it going", "ETA?", "is it stuck"
- About to quote an ETA or wall-time estimate to the user

## 程序职责说明：判定从哪来

以前这份文档教的是「两个时间点读 tqdm 算真实速率、纠正分片 ETA、手工 parse
进度行」这一整套手工流程——那套活现在是 `ops/heartbeat.py` +
`ops/sampler.py` + `ops/verdicts.py` 的常设职责：每个已接心跳的采集/训练/
评测脚本主循环里 `emit(done, total, ...)`，后台采样器每
`sample_interval_s`（默认 60 秒）读一轮全部心跳，按下面的六格判定 + 两线
公式算出判定/速率/ETA，写进它自己的状态文件（`MONITOR_DIR/latest.json`）。
**读判定优先用 `python3 run.py gpu-jobs json`——终端出口接读这份采样历史
（带新鲜度门槛，过期退回现场实探老路）接好之后，这条命令直接吐判定；接好
之前，同一份判定已经能从网页出口 `http://localhost:8377/json` 读到（采样器
自己起的网页，工单 06 已完成）。不要再手翻日志、手算 tqdm 行**——手工流程
只在采样查不到时（比如任务根本没接心跳，或采样器没跑）才退回去用。

六格判定（`ops/verdicts.py` 的 `V_DONE`/`V_DEAD`/`V_STALL`/`V_WARMUP`/
`V_SLOW`/`V_OK`，`judge()` 按固定优先级判，命中即停）：

| 判定常量 | 中文 | 命中条件（摘自 `judge()`） |
|---|---|---|
| `V_DONE` | 已完成 | `status=="done"` 或 `done >= total` |
| `V_DEAD` | 已挂 | tmux session 探不到（`alive is False`） |
| `V_STALL` | 疑似卡死 | 距上次心跳（还没见过心跳时距发射）超过判定线 |
| `V_WARMUP` | warm-up 中 | 还没见过第一条心跳，且未超 warm-up 上限 |
| `V_SLOW` | 变慢 | 近期速率 < 平均速率 × `slow_ratio` |
| `V_OK` | 健康 | 以上都不命中 |

两线公式（常数收在 `ops/verdicts.py` `DEFAULTS`，别处不许硬编码）：

- **判定线**（stall line，多久没心跳算卡死）：
  `max(stall_mult × 典型心跳间隔, stall_floor_samples × sample_interval_s)`，
  默认 `stall_mult=5.0`、`stall_floor_samples=3`、`sample_interval_s=60.0`；
  典型心跳间隔取最近 ≤`typical_beats`（20）个心跳间隔的中位数，样本不足
  `min_intervals`（3）个时退回 `warmup_line_s`（默认 1800 秒/30 分钟）顶着，
  避免长 task/长 step 开局就被误判卡死；发射时给了 `--stall-line` 就直接用
  那个数，不再算自适应值。
- **升级线**（escalate line，多久没心跳该拉人介入）：
  `判定线 × escalate_mult`（默认 3.0），或发射时给的 `--escalate-line`。
  过了升级线，采样器把这一轮的 `escalated` 标成真——这是 Phase 5「事故记录
  有内容才派 job-monitor」的输入。
- 服务类分片（`--service` 发射，如 vLLM）走 `_judge_service`：端口探测
  （`/health`）连续失败 `port_fail_rounds`（默认 3）轮记 `V_STALL`，达到
  `port_fail_rounds × escalate_mult` 轮升级；还没探到过一次 200 时按
  warm-up 上限顶着。

要改判定口径，改 `ops/verdicts.py` 的 `DEFAULTS`——这份文档只负责讲清楚
口径是什么，不再教怎么手工复现它。

## Decision tree

判断输入是采样器给的判定值（`verdict`/`escalated` 字段——`gpu-jobs json`
接好采样历史之后就在那，接好之前先读 `http://localhost:8377/json`），
不是原始日志：

| 判定 | Action |
|---|---|
| `V_OK` 健康 | 不用特别处理，按下面 Wakeup scheduling guidance 的节奏走 |
| `V_SLOW` 变慢 | 检查是不是尾部数据本身更慢（如冗长输出的样本），报告 + 按平均值外推 |
| `V_WARMUP` warm-up 中 | 还没心跳，正常；超过 warm-up 上限会自动变成 `V_STALL`，不用手动催 |
| `V_STALL` 疑似卡死，`escalated=false` | 记一笔，按常规节奏下次再看 |
| `V_STALL` 疑似卡死，`escalated=true` | 读日志定位死因——采样器已经把这一条记进事故记录；自动拉事故 agent 补射目前**未上线（暂缓）**，发现这条要靠人或 Claude 主动巡检介入 |
| `V_DEAD` 已挂 | 读日志定位死因，能修则补射：`python3 run.py launch --refire <run_id> --idx <N>` |
| `V_DONE` 已完成 | 走 Phase 6a 收尾五连，不用再监控 |

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
