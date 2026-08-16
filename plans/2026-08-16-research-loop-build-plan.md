# research-loop 插件施工计划（2026-08-16 晚定稿，同日夜间按两轮模拟走查修订；草案部分待 gyb 逐条过）

这份文件是 `plans/2026-08-16-research-loop-next-steps.md`（下面叫「设计文档」）的施工版。设计文档写的是「做成什么样」和「为什么」，这份写的是「怎么把它做出来」：施工前的裁决、词表、九本账的字段、状态转移表、五份角色 json 加 gyb 的 use case 表、`bin/rl` 命令表、run 角色照 gpu-run 写的对照、阈值默认值、待验证清单、测试清单、施工步骤、公共规矩、两轮模拟的问题到原则的对照。两份文档的分工按设计文档原则 8：可枚举的东西（字段、状态、命令、阈值、测试）只在这份写一遍，设计文档指过来；这份第一节的裁决优先于设计文档正文；每条推翻设计文档某一行的裁决，设计文档那一行同步改掉并标日期，不留两个值。

标了「草案」的小节是我先写、gyb 还没逐条过的内容；没标的都是 gyb 已经裁过的。

## 一、施工前的裁决（2026-08-16 晚，gyb 裁）

1. 旧代码不要。`research-loop/` 目录下现有的 93 个文件（旧的入账脚本、schema、319 个测试、`idea-layer` 等四个旧角色 skill）整体退役，新插件从空目录开始写。旧代码留在 git 历史里，需要抄一段的时候去历史里翻，不在工作树里留任何旧文件。
2. 插件本体留在 `new1/research-loop/` 子目录里，不另开仓库。new1 是第一个用户，迁移 new1 的老代码进 `experiments/` 由 gyb 自己手动搬，插件的入口 skill 不做全量搬迁的 workflow，只保留「按需搬」的提醒。
3. 五个角色的模型：由 agent（subagent 或 workflow）调用的时候，run、deploy、analysis 用 opus，idea、reviewer 用 fable；gyb 手动加载角色的时候跟当前会话的模型一致。写进五份角色 json 的 `model` 字段，两个取值分开写。idea 和 reviewer 用 fable 与本机 `~/.claude/CLAUDE.md` 的「subagent 默认不用 Fable」不一致，按设计文档原则 8 工程内为准：这条裁决就是 gyb 点名的那一次例外，插件的 `README` 和角色 json 里都要明写「fable 是 gyb 2026-08-16 点名的例外」。
4. 公共规矩不再沿用 8 月 15 日 `redesign.md` 第 97 到 105 行的通例九条本文，改成从设计文档里重新抽一份，见第十三节。九条里第③条「机验人判」gyb 裁定去掉，其余八条 gyb 认可仍然代表本意；第⑦条里「自己域自己修」只留给 deploy 和 idea，run 出问题一律开 issue 给 deploy。
5. 钩子宽宽的：只挂 Write 和 Edit，只拦写别的角色的目录和直接写 loop/ 两类离谱事，其余放行；约束主要写在 SKILL.md 里。（2026-08-16 夜，看完第一轮模拟结果裁的。）
6. gyb 什么都能干：gyb 是超级用户，在任何终端、任何角色会话里都能插入，不受任何权限检查影响。
7. reviewer 什么都能读，隔离只体现在读的顺序。
8. 打架的地方以工程内为准，不以机器全局规矩为准。
9. 改文档不许打补丁：先把问题抽成原则，按原则改正文，再拿原则回头审一遍全部条目。第十四节是两轮抽出来的对照表。

另外两条 gyb 同时定的：run 角色照 `.claude/skills/gpu-run/SKILL.md` 写，能力至少覆盖 gpu-run 的全生命周期，再按设计文档的原则改错误处理、钩子、通信三处（见第七节）；总验收的五个任务留到验收前由 gyb 定。

第六轮（第二轮模拟之后）我改的、gyb 还没裁的设计变动，一行一条，gyb 不认就改回：（a）派活从同步等改成后台派加认领（原则 11）；（b）gyb 的豁免收窄成只豁免权限、不豁免完整性，硬写用 `--force --reason`；（c）`--as-gyb` 在角色会话里一律要 `--quote`，gyb 本人敲也要；（d）grants 只收裸终端；（e）分析单开单时口径可以是 proposed，交活才要全 approved（改了设计文档「idea 也可以给 analysis 开单，但是单子里只能引已经批准的口径行」那一句）；（f）快车道加 `rl ql open/close`、补单只要一份简报、验收人固定 gyb、analysis 也能走；（g）N 张发射单由一个 run 会话接整个 batch；（h）issue 加 `failed`、`orphaned`、`fyi` 三种 kind；（i）`rl inbox`、`rl trace`、`rl handoff amend/resume/reissue`、`rl decision confirm`、`rl session show/list/focus` 几条新命令。

## 二、词表（草案，正式名一律英文，代码、账本、SKILL.md、聊天里都用英文名）

角色五个：`idea`、`deploy`、`run`、`analysis`、`reviewer`。写账的人叫 actor，取值是五个角色或 `gyb`。

九本账的英文名和文件名：

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

派活单的三种 `work_type`：工单 `work_order`（idea 开给 deploy；快车道补单是 deploy 开给 deploy）、分析单 `analysis_order`（idea 或 gyb 开给 analysis）、发射单 `launch_order`（deploy 开给 run）。

派活单的七个状态：待干 `todo`、开干 `in_progress`、卡住 `stuck`、干完等待验收 `done_pending_review`、验收完成 `accepted`、打回 `rejected`、收回 `withdrawn`。派活单上的人：`owner`（开单角色，就是 `from_role`，单子从开到关归它；快车道补单和 gyb 开的单 owner 记 `gyb`）、`holder`（当前在干的会话的 session_id，只在 `in_progress` 非空）、`last_holder`（上一个 holder）。派发方式 `dispatch`：`auto`（owner 后台起 subagent）、`manual`（gyb 亲自接）、`none`（暂不派）。父单 `parent_id`；接替 `supersedes`；尝试 `attempt`。

决定来源的三类：`decision`（旧决定编号加版本）、`file`（仓库里的文件路径，可带 `#锚点`）、`run`（runs 账里的 run_id）。决定的根 `root_id`。

issue 的九种 `kind`：`cannot`（干不了）、`not_mine`（不归我干）、`denied`（被钩子拦了）、`failed`（跑失败，附 `stage` 取 `smoke`、`launch`、`crash`）、`anomaly`（结果反常）、`request`（申请）、`withdrawn`（你手上的单子被收回了，通知类）、`orphaned`（holder 会话死了单子交回了，通知类）、`fyi`（gyb 越过 owner 处理了你的单子，通知类）。

口径的两种 `kind`：`metric`、`figure`。口径的四个状态：`proposed`、`approved`、`rejected`、`retired`。

其余名词：部署报告 `deploy_report`，两份分别叫 `method`（不带文件）和 `detail`（带文件）；代码路径清单 `code_paths`；快车道 `quick_lane`，快车道标签 `ql_tag`（形如 `ql-20260816-01`，rl 在锁里分）；批次 `batch`（形如 `b-20260816-01`，只有分片语义）；研究线 `line`（就是根决定编号）；分步表 `step_table`；预计时长 `estimated_seconds`；真实耗时 `actual_seconds`；分析单的交付物 `output_paths`；发射单尝试上的配置字典 `config`；进度说明 `progress_note`；过版 `stale`；废除 `retired`；回收命令 `reclaim`；认领 `adopt`；产物根 `artifact_root`；分析产物根 `analysis_artifact_root`；配置文件 `research-loop.json`；命令入口 `bin/rl`；以 gyb 身份写账的旗子 `--as-gyb`，随行的 gyb 原话 `--quote`；硬写 `--force --reason`；裸终端写账时的会话名 `cli`；母版版本 `rules_version`；修账标记 `fix_for`。

「它不是什么」这一栏留到 `common/GLOSSARY.md` 写的时候逐条给 gyb 过，这里只钉名字。

## 三、九本账的字段级行格式（草案）

公共骨架七样，每本账每一行都有：`id`（主键）、`version`（从 1 起，同一个 `id` 的新版本是新的一行，默认查询只取最新版）、`status`（每本账各自的取值，校验按它查）、`ts`（写入时间，ISO 8601）、`actor`（五个角色或 `gyb`）、`session_id`（写入会话，裸终端是 `cli`）、`schema_version`（整数）；可选 `fix_for`（doctor 修账时记扫描项名字）、`force_reason`（gyb `--force` 时必填）。

