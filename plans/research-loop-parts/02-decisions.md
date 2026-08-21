# 决定账

> 这份覆盖 decisions 这一本账：六个决定文件、一行决定的字段、来源三类与锚点、编号与版本、root_id 与 line、update 和 confirm 和 retire 和 merge、过版 stale 与改版那一刻的打印、改版不影响在办单子、reissue、reviewer 的基准按 actor、`rl decision` 的全部子命令。
> 不覆盖：另外七本账的行格式和入账规则在 `03-ledgers.md`（handoffs 的行格式在 `04-handoffs-and-sessions.md`）；派活单的状态转移表和 `rl handoff reissue` 那一行的前提在 `04-handoffs-and-sessions.md`；`rl status`、`rl inbox`、`rl trace`、`rl doctor` 的段落和扫描项在 `05-rl-cli.md`；`--as-gyb`、`--quote`、`--force --reason` 的判定规则在 `01-gyb.md` 和 `06-hooks-and-permissions.md`；idea 怎么和 gyb 谈决定在 `10-role-idea.md`，deploy 的自决粒度在 `11-role-deploy.md`，reviewer 怎么用这本账在 `14-role-reviewer.md`。
> 源：设计文档「gyb 自己做的事」「五个角色」「idea」「deploy」「reviewer」「账本」几节；施工计划第一节裁决、第二节词表、第三节 decisions 行格式、第五节角色 json、第六节命令表、第十节测试第 3 条。

## 六个决定文件

decisions 这一本账拆成六个文件，五个角色各一个加 gyb 一个，文件名是 `loop/decisions.<actor>.jsonl`。拆文件的理由是并行各写各的不撞车。

决定行按编号前缀落文件：`dec-idea-*` 全在 `decisions.idea.jsonl`，`dec-gyb-*` 全在 `decisions.gyb.jsonl`，一条决定的所有版本永远同一个文件，谁写的另记 `actor`。开新条时前缀由会话定：角色会话开的用那个角色的前缀（角色会话里替 gyb 记的也一样，`actor` 记 `gyb`，带 `quote`），裸终端开的用 `gyb` 前缀；所以 `decisions.gyb.jsonl` 只装 gyb 在裸终端新开的决定和它们的后续版本，gyb 在裸终端给 `dec-idea-0007` 追加的一版落 `decisions.idea.jsonl`，`actor` 记 `gyb`、`session_id` 记 `cli`。前缀的判据是「哪个会话」，不是「谁亲手敲的键盘」：rl 只看得到命令从哪个会话发出来，看不到键盘前面坐的是 gyb 还是模型。

源文档三处口径（词表按 actor、第三节按编号前缀、第六节按 actor 加括号例外）2026-08-18 gyb 裁定按编号前缀落文件，`actor` 是单独一个字段（见文末裁决记录）。词表里 `loop/decisions.<actor>.jsonl` 的 `<actor>` 读作「前缀里的角色名」，不是「写这一行的人」。

## 一行决定长什么样

九本账的公共骨架七样（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）加两个可选字段（`force_reason`、`via`）写在 `03-ledgers.md`，这里不抄。decisions 自己的字段是：

| 字段 | 取值和必填规则 |
|---|---|
| `id` | 形如 `dec-idea-0007`、`dec-gyb-0002`；前缀说落哪个文件，序号每个前缀各排各的 |
| `op` | 这一版是哪个动作：`add`、`update`、`confirm`、`retire`、`merge`；过版判定靠它跳过 `confirm` 版 |
| `root_id` | add 时等于自己，之后每一版都继承、一条决定内不变；merge 出的新决定用 `--root` 指定继承哪一条的根，被合并的旧决定废除版根照旧不动 |
| `status` | `active` 或 `retired` |
| `text` | 决定正文 |
| `sources` | 列表，三类来源之一，每一版都非空 |
| `quote` | 角色会话里 `--as-gyb` 写的行必填 |
| `merged_from` | 合并时必填 |

六个文件同一个格式。整本账是事件流，只增不改，「改」永远等于追加一版；默认查询每个编号只取最新版。

## 来源三类与锚点

每条决定必须带来源。来源是一个列表，每一项是三类之一：

| kind | 写法 | 说明 |
|---|---|---|
| `decision` | `{"kind":"decision","id":...,"version":...}` | 旧决定的编号加版本 |
| `file` | `{"kind":"file","path":...,"anchor":可选}` | 仓库里的文件路径，锚点可选 |
| `run` | `{"kind":"run","run_id":...}` | runs 账里的一个 run_id |

三类可以混着放，至少一项，空列表入账脚本拒收。`file` 类是仓库内任意路径：notes/ 里 gyb 的调查报告、analysis/ 里的图和 notebook、experiments/ 里的部署报告、review/ 里的清单、experiments/ 里的代码文件都算；锚点指到小节或行号区间，命令写成 `--source file:notes/x.md#<小节>`。`file` 类路径不存在拒收，带锚点通过——锚点本身不校验，这是有意的（2026-08-18 gyb 裁）：笔记会改、小节会挪、行号会漂，写入时查了也只保证那一刻；锚点是给读的人和模型定位用的提示，doctor 也不扫。`run` 类的 run_id 不在 runs 账里拒收。

不设「口头」这一类来源，每条决定都要能追到一个文件或一个数字。一条决定链的第一条决定，来源指现有代码文件或 notes/ 里的一行，两样都没有就先让 gyb 在 notes/ 写一行。

