# research-loop plugin — 设计 spec

**Status:** needs-triage
**日期：** 2026-08-13（brainstorming 定稿；同日五轮修订：四份分层隔离审核 → 修订一，
两份验收审核（覆盖核查 + 五场景重放）→ 修订二，复验十硬伤 → 修订三，
终验八硬伤 → 修订四，复验五硬伤 → 修订五。过程见 `audit-merge.md`）
**形态：** 机器级 plugin（跟机器走），工程铁轨通过仓库根配置文件挂接。

## 0 一句话

把研究循环（谈 idea → 定原则 → 定工程目标 → 施工 → 跑实验 → 故事裁决 → 写作）
做成一套分层的 plugin：三层干活、四信道通信、判据闸门把关、
结构化账本沉淀、一个独立监察面供用户亲验一切细节。

## 1 三层 + 监察面

层按**指挥权**切，每层只管自己的，跨层只认信道上的落盘文件。

| 层 | 干什么 | 账本写权（完整清单，与 §7 owners 一一对应） |
|---|---|---|
| idea 层 | 谈想法、定原则、裁决什么进故事、批准计算 | 原则文档、故事账、TIMELINE、文献账（KNOWLEDGE_MAP） |
| 部署层 | 原则 → spec → 代码 → 发实验 → 收数字 | spec、工单、抉择账、发射单、批次报告、错误分类表、schema 目录（含 runs schema）、代码地图、数据集清单（DATA.md） |
| 运行层 | 机械执行：跑命令、落日志、钉版本 | runs.jsonl 普通行（按部署层定义的 schema 写入；判据缩减行归部署层，§5）、任务台账、RUNMETA、原始输出、集群慢变量档案 |

- 写权说的是**账本内容的归属层**，不是脚本入口：所有账本一律由注册表脚本代笔
  （R7），任何层的会话都可以跑脚本，schema 校验由脚本保证。授权原话因此可以
  在 idea 层会话里当场落进抉择账（audit D7 的定义澄清）。
- **写权单层独占有三个成文例外**：待决账（跃迁级写权，谁能改哪个状态写死在 §5）、
  反馈账（append-only 共笔，条目带 layer 字段）、runs.jsonl（按行型分工：普通行归
  运行层经工程记账脚本，判据缩减行归部署层经 `ledger.py runs-append`，§5）。
  除这三本外，一本账一个层。
- **监察面**不是层：不在指挥链里，谁也不指挥、只读一切（所有账本+代码+原始输出），
  对各层账本零写权；落盘只有两类——专用报告区 `reports/`，以及按上一条前两个成文例外
  作为参与方写共享账（往待决账开条提问、往反馈账追加建议）。唯一产出是给用户的证据报告。
  监察必须用独立上下文，做事的会话不许自查顶数。
- **解读不过层**：上行只有事实，一切解读发生在 idea 层、由用户拍板。
  派生量计算（平均、比例等）是 idea 层活动：提案、批准、算、附命令都在 idea 层（R4）；
  部署层只跑既有机械汇总管道，不发明新算法。

## 2 信道

| # | 方向 | 体裁 | 规矩 |
|---|---|---|---|
| 1 | idea → 部署 | 原则文档 + spec | spec 每条指回 principle_id；指不回去 = 原则有缺，先回 idea 层补 |
| 2 | 部署 → idea | 数字账、批次报告、待决账条目 | 报告零解读；原则缺口/代码抉择点停手，写 open 条目进待决账 |
| 3 | 部署 → 运行 | 注册表命令、**发射单**、工单 | 不在注册表不许跑；**脏树一律拒发并升级部署层**（豁免清单在配置）；产物钉 RUNMETA |
| 4 | 运行 → 部署 | 日志、RUNMETA、台账、采样器判定（进台账）、待决账条目（故障升级） | 升级必须带证据：错误原文、日志路径、已试动作表 |

**待决账 `blocked.jsonl`**（贯穿信道 2/4 的双向体裁，schema 与跃迁规则见 §5）。
**会话开工必读两样**（每层的 SKILL.md 骨架里写死）：
① 本层待决队列（open 条目里 to_layer=本层的 + answered 条目里 from_layer=本层的，
都算未决）；② 有效授权视图（抉择账 kind=grant 且未过期未撤销的条目）。

总规矩：**可追溯链双向**（正向：工单→spec→原则条目；反向：run→发射单→工单，
靠 RUNMETA.launch_order_ref 与台账回指字段；抉择→run 靠发射单 decision_refs）；
**升级走楼梯不跳层**；**一切通信落盘，不走会话记忆**；
**所有账本对所有层可读，写权单层独占**（§1 的三个成文例外除外）。

