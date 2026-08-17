# RESULTS — 实验统计数字总表

> 本文件由 `python3 run.py record render` 自动生成，**不要手改**。
> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。
> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。

| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |
|---|---|---|---|---|---|---|---|
| `splice_replay_v1_srv` | 2026-08-18 06:59 | 探针线重启 | `c10c167` | - | ok | p2_n1.has_action=0.994 p2_n1.repeated_call=0.22 p2_n1.next_hit_call=0.374 p2_n1.uses_result=0.034 p2_n1.python_call=0.0 p2_n1.vs_nofill_own_med=7 p2_n1.truncated=0.051 p2_n0.has_action=1.0 p2_n0.repeated_call=0.181 p2_n0.next_hit_call=0.363 p2_n0.uses_result=0.022 p2_n0.python_call=0.0 p2_n0.vs_nofill_own_med=-1 p2_n0.truncated=0.028 p4.has_action=1.0 p4.repeated_call=0.092 p4.next_hit_call=0.562 p4.uses_result=0.101 p4.python_call=0.938 p4.vs_nofill_own_med=74 p4.truncated=0.0 p1_n1.has_action=0.989 p1_n1.repeated_call=0.156 p1_n1.next_hit_call=0.545 p1_n1.uses_result=0.084 p1_n1.python_call=0.0 p1_n1.vs_nofill_own_med=-56 p1_n1.truncated=0.039 p1_n2.has_action=0.944 p1_n2.repeated_call=0.084 p1_n2.next_hit_call=0.484 p1_n2.uses_result=0.056 p1_n2.python_call=0.0 p1_n2.vs_nofill_own_med=-40 p1_n2.truncated=0.045 p1_n3.has_action=0.966 p1_n3.repeated_call=0.25 p1_n3.next_hit_call=0.399 p1_n3.uses_result=0.039 p1_n3.python_call=0.0 p1_n3.vs_nofill_own_med=-45 p1_n3.truncated=0.034 p3k.has_action=1.0 p3k.repeated_call=0.076 p3k.next_hit_call=0.551 p3k.uses_result=0.079 p3k.python_call=0.0 p3k.vs_nofill_own_med=-795 p3k.truncated=0.157 nofill.has_action=1.0 nofill.repeated_call=0.689 nofill.next_hit_call=0.123 nofill.uses_result=0.034 nofill.python_call=0.0 nofill.vs_nofill_own_med=0 nofill.truncated=0.028 p1_n0.has_action=0.989 p1_n0.repeated_call=0.12 p1_n0.next_hit_call=0.521 p1_n0.uses_result=0.073 p1_n0.python_call=0.0 p1_n0.vs_nofill_own_med=-66 p1_n0.truncated=0.028 p1_n0p.has_action=0.983 p1_n0p.repeated_call=0.093 p1_n0p.next_hit_call=0.56 p1_n0p.uses_result=0.045 p1_n0p.python_call=0.0 p1_n0p.vs_nofill_own_med=-66 p1_n0p.truncated=0.062 | 塞法回放 v1:52 事件x178 切口x10 臂=1780 条续写全跑完、0 失败;各臂 has_action 0.94–1.0;调用级 next_hit_call nofill 0.12、p1 臂 0.40–0.56、p2 臂 0.36–0.37、p3k 0.55、p4 0.56;p4 93.8% 再叫 python 停在 </call/>;token 与 nofill 的配对中位差 p1 −40~−66、p2 −1/+7、p3k −795、p4 +74(正=省)。事实,不带解读。 |
| `cmp_chat_noprobe_5_srv4` | 2026-08-18 05:30 | 探针线重启 | `4a6ca2b` | - | ok | branch_points=7 max_top2_gap_at_branch=0.25 | 7 个冷/暖分叉位:top1-top2 logprob 差全是 0/0.125/0.25(bf16 logit 步长),两态同位 top1 logprob 最大差 ≤0.17 |
| `cmp_chat_noprobe_5_srv3` | 2026-08-18 05:17 | 探针线重启 | `a7831de` | - | ok | started=0 | VLLM_BATCH_INVARIANT=1 下 gpt-oss-120b(MXFP4) 起不来:走 _dequant_mxfp4 要 amd-quark(未装),且反量化成 bf16 单卡也放不下;此路不通 |
| `cmp_chat_noprobe_5_srv2` | 2026-08-18 05:11 | 探针线重启 | `a7831de` | - | ok | cases=13 cold_eq_warm=0 comp_eq_chat_same_state=13 | 13 个 prompt:同缓存状态下 completions(ids)==chat 13/13;清缓存(冷)与命中(暖)输出 13/13 不同 |
| `cmp_chat_noprobe_5_srv` | 2026-08-18 04:31 | 探针线重启 | `5c712b6` | - | ok | chat_tasks=5 noprobe_tasks=5 | 服务档:五题 chat baseline + no probe 串行各跑一遍;同 prompt 暖缓存下两端点逐字同,首次前缀(缓存未命中)输出与后续不同(8 个新 prompt 里 7 个) |
| `z1_probe_srv` | 2026-08-10 04:13 | 探针线重启 | `80d07f8` | - | ok | rounds=2 refires=2 | z1 探针服务:θ=0.65 手动;/health 回显 bug 与 /render 口径差在服役期间修复重启 |
| `z1_eval_ctool` | 2026-08-10 04:09 | 探针线重启 | `ef9a749+dirty` | - | ok | temperature=1.8227 chosen_theta_r10=0.75 chosen_theta_r05=0.775 | z1 ctool 回放评测:温度与双档 θ 均有解(val 36 事件) |
| `z1_gptoss_cgen` | 2026-08-10 02:50 | 探针线重启 | `fe9923b` | - | ok | best_val_ce=0.2344 val_exact_call=0.69 train_wall_min=69 | z1 小样 cgen:同 OOM 补射 H100 跑通 |
| `z1_gptoss_ctool` | 2026-08-10 02:50 | 探针线重启 | `fe9923b` | - | ok | best_calA_weighted_acc=0.6199 train_wall_min=4 | z1 小样 ctool:48G A6000 OOM 后 H100 跑通,4 分钟收官;数字无参照价值(20 题小样) |
| `z1_srv` | 2026-08-10 02:00 | 探针线重启 | `250fcae` | - | ok | ready_s=120 arms_rounds=2 | z1 vLLM 服务:采集 20 题+活跑三臂两轮全程在线,钉日期 2026-07-31 |
| `mth_datepin` | 2026-08-10 01:34 | 探针线重启 | `5495d1a` | - | ok | ready_s=306 chat_prompt_date=2026-07-31 tokenize_endpoint_date=2026-08-10 add_special_tokens_prompt_tok_eq=7 | §6-④ 生效:chat 基线路(harmony 渲染,harmony_utils.py:135 读 VLLM_SYSTEM_START_DATE)实测渲染 Current date: 2026-07-31(prompt_logprobs 回显);/tokenize 走模型 jinja 模板不读该变量、显示当天,不是基线路径。§6-③ 附验:同 prompt 带/不带 add_special_tokens=false 皆 7 token,缺省无害坐实 |
| `hcap` | 2026-08-06 19:29 | learn/vllm | `364242b` | gpt-oss-120b | ok | steps=13 completed=1 out_tokens_total=39088 steps_hit_max_tokens=3 toolcall_out_tokens=484 harmony_vs_chat_out_tokens=136 | 客户端自拼 harmony 走 /v1/completions 与 chat 路端到端等价(同一组消息 prompt/输出 token 数与 reasoning/content 逐字相同);抓到 13 步真实逐 token 流,其中 3 步撞 8192 上限 |

