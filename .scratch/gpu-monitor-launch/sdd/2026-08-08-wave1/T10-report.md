# T10 实现报告 — 补射模式 `launch --refire`

工单：`.scratch/gpu-monitor-launch/issues/10-refire.md`
计划对应节：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 12
分支：`ticket/20260808-par/T10`（工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T10`，已按协议移除）

## 做了什么

工单验收行是一条：「测试通过：活 session 拒绝，非 FREE 拒绝，成功路径台账分片的日志和 launched_at 更新且命令不变、没有第二个任务出现」。逐条对应：

1. **活 session 拒绝**：`ops/launch_cmd.py` 新增 `cmd_refire(argv)`，找到台账里 `run_id` 的第 `idx` 个 piece 后先查 `LC.has_session(piece.host, piece.session)`，为真就 `SystemExit`，报错文案点名"补射只对死分片"。
2. **非 FREE 拒绝**：目标卡取 `--piece` 给的值，没给就用台账原 host/gpus；`LC.probe_free(host, gpus)` 非 FREE 就 `SystemExit`，报错里带上 `probe_free` 返回的原因文本，方便事故 agent 拿着报错换卡重试（对应 spec 用户故事 31）。
3. **成功路径**：探到 FREE 后，日志换新文件名 `<sess>.r<refires+1>.log`（`refires` 读自采样器落盘的累计状态 `monitor/state.json`，键是 `job#idx`，没采样过就当 0）；`build_inner()` 把台账里存的 `piece["cmd"]` 原样包一层 `cd/CUDA_VISIBLE_DEVICES/tee`（不查任务注册表、不追加分片旗标）发进 `LC.tmux_launch(host, sess, inner)`，session 名沿用原名不变；随后 `gpu_jobs.mutate_reg()` 只原地改这一个 piece 的 `host/gpus/log/launched_at` 四个字段，job 本身和其余 piece 不动，**不调用 `LC.register_all()`**——不新开 `record.py start`、不重复台账 append，补射不产生第二个 job。

入口挂法：`run.py launch` 仍是唯一命令行入口，`cmd_launch(argv)` 一看到 `argv` 里有 `--refire` 就整个转发给 `cmd_refire(argv)`，不复用原有的 `parse_launch_argv`（那套是给"发新任务"用的，字段语义不同）。新增 `parse_refire_argv(argv)` 只认四个旗标：`--refire <run_id>` / `--idx <int>` / `--piece <host:gpus>` / `--allow-dirty`，碰到别的旗标直接拒绝（补射不是新任务，不该透传任务参数）。补射前照样过 `gate_dirty`（`--allow-dirty` 放行），与计划文档给出的接口签名一致。

同时改了两处文档：
- `ops/launch_cmd.py` 顶部 docstring 加一行指向 `cmd_refire`。
- `run.py` 顶部用法 docstring 补一行 `launch --refire` 的调用形式与一句话行为说明（工单/计划都没要求，但这是同一条命令的用法文档，不补的话后来人看 `run.py` 顶注找不到这个模式）。

`launch_cmd.py` 本身在工单 09 落地时就没有 MAP.md 行（核对过 `MAP.md` 全文，`launch_common.py`/`launch_probe.py` 都有行，`launch_cmd.py` 没有）。这是 T09 遗留的既有缺口，不属于本工单改动范围，没有顺手补——补射功能仍然挂在同一个 `launch_cmd.py` 文件里，如果之后要给这个文件建 MAP.md 行，`--refire` 应该在那行里一并提一句。

## 怎么验证的

TDD 顺序：先在 `tests/test_launch_cmd.py` 新增 `TestCmdRefire`（6 个用例：活 session 拒绝、非 FREE 拒绝、成功路径更新台账且不新增 job、`--piece` 覆盖目标卡、run_id 不存在拒绝、idx 越界拒绝），跑一遍确认失败（`SystemExit: launch 要一个任务名...`，因为 `--refire` 还没接进 `cmd_launch`），再写实现，再跑绿。

```
python3 -m unittest tests.test_launch_cmd.TestCmdRefire -v
```
输出：6 个用例全 `ok`。

```
python3 -m unittest discover -s tests -v
```
输出尾行：`Ran 68 tests in 3.579s` / `OK`（含本工单新增的 6 个用例，其余 62 个是仓库已有测试，全绿，没有因为本次改动回归）。