### 2.5 人的位置（idea 层顶端）

用户本人是 idea 层的顶端，一切判断的终点。人与系统之间也只有固定体裁：

**下行（你 → 系统）五种：**
- **拍板**：原则定稿、spec 批准、故事裁决、**待决条目答复**——落对应账本带日期；
  待决答复由当场会话代笔（answered_by 填 user）；
- **授权**：R4 计算批准、R6 自决授权——原话当场落抉择账（kind=grant，
  含结构化 scope 与有效期）；
- **撤销/更正**：任何已落账的拍板可收回——条目 status 变更 + `superseded_by`
  （脚本代笔），原则文档相应条目标【已撤销】；
- **触发**：路由表（§6）里的任何一句话；
- **打回**：验收不过，退回对应层重做，理由落批次报告。

**上行（系统 → 你）六种：**
- **提案**：计算提案（R4）、方案抉择（R5）——凡要你拍板的，必须以"提案+证据"形态
  到你面前，不许以既成事实形态出现；
- **证据报告**：R3 体裁（监察报告、观察报告、判据验收报告都是它的子类）；
- **抽查清单**：固定种子抽样直达路径 + 总体指纹；
- **待决队列**：blocked.jsonl 渲染视图，你回来先看这个；
- **回归警报**：新批次数字与故事账 active claim 冲突时的清单（只报事实不判）；
- **数字账**：批次报告 + RESULTS 渲染。

**你不在场时**：只有有效授权（kind=grant，scope 覆盖、未过期）内的自决可以继续
（R6 留痕），其余一律停在待决账 open，不许"先做了再说"。

## 3 十条硬规矩（全 plugin 通用）

- **R1 原则三件套**：每条原则 = `principle_id` + `scope` + 原则一句话 +
  判据（`criterion_cmd`，必须是注册表命令）+ 最近实测。
  **最近实测不手填**：判据每跑一次就是一次 run，进 runs.jsonl 带 principle_id，
  原则文档里的"最近实测+日期"由渲染脚本自动回填。原则文档带修订号。
  **判据必须轻量只读**（不占 GPU、部署层会话当场可跑）；要重算力才能产生的证据，
  先按普通 run 跑出产物，criterion_cmd 吃产物路径做检查。
  写不出轻量判据的原则退回 idea 层重谈。
- **R2 机验人判**：判据机器跑，判断人来下。AI 在验收里只做两件事：把检查跑起来、
  把原始证据摆到用户面前。
- **R3 证据体裁**：判据/监察/观察输出只许——计数、差异定位（分叉点原文并排，
  **两侧各带路径+行号**）、可点开的文件路径（带行号/记录号）。
  **每个数字必须配一条可直接粘贴执行的复现命令**，命令输出必须等于报告数字。
  计数为 0 的否定性陈述必须附扫描范围全量清单与总行数。
  报告头带溯源块：生成时间、git HEAD、所读账本行数/哈希。
  "通过/没问题/符合预期"等结论词违禁。lint + 机械校验器双重把关（§4）。
- **R4 计算授权**：对数据只许忠实呈现原始值。任何派生量先提案
  ——公式、分母、过滤条件、作用文件——用户批了才算，算完连同命令附在结果旁
  （进故事账的记 derivation_command）。
- **R5 抉择点上桌**：施工撞到方案分岔必须停手，写待决账，等裁决。
  机械判定三问（任一为是即停）：会改变某条判据的输出吗？会引入原则文档没有
  对应条目的新约束吗？不可逆吗（耗 GPU 时长/写 NFS/产物被下游引用）？
  三问全否才是施工自由度。**账本 schema 变更永远算第二问为是**，必上桌。
  裁决后：ledger.py 把 answered 的 R5 条目**同步生成一条抉择账 decision 条目**
  （chosen 填可 grep 的具体值）——这是抉择账的强制入账口，不许只留自由文本 answer。
- **R6 授权自决留痕**：只有有效授权（grant 的 scope 覆盖眼前分岔且未过期）才许自决；
  每个自决点写抉择账（decided_by=agent，authorized_by 指回 grant 条目）。
- **R7 确定性脚本化**：账本写入、schema 校验、溯源检查、抽样、lint、渲染，
  一律脚本干，LLM 只做需要判断的活。渲染产物不手改。
  **runs.jsonl 的数字只有注册表脚本两条路**：普通实验经发射单 `metrics_cmd`，
  判据 run 经 `criterion_cmd` 的结构化输出——**任何层禁止用眼睛读日志填数**。
  （派生量不进 runs.jsonl，走 R4 归故事账。）