decisions（六个文件同一个格式）：`id` 形如 `dec-idea-0007`、`dec-gyb-0002`，前缀只说开在哪本账，谁写的看 `actor`；`root_id`（add 时等于自己，update 继承，merge 时 `--root` 指定保留哪个）；`status` 取 `active` 或 `retired`；`text`；`sources` 列表，每项是 `{"kind":"decision","id":...,"version":...}`、`{"kind":"file","path":...,"anchor":可选}`、`{"kind":"run","run_id":...}` 三种之一，每一版都非空（update、confirm、retire、merge 不给 `--source` 时自动继承上一版）；`quote` 角色会话里 `--as-gyb` 写的行必填；`merged_from` 合并时必填。`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行。

issues：`id` 形如 `iss-0031`；`assignee` 五个角色或 `gyb`；`status` 取 `open`、`answered`、`closed`；`kind` 九选一；`stage`（`failed` 时必填）；`text`；`reply`（`answered` 时必填）；`handoff_id`（`cannot`、`failed`、`denied`、`withdrawn`、`orphaned` 时必填，其余可选）；`log_tail` 可选。改派等于追加一版换 `assignee`；`assignee` 是 `gyb` 的那一版（含首次开单）触发桌面通知。`reply` 只有 `assignee` 或 gyb 能写；`close` 只有开单的 actor 或 gyb 能写，另有两处自动关：`rl handoff accept` 关这张单关联的 `answered` issue，`rl inbox` 关读到的通知类 issue。

handoffs：`id` 形如 `ho-0012`；`work_type` 三选一；`from_role`（就是 owner，可以是 `gyb`）、`to_role`；`holder`、`last_holder`；`status` 七选一；`parent_id`（`launch_order` 必填指工单，`analysis_order` 可选，快车道补单空）；`supersedes` 可选；`batch` 可选；`line` 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着；`dispatch` 三选一；`quick_lane` 布尔；`decision_refs` 列表，每项 `{"id":...,"version":...}`（`work_order` 必填至少一项，`launch_order` 开单时从父单抄）；`evaluation_refs`（`analysis_order` 用，每项 `{"id":...,"version":...}`，开单时可以是 `proposed`，进 `done_pending_review` 时每项必须 `approved`）；`explanation`（`work_order` 必填；快车道补单由 deploy 写并含 gyb 点名原话）；`report_paths` 形如 `{"method":...,"detail":...}`（`work_order` 进 `done_pending_review` 时 `method` 必填且存在，`detail` 非快车道时必填且存在）；`code_paths` 列表（`work_order` 进 `done_pending_review` 时必填）；`output_paths` 形如 `{"notebook":...,"figures":[...]}`（`analysis_order` 进 `done_pending_review` 时必填且存在）；`attempts` 列表只在 `launch_order` 上，每项 `{"attempt":序号,"command","args","workdir","track","config":{...},"run_id","estimated_seconds","step_table":[...]}`，开单时第一项必填 `command`、`workdir`、`track`、`config`（字典：`model`、`params`、`dataset`、`split`、其余超参自由），`run_id` 由 rl 按 `<ho-id>-a<attempt>` 分配；`step_table` 每项 `{"step","kind":"gpu"|"cpu","smoke_seconds","scale_factor","estimated_seconds"}`，`estimated_seconds` 只加总最新一次尝试的行；`progress_note`（进 `todo` 且不是新建时必填）；`reason`（`rejected`、`withdrawn` 时必填，角色会话发起的 `withdrawn` 还要 `quote`）；`issue_id`（`stuck` 时必填）。

runs：`run_id`（主键，形如 `ho-0013-a1`，和产物目录名、tmux session、commit message 一致；快车道用 `ql_tag`）；`handoff_id`、`attempt`；`status` 取 `launched`、`finished`；`launched` 版必填 `commit`、`command`、`host`、`gpus`、`log_path`、`tmux_session`、`watch_cmd`、`started_at`、`config`（从发射单抄），产物目录按约定是 `<artifact_root>/<run_id>/`、账上不记；`finished` 版必填 `finished_at`、`exit_status`（`ok`、`failed`、`killed`）、`actual_seconds`（rl 从两个时间戳算），`exit_status` 是 `ok` 时 `metrics`（键是指标名、值是数）和 `data_path`（产物目录里给 analysis 算数用的那一个文件或子目录）必填。`actor` 是 `run` 或 `gyb`。

grants：`id` 形如 `grant-0003`；`grantee` 角色；`permission` 字符串，第一版只有一种 `read:notes`；`status` 取 `active`、`revoked`；`expires_at` 可选；`text`；`issue_id` 可选。`actor` 必须是 `gyb` 且 `session_id` 必须是 `cli`。

feedback：`id`；`target`（文件路径，或带前缀的编号 `rule-06`、`principle-06`）；`text`；`status` 取 `proposed`、`accepted`、`rejected`；`verdict_text`；`applied_to`（采纳时必填，路径列表，rl 校验每个路径存在）；`rules_version_after`（采纳时 rl 自动填）。提的那一版谁都能写，裁的那一版 `actor` 必须是 `gyb`。

evaluations：`id` 形如 `eval-0004`；`kind`；`name`；`definition`；`applies_to`；指标行二选一：`metrics_key` 或 `code_path`（形如 `analysis/common/metrics.py:accuracy`；`proposed` 时可以不存在，`approved` 时必须存在）；图行必填 `group_by`、`x`、`y`（三栏取值只能是 runs 顶层字段名、`config.<键>`、或已 `approved` 的指标口径编号）、`uses`；`status` 四选一；`reason`（打回时必填）；`quote`（批那一版必填，一句 quote 可以批多条）。`proposed` 那一版 `actor` 是 `analysis`；`approved` 的口径再 update 一版自动回 `proposed`；`approved`、`rejected`、`retired` 那一版 `actor` 必须是 `gyb`。

sessions：`session_id`（主键）；`role`；`model`（钩子从钩子输入的 JSON 里取，取不到记 `unknown`）；`launched_by` 取 `manual`、`subagent`、`workflow`；`rules_version`；`status` 取 `open`、`closed`；`open` 版必填 `started_at`；`last_activity`（不落账：rl 在查询 `rl session show`、`rl status`、`rl reclaim` 时现算，取九本账里该 `session_id` 的最大 `ts`，含 sessions 账自己的行；sessions 账不为刷新它追加版本；对外语义仍是「最后一次写账时间」）；`focus` 可选（reviewer 在审的决定编号）；`closed` 版必填 `ended_at`、`end_reason`（`hook`、`manual`、`reclaim`）、`released_handoffs`（销号时交回待干的单子列表）。开始版由钩子代角色写，`actor` 填角色。

scratch：主键是 `ql_tag`；`status` 取 `open`、`merged`、`dropped`；`role`（`deploy` 或 `analysis`）；`open` 版必填 `worktree`（deploy）或 `dir`（analysis）、`base_commit`、`branch`；中间版自由（建议 `note`、`metrics`）；`merged` 版必填 `handoff_id`；`dropped` 版必填 `reason`。`actor` 是 `deploy` 或 `analysis`。

## 四、派活单状态转移表（草案，`tables/transitions.json` 的内容）

每行六栏：从、到、谁能写、前提、之后谁拉起下游、子命令（原则 3）。gyb 对「谁能写」一栏一律豁免（原则 1）；「前提」一栏是完整性校验，对 gyb 生效，gyb 用 `--force --reason` 越过并留痕。holder 只在 `in_progress` 非空：进 `in_progress` 写 holder，离开 `in_progress` 一律清空并记 `last_holder`（原则 3 推论），表里不再逐行写。

| 从 | 到 | 谁能写 | 前提 | 之后谁拉起 | 子命令 |
|---|---|---|---|---|---|
| （新建） | `todo` | `from_role` | `work_order` 有 `decision_refs` 和 `explanation`；`launch_order` 有 `parent_id` 和第一次尝试的 `command`、`workdir`、`track`、`config`；`analysis_order` 有 `evaluation_refs`（可以是 proposed） | `dispatch=auto` 时 owner 后台起 subagent；`manual` 等 gyb；`none` 不动 | `handoff open` |
| （新建） | `done_pending_review` | `deploy`（快车道补单，owner 记 gyb） | `quick_lane` 为 true，`report_paths.method` 存在，`explanation` 非空，关联的 scratch 行状态是 `merged` | 无（等 gyb 验收，只有 gyb 能 accept） | `handoff open --quick-lane` |
| `todo` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`；`holder` 为空（非空退出码 2 并列出当前 holder）；`launch_order` 最新尝试已有 `launched` 未 `finished` 的 run 行时是认领，账行标 `adopted` | 无 | `handoff start [--batch B]` |
| `todo` / `stuck` | `todo`（内容追加） | owner、`to_role` | 只改内容：`launch_order` 追加一次尝试；`work_order` 补 `report_paths` 或 `code_paths`；`analysis_order` 补 `evaluation_refs`；状态不变 | 无 | `handoff amend` |
| `in_progress` | `stuck` | holder | `issue_id` 指向一条已存在的 issue，并且那条 issue 的 `handoff_id` 指回本单 | 无 | `handoff stuck` |
| `stuck` | `todo` | 回了 issue 的那个角色、owner | 关联 issue 状态是 `answered` | owner | `handoff resume` |
| `in_progress` | `done_pending_review` | holder | `work_order` 的 `report_paths` 和 `code_paths` 齐；`launch_order` 最新尝试的 run 行有 `exit_status=ok` 的 `finished` 版；`analysis_order` 的 `output_paths` 存在且 `evaluation_refs` 每项 `approved` | 无 | `handoff done` |
| `done_pending_review` | `todo`（内容追加） | owner、`to_role` | 只补 `report_paths` 或 `output_paths` 里丢了的路径，状态不变（doctor 修法用） | 无 | `handoff amend` |
| `done_pending_review` | `accepted` | owner；快车道补单只有 gyb | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi` | 无 | `handoff accept` |
| `done_pending_review` | `rejected` | owner | `reason` 非空 | owner | `handoff reject` |
| `rejected` | `todo` | owner、`reclaim` | 无 | owner | `handoff release` |
| `rejected` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`（原会话还活着直接接着干） | 无 | `handoff start` |
| `todo` / `in_progress` / `stuck` / `done_pending_review` / `rejected` | `withdrawn` | owner | `reason` 非空（角色会话发起还要 `quote`）；有 holder 时 rl 顺带开 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 时 rl 代 owner 连 `parent_id` 指向本单的下游单一起收，下游账行 actor 记发起人 | 无 | `handoff withdraw` |
| `in_progress` | `todo` | 销号钩子、`reclaim`、owner、gyb | `progress_note` 非空（钩子和 reclaim 自动填）；`launch_order` 且最新尝试有 `launched` 未 `finished` 的 run 行时不杀进程（等下一个 run 认领），reclaim 带 `--kill` 才先走中断收尾；rl 给 owner 开 `orphaned` 通知 | owner，owner 无活会话时进 `rl status` 的「等 gyb 拉起」 | `handoff release` |
| 任一非终态 | 同状态（接替） | owner | `--decision ID@V` 给新版本；rl 收旧单（`withdrawn`，级联）、开新单（继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单）、通知全部 holder | 同新建 | `handoff reissue` |

