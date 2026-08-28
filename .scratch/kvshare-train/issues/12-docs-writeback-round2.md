# 12 第二轮文档回写：skill 三份参考、MAP.md、run.py notes、gates.md

Status: resolved
Blocked by: 07, 08, 09, 10, 11（全部合并进 main 之后才发）
Spec: `.scratch/kvshare-train/spec.md` 16.7（清单）、16.10（静默失败点 #28 到 #32）。改动只在 `.claude/skills/probe-pipeline/references/stage-commands.md`、`invariants.md`、`extending.md`、`gates.md`、`MAP.md`、`pipeline/eval/ACCEPT_EVAL.md`、`run.py`（只改 `train-cgen / train-cparam / train-ctool / eval-tool-causal / eval-tool-mbert / eval-ccall / eval-cparam` 七条的 `notes` 字符串，不动别的键）。不改任何 `.py` 逻辑、不改测试。

## 背景

第二轮合并了五张代码工单：三个评测脚本的 `--overlong`（07）、训练器的 `--gen-eval / --gen-bs`（08）、对齐门槛参数化与 `--align-rule / --align-rel-tol`（09）、`--mem-probe-pick` 与 `mem_probe_summary`（10）、`sweep-lr` 任务（11）。CLAUDE.md 的规矩是扩展完必须回写 skill，否则下一个人拿的是旧地图。

## 要做的

先读 `git log --oneline 7668166..HEAD` 和五张工单的 Comments，以合并后的代码（`--help` 输出）为准，不以工单原文为准。

1. `stage-commands.md` §3：参数表加 `--overlong`（三个评测脚本，三个值各一句判据）、`--gen-eval / --gen-bs`、`--align-rule / --align-rel-tol / --align-tok-tol / --align-bf16-mean-tol / --align-bf16-max-tol / --align-baseline-factor`（ctool 只有前两个）、`--mem-probe-pick`（三个值各一句）；`sweep-lr plan / report` 的用法各一条命令；§3 输出清单加 `SWEEP_REPORT.json/.md`、`mem_probe_summary` 事件、评测报告里的 `overlong_mode` 与计数键；§3.1 ③ 排卡规则改成「`mem_probe_summary.worst_gb × 1.1` 再打碎片折」（两条仍分开写）。
2. `invariants.md`：cgen / cparam 训练默认带 200 行生成式评估（决定 28，`val_exact_*` 只进日志不选 best）；探针默认 `cost`；评测默认 `--overlong left`；对齐规则默认 `abs`、门槛默认值就是第一轮的常量。
3. `extending.md` §5 加 #28 到 #34，措辞照 spec 16.10 但按合并后的代码核对每条的触发条件；§3「换实现先例」段补一句：第二轮的四个开关都是参数、默认值等于推荐值、不新增格；§3.4（第 167 行附近的 run_id 三段形状）补一句：学习率扫描的 run_id 是四段 `ks828<tag>_gptoss_cgen_lr<lr>`，产物 `pipeline/runs/sweep/`，不进矩阵、不进 `summarize_matrix`。`stage-commands.md` §3.2 同样补这一句。
4. `MAP.md`：`sweep_lr.py` 新增一行；三个评测脚本的行补 `--overlong`；`train_causal_share.py` 的行补 `--gen-eval / --gen-eval-at / --align-rule / --mem-probe-pick`；`share_data.py` 的行补 `full_token_ids / n_full_tokens / event_full_texts / select_keys / epoch_minibatches`。
5. `run.py`：`train-cgen / train-cparam` 的 `notes` 补 `--gen-eval`、`--align-rule`、`--mem-probe-pick` 各一句；`train-ctool` 的 `notes` 补 `--align-rule`；三个评测任务（`eval-tool-causal / eval-ccall / eval-cparam`）的 `notes` 补 `--overlong`；`eval-tool-mbert` 的 `notes` 写「mbert 头只支持 `--overlong left`」。只改字符串，不动结构；改完 `python3 run.py selfcheck`。
6. `gates.md`：smoke 门只读 `ALIGN_CHECK.json` 的 `PASS`，`rule` 进 JSON 不影响门——写一句。
7. `extending.md` 第 123 行「换实现先例」里「四个评测脚本一字不改」改成「判分一字不改，输入构造第二轮加了 `--overlong` 一个开关（默认 `left` 时逐字段不变）」；`stage-commands.md` §7 第 517 行附近提旧探针字段（`longest_event`）的排卡说明改成 `mem_probe_summary.worst_gb`（并写 `scope` 的含义）；`pipeline/eval/ACCEPT_EVAL.md` 里「REPLAY_REPORT 逐字节不变」一类判据改成「现有键不变，第二轮加了 `overlong_mode`、`n_oow` 与三个计数键」。

## 验收

- `python3 run.py selfcheck` 通过。
- `grep -n "overlong" .claude/skills/probe-pipeline/references/stage-commands.md MAP.md run.py` 三处命中；`grep -n "#34" .claude/skills/probe-pipeline/references/extending.md` 命中；`grep -n "worst_gb\|runs/sweep" .claude/skills/probe-pipeline/references/stage-commands.md` 两个都命中。
- 文档里每个参数的默认值与对应脚本 `--help` 一致（评审逐个对）。
- 不改 `.py` 逻辑、不改测试。

## Comments

- 2026-08-28 plan-8-28 收账：wave6 实现 0 轮修复过评审，分支 `ticket/2026-08-28-wave6/T12`（base `ed88ad7`，head `4f10aec`），合并为 `1998522`（无冲突）。评审 minors 两条与实现者两条 concern 主会话在合并后直接改：extending §5 新行的 `#` 前缀去掉、与前 27 行同一格式；#30 的位序说法统一成「从 0 数的第 6 位」；spec 16.10 的 #35、#36 以及工单发射后新加的 #37（grad-ckpt 重算内核）补进 extending §5；invariants / stage-commands 里指向「spec 16.10 #35/#36」的交叉引用保留（内容在 spec 里也在）。另外补两处工单发射后才定的事：stage-commands §3 参数表 `loop` 的说明改成决定 32 的三组规则；§3.1 加读法 ④（479aa4b 之前带 `--mem-probe` 的 run 第一条 step 峰值是探针的数，决定 35）。cannotVerify 两条（各开关的 GPU 运行时行为、#28/#29/#34 的触发条件只静态核对）由第二轮冒烟与 `--overlong` 端到端验证覆盖。
