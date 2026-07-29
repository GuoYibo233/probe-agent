"""干闭环 smoke:探针服务 vs 离线回放评测的一致性对账(不需要 vLLM)。

把 v3 test 集样本按事件分组、按 sent_idx 顺序经 HTTP 喂探针服务,首次
conf>=θ 记预测(与 eval_replay.replay 同语义),复算 coverage/触发精度/
earliness,与该 run 的 REPLAY_REPORT.json test_frozen 并排。判据:
逐事件触发决定与离线一致(同模型同温度同 θ,唯一差异是 HTTP+逐条 vs
批量,数字应完全相等;浮点边缘允许 ±1 事件)。

用法(先起 probe_server,再任意 python3 跑本脚本,纯 CPU):
  python3 envs/loop/smoke_dry.py --server http://127.0.0.1:8201 \
      --run envs/bert_runs/bfcl_v3 --data envs/bert_data/v3/bfcl [--limit 100]
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_client import ProbeClient  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8201")
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", required=True, help="…/bert_data/v3/<env>")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个事件(0=全)")
    args = ap.parse_args()

    rep = json.loads((Path(args.run) / "REPLAY_REPORT.json").read_text())
    frozen = rep["test_frozen"]["0.05"]
    theta = frozen["theta"]

    rows = [json.loads(l) for l in open(Path(args.data) / "test.jsonl")]
    ev = defaultdict(list)
    for r in rows:
        ev[r["event"]].append(r)
    events = sorted(ev)
    if args.limit:
        events = events[: args.limit]

    cli = ProbeClient(args.server)
    print("health:", cli.health())

    recs, lat = [], []
    t0 = time.time()
    for i, k in enumerate(events):
        items = sorted(ev[k], key=lambda r: r["sent_idx"])
        rec = dict(fired=False, ok=False, depth=None)
        for r in items:
            out = cli.score(r["text"])
            lat.append(out["ms"])
            if out["conf"] >= theta:
                rec.update(fired=True, ok=(out["label"] == r["label"]),
                           depth=r["depth"])
                break
        recs.append(rec)
        if i % 20 == 0:
            print(f"{i}/{len(events)} events", flush=True)

    n = len(recs)
    fired = [r for r in recs if r["fired"]]
    cov = len(fired) / max(n, 1)
    acc = sum(r["ok"] for r in fired) / max(len(fired), 1)
    early = sum(1 - r["depth"] for r in fired) / max(len(fired), 1)
    lat.sort()
    out = {
        "n_events": n, "theta": theta,
        "server": {"coverage": round(cov, 4), "trig_acc": round(acc, 4),
                   "earliness": round(early, 4)},
        "replay_report": {k: frozen[k]
                          for k in ("coverage", "trig_acc", "earliness")},
        "probe_ms": {"p50": lat[len(lat) // 2], "p90": lat[int(len(lat) * .9)],
                     "max": lat[-1], "n_calls": len(lat)},
        "wall_s": round(time.time() - t0, 1),
    }
    print(json.dumps(out, indent=1))
    outp = Path(args.run) / "SMOKE_DRY.json"
    outp.write_text(json.dumps(out, indent=1))
    full = not args.limit
    same = (abs(cov - frozen["coverage"]) * n <= 1.5
            and abs(acc - frozen["trig_acc"]) * max(len(fired), 1) <= 1.5)
    print(f"-> {outp}")
    if full:
        print("PASS: 与离线回放一致" if same else
              "FAIL: 与 REPLAY_REPORT 不一致,查温度/截断/label_map")
    else:
        print("(limit 模式,只看延迟与跑通,不判定一致性)")


if __name__ == "__main__":
    main()
