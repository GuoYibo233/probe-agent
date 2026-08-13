# T05 报告 —— blocked 全跃迁 + r5 拼装 + grant/decision/decision-withdraw + R6

工单：`.scratch/research-loop/issues/05-blocked-decisions.md`
分支：`ticket/20260814-wave3/T05`
工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave3-T05`（收尾已 `git worktree remove`，分支保留）

## 一、做了什么（对照工单逐条）

### `research-loop/scripts/ledger_cmds/blockedcmd.py`

- **`blocked open`**（`--layer L` 即 `from_layer`，无独立 `--from-layer` 参数）：
  `blocked_id` 用 `_lib.alloc_id` 自增 B 前缀；`status=open`；
  `raised_at=now_iso()`；`kind=r5-choice` 时先在 CLI 层给可读报错
  （`blocked.where: kind=r5-choice requires --where and --options`），schema
  conditional 仍是兜底（两层都拦，工单原文"schema conditional 兜底，但 CLI
  先给可读报错"）；`--evidence` 用 `nargs="+"` 天然满足"至少一项"；
  持锁读现有行 → 建行 → `_lib.validate` → `_lib.jsonl_append`。
- **`blocked answer`**（`--layer L BID --answer TEXT [--answered-by user]
  [--chosen V] [--grant DID]`）：
  - 行不存在 → `blocked.blocked_id: row not found (got: 'BID')`；
    `status≠open` → `blocked.status: illegal transition to answered (got:
    '<当前值>')`（用 `_lib.fail` 的 `(got: ...)` 后缀，值走 `repr()` 自动加
    引号，跟工单原文的 `'<当前值>'` 字面一致，没有手拼字符串）。
  - 写权：`to_layer=user` 时任何 `--layer` 放行，`answered_by` 强制
    `"user"`（`--answered-by` 参数本身用 `choices=["user"]` 挡掉任何非
    `user` 的显式值，argparse 自己拒——工单"显式传 --answered-by 非 user →
    拒"落在这一层，测试 6 验证过）；`to_layer≠user` 时 `--layer` 必须等于
    `to_layer`，否则 `blocked.to_layer: only to_layer may write answered
    (got: '<L>')`。`answered_by = "user"`（`--answered-by user` 时）否则
    `= --layer` 值。
  - 非 r5 kind：只做就地更新（`status/answer/answered_at/answered_by`，
    `--grant` 给了就存 `grant_ref`）。
  - r5-choice：缺 `--chosen` 拒；`answered_by≠user` 缺 `--grant` 拒；
    `--grant` 指向的行必须在 `decisionscmd.active_grants()`
    （R6 机验落点）里，否则 `blocked.grant_ref: grant is not active`；
    写序按 `_write_order`——① 持 `decisions.jsonl` 锁，按 `blocked_ref=BID
    且 status=decided` 查重（幂等：命中就复用 `decision_id`，不重复
    append；> 1 条按"违反即拒"报 `decisions.blocked_ref: more than one
    decided decision synced to the same blocked row`）；未命中才机械拼装
    （`where/question/options` 抄 blocked 行，`chosen=--chosen`，
    `reason=--answer` 原文，`decided_by`/`authorized_by` 按 `answered_by`
    分流，`affects` 按 `blocked.ref` 是否 B 前缀判空，`blocked_ref=BID`，
    `raised_at=blocked.raised_at`）→ ② 就地更新 blocked（含回填
    `decision_ref`）；两步分属两把锁（`decisions.jsonl` 的锁只在 append
    这一小段内持有，`blocked.jsonl` 的锁贯穿整条命令）。
- **`blocked close`**（`--layer L BID`）：`--layer≠from_layer` 拒
  （`blocked.from_layer: only from_layer may close`）；`status∉{open,
  answered}` 拒（`illegal transition to closed`）；就地翻 `closed`。
- **`blocked withdraw`**（`BID --reason TEXT`，不收 `--layer`）：
  `status=open` → 工单原文一字不差的
  `blocked.status: withdraw applies to answered rows; from_layer should
  close open rows`；`status∉{answered,withdrawn}`（如 `closed`）→
  另一条防御性拒绝（工单没点名这个分支，行为定义见下"自查发现"第 1
  条）；`status=withdrawn` 时只做步骤①②的收敛修复（幂等，`exit 0`，不重
  复步骤③）。三步写序：① 经 `blocked.decision_ref` 找同步 decision，为空
  时按 `decisions.blocked_ref=BID 且 status=decided` 反查孤儿，找到且未
  `withdrawn` 才就地翻 `{status: withdrawn, withdrawn_by: user,
  withdrawn_reason: reason}`；② 按 `(ref=BID, status=open)` 查重，未命中
  才机械重开新条（`from_layer/to_layer/kind/question/where/options/
  evidence` 逐字抄旧条，`ref=BID`，新 `blocked_id`）；③ 旧条翻
  `withdrawn`，`answer` 尾部追加 `"\n[withdrawn by user: <reason>]"`。

### `research-loop/scripts/ledger_cmds/decisionscmd.py`

- **`grant`**（`--layer ∈ idea|deploy|run`，argparse `choices` 直接排除
  `oversight`——工单"--layer=oversight → 拒"落在这一层）：`--scope-desc`/
  `--scope-globs` 任一缺失 → `decisions.scope: grant requires structured
  scope`（工单原文字面）；`scope={desc, path_globs, expires_at}`；
  `decided_by=user`、`authorized_by=reason=--reason`、`where/options/
  chosen=null`、`affects=[]`、`raised_at=decided_at=now`、
  `status=decided`。
- **`decision`**：`decided_by` 缺省 `agent`。`decided_by=user` 时
  `--layer≠deploy` 拒（`decisions.decided_by: decided_by=user is only
  accepted from --layer deploy`）；`decided_by=agent` 时 `authorized_by`
  必须是字面 `spec-standing-gpu-1h` 或 `grant:D0xx`（格式先查，`grant:`
  前缀命中后持锁查 `active_grants()`，不在里面 →
  `decisions.authorized_by: authorized_by grant is not active`）。
  `where/options/chosen` 走 argparse `required=True`（schema conditional
  兜底）；`affects=--affects` 或 `[]`。
- **`decision-withdraw`**（`DID --reason TEXT`，不收 `--layer`）：行不存在
  拒；就地 `{status: withdrawn, withdrawn_by: user, withdrawn_reason:
  reason}`；`--superseded-by` 给了先查存在（`decisions.superseded_by: row
  not found`）才回填。
- **`active_grants(rows, now)`**（T09 消费的导出函数，工单原文签名）：
  `kind=grant` 且 `status=decided` 且 `superseded_by is None` 且
  `scope.expires_at is None or > now`。blockedcmd 的 R6 机验、
  decisionscmd 自己的 `decision` agent-授权校验都调它，不重复实现。

### 写入纪律

两个模块的每一次落盘（`open`/`grant`/`decision` 的 append，`answer` 里
拼装的 decision append，四条命令各自的 in-place update）都过
`_lib.validate`（针对合并后的完整行，不只是改动字段）+ `_lib.locked`；
白名单字段从 `tables/writes.json write_forms.form2_inplace_whitelist`
运行时读取，不在两个模块里各写一份字面量副本。

### `research-loop/tests/test_blocked_decisions.py`

工单"测试"清单 12 条逐条落测试函数（函数名标了对应关系，见下"怎么验证的"）
，另加四条边界补测：`close` 的写权/状态门、`decision-withdraw` 自身、
四个命令的"行不存在"分支。共 24 个测试函数。

## 二、怎么验证的

### 自查发现并修复的一处底表缺陷（详见"四、自查发现"第 2 条）

写测试跑第一轮时，**每一条**涉及 r5-choice 的测试（4/5/6/7/8/9/12，共
7/12 条）在 `blocked open` 这一步就全部失败，报错
`blocked.grant_ref: required when kind eq 'r5-choice' and answered_by neq
'user'`——直接用 `_lib.validate()` 单独复现确认：`tables/rows.json`
`blocked_row` 的第二条 conditional 只按 `kind=r5-choice 且 answered_by≠
user` 判断是否要求 `grant_ref`，但 `answered_by` 在行从未被答复时恒为
`null`，`null != "user"` 在 Python 里成立，条件在 **open 时就误触发**——
r5-choice 的行永远开不出来（更下游地，withdraw 机械重开一条 r5-choice
行时同样会撞上这条）。这不是工单需求的歧义，是 `tables/rows.json` 里一条
写漏了 `status` 子句的机器规则（`_note` 原文"D00x|null（answered_by≠user
的 r5-choice 必填）"本身用的是"答复"这个词，跟 spec.md §5"答复必传
--grant"一致，说明本意就是限定在已答复之后），修复方式是给这条
conditional 的 `when` 数组加一个 `{"field": "status", "op": "eq", "value":
"answered"}`，然后走 `genschemas.py` 自己文档里写明的"fix the table,
regenerate"路径重新生成 `schemas/blocked.schema.json`——`gen-schemas
--check` 确认这条改动之外的另外 7 个 schema 文件 + `owners.default.json`
一字节没变。这处改动单独一个 commit（`8498bcb`），跟 T05 自己的功能 commit
分开，方便审查/回滚。

### `python3 research-loop/tests/run_all.py test_blocked_decisions`

```
PASS test_blocked_decisions.test_active_grants_excludes_expired_wrong_status_superseded_and_wrong_kind
PASS test_blocked_decisions.test_answer_r5_converges_after_simulated_partial_write
PASS test_blocked_decisions.test_answer_r5_second_identical_run_rejected_no_double_decision
PASS test_blocked_decisions.test_answer_r5_with_answered_by_user_does_not_require_grant
PASS test_blocked_decisions.test_answer_write_rights_to_layer_must_match
PASS test_blocked_decisions.test_close_write_right_and_status_gate
PASS test_blocked_decisions.test_decision_agent_with_grant_authorized_by_requires_active_grant
PASS test_blocked_decisions.test_decision_agent_without_valid_authorized_by_rejected
PASS test_blocked_decisions.test_decision_decided_by_user_only_accepted_from_layer_deploy
PASS test_blocked_decisions.test_decision_spec_standing_gpu_1h_passes
PASS test_blocked_decisions.test_decision_withdraw_sets_fields_and_validates_superseded_by
PASS test_blocked_decisions.test_grant_missing_scope_globs_rejected
PASS test_blocked_decisions.test_grant_oversight_rejected
PASS test_blocked_decisions.test_grant_valid_lands_in_active_grants
PASS test_blocked_decisions.test_illegal_transitions
PASS test_blocked_decisions.test_open_creates_b001
PASS test_blocked_decisions.test_open_r5_choice_missing_where_options_rejected
PASS test_blocked_decisions.test_r5_answer_requires_chosen_then_grant_then_active_grant
PASS test_blocked_decisions.test_row_not_found_errors
PASS test_blocked_decisions.test_to_layer_user_any_layer_can_answer_but_answered_by_locked_to_user
PASS test_blocked_decisions.test_withdraw_answered_row_reopens_then_idempotent_rerun
PASS test_blocked_decisions.test_withdraw_open_row_rejected
PASS test_blocked_decisions.test_withdraw_orphan_reverse_lookup_via_blocked_ref
PASS test_blocked_decisions.test_withdraw_syncs_decision_to_withdrawn
-- run_all: 24 passed, 0 failed
```

工单 12 条与函数的对应关系：1→`test_open_r5_choice_missing_where_options_
rejected` + `test_open_creates_b001`；2→`test_answer_write_rights_to_layer_
must_match`；3→`test_illegal_transitions`；4→`test_r5_answer_requires_
chosen_then_grant_then_active_grant`；5→`test_answer_r5_with_answered_by_
user_does_not_require_grant`；6→`test_to_layer_user_any_layer_can_answer_
but_answered_by_locked_to_user`；7→`test_answer_r5_second_identical_run_
rejected_no_double_decision`；8→`test_withdraw_open_row_rejected` +
`test_withdraw_answered_row_reopens_then_idempotent_rerun` +
`test_withdraw_syncs_decision_to_withdrawn`；9→`test_withdraw_orphan_
reverse_lookup_via_blocked_ref`；10→`test_grant_missing_scope_globs_
rejected` + `test_grant_oversight_rejected` + `test_grant_valid_lands_in_
active_grants` + `test_active_grants_excludes_expired_wrong_status_
superseded_and_wrong_kind`；11→`test_decision_agent_without_valid_
authorized_by_rejected` + `test_decision_spec_standing_gpu_1h_passes` +
`test_decision_decided_by_user_only_accepted_from_layer_deploy`（另加
`test_decision_agent_with_grant_authorized_by_requires_active_grant` 补
`decision` 命令自己的 grant 有效性检查，工单没点名但代码路径是我写的）；
12→`test_answer_r5_converges_after_simulated_partial_write`。

### 全量：`python3 research-loop/tests/run_all.py`

```
-- run_all: 82 passed, 0 failed
```

（24 个新测试 + T02/T03/T12 遗留的 58 个，全绿。）

### `gen-schemas --check` / `spec_lint.py`

```
$ python3 research-loop/scripts/ledger.py gen-schemas --check; echo exit=$?
exit=0
$ python3 .scratch/research-loop/spec_lint.py 2>&1 | tail -3
-- spec_lint: 0 errors, 0 warnings
```

## 三、commit 清单

- `8498bcb` — `T05: fix blocked_row schema conditional that blocked every
  r5-choice open`（`tables/rows.json` + `schemas/blocked.schema.json`，
  独立一个 commit，见上"自查发现"）。
- `2a24c52` — `T05: blocked ledger's four transitions +
  grant/decision/decision-withdraw + R6`（`blockedcmd.py` +
  `decisionscmd.py` + `test_blocked_decisions.py`，功能与测试同一逻辑
  单元，一次提交）。

## 四、自查发现与存疑

1. **`blocked withdraw` 对 `status=closed`（或任何非
   open/answered/withdrawn 状态）的拒绝消息是我自己定的，工单没点名这个
   分支**：工单原文只给了 `status=open` 的精确报错字面
   （`withdraw applies to answered rows; from_layer should close open
   rows`），对 `closed` 之类的状态没有给出对应文案。我的处理：
   `status not in ("answered", "withdrawn")` 时报
   `blocked.status: withdraw does not apply to status='closed' rows`
   ——跟 `open` 分支分开成两条 `fail`，不套用"应该 close open 行"这句对
   `closed` 状态明显不通顺的话。没写专门测试断言这条具体文案（工单没要
   求），行为本身（拒绝）在 `test_illegal_transitions` 里间接验证过（那
   条测试撞的是 `close` 不是 `withdraw`，`withdraw` 对 `closed` 行的拒绝
   路径没有独立测试覆盖——如果后续发现这条分支的精确文案要对齐别处消费方
   （比如渲染层或某个 SKILL.md 的报错处理），需要回来改)。

2. **修了一处不在本工单文件清单里的底表缺陷**（`tables/rows.json` +
   `schemas/blocked.schema.json`，见上"自查发现"整段）：工单"文件"一节
   只列了三个要 Create 的文件，没提这两个。我判断这处修复"安全可自行裁决"
   （没有停下转 `NEEDS_CONTEXT`）的依据：① 缺陷本身是纯机械翻译错误
   （英文/中文 `_note` 原文与 spec.md §5 都写的是"答复"/"回复"才触发，
   不是需求本身有歧义）；② 缺陷不修，工单 12 条测试里 7 条（涉及 r5 的
   全部）连第一步 `open` 都过不去，等于本工单交付的核心功能（R5/R6 那一
   半）完全不可用、不可测；③ 修复走的是 `genschemas.py` 自己文档里写明
   的"改表→重新生成"路径，不是手改生成物；④ 改动面窄到一条 conditional
   的一个 `when` 子句，`gen-schemas --check` 证实除 `blocked.schema.json`
   外零改动；⑤ 独立成一个 commit，标题/正文都点明是"发现并修复上游缺陷"
   ，方便主会话审查或回滚这一处而不影响 T05 自己的功能 commit。如果这个
   判断不对（比如别的并行工单——T06/T07/T08/T09——依赖这条 conditional 的
   旧（错误）行为，或者主会话认为这类改动无论如何都该走 `NEEDS_CONTEXT`
   ），需要回来重新裁决。

3. `blocked answer` / `blocked withdraw` / `decision-withdraw` 每次就地
   更新前都先构造"合并后的完整行"跑一遍 `_lib.validate`，再调用
   `_lib.inplace_update`——工单没有逐字这样写，但 spec.md §5"写入两式：
   原子追加 + 白名单字段就地更新（都过 schema 与写权检查、都持文件锁）"
   明确要求 form2（就地更新）也要过 schema，而 `_lib.inplace_update` 本身
   不做 schema 校验（只做白名单字段检查），所以这一步是我在两个模块里都
   统一补的模式，不是工单某一条要求点名的，但四条就地更新路径（
   `answer`/`close`/`withdraw` 步骤①③/`decision-withdraw`）全部一致地这样
   做了，没有遗漏某一条。

4. CLI 成功路径统一在 stdout 打印单行 JSON（新建或更新后的行/摘要）——
   工单和 plan.md §C2 都没有规定成功时该往 stdout 输出什么，我选了这个
   最小约定（跟 `output_check.py` 的"stdout 最后一行是结构化 JSON"风格
   呼应），主要目的是让上层 skill/脚本能拿到刚分配的 `blocked_id`/
   `decision_id` 而不必再读账本文件。没有工单条款依赖这个输出格式，纯粹
   是可用性上的自选设计，如果后续某个消费方（比如 T15 的 SKILL.md 或
   inspector agent）期望不同的输出形态，这里可以改，不会牵连账本写入本身
   的正确性。

## 五、修复第 1 轮（finding F1）

工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave3-T05-fix1`（同一分支
`ticket/20260814-wave3/T05` 检出，完事已 `git worktree remove`）

