# T18 §V 第一轮修复：skill 文档面（三块承重新参考 + 全部措辞修）

Status: ready-for-agent
Blocked by: 17

## 范围声明

research-loop plugin 件，只动 `research-loop/skills/**` 与本工单点名的表
`_note` 文本；不改代码。英文。需求源：本工单 +
`sdd/vloop-round1-verdict.json`（confirmed 全文，本工单覆盖其中文档面）+
`audit-merge.md` 自决点 #151–157。**T17 已落地新 CLI 契约（decision
--blocked-ref、answer --decision-ref、legal_to、jobs 键名、error_classify
兜底、expected_outputs 非空、story baseline 可空、routes kind 列、run_id
缺省命名）——写文档前先读 T17 的 commit diff 与工单 Comments，教的必须是
落地后的行为，不是第一轮跑出来的旧行为。** 交付前 spec_lint 绿（若表文本
动了）+ 全量测试不破。

## 文件

- Create: `research-loop/skills/idea-layer/references/answering.md`
- Create: `research-loop/skills/deploy-layer/references/failures-inbound.md`
- Create: `research-loop/skills/oversight/references/regression.md`
- Modify: 五份 SKILL.md 与既有 references/*.md（逐条清单见下）

## 要求

新参考文件三件（各配 SKILL.md §6/stage 索引一行 + 必要交叉引用）：

1. **idea-layer answering.md**（verdict v1-idea-1，blocker）：idea 层如何
   处理 status 里 to_layer=idea 的 open 条——读行、裁决体裁、
   `blocked answer … --layer idea` 的完整形态（r5-choice 行答复即机械拼
   decision；非 r5 行引用授权走 T17 的两步路，转录用户裁决则平答）、
   answered 后由 from_layer 消化并 close 的生命周期。
2. **deploy-layer failures-inbound.md**（verdict v1-deploy-1 / v2-hop3-2/3，
   blocker）：kind=failure 升级条的处理规程——读 evidence 日志原文、跑
   error_classify（含缺表时的 unknown 兜底行为）、`ops/error_classes.json`
   的字段契约与首次起表方法（照 T17 后的 rows.json error_classes）、
   裁决分岔（重试/改单/上升）按 r5 纪律、R6 留痕走两步路、答复与收尾
   （blocked close 由 from_layer 做）。r5-choices.md 里"答复即机械拼
   decision"那句限定到 kind=r5-choice 并链到本文件。
3. **oversight regression.md**（verdict v1-oversight-5，blocker）：
   regression_check 的职责、调用形态、输出读法、与批次核查的先后关系；
   oversight SKILL.md §6 补行。

既有文件逐条修（编号对 verdict json 的 finding id）：

- v1-router-1/2：research-loop/SKILL.md "How to read the table" 补两句——
  CLI 目标的统一调用形 `python3 <plugin-root>/scripts/<file>` / ledger.py
  子命令；`kind` 列（T17 已加）两类目标各自怎么处置（handoff=移交层身份，
  command=当场执行不换层）。
- v1-idea-2/3：story.md 补单臂主张写法（baseline_runs 可空的语义）+
  principle_id 进 walk-through 清单。
- v1-deploy-4：closeout.md 或新节补"写批次报告"步骤（plans/<batch_id>.md、
  frontmatter 按 rows.json batch_report_header、写完才轮到核查）。
- v1-run-2/3/4/5 + v2-hop2-1/2/4/6 + v2-hop4-2/3：execute.md 重写发射与
  记账两节——fallback 发射器自己写 jobs 基条（键名列全）；run 层对
  ops/jobs.json 的直接编辑权（SKILL.md §3 成文，对齐 deploy §3 句式）；
  两个必加键的名字与取值（照 T17 后的 jobs_min_additions）；预检被拒 →
  不写 jobs、不落 runs 行、拒绝 stderr 原文存档进升级条 evidence；发射器
  的全部拒绝类别列举（脏树 / expected_commit 不符 / 无效 --project-root）；
  "脏"的定义含未跟踪未忽略文件；fallback 铁轨 sampler 映射
  done/failed→ok、timeout→stall。
- v1-run-6 + v2-hop1-3：execute.md"After it lands"与 launch-orders.md 写清
  expected_outputs 从哪来（issue/spec 的产物承诺）+ 空清单被拒（T17 行为）。
- v2-hop1-1/2/4/5/6：launch-orders.md 补 run_id 缺省命名（照 T17 note）、
  created_at 是 naive 本地时间与账本同钟、decision_refs 在机械改单时填什么、
  draft 文件格式（launch_order 行形 JSON）与用后即删（正本在
  ops/launch_orders/）；rows.json 里 batch_id/env_name/workdir/artifact_dir/
  smoke_cmd 及两处 "..." 占位 `_note` 填实文。
- v2-hop3-4/5：launch-orders.md 草稿去向（同上）；四份层 SKILL.md 各补一句
  rails.* 空键先跑 config-check 看锁面（含 deploy §6 无 ticket 行的说明——
  rails.build 未接线时 ticket 面锁住）。
- v2-hop4-1：execute.md 说明发射器失败时子进程输出全在
  attempt<N>.log（stdout 无回显）、同单重发是重新执行并追加 attempt。
- v2-hop4-4：execute.md 一句话钉 output_check verdict {ok, missing-output,
  empty-output} 与 record --status {ok, failed, empty-output, timeout} 的
  对应关系。
- v2-hop4-5：failures.md（run 层）补 answered 条消化后的 close 步骤；
  answering.md（idea）与 failures-inbound.md（deploy）同样带上 close。
- v2-hop5-1：四份层 SKILL.md 的"three read-only blocks"句后逐块点名 JSON
  字段（工作面=approved_specs_in_flight/open_issues/pending_launch_orders/
  running_runs/unrecorded_runs/batches_pending_report/batches_pending_inspection、
  队列=open_blocked/answered_blocked（+user 会话另有 pending_user_decisions）、
  授权=active_grants；waiting_on/inconsistencies 是附注块）。
- v2-hop5-2：idea SKILL.md 补 jsonl 账只经 `ledger.py query` 读的纪律句
  （query-only 读类是四账通例，不只监察面）。
- v1-oversight-4/6/7/8：inspection.md 补——报告消费方是 deploy 收官步
  （回填 plans 头 inspection_report 字段）；`ledger.py query runs --batch
  <batch_id>` 完整工作示例一枚；--spec-item 经发射单 spec_ref join 的说明；
  核查报告文件名约定 `reports/<batch_id>.md`。
- #154 文档半：report-genre.md 补"合规 id 形状豁免；不合规含数字标识符
  进 frontmatter 或配 `$ ` 行"。

## 测试

文档工单不加代码测试；交付门 = spec_lint 绿 + `gen-schemas --check` 绿 +
全量 run_all 不破 + 每条上表 finding 在文档里能指到落点（评审逐条对）。

## Comments
