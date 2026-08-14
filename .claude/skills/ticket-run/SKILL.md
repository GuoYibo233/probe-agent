---
name: ticket-run
description: 成批执行 .scratch/<功能名>/issues/ 里工单的唯一入口——主会话按 Blocked by 把工单分成波，每波发射一个 workflow，波内工单并行（每张一棵独立 git 工作树、一条独立分支），workflow 内部按"实现 → 评审 → 修复循环（上限 5 轮）"跑每张工单，分支合并、收账、裁决、终审回主会话。Invoke whenever Dungeon♂Master says "执行工单"、"清 ticket"、"把这批 issue 做了"、"按 spec 实施"、"execute tickets"、or a batch of .scratch issues needs implementing.
version: 1.0.0
---

# ticket-run — 工单成批执行的全生命周期

拼法来源：过程骨架抄 superpowers 的 subagent-driven-development（每任务一个全新实现者
+ 每任务一道评审 + 修复循环上限 5 轮 + 最后整分支终审），控制流交给 Workflow 工具的
确定性脚本（循环上限、门禁、断点续跑都写死在 JS 里，不靠主会话自觉），实现纪律
（TDD 于接缝、常跑单测、最后全量、逐单元 commit）写死在实现者规程里。

固定路径：
- 波脚本：`.claude/skills/ticket-run/wave.js`
- 角色规程：`.claude/skills/ticket-run/prompts/{implementer,reviewer,re-reviewer,final-reviewer}.md`
- 工单约定：`docs/agents/issue-tracker.md`；状态字符串：`docs/agents/triage-labels.md`
- 每波报告目录：`.scratch/<功能名>/sdd/<日期>-wave<N>/`（进 git，是评审记录的一部分）

## Phase 0 — 分波

1. 读 `.scratch/<功能名>/spec.md` 和 `issues/` 下全部工单。
2. 可执行集合 = 用户点名的工单；用户没点名就取 `Status: ready-for-agent` 的全部。
3. 按每张工单的 `Blocked by:` 行建依赖图，切成波：第 1 波 = 无未完成前置的工单，
   第 2 波 = 只依赖第 1 波的工单，依此类推。
4. 每张工单建一个 todo，备注波号和 Blocked by。todo 只是本会话的视图，
   真源永远是工单文件的 `Status:` 行——会话断了就从文件重建分波。

每波装 2 到 4 张工单。一张工单最坏要花 12 次 agent 调用
（1 次实现 + 1 次评审 + 5 轮修复，每轮 1 修 1 复审），波装太大一次 workflow 就超预算。

## Phase 1 — 预检与发射前 commit

1. 预检扫一遍：工单之间互相矛盾、工单与 spec 矛盾、工单要求的做法撞仓库铁律
   （绕过 run.py 注册表、往 home 写大产物、手改 RESULTS.md），全部攒成一个批量问题
   一次问完用户再动。扫不出问题就不出声直接往下走。
2. 工作树必须干净，未提交的先 commit（仓库铁律：发射前 commit，否则记录追不回代码）。
3. 建本波报告目录，把本波每张工单的 `Status:` 改成 `claimed`，连同报告目录一起 commit。

## Phase 2 — 发射一波

用 Workflow 工具发射，脚本定死控制流：

```
Workflow({
  scriptPath: ".claude/skills/ticket-run/wave.js",
  args: {
    repo: "/home/y-guo/reproduce/new1",
    feature: "<功能名>",
    wave: "<日期>-wave<N>",
    promptDir: "/home/y-guo/reproduce/new1/.claude/skills/ticket-run/prompts",
    reportDir: "/home/y-guo/reproduce/new1/.scratch/<功能名>/sdd/<日期>-wave<N>",
    tickets: [{ id: "01", path: ".scratch/<功能名>/issues/01-xxx.md" }, ...]
  }
})
```

