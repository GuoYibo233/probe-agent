# T08 报告——新训练器加回生成式评估:`--gen-eval N`(默认 200)与 `--gen-bs`

工单:`.scratch/kvshare-train/issues/08-gen-eval.md`
Spec:`.scratch/kvshare-train/spec.md` 16.3(做法)、16.9(测试)、16.10 #29 #30(静默失败点)
分支:`ticket/2026-08-28-wave5/T08`(工作树 `new1-wt/2026-08-28-wave5-T08`,已删除,分支保留)
base:`07907db08b50d66c1c193588f22b5cc97b24b4b3`
head:`b8a31f2`(`375acf5` → `05ca1b3` → `b8a31f2`)

## 一、做了什么(对照工单逐条)

### 1. `share_data.load_events` 行元组加第 6 位

- cgen 分支:`tgt_str = r["label_call"]`、`tool = None`(cgen 分支本来就没
  有 `tgt_str` 变量,直接对 `r["label_call"]` 分词加 eos,现在只是先把这个
  字符串存进一个变量名再传给 `tok(...)`,不改分词逻辑本身)。
- cparam 分支:`tool = r["label"]`(`tgt_str` 已经是现成变量,`param_target`
  返回 None 的行仍旧整条丢弃、计入 `assembly_mismatch`,这条判断在赋值
  `tool` 之前,顺序不变)。
- `rows.append(...)` 末尾加 `gen = dict(tgt=tgt_str, tool=tool)` 当第 6
  位,第 0 到 5 位(`sent_idx, text, p, seg_ids, seg_lab, w`)一个都没动。
- `pack_event` 里六名字的拆包 `_sent_idx, _text, p, seg_ids, seg_lab, _w =
  row` 改成 `= row[:6]`,7 位元组不再 `ValueError`。
- `share_data.py` 第 214/215 行(`prefix_len`/`packed_len` 按下标读
  `row[2]`/`row[3]`)、`train_causal_share.py` 第 179/470/789 行(按下标读
  `row[5]`/`row[1]`)按下标访问,7 位元组下行为不变,未改动。
- 文档字符串同步更新 `rows` 的元组形状说明。

### 2. 测试里手造行元组的地方补第 6 位

- `tests/test_share_data.py`:`_toy_event()` 的 3 行、`test_batch_mask` 里
  手造的 `ev_b` 单行,各补一个 `dict(tgt="", tool=None)` 占位(这两处不测
  生成式评估,占位值不影响原有断言)。
- `tests/test_share_data.py` 的 `TestPrefixRule._check_mode` 对真实
  `share_data.load_events` 返回值的六名字拆包
  `for sent_idx, text, p, seg_ids, seg_lab, w in ev["rows"]:` 改成七名字
  (加 `_gen`)——工单没有点名这一行,但它拆包的是真实 `load_events` 输出,
  行元组变 7 位之后不改就会 `ValueError`,连带修了。
- `tests/test_share_trainer.py`:工单点名的第 374/437/495 行附近实际是
  `W = sum(row[5] for ev in events for row in ev["rows"])`——按下标读,不是
  手造元组,7 位元组下行为不变,核实后未改动这个文件(细节见第四节自查)。

### 3. `train_causal_share.py` 加三个参数

`--gen-eval`(int,默认 200,0 关闭)、`--gen-bs`(int,默认 8)、
`--gen-eval-at`(`choices=["all","last"]`,默认 `last`),三个都紧跟在
`--log-every` 之后。

### 4. 抽样:`sample_gen_eval_rows(events, mode, seed, n)`

`ev_events` 加载完之后立刻调用(在 `readonly_env` 审计块之前),按事件加载
顺序、行按事件内 `sent_idx` 顺序摊平成一个列表(不过滤),
`random.Random(seed).shuffle` 后取前 `n` 行(`n` 大于行数就全取,Python
切片天然处理),再按 `mode` 打包:cgen `(text, None, None, tgt)`,cparam
`(text, None, None, tool, tgt)`(`tgt`/`tool` 取自行元组第 6 位的 `gen`
字典)。`seed` 用的是 `SEED = train_causal_callgen.SEED`(=42,同旧训练
器)。独立于 main() 之外的纯函数,方便单测。

### 5. 生成:调旧脚本 `eval_gen`,不写新函数

