"""触发时刻调用生成评测(新流水线 cgen 格):在 ctool 的触发点上让 callgen 模型
greedy 写出整条调用,判工具名 / 参数 / 整调用三层正确率。

规格 §6.3 的实现。与 eval_mbert_call.py(抽取头路线)对照读:两边的触发点定义
完全同源(【照抄 eval_extract.py 的 replay_fire()】),差别只在"参数从哪来"——
那边在触发前缀上抽区间,这边直接把整条调用生成出来。

- 触发点: --ctool-run 的 REPLAY_REPORT.json 给温度 T 与 chosen_theta[--risk],
  配 logits_test.pt 在 test 堆上回放,取每事件首次过 θ 的样本行
- 生成: prompt = 触发样本 text + CALL_SEP,CALL_SEP 从 --cgen-run/best/meta.json
  的 `call_sep` 字段读(与训练侧拼串口径同源,不硬编码);greedy、
  max_new_tokens=96、eos 停,再截到首个 \\n,最后 .strip()
  (与训练侧 val_exact_call 口径一致)。生成时 padding_side 临时切 left
- 解析: 工具名【照抄】AW_CALL(appworld)/ALF_CALL(alfworld)/BFCL_CALL(bfcl 与 tales),
  参数【照抄】split_args_named 的切法 + 同一套归一化(strip 后 strip 引号)。
  正则不匹配 = parse_fail
- 判分(真值 = 触发样本的 label 与 args_named):
    tool_ok           解析出的工具名 == label
    参数逐个          宽松 = 归一化后值相等;严格 = 未归一化原串相等;
                      键不匹配(多参/少参/名错)= 该参数错
    params_all_ok     全部参数宽松对(真值无参的事件恒真,并单独成列)
    full_call_ok      tool_ok 且 params_all_ok
- 产物: <cgen-run>/CALLGEN_REPORT.{json,md}

ro1 批次加 `--readonly-env {appworld,bfcl}`(默认关,关=行为逐字节不变):打开后
真值标签在装载处过 readonly_map.collapse()、触发条件加"argmax 不是弃权类";
只给"触发了且真值为只读工具"的事件判分,触发但真值非只读的事件不进
params_all_ok / full_call_ok 分母,单独计进新增键 readonly_excluded。
已有字段名与判分三档一个不动。双向保险丝查两处:ctool run 的 label_map.json
有没有弃权哨兵、cgen run 的 meta.json 有没有 readonly_env 键(缺失=旧模式)。

自主开火评测 `--self-fire`(默认关;打开不动任何旧字段,只加一个 self_fire 块):
给带开火头训练的 cgen run 用——触发点不再从 ctool 的报告拿 θ,而是让 cgen 自己的
开火头决定什么时候发射。
- 开火分数:每个边界上 prompt=text+call_sep 前向一次,取 prompt 末位隐状态过
  best/fire_head.pt,sigmoid 成开火概率(与训练侧取位一致,不看目标串)
- θ_fire 在 **val** 上扫(沿用 eval_tool 的 THETAS 网格与 RISK_TARGETS 机制),
  风险用标签算:错误开火 = 开火了但真值 not-ready
  (ready = 真值工具只读 且 该边界上所有参数 found)
- test 冻结一次:按选定的 θ_fire 回放开火点,在开火点上照原有三档判分生成并算
  参数 / 整调用指标。真值用**未折叠**的原标签,所以错误开火天然判错,不做剔除
- 需要 --readonly-env(ready 的定义依赖只读真值表)与一个 fire_head=true 的 cgen run

用法:
  cprobe-env/bin/python pipeline/eval/eval_causal_call.py --env appworld \\
    --ctool-run pipeline/runs/c1_q35_ctool --cgen-run pipeline/runs/c1_q35_cgen \\
    --data pipeline/data/aw_official_v1/q35
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "annotate"))
from rules import (ALF_CALL, AW_CALL, BFCL_CALL,        # noqa: E402
                   split_args_named)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "train"))
import readonly_map                                     # noqa: E402
import share_data                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_tool import RISK_TARGETS, THETAS              # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat                                         # noqa: E402

MAX_GEN_TOK = 96            # 【照抄 train_causal_callgen.py 的 MAX_GEN_TOK】
FALLBACK_SEP = "\n[CALL] "  # meta.json 没写 call_sep 时的兜底(应当写了)
TOPK_TOOLS = 10             # 分工具明细表行数


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta, nro_id=None):
    """【照抄 eval_extract.py 的 replay_fire()】首次过 θ 的样本行。

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


# ---------------------------------------------------------------- 解析

def norm(v):
    """【照抄】annotate 侧的值归一化:strip() 后 strip("\\"'")。"""
    return v.strip().strip("\"'")


