# 活跑注入线设计（2026-08-01，用户批准立项）

用户裁决（2026-08-01 对话）：回放注入的"合并缓存→续写→打分"三步**放弃**；
转建**分段生成的实时流程**——整道题活着跑，探针实时出手、实时注入，跑完整道题
看成败。评测全程不许知道预测对错：出手就执行、执行返回什么就注什么（报错也注）。

## 1 量什么

gpt-oss-120b 在 AppWorld 官方分区上整题活跑。每题两类数：

- **任务成败**：`world.evaluate()` 的结构化结果（活跑侧存 dict，不存 str）。
- **整题 token 账**：每步每段请求的 prompt/completion token 数逐段累加；
  触发后被丢弃的溢出文本单独记（部署总账两口径：billed=全部生成、kept=保留部分）。

对照 = 已采的 `envs/runs/w0_aw_official/appworld_gptoss` 轨迹（同贪心解码、同
SYSTEM、同 max_steps）。**两处不可比处要在报告里带上**：服务条件不同批次；
harmony 模板日期行不同（采集 2026-07-31，活跑是当天）。另留 `--no-probe` 臂：
同一条 completions 路径、不挂探针，用于隔离"自拼前缀路径本身"的偏差（回放线
nofill 的活跑版）。

## 2 一步之内怎么跑

1. 消息历史照采集脚本拼（SYSTEM 逐字回源核对；思考不回灌）。
2. harmony 前缀走 completions 端点自拼（chat 端点做不到中途续写——rebuild.py
   文件头有论证）。日期用当天，不钉采集日。
3. **分段生成**：每次向 vLLM 要 `--chunk-tokens`（默认 64）个 token，贪心、
   stop=`<|return|>`，文本逐段累积。
4. 每凑出一个新的句子级切口（`rules.boundaries` 同款正则），把
   `assemble(task, hist, thinking[:cut])`（与训练数据同一拼法：HIST_ROUNDS=3、
   RESULT_CAP=400）发给探针服务打分；置信度 = softmax(logits/T) 的最大值，
   T=1.1923（c1_gptoss_ctool 的 REPLAY_REPORT），首过 θ=0.925 即触发。
5. 触发：cgen 生成整条调用 → **正身世界 save_state → requote 补引号 → 执行 →
   截 4000 字符 → load_state 回档 → `_set_datetime()` 重冻时间 → 时间守卫断言**
   （照抄 exec_calls.py 的三连，finally 兜底）→ 把
   `[SYSTEM NOTE: prefetched {call} = {result}]` 拼在切口处，切口之后已生成的
   溢出文本丢弃（丢弃量记账）→ 从注入行之后继续分段生成。
6. `<|end|>` 出现后停止探测，放大段长把该步跑完；解析 final 通道取代码块，
   正身世界执行，喂回执行输出，进下一步。每步思考默认最多注一次
   （`--max-inject-per-step 1`）。

措辞：NOTE_TMPL 原样一行，**不加授权句**（与六点曲线口径一致）。

## 3 进程结构（venv 硬约束决定的）

- `pipeline/inject/live_appworld.py` —— **appworld venv**（cprobe-env import
  appworld 是 ModuleNotFoundError，实测）。驱动器：正身世界 + 分段生成 +
  投机执行三连 + 落盘。exec_calls.py 头上"唯一 import appworld"的说法从此变成
  两处，两个文件的头注释都要写明。
- `pipeline/inject/probe_server.py` —— **cprobe-env**（torch/transformers），
  GPU。装 ctool（CausalProbe backbone+head，85 类，max_len 4096，左截）+
  cgen（call_sep `"\n[CALL] "`）+ gpt-oss tokenizer。HTTP 三个口：
  `/score`（文本→置信度+预测工具）、`/gen`（文本→整条调用）、
  `/render`（messages→harmony 前缀；appworld venv 没有 transformers，
  渲染只能放服务侧）。
- `pipeline/inject/score_live.py` —— cprobe-env，纯 CPU。活跑轨迹 + 对照轨迹 →
  `LIVE_REPORT.{json,md}`。

## 4 已知口径差（报告必带，别静默）

1. **探针前向口径**：训练/回放是整段一次前向、边界位取 logits；活跑只能
   逐前缀前向、末位取 logits。因果模型数学等价，差别只剩分词边界效应。
   probe_server `--selftest` 拿存好的 logits_test.pt 对若干事件量化触发一致性。
2. **切口上限**：回放版切口超 64 时等距抽样；活跑看不见未来，只查前 64 个
   真实切口后歇手。gptoss 每事件切口中位 51，多数事件不受影响。
3. **注入内容**：活跑注"那一条调用的返回"；六点曲线注"整块 stdout"。不可逐字比。
4. cgen 活跑逐触发单条生成（bs=1 左填充无关紧要），与回放批量生成同 greedy 口径。
5. AppWorld 每任务约 90KB 输出目录（磁盘配额教训），驱动器跑完一题即清
   （`--keep-outputs` 保留）。

## 5 范围与顺序

冒烟用 **val 分区**的题调通（测试堆不拿来调试）；冒烟结果给用户过目，拿到
发射令才跑 test 168 题。GPU 两样：gpt-oss-120b 服务一张卡 + 探针服务约 3GB
（挑卡时一并安排），全走 gpu-run。跑完 record.py 记账、回写流水线 skill。
