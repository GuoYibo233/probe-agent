# T03 报告:训练器 `pipeline/train/train_causal_share.py` 与注册表

工单:`.scratch/kvshare-train/issues/03-share-trainer.md`
分支:`ticket/2026-08-28-wave2/T03`,base `2216c44d50838e6df6d3f8f78b31ca955998e520`,
head `f40daaa`(工作树 `/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03`,已删除)。

## 一、做了什么(对照工单逐条要求)

### 1. 新建 `pipeline/train/train_causal_share.py`

- 数据走 `share_data.py`(工单 01);tokenizer 与模型走
  `train_causal_callgen.build(dev, base=, attn_impl=, path=)`。`--base` 接受
  `qwen/qwen17/qwen4` 或一个目录路径(`args.base in train_causal_callgen.MODELS`
  判分支,是就传 `base=`,不是就传 `path=`)。
- 前向按 spec 第 4 节 + `design-attention.md`:一张公用的 `_forward_packed`
  先从末层隐状态按损失位 gather、再过 `model.lm_head`(不算全位置 logits),
  cuda 上套 `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])`(`_attn_ctx`,
  CPU 上退化成 `contextlib.nullcontext()`)。掩码 dtype 由调用方传入
  (`mask_dtype` 参数),训练/评估走 bf16(amp 开时)或 fp32(CPU),对齐检查
  走 fp32,bf16 粗筛走 bf16。pad 位置的 position_ids 由 `share_data.batch_mask`
  接着数(工单 01 已实现,本工单只是消费)。
- 损失与更新按第 5 节:`block_row_ce`(一个物理块每行 mean CE + w)、
  `backward_logical_minibatch`(一个逻辑小批按 `chunk_by_budget` 拆的物理块
  列表,`loss_C = Σ w_r·ce_r / W`,`(loss_C/n_g).backward()`)。`main()` 里
  每个 epoch 用 `random.Random(SEED+ep)` 打乱事件、按 `--events-per-mb` 切
  逻辑小批、按 `--accum` 分组;尾组按 `min(accum, M-组起点)` 定 `n_g`,不漏
  梯度、步长不打折。
- 评估与 `best/` 按第 6 节:评估点集合 `{ceil(U·k/E): k=1..E}`,实现里用
  `dict` 让同一个点被多个 `k` 命中时取 `max k` 当 `frac`(保证 `k=E` 那点、
  也就是 `u=U` 恒定映射到 `frac=E`,不被更早的重复点占掉,细节见
  「自查」)。`best/` 落盘与 `meta.json` 字段照工单逐项(`trainer/frac/
  gstep/tok_budget/events_per_mb/accum/attn_impl` 新增,`readonly_env`/
  `lora`/`grad_ckpt`/`param_only` 条件写)。
- 日志与心跳按第 7 节:`start/step/eval/save_best/done/mem_probe` 六种事件
  (`mem_probe` 只在 `--mem-probe` 时出现),`step` 的 `train_s` 只累计训练
  段时间(每次更新前后各计时一次,评估调用夹在两次计时之间、天然不计入)。
  `heartbeat.emit` 三处:起步(第 606 行)、每条 step(第 682 行)、收尾
  (第 726 行)。
- 命令行按第 8 节的表逐项实现;`--smoke`/`--max-events` 的组合规则(单独给
  `--max-events` 随机、和 `--smoke` 同给按 `shortest` 且 N 覆盖 40/16)按
  spec 字面写。
- 对齐检查按第 9 节,细节见下面单独一节(改动最大、最值得复核的部分)。

### 2. `run.py` 注册表

- `CELLS["cgen"]`/`CELLS["cparam"]` 改指 `train_causal_share.py`,分别带
  `["--mode", "cgen"]`/`["--mode", "cparam"]`;`CELL_ORDER` 未动。
- `TASKS["train-cgen"]`/`TASKS["train-cparam"]` 同步改脚本 + `args`,notes
  补了新口径的说明(上限、更新单位、内置对齐检查)。
- 新增 `TASKS["train-cgen-rows"]`/`TASKS["train-cparam-rows"]` 指向两个旧
  逐行脚本,字段照 `train-ctool` 逐项给全(`desc/stage/py/script/gpu/notes`),
  notes 按工单原话写「逐行参照实现,只用于对齐检查与对照;产物不进矩阵,
  run_id 不许用现役批次前缀」。
- `python3 run.py selfcheck`、`python3 -c "import ops.launch_probe"`、
  `python3 run.py show train-cgen` 打印含 `train_causal_share.py --mode cgen`
  —— 三条都过,细节见「二、怎么验证的」。
- `EVAL_CELLS` 未动(`git diff` 没有这块的改动)。

### 3. `MAP.md` 文案(工单要求写进报告,由工单 04 落盘)

- **cgen** 行:程序列改 `train_causal_share.py --mode cgen`;关键设定列写
  「一个事件一次前向共享前缀;上限 8192 超长事件整条丢弃;8 个事件一次
  更新;1 个 epoch 每四分之一评一次 val_ce;`--tok-budget` 控显存」。