三条定死在脚本里、不许在发射时改掉的规则：
- 波内工单并行，一张工单内部严格串行。每张工单的改动全部落在自己的分支
  `ticket/<波名>/T<NN>` 上，agent 在仓库旁边的 `<repo>-wt/` 下自建工作树、
  用完即删（git 的各工作树共享对象库，所以评审在主仓用 sha 就取得到 diff）。
  发射后主仓工作树谁都不动，代码合并等收账时做。工作树只用 git 命令建和进，
  派发消息里明令禁调 EnterWorktree 工具——subagent 调它会吊死不返回，
  wave3 和 wave9 各挂过一次（wave9 吊了 6 小时才被发现）。
  卡住的判法：读 workflow 目录下 agent-*.jsonl 的末行时间戳，
  停滞半小时以上就 TaskStop 后按下面的 resumeFromRunId 续跑。
- 每个 agent 的模型显式写死：实现和评审用 sonnet，修复第 4、5 轮升级 opus。
  不传模型就会继承主会话的 Fable，这条撞 subagent 禁 Fable 的硬规则。
- 修复循环上限 5 轮，到顶就带着未决 findings 返回，脚本不做裁决。

workflow 在后台跑，等完成通知。中途挂了或要改脚本，用 tool result 里的 runId
配 `resumeFromRunId` 续跑，已完成的工单命中缓存不会重跑；返回值可疑先读
transcript 目录的 `journal.jsonl` 再下判断。

## Phase 3 — 收账（每波返回后）

workflow 返回逐工单的结构化结果（含各自的分支名）。先合并代码，再做状态账：

1. `DONE` 的工单按工单号顺序逐个 `git merge --no-ff ticket/<波名>/T<NN>`。
   合并起冲突就停下报告用户——冲突本身说明这两张工单并不独立，分波分错了。
2. `CAP_TRIPPED` 的分支先不合，等下面的裁决做完再决定合并还是弃掉。
3. 清理：合并完删掉已合分支，`git worktree prune`，`<repo>-wt/` 下的残留目录删掉。

然后按状态处理每张工单：

- `DONE`：工单 `Status:` 改 `resolved`，在工单 `## Comments` 下追加一条：
  commit 范围、修复轮数、遗留 minors、实现者 concerns。
- `CAP_TRIPPED`（5 轮打满还有未决 findings）：主会话逐条裁决——评审错了就搁置并写明理由，
  真问题但没人依赖也搁置，真问题且后续工单要在上面盖楼就停下报告用户。
  裁决逐条写进工单 Comments，不许静默丢弃。
- `BLOCKED` / `NEEDS_CONTEXT`：缺的是上下文就补齐后把这张工单单独再发一波；
  缺的是用户决策就把 `Status:` 改 `ready-for-human` 并上报。
  工单要用 GPU 的活会以 BLOCKED 回来（实现者被禁止发射 GPU 进程），主会话走 gpu-run。
- `cannotVerify` 清单（评审在 diff 里查不了的项）：主会话自己核对，
  核实是真缺口就当 findings 把这张工单再发一波修复。

收完账 commit 一次（工单状态行 + Comments + 报告目录），然后发下一波，直到波清空。

## Phase 4 — 终审与汇报

全部波完成后做一次整分支终审，单个 agent 不用 workflow：

1. 用 Agent 工具派 opus，prompt 指向 `prompts/final-reviewer.md`，
   给它起点 commit（第一波发射前的 HEAD）、终点 HEAD、spec 路径、
   全部工单路径、收账攒下的 minors 与搁置清单。
2. 终审有 findings：派一个 sonnet 修复 agent 一次修完整个清单（不许一条一个 agent），
   再派一次范围限定的复审。残余的按 Phase 3 的 CAP_TRIPPED 规则裁决。
3. 汇报用户：每张工单的最终状态与 commit 范围、搁置清单、终审结论。只摆事实不带评语。

## 铁律接线

- 实现者规程里已写死：run.py 注册表三件套同 commit、大产物只写 NFS、uv 管环境、
  禁发 GPU 进程、禁手改 RESULTS.md。评审会当 spec 缺口抓，但主会话收账时再核一遍。
- 本 skill 管的是代码工单。工单本身要跑 GPU 实验的，实施部分照常走本 skill，
  发射部分回主会话走 gpu-run。
- 改了本 skill 的流程或脚本，按仓库规矩回写本文件，同一个 commit。
