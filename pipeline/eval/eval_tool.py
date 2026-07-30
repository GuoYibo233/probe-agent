"""回放评测(新流水线 eval 段):val 拟温度 + 扫阈值 → test 冻结一次。

源 = envs/bert/eval_replay.py(逐字照抄),加上 envs/bert/eval_replay_causal.py 的
因果打分路径。改动只有规格 §6.1 列的四处:

1. 堆名 ("calA","calB","test") → ("val","test"):温度在 val 拟、θ 也在 val 扫
   (§2.5),test 冻结不变;报告字段名 theta_sweep_calB 等【保持旧名不改】。
2. `--data` 直接指 <data_out>(不再拼 env 子目录)、`--run` 必填,都无默认值。
3. `--head causal`:模型加载 = CausalProbe(pipeline/train/train_causal_tool.py)
   的 backbone + head.pt;打分按事件整段一次前向、在每个边界位取 logits
   (【照抄 eval_replay_causal.py 的 score_causal】)。cached-logits 路径不变。
4. `--legacy-splits`:读旧的 calA/calB/test 并完全按旧逻辑跑(温度 calA、θ calB),
   `--data` 语义退回 <data>/<env>——只为 §6.5 验收用。

另加两个不改口径的开关(见 ACCEPT_EVAL.md 的偏离记录):
`--report-dir`(报告写别处,验收时不碰旧文件)、`--device`。

用法:
  # 新流水线(mbert 分类头)
  mbert-env/bin/python pipeline/eval/eval_tool.py --env appworld \\
    --run pipeline/runs/c1_q35_mtool --data pipeline/data/aw_official_v1/q35
  # 新流水线(因果探针)
  cprobe-env/bin/python pipeline/eval/eval_tool.py --env appworld --head causal \\
    --run pipeline/runs/c1_q35_ctool --data pipeline/data/aw_official_v1/q35
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

SEED = 20260729
THETAS = [round(0.5 + 0.025 * i, 3) for i in range(20)]  # 0.5 .. 0.975
RISK_TARGETS = [0.10, 0.05]        # 触发错误率约束(=精度 0.90/0.95)
BOOT = 1000
EVAL_BS = 4                        # 因果打分:事件数/批


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


# ---------------------------------------------------------------- 因果打分

def load_causal(run, n_labels, dev):
    """【照抄 train_causal_tool.CausalProbe 的加载方式】backbone 从 best/ 读、
    head 从 best/head.pt 读;cuda 上把 backbone 转 bf16(与旧 eval 同)。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
    from train_causal_tool import CausalProbe          # noqa: E402
    model = CausalProbe(run / "best", n_labels)
    model.head.load_state_dict(
        torch.load(run / "best" / "head.pt", map_location="cpu"))
    if str(dev).startswith("cuda"):
        model.backbone = model.backbone.to(torch.bfloat16)
    return model.to(dev).eval()


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


