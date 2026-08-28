#!/usr/bin/env python3
"""学习率扫描的驱动与报表(`.scratch/kvshare-train/spec.md` 16.6,工单 11)。

要回答什么问题:四个底座配置(全参 0.6B/1.7B、LoRA 1.7B/4B)各自的三个学习率
锚点里,哪一个 `val_ce` 最低?本文件只出两件事,GPU 发射由主会话走 gpu-run:

  plan   —— 按 `GRID` 生成 12 条 `train_causal_share.py` 命令,打印成清单与
             `python3 run.py launch` 行,`--write` 落 JSON。
  report —— 扫一批 run 目录的 `train_log.jsonl`,收成 `SWEEP_REPORT.json`
             与 `SWEEP_REPORT.md`。

用法:
    python3 run.py sweep-lr plan
    python3 run.py sweep-lr plan --write pipeline/runs/sweep/plan.json
    python3 run.py sweep-lr report --runs pipeline/runs/sweep/ks828* \\
        --out pipeline/runs/sweep
"""
import argparse
import datetime
import glob
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 网格常量(spec 16.6 决定 29、16.8 决定 30)——冒烟后可能再改,写成一眼能改
# 的样子:每项 tag/base/lora/lrs(全参三锚点 1e-5,5e-5,2e-4;LoRA 逐点乘 10
# 变 1e-4,5e-4,2e-3)/tok_budget/card(卡的种类,给发射员看)/extra(附加旗标)。
GRID = [
    dict(tag="b06", base="qwen", lora=False,
         lrs=[1e-5, 5e-5, 2e-4], tok_budget=16384, card="Ada",
         extra=["--grad-ckpt"]),
    dict(tag="b17", base="qwen17", lora=False,
         lrs=[1e-5, 5e-5, 2e-4], tok_budget=16384, card="H200",
         extra=[]),
    dict(tag="l17", base="qwen17", lora=True,
         lrs=[1e-4, 5e-4, 2e-3], tok_budget=16384, card="H200",
         extra=[]),
    dict(tag="l4", base="qwen4", lora=True,
         lrs=[1e-4, 5e-4, 2e-3], tok_budget=16384, card="H100",
         # --align-tol 3e-5:4B 的 fp32 逐行对齐差 1.54e-5 离默认 2e-5 只有
         # 23% 余量,同卡型逐位可复现,放宽给换卡型/换 torch 留余量(决定 36)
         extra=["--grad-ckpt", "--align-tol", "3e-5"]),
]

DEFAULT_DATA = "pipeline/data/nyapass_aw_v1/gptoss"
DEFAULT_OUT_ROOT = "pipeline/runs/sweep"
DEFAULT_TRACK = "kvshare-lr-sweep"


def fmt_lr(lr):
    """`1e-05` -> `1e-5`,`2e-04` -> `2e-4`:`f"{lr:.0e}"` 只留一位有效数字,
    再把指数里的前导零去掉。两个学习率格式化后撞车就是网格出了非单位数
    有效数字的值(比如 1.2e-5),`plan` 的自检靠这个撞车发现。"""
    s = f"{lr:.0e}"
    mantissa, exp = s.split("e")
    sign = exp[0]
    digits = exp[1:].lstrip("0") or "0"
    return f"{mantissa}e{sign}{digits}"


def build_plan(grid, data_dir, out_root, py):
    """纯函数:网格 -> 12 条 run 记录。`data_dir`/`out_root` 已解析成绝对路径。"""
    rows = []
    for cfg in grid:
        for lr in cfg["lrs"]:
            lr_s = fmt_lr(lr)
            run_id = f"ks828{cfg['tag']}_gptoss_cgen_lr{lr_s}"
            outdir = out_root / run_id
            cmd = [py, str(ROOT / "pipeline/train/train_causal_share.py"),
                   "--mode", "cgen",
                   "--base", cfg["base"],
                   "--env", "appworld",
                   "--data", str(data_dir),
                   "--out", str(outdir),
                   "--lr", lr_s,
                   "--tok-budget", str(cfg["tok_budget"]),
                   "--epochs", "1",
                   "--eval-per-epoch", "4",
                   "--log-every", "10",
                   "--mem-probe"]
            if cfg["lora"]:
                cmd.append("--lora")
            cmd += list(cfg["extra"])
            rows.append(dict(run_id=run_id, tag=cfg["tag"], base=cfg["base"],
                              lora=cfg["lora"], lr=lr, lr_s=lr_s,
                              tok_budget=cfg["tok_budget"], card=cfg["card"],
                              extra=list(cfg["extra"]),
                              cmd=" ".join(cmd), outdir=str(outdir)))

    # 自检:run_id 两两不同,重复就 SystemExit 并打印撞车的两条(含 lr 原值)。
    seen = {}
    for r in rows:
        prior = seen.get(r["run_id"])
        if prior is not None:
            raise SystemExit(
                f"run_id 撞车: {r['run_id']}\n"
                f"  第一条: tag={prior['tag']} lr={prior['lr']}\n"
                f"  第二条: tag={r['tag']} lr={r['lr']}\n"
                f"(fmt_lr 只留一位有效数字,网格里两个 lr 格式化后重合了)")
        seen[r["run_id"]] = r
    return rows


