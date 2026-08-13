# research-loop spec Advisor 建议详解

**适用读者：** 后续评估或修订 `.scratch/research-loop/spec.md` 与 `tables/` 的 agent
**相关材料：** `review/research-loop-spec-review.md` 给出总体判断；本文补充更具体的例子和可选方案。
**Advisor 声明：** 本文作者只承担 advisor 角色，不是 spec owner、决策者或实施负责人。本文不分配任务、不代表用户批准，也不要求后续 agent 照单执行。
**阅读方式：** 文中的数据结构、命令名、状态图和测试场景都是为了把风险说具体的示例方案，不是预先确定的需求。后续 agent 应先核对原 spec 的设计意图，再独立判断是否采纳、替换或拒绝这些建议，并把真正的取舍交给用户决定。

## 1. 建议关注的目标

从 advisor 视角看，下一版设计如果能从“规则完整的架构说明”推进到“不同实现者可以得到同一种行为的可执行规格”，会更适合长期使用。建议重点回答：

1. 每个实体的精确 schema 是什么；
2. 一个新会话怎样恢复当前状态；
3. 跨多个文件的动作中断后怎样恢复；
4. run、attempt、metric 之间是什么关系；
5. 用户批准绑定哪一份不可变内容；
6. registry、launch order 和最终 argv 谁是权威；
7. 不使用 GPU 时怎样完整验证整个 plugin；
8. 哪些属于 plugin core，哪些属于 new1 adapter。

仅在散文中补一句原则可能仍会留下实现歧义。较稳妥的做法是让被采纳的建议同时落到结构化表、命令契约和验收用例。

## 2. 建议优先保留的核心意图

根据当前 spec 和审计记录，以下内容看起来属于已经明确的核心意图。advisor 建议优先保留：

- 三层加监察面的职责划分；
- 用户位于 idea 层顶端；
- 跨层消息必须落盘或引用落盘对象；
- run 层不修改代码；
- 事实先于解释，故事由用户裁决；
- 数字由确定性程序抽取，不由 agent 看日志手填；
- 正轨与 quick path 分开；
- quick 结果不能直接成为 story 证据；
- 配置缺失时 fail closed；
- inspector 使用独立上下文；
- spec 和实现必须共享机器真源。

如果某项建议会改变这些意图，建议把冲突显式交给用户裁决，而不是由评审者或后续 agent 静默改写。

## 3. 建议先确定的实体模型

当前 `runs.jsonl` 同时承担执行、状态和指标，建议拆成下面的最小关系：

```text
Principle 1 ── * SpecItem 1 ── * Issue
                         │
                         └── * LaunchOrder 1 ── 1 Run
                                                  │
                                                  ├── * Attempt
                                                  └── * Observation

Decision * ── * LaunchOrder
Batch 1 ── * LaunchOrder
Batch 1 ── 1 BatchReport ── 0..1 InspectionReport
StoryClaim * ── * Observation/Run
BlockedItem 0..1 ── 0..1 Decision
```

### 3.1 Run

Run 表示一次逻辑实验，不表示某一次进程启动，也不表示单个指标。

示例：

```json
{
  "schema_version": 1,
  "run_id": "p012-20260813-01",
  "batch_id": "sp012-20260813-01",
  "launch_order_ref": "ops/launch_orders/p012-20260813-01.json",
  "status": "ok",
  "quick": false,
  "runmeta_path": "/net/.../p012-20260813-01/RUNMETA.json",
  "started_at": "2026-08-13T10:00:00+09:00",
  "finished_at": "2026-08-13T10:12:00+09:00",
  "recorded_at": "2026-08-13T10:12:02+09:00"
}
```

### 3.2 Attempt

Attempt 表示一次实际启动。换卡、重试或进程重启都产生新 attempt，不覆盖旧 attempt。