### F1：commit 8498bcb 越过工单声明的文件范围，改了共享真源
`tables/rows.json` / `schemas/blocked.schema.json`

finding 本身已经确认这处修复技术上是对的——不修，T05 自己 12 条测试里
7 条（涉及 r5 的全部）连 `open` 都过不去。finding 要求的不是撤回这处
修复，而是主会话在合并前对"是否与 T06–T09 冲突"有一个查证过的裁决，
而不是实现者自己关起门来决定、事后在报告里补一句"存疑"。

这一轮做的事：把 finding 要的查证补上，查证结果记在工单文件本身（而不是
只记在这份实现者自己写的报告里），让 T06–T09 的实现者或复核者不用重新
查一遍就能看到结论。

**查证过程**（在修复工作树里对 `git log`/`git diff` 直接跑，命令与输出见
下"怎么验证的"）：

- T06（`ticket/20260814-wave3/T06`，已有 2 个 commit）：
  `git diff main T06 -- research-loop/tables/rows.json research-loop/schemas/
  research-loop/tables/writes.json` 输出为空——T06 完全没碰这几个文件。
- T07（`ticket/20260814-wave3/T07`，已有 3 个 commit）：同样的 diff 为空。
- T08（`08-launch-order.md`）：`Blocked by: 03, 05`——按依赖图它本来就要
  等 T05 合并之后才会起，不存在"并行读到旧（错误）表"的时间窗口，谁在
  T05 之后合并都一样。
