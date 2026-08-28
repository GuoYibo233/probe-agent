# T10 报告:显存探针三种挑块方式 `--mem-probe-pick {tokens,cost,loop}`

工单:`.scratch/kvshare-train/issues/10-mem-probe-pick.md`
Spec:`.scratch/kvshare-train/spec.md` 16.5(做法与字段)、16.9(测试)、16.10 #31 #32
分支:`ticket/2026-08-28-wave5/T10`,base `07907db08b50d66c1c193588f22b5cc97b24b4b3`,
head `e272ffd53c4565bdd13657b003badd8d3c0b1f53`

## 一、做了什么(对照工单逐条)

### 1. `share_data.epoch_minibatches(events, seed, ep, events_per_mb)`(工单第 1 条)

新增函数(`pipeline/train/share_data.py`):`list(events)` 复制一份后
`random.Random(seed + ep).shuffle`,再按 `events_per_mb` 切成逻辑小批——就是
训练循环原来自己做的两步。`train_causal_share.py` 的训练循环(改前第 761 到
764 行)改调它,`cost`/`loop` 探针的枚举(`_enum_run_blocks`)也调它——三处
唯一真源。`grep -n "epoch_minibatches"` 两个文件都命中,训练循环里不再有
自己的 `random.Random(SEED + ep).shuffle` 调用(已核实 `grep -n
"random.Random(SEED" pipeline/train/train_causal_share.py` 零命中)。

### 2. `--mem-probe-pick {tokens,cost,loop}`(默认 `cost`)与 `run_mem_probe` 重构(工单第 2 条)

`run_mem_probe` 拆成骨架加三种挑块跑法,新签名
`run_mem_probe(model, opt, tr_events, args, dev, log, amp, full_events=None)`——
`tr_events` 留在改前 `full_events` 的位置(第三个位置参数),`full_events`
改成尾部关键字参数、默认 `None` 时退回用 `tr_events`。这样改前两处
`tcs.run_mem_probe(model, opt, events, args, "cpu", log, amp=False)` 的调用
(`tests/test_share_trainer.py` 第 548、595 行附近)按位置对齐后原样能跑
(`tr_events=events`,`full_events` 落到默认值再退回 `events` 自己),不用
改调用点,只按工单要求给这两处 `argparse.Namespace` 补了
`mem_probe_pick="tokens", accum=2` 两个字段(`run_mem_probe` 内部要读
`args.mem_probe_pick`/某些路径要读 `args.accum`,不补会 `AttributeError`)。

骨架(建优化器状态 -> `reset_peak_memory_stats` -> 按 `--mem-probe-pick`
分发 -> 清状态、恢复 lr、清梯度)与改前逐字一致,只是外层包了一层
随机数状态的保存/恢复(见第 4 条)。

- **`tokens`**(现状):全集里按 `share_data.worst_blocks` 挑最满块加最长
  事件,状态已建、连做两次(最满块)/一次(最长事件)反向。全集加载改成
  只在这个模式下发生:`main()` 里 `if args.mem_probe_pick == "tokens":`,
  且 `(not args.smoke) and args.max_events == 0` 时直接复用 `tr_events`
  (`limit=0` 时 `tr_events` 本来就是全集),否则才另装一次全集。
- **`cost`**(默认):新增 `_enum_run_blocks(tr_events, args)` 用
  `epoch_minibatches(tr_events, SEED, 0, events_per_mb)` 枚举 epoch 0 的
  逻辑小批,每个逻辑小批过 `chunk_by_budget` 得到物理块;新增
  `_pick_cost_blocks(blocks)` 挑三块——(i) `B x L_pad` 最大,并列取损失位
  多的;(ii) 损失位数最大,并列取 token 多的;(iii)
  `n_tokens/max + n_loss_pos/max` 最大。三块各在"状态已建、连做两次前向
  加反向、中间不清梯度"下量峰值;重复的块(按 `id()` 同一性判断)只跑
  一次,重复条目照写 `mem_probe` 事件、加 `same_as` 指到真正跑过的 kind。
