# research-loop 第二轮模拟走查（2026-08-16 夜）原始结果

说明：17 个场景各派一个 opus 模拟者、一个 opus 核实者，最后一个 critic。模拟者跑完 16 个（first-init-in-new1 没跑成），17 个核实者和 critic 全部因为月度用量上限没跑成，所以下面的摩擦全部是**未经核实**的模拟者原话，可能有误报。原始输出在 wcjaro2l5.output。

| 场景 | 步数 | gyb 亲自动手次数 | 摩擦条数 | blocks | slows | cosmetic |
|---|---|---|---|---|---|---|
| param-tweak | 45 | 8 | 21 | 2 | 13 | 6 |
| new-idea | 39 | 7 | 14 | 4 | 9 | 1 |
| result-wrong-review | 25 | 11 | 12 | 3 | 8 | 1 |
| plot-new-plan | 17 | 8 | 13 | 1 | 10 | 2 |
| next-plan-after-results | 36 | 16 | 12 | 2 | 9 | 1 |
| run-crash-midway | 40 | 4 | 17 | 3 | 11 | 3 |
| n-launch-orders | 58 | 10 | 18 | 4 | 12 | 2 |
| decision-revised-while-in-flight | 23 | 8 | 18 | 4 | 12 | 2 |
| gyb-manual-takeover | 27 | 9 | 13 | 3 | 10 | 0 |
| two-idea-lines-parallel | 26 | 20 | 14 | 5 | 8 | 1 |
| feedback-round | 15 | 9 | 14 | 2 | 9 | 3 |
| idea-request-notes | 15 | 4 | 10 | 0 | 9 | 1 |
| periodic-reclaim | 27 | 11 | 17 | 3 | 12 | 2 |
| hook-missed-session-end | 23 | 11 | 12 | 1 | 11 | 0 |
| smoke-fails | 44 | 4 | 16 | 1 | 12 | 3 |
| doctor-findings-fix | 24 | 15 | 13 | 2 | 9 | 2 |

## param-tweak（45 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 42 步：设计文档说销号只查「还挂在开干的单子」，施工计划说 end 时扫 holder 是本会话的单子、有就拒绝，没有状态过滤；而转移表里 in_progress→done_pending_review 那一行不清 holder（测试 2 只要求 start 写、stuck→todo/rejected/release/reclaim 清），于是 run 交完活就销不了号，用 --release 又会把已交活的单子打回 todo
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:204
   - 改法：转移表 in_progress→done_pending_review 那一行加「holder 清空」，并把 build-plan:126 的扫描限定成 in_progress 和 stuck 两种状态
2. [blocks/missing] 第 26、28、29 步：handoffs 的字段表里没有父单字段，但三处规矩都要它：「那张发射单挂在这张工单上」、doctor 扫「快车道工单已验收但没有关联发射单」、withdraw --cascade「连它派生的下游单一起收」，三处都无从实现
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：handoffs 加一个可选 parent_id 字段，open 时可填，doctor 和 cascade 都按它查
3. [slows/blocked] 第 25、26 步：部署报告要放「experiments/ 下这张工单自己的目录」，而快车道补单是新建直达 done_pending_review、开单时才分配单号，开单又硬要求两份报告路径已经存在，目录名在拿到单号之前取不出来
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：明写快车道补单的报告目录用 ql_tag 命名（experiments/ql-20260816-01/），单号事后不改目录
4. [slows/contradiction] 第 25 步：同一段里先说快车道「不写两层部署报告」，又说合回时补的那张工单要附两份部署报告路径且路径必须存在，等于把免掉的手续原样搬到出口
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:82; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：快车道补单只要一份 method 简报，detail 允许用杂账里那几行 ql_tag 记录顶替
5. [slows/principle_violation] 第 44 步：违反原则 7（快车道有明确的进和出）和原则 6（进出对称）：进有 rl scratch add 登记，出没有任何登记通道——scratch 只有 add 和 list、行里没有状态字段，handoffs 又没有 ql_tag 字段，rl status 的「没合回的快车道 worktree」这一段永远消不掉
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:21
   - 改法：加 `rl scratch close --tag QL --handoff ID`，status 按有没有 close 行判断合没合回
6. [slows/contradiction] 第 26、27 步：词表和 idea 一节定死 work_order 是 idea 开给 deploy、owner 就是 from_role、验收人是 owner，但快车道补单写在 deploy 的 ledger_writes 里由 deploy 自己开，成了 deploy 开给 deploy、deploy 验收自己的报告
   - 依据：plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:122; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：明写快车道补单 from_role=deploy、to_role=deploy 且验收人固定为 gyb，入账脚本对这一种单子拒收 deploy 自己 accept
7. [slows/too_heavy] 第 23 到 43 步：改一个学习率的出口是全套正常路：补工单加两份报告、开发射单、起 run subagent、分步计时、runs 账两版、两次验收，整条路 45 步、gyb 亲自动 8 次，和「想法要快速、多次迭代」的目标打架
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：允许快车道合回后把那次杂账里的数字补成 runs 账一行（标 quick_lane 来源），只有 gyb 点名要正式数字时才重跑
8. [slows/contradiction] 第 27 步：设计文档说替 gyb 打 --as-gyb 带 --quote「靠纪律，钩子不拦」，施工计划和测试 9 说缺 quote 退出码 2 硬拒收；更麻烦的是 gyb 本人和模型在同一个角色会话里打命令，rl 读的是同一个会话状态文件，分不出是谁打的，硬拒收就连 gyb 自己验收都要造一句原话
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定成硬拒收并只留一个值：gyb 本人在角色会话里用 --as-gyb --by-hand 免 quote，模型用一律要 quote
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
15. [slows/guessed] 第 7 步：快车道的 worktree 建在哪、分支叫什么名字文档一个字没写，deploy 只能自己编一个路径；同一天开第二条快车道时路径撞不撞也没人管
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:141
   - 改法：research-loop.json 加 quick_lane.worktree_root，路径和分支名都用 ql_tag 拼出来
