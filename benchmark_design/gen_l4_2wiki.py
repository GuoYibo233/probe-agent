#!/usr/bin/env python
"""L4 (假相似) 生成器 —— 2WikiMultihopQA,规范 L3L4_and_metrics_draft.md §2.3 第 1/2 类。

两个编辑族:

  polarity_flip     (§2.3 第 1 类 极性翻转)
      种子 "Which film came out first, A or B?" (答 A) → "…came out later, A or B?"
      证据文档一字不改,答案确定性反转。旧解 = 复述记忆里的答案 = 精确答错。
      规范 §2.4 判为 T3(静默错误:全程无矛盾信号,只有终局判分见分晓)。

  confusable_entity (§2.3 第 2 类 易混实体替换)
      种子两跳 (X, r1, M) → (M, r2, A)。把 X 换成同 relation、不同 subject 且
      与 X 同名系(共享姓氏/名字 token)的 X',链变成 (X', r1, M') → (M', r2, A')。
      记忆里 X 的文档对 X' 全部失效。规范 §2.4 判为 T1(hop1 检索文档里根本没这个名字)。

两族都做"旧解回放必败"的编程验证(§2.1 第 2 条):
  - polarity_flip:用 evidences 三元组里的日期,按问句的比较方向词求解,
    先验证该规则能复现种子的 gold answer(复现不了就不收,说明表面规则不可信),
    再验证翻转后 gold 变成另一个实体,且与旧答案规范化后不相等。
  - confusable_entity:在全局三元组库里沿新链求解,要求新答案存在、唯一、
    且与旧答案规范化后不相等。

表面相似度过滤(§2.1 第 1 条)本轮不做,见 --sim-filter 占位接口。

纯 CPU、无模型、无 API。固定随机种子,同参数重跑逐字节一致。
"""

import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_SEED = 20260729
SCRIPT_VERSION = "gen_l4_2wiki.py/2026-07-30"
HERE = Path(__file__).resolve().parent
DEFAULT_HF_HOME = "/net/tokyo100-10g/data/str01_01/y-guo/hf"
DATASET = "voidful/2WikiMultihopQA"


# --------------------------------------------------------------------------
# 文本工具
# --------------------------------------------------------------------------

def norm(s):
    """实体/答案的规范化:去重音、小写、压空白、去尾部标点。"""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .,;:!?\"'")
    return s


MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items())})


def parse_date(s):
    """把 2wiki 的日期字符串解析成 ((y, m, d), granularity)。解析不了返回 None。

    实测出现的形态:'1915' / 'December 25, 2019' / '31 May 2016' / '24 September 1982'
    """
    s = str(s).strip().strip(".")
    m = re.fullmatch(r"(\d{3,4})", s)
    if m:
        return (int(m.group(1)), 0, 0), 1
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return tuple(int(x) for x in m.groups()), 3
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{3,4})", s)
    if m and m.group(2).lower() in MONTHS:
        return (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))), 3
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{3,4})", s)
    if m and m.group(1).lower() in MONTHS:
        return (int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))), 3
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{3,4})", s)
    if m and m.group(1).lower() in MONTHS:
        return (int(m.group(2)), MONTHS[m.group(1).lower()], 0), 2
    return None


def date_cmp(a, b):
    """按两者共同的最粗粒度比较。相等或无法比较返回 None(歧义,不收)。"""
    pa, ga = a
    pb, gb = b
    g = min(ga, gb)
    ka, kb = pa[:g], pb[:g]
    if ka == kb:
        return None
    return -1 if ka < kb else 1


# --------------------------------------------------------------------------
# 极性翻转:比较方向词表
# --------------------------------------------------------------------------
# pick: 'min' = 选日期更早的那个实体;'max' = 选更晚的。
# flip: 翻转后替换成哪个词(自然、无歧义,且方向确定相反)。
# 顺序有意义:多词短语必须排在单词前面,匹配一次即停。
POLARITY_LEXICON = [
    # (正则片段, 该词对应的 pick, 翻转后的替换词, 适用 relation 白名单 None=全部)
    ("more recently", "max", "earlier", None),
    ("least recently", "min", "later", None),
    ("earlier", "min", "later", None),
    ("sooner", "min", "later", None),
    ("first", "min", "later", None),
    ("later", "max", "earlier", None),
    ("last", "max", "earlier", None),
    ("older", "min", "younger", {"date of birth"}),
    ("younger", "max", "older", {"date of birth"}),
]

