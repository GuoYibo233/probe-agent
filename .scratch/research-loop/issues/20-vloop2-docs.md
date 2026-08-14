# T20 §V 第二轮修复：skill 文档面（重试纪律 / 字段枚举补漏 / 判据成文）

Status: ready-for-agent
Blocked by: 19

## 范围声明

research-loop plugin 件，只动 `research-loop/skills/**`；不改代码不改表
（表侧已由 T19 落完）。英文。需求源：本工单 +
`sdd/vloop-round2-verdict.json`（confirmed 全文，本工单覆盖其中文档面）+
`audit-merge.md` 自决点 #158–161。**写文档前先读 T19 的 commit diff 与
工单 Comments，教的必须是 T19 落地后的行为。** 交付前 spec_lint +
gen-schemas --check + 全量 run_all 三绿（应零变化）+ 每条点名 finding
在文档里能指到落点（评审逐条对）。

## 要求（编号对 verdict json 的 finding id）

**#158 重试纪律成文（v2-hop4-1 / v2-hop3-3，blocker）**：
- run-layer `execute.md` "Recording" 与 `failures.md` "Consuming the
  answer"：两段式纪律——未入账的 run 可同 run_id 改单重发（RUNMETA
  attempts 递增）；失败**已入账**后，获准的重试是新发射单（新 run_id 取
  命名规则下一序号、decision_refs 带裁决 decision、全新 artifact_dir），
  旧失败行留账为实。写明 record.py 对旧 run_id 的拒绝（run 级不一致 /
  同主键）是设计围栏不是 bug。
- deploy-layer `failures-inbound.md` 裁决段：ruling=retry 时按上述两段式
  开新单；新单自然出现在 pending_launch_orders（run 层由此接活）。

**router（v1-router-1/2 + #160）**：`research-loop/SKILL.md` "How to read
the table"——kind=command 行执行 `cmd` 字段原文（T19 已拆列）；`to` 列是
散文说明不含可执行部分；`render blocked` 输出里 answered 行按 from_layer
分组、带 status 列，谁欠什么一句话说清。

**授权覆盖判定（v1-idea-1 + v2-hop3-2）**：`r5-choices.md` "Which mode
applies" 与 idea `answering.md` 自决段，写同一段判定文本（与 T19 落在
decisions_row.scope._note 的一致）：fork 触及的文件/产物全部落在
scope.path_globs 内 + scope.desc 用途白话明白涵盖 fork 主题，两条同时
成立才算覆盖；拿不准即不覆盖，走开条。`--where` 的取值择一律
（v2-hop3-2）：优先 spec item，其次工单，最后文件路径——取最能让读者
grep 回需求源的那个。

**status 字段枚举补漏（v1-deploy-2 / v1-run-5 / v1-oversight-5 /
v2-hop7-1 / v2-hop8-3）**：deploy / run / oversight 三份 SKILL.md §2 补
`pending_user_decisions` 的归属句（与 idea §2 既有措辞对齐：属待决队列块，
任何层都会看到，转给用户会话处理）；顺带 v1-oversight-4 的冒号句式修通。

**inconsistencies 附注块的处置（v2-hop6-7 / v2-hop7-2）**：deploy 与
oversight 两份 SKILL.md §6 各补一行"annex 非空时"的 stage 行——deploy 指
`failures-inbound.md` 新增小节（核对 code 对应的账并修数据源，修不动的
开条升级），oversight 指 `inspection.md` 新增小节（inconsistencies 是
观察线索，按需转 on-demand observation 报告；doctor 在哪一步跑写清）。

**run 层预检拒发的三处收尾（v1-run-1/3 + v2-hop4-6）**：`execute.md`
"After it lands" 补镜像豁免句（拒发的 launch 不跑 output_check——它必然
missing-output 且无意义）；line 48 一带补"分类步骤不适用于预检拒发"
（error_classify 的三类输入都不存在，--exit-code 不填发射器退出码）；
`failures.md` "Classify first" 开头补同一限定。

**error_classes 零表状态成文（v1-run-4 + v2-hop2-2）**：`failures.md` 与
`failures-inbound.md`——缺表时 error_classify 出 unknown + stderr 提示是
安全缺省不是故障；表由 deploy 按 failures-inbound.md 的字段契约首建；
unknown 走升级不走猜。

**oversight 材料绑定与派发两端（v1-deploy-6 + v1-oversight-1/2）**：
`closeout.md` Step 1 把 `<inspection material>` 显式绑定为批次报告路径
`plans/<batch_id>.md`（派发契约三件之一）；`inspection.md` 对应接收端同句
绑定；v1-oversight-2 点名的裸路径改成 `<root>` 前缀形。

**report-genre 三处（#159 文档半 + v2-hop6-2/3/4/5/6）**：`$ ` 行禁管道、
无 shell 执行（`<`/`>` 会成为字面 argv）、反斜杠续行受保护；带空格序数词
（"attempt 1"）会被判数字主张，改写成文字序数或挂 id；`> ` 摘录行已豁免
数字扫描（引用不是主张）；三种报告体裁（例行核查 / on-demand observation /
判据验收）各自的触发条件一句一个。

**jobs 直读口径（v2-hop6-1）**：oversight `inspection.md` 补一句——
ops/jobs.json 是 json 台账不是 jsonl 账本，不在 query-only 读类内，按路径
直读合法（statuscmd 自己就这么读）；派 reader 是为省上下文不是权限要求。

**其余逐条**（各一两句，落点照 verdict fix_locus）：
- v1-run-6 / waiting_on 成员规则：run SKILL.md §2 一句（成员=两类：
  pending_user_decisions 逐条 + batches_pending_inspection 逐条，action
  取 routes 表原文）。
- v2-hop1-2：launch-orders.md "Sourcing expected_outputs" 补
  `required_keys: []` = 只承诺行数/字节、无键级契约。
- v2-hop2-1：execute.md 拒发/退出码段补"发射器透传子进程退出码——exit
  2/3 之外的非零值是实验自己的失败码"。
- v2-hop5-2：closeout.md 写批次报告的门槛句——批次的每个 run 在 jobs 台账
  到终态且 runs 账有行（含失败行）才动笔；报告解释失败也是报告。
- v2-hop5-3：failures-inbound.md 升级目标判据——方向/解释/原则缺口 →
  --to-layer idea；要花用户的权（资源、范围、许可证、外部访问）→
  --to-layer user；工具/账本能力缺口 → feedback add（R9）留案 + 若当下
  卡死另开条给 idea。
- v2-hop5-4：failures-inbound.md 把 "R8" 引注展开成一句白话（新错误类
  规则由 deploy 提议、写表、留 decision 痕）。
- v2-hop5-5 / v2-hop7-3：deploy SKILL.md §3 或 launch-orders.md 补工单
  Status 词表指针（非终态 = 除 resolved/wontfix 外；statuscmd 按此推导
  open_issues）。
- v2-hop7-4：closeout.md Step 0 的 "§8 step 5" 引注改成自足白话（先报告
  后核查再收官的次序），不引 plugin 外的 spec 章节号。
- v2-hop8-2：idea SKILL.md §4 五条转录路径逐条给落点（ruling→story/
  blocked answer、authorization→grant、revocation→withdraw 体裁、
  trigger→routes 表、send-back→rejections[]），一条一个指向。
- v2-hop8-4：idea SKILL.md §2 工作面七字段一句话分"本层动手"与"只旁观"。

## 测试

文档工单不加代码测试；交付门 = 三绿 + 逐条 finding 落点可指。

## Comments