`accepted` 和 `withdrawn` 是终态。入账脚本只认这张表，表外的转移一律拒收，退出码 2。`stuck` 的单子销号和 reclaim 都不动（holder 已空），只有 issue `answered` 之后 `resume` 才回 `todo`。

## 五、角色 json 与 gyb 的 use case 表（草案，`tables/roles/<role>.json`、`tables/gyb-usecases.json`）

角色 json 五样：`reads`（读哪些账和目录，纪律，不设门禁）、`writes`（能 Write/Edit 的目录，钩子用）、`ledger_writes`（能调哪些 rl 写命令，入账校验用）、`dispatches_to`、`model`（`as_subagent` 和 `manual`，`manual` 写 `inherit` 是声明跟当前会话走，sessions 账落解析后的真实模型名或 `unknown`）。每个角色先列 use case，再从 use case 抄出四栏；`tests/test_skill_refs.py` 检查 SKILL.md 正文出现的每条 rl 写命令都在 `ledger_writes` 里、每个读的目录都在 `reads` 里，查询命令不查。

所有角色上线第一个动作：`rl inbox`。查询命令（show、list、trace、status、inbox、stale、doctor）谁都能调，不进 `ledger_writes`。

idea 的 use case：和 gyb 谈定决定并落账（decision add/update/confirm/retire/merge，替 gyb 记时带 quote）；开工单和分析单（handoff open，可带 `--manual`、`--no-dispatch`）；后台起 deploy 或 analysis subagent 并在它回来时验收或打回（handoff accept/reject）；决定改版后重派（handoff reissue）；收回（handoff withdraw）；重新拉起下游；申请读 notes/（issue open --kind request --to gyb）；回下游的 issue 并把单子交回待干（issue reply、handoff resume）；读 reviewer 清单。reads：九本账全部、`notes/`（要 grant）、`analysis/`、`experiments/` 下的部署报告目录、`review/`。writes：无目录。ledger_writes：decisions.idea 全部、handoffs 的 open/accept/reject/withdraw/release/reissue/resume/amend、issues 的 open/reply/reassign/close、feedback add。dispatches_to：deploy、analysis。

deploy 的 use case：接工单（handoff start）；写代码写报告；自决留痕（decision add 到 decisions.deploy）；开发射单并后台起 run（handoff open --type launch_order --parent ID，一次开 N 张同 batch）；验收发射单（accept/reject）；发射单卡住后改代码、追加一次尝试、回 issue、交回待干、再起 run（handoff amend、issue reply、handoff resume）；把 run_id 和指标补进 detail 报告后提验收（handoff done）；自己卡住开 issue（issue open、handoff stuck）；解决不了改派 gyb（issue reassign）；快车道（ql open/close、scratch add、handoff open --quick-lane、快车道里派 gpu-runner）；改宿主文件时列进报告、留决定、守宿主规矩。reads：`decisions.idea`、`decisions.gyb`、`decisions.deploy`、handoffs、issues、runs、feedback、`experiments/`、`ops/gpu_state.md`（快车道自己跑 GPU 时）。writes：`experiments/`（worktree 在仓库外，钩子不判）。ledger_writes：decisions.deploy 全部、handoffs 的 start/done/stuck/open/accept/reject/withdraw/release/resume/amend、issues 全部、scratch 全部（含 ql open/close）、feedback add。dispatches_to：run；gpu-runner（只在快车道）。

run 的 use case：接发射单或整个 batch（handoff start [--batch]）；认领已发射未收尾的尝试；读慢变量档案、探卡挑卡；smoke 并填分步表（handoff estimate，同 batch 其余单子 --copy-from）；发射前 commit 与发射；落数字账两版（run add、run finish，finish 同时调宿主收尾命令）；提验收（handoff done）；四种失败开 issue 并标卡住（issue open --kind failed --stage、handoff stuck）；读看门狗状态文件、杀进程、被收回或回收时中断收尾。reads：handoffs 里的 `launch_order`、issues（归自己的）、`experiments/`、`ops/gpu_state.md`、runs。writes：`artifact_root`（仓库外，钩子不判）。ledger_writes：runs 全部、handoffs 的 start/estimate/done/stuck、issues 的 open、decisions.run add（自决极少，比如挑卡的理由）、feedback add。dispatches_to：无。run 的 `rl inbox` 不查过版。

analysis 的 use case：接分析单（handoff start）；问 gyb 要统计什么并提口径（eval propose、被打回或要改时 eval update）；按口径写代码算数画图；交活（handoff done 附 output_paths）；分组键缺失开 issue 给 gyb（issue open --kind cannot）；发现代码问题开 issue 给 deploy；快车道先画一张图（ql open/close、scratch add）；自决留痕。reads：runs、evaluations、handoffs、issues、feedback、`decisions.idea`、`decisions.gyb`、`analysis/`。writes：`analysis/`。ledger_writes：evaluations 的 propose/update、handoffs 的 start/done/stuck、issues 的 open/reply、scratch 全部、decisions.analysis 全部、feedback add。dispatches_to：无。

reviewer 的 use case：按 gyb 点名审一条或一批决定（session focus）；读顺序先决定和代码、再运行记录、最后部署报告；按工单的 code_paths 和 runs 账里的 commit 审；写清单到 review/；自决留痕。reads：一切（九本账、全部目录）。writes：`review/`。ledger_writes：decisions.reviewer 全部、session focus、feedback add。dispatches_to：无。不开 issue。

| 角色 | as_subagent |
|---|---|
| idea | fable（gyb 2026-08-16 点名例外） |
| deploy | opus |
| run | opus |
| analysis | opus |
| reviewer | fable（同上） |

gyb 的 use case 表（原则 5 推论，`rl status` 的段落和 list 的过滤维度从这里倒推）：

