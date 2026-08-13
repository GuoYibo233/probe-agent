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

## 用户批注合并（2026-08-13 → 修订六）

用户在 spec.md 正文里留 19 处批注，讨论一轮后定四项裁决：
①工单维持部署层开（idea 层产出原则与目标）；②账本行数上限进 research-loop.json
（`ledger_caps`，plugin 带默认值）；③部署收官例行核查 = 派 opus inspector 通读
（不只跑机验脚本）；④上下文卫生主次 = 读走脚本为主、归档为辅。

批注 → 落点对照：上下文一等对象（§0）；账本回收（新 §2.1）；三层职责细化 +
会话身份 + 跨层传输细则 + 悬案攒批上报（§1 层纪律）；读权走脚本（§1 + R7 扩展）；
部署收官核查 + 监察面记忆（§1 监察面条目 + §6 路由 + §8 步 10）；开工必读动态视图
（§2）；聊天自由落账定格 + 实验设定硬边界 + 上行不死板（§2.5）；原则条目加
applies_when/rationale（R1 + §5）；通用/特化两层 + 默认铁轨兜底 + init 问卷
（§4 + §7）；doctor（§4 + §6 + §9）；错误处理程序先 LLM 兜底（R8 + §8 + §9）；
路由动作可手动触发不限阶段（§6 表下注）；账本上限 ledger_caps（§7）；
集群慢变量档案回收（§5）。

## 第六轮自决点（批注合并中的实施细节，按 R6 留痕）

33. **归档文件不进 ledgers 注册表**：`<name>.archive.jsonl` 与主账同目录，
    是主账伴生物；读写只经 ledger.py。备选是登记进 ledgers——弃：owners 键集合
    与 ledgers 严格相等的机验会被"归档行保留原归属层"搅浑（归档动作是机械搬运，
    没有单一归属层可填）。
34. **runs.jsonl 默认不轮转**（ledger_caps.runs=null）：new1 渲染链（RESULTS.md）
    依赖全量行，且会话读数走渲染产物与查询口、不直读原文件。其余四本 jsonl
    默认上限 blocked 500 / decisions 1000 / feedback 500 / story 1000（拍脑袋量级，
    工程可覆盖；doctor 报体量，值不合适随时改配置）。
35. **读手 subagent 钉 sonnet**：非结构化材料摘要属机械活（全局 subagent 模型
    策略：机械用 sonnet）；结构化账本一律脚本直查，不派 LLM。
36. **error_classify 无命中输出 unknown**（已被自决点 44 取代：接手层限部署层及以上），由各层 SKILL.md 引导 agent 接手
    （读日志、给归类建议、提议加分类行）；脚本本身不猜。§9 用例同步改。
37. **部署收官核查定为部署层收官规程的一步**（SKILL.md 收官段写死），
    不做自动 hook——守住 §10"不做 hooks"的边界；手动触发口进路由表（"深查这批"）。
38. **`how_to_read` 落批次报告头部**：部署层向 idea 层交"怎么读这批结果"
    （读数脚本+口径说明）的落点，对应用户批注"把实验结果怎么读交给上一层"。
39. **默认铁轨兜底脚本**只做顺序执行+文件锁+append 三件事，不复刻 gpu-run/
    ticket-run 的任何高级功能——裸项目能用即可，长出设施后换指配置。

## 第七轮：修订六对抗审核（三份 opus：批注覆盖/机制一致性/隔离重放）→ 修订七

38 条发现（28 硬）。硬伤七簇与修法：

- **归档机制五处对撞**（append-only 机验、指针行撞 schema、--layer 无值、活跃行
  两套定义、追溯脚本不读归档）→ 归档指针改伴生索引文件、archive 不收 --layer
  改三条搬运机验、逐账活跃行判定式写死、校验/追溯脚本默认跨档读、并发锁协议成文。
- **收官核查无闭环**（派发无契约、报告无人接、inspector 开不了待决账、"通读"与
  读权禁令对撞）→ §1 三步闭环：派发契约成文、verdict 字段、blocker 由部署层
  转录 blocked 并阻断收官、批次报告 inspection_report 回指、监察面读法豁免成文。
