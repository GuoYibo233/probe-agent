# T16 报告 — 九场景假铁轨自测

工单：`.scratch/research-loop/issues/16-e2e.md`
分支：`ticket/20260814-wave5/T16`
base：`882dd1dd9f3d71ef2286e994fb1ba2e8763a2a8b`
head：`1dd7caa`（工作树已删除，分支保留）

## 一、做了什么（对照工单逐条）

### 文件

- Create `research-loop/tests/test_e2e.py`：九个 `test_<N>_...` 函数，序号与
  spec.md §9 逐条对应（①正轨闭环 … ⑨新会话接手），全部走真实的
  `scripts/fallback/{launch,record,registry}.py` + `fake_experiment.py` /
  `fake_metrics.py`，不 mock 插件自身脚本。
- Modify `research-loop/tests/helpers.py`：新增 `make_rails_sandbox(tmp)`——
  在 `make_git_sandbox` 基础上把 `registry_cmd`/`registry_query`/
  `record_cmd` 指向真实 fallback 三件（不是 `make_sandbox()` 自带的
  `stub_registry.py`——`fake-experiment`/`fake-metrics` 只在 fallback 里注册）、
  `rails.gpu` 指向 `fallback/launch.py` 的命令形态、写一份已批准的
  demo spec（含条目 IT-001）+ 一张 demo 工单 + 一条 decided 的 D001，
  `ops/` 整目录 gitignore（沿用 `test_fallback.py` 的既有约定，脏树门禁
  才能在每个场景自己往 `ops/` 写东西之后仍然过），全部 commit。

### 九场景实现要点

1. **正轨闭环**：`mk_order` 写正轨单（spec_ref=IT-001、issue_ref=01-demo、
   decision_refs=[D001]）→ `launch.py`（ok）→ `output_check.py` verdict=ok →
   `record.py` 落两行（acc/rows）→ 写 `plans/<batch>.md`（frontmatter 齐、
   `inspection_report` 先空）→ 写 `reports/inspection-<batch>.md`
   （verdict: clean；正文风格上符合 evidence_lint 的两条规则——不闻其详见
   下方"存疑"第 1 条）→ 报告头回填 `inspection_report` → `story add` →
   `trace_check --closeout <batch>`。
2. **快车道**：`quick=true` 单三 refs 空 → launch → record → runs 行
   `quick=true`；`story add` 引用它验证被拒（"quick runs cannot enter the
   story ledger"）；`trace_check`（无 closeout）验证不因缺 spec_ref/
   issue_ref 报 `forward_chain`。
3. **转正重跑**：先造一张 quick 单跑完，再以它为模板造正轨单
   （`promoted_from`=quick run_id，seed/dataset_version/argv/env_name/
   filter 逐字沿用——包括 argv 里的 `--out` 仍指向 quick 单的旧
   `artifact_dir`，新 run 的产物目录靠发射单自己的 `artifact_dir` 字段
   区分，工单原文这句"argv 里 --out 也保持逐字"就是这个意思）→ launch →
   record → `story add` 放行（非 quick）→ 断言两条 runs 行的 acc 值
   逐字相同（因为 result.jsonl 字节相同，`fake_metrics.py` 是纯字节哈希
   派生）。
4. **empty 模式**：`--mode empty` → launch exit 0 → `output_check.py`
   verdict=empty-output → `record.py --status empty-output` → runs 行
   status=empty-output 且 metric_name/value/n 全 null。
5. **bad-metrics**：`--mode bad-metrics` → launch ok → `record.py` exit 2、
   无新行 → 按 R8 开 `blocked open --kind failure`，`--evidence` 传
   attempt1.log 路径 + `"tried: reran record once"` 两项 → 断言新增
   一条 kind=failure 且 evidence 含日志路径。
6. **fail 后重试 ok**：`--mode fail` → launch exit≠0（attempt 1，log 含
   "simulated failure"）→ 用 `mk_order` 同 run_id 重写发射单（`--mode` 改
   ok，验证同路径幂等：两次 `mk_order` 返回同一个路径）→ launch（attempt
   2 ok）→ record → 断言该 run_id 恰一组两行且 status=ok；RUNMETA
   attempts 两条俱在、第一条 argv 仍含 "fail"、attempt1.log 内容未被
   attempt 2 覆盖。