| use case | 要看什么 | 倒推出的命令或段落 |
|---|---|---|
| 开工第一眼 | 两条线各到哪一步、谁在干、哪些等我 | `rl status [--line L] [--group-by line\|batch]`，每行带线名和决定编号，`--json` 行结构写死 |
| 批 | 等批的口径、等裁的 feedback | status 段 3、段 8；`eval approve ID... --quote`、`feedback accept` |
| 验收 | 等验收的单子（含快车道补单）、报告路径 | status 段 4；`handoff accept/reject` |
| 拉起 | owner 没有活会话的待干单、gyb 手动接的单 | status 段 5，每行附「加载哪个角色」的命令 |
| 看进度 | 在跑的实验到哪了、日志和监控命令 | status 段 1 的发射单行带 `log_path`、`watch_cmd`、按 batch 汇一段 |
| 查一个数从哪来 | run 到发射单到工单到决定 | `rl trace <任何编号>` |
| 收回、改版重派 | 引旧版的活单和它们的 holder | `decision update/retire` 当场打印；`handoff withdraw/reissue` |
| 收拾 | 很久没动的会话和单子、卡住的、没关的快车道 | status 段 6、7、9；`rl reclaim --only/--skip`，输出按 owner 分组附现成命令 |
| 修账 | doctor 扫出没修的 | status 段 10；`rl doctor` 每项附修法和「修完之后归谁推」 |
| 会话 | holder 那个 session 是谁、活没活着 | `rl session show/list [--alive] [--role R]` |

## 六、`bin/rl` 命令表（草案）

actor 的判定（原则 1）：`rl` 从会话状态文件读当前角色（状态文件由角色 skill 头部钩子在加载时写，路径 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`）；读不到状态文件就是裸终端，actor 是 `gyb`，session_id 记 `cli`（gyb 2026-08-16 夜裁：裸终端就是 gyb，不要 `--as-gyb` 参数）。角色会话里任何命令加 `--as-gyb` 就以 gyb 身份写，session_id 照记当前会话，必须同时给 `--quote "<gyb 原话>"`，不论敲键盘的是谁（rl 分不出，见原则 1 推论），缺 quote 退出码 2；这是给 reviewer 事后查的痕迹。actor 是 gyb 时跳过「谁能调」和转移表「谁能写」；完整性前提照查，`--force --reason` 越过并记进账行。grants 只收 `cli`。

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl init` | 在研究仓库建 `research-loop.json`、`loop/` 九本账、`experiments/`、`analysis/`（含公共统计件模板和 `analysis/scratch/`）、`review/`、`notes/`，往 CLAUDE.md 追加一节（三句，见设计文档「分权与钩子」），问一次要不要给 idea 发 `read:notes` | gyb |
| `rl session start --role R [--model M] [--launched-by manual\|subagent\|workflow]` / `rl session end [--session ID] [--reason]` / `rl session focus --decision ID` / `rl session show ID` / `rl session list [--alive] [--role R]` | 登记和销号，钩子调；`end` 只扫 `in_progress` 且 holder 是本会话的单子，有就 release 交回 `todo`、自动填 `progress_note`、给 owner 开 `orphaned`、experiments/ 脏改动打 `wip/<ho-id>` 分支；`--session ID` 给 gyb 关别的会话 | start/end 钩子和 gyb，focus reviewer，查谁都行 |
| `rl inbox` | 角色的收件箱：本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知（读过即关）、本角色提的 feedback 的裁决 | 角色会话，上线第一动作 |
| `rl decision add --text --source K:V ... [--quote ...]` | 追加一条新决定，编号自动分配，落 actor 自己那本（角色会话 `--as-gyb` 落角色那本） | 五个角色、gyb |
| `rl decision update ID --text [--source ...] [--quote ...]` / `rl decision confirm ID --source ...` | 追加一版（update 换正文；confirm 正文不变只加来源）；不给 source 就继承上一版；写完当场列出引旧版而没到终态的单子和 holder | 同 actor（跨角色改别人的决定在自己那本 add，来源指原决定） |
| `rl decision retire ID [--source ...]` / `rl decision merge ID1 ID2 ... --text --root ID [--source ...]` | 废除；合并成新决定，被合并编号自动进 sources 和 merged_from，旧的各追加一版 `retired`；retire 同样列受影响的单子 | 同 actor |
| `rl decision show ID [--version V] [--history] [--with-runs]` / `rl decision list [--actor A] [--line L]` | 默认最新版；`--with-runs` 沿 parent_id 链反查各版本派出的单子和 run 与 metrics | 谁都行 |
| `rl decision stale [--mine] [--handoff ID]` | 过版检查，默认只列和本会话手上单子有关的，`--all` 全库 | 谁都行 |
| `rl trace <dec-\|ho-\|run_id\|iss-\|eval->` | 打出到决定各版本的整条链 | 谁都行 |
| `rl issue open --to R --kind K [--stage S] --text [--handoff ID] [--log-tail FILE\|--log-text -]` / `rl issue reassign ID --to R` / `rl issue reply ID --text` / `rl issue close ID` / `rl issue link ID --handoff ID` / `rl issue show ID` / `rl issue list [--open] [--to R] [--kind K]` | 问题条；`--to gyb`（开单或改派）触发通知；`link` 是 doctor 修法 | 按第五节 ledger_writes，查谁都行 |
| `rl handoff open --type T --to R [--parent ID] [--decision ID@V ...] [--explain ...] [--eval ID@V ...] [--command ... --workdir ... --track ... --config k=v ...] [--batch B] [--manual\|--no-dispatch] [--quick-lane --report-method P --ql QL]` | 开单，落 `todo`；`launch_order` 从父单抄 decision_refs 和 batch、分 run_id；带 `--quick-lane` 的工单直接落 `done_pending_review` | owner |
| `rl handoff start ID [--batch B]` / `amend ID [--command ... --workdir ... --track ... --config ...] [--report-method P --report-detail P --code-path P ...] [--eval ID@V ...]` / `stuck ID --issue ID` / `resume ID` / `done ID [--actual-seconds N] [--notebook P --figure P ...]` / `accept ID` / `reject ID --reason` / `withdraw ID --reason [--quote] [--cascade]` / `release ID --note ...` / `reissue ID --decision ID@V` | 转移表里的每一行一个子命令 | 按转移表 |
| `rl handoff estimate ID --step NAME --kind gpu\|cpu --smoke-seconds S --scale F` / `rl handoff estimate ID --copy-from ID2 [--scale F]` | 往最新一次尝试追加分步表一行，`estimated_seconds` 加总本次尝试；同 batch 复制 | run |
| `rl handoff show ID` / `rl handoff list [--status S] [--owner R] [--holder SESSION] [--to R] [--batch B] [--decision ID] [--line L]` | 查（`--mine` 删掉，拆成 owner 和 holder） | 谁都行 |
| `rl run add --handoff ID --attempt N --commit ... --host ... --gpus ... --log ... --tmux ... --watch-cmd ...` / `rl run finish RUN_ID --exit ok\|failed\|killed [--metric k=v ...] [--data-path P]` / `rl run relink RUN_ID --handoff ID` / `rl run show RUN_ID` / `rl run list [--handoff ID] [--decision ID] [--batch B] [--line L] [--all]` | 数字账两版，`add` 从发射单抄 command、config、run_id；`finish` 算 actual_seconds、同进程跑反常预警、调宿主收尾命令模板；`list` 默认只出每张单最新尝试且 `exit_status=ok` 的行，`--all` 全出；`relink` 是 doctor 修法 | 写 run 和 gyb，查谁都行 |
| `rl grant add --to R --permission P [--expires ...] [--issue ID]` / `rl grant revoke ID` / `rl grant list` / `rl grant show ID` | 授权，只收 `cli` | 写 gyb，查谁都行 |
| `rl feedback add --target ... --text` / `rl feedback accept ID --applied-to FILE ... [--text]` / `rl feedback reject ID --text` / `rl feedback show ID` / `rl feedback list` | 反馈账；accept 校验路径存在、自动 bump `rules_version`、列出还活着的会话和它们的 rules_version、打印待办（还要改哪几处、要不要收会话、单独 commit 加跑测试） | 提谁都行，裁只有 gyb，查谁都行 |
| `rl eval propose --kind metric\|figure --name ... --definition ... [--metrics-key K \| --code-path P] [--group-by ... --x ... --y ... --uses ID ...] --applies-to ...` / `rl eval update ID ...` / `rl eval approve ID ... --quote` / `rl eval reject ID --reason` / `rl eval retire ID` / `rl eval show ID` / `rl eval list [--status S]` | 口径账；approve 一次多条一句 quote；approved 后 update 回 proposed | 提和改 analysis，批和打回 gyb，查谁都行 |
| `rl ql open [--role deploy\|analysis] [--from ho-ID]` / `rl ql close QL --merged --handoff ID \| --dropped --reason` / `rl scratch add QL [--note ...] [--metric k=v]` / `rl scratch list [--status S]` / `rl scratch show QL` | 快车道进出和杂账；open 在锁里分 ql_tag、建 worktree（`quick_lane.worktree_root/<ql_tag>`，分支同名）或 `analysis/scratch/<ql_tag>/`；`--from` 把待干工单标 quick_lane | deploy、analysis |
| `rl status [--line L] [--group-by line\|batch] [--json]` | gyb 的收件箱十段：1 没到终态的单子（owner、holder 及活没活着、状态、挂了多久、线、发射单带 log_path 和 watch_cmd）；2 assignee 是 gyb 的 open issue（超过阈值的标出）；3 等批的口径；4 等验收的单子；5 等 gyb 拉起的（owner 无活会话的 todo、`dispatch=manual` 的）；6 过版的单子和 retired 决定名下的活单；7 holder 会话超过 `status.stale_holder_minutes` 没写账的开干单；8 等裁的 feedback；9 review/ 最近的清单、活着的会话（含 focus）、没关的快车道；10 上次 doctor 没修的。第一行打印距上次 reclaim 几天 | 谁都行 |
| `rl reclaim [--session-older-than H] [--handoff-older-than H] [--only ID ...] [--skip ID ...] [--kill] [--apply]` | 列出超过阈值没动的会话和单子和快车道，`--apply` 才动手：会话标 `reclaim` 销号并 release 名下开干的单；开干的发射单默认不杀进程（留给认领），`--kill` 才走中断收尾（杀进程、释放显存、宿主销号、runs 落 killed）；`stuck` 的只把 issue 改派 owner；`done_pending_review` 和 `todo` 的只列出附现成命令；结束按 owner 分组打印待拉起的单子和加载命令，并自动跑一遍 doctor | gyb |
| `rl doctor [--ack ITEM ID]` | 扫九本账，每项附修法命令和「修完归谁推」：编号重复；引用悬空；`stuck` 单子没有 issue（修法 `issue link`）；`cannot`/`failed`/`denied` 且 open 且没有单子指回的 issue；`done_pending_review` 的交付物路径不存在（修法 `handoff amend`）；runs 行 `handoff_id` 为空、悬空或不是 launch_order（修法 `run relink` 或 `--ack`）；runs 有 `launched` 版长期没 `finished` 版；runs 挂在 `withdrawn` 的单子上；快车道工单已 accepted 但没有关联发射单；approved 口径引的 metrics 键在 runs 账里不存在；`answered` 超过 N 天没 close 的 issue；单子回了 `todo` 而关联 issue 还 open；`in_progress` 的 holder 不在活着的会话里；sessions 没有结束版且超阈值没写账；retired 决定名下有活单；决定来源指 notes/ 但 grants 里没有该 actor 的 read:notes；accepted 的 feedback 的 applied_to 里没同时含母版和文档；loop/runs.jsonl 与宿主 ops/runs.jsonl 对不上的 run_id | 谁都行；角色跑只看不修，修法报给 owner 或 gyb |
| `rl notify --text` | 内部用，发桌面通知，机制见待验证第 6 条；推送表：issue assignee 变 gyb（含首次开单）、单子进 `done_pending_review` 且 owner 是 gyb 或 `dispatch=manual`、feedback 提出、owner 无活会话的 todo 出现、doctor 有没修的 | rl 自己 |

