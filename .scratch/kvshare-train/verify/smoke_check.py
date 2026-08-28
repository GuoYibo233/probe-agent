#!/usr/bin/env python3
"""kvshare 第二轮冒烟与扫描 run 的判读表(只读,不进注册表;纯 stdlib,系统 python3 可跑)。

用法:
  python3 .scratch/kvshare-train/verify/smoke_check.py <run_dir> [<run_dir> ...] \
      [--dev-threshold 15] [--json <out.json>]

每个 run_dir 读 train_log.jsonl(start / mem_probe / mem_probe_summary / eval / step / done 事件,
字段名按 spec 16.3 到 16.5)与 ALIGN_CHECK.json,输出:
  1. 一张汇总表:run_id、配置(b06/b17/l17/l4,从 start 的 base 与 lora 推)、检查点(best/meta.json
     的 grad_ckpt,没有就按排卡计划假定并标 "假定")、align PASS 与 max_abs_diff、探针 pick/scope、
     worst_gb(worst_kind)、worst 那一块的预期值与偏差、step 峰值最大值、wall_s。
  2. 每个 run 的明细:每条 mem_probe 事件的 kind、B、L_pad、n_tokens、n_loss_pos、peak、预期、偏差;
     每条 eval 事件的 frac、val_ce、val_exact_call(cparam 是 val_exact_params)、gen_n、gen_s。

预期值的算法(design-attention.md 9.1,单位 GB):
  预期 = 固定项 + 每 token 系数 × n_tokens / 1000 + 1.8 × n_loss_pos / 1000
固定项与系数按配置和检查点取(9.1 表);n_tokens / n_loss_pos 取探针事件里记的值,旧格式的事件
(只有 B、L_pad)按 B × L_pad 与默认损失位(fullest_block 1,984、longest_event 1,344)补。tokens 探针
默认块(16,384 个 token、1,984 个损失位)代进去:b17 不开检查点 98.1、l17 不开 77.7、l4 开 28.8、
b06 开 15.8(四个配置都已按 2026-08-28 到 29 的冒烟校准,design 9.8 与 9.9)。偏差 = (实测 − 预期) / 预期,
绝对值超过 --dev-threshold(默认 15%)的行打 "!!" 标记。
"""
import argparse
import json
import sys
from pathlib import Path

# 9.1 的显存模型(GB),按配置给 (不开检查点, 开检查点) 两个值。固定项:不开检查点含 fp32 权重、
# bf16 副本、梯度、AdamW 状态或 LoRA 四份;开检查点时 LoRA 的 bf16 副本不常驻(design 9.9:l4 两点
# 拟合 16.25,对 24.66 少的正是副本 8.04),全参少约 0.6。实测校准的:b06 两档、b17/l17 不开检查点
# (design 9.8)、l4 开检查点(9.9);其余是推算值:b17 开检查点 30.4、l17 开检查点 7.16(10.60 减副本
# 3.44)、l4 不开检查点 24.66。
FIXED_GB = {"b06": (10.86, 10.27), "b17": (30.97, 30.4), "l17": (10.60, 7.16), "l4": (24.66, 16.25)}
MB_PER_TOKEN = {  # (不开检查点, 开检查点)
    # 实测校准:b06 不开 2.44(8.6/9.1)、开 0.12(9.9);1.7B 不开 3.88(9.8);l4 开 0.55(9.9)。
    # 推算值:1.7B 开检查点 0.38、4B 不开检查点 7.32(两个底座峰值时刻不同,不能用倍率互推)
    "b06": (2.44, 0.12), "b17": (3.88, 0.38), "l17": (3.88, 0.38), "l4": (7.32, 0.55)}
MB_PER_LOSS_POS = 1.8
# 排卡计划(决定 30)里各配置是否开检查点;meta.json 没有 grad_ckpt 的时候用这个假定
PLANNED_GC = {"b06": True, "b17": False, "l17": False, "l4": True}
# 旧格式探针事件(没有 n_loss_pos)的默认损失位数:全集最满块与最长事件(9.2、8.6)
DEFAULT_LOSS_POS = {"fullest_block": 1984, "longest_event": 1344}
TAG_BY_BASE = {"qwen": "b06", "qwen17": "b17", "qwen4": "b4"}


