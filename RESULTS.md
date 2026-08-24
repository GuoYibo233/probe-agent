# RESULTS — 实验统计数字总表

> 本文件由 `python3 run.py record render` 自动生成，**不要手改**。
> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。
> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。

| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |
|---|---|---|---|---|---|---|---|
| `np821b17_gptoss_cgen` | 2026-08-23 05:44 | probe_np821b17 | `7dbd28e` | - | ok | best_val_ce=0.512 gsteps=17484 | np821b17 cgen 全量收官: best val_ce 0.512, 3 epoch 跑满, 墙钟约32.2h(H100,三次落位后) |
| `np821b17_gptoss_cparam` | 2026-08-23 05:42 | probe_np821b17 | `63884f2` | - | ok | best_val_ce=0.3378 gsteps=17484 | np821b17 cparam 全量收官: best val_ce 0.3378, 3 epoch 跑满, 墙钟约30.1h(H100) |
| `np821b17_gptoss_ctool` | 2026-08-23 05:42 | probe_np821b17 | `63884f2` | - | ok | best_calA_weighted_acc=0.6867 gsteps=387 align_maxdiff_hidden=0.000214 | np821b17 ctool 全量收官: best calA weighted acc 0.6867, ALIGN PASS(2.14e-04<3e-4), 墙钟约1.5h(H100) |
| `np821l17_gptoss_cparam` | 2026-08-22 12:04 | probe_np821l17 | `1b9334f` | - | running | - | - |
| `np821l17_gptoss_cgen` | 2026-08-22 12:04 | probe_np821l17 | `1b9334f` | - | running | - | - |
| `np821l17_gptoss_ctool` | 2026-08-22 12:04 | probe_np821l17 | `1b9334f` | - | ok | best_calA_weighted_acc=0.6974 gsteps=387 align_maxdiff_hidden=0.000237 | np821l17 ctool 全量收官: best calA weighted acc 0.6974, ALIGN PASS(2.37e-04<3e-4), 墙钟约3.2h(RTX6000Ada) |
| `np821l4_gptoss_cparam` | 2026-08-22 12:04 | probe_np821l4 | `1b9334f` | - | ok | best_val_ce=0.3375 gsteps=17484 | np821 l4 cparam(Qwen3-4B LoRA+gc, H200) 3ep 完成, best_val_ce 0.3375, 墙钟约 64.4h |
| `np821l4_gptoss_cgen` | 2026-08-22 12:04 | probe_np821l4 | `1b9334f` | - | ok | best_val_ce=0.371 gsteps=17484 | np821 l4 cgen(Qwen3-4B LoRA+gc, H200) 3ep 完成, best_val_ce 0.371, 墙钟约 64.2h |
| `np821l4_gptoss_ctool` | 2026-08-22 12:04 | probe_np821l4 | `1b9334f` | - | ok | best_calA_weighted_acc=0.7016 gsteps=387 align_maxdiff_hidden=0.000175 | np821l4 ctool 全量收官: best calA weighted acc 0.7016, ALIGN PASS(1.75e-04<3e-4), 墙钟约3.0h(H200) |
| `np821b06_gptoss_cparam` | 2026-08-22 12:03 | probe_np821b06 | `1b9334f` | - | ok | best_val_ce=0.396 gsteps=17484 | np821b06 cparam 全量收官: best val_ce 0.396, 3 epoch 跑满, 墙钟约18.0h(H100) |
| `np821b06_gptoss_cgen` | 2026-08-22 12:03 | probe_np821b06 | `1b9334f` | - | ok | best_val_ce=0.4793 gsteps=17484 | np821b06 cgen 全量收官: best val_ce 0.4793, 3 epoch 跑满, 墙钟约17.9h(H100) |
| `np821b06_gptoss_ctool` | 2026-08-22 12:03 | probe_np821b06 | `1b9334f` | - | ok | best_calA_weighted_acc=0.6883 gsteps=387 align_maxdiff_hidden=9.78e-05 | np821b06 ctool 全量收官: best calA weighted acc 0.6883, ALIGN PASS(9.78e-05<3e-4), 墙钟约1.0h(H100) |
| `nyapass` | 2026-08-22 05:49 | collect_nyapass | `a8566db` | gpt-oss-120b | ok | trajs=1260 units=315 steps30_hit=41 | - |
| `eval_p1b17_gptoss_cparam` | 2026-08-21 21:42 | eval_p1b17 | `9b1e660` | - | ok | risk=0.1 theta=0.925 n_scored=818 pred_tool_full_call_ok=0.7066 pred_tool_params_all_ok=0.7543 gt_tool_params_all_ok=0.7702 noparam_rate=0.3178 | p1b17 cparam评测(risk 0.1,theta 0.925):818事件,pred_tool full_call_ok 0.7066/params_all_ok 0.7543,gt_tool params 0.7702 |
| `eval_p1b17_gptoss_cgen` | 2026-08-21 21:41 | eval_p1b17 | `9b1e660` | - | ok | risk=0.1 theta=0.925 n_scored=818 parse_fail=0 tool_ok=0.8998 params_all_ok=0.7494 full_call_ok=0.7066 | p1b17 cgen评测(risk 0.1,theta 0.925):818事件,parse_fail 0,tool_ok 0.8998,full_call_ok 0.7066 |
| `eval_p1b17_gptoss_ctool` | 2026-08-21 21:27 | eval_p1b17 | `e29e2a9` | - | ok | theta_risk10=0.925 coverage=0.3596 trig_acc=0.9108 earliness=0.6878 wrong_spec=0.0321 temperature=1.2196 prior_acc=0.4193 | p1b17 ctool评测:0.05档theta选不出(null),0.1档theta 0.925,test冻结 coverage 0.3596/trig_acc 0.9108/earliness 0.6878/wrong_spec 0.0321;call档按§4.3改传--risk 0.1 |
| `eval_p1b06_gptoss_cparam` | 2026-08-21 18:58 | eval_p1b06 | `4d540e3` | - | ok | n_events_scored=388 pred_tool_ok=0.9794 pred_params_all_ok=0.9046 pred_full_call_ok=0.8892 noparam_rate=0.3763 gt_params_all_ok=0.9072 | p1b06 cparam 评测 388 触发事件,pred_tool full_call_ok 0.8892 |
| `eval_p1b06_gptoss_cgen` | 2026-08-21 18:58 | eval_p1b06 | `4d540e3` | - | ok | n_events_scored=388 parse_fail_rate=0.0 tool_ok=0.9794 params_all_ok=0.8582 full_call_ok=0.8454 exact_call_ok=0.8454 | p1b06 cgen 评测 388 触发事件,full_call_ok 0.8454 |
| `eval_p1b06_gptoss_ctool` | 2026-08-21 18:47 | eval_p1b06 | `377d01e` | - | ok | theta_005=0.975 coverage=0.1705 trig_acc=0.9794 earliness=0.6109 wrong_spec=0.0035 temperature=1.2333 | p1b06 ctool 评测出报告,0.05 档 θ=0.975,test 冻结 coverage 0.1705 trig_acc 0.9794 |
| `p1l4_gptoss_cparam` | 2026-08-21 12:44 | probe_p1l4 | `ba609fa` | - | running | - | - |
| `p1l4_gptoss_cgen` | 2026-08-21 12:44 | probe_p1l4 | `ba609fa` | - | running | - | - |
| `p1l4_gptoss_ctool` | 2026-08-21 12:44 | probe_p1l4 | `ba609fa` | - | ok | best_calA_weighted_acc=0.6689 calA_lastbound_acc=0.7244 best_epoch=2 align_maxdiff_hidden=7.63e-05 | 4B LoRA+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6689 |
| `p1l17_gptoss_cparam` | 2026-08-21 12:44 | probe_p1l17 | `ba609fa` | - | running | - | - |
| `p1l17_gptoss_cgen` | 2026-08-21 12:44 | probe_p1l17 | `ba609fa` | - | running | - | - |
| `p1l17_gptoss_ctool` | 2026-08-21 12:44 | probe_p1l17 | `ba609fa` | - | ok | best_calA_weighted_acc=0.6628 calA_lastbound_acc=0.7007 best_epoch=2 align_maxdiff_hidden=7.63e-05 | 1.7B LoRA+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6628 |
| `p1l06_gptoss_cparam` | 2026-08-21 12:44 | probe_p1l06 | `ba609fa` | - | running | - | - |
| `p1l06_gptoss_cgen` | 2026-08-21 12:44 | probe_p1l06 | `ba609fa` | - | running | - | - |
| `p1l06_gptoss_ctool` | 2026-08-21 12:44 | probe_p1l06 | `ba609fa` | - | ok | best_calA_weighted_acc=0.6878 calA_lastbound_acc=0.7511 best_epoch=2 align_maxdiff_hidden=7.95e-05 | 0.6B LoRA+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6878 |
| `p1b17_gptoss_cparam` | 2026-08-21 12:44 | probe_p1b17 | `ba609fa` | - | ok | best_val_ce=0.332 best_epoch=0 val_exact_params=0.705 assembly_mismatch_train=0 assembly_mismatch_val=0 | p1b17 cparam(1.7B全参+gc)训完3ep,best ep0 val_ce 0.332,exact_params 0.705,拼装mismatch 0/0 |
| `p1b17_gptoss_cgen` | 2026-08-21 12:44 | probe_p1b17 | `ba609fa` | - | ok | best_val_ce=0.4531 best_epoch=1 val_exact_call=0.505 | p1b17 cgen(1.7B全参+gc)训完3ep,best ep1 val_ce 0.4531,exact_call 0.505 |
| `p1b17_gptoss_ctool` | 2026-08-21 12:44 | probe_p1b17 | `ba609fa` | - | ok | best_calA_weighted_acc=0.6685 calA_lastbound_acc=0.7526 best_epoch=2 align_maxdiff_hidden=0.000202 | 1.7B 全参+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6685 |
| `p1b06_gptoss_cparam` | 2026-08-21 12:43 | probe_p1b06 | `ba609fa` | - | ok | best_val_ce=0.3493 val_exact_params_at_best=0.675 best_epoch=0 assembly_mismatch_train=0 assembly_mismatch_val=0 | 0.6B 全参 cparam 三轮跑完,best 第 0 轮 val_ce 0.3493,剥离失败 0 |
| `p1b06_gptoss_cgen` | 2026-08-21 12:43 | probe_p1b06 | `ba609fa` | - | ok | best_val_ce=0.4043 val_exact_call_at_best=0.49 best_epoch=0 | 0.6B 全参 cgen 三轮跑完,best 第 0 轮 val_ce 0.4043 |
| `p1b06_gptoss_ctool` | 2026-08-21 12:43 | probe_p1b06 | `ba609fa` | - | ok | best_calA_weighted_acc=0.6924 calA_lastbound_acc=0.7585 best_epoch=2 align_maxdiff_hidden=0.000107 | 0.6B 全参 ctool 三轮跑完,best 第 2 轮 wacc 0.6924 |
| `p1` | 2026-08-21 08:29 | p1 采集批 | `51ee4f5+dirty` | gpt-oss-120b | ok | n_files=315 n_final=315 completed_true=305 abort_nonnull=0 split_train=90 split_dev=57 split_test_normal=168 steps_mean=13.1 | p1 采集批 315 题全部落轨迹,每文件末行 final,三堆 90/57/168 与官方题单对上,abort 全空,任务级 completed_true 305/315 |
| `ident3_v1` | 2026-08-18 10:47 | 探针线重启 | `3fec724` | gpt-oss-120b | ok | runs=150 excluded=0 success_chat=14/50 success_noprobe=13/50 success_nofill=20/50 identical_pairs=0/2175 div_step0_same_arm=412/675 div_step0_cross_arm=1303/1500 prompt_sha_equal=1780/1780 nofill_fires=564/657 resume_identical=534/564 | ident3_v1 三臂逐 token 同(chat/noprobe/nofill 伪触发第5句尾)5题x10遍=150跑 0 失败;跨臂 prompt id sha 1780/1780 全等;2175 对配对没有一对整题逐 token 全同,同臂对首分叉步 0 占 137/225(chat)、144/225(noprobe)、131/225(nofill),跨臂 chat-noprobe 308/500、chat-nofill 499/500、noprobe-nofill 496/500;shared_tok 中位 同臂 123/61/225、跨臂 123/123/120;每题每臂 10 遍 10 条不同轨迹;成功 chat 14/50、noprobe 13/50、nofill 20/50;nofill 564 次中断重发,534 次(0.947)逐位复现被丢弃溢出。事实,不带解读。 |
| `ident3_v1_srv` | 2026-08-18 10:21 | 探针线重启 | `91635ad+dirty` | - | running | - | - |
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

