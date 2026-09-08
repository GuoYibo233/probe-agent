#!/usr/bin/env python3
"""`run.py launch` subcommand (ticket 09, implementation plan Task 11): finishes a
launch in one command. Refire mode (ticket 10, implementation plan Task 12) is at
the end of the file in `cmd_refire`.

The flow is fixed as ten steps (the order in the plan document, no step may be
reordered):
  1. Hand-written argument parsing (gpu_jobs.py's iter style; unknown arguments are
     passed through to the task, everything after `--` passes through entirely).
  2. task mode: `t = TASKS[task]`; `--cmd` mode skips the registry.
  3. `gate_dirty(...)` (honor_dry=True, reuses run.py's implementation).
  4. Required validation of `--run-id`/`--track` (a hard requirement of record start);
     if `--service` is given, `--port` must also be given (C2, final-review
     2026-08-09: without a port, the sampler's `probe_port` verdict chain breaks and
     the service piece gets stuck in warm-up).
  5. Pieces parsing + piece injection (only allows multiple `--piece` if marked
     shardable) + session/log naming.
  6. `--dry-run` prints the inner command for each piece, without touching any
     registration.
  7. `probe_free` per piece; if any card is not FREE, reject the whole call (nothing
     gets launched).
  8. `tmux_launch` per piece.
  9. 30-second alive check: passes early for all pieces the moment the log's byte
     count grows; if the window runs out, it's a failure only if the session is gone
     or the tail has a Traceback -- anything already launched is not rolled back and
     not registered.
  10. `register_all(...)` + print the monitoring entry points.

Usage:
  python3 run.py launch <task> [task args...] --run-id ID --piece host:gpus [--piece ...]
      --track DIRECTION [--note ...] [--outdir DIR]
      [--stall-line SECONDS] [--escalate-line SECONDS] [--warmup-line SECONDS]
      [--service --port PORT] [--allow-dirty] [--dry-run]
  python3 run.py launch --cmd '<full command>' --run-id ID --workdir DIR --piece ... (rest as above)

One-off commands outside the registry (the sole exception ruled on 2026-08-02) go
through the `--cmd` escape hatch: TASKS is not consulted, the command goes into
tmux as-is, and registration still happens.
"""
import shlex
import sys
import time
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parent
ROOT = OPS_DIR.parent

sys.path.insert(0, str(ROOT))
from run import TASKS, build_cmd, gate_dirty, tail_of  # noqa: E402

sys.path.insert(0, str(OPS_DIR))
import launch_common as LC  # noqa: E402
import gpu_jobs  # noqa: E402
import sampler as SAMP  # noqa: E402

ALIVE_WINDOW_S = 30
ALIVE_POLL_S = 5

# Known launch-level flags: only what appears here gets parsed as an argument; anything
# else (including everything after `--`) passes through unchanged to the task/`--cmd`.
_VALUE_FLAGS = ("--cmd", "--workdir", "--run-id", "--track", "--note",
                "--outdir", "--piece", "--stall-line", "--escalate-line",
                "--warmup-line", "--port")
_BOOL_FLAGS = ("--service", "--allow-dirty", "--dry-run")


def _need(it, flag):
    try:
        return next(it)
    except StopIteration:
        raise SystemExit(f"{flag} must be followed by a value")


