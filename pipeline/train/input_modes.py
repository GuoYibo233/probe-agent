"""T5 消融输入模式:full / no-think / no-hist 的样本切割(单一事实源)。

- full     原样
- no-think 切掉 [THINKING] 段(含标记);同事件样本合并为一条,w 归一为 1
- no-hist  切掉 [HISTORY] 段(含标记),Task 行与 [THINKING] 段保留;其余字段不动

train_probe.py 与 eval_replay_mode.py 都 import 本模块,保证训练评测切法逐字一致。

肉眼核对(验收件,打印同一事件三种模式各一条):
  python3 envs/bert/input_modes.py --data envs/bert_data/v3 --env bfcl --split test
"""

import argparse
import json

H_MARK = "\n[HISTORY]\n"
T_MARK = "\n[THINKING]\n"


def cut(text, mode):
    ih = text.find(H_MARK)
    it = text.find(T_MARK, ih + 1)
    assert ih >= 0 and it >= 0, "样本缺 [HISTORY]/[THINKING] 标记"
    if mode == "no-think":
        return text[:it]                    # Task + [HISTORY] 段
    if mode == "no-hist":
        return text[:ih] + text[it:]        # Task 行 + [THINKING] 段
    return text


def apply_mode(rows, mode):
    """rows: 数据集 jsonl 行(dict)列表。返回新列表,不改原行。"""
    if mode == "full":
        return rows
    if mode == "no-hist":
        out = []
        for r in rows:
            r = dict(r)
            r["text"] = cut(r["text"], mode)
            out.append(r)
        return out
    if mode == "no-think":                  # 同事件文本全同,取首条,权重归一
        seen = {}
        for r in rows:
            if r["event"] in seen:
                continue
            r = dict(r)
            r["text"] = cut(r["text"], mode)
            r["w"], r["sent_idx"], r["n_sents"] = 1.0, 0, 1
            seen[r["event"]] = r
        return list(seen.values())
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="envs/bert_data/v3")
    ap.add_argument("--env", default="bfcl")
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    rows = [json.loads(l)
            for l in open(f"{args.data}/{args.env}/{args.split}.jsonl")]
    # 挑一个有历史、多边界的事件,三种模式对照才有信息量
    pick = next(r for r in rows
                if r["sent_idx"] == 1 and "(start)" not in
                r["text"].split(T_MARK)[0])
    for mode in ("full", "no-think", "no-hist"):
        r = apply_mode([pick], mode)[0]
        print(f"\n{'='*70}\n[{mode}] event={r['event']} w={r['w']} "
              f"sent {r['sent_idx']+1}/{r['n_sents']}\n{'-'*70}\n{r['text']}")
    # 自检:no-think 合并数 = 事件数;no-hist 行数不变
    ev = len({r["event"] for r in rows})
    assert len(apply_mode(rows, "no-think")) == ev
    assert len(apply_mode(rows, "no-hist")) == len(rows)
    nt = apply_mode(rows, "no-think")
    assert all(T_MARK not in r["text"] for r in nt)
    nh = apply_mode(rows, "no-hist")
    assert all(H_MARK not in r["text"] and T_MARK in r["text"] for r in nh)
    print(f"\n自检: {args.env}/{args.split} 事件 {ev} / 样本 {len(rows)};"
          f" no-think 合并 {len(nt)} 条 ✓; no-hist 保行数且无 [HISTORY] ✓")


if __name__ == "__main__":
    main()
