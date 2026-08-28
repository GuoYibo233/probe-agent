# T07 报告:评测端超长事件的三种处理

工单:`.scratch/kvshare-train/issues/07-eval-overlong.md`
spec 段落:16.2(判据)、16.9 第一条(测试)、16.10 #28/#33/#34/#35(静默失败点)
分支:`ticket/2026-08-28-wave5/T07`,base `07907db08b50d66c1c193588f22b5cc97b24b4b3`,head `19f2c703062ea43ad17cd192f17790571d9300b6`

## 一、做了什么(对照工单逐条)

### 1. `share_data.py` 抽函数(工单第 1 条)

- `full_token_ids(tok, full_text)`:`load_events` 第 145-147 行那次全文分词原样抽出(`add_special_tokens=False, truncation=False`)。
- `n_full_tokens(tok, full_text)`:`return len(full_token_ids(tok, full_text))`。
- `load_events` 改调 `full_token_ids`,行为逐字节不变(分词次数、结果都不变)。
- `train_causal_tool.load_events` 第 128 行改调 `share_data.n_full_tokens(tok, e["full"])`——原来的调用没写 `truncation=False`,但没传 `max_length` 时 tokenizer 默认本来就不截断,数值不变。
- `event_full_texts(rows) -> dict[event] -> full_text`:按 event 分组,取 `sent_idx` 最大那行的 `text`,不过滤行、不动 `load_events` 里 `events_all.append(dict(...))` 那段分组。
- `select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new) -> (kept_keys, counts)`:见下面的设计说明。

四个新函数放在 `_pad16`(第 60 行)之后、`load_events`(原第 73 行)之前,没有碰工单点名"别动"的区域。

### 2. `eval_causal_call.py` / `eval_causal_param.py` 加 `--overlong`(工单第 2 条)

两个脚本都加 `--overlong {left,skip,drop-event}`,默认 `left`。三步顺序写死:readonly 排除(不变)→ `--overlong` 筛选(分词器加载之后,调 `share_data.select_keys`)→ `--limit`(位置从筛选之前挪到筛选之后)。`n_events_fired` 仍在筛选之前算,原义不变。

- `L(k)` 的分词口径与 `generate()` 一致(`add_special_tokens=False, truncation=False`);cparam 对 `gt_tool`/`pred_tool` 两套提示各算一遍,取最大值。
- `drop-event` 只对 `keys` 里的事件调 `event_full_texts`/`n_full_tokens`,不对全集分词。
- 两份报告(JSON+MD)都加 `overlong_mode` 与 `n_left_truncated/n_skipped_rows/n_dropped_events/n_excluded_by_ctool` 四个计数;cparam 另加诊断键 `n_left_truncated_by_tag = {"gt_tool": n, "pred_tool": n}`。
- `--self-fire` 路径未改动。

**与 ctool 的衔接**:读 `ctool_run/logits_test.meta.json` 的 `excluded_idx`(键不存在按空列表),按事件分组成 `dict[event] -> [row_idx,...]` 传给 `select_keys`;`select_keys` 内部对每个 key 检查"候选行是否全部被 ctool 剔除",全部被剔的 key 不判分、计入 `n_excluded_by_ctool`。

### 3. `eval_tool.py` 的 `score_causal` 与主流程加 `--overlong`(工单第 3 条)

`score_causal(..., overlong="left")` 现在返回 `(out, excluded_idx, counts)`(`counts` = `n_oow/n_skipped_bounds/n_dropped_events/n_dropped_bounds`,工单原文只写了 "(out, excluded_idx)" 两元,我把 `counts` 作为第三个返回值加了进去——`n_oow` 与另外三个 mode 计数都要写进 REPLAY_REPORT,`score_causal` 是唯一算出这些数的地方,不加第三个返回值就没法把这些数带出来;这一处是我的设计判断,列进下面的"自查发现与存疑"里)。