跑完实验才知道的结论（比如「学习率太低，换高一点再跑」）就是这么进账的：来源指那次跑的 run_id 和 analysis 的图，成为原决定的新一版或者一条新决定。

update、confirm、retire、merge 四个动作不给 `--source` 时自动继承上一版的来源。「有新证据改的一版」和「gyb 当场改主意的一版」不另设「改的原因」一栏（2026-08-18 gyb 裁，第二轮模拟提的 `change_reason` 不采纳）：分辨靠 `sources` 和 `quote`——有新证据就把那次 run 或那份文件挂上来当来源，gyb 当场改的带 `quote`，两样都没有就是延续上一版依据改了做法。纪律是有证据必挂，不靠多一栏。

## 编号、版本、新一版还是新一条

编号带角色前缀，序号每个前缀各排各的：`dec-idea-0007` 和 `dec-deploy-0007` 可以并存，分号只扫自己那本。更新不换编号、版本号加一，谁写的记在 `actor` 里。默认读取对每个编号只取最新版，历史全在文件里但默认读不到，要旧版本用 `--version` 或历史命令。

判据分三条：

1. 改的是同一个问题的答案（同一件事换个做法、换个参数、停掉）就追加一版。
2. 换了要回答的问题就开新条。
3. 跨角色改别人的决定一律在自己那本开新条，来源指原决定的编号加版本。

看过一批结果之后确认「继续、设定不变」也要留痕，用 `rl decision confirm` 追加一版，正文不变、只加来源，`op` 记 `confirm`；这一版不算改版，不触发过版（见下一节）。

扫号、分配、追加三步放在同一把锁（`loop/.lock`）里，不许扫完号再排队写，否则同角色两个会话会撞号；扫号只读本前缀那一个文件。

## root_id 与 line

每条决定记根决定：新开的决定根是自己，追加一版继承，一条决定内根只写一次不变；合并时用 `--root` 指定新决定继承哪一条的根，被合并的旧决定废除版根照旧（2026-08-18 gyb 裁）。合并的正向靠新决定的 `merged_from`，反向靠 `sources` 里的 `decision` 项，不靠改根。词表里研究线 `line` 就是根决定编号。

派活单上的 `line` 由 rl 从 `decision_refs` 第一项的 `root_id` 算出来存着（handoffs 的字段在 `04-handoffs-and-sessions.md`）。两条研究线并行时按根决定切开看：`rl status --group-by line`、`rl decision list --line L`、`rl handoff list --line L`、`rl run list --line L`。

## update、confirm、retire、merge

| 动作 | 命令 | 这一版做什么 |
|---|---|---|
| 追加一版 | `rl decision update ID --text [--source ...] [--quote ...]` | 换正文，版本号加一 |
| 确认继续 | `rl decision confirm ID --source ...` | 正文不变，只加来源，版本号加一，`op` 记 `confirm`，不算改版 |
| 废除 | `rl decision retire ID [--source ...]` | 追加一版标 `retired`，来源默认继承上一版；必须带理由（谁废都要，gyb 也要），理由就是这一版的正文 `text` |
| 合并 | `rl decision merge ID1 ID2 ... --text --root ID [--source ...]` | 新决定拿新编号，根继承 `--root` 那条，`sources` 自动含全部被合并的旧决定，`merged_from` 必填，旧的各追加一版标 `retired`、根不动 |

废除等于追加一版标 retired。废除必须带理由，谁废都要（gyb 也要），理由记进这一版决定行；角色会话里替 gyb 废除的原话按 `--as-gyb --quote` 既有规矩带，不另加（2026-08-18 gyb 裁，来自 `09`）。理由不另加栏、不复用 `force_reason`，直接写进废除这一版的正文 `text`——废除版的 `text` 就是废除理由（2026-08-18 gyb 裁，sync-inbox 问题 36 选 c）；命令上怎么带归 `05`（冻结后待议，问题 37）。停一条方向的时候鼓励再加上那次 run 和那张图当来源。

update、confirm、retire、merge 的「谁能调」是同 actor；跨角色改别人的决定在自己那本 add，来源指原决定。gyb 是超级用户，「谁能调」这一类检查对 gyb 不生效，完整性校验照查（见 `01-gyb.md`）。

## 过版、改版那一刻的打印、在办单子怎么办、reissue

跨层引用带版本，写法是「依据 dec-idea-0007 第 2 版」。过版判定跳过 `confirm` 版：引用记的版本比账里最新一个 `op` 不是 `confirm` 的版本小才算过时；单子引第 2 版、账上第 3 版是 confirm 出来的，不算过时。过时的查询命令当场标出「上层依据已从第 2 版更新到第 3 版，复核这条还成不成立」。过版的单子进 `rl status` 段 6 和相关角色的 `rl inbox`。

`rl decision update`、`rl decision retire`、`rl decision merge` 写完那一刻，rl 当场列出引着旧版而没到终态的单子和它们的 holder。`rl decision confirm` 不打印：确认继续没有东西要复核（2026-08-18 gyb 裁）。

`rl decision stale [--handoff ID] [--all]` 是过版检查命令，默认只列和本会话手上单子有关的，`--handoff ID` 只查那张单子引的，`--all` 全库（2026-08-17 随 `05` 定稿裁：去掉 `--mine`）。这条命令是查询命令，谁都能调。