def load_log(path):
    ev = {"start": None, "done": None, "summary": None, "mem_probe": [], "eval": [], "step": []}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        k = r.get("event")
        if k == "start":
            ev["start"] = r
        elif k == "done":
            ev["done"] = r
        elif k == "mem_probe_summary":
            ev["summary"] = r
        elif k in ("mem_probe", "eval", "step"):
            ev[k].append(r)
    return ev


def config_tag(start):
    """从 start 事件推配置名:base 决定底座,lora 键在不在决定训法。"""
    if not start:
        return "?"
    base = start.get("base", "?")
    tag = TAG_BY_BASE.get(base)
    if tag is None:
        tag = Path(str(base)).name or "?"        # --base 传的是目录(测试用小模型)
    if "lora" in start:
        tag = "l" + tag[1:] if tag.startswith("b") else "l:" + tag
    return tag


def grad_ckpt_of(run_dir, tag):
    """best/meta.json 的 grad_ckpt 是唯一记录检查点开关的地方;没有就按排卡计划假定。"""
    meta = run_dir / "best" / "meta.json"
    if meta.exists():
        try:
            m = json.loads(meta.read_text())
            return bool(m.get("grad_ckpt", False)), "meta"
        except (OSError, ValueError):
            pass
    if tag in PLANNED_GC:
        return PLANNED_GC[tag], "假定"
    return None, "缺"


def expected_gb(tag, gc, n_tokens, n_loss_pos):
    if tag not in FIXED_GB or gc is None or n_tokens is None or n_loss_pos is None:
        return None
    coef = MB_PER_TOKEN[tag][1 if gc else 0]
    fixed = FIXED_GB[tag][1 if gc else 0]
    return fixed + coef * n_tokens / 1e3 + MB_PER_LOSS_POS * n_loss_pos / 1e3


def probe_numbers(m):
    """一条 mem_probe 事件的 (n_tokens, n_loss_pos);旧格式按 B × L_pad 与默认损失位补。"""
    b = m.get("B", m.get("n_events"))
    l_pad = m.get("L_pad", m.get("packed_len_max"))
    n_tokens = m.get("n_tokens")
    if n_tokens is None and b is not None and l_pad is not None:
        n_tokens = b * l_pad
    n_loss = m.get("n_loss_pos")
    if n_loss is None:
        n_loss = DEFAULT_LOSS_POS.get(m.get("kind"))
    return n_tokens, n_loss


def fmt(v, nd=2):
    if v is None:
        return "缺"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def fmt_sci(v):
    return "缺" if v is None else f"{v:.2e}"


def dev_str(measured, expected, threshold):
    if measured is None or expected is None or expected <= 0:
        return "缺", False
    d = (measured - expected) / expected * 100
    flag = abs(d) > threshold
    return f"{d:+.1f}%" + (" !!" if flag else ""), flag