退出码：0 成功；2 校验拒收（原因写到标准错误，包含下一步该做什么）；3 角色无权（同上，附「开 issue 给谁」的命令）；4 文件锁等待超时。所有子命令支持 `--json`；`rl status --json` 每行至少含 `id`、`work_type`、`owner`、`holder`、`holder_alive`、`status`、`age_hours`、`line`、`decision_refs`、`batch`、`log_path`、`watch_cmd`。

锁：`loop/.lock` 一把全局文件锁，扫号、分配编号（含 ql_tag、run_id、batch）、追加三步在同一把锁里；跨账写入按设计文档「账本」一节的写序，先 issue 后 handoff。

## 七、run 角色照 gpu-run 写（草案）

gpu-run 的八个阶段对应到 run 的 use cases，一行一个：

| gpu-run 阶段 | run 的 use case | 改动 |
|---|---|---|
| Phase 0 读档案 `ops/gpu_state.md` | 接到 `launch_order` 后第一件事读慢变量档案；接单前先看最新尝试有没有 `launched` 未 `finished` 的 run 行，有就认领，跳到 Phase 5 | 档案路径进 `research-loop.json` 的 `gpu_state_path`；认领是新增 |
| Phase 1 实探空卡 `run.py gpu-jobs free` | 同 | 命令进配置的 `launcher.free_cmd` |
| Phase 2 挑卡分片 | 同，规则引用 gpu-run 的 `references/launch-methodology.md`；一个 run 会话接整个 batch，按宿主发射器自己的分片规矩发 N 份 | 不再一个 workflow 起 N 个 run |
| Phase 3 smoke | 同，并且多做一件事：先读代码列出每一步干什么，smoke 时逐步计时，`rl handoff estimate` 填分步表（同 batch 只实测一张，其余 `--copy-from`）；smoke 标准输出落 `artifact_root/smoke/<run_id>.log`；smoke 失败直接 `issue open --kind failed --stage smoke` 加 stuck，分步表不是前提 | 分步计时和 smoke 日志是新增 |
| Phase 4 发射前 commit、`run.py launch`、交监控命令 | 同，命令模板进配置的 `launcher.launch_cmd`，`--run-id` 和 `--track` 从发射单尝试上抄；发射成功后 `rl run add` 落发射版（含 tmux session 名和监控命令） | 三处登记之外多一处 runs 账；宿主发射器写 ops/ 的三个文件是 Bash 写入，钩子不看；loop/ 进宿主脏树白名单 |
| Phase 5 采样器接管 | 看门狗 monitor 只在 run 上线时起，只判、只写自己的状态文件，卡死和超时分开判，每轮顺带查本单是不是 `withdrawn` 或被 reclaim；run 会话每轮读状态文件，杀进程和写账都由 run 会话做 | 卡死阈值沿用 new1 `ops/verdicts.py` 的自适应判定线，超时用最新尝试的 `estimated_seconds` 乘宽松系数；monitor 不写九本账 |
| Phase 6a 正常收尾五连 | 汇报、`rl run finish --exit ok` 记数字（算 actual_seconds、同进程跑反常预警、调 `launcher.finish_cmd` 落宿主账）、释放显存、销号、commit；然后 `rl handoff done` | 数字进 `loop/runs.jsonl`，宿主 `ops/runs.jsonl` 由 finish_cmd 一起落，两本并存，doctor 对账 |
| Phase 6b 中断 | 跑挂：`rl run finish --exit failed`（同样调 finish_cmd），`issue open --kind failed --stage crash`，`handoff stuck`。被收回或被 reclaim `--kill`：`rl run finish --exit killed` 加收尾，不改单子状态 | 中断一律留痕；两种中断分开写 |

三处改进：错误处理是 smoke 失败、发射失败、跑挂三种一律 `rl issue open --to deploy --kind failed --stage smoke|launch|crash` 附日志末 40 行和 traceback、结果反常 `--kind anomaly --to gyb`，run 不修代码不重试，issue 里带 `handoff_id`；钩子是 run 会话装写权钩子（Write/Edit 进 `experiments/`、`analysis/`、`review/`、`notes/`、`loop/` 一律 deny 并提示开 issue，其余放行）加登记销号钩子；通信是发射单的尝试对象替代口头传命令，run_id、track、config 都从单子抄，分步表和 `actual_seconds` 让几次之后知道外推偏多少，看门狗的判定经 run 会话进 issues 账而不是只进网页。

