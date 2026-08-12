# research-loop plugin — 设计 spec

**Status:** needs-triage
**日期：** 2026-08-13（brainstorming 会话定稿）
**形态：** 机器级 plugin（跟机器走），工程铁轨通过仓库根配置文件挂接。

## 0 一句话

把研究循环（谈 idea → 定原则 → 定工程目标 → 施工 → 跑实验 → 故事裁决 → 写作）
做成一套分层的 plugin：三层干活、四信道通信、判据闸门把关、
三本结构化账沉淀、一个独立监察面供用户亲验一切细节。

## 1 三层 + 监察面

层按**指挥权**切，每层只管自己的，跨层只认信道上的落盘文件。

| 层 | 干什么 | 说什么语言 | 账本写权 |
|---|---|---|---|
| idea 层 | 谈想法、定原则、裁决什么进故事、批准计算 | 主张、假设、证据 | 原则文档、故事账、TIMELINE、KNOWLEDGE_MAP |
| 部署层 | 原则 → spec → 代码 → 发实验 → 收数字 | spec、注册表、run_id | spec、工单、抉择账、批次报告、代码地图 |
| 运行层 | 机械执行：跑命令、落日志、钉版本 | 命令、日志、台账 | 数字账（runs.jsonl）、任务台账、RUNMETA、原始输出 |

**监察面**不是层：不在指挥链里，谁也不指挥、零写权、只读一切
（所有账本 + 代码 + 原始输出 + 抉择账），唯一产出是给用户的证据报告。
监察必须用独立上下文（干净会话 / 独立 agent），做事的会话不许自查顶数。

**解读不过层**：上行只有事实，一切解读发生在 idea 层、由用户拍板。
派生量计算（平均、比例等）是 idea 层活动：提案、批准、算、附命令都发生在 idea 层（R4）；
部署层只跑既有的机械汇总管道（record → RESULTS 渲染），不发明新算法。

## 2 四条信道

| # | 方向 | 体裁 | 规矩 |
|---|---|---|---|
| 1 | idea → 部署 | 原则文档 + spec | spec 每条指回原则条目；指不回去 = 原则有缺，先回 idea 层补 |
| 2 | 部署 → idea | 数字账、批次报告、BLOCKED 上报 | 报告零解读；撞到原则没覆盖或代码抉择点，停手上报，不许即兴代决 |
| 3 | 部署 → 运行 | 注册表命令、发射单、工单 | 不在注册表不许跑；发射前 commit；产物钉 RUNMETA |
| 4 | 运行 → 部署 | 日志、RUNMETA、台账、采样器判定 | 已有铁轨，plugin 只定契约不重造 |

总规矩：**可追溯链**（工单→spec→原则条目→idea，发射→commit，一路能追）；
**升级走楼梯不跳层**；**一切通信落盘，不走会话记忆**。

## 3 七条硬规矩（全 plugin 通用）

- **R1 原则三件套**：每条原则 = 原则一句话 + 判据怎么跑 + 判据最近一次实测结果和日期。
  写不出判据的原则退回 idea 层重谈。（样板：new1 METHOD.md §2.2 的 R1-R4 表）
- **R2 机验人判**：判据机器跑，判断人来下。AI 在验收里只做两件事：把检查跑起来、把原始证据摆到用户面前。
- **R3 证据体裁**：判据/监察/观察输出只许三样——计数、差异定位（分叉点原文并排）、
  可点开的文件路径。"通过/没问题/符合预期"等结论词是违禁词，脚本 lint 强制。
- **R4 计算授权**：对数据只许忠实呈现原始值。任何派生量（平均、比例、去重计数）先提案
  ——公式、分母、过滤条件、作用文件——用户批了才算；算完连同命令附在结果旁，可复算。
- **R5 抉择点上桌**：施工撞到方案分岔（如 chat vs completions、vllm vs 其他）必须停下讨论，
  走信道 2 上报。
- **R6 授权自决留痕**：用户说"你自己定"之后 AI 可以定，但每个自决点写一条结构化记录进抉择账。
- **R7 确定性脚本化**：账本写入、schema 校验、溯源检查、抽样、lint、jsonl→md 渲染，
  一律脚本干，LLM 只做需要判断的活。渲染产物不手改。

## 4 组件结构（每层一件专责，不多不杂）

```
research-loop/                      # plugin 根
├── .claude-plugin/plugin.json
├── skills/
│   ├── research-loop/SKILL.md      # 路由薄壳：认阶段 → 转层，含路由表（§6）
│   ├── idea-layer/SKILL.md         # 谈idea规程、原则文档模板、故事裁决流程、R4 计算授权
│   ├── deploy-layer/SKILL.md       # spec 规矩、工单化、R5/R6、判据验收流程
│   ├── run-layer/SKILL.md          # 运行层契约：项目须提供注册表/钉版本/台账；挂接项目铁轨
│   └── oversight/SKILL.md          # 监察面：报告体裁、独立性纪律、抽查流程
├── agents/
│   └── inspector.md                # 只读监察员：零写权、R3 体裁、监察+观察两种报告；
│                                   # frontmatter 钉 model: opus（全局规矩：派发必须显式指定模型）
└── scripts/                        # 全部确定性，按层归属
    ├── story.py                    # (idea) 故事账写入+校验：run_id 必须真实存在于数字账
    ├── decisions.py                # (deploy) 抉择账写入+校验
    ├── trace_check.py              # (deploy) 溯源检查：spec→原则、工单→spec 引用全落地
    ├── spotcheck.py                # (oversight) 固定种子抽 N 样本，出直达路径清单
    ├── evidence_lint.py            # (oversight) 证据报告违禁结论词扫描
    └── render.py                   # 各账本 jsonl → md 渲染（渲染产物不手改）
```