def parse_launch_argv(argv):
    """Hand-written iter-style parsing. Returns a dict:
    task (str|None, None in --cmd mode) / cmd (str|None) / workdir (str|None) /
    run_id / track / note / outdir / pieces (list[str] 'host:gpus') /
    stall_line / escalate_line / warmup_line (float|None) / service (bool) /
    port (int|None, the service piece's alive-check port; see the --service
    validation in cmd_launch) /
    dry_run / allow_dirty (bool) / extra (list[str], passed through to the task/--cmd).

    Everything after `--` is no longer parsed as a launch flag and goes straight
    into extra -- this is how the task's own same-named flags like `--outdir`/`--port`
    are kept separate from launch's own flags (the task's own --port, e.g. a port
    argument that some task script defines itself, is written after `--`).
    """
    argv = list(argv)
    if "--" in argv:
        i = argv.index("--")
        head, tail = argv[:i], argv[i + 1:]
    else:
        head, tail = argv, []

    p = dict(task=None, cmd=None, workdir=None, run_id=None, track=None,
              note=None, outdir=None, pieces=[], stall_line=None,
              escalate_line=None, warmup_line=None, service=False, port=None,
              dry_run=False, allow_dirty=False, extra=[])

    if head and not head[0].startswith("-"):
        p["task"] = head[0]
        head = head[1:]

    extra_head = []
    it = iter(head)
    for a in it:
        if a == "--cmd":
            p["cmd"] = _need(it, a)
        elif a == "--workdir":
            p["workdir"] = _need(it, a)
        elif a == "--run-id":
            p["run_id"] = _need(it, a)
        elif a == "--track":
            p["track"] = _need(it, a)
        elif a == "--note":
            p["note"] = _need(it, a)
        elif a == "--outdir":
            p["outdir"] = _need(it, a)
        elif a == "--piece":
            p["pieces"].append(_need(it, a))
        elif a == "--stall-line":
            p["stall_line"] = float(_need(it, a))
        elif a == "--escalate-line":
            p["escalate_line"] = float(_need(it, a))
        elif a == "--warmup-line":
            p["warmup_line"] = float(_need(it, a))
        elif a == "--port":
            p["port"] = int(_need(it, a))
        elif a == "--service":
            p["service"] = True
        elif a == "--allow-dirty":
            p["allow_dirty"] = True
        elif a == "--dry-run":
            p["dry_run"] = True
        else:
            extra_head.append(a)  # Unknown flags are left to pass through to the task
    p["extra"] = extra_head + tail
    return p


def build_pieces(p, t):
    """Pure function: pieces parsing + piece injection + session/log naming (ticket 09
    acceptance item). `p` is the return value of `parse_launch_argv()`; `t` is
    `TASKS[task]` or None (`--cmd` mode). Returns
    `[{"host","gpus","session","log","cmd","workdir"}, ...]`, where `cmd` is the
    display command string used for tmux/registration (includes the piece flags,
    excludes cd/CUDA/tee)."""
    if not p["pieces"]:
        raise SystemExit("launch needs at least one --piece host:gpus")

    specs, claimed_by_host = [], {}
    for raw in p["pieces"]:
        if ":" not in raw:
            raise SystemExit(f"--piece must be in host:gpus form, got {raw!r}")
        host, gpus = raw.split(":", 1)
        gpu_ids = set(g for g in gpus.split(",") if g)
        prior = claimed_by_host.setdefault(host, set())
        clash = prior & gpu_ids
        if clash:
            raise SystemExit(
                f"--piece {raw} overlaps an existing piece on the same host at gpu {','.join(sorted(clash))}"
                "(two pieces on the same host and card collide with each other, split them onto different cards or launch separately)")
        prior |= gpu_ids
        specs.append((host, gpus))

    n = len(specs)
    if t is not None and n > 1 and not t.get("shardable"):
        raise SystemExit(
            f"job {p['task']} is not marked shardable, giving it {n} --piece is not allowed"
            "(piece indices cannot be split by hand, only a job marked shardable can take multiple pieces)")

    if t is not None:
        workdir = t.get("cwd", str(ROOT))
    else:
        workdir = p["workdir"] or str(ROOT)
    logdir = Path(workdir) / "logs"

    pieces = []
    for i, (host, gpus) in enumerate(specs):
        hs = host.replace("tokyo", "")
        gs = gpus.replace(",", "-")
        sess = f"new1_{p['run_id']}_t{hs}g{gs}"
        log = str(logdir / f"{sess}.log")
        if p["cmd"] is not None:
            cmd_str = p["cmd"]                # --cmd mode: command as-is, registry not consulted
        else:
            extra = list(p["extra"])
            if n > 1:
                extra += ["--shard-id", str(i), "--num-shards", str(n)]
            cmd_str = shlex.join(build_cmd(t, extra))
        pieces.append(dict(host=host, gpus=gpus, session=sess, log=log,
                           cmd=cmd_str, workdir=workdir))
    return pieces