# ---------------------------------------------------------------- 后处理

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
    ap.add_argument("--run", required=True, help="训练产物目录(必填)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>;--legacy-splits 下语义退回 <data>/<env>")
    ap.add_argument("--head", default="mbert", choices=["mbert", "causal"],
                    help="mbert=序列分类头;causal=因果探针(backbone+head.pt)")
    ap.add_argument("--legacy-splits", action="store_true",
                    help="读旧的 calA/calB/test 并按旧逻辑跑(温度 calA、θ calB),验收专用")
    ap.add_argument("--report-dir", default=None,
                    help="报告输出目录(默认 = --run;验收时指向别处以免覆盖旧件)")
    ap.add_argument("--cached-logits", action="store_true",
                    help="读 run 目录已存的 logits_*.pt,跳过模型推理(纯 CPU 后处理)")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()
    run = Path(args.run)
    data = Path(args.data) / args.env if args.legacy_splits else Path(args.data)
    rep_dir = Path(args.report_dir) if args.report_dir else run
    rep_dir.mkdir(parents=True, exist_ok=True)
    dev = args.device
    rng = random.Random(SEED)

    # 堆名映射(§2.5):新口径两堆,温度与 θ 都在 val 上定;旧口径三堆照旧
    if args.legacy_splits:
        split_names = ("calA", "calB", "test")
        fit_sp, sweep_sp = "calA", "calB"
    else:
        split_names = ("val", "test")
        fit_sp, sweep_sp = "val", "val"

    label2id = json.loads((run / "best" / "label_map.json").read_text())
    meta = {}
    if args.head == "causal":
        # 【照抄 eval_replay_causal.py】tokenizer 无条件加载(探测成本要用它计数),
        # --cached-logits 只跳过模型本身
        meta = json.loads((run / "best" / "meta.json").read_text())
        max_len = meta.get("max_len", 4096)
        tok = AutoTokenizer.from_pretrained(run / "best")
        if tok.pad_token_id is None:
            tok.pad_token = tok.eos_token
        tok.truncation_side = "left"
        tok.padding_side = "right"
        if not args.cached_logits:
            model = load_causal(run, len(label2id), dev)
    elif not args.cached_logits:
        tok = AutoTokenizer.from_pretrained(run / "best")
        tok.truncation_side = "left"
        model = AutoModelForSequenceClassification.from_pretrained(
            run / "best", torch_dtype=torch.bfloat16,
            attn_implementation="sdpa").to(dev)

    splits = {}
    for sp in split_names:
        rows = [r for r in load_rows(data / f"{sp}.jsonl")
                if r["label"] in label2id]
        for r in rows:
            r["y"] = label2id[r["label"]]
        if args.cached_logits:
            logits = torch.load(run / f"logits_{sp}.pt")
            assert len(logits) == len(rows), \
                f"{sp}: 缓存 logits {len(logits)} 行 != 数据 {len(rows)} 行,--data 与当次评测不同源"
        elif args.head == "causal":
            logits = score_causal(model.backbone, model.head, tok, rows,
                                  dev, max_len)
            torch.save(logits, run / f"logits_{sp}.pt")
        else:
            logits = score(model, tok, rows, dev)
            torch.save(logits, run / f"logits_{sp}.pt")
        splits[sp] = (rows, logits)

    # 1) val(旧口径 calA)拟温度
    rows_a, lg_a = splits[fit_sp]
    T = fit_temperature(lg_a, torch.tensor([r["y"] for r in rows_a]))

    # 2) val(旧口径 calB)回放扫 θ
    rows_b, lg_b = splits[sweep_sp]
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
    # 因果探针专有的两个诊断字段(【照抄 eval_replay_causal.py】,旧字段一个不动)
    if args.head == "causal":
        bert_tok, causal_tok = token_cost(tok, rows_t)
        rep["probe_backbone"] = meta.get("base")
        rep["probe_cost_test"] = {
            "bert_tokens": bert_tok, "causal_tokens": causal_tok,
            "ratio": round(bert_tok / max(causal_tok, 1), 3)}
    (rep_dir / "REPLAY_REPORT.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1))

    title = (f"# 回放评测 — {args.env}(因果探针 {meta.get('base')})"
             if args.head == "causal" else f"# 回放评测 — {args.env}")
    md = [title, f"- 温度 T={T:.3f}",
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
    if "probe_cost_test" in rep:
        pc = rep["probe_cost_test"]
        md += ["", "## 探测成本(test,探完全部轨迹的 token 计算量)",
               f"- ModernBERT 口径 bert_tokens={pc['bert_tokens']}"
               "(每个句子边界重读一遍前缀)",
               f"- 因果口径 causal_tokens={pc['causal_tokens']}"
               "(每个事件整段读一遍)",
               f"- ratio={pc['ratio']}x",
               f"- 口径:两边都用 {rep.get('probe_backbone')} 底座的 tokenizer 计数,"
               "不计 max_len 截断;只算探针读进去的 token,不含 agent 自身生成。"]
    (rep_dir / "REPLAY_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(rep["test_frozen"], indent=1))


if __name__ == "__main__":
    main()
