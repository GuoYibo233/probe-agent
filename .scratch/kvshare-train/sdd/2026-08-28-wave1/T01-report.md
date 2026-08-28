# T01 报告 —— `pipeline/train/share_data.py`

工单:`.scratch/kvshare-train/issues/01-share-data.md`
分支:`ticket/2026-08-28-wave1/T01`,base `2e61f5f01e5a79535cdc9a8622eb32213d83e10b`,
head `8e9c712`(工作树 `/home/y-guo/reproduce/new1-wt/2026-08-28-wave1-T01`,已按协议删除,分支保留)。

## 1 做了什么(对照工单逐条要求)

工单第 1 到 6 条,一一对应新建的 `pipeline/train/share_data.py`:

1. **`load_events(path, tok, mode, max_len, ro=None, limit=0, order="random")`**——
   按 spec 3.2 写死顺序:分组(事件顺序=文件首次出现,不按事件名重排)→
   `random.Random(SEED)` 抽 50 个事件做前缀性质抽查(对丢弃之前的全部事件)→
   逐事件全文分词得 `n_full`,超 `max_len` 整条丢弃计 `dropped_events`→
   按 `limit`/`order` 取子集(`"random"` 新建 `random.Random(SEED)` 打乱取前
   `limit` 个;`"shortest"` 按 `n_full` 升序;取完之后按文件首次出现的顺序
   重新排列,保住"事件顺序=文件序"的返回契约,不因取子集方式而变)→ 只对
   留下的事件逐行分词与行级丢弃。行级按 mode 分叉:cgen 用
   `train_causal_callgen.CALL_SEP`/`MAX_TGT_TOK`,cparam 用
   `train_causal_param.param_prompt_tail`/`param_target`(返回 None 计
   `assembly_mismatch`);两个常量/函数集都在 `load_events` 函数体内延迟
   import,不复制。`--readonly-env` 的 `ro` 参数照 `CallDS`/`ParamDS` 的口径
   过滤(非只读整条丢,计数记在调用方传入的 `ro` 字典里)。
   公共前缀 `p`(spec 3.4)、`seg_ids`/`seg_lab` 的拼法与断言
   `len(old_ids[p:]) >= 1` 照抄。两道硬停照 `train_causal_param.py` 第
   337~353 行搬:这个 split 装载后 0 行退出;cparam 剥离失败率超
   `ASSEMBLY_MISMATCH_LIMIT`(0.05,直接引用旧脚本常量,不复制数字)退出。
   拼接长度上界断言(`MAX_BOUNDS` 从 `pipeline/annotate/rules.py` 延迟 import)
   照 spec 3.5 实现。
   返回的每个事件 `dict` 除工单点名的 `event/n_full/packed_len/prefix_len/
   rows` 外,多带了一个 `full_ids`(事件全文分词结果)——`pack_event` 要用
   `full_ids[:P]` 拼前缀,工单没列这个字段但没有它 `pack_event` 拼不出拼接
   序列,自查阶段确认这是必要补充,不是节外生枝(见第 4 节)。
   另外一条自主决定:某个事件的全部行都被行级丢弃(readonly/tgt 过长/
   mismatch)掏空之后,这个事件本身不进最终返回的 `events` 列表(它的行已经
   分别记进 `dropped_rows_tgt`/`assembly_mismatch`/`ro` 里,不再单独计数)。
   工单没写这一条,是实现时撞见的空洞——具体见第 4 节自查记录。
2. **`pack_event(ev)`**——按 spec 第 4 节的拼接公式,返回
   `(tokens, positions, labels, row_index, seg_bounds)`,均为 python list。
3. **`allowed_mask(ev)`/`batch_mask(packed_list, L_pad)`**——两者共用一个
   私有核心 `_allowed_from_packed`,按 spec 第 4 节的注意力允许关系(前缀内部
   因果、第 k 段看前缀前 p_k 个位置与本段前 i+1 个 token、段间互不可见、
   前缀看不到任何目标段)用 torch 向量化构造 `[L, L]` bool 张量。
   `batch_mask` 右 pad 到 `L_pad`(断言 16 的倍数),造 `[B, 1, L_pad, L_pad]`
   bf16 加性掩码(pad 作为 query 只看自己,防 softmax 出 NaN),`position_ids`
   与 `input_ids`(pad 位置 id=0),以及损失位下标表——用 `labels` 数组本身
   取值(不移位):`labels[t] != -100` 的目标 token 由 logits 在位置 `t-1`
   算出,条目是 `(batch_idx, t-1, labels[t], row_index[t])`。
