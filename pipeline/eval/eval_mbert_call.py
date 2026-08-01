"""触发时刻抽取评测(新流水线 mext 格):回放定出触发点,在该前缀上抽参数,
报完整调用正确率。

源 = envs/bert/eval_extract.py(逐字照抄)+ envs/bert/param_tiers.py 的
parse/tier_of/THRESH(一起搬进本文件,不再单开模块)。改动只有规格 §6.2 列的:
`--data`/`--params` 指新目录(<data_out> 直接含 test.jsonl、参数默认
<data_out>/params)、堆名 calA→val(本脚本只用 test 堆,故只体现在参数目录口径上)、
抽取头函数改从 pipeline/train/train_mbert_extract.py import。其余全部照抄:
触发点取自 --run(mtool)的 REPLAY_REPORT 温度 + chosen_theta、在触发前缀上跑
抽取头、宽松/严格/整调用三档、三档分层(读 <data_out>/router_stats.md)。

ro1 批次加 `--readonly-env {appworld,bfcl}`(默认关,关=行为逐字节不变):打开后
真值标签在装载处过 readonly_map.collapse()、触发条件加"argmax 不是弃权类";
参数指标只在"触发了且真值为只读工具"的事件上算,触发但真值非只读的事件不进
params_all_ok / full_call_ok 分母,单独计进新增键 readonly_excluded。
已有字段名与三档判分一个不动。label_map.json 的弃权哨兵与本开关双向互为条件。

用法:
  mbert-env/bin/python pipeline/eval/eval_mbert_call.py --env appworld \\
    --run pipeline/runs/c1_q35_mtool --extractor pipeline/runs/c1_q35_mext \\
    --data pipeline/data/aw_official_v1/q35
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
import readonly_map                                      # noqa: E402
from train_mbert_extract import (FIND, collate, decode,  # noqa: E402
                                 load_extractor, span_ok)

TIERS = ("无参", "选择", "自由")
SPORK_ANCHOR = 0.076        # 竞品 SPORK 参数起步正确率
PILOT_ANCHOR = 0.338        # 先行试点:提前 25 token 时字面串已出现比例
THRESH = 0.90               # 【照抄 param_tiers.py】选择/自由档的逐字命中率分界


# ---------- 三档档位表(【照抄 param_tiers.py】) ----------

def parse(md_text):
    rows = []
    for line in md_text.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+|-)\s*\|", line)
        if m:
            hit = None if m.group(4) == "-" else float(m.group(4))
            rows.append((m.group(1), int(m.group(2)), int(m.group(3)), hit))
    return rows


def tier_of(hit):
    if hit is None:
        return "无参"
    return "选择" if hit >= THRESH else "自由"


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta, nro_id=None):
    """与 eval_tool.replay 同逻辑,额外返回触发的 sent_idx 与行。

    nro_id=None 是旧口径;给了弃权类 id(readonly 模式)时触发条件收窄成
    "conf>=θ 且 argmax != nro_id",与 eval_tool.replay 完全同源。
    """
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta and (nro_id is None or pred != nro_id):
                rec.update(fired=True, ok=(pred == r["y"]),
                           sent_idx=r["sent_idx"], row=r)
                break
        out[k] = rec
    return out


@torch.no_grad()
def run_extractor(model, tok, meta, items, dev, bs):
    """items=[(str,value,gs,ge,found)] -> [(loose_ok, strict_ok, pred_ans)]。"""
    out = []
    for i in range(0, len(items), bs):
        chunk = [(s, v, gs, ge, f, 1.0) for s, v, gs, ge, f in items[i:i + bs]]
        b = collate(chunk, tok, meta["max_len"])
        enc = {k: v.to(dev) for k, v in b["enc"].items()}
        s_lg, e_lg, a_lg = model(enc, b["last"].to(dev))
        s_lg, e_lg = s_lg.float().cpu(), e_lg.float().cpu()
        ansp = (a_lg.float().cpu() > 0)
        spans = decode(s_lg, e_lg, b["valid"], b["offs"])
        for j in range(len(chunk)):
            pa = bool(ansp[j])
            c0, c1 = spans[j]
            out.append((pa and span_ok(b["strs"][j], c0, c1,
                                       b["gs"][j], b["ge"][j]),
                        pa and b["strs"][j][c0:c1] == b["vals"][j], pa))
        if (i // bs) % 20 == 0:
            print(f"extracted {i}/{len(items)}", flush=True)
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--run", required=True, help="分类头 run 目录(mtool)")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(直接含 test.jsonl / router_stats.md)")
    ap.add_argument("--params", default=None,
                    help="参数区间标签目录(默认 <data>/params)")
    ap.add_argument("--extractor", required=True, help="抽取头 run 目录(mext)")
    ap.add_argument("--risk", type=float, default=0.05)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="截前 N 事件(冒烟)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具+弃权类模式(默认关);打开后真值折叠、"
                         "触发条件加\"argmax 不是弃权类\",且只给真值为只读"
                         "工具的触发事件算参数指标")
    args = ap.parse_args()

    run, ext = Path(args.run), Path(args.extractor)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    rep_cls = json.loads((run / "REPLAY_REPORT.json").read_text())
    T = rep_cls["temperature"]
    theta = rep_cls["chosen_theta"].get(str(args.risk))
    if theta is None:
        raise SystemExit(f"分类头报告里没有 risk={args.risk} 的 θ:"
                         f"{rep_cls['chosen_theta']}")

    # 1) 触发点:过滤逻辑与 eval_tool 逐行一致,保证与 logits_test.pt 同序
    label2id = json.loads((run / "best" / "label_map.json").read_text())

    # 防串味双向保险丝:label_map 里有弃权哨兵 ⇔ 必须传 --readonly-env
    has_sentinel = readonly_map.NON_READONLY in label2id
    if has_sentinel != bool(args.readonly_env):
        raise SystemExit(
            f"readonly 保险丝不匹配:{run / 'best' / 'label_map.json'} "
            f"{'含' if has_sentinel else '不含'}弃权哨兵 "
            f"{readonly_map.NON_READONLY!r};而 --readonly-env "
            f"{'传了 ' + str(args.readonly_env) if args.readonly_env else '没传'}。"
            "两者必须同时成立或同时不成立——readonly 模式训的 run 只能带 "
            "--readonly-env 评,旧口径 run 只能不带。")
    ro_set = nro_id = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    raw_rows = load_rows(data / "test.jsonl")
    if ro_set is not None:
        readonly_map.audit([r["label"] for r in raw_rows],
                           readonly_map.load_table(args.readonly_env),
                           "eval_mbert_call test")
        for r in raw_rows:
            r["label"] = readonly_map.collapse(r["label"], ro_set)
    rows = [r for r in raw_rows if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    logits = torch.load(run / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)
    fired = replay_fire(rows, torch.softmax(logits / T, -1), theta, nro_id)

    # 2) 参数真值:params 里同一 (event, sent_idx) 那一行
    pmap = {}
    for p in load_rows(params / "test.jsonl"):
        pmap[(p["event"], p["sent_idx"])] = p["params"]

    keys = [k for k in dict.fromkeys(r["event"] for r in rows)
            if fired[k]["fired"]]
    # readonly 模式:触发了但真值非只读的事件不算参数指标(不进任何分母),单独计数
    n_ro_excluded = 0
    if ro_set is not None:
        keep = [k for k in keys
                if fired[k]["label"] != readonly_map.NON_READONLY]
        n_ro_excluded = len(keys) - len(keep)
        keys = keep
    if args.limit:
        keys = keys[:args.limit]

    items, index = [], []
    for k in keys:
        rec = fired[k]
        text = rec["row"]["text"]
        for q in pmap.get((k, rec["sent_idx"]), []):
            index.append((k, q["found"]))
            items.append((text + FIND + q["key"], q["value"],
                          q["start"], q["end"], q["found"]))

    model, tok, meta = load_extractor(ext, args.device)
    res = run_extractor(model, tok, meta, items, args.device, args.bs) \
        if items else []

    # 3) 逐事件汇总。参数正确 = 真值 found 时区间对 / 真值抽不到时答抽不到
    per_ev = {k: dict(loose=True, strict=True, present=True, n=0)
              for k in keys}
    n_par = n_loose = n_strict = n_present = 0
    for (k, fnd), (lo, st, pa) in zip(index, res):
        cl, cs = (lo, st) if fnd else (not pa, not pa)
        e = per_ev[k]
        e["n"] += 1
        e["loose"] &= cl
        e["strict"] &= cs
        e["present"] &= fnd
        n_par += 1
        n_loose += cl
        n_strict += cs
        n_present += fnd

    tiers = {name: tier_of(hit)
             for name, _n, _np, hit in parse((data / "router_stats.md")
                                             .read_text())}

    buck = defaultdict(lambda: dict(n=0, allok=0, allok_s=0, call=0,
                                    noparam=0, present=0))

    def add(b, k):
        rec, pe = fired[k], per_ev[k]
        b["n"] += 1
        b["allok"] += pe["loose"]
        b["allok_s"] += pe["strict"]
        b["call"] += pe["loose"] and rec["ok"]
        b["noparam"] += pe["n"] == 0
        b["present"] += pe["present"]

    for k in keys:
        add(buck["整体"], k)
        add(buck[tiers.get(fired[k]["label"], "自由")], k)

    def fmt(b):
        return dict(n=b["n"], noparam_events=b["noparam"],
                    params_all_present=rate(b["present"], b["n"]),
                    params_all_ok=rate(b["allok"], b["n"]),
                    params_all_ok_strict=rate(b["allok_s"], b["n"]),
                    full_call_ok=rate(b["call"], b["n"]))

    n_ev = len(rows) and len({r["event"] for r in rows})
    out = dict(
        env=args.env, run=str(run), extractor=str(ext), risk=args.risk,
        theta=theta, temperature=T, n_events_test=n_ev,
        n_events_fired=len([k for k in fired if fired[k]["fired"]]),
        n_events_scored=len(keys), limit=args.limit,
        n_param_instances=n_par,
        param_present_rate=rate(n_present, n_par),
        param_acc_loose=rate(n_loose, n_par),
        param_acc_strict=rate(n_strict, n_par),
        by_tier={t: fmt(buck[t]) for t in TIERS if t in buck},
        overall=fmt(buck["整体"]),
        anchors=dict(spork_param_acc=SPORK_ANCHOR,
                     pilot_value_present_at_25tok=PILOT_ANCHOR))
    if ro_set is not None:
        out["readonly_env"] = args.readonly_env
        out["readonly_excluded"] = n_ro_excluded
    (ext / "EXTRACT_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    md = [f"# 触发时刻抽取评测 — {args.env}",
          f"- 分类头 {run.name} / 抽取头 {ext.name};风险≤{args.risk} → θ={theta}"
          f"(温度 T={T})",
          f"- test 事件 {n_ev},触发 {out['n_events_fired']},"
          f"本次计入 {len(keys)}" + (f"(--limit {args.limit})"
                                     if args.limit else ""),
          f"- 参数实例 {n_par};参数级正确率 宽松 {out['param_acc_loose']} / "
          f"严格 {out['param_acc_strict']};触发时值已出现 "
          f"{out['param_present_rate']}",
          "",
          "| 档位 | 事件数 | 其中无参 | 值已全出现 | 参数全对率 |"
          " 参数全对(严格) | 完整调用正确率 |",
          "|---|---|---|---|---|---|---|"]
    for t in list(TIERS) + ["整体"]:
        if t not in buck:
            continue
        f = fmt(buck[t])
        md.append(f"| {t} | {f['n']} | {f['noparam_events']} | "
                  f"{f['params_all_present']} | {f['params_all_ok']} | "
                  f"{f['params_all_ok_strict']} | {f['full_call_ok']} |")
    md += ["",
           "## 锚点与已知风险",
           f"- 竞品 SPORK 参数起步正确率 {SPORK_ANCHOR:.1%};"
           "本表末列的完整调用正确率是同一件事的口径。",
           "- 已知风险:早触发点参数常未出现——先行试点提前 25 token 时"
           f"字面串仅 {PILOT_ANCHOR:.1%} 已出现。这部分真值记为抽不到,"
           "抽取头答对抽不到也算参数正确,所以参数全对率可以高于"
           "值已全出现率;但真能在触发时刻组出完整调用去投机的,"
           "只有值已全出现那一列,它才是投机覆盖面的天花板。",
           "- 判对口径:宽松=预测字符区间覆盖真值且多出的只有空白/标点。"
           "BPE 把前导空格与引号并进 token,严格逐字会系统性低估——"
           "金标 token 跨度自身的严格通过率只有 "
           "tales 0.066 / bfcl 0.642 / appworld 0.659,"
           "宽松口径下则是 0.997/0.997/0.991。严格列仅供对照。"]
    if ro_set is not None:
        md += ["", f"## 只读模式(--readonly-env {args.readonly_env})",
               f"- 弃权类 {readonly_map.NON_READONLY}(标签 id {nro_id});"
               "触发条件加\"argmax 不是弃权类\",真值标签已折叠",
               f"- 触发但真值非只读、因而不进任何参数分母的事件:"
               f"{n_ro_excluded}(readonly_excluded);"
               f"本表各列的分母是余下的 {len(keys)} 个真值只读触发事件"]
    (ext / "EXTRACT_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(out["overall"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