- **R8 故障先自愈后升级**：失败先在本层职责与写权内按**错误分类表**处理
  （特征三类：退出码、output_check 判定、日志正则；命中即得自愈动作或升级指令，
  脚本判不经 LLM）；解决了留痕；解决不了写待决账升一层（运行→部署→idea→你），
  带证据。禁止跳层、静默吞错、越权修别层的东西。"重跑一次输出仍空"必升级。
- **R9 skill 进化落账**：每轮循环收官，各层把"skill 哪里不顺、建议怎么改"写进
  反馈账。建议不自动生效：用户定期审（路由句"审一下反馈"），
  批准的才改 skill 本体（进 git），驳回的记理由——审查以追加 review 行落账
  （§5，账本纯追加），只能由用户审查会话经脚本写。
- **R10 skill 正文按需加载**：SKILL.md 只放骨架（职责、信道、账本写权、开工必读、
  阶段索引），各阶段操作细则拆进 `references/<阶段>.md`，进到那个阶段才读。
  收官才用的反馈方法只在收官段加载。上下文隔离不只隔层，也隔时间。

## 4 组件结构（每层一件专责）

```
research-loop/                      # plugin 根
├── .claude-plugin/plugin.json
├── skills/
│   ├── research-loop/SKILL.md      # 路由薄壳：认阶段 → 转层，含路由表（§6）
│   ├── idea-layer/SKILL.md         # 谈idea规程、原则模板、故事裁决、R4、撤销体裁
│   ├── deploy-layer/SKILL.md       # spec 体裁、工单化、R5/R6、判据验收、发射单
│   ├── run-layer/SKILL.md          # 运行层契约：发射单执行、错误分类、产物校验
│   └── oversight/SKILL.md          # 监察面：报告体裁、独立性纪律、抽查流程
│   （每个 skill 目录配 references/<阶段>.md，按 R10 分阶段按需加载）
├── agents/
│   └── inspector.md                # 只读监察员：写权限定 reports/、R3 体裁
│                                   #   （监察面参与共享账的两条口子归监察会话，
│                                   #     不给这个 agent）；
│                                   # frontmatter 钉 model: opus（派发必须显式指定模型）
├── schemas/                        # 五本账 + 发射单的 JSON Schema（plugin 携带默认版，
│                                   # 工程可覆盖；变更走 R5 上桌 + schema_version 递增）
└── scripts/                        # 全部确定性，按层归属
    ├── ledger.py                   # 账本总入口：story/decisions(含 grant)/blocked/feedback
    │                               #   写入+schema校验+状态机+跃迁级写权检查+渲染
    │                               #   （渲染含：待决队列视图、有效授权视图、
    │                               #     原则文档"最近实测"回填、账本→md）；
    │                               #   另管三件：发射单写入（同一动作回填 affects，§5）、
    │                               #   判据 run 缩减行入账（runs-append，§5）、
    │                               #   init（从模板生成 research-loop.json 骨架）
    ├── trace_check.py              # (deploy) 溯源检查：spec→principle_id、工单→spec、
    │                               #   反向 run→发射单→工单、decision→run（扫发射单
    │                               #   decision_refs + 抉择账 affects）
    ├── output_check.py             # (run) 产物校验：expected_outputs 逐条比
    ├── error_classify.py           # (run) 错误分类：按分类表判自愈/升级，输入三类特征
    ├── spotcheck.py                # (oversight) 固定种子抽样：直达路径清单+总体指纹
    ├── evidence_lint.py            # (oversight) 违禁结论词 + "有数字无复现命令"检查
    ├── verify_report.py            # (oversight) 机械校验器：路径 stat、摘录逐字回比、
    │                               #   复现命令数值回比
    └── regression_check.py         # (oversight) 回归对照：新批次 vs 故事账 active claim
                                    #   同口径重比，冲突清单落 reports/（idea 层消费）
```
runs.jsonl 有且只有两个写入口，按行型分工：**普通实验行**走工程侧记账脚本
（new1: record.py 加载 runs.schema.json 校验；plugin 只携带 schema 与校验函数，
不替代这个入口）；**判据 run 缩减行**走 `ledger.py runs-append`（§5）。
两个入口加载同一份 schema、共用同一把文件锁。

## 5 账本 schema（单写多读，主键贯通）

