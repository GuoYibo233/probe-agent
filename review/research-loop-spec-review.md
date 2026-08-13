# research-loop plugin 架构评审

**评审对象：** `.scratch/research-loop/spec.md` 与 `tables/`
**评审日期：** 2026-08-13
**评审范围：** 只评估 plugin 架构本身是否可实现、可恢复、可长期使用；不评估当前 new1 工程是否已经兼容，也不修改原设计稿。
**评审角色：** 本文作者只作为 advisor 提供外部评审意见，不是本项目的决策者、spec owner 或实施负责人。
**意见性质：** 下文的优先级、数据结构和示例均为非约束性建议，用于说明风险和可能的解决方向；是否采纳、如何实现以及是否调整原有意图，由用户和后续负责 agent 决定。
**当前建议：** 保留总体架构；在开始全量实现前，优先评估 P0 项是否需要吸收到设计中。

## 1. 总体判断

设计已经形成了清楚的治理骨架：

- idea、deploy、run 三层按指挥权分工；
- oversight 独立于指挥链；
- 跨层通信依赖落盘事实，而不是会话记忆；
- 原则、spec、执行、结果、故事之间要求双向溯源；
- 正轨与 quick path 分开；
- 结构化数据和确定性脚本承担校验工作。

这些方向适合作为 plugin 的长期内核。当前主要风险不在概念，而在四个实现边界：

1. `tables/` 仍然是供人阅读的半结构化设计说明，不足以直接生成运行时 schema 和状态机。
2. 新会话没有可靠方法恢复“当前循环做到哪里、下一步是什么”。
3. 多账本联动只有单文件原子性，没有事务或修复协议。
4. 验收没有覆盖 plugin 最核心的完整研究循环。

如果直接按当前 spec 全量施工，最可能得到的是一套规则齐全、局部校验很多，但恢复现场和处理异常仍依赖 agent 临场推断的系统。这与“上下文是一等设计对象”的目标不一致。

## 2. P0：实现前应修订

### P0-1 建议让 `tables/` 成为真正可执行的单一真源

**现状**

- `rows.json` 使用 `_fields`、`_required` 和自然语言描述字段。
- 字段类型、是否可空、默认值、唯一键、条件必填和版本迁移没有统一机器表示。
- `ledgers.json.active` 是自然语言判定式，例如“未过期未被 superseded”或“按最新 review 合并”。
- spec 要求从这些表生成或引用 schema、owner 默认表和路由实现。

**影响**

两个实现者可能从同一张表写出不同的验证器。表虽然是文档真源，却不是运行时真源。以后修改字段时，仍然可能出现表、JSON Schema、CLI 和查询器四处漂移。

**建议**

将机器定义和解释文字分开：

```text
schemas/*.schema.json       真正的 JSON Schema
policies/owners.json        owner 和 transition 的结构化规则
policies/queries.json       active/filter/order 的结构化规则
tables/*.json               可保留为生成后的文档视图，或只保存 rationale
```

如果坚持五张表就是源，则至少把字段写成以下形态：

```json
{
  "run_id": {"type": "string", "minLength": 1},
  "status": {"enumRef": "runs.status"},
  "quick": {"type": "boolean", "default": false}
}
```

条件规则也应有确定表示，例如：

```json
{
  "when": {"field": "status", "op": "neq", "value": "ok"},
  "allowNull": ["metric_name", "value", "n"]
}
```

**验收**

- schema 可以完全由源表生成，生成结果可重复且 git diff 为空。
- 任意删除一个 required 字段、加入非法枚举、违反条件必填都会被同一个验证入口拒绝。
- `query` 和 `archive` 对 active 的判断调用同一份已解析规则，而不是各自重新实现。

### P0-2 增加循环状态恢复协议

**现状**

每层开工只要求读取本层待决队列和有效授权。这不能回答：

- 当前活跃的 principle/spec/batch 是什么；
- 哪些 issue 已完成或仍未开始；
- 哪些 launch order 等待执行；
- 哪些 run 正在运行、等待收尾或已经失败；
- 哪个 batch 等待报告、监察或用户裁决；
- 当前层接下来应该执行哪个动作。

**影响**

跨会话恢复仍然依赖用户重新说明，或让 agent 扫描多个目录后自行推断。框架保存了历史，却没有保存或派生当前工作面。

**建议**

提供一个确定性的恢复入口：

```text
ledger.py status [--batch BATCH_ID] [--json]
ledger.py next --layer idea|deploy|run|oversight [--batch BATCH_ID]
```

