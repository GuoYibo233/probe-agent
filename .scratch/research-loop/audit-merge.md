# 四份隔离审核归并 + spec 修订提案（待用户裁决，spec 未动）

2026-08-13。四个上下文隔离的 opus 审核员（idea 层 / 部署层 / 运行层 / 监察面）
各自只拿到本层按设计应见的材料，禁止读仓库文件。四份原始报告很长，这里是归并；
**档位是我的建议，采纳与否由你逐条裁决**：
P0 = 不补则某条链路死锁或静默出错；P1 = 不补则跨会话要靠猜；P2 = 先记账后置（YAGNI）。

## A 信道断链类

| # | 缺口 | 谁命中 | 修法提案 | 档位 |
|---|---|---|---|---|
| A1 | BLOCKED/升级上报没有落盘形态、没人保证被读到、答复没有回写责任人——双向死锁点 | idea+部署+运行 三杀 | 新增**待决账 `blocked.jsonl`**（状态机 open/answered/closed）：BLOCKED 上报、故障升级单、答复回执全是它的条目；下层写 open，上层写 answered，发起层确认 closed。"未决事项清单"= 它的渲染视图，你回来一眼看到有几件事挂着 | P0 |
| A2 | 原则条目无稳定编号、无 scope、无版本——"spec 指回原则"机验不了，"原则覆盖没覆盖"判不了 | idea+部署 双杀 | 原则条目加 `principle_id`、`scope`（管哪些文件/阶段/动作）；原则文档带修订号；spec 记 `approved_against_principles_version` | P0 |
| A3 | 判据实测写回撞写权：结果要更新原则文档（idea 层写权），跑判据的是部署层——链子中间断着 | idea+部署 双杀 | 判据每跑一次就是一次 run，进 runs.jsonl 带 `principle_id` 字段；原则文档三件套第三件（最近实测+日期）改由渲染脚本从 runs.jsonl 自动填（R7：渲染产物不手改）。不新开账本 | P0 |
| A4 | **发射单体裁完全未定义**——运行层的唯一驱动输入没有字段，六处隔离漏洞全由此起 | 运行 | 新体裁 `launch_orders/<run_id>.json`（部署层写、运行层只读）。必填：run_id、spec_ref、issue_ref、registry_task、argv、env_name、workdir、expected_commit、resources、expected_runtime_s、depends_on、**expected_outputs（path_glob+min_bytes/min_lines）**、metrics_cmd、smoke_cmd、retry 策略、mutable_params 白名单、artifact_dir。new1 挂接：gpu-run 的 launch 已实现大半，补字段即可 | P0 |
| A5 | spec 自身体裁未定义：验收标准、依赖、优先级、批准状态都没字段，新会话拆不出可复现工单 | idea+部署 双杀 | spec 条目定字段：id、指回 principle_id、acceptance、depends_on、priority/droppable、（文件头）approved_by+approved_date+原则版本 | P0 |
| A6 | run → 工单反向断链：从一次 run 追不回"为什么跑" | 监察+运行 双杀 | 发射单带 spec_ref/issue_ref；RUNMETA 加 launch_order_ref；台账加回指字段。正向链已存在，补反向三个字段 | P1 |
| A7 | 抉择账无下游指针、无 scope、无 status、时间只到日——"D003 影响了哪些结果"无解，"授权管一次还是管一类"靠猜 | 监察+部署+idea 三杀 | 抉择账补：status(open/decided/withdrawn)、scope、principle_ref、affects(spec条目/工单/run_id)、raised_at 秒级、where 限定取值域（路径/工单号） | P0 |

## B 静默失败类

