# Wave 7 precheck (2026-09-20, session new1-08)

One opus reader checked tickets 17 and 18 against the tree at be60c4c. It ran
ticket 17's C7, C8 and C15 as written: every hit comes from a file ticket 17
edits, none from a file neither ticket edits. The corrections below were applied
to the ticket bodies in commit 1e1dda9.

Blocks acceptance:

1. Ticket 17 C5 expected 34 Python files; the tree has 31 (the `eval/methods/`
   fold, errata line 181, never reached ticket 17).
2. Ticket 18 C9 could never print `ok-noref`: `constants/path_models.yaml` lines
   12 and 15 cite `legacy train_causal_tool.py`. The file joined ticket 18's list.
3. Ticket 17 section 4 named fewer lines than C15 flags (`handoff/SKILL.md` 52,
   `paper-write/SKILL.md` 83, `ticket-run/SKILL.md` 48 and 142). The
   every-occurrence rule of section 2 now covers section 4.
4. Ticket 18 section 0 said three renamed files; `docs/` tracks five, and
   `docs/adr/` is absent.
5. Ticket 18 C16 expected `ok-no-bare-docs-path` inside a worktree that lacks
   ticket 17's edits. The grep is now expected to print there, and the main
   session requires the clean result after the merge.

Minor, applied: the list of unedited `.md` files under `.claude/` is eight, not
four; three of the four prompts are already identical; the line edits to
`ticket-run/prompts/implementer.md` are moot because the file is overwritten;
`exp-status/SKILL.md` line 135 is an `ops/runs.jsonl` line; C11 covers seven
documents; C8's `named:` line is a subset; ticket 18 names the two dropped
`.gitignore` rules (`*.feather`, the `envs/runs/**` block); `tests` joined C9's
grep; "on top" in `notes/TIMELINE.md` means above the newest entry, below the
header; `CLAUDE.md` is written with the Write tool because the read-only hook
refuses a Bash command that carries the model table's file name with a write word.

Dispatch: ticket 17 runs alone as this wave's first dispatch. Ticket 18 waits for
the owner's answers (whether the `data/*_format.py` rename runs before or after
it; what deleting `legacy/` gives up) and for the rest of the GPU list.