16. [cosmetic/missing] 第 8 步：ql_tag 由调用者用 --tag 手填，谁分配这个 01 序号、撞了怎么办没写；锁那一段只保证自动编号的账不撞号
   - 依据：plans/2026-08-16-research-loop-build-plan.md:141; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl scratch new` 由 rl 在锁里分配 ql_tag 并打印出来
17. [cosmetic/contradiction] 第 4 步：设计文档说 SKILL.md 正文出现的每条 rl 子命令都要在角色 json 的 ledger_writes 里，施工计划的测试 13 只查写命令；deploy 上线要跑的 rl decision stale、rl handoff show 都是查询命令，不在 deploy 的 ledger_writes 里，按设计文档那句机器检查就红
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:215; plans/2026-08-16-research-loop-build-plan.md:103
   - 改法：把设计文档那一句改成「每条 rl 写命令」，或角色 json 加一栏 queries 单列查询命令
18. [cosmetic/missing] 第 26 步：work_order 的 explanation 定义成「idea 自己写的解释」且是必填，快车道全程没有 idea 会话，这段解释谁写、写什么没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:48
   - 改法：补一句：快车道补单的 explanation 由 deploy 写，注明来自 gyb 口头点名并抄一句原话
19. [cosmetic/ambiguous] 第 24 步：「gyb 看着行就合回主分支」这句的主语是 gyb，但 deploy 用 Bash 做 merge 钩子也不拦，谁执行 merge 两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:132
   - 改法：明写 merge 由 gyb 亲自打，deploy 只把命令交出来
20. [cosmetic/missing] 第 3 步：sessions 账要求手动加载也记真实模型名、不记 inherit，而角色 json 的 manual 一律是 inherit；钩子从哪里拿到当前会话的真实模型标识没写，待验证清单里也没有这一条
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「SessionStart 钩子输入里有没有模型标识」，拿不到就退到 rl session start --model unknown
21. [cosmetic/ambiguous] 第 21 步：杂账「跑出来的数字继续追加」，但 scratch 的主键是什么没写：是同一个 ql_tag 追加一版，还是每跑一次开一行新 id，两种读法都成立
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:55
   - 改法：scratch 的主键定为 ql_tag，每跑一次追加一版

## new-idea（39 步，gyb 动手 7 次）

1. [blocks/blocked] 第 8 步：新想法是 gyb 在聊天里当场说出来的，没有旧决定、没有 run_id、没有 analysis 产物，可来源必须至少一项且只有 decision/file/run 三类、明文写着「不设口头这一类」，file 类路径不存在还会被拒收；这条决定链的第一条决定入不了账，后面工单、发射单、runs 全部挂不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:205
   - 改法：明写「一条决定链的首条决定可以拿现有代码文件路径或 notes/ 里 gyb 的报告当来源，两者都没有时硬停并要求 gyb 先写一行 notes/」
2. [blocks/contradiction] 第 31 步和第 34 步：设计文档说销号时只检查「作为 holder 还挂在开干的单子」，施工计划的 rl session end 写的是「扫 holder 是本会话的单子，有就拒绝」，不分状态；run 和 deploy 提完 done_pending_review 时 holder 没被清空（清空只发生在 stuck→todo、rejected、release、reclaim），按施工计划这两个 subagent 都销不了号，而验收人正在同步等它们返回，两头卡死
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:204; plans/2026-08-16-research-loop-build-plan.md:209
   - 改法：施工计划第 126 行改成「只拦 in_progress 和 stuck 的单子」，并在转移表里给 in_progress→done_pending_review 也写上 holder 清空
3. [blocks/missing] 第 18 步：handoffs 的字段表里没有父单字段，发射单 ho-0002 挂不到工单 ho-0001 上；可是 withdraw --cascade 要「连它派生的下游单一起收」、doctor 要扫「快车道工单已 accepted 但没有关联发射单」、decision --with-runs 要顺着 handoffs 从决定反查到 run，这三处都依赖这层父子关系
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：handoffs 加 parent_id 字段，rl handoff open 加 --parent ID，launch_order 和快车道补单必填
4. [blocks/too_heavy] 第 10 步和第 19 步：接单默认是同步的，deploy 等 run 几个小时、idea 又等 deploy，于是 gyb 手动加载的 idea 会话从派单那一刻起被整场实验占住，gyb 想看进度只能另开终端；待验证第 9 条的失败备案只写了 deploy→run 这一层改成开单即销号，idea→deploy 这一层没有备案
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：明写 gyb 手动加载的角色会话一律不同步等下游，开完单即返回，验收由下一次会话或 gyb 在 rl status 里做
5. [slows/contradiction] 第 8 步：设计文档说 gyb 亲自打 --as-gyb 的落 decisions.gyb.jsonl、idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote，可角色会话里的命令全是模型打的，而施工计划规定模型打 --as-gyb 必须带 quote、账行 actor 记 gyb，决定文件又按 actor 拆名，同一条命令按两份文档会落进两个不同文件
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:29; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：明写「decisions.gyb.jsonl 只收裸终端写的行，角色会话里模型打的 --as-gyb 一律落 decisions.<角色>.jsonl 并记 quote」
6. [slows/principle_violation] 第 26 步：违反第 4 条原则「一个字段必不必填看这一版的状态」：runs 和 sessions 的字段表里根本没有 status 字段，必填项是按「version 1 是发射版、version 2 是收尾版」定的，可入账校验被规定成按 status 查，校验器在这两本账上无从下手
   - 依据：plans/2026-08-16-research-loop-next-steps.md:18; plans/2026-08-16-research-loop-next-steps.md:92; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：给 runs 加 status 取 launched/finished、sessions 加 status 取 open/closed，九本账的必填一律按 status 查
7. [slows/missing] 第 4 步：sessions 账要求手动加载也记真实模型标识、不记 inherit，可角色 json 的 manual 一栏写死 inherit，登记钩子调 rl session start --model M 时这个 M 从哪来没写；gyb 手动加载 idea 时钩子拿不到真实模型名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：明写钩子从钩子输入的 JSON 里取 model 字段传给 rl，取不到就记 unknown 并由 rl doctor 列出来
8. [slows/ambiguous] 第 2 步和第 3 步：这个场景走正常路还是快车道两种读法都成立：领路卡片写着「新想法先开 idea 落决定再派工单」，快车道的典型情形又写着「一个想法还没成型先跑一把看看」，而进快车道只看 gyb 点不点名、明说不设别的判据，gyb 不点名的时候模型没有依据选
   - 依据：plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：领路卡片加一句「只想先跑一把看数、不打算留决定和报告的，gyb 直接点快车道；其余走正常路」
9. [slows/too_heavy] 整条路：「探针输入从最后一层换成中间层」这一句话的改动，正常路要走 2 张派活单、3 个嵌套会话、2 份部署报告、至少 9 次 rl 写账，和「想法要快速、多次迭代」这条总目标对不上；唯一的减负出口快车道每次都要 gyb 当场点名
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给 work_order 加一个 --light 档只要一份 detail 报告，或者明写「同一条决定的第二次及以后的参数微调默认走快车道」
10. [slows/ambiguous] 第 33 步：设计文档说 deploy 验收完发射单「再拿数字接着干工单」，但没写这一步具体产出什么：工单的交付物只有两份部署报告，而报告在开发射单之前就写完了，数字进不进报告没写，于是既可以读成「什么都不用做直接 done」，也可以读成「要把 run_id 和指标补回报告」
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:118; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：明写「发射单验收后 deploy 把 run_id 和关键指标补进 detail 报告，再提 done_pending_review」
11. [slows/missing] 第 15 步：new1 的探针代码没搬进 experiments/，deploy 改的是仓库根的宿主代码，插件只写了钩子放行加「列进报告并留决定」；宿主仓库 CLAUDE.md 要求扩展流水线必须从 probe-pipeline skill 进、代码与 run.py 注册表同一个 commit，两套规矩没有对接句，deploy 会绕过宿主的注册表
   - 依据：plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:132; plans/2026-08-16-research-loop-build-plan.md:10
   - 改法：deploy 的 SKILL.md 加一句「改 experiments/ 外的宿主文件时按宿主仓库 CLAUDE.md 的规矩走，new1 是 probe-pipeline 加 run.py 注册表」
12. [slows/ambiguous] 第 37 步：「拿到数字给 gyb 看」两种读法都成立：idea 读九本账全部，可以直接 rl run show 把 metrics 念给 gyb；可另一处写着任何角色不许自己写新的要分析的东西、要看什么 gyb 一条条说由 analysis 记账批准，照抄一个原始指标算不算分析没有界
   - 依据：plans/2026-08-16-research-loop-next-steps.md:52; plans/2026-08-16-research-loop-next-steps.md:30; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：明写「照抄 runs 账 metrics 里的原始数不算分析，任何对比、聚合、画图都要走口径账」
13. [slows/missing] 第 39 步：插件的 loop/ 九本账和 new1 自己的四层记录（TIMELINE.md、DATA.md、RESULTS.md、ops/runs.jsonl）谁写谁不写只交代了 runs 一本两账并存，这次跑出来的数字要不要同时进 RESULTS.md、结论要不要补 TIMELINE 没人负责
   - 依据：plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:163
   - 改法：在 research-loop.json 里列一张宿主台账清单，明写角色一律不碰 TIMELINE/DATA/RESULTS，由 gyb 收尾时手动补
14. [cosmetic/missing] 第 27 步和第 28 步：gpu-run 的 Phase 4 要求把自助监控命令交到用户手上，可这条链上 run 的上游是 deploy subagent、gyb 不在链上；rl status 列的是单子、会话和快车道 worktree，没有一栏给正在跑的实验的日志路径或宿主 watch 命令，gyb 中途只能自己去猜命令
   - 依据：plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:142; .claude/skills/gpu-run/SKILL.md:97
   - 改法：rl status 的在办单子一栏顺带打印 runs 账里的 log_path、artifact_dir 和宿主的 watch 命令

## result-wrong-review（25 步，gyb 动手 11 次）

1. [blocks/missing] 第 3 步和第 4 步：handoffs 没有指向上游单子的字段，发射单的 decision_refs 又不是必填（只有 work_order 必填），所以从一个不对的 run_id 顺不回工单、更顺不回决定：runs.handoff_id 指的是发射单，发射单上既没有 parent 也可以没有 decision_refs，`rl handoff list --decision` 只出工单，`rl decision show --with-runs` 声称「顺着 handoffs 反查跑出的 run」这条链在工单到发射单这一跳断掉。同一个缺口让 `withdraw --cascade` 的「派生的下游单」和 doctor 的「快车道工单已 accepted 但没有关联发射单」都没有判断依据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个必填的 parent_id（发射单指它所属的工单、快车道正式重跑的发射单指那张快车道工单），--cascade、doctor 和反查全按它走。
2. [slows/too_heavy] 第 1 步到第 5 步：gyb 只是想知道「这个数字是按哪条决定跑出来的」，按文档要在裸终端敲 rl status、rl run list、rl handoff show、rl decision list、rl decision show 五条命令，中间还要靠 launch.command 里的路径人工比对，和「想法要快速、多次迭代」的目标不相称。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-build-plan.md:137
   - 改法：第六节命令表加一条 `rl trace <run_id>`，一条命令打出 run 到发射单到工单到决定各版本的整条链。
3. [blocks/contradiction] 第 16 步：设计文档说 reviewer「不开 issue、不派活」，施工计划第十三节公共规矩第 6 条说「analysis 和 reviewer 不在楼梯上，卡住直接开 issue 给出问题的角色」，两句直接打架；而且 reviewer 的角色 json 里 ledger_writes 只有 decisions.reviewer 和 feedback add，没有 issues，真按规矩 6 开 issue 会被入账校验退出码 3，reviewer 中途读不到产物时按文档无路可走。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:250; plans/2026-08-16-research-loop-build-plan.md:109
   - 改法：规矩 6 里把 reviewer 摘出来，明写 reviewer 只写 review/ 清单、卡住也只写进清单交给 gyb。
4. [slows/contradiction] 第 9 步、第 10 步、第 13 步（reviewer 全程只调查询命令）：设计文档说机器检查是「SKILL.md 正文出现的每条 rl 子命令都要在这个角色 json 的 ledger_writes 里」，施工计划的 test_skill_refs 只要求写命令在 ledger_writes 里；reviewer 的 SKILL.md 必然写到 rl decision stale、rl decision show、rl run show、rl handoff show 这些读命令，按设计文档那句检查必挂。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:40; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：把设计文档第 40 行改成「写命令进 ledger_writes、读命令进 reads」，和测试 13 对齐。
5. [blocks/missing] 第 19 步（gyb 若当场废掉或改 dec-idea-0007 而不是让 idea 改）：gyb 给别人的决定追加一版落哪个文件没写：设计文档说 gyb 写的决定落 decisions.gyb.jsonl，又说决定账按 actor 拆六个文件、编号带角色前缀，那 dec-idea-0007 的第 3 版由 gyb 写就会和第 1、2 版分居两个文件，「默认查询只取最新版」和锁里的扫号都要跨文件才对，入账脚本没有依据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:96; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:128
   - 改法：明写「决定行按 id 前缀落文件，谁写的记在 actor 字段」，dec-gyb 前缀只给 gyb 新开的决定。
6. [slows/contradiction] 第 19 步和第 23 步：`--as-gyb` 缺 `--quote` 到底硬不硬拦：设计文档说「这条靠纪律，钩子不拦，reviewer 事后可查」，施工计划第六节说「缺 quote 时 rl 拒收（退出码 2）」；再者 rl 只看会话状态文件，分不出角色会话里这条命令是 gyb 本人敲的还是模型敲的，硬拦会把 gyb 本人一起拦住，和原则 1「任何权限检查对 gyb 不生效」相冲。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：统一成硬拦，并明写 gyb 本人在角色会话里也要带 --quote（自引一句即可），设计文档第 34 行的「靠纪律」删掉。
7. [slows/missing] 第 11 步：reviewer 读顺序第一段要「先读最终的代码」，但没写要审的代码清单从哪来；工单上只有 report_paths 没有代码路径，而 deploy 改到 experiments/ 外的宿主文件（run.py 注册表、MAP.md、ops/）只列在 detail 报告里，读顺序又把 detail 排在最后，先读代码那一遍必然漏掉宿主文件的改动。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:62; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：工单加一个 code_paths 字段由 deploy 提验收时填，或明写 reviewer 第一段可以先读 detail 报告里的文件清单那一节、不读它的结论。
8. [slows/missing] 第 11 步和第 15 步：reviewer 审的是哪一版代码没有锚：清单四栏是决定编号加版本、代码或记录的位置、对不上在哪、建议动作，没有 commit；本场景要审的是跑出那个数字的那一版代码，runs 账里存着 commit，文档没写 reviewer 要按那个 commit 审还是审当前工作树，两种结论可能不一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：清单头部必填 run_id 和 commit，reviewer 明确按 runs 账里那个 commit 审。
9. [slows/missing] 第 7 步：gyb 手动加载角色时 sessions 账要求记真实模型标识、不记 inherit，可角色 json 的 manual 一栏一律写 inherit，登记钩子从哪拿到当前会话的真实模型名文档没写，待验证清单九条里也没有这一条。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「钩子输入里有没有模型标识」，拿不到就在 sessions 账记 unknown-manual 并允许 gyb 事后补。
10. [slows/ambiguous] 第 23 步：决定来源 file 类允不允许指 review/ 里的清单两种读法都通：设计文档举例只有 notes/ 里 gyb 的调查报告和 analysis/ 里的图与 notebook，测试 3 却只检查路径存不存在。审出问题之后更新决定，最自然的来源就是那份清单，入账脚本按哪种写会决定它收不收。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:205; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：设计文档第 46 行明写 file 类是仓库内任意路径，举例补上 review/ 的清单和 experiments/ 的部署报告。
11. [slows/missing] 第 8 步到第 15 步：reviewer 的审查基准只有决定账、不猜 gyb 的意思，可 gyb 起疑的正是「当初谈定的东西和代码不是一回事」，谈定却没被 idea 记进决定账的那部分 reviewer 审不出来，也没有任何一栏让它报告「代码里做了选择但决定账里没有对应行」。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:84
   - 改法：清单四栏加第五栏「决定账里没写但代码里做了的选择」，让 reviewer 把账的空白也报出来。
12. [cosmetic/missing] 第 6 步到第 17 步：reviewer 干活期间没有任何派活单，owner 和 holder 都不存在，rl status 只有等清单落盘之后才在「最近 7 天的 review 清单」那一段看得到；审到一半会话崩掉或 gyb 忘了这件事，收件箱里没有任何痕迹。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:84; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:182
   - 改法：rl status 的活着会话那一段带上 reviewer 会话正在审哪条决定（gyb 点名时用 rl 记一行），或给 reviewer 开一张 owner 是 gyb 的 review_order。

## plot-new-plan（17 步，gyb 动手 8 次）

1. [blocks/contradiction] 第 7 到第 10 步（提口径与开分析单的先后）：转移表规定 analysis_order 新建落 todo 的前提是 evaluation_refs 每项已 approved，但 analysis 的 use case 表把「接分析单」排在「问 gyb 要统计什么并提口径」前面，设计文档也写 analysis 先接单再问 gyb；一个全新的画图计划手上没有任何 approved 口径，照 use case 的顺序开单会被入账校验拒收，照转移表的顺序又要在没有单子的情况下先干活。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-next-steps.md:50
   - 改法：在设计文档 analysis 一节明写新计划的顺序是先开 analysis 会话过口径、口径 approved 之后再开分析单，或者改成分析单可以引 proposed 口径、到 handoff done 时才校验已 approved。
2. [slows/too_heavy] 整条路（第 1 步到第 17 步）：gyb 只想看一眼图，按文档要走 2 次 eval propose、2 次 approve、1 次 handoff open、start、done、accept 共 8 次写账，gyb 本人要介入 8 次；快车道只给 deploy，analysis 没有对应的轻路，和目标里「想法要快速、多次迭代」对不上。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：给 analysis 加一条 gyb 点名的快车道：图先落杂账不开口径不开单，图要被引用或复用的时候再补口径和分析单。
3. [slows/principle_violation] 第 10 步（gyb 开分析单）：违反原则 1。原则 1 写 gyb 在任何终端、任何角色会话里都能行使自己的权，任何权限检查不生效；但施工计划只让 gyb 豁免转移表「谁能写」一栏和「谁能调」检查，「前提」一栏照旧生效，于是 gyb 自己开分析单时被 evaluation_refs 必须 approved 这条前提挡住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:77; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：在施工计划第四节表头明写「前提」一栏对 gyb 生不生效，若生效就把它改称数据完整性校验、和权限检查分开命名。
4. [slows/contradiction] 第 17 步（结束会话）：设计文档说销号时检查这个会话作为 holder 有没有还挂在「开干」的单子，施工计划说 end 时扫 holder 是本会话的单子、有就拒绝，没限状态；转移表里 in_progress 到 done_pending_review 那一行又没写清空 holder，于是单子停在等验收时 gyb 想先关掉会话去看图会被拒绝下线。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87
   - 改法：在转移表 in_progress→done_pending_review 那一行加「holder 清空」，并把销号检查明确限定在 in_progress 和 stuck 两个状态。
5. [slows/missing] 第 10 步与第 16 步之后的下一轮迭代：handoffs 的 decision_refs 每项带 {id, version}，evaluation_refs 只写编号不带版本；口径 approved 之后再追加一版，已经派出去的分析单引的是哪一版查不出来，过版检查命令 rl decision stale 也只覆盖决定账。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：evaluation_refs 改成和 decision_refs 一样的 {id, version}，并让 stale 检查同时扫口径引用。
6. [slows/missing] 第 16 步之后（gyb 看完图想换个画法）：口径账只写了被打回之后 analysis 改了再提一版这条路，没写已经 approved 的口径能不能 update、update 之后 status 回不回 proposed、要不要重新批；也没有决定账那种「同一个问题换做法追加一版、换问题开新条」的判据。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:78; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:216; plans/2026-08-16-research-loop-next-steps.md:46
   - 改法：给 evaluations 抄一条决定账同款判据，并明写 approved 之后 update 一版就回 proposed、必须由 gyb 重新 approve。
7. [slows/missing] 第 6 步与第 8 步（写图口径的 group_by 和 x 轴）：图行必填 group_by、x、y，但文档没写这三栏的取值域是 runs 行的顶层字段、config 字典里的键、还是 analysis 现算的派生量；「按模型规模分组」要落成 config.params 全靠模型自己猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：在第三节 evaluations 字段里写死 group_by 和 x、y 的取值只能是 runs 的顶层字段名、config.<键>、或已 approved 的 metric 编号。
8. [slows/missing] 第 6 步（analysis 读 runs 账找分组键）：历史 run 的 config 里没有这次要用的分组键时没有出路：runs 账只有 run 角色的脚本能写、只增不改，analysis 补不了，文档也没写这时该开 issue 给谁、口径要不要改成从产物目录现算。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:99; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：加一句「分组键在 runs.config 里缺失时 analysis 开 issue 给 gyb（kind 是 cannot），由 gyb 定是补跑、是换口径、还是走 code_path 从产物目录现算」。
9. [slows/ambiguous] 第 9 步与第 15 步（会话里以 gyb 身份写账）：施工计划写「角色会话里的模型用 --as-gyb 必须同时给 --quote」，但 rl 看到的只是同一个 session_id 下的一条命令，分不出键盘前面是 gyb 本人还是模型；gyb 亲手在角色会话里打 --as-gyb 要不要带 quote 两种读法都说得通。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：改成「角色会话里的 --as-gyb 不论谁敲一律要 --quote」，把它定性成痕迹而不是身份判定。
10. [slows/ambiguous] 第 10 步（分析单的 from_role）：owner 被定义成开单角色也就是 from_role，而角色只有五个、gyb 不在角色表里；设计文档和词表都说 gyb 可以开分析单，但 handoffs 的 from_role 能不能填 gyb、gyb 算不算合法 owner 没有明写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:41; plans/2026-08-16-research-loop-build-plan.md:39; plans/2026-08-16-research-loop-next-steps.md:76
   - 改法：在第三节 handoffs 的 from_role 字段写清取值是五个角色或 gyb，并说明 owner 是 gyb 时验收和拉起下游都由 gyb 做。
11. [slows/missing] 第 3 步（钩子登记会话）：sessions 账要求记真实模型标识、不记 inherit，角色 json 里手动加载那一栏又一律写 inherit；钩子调 rl session start 的时候从哪里拿到真实模型名没写。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99
   - 改法：明写 model 由 rl session start 从会话环境或钩子输入里读，读不到就记 unknown 并让 doctor 列出来。
12. [cosmetic/missing] 第 13 步到第 14 步（图画完之后叫 gyb）：单子进 done_pending_review 只出现在 rl status 里，桌面通知只在 issue 改派给 gyb 的时候发；gyb 不坐在这个会话里的时候，得靠自己轮询才知道图画好了。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：把「等 gyb 验收的单子」也接进 rl notify，或者在设计文档里明写这一类只进 rl status、不通知。
13. [cosmetic/missing] 第 12 步（图和 notebook 落盘位置）：决定的来源里把 analysis/ 里的图当仓库内文件路径，init 又说原始数据走配置里的产物根；图和 notebook 进不进 git、多大算大产物要挪到产物根，两份文档都没划线。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：在 research-loop.json 里加一个 analysis 产物根，明写小图和 notebook 进仓库 analysis/、大文件进产物根并在口径行里记路径。

## next-plan-after-results（36 步，gyb 动手 16 次）

1. [blocks/contradiction] 第 20 步：销号时 holder 扫描的范围两处打架：设计文档说只查「还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子」不限状态；同时转移表的 done_pending_review 和 accepted 两行都没写清空 holder，所以一张已验收的分析单会永远把 holder 挂在这个会话上，而逃生口 `--release` 只允许从 in_progress/stuck 走，analysis 会话按字面走关不掉
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:88; 2026-08-16-research-loop-build-plan.md:93
   - 改法：转移表在 done_pending_review、accepted、withdrawn 三行明写 holder 清空，`rl session end` 只扫 in_progress 和 stuck
2. [blocks/blocked] 第 11 到 15 步：analysis_order 新建的前提是 evaluation_refs 每项已 approved，但口径是 analysis 接单之后才提的（角色 json 的 use case 顺序是「接分析单 → 提口径」）。一批新结果第一次要新指标时，单子和口径互为前提；只能靠「gyb 直接开一个没有单子的 analysis 会话先提口径」绕过，而文档从没描述过没有单子的 analysis 会话该怎么交付 notebook 和图
   - 依据：2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:107; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-next-steps.md:80
   - 改法：允许 analysis_order 引 proposed 口径开单、批准落在 done 之前，或明写「先谈口径后开单」并给无单分析会话一个交付落点
3. [slows/principle_violation] 第 14 步：违反原则 1。原则 1 和施工计划裁决 6 说 gyb 不受任何权限检查影响，转移表却只给 gyb 豁免「谁能写」一栏、不豁免「前提」一栏，于是 gyb 自己也开不出引未批口径的分析单、也收不了缺交付物的单子。两句话对「权限检查」的范围理解不一样
   - 依据：2026-08-16-research-loop-build-plan.md:77; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15
   - 改法：把原则 1 改写成「权限检查对 gyb 不生效，数据完整性前提对谁都生效」，并给 gyb 一个 `--force` 带原因写进账行
4. [slows/too_heavy] 第 1 到 36 步整条路：只是「看完一批结果定下一步」，gyb 亲自动作 16 次，其中光批口径就要按行逐条批、图口径还得先有指标口径两级批。设计文档开头写的目标是想法要快速多次迭代，每一条手续都要拿这两点衡量，这条路和那句话拉扯
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-next-steps.md:183; 2026-08-16-research-loop-build-plan.md:69
   - 改法：给「一批结果的例行复盘」开一条批量口令：gyb 一句话批一组口径（rl 记下这句原话展开成多行），图口径自动带上它 uses 的指标
5. [slows/ambiguous] 第 13、19 步：gyb 本人坐在角色会话里敲 `--as-gyb`，rl 分不出是 gyb 敲的还是模型敲的，测试 9 又硬性要求缺 quote 退出码 2，等于逼 gyb 引用自己刚说的话；文档只写了「角色会话里的模型」必须带 quote，没写 gyb 本人要不要
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:211; 2026-08-16-research-loop-next-steps.md:34
   - 改法：明写 `--as-gyb` 一律要 quote、gyb 本人把自己那句话填进去即可，SKILL.md 里给一条示例
6. [slows/ambiguous] 第 26 步：讨论里定下的结论落 decisions.gyb 还是落 decisions.idea 带 quote，判据是「gyb 亲自打的」还是「idea 替 gyb 记的」。可是在手动加载角色的会话里 rl 命令都是模型敲的，「gyb 亲自打」这条路实际只存在于另开裸终端，同一条结论两处都说得通，reviewer 的基准会散在两本账里
   - 依据：2026-08-16-research-loop-next-steps.md:34; 2026-08-16-research-loop-next-steps.md:44; 2026-08-16-research-loop-build-plan.md:121
   - 改法：定死「角色会话里一律落角色那本账带 quote，decisions.gyb 只收裸终端写的」，把判据从「谁亲手敲」换成「哪个会话」
7. [slows/missing] 第 33 步：「这条方向看完结果继续做、设定不变」这一支没有落点。决定不换做法就不追加版、不换问题就不开新条，账上留不下 gyb 看过这批数字并确认继续的痕迹，下一轮 reviewer 和 `rl decision stale` 都看不到这次复核
   - 依据：2026-08-16-research-loop-next-steps.md:46; 2026-08-16-research-loop-next-steps.md:109
   - 改法：加一条 `rl decision confirm ID --source run:... --source file:...`，追加一版正文不变、只增来源
8. [slows/missing] 第 27、36 步：决定 retire 之后，引用它的在办单子没人扫。doctor 的八项扫描和 rl status 的七段都没有「retired 决定名下还有没到终态的单子」这一项，设计文档又把停不停全交给 gyb 点名，忘了收回就一直挂着
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:112
   - 改法：doctor 和 status 各加一项「retired 决定名下还有活单」，附上 `rl handoff withdraw --cascade` 的修法
9. [slows/missing] 第 27 步：`--cascade` 收回下游单子的写入人是上游单的 owner（idea），可发射单的 owner 是 deploy，转移表 withdrawn 那一行「谁能写」只写了 owner，没给级联收回开口子
   - 依据：2026-08-16-research-loop-build-plan.md:92; 2026-08-16-research-loop-next-steps.md:124
   - 改法：转移表 withdrawn 那一行加一句「级联收回时上游单的 owner 可写下游单」，账行记清是级联触发的
10. [slows/ambiguous] 第 31 步：开完工单要不要立刻起 deploy subagent。设计文档说默认上游开完单直接起 subagent 同步等它回来，本场景 gyb 只想定计划不想现在开跑，文档没有「开单但暂不派」的默认，gyb 不当场喊停就会被带进几小时的实施
   - 依据：2026-08-16-research-loop-next-steps.md:120; 2026-08-16-research-loop-next-steps.md:48
   - 改法：`rl handoff open` 加 `--no-dispatch`，SKILL.md 写明 gyb 没说开跑就停在 todo
11. [slows/missing] 第 5 步：sessions 账要求手动加载也记真实模型名不记 inherit，角色 json 的 manual 一律 inherit，文档没写钩子从哪拿到当前会话的真实模型标识，待验证清单第 1 条只验了会话 id
   - 依据：2026-08-16-research-loop-next-steps.md:103; 2026-08-16-research-loop-build-plan.md:71; 2026-08-16-research-loop-build-plan.md:99; 2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「钩子输入里有没有模型标识」，拿不到就先记 unknown 并允许 rl 事后补一版
12. [cosmetic/ambiguous] 第 12 步：派生量口径 approve 时 code_path 必须已存在，可公共规矩 5 又说派生量只用 approved 的口径；analysis 到底能不能为一条还没批的口径先写代码，两种读法都说得通
   - 依据：2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:249
   - 改法：规矩 5 补一句「写代码不算算数，出数才要 approved 口径」

## run-crash-midway（40 步，gyb 动手 4 次）

1. [blocks/missing] 第 3 步：看门狗判死之后的动作链没人写：谁去杀训练进程、判定怎么送到 run 会话手里，两份文档都没有。next-steps.md:70 只写看门狗判卡死和超时两件事、每轮顺带查「被收回」并走中断流程，唯独没写「判死之后怎么办」；build-plan.md:162 只说卡死和超时分开判，:166 只说判定进 issues 账。场景标题里的「看门狗判死把它杀了」在文档里找不到执行者。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:70; plans/2026-08-16-research-loop-build-plan.md:162; plans/2026-08-16-research-loop-build-plan.md:166
   - 改法：在 run 的 SKILL.md Phase 5 写死：monitor 只判、只写自己的状态文件，run 会话每轮读它，杀进程和写九本账一律由 run 会话做。
2. [slows/ambiguous] 第 3、9 步：看门狗写账时 actor 判成谁，两种读法都说得通。build-plan.md:166 说「看门狗的判定进 issues 账」，读成 monitor 自己打 `rl issue open`；但 monitor 是独立进程，按 build-plan.md:121 读不到会话状态文件就判 actor 是 gyb、session_id 是 cli，这条 issue 会记成 gyb 开的。读成 run 会话来打则 build-plan.md:166 那句落空。两种读法分别导致账行 actor 记错，或者 monitor 和会话各开一条重复 issue。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：把 monitor 明确排除在写账者之外，改写成「看门狗的判定由 run 会话转写进 issues 账」。
3. [blocks/contradiction] 第 13 步：销号时扫什么单子，两份文档打架。next-steps.md:126 写「检查这个会话作为 holder 有没有还挂在开干的单子」（只管 in_progress），build-plan.md:126 写「扫 holder 是本会话的单子，有就拒绝并列出」（不限状态）。ho-0013 标 stuck 之后 holder 仍是 sess-run-01（转移表 build-plan.md:84 那一行不清 holder），按施工计划这版销号会被拒绝，而调 `rl session end` 的是钩子不是模型，钩子不会自己去选 `--release` 还是 `--stuck`，链条停在这里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：build-plan.md:126 改成「扫 holder 是本会话且状态为 in_progress 的单子」，并在转移表 in_progress→stuck 那一行注明 holder 保留还是清空。
4. [slows/missing] 第 19 步：转移表 build-plan.md:85 的 stuck→todo（谁能写=回了 issue 的那个角色，前提=关联 issue 已 answered）在 bin/rl 命令表 build-plan.md:134 里没有对应子命令，只能借 `release`；而 release 在转移表 build-plan.md:93 那一行的谁能写是「销号钩子、reclaim、owner」、前提只有「holder 清空」，借它就绕开了「issue 必须已回」这个前提。本场景 deploy 恰好既是 owner 又是回 issue 的人才糊得过去，工单场景（owner 是 idea、holder 是 deploy、回 issue 的是 idea）同样糊得过去但语义已经错位。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：给这一行加一个专门的子命令 `rl handoff resume ID`，前提校验关联 issue 是 answered。
5. [blocks/blocked] 第 24 步：deploy 修完代码之后，发射单 ho-0013 的 launch.command 和 args 还是崩之前那一版，命令表 build-plan.md:134 里没有任何改 launch 子对象的子命令，账又是只增不改（next-steps.md:92）。三条路都不通：带着旧命令跑（跑的和账上写的不一样）、开一张新发射单（旧单子只能 withdraw，转移表里 stuck 走不到重开）、手改账（钩子和入账校验都禁止）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:92
   - 改法：加 `rl handoff relaunch ID --command ... --workdir ...`：给发射单追加一版新的 launch 子对象并把状态带回 todo。
6. [slows/missing] 第 26 步：重跑时分步表没法重置。build-plan.md:135 写明 `rl handoff estimate` 是「往发射单追加分步表一行，estimated_seconds 自动加总」，崩之前那一轮的行还在单子上，第二轮 smoke 的行加上去，estimated_seconds 变成两轮之和，超时判定线（build-plan.md:176 timeout_factor=3 乘 estimated_seconds）跟着虚高三倍，等于关掉了超时看门狗。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:135; plans/2026-08-16-research-loop-build-plan.md:176
   - 改法：`rl handoff estimate` 加 `--reset` 或按重跑轮次分组，estimated_seconds 只加总最新一轮的行。
7. [slows/missing] 第 11 步：崩掉的这一跑没有地方回填真实耗时。`--actual-seconds` 只挂在 `rl handoff done`（build-plan.md:134、:61），而 stuck 这条路永远走不到 done，所以 next-steps.md:70 说的「跑完之后 run 把真实耗时回填，几次之后就知道外推偏多少」在崩溃场景下拿不到样本，偏偏崩之前跑到一半的那段耗时正是校准外推最有用的数据。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:70
   - 改法：把 actual_seconds 挪到 `rl run finish` 上，从 started_at 和 finished_at 自动算，不管退出状态是什么都记。
8. [slows/missing] 第 31、40 步：数字账里 killed 的 r1 和 ok 的 r2 挂同一个 handoff_id，没有任何字段标「r1 这条不算数」。build-plan.md:137 的 `rl run list --handoff/--decision` 会同时吐两条，analysis 按决定或 batch 分组时（next-steps.md:80 说 analysis 要顺决定到发射单到 run_id 这条链）会把废跑混进来；build-plan.md:144 的 doctor 也不扫这种情况（r1 有对应发射单，不报）。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：`rl run list` 默认只出 exit_status=ok 的行，要废跑加 `--all`。
9. [slows/missing] 第 38、39 步：issue 从 answered 到 closed 谁打、什么时候打没写。run 的 ledger_writes 只有 issue open（build-plan.md:105），deploy 和 idea 都有 close（:101、:103）但没规定何时用；`rl status` 七段（:142）只列改派给 gyb 超时的 issue，`rl doctor` 八项（:144）也不扫 answered 未 close 的 issue。结果是每次崩溃都留一条挂着的 issue，只有 gyb 偶然翻到才收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl handoff accept` 时自动 close 掉这张单子关联的 answered issue，doctor 补一项「answered 超过 N 天没 close」。
10. [slows/too_heavy] 第 12 到 20 步：三层会话同步嵌套等待：idea 等 deploy 等 run（next-steps.md:120、:58）。一个训练跑几小时，崩了之后 deploy 修完还要再等一整轮重跑，sess-idea-01 从派单到验收全程挂着不能做别的，与 next-steps.md:7「想法要快速、多次迭代」直接冲突。待验证第 9 条（build-plan.md:197）只测了一层（deploy 等 run），没测两层嵌套，备案也只写了 deploy 那一层。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：发射单一旦标 stuck 就让上游 subagent 立刻返回并销号，重跑由 gyb 在 `rl status` 里另起一个 deploy 会话接。
11. [slows/too_heavy] 第 16 到 20 步：deploy 改完一行超参之后，没有任何办法自己确认修对了：next-steps.md:58 明写 deploy 不跑 smoke，快车道要 gyb 点名才能进（next-steps.md:64），所以每一次修复都得走「起 run 会话 → 读档案 → 探卡 → 挑卡 → smoke → 填分步表 → 发射前 commit → 发射」全套；smoke 再挂就又是一条 issue 一轮循环。改一个 batch size 的代价和跑一个新实验一样。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:58; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：允许 deploy 在修 stuck 的发射单时不经 gyb 点名跑一次 smoke 规模的自测，结果写进杂账。
12. [slows/missing] 第 9、14 步：归角色（不是 gyb）的 issue 没有任何推送，角色上线也没规定要查。build-plan.md:59 只有 assignee 变成 gyb 那一版触发通知，build-plan.md:131 规定的「角色上线第一个动作」只有 `rl decision stale`。本 trace 里 deploy 会话正同步等着才立刻收到；一旦按待验证第 9 条的备案（build-plan.md:197）改成 deploy 开单即销号，iss-0031 就静静躺在账里没人知道，只能等 gyb 打 `rl status`。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:197
   - 改法：角色上线第一个动作改成两条：`rl decision stale` 加 `rl issue list --open --to <本角色>`。
