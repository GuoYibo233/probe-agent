# deploy 角色

> 这份写 deploy 这个角色的 SKILL.md 里要有的全部东西：写权、两份部署报告和 code_paths、自决的粒度、改宿主文件的三条纪律、开发射单、后台起 run 并验收、发射单卡住之后怎么办、单子被收回后半截东西的处置、体检发现报告丢了怎么办、把数字补回报告再提验收、快车道里 deploy 做的动作、gyb 坐在 deploy 会话里拍板怎么落账、用哪个模型。
> 这份不覆盖：handoffs 和 decisions 两本账的行格式（在 `03-ledgers.md`）、派活单的状态转移表和会话生命周期（在 `04-handoffs-and-sessions.md`）、`bin/rl` 的完整命令表和退出码（在 `05-rl-cli.md`）、钩子和角色 json 的文件格式（在 `06-hooks-and-permissions.md`）、快车道本身的机制（在 `07-quick-lane.md`）、宿主对接（在 `08-trees-init-and-host.md`）、公共母版八条规矩（在 `09-common-and-feedback.md`）、工单是怎么开过来的（在 `20-pair-idea-deploy.md`）、发射单交给 run 之后的事（在 `21-pair-deploy-run.md`）。
> 源：设计文档的「五个角色」总段、deploy 一节、快车道一节、「分权与钩子」、「交接与会话生命周期」；施工计划第一节裁决 3、第二节词表、第三节 handoffs、第四节转移表、第五节 deploy 的 use case、第六节命令表、第七节、第十三节。

## 一、deploy 是干什么的

deploy 写代码，把探索性概念转成清晰可发布的实现，把怎么运行交给 run。写的是研究代码，不要求严密的工程风格。

模型按施工计划第一节裁决 3：由 agent（subagent 或 workflow）调用的时候用 opus；gyb 手动加载 deploy 的时候跟当前会话的模型一致，角色 json 的 `model` 栏里 `manual` 写 `inherit`，sessions 账落解析后的真实模型名，取不到记 `unknown`。

`rl inbox` 谁需要谁敲，不是上线动作：deploy 被派单拉起时先干那张单，收件箱要看的时候自己敲。inbox 列五样：本角色名下 open 的 issue、owner 是本角色而 holder 为空的单子、本会话手上单子引的过版决定、发给本角色的通知、本角色提的 feedback 的裁决。

deploy 一个会话只装 deploy 一个角色。加载 skill 那一刻钩子把这个会话登记进 sessions 账，销号也由钩子做，规矩在 `04-handoffs-and-sessions.md`。

## 二、写权只有 experiments/

deploy 的 `writes` 只有 `experiments/`。钩子挂 Write、Edit、Bash 三个工具（Bash 2026-08-18 gyb 裁进来，定义处 `06`：钩子解析命令里的重定向、`tee`、`sed -i`、`mv`/`cp` 的目标路径，解析不出的归纪律），只按研究仓库内的相对路径判，只拦两类事：写别的角色的目录（`analysis/`、`review/`、`notes/`；`notes/` idea 也能写，2026-08-18 gyb 裁，定义处 `06`），和直接写 `loop/`。仓库外的路径一律放行，所以快车道的 worktree 和产物根 deploy 写得进去，钩子不判。仓库根的 `run.py`、`MAP.md`、`ops/` 这些路径钩子也放行，靠第五节的三条纪律管。钩子解析不出目标路径的 Bash 写法归纪律管，见第十一节的两句纪律。

钩子拦下来的时候回话要指路：告诉模型你是谁、为什么拦、去开哪条 issue 的命令是什么。分权三层的全文在 `06-hooks-and-permissions.md`。

## 三、接工单、两份部署报告、code_paths

工单（`work_order`）由 idea 开给 deploy，owner 是 idea。deploy 用 `rl handoff start ID` 接单，单子从 `todo` 进 `in_progress`，holder 记这个会话；holder 非空的时候接不进去，rl 退出码 2 并列出当前 holder。

干完写部署报告，分两份，都放 `experiments/` 下这张工单自己的目录里。正常工单的目录照单子的编号起名（`experiments/<单号>/`，2026-08-21 gyb 裁）；快车道补单的报告目录用 `experiments/<ql_tag>/`，拿到单号之后不改名（2026-08-21 gyb 裁，定义处 `07`）：

| 报告 | 字段名 | 里面写什么 |
|---|---|---|
| 不带文件的那份 | `report_paths.method` | 像论文里那样只讲做法、用了什么技术、数据怎么被处理，不带任何文件；必须原样抄一遍这张工单引的决定编号加版本 |
| 带文件的那份 | `report_paths.detail` | 带上文件和处理细节、这次改了哪些文件的清单（含 experiments/ 外的宿主文件）、这张单子上关联的 issue 编号和结论 |

不带文件的那份是 reviewer 的锚，reviewer 拿它审「代码和决定是不是一回事」。

除了两份报告，交活时还要填 `code_paths`，是要审的代码路径清单，reviewer 的代码清单就从这一栏来。这一栏全收：这张单改过的代码路径，不论在不在 `experiments/` 里，都列进去，宿主文件也算（2026-08-21 gyb 裁）。reviewer 的读顺序把 `detail` 报告排在最后，清单不全的话先读代码那一遍必漏宿主改动。

提 `done_pending_review` 的前提是 `report_paths` 和 `code_paths` 齐：`method` 必填且路径存在，`detail` 非快车道时必填且路径存在。缺了入账脚本不收这个状态。开单的时候不查这些，前提查在交付那一刻（原则 4 推论）。

验收人是 owner，也就是 idea；gyb 随时可以自己验。被打回（`rejected`）之后单子回 `todo`，由 idea 重新拉起 deploy；原会话还活着的话 deploy 可以直接 `rl handoff start` 从 `rejected` 接着干。

deploy 跑 `rl doctor` 看到自己名下那张 `done_pending_review` 的报告路径没了：直接开 issue 报给 gyb 修（`rl issue open --to gyb --kind cannot --handoff ID`），自己不动单子——打回的权在 owner 手里，deploy 是 `to_role` 没有（2026-08-21 gyb 裁）。

## 四、自决的粒度与 decisions.deploy

改变实验结果的选择算自决：取第几层、用哪个划分、超参取值。这一类进 `decisions.deploy.jsonl`，来源默认填改动的文件路径。纯写法的选择不算自决，不写账。

跨角色改别人的决定一律在自己那本开新条，来源指原决定的编号加版本，不去追别人那本的版本。

gyb 坐在 deploy 会话里当场拍板的参数不算 deploy 自决：按原则 1 落 `decisions.deploy.jsonl`、actor 记 gyb、带 `--quote`。`decisions.gyb.jsonl` 只收裸终端写的行，角色会话里替 gyb 记的决定一律落角色自己那本。角色会话里的 `--as-gyb` 不论谁敲都要 `--quote`，缺 quote rl 拒收，这个 quote 是留给 reviewer 事后查的痕迹。

决定的编号、版本、来源三类、`root_id` 这些在 `02-decisions.md`。

## 五、改 experiments/ 外的宿主文件：三条纪律

deploy 改到仓库根 `run.py` 的注册表、`MAP.md`、`ops/` 里的东西，钩子不拦，纪律是三条：

