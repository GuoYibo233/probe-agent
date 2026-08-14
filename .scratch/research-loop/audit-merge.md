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

## 用户裁决第二批（2026-08-13，保真审计裁决清单逐条拍板）→ 修订十六

对六处漂移、两处意图弱化、快车道问题的逐条裁决（编号对应汇报清单①–⑧）：

1. **下行不设固定体裁**："不需要固定题材"——用户侧说话不套格式，五类降为
   转录路径（约束转录会话不约束用户）。**上行保留常用格式但清单不闭**：
   "系统给我回话的方式……常见的这几类，你可以格式化了，当然也可以报额外的"。
2. **R5 改双模式**："分时候……不要写成铁的，看用户的决定"——默认上桌；
   用户明说"让你自己做"即入自决模式（落 grant）。附三条：
   "写 nfs 的话不用管，你可以自己写"（NFS 写不算不可逆）；
   "就算用户说了不能自己做决定，如果出现 GPU 的话，预计低于一小时的，
   你可以自己干"（常设授权）；"如果你自己干了，你必须要通知用户自己干了什么"
   （回报义务）。
3. **R9+反馈账留下**（"第3个要留下"）。
4. **R10 按需加载留下**（"第4个可以拆"）。
5. **batch_id 命名规则留下**（"我觉得没问题"）。
6. **runtime_factor 键留下**（"我觉得也没问题"）。
7. **I13a 接受现状**："我中途改了我的决策，把这个新的当成我的决策"——
   目标由部署层拆 spec、用户批准，此口径自此为用户决策，不再算漂移。
8. **I15 授权口子留 + 回报义务**："这个我可以授权你，但是你必须回报给我
   发生了什么"——实验设定可被 grant 覆盖，授权内自决必须事后回报。
   （执笔注：此句紧跟第 7 条之后无编号，按上下文判读为答第 8 条——
   第 7 条"接受现状"已语义完整，"授权"只贴第 8 条；判读已当面向用户声明，
   用户未纠。）

**快车道**："专门弄一个新的，就一口气完事儿。它可以高效的试验新的东西，
复用以前的东西。就平直快就可以了。顺便大实验也不需要那么多防御性设计，
毕竟是研究代码，它不会用到生产环境里的。"——新增 §2.6；
"减防御性设计"指令在重构（下节）中执行。

**重构令**："弄完之后。圈二圈三重构。spec"——按本会话提案的 ②（散文内核+
结构化表，封闭清单唯一成文）+ ③（spec-lint 机械校验散文对表）重构 spec。

## 第十六轮自决点（修订十六实施细节，按 R6 留痕）

103. **五类下行保留为"转录路径"不删**：用户免除的是"用户必须按体裁说话"，
     账本落法本身仍需成文；弃"整节删除"备选——删了转录会话无据可依。
104. **回报义务的机制 = R6 自决清单渲染**：decisions 账 decided_by=agent 近期
     条目渲染成清单随汇报明列；弃"新开回报账"备选——不加新账本，复用留痕。
105. **GPU<1h 常设授权的落痕**：authorized_by 填 `spec-standing-gpu-1h`
     哨兵值（不指向 grant 条目）；预计时长以发射单 expected_runtime_s 合计。
106. **快车道机制**：缩减发射单（spec_ref/issue_ref/decision_refs 可空 +
     quick=true）、run_id 归 quick-<YYYYMMDD>-<序> 批、trace_check 豁免回指、
     免批次报告与收官通读；quick 字段透传进 runs 行，story 引用 quick 行拒
     （要进故事按正轨重跑，种子固定重跑即复现）。数字入账与固定种子不免
     （数字纪律非防御手续）。
107. **schema 变更仍恒算抉择点**（第二问恒为是），但处理服从双模式——
     "必上桌"改为"按模式走"；弃"schema 变更恒上桌不受模式管"备选，
     依据用户"不要写成铁的"。

## 第十七轮：按用户重构令重构 spec（v2 内核版）