- `left`:不变,`n_oow` 只是诊断计数。
- `skip`:窗口外边界(`read_position` 返回 -1)进 `excluded_idx`,计 `n_skipped_bounds`。
- `drop-event`:`n_full_tokens(tok, 全文) > max_len` 的事件(用 ctool 训练器自己的规则——`rows` 在 `main()` 里已经按 `label in label2id` 过滤过,`items[-1][2]["text"]` 就是同一条"先过滤再取最后一行"规则)整个跳过分词/前向,全部边界记零 logits 进 `excluded_idx`。幸存事件的全文没被截断过,`n_oow` 恒为 0。
- `main()` 加 `--overlong`,只对 `--head causal` 生效,`--head mbert` 传非 `left` 直接 `SystemExit`(检查点在参数解析之后、任何文件访问之前)。
- `logits_*.meta.json` 新增 `overlong_mode`、`excluded_idx`,以及(causal 头下)`n_oow/n_skipped_bounds/n_dropped_events/n_dropped_bounds` 四个计数(后者是我为了让 `--cached-logits` 也能把这些数写进 REPLAY_REPORT 而加的,工单没有明写这四个键要不要落盘,见下面的存疑)。mbert 头恒写 `overlong_mode: "left"`、`excluded_idx: []`。
- `--cached-logits` 路径:读回 `overlong_mode`,与本次 `--overlong` 不同(或缺键而本次非 `left`)就 `SystemExit` 并写明两种模式;相同就照常,并读回 `excluded_idx`/四个计数。
- 每个 split(val/test)装载完 `rows`/`logits` 之后,按 `excluded_idx` 剔行再存进 `splits[sp]`——温度拟合、θ 扫描、test 冻结、stop-time 校准、深度桶 acc、先验基线、`token_cost`、`readonly_stats` 全部下游都吃剔行之后的数据。`logits_*.pt` 落盘时仍是全行数(剔除的行留零 logits),不影响 cgen/cparam 的下标对齐断言。
- `REPLAY_REPORT.json/.md` 加 `overlong_mode` 与四个计数,固定取 **test 堆**的数(val 堆的 `overlong_mode`/计数也写进它自己的 `logits_val.meta.json`,但不进 REPLAY_REPORT——这是我的取舍,工单没有明说 REPLAY_REPORT 的计数该是哪个堆的,见存疑)。

## 二、怎么验证的

```
$ /home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_eval_overlong tests.test_share_data tests.test_ctool_readpos
...
Ran 39 tests in 6.410s
OK (skipped=1)
```

(1 个 skip 是 `tests/test_share_data.py` 里需要现役 `pipeline/data/nyapass_aw_v1/gptoss/val.jsonl` 的用例——该目录 gitignore,worktree 里没有,主仓有;不是回归。)

```
$ grep -n "full_token_ids\|n_full_tokens" pipeline/train/share_data.py pipeline/train/train_causal_tool.py \
    pipeline/eval/eval_tool.py pipeline/eval/eval_causal_call.py pipeline/eval/eval_causal_param.py
```
五个文件全命中。

```
$ grep -n 'tok(e\["full_text"\]' pipeline/train/share_data.py   # 零命中
$ grep -rn "def select_keys" pipeline/                          # 只命中 share_data.py 一处
```

三个评测脚本 `--help` 都列出 `--overlong {left,skip,drop-event}`,默认 `left`(实测截图见对话记录,三份 `--help` 输出都带这一行)。

```
$ /home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest discover -s tests
Ran 431 tests in 17.867s
FAILED (failures=1, skipped=24)
```
唯一失败 `test_no_env_reads_default_preset` 是 `tests/test_preset.py` 里硬编码了 `/home/y-guo/reproduce/new1/configs/presets/default.json` 这个绝对路径去比对,在本工作树(`new1-wt/2026-08-28-wave5-T07`)下自然对不上——用 `git stash` 验证过:不改任何代码时这条用例在本工作树里同样失败,与本工单无关。

```
$ python3 run.py selfcheck
selfcheck: 76 任务 / 4 配方 / 3 预设, 16 处缺失
```
16 处缺失全是 venv/env 目录(`envs/*/venv`、`cprobe-env`、`mbert-env` 等),这些目录 gitignore、只在主仓存在,工作树里没有——本工单不改 `run.py`,主仓跑同一条命令是 `全部就位`,已用主仓验证过,不是回归。

## 三、commit 清单

- `74d38f6` T07: share_data 抽 full_token_ids/n_full_tokens/event_full_texts/select_keys
- `75e212c` T07: eval_tool.py score_causal 加 --overlong 三态,cached-logits 校验模式
- `7d2c961` T07: eval_causal_call/eval_causal_param 加 --overlong,接 ctool 剔除
- `19f2c70` T07: 新测试 tests/test_eval_overlong.py

## 四、自查发现与存疑

