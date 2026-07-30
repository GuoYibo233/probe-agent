# 执行手册 — 新流水线全链（写给执行会话的傻瓜书）

> **生效前提：用户说了"发射"。** 说了之后整条链做到底，**中途不再向用户请示**——
> 包括杀 vLLM 释放显存、发射 12 次训练这些原本要二次确认的动作，授权都包含在那一句里。
> 唯一要停下等用户的情况：结构性死局（推翻前提的事，比如 test_normal 任务在环境里
> 根本跑不了）。停之前把已完成的部分收尾干净。
>
> 配套文档（先读完再动手）：
> - 总计划：`/home/y-guo/reproduce/new1/plans/2026-07-31-pipeline-plan.md`
> - 施工图（五段工程细节）：`/home/y-guo/reproduce/new1/plans/2026-07-31-pipeline-engineering.md`
> - 本手册：执行层，命令与路径全部写死，照抄即可。

---

## 0. 用户的规矩（最高优先级，违反任何一条都是事故）

1. **GPU 发射必须有用户明确的"发射"**。回答子话题的"可以/就这样吧"不算。
   本手册的执行以用户已说"发射"为前提；链内动作免再批，链外的新主意仍要问。
2. **一个请求只做那一件事**，不顺手加活、不顺手改别的文件。
3. **禁止调用任何外部付费 API**。三个 agent 模型全部本地 vLLM 自建服务。
4. **与 `/home/y-guo/ACL2026` 完全隔离**：不读写其数据/代码/结果（共用硬件没问题）。
5. GPU 任务一律走 **`gpu-run` skill** 全生命周期（探卡→smoke→tmux→双登记→巡检→收尾），
   禁止手搓 ssh/nohup 裸发。
6. **qwen3.5 与 qwen3.6 永远是两个模型**，任何场合不合并成"qwen 侧"。
7. **口径全盘继承**：切样本规则、损失权重 w=1/m、评测三步法一个数不改；
   **v3 旧数据与旧数字一个字节不动**，新产物一律新目录新版本号。
8. **全自动标注，失败轨迹照用**（探针学"模型会做什么"，不是"应该做什么"）。
9. **种子 20260729 固定**，写进配置和每份报告；重跑必须逐样本一致。
10. **记录体系**：发射时 `record.py start`、收尾 `record.py finish`；
    `RESULTS.md` 是渲染产物不许手改；`ops/runs.jsonl` 只增不改；
    台账只通过 `gpu_jobs.py register/finish` 读写；
    **run_id 四处一致**（数据目录名 = tmux session 前缀 = 台账 name = commit message）。
11. **发射前先 commit**，工作树必须干净（否则记录里的 HEAD 追不回真实代码）。
12. **批量任务结束不许占卡过夜**：收尾必须杀干净服务、`nvidia-smi` 显存归零。
13. 双环境铁律：ModernBERT 线只用 `mbert-env`（transformers 4.57.6 钉死），
    因果线只用 `cprobe-env`（≥5.14），**谁也不许升级谁**。
14. 文档与汇报风格：事实和解读分开、事实在前；每个数字带指代和出处；
    不写统计判线的论证（用户明确不要）。

## 1. 地图（所有路径，全部绝对）

| 东西 | 路径 |
|---|---|
| 仓库根 | `/home/y-guo/reproduce/new1` |
| 台账 CLI | `python /home/y-guo/reproduce/new1/ops/gpu_jobs.py`（`free` 探卡 / `register` / `finish` / `watch`） |
| 实验记录 CLI | `python /home/y-guo/reproduce/new1/ops/record.py`（`start` / `finish`，语法见 §3.6） |
| 集群档案 | `/home/y-guo/reproduce/new1/ops/gpu_state.md`（H100/H200 idx 分布、CUDA 版本坑） |
| vLLM 可执行 | `/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm` |
| 服务端发射模板 | `/home/y-guo/reproduce/new1/envs/serve_logs/launch_vllm_topup.py`（照它写新的，环境变量三件套别丢：`LD_LIBRARY_PATH=.../envs/cuda-compat-13.0 VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID`） |
| 客户端发射模板 | `/home/y-guo/reproduce/new1/envs/runs/full_v2_topup/launch_clients.sh` |
| appworld 采集器 | `/home/y-guo/reproduce/new1/envs/collect/run_appworld.py`，解释器必须用 `/home/y-guo/reproduce/new1/envs/appworld/venv/bin/python` |
| appworld 官方题单 | `/home/y-guo/reproduce/new1/envs/appworld/data/datasets/{dev,train,test_normal,test_challenge}.txt`（57/90/168/417 题；wc -l 会各少 1，文件没有末尾换行） |
| Qwen3.5-27B 权重 | `/net/tokyo100-10g/data/str01_01/zhou-y/models/Qwen3.5-27B` |
| Qwen3.6-27B 权重 | `/net/tokyo100-10g/data/str01_01/zhou-y/models/Qwen3.6-27B` |
| gpt-oss-120b 权重 | `/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b` |
| ModernBERT 线解释器 | `/home/y-guo/reproduce/new1/mbert-env/bin/python` |
| 因果线解释器 | `/home/y-guo/reproduce/new1/cprobe-env/bin/python` |
| 旧训练脚本（复刻参照） | `/home/y-guo/reproduce/new1/envs/bert/{train_probe,train_extractor,train_causal_probe}.py` |
| 旧评测脚本（复刻参照） | `/home/y-guo/reproduce/new1/envs/bert/{eval_replay,eval_extract}.py`、标签规则 `param_label.py` |
| 旧切样本脚本（复刻参照） | `/home/y-guo/reproduce/new1/envs/collect/build_dataset.py` |
| 验收用旧数据 | 数据集 `/home/y-guo/reproduce/new1/envs/bert_data/v3/bfcl/`；现成 logits `/home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3/logits_*.pt`；对答案 `RESULTS.md` 的 v3 bfcl 行 |
| 注入格式参照 | `/home/y-guo/reproduce/new1/envs/loop/probe_server.py`（吃 `<run>/best/` + `label_map.json` + `REPLAY_REPORT.json` 里的 temperature） |
| 本次采集落盘 | `/home/y-guo/reproduce/new1/envs/runs/w0_aw_official/`（新建；.gitignore 已覆盖 `envs/runs/**`，只有 .md 进 git） |

