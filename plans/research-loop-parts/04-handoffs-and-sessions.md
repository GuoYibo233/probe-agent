# 派活单转移表与会话生命周期

> 这份覆盖 handoffs 这一本账的字段级行格式、七个状态、holder 不变量、六栏状态转移表全文、接单的三种 dispatch、三类单子的交付物、验收人、销号钩子做的动作、`rl status` 段 7、`rl reclaim` 的全部规矩、sessions 这一本账的行格式与 `rl session` 子命令、以及 orphaned、withdrawn、fyi 三种通知。
> 这份不覆盖：另外八本账的行格式与入账规则（见 `03-ledgers.md`）、`bin/rl` 的完整命令表和 `rl status` 其余九段与 `rl inbox`（见 `05-rl-cli.md`）、钩子拦什么和角色 json（见 `06-hooks-and-permissions.md`）、快车道本身怎么进怎么出（见 `07-quick-lane.md`）、五个角色各自在单子上干什么（见 `10-role-idea.md`、`11-role-deploy.md`、`12-role-run.md`、`13-role-analysis.md`、`14-role-reviewer.md`）、两个角色之间怎么交流（见 `20-pair-idea-deploy.md` 到 `25-pair-reviewer-idea.md`）、gyb 自己做的事（见 `01-gyb.md`）、十一条原则和裁决（见 `00-overview.md`、`02-decisions.md`）。
> 源：设计文档《research-loop 插件开发计划》的「交接与会话生命周期」一节、「账本」一节里 handoffs 和 sessions 两条、「五个角色」总段里的上线第一动作、原则 3 和原则 11；施工计划《research-loop 插件施工计划》第一节裁决（a）（b）（g）（i）、第二节词表、第三节 handoffs 和 sessions 两段、第四节整张状态转移表、第六节 `rl session` 与 `rl handoff` 与 `rl reclaim` 三行、第八节阈值里的 `status.stale_holder_minutes` 和三条 `reclaim.*`。

## 一、handoffs 这一本账的行格式

handoffs 是一本账，文件是 `loop/handoffs.jsonl`，工单、分析单、发射单三种单子共用这一本，用 `work_type` 区分。三种 `work_type` 是：工单 `work_order`（idea 开给 deploy；快车道补单是 deploy 开给 deploy）、分析单 `analysis_order`（idea 或 gyb 开给 analysis）、发射单 `launch_order`（deploy 开给 run）。

每一行先有九本账共用的公共骨架，一样不少：`id`（主键）、`version`（从 1 起，同一个 `id` 的新版本是新的一行，默认查询只取最新版）、`status`（每本账各自的取值，校验按它查）、`ts`（写入时间，ISO 8601）、`actor`（五个角色或 `gyb`）、`session_id`（写入会话，裸终端是 `cli`）、`schema_version`（整数）；可选 `fix_for`（doctor 修账时记扫描项名字）、`force_reason`（gyb `--force` 时必填）。骨架本身的规矩在 `03-ledgers.md`。

handoffs 自己的字段，一条一条抄下来：

| 字段 | 取值与必填规则 |
|---|---|
| `id` | 形如 `ho-0012` |
| `work_type` | 三选一 |
| `from_role` | 就是 owner，可以是 `gyb` |
| `to_role` | 派给谁 |
| `holder` | 当前在干的会话的 session_id |
| `last_holder` | 上一个 holder，离开 `in_progress` 时由 rl 从 `holder` 搬过来；永远不清，走到终态也留着，只是痕迹，不参与校验（2026-08-17 gyb 裁） |
| `status` | 七选一 |
| `parent_id` | `launch_order` 必填指工单，`analysis_order` 可选，快车道补单空 |
| `supersedes` | 可选 |
| `batch` | 可选 |
| `line` | 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着 |
| `dispatch` | 三选一 |
| `quick_lane` | 布尔 |
| `decision_refs` | 列表，每项 `{"id":...,"version":...}`（`work_order` 必填至少一项，`launch_order` 开单时从父单抄） |
| `evaluation_refs` | `analysis_order` 用，每项 `{"id":...,"version":...}`，开单时可以是 `proposed`，进 `done_pending_review` 时每项必须 `approved` |
| `explanation` | `work_order` 必填；快车道补单由 deploy 写并含 gyb 点名原话 |
| `report_paths` | 形如 `{"method":...,"detail":...}`（`work_order` 进 `done_pending_review` 时 `method` 必填且存在，`detail` 非快车道时必填且存在） |
| `code_paths` | 列表（`work_order` 进 `done_pending_review` 时必填） |
| `output_paths` | 形如 `{"notebook":...,"figures":[...]}`（`analysis_order` 进 `done_pending_review` 时必填且存在） |
| `attempts` | 列表只在 `launch_order` 上，每项 `{"attempt":序号,"command","args","workdir","track","config":{...},"run_id","estimated_seconds","step_table":[...]}` |
| `progress_note` | 只在 `in_progress` → `todo`（交回待干）那一版必填，写清干到哪了；`rejected` → `todo` 不要求，打回原因已经在 `reason` 里（2026-08-17 gyb 裁） |
| `reason` | `rejected`、`withdrawn` 时必填，角色会话发起的 `withdrawn` 还要 `quote` |
| `issue_id` | `stuck` 时必填 |

`attempts` 里面还有两条细规矩：开单时第一项必填 `command`、`workdir`、`track`、`config`（字典：`model`、`params`、`dataset`、`split`、其余超参自由），`run_id` 由 rl 按 `<ho-id>-a<attempt>` 分配；`step_table` 每项是 `{"step","kind":"gpu"|"cpu","smoke_seconds","scale_factor","estimated_seconds"}`，`estimated_seconds` 只加总最新一次尝试的行。一张发射单可以跑几次，每一次是单子上的一个 attempt，这条是原则 10，详细的跑法在 `12-role-run.md` 和 `21-pair-deploy-run.md`。

## 二、七个状态和 holder 不变量

七个状态，中文名和英文名一一对上：待干 `todo`、开干 `in_progress`、卡住 `stuck`、干完等待验收 `done_pending_review`、验收完成 `accepted`、打回 `rejected`、收回 `withdrawn`。`accepted` 和 `withdrawn` 是终态。

每张单子上有两个人。owner 是开单的角色，就是 `from_role`，负责单子从开到关：拉起下游、验收、收回；快车道补单和 gyb 开的单 owner 记 `gyb`。holder 是当前正在干这张单子的那一个会话，字段里存的是 session_id 不是角色名。owner 是角色不是会话，所以 owner 角色当下没有活着的会话时单子由 gyb 拉起，`rl status` 单列这一类。

holder 的不变量只有一句：holder 非空当且仅当单子在 `in_progress`。展开成两条动作：进 `in_progress` 写 holder，离开 `in_progress` 一律清空 holder 并把它记进 `last_holder`。任何离开开干的转移（交活、卡住、打回、收回、交回、回收）都清空 holder，开干只能从空 holder 进，销号只查开干的单子。这条不变量在转移表的表头写一次，表里不再逐行写。

## 三、状态转移表全文

这张表是 `tables/transitions.json` 的内容，入账脚本只认这张表，表外的转移一律拒收，退出码 2。每行六栏：从、到、谁能写、前提、之后谁拉起下游、子命令。

表头上还有三句规矩。第一句：gyb 对「谁能写」一栏一律豁免。第二句：「前提」一栏是完整性校验，对 gyb 生效，gyb 用 `--force --reason` 越过并留痕。第三句就是上一节的 holder 不变量。

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
| `done_pending_review` | `rejected` | owner | `reason` 非空；gyb 越过 owner 时 rl 给 owner 发 `fyi` | owner | `handoff reject` |
| `rejected` | `todo` | owner、`reclaim` | 无 | owner | `handoff release` |
| `rejected` | `in_progress` | `to_role` | 写入会话的角色等于 `to_role`（原会话还活着直接接着干） | 无 | `handoff start` |
| `todo` / `in_progress` / `stuck` / `done_pending_review` / `rejected` | `withdrawn` | owner | `reason` 非空（角色会话发起还要 `quote`）；有 holder 时 rl 顺带开 `withdrawn` 通知给 holder 的角色和 owner；`--cascade` 时 rl 代 owner 连 `parent_id` 指向本单的下游单一起收，下游账行 actor 记发起人 | 无 | `handoff withdraw` |
| `in_progress` | `todo` | 销号钩子、`reclaim`、owner | `progress_note` 非空（钩子和 reclaim 自动填）；`launch_order` 且最新尝试有 `launched` 未 `finished` 的 run 行时不杀进程（等下一个 run 认领），reclaim 带 `--kill` 才先走中断收尾；rl 给 owner 开 `orphaned` 通知 | owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent），owner 无活会话时进 `rl status` 的「等 gyb 拉起」 | `handoff release` |
| 任一非终态 | 同状态（接替） | owner | `--decision ID@V` 给新版本；rl 收旧单（`withdrawn`，级联）、开新单（继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单）、通知全部 holder | 同新建 | `handoff reissue` |

表尾还有一句：`stuck` 的单子销号和 reclaim 都不动（holder 已空），只有 issue `answered` 之后 `resume` 才回 `todo`。

改单子内容也是这张表里的行，不是表外的操作：`handoff amend` 出现两次，一次在 `todo` / `stuck` 上，一次在 `done_pending_review` 上，两行都写清了允许改哪几个字段、状态不变。发射单修完代码要换命令，走的就是 `todo` / `stuck` 那一行的追加一次尝试。

## 四、接单：三种 dispatch

`dispatch` 是单子上的一个字段，三个取值：`auto`（owner 后台起 subagent）、`manual`（gyb 亲自接）、`none`（暂不派）。

