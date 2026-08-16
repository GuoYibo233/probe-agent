# research-loop 第一轮场景模拟原始结果（2026-08-16 夜，11 个 opus agent：5 模拟 + 5 核实 + 1 critic）

来源：workflow wf_4d17df91-643。五个场景：param-tweak（改一个参数）、new-idea（新想法要实施）、result-wrong-review（结果不对审代码）、plot-new-plan（新计划画图）、next-plan-after-results（出结果定下一步）。每条摩擦带模拟者定级 sev_sim、核实者定级 sev_verified 和核实理由。

```

===== SCENARIO param-tweak steps=37 gyb_touch=7 keys=['scenario', 'total_steps', 'gyb_touchpoints', 'frictions', 'extra', 'trace_errors']

[F0] where=第 4 步（deploy 判定走不走快车道） kind=contradiction sev_sim=blocks sev_verified=slows real=True
  what: 设计文档第 43 行说快车道触发条件是「决定不动、只微调代码」，第 29 行又说「gyb 会参与到影响实验结果的工程细节里，这些细节同样写进决定账」。学习率是影响实验结果的工程细节，很可能账里本来就有一条决定写着 1e-4；改成 3e-4 到底算不算「决定动了」，两句话给出相反答案，整条路第一个岔口就分叉。
  refs: plans/2026-08-16-research-loop-next-steps.md:43, plans/2026-08-16-research-loop-next-steps.md:29
  suggestion: 在第 43 行给快车道写一条机器可判的判据：不新增也不修改任何 decisions 行就算决定不动，改动账里已有决定的正文一律走正常路。
  verify_reason: 两份文档都没有可判定的快车道判据。next-steps.md:43 只给了自然语言触发条件「决定不动、只微调代码」，next-steps.md:29 说 gyb 参与的工程细节同样写进决定账，两句话谁管学习率这种参数没写；build-plan.md 全文没有 quick_lane 的进入判据（第六节命令表 build-plan.md:119 只有 rl scratch add）。不过判成 slows 不是 blocks：本场景是 gyb 口头发起，且 next-steps.md:43 有「合回那一刻补一张正常工单引上决定」兜底，判错也会在合回时被补回来。

[F1] where=第 5 到第 10 步（deploy 在 git worktree 里改代码、写产物） kind=blocked sev_sim=blocks sev_verified=slows real=True
  what: 写权钩子按路径硬拦，deploy 只能写 experiments/；快车道的代码和产物在一棵独立 git worktree 里，worktree 根不在研究仓库的 experiments/ 下。角色 json 的 writes 栏只写了「experiments/（快车道在 worktree）」这一句括号，没写钩子怎么把 worktree 路径换算回 experiments/。按字面路径匹配，deploy 在 worktree 里第一次 Write 就被 deny，快车道一步都走不了。
  refs: plans/2026-08-16-research-loop-next-steps.md:101, plans/2026-08-16-research-loop-next-steps.md:43, plans/2026-08-16-research-loop-build-plan.md:90
  suggestion: 把快车道 worktree 根写进 research-loop.json，钩子判路径时先剥掉 worktree 根再按仓库内相对路径匹配。
  verify_reason: build-plan.md:90 的 writes 栏括号「快车道在 worktree」只声明了 worktree 属于 deploy 的写权，钩子按什么规则把 worktree 路径换算回 experiments/ 两份文档都没写（next-steps.md:101 只说「按路径判」，build-plan.md:185 的测试 8 三个用例全是仓库内路径）。判 slows 不判 blocks：写权在原则上已经给了，缺的是实现规则，施工时不会两难。

[F2] where=第 8 步（快车道跑 GPU 走 run.py launch） kind=contradiction sev_sim=blocks sev_verified=slows real=True
  what: 设计文档第 43 行说快车道产物留在 worktree 目录里、GPU 照旧走 gpu-run；gpu-run 第 80 到 84 行的 launch 一条命令会写 ops/jobs.json、ops/runs.jsonl 和产物目录 RUNMETA.json。设计文档第 101 行说产物根只有 run 的任务能写、ops/ 这类文件不给白名单、撞到就拦下提醒搬进 experiments/。deploy 走完 gpu-run 必然撞三处禁区。
  refs: plans/2026-08-16-research-loop-next-steps.md:43, plans/2026-08-16-research-loop-next-steps.md:101, plans/2026-08-16-research-loop-build-plan.md:91, .claude/skills/gpu-run/SKILL.md:80
  suggestion: 给快车道写一条明文例外：deploy 在快车道里可写 artifact_root 下的 quick_lane/ 子目录和 new1 的三个台账文件，其余照旧拦。
  verify_reason: 确实没有覆盖。next-steps.md:43 要求快车道 GPU 照旧走 gpu-run，gpu-run/SKILL.md:65-84 的 run.py launch 必然写 ops/jobs.json、ops/runs.jsonl 和 RUNMETA.json，而 next-steps.md:101 明写不给 run.py、MAP.md、ops/ 这类文件开白名单、撞到就拦下提醒搬进 experiments/，next-steps.md:163 还专门把「按角色开这些白名单」的提议顶回过。两份文档没有任何一处给快车道开例外。降为 slows 的理由：钩子管不管 Bash 写入未定（见第 12 条），撞不撞得上取决于未写的实现。

[F3] where=第 4 步（deploy 宣布进快车道）与第 10 步（写 scratch） kind=missing sev_sim=slows sev_verified=cosmetic real=True
  what: rl 命令表里和快车道有关的只有一条 rl scratch add，没有进快车道、退快车道的登记命令，也没有地方记这次快车道基于哪个基线 run_id、在哪棵 worktree、什么时候合回。第 4 步完全靠模型自觉，doctor 也扫不出「有人还挂在快车道」。
  refs: plans/2026-08-16-research-loop-build-plan.md:119, plans/2026-08-16-research-loop-build-plan.md:101, plans/2026-08-16-research-loop-next-steps.md:43
  suggestion: 加 rl quicklane start/finish 两条命令，start 记 worktree 与基线 run_id，finish 列出本次所有 scratch 行并提醒补工单。
  verify_reason: 部分成立。worktree 已经有地方记：build-plan.md:64 建议 scratch 行带 worktree，build-plan.md:119 的 rl scratch add 有 --worktree。但进出快车道的登记、基线 run_id、合回时点两份文档都没有，build-plan.md:122 的 doctor 扫描项里也没有快车道相关的一条。判 cosmetic：next-steps.md:141-142 两次以「小改动走快车道」为由裁掉附加手续，给快车道加两条登记命令和文档的取向相反。

[F4] where=第 22 步（正式重跑的发射单由谁在什么时候开） kind=missing sev_sim=slows sev_verified=slows real=True
  what: 第 43 行只说「合回之后要正式数字按正常路再跑一遍」，没说这次重跑挂在哪张单子上：是 deploy 在合回工单的 in_progress 期间顺手开一张 launch_order，还是等工单 accepted 之后另起一轮。转移表里 work_order 进 done_pending_review 的前提只有两份报告路径，不含「已经跑出正式数字」，所以按文档字面走完全可以合回了不跑。
  refs: plans/2026-08-16-research-loop-next-steps.md:43, plans/2026-08-16-research-loop-build-plan.md:70, plans/2026-08-16-research-loop-build-plan.md:74
  suggestion: 把「本单关联的 launch_order 已 accepted」写进合回工单进 done_pending_review 的前提那一格。
  verify_reason: 「谁开」这半截是覆盖了的：next-steps.md:41 说 deploy 给 run 开发射单，next-steps.md:43 说合回之后按正常路再跑一遍，合起来就是 deploy 开。没覆盖的是前提那一格——build-plan.md:74 里 work_order 进 done_pending_review 只要两份报告路径存在，不含「关联的 launch_order 已跑完」，所以按字面确实可以合回了不跑正式数字，且 build-plan.md:122 的 doctor 扫描项里也没有这一条。

[F5] where=第 34 步（analysis 提交分析结果等验收） kind=missing sev_sim=slows sev_verified=slows real=True
  what: 转移表 in_progress 到 done_pending_review 那一行只写了 work_order 要两份报告路径、launch_order 要 actual_seconds 和 runs 行，analysis_order 那一格空着，没写前提，也没写 analysis 拿什么当验收产物。按「表外的转移一律拒收」的规矩，这一格该填什么无法判断。
  refs: plans/2026-08-16-research-loop-build-plan.md:74, plans/2026-08-16-research-loop-build-plan.md:81, plans/2026-08-16-research-loop-next-steps.md:93
  suggestion: 补一句前提：analysis_order 进 done_pending_review 要填 analysis/ 下的 notebook 或统计脚本路径，且路径存在。
  verify_reason: build-plan.md:74 那一行的前提只写了 work_order 和 launch_order 两种，analysis_order 没写；next-steps.md:93 讲验收产物时通篇只讲部署报告，没有给分析单定验收产物；build-plan.md:52 的 report_paths 也只挂在 work_order 上。配合 build-plan.md:81「表外的转移一律拒收」，这一格是空还是「无前提」两读都成立。

[F6] where=第 5 到 10 步（钩子拦不拦 Bash 里的写入） kind=missing sev_sim=slows sev_verified=slows real=True
  what: 设计文档第 101 行的写权硬拦讲的是路径和 Write/Edit，测试清单第 8 条也全是 Write 用例。快车道整段动作是 Bash：git worktree、python 训练脚本、run.py launch，写文件的都不是 Write 工具。钩子到底管不管 Bash 写入没写，管则快车道寸步难行，不管则写权硬拦在快车道里等于不存在。
  refs: plans/2026-08-16-research-loop-next-steps.md:101, plans/2026-08-16-research-loop-build-plan.md:185
  suggestion: 在第 101 行补一句覆盖面声明：钩子只挂 Write/Edit，Bash 写入靠纪律加 rl doctor 事后扫。
  verify_reason: 两份文档都没写钩子的工具覆盖面。next-steps.md:101 只说「写权硬拦，按路径判」，唯一点名工具的地方是 loop/ 那句「谁都不许直接 Write/Edit」；next-steps.md:105 讲的是钩子怎么装上，不讲挂哪个工具；build-plan.md:185 的测试 8 三个用例全是 Write，build-plan.md:144 说 run 会话装两条写权钩子也没写匹配哪些工具。这条同时决定第 2 条到底是不是硬冲突。

[EXTRA0] sev=slows what: run 角色的 subagent 模型两份文档互相打架，且冲突裁决规则把它判成了未定：next-steps.md:47 写 sonnet，build-plan.md:11 写 opus（还标着「gyb 裁」），build-plan.md:3 规定冲突以设计文档为准。角色 json 的 as_subagent 字段（build-plan.md:85、91）到底填哪个，施工时无从下笔。
  refs: plans/2026-08-16-research-loop-next-steps.md:47, plans/2026-08-16-research-loop-build-plan.md:11, plans/2026-08-16-research-loop-build-plan.md:3, plans/2026-08-16-research-loop-build-plan.md:91
  suggestion: 在 build-plan 第一节裁决里点名说明这条是对设计文档第 47 行的修订，或者把 run 改回 sonnet；两份文档同时改，别留两个值。

[EXTRA1] sev=slows what: runs 和 sessions 两本账要事后回填，但没有版本机制。build-plan.md:46 只给五本账加了 version，runs（build-plan.md:54）和 sessions（build-plan.md:62）都没有；而 rl run finish（build-plan.md:115）要补 exit_status 和 metrics，rl session end（build-plan.md:104）要补 ended_at、end_reason、open_handoffs_at_end。next-steps.md:67 规定九本账只增不改，两边对不上。
  refs: plans/2026-08-16-research-loop-next-steps.md:67, plans/2026-08-16-research-loop-build-plan.md:46, plans/2026-08-16-research-loop-build-plan.md:54, plans/2026-08-16-research-loop-build-plan.md:62
  suggestion: 给 runs 和 sessions 也加 version，finish 和 end 一律追加新版本，默认查询取最新版；或者明写这两本按主键就地改并从「只增不改」里除名。

[EXTRA2] sev=slows what: 测试 10 和 rl run add 的时序对不上：build-plan.md:139 要求发射成功后立刻 rl run add 落第一行，build-plan.md:115 的 add 参数里 --metric 是可选的，build-plan.md:187 的测试却要求 runs 行缺 metrics 就拒收。发射那一刻不可能有指标。
  refs: plans/2026-08-16-research-loop-build-plan.md:139, plans/2026-08-16-research-loop-build-plan.md:115, plans/2026-08-16-research-loop-build-plan.md:187
  suggestion: 把测试 10 改成只对 finish 那一版校验 metrics，add 那一版只校验 run_id、handoff_id、commit。

[EXTRA3] sev=slows what: new1 的发射器和写权表在正常路上就撞车，不只是快车道的问题。build-plan.md:141 把「new1 的 ops/runs.jsonl 照旧由 run.py launch 写」当成既定事实，gpu-run/SKILL.md:80-84 还同时写 ops/jobs.json 和产物目录 RUNMETA.json；而 next-steps.md:101 明写不给 ops/ 这类文件开白名单、撞到就拦，next-steps.md:163 专门把开白名单的提议顶回过，build-plan.md:91 给 run 的 writes 也只有 artifact_root 和 runs 账。run 角色每次发射都要撞这一处。
  refs: plans/2026-08-16-research-loop-build-plan.md:141, plans/2026-08-16-research-loop-build-plan.md:91, plans/2026-08-16-research-loop-next-steps.md:101, plans/2026-08-16-research-loop-next-steps.md:163, .claude/skills/gpu-run/SKILL.md:80
  suggestion: 在 research-loop.json 里把宿主仓库的发射器台账路径单列一栏（launcher.ledger_paths），钩子对这几条路径按角色放行 run，并写明这不是给 ops/ 开通用白名单。

[EXTRA4] sev=slows what: 快车道走 run.py launch 时 --run-id 和 --track 从哪来没写。gpu-run/SKILL.md:86 说这两个参数必填、--track 要和 TIMELINE.md 的方向对得上；插件里 run_id 是 runs 账主键（build-plan.md:54），而 next-steps.md:43 说快车道不进 runs 账、不开发射单，所以既没有发射单给它派 run_id，也没有决定给它对 track。
  refs: plans/2026-08-16-research-loop-next-steps.md:43, plans/2026-08-16-research-loop-build-plan.md:54, .claude/skills/gpu-run/SKILL.md:86
  suggestion: 给快车道钉一个 run_id 命名前缀（例如 ql-<日期>-<序号>）并写进 scratch 行，track 固定填 quick_lane，明写这类 run_id 不占 runs 账命名空间。

[EXTRA5] sev=slows what: 「合回那一刻补一张正常工单」在转移表里没有补记入口。next-steps.md:43 要求合回时补单，但 build-plan.md:70 规定新建只能落 todo，要走到 accepted 必须经 in_progress 和 done_pending_review，而 build-plan.md:74 硬要 work_order 有两份部署报告路径且文件存在——代码在快车道里已经写完了，这张单子是事后补记，文档没给它一条不重做的路。
  refs: plans/2026-08-16-research-loop-next-steps.md:43, plans/2026-08-16-research-loop-build-plan.md:70, plans/2026-08-16-research-loop-build-plan.md:74
  suggestion: 在转移表加一行「（新建）→ done_pending_review」，限 work_type=work_order 且带 quick_lane 标记，前提同样是两份报告路径存在，验收照旧由 from_role 做。

[EXTRA6] sev=slows what: 场景里要改的训练脚本在 new1 目前大概率还在 experiments/ 外。build-plan.md:10 裁定 new1 老代码由 gyb 手动按需搬、入口 skill 不做全量搬迁，next-steps.md:101 规定 deploy 撞到这类文件钩子拦下并提醒 gyb 搬。于是快车道第一次 Edit 之前先要 gyb 搬文件，而搬完连带要改的仓库根 run.py 注册表本身又在 experiments/ 外、还是没人有权写。
  refs: plans/2026-08-16-research-loop-build-plan.md:10, plans/2026-08-16-research-loop-next-steps.md:101, plans/2026-08-16-research-loop-next-steps.md:121
  suggestion: 写明搬迁连带的注册表改动由 gyb 自己做，并在钩子的 deny 回话里直接列出「要搬哪个文件、连带要改哪个注册表」两行。

[EXTRA7] sev=slows what: 快车道让 deploy 干 run 的活，但 deploy 的角色 json 没有配套权限。build-plan.md:90 里 deploy 的 reads 不含 ops/gpu_state.md、writes 只有 experiments/、ledger_writes 按第三节也拿不到 runs 账；build-plan.md:91 把这些全给了 run，build-plan.md:144 还规定 run 会话对 experiments/ 一律 deny。两张权限表在快车道这条路上都对不上。
  refs: plans/2026-08-16-research-loop-build-plan.md:90, plans/2026-08-16-research-loop-build-plan.md:91, plans/2026-08-16-research-loop-build-plan.md:144, plans/2026-08-16-research-loop-next-steps.md:43
  suggestion: 在 deploy 的 json 里单列一栏 quick_lane_extra，写清快车道额外能读 gpu_state_path、能写 worktree 内的产物目录，不含 runs 账。

[EXTRA8] sev=cosmetic what: 手动会话往 sessions 账的 model 字段写什么没定。build-plan.md:85 说角色 json 的 manual 一律 inherit，build-plan.md:62 的 sessions 行有 model 字段，build-plan.md:104 的 rl session start 要 --model M；账里该记字面 inherit 还是记当前真实模型名，两份文档都没写。记 inherit 的话，sessions 账事后查不出这次是谁跑的。
  refs: plans/2026-08-16-research-loop-build-plan.md:85, plans/2026-08-16-research-loop-build-plan.md:62, plans/2026-08-16-research-loop-build-plan.md:104
  suggestion: 规定 model 字段一律记实际模型标识，inherit 只是 json 里的取值、不许落进账里。

[EXTRA9] sev=slows what: build-plan.md:11 给 idea 和 reviewer 的 subagent 钉了 fable，和本机全局规则冲突：/home/y-guo/.claude/CLAUDE.md 的「Subagent 模型策略」写着一律不用 Fable，机械任务 sonnet、需要判断力的 opus，只有用户当次点名才可以用 Fable。按现在这份施工计划做出来的插件，每次起 idea 或 reviewer subagent 都会违反那条全局规则。
  refs: plans/2026-08-16-research-loop-build-plan.md:11, /home/y-guo/.claude/CLAUDE.md
  suggestion: 把 idea、reviewer 的 as_subagent 改成 opus，或者由 gyb 明确写一条例外说明这个插件内允许 fable。

 trace_errors: ["第 23 步把 run subagent 的模型写成 opus，和设计文档打架：next-steps.md:47 原话「run 要小要快，模型用 sonnet」，build-plan.md:11 写的是 run 用 opus，而 build-plan.md:3 自己规定「这份和设计文档冲突的地方，以设计文档为准」，所以按文档字面这一步该是 sonnet。轨迹只引了 build-plan.md:11，没引 next-steps.md:47。", "第 26 步 rl run add 落 runs 账第一行时没有任何指标，但 build-plan.md:187 的测试 10 规定 runs 行缺 metrics 或 commit 一律拒收；发射刚成功那一刻指标不可能有，这一步按字面走会被入账脚本挡下。（根因是 build-plan.md:115、139 和 187 自相矛盾。）", "第 27 步的 rl run finish 和第 37 步的 rl session end 都是就地回填已有行（补 exit_status、metrics、ended_at），但 build-plan.md:46 只给 decisions、issues、handoffs、feedback、evaluations 加了 version 字段，runs 和 sessions 没有，next-steps.md:67 又规定九本账「只增不改」。轨迹默认这两本能改，文档不支持。", "第 6 步让 deploy 读 ops/gpu_state.md，但 build-plan.md:90 的 deploy reads 栏里没有这一项，只有 run 有（build-plan.md:91）。next-steps.md:101 说读权一律不硬拦，所以拦不下来，但这一步已经越出 deploy 的 reads 纪律，轨迹的 basis 没有标出来。", "第 9 步让 deploy 跑 run.py record finish 记数字，这条命令写 ops/runs.jsonl 和 RESULTS.md（gpu-run/SKILL.md:145-148、180-181）。next-steps.md:72 说数字账只有 run 角色的脚本能写，next-steps.md:101 说不给 ops/ 这类文件开白名单，轨迹把它当成合规的收尾动作。"]

===== SCENARIO new-idea steps=55 gyb_touch=16 keys=['scenario', 'total_steps', 'gyb_touchpoints', 'frictions', 'extra', 'trace_errors']

[F0] where=第 22、23 步 kind=missing sev_sim=blocks sev_verified=slows real=True
  what: 转移表里 stuck→in_progress 那一行只说「回了 issue 的那个角色或 gyb」能写，写完之后单子已经是 in_progress，可是原来的 deploy subagent 早就销号了；换一个新 subagent 接手一张已经 in_progress 的单子在表里没有对应的行，也没写谁负责重新派这个 subagent。
  refs: 2026-08-16-research-loop-build-plan.md:71, 2026-08-16-research-loop-build-plan.md:73, 2026-08-16-research-loop-next-steps.md:89, 2026-08-16-research-loop-next-steps.md:91
  suggestion: 转移表补一行「in_progress→in_progress 换手（to_role 的新会话，前提是上一个持有会话已销号）」，并写明 stuck 捞回之后由原上游负责重新起 subagent。
  verify_reason: 转移表 build-plan.md:68-79 十行里确实没有 in_progress 换手的那一行，handoffs 行格式 build-plan.md:52 也没有「当前持有会话」字段，而 build-plan.md:62 的 open_handoffs_at_end 又要求销号时算出「挂在这个会话名下的单子」，判定依据无处可取。部分覆盖：next-steps.md:91 写了 gyb 可以自己开 session 去接单，build-plan.md:79 的 in_progress→todo（销号钩子或 reclaim）给了一条绕路。但按 build-plan.md:73，stuck→in_progress 只有回 issue 的角色或 gyb 能写，新起的 deploy 会话自己捞不回来。

[F1] where=第 35 步 kind=ambiguous sev_sim=blocks sev_verified=slows real=True
  what: run 的写权只有 artifact_root 和经 rl 写 runs 账，而 `python3 run.py launch` 必然写 ops/jobs.json、ops/runs.jsonl、RESULTS.md 这些 experiments/ 和产物根之外的文件，施工计划自己也写了「new1 的 ops/runs.jsonl 照旧由 run.py launch 写」。文档只说写权按路径硬拦，没说钩子管不管 Bash 子进程写出来的文件：管，run 角色照 gpu-run 走这条路就跑不动；不管，写权硬拦对任何走 Bash 的写入都形同虚设。
  refs: 2026-08-16-research-loop-next-steps.md:101, 2026-08-16-research-loop-next-steps.md:105, 2026-08-16-research-loop-build-plan.md:91, 2026-08-16-research-loop-build-plan.md:141, 2026-08-16-research-loop-build-plan.md:144
  suggestion: 在第七节明写一句「写权钩子只拦 Write/Edit 工具，Bash 与被调脚本的写入不拦，靠 run 的 SKILL.md 纪律加 reviewer 事后查」。
  verify_reason: 两份文档没有一处写钩子拦哪些工具。next-steps.md:101 只说「写权硬拦，按路径判」，build-plan.md:185 的钩子测试八条全是 Write 用例，build-plan.md:144 又允许 run「经 rl 写 runs 账」（rl 是 Bash 命令），build-plan.md:141 明写「new1 的 ops/runs.jsonl 照旧由 run.py launch 写」。文字倾向是只拦 Write/Edit，但没有一句话钉死，实现者两种做法都能自称合规。severity 降到 slows：按 141 行的原意实现就跑得通，卡住的是规格而不是流程。

[F2] where=第 29 步 kind=contradiction sev_sim=slows sev_verified=cosmetic real=True
  what: run 用哪个模型两份文档说的不一样：设计文档写「run 要小要快，模型用 sonnet」，施工计划第一节第 3 条写「run、deploy、analysis 用 opus」。施工计划自己声明冲突以设计文档为准，但第 3 条又是同一天 gyb 后裁的，按哪句走都能自圆其说。
  refs: 2026-08-16-research-loop-next-steps.md:48, 2026-08-16-research-loop-build-plan.md:11, 2026-08-16-research-loop-build-plan.md:3
  suggestion: 在角色 json 落地之前让 gyb 点一次名，把败下来的那句在原文里划掉并注明被哪一句取代。
  verify_reason: 冲突文本确实存在：next-steps.md:48「run 要小要快，模型用 sonnet」对 build-plan.md:11「run、deploy、analysis 用 opus」，落 tables/roles/run.json 之前必须有人拍板。但 build-plan.md:3 已经给了裁决规则（冲突以设计文档为准，冲突本身回来改施工计划），所以没人真被卡住，走 sonnet 并回改施工计划就是文档规定的动作，「按哪句走都能自圆其说」这句站不住。

[F3] where=第 9、29、46 步 kind=contradiction sev_sim=slows sev_verified=slows real=True
  what: 施工计划把 idea 和 reviewer 的 as_subagent 模型定成 fable，而机器全局规则写死「subagent 禁止用 Fable，一律 opus/sonnet」。本场景里 idea 和 reviewer 都由 gyb 手动开（走 inherit）所以没炸，但 idea 一旦被 workflow 当 subagent 派就直接违规。
  refs: 2026-08-16-research-loop-build-plan.md:11, /home/y-guo/.claude/CLAUDE.md（Subagent 模型策略）
  suggestion: 把 idea、reviewer 的 as_subagent 改成 opus，fable 只留给 gyb 点名的那一次。
  verify_reason: build-plan.md:11 和角色表 build-plan.md:89、93 三处都写 idea、reviewer 的 as_subagent 是 fable，两份文档没有任何一行提到禁 Fable 这条机器全局规则（/home/y-guo/.claude/CLAUDE.md「Subagent 模型策略」）。本场景里 idea 和 reviewer 都由 gyb 手动开，走 build-plan.md:85 的 manual=inherit，所以没炸；一旦按 next-steps.md:91 的默认接单方式把 idea 当 subagent 起就直接违规。

[F4] where=第 1 步 kind=missing sev_sim=slows sev_verified=cosmetic real=True
  what: 文档只写了 gyb 开终端加载 plugin-dir，没写用哪条动作把角色装到会话上（是模型自动触发 skill、还是 gyb 打一条命令）。入口 skill 的三件事里「领路」也没展开成具体动作。角色不装上，钩子和 sessions 登记全不发生。
  refs: 2026-08-16-research-loop-build-plan.md:205, 2026-08-16-research-loop-next-steps.md:119, 2026-08-16-research-loop-next-steps.md:105
  suggestion: 在第六节命令表加一行 `rl role <name>` 或明写「gyb 手动 /skill <role>」，把加载动作钉成一条可打出来的命令。
  verify_reason: 文档只写了触发时刻和目录，没写动作：next-steps.md:97「加载 skill 把角色分配给会话的那一刻算开始」，next-steps.md:105「钩子写在角色 SKILL.md 的头部，加载角色的那一刻装上」，build-plan.md:205「每个终端加载 claude --plugin-dir ./research-loop，一个终端一到两个角色」，入口 skill 的「领路」在 next-steps.md:119 也没展开。确实 NOT_IN_DOC。降到 cosmetic：在 Claude Code 里加载一个 skill 是标准动作，写不写命令都不改设计。

[F5] where=第 51、52 步 kind=missing sev_sim=slows sev_verified=cosmetic real=True
  what: 转移表 in_progress→done_pending_review 那一行只写了 work_order 和 launch_order 的前提，analysis_order 没有前提也没有验收产物；部署报告只对 deploy 有定义，analysis 交什么算交完、gyb 拿什么验收没写。
  refs: 2026-08-16-research-loop-build-plan.md:74, 2026-08-16-research-loop-build-plan.md:76, 2026-08-16-research-loop-next-steps.md:93
  suggestion: 给 analysis_order 补一条前提：notebook 路径非空且文件存在，验收人读 notebook。
  verify_reason: build-plan.md:74 那一行的前提栏确实只写了 work_order 的 report_paths 和 launch_order 的 actual_seconds，analysis_order 一个字没有，等于无前提直接放行。验收产物侧面有覆盖：build-plan.md:220「统计类证据走 analysis 的 notebook」、next-steps.md:61「reviewer 审 analysis 写的分析代码和 notebook 是不是 gyb 要的」，gyb 读 notebook 验收是文档意思。缺的只是入账脚本那一条前提，宽松而不是阻塞。

[F6] where=第 24 步 kind=too_heavy sev_sim=slows sev_verified=slows real=True
  what: 快车道的触发条件是「决定不动、只微调代码」，而 new-idea 这个场景天然要新开一条决定，于是最需要快的那类活恰好被挡在快车道外面，必须走全套：工单、发射单、分步计时、两层报告、四次状态转移、两轮验收。设计文档第 7 行说的「想法要快速多次迭代」在这条路上落不下来。
  refs: 2026-08-16-research-loop-next-steps.md:43, 2026-08-16-research-loop-next-steps.md:7
  suggestion: 把触发条件改成「gyb 当场点头就走快车道」，新决定也可以先在 worktree 出数进 scratch 账，合回主分支那一刻再补正式工单和正式重跑。
  verify_reason: 文档内部对不上：next-steps.md:43 把快车道的触发条件写死成「决定不动、只微调代码」，而 next-steps.md:141-142 否掉「部署报告按改动大小分档」和「分步计时只对长任务做」的理由都是「小改动走快车道」。新决定加小改动这一类既进不了快车道，又被那两条理由假定成已经进了快车道，于是必须走全套工单、发射单、分步计时、两层报告。这不是模拟者脑补，是两处原文的缝。

[F7] where=第 7、53 步 kind=ambiguous sev_sim=slows sev_verified=slows real=True
  what: 「探针输入换成中间层」到底是旧决定「取最后一层」的新一版，还是一条新决定，两种读法都成立；而且 `rl decision update` 的 sources 要不要重填、能不能把自己的旧版当来源，第三节和第六节都没说。第 53 步回填结论时同样撞这个问题。
  refs: 2026-08-16-research-loop-next-steps.md:82, 2026-08-16-research-loop-next-steps.md:31, 2026-08-16-research-loop-build-plan.md:47, 2026-08-16-research-loop-build-plan.md:48, 2026-08-16-research-loop-build-plan.md:106
  suggestion: 写一条判据：正文改的是同一件事的做法就 update，换了要回答的问题就 add；并明写 update 必须重填 sources，允许 kind=decision 指自己的上一版。
  verify_reason: add 还是 update 的判据 NOT_IN_DOC：next-steps.md:31 只说「成为原决定的新一版或者一条新决定」，next-steps.md:82 只讲版本机制，两处都不给挑法。但「update 要不要重填 sources」这半条有覆盖，模拟者算漏了：build-plan.md:46 说同一个 id 的新版本是新的一行，build-plan.md:48 说 sources 空列表拒收，两句合起来就是每一版都必须带非空 sources。能不能拿自己上一版当来源确实没写。

[F8] where=第 29、41 步 kind=missing sev_sim=slows sev_verified=slows real=True
  what: deploy 起 run subagent 之后要不要一直等着：run 负责长时间任务，可能跑几小时，而发射单的验收人必须是 from_role（deploy），工单交验收也在同一个 deploy 会话里。deploy subagent 挂着等还是先销号、销号之后 ho-0008 的 accepted 由谁写，文档没写。
  refs: 2026-08-16-research-loop-next-steps.md:47, 2026-08-16-research-loop-next-steps.md:48, 2026-08-16-research-loop-next-steps.md:91, 2026-08-16-research-loop-build-plan.md:75
  suggestion: 明写长任务的做法：deploy 开完发射单就交单销号，launch_order 的 accepted 由 gyb 或 reviewer 兜底，或者 run 交单即自动 accepted。
  verify_reason: 「deploy 起完 run subagent 之后挂着等还是先销号」两份文档一个字没有，而 next-steps.md:47-48 明说 run 主要负责长时间任务、next-steps.md:97 又规定销号时名下不许挂 in_progress 单子，deploy 手上的 ho-0007 正是 in_progress，这个口子真空着。但「launch_order 的 accepted 谁写」有覆盖：build-plan.md:75 写的是 from_role 或 gyb，gyb 本来就能兜底。

[EXTRA0] sev=slows what: idea 的 reads 栏里没有 experiments/，可是验收部署报告非读它不可。build-plan.md:89 给 idea 的 reads 是「全部九本账、notes/（要 grant）、analysis/ 产物」，而 next-steps.md:39 规定两份部署报告放在 experiments/ 下这张工单自己的目录里，next-steps.md:93 又规定验收人默认是 idea、必须先读 method 再读 detail。第 44 步 idea 验收就是在读一个自己 reads 栏里没有的目录。读权不硬拦，所以不会被 deny，但角色 json 和验收职责直接打架。
  refs: 2026-08-16-research-loop-build-plan.md:89, 2026-08-16-research-loop-next-steps.md:39, 2026-08-16-research-loop-next-steps.md:93
  suggestion: 角色表里 idea 的 reads 补上「experiments/ 下的部署报告目录」，或者把报告改放到 idea 读得到的地方。

[EXTRA1] sev=slows what: run 的 writes 栏漏了 handoffs 账和 issues 账。build-plan.md:91 写 run 的 writes 只有 artifact_root 和 runs 账，build-plan.md:95 又说 ledger_writes 按第三节的句子抄；可是 run 必须调 rl handoff start、rl handoff estimate、rl handoff done（build-plan.md:112、113），出问题还必须 rl issue open 给 deploy（next-steps.md:51、build-plan.md:144）。按 json 生成的入账校验会把 run 自己该干的活拦掉，退出码 3。
  refs: 2026-08-16-research-loop-build-plan.md:91, 2026-08-16-research-loop-build-plan.md:95, 2026-08-16-research-loop-build-plan.md:112, 2026-08-16-research-loop-build-plan.md:113, 2026-08-16-research-loop-build-plan.md:144
  suggestion: 第五节把每个角色的 ledger_writes 逐本账写全（run 至少要 handoffs 的 start/estimate/done/stuck 和 issues 的 open），别只写目录写权。

[EXTRA2] sev=blocks what: 发射用的 python3 run.py 永远在 experiments/ 外，而文档明确不给它开白名单。next-steps.md:101 写「不给仓库根的 run.py、MAP.md、ops/ 这类文件开白名单」，可是 build-plan.md:136、139 又把 free_cmd 和 launch_cmd 的模板定成 run.py 的子命令。new1 的规矩是新任务必须挂进 run.py 的注册表才跑得起来，deploy 和 run 都没有改它的权，于是每加一个新实验任务都得停下来等 gyb 手动改注册表，跟第 14 步撞钩子是同一个死结，只是这个没有搬文件这条出路：run.py 搬不进 experiments/。
  refs: 2026-08-16-research-loop-next-steps.md:101, 2026-08-16-research-loop-build-plan.md:136, 2026-08-16-research-loop-build-plan.md:139
  suggestion: 在第七节明写发射入口这一类「插件依赖的宿主命令」怎么办：要么允许 launch_cmd 走 --cmd 逃生口不碰注册表，要么给注册表文件一条单独的裁决。

[EXTRA3] sev=slows what: rl run add 在发射成功那一刻落第一行，此时不可能有 metrics，和测试第 10 条「缺 metrics 拒收」冲突。build-plan.md:139 规定发射成功后就落数字账第一行，build-plan.md:54 把 metrics 列进 runs 的字段，build-plan.md:187 又把缺 metrics 定成拒收。两处按字面实现，run 角色的正常路第一步就过不去。
  refs: 2026-08-16-research-loop-build-plan.md:139, 2026-08-16-research-loop-build-plan.md:54, 2026-08-16-research-loop-build-plan.md:187
  suggestion: 把 runs 账拆成发射行和收尾行两种，或者明写 metrics 只在 rl run finish 时必填。

[EXTRA4] sev=cosmetic what: sessions 账没有「上游」字段，next-steps.md:55 说的「gyb 直接开 analysis session 的时候上游填 gyb」无处可填。build-plan.md:62 给 sessions 定的字段是 session_id、role、model、started_at、ended_at、end_reason、open_handoffs_at_end 七样，handoffs 行里有 from_role（build-plan.md:52），但 gyb 手动开会话、还没有单子的那一段（第 46、47 步就是这一段，analysis 先提口径后接单）没有任何地方记上游是谁。
  refs: 2026-08-16-research-loop-next-steps.md:55, 2026-08-16-research-loop-build-plan.md:62, 2026-08-16-research-loop-build-plan.md:52
  suggestion: sessions 行加一个 upstream 字段，rl session start 时带上；或者明写上游只体现在单子的 from_role 上、没单子的会话不记上游。

[EXTRA5] sev=slows what: deploy 自决要留痕，但留到什么粒度、来源填什么没写。build-plan.md:218 规矩二要求每个自决进自己那本 decisions 文件且来源不许空，deploy 的来源只能是 decisions.idea 的条目、仓库文件或 run_id（build-plan.md:48）。deploy 在 experiments/ 里改代码时的实现选择（中间层具体取第几层、改哪个函数）到底算不算「决定」，一条不写和一步一条之间没有判据，reviewer 按 next-steps.md:61 审「代码写得对不对」的时候拿什么当基准也就飘着。
  refs: 2026-08-16-research-loop-build-plan.md:218, 2026-08-16-research-loop-build-plan.md:48, 2026-08-16-research-loop-next-steps.md:61
  suggestion: 在公共规矩第二条后面补一句粒度判据，比如「改变实验结果的选择才算自决，纯写法不算」，并说明 deploy 自决的来源默认填改动的文件路径。

[EXTRA6] sev=slows what: reviewer 的问题清单出来之后没有任何回路。next-steps.md:59 写 reviewer 只写 review/ 里的问题清单、不开 issue 不派活、动不动由 gyb 看完定，可是九本账里没有一本收这份清单，rl status（build-plan.md:120）和 rl doctor（build-plan.md:122）扫的都是账，扫不到 review/ 下的文件。gyb 不主动去读那个目录，第 54 步的产出就没有任何机制让它再冒出来。
  refs: 2026-08-16-research-loop-next-steps.md:59, 2026-08-16-research-loop-build-plan.md:120, 2026-08-16-research-loop-build-plan.md:122
  suggestion: 让 rl status 顺带列一行「review/ 下有 N 份清单，最新一份是几号写的」，或者规定 reviewer 写完清单往 feedback 账提一条指向文件路径。

 trace_errors: ["第 27 步派错了人：发射前 commit 被安排给 deploy，build-plan.md:139 把「Phase 4 发射前 commit、run.py launch、交监控命令」整段写在 run 的 use case 里，build-plan.md:141 的 Phase 6a 收尾五连也带 commit。deploy 的 writes 按 build-plan.md:90 只有 experiments/，文档从没给 deploy 派过 commit 这件事。", "第 5 步把三类来源判成一项都填不出，忽略了 kind=decision：「从最后一层换成中间层」可以引原来那条「取最后一层」的决定当来源（next-steps.md:31 三类来源第一类、next-steps.md:81-83 决定账是一棵引用树、build-plan.md:48 sources 的 decision 取值）。第 6 步让 gyb 中途去写 notes 因此不是文档逼出来的唯一路。", "第 15 步说「assignee 是 gyb 触发桌面通知」，文档只给 reassign 定了这条：build-plan.md:110「reassign --to gyb 触发通知」，next-steps.md:70「只有改派到 gyb 名下的时候 bin/rl 才给 gyb 发通知」。首次 open 就写 --to gyb 算不算「改派」，build-plan.md:50 的措辞（assignee 变成 gyb 的那一版）两头都能读，trace 直接当成会通知。", "全程 55 步没有一行写进 decisions.deploy。build-plan.md:218 规矩二要求角色自己做的每个决定进自己那本 decisions 文件、来源不许空，build-plan.md:217 规矩一还要求规格没写到的岔路缺省往下干并追加一条决定。第 25 步 deploy 动手改取层代码必然有自决（改哪个函数、中间层取第几层的具体实现），trace 里零条。", "第 35 步 rl run add 落数字账第一行时没有 metrics，而 build-plan.md:187 的测试第 10 条写「runs 账 schema：缺 metrics 或 commit 拒收」。按 build-plan.md:139 这一行必须在发射成功后立刻落，那时候不可能有指标，这一步照文档会被入账脚本退回。"]

===== SCENARIO result-wrong-review steps=29 gyb_touch=12 keys=['scenario', 'total_steps', 'gyb_touchpoints', 'frictions', 'extra', 'trace_errors']

[F0] where=第 7 到 9 步（reviewer 想把决定连到代码） kind=blocked sev_sim=blocks sev_verified=slows real=True
  what: reviewer 唯一能把「哪条决定」连到「哪段代码」的链路是 handoffs 的 decision_refs 加工单目录，但 reviewer 的 reads 里只有 decisions.idea、experiments/、analysis/、runs，没有 handoffs（也没有 evaluations，所以它审 analysis 那一样时也无从知道 gyb 批过哪些口径）；而 handoffs 行里恰好带 report_paths 指向 deploy 的两份报告，对抗性隔离又要求默认不读报告。按纪律走，reviewer 定位不到审查对象；越纪律读，隔离就破了。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:93, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:52, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:63, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:61
  suggestion: 给 reviewer 开一个裁剪视图 `rl handoff show ID --for-reviewer`（只出 work_type、decision_refs、status，隐去 report_paths 和 explanation），把这个视图和 evaluations 写进 reviewer 的 reads。
  verify_reason: build-plan.md:93 的 reviewer reads 只有 decisions.idea / experiments/ / analysis/ / runs，确实不含 handoffs 和 evaluations；而 next-steps.md:61 要它审「实验运行得对不对」和「analysis 的代码是不是 gyb 要的」，前者的 command/args/step_table 在 handoffs 的 launch 子对象里（build-plan.md:52），后者的批准口径在 evaluations 里（build-plan.md:60）。两份文档都没有把这两本账给 reviewer 的句子，缺口是真的。但严重度写高了：读权一律不硬拦、reads 只是纪律（next-steps.md:101、build-plan.md:85），runs 账本身带 command（build-plan.md:54），所以 reviewer 不是「定位不到」，只是拿不到分步表和口径。另外「越纪律读就破隔离」这半句不成立——handoff 行里只有 report_paths 这个路径字符串，看见路径不等于读报告。

[F1] where=第 11 到 14 步（review 清单出来之后往回接） kind=missing sev_sim=blocks sev_verified=slows real=True
  what: reviewer 的产出只写 review/，不开 issue、不派活；而 idea 的 reads 是九本账加 notes/ 加 analysis/ 产物，不含 review/。从「审出代码和决定不一致」到「派活去改」中间没有任何账本或命令承接，全靠 gyb 一个人口头搬运，链子在账上是断的。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:59, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:89
  suggestion: 把 review/ 加进 idea 的 reads，并允许 gyb 用一条 `rl issue open --to idea --kind ... --text` 把清单挂给 idea，issue 里带 review 文件路径。
  verify_reason: build-plan.md:89 的 idea reads 是「全部九本账、notes/（要 grant）、analysis/ 产物」，review/ 既不是账也不是 analysis/ 产物，两份文档里没有任何一句把 review/ 给 idea 读，这一半是真缺口。但「链子断了」这半句站不住：next-steps.md:59 明写 reviewer 不开 issue、不派活，「动不动由 gyb 看完之后定」，承接人就是 gyb，这是设计选的路不是漏的路。所以定级降到 slows。

[F2] where=第 2 步和第 10 步（要看那次跑出来的数字） kind=missing sev_sim=slows sev_verified=slows real=True
  what: 命令表里 runs 账只有 `rl run add` 和 `rl run finish` 两个写命令，没有 show 或 list；decisions、handoffs、issues、evaluations 都配了查询命令，唯独数字账没有。gyb 和 reviewer 想看那次跑的 metrics 只能手工 grep loop/runs.jsonl，绕过了 rl。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:115, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:108
  suggestion: 命令表加一行 `rl run show RUN_ID` / `rl run list [--handoff ID]`，谁都能调。
  verify_reason: build-plan.md:115 的 runs 那一行确实只有 rl run add 和 rl run finish 两个写命令，对比 build-plan.md:108（decision show/list）、114（handoff show/list）、110（issue list）、118（eval list）都配了查询命令，唯独数字账没有。而 next-steps.md:67 写死账本「只经 bin/rl 命令进出」——「出」也算，所以手工 grep loop/runs.jsonl 是绕过设计，不是被允许的兜底。缺口真，且影响 reviewer（build-plan.md:93 reads 含 runs）和 analysis（build-plan.md:92）两个角色的日常。

[F3] where=第 21 步（idea 起 deploy subagent） kind=contradiction sev_sim=slows sev_verified=slows real=True
  what: 施工计划把 idea 和 reviewer 作为 subagent 时的模型定成 fable，而这台机器的全局规则写死 subagent 禁止用 Fable、一律 sonnet 或 opus 且每次派发都要显式传模型。本场景两个角色都是 gyb 手动开、走 inherit 所以没触发，一旦 idea 或 reviewer 被 workflow 派出去就直接违规。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:11, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:89, /home/y-guo/.claude/CLAUDE.md
  suggestion: 第一节第 3 条把 idea 和 reviewer 的 as_subagent 从 fable 改成 opus。
  verify_reason: build-plan.md:11 明写 idea、reviewer 作为 subagent 用 fable，build-plan.md:89 和 93 的表格里也是 fable；这与 /home/y-guo/.claude/CLAUDE.md 的硬规则（subagent 禁止用 Fable，一律 sonnet/opus，且每次派发显式传模型）直接冲突。文档写到了，但写的是违规值，属于必须改的真摩擦。本场景两个角色都是 gyb 手动开走 inherit（build-plan.md:85），所以这一轮没触发，一旦走 build-plan.md:207 步 8 的「主会话派 agent（模型按第一节第 3 条）」就直接违规。

[EXTRA0] sev=blocks what: 验收人是谁，三处口径不一致。设计文档 next-steps.md:89 写「验收完成（只有上游写，验收人必须是派活的人）」，同一份文档 next-steps.md:93 又写「验收人（默认 idea，gyb 点名的时候是 gyb 自己）」，施工计划 build-plan.md:75 落成「from_role 或 gyb」。本场景第 27 到 28 步正好是 gyb 点名自己验收，照 89 行入账脚本该拒收，照 75 行该通过。build-plan.md:3 又规定冲突以设计文档为准，而设计文档内部就打架，实现者无从选。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:89, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:93, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:75, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:3
  suggestion: 把 next-steps.md:89 的括号改成「只有上游或 gyb 写」，与 93 行和转移表对齐。

[EXTRA1] sev=slows what: 打回之后谁把下游重新拉起来，没写。转移表 build-plan.md:77 规定 rejected → in_progress 由 to_role 写，next-steps.md:89 也说「打回之后下游重新开干」；但下游是 subagent 的时候，它在提交 done_pending_review 之后就被 SubagentStop 销号了（next-steps.md:97、build-plan.md:62）。本场景第 28 步若 gyb 打回，单子停在 rejected，没有任何一句写「谁负责再起一个 deploy subagent 去接」。next-steps.md:91 只写了开单那一刻上游起 subagent，没写打回这一刻。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:77, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:89, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:91, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:97
  suggestion: 在 next-steps.md:91 接单那一段补一句「打回等同重新派活，由 from_role 再起一个 to_role 的 subagent 接」，或者让 rl handoff reject 直接把单子退回 todo。

[EXTRA2] sev=slows what: 代码那一侧没有决定版本的锚点，这正是本场景要审的东西。decision_refs 带版本只存在于 handoffs 行里（build-plan.md:52），而 experiments/ 里的代码和两份部署报告都不要求写自己照的是哪条决定第几版（next-steps.md:39 只规定两份报告的内容分工）。就算把 handoffs 给 reviewer 读，reviewer 也只能按目录名把工单和代码对上，对不上「这一段代码对应决定第 2 版还是第 3 版」。决定又是可以改版的（next-steps.md:82），审「代码和决定是不是一回事」缺一个锚。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:52, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:39, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:82
  suggestion: 在 next-steps.md:39 的 method 报告里加一条必写项：本次实现依据的 decision_refs 原样抄一遍（编号加版本）。

[EXTRA3] sev=slows what: gyb 本人不能往决定账写字。build-plan.md:105 的 rl decision add「谁能调」写的是「五个角色」，106 的 update 写的是「同角色」，两处都不含 gyb；而 next-steps.md:29 说 gyb 参与的工程细节「同样写进决定账」，next-steps.md:19 列 gyb 亲自做的五件事里也没有决定账。结果 gyb 看完 review 清单得出的判断，必须借 idea 会话的手才能留痕（本场景第 16 步就是为此专门开了一个会话）。裸终端里的 gyb 在九本账里能写的只有 grants、feedback 裁决、evaluations 批准。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:105, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:106, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:29, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:19
  suggestion: 在 build-plan.md:105、106 的「谁能调」里加上 gyb，写进哪本文件用 --role 指定；或者在设计文档里明写「gyb 的决定一律经 idea 落账」。

[EXTRA4] sev=slows what: 反常结果预警这个 monitor 挂在谁身上没写。next-steps.md:115 说 monitors/ 有两个，「发射看门狗只在 run 上线时起、反常结果预警盯数字账」，但待验证清单只验了看门狗的挂法（build-plan.md:168 的 on-skill-invoke:run），反常预警是常驻进程、跟着哪个角色起、还是 rl run finish 时同步跑，两份文档都没写。本场景整条链的起点是「结果不对」，起点上的这个部件正好没落地方案。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:115, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:168, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:158
  suggestion: 把反常预警改成 rl run finish 落账时同步检查阈值并开 anomaly issue，去掉一个常驻进程；或者在第九节加一条验证它的挂法。

[EXTRA5] sev=cosmetic what: review/ 目录只有归属没有格式。next-steps.md:113 只说 review/ 是 reviewer 的产出目录，next-steps.md:59 只说产出是「问题清单」，没写文件怎么命名、一次审查一个文件还是一条一个文件、清单里一条问题的字段是什么。build-plan.md:122 的 rl doctor 六项检查也不扫 review/，所以清单写了没人接、写重了没人管都查不出来。本场景第 11 步的文件名完全是模拟者自己编的。
  refs: /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:113, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-next-steps.md:59, /home/y-guo/reproduce/new1/plans/2026-08-16-research-loop-build-plan.md:122
  suggestion: 在 common/ 母版里加一份 review 清单的模板（一条问题四栏：决定编号加版本、代码位置、对不上在哪、建议动作），文件名定成 review/<日期>-<决定编号>.md。

 trace_errors: ["第 2 步 gyb「直接 grep loop/runs.jsonl 的 metrics」与 next-steps.md:67 冲突：那一行写的是九本账「只经 bin/rl 命令进出」，「出」也在内。模拟者引的 next-steps.md:101（读权一律不硬拦）说的是钩子不硬拦，不等于允许绕开 rl 读账。这一步应该记成「没有可用命令」，而不是记成合规动作。", "第 10 步 reviewer「直接读 loop/runs.jsonl 里 handoff_id=ho-0013 那一行」同上，撞 next-steps.md:67。build-plan.md:93 把 runs 列进 reviewer 的 reads 指的是能读这本账的内容，不是许可绕过 bin/rl 直接开文件。", "第 28 步 gyb 亲自跑 rl handoff accept，只对上了 build-plan.md:75（from_role 或 gyb），却和 next-steps.md:89 的原话「验收完成（只有上游写，验收人必须是派活的人）」相反。本单 from_role 是 idea，按设计文档这一行 gyb 不能写 accepted。模拟者只引了施工计划那一侧，没记这处冲突（施工计划自己在 build-plan.md:3 声明冲突以设计文档为准）。", "第 12 步断定 reviewer 不给 decisions.reviewer.jsonl 追加行，与 build-plan.md:105「rl decision add……谁能调：五个角色」和 build-plan.md:218「角色自己做的每个决定进自己那本 decisions 文件」相反。next-steps.md:59 的「产出只写 review/」按 build-plan.md:85 是目录写权那一栏的事，管不到账本追加权。", "第 1 步说跑 rl status「确认 ho-0012 和 ho-0013 都已经是 accepted 终态」，但 build-plan.md:120 写的是 rl status 列「所有没到终态的单子」——终态的单子根本不出现在输出里，看不见只能推断不存在未完单，不能据此确认某单已 accepted。要确认得用 build-plan.md:114 的 rl handoff show。"]

===== SCENARIO plot-new-plan steps=22 gyb_touch=11 keys=['scenario', 'total_steps', 'gyb_touchpoints', 'frictions', 'extra', 'trace_errors']

[F0] where=第 7、8 步（analysis 读 runs 账、找模型规模） kind=blocked sev_sim=blocks sev_verified=slows real=True
  what: runs 账的行格式里没有任何描述这次 run 跑的是什么模型的字段：主键、handoff_id、commit、command、host、gpus、artifact_dir、log_path、时间、exit_status、metrics、data_path，metrics 只装「指标名到数」。「按模型规模分组」这个分组键在账里根本不存在，analysis 只能去 command 字符串里正则抠模型名。
  refs: 2026-08-16-research-loop-build-plan.md:54
  suggestion: runs 行加一个 config 字典字段（模型名、参数量、数据集、split、超参），run 落账时必填，analysis 的分组键一律从这个字段取。
  verify_reason: runs 行字段表在 build-plan.md:54 全列了：run_id/handoff_id/commit/command/host/gpus/artifact_dir/log_path/started_at/finished_at/exit_status/metrics/data_path，确实没有模型名或模型规模字段，metrics 按同行原话只装「键是指标名、值是数」。两份文档里没有第二处给 runs 行加字段的地方。但不是 blocks：next-steps.md:55 写着 analysis「先问 gyb 要统计什么」，哪些 run 入图、按什么分组可以由 gyb 当场口述，另外 build-plan.md:217 的岔路缺省允许 analysis 自己定取法并留痕，所以走得下去，只是分组键没有账本依据、reviewer 事后无从复核。severity 降为 slows。

[F1] where=第 12、18 步（gyb 在角色会话里敲 gyb 专属命令） kind=missing sev_sim=slows sev_verified=slows real=True
  what: rl 从会话状态文件读角色，gyb 手动加载了 analysis 的那个终端里，rl 认到的角色就是 analysis，非 gyb 调 rl eval approve 退出码 3，rl handoff accept 的允许写者是 from_role 或 gyb 也一样过不去。文档没写 gyb 坐在角色会话里怎么行使自己的写权，只能另开一个裸终端。
  refs: 2026-08-16-research-loop-build-plan.md:99, 2026-08-16-research-loop-build-plan.md:75, 2026-08-16-research-loop-build-plan.md:118, 2026-08-16-research-loop-build-plan.md:186
  suggestion: 会话状态文件加一个 operator 字段，手动加载的会话记 operator=gyb，rl 见到这个字段就放行 gyb 专属子命令。
  verify_reason: build-plan.md:99 写的是 rl 从会话状态文件读角色、读不到才按 gyb 处理，而且「--role 参数可以显式指定但只允许在裸终端里用」；build-plan.md:186 的测试项写死「非 gyb 调 rl eval approve 退出码 3」。加载了 analysis 的会话里状态文件存在、角色是 analysis，两份文档都没有第二条通道让坐在这个会话前面的 gyb 行使自己的写权（eval approve、handoff accept 的 gyb 那一支、grant add）。NOT_IN_DOC。绕法是另开裸终端，所以是 slows 不是 blocks。

[F2] where=第 11 步（analysis 提口径） kind=ambiguous sev_sim=slows sev_verified=slows real=True
  what: 「画什么图」这件事记在哪本账没写死。口径账一行一个指标，字段是 name、definition、applies_to、code_path，装不下「按模型规模分组的准确率曲线」里的分组维度、横轴用什么、画成折线还是散点；而设计文档说画什么图由 gyb 说、analysis 记、gyb 批，能批的账只有口径账。两种读法都说得通：图挤进口径账的 definition 里，或者图根本不进账、只靠口头。
  refs: 2026-08-16-research-loop-next-steps.md:17, 2026-08-16-research-loop-next-steps.md:75, 2026-08-16-research-loop-build-plan.md:60, 2026-08-16-research-loop-build-plan.md:70
  suggestion: 口径账加 kind 字段区分 metric 和 figure，figure 行带分组维度和坐标轴，analysis_order 的 evaluation_refs 允许引 figure 行。
  verify_reason: 口径账在 next-steps.md:75 定义成「一行一个指标」，build-plan.md:60 的字段是 name/definition/applies_to/code_path/status，没有分组维度、横轴、图形式这些字段；handoffs 的 analysis_order 在 build-plan.md:52 只有 evaluation_refs，也没有图的规格字段。next-steps.md:17 要求「画什么图 gyb 说、analysis 记、gyb 批」，能批的账只有口径账。两份文档里找不到一句写死图记在哪、用什么字段记，NOT_IN_DOC。

[F3] where=第 16 步（analysis 提干完等待验收） kind=ambiguous sev_sim=slows sev_verified=cosmetic real=True
  what: 转移表里 in_progress 到 done_pending_review 这一行只给 work_order 和 launch_order 写了前提，analysis_order 空着。验收产物那一节说的是部署报告，那是 deploy 的东西。所以 analysis 交什么才算交、gyb 拿什么验收，可以读成「无前提直接过」，也可以读成「比照 work_order 要求路径必填」。
  refs: 2026-08-16-research-loop-build-plan.md:74, 2026-08-16-research-loop-build-plan.md:181, 2026-08-16-research-loop-next-steps.md:93
  suggestion: 转移表补一行 analysis_order 的前提：figure_paths 和 notebook_path 非空且文件存在。
  verify_reason: 转移表本身不歧义：build-plan.md:74 那一行只给 work_order 和 launch_order 写前提，build-plan.md:81 又写「入账脚本只认这张表，表外的转移一律拒收」，所以 analysis_order 无前提是确定读法，模拟者说的「两种读法」这一半不成立。真缺的是另一件：next-steps.md:93「验收产物是部署报告」通篇讲的是 deploy 的两份报告，analysis_order 交什么算交、图和 notebook 的路径落在单子的哪个字段，build-plan.md:52 的字段表里没有对应物，rl doctor（build-plan.md:122）也就查不到。这一半 NOT_IN_DOC。

[F4] where=第 7 步（analysis 读 runs 账） kind=missing sev_sim=slows sev_verified=slows real=True
  what: rl 命令表里 runs 账只有 add 和 finish 两个子命令，没有 list 或 show。analysis 要读数只能直接打开 loop/runs.jsonl，而设计文档写的是九本账「只经 bin/rl 命令进出」。
  refs: 2026-08-16-research-loop-build-plan.md:115, 2026-08-16-research-loop-next-steps.md:67, 2026-08-16-research-loop-next-steps.md:101
  suggestion: 命令表补 rl run list / rl run show，带 --json 和按字段过滤，analysis 一律从这里取数。
  verify_reason: build-plan.md:115 那一行 runs 账只列了 rl run add 和 rl run finish，同表的 decisions（:108）、handoffs（:114）、issues（:110）、evaluations（:118）都有 list 或 show，唯独 runs 没有；而 next-steps.md:67 写九本账「只经 bin/rl 命令进出」。analysis 的主数据源就是 runs（build-plan.md:92），只能直接开 loop/runs.jsonl，又撞上 next-steps.md:109「大文件禁止整读」的读法纪律。两份文档没有别处补这个查询命令，NOT_IN_DOC。

[F5] where=第 11 步（rl eval propose 填 code_path） kind=missing sev_sim=cosmetic sev_verified=cosmetic real=True
  what: 口径行的 code_path 形如 analysis/common/metrics.py:accuracy，但没写提口径的时候这个文件要不要已经存在。决定来源的 file 类明确写了路径不存在拒收，口径的 code_path 没有对应的话。analysis 先提口径后写代码就会踩到。
  refs: 2026-08-16-research-loop-build-plan.md:60, 2026-08-16-research-loop-build-plan.md:180
  suggestion: 明写 code_path 在 propose 时不校验存在、在 approve 时校验存在。
  verify_reason: build-plan.md:60 只写了 code_path 形如 analysis/common/metrics.py:accuracy，没写什么时候校验存在；build-plan.md:180 的存在性拒收只针对决定来源的 file 类，build-plan.md:181 只针对部署报告的两个路径，build-plan.md:74 同理。evaluations 的 code_path 在 propose 还是 approve 时校验，两份文档都没写，NOT_IN_DOC。

[EXTRA0] sev=slows what: gyb 在裸终端写的账行没有 session_id。公共骨架五样在 build-plan.md:46 写死每一行都要有 session_id，而 build-plan.md:99 说裸终端就是「读不到状态文件」的那种情况，裸终端里没有会话状态文件、sessions 账（build-plan.md:62）里也不会有这个会话。本场景 gyb 在裸终端写了三行账（eval approve、handoff open、handoff accept），这三行的 session_id 填什么，两份文档都没写。
  refs: 2026-08-16-research-loop-build-plan.md:46, 2026-08-16-research-loop-build-plan.md:99, 2026-08-16-research-loop-build-plan.md:62
  suggestion: 明写裸终端写入时 session_id 填一个固定值（比如 gyb-cli），或者由 rl 为裸终端生成一次性 session 行登记进 sessions 账。

[EXTRA1] sev=slows what: 口径提了之后没有任何东西告诉 gyb 有一条等他批。rl status 在 build-plan.md:120 列的是未到终态的单子、改派给 gyb 超阈值的 issue、活着的会话，proposed 状态的 evaluations 不在其中；桌面通知按 next-steps.md:70 只有 issue 改派到 gyb 才发。本场景 gyb 恰好坐在 analysis 会话前面才知道，走默认的 subagent 接单路线（next-steps.md:91）就没人叫他。
  refs: 2026-08-16-research-loop-build-plan.md:120, 2026-08-16-research-loop-next-steps.md:70, 2026-08-16-research-loop-build-plan.md:118, 2026-08-16-research-loop-next-steps.md:91
  suggestion: rl status 的输出里加一段「等 gyb 批的口径行」，和改派给 gyb 的 issue 并列。

[EXTRA2] sev=slows what: 口径被 gyb 否掉之后怎么走没有通道。evaluations 的 status 在 build-plan.md:60 只有 proposed、approved、retired，命令表 build-plan.md:118 只有 propose/approve/retire/list，没有打回也没有改提。gyb 觉得 analysis 提的口径横轴不对，只能不理它（单子按 build-plan.md:70 开不出来）或者 retire（语义是废除一条生效过的口径）。build-plan.md:46 说 evaluations 带 version，但没有任何命令能追加一版。
  refs: 2026-08-16-research-loop-build-plan.md:60, 2026-08-16-research-loop-build-plan.md:118, 2026-08-16-research-loop-build-plan.md:46, 2026-08-16-research-loop-build-plan.md:70
  suggestion: 命令表补 rl eval reject ID --reason 和 rl eval update ID（同 id 加一版），status 加一个 rejected。

[EXTRA3] sev=slows what: 准确率这个数到底谁算，两条规矩指向两个地方。build-plan.md:219 规矩三说数字只经 run 的脚本入账、禁止用眼睛读日志填数，runs 行的 metrics（build-plan.md:54）里已经有 accuracy；build-plan.md:60 的口径行又要求 code_path 指向 analysis/common/metrics.py:accuracy，build-plan.md:220、221 说统计类证据走 analysis 的 notebook、派生量只用 approved 的口径。同一个 accuracy 是直接取 runs.metrics 还是由 analysis 按口径重算，重算又要读产物（不在 analysis 的 reads 里，build-plan.md:92），文档没裁。
  refs: 2026-08-16-research-loop-build-plan.md:219, 2026-08-16-research-loop-build-plan.md:54, 2026-08-16-research-loop-build-plan.md:60, 2026-08-16-research-loop-build-plan.md:220, 2026-08-16-research-loop-build-plan.md:92
  suggestion: 明写口径行分两类：runs.metrics 已有的指标口径只登记来源键名不重算，派生量才写 code_path 由 analysis 算。

[EXTRA4] sev=cosmetic what: 让 analysis 上线跑过版检查，但 analysis 没有读决定账的纪律权。next-steps.md:84 写「角色上线第一个动作跑过版检查」，build-plan.md:109 的 rl decision stale 谁都能调、输出是「引用的版本小于最新版的派活单和决定」；而 build-plan.md:92 里 analysis 的 reads 只有 runs、evaluations、handoffs 里的 analysis_order，不含任何 decisions 文件。analysis 跑出一条过版结果之后按纪律不该去读那条决定，能做什么没写。
  refs: 2026-08-16-research-loop-next-steps.md:84, 2026-08-16-research-loop-build-plan.md:109, 2026-08-16-research-loop-build-plan.md:92, 2026-08-16-research-loop-build-plan.md:85
  suggestion: 要么把 rl decision stale 的上线动作限定给 reads 里有 decisions 的角色（idea、deploy、reviewer），要么在 analysis 的 reads 里加上「自己引到的那几条决定」。

 trace_errors: ["第 19 步和文档不符。trace 说「accepted 已经是终态，rejected 要写原因、语义是活没干对，所以只能重开一张分析单」，但转移表 build-plan.md:76 的 done_pending_review→rejected 前提栏只写「reason 非空」，build-plan.md:77 的 rejected→in_progress 前提栏写的是「无」，next-steps.md:89 也只说「打回，必须附原因，打回之后下游重新开干」，没有任何一句把 rejected 限定成「活没干对」。gyb 在第 18 步先 accept 才失去这条通道，是 trace 自己选的走法，不是文档只留了重开单这一条路。", "第 7 步和文档的账本口径冲突。trace 让 analysis 直接打开 loop/runs.jsonl 读，next-steps.md:67 写的是九本账「只经 bin/rl 命令进出」。trace 的理由（写权钩子不管读、next-steps.md:101 读权不硬拦）只说明不会被拦，不等于符合规矩；而且整读一本 jsonl 撞 next-steps.md:109「大文件禁止整读」。这一步暴露的是命令表缺 runs 查询命令（build-plan.md:115），trace 直接跳过了这个冲突，把违规读法当成合规默认。"]

===== SCENARIO next-plan-after-results steps=25 gyb_touch=11 keys=['scenario', 'total_steps', 'gyb_touchpoints', 'frictions', 'extra', 'trace_errors']

[F0] where=第 1 步 kind=ambiguous sev_sim=blocks sev_verified=slows real=True
  what: 整条路的第一个动作就踩在没裁的那条上：rl 读不到会话状态文件时算不算 gyb，第九节第 9 条明写「要 gyb 裁」，主案是按 gyb 处理，备案是必须显式给 --as-gyb、缺参数拒收。裁成备案的话第 1、2、7、8、13、16 步的命令全要改写法。
  refs: plans/2026-08-16-research-loop-build-plan.md:99, plans/2026-08-16-research-loop-build-plan.md:174
  suggestion: 现在就裁死：裸终端默认按 gyb，只有写 grants、批口径、验收这三类命令额外要一次确认。
  verify_reason: 确是未裁的口子，两份文档都只把它挂起来没定：build-plan:99 明写「读不到状态文件的时候按 gyb 处理…这条要 gyb 裁，见第九节第 9 条」，build-plan:174 第 9 条写「不是机器验证，是裁决」，失败备案是改成 --as-gyb 缺参数拒收；build-plan:213 又把它列进「留给 gyb 的」。文档承认待裁不等于覆盖，所以判真。但两个分支的写法文档都给全了，纸上模拟走得下去，只是命令形态待定，不到 blocks。

[F1] where=第 7、8、13、16 步 kind=too_heavy sev_sim=slows sev_verified=slows real=True
  what: gyb 全程坐在 analysis 或 idea 会话里，但 rl 从会话状态文件读角色，凡是要求 role=gyb 的写入（eval approve、handoff open --type analysis_order、handoff accept、grant add）都写不了，每一次都要切到另一个裸终端敲一条命令再切回来。这一趟里换了四次终端。
  refs: plans/2026-08-16-research-loop-build-plan.md:99, plans/2026-08-16-research-loop-build-plan.md:60, plans/2026-08-16-research-loop-build-plan.md:70, plans/2026-08-16-research-loop-build-plan.md:116
  suggestion: 规定 gyb 手动加载的角色会话是双身份：状态文件多记一个 owner=gyb，需要 gyb 权限的命令加 --as-gyb 当场放行。
  verify_reason: 文档没给 gyb 坐在角色会话里行使 gyb 权限的口子。build-plan:99 说 rl 从会话状态文件读角色、--role 只允许裸终端用；build-plan:60 evaluations 的 approved 那一版 role 必须是 gyb，:116 grant 只有 gyb，:75 accepted 只能 from_role 或 gyb 写。同时 next-steps:17 又要求口径「gyb 说、analysis 记、gyb 批」，:55 要求 analysis 先问 gyb——gyb 本来就在角色会话里说话。切终端这件事 NOT_IN_DOC，属真摩擦。

[F2] where=第 19 步 kind=contradiction sev_sim=blocks sev_verified=slows real=True
  what: 「停掉一条方向」正是本场景的主动作，可 `rl decision retire ID` 的命令签名里没有 --source；另一边写着废除等于追加一版、每条决定来源必填、空列表入账脚本拒收。按前者写不进来源，按后者这一版直接被拒收。
  refs: plans/2026-08-16-research-loop-build-plan.md:107, plans/2026-08-16-research-loop-build-plan.md:48, plans/2026-08-16-research-loop-next-steps.md:31, plans/2026-08-16-research-loop-next-steps.md:82
  suggestion: 给 retire 加必填 --source，理由是停一条方向本来就该指着哪个 run 和哪张图停。
  verify_reason: 两处对不上，文档没有调和句。build-plan:107 的签名是 `rl decision retire ID`，没有 --source；build-plan:48 写 decisions 每行 sources「空列表拒收」，next-steps:31 写「至少一项，空列表入账脚本拒收」，next-steps:82 写「废除等于追加一版标 retired」，build-plan:180 测试 3 也钉了空列表拒收。retired 那一版的 sources 从哪来，两份文档都 NOT_IN_DOC。实现时沿用上一版是自然选择，不至于卡死，所以不判 blocks。

[F3] where=第 12 步 kind=missing sev_sim=slows sev_verified=slows real=True
  what: 转移表 in_progress→done_pending_review 那一行只写了 work_order 和 launch_order 的前提，analysis_order 没有前提；「验收产物是部署报告」这条也只管 deploy。analysis 交活时要不要落 notebook 路径、验收人拿什么看，都没写。
  refs: plans/2026-08-16-research-loop-build-plan.md:74, plans/2026-08-16-research-loop-next-steps.md:93
  suggestion: 转移表补一行 analysis_order 前提：output_paths 里的 notebook 和图路径都要存在，缺一个拒收。
  verify_reason: 转移表 build-plan:74 那一行只写了 work_order 的 report_paths 和 launch_order 的 actual_seconds 两个前提，analysis_order 没有；next-steps:93「验收不预写标准，验收产物是部署报告」通篇讲的是 deploy 提交报告；build-plan:52 的 report_paths 也只对 work_order 必填。analysis 交活附什么、验收人拿什么看，两份文档都没写。

[F4] where=第 10、17 步 kind=contradiction sev_sim=slows sev_verified=slows real=True
  what: 设计文档说九本账只经 bin/rl 命令进出，可命令表里 runs 账只有 add 和 finish 两个写命令，没有 list 或 show。analysis 和 idea 要看这批数字，只能绕过 rl 直接读 loop/runs.jsonl。
  refs: plans/2026-08-16-research-loop-next-steps.md:67, plans/2026-08-16-research-loop-build-plan.md:115, plans/2026-08-16-research-loop-build-plan.md:108
  suggestion: 补 `rl run list/show --json`，并把「只经 rl」这句限定成只管写入。
  verify_reason: next-steps:67 写九本账「只经 bin/rl 命令进出」，但 build-plan:115 的 runs 行只有 `rl run add` 和 `rl run finish` 两个写命令，:108 的 show/list 是 decisions 的、:114 的 show/list 是 handoffs 的，命令表里确实没有 run 的读命令。next-steps:101「读权一律不硬拦」让直接读 jsonl 不违规，所以是摩擦不是死路。

[F5] where=第 17 步 kind=missing sev_sim=slows sev_verified=slows real=True
  what: 本场景的核心动作是把一批数字对回决定，可账本里只有 runs.handoff_id → handoffs.decision_refs → decisions 这条单向链，没有一条反查命令。要判断「dec-idea-0007 这条方向到底跑出什么」得手工串三本 jsonl。
  refs: plans/2026-08-16-research-loop-build-plan.md:52, plans/2026-08-16-research-loop-build-plan.md:54, plans/2026-08-16-research-loop-build-plan.md:114
  suggestion: 加一条 `rl decision show ID --with-runs`，把这条决定各版本派出的单子和跑出的 run_id、metrics 一次列全。
  verify_reason: 链条只有单向：build-plan:54 runs 行带 handoff_id，:52 handoffs 带 decision_refs，:48 decisions 带 sources；查询命令 build-plan:108（decision show/list）、:114（handoff show/list）、:120（status）、:122（doctor）里没有一条从决定反查 run 和 metrics。本场景的主动作正是把一批数字对回决定，NOT_IN_DOC。

[F6] where=第 1 步 kind=missing sev_sim=slows sev_verified=cosmetic real=True
  what: 反常预警 monitor 盯数字账，issues 有 kind=anomaly，但这条 issue 的 assignee 归谁、role 字段填什么都没写；monitor 又不是五个角色之一，而 role 只允许取五个角色或 gyb。这批实验刚跑完，第一步 rl status 大概率就撞见这类 issue。
  refs: plans/2026-08-16-research-loop-build-plan.md:50, plans/2026-08-16-research-loop-build-plan.md:46, plans/2026-08-16-research-loop-build-plan.md:158, plans/2026-08-16-research-loop-next-steps.md:115
  suggestion: 明写反常预警开的 issue 是 role=run、assignee=gyb，这样也能顺着 assignee 变 gyb 那条触发通知。
  verify_reason: kind=anomaly 在 build-plan:50 有，反常预警 monitor 在 next-steps:115 和 build-plan:158-159（阈值）有，build-plan:144 只交代了看门狗的判定进 issues 账，反常预警开的 issue 的 role 和 assignee 两份文档都没写；build-plan:46 又规定 role 只能是五个角色或 gyb，monitor 不在其中。确是没写到的字段。不过实现时随便定一个默认值就能走，影响很小。

[F7] where=第 3、14 步 kind=guessed sev_sim=slows sev_verified=cosmetic real=True
  what: 文档从没写「结果出来之后要定下一步」这条路从哪个角色进。我猜的是先开 analysis 出数、再开 idea 落决定；也可以只开 idea 会话直接读 runs 账下判断（idea 的 reads 里就有全部九本账），两条路手续差一半。
  refs: plans/2026-08-16-research-loop-next-steps.md:17, plans/2026-08-16-research-loop-next-steps.md:29, plans/2026-08-16-research-loop-next-steps.md:55, plans/2026-08-16-research-loop-build-plan.md:89
  suggestion: 在入口 skill 的领路那一节写几条常见路线图，头一条就是「一批结果出来之后先 analysis 后 idea」。
  verify_reason: 两份文档确实没写常见路线图的内容：next-steps:119 和 build-plan:205 只说入口 skill 干 init、迁移、领路三件事，「领路」领哪几条路一个字没写；next-steps:17、:29、:55 只写了角色各自的职责，没写「结果出来之后先 analysis 后 idea」这种顺序。属真缺口，但两条路都合法，走错了不出错账。

[F8] where=第 24 步 kind=contradiction sev_sim=slows sev_verified=slows real=True
  what: 施工计划把 idea 和 reviewer 当 subagent 时的模型定成 fable，机器级全局规矩写的是派 subagent 一律不用 Fable、只用 sonnet 或 opus，用户点名那一次才例外。本场景第 24 步 idea 起 deploy subagent 没事，但同一张表在 idea 自己被当 subagent 起的时候就踩规矩。
  refs: plans/2026-08-16-research-loop-build-plan.md:11, plans/2026-08-16-research-loop-build-plan.md:89, /home/y-guo/.claude/CLAUDE.md:6
  suggestion: 把 idea 和 reviewer 的 as_subagent 改成 opus，两处角色 json 一起改。
  verify_reason: 冲突属实：build-plan:11「idea、reviewer 用 fable」，build-plan:89 和 :93 的 as_subagent 列也写 fable；/home/y-guo/.claude/CLAUDE.md:6「一律显式指定模型，默认不用 Fable」、:7「用户明确点名要 Fable 的那一次派发才可以用 Fable」。两份文档里没有任何一句说 gyb 点名过 fable。本场景第 24 步派的是 deploy（opus，不违规），但同一张表在 idea 被当 subagent 起的时候就撞规矩。

[EXTRA0] sev=slows what: gyb 亲自下的方向判断经 idea 会话写进决定账之后，账上分不出是 gyb 定的还是 idea 自己定的：build-plan:46 的 role 记的是写这行的角色（idea），build-plan:106 的 decision update 谁能调写的是「同角色」。而 build-plan:217 的公共规矩第 1 条只把 grants、feedback 裁决、evaluations 批准三类列为「替 gyb 说话的写入」要硬停，决定不在列。于是本场景最重的三条判断（继续/停/换设定）是全套账里唯一没有 gyb 确认关卡的写入。
  refs: plans/2026-08-16-research-loop-build-plan.md:46, plans/2026-08-16-research-loop-build-plan.md:106, plans/2026-08-16-research-loop-build-plan.md:217, plans/2026-08-16-research-loop-next-steps.md:29
  suggestion: decisions 行加一个字段记「这一版是 gyb 当场定的还是角色自决的」，gyb 在场那一版由 idea 写但标出来，reviewer 审的时候才认得出哪条是基准。

[EXTRA1] sev=slows what: 停一条方向要收回的单子不止一张，而且跨角色收不动：next-steps:85 说停就用收回，build-plan:78 规定 withdrawn 只有 from_role 或 gyb 能写。工单是 idea 开的、发射单是 deploy 开的，idea 收不了 deploy 开给 run 的发射单，得 gyb 逐张收。更麻烦的是收回之后下游怎么知道——build-plan:50 只在 issue 的 assignee 变成 gyb 那一版发通知，单子被收回没有任何通知机制，正在跑的 GPU 任务怎么停也没写。
  refs: plans/2026-08-16-research-loop-next-steps.md:85, plans/2026-08-16-research-loop-build-plan.md:78, plans/2026-08-16-research-loop-build-plan.md:112, plans/2026-08-16-research-loop-build-plan.md:50, plans/2026-08-16-research-loop-build-plan.md:142
  suggestion: 加一条 `rl handoff withdraw ID --cascade`，把这张单派生的下游单一并收回并给活着的下游会话发通知；收回带 run 的发射单时按 build-plan:142 的 Phase 6b 留痕。

[EXTRA2] sev=slows what: analysis 按纪律读不到决定账：build-plan:92 的 analysis reads 只有 runs、evaluations 和 handoffs 里的 analysis_order。本场景 gyb 常要「按方向把这几个 run 分组比一比」，analysis 手上只有 run_id 和 metrics，分不出哪几个 run 属于同一条决定。next-steps:109 的读法纪律又要求只读自己需要的那部分，靠越界读补齐是违纪律的。
  refs: plans/2026-08-16-research-loop-build-plan.md:92, plans/2026-08-16-research-loop-build-plan.md:54, plans/2026-08-16-research-loop-next-steps.md:109
  suggestion: analysis 的 reads 加上 decisions.idea 和 handoffs 全本，或者让分析单的 evaluation_refs 旁边带一份 run_id 清单，gyb 开单时就把这批 run 圈好。

[EXTRA3] sev=slows what: 同一个指标名在两处各写一次，没人保证对得上：build-plan:54 的 runs.metrics 是 run 的脚本写的键值，build-plan:60 的 evaluations 带 name 和 code_path（形如 analysis/common/metrics.py:accuracy）。gyb 说要看的那个数到底是 run 已经写进 runs.metrics 的，还是 analysis 现算的，两份文档都没写；两边名字不一致的时候谁改也没写（analysis 改不了 experiments/，只能开 issue 给 deploy，见 build-plan:222）。
  refs: plans/2026-08-16-research-loop-build-plan.md:54, plans/2026-08-16-research-loop-build-plan.md:60, plans/2026-08-16-research-loop-build-plan.md:222
  suggestion: evaluations 行加一个字段写这条口径的取数方式（直接取 runs.metrics 的哪个键，还是走 code_path 现算），doctor 扫一遍 approved 口径里引的 metrics 键在 runs 账里存不存在。

[EXTRA4] sev=cosmetic what: 反常结果预警 monitor 什么时候在跑没定。next-steps:115 只写了看门狗「只在 run 上线时起」，反常预警只写「盯数字账」；build-plan:158-159 给了两个阈值。本场景的数字是实验跑完才落账的，那时 run 会话已经按 next-steps:97 销号了，预警要么没起要么起在别人的会话里。
  refs: plans/2026-08-16-research-loop-next-steps.md:115, plans/2026-08-16-research-loop-next-steps.md:97, plans/2026-08-16-research-loop-build-plan.md:158, plans/2026-08-16-research-loop-build-plan.md:168
  suggestion: 把反常预警定成 rl run finish 那一刻同进程跑的检查，不做常驻 monitor，超阈值当场开 issue；这样也绕开待验证第 3 条（monitor 的 on-skill-invoke 写法）。

 trace_errors: ["第 20 步：merge 的来源只写了 --source run:<run_id>，漏了被合并的旧决定。next-steps:83 写「新决定拿新编号，来源列表指多条旧决定」，build-plan:48 的 merged_from 是「可选」字段，所以指向旧决定的责任落在 sources 上。按 trace 的写法，新决定的来源列表里查不到它是从 dec-idea-0011 和 dec-idea-0012 合来的。", "第 22 步：让 idea 判快车道走不走。next-steps:43 写「deploy 有一个快车道模式，不是新角色」，触发条件、worktree、合回都在 deploy 身上；build-plan:89 idea 的 does/dispatches_to 里没有这一项。文档没给 idea 判快车道的位置。", "第 8 步（连带第 5、6、7 步）：把「gyb 要看一个数」一律走成 analysis 提口径 → gyb 批 → gyb 开 analysis_order。next-steps:75 的口径账是「一行一个指标」、build-plan:60 approved 之后长期有效，已批过的口径不需要重提重批；next-steps:55 又写「gyb 直接开 analysis session 的时候上游填 gyb」，没有一句要求每次分析都先落一张单。这一段手续是模拟者加的，不是文档写的。", "第 19 步把「沿用上一版 sources」当成既定走法写进了 action。文档里没有这句，build-plan:107 的 retire 签名无 --source、build-plan:48 又要求 sources 非空，正确的记法是 NOT_IN_DOC，而不是选一个默认行为往下走。"]

===== CRITIC
{
 "cross_cutting": [
  {
   "what": "写权钩子的工具覆盖面没定：拦不拦 Bash 和被调脚本写出来的文件。next-steps.md:101 只说「写权硬拦，按路径判」，唯一点名工具的是 loop/ 那句「谁都不许直接 Write/Edit」；build-plan.md:185 的测试 8 三个用例全是 Write；build-plan.md:144 又允许 run「经 rl 写 runs 账」（rl 是 Bash 命令），build-plan.md:141 明写 new1 的 ops/runs.jsonl 照旧由 run.py launch 写。管 Bash 则 run 和 deploy 的正常路都跑不动，不管则写权硬拦对一切走 Bash 的写入形同虚设。param-tweak 第 5 到 10 步和 new-idea 第 35 步各卡一次，另外两条跨场景缺口（发射器台账、快车道产物）到底是不是硬冲突也由它决定。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-next-steps.md:101",
    "plans/2026-08-16-research-loop-build-plan.md:185",
    "plans/2026-08-16-research-loop-build-plan.md:144",
    "plans/2026-08-16-research-loop-build-plan.md:141"
   ],
   "suggestion": "在 next-steps.md:101 补一句覆盖面声明：写权钩子只挂 Write 和 Edit，Bash 与被调脚本写出来的文件不拦，靠角色 SKILL.md 的纪律加 rl doctor 事后扫；build-plan.md:185 的测试 8 同时加一个 Bash 写入不被拦的用例把这条钉死。",
   "severity": "blocks"
  },
  {
   "what": "analysis_order 从开单到验收整条链没有交付物定义。build-plan.md:70 给了新建前提（evaluation_refs 且每项已 approved），但 build-plan.md:74 的 in_progress→done_pending_review 那一行只写了 work_order 的 report_paths 和 launch_order 的 actual_seconds，analysis_order 一格空着；build-plan.md:52 的 report_paths 只挂 work_order；next-steps.md:93 讲验收产物通篇讲 deploy 的两份部署报告。配合 build-plan.md:81「表外的转移一律拒收」，这一格是无前提直接放行，analysis 交什么算交、验收人拿什么看、build-plan.md:122 的 doctor 扫什么，都落空。param-tweak 第 34 步、new-idea 第 51 步、plot-new-plan 第 16 步、next-plan-after-results 第 12 步撞的是同一格。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:74",
    "plans/2026-08-16-research-loop-build-plan.md:52",
    "plans/2026-08-16-research-loop-build-plan.md:70",
    "plans/2026-08-16-research-loop-build-plan.md:122",
    "plans/2026-08-16-research-loop-next-steps.md:93"
   ],
   "suggestion": "handoffs 行给 analysis_order 加一栏 output_paths（notebook 路径加图路径列表），build-plan.md:74 那一格填「output_paths 非空且每个路径都存在」，build-plan.md:122 的 doctor 扫描项加一条「analysis_order 的 output_paths 不存在」。",
   "severity": "slows"
  },
  {
   "what": "数字账只能写不能查，也没有能分组的字段。build-plan.md:115 的 runs 那一行只有 rl run add 和 rl run finish 两个写命令，而 decisions（build-plan.md:108）、handoffs（:114）、issues（:110）、evaluations（:118）都配了 show 或 list；next-steps.md:67 又写死九本账「只经 bin/rl 命令进出」，「出」也在内，于是 analysis 和 reviewer 只能直接开 loop/runs.jsonl，还撞 next-steps.md:109 的「大文件禁止整读」。build-plan.md:54 的字段表里没有模型名、数据集、超参这类分组键，build-plan.md:52 和 :54 串起来只有 runs→handoffs→decisions 单向链，没有从决定反查跑了哪些 run 的路。result-wrong-review 第 2 和 10 步、plot-new-plan 第 7 步、next-plan-after-results 第 10 和 17 步都卡在这里。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:115",
    "plans/2026-08-16-research-loop-build-plan.md:108",
    "plans/2026-08-16-research-loop-build-plan.md:114",
    "plans/2026-08-16-research-loop-build-plan.md:54",
    "plans/2026-08-16-research-loop-build-plan.md:52",
    "plans/2026-08-16-research-loop-next-steps.md:67",
    "plans/2026-08-16-research-loop-next-steps.md:109"
   ],
   "suggestion": "命令表补一行 rl run list / rl run show RUN_ID，带 --json 和 --handoff、--decision 两个过滤；build-plan.md:54 的 runs 行加一个 config 字典（模型名、参数量、数据集、split、关键超参）由 run 落账时必填，分组一律取这个字段；build-plan.md:108 的 rl decision show 加 --with-runs 做反查。",
   "severity": "slows"
  },
  {
   "what": "宿主发射器写的三个文件全在写权表外，正常路和快车道都撞。build-plan.md:141 把「new1 的 ops/runs.jsonl 照旧由 run.py launch 写」当既定事实，gpu-run/SKILL.md:80 那一段说 launch 一次写 ops/jobs.json、ops/runs.jsonl 和产物目录 RUNMETA.json 三处；而 next-steps.md:101 明写不给仓库根的 run.py、MAP.md、ops/ 这类文件开白名单、撞到就拦下提醒搬进 experiments/，next-steps.md:163 专门把「按角色开这些白名单」的提议顶回过，build-plan.md:91 给 run 的 writes 也只有 artifact_root 和 runs 账。new-idea 第 35 步（正常路）和 param-tweak 第 8 步（快车道）撞的是同一处。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:141",
    "plans/2026-08-16-research-loop-build-plan.md:91",
    "plans/2026-08-16-research-loop-next-steps.md:101",
    "plans/2026-08-16-research-loop-next-steps.md:163",
    ".claude/skills/gpu-run/SKILL.md:80"
   ],
   "suggestion": "research-loop.json 里把宿主发射器的台账路径单列一栏 launcher.ledger_paths（new1 填 ops/jobs.json、ops/runs.jsonl、产物目录的 RUNMETA.json），钩子对这几条路径按角色放行 run；在 next-steps.md:163 那条旁边注明这是列举式放行，不是给 ops/ 开通用白名单。",
   "severity": "slows"
  },
  {
   "what": "五份角色 json 的 reads 栏按本职缺账，每个角色都缺一样干活必需的东西。build-plan.md:89 的 idea 没有 experiments/，可 next-steps.md:39 把两份部署报告放在 experiments/ 下、next-steps.md:93 又规定验收人默认是 idea；idea 也没有 review/。build-plan.md:92 的 analysis 没有任何 decisions 文件，分不出哪几个 run 属于同一条决定。build-plan.md:93 的 reviewer 没有 handoffs 和 evaluations，而 next-steps.md:61 要它审「实验运行得对不对」（分步表和命令在 handoffs 的 launch 子对象里，build-plan.md:52）和「analysis 的代码是不是 gyb 要的」（批准口径在 evaluations 里，build-plan.md:60）。读权按 next-steps.md:101 不硬拦，所以不会被 deny，但四个场景里角色都在读自己 reads 栏里没有的东西。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:89",
    "plans/2026-08-16-research-loop-build-plan.md:92",
    "plans/2026-08-16-research-loop-build-plan.md:93",
    "plans/2026-08-16-research-loop-build-plan.md:52",
    "plans/2026-08-16-research-loop-build-plan.md:60",
    "plans/2026-08-16-research-loop-next-steps.md:39",
    "plans/2026-08-16-research-loop-next-steps.md:61",
    "plans/2026-08-16-research-loop-next-steps.md:93"
   ],
   "suggestion": "按每个角色的本职动作倒推 reads 再写一遍第五节的表：idea 加 experiments/ 下的部署报告目录和 review/，analysis 加 decisions.idea，reviewer 加 evaluations 和一个裁剪过的派活单视图（rl handoff show ID --for-reviewer，只出 work_type、decision_refs、status、launch 子对象，隐去 report_paths 和 explanation，保住 next-steps.md:63 的对抗性隔离）。",
   "severity": "slows"
  },
  {
   "what": "下游会话销号之后谁把活重新拉起来，没写。next-steps.md:97 规定销号挂在 SessionEnd 和 SubagentStop 上、不指望模型自觉，next-steps.md:91 只写了开单那一刻上游起 subagent。于是 build-plan.md:73 的 stuck→in_progress（回了 issue 的角色或 gyb 写）和 build-plan.md:77 的 rejected→in_progress（to_role 写）这两行的执行者，在原 subagent 已经销号之后都不存在；build-plan.md:52 的 handoffs 行也没有「当前持有会话」字段，build-plan.md:62 的 open_handoffs_at_end 因此算不出来。new-idea 第 22 到 23 步（stuck 捞回）和 result-wrong-review 第 28 步（打回之后）是同一个口子。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-next-steps.md:91",
    "plans/2026-08-16-research-loop-next-steps.md:97",
    "plans/2026-08-16-research-loop-build-plan.md:73",
    "plans/2026-08-16-research-loop-build-plan.md:77",
    "plans/2026-08-16-research-loop-build-plan.md:52",
    "plans/2026-08-16-research-loop-build-plan.md:62"
   ],
   "suggestion": "转移表加一列「转移之后由谁负责起下游会话」，stuck 捞回和 rejected 两行都填 from_role；handoffs 行加一个 holder_session 字段，rl handoff start 时写、销号钩子按它算 open_handoffs_at_end。",
   "severity": "slows"
  },
  {
   "what": "gyb 坐在角色会话里行使不了自己的写权。build-plan.md:99 说 rl 从会话状态文件读角色、--role 只允许裸终端用，build-plan.md:186 的测试写死「非 gyb 调 rl eval approve 退出码 3」，build-plan.md:60 要求 approved 那一版 role 必须是 gyb，:75 的 accepted 只有 from_role 或 gyb 能写，:116 的 grant 只有 gyb。而 next-steps.md:17 要求口径是「gyb 说、analysis 记、gyb 批」、next-steps.md:55 要求 analysis 先问 gyb，gyb 本来就在那个角色会话里说话。plot-new-plan 第 12 和 18 步、next-plan-after-results 第 7、8、13、16 步全靠切到另一个裸终端敲命令，一趟换四次终端。这件事还和 build-plan.md:174 待验证第 9 条（读不到状态文件算不算 gyb）是同一个裁决面。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:99",
    "plans/2026-08-16-research-loop-build-plan.md:186",
    "plans/2026-08-16-research-loop-build-plan.md:60",
    "plans/2026-08-16-research-loop-build-plan.md:75",
    "plans/2026-08-16-research-loop-build-plan.md:116",
    "plans/2026-08-16-research-loop-build-plan.md:174",
    "plans/2026-08-16-research-loop-next-steps.md:17",
    "plans/2026-08-16-research-loop-next-steps.md:55"
   ],
   "suggestion": "会话状态文件加一个 operator 字段，gyb 手动加载角色的会话记 operator=gyb；rl 见到这个字段就放行 gyb 专属子命令（eval approve、handoff accept、grant add、feedback 裁决），账行的 role 记 gyb、session_id 照记当前会话。裁 build-plan.md:174 第 9 条的时候一起定，别分两次。",
   "severity": "slows"
  },
  {
   "what": "要事后回填的两本账没有版本机制，和「只增不改」对不上。build-plan.md:46 只给 decisions、issues、handoffs、feedback、evaluations 五本加了 version，runs（build-plan.md:54）和 sessions（build-plan.md:62）都没有；而 build-plan.md:115 的 rl run finish 要补 exit_status 和 metrics，build-plan.md:104 的 rl session end 要补 ended_at、end_reason、open_handoffs_at_end，next-steps.md:67 又写九本账「只增不改」。param-tweak 的第 27、37 步和 new-idea 的收尾都默认这两本能就地改，文档不支持。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:46",
    "plans/2026-08-16-research-loop-build-plan.md:54",
    "plans/2026-08-16-research-loop-build-plan.md:62",
    "plans/2026-08-16-research-loop-build-plan.md:115",
    "plans/2026-08-16-research-loop-build-plan.md:104",
    "plans/2026-08-16-research-loop-next-steps.md:67"
   ],
   "suggestion": "给 runs 和 sessions 也加 version，rl run finish 和 rl session end 一律追加新版本、默认查询取最新版，跟另外五本一个写法；不想加就在 next-steps.md:67 明写这两本按主键就地改并从「只增不改」里除名，两句必须只留一句。",
   "severity": "slows"
  },
  {
   "what": "rl run add 落第一行的时候不可能有 metrics，和入账校验冲突。build-plan.md:139 规定发射成功后立刻 rl run add 落数字账第一行，build-plan.md:115 的 add 参数里 --metric 是可选的，build-plan.md:187 的测试 10 却写「runs 账 schema：缺 metrics 或 commit 拒收」。param-tweak 第 26 步和 new-idea 第 35 步按字面走都会被入账脚本挡下，而这是 run 角色正常路的第一步。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:139",
    "plans/2026-08-16-research-loop-build-plan.md:115",
    "plans/2026-08-16-research-loop-build-plan.md:187",
    "plans/2026-08-16-research-loop-build-plan.md:54"
   ],
   "suggestion": "把测试 10 拆成两条：add 那一版只校验 run_id、handoff_id、commit 三样，metrics 只在 rl run finish 那一版必填；build-plan.md:54 的字段表里同时标出哪些字段是发射时写、哪些是收尾回填。",
   "severity": "slows"
  },
  {
   "what": "追加版本类命令的 sources 规则没写。build-plan.md:48 规定 decisions 每行 sources 空列表拒收，build-plan.md:180 的测试 3 把这条钉死，next-steps.md:31 也写「至少一项，空列表入账脚本拒收」；而 next-steps.md:82 说废除等于追加一版标 retired，build-plan.md:107 的 rl decision retire ID 签名里没有 --source。build-plan.md:106 的 rl decision update 同样没写 sources 要不要重填、能不能拿自己的上一版当来源，build-plan.md:107 的 merge 也没写被合并的旧编号是进 sources 还是只进 merged_from（build-plan.md:48 说 merged_from 是可选）。next-plan-after-results 第 19 步（停一条方向）和 new-idea 第 7 步（决定改版）撞的是同一条规则。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:48",
    "plans/2026-08-16-research-loop-build-plan.md:106",
    "plans/2026-08-16-research-loop-build-plan.md:107",
    "plans/2026-08-16-research-loop-build-plan.md:180",
    "plans/2026-08-16-research-loop-next-steps.md:31",
    "plans/2026-08-16-research-loop-next-steps.md:82"
   ],
   "suggestion": "明写 update、retire、merge 追加的那一版都带非空 sources：retire 加必填 --source（停一条方向本来就该指着哪个 run 和哪张图停），update 允许 kind=decision 指自己的上一版，merge 的 sources 必须列全被合并的旧编号、merged_from 从可选改成必填。顺带补一条 add 还是 update 的判据：正文改的是同一件事的做法就 update，换了要回答的问题就 add。",
   "severity": "slows"
  },
  {
   "what": "两处 subagent 模型取值和外部规则打架，五份角色 json 现在下不了笔。一处是 run：next-steps.md:47 写「run 要小要快，模型用 sonnet」，build-plan.md:11 写 run、deploy、analysis 用 opus，build-plan.md:3 自己规定冲突以设计文档为准。另一处是 idea 和 reviewer：build-plan.md:11、:89、:93 三处都写 as_subagent 是 fable，而 /home/y-guo/.claude/CLAUDE.md:6 的 Subagent 模型策略写死默认不用 Fable、一律 sonnet 或 opus，:7 说只有用户当次点名才可以用 Fable，两份文档里没有任何一句说 gyb 点过这个名。三个场景各报一次。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-build-plan.md:11",
    "plans/2026-08-16-research-loop-build-plan.md:89",
    "plans/2026-08-16-research-loop-build-plan.md:93",
    "plans/2026-08-16-research-loop-build-plan.md:3",
    "plans/2026-08-16-research-loop-next-steps.md:47",
    "/home/y-guo/.claude/CLAUDE.md:6"
   ],
   "suggestion": "一次改两处：idea 和 reviewer 的 as_subagent 从 fable 改成 opus；run 的取值在 next-steps.md:47 和 build-plan.md:11 之间由 gyb 点一次名，输的那句在原文里划掉并注明被哪一句取代，别让两个值同时留着。",
   "severity": "slows"
  },
  {
   "what": "反常结果预警这个 monitor 没有落点。next-steps.md:115 说 monitors/ 有两个，看门狗只在 run 上线时起、反常预警盯数字账；build-plan.md:158 和 :159 给了两个阈值（指标落在 0 或 1、耗时超预计 3 倍）；build-plan.md:168 的待验证第 3 条只验了看门狗的 on-skill-invoke:run 写法。反常预警跟着谁起没写，而数字是实验跑完才落账的，那时 run 会话按 next-steps.md:97 已经销号。它开的 issue 的 role 和 assignee 也没写：build-plan.md:50 有 kind=anomaly，build-plan.md:46 又规定 role 只能是五个角色或 gyb，monitor 不在其中。result-wrong-review 整条链的起点和 next-plan-after-results 的第 1 步都踩在这个部件上。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-next-steps.md:115",
    "plans/2026-08-16-research-loop-next-steps.md:97",
    "plans/2026-08-16-research-loop-build-plan.md:158",
    "plans/2026-08-16-research-loop-build-plan.md:159",
    "plans/2026-08-16-research-loop-build-plan.md:168",
    "plans/2026-08-16-research-loop-build-plan.md:50",
    "plans/2026-08-16-research-loop-build-plan.md:46"
   ],
   "suggestion": "把反常预警从常驻 monitor 改成 rl run finish 落账时同进程跑的阈值检查，超阈值当场 rl issue open --kind anomaly，role 记 run、assignee 记 gyb，顺着 build-plan.md:50 那条「assignee 变成 gyb 的那一版触发通知」发出去；monitors/ 只留看门狗一个，待验证第 3 条的范围也跟着缩小。",
   "severity": "slows"
  },
  {
   "what": "reviewer 的产出没有回到系统里的路。next-steps.md:59 规定 reviewer 产出只写 review/ 里的问题清单，不开 issue、不派活，动不动由 gyb 看完之后定；next-steps.md:113 只说 review/ 是它的产出目录。九本账里没有一本收这份清单，build-plan.md:120 的 rl status 和 :122 的 rl doctor 扫的都是账，build-plan.md:89 的 idea reads 里也没有 review/。gyb 不主动去开那个目录，清单就没有任何机制再冒出来；清单本身的文件名和字段两份文档也一个字没写。result-wrong-review 第 11 到 14 步和 new-idea 第 54 步是同一处。",
   "doc_refs": [
    "plans/2026-08-16-research-loop-next-steps.md:59",
    "plans/2026-08-16-research-loop-next-steps.md:113",
    "plans/2026-08-16-research-loop-build-plan.md:89",
    "plans/2026-08-16-research-loop-build-plan.md:120",
    "plans/2026-08-16-research-loop-build-plan.md:122"
   ],
   "suggestion": "rl status 的输出加一行「review/ 下有 N 份清单，最新一份是几号写的」，和改派给 gyb 的 issue 并列；review/ 加进 idea 的 reads；common/ 母版里放一份清单模板（一条问题四栏：决定编号加版本、代码位置、对不上在哪、建议动作），文件名定成 review/<日期>-<决定编号>.md。",
   "severity": "slows"
  }
 ],
 "duplicates": [
  "analysis_order 没有交付物和验收前提：param-tweak 第 34 步、new-idea 第 51 到 52 步、plot-new-plan 第 16 步、next-plan-after-results 第 12 步，四条报的都是 build-plan.md:74 那一行 analysis_order 的前提格空着加 next-steps.md:93 只定义了部署报告。",
  "数字账没有查询命令：result-wrong-review 第 2 和 10 步、plot-new-plan 第 7 步、next-plan-after-results 第 10 和 17 步，三个场景四条报的都是 build-plan.md:115 只有 rl run add 和 rl run finish，对 next-steps.md:67 的「只经 bin/rl 命令进出」。",
  "写权钩子管不管 Bash 写入：param-tweak 第 5 到 10 步和 new-idea 第 35 步，两条报的都是 next-steps.md:101 没写覆盖面加 build-plan.md:185 的测试全是 Write 用例。",
  "宿主发射器的三个台账文件撞写权表：param-tweak 第 8 步（快车道）、param-tweak extra 第 4 条（正常路）、new-idea extra 第 3 条（run.py 注册表），三条根子都在 build-plan.md:141 对 next-steps.md:101 和 :163。",
  "idea 和 reviewer 的 as_subagent 写成 fable：new-idea 第 9、29、46 步、result-wrong-review 第 21 步、next-plan-after-results 第 24 步，三个场景报的都是 build-plan.md:11 对 /home/y-guo/.claude/CLAUDE.md:6。",
  "run 的 subagent 模型 sonnet 还是 opus：param-tweak extra 第 1 条和 new-idea 第 29 步，两条报的都是 next-steps.md:47 对 build-plan.md:11，裁决规则同在 build-plan.md:3。",
  "runs 和 sessions 两本账要事后回填却没有 version：param-tweak extra 第 2 条和 new-idea 的 trace_error 第 3 条，指的都是 build-plan.md:46 只给五本账加 version，对 build-plan.md:54、:62 和 next-steps.md:67。",
  "rl run add 第一行没有 metrics 与测试 10 冲突：param-tweak extra 第 3 条加 trace_error 第 2 条、new-idea extra 第 4 条加 trace_error 第 5 条，四处指的都是 build-plan.md:139、:115、:187 三行自相矛盾。",
  "gyb 坐在角色会话里行使不了 gyb 权：plot-new-plan 第 12 和 18 步、next-plan-after-results 第 7、8、13、16 步，报的都是 build-plan.md:99 加 build-plan.md:60、:75、:116 的「谁能写」限定。",
  "反常结果预警 monitor 没有落点：result-wrong-review extra 第 5 条和 next-plan-after-results extra 第 5 条加 friction 第 7 条，指的都是 next-steps.md:115 只写「盯数字账」加 build-plan.md:158 到 :159 的阈值没有执行位置。",
  "下游 subagent 销号之后谁重新起：new-idea 第 22 到 23 步（stuck 捞回）和 result-wrong-review extra 第 2 条（打回之后），报的都是 next-steps.md:91 只写了开单那一刻起 subagent，对 build-plan.md:73 和 :77 两行的执行者。",
  "review/ 的清单没有回路：result-wrong-review 第 11 到 14 步和 new-idea extra 第 7 条，报的都是 next-steps.md:59 的产出不进任何账，对 build-plan.md:120 和 :122 扫不到、build-plan.md:89 的 idea 也读不到。",
  "reviewer 和 analysis 的 reads 缺账：result-wrong-review 第 7 到 9 步（reviewer 没有 handoffs 和 evaluations，build-plan.md:93）、next-plan-after-results extra 第 3 条（analysis 没有 decisions，build-plan.md:92）、new-idea extra 第 1 条（idea 没有 experiments/，build-plan.md:89），三条是同一张表按本职漏项。",
  "同一个指标名在 runs.metrics 和 evaluations.code_path 两处各写一次、谁算的没裁：plot-new-plan extra 第 4 条和 next-plan-after-results extra 第 4 条，指的都是 build-plan.md:54 对 build-plan.md:60 和 :220。"
 ],
 "missing_scenarios": [
  {
   "scenario": "跑到一半挂了：run 发射之后任务崩掉，或者看门狗判死，发射单要收场。",
   "why_it_matters": "build-plan.md:142 只说 Phase 6b 把发射单标 stuck 并开 issue 给 deploy，而 build-plan.md:72 要求 in_progress→stuck 时 issue_id 和那条 issue 的 handoff_id 互相指；同时 build-plan.md:74 规定 launch_order 进 done_pending_review 只要 actual_seconds 已填加 runs 账里有对应 handoff_id 的行，build-plan.md:54 的 exit_status 又允许 failed 和 killed。一次挂掉的跑两条路的字面条件都满足得了，走一遍才知道该停在哪个状态、失败的 runs 行算不算数。"
  },
  {
   "scenario": "一次开 N 张发射单，一个 workflow 起 N 个 run subagent 各接一张。",
   "why_it_matters": "next-steps.md:47 和 build-plan.md:137 把这条写成常规做法，五个场景全是单 run。N 个 run 会话同时追加 runs 账和 issues 账正是 next-steps.md:67 那把锁要挡的事（测试在 build-plan.md:178），而 build-plan.md:114 的 rl handoff list 只有 --status 和 --mine、build-plan.md:120 的 rl status 只按状态和时长列，一批单子没有任何字段能归组；其中一张挂了另外几张怎么办也没写。"
  },
  {
   "scenario": "决定改了一版，已经派出去的单子还在办。",
   "why_it_matters": "next-steps.md:85 定的是单子按派出时那一版继续做、rl 只标过时、停不停由 gyb 点名，next-steps.md:84 要角色上线第一件事跑过版检查，build-plan.md:109 给了 rl decision stale。可是 build-plan.md:120 的 rl status 不列过版单子，next-steps.md:70 的通知只在 issue 改派给 gyb 时发，「gyb 点名」这一步没有任何东西叫得动 gyb，这条设计到底空不空转要走一遍才看得出。"
  },
  {
   "scenario": "gyb 手动接单：上游只开单，gyb 自己开 session 干下游的活。",
   "why_it_matters": "next-steps.md:91 把它写成两种接单方式之一，五个场景没有一个完整走过。build-plan.md:71 要求 todo→in_progress 的写入会话角色等于 to_role，build-plan.md:99 说 rl 从状态文件读角色，于是 gyb 必须先加载那个角色 skill；接完之后这个会话在 sessions 账里 model 记 inherit 还是记真实模型（build-plan.md:62、:104、:85），验收人还是不是 from_role（build-plan.md:75），都只有走一遍才定得下来。"
  },
  {
   "scenario": "两条 idea 线并行推进，两批单子和两批数字同时在账上。",
   "why_it_matters": "next-steps.md:69 把 decisions 拆成五个文件的理由就是并行不撞车，但 handoffs、issues、runs 仍是单文件（build-plan.md:26 到 :27）。build-plan.md:114 的 rl handoff list 只有 --status 和 --mine，build-plan.md:120 的 rl status 只列状态和挂了多久，两条线的单子混在一张表里没有字段能分开，gyb 每天开工第一眼看的就是这张表。"
  },
  {
   "scenario": "角色提 feedback、gyb 裁、改插件母版这一整轮。",
   "why_it_matters": "next-steps.md:97 明写框架要随着用一起改、定时提醒叫 gyb 看 feedback 账，build-plan.md:223 的规矩七禁止角色自改母版只许提 feedback，build-plan.md:58 和 :117 给了完整字段和四个命令。五个场景一条 feedback 都没提过；feedback 裁成 accepted 之后谁去改 common/ 里的母版、改完在跑的会话怎么知道规矩变了，两份文档都没接上。"
  },
  {
   "scenario": "idea 要读 notes/ 里的文献调查，申请一次授权。",
   "why_it_matters": "next-steps.md:15 规定 idea 要经 gyb 允许才有读文献的权限，build-plan.md:56 的 permission 第一版只有 read:notes，build-plan.md:116 的 rl grant add 只有 gyb 能调。命令表里没有 idea 发起申请的那一条，next-steps.md:101 又说读权一律不硬拦，这条授权到底拦住了谁、idea 该开 issue 还是直接读，走一遍才看得出它是不是纯装饰。"
  },
  {
   "scenario": "gyb 定期跑回收命令收拾很久没动的会话和单子。",
   "why_it_matters": "next-steps.md:19 把定期回收列进 gyb 亲自做的五件事，next-steps.md:97 说钩子漏掉的全靠它兜底，build-plan.md:121 给了 rl reclaim、build-plan.md:156 到 :157 给了 48 小时和 72 小时两个阈值。--apply 会按 build-plan.md:79 那一行把 in_progress 的单子交回 todo，交回之后谁接、已经写了一半的代码和产物算什么，一次都没演过。"
  },
  {
   "scenario": "subagent 上下文满或被中断，销号钩子没触发，单子挂在死会话名下。",
   "why_it_matters": "next-steps.md:97 说销号挂 SessionEnd 和 SubagentStop 就是因为不能指望模型自觉调结束命令，而 build-plan.md:170 的待验证第 5 条同时写着这个机制还没验、失败备案是「全靠 rl reclaim，提醒周期从 7 天缩到 1 天」。备案生效那条路上 build-plan.md:62 的 open_handoffs_at_end 根本写不出来，这是设计里唯一一处自己承认可能不工作的兜底。"
  },
  {
   "scenario": "run 的 smoke 直接失败，一步都还没跑起来。",
   "why_it_matters": "next-steps.md:49 规定 run 接单第一件事是跑 smoke，build-plan.md:144 规定 smoke 失败一律 rl issue open 给 deploy、不修代码不重试。这一刻发射单上还没有分步表和 estimated_seconds（build-plan.md:52 里这两样是 smoke 时才由 rl handoff estimate 填的），单子按 build-plan.md:72 转 stuck 要不要先补这些字段没写，而 smoke 失败是 gpu-run/SKILL.md:45 里的常见事。"
  },
  {
   "scenario": "rl doctor 扫出一堆问题之后的收拾。",
   "why_it_matters": "build-plan.md:122 列了六类扫描结果（编号重复、引用悬空、stuck 单子没有 issue、没人引用的 issue、报告路径不存在、runs 行没有对应发射单），build-plan.md:183 的测试 6 还专门造了一条没人引用的 issue。可是 build-plan.md:101 到 :123 整张命令表里没有一条修的命令，账本又按 next-steps.md:67 只增不改，扫出来之后能做什么是空的。"
  },
  {
   "scenario": "在 new1 本仓库第一次跑 rl init。",
   "why_it_matters": "build-plan.md:206 的步 7 明写 init 要在 new1 跑一遍、loop/ 要长出来，next-steps.md:103 说 init 往仓库的 CLAUDE.md 追加裸会话纪律那一句。new1 的 CLAUDE.md 已经有「跑任务统一从 run.py 进」和三层记账那几条规矩，build-plan.md:10 又裁定老代码由 gyb 手动按需搬、入口 skill 不做全量搬迁，两套规矩落在同一个 CLAUDE.md 上、两本 runs 账并存（build-plan.md:141），只有真走一遍才看得见冲突在哪。"
  }
 ]
}```