执行"圈二圈三重构"：v1（643cb94，895 行）拆成散文内核（spec.md，461 行）+
五个数据表（tables/：ledgers/rows/writes/config/routes）+ spec_lint.py。
lint 四类检查面经注入实测各能触发（E1 表间不一致 2 例、E2 旧枚举链、
E3 路由表复述、W1 生造字段——测试副本注入后逐类报出，真本全绿）。
另派一份 opus 对照 v1 做内容丢失扫描（授权裁员 9 处除外），结果见本轮末。

## 第十七轮自决点（按 R6 留痕）

108. **md_size_caps 机制删除**（减防御性设计）：配置键、doctor md 体量扫描、
     阈值全裁；md 账整理由写权层会话或用户看着办。弃"保留只降为建议"
     备选——建议机制本身就是被裁的重量。
109. **发射单 mutable_params 字段删除**：重试时可变参数白名单裁掉，归铁轨
     自治；"seed 永不可变"升格为 §5 纪律句保留。
110. **任务台账字段清单裁员**：v1 开列的完整补字段清单收缩为最低两个回指
     （launch_order_ref/escalation_ref，rows.json jobs_min_additions）；
     其余以工程现状为准——new1 挂接工作量随之减。
111. **archive 并发协议压行**：临时副本+原子 rename 细则压成"全程持锁、
     原子替换"，实现细节归实施计划。
112. **活跃行判定式数据化**：从 §2.1 散文迁入 ledgers.json active 列，
     query 默认视图与 archive 共用同一份。
113. **§9 验收用例改列"拒绝面与豁免面"**：正例从略，篇幅约减半；
     覆盖的拒绝行为一条没减。
114. **元规则四条成文 §0.5**（用户方案①的产出物）：封闭清单唯一成文、
     字段单一归属、一物一名、交付前 spec_lint 全绿；并注明 tables/ 就是
     实施期 schemas/ 与 owners 默认表的生成源。
115. **表的划分取五件套**：owners 与 ledger_caps 默认值并进 ledgers.json
     单表（owner/cap 列），不单独立表——键集相等约束从"校验两表"变成
     "天然同源"。弃"照配置文件结构分表"备选。
116. **spec_lint 检查面**：E1 表间一致性（owner 值域/cap 规则/白名单指向）、
     E2 散文枚举链与表枚举冲突、E3 路由表复述、W1 反引号生造字段、
     W2 四元以上无主枚举链；警告不拦、错误拦（exit 1）。

**丢失扫描结果（opus 对照 643cb94 全文，核对 43 个角落）**：授权裁员 9 处之外
查出 12 处意外丢失（9 硬 3 小）——派发契约三件套名与核查范围句、inspector
与监察会话分野、oversight 表条目与散文相抵（两条口子没登记进表）、
trace_check 的 decision→run 一致性校验无执行者、principles-lint 少查
principle_id 唯一与 applies_when 非空、信道 4 采样器判定整项消失、归档 idx
字段与两消费者、归档伴生物不进 ledgers 的键集约束、§10 后置清单与 md 定形句
两段（含用户"可自动"诉求存档）、§9②(c) 把 recorded_at 误划进发射单透传、
doctor --out 与不写账本目录句、md/小 json 机验对号。12 处全部按清单落点修复，
修后 spec_lint 全绿 + 五表 JSON 可解析。lint 自身经注入实测：E1×2/E2/E3/W1
五类病各能触发。判保留的高危角落（撤销全链、r5-choice 拼装、freeze-legacy、
per-kind/per-transition、快车道、R5 双模式等 22 项）扫描逐一验过下落。

## 用户裁决第三批（2026-08-13，外部评审采纳令 + 减防御追加令）→ 第十八轮

用户原话一（采纳令，ultracode）：
> ultracode review/research-loop-advisor-notes.md review/research-loop-spec-review 查看这两个review意见，看看他说的有无道理，如果有的话采纳意见继续完善计划

用户原话二（执行中追加）：
> 我觉得这两个稍微有一点过度防御，我很希望能够快速执行，可以删除一些过度防御，如果有的话

两份评审：`review/research-loop-spec-review.md`（架构评审，P0×4/P1×6/P2×3）、
`review/research-loop-advisor-notes.md`（advisor 细化，建议 A–I + 实体模型）。