def analyze(run_dir, threshold):
    run_dir = Path(run_dir)
    out = dict(run_id=run_dir.name, dir=str(run_dir))
    log_p, align_p = run_dir / "train_log.jsonl", run_dir / "ALIGN_CHECK.json"
    if align_p.exists():
        a = json.loads(align_p.read_text())
        out["align"] = dict(PASS=a.get("PASS"), max_abs_diff=a.get("max_abs_diff"),
                            max_tok_diff=a.get("max_tok_diff"), rule=a.get("rule"),
                            bf16_mean=a.get("bf16_mean_abs_diff"), baseline_warn=a.get("baseline_warn"))
    else:
        out["align"] = None
    if not log_p.exists():
        out["error"] = "train_log.jsonl 缺"
        return out
    ev = load_log(log_p)
    st = ev["start"] or {}
    tag = config_tag(st)
    gc, gc_src = grad_ckpt_of(run_dir, tag)
    out.update(tag=tag, grad_ckpt=gc, grad_ckpt_source=gc_src, mode=st.get("mode"),
               tok_budget=st.get("tok_budget"), mem_probe_pick=st.get("mem_probe_pick"),
               gen_eval=st.get("gen_eval"), n_train_events=st.get("n_train_events"),
               smoke=st.get("smoke"), lr=st.get("lr"),
               align_pass_start=st.get("align_pass"), align_bf16_warn=st.get("align_bf16_warn"))

    probes = []
    for m in ev["mem_probe"]:
        n_tokens, n_loss = probe_numbers(m)
        exp = expected_gb(tag, gc, n_tokens, n_loss)
        peak = m.get("peak_mem_gb")
        d, flag = dev_str(peak, exp, threshold)
        probes.append(dict(kind=m.get("kind"), pick=m.get("pick"), B=m.get("B", m.get("n_events")),
                           L_pad=m.get("L_pad", m.get("packed_len_max")), n_tokens=n_tokens,
                           n_rows=m.get("n_rows"), n_loss_pos=n_loss, n_backward=m.get("n_backward"),
                           peak_gb=peak, expected_gb=exp, dev=d, flag=flag))
    out["probes"] = probes

    summ = ev["summary"]
    if summ:
        out["summary"] = dict(pick=summ.get("pick"), worst_gb=summ.get("worst_gb"),
                              worst_kind=summ.get("worst_kind"), scope=summ.get("scope"),
                              n_events_considered=summ.get("n_events_considered"), source="summary")
    elif probes:
        w = max((p for p in probes if p["peak_gb"] is not None), key=lambda p: p["peak_gb"], default=None)
        out["summary"] = (dict(pick=st.get("mem_probe_pick", "tokens(旧格式)"), worst_gb=w["peak_gb"],
                               worst_kind=w["kind"], scope="full?", n_events_considered=None,
                               source="max(mem_probe)") if w else None)
    else:
        out["summary"] = None
    if out["summary"]:
        wk = out["summary"]["worst_kind"]
        wp = next((p for p in probes if p["kind"] == wk), None)
        out["summary"]["expected_gb"] = wp["expected_gb"] if wp else None
        out["summary"]["dev"], out["summary"]["flag"] = dev_str(
            out["summary"]["worst_gb"], out["summary"]["expected_gb"], threshold)
        out["summary"]["x1_1"] = (None if out["summary"]["worst_gb"] is None
                                  else out["summary"]["worst_gb"] * 1.1)

    evals = []
    for e in ev["eval"]:
        exact = e.get("val_exact_call", e.get("val_exact_params"))
        evals.append(dict(ep=e.get("ep"), frac=e.get("frac"), gstep=e.get("gstep"),
                          val_ce=e.get("val_ce"), val_exact=exact, gen_n=e.get("gen_n"),
                          gen_s=e.get("gen_s"), n_eval_rows=e.get("n_eval_rows")))
    out["evals"] = evals
    steps = ev["step"]
    out["step_peak_gb"] = max((s.get("peak_mem_gb") or 0.0) for s in steps) if steps else None
    out["n_steps_logged"] = len(steps)
    out["last_ips"] = steps[-1].get("ips") if steps else None
    dn = ev["done"] or {}
    out["done"] = bool(ev["done"])
    out["wall_s"] = dn.get("wall_s")
    out["best_val_ce"] = dn.get("best_val_ce")
    out["best_frac"] = dn.get("best_frac")
    return out


