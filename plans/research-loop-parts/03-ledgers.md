# 九本账的行格式与入账规则

> 这份覆盖三样：九本账共同的总规矩（只增不改、version 与 status、锁与写序、能写就能查）、公共骨架七样加两个可选字段、九本账每一本的字段级行格式，外加 `bin/rl` 的退出码。
> 不覆盖的：decisions 的行格式、编号规则和来源三类写在 `02-decisions.md`；handoffs 的行格式和派活单状态转移表写在 `04-handoffs-and-sessions.md`，会话的登记、销号、回收也在那一份（这份只写 sessions 的行格式）；每条子命令怎么写、`rl status` 和 `rl inbox` 列什么、doctor 扫什么，都在 `05-rl-cli.md`；哪个角色能调哪条写命令在 `06-hooks-and-permissions.md`；快车道的进出动作在 `07-quick-lane.md`；阈值和配置文件在 `08-trees-init-and-host.md`；母版 `rules_version` 和反馈账的用法在 `09-common-and-feedback.md`。
> 源：设计文档的「账本」一节、原则 4、原则 6、原则 1 里 gyb 豁免那一段、「分权与钩子」的第二层；施工计划第二节词表、第三节九本账的字段级行格式、第六节末尾的退出码与锁那两段。

## 账本的总规矩

九本账全放 `loop/`，一行一条 json，不用 markdown，只经 `bin/rl` 进出。角色会话直接 Write 或 Edit `loop/` 由钩子拦下，见 `06-hooks-and-permissions.md`。`loop/` 进 git：每次 commit 顺手带上，不另设 commit 动作，账本 diff 永远是纯追加行；`loop/*.jsonl` 和 `loop/.lock` 不算脏树，宿主白名单那一处见 `08-trees-init-and-host.md`。

只增不改。任何「改」都是追加一版，一行写下去就不再动。默认查询对每个主键只取最新版，历史全在文件里，要旧版本得显式要。

每本账都有 `status` 字段，runs 和 sessions 也不例外。入账校验按 `status` 查：一个字段必不必填看这一版的 `status`，不看全局。

前提查在交付那一刻，不查在开单那一刻。开单只查「这一行说得清自己是什么」，交付才查「东西齐不齐」。哪一版查哪些前提写在转移表里，见 `04-handoffs-and-sessions.md`。

锁是 `loop/.lock`，一把全局文件锁。扫号、分配编号（含 `ql_tag`、`run_id`、`batch`）、追加，这三步放在同一把锁里，不许扫完号再排队写，否则同一个角色的两个会话会撞号。

编号的序号从 1 起，四位是最小宽度不是上限（`iss-0001` 到 `iss-9999`，下一条是 `iss-10000`），rl 排序按数值不按字符串；编号一旦发出去永远不重发、不回收。decisions 的编号带 actor 前缀（`dec-idea-0007`），六个文件各排各的序号，规则在 `02-decisions.md`。

跨两本账的写入定死写序：先写 issue 拿到编号，再写单子那一行引它。中间崩了顶多多一条没人引的 issue，`rl doctor` 扫得出来。

能写就能查。每本账都配写和查两头的命令，能 add 就有 show 和 list，sessions 和 runs 也不例外。查询命令谁都能调，读不设权。命令清单在 `05-rl-cli.md`。

gyb 的豁免只到权限那一层。actor 是 gyb 时跳过「谁能调」和转移表的「谁能写」；必填字段、路径存在、引用存在这些完整性校验对 gyb 同样生效。gyb 要硬写就加 `--force --reason`，rl 照写并把原因记进账行的 `force_reason`。`--force` 是 gyb 的权：actor 是角色的命令带 `--force` 一律拒收，退出码 3，错误信息附「开 issue 给 gyb」的命令；角色遇到完整性校验拒收只有两条路，把行补齐，或开 issue 让 gyb 决定要不要硬写。角色会话里 `--as-gyb --quote --force --reason` 这个组合按原则 1 算 gyb 身份写，照写，`quote` 和 `force_reason` 都记进账行。

## 公共骨架七样加两个可选字段

每本账的每一行都有这七样：

| 字段 | 取值或格式 | 说明 |
|---|---|---|
| `id` | 每本账各自的形状 | 主键；runs 的主键是 `run_id`，scratch 的主键是 `ql_tag` |
| `version` | 整数，从 1 起 | 同一个 `id` 的新版本是新的一行，默认查询只取最新版 |
| `status` | 每本账各自的取值 | 校验按它查 |
| `ts` | ISO 8601 | 写入时间 |
| `actor` | 五个角色之一或 `gyb` | 写这一行的人 |
| `session_id` | 会话 id，裸终端记 `cli` | 写入会话 |
| `schema_version` | 整数，从 1 起 | 行格式的版本，九本账共用一个数：任何一本账的字段表改了（加字段、改取值域、改必填条件）整套加一；rl 写每一行时填当前的数，读旧行时按行上标的那一版字段表解析和校验，不拿今天的表挑旧行的错 |

另外两个字段可选，都是「这一行不是常规写入」的痕迹：`fix_for` 是 doctor 修账时记的扫描项名字（doctor 打印的修法命令一律带 `--fix-for <扫描项>`），`force_reason` 在 gyb 用 `--force` 时必填、记硬写的理由。设计文档原来只写了 `fix_for` 一个，2026-08-17 裁定两个都要，设计文档那一句回去改。

## 九本账的名字和文件

| 中文名 | 英文名 | 文件 |
|---|---|---|
| 决定账 | decisions | `loop/decisions.<actor>.jsonl`，五个角色加 gyb 六个文件 |
| 问题条 | issues | `loop/issues.jsonl` |
| 派活单 | handoffs | `loop/handoffs.jsonl` |
| 数字账 | runs | `loop/runs.jsonl` |
| 授权 | grants | `loop/grants.jsonl` |
| 反馈账 | feedback | `loop/feedback.jsonl` |
| 口径账 | evaluations | `loop/evaluations.jsonl` |
| 会话账 | sessions | `loop/sessions.jsonl` |
| 杂账 | scratch | `loop/scratch.jsonl` |

## decisions

