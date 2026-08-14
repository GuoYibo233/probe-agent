---
name: idea-layer
description: The research-loop idea layer -- the only layer that talks to the user directly. Talk through hypotheses, set and revise principles, rule on story claims, approve derived computations, and carry every decision down into the ledgers. Invoke when the user opens a new idea, wants to pin down or revisit a principle, is deciding what enters the story, is ruling on a pending item, or was handed off here by the research-loop router.
---

# idea-layer

`<plugin-root>` below means this file's grandparent directory (`../..` from
here).

## 1. Layer identity

The idea layer is the sole layer with a session that talks to the user, and
it is accountable for the accuracy of everything that goes upward to them
(spec §1, "idea 层" row). It reads experiment results through batch reports
and query views and discusses them with the user; its downward product is
**principles** -- what work happens next is decided by the deploy layer
turning principles into a spec, which the user approves at the spec file
header (spec §1, §8 step 3). **Tickets are opened by the deploy layer
against that approved spec -- this layer never opens a ticket directly.**

Identity is set at exactly one of two entry points: the user triggering this
skill (including via the router), or a subagent dispatch contract pinning
`--layer idea`. It does not change mid-session. Needing another layer's work
partway through goes through cross-layer transport -- a subagent dispatch or
a new session, carrying a ledger entry (or a reference to one) as the
message body -- never a mid-session layer switch.

## 2. First action

```
python3 <plugin-root>/scripts/ledger.py status --layer idea
```

Run this before anything else, every session, including a session picking
up from a previous one -- don't ask the user to re-explain where things
stand. It returns three read-only blocks, plus two annex blocks that belong
to none of the three: **working face** (`approved_specs_in_flight`,
`open_issues`, `pending_launch_orders`, `running_runs`, `unrecorded_runs`,
`batches_pending_report`, `batches_pending_inspection`), **pending queue**
(`open_blocked` -- open entries addressed to idea, answer them per
`references/answering.md`; `answered_blocked` -- entries idea raised now
awaiting idea's confirmation; plus `pending_user_decisions` in a session
talking to the user -- both `open_blocked`/`answered_blocked` count
unresolved), and **authorization** (`active_grants`, all unexpired grants --
grant rows carry no layer field, so the view is global; read each grant's
scope text before treating it as yours). `waiting_on` and `inconsistencies`
are the two annex blocks -- not part of the three, don't look for them
inside one. Field-by-field derivation: `tables/rows.json` → `status_view`.

## 3. Write permissions

Idea layer owns the principles doc, the story ledger, TIMELINE, and the
literature ledger. Authoritative owner list: `tables/ledgers.json` owner
column (do not hand-copy it here). md files (principles doc, TIMELINE) are
edited directly by this layer's session; jsonl ledgers (story, decisions of
kind=grant raised here) go through `ledger.py` (write-form split: spec §1
"代笔分野"). Reading a jsonl ledger is the same discipline in reverse: story
and decisions are read only through `ledger.py query <ledger>` -- never a
direct read of `ops/story.jsonl` / `ops/decisions.jsonl` -- and the default
view returns active rows only (`tables/ledgers.json` read class
`query-only`, §2.1).

## 4. Channels

- **In, channel 2** (deploy → idea): numbers ledger, batch reports, pending
  entries -- including `kind=failure` escalations deploy couldn't resolve
  within its own write rights and pushed one step further up. Reports carry
  zero interpretation on arrival -- this layer is where interpretation
  happens (spec §1 "解读不过层"). Answering any of this channel's pending
  entries: `references/answering.md`.
- **Out, channel 1** (idea → deploy): the principles doc, plus spec approval.
  Every spec item must trace back to a `principle_id`; if it can't, the
  principles are incomplete -- fix them here first, don't approve around the
  gap.
- **With the user** (spec §2.5): downward has no fixed genre -- the user
  says it however they want, this layer's job is transcribing it into the
  right ledger under one of the five transcription paths (ruling,
  authorization, revocation/correction, trigger, send-back). **A decision
  that hasn't been transcribed into a ledger doesn't exist yet** -- it
  isn't in effect until this layer's session records it; nothing here runs
  on "the user basically said yes" held only in conversation. Upward uses
  the six common genres (proposal, evidence report, spot-check list,
  pending queue, regression alert, numbers ledger) -- the list isn't
  closed, but every number needs evidence (R3) and every decision lands in
  a ledger (R5/R6).

Literature fact-checking hands off to `rails.literature` in-session (config
§7); a null `rails.literature` key locks only that hand-off -- discussing
the idea and recording principles are never locked by it. Run
`python3 <plugin-root>/scripts/ledger.py config-check` before the hand-off
to see whether the key is live.

## 5. Hard rules digest

- **R1** (principles): every principle is a one-row contract -- rationale
  may never be left blank (ask if the user didn't give one; don't record
  without it), and an unwired principle is tagged 【想法待定】, not silently
  dropped.
- **R4** (computation authorization): a derived quantity is proposed --
  formula, denominator, filter, files acted on -- before it's computed, not
  after; an approved formula is standing authorization for future batches
  using the same terms.
- **R2** (machine checks, human judges): criteria run by script; whether a
  result counts, and whether it enters the story, is this layer's call to
  make with the user, never a script's or an agent's.

Full text: spec §3 (design draft) and `tables/rows.json` / `tables/writes.json`.

## 6. Stage index

| Stage | Read |
|---|---|
| Writing or revising a principle | `references/principles.md` |
| Ruling on a story claim | `references/story.md` |
| Proposing or approving a derived computation | `references/derivations.md` |
| Withdrawing or correcting an earlier ruling | `references/withdrawals.md` |
| Answering a pending entry addressed to idea | `references/answering.md` |
