# T17 §V 第一轮修复：代码+表+schema（R6 两步路 / 跳层锚点 / jobs 钉名 / 分类器兜底等）

Status: resolved
Blocked by:

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `sdd/vloop-round1-verdict.json`（45 条 confirmed 的全文与复现，
本工单覆盖其中代码/表面）+ `audit-merge.md` 自决点 #151–157（设计裁决，
与本工单冲突时以裁决为准）+ spec.md §3 R6/R8、§2 通道表。
动表后必须 `gen-schemas`（若产物变）+ `gen-schemas --check` + spec_lint 双绿。

## 文件

- Modify: `research-loop/scripts/ledger_cmds/blockedcmd.py`
- Modify: `research-loop/scripts/ledger_cmds/decisionscmd.py`
- Modify: `research-loop/scripts/ledger_cmds/storycmd.py`
- Modify: `research-loop/scripts/doctor.py`
- Modify: `research-loop/scripts/error_classify.py`
- Modify: `research-loop/scripts/output_check.py`
- Modify: `research-loop/scripts/fallback/record.py`
- Modify: `research-loop/tables/writes.json` / `rows.json` / `routes.json`
- Modify: `research-loop/schemas/`（gen-schemas 重生，禁手改）
- Modify: `research-loop/tests/helpers.py` + 相关测试文件

## 要求

### A. 非 r5-choice 自决的 R6 两步路（#151；verdict v1-deploy-2 / v2-hop3-1）

1. decisionscmd `decision` 子命令新增可选 `--blocked-ref B0xx`：校验该
   blocked 行存在（跨档查），落行时写既有 `blocked_ref` 字段（现在恒 null）。
2. blockedcmd `_run_answer`，kind≠r5-choice 分支：
   - `--grant` 一律拒，文案指两步路（先 `ledger.py decision --blocked-ref …
     --authorized-by grant:D0xx|spec-standing-gpu-1h`，再答复带 --decision-ref）。
     现有"非 r5 也校验 grant 活跃"的代码块随之改造（那是上一轮堵字面量的
     临时闸，被本条取代）。
   - 新增可选 `--decision-ref D0xx`：校验行存在、kind=decision、
     blocked_ref == 本 blocked_id、decided_by=agent、authorized_by 是
     `grant:<活跃 grant>` 或 `spec-standing-gpu-1h`；过了就把
     decision_ref 写进答复更新（whitelist 已含）。
   - 不带 grant/decision-ref 的平答仍合法（R6 只管引用授权的自决）。
   - to_layer=user 分支既有的拒 --grant 保持；同样拒 --decision-ref
     （用户转录不是自决）。
3. r5-choice 分支一字不动。
4. doctor 半状态节补反向扫描：blocked 行 kind≠r5-choice 且 grant_ref 非空
   且 decision_ref 空 → 建议行 `missing R6 trace: … -> record via
   ledger.py decision --blocked-ref …`（只建议不写，doctor 体裁不变）。
5. writes.json：blocked_transitions.answered 下新增
   `_non_r5_self_decision` 键成文以上契约（两步路 + 校验清单）。

### B. 开条跳层机器锚点（#152；verdict v3-1）

writes.json blocked_transitions.open 新增：
`"legal_to": {"run": ["deploy"], "deploy": ["idea", "user"], "idea": ["user"], "oversight": ["user", "deploy"]}`
（附 `_note` 指 failures.md 的不跳层规则）。blockedcmd `_run_open` 从表读
该映射校验 --layer→--to-layer，非法组合 `_lib.fail("blocked", "to_layer",
"…escalation must go one step (…legal targets: …)", …)`。

### C. jobs 台账必加键钉名（#153；verdict v1-run-2/5、v2-hop2-1/2、v2-hop4-2/3）

rows.json jobs_min_additions 重写：钉死键名 `escalation_ref`（可空 string，
指 blocked_id）、`sampler_verdict`（enum stall|dead|ok，仅对启动过的进程）、
`sampler_verdict_at`（ISO 时刻）；`_note` 写明：预检被拒的发射**不写 jobs
条目**，拒绝 stderr 原文存档进升级条 evidence 文件；fallback 铁轨映射
done/failed→ok、timeout→stall。纯表面（无 schema 产物则只过 --check）；
文档面归 T18。

### D. error_classify 缺表兜底（#155；verdict v1-run-1 / v2-hop2-3）