## 第十八轮：评审逐条裁断与落地

- 裁断方式：workflow 派 7 个 opus 评估组（schema 真源/恢复现场/崩溃一致性/
  实体模型/批准与命令权威/R2R3R4 边界/分层与范围）逐条对照 spec 原文与
  用户既有裁决裁断，1 个 opus 合成。共 111 条裁断：adopt 41 / partial 47 /
  reject 22 / user-decision 1；合成 15 个采纳项、34 条驳回（重型机器全驳：
  事务日志 operations.jsonl、staging manifest、observations/attempts 新账本、
  独立 approval 账本、五步 canonicalization、state.json、next 命令、
  顶层 CLI 门面、registry_digest、task_id+args 重构等，逐条反证在案）。
  完整方案存档 `review-adoption-plan.json`（含全部 verdicts 与驳回理由）。
- 落地：15 项采纳全部进 spec.md 与五表（用户追加令再裁两刀，见自决点
  #125/#132）。spec_lint 升级 E4（表可生成性）并经注入实测七类病全触发
  （六类表病 + 一类散文旧枚举链），真本 0 errors 0 warnings。
- 三条 user_flags 按用户两道原话就地落地（#132/#133/#134），随本轮汇报
  明列，可推翻。

## 第十八轮自决点（按 R6 留痕，authorized_by=用户采纳令；#125/#132 加引减防御追加令）

117. **runs 主键取三元组 (run_id, metric_name, filter)**：filter 已是行内
     字段且从发射单透传；二元组会把"同指标不同口径子集"误判重复。
118. **decisions 回指字段命名 blocked_ref**：与 blocked_row 已有的
     decision_ref/grant_ref 命名法对称；评估组提的 ref 与 blocked_row.ref
     同名不同义，撞一物一名。
119. **不发 observation_id**：观察值身份 = 主键三元组自然键，无第二消费者。
120. **只方言化 rows.json 一张表**：拒"拆 schemas/+policies/ 三套、tables
     降级文档视图"——ledgers 四列已是机器值且 E1 在验，拆表退回自决点 115
     判过的老形态。$enum 就地展开、不引 $defs 与跨文件 $ref。
121. **gen-schemas 挂 ledger.py 子命令**：不新开脚本；生成物一致性归
     gen-schemas --check，不塞 spec_lint（设计稿检查与实施期产物检查分工）。
122. **复合动作取最低档**：严格写序（翻状态的一笔最后写）+ 派生行回指查重
     （重跑即修复）+ doctor 半状态扫描（只查不动）。拒事务日志、staging、
     全账本 operation_id——幂等键用自然回指键。
123. **不提供自动重放与自动补齐**：修复动作恒为重跑原命令，验收措辞钉死，
     防实施期照"reconcile 自动恢复"造重放引擎。收官链判已被现文覆盖，不加协议。
124. **digest canonicalization 取"文件头整块不入哈希"**：approved_digest =
     sha256(第二条 --- 之后的正文原始字节)。拒五步 YAML 归一化（新漂移面）、
     拒 approved_commit（批准时多半未 commit）、拒独立 approval 账本。
125. **【减防御追加令】砍原则文档 digest 半边**：不加
     approved_against_principles_digest（按列归一化+置空回填列+第二类 stale
     报警，堵的是没踩过的坑）；悬空引用 approved_against_principles_version
     直接删（该版本号在 spec 里无人递增，是修缺陷）。保留 spec 正文
     approved_digest（堵真洞：批准戳所在文件归部署层写，偷改无机验可见）。
     R1 补"原则的批准是逐行事件"一句。
126. **status 不设全局 stage 标量**：原则逐行状态、多批并行、快车道与正轨
     并行，一个标量装不下；矛盾只进 inconsistencies[] 不推断阶段。不开
     next 命令（动作名取 routes.json to 列进 waiting_on[]，不立第二套映射）；
     不建 state.json 第六表、不建 current.json 物化视图。版本字段沿用
     schema_version 不引入 state_version。
127. **R2/R3/R4 收窄的例子全落 §9 验收用例**，不进 §3 正文（守 461 行内核）；
     不引入 extractor 一词（已有名字 metrics_cmd/criterion_cmd）。