决定账六个文件同一个格式，行格式、编号规则、`root_id`、来源三类、`quote` 的填法、`merged_from`、`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行，这些全写在 `02-decisions.md`。

## issues

`status` 取 `open`、`answered`、`closed`。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `id` | 形如 `iss-0031` | 必填 |
| `assignee` | 五个角色之一或 `gyb` | 必填 |
| `kind` | 九选一，见下表 | 必填 |
| `stage` | `smoke`、`launch`、`crash` | `kind` 是 `failed` 时必填 |
| `text` | 文本 | 必填 |
| `reply` | 文本 | `status` 是 `answered` 时必填 |
| `handoff_id` | 派活单编号 | `kind` 是 `cannot`、`failed`、`denied`、`withdrawn`、`orphaned` 时必填，其余可选 |
| `log_tail` | 文本本身：日志末 40 行，`--log-tail FILE` 由 rl 截末 40 行、`--log-text -` 从标准输入收，落账都是文本这一栏，不记路径（路径顺 `handoff_id` 到 runs 行的 `log_path` 查） | 可选 |

九种 `kind`：

| kind | 意思 |
|---|---|
| `cannot` | 干不了 |
| `not_mine` | 不归我干 |
| `denied` | 被钩子拦了 |
| `failed` | 跑失败，附 `stage` 取 `smoke`、`launch`、`crash` |
| `anomaly` | 结果反常 |
| `request` | 申请 |
| `withdrawn` | 你手上的单子被收回了，通知类 |
| `orphaned` | holder 会话死了单子交回了，通知类 |
| `fyi` | gyb 越过 owner 处理了你的单子，通知类 |

入账规则四条：改派等于追加一版换 `assignee`；`assignee` 是 `gyb` 的那一版（含首次开单）触发桌面通知；`reply` 只有 `assignee` 或 gyb 能写；`close` 只有开单的 actor 或 gyb 能写。另有两处自动关：`rl handoff accept` 关这张单关联的 `answered` issue，`rl inbox` 关读到的通知类 issue。

## handoffs

派活单的字段级行格式（`work_type`、`owner` 与 `holder`、`parent_id`、`attempts`、`report_paths`、`code_paths`、`output_paths` 这些）和七个状态的转移表写在 `04-handoffs-and-sessions.md`。

## runs

数字账一个 schema，一次尝试两版：发射成功那一刻落发射版，跑完落收尾版。`status` 取 `launched`、`finished`。`actor` 是 `run` 或 `gyb`：数字账只有 run 角色的脚本能写，gyb 是原则 1 的例外。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `run_id` | 形如 `ho-0013-a1`，快车道用 `ql_tag` | 主键，和产物目录名、tmux session、commit message 一致；产物目录按约定是 `<artifact_root>/<run_id>/`，账上不另记 |
| `handoff_id` | 发射单编号 | 必填 |
| `attempt` | 整数 | 必填 |
| `commit` | git commit | `launched` 版必填 |
| `command` | 命令行 | `launched` 版必填，从发射单抄 |
| `host` | 机器名 | `launched` 版必填 |
| `gpus` | 卡 | `launched` 版必填 |
| `log_path` | 日志路径 | `launched` 版必填 |
| `tmux_session` | tmux session 名 | `launched` 版必填 |
| `watch_cmd` | 监控命令 | `launched` 版必填 |
| `started_at` | 时间 | `launched` 版必填 |
| `config` | 字典：`model`、`params`、`dataset`、`split`、其余超参 | `launched` 版必填，从发射单抄 |
| `finished_at` | 时间 | `finished` 版必填 |
| `exit_status` | `ok`、`failed`、`killed` | `finished` 版必填 |
| `actual_seconds` | 秒 | `finished` 版必填，rl 从两个时间戳算 |
| `metrics` | 字典，键是指标名、值是数 | `exit_status` 是 `ok` 时必填 |
| `data_path` | 路径：产物目录里给 analysis 算数用的那一个文件或子目录 | `exit_status` 是 `ok` 时必填 |

收尾版有 `data_path`（2026-08-17 裁，按施工计划的表；设计文档收尾版四样那一句回去补）；发射版原来的 `artifact_dir` 一栏去掉，产物目录走 `<artifact_root>/<run_id>/` 的约定，看门狗和翻半截产物都按约定找。

真实耗时不管退出状态是什么都记。数字账默认只列每张单最新一次退出状态为 `ok` 的行，全出要另外要，见 `05-rl-cli.md`。

## grants

授权只有 gyb 在裸终端能写：`actor` 必须是 `gyb`，`session_id` 必须是 `cli`。角色会话里替 gyb 批授权不收。`status` 取 `active`、`revoked`。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `id` | 形如 `grant-0003` | 必填 |
| `grantee` | 角色 | 必填 |
| `permission` | 字符串，第一版只有 `read:notes` 一种 | 必填 |
| `expires_at` | 时间 | 可选 |
| `text` | 文本 | 必填 |
| `issue_id` | 问题条编号 | 可选 |

## feedback

反馈账谁都能提、只有 gyb 能裁、谁都能读。提的那一版 `actor` 谁都能写，裁的那一版 `actor` 必须是 `gyb`。`status` 取 `proposed`、`accepted`、`rejected`。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `id` | 反馈编号 | 必填 |
| `target` | 文件路径，或带前缀的编号 `rule-06`、`principle-06` | 必填 |
| `text` | 文本 | 必填 |
| `verdict_text` | 文本 | `accepted` 和 `rejected` 两版都必填：采纳的写采纳成什么样，不采纳的写为什么 |
| `applied_to` | 路径列表，rl 校验每个路径存在 | 采纳时必填 |
| `rules_version_after` | 母版版本 | 采纳时 rl 自动填 |

采纳的那一版要写清改了哪几个文件，母版和文档都算。

## evaluations

口径账一行一条口径，分指标和图两类。`status` 取 `proposed`、`approved`、`rejected`、`retired`。提和改由 analysis 写，批和打回由 gyb 写：`proposed` 那一版 `actor` 是 `analysis`，`approved`、`rejected`、`retired` 那一版 `actor` 必须是 `gyb`。已经 `approved` 的口径再 update 一版自动回 `proposed`，要 gyb 重新批。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `id` | 形如 `eval-0004` | 必填 |
| `kind` | `metric` 或 `figure` | 必填 |
| `name` | 名字 | 必填 |
| `definition` | 定义 | 必填 |
| `applies_to` | 适用范围，自由文本，rl 不解析；但要写出具体的程序或参数（哪条 track、哪个模型、哪个数据集、哪些 `config` 键的哪些取值），不许只写「所有跑」这类空话 | 必填 |
| `metrics_key` | runs 账 `metrics` 里的键 | 指标行和 `code_path` 二选一 |
| `code_path` | 形如 `analysis/common/metrics.py:accuracy` | 指标行和 `metrics_key` 二选一；`proposed` 时可以不存在，`approved` 时必须存在 |
| `group_by` | runs 顶层字段名、`config.<键>`、或已 `approved` 的指标口径编号 | 图行必填 |
| `x` | 同上三种取值 | 图行必填 |
| `y` | 同上三种取值 | 图行必填 |
| `uses` | 用哪几条指标口径 | 图行必填 |
| `reason` | 文本 | 打回时必填 |
| `quote` | gyb 原话 | 批那一版必填，一句 quote 可以批多条 |

## sessions

会话账两版：开始版和结束版。开始版由钩子代角色写，`actor` 填角色。`status` 取 `open`、`closed`。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `session_id` | 会话 id | 主键 |
| `role` | 五个角色之一 | 必填 |
| `model` | 钩子从钩子输入的 JSON 里取，取不到记 `unknown` | 必填 |
| `launched_by` | `manual`、`subagent`、`workflow` | 必填 |
| `rules_version` | 母版版本 | 必填 |
| `started_at` | 时间 | `open` 版必填 |
| `last_activity` | 时间，语义是最后一次写账时间 | 不落账：rl 在查询（`rl session show`、`rl status`、`rl reclaim`）时现算，取九本账里 `session_id` 等于它的行的最大 `ts`（含 sessions 账自己的行）；sessions 账不为刷新它追加版本 |
| `focus` | reviewer 在审的决定编号 | 可选 |
| `ended_at` | 时间 | `closed` 版必填 |
| `end_reason` | `hook`、`manual`、`reclaim` | `closed` 版必填 |
| `released_handoffs` | 销号时交回待干的单子列表 | `closed` 版必填 |

`last_activity` 不落账、查询时现算（2026-08-17 裁）：sessions 账每一版只对应会话状态的一次真实变化（开、关、`focus` 变），刷时间戳不算状态变化，不追加版本；「最后一次写账时间」从九本账的 `ts` 推出来，只有一处为准。

## scratch

杂账只有快车道写，记快车道的开张、数字、关张。主键是 `ql_tag`。`status` 取 `open`、`merged`、`dropped`，中间追加数字的每一版 `status` 仍是 `open`（跑了一次不是状态变化，是开着的时候发生的事，不设第四态）。`actor` 是 `deploy` 或 `analysis`。analysis 和 reviewer 默认不读这本账。

| 字段 | 取值或格式 | 必填条件 |
|---|---|---|
| `ql_tag` | 形如 `ql-20260816-01`，rl 在锁里分 | 主键 |
| `role` | `deploy` 或 `analysis` | 必填 |
| `worktree` | worktree 路径 | deploy 的 `open` 版必填 |
| `dir` | `analysis/scratch/<ql_tag>/` | analysis 的 `open` 版必填 |
| `base_commit` | git commit | `open` 版必填（analysis 的快车道不建分支，这一栏填什么由 `07-quick-lane.md` 定） |
| `branch` | 分支名 | deploy 的 `open` 版必填；analysis 的快车道不建分支，要不要这一栏由 `07-quick-lane.md` 定 |
| `note` | 文本 | 中间版（`status` 仍是 `open`）自由，建议写 |
| `metrics` | 键值对 | 中间版（`status` 仍是 `open`）自由，建议写 |
| `handoff_id` | 快车道补单编号 | `merged` 版必填 |
| `reason` | 文本 | `dropped` 版必填 |

校验头尾查、中间不查（2026-08-17 裁，按施工计划的表）：`open`、`merged`、`dropped` 三版各按上表查必填，中间追加数字的版只查骨架和 `ql_tag`。设计文档「格式松、只校验骨架和快车道标签」那句只对中间版成立，回去改成「中间版格式松」。

快车道的数字追加进杂账，不进 runs 账。杂账里的东西一旦要进正账拿来复用，它就不是快车道了，得按正常路重跑。

## 退出码

| 码 | 意思 | 附带 |
|---|---|---|
| 0 | 成功 | |
| 2 | 校验拒收 | 原因写到标准错误，包含下一步该做什么 |
| 3 | 角色无权（含角色带 `--force`） | 同上，附「开 issue 给谁」的命令 |
| 4 | 文件锁等待超时 | |

所有子命令支持 `--json`。表外的转移一律拒收，退出码 2。

## 和别的 part 的接口

本份是定义处的东西：九本账公共骨架（七样加 `fix_for`、`force_reason`）、总规矩（只增不改、按 `status` 查、锁与写序、编号从 1 起四位起步、能写就能查、gyb 豁免只到权限层、`loop/` 进 git）、issues / runs / grants / feedback / evaluations / sessions / scratch 七本的字段级行格式、退出码四个。别的 part 提到这些只指过来不抄；HANDOFF 四点五节标了「写了两遍」的三处（`09` 抄 issues/grants/feedback、`07` 抄 scratch、`04` 抄 sessions）每次同步要和本份一字不差。

本份指出去的：

- 派活单的七个状态、转移表、每一版查哪些前提，定义在 `04-handoffs-and-sessions.md`，本份的「校验按 status 查」靠它落地；handoffs 的全部字段（`parent_id`、`attempts`、`decision_refs`、`evaluation_refs`、`report_paths`、`code_paths`、`output_paths`、`progress_note`）也定义在那一份，本份 handoffs 一段只留一句指过去。
- 钩子代角色写 sessions 开始版、销号写结束版、reclaim 的动作定义在 `04-handoffs-and-sessions.md` 和 `06-hooks-and-permissions.md`；本份只定 sessions 的行格式。`last_activity` 不落账、查询时现算（2026-08-17 裁），`rl status`、`rl reclaim`、`rl session show` 算它的写法在 `05-rl-cli.md`。
- decisions 的字段（`root_id`、`sources` 三类、`quote`、`merged_from`）、六个文件的落法、编号带 actor 前缀六个文件各排各的号，定义在 `02-decisions.md`。
- actor 怎么判（裸终端记 `cli`、角色会话加 `--as-gyb` 要 `--quote`）和 `--force --reason` 的命令行写法，本份指 `05-rl-cli.md`；这一组规矩的定义处归 `01` / `05` / `06` 哪一处，sync-inbox 问题 1 等 gyb 裁，裁了本条跟着改。本份定的是：角色带 `--force` 拒收退出码 3，`--as-gyb --quote --force --reason` 算 gyb 身份照写。
- 每本账的写命令和查询命令清单、`rl trace`、`rl status`、`rl inbox`、`rl doctor`（含扫描项名字，`fix_for` 填它）、`rl reclaim` 在 `05-rl-cli.md`；`rl run add` 的签名去掉 `--artifact-dir`（2026-08-17 裁）。
- 哪个角色能调哪条写命令（角色 json 的 `ledger_writes`）在 `06-hooks-and-permissions.md`；钩子拦直接写 `loop/` 也在那一份。
- `ql_tag` 的分配、scratch 三态的开张关张动作（`rl ql open`、`rl ql close`）、analysis 的快车道 `base_commit` 和 `branch` 两栏填什么，在 `07-quick-lane.md`。本份定的是：中间版 `status` 仍是 `open`，校验头尾查中间不查。
- 九本账的路径、产物根 `artifact_root`、阈值（`issues.answered_stale_days` 这类）写在 `research-loop.json`，见 `08-trees-init-and-host.md`；`loop/` 进 git、脏树白名单那一处也在 `08`。产物目录 `<artifact_root>/<run_id>/` 这条约定归 `08` 还是 `12` 由统筹定，本份 runs 表只引它。
- feedback 的 `rules_version_after` 和母版 `rules_version` 的关系、feedback 的流程在 `09-common-and-feedback.md`；`verdict_text` 两版都必填由本份定。
- 口径怎么提、怎么批、批的时候一句话批一组，在 `13-role-analysis.md` 和 `22-pair-idea-analysis.md`；`applies_to` 是自由文本但要写具体程序或参数由本份定。
- runs 两版什么时候落、`rl run finish` 顺带调宿主收尾命令、看门狗按 `<artifact_root>/<run_id>/` 找产物目录，在 `12-role-run.md`；`data_path` 是产物目录里给 analysis 算数用的那一份，analysis 那头怎么用在 `23-pair-run-analysis.md`。
- 九本账的测试用例（锁与撞号、runs schema、口径、feedback）在 `30-build-steps-verify-tests.md`。

## 源文档没写清的

（无，全部已裁，见「裁决记录」。）

## 第二轮模拟里归到这一份的摩擦

下面的条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，保留场景名、序号、严重度、kind、原文、依据、改法，未核实、未判断。

### param-tweak（45 步，gyb 动手 8 次）

5. [slows/principle_violation] 第 44 步：违反原则 7（快车道有明确的进和出）和原则 6（进出对称）：进有 rl scratch add 登记，出没有任何登记通道——scratch 只有 add 和 list、行里没有状态字段，handoffs 又没有 ql_tag 字段，rl status 的「没合回的快车道 worktree」这一段永远消不掉
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:21
   - 改法：加 `rl scratch close --tag QL --handoff ID`，status 按有没有 close 行判断合没合回

16. [cosmetic/missing] 第 8 步：ql_tag 由调用者用 --tag 手填，谁分配这个 01 序号、撞了怎么办没写；锁那一段只保证自动编号的账不撞号
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl scratch new` 由 rl 在锁里分配 ql_tag 并打印出来

