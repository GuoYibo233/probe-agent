# T02 报告 —— ctool 的丢弃规则、默认值、读取位置规则、日志

工单:`.scratch/kvshare-train/issues/02-ctool-drop-readpos.md`
分支:`ticket/2026-08-28-wave2/T02`(工作树 `new1-wt/2026-08-28-wave2-T02`,base `2216c44`)

## 一、做了什么(对照工单逐条)

### 1. 丢弃规则(spec 11.1)

- `pipeline/train/train_causal_tool.py` 的 `load_events` 加了 `tok`、`max_len`
  两个参数:分组、前缀性质抽查、`rows` 字段清理之后,对每个事件算
  `len(tok(e["full"], add_special_tokens=False)["input_ids"])`,超过 `max_len`
  就丢并计数;之后再走 `limit`/`spot` 的取子集逻辑。返回值从 `events` 改成
  `(events, dropped)`。
- `main()` 里 val、train 两次调用都传了 `tok, args.max_len`;`start` 事件加了
  `dropped_events_train=dropped_events_train, dropped_events_val=dropped_events_val`。
- `collate`(原第 137~138 行)与 `align_check`(原第 209~210 行)的
  `truncation=True` 改成 `truncation=False`。
- `n_bound_dropped` 字段保留,`step`/`eval` 事件照旧写;`collate` 里对应的
  注释改成"找不到读取位置的切点数(n_bound_dropped),预期 0"。

### 2. 默认值(spec 11.2)

- `--max-len` 4096 → 8192。
- `--accum` 8 → 2(`--bs` 仍是 4,一次更新 8 个事件)。
- `--epochs` 默认值 3 未动(工单要求"不变")。
- 顶部模块 docstring 的"截断"一节改写成"上限"一节,反映新行为(不截断、
  整条丢超长事件、`n_bound_dropped` 现在恒为 0 的读取位置口径);argparse
  里这两个参数本来就没有带数字的 `help=` 文本,没有需要另外同步的地方。

### 3. 读取位置规则(spec 11.3)

- `train_causal_tool.py` 顶层加了 `import share_data`(与 `lora_util`、
  `readonly_map` 同一处、同种写法,不需要额外 `sys.path.insert`,因为
  `share_data.py` 本来就和它同目录)。
- `collate` 里原来 `for t in range(keep-1, -1, -1): if 0 < ends[t] <= b: ...`
  的循环体整段删掉,改成 `j = share_data.read_position(offsets_i, full, b, keep)`;
  `keep = int(enc["attention_mask"][i].sum())` 保留、作为第四个实参传入;
  `if j < 0` 的守卫原样保留(`dropped += 1`)。
- `eval_tool.py` 顶层在 `import readonly_map` 后面加了一行
  `import share_data`(复用同一条 `sys.path.insert`)。`score_causal` 里同样
  的循环体删掉,改调 `share_data.read_position(offsets_i, full, b, keep)`;
  `if j < 0: n_oow += 1; continue` 原样保留。`_full` 改名成 `full`(要传给
  `read_position` 当 `full_text` 用)。
- `align_check` 没有切点循环,只改了第 209 行(现文件里的对应位置)的
  `truncation`,和第 1 条共享同一处编辑。
- `eval_tool.py` 的左截断(`score_causal` 里 `truncation=True,
  max_length=max_len`)原样未动(spec 11.5)。

### 4. 日志(spec 11.4)

- `step` 事件加了 `lr=sch.get_last_lr()[0]`。
- `loss` 字段:核对了现有实现——`run` 在每次写日志(`gstep % 50 == 0`)后就
  清零、每个小批的 loss 都累加进 `run`,写日志时除以 `50 * args.accum`,这
  本来就是"自上一条 step 以来全部小批损失的平均,累加器写完清零",不需要
  再改计算逻辑,只补了 `lr` 这一个新字段。

### 5. 测试 `tests/test_ctool_readpos.py`

四个类,对应工单 (a)~(d):

