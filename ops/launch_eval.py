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

# 评测格唯一真源在仓库根 run.py 的 EVAL_CELLS(2026-08-02 审计 C14 起),
# 这里只 import——解释器/脚本/固定参数全从对应 TASKS 条目取,不再另抄一份。
# 双环境铁律(mbert 头走 mbert-env,causal 头走 cprobe-env)也记在 run.py 里。
sys.path.insert(0, str(WD))
from run import EVAL_CELLS, PY, TASKS  # noqa: E402
sys.path.insert(0, str(WD / "ops"))
from runmeta import append_runmeta  # noqa: E402

TOOL_KEYS = [c for c, (_, dep) in EVAL_CELLS.items() if dep is None]
CALL_KEYS = [c for c, (_, dep) in EVAL_CELLS.items() if dep is not None]


def cell_cmd_parts(cell):
    """格 -> (解释器, 脚本绝对路径, 固定参数, 依赖格|None),全部取自 run.py。"""
    task_name, dep = EVAL_CELLS[cell]
    t = TASKS[task_name]
    return (t.get("prog") or PY[t["py"]], str(WD / t["script"]),
            list(t.get("args", [])), dep)


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
        if cell not in TOOL_KEYS:
            sys.exit(f"tool 档的 cell 只能是 {TOOL_KEYS},给了 {cell}")
        py, script, fixed, _ = cell_cmd_parts(cell)
        run = runs / f"{batch}_{model}_{cell}"
        # 看 best/ 不看目录本身:RUNMETA 落盘会把空目录建出来,目录存在
        # 早已不等于训练出过东西(审计复核)
        if not (run / "best").is_dir():
            sys.exit(f"训练产物不存在: {run}/best")
        args = [py, script, "--env", env,
                "--run", str(run), "--data", str(data)] + fixed
        meta_dir = run
    else:
        if cell not in CALL_KEYS:
            sys.exit(f"call 档的 cell 只能是 {CALL_KEYS},给了 {cell}")
        py, script, fixed, dep = cell_cmd_parts(cell)
        head_run = runs / f"{batch}_{model}_{cell}"
        dep_run = runs / f"{batch}_{model}_{dep}"
        # 依赖顺序硬检查:工具格没出报告就拒绝发射(SKILL.md Phase C4 铁律)
        rep = dep_run / "REPLAY_REPORT.json"
        if not rep.is_file():
            sys.exit(f"依赖未就绪: {rep} 不存在——先把 {batch}_{model}_{dep} 评完")
        if not (head_run / "best").is_dir():
            sys.exit(f"训练产物不存在: {head_run}/best")
        # 两个 call 脚本的参数形状不同,这是发射器自己的知识(脚本 argparse 定的)
        if cell == "mext":
            args = [py, script, "--env", env, "--run", str(dep_run),
                    "--extractor", str(head_run), "--data", str(data)] + fixed
        else:
            args = [py, script, "--env", env, "--ctool-run", str(dep_run),
                    "--cgen-run", str(head_run), "--data", str(data)] + fixed
        meta_dir = head_run

    if extra:
        args += list(extra)
    sess = f"eval_{batch}_{model}_{cell}"
    return sess, " ".join(shlex.quote(str(a)) for a in args), meta_dir


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
        sess, cmd, meta_dir = build(args.stage, args.batch, args.data_root,
                                    args.env, p["model"], p["cell"],
                                    p.get("extra"))
        plan.append((p["host"], p["gpu"], sess, cmd,
                     f"{LOGD}/{sess}.log", meta_dir))

    if args.dry_run:
        for host, gpu, sess, cmd, log, meta_dir in plan:
            print(f"[dry-run] {host} gpu{gpu} {sess}\n    {cmd}")
        print(f"\n共 {len(plan)} 格(dry-run,未发射)")
        return

    for host, gpu, sess, cmd, log, meta_dir in plan:
        if launch(host, gpu, sess, cmd, log):
            # 产物钉代码:发射成功立刻把 commit+argv 落进产物目录(审计 B6)。
            # 记账失败只告警不中断——不能让 RUNMETA 把剩下的发射打死
            try:
                append_runmeta(meta_dir, cmd, kind=f"eval_{args.stage}",
                               extra={"session": sess, "launch_host": host,
                                      "gpu": gpu, "log": log,
                                      "placement": args.placement})
            except Exception as e:
                print(f"WARN RUNMETA 没写上({meta_dir}): {e}", file=sys.stderr)
    time.sleep(6)
    print("\n--- alive check ---")
    for host, gpu, sess, cmd, log, meta_dir in plan:
        print(f"{sess}: {'ALIVE' if has_session(host, sess) else 'DEAD'}")


if __name__ == "__main__":
    main()
