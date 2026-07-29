"""汇总全量批次的三指标:准确率 / 每步思考中位(字符) / 每轨迹调用数。

与 CALIB_v0.md 同口径,方便和 5 题校准批直接对比。
用法: python summarize_full.py
"""

import json
import statistics
from pathlib import Path

RUNS = Path("/home/y-guo/reproduce/new1/envs/runs")
MODELS = ["q35", "q36", "gptoss"]


def read_traj(path):
    """返回 (meta, gens, envs, final);坏行跳过。"""
    meta, gens, envs, final = {}, [], [], {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = r.get("type")
        if t == "meta":
            meta = r
        elif t == "gen":
            gens.append(r)
        elif t == "env":
            envs.append(r)
        elif t == "final":
            final = r
    return meta, gens, envs, final


def summarize(d, success_fn):
    rows = []
    for p in sorted(d.glob("*.jsonl")):
        meta, gens, envs, final = read_traj(p)
        if not final:
            continue
        think = [len(g.get("reasoning") or "") for g in gens]
        rows.append({
            "ok": success_fn(final),
            "think": think,
            # 有动作的步 = 一次真实工具调用
            "calls": sum(1 for e in envs if e.get("action")),
            "steps": final.get("steps", len(gens)),
        })
    if not rows:
        return None
    all_think = [t for r in rows for t in r["think"]]
    return {
        "n": len(rows),
        "acc": sum(r["ok"] for r in rows) / len(rows),
        "think_med": statistics.median(all_think) if all_think else 0,
        "calls": statistics.mean(r["calls"] for r in rows),
        "steps": statistics.mean(r["steps"] for r in rows),
    }


def aw_ok(final):
    return "'success': True" in str(final.get("eval", ""))


def tl_ok(final):
    return bool(final.get("won"))


def main():
    print(f"{'格子':<28} {'n':>4} {'acc':>6} {'思考中位/步':>11} "
          f"{'调用/轨迹':>9} {'步数均值':>8}")
    print("-" * 74)
    for env_name, sub, ok_fn in [("AppWorld dev", "full_appworld", aw_ok),
                                 ("TALES L1 6房间", "full_tales_L1", tl_ok),
                                 ("TALES L2 11房间", "full_tales_L2", tl_ok)]:
        for m in MODELS:
            d = RUNS / sub / m
            if not d.exists():
                continue
            s = summarize(d, ok_fn)
            if not s:
                continue
            print(f"{env_name + ' x ' + m:<28} {s['n']:>4} {s['acc']:>6.2f} "
                  f"{s['think_med']:>11.0f} {s['calls']:>9.1f} "
                  f"{s['steps']:>8.1f}")


if __name__ == "__main__":
    main()