决定改了一版，不影响已经派出去的单子：单子按派出时引的那一版继续做，rl 只标过时，不自动打回、不自动标待复核、不自动停。停不停由 gyb 点名，停就用收回（`rl handoff withdraw`）。改版之后要重派的用 `rl handoff reissue ID --decision ID@V`，一条命令收旧单（`withdrawn`，级联）、开新单（新单一律从 `todo` 起、同新建拉起，继承 `explanation`、`parent_id`、`batch`，`supersedes` 指旧单）、通知全部 holder。这一行的前提和「谁能写」在 `04-handoffs-and-sessions.md` 的转移表里。

retired 决定名下还有活单的进 `rl status` 段 6 和 doctor。

发射单开单时从父单抄 `decision_refs`（原则 9），run 不查 inbox、只关注自己那张发射单（2026-08-17 sync-inbox 问题 28）。两句不矛盾：抄引用是为了从决定反查跑过什么，不查是因为 run 不管过版。源文档「run 的 inbox 不查过版，发射单不引决定」那句里「发射单不引决定」按上述作废（2026-08-18 gyb 确认）。

## reviewer 的基准按 actor

reviewer 的审查基准是「actor 是 gyb 或 idea 的决定行」，不看落在哪个文件里。reviewer 不拿文献当基准、不猜 gyb 的意思。

gyb 在场定的那一版和 idea 自决的那一版账上要分得出来：actor 是 gyb（带 quote）还是 idea（不带 quote）。gyb 坐在 deploy 会话里当场拍板的参数落 `decisions.deploy.jsonl`、actor 记 gyb、带 quote，不算 deploy 自决。

reviewer 清单一条问题五栏，第五栏是「决定账里没写但代码里做了的选择」，清单格式在 `14-role-reviewer.md`。

## `rl decision` 的全部子命令

| 子命令 | 干什么 | 谁能调 |
|---|---|---|
| `rl decision add --text --source K:V ... [--quote ...]` | 追加一条新决定，前缀按会话定（角色会话用角色前缀，`--as-gyb` 也一样；裸终端用 `gyb`），序号在本前缀内自动分配，落前缀那本 | 五个角色、gyb |
| `rl decision update ID --text [--source ...] [--quote ...]` | 追加一版换正文；不给 source 就继承上一版；写完当场列出引旧版而没到终态的单子和 holder | 同 actor |
| `rl decision confirm ID --source ...` | 追加一版，正文不变只加来源，`op` 记 `confirm`；不算改版，不打印受影响单子，过版判定跳过这一版 | 同 actor |
| `rl decision retire ID [--source ...]` | 废除，必须带理由（谁废都要），理由就是这一版的正文 `text`；同样列受影响的单子 | 同 actor |
| `rl decision merge ID1 ID2 ... --text --root ID [--source ...]` | 合并成新决定，被合并编号自动进 sources 和 merged_from，旧的各追加一版 `retired` | 同 actor |
| `rl decision show ID [--version V] [--history] [--with-runs]` | 默认最新版；`--with-runs` 先按 handoffs 的 `decision_refs` 找出引这条决定（任一版）的单子当起点，再沿 `parent_id` 往下收子孙单和它们的 run 与 metrics，按单子编号去重，按引的版本分组 | 谁都行 |
| `rl decision list [--actor A] [--line L]` | 列决定 | 谁都行 |
| `rl decision stale [--handoff ID] [--all]` | 过版检查，默认只列和本会话手上单子有关的，`--all` 全库 | 谁都行 |

查询命令（show、list、stale）谁都能调，不进角色 json 的 `ledger_writes`。写命令进哪个角色的 `ledger_writes` 见 `06-hooks-and-permissions.md`：idea 有 decisions.idea 全部、deploy 有 decisions.deploy 全部、analysis 有 decisions.analysis 全部、reviewer 有 decisions.reviewer 全部、run 有 decisions.run add（自决极少，比如挑卡的理由）。

退出码六个（定义处 `03-ledgers.md`）：0 成功；1 rl 内部错误；2 校验拒收；3 角色无权；4 文件锁等待超时；5 用法错。非零退出的标准错误第一行是固定的原因种类。所有子命令支持 `--json`。

决定账相关的测试用例（空来源拒收、三类来源各一个、`decisions.gyb.jsonl` 拒收非 cli 行、update 继承来源、confirm 版本加一且不标过版、merge 记根且旧决定根不动、update 时打印引旧版的活单）在 `30-build-steps-verify-tests.md` 的测试第 3 条。

## 和别的 part 的接口

这一份是决定账的定义处（HANDOFF 四点五节）：六个文件、行的字段（含 `op`）、三类来源与锚点、编号与版本、`root_id`、过版判定（跳过 confirm 版）、reissue 的触发、reviewer 基准、`rl decision` 全部子命令，别处引用以这里为准。这里向外要的东西：