### `np821b17_gptoss_cgen`

- **结论**：np821b17 cgen 全量收官: best val_ce 0.512, 3 epoch 跑满, 墙钟约32.2h(H100,三次落位后)
- **方向**：probe_np821b17 ｜ **状态**：ok ｜ **起止**：2026-08-23 05:44 → 2026-08-24 15:34
- **代码**：`7dbd28e` (分支 main)
- **机器**：tokyo107 GPU 3
- **数字**：best_val_ce=0.512 gsteps=17484
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821b17_gptoss_cgen_t107g3.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_cgen --env appworld --base qwen17 --grad-ckpt`

### `np821b17_gptoss_cparam`

- **结论**：np821b17 cparam 全量收官: best val_ce 0.3378, 3 epoch 跑满, 墙钟约30.1h(H100)
- **方向**：probe_np821b17 ｜ **状态**：ok ｜ **起止**：2026-08-23 05:42 → 2026-08-24 15:34
- **代码**：`63884f2` (分支 main)
- **机器**：tokyo108 GPU 2
- **数字**：best_val_ce=0.3378 gsteps=17484
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821b17_gptoss_cparam_t108g2.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_cparam --env appworld --base qwen17 --grad-ckpt`

### `np821b17_gptoss_ctool`

- **结论**：np821b17 ctool 全量收官: best calA weighted acc 0.6867, ALIGN PASS(2.14e-04<3e-4), 墙钟约1.5h(H100)
- **方向**：probe_np821b17 ｜ **状态**：ok ｜ **起止**：2026-08-23 05:42 → 2026-08-23 07:17
- **代码**：`63884f2` (分支 main)
- **机器**：tokyo108 GPU 1
- **数字**：best_calA_weighted_acc=0.6867 gsteps=387 align_maxdiff_hidden=0.000214
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821b17_gptoss_ctool_t108g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821b17_gptoss_ctool --env appworld --base qwen --base qwen17 --align-tol 3e-4 --grad-ckpt`

### `np821l17_gptoss_cparam`

- **方向**：probe_np821l17 ｜ **状态**：running ｜ **起止**：2026-08-22 12:04 → 未收尾
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo107 GPU 2
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821l17_gptoss_cparam_t107g2.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821l17_gptoss_cparam --env appworld --base qwen17 --lora --grad-ckpt`