1. 改动列进部署报告带文件的那一份。
2. 在 `decisions.deploy.jsonl` 留一条来源指向那个文件。
3. 宿主仓库自己对这些文件的规矩照守。new1 是 `CLAUDE.md` 里的 probe-pipeline skill 和 run.py 注册表三件套。

老代码要不要搬进 `experiments/` 由 gyb 手动定，deploy 只提醒。

## 六、开发射单

deploy 给 run 开发射单（`launch_order`），deploy 是发射单的 owner。命令是 `rl handoff open --type launch_order --to run --parent ID --command ... --workdir ... --track ... --config k=v ... [--batch B] [--manual|--no-dispatch]`。

开单时 deploy 填的和 rl 自动给的：

| 东西 | 谁给 | 说明 |
|---|---|---|
| `parent_id` | deploy 填 | 指这张发射单所属的工单，`launch_order` 必填 |
| `decision_refs` | rl 自动 | 开单时从父单抄 |
| `batch` | deploy 填，可选；`launch_order` 开单时从父单抄 | 自由文本，调用者 `--batch B` 传，rl 不分配；一次开 N 张同 batch 的发射单时共用，只有分片语义 |
| `command`、`workdir` | deploy 填 | 第一次尝试的必填项 |
| `track` | deploy 填，从父单抄 | 宿主发射器要的方向名。工单格式里加方向名一栏，idea 开工单时填，发射单开单时照抄（2026-08-21 gyb 裁；工单加栏动 `04` 的字段表，冻结、等最后一期，见「要同步到别处的」） |
| `config` | deploy 填 | 字典：`model`、`params`、`dataset`、`split`、其余超参自由，给 analysis 分组用 |
| `run_id` | rl 自动 | 按 `<ho-id>-a<attempt>` 分配 |
| `line` | rl 自动 | 从 `decision_refs` 的 `root_id` 算出来存着；引用允许分属不同根决定，跨根的单在每条相关线的视图里都出现（2026-08-21 gyb 裁，sync-inbox 问题 43；字段语义定义处 `03` 冻结、等最后一期收口） |

deploy 不跑 smoke、不估时长，这两样都是 run 的活：分步表 `step_table` 和 `estimated_seconds` 由 run 在 smoke 的时候填。

一次开 N 张同 batch 的发射单时，只起一个 run 会话接整个 batch，run 用 `rl handoff start --batch B` 一次接下来：smoke 做一次、分步表填一次、探卡挑卡一次、按宿主发射器自己的分片规矩发 N 份、落 N 条 run 行。不是一个 workflow 起 N 个 run 各自探卡抢同一张卡。

batch 谁分原来两处不一致，2026-08-17 gyb 裁定（sync-inbox 问题 9）：`--batch B` 是调用者传的自由文本、可选，rl 不分配，施工计划第六节讲锁那段把 batch 列进「rl 在锁里分配的编号」那句作废。

## 七、后台起 run 并验收发射单

按原则 11，派活不占终端：deploy 开完发射单后台起一个 run 的 subagent 接走，deploy 会话继续可用，subagent 回来时 deploy 验收。给 run subagent 的开场提示把单子的内容全抄一遍（单号、命令、工作目录、方向名、`config`、`batch`），不是只给单号让它自己查账；成批时按批次一次交接（2026-08-21 gyb 裁）。开单带 `--manual` 的 deploy 只开单、gyb 自己开 session 去接；带 `--no-dispatch` 的停在 `todo` 等 gyb 说开跑。deploy 会话先结束了，单子照常在账上等 owner 下次上线或 gyb 验收。

run 交活的前提是最新一次尝试的 run 行有 `exit_status=ok` 的收尾版。deploy 用 `rl handoff accept ID` 验收、`rl handoff reject ID --reason` 打回。发射单被打回或者 run 会话销号把单子交回 `todo`，都由 deploy 重新起 run。

下游 subagent 没走到交活或卡住就返回的（报错、上下文满），deploy 当场 `rl handoff release ID --note ...` 把单子交回 `todo`，并决定是重起还是开 issue 给 gyb。

单子被上游收回时，deploy 把已写进 `experiments/` 的代码位置和产物根里半截产物目录的路径回进那条 `withdrawn` 通知 issue，东西留着不动，处置由 gyb 定（2026-08-21 gyb 裁）。

## 八、发射单卡住之后

run 出问题一律开 issue 回给 deploy，kind 是 `failed`，`stage` 取 `smoke`、`launch`、`crash` 三个之一，附日志末 40 行和 traceback，同时把发射单标 `stuck`。run 不修代码不重试。结果反常那一类（kind 是 `anomaly`）归 gyb，不归 deploy。

deploy 手上这条路是四步：

1. 改代码。
2. `rl handoff amend ID --command ... --workdir ...` 给发射单追加一次新的尝试，新命令、新工作目录都在这一版里。amend 只改内容不改状态，允许在 `todo` 和 `stuck` 上做。
3. `rl issue reply ID --text ...` 回那条 issue。
4. `rl handoff resume ID` 把单子交回 `todo`，前提是关联 issue 的状态已经是 `answered`。之后由 owner（也就是 deploy 自己）再起一个 run。

一张发射单是多次尝试的容器（原则 10）：smoke 失败、发射失败、跑挂、修完再来，每一次是单子上的一个 attempt，各带自己的命令、分步表、预计时长和 run 行。预计时长只算最新一次尝试。

deploy 自己卡住的时候走 `rl issue open` 加 `rl handoff stuck ID --issue ID`（前提是那条 issue 的 `handoff_id` 指回本单）；deploy 解决不了的用 `rl issue reassign ID --to gyb` 改派给 gyb。

## 九、把 run_id 和指标补进报告再提工单验收

发射单验收完之后，deploy 把 run_id 和关键指标补进带文件的那一份报告（`detail`），再提工单的 `done_pending_review`。补路径或补引用同样走 `rl handoff amend`。

## 十、快车道里的 deploy 动作

快车道由 gyb 点名进，口头就行。快车道本身的机制（标签怎么分、worktree 建在哪、杂账怎么写、怎么关张）在 `07-quick-lane.md`，这一节只写 deploy 做什么。

进：`rl ql open`，rl 分配 `ql_tag`、建 worktree 和同名分支、往杂账写开张的一行。`--from ho-ID` 可以把一张待干的工单转进快车道。

中间：deploy 在 worktree 上改代码、自己小规模跑。GPU 照旧走宿主发射器，快车道里 deploy 可以派 gpu-runner，这是 deploy 唯一能派 run 之外的对象。run_id 用快车道标签，track 沿用被微调的那个实验的方向，宿主的台账照登记、`record finish` 的结论栏写 `quick_lane` 加标签。数字追加进杂账，不进 runs 账。不开发射单、不叫 run、不做分步计时、不写决定账。

出：两条路，各是杂账上的一行。合回分三步：gyb 先亲自 merge 主分支（deploy 只把命令交出来）→ deploy 开补单、同时补那条 `decisions.deploy` → 拿到编号再 `rl ql close --merged --handoff ID` 关杂账，两边互指（2026-08-21 gyb 裁：先合并再补记，决定来源和报告路径的存在性检查一律按主树查，入账工具不用多认副本写法）；丢掉走 `rl ql close --dropped --reason`。补的是一张标了 `quick_lane` 的工单，这张单子的特别之处：

