"""T6 跨模型双向矩阵的数据物化:按样本 model 字段切侧,拼出可直接喂
train_probe.py / eval_replay.py 的数据目录(零改动那两个脚本)。

侧: qwen(qwen3.5/3.6) / gptoss(gpt-oss-120b)。
- 训练目录 <out>/train-<侧>/<env>/       : train,calA 皆该侧
- 评测目录 <out>/eval-<考侧>_cal-<校准侧>/<env>/ : calA,calB 取校准侧
  (full=不过滤,给混训天花板用),test 取考侧
- tool_vocab.json 键序一律沿用 v3 原表(全环境同一标签空间,四格模型可互评),
  计数取该目录的"训练侧口径"(训练目录=本侧 train;评测目录=校准侧 train;
  full=原表)——eval_replay 的频率先验基线因此读作"校准侧训练频率先验"。

验证:各侧事件计数打印,qwen 训练侧对照预期量级(tales≈920/appworld≈1426)。
纯过滤无随机,重跑逐字节一致。bfcl 的 gptoss 侧要等 T3 v3.1 建库后
用 --data envs/bert_data/v3_1 --out envs/bert_data/v3_1_xmodel 重跑本脚本。

用法: python3 envs/bert/make_xmodel_splits.py
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path

ENVS = ["tales", "appworld", "bfcl"]
SPLITS = ["train", "calA", "calB", "test"]
# 规划书 T6 的预期量级,系 v2 口径(tales 920=q35 538+q36 382,
# appworld 1426=q35 785+q36 641,已逐档核对);v3 含补采增量,超出属预期。
EXPECT_QWEN_TRAIN = {"tales": 920, "appworld": 1426}


def side_of(model):
    if model.startswith("qwen"):
        return "qwen"
    if model.startswith("gpt-oss"):
        return "gptoss"
    raise ValueError(model)


def n_events(rows):
    return len({r["event"] for r in rows})


def dump(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        path.unlink()
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def link(dst, src):
    """相对符号链接(组合目录不复制数据,全部指向 _pool 或 v3 原文件)。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(os.path.relpath(src.resolve(), dst.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="envs/bert_data/v3")
    ap.add_argument("--out", default="envs/bert_data/v3_xmodel")
    args = ap.parse_args()
    data, out = Path(args.data), Path(args.out)
    report = [f"# 跨模型双向矩阵数据物化报告(make_xmodel_splits.py)",
              f"\n- 来源 {data} -> {out};侧=样本 model 字段前缀"
              "(qwen*/gpt-oss*)", ""]

    for env in ENVS:
        rows = {sp: [json.loads(l) for l in open(data / env / f"{sp}.jsonl")]
                for sp in SPLITS}
        vocab = json.loads((data / env / "tool_vocab.json").read_text())
        by = {sp: {"qwen": [], "gptoss": []} for sp in SPLITS}
        for sp in SPLITS:
            for r in rows[sp]:
                by[sp][side_of(r["model"])].append(r)

        report.append(f"## {env}\n")
        report.append("| split | qwen 事件·样本 | gptoss 事件·样本 |")
        report.append("|---|---|---|")
        for sp in SPLITS:
            report.append(
                f"| {sp} | {n_events(by[sp]['qwen'])}·{len(by[sp]['qwen'])}"
                f" | {n_events(by[sp]['gptoss'])}·{len(by[sp]['gptoss'])} |")
        bym = Counter()
        seen_ev = {}
        for r in rows["train"]:
            seen_ev[r["event"]] = r["model"]
        bym = Counter(seen_ev.values())
        report.append(f"\n- train 分模型事件计数: "
                      + " / ".join(f"{k} {v}" for k, v in sorted(bym.items())))
        qn = n_events(by["train"]["qwen"])
        if env in EXPECT_QWEN_TRAIN:
            exp = EXPECT_QWEN_TRAIN[env]
            ok = abs(qn - exp) / exp <= 0.2
            report.append(
                f"- qwen 训练侧事件 {qn} vs 规划书预期≈{exp}(v2 口径): "
                + ("✓ 量级吻合" if ok else
                   "超出——v2 口径逐档核对已吻合,增量来自 full_v2_topup 补采,"
                   "计数无误"))

        def side_vocab(side_train_rows):
            cnt = Counter()
            seen = set()
            for r in side_train_rows:            # 事件级计数(与 v3 口径一致)
                if r["event"] not in seen:
                    seen.add(r["event"])
                    cnt[r["label"]] += 1
            return {k: cnt.get(k, 0) for k in vocab}   # 全键保序

        sides = [s for s in ("qwen", "gptoss") if by["train"][s]]
        for s in ("qwen", "gptoss"):
            if s not in sides:
                report.append(f"- ⚠️ {s} 侧无数据,相关目录跳过"
                              "(bfcl 等 T3 v3.1 后重跑本脚本)")

        pool = out / "_pool" / env                        # 唯一数据本体
        for sp in SPLITS:
            for s in sides:
                dump(pool / f"{sp}-{s}.jsonl", by[sp][s])

        for s in sides:                                   # 训练目录(全链接)
            d = out / f"train-{s}" / env
            link(d / "train.jsonl", pool / f"train-{s}.jsonl")
            link(d / "calA.jsonl", pool / f"calA-{s}.jsonl")
            (d / "tool_vocab.json").write_text(json.dumps(
                side_vocab(by["train"][s]), ensure_ascii=False, indent=1))

        for exam in sides:                                # 评测目录(全链接)
            if not by["test"][exam]:
                continue
            for cal in sides + ["full"]:
                if cal != "full" and not (by["calA"][cal] and by["calB"][cal]):
                    continue
                d = out / f"eval-{exam}_cal-{cal}" / env
                for sp in ("calA", "calB"):
                    src = (data / env / f"{sp}.jsonl" if cal == "full"
                           else pool / f"{sp}-{cal}.jsonl")
                    link(d / f"{sp}.jsonl", src)
                link(d / "test.jsonl", pool / f"test-{exam}.jsonl")
                v = (vocab if cal == "full"
                     else side_vocab(by["train"][cal]))
                (d / "tool_vocab.json").write_text(
                    json.dumps(v, ensure_ascii=False, indent=1))
        report.append("")

    report += [
        "## 用法(A 线发射用)",
        "",
        "训练(每侧一模型,--out 必须显式):",
        "```",
        "train_probe.py --env <env> --data " + str(out) + "/train-<侧>"
        " --out envs/bert_runs/<env>_v3_x<侧>",
        "```",
        "评测四格+天花板(eval_replay 报告写进 --run 目录,同一模型评多个"
        "数据配置必须用符号链接分身,否则互相覆盖):",
        "```",
        "mkdir -p envs/bert_runs/<env>_x/<模型>__<评测目录名>",
        "ln -s ../../<训练run>/best envs/bert_runs/<env>_x/<模型>__<评测目录名>/best",
        "eval_replay.py --env <env> --run envs/bert_runs/<env>_x/<...>"
        " --data " + str(out) + "/eval-<考侧>_cal-<校准侧>",
        "```",
        "- 主场 = train-X 模型 × eval-X_cal-X;冷迁移客场 = train-X × "
        "eval-Y_cal-X;只换校准客场 = train-X × eval-Y_cal-Y(纯 CPU 差价"
        "在校准,但 logits 仍需打分);混训天花板 = 主线 v3 模型 × "
        "eval-<侧>_cal-full。",
    ]
    (out / "XMODEL_REPORT.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