- 公共骨架七样字段（`id`、`version`、`status`、`ts`、`actor`、`session_id`、`schema_version`）和可选的 `force_reason`、`via`：定义在 `03-ledgers.md`（冻结）。decisions 自己的字段（`root_id`、`op`、`text`、`sources`、`quote`、`merged_from`）定义在本份。
- actor 的判定、`--as-gyb`、`--quote`、`--force --reason`、裸终端 session_id 记 `cli`：定义在 `01-gyb.md`，钩子那一层在 `06-hooks-and-permissions.md`。本份只用到：角色会话里 `--as-gyb` 的行 `actor` 记 gyb、`quote` 必填、仍落角色前缀那本。
- handoffs 的 `decision_refs`（每项 `{"id":...,"version":...}`）、`line`、`parent_id`、`supersedes`：定义在 `04-handoffs-and-sessions.md`（冻结）。本份用它们做三件事：`line` 按 `decision_refs` 的 `root_id` 归线（2026-08-21 gyb 裁：`decision_refs` 可分属不同根决定，跨根的单在每条相关线的视图里都出现；`04` 冻结，字段语义等最后一期收口）；过版判定拿 `decision_refs` 的版本和本账最新非 confirm 版比；`show --with-runs` 第一跳按 `decision_refs` 找单子、之后沿 `parent_id`。
- `rl handoff reissue` 和 `rl handoff withdraw` 那两行转移的前提与「谁能写」：定义在 `04-handoffs-and-sessions.md`（冻结）。本份只定「改版不自动动单子，重派用 reissue、停用 withdraw」。
- `rl status` 段 6（过版的单子和 retired 决定名下的活单）、`rl inbox` 里的过版一类、`rl trace`、doctor 的决定相关扫描：定义在 `05-rl-cli.md`（冻结）。过版的定义以本份为准：比最新一个非 confirm 版小才算过时。
- runs 账的 `run_id`（`run` 类来源要引它，不在 runs 账里拒收）：定义在 `03-ledgers.md`。
- grants 谁能写（只有 gyb，裸终端和角色会话里 `--as-gyb --quote` 都收）：定义在 `01-gyb.md`。`read:notes` 获准机制和 doctor「来源指 notes/ 但 actor 没有 `read:notes`」那一项 2026-08-21 随 `10-role-idea.md` 定稿砍掉；grants 账存废等最后一期（sync-inbox 问题 43）。
- 快车道不写决定账、合回时在补单里一并补一条 decisions.deploy：定义在 `07-quick-lane.md`。
- 角色 json 的 `ledger_writes` 四栏和机器检查：定义在 `06-hooks-and-permissions.md`。本份给的输入：五个角色各有自己那本的写权，run 只有 add；查询命令不进 `ledger_writes`。
- 退出码六个和非零退出第一行的原因种类：定义在 `03-ledgers.md`。
- 测试清单第 3 条：在 `30-build-steps-verify-tests.md`，本份定稿后要补两例（confirm 不标过版、merge 后旧决定根不动），见「要同步到别处的」。

## 源文档没写清的（留给 gyb）

（八条 2026-08-17 至 2026-08-18 全部裁完，逐条见文末「裁决记录」。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

下面的条目原样抄自 `plans/2026-08-16-research-loop-simulation-round2.md`，未核实，不做判断。

### param-tweak 第 9 条 [slows/contradiction]

原文：第 10 步：快车道说「中间的一切都在 worktree 和杂账里」，免掉的四样里没有决定账；但 deploy 一节说超参取值算自决必须进 decisions.deploy，规矩 2 又是硬的，两种读法都说得通，deploy 不知道该不该写这条决定

依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-build-plan.md:246

改法：快车道那一段补一句「不写决定账，合回时在补单里一并补一条 decisions.deploy」

### param-tweak 第 10 条 [slows/contradiction]

原文：第 10 步：决定的 add 还是 update 判据说「同一件事换个参数就追加一版」，但 rl decision update 只有同一个 actor 能调；原来的学习率写在 decisions.idea 或 decisions.gyb 里，deploy 追不了那一版，只能在自己那本开新条，判据就落空了

依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:128

改法：判据补一句「跨角色改参数一律在自己那本开新条，来源指原决定的编号加版本」

### param-tweak 第 14 条 [slows/ambiguous]

原文：第 10 步：决定来源的 file 类要求「仓库里的文件路径」且路径不存在拒收，快车道改的文件在 worktree 里，主树同路径存在但内容是旧的，填哪个路径、校验查哪棵树两种读法都成立

依据：plans/2026-08-16-research-loop-build-plan.md:43; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205

改法：file 类来源允许带 worktree 或 commit 前缀，校验按给出的那棵树查存在

### new-idea 第 1 条 [blocks/blocked]

原文：第 8 步：新想法是 gyb 在聊天里当场说出来的，没有旧决定、没有 run_id、没有 analysis 产物，可来源必须至少一项且只有 decision/file/run 三类、明文写着「不设口头这一类」，file 类路径不存在还会被拒收；这条决定链的第一条决定入不了账，后面工单、发射单、runs 全部挂不上

依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:205

改法：明写「一条决定链的首条决定可以拿现有代码文件路径或 notes/ 里 gyb 的报告当来源，两者都没有时硬停并要求 gyb 先写一行 notes/」

### new-idea 第 5 条 [slows/contradiction]

原文：第 8 步：设计文档说 gyb 亲自打 --as-gyb 的落 decisions.gyb.jsonl、idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote，可角色会话里的命令全是模型打的，而施工计划规定模型打 --as-gyb 必须带 quote、账行 actor 记 gyb，决定文件又按 actor 拆名，同一条命令按两份文档会落进两个不同文件

依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:29; plans/2026-08-16-research-loop-build-plan.md:121

改法：明写「decisions.gyb.jsonl 只收裸终端写的行，角色会话里模型打的 --as-gyb 一律落 decisions.<角色>.jsonl 并记 quote」

### result-wrong-review 第 5 条 [blocks/missing]

原文：第 19 步（gyb 若当场废掉或改 dec-idea-0007 而不是让 idea 改）：gyb 给别人的决定追加一版落哪个文件没写：设计文档说 gyb 写的决定落 decisions.gyb.jsonl，又说决定账按 actor 拆六个文件、编号带角色前缀，那 dec-idea-0007 的第 3 版由 gyb 写就会和第 1、2 版分居两个文件，「默认查询只取最新版」和锁里的扫号都要跨文件才对，入账脚本没有依据。