7. **批准失效**：给已批准的 demo spec 正文追加一个字符 → 手工造一张正轨单
   draft（不走 `mk_order`，因为这是负例）→ `launch-order` 断言 exit 2 且
   报 `approval_stale`。
8. **三类半状态收敛**（fixture 定义取自 issues/14-doctor.md 工单原文，
   doctor.py 本身不在 T16 依赖清单里，未调用）——三个子测试
   `test_8a`/`test_8b`/`test_8c`，每个都并排造一个"干净一次执行"
   （golden）与一个"裸写出半状态再重跑原命令"（broken）的独立沙盒，
   逐字段比对两边收敛后的结果：
   - 8a 孤儿 decision：裸写一条 `decided` 且 `blocked_ref` 回指的
     decisions 行，对应 blocked 行仍 `open` → 重跑 `blocked answer`
     （撞上 blockedcmd.py 自带的幂等去重逻辑）→ 收敛到与 golden 相同的
     行数、`decision_ref`/`blocked_ref` 互指关系、`chosen` 值。
   - 8b 撤销中断：裸写 blocked 行已经 `status=withdrawn`（答复文本已带
     `[withdrawn by user: ...]` 附注），但同步 decision 仍 `decided`、
     且缺 `(ref=BID, status=open)` 重开条（工单原文两个 OR 条件在这一份
     fixture 上同时成立）→ 重跑 `blocked withdraw` → 收敛到与 golden
     相同的行数、decision 状态、重开条存在性。
   - 8c affects 缺失：裸写发射单直接落到 `ops/launch_orders/` 正规路径
     （不经 `ledger.py launch-order`），`decision_refs=[D001]` 但
     D001.affects 未回填 → 重跑 `launch-order --file <该单自己的路径>`
     → 断言 affects 精确回填成 `[run_id]` 一项，与 golden 一致。
9. **新会话接手**：复用场景④的沙盒构造（`_build_scenario4_sandbox`），
   只跑 `ledger.py status --layer deploy`，断言输出能 `json.loads`、
   `status_view` 全部字段名都在，且 `batches_pending_report` 或
   `unrecorded_runs` 非空（工单原文允许二选一）。

### 未做 / 有意跳过的部分

- `evidence_lint.py`（T13）不存在于本分支所依赖的基线（Blocked by 只到
  12，不含 13），场景①没有实际调用它，只是把 `reports/inspection-*.md`
  写成它两条规则会认可的样子（正文不含判断词、唯一数字声明后三行内跟一条
  `$ wc -l ...` / `= N ...`）。这条属于描述性符合，不是机验通过。
- `doctor.py`（T14）同理不存在，场景⑧的三类 fixture 定义抄自
  issues/14-doctor.md 工单原文，但恢复动作走的是 `ledger.py blocked
  answer/withdraw`、`ledger.py launch-order` 本身，不经 doctor。

## 二、怎么验证的

