export const meta = {
  name: 'ticket-wave',
  description: '一波无相互依赖的工单并行执行：每张在自己的 git 工作树分支上走实现-评审-修复循环（上限5轮），返回逐工单分支与结果，分支合并由主会话收账时做',
}

// args 契约（全部必填）：
//   repo: 仓库根绝对路径
//   feature: 功能名（.scratch/<feature>/）
//   wave: 波名（如 20260808-wave1），用于分支名与工作树目录名
//   promptDir: 角色规程目录绝对路径
//   reportDir: 本波报告目录绝对路径（主会话已建好）
//   tickets: [{ id: '01', path: '.scratch/<feature>/issues/01-xxx.md' }, ...]
//
// 并行设计：工单之间并行（parallel），一张工单内部严格串行
// （实现 → 评审 → 修复轮），改动全部落在 ticket/<wave>/T<id> 分支上，
// 工作树建在仓库旁边的 <repo>-wt/ 下，agent 用完即删。主仓工作树谁都不碰。
//
// 模型写死：实现/评审/修复1-3轮 sonnet，修复4-5轮 opus。
// 不许省略 model —— 省略会继承主会话的 Fable，撞 subagent 禁 Fable 硬规则。
const M = { impl: 'sonnet', review: 'sonnet', escalate: 'opus' }
const MAX_ROUNDS = 5

const FINDING = {
  type: 'object',
  required: ['id', 'severity', 'title', 'detail'],
  properties: {
    id: { type: 'string' },
    severity: { enum: ['critical', 'important', 'minor'] },
    title: { type: 'string' },
    detail: { type: 'string' },
    file: { type: 'string' },
  },
}

const IMPL_SCHEMA = {
  type: 'object',
  required: ['status'],
  properties: {
    status: { enum: ['DONE', 'DONE_WITH_CONCERNS', 'NEEDS_CONTEXT', 'BLOCKED'] },
    base: { type: 'string', description: '分支起点 sha（建工作树前的主仓 HEAD）' },
    head: { type: 'string', description: '分支最后一个 commit 的 sha；没 commit 就等于 base' },
    testSummary: { type: 'string', description: '跑了什么测试命令、结果一行' },
    concerns: { type: 'array', items: { type: 'string' } },
    reason: { type: 'string', description: 'NEEDS_CONTEXT/BLOCKED 时：缺什么、卡在哪' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['findings', 'cannotVerify'],
  properties: {
    findings: { type: 'array', items: FINDING },
    cannotVerify: { type: 'array', items: { type: 'string' } },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  required: ['head', 'testEvidence'],
  properties: {
    head: { type: 'string' },
    testEvidence: { type: 'string', description: '覆盖被改代码的测试：命令 + 结果' },
    notes: { type: 'string' },
  },
}

const REREVIEW_SCHEMA = {
  type: 'object',
  required: ['verdicts', 'newFindings'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'verdict'],
        properties: {
          id: { type: 'string' },
          verdict: { enum: ['ADDRESSED', 'NOT_ADDRESSED'] },
          note: { type: 'string' },
        },
      },
    },
    newFindings: { type: 'array', items: FINDING },
  },
}

// 有的运行时把 args 以 JSON 字符串送达（对象属性静默变 undefined），这里先归一化
const A = typeof args === 'string' ? JSON.parse(args) : args

const P = A.promptDir
const branchOf = t => `ticket/${A.wave}/T${t.id}`
const wtPath = (t, suffix) => `${A.repo}-wt/${A.wave}-T${t.id}${suffix}`

const implPrompt = (t, report) =>
  `先读实现者规程 ${P}/implementer.md 并严格照做。\n` +
  `本单任务：工单文件 ${A.repo}/${t.path}，它是唯一需求源，先读它；` +
  `它引用 spec 的段落再去读 .scratch/${A.feature}/spec.md 对应节。\n` +
  `工作树协议（并行执行，必须照办）：在 ${A.repo} 里先 git rev-parse HEAD 记为 base，` +
  `然后 git worktree add ${wtPath(t, '')} -b ${branchOf(t)} 建出你自己的工作树和分支，` +
  `所有改动、测试、commit 只发生在这个工作树里；主仓工作树一个文件都不许动。` +
  `工作树只用 Bash 里的 git 命令建和进（后续命令带工作树绝对路径或 git -C），` +
  `禁止调用 EnterWorktree 工具——从 subagent 调它会吊死不返回（wave3、wave9 各挂过一次）。` +
  `收尾把工作树里的东西 commit 干净后 git worktree remove ${wtPath(t, '')}，分支留着。\n` +
  `完整报告写到 ${report}（主仓里的绝对路径，直接写）。commit 消息前缀 T${t.id}:。\n` +
  `返回结构化字段（status/base/head/testSummary/concerns/reason）。`

const reviewPrompt = (t, report, base, head) =>
  `先读评审规程 ${P}/reviewer.md 并严格照做。\n` +
  `仓库根：${A.repo}。被审工单：${A.repo}/${t.path}；实现者报告：${report}。\n` +
  `diff 在分支 ${branchOf(t)} 上，范围 ${base}..${head}——工作树共享对象库，` +
  `直接在主仓用 git log --oneline / git diff --stat / git diff -U10 取，不要建工作树，只读不改。\n` +
  `双裁决：spec 合规逐条对照工单要求，缺口记 critical finding；代码质量另查。\n` +
  `finding 的 id 用 F1、F2 顺序编号。返回 findings 与 cannotVerify 两个清单。`

