"""T5 消融评测包装:不改 eval_replay.py,monkeypatch load_rows 后按原协议跑。

- no-hist  : 完整回放评测,与主线同轨(含 T4 换算段等后续增补,自动继承)
- no-think : 回放协议退化(每事件仅一条),照跑原协议后另算 test 普通事件级
             准确率,追加进 REPLAY_REPORT(新字段,旧字段不动)

切割逻辑 import input_modes,与训练逐字一致。

用法:
  python eval_replay_mode.py --mode no-hist --env tales \
      --run envs/bert_runs/tales_v3_nohist --data envs/bert_data/v3
"""

import argparse
import json
import sys
from pathlib import Path

import torch

import eval_replay as er
from input_modes import apply_mode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["no-think", "no-hist"])
    args, rest = ap.parse_known_args()

    orig_load = er.load_rows
    er.load_rows = lambda p: apply_mode(orig_load(p), args.mode)
    sys.argv = [sys.argv[0]] + rest
    er.main()

    if args.mode != "no-think":
        return
    # 普通事件级准确率:无阈值,每事件一读,argmax 即预测
    ea = argparse.ArgumentParser()
    ea.add_argument("--env", required=True)
    ea.add_argument("--run", default=None)
    ea.add_argument("--data", default=str(er.BASE / "bert_data" / "v2"))
    a2 = ea.parse_args(rest)
    run = Path(a2.run or er.BASE / "bert_runs" / f"{a2.env}_v2")
    label2id = json.loads((run / "best" / "label_map.json").read_text())
    rows = [r for r in er.load_rows(Path(a2.data) / a2.env / "test.jsonl")
            if r["label"] in label2id]
    pred = torch.load(run / "logits_test.pt").argmax(-1)
    assert len(rows) == len(pred)
    acc = sum(int(p) == label2id[r["label"]]
              for r, p in zip(rows, pred)) / max(len(rows), 1)
    rep_p = run / "REPLAY_REPORT.json"
    rep = json.loads(rep_p.read_text())
    rep["nothink_plain_event_acc"] = round(acc, 4)
    rep["input_mode"] = args.mode
    rep_p.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    with open(run / "REPLAY_REPORT.md", "a") as f:
        f.write(f"\n## no-think 普通事件级准确率(每事件一读,无阈值)\n"
                f"{acc:.4f}(n={len(rows)});对照同报告先验基线 "
                f"{rep['prior_baseline_event_acc']}\n")
    print(f"nothink_plain_event_acc={acc:.4f}")


if __name__ == "__main__":
    main()