### `np821l17_gptoss_cgen`

- **方向**：probe_np821l17 ｜ **状态**：running ｜ **起止**：2026-08-22 12:04 → 未收尾
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo107 GPU 1
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821l17_gptoss_cgen_t107g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821l17_gptoss_cgen --env appworld --base qwen17 --lora --grad-ckpt`

### `np821l17_gptoss_ctool`

- **结论**：np821l17 ctool 全量收官: best calA weighted acc 0.6974, ALIGN PASS(2.37e-04<3e-4), 墙钟约3.2h(RTX6000Ada)
- **方向**：probe_np821l17 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:04 → 2026-08-22 15:02
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo107 GPU 0
- **数字**：best_calA_weighted_acc=0.6974 gsteps=387 align_maxdiff_hidden=0.000237
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821l17_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821l17_gptoss_ctool_t107g0.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821l17_gptoss_ctool --env appworld --base qwen --base qwen17 --align-tol 3e-4 --lora --grad-ckpt`

### `np821l4_gptoss_cparam`

- **结论**：np821 l4 cparam(Qwen3-4B LoRA+gc, H200) 3ep 完成, best_val_ce 0.3375, 墙钟约 64.4h
- **方向**：probe_np821l4 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:04 → 2026-08-25 04:54
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo108 GPU 5
- **数字**：best_val_ce=0.3375 gsteps=17484
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821l4_gptoss_cparam_t108g5.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_cparam --env appworld --base qwen4 --lora --grad-ckpt`

### `np821l4_gptoss_cgen`

- **结论**：np821 l4 cgen(Qwen3-4B LoRA+gc, H200) 3ep 完成, best_val_ce 0.371, 墙钟约 64.2h
- **方向**：probe_np821l4 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:04 → 2026-08-25 04:25
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo108 GPU 4
- **数字**：best_val_ce=0.371 gsteps=17484
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821l4_gptoss_cgen_t108g4.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_cgen --env appworld --base qwen4 --lora --grad-ckpt`