`auto` 是默认。上游开完单后台起 subagent 接走，上游会话继续可用，subagent 回来时上游验收；上游会话先结束了，单子照常在账上等 owner 下次上线或 gyb 验收。这就是原则 11「派活不占终端」，它取代了原来「subagent 接单默认同步」那一句。

`manual` 由开单时的 `--manual` 写进去，上游只开单，gyb 自己开 session 去接，owner 不起 subagent。`none` 由 `--no-dispatch` 写进去，单子停在 `todo` 等 gyb 说开跑。

`dispatch` 在单子交回 `todo` 之后照旧算数：能走到 release 这条路的都是外部原因（会话死了、被回收），代码没问题，owner 拉起时照原来的派法再来一次；代码或想法有问题的单子走的是 `stuck` 开 issue 那条路，修好之前回不到 `todo`（2026-08-17 gyb 裁）。

三件跟着接单一起定的事：

一是登记。subagent 加载角色 skill 那一刻和普通 session 一样登记进 sessions 账。

二是下游半路返回。下游 subagent 没走到交活或卡住就返回的（报错、上下文满），上游当场 `rl handoff release` 交回待干，然后读一眼返回的错误分两种办：外部原因（上下文满、进程被杀、终端没了）就照单子的 `dispatch` 走，`auto` 的当场再起一个 subagent 接；代码或想法有问题就不重起，开 issue 给该修的角色，单子留在 `todo`，等 issue 回了再派（2026-08-17 gyb 裁）。

三是认领。GPU 任务本体在 tmux 里跑、不跟会话走。run 会话死了单子交回待干，下一个 run 会话接单时先看最新一次尝试有没有已经发射还没收尾的 run 行，有就认领它：不重新 smoke、不重新发射，只接管看门狗和收尾，账行标 `adopted`。等几个小时的事只发生在 tmux 里，不发生在任何会话里。一次开 N 张同 batch 的发射单时只起一个 run 会话，用 `rl handoff start --batch` 一次接下整个 batch。

## 五、交付物与验收人

交付物按单子类型定，三样都是「路径存在或行存在」这种机器可查的前提，缺了不收 `done_pending_review`；开单的时候不查这些。

| 单子类型 | 交付物 |
|---|---|
| `work_order` | 两份部署报告的路径加代码路径清单 |
| `launch_order` | 数字账里退出状态为 ok 的那一版 |
| `analysis_order` | notebook 和图的路径加口径全部 approved |

验收不预写标准，验收产物是部署报告。理由是：要验的是「代码和想法是不是一回事」，这个判断在代码写出来之前写不成条目，写得成条目的（跑得通、快不快）不是要验的东西。所以 deploy 提 `done_pending_review` 必须附报告路径，路径为空入账脚本不收这个状态。

验收人是 owner。gyb 随时可以自己验：先读不带文件的那一份看做法对不对，再读带文件的那一份看写出来的东西和说的是不是一回事，打回要写明原因。gyb 越过 owner 验收或打回时 rl 给 owner 发一条 fyi 通知。快车道补单是唯一一种验收人固定的单子，只有 gyb 能 accept。

2026-08-17 gyb 裁：gyb 越过 owner 验收和打回都发 fyi，转移表 `accepted`、`rejected` 两行各写一句。（原来两份源文档不一致：设计文档写「验收或打回」都发，施工计划的转移表只在 `accepted` 那一行写了。）

## 六、会话生命周期与销号钩子

加载 skill 把角色分配给会话的那一刻算会话开始。钩子看得见这次加载，自动登记进 sessions 账，钩子代角色写，actor 填角色。

销号也由钩子自动做，挂在 SessionEnd 和 SubagentStop 上，不指望模型自觉调结束命令。gyb 也可以手动结束，可以指定别的会话。

销号那一刻程序当场检查这个会话作为 holder 有没有还挂在开干的单子，只查开干，别的状态一律放行。有开干的单子就不许悄悄下线，名下有几张开干的就交回几张，一张不留（比如 run 会话 `--batch` 接下的整批一起交回），交回的编号全部记进 sessions 账 `released_handoffs`（2026-08-17 gyb 裁）。钩子调的销号对每一张做四件事：

1. 把单子交回待干（走转移表 `in_progress` → `todo` 那一行）。
2. 写进度说明，内容是「会话销号，holder 是 X」。
3. 给 owner 发 orphaned 通知。
4. experiments/ 里的脏改动打一个 `wip/<ho-id>` 分支，分支名记进说明。

钩子漏掉的会话有两道兜底。第一道是 `rl status` 段 7：holder 会话超过 `status.stale_holder_minutes` 没写任何账的开干单，默认 30 分钟，先在 gyb 的收件箱里露头，gyb 或 owner 当场 release。第二道是 `rl reclaim`，见下面第八节。

## 七、sessions 这一本账与 `rl session` 子命令

sessions 记的是：哪个会话、什么角色、什么模型、怎么起的、几点开始、最后一次写账几点、几点销号，两版（开始版、结束版）。行格式：

| 字段 | 取值与必填规则 |
|---|---|
| `session_id` | 主键 |
| `role` | 五个角色之一 |
| `model` | 钩子从钩子输入的 JSON 里取，取不到记 `unknown` |
| `launched_by` | 取 `manual`、`subagent`、`workflow` |
| `rules_version` | 会话开始时的母版版本 |
| `status` | 取 `open`、`closed` |
| `started_at` | `open` 版必填 |
| `last_activity` | 不落账，rl 查询时现算，取九本账里该 `session_id` 的最大 `ts`（含 sessions 账自己的行）；sessions 账不为刷新它追加版本；对外语义仍是「最后一次写账时间」 |
| `focus` | 可选，reviewer 在审的决定编号 |
| `ended_at` | `closed` 版必填 |
| `end_reason` | `closed` 版必填，取 `hook`、`manual`、`reclaim` |
| `released_handoffs` | `closed` 版必填，销号时交回待干的单子列表 |

开始版由钩子代角色写，actor 填角色。

`rl session` 的五个子命令：

- `rl session start --role R [--model M] [--launched-by manual|subagent|workflow]`：登记，钩子调。
- `rl session end [--session ID] [--reason]`：销号，钩子调。`end` 只扫 `in_progress` 且 holder 是本会话的单子，有就全部 release 交回 `todo`、自动填 `progress_note`、给 owner 开 `orphaned`、experiments/ 脏改动打 `wip/<ho-id>` 分支；`--session ID` 给 gyb 关别的会话。gyb 用 `--session ID` 关别的会话时 rl 不拦、不查那个会话活没活着（rl 看不见进程，只看得见账），照样销号，`end_reason` 记 `manual`；那个会话要是其实还活着、之后又来写账，rl 看到它的 session 已经 `closed` 就拒收，提示「会话已被销号，重新加载角色登记」（2026-08-17 gyb 裁）。
- `rl session focus --decision ID`：reviewer 开工时记一下在审什么，`rl status` 的活着会话那一段带出来。
- `rl session show ID`。
- `rl session list [--alive] [--role R]`。

谁能调：start 和 end 是钩子和 gyb，focus 是 reviewer，查询谁都行。

母版版本这条链跟 sessions 有关：母版带一个 `rules_version`，会话开始版记下它，feedback 采纳的时候 rl 列出还活着的会话让 gyb 挑要不要收；母版改动在下次加载角色时生效，正在跑的会话不追、不通知，按现行母版干到底。反馈账本身在 `09-common-and-feedback.md`。

## 八、`rl reclaim` 的全部规矩

`rl reclaim` 是兜底，由 gyb 定期手动跑，定时提醒每 `notify.reminder_days`（默认 7）天叫他一次。谁能调：gyb。

命令形状：`rl reclaim [--session-older-than H] [--handoff-older-than H] [--only ID ...] [--skip ID ...] [--kill] [--apply]`。

三个阈值默认值：

| 键 | 默认值 | 用在哪 |
|---|---|---|
| `reclaim.session_idle_hours` | 48 | 会话超过 48 小时没写任何账算很久没动 |
| `reclaim.handoff_idle_hours` | 72 | 单子超过 72 小时没转移算很久没动 |
| `reclaim.ql_idle_days` | 7 | 快车道超过 7 天没关列进 reclaim |

不带 `--apply` 就只列出超过阈值没动的会话、单子和快车道，不动手。带 `--apply` 才动手，按单子状态分四种处置：

- 会话：标 `reclaim` 销号，并 release 名下开干的单。
- 开干的发射单：默认不杀进程，留给下一个 run 认领；`--kill` 才走中断收尾，也就是杀进程、释放显存、宿主销号、runs 落 killed。
- 卡住的单子：只把 issue 改派 owner，状态保持卡住。
- 等验收和待干的单子：只列出，附现成命令，不动手。

跑完还有两件事：结束时按 owner 分组打印待拉起的单子和加载命令，并自动跑一遍 doctor。

2026-08-17 gyb 裁：reclaim 回收开干的发射单默认不杀进程，`--kill` 才走中断收尾。（原来两份源文档不一致：设计文档说「先走中断收尾再交回待干」，施工计划的转移表和 reclaim 行说默认不杀。）同一段的第二处也是 2026-08-17 gyb 裁：reclaim 对卡住的单子只把 issue 改派给 owner，状态保持卡住，不提 holder，因为按第二节的不变量卡住的单子 holder 早已清空。（原来设计文档写「只清 holder 状态保持卡住并把 issue 改派给 owner」，是不变量定死之前的写法。）

## 九、三种通知：orphaned、withdrawn、fyi

这三种是 issues 账里的通知类 `kind`，不是问题，开出来只为了让人知道一件事。它们的字段规矩在 `03-ledgers.md`，这里只写触发点和收件人。

