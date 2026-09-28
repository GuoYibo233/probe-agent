# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`notes/CONTEXT.md`** — the glossary; this repo has one context and keeps no ADR directory.

Decisions live in `notes/TIMELINE.md` and `notes/plans/`; an agent reads them and never edits them.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `notes/CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it in your report for the owner to add).

## Flag decision conflicts

If your output contradicts a decision recorded in `notes/TIMELINE.md`, surface it explicitly rather than silently overriding:

> _Contradicts the TIMELINE entry of <date> (<decision>) — but worth reopening because…_