```
python3 run.py selfcheck
```
在工作树里跑出 `selfcheck: 63 任务 / 4 配方, 16 处缺失`，缺失全是 venv 解释器路径（如 `mbert-env/bin/python`、`envs/appworld/venv/bin/python`）。核对过：这些 `*-env/`、`.venv/` 目录在 `.gitignore` 里，只物理存在于主仓 `/home/y-guo/reproduce/new1/`，`git worktree add` 不会把它们带过去；在主仓（未改动的 HEAD）跑同一条命令是 `selfcheck: 63 任务 / 4 配方, 全部就位`。任务数和配方数（63/4）在工作树和主仓里一致，本次改动没有碰任何 `TASKS`/`RECIPES` 条目，`16 处缺失` 是工作树本身缺 venv 造成的环境噪音，不是本工单引入的注册表问题。

## commit 清单

- `5dd8462`（分支 `ticket/20260808-par/T10`）：`T10: launch --refire 补射死分片(活session拒绝,非FREE拒绝,只改台账不新开record)` — 改 `ops/launch_cmd.py`（`cmd_refire`/`parse_refire_argv`/`cmd_launch` 分派）、`run.py`（顶部用法 docstring 加一行）、`tests/test_launch_cmd.py`（`TestCmdRefire` 六个用例）。

## 自查发现与存疑

- `refires` 计数读的是采样器落盘的 `monitor/state.json`（`ops/sampler.py` 的 `load_state()`/`piece_key()`），不是台账里的字段——台账 piece 本身不存 `refires`。这个来源在计划 Task 12 的一句话里点明了（"采样器看到 launched_at 变了会自动重开该分片的心跳时间轴"，Task 6 已实现 `refires` 累加），我读了 `ops/sampler.py` 里 `update_piece_state()` 确认这条链路已经在，没有另起一套计数。如果补射发生在采样器一轮都没跑过这个分片位的窗口内（刚发射就挂，还没被采样过），`refires` 读到 0，日志后缀会是 `.r1.log`；如果连续两次都在采样器追上之前发生，两次都会读到 `.r1.log`（旧日志文件不会被覆盖，只是文件名撞了会追加写入同一个文件）。工单/计划都没有覆盖这个连续补射窗口的验收要求，我没有额外处理（YAGNI），记在这里供后续工单（如工单 12 事故触发）参考。
- 补射发射后**没有**调用 `verify_alive()`（30 秒验活）。计划 Task 12 的接口描述里逐步列到"mutate_reg 更新...不新开 record、不重复 register"为止，没有提验活这一步，工单验收行里也没有；正常 `launch` 模式的验活是独立设计决定（spec 用户故事 14），补射走的是同一条 `tmux_launch`，但没有照抄验活这一段。按工单字面执行，没有主动加验活。
- 探卡与 `mutate_reg` 之间存在一个理论竞态窗口（`has_session`/`probe_free` 在锁外做，最终台账更新在 `gpu_jobs.mutate_reg` 的文件锁内做）：与现有 `LC.register_all()` 的写法一致（同样是锁外探测、锁内写），不是本工单新引入的模式，沿用了仓库既有约定，没有另起炉灶加锁。

## 修复第 1 轮（F1）