- T09（`09-query-status.md`）：`Blocked by: 03`，当前 `Status:
  ready-for-agent`，还没建分支；工单原文自己写"fixture 全用 helpers 行
  工厂裸写账本（不依赖其他工单的 CLI）"——它读的是 `status_view` 那条
  派生源，不经过 `blocked open` 的 `_lib.validate()`，跟这条 `grant_ref`
  conditional 不搭界，谁先合并都不影响它。

**处置**：commit 8498bcb 原样保留在 T05 分支里，不撤、不拆成另一个分支
（拆分支属于扩大范围的重构，工单没要）。改动是：在
`.scratch/research-loop/issues/05-blocked-decisions.md` 的 `## Comments`
下追加一条记录，把上面的查证过程、依据、裁决写进去——这是工单文件本身
（在 T05 工单范围内），也是本仓 issue-tracker 约定（`docs/agents/
issue-tracker.md`）里"评论追加到文件末尾 Comments 标题下"的既有用法，
不是新开的机制。最终是否合并仍由主会话在分支终审时拍板，这一轮只是把
finding 点名要的"查证"这一步做完、有据可查。

### 怎么验证的

```
$ git diff main ticket/20260814-wave3/T06 -- research-loop/tables/rows.json research-loop/schemas/ research-loop/tables/writes.json
（空输出）
$ git diff main ticket/20260814-wave3/T07 -- research-loop/tables/rows.json research-loop/schemas/ research-loop/tables/writes.json
（空输出）
$ grep -n "Blocked by" .scratch/research-loop/issues/08-launch-order.md .scratch/research-loop/issues/09-query-status.md
.scratch/research-loop/issues/08-launch-order.md:4:Blocked by: 03, 05
.scratch/research-loop/issues/09-query-status.md:4:Blocked by: 03
```

