#!/usr/bin/env python3
"""`run.py launch` 子命令(工单 09,实施计划 Task 11):一条命令把发射走完。

流程钉死成十步(计划文档的顺序,一步不许换序):
  1. 手写参数解析(gpu_jobs.py 的 iter 风格;未知参数留给任务透传,
     `--` 之后全透传)。
  2. task 模式: `t = TASKS[task]`;`--cmd` 模式跳过注册表。
  3. `gate_dirty(...)`(honor_dry=True,复用 run.py 的实现)。
  4. `--run-id`/`--track` 必填校验(record start 硬要求)。
  5. pieces 解析 + 分片注入(标了 shardable 才许多 `--piece`) + session/log 命名。
  6. `--dry-run` 打印每分片的 inner 命令,不碰任何登记。
  7. 逐 piece `probe_free`,任何一张非 FREE 整次拒绝(一张都不发射)。
  8. 逐 piece `tmux_launch`。
  9. 验活 30 秒:全部 piece 见到日志字节数增长即提前通过;窗口到时
     session 没了或 tail 有 Traceback 才算失败——已发射的不回滚,不登记。
  10. `register_all(...)` + 打印监控入口。

用法:
  python3 run.py launch <task> [任务参数...] --run-id ID --piece host:gpus [--piece ...]
      --track 方向 [--note ...] [--outdir DIR]
      [--stall-line 秒] [--escalate-line 秒] [--warmup-line 秒]
      [--service] [--allow-dirty] [--dry-run]
  python3 run.py launch --cmd '<完整命令>' --run-id ID --workdir DIR --piece ... (其余同上)

注册表外的一次性命令(2026-08-02 裁决的唯一例外)走 `--cmd` 逃生口:不查
TASKS、命令原样进 tmux,登记照做。
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

ALIVE_WINDOW_S = 30
ALIVE_POLL_S = 5

# 已知的 launch 级旗标:出现在这里的才被当参数解析,其余(含 `--` 之后的
# 一切)原样透传给任务/`--cmd`。
_VALUE_FLAGS = ("--cmd", "--workdir", "--run-id", "--track", "--note",
                "--outdir", "--piece", "--stall-line", "--escalate-line",
                "--warmup-line")
_BOOL_FLAGS = ("--service", "--allow-dirty", "--dry-run")


def _need(it, flag):
    try:
        return next(it)
    except StopIteration:
        raise SystemExit(f"{flag} 后面要跟一个值")


def parse_launch_argv(argv):
    """手写 iter 解析。返回 dict:
    task(str|None,--cmd 模式下 None) / cmd(str|None) / workdir(str|None) /
    run_id / track / note / outdir / pieces(list[str] 'host:gpus') /
    stall_line / escalate_line / warmup_line(float|None) / service(bool) /
    dry_run / allow_dirty(bool) / extra(list[str],透传给任务/--cmd)。

    `--` 之后的一切不再当 launch 旗标解析,直接进 extra——这是任务自己的
    `--outdir`/`--port` 这类同名旗标与 launch 自己的旗标区分开的办法。
    """
    argv = list(argv)
    if "--" in argv:
        i = argv.index("--")
        head, tail = argv[:i], argv[i + 1:]
    else:
        head, tail = argv, []

    p = dict(task=None, cmd=None, workdir=None, run_id=None, track=None,
              note=None, outdir=None, pieces=[], stall_line=None,
              escalate_line=None, warmup_line=None, service=False,
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
        elif a == "--service":
            p["service"] = True
        elif a == "--allow-dirty":
            p["allow_dirty"] = True
        elif a == "--dry-run":
            p["dry_run"] = True
        else:
            extra_head.append(a)  # 未知旗标留给任务透传
    p["extra"] = extra_head + tail
    return p


def build_pieces(p, t):
    """纯函数:pieces 解析 + 分片注入 + session/log 命名(工单 09 验收项)。
    `p` 是 `parse_launch_argv()` 的返回;`t` 是 `TASKS[task]` 或 None(`--cmd`
    模式)。返回 `[{"host","gpus","session","log","cmd","workdir"}, ...]`,
    `cmd` 是给 tmux/登记用的展示命令串(已含分片旗标,不含 cd/CUDA/tee)。"""
    if not p["pieces"]:
        raise SystemExit("launch 至少要一个 --piece host:gpus")

    specs, seen = [], set()
    for raw in p["pieces"]:
        if ":" not in raw:
            raise SystemExit(f"--piece 要 host:gpus 形式,给的是 {raw!r}")
        host, gpus = raw.split(":", 1)
        key = (host, gpus)
        if key in seen:
            raise SystemExit(f"重复的 --piece {raw}(同机同卡两个分片会互相踩,"
                             "拆成不同卡或分开发射)")
        seen.add(key)
        specs.append((host, gpus))

    n = len(specs)
    if t is not None and n > 1 and not t.get("shardable"):
        raise SystemExit(
            f"任务 {p['task']} 没标 shardable,不许给 {n} 个 --piece"
            "(分片编号不能靠人手拆,标了 shardable 的任务才能多分片)")

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
            cmd_str = p["cmd"]                # --cmd 模式:命令原样,不查注册表
        else:
            extra = list(p["extra"])
            if n > 1:
                extra += ["--shard-id", str(i), "--num-shards", str(n)]
            cmd_str = shlex.join(build_cmd(t, extra))
        pieces.append(dict(host=host, gpus=gpus, session=sess, log=log,
                           cmd=cmd_str, workdir=workdir))
    return pieces


def build_inner(cmd_str, workdir, gpus, log, env=None):
    """tmux 里真正跑的 shell 命令:与 launch_probe.py:57 的模板完全一致,
    env 变量有就前置 K=V 对。"""
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
    """发射后验活。全部 piece 都见到日志字节数增长就提前通过;窗口到时逐
    piece 查 has_session + tail 4KB 有没有 Traceback 判定最终成败。
    返回 (ok: bool, failed: [(piece, tail_str), ...])。"""
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
    p = parse_launch_argv(argv)

    t = None
    if p["cmd"] is None:
        if not p["task"]:
            raise SystemExit(
                "launch 要一个任务名,或 --cmd '<完整命令>'(run.py list 看任务)")
        t = TASKS.get(p["task"])
        if t is None:
            raise SystemExit(f"不认识: {p['task']}(run.py list 看任务)")

    dirty_probe = []
    if p["dry_run"]:
        dirty_probe.append("--dry-run")
    if p["allow_dirty"]:
        dirty_probe.append("--allow-dirty")
    gate_dirty(dirty_probe, honor_dry=True)

    if not p["run_id"]:
        raise SystemExit("launch 要 --run-id")
    if not p["track"]:
        raise SystemExit(
            "launch 要 --track(这个实验服务于哪个方向,跟 TIMELINE.md 对齐)")

    pieces = build_pieces(p, t)
    env = t.get("env", {}) if t is not None else {}
    for piece in pieces:
        piece["inner"] = build_inner(piece["cmd"], piece["workdir"],
                                     piece["gpus"], piece["log"], env)

    if p["dry_run"]:
        for piece in pieces:
            print(f"[dry-run] {piece['host']} gpu{piece['gpus']} {piece['session']}")
            print("    " + piece["inner"])
        print(f"\n共 {len(pieces)} 分片(dry-run,未发射,未登记)")
        return 0

    reasons = []
    for piece in pieces:
        ok, why = LC.probe_free(piece["host"], piece["gpus"])
        if not ok:
            reasons.append(f"{piece['host']}:{piece['gpus']} {why}")
    if reasons:
        raise SystemExit(
            "发射前实探到非 FREE 的卡,整次拒绝(一张都不发射):\n"
            + "\n".join("  " + r for r in reasons))

    for piece in pieces:
        Path(piece["log"]).parent.mkdir(parents=True, exist_ok=True)
        LC.tmux_launch(piece["host"], piece["session"], piece["inner"])

    ok, failed = verify_alive(pieces)
    if not ok:
        print(f"验活失败({ALIVE_WINDOW_S} 秒窗口):以下分片已发射但不登记"
              "(已发射的不回滚,杀进程是人的决定):")
        for piece, _tail in failed:
            print(f"  {piece['session']} ({piece['host']}:{piece['gpus']}) "
                  f"log={piece['log']}")
            print("  ---- 日志末 40 行 ----")
            print(tail_of(piece["log"], 40))
        return 1

    kind = "service" if p["service"] else "batch"
    now = time.time()
    rich_pieces = [dict(host=pc["host"], gpus=pc["gpus"], session=pc["session"],
                        log=pc["log"], cmd=pc["cmd"], launched_at=now, kind=kind,
                        stall_line=p["stall_line"], escalate_line=p["escalate_line"])
                   for pc in pieces]

    cmd_display = (rich_pieces[0]["cmd"] if len(rich_pieces) == 1
                   else "; ".join(rp["cmd"] for rp in rich_pieces))
    monitor = {"warmup_s": p["warmup_line"]} if p["warmup_line"] is not None else None

    receipt = LC.register_all(p["run_id"], pieces[0]["workdir"], rich_pieces,
                              p["track"], cmd_display, note=p["note"],
                              outdir=p["outdir"], monitor=monitor)
    print(receipt)
    print("\n监控: python3 run.py gpu-jobs  /  python3 run.py gpu-jobs watch  /"
          "  网页 http://localhost:8377(ssh 端口转发)")
    return 0