通用约定：**jsonl 账的实体行必带 `schema_version`**（下面示例从略），校验器按行内
版本号选定版本校验，渲染器兼容读；**md 体裁的账（原则文档/spec/工单/批次报告）版本号
在文件头**（原则文档=修订号），不在行内。schema 文件随 plugin 携带默认版、工程可覆盖
（§7 `ledgers.schemas`）；**schema 变更 = R5 必上桌** + 版本递增。
各账 id（S/D/B/F 前缀）由 ledger.py 自增分配，写入走文件锁原子追加。
**ledger.py 一切写入必带 `--layer` 自报参数**（各层 SKILL.md 骨架写死本层取值；
唯一的第五值 `user` 只有 feedback review 子命令收，见反馈账一节）；
写权与跃迁检查是**防呆不是防伪**——挡误用（会话忘了自己是谁），不设防恶意冒报，
冒报不在威胁模型内。

**原则文档条目**（idea 层写；md 表）：
`principle_id | scope | 原则一句话 | criterion_cmd（注册表命令）| 最近实测（ledger.py 回填，不手填）`
文档头带修订号；标注四色：【现状】/【已定要改】/【想法待定】/【已撤销】。

**spec**（部署层写）：文件头 `{approved_by, approved_date, approved_against_principles_version}`
——批准状态落盘，新会话不许拿草稿当已批。
每条目 `{item_id, principle_id, 内容, acceptance, depends_on[], priority, droppable}`。

**工单**（部署层写；最小字段契约，new1 挂接现有 issue-tracker 约定）：
`issue_id、spec_item(回指 item_id)、Status 行、acceptance(抄或引 spec 条目)、Blocked by`。

**批次报告**（部署层写；md）：头部 `{batch_id, spec_items[], run_ids[], date}`，
batch_id 规则 `<spec条目>-<YYYYMMDD>-<序号>`；正文零解读（发生了什么、数字多少、
证据路径），evidence_lint 同样管它。

**故事账 `story.jsonl`**（idea 层写）：
```json
{"claim_id": "S001", "claim": "一句话主张",
 "evidence_runs": ["run_id"], "baseline_runs": ["run_id"],
 "candidate_runs": ["run_id"], "selection_rule": "怎么从候选里挑的",
 "derivation_command": "派生量的复算命令", "principle_id": "P003",
 "role": "主结果|消融|反例|动机", "decided_by": "user", "date": "YYYY-MM-DD",
 "status": "active|retired", "retired_reason": "", "retired_date": "",
 "superseded_by": "", "note": ""}
```
写入校验：所有被引 run_id 必须存在于 runs.jsonl **且 status=ok**。

**抉择账 `decisions.jsonl`**（部署层账；任何层会话经脚本落账）：
```json
{"decision_id": "D001", "kind": "decision|grant",
 "where": "文件路径|spec条目|工单号（kind=grant 时可空）",
 "question": "抉择点或授权的事项类别",
 "options": ["...（grant 可空）"], "chosen": "可 grep 的具体值（grant 可空）",
 "reason": "...", "authorized_by": "用户原话 | discussed | grant:D00x",
 "scope": {"desc": "管哪一类", "path_globs": ["..."], "expires_at": "ISO|null"},
 "principle_ref": "P00x|null", "affects": ["spec条目/工单/run_id"],
 "decided_by": "user|agent", "raised_at": "ISO秒级", "decided_at": "ISO秒级",
 "status": "open|decided|withdrawn", "superseded_by": ""}
```
- `kind=grant` 是预授权体裁：where/options/chosen 可空，**scope 必须结构化填全**。
  有效授权视图 = kind=grant、status=decided、未过期、无 superseded_by。
- **decision_refs 是权威，affects 是它的物化索引**：写发射单的同一个 ledger.py 动作
  自动把 run_id 回填进 decision_refs 指向的每条抉择的 affects（触发者=写发射单的
  部署层会话，不是另一个步骤）；两者不一致以发射单为准，trace_check 校验一致性。
- R5 裁决强制入账（§3 R5），杜绝"裁决只活在 blocked.answer 自由文本里"。

**待决账 `blocked.jsonl`**（跃迁级写权）：
```json
{"blocked_id": "B001", "from_layer": "idea|deploy|run|oversight",
 "to_layer": "user|idea|deploy",
 "kind": "principle-gap|r5-choice|failure|other",
 "ref": "spec条目/工单/run_id", "question": "卡在哪、缺什么",
 "where": "（kind=r5-choice 必填）", "options": ["（kind=r5-choice 必填）"],
 "evidence": ["日志路径", "已试动作"], "raised_at": "ISO秒级",
 "status": "open|answered|closed|withdrawn",
 "answer": "", "answered_at": "", "answered_by": "",
 "grant_ref": "D00x|null（answered_by≠user 的 r5-choice 必填）",
 "decision_ref": "D00x|null"}
```
- 跃迁级写权（ledger.py 按 --layer 强制）：open 只能 from_layer 写；
  answered 只能 to_layer 写——**to_layer=user 的特例**：任何层的当场会话都可代笔，
  但字段级检查强制 answered_by=user 且 answer 含用户原话；
  closed/withdrawn 只能 from_layer 写。
