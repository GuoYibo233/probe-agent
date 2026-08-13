# T09 报告 — query + status + render blocked

工单：`.scratch/research-loop/issues/09-query-status.md`
分支：`ticket/20260814-wave4/T09`，base `963bdaaf26fb897482e61c3fc4a6629005ec25c0`

## 做了什么

对照工单逐条要求：

### query LEDGER [过滤...] [--all-rows] [--include-archive]

- 只服务 `format=jsonl` 且 `read=query-only` 的账（通过 `tables/ledgers.json`
  查表判定，不硬编码账名清单）；md 账拒绝文案
  `query.<ledger>: md ledger, read the file directly (md-full)`（逐字符匹配
  工单给的原文）；json 单件（`direct` 读法类）拒绝文案
  `query.<ledger>: json ledger, read the file directly (direct)`；`sliced`
  类同理给出对应文案。三类拒绝共用一张 `_REJECT_DETAIL` 表。
- 默认视图逐账实现，均为纯函数：
  - story：`status=active`。
  - blocked：`status ∈ {open, answered}`。
  - decisions：`decisionscmd.active_grants(rows, now)`（直接 import，未重写
    语义）∪ 被引用行——引用源三处：blocked 账的 `grant_ref`/`decision_ref`、
    decisions 自身的 `superseded_by`（在已加载的 `rows`——即同一次
    `--include-archive` 决定下——里扫，不额外重读）、`launch_orders/*.json`
    各单的 `decision_refs`（始终按 launch_orders 账自身默认读法读，不随
    query 的 `--include-archive` 变化——该参数只对被查询的账本本身透传）。
  - feedback：suggestion 行按 review 行的 `ref` 是否指向它判定 pending，
    review 行本身永不进默认视图。
  - runs：无默认视图——`--batch`/`--run`/`--metric`/`--since` 一个都没给
    时拒绝，文案与工单给定原文逐字符一致；`--all-rows` 不豁免这条（检查发生
    在读默认视图之前，与 `--all-rows` 值无关）。
- `--all-rows` 跳过默认视图函数（对 runs 是恒等函数，效果上等价于工单说的
  "runs 除外"）；`--include-archive` 透传给 `_lib.jsonl_rows`。
- 便利过滤 `--status`/`--to-layer`/`--kind`/`--batch`/`--run`/`--metric` 均为
  `row.get(field) == value`，在默认视图之后生效；`--since` 按账本类型查
  `_SINCE_FIELD` 映射（runs→recorded_at、blocked→raised_at、
  story/feedback→date、decisions→decided_at）。
- 输出 `json.dumps(rows, indent=2, ensure_ascii=False)`，不排序（保留读出顺序）。

### status --layer L

- 输出严格照抄 `tables/rows.json` `status_view` 的十四个字段逐条派生源，
  没有另加派生规则；全程只读——不写文件、不建缓存、不落盘（`run()` 内没有任何
  `_lib.locked()`/写调用）。
- `approved_specs_in_flight`：递归扫 specs 账（`.scratch/**/*.md`），非
  frontmatter 文件（`_lib.parse_frontmatter` 抛错）跳过不报错；
  `approved_by` 非空 + 同级 `issues/*.md` 存在非终态（终态=`{resolved,
  wontfix}`，按工单原话，不是五档 triage 标签）Status 行 → 收录。
- `open_issues`：`issues` 账的 default_path 本身带通配符
  `.scratch/*/issues/`，用 `Path.relative_to(root)` 转成相对通配串再
  `root.glob()`，兼容工程覆盖同样带通配符的场景。
- `pending_launch_orders`/`running_runs`/`unrecorded_runs`：jobs.json 宽容
  读法（`_load_jobs`）——dict（键=run_id）与 list 两种形状都收，认
  `run_id`/`name` 与 `state`/`status` 键，解析不了的条目跳过不报错
  （plan.md §C5）。
- `batches_pending_report`/`batches_pending_inspection`：共用一次
  `_batch_report_headers()` 扫描结果（避免两次读盘、两次解析口径打架）。
