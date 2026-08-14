# T17 报告：§V 第一轮修复——代码+表+schema

工单：`.scratch/research-loop/issues/17-vloop-code.md`
分支：`ticket/20260814-wave7/T17`（base `e4fb336fc7750584f61f4517b537188b0be56311`，
head `8937e0ad7e3520851ecc71f529f9c9778aeb4e37`）
工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave7-T17`（收尾已删除，分支保留）

## 做了什么

按工单 A-H 逐条对照：

**A（#151，非 r5-choice 自决的 R6 两步路）**

1. `decisionscmd.py` 的 `decision` 子命令新增可选 `--blocked-ref B0xx`：跨档
   （含 archive）校验该 blocked 行存在，落行时写进既有 `blocked_ref` 字段
   （原来恒 `None`）。
2. `blockedcmd.py` `_run_answer`，kind≠r5-choice 分支：
   - `--grant` 一律拒（不论对应的 grant 是否活跃），拒绝文案指向两步路
     （`ledger.py decision --blocked-ref … --authorized-by grant:D0xx|
     spec-standing-gpu-1h`，再 `blocked answer --decision-ref D0xx`）。
     替换掉的正是工单点名的"上一轮堵字面量的临时闸"（原来对所有 kind
     统一校验 `--grant` 是否活跃，现在按 kind 拆成 r5-choice（原样保留）
     与非 r5-choice（改造）两支）。
   - 新增可选 `--decision-ref D0xx`：校验行存在、`kind=decision`、
     `blocked_ref` 等于本 blocked_id、`decided_by=agent`、`authorized_by`
     是 `grant:<活跃 grant>` 或字面量 `spec-standing-gpu-1h`；过了就把
     `decision_ref` 写进答复更新（whitelist 已含该字段，未改）。
   - 不带 `--grant`/`--decision-ref` 的平答仍合法。
   - `to_layer=user` 分支既有的拒 `--grant` 保持，同样拒 `--decision-ref`。
   - r5-choice 分支代码一字不动（原来的早退检查原样保留在 `if row["kind"]
     == "r5-choice":` 分支里）。
3. `doctor.py` 半状态节新增 `_missing_r6_trace_findings`：blocked 行
   kind≠r5-choice 且 `grant_ref` 非空且 `decision_ref` 空 → 建议行
   `missing R6 trace: … -> record via ledger.py decision --blocked-ref … `。
   只建议不写，纳入 `_section_half_state` 的第四类扫描。
4. `writes.json` `blocked_transitions.answered` 下新增 `_non_r5_self_decision`
   键，成文两步路契约、`--decision-ref` 校验清单、平答例外、
   `to_layer=user` 例外、r5-choice 不受影响四条说明。

**B（#152，开条跳层的机器锚点）**

`writes.json` `blocked_transitions.open` 新增
`legal_to: {run: [deploy], deploy: [idea, user], idea: [user], oversight:
[user, deploy]}` + `_legal_to_note`。`blockedcmd.py` `_run_open` 从表读该
映射校验 `--layer` → `--to-layer`，非法组合 `_lib.fail("blocked",
"to_layer", "escalation must go one step (…)", …)`。

**C（#153，jobs 台账必加键钉名）**

`rows.json` `jobs_min_additions` 重写：字典形式钉死键名
`escalation_ref`（可空 string，指 blocked_id）、`sampler_verdict`（enum
stall|dead|ok，只对启动过的进程）、`sampler_verdict_at`（ISO 时刻）；补
`_precheck_refusal`（预检被拒不写 jobs 条目）、`_fallback_mapping`
（done/failed→ok、timeout→stall）、`_schema_note`（纯表面，不参与
gen-schemas）。纯表格改动，不涉及代码——run 层直接编辑权文档面归 T18。

**D（#155，error_classify 缺表兜底）**

`error_classify.py`：`ops/error_classes.json` 缺失或不可解析 →
不再 traceback（原来的 `except` 块打印错误后 `return 2`），改成打印
`error_classify: error classes table not found/unreadable at <path>;
treating as unclassified` 到 stderr，`classes = {}`，继续走既有 unknown
分类出口（stdout 判定 `{"rule": null, "action": "unknown"}`，exit 0，与
"零规则命中"同形）。`rows.json` `error_classes` 补真实字段契约
（`_match_fields`/`_match_semantics`，先读代码再写表，字段名与
`error_classify.py` 的 `_MATCH_KEYS`/`_rule_matches` 逐字对齐）。

**E（#156，record.py 带 commit）**

`fallback/record.py` `_run_level_row` 新增 `commit` 参数，调用处从
`runmeta.get("commit")` 取值（RUNMETA 无此键才 null），不再硬编码 `None`。
**连带发现并修复一处表侧缺陷**：`rows.json` `runs_row_normal.commit` 字段
原本 `"type": "null"`（恒为 null 的 schema 硬约束）——这正是 v2-audit-1
指出的病灶本身，只是此前从未被撞到（字段永远写 null，恰好过 schema）。
不改这一处，record.py 的修复会在写入真实 commit 哈希时被 schema 拒绝
（本地测试实测复现：`runs.commit: expected type null (got: '<hash>')`）。
改为 `["string", "null"]` 并重生成 schema。

**F1（#157，expected_outputs 非空）**

`rows.json` `launch_order.expected_outputs` 加 `minItems: 1`
（gen-schemas 重生 `launch_order.schema.json`）。`output_check.py`
`run()` 对空清单（或缺省清单）返回
`{"verdict": "empty-output", "failures": [{"glob": null, "file": null,
"why": "expected_outputs is empty; an artifact gate with no expectations
is vacuous — declare at least one"}]}`，走既有 "verdict != ok → exit 4"
路径，不需要改 `main()`。`tests/helpers.py` `make_launch_order()` 缺省
`expected_outputs` 从 `[]` 改成
`[{"path_glob": "result.jsonl", "min_bytes": 1, "min_lines": 1}]`（真实、
`output_check.py` 实际会用到的字段——工单示例里的 `"required": true` 字段
`output_check.py` 不消费，未采纳，理由见下"自查发现"）。

**F2（#157，story 对照口径）**

`rows.json` `story_row.baseline_runs` 类型放宽为 `["array", "null"]`
（required 保留字段，仅类型加 null；gen-schemas 重生
`story.schema.json`）。`storycmd.py`：`--baseline-runs` 从 `required=True`
改为可选（缺省 `None`）；缺省时 `baseline_runs=None`（单臂陈述，不参与
"跟 candidate 是否同集合"校验，也不进 `_check_referenced_runs` 的引用清单）；
给了则与 `candidate_runs` 完全同集合（`set()` 比较，忽略顺序）→ 拒
`story.baseline_runs: baseline set equals candidate set; a comparison
against itself is empty`。

**G（v1-router-2 的表侧）**

`routes.json` 19 行逐行新增 `"kind": "handoff" | "command"`，顶层加 `_kind`
键成文判别口径。分类结果：11 条 handoff（1-10 行 idea-layer/deploy-layer/
oversight→inspector/rails.paper 目标 + 17 行"深查这批"直接派给 inspector），
8 条 command（11-16、18-19 行的 `ledger.py …`/`doctor.py …` 字面命令，以及
13 行"撤销"、14 行"打回"两条——这两条不带层/角色目标，是当场执行的写入
动作，判定依据见下"自查发现"）。SKILL.md 文字更新归 T18，本工单未碰。

**H（#154，run_id 缺省命名）**

`rows.json` `launch_order.run_id` 的 `_note` 补成文缺省形态
`<name>-<YYYYMMDD>-<序>`（name 限 `[A-Za-z0-9_.]+`）。`evidence_lint.py`
一字未动（工单要求）；核实过该形态确实落进其既有 `_ID_DATE_SEQ_RE =
\b[\w.]+-\d{8}-\d+\b` 的豁免正则。

## 怎么验证的

```
$ cd research-loop && python3 tests/run_all.py
-- run_all: 309 passed, 0 failed

$ python3 scripts/ledger.py gen-schemas --check
（exit 0，无输出）

$ cd .. && python3 .scratch/research-loop/spec_lint.py
-- spec_lint: 0 errors, 0 warnings
```

各条对应的"修前红修后绿"测试（新增或改写，均在上面 309 条里）：

- A：`test_blocked_decisions.py`
  - `test_non_r5_answer_grant_always_rejected_regardless_of_active_status`
    （改写自原 `test_non_r5_answer_grant_must_be_active_regardless_of_kind`
    ——旧测试断言的正是被 #151 取代的旧行为：非 r5 行带 `--grant` 且 grant
    活跃时会成功落 `grant_ref`，现在这个分支已经不存在，改为断言活跃/不
    活跃两种 grant 都被拒）
  - `test_non_r5_two_step_path_decision_then_answer_with_decision_ref`
    （两步路走通，`decision_ref` 回填）
  - `test_non_r5_decision_ref_must_point_back_at_this_blocked_row`
  - `test_non_r5_decision_ref_not_found_rejected`
  - `test_non_r5_decision_ref_wrong_kind_rejected`（指向 kind=grant 的行）
  - `test_non_r5_decision_ref_decided_by_user_rejected`
  - `test_non_r5_decision_ref_authorized_by_not_recognized_form_rejected`
  - `test_non_r5_decision_ref_grant_no_longer_active_rejected`
  - `test_to_layer_user_answer_with_decision_ref_is_rejected`
  - `test_decision_blocked_ref_must_exist`
  - `test_decision_blocked_ref_found_cross_archive`
  - `test_decision_blocked_ref_valid_lands_field_previously_always_null`
  - `test_doctor.py::test_doctor_missing_r6_trace_is_reported_and_sandbox_is_untouched`
  - `test_doctor.py::test_doctor_missing_r6_trace_skips_r5_choice_and_complete_rows`
- B：`test_blocked_decisions.py::test_open_legal_to_layer_enforced`
  （run→user 拒、run→deploy 过、idea→deploy 拒、oversight→user 过）
- D：`test_output_error.py::test_error_classify_missing_table_treated_as_unclassified`
  、`test_error_classify_unreadable_table_treated_as_unclassified`
- E：`test_fallback.py::test_record_ok_writes_two_metric_rows_with_matching_run_level_fields`
  （改写：commit 断言从 `is None` 改成 `== _lib.git_head(root)`）、
  `test_record_commit_missing_from_runmeta_lands_null`（新增，RUNMETA
  缺 commit 键的场景）
- F1：`test_output_error.py::test_output_check_empty_expected_outputs_rejected`
  、`test_output_check_helpers_default_contract_ok_against_a_real_artifact`
  、`test_launch_order.py::test_quick_true_all_refs_null_writes_successfully`
  （补一行 `assert written["expected_outputs"]`）
- F2：`test_story_feedback.py::test_story_add_without_baseline_runs_lands_null`
  、`test_story_add_baseline_equals_candidate_set_rejected`
- G/H：spec_lint + gen-schemas --check（跑法见上）

## commit 清单

- `3f941d9` T17: R6 two-step self-decision path (#151) + escalation
  legal_to (#152) —— `tables/writes.json`、
  `scripts/ledger_cmds/blockedcmd.py`、`scripts/ledger_cmds/decisionscmd.py`、
  `scripts/doctor.py`、`tests/test_blocked_decisions.py`、
  `tests/test_doctor.py`
- `3a30e9e` T17: routes.json kind field (handoff|command) per row —— v1-router-2
  —— `tables/routes.json`
- `8937e0a` T17: jobs/error_classes table contracts + record.py commit +
  output/story gates (#153-157) —— `tables/rows.json`、
  `schemas/launch_order.schema.json`、`schemas/runs.normal.schema.json`、
  `schemas/story.schema.json`、`scripts/error_classify.py`、
  `scripts/fallback/record.py`、`scripts/ledger_cmds/storycmd.py`、
  `scripts/output_check.py`、`tests/helpers.py`、`tests/test_fallback.py`、
  `tests/test_launch_order.py`、`tests/test_output_error.py`、
  `tests/test_story_feedback.py`

## 自查发现与存疑

1. **连带修的一处非工单条文的 schema 缺陷**：`rows.json`
   `runs_row_normal.commit` 原来 `"type": "null"`，与 E 条要求的行为
   （落真实 commit）直接矛盾——不改这处，`record.py` 的修复本身跑不通
   （本地跑测试实测复现过 `runs.commit: expected type null (got: '<hash>')`
   的报错）。工单 E 条文字只提了 `record.py`，没提这处 schema，但这是修
   E 的必要前提，不改就是白改，所以一并改了，并在 commit message 里说明。
   `test_fallback.py::test_record_ok_writes_two_metric_rows_with_matching_run_level_fields`
   原有一行 `assert acc_row["commit"] is None` 断言的正是旧（错）行为，
   一并改成断言真实 commit 值。

2. **helpers 缺省 `expected_outputs` 未采纳工单原文的 `"required": true`
   字段**：工单 F1 给的示例是
   `{"path_glob": "result.jsonl", "min_bytes": 1, "min_lines": 1,
   "required": true}`，但 `output_check.py` 的 `check_file`/`check_entry`
   只认 `path_glob`/`min_bytes`/`min_lines`/`required_keys` 四个字段，
   没有 `required` 这个键，加了也是死代码。改成
   `{"path_glob": "result.jsonl", "min_bytes": 1, "min_lines": 1}`——
   与仓库里已有的 `test_e2e.py` 里同样的 `result.jsonl` 约定一致。
   工单原文标了"如"（例如），按实现口径落地而非逐字照抄，是否合适请复核。

3. **G 条 13/14 两行（"我收回那条决定"/"这个不行，重做"）判成 kind=command
   而非 handoff**：verdict v1-router-2 举的两类例子明确点了
   idea-layer/deploy-layer/oversight→inspector（handoff）与
   `ledger.py render blocked`/`doctor.py`/`ledger.py init`（command），
   没有直接点这两行。判断依据：SKILL.md"Layer identity, restated once"
   把 handoff 定义为"设定接收会话层身份"的动作；这两行的实际动作是当场
   会话原地写账（撤销体裁走 `writes.json withdrawal_proxy` 的代笔路径、
   打回写批次报告头 `rejections[]`），不设定任何新会话的层身份，也不像
   `rails.paper`/`inspector` 那样把控制权移交给一个具名的层/角色/铁轨。
   这条分类是本工单范围内我自己的判断，不是逐字抄工单，标在这里供复核。

4. **jobs_min_additions 的 `sampler_verdict` 枚举没有登记进 `rows.json`
   顶层 `enums` 块**：因为 `jobs_min_additions` 在 `rows.json` 自己的
   `_not_generated` 清单里（jobs.json 没有 schema 产物，不走
   gen-schemas），用 `$enum` 方言语法会造成"看着像机器块、实际没人解析"
   的误导，所以写成了纯散文 enum 说明。`spec_lint.py` 的 `check_generatable`
   （E4）也确认只扫 `GEN_BLOCKS` 六个块，`jobs_min_additions` 不在其中，
   这处不受影响。

5. **`decision --blocked-ref` 与 `blocked answer --decision-ref` 的
   `--layer` 隔离没有额外校验**：工单没要求"decision 的 --layer 必须
   等于将来 answer 的 --layer"（比如 run 层开的 blocked 行，deploy 层写
   decision，deploy 层再 answer——这条本来就该合法，`decisionscmd.py`
   的 `--layer` 校验独立于 `blockedcmd.py`），没加额外约束，按最小实现
   处理。

未发现工单要求之外我自己引入的行为或代码；未使用 GPU；未改
`run.py`/`MAP.md`（工单声明本来就不涉及）。

## 第一轮修复：F1（expected_outputs 的 minItems:1 是死约束）

工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave7-T17-fix1`（收尾已删除，
分支保留）。分支未变，仍是 `ticket/20260814-wave7/T17`
（上一轮 head `8937e0ad7e3520851ecc71f529f9c9778aeb4e37`，
本轮修复后 head `cad4770154f2ec587f15e193a2c761a732839c64`）。

### 怎么修的

复核 finding：`research-loop/scripts/_lib.py::_check_value()`（第370-387行）
逐行核对，确认只实现了 `type`/`enum`/`const`/`minimum`/`items` 五个关键字，
从未读过 `minItems`；`launchcmd.py::_run_launch_order()` 对草稿也只调用通用
`_lib.validate(draft, schema, "launch_order")`，没有像 `storycmd.py` 对
baseline==candidate 那样另写手工 Python 检查补足。复现：把 `_lib.py` 的改动
`git stash` 掉后跑新测试，`expected_outputs: []` 的草稿确实以 exit 0 落盘
（见下"测试"节的 red 复现记录）。

`minItems` 只在整个仓库出现一次（`rows.json launch_order.expected_outputs`
及其重生的 `launch_order.schema.json`），没有别的表字段用到这个关键字。据此
判断：在共享校验器 `_check_value()` 里补一个真正读 `minItems` 的分支，是
最小且唯一必要的修法——不是给某条命令单独打补丁，而是把这个已经写在 schema
里、从未生效过的关键字实现出来，观察到的行为变化恰好只有 F1 要求的这一条
（launch-order 写入时对空 `expected_outputs` 拒绝），没有引入任何 F1 之外的
新约束。

`research-loop/scripts/_lib.py`：在 `_check_value()` 里 `minimum` 分支之后
新增：

```python
if "minItems" in field_schema:
    if not isinstance(value, list) or len(value) < field_schema["minItems"]:
        fail(ledger, field_path, f"fewer than minItems {field_schema['minItems']}", value)
```

写法照抄紧邻的 `minimum` 分支的风格（同样先防御性检查类型，再比较数值）。
同时把 `validate()` 的 docstring 里"Checks required, additionalProperties,
type..., minimum, array items..."补上 `minItems`。

这一改动让 `launchcmd.py::_run_launch_order()` 已有的
`_lib.validate(draft, schema, "launch_order")` 调用自动拿到 `minItems` 校验，
不需要碰 `launchcmd.py` 本身一个字。`output_check.py` 的空清单拒绝
（读时兜底，服务 minItems 补丁落地前写的旧单）本身工单第一轮已经做对，未动。

### 测试

新增两条测试，均按"改前跑 red、改后跑 green"验证过：

1. `research-loop/tests/test_lib.py::test_validate_minitems`——在改动函数
   自身的边界（`_lib.validate()`）加单元测试，照抄相邻
   `test_validate_minimum` 的写法：schema 里 `expected_outputs` 字段带
   `minItems: 1`，`["x"]` 过、`[]` 拒。
2. `research-loop/tests/test_launch_order.py::
   test_empty_expected_outputs_rejected_by_schema_before_write`——集成测试，
   钉住 F1 描述的确切回归场景：草稿 `expected_outputs: []` 过
   `ledger.py launch-order --layer deploy --file draft.json`，断言
   exit code == 2、stderr 含 `launch_order.expected_outputs` 与
   `minItems`、且 `ops/launch_orders/run-empty-outputs.json` 未落盘。

红测复现（`git stash push -- research-loop/scripts/_lib.py` 后跑）：

```
$ cd research-loop && python3 tests/run_all.py test_lib
FAIL test_lib.test_validate_minitems
-- run_all: 35 passed, 1 failed

$ python3 tests/run_all.py test_launch_order
FAIL test_launch_order.test_empty_expected_outputs_rejected_by_schema_before_write
-- run_all: 19 passed, 1 failed
```

`git stash pop` 恢复修复后（绿测）：

```
$ python3 tests/run_all.py
-- run_all: 311 passed, 0 failed

$ python3 scripts/ledger.py gen-schemas --check
（exit 0，无输出）

$ cd .. && python3 .scratch/research-loop/spec_lint.py
-- spec_lint: 0 errors, 0 warnings
```

（309 基线 + 本轮新增 2 条 = 311，与"第一轮"报告的 309 对得上。）

### commit 清单

- `cad4770` T17: fix1 F1 -- implement minItems in the shared schema
  validator —— `research-loop/scripts/_lib.py`、
  `research-loop/tests/test_launch_order.py`、
  `research-loop/tests/test_lib.py`

### 自查发现与存疑

未发现范围外改动；未碰 `run.py`/`MAP.md`；未使用 GPU。`minItems` 目前只有
`launch_order.expected_outputs` 一处使用者，`_check_value()` 里新加的分支
对其余现有 schema 无副作用（已用全量测试套件 + `gen-schemas --check` +
`spec_lint` 三线核实）。