```json
{
  "schema_version": 1,
  "attempt_id": "p012-20260813-01.a2",
  "run_id": "p012-20260813-01",
  "attempt_no": 2,
  "status": "ok",
  "host": "tokyo108",
  "resources": {"gpus": [0]},
  "argv": ["python3", "run.py", "eval", "--seed", "7"],
  "log_path": "/net/.../attempt-2.log",
  "started_at": "2026-08-13T10:00:00+09:00",
  "finished_at": "2026-08-13T10:12:00+09:00"
}
```

### 3.3 Observation

Observation 表示从 run 产物中机械抽取的一项数值或结构化事实。

```json
{
  "schema_version": 1,
  "observation_id": "O000123",
  "run_id": "p012-20260813-01",
  "metric_id": "accuracy",
  "value": 0.731,
  "n": 500,
  "filter": {"split": "test"},
  "extractor": {
    "task_id": "summarize-eval",
    "args": {"split": "test"}
  },
  "evidence_path": "/net/.../metrics.json",
  "recorded_at": "2026-08-13T10:12:02+09:00"
}
```

这样可以解决当前单个 run 只能自然表达一个 `metric_name/value/n` 的问题，也能让 story 精确引用证据。

## 4. 建议 A：把表改成可执行 schema

### 原因

当前 `_fields` 和中文描述无法唯一确定类型、required、nullable、条件字段和唯一键。声称“从表生成 schema”时，信息不足。

### 可能涉及的位置

- `tables/rows.json`
- `tables/ledgers.json`
- `tables/writes.json`
- `spec.md` 的 §0.5、§4、§5、§9

### 可选修改方式

为每个实体明确：

```text
type
required
properties
additionalProperties
primary_key 或 unique_by
conditional requirements
schema_version
reference targets
```

建议避免把下面这种只供人读的定义作为唯一机器源：

```json
{"_fields": ["run_id", "status", "value"]}
```

改成可以直接转成 JSON Schema 的结构：

```json
{
  "type": "object",
  "required": ["run_id", "status", "schema_version"],
  "additionalProperties": false,
  "properties": {
    "run_id": {"type": "string", "minLength": 1},
    "status": {"enumRef": "runs.status"},
    "schema_version": {"type": "integer", "minimum": 1}
  }
}
```

`enumRef` 如果不是标准 JSON Schema 语法，建议明确生成器如何展开，或者直接使用标准 `$ref`。

### 用于验证建议的例子

应拒绝：

```json
{"run_id": "r1", "status": "looks-good", "schema_version": 1}
```

为了便于 agent 修复，错误可以稳定输出字段路径和非法值，例如：

```text
runs.status: value "looks-good" is not one of [...]
```

## 5. 建议 B：定义 active query 的机器语义

### 原因

`status=active` 容易实现，但“最新 review 合并后 pending”以及“被任何引用指向的 decision 不归档”不是简单过滤。若继续保存为中文句子，`query` 和 `archive` 会各写一套逻辑。

### 可选修改方式

advisor 更倾向于不在首版设计通用表达式语言，而是使用有限、明确的策略名：

```json
{
  "story": {"active_policy": "story-active-v1"},
  "blocked": {"active_policy": "blocked-unresolved-v1"},
  "feedback": {"active_policy": "feedback-pending-group-v1"},
  "decisions": {"active_policy": "decision-live-or-referenced-v1"}
}
```

如果采纳该方案，可以为每个 policy 定义输入、输出和边界例子，并让 `query` 和 `archive` 调用同一个 policy registry，避免两套实现漂移。

### 边界例子

建议用以下边界例子检查 active 语义是否足够明确：

1. answered blocked，from_layer 尚未 close：active。
2. closed blocked，但 decision_ref 被 active launch order 引用：blocked 是否仍留主账，需要明确。
3. expired grant，被历史 run 引用：不再授权，但为追溯应保留。
4. suggestion 有 accepted review：不是 pending，但 suggestion 与 review 必须同批归档。
5. withdrawn decision 被历史 RUNMETA 间接引用：仍需跨档可查。

## 6. 建议 C：增加 `status`、`next` 和恢复状态图

### 原因