- **查询口外延未定义** → §2.1 读法对照表（jsonl 走 query / md 定稿件可整读 /
  小 json 直读 / 大体量走切片或读手）。
- **运行层 unknown 兜底与"只跑不解释"对撞** → R8 分层：运行层只机械升级，
  归类归部署层。
- **"目标"无载体** → idea 层下行产出只有原则，"这轮做什么"由部署层拆进 spec。
- **信道 3 工单跨层** → 体裁删工单，注明工单是部署层层内物。
- **rationale 校验无人接 + METHOD.md 现状差距** → 新 principles-lint 子命令、
  原则文档机器可解析格式约定、挂接清单加第⑥项（METHOD.md 改造）。

soft 项处理：批注计数 17→19 两处改正；§2.5 开头句改"落账物只有固定体裁"；
doctor 落点成文（stdout/--out，regression_check 加 --dry-run）；md 整理归属改
用户/idea 层会话代笔；归档不自动跑记自决点并进 §10 后置；编号名字空间成文。

## 第七轮自决点（按 R6 留痕）

40. **归档指针改伴生索引**（`<name>.archive.idx.json`）：主文件零新行型——
    弃"指针行进主文件"（撞各账 kind 枚举与实体行必填字段，还得走一轮 schema 上桌）。
41. **archive 不收 --layer**：维护动作无归属层；写权检查换三条搬运机验
    （逐字节在归档、剩余为子序列、行数守恒）；shared-append/跃迁校验器开唯一豁免。
42. **活跃行判定式逐账写死**，query 与 archive 共用；被 decision_refs/affects/
    grant_ref/decision_ref/superseded_by 指向的抉择行永不归档。
43. **校验/追溯脚本默认跨档读**（等价 --include-archive）；只有 query 默认活跃视图。
44. **运行层 unknown 只机械升级**：用户批注 19"agent 帮忙判断"落在部署层
    （Claude Code 部署会话），与运行层"只跑不解释"两立；提议加分类行不开新 kind，
    走 kind=failure 升级 + 部署层答复时改表。
45. **监察面读法豁免成文**（"只读一切"的含义）；收官闭环 verdict/转录/阻断/回指
    四件套；转录 blocker 不算自查顶数（判定在 inspector 独立上下文）。
46. **doctor 只出 stdout（可选 --out）**；regression_check 加 --dry-run 供 doctor，
    避免越权写 oversight 独占的 reports/；代码/bug 检查沿用工程自检，doctor 只调用；
    worktree 清理动作归部署层。
47. **归档不自动跑**（用户原话"看看能不能自动进行"）：首期 doctor 建议 + 用户确认，
    自动执行（--auto）进 §10 后置不弃——理由：重写主文件的动作首期保守 +
    不做 hooks 的边界。
48. **md_size_caps 新配置键**（md 账字节上限，doctor 读）；cluster_state 默认
    64KiB，其余 null（拍脑袋量级，工程可覆盖）。
49. **兜底铁轨最低必做项** = 写 RUNMETA + 脏树检查 + 极简台账（修正自决点 39
    的"只做三件事"：溯源链在兜底态不打折）。
50. **R1 未接线态**：criterion_cmd 暂空必标【想法待定】，补判据才转
    【现状】/【已定要改】——顺带覆盖 METHOD.md 现有无判据条目的迁移路径。

## 第八轮：修订七复验（两份 opus：逐条复核 + 白手扫描）→ 修订八

复验判定：38 条中 35 条干净解决，3 条残留（§9 error_classify 用例没跟上 R8 分层、
读法对照漏 reports//schemas、挂接清单"五项"实列六项）；白手另揪 14 条新伤
（8 硬 6 软），全部是修订七自己带出来的：md 整理执行者两处互斥、runs 查询视图
无谓词、四色标注无列可放、兜底脚本无落点、抉择账"任何层落账"与 owners=deploy
打架、init 无合法 --layer、"唯一重写主文件"说过头、to_layer 填不出运行层归属、
md_size_caps 缺键行为、idx 无读者、trace_check 注释缺两职、§1 表头自称完整。
修订八 17 处全修。

## 第八轮自决点（按 R6 留痕）