## 八、阈值默认值（草案，写进 `research-loop.json`，gyb 可改）

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `watchdog.stall_mult` | 5 | 卡死判定线 = 5 倍典型心跳间隔，沿用 `ops/verdicts.py` |
| `watchdog.stall_floor_samples` | 3 | 判定线下限三轮采样 |
| `watchdog.warmup_seconds` | 1800 | 开局 30 分钟不判卡死 |
| `watchdog.gpu_util_zero_seconds` | 900 | 显卡利用率连续 15 分钟为零算一路证据 |
| `watchdog.timeout_factor` | 3 | 超时 = 最新尝试 `estimated_seconds` 乘 3 |
| `issues.gyb_stale_hours` | 24 | `rl status` 段 2 标出超过 24 小时没动的 |
| `issues.answered_stale_days` | 3 | doctor 报 answered 超过 3 天没 close |
| `status.stale_holder_minutes` | 30 | `rl status` 段 7：holder 会话超过 30 分钟没写账的开干单 |
| `reclaim.session_idle_hours` | 48 | 会话超过 48 小时没写任何账算很久没动 |
| `reclaim.handoff_idle_hours` | 72 | 单子超过 72 小时没转移算很久没动 |
| `reclaim.ql_idle_days` | 7 | 快车道超过 7 天没关列进 reclaim |
| `anomaly.metric_extremes` | `[0, 1]` | 指标落在 0 或 1 触发反常预警，`rl run finish` 里查 |
| `anomaly.duration_factor` | 3 | 实际耗时超过预计 3 倍触发反常预警，同上 |
| `status.review_recent_days` | 7 | `rl status` 列最近 7 天的 review 清单 |
| `notify.reminder_days` | 7 | 每 7 天提醒 gyb 跑 `rl reclaim`、看 feedback、跑 doctor、落母版 |
| `quick_lane.worktree_root` | `<仓库>/../<仓库名>-ql/` | 快车道 worktree 建在哪 |

## 九、待验证清单（讨论已收口，施工第 0 步就测；每条写测法、通过标准、失败备案）

| # | 要验证的 | 测法 | 通过标准 | 失败备案 |
|---|---|---|---|---|
| 1 | Bash 环境里有没有现成的会话 id 变量 | 在会话里 `env \| grep -i session`，再对比钩子输入的 `session_id` | 同一个值 | SessionStart 钩子写状态文件，rl 按 `cwd` 加最近一次登记找 |
| 2 | skill 头部声明的钩子能不能给命令带参数 | 写一个测试 skill，头部钩子命令 `hook.sh --role test`，加载后触发看参数到没到 | 脚本收到 `--role test` | 五个角色各一份钩子脚本，内容相同只差常量 |
| 3 | monitor 的 `when: "on-skill-invoke:run"` 写法 | 写一个只打印一行的 monitor，加载 run skill 看起不起 | 加载后进程在、不加载不在 | monitor 常驻，脚本自己读会话状态文件判断当前角色是不是 run |
| 4 | skill 头部禁止模型调用的声明能不能锁入口 skill | 加声明后让模型自己调一次 | 调不动 | 入口 skill 的 SKILL.md 第一行写「模型调用即违规」靠纪律，另外 rl init 检查调用者状态文件不是任何角色 |
| 5 | SessionEnd 和 SubagentStop 在 subagent 结束时触发不触发、会话 id 是不是同一个 | 起一个加载角色的 subagent，让它写一行账，结束后查 sessions 账 | 有 `ended_at`、`session_id` 和 `started_at` 那行相同 | 全靠 `rl status` 段 7 加 `rl reclaim`，提醒周期从 7 天缩到 1 天 |
| 6 | 桌面通知机制 | 试 Claude Code 自带推送、`notify-send`、终端铃三种 | gyb 桌面看得到 | 退到 `rl status` 单列那一层，通知不做 |
| 7 | 定时提醒机制 | 试 Claude Code 的 schedule 和系统 cron | 到点 gyb 收得到 | `rl status` 第一行打印距上次 reclaim 几天（已是正案的一部分），提醒不做 |
| 8 | subagent 里加载角色 skill，头部钩子装不装得上、写权拦不拦 | 起 subagent 加载 deploy，让它写 `analysis/x.md` | 被 deny | subagent 路线改成 workflow 里的 `agentType` 指向 `agents/<role>.md`，钩子在 agent 定义里声明；再不行 subagent 接单只靠纪律加 reviewer 事后查。测完在设计文档 run 一节写死走哪一案，删掉另一案 |
| 9 | 后台 subagent（原则 11）：父会话活着时后台 subagent 能不能跑几个小时；父会话结束后台 subagent 会不会被杀 | 起 deploy 会话后台起一个 sleep 两小时的 run subagent，两种情况各试一次 | 活着时能跑完并回通知；父会话结束时的行为有结论 | 被杀的话正案不变（GPU 在 tmux、单子在账上、下一个 run 认领），只是待认领的单子多；同步等的老方案不再回来 |
| 10 | 钩子输入里有没有模型标识 | 打印 SessionStart 钩子的输入 JSON | 有 model 字段 | sessions.model 记 `unknown`，doctor 列出来，gyb 事后补 |
| 11 | 改一行母版不重启 claude 再加载一次角色，读到的是不是新文本 | 改 common/ 一行，同一进程再 `/` 加载角色 | 模型看到新文本 | feedback accept 的待办里加一句「改完母版必须重开终端」 |

原第 9 条「rl 读不到状态文件按 gyb 处理」gyb 2026-08-16 夜已裁：就是 gyb，不加参数。原第 9 条「上游同步等几个小时」按原则 11 改题成现在的第 9 条。

## 十、测试清单（草案，`research-loop/tests/`）

1. 锁与撞号：两个进程同时追加同一本账各 100 行，编号无重复、行数正确；ql_tag 和 run_id 同样不撞。
2. 转移表：对每一行合法转移各一个用例，加三个非法转移用例（跨状态、错角色、缺前提），非法一律退出码 2 并且账里没有新行；`holder` 只在 `in_progress` 非空，进写、出清、`last_holder` 留下；start 时 holder 非空拒收；认领用例（最新尝试有 launched 未 finished 的 run 行时 start 标 adopted）。
3. 决定来源：空列表拒收；三类来源各一个用例；`file` 类路径不存在拒收、带锚点通过；`run` 类 run_id 不在 runs 账拒收；update 不给 source 继承上一版；confirm 正文不变版本加一；merge 自动并入被合并编号并按 `--root` 记根；`decisions.gyb.jsonl` 拒收非 cli 行；update 时打印引旧版的活单。
4. 交付物：`work_order` 缺任一报告路径或 code_paths 拒收；快车道补单只要 method；`analysis_order` 缺 notebook 拒收、引 proposed 口径开单通过、交活时有 proposed 拒收；`launch_order` 没有最新尝试 `exit_status=ok` 的收尾版拒收；`quick_lane` 工单新建直达 `done_pending_review` 且只有 gyb 能 accept。
5. 过版：派活单引 v1、决定更新到 v2 之后 `rl decision stale` 列出来，`rl status` 也列，`rl inbox` 对相关角色列；口径引用同样查过版。
6. 跨账写序：模拟 issue 写成功、handoff 写失败，`rl doctor` 报对应项并给 `issue link` 修法。
7. 销号：holder 名下有 `in_progress` 单子时 `rl session end` 自动 release、progress_note 非空、owner 收到 `orphaned`；`done_pending_review` 和 `stuck` 的单子不挡销号；`--session ID` 能关别的会话。
8. 钩子：deploy 会话 Write `analysis/x` 被 deny 且标准错误含「开 issue」命令；任何角色 Write `loop/x.jsonl` 一律 deny；run 会话 Write `experiments/x` deny；deploy 会话 Write 仓库根 `run.py` 放行；deploy 会话 Write 仓库外 worktree 路径放行。
9. actor 与权限：analysis 调 `rl grant add` 退出码 3；analysis 会话里 `rl eval approve --as-gyb` 缺 `--quote` 退出码 2、带 quote 通过且账行 actor 是 gyb、session_id 是当前会话；裸终端 `rl eval approve` 直接通过、session_id 是 `cli`；裸终端 `rl grant add` 通过、角色会话 `--as-gyb` 的 `grant add` 拒收；非 run 调 `rl run add` 退出码 3、gyb 调通过；gyb 缺必填字段拒收、带 `--force --reason` 通过且账行有 force_reason。
10. runs 账 schema：发射版缺 `commit` 或 `config` 拒收、不要求 metrics；收尾版 `exit_status=ok` 缺 `metrics` 拒收；`failed` 不要求 metrics 但要有 actual_seconds；`finish` 时指标落在 0 或 1 自动开 `anomaly` issue 给 gyb；`run list` 默认不出 killed 和旧尝试，`--all` 出。
11. `rl status`、`rl inbox` 与 `rl reclaim`：造三张不同时长的单子，阈值内外各列对；收件箱十段各造一条都出现；inbox 四类各造一条；reclaim `--only`/`--skip` 生效、开干的发射单默认不杀、`--kill` 才杀；`--line` 过滤对。
12. 端到端：沙盒仓库 `rl init` 建树，模拟 idea 开单、deploy 接单写代码写报告提验收、idea 打回、单子回 `todo`、deploy 再接、idea 验收，全程只经 rl，最后 `rl doctor` 零报告；第二条：deploy 开发射单、run 接单 smoke 失败 stuck、deploy amend 一次尝试 resume、run 再接 ok、`rl trace` 从 run_id 打回决定。
13. `tests/test_skill_refs.py`：五份 SKILL.md 里出现的每条 rl 子命令、账名、状态名、目录名都在第二、五、六节里查得到，写命令在该角色的 `ledger_writes` 里，查询命令不查；SKILL.md 里没有 common/ 母版条文的副本。
14. 口径：propose 时 code_path 不存在通过，approve 时不存在拒收；reject 后 update 一版再 approve 通过；approved 后 update 回 proposed；figure 行缺 `uses` 或 group_by 取值不在允许域拒收；一次 approve 多条一句 quote。
15. 收回与接替：对有 holder 的单子 withdraw，自动出现 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 沿 parent_id 收掉派生的发射单；`reissue` 收旧开新、supersedes 指旧单。
16. 快车道：`ql open` 分标签建 worktree、scratch 开张行；`ql close --merged` 要求 handoff 存在、`--dropped` 要 reason；status 只列没关的。
17. feedback：accept 校验 applied_to 每个路径存在、rules_version 加一、sessions 开始版记 rules_version、inbox 对提的人列裁决。