工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T10-fix1`（检出既有分支 `ticket/20260808-par/T10`，已按协议移除）。

### F1：补射静默丢失原命令的 env 变量前缀

**评审指出的问题**：`cmd_refire()` 调用 `build_inner(piece["cmd"], job["workdir"], gpus, new_log)` 时没传 `env` 参数，`build_inner` 默认 `env=None`。台账 piece 当时只存 `host/gpus/session/log/cmd/launched_at/kind/stall_line/escalate_line`，既不存 `env` 也不存 `task` 名，补射时无从恢复原任务的 env 前缀。若某个 `TASKS` 任务定义了非空 `env`，对它的分片补射会悄悄丢掉这些环境变量，没有任何报错。

**根因**：`cmd_launch()` 正常发射路径里 `env = t.get("env", {}) if t is not None else {}` 只在本地变量里用来拼 `build_inner`，从没写进登记台账的 rich piece 里，所以到了补射时这份信息已经不在——不是传参时忘了带，是台账 schema 从一开始就没留这个字段。

**怎么修的**：
1. `ops/launch_cmd.py` `cmd_launch()`：`rich_pieces` 的 dict 构造里加一个 `env=env` 字段，把发射时已经算好的 `env` dict 原样存进台账 piece。
2. `ops/launch_cmd.py` `cmd_refire()`：读 `env = piece.get("env") or {}`，传给 `build_inner(piece["cmd"], job["workdir"], gpus, new_log, env)`（原来完全不传）。`piece.get("env")` 对本次修复前登记的旧台账 job（没有 `env` 字段）落空时按空 dict 处理，不报错、行为等价于修复前（仓库里目前没有任何 `TASKS` 条目用非空 `env`，向后兼容不丢失任何已发生过的真实行为）。
3. 同步更新两处 docstring：`launch_common.py` 的 `register_all()` 说明 piece 字段列表加 `env`；`launch_cmd.py` 的 `cmd_refire()` docstring 加一段说明 env 前缀的恢复来源和旧台账兼容行为。

改动范围只碰这两点，没有顺手给 piece 加 `task` 名字段（评审 detail 里提到台账也不存 task 名；但工单要修的是 env 前缀丢失这一个静默失败，task 名当前没有任何读取路径用到，加了就是没有验收对应的新字段，YAGNI，没加）。

### 怎么验证的

新增两个回归测试，加进 `tests/test_launch_cmd.py` 的 `TestCmdRefire`：
- `test_env_prefix_restored`：台账 job `erun` 的 piece 带 `"env": {"FOO": "bar", "BAZ": "qux"}`，补射后断言 `tmux_launch` 收到的 inner 命令里同时含 `FOO=bar`、`BAZ=qux` 和原 cmd。
- `test_missing_env_field_defaults_empty`：复用 `setUp` 里没有 `env` 字段的旧 `rrun` job，补射走成功路径不报错，inner 命令原样含 cmd。

```
python3 -m unittest tests.test_launch_cmd.TestCmdRefire -v
```
输出：8 个用例全 `ok`（原 6 个 + 本轮新增 2 个）。

```
python3 -m unittest discover -s tests
```
输出尾行：`Ran 70 tests in 3.576s` / `OK`（68 → 70，新增的 2 个回归测试，其余全绿，没有回归）。

```
python3 run.py selfcheck
```
在工作树里跑出 `selfcheck: 63 任务 / 4 配方, 16 处缺失`，缺失内容与上一轮报告记录的一致（均为工作树本身缺 venv 解释器路径的环境噪音，如 `mbert-env/bin/python`），任务数/配方数（63/4）没变，本次改动没有碰 `TASKS`/`RECIPES` 注册表任何条目。

### commit 清单

- `6595d1a`（分支 `ticket/20260808-par/T10`）：`T10: 补射恢复原任务 env 前缀(F1)` — 改 `ops/launch_cmd.py`（`cmd_launch` 的 rich piece 加 `env` 字段、`cmd_refire` 读回并传给 `build_inner`、两处 docstring）、`ops/launch_common.py`（`register_all` docstring 补 `env` 字段）、`tests/test_launch_cmd.py`（两个回归测试）。

### 自查发现与存疑

- 仓库现状全 grep `TASKS` 注册表未见任何条目用非空 `env`，所以这条修复目前没有真实任务能触发差异化行为验证（"改前会丢、改后不丢"这条断言只在测试的合成场景里成立）。评审 finding 本身也点明了这一点（"接口本身就是给这个场景用的"），修复思路是让台账 schema 补上这个字段、补射时对称地读回来，不是等一个真实非空 env 任务出现再补。
- 没有扩大范围给 piece 加 `task` 名字段：F1 的 detail 提到台账也不存 task 名，但当前没有任何读取路径需要"补射时反查任务名"（cmd 已经原样存了，probe_free/has_session 不需要 task 名），加这个字段没有对应的验收要求，按 YAGNI 原则没加。如果后续工单（如工单 12 事故触发）需要补射时按 task 名做额外校验，再单独评估。

## 修复第 2 轮（N1）

工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T10-fix2`（检出既有分支 `ticket/20260808-par/T10`，已按协议移除）。

