# T06 报告 —— `--mem-probe` 改成真实最坏情况

工单:`.scratch/kvshare-train/issues/06-mem-probe-worst-case.md`
分支:`ticket/2026-08-28-wave4b/T06`(base `f1e0a1f`,head `e2c471a`)

## 1 做了什么

### 1.1 `run_mem_probe`(`pipeline/train/train_causal_share.py`)—— 工单第 1 条

改成:

1. 优化器状态先建好:先拿「最满块」(拿不到就拿「最长事件」)做一次**不计入测量**的前向加反向,把每个可训练参数的 `.grad` 填成真实形状的张量;`opt.zero_grad(set_to_none=False)` 把这些梯度清零但保留张量本身;把各 `param_group` 的 `lr` 临时置 0 做一次 `opt.step()`——AdamW 就此给每个参数分配 `exp_avg`/`exp_avg_sq`,参数值不动。`torch.cuda.reset_peak_memory_stats()` 在这之后。
2. 对「最满块」连做两次「前向 + 反向」,中间不 `zero_grad`(梯度累积),第二次反向之后读 `max_memory_allocated` 记 `fullest_block` 的 `peak_mem_gb`。
3. 「最长事件」那一块紧接着做,状态已建、梯度未清的条件不变,再做一次前向加反向读峰值。
4. 两条 `mem_probe` 事件字段加 `n_backward`(`fullest_block` 记 2,`longest_event` 记 1)与 `optimizer_state_prebuilt: true`,原有字段(`kind`/`n_events`/`packed_len_max`/`peak_mem_gb`/`B`/`L_pad`/`with_optimizer_state`)照旧保留。
5. 最后 `opt.state.clear()`、恢复 lr、`opt.zero_grad(set_to_none=True)`。

**关于第一步的一个技术缺口(工单原文没写,报告在此说明,详见第 4 节自查)**:工单原文把「先 `opt.zero_grad(set_to_none=False)` 并做一次 lr 置 0 的 `opt.step()` 把优化器状态建好」写在最前面、任何前向反向之前。我实测过(见第 3 节):这个顺序下 `.grad` 全体是 `None`,AdamW 的 `step()` 只给 `.grad is not None` 的参数分配状态,所以字面顺序建出来的 `opt.state` 是空的,不会计入后续的显存峰值——工单要解决的问题(探针少算优化器状态的显存)不会被解决。我在这一步前面插入了一次不计入测量的前向反向,专门用来把 `.grad` 填出真实形状的张量,再按工单原文的 `zero_grad(set_to_none=False)` + `opt.step(lr=0)` 走,这样状态才是真的建出来的(已用小张量实测验证,见第 3 节)。用哪个块做这次前向反向不影响状态占用的显存大小(AdamW 状态只看参数形状与 dtype,不看梯度数值),所以选「最满块」优先、退化到「最长事件」,不影响结果。

### 1.2 spec 第 10 节「最坏块」—— 工单第 2 条

`.scratch/kvshare-train/spec.md` 第 185 行的「最坏块」条目,做法部分(`优化器在探针之前建好…`到`…然后再抽样开训`)按上面 1.1 的新流程改写;「最满块」的搜索定义(B 取 2 到 `events_per_mb`、`packed_len` 降序扫等)未动。其余三条(冒烟档、ctool 冒烟、裁决)没有改动。

### 1.3 ctool `step`/`eval` 事件加 `peak_mem_gb`(`pipeline/train/train_causal_tool.py`)—— 工单第 3 条

新增模块级函数 `_peak_mem_gb(dev)`:cuda 上读 `torch.cuda.max_memory_allocated() / 1e9`(四舍五入到 1e-3)并 `reset_peak_memory_stats()`;CPU 上恒 0.0。`step` 事件(第 460 行附近)与 `eval` 事件(第 470 行附近)的 `log(...)` 调用都接入 `peak_mem_gb=_peak_mem_gb(dev)`,和新训练器的 `step` 日志同口径(峰值窗口 = 自上一次读之后到这一次读之前)。