- `active_grants`：同样直接 import `decisionscmd.active_grants`，不重写。
- `waiting_on`：action 文本运行时从 `tables/routes.json` 取——`_route_to()`
  找 `say` 以给定前缀开头的那行的 `to` 原文，两类分别对应"有什么在等我"与
  "深查这批"；若表里找不到对应路由（配置漂移）主动 `_lib.fail`，不是静默出
  null。
- `inconsistencies`：三类廉价核对逐条实现——① 批次报告 `run_ids[]` 在 runs
  账查无；② jobs 终态与 runs 行 status 矛盾（done 但非 ok / failed|timeout
  但 ok）；③ 发射单 `created_at + expected_runtime_s×runtime_factor` 已过
  且 jobs 仍查无。
- 每个列表字段内部排序（sorted），保证同一份账本连查两次输出确定性一致
  （测试 9 直接验证）。

### render blocked

`querycmd.run(args)` 认 `args.command == 'render'` 分支（未在
`querycmd.register()` 里另注册 render 的 parser，`--layer` 也不收，照工单
2026-08-14 预警执行）；按 `status ∈ {open, answered}` 过滤、按 `to_layer`
分组（顺序取 `tables/rows.json` enums `blocked.to_layer`），每组打印
`blocked_id | kind | question | from_layer | raised_at` 表。

`ledger.py` 的 `_SUBCOMMAND_MODULES`（"query"→querycmd、"status"→statuscmd）
与 `_RENDER_TARGET_MODULES`（"blocked"→querycmd）在 T03 落地时已经写好，
本工单未改动 `ledger.py`。

### 范围声明遵守情况

- 未改 `run.py`/`MAP.md`（工单范围声明要求）——该 skill 铁律因此不适用于本单。
- 全程标准库，无第三方依赖。
- fixture 全部用 `helpers.py` 现有行工厂 + 测试文件内新写的 md/json 直写
  helper（`_write_launch_order`/`_write_jobs`/`_write_batch_report`/
  `_write_spec`/`_write_issue`），未调用 `story add`/`blocked open` 等
  CLI 写路径，也未改动 `tests/helpers.py`。

## 怎么验证的

```
$ python3 research-loop/tests/run_all.py test_query_status
PASS test_query_status.test_query_decisions_default_view_referenced_expired_grant_kept
PASS test_query_status.test_query_direct_ledger_rejected
PASS test_query_status.test_query_feedback_pending_excludes_reviewed_and_review_rows
PASS test_query_status.test_query_principles_md_ledger_rejected
PASS test_query_status.test_query_runs_batch_run_metric_since_filters
PASS test_query_status.test_query_runs_include_archive_reads_archive_file
PASS test_query_status.test_query_runs_requires_filter_and_all_rows_does_not_exempt
PASS test_query_status.test_query_story_default_active_all_rows_includes_retired
PASS test_query_status.test_render_blocked_groups_by_to_layer
PASS test_query_status.test_status_approved_specs_in_flight_and_open_issues
PASS test_query_status.test_status_four_breakpoints_land_correct_fields
PASS test_query_status.test_status_inconsistency_report_run_missing_other_fields_unaffected
PASS test_query_status.test_status_repeat_query_is_byte_identical_and_writes_nothing
PASS test_query_status.test_status_waiting_on_action_matches_routes_to_column
-- run_all: 14 passed, 0 failed
```