| # | 缺口 | 谁命中 | 修法提案 | 档位 |
|---|---|---|---|---|
| B1 | **退出码 0 + 空输出 = 静默成功**，空数字进账一路污染到 idea 层 | 运行 | 发射单 expected_outputs + 注册表内确定性校验脚本，结果进台账；"重跑一次仍空即升级"写死 | P0 |
| B2 | runs.jsonl schema 未定义、无版本——跨层解析无契约，运行层改字段名下游脚本静默坏 | idea+运行+监察 三杀 | `schemas/runs.schema.json`：**定义权部署层、写权运行层**，写入前脚本校验；行内至少 run_id、status、output_dir、metric_name、n(分母)、filter、seed、dataset_version、batch_id/arm、principle_id(判据用)、schema_version | P0 |
| B3 | 原始输出→数字的加工归属不明：运行层被逼做判断，或部署层算了写不进账 | 运行 | 明写：抽数脚本部署层写、挂注册表，发射单带 metrics_cmd，运行层只跑它并把结构化输出原样入账；**禁令：任何层禁止用眼睛读日志填数** | P0 |
| B4 | 错误分类（自愈还是升级）需要判断力，运行层却是机械层 | 运行 | 落盘错误分类规则表（错误特征→自愈动作/直接升级）+分类脚本；采样器"卡死"阈值进配置。new1 挂接：sampler/verdicts 已有实现，规则表成文即可 | P1 |
| B5 | 脏树 vs "发射前必须 commit" 权限打架：运行层无代码写权 | 运行 | 裁决成文：脏树一律拒发并升级部署层，台账/锁文件豁免清单写进配置（new1 已这么干，`--allow-dirty` 是逃生口），契约里成文 | P1 |
| B6 | 集群慢变量档案（驱动/坏卡/坑）不属于任何层，教训跨会话就丢 | 运行 | 写权划给运行层，配置加 cluster_state_file 键。new1 挂接：就是 ops/gpu_state.md，归队即可 | P1 |

## C 监察可核性类（防"AI 编造"，全部服务你亲验）

| # | 缺口 | 谁命中 | 修法提案 | 档位 |
|---|---|---|---|---|
| C1 | **计数不可核**：报告说"出现 137 次"，你没法复查；lint 只防结论词、不防编造 | 监察 | R3 升级：**每个数字必须配一条可直接粘贴执行的复现命令**，命令输出必须等于报告数字；lint 加规则"有数字无命令=报错"；另加机械校验器：路径逐个 stat、摘录逐字回比、命令数值回比 | P0 |
| C2 | 报告无溯源块、快照口径不定：过一周复查对不上，分不清数据变了还是报告错了 | 监察 | 报告头强制：生成时间、git HEAD、所读账本行数/哈希；计数为 0 的否定性陈述必须附扫描范围全量清单；差异定位两侧各带路径+行号 | P1 |
| C3 | 产物格式字典缺失：观察报告只能靠读代码反推字段含义，反推本身是判断，越了监察面的界 | 监察+idea 双杀 | RUNMETA 加 outputs 字段字典（file/format/fields 含义），由写文件的代码自动生成 | P1 |
| C4 | 抽样总体没有指纹：种子固定管不了"池子是哪个"，选择性抽样防不住 | 监察 | spotcheck.py 落盘总体指纹（文件清单+行数/哈希+种子+N+算法版本） | P1 |
| C5 | 账本注册表缺失：每次追溯先满仓库找账；ledger 目录无写权分区，越权写机验不了 | 监察+部署 双杀 | research-loop.json 枚举全部账本路径+写权层映射；越权写入可脚本机验 | P1 |
| C6 | reports/ 无命名约定、无通知：报告躺在目录里=没送到 | 监察 | 命名带日期主题；会话出口强制回报"绝对路径+三行摘要"；进 git（监察写权限定 reports/ 路径） | P2 |

## D 人的接口与 idea 层账本类