51. **md 账整理归写权层会话**（TIMELINE→idea、集群档案→运行层；用户可亲自改）：
    推翻修订七"由用户或 idea 层代笔"——内容判断需要归属层知识，整理罕发，
    运行层偶做一次可承受；与 §5"写权层人工整理"两处并一处。
52. **query runs 必须带过滤**（--batch/--run/--since/--metric 至少其一），
    无过滤拒绝返回全表；runs 无活跃行概念，读全量走 RESULTS 渲染。
53. **原则文档加 status 列**（四色取值）：principles-lint 与撤销体裁都落这一列，
    "文档头标注四色"的旧表述废除。
54. **兜底件落地 `scripts/fallback/`**（registry.py/launch.py/record.py），
    §9 计数与验收同步；弃"归 §10 后置"备选——裸项目可用是通用层的卖点。
55. **抉择账升为第四成文例外**（owners 值 per-kind，值域八个）：kind=decision
    只收 deploy、kind=grant 任意层、r5 同步拼装不查——把"任何层会话经脚本落账"
    从与"一本账一个层"的矛盾里解出来。
56. **init 与渲染/回填动作不过 --layer 检查**：init 豁免条件=目标文件不存在或
    用户确认覆盖；渲染/回填不产生新内容只物化已入账数据。
57. **blocked to_layer 填法**：按问题归属向上取到最近可答复层（运行层问题填
    deploy），枚举不加 run 值——运行层没有答复职能，加值只会造死信。

## 第九轮：修订八复验 → 修订九

复验判定：17 项 16 净、1 残留（--metric 只在 runs 过滤句出现、两份维度清单没有）；
白手 11 新伤（6 硬 5 软）：archive"唯一重写"与状态跃迁就地改行打架、per-kind
堵死 idea 层 R6 自决入账、收官③ from_layer 无来源、"记账脚本"无配置键、
未接线拒绝无执行者、兜底 outputs 无来源；软伤：表头表体不齐、decisions 幽灵
open 态、grant 活跃口径不齐、rails 兜底无件、--metric。修订九 12 处全修。

## 第九轮自决点（按 R6 留痕）

58. **写入两式成文**：原子追加 + 成文字段级就地更新（blocked 跃迁字段、decisions
    affects/superseded_by、story 撤销字段），此外行内容不可变；archive 措辞收窄为
    "唯一允许把行搬出主文件的动作"。
59. **per-kind 补 R6 通道**：decided_by=agent 且 authorized_by 指向有效 grant 的
    decision 行收任意层——授权自决在哪层发生就在哪层落账（idea 层 R4 计算自决
    因此有入账路径）。
60. **收官③ from_layer=deploy**（转录者），溯源靠 evidence 指核查报告；弃
    "监察会话开条"备选——例行核查用的是 agent 形态，会话形态另属手动深查。
61. **decisions 删幽灵 open 态**：status 枚举收成 decided|withdrawn，
    未决态一律归待决账（R5）；活跃判定式 grant 分支补 status=decided 与
    §5 有效授权视图对齐。
62. **新配置键 record_cmd**（工程记账脚本入口；new1 = python3 run.py record）；
    "null 键对照"改用它表达 runs 普通行锁。
63. **config-check 成为 ledger.py 子命令**：每次写入/query 自动做，铁轨动作由
    SKILL.md 触发前跑；doctor 拼装的"配置校验"即此件。
64. **兜底态 RUNMETA.outputs 允许空**（监察面回落直接读产物）；rails.* 明文无
    兜底件，未接留 null 按锁功能处理。

## 第十轮：修订九复验 → 修订十

复验判定：12 项 10 净、2 残留（都是"主体已修、别处没跟着改"：§9 query 用例
仍列 decisions open 态；§4 fallback 注释仍说 rails.* 可指入）；白手 12 新伤
（4 硬 8 软，其中 2 硬与 2 残留同源）。硬伤：§9 decisions open 幽灵用例、
fallback/launch.py 无配置落点（§4↔§7 打脸且 §9 兜底自测无从跑）、判据缩减行
elapsed_s/退出码无来源（会话执行 vs 脚本入账断档，撞 R7）、ledger_caps 允许
给 runs 配上限但 runs 无归档判定式。软伤：§2.1 就地更新清单漏 status、
R6"收任意层"与监察面零写权打架、init 没有 config-check 豁免、registry_query
不进问卷与 null 对照、query runs --since 无时间字段可依、兜底 RUNMETA 三字段
无空值豁免、fallback/record.py 与"plugin 不替代入口"措辞打架。修订十 11 处全修
（2 残留并入同源硬伤）。

