# D 线 → A 线交接：T12 记账命令 + c/d 卡活方案（2026-07-30 凌晨）

> D 线（C3 纸面与 CPU 件）无台账写入权。本文所有 record.py / gpu-run 命令
> 由 A 线执行。任务卡定义见 `plans/2026-07-30-task-plan.md` T12。

## 一、补记账（纯 CPU，三笔，优先做）

论文 `paper/speculator/main.tex` 协议节已有两处 source 注释指向下面的
run_id——**登记完成前这些数字属"查无 run_id"状态**，请先补账再干别的。

```bash
# 1) T12e:Qwen3-8B 全矩阵(07-28 已跑完,补记)
python3 ops/record.py start --run-id 20260728_fig1_8bfull --track c3 \
  --model Qwen3-8B --seed 20260729 \
  --cmd "fig1_pilot/launch_fleet.sh (8bfull_*,3档×mem/nomem×5seed×10ep)" \
  --data fig1_pilot/results \
  --note "C3 全矩阵复跑:8B 上记忆红利与档位关系"
python3 ops/record.py finish 20260728_fig1_8bfull --status ok \
  --metric total_tok_saving_L2=+9.6% --metric total_tok_saving_L2minus=-16.8% \
  --metric total_tok_saving_L1=-19.6% --metric acc_delta_all=0pp \
  --conclusion "8B 红利小于 4B;按正典货币(总token)近重复档也为负(输入税),Sp@k 到 k=8 才转正;详见 fig1_pilot/ANALYSIS_8bfull.md + benchmark_design/METRICS_SMOKE_8bfull.md"

# 2) T12f:TraceLab 相似度分布 v0(07-27 已跑完,补记)
python3 ops/record.py start --run-id 20260727_tracelab_simv0 --track c3 \
  --cmd "tracelab_analysis/similarity_v0.py" --data tracelab_analysis \
  --note "生态效度:真实负载里相似重复任务占多大比例"
python3 ops/record.py finish 20260727_tracelab_simv0 --status ok \
  --metric adj_sim_gt0.8=68.4% --metric adj_sim_0.3-0.8=17.2% \
  --metric adj_sim_lt0.3=14.5% --metric near_dup_within50=96.1% \
  --metric high_sim_cross_project=10.8% \
  --conclusion "重复相似任务是真实负载主体;跨 project 假相似 10.8% 为 L4 现实原型;仪器只见工具构成,边界已在论文声明"

# 3) T12d CPU 件:完美复用天花板(今晨新算)
python3 ops/record.py start --run-id 20260730_oracle_ceiling_8bfull --track c3 \
  --cmd "benchmark_design/oracle_ceiling.py --legacy-levels" \
  --data benchmark_design/ORACLE_CEILING_8bfull.md \
  --note "oracle 零成本回放上界,在 8bfull nomem 流上算"
python3 ops/record.py finish 20260730_oracle_ceiling_8bfull --status ok \
  --metric ceiling_L2_total=+21.0% --metric ceiling_L2_per_ep=+23.4% \
  --metric ceiling_L1=0% --metric ceiling_L2minus=0% \
  --conclusion "逐字回放上界只在 L2 非零且被失败任务封死(能回放的集本来便宜);L2 以上的省必须来自泛化——天花板基线并列汇报的动机"
```

## 二、T12e：已完成，勿重复烧卡

8bfull 全矩阵 07-28 已跑完并聚合（`fig1_pilot/ANALYSIS_8bfull.md`，正典编号
已重映射）。缺口只有 L0 无关流与 L3/L4 档——按设计稿约定挂 C4 全矩阵（T14）
一起补，现在不用动卡。

## 三、T12c 被试接入：剩余工作 + 发射方案

现状（`related_work/evo_mem_INTEGRATION.md`）：勘察完毕、3 处 import 修复
已打、ExpRAG 冒烟已通（search→synthesize→generate→evolve 全链路）。
该库是按论文重建的骨架非官方实现，论文措辞已定为"参照其统一接口"。

剩余程序活（CPU，可派程序线写，估时见 INTEGRATION §6，合计 1.5–2 天）：
1. 单轮 driver（答案抽取 + 评分回填记忆，§2.4 方案 2）；
2. ALFWorld EnvAdapter（真 TextWorld 包成 reset/step 协议）；
3. ReMem / DynamicCheatsheet / AWM 与原论文行为核对（重建代码，保真度未验）；
4. 换正式模型重冒烟（Qwen2.5-7B/14B-Instruct，HF 缓存已有）。

发射要点（走 gpu-run，1 卡即够）：
- 服务：`fig1_pilot/fig1-env` 的 vLLM 0.16.0，**必须带
  `FLASHINFER_DISABLE_VERSION_CHECK=1`**（flashinfer 版本不一致,不加起不来，
  INTEGRATION §3 有完整命令模板，port 8791）；
- 检索器 bge-base 在 CPU 上跑即可，不占卡；
- T12 验收口径：每被试一次冒烟通过记录（ExpRAG 已有，还差 3–4 个被试）。

## 四、T12d 全历史基线（要卡）

方案：fig1 流上加第三臂 `fullhist`——每集把此前所有集的完整轨迹塞进
上下文（超预算时保最近集优先截断，截断策略写进 run note）。
- 程序活：`fig1_pilot/fig1_run.py` 加 `--setting fullhist`（估 2–4 h，
  可派程序线）；
- 跑量：3 档 × 5 种子 × 10 集，参照 8bfull 实测单 run 数十分钟，
  单卡一晚可清；发射前 commit、record start、双登记照旧。
- 天花板（CPU 件）**已完**：`benchmark_design/ORACLE_CEILING_8bfull.md`。

## 五、D 线今晨产物索引（供对账）

- `benchmark_design/metrics.py`：T12b 指标脚本，五条防幸存者偏差规则全部
  断言化；`python3 metrics.py --selftest` 全过；8bfull 冒烟报告
  `METRICS_SMOKE_8bfull.md`（含与旧聚合的逐项对账）。
- `benchmark_design/oracle_ceiling.py` + `ORACLE_CEILING_8bfull.md`。
- `paper/speculator/main.tex` 新增 §Evaluation Protocol（C3 协议节），
  latexmk 编译干净（4 页，Overfull 0）。
- L3/L4 任务对生成脚本（T12a，完）：`gen_l4_alfworld.py`（真引擎回放验证，
  全模板抽样 800→259 有效对）/ `gen_l4_2wiki.py`（极性翻转 1690 全 T3 +
  易混替换 4804）/ `gen_l3_2wiki.py`（两跳拼接 4244，全 train 19520）；
  冒烟与七条坑见 `GEN_REPORT.md`。数据 jsonl 不进 git。
  口径修正一条：ALFWorld 位置改换族产不出 T3，配平靠动词/数量翻转补
  （已批注进设计稿 §5）。
