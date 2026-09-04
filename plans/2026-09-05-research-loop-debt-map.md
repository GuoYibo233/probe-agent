# 2026-09-05 research-loop 欠账到代码落点的对照单：冻结三份的九笔欠账各落在 v2 插件树的哪个文件

来历：03、04、05 三份分册从 2026-08-17 起冻结，之后的九笔改动只记在 `plans/research-loop-parts/sync-inbox.md`（问题 34、35、37、39、40、41、43、45、47），等最后一期合并进正文。今天写代码要抄的是新口径，所以这张单把每笔欠账的每个子项写清四样：新口径（sync-inbox 原句）、原冻结句（现文行号加原句）、代码落点（v2 插件树里的文件）、状态（settled 是已裁，pending 是还没裁、代码里按 `PENDING(...)` 标记）。冻结正文一个字不动，最后一期合并现行版的时候拿这张单逐笔核对。

做法：九路 opus 读手各读一笔欠账并逐字抄录，九路 fable 核手逐条对原文核对引文、行号、落点，统筹汇成本文件。核手改过的条目在备注里写明。

## 一、九笔欠账的总表

| 问题 | 子项数 | 其中 pending | 落到哪些文件 |
|---|---|---|---|
| 34 | 5 | 0 | `research-loop/bin/rl`、`research-loop/common/GLOSSARY.md`、`research-loop/schemas/decisions.schema.json`、`research-loop/scripts/rl_lib.py`、`research-loop/tables/ledgers.json`、`research-loop/tests/` |
| 35 | 7 | 0 | `research-loop/bin/rl`、`research-loop/hooks/`、`research-loop/scripts/rl_lib.py`、`research-loop/skills/<role>/SKILL.md`、`research-loop/tables/ledgers.json`、`research-loop/tables/roles/<role>.json`、`research-loop/tests/` |
| 37 | 8 | 4 | `research-loop/bin/rl`、`research-loop/common/GLOBAL-RULES.md`、`research-loop/common/REVIEW-CHECKLIST.md`、`research-loop/schemas/decisions.schema.json`、`research-loop/schemas/feedback.schema.json`、`research-loop/schemas/sessions.schema.json`、`research-loop/scripts/rl_lib.py`、`research-loop/tables/ledgers.json`、`research-loop/tests/` |
| 39 | 7 | 0（(a2) 由 D-15 代裁） | `research-loop/agents/<role>.md`、`research-loop/bin/rl`、`research-loop/hooks/`、`research-loop/schemas/sessions.schema.json`、`research-loop/scripts/rl_lib.py`、`research-loop/skills/<role>/SKILL.md`、`research-loop/skills/research-loop/SKILL.md`、`research-loop/tables/config_defaults.json`、`research-loop/tables/ledgers.json`、`research-loop/tables/transitions.json`、`research-loop/tests/` |
| 40 | 7 | 0 | `research-loop/bin/rl`、`research-loop/scripts/rl_lib.py`、`research-loop/tables/gyb-usecases.json` |
| 41 | 13 | 1 | `research-loop/bin/rl`、`research-loop/common/GLOBAL-RULES.md`、`research-loop/schemas/scratch.schema.json`、`research-loop/scripts/rl_lib.py`、`research-loop/skills/deploy/SKILL.md`、`research-loop/tables/commands.json`、`research-loop/tables/transitions.json`、`research-loop/tests/` |
| 43 | 7 | 1 | `research-loop/bin/rl`、`research-loop/schemas/handoffs.schema.json`、`research-loop/scripts/rl_lib.py`、`research-loop/tables/ledgers.json`、`research-loop/tables/transitions.json`、`research-loop/tests/` |
| 45 | 4 | 0 | `research-loop/bin/rl`、`research-loop/schemas/handoffs.schema.json`、`research-loop/scripts/rl_lib.py`、`research-loop/skills/analysis/SKILL.md`、`research-loop/skills/deploy/SKILL.md`、`research-loop/skills/run/SKILL.md`、`research-loop/tables/commands.json`、`research-loop/tables/transitions.json`、`research-loop/tests/` |
| 47 | 6 | 0 | `research-loop/bin/rl`、`research-loop/hooks/`、`research-loop/scripts/rl_lib.py`、`research-loop/tables/roles/analysis.json`、`research-loop/tables/roles/reviewer.json`、`research-loop/tests/` |

子项共 64 条，其中 pending 6 条（读手汇总时是 7 条，39(a2) 随后由 D-15 代裁）。

## 二、按落点文件反查：写这个文件的时候要看哪些子项

- `research-loop/agents/<role>.md`：39(a1)（五份角色 agent 定义就是「插件的角色 agent 类型」本体（08 L90、06 L126：「派活一律用这五个类型起 subagent，钩子输入的 `agent_type` 就是这么来的」）；`dispatch=auto` 起 subagent 时 subagent_type 取这五个文件名，agent 定义预加载本角色 skill、收窄工具面、不写钩子）
- `research-loop/bin/rl`：34(a)（子命令 `rl decision add`：用法与帮助写「前缀按会话定（角色会话用角色前缀，`--as-gyb` 也一样；裸终端用 `gyb`），序号在本前缀内自动分配，落前缀那本」，不写「落 actor 自己那本」（02 L109））；34(b)（子命令 `rl decision update`、`rl decision confirm`、`rl decision stale`（以及 `rl status` 段 6、`rl inbox` 的过版一项按同一判据算））；34(c)（子命令 `rl decision show --with-runs`（同一行的 `rl decision list [--actor A] [--line L]` 不受这条影响））；34(e)（子命令 `rl decision add` / `update` / `confirm` 的 `--as-gyb --quote` 这条路径：quote 必填，actor 记 gyb，落哪本按前缀）；35(a)（doctor 子命令：扫描项表末尾加第 20 项「陈旧会话状态文件」（loop/.sessions/ 下的状态文件，对应 sessions 账最新版是 closed，或者超过一天没动），修法是删文件，「修完之后归谁推」栏填 gyb；doctor 项数由十九变二十。「超过一天」在代码里硬编码 24 小时并标 PENDING(part 08 L57)，08 第三节阈值表没有对应的键）；35(g)（doctor 扫描项的编号规矩：问题 43(a) 删掉的第 16 项留空号、后面的项不重排，(a) 新加的项接末尾编成第 20 项；引用按项号写的地方（05 第 237 行的 doctor 第 16 项、01 第 156 行的 doctor 第 19 项、30 第 225 行的十九项）不跟着漂）；37(a)（子命令 `decision retire`：签名从 `rl decision retire ID [--source ...]` 改成带必填理由项，按 `update` 类推写成 `--text`；缺 `--text` 拒收）；37(b)（子命令 `feedback accept`：四件事之一改成「自动把 `rules_version` 加一并写回 `common/GLOBAL-RULES.md` 头部那一行」（定义处 09 L87））；37(d)（子命令 `doctor`：末段说明与输出里的「问题清单写成一份文件放 `common/`」写成文件名 `common/REVIEW-CHECKLIST.md`）；37(f)（子命令 `feedback add`（`--target` 的取值校验与提示）和 `feedback reject`（写完提示再提要开新一条））；37(g1)（子命令 `session start`：`rules_version` 不做参数、由 rl 读母版（05 L40 签名里没有这个参数））；39(b1)（`init` 子命令：重跑时已填过的项不再问、已建的不重建（无副作用，08 L36「重跑 init 时已经填过的项不再问」）；配置逐项问（08 L17、L40 表「init 问」栏）；只在研究仓库里建树，不动宿主代码和仓库 `.claude/`（08 L13））；39(b2)（`run finish` 子命令与 `reclaim --kill` 的中断收尾：四步（杀进程、释放显存、宿主销号、runs 落 `killed`）里「宿主销号」那一步调 `launcher.abort_cmd`，键留空就跳过这一步、不报错）；39(b3)（`doctor` 第 18 项：宿主 runs 账的路径不写死 `ops/runs.jsonl`，从配置 `host_ledgers` 里找 `kind` 是 `runs` 的那一项）；39(b4)（`init` 逐项问这三个键（08 第二节表里三项「init 问」栏都标 ✓））；39(c)（`init` 不问账路径（08 第二节 L40：「各账路径」2026-08-18 gyb 裁掉））；40(a)（不写 rl notify（命令表里的 `rl notify --text` 签名行和「rl notify」一节整删，插件的子命令集合里没有 notify））；40(b)（rl reclaim 没有任何定时提醒机制，只由 gyb 手动跑；rl status 第一行打印距上次 reclaim 几天是留下的唯一机制（05 L93 已是这么写））；40(c)（issue 的 assignee 是 gyb 的那一版（含首次开单）不发任何通知，只进 rl status 段 2；其余进角色的 rl inbox）；40(d)（rl issue open / rl issue reassign 的 `--to gyb`（开单或改派）不触发通知，那一版进 rl status 段 2）；40(e)（init 的默认配置不含 notify.reminder_days（rl init 写的 research-loop.json 阈值键里没有这一项））；40(f)（init 的默认配置不含 notify.reminder_days（rl init 写的 research-loop.json 阈值键里没有这一项））；41(c1)（子命令 `rl ql open --from ho-ID`：给那张待干工单追加一版标 quick_lane 并让它离开待干队列）；41(c2)（转进单出口那一步的子命令（名字未定，见 (f3)））；41(f1)（子命令 `rl ql close`：`--merged` 和 `--dropped` 两条路关张时都删掉 worktree 和同名分支）；41(f2)（子命令 `rl ql open --from ho-ID`：除了标 quick_lane，还要让单子离开待干队列（不再派人接、不占 holder））；41(f3)（转进单（`--from` 进来的单）出口那一步的子命令名，名字未定；落地前 bin/rl 里这一步标 PENDING(issue 41f)）；41(h)（`rl status`：段 9 里没关的快车道不进 line 分组，`--group-by line` 时单独列一堆）；43(a)（doctor subcommand: scan item 16 (decision source points at notes/ but grants has no read:notes for that actor) is not implemented; item number 16 is left unused, items are not renumbered, and item 20 from issue 35(a) is appended at the end (sync-inbox L195 (g))）；43(a2)（init subcommand: no 'ask once whether to issue read:notes to idea' prompt; init builds research-loop.json, loop/ with the ledgers, experiments/, analysis/ (with analysis/scratch/), review/, notes/, appends the CLAUDE.md section, and still refuses in a role session with exit code 3）；43(b)（status subcommand: with --group-by line, a handoff whose decision_refs span several root decisions is printed under every related line, not only under the first one; --line L filtering matches on the same rule）；45(a)（`handoff open` 子命令：`--track` 对 `work_order` 收方向名写进顶层栏；对 `launch_order` 不写顶层栏，从父单顶层 `track` 抄进第一次尝试）；45(b)（`handoff withdraw`：从 `in_progress` 收回时 rl 顺带开的那条 `withdrawn` 通知（04 L74、L194，收件人是 holder 的角色和 owner）的正文带这一句，提醒 holder 把已写的代码位置和半截产物目录路径回进这条 issue、东西不动、处置由 gyb 定。只是提示不是校验：05 L65 的 `withdraw ID --reason [--quote] [--cascade]` 是 owner 调的命令，holder 回没回 rl 查不了，所以不加前提、不加退出码）；47(b)（`rl session end`（含 `--session ID`）：release 交回全部走在前，sessions closed 版（带 released_handoffs）落最后一步）
- `research-loop/common/GLOBAL-RULES.md`：37(b)（头部一行带 `rules_version`（整数），格式要能被 rl 定位并原地加一）；37(g1)（头部那一行是唯一真源，会话开始版从这里读）；41(g)（公共规矩是九条（含 rule-09「凡修的东西是账上报过的 issue，修完必须回复并关掉，不许静默修」），头部带 rules_version）
- `research-loop/common/GLOSSARY.md`：34(d)（词表 `decisions` 那一行（现文第 25 行写「one file per actor: `loop/decisions.<actor>.jsonl`」，「它不是什么」栏写「the file is chosen by who decided」）按 02 L13 改读法：`<actor>` 是编号前缀里的角色名，文件由前缀定，不是由写这一行的人定；文件名字面不动（02 L13、09 L14））
- `research-loop/common/REVIEW-CHECKLIST.md`：37(d)（判断类检查的问题清单文件本身（09 L17 定的名字），doctor 末段指到它）
- `research-loop/hooks/`：35(c)（销号钩子（挂 SessionEnd 和 SubagentStop 的那个脚本）：每张开干单子的四件事做完、sessions 账结束版写完之后，最后一步删掉本会话的状态文件 loop/.sessions/<session_id>.json；每个会话删一次，名下没有开干单子的会话也删）；35(d)（登记钩子（角色 skill 加载时触发的那个）把状态文件写到 loop/.sessions/<session_id>.json）；35(f)（hooks/hooks.json 加写权钩子脚本：钩子挂 Write、Edit、Bash 三个工具（Bash 那一支解析命令里的重定向、tee、sed -i、mv/cp 的写目标），仍然只拦两类路径（别的角色目录、直接写 loop/））；39(a2)（登记钩子（session registration hook）：subagent 加载角色 skill 时登不登记一行 sessions、`session_id` 填父会话号还是另立标识；钩子输入里的 `agent_id`/`agent_type` 怎么用。标 PENDING(verify 5)）；47(b)（销号钩子（挂 SessionEnd 和 SubagentStop，04 L120、04 L223）按此写序：先逐张 release，最后写 sessions 的 closed 版）
- `research-loop/schemas/decisions.schema.json`：34(a)（`id` 栏的前缀说这行落哪个文件（`dec-(idea|deploy|run|analysis|reviewer|gyb)-NNNN`），`actor` 是单独一栏记谁写的（02 L21、L11））；34(b)（行上加 `op` 栏，取 `add`/`update`/`confirm`/`retire`/`merge` 五值，过版判定靠它跳过 confirm 版（02 L22、L390））；34(e)（`session_id` 栏不对 gyb 那本硬校验成 `cli`；裸终端写的行 `session_id` 记 `cli`，角色会话替 gyb 写的行记那个会话（02 L11、L129））；37(a)（decisions 行格式：`status`/`op` 是 `retired` 的那一版 `text` 必填，注一句「废除版的正文是废除理由」）
- `research-loop/schemas/feedback.schema.json`：37(b)（`rules_version_after` 采纳时 rl 自动填，取值是加一之后的那个整数）；37(f)（`target` 只收两种取值（仓库内文件路径，或带前缀编号 `rule-NN`/`principle-NN`）；要改的是某张表的某一行时 `target` 填那张表所在文件的路径、哪一行写进 `text`；`status` 三值里 `accepted` 和 `rejected` 都是终态（定义处 09 L73）；`rules_version_after` 是整数）
- `research-loop/schemas/handoffs.schema.json`：43(d)（the `line` field: computed by rl from decision_refs' root_id; decision_refs may span different root decisions, so a cross-root handoff belongs to every related line; whether `line` is stored as one value or a list is PENDING(part 04 L27)）；45(a)（字段表加顶层 `track` 一栏（方向名，`work_order` 开单时由 idea 填、开单必填）；`launch_order` 不加顶层 `track` 栏，它的方向名仍只在 `attempts[].track`（04 L38 的 attempts 内层栏不动））；45(d)（`code_paths` 字段的说明改成全收口径：这张单改过的代码路径不论在不在 `experiments/` 里都列，宿主文件也算。必填规则不动（`work_order` 进 `done_pending_review` 时必填、非空））
- `research-loop/schemas/scratch.schema.json`：41(a)（open 版必填按 role 分岔：role=deploy 必填 worktree、base_commit、branch；role=analysis 只必填 dir，base_commit 与 branch 两栏对 analysis 不设）
- `research-loop/schemas/sessions.schema.json`：37(g1)（`rules_version` 必填、整数，取值来源写成母版头部那一行（03 L184 是行格式定义处，04 L141 与它一字不差））；39(a2)（`session_id` 栏的语义：父子会话同号时主键怎么算，要不要另加一栏区分 subagent；`launched_by` 取值 `subagent` 那一档（04 L140）要不要保留。标 PENDING(verify 5)）
- `research-loop/scripts/rl_lib.py`：34(a)（decision add 选目标文件按编号前缀，前缀由会话定：角色会话用该角色前缀（`--as-gyb` 也一样，actor 记 gyb、quote 必填），裸终端用 gyb 前缀；一条决定的所有版本永远同一个文件，扫号只读本前缀那一个文件（02 L11、L52、L62））；34(b)（update、retire、merge 写完当场列出引旧版而没到终态的单子和 holder；confirm 追加一版正文不变、只加来源、`op` 记 `confirm`，写完不打印；过版判定跳过 `op` 是 `confirm` 的版本，引用版本比最新一个非 confirm 版小才算过时（02 L85、L87、L111））；34(c)（`--with-runs` 第一跳按 handoffs 的 `decision_refs`（任一版）找出引这条决定的单子当起点，再沿 `parent_id` 往下收子孙单和它们的 run 与 metrics，按单子编号去重、按引的版本分组（02 L114、L392、L130））；34(e)（决定入账的收行判据：`decisions.gyb.jsonl` 只装裸终端新开的决定及其全部后续版本，后续版本可以来自角色会话 `--as-gyb --quote`（`session_id` 照记那个会话），所以不能按「session_id 必须是 cli」硬拦；开新条的前缀判据按 02 第二节（02 L11））；35(d)（actor 判定读 loop/.sessions/<session_id>.json（不是 ${CLAUDE_PLUGIN_DATA}/sessions/）：读得到就按文件里的角色，读不到就是裸终端、actor 是 gyb、session_id 记 cli）；35(e)（总规矩（只增不改、按 status 校验、锁、进 git、脏树白名单）只对九本账生效，loop/.sessions/ 下的状态文件按普通文件处理）；37(a)（废除版入账校验：`retired` 那一版 `text` 必填，正文就是废除理由（问题 36 裁 c）；不新加栏、不复用 `force_reason`）；37(b)（读写母版头部 `rules_version` 那一行的函数：整数、从 1 起、那一行是唯一真源；这是 rl 唯一一处往母版文件写字的动作（09 L59），母版正文仍人手改）；37(f)（feedback 入账校验：`target` 按上面两种取值判；`accepted`、`rejected` 之后同一条不再收新版本（没有改一版的子命令，再提走 `rl feedback add` 开新一条，rl 不建链））；37(g1)（`rl session start` 落开始版时，`rules_version` 从 `common/GLOBAL-RULES.md` 头部那一行读（整数），钩子不传这个值（05 L40「`start` 的 `rules_version` 由 rl 从母版读」，09 L59「会话账的开始版就从这一行读」））；39(a2)（actor 判定的子会话分支（状态文件读到父会话的角色对不对、要不要另立信号）；工作指南第 92 行写明这一分支等第 5 条）；39(b2)（读 `research-loop.json` 的 `launcher.*` 四条模板并执行，留空一律跳过不报错（08 第二节 L51、L55））；39(b3)（配置读取：解析 `host_ledgers` 列表的 `path`/`note`/`kind` 三栏，机器只解析 `kind`，按 `kind: runs` 取宿主 runs 账路径）；39(b4)（配置读取认这三个键：`launcher.abort_cmd`（模板，留空跳过）、`repo_run`（固定三栏 `env`/`entry`/`notes`，机器不解析）、`host_ledgers`（列表，每项 `path`/`note`/`kind`，机器只解析 `kind`））；39(c)（账路径一律从 `tables/ledgers.json` 解析，不从 `research-loop.json` 读账路径）；40(e)（读 research-loop.json 阈值的代码认的键集合里没有 notify.*（reclaim 和 status 只读 reclaim.* 与 status.stale_holder_minutes））；40(f)（读 research-loop.json 阈值的代码认的键集合里没有 notify.*（L235 这句就是 05 用到的键清单，键清单落在读配置的代码里））；41(d)（owner 判定：快车道补单的 owner 取 gyb，不取 from_role（from_role 与 to_role 都是 deploy），accept 权限与 fyi/orphaned 收件人按这个 owner 走）；43(d)（line computation no longer takes only decision_refs[0].root_id; every root id of a cross-root handoff must be reachable by the line views; the stored shape (one value or a list) is PENDING(part 04 L27)）；45(a)（handoffs 按 status 的必填校验加「`work_order` 开单必填 `track`」；开 `launch_order` 时把父单顶层 `track` 抄进 `attempts[0].track` 的抄录逻辑，和抄 decision_refs、batch 同一处）；45(c)（`handoff open` 的参数校验：`work_order` 缺 `--track` 报 validation（退出码 2）；`launch_order` 不给 `--track` 不报错，改走从父单抄的那条路）；47(b)（「写账的会话得活着」这条入账校验（03 L15）按此序自然放行销号钩子写的 release 行——release 落账时 sessions 最新版还是 open）
- `research-loop/skills/<role>/SKILL.md`：35(b)（被查的对象：五份角色说明书里出现的子命令、账名、目录名，以及不许抄 common/ 母版条文）；39(a1)（五份角色说明书里 owner 派活那一段（04 第四节的副本），起 subagent 时点名角色 agent 类型；08 L331 记 2026-08-18 已给 `10`–`14` 五份各加一句「被派活时以插件角色 agent 类型起 subagent，agent 定义预加载本角色 skill」、类型名照 `agents/<role>.md` 的文件名，SKILL.md 照 10 到 14 抄）
- `research-loop/skills/analysis/SKILL.md`：45(b)（同上一条：analysis 是 holder（06 L218 ledger_writes 含 handoffs 的 start），被收回的是 `analysis_order`，半截产物在 `analysis/`）
- `research-loop/skills/deploy/SKILL.md`：41(e)（「限制条件」栏的派活交代：deploy 在快车道派 gpu-runner 时，gpu-runner 是宿主的东西、不登记 sessions 账、不写杂账，deploy 备好完整命令（`--run-id` 填 ql_tag、`--track` 填被微调实验的方向）交给它，跑完的数字由 deploy 自己追加进杂账（07 L58））；45(b)（自己手上的单子被收回（收到 `withdrawn` 通知）时：把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定；回完按 05 L138 自己 `rl issue close`。deploy 是 holder：06 L192 ledger_writes 含 handoffs 的 start）
- `research-loop/skills/research-loop/SKILL.md`：39(b1)（入口 skill 的 init 领路那一段（工作指南 L102「入口 skill：init、迁移提醒、领路五条」，08 第五节），三句一起写进去）
- `research-loop/skills/run/SKILL.md`：45(b)（同上一条：run 是 holder（06 L204 ledger_writes 含 handoffs 的 start），被收回的是 `launch_order`，半截产物目录在 `artifact_root`。run 能不能往 issue 回话见 unresolved）
- `research-loop/tables/commands.json`：41(f1)（`ql close` 那一条的 notes 写两条路都删 worktree 与同名分支（05 命令表的机器读副本））；41(f2)（`ql open` 那一条的 notes 写 `--from` 标 quick_lane 并让单子离开待干队列、不占 holder（05 命令表的机器读副本））；41(f3)（转进单出口那一步的子命令名，名字未定；占位条目的 signature 空、pending 标 PENDING(issue 41f)（05 命令表的机器读副本））；45(c)（`handoff open` 那一行（05 L64 命令表的机器读副本）的签名：`--track T` 从 `launch_order` 专用的那一组参数（`--command ... --workdir ... --track ... --config k=v ...`）里提出来单列成 `[--track T]`，`work_order` 也能收；notes 写明 `launch_order` 不给 `--track` 时从父单顶层 `track` 抄进 `attempts[0].track`，所以发射单侧可省。参数解析本体在 research-loop/bin/rl，(a) 的落点已列，本条不重复）
- `research-loop/tables/config_defaults.json`：39(b4)（08 第二节配置键的机器读副本，三个键各一行：`launcher.abort_cmd`（模板，default 空，留空跳过）、`repo_run`（固定三栏 `env`/`entry`/`notes`）、`host_ledgers`（列表，每项 `path`/`note`/`kind`），三项「init 问」栏都是 ✓）
- `research-loop/tables/gyb-usecases.json`：40(c)（status 段 2（assignee 是 gyb 的 issue）是这条的唯一出口，段 2 从 use case 表倒推（01 L100-114））；40(d)（同 (c)：status 段 2 是 assignee 为 gyb 的 issue 的唯一出口）
- `research-loop/tables/ledgers.json`：34(d)（decisions 那一行的 `file` 照抄 `loop/decisions.<actor>.jsonl` 不改字面，加一条说明：`<actor>` 读作编号前缀里的角色名，不是写这一行的人（02 L13、L403）；`id_pattern` 的六个前缀和 `books` 六本对得上）；35(a)（第 20 项扫的对象就是 plain_files 里的 `loop/.sessions/`（现文 tables/ledgers.json 第 94 行已登记这条路径，_source 写着 06 L118; 08 L18; sync-inbox Q35(e) L194））；35(d)（plain_files 里 loop/.sessions/ 那条就是这个路径的登记处（现文第 94 行））；35(e)（plain_files 一栏列 loop/.lock、loop/.doctor-acks.jsonl、loop/.sessions/ 三条，都不算九本账、不归 03 总规矩管（现文第 92 到 94 行已经是三条））；37(c)（grants 那一行留位不建立，标 PENDING(问题 43c)：不写 `rl grant` 子命令、不写 schema，撤销时列活会话这条也一并挂在这一行的 pending 说明里）；37(e)（grants 那一行留位不建立，标 PENDING(问题 43c)：`status` 只留 `active`、`revoked` 两个值，撤销后处置两句一并挂在这一行的 pending 说明里）；37(f)（feedback 那一行的 `status_values` 已是 proposed/accepted/rejected，补记 `accepted`、`rejected` 是终态（09 L73））；37(g2)（挂 grants 那一行的 PENDING(问题 43c) 说明：`rl grant revoke` 列会话之后收会话走 `rl session end --session ID`（09 L133）；`rl session end` 本身不改）；39(c)（九本账的名字和文件名（工作指南 L87 指到 03 第 47 到 57 行）：文件名钉死在 `loop/` 下，表里带上「位置钉死，配置里没有账路径」这条旁注）；43(c)（keep the grants row (中文名 授权 / 英文名 grants / 文件 loop/grants.jsonl) and mark it PENDING(issue 43c); the ledger list stays at nine rows）
- `research-loop/tables/roles/<role>.json`：35(b)（五份角色 json 的 reads 与 ledger_writes 两栏是这三样检查的对照源，reads 栏按 06 第 164 行的两种写法（账写账名、目录写带尾斜杠的相对仓库根路径））；35(f)（五栏 reads、writes、ledger_writes、dispatches_to、model 逐字照抄 06 第 172 到 234 行）
- `research-loop/tables/roles/analysis.json`：47(c)（核对结论：reads 已含 scratch（06 L216，2026-08-21 评审修复加进）、ledger_writes 的 scratch 是 "*"（06 L218「scratch 全部」），notes 第一条是英文原文「scratch: only the rows of its own ql_tag, only in the quick lane (06 L222)」，与新口径一致，不改）
- `research-loop/tables/roles/reviewer.json`：47(c)（核对结论：reads 已含 scratch（照抄 06 L228），与新口径一致，不改）
- `research-loop/tables/transitions.json`：39(a1)（（新建）→`todo` 行（04 L61）和 `in_progress`→`todo` 行（04 L75）的「之后谁拉起」栏：`auto` 起 subagent 那句写明用插件的角色 agent 类型，不用 general-purpose；`reissue` 行（04 L76）「同新建」跟着）；41(b)（（新建）→ done_pending_review 快车道补单那一行的「前提」栏加 code_paths 非空）；41(c1)（新增一行：从 todo 到 todo（追加一版标 quick_lane），谁能写 deploy，前提是单子在 todo，之后没人拉起（离开待干队列、不派人接、不占 holder），子命令 `rl ql open --from`）；41(c2)（新增一行（出口两条路）：quick_lane 标记的单追加一版直达 done_pending_review，前提同快车道新建行（report_paths.method、code_paths、explanation、与 scratch 行互指），验收人 gyb；放弃时追加一版退回 todo 并去掉 quick_lane 标）；41(d)（（新建）→ done_pending_review 行「谁能写」栏已写「`deploy`（快车道补单，owner 记 gyb）」、accept 行「owner；快车道补单只有 gyb」，照抄即可）；41(f2)（与 (c1) 新增的那一行同一件事，两处口径要一致）；41(f3)（行 ql_transfer_exit 的子命令栏标 PENDING(issue 41f)）；43(e)（row done_pending_review -> accepted: keep 谁能写 as owner (quick-lane make-up orders gyb only) and add the note that a handoff with dispatch=manual is accepted by gyb himself by default, with the fyi to owner still sent）；45(a)（（新建）→ `todo` 那一行的前提栏：`work_order` 一支加「有 `track`」；`launch_order` 一支写明第一次尝试的 `track` 由 rl 从父单顶层 `track` 抄，和 decision_refs、batch 一起抄）；45(b)（withdraw 那一行（转到 `withdrawn`）补这一句：收回时 holder 把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定。它是压在 holder 身上的纪律、rl 查不了，所以落在这一行的 side_effects 一栏而不是能校验的前提栏）
- `research-loop/tests/`：34(a)（测试 3（决定来源）与测试 9（actor 与权限）：角色会话 `--as-gyb` 开的决定落角色前缀那本、actor 记 gyb；30 第 106 行写明这一例在测试 3 里，测试 9 不重复）；34(b)（测试 3（决定来源）加一例「`confirm` 之后不标过版」：引 confirm 前那一版的单子 `rl decision stale` 不列、confirm 写完不打印受影响单子、行上 `op` 记 `confirm`（30 第 56 行）；测试 5（过版）按同一判据写）；34(e)（测试 3（决定来源）原文那一例「`decisions.gyb.jsonl` 拒收非 cli 行」（30 L54）和测试 9（actor 与权限）30 L106 的同一句，用例按 02 L11 与 (e) 的口径写：角色会话 `--as-gyb` 的 add 落角色前缀那本、actor 记 gyb，gyb 那本没有这一行（rl 不是拒收，是按会话定前缀）；角色会话 `--as-gyb` 给 `dec-gyb-NNNN` 追加的 update/confirm 落 gyb 那本、`session_id` 记那个会话；gyb 那本里每条决定的 add 版 `session_id` 都是 `cli`）；35(b)（测试 13（tests/test_skill_refs.py）：三样都查——写命令在该角色的 ledger_writes 里；SKILL.md 里出现的账名和目录在 reads 里；引用的名字都存在、母版不抄）；35(c)（测试 7（销号）加一条用例：销号之后本会话的状态文件不在了（30 第 76 到 86 行测试 7 现文的「要加的」清单里没有这一条，施工时补））；35(f)（测试 13（tests/test_skill_refs.py）三样都查，与 (b) 同一处）；37(a)（测试 3（决定来源）：加一例 `retire` 不给理由拒收、给了理由落进那一版 `text`；这条测试原来已有「`retire` 同样打印受影响的单子」）；37(b)（测试 17（feedback）：30 第 171 行已把这一句写进「要加的」——accept 把 `rules_version` 加一并写回 `common/GLOBAL-RULES.md` 头部那一行）；37(f)（测试 17（feedback）：加 `target` 两种取值的正反例、表的某一行走「路径进 target、行号进 text」、`rejected` 之后再写同一条拒收）；37(g1)（测试 17（feedback）原文已有「sessions 开始版记 rules_version」，补一例：改母版头部那一行之后新开会话记的是新值）；39(a2)（测试 7（销号，30 L76-86）与测试 8（钩子，30 L88-92）：subagent 登记与销号的用例等第 5 条测完才写得成）；39(b1)（测试 12 端到端（30 L132-136，沙盒仓库 `rl init` 建树、裸终端跑）、测试 9（30 L103「`rl init` 在角色会话里跑退出码 3」））；39(b2)（测试 11（30 L120-130，reclaim 开干的发射单默认不杀、`--kill` 才杀））；41(a)（测试 16（快车道）：analysis 的 `ql open --role analysis` 开张版只填 dir，deploy 开张版三栏齐；30-build-steps-verify-tests.md L164）；41(b)（测试 2（转移表）L49 那条快车道补单前提用例加 code_paths 非空；测试 4（交付物）L60「快车道补单只要 method」一句同步成还要 code_paths）；41(c1)（测试 2（转移表，每行合法转移一个用例）、测试 16（快车道））；41(c2)（测试 2（转移表）、测试 16（快车道））；41(f1)（测试 16（快车道）：close 两条路各一个用例，关张后工作树与同名分支都不在）；41(f2)（测试 16（快车道）、测试 2（转移表））；41(h)（测试 11（rl status、rl inbox 与 rl reclaim）：`--line` 过滤与 `--group-by line` 的用例里，没关的快车道单独成组）；43(b)（测试 11（`rl status`、`rl inbox` 与 `rl reclaim`）：原文的「`--line` 过滤对」一句加一个跨根用例——一张 decision_refs 分属两条根决定的单子，--group-by line 时两条线下面都出现，--line 过滤两条线各自都命中）；43(e)（测试 2（转移表）：done_pending_review -> accepted 那一行的用例加一条 dispatch=manual 的单子由 gyb accept 通过；owner accept 仍然通过）；43(e)（测试 15（收回与接替）：现文已有「gyb 越过 owner 验收和打回都给 owner 发 `fyi`」（30 L154），dispatch=manual 的单子 gyb 验收时 fyi 照发，用例按此加一条）；45(a)（测试 2（转移表，（新建）→ `todo` 的前提用例）加两条：`work_order` 开单缺 `track` 拒收退出码 2；`launch_order` 开单不给 `--track` 时 `attempts[0].track` 等于父单顶层 `track`）；45(c)（测试 2（转移表的开单前提用例）：`launch_order` 不带 `--track` 开单通过且 `attempts[0].track` 等于父单顶层 `track`，与 (a) 的用例是同一条）；47(b)（测试 7（销号，30 L76-86）加一条写序用例：release 行的 ts 早于 sessions closed 版、release 行的 session_id 是本会话且不被退出码 3 拒收）

