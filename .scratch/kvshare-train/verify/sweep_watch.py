#!/usr/bin/env python3
"""学习率扫描 run 的盯梢表(只读,纯 stdlib):显存偏差与曲线事实,不下结论。

用法:
  python3 .scratch/kvshare-train/verify/sweep_watch.py [<run_dir> ...] [--glob 'pipeline/runs/sweep/*']
      [--dev-threshold 15] [--grad-factor 5] [--json <out.json>]

每个 run 目录读 train_log.jsonl(字段按 spec 16.3 到 16.6:step 有 loss/lr/grad_norm/peak_mem_gb/ips,
eval 有 val_ce/val_exact_call/gen_s,mem_probe 与 mem_probe_summary 按 16.5)。输出两张表:

  1. 显存:mem_probe_summary.worst_gb 对同一块按 9.1/9.9 系数算的预期、step 峰值最大值对该配置
     epoch 0 真峰估计(design 9.9:b06 开检查点 22.1、b17 不开 102.2、l17 不开 81.9、l4 开 33.7 GB),
     两个偏差绝对值超过 --dev-threshold(默认 15%)打 "!!"。
  2. 曲线:step 的 loss(首、末、最大、最小、nan/inf 个数)、grad_norm(中位、最大、末条、超过中位
     --grad-factor 倍的条数)、eval 的 val_ce 序列(每一处比前一点上升的标 "↑")、最后一条 step 距现在
     的分钟数与最近两条 step 的间隔(停滞看这两个数)、done 与 best。

系数表直接 import 同目录 smoke_check.py 的 FIXED_GB / MB_PER_TOKEN / MB_PER_LOSS_POS(一物一源)。
"""
import argparse
import glob
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_check as sc  # noqa: E402

# design 9.9 / 9.4:扫描 run epoch 0 代价最大块与真峰估计(GB),按配置与检查点
# update 是真峰块所在的更新组序号(从 0 数,enum_blocks.json 的 group;第 N 组在第 N+1 次更新里做),
# 训练还没走到那一组之前 step 峰值低于真峰估计是应当的,表里标"未到"
TRUE_PEAK = {
    ("b06", True): dict(block=(12736, 5696), gb=22.1, update=475),
    ("b06", False): dict(block=(16384, 4271), gb=58.5, update=490),
    ("b17", False): dict(block=(16384, 4271), gb=102.2, update=490),
    ("b17", True): dict(block=(12736, 5696), gb=46.1, update=475),
    ("l17", False): dict(block=(16384, 4271), gb=81.9, update=490),
    ("l17", True): dict(block=(12736, 5696), gb=22.3, update=475),
    ("l4", True): dict(block=(15360, 4992), gb=33.7, update=110),
    ("l4", False): dict(block=(16384, 4271), gb=152.3, update=490),
}


def fmt(v, nd=2):
    if v is None:
        return "缺"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def dev(measured, expected, threshold):
    if measured is None or expected is None or expected <= 0:
        return "缺", False
    d = (measured - expected) / expected * 100
    return f"{d:+.1f}%" + (" !!" if abs(d) > threshold else ""), abs(d) > threshold


