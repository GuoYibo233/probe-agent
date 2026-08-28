# 09 对齐检查的门槛全部参数化，加相对判据 `--align-rule {abs,rel,both}`

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.4（判据与键名）、16.9（测试）。改动只在 `pipeline/train/train_causal_share.py`（对齐检查段，第 78 到 90 行的常量与第 434 到 570 行的 `run_align_check`、参数在 `--align-events` 之后加）、`pipeline/train/train_causal_tool.py`（对齐检查函数与参数）、`tests/test_share_trainer.py`、`tests/test_ctool_readpos.py`。不改 `share_data.py`、不改 `run.py`、不改文档。

## 背景

第一轮的五个门槛（逐行 2e-5、逐 token 3e-4、bf16 平均 2e-2 / 最大 1e-1、基线 3 倍）是按实测放宽的自定值（决定 18），ctool 的 `--align-tol` 从 1e-4 放到 3e-4（决定 20），gyb 没有裁决过。gyb 要做成参数、并给一个相对判据当备选，回头拿 `ALIGN_CHECK.json` 里的数对比。

## 要做的

1. `train_causal_share.py`：
   - 删掉模块顶部常量 `TOK_DIFF_TOL / BF16_MEAN_TOL / BF16_MAX_TOL`（第 78 到 81 行），改成参数 `--align-tok-tol 3e-4`、`--align-bf16-mean-tol 2e-2`、`--align-bf16-max-tol 1e-1`、`--align-baseline-factor 3.0`（基线告警用的倍数，现在写死的 `3 ×`），`--align-tol 2e-5` 已有；`REF_INST_CE_DRIFT_TOL` 不动（那是参照路径自检，不是门槛）。`run_align_check` 从 `args` 取值，不留第二份默认值。
   - 加 `--align-rule`（`choices=["abs", "rel", "both"]`，默认 `abs`）与 `--align-rel-tol`（float，默认 1e-5），放在 `--align-events` 之后、`lora_util.add_args(ap)` 之前（工单 08、10 也在参数段加参数，锚点不同；`start_kw` 里本工单加 `align_rule` 一个键，放在 `align_bf16_warn` 之后；合并冲突主会话收账时解）。判定：`abs` = 现状（逐行 ≤ `align_tol` 且逐 token ≤ `align_tok_tol`）；`rel` = `rel_max_abs_diff ≤ align_rel_tol`，`rel_max_abs_diff = max_abs_diff / ref_scale`，`ref_scale = mean(|ce_ref|)`（参照路径逐行 ce 绝对值的平均——用全体一个除数而不是逐行各除各的 ce，因为 ce 接近 0 的行会让逐行相对差发散；`ref_scale == 0` 时 `rel_max_abs_diff` 写 `null` 且 `rel` 规则判失败并打印原因）；`both` = 两条同时成立。
   - `ALIGN_CHECK.json` 不管规则是哪条都写全：`rule, tol, tok_tol, rel_tol, ref_scale, rel_max_abs_diff, bf16_mean_tol, bf16_max_tol, baseline_factor`；已有键（`PASS, n_events, ..., baseline_warn`）一个不动。`start` 事件加 `align_rule`。
   - 不过仍 `sys.exit(2)`，失败信息里写出用的规则和对应的数。
2. `train_causal_tool.py`：加 `--align-rule`（同三个值，默认 `abs`）与 `--align-rel-tol`（默认 1e-5）。相对量已经在算，不起新名字：`align_check` 第 243 到 250 行的 `absmax_hidden`、`reldiff_hidden = d_h / max(absmax_hidden, 1e-9)`、`absmax_logits`、`reldiff_logits`（注释写「诊断用，不参与判定」）。判定：`abs` = 现状 `max(d_h, d_l) < tol`（第 241 行）；`rel` = `reldiff_hidden ≤ align_rel_tol` 且 `reldiff_logits ≤ align_rel_tol`；`both` = 两条同时。ALIGN_CHECK.json 只加 `rule, rel_tol` 两个键（相对量本来就在）。把那句「不参与判定」的注释改成说明 `rel` 规则用它们。
3. 测试（spec 16.9 第三条）放新文件 `tests/test_align_rules.py`（不往 `test_share_trainer.py` / `test_ctool_readpos.py` 末尾加用例——工单 08、10 并行改那两个文件；小模型的构造 import 现有测试文件里的辅助函数）：
   - 新训练器：小模型 CPU 上 `--align-only` 跑三种规则，`ALIGN_CHECK.json` 都有全部新键，三种 `PASS` 都为真（fp32 CPU 差是 1e-6 量级）；`--align-rule rel --align-rel-tol -1` 退出码 2（用负数不用 0：差恰好是 0.0 时 `≤ 0` 会偶发通过）；`run_align_check` 第二条失败出口（参照基线自检失败时写的最小报告）也要带 `rule / rel_tol` 两个键；`tests/test_share_trainer.py` 里现有 drift 用例构造的 `argparse.Namespace` 缺新属性（`align_tok_tol` 等）的，补上默认值；`--align-baseline-factor 0` 时 `baseline_warn` 为真（`max(0 × 基线, 1e-6)` 仍是 1e-6，差大于 1e-6 才告警——如果小模型上差小于 1e-6，改成断言 `baseline_factor` 键的值等于传入值即可，测试里写明原因）。
   - ctool：`CausalProbe.build()` 只认 `MODELS[base]`、没有 `path=` 口子（`train_causal_tool.py` 第 177 到 184 行），所以照 `tests/test_share_trainer.py` 第 59 与 625 到 632 行的做法建 `Qwen3Config` 临时模型目录，直接构造 `CausalProbe(<目录>, n_labels)` 调 `align_check`（不走 `main()`），三种规则都过，返回的报告里有 `reldiff_hidden / reldiff_logits / rule / rel_tol`；`rel_tol = -1` 判失败。不读现役数据目录。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_align_rules tests.test_share_trainer tests.test_ctool_readpos` 通过。
- `grep -n "TOK_DIFF_TOL\|BF16_MEAN_TOL\|BF16_MAX_TOL" pipeline/train/train_causal_share.py` 零命中。
- `grep -n "rel_max_abs_diff" pipeline/train/train_causal_share.py` 命中；`grep -n "hidden_scale\|rel_maxdiff_hidden" pipeline/train/train_causal_tool.py` 零命中（不许起第二个名）。
- 不传新参数时两个脚本的判定与改前相同（默认值就是原常量）。