### N1：补射修复把 task env 值原样写进 git 追踪的 ops/jobs.json 台账

**评审指出的问题**：F1 为了让补射恢复 env 前缀，给 `cmd_launch()` 的 `rich_pieces` 加了一行 `env=env`，把发射时已经算好的 env dict 原样存进登记台账。`ops/jobs.json` 是 git 追踪文件（`git ls-files ops/jobs.json` 确认），按仓库现有工作流台账变更照例被提交。如果后续某个 `TASKS` 任务定义了非空 env（尤其是从本地环境变量/密钥管理器现取的 token），这个值会随正常发射流程原样写进 git 版本库，没有任何脱敏或排除机制拦截。

**根因**：F1 把"补射要恢复 env"这个需求，直接映射成"把 env 的值存进台账 piece"。这混淆了两件事——补射需要的是"能找回 env"的*能力*，不是"env 的原始值"本身。发射时的 `env` dict 本该只是拼 `build_inner` 的局部变量（修复前就是这样），F1 让它多了一条落盘到 git 追踪文件的持久化路径，这是新引入的风险面，不是本来就有的。

**怎么修的**（改动范围只碰这一个风险点，没有扩大范围重构）：

1. `ops/launch_cmd.py` `cmd_launch()`：`rich_pieces` 的 `env=env` 字段换成 `task=p["task"]`——只存任务名（字符串，不含密钥），不存 env 实际键值。`--cmd` 模式下 `p["task"]` 本来就是 `None`，和之前 `env` 落空到 `{}` 的效果一致，不额外引入新的 `--cmd` 模式差异。
2. `ops/launch_cmd.py` `cmd_refire()`：不再从台账读 `piece.get("env")`，改成 `task_name = piece.get("task")` → `t = TASKS.get(task_name) if task_name else None` → `env = t.get("env", {}) if t is not None else {}`——现算现传，和 `cmd_launch()` 里推导 env 的写法（`t.get("env", {}) if t is not None else {}`）完全对称，只是数据来源从"台账里的旧快照"换成"当前 TASKS 注册表里的定义"。env 的实际键值全程只活在这次补射调用的局部变量里，不落进任何持久化文件。
3. 两处 docstring 同步改口径：`launch_common.py` 的 `register_all()` piece 字段列表把 `env` 换成 `task`，并加一句指向 finding N1 的说明；`launch_cmd.py` 的 `cmd_refire()` docstring 说明 env 现在是"反查当前 TASKS 定义现算"而不是"台账快照"，并点出这带来的代价——如果任务注册表的 env 定义在原发射与补射之间被人改过，补射拿到的是改过之后的值，不是原发射当时那份；用这个代价换"env 原值永不写进 git 追踪文件"这条更硬的约束。

**scope 边界**：没有碰 `probe_free`/`has_session`/台账其余字段/`--piece` 覆盖逻辑，这些都不在 N1 的问题范围内。也没有给"env 值本身"加密/脱敏——直接不落盘就不需要脱敏，更简单也更彻底。

### 怎么验证的

TDD 顺序：先改 `tests/test_launch_cmd.py` 里依赖旧 `env` 字段的用例，跑一遍看到预期失败（补射再传不出原 env，因为台账不再存 `env` 而 `TASKS` 里也没注册对应任务），再改实现，再跑绿。

改动的测试：
- `test_env_prefix_restored`（`TestCmdRefire`）：台账 piece 从存 `"env": {...}` 改成存 `"task": "envtask"`，测试内用 `patch.dict(LCC.TASKS, {"envtask": fake_task(env=...)})` 现场注册一个带非空 env 的任务，断言补射后 inner 命令仍同时含 `FOO=bar`/`BAZ=qux`/原 cmd——F1 的验收断言原样保留，只是 env 的来源换了。
- `test_missing_env_field_defaults_empty` 更名 `test_missing_task_field_defaults_empty_env`：语义不变（旧台账没有 task 字段，补射不报错，cmd 原样重发），改名是因为现在缺的字段是 `task` 不是 `env`。
- 新增 `test_unknown_task_field_defaults_empty_env`：台账存的 `task` 名不在当前 `TASKS`（任务后来被下线的场景），补射不能因此报错，反查落空按 `{}` 处理。
- `TestCmdLaunchFullFlow` 的 `test_success_registers_rich_pieces`：检查字段列表把 `env` 换成 `task`，加一行断言 `pieces[0]["task"] == "faketask"`。
- 新增 `test_success_does_not_persist_raw_env_values`（`TestCmdLaunchFullFlow`）：任务定义 `env={"HF_TOKEN": "shh-do-not-commit-me"}`，发射后断言 tmux inner 命令里正常带着这个 env（发射本身没被削弱），但登记给 `register_all()` 的 rich piece 里 `assertNotIn("env", pieces[0])`、`repr(pieces[0])` 里不含这个密钥字符串——这是 N1 的直接回归测试，断言"密钥值不会流向登记台账"。