20. [cosmetic/missing] 第 3 步：sessions 账要求手动加载也记真实模型名、不记 inherit，而角色 json 的 manual 一律是 inherit；钩子从哪里拿到当前会话的真实模型标识没写，待验证清单里也没有这一条
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「SessionStart 钩子输入里有没有模型标识」，拿不到就退到 rl session start --model unknown

21. [cosmetic/ambiguous] 第 21 步：杂账「跑出来的数字继续追加」，但 scratch 的主键是什么没写：是同一个 ql_tag 追加一版，还是每跑一次开一行新 id，两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:55
   - 改法：scratch 的主键定为 ql_tag，每跑一次追加一版

### new-idea（39 步，gyb 动手 7 次）

6. [slows/principle_violation] 第 26 步：违反第 4 条原则「一个字段必不必填看这一版的状态」：runs 和 sessions 的字段表里根本没有 status 字段，必填项是按「version 1 是发射版、version 2 是收尾版」定的，可入账校验被规定成按 status 查，校验器在这两本账上无从下手
   - 依据：plans/2026-08-16-research-loop-next-steps.md:18; plans/2026-08-16-research-loop-next-steps.md:92; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：给 runs 加 status 取 launched/finished、sessions 加 status 取 open/closed，九本账的必填一律按 status 查

