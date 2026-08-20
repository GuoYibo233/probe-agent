"""触发时刻参数生成评测(新流水线 cparam 格):在 ctool 的触发点上,把工具名连同
左括号一起喂给 cparam 模型,让它只写参数,再重组成整条调用判分。

与 eval_causal_call.py(cgen 格)对照读:两边的触发点定义完全同源
(【照抄 eval_extract.py 的 replay_fire()】),判分口径也逐字照抄——差别只在
"工具名从哪来":那边由生成模型自己写,这边由输入直接给定。

本脚本一次跑**两个口径**,同一批触发点各生成一遍:
- gt_tool   prompt 里的工具名 = 真值 label,量的是模型纯粹的填参数能力
- pred_tool prompt 里的工具名 = ctool 在该触发行的 argmax 预测(经 label_map
            反查名字),量的是系统乙(ctool + cparam)的真实表现
两块的差 = ctool 选错工具漏下来的损失。矩阵(summarize_matrix.py)只取
pred_tool 块——那才是系统乙的真数字。

- 触发点: --ctool-run 的 REPLAY_REPORT.json 给温度 T 与 chosen_theta[--risk],
  配 logits_test.pt 在 test 堆上回放,取每事件首次过 θ 的样本行
- 生成: prompt = 触发样本 text + CALL_SEP + <工具名> + "(",CALL_SEP 从
  --cparam-run/best/meta.json 的 `call_sep` 字段读(与训练侧拼串口径同源,
  不硬编码);greedy、max_new_tokens=96、eos 停,再截到首个 \\n,最后 .strip()
  (与训练侧 val_exact_params 口径一致)。生成时 padding_side 临时切 left
- 判分: 先重组完整调用串 = <工具名> + "(" + 生成串,再走与 cgen 完全相同的
  parse_call / match_params:
    tool_ok           解析出的工具名 == label(gt_tool 块如实记,恒真;
                      pred_tool 块等价于"预测名 == 真值名")
    参数逐个          宽松 = 归一化后值相等;严格 = 未归一化原串相等;
                      键不匹配(多参/少参/名错)= 该参数错
    params_all_ok     全部参数宽松对(真值无参的事件恒真,并单独成列)
    full_call_ok      tool_ok 且 params_all_ok
    exact_call_ok     重组串 == label_call
- 产物: <cparam-run>/PARAM_REPORT.{json,md}

只读模式 `--readonly-env {appworld,bfcl}`(默认关,关=旧口径):照抄 cgen 评测的
语义——真值标签在装载处过 readonly_map.collapse()、触发条件加"argmax 不是弃权类";
只给"触发了且真值为只读工具"的事件判分,触发但真值非只读的事件不进任何分母,
单独计进 readonly_excluded。两块口径共用同一批触发点,所以这条对两块同时生效。
双向保险丝查两处:ctool run 的 label_map.json 有没有弃权哨兵、cparam run 的
meta.json 有没有 readonly_env 键(缺失=旧模式)。

用法:
  cprobe-env/bin/python pipeline/eval/eval_causal_param.py --env appworld \\
    --ctool-run pipeline/runs/c2_q35_ctool --cparam-run pipeline/runs/c2_q35_cparam \\
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat                                         # noqa: E402

MAX_GEN_TOK = 96            # 【照抄 train_causal_param.py 的 MAX_GEN_TOK】
FALLBACK_SEP = "\n[CALL] "  # meta.json 没写 call_sep 时的兜底(应当写了)
TOPK_TOOLS = 10             # 分工具明细表行数


def load_rows(path):
    return [json.loads(l) for l in open(path)]


def replay_fire(rows, probs, theta, nro_id=None):
    """【照抄 eval_causal_call.py 的 replay_fire()】首次过 θ 的样本行。

    比 cgen 那份多记一个 `pred`(该行的 argmax 类 id)——pred_tool 口径要靠它
    反查工具名。nro_id=None 是旧口径;给了弃权类 id(readonly 模式)时触发条件
    收窄成 "conf>=θ 且 argmax != nro_id",与 eval_tool.replay 完全同源。
    """
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None, pred=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta and (nro_id is None or pred != nro_id):
                rec.update(fired=True, ok=(pred == r["y"]),
                           sent_idx=r["sent_idx"], row=r, pred=pred)
                break
        out[k] = rec
    return out


# ---------------------------------------------------------------- 解析

def norm(v):
    """【照抄】annotate 侧的值归一化:strip() 后 strip("\\"'")。"""
    return v.strip().strip("\"'")


def split_named_raw(argstr):
    """【照抄 eval_causal_call.split_named_raw】split_args_named 的切法逐字照抄,
    只把末尾的归一化留给调用方:返回 [(key, 未归一化原串)]。与
    rules.split_args_named 的一致性在 parse_call() 里每次断言,防止两份切法漂移。"""
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
    """【照抄 eval_causal_call.parse_call】-> (tool_name, [(key, raw_value)])
    或 (None, []) 表示 parse_fail。"""
    # alfworld 必须显式分支:落回 BFCL_CALL 的 `(\w+)\(` 会把串里第一个
    # "词(" 认成工具名,静默把 tool_ok 打塌。ALF_CALL 只认 rules.ALF_TEMPLATES
    # 那 13 个官方动作名,与 annotate 侧同源。
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
    """【照抄 eval_causal_call.match_params】truth=[{"key","value"}](值已归一化),
    gen_raw=[(key, 未归一化原串)]。

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
def generate(model, tok, prompts, dev, bs, max_len, max_new, tag=""):
    """greedy 生成:遇 \\n 或 eos 停,返回 .strip() 后的参数串(不含工具名与左括号)。"""
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
        print(f"[{tag}] generated {min(i + bs, len(prompts))}/{len(prompts)}",
              flush=True)
        heartbeat.emit(min(i + bs, len(prompts)), len(prompts), "item")
    tok.padding_side, model.config.use_cache = prev_side, prev_cache
    return out


def rate(num, den):
    return round(num / den, 4) if den else None


# ------------------------------------------------------------ 判分

def score_points(keys, rowof, given, gens, env, n_samples=20):
    """在触发点上判分。keys 与 gens 同序,rowof[k] 给该点的真值行,
    given[k] 给喂进 prompt 的工具名。

    【判分口径逐字保留 eval_causal_call.score_points】工具名 / 宽松·严格参数 /
    整调用三档一个不动,唯一的差别是判分前先把工具名与左括号重组回去。
    """
    per_ev, samples = {}, []
    n_par = n_lo = n_st = 0
    for k, g in zip(keys, gens):
        row = rowof[k]
        truth = row.get("args_named") or []
        full = given[k] + "(" + g          # 重组完整调用串
        tool, raw = parse_call(full, env)
        n, lo, st = match_params(truth, raw)
        n_par += n
        n_lo += lo
        n_st += st
        noparam = not truth
        rec = dict(
            event=k, label=row["label"], label_call=row.get("label_call"),
            given_tool=given[k], gen_params=g, gen_call=full,
            parse_fail=tool is None,
            tool_ok=(tool == row["label"]),
            given_tool_ok=(given[k] == row["label"]),
            params_all_ok=(True if noparam else (n > 0 and lo == n)),
            params_all_ok_strict=(True if noparam else (n > 0 and st == n)),
            noparam=noparam,
            exact_call_ok=(full == row.get("label_call")))
        rec["full_call_ok"] = rec["tool_ok"] and rec["params_all_ok"]
        per_ev[k] = rec
        if len(samples) < n_samples:
            samples.append(dict(event=k, truth=row.get("label_call"),
                                gen=full, full_call_ok=rec["full_call_ok"]))
    return per_ev, samples, n_par, n_lo, n_st


def block(per_ev, keys, theta, n_par, n_lo, n_st, samples):
    """一个口径的全部数字。theta / n_events_scored / params_all_ok /
    full_call_ok 四项是 summarize_matrix 读 pred_tool 块要的字段,别改名。"""
    n = len(keys)
    c = lambda f: sum(1 for k in keys if per_ev[k][f])   # noqa: E731
    by_tool = defaultdict(lambda: dict(n=0, tool_ok=0, params_all_ok=0,
                                       full_call_ok=0))
    for k in keys:
        r = per_ev[k]
        b = by_tool[r["label"]]
        b["n"] += 1
        b["tool_ok"] += r["tool_ok"]
        b["params_all_ok"] += r["params_all_ok"]
        b["full_call_ok"] += r["full_call_ok"]
    top = sorted(by_tool.items(), key=lambda kv: -kv[1]["n"])[:TOPK_TOOLS]
    return dict(
        theta=theta, n_events_scored=n,
        parse_fail=c("parse_fail"), parse_fail_rate=rate(c("parse_fail"), n),
        tool_ok=rate(c("tool_ok"), n),
        given_tool_ok=rate(c("given_tool_ok"), n),
        params_all_ok=rate(c("params_all_ok"), n),
        params_all_ok_strict=rate(c("params_all_ok_strict"), n),
        full_call_ok=rate(c("full_call_ok"), n),
        exact_call_ok=rate(c("exact_call_ok"), n),
        noparam_events=c("noparam"), noparam_rate=rate(c("noparam"), n),
        n_param_instances=n_par,
        param_acc_loose=rate(n_lo, n_par),
        param_acc_strict=rate(n_st, n_par),
        by_tool={k: dict(n=v["n"], tool_ok=rate(v["tool_ok"], v["n"]),
                         params_all_ok=rate(v["params_all_ok"], v["n"]),
                         full_call_ok=rate(v["full_call_ok"], v["n"]))
                 for k, v in top},
        samples=samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True,
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--ctool-run", required=True,
                    help="因果分类头 run 目录(给触发点:温度/θ/logits_test.pt/label_map)")
    ap.add_argument("--cparam-run", required=True,
                    help="参数生成 run 目录(报告也写这里)")
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
    args = ap.parse_args()

    ctool, cparam = Path(args.ctool_run), Path(args.cparam_run)
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
    id2label = {v: k for k, v in label2id.items()}
    meta = json.loads((cparam / "best" / "meta.json").read_text())

    # 格保险丝:本脚本只吃 cparam 格的产物。cgen 的 meta 里没有 param_only,
    # 拿 cgen run 来评会静默多喂一遍工具名(prompt 里一次、生成里再一次)。
    if not meta.get("param_only"):
        raise SystemExit(
            f"{cparam / 'best' / 'meta.json'} 里没有 \"param_only\": true——"
            "这不是 cparam 格的产物。整条调用生成的 run 用 eval_causal_call.py 评。")

    # 数据三方对拍:cparam 训练时的 data、--data 实参、ctool 训练时的 data 必须是
    # 同一个目录。两档底座并行时,p1b06 的 ctool 配 p1b17 的 cparam 这类交叉喂法
    # 会静默通过其余全部保险丝。
    ctool_meta = json.loads((ctool / "best" / "meta.json").read_text())
    trio = {"--data 实参": str(data),
            "cparam meta.data": meta.get("data"),
            "ctool meta.data": ctool_meta.get("data")}
    canon = {k: (str(Path(v).resolve()) if v else None) for k, v in trio.items()}
    if len(set(canon.values())) != 1:
        raise SystemExit("数据三方对拍不一致,硬停:\n" + "\n".join(
            f"  {k} = {trio[k]!r} -> {canon[k]!r}" for k in trio))

    # 防串味双向保险丝:ctool 的 label_map 有弃权哨兵、cparam 的 meta 有
    # readonly_env 键(缺失=旧模式),两处都必须与 --readonly-env 同时成立
    has_sentinel = readonly_map.NON_READONLY in label2id
    meta_ro = meta.get("readonly_env")
    if has_sentinel != bool(args.readonly_env) or \
            (meta_ro is not None) != bool(args.readonly_env):
        raise SystemExit(
            f"readonly 保险丝不匹配:{ctool / 'best' / 'label_map.json'} "
            f"{'含' if has_sentinel else '不含'}弃权哨兵 "
            f"{readonly_map.NON_READONLY!r};"
            f"{cparam / 'best' / 'meta.json'} 的 readonly_env 键 "
            f"{'= ' + repr(meta_ro) if meta_ro is not None else '缺失(=旧模式)'};"
            f"而 --readonly-env "
            f"{'传了 ' + str(args.readonly_env) if args.readonly_env else '没传'}。"
            "三者必须同时成立或同时不成立——readonly 模式训的 run 只能带 "
            "--readonly-env 评,旧口径 run 只能不带。")
    if args.readonly_env and isinstance(meta_ro, str) \
            and meta_ro != args.readonly_env:
        raise SystemExit(
            f"readonly 保险丝:cparam run 是按 {meta_ro!r} 训的,"
            f"却要用 {args.readonly_env!r} 的真值表评——环境串味,硬停。")
    ro_set = nro_id = None
    if args.readonly_env:
        ro_set = readonly_map.load_readonly_set(args.readonly_env)
        nro_id = label2id[readonly_map.NON_READONLY]

    raw_rows = load_rows(data / "test.jsonl")
    if ro_set is not None:
        readonly_map.audit([r["label"] for r in raw_rows],
                           readonly_map.load_table(args.readonly_env),
                           "eval_causal_param test")
        for r in raw_rows:
            r["label"] = readonly_map.collapse(r["label"], ro_set)
    rows = [r for r in raw_rows if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]

    logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)
    fired = replay_fire(rows, torch.softmax(logits / T, -1), theta, nro_id)

    keys = [k for k in dict.fromkeys(r["event"] for r in rows)
            if fired[k]["fired"]]
    n_fired = len(keys)
    # readonly 模式:触发了但真值非只读的事件不判分(不进任何分母),单独计数。
    # 两块口径共用同一批 keys,所以这一条对 gt_tool / pred_tool 同时生效。
    n_ro_excluded = 0
    if ro_set is not None:
        keep = [k for k in keys
                if fired[k]["label"] != readonly_map.NON_READONLY]
        n_ro_excluded = len(keys) - len(keep)
        keys = keep
    if args.limit:
        keys = keys[:args.limit]

    # 2) 生成:CALL_SEP 从训练侧 meta.json 读(不硬编码),两个口径各生成一遍
    sep = meta.get("call_sep", FALLBACK_SEP)
    max_len = meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(cparam / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"                    # 保思考尾巴
    tok.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(
        cparam / "best",
        dtype=torch.bfloat16 if str(dev).startswith("cuda") else torch.float32
    ).to(dev).eval()

    rowof = {k: fired[k]["row"] for k in keys}
    gt_given = {k: rowof[k]["label"] for k in keys}
    pred_given = {k: id2label[fired[k]["pred"]] for k in keys}

    res = {}
    for tag, given in (("gt_tool", gt_given), ("pred_tool", pred_given)):
        prompts = [rowof[k]["text"] + sep + given[k] + "(" for k in keys]
        gens = (generate(model, tok, prompts, dev, args.bs, max_len,
                         args.max_new_tokens, tag) if prompts else [])
        per_ev, samples, n_par, n_lo, n_st = score_points(
            keys, rowof, given, gens, args.env)
        res[tag] = block(per_ev, keys, theta, n_par, n_lo, n_st, samples)

    n = len(keys)
    n_ev = len({r["event"] for r in rows})
    out = dict(
        env=args.env, ctool_run=str(ctool), cparam_run=str(cparam),
        risk=args.risk, theta=theta, temperature=T, call_sep=sep,
        max_new_tokens=args.max_new_tokens, limit=args.limit,
        n_events_test=n_ev, n_events_fired=n_fired, n_events_scored=n,
        gt_tool=res["gt_tool"], pred_tool=res["pred_tool"])
    if ro_set is not None:
        out["readonly_env"] = args.readonly_env
        out["readonly_excluded"] = n_ro_excluded
    (cparam / "PARAM_REPORT.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))

    g, p = res["gt_tool"], res["pred_tool"]
    md = [f"# 触发时刻参数生成评测 — {args.env}",
          f"- 分类头 {ctool.name} / 参数头 {cparam.name};风险≤{args.risk} → "
          f"θ={theta}(温度 T={T})",
          f"- test 事件 {n_ev},触发 {n_fired},本次计入 {n}"
          + (f"(--limit {args.limit})" if args.limit else ""),
          f"- 拼串分隔符 call_sep={sep!r}(读自参数头 meta.json);"
          f"prompt = text + call_sep + 工具名 + \"(\";"
          f"greedy max_new_tokens={args.max_new_tokens},遇换行或 eos 停",
          "",
          "| 指标 | gt_tool(喂真值工具名) | pred_tool(喂分类头预测) |",
          "|---|---|---|",
          f"| 判分事件数 | {g['n_events_scored']} | {p['n_events_scored']} |",
          f"| 解析失败率(本表结构上恒 0,见判分口径) | {g['parse_fail_rate']} | "
          f"{p['parse_fail_rate']} |",
          f"| 工具名正确率 | {g['tool_ok']} | {p['tool_ok']} |",
          f"| 参数全对率(宽松) | {g['params_all_ok']} | {p['params_all_ok']} |",
          f"| 参数全对率(严格) | {g['params_all_ok_strict']} | "
          f"{p['params_all_ok_strict']} |",
          f"| 完整调用正确率 | {g['full_call_ok']} | {p['full_call_ok']} |",
          f"| 整串逐字命中 | {g['exact_call_ok']} | {p['exact_call_ok']} |",
          f"| 无参事件占比 | {g['noparam_rate']}({g['noparam_events']}/{n}) | "
          f"同左 |",
          f"| 参数实例数 | {g['n_param_instances']} | {p['n_param_instances']} |",
          f"| 参数级正确率(宽松/严格) | {g['param_acc_loose']} / "
          f"{g['param_acc_strict']} | {p['param_acc_loose']} / "
          f"{p['param_acc_strict']} |",
          "",
          f"## 分工具明细(pred_tool 口径,按事件数前 {TOPK_TOOLS})",
          "| 工具 | 事件数 | 工具名正确 | 参数全对 | 完整调用正确 |",
          "|---|---|---|---|---|"]
    for k, v in p["by_tool"].items():
        md.append(f"| {k} | {v['n']} | {v['tool_ok']} | "
                  f"{v['params_all_ok']} | {v['full_call_ok']} |")
    md += ["", "## 判分口径",
           "- 判分前先把工具名与左括号重组回生成串前面,再走与 cgen 评测"
           "逐字相同的 parse_call / match_params。",
           "- 参数逐个比:宽松=归一化(strip 后去引号)后值相等;严格=原串逐字相等;"
           "键按 union 比,多参/少参/名错各记一个错实例。",
           "- 解析失败率在本表结构上恒为 0:工具名是脚本自己拼在串首的,"
           "parse_call 必命中。这一行与 cgen 报告的解析失败率不可比,"
           "也不反映生成质量。",
           "- 参数全对率里,真值无参的事件恒真(单独列出占比);"
           "完整调用正确 = 工具名对 且 参数全对(宽松)。gt_tool 块里无参事件"
           "连完整调用正确也恒真(工具名是喂进去的),这份白拿分比 cgen 格大"
           "(那边工具名要自己生成);横比时矩阵只吃 pred_tool 的 full_call_ok。",
           "- gt_tool 块的工具名由真值给定,所以工具名正确率恒为 1(如实记);"
           "pred_tool 块的工具名来自分类头 argmax,两块的差就是分类头选错工具"
           "漏下来的损失。矩阵只取 pred_tool——那是系统乙的真实口径。",
           "- 触发点与 ctool 的回放完全同源,所以本表可与同模型 cgen 格的 "
           "CALLGEN_REPORT 并排读:两边都是触发那一刻能不能组出整条调用。"]
    if ro_set is not None:
        md += ["", f"## 只读模式(--readonly-env {args.readonly_env})",
               f"- 弃权类 {readonly_map.NON_READONLY}(标签 id {nro_id});"
               "触发条件加\"argmax 不是弃权类\",真值标签已折叠",
               f"- 触发但真值非只读、因而不判分的事件:{n_ro_excluded}"
               f"(readonly_excluded);两块的分母都是余下的 {n} 个"
               "真值只读触发事件"]
    (cparam / "PARAM_REPORT.md").write_text("\n".join(md) + "\n")
    heartbeat.emit(n, n, "item", status="done")
    print(json.dumps(
        dict(n_events_scored=n,
             gt_tool={k: g[k] for k in ("tool_ok", "params_all_ok",
                                        "full_call_ok")},
             pred_tool={k: p[k] for k in ("tool_ok", "params_all_ok",
                                          "full_call_ok")}),
        ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
