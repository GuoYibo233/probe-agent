# T05 训练器审查修正 —— 实现报告

工单:`.scratch/kvshare-train/issues/05-trainer-review-fixes.md`
分支:`ticket/2026-08-28-wave3/T05`(base `45c881e3b24e0db68de6de001743b9d21ab1ca69`,
head `5060654fb62ff2847059963c118550ad49748201`)
改动文件:`pipeline/train/train_causal_share.py`、`tests/test_share_trainer.py`、
`.scratch/kvshare-train/spec.md`(仅第 9 节结果段那一行)。

## 一、做了什么(对照工单逐条)

**1. S1——末层隐状态的取法。** `_forward_packed` 原来调
`model(..., output_hidden_states=True)` 再取 `out.hidden_states[-1]`。改成新增
`_base_model_and_head(model)`(`model.get_base_model()` 拆到底座,没有这个方法
就用 `model` 本身)拿到 `(backbone, lm_head)`,再调
`backbone(input_ids=..., attention_mask=..., position_ids=..., use_cache=False)`
取 `.last_hidden_state`,gather 出损失位再过 `lm_head`。

`lora_util.wrap` 是就地注入(`get_peft_model` 直接替换原模型七件套
`nn.Linear`,原变量 `model` 本身在包装后还是原始 `Qwen3ForCausalLM`,不是
`PeftModel`),所以 `main()` 里训练全程用的 `model` 变量根本不会变成
`PeftModel`,`model.model`/`model.lm_head` 本来就直接可用;`_base_model_and_head`
里的 `get_base_model()` 分支是按工单原文"要兼容 peft 的包装对象"额外加的
防御分支,覆盖"调用方传进来的就是 `PeftModel` 本身"这种更泛的用法。用
`tests/test_share_trainer.py::TestBlockRowCeUnderLoRA::test_lora_forward_backward`
验证:小模型走 `lora_util.wrap` 之后直接调
`backward_logical_minibatch`,断言适配器参数(`requires_grad=True`)至少
有一个拿到梯度、非适配器参数(`requires_grad=False`)全部没有梯度。

**2. S2——bf16 粗筛不做漂移自检。** `_ref_forward` 加 `check_drift=True` 参数。
`check_drift=False` 时跳过"本地逐 token 公式聚合出的 `row_ce_local`"与
`inst_ce` 返回值的比对,只返回 `inst_ce` 的真实输出。三处调用点:REF_BATCH
整批(fp32)、bs=1 单行基线(fp32)保持默认 `True`;cuda 上 bf16 粗筛那一处显式
传 `check_drift=False`。补两个测试:`test_ref_forward_raises_real_exception_not_assert`
(改造后额外断言异常信息里带漂移数值)、新增
`test_ref_forward_check_drift_false_does_not_raise`(同一个漂移补丁,
`check_drift=False` 时不抛,返回值仍非空)。

**3. S3——反向移出 autocast。** `backward_logical_minibatch` 加 `amp=False`
参数,`with torch.autocast(...)` 只包 `block_row_ce` 这次前向,`loss_c` 的
计算与 `.backward()` 都移到 `with` 块外面。`main()` 里原来包住整个函数调用
的 `with torch.autocast(...)` 拿掉,`amp` 作为参数传进去。`run_mem_probe`
里的 `.backward()` 本来就在 autocast 外面,不用动。

**4. S5——对齐候选的长度筛。** `_align_candidates` 加 `max_len` 参数,筛选
条件从 `n_full <= ALIGN_LEN_FILTER` 改成 `n_full <= min(ALIGN_LEN_FILTER, max_len)`。
调用点 `run_align_check` 里补传 `args.max_len`。

**5. S6——参照路径的瞬时显存。** `_ref_forward` 里,`ce`/`rid` 从 `out`/`lg`
抽出来之后立刻 `del out, lg`,再调 `inst_ce_fn`(它自己会重新跑一遍模型前向,
产出自己的 `[B, L, V]` fp32 logits)。`row_ce_local` 的计算(仅 `check_drift=True`
时需要)挪到 `del` 之后、`inst_ce_fn` 调用之前,因为它只依赖已经抽出来的
`ce`/`rid`。

**6. F2——`ALIGN_CHECK.json` 的键(工单 03 minor)。** `report` dict 里去掉
`bf16_warn=bf16_warn`,落盘与打印的 JSON 不再带这个键;函数返回值改成
`dict(report, bf16_warn=bf16_warn)`,只在返回值里额外带一份给 `main()` 的
`start` 事件读(`align_bf16_warn=bool(align_rep["bf16_warn"])`,这行没动)。
`baseline_warn` 本来就在 `report` 里,不用改。spec 第 9 节结果段那一行的
字段列表补上 `baseline_warn`(唯一改动的一行,已核对没碰其余行)。

**7. N2——断言分支的测试(工单 03 minor)。** 工单要的两个用例都在 S2 的
改动里给出:`check_drift=True` 抛 `RefBaselineDriftError` 且错误信息含漂移
数值(正则 `max diff ([0-9.eE+-]+)` 提取后断言大于 `REF_INST_CE_DRIFT_TOL`)、
`check_drift=False` 时同样的补丁不抛。`TestRunAlignCheckHandlesRefBaselineDriftError`
类原有的"`run_align_check` 捕获异常走统一上报通道"用例不受影响(它
monkeypatch 的是整个 `_ref_forward` 函数,不经过 `check_drift` 分支)。