DATE_RELATIONS = {"date of birth", "publication date", "date of death", "inception"}


def find_polarity(question, subjects):
    """在屏蔽掉实体名之后找唯一的比较方向词。返回 (词, pick, 翻转词, span) 或 None。"""
    masked = question
    for s in subjects:
        # 实体在问句里的表面可能大小写不同(实测 "The Pervert'S Guide" vs "…'s Guide"),
        # 用大小写不敏感的正则屏蔽,避免把实体名里的 first/last 当成方向词。
        masked = re.sub(re.escape(s), lambda m: " " * len(m.group(0)),
                        masked, flags=re.IGNORECASE)
    hits = []
    for word, pick, flip, rel_ok in POLARITY_LEXICON:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])",
                             masked, flags=re.IGNORECASE):
            hits.append((m.start(), m.end(), word, pick, flip, rel_ok))
    if len(hits) != 1:
        return None          # 零个或多个方向词 → 翻转不唯一,不收
    return hits[0]


# --------------------------------------------------------------------------
# 数据加载
# --------------------------------------------------------------------------

def load_rows(split, hf_home, limit=0, with_context=False):
    os.environ.setdefault("HF_HOME", hf_home)
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset(DATASET)[split]
    cols = ["_id", "type", "question", "answer", "evidences"]
    if with_context:
        cols.append("context")
    ds = ds.select_columns(cols)
    if limit:
        ds = ds.select(range(min(limit, len(ds))))
    return list(ds)


def context_blob(row):
    """种子任务的 gold 文档池压成一个规范化字符串,用来检查 X' 是否出现在记忆里。"""
    parts = []
    for doc in row.get("context") or []:
        if not doc:
            continue
        parts.append(str(doc[0]))
        if len(doc) > 1 and doc[1]:
            parts.extend(str(s) for s in doc[1])
    return norm(" ".join(parts))


def build_triple_store(rows):
    """(norm_subject, relation) → {norm_object: 表面形式}。用于沿链求解与唯一性检查。"""
    store = defaultdict(dict)
    surface = {}
    for r in rows:
        for ev in r["evidences"]:
            if len(ev) != 3:
                continue
            s, rel, o = ev
            store[(norm(s), rel)][norm(o)] = o
            surface.setdefault(norm(s), s)
            surface.setdefault(norm(o), o)
    return store, surface


def unique_object(store, subj, rel):
    """(subj, rel) 在库里唯一确定一个 object 才返回它,否则 None。"""
    d = store.get((norm(subj), rel))
    if not d or len(d) != 1:
        return None
    return next(iter(d.values()))


# --------------------------------------------------------------------------
# 族一:极性翻转
# --------------------------------------------------------------------------