def build_inner(cmd_str, workdir, gpus, log, env=None):
    """The shell command actually run inside tmux: identical to the template at
    launch_probe.py:57; if env variables are given, K=V pairs are prefixed."""
    prefix = ""
    if env:
        prefix = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items()) + " "
    return f"cd {workdir} && {prefix}CUDA_VISIBLE_DEVICES={gpus} {cmd_str} 2>&1 | tee {log}"


def _log_size(path):
    p = Path(path)
    return p.stat().st_size if p.exists() else 0


def _tail_bytes(path, n=4096):
    p = Path(path)
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - n))
        return f.read().decode("utf-8", "replace")


def verify_alive(pieces, window_s=ALIVE_WINDOW_S, poll_s=ALIVE_POLL_S):
    """Alive check after launch. Passes early once every piece's log byte count has
    grown; when the window runs out, the final pass/fail is decided per piece by
    checking has_session + whether the last 4KB of the tail has a Traceback.
    Returns (ok: bool, failed: [(piece, tail_str), ...])."""
    start_sizes = {p["session"]: _log_size(p["log"]) for p in pieces}
    seen_output = {p["session"]: False for p in pieces}
    deadline = time.monotonic() + window_s
    while True:
        for p in pieces:
            sess = p["session"]
            if not seen_output[sess] and _log_size(p["log"]) > start_sizes[sess]:
                seen_output[sess] = True
        if all(seen_output.values()) or time.monotonic() >= deadline:
            break
        time.sleep(poll_s)
    failed = []
    for p in pieces:
        alive = LC.has_session(p["host"], p["session"])
        tail = _tail_bytes(p["log"], 4096)
        if not alive or "Traceback" in tail:
            failed.append((p, tail))
    return (not failed), failed