- `from_role` 和 `to_role` 都是 deploy，验收人固定是 gyb，只有 gyb 能 accept。
- 允许新建就直接进 `done_pending_review`，命令是 `rl handoff open --quick-lane --report-method P --ql QL`；`QL` 存进单子的 `ql_tag` 栏，开单前提是 `ql_tag` 指的杂账行状态是 `open`。
- 只要一份不带文件的简报（`report_paths.method`），带文件的那一份用杂账里的记录顶替。
- `explanation` 由 deploy 写，并抄一句 gyb 点名的原话。
- 同时补一条 `decisions.deploy` 记这次改动。

主分支上永远只有走过工单的代码（先合并后补单之间有个短窗口，主干上短暂有还没挂上单子的代码——补单是紧跟着的下一步，2026-08-21 gyb 认了这个窗口）。合回之后要正式数字，按正常路再开发射单跑一遍，那张发射单的父单就是这张快车道工单；doctor 会报「快车道工单已验收但没有关联发射单」。

两处原文不一致（2026-08-21 已由 `07` 定稿收口：开单动作 deploy、owner 记 gyb，见文末裁决记录，别再问）：快车道补单的 owner。施工计划第二节说 owner 就是 `from_role`、又说快车道补单的 owner 记 `gyb`，第三节说 `from_role` 就是 owner、取值可以是 `gyb`，设计文档说这张单子 `from_role` 和 `to_role` 都是 deploy。按施工计划第四节的表，那一行的「谁能写」是 deploy、括号注「快车道补单，owner 记 gyb」，accept 只有 gyb 能打。

## 十一、deploy 的 use case 表和角色 json 四栏

use case（施工计划第五节原文）：接工单（handoff start）；写代码写报告；自决留痕（decision add 到 decisions.deploy）；开发射单并后台起 run（handoff open --type launch_order --parent ID，一次开 N 张同 batch）；验收发射单（accept/reject）；发射单卡住后改代码、追加一次尝试、回 issue、交回待干、再起 run（handoff amend、issue reply、handoff resume）；把 run_id 和指标补进 detail 报告后提验收（handoff done）；自己卡住开 issue（issue open、handoff stuck）；解决不了改派 gyb（issue reassign）；快车道（ql open/close、scratch add、handoff open --quick-lane、快车道里派 gpu-runner）；改宿主文件时列进报告、留决定、守宿主规矩。

| 栏 | 内容 |
|---|---|
| reads | `decisions.idea`、`decisions.gyb`、`decisions.deploy`、handoffs、issues、runs、feedback、`experiments/`、`ops/gpu_state.md` |
| writes | `experiments/`（worktree 在仓库外，钩子不判） |
| ledger_writes | decisions.deploy 全部、handoffs 的 start/done/stuck/open/accept/reject/withdraw/release/resume/amend、issues 全部、scratch 全部（含 ql open/close）、feedback add |
| dispatches_to | run、gpu-runner |
| model | as_subagent 是 opus；manual 是 inherit |

备注（不进 json，2026-08-18 `reads` 写法裁决：备注移到表下）：`ops/gpu_state.md` 只在快车道自己跑 GPU 时读；gpu-runner 只在快车道派。`dispatches_to` 机器不查、纯纪律，事后从 sessions 账看谁起了谁（2026-08-18 gyb 裁，定义处 `06`）。

SKILL.md 里另写两句纪律（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`）：钩子拦不到的写法（脚本内部写文件、`python -c`、heredoc、任何钩子解析不出目标路径的 Bash 命令）一律不许往四个角色目录和 `loop/` 写，要写就用 Write/Edit 或钩子看得见的 Bash 写法，账本一律走 `rl`（Bash 进钩子匹配范围后按 sync-inbox 问题 38 改的措辞）；一个会话只加载一个角色，要换角色另开会话。

SKILL.md 的骨架按 `common/SPEC-TEMPLATE.md` 五栏写——角色设定、使用场景、可用工具、限制条件、输出样式；「可用工具」一栏只指到角色 json，不抄（2026-08-18 gyb 裁，定义处 `09-common-and-feedback.md`）。

被派活时以插件的角色 agent 类型起 subagent：agent 定义 `agents/<role>.md` 预加载本角色 skill、收窄工具面、不带钩子；写权钩子是一份插件级钩子文件，按钩子输入的 `agent_type` 认角色（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`，插件树在 `08`）。