全量回归（含其余 8 个既有 test_*.py，141 条）：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 155 passed, 0 failed
```

`python3 run.py selfcheck` 未跑——本单未改 `run.py` 注册表（工单范围声明
明确排除），该门禁不适用。

`ledger.py --help` / `ledger.py query --help` / `ledger.py status --help`
人工核对过一遍，子命令列表与参数面板正常出现（未被占位符吞掉）。

## commit 清单

- `6dac9c3` T09: add ledger.py query/status/render-blocked（三个新文件：
  querycmd.py、statuscmd.py、test_query_status.py，一次性提交——三者是
  同一个逻辑单元，query 的默认视图与 status 的部分派生共用
  `_iter_launch_orders`，拆开提交没有意义）

## 自查发现与存疑

- **`waiting_on` 的 `item`/`layer` 字段是我自己设计的**：工单只锁死了
  `action` 必须逐字等于 routes.json 的 `to` 列（测试 10 已验证），
  `[{item, ref, layer, action}]` 的字段名来自 `tables/rows.json`
  `status_view.waiting_on`，但 `item`/`layer` 两个字段具体取什么值工单和
  rows.json 都没有给出可执行定义。我的选择：`item` 取 `"blocked"`/`"batch"`
  区分两类来源，`layer` 取该项的目标层（pending_user_decisions 恒为
  `"user"`；batches_pending_inspection 取 `"deploy"`，因为触发"深查这批"的
  通常是部署层）。测试没有断言这两个字段的具体值，只断言了 `action` 与
  `ref`。如果这两个字段将来被其他消费者（比如某层 SKILL.md 的渲染逻辑）
  依赖具体取值，需要回头对齐。
- **`--status`/`--to-layer`/`--kind`/`--batch`/`--run`/`--metric` 便利过滤
  未做"这个字段对这个账本是否有意义"的校验**：比如 `query story --kind X`
  这种账本本没有 `kind` 字段的组合，会静默返回空数组而不是报错。工单原文
  只说"便利过滤...后置生效"，没有要求校验适用性，我按最简单行为实现；如果
  这个空返回容易被误读成"账本是空的"，可能需要后续加一层字段适用性校验。
- **`_decisions_referenced_ids` 里对 blocked/launch_orders 的扫描不跟随
  query 自身的 `--include-archive`**：这是我对"引用源扫描"应该读哪个版本
  的账本做的设计判断（spec §2.1 "--include-archive：透传 jsonl_rows"，
  字面上只提到"被查询的账本"），报告里已在代码注释和上面"做了什么"段落写明
  理由，供复核。
- 未新增测试覆盖 `query` 对不存在账名（比如 `query nosuchledger`）的报错
  路径——工单没有点名这个场景，属于我判断为不在验收范围内主动收敛
  （YAGNI 方向）而不是遗漏；代码路径本身存在（`_lib.fail("query", name,
  "unknown ledger")`），只是没有单独测试。

## 修复第 1 轮（2026-08-14）

分支同一条 `ticket/20260814-wave4/T09`，工作树
`new1-wt/20260814-wave4-T09-fix1`，base 沿用上一轮的
`963bdaaf26fb897482e61c3fc4a6629005ec25c0`（检出已有分支，未新开）。

两条 finding 逐条修：

### F1（critical）unrecorded_runs 未跨档读 runs 账

`_unrecorded_runs`（`statuscmd.py`）原调用
`_lib.jsonl_rows(cfg.ledger_path("runs"))`，没传 `include_archive=True`。
工单原文只在 `unrecorded_runs` 这一条上写了「（跨档）」，`batches_pending_report`
与 `inconsistencies` 两处读 runs 账的地方工单没有这个字样，因此只改
`_unrecorded_runs` 这一处，另两处按原样保留（对照 finding 的裁决范围，不
借机顺手改，避免超出这条 finding 本身）。

改法：

```python
runs_ids = {
    r.get("run_id")
    for r in _lib.jsonl_rows(cfg.ledger_path("runs"), include_archive=True)
}
```

新增回归测试 `test_status_unrecorded_runs_reads_across_archive`：jobs.json
记一个终态 job，对应的 runs 行只写进 `runs.archive.jsonl`（不写主文件），断言
`unrecorded_runs == []`。修复前用这条测试验证过会失败（把 `include_archive=True`
临时去掉重跑，`FAIL test_query_status.test_status_unrecorded_runs_reads_across_archive`
——`run_all: 15 passed, 1 failed`），确认测试确实钉住这条 bug 而不是空跑；随后
恢复修复，全绿。

### F2（important）jobs.json 的 list 形态零测试覆盖

`_load_jobs` 的 list 分支代码此前就存在且看起来正确，纯粹是缺测试。新增
`test_status_jobs_list_form_read_tolerantly`：jobs.json 写成 list，五个条目
分别覆盖：
- `{"run_id": ..., "state": "running"}` —— run_id 键 + state 键，正常收录，
  出现在 `running_runs`。
- `{"name": ..., "status": "done"}` —— name 键 + status 键（键名的另一种
  组合），正常收录，终态且 runs 账查无 → 出现在 `unrecorded_runs`。
- `"not-a-dict-entry"` —— 非 dict 条目，断言不崩、被跳过。
- `{"state": "done"}` —— 缺 run_id/name，断言被跳过（不出现在任何输出字段）。
- `{"run_id": "run-list-no-state"}` —— 缺 state/status，断言被跳过。

未改 `_load_jobs` 本身的实现——finding 明确写的是"零覆盖"而非"实现有错"，
代码走查确认逻辑符合工单 §C5 的宽容读法要求，属补测试而非改代码。

## 怎么验证的（修复轮）

```
$ python3 research-loop/tests/run_all.py test_query_status
PASS test_query_status.test_query_decisions_default_view_referenced_expired_grant_kept
PASS test_query_status.test_query_direct_ledger_rejected
PASS test_query_status.test_query_feedback_pending_excludes_reviewed_and_review_rows
PASS test_query_status.test_query_principles_md_ledger_rejected
PASS test_query_status.test_query_runs_batch_run_metric_since_filters
PASS test_query_status.test_query_runs_include_archive_reads_archive_file
PASS test_query_status.test_query_runs_requires_filter_and_all_rows_does_not_exempt
PASS test_query_status.test_query_story_default_active_all_rows_includes_retired
PASS test_query_status.test_render_blocked_groups_by_to_layer
PASS test_query_status.test_status_approved_specs_in_flight_and_open_issues
PASS test_query_status.test_status_four_breakpoints_land_correct_fields
PASS test_query_status.test_status_inconsistency_report_run_missing_other_fields_unaffected
PASS test_query_status.test_status_jobs_list_form_read_tolerantly
PASS test_query_status.test_status_repeat_query_is_byte_identical_and_writes_nothing
PASS test_query_status.test_status_unrecorded_runs_reads_across_archive
PASS test_query_status.test_status_waiting_on_action_matches_routes_to_column
-- run_all: 16 passed, 0 failed
```

全量回归（受影响文件所在的完整测试套件）：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 157 passed, 0 failed
```