每个 skill 只写：本层职责、本层账本写权、触到本层的信道。跨层内容不写。

## 5 账本 schema（结构化，单写多读，主键贯通）

**故事账 `story.jsonl`**（idea 层写，脚本代笔）：
```json
{"claim_id": "S001", "claim": "一句话主张", "evidence_runs": ["run_id", ...],
 "role": "主结果|消融|反例|动机", "decided_by": "user", "date": "YYYY-MM-DD",
 "status": "active|retired", "note": ""}
```

**抉择账 `decisions.jsonl`**（部署层写，脚本代笔）：
```json
{"decision_id": "D001", "where": "文件/阶段", "question": "抉择点是什么",
 "options": ["..."], "chosen": "...", "reason": "...",
 "authorized_by": "user原话或discussed", "decided_by": "user|agent", "date": "YYYY-MM-DD"}
```

**判据三件套**住原则文档内（同 METHOD.md §2.2 表格式）：判据 | 怎么跑 | 最近实测+日期。

原有账本（runs.jsonl、jobs.json、TIMELINE、RESULTS、DATA、KNOWLEDGE_MAP）全不动，
按 §1 表归层。故事账/抉择账的存放路径由工程配置定（new1：`ops/` 下，渲染到根目录）。

## 6 路由表（research-loop 薄壳的全部内容）

| 用户说 | 阶段 | 转给 |
|---|---|---|
| 我有个想法 / 讨论方向 | ① | idea-layer（谈；文献核实派项目侧 agent） |
| 定一下原则 / 这条进原则 | ② | idea-layer（原则模板 + R1） |
| 这轮做什么 / 出 spec | ③ | deploy-layer（spec + trace_check） |
| 施工 / 执行工单 | ④ | deploy-layer → 项目铁轨（new1: ticket-run） |
| 跑实验 | ⑤ | deploy-layer 调度 → 项目铁轨（new1: gpu-run / probe-pipeline） |
| 这个结果进故事吗 | ⑥ | idea-layer（用户拍板 → story.py 记账） |
| 写论文 | ⑦ | 项目铁轨（new1: paper-write），溯源对故事账取材 |
| 查 X / 让我亲眼看看 | 任意 | oversight → inspector |
| 看看输出里有什么 | 任意 | oversight → inspector（观察报告体裁） |

## 7 工程挂接（plugin 通用 ↔ 项目铁轨）

仓库根放 `research-loop.json`：
```json
{"ledger_dir": "ops", "registry_cmd": "python3 run.py",
 "rails": {"build": "ticket-run", "gpu": "gpu-run", "pipeline": "probe-pipeline",
           "paper": "paper-write", "literature": "update-knowledge-map"},
 "raw_data_roots": ["/net/.../reproduce/new1/"]}
```
plugin 的 skill/脚本只认这个配置，不写死任何工程路径。没有配置文件 = 该工程未接线，
run-layer/deploy-layer 的铁轨动作一律拒绝，只有谈和记账可用。

## 8 端到端剧本（验收时走一遍）

1. "我有个想法" → idea-layer 陪谈，文献入 KNOWLEDGE_MAP。产出候选假设。
2. 谈熟 → 写/改原则，每条过 R1。用户拍板。
3. 出 spec → trace_check 全绿。用户拍板。
4. spec → 工单 → ticket-run 施工。抉择点走 R5/R6，decisions.py 记账。
5. 冒烟 → 判据实跑 → 证据报告（R2/R3，evidence_lint 过）→ 用户亲验 → 批量走 gpu-run。
6. 跑完 → inspector 出观察报告 + spotcheck 抽查清单 → 用户读原件。
7. 用户拍板进故事 → story.py 记账（run_id 校验）。
8. 回 1，或走 paper-write，数字溯源对故事账。
9. 任意时刻"查 X" → inspector 顺 run_id 挖到原始文件。

## 9 验收标准

- 五个 skill + inspector agent + 六个脚本齐备，plugin 可安装、可被路由表触发。
- 六个脚本各有可跑的自测（造假数据 → 校验/渲染/lint 行为符合 §5/§3）。
- trace_check 对"spec 有一条指不回原则"的假样例正确报错。
- evidence_lint 对含"通过/没问题"的假报告正确报违禁。
- story.py 对不存在的 run_id 正确拒收。
- 在 new1 挂接后，端到端剧本 §8 的 1-3 步（不动 GPU）真实走通一遍。
- 与 new1 现有 skill 零冲突：不改 ticket-run/gpu-run/probe-pipeline/paper-write 任何一行。

## 10 不做什么（YAGNI）

- 不重写任何现有铁轨 skill 的内容，只路由挂接。
- 不做多研究线并行的目录树（现在一条线；将来要了平移，账本 schema 已带主键不用返工）。
- 不做 web 界面；监察面产出是文本报告。
- 不做自动触发（hooks）；路由由对话触发。
- md 系统的最终定形（哪些渲染到根目录、叫什么名）随实施定，不在 spec 里锁死。