- **`loop`**:同样用 `_enum_run_blocks` 枚举,先找到含损失位最多那一块所在
  的逻辑小批,再按 `(best_mb_idx // accum) * accum` 定位它所在的更新组
  (末组不足 `accum` 时 `group_end = min(group_start + accum, M_ep)`,`n_g`
  按实际个数),照训练循环原样跑一次更新:逐个逻辑小批
  `backward_logical_minibatch`,组跑完 `clip_grad_norm_` 接 lr=0 的
  `opt.step()`,再读峰值(顺序照工单/spec 字面:先 `opt.step()` 后读峰值,
  和真实 `step` 事件的峰值读取时点一致)。调度器 `sch` 未被触碰。

### 3. 随机数状态保存与恢复(工单第 2 条第五段,静默失败点 #31)

`run_mem_probe` 整段包在 `try/finally` 里:进入前存
`random.getstate()`、`torch.get_rng_state()`、(cuda 上)
`torch.cuda.get_rng_state()`,`finally` 里逐一 `setstate`/`set_rng_state`
恢复。测试 (c) 验证:小模型 `main()` 带 `--mem-probe --mem-probe-pick cost
--lora` 与不带 `--mem-probe`(同样 `--lora`)两次 `--smoke --max-events 6
--log-every 1` 跑下来,`train_log.jsonl` 的 `step` 事件 `loss` 逐条相同
(实测两次都是 `11.9434`,`eval` 的 `val_ce` 都是 `11.9295`)。

### 4. 事件字段统一 + `mem_probe_summary` + `_peak_gb`(工单第 2 条第六、七段)

新增模块级 `_peak_gb(dev)`(cuda 上 `max_memory_allocated() / 1e9`,其他
设备 `0.0`),探针三种模式与训练循环 `step` 日志(改前第 813 到 817 行)
都改调它。`mem_probe` 事件字段统一为 `pick, kind, B, L_pad, n_tokens,
n_rows, n_loss_pos, peak_mem_gb, n_backward, with_optimizer_state,
optimizer_state_prebuilt`(`loop_group` 另加 `n_blocks, n_events,
max_block_n_loss_pos`,`B/L_pad/n_tokens` 写组里最大那块的,
`n_rows/n_loss_pos` 整组求和,`n_backward` 是组内物理块总数);旧键
`n_events`(tokens/cost 下沿用等于 `B` 的老口径,loop_group 下改成组内总
事件数)、`packed_len_max`(等于 `L_pad`)保留不删。全部跑完写一条
`mem_probe_summary`(`pick, worst_gb, worst_kind, scope, n_events_considered`,
`scope` 是 `full`(tokens)或 `run`(cost/loop))。`start` 事件加了
`mem_probe_pick`(紧跟 `mem_probe` 那个键之后)。

### 5. 顺带:`step` 事件加 `grad_norm`(工单第 2 条第八段)

训练循环里 `total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(),
1.0)` 捕获返回值,`step` 日志加 `grad_norm=round(float(total_norm), 4)`。

### 6. 手造行元组 7 位(工单第 2 条第九段)

本工单没有在生产代码里新写手造行元组;测试文件里手造的物理块(`_mk_block`)
只服务于 `_pick_cost_blocks` 的纯挑块逻辑,不经过 `pack_event`/模型前向,
所以不受"6 位元组会让 `pack_event` 报 `ValueError`"这条约束影响(工单原文
说的是"share_data 行元组第 6 位是 gen 字典",而工单 08 尚未合并进本分支,
不存在 7 位/6 位冲突;若日后合并出现真实前向路径的手造事件,再按 7 位补齐)。

## 二、怎么验证的

全部命令用 `/home/y-guo/reproduce/new1/cprobe-env/bin/python`(worktree 里
没有这个虚拟环境,是软链接以外的本地目录,未被 git 跟踪,直接用主仓那份
解释器)。跑之前在 worktree 里补建了 `pipeline/data`、`pipeline/runs` 两个
到 NFS 的软链接(和主仓 `pipeline/data`/`pipeline/runs` 同一个软链接目标,
这两个软链接本身在 `.gitignore` 里被排除、`git worktree add` 不会带过来,
补建纯粹是为了让依赖现役数据/权重的测试跑起来,不改动任何被跟踪文件)。