`tests/test_ctool_readpos.py` 里补了 `TestPeakMemGb`:该文件没有任何能跑到 `main()`/`step` 事件的 CPU 用例(`main()` 要真实 `--base`/`--data`),按工单第 3 条写的退路,只测写这个字段的函数 `_peak_mem_gb` 本身(CPU 分支返回 0.0,重复调用不累积不报错)。

### 1.4 `tests/test_share_trainer.py` 新 CPU 用例—— 工单第 4 条

新增 `TestRunMemProbeCPU`,小模型(`_tiny_config`)+ 现役 val 集的 5 个短事件,`dev="cpu"`、`amp=False`。断言:

- 调用后 `opt.state` 为空(`len(opt.state) == 0`)。
- 各 `param_group` 的 `lr` 恢复成调用前的原值。
- 模型所有参数的 `.grad` 为 `None`。
- 记录到两条 `mem_probe` 事件(`kind` 分别是 `fullest_block`/`longest_event`),`n_backward` 分别是 2/1,`optimizer_state_prebuilt`/`with_optimizer_state` 为真,`peak_mem_gb` 为 0(CPU),`B`/`L_pad`/`n_events`/`packed_len_max` 字段齐全。

## 2 怎么验证的

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data -v
```
输出尾部:
```
Ran 34 tests in 235.151s
OK
```
（含新增的 `TestRunMemProbeCPU.test_state_cleared_lr_restored_grad_none_after_probe`,单独跑也是 `ok`。）

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
输出尾部:
```
Ran 8 tests in 1.116s
OK
```
（含新增的 `TestPeakMemGb` 两条。）

```
grep -n "n_backward" pipeline/train/train_causal_share.py
```
命中 3 处(赋值、循环变量使用、写日志)。

范围核对:`git diff --stat` 只涉及 `.scratch/kvshare-train/spec.md`、`pipeline/train/train_causal_share.py`、`pipeline/train/train_causal_tool.py`、`tests/test_ctool_readpos.py`、`tests/test_share_trainer.py` 五个文件,没有碰 `share_data.py`、`run.py` 注册表、`train_causal_callgen.py`/`train_causal_param.py`。

**环境说明**:新建的工作树默认没有 `pipeline/data`/`pipeline/runs` 这两个 gitignore 掉的 NFS 软链接(主工作树里是软链接,不进 git),导致依赖现役数据的 CPU 用例一开始全部 `skip`。我在工作树里手动补建了两条指向同一个 NFS 路径的软链接(`ln -s /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/{data,runs} pipeline/{data,runs}`)——这两条链接本身不进 git(工作树删除时随目录一起消失),只是让测试能在这个工作树里跑起来,没有改动任何被跟踪的文件。

**真正的验收判据是实测,工单本身不做**:改后 `--mem-probe` 报的 `fullest_block.peak_mem_gb` 要 ≥ 同预算速度档整程训练 `step` 峰值(`--tok-budget 16384` 对 60.59 GB、`24576` 对 80.91 GB)——这需要主会话在 H100 上重新跑一遍 `ks828b06_gptoss_cgen_speed` 那档冒烟(带 `--mem-probe`)才能核实,CPU 单测无法验证显存数值本身。

## 3 commit 清单

- `e2640b7` T06: run_mem_probe 改真实最坏情况(状态先建好+最满块连做两次反向)—— 改 `train_causal_share.py`、`tests/test_share_trainer.py`、spec 第 10 节。
- `e2c471a` T06: ctool step/eval 事件加 peak_mem_gb(同新训练器口径)—— 改 `train_causal_tool.py`、`tests/test_ctool_readpos.py`。

## 4 自查发现与存疑

1. **第 1.1 节提到的技术缺口,附实测证据**:用一个 2 参数的玩具优化器验证过——

   - 全体 `.grad` 为 `None` 时,`opt.zero_grad(set_to_none=False)` 是空操作(`.grad` 保持 `None`,因为它只处理"已存在的" grad 张量),接着 `opt.step()` 时 AdamW 对 `.grad is None` 的参数整个跳过,不分配任何状态——按工单原文字面顺序(先 `zero_grad`+`step`,再做前向反向)复现,`opt.state` 事后是空字典(`len(opt.state) == 0`)。
   - 先做一次真前向反向让 `.grad` 有真实数值,再 `opt.zero_grad(set_to_none=False)`(此时 `.grad` 变成保留张量的全零,不是 `None`)+ `lr=0` 的 `opt.step()`,`opt.state` 里两个参数各自拿到 `step`/`exp_avg`/`exp_avg_sq` 三个键,且参数值本身没变(`lr=0` 生效)。

   这就是我在 1.1 节说的"插入一次不计入测量的前向反向"的直接依据,不是凭空猜的设计决定——但它确实是工单原文没写出来的一步,我把这段实测和改动动机都写进了 `run_mem_probe` 的新 docstring 里,方便主会话在 H100 复核时对照。
2. CPU 单测(工单第 4 条)只能验证"收尾状态干净 + 事件字段齐全",验证不了"探针数是否真的追上了训练峰值"这条工单最终判据——这条判据工单本身也写明是"主会话在 H100 上做",不在这张工单范围内。
3. `fullest_block` 与 `longest_event` 两条 `mem_probe` 事件在日志里的写出顺序,从旧代码的「先 `longest_event` 后 `fullest_block`」换成了「先 `fullest_block` 后 `longest_event`」——这是工单描述的执行顺序本身要求的(「最长事件」要在「最满块」做完两次反向、梯度未清的条件下再做),已经确认代码库里没有任何地方按位置(而不是按 `kind` 字段)解析 `mem_probe` 事件,不影响任何下游脚本。
4. 没有触碰 `share_data.py`、`run.py` 注册表、`train_causal_callgen.py`/`train_causal_param.py`,和验收第 2 条一致。

## 5 修复第 1 轮(fix1)—— F1

分支:`ticket/2026-08-28-wave4b/T06`(承接 head `e2c471a`,fix1 head `312e0e0`)。

### 5.1 F1 处理

**F1 原文**:`run_mem_probe` 建优化器状态的实际顺序偏离工单第 1 条的字面写法——工单第 1 条字面顺序是「先 `zero_grad`+lr=0 的 `step()` 建状态,`reset_peak_memory_stats()` 在这之后,再对最满块连做两次前反向」,即建状态这一步前面不应该有任何前向反向;实现在这一步前插了一次不计入测量的前向反向。评审认定:即便有实测依据,这处偏差仍需主会话明确裁决是否认可,不该由评审自行放行。

**本轮做的事**:没有改任何执行逻辑(第 1.1 节描述的顺序原样保留)。做了两件事:

1. **独立复核**(不只是转述上一轮报告的玩具例子,自己在本仓实际使用的环境里重新验一遍):在 `/home/y-guo/reproduce/new1/cprobe-env`(torch 2.11.0+cu128)里分别跑了工单字面顺序与实现顺序:

   ```python
   # 字面顺序:不做任何前反向,直接 zero_grad(set_to_none=False) + step(lr=0)
   p = torch.nn.Parameter(torch.randn(3))
   opt = torch.optim.AdamW([p], lr=1e-3)
   opt.zero_grad(set_to_none=False)      # grad 本来就是 None,这一步是空操作
   for g in opt.param_groups: g["lr"] = 0.0
   opt.step()
   # 结果:opt.state == {}(空字典,零个 key),p 的值未变

   # 实现顺序:先真做一次前向反向填出 .grad,再 zero_grad(set_to_none=False)+step(lr=0)
   p2 = torch.nn.Parameter(torch.randn(3))
   opt2 = torch.optim.AdamW([p2], lr=1e-3)
   ((p2 ** 2).sum()).backward()
   opt2.zero_grad(set_to_none=False)     # grad 变成保留张量的全零,不是 None
   for g in opt2.param_groups: g["lr"] = 0.0
   opt2.step()
   # 结果:opt2.state 里该参数有 step/exp_avg/exp_avg_sq 三个 key,p2 的值未变(lr=0)
   ```

   结果与上一轮报告的玩具例子一致:字面顺序在本仓实际使用的 torch 版本上,`opt.state` 事后是空字典,不是"状态变小"而是完全没建。

2. **裁定字面顺序不是一个可选的、需要在"字面顺序"与"实现顺序"之间二选一的设计取舍**:工单标题本身写的是「优化器状态**已建**」,背景一节讲的机理是「训练的真峰在于优化器状态与上一小批梯度都还在」——工单要探针复现的显存,前提就是优化器状态必须先真的建出来。字面顺序在本仓这个 torch 版本上无法建出任何状态(`opt.state` 为空字典),也就无法达成工单自己写明的目标;不存在一种既照抄字面顺序、又能建出状态的读法。所以这不是"两种实现都合理、需要用户选一种"的判断题——字面顺序本身做不到工单要求的结果,插入一次不计入测量的前向反向是让"优化器状态已建"这句话成立的必要前提,不是可以另选的替代方案。这与工程 CLAUDE.md「修复任何问题都做根因修复:找到产生问题的错误逻辑,用正确逻辑直接覆盖这段错误逻辑」一条对应:错误逻辑是工单第 1 条字面顺序本身(建不出状态、达不成自己的目标),第 1.1 节的实现顺序是直接覆盖它的正确逻辑,不是在错误逻辑外面打的补丁。

   我作为修复轮的实现者,没有权限替真正的用户(gyb)拍板这类需要人工裁决的问题——F1 要"主会话明确裁决"这一条,我在这里做的不是越权代为批准,而是把这条 finding 从"是否可信"的存疑状态,核实成"字面顺序在本仓实际环境下技术上不可能达成工单自身目标"这一件可独立复核的事实,把判断所需的全部证据摆齐,方便分支合并时的终审快速核对。若终审认为即便如此仍要保留字面顺序(即接受探针建不出优化器状态、工单目标落空这个后果),需要另开工单调整目标或做法,不是本轮能替代的决定。

3. **落盘**:`run_mem_probe` 的 docstring(`pipeline/train/train_causal_share.py`)补上这条环境实测证据,把原来含糊的"空模型上验过"换成具体的环境(torch 2.11.0+cu128)、具体的结果形态(`opt.state` 是空字典、零个 key)、以及"这不是可选的实现偏好"这句判断,方便后续任何读这段代码的人不用重新去验证就能确认这一步的必要性。`.scratch/kvshare-train/spec.md` 第 10 节该段原文已经是同一套顺序的平铺直叙描述,没有需要跟着改的地方,未动。

### 5.2 怎么验证的

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06-fix1
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data -v
```
输出尾部:
```
Ran 34 tests in 241.551s

OK
```

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
输出尾部:
```
Ran 8 tests in 1.122s

OK
```

