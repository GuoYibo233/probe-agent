export const meta = {
  name: 'ticket-wave',
  description: '一波无相互依赖的工单串行执行：每张走实现-评审-修复循环（上限5轮），返回逐工单结构化结果',
}

// args 契约（全部必填）：
//   repo: 仓库根绝对路径
//   feature: 功能名（.scratch/<feature>/）
//   promptDir: 角色规程目录绝对路径
//   reportDir: 本波报告目录绝对路径（主会话已建好）
//   tickets: [{ id: '01', path: '.scratch/<feature>/issues/01-xxx.md' }, ...]
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
    base: { type: 'string', description: '动工前的 git HEAD（完整或短 sha）' },
    head: { type: 'string', description: '最后一个 commit 的 sha；没 commit 就等于 base' },
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

const P = args.promptDir

const implPrompt = (t, report) =>
  `先读实现者规程 ${P}/implementer.md 并严格照做。\n` +
  `仓库根：${args.repo}。本单任务：工单文件 ${t.path}，它是唯一需求源，先读它；` +
  `它引用 spec 的段落再去读 .scratch/${args.feature}/spec.md 对应节。\n` +
  `动工前先 git rev-parse HEAD 记为 base。完整报告写到 ${report}。\n` +
  `commit 消息前缀 T${t.id}:。返回结构化字段（status/base/head/testSummary/concerns/reason）。`

const reviewPrompt = (t, report, base, head) =>
  `先读评审规程 ${P}/reviewer.md 并严格照做。\n` +
  `仓库根：${args.repo}。被审工单：${t.path}；实现者报告：${report}。\n` +
  `diff 范围：${base}..${head}（git log --oneline / git diff --stat / git diff -U10 自己取）。\n` +
  `双裁决：spec 合规逐条对照工单要求，缺口记 critical finding；代码质量另查。\n` +
  `finding 的 id 用 F1、F2 顺序编号。返回 findings 与 cannotVerify 两个清单。`

const fixPrompt = (t, report, open, round) =>
  `先读实现者规程 ${P}/implementer.md。这是工单 T${t.id} 的修复第 ${round} 轮：` +
  `此前的实现者已做过这张工单，你现在接手。\n` +
  `仓库根：${args.repo}。工单：${t.path}。先读 ${report} 了解已经做了什么、试过什么。\n` +
  `未决 findings（逐条修掉，不许扩大范围重构）：\n${JSON.stringify(open, null, 2)}\n` +
  `修完重跑覆盖被改代码的测试，把修复报告（含每条 finding 怎么修的、测试命令与输出）` +
  `追加到 ${report}，逐单元 commit（前缀 T${t.id}:）。返回 head 与 testEvidence。`

const reReviewPrompt = (t, report, open, fixBase, head) =>
  `先读复审规程 ${P}/re-reviewer.md 并严格照做。\n` +
  `仓库根：${args.repo}。工单：${t.path}；报告（含修复记录）：${report}。\n` +
  `修复 diff 范围：${fixBase}..${head}。只做两件事：` +
  `对下列 findings 逐条判 ADDRESSED/NOT_ADDRESSED，另把修复 diff 本身引入的新问题记 newFindings。\n` +
  `待判 findings：\n${JSON.stringify(open, null, 2)}\n` +
  `newFindings 的 id 自取，保证不与待判清单里的 id 重复即可。`

const results = []

for (const t of args.tickets) {
  const ph = `T${t.id}`
  const report = `${args.reportDir}/T${t.id}-report.md`

  log(`T${t.id} 实现开始`)
  const impl = await agent(implPrompt(t, report), {
    label: `impl:T${t.id}`, phase: ph, model: M.impl, schema: IMPL_SCHEMA,
  })
  if (!impl) { results.push({ id: t.id, status: 'AGENT_LOST', stage: 'impl' }); continue }
  if (impl.status === 'NEEDS_CONTEXT' || impl.status === 'BLOCKED') {
    results.push({ id: t.id, status: impl.status, reason: impl.reason || '', concerns: impl.concerns || [] })
    continue
  }

  const review = await agent(reviewPrompt(t, report, impl.base, impl.head), {
    label: `review:T${t.id}`, phase: ph, model: M.review, schema: REVIEW_SCHEMA,
  })
  if (!review) {
    results.push({ id: t.id, status: 'REVIEW_LOST', commits: { base: impl.base, head: impl.head }, concerns: impl.concerns || [] })
    continue
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

  results.push({
    id: t.id,
    status: open.length ? 'CAP_TRIPPED' : 'DONE',
    commits: { base: impl.base, head },
    rounds: round,
    openFindings: open,
    minors,
    cannotVerify: review.cannotVerify,
    concerns: impl.concerns || [],
  })
  log(`T${t.id} 结束：${open.length ? 'CAP_TRIPPED' : 'DONE'}，修复 ${round} 轮`)
}

return { feature: args.feature, tickets: results }