reads 是纪律不设门禁，查询命令（show、list、trace、status、inbox、stale、doctor）谁都能调，不进 `ledger_writes`；`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲（2026-08-17 gyb 裁，sync-inbox 问题 23）。机器检查（测试 13）三样都查（2026-08-18 gyb 裁，定义处 `06-hooks-and-permissions.md`）：SKILL.md 正文出现的每条 rl 写命令都在这个角色 json 的 `ledger_writes` 里（查询命令不查）；SKILL.md 正文出现的每个账名和目录都在 `reads` 里（按 `reads` 栏定死的两种写法逐个对：账写账名，目录和文件写相对仓库根的路径）；引用的名字都在定义处查得到、母版不抄。

SKILL.md 不抄公共母版的条文，只写一句「按 common/ 执行」，测试会查抄没抄。

## 和别的 part 的接口

- handoffs 的行格式与字段（`parent_id`、`attempts`、`report_paths`、`code_paths`、`batch`、`line`、`progress_note`；`track` 栏 2026-08-21 裁定加进工单、等最后一期落账，见「要同步到别处的」）：`03-ledgers.md`；handoffs 行格式的定义处按 HANDOFF 四点五节是 `04-handoffs-and-sessions.md`。
- decisions 的行格式、编号加版本、来源三类、`root_id`：`02-decisions.md`。
- 七个状态和状态转移表（谁能写、前提、之后谁拉起、对应哪个子命令），以及 holder 只在 `in_progress` 非空这条不变量：`04-handoffs-and-sessions.md`。
- 会话登记与销号、销号时单子怎么交回 `todo`、脏改动打 `wip/<单号>` 分支、收回时半截产物报进 `withdrawn` issue（2026-08-21 裁、等最后一期落 `04`）：`04-handoffs-and-sessions.md`。
- `rl handoff open/start/amend/resume/done/accept/reject/withdraw/release`、`rl issue open/reply/reassign/close`、`rl decision add`、`rl ql open/close`、`rl scratch add`、`rl inbox` 的完整参数和退出码：`05-rl-cli.md`。
- 钩子挂在哪三个工具上（Write/Edit/Bash）、拦哪两类路径、Bash 分支怎么解析目标路径、拦下来怎么回话，角色 json 的文件格式：`06-hooks-and-permissions.md`。
- `ql_tag` 怎么分、worktree 建在哪（`quick_lane.worktree_root`）、杂账三个状态、出口三步的顺序（2026-08-21 裁：先合并再补记，见「要同步到别处的」）：`07-quick-lane.md`。
- 宿主发射器的命令模板、宿主台账清单、new1 的 run.py 注册表三件套和脏树白名单：`08-trees-init-and-host.md`。
- 公共规矩九条（尤其是自决必留痕、故障分域、出圈即留痕、修必销案）、读法、词表、issues 的九种 kind（本份用到 `cannot`、`failed`、`anomaly`、`withdrawn`）：`09-common-and-feedback.md`。
- 工单是谁开的、`explanation` 谁写、验收和打回：`20-pair-idea-deploy.md`。
- 发射单交给 run 之后 run 做什么、run 开回来的 issue 长什么样、派活开场提示全抄的口径（2026-08-21 裁，见「要同步到别处的」）：`21-pair-deploy-run.md`。
- analysis 发现代码问题开 issue 给 deploy：`24-pair-analysis-deploy.md`。
- reviewer 从 `code_paths` 拿要审的代码清单（2026-08-21 裁：全收，含宿主文件）：`25-pair-reviewer-idea.md`。
- `rl status` 的十段（桌面通知与推送表 2026-08-21 裁掉不做）、gyb 越过 owner 验收时给 owner 发 `fyi`：`01-gyb.md`。
- 测试清单里和 deploy 有关的条目（钩子、交付物、快车道、端到端）和施工步骤：`30-build-steps-verify-tests.md`。

## 源文档没写清的（留给 gyb）

（2026-08-21 七条全部裁毕，见裁决记录。原第 4 条里挂着的待验证第 9 条「后台 subagent 能不能跑几小时、父会话结束会不会被杀」仍在 `30` 的待验证清单上，测出的结论不动已裁的开场话与批次交接口径。）

## 第二轮模拟里归到这一份的摩擦（原样，未核实）

来源是 `plans/2026-08-16-research-loop-simulation-round2.md`，按场景分组，序号是那一份里的原序号。这些条目未经核实，原文照抄，不做判断。

### param-tweak（45 步，gyb 动手 8 次）

2. [blocks/missing] 第 26、28、29 步：handoffs 的字段表里没有父单字段，但三处规矩都要它：「那张发射单挂在这张工单上」、doctor 扫「快车道工单已验收但没有关联发射单」、withdraw --cascade「连它派生的下游单一起收」，三处都无从实现
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：handoffs 加一个可选 parent_id 字段，open 时可填，doctor 和 cascade 都按它查

3. [slows/blocked] 第 25、26 步：部署报告要放「experiments/ 下这张工单自己的目录」，而快车道补单是新建直达 done_pending_review、开单时才分配单号，开单又硬要求两份报告路径已经存在，目录名在拿到单号之前取不出来
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：明写快车道补单的报告目录用 ql_tag 命名（experiments/ql-20260816-01/），单号事后不改目录

4. [slows/contradiction] 第 25 步：同一段里先说快车道「不写两层部署报告」，又说合回时补的那张工单要附两份部署报告路径且路径必须存在，等于把免掉的手续原样搬到出口
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：快车道补单只要一份 method 简报，detail 允许用杂账里那几行 ql_tag 记录顶替

6. [slows/contradiction] 第 26、27 步：词表和 idea 一节定死 work_order 是 idea 开给 deploy、owner 就是 from_role、验收人是 owner，但快车道补单写在 deploy 的 ledger_writes 里由 deploy 自己开，成了 deploy 开给 deploy、deploy 验收自己的报告
   - 依据：plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:122; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：明写快车道补单 from_role=deploy、to_role=deploy 且验收人固定为 gyb，入账脚本对这一种单子拒收 deploy 自己 accept

7. [slows/too_heavy] 第 23 到 43 步：改一个学习率的出口是全套正常路：补工单加两份报告、开发射单、起 run subagent、分步计时、runs 账两版、两次验收，整条路 45 步、gyb 亲自动 8 次，和「想法要快速、多次迭代」的目标打架
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：允许快车道合回后把那次杂账里的数字补成 runs 账一行（标 quick_lane 来源），只有 gyb 点名要正式数字时才重跑

9. [slows/contradiction] 第 10 步：快车道说「中间的一切都在 worktree 和杂账里」，免掉的四样里没有决定账；但 deploy 一节说超参取值算自决必须进 decisions.deploy，规矩 2 又是硬的，两种读法都说得通，deploy 不知道该不该写这条决定
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-build-plan.md:246
   - 改法：快车道那一段补一句「不写决定账，合回时在补单里一并补一条 decisions.deploy」

10. [slows/contradiction] 第 10 步：决定的 add 还是 update 判据说「同一件事换个参数就追加一版」，但 rl decision update 只有同一个 actor 能调；原来的学习率写在 decisions.idea 或 decisions.gyb 里，deploy 追不了那一版，只能在自己那本开新条，判据就落空了
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:128
   - 改法：判据补一句「跨角色改参数一律在自己那本开新条，来源指原决定的编号加版本」

11. [slows/contradiction] 第 16、20 步：快车道说数字进杂账不进 runs 账，但 GPU「照旧走 gpu-run」，run.py launch 一条命令自动往宿主 ops/runs.jsonl 登记、Phase 6a 五连还要 record finish 把数字渲进 RESULTS.md；文档没说快车道要不要跑这一步
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:140
   - 改法：快车道那一段明写「宿主台账照登记，record finish 的 conclusion 写 quick_lane 加 ql_tag」

12. [slows/contradiction] 第 16 步：设计文档要求快车道发射时 track 一律填 quick_lane，gpu-run 要求 --track 和 TIMELINE.md 里的方向对得上，quick_lane 不是 TIMELINE 里的任何一条方向
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:91
   - 改法：在 TIMELINE.md 里固定登记一条 quick_lane 方向，或者改成沿用被微调那个实验的 track

13. [slows/ambiguous] 第 12 到 16 步：快车道里 GPU「照旧走 gpu-run」，gpu-run Phase 4 明写发射环节整段派 gpu-runner agent、不在主对话手搓，但 deploy 的 dispatches_to 只有 run，派 gpu-runner 算不算越权没写
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:58; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：deploy 的 dispatches_to 加 gpu-runner 并注明只在快车道用，或明写快车道 deploy 自己发射

14. [slows/ambiguous] 第 10 步：决定来源的 file 类要求「仓库里的文件路径」且路径不存在拒收，快车道改的文件在 worktree 里，主树同路径存在但内容是旧的，填哪个路径、校验查哪棵树两种读法都成立
   - 依据：plans/2026-08-16-research-loop-build-plan.md:43; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205
   - 改法：file 类来源允许带 worktree 或 commit 前缀，校验按给出的那棵树查存在

17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令

18. [cosmetic/missing] 第 26 步：work_order 的 explanation 定义成「idea 自己写的解释」且是必填，快车道全程没有 idea 会话，这段解释谁写、写什么没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:48
   - 改法：补一句：快车道补单的 explanation 由 deploy 写，注明来自 gyb 口头点名并抄一句原话

19. [cosmetic/ambiguous] 第 24 步：「gyb 看着行就合回主分支」这句的主语是 gyb，但 deploy 用 Bash 做 merge 钩子也不拦，谁执行 merge 两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:132
   - 改法：明写 merge 由 gyb 亲自打，deploy 只把命令交出来

### new-idea（39 步，gyb 动手 7 次）

3. [blocks/missing] 第 18 步：handoffs 的字段表里没有父单字段，发射单 ho-0002 挂不到工单 ho-0001 上；可是 withdraw --cascade 要「连它派生的下游单一起收」、doctor 要扫「快车道工单已 accepted 但没有关联发射单」、decision --with-runs 要顺着 handoffs 从决定反查到 run，这三处都依赖这层父子关系
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：handoffs 加 parent_id 字段，rl handoff open 加 --parent ID，launch_order 和快车道补单必填

9. [slows/too_heavy] 整条路：「探针输入从最后一层换成中间层」这一句话的改动，正常路要走 2 张派活单、3 个嵌套会话、2 份部署报告、至少 9 次 rl 写账，和「想法要快速、多次迭代」这条总目标对不上；唯一的减负出口快车道每次都要 gyb 当场点名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给 work_order 加一个 --light 档只要一份 detail 报告，或者明写「同一条决定的第二次及以后的参数微调默认走快车道」

10. [slows/ambiguous] 第 33 步：设计文档说 deploy 验收完发射单「再拿数字接着干工单」，但没写这一步具体产出什么：工单的交付物只有两份部署报告，而报告在开发射单之前就写完了，数字进不进报告没写，于是既可以读成「什么都不用做直接 done」，也可以读成「要把 run_id 和指标补回报告」
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:118; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：明写「发射单验收后 deploy 把 run_id 和关键指标补进 detail 报告，再提 done_pending_review」

11. [slows/missing] 第 15 步：new1 的探针代码没搬进 experiments/，deploy 改的是仓库根的宿主代码，插件只写了钩子放行加「列进报告并留决定」；宿主仓库 CLAUDE.md 要求扩展流水线必须从 probe-pipeline skill 进、代码与 run.py 注册表同一个 commit，两套规矩没有对接句，deploy 会绕过宿主的注册表
   - 依据：plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:132; plans/2026-08-16-research-loop-build-plan.md:10
   - 改法：deploy 的 SKILL.md 加一句「改 experiments/ 外的宿主文件时按宿主仓库 CLAUDE.md 的规矩走，new1 是 probe-pipeline 加 run.py 注册表」

### result-wrong-review（25 步，gyb 动手 11 次）

1. [blocks/missing] 第 3 步和第 4 步：handoffs 没有指向上游单子的字段，发射单的 decision_refs 又不是必填（只有 work_order 必填），所以从一个不对的 run_id 顺不回工单、更顺不回决定：runs.handoff_id 指的是发射单，发射单上既没有 parent 也可以没有 decision_refs，`rl handoff list --decision` 只出工单，`rl decision show --with-runs` 声称「顺着 handoffs 反查跑出的 run」这条链在工单到发射单这一跳断掉。同一个缺口让 `withdraw --cascade` 的「派生的下游单」和 doctor 的「快车道工单已 accepted 但没有关联发射单」都没有判断依据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个必填的 parent_id（发射单指它所属的工单、快车道正式重跑的发射单指那张快车道工单），--cascade、doctor 和反查全按它走。

7. [slows/missing] 第 11 步：reviewer 读顺序第一段要「先读最终的代码」，但没写要审的代码清单从哪来；工单上只有 report_paths 没有代码路径，而 deploy 改到 experiments/ 外的宿主文件（run.py 注册表、MAP.md、ops/）只列在 detail 报告里，读顺序又把 detail 排在最后，先读代码那一遍必然漏掉宿主文件的改动。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：工单加一个 code_paths 字段由 deploy 提验收时填，或明写 reviewer 第一段可以先读 detail 报告里的文件清单那一节、不读它的结论。

### run-crash-midway（40 步，gyb 动手 4 次）

5. [blocks/blocked] 第 24 步：deploy 修完代码之后，发射单 ho-0013 的 launch.command 和 args 还是崩之前那一版，命令表 build-plan.md:134 里没有任何改 launch 子对象的子命令，账又是只增不改（next-steps.md:92）。三条路都不通：带着旧命令跑（跑的和账上写的不一样）、开一张新发射单（旧单子只能 withdraw，转移表里 stuck 走不到重开）、手改账（钩子和入账校验都禁止）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl handoff relaunch ID --command ... --workdir ...`：给发射单追加一版新的 launch 子对象并把状态带回 todo。

