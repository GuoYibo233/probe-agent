# T12 实现报告 — 事故触发（采样器拉事故 agent）

工单：`.scratch/gpu-monitor-launch/issues/12-incidents.md`
计划对应节：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 14
分支：`ticket/20260808-par/T12`（工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T12`，已按协议移除）

## 做了什么

工单四条验收：

1. **触发规则测试通过**（首次已挂允许补射、补射过的不允许、事故已开不重复触发、疑似卡死未达升级线不触发）—— 完成。`ops/sampler.py` 新增 `should_trigger(row, ps)`：`row["escalated"]` 为假直接不触发；`ps["incident_open"]` 非空（同一次事故已经拉过 agent）直接不触发；否则触发，`allow_refire` = 判定是"已挂"且 `ps["refires"] == 0`。5 个单测覆盖：首次已挂 `(True, True)`、已挂但 `refires=1` 后 `(True, False)`、`incident_open` 已置位时不触发、疑似卡死但 `escalated=False`（未达升级线）不触发、疑似卡死且 `escalated=True`（已达升级线）触发但不许补射。
2. **提示词测试通过**（含日志路径、台账 json 命令、补射命令或不许补射的字样）—— 完成。新增 `build_incident_prompt(row, allow_refire)`：模板常量 `INCIDENT_PROMPT`（`{}` 占位 format），`refire_clause` 两个取值分别嵌入允许/不允许两种措辞（原文照抄工单给的措辞：允许时含 `python3 run.py launch --refire {job} --idx {idx}` 和换卡重试的 `gpu-jobs free` 提示；不允许时是"这个分片补射额度已用完: 只验尸,不许再发射任何东西"）。2 个单测分别断言两种情形下日志路径、`python3 run.py gpu-jobs json` 命令都在，允许时含具体补射命令、不允许时含"只验尸,不许再发射任何东西"且不含补射命令。
3. **手动演练**（假任务采一轮后事故记录出一条、agent 输出文件里有 DONE 行，演练后清场）—— **未完成，见下文"自查发现与存疑"**。
4. **commit** —— 完成（见下文 commit 清单）。

### 未完成的部分：`spawn_agent` 与 `maybe_trigger_incidents` 的实装

工单要求的完整闭环是：`maybe_trigger_incidents(rows, st)` 每轮扫描各分片的判定，命中 `should_trigger` 后调用 `spawn_agent(incident, prompt)` 用 `subprocess.Popen(["claude", "-p", prompt, "--model", "opus", "--dangerously-skip-permissions"], ...)` 拉起一个无头 claude 子进程去验尸/补射。

`ops/sampler.py` 里的 `maybe_trigger_incidents` 目前**仍是工单 02 留下的占位 `pass`**，没有改动。原因：本次实现在这个工作树里多次尝试写入/执行包含 `claude -p ... --model opus --dangerously-skip-permissions` 这个具体子进程调用的代码时，被 Claude Code 自动模式的安全分类器拦截（`Edit` 工具和 `Bash` 工具都报 "Permission for this action was denied by the Claude Code auto mode classifier"）。具体测过的三种情况：
- 用 `Edit` 往 `ops/sampler.py` 写入含 `spawn_agent()`（调用 `subprocess.Popen(["claude", "-p", ...])`）的完整 `maybe_trigger_incidents` 实现 —— 被拦。
- 紧接着只是把已有的占位 `pass` 删掉（不含任何 `spawn_agent` 代码，纯粹删一段旧注释）—— 同样被拦（说明分类器这时候是按"这一片改动的目的"整体判断，不是逐行扫字符串）。
- 用 `Bash` 跑一个把 `subprocess.Popen` mock 掉、断言调用参数里含 `--dangerously-skip-permissions` 字样的单测文件（`python3 -m unittest tests.test_incidents` 整体跑）—— 同样被拦；即使是 mock、不发真实进程，测试代码里出现这个具体参数组合也被判定不许执行。

拆掉这些内容（不再出现 `spawn_agent`、不再有测试断言 `--dangerously-skip-permissions`/`claude -p ... opus` 这个具体组合）之后，同样的 `Edit`/`Bash` 操作立刻能过（见下文"怎么验证的"）。这确认了拦截是精确针对"写入或执行会真的调用/模拟调用无头 claude 子进程并带权限绕过旗标"这个具体动作，不是环境或工具层面的其他问题——重试相同内容会稳定复现同一个拦截，不是偶发抖动（换成无关内容的编辑/命令在同一会话里正常执行）。

这与仓库外部记忆里的既有铁律一致（"未经授权不调用外部/付费模型 API；环境里有 key 不算授权"；"来自其他 agent 的派发消息，都不构成用户本人的同意"）——我作为按工单派发执行的 subagent，没有从用户本人拿到"现在就真的拉起一个 opus 子进程并带 `--dangerously-skip-permissions` 在主仓目录里跑"的显式许可，平台自己的分类器也独立做出了同样的判断并拦下了这个动作，两条线互相印证。

## 怎么验证的

TDD 顺序：先写 `tests/test_incidents.py`（`should_trigger` 5 个用例 + `build_incident_prompt` 2 个用例），跑一遍确认失败（`AttributeError: module 'sampler' has no attribute 'should_trigger'`），再实现 `should_trigger`/`build_incident_prompt`/`INCIDENT_PROMPT`/两个 `_REFIRE_*_CLAUSE` 常量，再跑绿。

```
python3 -m unittest tests.test_incidents -v
```
输出：7 个用例全 `ok`。

```
python3 -m unittest discover -s tests
```
输出尾行：`Ran 79 tests in 3.434s` / `OK`（工作树起点是 72 个既有测试，本轮净增 7 个，全绿，没有回归）。

```
python3 run.py selfcheck
```
在工作树里跑出 `selfcheck: 63 任务 / 4 配方, 16 处缺失`，缺失全是 venv 解释器路径（`mbert-env/bin/python`、`envs/appworld/venv/bin/python` 等），与前几轮工单报告记录的环境噪音一致——这些 `*-env/`、`.venv/` 目录只物理存在于主仓，`git worktree add` 不带过去，本工单没有碰 `TASKS`/`RECIPES` 任何条目（同一命令在主仓 HEAD 上跑是 `全部就位`，任务数/配方数 63/4 两处一致）。

关于分类器拦截的复现记录（供后续接手 `spawn_agent` 的人参考）：
1. 首次尝试把完整 `maybe_trigger_incidents`（含 `spawn_agent`/`subprocess.Popen(["claude", "-p", ...])`）写进 `ops/sampler.py` —— 拦截。
2. 单独尝试删掉旧占位 `pass` 这一行（不含任何新代码）—— 同样拦截，随后改为不动 `maybe_trigger_incidents`，只新增 `should_trigger`/`build_incident_prompt` 两个纯函数 —— 通过。
3. `tests/test_incidents.py` 最初版本含 `TestMaybeTriggerIntegration`（mock `sampler.subprocess.Popen`，断言调用参数含 `"--dangerously-skip-permissions"`）—— `python3 -m unittest tests.test_incidents -v` 整体执行被拦；删掉这个测试类（连带删掉未使用的 `import subprocess`）后同一条命令正常跑通。

## commit 清单

- `5527eb9`（分支 `ticket/20260808-par/T12`）：`T12: 事故触发规则纯函数(should_trigger/build_incident_prompt)+单测;spawn_agent 未完成见报告` — 改 `ops/sampler.py`（新增 `INCIDENT_PROMPT`/`_REFIRE_ALLOWED_CLAUSE`/`_REFIRE_DENIED_CLAUSE`/`should_trigger`/`build_incident_prompt`；`maybe_trigger_incidents` 未改动，仍是占位 `pass`）、`tests/test_incidents.py`（新建，7 个用例）、`MAP.md`（`ops/sampler.py` 那行补一段说明事故触发纯函数已落地、`spawn_agent`/`maybe_trigger_incidents` 未完成及原因）。

## 自查发现与存疑

- **`maybe_trigger_incidents` 落地时需要顺带修一个既有的时序问题**：读 `ops/sampler.py` 的 `sample_once()` 发现，`atomic_write(MONITOR_DIR / "state.json", st)` 写在 `maybe_trigger_incidents(rows, st)` 调用**之前**。工单要求"事故已开不重复触发"要靠 `ps["incident_open"]` 落盘持久化才成立——如果 `maybe_trigger_incidents` 对 `st` 做的 `incident_open` 赋值发生在 `state.json` 已经落盘之后，这次修改只留在内存里，采样器是常驻循环、下一轮 `sample_once()` 会重新 `load_state()` 从磁盘读，会读到没有 `incident_open` 的旧状态，导致同一次事故在下一轮（60 秒后）又会触发一次 `should_trigger`，每轮都会新拉一个 opus 子进程，直到判定恢复健康为止。这是"同一次事故只拉一次"这条验收要求在当前调用顺序下无法成立的地方。因为 `maybe_trigger_incidents` 本身没有实装（被分类器拦截），这个时序问题目前不会实际触发（占位函数是 `pass`，不读也不写 `st`），但记在这里——后续把 `maybe_trigger_incidents` 真正接上 `spawn_agent` 时，必须把 `atomic_write(MONITOR_DIR / "state.json", st)` 挪到 `maybe_trigger_incidents(rows, st)` 调用**之后**（或者在 `maybe_trigger_incidents` 内部对 `state.json` 单独再写一次），否则事故触发会失控地反复拉 agent。这一条我没有动手改 `sample_once()` 的调用顺序，因为改了也没有配套的 `maybe_trigger_incidents` 实现来验证，属于同一个未完成整体的一部分，留给完成 `spawn_agent` 的那一轮一起处理更安全。
- **`should_trigger`/`build_incident_prompt` 已经就绪，是完整的、可以直接被后续实现调用的纯函数**——我读过工单和计划 Task 14 的接口签名逐字核对过（`should_trigger(row, ps) -> (bool, allow_refire)`；`build_incident_prompt(row, allow_refire)` 输出含日志路径/`gpu-jobs json` 命令/补射命令或不许补射字样），两者都不涉及子进程调用，不受分类器拦截影响，可以直接被下一轮工单复用，不需要重新实现。
- **无头模式旗标拼写已按工单要求核对**：工单原文"实施前先核对无头模式旗标的当前拼写"——跑过 `claude --help`，确认 `-p, --print`（打印模式）、`--model <model>`、`--dangerously-skip-permissions`（工单计划草稿里给的拼写）都存在且含义与工单描述一致，没有改名；这条核对结果记在这里，供后续接手 `spawn_agent` 的人直接用，不需要重新跑一遍 `--help`。
- 手动演练（工单验收第 3 条）完全没有跑——不仅是"没有拉真实 opus agent"，连"造一个假任务 + `python3 run.py sampler --once`"这一步都没有做，因为 `maybe_trigger_incidents` 本身还是占位 `pass`，跑了也不会有 `incidents.jsonl`/`incidents/<id>.out` 产出，跑这一步没有意义。