def analyze(run_dir, args, now):
    run_dir = Path(run_dir)
    r = dict(run_id=run_dir.name)
    log_p = run_dir / "train_log.jsonl"
    if not log_p.exists():
        r["error"] = "train_log.jsonl 缺"
        return r
    ev = sc.load_log(log_p)
    st = ev["start"] or {}
    tag = sc.config_tag(st)
    gc, gc_src = sc.grad_ckpt_of(run_dir, tag)
    r.update(tag=tag, grad_ckpt=gc, grad_ckpt_source=gc_src, lr=st.get("lr"),
             tok_budget=st.get("tok_budget"), steps_total=st.get("steps"),
             mem_probe_pick=st.get("mem_probe_pick"), align_pass=st.get("align_pass"),
             align_maxdiff=st.get("align_maxdiff"))

    # ---- 显存 ----
    probes = []
    for m in ev["mem_probe"]:
        n_tokens, n_loss = sc.probe_numbers(m)
        exp = sc.expected_gb(tag, gc, n_tokens, n_loss)
        d, flag = dev(m.get("peak_mem_gb"), exp, args.dev_threshold)
        probes.append(dict(kind=m.get("kind"), n_tokens=n_tokens, n_loss_pos=n_loss,
                           peak_gb=m.get("peak_mem_gb"), expected_gb=exp, dev=d, flag=flag))
    r["probes"] = probes
    summ = ev["summary"]
    if summ:
        wp = next((p for p in probes if p["kind"] == summ.get("worst_kind")), None)
        d, flag = dev(summ.get("worst_gb"), wp["expected_gb"] if wp else None, args.dev_threshold)
        r["summary"] = dict(pick=summ.get("pick"), scope=summ.get("scope"), worst_gb=summ.get("worst_gb"),
                            worst_kind=summ.get("worst_kind"),
                            expected_gb=wp["expected_gb"] if wp else None, dev=d, flag=flag)
    else:
        r["summary"] = None
    steps = ev["step"]
    peaks = [s.get("peak_mem_gb") for s in steps if s.get("peak_mem_gb") is not None]
    r["step_peak_gb"] = max(peaks) if peaks else None
    tp = TRUE_PEAK.get((tag, gc))
    r["true_peak_est"] = tp["gb"] if tp else None
    r["true_peak_block"] = tp["block"] if tp else None
    r["true_peak_update"] = tp["update"] + 1 if tp else None
    r["step_peak_dev"], r["step_peak_flag"] = dev(r["step_peak_gb"], r["true_peak_est"], args.dev_threshold)
    gstep_last = steps[-1].get("gstep") if steps else None
    # 还没走到真峰块所在的更新,并且 step 峰值低于估计:这是应当的,不打标记
    steps_total = st.get("steps") or 0
    if (tp and gstep_last is not None and gstep_last < tp["update"] + 1 <= steps_total
            and not st.get("smoke") and r["step_peak_gb"] is not None and r["step_peak_gb"] < tp["gb"]):
        r["step_peak_dev"] = f"{r['step_peak_dev'].replace(' !!', '')} 未到(真峰块在第 {tp['update'] + 1} 次更新)"
        r["step_peak_flag"] = False
    if st.get("smoke") and r["step_peak_gb"] is not None and r["true_peak_est"] is not None:
        r["step_peak_dev"] = r["step_peak_dev"].replace(" !!", "") + " (smoke 块小,不比)"
        r["step_peak_flag"] = False

    # ---- 曲线 ----
    losses = [s.get("loss") for s in steps if s.get("loss") is not None]
    finite = [x for x in losses if isinstance(x, (int, float)) and math.isfinite(x)]
    r["loss"] = dict(n=len(losses), first=finite[0] if finite else None, last=finite[-1] if finite else None,
                     max=max(finite) if finite else None, min=min(finite) if finite else None,
                     n_nonfinite=len(losses) - len(finite))
    gns = [s.get("grad_norm") for s in steps if s.get("grad_norm") is not None]
    gfin = [x for x in gns if isinstance(x, (int, float)) and math.isfinite(x)]
    med = statistics.median(gfin) if gfin else None
    r["grad_norm"] = dict(n=len(gns), median=med, max=max(gfin) if gfin else None,
                          last=gfin[-1] if gfin else None,
                          n_over=sum(1 for x in gfin if med and x > args.grad_factor * med) if gfin else 0,
                          n_nonfinite=len(gns) - len(gfin),
                          argmax_gstep=(steps[[s.get("grad_norm") for s in steps].index(max(gfin))].get("gstep")
                                        if gfin else None))
    vals = [(e.get("frac"), e.get("gstep"), e.get("val_ce"), e.get("val_exact_call", e.get("val_exact_params")),
             e.get("gen_s")) for e in ev["eval"]]
    marks = []
    for i, (frac, gstep, vce, vex, gs) in enumerate(vals):
        up = i > 0 and vals[i - 1][2] is not None and vce is not None and vce > vals[i - 1][2]
        marks.append(dict(frac=frac, gstep=gstep, val_ce=vce, val_exact=vex, gen_s=gs, up=up))
    r["evals"] = marks
    r["n_val_up"] = sum(1 for m in marks if m["up"])
    r["lr_last"] = steps[-1].get("lr") if steps else None
    r["gstep_last"] = steps[-1].get("gstep") if steps else None
    r["ips_last"] = steps[-1].get("ips") if steps else None
    r["last_step_age_min"] = (now - steps[-1]["t"]) / 60 if steps and "t" in steps[-1] else None
    r["step_interval_min"] = ((steps[-1]["t"] - steps[-2]["t"]) / 60
                              if len(steps) >= 2 and "t" in steps[-1] and "t" in steps[-2] else None)
    dn = ev["done"] or {}
    r["done"] = bool(ev["done"])
    r["best_val_ce"] = dn.get("best_val_ce")
    r["best_frac"] = dn.get("best_frac")
    r["wall_s"] = dn.get("wall_s")
    return r