状态优先从已有账本派生，避免再维护一个容易漂移的手写状态文件。若派生成本或歧义过高，再增加只由脚本维护的 `current.json` 物化视图。

建议输出至少包括：

```text
active_spec
active_batch
stage
open_issues
pending_launch_orders
running_runs
unrecorded_or_unchecked_runs
open_blockers
pending_inspection
pending_user_decisions
next_actions[]
```

所有 layer skill 的开工步骤应变成：读 `status`、本层 `next`、待决队列、有效授权，而不是只读后两项。

**验收**

- 在端到端流程的任意一步关闭会话，新会话只运行标准开工命令即可恢复正确阶段。
- 同一份落盘状态多次查询得到相同 next action。
- 状态矛盾时明确返回 `inconsistent`，不得猜一个阶段继续执行。

### P0-3 定义多账本联动的崩溃一致性

**现状**

以下动作都跨越多个落盘对象：

- 回答 `r5-choice`：更新 blocked、追加 decision、回填 `decision_ref`；
- 写发射单：落发射单、更新 decision `affects`；
- 撤销 answered blocked：撤销旧条、重开新条、撤销关联 decision；
- 完成运行：写 RUNMETA、jobs、runs、渲染 RESULTS；
- 收官：写 inspection report、回填 batch report、执行 closeout gate。

现有“原子追加、就地更新、文件锁”只能保护单个文件。进程在中间退出会留下半完成链路。

**建议**

选择并写死一种协议：

1. 首选：追加 transaction journal，记录 `prepared -> committed`，各账本是物化视图。
2. 次选：每个复合动作先写 staging manifest，全部成功后写 commit marker。
3. 最低方案：规定严格写入顺序，并提供 `ledger.py reconcile` 检测和补齐可机械恢复的半状态。

所有复合操作必须有 `operation_id`，保证重试幂等。重复执行不得产生第二条 decision、第二张发射单或第二次指标入账。

**验收**

- 在每两个文件写入之间注入进程退出。
- 重启后 `reconcile` 能恢复到完整旧状态或完整新状态。
- 同一命令重复执行两次，实体数量和引用关系不变。

### P0-4 用假铁轨验收完整循环

**现状**

spec 的端到端剧本覆盖完整流程，但实际集成验收只要求走通 1-3 步。这没有覆盖 plugin 风险最高的执行、入账、报告、监察和故事裁决。

**建议**

提供一个无需 GPU、无需外部服务的 deterministic fake rail。它应当：

- 接收发射单；
- 生成固定的小产物和 RUNMETA；
- 输出两个以上指标；
- 可通过参数制造 success、failure、timeout、empty-output；
- 支持一次 retry；
- 可以被 spotcheck 和 verify_report 读取。

v1 交付必须实际走通：

```text
init
-> principle
-> approved spec
-> issue
-> launch order
-> fake run
-> RUNMETA/jobs/runs
-> batch report
-> inspection
-> story decision
-> closeout
```

同时走通 quick path，并验证 quick 结果不能直接进入 story。

## 3. P1：首版数据契约应补齐

### P1-1 明确 run 与 metric 的基数

**现状**

普通 run 行只有单个 `metric_name/value/n`，但一般实验一次会产生多个指标。目前没有定义一个 run 写多行还是把多个指标塞进一个 value，也没有定义重复 `run_id` 的语义。

**建议**

将执行事实与观察值拆开：

```text
runs.jsonl
  run_id, status, batch_id, launch_order_ref, runmeta_path, elapsed_s, ...

observations.jsonl
  observation_id, run_id, metric_id, value, n, filter, recorded_at, ...
```

story 引用时应明确引用 `run_id`、`observation_id` 或两者。若不增加账本，也至少把 `metrics` 定义成有 schema 的数组，并规定查询与去重规则。

### P1-2 建议让批准绑定不可变内容

**现状**

spec header 记录版本、批准人、日期和原则版本，但没有记录被批准内容的 hash 或 commit。批准后继续编辑 Markdown，批准标记仍可能看起来有效。

**建议**

增加：

```text
approved_digest
approved_commit
```

二选一即可，优先 digest，因为 spec 可能在尚未 commit 时由用户批准。`trace_check` 每次使用 spec 前重新计算 digest；不一致即标记 `approval_stale`。

principles 的批准也需要同等机制，或者明确原则状态变更本身就是逐行批准事件。

### P1-3 命令只能有一个权威来源