- **cparam** 行:同上,程序列改 `--mode cparam`。
- 新增一行 **(参照)**:`train_causal_callgen.py`/`train_causal_param.py`,
  经 `train-cgen-rows`/`train-cparam-rows` 发射,4096、左截、3 epoch 的旧
  逐行口径,冻结为对齐参照,产物不进矩阵。
- 新增一行 **(共用)**:`pipeline/train/share_data.py`,cgen/cparam(以及
  ctool 的 `read_position`,工单 02)共用的纯 CPU 数据与分词模块。

### 4. 对齐检查(第 9 节,改动最大的部分)

- 放在 `lora_util.wrap` 之前、`model.eval()` 下,`run_align_check()` 一个
  函数做完:`torch.set_float32_matmul_precision("highest")` + cuda 上关两个
  `allow_tf32`(`finally` 里恢复)。
- 进料:`_align_candidates` 独立扫一遍 val(按 event 分组 + 全文分词过滤
  `<= 2048` token,不跑 `share_data.load_events` 的行级流水线——这条是
  为了不让 `--smoke` 时的抽样也背上全量行级分词的开销,细节见「自查」第
  1 条),`random.Random(SEED)` 抽样,`_write_align_tmpfile` 按
  `(event, sent_idx)` 升序写临时文件(`tempfile.mkstemp`,系统临时目录,
  `finally` 里 `unlink`)。
- 新路径:同一份临时文件喂 `share_data.load_events(limit=0)`,`_new_forward`
  逐事件单独一次前向(数量小,不必按预算装块)。
- 参照路径:`_ref_forward` 用旧 `collate`(`import` 自旧脚本,不复制)按
  `bs` 行一批,手算与 `inst_ce` 相同公式的交叉熵,但多留逐 token 的中间量
  ——这条和字面「import inst_ce」有出入,细节与理由见「自查」第 2 条。
  `bs=4`「整批」与 `bs=1`「单行」各跑一遍(后者是补齐基线)。参照路径不套
  `EFFICIENT_ATTENTION`(design-attention.md 7.1 节的坑:单行批没有掩码,
  HF 走 `enable_gqa`,mem-efficient 不接 GQA)。
- 配对:`len(ds.rows) == 新路径总行数`、逐位 `ds.rows[i][0] == 新路径第 i
  行的 text`、丢弃计数相等(cgen 只查 `dropped_rows_tgt`,cparam 另查
  `assembly_mismatch`;`mode != "cparam" or ds.mismatch == ...` 的短路写法
  是必须的——`CallDS` 没有 `.mismatch` 属性,cgen 分支从不求值右边)。
- 判定:逐行 `<= --align-tol`(默认 2e-5)且逐 token `<= 3e-4`(固定值
  `TOK_DIFF_TOL`,不开成 CLI 参数,按 spec 字面);基线告警
  `row_diff > max(3*baseline_diff, 1e-6)` 只告警不判定。bf16 粗筛只在 cuda
  上做,CPU 上三个字段(`bf16_mean_abs_diff`/`bf16_max_abs_diff`/隐含的
  `bf16_warn`)按 spec 写 null/False。`ALIGN_CHECK.json` 键名用大写 `PASS`,
  另外按 spec 原文加了 `baseline_warn`(spec 正文明确要求「打
  baseline_warn: true」)与一个额外诊断键 `bf16_warn`。

## 二、怎么验证的

全部在工作树 `/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03` 里跑
(cprobe-env/mbert-env 用软链接到主仓,pipeline/data、pipeline/runs 同样
软链到 NFS——工作树是全新 checkout,这三类都不进 git,提交前已删掉软链)。

**单元测试**(`tests/test_share_trainer.py` 的 (a)(b)(c) + 既有三份):

```
cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data \
  tests.test_cparam_assembly tests.test_lora_merge -v
```
输出尾部:`Ran 48 tests in 165.629s` / `OK`(48 个全过,含我新写的 6 个:
`TestPackedForwardMatchesOldPath.{test_cgen,test_cparam}`、
`TestBackwardBlockSplitInvariance.test_split_into_1_vs_3_blocks`、
`TestMainSmokeCPU.{test_cgen_smoke,test_cparam_smoke}` 算 3 个 test method
但内含 cgen/cparam 两次断言链)。

系统 `python3` 直接点名这几个模块跑时,四个文件(含既有的
`test_share_data.py`/`test_cparam_assembly.py`/`test_lora_merge.py`)全部同样
在 import 阶段 `SkipTest` 被 `unittest.loader.loadTestsFromName` 当成异常抛
出来(traceback 而不是「OK skipped」)——这是 `python3 -m unittest
tests.test_X`(显式点名模块)这个调用形式本身的行为,`python3 -m unittest
discover` 才会把它当 skip 处理,在**主仓**(未改动)对
`tests/test_share_data.py` 复现过同样的 traceback,不是本工单引入的回归。
`discover` 形式验过一遍:
```
python3 -m unittest discover -s tests -p "test_share_trainer.py" -v
# test_share_trainer (unittest.loader.ModuleSkipped) ... skipped
# Ran 1 test in 0.000s / OK (skipped=1)
```

