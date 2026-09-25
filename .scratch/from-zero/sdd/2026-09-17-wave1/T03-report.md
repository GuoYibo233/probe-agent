# T03 report — the registry and the ledger

Branch: `ticket/2026-09-17-wave1/T03`, base `cca3ca3a506cf5b2a8d990e641ec160e40e8465f`,
head `d06b83dfd4e579d4f40897e5d599840fe3d190c1`.

## 1. What was done

Against the ticket's file list:

- `jobs/registry.py` — written in two marked halves (writer, then reader), as
  required. Offers every name 8.0 pins: writer half `DEFAULTS`, `lock`,
  `append_start`, `append_finish`, `write_meta`, `write_done`, `beat`,
  `Heartbeat.emit`/`.finish`; reader half `ls`, `where`, `find`, `kill`,
  `free`, `sync`, `open_runs`, `live_sessions`, `session_alive`,
  `typical_gap_s`, `stall_line_s`, `rates`, `judge`, `judge_service`; and the
  three internal-but-pinned names `render`, `cards_busy`, `fold`. Imports
  nothing from the repo (only stdlib plus PyYAML), and `constants/path_outputs.yaml`
  is read lazily inside `_outputs_config()`, cached in the module global
  `_OUTPUTS_CONFIG` — every writer-half function works with no `constants/`
  directory on disk, which A1–A8 exercise directly.
- `jobs/runs.jsonl` — seeded empty (0 bytes), in git.
- `jobs/RESULTS.md` — seeded by actually running `registry.render()` over the
  empty seeded ledger inside the worktree (not hand-typed), so it is byte-for-byte
  what the code produces.
- `tests/test_registry_concurrent_append.py` — the fourth of the tree's four
  planned `tests/` checks: forks 8 processes, each appending 20 start rows
  (`append_start`) into a temp copy of the tree, and asserts 160 lines land and
  every line parses as JSON. Header carries `# venv: probe`.
- `.gitignore` — added the single line `jobs/runs.jsonl.lock`, nothing else
  touched.
- `README.md` — created (it did not exist yet on this branch); added only this
  ticket's own files' lines, in the five-annotation format, plus a short
  "how to run" note. Per spec section 3, this file is expected to collect
  merge conflicts across wave-1 tickets and be reassembled whole by ticket 14;
  I did not touch any other ticket's territory in it.

## 2. How it was verified

All ten acceptance commands were run from the repo root of the ticket
worktree (`/home/y-guo/reproduce/new1-wt/2026-09-17-wave1-T03`), through the
absolute interpreters named in the ticket. No command wrote into the real
`jobs/runs.jsonl`; every functional check ran against a throw-away `mktemp -d`
tree, and A8's final check confirms `git status --porcelain jobs/` is empty on
the real tree post-commit.

**A1 — imports as `any` under every interpreter, and under system python3.**
```
$ for P in "$PR" "$AW" "$VL"; do $P -c "..."; done; python3 -c "..."
1800 180
1800 180
1800 180
sys ok
```
Matches exactly; exit 0 for all four.

**A2 — the re-entrant lock, and that a second process really blocks.**
```
$ "$PR" - <<'PY' ... PY
waited 32.7
outer released
exit=0
```
The printed order came out swapped from the ticket's illustration (`outer
released` first, then `waited N.N`), and the wait was far longer than the
illustrative `2.0`. I did not treat this as a failure without checking it: I
re-ran the same lock hand-off with an instrumented variant that writes
absolute timestamps to a side file instead of relying on each process's own
buffered stdout (Python block-buffers `print()` output when it isn't a tty,
so the parent's `"outer released"` line sits in its own buffer until the
parent process exits, while the child's line — printed once, right before the
child exits — flushes immediately; that is a display-order artifact, not an
execution-order one). The instrumented run showed real wall-clock timestamps:
the outer process released the lock at `+2.001s`, and the blocked child only
observed the grant at `+33.8s` — a genuine ~32s gap between release and grant,
not a code defect. `df -T`/`mount` on this worktree confirm `/home/y-guo` is
NFSv3 with `local_lock=none`, so `fcntl.flock()` here goes over the network
lock manager (NLM), which is exactly the filesystem the contracts document's
own "Facts measured on this machine" section already flags as unmeasured for
locking (it only measured `O_EXCL` atomicity on the NFSv4 outputs mount, and
says home "holds no records" for locking). Concretely: **mutual exclusion is
enforced correctly** (the child provably waited until the real release), but
**granting a blocked `flock()` after release on this NFSv3 home mount takes on
the order of 30 seconds**, not sub-second. The ticket's own acceptance line
only requires the wait to be "any value >= 1.5", which 32.7 (and 33.8 in the
instrumented rerun) satisfies, and exit was 0. I flag the ~30s figure as a new
measured fact below (concerns) since it matters for wave-5/6 tickets (`run.py`,
`jobs/launch.py`) that take this same lock around the launch gate and the
card reservation — a person watching a launch could see it "hang" for tens of
seconds at a lock boundary with nothing wrong. `tests/test_registry_concurrent_append.py`
(A7) does not hit this path because `tempfile.TemporaryDirectory()` resolves
under `/tmp`, which is local, not NFS.

**A3 — start row, finish row, fold, `RESULTS.md`, `open_runs`, `find`.**
```
open: ['sample-abc123abc123']
open after finish: []
lines: 2
results has run: True
find: ['sample-abc123abc123']
exit=0
```
Exact match.

**A4 — `write_meta`, `write_done`: fields and atomicity.**
```
owners: 2 stage kept: sample
done keys: ['commit', 'counts', 'finished_at', 'key', 'metrics', 'pairs', 'report', 'stage', 'versions']
no temp left: ['done.json', 'meta.json']
exit=0
```
Exact match.

**A5 — the heartbeat file, its name and its `<launch>` index.**
```
['3-0.jsonl', '3-1.jsonl']
3 ['done', 'total', 'ts', 'unit'] done
exit=0
```
Exact match (stdout additionally carries the `@hb `-prefixed mirror lines per
the errata; the ticket's expected output is the two `print()` lines, both
present).

**A6 — the verdicts, as pure functions.**
```
60.0
None
1800.0 300.0
(0.1, 0.1)
('done', False)
('dead', True)
('suspected stall', True)
('warming up', False)
('slowed', False)
('healthy', False)
('healthy', False)
('warming up', False)
('suspected stall', True)
('dead', True)
exit=0
```
Exact match, all six verdicts present.

**A7 — the concurrent-append check.**
```
$ "$PR" tests/test_registry_concurrent_append.py
.
----------------------------------------------------------------------
Ran 1 test in 0.207s

