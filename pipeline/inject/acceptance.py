"""甲丙两问的算力账:小模型的草稿,大模型认多少。规格:
plans/2026-08-01-splice-impl-spec.md §D4

这个脚本不改动实验,只是拿已经跑完的 switch_only 臂当"大模型自己写整条调用"的
参照,回答两件事:

- 甲(工具名接受率):探针预测的工具名 pred_label,和大模型自己写出来的调用的
  工具名一样吗?一样才谈得上"先猜工具名去预取"。
- 丙(参数产线的草稿被接受多长):把 cgen 写的整条 gen_call 和大模型写的
  call_out 都用 gpt-oss 分词器编码,取最长公共前缀。前缀有多长,投机解码里
  这条草稿就能省多少步——这是省算力账的唯一硬口径,字符级的"像不像"不算数。

丙的默认路走分词器对比,不需要服务;给了 --base-url 才跑备用精确路:把
"prompt + 草稿"整串喂给 vLLM 的 completions,echo=True + logprobs + max_tokens=0,
逐 token 看它是不是 top-1,第一个不是的就是拒绝点。两路都跑就报不一致率。

用法(默认路,纯 CPU):
  cprobe-env/bin/python pipeline/inject/acceptance.py \\
      --run-dir pipeline/inject/runs/aw_gptoss_splice
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parse_call                                            # noqa: E402
from build_form_table import load_table, skeleton            # noqa: E402
from extract_completed import rebuild_sides                  # noqa: E402

DEFAULT_TOKENIZER = ("/net/tokyo100-10g/data/str01_01/y-guo/models/"
                     "gpt-oss-120b")
# 规格 §命名钉死;备用精确路要照 run 段那样重拼 prompt 才对得上
SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"


def pct(xs, q):
    """分位数,最近秩法(样本量小的时候不做插值,免得报出没出现过的数)。"""
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def lcp(a, b):
    """最长公共前缀长度。"""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def load_switch_only(d, tag):
    """per_event<tag>.jsonl 里 switch_only 臂的记录,按 event 索引。"""
    p = d / f"per_event{tag}.jsonl"
    if not p.exists():
        raise SystemExit(f"没有 {p};甲丙两问都要 switch_only 臂的打分记录")
    out = {}
    for line in open(p):
        r = json.loads(line)
        if r.get("arm") == "switch_only":
            out[r["event"]] = r
    if not out:
        raise SystemExit(f"{p} 里没有 switch_only 臂——先把这条臂跑出来再验收")
    return out


def part_a(plan, sw):
    """甲:pred_label == switch_only 的 tool_out。

    分母是"探针给了工具名"的事件。大模型这一步压根没写出调用(tool_out 为空)
    的算不接受、不算弃权——真跑起来预取照样白花了,单列 n_no_tool 让人看得见,
    另给一条只在"写了调用"的事件上算的 accept_rate_of_called 做对照。
    """
    n = hit = no_tool = 0
    miss = Counter()
    for ev, r in sw.items():
        pred = (plan.get(ev) or {}).get("pred_label")
        if pred is None:
            continue
        n += 1
        tool = r.get("tool_out")
        if tool is None:
            no_tool += 1
        elif pred == tool:
            hit += 1
        else:
            miss[f"{pred} -> {tool}"] += 1
    called = n - no_tool
    return dict(n=n, n_hit=hit, n_no_tool=no_tool,
                accept_rate=round(hit / n, 4) if n else None,
                accept_rate_of_called=(round(hit / called, 4)
                                       if called else None),
                top_miss=miss.most_common(10))


def part_c_tok(plan, sw, tok):
    """丙:cgen 的 gen_call vs switch_only 的 call_out,分词器级最长公共前缀。"""
    rows = []
    skipped = Counter()
    for ev, r in sw.items():
        p = plan.get(ev)
        draft = (p or {}).get("gen_call")
        ref = r.get("call_out")
        if not draft:
            skipped["no_gen_call"] += 1
            continue
        if not ref:
            skipped["no_call_out"] += 1
            continue
        di = tok.encode(draft, add_special_tokens=False)
        ri = tok.encode(ref, add_special_tokens=False)
        if not di:
            skipped["empty_draft"] += 1
            continue
        k = lcp(di, ri)
        rows.append(dict(event=ev, draft=draft, ref=ref,
                         draft_tok=len(di), ref_tok=len(ri),
                         accept_len=k, accept_frac=round(k / len(di), 4),
                         exact=(di == ri)))
    return rows, dict(skipped)


def summarize_c(rows):
    lens = [r["accept_len"] for r in rows]
    fracs = [r["accept_frac"] for r in rows]
    n_exact = sum(1 for r in rows if r["exact"])
    return dict(
        n=len(rows),
        n_exact=n_exact,
        exact_rate=round(n_exact / len(rows), 4) if rows else None,
        accept_len=dict(median=pct(lens, 0.5), p10=pct(lens, 0.10),
                        p90=pct(lens, 0.90),
                        mean=(round(sum(lens) / len(lens), 3)
                              if lens else None)),
        accept_frac=dict(median=pct(fracs, 0.5), p10=pct(fracs, 0.10),
                         p90=pct(fracs, 0.90),
                         mean=(round(sum(fracs) / len(fracs), 4)
                               if fracs else None)),
        draft_tok=dict(median=pct([r["draft_tok"] for r in rows], 0.5)),
        hist_accept_len=dict(sorted(Counter(lens).items())))


# ------------------------------------------------------- 备用精确路(要服务)

def post_completions(base_url, payload, timeout):
    import urllib.request
    # 与 replay_inject.post_completions 同约定:--base-url 以 /v1 结尾
    req = urllib.request.Request(
        base_url.rstrip("/") + "/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def anchor_of(plan, raw, ev, tok, table):
    """重拼 switch_only 那一步的 prompt,一直拼到裸调用起头的位置。

    草稿要和参照从同一个位置起跑,接受长度才有意义:所以锚点 = run 段的
    prompt(前缀 + analysis 开栏 + 思考头 + SWITCH),再接上大模型自己写的、
    裸调用之前的那截壳子(围栏开栏加 print( 之类)。
    """
    import rebuild as R
    p = plan[ev]
    o = raw.get(ev, {}).get("switch_only")
    if o is None or not o.get("text"):
        return None
    meta, gens, envs, _ = R.load_traj(Path(p["traj_path"]))
    msgs = R.build_messages(meta, gens, envs, p["step"])
    prefix = R.build_prefix(tok, msgs, pin_date=R.COLLECT_DATE)
    head = (gens[p["step"]].get("reasoning") or "").strip()[:p["cut"]]
    pred_label = p.get("pred_label")
    skel = skeleton(pred_label, table) if pred_label else ""
    _, final = rebuild_sides("switch_only", o["text"], skel)
    call, end = parse_call.complete_call(final)
    if call is None:
        return None
    return prefix + R.ANALYSIS_OPEN + head + SWITCH + final[:end - len(call)]


def part_c_echo(rows, plan, raw, tok, table, a):
    """把草稿接在锚点后面喂回去,逐 token 看它是不是 top-1。"""
    out, fail = [], Counter()
    for r in rows:
        anc = anchor_of(plan, raw, r["event"], tok, table)
        if anc is None:
            fail["no_anchor"] += 1
            continue
        try:
            resp = post_completions(a.base_url, dict(
                model=a.model, prompt=anc + r["draft"], max_tokens=0,
                temperature=0.0, echo=True, logprobs=1,
                skip_special_tokens=False), a.timeout)
        except Exception as e:
            fail[f"http_{type(e).__name__}"] += 1
            continue
        lp = resp["choices"][0].get("logprobs") or {}
        offs = lp.get("text_offset") or []
        toks = lp.get("tokens") or []
        tlp = lp.get("token_logprobs") or []
        tops = lp.get("top_logprobs") or []
        # 草稿的第一个 token = 第一个起点落在锚点之后的 token。用 text_offset
        # 定位,不用"锚点单独编码的长度"——两者在边界上会差一个 token
        idx = [i for i, o in enumerate(offs) if o >= len(anc)]
        if not idx:
            fail["no_draft_span"] += 1
            continue
        k = 0
        for i in idx:
            top = tops[i] if i < len(tops) else None
            if not top or tlp[i] is None:
                break
            if toks[i] != max(top, key=top.get):   # 不是 top-1 = 拒绝点
                break
            k += 1
        out.append(dict(event=r["event"], accept_len_echo=k,
                        accept_len_lcp=r["accept_len"],
                        agree=(k == r["accept_len"])))
    n = len(out)
    n_dis = sum(1 for x in out if not x["agree"])
    ks = [x["accept_len_echo"] for x in out]
    return dict(n=n, n_fail=dict(fail), n_disagree=n_dis,
                disagree_rate=round(n_dis / n, 4) if n else None,
                accept_len_echo=dict(median=pct(ks, 0.5), p10=pct(ks, 0.10),
                                     p90=pct(ks, 0.90)),
                rows=out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--plan-file", default="plan.jsonl")
    ap.add_argument("--tag", default="", help="per_event<tag>/raw<tag> 的后缀")
    ap.add_argument("--tokenizer", default=DEFAULT_TOKENIZER,
                    help="大模型分词器(CPU 加载,只用来编码,不建模型)")
    ap.add_argument("--form-table", default=None)
    ap.add_argument("--base-url", default=None,
                    help="给了才跑备用精确路(echo+logprobs);不给标 skipped")
    ap.add_argument("--model", default="gpt-oss-120b")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--limit", type=int, default=0,
                    help="备用精确路只跑前 N 条(它一条一次请求,很慢)")
    ap.add_argument("--out", default="ACCEPT_REPORT.json")
    a = ap.parse_args()

    from transformers import AutoTokenizer
    d = Path(a.run_dir)
    plan = {}
    for line in open(d / a.plan_file):
        p = json.loads(line)
        plan[p["event"]] = p
    sw = load_switch_only(d, a.tag)
    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    table = load_table(a.form_table)

    rep = dict(run_dir=str(d), plan_file=a.plan_file, tag=a.tag,
               tokenizer=a.tokenizer, n_plan=len(plan), n_switch_only=len(sw))
    rep["jia_tool_accept"] = part_a(plan, sw)
    rows, skipped = part_c_tok(plan, sw, tok)
    rep["bing_draft_accept"] = dict(skipped=skipped, **summarize_c(rows))

    if a.base_url:
        use = rows[:a.limit] if a.limit else rows
        raw = {}
        for line in open(d / f"raw{a.tag}.jsonl"):
            o = json.loads(line)
            raw.setdefault(o["event"], {})[o["arm"]] = o
        rep["bing_echo"] = part_c_echo(use, plan, raw, tok, table, a)
    else:
        rep["bing_echo"] = dict(status="skipped",
                                reason="没给 --base-url,备用精确路不跑")

    (d / a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    show = {k: v for k, v in rep.items() if k != "bing_echo"}
    show["bing_draft_accept"] = {
        k: v for k, v in show["bing_draft_accept"].items()
        if k != "hist_accept_len"}
    print(json.dumps(show, ensure_ascii=False, indent=1))
    print(f"-> {d / a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