**grep 检查**:
```
grep -n "heartbeat.emit" pipeline/train/train_causal_share.py
# 606:    heartbeat.emit(0, steps, "step")
# 682:                heartbeat.emit(gstep, steps, "step", loss=loss_val)
# 726:    heartbeat.emit(gstep, steps, "step", status="done")
grep -n "sdpa_kernel" pipeline/train/train_causal_share.py
# 命中 import 行 + _attn_ctx 定义(训练/评估/对齐检查三处前向都走
# _forward_packed 这一个共用函数,所以只有一处 sdpa_kernel([...]) 字面量,
# 但三处调用路径都经过它)
```

**CPU 真实冒烟**(0.6B fp32,按工单验收段的原始命令):
```
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --data pipeline/data/nyapass_aw_v1/gptoss --out pipeline/runs/smoke/share_cpu_cgen_smoke \
  --device cpu --smoke --max-events 6 --log-every 1 --align-events 2 --base qwen --force
```
`ALIGN_CHECK.json`:`PASS: true`,`max_abs_diff: 2.384e-6`(tol 2e-5),
`max_tok_diff: 2.193e-5`(tol 3e-4),`n_events: 2`,`n_rows: 75`。
`train_log.jsonl` 五种事件都出现;`step` 只有一条(6 个事件、
`events_per_mb=4`、`accum=2` → `M=2, U=1`,与工单第 5 条「6 个事件只有 1
次更新」吻合);`loss` 从 3.3317 到 `val_ce` 1.2026(0.6B 底座已有语言
先验,不是随机初始化,数字量级合理)。`best/` 目录 2.3G。

cparam 同一条命令换 `--mode cparam --out .../share_cpu_cparam_smoke`:
`ALIGN_CHECK.json` `PASS: true`,`max_abs_diff: 3.576e-6`,
`max_tok_diff: 1.335e-5`;`best/meta.json` 含 `"param_only": true`。

两次产物留在 NFS:
`pipeline/runs/smoke/share_cpu_{cgen,cparam}_smoke/`。

**旧脚本零改动核验**:
```
git diff --stat
#  pipeline/train/train_causal_callgen.py | 22 +++++++++----
#  run.py                                 | 57 +++++++++++++++++++++++++++++-----
git diff pipeline/train/train_causal_param.py   # 空输出
```

**`run.py` 注册表**:
```
python3 run.py selfcheck
# 74 个已存在任务在主仓「全部就位」;在本工作树里因为第三方 env(appworld/
# alfworld/tales/tau2/toolhop/bfcl/vllm/stb-server)没有软链、报「缺解释器/
# 程序」——这些跟 train-cgen/train-cparam/train-cgen-rows/train-cparam-rows
# 或 train_causal_share.py 一个字都不沾,是全新 git 工作树缺第三方 venv 的
# 通病(cprobe-env/mbert-env 补软链前也一样报;补上之后这两个不再出现在
# 缺失列表里),不是本工单引入的注册表缺陷。
python3 -c "import ops.launch_probe"   # 无输出,退出码 0
python3 run.py show train-cgen --allow-dirty
#   命令: .../cprobe-env/bin/python .../train_causal_share.py --mode cgen '<参数...>'
```

## 三、commit 清单

- `b503e84` T03: train_causal_callgen.build() 加 attn_impl/path 两个关键字参数
- `2e50bfb` T03: 新增缓存复用训练器 train_causal_share.py,run.py 接入 cgen/cparam
- `f40daaa` T03: tests/test_share_trainer.py,spec 12 (a)(b)(c)

## 四、自查发现与存疑

1. **对齐检查的候选抽样绕开了 `share_data.load_events` 的行级流水线**
   (`_align_candidates` 自己按 event 分组 + 全文分词,不调用
   `share_data.load_events(val, limit=0)`)。原因是后者的行级分词发生在
   「取子集之后」,但对齐候选抽样这一步恰恰需要**先看遍全部事件**才能
   取子集(挑出 `<=2048` token 的事件),如果为了抽样先跑一遍
   `load_events(limit=0)` 会连带对全量 val(115,211 行)做行级分词,`--smoke`
   时这笔开销和抽 6 个事件的目的完全不成比例。这段逻辑因此没有直接复用
   `share_data.py`,是我按性能考虑自己写的一段(按 event 分组 + 全文分词
   过滤),不在工单点名的「不许复制」清单(`CALL_SEP`/`MAX_TGT_TOK`/
   `param_prompt_tail`/`param_target`/`MODELS`/`SEED`)里,但请复核这个
   取舍是否可接受。

2. **参照路径的逐 token CE 不是直接调用 `inst_ce`,而是手算同一套公式**
   (`_ref_forward`)。工单/spec 第 9 节字面写「import 旧脚本的 collate、
   inst_ce...得到每行 ce」,但 spec 同一节还要求「逐目标 token 的最大差
   ≤ 3e-4」这个逐 token 粒度的判据——`inst_ce` 本身只回每行 mean CE(见
   `train_causal_callgen.py` 第 231~253 行),没有暴露逐 token 的中间量。
   我的处理是:`_ref_forward` 里手写与 `inst_ce` 完全相同的移位预测 + 掩码
   + 交叉熵公式(只是多留一步 `ce`(逐 token)而不是直接对 `inst_ce` 返回值
   聚合),没有另外调用 `inst_ce` 做双重验证。这条我判断是「工单需求本身
   要求的能力超出了 `inst_ce` 的接口」而不是「我图省事另写一套」,但它确实
   是这张工单里离字面指令最远的一处自主决定,请重点复核公式是否与
   `inst_ce` 逐位等价(cgen/cparam 两个真实冒烟的 `max_abs_diff`/
   `max_tok_diff` 都在 1e-5~1e-6 量级、远低于门槛,是一个间接证据,但不是
   逐行对 `inst_ce` 输出做过的直接断言)。

