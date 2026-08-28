# 09 对齐检查的门槛全部参数化，加相对判据 `--align-rule {abs,rel,both}`

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.4（判据与键名）、16.9（测试）。改动只在 `pipeline/train/train_causal_share.py`（对齐检查段，第 78 到 90 行的常量与第 434 到 570 行的 `run_align_check`、参数在 `--align-events` 之后加）、`pipeline/train/train_causal_tool.py`（对齐检查函数与参数）、`tests/test_share_trainer.py`、`tests/test_ctool_readpos.py`。不改 `share_data.py`、不改 `run.py`、不改文档。

## 背景

第一轮的五个门槛（逐行 2e-5、逐 token 3e-4、bf16 平均 2e-2 / 最大 1e-1、基线 3 倍）是按实测放宽的自定值（决定 18），ctool 的 `--align-tol` 从 1e-4 放到 3e-4（决定 20），gyb 没有裁决过。gyb 要做成参数、并给一个相对判据当备选，回头拿 `ALIGN_CHECK.json` 里的数对比。

## 要做的

1. `train_causal_share.py`：
   - 删掉模块顶部常量 `TOK_DIFF_TOL / BF16_MEAN_TOL / BF16_MAX_TOL`（第 78 到 81 行），改成参数 `--align-tok-tol 3e-4`、`--align-bf16-mean-tol 2e-2`、`--align-bf16-max-tol 1e-1`、`--align-baseline-factor 3.0`（基线告警用的倍数，现在写死的 `3 ×`），`--align-tol 2e-5` 已有；`REF_INST_CE_DRIFT_TOL` 不动（那是参照路径自检，不是门槛）。`run_align_check` 从 `args` 取值，不留第二份默认值。
   - 加 `--align-rule`（`choices=["abs", "rel", "both"]`，默认 `abs`）与 `--align-rel-tol`（float，默认 1e-5）。判定：`abs` = 现状（逐行 ≤ `align_tol` 且逐 token ≤ `align_tok_tol`）；`rel` = `rel_max_abs_diff ≤ align_rel_tol`，`rel_max_abs_diff = max_abs_diff / ref_scale`，`ref_scale = max(|ce_ref|)`（参照路径逐行 ce 绝对值的最大值，`ref_scale == 0` 时 `rel_max_abs_diff` 写 `null` 且 `rel` 规则判失败并在 `start` 前打印原因）；`both` = 两条同时成立。
   - `ALIGN_CHECK.json` 不管规则是哪条都写全：`rule, tol, tok_tol, rel_tol, ref_scale, rel_max_abs_diff, bf16_mean_tol, bf16_max_tol, baseline_factor`；已有键（`PASS, n_events, ..., baseline_warn`）一个不动。`start` 事件加 `align_rule`。
   - 不过仍 `sys.exit(2)`，失败信息里写出用的规则和对应的数。
2. `train_causal_tool.py`：加 `--align-rule`（同三个值，默认 `abs`）与 `--align-rel-tol`（默认 1e-5）。相对量 `rel_maxdiff_hidden = maxdiff_hidden / hidden_scale`，`hidden_scale = max(|h_full|)`（整段前向末位隐状态绝对值的最大值，就是现在算 `maxdiff_hidden` 时那个整段前向的张量）。`abs` = 现状（`maxdiff_hidden ≤ align_tol`，如果现有判定还看分类头 logits 的差就照旧一起看）；`rel` = `rel_maxdiff_hidden ≤ align_rel_tol`；`both` = 两条同时。ALIGN_CHECK.json 加 `rule, rel_tol, hidden_scale, rel_maxdiff_hidden`。
3. 测试（spec 16.9 第三条）：
   - `tests/test_share_trainer.py`：小模型 CPU 上 `--align-only` 跑三种规则，`ALIGN_CHECK.json` 都有全部新键，三种 `PASS` 都为真（fp32 CPU 差是 1e-6 量级）；`--align-rule rel --align-rel-tol 0` 退出码 2；`--align-baseline-factor 0` 时 `baseline_warn` 为真（`max(0 × 基线, 1e-6)` 仍是 1e-6，差大于 1e-6 才告警——如果小模型上差小于 1e-6，改成断言 `baseline_factor` 键的值等于传入值即可，测试里写明原因）。
   - `tests/test_ctool_readpos.py`：ctool 的对齐检查函数在小模型上三种规则都过，`rel_maxdiff_hidden` 与 `hidden_scale` 在 JSON 里；`--align-rel-tol 0` 判失败。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_ctool_readpos` 通过。
- `grep -n "TOK_DIFF_TOL\|BF16_MEAN_TOL\|BF16_MAX_TOL" pipeline/train/train_causal_share.py` 零命中。
- `grep -n "rel_max_abs_diff" pipeline/train/train_causal_share.py` 与 `grep -n "rel_maxdiff_hidden" pipeline/train/train_causal_tool.py` 命中。
- 不传新参数时两个脚本的判定与改前相同（默认值就是原常量）。