```
$ python3 research-loop/tests/run_all.py test_e2e
...
FAIL test_e2e.test_1_clean_loop_reaches_closeout
FAIL test_e2e.test_2_quick_lane_skips_refs_and_blocks_story
PASS test_e2e.test_3_promote_quick_to_full_reruns_byte_identical_argv
PASS test_e2e.test_4_empty_mode_records_null_metrics
PASS test_e2e.test_5_bad_metrics_opens_blocked_with_evidence
PASS test_e2e.test_6_fail_then_retry_ok_preserves_first_attempt
PASS test_e2e.test_7_approval_invalidated_by_body_edit_rejects_new_order
PASS test_e2e.test_8a_orphan_decision_converges_on_reanswer
PASS test_e2e.test_8b_withdraw_interrupted_converges_on_rewithdraw
PASS test_e2e.test_8c_affects_missing_converges_on_launch_order_rewrite
PASS test_e2e.test_9_new_session_status_reflects_disk_truth_alone
-- run_all: 9 passed, 2 failed
```

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 230 passed, 2 failed
```

基线（改动前，只跑既有测试）是 221 passed / 0 failed；230 = 221 + 11
（本工单新增的 11 个 test 函数：9 个场景，其中⑧拆成 3 个）；失败数恰好
是新增里那 2 个（test_1、test_2），没有波及任何既有测试——"全量
run_all.py 不破坏既有测试"这条验收线过了。test_e2e 自身"全过"这条验收线
**没有**过，原因见下方第三节，是本工单文件范围之外的依赖缺陷，不是
test_e2e.py 自己写错。

`python3 -c "import ast; ast.parse(...)"` 确认 test_e2e.py 语法整洁；未改
`run.py` 注册表，未跑 `run.py selfcheck`（工单范围本就声明"不改 run.py /
MAP.md"）。

## 三、发现的一处跨工单缺陷（阻塞场景①②的 exit 0，未在本分支修）

**现象**：任何一次真实跑通 `fallback/launch.py` 之后再跑 `trace_check.py`，
都会报出两条与被测场景本身无关的错误：

```
runs_backlink.launch_order_ref_missing: runs row <run_id>: RUNMETA.launch_order_ref
  '<绝对路径>/ops/launch_orders/<run_id>.json' does not point to an existing launch order
jobs_backlink: jobs entry '<run_id>': launch_order_ref '<同一绝对路径>' does not point
  to an existing launch order