def cmd_plan(args):
    grid = GRID
    if args.grid:
        grid = json.loads(Path(args.grid).read_text())

    data_dir = Path(args.data)
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    data_dir = data_dir.resolve()

    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    out_root = out_root.resolve()

    rows = build_plan(grid, data_dir, out_root, args.py)

    print("| run_id | tag | base | lora | lr | tok_budget | card | extra |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        extra_s = " ".join(r["extra"]) if r["extra"] else "-"
        print(f"| {r['run_id']} | {r['tag']} | {r['base']} | {r['lora']} | "
              f"{r['lr_s']} | {r['tok_budget']} | {r['card']} | {extra_s} |")

    print()
    print("把下面每行的 --piece 占位换成排卡表里的实际卡:")
    for r in rows:
        quoted = shlex.quote(r["cmd"])
        print(f"python3 run.py launch --cmd {quoted} --run-id {r['run_id']} "
              f"--track {args.track} --outdir {r['outdir']} "
              f"--piece <host>:<gpus>")

    if args.write:
        out = [dict(run_id=r["run_id"], tag=r["tag"], base=r["base"],
                     lora=r["lora"], lr=r["lr"], tok_budget=r["tok_budget"],
                     card=r["card"], cmd=r["cmd"], outdir=r["outdir"])
               for r in rows]
        Path(args.write).write_text(
            json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def _read_events(run_dir):
    log_path = run_dir / "train_log.jsonl"
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def summarize_run(run_dir):
    """一个 run 目录 -> 一条报告记录(dict),按 spec 16.6 的字段取法。"""
    events = _read_events(run_dir)
    start = next((e for e in events if e["event"] == "start"), None)
    evals = [e for e in events if e["event"] == "eval"]
    done = next((e for e in events if e["event"] == "done"), None)
    steps = [e for e in events if e["event"] == "step"]
    mem_summary = next(
        (e for e in events if e["event"] == "mem_probe_summary"), None)
    mem_probes = [e for e in events if e["event"] == "mem_probe"]

    eval_rows = []
    for e in evals:
        val_exact = e.get("val_exact_call", e.get("val_exact_params"))
        eval_rows.append(dict(ep=e.get("ep"), frac=e.get("frac"),
                               val_ce=e.get("val_ce"), val_exact=val_exact))

    # val_exact 不是每个评估点都有(--gen-eval-at last 时只有 epoch 末那条
    # 有);spec 16.6 取有值的那个评估点的值,标出它的 (ep, frac),多个点有
    # 值时取最后一个——按 eval_rows 的顺序遍历,每碰到有值的就覆盖,循环
    # 完留下的就是最后一个有值的点。
    val_exact_best = val_exact_frac = None
    for r in eval_rows:
        if r["val_exact"] is not None:
            val_exact_best = r["val_exact"]
            val_exact_frac = f"{r['ep']}.{r['frac']}"

    peak_mem_gb = (max(s.get("peak_mem_gb") for s in steps)
                   if steps else None)
    if mem_summary is not None:
        worst_gb = mem_summary.get("worst_gb")
    elif mem_probes:
        worst_gb = max(m.get("peak_mem_gb") for m in mem_probes)
    else:
        worst_gb = None

    if done is not None:
        status = "done"
        best_val_ce = done.get("best_val_ce")
        best_frac = done.get("best_frac")
        best_ep = done.get("best_ep")
        wall_s = done.get("wall_s")
    else:
        status = "running"
        wall_s = None
        if eval_rows:
            best = min(eval_rows, key=lambda r: r["val_ce"])
            best_val_ce, best_frac, best_ep = (
                best["val_ce"], best["frac"], best["ep"])
        else:
            best_val_ce = best_frac = best_ep = None

    return dict(
        run_id=run_dir.name, status=status,
        base=start.get("base") if start else None,
        lora=bool(start and "lora" in start),
        lr=start.get("lr") if start else None,
        tok_budget=start.get("tok_budget") if start else None,
        n_train_events=start.get("n_train_events") if start else None,
        dropped_events_train=(
            start.get("dropped_events_train") if start else None),
        evals=eval_rows, best_val_ce=best_val_ce, best_frac=best_frac,
        _best_ep=best_ep, wall_s=wall_s, peak_mem_gb=peak_mem_gb,
        worst_gb=worst_gb, val_exact=val_exact_best,
        val_exact_frac=val_exact_frac)


def _expand_runs(patterns):
    dirs = set()
    for pat in patterns:
        for hit in glob.glob(pat):
            dirs.add(Path(hit))
    return sorted(dirs)


def cmd_report(args):
    dirs = _expand_runs(args.runs)
    records = []
    for d in dirs:
        if not (d / "train_log.jsonl").exists():
            print(f"[跳过] 没有 train_log.jsonl: {d}", file=sys.stderr)
            continue
        records.append(summarize_run(d))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_records = [{k: v for k, v in r.items() if k != "_best_ep"}
                     for r in records]
    (out_dir / "SWEEP_REPORT.json").write_text(
        json.dumps(json_records, ensure_ascii=False, indent=1))

    # 分组 = (base, lora),组内按 lr 升序;组间按 (base, lora) 排序。
    groups = {}
    for r in records:
        groups.setdefault((r["base"], r["lora"]), []).append(r)
    for key in groups:
        # (x is None, x) 在两条都缺 lr 时拿 (True, None) 比 (True, None),
        # 第二个元素 None < None 抛 TypeError——None 时换一个可比的替身
        # (0.0),排序结果不看这个替身的值(第一个元素已经把 None 排到最后)。
        groups[key].sort(
            key=lambda r: (r["lr"] is None, r["lr"] if r["lr"] is not None else 0.0))

    # 动态列:全部 run 出现过的 (ep, frac) 组合,升序。
    combos = sorted({(e["ep"], e["frac"])
                      for r in records for e in r["evals"]
                      if e["ep"] is not None and e["frac"] is not None})

    lines = []
    lines.append(f"生成时间: {datetime.datetime.now().isoformat(timespec='seconds')}"
                  f"  读取目录数: {len(records)}")
    lines.append("")
    combo_cols = [f"val_ce@{ep}.{frac}" for ep, frac in combos]
    header = (["run_id", "lr"] + combo_cols +
              ["best_val_ce", "best_frac", "val_exact(@ep.frac)",
               "peak_mem_gb", "worst_gb", "wall_s", "status"])
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    def _fmt(v):
        return "-" if v is None else str(v)

    for key in sorted(groups, key=lambda k: (k[0] or "", k[1])):
        rows = groups[key]
        # 同上:两条都缺 best_val_ce 时 None 换成可比的替身 0.0,不影响排序
        # (第一个元素已经把 None 排到最后)。
        best_i = min(range(len(rows)), key=lambda i: (
            rows[i]["best_val_ce"] is None,
            rows[i]["best_val_ce"] if rows[i]["best_val_ce"] is not None else 0.0))
        for i, r in enumerate(rows):
            by_combo = {(e["ep"], e["frac"]): e["val_ce"] for e in r["evals"]}
            # val_exact 取的是"有值的那个评估点"(spec 16.6),不一定是
            # best_val_ce 所在的评估点——summarize_run 已经按这条规则挑好
            # 存进 r["val_exact"]/r["val_exact_frac"],这里直接读,不再按
            # best_ep/best_frac 重新配对。
            val_exact_cell = ("-" if r["val_exact"] is None else
                              f"{r['val_exact']}@{r['val_exact_frac']}")
            run_id_cell = ("*" + r["run_id"]) if i == best_i else r["run_id"]
            lr_cell = fmt_lr(r["lr"]) if r["lr"] is not None else "-"
            row = [run_id_cell, lr_cell]
            row += [_fmt(by_combo.get(c)) for c in combos]
            row += [_fmt(r["best_val_ce"]), _fmt(r["best_frac"]),
                    val_exact_cell, _fmt(r["peak_mem_gb"]),
                    _fmt(r["worst_gb"]), _fmt(r["wall_s"]), r["status"]]
            lines.append("| " + " | ".join(row) + " |")

    (out_dir / "SWEEP_REPORT.md").write_text("\n".join(lines) + "\n")
    return 0


def build_argparser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("plan", help="按网格生成 run 清单")
    pp.add_argument("--grid", default=None, help="JSON 文件,整体替换 GRID")
    pp.add_argument("--data", default=DEFAULT_DATA)
    pp.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    pp.add_argument("--py", default=str(ROOT / "cprobe-env/bin/python"))
    pp.add_argument("--track", default=DEFAULT_TRACK)
    pp.add_argument("--write", default=None, help="落一份 plan.json")
    pp.set_defaults(func=cmd_plan)

    rp = sub.add_parser("report", help="收一批 run 目录成报表")
    rp.add_argument("--runs", nargs="+", required=True,
                     help="run 目录路径或 glob,可给多个")
    rp.add_argument("--out", required=True, help="报表输出目录")
    rp.set_defaults(func=cmd_report)

    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