| # | 缺口 | 谁命中 | 修法提案 | 档位 |
|---|---|---|---|---|
| D1 | 故事账表达不了对照与挑选：baseline 是谁、从几个候选里挑的、挑选规则——"挑最好一次"和"只跑过一次"落账后长一样 | idea | 故事账补：baseline_runs、candidate_runs、selection_rule、derivation_command、principle_id、retired_reason/retired_date/superseded_by、status 取值域；写入脚本加"被引 run 必须 status=ok"校验 | P0 |
| D2 | 新结果推翻旧 claim 账上没动静（反证/回归无信道） | idea | 冲突检查脚本：新批次入账时对照故事账 active claim 的 evidence_runs 同口径重比，飘了列清单报你（只报事实不判） | P1 |
| D3 | 下行缺"撤销/更正"体裁：拍板收回无处落 | idea | 账本一律 status 变更+superseded_by（脚本代笔），原则文档加【已撤销】标注 | P1 |
| D4 | 下行缺"临时指令"（先试一下回来再定）、"补证请求"；上行缺"设定差异声明" | idea | 补证请求=对监察面的路由句（不新增体裁）；临时指令=spec 的 exploratory 标记；设定差异声明并进 C1 报告体裁 | P2 |
| D5 | 实验设定账/数据集清单账缺失：新实验"跑多大、什么数据、什么种子"无账承载 | 部署 | 单次设定由发射单承载（A4 已含 seed/dataset 字段）；数据集清单=DATA.md 加结构化表头（dataset_id/路径/生成 commit/行数/校验和/当前版）。不新开账 | P1 |
| D6 | 可行性成本无账可查（试一次几张卡几小时） | idea | 台账补 elapsed/gpu_count（运行层落，机械） | P2 |
| D7 | 授权原话落账的写权矛盾：authorized_by 在部署层账里，idea 层写不了也验不了转写忠实 | idea+部署 双杀 | 授权时主会话当场用脚本落账（decisions.py 是注册表命令，谁的会话都能跑，写的是部署层的账但由脚本代笔+schema 校验；账本写权指"哪层的账"，脚本入口不分层）——此条为定义澄清，进 spec §5 | P1 |

## 修订落点

P0 共 11 条（A1-A5、A7、B1-B3、C1、D1；此前误记 10），全部是"不补则死锁或静默出错"。
落点：§2 信道（+待决账）、§4 组件（+launch_order 体裁、+机械校验器、+冲突检查、脚本清单重排）、
§5 schema（原则条目/spec/故事账/抉择账/runs/发射单六个 schema 全部成文）、§7 配置（账本注册表+写权映射）。
P1 共 11 条，P2 共 4 条——P2 建议只在 spec §10 记一笔"后置"，不实施。

四份原始报告全文备查：会话任务输出目录（需要的话我把四份拷进 .scratch/research-loop/audits/）。

## 本轮自决点（用户授权"你先自己更新"，按 R6 留痕，逐条可推翻）

1. **判据实测走 runs.jsonl 不新开账**：两份报告提案不同（idea 层报告提 runs.jsonl 加
   principle_id，部署层报告提新开判据实测账），我选前者——少一本账，且"实测不手填、
   渲染回填"顺带满足 R7。
2. **授权落账的写权矛盾用"定义澄清"解**：写权指账本内容归属层，脚本入口不分层，
   idea 层会话可当场跑脚本写抉择账。没有给 idea 层开写权，也没做转写校验机制。
3. **账本脚本合并成 ledger.py 一个入口**（story/decisions/blocked/feedback 四本账做成
   子命令），照顾"不要太多太杂"；单一职责靠子命令边界保持。
4. **P2 四条全部后置**：reports 通知信道、临时指令/补证请求专用体裁、成本查询视图、
   只读性钩子验证。理由各自写在 §10。
5. **发射单字段收录了运行层报告的主干**，裁掉两个：allow_bigger_card（并进
   retry.allow_card_swap 的语义）、attempt 间工作树不变的要求（由"脏树拒发"覆盖）。

## 第二轮自决点（两份验收审核 → 修订二，按 R6 留痕，逐条可推翻）

6. **R7 与 R1 的打架用"两条注册表路"解**：runs.jsonl 数字来源 = metrics_cmd（普通实验）
   或 criterion_cmd（判据 run），不强求判据也开发射单；R7 的排他范围限定在 runs.jsonl，
   派生量归 R4/故事账。