```

**根因**：`scripts/fallback/launch.py`（T10）把 RUNMETA.json 和
`ops/jobs.json` 里的 `launch_order_ref` 都设成
`str(args.launch_order)`——调用方传给它的原始 CLI 路径字符串（可以是
绝对路径，也可以是相对路径，视调用方而定，但无论哪种都带目录和 `.json`
后缀）。而 `trace_check.py`（T11）的 `_load_launch_orders()` 把
`ops/launch_orders/*.json` 按**文件名去掉后缀的 stem**（即裸 run_id）建
索引，`check_runs_backlink`/`check_jobs_backlink` 都拿 `launch_order_ref`
去查这份以 stem 为键的字典——只要 `launch_order_ref` 带目录或后缀，这个
查找必然落空。`_load_launch_orders()` 自己的 docstring 也明确写了
"filename stem is the canonical run_id ... it is the key used everywhere
else in this script"，`launchcmd.py` 的 `promoted_from` 解析、
`decisions.affects` 也都是拿裸 run_id 当键——`launch.py` 是这条约定里的
唯一例外。

**复现**（在本工单的沙盒基础设施上，未改任何生产代码）：

```
launch-order 0
launch 0
record 0
trace_check 1
runs_backlink.launch_order_ref_missing: runs row run-check: RUNMETA.launch_order_ref
  '/tmp/tmp897kz1tp/ops/launch_orders/run-check.json' does not point to an existing launch order
jobs_backlink: jobs entry 'run-check': launch_order_ref '/tmp/tmp897kz1tp/ops/launch_orders/run-check.json'
  does not point to an existing launch order
trace_check: 2 errors, 0 warnings
```

**影响范围核实过**：只影响"跑完整条真实链路后要求 `trace_check` 全绿"的
场景，即①（`--closeout` 要求 exit 0）和②（要求 exit 0）。其余七个场景
要么不调用 `trace_check`（③④⑤⑥⑦⑨），要么⑧的三个恢复动作走的是
`blocked answer/withdraw`、`launch-order` 本身而不是 `trace_check`，都不
受这条缺陷影响，逐一实测确认过。

**建议修法**（未在本分支落地）：`launch.py` 把
`launch_order_ref = str(args.launch_order)` 改成
`launch_order_ref = order["run_id"]`（一处赋值，RUNMETA 和 jobs.json 两个
消费点共用同一个变量，一次改完）。但这样改会让
`test_fallback.py` 里现成的两条断言
（`entry["launch_order_ref"] == str(order_path)` /
`runmeta["launch_order_ref"] == str(order_path)`，都在
`test_launch_ok_writes_runmeta_and_marks_jobs_done` 里）失真，需要同步
改成 `== order["run_id"]`——`launch.py` 和 `test_fallback.py` 都是 T10 的
文件，不在本工单"Create test_e2e.py / Modify（如需）helpers.py"的声明
范围内，也是别的工单已经合并过的产物，所以没有在本分支动它们；工单
implementer 规程的铁律原文是"只动这张工单范围内的文件……违者整单白干"，
这条我认为不该自己裁决绕过。

## 四、commit 清单

- `1dd7caa` T16: nine-scenario fake-rails e2e self-test (spec §9)——
  唯一一次 commit，`research-loop/tests/helpers.py`（+90 行，新增
  `make_rails_sandbox`）+ `research-loop/tests/test_e2e.py`（新建，
  753→大约 780 行，九场景十一个 test 函数）。

## 五、自查发现与存疑

1. **evidence_lint 的"体裁过"是描述性的，不是机验的**——第一节已说明；
   T13 落地后如果想让场景①真正调用 `evidence_lint.py` 校验
   `reports/inspection-*.md`，需要回来加这一步，但那是 T13 落地之后的
   增量，不该反向阻塞 T16。
2. **场景①②当前会失败**——见第三节，status 定为
   `DONE_WITH_CONCERNS` 主要就是因为这个：test_e2e.py 本身完整、正确，
   逐场景对得上 spec §9 原文，但"验收：全过"这条硬线在
   `fallback/launch.py` 那处缺陷修复之前过不了。这不是我自己拿不准
   要不要修（分析很确定，复现也很确定），而是修复地点在工单范围外，
   需要人/ 后续工单裁决是否授权跨工单动这两个文件。
3. **场景⑧的 golden vs broken 比较是"结构对等"不是"逐字节相同"**——
   两边都各自新分配 id（B00x/D00x 从各自沙盒的 1 开始编号）、
   时间戳字段（raised_at/decided_at/answered_at）天然不同，所以断言
   比较的是行数、状态值、互指关系、`chosen`/`affects` 这些"形状"字段，
   不是整行相等。工单原文"实体数量与引用关系...逐字段一致"我按这个口径
   实现的，供评审核对是否符合原意。
4. **场景③里 argv 与 metrics_cmd 都指向 quick 单的旧 artifact_dir，
   没有指向新建的 artifact_dir**——这是照工单原文"argv 里 --out 也保持
   逐字"的字面要求走的（详见 test_e2e.py 模块内场景③函数的注释），
   不是我自己的选择；连带 metrics_cmd 一起沿用是因为它不在
   trace_check 比对的五个字段里、且这样能让两次记账读到同一份
   result.jsonl 字节，从而让两条 acc 值"逐字相同"这条断言成立，两边
   互相咬合，评审如果觉得这个理解有偏差，麻烦回工单原文核对。

## 六、修复第 1 轮（fix1）

分支：`ticket/20260814-wave5/T16`（同一条分支续跑，未另开）
head：`2a84828`

### F1（critical）：验收线"test_e2e 全过"未达标——修法

评审复核确认了报告第三节的诊断，并把处置权交回主会话；主会话裁决是
在本工单范围内直接修，而不是另开工单。按报告里给出的建议修法原样落地：

- `research-loop/scripts/fallback/launch.py`：`launch_order_ref = str(args.launch_order)`
  改成 `launch_order_ref = order["run_id"]`，两处消费点（`jobs.json` 登记、
  `RUNMETA.json` 首次写入）共用同一个变量，一处赋值改完两处生效。改动点
  加了三行注释，写清为什么必须是 `run_id`：`trace_check.py`
  `_load_launch_orders()` 按文件名 stem 建索引，`launchcmd.py` 的
  `promoted_from` 解析、`decisions.affects` 都用裸 `run_id` 当键，
  `launch.py` 原来是这条约定里的唯一例外。
- `research-loop/tests/test_fallback.py`：`test_launch_ok_writes_runmeta_and_marks_jobs_done`
  里两条断言 `entry["launch_order_ref"] == str(order_path)` /
  `runmeta["launch_order_ref"] == str(order_path)` 同步改成
  `== order["run_id"]`，与实现改动同步，不然这两条会因为修了 launch.py
  反过来红。
- `research-loop/tests/test_e2e.py`：删掉模块 docstring 里"KNOWN,
  DOCUMENTED PRE-EXISTING DEFECT"那一整段，以及 `_LAUNCH_ORDER_REF_BUG`
  常量和它在 test_1/test_2 两处 `assert code == 0` 里的引用——这段文字
  专门描述的就是这处缺陷，缺陷修完它就是过时信息，留着会误导下一个读
  这份文件的人以为 bug 还在；两处断言消息改回和文件里其余断言一致的
  `(out, err)` 朴素写法。

改动只碰这三个文件，没有动 `run.py` 注册表、`MAP.md`、`doctor.py`
（尚未落地）或其他任何工单范围外的东西；`str(order_path)` 的一处遗留
在 `test_fallback.py` 里仍在别处使用（`_run_launch(root, order_path)`），
没有变成死变量。

### 怎么验证的

```
$ python3 research-loop/tests/run_all.py test_e2e
PASS test_e2e.test_1_clean_loop_reaches_closeout
PASS test_e2e.test_2_quick_lane_skips_refs_and_blocks_story
PASS test_e2e.test_3_promote_quick_to_full_reruns_byte_identical_argv
PASS test_e2e.test_4_empty_mode_records_null_metrics
PASS test_e2e.test_5_bad_metrics_opens_blocked_with_evidence
PASS test_e2e.test_6_fail_then_retry_ok_preserves_first_attempt
PASS test_e2e.test_7_approval_invalidated_by_body_edit_rejects_new_order
PASS test_e2e.test_8a_orphan_decision_converges_on_reanswer
PASS test_e2e.test_8b_withdraw_interrupted_converges_on_rewithdraw
PASS test_e2e.test_8c_affects_missing_converges_on_launch_order_rewrite
PASS test_e2e.test_9_new_session_status_reflects_disk_truth_alone
-- run_all: 11 passed, 0 failed
```

```
$ python3 research-loop/tests/run_all.py test_fallback
-- run_all: 13 passed, 0 failed
```

```
$ python3 research-loop/tests/run_all.py test_trace_check
-- run_all: 33 passed, 0 failed
```

（`test_fallback` 覆盖被改的 `launch.py` 与它自己的两条断言；
`test_trace_check` 覆盖 `check_runs_backlink`/`check_jobs_backlink`
消费 `launch_order_ref` 的那一侧，用来确认修法真的对上了它索引
`launch_order_ref` 的方式——它自己的 fixture 早就是拿裸 `run_id`
当 `launch_order_ref` 写的，见 `test_trace_check.py` 372/416/841 行，
这次改动前就已经隐含了"正确值应该是裸 run_id"这个预期，只是
`launch.py` 一直没对上。）

```
$ python3 research-loop/tests/run_all.py
-- run_all: 232 passed, 0 failed
```

修前 230 passed / 2 failed，修后 232 passed / 0 failed——新增两个通过
的正是 F1 点名的 `test_1`/`test_2`，其余 230 个不变，没有新增失败。

### commit 清单

- `2a84828` T16: fix F1 -- launch.py launch_order_ref must be bare
  run_id, not CLI path——`research-loop/scripts/fallback/launch.py`
  （1 处赋值 +3 行注释）+ `research-loop/tests/test_fallback.py`
  （2 处断言）+ `research-loop/tests/test_e2e.py`（删过时文档段落 +
  两处断言消息简化），共 3 个文件、+10/-37 行。

### 自查发现与存疑

- F1 是本轮唯一一条 finding，已逐字按 finding 给出的诊断和建议修法
  落地，没有另外发现新问题。
- 第五节存疑 2（"场景①②当前会失败"）随本轮修复已经过时，作废，
  不再适用；其余存疑 1/3/4 与本轮无关，原样保留供评审参考。
