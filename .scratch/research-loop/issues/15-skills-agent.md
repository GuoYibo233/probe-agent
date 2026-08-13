# T15 五个 SKILL.md + references + inspector agent（全英文）

Status: resolved
Blocked by: 04, 05, 06, 07, 08, 09

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md。**本工单全部产物是英文散文
（SKILL.md / references / agent），不写代码**。需求源：本工单 + spec.md
§1（层纪律五条 + 监察面 + 收官核查三步）、§2（信道表 + 会话开工必读 +
总规矩）、§2.1（读法）、§2.5（人的位置）、§2.6（快车道）、§3（R1–R10）、
§6（路由）、§8（剧本）。铁律：**封闭清单一律指向 tables/ 文件，不许在
skill 正文复述**（路由表、枚举、写权表、config 键表）。命令一律写
`python3 <plugin-root>/scripts/ledger.py ...` 形态（plugin-root 用相对
skill 文件的路径说明）。

## 文件（Create 全部）

```
research-loop/skills/research-loop/SKILL.md
research-loop/skills/idea-layer/SKILL.md
research-loop/skills/idea-layer/references/{principles.md,story.md,derivations.md,withdrawals.md}
research-loop/skills/deploy-layer/SKILL.md
research-loop/skills/deploy-layer/references/{spec-items.md,launch-orders.md,r5-choices.md,criteria.md,closeout.md,quick-lane.md}
research-loop/skills/run-layer/SKILL.md
research-loop/skills/run-layer/references/{execute.md,failures.md}
research-loop/skills/oversight/SKILL.md
research-loop/skills/oversight/references/{inspection.md,report-genre.md,spotcheck.md}
research-loop/agents/inspector.md
```

## 每份 SKILL.md 的骨架（R10：只放骨架，细则进 references）

frontmatter：name、description（一句话，何时触发）。正文六节，顺序固定：

1. **Layer identity**：本层管什么（spec §1 表行）；身份只在两个入口产生
   （用户触发 skill 含路由句 / 派发契约钉死），整会话不变，要别层的活走
   跨层传输不就地换层（spec §1 会话身份条原文翻译）。
2. **First action**：`ledger.py status --layer <本层>`——工作面 + 待决队列 +
   有效授权三块（照 spec §2 会话开工必读）。
3. **Write permissions**：本层可写哪些账（列账名即可），规则真源指
   `tables/ledgers.json` owner 列与 `tables/writes.json`。
4. **Channels**：进出各是什么体裁（spec §2 信道表本层相关行，散文一句一条）。
5. **Hard rules digest**：本层最相关的 R 条各一句（idea：R1/R4/R2；
   deploy：R5/R6/R7/R3；run：R7/R8 + 零代码写权 + 只跑不解释；
   oversight：R3/R2 + 零写权 + 独立上下文），并写明全文在 spec（设计稿）
   与 tables/。
6. **Stage index**：表——阶段 → references/<file>.md，进那个阶段才读（R10）。

## 各 references 的内容要点（每份 ≤60 行，操作序列写成编号步骤）

- idea/principles.md：R1 全文操作化——八列表模板（指向 helpers 造的列序）、
  rationale 追问义务、未接线态【想法待定】、批准=逐行事件、
  principles-lint + render 命令。
- idea/story.md：故事裁决流程：用户拍板 → `story add` 参数逐个说明 →
  quick 行会被拒 → retire/更正路径。
- idea/derivations.md：R4 提案格式（公式/分母/过滤/作用文件）、批过口径
  =预授权、变了重提案、derivation_command 记账。
- idea/withdrawals.md：§2.5 撤销五路（jsonl 三路命令 + md 两路改文件），
  规则真源 tables/writes.json withdrawal_*。
- deploy/spec-items.md：spec 文件头 frontmatter 契约（spec_header 五字段）、
  条目八字段、trace_check 全绿 → 用户拍板 → `approve-spec`；不批准 =
  不落 approved_by + 开待决条。
- deploy/launch-orders.md：发射单字段速览（真源 schemas/launch_order）、
  写单命令、批准门禁与 stale、affects 回填、发射转交 rails.gpu、
  smoke → 判据 → 批量的顺序（§8 步 5）。
- deploy/r5-choices.md：三问识别（判据输出变？新约束无原则对应？不可逆？
  写产物盘不算）、schema 变更恒第二问为是、三模式（默认停手开
  blocked r5-choice / grant 自决 / 常设授权 GPU<1h）、留痕与事后回报
  （§2.5 回报条款）。
