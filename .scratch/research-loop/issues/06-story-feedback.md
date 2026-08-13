# T06 故事账 + 反馈账

Status: ready-for-agent
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `tables/rows.json`（story_row 含 `_write_check`、feedback_rows）+
`tables/writes.json`（owner_values.shared-append、withdrawal_proxy.story、
form2 白名单 story）+ spec.md §2.6（quick 行禁入故事）、R9、§9 对应条。

## 文件

- Create: `research-loop/scripts/ledger_cmds/storycmd.py`
- Create: `research-loop/scripts/ledger_cmds/feedbackcmd.py`
- Create: `research-loop/tests/test_story_feedback.py`

## 要求

### story add（--layer idea 独占）

- 三个 run 列表参数是逗号分隔串；写入前跨档（include_archive=True）做
  `_write_check`：每个被引 run_id 必须在 runs 账存在、其行 status=ok、
  quick 不为 true（criterion 行 quick=null 放行）。违反分别报
  `story.evidence_runs: run not found / run status is not ok / quick runs
  cannot enter the story ledger`（带 run_id 实际值）。
- metric_names 非空时：每个 metric 必须在**每个**被引 run（evidence ∪
  baseline ∪ candidate）的 runs 行里出现过（metric_name 列），否则
  `story.metric_names: metric not found in referenced run (got: ...)`
  ——§9"metric_names 指向不存在的指标则 story 写入拒"的落点。
- decided_by 固定 "user"（schema const）、date=today()、status=active、
  claim_id 自增 S 前缀；validate + 持锁 append。

### story retire（SID --reason TEXT [--superseded-by SID2]，不收 --layer）

撤销代笔（withdrawal_proxy.story）：就地 {status: retired,
retired_reason: reason, retired_date: today(), retired_by: "user",
superseded_by: 给了先验证存在}。字段全在 form2 story 白名单内。

### feedback add（--layer ∈ idea|deploy|run|oversight）

suggestion 行：fb_id 自增 F、kind=suggestion、date=today()、layer=--layer
（条目 layer 自证）、context/problem/suggestion 必填；validate
（feedback.suggestion schema）+ append。

### feedback review（--layer user 强制）

- --layer ≠ user → 拒 `feedback.layer: review rows only accept --layer user`。
- --ref 必须存在且 kind=suggestion，否则拒。
- 追加 review 行（新 fb_id、kind=review、ref、layer="user"、verdict、note、
  date）；validate（feedback.review schema）。
- 反馈账只许追加：不提供任何就地更新口（form2 无 feedback）。

## 测试（test_story_feedback.py）

1. story add：被引 run 不存在拒 / status=failed 拒 / quick=true 拒 /
   合法（fixture 用 helpers.make_runs_row_normal 裸写 runs 账）落 S001。
2. metric_names 含 runs 里没有的指标名 → 拒；全存在 → 过。
3. criterion 行（quick=null）作 evidence → 放行。
4. story add 用 --layer deploy → 拒（idea 独占）。
5. retire：字段五件齐、--superseded-by 指向不存在的 claim 拒。
6. feedback add 四层各过一次，layer 字段自证正确；--layer user 的 add 拒
   （suggestion 的 layer 域是四层）。
7. review：--layer deploy 拒；--ref 指向 review 行拒；合法 review 落行。
8. "改写旧行拒"：直接调 `_lib.inplace_update`（whitelist=set()）改
   suggestion 文本 → RLError。

## Comments
