# T02 — 采样器单轮走通，三份落盘文件出来

工单：`.scratch/gpu-monitor-launch/issues/02-sampler-once.md`
需求依据：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 6（采样器核心 `ops/sampler.py`）。
设计依据：`docs/design/2026-08-08-gpu-monitor-launch.md` §3（采样器）§4（判定）。
工单未直接引用 spec.md 的任何节，未读 spec.md。

工作树：`/home/y-guo/reproduce/new1-wt/20260808-par-T02`，分支 `ticket/20260808-par/T02`，
base commit `5be5d0827fe959cc1c016c8f99221c4d6a4218c8`。

## 做了什么（对照工单四条验收）

1. **采样器测试通过：假台账两分片（一活一死），活的判定是健康或 warm-up 中，死的判定是已挂，累计 token 读对**
   - 新建 `ops/sampler.py`，`sample_once()` 读台账 active、`read_beats()` tail 日志抓心跳、
     `live_sessions()` 探 tmux 存活、`update_piece_state()` 攒累计状态、`build_row()` 调
     `ops/verdicts.py` 的 `stall_line_s`/`rates`/`judge` 出判定行。
   - 用工单/计划里给的测试骨架原样落盘 `tests/test_sampler.py`（`TestSampleOnce.test_round`）：
     两分片一个有三条心跳且 session 活着，一个只有普通文本且 session 不在存活集合里；
     断言活分片判定 ∈ {健康, warm-up 中}、死分片判定 = 已挂、`tok_in == 210`（最后一条心跳的累计值）。

2. **三份落盘文件都出现并且能 json.load；再采一轮，没变的日志不重复追加心跳**
   - `latest.json`/`state.json`/`history/<job>.jsonl` 用 `atomic_write`（tmp + `os.replace`，
     与 `run.py:save_state` 同款）和 `append_jsonl` 落盘，`NEW1_MONITOR_DIR` 环境变量可把目录
     指到别处。补了 `test_files_are_valid_json`：三份文件都存在、`json.load` 能读、
     `history/x.jsonl` 每一行独立是合法 JSON。
   - 心跳去重：`update_piece_state` 里拿 `ps["recent_beats"]` 最后一条的 `(ts, done)` 当基准，
     只有严格更大的 `(ts, done)` 才算新心跳、才 append。工单骨架里 `test_round` 的第二段
     （同一份日志再采一轮，`recent_beats` 长度不变）已覆盖。
   - 补射（`launched_at` 变了）整段状态重开、`refires` 计数：另写了
     `test_refire_resets_state_and_counts`——先采一轮确认 `refires == 0`、`recent_beats` 长度 3，
     改 `launched_at` 再采一轮，断言 `refires == 1` 且 `first_beat` 非空（状态确实重开了，
     不是历史遗留值）。

3. **`python3 run.py sampler --once` 在真台账上跑完不炸**
   - 在工作树里跑了 `python3 run.py sampler --once`（没设 `NEW1_MONITOR_DIR`，走真实 NFS 路径），
     RC=0。当时 `ops/jobs.json` 的 `active` 是空列表，所以这轮实际验证的是"空台账 + 真实
     `live_sessions` 反查台账外 session"这条路径：`live_sessions` 真的 ssh 了 tokyo105-108，
     `extras` 里出现了 tokyo105 上四个未登记的 tmux session（`7-29run`/`7-31run`/`flow-8-1`/
     `rc-claude`，这是別的对话在用的 session，不属于本工单管的东西）。产物落在
     `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/`（`latest.json`/
     `state.json`，内容见下方验证输出），没有清理——这正是采样器部署后应该写的位置，
     留档不算脏。

4. **`python3 run.py selfcheck` 通过并 commit**
   - `run.py` `TASKS` 加了 `"sampler"` 条目（`stage="ops", py="sys",
     script="ops/sampler.py"`，三条 notes：怎么起常驻、落盘在哪、`--once` 冒烟用法），
     文字与计划 Task 6 Step 4 给出的条目逐字一致。
   - `MAP.md` 补了 `ops/sampler.py` 一行。
   - `selfcheck` 在这个隔离工作树里跑不到"全部就位"——见下方"验证"一节的说明，
     这是工作树本身缺 venv 目录导致的，不是本单改动引入的问题（见"自查发现与存疑"）。

## 怎么验证的