### `np821l4_gptoss_ctool`

- **结论**：np821l4 ctool 全量收官: best calA weighted acc 0.7016, ALIGN PASS(1.75e-04<3e-4), 墙钟约3.0h(H200)
- **方向**：probe_np821l4 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:04 → 2026-08-22 15:02
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo108 GPU 3
- **数字**：best_calA_weighted_acc=0.7016 gsteps=387 align_maxdiff_hidden=0.000175
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821l4_gptoss_ctool_t108g3.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821l4_gptoss_ctool --env appworld --base qwen --base qwen4 --align-tol 3e-4 --lora --grad-ckpt`

### `np821b06_gptoss_cparam`

- **结论**：np821b06 cparam 全量收官: best val_ce 0.396, 3 epoch 跑满, 墙钟约18.0h(H100)
- **方向**：probe_np821b06 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:03 → 2026-08-23 05:42
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo108 GPU 2
- **数字**：best_val_ce=0.396 gsteps=17484
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821b06_gptoss_cparam_t108g2.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_cparam --env appworld --base qwen`

### `np821b06_gptoss_cgen`

- **结论**：np821b06 cgen 全量收官: best val_ce 0.4793, 3 epoch 跑满, 墙钟约17.9h(H100)
- **方向**：probe_np821b06 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:03 → 2026-08-23 05:42
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo108 GPU 1
- **数字**：best_val_ce=0.4793 gsteps=17484
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821b06_gptoss_cgen_t108g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_cgen --env appworld --base qwen`

### `np821b06_gptoss_ctool`

- **结论**：np821b06 ctool 全量收官: best calA weighted acc 0.6883, ALIGN PASS(9.78e-05<3e-4), 墙钟约1.0h(H100)
- **方向**：probe_np821b06 ｜ **状态**：ok ｜ **起止**：2026-08-22 12:03 → 2026-08-22 13:32
- **代码**：`1b9334f` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：best_calA_weighted_acc=0.6883 gsteps=387 align_maxdiff_hidden=9.78e-05
- **原始数据**：`/home/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_np821b06_gptoss_ctool_t108g0.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/nyapass_aw_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/np821b06_gptoss_ctool --env appworld --base qwen --base qwen --align-tol 3e-4`

### `nyapass`

- **想验证什么**：nyapass_aw_v1 采集:每题 4 条轨迹
- **方向**：collect_nyapass ｜ **状态**：ok ｜ **起止**：2026-08-22 05:49 → 2026-08-22 11:10
- **代码**：`a8566db` (分支 main)
- **机器**：tokyo105 GPU cpu
- **模型 / 种子**：gpt-oss-120b / -
- **数字**：trajs=1260 units=315 steps30_hit=41
- **原始数据**：`/home/y-guo/reproduce/new1/envs/runs/nyapass/appworld_gptoss`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/envs/runs/nyapass/logs`
- **命令**：`bash /home/y-guo/reproduce/new1/envs/runs/nyapass/launch_clients.sh`