def gen_polarity_flip(rows, args, stats):
    out = []
    for r in rows:
        if r["type"] != "comparison":
            continue
        ev = r["evidences"]
        if len(ev) != 2 or len(ev[0]) != 3 or len(ev[1]) != 3:
            stats["polarity_reject"]["malformed_evidence"] += 1
            continue
        if ev[0][1] != ev[1][1]:
            stats["polarity_reject"]["relation_mismatch"] += 1
            continue
        rel = ev[0][1]
        if rel not in DATE_RELATIONS:
            stats["polarity_reject"]["non_date_relation"] += 1
            continue
        subs = [ev[0][0], ev[1][0]]
        ans = r["answer"]
        if norm(ans) not in {norm(s) for s in subs}:
            stats["polarity_reject"]["answer_not_a_subject"] += 1
            continue
        d0, d1 = parse_date(ev[0][2]), parse_date(ev[1][2])
        if d0 is None or d1 is None:
            stats["polarity_reject"]["date_unparsable"] += 1
            continue
        c = date_cmp(d0, d1)
        if c is None:
            stats["polarity_reject"]["dates_tied_or_ambiguous"] += 1
            continue
        earlier = subs[0] if c < 0 else subs[1]
        later = subs[1] if c < 0 else subs[0]

        hit = find_polarity(r["question"], subs)
        if hit is None:
            stats["polarity_reject"]["no_unique_direction_word"] += 1
            continue
        st, en, word, pick, flip_word, rel_ok = hit
        if rel_ok is not None and rel not in rel_ok:
            stats["polarity_reject"]["direction_word_relation_mismatch"] += 1
            continue

        # —— 编程验证 A:表面方向词规则能复现 gold answer,否则规则不可信,不收
        predicted = earlier if pick == "min" else later
        if norm(predicted) != norm(ans):
            stats["polarity_reject"]["rule_disagrees_with_gold"] += 1
            continue

        # —— 编程验证 B:翻转后的 gold 必须是另一个实体
        new_answer = later if pick == "min" else earlier
        if norm(new_answer) == norm(ans):
            stats["polarity_reject"]["flip_did_not_change_answer"] += 1
            continue

        new_q = r["question"][:st] + _match_case(r["question"][st:en], flip_word) + r["question"][en:]

        out.append({
            "pair_id": f"2wiki/{args.split}/polarity_flip/{r['_id']}",
            "level": "L4",
            "domain": "2wiki",
            "edit_family": "polarity_flip",
            "split": args.split,
            "seed_qid": r["_id"],
            "seed_type": r["type"],
            "seed_question": r["question"],
            "seed_answer": ans,
            "l4_question": new_q,
            "l4_answer": new_answer,
            "edit": {"span": [st, en], "from": r["question"][st:en], "to": flip_word,
                     "direction_before": pick, "direction_after": "max" if pick == "min" else "min"},
            "evidences": ev,
            "evidence_identical_to_seed": True,   # 极性翻转不动任何证据文档
            "verification": {
                "rule_reproduces_gold": True,
                "old_answer_on_new_question_correct": False,   # 收录判据:旧解必败
                "old_answer": ans,
                "new_gold": new_answer,
                "dates": {subs[0]: ev[0][2], subs[1]: ev[1][2]},
                "relation": rel,
            },
            "tier": "T3",
            "tier_basis": "证据文档与检索结果与种子完全相同,回放过程零矛盾信号,"
                          "只有终局判分失败(规范 §2.4 T3)",
            "d_star": None,
            "sim_filter": {"applied": False, "tau": args.sim_filter,
                           "note": "待 bge-large 就位后补 §2.1 第 1 条过滤"},
            "generator": SCRIPT_VERSION,
            "rng_seed": args.seed,
        })
    return out


def _match_case(original, replacement):
    """保留原词的大小写形态(句首大写 / 全小写)。"""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# --------------------------------------------------------------------------
# 族二:易混实体替换
# --------------------------------------------------------------------------

STOP_TOKENS = {"the", "of", "and", "in", "a", "an", "film", "de", "la", "van", "von"}


def name_tokens(s):
    return [t for t in re.findall(r"[A-Za-z][A-Za-z'\-]+", norm(s))
            if len(t) >= 3 and t not in STOP_TOKENS]


def confusability(x, y):
    """同名系判据(§2.3 '同姓氏/同名系'):共享至少一个实词 token。
    末位 token 相同(姓氏一致)记为强易混,否则弱易混。返回 (bool, kind, shared)。"""
    tx, ty = name_tokens(x), name_tokens(y)
    if not tx or not ty:
        return False, None, []
    shared = sorted(set(tx) & set(ty))
    if not shared:
        return False, None, []
    if tx[-1] == ty[-1]:
        return True, "same_final_token", shared
    return True, "shared_token", shared