“读待决队列 + 有效授权”只能恢复问题和权限，不能恢复工作进度。plugin 的长期可用性取决于新会话能否不靠用户复述继续工作。

### 可能涉及的位置

- `spec.md` §1 的开工必读
- `spec.md` §2.1 查询纪律
- `spec.md` §4 组件结构
- `spec.md` §8 端到端剧本
- `spec.md` §9 验收
- `tables/routes.json`
- 必要时新增 `tables/state.json`，或在现有表中登记状态派生规则

### 状态图示例

```text
idea_draft
  -> principles_approved
  -> spec_draft
  -> spec_approved
  -> building
  -> ready_to_launch
  -> running
  -> collecting
  -> report_ready
  -> inspection_pending
  -> user_decision_pending
  -> closed
```

`blocked` 是附加状态，不应替代主阶段。quick path 可以是：

```text
quick_ready -> quick_running -> quick_recorded -> quick_closed
```

### `status --json` 示例

```json
{
  "state_version": 1,
  "active_spec": "research-loop-v2",
  "active_batch": "sp012-20260813-01",
  "stage": "inspection_pending",
  "open_issues": [],
  "pending_launch_orders": [],
  "running_runs": [],
  "open_blockers": ["B0042"],
  "next_actions": [
    {
      "layer": "oversight",
      "action": "inspect_batch",
      "ref": "sp012-20260813-01"
    }
  ],
  "inconsistencies": []
}
```

### 矛盾状态例子

如果 batch report 声称包含 `run-2`，但 runs 中没有 `run-2`，advisor 建议不要猜测正常阶段，而是返回类似下面的矛盾状态：

```json
{
  "stage": "inconsistent",
  "inconsistencies": [
    {"code": "missing-run", "ref": "run-2", "source": "plans/batch-x.md"}
  ]
}
```

## 7. 建议 D：定义复合操作协议

### 原因

文件锁不能保证多个文件一起成功，因此建议在设计中选择回滚、重放或修复中的一种一致策略。

### 一种较小的可选方案

新增 append-only `operations.jsonl`：

```json
{
  "operation_id": "OP00042",
  "kind": "answer-r5-choice",
  "status": "prepared",
  "inputs": {"blocked_id": "B0012", "chosen": "option-a"},
  "effects": [
    {"ledger": "decisions", "id": "D0031"},
    {"ledger": "blocked", "id": "B0012"}
  ],
  "created_at": "2026-08-13T10:00:00+09:00"
}
```

完成后追加：

```json
{
  "operation_id": "OP00042",
  "status": "committed",
  "committed_at": "2026-08-13T10:00:01+09:00"
}
```

`reconcile` 对 prepared 但未 committed 的操作，根据已存在 effect 重放缺失步骤。所有 effect 使用预分配 ID，因此重放不会产生重复行。

### 建议优先覆盖的操作

- `answer-r5-choice`
- `withdraw-blocked-answer`
- `create-launch-order`
- `record-run-completion`
- `closeout-batch`

### 可用于评估方案的故障注入

以 `answer-r5-choice` 为例：

1. 只写 prepared 后退出；
2. 追加 decision 后退出；
3. 更新 blocked 后退出；
4. 写 committed 前退出；
5. 完成后重复执行原命令。

理想结果是：每种情况重启并 reconcile 后都只存在一个 decision，blocked 的 `decision_ref` 正确，operation 只有一个逻辑结果。这个性质可作为判断方案是否足够稳健的标准。

## 8. 建议 E：让批准绑定内容摘要

### 原因

批准日期和版本号不能证明批准后内容没有被编辑。

### 结构示例

```yaml
spec_version: 2
approved_by: user
approved_at: 2026-08-13T10:00:00+09:00
approved_digest: sha256:abc123...
approved_against_principles_digest: sha256:def456...
```

如果采用 digest 方案，计算时需要排除批准字段本身，否则回填 digest 会再次改变 digest。可考虑明确如下 canonicalization：

