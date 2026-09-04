# tables/ - machine-readable copies of the design parts

Every file in this directory is a transcription of a table that already exists in
`plans/research-loop-parts/` (the design parts). Nothing here is invented: each
field carries a `_source` (or the file carries a `_sources` map) pointing at the
part and line it was copied from, written as `06 L178` (part 06, line 178) or
`sync-inbox Q41(c) L294` (sync-inbox question 41 item c, line 294; sync-inbox line
numbers are as of commit b7bec26, the question and item letters are the stable part). Anything the
parts have not ruled is marked `PENDING(issue NN)` / `PENDING(part 22 L113)` and
listed in `_pending`, so the final merge pass can grep for it.

## Files

| file | copied from | used by |
|---|---|---|
| `ledgers.json` | 03 L45-57 (nine ledgers), 03 L9 / 08 L18 (plain files), 39(c) | `rl_lib` paths, test 13 ledger names |
| `roles/<role>.json` | 06 L172-234 (five role tables), 06 L236-250 (model column) | write hook (`writes`), ledger validation (`ledger_writes`), test 13 (`reads`, `ledger_writes`) |
| `commands.json` | 05 L31-96 (command table), 05 L98-102 (query/write split) | `rl_lib.COMMANDS`, `bin/rl` dispatch, test 13 command existence |
| `transitions.json` | 04 L53-78 (the transition table), plus Q41(b)(c), Q43(e), Q45 | ledger validation of handoffs, test 2 |
| `gyb-usecases.json` | 01 L98-114 | `rl status` sections, list filters (step 4) |
| `exit_codes.json` | 03 L215-228 | every `rl` exit |
| `config_defaults.json` | 08 L38-79 (keys and thresholds), 07 L132-139 | `rl init`, thresholds read by `rl_lib` |

## Construction conventions (not rulings; each one is a code shape chosen to carry a ruling)

1. **Command names** are the `rl` sub-command spelled as it is typed, without the
   `rl` prefix: `handoff open`, `decision add`, `trace`, `status`. Flag-only write
   forms of `doctor` are listed literally: `doctor --ack`, `doctor --unack`,
   `doctor --list-acks`.
2. **`ledger_writes`** in a role file is an object keyed by ledger name. The value
   is either the string `"*"` (every write command whose `ledger` in
   `commands.json` is that ledger) or a list of full command names. `decisions`
   is keyed per book (`decisions.idea`), matching 06's wording "decisions.idea, all".
3. **`reads`** follows 06 L164: a ledger is written by its English name
   (`decisions.<role>` for decision books), a directory as a repo-relative path
   with a trailing slash, a file as a repo-relative path.
4. **Preconditions** in `transitions.json` are `{id, text, source}` objects. The
   `id` names the check that `rl_lib` implements; the `text` is an English
   rendering of the part's sentence; the `source` points back to the sentence.
5. **Row keys.** The skeleton field `id` is named `run_id` in runs, `ql_tag` in
   scratch and `session_id` in sessions (03 L35, L104, L180, L200); `ledgers.json`
   records the key name per ledger.