3. **`--mem-probe` 与 GPU 侧对齐检查、bf16 第二道粗筛(`dev.startswith
   ("cuda")` 分支)在我这边完全没有跑到**——本工单铁律禁止发射 GPU 进程,
   这几段代码按 spec 第 10 节、第 9 节字面写完,CPU 上只验证了
   「`dev.startswith("cuda")` 为假时跳过」这条分支本身不炸,没有验证 cuda
   分支的实际数值(尤其是 `run_mem_probe` 里「把 lr 置 0 做一次 opt.step()
   分配 AdamW 状态、再清空」这套操作在真实优化器上是否如预期)。这部分
   连同下面的「GPU 上要跑的命令」一起交主会话走 gpu-run。

4. **`--mem-probe` 的全量训练集加载不带 `--readonly-env` 过滤**
   (`share_data.load_events(..., ro=None, limit=0)`,main() 第 611 行)。
   spec 没有明确说探针要不要过 readonly 过滤;不过滤会让探针看到的事件
   集合(可能)比真实训练时更大,得到的显存峰值偏保守(不会低估),我认为
   方向安全但不是 spec 点名的行为,列出来备查。

5. **`wall_s`(done 事件)包含 `--mem-probe` 的耗时**——`training_t0` 打在
   `heartbeat.emit(0, steps, "step")` 之后、`--mem-probe` 块之前,所以
   `--mem-probe` 打开时 `wall_s` 会比纯训练时间长。spec 没有精确定义
   `wall_s` 的起止点,这是我的选择(把它当「这次调用总耗时」而不是「纯
   训练耗时」),备查。

6. **发现一个跟本工单无关但值得记的坑**:新建的 git 工作树里,`*-env/`
   这条 `.gitignore` 规则(带斜杠)只匹配真目录,不匹配指向真目录的软链
   ——我在工作树里为了跑测试临时建的 `cprobe-env`/`mbert-env` 软链
   一度会被 `git status`/`git add -A` 当成未追踪的普通文件(不像
   `pipeline/data`/`pipeline/runs` 那两条裸名规则,没有斜杠,软链也认)。
   提交前已经 `rm` 掉这两个软链,没有进任何一次 commit,但后续别的
   worktree 分支要小心同一个坑(不要在工作树里用软链复原 `*-env/` 之外
   的大目录,或者软链之后 `git add` 前先 `git status` 确认)。

## 五、GPU 上要跑的命令(不在本工单,交主会话走 gpu-run)

冒烟档(`launch_probe` 会自动追加 `--smoke`):
```
run_id: ks828b06_gptoss_cgen_smoke / ks828b06_gptoss_cparam_smoke
```
用 `ops/launch_probe.py smoke`(或直接手发)起,产物落
`pipeline/runs/smoke/<run_id>_smoke/`,验收「能跑、能存、日志齐、
ALIGN_CHECK.json PASS」。

速度/显存档(spec 第 10 节,tokyo108 H100,不带 `--smoke`):
```
cprobe-env/bin/python pipeline/train/train_causal_share.py --mode cgen \
  --data pipeline/data/nyapass_aw_v1/gptoss \
  --out pipeline/runs/smoke/ks828b06_gptoss_cgen_speed \
  --max-events 450 --log-every 3 --eval-per-epoch 1 --mem-probe \
  --tok-budget 16384 --base qwen --force
# 另跑一次 --tok-budget 24576;PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# 作为开关一起量(spec 第 10 节)
```
`--mem-probe` 打开时会先对 train 全集跑一遍事件级分词(186,479 行)再
`worst_blocks` 找最坏块,GPU 上这一步比 CPU 上快得多,但仍是最耗时的
前置步骤,排期时按「几分钟」量级预留即可(CPU 上完整跑一次
`share_data.load_events(train, limit=0)` 的量级本身没有单独计时,冒烟档
6 个事件 + 2 个对齐事件的完整命令墙钟在 26~27 秒,含这一步全量分词的
`--mem-probe` 会更长)。

## 六、修复轮 1(评审 finding F1)

工作树:`/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03-fix1`(已删除),
分支不变(`ticket/2026-08-28-wave2/T03`),base 仍是上面记的 `f40daaa`
(检出既有分支,不是新分支),新 head `106ab63`。

### F1:对齐检查参照路径没有 import 调用 `inst_ce`,而是手写同公式的替代实现

**finding 原文的核心质疑**:`_ref_forward` 只手写一套与 `inst_ce` 数学等价
的公式,从未真正调用 `train_causal_callgen.inst_ce`/`train_causal_param.inst_ce`,
和 spec 第 9 节字面「import 旧脚本的 `collate`、`inst_ce`...得到每行 ce」
有出入;而且代码里没有任何一处把 `_ref_forward` 的逐行结果与真正调用
`inst_ce` 的结果做过交叉验证——上一轮唯一相关的测试
`TestPackedForwardMatchesOldPath` 验的是新路径 `block_row_ce` 对 `inst_ce`
的差,验证的是另一条代码路径,不覆盖 `_ref_forward` 这段手写公式本身。