const fixPrompt = (t, report, open, round) =>
  `先读实现者规程 ${P}/implementer.md。这是工单 T${t.id} 的修复第 ${round} 轮：` +
  `此前的实现者已做过这张工单，你现在接手。\n` +
  `工单：${A.repo}/${t.path}。先读 ${report} 了解已经做了什么、试过什么。\n` +
  `工作树协议：在 ${A.repo} 里 git worktree add ${wtPath(t, `-fix${round}`)} ${branchOf(t)} ` +
  `把已有分支检出到你自己的工作树；如果报 already checked out，说明上一轮的工作树没删干净，` +
  `先 git worktree prune，还不行就对那个残留路径 git worktree remove --force 再重试。` +
  `所有改动只发生在这个工作树里，修完 commit 到分支（前缀 T${t.id}:），` +
  `然后 git worktree remove ${wtPath(t, `-fix${round}`)}。` +
  `工作树只用 Bash 里的 git 命令操作，禁止调用 EnterWorktree 工具（会吊死不返回）。\n` +
  `未决 findings（逐条修掉，不许扩大范围重构）：\n${JSON.stringify(open, null, 2)}\n` +
  `修完重跑覆盖被改代码的测试，把修复报告（含每条 finding 怎么修的、测试命令与输出）` +
  `追加到 ${report}。返回 head 与 testEvidence。`

const reReviewPrompt = (t, report, open, fixBase, head) =>
  `先读复审规程 ${P}/re-reviewer.md 并严格照做。\n` +
  `仓库根：${A.repo}。工单：${A.repo}/${t.path}；报告（含修复记录）：${report}。\n` +
  `修复 diff 在分支 ${branchOf(t)} 上，范围 ${fixBase}..${head}，在主仓直接取，只读不改。只做两件事：` +
  `对下列 findings 逐条判 ADDRESSED/NOT_ADDRESSED，另把修复 diff 本身引入的新问题记 newFindings。\n` +
  `待判 findings：\n${JSON.stringify(open, null, 2)}\n` +
  `newFindings 的 id 自取，保证不与待判清单里的 id 重复即可。`

async function runTicket(t) {
  const ph = `T${t.id}`
  const report = `${A.reportDir}/T${t.id}-report.md`
  const branch = branchOf(t)

  log(`T${t.id} 实现开始（分支 ${branch}）`)
  const impl = await agent(implPrompt(t, report), {
    label: `impl:T${t.id}`, phase: ph, model: M.impl, schema: IMPL_SCHEMA,
  })
  if (!impl) return { id: t.id, status: 'AGENT_LOST', stage: 'impl', branch }
  if (impl.status === 'NEEDS_CONTEXT' || impl.status === 'BLOCKED') {
    return { id: t.id, status: impl.status, branch, reason: impl.reason || '', concerns: impl.concerns || [] }
  }

  const review = await agent(reviewPrompt(t, report, impl.base, impl.head), {
    label: `review:T${t.id}`, phase: ph, model: M.review, schema: REVIEW_SCHEMA,
  })
  if (!review) {
    return { id: t.id, status: 'REVIEW_LOST', branch, commits: { base: impl.base, head: impl.head }, concerns: impl.concerns || [] }
  }

  let open = review.findings.filter(f => f.severity !== 'minor')
  const minors = review.findings.filter(f => f.severity === 'minor')
  let head = impl.head
  let round = 0

  while (open.length && round < MAX_ROUNDS) {
    round++
    const model = round >= 4 ? M.escalate : M.impl
    log(`T${t.id} 修复第 ${round} 轮，未决 ${open.length} 条`)
    const fix = await agent(fixPrompt(t, report, open, round), {
      label: `fix${round}:T${t.id}`, phase: ph, model, schema: FIX_SCHEMA,
    })
    if (!fix) break
    const rr = await agent(reReviewPrompt(t, report, open, head, fix.head), {
      label: `rereview${round}:T${t.id}`, phase: ph, model: M.review, schema: REREVIEW_SCHEMA,
    })
    head = fix.head
    if (!rr) break
    const addressed = new Set(rr.verdicts.filter(v => v.verdict === 'ADDRESSED').map(v => v.id))
    open = open.filter(f => !addressed.has(f.id))
    for (const nf of rr.newFindings) {
      if (nf.severity === 'minor') minors.push(nf)
      else open.push(nf)
    }
  }

  const status = open.length ? 'CAP_TRIPPED' : 'DONE'
  log(`T${t.id} 结束：${status}，修复 ${round} 轮`)
  return {
    id: t.id,
    status,
    branch,
    commits: { base: impl.base, head },
    rounds: round,
    openFindings: open,
    minors,
    cannotVerify: review.cannotVerify,
    concerns: impl.concerns || [],
  }
}

// 工单之间并行；parallel 把抛异常的 thunk 归成 null，这里补回工单身份
const raw = await parallel(A.tickets.map(t => () => runTicket(t)))
const results = raw.map((r, i) => r || { id: A.tickets[i].id, status: 'AGENT_LOST', branch: branchOf(A.tickets[i]) })

return { feature: A.feature, wave: A.wave, tickets: results }