| kind | 什么时候开 | 开给谁 | 内容 |
|---|---|---|---|
| `withdrawn` | 收回一张有 holder 的单子时 | holder 的角色和 owner | 你手上的单子被收回了 |
| `orphaned` | holder 会话死了、单子被交回待干时（销号钩子、reclaim、owner release 都算） | owner | holder 会话死了单子交回了 |
| `fyi` | gyb 越过 owner 处理了单子时 | owner | gyb 越过 owner 处理了你的单子 |

三种都进对应角色的 `rl inbox`，被 `rl inbox` 读过即关。`withdrawn` 和 `orphaned` 的 issue 行里 `handoff_id` 必填。

角色上线第一个动作是 `rl inbox`，它列四类东西，其中两类和这份直接相关：owner 是本角色而没有 holder 的单子、发给本角色的通知。inbox 的完整内容在 `05-rl-cli.md`。

## 和别的 part 的接口

按 HANDOFF 四点五节的关联表，先列本份是定义处的东西（别处只引用、不重抄），再列本份引用别处定义的东西。

本份是定义处的：

- handoffs 账的全部字段（第一节字段表，含 `parent_id`、`supersedes`、`batch`、`line`、`dispatch`、`quick_lane`、`decision_refs`、`evaluation_refs`、`explanation`、`report_paths`、`code_paths`、`output_paths`、`attempts`、`progress_note`、`reason`、`issue_id`、`holder`、`last_holder`）；`03-ledgers.md` 的 handoffs 一段只留一句指过来。`10-role-idea.md`、`11-role-deploy.md`、`20-pair-idea-deploy.md` 等把这些字段指到 `03` 的，同步时改成指本份。
- 七个状态、holder 不变量（第二节）、`tables/transitions.json` 全表（第三节）、三种 dispatch（第四节）、三类单子的交付物与验收人（第五节）、销号钩子做的四件事（第六节）、`rl reclaim` 的处置（第八节）、三种通知的触发点与收件人（第九节）。`20`、`21`、`22` 三份角色对 part 各抄了转移表里自己那条通道的几行，判断规矩 2：改一处必改另一处，本份 2026-08-17 改的 `in_progress` → `todo`、`done_pending_review` → `rejected` 两行已列进「要同步到别处的」。
- sessions 账的行格式（第七节字段表）和 `03-ledgers.md` 的 sessions 一段是同一张表写了两遍（HANDOFF 判断规矩 2），两边要一字不差；rl-hub 2026-08-17 来信按 `03` 是定义处处理，本份照 `03` 的裁决改。`rl session` 五条子命令的判据（第七节）由本份定，签名在 `05-rl-cli.md`。

本份引用别处定义的：

- 公共骨架七样字段（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）加可选的 `fix_for`、`force_reason`，退出码：定义在 `03-ledgers.md`。
- issues 账的九种 `kind`、三个 `status`（`open`、`answered`、`closed`）、`handoff_id` 和 `reply` 的必填规则：定义在 `03-ledgers.md`（`09-common-and-feedback.md` 抄了一遍）；本份只用 `withdrawn`、`orphaned`、`fyi` 三种和 `answered` 这一个状态。
- runs 账的 `status`（`launched`、`finished`）和 `exit_status`（`ok`、`failed`、`killed`）：定义在 `03-ledgers.md`；转移表的 `done` 行和认领判据都靠它。
- evaluations 的四个状态（`proposed`、`approved`、`rejected`、`retired`）：定义在 `03-ledgers.md`；转移表 `analysis_order` 的开单和交活两行都引它。
- 决定账的 `root_id`、`{"id","version"}` 引用格式、`--decision ID@V`：定义在 `02-decisions.md`（原文指 `03`，按 HANDOFF 四点五节改指 `02`）；handoffs 的 `line` 字段从 `root_id` 算出来，`reissue` 那一行用 `ID@V`。
- `bin/rl` 每条子命令的签名与「谁能调」、`loop/.lock` 一把全局锁、`rl status` 的十段全文、`rl inbox` 的四类、`rl trace`、`rl doctor` 的扫描项和修法：写在 `05-rl-cli.md`；本份只写 `rl handoff`、`rl session`、`rl reclaim` 三组子命令背后的判据和 status 段 7 的内容。
- 阈值 `status.stale_holder_minutes`（默认 30）、`reclaim.session_idle_hours`（48）、`reclaim.handoff_idle_hours`（72）、`reclaim.ql_idle_days`（7）、`notify.reminder_days`（7）：阈值表定义在 `08-trees-init-and-host.md`（原文指「`05` 指到的施工计划第八节」，按 HANDOFF 四点五节改指 `08`）。
- gyb 豁免「谁能调」和转移表「谁能写」、完整性前提照查、`--force --reason` 留痕、`--as-gyb` 加 `--quote`、actor 按会话判：定义在 `01-gyb.md` 第二节（2026-08-17 gyb 裁）；命令行参数写法在 `05-rl-cli.md`；钩子那一层在 `06-hooks-and-permissions.md`。
- 销号钩子挂在 SessionEnd 和 SubagentStop 上、登记钩子从钩子输入取 model、会话状态文件：钩子本体写在 `06-hooks-and-permissions.md`。
- 快车道补单的两行（新建直达 `done_pending_review`、只有 gyb 能 accept）、`ql_tag`、scratch 账的 `merged` 状态：快车道进出在 `07-quick-lane.md`，scratch 行格式在 `03-ledgers.md`。
- `attempts` 里的 `step_table`、`estimated_seconds` 怎么填、认领之后 run 怎么接管看门狗和收尾、`--kill` 走的中断收尾四步：写在 `12-role-run.md` 和 `21-pair-deploy-run.md`。
- 部署报告分 `method` 和 `detail` 两份、`code_paths` 谁填：写在 `11-role-deploy.md` 和 `20-pair-idea-deploy.md`。
- `output_paths` 和口径要 approved 才交活：写在 `13-role-analysis.md` 和 `22-pair-idea-analysis.md`。
- 母版 `rules_version`、feedback 采纳时列活会话让 gyb 挑：写在 `09-common-and-feedback.md`。
- 测试 2（转移表与 holder）、测试 4（交付物）、测试 7（销号）、测试 11（status 与 reclaim）、测试 15（收回与接替）：写在 `30-build-steps-verify-tests.md`。
- 待验证第 5 条（SessionEnd 和 SubagentStop 在 subagent 上触不触发）、第 8 条（subagent 里加载角色 skill 钩子装不装得上）、第 9 条（后台 subagent 能不能跑几个小时、父会话结束会不会被杀）、第 10 条（钩子输入里有没有模型标识）：写在 `30-build-steps-verify-tests.md`；这四条不成立会改掉本份第四、六、七节的写法。

## 源文档没写清的（留给 gyb）

（2026-08-17 全部裁完，见文末「裁决记录」。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，保留场景名、序号、严重度、kind、原文、依据、改法，一个字没改，也没做任何判断。那份文件开头写着：这些摩擦全部是未经核实的模拟者原话，可能有误报。

### param-tweak（45 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 42 步：设计文档说销号只查「还挂在开干的单子」，施工计划说 end 时扫 holder 是本会话的单子、有就拒绝，没有状态过滤；而转移表里 in_progress→done_pending_review 那一行不清 holder（测试 2 只要求 start 写、stuck→todo/rejected/release/reclaim 清），于是 run 交完活就销不了号，用 --release 又会把已交活的单子打回 todo
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:204
   - 改法：转移表 in_progress→done_pending_review 那一行加「holder 清空」，并把 build-plan:126 的扫描限定成 in_progress 和 stuck 两种状态
2. [blocks/missing] 第 26、28、29 步：handoffs 的字段表里没有父单字段，但三处规矩都要它：「那张发射单挂在这张工单上」、doctor 扫「快车道工单已验收但没有关联发射单」、withdraw --cascade「连它派生的下游单一起收」，三处都无从实现
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：handoffs 加一个可选 parent_id 字段，open 时可填，doctor 和 cascade 都按它查

### new-idea（39 步，gyb 动手 7 次）

2. [blocks/contradiction] 第 31 步和第 34 步：设计文档说销号时只检查「作为 holder 还挂在开干的单子」，施工计划的 rl session end 写的是「扫 holder 是本会话的单子，有就拒绝」，不分状态；run 和 deploy 提完 done_pending_review 时 holder 没被清空（清空只发生在 stuck→todo、rejected、release、reclaim），按施工计划这两个 subagent 都销不了号，而验收人正在同步等它们返回，两头卡死
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:204; plans/2026-08-16-research-loop-build-plan.md:209
   - 改法：施工计划第 126 行改成「只拦 in_progress 和 stuck 的单子」，并在转移表里给 in_progress→done_pending_review 也写上 holder 清空
3. [blocks/missing] 第 18 步：handoffs 的字段表里没有父单字段，发射单 ho-0002 挂不到工单 ho-0001 上；可是 withdraw --cascade 要「连它派生的下游单一起收」、doctor 要扫「快车道工单已 accepted 但没有关联发射单」、decision --with-runs 要顺着 handoffs 从决定反查到 run，这三处都依赖这层父子关系
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：handoffs 加 parent_id 字段，rl handoff open 加 --parent ID，launch_order 和快车道补单必填
4. [blocks/too_heavy] 第 10 步和第 19 步：接单默认是同步的，deploy 等 run 几个小时、idea 又等 deploy，于是 gyb 手动加载的 idea 会话从派单那一刻起被整场实验占住，gyb 想看进度只能另开终端；待验证第 9 条的失败备案只写了 deploy→run 这一层改成开单即销号，idea→deploy 这一层没有备案
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：明写 gyb 手动加载的角色会话一律不同步等下游，开完单即返回，验收由下一次会话或 gyb 在 rl status 里做
10. [slows/ambiguous] 第 33 步：设计文档说 deploy 验收完发射单「再拿数字接着干工单」，但没写这一步具体产出什么：工单的交付物只有两份部署报告，而报告在开发射单之前就写完了，数字进不进报告没写，于是既可以读成「什么都不用做直接 done」，也可以读成「要把 run_id 和指标补回报告」
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:118; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：明写「发射单验收后 deploy 把 run_id 和关键指标补进 detail 报告，再提 done_pending_review」