## 2. 全链总览（顺序执行，A 跑着的时候做 B）

- **Phase A**：采集发射（占 tokyo108 六卡，墙钟估 3–5 小时）
- **Phase B**：写新流水线五段 + 过双验收线（纯 CPU，与 A 并行）
- **Phase C**：造数据集 → 四格 smoke → 12 次训练 + 回放评测（A6000 池约 2 小时）
- **Phase D**：收官（记账、汇报、释放、commit）

## 3. Phase A — 采集发射（run_id = `w0_aw_official`）

### 3.1 发射前

```bash
cd /home/y-guo/reproduce/new1
git status --short   # 必须干净；不干净先 commit
python ops/gpu_jobs.py free   # 现探空卡，只用 OWNERS=FREE 的卡；tokyo108 六卡必须全 FREE
```

### 3.2 服务端：tokyo108 六卡六实例

照 `launch_vllm_topup.py` 写 `/home/y-guo/reproduce/new1/envs/serve_logs/launch_vllm_w0.py`，
JOBS 表如下（Qwen 通用旗标 = `--reasoning-parser deepseek_r1 --max-model-len 65536
--gpu-memory-utilization 0.92 --enable-auto-tool-choice --tool-call-parser qwen3_coder`）：

| GPU idx | 卡 | 模型 | served-model-name | 端口 | 追加旗标 | session 名 |
|---|---|---|---|---|---|---|
| 3 | H200 | Qwen3.5-27B | `qwen3.5-27b` | 8101 | — | `new1_w0_srv_q35a_t108g3` |
| 2 | H100 | Qwen3.5-27B | `qwen3.5-27b` | 8102 | `--max-num-seqs 512` | `new1_w0_srv_q35b_t108g2` |
| 0 | H100 | Qwen3.6-27B | `qwen3.6-27b` | 8104 | `--max-num-seqs 512` | `new1_w0_srv_q36a_t108g0` |
| 1 | H100 | Qwen3.6-27B | `qwen3.6-27b` | 8105 | `--max-num-seqs 512` | `new1_w0_srv_q36b_t108g1` |
| 4 | H200 | gpt-oss-120b | `gpt-oss-120b` | 8103 | —（gpt-oss 不带 Qwen 旗标，只要 `--gpu-memory-utilization 0.92`） | `new1_w0_srv_gptossa_t108g4` |
| 5 | H200 | gpt-oss-120b | `gpt-oss-120b` | 8106 | 同上 | `new1_w0_srv_gptossb_t108g5` |

坑：**H100（95G）上跑 Qwen 必须 `--max-num-seqs 512`**（Mamba cache 只够 612 块，
默认 1024 会崩）。日志落 `/home/y-guo/reproduce/new1/envs/serve_logs/<session>.log`。
健康判据：日志出现 "Application startup complete"，且
`curl -s http://tokyo108:<port>/v1/models` 返回模型名。六个全健康才进下一步。

### 3.3 smoke（每模型 1 题，不通过不许放量）

三条命令（本机 tmux 或前台皆可；`E=/home/y-guo/reproduce/new1/envs`，
`F=$E/runs/w0_aw_official`）：