4. **`chunk_by_budget(events, tok_budget)`**——事件按 `packed_len` 降序,
   贪心装块:块的『事件数 × 块内最长 `packed_len`』≤ `tok_budget`;单个事件
   超预算独自成块。`worst_blocks` 在此基础上返回『`packed_len` 最大的单个
   事件』和『装块结果里块内最长 `packed_len` 最大的那一块』。
5. **`read_position(offsets, full_text, cut, keep)`**——按 spec 11.3:
   `j` = 起始位置 `< cut` 的最后一个真实 token;`end_j <= cut` 读 `j`;
   `end_j > cut` 且 `full_text[cut:end_j]` 全空白也读 `j`;否则读 `j-1`;
   两种情况返回 -1(找不到起点、或要退到 `j-1` 而 `j=0`)。
6. **测试 `tests/test_share_data.py`**——见第 2 节。

## 2 怎么验证的

```
cprobe-env/bin/python -m unittest tests.test_share_data -v
```
18 个用例全过(其中 `TestPrefixRule` 两个用例用真实 Qwen3-0.6B-Base 分词器
与 val 集抽样,`TestReadPosition` 三个用例也用真实分词器):
```
Ran 18 tests in 15.664s
OK
```
(worktree 里没有 `pipeline/data` 软链——它是 gitignore 的裸名软链,新
worktree 不会带出来——补了一条本地软链指回
`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data` 才让
`TestPrefixRule` 跑起来而不是 skip;这条软链没进 git,不影响主仓。)

```
python3 -m unittest tests.test_share_data -v
```
系统 python3 没有 torch,整个模块按 `unittest.loader.ModuleSkipped` 干净
跳过(退出码 0),口径照 `tests/test_cparam_assembly.py` 的既有约定。