`grep -n "def eval_gen" pipeline/train/train_causal_share.py` 零命中——按
`args.mode` 调 `train_causal_callgen.eval_gen` 或
`train_causal_param.eval_gen`,两个旧函数自己处理
`padding_side`/`use_cache`/`model.eval()`/`model.train()`。调用点在
`eval_ce` 之后、写 `eval` 事件之前,不在 `_attn_ctx` 上下文里(第 7 条的
守卫测试钉住这一点)。

### 6. 日志

- `eval` 事件:`do_gen = args.gen_eval > 0 and (args.gen_eval_at == "all"
  or frac == E)` 成立时才加 `val_exact_call`(cgen)/`val_exact_params`
  (cparam)、`gen_n`(`len(gen_rows)`)、`gen_s`(`round(经过秒数, 2)`);不
  成立(`--gen-eval 0`,或 `--gen-eval-at last` 下非 epoch 末评估点)时三
  个键都不写。
- `start` 事件加 `gen_eval`、`gen_bs`、`gen_eval_at` 三个键,放在
  `log_every` 键之后(见第四节「工单内部两条要求不一致」的说明)。
- `save_best` 判据没动,仍只看 `val_ce`。
- `train_s` 的计时代码(`epoch_train_s += time.time() - t0`)没有触碰,
  生成时间不计入。

### 7. 评估段心跳

`eval_ce` 加可选参数 `beat=None`,块循环 `for i, blk in
enumerate(blocks):` 里 `(i + 1) % 25 == 0` 时调一次;主流程调用点传
`beat=lambda: heartbeat.emit(gstep, steps, "step")`;`do_gen` 为真时在调
`eval_gen` 之前、之后各再发一次同样的心跳。`heartbeat.emit` 只传
`(gstep, steps, "step")` 三个位置参数,没有传别的关键字。

### 8. 测试(新文件 `tests/test_share_gen_eval.py`)

不追加进 `test_share_trainer.py`(工单 09/10 并行往同一文件末尾加用例会
撞)。全部用手造小事件(每事件一行,`label`/`label_call` 互相匹配,cgen/
cparam 都能干净装载)与随机初始化小模型(`_tiny_config`,从
`tests.test_share_trainer` import),不读 `pipeline/data/nyapass_aw_v1/
gptoss`(spec 16.9 前言)。真实分词器只用来分词/建模型词表。

- `TestGenEvalEndToEnd`(对应 (a)(b)):12 个训练事件 + 6 个 val 事件,
  `--events-per-mb 4 --accum 2 --eval-per-epoch 2` 给出两个不同的评估点
  (`frac=1` 与 `frac=2`)。cgen/cparam 各三个用例:`--gen-eval-at all` 下
  两条 `eval` 都有三个新键且 `gen_n==3`;`--gen-eval-at last` 下只有
  `frac==2` 那条有;`--gen-eval 0` 下两条都没有。
- `TestSampleGenEvalRowsDeterministic`(对应 (c)):同一批 `events` 调
  `sample_gen_eval_rows` 两次结果相同(cgen/cparam 各一个用例);另一个
  用例验证 `n` 大于行数时取全部。
- `TestAttnCtxOnlyInForwardPacked`(对应 (d)):`ast` 解析
  `train_causal_share.py` 源码,遍历 `Call` 节点找 `_attn_ctx(...)`,记录
  每次调用所在的最近 `FunctionDef` 名字,断言全部是 `_forward_packed`
  (`def _attn_ctx` 那一行本身是 `FunctionDef` 不是 `Call`,不会被计入)。
- `TestEvalCeBeat`(对应 (e)):30 个 val 事件,`tok_budget` 取
  「全部事件补齐长度里最小的那个」——这样任意两个事件的 `cand_max` 都
  `>= tok_budget`,`2 * pad16(cand_max) > tok_budget` 恒成立,保证每个
  事件独自成一个物理块(30 块 >= 25);断言 `beat` 至少被调用一次。另一个
  用例验证 `beat=None`(默认)不报错。

## 二、怎么验证的

```
cd new1-wt/2026-08-28-wave5-T08
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest \
  tests.test_share_gen_eval tests.test_share_trainer tests.test_share_data
```
输出:`Ran 33 tests in 20.219s` / `OK (skipped=9)`(跳过的是要真实分词器
路径不存在、或 `peft` 未装的用例分支,和改动前的跳过原因一致)。

单独跑新文件(`-v`)也全绿:
```
Ran 12 tests in 19.488s
OK
```