## 二、怎么验证的

**cprobe-env 单测(worktree 内,`pipeline/data/nyapass_aw_v1` 是软链到主仓同名
目录,只读,不改主仓任何文件):**

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
  tests.test_share_trainer tests.test_share_data
```
输出尾行:`Ran 32 tests in 233.106s` / `OK`(其中 `TestBlockRowCeUnderLoRA`、
`test_ref_forward_check_drift_false_does_not_raise` 是本次新增,其余是既有
用例回归)。`ALIGN_CHECK.json` 实测样例(`TestMainSmokeCPU.test_cgen_smoke`
跑出的真实产物):

```
{
 "PASS": true, "n_events": 2, "n_rows": 75, "n_tgt_tokens": 1551,
 "max_abs_diff": 1.9073486328125e-06, "max_tok_diff": 9.5367431640625e-07,
 "baseline_max_abs_diff": 1.9073486328125e-06, "tol": 2e-05,
 "bf16_mean_abs_diff": null, "bf16_max_abs_diff": null,
 "attn_impl": "sdpa", "mismatch_idx": [], "baseline_warn": false
}
```
确认落盘的 JSON 里没有 `bf16_warn` 键,`baseline_warn` 在;同一条 run 的
`start` 事件里 `'align_bf16_warn': False` 照常存在(CPU 设备走不到 cuda 分支,
恒 False,字段本身没丢)。

**系统 python3 discover(按验收要求跑一遍,预期整体 skip):**
```
python3 -m unittest discover -s tests -p 'test_share_*.py'
```
输出:`skipped "要 cprobe-env 解释器:No module named 'torch'"` ×2,
`Ran 2 tests in 0.000s` / `OK (skipped=2)`。

**grep 两条验收命令:**
```
grep -n "output_hidden_states" pipeline/train/train_causal_share.py   # 无输出,exit 1
grep -n "backward" pipeline/train/train_causal_share.py
```
后者命中 4 行(定义处 1 行 + 文档字符串里提到 `.backward()` 2 行 + 实际调用
2 处):`backward_logical_minibatch` 里的 `(loss_c / n_g).backward()` 在
`with torch.autocast(...)` 块之外(该 with 块只包 `ce_per_row, w = block_row_ce(...)`
这一行,已在报告贴出的代码片段里核对缩进);`run_mem_probe` 里的
`loss.backward()` 本来就在其 autocast 块外面,未改动。

**`python3 run.py selfcheck`(worktree 内跑,与主仓对照):**
worktree 内输出 `selfcheck: 76 任务 / 4 配方 / 3 预设, 16 处缺失`,16 处缺失全部
是 `cprobe-env`/`mbert-env`/`envs/*` 这类 `.gitignore` 里 `*-env/` 或
`envs/<第三方 clone>/` 排除的本地虚拟环境与第三方目录——git worktree 只
checkout 受版本控制的文件,这些目录天然不会出现在新工作树里,与本工单
改动无关。对照主仓同一份 `run.py`(未改动任何一行)跑 `selfcheck` 输出
`selfcheck: 76 任务 / 4 配方 / 3 预设, 全部就位`——任务/配方/预设计数与
worktree 内完全一致,证明注册表结构没被碰坏,缺失清单只是本地环境目录在
worktree 里不存在。本工单没有改 `run.py` 或任何任务定义。

## 三、commit 清单

- `5060654` T05: 训练器审查修正 S1/S2/S3/S5/S6 + F2/N2(工单 05)——
  `pipeline/train/train_causal_share.py`、`tests/test_share_trainer.py`、
  `.scratch/kvshare-train/spec.md` 三个文件,一次提交(七条要求互相耦合在
  同一批函数改动里,拆开提交没有更清晰的边界)。

## 四、自查发现与存疑

- 为了在 worktree 里跑通需要真实数据/分词器的用例,在 worktree 里建了一个
  软链 `pipeline/data/nyapass_aw_v1 -> /home/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1`
  (该目录整体在 `.gitignore` 里,`git status` 确认没有被 git 感知,只读引用,
  不影响主仓任何文件)。工作树按协议整体删除时这个软链会一并消失,不需要
  额外清理。
- `run_align_check` 里原有一条注释说"三处 `_ref_forward` 调用...共用这一个
  except",这句话在 S2 之后不再准确(bf16 那一处已经 `check_drift=False`,
  不会再抛 `RefBaselineDriftError`),已顺手改成准确描述(只有两处 fp32
  调用会触发这个 except)。这是文档准确性的顺手修正,不在工单条目里,
  单独提出来告知。
- `_forward_packed`/`_ref_forward` 的文档字符串里原来含 `output_hidden_states`
  这个字面字符串(用来解释"不再这样做"),第一版写完发现会让验收的
  `grep "output_hidden_states"` 命中,已改写成不含这个字面子串的等价描述
  再复核 grep 通过。
- 没有触碰 `share_data.py`、旧脚本(`train_causal_callgen.py`/
  `train_causal_param.py`)、`run.py` 注册表,`.scratch/kvshare-train/spec.md`
  只改了第 9 节结果段那一行(已用 `git diff` 核对整份 diff 只有这一处)。