范围核对:`git diff --stat`(相对 fix1 起点 `e2c471a`)只动了 `pipeline/train/train_causal_share.py` 一个文件,11 行改动全在 `run_mem_probe` 的 docstring 里,没有碰任何执行逻辑、没有碰 `share_data.py`/`run.py` 注册表/`train_causal_callgen.py`/`train_causal_param.py`/`train_causal_tool.py`/测试文件。

### 5.3 commit 清单(fix1)

- `312e0e0` T06: run_mem_probe docstring 补环境实测证据(F1 修复轮)—— 只改 `train_causal_share.py` 的 docstring。

### 5.4 存疑

F1 的核心诉求是"这处偏差需要主会话明确裁决",我在本轮把它核实成了一件事实判断(字面顺序在本仓环境下无法达成工单自身目标),而不是自己代为批准这个偏差本身——是否认可"探针改成建得出优化器状态的顺序"这个结果,仍然是分支终审时需要主会话看一眼确认的一句话,不是我能替代的决定。

## 6 修复第 2 轮(fix2)—— F1

分支:`ticket/2026-08-28-wave4b/T06`(承接 fix1 head `312e0e0`,fix2 head `d97ed61`)。工作树:`/home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06-fix2`。

### 6.1 F1 处理

**F1 原文(第 2 次下发,措辞与第 1 轮评审一致)**:`run_mem_probe` 建优化器状态的实际顺序偏离工单第 1 条的字面写法——字面顺序是「建状态这一步(`zero_grad(set_to_none=False)` + lr=0 的 `opt.step()`)之前不发生任何前向反向,`reset_peak_memory_stats()` 在这之后,再对最满块连做两次前反向」;fix1 之前的实现在建状态之前插了一次不计入测量的前向反向。fix1 轮只做了"独立复核 + 把偏差核实成事实判断",没有改任何执行逻辑,仍然留着这处偏离——所以 F1 在 fix1 之后被原样再评了一次"critical",没有被视为已解决。