`python3 run.py selfcheck` 仍未跑——本轮改动仍在工单范围声明排除的
`run.py`/`MAP.md` 之外，`git status --porcelain` 确认只动了
`statuscmd.py` 与 `test_query_status.py` 两个文件。

## commit 清单（修复轮）

- `635a028` T09: fix unrecorded_runs archive read, add jobs.json list-form test
  （`statuscmd.py` 一行读法改动 + `test_query_status.py` 两个新测试，一次提交——
  两条 finding 改动范围小且互不相关但都落在同一对文件上，拆开提交意义不大）

## 自查发现与存疑（修复轮）

- F1 的裁决边界按 finding 原文字面执行：只改 `unrecorded_runs`，
  `batches_pending_report`/`inconsistencies` 两处同样读 runs 账但工单没写
  「（跨档）」的地方保持原样未动——finding 本身的补充上下文也提到这条
  裁决不因为"三处一起改更一致"而扩大。
- 两处修复均未触及 `run.py`/`MAP.md`，工单范围声明维持有效，`selfcheck`
  门禁不适用。

## 修复第 1 轮 · 重复派发核验（2026-08-14）

收到与上一节完全相同的两条 finding（F1/F2），按派发消息协议准备
`git worktree add .../new1-wt/20260814-wave4-T09-fix1 ticket/20260814-wave4/T09`
时发现分支已不存在。核对结果：

- `git branch -a` / `git branch --contains 635a0289db217d1ad0f6e5e103f393a89f5ce7d2`：
  仓库里只剩 `main` 与 `ticket/20260814-wave4/T10` 两条分支，
  `ticket/20260814-wave4/T09` 已不在（`git reflog show` 该引用报
  "unknown revision"，即已被删除而非改名）。
- `git log --oneline --all --graph`：上一节记录的两个 commit
  （`6dac9c3` 初版、`635a028` 本 finding 的修复）已经出现在 `main` 上，
  经由 `6b86a44 research-loop: merge T09 (wave4)` 合并；`main` 之后又有
  `76decc2 research-loop: wave4 部分收账（T08/T09/T11 resolved；...）`
  把 T09 记成已结项。