```
$ python3 -m unittest tests.test_sampler tests.test_heartbeat tests.test_verdicts -v
test_unreachable_returns_false (tests.test_sampler.TestProbePort) ... ok
test_missing_log_returns_empty (tests.test_sampler.TestReadBeats) ... ok
test_reads_only_valid_heartbeat_lines (tests.test_sampler.TestReadBeats) ... ok
test_files_are_valid_json (tests.test_sampler.TestSampleOnce) ... ok
test_refire_resets_state_and_counts (tests.test_sampler.TestSampleOnce) ... ok
test_round (tests.test_sampler.TestSampleOnce) ... ok
（heartbeat 4 + verdicts 11 一并跑，全 21 ok）

Ran 21 tests in 0.043s

OK
```

写测试之前先跑过一次确认失败（`ModuleNotFoundError: No module named 'sampler'`），六个用例齐了以后再补的实现。

```
$ python3 run.py sampler --once
[sampler] cwd=/home/y-guo/reproduce/new1-wt/20260808-par-T02
  python3 /home/y-guo/reproduce/new1-wt/20260808-par-T02/ops/sampler.py --once
RC=0

$ cat /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/latest.json
{
 "sampled_at": 1786139885.1503584,
 "rows": [],
 "extras": {
  "tokyo105": [
   "7-29run",
   "7-31run",
   "flow-8-1",
   "rc-claude"
  ]
 },
 "incidents_tail": []
}
```

```
$ python3 run.py selfcheck
（尾三行）
缺 cwd 目录: .../envs/stabletoolbench/server  (任务 stb-virtual-server)
缺解释器/程序: .../envs/vllm-env/bin/python  (任务 build-token-walk)
selfcheck: 63 任务 / 4 配方, 16 处缺失
```

对照跑了同一份 `run.py` 在主仓工作树（`/home/y-guo/reproduce/new1`，只读，没有改动任何文件）：
`selfcheck: 62 任务 / 4 配方, 全部就位`。两边的差异只有任务数 62→63（本单新增的
`sampler` 条目）和 16 条"缺解释器/缺脚本/缺 cwd"——16 条清一色是别的任务
（`collect-aw`/`collect-alf`/`toolhop-official`/`stb-virtual-server`/`build-token-walk` 等）
指向的 venv 目录和第三方脚本，这些目录按 `.gitignore` 不进 git，`git worktree add`
建出来的隔离工作树里天然没有——16 条里不含任何一条提到 `sampler`。

## Commit 清单

- `d7f3435` — T02: monitor: 采样器核心(采心跳/探存活/判定/落盘 latest+state+history)+注册 sampler 任务
  （`ops/sampler.py`、`tests/test_sampler.py`、`run.py`、`MAP.md`）

## 自查发现与存疑

- **`selfcheck` 在隔离工作树里报 16 处缺失，是工作树结构性的，不是本单引入的**：这些
  缺失全部指向 `.gitignore` 排除的 venv 目录（`envs/*/venv`、`cprobe-env`、`mbert-env` 等）
  和第三方脚本，`git worktree add` 不会把主仓里这些未跟踪目录带过来。已用对照实验证实
  （见上）：同一份代码在主仓工作树跑 selfcheck 是"全部就位"，只是任务数少 1（还没挂
  `sampler`）。工单要求"跑 selfcheck 通过并 commit"，本单在自己的隔离工作树里做不到字面
  意义上的"通过"（rc=1），但这是 ticket-run 并行执行协议本身带来的环境限制，与本单代码
  改动无关——合并回主分支后 selfcheck 会回到"全部就位"。这一条留给主会话在合并/收账阶段
  确认。
