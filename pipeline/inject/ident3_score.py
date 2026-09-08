"""ident3 打分(纯 CPU,stdlib):三臂(chat / noprobe / nofill)x 5 题 x 10 遍,
逐 token 比对,出 IDENT3_REPORT.{json,md}。计划:plans/archive/2026-08-18-ident3.md §4。

输入目录结构(ident3_job.sh 落的):
  <root>/chat/rep<r>/appworld_gptoss/appworld_<tid>.jsonl   (run_appworld --api chat)
  <root>/noprobe/rep<r>/live_<tid>.jsonl                    (live_appworld --no-probe)
  <root>/nofill/rep<r>/live_<tid>.jsonl                     (live_appworld --fire-nth-cut N --nofill)

每次跑抽成同一形态:每步的生成 token id 列表(chat 取 out_token_ids,live 取
gen_ids)、每步 prompt token 数、成败、步数、总生成 token。比对口径:
- 两次跑"逐 token 同"= 每步 id 序列全等且步数相同;首个分叉 = 第一个 id 不等的
  步 + 步内首个不等的位;分叉前累计相同 token 数 = shared_tok。
- 尾部的 <|return|>(200002)在比对前剥掉:chat 与 completions 对停止 token 是否
  计入 token_ids 的口径可能不同,这层差不算分叉(报告里单列各臂末 id 的分布)。
- 配对分同臂对(chat-chat / noprobe-noprobe / nofill-nofill)与跨臂对
  (chat-noprobe / chat-nofill / noprobe-nofill);同臂对与跨臂对的分叉分布一样
  = 臂间没有可言的差别。
- 只报事实,不解读。

用法:
  python3 pipeline/inject/ident3_score.py --root /net/.../pipeline/inject/runs/ident3_v1
"""

import argparse
import glob
import hashlib
import itertools
import json
import re
import statistics as S
from collections import Counter, defaultdict
from pathlib import Path

ARMS = ("chat", "noprobe", "nofill")
RETURN_ID = 200002          # <|return|>
SUCCESS_RE = re.compile(r"'success': (True|False)")


def _success(ev):
    if isinstance(ev, dict):
        v = ev.get("success")
        return None if v is None else bool(v)
    if isinstance(ev, str):
        m = SUCCESS_RE.search(ev)
        return None if not m else (m.group(1) == "True")
    return None


def ids_sha(ids):
    """与 live_appworld.ids_sha 同一算法(逗号串 sha1);chat 存整段 prompt id,
    活跑存 sha,两边算同一个 sha 就是逐 id 比。"""
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()


def load_run(path, arm):
    recs, bad_lines = [], 0
    with open(path) as f:
        for line in f:
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                bad_lines += 1            # 进程被杀留下的半行,数着,不炸
    gens = [r for r in recs if r.get("type") == "gen"]
    fin = next((r for r in recs if r.get("type") == "final"), None)
    specs = [r for r in recs if r.get("type") == "spec"]
    resumes = [r for r in recs if r.get("type") == "resume"]
    steps_ids, prompt_tok, prompt_sha, gen_tok = [], [], [], []
    for g in gens:
        if arm == "chat":
            ids = g.get("out_token_ids")
            pids = g.get("prompt_token_ids")
            prompt_tok.append(len(pids) if pids is not None else g["usage"]["in"])
            prompt_sha.append(ids_sha(pids) if pids is not None else None)
            gen_tok.append(g["usage"]["out"])
        else:
            ids = g.get("gen_ids")
            prompt_tok.append(g.get("prefix_tok"))
            prompt_sha.append(g.get("prefix_sha"))
            gen_tok.append(g["usage"]["gen_tok"])
        steps_ids.append(list(ids) if ids is not None else None)
    abort = (fin.get("abort") if fin else "NO_FINAL")
    return dict(
        path=str(path), arm=arm, bad_lines=bad_lines,
        steps=fin["steps"] if fin else None,
        completed=fin.get("completed") if fin else None,
        abort=abort,
        success=_success(fin.get("eval")) if fin else None,
        # 任一臂只要 abort 非空(live 的 task_error:*、chat 的 stepN:Err:*、
        # 上下文撞顶、没有 final)都不进成败与配对——两臂口径对齐,不让一次
        # 服务端故障顶着"短轨迹"进配对
        excluded=bool(abort),
        n_gen=len(gens), ids=steps_ids, prompt_tok=prompt_tok,
        prompt_sha=prompt_sha,
        gen_tok=gen_tok, gen_tok_total=sum(gen_tok),
        n_inject=sum(g.get("n_inject", 0) for g in gens),
        discard_tok=sum((g.get("discard") or {}).get("tokens", 0) for g in gens),
        inconsistent=sum(1 for g in gens if g.get("text_ids_consistent") is False),
        specs=specs, resumes=resumes,
        last_ids=[s[-1] for s in steps_ids if s])