13. [slows/guessed] 第 9 步：跑挂该开哪种 kind 的 issue，只能猜。build-plan.md:45 的六种 kind 是 cannot / not_mine / denied / anomaly / request / withdrawn，没有一种对应「跑挂」；build-plan.md:166 给的命令模板直接写成 `rl issue open --to deploy --kind ...` 把 kind 留空；next-steps.md:72 列了四种要开 issue 的情形（smoke 失败、发射失败、跑挂、结果反常）但只给结果反常指定了 anomaly。本 trace 取 cannot 是猜的，四种情形挤进一个 kind 之后 `rl issue list` 没法按失败类型筛。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：给 run 的四种失败各定一个 kind（smoke_failed / launch_failed / crashed / anomaly），写进第二节词表。
14. [slows/ambiguous] 第 13 步：sessions 账的 open_handoffs_at_end 字段说明是「结束时 holder 还是这个会话的单子列表，正常应为空」（build-plan.md:71），但发射单标 stuck 之后 holder 不清空，run 会话销号时这个字段必然非空。到底是「非空就是异常要拦」还是「非空只是记一笔」，文档没说，两种读法分别对应销号被拒和销号放行。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:84
   - 改法：把这个字段的说明改成「结束时状态还是 in_progress 的单子列表，非空即拒绝销号」，stuck 的单子不算。