**现状**

发射单同时携带 `registry_task` 和完整 `argv`；原则文档中的 `criterion_cmd` 又会被直接提取执行。registry 和 argv 不一致时没有权威顺序，Markdown shell 字符串也带来引用和转义问题。

**建议**

发射单只保存结构化请求：

```json
{
  "task_id": "eval-model",
  "args": {"model": "x", "seed": 1},
  "registry_digest": "..."
}
```

运行层通过 registry 解析出 argv，并把最终 argv 写入 RUNMETA。原则条目同样使用 `criterion_task + criterion_args`，不从 Markdown 单元格执行任意 shell 字符串。

如果为了可读性保留 argv，它只能是生成后的只读快照，执行前必须验证它与 registry 解析结果一致。

### P1-4 收窄 R2、R3、R4 的作用域

**问题**

- R2 的“AI 在验收里只做两件事”与 inspector 输出 blockers、部署层分类故障等职责容易冲突。
- R3 的“每个数字都有复现命令”字面上会覆盖日期、行号、hash、参数和运行时长。
- R4 的“任何派生量先批准”会让已经在 spec 中声明的均值、比例和过滤口径反复请求批准。

**建议口径**

- R2：最终科学判断与故事裁决归用户；agent 可以做结构检查、缺陷判定和证据整理。
- R3：支撑经验性主张的数值必须可复算；元数据数字只要求可溯源。
- R4：批准 spec 中的 metric/criterion/derivation 定义即视为预授权；只有新增或改变公式、分母、过滤条件时才重新上桌。

### P1-5 通用内核与工程适配层分离

**现状**

plugin 声称适用于一般“idea 到实验”项目，但内核直接出现 GPU、一小时阈值、显存、换卡、NFS、opus 和 sonnet。这些是 new1 的策略，不是所有研究工程的共同语义。

**建议分层**

```text
plugin core
  layers, ledgers, transitions, provenance, approval, reports

resource adapter
  local-process | gpu-cluster | scheduler | remote-service

project policy
  standing authorization, runtime limit, dirty-tree policy

agent roles
  inspector_model, reader_model; 未配置时使用当前会话默认模型
```

new1 的配置可以继续表达 GPU < 1h 常设授权，但 plugin core 应使用通用的 compute authorization policy。

### P1-6 定义 quick 转正与 retry/attempt 语义

**quick 转正**

固定 seed 不等于复现。复现还依赖 commit、数据版本、环境、参数和输入产物。建议增加：

```text
promoted_from_run_id
source_launch_order_ref
```

从 quick 转正时由脚本复制完整配置生成 normal launch order，并明确哪些字段允许改变。

**retry**

发射单已有 retry，RUNMETA 只有单个 `attempt_no`，但没有说明一次 run 的多个 attempt 如何保存。建议采用：

```text
run_id                 逻辑实验
attempt_id             每次实际执行
RUNMETA.attempts[]      或每个 attempt 独立 RUNMETA
```

不得覆盖前一次失败 attempt 的 argv、日志和资源信息。

## 4. P2：降低首版操作成本

### P2-1 增加一条面向人的统一入口

目前功能分散在多个 skill 和脚本中。plugin 顶层建议提供稳定入口：

```text
research-loop init
research-loop status
research-loop next
research-loop check
research-loop query ...
```

顶层入口可以转调 `ledger.py` 等内部脚本，但用户和上层 skill 不应依赖内部文件布局。

### P2-2 将强制核查成本做成策略

“每批都由独立 inspector 通读”可以作为 new1 默认策略，但通用 plugin 最好支持：

```text
inspection_policy = always | risk-based | manual
```

无论选择哪种策略，机械的 trace/schema/evidence 检查都应始终执行。变化的只是是否再调用独立上下文做完整通读。

### P2-3 首版暂缓低频维护能力

archive、feedback 自进化、regression_check 聚合、doctor 聚合和通用 fallback 都有价值，但不是证明核心循环成立的前提。建议在核心闭环稳定后再加入，以免首版同时实现太多状态机和豁免规则。

归档尤其应等撤销和更正语义稳定后再做，否则需要提前解决“用户撤销已经归档的 decision/blocked 行时写哪里”的问题。

## 5. 建议保留的设计

以下部分不建议推翻：