```bash
$E/appworld/venv/bin/python $E/collect/run_appworld.py \
  --base-url http://tokyo108:8101/v1 --model qwen3.5-27b \
  --split test_normal --n 1 --max-steps 30 \
  --outdir $F/appworld_q35_tn --exp w0q35tn_smoke
# qwen3.6 同上：端口 8104，outdir $F/appworld_q36_tn，exp w0q36tn_smoke
# gpt-oss 同上：端口 8103，outdir $F/appworld_gptoss_tn，exp w0gptn_smoke，
#   末尾加 --api chat --reasoning-effort high
```

通过判据：outdir 里出现 `appworld_<tid>.jsonl`，文件里 `type:"llm"` 条目带非空
`think` 字段、`type:"env"` 条目带代码动作。smoke 采过的题，全量时 `--resume` 自动跳过。
失败就修（先查服务日志），修不好按 §6 判断是否死局。

### 3.4 客户端：14 分片全上

写 `/home/y-guo/reproduce/new1/envs/runs/w0_aw_official/launch_clients.sh`，
照 `full_v2_topup/launch_clients.sh` 的 `tm()`/`aw()` 函数改。统一参数：
`--n 0 --max-steps 30 --resume`；gpt-oss 分片额外 `--api chat --reasoning-effort high`。
日志 `$F/logs/<session>.log`。分片表（session 名 = `new1_w0aw_<tag>_s<k>`）：

| tag | split | num-shards | shard-id → 端口 | outdir | exp |
|---|---|---|---|---|---|
| q35tr | train | 2 | s0→8101，s1→8102 | `$F/appworld_q35_train` | `w0q35tr` |
| q35tn | test_normal | 4 | s0,s1→8101，s2,s3→8102 | `$F/appworld_q35_tn` | `w0q35tn` |
| q36tn | test_normal | 4 | s0,s1→8104，s2,s3→8105 | `$F/appworld_q36_tn` | `w0q36tn` |
| gptn | test_normal | 4 | s0,s1→8103，s2,s3→8106 | `$F/appworld_gptoss_tn` | `w0gptn` |

（qwen3.5 每实例 3 条并发流、其他模型 2 条，这是故意的——q3.5 题多，拉平墙钟。）

### 3.5 双登记（发射后立刻）

```bash
cd /home/y-guo/reproduce/new1
python ops/gpu_jobs.py register --name w0_aw_official \
  --workdir /home/y-guo/reproduce/new1/envs/runs/w0_aw_official \
  --piece tokyo108:3:new1_w0_srv_q35a_t108g3:/home/y-guo/reproduce/new1/envs/serve_logs/new1_w0_srv_q35a_t108g3.log \
  --piece tokyo108:2:new1_w0_srv_q35b_t108g2:/home/y-guo/reproduce/new1/envs/serve_logs/new1_w0_srv_q35b_t108g2.log \
  --piece tokyo108:0:new1_w0_srv_q36a_t108g0:/home/y-guo/reproduce/new1/envs/serve_logs/new1_w0_srv_q36a_t108g0.log \
  --piece tokyo108:1:new1_w0_srv_q36b_t108g1:/home/y-guo/reproduce/new1/envs/serve_logs/new1_w0_srv_q36b_t108g1.log \
  --piece tokyo108:4:new1_w0_srv_gptossa_t108g4:/home/y-guo/reproduce/new1/envs/serve_logs/new1_w0_srv_gptossa_t108g4.log \
  --piece tokyo108:5:new1_w0_srv_gptossb_t108g5:/home/y-guo/reproduce/new1/envs/serve_logs/new1_w0_srv_gptossb_t108g5.log
```

### 3.6 实验记录（与 3.5 同时）

```bash
python ops/record.py start --name w0_aw_official --track pipeline \
  --model "qwen3.5-27b,qwen3.6-27b,gpt-oss-120b" --seed 20260729 \
  --host tokyo108 --gpu 0,1,2,3,4,5 \
  --param split=train+test_normal --param tasks=594 --param max_steps=30 \
  --data /home/y-guo/reproduce/new1/envs/runs/w0_aw_official \
  --cmd "launch_vllm_w0.py + launch_clients.sh (14 shards)" \
  --note "第0波:appworld官方分区采集,q3.5补train 90+三模型各采test_normal 168"
```

### 3.7 监控

- 用户自助入口（发射后把这两行原样发在对话里）：
  `python /home/y-guo/reproduce/new1/ops/gpu_jobs.py` 和 `... watch`
- Claude 侧：job-monitor 只读 agent 30 分钟一巡（进度 = 各 outdir 里 jsonl 文件数）。
- 分片挂了：读日志定位 → 修复 → 只重发该分片（`--resume` 保证不重跑已完成的题）。
- 服务实例挂了救不活：把它的分片改指同模型另一实例的端口重发，不停摆。

### 3.8 Phase A 收尾（做完立刻，不等 Phase B/C）