15. [cosmetic/missing] 第 6、27、30 步：崩溃分支下宿主那本账怎么收没写。build-plan.md:163 只在 Phase 6a 说明「数字进 loop/runs.jsonl，new1 的 ops/runs.jsonl 照旧由 run.py launch 写，两本并存」，:164 的 Phase 6b 完全没提宿主账，所以 r1 在 ops/runs.jsonl 里那条永远停在 `record start` 没有 finish，宿主的 RESULTS.md 缺一行。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:163; plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-next-steps.md:148
   - 改法：Phase 6b 那一行补一句：`rl run finish --exit failed|killed` 的同时打宿主的 `python3 run.py record finish <run_id>`。
16. [cosmetic/contradiction] 第 23 步：卡住的单子被回复之后谁能接，两处说法不一样。next-steps.md:116 写「卡住的 issue 被回复之后单子回待干，谁接都行」，转移表 build-plan.md:83 的 todo→in_progress 那一行前提写死「写入会话的角色等于 to_role」。按正文任何角色都能接，按表只有 run 能接。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:116; plans/2026-08-16-research-loop-build-plan.md:83
   - 改法：把 next-steps.md:116 的「谁接都行」改成「to_role 的任何一个会话都能接」，与转移表对齐。
17. [cosmetic/missing] 第 34 步：崩过一次这件事在两份部署报告里没有落点。next-steps.md:56 规定 method 那份只讲做法、用了什么技术、数据怎么被处理，detail 那份带文件和处理细节，两份都不装失败史；reviewer 拿 method 那份当锚审「代码和决定是不是一回事」时，看不到「原来的 batch size 跑不动」这条，只能自己去 issues 账翻。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：detail 那份加一栏「这张单子上关联的 issue 编号和结论」，由 `rl handoff show` 自动列。

## n-launch-orders（58 步，gyb 动手 10 次）

1. [blocks/missing] 第 10、46 步：发射单挂不到工单和决定上：handoffs 的字段表里没有父单字段，转移表对 launch_order 新建也不要求 decision_refs，所以「决定 → 工单 → 5 张发射单 → run_id」这条链在账上是断的。idea 只能从 detail 报告的正文里抄 batch 标签和 run_id 才拿得到这批数字，`rl decision show --with-runs`、`rl run list --decision`、doctor 的「快车道工单已 accepted 但没有关联发射单」三处都没有可走的字段。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:81; 2026-08-16-research-loop-build-plan.md:130; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-next-steps.md:64; 2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 parent_handoff 字段，launch_order 和 analysis_order 新建时必填，并自动从父单继承 decision_refs 和 batch。
2. [blocks/missing] 第 11 步：deploy 用什么起那个 workflow、workflow 定义文件放在插件树的哪里、5 张单号怎么分派给 5 个 subagent，三样都没写。插件本体的目录清单里只有 skills/common/tables/schemas/scripts/bin/hooks/monitors/tests，没有 workflows/ 或 agents/；待验证第 8 条的备案里出现过「workflow 里的 agentType 指向 agents/<role>.md」，但那只是备案，正文没定。这个场景的核心机制整个是猜的。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-next-steps.md:150; 2026-08-16-research-loop-build-plan.md:196
   - 改法：在插件树里加一层 workflows/fanout.js（或 agents/<role>.md），明写 deploy 起 N 个 run 时把单号、batch、分到的卡逐个写进 subagent 提示。
3. [blocks/principle_violation] 第 14 步：违反原则 3（每张派活单有 owner 和 holder，holder 是当前正在干这张单子的那一个会话）。转移表 todo→in_progress 那一行的前提只有「写入会话的角色等于 to_role」，没有「holder 为空」这一条，所以两个 run subagent 先后 start 同一张单是合法转移，后一个直接覆盖前一个的 holder，另一张单没人接却在账上看不出来。
   - 依据：2026-08-16-research-loop-build-plan.md:83; 2026-08-16-research-loop-next-steps.md:17
   - 改法：转移表 todo→in_progress 的前提加一句「holder 为空」，已有 holder 时退出码 2 并把当前 holder 列出来。
4. [slows/missing] 第 16 步：5 个 run subagent 各自实探空卡各自挑卡，中间没有任何互斥，发射单的 launch 子对象里也没有卡位字段，谁给哪张单分哪张卡文档没写。设计文档只说「一张卡一个 run」和「分片对应一次开 N 张同 batch 的发射单」。并发挑到同一张卡时宿主发射器逐 piece 实探非 FREE 就整次拒绝，这正是这个场景里「一张挂了」最容易发生的原因。
   - 依据：2026-08-16-research-loop-next-steps.md:68; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:159; .claude/skills/gpu-run/SKILL.md:30
   - 改法：launch 子对象加 host 和 gpus 两个字段，由 deploy 开 N 张单时一次分完；rl 对同一 batch 的挑卡加一把锁。
5. [slows/too_heavy] 第 17 步：同一个 batch 的 5 张单只差一个 seed，每个 run subagent 都要各自读一遍代码、列一遍步骤、跑一遍 smoke、逐步计时、逐步打 estimate。设计文档明说不给「分步计时只对长任务做」的口子，正常路的发射单一律做，于是同一份分步表被重复造 5 次，撞在「想法要快速多次迭代」这个总目标上。
   - 依据：2026-08-16-research-loop-next-steps.md:70; 2026-08-16-research-loop-next-steps.md:179; 2026-08-16-research-loop-build-plan.md:135; 2026-08-16-research-loop-build-plan.md:160
   - 改法：加一条 `rl handoff estimate ID --copy-from <同 batch 的另一张单>`，同 batch 只让第一张单实测分步表，其余按规模系数复制。
6. [slows/missing] 第 34 步：发射单被重跑时分步表没有清空或分版：estimate 是「往发射单追加分步表一行，estimated_seconds 自动加总」，第二次 smoke 的行加在第一次的行后面，预计时长变成两次之和。后果是看门狗的超时线（estimated_seconds 乘 3）和反常预警的 duration_factor 两处一起失真。
   - 依据：2026-08-16-research-loop-build-plan.md:135; 2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:176; 2026-08-16-research-loop-build-plan.md:181
   - 改法：分步表按尝试分组（每次 handoff start 起一个 attempt 号），estimated_seconds 只加总最新一个 attempt 的行。
7. [blocks/contradiction] 第 25、42 步：销号时查 holder 的范围两份文档写得不一样：设计文档说「检查这个会话作为 holder 有没有还挂在开干的单子」，施工计划说「扫 holder 是本会话的单子，有就拒绝并列出」。转移表里 done_pending_review 和 stuck 两个状态都不清 holder，所以按施工计划的读法，4 个跑完的 run subagent 和写完报告的 deploy 会话全都退不出去；按设计文档的读法才能销号。测试清单第 7 条只覆盖了 in_progress 这一种。
   - 依据：2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-build-plan.md:126; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:84; 2026-08-16-research-loop-build-plan.md:209
   - 改法：施工计划第六节改成「只拦 status 为 in_progress 且 holder 是本会话的单子」，done_pending_review 和 stuck 一律放行销号。
8. [slows/contradiction] 第 25 步：转移表里 stuck→todo 有两行且前提打架：一行要求「关联 issue 状态是 answered」，另一行允许销号钩子和 reclaim 只清 holder 就把 stuck 降回 todo。run5 一销号，ho-0017 就在 issue 还没被 deploy 回复的情况下变回 todo，owner 按规矩可以立刻再起一个 run，代码没改照样再挂一次。
   - 依据：2026-08-16-research-loop-build-plan.md:85; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:117
   - 改法：销号钩子和 reclaim 对 stuck 单只清 holder、状态留在 stuck，只有 issue 转 answered 之后才允许回 todo。
9. [cosmetic/missing] 第 24 步：run 出问题的四种情况里，只有「结果反常」在 issue 的六种 kind 里有对应值（anomaly），smoke 失败、发射失败、跑挂三种该填哪个 kind 没写，施工计划第七节那一句直接写成 `--kind ...`。这里只能挑了 cannot。
   - 依据：2026-08-16-research-loop-build-plan.md:45; 2026-08-16-research-loop-build-plan.md:166; 2026-08-16-research-loop-next-steps.md:72
   - 改法：issue 的 kind 加一个 failed（或把三种失败明写成一律用 cannot），并在 run 的 SKILL.md 里一种失败对一个 kind 列成表。
10. [slows/missing] 第 18 步：run_id 谁定、什么格式没写，只写了它要和产物目录名、tmux session、commit message 一致；宿主发射器还硬要求一个 --track 且要和 TIMELINE.md 的方向对得上，插件九本账里根本没有 track 这个字段，也没写谁给。batch 标签同样没有格式（对比 ql_tag 是给了格式的）。这三样在这一步全靠猜。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:49; 2026-08-16-research-loop-next-steps.md:68; .claude/skills/gpu-run/SKILL.md:86
   - 改法：launch 子对象加 run_id 和 track 两个字段由 deploy 开单时填，batch 照 ql_tag 的样子定成 b-<日期>-<序号>。
11. [slows/principle_violation] 第 41 步：违反原则 1（gyb 是超级用户，钩子、入账校验、转移表的谁能写对 gyb 一律不生效）。施工计划规定角色会话里用 --as-gyb 缺 --quote 一律退出码 2，而 rl 分不出键盘前面坐的是 gyb 本人还是模型，结果 gyb 在自己手动加载的角色会话里反而行使不了 gyb 权，只能退出会话回裸终端。这和裁决 6「gyb 在任何终端、任何角色会话里都能插入」直接打架。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-build-plan.md:14; 2026-08-16-research-loop-next-steps.md:15; 2026-08-16-research-loop-next-steps.md:34
   - 改法：缺 quote 时不拒收，改成照写并在账行打一个 quote_missing 标记留给 reviewer 事后查。
12. [slows/missing] 第 18、20 步：5 个 run subagent 的监控入口到不了 gyb 眼前。gpu-run 要求发射后把 gpu-jobs watch 和网页交给用户，但 subagent 的输出只回到 deploy 会话；rl status 列的是单子状态和挂了多久，不含进度、速率、ETA。gyb 在这几个小时里看不到这一批五张卡跑到哪了。
   - 依据：.claude/skills/gpu-run/SKILL.md:97; 2026-08-16-research-loop-build-plan.md:161; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-next-steps.md:124
   - 改法：rl run add 时把宿主的 tmux session 名和监控命令写进 runs 行，rl status 按 batch 汇一段进度出来。
13. [slows/missing] 第 26 步：待验证第 9 条（上游 subagent 同步等几小时会不会被超时收掉）的备案正好落在这个场景上，但备案没给续跑规矩：一旦 deploy 开完单就销号，ho-0012 会被销号钩子交回 todo、报告还没写、5 张发射单已经派出去，下一个 deploy 会话重新 start 之后怎么知道进度到哪、去哪找那个 batch，文档没写。
   - 依据：2026-08-16-research-loop-build-plan.md:197; 2026-08-16-research-loop-build-plan.md:93; 2026-08-16-research-loop-next-steps.md:120
   - 改法：备案里补一句：work_order 也记 batch，重新 start 时第一件事是 rl handoff list --batch 复原五张单的状态。
14. [slows/missing] 第 46 步：同一张发射单重跑之后名下挂了两条 run（一条 killed 一条 ok），`rl run list --batch` 会把 6 条一起吐出来，去重和筛掉失败的规则没写，analysis 按 batch 拉数分组的时候同样吃到这 6 条。这一步只能自己挑。
   - 依据：2026-08-16-research-loop-build-plan.md:63; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-next-steps.md:80
   - 改法：rl run list 默认只出 exit_status=ok 且每张发射单取最新一条，加 --all 才出全部。
15. [slows/ambiguous] 第 48 步：跨 run 的聚合数算谁的活，两种读法都说得通。一种读法：idea 读九本账全部，runs 账的 metrics 就在里面，自己把 5 个数平均一下没人拦。另一种读法：规矩 5 说派生量只用 approved 的口径、由 analysis 算，均值方差正是派生量，idea 自己算就是自作主张。
   - 依据：2026-08-16-research-loop-next-steps.md:52; 2026-08-16-research-loop-next-steps.md:30; 2026-08-16-research-loop-build-plan.md:249
   - 改法：明写一句：单个 run 的 metrics idea 可以直接引，任何跨 run 的聚合一律走 analysis 分析单。
16. [slows/too_heavy] 第 50 到 54 步：口径要 approved 之后才能开分析单，而 approve 又要求 code_path 已经存在，于是同一件事要开两个 analysis 会话：先由 gyb 直接开一个没有单子的 analysis 会话把代码写出来，gyb 批完之后 idea 再开正式分析单让第二个 analysis subagent 重做一遍。5 个种子求个均值走完这一圈要 gyb 亲自动手三次。
   - 依据：2026-08-16-research-loop-next-steps.md:78; 2026-08-16-research-loop-next-steps.md:76; 2026-08-16-research-loop-build-plan.md:69; 2026-08-16-research-loop-build-plan.md:81
   - 改法：允许 analysis_order 引 proposed 的口径，把「已 approved」和「code_path 存在」两条前提一起挪到 handoff done 那一步校验。
17. [cosmetic/missing] 第 13 步：run 上线第一个动作是跑 rl decision stale，但 run 的角色 json 里 reads 不含 decisions 账，发射单上也没有 decision_refs，这条检查对 run 是空转。
   - 依据：2026-08-16-research-loop-build-plan.md:131; 2026-08-16-research-loop-build-plan.md:105; 2026-08-16-research-loop-build-plan.md:81
   - 改法：把「上线跑过版检查」限定给 idea、deploy、analysis 三个角色，或者让 launch_order 继承父工单的 decision_refs 之后 run 再查。
18. [slows/too_heavy] 第 21 步：同一批数字要在两处各填一遍：先按宿主流水线 run.py record finish 写 ops/runs.jsonl，再 rl run finish 写 loop/runs.jsonl，两本并存不合并，谁对账没写。5 张单就是 10 次填数。
   - 依据：2026-08-16-research-loop-build-plan.md:163; 2026-08-16-research-loop-next-steps.md:148; .claude/skills/gpu-run/SKILL.md:143
   - 改法：让 rl run finish 顺带调宿主的 record finish（或反过来），一次输入两本账都落，doctor 加一条两本对账的扫描。

## decision-revised-while-in-flight（23 步，gyb 动手 8 次）

