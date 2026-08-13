# T11 报告 —— trace_check.py（溯源检查 + 收官门禁）

工单：`.scratch/research-loop/issues/11-trace-check.md`
分支：`ticket/20260814-wave4/T11`
工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave4-T11`（收尾已 `git worktree remove`，分支保留）

## 一、做了什么（对照工单逐条要求）

新建两个文件，均在 `research-loop/` 内，plugin 件不改 `run.py`/`MAP.md`（已核对
diff 只有这两个文件）：

- `research-loop/scripts/trace_check.py`
- `research-loop/tests/test_trace_check.py`

`trace_check.py` 是独立脚本（不挂 `ledger.py` 分发表，和 `output_check.py`/
`error_classify.py` 同形，`plan.md` 目录树也把它列在 `ledger.py` 旁边而非
`ledger_cmds/` 下）。CLI：`trace_check.py [--project-root P] [--closeout
BATCH_ID]`，输出一行一发现 `<check>: <detail>`，末行汇总 `trace_check: <N>
errors, <M> warnings`，有 error（`severity=="error"`）退出 1。当前八条检查
产出的发现全是 error，`warnings` 恒为 0——CLI 契约本身要求汇总行同时报两个
数，代码按 severity 字段泛化实现（为将来可能出现的 warning 级发现留了口子），
不是只为了凑格式硬编两个数字。

八条检查一条一个函数（对应工单"检查清单"1-8）：

1. **`check_forward_chain`**——非 quick 发射单三查：`spec_ref` 用
   `_find_spec_file`（递归 specs 目录 `*.md`，字符串含 item_id 即命中，和
   T08 launch-order 写入侧同一存在性判法）；`issue_ref` 用
   `_find_issue_file`（`tables/ledgers.json` issues 账 default_path 是
   `.scratch/*/issues/`，是个 glob——`Config.ledger_path()` 会把 `*` 当字面
   路径段拼死，这里自己重新把 raw 值当 glob 解出来搜，不经过
   `Config.ledger_path`）；`decision_refs` 逐个查 decisions 账存在
   且 `status=="decided"`。`order.get("quick")` 为真整条跳过。
2. **`check_approval`**——`spec_ref` 非空的非 quick 单：找到 spec 文件后
   `parse_frontmatter` 取 `approved_by`/`approved_digest`；`approved_by`
   空报 `not-approved`；非空则 `_lib.spec_digest` 重算，不等报
   `approval_stale`。找不到 spec 文件时不重复报错（已经是
   `check_forward_chain` 的活）。
3. **`check_affects`**——正向：发射单每个 `decision_refs` 里的 D，其
   `affects` 不含该 run_id（用发射单文件名作 run_id，见下）报
   `affects-missing`，detail 里带 `re-run` + `launch-order` 字样的修复指引；
   反向：`decisions.affects` 里能对上一张现存发射单文件的 run_id，若该单
   `decision_refs` 不含这个 D，报 `affects-extra`。
4. **`check_runs_backlink`**——普通行：`runmeta_path` 文件存在 → 读
   `launch_order_ref` → 对应发射单存在 → 该发射单**自身 JSON 里的
   `run_id` 字段**等于行的 `run_id`（不是"文件名等于行 run_id"，那是
   trivial 的；这里查的是文件名和文件内容两者是否一致，专门覆盖"文件叫
   run-001.json 但内容里 run_id 写成别的"这种真错位，见下方"自查"）。同
   run_id 多个指标行按 `_run_level_fields` 只查一次（去重用
   `seen_normal_run_ids`），不会因为一个 run 挂三个指标就报三条一样的错。
   判据缩减行：`principle_id` 查原则文档（`ledger_cmds.principlescmd.
   parse_principles` 能导入就用它，导不进去（`ImportError`）落到脚本自带
   的同款解析——按工单原话实现了两条路径，不是只写了 try 但从没触发过；
   已经用 `builtins.__import__` 打桩强制走 `ImportError` 分支单独验证过，
   见下方"怎么验证的"）；查到principle 后拿 `criterion_cmd` 过
   `_lib.check_in_registry`，失败信息含 `"not wired"` 归为 `unwired`
   （覆盖 `registry_cmd`/`registry_query` 两种未接线），否则归
   `runs_backlink.criterion_cmd`；**不因为 `criterion_cmd` 是空串就跳过
   这一步**（想过跳过，见下方"自查"，最后决定按工单字面"criterion_cmd
   过 check_in_registry"不设这个例外）。
5. **`check_jobs_backlink`**——`ops/jobs.json` 兼容 `plan.md` §C5 说的
   两种形状（`{run_id: {...}}` 字典或 `[{run_id/name: ..., ...}]` 列表），
   逐条 `launch_order_ref` 查发射单是否存在。
6. **`check_story_refs`**——故事账 `status=="active"` 的每条，
   `evidence_runs`/`baseline_runs`/`candidate_runs` 三个列表的每个
   run_id：跨档（`include_archive=True`）查 runs 账存在、且该行
   `quick` 不为真。这条工单"检查清单"里写了但"测试"编号列表没单独点名，
   仍按"每条独立函数逐条实现"做了，也补了两个测试（见下）。
7. **`check_promotion`**——`promoted_from` 非空的发射单，跟来源单比对
   `seed`/`dataset_version`/`argv`/`env_name`/`filter` 五个字段，
   `!=` 逐个比，不等的字段名收进列表报 `promotion-field-drift`。来源单
   本身缺失不在这里报（工单原话："沿用字段一致性归 trace_check，写入侧
   不查"——存在性是 T08 写入侧的活）。
8. **`check_closeout`**——只在 `--closeout BATCH_ID` 传入时跑：批次报告
   先按 `<batch_reports目录>/<batch_id>.md` 找，找不到再扫全目录按
   frontmatter `batch_id` 字段配对；报告缺失报 `closeout.report_missing`；
   `inspection_report` 空串报 `closeout.inspection_report_empty`（平时不
   带 `--closeout` 完全不跑这条，验证见下）；`run_ids` 里任何一个不在
   runs 账报 `closeout.run_id_unrecorded`。八条常规检查照跑不受影响，
   全绿才 0。

`<check>` 具体取值：工单原文带反引号的四个字面量
（`approval_stale`/`affects-missing`/`affects-extra`/
`promotion-field-drift`）逐字照用；`unwired`/`not-approved` 工单原文写了
但没加反引号，按原文措辞实现（非强制字面量，但读起来是同一个意思）；
其余六种断链没有点名字面量，自定了 `forward_chain.spec_ref` /
`forward_chain.issue_ref` / `forward_chain.decision_ref` /
`runs_backlink.runmeta_missing` / `runs_backlink.launch_order_ref_missing`
/ `runs_backlink.run_id_mismatch` / `runs_backlink.principle_missing` /
`runs_backlink.criterion_cmd` / `jobs_backlink` / `story_refs` /
`closeout.report_missing` / `closeout.report_unreadable` /
`closeout.inspection_report_empty` / `closeout.run_id_unrecorded`。

## 二、怎么验证的

测试命令：`python3 research-loop/tests/run_all.py test_trace_check`

```
PASS test_trace_check.test_affects_extra_reported
PASS test_trace_check.test_affects_missing_reported_with_rerun_guidance
PASS test_trace_check.test_all_green_fixture_exits_zero_with_zero_errors
PASS test_trace_check.test_approval_empty_approved_by_reports_not_approved
PASS test_trace_check.test_approval_not_stale_on_withdrawals_or_spec_version_bump
PASS test_trace_check.test_approval_stale_on_body_punctuation_change
PASS test_trace_check.test_closeout_empty_inspection_report_rejected
PASS test_trace_check.test_closeout_filled_inspection_report_passes
PASS test_trace_check.test_closeout_missing_report_reported
PASS test_trace_check.test_closeout_run_id_not_recorded_reported
PASS test_trace_check.test_criterion_row_checks_principle_and_registry_not_spec_chain
PASS test_trace_check.test_criterion_row_principle_id_not_in_principles_doc_reported
PASS test_trace_check.test_criterion_row_registry_query_null_reports_unwired
PASS test_trace_check.test_cross_archive_referenced_run_only_in_archive_not_reported_broken
PASS test_trace_check.test_forward_chain_decision_ref_missing_reported
PASS test_trace_check.test_forward_chain_decision_ref_not_decided_reported
PASS test_trace_check.test_forward_chain_issue_ref_missing_reported
PASS test_trace_check.test_forward_chain_spec_ref_missing_reported
PASS test_trace_check.test_jobs_backlink_missing_reported
PASS test_trace_check.test_normal_mode_empty_inspection_report_not_reported
PASS test_trace_check.test_promotion_all_fields_match_is_clean
PASS test_trace_check.test_promotion_field_drift_names_seed
PASS test_trace_check.test_quick_launch_order_exempts_forward_chain_refs
PASS test_trace_check.test_runs_backlink_launch_order_ref_missing_reported
PASS test_trace_check.test_runs_backlink_run_id_mismatch_reported
PASS test_trace_check.test_runs_backlink_runmeta_path_missing_reported
PASS test_trace_check.test_story_refs_broken_run_reference_reported
PASS test_trace_check.test_story_refs_quick_run_reference_reported
-- run_all: 28 passed, 0 failed
```

全量跑一遍确认没破坏别人（`python3 research-loop/tests/run_all.py`）：

```
-- run_all: 169 passed, 0 failed
```

`ledger_cmds.principlescmd` 导不进去时走自带解析那条分支，单独用
`builtins.__import__` 打桩逼出 `ImportError` 手工验证过（不在
`run_all.py` 覆盖范围内，因为这条分支只在模块导入的那一刻二选一，正常
测试环境里 `ledger_cmds.principlescmd` 永远导得进去，走不到 fallback）：

```
fallback parse_principles: <function _parse_principles at 0x...>
[{'principle_id': 'P001', ..., 'criterion_cmd': 'python3 x.py check', ...}]
fallback OK
```

CLI 手工冒烟（`--project-root` 显式给一个没接线的空目录、以及不给
`--project-root` 时靠 cwd 找不到 `research-loop.json`）：

```
$ python3 trace_check.py --project-root /tmp/tc_smoke_empty
trace_check: 0 errors, 0 warnings
$ echo $?
0
$ cd /tmp/tc_smoke_empty && python3 .../trace_check.py
trace_check: project not wired: research-loop.json not found (run: ledger.py init)
$ echo $?
2
```

工单未点名要跑 `run.py selfcheck`（本工单没碰 `run.py` 注册表），没跑。

## 三、commit 清单

- `715496d` T11: trace_check.py -- traceability check + batch closeout gate
  （两个文件一次提交：脚本 + 测试，逻辑上是一件事，没有再拆）

## 四、自查发现与存疑

1. **发射单键改成"文件名作 run_id"而不是"文件内容里的 run_id 字段"**——
   `_load_launch_orders` 原本想法是 `{data["run_id"]: data}`，后来改成
   `{path.stem: data}`。理由：spec §5 原话"发射单按 run_id 命名"，文件名
   才是权威 key；如果用内容里的 `run_id` 字段当 key，"该发射单 run_id 与行
   run_id 一致"这条检查会变成永远真的套套逻辑（因为 dict 是用这个字段建的，
   查出来的 `order["run_id"]` 必然等于查询用的那个值）。改成按文件名建
   key 后，`check_runs_backlink` 里 `order.get("run_id") != run_id`
   才是一次真的交叉核对，`test_runs_backlink_run_id_mismatch_reported`
   专门测了这个场景（文件叫 `run-001.json`，内容里 `run_id` 却写
   `run-999`）。工单原文没有把这处实现选择挑明，是我按 §5 原话 + 测试点
   "runs 反链…该发射单 run_id 与行 run_id 一致" 反推出来的，写在这里供
   复核。
2. **判据缩减行 `criterion_cmd` 空串时没有跳过注册表检查**——想过给空串
   开个例外（【想法待定】原则允许 `criterion_cmd` 暂空，见 R1），但工单
   §4 原话是"principle_id 在原则文档里存在…+ criterion_cmd 过
   check_in_registry"，没写"cmd 非空时才查"这个条件；而且能走到这一步
   说明 runs.jsonl 里确实存在一条这个 principle 的已实测判据行——如果
   现在原则文档上的 `criterion_cmd` 是空的，那正是"记录过的实测和当前
   原则状态对不上"的真实漂移，值得报。所以最终没设这个跳过，测试没有
   专门覆盖这个空串子分支（工单测试列表也没点这条），如果后续认为该
   跳过，是这一处的实现选择，不是漏测。
3. **`check_in_registry` 失败信息按 `"not wired" in exc.message` 区分
   `unwired` 和 `runs_backlink.criterion_cmd`**——工单原文只点名了
   "registry_query null → 报 unwired"，没提 `registry_cmd` 为 null 的
   情形该归哪类。`_lib.check_in_registry` 两种未接线的报错文案都含
   "not wired"这个词，我把两种都算 `unwired`（都是"没接上"，不是"接上了
   但配置错了"），"task 不在注册表""argv 前缀不对"这类才归
   `runs_backlink.criterion_cmd`。只测了 `registry_query` 为 null 这一种
   （工单点名的那种），`registry_cmd` 为 null 那条支路没写测试。
4. **测试 fixture 里 `helpers.METHOD_MD` 默认 `criterion_cmd` 对不上
   `make_sandbox()` 生成的 `registry_cmd` 前缀**——这不是我这张工单引入
   的问题，T08 工单 Comments 已经记过同一件事（helpers 默认值本来就没打算
   对齐，靠各工单测试自己按实际 `registry_cmd` 改写）。我加了
   `_fix_method_criterion_cmd` 辅助函数，在三个真的要让 P001 的
   `criterion_cmd` 走通注册表检查的测试里调用，重写 METHOD.md 那一格；
   没改 `tests/helpers.py`（不在这张工单范围内，也怕影响别的工单测试）。
5. **`--project-root` 显式给一个未接线目录时不拦**——`_lib.load_config`
   本身在配置文件不存在时返回一个空 `Config`（不报错），我在
   `main()` 里也没另加"必须已接线"的门禁，只在**没给 `--project-root`
   且 `find_project_root()` 也找不到**时才报错退出 2。也就是说
   `trace_check.py --project-root /some/empty/dir` 会在零账本、零发射单
   的情况下汇报"0 errors, 0 warnings"退出 0，而不是报"未接线"。工单没写
   这处该怎么处理，我按其余独立脚本（`output_check.py`/
   `error_classify.py` 不做工程级 wiring 门禁，只处理自己直接给的路径）
   的宽松风格照做，行为已在报告里的"CLI 手工冒烟"贴出来，供复核。

## 五、修复第 1 轮（对付 finding F1）

分支上一轮提交后拿到一条 important 级 finding，编号 F1。这里先把
finding 指的问题讲清楚，再讲怎么改的，最后贴测试。

### F1 指出的问题

`check_forward_chain`（工单第 1 条，判发射单的 spec_ref 存不存在）和
`check_approval`（工单第 2 条，判 spec 批准面的 approved_by 和
approved_digest）共用同一个查找函数 `_find_spec_file`：这个函数只看
spec 目录下有没有一个 md 文件的正文含 item_id 这个字符串，不检查这个
文件带不带合法的 `---` frontmatter。两个函数因此在同一处失手：一个
spec 文件如果被人在正常写入流程之外改坏了 frontmatter（比如删掉了开头
的 `---` 那一行），`check_forward_chain` 照样判它“找到了”，不会报
`forward_chain.spec_ref`；`check_approval` 找到同一个文件之后去读
`approved_by` 和 `approved_digest`，这一步会因为解析不出 frontmatter
而抛 `_lib.RLError`，而上一轮的代码在这里写的是
`except _lib.RLError: continue`，直接跳过，不留任何 finding。链路走
完，`trace_check` 全程“0 errors, 0 warnings”，被改坏的 spec 文件全程
没被任何一条检查抓到。

finding 还指出一处文档不准：`_find_spec_file` 的 docstring 上一轮写的
是“同 T08 launch-order 写入侧对 spec_ref 用的存在性判法”，但 T08 工单
（`.scratch/research-loop/issues/08-launch-order.md` 第 39 行）写的判法
是“含该 item_id 字符串**且带 frontmatter**”，比 T11 自己检查 1 的原话
（工单第 27 行“字符串含 item_id”）多了“带 frontmatter”这个条件。
`_find_spec_file` 只实现了字符串这一半，docstring 却写成两边等价，这句
话本身是错的。

### 怎么改的

改动只落在 `check_approval` 一处行为，`check_forward_chain` 和
`_find_spec_file` 的判法没动——T11 检查 1 的原话就是“字符串含 item_id”，
没有“带 frontmatter”这个条件，所以查找逻辑本身不算错，错在
`check_approval` 拿到解析失败之后的处理方式，以及 docstring 那句话。

`research-loop/scripts/trace_check.py`：

- `check_approval` 里原来的 `except _lib.RLError: continue` 改成新增一条
  finding，check 取 `approval.spec_unreadable`，detail 里带上
  `exc.message`（也就是 `_lib.parse_frontmatter` 报的具体原因，例如
  “frontmatter must start with a '---' line”）。这样一来，`check 1`
  判“找到”和`check 2` 判“读不出批准信息”分工清楚：spec 文件被 T08
  正常写入过，两边都会顺利通过；spec 文件被写坏，`check 1` 因为判法本身
  就是字符串匹配所以不会报，`check 2` 会在这里报出来，不再是零 finding。
- `_find_spec_file` 的 docstring 改写，去掉“同 T08 存在性判法”这句不准
  的话，改成如实写清三件事：这里用的判法就是 T11 检查 1 自己的原话
  （字符串含 item_id）；这比 T08 写入侧的门禁（issues/08-launch-order.md
  第 39 行，字符串加 frontmatter 两个条件）松；这个函数找到的文件不保证
  一定能解析出 frontmatter，读不出来的情形归 `check_approval` 处理，不
  在这里假装“找到了就等于没问题”。
- 模块顶部的 checks 清单注释里，第 2 条 `check_approval` 的说明补上
  `approval.spec_unreadable` 这一种 finding，并写明这不是把责任推给
  `check_forward_chain`——`check_forward_chain` 的判法本来就不检查
  frontmatter，所以这条 finding 只能靠 `check_approval` 自己报。

`research-loop/tests/test_trace_check.py`：新增一条测试
`test_approval_malformed_spec_frontmatter_reported_not_silently_dropped`。
造一个 spec 文件，正文含 `IT-001`（`check_forward_chain` 的判法能找到），
但整个文件不带 `---` frontmatter；发射单非 quick、`spec_ref` 指向
`IT-001`。断言两件事：一，输出里没有任何一行以 `forward_chain.spec_ref:`
开头（`check_forward_chain` 按自己的判法正常判定“找到”，这不是回归）；
二，输出里有一行以 `approval.spec_unreadable:` 开头且带上 `run-001`
这个 run_id（`check_approval` 报出了这处损坏，不再是零 finding）。

### 测试

命令：`python3 research-loop/tests/run_all.py test_trace_check`

```
PASS test_trace_check.test_affects_extra_reported
PASS test_trace_check.test_affects_missing_reported_with_rerun_guidance
PASS test_trace_check.test_all_green_fixture_exits_zero_with_zero_errors
PASS test_trace_check.test_approval_empty_approved_by_reports_not_approved
PASS test_trace_check.test_approval_malformed_spec_frontmatter_reported_not_silently_dropped
PASS test_trace_check.test_approval_not_stale_on_withdrawals_or_spec_version_bump
PASS test_trace_check.test_approval_stale_on_body_punctuation_change
PASS test_trace_check.test_closeout_empty_inspection_report_rejected
PASS test_trace_check.test_closeout_filled_inspection_report_passes
PASS test_trace_check.test_closeout_missing_report_reported
PASS test_trace_check.test_closeout_run_id_not_recorded_reported
PASS test_trace_check.test_criterion_row_checks_principle_and_registry_not_spec_chain
PASS test_trace_check.test_criterion_row_principle_id_not_in_principles_doc_reported
PASS test_trace_check.test_criterion_row_registry_query_null_reports_unwired
PASS test_trace_check.test_cross_archive_referenced_run_only_in_archive_not_reported_broken
PASS test_trace_check.test_forward_chain_decision_ref_missing_reported
PASS test_trace_check.test_forward_chain_decision_ref_not_decided_reported
PASS test_trace_check.test_forward_chain_issue_ref_missing_reported
PASS test_trace_check.test_forward_chain_spec_ref_missing_reported
PASS test_trace_check.test_jobs_backlink_missing_reported
PASS test_trace_check.test_normal_mode_empty_inspection_report_not_reported
PASS test_trace_check.test_promotion_all_fields_match_is_clean
PASS test_trace_check.test_promotion_field_drift_names_seed
PASS test_trace_check.test_quick_launch_order_exempts_forward_chain_refs
PASS test_trace_check.test_runs_backlink_launch_order_ref_missing_reported
PASS test_trace_check.test_runs_backlink_run_id_mismatch_reported
PASS test_trace_check.test_runs_backlink_runmeta_path_missing_reported
PASS test_trace_check.test_story_refs_broken_run_reference_reported
PASS test_trace_check.test_story_refs_quick_run_reference_reported
-- run_all: 29 passed, 0 failed
```

比上一轮多出的那一条就是本轮新增的
`test_approval_malformed_spec_frontmatter_reported_not_silently_dropped`，
其余 28 条和上一轮完全相同（对照上面“二、怎么验证的”那一节的清单，
名字逐条一致），没有一条因为这次改动而变了断言或者被删掉。

全量重跑确认没有影响别的工单（`python3 research-loop/tests/run_all.py`）：

```
-- run_all: 170 passed, 0 failed
```

上一轮的全量数字是 169，这一轮多出的 1 条就是新增的测试。

### commit 清单

- `c6cc2d2` T11: fix silent-drop gap in check_approval on malformed spec
  frontmatter

### 存疑

`approval.spec_unreadable` 是这一轮新起的 finding 字面量，工单原文没有
点名。上一轮报告“二、怎么验证的”上方列出的一批自定字面量
（`forward_chain.spec_ref` 等）都是工单没点名、按同一套命名习惯自定的，
这一条延续的是同一个习惯（`check_closeout` 已经有一个同构的
`closeout.report_unreadable`，两边都是“这条账目本身能不能解析”这一类
问题，命名对齐着写），不是这一轮单独引入的新命名方式，留在这里供复核。

## 六、修复第 2 轮（对付 finding F2、F3）——分支已被合并进 main 之后的接手

### 接手时发现的分支状态

这一轮派发消息给的工作树协议是"检出已有分支 `ticket/20260814-wave4/T11`"，
但接手时这条分支在仓库里已经不存在了。查 `main` 的历史发现：`c6cc2d2`（上一
轮 F1 修复的提交）已经通过一个真正的 merge commit `df6ea74`（"research-loop:
merge T11 (wave4)"）进了 `main`，紧接着 `76decc2`（"research-loop: wave4
部分收账（T08/T09/T11 resolved...）"）把工单 11 标成 resolved 并往
`.scratch/research-loop/issues/11-trace-check.md` 的 Comments 追加了一条
"DONE，1 轮 0 修复...merge 进 main"。也就是说，这次派来的三条 finding
（F1/F2/F3）所依据的复审，跑在 `963bdaaf..715496d` 这个只到初次实现、还没
应用 F1 修复的 diff 区间上；但在这条复审跑完、finding 派发下来之前，分支已
经先经过 F1 修复（`c6cc2d2`）、合并、收账走完了一整圈，原分支也按合并后惯例
删掉了。F1 finding 本身的文字里也点出了这处时间差（"that commit falls
OUTSIDE the diff range given for this review"），所以这不是我这一轮才发现的
新问题，是复审依据的版本和分支实际进度已经错开了一步。

处理方式：`git worktree add -b ticket/20260814-wave4/T11
<工作树路径> c6cc2d2` —— 用同一个分支名，从原分支被删前的最后一个提交
（`c6cc2d2`，与 `main` 上合并进来的那份代码逐字节相同，已用 `git show df6ea74
--stat` 核对只有两个文件、行数与新建文件一致）重新建出这条分支，而不是另起
一个新分支名。理由：实现者规程"修复轮是检出已有分支，不另建分支"这条的本意
是不要在同一张工单上分叉出第二条历史；分支被删是收账流程的正常清理动作，不
是这条分支不该存在——用同一个名字、同一个提交重建，是在"分支已被删"这个既
成事实下最贴近原意的做法。

**这处分支状态不一致留给主会话核实**：`main` 上 T11 已经被标成 resolved 并
合并，工单文件 Comments 里写的是"1 轮 0 修复"；这一轮修复完成后，`main`
上的代码仍然缺 F2、F3 两处改动（这两处改动此刻只存在于重建出的
`ticket/20260814-wave4/T11` 分支上，还没有第二次合并进 `main`）。这条分支
要不要、以及怎么再合一次进 `main`，工单 Comments 那句"merge 进 main"要不要
连带更新，是收账层面的判断，我在实现者角色上不擅自做——第一，那不是这张工单
"范围声明"里的事；第二，工单收官记录（issues 文件的 Comments 行）按仓规是
人工/主会话维护的账，不是实现者能单方面改的。

### F2 指出的问题

`trace_check.py` 里有三处直接 `json.loads(...)`，没有任何异常处理：
`_load_launch_orders` 读 `ops/launch_orders/*.json` 逐个文件、`_load_jobs`
读 `ops/jobs.json`、`check_runs_backlink` 里读 RUNMETA 文件。这三个文件都
不是靠事务写入保证原子性的普通文件（`issues/08-launch-order.md` 第 233
行点过 `launchcmd.py` 用的是一个普通、非原子的 `Path.write_text`），如果
其中任何一个在读的那一刻是半写状态或者被外部改坏，`json.loads` 会抛
`json.JSONDecodeError`，`main()` 里只兜了 `except _lib.RLError`，接不住这
个异常，整个 `trace_check` 进程直接带着一截 Python 原始 traceback 崩掉——
不打印任何一条 finding，后面排在它之后的每一条检查都不会跑到。这和这个脚本
本身的定位（专门抓账本损坏）正好相反：账本损坏的其中一种形式（JSON 语法
错误）反而能让抓损坏的工具自己先倒下。

我先复现了一遍崩溃的原样（改动前的代码，`git stash` 挡开这一轮的改动后
手工构造一个坏掉的发射单文件跑一遍），确认了 finding 描述的现象：

```
$ python3 -c "... helpers.make_sandbox + 写一个内容是 '{not valid json' 的
  ops/launch_orders/run-bad.json，然后 helpers.run_script(root, 'trace_check.py') ..."
code: 1
stdout: (空)
stderr has Traceback: True
...
json.decoder.JSONDecodeError: Expecting property name enclosed in double
quotes: line 1 column 2 (char 1)
```

`code == 1` 只是 Python 未捕获异常时解释器给的默认退出码，跟"发现了 1 个
error"这个 `trace_check` 自己的退出码语义完全是两回事——`stdout` 是空的，
一条 finding 都没打印出来，`stderr` 上是原始 traceback，不是一行干净的
`load.*: ...` 提示。

### 怎么改的

`research-loop/scripts/trace_check.py`：

- `_load_launch_orders(cfg)`：改成逐个发射单文件 `try/except (OSError,
  json.JSONDecodeError)`，解析失败的文件不写进返回的 `orders` 字典（这样
  它不会被任何检查误当成"存在且没问题"），改成往新增的第二个返回值
  `findings` 里追加一条 `load.launch_order_unreadable`。函数签名从
  `-> dict` 改成 `-> tuple`（`(orders, findings)`），docstring 同步改写。
- `_load_jobs(cfg)`：同样的 `try/except`，读 `ops/jobs.json` 那一步失败时
  直接返回 `([], [一条 load.jobs_unreadable finding])`。函数签名同样改成
  `-> tuple`。
- `_Context.__init__`：新增 `self.load_findings = []`，`_load_launch_orders`
  / `_load_jobs` 现在各自吐出的 findings 都并进这个列表里；`self.launch_orders`
  / `self.jobs` 的赋值改成拆包这两个函数新的二元组返回值，`_Context`
  其余字段（`decisions_rows`、`runs_rows`、`story_rows`、
  `principles_rows`/`principles_by_id`）没有动。
- `check_runs_backlink`：原来那行裸的
  `runmeta = json.loads(runmeta_path.read_text(...))` 包进
  `try/except (OSError, json.JSONDecodeError)`，失败时追加一条
  `runs_backlink.runmeta_unreadable`（带上 `run_id` 和
  `runmeta_path_str`，跟这个函数里紧挨着的另外两种 finding
  ——`runmeta_missing`、`launch_order_ref_missing`——同一个前缀、同一种
  措辞风格）然后 `continue`，不往下走。这一处不需要改函数签名，因为
  `check_runs_backlink` 本来就在往一个局部 `findings` 列表里追加，直接
  在原地加一个 `try/except` 分支就行。
- `run(root, closeout_batch_id)`：`findings = []` 改成
  `findings = list(ctx.load_findings)`，把加载阶段收集到的 findings
  垫在最前面，后面 `_REGULAR_CHECKS` 和（`--closeout` 模式下）
  `check_closeout` 产出的 findings 照旧 `extend` 上去。这样一来
  `--closeout` 模式（工单第 8 条"以上全部常规检查全绿才 exit 0"）也
  自动覆盖了加载阶段的损坏——不用在 `check_closeout` 那条单独再判一遍。
- 模块顶部 docstring：第 4 条检查说明补一句"RUNMETA 解析失败报
  `runs_backlink.runmeta_unreadable`"；在检查清单和 `Output` 之间加一段
  新段落，说明加载阶段本身也是"只读、也可能失败"的，失败报
  `load.launch_order_unreadable` / `load.jobs_unreadable`，不是崩溃也不是
  假装没事。

`research-loop/tests/test_trace_check.py`：新增一个不对应任何单一检查号的
分区"0. Loading resilience（fix round 1, F2）+ ImportError fallback（F3）"，
放在原有的"1. Broken-chain findings"分区之前（呼应脚本正文里"Loading"
先于"1. 正链检查"的顺序）：

- `test_load_malformed_launch_order_json_reported_not_crashed`——写一个
  内容是 `"{not valid json"` 的 `ops/launch_orders/run-bad.json`，断言
  退出码 1、有一行 `load.launch_order_unreadable:` 带上文件名、`stderr`
  里没有 `"Traceback"` 字样、汇总行精确是
  `trace_check: 1 errors, 0 warnings`（沙箱里没有别的账目，这一个坏文件
  应该是唯一一条 finding）。
- `test_load_malformed_jobs_json_reported_not_crashed`——同样手法坏一个
  `ops/jobs.json`，断言 `load.jobs_unreadable:`、无 traceback、汇总行
  精确 1 条 error。
- `test_runs_backlink_runmeta_unreadable_reported_not_crashed`——起手式
  仿照已有的 `test_runs_backlink_runmeta_path_missing_reported`（同一个
  检查函数里紧挨着的另一种断链），只是这次文件是"存在但内容不是合法
  JSON"而不是"不存在"，断言 `runs_backlink.runmeta_unreadable:` 带
  `run-001`、无 traceback。

### F3 指出的问题

`trace_check.py` 顶部 `except ImportError:` 分支（复刻
`ledger_cmds.principlescmd.parse_principles` 的一份约 40 行的备份实现，
只有当 `ledger_cmds` 不在 `sys.path` 上——比如某种裁剪过的部署——时才会
走到）在这一份代码里标了 `# pragma: no cover`，而且 `test_trace_check.py`
现有的 28 条测试没有一条真正碰过这条分支（`helpers.run_script` 是拿
`subprocess.run` 起一个全新的 Python 进程去跑 `trace_check.py`，那个子
进程里 `ledger_cmds.principlescmd` 永远导得进去，主路径永远赢，`except`
分支永远不会被执行到）。上一轮报告写的"单独用 `builtins.__import__`
打桩逼出 `ImportError` 手工验证过"这句话，没有配一条可以照着重新跑一遍
的命令，只有一段带省略号地址（`0x...`）的控制台片段，读起来更像手打的
示意而不是原样粘贴的终端输出，没法拿它独立复核。

### 怎么改的

`research-loop/tests/test_trace_check.py`：新增
`test_import_error_fallback_parses_principles_same_as_primary`（在同一个
"0."分区里）。做法和上一轮报告描述的手工验证是同一套技术，只是这次写成了
一条能重复跑、能通过/失败判定的自动化测试，而不是一次性手工操作：

1. 先用真正的 `ledger_cmds.principlescmd.parse_principles` 解析
   `helpers.make_sandbox()` 落的那份 `METHOD.md`（`helpers.METHOD_MD`
   常量，两条 principle 行），存成 `expected`，并断言它非空（防止这条
   测试因为拿到空列表两边都是 `[]` 而"意外"通过）。
2. 把 `builtins.__import__` 换成一个包装函数：凡是被导入的模块名严格等于
   `"ledger_cmds.principlescmd"` 就直接抛 `ImportError`，其余一律照转发
   给原始 `__import__`（这一步先在仓库外单独用一段脚本核实过——见下方
   "验证接口拦截技术本身"——确认 `from ledger_cmds.principlescmd import
   parse_principles` 这句话在 CPython 里真的是拿这个完整点号路径去调
   `__import__` 的，不是拿 `"ledger_cmds"` 去调）。
3. `importlib.reload(trace_check)`——因为 `builtins.__import__`
   已经被换成会报错的那个，`trace_check.py` 顶部
   `try: from ledger_cmds.principlescmd import ... except ImportError:`
   这次真的会走进 `except` 分支，把模块级的 `_parse_principles`
   （连同 `_split_row`、`_find_header`）重新定义成本地那份备份实现。
4. 用重新绑定过的 `trace_check._parse_principles(method_path)` 解析
   同一份 `METHOD.md`，和第 1 步的 `expected` 逐字段比对（`==`
   比较两个 list-of-dict，不是只看"没抛异常"）。
5. `finally` 里把 `builtins.__import__` 换回原始函数、再
   `importlib.reload(trace_check)` 一次，让模块级 `_parse_principles`
   重新绑回真正的 `ledger_cmds.principlescmd.parse_principles`——测试
   最后再断言一次 `trace_check._parse_principles is _real_parse_principles`
   （`is`，同一个函数对象，不是"看起来一样"），确认这套"拦截-重载-复原"
   的操作没有在进程里留下任何影响后续测试的残余状态（`run_all.py`
   把所有 `test_*.py` 放在同一个进程里顺序跑，这一条如果收不干净会连累
   后面任何测试）。

`research-loop/scripts/trace_check.py`：`except ImportError:` 那行原来的
`# pragma: no cover -- exercised only in a stripped deployment` 改成一段
说明这条分支现在有
`test_trace_check.py::test_import_error_fallback_parses_principles_same_as_primary`
覆盖，不是只手工验证过；去掉了不再准确的 `pragma: no cover` 字面量（这条
分支现在确实被一条自动化测试执行到了，即使默认的
`python3 trace_check.py` 调用路径本身还是走不到它）。

### 验证接口拦截技术本身（写测试之前先核实的一步）

写正式测试之前，先在这个工作树的仓库根用一段独立脚本核实了
`builtins.__import__` 拦截 + `importlib.reload` 这套手法确实按预期工作
（不是只信"应该会这样"）：

```
$ python3 -c "
import sys
sys.path.insert(0, 'tests'); sys.path.insert(0, 'scripts')
import builtins, importlib
import trace_check
real_import = builtins.__import__
calls = []
def blocking(name, *a, **k):
    calls.append(name)
    if name == 'ledger_cmds.principlescmd':
        raise ImportError('blocked')
    return real_import(name, *a, **k)
builtins.__import__ = blocking
try:
    importlib.reload(trace_check)
    print('has _split_row after reload:', hasattr(trace_check, '_split_row'))
    print('_parse_principles module:', trace_check._parse_principles.__module__)
finally:
    builtins.__import__ = real_import
    importlib.reload(trace_check)
print('calls seen (dedup):', sorted(set(calls)))
print('primary restored, module:', trace_check._parse_principles.__module__)
"
has _split_row after reload: True
_parse_principles module: trace_check
calls seen (dedup): ['__future__', '_io', '_lib', 'argparse', 'json', 'ledger_cmds.principlescmd', 'pathlib', 're', 'sys']
primary restored, module: ledger_cmds.principlescmd
```

`_parse_principles module: trace_check` 证实了拦截生效后 `_parse_principles`
确实重新绑到了 `trace_check.py` 里本地定义的那份备份函数（模块名是
`trace_check`，不是 `ledger_cmds.principlescmd`）；`calls seen` 里能看到
`__import__` 真的是被拿 `'ledger_cmds.principlescmd'` 这个完整名字调用的；
复原之后 `module` 变回 `ledger_cmds.principlescmd`，确认 `finally` 里的
复原步骤有效。

### 测试

命令：`python3 research-loop/tests/run_all.py test_trace_check`

```
PASS test_trace_check.test_affects_extra_reported
PASS test_trace_check.test_affects_missing_reported_with_rerun_guidance
PASS test_trace_check.test_all_green_fixture_exits_zero_with_zero_errors
PASS test_trace_check.test_approval_empty_approved_by_reports_not_approved
PASS test_trace_check.test_approval_malformed_spec_frontmatter_reported_not_silently_dropped
PASS test_trace_check.test_approval_not_stale_on_withdrawals_or_spec_version_bump
PASS test_trace_check.test_approval_stale_on_body_punctuation_change
PASS test_trace_check.test_closeout_empty_inspection_report_rejected
PASS test_trace_check.test_closeout_filled_inspection_report_passes
PASS test_trace_check.test_closeout_missing_report_reported
PASS test_trace_check.test_closeout_run_id_not_recorded_reported
PASS test_trace_check.test_criterion_row_checks_principle_and_registry_not_spec_chain
PASS test_trace_check.test_criterion_row_principle_id_not_in_principles_doc_reported
PASS test_trace_check.test_criterion_row_registry_query_null_reports_unwired
PASS test_trace_check.test_cross_archive_referenced_run_only_in_archive_not_reported_broken
PASS test_trace_check.test_forward_chain_decision_ref_missing_reported
PASS test_trace_check.test_forward_chain_decision_ref_not_decided_reported
PASS test_trace_check.test_forward_chain_issue_ref_missing_reported
PASS test_trace_check.test_forward_chain_spec_ref_missing_reported
PASS test_trace_check.test_import_error_fallback_parses_principles_same_as_primary
PASS test_trace_check.test_jobs_backlink_missing_reported
PASS test_trace_check.test_load_malformed_jobs_json_reported_not_crashed
PASS test_trace_check.test_load_malformed_launch_order_json_reported_not_crashed
PASS test_trace_check.test_normal_mode_empty_inspection_report_not_reported
PASS test_trace_check.test_promotion_all_fields_match_is_clean
PASS test_trace_check.test_promotion_field_drift_names_seed
PASS test_trace_check.test_quick_launch_order_exempts_forward_chain_refs
PASS test_trace_check.test_runs_backlink_launch_order_ref_missing_reported
PASS test_trace_check.test_runs_backlink_run_id_mismatch_reported
PASS test_trace_check.test_runs_backlink_runmeta_path_missing_reported
PASS test_trace_check.test_runs_backlink_runmeta_unreadable_reported_not_crashed
PASS test_trace_check.test_story_refs_broken_run_reference_reported
PASS test_trace_check.test_story_refs_quick_run_reference_reported
-- run_all: 33 passed, 0 failed
```

比上一轮多出的 4 条就是这一轮新增的（3 条 F2、1 条 F3），其余 29 条
（上一轮那 28 条加上 F1 修复时新增的那 1 条）名字逐条一致，没有一条因为
这次改动变了断言或者被删掉。

全量重跑确认没有影响别的工单（`python3 research-loop/tests/run_all.py`）：

```
-- run_all: 174 passed, 0 failed
```

上一轮的全量数字是 170，这一轮多出的 4 条就是新增的测试，别的工单一条
没变。

这一轮没碰 `run.py` 注册表（这张工单本来就不挂注册表），没跑
`run.py selfcheck`。

### commit 清单

- `81be3bc` T11: fix F2 (unguarded json.loads crashes) + F3 (untested
  ImportError fallback)（两条 finding 的改动放在同一个提交里——F2
  改的三处加载函数、F3 改的测试分区导言注释和新增测试，在
  `test_trace_check.py` 里物理上挨在一起，拆成两个提交需要手工切
  hunk，权衡后按"这一轮修复"当一个逻辑单元一次提交，commit message
  里分别说清楚各自对应哪条 finding、各自怎么改的）

### 存疑

1. **分支重建与 `main` 侧收账状态不一致**——已在本节最前面"接手时发现
   的分支状态"整段说清楚，这里不重复；核心一句话：`main` 已经把 T11
   标成 resolved 并合并了 F1 的修复，这一轮的 F2/F3 修复目前只在重建出
   的 `ticket/20260814-wave4/T11` 分支上，还没有第二次合并，工单
   Comments 也还没更新反映这一轮。
2. **`_lib.jsonl_rows`（进而 `_read_jsonl_file`）内部同样有一处不带
   `try/except` 的 `json.loads(line)`**（解析 `decisions.jsonl` /
   `runs.jsonl` / `story.jsonl` 等每一行）——读代码时注意到这一处和 F2
   点名的三处是同一类问题，但它在 `research-loop/scripts/_lib.py`
   里，是很多张工单共用的库函数，不是 T11 自己的文件，F2 原文也没有
   点这一处。按"逐条修掉，不许扩大范围重构"没有动它，留在这里供复核，
   要不要另开工单是收账层面的判断。