10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。

11. [slows/too_heavy] 第 16 到 20 步：deploy 改完一行超参之后，没有任何办法自己确认修对了：next-steps.md:58 明写 deploy 不跑 smoke，快车道要 gyb 点名才能进（next-steps.md:64），所以每一次修复都得走「起 run 会话 → 读档案 → 探卡 → 挑卡 → smoke → 填分步表 → 发射前 commit → 发射」全套；smoke 再挂就又是一条 issue 一轮循环。改一个 batch size 的代价和跑一个新实验一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：允许 deploy 在修 stuck 的发射单时不经 gyb 点名跑一次 smoke 规模的自测，结果写进杂账。

17. [cosmetic/missing] 第 34 步：崩过一次这件事在两份部署报告里没有落点。next-steps.md:56 规定 method 那份只讲做法、用了什么技术、数据怎么被处理，detail 那份带文件和处理细节，两份都不装失败史；reviewer 拿 method 那份当锚审「代码和决定是不是一回事」时，看不到「原来的 batch size 跑不动」这条，只能自己去 issues 账翻。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：detail 那份加一栏「这张单子上关联的 issue 编号和结论」，由 `rl handoff show` 自动列。

### n-launch-orders（58 步，gyb 动手 10 次）

1. [blocks/missing] 第 10、46 步：发射单挂不到工单和决定上：handoffs 的字段表里没有父单字段，转移表对 launch_order 新建也不要求 decision_refs，所以「决定 → 工单 → 5 张发射单 → run_id」这条链在账上是断的。idea 只能从 detail 报告的正文里抄 batch 标签和 run_id 才拿得到这批数字，`rl decision show --with-runs`、`rl run list --decision`、doctor 的「快车道工单已 accepted 但没有关联发射单」三处都没有可走的字段。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:130; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-next-steps.md:64; 2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 parent_handoff 字段，launch_order 和 analysis_order 新建时必填，并自动从父单继承 decision_refs 和 batch。

2. [blocks/missing] 第 11 步：deploy 用什么起那个 workflow、workflow 定义文件放在插件树的哪里、5 张单号怎么分派给 5 个 subagent，三样都没写。插件本体的目录清单里只有 skills/common/tables/schemas/scripts/bin/hooks/monitors/tests，没有 workflows/ 或 agents/；待验证第 8 条的备案里出现过「workflow 里的 agentType 指向 agents/<role>.md」，但那只是备案，正文没定。这个场景的核心机制整个是猜的。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-next-steps.md:150; 2026-08-16-research-loop-build-plan.md:196
   - 改法：在插件树里加一层 workflows/fanout.js（或 agents/<role>.md），明写 deploy 起 N 个 run 时把单号、batch、分到的卡逐个写进 subagent 提示。

4. [slows/missing] 第 16 步：5 个 run subagent 各自实探空卡各自挑卡，中间没有任何互斥，发射单的 launch 子对象里也没有卡位字段，谁给哪张单分哪张卡文档没写。设计文档只说「一张卡一个 run」和「分片对应一次开 N 张同 batch 的发射单」。并发挑到同一张卡时宿主发射器逐 piece 实探非 FREE 就整次拒绝，这正是这个场景里「一张挂了」最容易发生的原因。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:159; .claude/skills/gpu-run/SKILL.md:30
   - 改法：launch 子对象加 host 和 gpus 两个字段，由 deploy 开 N 张单时一次分完；rl 对同一 batch 的挑卡加一把锁。