1. [blocks/missing] 第 7、10 步：handoffs 行格式（build-plan.md:61）里没有任何父子字段：launch_order 不记它挂在哪张 work_order 上，重开的单子也不记它接的是哪张旧单。可是 next-steps.md:124 的 `--cascade` 要「连它派生的下游单子一起收」、next-steps.md:80 说 analysis 能「从决定顺到发射单再顺到 run_id」、build-plan.md:144 的 doctor 要扫「快车道工单已 accepted 但没有关联发射单」——三处都要这条链，账里没有这个字段。本场景 idea 打了 --cascade，rl 走不到 ho-0013，正在烧卡的那张发射单收不掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:80
   - 改法：handoffs 加一个 `parent_handoff` 字段，开发射单和分析单时必填，cascade、doctor、链式查询都走它。
2. [blocks/missing] 第 7 步：decision_refs 只对 work_order 必填（build-plan.md:61），文档没有一句要求 deploy 把工单的决定编号抄进发射单，所以 `rl decision stale`（build-plan.md:131）和 `rl handoff list --decision`（build-plan.md:136）都列不出正在跑的 ho-0013。过版检查只看得见工单，看不见真正在花机时的那张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-build-plan.md:136; plans/2026-08-16-research-loop-next-steps.md:111
   - 改法：开 launch_order 时自动从父工单继承 decision_refs 并写进单子，stale 检查按继承后的引用算。
3. [blocks/contradiction] 第 15 步：build-plan.md:164（Phase 6b）写「`rl run finish --exit failed|killed`，发射单标 `stuck` 并开 issue 给 deploy；被收回时也走这里」，而转移表 build-plan.md:92 只允许各状态转到 `withdrawn`，build-plan.md:95 又写「`accepted` 和 `withdrawn` 是终态，表外的转移一律拒收，退出码 2」。run 按 SKILL.md 走到这一步必然吃退出码 2。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:164; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：第七节 6b 拆成两句：跑挂走 stuck，被收回只做 `rl run finish --exit killed` 加收尾，不再动单子状态。
4. [blocks/blocked] 第 16、18 步：转移表转到 `withdrawn` 那一行（build-plan.md:92）的前提栏写「无」，没有像 rejected 和 release 两行那样写「holder 清空」。销号时 `rl session end` 要扫 holder 是本会话的单子，有就拒绝（build-plan.md:126、next-steps.md:126），逃生口 `--release` 是把单子交回 `todo`，可是 `withdrawn` 到 `todo` 在表里不存在。结果 run 会话和 deploy 会话都销不了号，只能等 `rl reclaim`。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-next-steps.md:126
   - 改法：转到 `withdrawn` 的那一行前提栏补「holder 清空」，并明写 session end 只检查未到终态的单子。
5. [slows/contradiction] 第 10、11 步：转移表「谁能写」栏（build-plan.md:92）规定收回只有 owner 能写，而 next-steps.md:124 的 `--cascade` 要求 owner 一条命令连下游单一起收，下游单的 owner 是另一个角色（本场景 idea 收 deploy 的发射单）。两句同时成立就等于 owner 能越过另一个 owner 写单子。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：明写 cascade 是 rl 代 owner 连锁收回、被收的下游单 actor 记发起人并自动给下游 owner 开一条 issue，或者干脆只允许 gyb 用 --cascade。
6. [slows/missing] 第 7 步：文档只在两个时机查过版：「角色上线第一个动作跑过版检查」（next-steps.md:111）和 `rl status`（next-steps.md:124）。决定改版的那一刻，`rl decision update`（build-plan.md:128）不输出任何「有 N 张在办单子引着旧版」的提示。本场景是我按原则 6 让 idea 主动再跑一次 `rl decision stale`，文档没有这条规矩；idea 不跑就没人发现。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:128; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：`rl decision update` 和 `retire` 写完那一刻当场列出引旧版且未到终态的单子，并把它们的 holder 会话一起打印出来。
7. [slows/contradiction] 第 9、20 步：原则 6（next-steps.md:20）写「所有等 gyb 处理的事由 rl status 一处列出，桌面通知只是它的推送」，issues 一节（next-steps.md:97）写「只有改派到 gyb 名下的时候 bin/rl 才给 gyb 发通知，其余不发」。过版、等批口径、等验收这几段按后一句就永远不推送，gyb 只能靠自己想起来跑 rl status。本场景要不是 gyb 自己就是改决定的人，过版没人叫他。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:124
   - 改法：把「哪几段触发推送」列成一张表写进第八节阈值旁边，过版且有 holder 的单子归进推送那一档。
8. [slows/principle_violation] 第 11 步：违反第 1 条原则（next-steps.md:15「任何权限检查对 gyb 一律不生效」）。build-plan.md:121 规定角色会话里用 `--as-gyb` 缺 `--quote` 就退出码 2 拒收，而 rl 分不出这条命令是 gyb 本人敲的还是会话里的模型代打的，于是 gyb 本人在角色会话里行使 gyb 权也会被拒收。本场景 gyb 因此被逼退出去另开一个裸终端才收得掉 ho-0013。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：缺 quote 时不拒收，改成落账时把这一行标 `quote_missing` 交给 reviewer 事后查，硬拦只留给模型自己发起的不可逆动作。
9. [slows/ambiguous] 第 6 步：来源三类不含口头（next-steps.md:46），可是「换个评测集」这种 gyb 当场改主意既没有新文件也没有新 run_id，只能靠 update 默认继承上一版的来源（build-plan.md:57）。于是账上「有新证据的改版」和「临时改主意」长得一模一样，两种读法都说得通：一种是继承就算合规，一种是必须先去 notes/ 落一行再改。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：决定行加一个 `change_reason` 枚举（新证据 / gyb 口头改），口头那档必须同时带 quote，来源仍继承。
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
14. [slows/missing] 第 14、23 步：被收回的发射单跑出来的那条 run（exit killed、config 记的是旧评测集）留在 loop/runs.jsonl 正账里，没有任何作废标记。决定来源的第三类就是 run_id（next-steps.md:46），后面谁都能拿它当来源；doctor 的扫描项（build-plan.md:144）也不查「run 挂在已收回的单子上」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：doctor 加一条扫描「runs 行的 handoff 已 withdrawn」，并且 `rl decision add --source run:ID` 引到这种 run 时当场警告。
15. [slows/contradiction] 第 3 步：sessions 账要求「手动加载记真实模型名，不记 inherit」（next-steps.md:103、build-plan.md:71），角色 json 的 model 栏又写「`manual` 一律 `inherit`」（build-plan.md:99）。钩子调 `rl session start --role R --model M`（build-plan.md:126）时那个 M 从哪里取，两份文档都没写，第九节待验证清单也没有这一条。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:126
   - 改法：把「钩子输入里有没有模型标识」加进第九节待验证清单，拿不到就允许 sessions.model 记 `unknown`，两处口径统一。
16. [slows/too_heavy] 第 6 到 22 步整段：「换个评测集」这一件事走了 23 步、gyb 亲自动手 8 次、牵动 4 个会话，其中 5 步是纯手续（分两次收单、两个会话销不掉号、手动关两条通知 issue、按新版本重开一张内容几乎相同的工单）。目标那一节写的是「想法要快速、多次迭代」（next-steps.md:7），这条路上没有任何一条把「决定改版后重派」压成一步的捷径。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：加一条 `rl handoff reissue ho-XXXX --decision ID@V`：一条命令连锁收旧单、清 holder、继承 explanation 开新单，并通知全部 holder。
17. [cosmetic/missing] 第 21 步：重开的 ho-0014 和被收回的 ho-0012 之间没有任何字段能看出是同一件事的第二次派发（handoffs 行格式 build-plan.md:61 里没有 supersedes 之类的栏），`rl status` 和 `rl handoff list --decision` 都只会把它们并排列成两张单。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:133
   - 改法：handoff open 加 `--supersedes ho-XXXX`，写进单子并在 status 里归成一组。
18. [cosmetic/missing] 第 13、18 步：单子被收回之后，experiments/ 里 deploy 已经写下的代码和产物根里那半截产物目录怎么处置，两份文档都没写。快车道有明确的进出规矩（next-steps.md:64 的 worktree 和合回），正常路收回之后没有对应的一句。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:92
   - 改法：转移表转到 `withdrawn` 那一行的前提栏补一句：holder 在返回前把半截产物路径写进那条 withdrawn issue，处置由 gyb 定。

## gyb-manual-takeover（27 步，gyb 动手 9 次）

1. [blocks/contradiction] 第 20 步和第 27 步：销号时扫什么单子两处写法不一样：设计文档说「检查这个会话作为 holder 有没有还挂在开干的单子」（只管 in_progress），施工计划说「扫 holder 是本会话的单子，有就拒绝并列出」（不限状态）。而转移表里 in_progress→done_pending_review 和 done_pending_review→accepted 两行都没有清 holder 这一步（测试 2 只要求 stuck→todo、rejected、release、reclaim 时清），所以按施工计划那句读，run subagent 和 gyb 的 deploy 会话都会在销号时被拒；钩子跑在会话结束那一刻，没法交互补 --release。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:87; plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:204; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：施工计划第 126 行改成「只扫 status 是 in_progress 或 stuck 的单子」，并在转移表 in_progress→done_pending_review 那一行补上「holder 清空」。
2. [blocks/missing] 第 1 步：没有任何办法表达「这张单 gyb 手动接，别起 subagent」：rl handoff open 没有这个旗子，handoffs 行里没有这个字段，idea 的默认动作是开完单直接起 deploy subagent 并同步等。gyb 的口头交代不进账，idea 会话一旦重开或被 reclaim，idea 还会按 owner 职责再拉起一个下游，两个会话抢着打 rl handoff start，晚的那个撞上「表外转移一律拒收」拿退出码 2。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:83; plans/2026-08-16-research-loop-build-plan.md:95
   - 改法：给 handoffs 加一个 dispatch 字段（auto / manual），rl handoff open 带 --manual 时 owner 不起 subagent、rl status 单列这类单子。
3. [slows/missing] 第 17 步：正常路的 run_id 谁生成、按什么规则没写。快车道有 ql_tag 的形状规定（ql-20260816-01，兼作宿主要的 run_id，track 一律填 quick_lane），正常路只说 run_id「和产物目录名、tmux session、commit message 一致」，没说谁造、什么格式；发射单的 launch 子对象也只有 command / args / workdir，没有 run_id 和 track 两栏，而宿主 run.py launch 的 --run-id 和 --track 是必填。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:64; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:85
   - 改法：在 launch 子对象里加 run_id 和 track 两个必填字段，run_id 由 rl handoff open 时按 ho 号加日期自动生成。
