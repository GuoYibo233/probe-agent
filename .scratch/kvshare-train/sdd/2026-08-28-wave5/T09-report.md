# T09 报告——对齐检查门槛全部参数化,加相对判据 `--align-rule {abs,rel,both}`

工单:`.scratch/kvshare-train/issues/09-align-tolerance-params.md`
Spec:`.scratch/kvshare-train/spec.md` 16.4(判据与键名)、16.9 第三条(测试)
分支:`ticket/2026-08-28-wave5/T09`(工作树 `new1-wt/2026-08-28-wave5-T09`,已删除,分支保留)
base:`07907db08b50d66c1c193588f22b5cc97b24b4b3`
head:`ebbf4e2`(`f7e833f` 之后)

## 一、做了什么(对照工单逐条)

### 1. `train_causal_share.py`

- 删掉模块顶部常量 `TOK_DIFF_TOL`(3e-4)、`BF16_MEAN_TOL`(2e-2)、
  `BF16_MAX_TOL`(1e-1),连同它们头顶「固定值,不是命令行参数」的过时注释一并
  删除;`ALIGN_LEN_FILTER`、`REF_BATCH`、`REF_INST_CE_DRIFT_TOL` 不动。
- 新增六个参数,全部放在 `--align-events` 之后、`lora_util.add_args(ap)`
  之前:`--align-tok-tol`(默认 3e-4)、`--align-bf16-mean-tol`(默认 2e-2)、
  `--align-bf16-max-tol`(默认 1e-1)、`--align-baseline-factor`(默认 3.0)、
  `--align-rule`(`choices=["abs","rel","both"]`,默认 `abs`)、
  `--align-rel-tol`(默认 1e-5)。`--align-tol`(2e-5)已有,不重复加。
- `run_align_check` 里三处旧常量全部换成 `args.align_tok_tol` /
  `args.align_bf16_mean_tol` / `args.align_bf16_max_tol`;基线告警的写死
  倍数 `3 ×` 换成 `args.align_baseline_factor ×`。
- 判定逻辑:
  - `abs_ok = row_diff <= args.align_tol and tok_diff <= args.align_tok_tol`
    (与改前的 `pass_ok` 表达式逐字节相同,只是拆成一个中间变量)。
  - `ref_scale = mean(|ce_ref_i|)`(对 `row_ref`——参照路径 `REF_BATCH` 整批
    那一遍的返回值——取绝对值再求整体一个平均数,不是逐行各除各的 ce)。
  - `ref_scale == 0` 时 `rel_max_abs_diff = None`,`rel_ok = False`;否则
    `rel_max_abs_diff = row_diff / ref_scale`,`rel_ok = rel_max_abs_diff <=
    args.align_rel_tol`。
  - 按 `args.align_rule` 三选一:`abs` 取 `abs_ok`,`rel` 取 `rel_ok`,
    `both` 取两者与;`pass_ok = hard_ok and rule_ok`(`hard_ok` ——行数/丢弃
    计数一致性——不管哪条规则都必须成立,这条改前就是硬性前提,没有变过)。
- `ALIGN_CHECK.json` 补齐工单点名的九个键(`tol` 已在原有键里,不重复):
  `rule, tol, tok_tol, rel_tol, ref_scale, rel_max_abs_diff, bf16_mean_tol,
  bf16_max_tol, baseline_factor`;已有键(`PASS, n_events, n_rows,
  n_tgt_tokens, max_abs_diff, max_tok_diff, baseline_max_abs_diff,
  bf16_mean_abs_diff, bf16_max_abs_diff, attn_impl, mismatch_idx,
  baseline_warn`)一个不动。两条失败出口(判定失败的正常出口、
  `RefBaselineDriftError` 的自检失败出口)都带上新键——正常出口带全部九
  个,drift 出口按工单要求只补 `rule` 与 `rel_tol` 两个(那条路径在
  `abs_ok`/`rel_ok` 算出来之前就已经异常退出,其余七个键那个阶段还没算出
  数值)。
- 仍 `sys.exit(2)`;失败信息里加一行「规则 --align-rule <rule>」,`rel`/
  `both` 规则下再加一行相对差与 `ref_scale`(`ref_scale == 0` 时改印那句
  「ref_scale 为 0……rel 规则判失败」的原因说明)。
- `start` 事件加 `align_rule=args.align_rule`,紧跟在 `align_bf16_warn` 之后
  (工单指定的锚点)。

### 2. `train_causal_tool.py`

- `align_check()` 加两个关键字参数 `rule="abs"`、`rel_tol=1e-5`。相对量沿用
  已有的 `absmax_hidden`、`reldiff_hidden = d_h / max(absmax_hidden, 1e-9)`、
  `absmax_logits`、`reldiff_logits`,没有起第二个名字,只是把计算挪到判定
  逻辑之前。判定:`abs` = 现状 `max(d_h, d_l) < tol`;`rel` =
  `reldiff_hidden <= rel_tol and reldiff_logits <= rel_tol`(两个量都看,跟
  `abs` 规则一样);`both` = 两条同时。原来那句「诊断用,不参与判定」的注释
  改写成:`abs` 规则下这两个量只当诊断参考,`rel`/`both` 规则下参与判定。