### result-wrong-review（25 步，gyb 动手 11 次）

1. [blocks/missing] 第 3 步和第 4 步：handoffs 没有指向上游单子的字段，发射单的 decision_refs 又不是必填（只有 work_order 必填），所以从一个不对的 run_id 顺不回工单、更顺不回决定：runs.handoff_id 指的是发射单，发射单上既没有 parent 也可以没有 decision_refs，`rl handoff list --decision` 只出工单，`rl decision show --with-runs` 声称「顺着 handoffs 反查跑出的 run」这条链在工单到发射单这一跳断掉。同一个缺口让 `withdraw --cascade` 的「派生的下游单」和 doctor 的「快车道工单已 accepted 但没有关联发射单」都没有判断依据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个必填的 parent_id（发射单指它所属的工单、快车道正式重跑的发射单指那张快车道工单），--cascade、doctor 和反查全按它走。
7. [slows/missing] 第 11 步：reviewer 读顺序第一段要「先读最终的代码」，但没写要审的代码清单从哪来；工单上只有 report_paths 没有代码路径，而 deploy 改到 experiments/ 外的宿主文件（run.py 注册表、MAP.md、ops/）只列在 detail 报告里，读顺序又把 detail 排在最后，先读代码那一遍必然漏掉宿主文件的改动。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：工单加一个 code_paths 字段由 deploy 提验收时填，或明写 reviewer 第一段可以先读 detail 报告里的文件清单那一节、不读它的结论。

### plot-new-plan（17 步，gyb 动手 8 次）

4. [slows/contradiction] 第 17 步（结束会话）：设计文档说销号时检查这个会话作为 holder 有没有还挂在「开干」的单子，施工计划说 end 时扫 holder 是本会话的单子、有就拒绝，没限状态；转移表里 in_progress 到 done_pending_review 那一行又没写清空 holder，于是单子停在等验收时 gyb 想先关掉会话去看图会被拒绝下线。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：在转移表 in_progress→done_pending_review 那一行加「holder 清空」，并把销号检查明确限定在 in_progress 和 stuck 两个状态。
10. [slows/ambiguous] 第 10 步（分析单的 from_role）：owner 被定义成开单角色也就是 from_role，而角色只有五个、gyb 不在角色表里；设计文档和词表都说 gyb 可以开分析单，但 handoffs 的 from_role 能不能填 gyb、gyb 算不算合法 owner 没有明写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:41; plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：在第三节 handoffs 的 from_role 字段写清取值是五个角色或 gyb，并说明 owner 是 gyb 时验收和拉起下游都由 gyb 做。
12. [cosmetic/missing] 第 13 步到第 14 步（图画完之后叫 gyb）：单子进 done_pending_review 只出现在 rl status 里，桌面通知只在 issue 改派给 gyb 的时候发；gyb 不坐在这个会话里的时候，得靠自己轮询才知道图画好了。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：把「等 gyb 验收的单子」也接进 rl notify，或者在设计文档里明写这一类只进 rl status、不通知。

### next-plan-after-results（36 步，gyb 动手 16 次）

1. [blocks/contradiction] 第 20 步：销号时 holder 扫描的范围两处打架：设计文档说只查「还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子」不限状态；同时转移表的 done_pending_review 和 accepted 两行都没写清空 holder，所以一张已验收的分析单会永远把 holder 挂在这个会话上，而逃生口 `--release` 只允许从 in_progress/stuck 走，analysis 会话按字面走关不掉
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:88; 2026-08-16-research-loop-build-plan.md:93
   - 改法：转移表在 done_pending_review、accepted、withdrawn 三行明写 holder 清空，`rl session end` 只扫 in_progress 和 stuck
3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行
9. [slows/missing] 第 27 步：`--cascade` 收回下游单子的写入人是上游单的 owner（idea），可发射单的 owner 是 deploy，转移表 withdrawn 那一行「谁能写」只写了 owner，没给级联收回开口子
   - 依据：2026-08-16-research-loop-build-plan.md:92; 2026-08-16-research-loop-next-steps.md:124
   - 改法：转移表 withdrawn 那一行加一句「级联收回时上游单的 owner 可写下游单」，账行记清是级联触发的
10. [slows/ambiguous] 第 31 步：开完工单要不要立刻起 deploy subagent。设计文档说默认上游开完单直接起 subagent 同步等它回来，本场景 gyb 只想定计划不想现在开跑，文档没有「开单但暂不派」的默认，gyb 不当场喊停就会被带进几小时的实施
   - 依据：2026-08-16-research-loop-next-steps.md:120; 2026-08-16-research-loop-next-steps.md:48
   - 改法：`rl handoff open` 加 `--no-dispatch`，SKILL.md 写明 gyb 没说开跑就停在 todo

### run-crash-midway（40 步，gyb 动手 4 次）