依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:96; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:128

改法：明写「决定行按 id 前缀落文件，谁写的记在 actor 字段」，dec-gyb 前缀只给 gyb 新开的决定。

### result-wrong-review 第 10 条 [slows/ambiguous]

原文：第 23 步：决定来源 file 类允不允许指 review/ 里的清单两种读法都通：设计文档举例只有 notes/ 里 gyb 的调查报告和 analysis/ 里的图与 notebook，测试 3 却只检查路径存不存在。审出问题之后更新决定，最自然的来源就是那份清单，入账脚本按哪种写会决定它收不收。

依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205; plans/2026-08-16-research-loop-build-plan.md:57

改法：设计文档第 46 行明写 file 类是仓库内任意路径，举例补上 review/ 的清单和 experiments/ 的部署报告。

### result-wrong-review 第 11 条 [slows/missing]

原文：第 8 步到第 15 步：reviewer 的审查基准只有决定账、不猜 gyb 的意思，可 gyb 起疑的正是「当初谈定的东西和代码不是一回事」，谈定却没被 idea 记进决定账的那部分 reviewer 审不出来，也没有任何一栏让它报告「代码里做了选择但决定账里没有对应行」。

依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:84

改法：清单四栏加第五栏「决定账里没写但代码里做了的选择」，让 reviewer 把账的空白也报出来。

### plot-new-plan 第 6 条 [slows/missing]

原文：第 16 步之后（gyb 看完图想换个画法）：口径账只写了被打回之后 analysis 改了再提一版这条路，没写已经 approved 的口径能不能 update、update 之后 status 回不回 proposed、要不要重新批；也没有决定账那种「同一个问题换做法追加一版、换问题开新条」的判据。

依据：plans/2026-08-16-research-loop-next-steps.md:78; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:216; plans/2026-08-16-research-loop-next-steps.md:46

改法：给 evaluations 抄一条决定账同款判据，并明写 approved 之后 update 一版就回 proposed、必须由 gyb 重新 approve。

### next-plan-after-results 第 6 条 [slows/ambiguous]

原文：第 26 步：讨论里定下的结论落 decisions.gyb 还是落 decisions.idea 带 quote，判据是「gyb 亲自打的」还是「idea 替 gyb 记的」。可是在手动加载角色的会话里 rl 命令都是模型敲的，「gyb 亲自打」这条路实际只存在于另开裸终端，同一条结论两处都说得通，reviewer 的基准会散在两本账里

依据：2026-08-16-research-loop-next-steps.md:34; 2026-08-16-research-loop-next-steps.md:44; 2026-08-16-research-loop-build-plan.md:121

改法：定死「角色会话里一律落角色那本账带 quote，decisions.gyb 只收裸终端写的」，把判据从「谁亲手敲」换成「哪个会话」

### next-plan-after-results 第 7 条 [slows/missing]

原文：第 33 步：「这条方向看完结果继续做、设定不变」这一支没有落点。决定不换做法就不追加版、不换问题就不开新条，账上留不下 gyb 看过这批数字并确认继续的痕迹，下一轮 reviewer 和 `rl decision stale` 都看不到这次复核

依据：2026-08-16-research-loop-next-steps.md:46; 2026-08-16-research-loop-next-steps.md:109

改法：加一条 `rl decision confirm ID --source run:... --source file:...`，追加一版正文不变、只增来源

### next-plan-after-results 第 8 条 [slows/missing]

原文：第 27、36 步：决定 retire 之后，引用它的在办单子没人扫。doctor 的八项扫描和 rl status 的七段都没有「retired 决定名下还有没到终态的单子」这一项，设计文档又把停不停全交给 gyb 点名，忘了收回就一直挂着

依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:112

改法：doctor 和 status 各加一项「retired 决定名下还有活单」，附上 `rl handoff withdraw --cascade` 的修法

### decision-revised-while-in-flight 第 2 条 [blocks/missing]

原文：第 7 步：decision_refs 只对 work_order 必填（build-plan.md:61），文档没有一句要求 deploy 把工单的决定编号抄进发射单，所以 `rl decision stale`（build-plan.md:131）和 `rl handoff list --decision`（build-plan.md:136）都列不出正在跑的 ho-0013。过版检查只看得见工单，看不见真正在花机时的那张单。

依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:111

改法：开 launch_order 时自动从父工单继承 decision_refs 并写进单子，stale 检查按继承后的引用算。

### decision-revised-while-in-flight 第 6 条 [slows/missing]

原文：第 7 步：文档只在两个时机查过版：「角色上线第一个动作跑过版检查」（next-steps.md:111）和 `rl status`（next-steps.md:124）。决定改版的那一刻，`rl decision update`（build-plan.md:128）不输出任何「有 N 张在办单子引着旧版」的提示。本场景是我按原则 6 让 idea 主动再跑一次 `rl decision stale`，文档没有这条规矩；idea 不跑就没人发现。

依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:128; plans/2026-08-16-research-loop-build-plan.md:131

改法：`rl decision update` 和 `retire` 写完那一刻当场列出引旧版且未到终态的单子，并把它们的 holder 会话一起打印出来。

### decision-revised-while-in-flight 第 9 条 [slows/ambiguous]