- 渲染口径：open 归 to_layer 的待办，answered 归 from_layer 的待确认，**两者都算未决**；
  closed/withdrawn 不显示。
- **kind=r5-choice 的条目**：open 时必填 where/options；answer 跃迁必传 `--chosen`
  （可 grep 的具体值）——ledger.py 用 where/options/chosen/answer 四样**机械拼出**
  decision 条目（不猜自由文本），`decision_ref` 回指。拼装的字段映射规则成文：
  reason = answer 原文；decided_by = answered_by 为 user 时填 user、否则填 agent；
  authorized_by = answered_by 为 user 时填 answer（用户原话）、否则填
  `grant:<grant_ref>`——**answered_by≠user 的 r5-choice 答复必传 `--grant`**
  （落 grant_ref 字段，指向覆盖此分岔的有效授权），没有就拒，这正是 R6 的机验落点。

**反馈账 `feedback.jsonl`**（append-only 共笔，条目带 layer；两种行型）：
```json
{"fb_id": "F001", "kind": "suggestion", "date": "YYYY-MM-DD",
 "layer": "idea|deploy|run|oversight",
 "context": "哪个阶段/哪轮运行", "problem": "哪里不顺", "suggestion": "建议怎么改"}
{"fb_id": "F002", "kind": "review", "ref": "F001", "layer": "user",
 "verdict": "accepted|rejected", "note": "", "date": "YYYY-MM-DD"}
```
审查不改写旧行：用户审查会话经 ledger.py **追加 kind=review 行**（路由句"审一下反馈"）；
review 行 layer 恒为 `user`——`--layer` 的合法值因此有第五个 `user`，
只有 feedback 的 review 子命令收它（其余一切写入仍只收四个层/面值）；
建议条的有效状态 = 指向它的最新 review 行的 verdict，没有 review 行 = pending
（渲染器合并显示）。账本本体纯追加，shared-append 的机验（校验器只放行 append）
因此成立。

**发射单 `launch_orders/<run_id>.json`**（部署层写、运行层只读）：
```json
{"run_id": "部署层按工程命名规则给定，运行层不得自造", "spec_ref": "item_id",
 "issue_ref": "工单", "decision_refs": ["D00x"], "batch_id": "...",
 "registry_task": "注册表任务名", "argv": [...], "env_name": "...", "workdir": "...",
 "expected_commit": "...", "seed": 0, "dataset_version": "...",
 "resources": {"gpus": 1, "min_vram_gb": 0, "exclusive": false},
 "expected_runtime_s": 0, "depends_on": ["run_id"],
 "expected_outputs": [{"path_glob": "...", "min_bytes": 0, "min_lines": 0, "required_keys": []}],
 "metrics_cmd": "结构化抽数命令", "smoke_cmd": "...",
 "retry": {"max_attempts": 2, "retriable_errors": [], "allow_card_swap": true},
 "mutable_params": ["只管 argv 内参数白名单；seed 永不在内；资源分配归 retry 管"],
 "artifact_dir": "...", "created_by": "...", "created_at": "ISO秒级"}
```
- **结构化抽数契约（metrics_cmd 与 criterion_cmd 通用）**：stdout 最后一行必须是
  单个 JSON 对象——criterion_cmd 至少含 `{"value":…, "evidence_path":…}`
  （evidence_path 落缩减行 output_dir）；metrics_cmd 至少含
  `{"metric_name":…, "value":…, "n":…}`。入账脚本只解析这最后一行；
  解析失败 = 入账拒绝并按 R8 升级，禁止人眼读日志补数。
- 超时判定用 expected_runtime_s（×配置系数）；"卡死"判定用配置 stall_thresholds，两者分工。
- **与工程台账的顺序**：部署层写发射单 → 运行层铁轨读发射单发射并登记任务台账 →
  RUNMETA/台账回指 launch_order_ref。发射单不取代台账：发射单=要跑什么（前瞻），
  台账=跑成什么样（后验）。