6. **Session identity.** `rl` reads its own session id from the environment
   variable `CLAUDE_CODE_SESSION_ID` (present in this session's Bash), and tests
   override it with `RL_SESSION_ID`. Whether the hook input's `session_id` equals
   this variable was verify item 1, closed on 2026-09-05: the two are equal
   (`plans/2026-09-05-research-loop-verify.md` section 2.7).
7. **Environment variables `rl` reads** (names fixed here so hook, tests and library agree):
   `RL_SESSION_ID` overrides the session id (tests); `RL_CALLER=hook` marks the plugin
   hook's own calls to `session start` / `session end` (who column "hook, gyb", 05 L40);
   `RL_COMMON_DIR` points at a sandbox copy of `common/` (tests); `RL_AGENT_TYPE` and
   `RL_AGENT_ID` are injected by the write hook into a subagent's Bash commands so `rl`
   can tell a subagent from its parent session (verify item 5, proxy decision D-15;
   `plans/2026-09-05-research-loop-verify.md` sections 2.4-2.5 and 4: `agent_type` is
   `research-loop:<role>` from the plugin's agents/, bare `<role>` from `--agents`, both
   accepted). The
   injection is `export RL_AGENT_TYPE='<type>'; export RL_AGENT_ID='<id>'; <command>`
   (shell-escaped), never a prefix assignment, so chained commands (`cd x && rl ...`)
   still see the variables (D-15 addendum).
8. **Opening version = version 1.** 03 L211 separates "the open, merged and dropped
   versions" from "middle versions that append numbers"; the schemas tell the opening
   version from a middle one by `version == 1`. Same reading for the quick-lane
   supplement's `ql_tag` (04 L31).
9. **Where `rl` comes from.** The plugin's SessionStart hook appends
   `export PATH="$CLAUDE_PLUGIN_ROOT/bin:$PATH"` to the file named by `CLAUDE_ENV_FILE`
   (Claude Code hooks reference, https://code.claude.com/docs/en/hooks, SessionStart
   section on `CLAUDE_ENV_FILE`; verified in `plans/2026-09-05-research-loop-verify.md`
   2.5 that only SessionStart hooks see that variable), so every later Bash call of the
   session and of its subagents (same environment, verify.md 2.4) can type bare `rl`.
   Skills therefore write bare `rl ...`; if the hook is not installed the fallback is the
   full path `${CLAUDE_PLUGIN_ROOT}/bin/rl` (proxy decision D-21). `rl init` writes no
   alias and touches neither host code nor `.claude/` (08 L13).
10. **`writes` outside the repo.** A `writes` entry that is not a repo path (run's
   `artifact_root`, 06 L203) is descriptive only: the hook lets every path outside the
   repo through (06 L13), so the hook never consults it.

11. **Bash write targets the hook reads.** 06 L70 names redirections, `tee`, `sed -i`,
    `mv`/`cp`; the hook also reads the targets of `install`, `rsync`, `touch`, `mkdir`,
    `rm`, `truncate`, `dd` (stricter, same two blocked kinds). Anything else is
    discipline (06 L29).
12. **`--json` of `decision update/retire/merge`** carries `affected`: a list of
    `{"id", "holder"}` for the open orders citing an older version (02 L87 says they are
    printed; the key name is a construction convention).

13. **Injection changes permission matching.** After the D-15 injection a subagent's
    Bash command starts with `export ...;`, and Claude Code matches permission rules
    against the rewritten command (hooks reference), so prefix-style allow rules written
    for bare commands no longer match inside subagents.

14. **Extra keys on `rl status --json` rows.** Beyond the twelve keys of 01 L135 a row may
    carry `stale_holder` (true when the row is listed in section 7) so scripts and tests
    can tell section membership without parsing text; adding keys is allowed by 05 L123
    ("add fields, never remove").

15. **`--reason` is parsed once.** bin/rl strips the five global flags (`--json`,
    `--as-gyb`, `--quote`, `--force`, `--reason`) before dispatch; handlers whose
    signature also has `--reason` (`handoff reject/withdraw`, `ql close --dropped`,
    `session end`) read it from the global options, so one `--reason` serves both the
    command and a `--force` on the same call.

## Readings that go beyond the letter of a part (ruled by proxy decisions D-10, D-11, D-12; gyb reviews the record)

- `track` on a `work_order` is required at open (sync-inbox Q45(a)(f): filled by idea at open;
  proxy decision D-10); a `launch_order` copies it into `attempts[0].track`.
- The feedback `id` has no shape in 03 L145 (it only says "feedback id"); the schema uses `fb-NNNN`
  by analogy with `iss-NNNN` (proxy decision D-11).
- `grants` stays a named ledger with no schema and no commands (proxy decision
  D-01, `PENDING(issue 43c)`).
- `commands.json`, `exit_codes.json` and `config_defaults.json` are containers the parts did not
  name; their content is transcription (proxy decision D-12).