## 逐条详情

### `splice_replay_v1_srv`

- **结论**：塞法回放 v1:52 事件x178 切口x10 臂=1780 条续写全跑完、0 失败;各臂 has_action 0.94–1.0;调用级 next_hit_call nofill 0.12、p1 臂 0.40–0.56、p2 臂 0.36–0.37、p3k 0.55、p4 0.56;p4 93.8% 再叫 python 停在 <|call|>;token 与 nofill 的配对中位差 p1 −40~−66、p2 −1/+7、p3k −795、p4 +74(正=省)。事实,不带解读。
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-18 06:59 → 2026-08-18 07:40
- **代码**：`c10c167` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：p2_n1.has_action=0.994 p2_n1.repeated_call=0.22 p2_n1.next_hit_call=0.374 p2_n1.uses_result=0.034 p2_n1.python_call=0.0 p2_n1.vs_nofill_own_med=7 p2_n1.truncated=0.051 p2_n0.has_action=1.0 p2_n0.repeated_call=0.181 p2_n0.next_hit_call=0.363 p2_n0.uses_result=0.022 p2_n0.python_call=0.0 p2_n0.vs_nofill_own_med=-1 p2_n0.truncated=0.028 p4.has_action=1.0 p4.repeated_call=0.092 p4.next_hit_call=0.562 p4.uses_result=0.101 p4.python_call=0.938 p4.vs_nofill_own_med=74 p4.truncated=0.0 p1_n1.has_action=0.989 p1_n1.repeated_call=0.156 p1_n1.next_hit_call=0.545 p1_n1.uses_result=0.084 p1_n1.python_call=0.0 p1_n1.vs_nofill_own_med=-56 p1_n1.truncated=0.039 p1_n2.has_action=0.944 p1_n2.repeated_call=0.084 p1_n2.next_hit_call=0.484 p1_n2.uses_result=0.056 p1_n2.python_call=0.0 p1_n2.vs_nofill_own_med=-40 p1_n2.truncated=0.045 p1_n3.has_action=0.966 p1_n3.repeated_call=0.25 p1_n3.next_hit_call=0.399 p1_n3.uses_result=0.039 p1_n3.python_call=0.0 p1_n3.vs_nofill_own_med=-45 p1_n3.truncated=0.034 p3k.has_action=1.0 p3k.repeated_call=0.076 p3k.next_hit_call=0.551 p3k.uses_result=0.079 p3k.python_call=0.0 p3k.vs_nofill_own_med=-795 p3k.truncated=0.157 nofill.has_action=1.0 nofill.repeated_call=0.689 nofill.next_hit_call=0.123 nofill.uses_result=0.034 nofill.python_call=0.0 nofill.vs_nofill_own_med=0 nofill.truncated=0.028 p1_n0.has_action=0.989 p1_n0.repeated_call=0.12 p1_n0.next_hit_call=0.521 p1_n0.uses_result=0.073 p1_n0.python_call=0.0 p1_n0.vs_nofill_own_med=-66 p1_n0.truncated=0.028 p1_n0p.has_action=0.983 p1_n0p.repeated_call=0.093 p1_n0p.next_hit_call=0.56 p1_n0p.uses_result=0.045 p1_n0p.python_call=0.0 p1_n0p.vs_nofill_own_med=-66 p1_n0p.truncated=0.062
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/splice_replay_v1`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_splice_replay_v1_srv_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `cmp_chat_noprobe_5_srv4`

- **结论**：7 个冷/暖分叉位:top1-top2 logprob 差全是 0/0.125/0.25(bf16 logit 步长),两态同位 top1 logprob 最大差 ≤0.17
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-18 05:30 → 2026-08-18 05:34
- **代码**：`4a6ca2b` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：branch_points=7 max_top2_gap_at_branch=0.25
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/cmp_chat_noprobe_5/analysis/branch_logprobs.txt`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_cmp_chat_noprobe_5_srv4_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 VLLM_SERVER_DEV_MODE=1 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `cmp_chat_noprobe_5_srv3`