## 第十轮自决点（按 R6 留痕）

65. **R6 自决与 grant 代笔收窄为 idea|deploy|run 三层**（不含 oversight）：
    监察面零写权是更硬的约束，抉择不是它的职能；三处（§1/§5/§7）同口径。
66. **rails.gpu 有兜底件**：fallback/launch.py 的配置落点就是 rails.gpu；
    "无兜底件"限缩为 build/pipeline/paper/literature 四轨。取此而非"launch.py
    由 registry 间接进"，因为 §9 要求兜底态反向溯源链可跑，直指最短。
67. **判据执行与入账合一**：`ledger.py runs-append` 代拉起 criterion_cmd 并计时，
    退出码/elapsed_s/尾行解析全由脚本自取，会话只发起不经手数字（R7 闭环）。
68. **runs 行加必填 recorded_at**（ISO 秒级，两个入账脚本自动打，不许手填），
    `query --since` 按它过滤；弃"从 batch_id 反解日期"备选——依赖命名约定太脆。
69. **ledger_caps.runs 只许 null**（config-check 判非法）：runs 无活跃行判定式，
    归档在它身上无定义；渲染链依赖全量行。

## 第十一轮：修订十复验 → 修订十一

复验判定：12 项 11 净、1 残留（rails.gpu 兜底落点有了，但 rails.* 值域全文仍
只写"skill 名"，launch.py 这种脚本路径没有调用契约）；白手 3 硬 3 软，其中
白手 agent 实读了 new1 的 ops/record.py 与 runs.jsonl（主会话已复核属实）：
record.py 写的是 ev=start/finish 两行事件流、写入路径上无任何锁——挂接清单②
"现有锁协议需核实兼容"前提不成立，是从零新增；registry_query 无兜底件导致
"裸项目装上即可用"与"registry_query=null 锁 principles-lint"打脸；撤销体裁
"status+superseded_by"在 blocked/spec 两类拍板上无字段可写。软伤：
inspection_report 在途空值无成文、criterion_cmd 取值来源未写、§1"注册表
脚本代笔"专名混用。修订十一 7 处全修。

## 第十一轮自决点（按 R6 留痕）

70. **rails.* 值域两型成文**：skill 名（路由转交）或可执行命令/脚本路径
    （运行层直接执行，入参为发射单路径）；区分机械——命中已装 skill 名按前者。
71. **fallback/registry.py 带 `--list` 只读免门禁子命令**，registry_query 兜底
    落点即它；兜底映射从三键扩为四键。
72. **撤销体裁按账分四路**（弃"给 blocked 加 superseded_by"备选，不加字段）：
    抉择/故事账走 status+superseded_by；原则标【已撤销】；spec 改文件头
    approved_* 并递增版本；待决答复由 from_layer 写 withdrawn 并另开新条
    ref 指旧 blocked_id。
73. **挂接清单②扩为三件新增 + 新增⑦渲染器跟随**：runs.jsonl 锁从零建
    （与 runs-append 同协议）；行型改造为 §5 单指标行，旧事件流冻结为
    runs.legacy.jsonl（不进 ledgers 注册表）；§5 字段由 record.py 自动补齐。
    弃"spec 放宽允许事件流"备选——query 维度与 --since 都靠平铺行型。
74. **inspection_report 允许空串 = 未收官**：trace_check 只在非空时校验，
    收官门禁另查非空。
75. **criterion_cmd 取值链成文**：runs-append 按 --principle 从原则文档
    criterion_cmd 列取命令，行内不存命令本体；trace_check 豁免检查同链。

## 第十二轮：修订十一复验 → 修订十二