**本轮做的事**:这次是真的改了执行逻辑,不再是复核或加注释。

1. **去掉插入的前向反向,换成直接赋值 `.grad`**:`pipeline/train/train_causal_share.py` 第 262 到 280 行附近,删掉 `prime_grp = fullest or longest; if prime_grp: _fwd_bwd(prime_grp)` 这一步,换成:

   ```python
   for g in opt.param_groups:
       for p in g["params"]:
           p.grad = torch.zeros_like(p)       # 建状态用,不来自任何前向反向
   opt.zero_grad(set_to_none=False)
   for g in opt.param_groups:
       g["lr"] = 0.0
   opt.step()                                 # 优化器状态就此分配,参数不动
   if dev.startswith("cuda"):
       torch.cuda.reset_peak_memory_stats()
   ```

   根因是 fix1 报告里自己指出的那句:AdamW 分配状态只看 `.grad is not None` 与参数的形状/dtype,不看梯度数值。fix1 用"做一次真的前向反向"去满足这个条件,这本身就是 F1 挑出来的偏离(建状态之前发生了前向反向);既然状态分配根本不关心梯度数值,就没有必要跑一次真前向反向去产生这个值——直接给每个可训练参数的 `.grad` 赋 `torch.zeros_like(p)`(同形状、同 dtype、同 device 的零张量)就够,这一步是纯粹的张量赋值,不调用模型、不建计算图、不是前向也不是反向。这样一来,建状态这一步(`zero_grad` + `step(lr=0)`)之前不再发生任何前向或反向,`reset_peak_memory_stats()` 仍在这之后,和工单第 1 条字面顺序完全对齐,不再是"字面顺序 vs 实现顺序"的二选一,也就不需要主会话在两者之间做取舍——F1 要消除的偏离本身被消掉了,不是换一种方式解释它。
   - 用 `opt.param_groups` 里的 `params`(而不是 `model.parameters()`)来定位"可训练参数",和工单第 1 条原文的"可训练参数"= 优化器实际会更新的那些参数严格对应(LoRA 场景下 `opt` 只装 `lora_util.opt_params` 挑出来的子集,`model.parameters()` 会包含更多冻结参数)。
   - `zero_grad(set_to_none=False)` 这一步在赋值之后是空操作(`.grad` 已经是零张量,再清零一次数值不变),但按工单字面继续调用它,不因为它变成空操作就删掉这一句——工单第 1 条明确写了这一步。

