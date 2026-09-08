"""The exec stage for miss_policy=execute: puts the call predicted by the probe back
into the real appworld environment and executes it.

The question this answers: the skip variant simply skips injection whenever the probe
guesses wrong, so "the cost of a wrong guess" disappears from the ledger (of 1061 fire
events, 372 wrong guesses were skipped, biasing the accuracy axis optimistic). The
execute variant makes every fire actually land: replay that task's environment to that
step, execute the predicted call, and **inject it as-is regardless of whether the
return is a real result or an error**. Only then does the cost of a wrong guess get
recorded.

Method (one AppWorld instance per unit, advancing in ascending step order):
  1. Before reaching the target step, process the events at that step first -- at this
     point the environment state is exactly the state the model faced when it wrote
     that thinking text;
  2. `save_state` to checkpoint -> execute the "requoted predicted call" -> `load_state`
     to restore -> `_set_datetime()` to re-freeze time -> assert the frozen moment did
     not drift;
  3. Execute the real code recorded for that step, compare the output against the
     result recorded in the trajectory character by character; on mismatch, mark the
     events after that unit as prefix_verbatim=False (see known bias 1).

**This file is the only place in the whole pipeline that imports appworld**, so it can
only run with `envs/appworld/venv/bin/python`; `import appworld` in cprobe-env raises
ModuleNotFoundError (measured). So the exec stage is a standalone file with its own
interpreter, handed off via jsonl: plan.jsonl (produced by cprobe-env) -> this file ->
exec_calls.jsonl -> `replay_inject.py merge-exec` (cprobe-env) -> plan_exec.jsonl.
Pure CPU, no GPU card used.

Boundaries (what the execute variant cannot do -- don't misrepresent this in the
report):
- **The execute variant does not produce an appworld task-level score.** For one
  event, this file only executes "that one predicted call"; it does not let the model
  keep going through the whole task, nor does it call `world.evaluate()`. So what it
  measures is **single-step call consistency + the real error injected on a wrong
  guess**, not appworld's Test score. The real task-level axis needs an in-loop
  rollout (attach the probe inside run_appworld.py's loop, inject on fire, run the
  whole task, then evaluate) -- that is a separate collection run, outside the scope
  of this file.

Known biases (always include these in the report, never silently drop them):
1. Prefix-replay fidelity has only been measured at 100% on 3 trajectories, 28 steps
   (2026-08-01). APIs with randomness, time-dependent APIs, and the boundary at the
   4000-character truncation point can all drift. So every step is checked against the
   recorded result character by character; drifted events are marked
   prefix_verbatim=False / drift_step=<step number> and listed separately in the
   report -- skipping this check means executing the predicted call against a wrong
   state and then reporting the result as if it were real.
2. The injected content depends on requote, a **heuristic**: the gen_call in
   plan.jsonl is the annotate side's dequoted normalized string (strip("\"'") in
   annotate/rules.py:133), looking like
   `apis.api_docs.show_api_doc(app_name=venmo, api_name=search_users)`, which raises a
   NameError if executed directly. The branch that adds quotes back falls into
   arg_modes per argument, and the report counts the branches. Forcing
   `{app_name, api_name}` to strings is an **empirically hardcoded rule** (these two
   arguments of appworld's api_docs are always strings); switching environment or
   tool family will silently take the wrong branch -- hence the need for an
   acceptance line.
   **The acceptance line only accepts events where three conditions hold at once**:
   the prediction matches the ground truth (full_call_ok), the code block contains
   exactly 1 call, and that code block is a single clean `print(call)` statement (a
   full-line comment does not count). Missing any one of these three, "the output of
   executing that call alone" and "the whole stdout block recorded" are simply not
   comparable, and including them only produces false alarms against yourself -- two
   false alarms measured in practice: (1) a code block is
   `print("passwords:", apis.supervisor.show_account_passwords())`, a single call
   with nothing wrong, but the recorded stdout has extra prefixes and goes through
   Python's repr instead of appworld's json-converting print; (2) when the call
   itself errors, the traceback echoes back the source code, and differing quote
   styles make it not match character for character (the trajectory has
   app_name="spotify", requote fills in 'spotify') -- so for error cases, compare via
   err_tail(), only the message after the exception line.
   Measured (2026-08-01): 17/17 on the first 4 units; 53/53 on 80 events across 13
   units (52 exact matches + 1 matching error message), excluding 1 that was not
   comparable.
6. Of the full 1061 events, 664 are hit + single-call, of which 643 are clean prints
   -- the acceptance line's denominator is those 643; the other 21 are not comparable
   and are listed separately, not counted.
3. The execute variant changes the injected content from "the whole stdout block" to
   "that one call's return value." This actually fixes the multi-call bias listed at
   the top of replay_inject.py (99/1061 events have code blocks with multiple calls),
   at the cost that hit events are no longer character-for-character comparable with
   the already-run skip/oracle six-point curve. So the score stage must bucket by
   inject_source, never mix them into a single average.
4. The cache key carries REQUOTE_VERSION: changing any requote rule requires
   incrementing this constant, or the old cache will be silently reused.
5. A process can only have one live AppWorld: both `initialize()` and `load_state()`
   call `AppWorld.close_all()` (environment.py:368/751), which stops all time
   freezers, clears the DB cache, and closes the ApiCollection -- a second instance
   would silently break the first. So concurrency can only be done via multiple
   processes, each with its own experiment_name; you cannot open two worlds in one
   process.

Usage:
  # smoke test (4 units, about 1 minute, pure CPU; see the --selfcheck exit code for
  # the green bar)
  envs/appworld/venv/bin/python pipeline/inject/exec_calls.py \\
      --plan pipeline/inject/runs/aw_gptoss_r10/plan.jsonl \\
      --out  /tmp/exec_smoke.jsonl --cache /tmp/exec_cache_smoke.jsonl \\
      --exp  smoke_execprobe --limit-units 4 --selfcheck

  # full run: 4 shards, one process per shard (pure CPU, can run in parallel with the
  # run stage of other θ points)
  for i in 0 1 2 3; do envs/appworld/venv/bin/python \\
      pipeline/inject/exec_calls.py \\
      --plan pipeline/inject/runs/aw_gptoss_th0925/plan.jsonl \\
      --out  pipeline/inject/runs/aw_gptoss_th0925/exec_calls.jsonl \\
      --cache pipeline/inject/exec_cache/aw_gptoss.jsonl \\
      --exp  aw_exec_th0925 --num-shards 4 --shard-id $i & done; wait
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "annotate"))

from rules import AW_CALL, first_call_named            # noqa: E402

# appworld's path_store requires the process cwd to be this directory (same as run_appworld.py:63)
APPWORLD_HOME = "/home/y-guo/reproduce/new1/envs/appworld"

# During collection, world.execute output is truncated to 4000 characters before being
# written [copied from envs/collect/run_appworld.py:105]. Without truncating, the
# length distribution of the injected content would not be comparable to traj_hit, and
# the token-savings axis would drift silently.
TRUNC = 4000

# Random seed: AppWorld's default is 100 (environment.py:97), and it was not passed
# explicitly during collection. The project hard rule is that the seed must be written
# into the code and into the report, so it is pinned explicitly here and written into meta.
APPWORLD_SEED = 100

# The checkpoint name used for restoring. A fixed name is overwritten repeatedly (_save_state has delete_if_exists=True)
CKPT = "probe"

# requote rule version. **Incrementing this is required whenever any branch of
# requote() below changes**, otherwise the cache key stays the same and old results
# get silently reused (known bias 4)
REQUOTE_VERSION = 1

IDENT = re.compile(r"^[A-Za-z_]\w*$")
POSKEY = re.compile(r"^pos\d+$")

# These two arguments of appworld's api_docs are always strings. Empirically hardcoded, see known bias 2
ALWAYS_STR = {"app_name", "api_name"}


# ------------------------------------------------------------- requote

def requote(call, user_ns):
    """Turn the dequoted predicted call string into executable python. Returns (code,
    which branch each argument took).

    Branch order (per argument, order must not change):
      unparsable_raw  the whole string cannot even be assembled into
                      `apis.<app>.<api>(` (2 out of the full 1061, shaped like
                      `apis.login(...)`). **Drop it into the environment as-is and let
                      it error and get counted, never skip it** -- skipping it would
                      erase the cost of the probe's wrong guess again, and that is
                      exactly the flaw the execute variant is meant to fix.
      forced_str      the key is in ALWAYS_STR, force repr into a string (1454/1475 of
                      the full set)
      literal         ast.literal_eval recognizes it (numbers/True/None/lists, 1 in
                      the full set)
      shell_var       it is an identifier and that variable genuinely exists in the
                      shell after prefix replay (catches real variable references like
                      `access_token=access_token`)
      quoted          everything else, repr into a string (the remaining 20 in the
                      full set)
    Argument order follows the order first_call_named produces them in, not sorted.

    **The shell_var branch is inherently ambiguous**, and the ambiguity shows up in
    real data: of the 20 non-api_docs argument values in the full 1061, some are
    `password=phone_password` (genuinely a variable reference) and some are
    `password=b4GXZH6`, `password=_7JMKRg` (literal passwords that happen to look like
    identifiers too). The condition `v in user_ns` blocks the latter -- a password
    string will not happen to also be a variable name -- but the moment a real
    collision occurs (say, the model names a variable `email`, and the probe also
    predicts the literal value `email`), it silently takes the wrong branch. So every
    argument's branch is recorded into arg_modes and counted in the report; to
    actually catch this, look at the matched_traj_result acceptance line on hit
    single-call events.
    """
    m = AW_CALL.search(call or "")
    if not m:
        return f"print({call})", ["unparsable_raw"]
    tool = f"apis.{m.group(1)}.{m.group(2)}"
    named = first_call_named(call, AW_CALL) or []
    parts, modes = [], []
    for k, v in named:
        pos = bool(POSKEY.match(k))          # positional argument (0 in the full set, kept defensively)
        if k in ALWAYS_STR:
            val, mode = repr(v), "forced_str"
        else:
            try:
                ast.literal_eval(v)          # number / True / None / list / dict
                val, mode = v, "literal"
            except Exception:
                if IDENT.match(v) and v in user_ns:
                    val, mode = v, "shell_var"
                else:
                    val, mode = repr(v), "quoted"
        parts.append(val if pos else f"{k}={val}")
        modes.append(("pos_" + mode) if pos else mode)
    return f"print({tool}({', '.join(parts)}))", modes


# Whether the code recorded at this step is "exactly one print(some apis call)"
# statement. Only steps like this have stdout comparable to "executing that call
# alone" -- an event was measured with a code block of
# `print("passwords:", apis.supervisor.show_account_passwords())`,
# a single call with nothing wrong, but the recorded stdout has extra prefixes and
# goes through Python's repr instead of appworld's json-converting print; using it as
# an acceptance line would produce a false alarm against yourself
# Deliberately not adding re.S: with `.` matching across lines,
# `print(apis.a.b())\nprint(apis.c.d())` would also get recognized as one statement
# (the trailing `)` matches into the second statement) -- hit this before. A
# multi-line single-call block is always judged "not clean"; better to conservatively
# exclude it from the acceptance line
BARE_PRINT = re.compile(r"print\(\s*apis\.\w+\.\w+\([^\n]*\)\s*\)")


def is_bare_print(code):
    """Whether the code recorded at this step is "exactly one print(some apis call)"
    statement (a full-line comment does not count).

    Comments and blank lines produce no stdout, so a code block with a `# note` line
    is still comparable to "executing that call alone." Not stripping comments would
    wrongly judge 167 of the full 664 hit+single-call events as not comparable
    (measured: 497 -> 664), needlessly shrinking the acceptance line's denominator.
    """
    body = [ln for ln in (code or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    return len(body) == 1 and bool(BARE_PRINT.fullmatch(body[0].strip()))


def err_tail(out):
    """Strip the "echoed source code" lines from the error text, keeping only the
    exception line and the message after it. Returns None if it is not an error.

    Why this is needed: appworld's error text echoes the **source line** that errored
    verbatim into the traceback, so even when "the call the probe predicted" and "the
    call actually executed at the time" are semantically identical, a
    character-for-character comparison fails whenever the quote style differs (the
    trajectory has app_name="spotify", requote fills in app_name='spotify'). Hit this
    in practice. Comparing the message after the exception line is what actually
    compares "whether the error is the same."
    """
    if out is None or not out.startswith("Execution failed"):
        return None
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^([A-Za-z_][\w.]*)\s*:", line.strip()):
            return "\n".join(lines[i:])
    return out


def error_kind(out):
    """Identify the error kind from execute's return value. Returns None if it is not an
    error.

    This function is the **single source of truth**: merge-exec recomputes it from
    exec_out and does not trust the field already in the cache -- otherwise, changing
    the classification rule would leave old labels from the old cache silently
    sitting in the report.

    http_4xx is pulled out on its own because appworld turns both "API name does not
    exist" and "wrong argument" into status codes like 422 (measured: the probe
    guessed `apis.api_docs.show_api_doc(app_name='spotify',
    api_name='add_tracks_to_playlist')` and got back
    `Exception: Response status code is 422: {"message":"No APIs with name ...`).
    Recording a generic Exception would hide exactly what the probe got wrong.
    """
    if out is None or not out.startswith("Execution failed"):
        return None
    if "timed out" in out:
        return "timeout"
    if "Syntax error in line" in out:
        return "SyntaxError"
    m = re.search(r"Response status code is (\d+)", out)
    if m:
        return f"http_{m.group(1)}"
    # The last line of a python traceback is `ExcName: msg`, but msg can contain its own
    # newlines (the 422 json above takes up the last line), so search backward for the
    # first `Name:`. Careful not to write this as "name must end in Error/Exception" --
    # the bare `Exception:` is only 9 characters and a "prefix + suffix" regex would miss
    # it (hit this before)
    for line in reversed([x.strip() for x in out.splitlines() if x.strip()]):
        m = re.match(r"^([A-Za-z_][\w.]*)\s*:", line)
        if m:
            return m.group(1).rsplit(".", 1)[-1]
    return "unknown"


# ------------------------------------------------------------- traj / cache

def load_steps(traj_path):
    """The steps in the trajectory that were actually executed: [(step, the code executed
    at the time, the result recorded at the time)].

    Takes the action recorded by env directly -- it is exactly the string passed to
    world.execute during collection (envs/collect/run_appworld.py:104-106), one step
    fewer than taking gen's content and re-extracting it with CODE_RE. Steps where
    action is None (NO_CODE_BLOCK) were not executed, skip them.
    """
    envs = {}
    with open(traj_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("type") == "env" and r.get("action") is not None:
                envs[r["step"]] = r
    return [(st, envs[st]["action"], envs[st].get("result") or "")
            for st in sorted(envs)]


def prefix_sigs(steps):
    """The cumulative fingerprint of the **code actually executed before each step**,
    used as the trajectory identity in the cache key.

    Why this is necessary: appworld's unit names are identical across the three
    models (gptoss/q35/q36) (three copies under `envs/runs/w0_aw_official/`,
    same-named unit files), but each trajectory executes different code on the same
    unit, so the world state differs. If the cache key only had unit+step, running
    execute on a different batch of trajectories would **silently** reuse another
    world's execution results; worse, on a cache hit the whole prefix replay is
    skipped and `prefix_verbatim` is copied straight from the cache as True -- this
    both contaminates the injected content and disables the only sentinel that could
    catch the contamination, so n_drift in the report would be a false 0.
    (Reproduced in practice: switch the plan's traj_path from appworld_gptoss to
    appworld_q35, then run against a cache built from gptoss -- 8/8 all hit, not a
    single world built, exec_out identical character for character.)

    World state is determined by "what was executed before this step," so the
    fingerprint takes the prefix, not the whole trajectory.
    """
    out, h = {}, hashlib.sha1()
    for st, action, _ in steps:
        out[st] = h.hexdigest()[:16]         # the prefix **before** this step
        h.update(f"{st}\x00{action}\x00".encode())
    return out


def cache_key(unit, step, gen_call, psig):
    raw = f"{REQUOTE_VERSION}|{unit}|{step}|{psig}|{gen_call}"
    return hashlib.sha1(raw.encode()).hexdigest()


def cache_files(cache_path):
    """All shard files under the same cache stem name.

    Each shard process writes its own `<stem>.s<id>.jsonl` (concurrent O_APPEND writes
    of lines over 4KB interleave, so they cannot share one file); reading pulls in all
    sibling files -- this lets most predicted calls hit the cache directly across the
    six θ points (state is independent of θ).

    Matching must be exact to the two shapes `<stem>.jsonl` and `<stem>.s<N>.jsonl` --
    the original prefix glob (`<stem>*`) would silently swallow caches from other
    batches like `<stem>_v2.s0.jsonl`, `<stem>2.jsonl` (audit B8).
    """
    p = Path(cache_path)
    if not p.parent.is_dir():
        return []
    pat = re.compile(re.escape(p.stem) + r"(\.s\d+)?" + re.escape(p.suffix) + r"$")
    return sorted(str(f) for f in p.parent.iterdir() if pat.fullmatch(f.name))


def _reqver_write(p, h):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")          # four shards run concurrently, the write must be atomic
    tmp.write_text(json.dumps({"requote_version": REQUOTE_VERSION,
                               "src_sha1": h}))
    os.replace(tmp, p)


def check_requote_version(cache_main):
    """Mechanical guard (audit B8): refuse to run if the **executable structure** of
    requote()/cache_key() changed but REQUOTE_VERSION was not incremented -- an
    unchanged key would silently reuse results computed under the old convention.
    Comment/docstring changes do not count (normalized through ast before hashing).
    The record is stored at <stem>.reqver.json, created automatically on first run;
    incrementing switches to a new record automatically (the old key naturally
    expires)."""
    import ast
    import inspect
    src = inspect.getsource(requote) + inspect.getsource(cache_key)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    h = hashlib.sha1(ast.unparse(tree).encode()).hexdigest()
    p = cache_main.with_name(cache_main.stem + ".reqver.json")
    if p.exists():
        try:
            old = json.loads(p.read_text())
        except Exception:
            sys.exit(f"cache version record is corrupted: {p} -- confirm by hand, delete it, and rerun "
                     "(this rebuilds the record from the current source); do not treat this as no record and silently let it pass.")
        if old.get("src_sha1") == h:
            if old.get("requote_version") != REQUOTE_VERSION:
                _reqver_write(p, h)     # only incremented, source unchanged: the record catches up to the constant
            return
        if old.get("requote_version") == REQUOTE_VERSION:
            sys.exit(
                f"the source of requote()/cache_key() has changed, but REQUOTE_VERSION is still "
                f"{REQUOTE_VERSION} -- the cache key stays the same, old results get silently reused. "
                f"If this is confirmed to be a logic change, bump REQUOTE_VERSION by 1 and rerun; "
                f"record: {p}")
    _reqver_write(p, h)


def load_cache(cache_path):
    cache = {}
    for fp in cache_files(cache_path):
        with open(fp) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:            # a half-written line (process killed) is simply dropped
                    continue
                if o.get("key"):
                    cache[o["key"]] = o
    return cache


# ------------------------------------------------------------- one unit

def replay_unit(AppWorld, unit, rows, traj_path, exp, cache, cache_sink,
                stats, out, probe=True):
    """Replay one unit to the step of each event and execute the predicted call,
    appending records to out.

    Division of write responsibility: execution results are written into cache_sink
    **on the spot** (nothing is wasted if the process gets killed); event records are
    appended to the out list the caller provides, and the caller writes the file --
    the function itself never touches a file, to avoid missing some path (e.g. the
    one where the whole unit hits the cache); out is owned by the caller, so if a
    unit blows up partway through, the events already done are still there and are
    not wasted.

    probe=False is "clean replay" mode: no probe call is inserted at all, it only
    checks the recorded result step by step. --selfcheck uses this on drifted units
    to assign blame for the drift (is the replay itself not faithful, or did a probe
    call write to the DB and fail to restore it cleanly).
    """
    steps = load_steps(traj_path)
    have = {st for st, _, _ in steps}
    # These two tables let "comparing against the recorded result" not depend on whether
    # execution actually happened (the path where the whole unit hits the cache must also
    # be able to compute it), so prepare them before building the world
    rec_of = {st: r for st, _, r in steps}
    psig = prefix_sigs(steps)                # the trajectory identity in the cache key, see prefix_sigs
    bare_of = {st: is_bare_print(c) for st, c, _ in steps}
    by_step = {}
    for r in rows:
        by_step.setdefault(r["step"], []).append(r)

    def compare(eout, st):
        """Compare "the execution return value" against "the result recorded in the
        trajectory" three ways: character for character / error message only /
        whether the code recorded at this step is a single clean print(call)
        statement."""
        recorded = rec_of.get(st)
        return dict(matched_traj_result=(eout == recorded),
                    matched_traj_error=(
                        None if err_tail(eout) is None
                        or err_tail(recorded) is None
                        else err_tail(eout) == err_tail(recorded)),
                    traj_bare_print=bare_of.get(st))

    # every step before this one must already be executed; the real code at the last needed step does not need re-executing
    last_needed = max(by_step) if by_step else -1
    missing = [r for r in rows if r["step"] not in have]
    for r in missing:                        # this step was never executed in the trajectory (NO_CODE_BLOCK)
        out.append(dict(event=r["event"], unit=unit, step=r["step"],
                        gen_call=r["gen_call"], exec_code=None, arg_modes=None,
                        exec_out=None, exec_ok=None,
                        error_kind="step_not_in_traj",
                        prefix_verbatim=None, drift_step=None,
                        matched_traj_result=None, cache_hit=False, wall_s=0.0,
                        full_call_ok=r.get("full_call_ok"),
                        n_calls_in_block=r.get("n_calls_in_block")))
        stats["step_not_in_traj"] += 1

    todo = [r for r in rows if r["step"] in have]
    if not todo:
        return out

    # everything hits the cache -> don't even need to build the world (this is what makes re-running across θ points cheap)
    hits = {r["event"]: cache.get(cache_key(unit, r["step"], r["gen_call"],
                                            psig[r["step"]]))
            for r in todo}
    if probe and all(hits.values()):
        for r in todo:
            c = dict(hits[r["event"]])
            c.pop("key", None)
            c.update(event=r["event"], unit=unit, step=r["step"],
                     gen_call=r["gen_call"], cache_hit=True, wall_s=0.0,
                     dt_guard=None, full_call_ok=r.get("full_call_ok"),
                     n_calls_in_block=r.get("n_calls_in_block"),
                     # Compute the three comparison fields fresh, do not copy them from the cache: the old
                     # cache may have been written under the previous comparison method, copying it would
                     # silently carry the old convention into the report
                     **compare(c.get("exec_out"), r["step"]))
            out.append(c)
            stats["cache_hit"] += 1
            stats["exec_ok" if c.get("exec_ok") else "exec_err"] += 1
        stats["unit_all_cached"] += 1
        return out

    world = AppWorld(task_id=unit, experiment_name=exp,
                     random_seed=APPWORLD_SEED)
    try:
        # The baseline for the time guard: the frozen moment at the unit's start. load_state
        # only does _load_state + _execute_preamble and does not re-freeze time
        # (environment.py:748-754), so after restoring a checkpoint you must explicitly call
        # _set_datetime() again and re-check -- skipping this check risks executing the call
        # against real time.
        t_frozen = world.execute("print(DateTime.now())").strip()
        dt_guard = not t_frozen.startswith("Execution failed")
        if dt_guard:
            stats["dt_guard_ok"] += 1
            if t_frozen != str(world.task.datetime):
                stats["dt_ne_task_datetime"] += 1
        else:
            stats["dt_guard_broken"] += 1

        verbatim, drift_at, clean_outs = True, None, []
        for st, code, recorded in steps:
            if st > last_needed:
                break
            for i, r in enumerate(by_step.get(st, []) if probe else []):
                t0 = time.time()
                key = cache_key(unit, st, r["gen_call"], psig[st])
                hit = cache.get(key)
                if hit:
                    rec = dict(hit)
                    rec.pop("key", None)
                    rec.update(event=r["event"], unit=unit, step=st,
                               cache_hit=True)
                    stats["cache_hit"] += 1
                else:
                    code_x, modes = requote(r["gen_call"], world.shell.user_ns)
                    last_event_of_unit = (st == last_needed and
                                          i == len(by_step[st]) - 1)
                    # checkpoint -> execute -> restore, all three must happen together: skipping the
                    # restore does not raise an error, but silently contaminates the state for every
                    # later event in the same unit (risk 2).
                    # So `finally` is the fallback, and after restoring, time is re-frozen and asserted
                    # again.
                    world.save_state(CKPT)
                    try:
                        eout = str(world.execute(code_x))[:TRUNC]
                    finally:
                        if not last_event_of_unit:
                            world.load_state(CKPT)
                            world._set_datetime()
                            if dt_guard:
                                now = world.execute(
                                    "print(DateTime.now())").strip()
                                if now != t_frozen:
                                    raise RuntimeError(
                                        f"time drifted after the restore: {now!r} != "
                                        f"{t_frozen!r} ({unit} s{st})")
                    ek = error_kind(eout)
                    rec = dict(exec_code=code_x, arg_modes=modes,
                               exec_out=eout, exec_ok=(ek is None),
                               error_kind=ek,
                               prefix_verbatim=verbatim, drift_step=drift_at,
                               cache_hit=False, **compare(eout, st))
                    cache_sink.write(json.dumps(
                        dict(key=key, appworld_seed=APPWORLD_SEED,
                             requote_version=REQUOTE_VERSION, **rec),
                        ensure_ascii=False) + "\n")
                    cache_sink.flush()
                    rec.update(event=r["event"], unit=unit, step=st)
                rec.update(gen_call=r["gen_call"], dt_guard=dt_guard,
                           wall_s=round(time.time() - t0, 3),
                           full_call_ok=r.get("full_call_ok"),
                           n_calls_in_block=r.get("n_calls_in_block"))
                # prefix_verbatim / drift_step reflect "whether the prefix had drifted by the time
                # this event was reached"; the value in the cache is from the first execution, this
                # replay's value takes precedence here
                rec["prefix_verbatim"], rec["drift_step"] = verbatim, drift_at
                out.append(rec)
                stats["exec_ok" if rec.get("exec_ok") else "exec_err"] += 1

            if st == last_needed:            # stop once the target step is reached, no need to execute the real code for this step
                break
            got = str(world.execute(code))[:TRUNC]
            clean_outs.append((st, got))
            if got != recorded and verbatim:
                verbatim, drift_at = False, st
                stats["unit_drift"] += 1
        return out if probe else clean_outs
    finally:
        world.close()


# ------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", required=True, help="plan.jsonl (either the execute or skip version works)")
    ap.add_argument("--out", required=True, help="exec_calls.jsonl; sharding appends .s<id> automatically")
    ap.add_argument("--cache", required=True,
                    help="execution cache reused across θ values (append-only jsonl, each shard writes its own copy)")
    ap.add_argument("--exp", required=True, help="prefix for the appworld experiment_name")
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--limit-units", type=int, default=0)
    ap.add_argument("--keep-outputs", action="store_true",
                   help="do not delete each unit's appworld output dir after it finishes (deleted by default). "
                        "Each appworld unit leaves ~90KB of dbs/checkpoints/logs, "
                        "and /home is a shared disk with a quota (hit "
                        "Disk quota exceeded once on 2026-08-01) -- delete right after it finishes, to keep usage down to one unit's worth")
    ap.add_argument("--selfcheck", action="store_true",
                    help="compute MATCH/DIFF/EXEC_ERR only on hit, single-call events; "
                         "exit non-zero if there is any DIFF or any unit drifted")
    a = ap.parse_args()

    # Always resolve paths before chdir: chdir first, then resolving a relative
    # path silently fails to find the file
    plan_p = Path(a.plan).resolve()
    out_p = Path(a.out).resolve()
    # Cache read and write paths must stay separate: **write** only writes its own
    # piece (lines over 4KB interleave under concurrent O_APPEND); **read** must
    # read every sibling piece under the main name. The two used to share one
    # variable -- after appending the .s<id> suffix and globbing with it, only
    # that piece could ever match, so cache reuse across pieces and across theta
    # (θ) never actually worked (and "backfilling between theta points via the
    # cache" is the only time-saving mechanism for laying out six points in the
    # execute cell).
    cache_main = Path(a.cache).resolve()
    if a.num_shards > 1:                     # One file per piece, to avoid interleaving under concurrent writes
        out_p = out_p.with_name(f"{out_p.stem}.s{a.shard_id}{out_p.suffix}")
    cache_p = cache_main.with_name(
        f"{cache_main.stem}.s{a.shard_id}{cache_main.suffix}")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    cache_p.parent.mkdir(parents=True, exist_ok=True)

    plan = [json.loads(l) for l in open(plan_p)]
    by_unit = {}
    for p in plan:
        # traj_path in the plan is **relative to the project root** (replay_inject.py
        # runs from the root), but this file needs to chdir into envs/appworld -- so
        # it must anchor back to the root before the chdir.
        # Hit this before: without anchoring it's FileNotFoundError and the whole
        # batch of units is ruined
        tp = Path(p["traj_path"])
        p["traj_path"] = str(tp if tp.is_absolute() else
                             (PROJ_ROOT / tp).resolve())
        by_unit.setdefault(p["unit"], []).append(p)
    # Pieces are split by unit; events of the same unit must land in the same
    # process (they share one world)
    # [Copied from envs/collect/run_appworld.py:69]'s splitting method
    units = sorted(by_unit)
    if a.limit_units:
        units = units[:a.limit_units]
    units = units[a.shard_id::a.num_shards]
    exp = a.exp if a.num_shards == 1 else f"{a.exp}_s{a.shard_id}"

    done = set()                             # Resume from a checkpoint
    if out_p.exists():
        for l in open(out_p):
            try:
                done.add(json.loads(l)["event"])
            except Exception:
                pass
    check_requote_version(cache_main)        # Logic changed without bumping the version number -> refuse to run
    cache = load_cache(cache_main)           # Read the main name -> all sibling pieces come in
    print(f"shard {a.shard_id}/{a.num_shards}: {len(units)} units "
          f"{sum(len(by_unit[u]) for u in units)} events exp={exp} "
          f"{len(done)} already present, {len(cache)} cached, seed={APPWORLD_SEED}",
          flush=True)

    os.chdir(APPWORLD_HOME)
    from appworld import AppWorld                              # noqa: E402

    stats = Counter()
    recs, unit_err, t00 = [], [], time.time()
    sink, csink = open(out_p, "a"), open(cache_p, "a")
    for i, u in enumerate(units):
        rows = [r for r in by_unit[u] if r["event"] not in done]
        if not rows:
            continue
        t0 = time.time()
        got = []
        try:
            replay_unit(AppWorld, u, rows, rows[0]["traj_path"], exp,
                        cache, csink, stats, got)
        except Exception as e:
            # If a unit crashes partway through: events already done are still flushed to
            # disk (got is what we hold), and the remaining events are simply missing from
            # exec_calls.jsonl -- merge-exec marks them exec_missing and counts them
            # separately, it never silently falls back to "no injection"
            unit_err.append(dict(unit=u, error=f"{type(e).__name__}: {e}",
                                 done=len(got), want=len(rows)))
            stats["unit_error"] += 1
            print(f"  UNIT FAIL {u}: {type(e).__name__}: {e} "
                  f"(done {len(got)}/{len(rows)})", flush=True)
        recs += got
        for r in got:                        # Event records are flushed to disk only here, none are dropped
            sink.write(json.dumps(r, ensure_ascii=False) + "\n")
        sink.flush()
        if not a.keep_outputs:
            # This unit's world is already closed; nobody reads its dbs/checkpoints/logs
            # again. Keeping them is 168 x 90KB piling up on the quota-limited disk, and
            # it also blocks the next theta point
            shutil.rmtree(Path(APPWORLD_HOME) / "experiments" / "outputs" /
                          exp / "tasks" / u, ignore_errors=True)
        print(f"  [{i + 1}/{len(units)}] {u} {len(rows)} ev "
              f"{time.time() - t0:.1f}s ok={stats['exec_ok']} "
              f"err={stats['exec_err']} cache={stats['cache_hit']} "
              f"drift={stats['unit_drift']}", flush=True)
    sink.close()
    csink.close()

    meta = dict(plan=str(plan_p), out=str(out_p), cache=str(cache_p), exp=exp,
                num_shards=a.num_shards, shard_id=a.shard_id,
                appworld_seed=APPWORLD_SEED,
                requote_version=REQUOTE_VERSION, trunc=TRUNC,
                n_units=len(units), n_events=len(recs),
                wall_s=round(time.time() - t00, 1),
                arg_modes=dict(Counter(
                    m for r in recs for m in (r.get("arg_modes") or []))),
                error_kind=dict(Counter(
                    r["error_kind"] for r in recs if r.get("error_kind"))),
                stats=dict(stats), unit_errors=unit_err)
    try:
        Path(str(out_p) + ".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1))
    except OSError as e:
        # Event records are already flushed one by one, so a crash here doesn't lose
        # results; but make it clear this is a disk problem, not a logic bug. /home is
        # a shared disk with a quota, and Errno 122 has actually been hit here
        print(f"cannot write meta ({e}) -- event records are already on disk at {out_p}, "
              f"a rerun after freeing space will hit the cache and finish in seconds", flush=True)
        raise
    print(json.dumps(meta, ensure_ascii=False, indent=1), flush=True)

    if not a.selfcheck:
        return 0

    # ---- Acceptance line: the predicted call matches the real one (hit), the
    #      code block contains exactly 1 call, and that code block is a clean
    #      one-line print(call) -- only when all three hold should the output of
    #      "executing this call alone" match the result recorded in the
    #      trajectory. Missing any one of the three means the two sides are not
    #      comparable at all, and folding it into the acceptance line only
    #      produces a false alarm for itself (two kinds of false alarm actually
    #      hit:
    #      (1) the code block is print("passwords:", apis...), so the recorded
    #      stdout carries extra prefixes;
    #      (2) when the call itself errors, the traceback echoes the source, and
    #      differing quote styles make it not match character for character).
    n_match = n_match_err = n_diff = n_err = n_skip = 0
    for r in recs:
        if not (r.get("full_call_ok") and r.get("n_calls_in_block") == 1):
            continue
        if not r.get("traj_bare_print"):
            n_skip += 1
            tag = "SKIP_MIX"          # The recorded code block is not a clean print(call) one-liner
        elif r.get("exec_out") is None:
            n_err += 1
            tag = "NO_EXEC"
        elif r["matched_traj_result"]:
            n_match += 1
            tag = "MATCH"
        elif r.get("matched_traj_error"):
            n_match_err += 1          # Error messages match, differing only in quotes echoed in the traceback
            tag = "MATCH_ERR"
        elif not r["exec_ok"]:
            n_err += 1
            tag = "EXEC_ERR"
        else:
            n_diff += 1
            tag = "DIFF"
        print(f"  {tag:9s} {r['unit']} s{r['step']} modes={r.get('arg_modes')} "
              f"| {str(r.get('exec_code'))[:86]} "
              f"| out={str(r.get('exec_out'))[:58]!r}", flush=True)
    bad_pv = [r["unit"] for r in recs if r.get("prefix_verbatim") is False]
    bad_dt = [r["unit"] for r in recs if r.get("dt_guard") is False]
    print(f"\nselfcheck: hit, single-call, clean-print events MATCH {n_match} "
          f"MATCH_ERR {n_match_err} DIFF {n_diff} EXEC_ERR/NO_EXEC {n_err}"
          f"(there are also {n_skip} hit, single-call events not comparable because the code block "
          f"is not a single clean print statement; not counted toward the acceptance line); prefix-drifted unit {sorted(set(bad_pv))};"
          f"units where the time guard failed {sorted(set(bad_dt))};unit-level failures {unit_err}")

    # If it drifts, pin down the cause: if a clean replay (with no probe inserted
    # at all) also drifts, the replay itself is not faithful; if it drifts only
    # with a probe inserted, the probe call wrote to the database and the
    # checkpoint rollback was not clean (risk 2)
    for u in sorted(set(bad_pv)):
        rows = by_unit[u]
        try:
            clean = replay_unit(AppWorld, u, rows, rows[0]["traj_path"],
                                exp + "_clean", {}, open(os.devnull, "w"),
                                Counter(), [], probe=False)
        except Exception as e:
            print(f"  fault attribution failed for {u}: {type(e).__name__}: {e}")
            continue
        rec = {st: r for st, _, r in load_steps(rows[0]["traj_path"])}
        bad = [st for st, got in clean if got != rec.get(st)]
        print(f"  {u} steps that drift even under a clean replay: {bad} "
              f"({'the replay itself is not faithful' if bad else 'suspected that the probe call did not clean up'})")
        if not a.keep_outputs:
            shutil.rmtree(Path(APPWORLD_HOME) / "experiments" / "outputs" /
                          (exp + "_clean"), ignore_errors=True)

    ok = (n_diff == 0 and n_err == 0 and not bad_pv and not bad_dt
          and not unit_err and n_match > 0)
    print("selfcheck " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