1. **`select_keys` 的 `keys` 参数形状是我做的裁决,不是照抄工单原文**。工单写 `select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new)`,只说 `n_full`/`prompt_len` 是"按 key 查的字典"、`excluded_rows` 是"ctool 传来的剔除行集合"。工单验收里的 (b) 明确要测"给定 excluded_rows 时的剔除(部分行被剔的事件留下、全部候选行被剔的事件去掉并计入 n_excluded_by_ctool)"——一个事件要能表达"部分行被剔"和"全部候选行被剔"两种情况,`keys` 必须带每个事件的候选行下标,不能只是扁平的 event id 列表。我把 `keys` 定成 `dict[key] -> list[int]`(候选行下标列表),`select_keys` 内部逐 key 检查 `all(i in excluded_rows for i in keys[k])`。三个评测脚本的调用点里,`keys_rowmap = {k: ev_row_idx[k] for k in keys}` 里的候选行是"该事件在 `rows` 里的全部行下标",不是"只到当前触发行为止"——也就是说,如果一个事件的触发行恰好落在 ctool 剔除的行上、但同一事件还有别的候选行没被剔,我这版实现会把这个事件**继续按原来的触发点(`fired[k]["row"]`)判分**,不会去重新在剩下的行里挑一个新触发点。工单原文"一个事件在剩下的行里挑触发点"字面上要求重新挑,但重新挑需要 `probs`/`theta`(`select_keys` 签名里没有这两个参数,拿不到),要做到位得改 `replay_fire` 本身;鉴于项目里实际的 θ 都在 0.9 以上、远高于均匀分布的 `1/n_labels`,"零 logits 的行恰好触发"这个场景概率极低,我选择了只做工单里最具体、最可测的那条判据(候选行剔光就整个不判分),没有额外重挑触发点。这是我做的裁决,不是我看错了工单,想请你确认这个取舍是否可以接受。
2. `score_causal` 从两值返回改成 `(out, excluded_idx, counts)` 三值——工单原文只写 "(out, excluded_idx)"。`counts` 是我加的第三个返回值,因为 `n_oow`/`n_skipped_bounds`/`n_dropped_events`/`n_dropped_bounds` 四个数工单要求写进 REPLAY_REPORT 与 `logits_*.meta.json`,而 `score_causal` 是唯一算出它们的地方,不加这个返回值就传不出来。
3. `logits_*.meta.json` 里除了 `overlong_mode`/`excluded_idx` 之外,我还额外写了 `n_oow`/`n_skipped_bounds`/`n_dropped_events`/`n_dropped_bounds` 四个计数(工单第 3 条列的新增键只写了 `overlong_mode` 与 `excluded_idx`)——这是为了让 `--cached-logits` 路径也能把这四个数带进 REPLAY_REPORT(不这样做的话,走缓存的那次跑不出这几个计数,只能空着或者重新硬算一遍,都不对)。旧缓存(没有这四个键)按 0 处理。
4. `REPLAY_REPORT` 的 `overlong_mode` 与四个计数,我固定取 **test 堆**的数,val 堆各自的数只留在 `logits_val.meta.json` 里、不进 REPLAY_REPORT——工单没有明说该取哪个堆(现有的 `probe_cost_test`/`n_events_test` 等字段本来就是 test-only 的命名惯例,我按同样的惯例处理)。
5. `--overlong skip/drop-event` 下,`val` 堆(拟温度、扫 θ 用)也会按同样的规则剔行(而不是只对 test 堆生效)——工单原文的判据描述集中在 ctool 的 test 堆衔接段,没有明确提 val 堆要不要同样处理;我认为不处理的话,val 堆里残留的零 logits 行会污染温度拟合与 θ 扫描,与 `--overlong` 想解决的问题(零 logits 不该被当真)矛盾,所以我让两个堆都走同一套剔除逻辑。
6. 为了让 `score_causal` 的签名变更不破坏既有测试,我改了 `tests/test_ctool_readpos.py` 两处调用点(工单的文件范围清单里没写这个文件)——这是工单本身要求的验收命令(`tests.test_ctool_readpos` 必须通过)与 `score_causal` 签名变更(工单第 3 条明确要求)两者相加的必然结果,不是我自己扩大范围。
7. `n_dropped_events`(`select_keys`/`score_causal` 两处)用严格 `>` 判 `n_full[k] > max_len` / `n_full_tokens(...) > max_len`,与 `load_events`/`train_causal_tool.load_events` 的判据(同样严格 `>`)口径一致,没有引入新的边界差异。
8. 没有跑到 GPU:这张工单全程是纯 CPU 代码改动 + CPU 单测,不涉及需要显卡的步骤,没有触发 gpu-run 流程。

## 五、修复第 1 轮(2026-08-28,接手自上一轮实现者)

工作树 `new1-wt/2026-08-28-wave5-T07-fix1`,分支仍是 `ticket/2026-08-28-wave5/T07`,
起点(修复前)`19f2c70`,修复后 head `eadb3f8`。收到三条未决 finding,逐条修:

### F1(critical)eval_causal_call.py 未按 spec 16.2 实现"ctool 剔除后重新挑触发点"