原文：第 6 步：来源三类不含口头（next-steps.md:46），可是「换个评测集」这种 gyb 当场改主意既没有新文件也没有新 run_id，只能靠 update 默认继承上一版的来源（build-plan.md:57）。于是账上「有新证据的改版」和「临时改主意」长得一模一样，两种读法都说得通：一种是继承就算合规，一种是必须先去 notes/ 落一行再改。

依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:57

改法：决定行加一个 `change_reason` 枚举（新证据 / gyb 口头改），口头那档必须同时带 quote，来源仍继承。

### decision-revised-while-in-flight 第 14 条 [slows/missing]

原文：第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。

依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144

改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。

### decision-revised-while-in-flight 第 16 条 [slows/too_heavy]

原文：第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。

依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92

改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。

### decision-revised-while-in-flight 第 17 条 [cosmetic/missing]

原文：第 21 步：重开的 ho-0014 和被收回的 ho-0012 之间没有任何字段能看出是同一件事的第二次派发（handoffs 行格式 build-plan.md:61 里没有 supersedes 之类的栏），`rl status` 和 `rl handoff list --decision` 都只会把它们并排列成两张单。

依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:133

改法：handoff open 加 `--supersedes ho-XXXX`，写进单子并在 status 里归成一组。

### gyb-manual-takeover 第 6 条 [slows/ambiguous]

原文：第 10 步：gyb 坐在 deploy 会话里当场拍板一个影响实验结果的参数，这条落 decisions.deploy 还是 decisions.gyb 两种读法都说得通：deploy 一节说「取第几层、超参取值算自决，进 decisions.deploy」，idea 一节说「gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账」并要求 gyb 定的那一版和角色自决的分得出来。落错了直接影响 reviewer——reviewer 的审查基准只有 gyb 和 idea 层谈定的决定，落进 decisions.deploy 就不在基准里。

依据：plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:34

改法：在 deploy 一节补一句：gyb 当场拍板的算 gyb 的决定，落 decisions.gyb（--as-gyb 加 --quote），deploy 自决只指 gyb 不在场时自己拿的主意。

### gyb-manual-takeover 第 12 条 [slows/missing]

原文：第 6 步：取一条决定的指定版本没有命令。rl decision show 只有默认最新版和 --history 全量两档，可单子按派出时引的那一版继续做，deploy 要的就是 dec-idea-0007 第 2 版；只能把全部历史拉进上下文再自己挑，和读法纪律「挑最小的读法、大文件禁止整读」直接顶上。

依据：plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-next-steps.md:144

改法：rl decision show 加一个 --version V 参数，handoff show 里显示 decision_refs 时顺带把那一版正文带出来。

### two-idea-lines-parallel 第 1 条 [blocks/missing]

原文：第 2、6、9、20、25 步：九本账里没有任何一个字段说一行属于哪条研究线。公共骨架六样是 id/version/ts/actor/session_id/schema_version，decisions 按 actor 拆六个文件不按线拆，issues、evaluations、scratch、sessions 四本账各自的字段表里也没有线维度。gyb 早上第一眼要分清两条线，只能靠自己记住哪个决定编号属于哪条线。

依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-next-steps.md:96

改法：公共骨架加一个可选的 line 字段，rl 的 status/list/show 全部加 --line 过滤，开单和提口径时从上游单子自动继承。

### two-idea-lines-parallel 第 2 条 [blocks/missing]

原文：第 3、4 步：「根决定」这个归组键没有定义。设计文档说 status 可按根决定归组、施工计划写 --group-by decision，但 decisions 行上只有 sources 没有 parent 或 root 字段；两个旧决定合并成新决定之后一条决定有多个被合并的旧编号，往上走根不唯一。

依据：plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:110

改法：要么给 decisions 加一个显式 root_id（merge 时指定保留哪个根），要么把 --group-by decision 定义成「按单子上直接引的决定编号分组」并在文档里写死这一句。

### two-idea-lines-parallel 第 4 条 [slows/ambiguous]

原文：第 5 步：batch 一个字段被当成两种粒度用。设计文档定义 batch 是 deploy 一次开 N 张发射单的共用标签（分片级），修订记录却把「两条 idea 线归不了组」列成靠 batch 标签解决的问题（研究线级）。gyb 打 --group-by batch 看到的到底是两条线还是两次分片，两种读法都说得通。

依据：plans/2026-08-16-research-loop-next-steps.md:68; plans/2026-08-16-research-loop-next-steps.md:214; plans/2026-08-16-research-loop-build-plan.md:61

改法：batch 只保留分片语义，线级归组交给新加的 line 字段，把修订记录里「两条 idea 线归不了组」那一项的解决办法改成 line。

### two-idea-lines-parallel 第 11 条 [slows/too_heavy]

原文：第 15、18 步：角色上线第一个动作 rl decision stale 没有范围参数，列的是全库过版的单子和决定。两条线并行时，蒸馏线的 deploy 一上线就把探针线的过版项读进上下文，和读法纪律「读进来的每个字都留在上下文里挤占后面的判断、只读自己需要的那部分」直接顶。

依据：plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-next-steps.md:144

改法：rl decision stale 加 --mine 和 --handoff 两个过滤，角色上线默认只查本会话要接的那张单子相关的决定。

### idea-request-notes 第 4 条 [slows/ambiguous]