- **对计划里给的 `sample_once()`/`build_row()` 骨架代码做了两处必要偏离**，都写进了
  commit message，这里再展开一遍：
  1. 计划骨架里 `sample_once()` 直接调用 `from gpu_jobs import load_reg`，但
     `gpu_jobs.load_reg()` 函数体内读的是 `gpu_jobs` 模块自己的全局 `REG_PATH`，不是调用方
     的。工单/计划给的测试骨架里 `self.S.REG_PATH = str(self.jobs)` 这行monkeypatch 的是
     `sampler.REG_PATH`（sampler 模块自己的属性），这样 patch 完全碰不到 `gpu_jobs.REG_PATH`，
     照抄骨架会导致测试读到真实的 `ops/jobs.json` 而不是 tmp 目录里的假台账。改成
     `ops/sampler.py` 自己定义 `load_reg()`（4 行，读本模块的 `REG_PATH`，默认值等于
     `gpu_jobs.REG_PATH`），让 monkeypatch 按测试骨架写的方式生效。`live_sessions` 没有
     这个问题——它是被直接调用的函数名，在 `sampler.py` 全局命名空间里晚绑定,
     monkeypatch `sampler.live_sessions` 天然生效,不用改。
  2. 计划骨架里 `build_row(job["name"], idx, piece, ps, now_mono)` 只传 job 名字符串，但
     "关键实现约束"一节明确写了 `warmup_s` 要从 `job.get("monitor", {}).get("warmup_s")`
     取——只有名字取不到 `monitor` 字段。改成 `build_row` 接收完整 job 字典，内部再取
     `job["name"]` 填 row 的 `"job"` 字段。这个改动不影响任何外部可观察行为（测试只看
     `latest["rows"]` 和落盘文件内容,不检查函数调用签名）。
  两处都判断为"骨架示例代码本身和同一份计划文档里的文字描述打架，需要临场选边"，不是
  "工单需求本身有歧义"，所以没有停下来要 NEEDS_CONTEXT,自己按文字描述（更详细、更明确
  的那份）裁决了。
- **自查改了两处实现（非骨架偏离,是我自己写代码时的两个疑点）**：
  1. `eta_s` 计算里"近期速率没值退回平均速率"最初写成 `recent_rate if recent_rate else
     avg_rate`——`recent_rate` 恰好等于 `0.0`（真实停摆但还没到判定线）时会被 truthy 判断
     误当成"没值",悄悄换成平均速率,把"当前是 0"的信息抹掉了。改成显式
     `is not None` 判断。
  2. "探测失败连续 10 轮"最初是行内魔法数字 `10`,改成模块级命名常量
     `_PROBE_FAIL_ROUNDS_RED`（这个阈值来自设计文档 §4 的固定文字"连续 10 轮",不属于
     `ops/verdicts.py` 的 `DEFAULTS`——那是纯函数判定引擎自己的配置面,采样器侧的常数
     不该混进去,所以没有塞进 `verdicts.DEFAULTS`,单独留在 `sampler.py` 模块级）。
- `state.json` 的持久化字段比计划文档 §3 列出的 schema
  （`first_beat`/`recent_beats`/`last_new_beat_mono`/`last_done`/`launched_at`/`alive_last`/
  `probe_fail_rounds`/`port_ever_ok`/`port_fail_rounds`/`verdict`/`escalated_since_mono`/
  `incident_open`/`refires`）多了三个键：`last_total`/`last_unit`/`last_status`。这三个
  是 row 输出必须有的 `total`/`unit` 以及 judge() 要用的 `status` 的落脚点——设计文档给的
  schema 里没写它们该存在哪儿，`recent_beats` 每条心跳的字段列表也明确没有 `total`（列的
  是 `ts/done/tok_in/tok_out/loss/status`），所以只能另开三个键存最近一次心跳的 total/unit/
  status。`escalated_since_mono`/`incident_open` 两个键按 schema 建了但只在创建/重开状态
  时写默认值（`None`/`False`），本单没有实现"什么时候该刷新它们"的逻辑——设计文档写明这
  两个字段是给 Task 14（工单 12，事故触发）用的，采样器的 `maybe_trigger_incidents(rows,
  st)` 本单按计划要求原样留空函数（`pass`）,没有提前动事故判定那部分逻辑。
- 服务类分片（`kind == "service"`）的端口探测 `probe_port()`按计划 Task 6 的接口清单写了
  （HTTP GET `/health`,异常/超时都算 False）,但工单 02 的验收标准全部针对 `kind="batch"`
  的两分片场景,没有覆盖服务类的端到端流程（那是工单 13 vLLM 服务档的活）。只补了
  `probe_port` 自身的单测（探一个必然拒连的本机端口,断言返回 False）,没有另造一份
  `kind="service"` 的 `sample_once()` 集成测试——服务类的完整场景留给工单 13 去验。
- 没有触碰 `ops/jobs.json`（本单跑 `sampler --once` 时台账 `active` 本来就是空列表,没有写
  这个文件,只读了）,也没有改动别的工单负责的文件。