**根因**(与自查存疑第 1 条对应,现在给出根因修复而不是维持原裁决):
`fired = replay_fire(rows, probs, ...)`(原第 578 行)在任何剔除之前就用**全部**
行算出来,`keys_rowmap[k]` 传的又是该事件在 `rows` 里的**全部行下标**(含
`fired[k]["row"]` 本身)。触发行的 conf 定义上必然 `>= θ`,而 ctool 剔除的行
过 softmax 是均匀分布 `1/n_labels`,只有 `θ<=1/n_labels` 时才可能撞上——项目
里的 θ 都在 0.9 以上,所以 `all(i in excluded_rows for i in keys[k])` 这条检查
对任何已经进了 `keys` 的事件恒假,`n_excluded_by_ctool` 恒为 0。更根本的是:
如果一个事件的候选行**全部**被 ctool 剔除(比如两行都是真实的零 logits),它
在原始的、未经剔除处理的 `replay_fire` 里本来就不会 `fired`(0.5 类的 conf 过
不了 0.9 的 θ),于是它连"已触发"这一步都进不去——`select_keys` 根本看不到
这个 key,不是"检查它但判定假",是压根没有机会检查。这个事件就这样从
`n_events_fired`、`n_excluded_by_ctool`、`n_events_scored` 三个计数里**同时消失**,
不出现在任何分母里,也不报错。

**修复**(直接覆盖错误逻辑,不打补丁):把 ctool 剔除挪到调 `replay_fire` **之前**——
读 `excluded_idx` 之后,先按事件分组算"候选行是否全部被剔"计
`n_excluded_by_ctool`(这一步在剔除之后,不依赖任何后续的 fired 状态),再把
`rows`/`probs` 按"下标不在 excluded_rows 里"筛一遍(`cand_idx`/`cand_rows`/
`cand_probs`),拿筛过的候选行去调 `replay_fire`。这样触发点天然只从未被剔除
的候选行里挑,不管 θ 与 `1/n_labels` 的大小关系——不是"θ 通常挡得住所以没事",
而是从源头上不让被剔除的行进入候选池。`--overlong` 那一步(第二次调
`select_keys`)因此改传空的 `excluded_rows`:`keys` 里的事件都已经保证至少有
一个候选行没被剔,`select_keys` 自己的剔除分支在这里永远不会再命中,加了
一句 `assert length_counts["n_excluded_by_ctool"] == 0` 钉住这个不变量(断言失败
说明前面的假设被破坏了,不是防御性兜底)。

`eval_causal_call.py` 第 572-607 行(挑触发点)、第 622-650 行(`--overlong`
筛选)。

### F2(critical)eval_causal_param.py 同一缺口

`eval_causal_param.py` 的问题与 F1 逐字同构(`replay_fire` 调用在第 403 行、
`keys_rowmap` 在原第 447 行同样取全部行下标),按同一个根因修复法处理:
第 401-434 行(挑触发点,`ev_row_idx`/`excluded_rows`/`n_excluded_by_ctool` 提前
算好、`cand_idx`/`cand_rows`/`cand_probs` 筛过再调 `replay_fire`)、第 453-486 行
(`--overlong` 筛选改传空 `excluded_rows`,同样断言剩下的 `n_excluded_by_ctool`
恒为 0)。两个脚本的 `select_keys`(`share_data.py`)本身没有改动——它作为纯
函数的行为一直是对的(给定正确的 `keys`/`excluded_rows` 就能正确剔除),问题
从来只在两个评测脚本调用它之前"喂给它什么"这一步。

自查存疑第 4/5 条(`REPLAY_REPORT` 只取 test 堆数字、val 堆也走同一套剔除
逻辑)与本次修复无关,不动;第 2/3/6/7 条(`score_causal` 三值返回、
`logits_*.meta.json` 多写四个计数、`test_ctool_readpos.py` 两处调用点、
`n_dropped_events` 判据)同样不在这次 finding 范围内,原样保留。

### F3(important)新测试没有覆盖 F1/F2 实际所在的接线代码

原来的 `TestSelectKeys` 直接手造 `keys = {"e1": [0, 1], ...}` 这种候选行下标
字典去调 `select_keys`,绕开了两个评测脚本里"从 `rows` 建 `keys_rowmap`、拿
`fired[k]['row']` 当触发点"这段真正的接线——F1/F2 的 bug 就在这段接线里,
孤立单测测不到它。

`tests/test_eval_overlong.py` 新增两个端到端测试类:

- `TestCgenCtoolExclusionWiring`(测 `eval_causal_call.py`)
- `TestCparamCtoolExclusionWiring`(测 `eval_causal_param.py`)