def render(rows, args):
    print("显存(GB):worst_gb 对同块预期;step 峰值对该配置 epoch 0 真峰估计(design 9.9)")
    print("| run_id | 配置 | 检查点 | lr | align | pick/scope | worst_gb (kind) | 预期 | 偏差 | step 峰值 | 真峰估计 | 偏差 | 进度 |")
    print("|" + "---|" * 13)
    for r in rows:
        if r.get("error"):
            print(f"| {r['run_id']} | | | | | | | | | | | | {r['error']} |")
            continue
        s = r.get("summary")
        gc = r.get("grad_ckpt")
        gc_s = ("缺" if gc is None else ("开" if gc else "关")) + ("(假定)" if r.get("grad_ckpt_source") == "假定" else "")
        prog = f"{r.get('gstep_last')}/{r.get('steps_total')}" + ("(done)" if r.get("done") else "")
        al = f"{r.get('align_pass')} {r.get('align_maxdiff'):.2e}" if r.get("align_maxdiff") is not None else "缺"
        print(f"| {r['run_id']} | {r['tag']} | {gc_s} | {r.get('lr')} | {al} | "
              f"{(s['pick'] + '/' + str(s['scope'])) if s else '缺'} | "
              f"{(fmt(s['worst_gb']) + ' (' + str(s['worst_kind']) + ')') if s else '缺'} | "
              f"{fmt(s['expected_gb'], 1) if s else '缺'} | {s['dev'] if s else '缺'} | "
              f"{fmt(r.get('step_peak_gb'))} | {fmt(r.get('true_peak_est'), 1)} | {r.get('step_peak_dev')} | {prog} |")
    print()
    print("曲线:loss 与 grad_norm 来自 step 事件,val_ce 来自 eval 事件(↑ = 比前一点上升)")
    print("| run_id | lr | loss 首→末 (最大/最小, 非有限) | grad_norm 中位/最大@gstep/末 (超中位×{:g} 条数) | val_ce 序列 | 末 lr | 末 step 距现在 min / 间隔 min | done best |".format(args.grad_factor))
    print("|" + "---|" * 8)
    for r in rows:
        if r.get("error"):
            continue
        L, G = r["loss"], r["grad_norm"]
        vseq = " → ".join(f"{fmt(m['val_ce'], 4)}{'↑' if m['up'] else ''}" for m in r["evals"]) or "无"
        print(f"| {r['run_id']} | {r.get('lr')} | {fmt(L['first'], 4)}→{fmt(L['last'], 4)} ({fmt(L['max'], 4)}/{fmt(L['min'], 4)}, {L['n_nonfinite']}) | "
              f"{fmt(G['median'], 3)}/{fmt(G['max'], 3)}@{G['argmax_gstep']}/{fmt(G['last'], 3)} ({G['n_over']}) | {vseq} | "
              f"{r.get('lr_last')} | {fmt(r.get('last_step_age_min'), 1)} / {fmt(r.get('step_interval_min'), 1)} | "
              f"{r.get('done')} {fmt(r.get('best_val_ce'), 4)}@{r.get('best_frac')} |")
    flagged = [r["run_id"] for r in rows if not r.get("error") and (
        (r.get("summary") and r["summary"].get("flag")) or r.get("step_peak_flag"))]
    diverge = [r["run_id"] for r in rows if not r.get("error") and (
        r["loss"]["n_nonfinite"] or r["grad_norm"]["n_nonfinite"] or r["grad_norm"]["n_over"] or r["n_val_up"])]
    print()
    print(f"显存偏差超过 ±{args.dev_threshold:g}% 的 run: {', '.join(flagged) if flagged else '无'}")
    print(f"曲线有异常标记(非有限 loss/grad_norm、grad_norm 超中位 ×{args.grad_factor:g}、val_ce 上升)的 run: "
          f"{', '.join(diverge) if diverge else '无'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="*")
    ap.add_argument("--glob", default=None, help="run 目录的 glob,比如 'pipeline/runs/sweep/*'")
    ap.add_argument("--dev-threshold", type=float, default=15.0)
    ap.add_argument("--grad-factor", type=float, default=5.0, help="grad_norm 超过中位数的几倍算异常")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    dirs = list(args.run_dirs)
    if args.glob:
        dirs += sorted(d for d in glob.glob(args.glob) if Path(d).is_dir())
    if not dirs:
        print("没有 run 目录(目录不存在或 glob 没匹配到)")
        return 0
    now = time.time()
    rows = [analyze(d, args, now) for d in dirs]
    render(rows, args)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