### `eval_p1b17_gptoss_cparam`

- **结论**：p1b17 cparam评测(risk 0.1,theta 0.925):818事件,pred_tool full_call_ok 0.7066/params_all_ok 0.7543,gt_tool params 0.7702
- **方向**：eval_p1b17 ｜ **状态**：ok ｜ **起止**：2026-08-21 21:42 → 2026-08-21 21:55
- **代码**：`9b1e660` (分支 main)
- **机器**：tokyo108 GPU 3
- **数字**：risk=0.1 theta=0.925 n_scored=818 pred_tool_full_call_ok=0.7066 pred_tool_params_all_ok=0.7543 gt_tool_params_all_ok=0.7702 noparam_rate=0.3178
- **原始数据**：`pipeline/runs/p1b17_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/eval_p1b17_gptoss_cparam.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_causal_param.py --env appworld --ctool-run /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_ctool --cparam-run /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_cparam --data /home/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/gptoss --risk 0.1`

### `eval_p1b17_gptoss_cgen`

- **结论**：p1b17 cgen评测(risk 0.1,theta 0.925):818事件,parse_fail 0,tool_ok 0.8998,full_call_ok 0.7066
- **方向**：eval_p1b17 ｜ **状态**：ok ｜ **起止**：2026-08-21 21:41 → 2026-08-21 21:55
- **代码**：`9b1e660` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：risk=0.1 theta=0.925 n_scored=818 parse_fail=0 tool_ok=0.8998 params_all_ok=0.7494 full_call_ok=0.7066
- **原始数据**：`pipeline/runs/p1b17_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/eval_p1b17_gptoss_cgen.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_causal_call.py --env appworld --ctool-run /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_ctool --cgen-run /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_cgen --data /home/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/gptoss --risk 0.1`

### `eval_p1b17_gptoss_ctool`

- **结论**：p1b17 ctool评测:0.05档theta选不出(null),0.1档theta 0.925,test冻结 coverage 0.3596/trig_acc 0.9108/earliness 0.6878/wrong_spec 0.0321;call档按§4.3改传--risk 0.1
- **方向**：eval_p1b17 ｜ **状态**：ok ｜ **起止**：2026-08-21 21:27 → 2026-08-21 21:41
- **代码**：`e29e2a9` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：theta_risk10=0.925 coverage=0.3596 trig_acc=0.9108 earliness=0.6878 wrong_spec=0.0321 temperature=1.2196 prior_acc=0.4193
- **原始数据**：`pipeline/runs/p1b17_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/eval_p1b17_gptoss_ctool.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_tool.py --env appworld --run /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_ctool --data /home/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/gptoss --head causal`

### `eval_p1b06_gptoss_cparam`

- **结论**：p1b06 cparam 评测 388 触发事件,pred_tool full_call_ok 0.8892
- **方向**：eval_p1b06 ｜ **状态**：ok ｜ **起止**：2026-08-21 18:58 → 2026-08-21 19:05
- **代码**：`4d540e3` (分支 main)
- **机器**：tokyo108 GPU 3
- **数字**：n_events_scored=388 pred_tool_ok=0.9794 pred_params_all_ok=0.9046 pred_full_call_ok=0.8892 noparam_rate=0.3763 gt_params_all_ok=0.9072
- **原始数据**：`pipeline/runs/p1b06_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/eval_p1b06_gptoss_cparam.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_causal_param.py --env appworld --ctool-run /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_ctool --cparam-run /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_cparam --data /home/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/gptoss`