做法:手造真实 Qwen 分词器 + 随机初始化的两层 `AutoModelForCausalLM`(照
`tests/test_lora_merge.py` 的 `tiny_config`/`save_pretrained` 套路存成一个
`<run>/best` 目录),配一份手造的 `ctool` run(`REPLAY_REPORT.json` +
`logits_test.pt` + `logits_test.meta.json`)与一份手造的 `test.jsonl`,把脚本里
的 `generate()` 换成一个"回声"函数(原样返回喂进去的 prompt,不依赖模型真能
写出什么),端到端跑 `eval_causal_call.main()` / `eval_causal_param.main()`,
再读落盘的 `CALLGEN_REPORT.json` / `PARAM_REPORT.json`。

构造三个事件(2 类标签,`θ=0.9`):

- `ev_reselect`:两行,sent_idx 0 被剔除但故意给强自信 logits(`[10,-10]`,
  conf≈1.0)——用来验证"剔除的行不许当触发点候选"这条不是靠 θ 天然挡住的,
  接线本身必须挡;sent_idx 1 没被剔除,logits `[3,-3]`(conf≈0.9975)存活。
- `ev_full_excl`:两行都被剔除,logits 是 ctool 真实产出的零 logits
  `[0,0]`(conf=0.5<0.9)——这正是 F1 指出的"老接线里这类事件连 fired 都进
  不去、从所有计数里静默消失"的场景。
- `ev_normal`:一行,没被剔除,正常触发,当基线对照。

断言 `n_events_test==3`、`n_events_fired==2`、`n_excluded_by_ctool==1`、
`n_events_scored==2`,并从回声报告的 `samples[...]["gen"]` 字段里读出
`ev_reselect` 的生成 prompt——确认它含 "ROW1 SURVIVING TEXT"(重新挑到的那一
行)、不含 "ROW0 EXCLUDED CONFIDENT TEXT"(被剔除的那一行)。

**验证这两个新测试确实会抓住 F1/F2**(不是自娱自乐的绿测):用
`git show 19f2c70:pipeline/eval/eval_causal_call.py`(修复前的版本)临时换上
这两个脚本,单独跑这两个新测试类,两个都在 `n_excluded_by_ctool` 上失败
(`0 != 1`);换回修复后的脚本,两个测试转绿。

## 六、怎么验证的(本轮)

```
$ cprobe-env/bin/python -m unittest tests.test_eval_overlong tests.test_share_data tests.test_ctool_readpos
Ran 41 tests in 7.225s
OK (skipped=1)
```
(41 = 上一轮的 39 + 本轮新增的 2 个端到端测试;跳过的 1 个与上一轮相同,是
`tests/test_share_data.py` 里需要现役数据目录的用例,worktree 里没有那个
gitignore 的目录,不是回归。)

```
$ cprobe-env/bin/python -m unittest discover -s tests
Ran 433 tests in 17.016s
FAILED (failures=1, skipped=24)
```
唯一失败仍是 `tests.test_preset.TestBfclHandlerPreset.test_no_env_reads_default_preset`
(硬编码 `/home/y-guo/reproduce/new1/...` 绝对路径,在本工作树路径下天然对不上,
上一轮已确认与本工单无关,本轮验证依旧如此)。

```
$ grep -n "full_token_ids\|n_full_tokens" pipeline/train/share_data.py pipeline/train/train_causal_tool.py \
    pipeline/eval/eval_tool.py pipeline/eval/eval_causal_call.py pipeline/eval/eval_causal_param.py | wc -l
11   # 五个文件全命中
$ grep -n 'tok(e\["full_text"\]' pipeline/train/share_data.py | wc -l
0
$ grep -rn "def select_keys" pipeline/
pipeline/train/share_data.py:104:def select_keys(...)   # 只此一处
```

三个评测脚本 `--help` 仍列出 `--overlong {left,skip,drop-event}`,默认 `left`
(逐字重跑确认,输出与上一轮报告一致)。

```
$ python3 run.py selfcheck
selfcheck: 76 任务 / 4 配方 / 3 预设, 16 处缺失
```
16 处缺失仍是 venv/env 目录(gitignore,只在主仓,不在本工作树),与上一轮
一致,不是回归。

## 七、commit 清单(本轮)

- `530c997` T07: 修复 F1/F2 ctool 剔除行接线——挑触发点前先剔候选行,重新挑触发点
- `eadb3f8` T07: 补 F3 回归测试——端到端跑 eval_causal_call/param 的接线,不再只测孤立单元

修复后 head:`eadb3f8`。