**根因**:`inst_ce` 只回传每行 mean CE(`train_causal_callgen.py` 第
231~253 行 / `train_causal_param.py` 第 197~209 行的局部变量 `ce` 从未
对外暴露),而 spec 同一节还要求逐目标 token 的最大差门槛(≤3e-4),这个
粒度 `inst_ce` 的接口给不出来。上一轮的应对是绕开——整段另写一套「相同
公式」,但从未真正调用过 `inst_ce` 做对照,所以「两套公式等价」只是
未经验证的断言。

**怎么改的(不是打补丁,是把接口缺口用真调用+断言堵死)**:

1. `_ref_forward` 现在真的 import 并调用 `inst_ce_fn = train_causal_callgen.inst_ce`
   / `train_causal_param.inst_ce`,函数返回的 `row_ce` 就是 `inst_ce` 的
   直接返回值(`.tolist()` 之前没有再加工)——这一步满足 spec 第 9 节的
   字面指令,不再是「同公式的另一份实现」。
2. 逐 token 门槛需要的中间量 `inst_ce` 拿不到,所以仍然本地按
   `inst_ce` 完全相同的移位预测 + 掩码 + 交叉熵公式算一份 `ce`(逐 token)
   供 `tok_ce` 用;但每一批处理完之后,立刻断言这份本地公式聚合出的逐行
   结果(`row_ce_local`)与真正调用 `inst_ce` 拿到的 `row_ce_inst` 一致
   (新增常量 `REF_INST_CE_DRIFT_TOL = 1e-6`,同一批数据同一次 `no_grad`
   前向调两遍理论上 bit 级相同,这道容差只防浮点求和顺序的极小抖动,
   比 `--align-tol` 的 2e-5 低一个量级,离真正的公式错位——1e-2 量级——
   还差 1000 倍,不会把结构性错位放过)。不一致就当场 `AssertionError`,
   不会把一个未经验证的手写公式悄悄当成对齐检查的基准。
3. 新增单测 `TestRefForwardUsesInstCe`(`tests/test_share_trainer.py`),
   直接对 `_ref_forward` 断言(不像 (a) 那样只验新路径):调用
   `_ref_forward` 拿到 `row_ref`,再不经过它、独立按同样的分批方式
   (`tcs.REF_BATCH=4`)走一遍旧 `collate` + 直接调用 `old_inst_ce`,
   两边逐行结果用 `assertEqual(diff, 0.0)` 断言完全相等(同一模型同一批
   输入同一次 `no_grad` 前向,理论上无差)——这条测试独立于 `_ref_forward`
   内部的断言,从外部再验一遍同一个性质,cgen/cparam 各一个 test method。
4. 更新了函数 docstring 与模块级 docstring(第 22~28 行)里描述参照路径
   公式的措辞,不再写「自算的逐 token CE,公式与 inst_ce 相同」,改成
   「真正调用的 inst_ce 得到逐行 ce;逐 token 门槛需要的中间量另用同一套
   公式本地算,每批都断言与 inst_ce 的返回值一致」。

只改了这两个文件(`pipeline/train/train_causal_share.py`、
`tests/test_share_trainer.py`),`git diff HEAD --stat` 确认
`train_causal_callgen.py`/`train_causal_param.py` 零改动,未触碰工单
其余任何验收点。

### 怎么验证的

**单元测试**(与工单验收段同一条命令,重跑):
```
cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data \
  tests.test_cparam_assembly tests.test_lora_merge
# Ran 50 tests in 218.148s / OK
```
(48 → 50,多出的 2 个是新增的 `TestRefForwardUsesInstCe.{test_cgen,test_cparam}`;
单独 `-v` 跑过一遍 `tests.test_share_trainer`,7 个 test 全部 `ok`,含这
两个新用例。)

**真实 Qwen3-0.6B-Base CPU smoke 重跑**(工单验收段原始命令,`--force`
覆盖旧产物),核对数字与修复前(上一轮报告第二节)完全一致:

cgen:
```
{
 "PASS": true, "n_events": 2, "n_rows": 75, "n_tgt_tokens": 1551,
 "max_abs_diff": 2.384185791015625e-06,
 "max_tok_diff": 2.193450927734375e-05,
 "baseline_max_abs_diff": 2.1457672119140625e-06, "tol": 2e-05,
 "bf16_mean_abs_diff": null, "bf16_max_abs_diff": null,
 "attn_impl": "sdpa", "mismatch_idx": [],
 "baseline_warn": false, "bf16_warn": false
}
```
`loss` 3.3317 → `val_ce` 1.2026,与上一轮报告的数字逐位相同。

