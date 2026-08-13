# T09 query + status + render blocked

Status: claimed
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `tables/ledgers.json`（read 列、active 列、`_read_classes`）+
`tables/rows.json`（status_view **逐字段派生源，实现只许照抄**）+
`tables/routes.json`（waiting_on 的 action 值域）+ spec.md §2、§2.1。

## 文件

- Create: `research-loop/scripts/ledger_cmds/querycmd.py`
- Create: `research-loop/scripts/ledger_cmds/statuscmd.py`
- Create: `research-loop/tests/test_query_status.py`

## 要求

### query LEDGER [过滤...] [--all-rows] [--include-archive]

- 只服务 format=jsonl 的账；md 账 → 拒
  `query.<ledger>: md ledger, read the file directly (md-full)`；
  json 单件 → 拒（direct）。
- 默认视图 = ledgers.json active 列逐账实现：
  - story: status=active
  - blocked: status ∈ {open, answered}
  - decisions: active_grants（import decisionscmd.active_grants）∪ 被引用行
    （引用源扫描：blocked 账的 grant_ref/decision_ref、decisions 自身的
    superseded_by、launch_orders 目录各单的 decision_refs）
  - feedback: 建议条按最新 review 行合并后 pending = 没有任何 review 行
    指向它的 suggestion（review 行本身不进默认视图）
  - runs: **无默认视图**——--batch/--run/--since/--metric 至少一个，否则拒
    `query.runs: refuse to return the full table; add a filter
    (--batch/--run/--since/--metric) or read the rendered product`；
    --all-rows 也不豁免这条。
- --all-rows：跳过 active 过滤（runs 除外）；--include-archive 透传 jsonl_rows。
- 便利过滤 --status/--to-layer/--kind 后置生效。--since 按 recorded_at
  （runs）/raised_at（blocked）/date（story、feedback）/decided_at（decisions）。
- 输出：JSON 数组，indent 2。

### status --layer L（statuscmd）

**输入输出契约 = tables/rows.json status_view，逐字段照抄派生源；
纯只读（不写任何文件、不缓存）。** 输出单个 JSON 对象，字段与派生：

- schema_version=1；generated_at=now_iso()；layer=--layer。
- approved_specs_in_flight：specs 目录递归 *.md，frontmatter approved_by
  非空，且其功能目录（spec 文件同级）的 issues/*.md 存在 Status 行非终态
  （终态={resolved, wontfix}）的 → 列 spec 路径。允许多份。
- open_issues：issues 目录 *.md，Status 行非终态 → {issue_id: 文件名去后缀, path}。
- pending_launch_orders：launch_orders 目录 *.json，文件名 run_id 不在 jobs
  台账 → {run_id, path}。
- running_runs：jobs 台账 state/status == running 的 run_id。
- unrecorded_runs：jobs 终态（done/failed/timeout）且 runs 账（跨档）无该
  run_id 行。
- batches_pending_report：runs 账 batch_id 非空的去重值中，plans/ 目录无
  任何 *.md 的 frontmatter batch_id 等于它的。
- batches_pending_inspection：plans/*.md frontmatter inspection_report 为
  空串 → {batch_id, path}。
- open_blocked / pending_user_decisions / active_grants：照 status_view。
- waiting_on：[{item, ref, layer, action}]，action **运行时从
  tables/routes.json 的 to 列取原文**，两类：pending_user_decisions 逐条 →
  action = say 以"有什么在等我"开头那行的 to；batches_pending_inspection
  逐条 → action = say 以"深查这批"开头那行的 to。
- inconsistencies：[{code, ref, source}] 只列不猜，恰三类廉价核对：
  ① 批次报告 run_ids 里 runs 账查无 → code=report-run-missing；
  ② jobs 终态与 runs 行状态矛盾（job done 但 runs 行 status 非 ok，或
    job failed/timeout 但 runs 行 status=ok）→ code=jobs-runs-status-mismatch；
  ③ 发射单 created_at + expected_runtime_s×runtime_factor 已过、jobs 仍查无
    → code=launch-overdue。
- jobs 读法宽容（plan.md §C5）：dict 或 list 都收，认 run_id/name 与
  state/status 键；解析不了的条目跳过不报错。
- 不设 stage 字段（status_view._no_stage）。

### render blocked（维护/渲染动作，不收 --layer）

status ∈ {open, answered} 的行按 to_layer 分组渲染成 md 表打 stdout
（列：blocked_id/kind/question/from_layer/raised_at）。

## 测试（test_query_status.py）

fixture 全用 helpers 行工厂裸写账本（不依赖其他工单的 CLI）。

1. query story 默认只出 active；--all-rows 连 retired 一起出。
2. query runs 无过滤拒（--all-rows 也拒）；--run/--batch/--metric/--since
   各过滤正确。
3. query decisions 默认视图：过期 grant 不出；被 blocked.grant_ref 引用的
   过期 grant 出（被引用行保留）。
4. query feedback：有 review 指向的 suggestion 不出，没有的出。
5. query principles（md 账）拒。
6. --include-archive：行只在 runs.archive.jsonl 里 → 默认查无、
   --include-archive 查到。
7. status 四断点 fixture 各落对应字段：发射单已写未发 →
   pending_launch_orders；jobs done 无 runs 行 → unrecorded_runs；
   runs 有行无批次报告 → batches_pending_report；报告头 inspection_report=""
   → batches_pending_inspection。
8. 批次报告引用不存在 run_id → 只进 inconsistencies（code=report-run-missing），
   其余字段照常出。
9. 同一账本连查两次，除 generated_at 外逐字节一致；跑前后沙盒目录内容
   （文件清单+各文件 sha）完全不变——status 不写盘。
10. waiting_on 的 action 值恰是 routes.json to 列原文（断言字符串相等）。

## Comments

- 2026-08-14 预警（T03 落地后的对接契约，实现前必读 ledger.py 现状）：
  `render` 的 argparse parser 由 ledger.py 自己注册（只有一个 target 位置参数），
  target→模块映射在 ledger.py 的 `_RENDER_TARGET_MODULES`（blocked→querycmd）。
  本工单**不要**给 render 注册 parser，只需在 querycmd.run(args) 里认
  `args.command == 'render'` 分支；认为映射不对就回头改 ledger.py 那张表。
  另：分组子命令未实现时的文案是 `not implemented yet: <顶层子命令名>`（不带
  二级动词），测试断言按此格式。

- 2026-08-14 预警（T05 落地后的对接契约）：decisionscmd 已导出
  `active_grants(rows, now)`，语义 = kind=grant 且 status=decided 且
  superseded_by 为 null 且（scope.expires_at 为 null 或 > now）。本工单
  query decisions 默认视图直接 import 这个函数，别自己重写一份语义。