**runs.jsonl**（定义权部署层：`runs.schema.json`；写权按行型分工——普通行归运行层、
判据缩减行归部署层，§1 第三例外；写入前脚本校验）：
行至少含 `run_id, status(ok|failed|oom|timeout|empty-output|killed|partial), output_dir,
runmeta_path, metric_name, value, n(分母), filter, seed, dataset_version, batch_id,
arm(实验组|对照组), principle_id(判据缩减行专用，普通行一律为 null),
commit(判据缩减行用，普通行为 null——普通行的 commit 在 RUNMETA), elapsed_s, gpu_count,
schema_version`。**status≠ok 的行 metric_name/value/n 允许为 null**。
**判据 run 是缩减行**（principle_id 非空即缩减行，一一对应）：
必填只有 run_id、status、principle_id、value（判据输出的计数/判定值）、
output_dir（证据文件路径）、commit（runs-append 自动抓 git HEAD，脏树加 `-dirty` 后缀）、
elapsed_s、schema_version，其余允许 null；run_id 由 ledger.py 按
`chk-<principle_id>-<YYYYMMDD>-<序>` 分配，其中日期段就是渲染脚本回填
"最近实测+日期"的日期来源（判据 run 不开发射单，这是 run_id"由部署层给定"的
唯一成文例外）。**执行契约**：由**部署层会话**当场执行 criterion_cmd
（注册表命令自带解释器与环境，不需要发射单的 env_name/workdir）；判据一律
轻量只读（R1 硬约束）——不占 GPU、不过脏树发射门禁、不登任务台账、不写 RUNMETA，
要重算力的证据先按普通 run 跑出产物、criterion_cmd 吃产物路径做检查
（output_dir 可指向该产物内的证据文件），溯源就是缩减行本身
（principle_id→原则文档 + commit + output_dir 证据文件）。
入账走 `ledger.py runs-append`（--layer deploy，§1 第三例外），
吃 criterion_cmd 的结构化输出（契约见发射单一节），同样过 schema 校验；
**只有退出码 0 且尾行 JSON 解析成功才落行（status=ok）**——退出非 0 或解析失败
一律不落行，按 R8 升级：判据没跑成不算实测，原则文档"最近实测"不更新。
**trace_check 反向链豁免**：principle_id 非空的行不查 run→发射单→工单回指，
改查 principle_id 存在于原则文档、criterion_cmd 在注册表。

**RUNMETA**（运行层写；**落点约定：artifact_dir 根下 `RUNMETA.json`**，
runs.jsonl.runmeta_path 回指）：commit + argv + 脏树清单 + `launch_order_ref` +
`attempt_no` + `env_name` + `outputs: [{file, format, fields:{字段名: 含义}}]`
（产物字段字典，由写文件的代码自动生成——监察面读格式的唯一权威来源）。

**任务台账**：补 `status 枚举（同 runs）、exit_code、attempt_no、gpu_ids、host、
tmux_session、started_at、ended_at、log_path、artifact_dir、launch_order_ref、
escalation_ref(blocked_id)、采样器判定(stall|dead|ok + 判定时间)`。

**错误分类表**（部署层写，error_classify.py 判）：
`{特征: {exit_code | output_check 判定 | log_regex} → 动作: 重试|换卡|升级}`。
**集群慢变量档案**：写权运行层（new1 挂接：ops/gpu_state.md）。

## 6 路由表（research-loop 薄壳的全部内容）

| 用户说 | 阶段 | 转给 |
|---|---|---|
| 我有个想法 / 讨论方向 | ① | idea-layer（谈；文献核实走 rails.literature 铁轨） |
| 定一下原则 / 这条进原则 | ② | idea-layer（原则模板 + R1） |
| 这轮做什么 / 出 spec | ③ | deploy-layer（spec + trace_check） |
| 施工 / 执行工单 | ④ | deploy-layer → rails.build（new1: ticket-run） |
| 跑实验 | ⑤ | deploy-layer 出发射单 → rails.gpu / rails.pipeline |
| 这个结果进故事吗 | ⑥ | idea-layer（用户拍板 → ledger.py story） |
| 写论文 | ⑦ | rails.paper（new1: paper-write），溯源对故事账取材 |
| 查 X / 让我亲眼看看 | 任意 | oversight → inspector |
| 看看输出里有什么 | 任意 | oversight → inspector（观察报告 = R3 子类） |
| 有什么在等我 | 任意 | ledger.py blocked 渲染（待决队列视图） |
| 这类事你自己定（授权） | 任意 | ledger.py grant 落账（结构化 scope，当场） |
| 我收回那条决定 | 任意 | 撤销体裁 → 对应账 status 变更 + superseded_by |
| 这个不行，重做（打回） | 任意 | 退回对应层，理由落批次报告 |
| 审一下反馈 | 收官后 | ledger.py feedback review（R9） |

## 7 工程挂接（plugin 通用 ↔ 项目铁轨）

