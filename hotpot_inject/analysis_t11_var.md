# T11 采样方差检查（run_id 20260730_0413_hotpot_t11_var）

协议：Qwen3-8B，hotpot fullwiki，comparison/bridge 各 40 题，temperature 0.6，
种子 {1,2,3}（`torch.manual_seed`，每种子基线独立生成、注入条件与同种子同题基线配对），
budget 2500，条件集 baseline / hop1@{start,25,0} / hop2@0 / hop2_start / both_start，
8 分片 × 3 种子 = 24 任务（tokyo105 八卡，1338 条记录）。
代码 commit `4147942`（--temperature/--gen-seed 开关），聚合器 `aggregate_var.py`
（单种子口径与 aggregate.py 交叉验证吻合）。原始记录 `results_t11/`（NFS/本地，不入库）。

表格口径：em/soft/d_tok 均为"每种子先聚合，再报跨种子 mean±std"；
d_tok = 同种子同题基线生成 token − 该条件生成 token（正 = 省）。

| model | dataset | type | cond | offset | seeds | n/seed | em | soft | gen_tok | d_tok |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-8B | hotpot | bridge | baseline |  | 3 | 40,40,40 | 0.02±0.01 | 0.61±0.05 | 486.88±52.07 |  |
| Qwen3-8B | hotpot | bridge | both_start | -1 | 3 | 33,36,38 | 0.00±0.00 | 0.72±0.02 | 26.85±1.16 | 433.88±40.43 |
| Qwen3-8B | hotpot | bridge | hop1 | -1 | 3 | 33,36,38 | 0.01±0.02 | 0.48±0.04 | 87.67±42.68 | 373.06±76.69 |
| Qwen3-8B | hotpot | bridge | hop1 | 0 | 3 | 33,36,38 | 0.02±0.02 | 0.57±0.06 | 525.88±59.44 | -65.15±63.38 |
| Qwen3-8B | hotpot | bridge | hop1 | 25 | 3 | 33,36,38 | 0.02±0.02 | 0.49±0.04 | 613.71±71.72 | -152.98±69.45 |
| Qwen3-8B | hotpot | bridge | hop2 | 0 | 3 | 9,8,9 | 0.00±0.00 | 0.85±0.17 | 456.72±42.01 | 27.90±49.14 |
| Qwen3-8B | hotpot | bridge | hop2_start | -1 | 3 | 9,8,9 | 0.00±0.00 | 0.65±0.33 | 64.88±4.66 | 419.74±93.77 |
| Qwen3-8B | hotpot | comparison | baseline |  | 3 | 40,40,40 | 0.25±0.00 | 0.74±0.05 | 402.23±27.78 |  |
| Qwen3-8B | hotpot | comparison | both_start | -1 | 3 | 34,35,37 | 0.27±0.01 | 0.70±0.05 | 32.44±3.05 | 368.62±14.29 |
| Qwen3-8B | hotpot | comparison | hop1 | -1 | 3 | 34,35,37 | 0.17±0.03 | 0.56±0.02 | 116.23±8.96 | 284.83±17.94 |
| Qwen3-8B | hotpot | comparison | hop1 | 0 | 3 | 34,35,37 | 0.28±0.01 | 0.74±0.03 | 432.20±54.20 | -31.14±43.44 |
| Qwen3-8B | hotpot | comparison | hop1 | 25 | 3 | 34,35,37 | 0.24±0.03 | 0.64±0.06 | 457.91±37.76 | -56.85±35.65 |
| Qwen3-8B | hotpot | comparison | hop2 | 0 | 3 | 32,30,35 | 0.28±0.03 | 0.72±0.04 | 379.55±29.83 | 20.14±18.55 |
| Qwen3-8B | hotpot | comparison | hop2_start | -1 | 3 | 32,30,35 | 0.22±0.04 | 0.64±0.05 | 118.37±15.38 | 281.32±23.12 |

## 判语（对贪心口径三条主线结论的稳健性核验）

1. **comparison 早注毒性在采样口径下复现**：hop1@start 使 soft 0.74→0.56
   （−18pp，与贪心口径掉幅一致），em 0.25→0.17；三种子方向一致（soft std 仅 0.02）。
2. **决策死区复现**：贴近调用点注入（hop1@25）省 token 为负
   （bridge −153±69 / comparison −57±36），三种子符号不翻；@0 同为负、幅度较小。
3. **both_start 仍是全场最优动作**：bridge soft 0.61→0.72（+11pp 反而升）且省
   434±40 token；comparison soft 0.74→0.70（−4pp，在种子噪声带内）省 369±14 token。
   两类型都在"大省 token 且不掉分"象限，与贪心结论一致。
4. **小样本警示（写论文必标）**：bridge 发生第二跳的子集每种子仅 8–9 题，
   hop2_start 的 soft ±0.33，该格数字只能当方向性证据；comparison 的 hop2 子集
   （30–35 题）无此问题。bridge 的 em 全条件≈0（8B 在 bridge 上几乎不产生
   精确匹配答案），soft 是有效指标，与贪心口径一致。

## 两类多跳分开报数（T11 另一半验收）

本表与 wave1/wave2 全部历史表格均按 comparison（独立两跳）/ bridge（有依赖两跳）
分列（类型来自数据集原生 `type` 字段，非自建分类器），无混杂报数。