cparam:
```
{
 "PASS": true, "n_events": 2, "n_rows": 75, "n_tgt_tokens": 1090,
 "max_abs_diff": 3.5762786865234375e-06,
 "max_tok_diff": 1.33514404296875e-05,
 "baseline_max_abs_diff": 3.5762786865234375e-06, "tol": 2e-05,
 "bf16_mean_abs_diff": null, "bf16_max_abs_diff": null,
 "attn_impl": "sdpa", "mismatch_idx": [],
 "baseline_warn": false, "bf16_warn": false
}
```
与上一轮报告的数字逐位相同(`max_abs_diff` 3.576e-6、`max_tok_diff`
1.335e-5)。两次运行里 `REF_INST_CE_DRIFT_TOL` 断言均未触发(没有
`AssertionError`,`ALIGN_CHECK.json` 正常写出)。产物覆盖回
`pipeline/runs/smoke/share_cpu_{cgen,cparam}_smoke/`。

**性能影响的对照实验**(finding 没有点名要测,但改动会让 `_ref_forward`
每批多调一次 `inst_ce`,即参照路径的模型前向次数翻倍,主动测了一下量级,
不是靠猜):用 `--align-only`(只跑对齐检查、不进训练/存盘)在同一台机器
上前后各跑一次同一条命令(`--mode cgen --smoke --max-events 6
--align-events 2`),用 `git stash` 切回修复前的代码跑一次、`git stash pop`
恢复后再跑一次:
```
修复前(git stash 后): real 3m30.945s / user 84m56.327s / sys 5m59.441s
修复后(当前代码):     real 6m54.556s / user 171m0.156s / sys 15m15.537s
```
约 2 倍,与「参照路径每批多调一次 `inst_ce`(多一次模型前向)」的理论
预期吻合。这一开销只发生在开训前一次性的对齐检查阶段(由 `--align-events`
控制规模,不随训练数据量增长),不影响 `wall_s`(训练循环计时字段不含
对齐检查)、不影响任何已上报的 `train_log.jsonl` 事件字段。两次测量都在
同一台当前负载中等偏高的登录机上(`uptime` 显示 5/15 分钟负载 13~18,
64 核,同时有其他 wave2 工单的会话在跑),所以两个绝对数字本身(3m30s /
6m54s)不能拿来跟上一轮报告里「26~27 秒」的机器空闲时基线直接比,但
两次前后对照是背靠背在同一时间窗内做的,相对倍数(约 2x)是本次改动的
真实成本,不是机器负载波动造成的假象。

**旧脚本零改动核验**:
```
git diff HEAD -- pipeline/train/train_causal_callgen.py pipeline/train/train_causal_param.py
# 空输出
```

**`run.py` 注册表(未受此次改动影响,复核一遍确认没有连带破坏)**:
```
python3 run.py selfcheck        # 76 任务缺失 14 项,清一色第三方 env
                                  # 符号链接缺失(worktree 通病,与
                                  # train-cgen/train-cparam 无关,同上一轮)
python3 -c "import ops.launch_probe"   # 无输出,退出码 0
python3 run.py show train-cgen --allow-dirty
#   命令: .../cprobe-env/bin/python .../train_causal_share.py --mode cgen '<参数...>'
```

### commit 清单(本轮)

- `106ab63` T03: 修复1 F1 对齐检查参照路径改真调 inst_ce,不再手写替代公式

### 自查发现与存疑(本轮新增)

1. **对性能的取舍**:`_ref_forward` 现在对 `REF_BATCH` 整批、`bs=1` 单行
   基线、cuda 上的 bf16 粗筛三处调用统一生效(它们共用同一个函数),而
   真正门禁 PASS/FAIL 的只有第一处(`REF_BATCH` 那次调用);后两处只用于
   告警(`baseline_warn`/`bf16_warn`),不参与判定。我判断按统一的单一
   函数处理(不为「门禁用」和「告警用」两种调用方式分叉出两套 `_ref_forward`
   实现)更简单、更不容易出现「只在其中一条路径上验证过」的新缺口,所以
   没有只在 `REF_BATCH` 那一次套用真调用,三处都统一享有这个保证,代价
   是三处的前向次数都翻倍。这是我的取舍,不是 finding 点名要求的,列出
   来备查。
2. **`REF_INST_CE_DRIFT_TOL` 的容差值(1e-6)没有专门在真实 GPU 环境上
   验证过**——CPU 上两次真实 smoke 与新单测都在这个容差内通过(且实测
   drift 远小于门槛,CPU 上两次前向理论上应为 bit 级相同),但 GPU 上是
   否会因为不同 kernel 调度出现比 1e-6 更大的抖动没有实测过(本工单铁律
   禁止发射 GPU 进程)。如果 GPU 上触发了这条检查,说明的是「同一批数据
   同一个模型前向两次结果不同」这类内核不确定性问题,而不是逐行公式本身
   错了;届时需要在 GPU 上单独复核这条容差是否需要放宽,不是本轮能验证
   的范围(修复 2 之后,即便真触发,现在也会写出 `ALIGN_CHECK.json` 并
   `sys.exit(2)`,而不是让进程带着未处理的异常崩溃——排查时能拿到结构化
   产物)。

## 七、修复轮 2(评审 finding N1)

工作树:`/home/y-guo/reproduce/new1-wt/2026-08-28-wave2-T03-fix2`(已删除),
分支不变(`ticket/2026-08-28-wave2/T03`),base 仍是工单原始 base
`2216c44d50838e6df6d3f8f78b31ca955998e520`(检出既有分支,不是新分支),
上一轮 head `106ab63`,新 head `312038d`。