1. 核对条数：`appworld_q35_train` 90 个 jsonl、`appworld_q35_tn`/`appworld_q36_tn`/
   `appworld_gptoss_tn` 各 168 个，且每个文件末行是 `type:"final"`。
2. 缺的题重发对应分片补齐（`--resume`）。
3. 杀六个服务：`ssh tokyo108 tmux kill-session -t <session>` × 6；
   `ssh tokyo108 nvidia-smi` 确认显存归零（授权已含，不必再问用户）。
4. `python ops/gpu_jobs.py finish w0_aw_official`
5. `python ops/record.py finish w0_aw_official --status ok \
   --metric files=594 --conclusion "<一句话:各模型完成数与中位步数>"`
6. commit（message 带 `w0_aw_official`）。

## 4. Phase B — 写新流水线（与 Phase A 并行，纯 CPU）

逐段细节在施工图 `2026-07-31-pipeline-engineering.md`，此处只列执行要点：

1. 顶层建 `pipeline/{collect,annotate,train,eval,inject,configs}/`；
   `.gitignore` 追加 `pipeline/data/**`、`pipeline/runs/**`（保 `!**/*.md`，
   照 `envs/bert_data` 现有模式抄）。
2. 写码顺序：annotate → eval → train 四格 → collect 生成器 → inject 校验器。
3. **双验收线，全过才准进 Phase C**：
   - annotate 验收：拿 `envs/runs/` 里 v3 用过的 bfcl 原始轨迹重跑切样本，
     与 `envs/bert_data/v3/bfcl/` **逐字节 diff**（只比旧字段，新增 label_call 除外）。
   - eval 验收：复用 `envs/bert_runs/bfcl_v3/logits_*.pt` 跑新 eval（零 GPU），
     数字对上 `RESULTS.md` 的 v3 bfcl 行。
4. 超参与规则**全部照抄**旧脚本，一个数不改（清单见施工图 §2/§3/§4）。
   唯一的新东西：因果+参数的训练目标和它的判分器。

## 5. Phase C — 数据集 + 12 次训练 + 回放评测

1. **造数据集**（CPU）：用新 annotate 段，输入 = `w0_aw_official` 新轨迹 +
   v3 已有的 appworld 旧轨迹（q3.5 dev 57 / q3.6 dev+train 147 / gpt-oss dev+train 147，
   在 `envs/runs/full_v1/` 与 `full_v2_topup/`），按官方分区落三堆：
   train 区 90 题 = 训练堆，dev 区 57 题 = val 堆，test_normal 区 168 题 = test 堆。
   每模型一套，产 `pipeline/data/aw_official_v1/<model>/{train,val,test}.jsonl` +
   `ANNOTATE_REPORT.md`；`DATA.md` §3/§4 补版本条目。
2. **四格 smoke**：每格 50 步微训（loss 在降、ckpt 能存读）。
3. **发射 12 次训练**：3 模型 × 4 格。走 gpu-run：现探空卡，从 tokyo105 的 8 张
   A6000 起（CUDA 12.9 最稳），不够再上 106（cu128 轮子先 10 秒实测能跑）。
   session 名 `new1_c1_<model>_<cell>_t<host>g<gpu>`；每 run `record.py start`
   （run_id 形如 `c1_q35_mbert_tool`，--track pipeline）。
   解释器：mbert 格用 `mbert-env/bin/python`，causal 格用 `cprobe-env/bin/python`。
4. **回放评测**：训练全收敛后跑 eval 段（温度 val 拟、门槛 val 扫、test 冻结一次），
   产 12 份 `REPLAY_REPORT.json` + 一份全矩阵汇总 md。
5. 每 run `record.py finish --metric trig_acc=... --metric coverage=...`（参数格
   加三档参数指标）；释放；销号；commit。

## 6. 意外处置边界

- **自动处置（不找用户）**：分片挂→修+重发；实例挂→分片改port；OOM→砍并发/
  换更大卡重发；单题超时卡死→跳过该题记入报告缺口。
- **停下等用户（先收尾再停）**：test_normal 任务在 appworld 里根本跑不了、
  权重路径失效、双验收线反复过不了这类**推翻前提**的事。
- 已知的仪器坑：appworld 包内置 freezegun 冻结了进程内时钟，
  **不要用 time.time() 测单题耗时**，要测就用 jsonl 文件 mtime 差。
  evaluate() 在 test 分区可能报错——采集器已容错（评测失败不弃轨迹），属正常。

## 7. 最终汇报格式（Phase D）

全链收官后一次性汇报：各模型采集完成数与落盘路径、双验收线的证据、
12 格矩阵的关键数字表（触发准确率/覆盖率/参数三档）、每格一句话结论、
所有 run_id 清单、TIMELINE 补的条目。事实在前、解读在后，每个数字带出处。