- `TestReadPositionManual` + `TestCollateReadPosition`:(a)手造 offsets 直接
  验 `share_data.read_position`;真实 Qwen 分词器上一个事件,验证
  `train_causal_tool.collate` 读出的列下标与直接调
  `share_data.read_position` 的结果一致(`'Spotify."\n\nWe are done here
  now.'`,切点 10,预期覆盖 `'."\n\n'` 的 token)。
- `TestLoadEventsDropCount`:(b)一短一长两个事件,长事件全文 token 数
  > max_len,断言 `dropped == 1`、返回事件数 1、保留的是短事件。
- `TestTrainEvalReadPositionAgree`:(c)同一全文、四个上限以内的切点,
  分别过 `train_causal_tool.collate` 与 `eval_tool.score_causal`,用
  monkeypatch `share_data.read_position`(两个模块 import 的是同一个模块
  对象,已用 `train_causal_tool.share_data is eval_tool.share_data` 验证)
  录下 `(cut, j)` 序列,断言两边完全一致。
- `TestScoreCausalOutOfWindow`:(d)构造一个全文 token 数超过 `max_len` 的
  事件(触发左截断),一个切点落在被截掉的开头部分、一个切点是全文末尾;
  `head` 权重清零、偏置定值 1.0,直接从输出张量本身判断"这一行有没有被
  gather 过"——窗口外那行输出 0.0(未 gather),窗口内那行输出 1.0(gather
  到 bias),对应 `n_oow` 计数与 `cols` 收录的分野。

`score_causal` 需要真实的 `backbone`/`head` 对象才能跑,为避免为一个纯逻辑
测试去加载整个 Qwen 模型,写了一个 `_StubBackbone`(只返回形状正确的全零
`last_hidden_state`),因为这几条测试只关心读取位置选中的列下标,不关心
gather 出来的隐状态数值本身。

## 二、怎么验证的

```
cd new1-wt/2026-08-28-wave2-T02
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
```
Ran 6 tests in 1.144s
OK
```
(有一条 `UserWarning: max_length is ignored when padding=True and there is no
truncation strategy` 和一条 `ResourceWarning: unclosed file`,都记在下面「自
查发现」里,不算测试失败。)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m py_compile \
  pipeline/train/train_causal_tool.py pipeline/eval/eval_tool.py
```
```
(无输出,退出码 0)
```

硬门(mbert-env,真 import 不许 try/skip 兜):
```
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/eval'); import eval_tool; print('ok')"
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/eval'); import eval_mbert_call; print('ok')"
```
两条都打印 `ok`,退出码 0(各有一条 transformers 自己的
`TRANSFORMERS_CACHE` `FutureWarning`,与本工单无关)。

`git diff` 范围核对(acceptance 第 4 条):
```
git diff -- pipeline/eval/eval_tool.py
```
只有两处:顶层加 `import share_data` 一行;`score_causal` 里原来的切点定位
循环换成 `share_data.read_position` 调用。`score` 函数(mbert 分类头路径)、
`main()` 里的左截断设置等一个字没动。

全量回归(确认没有引入新失败):
```
python3 -m unittest discover -s tests -v          # 系统 python3
```
```
Ran 357 tests in 8.678s
FAILED (failures=1, errors=1, skipped=19)
```
唯一的 failure(`test_no_env_reads_default_preset`)和唯一的 error
(`test_splice_replay`)都是既有的、与本工单无关的失败——`test_splice_replay`
是仓库记忆记过的"要 cprobe-env 才过"的用例,`test_no_env_reads_default_preset`
是工单 01 收账报告里已经记录过的既有失败(预设那批,未深查)。本文件新增的
`test_ctool_readpos` 在系统 python3 下按预期整模块 `skipped`。

```
cprobe-env/bin/python -m unittest discover -s tests -v
```
```
Ran 415 tests in 11.847s
FAILED (failures=1, skipped=16)
```
同一条既有失败(`test_no_env_reads_default_preset`),`test_ctool_readpos` 的
6 条全部实跑通过。

