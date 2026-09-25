# T03 registry — owner-ruling round 1

Ticket: `.scratch/from-zero/issues/03-registry-and-ledger.md`
Branch: `ticket/2026-09-18-wave4/T03-alias-ruling`
Base: `d1a4e60ffb50436bd4a8d7e8a3df5b194e71fe54`
Head: `08d31a83331082502c840f5c05cd62ab7a08e09b`

## Owner rulings applied, round 1

### RULING-6 — `_alive_on` canonicalises the host through the alias column

**What changed.** `jobs/registry.py`'s `_alive_on` tested `host in
sessions.failed_hosts` on the raw host string a piece's row carries, while
`sessions.failed_hosts` (built by `live_sessions()`) is filled with canonical
`hosts:` names. A piece recorded under its cluster alias (`tokyo105` answers to
`shiga`, `tokyo108` to `saitama`) on a host whose probe failed was therefore
reported alive instead of dead, breaking 3.4's fail-closed rule.
`jobs/launch._piece_alive` already canonicalises the same comparison through
`_canonical_host`. The fix makes `_alive_on` do the same, in place, before the
`failed_hosts` membership test — one function, no special case, nothing else in
the file touched:

```diff
 def _alive_on(host: str | None, session: str | None, sessions: set) -> bool:
     if not host or not session:
         return False
-    if isinstance(sessions, _ProbedSessions) and host in sessions.failed_hosts:
-        return True
+    if isinstance(sessions, _ProbedSessions):
+        cfg = _outputs_config()
+        if _canonical_host(host, cfg) in sessions.failed_hosts:
+            return True
     return session in sessions
```

**Commands and their real output.**

A1, the import check, rerun under the three interpreters and system `python3`
(all from the worktree root):

```
$ for P in "$PR" "$AW" "$VL"; do
    $P -c "import sys; sys.path.insert(0,'.'); from jobs import registry as r; print(r.DEFAULTS['launch_timeout_s'], r.DEFAULTS['stall_line'])"
  done
1800 180
1800 180
1800 180
$ python3 -c "import sys; sys.path.insert(0,'.'); from jobs import registry; print('sys ok')"
sys ok
```

The wave-4 seam check for RULING-6, run under `external/probe-env/bin/python`
with `registry._outputs_config` stubbed in-process to a fabricated `hosts:`
block (`{name: tokyo105, alias: shiga, cards: 8}`), never touching the real
`constants/path_outputs.yaml`:

```
alias-vs-canonical (expect True): True
neither failed nor holding (expect False): False
present session (expect True): True
present session via alias (expect True): True
```

- `failed_hosts = {"tokyo105"}` (the canonical name), piece recorded on host
  `"shiga"` (its alias) → `_alive_on` reports alive (`True`). This is the
  ruling's exact scenario.
- A piece on a host that is neither failed nor holding the session (`sessions2`
  holds only `"other-session"` on `tokyo106`, `failed_hosts` empty, piece host
  `"tokyo107"`) → reports not alive (`False`).
- A piece whose session is genuinely present, addressed both by the canonical
  name (`tokyo105`) and by the alias (`shiga`) → reports alive (`True`) in both
  spellings, so the ruling changes only the fail-closed path and leaves the
  ordinary "session present" path unchanged.

Supporting checks (unaffected by the change, rerun to confirm nothing else
broke):

```
$ grep -n "/home/\|/net/" jobs/registry.py || echo NO_ABS_PATH
NO_ABS_PATH
$ "$PR" tests/test_registry_concurrent_append.py
----------------------------------------------------------------------
Ran 1 test in 0.198s

OK
$ git status --porcelain jobs/
 M jobs/registry.py
```

Only `jobs/registry.py` is modified; no real `jobs/runs.jsonl` or
`jobs/RESULTS.md` was written by any check (the seam check pointed
`registry._outputs_config` at a fabricated `hosts:` block inside the running
process and never touched `constants/path_outputs.yaml` or the ledger files on
disk).

**README.md.** No line needed a change: the fix adds no import, no new read or
write target, and the module docstring is untouched.

**Commit.** `ticket/2026-09-18-wave4/T03-alias-ruling`, one commit:
`T03: alias ruling round 1 - _alive_on canonicalises host before the
failed_hosts test (RULING-6)`.

**Open questions.** None. The ruling was unambiguous and the fix is a single
in-place change to the one function it names.