### N1:`REF_INST_CE_DRIFT_TOL` 校验用裸 `assert` 实现,绕开了本文件自己的
失败上报通道

**finding 原文的核心质疑**:修复 1 新增的 `assert drift <=
REF_INST_CE_DRIFT_TOL` 是判定「参照基线是否可信」的唯一运行时校验,但它
没有走 `run_align_check` 里其余所有校验一致采用的模式——算出结果、写进
`ALIGN_CHECK.json`、打印诊断信息、`sys.exit(2)`——而是用了一个裸
`assert`。两个后果:(1)`-O`/`PYTHONOPTIMIZE` 下 Python 会把这条 assert
整体剥掉,F1 修复要堵的口子会静默重新打开;(2)真触发时(报告已自陈
1e-6 容差没在真实 GPU 上跑过)进程会以裸 `AssertionError` traceback
崩溃,不会像同一函数里其它失败分支那样先写出 `ALIGN_CHECK.json`。

**根因**:F1 修复时把这道校验实现成了 Python 语言层面的 `assert` 语句,
而不是这个文件自己的失败上报机制(`if 条件: 写报告 + 打印 + sys.exit(2)`)
——`assert` 本身就是一种可以被解释器优化开关整体禁用的机制,拿它做生产
代码里唯一判定基线可信度的运行时校验,和文件里其余所有校验的处理方式不
一致,是这次新引入的、和既有约定拧着的写法。