10. [slows/missing] 第 18 步：run_id 谁定、什么格式没写，只写了它要和产物目录名、tmux session、commit message 一致；宿主发射器还硬要求一个 --track 且要和 TIMELINE.md 的方向对得上，插件九本账里根本没有 track 这个字段，也没写谁给。batch 标签同样没有格式（对比 ql_tag 是给了格式的）。这三样在这一步全靠猜。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:49; 2026-08-16-research-loop-next-steps.md:68; .claude/skills/gpu-run/SKILL.md:86
   - 改法：launch 子对象加 run_id 和 track 两个字段由 deploy 开单时填，batch 照 ql_tag 的样子定成 b-<日期>-<序号>。

13. [slows/missing] 第 26 步：待验证第 9 条（上游 subagent 同步等几小时会不会被超时收掉）的备案正好落在这个场景上，但备案没给续跑规矩：一旦 deploy 开完单就销号，ho-0012 会被销号钩子交回 todo、报告还没写、5 张发射单已经派出去，下一个 deploy 会话重新 start 之后怎么知道进度到哪、去哪找那个 batch，文档没写。
   - 依据：2026-08-16-research-loop-build-plan.md:197; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:120
   - 改法：备案里补一句：work_order 也记 batch，重新 start 时第一件事是 rl handoff list --batch 复原五张单的状态。

### decision-revised-while-in-flight（23 步，gyb 动手 8 次）

2. [blocks/missing] 第 7 步：decision_refs 只对 work_order 必填（build-plan.md:61），文档没有一句要求 deploy 把工单的决定编号抄进发射单，所以 `rl decision stale`（build-plan.md:131）和 `rl handoff list --decision`（build-plan.md:136）都列不出正在跑的 ho-0013。过版检查只看得见工单，看不见真正在花机时的那张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：开 launch_order 时自动从父工单继承 decision_refs 并写进单子，stale 检查按继承后的引用算。

11. [slows/missing] 第 17 步：接单默认是同步的，上游会话等下游 subagent 回来（next-steps.md:120、next-steps.md:17）。等待期间上游会话没有任何中断通道，rl 给它开的 `kind=withdrawn` issue 要等下游返回才看得见。本场景 deploy 从工单被收回到 run 返回的那几个小时里对收回完全无反应，还在等一张已经作废的发射单。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：收回一张有 holder 的单子时，同时给它的下游单子发同一条收回信号，让下游的看门狗把上游一起唤醒；或者明写等待期间的收回一律由 gyb 直接收到最底层那张单。

18. [cosmetic/missing] 第 13、18 步：单子被收回之后，experiments/ 里 deploy 已经写下的代码和产物根里那半截产物目录怎么处置，两份文档都没写。快车道有明确的进出规矩（next-steps.md:64 的 worktree 和合回），正常路收回之后没有对应的一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：转移表转到 `withdrawn` 那一行的前提栏补一句：holder 在返回前把半截产物路径写进那条 withdrawn issue，处置由 gyb 定。

### gyb-manual-takeover（27 步，gyb 动手 9 次）

3. [slows/missing] 第 17 步：正常路的 run_id 谁生成、按什么规则没写。快车道有 ql_tag 的形状规定（ql-20260816-01，兼作宿主要的 run_id，track 一律填 quick_lane），正常路只说 run_id「和产物目录名、tmux session、commit message 一致」，没说谁造、什么格式；发射单的 launch 子对象也只有 command / args / workdir，没有 run_id 和 track 两栏，而宿主 run.py launch 的 --run-id 和 --track 是必填。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:85
   - 改法：在 launch 子对象里加 run_id 和 track 两个必填字段，run_id 由 rl handoff open 时按 ho 号加日期自动生成。

6. [slows/ambiguous] 第 10 步：gyb 坐在 deploy 会话里当场拍板一个影响实验结果的参数，这条落 decisions.deploy 还是 decisions.gyb 两种读法都说得通：deploy 一节说「取第几层、超参取值算自决，进 decisions.deploy」，idea 一节说「gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账」并要求 gyb 定的那一版和角色自决的分得出来。落错了直接影响 reviewer——reviewer 的审查基准只有 gyb 和 idea 层谈定的决定，落进 decisions.deploy 就不在基准里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：在 deploy 一节补一句：gyb 当场拍板的算 gyb 的决定，落 decisions.gyb（--as-gyb 加 --quote），deploy 自决只指 gyb 不在场时自己拿的主意。

8. [slows/too_heavy] 第 11、16、22 步：gyb 亲手接一张已经开出来的正式工单，手续和 subagent 走一模一样：必须开发射单、必须分步计时填 step_table、必须写两份部署报告（method 那份还要原样抄决定编号加版本）。想减手续只有快车道，可快车道的入口是「gyb 点名」加另开一棵 worktree 加 rl scratch add，转移表里也没有「已开出的工单转快车道」这一行，而且审读意见第 1、2 条已经明确否掉了按改动大小分档。gyb 亲自上手的场合反而最重，和「想法要快速、多次迭代」相反。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:178; plans/2026-08-16-research-loop-build-plan.md:82
   - 改法：转移表补一行「todo 的 work_order 由 gyb 改标 quick_lane」，改标之后免发射单和两份报告，只留 scratch 记录。

9. [slows/too_heavy] 第 12 步到第 21 步：gyb 手动的 deploy 会话按默认要同步等 run subagent 跑完才能接着干，实验跑几个小时 gyb 的交互终端就被占几个小时；而「上游 subagent 同步等下游几个小时会不会被超时收掉」还挂在待验证第 9 条上没有结论，备案是「长任务改成 deploy 开单即销号」，两种走法对 gyb 手动会话的体验差别很大。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：对 gyb 手动加载的角色会话默认走异步：开完发射单就把工单 release 回 todo，等 run 完了 rl status 提醒 gyb 再接。

### hook-missed-session-end（23 步，gyb 动手 11 次）

6. [slows/guessed] 步 13、步 14：设计 L120 只写「上游开完单直接起一个 subagent 接走并同步等它回来」，没写下游 subagent 没走到 done 或 stuck 就返回的时候上游拿到什么、该做什么。待验证第 9 条（设计 L168、施工 L197）只问「等几个小时会不会被超时收掉」，不问「等的对象死了怎么办」。最快能发现这件事的就是被阻塞的上游会话，文档没给它任何职责，我只能按原则 3 推它该 release 加重起。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：设计 L120 补一句「下游 subagent 没走到 done 或 stuck 就返回的，上游当场 rl handoff release 并决定重起还是开 issue 给 gyb」，并写进 idea 和 deploy 的 SKILL.md。

### smoke-fails（44 步，gyb 动手 4 次）

2. [slows/contradiction] 步 20 到步 22（run 标卡住之后怎么收场）：转移表有一行 stuck→in_progress，谁能写是 holder，前提是「关联 issue 状态是 answered，holder 会话还活着」。可是接单默认是同步 subagent：deploy 起 run 之后一直等 run 返回。run 要想等到 issue 被回复，就得挂在那儿不返回，而回复它的 deploy 正卡在等 run 返回上，两边互等；run 要是返回，会话就结束，holder 会话不再活着。所以这一行在默认接单模式下永远走不到，smoke 失败只能走「销号—回 issue—回 todo—重起 subagent」的重路。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:86; plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：明写 stuck→in_progress 只给 gyb 手动接的会话用，subagent 接的单子一律以返回上游结束；或者给发射单开一条「同一个 deploy 会话就地修完直接再起 run」的短路并写进转移表。