每一步施工结束 `tests/run_all.py` 全绿才 commit。

## 十一、施工步骤（每步交付物、验收、依赖、执行者与模型）

施工纪律四条从 8 月 15 日的记录搬过来：每步封闭验收（这一步的测试全绿才算完）、检查器先于被检查物（先写 schema 校验和测试，再写入账代码）、一步一个动件（一个 commit 只做一件事）、修三轮修不动就废掉重做。

| 步 | 交付 | 验收 | 依赖 | 执行者 |
|---|---|---|---|---|
| 0 验证 | 第九节 11 条的结果写进 `plans/2026-08-1x-research-loop-verify.md`，每条写实测结果和选了主案还是备案；备案影响正文的当场改设计文档，删掉另一案 | 11 条都有结论 | 无 | 主会话亲自做，要真会话 |
| 1 清空 | `git rm -r research-loop/`，只留空目录和 `.claude-plugin/plugin.json` 新写一份 | 目录里只有 plugin.json | 无 | 主会话 |
| 2 架构文档 | `research-loop/ARCHITECTURE.md`，两棵树每个文件一行：干什么、谁读、谁写、改它连带改哪些；十一条原则抄一份在开头 | gyb 读一遍点头 | 步 0（备案影响树） | 主会话写 |
| 3 共同底座 | `tables/ledgers.json`、`tables/transitions.json`、`tables/roles/*.json`、`tables/gyb-usecases.json`、`schemas/*.schema.json`、`scripts/rl_lib.py`（锁、编号、追加、校验、actor 判定）、`bin/rl` 骨架、第十节测试 1 到 7、9、10、14、17 | `tests/run_all.py` 全绿 | 步 2 | 工单化，走 ticket-run，实现者 sonnet、评审 opus |
| 4 交流机制 | `hooks/`（写权钩子、登记销号钩子）、`rl status`、`rl inbox`、`rl trace`、`rl reclaim`、`rl doctor`、`rl notify`、`monitors/`（看门狗）、快车道命令、测试 8、11、15、16 | 全绿；在真会话里手动触发一次 deny 和一次销号 | 步 3 | 工单化同上；真会话验证主会话做 |
| 5 公共母版 | `common/GLOBAL-RULES.md`（第十三节八条加十一条原则，带 rules_version 和 rule-NN/principle-NN 编号）、`common/GLOSSARY.md`（第二节词表加「它不是什么」）、`common/SPEC-TEMPLATE.md`（五栏）、`common/READING.md`（读法栏原话） | gyb 逐条过 | 步 3 | 主会话写，中文底稿给 gyb 过，正式版英文 |
| 6 五个 SKILL.md | `skills/idea/`、`skills/deploy/`、`skills/run/`、`skills/analysis/`、`skills/reviewer/` 各一份 SKILL.md（英文，头部带钩子声明，正文有 use case 表，只引用母版不抄），run 的照第七节，入口 `skills/research-loop/SKILL.md` 只干 init、迁移提醒、领路（路线图见设计文档） | 测试 13 全绿 | 步 4、5 | gyb 开三个终端并行，每个终端加载 `claude --plugin-dir ./research-loop`，一个终端一到两个角色 |
| 7 最小一条路 | 在临时沙盒仓库 `rl init` → 加载 idea 写一条决定开一张工单 → 加载 deploy 接单写代码写报告提验收 → 回 idea 打回 → deploy 再接 → idea 验收 → `rl doctor` 零报告；再走一遍测试 12 的第二条（发射单 smoke 失败到 trace）；然后在 new1 跑 `rl init`，gyb 改 new1 CLAUDE.md 的 GPU 那一行和脏树白名单 | 沙盒全程只经 rl；new1 的 `loop/` 长出来、CLAUDE.md 只多一节 | 步 6 | 主会话，真会话 |
| 8 总验收 | gyb 定五个任务，每个角色两个 agent 一个加载 skill 一个不加载各做一遍，产出摆一起 | gyb 自己看 | 步 7 | gyb 定任务，主会话派 agent（模型按第一节第 3 条） |

每步一个或多个 commit，commit message 前缀 `research-loop v2:`；用起来之后改母版的 commit 前缀 `research-loop rules:`，改完跑一遍 `tests/run_all.py`。

## 十二、留给 gyb 的

总验收的五个任务在步 8 前定；第一节末尾（a）到（i）九条我改的设计变动逐条裁；第二节到第八节的草案逐条过，过的时候一次一节；第三轮模拟要不要跑、跑之前先把 new1 第一次 rl init 那个没跑成的场景补上；new1 CLAUDE.md 的两处宿主改动（GPU 铁律对 run 会话的读法、脏树白名单加 loop/）在步 7 时由 gyb 亲手改。

## 十三、公共规矩八条（从设计文档抽出，替代 8 月 15 日的通例九条；母版里编号 rule-01 到 rule-08）

1. 岔路缺省：规格没写到的岔路，角色按十一条原则推着往下干并追加一条决定，来源写清依据；替 gyb 说话的写入（`--as-gyb`、evaluations 批准、feedback 裁决）没有 gyb 当场的原话一律硬停，不可逆动作（收回、废除）硬停并带原话或理由。
2. 自决必留痕：角色自己做的每个决定进自己那本 decisions 文件，来源不许空；改变实验结果的选择才算自决，纯写法不算；gyb 在角色会话里当场拍的板算 gyb 的决定，落同一本账、actor 记 gyb、带 quote。
3. 数字只经脚本入账：runs 账只有 run 的脚本能写（gyb 例外），实验数据一个 schema，禁止用眼睛读日志填数。
4. 证据配路径：每个数字配可复现的执行路径，统计类证据走 analysis 的 notebook；单个 run 的原始指标可以直接引，跨 run 的对比、聚合、画图一律走分析单。
5. 口径不发明：analysis 只算 gyb 说要看的数、只画 gyb 说要画的图；写代码不算算数，出数才要 `approved` 的口径。
6. 故障分域：deploy 和 idea 接到问题先判病因在不在自己域，在就地修；run 出问题一律开 issue 给 deploy，不自行重试，重来是发射单上的下一次尝试；analysis 卡住开 issue 给出问题的角色；reviewer 不开 issue，卡住也只写进清单交给 gyb。
7. 改规矩走反馈账：角色不许自改母版和规格，提到 feedback 之后照现行母版继续干，不等裁决；裁决只对下次加载的会话生效。
8. 出圈即留痕：钩子拦下的，原话告诉模型开哪条 issue；钩子不拦但越出自己 writes 的（宿主文件、Bash 写入），列进报告并留决定并守宿主规矩；读账一律经 rl 查询命令，查询命令谁都能调。

8 月 15 日第③条「机验人判」不收录（gyb 裁定意义不明）。

## 十四、模拟走查：问题到原则到改动

### 第一轮（2026-08-16 夜）

第一轮模拟的原始结果在 `plans/2026-08-16-research-loop-simulation-round1.md`。critic 归并的 13 条跨场景缺口和单场景独有的二十来条，按根子归成八堆，每堆一条原则（设计文档第二节前八条），这份施工计划按原则改的地方如下：