### `eval_p1b06_gptoss_cgen`

- **结论**：p1b06 cgen 评测 388 触发事件,full_call_ok 0.8454
- **方向**：eval_p1b06 ｜ **状态**：ok ｜ **起止**：2026-08-21 18:58 → 2026-08-21 19:05
- **代码**：`4d540e3` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：n_events_scored=388 parse_fail_rate=0.0 tool_ok=0.9794 params_all_ok=0.8582 full_call_ok=0.8454 exact_call_ok=0.8454
- **原始数据**：`pipeline/runs/p1b06_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/eval_p1b06_gptoss_cgen.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_causal_call.py --env appworld --ctool-run /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_ctool --cgen-run /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_cgen --data /home/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/gptoss`

### `eval_p1b06_gptoss_ctool`

- **结论**：p1b06 ctool 评测出报告,0.05 档 θ=0.975,test 冻结 coverage 0.1705 trig_acc 0.9794
- **方向**：eval_p1b06 ｜ **状态**：ok ｜ **起止**：2026-08-21 18:47 → 2026-08-21 18:58
- **代码**：`377d01e` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：theta_005=0.975 coverage=0.1705 trig_acc=0.9794 earliness=0.6109 wrong_spec=0.0035 temperature=1.2333
- **原始数据**：`pipeline/runs/p1b06_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/eval_p1b06_gptoss_ctool.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/eval/eval_tool.py --env appworld --run /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_ctool --data /home/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/gptoss --head causal`

### `p1l4_gptoss_cparam`

- **方向**：probe_p1l4 ｜ **状态**：running ｜ **起止**：2026-08-21 12:44 → 未收尾
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 8
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l4_gptoss_cparam_t106g8.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l4_gptoss_cparam --env appworld --base qwen4 --lora --grad-ckpt`

### `p1l4_gptoss_cgen`

- **方向**：probe_p1l4 ｜ **状态**：running ｜ **起止**：2026-08-21 12:44 → 未收尾
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 7
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l4_gptoss_cgen_t106g7.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l4_gptoss_cgen --env appworld --base qwen4 --lora --grad-ckpt`

### `p1l4_gptoss_ctool`

- **结论**：4B LoRA+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6689
- **方向**：probe_p1l4 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:44 → 2026-08-21 16:16
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 6
- **数字**：best_calA_weighted_acc=0.6689 calA_lastbound_acc=0.7244 best_epoch=2 align_maxdiff_hidden=7.63e-05
- **原始数据**：`pipeline/runs/p1l4_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l4_gptoss_ctool_t106g6.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l4_gptoss_ctool --env appworld --base qwen --base qwen4 --align-tol 3e-4 --lora --grad-ckpt`

### `p1l17_gptoss_cparam`

- **方向**：probe_p1l17 ｜ **状态**：running ｜ **起止**：2026-08-21 12:44 → 未收尾
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 5
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l17_gptoss_cparam_t106g5.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l17_gptoss_cparam --env appworld --base qwen17 --lora --grad-ckpt`

### `p1l17_gptoss_cgen`

- **方向**：probe_p1l17 ｜ **状态**：running ｜ **起止**：2026-08-21 12:44 → 未收尾
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 4
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l17_gptoss_cgen_t106g4.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l17_gptoss_cgen --env appworld --base qwen17 --lora --grad-ckpt`

### `p1l17_gptoss_ctool`

- **结论**：1.7B LoRA+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6628
- **方向**：probe_p1l17 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:44 → 2026-08-21 14:16
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 3
- **数字**：best_calA_weighted_acc=0.6628 calA_lastbound_acc=0.7007 best_epoch=2 align_maxdiff_hidden=7.63e-05
- **原始数据**：`pipeline/runs/p1l17_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l17_gptoss_ctool_t106g3.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l17_gptoss_ctool --env appworld --base qwen --base qwen17 --align-tol 3e-4 --lora --grad-ckpt`

### `p1l06_gptoss_cparam`

- **方向**：probe_p1l06 ｜ **状态**：running ｜ **起止**：2026-08-21 12:44 → 未收尾
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 2
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l06_gptoss_cparam_t106g2.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l06_gptoss_cparam --env appworld --base qwen --lora --grad-ckpt`

### `p1l06_gptoss_cgen`

- **方向**：probe_p1l06 ｜ **状态**：running ｜ **起止**：2026-08-21 12:44 → 未收尾
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 1
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l06_gptoss_cgen_t106g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l06_gptoss_cgen --env appworld --base qwen --lora --grad-ckpt`