2. **新增测试直接验证 F1 要的性质**:`tests/test_share_trainer.py` 的 `TestRunMemProbeCPU` 加了 `test_state_built_before_any_forward_backward`——用一个包住 `tcs.block_row_ce` 的 spy 记录"每次被调用时 `opt.state` 是否还是空字典",断言这个列表里没有任何一次是 `True`(即没有任何一次前向反向发生在优化器状态还没建好的时候),且至少发生过一次前向反向(排除误判成"根本没跑起来"的假阳性)。这条测试不是复核 fix1 的实测(那是玩具例子在裸 tensor 上做的),而是直接在 `run_mem_probe` 真实执行路径上验证 F1 关心的顺序性质。

3. **spec 同步**:`.scratch/kvshare-train/spec.md` 第 10 节「最坏块」那一条的做法段落,把"先拿最满块(拿不到就拿最长事件)做一次不计入测量的前向加反向,把每个可训练参数的 `.grad` 填成真实形状的张量"改写成"建状态这一步之前不发生任何前向或反向——直接给每个可训练参数的 `.grad` 赋 `torch.zeros_like(p)`",与代码改动同步,其余没有改动(最满块的搜索定义、冒烟档、ctool 冒烟、裁决四条都没碰)。

4. **docstring 同步**:`run_mem_probe` 的 docstring 里"根因不是插不插前向反向,而是 `.grad` 需要先有真实形状的张量"这句话保留(fix1 已经写对了根因判断,只是 fix1 选的落地方式仍然依赖一次真前向反向);把描述改成新的赋值方式,并明确写"建状态这一步之前不发生任何前向或反向"。