复验判定：7 项 5 净、2 残留（"注册表"专名声明立了但 R7/§7/§8 旧用法没扫；
spec 版本递增无落点字段）；白手 5 硬 6 软。硬伤：撤销四路里两路无合法代笔人
（用户在 idea 层收回 deploy 的 decision 被 per-kind 拒）、owners 键全文无来源
（init 不问、无默认表，接线产物必过不了 config-check）、"收官门禁另查非空"
无执行者、legacy 冻结撞 §2.1 archive 唯一性且监察面追溯缺块、rails 值域两型
误写成五轨通用（撞 §2 信道 3"施工不跨层下发"）。修订十二 13 处全修。
**用户同轮指令：最多再迭代三轮，之后不论如何停。**

## 第十二轮自决点（按 R6 留痕）

76. **撤销代笔特例**：撤销体裁的成文就地更新由当场会话代笔、不查 --layer
    归属，字段级强制留用户原话，无原话拒。
77. **spec 文件头加 spec_version**；批准撤销 = approved_by/approved_date 清空
    （回未批态）+ spec_version 递增。
78. **owners 由 plugin 携带全键默认表**（值按 §1 固定），init 自动生成不询问；
    工程改值走 R5。
79. **收官非空门禁的执行者 = `trace_check --closeout <batch_id>`**（空串即
    报错），部署层 SKILL.md 收官段末跑。
80. **legacy 冻结定为一次性接线迁移**：执行者=用户确认下的接线会话，机验=
    逐字节一致+新主文件从零行，是 §2.1 archive 唯一性的唯一成文豁免；
    legacy 挂 ledgers.runs_legacy（owners=run，只读，任何写入拒）。
81. **rails 值域按键分收**：只有 rails.gpu 两型（skill 名或可执行命令），
    其余四轨只许 skill 名（施工不跨层下发，§2 信道 3）；弃"gpu/pipeline 都开
    第二型"备选——pipeline 是会话形态整链流程，无发射单可作入参。
82. **打回理由落批次报告头部 rejections[]**（用户原话转录，evidence_lint
    对此字段豁免）；弃"落待决账"备选——打回的消费者是被退回层，顺批次报告看。
83. **"注册表"全文只指 registry_cmd**：ledgers 改称"账本清单"，R7 改"两条
    脚本路径"。

## 第十三轮（用户上限第 1 轮）：修订十二复验 + 保真审计 → 修订十三

复验判定：13 项 10 净、3 残留；白手 9 新伤（5 硬 4 软），仍集中在修订十二
新改文字。硬伤：撤销特例与 blocked 跃迁旧句打脸（withdrawn 两种口径并存）、
decisions 撤销留痕字段不在白名单（"无原话拒"恒成立）、"所有账本脚本代笔"对
md 账不成立、撤销 answered 后原提问层视图掉条、doctor"调用工程自检"调不动
skill。修订十三 13 处全修（含补一条丢失的意图承载：plugin 本体英文成文进 §4）。

保真审计三件（结果全文在 tasks/wb23lj1xc.output，交用户裁决不自动改）：
- diff：73 处设计级改动，49 追自决点、12 追批注、6 追裁决、
  **6 处 untraceable-drift**（§2.5 五下六上体裁清单、R5 三问、R9+反馈账、
  R10 按需加载、batch_id 命名规则、runtime_factor 键）——均出现在用户批注
  过的修订五文本里（用户见过未逐条确认）。
- intent：I1–I16 无 lost；8 held、8 strengthened、3 weakened
  （I3 英文约定未成文——本轮已修；I13a"idea 层产目标"挪成部署层拆 spec；
  I15"永不自决"降为"无 grant 覆盖时不自决"）。
- loop 总判：原目标没丢、原则先行仍是唯一被脚本强制的骨架，但重心已从
  "循环"移到"账本与核查"：857 行里约 705 行讲账本/配置/校验；"跑一个实验"
  至少四道批准、六处登记、一次强制 opus 通读；小实验无快车道。

## 第十三轮自决点（按 R6 留痕）

84. **decisions 撤销留痕字段**：加 withdrawn_by/withdrawn_reason 进 schema 与
    白名单；story 加 retired_by（归 retired_* 族）；特例句按账点名落点。
85. **blocked withdrawn 跃迁改口径**：closed 仍 from_layer，withdrawn 走撤销
    特例；撤销 answered 条由 ledger.py 同一动作机械重开（沿旧条 from/to/kind/
    question，ref 指旧条）——原提问层视图不掉条。