## 三、逐笔逐子项

## 问题 34（sync-inbox L166-172（事项段落「2026-08-18 来自 rl-hub-v4 关于 02 定稿动到冻结三份的几句（冻结后待议）」），子项 L170 的（a）到（d）、L171 的 (e)，核手核过）

### 34(a) 状态 settled

- 代码落点：`research-loop/scripts/rl_lib.py`（decision add 选目标文件按编号前缀，前缀由会话定：角色会话用该角色前缀（`--as-gyb` 也一样，actor 记 gyb、quote 必填），裸终端用 gyb 前缀；一条决定的所有版本永远同一个文件，扫号只读本前缀那一个文件（02 L11、L52、L62））；`research-loop/bin/rl`（子命令 `rl decision add`：用法与帮助写「前缀按会话定（角色会话用角色前缀，`--as-gyb` 也一样；裸终端用 `gyb`），序号在本前缀内自动分配，落前缀那本」，不写「落 actor 自己那本」（02 L109））；`research-loop/schemas/decisions.schema.json`（`id` 栏的前缀说这行落哪个文件（`dec-(idea|deploy|run|analysis|reviewer|gyb)-NNNN`），`actor` 是单独一栏记谁写的（02 L21、L11））；`research-loop/tests/`（测试 3（决定来源）与测试 9（actor 与权限）：角色会话 `--as-gyb` 开的决定落角色前缀那本、actor 记 gyb；30 第 106 行写明这一例在测试 3 里，测试 9 不重复）
- 新口径：sync-inbox L170: （a）`05:47` `rl decision add` 那行「落 actor 自己那本（角色会话 `--as-gyb` 落角色那本）」→「落编号前缀那本：角色会话开的用那个角色的前缀（`--as-gyb` 也一样，`actor` 记 gyb），裸终端开的用 `gyb` 前缀」
- 原冻结句：`05-rl-cli.md` L47「| `rl decision add --text --source K:V ... [--quote ...]` | 追加一条新决定，编号自动分配，落 actor 自己那本（角色会话 `--as-gyb` 落角色那本） | 五个角色、gyb |」
- 备注：裁决原话见 02-decisions.md L388「2026-08-18 gyb 裁「甲」：决定行按编号前缀落文件，一条决定所有版本同文件，`actor` 单独记」；定义处正文在 02 L11。

### 34(b) 状态 settled

- 代码落点：`research-loop/scripts/rl_lib.py`（update、retire、merge 写完当场列出引旧版而没到终态的单子和 holder；confirm 追加一版正文不变、只加来源、`op` 记 `confirm`，写完不打印；过版判定跳过 `op` 是 `confirm` 的版本，引用版本比最新一个非 confirm 版小才算过时（02 L85、L87、L111））；`research-loop/bin/rl`（子命令 `rl decision update`、`rl decision confirm`、`rl decision stale`（以及 `rl status` 段 6、`rl inbox` 的过版一项按同一判据算））；`research-loop/schemas/decisions.schema.json`（行上加 `op` 栏，取 `add`/`update`/`confirm`/`retire`/`merge` 五值，过版判定靠它跳过 confirm 版（02 L22、L390））；`research-loop/tests/`（测试 3（决定来源）加一例「`confirm` 之后不标过版」：引 confirm 前那一版的单子 `rl decision stale` 不列、confirm 写完不打印受影响单子、行上 `op` 记 `confirm`（30 第 56 行）；测试 5（过版）按同一判据写）
- 新口径：sync-inbox L170: （b）`05:48` update/confirm 那行「写完当场列出引旧版而没到终态的单子和 holder」只对 update 成立，confirm 不打印、不算改版
- 原冻结句：`05-rl-cli.md` L48「| `rl decision update ID --text [--source ...] [--quote ...]` / `rl decision confirm ID --source ...` | 追加一版（update 换正文；confirm 正文不变只加来源）；不给 source 就继承上一版；写完当场列出引旧版而没到终态的单子和 holder | 同 actor（跨角色改别人的决定在自己那本 add，来源指原决定） |」
- 备注：裁决原话见 02-decisions.md L390「2026-08-18 gyb 裁「乙」：`rl decision confirm` 不算改版——写完不打印受影响单子，过版判定跳过 `confirm` 版（引用版本比最新一个非 confirm 版小才算过时）；为此行上加 `op` 字段」。sync-inbox L170 末句已写明 `04` 里没有「比最新版小就是过时」这类句子，`04` 不需要动。核手另核了 `05`：现文 L41、L137、L160 提到过版只写「过版决定」「过版的单子」，没有「比最新版小就是过时」的判据句，所以 bin/rl 那条落点里 `rl status` 段 6 与 `rl inbox` 的过版判据只从 02 L85 取，`05` 里没有要一并改的判据句。

### 34(c) 状态 settled

- 代码落点：`research-loop/bin/rl`（子命令 `rl decision show --with-runs`（同一行的 `rl decision list [--actor A] [--line L]` 不受这条影响））；`research-loop/scripts/rl_lib.py`（`--with-runs` 第一跳按 handoffs 的 `decision_refs`（任一版）找出引这条决定的单子当起点，再沿 `parent_id` 往下收子孙单和它们的 run 与 metrics，按单子编号去重、按引的版本分组（02 L114、L392、L130））
- 新口径：sync-inbox L170: （c）`05:50` `--with-runs`「沿 parent_id 链反查」→「先按 `decision_refs` 找起点单子再沿 `parent_id` 收」
- 原冻结句：`05-rl-cli.md` L50「| `rl decision show ID [--version V] [--history] [--with-runs]` / `rl decision list [--actor A] [--line L]` | 默认最新版；`--with-runs` 沿 parent_id 链反查各版本派出的单子和 run 与 metrics | 谁都行 |」
- 备注：裁决原话见 02-decisions.md L392「2026-08-18 gyb 裁「甲」：`rl decision show --with-runs` 第一跳按 handoffs 的 `decision_refs`（任一版）找起点单子，再沿 `parent_id` 收子孙单和 run/metrics，去重、按版本分组」。30 第二节（标题「测试清单十七条，加 `05` 定稿点名的三条」，测试 1 到 20）里没有点名 `--with-runs` 的用例；30 全文唯一提到 `--with-runs` 的是第 300 行摩擦一节（原样未核实）里的一条阻塞项，不是测试，所以不列测试落点。

### 34(d) 状态 settled

- 代码落点：`research-loop/tables/ledgers.json`（decisions 那一行的 `file` 照抄 `loop/decisions.<actor>.jsonl` 不改字面，加一条说明：`<actor>` 读作编号前缀里的角色名，不是写这一行的人（02 L13、L403）；`id_pattern` 的六个前缀和 `books` 六本对得上）；`research-loop/common/GLOSSARY.md`（词表 `decisions` 那一行（现文第 25 行写「one file per actor: `loop/decisions.<actor>.jsonl`」，「它不是什么」栏写「the file is chosen by who decided」）按 02 L13 改读法：`<actor>` 是编号前缀里的角色名，文件由前缀定，不是由写这一行的人定；文件名字面不动（02 L13、09 L14））
- 新口径：sync-inbox L170: （d）`03:49` 词表 `loop/decisions.<actor>.jsonl` 的 `<actor>` 读作编号前缀里的角色名，只是读法说明，可不动字。
- 原冻结句：`03-ledgers.md` L49「| 决定账 | decisions | `loop/decisions.<actor>.jsonl`，五个角色加 gyb 六个文件 |」
- 备注：02-decisions.md L403 逐字写着「`03` 词表 `loop/decisions.<actor>.jsonl` 的 `<actor>` 读作前缀里的角色名（03 冻结，冻结后待议，只是读法说明，不必改字）」。现文 research-loop/tables/ledgers.json 的 decisions 行已按此写着 file、books、id_pattern，只差这条读法说明。读手拿不准的 GLOSSARY 落点按原文定下：02 L13 说的「词表」是施工计划第二节那份（02 L5「第二节词表」、02 L13「源文档三处口径（词表按 actor、第三节按编号前缀、第六节按 actor 加括号例外）」），09 L14（读手写成第 13 行，现文第 13 行是 GLOBAL-RULES 那行，第 14 行才是 GLOSSARY）逐字写「`common/GLOSSARY.md` | 词表，就是施工计划第二节那份，再加一栏「它不是什么」」，所以 02 L13 的读法说明同样落到 GLOSSARY.md；现文 research-loop/common/GLOSSARY.md L25 的 decisions 行写着「one file per actor」和「the file is chosen by who decided」，是按 actor 的旧读法。

### 34(e) 状态 settled

- 代码落点：`research-loop/scripts/rl_lib.py`（决定入账的收行判据：`decisions.gyb.jsonl` 只装裸终端新开的决定及其全部后续版本，后续版本可以来自角色会话 `--as-gyb --quote`（`session_id` 照记那个会话），所以不能按「session_id 必须是 cli」硬拦；开新条的前缀判据按 02 第二节（02 L11））；`research-loop/schemas/decisions.schema.json`（`session_id` 栏不对 gyb 那本硬校验成 `cli`；裸终端写的行 `session_id` 记 `cli`，角色会话替 gyb 写的行记那个会话（02 L11、L129））；`research-loop/bin/rl`（子命令 `rl decision add` / `update` / `confirm` 的 `--as-gyb --quote` 这条路径：quote 必填，actor 记 gyb，落哪本按前缀）；`research-loop/tests/`（测试 3（决定来源）原文那一例「`decisions.gyb.jsonl` 拒收非 cli 行」（30 L54）和测试 9（actor 与权限）30 L106 的同一句，用例按 02 L11 与 (e) 的口径写：角色会话 `--as-gyb` 的 add 落角色前缀那本、actor 记 gyb，gyb 那本没有这一行（rl 不是拒收，是按会话定前缀）；角色会话 `--as-gyb` 给 `dec-gyb-NNNN` 追加的 update/confirm 落 gyb 那本、`session_id` 记那个会话；gyb 那本里每条决定的 add 版 `session_id` 都是 `cli`）
- 新口径：sync-inbox L171: (e) `05:25`「`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行」与 `02` 定稿的编号前缀规矩打架——改成「`decisions.gyb.jsonl` 只装裸终端新开的决定及其全部后续版本（后续版本可以来自角色会话 `--as-gyb --quote`，`session_id` 照记那个会话），开新条的前缀判据见 `02` 第二节」。
- 原冻结句：`05-rl-cli.md` L25「grants 只有 gyb 能写：裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收（2026-08-17 gyb 裁，问题 27）。`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行，这条不变，角色会话里替 gyb 记的决定落那个角色自己那本、actor 记 `gyb`、带 quote。」
- 原冻结句：`03-ledgers.md` L61「决定账六个文件同一个格式，行格式、编号规则、`root_id`、来源三类、`quote` 的填法、`merged_from`、`decisions.gyb.jsonl` 只收 `session_id` 是 `cli` 的行，这些全写在 `02-decisions.md`。」
- 备注：这一子项来自 sync-inbox L171 的「统筹补扫 2026-08-21（评审修复，gyb 授权）」，不在派活里点名的（a）到（d）之内，属同一笔欠账 34 的 要改的地方，一并列出。新口径的定义处是 02-decisions.md L11 第二节。读手的两处拿不准按原文定下。一，03 L61 与 05 L25 是同一句的两处所在，sync-inbox (e) 只点了 05:25；03 L61 是指路句（末尾「这些全写在 `02-decisions.md`」），代码落点与 (e) 完全相同，冻结句改不改随问题 34 整段等最后一期（sync-inbox L172；HANDOFF 第五节「34/35/40/41/43/45 段里 2026-08-21 评审补扫追加的行也一并落」），本条目把 03 L61 列进 frozen_original 是为了最后一期合成现行版时不漏这一处。二，写用例照 02 L11 与 (e)：02 L126 写「别处引用以这里为准」，sync-inbox L172 写「此前读 `05` 命令表时以 `02` 定稿为准」，(e) 本身是 gyb 授权的评审修复。旧句「只收 / 拒收非 cli 行」现在还留在四个不冻结的地方：02 L122（决定账测试用例清单那句）、30 L54（测试 3 原文）、30 L106（测试 9）、01 L94（01 已定稿 `cd569ab`，不冻结）；本对照单不改文件，只记下来。

读手没能定的：无。读手的三处都按原文判定了：一（03 L61）和二（30 的测试用例照哪句写）写进 (e) 的 note，三（GLOSSARY.md 要不要落）写进 (d) 的 landing 和 note。

核手的话：核过没改的：五条 new_wording 都是 sync-inbox L170/L171 现文逐字（(b) 末尾省掉一个分号，属截取）；六条 frozen_original（05 L47、L48、L50、L25，03 L49、L61）quote 与行号都和现文一致；十五条 landing 路径全在清单内；02 的引用行（L11、L13、L21、L22、L52、L62、L85、L87、L109、L111、L114、L122、L126、L129、L130、L388、L390、L392、L403-405）逐行核过与读手引的内容一致；30 的测试 3/5/9 标题与 L54、L56、L106 核过；status 五条 settled 没动；L170 末句「`04` 里没找到……」读手放在顶层 note 逐字引，没当子项，符合要求。改了 7 处：1) (b).note 补一句核 `05` 的结果——05 L41、L137、L160 提到过版但没有「比最新版小就是过时」的判据句，给 bin/rl 那条落点垫底；2) (c).note 把「30 的十七条测试」改成「30 第二节测试 1 到 20（标题写十七条加 `05` 定稿点名的三条）」，并补上 30 全文唯一提到 `--with-runs` 的是第 300 行摩擦一节的阻塞项这一事实；3) (d).landing 加 research-loop/common/GLOSSARY.md 一条，依据是 02 L13 的「词表」指施工计划第二节、09 L14 说 GLOSSARY.md 就是那份词表，且现文 GLOSSARY.md L25 写着按 actor 的旧读法（「one file per actor」「the file is chosen by who decided」），这就把读手 unresolved 第三条定掉了；4) (d).note 把读手写的「09 第 13 行」改成第 14 行（第 13 行是 GLOBAL-RULES 那行），并写明 GLOSSARY 落点的推导链和现文内容；5) (e).landing 的 tests 那条把「拒收的是裸终端以外新开的条」改成按 02 L11 的路由说法（rl 按会话定前缀、不拒收）并写出三个可测断言，原句的「拒收」框架与 02 L11「前缀由会话定」不合；6) (e).note 把读手 unresolved 第一条（03 L61）和第二条（用例照哪句写）按原文定下并记下旧句还留在 02 L122、30 L54、30 L106、01 L94 四个不冻结处这一事实；7) unresolved 清空成「无」并注明三条各落到哪里。

## 问题 35（sync-inbox L190-196，核手核过）

### 35(a) 状态 settled

- 代码落点：`research-loop/bin/rl`（doctor 子命令：扫描项表末尾加第 20 项「陈旧会话状态文件」（loop/.sessions/ 下的状态文件，对应 sessions 账最新版是 closed，或者超过一天没动），修法是删文件，「修完之后归谁推」栏填 gyb；doctor 项数由十九变二十。「超过一天」在代码里硬编码 24 小时并标 PENDING(part 08 L57)，08 第三节阈值表没有对应的键）；`research-loop/tables/ledgers.json`（第 20 项扫的对象就是 plain_files 里的 `loop/.sessions/`（现文 tables/ledgers.json 第 94 行已登记这条路径，_source 写着 06 L118; 08 L18; sync-inbox Q35(e) L194））
- 新口径：sync-inbox L194: （a）`05` doctor 表加一项「陈旧会话状态文件」——sessions 账已销号或超过一天没动的状态文件，修法删文件、归 gyb 推（十九项变二十项，`03`/`05` 提到「十九项」的句子跟着改）
- 原冻结句：`05-rl-cli.md` L191「`rl doctor [--ack ITEM ID] [--unack ITEM ID] [--list-acks]` 扫九本账。十九项：前十八项照施工计划第六节，第 19 项是 2026-08-17 从待验证第 10 条的失败备案升上来的。修法和「修完之后归谁推」两栏 2026-08-17 gyb 裁（第 3、5、6 项的修法出自源文档，其余是这次补的）。「只报不修」的项 doctor 只列出涉及的行，不给修法命令，人看了决定。」
- 原冻结句：`05-rl-cli.md` L213「| 19 | sessions 行 `model` 是 `unknown` | `rl session amend ID --model M` | gyb 或该角色 |」
- 原冻结句：`05-rl-cli.md` L221「doctor 只做脚本能判的检查，也就是上面十九项。判断类的检查（比如「这张单的报告有没有回答它引的决定」「这条 run 的 config 和发射单写的一不一样」）不在 doctor 里：问题清单写成一份文件放 `common/`，由 reviewer 角色派 sonnet subagent 一人领一题逐条查，查出来的写进 review/ 清单，要不要开 issue 由 gyb 看完用自己的权限开（2026-08-17 gyb 裁，问题 6 后改：只写清单不开 issue；见 09-common-and-feedback.md 和 14-role-reviewer.md）。」
- 原冻结句：`03-ledgers.md` L240「- 每本账的写命令和查询命令清单、`rl trace`、`rl status`、`rl inbox`（只读不关）、`rl doctor`（十九项与修法；`--ack/--unack` 是写命令、只有 gyb）、`rl reclaim` 在 `05-rl-cli.md`；`rl run add` 的签名去掉 `--artifact-dir`（2026-08-17 裁）。`05` 的「锁与写序」一节和退出码表照抄本份，两边一字不差。」
- 原冻结句：`06-hooks-and-permissions.md` L120「状态文件谁删（2026-08-18 gyb 裁）：销号钩子在会话结束时顺手删；会话被强杀删不掉的留着，由 `rl doctor` 扫，sessions 账里对应会话已销号、或文件超过一天没动的当垃圾清。活死以 sessions 账为准，状态文件只是缓存（原则 8）。位置定在 `loop/.sessions/` 之后不再依赖宿主变量，原来「`${CLAUDE_PLUGIN_DATA}` 解析到哪」那半条待验证撤销，不测了。」
- 备注：裁决原话在 sync-inbox L192：gyb 2026-08-18 对 06 答「5a」（会话状态文件销号钩子顺手删、删不掉的 doctor 扫）；定义句是 06 第 120 行（已抄进 frozen_original）。06 第 476 行同样记了这一条并注明「已冻结，冻结后待议」。冻结分册 05 的正文至今没改（sync-inbox L196 状态：等最后一期，此前以 06 定稿为准），所以代码按新口径写、分册文字留到最后一期。03/05 提到「十九项」的句子经 grep 只有三处：05 第 191 行、05 第 221 行、03 第 240 行，都已抄进 frozen_original（09 第 17 行、14 第 15 行、30 第 217/225 行也写「十九项」，不在本子项点名的 03/05 范围内）。「超过一天」的阈值：08-trees-init-and-host.md 第三节阈值表（第 57 到 80 行）十七个键里没有会话状态文件的陈旧阈值（最接近的 `reclaim.session_idle_hours` 默认 48 小时说的是 sessions 账没写账、不是状态文件没动，值也不是一天），所以阈值表没有键，代码硬编码一天并标 PENDING(part 08 L57)。第 20 项的测试落点：30 第二节测试 6（跨账写序）的用例只覆盖 doctor 第 3 项「stuck 单子没有 issue」，测试 18（rl session amend）的用例只覆盖第 19 项 model=unknown，两条都挂不上第 20 项，没有用例；30 第 225 行本来就写着十九项里只有第 3、19 项有用例。