128. **拒"未配置时继承会话默认模型"**：与用户全局硬规则（派 subagent 一律
     显式传模型）冲突；改 plugin 携带默认值 opus/sonnet 且显式传，
     配置键 roles.inspector_model/reader_model。
129. **inspection_policy v1 值域只收 always**：risk-based 判定规则无人写、
     manual 等于关核查，v1 无使用者；加值须回 spec 走 R5。
130. **快车道转正只加 promoted_from 一个字段**：发射单按 run_id 命名，
     source_launch_order_ref 与它互推，存两个键 = 同一事实两处成文。
     "种子固定重跑即复现"改成"沿用整张发射单"（六因子漏五是现文自己的反证）。
131. **假铁轨复用 fallback 三件**：不建平行 tests/fixtures 工程（两套铁轨
     要同步维护）；崩溃类验收用半状态 fixture + 重复执行，不搭进程 kill
     注入框架。fake 两脚本不计入"九个脚本"计数。
132. **【减防御追加令 + user_flags①就地裁决】archive 执行件整体排 v1.1**：
     v1 只留行数到 cap 告警（doctor 既有扫描）；archive 命令、归档索引、
     跨档就地更新（第 13 项）随 v1.1；设计文字留表不删，届时不重谈。
133. **【裁决点，user_flags③】runs 账本 schema 变更落地**：一次实验多指标 =
     同 run_id 多行、一行一指标；metrics_cmd 尾行改 metrics 数组。R5 第二问
     （schema 变更）恒真，authorized_by=用户采纳令原话；随本轮汇报明列可推翻。
134. **【user_flags②】R4 预授权句落地**：批过的口径每批照算不再上桌；
     口径没写全不算预授权；改口径一律重新提案。
135. **blocked answered 的 force_fields 补 _when 条件**：执行 agent 自报的
     缺陷——无条件强制会把授权自决答复（answered_by=agent）也翻成 user；
     现限定"仅 to_layer=user 代笔特例生效"。
136. **fake.mode 五值收进 rows.enums**：spec_lint E2 咬住 §9 散文里新长的
     封闭清单（--mode 值域），按 §0.5 迁表；E2 加"完整落在某表枚举 = 合法
     引用"豁免，豁免不放走冲突链（注入实测：resolved 混入四态链仍报错）。

## 用户裁决第四批（2026-08-13，第十八轮汇报后）

用户原话（两条连发，后一条细化前一条）：

> 首先声明哪一层要由我显式决定，你不许自己决定。

> 一个对话在哪一层用只有用户触发skill或者调用subagent的时候能决定

裁决内容：会话的层身份不由会话自己判断。合法来源只有两个入口——
用户触发某层 skill（含经路由句转入），或派发 subagent 时由派发方在
派发契约里钉死。身份定下后整个会话不变；干到一半需要别层的活走跨层
传输（subagent 派发或新开会话），不许就地换层。

落地两处：spec.md §1 会话身份条整句重写；tables/writes.json
layer_param 加 _source 键。原文"每个会话开工第一动作是声明本层身份"
作废——"声明"隐含会话自选，正是本裁决禁止的。

137. **层身份来源收两口**：按用户裁决落地。路由薄壳的"认阶段→转层"
     不与本裁决冲突——路由句本身是用户说的话（routes.json say 列），
     属"用户触发 skill"入口；inspector 等 agent 派发属第二入口。

## 实施期（2026-08-13，用户令"出计划，然后直接执行，迭代到分层验证全过"）

计划 `plan.md` + 工单 `issues/01-16`，执行走 ticket-run。实施期自决点
（全部可推翻，推翻即改 plan/工单重跑对应波）：

138. **plugin 落点**：在 new1 仓库根 `research-loop/` 开发（git 管版本、
     ticket-run 的工作树机制要求在本仓库内；R9 反馈改 skill 本体要进 git）。
     "机器级安装"（拷贝/软链到 ~/.claude）后置，不在本轮。