def cmd_launch(argv):
    if "--refire" in argv:
        return cmd_refire(argv)
    p = parse_launch_argv(argv)

    t = None
    if p["cmd"] is None:
        if not p["task"]:
            raise SystemExit(
                "launch needs a job name, or --cmd '<full command>' (see run.py list for jobs)")
        t = TASKS.get(p["task"])
        if t is None:
            raise SystemExit(f"unrecognized: {p['task']} (see run.py list for jobs)")

    dirty_probe = []
    if p["dry_run"]:
        dirty_probe.append("--dry-run")
    if p["allow_dirty"]:
        dirty_probe.append("--allow-dirty")
    gate_dirty(dirty_probe, honor_dry=True)

    if not p["run_id"]:
        raise SystemExit("launch needs --run-id")
    if not p["track"]:
        raise SystemExit(
            "launch needs --track (which direction this experiment serves, align with TIMELINE.md)")
    if p["service"] and p["port"] is None:
        # C2 (final-review, 2026-08-09): without a port, the rich piece has no "port" field,
        # so sampler.update_piece_state's probe_port branch never gets a port and the verdict
        # stays stuck in warm-up -- a service-kind piece must pin the port into the ledger at
        # launch time.
        raise SystemExit("serve profile needs --port")

    pieces = build_pieces(p, t)
    env = t.get("env", {}) if t is not None else {}
    for piece in pieces:
        piece["inner"] = build_inner(piece["cmd"], piece["workdir"],
                                     piece["gpus"], piece["log"], env)

    if p["dry_run"]:
        for piece in pieces:
            print(f"[dry-run] {piece['host']} gpu{piece['gpus']} {piece['session']}")
            print("    " + piece["inner"])
        print(f"\n{len(pieces)} pieces total (dry-run, not launched, not registered)")
        return 0

    reasons = []
    for piece in pieces:
        ok, why = LC.probe_free(piece["host"], piece["gpus"])
        if not ok:
            reasons.append(f"{piece['host']}:{piece['gpus']} {why}")
    if reasons:
        raise SystemExit(
            "pre-launch live probe found a non-FREE card, the whole launch is refused (not a single one launches):\n"
            + "\n".join("  " + r for r in reasons))

    for piece in pieces:
        Path(piece["log"]).parent.mkdir(parents=True, exist_ok=True)
        LC.tmux_launch(piece["host"], piece["session"], piece["inner"])

    ok, failed = verify_alive(pieces)
    if not ok:
        print(f"liveness check failed ({ALIVE_WINDOW_S}-second window): the following pieces were launched but not registered"
              "(launched pieces are not rolled back, killing the process is a human decision):")
        for piece, _tail in failed:
            print(f"  {piece['session']} ({piece['host']}:{piece['gpus']}) "
                  f"log={piece['log']}")
            print("  ---- last 40 log lines ----")
            print(tail_of(piece["log"], 40))
        return 1

    kind = "service" if p["service"] else "batch"
    now = time.time()
    rich_pieces = [dict(host=pc["host"], gpus=pc["gpus"], session=pc["session"],
                        log=pc["log"], cmd=pc["cmd"], launched_at=now, kind=kind,
                        stall_line=p["stall_line"], escalate_line=p["escalate_line"],
                        task=p["task"], port=p["port"])
                   for pc in pieces]

    cmd_display = (rich_pieces[0]["cmd"] if len(rich_pieces) == 1
                   else "; ".join(rp["cmd"] for rp in rich_pieces))
    monitor = {"warmup_s": p["warmup_line"]} if p["warmup_line"] is not None else None

    receipt = LC.register_all(p["run_id"], pieces[0]["workdir"], rich_pieces,
                              p["track"], cmd_display, note=p["note"],
                              outdir=p["outdir"], monitor=monitor)
    print(receipt)
    print("\nmonitor: python3 run.py gpu-jobs  /  python3 run.py gpu-jobs watch  /"
          "  web http://localhost:8377 (ssh port forward)")
    return 0


def parse_refire_argv(argv):
    """Argument parsing for refire mode (ticket 10). Returns a dict:
    run_id / idx (int) / piece (str|None, 'host:gpus') / allow_dirty (bool).
    Only these four flags are recognized -- refire is not a new task and doesn't
    accept the rest of launch's normal-mode arguments."""
    p = dict(run_id=None, idx=None, piece=None, allow_dirty=False)
    it = iter(argv)
    for a in it:
        if a == "--refire":
            p["run_id"] = _need(it, a)
        elif a == "--idx":
            p["idx"] = int(_need(it, a))
        elif a == "--piece":
            p["piece"] = _need(it, a)
        elif a == "--allow-dirty":
            p["allow_dirty"] = True
        else:
            raise SystemExit(f"unrecognized argument in --refire mode: {a!r}"
                              "(only --refire/--idx/--piece/--allow-dirty are recognized)")
    return p