def discover(root):
    """-> {tid: {arm: {rep: run}}}"""
    runs = defaultdict(lambda: defaultdict(dict))
    for arm in ARMS:
        for rep_dir in sorted(glob.glob(str(root / arm / "rep*"))):
            rep = int(Path(rep_dir).name[3:])
            pat = (f"{rep_dir}/appworld_gptoss/appworld_*.jsonl" if arm == "chat"
                   else f"{rep_dir}/live_*.jsonl")
            for p in sorted(glob.glob(pat)):
                name = Path(p).stem
                tid = name[len("appworld_"):] if arm == "chat" else name[len("live_"):]
                runs[tid][arm][rep] = load_run(p, arm)
    return runs


def strip_tail(ids):
    ids = list(ids)
    while ids and ids[-1] == RETURN_ID:
        ids.pop()
    return ids


def compare(a, b):
    """两次跑逐 token 比。返回 dict(identical, div_step, div_tok, shared_tok)。
    div_step=None 表示全同(含步数相同)。步数不同但公共步全同:div_step=公共步数,
    div_tok=0。某步 id 缺失(旧格式)按不可比记 None。"""
    shared = 0
    n = min(len(a["ids"]), len(b["ids"]))
    for s in range(n):
        x, y = a["ids"][s], b["ids"][s]
        if x is None or y is None:
            return dict(identical=None, div_step=None, div_tok=None, shared_tok=None,
                        comparable=False)
        x, y = strip_tail(x), strip_tail(y)
        m = 0
        while m < min(len(x), len(y)) and x[m] == y[m]:
            m += 1
        if m < len(x) or m < len(y):
            return dict(identical=False, div_step=s, div_tok=m,
                        shared_tok=shared + m, comparable=True)
        shared += len(x)
    if len(a["ids"]) != len(b["ids"]):
        return dict(identical=False, div_step=n, div_tok=0, shared_tok=shared,
                    comparable=True)
    return dict(identical=True, div_step=None, div_tok=None, shared_tok=shared,
                comparable=True)