原文：第 14 步：决定落哪本账的判据是「由 gyb 亲自打 --as-gyb 写的落 decisions.gyb.jsonl，idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote」。但在角色会话里 gyb 从不打命令、只说话，命令全是模型打的，「亲自打 --as-gyb」这件事在角色会话里不存在。模型代打的 --as-gyb 算不算亲自，两种读法都说得通，同一条 gyb 定的决定可能落进两本不同的账

依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:57

改法：第三节写死一条：decisions.gyb.jsonl 只收 session_id 为 cli 的行，角色会话里替 gyb 记的一律落角色自己那本并带 quote

### idea-request-notes 第 7 条 [slows/missing]

原文：第 12 步和第 14 步：file 类来源只有 path 一个字段。一份几十页的文献调查整份当来源，reviewer 拿决定账当唯一审查基准的时候，定位不到是报告里哪一句支撑这条决定，核不动「代码和决定是不是一回事」上游的那一半

依据：plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:88

改法：file 类来源加一个可选的 anchor 字段（小节标题或行号区间），命令写成 `--source file:notes/x.md#<小节>`

### idea-request-notes 第 8 条 [slows/missing]

原文：第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对

依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144

改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层

### n-launch-orders 第 17 条 [cosmetic/missing]

原文：第 13 步：run 上线第一个动作是跑 rl decision stale，但 run 的角色 json 里 reads 不含 decisions 账，发射单上也没有 decision_refs，这条检查对 run 是空转。

依据：2026-08-16-research-loop-build-plan.md:131; 2026-08-16-research-loop-build-plan.md:105; 2026-08-16-research-loop-build-plan.md:81

改法：把「上线跑过版检查」限定给 idea、deploy、analysis 三个角色，或者让 launch_order 继承父工单的 decision_refs 之后 run 再查。

### smoke-fails 第 14 条 [cosmetic/contradiction]

原文：步 10（run 上线跑过版检查）：设计文档说角色上线第一个动作跑过版检查，这是对所有角色说的；施工计划第五节给 run 的 reads 只有 handoffs 里的 launch_order、experiments/、ops/gpu_state.md、runs，不含 decisions。rl decision stale 要读 decisions 账，run 跑它就越出自己的 reads 栏，不跑又违反上线第一个动作那句。发射单本来也不引决定，run 跑了也查不出跟自己有关的东西。

依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:131

改法：明写过版检查只对 idea、deploy、analysis、reviewer 强制，run 免跑；或者把 decisions 的只读加进 run 的 reads。

## 裁决记录（日期）