- `main()` 加 `--align-rule`(同三个值,默认 `abs`)与 `--align-rel-tol`
  (默认 1e-5),`align_check()` 调用点传 `rule=args.align_rule,
  rel_tol=args.align_rel_tol`。`ALIGN_CHECK.json` 只多两个键 `rule,
  rel_tol`(相对量本来就在报告里)。失败打印信息加一行规则名,`rel_tol` 也
  印进相对差那一行。

### 3. 测试

新文件 `tests/test_align_rules.py`(没有改动 `test_share_trainer.py` /
`test_ctool_readpos.py` 的末尾,只在 `test_share_trainer.py` 里改了一处已有
用例的 `Namespace`,原因见下):

- `TestAlignRulesShare`:手造 3 个短 cgen 事件(每事件 2 行,行 `text` 用字符
  串拼接的方式保证严格互为前缀,满足 `share_data.load_events` 的前缀性质抽
  查),不读 `pipeline/data/nyapass_aw_v1/gptoss`。走真实 CLI 入口
  `tcs.main()`(`sys.argv` 打补丁,套 `TestMainSmokeCPU._run_smoke` 的写
  法),`--base` 指向临时保存的 `Qwen3Config` 小模型目录,`--align-only`。
  四个用例:
  - `test_three_rules_pass_with_all_new_keys`:`abs/rel/both` 三种规则各跑
    一次,`ALIGN_CHECK.json` 都含九个新键,`rule` 字段与传入值一致,`PASS`
    都为真。
  - `test_align_rel_tol_negative_fails`:`--align-rule rel --align-rel-tol
    -1` 退出码 2。
  - `test_baseline_factor_zero`:`--align-baseline-factor 0` 之后先断言
    `baseline_factor` 键等于 0.0;只有 `max_abs_diff > 1e-6` 才进一步断言
    `baseline_warn` 为真(工单第 1 条最后一句给的条件——实测这个小模型上
    `max_abs_diff` 恰好是 0.0,所以这条用例目前只跑到断言 `baseline_factor`
    键那一半,分支代码留着走查)。
  - `test_run_align_check_drift_exit_has_rule_and_rel_tol`:monkeypatch
    `_ref_forward` 直接抛 `RefBaselineDriftError`,断言
    `run_align_check` 写出的最小报告里 `rule`/`rel_tol` 与传入值一致。
- `TestAlignRulesTool`:照 `tests/test_share_trainer.py` 第 59
  (`_tiny_config` 里 `Qwen3Config` 的参数)与 625 到 632 行
  (`AutoModelForCausalLM.from_config(...).save_pretrained` +
  `tok.save_pretrained`)的做法建临时模型目录,直接
  `tct.CausalProbe(model_dir, n_labels=4)` 再调 `tct.align_check(...)`,不走
  `main()`,不读现役数据目录。两个用例:三种规则都过且报告带
  `reldiff_hidden/reldiff_logits/rule/rel_tol`;`rel_tol=-1` 判失败
  (`PASS=False`,不走 CLI 所以没有 `sys.exit`)。
- `tests/test_share_trainer.py`:`TestRunAlignCheckHandlesRefBaselineDriftError`
  里手造的 `argparse.Namespace`(第 316 到 318 行)缺新增的六个属性——不补的
  话 `run_align_check` 的 `except RefBaselineDriftError` 分支取
  `args.align_rule`/`args.align_rel_tol` 会 `AttributeError`。补齐六个属性,
  值等于 CLI 默认值。这处改动在工单允许的文件范围内(工单头部列的四个文件
  之一),不算「往末尾加用例」,是维护既有用例。

小模型的构造(`_tiny_config`/`QWEN_PATH`/`SEED`)通过
`from tests.test_share_trainer import _tiny_config, QWEN_PATH, SEED` 复用,
没有重复定义一份。

## 二、怎么验证的

工作树里默认没有 `pipeline/data`(该目录整个被 `.gitignore` 排除,是主仓
工作树里的本地便利软链接,不进 git,worktree 天然拿不到)。为了不只验证
「skip 掉真实数据相关用例」这一种弱结果,验证分两轮:

**第一轮(worktree 原状,`pipeline/data` 不存在)**——验证新测试文件本身,
以及不依赖真实数据集的用例:

```
cd new1-wt/2026-08-28-wave5-T09
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
    tests.test_align_rules tests.test_share_trainer tests.test_ctool_readpos
```
输出:`Ran 16 tests in 10.968s` `OK (skipped=8)`——8 个 skip 全部是
`test_share_trainer.py` 里依赖 `pipeline/data/nyapass_aw_v1/gptoss` 的既有
用例(`TestMainSmokeCPU`、`TestRunAlignCheckHandlesRefBaselineDriftError` 等
setUpClass 里的 `skipTest`),不是本工单加的新用例——新用例(`test_align_rules`
6 个)与 `test_ctool_readpos`(10 个)全部真跑并通过。