def cmd_refire(argv):
    """`run.py launch --refire <run_id> --idx <piece index> [--piece host:gpus]
    [--allow-dirty]` (ticket 10, implementation plan Task 12).

    A live session is rejected → the target card (given by --piece, or the original
    card) is probed and rejected if not FREE → the cmd stored for that piece in the
    ledger is resent as-is, the env prefix is restored as-is (the session name stays
    the same, the log switches to a new file) → the ledger's host/gpus/log/launched_at
    for that piece are updated in place. No new record is opened, and register is not
    repeated -- refire is not a new task, and only the ledger needs to be touched for
    registration. Once the sampler sees launched_at change, it automatically reopens
    that piece's heartbeat timeline and increments refires (ticket 02/Task 6, already
    implemented).

    env prefix: the ledger piece does not store env's actual key-value pairs (env may
    carry secrets, `ops/jobs.json` is a git-tracked file, and writing them in as-is
    would commit secrets into the ledger along with version control -- finding N1,
    2026-08-08). The ledger piece stores only `task` (the task name, written into the
    rich piece by `cmd_launch`); on refire, this task name is used to look up the
    *current* `TASKS[task]["env"]`, computed fresh and passed to `build_inner`, with the
    original value never written to disk. This means that if the task registry's `env`
    definition was changed between the original launch and the refire, the refire gets
    the changed value, not a snapshot from the time of the original launch -- this cost
    is traded for the harder guarantee that "env's original value is never written into
    a git-tracked file." `--cmd` mode (task is None) and an old ledger (the piece has no
    `task` field, or `task` is not in the current TASKS) are both treated the same way,
    falling back to an empty dict, without raising an error.
    """
    p = parse_refire_argv(argv)
    if not p["run_id"]:
        raise SystemExit("--refire must be followed by run_id (the ledger job name to refire)")
    if p["idx"] is None:
        raise SystemExit("refire needs --idx <piece number> (the index into the ledger's pieces)")

    dirty_probe = ["--allow-dirty"] if p["allow_dirty"] else []
    gate_dirty(dirty_probe, honor_dry=True)

    reg = gpu_jobs.load_reg()
    job = next((j for j in reg["active"] if j["name"] == p["run_id"]), None)
    if job is None:
        raise SystemExit(f"no active job {p['run_id']!r} in the job ledger")
    pieces = job["pieces"]
    if not (0 <= p["idx"] < len(pieces)):
        raise SystemExit(
            f"{p['run_id']} has only {len(pieces)} pieces, --idx {p['idx']} is out of range")
    piece = pieces[p["idx"]]

    if LC.has_session(piece["host"], piece["session"]):
        raise SystemExit(
            f"{piece['session']} ({piece['host']}) is still alive, refire only applies to dead pieces"
            "(a live session may not be refired)")

    if p["piece"]:
        if ":" not in p["piece"]:
            raise SystemExit(f"--piece must be in host:gpus form, got {p['piece']!r}")
        host, gpus = p["piece"].split(":", 1)
    else:
        host, gpus = piece["host"], piece["gpus"]

    ok, why = LC.probe_free(host, gpus)
    if not ok:
        raise SystemExit(
            f"target card {host}:{gpus} is not FREE, refire refused ({why}); "
            "use this error to switch cards, retry with --piece host:gpus")

    st = SAMP.load_state()
    refires = st.get(SAMP.piece_key(p["run_id"], p["idx"]), {}).get("refires", 0)
    sess = piece["session"]
    new_log = str(Path(piece["log"]).parent / f"{sess}.r{refires + 1}.log")
    Path(new_log).parent.mkdir(parents=True, exist_ok=True)
    task_name = piece.get("task")
    t = TASKS.get(task_name) if task_name else None
    env = t.get("env", {}) if t is not None else {}  # Computed and passed through fresh; the original value is never written to disk
    inner = build_inner(piece["cmd"], job["workdir"], gpus, new_log, env)
    LC.tmux_launch(host, sess, inner)

    now = time.time()

    def _mutate(reg2):
        job2 = next(j for j in reg2["active"] if j["name"] == p["run_id"])
        piece2 = job2["pieces"][p["idx"]]
        piece2["host"] = host
        piece2["gpus"] = gpus
        piece2["log"] = new_log
        piece2["launched_at"] = now

    gpu_jobs.mutate_reg(_mutate)

    print(f"refire: {p['run_id']}#{p['idx']} ({sess}) {host}:{gpus} "
          f"log={new_log}")
    return 0