- 三个 commit 的时间戳（`635a028` 04:32、`6b86a44` 04:51、`76decc2`
  04:52）都早于本次派发收到的时刻（04:53），且报告文件本身的 mtime
  （04:33）与 `635a028` 的作者时间几乎相邻——即上一节"修复第 1 轮"是另一个
  实现者会话刚做完、已经被主会话合并收账，本次派发是对同一批 finding 的
  重复调度，不是我漏做。
- 在 `main` 工作树（未建新 worktree、未建新分支，因为可挂的分支已不存在）
  里核对代码：`statuscmd.py` 里 `_unrecorded_runs` 已带
  `include_archive=True` 并附注释说明只改这一处的理由（对应 F1）；
  `test_query_status.py` 里
  `test_status_unrecorded_runs_reads_across_archive` 与
  `test_status_jobs_list_form_read_tolerantly` 两个测试都在（对应 F1/F2
  的回归覆盖）。逐字比对，与上一节描述的改法一致，未发现遗漏。
- 重跑测试确认现状：`test_query_status` 16/16 通过；全量回归
  `run_all.py`（当前 HEAD 已含 T08/T09/T11 三单）204/204 通过，见下节
  命令与输出。

**本轮未创建工作树、未创建分支、未产生新 commit**——两条 finding 在
`main` 当前状态下均已修复且已过全量回归，没有代码可改。按仓库铁律
"动手前先取得同意；一个请求只做那一件事"，在核验清楚"已经做完"之后不再
无意义地补一个空提交或重造分支。这条重复派发建议由主会话核对其
wave4 收账记录里 T09 的状态跟踪是否与实际提前完成的情况脱节。

### 怎么验证的（本轮核验）

```
$ python3 research-loop/tests/run_all.py test_query_status
PASS test_query_status.test_query_decisions_default_view_referenced_expired_grant_kept
PASS test_query_status.test_query_direct_ledger_rejected
PASS test_query_status.test_query_feedback_pending_excludes_reviewed_and_review_rows
PASS test_query_status.test_query_principles_md_ledger_rejected
PASS test_query_status.test_query_runs_batch_run_metric_since_filters
PASS test_query_status.test_query_runs_include_archive_reads_archive_file
PASS test_query_status.test_query_runs_requires_filter_and_all_rows_does_not_exempt
PASS test_query_status.test_query_story_default_active_all_rows_includes_retired
PASS test_query_status.test_render_blocked_groups_by_to_layer
PASS test_query_status.test_status_approved_specs_in_flight_and_open_issues
PASS test_query_status.test_status_four_breakpoints_land_correct_fields
PASS test_query_status.test_status_inconsistency_report_run_missing_other_fields_unaffected
PASS test_query_status.test_status_jobs_list_form_read_tolerantly
PASS test_query_status.test_status_repeat_query_is_byte_identical_and_writes_nothing
PASS test_query_status.test_status_unrecorded_runs_reads_across_archive
PASS test_query_status.test_status_waiting_on_action_matches_routes_to_column
-- run_all: 16 passed, 0 failed
```

全量回归（当前 `main` HEAD = `76decc2`，含 T08/T09/T11 三单落地后的完整
测试套件）：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 204 passed, 0 failed
```

### commit 清单（本轮核验）

无。未建工作树、未建分支、未产生新 commit——两条 finding 在派发到达前已
由上一节记录的 `635a028`（经 `6b86a44` 合入 `main`）修复完毕。

### 自查发现与存疑（本轮核验）

- 本轮返回状态按语义算 `DONE`（两条 finding 全部核实已修复、测试全绿），
  但不是我这次会话产出的修复——如实记在这里，避免报告显得像重复邀功。
- 建议主会话检查 wave4 workflow 里 T09 修复轮的完成回报路径是否存在
  竞态（上一轮实现者已完成并回报，但主会话可能仍按旧状态又发了一次
  这次的修复派发）；这不是本工单范围内能改的东西，只记录现象供参考。
