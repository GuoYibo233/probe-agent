"""C2-2t 回放评测:校准(calA 拟温度)→ calB 回放扫阈值 → test 冻结一次。

导师协议全量落地:
- 评测对象 = 首次越阈策略,不是筛高分样本:每事件按 sent_idx 顺序回放,
  置信度(温度校准后 max softmax)首过 θ 即触发,只计那一下
- 报 coverage / 触发精度 / 无条件错误投机率 / earliness(1-触发深度)
- stop-time 校准表:只在首次触发点上分桶比较 平均置信 vs 实际对率
- 深度十桶样本级 acc(诊断用)+ 频率先验基线对照
- 置信区间:任务实例级 bootstrap(同实例的事件整体重采样)
- θ 只在 calB 上选(风险约束下最大 coverage),test 只跑选定的 θ

用法: python eval_replay.py --env tales   (在训练产物 best/ 就绪后跑,需 GPU)
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE = Path("/home/y-guo/reproduce/new1/envs")
SEED = 20260729
THETAS = [round(0.5 + 0.025 * i, 3) for i in range(20)]  # 0.5 .. 0.975
RISK_TARGETS = [0.10, 0.05]        # 触发错误率约束(=精度 0.90/0.95)
BOOT = 1000


def load_rows(path):
    return [json.loads(l) for l in open(path)]


@torch.no_grad()
def score(model, tok, rows, dev, bs=16, max_len=4096):
    """返回每行的 logits(np 数组顺序与 rows 一致)。"""
    out = []
    model.eval()
    for i in range(0, len(rows), bs):
        texts = [r["text"] for r in rows[i:i + bs]]
        enc = tok(texts, truncation=True, max_length=max_len,
                  padding=True, return_tensors="pt")
        enc = {k: v.to(dev) for k, v in enc.items()}
        out.append(model(**enc).logits.float().cpu())
        if (i // bs) % 50 == 0:
            print(f"scored {i}/{len(rows)}", flush=True)
    return torch.cat(out)


def fit_temperature(logits, labels):
    logT = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([logT], lr=0.1, max_iter=100)
    lossf = torch.nn.CrossEntropyLoss()

    def closure():
        opt.zero_grad()
        loss = lossf(logits / logT.exp(), labels)
        loss.backward()
        return loss
    opt.step(closure)
    return float(logT.exp())


def replay(rows, probs, theta):
    """rows+probs 同序。返回每事件 dict(fired, ok, depth, conf)。"""
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, depth=None, conf=None,
                   unit=items[0][1]["unit"], label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta:
                rec.update(fired=True, ok=(pred == r["y"]),
                           depth=r["depth"], conf=conf)
                break
        out[k] = rec
    return out


def agg(recs):
    n = len(recs)
    fired = [r for r in recs if r["fired"]]
    cov = len(fired) / max(n, 1)
    acc = sum(r["ok"] for r in fired) / max(len(fired), 1)
    early = (sum(1 - r["depth"] for r in fired) / max(len(fired), 1))
    wrong = sum(1 for r in fired if not r["ok"]) / max(n, 1)
    return dict(n=n, coverage=round(cov, 4), trig_acc=round(acc, 4),
                earliness=round(early, 4), wrong_spec=round(wrong, 4))


def economics(recs):
    """投机经济换算(T4,离线估算;字段口径与 T10 fork 对照的在线实测对齐,日后并排对账):
    - exp_token_saving_ratio: 截断口径,每事件期望省下的思考 token 比例
      = Σ触发事件(1-depth) / 全事件数 ≡ 触发率×提前量(对错都省,错的代价记在错误投机率)
    - exp_overlap_ratio: 预取口径,期望重叠延迟比例;只有触发且预测正确的事件
      贡献重叠窗口(错误预取不省延迟但也无害)
    """
    n = max(len(recs), 1)
    save = sum(1 - r["depth"] for r in recs if r["fired"]) / n
    overlap = sum(1 - r["depth"] for r in recs if r["fired"] and r["ok"]) / n
    return dict(exp_token_saving_ratio=round(save, 4),
                exp_overlap_ratio=round(overlap, 4))


def bootstrap(recs, rng):
    by_unit = defaultdict(list)
    for r in recs:
        by_unit[r["unit"]].append(r)
    units = list(by_unit)
    stats = defaultdict(list)
    for _ in range(BOOT):
        samp = []
        for u in (rng.choice(units) for _ in units):
            samp.extend(by_unit[u])
        a = agg(samp)
        for k in ("coverage", "trig_acc", "earliness"):
            stats[k].append(a[k])
    ci = {}
    for k, v in stats.items():
        v.sort()
        ci[k] = (round(v[int(BOOT * .025)], 4), round(v[int(BOOT * .975)], 4))
    return ci


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl"])
    ap.add_argument("--run", default=None)
    ap.add_argument("--data", default=str(BASE / "bert_data" / "v2"))
    ap.add_argument("--cached-logits", action="store_true",
                    help="读 run 目录已存的 logits_*.pt,跳过模型推理(纯 CPU 后处理)")
    args = ap.parse_args()
    run = Path(args.run or BASE / "bert_runs" / f"{args.env}_v2")
    data = Path(args.data) / args.env
    dev = "cuda"
    rng = random.Random(SEED)

    label2id = json.loads((run / "best" / "label_map.json").read_text())
    if not args.cached_logits:
        tok = AutoTokenizer.from_pretrained(run / "best")
        tok.truncation_side = "left"
        model = AutoModelForSequenceClassification.from_pretrained(
            run / "best", torch_dtype=torch.bfloat16,
            attn_implementation="sdpa").to(dev)

    splits = {}
    for sp in ("calA", "calB", "test"):
        rows = [r for r in load_rows(data / f"{sp}.jsonl")
                if r["label"] in label2id]
        for r in rows:
            r["y"] = label2id[r["label"]]
        if args.cached_logits:
            logits = torch.load(run / f"logits_{sp}.pt")
            assert len(logits) == len(rows), \
                f"{sp}: 缓存 logits {len(logits)} 行 != 数据 {len(rows)} 行,--data 与当次评测不同源"
        else:
            logits = score(model, tok, rows, dev)
            torch.save(logits, run / f"logits_{sp}.pt")
        splits[sp] = (rows, logits)

    # 1) calA 拟温度
    rows_a, lg_a = splits["calA"]
    T = fit_temperature(lg_a, torch.tensor([r["y"] for r in rows_a]))

    # 2) calB 回放扫 θ
    rows_b, lg_b = splits["calB"]
    probs_b = torch.softmax(lg_b / T, -1)
    sweep = []
    econ_sweep = []
    for th in THETAS:
        recs = list(replay(rows_b, probs_b, th).values())
        sweep.append((th, agg(recs)))
        econ_sweep.append((th, economics(recs)))
    chosen = {}
    for risk in RISK_TARGETS:
        ok = [(th, a) for th, a in sweep
              if a["trig_acc"] >= 1 - risk and a["coverage"] > 0]
        chosen[risk] = (max(ok, key=lambda x: x[1]["coverage"])[0]
                        if ok else None)

    # 3) test 冻结:只跑选定 θ
    rows_t, lg_t = splits["test"]
    probs_t = torch.softmax(lg_t / T, -1)
    final = {}
    econ_test = {}
    for risk, th in chosen.items():
        if th is None:
            final[risk] = None
            econ_test[str(risk)] = None
            continue
        recs = list(replay(rows_t, probs_t, th).values())
        final[risk] = dict(theta=th, **agg(recs), ci=bootstrap(recs, rng))
        econ_test[str(risk)] = dict(theta=th, **economics(recs))

    # stop-time 校准(test,取风险 0.05 的 θ;无则 0.8)
    th0 = chosen.get(0.05) or 0.8
    fired = [r for r in replay(rows_t, probs_t, th0).values() if r["fired"]]
    bins = defaultdict(list)
    for r in fired:
        bins[min(int(r["conf"] * 10), 9)].append(r)
    stoptime = {f"{b/10:.1f}-{(b+1)/10:.1f}":
                dict(n=len(v),
                     mean_conf=round(sum(x["conf"] for x in v) / len(v), 3),
                     acc=round(sum(x["ok"] for x in v) / len(v), 3))
                for b, v in sorted(bins.items())}

    # 深度十桶样本级 acc(诊断)+ 先验基线
    pred_t = probs_t.argmax(-1)
    dep = defaultdict(lambda: [0, 0])
    for r, p in zip(rows_t, pred_t):
        b = min(9, int(r["depth"] * 10))
        dep[b][0] += int(p) == r["y"]
        dep[b][1] += 1
    depth_acc = {f"{b/10:.1f}": round(c / n, 3)
                 for b, (c, n) in sorted(dep.items())}
    vocab = json.loads((data / "tool_vocab.json").read_text())
    prior_tool = max(vocab, key=vocab.get)
    ev_labels = {r["event"]: r["label"] for r in rows_t}
    prior_acc = (sum(1 for v in ev_labels.values() if v == prior_tool)
                 / max(len(ev_labels), 1))

    rep = {
        "env": args.env, "temperature": round(T, 4),
        "theta_sweep_calB": [(th, a) for th, a in sweep],
        "chosen_theta": {str(k): v for k, v in chosen.items()},
        "test_frozen": {str(k): v for k, v in final.items()},
        "stoptime_calibration_test": stoptime,
        "depth_bucket_acc_test": depth_acc,
        "prior_baseline_event_acc": round(prior_acc, 4),
        "n_events_test": len(ev_labels),
        "speculation_economics": {
            "note": ("T4 离线估算;与 T10 fork 对照(在线实测)同量对账。"
                     "save=截断口径 触发率×提前量;overlap=预取口径 仅触发且对"),
            "calB_sweep": econ_sweep,
            "test_frozen": econ_test,
        },
    }
    (run / "REPLAY_REPORT.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1))

    md = [f"# 回放评测 — {args.env}", f"- 温度 T={T:.3f}",
          f"- test 事件数 {len(ev_labels)};频率先验基线 {prior_acc:.3f}", ""]
    for risk, r in final.items():
        if r:
            md.append(
                f"- **风险≤{risk}** θ={r['theta']}: coverage "
                f"{r['coverage']} (CI {r['ci']['coverage']}), 触发精度 "
                f"{r['trig_acc']} (CI {r['ci']['trig_acc']}), earliness "
                f"{r['earliness']} (CI {r['ci']['earliness']}), "
                f"错误投机率 {r['wrong_spec']}")
        else:
            md.append(f"- 风险≤{risk}: calB 上无满足约束的 θ")
    md += ["", "## 深度桶 acc(样本级,诊断)",
           json.dumps(depth_acc), "", "## stop-time 校准(首次触发点)",
           json.dumps(stoptime, ensure_ascii=False)]
    md += ["", "## 投机经济换算(T4 离线估算,口径对齐 T10 fork 对照)",
           "| 口径 | θ | 期望省 token 比例(截断) | 期望重叠延迟比例(预取) |",
           "|---|---|---|---|"]
    for risk, e in econ_test.items():
        if e:
            md.append(f"| test 风险≤{risk} | {e['theta']} | "
                      f"{e['exp_token_saving_ratio']} | {e['exp_overlap_ratio']} |")
        else:
            md.append(f"| test 风险≤{risk} | - | - | - |")
    md += ["", "calB 全 θ 档:", "| θ | 省 token | 重叠延迟 |", "|---|---|---|"]
    md += [f"| {th} | {e['exp_token_saving_ratio']} | {e['exp_overlap_ratio']} |"
           for th, e in econ_sweep]
    (run / "REPLAY_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(rep["test_frozen"], indent=1))


if __name__ == "__main__":
    main()