def gen_confusable_entity(rows, store, args, stats, rng):
    # subject 索引:relation → [subject 表面形式],用来找同 relation 不同 subject 的 X'
    by_rel = defaultdict(list)
    for (s_norm, rel), objs in store.items():
        if len(objs) == 1:
            by_rel[rel].append(s_norm)
    for rel in by_rel:
        by_rel[rel].sort()

    # 按名字 token 建倒排,免得对每个种子扫全表
    tok_index = {}
    for rel, subs in by_rel.items():
        idx = defaultdict(list)
        for s in subs:
            for t in name_tokens(s):
                idx[t].append(s)
        tok_index[rel] = idx

    surface = {}
    for r in rows:
        for ev in r["evidences"]:
            if len(ev) == 3:
                surface.setdefault(norm(ev[0]), ev[0])
                surface.setdefault(norm(ev[2]), ev[2])

    out = []
    for r in rows:
        if r["type"] not in ("compositional", "inference"):
            continue
        ev = r["evidences"]
        if len(ev) != 2 or any(len(e) != 3 for e in ev):
            stats["confusable_reject"]["not_two_hop"] += 1
            continue
        (x, r1, m), (m2, r2, a) = ev
        if norm(m) != norm(m2):
            stats["confusable_reject"]["chain_not_joined"] += 1
            continue
        if norm(a) != norm(r["answer"]):
            stats["confusable_reject"]["answer_not_chain_tail"] += 1
            continue
        # 种子问句里必须能定位到 X 的表面形式,否则无法做最小编辑
        span = _find_span(r["question"], x)
        if span is None:
            stats["confusable_reject"]["subject_not_in_question"] += 1
            continue

        cands = []
        seen = set()
        for t in name_tokens(x):
            for s_norm in tok_index.get(r1, {}).get(t, []):
                if s_norm == norm(x) or s_norm in seen:
                    continue
                seen.add(s_norm)
                ok, kind, shared = confusability(x, s_norm)
                if not ok:
                    continue
                cands.append((s_norm, kind, shared))
        if not cands:
            stats["confusable_reject"]["no_confusable_subject"] += 1
            continue
        # 强易混优先,同级按规范化名字排序 ⇒ 与遍历顺序无关、可复现
        cands.sort(key=lambda c: (0 if c[1] == "same_final_token" else 1, c[0]))

        picked = None
        for s_norm, kind, shared in cands:
            m_new = unique_object(store, s_norm, r1)
            if m_new is None or norm(m_new) == norm(m):
                continue
            a_new = unique_object(store, m_new, r2)
            if a_new is None:
                continue
            if norm(a_new) == norm(a):
                continue                      # 新旧答案撞车 ⇒ 旧解未必败,不收
            picked = (s_norm, kind, shared, m_new, a_new)
            break
        if picked is None:
            stats["confusable_reject"]["no_resolvable_new_chain"] += 1
            continue
        s_norm, kind, shared, m_new, a_new = picked
        x_new = surface.get(s_norm, s_norm)

        st, en = span
        new_q = r["question"][:st] + x_new + r["question"][en:]

        # 档位不靠假设:查 X' 到底在不在种子任务的 gold 文档池里。
        # 不在 → hop1 一检索就穿帮,d*≈0,T1;在 → hop1 还能糊弄过去,hop2 才错,d*=0.5,T2。
        blob = context_blob(r)
        x_in_ctx = bool(blob) and s_norm in blob
        if not blob:
            tier, d_star = "T1", 0.0
            basis = "未加载 context(--no-context),按 §2.4 默认判 T1,未经文档核实"
        elif x_in_ctx:
            tier, d_star = "T2", 0.5
            basis = ("X' 出现在种子的 gold 文档池里,hop1 不立刻穿帮,"
                     "分歧落在 hop2(规范 §2.4 T2)")
        else:
            tier, d_star = "T1", 0.0
            basis = ("已核实:X' 不出现在种子任务的任何 gold 文档中,"
                     "hop1 检索开局即穿帮(规范 §2.4 T1)")
        out.append({
            "pair_id": f"2wiki/{args.split}/confusable_entity/{r['_id']}",
            "level": "L4",
            "domain": "2wiki",
            "edit_family": "confusable_entity",
            "split": args.split,
            "seed_qid": r["_id"],
            "seed_type": r["type"],
            "seed_question": r["question"],
            "seed_answer": r["answer"],
            "l4_question": new_q,
            "l4_answer": a_new,
            "edit": {"span": [st, en], "from": r["question"][st:en], "to": x_new,
                     "confusability": kind, "shared_tokens": shared},
            "seed_chain": [[x, r1, m], [m, r2, a]],
            "l4_chain": [[x_new, r1, m_new], [m_new, r2, a_new]],
            "verification": {
                "new_chain_resolvable": True,
                "new_chain_unique": True,       # 两跳都要求 (subject, relation) 唯一
                "old_answer_on_new_question_correct": False,
                "old_answer": r["answer"],
                "new_gold": a_new,
                "junction_changed": True,       # M → M',种子记忆的 hop1 文档整段失效
                "x_prime_in_seed_context": x_in_ctx,
            },
            "tier": tier,
            "tier_basis": basis,
            "d_star": d_star,
            "sim_filter": {"applied": False, "tau": args.sim_filter,
                           "note": "待 bge-large 就位后补 §2.1 第 1 条过滤"},
            "generator": SCRIPT_VERSION,
            "rng_seed": args.seed,
        })
    return out