7. [slows/missing] 第 4 步：sessions 账要求手动加载也记真实模型标识、不记 inherit，可角色 json 的 manual 一栏写死 inherit，登记钩子调 rl session start --model M 时这个 M 从哪来没写；gyb 手动加载 idea 时钩子拿不到真实模型名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：明写钩子从钩子输入的 JSON 里取 model 字段传给 rl，取不到就记 unknown 并由 rl doctor 列出来

### plot-new-plan（17 步，gyb 动手 8 次）

5. [slows/missing] 第 10 步与第 16 步之后的下一轮迭代：handoffs 的 decision_refs 每项带 {id, version}，evaluation_refs 只写编号不带版本；口径 approved 之后再追加一版，已经派出去的分析单引的是哪一版查不出来，过版检查命令 rl decision stale 也只覆盖决定账。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：evaluation_refs 改成和 decision_refs 一样的 {id, version}，并让 stale 检查同时扫口径引用。

6. [slows/missing] 第 16 步之后（gyb 看完图想换个画法）：口径账只写了被打回之后 analysis 改了再提一版这条路，没写已经 approved 的口径能不能 update、update 之后 status 回不回 proposed、要不要重新批；也没有决定账那种「同一个问题换做法追加一版、换问题开新条」的判据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:78; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:216; plans/2026-08-16-research-loop-next-steps.md:46
   - 改法：给 evaluations 抄一条决定账同款判据，并明写 approved 之后 update 一版就回 proposed、必须由 gyb 重新 approve。

7. [slows/missing] 第 6 步与第 8 步（写图口径的 group_by 和 x 轴）：图行必填 group_by、x、y，但文档没写这三栏的取值域是 runs 行的顶层字段、config 字典里的键、还是 analysis 现算的派生量；「按模型规模分组」要落成 config.params 全靠模型自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：在第三节 evaluations 字段里写死 group_by 和 x、y 的取值只能是 runs 的顶层字段名、config.<键>、或已 approved 的 metric 编号。

### next-plan-after-results（36 步，gyb 动手 16 次）

12. [cosmetic/ambiguous] 第 12 步：派生量口径 approve 时 code_path 必须已存在，可公共规矩 5 又说派生量只用 approved 的口径；analysis 到底能不能为一条还没批的口径先写代码，两种读法都说得通
   - 依据：plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:249
   - 改法：规矩 5 补一句「写代码不算算数，出数才要 approved 口径」

### run-crash-midway（40 步，gyb 动手 4 次）