- 2026-08-17 来自 `05-rl-cli.md` 定稿（`656c8a9`）的裁决（rl-hub 转来；gyb 原话「全推荐」「只要他不动目前的代码什么的就全推荐就行」「全都推荐，只要不影响正在跑的进程」「A」）：`rl decision stale` 签名改成 `[--handoff ID] [--all]`，去掉 `--mine`。对回原则 8。第 90 行、命令表那一行照改，「没写清」第 3 条据此销掉。
- 2026-08-17 来自 sync-inbox 问题 15 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「B」）：「一行决定长什么样」和接口一节的两个可选栏由「`fix_for`、`force_reason`」改成「`force_reason`、`via`」。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 21 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「A」）：「过版、改版那一刻的打印、在办单子怎么办、reissue」一节的 reissue 那句补「新单一律从 `todo` 起、同新建拉起」。对回原则 4。
- 2026-08-17 来自 sync-inbox 问题 25 的裁决（定义处 `03`，rl-hub-v3 传；gyb 原话「我想让agent有办法识别发生了什么就行」）：`rl decision` 子命令一节末尾的退出码由四个改成六个（0/1/2/3/4/5），并写上非零退出第一行给原因种类。对回原则 5。
- 2026-08-17 来自 sync-inbox 问题 27 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「3 不是，可以替我写」）：接口一节「grants 只收裸终端」改成「grants 谁能写（只有 gyb，裸终端和角色会话里 `--as-gyb --quote` 都收）」。对回原则 1。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「顺便run只需要关注自己的工单，一般不会空run，不需要查，这个改了」）：「过版」一节两处原文不一致那段的末句「run 的 inbox 仍然不查过版」改成「run 不查 inbox，只关注自己那张发射单」。对回原则 6。
- 2026-08-18 gyb 裁「甲」：决定行按编号前缀落文件，一条决定所有版本同文件，`actor` 单独记；gyb 那本只装 gyb 裸终端新开的决定及其后续版本，gyb 裸终端给角色决定追加的版本落角色那本。对回原则 4。「六个决定文件」一节两段照改，`id` 字段说明照改，「没写清」第 1 条销掉，第一处「两处原文不一致」结掉。
- 2026-08-18 gyb 裁「甲」：序号每个前缀各排各的，`dec-idea-0007` 和 `dec-deploy-0007` 可并存，扫号只读本前缀那一个文件。对回原则 4。「编号、版本」一节两句照改，「没写清」第 2 条销掉。
- 2026-08-18 gyb 裁「乙」：`rl decision confirm` 不算改版——写完不打印受影响单子，过版判定跳过 `confirm` 版（引用版本比最新一个非 confirm 版小才算过时）；为此行上加 `op` 字段（`add`/`update`/`confirm`/`retire`/`merge`）。对回原则 9。「一行决定长什么样」加 `op` 行，「编号、版本」「update…」表、「过版」一节前两段照改，「没写清」第 4 条销掉。
- 2026-08-18 gyb 裁「甲」：merge 时被合并旧决定的废除版 `root_id` 不动，一条决定内根只写一次；新决定的根按 `--root` 继承；正反向靠 `merged_from` 和 `sources`。对回原则 4。`root_id` 字段行、「root_id 与 line」一节、merge 表行照改，「没写清」第 5 条销掉。
- 2026-08-18 gyb 裁「甲」：`rl decision show --with-runs` 第一跳按 handoffs 的 `decision_refs`（任一版）找起点单子，再沿 `parent_id` 收子孙单和 run/metrics，去重、按版本分组。对回原则 9。子命令表那一行照改，「没写清」第 6 条销掉。
- 2026-08-18 gyb 裁「甲」：不加 `change_reason` 栏；「有新证据的改版」和「gyb 改主意」靠 `sources` 和 `quote` 分辨，纪律是有证据必挂。对回原则 8。「来源三类与锚点」一节继承来源那句后补一段，「没写清」第 7 条销掉。
- 2026-08-18 gyb 裁「甲」：`file` 类来源的锚点有意不校验（只查路径存在），doctor 也不扫。对回原则 7。「来源三类与锚点」一节那句照改，「没写清」第 8 条销掉。
- 2026-08-18 gyb 确认「甲」：发射单从父单抄 `decision_refs`、run 不查 inbox 两句并存不矛盾，源文档「发射单不引决定」作废。对回原则 9。「过版」一节第二处「两处原文不一致」改成结论。
- 2026-08-18 来自 `09-common-and-feedback.md` 定稿（`aaca3c9`，rl-hub-v5 传；gyb 原话「a」）：`rl decision retire` 必须带理由，谁废都要（gyb 也要），理由记进这一版决定行；替 gyb 废除的原话按 `--as-gyb --quote` 既有规矩。第五节表、表下一段、接口一节命令表三处照改。理由落行上哪一栏（新加一栏还是复用 `force_reason`）本份是定义处，等 gyb 裁（sync-inbox 问题 36）；命令签名归 `05`（冻结后待议，问题 37）。对回原则 1、8。
- 2026-08-18 gyb 裁（sync-inbox 问题 36，rl-hub-v5 问，原话「c」）：废除理由不另加栏、不复用 `force_reason`，直接写进废除那一版的正文 `text`。第五节表、表下一段、接口一节命令表三处照改。对回原则 8。
- 2026-08-21 来自 `10-role-idea.md` 定稿（`96459b4`，rl-hub-v6 传；gyb 原话「砍掉，默认能读」「不用申请」、选「允许，两边都算」）：doctor「来源指 notes/ 而无 `read:notes`」扫描随获准机制砍掉，正文那段删、接口一节 grants 行照改；`decision_refs` 可分属不同根决定、跨根的单在每条相关线的视图里都出现，接口一节 `line` 那句照改（`03` 冻结，等最后一期收口）。对回原则 2、9。
- 2026-08-21 评审修复（gyb 授权，定义处 HANDOFF 四点五节：handoffs 行格式定义处是 `04-handoffs-and-sessions.md`）：第 68、130 行把 handoffs 的字段（`decision_refs`、`line`、`parent_id`、`supersedes`）的定义处由 `03-ledgers.md` 改指 `04-handoffs-and-sessions.md`；第 4 行未见对应指向，未改。

## 要同步到别处的

- 决定行按编号前缀落文件（2026-08-18 裁「甲」）：凡写「gyb 的决定落 gyb 那本」「按 actor 落文件」的引用处改成「按编号前缀落文件，`actor` 另记」；`03` 词表 `loop/decisions.<actor>.jsonl` 的 `<actor>` 读作前缀里的角色名（03 冻结，冻结后待议，只是读法说明，不必改字）。（已同步 2026-08-18 rl-hub-v4；动到冻结的 03/04/05 的那几句记 sync-inbox「冻结后待议」问题 34，未改）
- decisions 行新增 `op` 字段（`add`/`update`/`confirm`/`retire`/`merge`），confirm 不算改版（2026-08-18 裁「乙」）：凡写「引用版本比最新版小就是过时」的地方（`04` 派活单「依据过时」、`05` `rl status` 段 6 / `rl inbox` 过版项、`07`/`09`/`23` 若有）改成「比最新一个非 confirm 版小才算过时」；`04`/`05` 冻结，冻结后待议。`30` 测试第 3 条要加一例「confirm 之后不标过版」。（已同步 2026-08-18 rl-hub-v4；动到冻结的 03/04/05 的那几句记 sync-inbox「冻结后待议」问题 34，未改）
- `rl decision show --with-runs` 的说明（2026-08-18 裁「甲」）：`05` 命令表若照抄「沿 parent_id 链反查」，改成「先按 `decision_refs` 找起点单子再沿 `parent_id` 收」；`05` 冻结，冻结后待议。（已同步 2026-08-18 rl-hub-v4；动到冻结的 03/04/05 的那几句记 sync-inbox「冻结后待议」问题 34，未改）
- 测试第 3 条（`30`）加两例：confirm 之后不标过版；merge 后旧决定废除版 `root_id` 不动。（已同步 2026-08-18 rl-hub-v4；动到冻结的 03/04/05 的那几句记 sync-inbox「冻结后待议」问题 34，未改）
- 「发射单不引决定」这句凡在引用处（`11`、`12`、`23` 若有）出现的，删掉或改成「发射单从父单抄 `decision_refs`，run 不查 inbox」（2026-08-18 确认）。（已同步 2026-08-18 rl-hub-v4；动到冻结的 03/04/05 的那几句记 sync-inbox「冻结后待议」问题 34，未改）