3. [blocks/contradiction] 第 13 步：销号时扫什么单子，两份文档打架。next-steps.md:126 写「检查这个会话作为 holder 有没有还挂在开干的单子」（只管 in_progress），build-plan.md:126 写「扫 holder 是本会话的单子，有就拒绝并列出」（不限状态）。ho-0013 标 stuck 之后 holder 仍是 sess-run-01（转移表 build-plan.md:84 那一行不清 holder），按施工计划这版销号会被拒绝，而调 `rl session end` 的是钩子不是模型，钩子不会自己去选 `--release` 还是 `--stuck`，链条停在这里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：build-plan.md:126 改成「扫 holder 是本会话且状态为 in_progress 的单子」，并在转移表 in_progress→stuck 那一行注明 holder 保留还是清空。
4. [slows/missing] 第 19 步：转移表 build-plan.md:85 的 stuck→todo（谁能写=回了 issue 的那个角色，前提=关联 issue 已 answered）在 bin/rl 命令表 build-plan.md:134 里没有对应子命令，只能借 `release`；而 release 在转移表 build-plan.md:93 那一行的谁能写是「销号钩子、reclaim、owner」、前提只有「holder 清空」，借它就绕开了「issue 必须已回」这个前提。本场景 deploy 恰好既是 owner 又是回 issue 的人才糊得过去，工单场景（owner 是 idea、holder 是 deploy、回 issue 的是 idea）同样糊得过去但语义已经错位。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：给这一行加一个专门的子命令 `rl handoff resume ID`，前提校验关联 issue 是 answered。
5. [blocks/blocked] 第 24 步：deploy 修完代码之后，发射单 ho-0013 的 launch.command 和 args 还是崩之前那一版，命令表 build-plan.md:134 里没有任何改 launch 子对象的子命令，账又是只增不改（next-steps.md:92）。三条路都不通：带着旧命令跑（跑的和账上写的不一样）、开一张新发射单（旧单子只能 withdraw，转移表里 stuck 走不到重开）、手改账（钩子和入账校验都禁止）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl handoff relaunch ID --command ... --workdir ...`：给发射单追加一版新的 launch 子对象并把状态带回 todo。
10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。
14. [slows/ambiguous] 第 13 步：sessions 账的 open_handoffs_at_end 字段说明是「结束时 holder 还是这个会话的单子列表，正常应为空」（build-plan.md:71），但发射单标 stuck 之后 holder 不清空，run 会话销号时这个字段必然非空。到底是「非空就是异常要拦」还是「非空只是记一笔」，文档没说，两种读法分别对应销号被拒和销号放行。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：把这个字段的说明改成「结束时状态还是 in_progress 的单子列表，非空即拒绝销号」，stuck 的单子不算。
16. [cosmetic/contradiction] 第 23 步：卡住的单子被回复之后谁能接，两处说法不一样。next-steps.md:116 写「卡住的 issue 被回复之后单子回待干，谁接都行」，转移表 build-plan.md:83 的 todo→in_progress 那一行前提写死「写入会话的角色等于 to_role」。按正文任何角色都能接，按表只有 run 能接。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:116; plans/2026-08-16-research-loop-build-plan.md:83
   - 改法：把 next-steps.md:116 的「谁接都行」改成「to_role 的任何一个会话都能接」，与转移表对齐。

### n-launch-orders（58 步，gyb 动手 10 次）

3. [blocks/principle_violation] 第 14 步：违反原则 3（每张派活单有 owner 和 holder，holder 是当前正在干这张单子的那一个会话）。转移表 todo→in_progress 那一行的前提只有「写入会话的角色等于 to_role」，没有「holder 为空」这一条，所以两个 run subagent 先后 start 同一张单是合法转移，后一个直接覆盖前一个的 holder，另一张单没人接却在账上看不出来。
   - 依据：2026-08-16-research-loop-build-plan.md:83; 2026-08-16-research-loop-next-steps.md:17
   - 改法：转移表 todo→in_progress 的前提加一句「holder 为空」，已有 holder 时退出码 2 并把当前 holder 列出来。
7. [blocks/contradiction] 第 25、42 步：销号时查 holder 的范围两份文档写得不一样：设计文档说「检查这个会话作为 holder 有没有还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子，有就拒绝并列出」。转移表里 done_pending_review 和 stuck 两个状态都不清 holder，所以按施工计划的读法，4 个跑完的 run subagent 和写完报告的 deploy 会话全都退不出去；按设计文档的读法才能销号。测试清单第 7 条只覆盖了 in_progress 这一种。
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:209
   - 改法：施工计划第六节改成「只拦 status 为 in_progress 且 holder 是本会话的单子」，done_pending_review 和 stuck 一律放行销号。
8. [slows/contradiction] 第 25 步：转移表里 stuck→todo 有两行且前提打架：一行要求「关联 issue 状态是 answered」，另一行允许销号钩子和 reclaim 只清 holder 就把 stuck 降回 todo。run5 一销号，ho-0017 就在 issue 还没被 deploy 回复的情况下变回 todo，owner 按规矩可以立刻再起一个 run，代码没改照样再挂一次。
   - 依据：2026-08-16-research-loop-build-plan.md:85; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:117
   - 改法：销号钩子和 reclaim 对 stuck 单只清 holder、状态留在 stuck，只有 issue 转 answered 之后才允许回 todo。
13. [slows/missing] 第 26 步：待验证第 9 条（上游 subagent 同步等几小时会不会被超时收掉）的备案正好落在这个场景上，但备案没给续跑规矩：一旦 deploy 开完单就销号，ho-0012 会被销号钩子交回 todo、报告还没写、5 张发射单已经派出去，下一个 deploy 会话重新 start 之后怎么知道进度到哪、去哪找那个 batch，文档没写。
   - 依据：2026-08-16-research-loop-build-plan.md:197; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:120
   - 改法：备案里补一句：work_order 也记 batch，重新 start 时第一件事是 rl handoff list --batch 复原五张单的状态。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

1. [blocks/missing] 第 7、10 步：handoffs 行格式（build-plan.md:61）里没有任何父子字段：launch_order 不记它挂在哪张 work_order 上，重开的单子也不记它接的是哪张旧单。可是 next-steps.md:124 的 `--cascade` 要「连它派生的下游单子一起收」、next-steps.md:80 说 analysis 能「从决定顺到发射单再顺到 run_id」、build-plan.md:144 的 doctor 要扫「快车道工单已 accepted 但没有关联发射单」——三处都要这条链，账里没有这个字段。本场景 idea 打了 --cascade，rl 走不到 ho-0013，正在烧卡的那张发射单收不掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 `parent_handoff` 字段，开发射单和分析单时必填，cascade、doctor、链式查询都走它。
3. [blocks/contradiction] 第 15 步：build-plan.md:164（Phase 6b）写「`rl run finish --exit failed|killed`，发射单标 `stuck` 并开 issue 给 deploy；被收回时也走这里」，而转移表 build-plan.md:92 只允许各状态转到 `withdrawn`，build-plan.md:95 又写「`accepted` 和 `withdrawn` 是终态，表外的转移一律拒收，退出码 2」。run 按 SKILL.md 走到这一步必然吃退出码 2。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：第七节 6b 拆成两句：跑挂走 stuck，被收回只做 `rl run finish --exit killed` 加收尾，不再动单子状态。
4. [blocks/blocked] 第 16、18 步：转移表转到 `withdrawn` 那一行（build-plan.md:92）的前提栏写「无」，没有像 rejected 和 release 两行那样写「holder 清空」。销号时 `rl session end` 要扫 holder 是本会话的单子，有就拒绝（build-plan.md:126、next-steps.md:126），逃生口 `--release` 是把单子交回 `todo`，可是 `withdrawn` 到 `todo` 在表里不存在。结果 run 会话和 deploy 会话都销不了号，只能等 `rl reclaim`。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-next-steps.md:126
   - 改法：转到 `withdrawn` 的那一行前提栏补「holder 清空」，并明写 session end 只检查未到终态的单子。
5. [slows/contradiction] 第 10、11 步：转移表「谁能写」栏（build-plan.md:92）规定收回只有 owner 能写，而 next-steps.md:124 的 `--cascade` 要求 owner 一条命令连下游单一起收，下游单的 owner 是另一个角色（本场景 idea 收 deploy 的发射单）。两句同时成立就等于 owner 能越过另一个 owner 写单子。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：明写 cascade 是 rl 代 owner 连锁收回、被收的下游单 actor 记发起人并自动给下游 owner 开一条 issue，或者干脆只允许 gyb 用 --cascade。
10. [slows/missing] 第 10 步：公共规矩第 1 条（build-plan.md:245）要求不可逆动作要有 gyb 当场的原话，收回是终态、不可逆，可是 `rl handoff withdraw ID [--cascade]`（build-plan.md:134）没有 `--quote` 参数，handoffs 行格式（build-plan.md:61）也没有 quote 字段，gyb 那句「停」没有落点。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：withdraw 和 reject 都加 `--quote`，handoffs 行加 quote 字段，角色会话发起时缺 quote 就报错。
11. [slows/missing] 第 17 步：接单默认是同步的，上游会话等下游 subagent 回来（next-steps.md:120、next-steps.md:17）。等待期间上游会话没有任何中断通道，rl 给它开的 `kind=withdrawn` issue 要等下游返回才看得见。本场景 deploy 从工单被收回到 run 返回的那几个小时里对收回完全无反应，还在等一张已经作废的发射单。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：收回一张有 holder 的单子时，同时给它的下游单子发同一条收回信号，让下游的看门狗把上游一起唤醒；或者明写等待期间的收回一律由 gyb 直接收到最底层那张单。
12. [slows/missing] 第 19 步：转到 `withdrawn` 那一行的「之后谁拉起」栏写「无」（build-plan.md:92），收回只给 holder 的角色开 issue，不给 owner 任何东西。S-idea1 从同步等待里醒来，发现自己开的 ho-0012 已经被收回，下一步该干什么文档没写，它是接着开新单还是销号只能自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：收回时给 owner 角色也开一条 issue（kind 复用 withdrawn），转移表第五栏写明 owner 醒来后要么重开单要么销号。
13. [slows/missing] 第 20 步：rl 自动开的 `kind=withdrawn` issue 的 assignee 是角色不是会话（build-plan.md:59），run 的 subagent 收到信号后就结束了，这条 issue 没人回也没人关。doctor 的扫描项里只有「没人引用的 issue」（build-plan.md:144），这条带着 handoff_id 所以扫不出来，会一直挂在 `rl status` 的 open 列表里。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：withdraw 自动开的 issue 直接落成 `closed`（它是通知不是问题），或者 doctor 加一条「holder 已销号但 withdrawn issue 仍 open」的扫描并附 close 命令。
16. [slows/too_heavy] 第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。
17. [cosmetic/missing] 第 21 步：重开的 ho-0014 和被收回的 ho-0012 之间没有任何字段能看出是同一件事的第二次派发（handoffs 行格式 build-plan.md:61 里没有 supersedes 之类的栏），`rl status` 和 `rl handoff list --decision` 都只会把它们并排列成两张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：handoff open 加 `--supersedes ho-XXXX`，写进单子并在 status 里归成一组。
18. [cosmetic/missing] 第 13、18 步：单子被收回之后，experiments/ 里 deploy 已经写下的代码和产物根里那半截产物目录怎么处置，两份文档都没写。快车道有明确的进出规矩（next-steps.md:64 的 worktree 和合回），正常路收回之后没有对应的一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：转移表转到 `withdrawn` 那一行的前提栏补一句：holder 在返回前把半截产物路径写进那条 withdrawn issue，处置由 gyb 定。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

1. [blocks/contradiction] 第 20 步和第 27 步：销号时扫什么单子两处写法不一样：设计文档说「检查这个会话作为 holder 有没有还挂在开干的单子」（只管 in_progress），施工计划说「扫 holder 是本会话的单子，有就拒绝并列出」（不限状态）。而转移表里 in_progress→done_pending_review 和 done_pending_review→accepted 两行都没有清 holder 这一步（测试 2 只要求 stuck→todo、rejected、release、reclaim 时清），所以按施工计划那句读，run subagent 和 gyb 的 deploy 会话都会在销号时被拒；钩子跑在会话结束那一刻，没法交互补 --release。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:204; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：施工计划第 126 行改成「只扫 status 是 in_progress 或 stuck 的单子」，并在转移表 in_progress→done_pending_review 那一行补上「holder 清空」。
2. [blocks/missing] 第 1 步：没有任何办法表达「这张单 gyb 手动接，别起 subagent」：rl handoff open 没有这个旗子，handoffs 行里没有这个字段，idea 的默认动作是开完单直接起 deploy subagent 并同步等。gyb 的口头交代不进账，idea 会话一旦重开或被 reclaim，idea 还会按 owner 职责再拉起一个下游，两个会话抢着打 rl handoff start，晚的那个撞上「表外转移一律拒收」拿退出码 2。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:83; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：给 handoffs 加一个 dispatch 字段（auto / manual），rl handoff open 带 --manual 时 owner 不起 subagent、rl status 单列这类单子。
9. [slows/too_heavy] 第 12 步到第 21 步：gyb 手动的 deploy 会话按默认要同步等 run subagent 跑完才能接着干，实验跑几个小时 gyb 的交互终端就被占几个小时；而「上游 subagent 同步等下游几个小时会不会被超时收掉」还挂在待验证第 9 条上没有结论，备案是「长任务改成 deploy 开单即销号」，两种走法对 gyb 手动会话的体验差别很大。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：对 gyb 手动加载的角色会话默认走异步：开完发射单就把工单 release 回 todo，等 run 完了 rl status 提醒 gyb 再接。
10. [slows/principle_violation] 第 3 步：违反原则 1（谁在打命令和会话装了什么角色是两回事，账行如实记 actor 和会话两样）。这条链上第 5 到第 23 步全部由 gyb 本人驱动，可 sessions 账只有 role 和 model 两栏、handoffs 只有 holder 一栏、每条账行的 actor 只能填角色名，事后没有任何字段能分出「这张单是 gyb 亲手干的」还是「subagent 干的」；reviewer 要查也查不到。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-next-steps.md:120
   - 改法：sessions 账加一栏 launched_by（manual / subagent / workflow），钩子登记时按有没有父会话填。
11. [slows/missing] 第 26 步：gyb 越过 owner 直接验收之后，没有任何通道把这件事告诉 owner idea。转移表 done_pending_review→accepted 那一行第五栏是「无」，issues 账只在改派给 gyb 时发通知，rl status 是给 gyb 的收件箱不是给角色的。idea 会话下次上线只会看到单子已经是终态，不知道是谁验的、为什么验过。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：gyb 代 owner 写终态转移时，rl 自动给 owner 角色开一条 kind=not_mine 之外的新 kind（比如 fyi）的 issue，或者在角色上线时和 decision stale 一起报一句「你名下的单子被 gyb 处理过」。

### two-idea-lines-parallel（26 步，gyb 动手 20 次）

7. [slows/contradiction] 第 12 步：转移表里 stuck→todo 有两行都能匹配，两套「谁能写」：一行写「回了 issue 的那个角色」、前提是关联 issue 已 answered；另一行是 in_progress/stuck→todo，写的人是销号钩子、reclaim、owner 的 release，前提只有 holder 清空。文档同时说入账脚本只认这张表、表外一律拒收，撞到两行按哪一行校验没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:95; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：把第 93 行那一行的「从」缩成只有 in_progress，stuck 的出口只留第 85 行并把销号钩子和 reclaim 并进那一行的「谁能写」。
8. [blocks/missing] 第 13 步：owner 是角色不是会话，owner 角色没有活着的会话时谁把它叫醒没写。原则 3 和交接一节四处都写「回到待干、由 owner 重新拉起下游」，本场景蒸馏线的 deploy 会话已销号，账上只剩一张 todo 单子和一个不存在的 owner。按原则 1 只能推出 gyb 有权自己干，推不出系统怎么提醒他该开哪个角色的会话。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：rl status 单列一段「等 gyb 拉起」：owner 角色没有活会话的 todo 单子，每行附上该开哪个角色会话的那条命令。
9. [cosmetic/contradiction] 第 14 步：手动加载的会话在 sessions 账里 model 记什么，两处打架：sessions 行格式写「真实模型标识，手动加载也记真实的，不记 inherit」，角色 json 那一栏写「model 分 as_subagent 和 manual，manual 一律 inherit」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：角色 json 那一栏加半句「manual 写 inherit 是声明跟当前会话走，sessions 账落解析后的真实模型名」，两句各自限定清楚。

### feedback-round（15 步，gyb 动手 9 次）

5. [slows/missing] 第 12 步（正在跑的 analysis 会话和 idea 会话怎么办）：母版改了以后，正在跑的会话按旧规矩产出的东西算不算数（要不要打回、收回、重做）没写；账上也没有任何地方记得住某个会话是在哪一版母版下跑的：sessions 账只有 session_id、role、model、started_at、ended_at、end_reason、open_handoffs_at_end 七样，母版文件本身也没有版本号
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：母版文件加一个 rules_version，sessions 开始版记下它，accept 时 rl 顺带列出还活着的会话和它们的 rules_version 让 gyb 挑要不要收

### idea-request-notes（15 步，gyb 动手 4 次）

5. [slows/missing] 第 6 步之后到第 8 步之间：idea 开完 --to gyb 的 request issue 之后，等回话期间会话该干什么没写。idea 手上没有派活单，转移表里的 stuck 只有 holder 能写、对 idea 不适用；gyb 要是走开了，idea 会话要么空转要么销号，而销号之后没有任何机制重新拉起 idea——原则 3 只管有 owner 的单子，idea 是最上游、只由 gyb 在终端手动 / 加载
   - 依据：plans/2026-08-16-research-loop-build-plan.md:84; plans/2026-08-16-research-loop-next-steps.md:117; plans/2026-08-16-research-loop-next-steps.md:154
   - 改法：idea 的 SKILL.md 纪律栏写死：开完 --to gyb 的 issue 立即把待办交回 gyb 并结束本轮，gyb 下次开 idea 会话时用 `rl issue list --to gyb` 捡起来接着走

### periodic-reclaim（27 步，gyb 动手 11 次）

1. [blocks/missing] 第 6、7 步：reclaim 只有 --older-than 和 --apply 两个开关，没有逐条挑选或排除的办法。一个跑三天的 run 会话中间不写账，48 小时的会话阈值必然把它算成很久没动，gyb 想留下它只能整体调大 --older-than，代价是其他该收的也收不了。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178
   - 改法：reclaim 加 --only ID... 和 --skip ID...，并且默认跳过 launch_order 对应进程还活着的会话。
2. [blocks/missing] 第 8、11、22 步：reclaim 把 launch_order 从 in_progress 改成 todo 之后，GPU 进程照跑、显存不释放、宿主 ops/jobs.json 的号不销。看门狗每轮采样只查本单是不是 withdrawn，改成 todo 它不认，不会走中断流程；owner 这时再起一个 run 接同一张单，同一份实验会被发射两次。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:70; plans/2026-08-16-research-loop-build-plan.md:162; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：reclaim 对 launch_order 先走 gpu-run 的中断收尾（rl run finish --exit killed、释放显存、销号）再交回 todo，看门狗把 reclaim 和 withdrawn 一起当中断信号。
3. [slows/contradiction] 第 8、9 步：施工计划第六节写 reclaim 是「会话标 reclaim 销号，单子交回 todo、holder 清空」，同一节又写 session end 时扫到 holder 是本会话的单子就拒绝。按前一句的顺序做，reclaim 的第一步就被自己的入账校验拒收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：把 reclaim 那一格改写成「先把名下单子交回 todo、holder 清空，再销号」，两步放同一把锁里。
4. [slows/ambiguous] 第 5、8、11 步：会话阈值 48 小时比单子阈值 72 小时短，两个方向都出问题：会话被销号而它名下的单子还没超 72 小时（销号要不要连带 release 这张单，两种读法都说得通）；单子超 72 小时被拉回 todo 而 holder 会话还活着在干（没有任何东西通知它停）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:178; plans/2026-08-16-research-loop-build-plan.md:179; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：销号一律连带 release 名下全部单子（不看单子阈值），回收还活着的 holder 的单子时照 withdraw 的办法开一条 issue 给 holder 的角色。
5. [slows/contradiction] 第 10 步：转移表里 stuck → todo 有两行：一行前提是关联 issue 状态为 answered，另一行（reclaim 走的这行）前提只要 holder 清空。reclaim 按后一行把还在等回答的单子放回待干，下一个接单的人接到一张实际还卡着的单，那条 open issue 也没人再管。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：reclaim 对 stuck 单子只清 holder、状态保持 stuck，同时把关联 issue 改派给 owner。
6. [slows/missing] 第 11、27 步：reclaim 列出的单子里，done_pending_review 和 todo 这两类在转移表里没有 reclaim 能写的行，--apply 之后原样不动，文档也没说这两类被列出来之后 gyb 该干什么。挂了 100 小时没人验收的单子就这么继续挂着。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:88
   - 改法：reclaim 的输出把这两类单独分一段，明写不自动动，每条附一条现成的 accept / reject / withdraw 命令。
7. [slows/too_heavy] 第 12、15 步：回收之后没有任何东西通知 owner，也没有 owner 的收件箱（rl status 是 gyb 的）。owner 是角色不是会话，原来的会话已经被销号，gyb 得亲手为每个 owner 角色开一个终端加载 skill，单子分属几个 owner 就开几个。文档开头写这套东西服务的是想法要快速多次迭代，这一步和它拧着。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：reclaim --apply 结束时按 owner 分组打印每张单子和一条现成的加载命令，rl status 里加「按角色分的待接单」一段。
8. [slows/ambiguous] 第 15 步：rl handoff list 的 --mine 没定义是按 owner 过滤还是按 holder 过滤。owner 找回被回收的单子正是要按 owner 过滤，按 holder 过滤会一条都查不到。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:41
   - 改法：拆成 --owner 和 --holder 两个开关，--mine 删掉。
9. [blocks/missing] 第 18、19 步：半成品代码没有落点。handoffs 的字段表里 report_paths 只有提 done_pending_review 时才填，in_progress → todo 那一版里没有任何字段记着上一个会话写到哪、动了哪些文件、下一个人该接着改还是推倒重来。接手的 deploy 只能自己去 experiments/ 里翻代码猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-next-steps.md:56
   - 改法：给 in_progress → todo 这一行加一个必填的 progress_note，reclaim 自动填「reclaim 于 X，工作目录 experiments/<handoff_id>」，接手方先读它。
10. [slows/missing] 第 19 步：被回收会话在 experiments/ 里留下的未提交改动没人管。文档只在 run 的 Phase 4 写了发射前 commit，deploy 半途被回收的脏工作树既没有要求提交，也没有要求记 git status，下一个会话看到的是一堆来路不明的改动。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：reclaim 时对 experiments/ 的脏改动自动打一个 wip/<handoff_id> 分支，分支名写进 progress_note。
13. [slows/missing] 第 26 步：doctor 的八个扫描项里没有 reclaim 会造出来的两种脏账：单子已经回到 todo 而关联 issue 还是 open，以及 runs 有发射版长期没有收尾版。这两种正是回收留下的残渣，扫不出来就没人修。文档也没写 reclaim 之后要不要跑 doctor。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：doctor 加这两项扫描，reclaim --apply 结束时自动跑一遍 doctor 并打印结果。
14. [slows/missing] 第 13 步：钩子调 rl session start 时那一行的 actor 填什么没写。公共骨架规定 actor 取值是五个角色或 gyb，钩子两样都不是。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：明写钩子代角色写账，sessions 开始版的 actor 填 --role 那个角色，session_id 填新会话。

### hook-missed-session-end（23 步，gyb 动手 11 次）

1. [slows/too_heavy] 步 2、步 5：文档指名「钩子漏掉的」走 rl reclaim（设计 L126），但 reclaim 的默认阈值是会话 48 小时、单子 72 小时（施工 L178、L179），提醒周期 7 天（施工 L183）。会话死掉 6 小时的时候，文档给的唯一恢复路一条都不触发，这张工单最坏要躺 7 天才有人碰，和设计 L7「想法要快速、多次迭代」打架。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-build-plan.md:178; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加一段「holder 会话超过 N 分钟没写任何账的 in_progress 单」，N 默认 30 分钟，和 reclaim 的 48/72 小时分开。
2. [blocks/contradiction] 步 20：施工 L126 写 rl session end「扫 holder 是本会话的单子，有就拒绝并列出」，测试 7（施工 L209）写的是「holder 名下有 in_progress 单子时拒绝」。转移表 in_progress→done_pending_review 那一行（施工 L87）不清空 holder，测试 2（施工 L204）列的清空时机也不含 done_pending_review。按 L126 字面，正常交完活的 deploy subagent 销号会被拒收，钩子拿不到合法的下一步（--release 会把已交活的单子打回 todo），会话照样结束，sessions 账再留一行没有结束版的死会话，本场景的 bug 自我复制一遍。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:209; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:204
   - 改法：L126 改成「扫 holder 是本会话且状态是 in_progress 或 stuck 的单子」，并在转移表那一行写明 holder 保留到 accepted 或 rejected。
3. [slows/missing] 步 2：rl status 的「活着的会话」（施工 L142）只能按 sessions 账有没有结束版判定，钩子漏销号的死会话被列成活着。sessions 行（施工 L71）没有 last_activity 之类的字段，reclaim 的口径「会话超过 48 小时没写任何账」（施工 L178）要跨九本账扫 session_id，怎么算没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:178
   - 改法：sessions 账加 last_activity 字段，rl 每次写任何账顺带刷新，status 和 reclaim 都读它。
4. [slows/principle_violation] 步 3：违反原则 6（设计 L20、L94「能 add 就有 show 和 list」）。命令表（施工 L126）里 sessions 只有 start 和 end，九本账里唯独它没有 show 和 list。gyb 从 rl status 拿到 holder 的 session_id，查不出它是哪个角色、什么时候开的、最后一次写账是什么时候。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:94; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：命令表补 rl session show ID 和 rl session list [--alive] [--role R]，谁都能调。
5. [slows/missing] 步 7：设计 L32 和 L126 两处写「gyb 也可以手动结束会话」，但命令表里 rl session end [--reason]（施工 L126）没有指定会话的参数，只能结束当前会话。gyb 结不掉那个已经死掉的 sess-deploy-3，只能等 reclaim 到 48 小时。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:32; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：rl session end 加 --session ID，「谁能调」那一栏保持钩子和 gyb。
6. [slows/guessed] 步 13、步 14：设计 L120 只写「上游开完单直接起一个 subagent 接走并同步等它回来」，没写下游 subagent 没走到 done 或 stuck 就返回的时候上游拿到什么、该做什么。待验证第 9 条（设计 L168、施工 L197）只问「等几个小时会不会被超时收掉」，不问「等的对象死了怎么办」。最快能发现这件事的就是被阻塞的上游会话，文档没给它任何职责，我只能按原则 3 推它该 release 加重起。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：设计 L120 补一句「下游 subagent 没走到 done 或 stuck 就返回的，上游当场 rl handoff release 并决定重起还是开 issue 给 gyb」，并写进 idea 和 deploy 的 SKILL.md。
7. [slows/ambiguous] 步 5、步 6：把单子从 in_progress 拉回 todo 有三个写入者（施工 L93：销号钩子、reclaim、owner 的 release），设计 L126 又单独指名钩子漏掉的走 reclaim，文档没说这一情形该走哪条，两种读法都说得通。rl reclaim [--older-than H]（施工 L143）只有一个 H，第八节却有会话和单子两个阈值（施工 L178、L179），H 盖哪个也没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:143; plans/2026-08-16-research-loop-next-steps.md:126
   - 改法：设计 L126 改成「钩子漏掉的：owner 或 gyb 当场 release，超阈值没人管的由 reclaim 兜底」，--older-than 拆成 --session-older-than 和 --handoff-older-than。
8. [slows/missing] 步 12、步 16：单子交回 todo 之后重派，死掉的 deploy 在 experiments/ 里留下的半成品代码没人负责交代或清理。handoffs 的字段（施工 L61）没有工作记录一栏，交付物只有两份部署报告（设计 L118），单子上看不出这张单干过两遍，新 deploy 是接着干还是推倒重来没有依据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:118; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：转移表 in_progress→todo 那一行加一个必填的 note 字段，写清上一手干到哪、产物在哪。
9. [slows/missing] 步 6、步 22：整个恢复过程在九本账上不留痕，违反原则 4 的事件流本意（设计 L18）。release 那一版只记 status 和 holder 清空；issue 的六种 kind（施工 L45）没有一种对得上「你的 holder 会话死了、单子被交回」；reclaim 关掉死会话时 open_handoffs_at_end（施工 L71）已经是空的，因为单子先被 release 了。事后谁都看不出钩子漏过一次。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:18; plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：issue 的 kind 加一种 orphaned，release 和 reclaim 交回单子时自动开一条给 owner，把当时的 holder 会话 id 写进去。
10. [slows/missing] 步 23：rl doctor 的八项扫描（施工 L144）没有一项覆盖本场景：既没有「sessions 账里没有结束版但超过阈值没写账的会话」，也没有「in_progress 单子的 holder 不在活着的会话里」。恢复完 doctor 报零，钩子漏销号永远不进 doctor 的视野。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加这两项扫描，修法分别给 rl handoff release 和 rl session end --session ID。
11. [slows/missing] 步 4：rl handoff list 的过滤器（施工 L136）只有 --status、--mine、--batch、--decision，没有按 holder 会话过滤的口子。死掉的 deploy 名下除了这张工单，还可能有它当 owner 开出去的发射单，gyb 只能全量列 in_progress 肉眼比对。--mine 在 actor 是 gyb 的时候指什么也没定义。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:41
   - 改法：handoff list 加 --holder SESSION 和 --owner ROLE，并写明 actor 是 gyb 时 --mine 等于全部。
12. [slows/missing] 步 8、步 10：单子回到 todo 之后由 owner 重新拉起（设计 L17、施工 L93 第五栏），但 owner 是角色不是常驻进程。没有活着的 idea 会话的时候，这张 todo 单子只能等 gyb 下次看 rl status 才有人碰；谁在什么时候把 owner 叫起来，文档没写。本场景里重派全靠 gyb 口头说一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 的单子那段单列一行「todo 且 owner 角色当前没有活着的会话」的单子，并进桌面通知。

### smoke-fails（44 步，gyb 动手 4 次）

1. [blocks/contradiction] 步 22 与步 39（run subagent 两次销号）：销号时要检查的单子范围两份文档不一样：设计文档写「检查这个会话作为 holder 有没有还挂在**开干**的单子」，施工计划写「end 时扫 **holder 是本会话的单子**，有就拒绝并列出」。smoke 失败后这张发射单在 stuck，正常收尾后在 done_pending_review，两次 holder 都还是本会话（转移表 in_progress→stuck、in_progress→done_pending_review 两行都没写清空 holder）。按施工计划的读法，SubagentStop 钩子调的 rl session end 每次都被拒收（退出码 2），而钩子是自动触发的、没法回头补 --release 或 --stuck，结果 sessions 账永远缺结束版、holder 死钉在一个已经不存在的会话上，只能等 48 小时 reclaim。这同时是原则 8 的漏网：两份文档留了两个值，没有回来改掉其中一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:84; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：把销号检查钉死成「只对 in_progress 拒绝」，stuck 和 done_pending_review 放行并在 end 里顺手清空 holder，两份文档同步改成同一句。
2. [slows/contradiction] 步 20 到步 22（run 标卡住之后怎么收场）：转移表有一行 stuck→in_progress，谁能写是 holder，前提是「关联 issue 状态是 answered，holder 会话还活着」。可是接单默认是同步 subagent：deploy 起 run 之后一直等 run 返回。run 要想等到 issue 被回复，就得挂在那儿不返回，而回复它的 deploy 正卡在等 run 返回上，两边互等；run 要是返回，会话就结束，holder 会话不再活着。所以这一行在默认接单模式下永远走不到，smoke 失败只能走「销号—回 issue—回 todo—重起 subagent」的重路。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:86; plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：明写 stuck→in_progress 只给 gyb 手动接的会话用，subagent 接的单子一律以返回上游结束；或者给发射单开一条「同一个 deploy 会话就地修完直接再起 run」的短路并写进转移表。
3. [slows/missing] 步 27（deploy 回完 issue 把发射单拉回 todo）：转移表 stuck→todo 那一行的「谁能写」是「回了 issue 的那个角色」，可是 bin/rl 命令表里 handoff 的子命令只有 start/stuck/done/accept/reject/withdraw/release，没有一条对应这次转移；release 在转移表另一行里写的是 owner 专用。这次 deploy 恰好既是回 issue 的人又是 owner，用 release 蒙混过去了，换成 gyb 之外的非 owner 角色回 issue 就没有命令可打。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：加一条 rl handoff resume ID（前提是关联 issue 已 answered），并在转移表每一行后面补上对应的子命令名。
4. [slows/contradiction] 步 22（销号钩子的逃生口）与步 26 到 27：设计文档说「卡住的 issue 被回复之后单子回待干」，转移表 stuck→todo 的前提也是「关联 issue 状态是 answered」；但转移表最后一行允许销号钩子和 reclaim 把 stuck 直接推回 todo，前提只有「holder 清空」，施工计划的 session end 逃生口 --release 走的正是这条。走这条的话，ImportError 的 issue 还没被回复，单子就回了 todo，owner 一拉起下一个 run subagent 就再撞同一个 ImportError，白烧一轮探卡加 smoke。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:116; plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：销号和 reclaim 对 stuck 单一律保持 stuck 只清 holder，不推回 todo；只有关联 issue 变 answered 才允许进 todo。
13. [slows/missing] 步 26 到 27（deploy 修完代码）：修 import 有时候要换入口（比如从 python -m pkg.train 换成 python scripts/train.py）或者加环境变量，发射单上写死的 launch.command 就得跟着改。九本账全是事件流、改等于追加一版，可是转移表里没有「改单内容」这一行，命令表里也没有对应的子命令，deploy 只能收回旧单重开一张新单，把 stuck 的 issue 关联关系一起丢掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:18
   - 改法：加 rl handoff amend ID --command ... --workdir ...，只许在 todo 或 stuck 上追加一版，并在转移表里补一行原地追加。

### doctor-findings-fix（24 步，gyb 动手 15 次）

6. [slows/too_heavy] 第 9 到 19 步（修第二类）：第二类的真实病因只是一份报告文件没了，修它却要走「打回 → 加载 deploy 会话 → decision stale → start → 重写报告 → done → accept」七步，中间还要新登记一个会话、还要把单子在四个状态之间转一圈。对着「想法要快速、多次迭代」这条目标偏重。
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:91; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:88
   - 改法：给 done_pending_review 的单子加一条 `rl handoff amend ID --report-detail P`：追加一版只换路径、不改状态、校验路径存在。
7. [slows/missing] 第 8、18 步（holder 指向死会话）：转移表和测试 2 列的 holder 清空时机是 start 写、stuck→todo / rejected / release / reclaim 清，唯独 in_progress→done_pending_review 不清；销号钩子又只检查 holder 名下还在 in_progress 的单子。于是等验收的单子上 holder 长期写着一个已经销号的会话，rl status 那一栏显示有人在干，实际没有。
   - 依据：2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:204; 2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-next-steps.md:124
   - 改法：在转移表 in_progress→done_pending_review 那一行补一句 holder 清空，或者 rl status 显示 holder 时标出这个会话还活着没有。
13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。

## 裁决记录（日期）

- 2026-08-17 来自 `03-ledgers.md` 的裁决（rl-hub 转来）：`last_activity` 不落账，rl 查 `rl session show` / `rl status` / `rl reclaim` 时扫九本账取该 `session_id` 的最大 `ts`（含 sessions 账自己的行）；sessions 账不为刷时间戳追加版本。gyb 原话「我觉得用 b 可以 很对」。对回原则 4、原则 8。本份第七节字段表照改，「没写清」原第 6 条销掉。
- 2026-08-17 gyb 裁：打回（`rejected`）之后 release 回 `todo` 不要求 `progress_note`，打回原因已在 `reason` 里；`progress_note` 只在 `in_progress` → `todo` 那一版必填。gyb 原话「不用」。对回原则 4（一个字段必不必填看这一版的状态）。字段表 `progress_note` 那一行照改，「没写清」原第 1 条销掉。
- 2026-08-17 gyb 裁：会话销号时名下所有开干的单子全部交回待干，一张不留，编号全记进 `released_handoffs`。gyb 原话「全部」。对回原则 3（holder 是当前正在干的会话，会话没了就没人在干）。第六节照改，「没写清」原第 2 条销掉。
- 2026-08-17 gyb 裁：单子交回 `todo` 后 `dispatch` 照旧算数，能不能再干取决于原因：外部原因（会话死、被回收、进程被杀）照 `auto` 再起一个 subagent；代码有问题的先修，走 `stuck` 开 issue，下游半路报错返回时上游读错误分这两种办。gyb 原话「我想这个问题应该取决于再干能不能成功吧，如果是啥外部元素，重试能成功那可以再来，但是如果代码有问题得给代码先修了啊」。对回原则 11（派活不占终端）和原则 3（owner 负责拉起）。第四节两处、转移表 release 行「之后谁拉起」栏照改，「没写清」原第 3 条销掉。
- 2026-08-17 gyb 裁：`last_holder` 永远不清，终态也留着。gyb 原话「留着吧」。对回原则 4（账是事件流，痕迹只增不删）。字段表 `last_holder` 那一行照改，「没写清」原第 4 条销掉。
- 2026-08-17 gyb 裁：`rl session end --session ID` 关别的会话时 rl 不拦、照样销号；被误关的会话再写账时 rl 拒收并提示重新登记。gyb 原话「a」。对回原则 1（rl 只认会话，不认手指；gyb 是超级用户）。第七节 `rl session end` 那一条照改，「没写清」原第 5 条销掉。
- 2026-08-17 gyb 裁：转移表 `in_progress` → `todo` 那一行「谁能写」栏里单列的 gyb 删掉，gyb 靠表头豁免，跟别的行一个写法。gyb 原话「删了吧」。对回原则 8（可枚举的东西只写一遍）。「没写清」原第 7 条销掉。
- 2026-08-17 gyb 裁：gyb 越过 owner 打回（`reject`）也给 owner 发 fyi，和验收通过一样。gyb 原话「可以 发」。对回原则 6（送进「等某人」状态的那一行必须出现在那个人的收件箱里）。转移表 `rejected` 行和第五节的不一致标注照改，「没写清」原第 8 条销掉。
- 2026-08-17 gyb 裁：`rl reclaim --apply` 回收开干的发射单默认不杀 GPU 进程，留给下一个 run 认领，`--kill` 才杀。gyb 原话「不杀」。对回原则 11（GPU 任务本体在 tmux 里跑、不跟会话走）。第八节不一致第一处照改。
- 2026-08-17 gyb 裁：reclaim 对卡住的单子只改派 issue 给 owner、状态保持卡住，不提 holder（按不变量已空）。gyb 原话「按照施工计划吧」。对回原则 3（holder 非空当且仅当开干）。第八节不一致第二处照改。
- 2026-08-17 来自 sync-inbox 问题 1 的裁决（rl-hub 转来）：actor 判定、`--as-gyb` 加 `--quote`、`--force --reason` 这一组规矩定义处归 `01-gyb.md` 第二节；`05` 的「actor 怎么定」是命令行写法，算写了两遍、每次同步对齐；`06` 只留钩子对 `--as-gyb` 不生效那一句。gyb 原话「这个归01吧」。对回原则 8（文档只有一处为准）。接口一节那条照改。

## 要同步到别处的

- `20-pair-idea-deploy.md` 第 26 行「`progress_note`（进 `todo` 且不是新建时必填）」改成「`progress_note`（只在 `in_progress` → `todo` 那一版必填；`rejected` → `todo` 不要求）」。来源：本份 2026-08-17 裁决。——已同步 2026-08-17（rl-hub，`75ed02f`）。
- `20-pair-idea-deploy.md` 第 58 行、`21-pair-deploy-run.md` 第 134 行、`22-pair-idea-analysis.md` 第 79 行抄的转移表 `in_progress` → `todo` 那一行，「谁能写」栏删掉单列的 gyb（改成「销号钩子、`reclaim`、owner」），「之后谁拉起」栏「owner，owner 无活会话时进 `rl status` 的「等 gyb 拉起」」改成「owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent），owner 无活会话时进 `rl status` 的「等 gyb 拉起」」。来源：本份 2026-08-17 裁决。——已同步 2026-08-17（rl-hub，`75ed02f`）。
- 新增一条入账校验：`session_id` 对应的 sessions 账最新版是 `closed` 的会话再写任何账，rl 拒收并提示重新加载角色登记。这条是本份 2026-08-17 裁决带出来的，定义处按 HANDOFF 判断规矩 3 找不到（入账校验在 `03-ledgers.md`，命令在 `05-rl-cli.md`），请 rl-hub 问 gyb 归哪一份。——已立为 `sync-inbox.md` 第一段问题 5，等 gyb 2026-08-17。
- `01-gyb.md` 第 148 行「按裁决以施工计划的表为准」（fyi 只在 accept 发）改成「2026-08-17 gyb 裁：验收和打回都发 fyi」；`20-pair-idea-deploy.md`、`21-pair-deploy-run.md`、`22-pair-idea-analysis.md` 抄的转移表 `done_pending_review` → `rejected` 那一行，前提栏「`reason` 非空」后面加「；gyb 越过 owner 时 rl 给 owner 发 `fyi`」。来源：本份 2026-08-17 裁决。——已同步 2026-08-17（rl-hub，`75ed02f`）。
- `01-gyb.md` 第 45 行、`05-rl-cli.md` 第 170 行标的「reclaim 对开干发射单杀不杀进程」不一致，gyb 2026-08-17 在本份裁了：默认不杀、`--kill` 才杀，两处的「按裁决以施工计划的表为准」改成「2026-08-17 gyb 裁：默认不杀，`--kill` 才杀」。来源：本份裁决。——已同步 2026-08-17（rl-hub：`01` 在 `75ed02f`；`05` 第 170 行交 rl-part-05 改）。