`ops/error_classes.json` 缺失或不可解析 → 不裸崩：按零规则处理走既有
unknown 分类出口（stdout 判定与退出码与 unknown 同形），stderr 加一行
`error classes table not found/unreadable at <path>; treating as unclassified`。
rows.json error_classes 条目补真实字段契约（规则数组各字段名/类型/匹配语义，
照现实现成文——先读 error_classify.py 再写表，表码一致）。

### E. record.py 带 commit（#156；verdict v2-audit-1）

runs 行 `commit` 字段取 RUNMETA 的 `commit` 键（缺键才 null）。

### F. expected_outputs 非空 + story 对照口径（#157；verdict v1-run-6 / v1-idea-2）

1. rows.json launch_order.expected_outputs 加 minItems 1 → gen-schemas 重生；
   output_check 对空清单（或 schema 前旧单）拒绝 exit 4
   `expected_outputs is empty; an artifact gate with no expectations is
   vacuous — declare at least one`。helpers.make_launch_order 缺省补一条真契约
   （如 `{"path_glob": "result.jsonl", "min_bytes": 1, "min_lines": 1,
   "required": true}`），受影响 fixture/测试跟改。
2. story：rows.json story_row.baseline_runs 放宽可空（required 保留字段但
   type 加 null，语义注明 null=单臂绝对陈述）→ schema 重生；storycmd
   `--baseline-runs` 变可选缺省 null；给了则集合与 candidate_runs 完全相同
   → 拒 `story.baseline_runs: baseline set equals candidate set; a
   comparison against itself is empty`。

### G. routes.json 目标分型（verdict v1-router-2 的表侧）

routes.json 每行新增 `"kind": "handoff" | "command"`（19 行逐行标注；
handoff=层/角色移交，command=当场执行的 CLI）。spec_lint 若对表结构有断言
需同步。SKILL.md 文字归 T18。

### H. run_id 缺省命名（#154 表侧）

rows.json launch_order.run_id 的 `_note` 改为成文缺省：
`<name>-<YYYYMMDD>-<序>`，name 限 `[A-Za-z0-9_.]+`（连字符是段分隔符，
恰好落进 evidence_lint 既有 _ID_DATE_SEQ_RE 豁免形状）；工程可另立成文
规则覆盖。evidence_lint.py 一字不动。

## 测试（各行为改动配"修前红修后绿"的测试）

1. A：非 r5 行答复带 --grant → 拒；两步路走通（decision --blocked-ref 落
   blocked_ref → answer --decision-ref 回填 decision_ref）；--decision-ref
   指向 blocked_ref 不匹配/authorized_by 非授权形 → 拒；平答无 grant 仍过；
   doctor 对 grant_ref 非空 decision_ref 空的旧形状行出 missing R6 trace 建议。
2. B：run→user 开条拒、run→deploy 过、idea→deploy 拒、oversight→user 过。
3. D：无 error_classes.json 的沙盒跑 error_classify → 不 traceback、unknown
   同形输出、stderr 含表路径。
4. E：record 后 runs 行 commit == RUNMETA.commit；RUNMETA 缺键 → null。
5. F1：空 expected_outputs 的发射单过 output_check → exit 4；helpers 缺省单
   过 schema 且 output_check 对真产物 ok。
6. F2：story add 不带 --baseline-runs → 落行 baseline_runs=null 过 schema；
   baseline==candidate（同集合）→ 拒。
7. G/H：spec_lint + gen-schemas --check 双绿（表改动的回归门）。

## Comments

- 2026-08-14 wave7 收账：DONE，1 轮 0 修复，commit 范围 e4fb336..cad4770，
  merge 进 main。主仓复跑全量 311/311 + gen-schemas --check + spec_lint 三绿。
  三条 concerns 主会话亲核裁决：
  ① runs_row_normal.commit 的 schema 从 type:null 放宽为 [string,null]——
  这是自决点 #156 对原表设计（"普通行 commit 只在 RUNMETA"）的**推翻**而非
  补缺，实现者按工单"裁决为准"改表正确；旧行 commit=null 仍合法，留痕在
  表 _note 与本条。② helpers 缺省 expected_outputs 未用工单示例里的
  "required" 键——表里第四字段本来就是 required_keys[]，工单示例是主会话
  笔误，实现者取实际被 output_check 消费的三字段，认可。③ routes.json
  12/13 行（撤销/打回）标 kind=command：成立（command=当场处置不换层，
  含多步程序不只单条 CLI）——kind 语义这句话转 T18 写进 SKILL.md。
  接受的 minor：test_fallback 本地 _make_order 仍造 expected_outputs=[] 的
  单（手写落盘不过 launch-order 门，行为无洞，fixture 与新 minItems 语义
  不一致而已）。