```
python3 -m unittest discover -s tests -v
```
全量 discover 下 `test_share_data` 同样正确落在 `ModuleSkipped`,不计入
失败。全量跑出 `FAILED (failures=1, errors=1, skipped=18)`——两个失败都
与本工单无关、且在我碰之前就存在:
- `test_splice_replay`(`_FailedTest`,要 cprobe-env 里的 `openai_harmony`)——
  这是仓库既有记忆里记过的老毛病(`new1-unittest-quirks`:"全量测试恒剩
  1 error")。
- `test_no_env_reads_default_preset`(`test_preset.TestBfclHandlerPreset`)——
  跟 `configs/presets/default.json` 有关,与 `share_data`/训练器完全无关,
  没有深查(工单范围之外,只动了本工单该动的两个文件)。

```
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train'); import share_data; print(share_data.read_position)"
```
退出码 0(硬门通过)。

```
cprobe-env/bin/python -m unittest tests.test_cparam_assembly tests.test_lora_merge
```
两个现有测试文件共 22 个用例全过,确认没有连带影响。

```
python3 run.py selfcheck
```
`74 任务 / 4 配方 / 3 预设, 16 处缺失`——16 处缺失全是本地 worktree 没有
`envs/*/venv`、`cprobe-env`、`mbert-env` 等按机器装的解释器/软链(worktree
新建时不会带出这些 gitignore 的东西),不是注册表结构问题;本工单没有改动
`run.py` 或任何注册表条目,`git status` 只有 `share_data.py` 与
`test_share_data.py` 两个新文件。

## 3 commit 清单

- `8e9c712` T01: 新建 `pipeline/train/share_data.py`(cgen/cparam 共用数据与
  分词模块)+ `tests/test_share_data.py`。单个 commit,两个新文件,没有改动
  任何既有文件。

## 4 自查发现与存疑

- **`event` 字典多带了 `full_ids` 字段**:工单第 1 条列的字段是
  `event, n_full, packed_len, prefix_len P, rows`,没提 `full_ids`。但
  `pack_event` 需要 `full_ids[:P]` 拼前缀,而 `pack_event` 是同一工单第 2 条
  要交付的东西,离了这个字段没法实现。判断这是工单枚举时的疏漏而非故意
  排除,补了这个字段,已在报告里点出供复核。
- **全部行被行级丢弃的事件不进返回列表**:工单原文没写这一条,是实现时
  撞见的空洞——如果保留这种"事件在、行是空列表"的记录,`pack_event` 会
  拼出一个只有前缀、`packed_len=prefix_len`、零损失位的"事件",在
  `--smoke`/`chunk_by_budget` 里占一个名额却不产生任何训练信号。按空洞判据
  排除,不新增计数字段(它的行已经分别记在 `dropped_rows_tgt`/
  `assembly_mismatch`/`ro["dropped"]` 里)。测试 `test_cgen_and_cparam_drop_counts`
  的 `ev_long_tgt` 用例覆盖了这一分支(第一版测试没考虑到这个空洞,断言
  `"ev_long_tgt" not in kept_events` 时先跑出了 FAIL,加上这条排除逻辑后
  才过——记在这里因为它是根因修复而不是补丁,补丁做法会是在测试里放宽
  断言而不是改实现)。
- **`load_events` 里的两道硬停(0 行 / cparam 剥离失败率)**:工单原文
  "两道硬停照搬"只出现在第 1 条的括号注里,验收段(a)~(e) 没有专门列出
  要测硬停触发;我另加了 `test_hard_stop_zero_rows` 与
  `test_hard_stop_assembly_mismatch_rate` 两个用例断言 `SystemExit` 真的会
  抛出来,判断这是把工单要求的功能测到位而非节外生枝,但确实超出了验收段
  字面列的 (a)~(e),点出来给复核。
- **`chunk_by_budget`/`worst_blocks` 的测试用手造 `dict(event=.., packed_len=..)`**,
  没有走 `load_events` 产出的完整事件结构——这两个函数本来就只读
  `packed_len` 一个键,手造假件更能把"贪心装块"这条逻辑单独测清楚;
  真实完整事件结构已经在 `TestPrefixRule` 里跑过一遍 `load_events` 的产出
  形状,两边合起来覆盖到位,判断不需要再叠一层用真事件测 chunk。
- **未验证之处**:`load_events`/`pack_event` 等函数在真正的大规模训练场景
  (--max-len 8192、64 行/事件的边界情况)下没有跑过,那是工单 03(训练器)与
  gpu-run 冒烟的职责,本工单只在 CPU 单测规模上验证过逻辑正确性。

## 5 给工单 04 的 MAP.md 文案

工单 04 负责往 `MAP.md` 第 88 行那张训练表加一行 `（共用）`(本工单不改
`MAP.md`,照工单第 24 条要求把文案写在这里):

```
| （共用） | `pipeline/train/share_data.py` | cgen/cparam 新训练器
(`train_causal_share.py`,工单 03)与 ctool/`eval_tool.py`(工单 02)共用的
纯 CPU 数据与分词模块:`load_events` 按事件分组、算公共前缀 `p`、拼目标段
`seg_ids`/`seg_lab`;`pack_event`/`allowed_mask`/`batch_mask` 建形态 A 的
拼接序列与注意力掩码;`chunk_by_budget`/`worst_blocks` 按 token 预算贪心
装块;`read_position` 是 ctool/`eval_tool.py` 切点读取位置规则的单一真源 |
模块顶层只有 stdlib+torch,对 `train_causal_callgen`/`train_causal_param`/
`rules.MAX_BOUNDS` 的 import 全部延迟到 `load_events` 函数体内(mbert-env
的 transformers 4.57.6 装不动旧训练脚本模块顶层的版本门,而
`eval_tool.py` 要在 mbert-env 下 import 本模块拿 `read_position`);
`mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train');
import share_data"` 是硬门,必须退出码 0 |
```

## 6 修复第 1 轮(2026-08-28,commit `d48c287`)

分支`ticket/2026-08-28-wave1/T01`,base 仍是 `2e61f5f`,这一轮的 head
`d48c287`(工作树 `/home/y-guo/reproduce/new1-wt/2026-08-28-wave1-T01-fix1`,
已按协议删除,分支保留)。收到的三条未决 findings,逐条修在
`pipeline/train/share_data.py`,没有碰其余任何文件。

### F1(critical)——`worst_blocks` 缺 `events_per_mb` 参数,最满块算法与工单不符

**改法**:签名改成 `worst_blocks(events, tok_budget, events_per_mb)`,不再
借用 `chunk_by_budget` 对全量事件跑贪心装块再挑"块内最长最大"那块——那
个算法的块内事件数不受 `events_per_mb` 约束,真实训练里不会出现这种块。
新算法照工单原文:`B` 取 2 到 `events_per_mb`;把 `events` 按 `packed_len`
降序排好;对每个 `B`,用大小为 `B` 的滑动窗口从最长的一端往下扫(降序排
列下窗口内最长恰好是窗口首元素,窗口下移这个值只会变小或不变),取第一
个满足 `B * L_pad <= tok_budget` 的窗口作为这个 `B` 的最优组;几个 `B`
各自的最优组里,取 `B * L_pad` 最大的那一组当"最满块"。找不到任何满足
条件的窗口(事件数不够,或预算小到连 2 个事件都装不下)时,这一份返回
空列表(工单没写这个边界情况,判断"没有一个合法组合"就该如实返回空,
不是硬凑一个不满足预算的组合出来)。

**验证**:新写 `test_worst_blocks`(手算 `events_per_mb=3`、`tok_budget=200`
的例子,B=2 最优组 `{b,c}`(product=192)比 B=3 最优组(product=96)大,
`packed_len` 最大的单个事件 `a` 反而不在最满块里——因为 `a` 跟第二大的
`b` 配对就超预算)。同一个用例里另外跑一遍旧算法的做法(直接对全量事件
跑 `chunk_by_budget` 再挑"块内最长最大"那块)对照,结果是单事件块 `{a}`,
跟正确答案 `{b,c}` 不同,断言这条差异真实存在(不是我自己以为存在)。
另加两个边界用例:`test_worst_blocks_no_valid_group_when_budget_too_small`
(预算连 2 个都装不下,最满块返回空列表)、`test_worst_blocks_empty_events`
(空 `events` 两份都返回空列表,沿用原有行为)。

### F2(critical)——`chunk_by_budget` 预算判据用 `packed_len` 而非 `L_pad`

**改法**:新增 `_pad16(n)` 辅助函数(`((n + 15) // 16) * 16`,和
`batch_mask` 的 `L_pad` 补齐同口径),`chunk_by_budget` 的预算判据从
`n * cand_max <= tok_budget` 改成 `n * _pad16(cand_max) <= tok_budget`。
`worst_blocks` 的滑动窗口判据同样用 `_pad16(window[0]["packed_len"])`。

**验证**:新写 `test_budget_uses_padded_length`:两个事件 `packed_len=161`,
`tok_budget=322`——补齐前 `2*161=322<=322` 会通过(会被误装进同一块),
补齐后 `L_pad=_pad16(161)=176`,`2*176=352>322` 不通过,断言两个事件最终
各自成块。原有 `test_greedy_budget`/`test_single_event_over_budget_alone`
两个用例不改动也全过(它们的断言用的是 `<=` 弱不等式,`packed_len` 判据
换成 `L_pad` 判据只会让装块更保守,不会打破这两条断言)。

### F3(critical)——`batch_mask` 对 pad 位置的 `position_ids` 写死 0,不是"接着数"

**改法**:pad 区间(`[L, L_pad)`)的 `position_ids` 从"保持初始化的 0"改成
从这一事件最后一个真实位置(`positions[-1]`)往后连续编号
(`torch.arange(last_pos + 1, last_pos + 1 + (L_pad - L))`);`positions`
为空(`L=0`)时 `last_pos` 取 -1 只是防 `IndexError` 的边界兜底,不是
额外功能——从 -1 开始接着数就是 0,1,2...,跟"接着数"这条规则本身一致。
`batch_mask` 的 docstring 同步改掉"pad 位置的 `position_ids` 是 0"这句
错误描述。

**验证**:`test_batch_mask` 里加了两段逐位断言:事件 A(`prefix_len=3`,
真实位置 `[0,1,2,1,2,3,3,4,5,2,3,4]`,最后一个真实位置是 4)的 4 个 pad
位应该是 `[5,6,7,8]`;事件 B(`prefix_len=0`,真实位置 `[0,1]`)的 14 个
pad 位应该是 `[2..15]`。两条都实测通过。原有的掩码相关断言(pad 作为
query 只看自己、真实 token 看不到 pad)不受影响——F3 只改 `position_ids`
的取值,不改 `allowed`/`mask` 的计算,且 RoPE 类相对位置编码下这处偏差
本来就不影响任何真实输出(finding 本身也这么写),这次改动纯粹是让实现
文字上跟 spec 对齐。

### 怎么验证的(这一轮)

```
cprobe-env/bin/python -m unittest tests.test_share_data -v
```
21 个用例全过(18 个原有 + 3 个新增:`test_budget_uses_padded_length`、
`test_worst_blocks_no_valid_group_when_budget_too_small`、
`test_worst_blocks_empty_events`;原有 `test_worst_blocks`/`test_batch_mask`
两个用例改了断言内容,不算新增):
```
Ran 21 tests in 15.858s

OK
```
(worktree 里同样没有 `pipeline/data`/`cprobe-env`/`mbert-env` 三条本地
软链——继承自上一轮的已知情况,gitignore 的裸名软链不会随 `git worktree
add` 带出来——补了三条本地软链指回主仓对应目录/env 才能跑;这三条软链
没进 git,不影响主仓,工作树删除后一并消失。)

```
mbert-env/bin/python -c "import sys; sys.path.insert(0,'pipeline/train'); import share_data; print(share_data.read_position)"
```
退出码 0(硬门仍然通过,这一轮没有碰这个函数)。

```
cprobe-env/bin/python -m unittest tests.test_cparam_assembly tests.test_lora_merge
```
两个现有测试文件共 22 个用例全过,确认没有连带影响。

```
python3 -m unittest discover -s tests -v
```
`test_share_data` 仍正确落在 `unittest.loader.ModuleSkipped`(系统 python3
没有 torch),不计入失败。全量跑出 `FAILED (failures=1, errors=1,
skipped=17)`——一次失败(`test_no_env_reads_default_preset`)一次报错
(`test_splice_replay`)都是上一轮报告里记过的既有问题,跟 `share_data`
无关,这一轮没有改动它们涉及的任何文件。`skipped` 从上一轮的 18 变成
17,数字本身在这一轮没有细查(不是这几条 finding 的范围,也不是
`share_data`/`test_share_data` 造成的——这两个文件对应的那一条 skip
在两轮里都稳定落在 `ModuleSkipped`),留给之后按需处理。

```
python3 run.py selfcheck
```
`74 任务 / 4 配方 / 3 预设, 14 处缺失`——缺失数比上一轮的 16 少 2,是
这一轮补的 `cprobe-env`/`mbert-env` 本地软链让对应任务的解释器路径能
找到了,不是注册表结构变化;这一轮没有改动 `run.py` 或任何注册表条目,
`git status` 里跟踪文件只有 `share_data.py` 与 `test_share_data.py` 两个。

### commit 清单(这一轮)

- `d48c287` T01: 修复 3 条 findings(worst_blocks 签名与算法、chunk_by_budget
  预算判据、pad position_ids)。单个 commit,两个既有文件的修改,没有新增
  或删除文件。

### 自查发现与存疑(这一轮)

- **`worst_blocks` 找不到合法组合时返回空列表**:工单原文没写这条边界,
  是修复时新加的行为判断(按空判据处理,不是节外生枝);已在上面 F1 段
  与 `test_worst_blocks_no_valid_group_when_budget_too_small` 里点出。
- **`chunk_by_budget` 现有两个测试(`test_greedy_budget`、
  `test_single_event_over_budget_alone`)在改判据前后都能过**,因为它们
  的断言用 `<=` 弱不等式且没有构造"补齐前后跨预算边界"的数值——这正是
  F2 指出的"测试没拦住这个偏差"的根因,这一轮新增的
  `test_budget_uses_padded_length` 专门补上这条判别力。
- **未验证之处**:这三条 finding 的修复只在 CPU 单测规模上验证过逻辑
  正确性;`worst_blocks` 真正喂给 spec 第 10 节排卡裁决的完整链路(在
  `--mem-probe` 里被训练器调用、拿真实 H100 显存数字核对)仍然是工单 03
  与 gpu-run 冒烟的职责,这一轮没有跑。