- 三层加监察面的职责划分；
- idea 层负责用户主对话和故事裁决；
- run 层只机械执行，不修改代码；
- 跨层消息必须落盘或引用落盘对象；
- 正轨与 quick path 分离；
- story 只能引用经过正式流程的结果；
- 数字从结构化脚本进入账本，不由 agent 从日志手填；
- 发射前钉 commit、参数、数据版本和产物路径；
- inspector 使用独立上下文；
- spec 与实现共享机器真源；
- 配置未接线时 fail closed。

其中“写权”应明确定位为协作纪律和防误用机制，不应被描述成安全边界。`--layer` 是自报参数，无法证明调用者身份；这对本地研究 plugin 可以接受，只需准确描述能力边界。

## 6. 建议的 v1 范围

### 建议纳入 v1

1. plugin manifest 与顶层路由 skill。
2. idea/deploy/run/oversight 四个角色入口。
3. 可执行 schema 和统一验证器。
4. principle、spec、blocked、decision 的最小闭环。
5. launch order、run、attempt、observation、RUNMETA 的最小闭环。
6. batch report、inspection、story、closeout。
7. quick path 及转正规则。
8. `status`、`next`、`reconcile`。
9. fake rail 和完整集成测试。
10. new1 adapter，但不在 core 中硬编码 new1 名称和路径。

### 建议留到 v1.1

1. archive 和 archive index。
2. feedback review 与 skill 进化。
3. regression_check。
4. doctor 聚合报告。
5. 多种 resource adapter。
6. risk-based inspection policy。
7. 更完整的 fallback 工程设施。

## 7. v1 交付门禁

### 静态门禁

- 所有 JSON/Markdown 契约可解析。
- 源表可以确定生成 schema 和默认配置。
- 生成物重复生成无 diff。
- spec lint、schema validation、trace check 全部成功。

### 正常路径

- 空仓库 init 后能运行 fake experiment 完整闭环。
- 一个 run 能记录多个 observation。
- report 中的经验性数字都能通过命令复算。
- story 只能引用有效、非 quick、状态为成功的证据。

### 恢复路径

- 在每个阶段中断并启动新会话，`status/next` 都能恢复。
- 跨文件操作每个写入点发生崩溃后都能 reconcile。
- 同一命令重复执行不产生重复实体。
- 批准后的 spec 被修改时必须被识别为 stale。

### 失败路径

- 非零退出、超时、空产物、结构化输出损坏分别产生确定状态。
- retry 保留所有 attempt，不覆盖失败证据。
- 未知错误只升级，不自动猜分类。
- 配置缺失时只锁对应能力，并明确给出缺失键和恢复动作。

### quick path

- quick run 不要求 spec、issue、batch report 和例行 inspection。
- quick run 仍保存完整 launch order、seed、commit、dataset 和 RUNMETA。
- quick run 不能直接进入 story。
- quick 转正由原 launch order 机械生成，并保留来源引用。

## 8. 推荐实施顺序

1. 先把实体关系和状态图定稿，不写 skill 正文。
2. 将五张表改造成可执行契约，并生成 schema。
3. 实现 ledger 基础设施、幂等 ID 和复合操作协议。
4. 实现 `status/next/reconcile`。
5. 实现 fake rail，跑通 normal 和 quick 两条完整路径。
6. 再写四个角色 skill，让 skill 调用已经稳定的命令。
7. 最后接入 new1，逐项迁移现有 METHOD、runs、RESULTS、jobs 和 RUNMETA。

这个顺序可以防止 skill 文本先固化一个尚未经过端到端验证的数据模型。

## 9. 对现有 lint 的判断

当前 `python3 .scratch/research-loop/spec_lint.py` 结果为：

```text
-- spec_lint: 0 errors, 0 warnings
```

这证明当前五表 JSON 可解析，已覆盖的 owner/cap/枚举/词汇检查没有发现漂移。它不证明以下性质：

- schema 可生成；
- active 表达式可执行；
- 状态转换完整；
- 跨账本操作可恢复；
- 批准没有过期；
- 完整研究循环可运行。

因此建议保留现有 lint，并把它定位为“设计稿静态一致性检查”；运行语义由 schema 测试、状态机测试和完整集成测试负责。

## 10. 最终建议

这份设计不需要推倒重来。最值得保留的是分层、落盘通信、证据纪律和 quick path。下一轮修订应集中解决：

1. 可执行真源；
2. 会话恢复；
3. 跨账本一致性；
4. 完整假任务验收；
5. run/metric/attempt 数据模型。

完成这五项以后，它才适合作为长期 plugin 内核；其余治理功能可以在真实使用中逐步加回。
