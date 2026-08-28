# 05 训练器审查修正（assistant-2 只读审查的 5 条建议 + 工单 03 的 2 条 minor）

Status: resolved
Blocked by: 03
Spec: `.scratch/kvshare-train/spec.md` 第 4、9 节；`design-attention.md` 第二、五节。改动只在 `pipeline/train/train_causal_share.py` 与 `tests/test_share_trainer.py`。行号按合并后的 main（`12c4a2b`），实现者以当前文件为准重新定位。

## 要做的

1. 末层隐状态的取法（S1，`train_causal_share.py` 第 133 到 136 行附近）：现在用 `output_hidden_states=True` 再取 `hidden_states[-1]`。改成 `model.model(input_ids=..., attention_mask=..., position_ids=..., use_cache=False).last_hidden_state` 再过 `model.lm_head`（LoRA 包装后 `model.model` / `model.lm_head` 的取法要兼容 peft 的包装对象，`get_base_model()` 或等价写法，实现者验证 `--lora` 下能跑）。理由：`hidden_states[-1]` 靠 HF 往元组末尾追加 `last_hidden_state` 的约定，并且 `--grad-ckpt` 下记录器会把 28 层输出全拿住（16k token 的块约 1.9 GB）。改完 `tests/test_share_trainer.py` 的 (a) 逐行 ce 等价测试必须仍然通过。
2. bf16 粗筛不做漂移自检（S2，第 429 到 430 行与第 331 到 338 行附近）：`_ref_forward` 加一个 `check_drift` 开关；fp32 那一遍保留（容差 1e-6），bf16 粗筛那一遍关掉（它只用 `row_ce`）。理由：bf16 下比的是两次独立前向的 bf16 结果，GPU 内核只要抖 1e-6 就 `RefBaselineDriftError` → `exit(2)`，一条只告警的检查会挡住开训。
3. 反向传播移出 autocast（S3，第 708 到 710 行附近）：`backward_logical_minibatch` 现在把 `.backward()` 也套在 autocast 里；改成 autocast 只包前向（收进 `block_row_ce` 的前向），`.backward()` 在外面，照旧训练器第 489 到 505 行的形状。
4. 对齐候选的长度筛（S5，第 268 行附近）：`_align_candidates` 的筛选条件改成 `n_full <= min(ALIGN_LEN_FILTER, args.max_len)`，否则 `--max-len < 2048` 时新路径丢事件而 `CallDS` 不丢，行数不等直接 `exit(2)`。
5. 参照路径的瞬时显存（S6，第 319 到 331 行附近）：fp32 参照路径里 `out`（[4, L, V] fp32 约 5.1 GB）还活着时又调一次 `inst_ce` 做漂移自检，瞬时约 10 GB；先 `del out, lg`（或者先取出需要的 `row_ce` / `tok_ce` 再释放）再调 `inst_ce`。
6. `ALIGN_CHECK.json` 的键（工单 03 minor F2）：去掉 spec 列表之外的 `bf16_warn` 键（`align_bf16_warn` 已在 `start` 事件里），`baseline_warn` 保留（spec 正文点名）。同步把 spec 第 9 节结果段的字段列表补上 `baseline_warn`（只改那一行）。
7. 断言分支的测试（工单 03 minor N2）：`tests/test_share_trainer.py` 加一个用例，给 `inst_ce_fn` 打补丁让它返回偏移过的行均值，断言 `_ref_forward(check_drift=True)` 抛 `RefBaselineDriftError`（或现有的那个异常类型）并且错误信息含漂移数值；再加一个用例断言 `check_drift=False` 时同样的补丁不抛。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data` 通过；`python3 -m unittest discover -s tests -p 'test_share_*.py'` OK（skip 也算）。
- `grep -n "output_hidden_states" pipeline/train/train_causal_share.py` 无命中；`grep -n "backward" pipeline/train/train_causal_share.py` 命中的行不在任何 `torch.autocast` 的 with 块之内（报告里贴出上下文证明）。
- `--lora` 路径：`tests/test_share_trainer.py` 里加一个小模型 `--lora` 的一次前向加反向用例（peft 装了就跑，没装就 skip），证明第 1 条的取法在 peft 包装下能跑。
- `python3 run.py selfcheck` 通过（注册表不动，只是确认没碰坏）。
- 不改 `share_data.py`、不改旧脚本、不改 spec 除第 6 条那一行。

## Comments

- 2026-08-28 plan-8-28 收账：wave3 实现 1 轮修复过评审，分支 `ticket/2026-08-28-wave3/T05`（base `45c881e`，head `6c507cc`），合并为 `a89da00`（spec §9 字段列表那一行与主干冲突，取主干并补 `baseline_warn`）。主会话复核：cprobe-env 下 `test_share_trainer test_share_data test_ctool_readpos` Ran 39 tests OK；`grep -c output_hidden_states` 0；`_ref_forward(..., check_drift=True)` 开关在；selfcheck 76 任务就位。遗留 minors（照录）：F2 报告里 backward 的 grep 命中行数写的 4 实际 6（结论对：206、248 两处 `.backward()` 都不在 autocast 内）；N1 新测试与既有 `test_lora_forward_backward` 大段重复。实现者 concerns（照录）：顺手改了 `run_align_check` 里一条过时注释；worktree 里建了只读软链 `pipeline/data/nyapass_aw_v1`（在 .gitignore 里，随 worktree 删除）；worktree 里 selfcheck 报 16 处缺失是本地虚拟环境目录不在版本控制里，主仓对照 76/4/3 一致。GPU 上 S2/S6 的数值效果由主会话最终冒烟核。