1. 解析 frontmatter；
2. 删除 `approved_*` 和 `withdrawals`；
3. 以固定 key 顺序序列化 frontmatter；
4. 拼接正文原始 UTF-8；
5. 计算 SHA-256。

也可以改用独立 approval 账本，让批准事件引用文档 digest。后者审计性更好，但首版工作量更大。

### 用于评估建议的例子

- 只修改一个标点，`trace_check` 也应报告 `approval_stale`。
- 只增加 withdrawal 记录，不应让原 digest 校验发生无法解释的循环。
- principles 内容变化后，已有 spec 的 `approved_against_principles_digest` 应失效。

## 9. 建议 F：统一命令权威

### 原因

`registry_task` 和 `argv` 同时存在时会漂移；从 Markdown 读取 shell 命令直接执行也难以正确处理 quoting。

### 契约示例

LaunchOrder 保存：

```json
{
  "task_id": "evaluate",
  "args": {
    "model": "gpt-oss-120b",
    "dataset": "d17",
    "seed": 7
  },
  "registry_digest": "sha256:..."
}
```

运行层执行：

```text
registry.resolve(task_id, args) -> argv[]
```

RUNMETA 保存解析后的 `argv[]`。这样：

- 发射单说明意图；
- registry 是命令构造权威；
- RUNMETA 保存实际执行事实。

criterion 和 metrics extractor 使用同一模式：

```json
{
  "task_id": "check-principle-p003",
  "args": {"artifact": "${run.output_dir}"}
}
```

advisor 建议避免通过 `shell=True` 执行自由字符串。若工程确实需要 shell pipeline，可以考虑把 pipeline 封装成 registry 中的脚本任务。

## 10. 建议 G：澄清 R2、R3、R4 的边界

### R2 建议文本

```text
机械检查由程序执行；最终科学判断、是否接受结果、是否进入故事由用户决定。
agent 可以识别结构缺陷、整理证据和提出带证据的 blocker，但不得替用户作科学结论。
```

这样不会与 inspector 的 `clean/blockers` 体裁冲突，因为 blocker 是流程或证据缺陷，不是科学结论。

### R3 建议文本

```text
所有支撑经验性主张的数值必须具有复算命令或结构化 extractor 引用。
日期、行号、文件大小、hash、ID 等溯源元数据不要求逐项附独立命令，但必须能从所引文件机械读取。
```

例子：

- `accuracy=0.731`：必须能复算。
- `n=500`：必须由同一个 extractor 输出。
- `生成于 2026-08-13`：属于元数据，不需要额外命令。
- `见第 42 行`：属于定位信息，不需要额外命令。

### R4 建议文本

```text
spec 中已批准的 observation 和 derivation 定义视为预授权。
新增或改变公式、分母、过滤条件、聚合层级、缺失值处理时，必须重新获得批准。
```

例子：

- spec 已批准 `correct / total`：每批计算不需要再次询问。
- 临时把分母从全样本改成“成功完成样本”：必须重新批准。
- 临时新增 bootstrap CI：如果 spec 没写，必须先提案。

## 11. 建议 H：拆分 core 与 adapter

### Core 只保留

```text
role/layer
ledger/entity
approval
transition
provenance
query/status/reconcile
report/story
resource request 的抽象字段
```

### Adapter 负责

```text
怎样探测资源
怎样发射和停止
怎样采样健康状态
怎样写工程任务台账
怎样解析 registry
怎样定位大产物
```

### new1 policy 负责

```json
{
  "compute": {
    "adapter": "gpu-run",
    "standing_authorization": {
      "max_expected_runtime_s": 3600,
      "resource_type": "gpu"
    }
  },
  "artifact_roots": ["/net/.../reproduce/new1"],
  "roles": {
    "inspector_model": "opus",
    "reader_model": "sonnet"
  }
}
```

plugin core 不应出现 tokyo、NFS、48G、换卡或具体模型名。它可以支持这些概念，但值来自 adapter/config。

## 12. 建议 I：设计 fake rail 全链测试