139. **表搬家**：`git mv .scratch/research-loop/tables research-loop/tables`，
     spec_lint 与 spec.md §0.5 同步指向——§0.5 第 5 条"spec 与实现共用
     一个真源"的字面落地，消除两份表的可能性。
140. **纯 stdlib + Python 3.10**：机器级 plugin 不得假设任何虚拟环境；
     测试用自带 stdlib 跑器 `tests/run_all.py`，不用 pytest。
141. **ledger.py 拆薄分发器 + ledger_cmds/ 包**：spec 说"九个脚本"计数不变
     （ledger.py 仍是账本总入口），包是文件组织——一组子命令一个模块，
     让工单并行施工不撞同一个文件，也控住单文件体量。
142. **生成 schema 丢 `_note`**：表里的说明是中文，plugin 本体要英文；
     生成物只带结构（enum 展开、$ref_to 保留为注解），散文说明留在表里。
143. **报告体裁机验约定**（plan.md §C6）：`$ ` 复现命令行、`= ` 回显行、
     `> ` 摘录行、`path:line` 引用——R3"可粘贴执行的复现命令"要机验就得
     定死可解析形态；写进 oversight SKILL.md 与三件 lint/校验器，两边共用。
144. **自测场景⑥的 fail→ok 实现**：不给 fake.mode 加 flaky 值（枚举是
     封闭清单，动表=动 spec），用"同 run_id 重写发射单（--mode 改 ok）+
     重新发射"实现重试，RUNMETA attempts 两条留痕正好考到"前条不得覆写"。

145. **launch_order_ref 的取值裁决（wave5 收账，2026-08-14）**：T16 e2e 抓出
     launch.py 写 CLI 原始路径、trace_check 按 run_id 索引的跨工单不一致。
     裁决取 run_id：表源只列字段名未钉格式，spec §5 钉了发射单文件名 =
     `<run_id>.json`，run_id 是发射单主键；CLI 原始路径随调用 cwd 漂移、
     不可复现。T10 工单文字"launch_order_ref: 发射单路径"以此更正。
     修复随 T16 修复轮落地（2a84828），主会话亲核认可跨范围改动。

以下四条是终审（sdd/final-review.md，2026-08-14）四道裁决题的主会话裁决，
关键事实（两个写入口一收一拒、--spec-item 查无、statuscmd 扁平输出）均亲核过：

146. **常设授权不经 blocked answer（终审 F9/F10 的裁决）**：blockedcmd 对
     `--grant` 只收活跃 grant 的行为保留——spec §2.6 快车道的字面就是"常设
     授权直接干、事后 R6 留痕"，不走待决账问答。`r5-choices.md:41` 那处
     教人把 `spec-standing-gpu-1h` 当 grant_ref 传的括号删掉，改指 §2.6；
     同文档补 `ledger.py decision` 的完整调用形态（F11）。代码侧加一条机验
     堵 F10：`to_layer=user` 的行答复时禁止带 `--grant`——带了就说明不是
     用户在裁决，答案却会被记成 `answered_by=user`，属审计链反写。
147. **evidence_lint 的行为是准，表与文档向它对齐（终审 F13 的裁决）**：
     "账本行数"这类裸数字与经验数值在形状上不可分，linter 不可能按内容
     豁免；真正的豁免机制只有两个——落在 frontmatter 块里（块级豁免），或
     跟 `$ `/`= ` 复现对（声明行豁免）。`rows.json` `evidence_lint_exempt`
     的 `_rule` 补一句实现方式说明，`report-genre.md` 改成"溯源三件落
     frontmatter，正文里的行数必须带 `$ ` 复现行"。
148. **实现 `query runs --spec-item`（终审 F8 的裁决）**：spec §2.1（93 行）
     白纸黑字承诺了这个维度，R3 全量扫描陈述靠它撑，删 spec 那句是削设计
     迁就实现。实现走发射单 join：扫 launch_orders 目录收集 spec_ref 匹配
     的 run_id 集，再过滤 runs 行；`ledgers.json` 的过滤集补上
     `--spec-item`（改表，复跑 spec_lint + gen-schemas --check）。
