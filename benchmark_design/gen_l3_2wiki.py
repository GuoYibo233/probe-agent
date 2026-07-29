#!/usr/bin/env python
"""L3 (组合相似) 生成器 —— 2WikiMultihopQA 两跳拼接,规范 §1.3 第 1 类。

L3 的定义(§1.1):每个成分都在种子集 S 里单独出现过、但该成分组合从未出现过。
QA 域的成分元组是跳链 <(e1, r1), (e2, r2)>。

生成流程,严格照 §1.1 四步:
  1. 抽成分:把 S 里每条题的 evidences 拆成单跳三元组 (subject, relation, object),
     每条三元组记住它来自哪个种子问题(零件出处)。
  2. 采样组合:枚举 hop1=(s1, r1, o1) 与 hop2=(s2, r2, o2),要求拼接点 norm(o1)==norm(s2),
     且两条单跳来自**不同的**种子问题 —— 同一题里的两跳本来就连着,拼出来不是新组合。
  3. 可行性过滤(§1.1 第 3 条):
     a. 拼接点实体一致(枚举条件本身);
     b. 目标关系在 gold 三元组里有出处(hop2 本身就是一条 gold 三元组);
     c. 唯一可解:(s1, r1) 与 (o1, r2) 在三元组库里都只对应一个 object,
        否则新问题没有唯一答案,不能编程判分;
     d. 组合是新的:链 (s1, r1, r2) 不等于数据集里任何一条已有题的链
        —— 用全集查重而不只查 S,标准比规范更严。
  4. 记零件出处:hop1_from / hop2_from / template_from 三个种子问题 id 全部落盘,
     读数分析时可按零件数、按出处分层。

问句表面形式不手写模板,从数据集里挖:2wiki 的 compositional 题本身就是
"(a, r1, b) → (b, r2, c)" 的自然语言化,把其中的头实体 a 挖成占位符就得到
(r1, r2) 这一对关系的官方模板(例:'What is the date of birth of {S}\\'s father?')。
这样生成的 L3 问句与种子集同分布,不引入人写措辞这个混淆变量。

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
SCRIPT_VERSION = "gen_l3_2wiki.py/2026-07-30"
HERE = Path(__file__).resolve().parent
DEFAULT_HF_HOME = "/net/tokyo100-10g/data/str01_01/y-guo/hf"
DATASET = "voidful/2WikiMultihopQA"
PLACEHOLDER = "{S}"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .,;:!?\"'")


def load_rows(split, hf_home, limit=0):
    os.environ.setdefault("HF_HOME", hf_home)
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset(DATASET)[split].select_columns(
        ["_id", "type", "question", "answer", "evidences"])
    if limit:
        ds = ds.select(range(min(limit, len(ds))))
    return list(ds)


def find_span(question, entity):
    """定位实体提及,连同紧随其后的括号消歧块一起返回(理由同 gen_l4_2wiki)。"""
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


def two_hop_chain(row):
    """行是干净两跳就返回 ((s1,r1,o1),(o1,r2,o2)),否则 None。"""
    ev = row["evidences"]
    if len(ev) != 2 or any(len(e) != 3 for e in ev):
        return None
    (s1, r1, o1), (s2, r2, o2) = ev
    if norm(o1) != norm(s2):
        return None
    return (s1, r1, o1), (s2, r2, o2)


def mine_templates(rows, stats):
    """(r1, r2) → (模板串, 来源 qid)。同一 key 取出现最多的模板,同频按字典序定序。"""
    bank = defaultdict(Counter)
    src = defaultdict(dict)
    for r in rows:
        if r["type"] != "compositional":
            continue
        ch = two_hop_chain(r)
        if ch is None:
            stats["template_reject"]["not_two_hop"] += 1
            continue
        (s1, r1, o1), (s2, r2, o2) = ch
        if norm(o2) != norm(r["answer"]):
            stats["template_reject"]["answer_not_chain_tail"] += 1
            continue
        span = find_span(r["question"], s1)
        if span is None:
            stats["template_reject"]["head_not_in_question"] += 1
            continue
        st, en = span
        tpl = r["question"][:st] + PLACEHOLDER + r["question"][en:]
        if PLACEHOLDER not in tpl:
            continue
        bank[(r1, r2)][tpl] += 1
        src[(r1, r2)].setdefault(tpl, r["_id"])
    out = {}
    for key, ctr in bank.items():
        tpl = sorted(ctr.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        out[key] = (tpl, src[key][tpl], ctr[tpl], len(ctr))
    return out


def build_store(rows):
    store = defaultdict(dict)
    for r in rows:
        for ev in r["evidences"]:
            if len(ev) == 3:
                store[(norm(ev[0]), ev[1])][norm(ev[2])] = ev[2]
    return store


def unique_object(store, subj, rel):
    d = store.get((norm(subj), rel))
    if not d or len(d) != 1:
        return None
    return next(iter(d.values()))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="train", choices=["train", "validation", "test"])
    ap.add_argument("--hf-home", default=DEFAULT_HF_HOME)
    ap.add_argument("--seed-pool", type=int, default=20000,
                    help="种子集 S 的大小(取 split 前 N 条);0=全量")
    ap.add_argument("--limit", type=int, default=0, help="最多输出多少条(0=不限)")
    ap.add_argument("--novelty-scope", default="split", choices=["pool", "split"],
                    help="'组合从未出现过'查重的范围:pool=只查种子集 S(规范 §1.1 第 2 条的"
                         "字面要求);split=查整个 split(更严,默认)")
    ap.add_argument("--max-per-junction", type=int, default=2,
                    help="同一个拼接点实体最多产出多少条,防止热门实体刷屏")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=str(HERE / "l3_2wiki_items.jsonl"))
    ap.add_argument("--sim-filter", type=float, default=None, metavar="TAU",
                    help="[未实现] 表面相似度接口,与 L4 脚本保持一致;L3 不依赖 tau 准入,"
                         "但读数分析要报 L3 与种子的相似度分布,待 bge-large 就位后接上")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.sim_filter is not None:
        print(f"[warn] --sim-filter {args.sim_filter} 收到但未实现,本轮不做过滤。",
              file=sys.stderr)
    t0 = time.time()
    rng = random.Random(args.seed)

    rows = load_rows(args.split, args.hf_home, args.seed_pool)
    print(f"[load] split={args.split} 种子集 |S|={len(rows)}  ({time.time()-t0:.1f}s)")

    stats = {"template_reject": Counter(), "reject": Counter()}
    templates = mine_templates(rows, stats)
    print(f"[tpl] 从 S 里挖出 {len(templates)} 对 (r1, r2) 的官方模板")

    store = build_store(rows)

    # 已存在的链,用于 §1.1 第 2 条"剔除与已有任务元组相等的组合"。
    # 默认按整个 split 查重(比规范只查 S 更严):S 里没见过、但 split 里已有的组合,
    # 拿去当 L3 会把"数据集本来就有的题"混进组合泛化档,读数会虚高。
    novelty_rows = rows
    if args.novelty_scope == "split":
        full = load_rows(args.split, args.hf_home, 0)
        if len(full) > len(rows):
            novelty_rows = full
        print(f"[novelty] 查重范围 split,共 {len(novelty_rows)} 条题参与查重")
    seen_chains = set()
    for r in novelty_rows:
        ch = two_hop_chain(r)
        if ch:
            (s1, r1, _), (_, r2, _) = ch
            seen_chains.add((norm(s1), r1, r2))
    del novelty_rows

    # 步骤 1:抽成分,每条单跳记出处
    hop_by_object = defaultdict(list)   # norm(object) → [(s, r, o, qid)]
    hop_by_subject = defaultdict(list)  # norm(subject) → [(s, r, o, qid)]
    for r in rows:
        for ev in r["evidences"]:
            if len(ev) != 3:
                continue
            s, rel, o = ev
            hop_by_object[norm(o)].append((s, rel, o, r["_id"]))
            hop_by_subject[norm(s)].append((s, rel, o, r["_id"]))
    print(f"[parts] 拼接点候选实体 {len(hop_by_object)} 个")

    # 步骤 2-3:枚举组合 + 可行性过滤
    items = []
    emitted_chains = set()
    per_junction = Counter()
    for junction in sorted(hop_by_object):
        heads = hop_by_object[junction]
        tails = hop_by_subject.get(junction)
        if not tails:
            continue
        for (s1, r1, o1, qa) in sorted(set(heads)):
            for (s2, r2, o2, qb) in sorted(set(tails)):
                if qa == qb:
                    stats["reject"]["same_seed_question"] += 1
                    continue                      # 同一题里的两跳本来就连着,不算新组合
                if r1 == r2 and norm(s1) == junction:
                    stats["reject"]["degenerate"] += 1
                    continue
                if norm(o2) == norm(s1):
                    stats["reject"]["cycles_back"] += 1
                    continue
                key = (norm(s1), r1, r2)
                if key in seen_chains:
                    stats["reject"]["combination_already_seen"] += 1
                    continue
                if key in emitted_chains:
                    stats["reject"]["duplicate_output"] += 1
                    continue
                tpl = templates.get((r1, r2))
                if tpl is None:
                    stats["reject"]["no_template_for_relation_pair"] += 1
                    continue
                # 唯一可解:两跳都必须在库里唯一确定
                m = unique_object(store, s1, r1)
                if m is None or norm(m) != junction:
                    stats["reject"]["hop1_not_unique"] += 1
                    continue
                a = unique_object(store, junction, r2)
                if a is None or norm(a) != norm(o2):
                    stats["reject"]["hop2_not_unique"] += 1
                    continue
                if per_junction[junction] >= args.max_per_junction:
                    stats["reject"]["junction_quota"] += 1
                    continue

                tpl_str, tpl_src, tpl_freq, tpl_variants = tpl
                question = tpl_str.replace(PLACEHOLDER, s1)
                emitted_chains.add(key)
                per_junction[junction] += 1
                items.append({
                    "item_id": f"2wiki/{args.split}/l3_two_hop/{len(items):06d}",
                    "level": "L3",
                    "domain": "2wiki",
                    "construction": "two_hop_join",     # §1.3 第 1 类
                    "split": args.split,
                    "question": question,
                    "answer": a,
                    "chain": [[s1, r1, m], [m, r2, a]],
                    "junction_entity": m,
                    "n_parts": 2,
                    "provenance": {                     # §1.1 第 4 条:零件出处
                        "hop1_from": qa,
                        "hop2_from": qb,
                        "template_from": tpl_src,
                        "template": tpl_str,
                        "template_freq_in_S": tpl_freq,
                        "template_variants_in_S": tpl_variants,
                    },
                    "feasibility": {
                        "junction_consistent": True,
                        "target_relation_has_gold_triple": True,
                        "hop1_unique": True,
                        "hop2_unique": True,
                        "combination_unseen_in": args.novelty_scope,
                    },
                    "sim_filter": {"applied": False, "tau": args.sim_filter,
                                   "note": "待 bge-large 就位后补相似度读数"},
                    "generator": SCRIPT_VERSION,
                    "rng_seed": args.seed,
                })

    items.sort(key=lambda r: (r["provenance"]["hop1_from"], r["provenance"]["hop2_from"],
                              r["question"]))
    if args.limit and len(items) > args.limit:
        idx = sorted(rng.sample(range(len(items)), args.limit))
        items = [items[i] for i in idx]
    for i, it in enumerate(items):
        it["item_id"] = f"2wiki/{args.split}/l3_two_hop/{i:06d}"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    summary = {
        "generator": SCRIPT_VERSION,
        "seed": args.seed,
        "split": args.split,
        "seed_pool": len(rows),
        "templates_mined": len(templates),
        "n_items": len(items),
        "relation_pairs_used": dict(Counter(
            f"{it['chain'][0][1]} → {it['chain'][1][1]}" for it in items).most_common(20)),
        "reject": dict(stats["reject"]),
        "template_reject": dict(stats["template_reject"]),
        "elapsed_s": round(time.time() - t0, 1),
        "args": vars(args),
    }
    with open(str(out) + ".stats.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(items)} 条 L3 → {out}  ({summary['elapsed_s']}s)")
    print("       丢弃原因", summary["reject"])


if __name__ == "__main__":
    main()