2. [slows/ambiguous] 第 3、9 步：看门狗写账时 actor 判成谁，两种读法都说得通。build-plan.md:166 说「看门狗的判定进 issues 账」，读成 monitor 自己打 `rl issue open`；但 monitor 是独立进程，按 build-plan.md:121 读不到会话状态文件就判 actor 是 gyb、session_id 是 cli，这条 issue 会记成 gyb 开的。读成 run 会话来打则 build-plan.md:166 那句落空。两种读法分别导致账行 actor 记错，或者 monitor 和会话各开一条重复 issue。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：把 monitor 明确排除在写账者之外，改写成「看门狗的判定由 run 会话转写进 issues 账」。

7. [slows/missing] 第 11 步：崩掉的这一跑没有地方回填真实耗时。`--actual-seconds` 只挂在 `rl handoff done`（build-plan.md:134、:61），而 stuck 这条路永远走不到 done，所以 next-steps.md:70 说的「跑完之后 run 把真实耗时回填，几次之后就知道外推偏多少」在崩溃场景下拿不到样本，偏偏崩之前跑到一半的那段耗时正是校准外推最有用的数据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:70
   - 改法：把 actual_seconds 挪到 `rl run finish` 上，从 started_at 和 finished_at 自动算，不管退出状态是什么都记。

8. [slows/missing] 第 31、40 步：数字账里 killed 的 r1 和 ok 的 r2 挂同一个 handoff_id，没有任何字段标「r1 这条不算数」。build-plan.md:137 的 `rl run list --handoff/--decision` 会同时吐两条，analysis 按决定或 batch 分组时（next-steps.md:80 说 analysis 要顺决定到发射单到 run_id 这条链）会把废跑混进来；build-plan.md:144 的 doctor 也不扫这种情况（r1 有对应发射单，不报）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：`rl run list` 默认只出 exit_status=ok 的行，要废跑加 `--all`。

9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。

13. [slows/guessed] 第 9 步：跑挂该开哪种 kind 的 issue，只能猜。build-plan.md:45 的六种 kind 是 cannot / not_mine / denied / anomaly / request / withdrawn，没有一种对应「跑挂」；build-plan.md:166 给的命令模板直接写成 `rl issue open --to deploy --kind ...` 把 kind 留空；next-steps.md:72 列了四种要开 issue 的情形（smoke 失败、发射失败、跑挂、结果反常）但只给结果反常指定了 anomaly。本 trace 取 cannot 是猜的，四种情形挤进一个 kind 之后 `rl issue list` 没法按失败类型筛。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：给 run 的四种失败各定一个 kind（smoke_failed / launch_failed / crashed / anomaly），写进第二节词表。

14. [slows/ambiguous] 第 13 步：sessions 账的 open_handoffs_at_end 字段说明是「结束时 holder 还是这个会话的单子列表，正常应为空」（build-plan.md:71），但发射单标 stuck 之后 holder 不清空，run 会话销号时这个字段必然非空。到底是「非空就是异常要拦」还是「非空只是记一笔」，文档没说，两种读法分别对应销号被拒和销号放行。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：把这个字段的说明改成「结束时状态还是 in_progress 的单子列表，非空即拒绝销号」，stuck 的单子不算。

### n-launch-orders（58 步，gyb 动手 10 次）

10. [slows/missing] 第 18 步：run_id 谁定、什么格式没写，只写了它要和产物目录名、tmux session、commit message 一致；宿主发射器还硬要求一个 --track 且要和 TIMELINE.md 的方向对得上，插件九本账里根本没有 track 这个字段，也没写谁给。batch 标签同样没有格式（对比 ql_tag 是给了格式的）。这三样在这一步全靠猜。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:49; 2026-08-16-research-loop-next-steps.md:68; .claude/skills/gpu-run/SKILL.md:86
   - 改法：launch 子对象加 run_id 和 track 两个字段由 deploy 开单时填，batch 照 ql_tag 的样子定成 b-<日期>-<序号>。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

13. [slows/missing] 第 20 步：rl 自动开的 `kind=withdrawn` issue 的 assignee 是角色不是会话（build-plan.md:59），run 的 subagent 收到信号后就结束了，这条 issue 没人回也没人关。doctor 的扫描项里只有「没人引用的 issue」（build-plan.md:144），这条带着 handoff_id 所以扫不出来，会一直挂在 `rl status` 的 open 列表里。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：withdraw 自动开的 issue 直接落成 `closed`（它是通知不是问题），或者 doctor 加一条「holder 已销号但 withdrawn issue 仍 open」的扫描并附 close 命令。

14. [slows/missing] 第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