149. **status 补齐 spec §2 的分层视图（终审 F15 的裁决）**：spec §2 是设计
     权威，采终审"补表再补码"的正解、不做改文档止血。`rows.json`
     `status_view` 两处改动：`open_blocked` 的派生源改成"status=open 且
     to_layer=--layer"（原"全部 open"会把别层队列混进本层）；新增
     `answered_blocked` = "status=answered 且 from_layer=--layer"（本层
     提出且已有答复、待本层消化收尾的条目）。statuscmd 照表实现；
     `pending_user_decisions`（to_layer=user）与 `active_grants` 不动，
     四份 SKILL.md 的"三块分层视图"描述随之变真。
150. **复审残余的裁决（2026-08-14）**：范围限定复审判 15 FIXED + F15 文档
     半边 PARTIAL + 11 条观察。处置全文见 sdd/final-review.md 末节：修掉
     6 条（含唯一挡合并残余 idea-layer/SKILL.md 授权视图措辞、blockedcmd
     全 kind 校验 --grant、fallback/launch.py 接 F2 根校验，各配测试），
     搁置 4 条（b589621 bisect 断点 / e2e ⑤ 日志摆设 / 手工 --ref 顶重开 /
     --spec-item 非 runs 账静默空表，理由同见该节）。修后 288/288 +
     gen-schemas --check + spec_lint 三绿，主会话亲跑。

以下七条是 §V 验证循环第一轮（sdd/vloop-round1.md，45 confirmed）里
设计裁决题的主会话定案，补丁工单 17/18 按此实现：

151. **非 r5-choice 自决的 R6 机验路（v1-deploy-2 / v2-hop3-1）**：r5 拼装
     保持 r5 专属不外扩（writes.json r5_choice_assembly 的 _rule 字面就是
     kind=r5-choice）。非 r5 行走两步显式路：`ledger.py decision` 新增
     `--blocked-ref B0xx`（校验行存在，落既有 blocked_ref 字段）；
     blockedcmd 对 kind≠r5-choice 的答复拒收 --grant（文案指向两步路），
     新增可选 `--decision-ref D0xx`（校验：行存在、kind=decision、
     blocked_ref 等于本条、authorized_by 指活跃 grant 或常设字面量），给了
     就回填 blocked.decision_ref。机验边界定为"引用授权必留痕"：不带
     grant/decision-ref 的平答（转录既有账面信息）仍合法——R6 管的是自决点，
     不是一切答复。doctor 半状态补反向扫描：kind≠r5-choice 且 grant_ref
     非空且 decision_ref 空 → missing-R6-trace 建议（兜历史/手写形状）。
152. **开条跳层的机器锚点（v3-1）**：writes.json blocked_transitions.open
     新增封闭映射 legal_to：run→[deploy]、deploy→[idea,user]、idea→[user]、
     oversight→[user,deploy]；blockedcmd._run_open 照表校验。依据
     failures.md:51"升级走楼梯"与 spec §2 通道表；deploy→run 不设
     （下行走发射单/答复，不走开条）。
153. **jobs 台账两个必加键钉名（v1-run-2/5、v2-hop2-1/2、v2-hop4-2/3）**：
     rows.json jobs_min_additions 钉死字段名 escalation_ref（可空，指
     blocked_id）与 sampler_verdict/sampler_verdict_at；sampler_verdict
     只对"进程真启动过"的 run 有值，枚举不加新值——发射在预检被拒时
     **不写 jobs 条目**，拒绝原文存档进升级条的 evidence 文件；fallback
     铁轨的判定映射钉死：done/failed→ok（活性不是成败）、timeout→stall。
     run 层对 ops/jobs.json 的直接编辑权在 run SKILL.md §3 成文（对齐
     deploy §3 的既有写法）。
154. **run_id 缺省命名规则（v2-hop1-1）→ 顺带解 evidence_lint 冲突
     （v1-oversight-2）**：rows.json launch_order.run_id 的 note 钉缺省
     形态 `<name>-<YYYYMMDD>-<序>`，name 限 [A-Za-z0-9_.]（连字符留作
     段分隔）；工程可另立成文规则覆盖。该形态恰好命中 evidence_lint 既有
     _ID_DATE_SEQ_RE 豁免——linter 一字不动，第一轮沙盒里 run-101 那种
     形状是种子自己不合规。report-genre.md 补一句：合规 id 按形状豁免，
     不合规含数字标识符要么进 frontmatter 要么配 `$ ` 行。
