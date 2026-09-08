"""T5 ablation input modes: sample slicing for full / no-think / no-hist (single source of truth).

- full     as is
- no-think cuts the [THINKING] segment (including its marker); samples from the same event are
           merged into one, w normalized to 1
- no-hist  cuts the [HISTORY] segment (including its marker), keeps the Task line and the
           [THINKING] segment; other fields untouched

Both train_probe.py and eval_replay_mode.py import this module, to keep the training and eval
slicing character for character identical.

Eyeball check (acceptance artifact, prints one entry per mode for the same event):
  python3 envs/bert/input_modes.py --data envs/bert_data/v3 --env bfcl --split test
"""

import argparse
import json

H_MARK = "\n[HISTORY]\n"
T_MARK = "\n[THINKING]\n"


def cut(text, mode):
    ih = text.find(H_MARK)
    it = text.find(T_MARK, ih + 1)
    assert ih >= 0 and it >= 0, "sample is missing the [HISTORY]/[THINKING] marker"
    if mode == "no-think":
        return text[:it]                    # Task + [HISTORY] segment
    if mode == "no-hist":
        return text[:ih] + text[it:]        # Task line + [THINKING] segment
    return text


def apply_mode(rows, mode):
    """rows: a list of dataset jsonl rows (dicts). Returns a new list, does not modify the original rows."""
    if mode == "full":
        return rows
    if mode == "no-hist":
        out = []
        for r in rows:
            r = dict(r)
            r["text"] = cut(r["text"], mode)
            out.append(r)
        return out
    if mode == "no-think":                  # Same text within an event; keep the first row, normalize the weight
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
    # This spot originally had no choices (the only silent gap among the pipeline's eight
    # --env options): passing a wrong environment name isn't caught by argparse, it just
    # builds a nonexistent path at :62.
    ap.add_argument("--env", default="bfcl",
                    choices=["tales", "appworld", "bfcl", "alfworld"])
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    rows = [json.loads(l)
            for l in open(f"{args.data}/{args.env}/{args.split}.jsonl")]
    # Pick an event with history and multiple boundaries, so comparing the three modes is informative
    pick = next(r for r in rows
                if r["sent_idx"] == 1 and "(start)" not in
                r["text"].split(T_MARK)[0])
    for mode in ("full", "no-think", "no-hist"):
        r = apply_mode([pick], mode)[0]
        print(f"\n{'='*70}\n[{mode}] event={r['event']} w={r['w']} "
              f"sent {r['sent_idx']+1}/{r['n_sents']}\n{'-'*70}\n{r['text']}")
    # Self-check: no-think's merged count = event count; no-hist's row count is unchanged
    ev = len({r["event"] for r in rows})
    assert len(apply_mode(rows, "no-think")) == ev
    assert len(apply_mode(rows, "no-hist")) == len(rows)
    nt = apply_mode(rows, "no-think")
    assert all(T_MARK not in r["text"] for r in nt)
    nh = apply_mode(rows, "no-hist")
    assert all(H_MARK not in r["text"] and T_MARK in r["text"] for r in nh)
    print(f"\nself-check: {args.env}/{args.split} events {ev} / samples {len(rows)};"
          f" no-think merged {len(nt)} rows ✓; no-hist kept row count with no [HISTORY] ✓")


if __name__ == "__main__":
    main()