def _find_span(question, entity):
    """在问句里定位实体的完整提及,返回 (start, end)。

    两个坑,都在冒烟里实打实撞到过:
    1. evidences 里的 subject 是 'G.I. Jane',问句写的是 'G.I. Jane (1951 Film)' ——
       只替换前半截会留下张冠李戴的消歧后缀('It Happened to Jane (1951 Film)',
       而它其实是 1959 年的片子)。
    2. evidences 里是 'Lover Man',问句写的是 'Lover Man (Oh, Where Can You Be?)' ——
       同样必须整块吞掉,否则新问句成了 'Old Man (Oh, Where Can You Be?)'。
    所以定位到实体后,把紧跟其后的整个括号块一并纳入替换区间。
    """
    for cand in (entity, re.sub(r"\s*\([^)]*\)\s*$", "", entity)):
        if not cand:
            continue
        m = re.search(re.escape(cand), question, flags=re.IGNORECASE)
        if not m:
            continue
        st, en = m.start(), m.end()
        tail = re.match(r"\s*\([^)]*\)", question[en:])
        if tail:
            en += tail.end()
        return st, en
    return None


# --------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="train", choices=["train", "validation", "test"])
    ap.add_argument("--hf-home", default=DEFAULT_HF_HOME)
    ap.add_argument("--family", default="both",
                    choices=["both", "polarity_flip", "confusable_entity"])
    ap.add_argument("--seed-pool", type=int, default=20000,
                    help="从 split 里取前 N 条当种子集 S(0=全量)")
    ap.add_argument("--limit-per-family", type=int, default=0,
                    help="每族最多保留多少条(0=不限);随机抽样,种子固定")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=str(HERE / "l4_2wiki_pairs.jsonl"))
    ap.add_argument("--sim-filter", type=float, default=None, metavar="TAU",
                    help="[未实现] 表面相似度阈值 tau(§2.1 第 1 条),待 bge-large 就位")
    ap.add_argument("--no-context", action="store_true",
                    help="不加载 context 列(省内存),代价是易混替换的 T1/T2 档只能按默认判,"
                         "不经 gold 文档核实")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.sim_filter is not None:
        print(f"[warn] --sim-filter {args.sim_filter} 收到但未实现,本轮不做过滤。",
              file=sys.stderr)
    t0 = time.time()
    rng = random.Random(args.seed)

    want_ctx = (not args.no_context) and args.family in ("both", "confusable_entity")
    rows = load_rows(args.split, args.hf_home, args.seed_pool, with_context=want_ctx)
    print(f"[load] split={args.split} 种子集 |S|={len(rows)}  ({time.time()-t0:.1f}s)")
    store, _ = build_triple_store(rows)
    print(f"[store] 三元组键 {len(store)} 个 (subject, relation)")

    stats = {"polarity_reject": Counter(), "confusable_reject": Counter()}
    recs = []
    if args.family in ("both", "polarity_flip"):
        p = gen_polarity_flip(rows, args, stats)
        print(f"[polarity_flip] {len(p)} 条")
        recs.append(("polarity_flip", p))
    if args.family in ("both", "confusable_entity"):
        c = gen_confusable_entity(rows, store, args, stats, rng)
        print(f"[confusable_entity] {len(c)} 条")
        recs.append(("confusable_entity", c))

    final = []
    for name, lst in recs:
        lst.sort(key=lambda r: r["pair_id"])          # 顺序与遍历无关
        if args.limit_per_family and len(lst) > args.limit_per_family:
            idx = sorted(random.Random(args.seed).sample(range(len(lst)),
                                                         args.limit_per_family))
            lst = [lst[i] for i in idx]
        final.extend(lst)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "generator": SCRIPT_VERSION,
        "seed": args.seed,
        "split": args.split,
        "seed_pool": len(rows),
        "counts": {k: sum(1 for r in final if r["edit_family"] == k)
                   for k in ("polarity_flip", "confusable_entity")},
        "tier_counts": dict(Counter(r["tier"] for r in final)),
        "polarity_reject": dict(stats["polarity_reject"]),
        "confusable_reject": dict(stats["confusable_reject"]),
        "elapsed_s": round(time.time() - t0, 1),
        "args": vars(args),
    }
    with open(str(out) + ".stats.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[done] 共 {len(final)} 条 → {out}  ({summary['elapsed_s']}s)")
    print("       丢弃原因(极性翻转)", summary["polarity_reject"])
    print("       丢弃原因(易混替换)", summary["confusable_reject"])


if __name__ == "__main__":
    main()