155. **error_classify 缺表不裸崩（v1-run-1 / v2-hop2-3）**：
     ops/error_classes.json 缺失/不可解析 → 按零规则处理，产 unknown 判定
     并在 stderr 报表路径，退出码与 unknown 分类同路；rows.json
     error_classes 补真字段契约，deploy 侧新参考文档教如何起表（走 18）。
156. **record.py 带 commit 入行（v2-audit-1）**：runs 行 commit 字段取
     RUNMETA.commit（RUNMETA 无此键才落 null），不再写死 null。
157. **expected_outputs 不许空产物契约（v1-run-6）**：rows.json
     launch_order.expected_outputs 加 minItems 1（重生 schema），
     output_check 对空清单拒绝并说明；tests/helpers 缺省发射单跟着补一条
     真实产物契约。execute.md 的门禁语义由此成立。
     story 行的对照口径（v1-idea-2）一并定：baseline_runs 放宽为可空
     （null = 单臂绝对陈述，不是对照主张），CLI --baseline-runs 变可选，
     给了则与 candidate_runs 集合不得完全相同；表+schema+CLI+story.md
     四处同步。

以下四条是 §V 第二轮（sdd/vloop-round2.md，48 confirmed）设计裁决题的定案，
补丁工单 19/20 按此实现：

158. **记过账的重试用新 run_id（第二轮 v2-hop4-1/v2-hop3-3 的裁决）**：
     runs 账保持 append-only 纯度，不给 record.py 开 supersede 口。纪律
     分两段：run 尚未入账时，同 run_id 改单重发合法（RUNMETA attempts
     留痕，e2e 场景⑥形状，#144 语义收窄到这一段）；**失败已经入账后，
     获准的重试是一张新发射单**——新 run_id（缺省命名规则取下一个序号）、
     decision_refs 带裁决 decision、全新 artifact_dir。旧 run 的失败行
     留在账上是事实不是垃圾。附带收益：新单自然落进
     pending_launch_orders（v2-hop3-3 的队列表示问题消解）、jobs 与 runs
     状态各自一致（mismatch 告警消解）。纯文档+表注改动，代码零改。
159. **evidence_lint 收四类机械误火、门不松（v1-oversight-3/v2-hop6-4/5/6）**：
     规则 2 新增豁免——`> ` 摘录行整行跳过（引用不是主张，摘录保真由
     verify_report 逐字节比对）；行首标题/列表编号前缀剥除；`§\d+` 引用
     剥除；字母紧连数字的单 token（python3/sha256/attempt1）剥除；`$ `
     行的续行（反斜杠续行）进保护集。带空格的序数词（"attempt 1"）保持
     命中——机器分不出它和计数，体裁文档教改写。report-genre.md 补成文：
     `$ ` 行禁管道、无 shell 执行（重定向符会变成字面 argv）。非回归底线：
     裸行数（"row count: 5"）必须仍被命中。
160. **routes 命令拆列 + render blocked 补状态（v1-router-1/2）**：
     routes.json 的 kind=command 行新增 `cmd` 字段只装可粘贴的命令尾巴，
     `to` 列留散文说明；router SKILL.md 教"kind=command 执行 cmd 列"。
     `render blocked` 加 status 列；answered 行改按 from_layer 分组（欠
     close 的一方），open 行仍按 to_layer 分组（欠答复的一方）。
161. **launch.py 首次登记合并不覆盖（v2-hop4-2）**：对既有 jobs 条目
     只更新发射器自有的五个键（launch_order_ref/state/started_at/
     finished_at/log_path），run 层加的 escalation_ref / sampler_verdict /
     sampler_verdict_at 等外来键原样保留——与收尾更新既有的 merge 写法
     对齐。escalation_ref 存最新一条升级的 blocked_id（历史在 blocked
     账本身，表注成文）。
