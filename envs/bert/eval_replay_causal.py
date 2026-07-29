"""因果探针的回放评测(C2-2t T8):与 ModernBERT 版 eval_replay.py 完全同轨。

协议、阈值网格、置信区间、T4 投机经济换算全部 import eval_replay 复用
(fit_temperature / replay / agg / economics / bootstrap / THETAS /
RISK_TARGETS),报告字段名与文件名一字不差,所以 REPLAY_REPORT.{json,md}
可与 ModernBERT 的报告并排读。

唯一的不同在**打分方式**:ModernBERT 每行(=一个句子边界前缀)重编码一次;
因果探针按事件整段一次前向,gather 各边界 token 位的 logits,再还原成与行序
一致的 per-row logits 张量。左截(--max-len)窗口外的边界给全零 logits——
置信度退化成 1/n_labels,永远不会越阈,等价于"这一下探针没得看,不触发"。

新增两个字段(旧字段一个不动):
- probe_backbone: 底座名
- probe_cost_test: {bert_tokens, causal_tokens, ratio}——探完一条轨迹的计算量
  对比,bert_tokens = Σ每行前缀 token 数(ModernBERT 口径:每个边界重读一遍),
  causal_tokens = Σ每事件全文 token 数(因果口径:整条读一遍),都用本底座
  tokenizer 计数、不计 max_len 截断。

用法: python eval_replay_causal.py --env bfcl --run <train_causal_probe 的 --out>
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_replay as ER                                   # noqa: E402
from eval_replay import (RISK_TARGETS, THETAS, agg, bootstrap,  # noqa: E402
                         economics, fit_temperature, load_rows, replay)

BASE = Path("/home/y-guo/reproduce/new1/envs")
SEED = ER.SEED
EVAL_BS = 4          # 事件数/批


@torch.no_grad()
def score_causal(backbone, head, tok, rows, dev, max_len, bs=EVAL_BS):
    """按事件一次前向、gather 各边界位置 logits,还原成与 rows 同序的张量。"""
    ev = defaultdict(list)
    for i, r in enumerate(rows):
        ev[r["event"]].append((r["sent_idx"], i, r))
    events = []
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        full = items[-1][2]["text"]
        events.append((full, [(len(r["text"]), i) for _, i, r in items]))

    n_lab = head.out_features
    out = torch.zeros(len(rows), n_lab)
    n_oow = 0                                    # 左截窗口外的边界数
    for s in range(0, len(events), bs):
        chunk = events[s:s + bs]
        enc = tok([e[0] for e in chunk], truncation=True, max_length=max_len,
                  padding=True, return_offsets_mapping=True,
                  return_tensors="pt")
        offs = enc.pop("offset_mapping")
        enc = {k: v.to(dev) for k, v in enc.items()}
        h = backbone(input_ids=enc["input_ids"],
                     attention_mask=enc["attention_mask"],
                     use_cache=False).last_hidden_state
        for bi, (_full, bounds) in enumerate(chunk):
            ends = offs[bi, :, 1].tolist()
            keep = int(enc["attention_mask"][bi].sum())
            cols, idxs = [], []
            for b, ri in bounds:
                j = -1
                for t in range(keep - 1, -1, -1):        # 最大的 j: 0 < end <= b
                    if 0 < ends[t] <= b:
                        j = t
                        break
                if j < 0:
                    n_oow += 1
                    continue
                cols.append(j)
                idxs.append(ri)
            if cols:
                lg = head(h[bi, torch.tensor(cols, device=dev)].float())
                out[torch.tensor(idxs)] = lg.cpu()
        if (s // bs) % 25 == 0:
            print(f"scored {s}/{len(events)} events", flush=True)
    print(f"边界总数 {len(rows)},左截窗口外(全零 logits,永不触发) {n_oow}",
          flush=True)
    return out


def token_cost(tok, rows):
    """(bert_tokens, causal_tokens):每行前缀 vs 每事件全文,不计 max_len 截断。"""
    bert = sum(len(x) for x in tok([r["text"] for r in rows])["input_ids"])
    ev = {}
    for r in rows:
        if len(r["text"]) > len(ev.get(r["event"], "")):
            ev[r["event"]] = r["text"]
    causal = sum(len(x) for x in tok(list(ev.values()))["input_ids"])
    return bert, causal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl"])
    ap.add_argument("--run", required=True,
                    help="train_causal_probe.py 的 --out 目录")
    ap.add_argument("--data", default=str(BASE / "bert_data" / "v3"),
                    help="默认 v3(注意 ModernBERT 的 eval_replay.py 默认是 v2)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--cached-logits", action="store_true",
                    help="读 run 目录已存的 logits_*.pt,跳过前向(纯 CPU 后处理)")
    ap.add_argument("--smoke", action="store_true",
                    help="每 split 截 40 行、bootstrap 降 20 次,只验管线")
    args = ap.parse_args()

    run = Path(args.run)
    data = Path(args.data) / args.env
    dev = args.device
    rng = random.Random(SEED)
    if args.smoke:
        ER.BOOT = 20

    label2id = json.loads((run / "best" / "label_map.json").read_text())
    meta = json.loads((run / "best" / "meta.json").read_text())
    max_len = meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(run / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"
    tok.padding_side = "right"
    if not args.cached_logits:
        backbone = AutoModel.from_pretrained(
            run / "best",
            dtype=torch.bfloat16 if dev.startswith("cuda") else torch.float32
        ).to(dev).eval()
        head = torch.nn.Linear(
            backbone.config.get_text_config().hidden_size,
            len(label2id)).to(dev)
        head.load_state_dict(torch.load(run / "best" / "head.pt",
                                        map_location=dev))
        head.eval()

    splits = {}
    for sp in ("calA", "calB", "test"):
        rows = [r for r in load_rows(data / f"{sp}.jsonl")
                if r["label"] in label2id]
        if args.smoke:
            rows = rows[:40]
        for r in rows:
            r["y"] = label2id[r["label"]]
        if args.cached_logits:
            logits = torch.load(run / f"logits_{sp}.pt")
            assert len(logits) == len(rows), \
                f"{sp}: 缓存 logits {len(logits)} 行 != 数据 {len(rows)} 行,--data 与当次评测不同源"
        else:
            logits = score_causal(backbone, head, tok, rows, dev, max_len)
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

    # 探测成本(test):每行前缀 vs 每事件全文
    bert_tok, causal_tok = token_cost(tok, rows_t)

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
        "probe_backbone": meta.get("base"),
        "probe_cost_test": {
            "bert_tokens": bert_tok, "causal_tokens": causal_tok,
            "ratio": round(bert_tok / max(causal_tok, 1), 3)},
    }
    (run / "REPLAY_REPORT.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1))

    md = [f"# 回放评测 — {args.env}(因果探针 {meta.get('base')})",
          f"- 温度 T={T:.3f}",
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
    md += ["", "## 探测成本(test,探完全部轨迹的 token 计算量)",
           f"- ModernBERT 口径 bert_tokens={bert_tok}(每个句子边界重读一遍前缀)",
           f"- 因果口径 causal_tokens={causal_tok}(每个事件整段读一遍)",
           f"- ratio={rep['probe_cost_test']['ratio']}x",
           f"- 口径:两边都用 {meta.get('base')} 底座的 tokenizer 计数,"
           "不计 max_len 截断;只算探针读进去的 token,不含 agent 自身生成。"]
    (run / "REPLAY_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(rep["test_frozen"], indent=1))
    print(json.dumps(rep["probe_cost_test"], indent=1))


if __name__ == "__main__":
    main()