- 验收命令(工单原文):
  ```
  cprobe-env/bin/python -m unittest tests.test_mem_probe_pick tests.test_share_trainer tests.test_share_data
  ```
  输出:`Ran 42 tests in 571.167s` `OK`(5 + 16 + 21 = 42,数字对得上,没有
  被我的 `import test_share_trainer as tst` 重复收录)。

- `grep -n "epoch_minibatches" pipeline/train/share_data.py
  pipeline/train/train_causal_share.py`:两个文件都命中(定义 + 3 处调用)。
- `grep -n "random.Random(SEED" pipeline/train/train_causal_share.py`:零
  命中(训练循环里不再有自己的 shuffle)。
- `grep -n "mem_probe_summary\|get_rng_state\|def _peak_gb"
  pipeline/train/train_causal_share.py`:三个都命中。
- `git diff --stat main -- run.py`:空(没改 `run.py`)。
- `python3 run.py selfcheck`:在这个 worktree 里报 16 处"缺解释器/程序"
  (`envs/*`、`cprobe-env`、`mbert-env` 等本地虚拟环境目录本来就没被
  `git worktree add` 带过来),但任务/配方/预设计数 `76 任务 / 4 配方 / 3
  预设` 和主仓(`selfcheck: 76 任务 / 4 配方 / 3 预设, 全部就位`)完全一致
  ——注册表本身没有被改动,缺失纯粹是 worktree 缺本地环境目录,不是本工单
  引入的问题(本工单也确实没有改 `run.py`)。

### 新测试(`tests/test_mem_probe_pick.py`)逐条对应

- (a) `TestPickCostBlocks`:手造 6 个单事件物理块(1 个损失位最多、2 个
  token 数并列但损失位不同、1 个综合分最高、2 个陪衬块),断言
  `_pick_cost_blocks` 挑到的 `max_tokens_block` 是并列里损失位多的那块、
  `max_losspos_block` 与它不同、`max_cost_block` 是按公式算出来的那块
  ——通过。手算过程见测试文件内注释与本报告底部"自查"一节的复核。
- (b) `TestRunMemProbeThreeModes`:`tokens`/`cost`/`loop` 三种模式各跑一次
  `run_mem_probe`(真实 Qwen3-0.6B-Base 分词器 + 随机初始化的两层小模型 +
  val 集抽的 5 个短事件),断言 `opt.state` 为空、`lr` 恢复、`.grad` 全
  `None`、参数逐位不变(`torch.equal`);`_peak_gb` 用
  `unittest.mock.patch.object` 换成每次调用返回递增值(1.0、2.0、…)的假
  函数,断言 `mem_probe_summary.worst_gb` 等于本轮各 `mem_probe` 事件
  `peak_mem_gb` 的最大值,`worst_kind` 对上那个最大值所在的 `kind`——三个
  子测试都通过。
- (c) `TestMemProbeRngRestorationViaMain`:小模型 `main()` 带
  `--mem-probe --mem-probe-pick cost --device cpu --lora` 与不带
  `--mem-probe`(同样 `--lora`)各跑一次(`--smoke --max-events 6
  --log-every 1`),两份 `train_log.jsonl` 的 `step` 事件 `loss` 逐条
  相同——通过(实测两次 `loss` 都是 `11.9434`)。

### `tests/test_share_data.py` 新增 `TestEpochMinibatches`

`test_matches_old_inline_shuffle`:23 个手造事件,`epoch_minibatches` 与
函数体内手抄的"旧写法"(`list(events)` 复制、`random.Random(seed +
ep).shuffle`、按 `events_per_mb` 切片)比对事件名序列,逐个相同。
`test_does_not_mutate_input`:确认不改调用方传入的原始列表。两条都通过。

### 完整 diff 涉及的四个文件各自单独跑过