### fixture

建议 plugin 自带：

```text
tests/fixtures/fake-project/
  registry.json
  tasks/fake_experiment.py
  tasks/fake_metrics.py
  expected/artifact.json
```

fake experiment 接受：

```text
--seed N
--mode ok|fail|timeout|empty|bad-metrics
--out DIR
```

`ok` 模式产生：

```json
{"correct": 7, "total": 10, "labels": ["a", "b"]}
```

metrics extractor 最后一行产生：

```json
{
  "observations": [
    {"metric_id": "accuracy", "value": 0.7, "n": 10},
    {"metric_id": "correct", "value": 7, "n": 10}
  ],
  "evidence_path": "artifact.json"
}
```

### 建议考虑的集成场景

1. 正轨成功闭环。
2. quick 成功但 story 拒绝。
3. quick 转正后 normal run 可进入 story。
4. empty output 记为 `empty-output`。
5. metrics 最后一行不是 JSON，拒绝 observation 入账并开 failure blocker。
6. 第一次 attempt 失败、第二次成功，两个 attempt 都可查。
7. spec 批准后修改一字，发射被 stale approval 门禁拒绝。
8. 在复合操作中间崩溃，reconcile 后链路完整。
9. 新会话只调用 status/next 即可继续。

## 13. 可能涉及的 spec 位置

如果用户决定采纳上述建议，下表可作为寻找修改落点的参考，而不是任务清单：

| 位置 | 应补内容 |
|---|---|
| §0.5 | 机器真源的精确定义、生成方向和禁止手改的生成物 |
| §1 | 开工读取 status/next；layer 是协作身份而非安全身份 |
| §2 | 当前循环恢复、复合操作落盘、幂等语义 |
| §2.6 | quick 转正引用完整 launch order，不再写“同 seed 即复现” |
| R2 | 区分机械缺陷判断与最终科学判断 |
| R3 | 将复算义务限定为经验性数字 |
| R4 | 已批准 metric/derivation 视为预授权 |
| R7 | task_id + structured args；禁止从 Markdown 执行自由 shell |
| §4 | 增加 status/reconcile、operation journal、fake rail；明确 v1/v1.1 |
| §5 | run/attempt/observation 与复合操作协议 |
| §7 | core/adapter/project policy 分界 |
| §8 | 增加中断恢复与 quick 转正剧本 |
| §9 | 完整 fake end-to-end、崩溃注入、多指标、批准失效测试 |

对应的 `tables/` 可能需要考虑以下落点：

| 文件 | 应补内容 |
|---|---|
| `rows.json` | executable schema、Run/Attempt/Observation、approval digest、operation |
| `ledgers.json` | attempts/observations/operations 或等价存储；active policy 名 |
| `writes.json` | 复合操作、幂等和 reconcile 权限 |
| `config.json` | adapter、role model、inspection policy、compute authorization policy |
| `routes.json` | status/resume、reconcile、quick promotion 的入口 |

## 14. 用于评估修订稿的问题

以下问题可用于评估修订稿是否减少了实现歧义；它们不是 advisor 代替用户设定的完成条件：

1. 不读自然语言说明也能从结构化表生成所有 JSON Schema。
2. run、attempt、observation 的主键和引用关系无歧义。
3. `status/next` 的输入、输出和 stage 派生规则已成文。
4. 五类复合操作有幂等和中断恢复协议。
5. approval digest 的 canonicalization 已成文。
6. task_id、args、argv、RUNMETA 的权威顺序已成文。
7. R2、R3、R4 不再互相冲突，也不会让常规已批准统计反复请求用户。
8. core 中没有 new1 专名或具体资源实现。
9. fake rail 九个集成场景进入 §9 验收。
10. `spec_lint.py` 更新并全绿，同时增加 schema 生成确定性检查。

从评审角度，先稳定设计、再单独制定 implementation plan 和 issues，会更容易区分架构问题与 new1 适配问题。这只是工作顺序建议，最终安排由用户和负责 agent 决定。