- **结论**：VLLM_BATCH_INVARIANT=1 下 gpt-oss-120b(MXFP4) 起不来:走 _dequant_mxfp4 要 amd-quark(未装),且反量化成 bf16 单卡也放不下;此路不通
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-18 05:17 → 2026-08-18 05:20
- **代码**：`a7831de` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：started=0
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_cmp_chat_noprobe_5_srv3_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 VLLM_SERVER_DEV_MODE=1 VLLM_BATCH_INVARIANT=1 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `cmp_chat_noprobe_5_srv2`

- **结论**：13 个 prompt:同缓存状态下 completions(ids)==chat 13/13;清缓存(冷)与命中(暖)输出 13/13 不同
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-18 05:11 → 2026-08-18 05:17
- **代码**：`a7831de` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：cases=13 cold_eq_warm=0 comp_eq_chat_same_state=13
- **原始数据**：`/home/y-guo/.claude/jobs/6d27f0e1/tmp/cold_warm.json`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_cmp_chat_noprobe_5_srv2_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 VLLM_SERVER_DEV_MODE=1 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `cmp_chat_noprobe_5_srv`

- **结论**：服务档:五题 chat baseline + no probe 串行各跑一遍;同 prompt 暖缓存下两端点逐字同,首次前缀(缓存未命中)输出与后续不同(8 个新 prompt 里 7 个)
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-18 04:31 → 2026-08-18 05:10
- **代码**：`5c712b6` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：chat_tasks=5 noprobe_tasks=5
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/cmp_chat_noprobe_5`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_cmp_chat_noprobe_5_srv_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `z1_probe_srv`

- **结论**：z1 探针服务:θ=0.65 手动;/health 回显 bug 与 /render 口径差在服役期间修复重启
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-10 04:13 → 2026-08-10 04:56
- **代码**：`80d07f8` (分支 main)
- **机器**：tokyo105 GPU 0
- **数字**：rounds=2 refires=2
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_z1_probe_srv_t105g0.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/inject/probe_server.py serve --theta 0.65 --ctool-run /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/z1_gptoss_ctool --cgen-run /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/z1_gptoss_cgen --port 8790 --device cuda:0`