OK
```
`OK`, exit 0.

**A8 — the ledger seed files, and the ignore line.**
```
ledger empty
# Registry results
> Generated by `jobs/registry.py`'s `render()` from `jobs/runs.jsonl` — do not edit by hand.
No runs yet.
jobs/runs.jsonl.lock
```
(the last command, `git status --porcelain jobs/`, printed nothing, i.e. a
clean tree, once run after the commit — checked both before commit, where it
correctly showed the untracked new files, and after, where it is empty).

**A9 — no absolute cluster path in the code.**
```
NO_ABS_PATH
```

**A10 — `ls` over an empty ledger probes no host.**
```
empty ls: []
empty ls --debug: []
exit=0
```
No `AssertionError`; confirms `ls` reaches `live_sessions` through the module
global (so the monkeypatch `r.live_sessions = boom` in the test process took
effect) and only calls it when the folded row set is non-empty.

## 3. The commit

- `d06b83d` — `T03: add the registry (jobs/registry.py), the ledger seeds, and
  the concurrent-append test`. All six files (`jobs/registry.py`,
  `jobs/runs.jsonl`, `jobs/RESULTS.md`, `tests/test_registry_concurrent_append.py`,
  `README.md`, `.gitignore`) landed in this one commit.

## 4. Decisions the ticket did not make, and where they are

1. **No `# venv: any` comment in `jobs/registry.py`.** The ticket's dispatch
   protocol (`implementer.md`) says every new file carries a
   `# venv: any|appworld|probe|vllm` line unconditionally; spec section 5
   (which this ticket cites explicitly) says that comment is added "when the
   file is not `venv: any`". Since `jobs/registry.py` *is* `venv: any`, I
   followed spec section 5's more specific, explicitly-cited rule and left the
   comment out. `tests/test_registry_concurrent_append.py` is `venv: probe`
   (not `any`), so it does carry `# venv: probe`, right after the docstring.
2. **`write_meta`'s merge rule for `owners`.** The ticket pins `launches`
   (append-only) and `pieces` (merged entry by entry); every other field,
   including `owners`, is documented only as "kept when the caller does not
   pass it". A4's test confirms wholesale replacement is correct when the
   field *is* passed (the caller passes the full 2-entry `owners` list and
   gets 2 back), so I implemented every field but `launches`/`pieces` as a
   plain replace-when-given. This matches what 8.3 says `run.py` itself does
   for `owners` — it reads the directory first, decides whether to add a name,
   and calls `write_meta` with the whole resulting list — so no ambiguity
   should arise once `run.py` (ticket 14) is the caller.
