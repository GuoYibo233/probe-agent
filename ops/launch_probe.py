#!/usr/bin/env python3
"""tmux launcher for Phase C probe training —— 批次无关的泛化版。

取代 `ops/launch_c1.py`(它把批次前缀 `c1_`、数据集 `aw_official_v1`、
smoke 的模型 `q35` 三处写死,每加一个批次就得复制一份)。

用法:
  # 四格 smoke(一个模型,四张卡)
  launch_probe.py smoke --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --model q36 --host tokyo107 --gpus 0,1,2,3

  # 全量(排卡表驱动)
  launch_probe.py full --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --placement ops/c2_placement.json

排卡表是一个 json 数组,一格一条:
  [{"model": "q36", "cell": "mtool", "host": "tokyo107", "gpu": 0,
    "extra": ["--align-tol", "3e-4"]}, ...]

run_id = <batch>_<model>_<cell>,四处一致(数据目录名 / tmux session / 台账 name /
commit message),见 CLAUDE.md「记录」一节。
"""
import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

WD = Path(__file__).resolve().parent.parent
LOGD = WD / "logs"

LOCAL = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
ALIAS = {"shiga": "tokyo105", "saitama": "tokyo108"}
LOCAL = ALIAS.get(LOCAL, LOCAL)

# 格 -> (解释器, 训练脚本, 该格固定要带的参数)。
# 唯一真源在仓库根 run.py 的 CELLS(2026-08-02 起),这里只 import 不再另抄一份
# ——两张同构表必漂移,而那种漂移是静默的。双环境铁律也记在 run.py 里。
sys.path.insert(0, str(WD))
from run import CELLS, CELL_ORDER  # noqa: E402
sys.path.insert(0, str(WD / "ops"))
from runmeta import append_runmeta  # noqa: E402


def has_session(host, s):
    cmd = f"tmux has-session -t {shlex.quote(s)}"
    argv = ["bash", "-c", cmd] if host == LOCAL else ["ssh", "-n", host, cmd]
    return subprocess.run(argv, capture_output=True, text=True).returncode == 0


def launch(host, gpu, session, cmd, log):
    if has_session(host, session):
        print(f"SKIP (exists): {session}")
        return False
    inner = f"cd {WD} && CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
    tmux = f"tmux new-session -d -s {shlex.quote(session)} {shlex.quote(inner)}"
    argv = ["bash", "-c", tmux] if host == LOCAL else ["ssh", "-n", host, tmux]
    subprocess.run(argv, check=True)
    print(f"LAUNCHED {session}  ({host} gpu{gpu})  log={log}")
    return True


def build(batch, data_root, env, model, cell, smoke, extra=None):
    py, script, base_args = CELLS[cell]
    rid = f"{batch}_{model}_{cell}"
    data = Path(data_root) / model
    if not data.is_dir():
        sys.exit(f"数据目录不存在: {data}")
    out = WD / ("pipeline/runs/smoke/" + rid + "_smoke" if smoke else "pipeline/runs/" + rid)
    args = [py, str(script), "--data", str(data), "--out", str(out), "--env", env]
    args += base_args
    if smoke:
        args.append("--smoke")
    if extra:
        args += list(extra)
    return rid, " ".join(shlex.quote(a) for a in args), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "full"])
    ap.add_argument("--batch", required=True, help="run_id 前缀,如 c2")
    ap.add_argument("--data-root", required=True, help="数据集版本目录(其下一模型一子目录)")
    ap.add_argument("--env", required=True,
                    choices=["appworld", "alfworld", "bfcl", "tales"])
    ap.add_argument("--model", help="smoke 模式:拿哪个模型的数据跑四格")
    ap.add_argument("--host", default="tokyo107", help="smoke 模式:跑在哪台")
    ap.add_argument("--gpus", default="0,1,2,3", help="smoke 模式:四张卡")
    ap.add_argument("--placement", help="full 模式:排卡表 json")
    ap.add_argument("--force", action="store_true",
                    help="透传训练脚本的 --force:同 out 目录重训(B7 守卫逃生,"
                         "smoke 重跑必用——smoke 目录名是确定性推出的)")
    ap.add_argument("--dry-run", action="store_true", help="只打印不发射")
    args = ap.parse_args()
    force = ["--force"] if args.force else []

    LOGD.mkdir(exist_ok=True)
    plan = []

    if args.mode == "smoke":
        if not args.model:
            sys.exit("smoke 模式要 --model")
        gpus = [g.strip() for g in args.gpus.split(",")]
        if len(gpus) != len(CELL_ORDER):
            sys.exit(f"--gpus 要给 {len(CELL_ORDER)} 张卡,给了 {len(gpus)}")
        for cell, gpu in zip(CELL_ORDER, gpus):
            rid, cmd, out = build(args.batch, args.data_root, args.env,
                                  args.model, cell, True, force or None)
            hs = args.host.replace("tokyo", "")
            sess = f"new1_{rid}_smoke_t{hs}g{gpu}"
            plan.append((args.host, gpu, sess, cmd, f"{LOGD}/{sess}.log", out, rid))
    else:
        if not args.placement:
            sys.exit("full 模式要 --placement")
        for p in json.load(open(args.placement)):
            rid, cmd, out = build(args.batch, args.data_root, args.env,
                                  p["model"], p["cell"], False,
                                  list(p.get("extra") or []) + force)
            host, gpu = p["host"], p["gpu"]
            hs = host.replace("tokyo", "")
            sess = f"new1_{rid}_t{hs}g{gpu}"
            plan.append((host, gpu, sess, cmd, f"{LOGD}/{sess}.log", out, rid))

    if args.dry_run:
        for host, gpu, sess, cmd, log, out, rid in plan:
            print(f"[dry-run] {host} gpu{gpu} {sess}\n    {cmd}")
        print(f"\n共 {len(plan)} 格(dry-run,未发射)")
        return

    for host, gpu, sess, cmd, log, out, rid in plan:
        if launch(host, gpu, sess, cmd, log):
            # 产物钉代码:发射成功立刻把 commit+argv 落进产物目录(审计 B6)。
            # 记账失败只告警不中断——不能让 RUNMETA 把剩下的发射打死
            try:
                append_runmeta(out, cmd, kind="train",
                               extra={"run_id": rid, "session": sess,
                                      "launch_host": host, "gpu": gpu,
                                      "log": log,
                                      "placement": args.placement or ""})
            except Exception as e:
                print(f"WARN RUNMETA 没写上({out}): {e}", file=sys.stderr)
    time.sleep(6)
    print("\n--- alive check ---")
    for host, gpu, sess, cmd, log, out, rid in plan:
        print(f"{sess}: {'ALIVE' if has_session(host, sess) else 'DEAD'}")


if __name__ == "__main__":
    main()