86. **owners 值域加第九值 frozen**（只读冻结件，任何写入拒）；新增键由接线
    会话与 ledgers 同批补齐，init 对默认表外键提示补填。
87. **freeze-legacy 成为 ledger.py 子命令**（不收 --layer、用户确认、机验
    两条、重复执行拒）。
88. **§1 代笔句分野**：jsonl 脚本代笔 / md 归属层会话直编+lint 事后把关。
89. **doctor 不调用工程自检**（skill 不是脚本调得动的），代码检查归
    rails.build 会话收尾。
90. **打回限定批次验收阶段**；spec/原则不批准 = 不落 approved_by + 开待决条。
91. **撤销留痕对称**：spec 头加 withdrawals[]；原则撤销原话注日期追进
    rationale。
92. **四轨 null 锁对应 §6 路由句**（触发即报未接线）。

## 第十四轮（用户上限第 2 轮）：修订十三复验 → 修订十四

复验判定：12 项 9 净、3 残留（freeze-legacy 未进 §5 豁免闭集与 §2.1"唯一
例外"句；§2.1 白名单复述漏新字段；机械重开沿用清单漏 where/options/evidence
且同步 decision 条无联动）；白手 2 硬 2 软（硬 #1 与残留 #1 同源）。
硬伤：freeze-legacy 被 §5"一切写入必带 --layer"罩住无豁免落点；四轨 null
"锁路由句"把"我有个想法"整行锁死（比无配置文件还严）。修订十四 6 处全修。

## 第十四轮自决点（按 R6 留痕）

93. **豁免闭集扩为三个维护动作**（archive/init/freeze-legacy），freeze-legacy
    合法性由两条迁移机验+重复拒代替写权检查；§2.1"唯一例外"改双例外。
94. **§2.1 白名单复述改概括式**，逐项以 §5 写入两式②为唯一穷举——防两份
    穷举再漂移。
95. **机械重开沿用清单补全**（+where/options/evidence）；被撤销答复的同步
    decision 条同一动作置 withdrawn+撤销原话——被收回的裁决不得保持生效。
96. **四轨 null 按动作锁不按路由行锁**（literature 只锁文献核实、pipeline
    只锁自己那条发射路径、build 锁施工、paper 锁取材），陪谈与落原则永不被锁。
97. **§1 代笔句补第三类小 json 逐件归口**（发射单走 ledger.py、error_classes/
    schemas 会话直编、jobs/RUNMETA 归代码）。
98. **superseded_by 来源成文**：纯撤销留空；更正由用户给 --superseded-by，
    脚本校验存在后回填。

## 第十五轮（用户上限第 3 轮，最后一轮）：修订十四复验 → 修订十五（未再复验）

复验判定：6 项 4 净、2 残留（§2.5 第四路清单又是"两处成文一处旧"、§1 代笔句
枚举与 §2.1 读法类目错位）；白手 3 硬 3 软。硬伤：机械重开的"原提问层视图
不掉条"与必读视图定义打脸（open 只进 to_layer 待办）——按裁决(a)改成事实
描述；rails.paper 的 null 锁无执行者（写论文路由不经层）——薄壳转交前跑
config-check；runs 普通行 arm/filter 全文无来源——发射单加两字段、记账脚本
透传。修订十五 8 处全修（含把 §2.5/§2.1 的重复穷举一律改成指回 §5 唯一真源）。
**按用户 2026-08-13 指令迭代到此为止，修订十五未经复验轮验证**——修法全部
来自第 15 轮报告的精确落点，但"修复引入新伤"的风险未经机器复查，
残留风险以此为界。

## 第十五轮自决点（按 R6 留痕）

99. **机械重开的口径按事实改**（弃"扩必读视图"备选）：新 open 条回 to_layer
    待办，问题不因撤销而消失；不改 §2 必读视图定义。
100. **发射单加 arm/filter 两字段**（部署层填、可空），runs 普通行由记账脚本
    从发射单透传——运行层不判语义。
101. **薄壳获得 config-check 职责**：直接转交铁轨（写论文）前跑，被锁则拒
    并说明 null 键。
102. **重复穷举一律指回唯一真源**：§2.5 第四路沿用清单、§2.1 就地更新白名单
    复述、§2.1 豁免句全改为指回 §5。
