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

MAX_GEN_TOK = 96            # 【照抄 train_causal_callgen.py 的 MAX_GEN_TOK】
FALLBACK_SEP = "\n[CALL] "  # meta.json 没写 call_sep 时的兜底(应当写了)
TOPK_TOOLS = 10             # 分工具明细表行数


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta):
    """【照抄 eval_extract.py 的 replay_fire()】首次过 θ 的样本行。"""
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
            if conf >= theta:
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
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


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
    args = ap.parse_args()

    ctool, cgen = Path(args.ctool_run), Path(args.cgen_run)
    data = Path(args.data)
    dev = args.device

    rep_cls = json.loads((ctool / "REPLAY_REPORT.json").read_text())
    T = rep_cls["temperature"]
    theta = rep_cls["chosen_theta"].get(str(args.risk))
    if theta is None:
        raise SystemExit(f"分类头报告里没有 risk={args.risk} 的 θ:"
                         f"{rep_cls['chosen_theta']}")

    # 1) 触发点:过滤逻辑与 eval_tool 逐行一致,保证与 logits_test.pt 同序
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    rows = [r for r in load_rows(data / "test.jsonl")
            if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)
    fired = replay_fire(rows, torch.softmax(logits / T, -1), theta)

    keys = [k for k in dict.fromkeys(r["event"] for r in rows)
            if fired[k]["fired"]]
    n_fired = len(keys)
    if args.limit:
        keys = keys[:args.limit]

    # 2) 生成:CALL_SEP 从训练侧 meta.json 读(不硬编码)
    meta = json.loads((cgen / "best" / "meta.json").read_text())
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

    prompts = [fired[k]["row"]["text"] + sep for k in keys]
    gens = generate(model, tok, prompts, dev, args.bs, max_len,
                    args.max_new_tokens) if prompts else []

    # 3) 判分
    per_ev, samples = {}, []
    n_par = n_lo = n_st = 0
    for k, g in zip(keys, gens):
        row = fired[k]["row"]
        truth = row.get("args_named") or []
        tool, raw = parse_call(g, args.env)
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
        if len(samples) < 20:
            samples.append(dict(event=k, truth=row.get("label_call"),
                                gen=g, full_call_ok=rec["full_call_ok"]))

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
        n_events_test=n_ev, n_events_fired=n_fired, n_events_scored=n,
        parse_fail=cnt("parse_fail"), parse_fail_rate=rate(cnt("parse_fail"), n),
        tool_ok=rate(cnt("tool_ok"), n),
        params_all_ok=rate(cnt("params_all_ok"), n),
        params_all_ok_strict=rate(cnt("params_all_ok_strict"), n),
        full_call_ok=rate(cnt("full_call_ok"), n),
        exact_call_ok=rate(cnt("exact_call_ok"), n),
        noparam_events=cnt("noparam"), noparam_rate=rate(cnt("noparam"), n),
        n_param_instances=n_par,
        param_acc_loose=rate(n_lo, n_par), param_acc_strict=rate(n_st, n_par),
        by_tool={k: dict(n=v["n"], tool_ok=rate(v["tool_ok"], v["n"]),
                         params_all_ok=rate(v["params_all_ok"], v["n"]),
                         full_call_ok=rate(v["full_call_ok"], v["n"]))
                 for k, v in top},
        samples=samples)
    (cgen / "CALLGEN_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    md = [f"# 触发时刻调用生成评测 — {args.env}",
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
          "|---|---|---|---|---|"]
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
    (cgen / "CALLGEN_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps({k: out[k] for k in
                      ("n_events_scored", "parse_fail_rate", "tool_ok",
                       "params_all_ok", "full_call_ok")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