4. [blocks/missing] 第 17 步：没写 loop/ 九本账进不进 git、要不要加进宿主的脏树白名单。new1 的门禁把 ops/jobs.json、ops/runs.jsonl、RESULTS.md、*.lock 排除在脏之外，loop/*.jsonl 不在里面；而每一条 rl 命令都在追加行，run 走到「发射前 commit」那一刻工作树必脏，要么把账本一起 commit 进去（发射前 commit 那一步禁止 --allow-dirty），要么被门禁拦住。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-build-plan.md:161; /home/y-guo/reproduce/new1/CLAUDE.md:36; /home/y-guo/reproduce/new1/.claude/skills/gpu-run/SKILL.md:54
   - 改法：rl init 时把 loop/*.jsonl 和 loop/.lock 一起加进宿主 run.py 的脏树白名单，并在 research-loop.json 里记一句账本入不入 git。
5. [slows/contradiction] 第 13 到 19 步：run 角色 skill 照 gpu-run 写、能力至少覆盖它的全生命周期，等于 GPU 活从 run skill 走；但 new1 的 CLAUDE.md 是「任何要用显卡跑的程序一律走 gpu-run skill，禁止绕过」，而 rl init 明写「往 CLAUDE.md 追加一节，追加不覆盖，new1 原有的规矩照旧」。两条都是工程内的规矩，原则 8 的「工程内为准」裁不动这一对。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:19; plans/2026-08-16-research-loop-build-plan.md:153; plans/2026-08-16-research-loop-next-steps.md:148; plans/2026-08-16-research-loop-next-steps.md:22; /home/y-guo/reproduce/new1/CLAUDE.md:3
   - 改法：rl init 追加的那一节里明写一句「加载了 run 角色的会话以 run SKILL.md 为准，gpu-run 铁律对它不适用」，并同步改 new1 CLAUDE.md 第 3 行。
6. [slows/ambiguous] 第 10 步：gyb 坐在 deploy 会话里当场拍板一个影响实验结果的参数，这条落 decisions.deploy 还是 decisions.gyb 两种读法都说得通：deploy 一节说「取第几层、超参取值算自决，进 decisions.deploy」，idea 一节说「gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账」并要求 gyb 定的那一版和角色自决的分得出来。落错了直接影响 reviewer——reviewer 的审查基准只有 gyb 和 idea 层谈定的决定，落进 decisions.deploy 就不在基准里。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:60; plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:88; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：在 deploy 一节补一句：gyb 当场拍板的算 gyb 的决定，落 decisions.gyb（--as-gyb 加 --quote），deploy 自决只指 gyb 不在场时自己拿的主意。
7. [slows/ambiguous] 第 10 步、第 26 步：--as-gyb 的 --quote 是给「模型替 gyb 打」设的，可 rl 拿不到「这条命令是 gyb 的手指打的还是模型打的」这个信息，同一个角色会话里两种情况长得一模一样。要么一律强制 quote（gyb 本人被迫引用自己一句话），要么一律不强制（模型代打的痕迹就没了）。本次模拟只能绕道：gyb 另开裸终端验收。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:211
   - 改法：定死一律强制 --quote，gyb 本人打的时候 quote 里填自己那句话；文档里把这条写成「无条件」而不是「模型用的时候」。
8. [slows/too_heavy] 第 11、16、22 步：gyb 亲手接一张已经开出来的正式工单，手续和 subagent 走一模一样：必须开发射单、必须分步计时填 step_table、必须写两份部署报告（method 那份还要原样抄决定编号加版本）。想减手续只有快车道，可快车道的入口是「gyb 点名」加另开一棵 worktree 加 rl scratch add，转移表里也没有「已开出的工单转快车道」这一行，而且审读意见第 1、2 条已经明确否掉了按改动大小分档。gyb 亲自上手的场合反而最重，和「想法要快速、多次迭代」相反。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:56; plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:178; plans/2026-08-16-research-loop-build-plan.md:82
   - 改法：转移表补一行「todo 的 work_order 由 gyb 改标 quick_lane」，改标之后免发射单和两份报告，只留 scratch 记录。
9. [slows/too_heavy] 第 12 步到第 21 步：gyb 手动的 deploy 会话按默认要同步等 run subagent 跑完才能接着干，实验跑几个小时 gyb 的交互终端就被占几个小时；而「上游 subagent 同步等下游几个小时会不会被超时收掉」还挂在待验证第 9 条上没有结论，备案是「长任务改成 deploy 开单即销号」，两种走法对 gyb 手动会话的体验差别很大。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:168; plans/2026-08-16-research-loop-build-plan.md:197; plans/2026-08-16-research-loop-next-steps.md:7
   - 改法：对 gyb 手动加载的角色会话默认走异步：开完发射单就把工单 release 回 todo，等 run 完了 rl status 提醒 gyb 再接。
10. [slows/principle_violation] 第 3 步：违反原则 1（谁在打命令和会话装了什么角色是两回事，账行如实记 actor 和会话两样）。这条链上第 5 到第 23 步全部由 gyb 本人驱动，可 sessions 账只有 role 和 model 两栏、handoffs 只有 holder 一栏、每条账行的 actor 只能填角色名，事后没有任何字段能分出「这张单是 gyb 亲手干的」还是「subagent 干的」；reviewer 要查也查不到。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-next-steps.md:120
   - 改法：sessions 账加一栏 launched_by（manual / subagent / workflow），钩子登记时按有没有父会话填。
11. [slows/missing] 第 26 步：gyb 越过 owner 直接验收之后，没有任何通道把这件事告诉 owner idea。转移表 done_pending_review→accepted 那一行第五栏是「无」，issues 账只在改派给 gyb 时发通知，rl status 是给 gyb 的收件箱不是给角色的。idea 会话下次上线只会看到单子已经是终态，不知道是谁验的、为什么验过。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:88; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：gyb 代 owner 写终态转移时，rl 自动给 owner 角色开一条 kind=not_mine 之外的新 kind（比如 fyi）的 issue，或者在角色上线时和 decision stale 一起报一句「你名下的单子被 gyb 处理过」。
12. [slows/missing] 第 6 步：取一条决定的指定版本没有命令。rl decision show 只有默认最新版和 --history 全量两档，可单子按派出时引的那一版继续做，deploy 要的就是 dec-idea-0007 第 2 版；只能把全部历史拉进上下文再自己挑，和读法纪律「挑最小的读法、大文件禁止整读」直接顶上。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:130; plans/2026-08-16-research-loop-next-steps.md:112; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision show 加一个 --version V 参数，handoff show 里显示 decision_refs 时顺带把那一版正文带出来。
13. [slows/guessed] 第 13 步：整段「deploy 会话起 run subagent、subagent 里加载角色 skill、头部钩子装得上、写权拦得住」建立在待验证第 8 条上，那一条还没测，备案是改走 workflow 的 agentType 或者干脆只靠纪律。我按主案（钩子装得上）走完了这一段，主案不成立的话第 13 到 20 步的登记、销号、写权全部要换写法。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:167; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-build-plan.md:227
   - 改法：施工步 0 先把第 8 条测掉，测完在设计文档 run 一节写死走主案还是备案，不留两种走法。

## two-idea-lines-parallel（26 步，gyb 动手 20 次）

1. [blocks/missing] 第 2、6、9、20、25 步：九本账里没有任何一个字段说一行属于哪条研究线。公共骨架六样是 id/version/ts/actor/session_id/schema_version，decisions 按 actor 拆六个文件不按线拆，issues、evaluations、scratch、sessions 四本账各自的字段表里也没有线维度。gyb 早上第一眼要分清两条线，只能靠自己记住哪个决定编号属于哪条线。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-next-steps.md:96
   - 改法：公共骨架加一个可选的 line 字段，rl 的 status/list/show 全部加 --line 过滤，开单和提口径时从上游单子自动继承。
2. [blocks/missing] 第 3、4 步：「根决定」这个归组键没有定义。设计文档说 status 可按根决定归组、施工计划写 --group-by decision，但 decisions 行上只有 sources 没有 parent 或 root 字段；两个旧决定合并成新决定之后一条决定有多个被合并的旧编号，往上走根不唯一。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:110
   - 改法：要么给 decisions 加一个显式 root_id（merge 时指定保留哪个根），要么把 --group-by decision 定义成「按单子上直接引的决定编号分组」并在文档里写死这一句。
3. [blocks/contradiction] 第 4、7 步：handoffs 字段表里没有指向父单的字段，但至少四处规矩依赖这条派生链：转移表的 --cascade 要收「派生的下游单」、测试 15 要 cascade 收掉派生的发射单、快车道正式重跑的发射单要「挂在这张工单上」、doctor 要扫「快车道工单已 accepted 但没有关联发射单」；设计文档还直接断言存在「从决定顺到发射单再顺到 run_id 的那条链」，rl decision show --with-runs 和 rl run list --decision 都靠它。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:92; plans/2026-08-16-research-loop-build-plan.md:217; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:80; plans/2026-08-16-research-loop-build-plan.md:130
   - 改法：handoffs 加一个 parent_handoff 字段，launch_order 和 analysis_order 新建时必填（快车道补单可空），转移表新建那一行的前提栏写进去。
4. [slows/ambiguous] 第 5 步：batch 一个字段被当成两种粒度用。设计文档定义 batch 是 deploy 一次开 N 张发射单的共用标签（分片级），修订记录却把「两条 idea 线归不了组」列成靠 batch 标签解决的问题（研究线级）。gyb 打 --group-by batch 看到的到底是两条线还是两次分片，两种读法都说得通。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:68; plans/2026-08-16-research-loop-next-steps.md:214; plans/2026-08-16-research-loop-build-plan.md:61
   - 改法：batch 只保留分片语义，线级归组交给新加的 line 字段，把修订记录里「两条 idea 线归不了组」那一项的解决办法改成 line。
5. [slows/contradiction] 第 2 步：rl status 列几段两处不一样：设计文档列七段（单子、issue、口径、等验收、过版、review 清单、快车道 worktree），施工计划列八段（多一段「活着的会话」）。按原则 8，施工计划只有第一节的裁决优先，第六节是草案，所以设计文档赢、「活着的会话」被砍——而本场景里 gyb 恰恰要靠这一段看两条线各有谁在干活。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-next-steps.md:22
   - 改法：把「活着的会话」补进设计文档第 124 行那句，两处对齐成八段。
6. [slows/too_heavy] 第 9、10、20、25 步：收件箱里每一条都要两跳才知道属于哪条线：issue 行只有可选的 handoff_id，要 issue show 再 handoff show；口径行只有自由文本 applies_to；scratch 行只有 ql_tag、worktree、base_commit。一条线一天挂三五条，早上第一眼就变成十几条命令。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:69; plans/2026-08-16-research-loop-build-plan.md:73; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：rl status 每行直接把这一行溯到的决定编号和线名打出来，别让 gyb 自己跳。
7. [slows/contradiction] 第 12 步：转移表里 stuck→todo 有两行都能匹配，两套「谁能写」：一行写「回了 issue 的那个角色」、前提是关联 issue 已 answered；另一行是 in_progress/stuck→todo，写的人是销号钩子、reclaim、owner 的 release，前提只有 holder 清空。文档同时说入账脚本只认这张表、表外一律拒收，撞到两行按哪一行校验没写。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:85; plans/2026-08-16-research-loop-build-plan.md:93; plans/2026-08-16-research-loop-build-plan.md:95; plans/2026-08-16-research-loop-build-plan.md:134
   - 改法：把第 93 行那一行的「从」缩成只有 in_progress，stuck 的出口只留第 85 行并把销号钩子和 reclaim 并进那一行的「谁能写」。
8. [blocks/missing] 第 13 步：owner 是角色不是会话，owner 角色没有活着的会话时谁把它叫醒没写。原则 3 和交接一节四处都写「回到待干、由 owner 重新拉起下游」，本场景蒸馏线的 deploy 会话已销号，账上只剩一张 todo 单子和一个不存在的 owner。按原则 1 只能推出 gyb 有权自己干，推不出系统怎么提醒他该开哪个角色的会话。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:17; plans/2026-08-16-research-loop-next-steps.md:48; plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:93
   - 改法：rl status 单列一段「等 gyb 拉起」：owner 角色没有活会话的 todo 单子，每行附上该开哪个角色会话的那条命令。
9. [cosmetic/contradiction] 第 14 步：手动加载的会话在 sessions 账里 model 记什么，两处打架：sessions 行格式写「真实模型标识，手动加载也记真实的，不记 inherit」，角色 json 那一栏写「model 分 as_subagent 和 manual，manual 一律 inherit」。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：角色 json 那一栏加半句「manual 写 inherit 是声明跟当前会话走，sessions 账落解析后的真实模型名」，两句各自限定清楚。
10. [blocks/blocked] 第 22 步：分析单和口径互为前提。新建 analysis_order 的前提是 evaluation_refs 每项已 approved，设计文档也写「单子里只能引已经批准的口径行」；而 analysis 的 use case 第一条是接分析单，接完才问 gyb 要统计什么、才提口径给 gyb 批。一批新数出来之后的第一张分析单永远开不出来。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-next-steps.md:50; plans/2026-08-16-research-loop-next-steps.md:76; plans/2026-08-16-research-loop-build-plan.md:107
   - 改法：把 evaluation_refs 每项 approved 这个前提从新建那一行挪到 in_progress→done_pending_review 那一行，新建时允许空。
11. [slows/too_heavy] 第 15、18 步：角色上线第一个动作 rl decision stale 没有范围参数，列的是全库过版的单子和决定。两条线并行时，蒸馏线的 deploy 一上线就把探针线的过版项读进上下文，和读法纪律「读进来的每个字都留在上下文里挤占后面的判断、只读自己需要的那部分」直接顶。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:131; plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-next-steps.md:144
   - 改法：rl decision stale 加 --mine 和 --handoff 两个过滤，角色上线默认只查本会话要接的那张单子相关的决定。
12. [slows/missing] 第 26 步：rl status --json 每行带哪些字段没写。命令表只有一句「所有子命令支持 --json 输出机器可读结果」，没写 status 的 json 行结构。gyb 想自己写脚本按线切，不知道 json 里有没有 decision_refs、batch、workdir 这些能认线的字段。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:147; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：在命令表第六节写死 status --json 的行结构，至少含 id、work_type、owner、holder、status、挂了多久、decision_refs、batch。
13. [slows/principle_violation] 第 2 到 10 步整段：违反原则 6（进出对称、等 gyb 的事一处汇总）。一处汇总做到了，进出对称没做到：账里能写进 batch，却没有任何一个查询能按线一次拿全这条线的三类单子加 issue 加口径加快车道；status 把两条线混排成一段，gyb 每条还要两跳才认线，「一处列出」在两条线并行时退化成「一处混排」。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：原则 6 补一句「一处列出的同时必须能按线切开」，并给 status 和各 list 命令加 --line。
14. [slows/principle_violation] 第 1 到 26 步整条路：违反原则 5（权限从动作倒推）的做法本身。五份角色 json 都从 use case 表倒推，而 gyb 明写「不在表里」，所以 gyb 自己的日常动作（早上分清两条线、逐条认线、批口径、把没人接的单子拉起来）从来没被倒推过一遍，status 和 list 的过滤维度是从五个角色的需求推出来的，不是从 gyb 的需求推出来的。这条路上 gyb 亲自动手二十次，其中十次是纯查询拼图。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:19; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：给 gyb 也写一张 use case 表（开工第一眼、批、验收、拉起、回收），从这张表倒推 status 和各 list 命令要哪些过滤维度和哪些输出栏。

## feedback-round（15 步，gyb 动手 9 次）

1. [blocks/principle_violation] 第 3、6 步（feedback 落账之后没人叫 gyb）：违反八条原则第 6 条「所有等 gyb 处理的事一处汇总」：feedback 的 proposed 版既不进 rl status 的七段，也不触发通知（通知只给 issue 改派到 gyb 那一版），gyb 唯一的兜底是七天一次的定时提醒 notify.reminder_days，一条规矩改动最坏挂七天
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:183
   - 改法：rl status 加第八段「等 gyb 裁的 feedback」，并让 rl feedback add 走 issue 那条通知通道发一次桌面通知
2. [blocks/principle_violation] 第 7 步（gyb 查 feedback）与第 13 步（deploy 想知道裁决结果）：违反第 6 条「进出对称」和第 5 条「权限从动作倒推」：deploy、run、analysis 三份角色 json 的 ledger_writes 都有 feedback add，reads 里都没有 feedback；命令表也只有 feedback list 没有 feedback show。提反馈的角色写得进去、查不出来，自己提的那条被采纳还是被否只能靠 gyb 口头说
   - 依据：plans/2026-08-16-research-loop-build-plan.md:103; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:107; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:94
   - 改法：五份角色 json 的 reads 一律加 feedback，命令表补 `rl feedback show ID`
3. [slows/contradiction] 第 4 步（deploy 提完 feedback 之后接着干还是停）：公共规矩第 7 条写「提到 feedback 等 gyb 裁」，设计文档 feedback 那一条写「母版改动在下次加载角色时生效，正在跑的会话不追」；前一句读成停下来等裁决，后一句读成照旧按现行母版干到底，两种读法都说得通
   - 依据：plans/2026-08-16-research-loop-build-plan.md:251; plans/2026-08-16-research-loop-next-steps.md:101
   - 改法：规矩第 7 条改成「提完继续按现行母版干，不等裁决；裁决只对下次加载的会话生效」
4. [slows/contradiction] 第 11 步（rl feedback accept 填 applied_to）：applied_to 的口径是「改了母版哪个文件」，单值；但按原则 8「后裁的赢、要回来把正文那一行改掉、不留两个值」，一条采纳的规矩至少要同时改母版 common/GLOBAL-RULES.md 和施工计划第十三节那一行，单值记不下第二处，doctor 也没有一条扫描去查第二处漏没漏
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-next-steps.md:22; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：applied_to 改成路径列表，rl doctor 加一条「accepted 的 feedback 的 applied_to 没同时含母版和设计或施工文档」
5. [slows/missing] 第 12 步（正在跑的 analysis 会话和 idea 会话怎么办）：母版改了以后，正在跑的会话按旧规矩产出的东西算不算数（要不要打回、收回、重做）没写；账上也没有任何地方记得住某个会话是在哪一版母版下跑的：sessions 账只有 session_id、role、model、started_at、ended_at、end_reason、open_handoffs_at_end 七样，母版文件本身也没有版本号
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：母版文件加一个 rules_version，sessions 开始版记下它，accept 时 rl 顺带列出还活着的会话和它们的 rules_version 让 gyb 挑要不要收
6. [slows/missing] 第 12、13 步（想主动通知正在跑的会话）：文档给的答案是不通知、下次加载才生效，但 gyb 万一想立刻让人知道，系统里没有通道：issue 的 assignee 是角色不是会话、六种 kind 里没有「规矩变了」这一类，feedback 账根本没有 assignee，桌面通知只发给 gyb
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-next-steps.md:101
   - 改法：要么在 feedback 那一条明写「采纳只对下次加载生效，不给正在跑的会话补通知」，要么给 issue 加 kind=rule_change 并允许 assignee 填 session_id
7. [slows/missing] 第 14 步（下次加载角色时生效）：「母版改动在下次加载角色时生效」是这个场景的最终答案，可是第九节九条待验证清单里没有它：改一行 common/ 之后，同一个 claude 进程里再加载一次角色 skill 读到的是新文本还是缓存的旧文本，没人测过
   - 依据：plans/2026-08-16-research-loop-next-steps.md:101; plans/2026-08-16-research-loop-build-plan.md:187; plans/2026-08-16-research-loop-build-plan.md:196
   - 改法：待验证清单加第 10 条：改一行母版，不重启 claude 再加载一次角色，看模型读到的是不是新文本，失败备案是改完母版必须重开终端
8. [slows/missing] 第 10 步（gyb 自己 grep 五份 SKILL.md）：母版 common/ 和五份角色 SKILL.md 是引用关系还是抄一份，文档没写；施工步 5 和步 6 是两步分别写的两组文件。抄了的话改母版根本不生效，gyb 只能自己去 grep 五份 SKILL.md 有没有重复条文
   - 依据：plans/2026-08-16-research-loop-next-steps.md:150; plans/2026-08-16-research-loop-build-plan.md:232; plans/2026-08-16-research-loop-build-plan.md:233; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：定死 SKILL.md 只写一句「按 common/GLOBAL-RULES.md 执行」、不许抄条文，测试 13 加一条查 SKILL.md 里有没有母版条文的副本
9. [cosmetic/ambiguous] 第 2 步（feedback 的 target 填什么）：target 的口径是「文件路径或规矩编号」，可母版里公共规矩八条编号 1 到 8、八条设计原则也编号 1 到 8，两套都在同一个文件里，`--target 6` 指的是规矩 6 还是原则 6 分不出来
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:245; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:13
   - 改法：规矩和原则各给一套带前缀的稳定编号（rule-06、principle-06），target 只收文件路径或这两种编号
10. [cosmetic/ambiguous] 第 8、11 步（先改文件还是先 accept）：accept 那一版要求 applied_to 必填「改了母版哪个文件」，但没写是先把母版改完再 accept 还是先 accept 再去改，入账校验也没说要不要检查这个路径存在、检查改没改
   - 依据：plans/2026-08-16-research-loop-build-plan.md:67; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：命令表写死「accept 之前先把母版改完，rl 校验 applied_to 的每个路径存在」
11. [slows/missing] 第 5、13 步（deploy 和 gyb 之间的口头传话）：这条路能走通全靠 deploy 是 gyb 手动加载的终端会话、两头能说话。deploy 要是 subagent（上游同步等着它回来），它提了 feedback 没人告诉 gyb，gyb 裁完也没法把话递回去，整条路断在这儿
   - 依据：plans/2026-08-16-research-loop-next-steps.md:120; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：rl feedback add 在 actor 是 subagent 会话时顺带开一条 kind=request 的 issue 给 gyb，借已有的通知和 status 通道
12. [slows/too_heavy] 整条路（gyb 亲手做九件事）：改一条规矩要 gyb 亲自做九个动作（status、feedback list、改母版、改施工计划、grep 五份 skill、accept、判断要不要收会话、告诉 deploy、commit），系统只帮他记一行账，剩下八件全靠他自己记得住；这跟「想法要快速、多次迭代」的目标不匹配
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-build-plan.md:139; plans/2026-08-16-research-loop-build-plan.md:67
   - 改法：rl feedback accept 收多个 applied_to 并当场打印一张待办（还要改哪几处、活着的会话要不要收、要不要 commit 和跑测试）
13. [slows/principle_violation] 第 11 步的另一条走法（gyb 就坐在 deploy 会话里裁）：违反第 1 条「gyb 是超级用户，任何权限检查对 gyb 不生效」：角色会话里用 --as-gyb 缺 --quote 一律退出码 2（测试 9 钉死了这条），可 rl 分不出打字的是 gyb 本人还是模型，gyb 亲自在 deploy 会话里裁 feedback 会被自己的校验拦下来，得先换个裸终端
   - 依据：plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:211; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-next-steps.md:34
   - 改法：给一个 gyb 本人当场打字的旗子（比如 --i-am-gyb）免 quote，或者把缺 quote 从拒收降成账行打一个「无原话」的标记
14. [cosmetic/missing] 第 15 步（改完母版要不要 commit、要不要跑测试）：第十一节的「每一步施工结束 tests/run_all.py 全绿才 commit」和 commit 前缀 research-loop v2: 只管施工那八步，用起来之后运行期改母版要不要单独 commit、要不要重跑测试 13，没写
   - 依据：plans/2026-08-16-research-loop-build-plan.md:219; plans/2026-08-16-research-loop-build-plan.md:237; plans/2026-08-16-research-loop-build-plan.md:215
   - 改法：feedback 那一节补一句：accept 之后母版改动单独一个 commit，前缀 research-loop rules:，并跑一遍 tests/run_all.py

## idea-request-notes（15 步，gyb 动手 4 次）

1. [slows/contradiction] 第 7 步：两句打架：设计文档写「只有改派到 gyb 名下的时候 bin/rl 才给 gyb 发通知，其余不发」，施工计划写「assignee 变成 gyb 的那一版（含首次开单就写给 gyb）触发桌面通知」。idea 的 request issue 是首次开单就给 gyb、不是改派，按前一句收不到推送；rl status 那一段的措辞又是「改派给 gyb 超过 N 小时没动的 issue」，也可能不列。按原则 8，施工计划只有第一节的裁决优先，L59 是第三节草案，所以严格读应当以设计文档为准、不发通知——那 gyb 一离开终端这条申请就既没人推也不在收件箱里，idea 干等
   - 依据：plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:142
   - 改法：两处统一改成「assignee 是 gyb 的那一版一律通知（含首次开单）」，rl status 那一段同步改成「assignee 是 gyb、状态 open 且超过 issues.gyb_stale_hours 的 issue」
2. [slows/contradiction] 第 5 步：命令表里 `rl grant add / rl grant list` 整行的「谁能调」只写 gyb，idea 调 grant list 应拿退出码 3；但 idea 的 reads 写的是「九本账全部」，公共规矩第 8 条又要求「读账一律经 rl 查询命令」。结果是 idea 查不到自己名下有没有 read:notes，每开一个新会话都只能重新走一遍申请，或者凭猜
   - 依据：plans/2026-08-16-research-loop-build-plan.md:138; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:252; plans/2026-08-16-research-loop-next-steps.md:52
   - 改法：第六节把 grants 拆成两行：`grant add` 谁能调写 gyb，`grant list/show` 谁能调写「谁都行」
3. [slows/contradiction] 第 9 步：设计文档一处写「idea 开一条 issue 给 gyb，gyb 写一条 grant」，另一处允许角色会话里的模型带 --quote 替 gyb 打 --as-gyb。本场景两句合起来的结果是：申请方和批准方是同一个会话里的同一个模型，quote 只是模型自己敲进去的字符串、rl 不校验，而 grant 的全部价值就是「给 reviewer 事后查的凭据」，自提自批之后这份凭据证明不了任何事
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:121; plans/2026-08-16-research-loop-build-plan.md:245
   - 改法：第六节 grants 那一行加一句「grants 不接受 --as-gyb，只收 session_id 为 cli 的裸终端写入」，gyb 批授权必须自己在裸终端打一次
4. [slows/ambiguous] 第 14 步：决定落哪本账的判据是「由 gyb 亲自打 --as-gyb 写的落 decisions.gyb.jsonl，idea 替 gyb 记的落 decisions.idea.jsonl 并带 quote」。但在角色会话里 gyb 从不打命令、只说话，命令全是模型打的，「亲自打 --as-gyb」这件事在角色会话里不存在。模型代打的 --as-gyb 算不算亲自，两种读法都说得通，同一条 gyb 定的决定可能落进两本不同的账
   - 依据：plans/2026-08-16-research-loop-next-steps.md:44; plans/2026-08-16-research-loop-next-steps.md:34; plans/2026-08-16-research-loop-build-plan.md:57
   - 改法：第三节写死一条：decisions.gyb.jsonl 只收 session_id 为 cli 的行，角色会话里替 gyb 记的一律落角色自己那本并带 quote
5. [slows/missing] 第 6 步之后到第 8 步之间：idea 开完 --to gyb 的 request issue 之后，等回话期间会话该干什么没写。idea 手上没有派活单，转移表里的 stuck 只有 holder 能写、对 idea 不适用；gyb 要是走开了，idea 会话要么空转要么销号，而销号之后没有任何机制重新拉起 idea——原则 3 只管有 owner 的单子，idea 是最上游、只由 gyb 在终端手动 / 加载
   - 依据：plans/2026-08-16-research-loop-build-plan.md:84; plans/2026-08-16-research-loop-next-steps.md:117; plans/2026-08-16-research-loop-next-steps.md:154
   - 改法：idea 的 SKILL.md 纪律栏写死：开完 --to gyb 的 issue 立即把待办交回 gyb 并结束本轮，gyb 下次开 idea 会话时用 `rl issue list --to gyb` 捡起来接着走
6. [slows/too_heavy] 第 6 步到第 11 步整段：gyb 就坐在这个会话里说了句「你去读吧」，为了读一份 md 却要走 issue open、通知、grant add、issue reply、issue close 五个动作四行账。permission 第一版只有 read:notes 一种、grantee 是角色不是会话，所以批一次就永久覆盖整个 notes/，这套手续一辈子只有第一次有信息量，和「想法要快速、多次迭代」这条总目标对不上
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-build-plan.md:65
   - 改法：`rl init` 时问一次 gyb 要不要当场给 idea 发 read:notes，发了以后就不用走申请，没发才走 issue 那条路
7. [slows/missing] 第 12 步和第 14 步：file 类来源只有 path 一个字段。一份几十页的文献调查整份当来源，reviewer 拿决定账当唯一审查基准的时候，定位不到是报告里哪一句支撑这条决定，核不动「代码和决定是不是一回事」上游的那一半
   - 依据：plans/2026-08-16-research-loop-build-plan.md:57; plans/2026-08-16-research-loop-next-steps.md:46; plans/2026-08-16-research-loop-next-steps.md:88
   - 改法：file 类来源加一个可选的 anchor 字段（小节标题或行号区间），命令写成 `--source file:notes/x.md#<小节>`
8. [slows/missing] 第 12 步：读权不上钩子、靠纪律加 reviewer 事后查，但文档没写 reviewer 拿什么查「idea 有没有在没 grant 的时候就读了 notes/」。系统里没有读日志，doctor 的八项扫描里也没有这一类，这条纪律实际上无从核对
   - 依据：plans/2026-08-16-research-loop-next-steps.md:28; plans/2026-08-16-research-loop-next-steps.md:136; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：`rl doctor` 加一项扫描「decisions 里 source 指向 notes/ 但 grants 里查不到该 actor 的 read:notes」，把这条纪律接回入账校验那一层
9. [slows/missing] 第 2 步：sessions 账要求 model 记真实模型标识、明说不记 inherit，角色 json 里手动加载又一律写 inherit，而钩子从哪里拿到当前会话的真实模型名文档没写，待验证清单九条里也没有这一条（只验了会话 id 变量）。钩子落地时这个字段只能填 inherit 或者靠猜
   - 依据：plans/2026-08-16-research-loop-next-steps.md:103; plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:99; plans/2026-08-16-research-loop-build-plan.md:189
   - 改法：待验证清单加一条「Bash 环境里有没有当前模型名的变量」，拿不到就把第三节 sessions 的 model 改成允许写 inherit 并注明原因
10. [cosmetic/missing] 第 10 步和第 11 步：issues 三个状态的写权只有一句「按第五节 ledger_writes」，谁写 reply、谁写 close 没规定；idea 的 ledger_writes 含 issues 的 open/reply/reassign/close 四个，所以 idea 自己开、自己答、自己关全过校验，和派活单那张写得很死的转移表不对称
   - 依据：plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:101; plans/2026-08-16-research-loop-build-plan.md:79
   - 改法：第六节 issue 那一行加前提栏：reply 只有 assignee 或 gyb 能写，close 只有开单的 actor 或 gyb 能写

## periodic-reclaim（27 步，gyb 动手 11 次）

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
11. [slows/missing] 第 3、24 步：一条一周没动的快车道 worktree 没有出路。reclaim 只管会话和单子，scratch 账只有 add 和 list，设计文档写死出快车道只有合回主分支补工单这一条路，放弃一条快车道没有命令，rl status 里那一行永远挂着，越攒越多。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-next-steps.md:124; plans/2026-08-16-research-loop-build-plan.md:141
   - 改法：加 rl scratch retire --tag QL --reason，rl status 只列没 retire 的快车道，reclaim 把超期的快车道也列进来。
12. [slows/principle_violation] 第 23 步：违反原则 1。runs 账的行格式写死「actor 必须是 run」，而原则 1 说任何权限检查对 gyb 一律不生效。gyb 要给回收下来的孤儿发射版补一条 exit=killed 的收尾版，按前一句写不进去，按原则 1 写进去就破了 schema，入账脚本按哪一条实现没有定论。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:137; plans/2026-08-16-research-loop-next-steps.md:15; plans/2026-08-16-research-loop-build-plan.md:121
   - 改法：runs 账的 actor 改成允许 run 或 gyb，字段表那一句后面补「gyb 例外，同原则 1」。
13. [slows/missing] 第 26 步：doctor 的八个扫描项里没有 reclaim 会造出来的两种脏账：单子已经回到 todo 而关联 issue 还是 open，以及 runs 有发射版长期没有收尾版。这两种正是回收留下的残渣，扫不出来就没人修。文档也没写 reclaim 之后要不要跑 doctor。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-next-steps.md:20
   - 改法：doctor 加这两项扫描，reclaim --apply 结束时自动跑一遍 doctor 并打印结果。
14. [slows/missing] 第 13 步：钩子调 rl session start 时那一行的 actor 填什么没写。公共骨架规定 actor 取值是五个角色或 gyb，钩子两样都不是。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:55; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:71
   - 改法：明写钩子代角色写账，sessions 开始版的 actor 填 --role 那个角色，session_id 填新会话。
15. [slows/missing] 第 1 步：定时提醒的失败备案是「入口 skill 加载时打印一行距上次 reclaim 几天」，可入口 skill 只许 gyb 手动调用，gyb 不主动加载就永远看不到这一行。备案落空的时候没有第二条路。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:195; plans/2026-08-16-research-loop-next-steps.md:163; plans/2026-08-16-research-loop-next-steps.md:154
   - 改法：备案改成 rl status 的第一行打印距上次 reclaim 的天数，rl status 谁都能调、gyb 天天用。
16. [cosmetic/missing] 第 2、4 步：入口 skill 的领路清单里四条路线图都是做实验的路线，没有这条定期收拾的路线，gyb 收到提醒之后要凭记忆敲 status 和 reclaim 的顺序。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:154; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：领路加一条「收到 7 天提醒 → rl status → rl reclaim 看列表 → --apply → 按 owner 逐个拉起 → rl doctor」。
17. [cosmetic/missing] 第 25 步：提醒里的第三件事「迭代框架本身」没写具体做什么、产出落到哪本账、改完的母版要不要 commit。feedback 账那条线写清楚了，这一条只有名字。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:126; plans/2026-08-16-research-loop-build-plan.md:183; plans/2026-08-16-research-loop-build-plan.md:139
   - 改法：把这一条改写成「跑 rl feedback list，把 accepted 的改动落到 common/ 母版并单独 commit」，不留抽象说法。

## hook-missed-session-end（23 步，gyb 动手 11 次）

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

## smoke-fails（44 步，gyb 动手 4 次）

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
5. [slows/missing] 步 7（deploy 开发射单）：handoffs 的行格式没有「这张发射单挂在哪张工单上」的字段，只有 work_order 有 decision_refs，launch_order 既不引决定也不引父单。可是设计文档要求 analysis 顺着 handoffs 从决定走到发射单再走到 run_id，doctor 还要扫「快车道工单已 accepted 但没有关联发射单」，两处都需要这条父子边，账上没有地方记。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:81; plans/2026-08-16-research-loop-build-plan.md:144; plans/2026-08-16-research-loop-next-steps.md:80; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：handoffs 加一个 parent 字段，rl handoff open 在角色会话里默认填当前会话正持有的那张单，withdraw --cascade 也照它走。
6. [slows/missing] 步 33（第二次 smoke 通过后发射）：正常路的 run_id 谁定、怎么命名，文档没写。只有快车道写了 ql_tag 兼作宿主发射器要的 run_id、track 一律填 quick_lane。宿主 run.py launch 的 --run-id 和 --track 都是必填，new1 的规矩还要求 run_id 在产物目录名、tmux session、台账 name、commit message 四处一致，run 在这一步只能自己编一个，且 --track 要和 TIMELINE.md 的方向对得上，谁给这个值也没写。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:64; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:161; plans/2026-08-16-research-loop-build-plan.md:63
   - 改法：rl handoff open --type launch_order 时自动分配 run_id 写进 launch 子对象（形如 ho-0013-01），track 由 deploy 开单时必填。
7. [slows/missing] 步 34（rl run add 落发射版）：runs 发射版必填 config 字典，里面要有 model、params、dataset、split，是给 analysis 分组用的；但发射单的 launch 子对象只有 command、args、workdir、estimated_seconds、step_table、actual_seconds，没有 config。run 要么去解析命令行参数，要么去读 experiments/ 的代码猜这四个值，而这四个值本来是 deploy 定的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:63; plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：把 config 挪到发射单上由 deploy 开单时填，rl run add 默认从发射单抄，run 只补机器和卡。
8. [slows/ambiguous] 步 19（run 开 issue）：smoke 失败该填哪个 kind 没定。六种 kind 里 cannot（干不了）和 not_mine（不归我干）两种读法都说得通：ImportError 是代码问题、明显不归 run 干，但 run 的确也是干不了。施工计划第七节只写「一律 rl issue open --to deploy --kind ...」，省略号没填。kind 影响 doctor 和 status 的归类，也影响 gyb 读账时的判断。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:45; plans/2026-08-16-research-loop-build-plan.md:166; plans/2026-08-16-research-loop-next-steps.md:72
   - 改法：在第七节把四种失败各钉一个 kind：smoke 失败、发射失败、跑挂都是 cannot，结果反常是 anomaly。
9. [slows/missing] 步 18（run 准备 --log-tail）：开 issue 要附日志末 40 行和 traceback，命令给的是 --log-tail FILE，要一个文件路径。可是 smoke 阶段按 gpu-run 的规矩产物不留档，ImportError 是前台跑出来的、traceback 只在标准输出里，压根没有日志文件。run 得自己想办法把 stdout 落成文件，落到哪、叫什么名，文档没写（run 的写权只有仓库外的 artifact_root）。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:72; plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:160; .claude/skills/gpu-run/SKILL.md:49
   - 改法：run 的 SKILL.md 规定 smoke 一律重定向到 artifact_root/smoke/<发射单号>.log，或者给 rl issue open 加 --log-text 从标准输入收。
10. [slows/too_heavy] 步 19 到步 30（整个修复回路）：一个 import 报错要走完：落一条 issue、把单子标 stuck、run 会话销号、deploy 读 issue、改代码、回 issue、把单子拉回 todo、重起一个 run subagent、重读慢变量档案、重探空卡、重挑卡、重跑 smoke。至少八次账写入加两次会话生死。文档还把两条捷径都堵死了：run 不许自行重试，下游不许小修，快车道只能由 gyb 事先点名进、单子已经在正常路上时没有中途改走快车道的路。这和「想法要快速、多次迭代」的目标拧着。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:7; plans/2026-08-16-research-loop-next-steps.md:185; plans/2026-08-16-research-loop-next-steps.md:180; plans/2026-08-16-research-loop-next-steps.md:64
   - 改法：给发射单加一条 smoke 失败专用短路：run 返回 traceback，deploy 在同一会话里就地修完打 rl handoff release 再起 run，issue 照开但不必等回复，并明写这不算 run 自行重试。
11. [slows/principle_violation] 步 43（gyb 跑 rl status 收尾看一眼）：违反原则 6 的「进出对称」那一半。run 开给 deploy 的 issue 不触发通知（只有改派到 gyb 名下才通知），rl status 的七段里只有「改派给 gyb 超过阈值的 issue」，没有「open 的 issue 按 assignee 分组」这一段。这条 iss-0031 从 open 到 answered 之后没人 close，账上也没有任何出口能把它列出来；单子本身能在「没到终态的单子」里露头，issue 露不了头。deploy 会话要是先走了，这条 issue 就悬着，只能靠 reclaim 捞单子，issue 永远 open。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:20; plans/2026-08-16-research-loop-next-steps.md:97; plans/2026-08-16-research-loop-build-plan.md:142; plans/2026-08-16-research-loop-build-plan.md:143
   - 改法：rl status 加一段「open 与 answered 的 issue 按 assignee 分组」，reclaim 一并列出超过阈值没动的 issue。
12. [cosmetic/missing] 步 26 与步 43（iss-0031 的收场）：issue 有 open、answered、closed 三个状态，命令表也有 rl issue close，但谁来 close、什么时候 close 全文没写。这次 deploy 回复之后 issue 停在 answered 就再没人碰过，doctor 只扫「没人引用的 issue」，扫不出这种长期 answered 不 closed 的。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:59; plans/2026-08-16-research-loop-build-plan.md:132; plans/2026-08-16-research-loop-build-plan.md:144
   - 改法：rl handoff accept 时自动 close 这张单关联的所有 answered issue，剩下的由开单角色手动 close。
13. [slows/missing] 步 26 到 27（deploy 修完代码）：修 import 有时候要换入口（比如从 python -m pkg.train 换成 python scripts/train.py）或者加环境变量，发射单上写死的 launch.command 就得跟着改。九本账全是事件流、改等于追加一版，可是转移表里没有「改单内容」这一行，命令表里也没有对应的子命令，deploy 只能收回旧单重开一张新单，把 stuck 的 issue 关联关系一起丢掉。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:61; plans/2026-08-16-research-loop-build-plan.md:134; plans/2026-08-16-research-loop-next-steps.md:18
   - 改法：加 rl handoff amend ID --command ... --workdir ...，只许在 todo 或 stuck 上追加一版，并在转移表里补一行原地追加。
14. [cosmetic/contradiction] 步 10（run 上线跑过版检查）：设计文档说角色上线第一个动作跑过版检查，这是对所有角色说的；施工计划第五节给 run 的 reads 只有 handoffs 里的 launch_order、experiments/、ops/gpu_state.md、runs，不含 decisions。rl decision stale 要读 decisions 账，run 跑它就越出自己的 reads 栏，不跑又违反上线第一个动作那句。发射单本来也不引决定，run 跑了也查不出跟自己有关的东西。
   - 依据：plans/2026-08-16-research-loop-next-steps.md:111; plans/2026-08-16-research-loop-build-plan.md:105; plans/2026-08-16-research-loop-build-plan.md:131
   - 改法：明写过版检查只对 idea、deploy、analysis、reviewer 强制，run 免跑；或者把 decisions 的只读加进 run 的 reads。
15. [slows/guessed] 步 9 与步 22（run subagent 的钩子与销号）：待验证清单第 5 条（SubagentStop 在 subagent 结束时触不触发、会话 id 是不是同一个）和第 8 条（subagent 里加载角色 skill 钩子装不装得上）都还没测，两条各有备案，选主案还是备案会改掉本场景一半的走法：备案里 subagent 路线改成 workflow 的 agentType，或者「接单只靠纪律加 reviewer 事后查」，那样 run 的写权拦不住、销号全靠 reclaim、sessions 账没有结束版。我这次按主案走，属于猜。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:193; plans/2026-08-16-research-loop-build-plan.md:196; plans/2026-08-16-research-loop-next-steps.md:164; plans/2026-08-16-research-loop-next-steps.md:167
   - 改法：施工步 0 出结论之后，按选中的那一案把 run 的 SKILL.md 和第七节改死，删掉另一案，不留两条路。
16. [cosmetic/missing] 步 2 与步 9（钩子登记会话）：sessions 账要求 model 记真实模型标识、手动加载也记真实的、不记 inherit，rl session start --role R --model M 由钩子调；但钩子从哪拿到这个真实模型名，文档没写，待验证清单第 1 条只查了会话 id 有没有现成变量，没查模型标识。
   - 依据：plans/2026-08-16-research-loop-build-plan.md:71; plans/2026-08-16-research-loop-build-plan.md:126; plans/2026-08-16-research-loop-build-plan.md:189; plans/2026-08-16-research-loop-next-steps.md:103
   - 改法：待验证清单加一条「钩子输入里有没有模型标识」，拿不到就退成记 unknown 并把启动命令一起写进账行。

## doctor-findings-fix（24 步，gyb 动手 15 次）

1. [slows/missing] 第 2 步（doctor 输出修法）：doctor 那一行承诺「每类结果附一条修法（都是追加一版的 rl 命令）」，但八个扫描项没有任何一项写出具体的修法命令是什么；本场景三类问题的修法全靠我按转移表和命令表倒推，三类里有两类倒推出来的路子不止一条。
   - 依据：2026-08-16-research-loop-build-plan.md:144
   - 改法：在第六节 doctor 那一行下面补一张八行表，每个扫描项写死修法命令模板、谁能打、修完之后单子归谁推。
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
6. [slows/too_heavy] 第 9 到 19 步（修第二类）：第二类的真实病因只是一份报告文件没了，修它却要走「打回 → 加载 deploy 会话 → decision stale → start → 重写报告 → done → accept」七步，中间还要新登记一个会话、还要把单子在四个状态之间转一圈。对着「想法要快速、多次迭代」这条目标偏重。
   - 依据：2026-08-16-research-loop-next-steps.md:7; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:91; 2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:88
   - 改法：给 done_pending_review 的单子加一条 `rl handoff amend ID --report-detail P`：追加一版只换路径、不改状态、校验路径存在。
7. [slows/missing] 第 8、18 步（holder 指向死会话）：转移表和测试 2 列的 holder 清空时机是 start 写、stuck→todo / rejected / release / reclaim 清，唯独 in_progress→done_pending_review 不清；销号钩子又只检查 holder 名下还在 in_progress 的单子。于是等验收的单子上 holder 长期写着一个已经销号的会话，rl status 那一栏显示有人在干，实际没有。
   - 依据：2026-08-16-research-loop-build-plan.md:87; 2026-08-16-research-loop-build-plan.md:204; 2026-08-16-research-loop-next-steps.md:126; 2026-08-16-research-loop-next-steps.md:124
   - 改法：在转移表 in_progress→done_pending_review 那一行补一句 holder 清空，或者 rl status 显示 holder 时标出这个会话还活着没有。
8. [slows/ambiguous] 第 19 步（谁来 accept）：gyb 本人坐在 deploy 会话里想验收，按文档要打 `--as-gyb` 并且必须带 `--quote gyb 原话`，缺 quote 退出码 2；可是 rl 只看会话状态文件，分不出这条命令是 gyb 本人敲的还是模型敲的，于是 gyb 本人也得引用自己刚说的一句话。我只能让 gyb 退回裸终端打，多切一次终端。
   - 依据：2026-08-16-research-loop-build-plan.md:121; 2026-08-16-research-loop-next-steps.md:34
   - 改法：`--as-gyb` 缺 quote 时改成交互式追问一次再放行，或者加一个 `--quote-self` 表示 gyb 本人当场敲的。
9. [slows/principle_violation] 第 1、24 步（doctor 的结果没有落点）：违反原则 6「所有等 gyb 处理的事由 rl status 一处列出」：doctor 扫出来的问题不在 rl status 的七段里，也不在 7 天定时提醒的三件事（reclaim、看 feedback、迭代框架）里，没人叫 gyb 跑 doctor，修不了的那条（第三类）也没有任何地方替他记着。
   - 依据：2026-08-16-research-loop-next-steps.md:20; 2026-08-16-research-loop-build-plan.md:142; 2026-08-16-research-loop-build-plan.md:183; 2026-08-16-research-loop-build-plan.md:144
   - 改法：rl status 加第八段「上次 doctor 扫出还没修的问题」，并把跑 doctor 并进 7 天提醒那三件事里。
10. [slows/missing] 第 7 步（第一类修到哪算完）：文档没写 doctor 修到哪算完。补上 stuck 那一版之后账面一致了，但那张发射单实际还卡着、那条 issue 还等 deploy 回、真正的实验失败没人处理；doctor 的输出也不区分「账面对不上」和「活还没干完」。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:85
   - 改法：doctor 每条修法后面固定加一句「修完之后这张单子归谁推」，取值和转移表第五栏一致。
11. [slows/guessed] 第 21 步（第三类到底指什么）：「runs 行没有对应发射单」有两种读法：handoff_id 为空，还是 handoff_id 指向的单子不存在或者 work_type 不是 launch_order。命令表里 `rl run add --handoff ID` 看着是必给的，第一种读法在文档里产生不出来，我只能猜是第二种，而文档也没写这条脏数据是怎么进来的。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:137; 2026-08-16-research-loop-build-plan.md:63
   - 改法：把这一项改写成「runs.handoff_id 为空、悬空、或者指向的单子 work_type 不是 launch_order」，并在旁边注一句它怎么产生。
12. [cosmetic/missing] 第 5、9 步（修账那两版留不留痕）：gyb 在裸终端补的 stuck 和 reject 这两版，账上只留 status 和 reason，没有任何字段标明这是 doctor 修账修出来的。reviewer 事后翻 handoffs，分不出这张单子是真卡住过、还是只是把断掉的引用补回去。
   - 依据：2026-08-16-research-loop-build-plan.md:61; 2026-08-16-research-loop-build-plan.md:55; 2026-08-16-research-loop-next-steps.md:88
   - 改法：公共骨架加一个可选的 `fix_for` 字段，doctor 给的修法命令一律带上扫描项名字。
13. [cosmetic/missing] 第 1 步（谁跑 doctor、跑完能不能自己修）：doctor 写的是「谁都行」，但角色会话跑出问题之后能不能自己修没写。deploy 看到自己名下那张 done_pending_review 的报告路径没了，它是 to_role 不是 owner，按转移表打回只有 owner 能写，它只能开 issue，文档没说这一步该开给谁、kind 填哪个。
   - 依据：2026-08-16-research-loop-build-plan.md:144; 2026-08-16-research-loop-build-plan.md:89; 2026-08-16-research-loop-build-plan.md:45
   - 改法：在 doctor 那一行写一句「角色跑 doctor 只看不修，修法一律 `rl issue open --to <owner> --kind cannot` 报给 owner 或 gyb」。