### `p1l06_gptoss_ctool`

- **结论**：0.6B LoRA+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6878
- **方向**：probe_p1l06 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:44 → 2026-08-21 14:16
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo106 GPU 0
- **数字**：best_calA_weighted_acc=0.6878 calA_lastbound_acc=0.7511 best_epoch=2 align_maxdiff_hidden=7.95e-05
- **原始数据**：`pipeline/runs/p1l06_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1l06_gptoss_ctool_t106g0.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1l06_gptoss_ctool --env appworld --base qwen --base qwen --align-tol 3e-4 --lora --grad-ckpt`

### `p1b17_gptoss_cparam`

- **结论**：p1b17 cparam(1.7B全参+gc)训完3ep,best ep0 val_ce 0.332,exact_params 0.705,拼装mismatch 0/0
- **方向**：probe_p1b17 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:44 → 2026-08-21 21:27
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo108 GPU 5
- **数字**：best_val_ce=0.332 best_epoch=0 val_exact_params=0.705 assembly_mismatch_train=0 assembly_mismatch_val=0
- **原始数据**：`pipeline/runs/p1b17_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1b17_gptoss_cparam_t108g5.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_cparam --env appworld --base qwen17 --grad-ckpt`

### `p1b17_gptoss_cgen`

- **结论**：p1b17 cgen(1.7B全参+gc)训完3ep,best ep1 val_ce 0.4531,exact_call 0.505
- **方向**：probe_p1b17 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:44 → 2026-08-21 21:27
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo108 GPU 4
- **数字**：best_val_ce=0.4531 best_epoch=1 val_exact_call=0.505
- **原始数据**：`pipeline/runs/p1b17_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1b17_gptoss_cgen_t108g4.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_cgen --env appworld --base qwen17 --grad-ckpt`

### `p1b17_gptoss_ctool`

- **结论**：1.7B 全参+gc ctool 三轮跑完,best 第 2 轮 wacc 0.6685
- **方向**：probe_p1b17 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:44 → 2026-08-21 13:17
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo108 GPU 3
- **数字**：best_calA_weighted_acc=0.6685 calA_lastbound_acc=0.7526 best_epoch=2 align_maxdiff_hidden=0.000202
- **原始数据**：`pipeline/runs/p1b17_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1b17_gptoss_ctool_t108g3.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1b17_gptoss_ctool --env appworld --base qwen --base qwen17 --align-tol 3e-4 --grad-ckpt`

### `p1b06_gptoss_cparam`

- **结论**：0.6B 全参 cparam 三轮跑完,best 第 0 轮 val_ce 0.3493,剥离失败 0
- **方向**：probe_p1b06 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:43 → 2026-08-21 18:47
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo108 GPU 2
- **数字**：best_val_ce=0.3493 val_exact_params_at_best=0.675 best_epoch=0 assembly_mismatch_train=0 assembly_mismatch_val=0
- **原始数据**：`pipeline/runs/p1b06_gptoss_cparam`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1b06_gptoss_cparam_t108g2.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_param.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_cparam --env appworld --base qwen`

### `p1b06_gptoss_cgen`

- **结论**：0.6B 全参 cgen 三轮跑完,best 第 0 轮 val_ce 0.4043
- **方向**：probe_p1b06 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:43 → 2026-08-21 18:47
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo108 GPU 1
- **数字**：best_val_ce=0.4043 val_exact_call_at_best=0.49 best_epoch=0
- **原始数据**：`pipeline/runs/p1b06_gptoss_cgen`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1b06_gptoss_cgen_t108g1.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_cgen --env appworld --base qwen`

### `p1b06_gptoss_ctool`