7. **预授权做成抉择账的 kind=grant**，不新开授权账；scope 结构化（desc/path_globs/
   expires_at）；"开工必读"从待决队列一样扩成两样（+有效授权视图）。
8. **R5 裁决强制同步进抉择账**（ledger.py 自动生成 decision 条目），堵"裁决只活在
   blocked.answer 自由文本"的洞；抉择→run 的出边 = 发射单 decision_refs + affects 可追加。
9. **写权例外成文两个**（blocked=per-transition、feedback=shared-append），owners 用
   规则名不用层名；"唯一的双向账"说法删除。
10. **regression_check 从 idea 层改归 oversight**（只读账本、清单落 reports/），
    解写权冲突。
11. **"零冲突"承诺改述为"不改流程、增量字段单列挂接清单"**（三项：发射器回指字段、
    record.py 挂 schema 校验、RUNMETA outputs 字典）——审核员判得对，补字段就是改代码，
    原承诺字面不成立。
12. **RUNMETA 落点定为 artifact_dir 根下 RUNMETA.json** + runs.jsonl 加 runmeta_path
    回指；ledgers 补 specs/issues/timeline/literature/batch_reports/codemap 六键。

## 第三轮自决点（复验 10 硬伤 → 修订三，按 R6 留痕）

13. **判据 run 定为 runs.jsonl 缩减行**（principle_id 非空即是；必填七字段其余可空；
    run_id 前缀 chk-，由 ledger.py 分配——这是"run_id 由部署层给定"的唯一成文例外），
    不给判据开发射单。
14. **跃迁写权定位为防呆不防伪**：ledger.py 一切写入必带 --layer 自报；冒报不在
    威胁模型内。to_layer=user 的 answered 用字段级检查（answered_by=user）替层检查。
15. **R5 同步用结构化字段机械拼**：blocked 加 kind 与 where/options（r5-choice 必填），
    answer 必传 --chosen，杜绝脚本解析自由文本。
16. **affects 回填触发者定为"写发射单的同一动作"**；decision_refs 权威、affects 是索引。
17. **owners 值域收成六个**；ledgers 允许路径模板；registry_query 改成命令形态、
    真实取值进挂接清单第 5 项待核实。

## 第四轮自决点（终验 8 硬伤 → 修订四，按 R6 留痕）

终验报告判定：上轮 10 条里 5 条干净解决，4 条解法带出新矛盾，共余 8 个硬伤，
全部集中在判据 run 缩减行的落地、写权/键集合的同步、以及 shared-append 的机验上。
逐条修法与自决：

18. **runs.jsonl 定为双写入口，按行型分工**：普通行走工程记账脚本（record.py）、
    判据缩减行走 ledger.py runs-append，两入口同一 schema 共用文件锁；§4 的
    "不替代工程记账入口"限定于普通行。ledger.py 职责表补三件：发射单写入、
    runs-append、init。挂接清单②扩注（record.py 锁协议兼容需核实）。
19. **判据 run 执行契约成文**：部署层会话当场执行 criterion_cmd（注册表命令自带
    解释器与环境）；定位轻量只读——不占 GPU、不过脏树门禁、不登台账、不写 RUNMETA；
    缩减行加必填 commit（runs-append 自动抓 git HEAD，脏树 -dirty 后缀）补溯源；
    **要占 GPU 的判据不算缩减行**，开正式发射单按普通 run 走。
20. **缩减行判定式收紧 + trace_check 豁免**：缩减行 = principle_id 非空且
    runmeta_path 为 null；这类行豁免 run→发射单→工单反向链，改验 principle_id
    在原则文档、criterion_cmd 在注册表；带 RUNMETA 的判据 run 照常走反向链。
21. **抽数输出契约统一成文**：metrics_cmd 与 criterion_cmd 的 stdout 最后一行必须是
    单个 JSON 对象（字段各自成文）；解析失败=入账拒绝并按 R8 升级。
