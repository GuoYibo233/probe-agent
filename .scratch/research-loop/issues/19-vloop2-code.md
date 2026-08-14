# T19 §V 第二轮修复：代码+表（jobs 合并 / evidence_lint 误火 / render 状态列 / routes 拆列 / 表注）

Status: resolved
Blocked by:

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `sdd/vloop-round2-verdict.json`（48 条 confirmed 全文与复现）+
`audit-merge.md` 自决点 #158–161（设计裁决，与工单冲突以裁决为准）。
动表后 `gen-schemas --check` + spec_lint 双绿；交付前全量 run_all 绿。

## 文件

- Modify: `research-loop/scripts/fallback/launch.py`
- Modify: `research-loop/scripts/evidence_lint.py`
- Modify: `research-loop/scripts/ledger_cmds/querycmd.py`
- Modify: `research-loop/tables/routes.json` / `rows.json`
- Modify: 相关测试文件

## 要求

### A. launch.py 首次登记 merge（#161；verdict v2-hop4-2）

发射时的 jobs 登记（launch.py:159-168 一带的整体赋值）改成与收尾更新
（:219-225）相同的 merge 形态：`entry = jobs.get(run_id, {})` 起步，只更新
发射器自有五键（launch_order_ref/state/started_at/finished_at/log_path），
外来键（escalation_ref/sampler_verdict/sampler_verdict_at 等）原样保留。

### B. evidence_lint 四类机械误火豁免（#159；verdict v1-oversight-3、v2-hop6-4/5/6）

规则 2（no-repro-command）新增，规则 1 不动：
1. `> ` 开头的摘录行整行不进规则 2 扫描（引用不是主张；摘录保真已由
   verify_report 逐字节比对负责）。
2. 剥除行首的标题/列表编号前缀（`## 2.` / `3.` 一类——只剥行首序号，
   不剥行中数字）。
3. 剥除 `§\d+`（含括号形 `(§1)`）。
4. 剥除字母紧连数字的单 token（`\b[A-Za-z_]+\d+\b`：python3/sha256/
   attempt1/utf8 形）。
5. `$ ` 行的反斜杠续行加入 protected 集（现只保护 `$ ` 行本身与紧邻
   `= ` 行）。
带空格的序数词（"attempt 1"）**保持命中**——不许为它开洞（#159 的边界）。
模块 docstring 的豁免清单同步。

### C. render blocked 状态列与分组（#160；verdict v1-router-1）

querycmd `_run_render_blocked`：表加 `status` 列；status=answered 的行改按
`from_layer` 分组（欠 close 的一方），open 行仍按 `to_layer` 分组。既有
render 测试同步改断言。

### D. routes.json 命令拆列（#160；verdict v1-router-2）

kind=command 的行新增 `"cmd"` 字段，只装可粘贴执行的命令尾巴
（如 `"ledger.py render blocked"`、`"doctor.py"`、
`"ledger.py status --layer <本层>"`）；`to` 列保留原散文。撤销/打回两行
（12/13）没有单条命令，`cmd` 置 null 并在行内 `_note` 说明"多步程序，
见 to 列指向的规则"。spec_lint 如对 routes 结构有断言需同步。
router SKILL.md 的文字归 T20。

### E. 表注五处（照裁决与 verdict 原文）

rows.json：
1. `runs_row_normal._dup_rule`：补 #158 两段式重试纪律原文（未入账同
   run_id 改单重发合法走 RUNMETA attempts；失败入账后获准重试 = 新
   run_id 新发射单，decision_refs 带裁决，旧失败行留账）。
2. `launch_order.properties.resources._note`：无集群工程的空值形态是
   `{}`（字段 required、不可 null——verdict v2-hop1-1）。
3. `jobs_min_additions`：escalation_ref 存最新一条升级的 blocked_id，
   升级历史在 blocked 账本身（#161 尾句；verdict v2-hop4-3）。
4. `status_view.pending_launch_orders._note`：补半句"获准重试的新单
   自然落入本字段（#158）"。
5. `status_view.batches_pending_report._note`：补"失败/空产物 run 的
   批次同样欠报告——报告解释失败也是报告（verdict v2-hop3-4 按此定）"。
6. `decisions_row.scope._note`：补授权覆盖判定（verdict v1-idea-1 的表侧；
   判定文本与 T20 将写进 r5-choices.md 的一致）：fork 触及的文件/产物
   全部落在 scope.path_globs 内，且 scope.desc 的用途白话明白涵盖该
   fork 的主题，两条同时成立才算覆盖；拿不准即不覆盖，走开条。

## 测试（各行为改动配"修前红修后绿"的测试）

1. A：预置带 escalation_ref/sampler_verdict 的 jobs 条目 → 同 run_id 重发
   → 两键仍在且 state/log_path 更新。
2. B：oversight-3 的五个误火形状（`## 2.` 标题、`(§1)`、`> ` 带数字摘录行、
   `python3`、`$ ` 续行）各一测试过 lint；非回归：`row count: 5` 裸行仍
   命中、"attempt 1" 仍命中。
3. C：answered 行出现在 from_layer 组且带 status 列；open 行仍在 to_layer 组。
4. D/E：spec_lint + gen-schemas --check 双绿。

## Comments
- 2026-08-14 wave9 收账：DONE，1 轮 0 修复，commit 范围 5926300..7fa9d1c，merge 进
  main。主仓复跑 319/319 + gen-schemas --check + spec_lint 三绿。首次发射的实现者
  在建工作树一步调 EnterWorktree 工具吊死 6 小时，TaskStop 后在 wave.js 派发消息里
  禁掉该工具重发成功（skill 修复 commit 5926300）。四条 concerns 裁决：① 工单 E 节
  标题"五处"实列六条，按内容为准，认可；② grant/feedback review 两行 cmd 的占位参数
  经主会话对照两个子命令的 argparse 实核（--layer/--question/--reason 与
  --layer/--ref/--verdict 均必填），认可；③ routes 表头新增 _cmd 说明字段是仿 _kind
  先例的合理延伸，纯下划线说明字段不进 schema，保留（评审 minor F1 同此裁决）；
  ④ 工单"12/13 行"行号对不上，实现者按语义定位撤销/打回两行，认可。
  cannotVerify 四条：前三条按范围声明归 T20 核（router SKILL.md 文字、r5-choices.md
  判定文本、report-genre.md 体裁半条）；第四条（测试输出采信报告）已由主仓复跑覆盖。