### 35(b) 状态 settled

- 代码落点：`research-loop/tests/`（测试 13（tests/test_skill_refs.py）：三样都查——写命令在该角色的 ledger_writes 里；SKILL.md 里出现的账名和目录在 reads 里；引用的名字都存在、母版不抄）；`research-loop/tables/roles/<role>.json`（五份角色 json 的 reads 与 ledger_writes 两栏是这三样检查的对照源，reads 栏按 06 第 164 行的两种写法（账写账名、目录写带尾斜杠的相对仓库根路径））；`research-loop/skills/<role>/SKILL.md`（被查的对象：五份角色说明书里出现的子命令、账名、目录名，以及不许抄 common/ 母版条文）
- 新口径：sync-inbox L194: （b）`05:100` 附近「机器检查只查 SKILL.md 里出现的写命令在不在 `ledger_writes` 里」与 `06`「三样都查」不一致，改成三样
- 原冻结句：`05-rl-cli.md` L100「查询命令是 show、list、trace、status、inbox（只读，不顺带关任何 issue）、stale、doctor 七类，谁都能调，不进角色 json 的 `ledger_writes`；doctor 里 `doctor`（查）与 `doctor --list-acks` 是查询，`doctor --ack` / `--unack` 是写命令、只有 gyb 能敲。这是原则 2 的推论：读一律不设权，角色 json 的 `reads` 栏是纪律不是门禁。机器检查只查 SKILL.md 里出现的写命令在不在这个角色的 `ledger_writes` 里。」
- 原冻结句：`06-hooks-and-permissions.md` L35「读不上任何一层的硬拦（原则 2 推论）。九本账的查询命令谁都能调，角色 json 的 `reads` 栏是纪律不是门禁。机器检查只做文本对照、不设读的门禁：写命令在不在 `ledger_writes` 里、SKILL.md 里出现的账名和目录在不在 `reads` 里、引用的名字存不存在、有没有抄母版，见「`tests/test_skill_refs.py` 查什么」（2026-08-18 gyb 裁，三样都查）。」
- 备注：裁决原话在 sync-inbox L192：问题十二答「a」（测试 13 三样都查）。06 第 450 行写死了三样的内容：写命令 ∈ ledger_writes；SKILL.md 里出现的账名和目录 ∈ reads；引用的名字都存在、母版不抄；06 第 35 行是与 05 第 100 行末句对应的正文句（已抄进 frozen_original），06 第 256 到 260 行是三样的逐条定义。05 现文第 100 行末句仍是旧的一样。

### 35(c) 状态 settled

- 代码落点：`research-loop/hooks/`（销号钩子（挂 SessionEnd 和 SubagentStop 的那个脚本）：每张开干单子的四件事做完、sessions 账结束版写完之后，最后一步删掉本会话的状态文件 loop/.sessions/<session_id>.json；每个会话删一次，名下没有开干单子的会话也删）；`research-loop/tests/`（测试 7（销号）加一条用例：销号之后本会话的状态文件不在了（30 第 76 到 86 行测试 7 现文的「要加的」清单里没有这一条，施工时补））
- 新口径：sync-inbox L194: （c）`04` 销号钩子的动作清单加「删本会话的状态文件」。
- 原冻结句：`04-handoffs-and-sessions.md` L122「销号那一刻程序当场检查这个会话作为 holder 有没有还挂在开干的单子，只查开干，别的状态一律放行。有开干的单子就不许悄悄下线，名下有几张开干的就交回几张，一张不留（比如 run 会话 `--batch` 接下的整批一起交回），交回的编号全部记进 sessions 账 `released_handoffs`（2026-08-17 gyb 裁）。钩子调的销号对每一张做四件事：」
- 原冻结句：`04-handoffs-and-sessions.md` L124「1. 把单子交回待干（走转移表 `in_progress` → `todo` 那一行，账行 `actor` 记会话的角色、`via=session_end`）。」
- 原冻结句：`04-handoffs-and-sessions.md` L125「2. 写进度说明，内容是「会话销号，holder 是 X」。」
- 原冻结句：`04-handoffs-and-sessions.md` L126「3. 给 owner 发 orphaned 通知。」
- 原冻结句：`04-handoffs-and-sessions.md` L127「4. experiments/ 里的脏改动打一个 `wip/<ho-id>` 分支，分支名记进说明。」
- 备注：同出 06 的「5a」裁决（sync-inbox L192），定义句是 06 第 120 行「销号钩子在会话结束时顺手删」。06 第 278 行把「会话状态文件的写和删」列为 06 自己的定义处。接在哪一层按 04 第六节原文判定：04 第 122 行的清单开头写的是「钩子调的销号对每一张做四件事」，四件事逐张单子做一遍，而且只在名下有开干单子时才做；删状态文件是每个会话做一次、没有开干单子的会话也要做，所以它进不了这张逐张清单、也不是清单的第 5 条。位置是清单外面、第 127 行第 4 条之后、第 129 行「钩子漏掉的会话有两道兜底」之前，作为会话层的收尾动作：单子逐张处理完、sessions 账结束版写完，再删状态文件。删在最后是因为 rl 判 actor 靠这个文件（05 第 15 到 17 行），销号顺带写的 release 版和结束版都要记会话的角色（05 第 29 行、04 第 124 行），文件先删了这些账行就会判成裸终端。

### 35(d) 状态 settled