### `z1_eval_ctool`

- **结论**：z1 ctool 回放评测:温度与双档 θ 均有解(val 36 事件)
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-10 04:09 → 2026-08-10 04:56
- **代码**：`ef9a749`  ⚠️ 发射时工作树是脏的（16 文件），这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo108 GPU 1
- **数字**：temperature=1.8227 chosen_theta_r10=0.75 chosen_theta_r05=0.775
- **原始数据**：`已删除`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_z1_eval_ctool_t108g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_tool.py --head causal --env appworld --run /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/z1_gptoss_ctool --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/aw_z1_v1/gptoss`

### `z1_gptoss_cgen`

- **结论**：z1 小样 cgen:同 OOM 补射 H100 跑通
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-10 02:50 → 2026-08-10 04:56
- **代码**：`fe9923b` (分支 main)
- **机器**：tokyo105 GPU 1
- **数字**：best_val_ce=0.2344 val_exact_call=0.69 train_wall_min=69
- **原始数据**：`已删除`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_z1_gptoss_cgen_t105g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/aw_z1_v1/gptoss --out /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/z1_gptoss_cgen`

### `z1_gptoss_ctool`

- **结论**：z1 小样 ctool:48G A6000 OOM 后 H100 跑通,4 分钟收官;数字无参照价值(20 题小样)
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-10 02:50 → 2026-08-10 04:56
- **代码**：`fe9923b` (分支 main)
- **机器**：tokyo105 GPU 0
- **数字**：best_calA_weighted_acc=0.6199 train_wall_min=4
- **原始数据**：`已删除`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_z1_gptoss_ctool_t105g0.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --base qwen --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/aw_z1_v1/gptoss --out /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/z1_gptoss_ctool --align-tol 3e-4`

### `z1_srv`

- **结论**：z1 vLLM 服务:采集 20 题+活跑三臂两轮全程在线,钉日期 2026-07-31
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-10 02:00 → 2026-08-10 04:56
- **代码**：`250fcae` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：ready_s=120 arms_rounds=2
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_z1_srv_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `mth_datepin`

- **结论**：§6-④ 生效:chat 基线路(harmony 渲染,harmony_utils.py:135 读 VLLM_SYSTEM_START_DATE)实测渲染 Current date: 2026-07-31(prompt_logprobs 回显);/tokenize 走模型 jinja 模板不读该变量、显示当天,不是基线路径。§6-③ 附验:同 prompt 带/不带 add_special_tokens=false 皆 7 token,缺省无害坐实
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-10 01:34 → 2026-08-10 01:42
- **代码**：`5495d1a` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：ready_s=306 chat_prompt_date=2026-07-31 tokenize_endpoint_date=2026-08-10 add_special_tokens_prompt_tok_eq=7
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_mth_datepin_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

### `hcap`

- **想验证什么**：验客户端自拼 harmony 走 /v1/completions 能不能跑通,并抓一条 AppWorld 轨迹的逐 token 原始流(return_token_ids)做教学页
- **结论**：客户端自拼 harmony 走 /v1/completions 与 chat 路端到端等价(同一组消息 prompt/输出 token 数与 reasoning/content 逐字相同);抓到 13 步真实逐 token 流,其中 3 步撞 8192 上限
- **方向**：learn/vllm ｜ **状态**：ok ｜ **起止**：2026-08-06 19:29 → 2026-08-06 19:42
- **代码**：`364242b` (分支 main)
- **机器**：tokyo108 GPU 2
- **模型 / 种子**：gpt-oss-120b / 0
- **参数**：api=harmony temperature=0.0 start_date=2026-08-06 reasoning_effort=high
- **数字**：steps=13 completed=1 out_tokens_total=39088 steps_hit_max_tokens=3 toolcall_out_tokens=484 harmony_vs_chat_out_tokens=136
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/envs/runs/hcap`（不在 git 里）
- **日志**：`/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_hcap_srv.log`
- **命令**：`envs/appworld/venv/bin/python envs/collect/run_appworld.py --api harmony --base-url http://tokyo108:8113/v1 --model gpt-oss-120b`
