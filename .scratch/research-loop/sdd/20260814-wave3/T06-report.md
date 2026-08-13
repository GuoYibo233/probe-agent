# T06 报告：story 账 + feedback 账

工单：`.scratch/research-loop/issues/06-story-feedback.md`
分支：`ticket/20260814-wave3/T06`（base `6cce8bc`，head `4e54feb`）

## 一、做了什么（对照工单逐条）

### story add（--layer idea 独占）

- `research-loop/scripts/ledger_cmds/storycmd.py` 的 `_cmd_add`：先查
  `args.layer != "idea"` 拒绝（`story.layer: story add is idea-layer only`），
  再拆三个逗号分隔的 run 列表参数。
- `_check_referenced_runs`：跨档（`jsonl_rows(..., include_archive=True)`）
  读 runs 账，对 evidence/baseline/candidate 三个列表的并集逐一查：
  存在性、`status=="ok"`、`quick is not True`——三种违反都按工单原话报
  `story.evidence_runs: run not found / run status is not ok / quick runs
  cannot enter the story ledger`，`(got: '<run_id>')` 带实际值。工单原文把
  三条违反消息统一写在 `story.evidence_runs` 名下（没有按 baseline/
  candidate 拆分字段名），本实现照抄这个字段名，不管命中的 run_id 来自
  哪一个列表。
- `_check_metric_names`：`metric_names` 非空时，对 evidence∪baseline∪
  candidate 去重后的每个 run_id，检查每个 metric 是否在该 run 的
  runs 行 `metric_name` 列里出现过；缺一个就报
  `story.metric_names: metric not found in referenced run (got: '<metric>')`。
- 落 `claim_id`（S 前缀自增，读现有 story.jsonl 含归档）、`decided_by="user"`、
  `date=today()`、`status="active"`；`validate()` 走 `schemas/story.schema.json`；
  持锁 append。
- **principle_id 存在性不在本工单范围**：rows.json 把 `principle_id` 标成
  `$ref_to`，工单的 `_write_check` 引述里没有提它，spec 也把 `$ref_to` 的
  存在性检查明确划给 trace_check（T11）——本命令不查。

### story retire（SID --reason TEXT [--superseded-by SID2]，不收 --layer）

- `_cmd_retire`：`--reason` 必须给出用户原话（空白字符串拒
  `story.retired_reason: withdrawal requires the user's own words`，对应
  `tables/writes.json` withdrawal_proxy 的"无用户原话拒"）。
- `--superseded-by` 给了先查存在（跨档），不存在拒
  `story.superseded_by: claim not found (got: '<sid>')`——校验先于
  `inplace_update`，被拒时原行不动。
- 就地更新走 `_lib.inplace_update`，whitelist 精确等于 form2 白名单五件：
  `status/retired_reason/retired_date/retired_by/superseded_by`。

### feedback add（--layer ∈ idea|deploy|run|oversight）

- `research-loop/scripts/ledger_cmds/feedbackcmd.py` 的 `_cmd_add`：
  `--layer` 不在四层集合内拒
  `feedback.layer: add rows only accept layer values idea|deploy|run|oversight`。
  该四层限制是脚本手查（schema 里 layer 字段只是 `type: string`，没有
  `$enum`——tables/rows.json 的 enums 表本来就没收 `feedback.layer` 这个键）。
- `fb_id` F 前缀自增（跨档读现有行）、`kind="suggestion"`、`date=today()`，
  `layer=args.layer` 原样落（"条目 layer 自证"）；`validate()` 走
  `schemas/feedback.suggestion.schema.json`；持锁 append。

### feedback review（--layer user 强制）

- `_cmd_review`：`--layer != "user"` 拒
  `feedback.layer: review rows only accept --layer user`——工单给的是这句
  的完整原文，不带 `(got: ...)` 后缀，所以调用 `_lib.fail` 时没传 value。
- `--ref` 先查存在（不存在拒 `feedback.ref: row not found`），再查
  `kind == "suggestion"`（不是则拒
  `feedback.ref: ref must point to a suggestion row`）。