```
grep -n "gen_eval\|val_exact_" pipeline/train/train_causal_share.py
```
命中 `sample_gen_eval_rows` 定义、`gen_rows` 赋值、`start_kw` 里的
`gen_eval`/`gen_bs`/`gen_eval_at`、`do_gen` 判据、`exact_key` 三处。

```
grep -n "def eval_gen" pipeline/train/train_causal_share.py
```
零命中(退出码 1)。

工单验收清单原样命令,用真实 `--base qwen` 0.6B 底座、真实现役数据集
`pipeline/data/nyapass_aw_v1/gptoss`,CPU 上跑:
```
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --base qwen --data pipeline/data/nyapass_aw_v1/gptoss \
  --out <out> --smoke --max-events 6 --gen-eval 3 --gen-bs 2 --device cpu
```
`ALIGN_CHECK.json`:`PASS: true`(`max_abs_diff` 2.38e-06,`tol` 2e-05)。
`train_log.jsonl` 的 `eval` 事件:
```
{'event': 'eval', 'ep': 0, 'frac': 4, 'gstep': 1, 'val_ce': 1.2026,
 'n_eval_rows': 18, 'val_exact_call': 0.0, 'gen_n': 3, 'gen_s': 3.38,
 't': 1787923369.9}
```
三个新键(`val_exact_call`、`gen_n`、`gen_s`)都在,`gen_n == 3` 与传入的
`--gen-eval 3` 一致。`start` 事件里 `gen_eval: 3, gen_bs: 2, gen_eval_at:
'last'` 三个键都在。`done` 事件 `wall_s: 13.91`(训练+评估本身很快,耗时
主要在开训前的对齐检查——CPU 上用真实 0.6B 模型做 fp32 前向,这段代码
本工单没有改动,过程中花了十几分钟,与本工单改动无关)。

`git status --porcelain`(工作树内)只有:
```
 M pipeline/train/share_data.py
 M pipeline/train/train_causal_share.py
 M tests/test_share_data.py
?? tests/test_share_gen_eval.py
```
没有碰 `run.py`、`train_causal_callgen.py`、`train_causal_param.py`。

## 三、commit 清单

- `375acf5` T08: share_data 行元组加第 6 位 gen 字典,pack_event 拆包适配
- `05ca1b3` T08: train_causal_share 加 --gen-eval/--gen-bs/--gen-eval-at
- `b8a31f2` T08: 自查修复——去掉 test_share_gen_eval.py 里没用到的 random 导入

## 四、自查发现与存疑

1. **工单内部两条要求不完全一致,已按更完整的一条实现,记在这里供收账
   裁决**:工单第 2 条说「`start_kw` 字典里本工单加 `gen_eval / gen_bs`
   两个键」(只提两个),第 5 条说「`start` 事件加 `gen_eval`、`gen_bs`、
   `gen_eval_at`」(三个)。spec 16.3 原文也只写两个键。三处测试(点 7)
   都不检查 `start` 事件的具体字段数,所以两种实现都不会让验收判据变红。
   我按第 5 条(更完整、专门讲日志字段的一条)实现,`start_kw` 里加了
   `gen_eval`、`gen_bs`、`gen_eval_at` 三个键——如果 gyb 的意图是只加两个
   (比如 `gen_eval_at` 留给别处或者不落日志),需要主会话收账时改掉这一处
   (`train_causal_share.py` 里 `log_every=args.log_every,` 那一行往后数
   一行)。
2. 工单第 1 条点名 `tests/test_share_trainer.py` 第 374/437/495 行附近
   「手造行元组」要补第 6 位,核实后这三处是 `row[5]`(按下标读取真实
   `load_events` 输出),不是手造元组,7 位元组下行为不受影响,所以没有
   改这个文件。已跑过 `tests.test_share_trainer` 全绿确认。
3. `--smoke` 下真实 0.6B `--base qwen` 模型在 CPU 上跑对齐检查很慢
   (fp32、`REF_BATCH=4` 与 `bs=1` 单行基线两遍、加 `_new_forward`,CPU 无
   GPU 加速,`bs=1` 那一遍是逐行各跑一次整模型前向),实测这一段花了十几
   分钟才打印出第一行 `ALIGN_CHECK.json`——这是 `run_align_check` 现有
   逻辑(本工单没有改动这段代码),不是本次改动引入的新开销。跑完之后
   `PASS: true`,`train_log.jsonl` 里三个新键齐全,结果见第二节。