- 代码落点：`research-loop/scripts/rl_lib.py`（actor 判定读 loop/.sessions/<session_id>.json（不是 ${CLAUDE_PLUGIN_DATA}/sessions/）：读得到就按文件里的角色，读不到就是裸终端、actor 是 gyb、session_id 记 cli）；`research-loop/hooks/`（登记钩子（角色 skill 加载时触发的那个）把状态文件写到 loop/.sessions/<session_id>.json）；`research-loop/tables/ledgers.json`（plain_files 里 loop/.sessions/ 那条就是这个路径的登记处（现文第 94 行））
- 新口径：sync-inbox L194: （d）`06` 追裁（`f820504`）：会话状态文件路径改 `loop/.sessions/<session_id>.json`——`05:15` actor 判定那句的路径 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json` 同改
- 原冻结句：`05-rl-cli.md` L15「第一种，裸终端。`rl` 从会话状态文件读当前角色，状态文件由角色 skill 头部钩子在加载的时候写，路径是 `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`。读不到状态文件就是裸终端，actor 是 `gyb`，`session_id` 记 `cli`。裸终端不要 `--as-gyb` 这个参数（2026-08-16 夜 gyb 裁）。」
- 原冻结句：`06-hooks-and-permissions.md` L118「`rl` 判 actor 靠会话状态文件：状态文件由插件级钩子文件里的一条钩子在加载角色 skill 时写（`agent_type` 非空的 subagent 不写，2026-08-18 gyb 裁），路径 `loop/.sessions/<session_id>.json`（2026-08-18 gyb 裁：放记忆文件夹下的子文件夹，不用宿主给插件的数据目录变量）。」
- 备注：追裁的定义句是 06 第 118 行（已抄进 frozen_original），裁决记录在 06 第 451 行。落地处在 01-gyb.md 第 158 行已经是新路径：「actor 判定的实现（会话状态文件路径 `loop/.sessions/<session_id>.json`（2026-08-18 gyb 裁，原来是宿主给插件的数据目录）、钩子在加载角色时写）在 `06-hooks-and-permissions.md`。」05 现文第 15 行仍是旧路径；05 第 15 行还写着「状态文件由角色 skill 头部钩子在加载的时候写」，06 第 102 行已改成插件级钩子文件里的一条钩子写、skill 头部不声明钩子，这半句随 (f) 的三工具改法同源、同一轮改。05 第 29、39、233 行也提到会话状态文件，但都不带路径。

### 35(e) 状态 settled

- 代码落点：`research-loop/tables/ledgers.json`（plain_files 一栏列 loop/.lock、loop/.doctor-acks.jsonl、loop/.sessions/ 三条，都不算九本账、不归 03 总规矩管（现文第 92 到 94 行已经是三条））；`research-loop/scripts/rl_lib.py`（总规矩（只增不改、按 status 校验、锁、进 git、脏树白名单）只对九本账生效，loop/.sessions/ 下的状态文件按普通文件处理）
- 新口径：sync-inbox L194: （e）`03` 总规矩「普通文件不算九本账」的清单（`.lock`、`.doctor-acks.jsonl`）加 `loop/.sessions/`，`04` 提到状态文件路径的地方同改。
- 原冻结句：`03-ledgers.md` L9「九本账全放 `loop/`，一行一条 json，不用 markdown，只经 `bin/rl` 进出。角色会话直接 Write 或 Edit `loop/` 由钩子拦下，见 `06-hooks-and-permissions.md`。`loop/` 进 git：每次 commit 顺手带上，不另设 commit 动作，账本 diff 永远是纯追加行；九本账的 jsonl 和 `loop/.lock` 不算脏树，宿主白名单那一处见 `08-trees-init-and-host.md`。`loop/.doctor-acks.jsonl` 是普通文件、不算九本账之一，本节的总规矩（只增不改、锁、进 git、脏树白名单）不管它（2026-08-17 gyb 裁，sync-inbox 问题 24；它由 doctor 首次 `--ack` 时建、`rl init` 不建，见 `08` 第一节和 `05` doctor 一节）。」
- 原冻结句：`03-ledgers.md` L232「本份是定义处的东西：九本账公共骨架（七样加 `force_reason`、`via` 两个可选栏；`fix_for` 2026-08-17 问题 15 删）、总规矩（只增不改、按 `status` 查、写账的会话得活着、锁与写序、编号从 1 起四位起步、能写就能查、gyb 豁免只到权限层、`loop/` 进 git；`loop/.doctor-acks.jsonl` 不归总规矩管）、issues / runs / grants / feedback / evaluations / sessions / scratch 七本的字段级行格式、退出码六个（0/1/2/3/4/5）与非零退出的原因种类。别的 part 提到这些只指过来不抄；HANDOFF 四点五节标了「写了两遍」的几处（`09` 抄 issues/grants/feedback、`07` 抄 scratch、`04` 抄 sessions、`05` 抄锁与写序和退出码表）每次同步要和本份一字不差。」
- 原冻结句：`04-handoffs-and-sessions.md` L223「- 销号钩子挂在 SessionEnd 和 SubagentStop 上、登记钩子从钩子输入取 model、会话状态文件：钩子本体写在 `06-hooks-and-permissions.md`。」
- 备注：03 那一半有对应句子（第 9 行的普通文件句、第 232 行的总规矩汇总句）。04 那一半在现文里找不到写出路径的句子：04 只有第 223 行提到「会话状态文件」而不带路径，路径本身在 04 里从来没出现过（grep `CLAUDE_PLUGIN_DATA` 和 `loop/.sessions` 在 04 无命中，核对时重跑过一次，结果相同），所以 04 这一半按纯新增处理或者销掉。

### 35(f) 状态 settled

- 代码落点：`research-loop/hooks/`（hooks/hooks.json 加写权钩子脚本：钩子挂 Write、Edit、Bash 三个工具（Bash 那一支解析命令里的重定向、tee、sed -i、mv/cp 的写目标），仍然只拦两类路径（别的角色目录、直接写 loop/））；`research-loop/tests/`（测试 13（tests/test_skill_refs.py）三样都查，与 (b) 同一处）；`research-loop/tables/roles/<role>.json`（五栏 reads、writes、ledger_writes、dispatches_to、model 逐字照抄 06 第 172 到 234 行）
- 新口径：sync-inbox L195: (f) `05:233` 接口一节「钩子只挂 Write 和 Edit、只拦两类事」「`test_skill_refs` 只查写命令」同句连带改：钩子管 Write/Edit/Bash 三工具、`test_skill_refs` 三样都查，与 (a)(b) 同源（`06` 定稿）。
- 原冻结句：`05-rl-cli.md` L233「- 角色 json 的 `reads`、`writes`、`ledger_writes`、`dispatches_to`、`model` 五栏，钩子只挂 Write 和 Edit、只拦两类事，`test_skill_refs` 只查写命令，会话状态文件的路径：`06-hooks-and-permissions.md`。」
- 备注：三工具这一半在 01-gyb.md 第 159 行已经是新写法：「钩子挂 Write、Edit、Bash 三个工具、拦哪两类路径；Bash 那一支解析命令里的重定向、`tee`、`sed -i`、`mv`/`cp` 的写目标，解析不出目标路径的写法钩子不看、归纪律」。05 第 233 行是同一句里两处旧写法一起挂着，所以随 (a)(b) 一起改。

### 35(g) 状态 settled

- 代码落点：`research-loop/bin/rl`（doctor 扫描项的编号规矩：问题 43(a) 删掉的第 16 项留空号、后面的项不重排，(a) 新加的项接末尾编成第 20 项；引用按项号写的地方（05 第 237 行的 doctor 第 16 项、01 第 156 行的 doctor 第 19 项、30 第 225 行的十九项）不跟着漂）
- 新口径：sync-inbox L195: (g) 落 (a) 和问题 43(a) 时 doctor 项号规矩：删的留空号不重排、新加接末尾编号，既有按项号写的引用（`05:237`、`01:156`、`30:225` 这类）不跟着漂（HANDOFF 第五节 2026-08-21 记）。
- 原冻结句：`05-rl-cli.md` L237「- `read:notes` 的申请走法（`rl init` 问的那一次和 doctor 第 16 项）：`10-role-idea.md`。」
- 原冻结句：`01-gyb.md` L156「- grants、feedback、evaluations、sessions 四本账的行格式和状态取值在 `03-ledgers.md`；本文只写 gyb 这一头的动作。sessions 的 `amend` 版（只许改 `model`，是 doctor 第 19 项 `model=unknown` 的修法，2026-08-21 gyb 确认走这条路、不加新机制）在 `04-handoffs-and-sessions.md` 第七节，命令签名 `rl session amend ID --model M` 在 `05-rl-cli.md`。」
- 原冻结句：`30-build-steps-verify-tests.md` L225「1. doctor 十九项只有第 3 项（经测试 6）和第 19 项（经测试 18）有对应的测试用例，其余十七项各造一条脏账、跑修法命令、再扫零报告，第十节没有这一条测试。」
- 原冻结句：`HANDOFF.md` L124「doctor 扫描项的项号规矩照 rule-NN 的办法：删的留空号、新加往后排，免得按项号写的引用全漂。」
- 备注：规矩本身在 HANDOFF.md 第五节第 124 行（已抄进 frozen_original），照的是 09 第 49 行 rule-NN 的编号规矩（废掉留空号不补位、新加往后排）。列出的三条冻结原句是「既有按项号写的引用」，抄来核对项号有没有漂。三处现文行号核过都没漂：05:237 是 doctor 第 16 项，01:156 是 doctor 第 19 项，30:225 是 doctor 十九项。问题 43(a)（sync-inbox L311）删的是「决定来源指向 notes/ 但 grants 查不到 `read:notes`」，对应 05 第 210 行的第 16 项，所以 05:237 引的第 16 项删后变成空号、引用照旧。授权来源是 sync-inbox L195 的「统筹补扫 2026-08-21（评审修复，gyb 授权）」加 HANDOFF 第五节 2026-08-21 的记录。

读手没能定的：无。读手留的两条都按原文判定了，写在 (a) 和 (c) 的 note 里：(a) 的阈值——08 第三节阈值表没有键，代码硬编码一天并标 PENDING(part 08 L57)；(a) 的测试——测试 6 只覆盖第 3 项、测试 18 只覆盖第 19 项，第 20 项没有用例；(c) 的位置——04 第 122 行的清单是逐张单子做的四件事，删状态文件是每个会话一次，接在清单外面、第 4 条之后第 129 行兜底段之前，作为会话层最后一步、在 sessions 账结束版之后。

核手的话：核对方法：sync-inbox L186-199、05 第 12-17/97-102/188-240 行、03 第 7-10/229-242 行、04 第 112-135/219-226 行、01 第 154-160 行、30 第 27-86/173-183/222-227 行、08 第 55-82 行、06 第 35/102/116-126/160-175/252-262/278/441-478 行、HANDOFF 第 116-126 行、research-loop/README.md 全文、research-loop/tables/ledgers.json 第 90-107 行都用 Read 或 grep 亲眼读过。结果：七个子项的 new_wording 都是 sync-inbox L194/L195 的逐字截段，没改；读手抄的 15 条 frozen_original 引文与行号全部与现文逐字一致，没改。改动 11 处：(1) (a) landing 第 2 条 tables/ledgers.json 的行号 103 改 94——plain_files 三条在现文第 92 到 94 行，loop/.sessions/ 是第 94 行，_source 栏实际写的是「06 L118; 08 L18; sync-inbox Q35(e) L194」，一并照抄；(2) (d) landing 第 3 条同一处行号 103 改 94；(3) (e) landing 第 1 条「第 101 到 103 行」改「第 92 到 94 行」；(4) (a) frozen_original 补 06 第 120 行——子项点名的「sessions 账已销号或超过一天没动」这句的定义处，读手只在 note 里引了 06 第 476 行的同步清单；(5) (b) frozen_original 补 06 第 35 行——子项点名的「`06`「三样都查」」原句，读手没抄；(6) (d) frozen_original 补 06 第 118 行——子项点名的「`06` 追裁」把路径改成 loop/.sessions/<session_id>.json 的定义句，读手只引了 01 第 158 行的转述处；(7) (g) frozen_original 补 HANDOFF.md 第 124 行——子项点名的「HANDOFF 第五节 2026-08-21 记」的原句，第 124 行在第五节（第 116 到 125 行）内；(8) (a) note 与 bin/rl landing 补阈值判定：08 第三节阈值表第 61 到 79 行十七个键没有会话状态文件陈旧阈值，按核对指令写「阈值表没有键，代码硬编码一天并标 PENDING(part 08 L57)」，不加 config_defaults.json 落点；同时补测试判定：测试 6 用例只覆盖 doctor 第 3 项、测试 18 只覆盖第 19 项，第 20 项没有用例；(9) (c) landing 第 1 条与 note 补位置判定：04 第 122 行原文是「对每一张做四件事」且只在有开干单子时做，删状态文件是每会话一次，所以放清单外面、第 4 条之后第 129 行之前，会话层最后一步、在 sessions 账结束版之后，理由是 rl 判 actor 靠这个文件（05 第 15-17 行）而销号顺带写的账行要记会话角色（05 第 29 行、04 第 124 行）；(10) (c) landing 第 2 条标明 30 测试 7 现文「要加的」清单（第 80 到 86 行）里没有这条用例、施工时补；(11) unresolved 两条判定完清空。另外 (d) note 补了一句：05 第 15 行「状态文件由角色 skill 头部钩子在加载的时候写」与 06 第 102 行「插件级钩子文件里的一条钩子写、skill 头部不声明钩子」不一致，和 (f) 同源，算进 (d) 的改法不另立子项。status 与 pending_ref 七项都核过：sub 正文没有「请统筹问 gyb」「归 05 定」「由 gyb 定」「由 gyb 过目」「等待验证第 N 条」字样，L196 的「等最后一期」管的是冻结分册的文字、代码以 06 定稿为准，七项保持 settled。landing 路径七个子项全在清单内且与 README 目录表相符（bin/rl、tables/ledgers.json、tables/roles/<role>.json、skills/<role>/SKILL.md、hooks/、tests/、scripts/rl_lib.py），没改。

## 问题 37（sync-inbox L227-232，核手核过）

### 37(a) 状态 pending，标记 `PENDING(issue 37a)`

- 代码落点：`research-loop/bin/rl`（子命令 `decision retire`：签名从 `rl decision retire ID [--source ...]` 改成带必填理由项，按 `update` 类推写成 `--text`；缺 `--text` 拒收）；`research-loop/scripts/rl_lib.py`（废除版入账校验：`retired` 那一版 `text` 必填，正文就是废除理由（问题 36 裁 c）；不新加栏、不复用 `force_reason`）；`research-loop/schemas/decisions.schema.json`（decisions 行格式：`status`/`op` 是 `retired` 的那一版 `text` 必填，注一句「废除版的正文是废除理由」）；`research-loop/tests/`（测试 3（决定来源）：加一例 `retire` 不给理由拒收、给了理由落进那一版 `text`；这条测试原来已有「`retire` 同样打印受影响的单子」）
- 新口径：sync-inbox L231: （a）`05` `rl decision retire ID [--source ...]` 签名加理由项（必填；问题 36 已裁 c：理由就是废除版的正文 `text`，签名照 `update` 那样带 `--text`——旗子名是统筹按 `update` 类推的写法，最后一期改 `05` 时由 gyb 过目）
- 原冻结句：`05-rl-cli.md` L49「| `rl decision retire ID [--source ...]` / `rl decision merge ID1 ID2 ... --text --root ID [--source ...]` | 废除；合并成新决定，被合并编号自动进 sources 和 merged_from，旧的各追加一版 `retired`；retire 同样列受影响的单子 | 同 actor |」
- 原冻结句：`05-rl-cli.md` L48「`rl decision update ID --text [--source ...] [--quote ...]`」
- 备注：理由必填、理由就是废除版正文 `text` 这两件事已裁（问题 36 答 c，sync-inbox L222-225，`02` 已落地）；卡住的只有旗子名——`--text` 是统筹按 `update` 类推写的，sync-inbox 明写「最后一期改 `05` 时由 gyb 过目」。今天照 `--text` 写、代码里标 PENDING 指回 37(a) 即可，旗子名改了只改一处签名。类推的样板是 05 L48 `update` 的签名（已抄进原冻结句）。

### 37(b) 状态 settled

- 代码落点：`research-loop/bin/rl`（子命令 `feedback accept`：四件事之一改成「自动把 `rules_version` 加一并写回 `common/GLOBAL-RULES.md` 头部那一行」（定义处 09 L87））；`research-loop/scripts/rl_lib.py`（读写母版头部 `rules_version` 那一行的函数：整数、从 1 起、那一行是唯一真源；这是 rl 唯一一处往母版文件写字的动作（09 L59），母版正文仍人手改）；`research-loop/common/GLOBAL-RULES.md`（头部一行带 `rules_version`（整数），格式要能被 rl 定位并原地加一）；`research-loop/schemas/feedback.schema.json`（`rules_version_after` 采纳时 rl 自动填，取值是加一之后的那个整数）；`research-loop/tests/`（测试 17（feedback）：30 第 171 行已把这一句写进「要加的」——accept 把 `rules_version` 加一并写回 `common/GLOBAL-RULES.md` 头部那一行）
- 新口径：sync-inbox L231: （b）`05` `rl feedback accept` 那句「自动把 `rules_version` 加一」补「并写回 `common/GLOBAL-RULES.md` 头部那一行」
- 原冻结句：`05-rl-cli.md` L80「| `rl feedback add --target ... --text` / `rl feedback accept ID --applied-to FILE ... --text ...` / `rl feedback reject ID --text` / `rl feedback show ID` / `rl feedback list` | 反馈账；accept 校验路径存在、自动 bump `rules_version`、列出还活着的会话和它们的 rules_version、打印待办（还要改哪几处、要不要收会话、单独 commit 加跑测试） | 提谁都行，裁只有 gyb，查谁都行 |」
- 原冻结句：`05-rl-cli.md` L236「- `rl feedback accept` 的 `rules_version` 和母版改动的规矩、公共规矩八条、issues 九种 kind、判断类检查的问题清单文件（本份裁：放 `common/`）：`09-common-and-feedback.md`。」
- 备注：依据是 09 第七问 gyb 答「a」（sync-inbox L206 第 7 条、09 L376），非冻结的 30 测试 17 已同步。

### 37(c) 状态 pending，标记 `PENDING(issue 43c)`

- 代码落点：`research-loop/tables/ledgers.json`（grants 那一行留位不建立，标 PENDING(问题 43c)：不写 `rl grant` 子命令、不写 schema，撤销时列活会话这条也一并挂在这一行的 pending 说明里）
- 新口径：sync-inbox L231: （c）`05` `rl grant revoke` 一节补「列出 grantee 还活着的会话和各自加载时间，让 gyb 挑要不要收，不自动收」
- 原冻结句：`05-rl-cli.md` L79「| `rl grant add --to R --permission P --text ... [--expires ...] [--issue ID]` / `rl grant revoke ID` / `rl grant list` / `rl grant show ID` | 授权；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收（问题 27） | 写 gyb，查谁都行 |」
- 备注：内容本身已裁（09 第八问 gyb 答「a」，sync-inbox L206 第 8 条），卡的是 grants 账存废：代裁 D-01 今天 grants 留位不建立，落点只到 `tables/ledgers.json`。43(c) 裁「留」之后真正的落点是 `research-loop/bin/rl` 的 `grant revoke` 子命令加这段输出。05 里没有独立的「`rl grant revoke` 一节」，全份只有命令表第 79 行这一处（第 75 行小节标题是「授权、反馈、口径」）。

### 37(d) 状态 settled

- 代码落点：`research-loop/bin/rl`（子命令 `doctor`：末段说明与输出里的「问题清单写成一份文件放 `common/`」写成文件名 `common/REVIEW-CHECKLIST.md`）；`research-loop/common/REVIEW-CHECKLIST.md`（判断类检查的问题清单文件本身（09 L17 定的名字），doctor 末段指到它）
- 新口径：sync-inbox L231: （d）`05` doctor 一节末段「判断类检查的问题清单」可带文件名 `common/REVIEW-CHECKLIST.md`
- 原冻结句：`05-rl-cli.md` L221「doctor 只做脚本能判的检查，也就是上面十九项。判断类的检查（比如「这张单的报告有没有回答它引的决定」「这条 run 的 config 和发射单写的一不一样」）不在 doctor 里：问题清单写成一份文件放 `common/`，由 reviewer 角色派 sonnet subagent 一人领一题逐条查，查出来的写进 review/ 清单，要不要开 issue 由 gyb 看完用自己的权限开（2026-08-17 gyb 裁，问题 6 后改：只写清单不开 issue；见 09-common-and-feedback.md 和 14-role-reviewer.md）。」
- 备注：依据是 09 第九问 gyb 答「a」（sync-inbox L206 第 9 条、09 L378）。同一句在非冻结的 08、14、30 步 5 已经同步（sync-inbox L211-213）。这一笔只改文件名，doctor 的十九项扫描不动。

### 37(e) 状态 pending，标记 `PENDING(issue 43c)`

- 代码落点：`research-loop/tables/ledgers.json`（grants 那一行留位不建立，标 PENDING(问题 43c)：`status` 只留 `active`、`revoked` 两个值，撤销后处置两句一并挂在这一行的 pending 说明里）
- 新口径：sync-inbox L231: （e）`03` grants 段（与 `09` 第七节写了两遍）加「撤销时刻之后再读算越权，reviewer 按时间戳查；撤销时 rl 列出还活着的会话让 gyb 挑」
- 原冻结句：`03-ledgers.md` L128「授权只有 gyb 能写：`actor` 必须是 `gyb`。裸终端直接写；角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话（2026-08-17 gyb 裁，sync-inbox 问题 27，原话「3 不是，可以替我写」；施工计划第一节 (d)「grants 只收裸终端」不认）。`status` 取 `active`、`revoked`。」
- 备注：内容已裁（09 第八问答「a」，定义处 09 L133）。卡的同样是 grants 账存废（代裁 D-01），今天落点只到 `tables/ledgers.json`。43(c) 裁「留」之后，两句会分别落到 `research-loop/schemas/grants.schema.json`（撤销版的时间戳）、`research-loop/bin/rl` 的 `grant revoke`（列活会话）和 `research-loop/common/REVIEW-CHECKLIST.md`（reviewer 按时间戳查越权读，属判断类检查、不进 doctor）。

### 37(f) 状态 settled

- 代码落点：`research-loop/schemas/feedback.schema.json`（`target` 只收两种取值（仓库内文件路径，或带前缀编号 `rule-NN`/`principle-NN`）；要改的是某张表的某一行时 `target` 填那张表所在文件的路径、哪一行写进 `text`；`status` 三值里 `accepted` 和 `rejected` 都是终态（定义处 09 L73）；`rules_version_after` 是整数）；`research-loop/scripts/rl_lib.py`（feedback 入账校验：`target` 按上面两种取值判；`accepted`、`rejected` 之后同一条不再收新版本（没有改一版的子命令，再提走 `rl feedback add` 开新一条，rl 不建链））；`research-loop/bin/rl`（子命令 `feedback add`（`--target` 的取值校验与提示）和 `feedback reject`（写完提示再提要开新一条））；`research-loop/tables/ledgers.json`（feedback 那一行的 `status_values` 已是 proposed/accepted/rejected，补记 `accepted`、`rejected` 是终态（09 L73））；`research-loop/tests/`（测试 17（feedback）：加 `target` 两种取值的正反例、表的某一行走「路径进 target、行号进 text」、`rejected` 之后再写同一条拒收）
- 新口径：sync-inbox L231: （f）`03` feedback 段 `target` 那句加「表的某一行填那张表所在文件的路径，哪一行写进 `text`」、`status` 那句加「`rejected` 是终态，再提开新一条」、`rules_version` 可注「整数」
- 原冻结句：`03-ledgers.md` L141「反馈账谁都能提、只有 gyb 能裁、谁都能读。提的那一版 `actor` 谁都能写，裁的那一版 `actor` 必须是 `gyb`。`status` 取 `proposed`、`accepted`、`rejected`。」
- 原冻结句：`03-ledgers.md` L146「| `target` | 文件路径，或带前缀的编号 `rule-06`、`principle-06` | 必填 |」
- 原冻结句：`03-ledgers.md` L150「| `rules_version_after` | 母版版本 | 采纳时 rl 自动填 |」
- 备注：依据是 09 第四、五、七问 gyb 全答「a」（sync-inbox L206 第 4、5、7 条），定义处原文在 09 L73。「`rules_version` 可注整数」在 03 feedback 段（L139-152）指的是 L150 那一栏，现文栏名是 `rules_version_after`（feedback 段里没有叫 `rules_version` 的栏）；sessions 段 L184 的 `rules_version` 栏归 (g1) 管，那边的 schema 也写整数，两处都落整数、不另立一笔。口径差核过：09 L73 现文是「`accepted` 和 `rejected` 都是终态」，sync-inbox (f) 只点 `rejected`；schema 按定义处 09 L73 两个终态写。

### 37(g1) 状态 settled

- 代码落点：`research-loop/scripts/rl_lib.py`（`rl session start` 落开始版时，`rules_version` 从 `common/GLOBAL-RULES.md` 头部那一行读（整数），钩子不传这个值（05 L40「`start` 的 `rules_version` 由 rl 从母版读」，09 L59「会话账的开始版就从这一行读」））；`research-loop/bin/rl`（子命令 `session start`：`rules_version` 不做参数、由 rl 读母版（05 L40 签名里没有这个参数））；`research-loop/schemas/sessions.schema.json`（`rules_version` 必填、整数，取值来源写成母版头部那一行（03 L184 是行格式定义处，04 L141 与它一字不差））；`research-loop/common/GLOBAL-RULES.md`（头部那一行是唯一真源，会话开始版从这里读）；`research-loop/tests/`（测试 17（feedback）原文已有「sessions 开始版记 rules_version」，补一例：改母版头部那一行之后新开会话记的是新值）
- 新口径：sync-inbox L231: （g）`04` sessions 账开始版 `rules_version` 补「从 `common/GLOBAL-RULES.md` 头部那一行读」
- 原冻结句：`04-handoffs-and-sessions.md` L141「| `rules_version` | 母版版本 | 必填 |」
- 原冻结句：`04-handoffs-and-sessions.md` L160「母版版本这条链跟 sessions 有关：母版带一个 `rules_version`，会话开始版记下它，feedback 采纳的时候 rl 列出还活着的会话让 gyb 挑要不要收；母版改动在下次加载角色时生效，正在跑的会话不追、不通知，按现行母版干到底。反馈账本身在 `09-common-and-feedback.md`。」
- 原冻结句：`03-ledgers.md` L184「| `rules_version` | 母版版本 | 必填 |」
- 原冻结句：`05-rl-cli.md` L40「`start` 的 `rules_version` 由 rl 从母版读」
- 备注：已裁（09 第七问答「a」，09 L376；09 L154 是定义处指向、09 L59 是定义处原句），今天就能写代码。sessions 开始版由钩子代角色写（03 L176、04 L133），但钩子只调 `rl session start`、不算这一笔的改动落点，故不列 hooks/。

### 37(g2) 状态 pending，标记 `PENDING(issue 43c)`

- 代码落点：`research-loop/tables/ledgers.json`（挂 grants 那一行的 PENDING(问题 43c) 说明：`rl grant revoke` 列会话之后收会话走 `rl session end --session ID`（09 L133）；`rl session end` 本身不改）
- 新口径：sync-inbox L231: `rl grant revoke` 列会话之后收会话走 `rl session end`。
- 原冻结句：`04-handoffs-and-sessions.md` L158「谁能调：start 和 end 是钩子和 gyb，amend 是 gyb 或该角色的活会话，focus 是 reviewer，查询谁都行。」
- 原冻结句：`04-handoffs-and-sessions.md` L152「`--session ID` 给 gyb 关别的会话。gyb 用 `--session ID` 关别的会话时 rl 不拦、不查那个会话活没活着（rl 看不见进程，只看得见账），照样销号，`end_reason` 记 `manual`」
- 备注：grants 相关，按代裁 D-01 落 `tables/ledgers.json` 标 pending。43(c) 裁「留」之后它只是 04 第七节「谁能调 session end」那句（L158）加一条引用（09 L399 原话「只是引用，那边若有「谁会调 session end」的清单可加一条」），`rl session end --session ID` 的签名与行为（04 L152）不动。

核手的话：改了 7 处。一、(a) 原冻结句补 05 L48 `update` 签名的一段：子项明写「签名照 `update` 那样带 `--text`」，类推的样板要有原句可查。二、(f) 读手的 unresolved 第一条按现文定死：sync-inbox L231 (f) 挂在「`03` feedback 段」下，03 feedback 段（L139-152）里带 `rules_version` 字样的只有 L150 `rules_version_after` 一栏，读手抄的 L150 就是它，note 里写明；sessions 段 L184 的 `rules_version` 栏划给 (g1)，两处 schema 都写整数。三、(f) 口径差核过：09 L73 现文是「`accepted` 和 `rejected` 都是终态：被打回之后要再提就 `rl feedback add` 开新一条」，属实，(f) note 加「schema 按定义处 09 L73 两个终态写」，feedback.schema.json、rl_lib.py、ledgers.json 三个落点的 what 同步改成两个终态。四、(g) 拆成 (g1)(g2)：(g1) sessions 开始版 `rules_version` 从母版头部那一行读，settled、无 pending_ref，落点 rl_lib.py（读的动作，05 L40「由 rl 从母版读」）加 sessions.schema.json（整数）；(g2) `rl grant revoke` 列会话之后收会话走 `rl session end`，pending、`issue 43c`，落点只有 tables/ledgers.json（代裁 D-01）。读手原来塞在 (g) bin/rl 落点里的「`session end`（含 `--session ID`）是 gyb 收会话的动作」移到 (g2)。五、(g1) 原冻结句补 03 L184（sessions 行格式定义处，04 L133 明写「下表与那里一字不差」）和 05 L40 一段（「`start` 的 `rules_version` 由 rl 从母版读」）。六、(g2) 原冻结句补 04 L152 一段（`--session ID` 给 gyb 关别的会话）。七、读手 unresolved 三条全部定掉：第一条见二，第二条 (a) pending_ref 就用 `issue 37a`（与 research-loop/README.md 的 PENDING(issue NN) 写法一致），第三条见四；unresolved 清空。核过没改的：(a)(b)(c)(d)(e)(f) 六条 new_wording 与 sync-inbox L231 逐字相符；05 L49/L80/L236/L79/L221、03 L128/L141/L146/L150、04 L141/L160/L158 十二处原句与现文逐字相符、行号相符；(c) note 说 05 里 `grant revoke` 只在 L79 一处，grep 属实；所有落点路径都在清单内；D-01 原文核过（`tables/ledgers.json` 保留 grants 行标 PENDING(问题 43c)，不写 schema、不写 `rl grant` 子命令）。

## 问题 39（sync-inbox L248-254，核手核过）

### 39(a1) 状态 settled

- 代码落点：`research-loop/agents/<role>.md`（五份角色 agent 定义就是「插件的角色 agent 类型」本体（08 L90、06 L126：「派活一律用这五个类型起 subagent，钩子输入的 `agent_type` 就是这么来的」）；`dispatch=auto` 起 subagent 时 subagent_type 取这五个文件名，agent 定义预加载本角色 skill、收窄工具面、不写钩子）；`research-loop/tables/transitions.json`（（新建）→`todo` 行（04 L61）和 `in_progress`→`todo` 行（04 L75）的「之后谁拉起」栏：`auto` 起 subagent 那句写明用插件的角色 agent 类型，不用 general-purpose；`reissue` 行（04 L76）「同新建」跟着）；`research-loop/skills/<role>/SKILL.md`（五份角色说明书里 owner 派活那一段（04 第四节的副本），起 subagent 时点名角色 agent 类型；08 L331 记 2026-08-18 已给 `10`–`14` 五份各加一句「被派活时以插件角色 agent 类型起 subagent，agent 定义预加载本角色 skill」、类型名照 `agents/<role>.md` 的文件名，SKILL.md 照 10 到 14 抄）
- 新口径：sync-inbox L252: （a）`04` `dispatch=auto` 起 subagent 时用插件的角色 agent 类型（`agents/<role>.md`），不用 general-purpose
- 原冻结句：`04-handoffs-and-sessions.md` L84「`dispatch` 是单子上的一个字段，三个取值：`auto`（owner 后台起 subagent）、`manual`（gyb 亲自接）、`none`（暂不派）。」
- 原冻结句：`04-handoffs-and-sessions.md` L86「`auto` 是默认。上游开完单后台起 subagent 接走，上游会话继续可用，subagent 回来时上游验收；上游会话先结束了，单子照常在账上等 owner 下次上线或 gyb 验收。这就是原则 11「派活不占终端」，它取代了原来「subagent 接单默认同步」那一句。」
- 原冻结句：`04-handoffs-and-sessions.md` L61「`dispatch=auto` 时 owner 后台起 subagent；`manual` 等 gyb；`none` 不动」
- 原冻结句：`04-handoffs-and-sessions.md` L75「owner 照单子原来的 `dispatch` 拉起（`auto` 再起一个 subagent），owner 无活会话时进 `rl status` 的「等 gyb 拉起」」
- 原冻结句：`04-handoffs-and-sessions.md` L96「外部原因（上下文满、进程被杀、终端没了）就照单子的 `dispatch` 走，`auto` 的当场再起一个 subagent 接」
- 备注：裁决原文见 sync-inbox L250「gyb 2026-08-18 对 08「定死吧」「A A A」「剩下的建议我确认」」；agents/ 层五份角色 agent 定义由 08 第四节 L90 立，06 L126 写「派活一律用这五个类型起 subagent」，问题 38-2（sync-inbox L245-246）已裁它改动走母版流程。装 agent 类型定义的文件 research-loop/agents/<role>.md 在落点清单里（统筹 2026-09-05 补进清单），列为第一个落点。

### 39(a2) 状态 settled（2026-09-05 待验证第 5 条测完，代裁 D-15；代码里的来源标注写 `proxy decision D-15`，原读手记的是 pending、标记 verify 5）

- 代码落点：`research-loop/hooks/`（登记钩子（session registration hook）：subagent 加载角色 skill 时登不登记一行 sessions、`session_id` 填父会话号还是另立标识；钩子输入里的 `agent_id`/`agent_type` 怎么用。标 PENDING(verify 5)）；`research-loop/schemas/sessions.schema.json`（`session_id` 栏的语义：父子会话同号时主键怎么算，要不要另加一栏区分 subagent；`launched_by` 取值 `subagent` 那一档（04 L140）要不要保留。标 PENDING(verify 5)）；`research-loop/scripts/rl_lib.py`（actor 判定的子会话分支（状态文件读到父会话的角色对不对、要不要另立信号）；工作指南第 92 行写明这一分支等第 5 条）；`research-loop/tests/`（测试 7（销号，30 L76-86）与测试 8（钩子，30 L88-92）：subagent 登记与销号的用例等第 5 条测完才写得成）
- 新口径：sync-inbox L252: 第四节「subagent 加载角色 skill 那一刻和普通 session 一样登记进 sessions 账」那句——subagent 的 `session_id` 与父会话相同、钩子输入多 `agent_id`/`agent_type`、状态文件不写，subagent 算不算一次 sessions 行、`session_id` 记什么，等待验证第 5 条测完再定
- 原冻结句：`04-handoffs-and-sessions.md` L94「一是登记。subagent 加载角色 skill 那一刻和普通 session 一样登记进 sessions 账。」
- 原冻结句：`04-handoffs-and-sessions.md` L118「加载 skill 把角色分配给会话的那一刻算会话开始。钩子看得见这次加载，自动登记进 sessions 账，钩子代角色写，actor 填角色。」
- 原冻结句：`04-handoffs-and-sessions.md` L137「| `session_id` | 会话 id | 主键 |」
- 原冻结句：`04-handoffs-and-sessions.md` L140「| `launched_by` | `manual`、`subagent`、`workflow` | 必填 |」
- 原冻结句：`04-handoffs-and-sessions.md` L230「待验证第 5 条（SessionEnd 和 SubagentStop 在 subagent 上触不触发）、第 8 条（subagent 里加载角色 skill 钩子装不装得上）、第 9 条（后台 subagent 能不能跑几个小时、父会话结束会不会被杀）、第 10 条（钩子输入里有没有模型标识）：写在 `30-build-steps-verify-tests.md`；这四条不成立会改掉本份第四、六、七节的写法。」
- 备注：统筹补扫 sync-inbox L253 原句：「统筹补扫 2026-08-21（评审修复，gyb 授权）：(a) 后半（subagent 算不算一次 sessions 行、`session_id` 记什么）依赖待验证第 5 条，最后一期时还没测完就明记挂起，别硬落。」30 第 17 行待验证第 5 条：「SessionEnd 和 SubagentStop 在 subagent 结束时触发不触发、会话 id 是不是同一个」，状态栏「待测；不成立会改 `04` 第六、七节和 `12` 的走法」，2026-08-21 补注把 subagent 场景 rl 判 actor 的口子一起挂在这条上，测完由 04 定。06 L112「subagent（`agent_type` 非空）算不算一次 sessions 行、`session_id` 记什么（它和父会话相同），等待验证第 5 条测完由 `04` 定，本份只记事实」与 06 L118（subagent 不写状态文件、`session_id` 与父会话相同，同挂第 5 条）是同一条挂起的另两处。04 L140 sessions 行格式里 `launched_by` 已有 `subagent` 一档，说明冻结正文默认 subagent 有一行，第 5 条测出不登记时这一档跟着改。

### 39(b1) 状态 settled

- 代码落点：`research-loop/bin/rl`（`init` 子命令：重跑时已填过的项不再问、已建的不重建（无副作用，08 L36「重跑 init 时已经填过的项不再问」）；配置逐项问（08 L17、L40 表「init 问」栏）；只在研究仓库里建树，不动宿主代码和仓库 `.claude/`（08 L13））；`research-loop/skills/research-loop/SKILL.md`（入口 skill 的 init 领路那一段（工作指南 L102「入口 skill：init、迁移提醒、领路五条」，08 第五节），三句一起写进去）；`research-loop/tests/`（测试 12 端到端（30 L132-136，沙盒仓库 `rl init` 建树、裸终端跑）、测试 9（30 L103「`rl init` 在角色会话里跑退出码 3」））
- 新口径：sync-inbox L252: （b）`05` `rl init` 一行补「重跑无副作用；逐项问配置；不动宿主代码和仓库 `.claude/`」
- 原冻结句：`05-rl-cli.md` L39「| `rl init` | 在研究仓库建 `research-loop.json`、`loop/` 九本账、`experiments/`、`analysis/`（含公共统计件模板和 `analysis/scratch/`）、`review/`、`notes/`，往 CLAUDE.md 追加一节（三句），问一次要不要给 idea 发 `read:notes`；读到会话状态文件就拒收，退出码 3，提示换裸终端跑 | gyb，只在裸终端 |」
- 原冻结句：`05-rl-cli.md` L235「- `rl init` 建的六样加一节、`research-loop.json` 阈值表」
- 备注：05 L39 那一行里「问一次要不要给 idea 发 `read:notes`」已被 08 第一节 L36 砍掉（获准机制 2026-08-21 砍，08 裁决记录 L309），改这一行时连带。「重跑无副作用」没有用例：30 第二节 L29-184 里 `rl init` 只出现在测试 9（L103，角色会话里退出码 3）、测试 12（L134、L136，沙盒建树、裸终端跑）、测试 19（L179，不建 `.doctor-acks.jsonl`），没有一条重跑 init，工作指南 L108 把它列在查漏补的六条里。research-loop/skills/research-loop/ 是入口 skill 不是角色 skill，路径形状借用 skills/<role>/SKILL.md 这一条，工作指南 L102 与 08 L89（六个 skill：入口一个，五个角色各一个）都指到这个目录。

### 39(b2) 状态 settled

- 代码落点：`research-loop/bin/rl`（`run finish` 子命令与 `reclaim --kill` 的中断收尾：四步（杀进程、释放显存、宿主销号、runs 落 `killed`）里「宿主销号」那一步调 `launcher.abort_cmd`，键留空就跳过这一步、不报错）；`research-loop/scripts/rl_lib.py`（读 `research-loop.json` 的 `launcher.*` 四条模板并执行，留空一律跳过不报错（08 第二节 L51、L55））；`research-loop/tests/`（测试 11（30 L120-130，reclaim 开干的发射单默认不杀、`--kill` 才杀））
- 新口径：sync-inbox L252: `rl run finish` 一节补「中断收尾里宿主销号调 `launcher.abort_cmd`，留空跳过」
- 原冻结句：`05-rl-cli.md` L73「`finish` 算 actual_seconds、同进程跑反常预警、调宿主收尾命令模板」
- 原冻结句：`05-rl-cli.md` L179「- 开干的发射单：默认不杀进程，留给下一个 run 认领；带 `--kill` 才走中断收尾，也就是杀进程、释放显存、宿主销号、runs 落 `killed`。」
- 原冻结句：`05-rl-cli.md` L235「宿主发射器的命令模板（`launcher.free_cmd`、`launcher.launch_cmd`、`launcher.finish_cmd`）、`rl run finish` 调哪条宿主命令：`08-trees-init-and-host.md`。」
- 备注：`launcher.abort_cmd` 的定义处是 08 第二节 L51，new1 填 `run.py gpu-jobs finish`；「宿主没有这条命令的仓库留空，留空就跳过这一步（2026-08-18 gyb 裁，四条模板各一个键）」；08 L55「`launcher.*` 四条模板留空的含义都一样：这个宿主没有这一步，rl 调到这里就跳过、不报错」；08 L146 宿主对接一节同句。05 现文没有叫「rl run finish」的小节，命令表 L73 那一行是唯一落笔处；05 现文只列了三条模板，缺 abort_cmd（与 (b4) 同一处漏项），键本身的声明随 (b4) 落进 tables/config_defaults.json（v2 树该文件 L11 已记 `launcher.abort_cmd`，default null，「empty means the step is skipped」，_source 08 L51）。

### 39(b3) 状态 settled

- 代码落点：`research-loop/bin/rl`（`doctor` 第 18 项：宿主 runs 账的路径不写死 `ops/runs.jsonl`，从配置 `host_ledgers` 里找 `kind` 是 `runs` 的那一项）；`research-loop/scripts/rl_lib.py`（配置读取：解析 `host_ledgers` 列表的 `path`/`note`/`kind` 三栏，机器只解析 `kind`，按 `kind: runs` 取宿主 runs 账路径）
- 新口径：sync-inbox L252: doctor「两本 runs 账对账」按 `host_ledgers` 里 `kind: runs` 找宿主账
- 原冻结句：`05-rl-cli.md` L212「| 18 | loop/runs.jsonl 与宿主 ops/runs.jsonl 对不上的 run_id | 只报不修：列出两边各有没有 | run |」
- 备注：`host_ledgers` 的定义处是 08 第二节 L53，原句已写明「`kind`（只有宿主 runs 账那一项填 `runs`，doctor 对账时按这个标记找宿主 runs 账；其余项留空）」；08 L150 宿主对接一节同句。「两本 runs 账对账」是 08 L180 接口一节给 doctor 第 18 项起的叫法，05 现文里没有这四个字，第 18 项在 05 L212。doctor 第 18 项没有用例：30 第二节 L29-184 里碰 doctor 的只有测试 6（L70-74，第 3 项）、测试 11（L129，`rl doctor --json` 最小结构）、测试 18（L175，第 19 项 amend 后不再报）、测试 19（L177-179，第 6 项的 ack/unack），没有一条对两本 runs 账。

### 39(b4) 状态 settled

- 代码落点：`research-loop/tables/config_defaults.json`（08 第二节配置键的机器读副本，三个键各一行：`launcher.abort_cmd`（模板，default 空，留空跳过）、`repo_run`（固定三栏 `env`/`entry`/`notes`）、`host_ledgers`（列表，每项 `path`/`note`/`kind`），三项「init 问」栏都是 ✓）；`research-loop/scripts/rl_lib.py`（配置读取认这三个键：`launcher.abort_cmd`（模板，留空跳过）、`repo_run`（固定三栏 `env`/`entry`/`notes`，机器不解析）、`host_ledgers`（列表，每项 `path`/`note`/`kind`，机器只解析 `kind`））；`research-loop/bin/rl`（`init` 逐项问这三个键（08 第二节表里三项「init 问」栏都标 ✓））
- 新口径：sync-inbox L252: 接口一节 `08` 那条键清单加 `launcher.abort_cmd`、`repo_run`、`host_ledgers`
- 原冻结句：`05-rl-cli.md` L235「- `rl init` 建的六样加一节、`research-loop.json` 阈值表（本份用到 `issues.gyb_stale_hours`、`issues.answered_stale_days`、`status.stale_holder_minutes`、`status.review_recent_days`、`reclaim.*`、`notify.reminder_days`、`quick_lane.worktree_root`，新加 `lock.timeout_seconds` 默认 10 秒）、宿主发射器的命令模板（`launcher.free_cmd`、`launcher.launch_cmd`、`launcher.finish_cmd`）、`rl run finish` 调哪条宿主命令：`08-trees-init-and-host.md`。`rl init` 在角色会话里拒收退出码 3，已收（08 第一节）。」
- 备注：三个键在 08 第二节 L51、L52、L53 逐条核过：`launcher.abort_cmd`（第 51 行）、`repo_run`（第 52 行）、`host_ledgers`（第 53 行），三项 init 问栏都是 ✓；08 L177 接口一节明写「`research-loop.json` 的全部键（含 `launcher.abort_cmd`、`repo_run`、`host_ledgers`，2026-08-18 加）」。本子项改的是 05 接口一节的转指清单，键本身的定义处在 08，机器读副本是 tables/config_defaults.json（v2 树该文件 L11-13 已记这三个键，_source 各标 08 L51/L52/L53）。同一处 L235 还挂着已被问题 40 砍掉的 `notify.reminder_days`（见 sync-inbox L260-264，对照单 40(f)），改这一行时会撞上。

### 39(c) 状态 settled

- 代码落点：`research-loop/tables/ledgers.json`（九本账的名字和文件名（工作指南 L87 指到 03 第 47 到 57 行）：文件名钉死在 `loop/` 下，表里带上「位置钉死，配置里没有账路径」这条旁注）；`research-loop/scripts/rl_lib.py`（账路径一律从 `tables/ledgers.json` 解析，不从 `research-loop.json` 读账路径）；`research-loop/bin/rl`（`init` 不问账路径（08 第二节 L40：「各账路径」2026-08-18 gyb 裁掉））
- 新口径：sync-inbox L252: （c）`03` 词表九个文件名旁注「位置钉死，配置里没有账路径（2026-08-18 gyb 裁，`08` 第一节）」
- 原冻结句：`03-ledgers.md` L45「## 九本账的名字和文件」
- 原冻结句：`03-ledgers.md` L49「| 决定账 | decisions | `loop/decisions.<actor>.jsonl`，五个角色加 gyb 六个文件 |」
- 原冻结句：`03-ledgers.md` L50「| 问题条 | issues | `loop/issues.jsonl` |」
- 原冻结句：`03-ledgers.md` L51「| 派活单 | handoffs | `loop/handoffs.jsonl` |」
- 原冻结句：`03-ledgers.md` L52「| 数字账 | runs | `loop/runs.jsonl` |」
- 原冻结句：`03-ledgers.md` L53「| 授权 | grants | `loop/grants.jsonl` |」
- 原冻结句：`03-ledgers.md` L54「| 反馈账 | feedback | `loop/feedback.jsonl` |」
- 原冻结句：`03-ledgers.md` L55「| 口径账 | evaluations | `loop/evaluations.jsonl` |」
- 原冻结句：`03-ledgers.md` L56「| 会话账 | sessions | `loop/sessions.jsonl` |」
- 原冻结句：`03-ledgers.md` L57「| 杂账 | scratch | `loop/scratch.jsonl` |」
- 备注：08 第二节 L40 原句：「其中「各账路径」2026-08-18 gyb 裁掉：账的位置钉死在 `loop/`，配置里没有这一项（见第一节）。」08 第一节 L18：「九本账的位置和文件名钉死：永远是 `loop/` 下 `03-ledgers.md` 词表里那九个名字，配置里没有「各账路径」这一项（2026-08-18 gyb 裁，原话「定死吧」）」；裁决记录 08 L301 同。03 现文那张表本身没有这句旁注，属纯新增的一行注。v2 树 tables/ledgers.json L3 的 `_note` 已写「Ledger files live under loop/ and their names are pinned; the config has no per-ledger path key (08 L18, gyb 2026-08-18 ruled the paths pinned)」，L2 `_source` 引 sync-inbox Q39(c) L252。ledgers.json 另有 grants 账存废（问题 43(c)）没裁定，与本子项无关。

读手没能定的：无。读手原留的三条都已判定：一、(a1) 角色 agent 类型的定义文件 research-loop/agents/<role>.md 按统筹 2026-09-05 的清单已是合法落点，写进 landing。二、(b1)「重跑无副作用」在 30 第二节 L29-184 没有用例（init 只出现在测试 9 L103、测试 12 L134-136、测试 19 L179，没有一条重跑），note 写「没有用例」，不算问题。三、(b3) doctor 第 18 项在 30 第二节没有用例（碰 doctor 的只有测试 6、11、18、19，各对第 3 项、--json 结构、第 19 项、第 6 项 ack），note 写「没有用例」，不算问题。

核手的话：核了七个子项加 unresolved 三条，改了 9 处。1) (b3) frozen_original 行号 206 改 212：用 Read 核 05 L189-221 的 doctor 表，L206 是第 12 项「单子回了 `todo` 而关联 issue 还 open」，第 18 项「loop/runs.jsonl 与宿主 ops/runs.jsonl 对不上的 run_id」在 L212，引文本身逐字对。2) (a1) landing 加 research-loop/agents/<role>.md 作第一个落点（统筹指示 agents/ 已进清单），what 引 08 L90、06 L126「派活一律用这五个类型起 subagent，钩子输入的 `agent_type` 就是这么来的」；transitions.json 的 what 补 `reissue` 行（04 L76「同新建」）；SKILL.md 的 what 补 08 L331 记的「10 到 14 五份已各加一句、类型名照 agents/<role>.md 文件名」。3) (a1) note 删「不在允许的落点清单里，见 unresolved」，改成已列为落点；unresolved 第一条销。4) (a2) frozen_original 加 04 L140「| `launched_by` | `manual`、`subagent`、`workflow` | 必填 |」：sessions 行格式里 `launched_by` 已有 `subagent` 一档，是冻结正文默认 subagent 有一行 sessions 的另一处证据，第 5 条测出不登记时这一档跟着改；schemas/sessions.schema.json 的 what 补这一档。5) (a2) note 补 06 L112、L118 两处同挂第 5 条的原句（用 grep 找到、Read 核过）。6) (b1) note 把「现有测试清单里没有对应用例」写实成「没有用例」并列出 30 §2 里 init 出现的三处（L103、L134/136、L179，awk 扫 L29-184 得到），unresolved 第二条销；landing 的 what 各补 08 L36/L17/L40/L13 出处。7) (b3) note 改正读手的覆盖说法：30 §2 碰 doctor 的不止测试 6 和 19，还有测试 11（L129 `rl doctor --json` 最小结构）和测试 18（L175 第 19 项），四条都不对两本 runs 账，写「没有用例」，unresolved 第三条销；另补一句「两本 runs 账对账」是 08 L180 的叫法、05 现文没有这四个字。8) (b4) landing 加 research-loop/tables/config_defaults.json 作第一个落点：统筹清单明写它是「08 第三节阈值表和第二节配置键」的机器读副本，(b4) 改的正是 08 第二节三个配置键的清单，只写 rl_lib.py 和 bin/rl 盖不住键的声明本身；note 补 08 L177 接口一节原句和 v2 树 config_defaults.json L11-13 已记三键的旁证。9) (b2) 与 (c) 的 note 各补旁证：(b2) 补 08 L55 整句、08 L146、05 现文没有「rl run finish」小节所以 L73 是唯一落笔处、键的声明随 (b4) 进 config_defaults.json（L11 已记 abort_cmd，default null）；(c) 补 08 L18、裁决记录 L301、v2 树 ledgers.json L2-3 已带钉死旁注。核过没改的：七条 new_wording 与 sync-inbox L252 逐字相符（用 Read 核 L240-269）；frozen_original 里 04 L61/L75/L84/L86/L94/L96/L118/L137/L230、05 L39/L73/L179/L235、03 L45/L49-57 共 19 条引文用 Read 逐行核对，引文与行号全部与现文一致；note 里引的旁证行（sync-inbox L245-246/L250/L253/L260-264、08 L13/L17/L18/L36/L40/L51/L52/L53/L55/L89/L90/L146/L150/L177/L180/L301/L309/L331、06 L112/L118/L126、30 L17/L103/L120-136/L175-179、工作指南 L87/L92/L100/L102/L108）逐一读过，全部属实；status 与 pending_ref 按规则：只有 (a2) 带「等待验证第 5 条测完再定」，pending、`verify 5`，其余六项 settled、空。一处判断留给统筹复核：(b1) 落点 research-loop/skills/research-loop/SKILL.md 是入口 skill，清单里对应的形状是 skills/<role>/SKILL.md 而 research-loop 不是五个角色之一；工作指南 L102 与 08 L89（六个 skill：入口一个，五个角色各一个）都把入口 skill 放在 skills/ 下这个目录名，清单里没有更贴的条目，所以保留读手的路径，不改。

## 问题 40（sync-inbox L282-288，核手核过）

### 40(a) 状态 settled

- 代码落点：`research-loop/bin/rl`（不写 rl notify（命令表里的 `rl notify --text` 签名行和「rl notify」一节整删，插件的子命令集合里没有 notify））；`none`（接口一节待验证清单句里第 6、7 条标已销：只改设计文字，30 第 18、19 行已标「已销 2026-08-21」，没有代码落点）
- 新口径：sync-inbox L286: （a）`05`「rl notify」一节（含 `rl notify --text` 签名行）删，命令表如有该行同删；接口一节待验证清单句里第 6、7 条标已销
- 原冻结句：`05-rl-cli.md` L96「| `rl notify --text` | 发桌面通知，不进任何账；推送表和机制见 `01-gyb.md` 第五节 | rl 自己；gyb 也可以手动调 |」
- 原冻结句：`05-rl-cli.md` L223「## rl notify」
- 原冻结句：`05-rl-cli.md` L225「`rl notify --text` 的推送表和机制定义在 `01-gyb.md` 第五节（2026-08-17 gyb 裁，一件事归 01）；定期提醒（待验证第 7 条、`notify.reminder_days`）同在 01 第五节。本份只留命令表里的签名行。」
- 原冻结句：`05-rl-cli.md` L241「- 待验证清单十一条（含第 6 条桌面通知、第 7 条定时提醒、第 1 条会话 id 变量）的测法、通过标准、失败备案：`30-build-steps-verify-tests.md`。本份把待验证第 4 条备案「`rl init` 检查调用者不是任何角色」升成正案、把第 10 条备案里的「doctor 列 `model=unknown`」收成 doctor 第 19 项，要 `30` 收。」
- 备注：裁决原文在 sync-inbox L284（gyb 2026-08-21「收件箱这个算了 先不做，就维护一个我要看的东西就行，我自己记得定期手动看」「那这个砍了吧」），定义处 01-gyb.md 第五节 L137-141；施工指南第四节 L93 已写「rl notify 已裁掉（问题 40）不写」。05-rl-cli.md 命令表在 v2 树里的落点是 research-loop/bin/rl 的子命令集合（核手按统筹指示定）；v2 树里另有 research-loop/tables/commands.json 第 91 行把 notify 记进 removed_commands（why 引 01 L137-141 和 sync-inbox Q40(a) L286），该文件不在落点清单、也不在 README 目录表里，只作旁证。

### 40(b) 状态 settled

- 代码落点：`research-loop/bin/rl`（rl reclaim 没有任何定时提醒机制，只由 gyb 手动跑；rl status 第一行打印距上次 reclaim 几天是留下的唯一机制（05 L93 已是这么写））
- 新口径：sync-inbox L286: （b）`04` 第 164 行附近「定时提醒每 `notify.reminder_days`（默认 7）天叫他一次」半句删，改「gyb 自己记得定期手动跑」
- 原冻结句：`04-handoffs-and-sessions.md` L164「`rl reclaim` 是兜底，由 gyb 定期手动跑，定时提醒每 `notify.reminder_days`（默认 7）天叫他一次。谁能调：gyb。」
- 备注：现文行号与子项写的 164 一致，没漂。01-gyb.md L147 是定义处：定期提醒不做，`rl status` 第一行打印距上次 reclaim 几天转正为唯一机制。

### 40(c) 状态 settled

- 代码落点：`research-loop/bin/rl`（issue 的 assignee 是 gyb 的那一版（含首次开单）不发任何通知，只进 rl status 段 2；其余进角色的 rl inbox）；`research-loop/tables/gyb-usecases.json`（status 段 2（assignee 是 gyb 的 issue）是这条的唯一出口，段 2 从 use case 表倒推（01 L100-114））
- 新口径：sync-inbox L286: （c）`03:92` issues 入账规则「`assignee` 是 `gyb` 的那一版（含首次开单）触发桌面通知」改「进 `rl status` 段 2」（`03` 与 `09` 写了两遍处）
- 原冻结句：`03-ledgers.md` L92「入账规则四条：改派等于追加一版换 `assignee`；`assignee` 是 `gyb` 的那一版（含首次开单）触发桌面通知；`reply` 只有 `assignee` 或 gyb 能写；`close` 只有开单的 actor 或 gyb 能写，通知类 issue（`withdrawn`、`orphaned`、`fyi`）的 `assignee` 也能关（2026-08-17 gyb 裁，sync-inbox 问题 23：`rl inbox` 只读不关，通知类 issue 由收件人做完了自己 `rl issue close`）。另有一处自动关：`rl handoff accept` 关这张单关联的 `answered` issue。」
- 备注：03 现文 L92 仍写「触发桌面通知」，行号没漂；写了两遍的另一处 09-common-and-feedback.md L115 已于 2026-08-21 改成「进 `rl status` 段 2」（现文：「`assignee` 是 `gyb` 的那一版（含首次开单）进 `rl status` 段 2，其余进角色的 `rl inbox`（桌面通知 2026-08-21 裁掉不做）。」），本次只补 03 这一处。同一行里 reply/close 写权那几条不在本笔欠账范围内，它们的落点是 scripts/rl_lib.py 与 schemas/issues.schema.json，本笔不动。

### 40(d) 状态 settled

- 代码落点：`research-loop/bin/rl`（rl issue open / rl issue reassign 的 `--to gyb`（开单或改派）不触发通知，那一版进 rl status 段 2）；`research-loop/tables/gyb-usecases.json`（同 (c)：status 段 2 是 assignee 为 gyb 的 issue 的唯一出口）
- 新口径：sync-inbox L287: (d) `05:58` issue 命令行「`--to gyb`（开单或改派）触发通知」改「进 `rl status` 段 2」（`09:119` 同句 2026-08-21 已改，写了两遍处）
- 原冻结句：`05-rl-cli.md` L58「| `rl issue open --to R --kind K [--stage S] --text [--handoff ID] [--log-tail FILE\|--log-text -]` / `rl issue reassign ID --to R` / `rl issue reply ID --text` / `rl issue close ID` / `rl issue link ID --handoff ID` / `rl issue show ID` / `rl issue list [--open] [--to R] [--kind K]` | 问题条；`--to gyb`（开单或改派）触发通知；`link` 是 doctor 修法 | 按角色 json 的 `ledger_writes`，查谁都行 |」
- 备注：统筹补扫 2026-08-21（评审修复，gyb 授权）追加的三处同源残留之一。05 现文 L58 行号没漂。写了两遍的另一处 09-common-and-feedback.md L119 已改（现文：「`--to gyb`（开单或改派）进 `rl status` 段 2；`link` 是 doctor 给的修法。」）。05 命令表在 v2 树里的落点是 research-loop/bin/rl 的子命令集合（核手按统筹指示定）；tables/commands.json 的 issue 一族只作旁证，不进落点。

### 40(e) 状态 settled

- 代码落点：`research-loop/bin/rl`（init 的默认配置不含 notify.reminder_days（rl init 写的 research-loop.json 阈值键里没有这一项））；`research-loop/scripts/rl_lib.py`（读 research-loop.json 阈值的代码认的键集合里没有 notify.*（reclaim 和 status 只读 reclaim.* 与 status.stale_holder_minutes））
- 新口径：sync-inbox L287: (e) `04:221` 阈值清单删 `notify.reminder_days` 一项
- 原冻结句：`04-handoffs-and-sessions.md` L221「- 阈值 `status.stale_holder_minutes`（默认 30）、`reclaim.session_idle_hours`（48）、`reclaim.handoff_idle_hours`（72）、`reclaim.ql_idle_days`（7）、`notify.reminder_days`（7）：阈值表定义在 `08-trees-init-and-host.md`（原文指「`05` 指到的施工计划第八节」，按 HANDOFF 四点五节改指 `08`）。」
- 备注：现文 L221 行号没漂。阈值表的定义处 08-trees-init-and-host.md 已于 2026-08-21 删掉这一行（08 L308 裁决记录；01 L59 同记），04 这份是引用处，冻结未改。v2 树里 research-loop/tables/config_defaults.json 第 36 行已把 notify.reminder_days 记进 removed_keys（why 引 01 L145-147 和 sync-inbox Q40），该文件不在落点清单、也不在 README 目录表里，只作旁证。

### 40(f) 状态 settled

- 代码落点：`research-loop/bin/rl`（init 的默认配置不含 notify.reminder_days（rl init 写的 research-loop.json 阈值键里没有这一项））；`research-loop/scripts/rl_lib.py`（读 research-loop.json 阈值的代码认的键集合里没有 notify.*（L235 这句就是 05 用到的键清单，键清单落在读配置的代码里））
- 新口径：sync-inbox L287: (f) `05:235` 接口一节阈值清单删 `notify.reminder_days`
- 原冻结句：`05-rl-cli.md` L235「- `rl init` 建的六样加一节、`research-loop.json` 阈值表（本份用到 `issues.gyb_stale_hours`、`issues.answered_stale_days`、`status.stale_holder_minutes`、`status.review_recent_days`、`reclaim.*`、`notify.reminder_days`、`quick_lane.worktree_root`，新加 `lock.timeout_seconds` 默认 10 秒）、宿主发射器的命令模板（`launcher.free_cmd`、`launcher.launch_cmd`、`launcher.finish_cmd`）、`rl run finish` 调哪条宿主命令：`08-trees-init-and-host.md`。`rl init` 在角色会话里拒收退出码 3，已收（08 第一节）。」
- 备注：现文 L235 行号没漂。与 (e) 同一个键，(e) 在 04 的接口一节、(f) 在 05 的接口一节，落点相同。同一行 L235 还挂着问题 39(b4) 要补的三个键（launcher.abort_cmd、repo_run、host_ledgers），改这一行时两笔欠账撞在一处。

### 40(x) 状态 settled

- 代码落点：`none`（只改设计文字：L3 导语里「`rl notify` 的签名（推送表归 01-gyb.md 第五节）」那一项删，L89 小节标题里的「、通知」删（这一节的表里「通知」只对应 L96 那一行，行删了标题的字跟着删）；代码落点已由 (a) 覆盖（bin/rl 的子命令集合里没有 notify））
- 新口径：sync-inbox L286: （a）`05`「rl notify」一节（含 `rl notify --text` 签名行）删，命令表如有该行同删
- 原冻结句：`05-rl-cli.md` L3「> 这份是命令的唯一总表：actor 怎么定、每条子命令干什么谁能调、退出码、`--json`、锁与写序、`rl inbox`、`rl trace`、`rl status` 的十段、`rl reclaim`、`rl doctor` 的全部扫描项与修法、`rl notify` 的签名（推送表归 01-gyb.md 第五节）。别的 part 引用命令时指到这一份。」
- 原冻结句：`05-rl-cli.md` L89「### 收件箱、回收、体检、通知」
- 备注：核手补，同源残留。问题 40(a) 点名的是「rl notify」一节、命令表签名行、接口一节待验证句三处；05 现文 L3 导语仍把「`rl notify` 的签名」列进本份覆盖范围，L89 小节标题仍带「通知」，两处都是 (a) 删掉签名行之后没有指向的字面，随 (a) 一起删字。05 里其余含「桌面通知」「rl notify」的行（L307、L309、L379、L437、L439、L517、L553、L561、L611、L642、L645、L677）都在评审记录和裁决记录里，是历史记录，不改。

读手没能定的：无。读手原留的两条都已判定：一、05 L3 导语的 `rl notify` 残留核对现文后确认存在，连同 L89 小节标题的「通知」补成子项 (x)；二、05 命令表在 v2 树里的落点按统筹指示定为 research-loop/bin/rl 的子命令集合，(a)(d) 的落点不改指 tables/commands.json。

核手的话：核了六个子项加 unresolved 两条，改了 4 处。1) 新增子项 (x)：读手在 unresolved 里提的 05 第 3 行导语残留，用 Read 核对现文确认「`rl notify` 的签名（推送表归 01-gyb.md 第五节）」仍在；另用 grep 扫 03/04/05 全文，L89 小节标题「### 收件箱、回收、体检、通知」的「通知」只对应 L96 那一行签名行，也是同源残留，一并抄进 (x)；new_wording 按指示引问题 40(a) 那句，note 写「核手补，同源残留」，落点 none（纯文字），unresolved 第一条随之销掉。2) unresolved 第二条（命令表实体是 tables/commands.json 还是 bin/rl）按统筹指示判定：05 命令表在 v2 树里的落点是 research-loop/bin/rl 的子命令集合，(a)(d) 落点维持 bin/rl；(a)(d) 的 note 里「按指示写成」改成明确的判定语，commands.json 降为旁证；unresolved 清空。3) (e)(f) 各加一条落点 research-loop/scripts/rl_lib.py：05 L235 那句本身就是「本份用到的阈值键清单」，键清单在 v2 树里落在读配置的代码（同问题 39(b4) 对同一行的处理），只写 bin/rl 的 init 默认配置盖不住「没有代码读这个键」这一半；(e) 的 note 补 v2 树 tables/config_defaults.json 第 36 行 removed_keys 已记 notify.reminder_days 这条旁证（该路径不在落点清单也不在 README 目录表）。4) (f) 的 note 补一句：L235 同时挂着问题 39(b4) 要补的三个键，两笔欠账撞同一行。核过没改的：六条 new_wording 与 sync-inbox L286-287 逐字相符；八条 frozen_original（05 L96/L223/L225/L241/L58/L235，04 L164/L221，03 L92）用 Read 逐行核对，引文与行号全部与现文一致，L58 的 `\|` 是 JSON 转义、现文是 `\|` 一个反斜杠；note 里引的旁证行（01 L59/L100-114/L137-141/L147、08 L308、09 L115/L119、30 L18-19、施工指南 L93、commands.json L91）逐一读过，全部属实；六个子项都没有「问 gyb」「归 05 定」「等待验证」字样，status 全 settled、pending_ref 全空，符合规则；落点路径全在清单内且与 research-loop/README.md 目录表相符（bin/rl = 命令入口，tables/gyb-usecases.json = gyb use case 表，scripts/rl_lib.py = 账的读写实现）。

## 问题 41（sync-inbox L290-296，核手核过）

### 41(a) 状态 settled

- 代码落点：`research-loop/schemas/scratch.schema.json`（open 版必填按 role 分岔：role=deploy 必填 worktree、base_commit、branch；role=analysis 只必填 dir，base_commit 与 branch 两栏对 analysis 不设）；`research-loop/tests/`（测试 16（快车道）：analysis 的 `ql open --role analysis` 开张版只填 dir，deploy 开张版三栏齐；30-build-steps-verify-tests.md L164）
- 新口径：sync-inbox L294: （a）`03` scratch 表 `open` 版必填改「deploy 填 `worktree`、`base_commit`、`branch`；analysis 只填 `dir`」
- 原冻结句：`03-ledgers.md` L202「| `worktree` | worktree 路径 | deploy 的 `open` 版必填 |」
- 原冻结句：`03-ledgers.md` L203「| `dir` | `analysis/scratch/<ql_tag>/` | analysis 的 `open` 版必填 |」
- 原冻结句：`03-ledgers.md` L204「| `base_commit` | git commit | `open` 版必填（analysis 的快车道不建分支，这一栏填什么由 `07-quick-lane.md` 定） |」
- 原冻结句：`03-ledgers.md` L205「| `branch` | 分支名 | deploy 的 `open` 版必填；analysis 的快车道不建分支，要不要这一栏由 `07-quick-lane.md` 定 |」
- 备注：裁决在 07-quick-lane.md L292「2026-08-21 问题 1 裁 A（原话「A」）」，新口径已经落在 07 第六节 L70「`open` | `role`（`deploy` 或 `analysis`）；deploy 填 `worktree`、`base_commit`、`branch`，analysis 只填 `dir`——`base_commit`、`branch` 两栏对 analysis 不设」；03 是定义处（写了两遍处），冻结未跟。03 L204、L205 里「由 `07-quick-lane.md` 定」的悬空一并消掉。底座 2046a63 的 research-loop/schemas/scratch.schema.json 已按 07 L70 分岔：L24 role=deploy 的 open 版必填 worktree、base_commit、branch，L25 role=analysis 的 open 版必填 dir，两条都标了 sync-inbox Q41(a) 或 07 L70。

### 41(b) 状态 settled

- 代码落点：`research-loop/tables/transitions.json`（（新建）→ done_pending_review 快车道补单那一行的「前提」栏加 code_paths 非空）；`research-loop/tests/`（测试 2（转移表）L49 那条快车道补单前提用例加 code_paths 非空；测试 4（交付物）L60「快车道补单只要 method」一句同步成还要 code_paths）
- 新口径：sync-inbox L294: （b）`04` 转移表快车道「（新建）→ done_pending_review」行前提加「`code_paths` 非空」
- 原冻结句：`04-handoffs-and-sessions.md` L62「| （新建） | `done_pending_review` | `deploy`（快车道补单，owner 记 gyb） | `quick_lane` 为 true，`report_paths.method` 存在，`explanation` 非空，`ql_tag` 指的 scratch 行状态是 `open`（补单开完拿到编号再 `rl ql close --merged --handoff ID` 关杂账，两边互指） | 无（等 gyb 验收，只有 gyb 能 accept） | `handoff open --quick-lane` |」
- 备注：裁决在 07 L294「2026-08-21 问题 4 裁 A」。07 现文已经是新口径：L101 规矩 6「`code_paths` 必填……（2026-08-21 gyb 裁，问题 4）」，L109 抄的转移表行前提里已带「`code_paths` 非空（2026-08-21 加，问题 4，`04` 冻结表未跟、在要同步的清单里）」。底座 5c56edf 已叠进：research-loop/tables/transitions.json 行 id `open_quick_lane` 的前提里有 id `ql.code_paths_nonempty`（L40，source 写 sync-inbox Q41(b) L294; 07 L101, L109）；HEAD 与 5c56edf 在这一行逐字相同。

### 41(c1) 状态 settled

- 代码落点：`research-loop/tables/transitions.json`（新增一行：从 todo 到 todo（追加一版标 quick_lane），谁能写 deploy，前提是单子在 todo，之后没人拉起（离开待干队列、不派人接、不占 holder），子命令 `rl ql open --from`）；`research-loop/bin/rl`（子命令 `rl ql open --from ho-ID`：给那张待干工单追加一版标 quick_lane 并让它离开待干队列）；`research-loop/tests/`（测试 2（转移表，每行合法转移一个用例）、测试 16（快车道））
- 新口径：sync-inbox L294: （c）`04` 转移表补两行——「`todo` 的单 `rl ql open --from` 标 `quick_lane`、离开待干不占 holder」
- 原冻结句：无（纯新增）
- 备注：纯新增：04 第三节转移表（L59 到 L77）现在十六行里没有这一行。裁决在 07 L295「2026-08-21 问题 6 裁 A」，07 现文 L31 已写「rl 把那张工单追加一版标 `quick_lane`，单子从此离开待干队列——正常流程不再派人接它、不占 holder」。底座 5c56edf 已叠进：transitions.json 行 id `ql_transfer_in`（L231 到 L241），from todo、to same、who_can_write deploy、前提 id `ql.transfer_marks_quick_lane`、subcommand `ql open --from`，source 写 07 L31; sync-inbox Q41(c) L294。

### 41(c2) 状态 settled

- 代码落点：`research-loop/tables/transitions.json`（新增一行（出口两条路）：quick_lane 标记的单追加一版直达 done_pending_review，前提同快车道新建行（report_paths.method、code_paths、explanation、与 scratch 行互指），验收人 gyb；放弃时追加一版退回 todo 并去掉 quick_lane 标）；`research-loop/bin/rl`（转进单出口那一步的子命令（名字未定，见 (f3)））；`research-loop/tests/`（测试 2（转移表）、测试 16（快车道））
- 新口径：sync-inbox L294: （c）`04` 转移表补两行——……「`quick_lane` 标记的单出口追加一版直达 `done_pending_review`（前提同快车道新建行）／放弃退回 `todo` 去标记」
- 原冻结句：无（纯新增）
- 备注：纯新增：04 第三节转移表现文没有这一行。行本身已裁（07 L295 问题 6 裁 A，07 L114 写明「出口合回时把原单追加一版直达 `done_pending_review`，前提同上表那一栏……放弃时追加一版退回 `todo`、去掉 `quick_lane` 标（或 gyb 收回）」）；这一行「子命令」栏的名字属于 (f3)，没裁定。底座 5c56edf 已叠进：transitions.json 行 id `ql_transfer_exit`（L242 到 L254），from todo、to [done_pending_review, todo]、who_can_write deploy、前提 id `ql.exit_same_as_open_quick_lane`、subcommand 栏写 `PENDING(issue 41f)`（L251），_pending 栏 L253 写「sub-command name for this exit is for gyb to set at the final merge」。

### 41(d) 状态 settled

- 代码落点：`research-loop/scripts/rl_lib.py`（owner 判定：快车道补单的 owner 取 gyb，不取 from_role（from_role 与 to_role 都是 deploy），accept 权限与 fyi/orphaned 收件人按这个 owner 走）；`research-loop/tables/transitions.json`（（新建）→ done_pending_review 行「谁能写」栏已写「`deploy`（快车道补单，owner 记 gyb）」、accept 行「owner；快车道补单只有 gyb」，照抄即可）
- 新口径：sync-inbox L294: （d）`04`「owner 就是开单角色」通则加例外「快车道补单开单动作 deploy、owner 记 gyb」
- 原冻结句：`04-handoffs-and-sessions.md` L49「每张单子上有两个人。owner 是开单的角色，就是 `from_role`，负责单子从开到关：拉起下游、验收、收回；快车道补单和 gyb 开的单 owner 记 `gyb`。holder 是当前正在干这张单子的那一个会话，字段里存的是 session_id 不是角色名。owner 是角色不是会话，所以 owner 角色当下没有活着的会话时单子由 gyb 拉起，`rl status` 单列这一类。」
- 原冻结句：`04-handoffs-and-sessions.md` L19「| `from_role` | 就是 owner，可以是 `gyb` |」
- 原冻结句：`04-handoffs-and-sessions.md` L62「| （新建） | `done_pending_review` | `deploy`（快车道补单，owner 记 gyb） | `quick_lane` 为 true，`report_paths.method` 存在，`explanation` 非空，`ql_tag` 指的 scratch 行状态是 `open`（补单开完拿到编号再 `rl ql close --merged --handoff ID` 关杂账，两边互指） | 无（等 gyb 验收，只有 gyb 能 accept） | `handoff open --quick-lane` |」
- 备注：(i) 的核对结果：04 现文已有同义句，两处——L49 通则末半句「快车道补单和 gyb 开的单 owner 记 `gyb`」，L62 转移表「谁能写」栏「`deploy`（快车道补单，owner 记 gyb）」，两句合起来覆盖「开单动作 deploy、owner 记 gyb」。按 (i) 的「已有就只核不加」，最后一期落地时只核不加句。另记一处：04 L19 字段表写「`from_role` | 就是 owner，可以是 `gyb`」，这是通则的第二个副本，快车道补单的 from_role 是 deploy 而 owner 是 gyb（07 L116「设计文档「`from_role` 和 `to_role` 都是 deploy」那句照旧成立，说的是谁干的活」）；L19 与 L49 是同源句，最后一期一起改。底座 5c56edf 已叠进：transitions.json 表头规矩 id `owner_definition`（L13）写「owner is from_role and is a role, not a session; quick-lane supplements and gyb-opened orders record owner gyb; the quick-lane supplement is opened by deploy with owner recorded as gyb」，source 写 04 L49; 07 L116; sync-inbox Q41(d)；行 `open_quick_lane` 的 who_note（L35）与行 `accept` 的 who_note（L137）也带了。research-loop/scripts/rl_lib.py 现在还没有 owner 判定的代码（grep quick_lane 无结果）。

### 41(e) 状态 settled

- 代码落点：`none`（设计文字：04 第七节（sessions 这一本账，L131 到 L160）补一句。登记钩子只在加载插件角色 skill 那一刻触发，gpu-runner 是宿主的东西、不加载角色 skill，代码侧没有要写的分支；sessions.schema.json 的 role 枚举只有五个角色（L11），也不用动）；`research-loop/skills/deploy/SKILL.md`（「限制条件」栏的派活交代：deploy 在快车道派 gpu-runner 时，gpu-runner 是宿主的东西、不登记 sessions 账、不写杂账，deploy 备好完整命令（`--run-id` 填 ql_tag、`--track` 填被微调实验的方向）交给它，跑完的数字由 deploy 自己追加进杂账（07 L58））
- 新口径：sync-inbox L294: （e）`04` sessions 账补「宿主 gpu-runner 不登记 sessions 账」
- 原冻结句：无（纯新增）
- 备注：纯新增：04 全文没有 gpu-runner 三个字（grep 过），第七节 L131 到 L160 也没有对应句子。裁决在 07 L296「2026-08-21 问题 7 裁 A」，07 L58 现文「gpu-runner 是宿主的东西，不进插件的账：不登记 sessions 账、不写杂账（2026-08-21 gyb 裁，问题 7）」。要不要落进 deploy 的 SKILL.md 的判定：06-hooks-and-permissions.md L193 deploy 的 `dispatches_to` 是「run、gpu-runner」，L196 备注「gpu-runner 只在快车道派」；11-role-deploy.md L122「快车道里 deploy 可以派 gpu-runner，这是 deploy 唯一能派 run 之外的对象」、L145 json 副本 dispatches_to「run、gpu-runner」；施工指南（plans/2026-09-04-research-loop-work-guide.md）L126 步 6 写 SKILL.md「限制条件」栏「装 reads、dispatches_to、……、派活交代」。gpu-runner 在 deploy 的 dispatches_to 里，「不登记 sessions 账」是派它时的交代，所以落进 research-loop/skills/deploy/SKILL.md 的限制条件栏。research-loop/skills/ 现在是空目录，这份 SKILL.md 步 6 才写。

### 41(f1) 状态 settled

- 代码落点：`research-loop/tables/commands.json`（`ql close` 那一条的 notes 写两条路都删 worktree 与同名分支（05 命令表的机器读副本））；`research-loop/bin/rl`（子命令 `rl ql close`：`--merged` 和 `--dropped` 两条路关张时都删掉 worktree 和同名分支）；`research-loop/tests/`（测试 16（快车道）：close 两条路各一个用例，关张后工作树与同名分支都不在）
- 新口径：sync-inbox L294: （f）`05` `rl ql close` 补「`--merged` 和 `--dropped` 都删工作树与同名分支」
- 原冻结句：`05-rl-cli.md` L87「| `rl ql open [--role deploy\|analysis] [--from ho-ID]` / `rl ql close QL --merged --handoff ID \| --dropped --reason` / `rl scratch add QL [--note ...] [--metric k=v]` / `rl scratch list [--status S]` / `rl scratch show QL` | 快车道进出和杂账；open 在锁里分 ql_tag、建 worktree（`quick_lane.worktree_root/<ql_tag>`，分支同名）或 `analysis/scratch/<ql_tag>/`；`--from` 把待干工单标 quick_lane；`close --merged --handoff ID` 的前提是 ID 是 quick_lane 补单且它的 `ql_tag` 等于 QL | `ql open`、`scratch add` deploy、analysis；`ql close --merged` 只有 deploy，`--dropped` deploy、analysis 都行（analysis 快车道没有补单）；`scratch list/show` 查谁都行 |」
- 备注：裁决在 07 L297「2026-08-21 问题 8 裁 A（gyb 确认「可以」，按总纲关张即清干净）」，07 L92 现文「`rl ql close` 关张时把工作树和同名分支一并删掉，`--merged` 和 `--dropped` 两条路都删」。05 L87 现文只写了 open 建 worktree，没写 close 删。底座 5c56edf 已叠进：research-loop/tables/commands.json L71 `ql close` 的 notes 写「Both paths delete the worktree and the branch of the same name (07 L92; sync-inbox Q41(f))」。

### 41(f2) 状态 settled

- 代码落点：`research-loop/tables/commands.json`（`ql open` 那一条的 notes 写 `--from` 标 quick_lane 并让单子离开待干队列、不占 holder（05 命令表的机器读副本））；`research-loop/bin/rl`（子命令 `rl ql open --from ho-ID`：除了标 quick_lane，还要让单子离开待干队列（不再派人接、不占 holder））；`research-loop/tables/transitions.json`（与 (c1) 新增的那一行同一件事，两处口径要一致）；`research-loop/tests/`（测试 16（快车道）、测试 2（转移表））
- 新口径：sync-inbox L294: （f）……`rl ql open --from` 补「单子标 `quick_lane` 并离开待干」
- 原冻结句：`05-rl-cli.md` L87「`--from` 把待干工单标 quick_lane；`close --merged --handoff ID` 的前提是 ID 是 quick_lane 补单且它的 `ql_tag` 等于 QL」
- 备注：05 L87 现文只写到「把待干工单标 quick_lane」，缺「离开待干」半句；这里的 quote 截的是 L87 中段，整行原文见 (f1) 的 frozen_original。裁决在 07 L295（问题 6 裁 A），07 L31 现文写全了。底座 5c56edf 已叠进：commands.json L70 `ql open` 的 notes 写「--from marks a todo work order quick_lane and takes it out of the todo queue without a holder (07 L31; sync-inbox Q41(f))」；transitions.json 行 `ql_transfer_in`（L231 到 L241）同一件事。

### 41(f3) 状态 pending，标记 `PENDING(issue 41f)`

- 代码落点：`research-loop/tables/commands.json`（转进单出口那一步的子命令名，名字未定；占位条目的 signature 空、pending 标 PENDING(issue 41f)（05 命令表的机器读副本））；`research-loop/tables/transitions.json`（行 ql_transfer_exit 的子命令栏标 PENDING(issue 41f)）；`research-loop/bin/rl`（转进单（`--from` 进来的单）出口那一步的子命令名，名字未定；落地前 bin/rl 里这一步标 PENDING(issue 41f)）
- 新口径：sync-inbox L294: （f）……转进单出口那一步的子命令名归 `05` 定
- 原冻结句：无（纯新增）
- 备注：纯新增，冻结正文里没有对应句子。按 (j) 的读法「最后一期改 `05` 时由 gyb 定」——冻结规矩不给 rl-part-05 派活。施工指南 L96 也把这一条列成没裁定：「ql 转进单出口的子命令名（问题 41(f)）没裁定」。底座 5c56edf 已叠进两处占位：commands.json L88 条目 name「<quick-lane exit of a transferred order>」、signature null、pending「PENDING(issue 41f): the sub-command that appends the exit version … has no name yet (07 L114)」；transitions.json L251 行 `ql_transfer_exit` 的 subcommand 栏「PENDING(issue 41f)」。

### 41(g) 状态 settled

- 代码落点：`research-loop/common/GLOBAL-RULES.md`（公共规矩是九条（含 rule-09「凡修的东西是账上报过的 issue，修完必须回复并关掉，不许静默修」），头部带 rules_version）
- 新口径：sync-inbox L294: （g）`05:236` 接口「公共规矩八条」改九条（rule-09 修必销案，2026-08-21 立）
- 原冻结句：`05-rl-cli.md` L236「- `rl feedback accept` 的 `rules_version` 和母版改动的规矩、公共规矩八条、issues 九种 kind、判断类检查的问题清单文件（本份裁：放 `common/`）：`09-common-and-feedback.md`。」
- 备注：sync-inbox 里写的行号 `05:236` 与现文一致。rule-09 已于 2026-08-21 立并同步到 09（07 L320「已同步 2026-08-21 rl-hub-v5：立为 rule-09，标题与各处「八条」改九条」），05 的接口句是冻结没跟上的那一处。05 另外两处出现「八条」的地方（L437「八条原则第 6 条」、L459「公共规矩第 8 条」）在「第二轮模拟里归到这一份的摩擦（原样，未核实）」一段里，不属于这一笔。底座已落：research-loop/common/GLOBAL-RULES.md L1「rules_version: 1」，L35「### rule-09 A fix closes its case」，L5 的来源注写 rule-01 到 rule-09 对应 09 L37 到 L45。

### 41(h) 状态 settled

- 代码落点：`research-loop/bin/rl`（`rl status`：段 9 里没关的快车道不进 line 分组，`--group-by line` 时单独列一堆）；`research-loop/tests/`（测试 11（rl status、rl inbox 与 rl reclaim）：`--line` 过滤与 `--group-by line` 的用例里，没关的快车道单独成组）
- 新口径：sync-inbox L295: (h) `05` `rl status` 段 9／`--group-by line` 那里补「没关的快车道不归线，单独列一堆」（`07` 定稿，`01` 已落，`05:163`/`05:166` 当时漏攒）
- 原冻结句：`05-rl-cli.md` L163「| 9 | review/ 最近的清单、活着的会话（含 focus）、没关的快车道 |」
- 原冻结句：`05-rl-cli.md` L166「第一行打印距上次 reclaim 几天。整份可以按 `--line` 过滤、按 `--group-by line|batch` 归组；`line` 就是根决定编号。」
- 备注：sync-inbox 写的 `05:163`/`05:166` 与现文一致，没漂。同一句 2026-08-21 已落进 01-gyb.md（07 L319「`01-gyb.md`：`rl status` 段 9／`--group-by line` 补「没关的快车道不归线，单独列一堆」（问题 10）。（已同步 2026-08-21 rl-hub-v5）」），05 是冻结没跟上的那一处。裁决记录在 07 L299「2026-08-21 问题 10 裁 A」。

### 41(i) 状态 settled

- 代码落点：`none`（核对动作，不是改动；核对结果已写进 (d) 的 note）
- 新口径：sync-inbox L295: (i) (d) 那条评审核对 `04` 现文可能已有同义句，落地时先核对、已有就只核不加
- 原冻结句：`04-handoffs-and-sessions.md` L49「每张单子上有两个人。owner 是开单的角色，就是 `from_role`，负责单子从开到关：拉起下游、验收、收回；快车道补单和 gyb 开的单 owner 记 `gyb`。」
- 原冻结句：`04-handoffs-and-sessions.md` L62「| （新建） | `done_pending_review` | `deploy`（快车道补单，owner 记 gyb） | …… |」
- 备注：核对结论：04 现文已有同义句，(d) 落地时只核不加。L49 覆盖「owner 记 gyb」，L62 覆盖「开单动作 deploy」加「owner 记 gyb」。唯一没覆盖的是 L19 字段表那句「`from_role` | 就是 owner，可以是 `gyb`」，与 L49 同源，最后一期一起改，见 (d) 的 note。

### 41(j) 状态 settled

- 代码落点：`none`（只定 (f3) 的读法，本身没有代码落点；落到 (f3) 的 status=pending、pending_ref=issue 41f）
- 新口径：sync-inbox L295: (j) (f) 里「转进单出口那一步的子命令名归 `05` 定」读作「最后一期改 `05` 时由 gyb 定」——冻结规矩不给 rl-part-05 派活
- 原冻结句：无（纯新增）
- 备注：纯新增（是 sync-inbox 自己的读法说明，冻结正文里没有对应句子）。

核手的话：核对方式：sync-inbox L290-296、03 L196-209、04 L16-25 / L45-80 / L131-160、05 L84-89 / L158-168 / L232-239、07 L21-122 / L281-321、06 L170-234、11 的 gpu-runner 四处、施工指南 L110-131、30 L44-63 / L160-166 都用 Read 读了现文；transitions.json、commands.json、scratch.schema.json、GLOBAL-RULES.md 读了 HEAD 并用 git show 对了 5c56edf。改了 15 处：1. (a) note 里 07 裁决记录的行号 L294 改 L292（L292 才是问题 1，L294 是问题 4），补底座 scratch.schema.json 已分岔的行号。2. (b) note 补 07 L294 问题 4 的裁决行和底座 transitions.json L40 `ql.code_paths_nonempty`。3. (c1) note 补底座行 `ql_transfer_in`（L231-241）。4. (c2) new_wording 在「补两行——」后面加省略号「……」：原句两个「」是连着的，读手跳过第一个「」直接接第二个，没标省略，按「允许截取、不许改字」的规矩补省略号标出跳过的一段。5. (c2) note 补底座行 `ql_transfer_exit`（L242-254，subcommand 栏 L251 是 PENDING(issue 41f)）。6. (d) frozen_original 第二条行号 21 改 19：04 L19 才是「| `from_role` | 就是 owner，可以是 `gyb` |」，L21 是 holder 那一行（派活的说明里也写成 L21，同样是错的）。7. (d) note 行号同改，写明 L19 与 L49 是同源句、最后一期一起改，补底座表头规矩 `owner_definition`（L13）与两处 who_note（L35、L137），并记 rl_lib.py 现在还没有 owner 判定代码。8. (e) landing 加 research-loop/skills/deploy/SKILL.md：06 L193 deploy 的 dispatches_to 含 gpu-runner、L196 备注只在快车道派，11 L122 与 L145 同说，施工指南 L126 步 6 写 SKILL.md 限制条件栏「装 reads、dispatches_to、……、派活交代」，「不登记 sessions 账」是派 gpu-runner 时的交代，落进这一栏；note 写了判定链，原 none 一条保留并补 sessions.schema.json role 枚举不用动。9. (f1) landing 加 research-loop/tables/commands.json（05 命令表的机器读副本，底座 L71 `ql close` 的 notes 已写两条路都删）。10. (f2) frozen_original 的 quote 去掉夹在引文里的「……（整行原文见 (f1) 的 frozen_original）」，只留 05 L87 中段的逐字原文；那句说明移到 note。11. (f2) landing 加 commands.json（底座 L70 `ql open` 的 notes 已写离开待干、不占 holder），note 补底座两处。12. (f3) landing 加 commands.json（底座 L88 占位条目 signature null、pending PENDING(issue 41f)）和 transitions.json（L251），note 补两处占位。13. (g) note 补底座 GLOBAL-RULES.md 已落（L1 rules_version: 1，L35 rule-09）。14. (h) note 补 07 L299 问题 10 的裁决行。15. (i) note 行号 L21 改 L19，写同源句结论。读手的 unresolved 两条都按原文判掉了：(e) 落 deploy 的 SKILL.md（第 8 处），(d) 的 L19 是同源句、最后一期一起改（第 7 处），unresolved 清空。没改的：其余 new_wording 与 sync-inbox L294/L295 逐字一致；03 L202-205、04 L49、L62、05 L87、L163、L166、L236 的 quote 与行号全部与现文一致；status 与 pending_ref 全部维持（只有 (f3) pending，pending_ref `issue 41f`）；transitions.json 从 5c56edf 到 HEAD 只改了 `open.work_order_has_track` 的 source 一行，Q41 相关行逐字未变。

## 问题 43（sync-inbox L307-314，核手核过）

### 43(a) 状态 settled

- 代码落点：`research-loop/bin/rl`（doctor subcommand: scan item 16 (decision source points at notes/ but grants has no read:notes for that actor) is not implemented; item number 16 is left unused, items are not renumbered, and item 20 from issue 35(a) is appended at the end (sync-inbox L195 (g))）
- 新口径：sync-inbox L311: （a）`05` doctor 十九项里「决定来源指向 notes/ 但 grants 查不到 `read:notes`」一项删
- 原冻结句：`05-rl-cli.md` L210「| 16 | 决定来源指 notes/ 但 grants 里没有该 actor 的 read:notes | 只报不修：附 `rl grant add --to R --permission read:notes`（事后补授权）或 `rl decision update ID` 换来源两条命令 | gyb |」
- 原冻结句：`05-rl-cli.md` L191「`rl doctor [--ack ITEM ID] [--unack ITEM ID] [--list-acks]` 扫九本账。十九项：前十八项照施工计划第六节，第 19 项是 2026-08-17 从待验证第 10 条的失败备案升上来的。修法和「修完之后归谁推」两栏 2026-08-17 gyb 裁（第 3、5、6 项的修法出自源文档，其余是这次补的）。「只报不修」的项 doctor 只列出涉及的行，不给修法命令，人看了决定。」
- 原冻结句：`05-rl-cli.md` L221「doctor 只做脚本能判的检查，也就是上面十九项。」
- 原冻结句：`03-ledgers.md` L240「- 每本账的写命令和查询命令清单、`rl trace`、`rl status`、`rl inbox`（只读不关）、`rl doctor`（十九项与修法；`--ack/--unack` 是写命令、只有 gyb）、`rl reclaim` 在 `05-rl-cli.md`；`rl run add` 的签名去掉 `--artifact-dir`（2026-08-17 裁）。`05` 的「锁与写序」一节和退出码表照抄本份，两边一字不差。」
- 备注：现文项号是第 16 项（05 L210）。按 sync-inbox L195 的 (g)：删的留空号不重排、新加接末尾编号，既有按项号写的引用（`05:237`、`01:156`、`30:225` 这类）不跟着漂。删 16 加 20 之后活着的项是 1-15、17、18、19、20 共十八项，05 L191、05 L221、03 L240 三处「十九项」的计数句要跟着改（grep 03/04/05 「十九项」只命中这三处），这三处是设计文字、没有代码落点。测试侧无落点：30 L225 写明 doctor 只有第 3 项（经测试 6）和第 19 项（经测试 18）有用例，第 16 项本来就没有用例。施工指南 L96 已把这一笔写进 `bin/rl` 步 4 那一行（「doctor（按问题 35(a)、43(a) 删掉第 16 项加上第 20 项）」）。

### 43(a2) 状态 settled

- 代码落点：`research-loop/bin/rl`（init subcommand: no 'ask once whether to issue read:notes to idea' prompt; init builds research-loop.json, loop/ with the ledgers, experiments/, analysis/ (with analysis/scratch/), review/, notes/, appends the CLAUDE.md section, and still refuses in a role session with exit code 3）
- 新口径：sync-inbox L312: （统筹补扫 2026-08-21 rl-hub-v6：(a) 的连带还有两处——`05` `rl init` 签名行里「问一次要不要给 idea 发 `read:notes`」那半句、`05` 接口一节「`read:notes` 的申请走法」一行，同属获准机制砍掉，最后一期一起删。）
- 原冻结句：`05-rl-cli.md` L39「| `rl init` | 在研究仓库建 `research-loop.json`、`loop/` 九本账、`experiments/`、`analysis/`（含公共统计件模板和 `analysis/scratch/`）、`review/`、`notes/`，往 CLAUDE.md 追加一节（三句），问一次要不要给 idea 发 `read:notes`；读到会话状态文件就拒收，退出码 3，提示换裸终端跑 | gyb，只在裸终端 |」
- 备注：同一笔的两处连带里的第一处，sync-inbox 原文没有单独编号，本对照单按施工交代拆成 (a2)。`rl init` 的产物按施工指南 L104 归步 7、今天不做，但 `rl init` 的子命令签名本身在 `bin/rl` 里，删的是签名行里那半句提问。测试侧无落点：测试 9 只测「`rl init` 在角色会话里跑退出码 3」（30 L103），不涉这句提问。

### 43(a3) 状态 settled

- 代码落点：`none`（05 接口一节指向 10-role-idea.md 的一行交叉引用，删掉只动设计文字；这一行指的两样东西（rl init 那次提问、doctor 第 16 项）本身的代码落点已经记在 (a2) 和 (a)）
- 新口径：sync-inbox L312: （统筹补扫 2026-08-21 rl-hub-v6：(a) 的连带还有两处——`05` `rl init` 签名行里「问一次要不要给 idea 发 `read:notes`」那半句、`05` 接口一节「`read:notes` 的申请走法」一行，同属获准机制砍掉，最后一期一起删。）
- 原冻结句：`05-rl-cli.md` L237「- `read:notes` 的申请走法（`rl init` 问的那一次和 doctor 第 16 项）：`10-role-idea.md`。」
- 备注：同一笔的两处连带里的第二处，sync-inbox 原文没有单独编号，本对照单按施工交代拆成 (a3)。这一行就是 sync-inbox L195 (g) 点名「不跟着漂」的 `05:237`，删整行之后项号引用问题一并消失。grep 三份冻结件「第 16 项」只命中这一行。

### 43(b) 状态 settled

- 代码落点：`research-loop/bin/rl`（status subcommand: with --group-by line, a handoff whose decision_refs span several root decisions is printed under every related line, not only under the first one; --line L filtering matches on the same rule）；`research-loop/tests/`（测试 11（`rl status`、`rl inbox` 与 `rl reclaim`）：原文的「`--line` 过滤对」一句加一个跨根用例——一张 decision_refs 分属两条根决定的单子，--group-by line 时两条线下面都出现，--line 过滤两条线各自都命中）
- 新口径：sync-inbox L311: （b）`05` `rl status --group-by line` 改「跨根的单在每条相关线里都出现」
- 原冻结句：`05-rl-cli.md` L166「第一行打印距上次 reclaim 几天。整份可以按 `--line` 过滤、按 `--group-by line|batch` 归组；`line` 就是根决定编号。」
- 原冻结句：`05-rl-cli.md` L93「| `rl status [--line L] [--group-by line\|batch] [--json]` | gyb 的收件箱十段，见下一节；第一行打印距上次 reclaim 几天 | 谁都行 |」
- 备注：裁决来源是 gyb 2026-08-21「允许，两边都算」（跨根单归线，sync-inbox L300）。签名行 05 L93 不用改字，改的是 L166 的语义句。这一笔是「视图侧」，字段侧是 (d)。另有问题 41 的统筹补扫 (h)（sync-inbox L295）也动 05 L166 附近（段 9 那句「没关的快车道不归线，单独列一堆」，落点 `05:163`/`05:166`），落地时两笔在同一段，注意别互相盖掉。

### 43(c) 状态 pending，标记 `PENDING(issue 43c)`

- 代码落点：`research-loop/tables/ledgers.json`（keep the grants row (中文名 授权 / 英文名 grants / 文件 loop/grants.jsonl) and mark it PENDING(issue 43c); the ledger list stays at nine rows）
- 新口径：sync-inbox L311: （c）`05` `rl grant` 子命令与 `03` grants 账的存废（permission 第一版只有 `read:notes` 一种，机制砍掉后账里没有内容）请统筹按定义处问 gyb
- 原冻结句：`03-ledgers.md` L53「| 授权 | grants | `loop/grants.jsonl` |」
- 原冻结句：`03-ledgers.md` L128「授权只有 gyb 能写：`actor` 必须是 `gyb`。裸终端直接写；角色会话里 `--as-gyb --quote` 替 gyb 写也收，`session_id` 照记那个会话（2026-08-17 gyb 裁，sync-inbox 问题 27，原话「3 不是，可以替我写」；施工计划第一节 (d)「grants 只收裸终端」不认）。`status` 取 `active`、`revoked`。」
- 原冻结句：`03-ledgers.md` L134「| `permission` | 字符串，第一版只有 `read:notes` 一种 | 必填 |」
- 原冻结句：`05-rl-cli.md` L79「| `rl grant add --to R --permission P --text ... [--expires ...] [--issue ID]` / `rl grant revoke ID` / `rl grant list` / `rl grant show ID` | 授权；裸终端直接写，角色会话里 `--as-gyb --quote` 替 gyb 写也收（问题 27） | 写 gyb，查谁都行 |」
- 备注：今天的代裁是 D-01「授权账（grants）今天留位不建立」（plans/2026-09-04-research-loop-proxy-decisions.md 第 17 到 23 行）：`tables/ledgers.json` 里保留 grants 这一行并标 `PENDING(问题 43c)`；不写 grants 的 schema、不写 `rl grant` 子命令、测试 9 里 grant 相关的用例标跳过。理由是留位不建立改动最小，留和砍两个方向到最后一期都还能走。标记的字面按 D-09（同文件 L81-84）改成英文形式 `PENDING(issue 43c)`。因此本笔另外三处「不建立」的地方（`research-loop/schemas/grants.schema.json` 不写、`research-loop/bin/rl` 不写 grant 子命令、`research-loop/tests/` 测试 9 里 grant 的用例标跳过）按施工交代不进 landing，只记在这里。测试 9 现文涉 grant 的用例见 30 L96、L98：「analysis 调 `rl grant add` 退出码 3」「裸终端 `rl grant add` 通过」「角色会话里 `--as-gyb --quote` 替 gyb 写 grant 也收」。

### 43(d) 状态 settled

- 代码落点：`research-loop/schemas/handoffs.schema.json`（the `line` field: computed by rl from decision_refs' root_id; decision_refs may span different root decisions, so a cross-root handoff belongs to every related line; whether `line` is stored as one value or a list is PENDING(part 04 L27)）；`research-loop/scripts/rl_lib.py`（line computation no longer takes only decision_refs[0].root_id; every root id of a cross-root handoff must be reachable by the line views; the stored shape (one value or a list) is PENDING(part 04 L27)）
- 新口径：sync-inbox L311: （d）`03` `line` 字段语义改「`decision_refs` 可分属不同根决定，跨根的单在每条相关线的视图里都出现」 ／ sync-inbox L313: - 统筹补扫 2026-08-21（评审修复，gyb 授权）：(d) 的 `line` 是 handoffs 字段，定义处是 `04`（`03` 里没有这个字段），落点从 `03` 改 `04`——`04` 字段表 `line` 的语义句照 (d) 的内容改。
- 原冻结句：`04-handoffs-and-sessions.md` L27「| `line` | 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着 |」
- 原冻结句：`04-handoffs-and-sessions.md` L219「- 决定账的 `root_id`、`{"id","version"}` 引用格式、`--decision ID@V`：定义在 `02-decisions.md`（原文指 `03`，按 HANDOFF 四点五节改指 `02`）；handoffs 的 `line` 字段从 `root_id` 算出来，`reissue` 那一行用 `ID@V`。」
- 备注：落点已按 sync-inbox L313 从 `03` 改到 `04`——`03` 里没有 `line` 这个字段（grep 03-ledgers.md 无 `line` 字段行），handoffs 字段表在 `04` 第一节。schema 的账名按 03 L51「派活单 handoffs `loop/handoffs.jsonl`」写成 handoffs.schema.json。视图侧是 (b)。形状：现文 04 L27 只写「由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着」，取的是第一项、存的是一个值；新口径「可分属不同根决定」之后 `line` 存一个值还是一个列表，sync-inbox L311/L313 和 04 现文都没写——形状现文没定，代码按 PENDING(part 04 L27) 标。测试侧另有两处现文提到 `line`：30 L118「`run list --decision` 和 `--line` 经 `handoff_id` 反查 handoffs 的 `decision_refs` 和 `line`」（测试 10）、30 L122「`--line` 过滤对」（测试 11），跨根用例记在 (b) 的落点里。

### 43(e) 状态 settled

- 代码落点：`research-loop/tables/transitions.json`（row done_pending_review -> accepted: keep 谁能写 as owner (quick-lane make-up orders gyb only) and add the note that a handoff with dispatch=manual is accepted by gyb himself by default, with the fyi to owner still sent）；`research-loop/tests/`（测试 2（转移表）：done_pending_review -> accepted 那一行的用例加一条 dispatch=manual 的单子由 gyb accept 通过；owner accept 仍然通过）；`research-loop/tests/`（测试 15（收回与接替）：现文已有「gyb 越过 owner 验收和打回都给 owner 发 `fyi`」（30 L154），dispatch=manual 的单子 gyb 验收时 fyi 照发，用例按此加一条）
- 新口径：sync-inbox L311: （e）`04` 转移表 `done_pending_review`→`accepted` 行「验收人是 owner」补备注「`dispatch=manual` 的单默认 gyb 自己验收，`fyi` 照发」。
- 原冻结句：`04-handoffs-and-sessions.md` L70「| `done_pending_review` | `accepted` | owner；快车道补单只有 gyb | 无；gyb 越过 owner 时 rl 给 owner 发 `fyi`；rl 顺带关这张单关联的 `answered` issue（`03` 定） | 无 | `handoff accept` |」
- 原冻结句：`04-handoffs-and-sessions.md` L112「验收人是 owner。gyb 随时可以自己验：先读不带文件的那一份看做法对不对，再读带文件的那一份看写出来的东西和说的是不是一回事，打回要写明原因。gyb 越过 owner 验收或打回时 rl 给 owner 发一条 fyi 通知。快车道补单是唯一一种验收人固定的单子，只有 gyb 能 accept。」
- 原冻结句：`04-handoffs-and-sessions.md` L88「`manual` 由开单时的 `--manual` 写进去，上游只开单，gyb 自己开 session 去接，owner 不起 subagent。`none` 由 `--no-dispatch` 写进去，单子停在 `todo` 等 gyb 说开跑。」
- 备注：裁决来源是 gyb 2026-08-21「你干完自己算数」（--manual 单验收，sync-inbox L300）。sync-inbox 点的是转移表那一行，而「验收人是 owner」这五个字逐字出现在 04 第五节 L112，转移表 L70 的对应栏写的是「owner；快车道补单只有 gyb」，两处都抄下来了；`dispatch=manual` 的定义在 04 L84、L88（「gyb 亲自接」「上游只开单，gyb 自己开 session 去接，owner 不起 subagent」）。04 现文没有 `dispatch=manual` 验收人的同义句（grep manual 命中 L61、L84、L88、L140、L146、L151、L152 和 L372 起的评审段，都不是验收人句），属纯新增；问题 41 的统筹补扫 (i)（sync-inbox L295，原话针对 41(d)）「落地时先核对、已有就只核不加」这条核对法在这里照做了，结论是没有。新备注和 L112 末句的关系：新备注的字是「默认」，L112 末句的字是「固定」，新备注没动转移表 L70「谁能写」一栏（owner；快车道补单只有 gyb），owner 仍能 accept `dispatch=manual` 的单，所以「快车道补单是唯一一种验收人固定的单子」在加了新备注之后仍然成立。两句是补充关系，L112 那句不用改；「`fyi` 照发」对应的就是 L112「gyb 越过 owner 验收或打回时 rl 给 owner 发一条 fyi 通知」和 L70「gyb 越过 owner 时 rl 给 owner 发 `fyi`」，机制现文已有。

读手没能定的：无。读手原来的两条：一、(e) 新备注与 04 L112「唯一一种验收人固定」的关系已按现文判成补充（默认不等于固定，owner 仍能验收），记在 (e) 的 note；二、(d) `line` 字段的存储形状现文没定，按施工交代记成「代码按 PENDING(part 04 L27) 标」，记在 (d) 的 note 和两条 landing 里。

核手的话：核对方法：sync-inbox L295、L300、L307-314 逐字比过；05 L39、L79、L93、L166、L191、L210、L221、L237，03 L51、L53、L128、L134、L240，04 L27、L61、L70、L84、L88、L112、L219 逐字比过，行号全对；30 L96、L98、L103、L118、L122、L154、L225，施工指南 L96、L104，代裁记录 D-01（L17-23）、D-09（L81-84）都读了，读手引用属实；grep 03/04/05「十九项」只命中 05 L191、05 L221、03 L240，grep 三份冻结件「第 16 项」只命中 05 L237，读手没有漏抄。六个子项的 new_wording 全部是 sync-inbox 原句逐字截取；landing 路径全部在清单内；status 与 pending_ref 按规矩核对无误（只有 (c) 是 pending、issue 43c、落点 ledgers.json）。改了六处：1. (b) note「问题 42 的 (h)」改成「问题 41 的统筹补扫 (h)（sync-inbox L295）」——(h)(i)(j) 三条在 L295，属问题 41（07 定稿动冻结三份那一段，L290-296），问题 42 在 L302、只有 (a) 到 (f)。2. (d) 两条 landing 的 what 末尾加「存储形状 PENDING(part 04 L27)」——读手原文写成「carries every related root id」，等于预设了列表形状，现文没定。3. (d) note 加形状判定：04 L27 现文取第一项存一个值，新口径没写形状，代码按 PENDING(part 04 L27) 标。4. (e) note「问题 42 的 (i)」改成「问题 41 的统筹补扫 (i)（原话针对 41(d)）」，grep manual 的命中清单补上漏掉的 L152（`end_reason` 记 `manual`）。5. (e) frozen_original 补 04 L88（`dispatch=manual` 的定义句，子项点名的 `dispatch=manual` 在冻结件里的出处），note 加两句补充/冲突判定：新备注是「默认」、L112 是「固定」、「谁能写」栏不动、owner 仍能验收，L112「唯一一种」仍成立，判成补充，status 维持 settled。L112 整句读手本来就抄全了，没有再补。6. unresolved 两条按第 5 项交代销掉，改写成销案说明。

## 问题 45（sync-inbox L325-331，核手核过）

### 45(a) 状态 settled

- 代码落点：`research-loop/schemas/handoffs.schema.json`（字段表加顶层 `track` 一栏（方向名，`work_order` 开单时由 idea 填、开单必填）；`launch_order` 不加顶层 `track` 栏，它的方向名仍只在 `attempts[].track`（04 L38 的 attempts 内层栏不动））；`research-loop/tables/transitions.json`（（新建）→ `todo` 那一行的前提栏：`work_order` 一支加「有 `track`」；`launch_order` 一支写明第一次尝试的 `track` 由 rl 从父单顶层 `track` 抄，和 decision_refs、batch 一起抄）；`research-loop/scripts/rl_lib.py`（handoffs 按 status 的必填校验加「`work_order` 开单必填 `track`」；开 `launch_order` 时把父单顶层 `track` 抄进 `attempts[0].track` 的抄录逻辑，和抄 decision_refs、batch 同一处）；`research-loop/bin/rl`（`handoff open` 子命令：`--track` 对 `work_order` 收方向名写进顶层栏；对 `launch_order` 不写顶层栏，从父单顶层 `track` 抄进第一次尝试）；`research-loop/tests/`（测试 2（转移表，（新建）→ `todo` 的前提用例）加两条：`work_order` 开单缺 `track` 拒收退出码 2；`launch_order` 开单不给 `--track` 时 `attempts[0].track` 等于父单顶层 `track`）
- 新口径：sync-inbox L329: （a）`04` handoffs 字段表 `work_order` 加 `track` 一栏（idea 开单时填），`launch_order` 开单从父单抄 `track`
- 原冻结句：`04-handoffs-and-sessions.md` L38「| `attempts` | 列表只在 `launch_order` 上，每项 `{"attempt":序号,"command","args","workdir","track","config":{...},"run_id","estimated_seconds","actual_seconds","step_table":[...]}` |」
- 原冻结句：`04-handoffs-and-sessions.md` L43「`attempts` 里面还有两条细规矩：开单时第一项必填 `command`、`workdir`、`track`、`config`（字典：`model`、`params`、`dataset`、`split`、其余超参自由），`run_id` 由 rl 按 `<ho-id>-a<attempt>` 分配；`step_table` 每项是 `{"step","kind":"gpu"|"cpu","smoke_seconds","scale_factor","estimated_seconds"}`，`estimated_seconds` 只加总最新一次尝试的行。真实耗时人不填：`rl run finish` 从时间戳算出写进 runs 的 finish 版，同时由 rl 抄进发射单最新一次尝试的 `actual_seconds`，预计和实际在同一张单上对着看；`handoff done` 不带 `--actual-seconds`（2026-08-17 gyb 裁）。一张发射单可以跑几次，每一次是单子上的一个 attempt，这条是原则 10，详细的跑法在 `12-role-run.md` 和 `21-pair-deploy-run.md`。」
- 原冻结句：`04-handoffs-and-sessions.md` L61「| （新建） | `todo` | `from_role` | `work_order` 有 `decision_refs` 和 `explanation`；`launch_order` 有 `parent_id` 和第一次尝试的 `command`、`workdir`、`track`、`config`；`analysis_order` 有 `evaluation_refs`（可以是 proposed） | `dispatch=auto` 时 owner 后台起 subagent；`manual` 等 gyb；`none` 不动 | `handoff open` |」
- 备注：统筹补扫 (f) 逐字（sync-inbox L330）：「(f) (a) 的 `track` 与 `04` attempts 里已有的 `track` 同名同义——`work_order` 加顶层 `track`（idea 开单填），`launch_order` 不另加顶层栏，开单时从父单顶层 `track` 抄进第一次尝试的 `attempts[].track`，两处一个意思。」本条按补扫之后的口径写：只有 `work_order` 加顶层栏，`launch_order` 不加顶层栏、只抄进 attempts。顶层 `track` 这一栏在 04 第一节字段表（L15-41）里现在没有对应行，这半边是纯新增；`launch_order` 从父单抄这半边落在现有的 L61 前提行和 L43 的 attempts 细规矩上。裁决原话在 sync-inbox L318（本段 L327 写「同上一段」）：gyb 2026-08-21「工单格式里加一个位置」（方向名 track 从工单继承）。「必填」这一点是代裁 D-10（plans/2026-09-04-research-loop-proxy-decisions.md L89-94，底座助手提、统筹裁）：`work_order` 开单时 `track` 必填，依据是 04 L43「开单时第一项必填 `command`、`workdir`、`track`、`config`」加 11 L76「| `track` | deploy 填，从父单抄 | 宿主发射器要的方向名。工单格式里加方向名一栏，idea 开工单时填，发射单开单时照抄（2026-08-21 gyb 裁；工单加栏动 `04` 的字段表，冻结、等最后一期，见「要同步到别处的」） |」——没有 `track` 的工单下面永远开不出发射单，所以在工单开单这一步就要；D-10 的落点栏另写「sync-inbox 问题 48(b) 记最后一期要落进 04 字段表」。角色说明书那一侧（idea 开单填、deploy 照抄）归 sync-inbox 问题 44(b)，2026-08-21 已落进 `10`、`20`、`21`，本笔不重复列。v2 树现状（2026-09-05 核）：research-loop/tables/transitions.json 第 22、23 行已按本口径落进（前提 id `open.work_order_has_track` 与 `open.launch_order_first_attempt`，source 记 Q45(a)(f) L329-330 和 proxy decision D-10）；research-loop/schemas/handoffs.schema.json 已经写出来了，第 45 行有顶层 `track`（description 写 work_order 由 idea 开单填、launch_order 只在 attempts[].track），第 18 行 attempts 内层 `track` 写「copied from the parent work_order's top-level track」，第 65 行 work_order 的 then_required 含 `track`。

### 45(b) 状态 settled

- 代码落点：`research-loop/tables/transitions.json`（withdraw 那一行（转到 `withdrawn`）补这一句：收回时 holder 把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定。它是压在 holder 身上的纪律、rl 查不了，所以落在这一行的 side_effects 一栏而不是能校验的前提栏）；`research-loop/bin/rl`（`handoff withdraw`：从 `in_progress` 收回时 rl 顺带开的那条 `withdrawn` 通知（04 L74、L194，收件人是 holder 的角色和 owner）的正文带这一句，提醒 holder 把已写的代码位置和半截产物目录路径回进这条 issue、东西不动、处置由 gyb 定。只是提示不是校验：05 L65 的 `withdraw ID --reason [--quote] [--cascade]` 是 owner 调的命令，holder 回没回 rl 查不了，所以不加前提、不加退出码）；`research-loop/skills/deploy/SKILL.md`（自己手上的单子被收回（收到 `withdrawn` 通知）时：把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定；回完按 05 L138 自己 `rl issue close`。deploy 是 holder：06 L192 ledger_writes 含 handoffs 的 start）；`research-loop/skills/run/SKILL.md`（同上一条：run 是 holder（06 L204 ledger_writes 含 handoffs 的 start），被收回的是 `launch_order`，半截产物目录在 `artifact_root`。run 能不能往 issue 回话见 unresolved）；`research-loop/skills/analysis/SKILL.md`（同上一条：analysis 是 holder（06 L218 ledger_writes 含 handoffs 的 start），被收回的是 `analysis_order`，半截产物在 `analysis/`）
- 新口径：sync-inbox L329: （b）`04` withdraw 一侧补一句「收回时 holder 把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定」
- 原冻结句：`04-handoffs-and-sessions.md` L74「| `todo` / `in_progress` / `stuck` / `done_pending_review` / `rejected` | `withdrawn` | owner | `reason` 非空（角色会话发起还要 `quote`）；从 `in_progress` 收回时 rl 顺带开 `withdrawn` 通知给 holder 的角色和 owner，其他状态不通知；`--cascade` 时 rl 代 owner 连 `parent_id` 指向本单的下游单一起收，下游账行 actor 记发起人 | 无 | `handoff withdraw` |」
- 原冻结句：`04-handoffs-and-sessions.md` L194「| `withdrawn` | 从 `in_progress` 收回一张单子时；其他状态收回不通知 | holder 的角色和 owner | 你手上的单子被收回了 |」
- 原冻结句：`04-handoffs-and-sessions.md` L370「   - 改法：转移表转到 `withdrawn` 那一行的前提栏补一句：holder 在返回前把半截产物路径写进那条 withdrawn issue，处置由 gyb 定。」
- 备注：裁决原话在 sync-inbox L318（本段 L327 写「同上一段」）：gyb 2026-08-21「报位置、留着不动，处置由你定」（收回后的半截产物）。子项句子里的「处置由 gyb 定」是要写进 issue 的那句纪律的内容——半截产物留着不动、以后怎么处置由 gyb 决定——不是这个子项本身还没裁，所以 settled。04 现文的 withdraw 一侧有三处：转移表 L74（正文规矩）、第九节通知表 L194（withdrawn 通知的触发点与收件人）、L370 是第二轮互查报告 gyb-manual-takeover 之外那一段的第 18 条改法（同一句内容的来源，属互查报告不属正文）。要补的这一句在正文里目前没有，正文这半边是纯新增。这句纪律的动作人是 holder，不是调 withdraw 的 owner：holder 是「当前正在干这张单子的那一个会话」（04 L49），进 `in_progress` 才写 holder（04 L51），所以能当 holder 的角色就是 06 五份 json 里 ledger_writes 含 handoffs 的 start 的那三个：deploy（L192）、run（L204）、analysis（L218）；idea（L180）的 handoffs 动作是 open/accept/reject/withdraw/release/reissue/resume/amend、没有 start，reviewer（L230）没有 handoffs，这两个不是 holder，不进落点。rl 查不了「holder 有没有回」，所以没有可写的前提用例，测试清单里不新增用例；测试 15（收回与接替）现有的用例不受影响。v2 树现状（2026-09-05 核）：research-loop/tables/transitions.json 第 192 行的 withdraw 行已把这句落进 side_effects，id `withdraw.holder_reports_partial_work`，source 记「sync-inbox Q45(b) L329 (discipline for the holder, not a check)」；research-loop/skills/ 目录现在是空的，三份角色 SKILL.md 都还没写。

### 45(c) 状态 settled

- 代码落点：`research-loop/tables/commands.json`（`handoff open` 那一行（05 L64 命令表的机器读副本）的签名：`--track T` 从 `launch_order` 专用的那一组参数（`--command ... --workdir ... --track ... --config k=v ...`）里提出来单列成 `[--track T]`，`work_order` 也能收；notes 写明 `launch_order` 不给 `--track` 时从父单顶层 `track` 抄进 `attempts[0].track`，所以发射单侧可省。参数解析本体在 research-loop/bin/rl，(a) 的落点已列，本条不重复）；`research-loop/scripts/rl_lib.py`（`handoff open` 的参数校验：`work_order` 缺 `--track` 报 validation（退出码 2）；`launch_order` 不给 `--track` 不报错，改走从父单抄的那条路）；`research-loop/tests/`（测试 2（转移表的开单前提用例）：`launch_order` 不带 `--track` 开单通过且 `attempts[0].track` 等于父单顶层 `track`，与 (a) 的用例是同一条）
- 新口径：sync-inbox L329: （c）`05` `rl handoff open --type work_order` 要能收方向名，`launch_order` 自动从父单抄之后发射单侧的方向名参数改可省
- 原冻结句：`05-rl-cli.md` L64「| `rl handoff open --type T --to R [--parent ID] [--decision ID@V ...] [--explain ...] [--eval ID@V ...] [--command ... --workdir ... --track ... --config k=v ...] [--batch B] [--manual\|--no-dispatch] [--quick-lane --report-method P --ql QL]` | 开单，落 `todo`；`launch_order` 从父单抄 decision_refs 和 batch、分 run_id；`--batch` 是调用者的自由文本，rl 不分配；带 `--quick-lane` 的工单直接落 `done_pending_review`，`QL` 存进单子的 `ql_tag` 栏（04 定），补单前提是关联的 scratch 行状态是 `open` | owner；快车道补单是 deploy 调、owner 记 gyb（04 第 62 行） |」
- 备注：这一条是 (a)(f) 的命令行侧落地，裁决原话同 (a)（sync-inbox L318 的「工单格式里加一个位置」），本子项自己没有单独的 gyb 原话。`--track` 在 05 现文里只出现两处：L64 的 `handoff open`（本子项要改的那一处）和 L65 的 `handoff amend`（原文片段：「`amend ID [--command ... --workdir ... --track ... --config ...]`」），子项没点 amend，按不改记。命令表的实体是 research-loop/tables/commands.json（代裁 D-12 允许 tables/ 多这三份表，`bin/rl` 的子命令分发读命令表），落点按此写。v2 树现状（2026-09-05 核）：research-loop/tables/commands.json 第 35 行已按新口径改写签名（`[--track T]` 单列出来，notes 里写明 work_order 收方向名、launch_order 从父单抄进 attempts[0].track 所以发射单侧可省，_source 记「05 L64; sync-inbox Q45(c) L329」）；第 37 行 `handoff amend` 的签名仍带 `--track ...`，与本条不动 amend 一致。

### 45(d) 状态 settled

- 代码落点：`research-loop/schemas/handoffs.schema.json`（`code_paths` 字段的说明改成全收口径：这张单改过的代码路径不论在不在 `experiments/` 里都列，宿主文件也算。必填规则不动（`work_order` 进 `done_pending_review` 时必填、非空））
- 新口径：sync-inbox L329: （d）`03` `code_paths` 字段说明补「全收：这张单改过的代码路径不论在不在 `experiments/` 里都列，宿主文件也算」
- 原冻结句：`04-handoffs-and-sessions.md` L36「| `code_paths` | 列表（`work_order` 进 `done_pending_review` 时必填） |」
- 备注：统筹补扫 (e) 逐字（sync-inbox L330）：「(e) (d) 的 `code_paths` 是 handoffs 字段，定义处是 `04`（`03` 里没有这个字段），落点从 `03` 改 `04`」。所以本条按落点 `04` 写，子项原话里的 `03` 作废。`03-ledgers.md` 现文提到 code_paths 的只有两处指过去的句子（L96：「派活单的字段级行格式（`work_type`、`from_role`（就是 owner）与 `holder`、`parent_id`、`attempts`、`report_paths`、`code_paths`、`output_paths` 这些）和七个状态的转移表写在 `04-handoffs-and-sessions.md`。」；L236 同类），没有字段定义，与 (e) 说的一致。裁决原话在 sync-inbox L318（本段 L327 写「同上一段」）：gyb 2026-08-21「全收」（code_paths 含宿主文件）。「全收」是口径说明不是 rl 能校验的东西——rl 查不了列全没列全，只查非空，所以测试清单不新增用例，测试 4 现有的「`work_order` 缺任一报告路径或 code_paths 拒收」不受影响。reviewer 按全量口径读代码清单那一侧归 sync-inbox 问题 44(c)，2026-08-21 已落进 `25` 和 `14`，本笔不重复列。v2 树现状（2026-09-05 核）：research-loop/schemas/handoffs.schema.json 已经写出来了，第 50 行 `code_paths` 的 description 写「lists every code path this order changed, host files included (04 L36; sync-inbox Q45(d))」，全收口径已落；tables/transitions.json 第 113 行的 `done.work_order_deliverables` 只写 code_paths 非空，没写全收口径（全收是字段说明，归 schema），这样分工是对的。

读手没能定的：一点。(b) 的落点 research-loop/skills/run/SKILL.md 要 run 把代码位置和半截产物目录路径「回进那条 `withdrawn` issue」，可是 06 L204 run 的 ledger_writes 是「runs 全部、handoffs 的 start/estimate/done/stuck、issues 的 open、decisions.run add（自决极少，比如挑卡的理由）、feedback add」——issues 只有 open，没有 reply 也没有 close；而 03 L92 写「`reply` 只有 `assignee` 或 gyb 能写」「通知类 issue（`withdrawn`、`orphaned`、`fyi`）的 `assignee` 也能关」，withdrawn 通知的收件人是「holder 的角色和 owner」（04 L194），run 是 assignee。按 03 run 能回能关，按 06 的 run 那份 json 钩子会拦。deploy（06 L192 issues 全部）和 analysis（06 L218 issues 的 open/reply/close）没有这个问题。run 侧这句纪律怎么落（06 的 run 行加 issues 的 reply/close，还是 run 用别的方式报位置）我判不了，留给统筹或最后一期。

核手的话：核对结果与改动。核过没改的：四条 new_wording 与 sync-inbox L329 逐字相符；frozen_original 八条引文（04 L38、L43、L61、L74、L194、L370、L36，05 L64）与现文逐字相符、行号相符（05 L64 的 `\\|` 在 JSON 里解出来正是现文的 `\|`）；(d) 的定义处按补扫 (e) 落在 04 L36、落点 schemas/handoffs.schema.json，读手已对；(c) 的 `--track` 在 05 里只有 L64、L65 两处，grep 核过；四条 status settled、pending_ref 空，读手已对。改了六处。一、(a) note：加代裁 D-10（proxy-decisions L89-94，必填的依据 04 L43 加 11 L76，11 L76 引了原句），并把 v2 树现状从「schemas/ 只有 .gitkeep」改成现在的样子（handoffs.schema.json 已存在，第 45、18、65 行落了 track）。二、(b) landing：加 research-loop/bin/rl（withdraw 从 in_progress 收回时 rl 开的 withdrawn 通知正文带这句，提示不是校验，依据 04 L74、L194 和 05 L65）和三份 SKILL.md（deploy/run/analysis，holder 判定依据 06 L192、L204、L218 的 ledger_writes 含 handoffs 的 start；idea L180 没 start、reviewer L230 没 handoffs，排除）。三、(b) note：写明「处置由 gyb 定」是纪律内容不是待裁，加 holder 三角色的依据，v2 树现状补 transitions.json 第 192 行和 skills/ 目录为空。四、(c) landing：research-loop/bin/rl 改成 research-loop/tables/commands.json（清单现在有这条路径；参数解析本体已在 (a) 的 bin/rl 落点里，不重复），note 里删掉「不在清单里」那句、补 D-12 与第 37 行 amend 不动。五、(d) note：v2 树现状改成 schema 已存在、第 50 行已落全收口径。六、unresolved：读手四点里的一（「等最后一期」是冻结正文的禁改令，四条裁决原话在 L318，settled）、二（「处置由 gyb 定」是纪律内容）、三（三份 SKILL.md 要进，按指示落）、四（命令表实体现在在清单里）全部收掉；新留一点：run 的 ledger_writes（06 L204）没有 issues 的 reply/close，与 03 L92 的 assignee 能回能关不一致，run 作为 holder 怎么把位置回进 withdrawn issue 我判不了。

## 问题 47（sync-inbox L344-349，核手核过）

### 47(a) 状态 settled

- 代码落点：`none`（只改 03「和别的 part 的接口」一节的指向句措辞，代码不变）
- 新口径：sync-inbox L348: （a）`03:242`「合回六步的顺序（先开补单再 `ql close --merged`）」——`07` 里没有「六步」这个说法，改成「合回的出口顺序（gyb 先 merge → deploy 开补单、补 `decisions.deploy` → `ql close --merged --handoff ID`），见 `07` 出口一节」（问题 44(a) 已确认此序）。
- 原冻结句：`03-ledgers.md` L242「- `ql_tag` 的分配、scratch 三态的开张关张动作（`rl ql open`、`rl ql close`）、合回六步的顺序（先开补单再 `ql close --merged`）、analysis 的快车道只有 `--dropped`、analysis 的快车道 `base_commit` 和 `branch` 两栏填什么，在 `07-quick-lane.md`。本份定的是：中间版 `status` 仍是 `open`，校验头尾查中间不查，`merged` 版必填 `handoff_id` 与补单的 `ql_tag` 互指，快车道数字不进 runs。」
- 备注：评审修复代裁，gyb 可否。行号未漂，现文 03 L242 就是这句。出口顺序本身的代码落点已经写好、不由这一笔带出：research-loop/tables/transitions.json 的 open_quick_lane 行前提 ql.scratch_row_open 写着「the supplement is opened first, then `rl ql close --merged --handoff ID` closes the scratch row」（源 04 L62、07 L88），research-loop/tables/commands.json 的 ql close 行写着 --merged 要求 ID 是 quick_lane 补单且 ql_tag 等于 QL；补 decisions.deploy 那一步在 07 出口一节。

### 47(b) 状态 settled

- 代码落点：`research-loop/hooks/`（销号钩子（挂 SessionEnd 和 SubagentStop，04 L120、04 L223）按此写序：先逐张 release，最后写 sessions 的 closed 版）；`research-loop/bin/rl`（`rl session end`（含 `--session ID`）：release 交回全部走在前，sessions closed 版（带 released_handoffs）落最后一步）；`research-loop/scripts/rl_lib.py`（「写账的会话得活着」这条入账校验（03 L15）按此序自然放行销号钩子写的 release 行——release 落账时 sessions 最新版还是 open）；`research-loop/tests/`（测试 7（销号，30 L76-86）加一条写序用例：release 行的 ts 早于 sessions closed 版、release 行的 session_id 是本会话且不被退出码 3 拒收）
- 新口径：sync-inbox L348: （b）`04` 第六节销号钩子那段补一句跨账写序：「先逐张 release 交回（release 行的 `session_id` 记本会话，此刻 sessions 还没 `closed`，写得进），最后落 sessions 的 `closed` 版（含 `released_handoffs` 清单）」——`03:15` 已明写此序并说「`04` 第六节定的顺序」，`04` 补上这句指向才成立。
- 原冻结句：`03-ledgers.md` L15「写账的会话得活着：一条写命令的 `session_id` 在 sessions 账里最新版是 `closed` 的，rl 拒收并提示「会话已被销号，重新加载角色登记」，退出码 3；`--force`、`--as-gyb --force` 都越不过这条，唯一出路是重新加载角色（2026-08-17 gyb 裁，事情本身在 `04-handoffs-and-sessions.md` 第七节 `rl session end --session ID` 那条；这条校验的定义处是本份，sync-inbox 问题 5；退出码和越不过是问题 14）。销号钩子自己写的那些 release 行不会被这条拒掉：`04` 第六节定的顺序是先把名下开干的单子交回待干（release 行的 `session_id` 记那个会话），最后才落 sessions 的 `closed` 版。」
- 原冻结句：`04-handoffs-and-sessions.md` L122「销号那一刻程序当场检查这个会话作为 holder 有没有还挂在开干的单子，只查开干，别的状态一律放行。有开干的单子就不许悄悄下线，名下有几张开干的就交回几张，一张不留（比如 run 会话 `--batch` 接下的整批一起交回），交回的编号全部记进 sessions 账 `released_handoffs`（2026-08-17 gyb 裁）。钩子调的销号对每一张做四件事：」
- 备注：评审修复代裁，gyb 可否。04 第六节现文（L116 到 L129）没有对应句子，这一句对 04 是纯新增；插入点在 L122 末尾「钩子调的销号对每一张做四件事：」与 L124 的四件事清单之间，或紧跟四件事清单之后。frozen_original 里列的 03 L15 是子项点名的那一行（行号未漂）、04 L122 是插入点上下文，不是被改写的句子。sessions 的 closed 版必填 released_handoffs 已由行格式表定死（03 L190、04 L147），落进 research-loop/schemas/sessions.schema.json 的是那条必填规则，不是本子项新加的东西。

### 47(c) 状态 settled

- 代码落点：`research-loop/tables/roles/reviewer.json`（核对结论：reads 已含 scratch（照抄 06 L228），与新口径一致，不改）；`research-loop/tables/roles/analysis.json`（核对结论：reads 已含 scratch（06 L216，2026-08-21 评审修复加进）、ledger_writes 的 scratch 是 "*"（06 L218「scratch 全部」），notes 第一条是英文原文「scratch: only the rows of its own ql_tag, only in the quick lane (06 L222)」，与新口径一致，不改）；`none`（03 L196 那一句的措辞改动本身没有代码落点）
- 新口径：sync-inbox L348: （c）`03:196` scratch 段「analysis 和 reviewer 默认不读这本账」改成「这本账日常不进审读顺序：deploy 和 analysis 只在快车道里读写自己那条 `ql_tag` 的行，reviewer 审快车道时才读（reads 清单里有）」——`06` 定稿的 json 里 reviewer 的 reads 有 scratch、analysis 的 ledger_writes 有 scratch 全部（`07:64` 同句 2026-08-21 已按此改，写了两遍处）。
- 原冻结句：`03-ledgers.md` L196「杂账只有快车道写，记快车道的开张、数字、关张。主键是 `ql_tag`。`status` 取 `open`、`merged`、`dropped`，中间追加数字的每一版 `status` 仍是 `open`（跑了一次不是状态变化，是开着的时候发生的事，不设第四态）。`actor` 是 `deploy` 或 `analysis`。analysis 和 reviewer 默认不读这本账。」
- 原冻结句：`07-quick-lane.md` L64「杂账只有快车道写，只写三样事：开张、数字、关张。中间版格式松，只校验骨架和 `ql_tag`；`open`、`merged`、`dropped` 三版按表查必填。中间追加数字的每一版 `status` 仍是 `open`，不设第四态。这本账日常不进审读顺序：deploy 和 analysis 只在快车道里读写自己那条 ql_tag 的行，reviewer 审快车道时才读（reads 清单里有 scratch，见 `06`）。」
- 备注：评审修复代裁，gyb 可否。行号未漂：03 L196 现文就是被改的句子。07 L64 已经是新口径的同一句（2026-08-21 已改），03 这一处是「写了两遍」的另一处，改完两边同义。06 第 172 到 234 行核过：reviewer 的 reads 在 L228 有 scratch，analysis 的 reads 在 L216 有 scratch、ledger_writes 在 L218 有「scratch 全部」，deploy 的 reads 在 L190 有 scratch、备注 L196 写「scratch 只在快车道读写自己那条 ql_tag 的行」。核手打开两个 json 现文核实：research-loop/tables/roles/reviewer.json 的 reads 数组（文件第 3 到 7 行）含 "scratch"，_sources.reads 记「06 L228」；research-loop/tables/roles/analysis.json 的 reads 数组（文件第 3 行）含 "scratch"，ledger_writes 里 "scratch": "*"（第 9 行），notes[0] 是「scratch: only the rows of its own ql_tag, only in the quick lane (06 L222)」，_sources.reads 记「06 L216 (scratch added by the 2026-08-21 review fix, sync-inbox L341)」。读手说的「两个 json 的 reads 已含 scratch」属实。

### 47(d) 状态 settled

- 代码落点：`none`（两处都是 03 的指向句，各补半句括号，代码不变）
- 新口径：sync-inbox L348: （d）`03:4` 与 `03:240`「`rl status`……在 `05-rl-cli.md`」各补半句「（十段内容定义处是 `01`，`05` 是命令表）」。
- 原冻结句：`03-ledgers.md` L4「> 不覆盖的：decisions 的行格式、编号规则和来源三类写在 `02-decisions.md`；handoffs 的行格式和派活单状态转移表写在 `04-handoffs-and-sessions.md`，会话的登记、销号、回收也在那一份（这份只写 sessions 的行格式）；每条子命令怎么写、`rl status` 和 `rl inbox` 列什么、doctor 扫什么，都在 `05-rl-cli.md`；哪个角色能调哪条写命令在 `06-hooks-and-permissions.md`；快车道的进出动作在 `07-quick-lane.md`；阈值和配置文件在 `08-trees-init-and-host.md`；母版 `rules_version` 和反馈账的用法在 `09-common-and-feedback.md`。」
- 原冻结句：`03-ledgers.md` L240「- 每本账的写命令和查询命令清单、`rl trace`、`rl status`、`rl inbox`（只读不关）、`rl doctor`（十九项与修法；`--ack/--unack` 是写命令、只有 gyb）、`rl reclaim` 在 `05-rl-cli.md`；`rl run add` 的签名去掉 `--artifact-dir`（2026-08-17 裁）。`05` 的「锁与写序」一节和退出码表照抄本份，两边一字不差。」
- 备注：评审修复代裁，gyb 可否。行号未漂，03 L4 与 03 L240 现文都含「……在 `05-rl-cli.md`」。这半句对施工有一个抄录方向的提示（不算代码改动）：rl status 十段的内容定义在 01 第三、四节（01 L98-114 use case 表、01 L116 起「rl status：gyb 的收件箱」），research-loop/tables/gyb-usecases.json 的 _source 已经写的是「01 L98-114 (the table), 01 L116-135 (rl status ten sections and --json keys)」，与这半句一致；bin/rl 的 status 子命令写十段内容时照 01 抄，05 只出命令表与签名。

### 47(e) 状态 settled

- 代码落点：`none`（04「本份引用别处定义的」里的一句指向句，补半句括号，代码不变）
- 新口径：sync-inbox L348: （e）`04:220`「`rl status` 的十段全文……写在 `05-rl-cli.md`」同补这半句。
- 原冻结句：`04-handoffs-and-sessions.md` L220「- `bin/rl` 每条子命令的签名与「谁能调」、`rl status` 的十段全文、`rl inbox` 的五项、`rl trace`、`rl doctor` 的扫描项和修法：写在 `05-rl-cli.md`；本份只写 `rl handoff`、`rl session`、`rl reclaim` 三组子命令背后的判据和 status 段 7 的内容。」
- 备注：评审修复代裁，gyb 可否。行号未漂，04 L220 现文就是这句。补的半句与 (d) 同一句「（十段内容定义处是 `01`，`05` 是命令表）」，抄录方向的提示同 (d)。

### 47(f) 状态 settled

- 代码落点：`none`（04「本份是定义处的」里那句括号的标注修正，代码不变）
- 新口径：sync-inbox L348: （f）`04:209` 括号里那串「……待同步」补「（已同步 2026-08-17 夜 rl-hub-v3 `70c766b`，见文末「要同步到别处的」末条）」——正文标注与文末已同步标注打架，以文末为准。
- 原冻结句：`04-handoffs-and-sessions.md` L209「- 七个状态、holder 不变量（第二节）、`tables/transitions.json` 全表（第三节）、三种 dispatch（第四节）、三类单子的交付物与验收人（第五节）、销号钩子做的四件事（第六节）、`rl reclaim` 的处置（第八节）、三种通知的触发点与收件人（第九节）。`20`、`21`、`22` 三份角色对 part 各抄了转移表里自己那条通道的几行，判断规矩 2：改一处必改另一处，本份 2026-08-17 改动的行全部列在「要同步到别处的」（`in_progress` → `todo`、`done_pending_review` → `rejected` 两行已同步；新加的 estimate 行、start 行 `adopted`、两条 amend 行、快车道补单行前提、accept 行顺带关 issue、withdraw 行通知条件、reissue 行「到」栏待同步）。」
- 原冻结句：`04-handoffs-and-sessions.md` L560「- `20-pair-idea-deploy.md`（抄 idea→deploy 通道的行）、`21-pair-deploy-run.md`（抄 deploy→run 通道的行）、`22-pair-idea-analysis.md`（抄 idea→analysis 通道的行）抄的转移表要按本份第三节当前 HEAD 对齐这几行：新加的 `in_progress` → `in_progress` estimate 行（第 65 行，只有 21 用得上）；`todo` → `in_progress` start 行的 `adopted: true` 与 runs 同标（第 63 行）；两条 amend 行放宽后的允许内容（第 64、69 行）；快车道补单行前提改成 scratch 行是 `open`（第 62 行，20 用得上）；accept 行「rl 顺带关这张单关联的 `answered` issue」（第 70 行）；withdraw 行「从 `in_progress` 收回时通知，其他状态不通知」（第 74 行）；reissue 行「到」栏「旧单 `withdrawn`，新单 `todo`」（第 76 行）。来源：本份 2026-08-17 收 sync-inbox 问题 7、8、10、17、20、21 与三份互查第 4 条。——由统筹同步（rl-hub-v2 已列进 HANDOFF 第八节）。——已同步 2026-08-17 夜，rl-hub-v3 `70c766b`（20/21/22 抄的行按本份 HEAD 对齐；21 表里本来就没有 `done_pending_review` 的 amend 行、20 表里没有补单新建行，是抄表时就缺的，未补）。」
- 备注：评审修复代裁，gyb 可否。行号未漂：04 L209 现文括号末尾就是「reissue 行「到」栏待同步」；文末「要同步到别处的」的末条是现文 04 L560，末尾写着「——已同步 2026-08-17 夜，rl-hub-v3 `70c766b`」，与正文的「待同步」打架，按子项以文末为准。frozen_original 的第二条 04 L560 是「以文末为准」引的那一条，不是被改的句子。

核手的话：核手逐项核过。1. new_wording：六条 (a) 到 (f) 与 sync-inbox.md 第 348 行逐字相同，各条截的是同一行里自己那一段，无改动。2. frozen_original：03 L4、L15、L196、L240、L242，04 L122、L209、L220、L560，07 L64 共十条引文全部与现文逐字相同、行号相同（04 现文共 560 行，L560 是「要同步到别处的」一节（起于 L553）的末条，(f) 说「文末末条」属实），无改动。3. landing：路径全在允许清单内。(b) 的写序核对 03 L15 现文「`04` 第六节定的顺序是先把名下开干的单子交回待干（release 行的 `session_id` 记那个会话），最后才落 sessions 的 `closed` 版」与 04 第六节现文 L116 到 L129：04 那段只列销号对每张单做的四件事，没有 release 与 sessions closed 版的先后句，读手说「对 04 是纯新增」属实，四条落点的写序「先逐张 release 交回，最后落 sessions 的 closed 版」与 03 L15 一致，无改动。(c) 打开 research-loop/tables/roles/reviewer.json 与 analysis.json 核实：reviewer 的 reads 含 scratch（_sources 记 06 L228），analysis 的 reads 含 scratch、ledger_writes 的 scratch 是 "*"、notes[0] 是英文「scratch: only the rows of its own ql_tag, only in the quick lane (06 L222)」；读手的说法属实。改了两处，都在 (c)：其一，analysis.json 那条 landing 的 what 原文把 notes[0] 写成中文「只在快车道读写自己那条 ql_tag 的行」并加了引号，会被当成逐字引文，改成注明是英文原文并照抄；其二，(c) 的 note 末尾补一段核手打开两个 json 的核实结果（任务要求属实就在 note 写明）。读手 note 里引的旁证也顺带核过：06 L190、L196、L216、L218、L222、L228 与所述一致；transitions.json 的 open_quick_lane 行前提 ql.scratch_row_open 的 text 与 source（04 L62; 07 L88）一致；commands.json 的 ql close 行 notes 有「--merged requires ID to be a quick_lane supplement whose ql_tag equals QL (05 L87)」；gyb-usecases.json 的 _source 是「01 L98-114 (the table), 01 L116-135 (rl status ten sections and --json keys)」，01 L98 是「三、gyb 的 use case 表」、L116 是「四、rl status：gyb 的收件箱」；30 L76-86 是「测试 7：销号」；03 L190 与 04 L147 都写 released_handoffs 是 closed 版必填；04 L120 写销号钩子挂 SessionEnd 和 SubagentStop，L223 是引用句。4. status：六条都是 settled，note 都以「评审修复代裁，gyb 可否」开头，无改动。unresolved 为空，无改动。

## 四、统筹对核手留下的一点和一处状态变化的处置（2026-09-05）

- 45(b) 的 run 那一支：核手指出 06 L204 给 run 的 issues 写权只有 open，03 L92 写通知类 issue 的 assignee 能回能关，45(b) 要 holder（含 run）把代码位置和半截产物路径回进 withdrawn issue，三处对不上。统筹不改 06 的角色 json（D-03 的原则：json 逐字抄 06），run 那一支在 `research-loop/skills/run/SKILL.md` 和 rl 里标 `PENDING(issue 50)`，sync-inbox 问题 50 等 gyb 裁 run 的 issues 写权要不要加 reply、close。deploy 和 analysis 两支照 settled 落。记在代裁记录 D-14。
- 39(a2)（子会话算不算一次 sessions 行、session_id 记什么）：待验证第 5 条 2026-09-05 测完，统筹按验证助手和底座助手的推荐代裁成 D-15（rl 判 actor 先看钩子注入的 RL_AGENT_TYPE，子会话在 sessions 账另落一行、session_id 记母会话的、加可选栏 agent_id，SubagentStop 关子会话那一行并交回它的单，SessionEnd 交回本 session_id 名下全部）。代码里的标记从 `PENDING(verify 5)` 改成来源标注 `proxy D-15`；冻结正文的落点记 sync-inbox 问题 49。