def render(rows):
    head = ("| run_id | 配置 | 检查点 | align PASS / max_abs_diff | pick / scope | worst_gb (kind) "
            "| 预期 GB | 偏差 | worst×1.1 | step 峰值 GB | eval 次数 / best val_ce | wall_s |")
    print(head)
    print("|" + "---|" * 12)
    for r in rows:
        if r.get("error"):
            print(f"| {r['run_id']} | | | | | | | | | | | {r['error']} |")
            continue
        al = r.get("align")
        al_s = "缺" if al is None else f"{al.get('PASS')} / {fmt_sci(al.get('max_abs_diff'))}"
        gc = r.get("grad_ckpt")
        gc_s = ("缺" if gc is None else ("开" if gc else "关")) + (
            f"({r['grad_ckpt_source']})" if r.get("grad_ckpt_source") == "假定" else "")
        s = r.get("summary")
        if s:
            pick_s = f"{s.get('pick')} / {s.get('scope')}"
            worst_s = f"{fmt(s.get('worst_gb'))} ({s.get('worst_kind')})"
            exp_s, dev_s, x11 = fmt(s.get("expected_gb"), 1), s.get("dev"), fmt(s.get("x1_1"), 1)
        else:
            pick_s = worst_s = exp_s = dev_s = x11 = "缺"
        ev_s = f"{len(r['evals'])} / {fmt(r.get('best_val_ce'), 4)}"
        print(f"| {r['run_id']} | {r['tag']} | {gc_s} | {al_s} | {pick_s} | {worst_s} | {exp_s} | {dev_s} "
              f"| {x11} | {fmt(r.get('step_peak_gb'))} | {ev_s} | {fmt(r.get('wall_s'), 1)}"
              f"{'' if r.get('done') else '(未 done)'} |")
    for r in rows:
        if r.get("error"):
            continue
        print()
        print(f"== {r['run_id']}  配置 {r['tag']}  mode {r.get('mode')}  lr {r.get('lr')}  "
              f"tok_budget {r.get('tok_budget')}  smoke {r.get('smoke')}  n_train_events {r.get('n_train_events')}  "
              f"gen_eval {r.get('gen_eval')}  mem_probe_pick {r.get('mem_probe_pick')}  "
              f"检查点来源 {r.get('grad_ckpt_source')}")
        al = r.get("align")
        if al:
            print(f"   align: PASS={al.get('PASS')} max_abs_diff={fmt_sci(al.get('max_abs_diff'))} "
                  f"max_tok_diff={fmt_sci(al.get('max_tok_diff'))} bf16_mean={fmt_sci(al.get('bf16_mean'))} "
                  f"rule={al.get('rule')} baseline_warn={al.get('baseline_warn')}")
        for p in r["probes"]:
            print(f"   mem_probe {p['kind']:>18s}: B={p['B']} L_pad={p['L_pad']} n_tokens={p['n_tokens']} "
                  f"n_rows={p['n_rows']} n_loss_pos={p['n_loss_pos']} n_backward={p['n_backward']} "
                  f"peak={fmt(p['peak_gb'])} 预期={fmt(p['expected_gb'], 1)} 偏差={p['dev']}")
        s = r.get("summary")
        if s:
            print(f"   summary({s.get('source')}): pick={s.get('pick')} scope={s.get('scope')} "
                  f"worst={fmt(s.get('worst_gb'))} ({s.get('worst_kind')}) "
                  f"n_events_considered={s.get('n_events_considered')} 预期={fmt(s.get('expected_gb'), 1)} "
                  f"偏差={s.get('dev')} worst×1.1={fmt(s.get('x1_1'), 1)}")
        for e in r["evals"]:
            print(f"   eval ep={e['ep']} frac={e['frac']} gstep={e['gstep']}: val_ce={fmt(e['val_ce'], 4)} "
                  f"val_exact={fmt(e['val_exact'], 4)} gen_n={e['gen_n']} gen_s={fmt(e['gen_s'], 1)} "
                  f"n_eval_rows={e['n_eval_rows']}")
        print(f"   step: {r['n_steps_logged']} 条, 峰值最大 {fmt(r.get('step_peak_gb'))} GB, 末条 ips {r.get('last_ips')}; "
              f"done={r.get('done')} best_val_ce={fmt(r.get('best_val_ce'), 4)} best_frac={r.get('best_frac')} "
              f"wall_s={fmt(r.get('wall_s'), 1)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--dev-threshold", type=float, default=15.0, help="偏差百分比超过就打 !! 标记")
    ap.add_argument("--json", default=None, help="把全部字段另存成 JSON")
    args = ap.parse_args()
    rows = [analyze(d, args.dev_threshold) for d in args.run_dirs]
    render(rows)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"\nJSON 写到 {args.json}")
    flagged = [r["run_id"] for r in rows if r.get("summary") and r["summary"].get("flag")]
    if flagged:
        print(f"\n偏差超过 ±{args.dev_threshold:g}% 的 run: {', '.join(flagged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