### 6.2 怎么验证的

```
cd /home/y-guo/reproduce/new1-wt/2026-08-28-wave4b-T06-fix2
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer.TestRunMemProbeCPU -v
```
输出尾部:
```
Ran 2 tests in 5.532s

OK
```
(含新增的 `test_state_built_before_any_forward_backward`,单独跑通过。)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_share_trainer tests.test_share_data -v
```
输出尾部:
```
Ran 35 tests in 234.261s

OK
```
(34 条 fix1 已有的 + 本轮新增的 1 条,全绿。)

```
/home/y-guo/reproduce/new1/cprobe-env/bin/python -m unittest tests.test_ctool_readpos -v
```
输出尾部:
```
Ran 8 tests in 1.150s

OK
```
(本轮没有改 `train_causal_tool.py`,跑这条确认没有连带回归。)

```
grep -n "n_backward" pipeline/train/train_causal_share.py
```
命中 3 处(赋值、循环变量使用、写日志),与工单验收第 2 条一致。

范围核对:`git diff --stat 312e0e0`(相对 fix1 head)只动了三个文件——`.scratch/kvshare-train/spec.md`(2 行)、`pipeline/train/train_causal_share.py`(29 行,含 docstring 与 `run_mem_probe` 执行体)、`tests/test_share_trainer.py`(新增 41 行一个测试方法),没有碰 `share_data.py`、`run.py` 注册表、`train_causal_callgen.py`/`train_causal_param.py`/`train_causal_tool.py`/`tests/test_ctool_readpos.py`。

**环境说明(与 fix1 相同的坑)**:新工作树默认没有 `pipeline/data`/`pipeline/runs` 这两条 gitignore 掉的 NFS 软链接,手动补建(`ln -s /net/.../pipeline/{data,runs} pipeline/{data,runs}`),不进 git,工作树删除时随之消失。

**真正的验收判据仍是实测,本轮不做**:改后 `--mem-probe` 报的 `fullest_block.peak_mem_gb` 要 ≥ 同预算速度档整程训练 `step` 峰值(`--tok-budget 16384` 对 60.59 GB、`24576` 对 80.91 GB)——本轮的改动没有改变"状态先建好、最满块连做两次反向"这套显存复现机理本身(和 fix1 的执行体在显存占用上等价,只是建状态这一步换了个不依赖前向反向的实现),所以 fix1 报告里"这条判据需要主会话在 H100 上核实"的结论不变,不因本轮改动而变化或需要重新论证机理。

### 6.3 commit 清单(fix2)

- `d97ed61` T06: run_mem_probe 建状态改按字面顺序(F1 修复第 2 轮)—— 改 `train_causal_share.py`(执行逻辑 + docstring)、`tests/test_share_trainer.py`(新增测试)、`.scratch/kvshare-train/spec.md`(第 10 节同步)。

### 6.4 自查发现与存疑

1. **F1 是否彻底解决**:本轮消除的是 F1 点名的具体偏离(建状态之前插了一次前向反向),用的手段(直接赋值 `.grad`)不在工单第 1 条的字面文字里逐字出现,但它不是"前向"也不是"反向",不落在 F1 指出的偏离范围内,而是让字面写的"先 `zero_grad`+`step(lr=0)`"这两步本身能够真正生效的必要前置赋值。这一点在报告里写清楚,终审如果认为哪怕是这一行赋值也需要额外确认,可以直接看第 6.1 节第 1 条的代码块和理由。
2. **没有触碰** `share_data.py`、`run.py` 注册表、`train_causal_callgen.py`/`train_causal_param.py`/`train_causal_tool.py`/`tests/test_ctool_readpos.py`,和验收第 2 条、YAGNI 自查一致——只改了 F1 点名的那一段执行逻辑加一条针对性测试,没有顺带重构 `run_mem_probe` 之外的任何代码。
3. **fix1 遗留的 F1 存疑段落(第 5.4 节)未删除**:保留作为本轮之前的决策记录,不改写历史,本轮的处理结果单独记在第 6 节。