5. [slows/missing] 步 7（deploy 开发射单）：handoffs 的行格式没有「这张发射单挂在哪张工单上」的字段，只有 work_order 有 decision_refs，launch_order 既不引决定也不引父单。可是设计文档要求 analysis 顺着 handoffs 从决定走到发射单再走到 run_id，doctor 还要扫「快车道工单已 accepted 但没有关联发射单」，两处都需要这条父子边，账上没有地方记。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:80; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：handoffs 加一个 parent 字段，rl handoff open 在角色会话里默认填当前会话正持有的那张单，withdraw --cascade 也照它走。

6. [slows/missing] 步 33（第二次 smoke 通过后发射）：正常路的 run_id 谁定、怎么命名，文档没写。只有快车道写了 ql_tag 兼作宿主发射器要的 run_id、track 一律填 quick_lane。宿主 run.py launch 的 --run-id 和 --track 都是必填，new1 的规矩还要求 run_id 在产物目录名、tmux session、台账 name、commit message 四处一致，run 在这一步只能自己编一个，且 --track 要和 TIMELINE.md 的方向对得上，谁给这个值也没写。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：rl handoff open --type launch_order 时自动分配 run_id 写进 launch 子对象（形如 ho-0013-01），track 由 deploy 开单时必填。

7. [slows/missing] 步 34（rl run add 落发射版）：runs 发射版必填 config 字典，里面要有 model、params、dataset、split，是给 analysis 分组用的；但发射单的 launch 子对象只有 command、args、workdir、estimated_seconds、step_table、actual_seconds，没有 config。run 要么去解析命令行参数，要么去读 experiments/ 的代码猜这四个值，而这四个值本来是 deploy 定的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：把 config 挪到发射单上由 deploy 开单时填，rl run add 默认从发射单抄，run 只补机器和卡。

10. [slows/too_heavy] 步 19 到步 30（整个修复回路）：一个 import 报错要走完：落一条 issue、把单子标 stuck、run 会话销号、deploy 读 issue、改代码、回 issue、把单子拉回 todo、重起一个 run subagent、重读慢变量档案、重探空卡、重挑卡、重跑 smoke。至少八次账写入加两次会话生死。文档还把两条捷径都堵死了：run 不许自行重试，下游不许小修，快车道只能由 gyb 事先点名进、单子已经在正常路上时没有中途改走快车道的路。这和「想法要快速、多次迭代」的目标拧着。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:185; plans/2026-08-16-research-loop-next-steps.md:180; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给发射单加一条 smoke 失败专用短路：run 返回 traceback，deploy 在同一会话里就地修完打 rl handoff release 再起 run，issue 照开但不必等回复，并明写这不算 run 自行重试。

13. [slows/missing] 步 26 到 27（deploy 修完代码）：修 import 有时候要换入口（比如从 python -m pkg.train 换成 python scripts/train.py）或者加环境变量，发射单上写死的 launch.command 就得跟着改。九本账全是事件流、改等于追加一版，可是转移表里没有「改单内容」这一行，命令表里也没有对应的子命令，deploy 只能收回旧单重开一张新单，把 stuck 的 issue 关联关系一起丢掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:18
   - 改法：加 rl handoff amend ID --command ... --workdir ...，只许在 todo 或 stuck 上追加一版，并在转移表里补一行原地追加。

### doctor-findings-fix（24 步，gyb 动手 15 次）

6. [slows/too_heavy] 第 9 到 19 步（修第二类）：第二类的真实病因只是一份报告文件没了，修它却要走「打回 → 加载 deploy 会话 → decision stale → start → 重写报告 → done → accept」七步，中间还要新登记一个会话、还要把单子在四个状态之间转一圈。对着「想法要快速、多次迭代」这条目标偏重。
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:91; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:88
   - 改法：给 done_pending_review 的单子加一条 `rl handoff amend ID --report-detail P`：追加一版只换路径、不改状态、校验路径存在。

8. [slows/ambiguous] 第 19 步（谁来 accept）：gyb 本人坐在 deploy 会话里想验收，按文档要打 `--as-gyb` 并且必须带 `--quote gyb 原话`，缺 quote 退出码 2；可是 rl 只看会话状态文件，分不出这条命令是 gyb 本人敲的还是模型敲的，于是 gyb 本人也得引用自己刚说的一句话。我只能让 gyb 退回裸终端打，多切一次终端。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-next-steps.md:34
   - 改法：`--as-gyb` 缺 quote 时改成交互式追问一次再放行，或者加一个 `--quote-self` 表示 gyb 本人当场敲的。

13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。

## 裁决记录（日期）