def q(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    xs = sorted(xs)
    return dict(n=len(xs), min=xs[0], med=S.median(xs), max=xs[-1],
                mean=round(S.mean(xs), 2))


def cell(x):
    """markdown 表格单元格:去掉会破表的竖线与换行,截长。"""
    return str(x).replace("|", "/").replace("\n", " ")[:80]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    root = Path(a.root)
    runs = discover(root)
    rep = dict(root=str(root), tasks={}, pairs={}, pair_list=[], nofill={},
               prompt_check={}, last_ids={}, excluded=[])
    md = [f"# IDENT3 report — {root.name}", ""]

    # ---- 1. 每题每臂 ----
    md += ["## 1. 每题每臂(10 遍)", "",
           "gen_tok 两列:billed = 服务端记的全部生成 token(nofill 含中断丢弃的溢出与"
           "重发续写);kept = billed − 丢弃溢出(chat/noprobe 两者相同)。"
           "excluded = abort 非空(task_error / stepN 错误 / 上下文撞顶 / 无 final),"
           "不进成败与配对。", "",
           "| task | arm | n | excluded | success | steps min/med/max | "
           "gen_tok billed med | gen_tok kept med | distinct traj | inconsistent |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for tid in sorted(runs):
        rep["tasks"][tid] = {}
        for arm in ARMS:
            rs = list(runs[tid].get(arm, {}).values())
            if not rs:
                continue
            ok = [r for r in rs if not r["excluded"]]
            for r in rs:
                if r["excluded"]:
                    rep["excluded"].append(dict(tid=tid, arm=arm, path=r["path"],
                                                abort=str(r["abort"])[:200]))
            succ = sum(1 for r in ok if r["success"])
            with_ids = [r for r in ok if all(s is not None for s in r["ids"])]
            distinct = len({json.dumps([strip_tail(s) for s in r["ids"]])
                            for r in with_ids})
            row = dict(n=len(rs), n_ok=len(ok), success=succ,
                       steps=q([r["steps"] for r in ok]),
                       gen_tok_billed=q([r["gen_tok_total"] for r in ok]),
                       gen_tok_kept=q([r["gen_tok_total"] - r["discard_tok"]
                                       for r in ok]),
                       distinct_traj=distinct, n_with_ids=len(with_ids),
                       excluded=len(rs) - len(ok),
                       inconsistent=sum(r["inconsistent"] for r in rs),
                       bad_lines=sum(r["bad_lines"] for r in rs),
                       abort=dict(Counter(str(r["abort"])[:60] for r in rs
                                          if r["abort"])))
            rep["tasks"][tid][arm] = row
            st = row["steps"] or {}
            md.append(f"| {tid} | {arm} | {len(rs)} | {row['excluded']} | "
                      f"{succ}/{len(ok)} | "
                      f"{st.get('min')}/{st.get('med')}/{st.get('max')} | "
                      f"{(row['gen_tok_billed'] or {}).get('med')} | "
                      f"{(row['gen_tok_kept'] or {}).get('med')} | "
                      f"{distinct}/{len(with_ids)} | {row['inconsistent']} |")
    md.append("")
    if rep["excluded"]:
        md += ["被排除的跑:", ""] + [
            f"- {e['tid']} {e['arm']}: {cell(e['abort'])}" for e in rep["excluded"]
        ] + [""]

    # ---- 2. 配对逐 token 比 ----
    pair_stats = defaultdict(list)
    for tid in sorted(runs):
        allr = [(arm, r, run) for arm in ARMS
                for r, run in sorted(runs[tid].get(arm, {}).items())
                if not run["excluded"]]
        for (a1, r1, x), (a2, r2, y) in itertools.combinations(allr, 2):
            kind = f"{a1}-{a2}" if ARMS.index(a1) <= ARMS.index(a2) else f"{a2}-{a1}"
            c = compare(x, y)
            c.update(tid=tid, a=f"{a1}:r{r1}", b=f"{a2}:r{r2}", kind=kind)
            pair_stats[kind].append(c)
            rep["pair_list"].append(c)
    md += ["## 2. 两两配对逐 token 比(同题、去掉 excluded 的跑)", "",
           "| pair kind | n pairs | identical | comparable | div step 0 | "
           "div_step med | div_tok med | shared_tok med | shared_tok min |",
           "|---|---|---|---|---|---|---|---|---|"]
    for kind in sorted(pair_stats):
        cs = pair_stats[kind]
        comp = [c for c in cs if c["comparable"]]
        div = [c for c in comp if not c["identical"]]
        row = dict(n=len(cs), comparable=len(comp),
                   identical=sum(1 for c in comp if c["identical"]),
                   div_step0=sum(1 for c in div if c["div_step"] == 0),
                   div_step=q([c["div_step"] for c in div]),
                   div_tok=q([c["div_tok"] for c in div]),
                   shared_tok=q([c["shared_tok"] for c in comp]),
                   div_step_hist=dict(Counter(c["div_step"] for c in div)))
        rep["pairs"][kind] = row
        md.append(f"| {kind} | {row['n']} | {row['identical']} | {row['comparable']} | "
                  f"{row['div_step0']} | {(row['div_step'] or {}).get('med')} | "
                  f"{(row['div_tok'] or {}).get('med')} | "
                  f"{(row['shared_tok'] or {}).get('med')} | "
                  f"{(row['shared_tok'] or {}).get('min')} |")
    md.append("")
    md += ["同臂对 = chat-chat / noprobe-noprobe / nofill-nofill;其余为跨臂对。"
           "div_tok = 分叉步内首个不等的 token 位。", ""]
    # 按题的配对细表
    md += ["### 2b. 按题:每种配对的 identical / n", ""]
    kinds = sorted(pair_stats)
    md += ["| task | " + " | ".join(kinds) + " |", "|---|" + "---|" * len(kinds)]
    for tid in sorted(runs):
        cells = []
        for kind in kinds:
            cs = [c for c in pair_stats[kind] if c["tid"] == tid and c["comparable"]]
            cells.append(f"{sum(1 for c in cs if c['identical'])}/{len(cs)}")
        md.append(f"| {tid} | " + " | ".join(cells) + " |")
    md.append("")

    # ---- 3. 跨臂 prompt id 核对(分叉前的步 + 分叉步):按 sha 逐 id 比 ----
    n_eq = n_tot = n_len_eq = 0
    mism = []
    for kind, cs in pair_stats.items():
        a1, a2 = kind.split("-")
        if a1 == a2:
            continue
        for c in cs:
            if not c["comparable"]:
                continue
            x = runs[c["tid"]][c["a"].split(":")[0]][int(c["a"].split(":r")[1])]
            y = runs[c["tid"]][c["b"].split(":")[0]][int(c["b"].split(":r")[1])]
            upto = c["div_step"] if c["div_step"] is not None else min(
                len(x["prompt_sha"]), len(y["prompt_sha"]))
            for s in range(min(upto + 1, len(x["prompt_sha"]), len(y["prompt_sha"]))):
                # 分叉步本身的 prompt 也应相同(prompt 是分叉之前的历史)
                if x["prompt_sha"][s] is None or y["prompt_sha"][s] is None:
                    continue
                n_tot += 1
                n_len_eq += (x["prompt_tok"][s] == y["prompt_tok"][s])
                if x["prompt_sha"][s] == y["prompt_sha"][s]:
                    n_eq += 1
                elif len(mism) < 20:
                    mism.append(dict(tid=c["tid"], a=c["a"], b=c["b"], step=s,
                                     len_a=x["prompt_tok"][s], len_b=y["prompt_tok"][s]))
    rep["prompt_check"] = dict(n=n_tot, sha_equal=n_eq, len_equal=n_len_eq,
                               mismatches=mism)
    md += ["## 3. 跨臂 prompt id 核对(分叉前的步 + 分叉步;sha1 逐 id 比)", "",
           f"- sha 相等 {n_eq} / {n_tot};长度相等 {n_len_eq} / {n_tot}"
           f"(应为全等;不等就是管线问题,前 20 条见 JSON prompt_check.mismatches)", ""]

    # ---- 4. 各臂每步末 id ----
    for arm in ARMS:
        cnt = Counter()
        for tid in runs:
            for run in runs[tid].get(arm, {}).values():
                cnt.update(run["last_ids"])
        rep["last_ids"][arm] = {str(k): v for k, v in cnt.most_common(5)}
    md += ["## 4. 各臂每步生成 id 序列的末 id(top-5)", "",
           json.dumps(rep["last_ids"]), ""]

    # ---- 5. nofill 专属 ----
    specs, resumes, n_steps, n_fired = [], [], 0, 0
    for tid in runs:
        for run in runs[tid].get("nofill", {}).values():
            specs += run["specs"]
            resumes += run["resumes"]
            n_steps += run["n_gen"]
            n_fired += run["n_inject"]
    if specs or n_steps:
        idn = [r["identical"] for r in resumes]
        row = dict(n_steps=n_steps, n_fired=n_fired,
                   fire_rate=round(n_fired / n_steps, 3) if n_steps else None,
                   head_ends_ws=dict(Counter(str(s.get("head_ends_ws")) for s in specs)),
                   head_tok=q([s["head_tok"] for s in specs]),
                   head_chars=q([s.get("head_chars") for s in specs]),
                   overflow_tok=q([r["overflow_tok"] for r in resumes]),
                   n_resume=len(resumes),
                   identical=sum(idn),
                   identical_rate=round(sum(idn) / len(idn), 3) if idn else None,
                   match_len=q([r["match_len"] for r in resumes]),
                   match_len_zero=sum(1 for r in resumes if r["match_len"] == 0),
                   match_ratio=q([round(r["match_len"] / r["overflow_tok"], 3)
                                  for r in resumes if r["overflow_tok"]]),
                   finish=dict(Counter(str(r.get("finish")) for r in resumes)))
        rep["nofill"] = row
        md += ["## 5. nofill:中断-重发账", "",
               f"- 步数 {n_steps},开火 {n_fired}(fire_rate {row['fire_rate']})",
               f"- head 以空白结尾 {row['head_ends_ws']};head_tok {row['head_tok']};"
               f"head_chars {row['head_chars']}",
               f"- 重发续写 vs 被丢弃的溢出:n={len(resumes)},逐位全同 "
               f"{row['identical']}({row['identical_rate']}),match_len {row['match_len']},"
               f"match_len=0 的 {row['match_len_zero']},overflow_tok {row['overflow_tok']},"
               f"match_ratio {row['match_ratio']};重发续写 finish {row['finish']}", ""]

    (root / "IDENT3_REPORT.json").write_text(json.dumps(rep, ensure_ascii=False,
                                                        indent=1, default=str))
    (root / "IDENT3_REPORT.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\n-> {root}/IDENT3_REPORT.{{md,json}}")


if __name__ == "__main__":
    main()
