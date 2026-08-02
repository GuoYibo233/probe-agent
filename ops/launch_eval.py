#!/usr/bin/env python3
"""tmux launcher for Phase C4 eval —— 批次无关。

流水线一直缺这一环:训练有 `ops/launch_probe.py`,评测却一直靠手搓 ssh+tmux。
本脚本把 SKILL.md Phase C4 的依赖顺序固化下来:

    tool 档(mtool/ctool) ── 出 REPLAY_REPORT.json + logits_test.pt
                 ↓ 提供温度与触发点 theta
    call 档(mext 吃同模型 mtool 的、cgen 吃同模型 ctool 的)

用法:
  # 先发工具格(互不依赖,一把并行)
  launch_eval.py tool --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --placement ops/c2_eval_tool_placement.json

  # 工具格出报告后再发参数格
  launch_eval.py call --batch c2 --data-root pipeline/data/alf_official_v1 \
      --env alfworld --placement ops/c2_eval_call_placement.json

排卡表一格一条:
  [{"model": "q36", "cell": "mtool", "host": "tokyo106", "gpu": 0,
    "extra": ["--risk", "0.1"]}, ...]

`cell` 在 tool 档取 mtool/ctool,在 call 档取 mext/cgen(写头的名字,脚本自己
换算成它依赖的工具格路径)。session 名 = eval_<batch>_<model>_<cell>。
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

MBERT = str(WD / "mbert-env/bin/python")
CPROBE = str(WD / "cprobe-env/bin/python")
EV = WD / "pipeline/eval"

# 工具格: 头 -> (解释器, 该头固定要带的参数)
# 双环境铁律: mbert 头走 mbert-env, causal 头走 cprobe-env(它要 import
# pipeline/train/train_causal_tool.py), 互不升级。
TOOL_CELLS = {
    "mtool": (MBERT, []),
    "ctool": (CPROBE, ["--head", "causal"]),
}
# 参数格: 头 -> (解释器, 脚本, 它依赖的工具格)
CALL_CELLS = {
    "mext": (MBERT, EV / "eval_mbert_call.py", "mtool"),
    "cgen": (CPROBE, EV / "eval_causal_call.py", "ctool"),
}


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


def build(stage, batch, data_root, env, model, cell, extra=None):
    runs = WD / "pipeline/runs"
    data = WD / data_root / model
    if not data.is_dir():
        sys.exit(f"数据目录不存在: {data}")

    if stage == "tool":
        if cell not in TOOL_CELLS:
            sys.exit(f"tool 档的 cell 只能是 {list(TOOL_CELLS)},给了 {cell}")
        py, head_args = TOOL_CELLS[cell]
        run = runs / f"{batch}_{model}_{cell}"
        if not run.is_dir():
            sys.exit(f"训练产物不存在: {run}")
        args = [py, str(EV / "eval_tool.py"), "--env", env,
                "--run", str(run), "--data", str(data)] + head_args
    else:
        if cell not in CALL_CELLS:
            sys.exit(f"call 档的 cell 只能是 {list(CALL_CELLS)},给了 {cell}")
        py, script, dep = CALL_CELLS[cell]
        head_run = runs / f"{batch}_{model}_{cell}"
        dep_run = runs / f"{batch}_{model}_{dep}"
        # 依赖顺序硬检查:工具格没出报告就拒绝发射(SKILL.md Phase C4 铁律)
        rep = dep_run / "REPLAY_REPORT.json"
        if not rep.is_file():
            sys.exit(f"依赖未就绪: {rep} 不存在——先把 {batch}_{model}_{dep} 评完")
        if not head_run.is_dir():
            sys.exit(f"训练产物不存在: {head_run}")
        if cell == "mext":
            args = [py, str(script), "--env", env, "--run", str(dep_run),
                    "--extractor", str(head_run), "--data", str(data)]
        else:
            args = [py, str(script), "--env", env, "--ctool-run", str(dep_run),
                    "--cgen-run", str(head_run), "--data", str(data)]

    if extra:
        args += list(extra)
    sess = f"eval_{batch}_{model}_{cell}"
    return sess, " ".join(shlex.quote(str(a)) for a in args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["tool", "call"],
                    help="tool=工具格(先跑) / call=参数格(吃工具格的触发点)")
    ap.add_argument("--batch", required=True, help="run_id 前缀,如 c2")
    ap.add_argument("--data-root", required=True, help="数据集版本目录")
    ap.add_argument("--env", required=True,
                    choices=["appworld", "alfworld", "bfcl", "tales"])
    ap.add_argument("--placement", required=True, help="排卡表 json")
    ap.add_argument("--dry-run", action="store_true", help="只打印不发射")
    args = ap.parse_args()

    LOGD.mkdir(exist_ok=True)
    plan = []
    for p in json.load(open(args.placement)):
        sess, cmd = build(args.stage, args.batch, args.data_root, args.env,
                          p["model"], p["cell"], p.get("extra"))
        plan.append((p["host"], p["gpu"], sess, cmd, f"{LOGD}/{sess}.log"))

    if args.dry_run:
        for host, gpu, sess, cmd, log in plan:
            print(f"[dry-run] {host} gpu{gpu} {sess}\n    {cmd}")
        print(f"\n共 {len(plan)} 格(dry-run,未发射)")
        return

    for host, gpu, sess, cmd, log in plan:
        launch(host, gpu, sess, cmd, log)
    time.sleep(6)
    print("\n--- alive check ---")
    for host, gpu, sess, cmd, log in plan:
        print(f"{sess}: {'ALIVE' if has_session(host, sess) else 'DEAD'}")


if __name__ == "__main__":
    main()