本轮没改任何功能代码，只改了工单文件的 Comments 段，仍按规程重跑覆盖
T05 改动面的测试，确认修复轮没引入回归：

```
$ python3 research-loop/tests/run_all.py test_blocked_decisions
（24 项全 PASS）
-- run_all: 24 passed, 0 failed
$ python3 research-loop/tests/run_all.py
（82 项全 PASS，含 test_genschemas / test_lib / test_output_error）
-- run_all: 82 passed, 0 failed
$ python3 research-loop/scripts/ledger.py gen-schemas --check; echo exit=$?
exit=0
$ python3 .scratch/research-loop/spec_lint.py 2>&1 | tail -3
-- spec_lint: 0 errors, 0 warnings
```

### commit 清单（本轮）

- `5996e9a` — `T05: append F1 cross-ticket investigation to ticket
  Comments (fix round 1)`（只改
  `.scratch/research-loop/issues/05-blocked-decisions.md`）。

### 自查

- 没有碰 `blockedcmd.py`/`decisionscmd.py`/`test_blocked_decisions.py`
  以外任何功能文件，也没有再碰 `tables/rows.json`/`schemas/`——finding
  F1 本身不是要求撤回或改代码，是要求把查证和裁决记录下来，这一轮只做
  了这一件事，没有借机顺手改别的。
- 没有创建新工单、没有拆分支——finding 明确说"是否要走 NEEDS_CONTEXT
  补票"是留给主会话的开放问题之一，我没有替主会话把这个口子开成新工单；
  按查证结果（零冲突、T08 已被 Blocked-by 天然排在 T05 之后、T09 尚未
  起分支）判断没有必要，但这仍是给主会话的建议而非最终裁决。