- 落 `fb_id`（F 前缀自增）、`kind="review"`、`ref/layer="user"/verdict/note/
  date`；`validate()` 走 `schemas/feedback.review.schema.json`；持锁 append。
- 反馈账只许追加：`feedbackcmd.py` 全程没有调用 `_lib.inplace_update`；
  `tables/writes.json` 的 form2 白名单本来就没有 `feedback` 这一项。

## 二、怎么验证的

全部命令在工作树 `/home/y-guo/reproduce/new1-wt/20260814-wave3-T06` 内跑，
`cwd` 为该工作树根。

```
$ python3 research-loop/tests/run_all.py test_story_feedback
```
末尾输出：
```
-- run_all: 17 passed, 0 failed
```

（17 条 = 工单列的 8 条场景，"story add 合法" 拆成"存在性/status/quick 各一条
拒绝用例 + 一条合法落账"共 4 条、metric_names 拒绝+放行 2 条、criterion 行
放行 1 条、layer 独占拒绝 1 条、retire 三条（五件齐 + superseded-by 拒绝 +
按 writes.json 补的空原话拒绝）、feedback add 两条、feedback review 三条、
`_lib.inplace_update` 直调拒绝 1 条。）

再跑全量测试套件确认没有回归：
```
$ python3 research-loop/tests/run_all.py
```
末尾输出：
```
-- run_all: 75 passed, 0 failed
```

`python3 -m py_compile` 三个新文件全过（语法检查）。

本工单范围声明"不改 run.py / MAP.md"，没有新增或改动任务，因此没有跑
`python3 run.py selfcheck`（三个新文件都在 `research-loop/` plugin 内，不
挂 run.py 注册表）。

## 三、commit 清单

- `4e54feb` `T06: story + feedback ledger writes (ledger.py story/feedback)`
  ——三个文件：`storycmd.py`、`feedbackcmd.py`、`test_story_feedback.py`，
  一次性提交（实现+测试同批，逻辑上是一个不可拆的单元：没测试的实现在这
  张工单的纪律下不算完成）。

工作树内 `git status` 干净（提交后立即检查过），已按协议
`git worktree remove` 删除工作树，分支 `ticket/20260814-wave3/T06` 保留。

## 四、自查发现与存疑

1. **`story.evidence_runs` 字段名覆盖三个 run 列表**：工单原文把"run not
   found / run status is not ok / quick..."三条违反消息都写成
   `story.evidence_runs: ...`，没有为 baseline_runs/candidate_runs 单独开
   字段名。我按字面实现——不管违规的 run_id 来自哪个列表，报错字段名一律
   `evidence_runs`。这个决定我认为是对工单原文最贴切的字面理解，但如果
   实际意图是"按来源列表报不同字段名"，这里需要回工单澄清；目前测试
   （`test_story_add_rejects_evidence_run_not_found` 等）按"统一
   evidence_runs"这个理解断言的。
2. **两处消息的 wording 是我自己拟的，工单没给精确原文**：
   - `story.layer: story add is idea-layer only`（工单只写"idea 独占"，
     没给错误原话）；
   - `feedback.layer: add rows only accept layer values
     idea|deploy|run|oversight`（工单只写"四层各过一次...--layer user 的
     add 拒"，没给错误原话）；
   - `feedback.ref: row not found` / `feedback.ref: ref must point to a
     suggestion row`（工单只写"--ref 必须存在且 kind=suggestion，否则拒"，
     没有拆成两句话的原文）；
   - `story.superseded_by: claim not found`、
     `story.retired_reason: withdrawal requires the user's own words`
     同理。
   这些地方都走 `_lib.fail()` 的固定格式（R3：`<账名>.<字段路径>: <说明>`），
   字段名和大意照工单/writes.json 走，只是措辞本身工单没有钉死。
3. **空白 `--reason` 拒绝没有被工单的 8 条测试列举**，是我按
   `tables/writes.json` withdrawal_proxy 的"无用户原话拒"文字要求补的
   （补了对应测试 `test_story_retire_rejects_blank_reason`）——这条不算
   YAGNI 违规，因为它直接对应工单引用的 spec/writes.json 条款，但列在这里
   供复核。