```
python3 -m unittest tests.test_launch_cmd -v
```
输出尾行：`Ran 31 tests in 0.328s` / `OK`（`TestCmdLaunchFullFlow` 5 个 + `TestCmdRefire` 8 个 + 其余 18 个，全绿，含本轮新增/改名的 4 个用例）。

```
python3 -m unittest discover -s tests
```
输出尾行：`Ran 72 tests in 3.479s` / `OK`（70 → 72，净增 2 个：改名 1 个不增不减、新增 2 个，全绿，没有回归）。

```
python3 run.py selfcheck
```
在工作树里跑出 `selfcheck: 63 任务 / 4 配方, 16 处缺失`，缺失内容与前两轮报告记录的一致（均为工作树本身缺 venv 解释器路径的环境噪音）。同一条命令在主仓（未改动的 HEAD）跑是 `selfcheck: 63 任务 / 4 配方, 全部就位`，任务数/配方数在两处一致——本次改动没有碰 `TASKS`/`RECIPES` 注册表任何条目。

另外 grep 确认改动没有遗漏读取路径：`grep -rn '"env"\|piece.get("env")' ops/*.py`（排除测试）只剩 `ops/launch_cmd.py` 里 `cmd_launch()`/`cmd_refire()` 从 `TASKS[task]["env"]` 现算 env 的两行和 `launch_common.py` 的一行文档注释，`ops/sampler.py`/`ops/gpu_jobs.py`/网页与 json 出口都没有读取过台账 piece 的 `env` 字段（F1 落地以来就没有其他消费方），这次去掉这个字段不影响任何别的模块。

### commit 清单

- `55a0d0e`（分支 `ticket/20260808-par/T10`）：`T10: 补射 env 不再原样落台账,改存 task 名现算现传(N1)` — 改 `ops/launch_cmd.py`（`cmd_launch` 的 rich piece 把 `env` 换成 `task`、`cmd_refire` 反查 `TASKS[task]["env"]` 现算现传、docstring 更新）、`ops/launch_common.py`（`register_all` docstring 字段列表同步）、`tests/test_launch_cmd.py`（2 个用例改造 + 2 个新增）。

### 自查发现与存疑

- **env 快照 vs 现查的语义差异**：补射恢复的 env 现在是"当前 TASKS 注册表里的定义"，不是"原发射那一刻的快照"。如果两次之间有人改了 `TASKS[task]["env"]`（比如换了一个新 token），补射会用新值，不是原任务实际跑过的那份。工单/评审都没有要求"逐字节复现原发射环境"这个更强的属性，而且这条差异本身就是换来"env 值不落 git"这条更硬约束的代价，记在这里供后续工单参考，没有额外处理。
- **`t` 变量名与 `cmd_launch()` 里已有的 `t = TASKS.get(p["task"])` 同名但作用域不冲突**：`cmd_refire()` 里新引入的局部变量 `t = TASKS.get(task_name)` 与 `cmd_launch()` 函数体里的 `t` 是两个不同函数的局部变量，不存在遮蔽或串扰；沿用同一个变量名是为了与 `cmd_launch()` 里"用 `t` 表示任务定义 dict"的既有命名习惯保持一致，没有另起名字造成认知负担。
- 仍然没有给 piece 加密钥脱敏机制——因为直接不落盘，不需要脱敏这层。如果之后出现"就是要把某些非密钥的 env 值留痕在台账里以便审计"这种新需求，那是另一个跟 N1 反方向的需求，需要新工单单独评估，不在这轮改动范围内顺手做。