**第二轮(临时建本地软链接指向 net 盘同一份数据,验证过后立刻删除,没有
碰主仓)**——补跑第一轮里 skip 掉的那 8 个既有用例,确认这次改动没有破坏它
们、且验证了我在 `test_share_trainer.py` 里补的六个 `Namespace` 新属性确实
能让那条 drift 分支正常跑通(不是只在 skip 状态下语法正确):

```
ln -s /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data \
    new1-wt/2026-08-28-wave5-T09/pipeline/data
cd new1-wt/2026-08-28-wave5-T09
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
    tests.test_align_rules tests.test_share_trainer tests.test_ctool_readpos
rm new1-wt/2026-08-28-wave5-T09/pipeline/data   # 验证完立即删除
```
输出:`Ran 28 tests in 338.091s` `OK`(0 skip,全部真跑通过)。这一轮里
`TestMainSmokeCPU.test_cgen_smoke`/`test_cparam_smoke`(改前就有、断言
`ALIGN_CHECK.json` 的 `PASS` 为真)全部通过,验证了「不传新参数时判定与改前
相同」这条验收要求——它们跑的是默认参数(`--align-rule` 不传,取默认值
`abs`),走的正是新增的 `abs_ok` 分支,与改前的表达式逐字节相同。

`TestRunAlignCheckHandlesRefBaselineDriftError.test_run_align_check_reports_drift_error_instead_of_crashing`
这条(本工单改过它的 `Namespace`)也在这一轮里真跑,输出的报告确认带上了
`"rule": "abs", "rel_tol": 1e-05` 两个新键,退出码仍是 2——`ALIGN_CHECK.json`
关键片段:
```
{
 "PASS": false,
 "stage": "ref_forward_drift",
 "error": "...",
 "ref_inst_ce_drift_tol": 1e-06,
 "rule": "abs",
 "rel_tol": 1e-05
}
```

**验收清单里的四条 grep**(在 worktree 里跑):

```
grep -n "TOK_DIFF_TOL\|BF16_MEAN_TOL\|BF16_MAX_TOL" pipeline/train/train_causal_share.py
```
→ 零命中(exit 1)。

```
grep -n "rel_max_abs_diff" pipeline/train/train_causal_share.py
```
→ 6 处命中(计算、判定、写报告、失败信息各处)。

```
grep -n "hidden_scale\|rel_maxdiff_hidden" pipeline/train/train_causal_tool.py
```
→ 零命中(exit 1),没有起第二个名。

「不传新参数时两个脚本的判定与改前相同」——见上面第二轮
`TestMainSmokeCPU`/`TestAlignRulesShare`/`TestAlignRulesTool` 三种规则里
`abs`(默认值)分支的通过结果,以及手工过一遍的 diff:`abs_ok` 的表达式与
改前 `pass_ok` 逐字节相同,`train_causal_tool.py` 的 `abs` 分支
`max(d_h, d_l) < tol` 也没有改动一个字符。

`run.py` 本工单没有改动,不涉及注册表,没有跑 `run.py selfcheck`。

## 三、commit 清单

- `f7e833f` T09: 对齐检查门槛全部参数化,加相对判据 --align-rule {abs,rel,both}
  ——`pipeline/train/train_causal_share.py`、`pipeline/train/train_causal_tool.py`
- `ebbf4e2` T09: 加 tests/test_align_rules.py 测对齐判据参数化,补 drift 用例的新属性
  ——`tests/test_align_rules.py`(新)、`tests/test_share_trainer.py`

## 四、自查发现与存疑

- `test_baseline_factor_zero` 这条用例:实测这个手造小模型上
  `max_abs_diff` 恰好是 `0.0`(fp32 CPU 上新旧两条路径对这几个手造事件算出
  的逐行 ce 完全相同,浮点误差在这个规模的模型/数据上没有暴露出来),所以
  `--align-baseline-factor 0` 时 `baseline_warn` 实测是 `False`
  (`0.0 > max(0, 1e-6)` 为假)。用例按工单第 1 条最后一句的条件分支处理
  (差 > 1e-6 才断言 `baseline_warn` 为真,否则退而断言 `baseline_factor`
  键忠实记录传入值),两条分支代码都在,但当前这份手造数据只覆盖到了后一条
  分支——`baseline_warn=True` 的那条分支没有被这批数据实际执行到。这是工单
  原文预见到的情况,不是遗漏,但如实记录。
- `--align-tok-tol` 等六个新参数的默认值助记与「一物一源」的检查:确认
  `run_align_check` 内部三处旧常量引用已经全部替换,`main()` 里没有另开一份
  默认值字典。
- `ALIGN_CHECK.json` 的键顺序:Python 3.7+ dict 保序,新键全部追加在原有键
  之后,`json.dumps` 输出顺序与源码里 `dict(...)` 的书写顺序一致,不影响任何
  现有按键名读取的代码(`gates.md` 只读 `PASS`,回写工单 12 会处理)。
- 没有发现需要 `NEEDS_CONTEXT`/`BLOCKED` 的缺口,工单本身没有歧义。