def split_named_raw(argstr):
    """split_args_named 的切法逐字照抄,只把末尾的归一化留给调用方:
    返回 [(key, 未归一化原串)]。与 rules.split_args_named 的一致性在
    parse_call() 里每次断言,防止两份切法漂移。"""
    vals, buf, depth, q = [], "", 0, None
    for ch in argstr:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())
    out, pos = [], 0
    for v in vals:
        m = re.match(r"(\w+)\s*=\s*(.+)", v, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip()))
        else:
            out.append((f"pos{pos}", v.strip()))
            pos += 1
    return out


def parse_call(code, env):
    """-> (tool_name, [(key, raw_value)]) 或 (None, []) 表示 parse_fail。"""
    # alfworld 必须显式分支:落回 BFCL_CALL 的 `(\w+)\(` 会把生成串里第一个
    # "词(" 认成工具名(例如把思考残句里的 `note(` 当工具),静默把 tool_ok 打塌。
    # ALF_CALL 只认 rules.ALF_TEMPLATES 那 13 个官方动作名,与 annotate 侧同源。
    name_re = (AW_CALL if env == "appworld"
               else ALF_CALL if env == "alfworld" else BFCL_CALL)
    m = name_re.search(code)
    if not m:
        return None, []
    tool = (f"apis.{m.group(1)}.{m.group(2)}" if env == "appworld"
            else m.group(1))
    i, depth = m.end() - 1, 0
    inner = None
    for j in range(i, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                inner = code[i + 1: j]
                break
    if inner is None:                      # 括号没闭合(生成被截断)
        return tool, []
    raw = split_named_raw(inner)
    assert [(k, norm(v)) for k, v in raw] == split_args_named(inner), \
        f"切法与 rules.split_args_named 不一致: {inner!r}"
    return tool, raw


def match_params(truth, gen_raw):
    """truth=[{"key","value"}](值已归一化), gen_raw=[(key, 未归一化原串)]。

    按键分组后逐位置比:union 口径——多参/少参/名错都各记一个错实例。
    返回 (n_inst, n_loose_ok, n_strict_ok)。
    """
    tmap, gmap = defaultdict(list), defaultdict(list)
    for a in truth:
        tmap[a["key"]].append(a["value"])
    for k, v in gen_raw:
        gmap[k].append(v)
    n = lo = st = 0
    for k in list(tmap) + [k for k in gmap if k not in tmap]:
        tv, gv = tmap.get(k, []), gmap.get(k, [])
        n += max(len(tv), len(gv))
        for i in range(min(len(tv), len(gv))):
            lo += norm(gv[i]) == tv[i]
            st += gv[i] == tv[i]
    return n, lo, st


# ---------------------------------------------------------------- 生成

@torch.no_grad()
def generate(model, tok, prompts, dev, bs, max_len, max_new):
    """greedy 生成:遇 \\n 或 eos 停,返回 .strip() 后的整条调用串。"""
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "left"                       # 生成必须左 padding
    model.config.use_cache = True
    out = []
    heartbeat.emit(0, len(prompts), "item")
    for i in range(0, len(prompts), bs):
        chunk = prompts[i:i + bs]
        enc = tok(chunk, truncation=True,
                  max_length=max(max_len - max_new, 1), padding=True,
                  add_special_tokens=False, return_tensors="pt").to(dev)
        gen = model.generate(**enc, do_sample=False, max_new_tokens=max_new,
                             eos_token_id=tok.eos_token_id,
                             pad_token_id=tok.pad_token_id)
        txt = tok.batch_decode(gen[:, enc["input_ids"].shape[1]:],
                               skip_special_tokens=True)
        out += [t.split("\n")[0].strip() for t in txt]
        print(f"generated {min(i + bs, len(prompts))}/{len(prompts)}",
              flush=True)
        heartbeat.emit(min(i + bs, len(prompts)), len(prompts), "item")
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


# ------------------------------------------------------------ 自主开火

def load_ready(data, params, split, ro_set):
    """读一堆样本并算开火真值 ready。返回 (rows, stats)。

    ready = 真值工具在只读集合里 且 该样本所有参数 found=true(零参数空真);
    params 里 join 不到的按 not-ready 处理并计数。标签**不折叠**——
    self-fire 这条路不经过 ctool 的标签空间。
    """
    pmap = {}
    for p in load_rows(params / f"{split}.jsonl"):
        pmap[(p["event"], p["sent_idx"])] = p["params"]
    rows = load_rows(data / f"{split}.jsonl")
    st = dict(n=len(rows), n_ready=0, n_readonly=0,
              n_join_miss=0, n_join_miss_with_args=0)
    for r in rows:
        is_ro = r["label"] in ro_set
        st["n_readonly"] += is_ro
        ps = pmap.get((r["event"], r["sent_idx"]))
        if ps is None:
            st["n_join_miss"] += 1
            if r.get("args_named"):
                st["n_join_miss_with_args"] += 1
            r["ready"] = False
        else:
            r["ready"] = bool(is_ro and all(q["found"] for q in ps))
        st["n_ready"] += r["ready"]
    n = max(st["n"], 1)
    st["frac_ready"] = round(st["n_ready"] / n, 6)
    st["frac_readonly"] = round(st["n_readonly"] / n, 6)
    st["frac_join_miss"] = round(st["n_join_miss"] / n, 6)
    if st["frac_join_miss"] > 0.01:
        print(f"[self-fire] 警告:{split} 有 {st['n_join_miss']}/{st['n']} "
              f"({st['frac_join_miss']:.1%}) 个样本在 params 里 join 不到,"
              f"已按 not-ready 处理", flush=True)
    return rows, st


@torch.no_grad()
def score_fire(model, fire, tok, rows, sep, dev, bs, max_len, max_new):
    """每个边界的开火概率。prompt=text+sep,右 padding,取 prompt 末位隐状态。

    截断口径与 generate() 那条路一模一样(max_length = max_len - max_new),
    所以"在哪段前缀上决定开火"与"从哪段前缀开始生成"是同一件东西。
    """
    prev_side, prev_cache = tok.padding_side, model.config.use_cache
    tok.padding_side = "right"                      # 末位靠 attention_mask 定位
    model.config.use_cache = False
    out = torch.zeros(len(rows))
    for i in range(0, len(rows), bs):
        chunk = [r["text"] + sep for r in rows[i:i + bs]]
        enc = tok(chunk, truncation=True,
                  max_length=max(max_len - max_new, 1), padding=True,
                  add_special_tokens=False, return_tensors="pt").to(dev)
        h = model(input_ids=enc["input_ids"],
                  attention_mask=enc["attention_mask"], use_cache=False,
                  output_hidden_states=True).hidden_states[-1]
        last = enc["attention_mask"].sum(1) - 1
        lg = fire(h[torch.arange(h.size(0), device=h.device), last].float())
        out[i:i + len(chunk)] = torch.sigmoid(lg.squeeze(-1).float()).cpu()
        if (i // bs) % 50 == 0:
            print(f"fire-scored {i}/{len(rows)}", flush=True)
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def replay_fire_head(rows, probs, theta, gate=None):
    """开火头版回放:每事件取首个 fire_prob>=θ(且 gate 为真)的边界。

    与 replay_fire 同构,只是判据换成开火概率;gate[i] 用于 mext 那边的
    "argmax 不是弃权类",这里恒 None。
    """
    ev = defaultdict(list)
    for i, (r, p) in enumerate(zip(rows, probs)):
        ev[r["event"]].append((r["sent_idx"], i, r, float(p)))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ready=False, sent_idx=None, row=None, conf=None)
        for _, i, r, p in items:
            if p >= theta and (gate is None or gate[i]):
                rec.update(fired=True, ready=bool(r["ready"]),
                           sent_idx=r["sent_idx"], row=r, conf=round(p, 4))
                break
        out[k] = rec
    return out


def agg_fire(recs):
    """开火头的覆盖率 / 正确率 / 错误开火率,公式与 eval_tool.agg 同构。"""
    n = len(recs)
    fired = [r for r in recs if r["fired"]]
    return dict(n=n, n_fired=len(fired),
                coverage=round(len(fired) / max(n, 1), 4),
                fire_acc=round(sum(r["ready"] for r in fired)
                               / max(len(fired), 1), 4),
                wrong_fire_rate=round(sum(1 for r in fired if not r["ready"])
                                      / max(n, 1), 4))


def pick_theta(sweep):
    """【与 eval_tool 选 θ 同机制】风险约束下取覆盖率最大的那档。"""
    chosen = {}
    for risk in RISK_TARGETS:
        ok = [(th, a) for th, a in sweep
              if a["fire_acc"] >= 1 - risk and a["coverage"] > 0]
        chosen[risk] = (max(ok, key=lambda x: x[1]["coverage"])[0]
                        if ok else None)
    return chosen


# ------------------------------------------------------------ 判分

def score_points(keys, rowof, gens, env, n_samples=20):
    """在给定的触发/开火点上判分。keys 与 gens 同序,rowof[k] 给该点的真值行。

    【判分口径逐字保留】工具名 / 宽松·严格参数 / 整调用三档一个不动。
    """
    per_ev, samples = {}, []
    n_par = n_lo = n_st = 0
    for k, g in zip(keys, gens):
        row = rowof[k]
        truth = row.get("args_named") or []
        tool, raw = parse_call(g, env)
        n, lo, st = match_params(truth, raw)
        n_par += n
        n_lo += lo
        n_st += st
        noparam = not truth
        rec = dict(
            event=k, label=row["label"], label_call=row.get("label_call"),
            gen_call=g, parse_fail=tool is None,
            tool_ok=(tool == row["label"]),
            params_all_ok=(True if noparam else (n > 0 and lo == n)),
            params_all_ok_strict=(True if noparam else (n > 0 and st == n)),
            noparam=noparam,
            exact_call_ok=(g == row.get("label_call")))
        rec["full_call_ok"] = rec["tool_ok"] and rec["params_all_ok"]
        per_ev[k] = rec
        if len(samples) < n_samples:
            samples.append(dict(event=k, truth=row.get("label_call"),
                                gen=g, full_call_ok=rec["full_call_ok"]))
    return per_ev, samples, n_par, n_lo, n_st


def self_fire_block(args, cgen, data, params, meta, model, tok, sep,
                    max_len, dev, ro_set):
    """自主开火:θ_fire 在 val 上扫 → test 冻结一次 → 开火点上生成并判分。"""
    if not meta.get("fire_head"):
        raise SystemExit(
            f"--self-fire 要求 cgen run 是带开火头训的:{cgen/'best'/'meta.json'} "
            "里没有 \"fire_head\": true。请用 train_causal_callgen.py --fire-head 训。")
    fp = cgen / "best" / "fire_head.pt"
    if not fp.exists():
        raise SystemExit(f"--self-fire 找不到开火头权重 {fp}")
    sd = torch.load(fp, map_location="cpu")
    fire = torch.nn.Linear(sd["weight"].shape[1], 1)
    fire.load_state_dict(sd)
    fire = fire.float().to(dev).eval()
    bs = args.fire_bs or args.bs

    val_rows, val_st = load_ready(data, params, "val", ro_set)
    test_rows, test_st = load_ready(data, params, "test", ro_set)

    # θ_fire 在 val 上扫(网格与风险目标沿用 eval_tool 的 THETAS/RISK_TARGETS)
    pv = score_fire(model, fire, tok, val_rows, sep, dev, bs, max_len,
                    args.max_new_tokens)
    sweep = [(th, agg_fire(list(replay_fire_head(val_rows, pv, th).values())))
             for th in THETAS]
    chosen = pick_theta(sweep)
    th_fire = chosen.get(args.risk)
    if th_fire is None:
        print(f"[self-fire] val 上 20 档 θ 都压不到风险≤{args.risk};"
              f"chosen={chosen},本块只出扫描表。", flush=True)
        return dict(theta_fire=None, risk=args.risk,
                    chosen_theta_fire={str(k): v for k, v in chosen.items()},
                    theta_sweep_val=[dict(theta=th, **a) for th, a in sweep],
                    ready_stats=dict(val=val_st, test=test_st),
                    val=None, test=None, scored=None, on_ready=None)

    # test 冻结一次
    pt = score_fire(model, fire, tok, test_rows, sep, dev, bs, max_len,
                    args.max_new_tokens)
    rec = replay_fire_head(test_rows, pt, th_fire)
    keys = [k for k in dict.fromkeys(r["event"] for r in test_rows)
            if rec[k]["fired"]]
    if args.limit:
        keys = keys[:args.limit]
    # 判分用**未折叠**的原标签(load_ready 这条路根本不折叠):
    # 错误开火天然判错,不做剔除
    rowof = {k: rec[k]["row"] for k in keys}
    gens = generate(model, tok, [rowof[k]["text"] + sep for k in keys], dev,
                    args.bs, max_len, args.max_new_tokens) if keys else []
    per_ev, samples, n_par, n_lo, n_st = score_points(keys, rowof, gens,
                                                      args.env)

    def block(ks):
        n = len(ks)
        c = lambda f: sum(1 for k in ks if per_ev[k][f])   # noqa: E731
        return dict(n=n, parse_fail_rate=rate(c("parse_fail"), n),
                    tool_ok=rate(c("tool_ok"), n),
                    params_all_ok=rate(c("params_all_ok"), n),
                    params_all_ok_strict=rate(c("params_all_ok_strict"), n),
                    full_call_ok=rate(c("full_call_ok"), n),
                    exact_call_ok=rate(c("exact_call_ok"), n),
                    noparam_events=c("noparam"))
    ready_keys = [k for k in keys if rec[k]["ready"]]
    return dict(
        theta_fire=th_fire, risk=args.risk,
        chosen_theta_fire={str(k): v for k, v in chosen.items()},
        theta_sweep_val=[dict(theta=th, **a) for th, a in sweep],
        ready_stats=dict(val=val_st, test=test_st),
        val=dict(theta=th_fire,
                 **agg_fire(list(replay_fire_head(val_rows, pv,
                                                  th_fire).values()))),
        test=agg_fire(list(rec.values())),
        scored=dict(n_param_instances=n_par,
                    param_acc_loose=rate(n_lo, n_par),
                    param_acc_strict=rate(n_st, n_par), **block(keys)),
        on_ready=block(ready_keys),
        samples=samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--ctool-run", required=True,
                    help="因果分类头 run 目录(给触发点:温度/θ/logits_test.pt)")
    ap.add_argument("--cgen-run", required=True, help="调用生成 run 目录")
    ap.add_argument("--data", required=True,
                    help="数据目录 <data_out>(直接含 test.jsonl)")
    ap.add_argument("--risk", type=float, default=0.05)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--bs", type=int, default=8, help="生成批大小")
    ap.add_argument("--max-new-tokens", type=int, default=MAX_GEN_TOK)
    ap.add_argument("--limit", type=int, default=0, help="截前 N 触发事件(冒烟)")
    ap.add_argument("--readonly-env", default=None,
                    choices=list(readonly_map.READONLY_ENVS),
                    help="只读工具+弃权类模式(默认关);打开后真值折叠、"
                         "触发条件加\"argmax 不是弃权类\",且只给真值为只读"
                         "工具的触发事件判分")
    ap.add_argument("--params", default=None,
                    help="参数区间标签目录(默认 <data>/params);--self-fire 用它算 ready")
    ap.add_argument("--self-fire", action="store_true",
                    help="自主开火评测:θ_fire 在 val 上扫、test 冻结一次,"
                         "触发点由 cgen 自己的开火头定,不用 ctool 的 θ。"
                         "只加 self_fire 块,旧字段一个不动")
    ap.add_argument("--fire-bs", type=int, default=0,
                    help="开火打分的批大小(0=沿用 --bs)")
    ap.add_argument("--overlong", default="left",
                    choices=["left", "skip", "drop-event"],
                    help="触发事件全文/提示超长的三种处理(spec 16.2);"
                         "默认 left(行为与加这个开关之前逐字节不变)。"
                         "只描述主路径,--self-fire 不受影响")
    args = ap.parse_args()

    ctool, cgen = Path(args.ctool_run), Path(args.cgen_run)
    data = Path(args.data)
    params = Path(args.params) if args.params else data / "params"
    dev = args.device

    if args.self_fire and not args.readonly_env:
        raise SystemExit(
            "--self-fire 必须与 --readonly-env 同时传:开火真值 ready 的定义"
            "依赖该环境的只读真值表。")

    rep_cls = json.loads((ctool / "REPLAY_REPORT.json").read_text())
    T = rep_cls["temperature"]
    theta = rep_cls["chosen_theta"].get(str(args.risk))
    if theta is None:
        if not args.self_fire:
            raise SystemExit(f"分类头报告里没有 risk={args.risk} 的 θ:"
                             f"{rep_cls['chosen_theta']}")
        print(f"[self-fire] 分类头报告里没有 risk={args.risk} 的 θ"
              f"({rep_cls['chosen_theta']}),旧模式整块跳过,只出 self_fire。",
              flush=True)
    old_mode = theta is not None

    # 1) 触发点:过滤逻辑与 eval_tool 逐行一致,保证与 logits_test.pt 同序
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    meta = json.loads((cgen / "best" / "meta.json").read_text())

    # 格保险丝:本脚本只吃 cgen 格的产物。cparam 的 run 只训过"写参数段",
    # 喂进来生成的串没有工具名,判分会全塌而且一路跑通不报错。
    if meta.get("param_only"):
        raise SystemExit(
            f"{cgen / 'best' / 'meta.json'} 带 \"param_only\": true——"
            "这是 cparam 格的产物。参数生成的 run 用 eval_causal_param.py 评。")

    # 数据三方对拍:cgen 训练时的 data、--data 实参、ctool 训练时的 data 必须是
    # 同一个目录。两档底座并行时,p1b06 的 ctool 配 p1b17 的 cgen 这类交叉喂法
    # 会静默通过其余全部保险丝。
    ctool_meta = json.loads((ctool / "best" / "meta.json").read_text())
    trio = {"--data 实参": str(data),
            "cgen meta.data": meta.get("data"),
            "ctool meta.data": ctool_meta.get("data")}
    canon = {k: (str(Path(v).resolve()) if v else None) for k, v in trio.items()}
    if len(set(canon.values())) != 1:
        raise SystemExit("数据三方对拍不一致,硬停:\n" + "\n".join(
            f"  {k} = {trio[k]!r} -> {canon[k]!r}" for k in trio))

    # 防串味双向保险丝:ctool 的 label_map 有弃权哨兵、cgen 的 meta 有
    # readonly_env 键(缺失=旧模式),两处都必须与 --readonly-env 同时成立
    has_sentinel = readonly_map.NON_READONLY in label2id
    meta_ro = meta.get("readonly_env")
    if has_sentinel != bool(args.readonly_env) or \
            (meta_ro is not None) != bool(args.readonly_env):
        raise SystemExit(
            f"readonly 保险丝不匹配:{ctool / 'best' / 'label_map.json'} "
            f"{'含' if has_sentinel else '不含'}弃权哨兵 "
            f"{readonly_map.NON_READONLY!r};"
            f"{cgen / 'best' / 'meta.json'} 的 readonly_env 键 "
            f"{'= ' + repr(meta_ro) if meta_ro is not None else '缺失(=旧模式)'};"
            f"而 --readonly-env "
            f"{'传了 ' + str(args.readonly_env) if args.readonly_env else '没传'}。"
            "三者必须同时成立或同时不成立——readonly 模式训的 run 只能带 "
            "--readonly-env 评,旧口径 run 只能不带。")
    if args.readonly_env and isinstance(meta_ro, str) \
            and meta_ro != args.readonly_env:
        raise SystemExit(
            f"readonly 保险丝:cgen run 是按 {meta_ro!r} 训的,"
            f"却要用 {args.readonly_env!r} 的真值表评——环境串味,硬停。")
    ro_set = nro_id = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    raw_rows = load_rows(data / "test.jsonl")
    if ro_set is not None:
        readonly_map.audit([r["label"] for r in raw_rows],
                           readonly_map.load_table(args.readonly_env),
                           "eval_causal_call test")
        for r in raw_rows:
            r["label"] = readonly_map.collapse(r["label"], ro_set)
    rows = [r for r in raw_rows if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    fired, keys, n_fired, n_ro_excluded = {}, [], 0, 0
    overlong_counts = dict(n_left_truncated=0, n_skipped_rows=0,
                          n_dropped_events=0, n_excluded_by_ctool=0)
    ev_row_idx = defaultdict(list)
    for i, r in enumerate(rows):
        ev_row_idx[r["event"]].append(i)
    if old_mode:
        logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
        assert len(rows) == logits.shape[0], (len(rows), logits.shape)

        # ctool 剔除的行不许当触发点候选(spec 16.2 衔接段):提前读
        # excluded_idx,只在剩下的行里挑触发点——零 logits 过 softmax 是均匀
        # 分布,只在 θ<=1/n_labels 时才会被 θ 天然挡住,不能靠这个当保险。
        # 一个事件的候选行全部被剔时没有触发点,不判分,计 n_excluded_by_ctool。
        ctool_lmeta = ctool / "logits_test.meta.json"
        excluded_rows = set()
        if ctool_lmeta.exists():
            excluded_rows = set(
                json.loads(ctool_lmeta.read_text()).get("excluded_idx", []))
        overlong_counts["n_excluded_by_ctool"] = sum(
            1 for idxs in ev_row_idx.values()
            if all(i in excluded_rows for i in idxs))
        cand_idx = [i for i in range(len(rows)) if i not in excluded_rows]
        cand_rows = [rows[i] for i in cand_idx]
        cand_probs = torch.softmax(logits[cand_idx] / T, -1)
        fired = replay_fire(cand_rows, cand_probs, theta, nro_id)

        keys = [k for k in dict.fromkeys(r["event"] for r in cand_rows)
                if fired[k]["fired"]]
        n_fired = len(keys)
        # readonly 模式:触发了但真值非只读的事件不判分(不进任何分母),单独计数
        if ro_set is not None:
            keep = [k for k in keys
                    if fired[k]["label"] != readonly_map.NON_READONLY]
            n_ro_excluded = len(keys) - len(keep)
            keys = keep

    # 2) 生成:CALL_SEP 从训练侧 meta.json 读(不硬编码)
    sep = meta.get("call_sep", FALLBACK_SEP)
    max_len = meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(cgen / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                    # 保思考尾巴
    tok.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(
        cgen / "best",
        dtype=torch.bfloat16 if str(dev).startswith("cuda") else torch.float32
    ).to(dev).eval()

    if old_mode:
        # --overlong 筛选(分词器加载之后;readonly 排除之后、--limit 之前,
        # spec 16.2 三步顺序写死)。ctool 剔除已经在挑触发点那一步处理过
        # (上面的 overlong_counts["n_excluded_by_ctool"]),这里传空集合,
        # 只做提示长度筛选——keys 里的事件都已经保证至少有一个未被 ctool
        # 剔除的候选行,select_keys 的剔除分支在这里必然不再命中。
        keys_rowmap = {k: ev_row_idx[k] for k in keys}
        prompt_len = {k: len(tok(fired[k]["row"]["text"] + sep,
                                add_special_tokens=False,
                                truncation=False)["input_ids"])
                     for k in keys}
        n_full = {}
        if args.overlong == "drop-event":
            key_set = set(keys)
            full_texts = share_data.event_full_texts(
                [r for r in rows if r["event"] in key_set])
            n_full = {k: share_data.n_full_tokens(tok, full_texts[k])
                     for k in keys}
        keys, length_counts = share_data.select_keys(
            args.overlong, keys_rowmap, n_full, prompt_len, set(),
            max_len, args.max_new_tokens)
        assert length_counts["n_excluded_by_ctool"] == 0, (
            "keys 里的事件理应都至少有一个未被 ctool 剔除的候选行")
        overlong_counts.update(n_left_truncated=length_counts["n_left_truncated"],
                              n_skipped_rows=length_counts["n_skipped_rows"],
                              n_dropped_events=length_counts["n_dropped_events"])
        if args.limit:
            keys = keys[:args.limit]

    prompts = [fired[k]["row"]["text"] + sep for k in keys]
    gens = generate(model, tok, prompts, dev, args.bs, max_len,
                    args.max_new_tokens) if prompts else []

    # 3) 判分
    per_ev, samples, n_par, n_lo, n_st = score_points(
        keys, {k: fired[k]["row"] for k in keys}, gens, args.env)

    n = len(per_ev)
    cnt = lambda f: sum(1 for r in per_ev.values() if r[f])   # noqa: E731

    by_tool = defaultdict(lambda: dict(n=0, tool_ok=0, params_all_ok=0,
                                       full_call_ok=0))
    for r in per_ev.values():
        b = by_tool[r["label"]]
        b["n"] += 1
        b["tool_ok"] += r["tool_ok"]
        b["params_all_ok"] += r["params_all_ok"]
        b["full_call_ok"] += r["full_call_ok"]
    top = sorted(by_tool.items(), key=lambda kv: -kv[1]["n"])[:TOPK_TOOLS]

    n_ev = len({r["event"] for r in rows})
    out = dict(
        env=args.env, ctool_run=str(ctool), cgen_run=str(cgen),
        risk=args.risk, theta=theta, temperature=T, call_sep=sep,
        max_new_tokens=args.max_new_tokens, limit=args.limit,
        n_events_test=n_ev, overlong_mode=args.overlong,
        n_left_truncated=overlong_counts["n_left_truncated"],
        n_skipped_rows=overlong_counts["n_skipped_rows"],
        n_dropped_events=overlong_counts["n_dropped_events"],
        n_excluded_by_ctool=overlong_counts["n_excluded_by_ctool"])
    if old_mode:
        out.update(
            n_events_fired=n_fired, n_events_scored=n,
            parse_fail=cnt("parse_fail"),
            parse_fail_rate=rate(cnt("parse_fail"), n),
            tool_ok=rate(cnt("tool_ok"), n),
            params_all_ok=rate(cnt("params_all_ok"), n),
            params_all_ok_strict=rate(cnt("params_all_ok_strict"), n),
            full_call_ok=rate(cnt("full_call_ok"), n),
            exact_call_ok=rate(cnt("exact_call_ok"), n),
            noparam_events=cnt("noparam"), noparam_rate=rate(cnt("noparam"), n),
            n_param_instances=n_par,
            param_acc_loose=rate(n_lo, n_par),
            param_acc_strict=rate(n_st, n_par),
            by_tool={k: dict(n=v["n"], tool_ok=rate(v["tool_ok"], v["n"]),
                             params_all_ok=rate(v["params_all_ok"], v["n"]),
                             full_call_ok=rate(v["full_call_ok"], v["n"]))
                     for k, v in top},
            samples=samples)
    if ro_set is not None:
        out["readonly_env"] = args.readonly_env
        out["readonly_excluded"] = n_ro_excluded

    # ---------------- 自主开火(--self-fire):θ_fire 在 val 上扫,test 冻结一次
    sf = None
    if args.self_fire:
        sf = self_fire_block(args, cgen, data, params, meta, model, tok, sep,
                             max_len, dev, ro_set)
        out["self_fire"] = sf
    (cgen / "CALLGEN_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    md = [f"# 触发时刻调用生成评测 — {args.env}",
          f"- overlong_mode={out['overlong_mode']}"
          f"(n_left_truncated={out['n_left_truncated']}, "
          f"n_skipped_rows={out['n_skipped_rows']}, "
          f"n_dropped_events={out['n_dropped_events']}, "
          f"n_excluded_by_ctool={out['n_excluded_by_ctool']})"]
    if not old_mode:
        md += [f"- 分类头 {ctool.name} 在 risk={args.risk} 上无解 θ,"
               "旧模式整块跳过;本文件只有自主开火那一节。"]
    md += ([
          f"- 分类头 {ctool.name} / 生成头 {cgen.name};风险≤{args.risk} → "
          f"θ={theta}(温度 T={T})",
          f"- test 事件 {n_ev},触发 {n_fired},本次计入 {n}"
          + (f"(--limit {args.limit})" if args.limit else ""),
          f"- 拼串分隔符 call_sep={sep!r}(读自生成头 meta.json);"
          f"greedy max_new_tokens={args.max_new_tokens},遇换行或 eos 停",
          "",
          "| 指标 | 值 |", "|---|---|",
          f"| 解析失败率 | {out['parse_fail_rate']} |",
          f"| 工具名正确率 | {out['tool_ok']} |",
          f"| 参数全对率(宽松) | {out['params_all_ok']} |",
          f"| 参数全对率(严格) | {out['params_all_ok_strict']} |",
          f"| 完整调用正确率 | {out['full_call_ok']} |",
          f"| 整串逐字命中(对照训练侧 val_exact_call) | {out['exact_call_ok']} |",
          f"| 无参事件占比 | {out['noparam_rate']}({out['noparam_events']}/{n}) |",
          f"| 参数实例数 | {n_par} |",
          f"| 参数级正确率(宽松/严格) | {out['param_acc_loose']} / "
          f"{out['param_acc_strict']} |",
          "",
          f"## 分工具明细(按事件数前 {TOPK_TOOLS})",
          "| 工具 | 事件数 | 工具名正确 | 参数全对 | 完整调用正确 |",
          "|---|---|---|---|---|"] if old_mode else [])
    if old_mode:
        for k, v in top:
            md.append(f"| {k} | {v['n']} | {rate(v['tool_ok'], v['n'])} | "
                      f"{rate(v['params_all_ok'], v['n'])} | "
                      f"{rate(v['full_call_ok'], v['n'])} |")
    md += ["", "## 判分口径",
           "- 参数逐个比:宽松=归一化(strip 后去引号)后值相等;严格=原串逐字相等;"
           "键按 union 比,多参/少参/名错各记一个错实例。",
           "- 参数全对率里,真值无参的事件恒真(单独列出占比);"
           "完整调用正确 = 工具名对 且 参数全对(宽松)。",
           "- 触发点与 ctool 的回放完全同源,所以本表可与同模型 mext 格的"
           "EXTRACT_REPORT 并排读:两边都是触发那一刻能不能组出整条调用。"]
    if ro_set is not None and old_mode:
        md += ["", f"## 只读模式(--readonly-env {args.readonly_env})",
               f"- 弃权类 {readonly_map.NON_READONLY}(标签 id {nro_id});"
               "触发条件加\"argmax 不是弃权类\",真值标签已折叠",
               f"- 触发但真值非只读、因而不判分的事件:{n_ro_excluded}"
               f"(readonly_excluded);本表各列的分母是余下的 {n} 个"
               "真值只读触发事件"]
    if sf is not None and sf["test"] is None:
        md += ["", f"## 自主开火(--self-fire,风险≤{args.risk})",
               f"- val 上 20 档 θ 都压不到风险≤{args.risk}"
               f"(chosen={sf['chosen_theta_fire']}),test 没考,"
               "只留 self_fire.theta_sweep_val 那张扫描表。"]
    elif sf is not None:
        a = sf["test"]
        md += ["", f"## 自主开火(--self-fire,风险≤{args.risk})",
               f"- θ_fire 在 val 上扫出 {sf['theta_fire']}"
               f"(val 覆盖率 {sf['val']['coverage']} / "
               f"开火正确率 {sf['val']['fire_acc']});test 冻结一次",
               "- 开火真值 ready = 工具只读 且 该边界上参数全部 found;"
               "错误开火 = 开火了但真值 not-ready",
               f"- test 事件 {a['n']},开火 {a['n_fired']},"
               f"覆盖率 {a['coverage']},开火正确率 {a['fire_acc']},"
               f"错误开火率 {a['wrong_fire_rate']}",
               "",
               "| 指标(分母=开火点) | 全部开火点 | 其中真值 ready 的 |",
               "|---|---|---|",
               f"| 事件数 | {sf['scored']['n']} | {sf['on_ready']['n']} |",
               f"| 解析失败率 | {sf['scored']['parse_fail_rate']} | "
               f"{sf['on_ready']['parse_fail_rate']} |",
               f"| 工具名正确率 | {sf['scored']['tool_ok']} | "
               f"{sf['on_ready']['tool_ok']} |",
               f"| 参数全对率(宽松) | {sf['scored']['params_all_ok']} | "
               f"{sf['on_ready']['params_all_ok']} |",
               f"| 完整调用正确率 | {sf['scored']['full_call_ok']} | "
               f"{sf['on_ready']['full_call_ok']} |",
               "",
               "- 左列不剔除任何开火点:错误开火拿真实(未折叠)标签判分,"
               "所以它天然算错——这一列才是\"让探针自己决定何时发射\"的真成绩。",
               "- 右列只看真值 ready 的开火点,用来和旧模式那张表对照读。"]
    (cgen / "CALLGEN_REPORT.md").write_text("\n".join(md) + "\n")
    heartbeat.emit(n, n, "item", status="done")
    if old_mode:
        print(json.dumps({k: out[k] for k in
                          ("n_events_scored", "parse_fail_rate", "tool_ok",
                           "params_all_ok", "full_call_ok")},
                         ensure_ascii=False, indent=1))
    if sf is not None and sf["test"] is not None:
        print(json.dumps(dict(theta_fire=sf["theta_fire"], **sf["test"],
                              full_call_ok=sf["scored"]["full_call_ok"]),
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