3. **`ls`'s flag column is intentionally incomplete.** 8.6 lists eight flags:
   `edited, behind, consumed, split, pinned, dirty, debug, orphan`. 8.0 states
   `edited` and `progress` are computed by `run.py` and only *passed in*
   here, because this file "cannot call `key`" and "cannot tell a done record
   from a claimed one" — i.e., registry.py is deliberately kept ignorant of
   `schema.py` and `data/task_record.py`. I extended the same reasoning to
   `behind` (needs `schema.py`'s `VERSION`-line reading), `consumed` and
   `split` (their sha1 comparisons are against files this module's own
   `reads:` line in contracts 0.2 does not list — only `constants/path_outputs.yaml`,
   `jobs/runs.jsonl`, and a run directory's `meta.json`/heartbeat are on that
   line) and `pinned` (only `schema.py` knows whether a reference was given as
   `key:`/`dir:`). I implemented `edited` (passed through), `debug`, `dirty`
   (both straight off the start row) and `orphan` (self-contained: a run with
   a finish row whose service piece is still alive) inside `_ls_row`, and left
   `behind`/`consumed`/`split`/`pinned` for whichever ticket wires `run.py`'s
   walk (14) to compute and merge in, since they need files this ticket's
   contracts-cited `reads:` line does not cover. `ls`'s returned row does carry
   everything those checks need as raw ingredients (`versions`, `diff`,
   `dir`, `key`, `stage`) for that caller to use.
4. **`judge`/`judge_service`'s piece-dict shape.** I used exactly the errata's
   pinned key set (`{kind, alive, status, done, total, has_beat, beat_ts,
   beat_age_s, since_launch_s, port_ok, avg_rate, recent_rate}` for `judge`,
   and the smaller service set for `judge_service`), and A6 exercises both
   functions directly against that shape, independent of how `_ls_row`
   assembles it — so a caller other than `ls` (e.g. a future test) can build
   the dict by hand and get the same answers.
5. **`cards_busy()`'s `nvidia-smi` probe shape.** The contracts don't pin an
   exact command line for probing *every* card of a host in one shot (the
   ported reference, `legacy/ops/launch_common.py`, probes one already-known
   card list at a time, which is the shape `probe_free` needs but not what
   `cards_busy`/`free` need — they must discover busy indices across an
   entire host with no prior card list). I implemented one `nvidia-smi
   --query-compute-apps` call per index, wrapped in a single shell loop so it
   is still one ssh/bash round trip per host, fail-closed (every index counts
   busy on any probe failure). This function is not exercised by any of my
   ticket's acceptance commands (A1–A10) and is explicitly called out in the
   ticket's own tail as `M-J1`/`M-J2`, "GPU / main session — not yours" — I
   have no ssh access and no GPU in this worktree to verify it against a real
   cluster, so I am flagging the implementation rather than claiming it is
   verified.
6. **`live_sessions()`'s fail-closed guarantee is per-host, via a private
   subclass.** 8.0/3.4 say `live_sessions()` itself is fail-closed ("an
   unclear probe reports the session alive"), but its pinned return type is a
   bare `set[str]` of session names, and a flat set of names cannot, on its
   own, distinguish "this host answered and has no such session" from "this
   host didn't answer, so we don't know." I return a `set` subclass
   (`_ProbedSessions`) that also carries `failed_hosts`; ordinary callers that
   only care about "the live session names" see a plain set of real names (the
   subclass changes nothing about membership testing), while this module's own
   `_alive_on(host, session, sessions)` helper — used by `ls`, `cards_busy` and
   `sync` — checks `failed_hosts` first and reports alive when the piece's own
   host could not be probed, without paying for an extra `session_alive()`
   round trip per piece. This preserves the "one `tmux ls` per host, not per
   piece" cost profile 3.4 describes for `ls`.
7. **Port health check for a service piece is a raw TCP connect.** The exact
   `/health` protocol lives in Part 7 (agent/probe service, tickets 05–07),
   which is out of this ticket's cited scope (spec section 2, 3, 4, 5, 7, 9 —
   note this is spec.md's own section numbering, not contracts Part 7). I
   implemented `_probe_port` as a bare `socket.create_connection` against the
   piece's recorded `port`/`host`, which is enough to distinguish "answering"
   from "not answering" for `judge_service`'s three non-dead verdicts, and
   left the actual health-check semantics to whichever ticket owns that
   protocol.

## 5. What I could not do, and why

Nothing in my ticket's own acceptance section (A1–A10) was left undone; every
command ran and every output matched. The two checks the ticket marks
"GPU / main session — not yours" (`M-J1`, `M-J2`) were not run — they need a
real cluster host list, `ssh`, and `nvidia-smi`, none of which are available
from this worktree, and the ticket says these are not mine to run.

## 6. Anything noticed that belongs in another ticket

- **The ~30s NFSv3 `flock()` grant latency on `/home/y-guo`** (section 2, A2
  above) is a new measured fact, not yet in the contracts document's "Facts
  measured on this machine" section, which only measured `O_EXCL` atomicity on
  the NFSv4 *outputs* mount and explicitly says home "holds no records" for
  locking. Tickets 12 (`jobs/launch.py`) and 14 (`run.py`) both take
  `registry.lock()` around the launch gate and the card reservation; a person
  watching two near-simultaneous launches on this machine should expect the
  second one's tmux sessions to start roughly 30 seconds after the first
  finishes its own lock hold, not sub-second. Worth a line in `ops/gpu_state.md`
  or the contracts document's own facts section if the owner wants it
  recorded there.
- **`ls`'s `behind`/`consumed`/`split`/`pinned` flags** (decision 3 above) are
  not computed by `jobs/registry.py` because the files they need to read are
  outside this module's contracts-cited `reads:` line. Ticket 14 (`run.py`'s
  walk) is the natural place to compute them and merge them into what `ls`
  returns, the same way it already supplies `edited` and `progress`.

## 7. Self-review

- Read back the full diff (`git show d06b83d --stat` and the file contents):
  no file outside the ticket's list was touched, `.gitignore` gained exactly
  the one line the ticket names.
- Checked for a stray `legacy/` citation in the shipped source (the first
  version of the file had three, in a constant comment and two docstrings,
  citing `legacy/ops/verdicts.py` and `legacy/ops/launch_common.py`); rewrote
  all three to describe behaviour without naming the directory, re-ran the
  full acceptance suite afterwards to confirm nothing regressed, and record
  the citations here instead: the five shape constants come from
  `legacy/ops/verdicts.py:16-27`; the local-vs-ssh host short-circuit and the
  per-host `nvidia-smi` probe shape come from `legacy/ops/launch_common.py:41-67`
  and `:70-88`.
- Confirmed with `ast` that `jobs/registry.py` imports only the standard
  library plus `yaml`, carries no `VERSION` line, and that my `README.md`
  entry's `imports:`/`writes:` lines match what the code actually does —
  these are the four "selfcheck lines that apply later" the ticket lists by
  hand, ahead of ticket 15 existing.
- One process-level artifact worth naming so it isn't mistaken for a code
  defect: while re-verifying A4/A5/A10 in a second, separate shell
  invocation, I reused a `$T` temp-dir variable from an earlier, different
  shell invocation without re-exporting it; since each Bash tool call starts
  a fresh shell, `$T` was empty in that second call, and the acceptance
  script's `T = pathlib.Path(sys.argv[1])` silently resolved to the current
  directory, writing a stray `out/` directory into the ticket worktree. The
  printed results were still correct (the code doesn't care where its inputs
  live), but I deleted the stray directory before committing and it never
  reached git. Mentioning it only because a reviewer diffing my terminal
  transcript against the ticket's exact command text will see one run where
  `"$T"` was empty.

## 8. Fix round 1

Branch `ticket/2026-09-17-wave1/T03`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave1-T03-fix1`, base commit
`d06b83d` (this ticket's original commit), fix commit `98ff8a1`.

Four findings, all fixed by correcting the wrong logic directly (no
patch-over, no flag):

**F1 (critical) — `ls()`'s orphan flag omitted "a tmux session matching no
row" entirely.** `_ls_row`'s `orphan` computation only ever implemented 8.6's
second clause (a service piece still running after its owner run finished);
the first clause — a live tmux session on a `hosts:` machine that matches no
piece of any run — was never checked, because `_ls_row` only iterates the
pieces of the one folded row it is building and never cross-checks
`live_sessions()`'s full session set against what every run's pieces claim.

Fix: `ls()` now computes `_known_sessions(all_entries)` — every session name
recorded in any run's current pieces (through `meta.json` when it exists,
else the start row), across the **whole** ledger, not just the rows this
call will display, so a session that belongs to a filtered-out workflow or a
filtered-out debug run is never mistaken for orphan. Any name in
`live_sessions()`'s result that is not in that known set gets a synthetic
`ls()` row of its own (`_orphan_session_row`): every run-identifying field is
`None` (there is no run behind it), `status` is `"orphan_session"`,
`flags.orphan` is `True`, and the one piece entry carries the bare session
name and, when known, its host. To carry the host, `_ProbedSessions` (the
subclass `live_sessions()` already returns for the `failed_hosts` fail-closed
test) gained a second piece of bookkeeping, `host_of: dict[str, str]`,
populated the same pass `live_sessions()` already makes over each host's
`tmux ls` output — no second probe, no signature change to `live_sessions()`
itself (still `-> set[str]`, still one `tmux ls` per host). This is the same
pattern the ticket's own round-1 work used for `failed_hosts` (decision 6 of
section 4 above), extended rather than duplicated.

Verified directly: monkeypatched `live_sessions` to return one known session
(`sample-abc123abc123-0`, matching a real committed run) plus one stray name
(`stray-session-xyz`) with `host_of` for both, then called `r.ls(debug=True)`
against the A3/A4/A5 temp tree (which already has the one finished
`sample-abc123abc123` run on disk). Result: exactly one orphan row, for
`stray-session-xyz` on `tokyo105`, `flags.orphan == True`; the known run's
row has `flags.orphan == False`. A10 (the empty-ledger, no-`ssh` guarantee)
re-verified passing after this change, since the new code only runs inside
the branch that already calls `live_sessions()` — i.e. only when the
*displayed* row set (`entries`, after the `workflow`/`debug` filters) is
non-empty; a filtered-to-empty call still returns `[]` before any host is
probed, unchanged from before this fix.

**F2 (critical) — docstring, README.md, and contracts 0.2 disagreed on
`jobs/registry.py`'s one sentence.** The module docstring said "the
heartbeat files, the verdict functions, ls/where/find/kill/free/sync, and
RESULTS.md"; README.md's entry said "the heartbeat, the verdicts,
ls/where/find/kill/free/sync, RESULTS.md"; contracts 0.2's own tree line
(`notes/plans/2026-09-17-contracts.md:600-601`) says "the heartbeat, the
verdicts, ls/where/find/kill/free, RESULTS.md" — no "/sync". None of the
three matched character for character, contradicting spec section 5 ("the
same sentence as its README.md entry") and section 3 (README entries are
copied from contracts 0.2's authoritative text).

Fix: rewrote both the docstring's first line and README.md's entry sentence
to contracts 0.2's exact wording, dropping the "/sync" contracts never had
and correcting "heartbeat files"/"verdict functions" back to contracts'
"heartbeat"/"verdicts". `sync` is still a real, offered function in the file
(8.6 requires it); it is simply not named in this one summary sentence,
matching contracts. Verified by `ast.get_docstring` pulling the docstring's
first line and comparing it, and README's entry line, against a fresh
`grep` of the contracts tree line: all three now read
`the registry: runs.jsonl rows under a lock, meta.json, the heartbeat, the
verdicts, ls/where/find/kill/free, RESULTS.md.` (docstring capitalizes the
leading "The", matching the convention already set by ticket 02's
`task_record.py`, whose docstring capitalizes while its README entry does
not — same sentence, sentence-initial case aside).

**F3 (critical) — a corrupted `meta.json` was silently discarded, not
archived.** The ticket's own Legacy sources table cites
`legacy/ops/runmeta.py:55-84` (`append_runmeta`) for "temp-name + rename, and
the corrupt-file rename," but only the write-side temp-name-and-rename half
was ported; `_read_json` swallowed `json.JSONDecodeError` into a bare `None`,
and `write_meta` treated that `None` exactly like "no file yet," so the next
write silently overwrote a scrambled `meta.json` — which also holds
`pieces`, the frozen refire commands, and `launches` history — with no
archive step.

Fix: added `_read_meta_or_recover(meta_path)`, used only by `write_meta`
(this is `meta.json`'s own read, not a change to the generic `_read_json`
used elsewhere for `done.json`/`service_*.json`, which have no such
recovery requirement in the ticket's cited sources). A missing file still
returns a fresh default. A file that exists but fails to parse as JSON is
renamed aside to `meta.json.corrupt.<timestamp>` (`%Y%m%d_%H%M%S`, matching
the legacy format) via `os.replace` before a fresh default is returned, so
the scrambled content is preserved on disk under a different name rather
than lost. README.md's `writes:` line for `jobs/registry.py` gained the new
archive path.

Verified directly: wrote `"{not json at all"` into a fresh run directory's
`meta.json`, called `write_meta(...)`, and confirmed the directory then
holds both `meta.json` (a valid fresh default with the caller's fields
merged in) and exactly one `meta.json.corrupt.<timestamp>` file whose
content is byte-for-byte the original garbage.

**F4 (critical) — `kill()` reported a tmux session ended even when the kill
command never reached the host.** `kill()` called `_remote_shell(host, ...)`
for a non-`cpu` piece and discarded its `(ok, out)` return, appending the
session to `ended` unconditionally right after. `_remote_shell` returns
`ok=False` on an ssh failure or timeout — meaning the command never ran on
the host — so a run on an unreachable host was reported as successfully
killed with its tmux session and GPU usage still live.

Fix: `kill()` now checks `_remote_shell`'s `ok` return and only appends the
session to `ended` when `ok` is `True` (the shell command actually executed
on the host — via the local short-circuit or over ssh — regardless of
whether `tmux kill-session` itself found a session to kill, which the
`; true` suffix always makes exit 0 for). Docstring updated to state this
explicitly for both piece kinds (a `cpu` piece already only counted as ended
when its `pid` was alive to signal; this makes the tmux-piece rule the same
kind of honest report).

Verified directly: registered a run with one `loop` piece on host
`unreachable-host`, monkeypatched `_remote_shell` to return `(False, "")`
(simulating an unreachable host) and called `kill()` — result `[]`, nothing
reported ended. Re-monkeypatched `_remote_shell` to return `(True, "")`
(simulating a reachable host) and called `kill()` again on the same run —
result `['killtest-abc123abc123-0']`, the session correctly reported ended.

### Full acceptance re-run (A1–A10), after all four fixes

All ten commands re-run verbatim from the fix worktree's repo root, through
the same absolute interpreters, on a fresh `mktemp -d` tree for every
functional check (never the real `jobs/runs.jsonl`); outputs pasted in full.

**A1**
```
1800 180
1800 180
1800 180
sys ok
exit=0
```

**A2**
```
waited 1.9
outer released
exit=0
```
(`>= 1.5` satisfied; exit 0. This run did not hit the ~30s NFS grant latency
noted in section 2 above — lock grant timing is a filesystem/kernel fact
external to this fix, not something this round changed.)

**A3**
```
open: ['sample-abc123abc123']
open after finish: []
lines: 2
results has run: True
find: ['sample-abc123abc123']
exit=0
```

**A4**
```
owners: 2 stage kept: sample
done keys: ['commit', 'counts', 'finished_at', 'key', 'metrics', 'pairs', 'report', 'stage', 'versions']
no temp left: ['done.json', 'meta.json']
exit=0
```

**A5**
```
['3-0.jsonl', '3-1.jsonl']
3 ['done', 'total', 'ts', 'unit'] done
exit=0
```

**A6**
```
60.0
None
1800.0 300.0
(0.1, 0.1)
('done', False)
('dead', True)
('suspected stall', True)
('warming up', False)
('slowed', False)
('healthy', False)
('healthy', False)
('warming up', False)
('suspected stall', True)
('dead', True)
exit=0
```

**A7**
```
$ external/probe-env/bin/python tests/test_registry_concurrent_append.py
.
----------------------------------------------------------------------
Ran 1 test in 0.201s

OK
exit=0
```

**A8**
```
ledger empty
# Registry results
> Generated by `jobs/registry.py`'s `render()` from `jobs/runs.jsonl` — do not edit by hand.
No runs yet.
jobs/runs.jsonl.lock
```
`git status --porcelain jobs/` printed nothing after the fix commit (clean).

**A9**
```
NO_ABS_PATH
```

**A10**
```
empty ls: []
empty ls --debug: []
exit=0
```
No `AssertionError`; confirms the new orphan-session code path inside `ls()`
is still gated behind the same "displayed row set is non-empty" check as
before, so an empty ledger still issues no `ssh`.

### Commit

- `98ff8a1` — `T03: fix round 1 — orphan session detection, docstring/README/contracts
  alignment, corrupt meta.json archive, honest kill() return`. Both changed
  files (`jobs/registry.py`, `README.md`) landed in this one commit; the
  ledger seed files (`jobs/runs.jsonl`, `jobs/RESULTS.md`) were untouched
  (confirmed via `git status --porcelain jobs/` before and after).

### Self-review

- Full diff read back (`git diff jobs/registry.py`, `git diff README.md`):
  every hunk traces to one of F1–F4; nothing else in the file was reformatted
  or restructured. No new `legacy/` citation (`grep -in legacy jobs/registry.py`
  → no match). No new repo import, no `VERSION` line introduced
  (`ast`-checked). README's `imports:`/`writes:` lines re-checked against the
  code by hand; `writes:` gained the one new archive-path line for F3.
- Considered whether F1's fix should filter orphan rows by the `workflow`
  argument the same way normal rows are filtered, and decided against it: an
  orphan session by definition belongs to no known run, so it has no
  workflow to filter by, and always surfacing it is the conservative,
  fail-visible choice consistent with 3.4's fail-closed posture elsewhere in
  this file.
- Open question for the reviewer, not blocking: F1's synthetic orphan row
  shape (`run_id: None`, `status: "orphan_session"`) is not pinned anywhere
  in the ticket or contracts — there is no acceptance command in A1–A10 that
  exercises this path, and 8.6's own text only says the flag column carries
  `orphan`, not what a row with no owning run looks like. I designed the
  shape to stay structurally close to a normal `ls()` row (same key set) so
  a caller can treat it uniformly, but a future ticket wiring `run.py ls`'s
  display (ticket 14) may want a different presentation for a row with no
  `run_id`; flagging this as a design choice made without an ticket-pinned
  shape to follow, not as an open defect.

## 9. Fix round 2

Branch `ticket/2026-09-17-wave1/T03`, worktree
`/home/y-guo/reproduce/new1-wt/2026-09-17-wave1-T03-fix2`, base commit
`98ff8a1` (fix round 1's commit), fix commit `ecfd925`.

One finding, fixed by correcting the wrong logic directly (no patch-over, no
flag):

**NF1 (important) — orphan-session detection was silently skipped whenever
`ls()`'s filtered row set was empty.** `ls()`'s early return
(`if not entries: return []`, formerly the line right before the
`live_sessions()` call) checked `entries` — the list *after* the
`workflow=`/`debug=` display filters were applied — not `all_entries`, the
full folded ledger F1's own `_known_sessions()` and orphan-row logic walk.
An orphan session belongs to no known run by construction: it therefore has
no `workflow` field to match a `workflow=` filter, and no non-debug run to
satisfy the default `debug=False` filter's requirement that *something*
pass it. So any call where the filtered display set happened to be empty —
a `workflow=` filter matching zero runs, or a ledger holding only debug
runs while `debug=False` (the caller's default) — returned `[]` before
`live_sessions()` was ever called, silently skipping the fail-closed orphan
check in exactly the case it exists to catch: a genuinely live orphaned
tmux session sitting alongside a ledger whose display filter happens to
exclude every known run.

Root cause: the early-return guard and the orphan check are gated behind
the same `if`, but they answer two different questions — "is there a
*display* row to judge" (which depends on the filters) versus "is there
anything in the ledger at all, so an orphan probe could possibly find
something new" (which does not depend on the filters, since an orphan row
is never filtered — see fix round 1's self-review, which already decided
orphan rows are never filtered by `workflow`).

Fix: moved the early return to test `all_entries` (the full folded ledger,
before either filter) instead of `entries` (the filtered display list), and
moved it earlier — right after `all_entries` is built, before the
`workflow`/`debug` filtering even runs. `entries` is still filtered exactly
as before and still drives which normal rows get built; `live_sessions()`
is now called whenever `all_entries` is non-empty, independent of whether
the filters happen to leave `entries` empty. A10's guarantee is preserved
exactly: a *truly* empty ledger (`all_entries == []`, i.e. no run recorded
at all) still returns `[]` with no `live_sessions()` call, since that is
the only case where the early return still fires.

Verified directly, three ways, all against a fresh `mktemp -d` tree
(never the real `jobs/runs.jsonl`):

1. **Workflow filter matching zero runs.** Committed one real run with
   `workflow="baseline"`, monkeypatched `live_sessions()` to return one
   stray session name with a known host, then called
   `r.ls(workflow="no-such-workflow")`. Before the fix this returned `[]`
   (the filtered `entries` list is empty, so the old guard fired before
   `live_sessions()` ran); after the fix it returns exactly one row:
   `(run_id=None, status="orphan_session")` — the orphan is now surfaced
   even though the display filter matches nothing.
2. **Debug-only ledger with the default `debug=False`.** Registered one run
   with `debug=True` and nothing else in the ledger, monkeypatched
   `live_sessions()` the same way, then called `r.ls()` (implicit
   `debug=False`). Result: exactly one row, the orphan
   (`run_id=None, status="orphan_session"`) — the debug run itself is
   correctly filtered out of the display set, but the orphan check still
   ran and still found the stray session. `r.ls(debug=True)` on the same
   ledger returns two rows: the debug run (`status="launch_failed"`, since
   its one session name doesn't match the stray one) plus the same orphan
   row — confirming the orphan row is independent of the `debug` filter in
   both directions.
3. **A10 re-run, including with filters on a truly empty ledger.** Extended
   A10's own script (empty `jobs/runs.jsonl`, `live_sessions` monkeypatched
   to raise `AssertionError` if called) to also call `r.ls(workflow="x")` in
   addition to the ticket's own `r.ls()` and `r.ls(debug=True)`. All three
   calls returned `[]` with no `AssertionError`, confirming a genuinely
   empty ledger still short-circuits before any filter is even evaluated.

### Full acceptance re-run (A1–A10), after the fix

All ten commands re-run verbatim from the fix-round-2 worktree's repo root,
through the same absolute interpreters, on a fresh `mktemp -d` tree for
every functional check (never the real `jobs/runs.jsonl`); outputs pasted
in full.

**A1**
```
1800 180
1800 180
1800 180
sys ok
```
(exit 0 for all four checks)

**A2**
```
waited 1.9
outer released
exit=0
```

**A3**
```
open: ['sample-abc123abc123']
open after finish: []
lines: 2
results has run: True
find: ['sample-abc123abc123']
exit=0
```

**A4**
```
owners: 2 stage kept: sample
done keys: ['commit', 'counts', 'finished_at', 'key', 'metrics', 'pairs', 'report', 'stage', 'versions']
no temp left: ['done.json', 'meta.json']
exit=0
```

**A5**
```
['3-0.jsonl', '3-1.jsonl']
3 ['done', 'total', 'ts', 'unit'] done
exit=0
```
(stdout additionally carries the `@hb `-prefixed mirror lines per the
errata, unchanged from prior rounds)

**A6**
```
60.0
None
1800.0 300.0
(0.1, 0.1)
('done', False)
('dead', True)
('suspected stall', True)
('warming up', False)
('slowed', False)
('healthy', False)
('healthy', False)
('warming up', False)
('suspected stall', True)
('dead', True)
exit=0
```

**A7**
```
$ external/probe-env/bin/python tests/test_registry_concurrent_append.py
.
----------------------------------------------------------------------
Ran 1 test in 0.217s

OK
exit=0
```

**A8**
```
ledger empty
# Registry results
> Generated by `jobs/registry.py`'s `render()` from `jobs/runs.jsonl` — do not edit by hand.
No runs yet.
jobs/runs.jsonl.lock
```
`git status --porcelain jobs/` printed nothing, both before the fix commit
(where it correctly showed only `jobs/registry.py` modified) and after
(clean).

**A9**
```
NO_ABS_PATH
```

**A10**
```
empty ls: []
empty ls --debug: []
empty ls workflow=x: []
exit=0
```
No `AssertionError`; the third call (`workflow="x"`) is this round's own
addition to the ticket's script, confirming a filter argument alone cannot
trigger a host probe over a genuinely empty ledger.

### Commit

- `ecfd925` — `T03: fix round 2 — orphan-session detection no longer
  skipped by an empty filtered display set`. One file changed
  (`jobs/registry.py`), 9 insertions, 3 deletions. The ledger seed files
  (`jobs/runs.jsonl`, `jobs/RESULTS.md`) and `README.md` were untouched
  (confirmed via `git status --porcelain` before and after; `README.md`'s
  entry for `jobs/registry.py` needed no change since `ls()`'s summary
  sentence in both the docstring and README already described the function
  at the same level of detail this fix operates below).

### Self-review

- Full diff read back (`git diff jobs/registry.py`, `git show ecfd925`):
  the only change is moving the early-return guard from `entries` to
  `all_entries` and relocating it before the filters, plus rewriting the
  docstring's explanation of when the probe is skipped to match. No other
  line in `ls()`, `_ls_row`, `_known_sessions`, or `_orphan_session_row` was
  touched. No new `legacy/` citation (`grep -in legacy jobs/registry.py` →
  no match, same as before this round). No new repo import, no `VERSION`
  line introduced.
- Considered whether this fix should also change `_known_sessions()` or
  `_orphan_session_row()`: it should not and does not — both already
  compute over `all_entries`/the full session set correctly (that was fix
  round 1's job); this round's bug was purely in which list gated the call
  to `live_sessions()` in the first place, so only the guard's condition
  and its position needed to move.
- Checked the ticket's own worry surface directly: 8.6's fail-closed
  posture for `live_sessions()`/`session_alive()` is about what happens
  when a probe *fails* (report alive); NF1 was about a probe never being
  *attempted*, which is the same "fail-closed" spirit one level up — a
  filter argument is caller-supplied UI/display state, not a signal that
  the underlying ledger has nothing live to check.
- No open questions from this round.

## 10. Redispatched "fix round 1" — independent re-verification, no code changes

This dispatch arrived carrying the same four findings (F1-F4) section 8 above already
describes fixing, framed as "fix round 1" and pointed at a fresh worktree of
`ticket/2026-09-17-wave1/T03`. Setting that up surfaced two things this report had not
yet recorded, both consistent with a concurrent session working the same branch (new1's
multi-session setup shares one working tree, `bgIsolation=none`):

- A leftover, uncommitted worktree at `.../new1-wt/2026-09-17-wave1-T03-fix2`, checked
  out at `98ff8a1` (section 8's commit) with one uncommitted hunk to `jobs/registry.py` —
  a duplicate, unfinished attempt at the same gating fix section 9 above describes,
  byte-for-byte identical to what is committed as `ecfd925` by `git diff`. Nothing was
  lost: an equivalent, already self-reviewed fix had separately landed as `ecfd925`
  before this dispatch's own worktree existed, so the leftover was removed with
  `git worktree remove --force` per the dispatch protocol for exactly this case, only
  after `git status --porcelain -uall` confirmed it held nothing beyond that one
  duplicate hunk.
- Section 9 (fix round 2) was not yet in this file when this dispatch started reading
  it, and appeared mid-file partway through this dispatch's own testing — written by
  that same concurrent session. This dispatch's own fresh worktree was independently
  removed by concurrent activity seconds after creation and had to be recreated once
  before proceeding.

Rather than take either report section on trust, this dispatch re-verified all four
originally-assigned findings against the code directly, with its own commands, before
discovering (below) that the branch had by then already been merged:

- **F2** (docstring/README/contracts text): `notes/plans/2026-09-17-contracts.md:600-601`,
  `jobs/registry.py:1` and `README.md:11-12` read back and compared by eye — all three
  carry the identical sentence `the registry: runs.jsonl rows under a lock, meta.json,
  the heartbeat, the verdicts, ls/where/find/kill/free, RESULTS.md.` (the docstring
  capitalises the sentence-initial "The"; the other two do not), matching contracts 0.2
  exactly.
- **F1, F3, F4**: exercised with new Python snippets independent of sections 8/9,
  actual output from this run:

```
[F1a] orphan detection, unfiltered call:
  rows: 2  orphans: ['stray-session-xyz']  known row's own orphan flag: False

[F1b] round-2 case: a workflow filter that empties the displayed row set must
      not hide a real orphan session:
  rows: 1  statuses: ['orphan_session']

[F3] a scrambled meta.json ("{not json at all"), then write_meta(...):
  dir listing: ['meta.json', 'meta.json.corrupt.20260917_180628']
  corrupt archived: True
  archived content matches original garbage: True
  fresh meta stage: sample  owners: [{'workflow': 'baseline'}]

[F4] kill() on a piece whose host is unreachable, then reachable:
  kill() while host unreachable: []
  kill() while host reachable: ['killtest-abc123abc123-0']
```

- **A1-A10**, the ticket's full acceptance suite, rerun verbatim end to end from this
  dispatch's own worktree, through the same absolute interpreters, on fresh `mktemp -d`
  trees: all ten passed, matching the ticket's expected output exactly (A2's wait was
  `1.9`, comfortably over the `>= 1.5` bar; every other command's output was
  character-for-character what sections 8 and 9 already pasted).

While this pass was still running, `git log` on the ticket branch started returning
"unknown revision": the main conversation had, concurrently and without this dispatch's
involvement, merged `ticket/2026-09-17-wave1/T03` into `from-zero` (`361dabd`), run its
own wave-1 reconciliation (`6cb1171`, including the main-session-only checks `M-J1`/
`M-J2` the ticket reserves for it), and marked the ticket `resolved`. `git diff ecfd925
6cb1171 -- jobs/registry.py` is empty — the merge carried `ecfd925` through byte for
byte — so the evidence above, gathered independently of that merge, verifies exactly
the code now on `from-zero`.

**F1-F4 are correctly and completely fixed in the code already merged to `from-zero`.
This dispatch made no code changes and no new commit**: the working tree it built was
clean and matched an already-correct head, so there was no wrong logic left to correct.
The `head` this dispatch reports is `ecfd925`, ticket T03's own last commit (now folded
into `from-zero` at `6cb1171` via merge `361dabd`); the ticket branch itself no longer
exists to query directly, having been deleted after the merge.

## 11. Fix round 2 (redispatched) — N1, orphan sessions scoped to this repo

This dispatch carried one new finding, found by a review pass over the code already
merged to `from-zero` (T03 itself is marked `resolved`; the fix round number in this
dispatch's own framing counts against this finding, not against F1-F4/NF1 above, which
sections 8-10 already closed).

**Branch state at the start of this round.** The worktree protocol's prescribed command
(`git worktree add .../fix2 ticket/2026-09-17-wave1/T03`) failed with
`fatal: invalid reference: ticket/2026-09-17-wave1/T03` — consistent with section 10's
own finding that the branch was deleted once the main session merged it (`361dabd`) and
reconciled wave 1 (`6cb1171`). Since the code this finding is about lives on `from-zero`
now, and `from-zero` was already checked out in the main worktree (git refuses to check
out the same branch in two worktrees at once), I recreated
`ticket/2026-09-17-wave1/T03` from `from-zero`'s current tip (`6cb1171`, which carries
F1-F4/NF1 unchanged — confirmed already by section 10's `git diff ecfd925 6cb1171 --
jobs/registry.py` being empty) and built the fix worktree on that branch, so the branch
name and the worktree path both still match what the dispatch named. The fix commit
below is this branch's only new commit; it still needs the same merge-into-`from-zero`
step the main session already did twice for this ticket.

**N1 (important) — orphan-session rows were not scoped to sessions of this repo.**
`ls()`'s orphan-candidate computation (`set(sessions) - known`) used
`live_sessions()`'s raw return value directly: every bare session name a `tmux ls`
against a `hosts:` machine happens to report, filtered only by whether it matched a
piece this ledger already knows about. `constants/path_outputs.yaml`'s `hosts:`
(tokyo105-108) are shared cluster machines other work also runs on under the same
login (project memory records them as freely usable by, for instance, ACL2026), and the
piece session-naming convention contracts pins (2699, `tmux new-session -d -s
<stage>-<key>-<piece>`) carries no repo-specific prefix. So nothing in the code
distinguished "a new1 session no row claims" from "some other process's tmux session
that happens to be running on the same shared host" — both landed identically as a
synthetic `orphan_session` row.

Root cause: the wrong logic was the implicit definition of "candidate orphan" as "any
name `live_sessions()` returns." The fix replaces that definition at its source with
the correct one — "a name shaped like this repo's own launcher would produce" — rather
than leaving the raw set-difference in place and filtering its output from outside.

Fix: added `_is_repo_session_name(name)`, matching the pinned `<stage>-<key>-<piece>`
shape using only two facts this module already owns as part of its own row schema — the
`key` format (2414: 12 lowercase hex characters, the same value this module already
stores and returns in every folded row) and the piece `index` format (8.1: a bare
integer) — via `re.compile(r"^.+-[0-9a-f]{12}-\d+$")`. This adds no hardcoded stage-name
list (the six stage names live in `experimental_settings/schema.py`, which this module
is deliberately kept ignorant of per decision 3, section 4 above) and no new dependency
beyond the stdlib `re` module already implied by the file's "stdlib and PyYAML only"
line. `ls()` now intersects `live_sessions()`'s result with this shape before
subtracting `known`, so only a name that could plausibly be this repo's own is ever a
candidate; `_known_sessions()`, `_orphan_session_row()`, `live_sessions()`,
`cards_busy()`, `session_alive()` and `sync()` are unchanged — the finding is specific
to the one unscoped set-difference inside `ls()`, and none of those other functions do
a raw membership test against the *entire* live-session set (they all test one already-
known session name at a time, which is correct for any name, convention-shaped or not).
Updated `ls()`'s own docstring and added one to the new helper, since the prior
docstring already claimed to implement "a tmux session of this repo" without the code
actually checking that condition.

Verified directly, reproducing the finding's own scenario plus a regression check that
genuine orphan detection still works, against the fix worktree's own copy of the file
(never the real `jobs/runs.jsonl`), on the A3/A4/A5 temp tree (which already carries one
real, finished `sample-abc123abc123` run with tracked session
`sample-abc123abc123-0`):

```
orphan sessions reported by ls(): ['sample-deadbeef0123-2']
known run's own orphan flag: False
_is_repo_session_name('sample-abc123abc123-0') = True
_is_repo_session_name('ACL2026-eval-run') = False
_is_repo_session_name('gyb-manual-debug') = False
_is_repo_session_name('sample-deadbeef0123-2') = True
```

`live_sessions()` was monkeypatched to return four names: the one real tracked session,
the finding's own two unrelated names (`ACL2026-eval-run`, `gyb-manual-debug`), and one
genuine-but-never-registered new1-shaped session (`sample-deadbeef0123-2`, matching the
naming convention but claimed by no piece in the ledger). Before this fix, all three
unknown names would have been reported as orphan; after it, only the repo-shaped,
genuinely-unregistered one is — the two unrelated names are gone from the output, and
the real run's own row still correctly shows `orphan: False`.

### Full acceptance re-run (A1-A10), after the fix

All ten commands re-run verbatim from the fix-round-2 worktree's repo root, through the
same absolute interpreters, on a fresh `mktemp -d` tree for every functional check
(never the real `jobs/runs.jsonl`); outputs pasted in full.

**A1**
```
1800 180
1800 180
1800 180
sys ok
```
(exit 0 for all four checks)

**A2**
```
waited 1.9
outer released
exit=0
```

**A3**
```
open: ['sample-abc123abc123']
open after finish: []
lines: 2
results has run: True
find: ['sample-abc123abc123']
exit=0
```

**A4**
```
owners: 2 stage kept: sample
done keys: ['commit', 'counts', 'finished_at', 'key', 'metrics', 'pairs', 'report', 'stage', 'versions']
no temp left: ['done.json', 'meta.json']
exit=0
```

**A5**
```
['3-0.jsonl', '3-1.jsonl']
3 ['done', 'total', 'ts', 'unit'] done
exit=0
```
(stdout additionally carries the `@hb `-prefixed mirror lines per the errata,
unchanged from prior rounds)

**A6**
```
60.0
None
1800.0 300.0
(0.1, 0.1)
('done', False)
('dead', True)
('suspected stall', True)
('warming up', False)
('slowed', False)
('healthy', False)
('healthy', False)
('warming up', False)
('suspected stall', True)
('dead', True)
exit=0
```

**A7**
```
$ external/probe-env/bin/python tests/test_registry_concurrent_append.py
.
----------------------------------------------------------------------
Ran 1 test in 0.202s

OK
exit=0
```

**A8**
```
ledger empty
# Registry results
> Generated by `jobs/registry.py`'s `render()` from `jobs/runs.jsonl` — do not edit by hand.
No runs yet.
jobs/runs.jsonl.lock
```
`git status --porcelain jobs/` showed only ` M jobs/registry.py` before the commit
(this round's fix, uncommitted at the time of the check) and nothing beyond that; the
ledger seed files were untouched throughout.

**A9**
```
NO_ABS_PATH
```

**A10**
```
empty ls: []
empty ls --debug: []
empty ls workflow=x: []
exit=0
```
No `AssertionError`; a shape-scoped filter alone cannot trigger a host probe over a
genuinely empty ledger, unchanged from round 2's own addition of the `workflow=`
variant.

### Commit

- `ec1c026` — `T03: fix round 2 — orphan-session detection scoped to this repo's own
  session-name shape`, on branch `ticket/2026-09-17-wave1/T03` (recreated from
  `from-zero`'s tip `6cb1171`, per the branch-state note above). One file changed
  (`jobs/registry.py`), 34 insertions, 12 deletions. `README.md` needed no change: the
  module's one-sentence summary (the F2-aligned line shared by the docstring, `README`,
  and contracts 0.2) is untouched, the `imports:` line already reads `none (repo);
  [PyYAML]` (it does not enumerate individual stdlib modules, so adding the stdlib `re`
  import changes nothing it states), and no new read, write or `venv` behaviour was
  added. `run.py` does not exist yet on this branch, so the implementer protocol's
  `run.py selfcheck` step does not apply.

### Self-review

- Full diff read back (`git diff jobs/registry.py`, `git show ec1c026`): every hunk
  traces to N1 — the new `import re`, the new `_SESSION_NAME_RE`/
  `_is_repo_session_name`, the `ls()` docstring update describing the scoping, and the
  one-line change to what `ls()` iterates before building orphan rows. No other function
  was touched.
- No new `legacy/` citation (`grep -in legacy jobs/registry.py` → no match): the fix is
  a new mechanism this round needed, not a ported one, so nothing to cite.
- Considered hardcoding the six stage names (`sample`, `build`, `train`, `eval`,
  `inject`, `score`) from contracts 2.1 into the shape check instead of a suffix-only
  match, for a tighter test; decided against it, for two reasons: it would encode a fact
  from a file this module deliberately does not import or track versions of (schema.py
  owns the stage table; this module "cannot call `key`" per decision 3, section 4
  above), and it would silently misclassify a genuine session of a future seventh stage
  as not-this-repo's the day contracts 2.1 grows one, which is a worse failure than
  today's over-broad match — a real new1 session going unflagged as orphan is a
  fail-open outcome the file's fail-closed posture (3.4, 8.6) argues against everywhere
  else it applies.
- Considered whether the shape check should also apply inside `live_sessions()` itself
  or `cards_busy()`/`sync()`; decided against it — those functions test membership of
  one already-known session name at a time (a name this module's own writer half
  produced), never do a raw sweep over every live session the way `ls()`'s orphan branch
  did, and the finding's own citation (`jobs/registry.py:906-907`) points at exactly that
  one branch.
- Open question for the reviewer, not blocking: the shape check is a heuristic — a
  session from some other tool that happens to look like `<word>-<12 lowercase hex
  chars>-<digits>` would still be misreported as a new1 orphan, and conversely nothing
  stops a person from starting a manual tmux session that happens to match the shape on
  purpose. Neither case is reachable from this finding's own reproduction, and closing
  it completely would need a repo-specific prefix in the naming convention itself
  (contracts 2699, `jobs/launch.py`, ticket 12) — out of this ticket's file list and
  this module's `reads:` scope.
