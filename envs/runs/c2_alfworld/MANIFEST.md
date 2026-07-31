# 发射清单 — c2_alfworld

gen_launch.py 生成(勿手改)。服务 3 实例 / 客户端 22 分片。

## 服务表

| host | GPU idx | 卡 | 模型 | served-model-name | 端口 | 追加旗标 | session | 日志 |
|---|---|---|---|---|---|---|---|---|
| tokyo108 | 0 | H100 | q36(副本 A) | qwen3.6-27b | 8101 | --max-num-seqs 512 | `new1_c2_srv_q36_t108g0` | `/home/y-guo/reproduce/new1/envs/serve_logs/new1_c2_srv_q36_t108g0.log` |
| tokyo108 | 1 | H100 | gptoss(副本 A) | gpt-oss-120b | 8102 | — | `new1_c2_srv_gptossa_t108g1` | `/home/y-guo/reproduce/new1/envs/serve_logs/new1_c2_srv_gptossa_t108g1.log` |
| tokyo108 | 2 | H100 | gptoss(副本 B) | gpt-oss-120b | 8103 | — | `new1_c2_srv_gptossb_t108g2` | `/home/y-guo/reproduce/new1/envs/serve_logs/new1_c2_srv_gptossb_t108g2.log` |

Qwen 通用旗标:`--reasoning-parser deepseek_r1 --max-model-len 65536 --gpu-memory-utilization 0.92 --enable-auto-tool-choice --tool-call-parser qwen3_coder`;
gpt-oss 不带 Qwen 旗标,只要 `--gpu-memory-utilization 0.92`。

## 分片表

| tag | 模型 | split | num-shards | shard-id → 端口 | outdir | exp | session |
|---|---|---|---|---|---|---|---|
| q36tr | qwen3.6-27b | train | 4 | s0→8101, s1→8101, s2→8101, s3→8101 | `$F/alfworld_q36` | c2q36tr | `new1_c2alf_q36tr_s<k>` |
| q36va | qwen3.6-27b | val | 2 | s0→8101, s1→8101 | `$F/alfworld_q36` | c2q36va | `new1_c2alf_q36va_s<k>` |
| q36te | qwen3.6-27b | test | 2 | s0→8101, s1→8101 | `$F/alfworld_q36` | c2q36te | `new1_c2alf_q36te_s<k>` |
| gptr | gpt-oss-120b | train | 6 | s0→8102, s1→8102, s2→8102, s3→8103, s4→8103, s5→8103 | `$F/alfworld_gptoss` | c2gptr | `new1_c2alf_gptr_s<k>` |
| gpva | gpt-oss-120b | val | 4 | s0→8102, s1→8102, s2→8103, s3→8103 | `$F/alfworld_gptoss` | c2gpva | `new1_c2alf_gpva_s<k>` |
| gpte | gpt-oss-120b | test | 4 | s0→8102, s1→8102, s2→8103, s3→8103 | `$F/alfworld_gptoss` | c2gpte | `new1_c2alf_gpte_s<k>` |

`$F` = `/home/y-guo/reproduce/new1/envs/runs/c2_alfworld`,日志 `$F/logs/<session>.log`。
客户端统一参数 `--n 0 --max-steps 50 --resume`;gpt-oss 分片额外 `--api chat --reasoning-effort high`。
outdir 一律 `alfworld_<model_key>` 标准名(下游事件抽取按目录名尾巴认模型)。

## 发射顺序

1. `python3 launch_servers.py`(六实例起齐,日志出现 "Application startup complete" 且 `curl -s http://<host>:<port>/v1/models` 有返回)
2. smoke:每模型 1 题(执行手册 §3.3)
3. `bash launch_clients.sh`
4. 双登记:`ops/gpu_jobs.py register` + `ops/record.py start`
