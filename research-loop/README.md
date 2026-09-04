# research-loop 插件本体（v2，2026-09-05 起施工的骨架版）

这个目录是 research-loop 插件的本体，留在 new1 仓库里，不另开仓库（00 分册裁决 2）。插件给一个研究仓库装上五个角色：idea、deploy、run、analysis、reviewer。角色之间的交流全部走研究仓库 `loop/` 目录下的九本账，账只能经过 `bin/rl` 这个命令行工具读写；插件级钩子只拦两类离谱的写文件，写别的角色的目录和直接写 `loop/`（06 分册第 13 行）。

设计真源是 `plans/research-loop-parts/` 的 00 到 30 分册，施工步骤在 30 分册第三节，2026-09-04 的施工指南在 `plans/2026-09-04-research-loop-work-guide.md`。代码里每条逻辑都要能指回分册号和行号；没裁定的地方写成 `PENDING(问题 NN)` 或者 `PENDING(22 第 113 行)`，指回 `plans/research-loop-parts/sync-inbox.md` 或者分册条目。

## 这棵树每个目录装什么（08 分册第四节）

| 目录或文件 | 装什么 |
|---|---|
| `.claude-plugin/plugin.json` | 插件清单 |
| `skills/` | 六个 skill：入口一个，五个角色各一个；角色 skill 的头部不声明钩子 |
| `agents/` | 五份角色 agent 定义，只做塑形（提示词、预加载角色 skill、收窄工具面），不写钩子 |
| `common/` | 公共母版：公共规矩、词表、五栏规格、读法、判断类检查问题清单，带 `rules_version` |
| `tables/` | 九本账的清单、派活单的状态转移表、角色 json、gyb 的 use case 表 |
| `schemas/` | 九本账的行格式 |
| `scripts/` | 入账与查询的实现 |
| `bin/rl` | 命令入口，含 status、inbox、trace、回收、doctor |
| `hooks/` | 插件级钩子文件 `hooks/hooks.json` 加脚本：写权钩子、登记钩子、销号钩子 |
| `monitors/` | 一个发射看门狗，只在 run 上线的时候启动 |
| `tests/` | 测试，入口 `python3 research-loop/tests/run_all.py` |

不建 `workflows/`：派活是每张单各起一个子会话，不需要扇出脚本（08 分册第 102 行）。

## 模型：fable 是 gyb 2026-08-16 点名的例外

五个角色由 agent（子会话或者 workflow）调用的时候，run、deploy、analysis 用 opus，idea、reviewer 用 fable；gyb 手动加载角色的时候跟当前会话的模型一致（00 分册裁决 3，写进五份角色 json 的 `model` 字段）。idea 和 reviewer 用 fable 与本机 `~/.claude/CLAUDE.md` 的「subagent 默认不用 Fable」不一致，按工程内为准：fable 是 gyb 2026-08-16 点名的例外，只对插件运行时生效，不对施工时派去写代码或者写文档的子会话生效（HANDOFF 第八节）。

## 状态与提交规矩

2026-09-05 施工步 1 做完：旧插件（0.1.0）的文件整体退役，留在 commit b63519b 之前的历史里，工作树里不留任何旧文件（00 分册裁决 1）。空目录用 `.gitkeep` 占位，因为 git 不记录空目录。

commit 前缀施工期用 `research-loop v2:`，用起来之后改母版用 `research-loop rules:`，改完运行一遍 `tests/run_all.py`（30 分册第三节）。
