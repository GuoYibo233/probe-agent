# 2026-08-21 三路评审发现与已批修复清单（p1 训练发射的前置账）

三个只读评审 agent（cparam 本体 / 注册表接线 / 采集配置）2026-08-21 审完
commit a35b580 与 05b3abc（基准 HEAD 28dbec8）。采集配置六项全过、可发射。
代码侧发现如下,gyb 已裁决三包修复全做。**行号都是 28dbec8 时点的,改前重新定位。**

执行时机约束：LoRA 实现 agent 落地验收后一起改（文件重叠）,全部 commit
之后才许发训练。

## 包一 保险丝（已批,三条都加）

1. `pipeline/eval/eval_causal_call.py`（约 :509 读 best/meta.json 处）：
   meta 含 `param_only: true` → SystemExit 拒收。堵「cparam 的 run 喂给 cgen
   评测一路跑通出全塌报告」（两个评审独立发现;正路排卡表碰不到,手搓会踩）。
2. `train_causal_param.py` 与 `train_causal_callgen.py`：val 堆 0 行 → 硬报错
   退出。现状:val 全被丢时 `eval_ce` 返回 `0/1e-9=0.0`,每个 epoch 都当 best 存,
   run 看起来完美（实测复现;train 堆空会硬崩,val 用 SequentialSampler 不拦空）。
3. `train_causal_param.py`：剥离失败率 `assembly_mismatch/(kept+mismatch) > 5%`
   → 硬停;计数写进 meta.json。对齐 `readonly_map.py:70` UNKNOWN_HARD_LIMIT=0.05
   先例。现状只进 train_log 首行,上游拼串口径漂移会静默吞样本。

## 包二 口径补齐（已批,三件都做）

1. `train_causal_callgen.py` meta 补 `"base": args.base`（:503-506 现只有
   base_path;tool 与 param 两脚本都有 base 键,记法要一致）。
2. `eval_causal_param.py` 与 `eval_causal_call.py`：头 run 的 meta.data、
   `--data` 实参、`--ctool-run` 的 meta.data 三方对拍,不一致硬报错。堵
   「p1b06 的 ctool 配 p1b17 的 cparam 静默通过全部保险丝」（第一轮两档并行,
   这是真实风险）。
3. `eval_causal_param.py` 的 md 报告：标注解析失败率恒 0 的原因（工具名是脚本
   自己拼在串首的,parse 必命中）;把 pred_tool/gt_tool 的 noparam_rate 印进 md
   （无参事件恒判对,cparam 白拿分占比比 cgen 高,矩阵只吃 full_call_ok）。

## 包三 测试补强（已批,四件都补）

1. 补两文件契约测试：`given + "(" + gen == label_call` 当且仅当
   `gen == param_target(label, label_call)`（现在只有训练侧单边覆盖）。
2. 空转用例 `test_value_with_comma_quote_paren` 改成真打评测侧解析
   （split_named_raw/parse_call）。注意:引号内括号配平不认引号是 cgen 既有判分
   口径（`apis.gmail.send(body="a ) b")` 切成 `[('body','"a')]`）,测试记录现状,
   不改判分。
3. 三个分隔符常量互相对拍：train_causal_param.CALL_SEP、
   train_causal_callgen.CALL_SEP、eval_causal_param.FALLBACK_SEP。
4. 测试文件 catch SystemExit（train_causal_param.py:50-53 在 transformers<5.14
   抛 SystemExit 不是 ImportError）,让 mbert-env 下 discover 正常 skip 而不是 error。

## skill 回写欠账（纪律必修,不需批）

- `references/extending.md`：:120/:163 引 summarize_matrix CELLS 行号 21→24;
  :156 rid 拼接 75→90;:267(#14) 21→24;**:268(#15) else 分支 55-58→70-73**
  （55-58 现在是 mext 分支,照旧文改会改错地方）;:37「三个 eval」→四个;
  :134 心跳清单→五训练四 eval;:149 logits 行数 assert→三处;:260(#7)→四个 eval
  里两个的 --env 真影响判分。
- `references/stage-commands.md` §4：:253 四个 eval 任务→五个;:244 三个 eval
  带 --readonly-env→四个;:279/:287/:289「三个 eval」→四;:285/:286/:288
  「两个 call」含 cparam;补 eval_causal_param 的 --max-new-tokens 行;
  :301 输入输出表补 summarize_matrix 读 PARAM_REPORT.json;:303 退出码补
  param_only 硬退一条。

## 记档不修（gyb 未批修,当前口径保持）

- 矩阵 `--risk` 只对 tool 格生效,参数格印评测时档而表头按 --risk 写（cgen 时代
  设计层问题）。
- 无参事件恒判 params_all_ok/full_call_ok 为真（cgen 既有判分口径,动了不可比）。
- 引号内括号解析缺陷（同上,既有判分口径）。
- `gen_launch.py:279` 预设名嵌引号无转义（名字先过存在性校验,当前打不到）。
- 零触发事件→报告 null→矩阵格 '-' 但状态 OK（静默点 #15 的变体,cgen 同款）。
- selfcheck 不查 CELL_ORDER ⊆ CELLS（当前不变式成立,实测过）。
- `probe_server.py:69-70` 缺省指向已清场的 c1 run（不传参会响亮报错）。
- `summarize_matrix.py` `--prefix` 缺省 "c1"（用时必显式传批次）。
- 底座档位不进 run_id/矩阵行——由「一批一档」约定 + meta 的 base 键覆盖。

## 流程状态（写于 2026-08-21 发射当天,过时就地更新）

- 在跑：①LoRA 实现 agent——三训练脚本加 --lora（rank16/alpha32/dropout0.05/
  lr2e-4 默认）与 --grad-ckpt,peft 装 cprobe-env（transformers/torch 版本不许
  动）,存档 merge_and_unload 并回底座、评测零改动,CPU e2e,不 commit,主会话
  验收。②采集发射员 agent——manifest_p1,tokyo108 双 H200 起 gpt-oss-120b,
  G2 实探→gen-launch 正式生成→双服务→G3 健康→G4 一题 smoke（meta 预设
  gptoss_harmony_high/effort high/末行 final）→放量 7 分片→jobs.json+record
  start+RUNMETA 三处登记。脏树经 gyb 裁决用 --allow-dirty 放行(脏的是训练侧
  半成品与 research-loop 会话文档,不在采集代码路径)。
- 顺序：采集收尾（G6 315 文件/G7 归零/finish/record finish/提交台账）→标注造
  数据（p1_gptoss.json,G9 90/57/168,check_callstr,逐字节重建,DATA.md）;
  LoRA 验收+三包修复+回写 commit 完→训练 smoke（1.7B 全参显存/LoRA 三档/
  4B 挤不进开 --grad-ckpt）→发射前 commit（research-loop 文档仍脏就单独一笔
  注明来源收进去）→并行发射:全参 p1b06+p1b17 六任务 tokyo108,LoRA
  p1l06/p1l17/p1l4 九任务 tokyo106→评测（已授权）依赖序发,逐批矩阵,
  record 记数→总汇报。
- 训练主线口径锁死：全参,lr 1e-5,3 epoch,批 4×累积 8=有效批 32,warmup 5%,
  fp32 权重+bf16 计算,max_len 4096,损失只算目标段,seed 20260729,best 按
  val_ce。LoRA 线超参走旗标默认,不进锁超参横比。