- 2026-08-17 来自 sync-inbox 问题 8 的裁决（定义处 `04`，rl-hub-v3 传；gyb 原话「A」）：第十节「出」那段改成先开补单、拿到编号再 `rl ql close --merged --handoff ID` 关杂账，两边互指；补单那一条加「`QL` 存进单子的 `ql_tag` 栏，开单前提是 `ql_tag` 指的杂账行状态是 `open`」。
- 2026-08-17 来自 sync-inbox 问题 9 的裁决（定义处 `03`、`04`，rl-hub-v3 传；gyb 原话「A」）：第六节 `batch` 那一行改成「deploy 填，可选，自由文本，rl 不分配」，「两处原文不一致：batch 谁分」那段改成裁决结论。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `03`、`05`，rl-hub-v3 传；gyb 原话「只有做完了的时候才关，巡检要我本人确认」）：第一节 inbox 五样里通知那一项后面的「（读过即关）」删掉。
- 2026-08-17 来自 sync-inbox 问题 28 的裁决（定义处 `01`，rl-hub-v3 传；gyb 原话「每个角色创建时候，不要自动查收件箱」「C」）：第一节「deploy 上线第一个动作是 `rl inbox`（原则 6）」改成「`rl inbox` 谁需要谁敲，不是上线动作：deploy 被派单拉起时先干那张单，收件箱要看的时候自己敲」。
- 2026-08-17 来自 sync-inbox 问题 23 的裁决（定义处 `05`，rl-hub-v3 传；gyb 原话见 inbox）：查询命令那句后补「`rl doctor --ack`、`--unack` 是写命令、只有 gyb 能敲」，与 `06-hooks-and-permissions.md` 同句一字不差。
- 2026-08-17 rl-hub-v3 审后补：第六节 `batch` 行按 `04-handoffs-and-sessions.md` 字段表补回「`launch_order` 开单时从父单抄」「调用者 `--batch B` 传」（问题 9 原话说 launch_order 从父单抄的规矩照旧）。
- 2026-08-18 来自 `06-hooks-and-permissions.md` 定稿（`d430192`，rl-hub-v4 传；gyb 原话「a」（问题七、八、十一、十二）「6 c」「让idea能写gyb」）：json 副本 `reads` 去括号备注、`dispatches_to` 改「run、gpu-runner」、两条备注移到表下；第二节写别的角色目录那句注 `notes/` idea 也能写；机器检查改三样都查；加两句 SKILL.md 纪律。对回原则 5、8、2。
- 2026-08-18 来自 `09-common-and-feedback.md` 定稿（`aaca3c9`，rl-hub-v5 传；gyb 原话「a」）：两句纪律之后补一句 SKILL.md 骨架按 `common/SPEC-TEMPLATE.md` 五栏写（角色设定、使用场景、可用工具、限制条件、输出样式），「可用工具」只指到角色 json。对回原则 8。
- 2026-08-18 来自 `08-trees-init-and-host.md` 定稿（`eb02403`，rl-hub-v5 传）：五栏骨架句之后补一句「被派活时以插件的角色 agent 类型起 subagent，agent 定义预加载本角色 skill、不带钩子，写权钩子是插件级、按 `agent_type` 认角色」。对回原则 2。
- 2026-08-18 来自 sync-inbox 问题 38 的裁决（定义处 `06`，rl-hub-v5 传；gyb 原话「b」）：两句纪律的第一句改成「钩子拦不到的写法一律不许往四个角色目录和 `loop/` 写，要写就用 Write/Edit 或钩子看得见的 Bash 写法」（Bash 进了钩子匹配范围）。对回原则 2。
- 2026-08-21 来自 `07-quick-lane.md` 定稿（`7a01842`，rl-hub-v5 传）：报告目录约定补「快车道补单用 `experiments/<ql_tag>/`，拿到单号之后不改名」；「两处原文不一致」快车道补单 owner 处收口（开单动作 deploy、owner 记 gyb，定义处 `04` 冻结后待议）；「没写清」第 1 条快车道半边标已裁。对回原则 4。
- 2026-08-21 来自 `01-gyb.md` 定稿（`cd569ab`，rl-hub-v5 传）：接口一节推送表字样按「桌面通知不做」改；公共规矩八条改九条。对回原则 6。
- 2026-08-21 gyb 裁（本份定稿，rl-part-11 问；gyb 选「照单子的编号起名」）：正常工单的报告目录照单号起名（`experiments/<单号>/`）；快车道半边维持 `07` 已裁的 `experiments/<ql_tag>/`。对回原则 6。
- 2026-08-21 gyb 裁（本份定稿；gyb 选「工单格式里加一个位置」）：方向名（`track`）从工单继承——工单格式加方向名一栏，idea 开工单时填，发射单开单时照抄；工单加栏动 `04` 字段表（冻结），等最后一期，见「要同步到别处的」。对回原则 9。
- 2026-08-21 gyb 裁（本份定稿；gyb 选「全收」）：`code_paths` 全收，这张单改过的代码路径不论在不在 `experiments/` 里都进清单，宿主文件也算。对回原则 2。
- 2026-08-21 gyb 裁（本份定稿；gyb 选「开场话把单子内容全抄一遍」）：deploy 后台起 run subagent 的开场提示把单子内容全抄（单号、命令、工作目录、方向名、config、batch），不是只给单号让它查账；成批按批次一次交接（已有规矩不动）。对回原则 9。
- 2026-08-21 gyb 裁（本份定稿；gyb 原话「不能先合并好再记上去吗」加确认「就这么定：先合并再补记」）：快车道出口顺序改成 gyb 先 merge → deploy 开补单、补 `decisions.deploy` → 关杂账；决定来源和报告路径的存在性检查一律按主树查；「主分支上永远只有走过工单的代码」认下合并到补单之间的短窗口。牵连 `07`，见「要同步到别处的」。对回原则 7。
- 2026-08-21 gyb 裁（本份定稿；gyb 选「直接报给 gyb 让他修」）：deploy 跑 doctor 看到自己名下 `done_pending_review` 的报告路径没了，开 issue 报给 gyb 修，自己不动单子；kind 取 `09` 九种里既有的 `cannot`（干不了，`handoff_id` 必填），不加新种。对回原则 1。
- 2026-08-21 gyb 裁（本份定稿；gyb 选「报位置、留着不动，处置由你定」）：单子被收回时 deploy 把已写的代码位置和半截产物目录路径回进那条 `withdrawn` 通知 issue，东西不动，处置由 gyb 定。对回原则 3。
- 2026-08-21 来自 `10-role-idea.md` 定稿（`96459b4`，rl-hub-v6 传）：`rl inbox` 过版项口径统一「本会话手上单子引的过版决定」；feedback 裁决在 `rl inbox` 单列一项、不并进通知（合计五类）。第一节五样清单已一字一致，正文没动。对回原则 6。
- 2026-08-21 来自 `10-role-idea.md` 定稿（`96459b4`，rl-hub-v6 传；gyb 选「允许，两边都算」）：`decision_refs` 可分属不同根决定，跨根的单在每条相关线的视图里都出现；第六节 `line` 行按新口径并句（字段语义定义处 `03` 冻结、等最后一期收口，sync-inbox 问题 43）。对回原则 9。
- 2026-08-21 rl-part-11 定稿自查（按已有裁决补传播，没新问）：第二节钩子口径按 `06` 定稿与 sync-inbox 问题 38 补齐——「只挂 Write 和 Edit 两个工具」「Bash 写出来的文件钩子不看」两句改成三工具口径（Bash 解析重定向、tee、sed -i、mv/cp 目标路径，解析不出的归纪律），与第十一节两句纪律对齐。对回原则 2、8。

## 要同步到别处的

- `04-handoffs-and-sessions.md`（冻结，等最后一期）：handoffs 字段表 `work_order` 加 `track` 一栏（idea 开单时填）；`launch_order` 开单从父单抄 `track`。gyb 原话「工单格式里加一个位置」（2026-08-21）。
- `04-handoffs-and-sessions.md`（冻结，等最后一期）：withdraw 一侧补一句——收回时 holder 把已写的代码位置和半截产物目录路径回进那条 `withdrawn` issue，东西不动，处置由 gyb 定。gyb 原话「报位置、留着不动，处置由你定」（2026-08-21）。
- `05-rl-cli.md`（冻结，等最后一期）：`rl handoff open --type work_order` 要能收方向名；`launch_order` 开单自动从父单抄之后，发射单侧的方向名参数改成可省。
- `03-ledgers.md`（冻结，等最后一期）：`code_paths` 字段说明补「全收：这张单改过的代码路径不论在不在 `experiments/` 里都列，宿主文件也算」。
- `07-quick-lane.md`：出口顺序改成「gyb 先 merge → deploy 开补单、补 `decisions.deploy` → `rl ql close --merged --handoff ID`」；决定来源和报告路径的存在性检查一律按主树查；「主分支上永远只有走过工单的代码」句认下合并到补单之间的短窗口。gyb 原话「不能先合并好再记上去吗」加确认「就这么定：先合并再补记」（2026-08-21）。
- `10-role-idea.md`、`20-pair-idea-deploy.md`：idea 开工单时填方向名一栏，deploy 开发射单照抄。
- `25-pair-reviewer-idea.md`：reviewer 的代码清单按全量口径读（含 `experiments/` 外宿主文件）。
- `12-role-run.md`、`21-pair-deploy-run.md`：派活开场提示全抄单子内容的口径（run 被拉起时开场话里有全貌；裁的场景是 deploy 派 run，别的通道要不要照此由统筹定）。