4. **命令成功时把新行/更新后的行整块 JSON 打到 stdout**：工单和 plan.md
   都没有给这四个 write 子命令的 stdout 契约，我选了"打印整行 JSON"这个
   最直接、机器可读、也方便测试断言的形式；如果后续工单（T15 skill 文档、
   T16 e2e）对 stdout 格式有别的期待，这里可能要跟着改。
5. **没有做的**：`principle_id`、`decisions`（grant/blocked）之类跨账引用
   的存在性检查——按 `tables/rows.json` 的 `$ref_to` 注解和 spec §0.5 的
   分工，这些归 T11 trace_check，本工单的 `_write_check` 明确只提了 run
   存在性/status/quick 与 metric_names，没多做。

## 五、修复第 1 轮（工作树 `20260814-wave3-T06-fix1`，base `4e54feb`）

### F1（important）：feedback review 的 `--ref` 不存在分支没有测试覆盖

工单原文"--ref 必须存在且 kind=suggestion，否则拒"是两个独立子句。
`feedbackcmd.py._cmd_review` 的实现本身没问题——`ref_row is None` 时报
`feedback.ref: row not found`，`kind != "suggestion"` 时报
`feedback.ref: ref must point to a suggestion row`，两条分支都在——但测试
文件只有 `test_feedback_review_rejects_ref_pointing_at_a_review_row` 覆盖
第二条，`--ref` 指向完全不存在的 `fb_id` 这一条没有任何用例兜底。

**怎么修的**：读了 `feedbackcmd.py._cmd_review` 确认逻辑没问题（`_lib.fail
("feedback", "ref", "row not found", args.ref)`，格式走 `_lib.fail` 的固
定拼接：`<ledger>.<field>: <msg> (got: <value!r>)`），只补测试，不动实现
代码。新增 `test_feedback_review_rejects_ref_not_found`：先 `_add_suggestion`
落一条合法建议占位（确认反馈账非空场景下也生效，不是靠空账通过），再用
`--ref F999`（账里不存在的 fb_id）调 `feedback review`，断言 `code == 2`
且 `err.strip() == "feedback.ref: row not found (got: 'F999')"`。插入位置
紧邻 `test_feedback_review_rejects_ref_pointing_at_a_review_row` 之前，同属
"7. feedback review" 分组，风格（sandbox 建法、断言写法）照抄同组其他用例。

未触碰任何实现文件（`storycmd.py`、`feedbackcmd.py` 本轮零改动），diff 只
有 `test_story_feedback.py` 的 13 行新增。

### 怎么验证的

工作树 `/home/y-guo/reproduce/new1-wt/20260814-wave3-T06-fix1`，`cwd` 为该
工作树根。

```
$ python3 research-loop/tests/run_all.py test_story_feedback
```
末尾输出：
```
-- run_all: 18 passed, 0 failed
```
（17 → 18，新增的 `test_feedback_review_rejects_ref_not_found` 在列，且
`PASS`。）

全量回归：
```
$ python3 research-loop/tests/run_all.py
```
末尾输出：
```
-- run_all: 76 passed, 0 failed
```
（75 → 76，无回归。）

### commit 清单

- `a88395f` `T06: cover feedback review --ref pointing at a nonexistent
  fb_id (F1)`——`test_story_feedback.py` 新增
  `test_feedback_review_rejects_ref_not_found`，13 行，无实现代码改动。

工作树内 `git status` 提交后为干净，已按协议 `git worktree remove` 删除
工作树，分支 `ticket/20260814-wave3/T06` 保留，head 更新为 `a88395f`。

### 自查

diff 只加了一个测试函数，没有改动任何实现文件，没有引入新的 helper 或
fixture，风格与同组其余测试一致。范围只覆盖 F1 这一条 finding，没有顺带
改动本轮报告以外的任何东西。本轮无遗留 concerns。