- **结论**：0.6B 全参 ctool 三轮跑完,best 第 2 轮 wacc 0.6924
- **方向**：probe_p1b06 ｜ **状态**：ok ｜ **起止**：2026-08-21 12:43 → 2026-08-21 13:17
- **代码**：`ba609fa` (分支 main)
- **机器**：tokyo108 GPU 0
- **数字**：best_calA_weighted_acc=0.6924 calA_lastbound_acc=0.7585 best_epoch=2 align_maxdiff_hidden=0.000107
- **原始数据**：`pipeline/runs/p1b06_gptoss_ctool`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/logs/new1_p1b06_gptoss_ctool_t108g0.log`
- **命令**：`/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --data pipeline/data/aw_p1_v1/gptoss --out /home/y-guo/reproduce/new1/pipeline/runs/p1b06_gptoss_ctool --env appworld --base qwen --base qwen --align-tol 3e-4`

### `p1`

- **想验证什么**：p1 采集:AppWorld 官方三堆全量 315 题,gpt-oss-120b 单模型 harmony/effort high,双 vLLM 实例(tokyo108 GPU4/5 H200)+7 客户端分片,给三种训法×三档底座供数据
- **结论**：p1 采集批 315 题全部落轨迹,每文件末行 final,三堆 90/57/168 与官方题单对上,abort 全空,任务级 completed_true 305/315
- **方向**：p1 采集批 ｜ **状态**：ok ｜ **起止**：2026-08-21 08:29 → 2026-08-21 11:37
- **代码**：`51ee4f5`  ⚠️ 发射时工作树是脏的（10 文件），这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo108 GPU 4,5
- **模型 / 种子**：gpt-oss-120b / 20260729
- **参数**：preset=gptoss_harmony_high api=harmony reasoning_effort=high temperature=0.0 start_date=2026-08-06 max_steps=30 splits=train90+dev57+test_normal168 tasks=315 shards=7 servers=2 data_version=aw_p1_v1
- **数字**：n_files=315 n_final=315 completed_true=305 abort_nonnull=0 split_train=90 split_dev=57 split_test_normal=168 steps_mean=13.1
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/envs/runs/p1/appworld_gptoss`（不在 git 里）
- **日志**：`/home/y-guo/reproduce/new1/envs/runs/p1/logs`
- **命令**：`python3 run.py gen-launch --config pipeline/collect/manifest_p1.json && cd envs/runs/p1 && python3 launch_servers.py && bash launch_clients.sh`

### `ident3_v1`

- **想验证什么**：三臂逐 token 同:chat / no probe / probe-but-nofill(伪触发第 5 个句尾切口、模型自己的 id 重发、不塞),5 题 x 10 遍,量同臂/跨臂逐 token 分叉与 nofill 重发复现度
- **结论**：ident3_v1 三臂逐 token 同(chat/noprobe/nofill 伪触发第5句尾)5题x10遍=150跑 0 失败;跨臂 prompt id sha 1780/1780 全等;2175 对配对没有一对整题逐 token 全同,同臂对首分叉步 0 占 137/225(chat)、144/225(noprobe)、131/225(nofill),跨臂 chat-noprobe 308/500、chat-nofill 499/500、noprobe-nofill 496/500;shared_tok 中位 同臂 123/61/225、跨臂 123/123/120;每题每臂 10 遍 10 条不同轨迹;成功 chat 14/50、noprobe 13/50、nofill 20/50;nofill 564 次中断重发,534 次(0.947)逐位复现被丢弃溢出。事实,不带解读。
- **方向**：探针线重启 ｜ **状态**：ok ｜ **起止**：2026-08-18 10:47 → 2026-08-18 20:14
- **代码**：`3fec724` (分支 main)
- **机器**：shiga GPU -
- **模型 / 种子**：gpt-oss-120b / 100
- **参数**：arms=chat,noprobe,nofill tasks=test_normal[:5] reps=10 fire_nth_cut=5 max_steps=20
- **数字**：runs=150 excluded=0 success_chat=14/50 success_noprobe=13/50 success_nofill=20/50 identical_pairs=0/2175 div_step0_same_arm=412/675 div_step0_cross_arm=1303/1500 prompt_sha_equal=1780/1780 nofill_fires=564/657 resume_identical=534/564
- **原始数据**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/ident3_v1/IDENT3_REPORT.md`（不在 git 里）
- **日志**：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/ident3_v1/logs`
- **命令**：`envs/serve_logs/ident3_job.sh {chat,noprobe,nofill} /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/inject/runs/ident3_v1 10 5 8114 http://localhost:8795 (shiga tmux new1_ident3_v1_<arm> x3 并行;vLLM=ident3_v1_srv tokyo108:8114;render-only probe_server shiga:8795)`

### `ident3_v1_srv`

- **方向**：探针线重启 ｜ **状态**：running ｜ **起止**：2026-08-18 10:21 → 未收尾
- **代码**：`91635ad`  ⚠️ 发射时工作树是脏的（10 文件），这个 commit 追不回真实代码 (分支 main)
- **机器**：tokyo108 GPU 0
- **日志**：`/home/y-guo/reproduce/new1/envs/serve_logs/logs/new1_ident3_v1_srv_t108g0.log`
- **命令**：`LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID VLLM_CACHE_ROOT=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache TRITON_CACHE_DIR=/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/triton VLLM_SYSTEM_START_DATE=2026-07-31 /home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm serve /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b --served-model-name gpt-oss-120b --port 8114 --host 0.0.0.0 --max-model-len 65536 --gpu-memory-utilization 0.92`

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