**怎么改的(不是打补丁,是把错误逻辑——裸 assert——直接换成正确逻辑）**:

1. 新增异常类 `RefBaselineDriftError(RuntimeError)`(定义在
   `REF_INST_CE_DRIFT_TOL` 常量后面),docstring 写清楚为什么不能用裸
   `assert`。
2. `_ref_forward` 里把 `assert drift <= REF_INST_CE_DRIFT_TOL, (...)`
   改成 `if drift > REF_INST_CE_DRIFT_TOL: raise RefBaselineDriftError(...)`
   ——`if`/`raise` 不受 `-O`/`PYTHONOPTIMIZE` 影响,消息文案原样保留。
3. `run_align_check` 的 `try/finally` 中间新增一个
   `except RefBaselineDriftError as e:` 分支,按文件里其余所有失败分支
   同样的模式处理:写 `report = dict(PASS=False,
   stage="ref_forward_drift", error=str(e),
   ref_inst_ce_drift_tol=REF_INST_CE_DRIFT_TOL)`,落盘
   `ALIGN_CHECK.json`,打印诊断(说明排查方向:两套公式是否等价,或者
   该环境是否需要放宽容差),再 `sys.exit(2)`。三处调用 `_ref_forward`
   的地方(`REF_BATCH` 整批、`bs=1` 单行基线、cuda 上的 bf16 粗筛)共用
   这一个 `except`,不管哪一处触发都走同一条上报路径;`finally` 块(恢复
   精度设置、删临时文件、`model.train()`)在 `sys.exit(2)` 抛出
   `SystemExit` 冒泡的过程中依然会执行,不受这次改动影响。
4. 顺带更新了 `_ref_forward` 与模块级 docstring 里提到「不一致就当场
   `AssertionError`」的措辞,改成准确描述新流程(抛 `RefBaselineDriftError`
   → `run_align_check` 捕获 → 结构化上报)。
5. 新增单测 `TestRunAlignCheckHandlesRefBaselineDriftError`
   (`tests/test_share_trainer.py`),两个 test method:
   - `test_ref_forward_raises_real_exception_not_assert`:给
     `train_causal_callgen.inst_ce` 打 monkeypatch(返回值统一加
     1.0,远超 1e-6 容差),直接对 `_ref_forward` 断言抛出
     `tcs.RefBaselineDriftError`——证明这是一个真异常,不是会被 `-O`
     剥除的 `assert`。
   - `test_run_align_check_reports_drift_error_instead_of_crashing`:给
     `tcs._ref_forward` 打 monkeypatch(直接抛
     `RefBaselineDriftError("测试注入的漂移")`),调用
     `run_align_check(...)`,断言抛出 `SystemExit` 且 `code == 2`,且
     `ALIGN_CHECK.json` 落盘、`PASS` 为假、`stage ==
     "ref_forward_drift"`、`error` 字段含注入的消息——证明失败会走结构化
     上报通道,不是让异常原样冒出去变成未处理的 traceback。

只改了这两个文件(`pipeline/train/train_causal_share.py`、
`tests/test_share_trainer.py`),`git diff HEAD --stat` 确认
`train_causal_callgen.py`/`train_causal_param.py` 零改动,未触碰工单
其余任何验收点,也没有借机做 finding 没点名的重构。

### 怎么验证的

**单元测试**(工单验收段同一条命令,重跑):
```
cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data \
  tests.test_cparam_assembly tests.test_lora_merge
# Ran 52 tests in 230.616s / OK
```
(50 → 52,多出的 2 个是新增的
`TestRunAlignCheckHandlesRefBaselineDriftError.{test_ref_forward_raises_real_exception_not_assert,
test_run_align_check_reports_drift_error_instead_of_crashing}`;单独
`-v` 跑过一遍 `tests.test_share_trainer`,9 个 test 全部 `ok`,含这两个
新用例,新用例的打印输出确认了预期行为:
```
{
 "PASS": false,
 "stage": "ref_forward_drift",
 "error": "测试注入的漂移",
 "ref_inst_ce_drift_tol": 1e-06
}
对齐检查 FAIL:参照路径自检失败,拒绝开训。
  测试注入的漂移
  排查:_ref_forward 里本地逐 token 公式与 inst_ce 的移位/掩码/聚合逻辑是否等价;...
```

**真实 Qwen3-0.6B-Base CPU smoke 重跑**(工单验收段原始命令,`--force`
覆盖旧产物),核对数字与修复前(上两轮报告)完全一致:

cgen:`PASS: true`,`max_abs_diff: 2.384185791015625e-06`,
`max_tok_diff: 2.193450927734375e-05`,`baseline_max_abs_diff:
2.1457672119140625e-06`;`loss` 3.3317 → `val_ce` 1.2026。
cparam:`PASS: true`,`align_maxdiff: 3.5762786865234375e-06`
(`train_log.jsonl` 的 `start` 事件字段,与 `ALIGN_CHECK.json` 的
`max_abs_diff` 同一个数);`loss` 5.6631 → `val_ce` 1.9795。
两次运行里新的 `except RefBaselineDriftError` 分支均未触发(没有走这条
路径,`_ref_forward` 内部的 `if`/`raise` 没有跳),`ALIGN_CHECK.json` 走
的是正常 `PASS=true` 分支,产物覆盖回
`pipeline/runs/smoke/share_cpu_{cgen,cparam}_smoke/`。

**grep 检查**(工单验收段原始命令,重跑):
```
grep -n "heartbeat.emit" pipeline/train/train_causal_share.py
# 664/740/784,三处不变
grep -n "sdpa_kernel" pipeline/train/train_causal_share.py
# 命中不变
grep -n "^\s*assert " pipeline/train/train_causal_share.py
# 空输出——全文件不再有裸 assert
```

**旧脚本零改动核验**:
```
git diff HEAD -- pipeline/train/train_causal_callgen.py pipeline/train/train_causal_param.py
# 空输出
```

**`run.py` 注册表(未受此次改动影响,复核一遍确认没有连带破坏)**:
```
python3 run.py selfcheck        # 76 任务缺失 14 项,清一色第三方 env
                                  # 符号链接缺失(worktree 通病,与
                                  # train-cgen/train-cparam 无关,同前两轮)
python3 -c "import ops.launch_probe"   # 无输出,退出码 0
python3 run.py show train-cgen --allow-dirty
#   命令: .../cprobe-env/bin/python .../train_causal_share.py --mode cgen '<参数...>'
```

`git diff HEAD --stat`:
```
 pipeline/train/train_causal_share.py | 47 +++++++++++++++++----
 tests/test_share_trainer.py          | 81 ++++++++++++++++++++++++++++++++++++
 2 files changed, 121 insertions(+), 7 deletions(-)
```

### commit 清单(本轮)

- `312038d` T03: 修复2 N1 对齐检查参照基线自检改真异常+结构化上报,不再用裸 assert

### 自查发现与存疑(本轮新增)

1. **除了 `try/finally` 之间新增的 `except RefBaselineDriftError`,没有
   动 `run_align_check` 其余任何逻辑**——正常通过/正常 FAIL(逐行差超
   `--align-tol` 或逐 token 差超 `TOK_DIFF_TOL`)两条既有路径的代码与行为
   逐字未变,只是新增了第三条失败路径(参照基线自检失败)接进同一套
   report/打印/sys.exit(2) 骨架,没有借这次改动顺带重构其余分支,符合
   finding 只要求修这一处的范围限定。
2. **`except RefBaselineDriftError` 分支写的 report dict 字段与正常路径
   的 report 字段不完全相同**(少了 `n_events`/`n_rows`/`max_abs_diff` 等
   字段,因为这些值在参照基线自检失败时根本没算出来;多了
   `stage`/`ref_inst_ce_drift_tol` 两个字段区分这是哪一类失败)——两条
   路径的 `ALIGN_CHECK.json` schema 因此不完全一致(共同点只有 `PASS` 一
   定存在)。finding 只要求「走同一套写报告+打印+退出的通道」,没有要求
   两类失败的字段 schema 完全统一;我判断如果消费 `ALIGN_CHECK.json` 的
   下游代码(目前没有,人工读)以后要机器解析这个文件,应该先判断
   `PASS` 再按需读其余字段,不应假设字段集合固定,这是我的取舍,列出来
   备查,不属于本次要解决的范围。
3. **`REF_INST_CE_DRIFT_TOL` 在真实 GPU 上是否需要放宽依然没有验证**
   (与上一轮自查第 2 条相同,本工单铁律禁止发射 GPU 进程,没有变化)——
   区别只在于:上一轮如果 GPU 上真触发这条检查,进程会带着未处理的
   `AssertionError` 崩溃;这一轮触发后会写出结构化 `ALIGN_CHECK.json` 再
   `sys.exit(2)`,排查时能看到 `stage: "ref_forward_drift"` 和具体的
   drift 数值,不再是裸 traceback。
