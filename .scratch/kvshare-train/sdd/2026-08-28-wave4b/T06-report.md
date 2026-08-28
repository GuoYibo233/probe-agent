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