```
python3 run.py selfcheck
```
```
selfcheck: 74 任务 / 4 配方 / 3 预设, 16 处缺失
```
16 处缺失全是这个工作树里没有的 gitignore 掉的解释器/venv 目录(cprobe-env、
mbert-env、envs/* 等),是新建工作树的正常现象,不是本工单改动引入的问题
(本工单没有碰 `run.py` 或注册表本身)。任务/配方/预设计数与主仓最近一次
selfcheck 记录的数字一致。

## 三、commit 清单

- `40cbd8d` T02: train_causal_tool.py 加事件级丢弃规则、读取位置改走
  share_data.read_position
- `b6a3a51` T02: eval_tool.py score_causal 的读取位置改走
  share_data.read_position
- `479b887` T02: 加测试 tests/test_ctool_readpos.py(读取位置与丢弃计数)

分支起点(base)`2216c44`,分支末端(head)`479b887`。

## 三之二、给工单 04 的 MAP.md 文案

工单验收第 4 条要求 MAP.md 本工单不动、由工单 04 写,这里按验收原文给出的
三个要点(上限 8192 超长事件整条丢弃;一次更新 8 个事件;读取位置读跨切点的
空白 token)给出建议文案,供工单 04 采用或改写:

> 上限 `--max-len` 默认 8192(事件全文 token 数超限整条丢弃,不再截断,计数
> 进 `dropped_events_train`/`dropped_events_val`);读取位置规则用
> `share_data.read_position`,切点落在两个 token 之间的空白字符时读跨切点、
> 归到前一个 token;`--bs 4 --accum 2`,一次更新 8 个事件

## 四、自查发现与存疑

1. **`collate`/`align_check` 里 `max_length=max_len` 参数在 `truncation=False`
   下已经不生效**——HF tokenizer 会打一条一次性 `UserWarning`("max_length
   is ignored when padding=True and there is no truncation strategy"),测试
   跑的时候实测确认了这条警告确实会出现。工单原文只要求把 `truncation=True`
   改成 `truncation=False`,没有要求同时删掉 `max_length` 这个已经变成摆设
   的参数,所以我按字面只改了 `truncation`,把这条观察记在这里——是否要在
   后续工单里顺手把这两处的 `max_length=max_len` 也删掉,由主会话/后续工单
   判断。
2. **`build()` 里 `tok.truncation_side = "left"` 现在也是摆设**——因为
   `collate`/`align_check` 都不再截断了,这行设置不会再影响任何行为。工单
   没有点名这一行,没有动它。
3. **`load_events` 里 `for line in open(path):` 没用上下文管理器**——这是
   改动之前就有的写法(不是本工单引入的),测试里跑到这条路径时 Python 会打
   一条 `ResourceWarning: unclosed file`。工单范围内没有要求改这个,没有动。
4. **`python3 -m unittest tests.test_ctool_readpos`(不加 `discover`)在
   mbert-env 下会以退出码 1 崩溃**,而不是干净地跳过——这不是本工单测试写法
   的问题,是 Python `unittest` 本身的行为:`loadTestsFromName`(直接点名单
   个模块时走的加载路径)不会把模块导入期抛出的 `SkipTest` 当成正常跳过处理,
   只有 `unittest discover` 才会正确识别成 `ModuleSkipped` 并报
   `OK (skipped=N)`。用同样的手法逐一验证过:`tests/test_cparam_assembly.py`
   和 `tests/test_share_data.py`(工单 01 已收账合并的文件)在 mbert-env 下
   用 `-m unittest tests.<module>` 直接点名跑,同样会崩成退出码 1——这是这
   三个文件共有的既有行为,不是本工单引入的回归。工单验收原文写的是
   "两个环境都过",我按 discover 模式(`OK (skipped=1)`)与两条硬门 import
   检查(`import eval_tool`/`import eval_mbert_call` 打印 `ok`)核验过 mbert-env
   侧不会造成真实故障;是否需要因为这条 unittest 自身的行为去改测试运行方式
   (比如统一改用 discover),留给主会话判断。
5. **`step` 事件里的 `lr` 没有做四位小数的 `round()`**——工单原文给的表达式
   就是 `sch.get_last_lr()[0]`,同一行里 `loss`/`ips` 都有 `round(...,4)`,
   我按字面没加 round,直接写了原始 float。`json.dumps` 能正常序列化,不影
   响正确性,只是精度显示上和同一条日志里其他字段不一致,记在这里供参考。
