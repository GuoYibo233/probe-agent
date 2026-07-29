# TraceLab 概念 → 代码映射（repo: related_work/TraceLab）

子 agent 逐文件核实于 2026-07-27。工程要点只含论文正文里看不到的信息。

## c2 三层结构（session/request/step）
- `artifacts/human_in_the_loop/user_turn_decomposition/analyze.py:1-42`；`artifacts/utils/trace_db.py:11-16`；`scripts/extract_codex_rounds.py:470-490`
- 论文的 "step" 在代码里统一叫 "round"；"request" 没有独立数据结构，是 user_turn_decomposition 里的逐 session 状态机，其他实验通过 importlib 动态加载复用（session_cost_distribution/analyze.py:84-88）。
- 天然键全部不唯一（round_id 约 8.9k 重复），主键是文件序 round_pk，刻意不去重（"de-duping would change results"）。
- Codex subagent 的 round 按 turn_id/parent 规则归并回父 session。

## c3 prefix caching
- `artifacts/prefix_cache/timeout_miss_pattern/plot.py:1-33`
- 论文"idle 过期的是 cache 不是 context"的示意图是纯合成数据，bar 高度手工设计，专门用来反驳"gap 后 bar 重置"的错误心智模型。

## c4 P/A/O 记账
- `scripts/extract_claude_rounds.py:54-90`；`scripts/extract_codex_rounds.py:457-520`
- Claude：同一 message id 会重复携带 usage，用 (output, total_input, has_stop_reason) 三元组打分保留"最完整"快照，而非取最后一条（防止 0 占位覆盖）。
- Codex：round 边界是 event_msg.token_count 事件；A = max(0, input − cached)（负值截断）；用 total_token_usage 的 JSON 签名去重。

## c5 采集流水线
- `scripts/collect_llm_traces.py:1-46`；`scripts/sanitize_round_trace.py:1-110`；`scripts/trace_privacy.py:1-60`
- 假名化种子确定性（seed "coding-trace-sanitize-round-trace-v1"）且保格式；敏感键单一来源在 trace_privacy.py；tools[].input 整体丢弃（DB 层不建列）。

## c6 数据集与 DuckDB
- `artifacts/trace_facts/overview_summary/analyze.py:331-462`；`artifacts/utils/trace_db.py:160-257`；`artifacts/utils/DB_SCHEMA.md`
- 3 表 DuckDB（rounds/tool_calls/timing_events）；为兼容 Pyodide 限定 1.1 语法；timestamp 经 VARCHAR round-trip 钉成 naive UTC。
- "user" 列强制物理存在：缺列时 DuckDB 把带引号 "user" 静默解析成 current_user，distinct 用户数会错算成 1。

## c8 compaction 判据
- `artifacts/session/session_compaction_counts/analyze.py:60-98`；`artifacts/utils/growth.py:14-15,133-149`
- drop≥64k（复用 MAJOR_REDUCTION_MIN_TOKENS，保证是 major reduction 严格子集）；降前 ≥0.75×session 峰值；3 步内不回到 ≥0.75×降前值且必须有后续步。
- 另有论文没细讲的 micro_reduction 桶（≤1024）。

## c9 成本计算
- `artifacts/session/session_cost_distribution/analyze.py:103-165`；`artifacts/web_analytics/pricing.py:87-114`；`artifacts/utils/pricing.json`
- append 内部再拆两档：min(cache_creation, append) 按 5 分钟 cache-write 费率，剩余按 fresh input 费率。
- 无价格模型的 round 直接剔除（约 0.9%）。

## c10 时间分布
- `artifacts/session/session_timing_distribution/analyze.py:1-56`；`artifacts/utils/timing.py:142-191`
- human thinking = 任意前一事件到 user_message 的正 gap（修正旧定义漏残差）；另算 per-session clamp 1h 口径；生成/工具时间可并发重叠，份额不保证加和 100%。

## c12 双峰输入
- `artifacts/llm_generation/prefix_append_distribution/plot.py:167-260`
- 直方图 + append-token 加权分桶直接呈现，非拟合。

## c13 output 记账判别
- `artifacts/llm_generation/output_append_assignment/plot.py:263-307,329-397,1168-1186`
- 容差谓词投票：tol = max(512, 10%×prev_output)；场景级标签需 n≥50 且 70/20 阈值；只取相邻 gap≤240s、prev_output≥2k/4k 的 pair；结论是逐模型版本判别的。

## c14 解码速度
- `artifacts/llm_generation/context_decode_speed_scatter/plot.py:28-35,111-205`；`timing_fit/fit_timing_trace.py:24-46`
- 过滤：context≥4096、速度上限 160 tok/s、TTFT≤40s；timing_fit 另拟合了 P/A/O 二次型（10 特征）预测时长，论文没展开。

## c15 工具重尾
- `artifacts/tool_calls/tool_call_counts/plot.py:41-44`；`tool_latency_distribution/plot.py:1-35`；`trace_db.py:409-414`
- "80 多种工具"经过收编：调用数 <20 并入 Other；时长用 EFFECTIVE_TOOL_LATENCY_MS_SQL：优先 internal，缺失才用 wall，仅取正值。

## c16 工具开销残差
- `artifacts/tool_calls/codex_wall_internal_gap/analyze.py:1-12,32-33,86-110`
- R = GREATEST(wall−internal, 0) 直接在 SQL 里算；残差是 approval/user-wait 的唯一信号（sanitize 后不保留审批事件）；工具硬编码分 DIRECT_HUMAN_TOOLS 与 EXECUTION_LIKE 两组。

## c17 命中率
- `artifacts/prefix_cache/cache_hit_ratio/analyze.py:189-282,58-95`；`cache_hit_idle_relationship/cache_hit_idle_gap_analysis.py:1-50`
- 95.7% 是 token 加权口径（另有逐 round 口径）；user-initiated 判定 = 首个 timing 事件是 user_message；idle→miss 归因是 stateful 走查（低命中 round 回看前一 round 的 gap）。

## c18 fresh / 放大
- `artifacts/prefix_cache/redundant_prefill/analyze.py:1-119`
- fresh = max(0, ΔL) − output(P)，P 是文件序上一 round（非 index−1）；聚合先求和再相除（非逐步均值）。

## c19 驱逐扫描
- `artifacts/prefix_cache/eviction_tradeoff/analyze.py:1-99,109-131`
- 二值模型：g≤τ 全命中 / g>τ 全 miss；fresh 额外 clip 到 [0, append]（与 c18 裸定义不同）；R(τ) 的 gap 显式 cap 到 τ；τ 扫 1s–4h 260 个对数点。
- 真实部署点用"有效驱逐时间"反解：理想曲线命中率 = 实测 95.7% 处约 8 分钟。

## c20 省钱上界
- `artifacts/prefix_cache/human_idle_cache_counterfactual/analyze.py:1-98`
- 反事实：仅 user-initiated 且有前驱的步，append 压到 min(append, context_growth)，总输入不变，移走的 token 按 cache-read 价计；剩余 cache-creation 仍按 5 分钟 write 价。

UNMAPPED：无（c3 仅对应合成示意图）。c1、c7、c11 是纯论述/统计概念，无独立代码。