| 根子 | 原则 | 归进来的问题 | 改了这份的哪里 |
|---|---|---|---|
| actor 和角色混成一个概念 | 1 身份 | gyb 在角色会话里写不了 gyb 权、裸终端 session_id、手动会话 model、gyb 写决定账、gyb 定的和 idea 自决分不出、验收人三口径 | 第二节 actor 与 `--as-gyb`、第三节骨架与 `decisions.gyb`、第四节 gyb 豁免、第六节 actor 判定、测试 9 |
| 钩子、入账校验、纪律三层没分开 | 2 三层约束 | 拦不拦 Bash、宿主发射器三个文件、worktree 路径、run.py 注册表、快车道跑 gpu-run | 第一节裁决 5、第五节 writes 注、第七节钩子句、测试 8、规矩 8 |
| 单子没有 owner 和 holder | 3 owner 与 holder | 销号后谁拉起、打回后谁写、holder 字段、analysis_order 交付物、跑挂与 smoke 失败、reclaim 之后 | 第三节 handoffs、第四节整张表重写、第七节 6b、测试 2、4、7、12 |
| 事件账和状态账混了 | 4 事件流 | runs/sessions 无 version、run add 无 metrics、retire 无来源、add 还是 update、merge 来源、口径打回、anomaly issue 字段 | 第三节全部账带 version、runs 两版、evaluations 四态、第六节 decision 命令的来源继承、测试 3、10、14 |
| 角色 json 凭印象写 | 5 权限倒推 | idea/analysis/reviewer 的 reads 缺项、run 的 ledger_writes 漏账 | 第五节整节重写成 use case 倒推、测试 13 |
| 有进无出、等 gyb 的事散落 | 6 进出对称与收件箱 | runs 无查询、无分组键、决定反查、口径与过版没人叫 gyb、review 无回路、反常预警无落点、batch 归组、收回无通知 | 第三节 runs config、handoffs batch、第六节 run show/list、decision --with-runs、status、doctor、第八节阈值、测试 11、15 |
| 快车道只有一句话 | 7 快车道进出 | 判据、新想法被挡、worktree、ql_tag、合回补单无路、正式重跑挂哪、进出无登记 | 第二节 ql_tag、第三节 scratch、第四节新建直达一行、第六节 scratch 与 --quick-lane、doctor 扫描项、测试 4 |
| 两份文档谁为准 | 8 一处为准 | run sonnet 对 opus、fable 对全局规则、后裁输给先写 | 开头优先级句、第一节裁决 3 与 8 |

### 第二轮（2026-08-16 夜，第六轮讨论）

第二轮的原始结果在 `plans/2026-08-16-research-loop-simulation-round2.md`：十六个场景 234 条摩擦，没有经过核实者和 critic（月度用量上限），我按引用最多的条目对着两份文档自己核过每一堆。归成十一堆，前八堆是原来八条各缺一段推论、后三堆是新原则；这份施工计划改的地方如下：

| 根子 | 原则 | 归进来的问题（场景数） | 改了这份的哪里 |
|---|---|---|---|
| rl 看不见是谁敲的键盘 | 1 补推论 | quote 硬拦还是纪律两处不一（8）；gyb 本人在角色会话里被拦（6）；决定落 gyb 那本还是角色那本（4）；grants 自提自批；豁免包不包括前提栏和 runs actor（3）；sessions model 从哪来（7）；手动还是 subagent 分不出 | 第一节（b）（c）（d）、第三节骨架 force_reason、decisions 的 quote 与 gyb 文件、runs actor、grants cli、sessions launched_by 与 model；第四节表头前提对 gyb 生效；第六节 actor 判定；测试 9 |
| 读也被当权限管 | 2 补推论 | grant list 只 gyb 能调；feedback 只写不读；机器检查算进查询命令；run 上线 stale 越 reads | 第五节开头、第六节各查询行「谁都行」、测试 13 |
| holder 生命周期没有不变量 | 3 补推论 | 销号扫哪些状态两处不一（11）；done 和 stuck 不清 holder（8）；stuck→todo 两行打架（4）；withdrawn 不清 holder；双 start；owner 无活会话；gyb 手动接单没法表达；holder 指死会话 | 第二节 last_holder、dispatch；第三节 handoffs；第四节表头不变量与 resume/amend/reissue 行、start 前提；第六节 session end 改成自动 release；测试 2、7 |
| 前提放错了时机、账没有 status | 4 补推论 | 分析单和口径互为前提（5）；口径引用无版本；approved 能不能改；改单内容无路（4）；runs/sessions 无 status | 第三节每本账 status、evaluation_refs 带版本；第四节新建行放宽、done 行收紧、amend 两行；第六节 eval update 回 proposed；测试 4、14 |
| gyb 没有 use case 表 | 5 补推论 | 两条线混排、两跳认线、list 无 owner/holder 过滤、--mine 未定义、status --json 无结构、七段八段不一、doctor 无修法、reclaim 不能挑 | 第五节 gyb 表；第六节 status 十段、list 过滤、--json 结构、reclaim 参数、doctor 修法 |
| 只有 gyb 有收件箱、推送无表 | 6 补推论 | feedback 没人叫（2）；角色 issue 无推送（3）；withdrawn 通知无人关；retired 决定活单无人扫；doctor 无落点；issue close 谁打（4）；首次开给 gyb 通知两处不一；reviewer 无痕；改版不列受影响单；监控入口到不了 gyb | 第二节通知类 kind；第三节 issues 的 close 规则；第六节 inbox、notify 推送表、decision update 打印、session focus、runs tmux 与 watch_cmd；第八节 answered_stale_days |
| 快车道只有进没有出 | 7 补推论 | scratch 无关张（3）；补单自开自验；两份报告；写不写决定账；宿主台账；track 对不上 TIMELINE；worktree 在哪；标签谁分；派 gpu-runner；已开工单转快车道；analysis 无轻路 | 第二节 ql_tag 分配与 batch 语义；第三节 scratch 三态；第四节快车道行 owner gyb；第五节 deploy 与 analysis 的快车道 use case；第六节 ql open/close；第八节 worktree_root、ql_idle_days；测试 16 |
| 两份文档各说一遍 | 8 补推论 | status 段落、销号规则、通知触发、quote 规则、机器检查范围各有两句 | 开头分工句；设计文档改成指过来 |
| 账上没有链 | 9 新 | 无父单字段（12）；发射单不引决定；run_id/track/config 谁定（5）；batch 两种粒度；根决定未定义；重开单看不出接替；顺回决定要五条命令 | 第二节 parent_id、supersedes、root_id、line；第三节 handoffs 的 parent_id/line/attempts、decisions 的 root_id；第六节 trace、handoff open 继承、run add 从单子抄、list --line |
| 发射单只有一次机会 | 10 新 | 修完命令还是旧的（3）；分步表跨轮累加（3）；崩掉那次无耗时；killed 和 ok 混列（3）；失败填哪个 kind（4）；smoke 无日志文件；看门狗判死谁杀（2）；宿主账失败分支不收尾；run 上线 stale 空转 | 第二节 attempt、failed；第三节 attempts、runs 的 attempt 与 actual_seconds；第四节 amend/resume；第六节 estimate 只算最新尝试、run list 默认过滤；第七节 Phase 3、5、6a、6b |
| 同步等占住终端 | 11 新 | 三层嵌套等几小时（6）；gyb 手动会话被占；等待期间收不到收回；下游没走到 done 就返回；会话死了 GPU 还跑谁接；N 个 run 抢卡、smoke 做 N 遍 | 第一节（a）（g）；第四节 start 认领、release 不杀进程；第五节 dispatch 语义；第六节 reclaim --kill、handoff start --batch、estimate --copy-from；第七节 Phase 0、2；第九节第 9 条改题 |

第二轮模拟者数出来的手续量（未核实）在设计文档最后一节。第三轮模拟（要不要跑 gyb 定）走同样十七个场景，重点数手续量、验第一节（a）到（i）九条改动有没有引出新的打架。

### 按 part 裁决回写（统筹 session 记，一行一条）

- 2026-08-17，按 `03-ledgers.md` 的裁决（gyb：「我觉得用 b 可以 很对」，b 是不落账、查询时现算），第三节 sessions 行的 `last_activity` 那句从「rl 每次替这个会话写任何账时顺带刷新，是 sessions 账上的一版还是内存索引施工时定」改成「不落账，rl 查询时现算，取九本账里该 `session_id` 的最大 `ts`；sessions 账不为刷新它追加版本」。对回原则 4、原则 8。
- 2026-08-17，按 `03-ledgers.md` 的裁决（gyb 原话见设计文档同日那条），第三节 runs 行去掉发射版的 `artifact_dir`、补「产物目录按约定 `<artifact_root>/<run_id>/`」、`data_path` 补上定义；第六节命令表 `rl run add` 去掉 `--artifact-dir`。对回原则 8、原则 9。