4. [blocks/missing] 第 17 步：没写 loop/ 九本账进不进 git、要不要加进宿主的脏树白名单。new1 的门禁把 ops/jobs.json、ops/runs.jsonl、RESULTS.md、*.lock 排除在脏之外，loop/*.jsonl 不在里面；而每一条 rl 命令都在追加行，run 走到「发射前 commit」那一刻工作树必脏，要么把账本一起 commit 进去（发射前 commit 那一步禁止 --allow-dirty），要么被门禁拦住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/CLAUDE.md:36; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:54
   - 改法：rl init 时把 loop/*.jsonl 和 loop/.lock 一起加进宿主 run.py 的脏树白名单，并在 research-loop.json 里记一句账本入不入 git。

10. [slows/principle_violation] 第 3 步：违反原则 1（谁在打命令和会话装了什么角色是两回事，账行如实记 actor 和会话两样）。这条链上第 5 到第 23 步全部由 gyb 本人驱动，可 sessions 账只有 role 和 model 两栏、handoffs 只有 holder 一栏、每条账行的 actor 只能填角色名，事后没有任何字段能分出「这张单是 gyb 亲手干的」还是「subagent 干的」；reviewer 要查也查不到。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-next-steps.md:120
   - 改法：sessions 账加一栏 launched_by（manual / subagent / workflow），钩子登记时按有没有父会话填。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

1. [blocks/missing] 第 2、6、9、20、25 步：九本账里没有任何一个字段说一行属于哪条研究线。公共骨架六样是 id/version/ts/actor/session_id/schema_version，decisions 按 actor 拆六个文件不按线拆，issues、evaluations、scratch、sessions 四本账各自的字段表里也没有线维度。gyb 早上第一眼要分清两条线，只能靠自己记住哪个决定编号属于哪条线。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-next-steps.md:96
   - 改法：公共骨架加一个可选的 line 字段，rl 的 status/list/show 全部加 --line 过滤，开单和提口径时从上游单子自动继承。

9. [cosmetic/contradiction] 第 14 步：手动加载的会话在 sessions 账里 model 记什么，两处打架：sessions 行格式写「真实模型标识，手动加载也记真实的，不记 inherit」，角色 json 那一栏写「model 分 as_subagent 和 manual，manual 一律 inherit」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：角色 json 那一栏加半句「manual 写 inherit 是声明跟当前会话走，sessions 账落解析后的真实模型名」，两句各自限定清楚。

### feedback-round（15 步，gyb 动手 9 次）

2. [blocks/principle_violation] 第 7 步（gyb 查 feedback）与第 13 步（deploy 想知道裁决结果）：违反第 6 条「进出对称」和第 5 条「权限从动作倒推」：deploy、run、analysis 三份角色 json 的 ledger_writes 都有 feedback add，reads 里都没有 feedback；命令表也只有 feedback list 没有 feedback show。提反馈的角色写得进去、查不出来，自己提的那条被采纳还是被否只能靠 gyb 口头说
   - 依据：plans/2026-08-16-research-loop-build-plan.md:103; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:94
   - 改法：五份角色 json 的 reads 一律加 feedback，命令表补 `rl feedback show ID`

4. [slows/contradiction] 第 11 步（rl feedback accept 填 applied_to）：applied_to 的口径是「改了母版哪个文件」，单值；但按原则 8「后裁的赢、要回来把正文那一行改掉、不留两个值」，一条采纳的规矩至少要同时改母版 common/GLOBAL-RULES.md 和施工计划第十三节那一行，单值记不下第二处，doctor 也没有一条扫描去查第二处漏没漏
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:22; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：applied_to 改成路径列表，rl doctor 加一条「accepted 的 feedback 的 applied_to 没同时含母版和设计或施工文档」

5. [slows/missing] 第 12 步（正在跑的 analysis 会话和 idea 会话怎么办）：母版改了以后，正在跑的会话按旧规矩产出的东西算不算数（要不要打回、收回、重做）没写；账上也没有任何地方记得住某个会话是在哪一版母版下跑的：sessions 账只有 session_id、role、model、started_at、ended_at、end_reason、open_handoffs_at_end 七样，母版文件本身也没有版本号
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：母版文件加一个 rules_version，sessions 开始版记下它，accept 时 rl 顺带列出还活着的会话和它们的 rules_version 让 gyb 挑要不要收

9. [cosmetic/ambiguous] 第 2 步（feedback 的 target 填什么）：target 的口径是「文件路径或规矩编号」，可母版里公共规矩八条编号 1 到 8、八条设计原则也编号 1 到 8，两套都在同一个文件里，`--target 6` 指的是规矩 6 还是原则 6 分不出来
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:13
   - 改法：规矩和原则各给一套带前缀的稳定编号（rule-06、principle-06），target 只收文件路径或这两种编号

10. [cosmetic/ambiguous] 第 8、11 步（先改文件还是先 accept）：accept 那一版要求 applied_to 必填「改了母版哪个文件」，但没写是先把母版改完再 accept 还是先 accept 再去改，入账校验也没说要不要检查这个路径存在、检查改没改
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：命令表写死「accept 之前先把母版改完，rl 校验 applied_to 的每个路径存在」

### idea-request-notes（15 步，gyb 动手 4 次）

2. [slows/contradiction] 第 5 步：命令表里 `rl grant add / rl grant list` 整行的「谁能调」只写 gyb，idea 调 grant list 应拿退出码 3；但 idea 的 reads 写的是「九本账全部」，公共规矩第 8 条又要求「读账一律经 rl 查询命令」。结果是 idea 查不到自己名下有没有 read:notes，每开一个新会话都只能重新走一遍申请，或者凭猜
   - 依据：plans/2026-08-16-research-loop-build-plan.md:138; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:52
   - 改法：第六节把 grants 拆成两行：`grant add` 谁能调写 gyb，`grant list/show` 谁能调写「谁都行」

3. [slows/contradiction] 第 9 步：设计文档一处写「idea 开一条 issue 给 gyb，gyb 写一条 grant」，另一处允许角色会话里的模型带 --quote 替 gyb 打 --as-gyb。本场景两句合起来的结果是：申请方和批准方是同一个会话里的同一个模型，quote 只是模型自己敲进去的字符串、rl 不校验，而 grant 的全部价值就是「给 reviewer 事后查的凭据」，自提自批之后这份凭据证明不了任何事
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:245
   - 改法：第六节 grants 那一行加一句「grants 不接受 --as-gyb，只收 session_id 为 cli 的裸终端写入」，gyb 批授权必须自己在裸终端打一次

10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

### periodic-reclaim（27 步，gyb 动手 11 次）

11. [slows/missing] 第 3、24 步：一条一周没动的快车道 worktree 没有出路。reclaim 只管会话和单子，scratch 账只有 add 和 list，设计文档写死出快车道只有合回主分支补工单这一条路，放弃一条快车道没有命令，rl status 里那一行永远挂着，越攒越多。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:141
   - 改法：加 rl scratch retire --tag QL --reason，rl status 只列没 retire 的快车道，reclaim 把超期的快车道也列进来。

12. [slows/principle_violation] 第 23 步：违反原则 1。runs 账的行格式写死「actor 必须是 run」，而原则 1 说任何权限检查对 gyb 一律不生效。gyb 要给回收下来的孤儿发射版补一条 exit=killed 的收尾版，按前一句写不进去，按原则 1 写进去就破了 schema，入账脚本按哪一条实现没有定论。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：runs 账的 actor 改成允许 run 或 gyb，字段表那一句后面补「gyb 例外，同原则 1」。

14. [slows/missing] 第 13 步：钩子调 rl session start 时那一行的 actor 填什么没写。公共骨架规定 actor 取值是五个角色或 gyb，钩子两样都不是。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：明写钩子代角色写账，sessions 开始版的 actor 填 --role 那个角色，session_id 填新会话。

### hook-missed-session-end（23 步，gyb 动手 11 次）

3. [slows/missing] 步 2：rl status 的「活着的会话」（施工 L142）只能按 sessions 账有没有结束版判定，钩子漏销号的死会话被列成活着。sessions 行（施工 L71）没有 last_activity 之类的字段，reclaim 的口径「会话超过 48 小时没写任何账」（施工 L178）要跨九本账扫 session_id，怎么算没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:178
   - 改法：sessions 账加 last_activity 字段，rl 每次写任何账顺带刷新，status 和 reclaim 都读它。

4. [slows/principle_violation] 步 3：违反原则 6（设计 L20、L94「能 add 就有 show 和 list」）。命令表（施工 L126）里 sessions 只有 start 和 end，九本账里唯独它没有 show 和 list。gyb 从 rl status 拿到 holder 的 session_id，查不出它是哪个角色、什么时候开的、最后一次写账是什么时候。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:94; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：命令表补 rl session show ID 和 rl session list [--alive] [--role R]，谁都能调。

9. [slows/missing] 步 6、步 22：整个恢复过程在九本账上不留痕，违反原则 4 的事件流本意（设计 L18）。release 那一版只记 status 和 holder 清空；issue 的六种 kind（施工 L45）没有一种对得上「你的 holder 会话死了、单子被交回」；reclaim 关掉死会话时 open_handoffs_at_end（施工 L71）已经是空的，因为单子先被 release 了。事后谁都看不出钩子漏过一次。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:18; plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：issue 的 kind 加一种 orphaned，release 和 reclaim 交回单子时自动开一条给 owner，把当时的 holder 会话 id 写进去。

### smoke-fails（44 步，gyb 动手 4 次）

7. [slows/missing] 步 34（rl run add 落发射版）：runs 发射版必填 config 字典，里面要有 model、params、dataset、split，是给 analysis 分组用的；但发射单的 launch 子对象只有 command、args、workdir、estimated_seconds、step_table、actual_seconds，没有 config。run 要么去解析命令行参数，要么去读 experiments/ 的代码猜这四个值，而这四个值本来是 deploy 定的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：把 config 挪到发射单上由 deploy 开单时填，rl run add 默认从发射单抄，run 只补机器和卡。

9. [slows/missing] 步 18（run 准备 --log-tail）：开 issue 要附日志末 40 行和 traceback，命令给的是 --log-tail FILE，要一个文件路径。可是 smoke 阶段按 gpu-run 的规矩产物不留档，ImportError 是前台跑出来的、traceback 只在标准输出里，压根没有日志文件。run 得自己想办法把 stdout 落成文件，落到哪、叫什么名，文档没写（run 的写权只有仓库外的 artifact_root）。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:72; plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:160; .claude/skills/gpu-run/SKILL.md:49
   - 改法：run 的 SKILL.md 规定 smoke 一律重定向到 artifact_root/smoke/<发射单号>.log，或者给 rl issue open 加 --log-text 从标准输入收。

### doctor-findings-fix（24 步，gyb 动手 15 次）

2. [blocks/blocked] 第 21、22、23 步（修第三类）：「runs 行没有对应发射单」这一类没有可用的修法：runs 的写命令只有 add 和 finish，第三节只定义了 version 1 发射版和 version 2 收尾版，没有第三版；handoff 编号自动分配，补开一张 launch_order 也补不进已有 runs 行的 handoff_id（账只增不改）。gyb 按文档走到这里做不下去，doctor 每次都会继续报这一条。
   - 依据：2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:133; 2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-next-steps.md:92
   - 改法：加一条 `rl run relink RUN_ID --handoff ID`，作为 runs 的第三版（只允许补 handoff_id），或者给 doctor 加一条 acknowledge 命令把确认过的孤儿行消音。

3. [blocks/contradiction] 第 23 步（gyb 能不能手写 runs 行）：设计文档说「第二层是入账校验，硬的……gyb 例外」，读起来 gyb 连必填字段和 actor 限制都免；施工计划说「actor 是 gyb 时跳过全部『谁能调』和转移表『谁能写』的检查」，读起来只免这两类。runs 那一行写着 actor 必须是 run，gyb 到底能不能补写一行 runs 直接取决于这两句谁算数。
   - 依据：2026-08-16-research-loop-next-steps.md:134; 2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:63
   - 改法：在施工计划第六节写死一句「gyb 只豁免谁能调与转移表谁能写，schema 必填与 actor 限制对 gyb 同样生效」，并把设计文档那句「gyb 例外」改成同一句话。

4. [slows/ambiguous] 第 3、4 步（判定第一类是什么）：「没人引用的 issue」没有定义什么叫被引用。按现有字段只有 handoff.issue_id 和 grant.issue_id 会指回 issue，而 handoff 的 issue_id 只在 stuck 那一版必填，于是 withdraw 自动开的 kind=withdrawn issue、run finish 开的 kind=anomaly issue、idea 的 kind=request issue 天生就没人引用，doctor 会把这些正常的行当问题报。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:59; 2026-08-16-research-loop-build-plan.md:92
   - 改法：把这一项收窄成「kind 是 cannot 或 denied、status 是 open、且没有任何 handoff 的 issue_id 指回来的 issue」，其余 kind 一律不扫。

5. [slows/blocked] 第 6 步（补 stuck 那一版）：`rl handoff stuck` 的前提是「那条 issue 的 handoff_id 指回本单」，但 `rl issue open` 的 `--handoff` 是可选参数；崩在写序中途的那条 issue 如果当初没带 --handoff，这条前提永远满足不了，而 issues 的命令只有 reassign/reply/close，没有补 handoff_id 的路，第一类同样修不了。
   - 依据：2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:132; 2026-08-16-research-loop-build-plan.md:59
   - 改法：要么把 `--handoff` 在 kind 是 cannot/denied/withdrawn 时改成必填，要么加一条 `rl issue link ID --handoff ID`（追加一版只补这个字段）。

12. [cosmetic/missing] 第 5、9 步（修账那两版留不留痕）：gyb 在裸终端补的 stuck 和 reject 这两版，账上只留 status 和 reason，没有任何字段标明这是 doctor 修账修出来的。reviewer 事后翻 handoffs，分不出这张单子是真卡住过、还是只是把断掉的引用补回去。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:55; 2026-08-16-research-loop-next-steps.md:88
   - 改法：公共骨架加一个可选的 `fix_for` 字段，doctor 给的修法命令一律带上扫描项名字。

## 裁决记录（日期）

- 2026-08-17：`schema_version` 从 1 起，九本账共用一个数，任何一本账的字段表改了（加字段、改取值域、改必填条件）整套加一；rl 读旧行按行上标的那一版字段表解析。对回原则 8（一处为准）和原则 4（旧行永不动）。
- 2026-08-17：`last_activity` 不落账，rl 查询时现算（九本账里该 `session_id` 的最大 `ts`）；sessions 账不为刷时间戳追加版本。对回原则 4（每一版对应一次真实状态变化）和原则 8（一处为准）。
- 2026-08-17：编号序号从 1 起；四位是最小宽度，用完自然进到五位，rl 排序按数值；编号发出去不重发。decisions 六个文件各排各的号、编号带 actor 前缀，02 已写死，03 不另裁。对回原则 4（编号只增不回收）。
- 2026-08-17：issues 的 `log_tail` 存文本本身（日志末 40 行），一栏，两个命令入口只是喂法不同；不另记路径。对回原则 4（证据冻在事件行里）和原则 8（路径已在 runs 行，不写两处）。
- 2026-08-17：feedback 的 `verdict_text` 在 `accepted` 和 `rejected` 两版都必填。对回原则 6（提进去的人要能查到结果）。
- 2026-08-17：evaluations 的 `applies_to` 是自由文本、rl 不解析，但必须写出具体的程序或参数（track、模型、数据集、config 键值），不做格式化。对回原则 2（怎么筛数据靠纪律和 reviewer，账只查说得清）。
- 2026-08-17：scratch 中间追加数字的每一版 `status` 仍是 `open`，不设第四态。对回原则 4（校验按 status 查，中间版继承 open 版必填）和原则 7（快车道只有进和出两个动作）。
- 2026-08-17：角色会话带 `--force` 一律拒收，退出码 3，附「开 issue 给 gyb」的命令；`--as-gyb --quote --force --reason` 算 gyb 身份写，照写。对回原则 1（豁免只属于 gyb）和原则 2（入账校验是硬的）。
- 2026-08-17：`loop/` 九本账进 git，每次 commit 顺手带上，不另设 commit 动作。对回原则 8（账本是唯一为准的记录，要有历史）和原则 4（只增不改，diff 纯追加）。
- 2026-08-17：公共骨架的可选字段是 `fix_for` 和 `force_reason` 两个（不一致 1 定稿，按施工计划的表）。对回原则 1（gyb 硬写留痕）。
- 2026-08-17：runs 收尾版留 `data_path`（`ok` 时必填，是产物目录里给 analysis 算数用的文件或子目录）；发射版去掉 `artifact_dir`，产物目录按约定 `<artifact_root>/<run_id>/`，账上不记（不一致 2 定稿）。对回原则 8（约定已在 12，不写两处）和原则 9（analysis 从 run_id 直接到数据）。
- 2026-08-17：scratch 校验头尾查、中间不查：`open`、`merged`、`dropped` 三版按表查必填，中间版只查骨架和 `ql_tag`；`branch` 改成 deploy 的 `open` 版必填，analysis 的 `base_commit`、`branch` 两栏交 `07` 定（不一致 3 定稿）。对回原则 7（进出两行得说得清自己是什么）。

## 要同步到别处的

- `04-handoffs-and-sessions.md`：sessions 字段表里 `last_activity` 那一栏「rl 每次替这个会话写任何账时顺带刷新，是 sessions 账上的一版还是内存索引施工时定」改成「不落账，rl 查询时现算，取九本账里该 `session_id` 的最大 `ts`；sessions 账不为刷新它追加版本」；04 的「没写清」第 6 条据此销掉。已同步 2026-08-17。
- `09-common-and-feedback.md`：feedback 行格式那一句里 `verdict_text` 后面补「`accepted` 和 `rejected` 两版都必填：采纳的写采纳成什么样，不采纳的写为什么」，和 03 的字段表一字不差。 已同步 2026-08-17。
- `07-quick-lane.md`：scratch 那张「这一版 / 必填」表里「中间版」那一行改成「中间版（`status` 仍是 `open`）」，正文加一句「中间追加数字的每一版 `status` 仍是 `open`，不设第四态」。 已同步 2026-08-17。
- `--force --reason` 的定义处（`01-gyb.md` / `05-rl-cli.md` / `06-hooks-and-permissions.md` 哪一处，sync-inbox 问题 1 待裁）：补一句「actor 是角色的命令带 `--force` 一律拒收，退出码 3；角色会话里 `--as-gyb --quote --force --reason` 算 gyb 身份写，照写」；`05` 退出码 3 那一行同步加「含角色带 `--force`」。 已同步 2026-08-17：`05` 退出码那行已交 rl-part-05；规矩本身的定义处仍在 sync-inbox 问题 1 等 gyb。
- `08-trees-init-and-host.md`：init 那一段补「`loop/` 进 git，每次 commit 顺手带上，不另设 commit 动作；`.gitignore` 不排除 `loop/`」，08 的「没写清」第 5 条据此销掉。 已同步 2026-08-17。
- 设计文档「账本」一节公共骨架那一句：「七样加一个可选的 `fix_for`」改成「七样加两个可选：`fix_for`、`force_reason`」（统筹 session 回写）。 已同步 2026-08-17。
- runs 发射版去掉 `artifact_dir`、产物目录走 `<artifact_root>/<run_id>/` 约定，牵连四份：`05-rl-cli.md` 的 `rl run add` 签名去掉 `--artifact-dir`；`12-role-run.md` 第 70 行发射版必填清单去掉 `artifact_dir`、第 62 行「run_id 和产物目录名一致」补成「产物目录是 `<artifact_root>/<run_id>/`」、第 80 行看门狗「产物目录多久没新文件」按约定找；`21-pair-deploy-run.md` 第 77 行、`23-pair-run-analysis.md` 第 17 行发射版字段清单去掉 `artifact_dir`，`23` 第 38 行和「没写清」第 1 条（`data_path` 和 `artifact_dir` 差在哪）据此改写。这条约定归 `08`（`artifact_root`）还是 `12`（run 的产物）由统筹定。 已同步 2026-08-17：`12`、`21`、`23`、两份源文档由统筹改，`05` 交 rl-part-05；约定归 `08` 还是 `12` 攒进 sync-inbox 问题 4 等 gyb。
- 设计文档 run 一节收尾版「结束时间、退出状态、指标、真实耗时」四样补 `data_path`（统筹 session 回写）。 已同步 2026-08-17。
- `07-quick-lane.md`：第 60 行「格式松，入账校验只校验骨架和快车道标签」改成「中间版格式松，只校验骨架和 `ql_tag`；`open`、`merged`、`dropped` 三版按表查必填」；scratch 表 `open` 那一行 `branch` 改成「`branch`（deploy）」，并在 07 自己「没写清」第 1 条裁 analysis 的 `base_commit`、`branch` 填什么。 已同步 2026-08-17。
- 设计文档「账本」一节杂账「格式松、只校验骨架和快车道标签」改成「中间版格式松；开张、合回、放弃三版各有必填」（统筹 session 回写）。 已同步 2026-08-17。