仓库根 `research-loop.json`（写权归用户/主会话，变更过 git）：
```json
{"ledgers": {
   "principles": "METHOD.md", "story": "ops/story.jsonl", "timeline": "TIMELINE.md",
   "literature": "KNOWLEDGE_MAP.md",
   "specs": ".scratch/", "issues": ".scratch/*/issues/",
   "decisions": "ops/decisions.jsonl", "blocked": "ops/blocked.jsonl",
   "feedback": "ops/feedback.jsonl", "launch_orders": "ops/launch_orders/",
   "batch_reports": "plans/", "codemap": "MAP.md",
   "runs": "ops/runs.jsonl", "jobs": "ops/jobs.json",
   "schemas": "ops/schemas/", "runs_schema": "ops/schemas/runs.schema.json",
   "error_classes": "ops/error_classes.json", "cluster_state": "ops/gpu_state.md",
   "datasets": "DATA.md", "reports": "reports/",
   "runmeta": "<artifact_dir>/RUNMETA.json", "raw_data": "<raw_data_roots>/**"},
 "owners": {"principles": "idea", "story": "idea", "timeline": "idea", "literature": "idea",
   "specs": "deploy", "issues": "deploy", "decisions": "deploy",
   "feedback": "shared-append", "blocked": "per-transition",
   "launch_orders": "deploy", "batch_reports": "deploy", "codemap": "deploy",
   "schemas": "deploy", "runs_schema": "deploy", "error_classes": "deploy",
   "datasets": "deploy",
   "runs": "per-row-type", "jobs": "run", "cluster_state": "run", "runmeta": "run",
   "raw_data": "run", "reports": "oversight"},
 "registry_cmd": "python3 run.py",
 "registry_query": "python3 run.py show --list",
 "dirty_exempt_globs": ["ops/jobs.json*", "ops/runs.jsonl", "RESULTS.md", "*.lock"],
 "stall_thresholds": {"no_log_growth_s": 0, "gpu_idle_s": 0, "startup_grace_s": 0},
 "runtime_factor": 3,
 "rails": {"build": "ticket-run", "gpu": "gpu-run", "pipeline": "probe-pipeline",
           "paper": "paper-write", "literature": "update-knowledge-map"},
 "raw_data_roots": ["/net/.../reproduce/new1/"]}
```
- `ledgers` 是**完整账本注册表**（监察面追溯起点），§1 写权表里的每一本都有路径；
  值允许路径模板（`<artifact_dir>`、`<raw_data_roots>` 占位）。
- `owners` 的**键集合与 ledgers 严格相等**（配置校验器查这个），值与 §1 的写权约定
  （三层写权表 + 监察面条目）一一对应。**值域成文**：层名 `idea|deploy|run`、
  面名 `oversight`、规则名 `per-transition`（按 §5 跃迁规则机验）| `shared-append`
  （只许追加，条目 layer 自证）| `per-row-type`（runs.jsonl 专用，§1 第三例外：
  普通行归 run 层经工程记账脚本、判据缩减行归 deploy 层经 runs-append，
  机验 = runs-append 只收 `--layer deploy`）——校验器按这七个值收，别的都非法。
- `registry_query` 必须是**只读且不受脏树门禁**的动作；样例值待 new1 核实
  （§9 挂接清单第 5 项），不满足就加只读入口。
- 没有配置文件 = 工程未接线：铁轨动作与一切记账都拒绝——账本路径全部来自
  `ledgers`，没有配置就没有落点；只有谈可用。接线第一步 `ledger.py init`
  从 plugin 内模板生成 research-loop.json 骨架，人工填对路径后过配置校验。
- 数据集清单挂 DATA.md（new1 侧加结构化表头：dataset_id/路径/生成 commit/行数/
  校验和/当前版本）。

## 8 端到端剧本（验收时走一遍）

1. "我有个想法" → idea-layer 陪谈，文献入 KNOWLEDGE_MAP（rails.literature）。产出候选假设。
2. 谈熟 → 写/改原则，每条过 R1。用户拍板。
3. 出 spec（含 acceptance/depends_on，文件头记批准）→ trace_check 全绿。用户拍板。
4. spec → 工单（§5 工单契约）→ rails.build 施工。抉择点走 R5 三问；
   自决先查有效授权视图（开工必读②），命中才自决并留痕（R6）。
5. 部署层出发射单（含 seed/dataset_version/decision_refs；同一动作把 run_id 回填进
   被引抉择的 affects）→ 冒烟 →
   判据实跑（criterion_cmd 结构化输出进 runs.jsonl 带 principle_id）→
   证据报告（R3）→ evidence_lint + verify_report 过 → 用户亲验 →
   批量发射走 rails.gpu（铁轨读发射单、登记台账、RUNMETA 回指）；
   output_check 防空产物；数字只经 metrics_cmd/criterion_cmd 入账。