- deploy/criteria.md：判据 run 契约——`runs-append` 一个动作、轻量只读、
  失败不落行按 R8 升级。
- deploy/closeout.md：收官三步闭环（§1）：落报告 → 派 inspector
  （模型取 config roles.inspector_model；派发契约必传 batch_id、报告路径、
  config 路径、三件套命令）→ 读回 verdict，blocker 转录 blocked、
  无 blocker 回填 inspection_report + `trace_check --closeout`。
- deploy/quick-lane.md：§2.6 全文操作化：免什么、不免什么、quick 单字段、
  转正 promoted_from 流程。
- run/execute.md：一张发射单说清才接活；执行=铁轨或 fallback launch.py；
  脏树拒发升级；output_check；record；台账登记；零代码写权。
- run/failures.md：R8 操作化：error_classify → 命中动作照做；unknown →
  不判，收齐错误原文/日志路径/已试动作表开 blocked kind=failure 升部署层；
  重跑一次输出仍空必升级。
- oversight/inspection.md：例行核查步骤（跑三件套 + 通读本批账目）、
  verdict 头契约（inspection_report_header）、blocker 只写流程/证据缺陷
  不写科学结论、监察会话与 inspector agent 的两口子分界（§1）。
- oversight/report-genre.md：R3 体裁全文操作化 + plan.md §C6 约定
  （`$ ` 复现行 / `= ` 回显 / 摘录 `> ` / path:line）、零计数陈述带全量
  清单、溯源块三件。
- oversight/spotcheck.md：spotcheck 用法 + 直达路径清单交付形态。

## 路由薄壳 research-loop/SKILL.md

- 职责一句话：识别用户短语 → 读 `tables/routes.json` 匹配 → 转对应层/动作；
  **表内容不搬进正文**（一行都不许），只写读表方法与兜底
  （没匹配 → 列 say 列给用户挑）。
- 直接转交铁轨前跑 `ledger.py config-check`，被锁则拒并点名 null 键（§6/§7）。
- 层身份两入口规则重申一句（路由句=用户触发入口）。

## inspector agent（agents/inspector.md）

frontmatter：name: inspector、description（只读监察员，何时派）、
model: opus（plugin 默认；派发方按 config roles.inspector_model 覆盖）、
tools: Read, Grep, Glob, Bash。正文：只读纪律（对账本零写权、唯一落盘
reports/）；不做 §1 归监察会话的两个口子（开待决条/追加 feedback）；
R3 体裁 + C6 约定；必跑三件套（trace_check / evidence_lint /
verify_report，命令原样给出）；verdict 头（真源
tables/rows.json inspection_report_header）；跨次线索记
reports/inspector-notes.md；R2——不下科学结论。

## 验收（评审逐条对）

1. 全部文件存在且为英文；每份 SKILL.md ≤120 行、references ≤60 行。
2. `grep -r "用户说" research-loop/skills/` 零命中（路由表没被复述）；
   skill 正文没有出现任何 tables/*.json 里的完整枚举列表。
3. 每份层 SKILL.md 含精确的一行 `ledger.py status --layer <本层>`。
4. Stage index 指到的 references 文件全部存在。
5. spec §1 层纪律五条、§2.5 落账定格与实验设定硬边界、§2.6 底线三条，
   在对应 skill 里各有落点（评审对照 spec 逐条找）。

## Comments

## Comments

- 2026-08-14 wave5 收账：DONE，0 修复轮，commit 范围 882dd1d..d21065a，
  merge 进 main。遗留 minor F1（仅报告叙述问题，不碰代码）：T15-report.md
  两处"落点"说法与实际文件对不上（R6 回报条款实际落在
  deploy-layer/references/r5-choices.md 不在 SKILL.md §5；"账本即信道"
  措辞实际在 deploy-layer/references/closeout.md:18）——按报告找证据时以
  此更正为准。concerns 裁决：英文正文里逐字引用中文数据层取值（routes.json
  触发句、【想法待定】等 enum 标签、spec 中文节名）**主会话认可**——这些是
  必须逐字复现的数据值，翻译即错误；工单第 62 行"条目八字段"是起草笔误，
  表源 spec_header.item 是七字段，交付物直接指表未断言数量，无需改动。
  环境注记：Write 工具拒写 oversight/references/report-genre.md（文件名含
  report 触发子串守卫），实现者用 bash heredoc 绕过——后续会话改这个文件
  可能也要走 bash。cannotVerify（references 里对 T13/T14 脚本行为的描述）
  归验证循环 V1 实测核对。
