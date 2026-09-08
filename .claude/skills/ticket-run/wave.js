export const meta = {
  name: 'ticket-wave',
  description: 'Parallel execution of a wave of tickets with no mutual dependencies: each ticket runs an implement-review-fix loop (capped at 5 rounds) on its own git worktree branch, returns per-ticket branches and results; branch merging happens when the main session does settlement',
}

// args contract (all required):
//   repo: absolute path to the repo root
//   feature: feature name (.scratch/<feature>/)
//   wave: wave name (e.g. 20260808-wave1), used in the branch name and worktree directory name
//   promptDir: absolute path to the role-protocol directory
//   reportDir: absolute path to this wave's report directory (already created by the main session)
//   tickets: [{ id: '01', path: '.scratch/<feature>/issues/01-xxx.md' }, ...]
//
// Parallel design: tickets run in parallel (parallel); within one ticket everything is strictly serial
// (implement -> review -> fix rounds); all changes land on the ticket/<wave>/T<id> branch,
// the worktree is built under <repo>-wt/ next to the repo, and the agent deletes it when done. Nobody touches the main repo's worktree.
//
// Model is hardcoded: sonnet for implement/review/fix rounds 1-3, opus for fix rounds 4-5.
// Never omit model -- omitting it inherits the main session's Fable, which hits the subagent-no-Fable hard rule.
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
    base: { type: 'string', description: 'branch start sha (the main repo HEAD before creating the worktree)' },
    head: { type: 'string', description: 'sha of the branch\'s last commit; equals base if there is no commit' },
    testSummary: { type: 'string', description: 'what test command ran, one line of results' },
    concerns: { type: 'array', items: { type: 'string' } },
    reason: { type: 'string', description: 'for NEEDS_CONTEXT/BLOCKED: what is missing, where it is stuck' },
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
    testEvidence: { type: 'string', description: 'tests covering the changed code: command + result' },
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

// Some runtimes deliver args as a JSON string (object properties silently become undefined); normalize it here first
const A = typeof args === 'string' ? JSON.parse(args) : args

const P = A.promptDir
const branchOf = t => `ticket/${A.wave}/T${t.id}`
const wtPath = (t, suffix) => `${A.repo}-wt/${A.wave}-T${t.id}${suffix}`

const implPrompt = (t, report) =>
  `Read the implementer protocol at ${P}/implementer.md first and follow it strictly.\n` +
  `This ticket's task: the ticket file is ${A.repo}/${t.path}, the sole source of requirements -- read it first; ` +
  `for any spec section it references, read the matching section of .scratch/${A.feature}/spec.md.\n` +
  `Worktree protocol (parallel execution, mandatory): in ${A.repo}, first run git rev-parse HEAD and record it as base, ` +
  `then run git worktree add ${wtPath(t, '')} -b ${branchOf(t)} to create your own worktree and branch, ` +
  `all changes, tests, and commits happen only in this worktree; do not touch a single file in the main repo's worktree. ` +
  `Create and enter the worktree only with git commands in Bash (later commands carry the worktree's absolute path or use git -C); ` +
  `calling the EnterWorktree tool is forbidden -- calling it from a subagent hangs and never returns (it happened once each in wave3 and wave9). ` +
  `At the end, commit everything in the worktree cleanly, then run git worktree remove ${wtPath(t, '')}; keep the branch.\n` +
  `Write the full report to ${report} (an absolute path in the main repo; write it there directly). Prefix commit messages with T${t.id}:.\n` +
  `Return the structured fields (status/base/head/testSummary/concerns/reason).`

const reviewPrompt = (t, report, base, head) =>
  `Read the review protocol at ${P}/reviewer.md first and follow it strictly.\n` +
  `Repo root: ${A.repo}. Ticket under review: ${A.repo}/${t.path}; implementer's report: ${report}.\n` +
  `The diff is on branch ${branchOf(t)}, range ${base}..${head} -- worktrees share the object store, ` +
  `so get it directly in the main repo with git log --oneline / git diff --stat / git diff -U10; do not create a worktree, read only, make no changes.\n` +
  `Two-part ruling: check spec compliance item by item against the ticket's requirements and record any gap as a critical finding; check code quality separately.\n` +
  `Number finding ids sequentially as F1, F2, .... Return two lists: findings and cannotVerify.`

const fixPrompt = (t, report, open, round) =>
  `Read the implementer protocol at ${P}/implementer.md first. This is fix round ${round} for ticket T${t.id}: ` +
  `an earlier implementer already worked this ticket, and you are taking over now.\n` +
  `Ticket: ${A.repo}/${t.path}. Read ${report} first to see what has already been done and tried.\n` +
  `Worktree protocol: in ${A.repo} run git worktree add ${wtPath(t, `-fix${round}`)} ${branchOf(t)} ` +
  `to check the existing branch out into your own worktree; if it reports already checked out, the previous round's worktree was not cleaned up, ` +
  `so run git worktree prune first, and if that does not fix it, run git worktree remove --force on that leftover path and retry. ` +
  `All changes happen only in this worktree; once the fix is done, commit it to the branch (prefix T${t.id}:), ` +
  `then run git worktree remove ${wtPath(t, `-fix${round}`)}. ` +
  `Operate the worktree only with git commands in Bash; calling the EnterWorktree tool is forbidden (it hangs and never returns).\n` +
  `Open findings (fix each one; do not refactor beyond scope):\n${JSON.stringify(open, null, 2)}\n` +
  `Once the fix is done, rerun the tests covering the changed code, and append the fix report (how each finding was fixed, test commands and output) ` +
  `to ${report}. Return head and testEvidence.`

const reReviewPrompt = (t, report, open, fixBase, head) =>
  `Read the re-review protocol at ${P}/re-reviewer.md first and follow it strictly.\n` +
  `Repo root: ${A.repo}. Ticket: ${A.repo}/${t.path}; report (with the fix record): ${report}.\n` +
  `The fix diff is on branch ${branchOf(t)}, range ${fixBase}..${head}; get it directly in the main repo, read only, make no changes. Do exactly two things: ` +
  `judge each of the following findings ADDRESSED or NOT_ADDRESSED, and record any new problem introduced by the fix diff itself as newFindings.\n` +
  `Findings awaiting judgment:\n${JSON.stringify(open, null, 2)}\n` +
  `Pick ids for newFindings yourself, just make sure they do not repeat ids already in the pending list.`

async function runTicket(t) {
  const ph = `T${t.id}`
  const report = `${A.reportDir}/T${t.id}-report.md`
  const branch = branchOf(t)

  log(`T${t.id} implementation started (branch ${branch})`)
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
    log(`T${t.id} fix round ${round}, ${open.length} open findings`)
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
  log(`T${t.id} finished: ${status}, ${round} fix rounds`)
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

// Tickets run in parallel; parallel turns a throwing thunk into null, so restore the ticket identity here
const raw = await parallel(A.tickets.map(t => () => runTicket(t)))
const results = raw.map((r, i) => r || { id: A.tickets[i].id, status: 'AGENT_LOST', branch: branchOf(A.tickets[i]) })

return { feature: A.feature, wave: A.wave, tickets: results }