6. 跑完 → inspector 观察报告（RUNMETA.outputs 读格式）+ spotcheck 抽查清单 →
   用户读原件。regression_check 对照故事账，冲突清单落 reports/。
7. 用户拍板进故事 → ledger.py story 记账（run 存在性+status=ok 校验）。
8. 回 1，或走 rails.paper，数字溯源对故事账。
9. 任意时刻"查 X" → inspector 顺账本注册表挖到原始文件（runmeta_path→RUNMETA→
   outputs 字典）；"有什么在等我" → 待决队列渲染。
10. 收官：各层反馈进反馈账；用户说"审一下反馈"时走 R9 审查。
    全程失败按 R8 走楼梯（error_classify.py 判，不经 LLM）。

## 9 验收标准

- 五个 skill + inspector agent + 八个脚本 + schemas/ 齐备，plugin 可安装、路由表可触发。
- 每个脚本有可跑自测。重点用例：
  - trace_check：spec 条目指不回 principle_id → 报错；run→工单断链 → 报错；
    判据缩减行（principle_id 非空）→ 不按断链报错，
    改验 principle_id 在原则文档、criterion_cmd 在注册表；
    decision→run 反查（经 decision_refs 与 affects）返回正确集合。
  - ledger.py story：run_id 不存在或 status≠ok → 拒收；撤销 → status+superseded_by。
  - ledger.py blocked：状态机与跃迁级写权（--layer 传错 → 拒），非法跃迁 → 拒绝；
    kind=r5-choice 缺 where/options 开条 → 拒，answer 未传 --chosen → 拒；
    answered 后自动同步 decision 条目并回填 decision_ref（机械拼装，不解析自由文本）；
    answered_by≠user 的 r5-choice 答复未传 --grant → 拒；
    to_layer=user 特例：answered_by≠user → 拒。
  - ledger.py grant：无结构化 scope → 拒收；过期/被 superseded 的 grant
    不进有效授权视图。
  - ledger.py feedback：review 行只能经审查子命令追加（--layer user），
    layer≠user 的 review 行或改写旧行 → 拒。
  - ledger.py runs-append：--layer≠deploy → 拒；criterion_cmd 退出非 0
    或尾行非 JSON → 不落行、升级。
  - output_check：退出码 0 + 空产物 → 判 empty-output，不得记 ok。
  - error_classify：三类特征（exit_code / output_check 判定 / log_regex）各一条规则
    命中正确动作；无命中 → 升级。
  - evidence_lint：含"通过"；或有数字无复现命令 → 报违禁。
  - verify_report：伪造计数/不存在路径/被改动的摘录 → 逐条揪出。
  - spotcheck：总体指纹变化后同种子重抽 → 报"总体已变"，不得静默给出不同样本。
  - regression_check：新数字与 active claim 冲突 → 出清单落 reports/。
- 在 new1 挂接后，端到端剧本 §8 的 1-3 步（不动 GPU）真实走通一遍。
- **铁轨兼容承诺（修订版）**：不改变 ticket-run/gpu-run/probe-pipeline/paper-write
  的对外流程与现有行为；new1 挂接所需的**增量改动单列挂接清单**进实施计划，
  已知五项：① 发射器补写 launch_order_ref 等回指字段；② record.py 挂 runs schema 校验
  （普通行入口；判据缩减行的入口是 ledger.py runs-append，两入口同一份 schema、
  共用文件锁——record.py 现有锁协议需核实兼容）；③ RUNMETA 增 outputs 字典；
  ④ 发射器接受部署层给定的 run_id（new1 发射器现以任务
  name 为入参，大概率零改动，需核实）；⑤ registry_query 的只读免门禁入口核实/新增。
  每项逐项过工程自检；①③④若涉及流程改动，先回本 spec 走 R5。

## 10 不做什么（YAGNI）

- 不重写任何现有铁轨 skill 的内容，只路由挂接（增量字段见 §9 挂接清单）。
- 不做多研究线并行目录树（schema 已带主键，将来平移不返工）。
- 不做 web 界面；监察面产出是文本报告。
- 不做自动触发（hooks）；路由由对话触发。
- **后置（audit P2 + 二轮验收判定的非阻塞项）**：reports/ 与待决账的通知/时限提醒
  （先用"开工必读"和会话出口回报顶）、下行"临时指令/补证请求"专用体裁
  （先用 spec 的 exploratory 标记和路由句顶）、台账成本字段的可行性查询视图
  （elapsed_s/gpu_count 已入账，视图后置）、监察会话只读性的钩子验证。
- md 系统最终定形（哪些渲染到根目录、叫什么名）随实施定，不在 spec 锁死。