22. **监察面写权改述**：对各层账本零写权，落盘=reports/ + 按两个成文例外参与共享账
    （blocked 开条提问、feedback 追加建议）——消掉"唯一写权 reports/"与枚举含
    oversight 的互斥。
23. **反馈账审查改成追加 review 行**：feedback.jsonl 两种行型（suggestion/review），
    有效状态=最新 review 行、无则 pending；不再改写 status 字段，shared-append
    的"只放行 append"机验成立。
24. **r5-choice 拼装映射规则成文**：reason=answer 原文、decided_by 按 answered_by 推、
    authorized_by=用户原话或 grant:<grant_ref>；blocked 加 grant_ref 字段，
    answered_by≠user 的 r5-choice 必传 --grant 否则拒（R6 机验落点）。
25. **配置键集合对齐**：schemas 目录进 ledgers（删顶层 schemas_dir 键），owners 键集合
    与 ledgers 严格相等由配置校验器查；§1 部署层写权格补 schema 目录与数据集清单。
26. **无配置文件语义收紧**：记账也不可用（路径全来自 ledgers），只有谈可用；
    接线第一步 = ledger.py init 出配置骨架。

## 第五轮自决点（复验 5 硬伤 → 修订五，按 R6 留痕）

第四轮复验判定：8 处修法中 4 处干净解决，余 5 个硬伤，根子有二——
"GPU 判据走普通行"的分支撑不住（三处字段契约互斥、日期无来源）、
两处 --layer 取值无人接（runs-append、用户审查会话）。修法与自决：

27. **砍掉 GPU 判据分支**：判据一律轻量只读（R1 硬约束：不占 GPU、部署层会话
    当场可跑）；要重算力的证据先按普通 run 跑出产物，criterion_cmd 吃产物路径
    做检查（缩减行 output_dir 可指向产物内证据文件）。这正是 METHOD.md 里
    R3 判据的实际做法（判据本体是对已有 run 产物的 CPU 检查）。
    判定式复原为 principle_id 非空 ⇔ 缩减行；trace_check 豁免同步简化。
    连带消掉：普通行 principle_id 必空 vs 照填的互斥、发射单无 criterion_cmd
    槽位、GPU 判据日期无来源（#2、#3 一并落地）。
28. **runs.jsonl 升为 §1 第三个成文写权例外**（per-row-type）：普通行归 run 层
    经工程记账脚本、缩减行归 deploy 层经 runs-append；owners 值域扩成七个，
    per-row-type 的机验 = runs-append 只收 --layer deploy。监察面条目改引
    "前两个例外"。
29. **失败判据不落行**：runs-append 只在退出码 0 且尾行 JSON 解析成功时落行
    （status=ok）；其余不落行按 R8 升级——判据没跑成不算实测，"最近实测"不更新。
    消掉 value 必填/可空/拒入账三方互斥。备选是落 failed 行记录失败史，
    弃：schema 要开二套必填规则，失败史在 blocked 账里已有。
30. **feedback review 行补 layer=user**：--layer 合法值加第五个 user，只有
    feedback review 子命令收；"条目 layer 自证"对两种行型都成立。
31. **inspector agent 与监察会话的写权分工写进 §4 注释**：共享账两条口子归
    监察会话，agent 仍限定 reports/（上轮复验的非阻塞注，顺手成文）。
    §9 补 feedback 与 runs-append 两组用例。

## 收敛记录（第五轮复验 → 全绿）

第五轮复验判定：5 处修法 4 处干净解决，仅余 1 个硬伤——两处旧口径残留
（§2 总规矩"两个成文例外"未跟上第三例外、§5 runs.jsonl 段头仍写"写权运行层"），
已就地修掉并 grep 确认无其他残留。五轮合计：4 份分层隔离审核 + 2 份验收审核 +
3 份终验复核，修订一至五，自决点 1-31。

32. **成文留白一处（复验判定非硬伤，留给实施）**：判据 evidence_path 指向
    空文件时算什么，spec 未规定——实施 runs-append 时定（建议按 R8 的
    "输出仍空必升级"精神处理），不回改 spec。
