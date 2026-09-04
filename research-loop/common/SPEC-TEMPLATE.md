# Role skill template: the five sections every role SKILL.md follows

<!-- Sources: 09 L15 (five sections, ruled 2026-08-18, carried over from the 2026-08-15 five-column spec), 09 L27 (the tools section is one pointer to the role json; no copies of common/ text, only "follow common/"), 08 L89 (the header declares no hooks), 09 L53 and 06 L29 (two discipline sentences copied into every role skill), 06 L258-L260 (what research-loop/tests/test_skill_refs.py checks), 10 L36 (use-case table columns follow principle-05). -->

A role SKILL.md is the third layer of constraint (principle-02): everything the hook and ledger validation do not enforce lives there as discipline. Every role skill follows this template so that gyb, reviewer and the machine check `research-loop/tests/test_skill_refs.py` can read five skills the same way.

## Header
The frontmatter carries `name` and `description`. It declares no hooks: a hook declared in a skill header governs only the top-level session, and a subagent's calls never pass through it (08 L89, verified item 8), so the write hook lives at plugin level instead.

## Section 1: Role definition
What the role does, what it does not do, who starts a session of it, and which model runs it when started as a subagent.

## Section 2: Use cases
A table with four columns: use case; ledgers and directories read; directory written; `rl` write commands. Each row is one use case, and the role json's four columns are derived from these rows, never the other way round (principle-05). Below the table, one short paragraph per use case in working order.

## Section 3: Available tools
Exactly one sentence pointing to `research-loop/tables/roles/<role>.json`. The json's four columns (`reads`, `writes`, `ledger_writes`, `dispatches_to`) are never copied into the skill: a copy would go stale the first time feedback changes the json.

## Section 4: Constraints
Discipline the machine does not enforce: reading order, what may be written outside the role directory and how to report it, when to open an issue and to whom, when to stop and ask gyb, dispatch targets. Two sentences appear verbatim in every role skill, copied from `common/GLOBAL-RULES.md` (rule-08 and the un-numbered discipline; 06 L29, 09 L53) so that the machine check can recognize them as the two permitted copies (proxy decision D-08):

1. Writes the hook cannot see (a script writing files internally, `python -c`, heredocs, any Bash command whose target path the hook cannot parse) never go into the four role directories or `loop/`; to write there use Write/Edit or a Bash form the hook can see, and ledgers only ever go through `rl`.
2. One session loads one role. To switch roles, open another session. The machine does not enforce this; what happens on a second load in the same session is undefined and has no fallback.

The section ends with the line "Follow `common/`." and copies nothing else from `common/`.

## Section 5: Output style
What the role delivers and the shape of each deliverable.

## Token convention
This section is a construction convention of `research-loop/tests/test_skill_refs.py`, not a ruling from the design parts, which list four kinds of names to check (06 L260): PENDING(proxy decision). Inside a role skill, every `rl` command, ledger name, status value, directory path and glossary term is written in backticks. The machine check extracts backticked tokens and verifies each one against its definition site: commands against `research-loop/tables/commands.json`, ledger names against `research-loop/tables/ledgers.json`, status values against the schemas and the transition table, directories against the role jsons, remaining terms against `common/GLOSSARY.md`. A name that exists nowhere fails the check, which is the point: an invented command or state in a skill is a bug the model would otherwise act on.