- `tests.test_share_data`(21 -> 23 条,含新增两条):`Ran 23 tests` `OK`
  (1 条 `setUpClass` 级 skip,val 集路径判断早于我补的软链接生效那一次,
  之后补链接重跑就没有再 skip;这次连同 `test_share_trainer` 一起跑的
  `Ran 37 tests`/`OK` 就是补链接之后的结果,已把这条也跑实了)。
- `tests.test_share_trainer`(16 条,含改动的两条探针用例):随
  `test_share_data` 一起跑,`Ran 37 tests` `OK`。

## 三、commit 清单

- `d4a87d9` T10: share_data.epoch_minibatches 唯一真源(spec 16.5)
  ——`pipeline/train/share_data.py` 新增函数,`tests/test_share_data.py`
  新增 `TestEpochMinibatches`。
- `e272ffd` T10: 显存探针三种挑块方式 --mem-probe-pick {tokens,cost,loop}
  (spec 16.5)——`pipeline/train/train_causal_share.py` 的 `run_mem_probe`
  重构与训练循环改调 `epoch_minibatches`/`grad_norm`,
  `tests/test_share_trainer.py` 两处 `Namespace` 补字段,新增
  `tests/test_mem_probe_pick.py`。

## 四、自查发现与存疑

- **`_pick_cost_blocks` 手算复核**(供复核用,不是新发现的问题):6 块
  `packed_len`/损失位为 `(64,60)`、`(320,16)`、`(320,40)`、`(288,55)`、
  `(48,5)`、`(32,3)`(均为 1 行或多行 1 事件块,`B=1`,`L_pad` 与
  `packed_len` 因取值都是 16 的倍数而相等,`n_tok=L_pad`)。
  `max_n_tok=320`,`max_n_loss_pos=60`。三块得分:`(64,60)` 的 cost =
  64/320+60/60=1.2;`(320,16)` = 1.2667;`(320,40)` = 1.6667;`(288,55)` =
  0.9+0.9167=1.8167;两个陪衬块 0.233、0.15。`max_tokens_block` 在
  `(320,16)` 与 `(320,40)` 并列时按"损失位多"取到 `(320,40)`;
  `max_losspos_block` 是 `(64,60)`(唯一最大,与前者不同);`max_cost_block`
  是 `(288,55)`(唯一最大)。三块两两不同,和测试断言一致。
- **`worst_kind` 在 CPU 真实(未 mock)路径下可能是 `None`**:`_mem_probe_*`
  三个函数用 `if peak > worst_gb:`(初始 `worst_gb=0.0`)决定 `worst_kind`,
  CPU 上 `_peak_gb` 恒返回 `0.0`,首个候选的 `0.0` 不满足严格大于
  `0.0`,`worst_kind` 会停在 `None`(`worst_gb` 本身仍然正确,因为 `0.0`
  确实是全 `0.0` 列表的最大值)。测试 (c) 的真实输出里能看到这一现象
  (`mem_probe_summary` 的 `worst_kind: None`,`worst_gb: 0.0`)。GPU 上
  真实峰值不会恰好等于哨兵值 `0.0`,不构成生产问题;工单/spec 也明确
  "CPU 上真值恒 0.0,不 patch 就是 0 == 0,没有区分度"这一限制本身是
  预期之内的,所以没有为此改动判定逻辑,只在这里记录下来供复核。
  这条我判断不需要改,如果 gyb 认为 `worst_kind` 在全零并列时也该给一个
  非 `None` 的值(比如取第一个候选),需要另行裁决再改。
  - **测试 (c) 里 `cost` 模式的三块全部落到同一个物理块**(`same_as` 链
  `max_losspos_block -> max_tokens_block`、`max_cost_block ->
  max_tokens_block`):`--max-events 6`、`events_per_mb=4`(默认)下 6 个
  事件只切出 2 个逻辑小批、`tok_budget=16384` 足够大让每个逻辑小批各自
  装进 1 个物理块,恰好其中一块同时是 token 最多、损失位最多、综合分
  最高的块。这是真实数据在小样本下的巧合,不是 bug——(a) 测试已经用手造
  数据单独验证过三条挑块规则在有区分度时的行为。
