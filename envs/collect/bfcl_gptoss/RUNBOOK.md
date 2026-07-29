# bfcl_gptoss 补采执行手册(2026-07-30)

代码全部就绪(handler 已装进 venv 并注册,commit 6fc03f3),
本 session 被权限拦截无法 ssh 发射,按下列步骤由 gpu-runner 或人工执行。
每步都幂等,断了从当步重跑。

## 1. 发射服务(tokyo108 H100 g0,发射时实探确认仍空闲)

```bash
python3 /home/y-guo/reproduce/new1/envs/serve_logs/launch_vllm_bfcl_gptoss.py
```

就绪判据(120B 从 NFS 加载约 5-10 分钟):

```bash
curl -s http://tokyo108:8103/v1/models | grep gpt-oss-120b
```

## 2. smoke:单任务全流程

```bash
cd /home/y-guo/reproduce/new1/envs/bfcl
printf '{"multi_turn_base": ["multi_turn_base_0"]}\n' > test_case_ids_to_generate.json
BFCL_PROJECT_ROOT=$PWD LOCAL_SERVER_ENDPOINT=tokyo108 LOCAL_SERVER_PORT=8103 \
venv/bin/bfcl generate --model openai/gpt-oss-120b \
  --test-category multi_turn_base --run-ids --skip-server-setup \
  --local-model-path /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b \
  --num-threads 1 \
  --result-dir /home/y-guo/reproduce/new1/envs/runs/full_v2_topup/bfcl_gptoss
```

(--run-ids 会用 ids 文件**替代**类目全集,已读源码确认,只跑这 1 题;
smoke 直接写最终目录,全量续跑按 id 去重不重做。单题高思考档可能要 10 分钟量级。)

验收(两条都过才继续):

```bash
python3 - <<'EOF'
import json, glob
f = glob.glob("/home/y-guo/reproduce/new1/envs/runs/full_v2_topup/bfcl_gptoss/**/*multi_turn*result.json", recursive=True)[0]
e = json.loads(open(f).readline())
logs = e["inference_log"]
rc = [m.get("reasoning_content","") for turn in logs for m in (turn if isinstance(turn,list) else [turn]) if isinstance(m,dict) and m.get("role")=="assistant"]
print("思考字符数(每轮):", [len(x) for x in rc][:10])
print("首轮动作:", str(e["result"][0])[:200])
EOF
```

- 思考字符数普遍 > 0(reasoning 通道通了)
- 首轮动作是 `[func(...)]` 形态的调用文本(文本协议解析通了)

若 vLLM 拒收 model 名(404):服务端没设 served-model-name 时模型 id=权重路径,
与 --local-model-path 相同,理论上必对;真报错就看 curl /v1/models 返回的 id,
用 REMOTE_OPENAI_BASE_URL 覆盖或改 launcher 加 --served-model-name 对齐。

## 3. 全量发射(200 题,tmux,本机)

```bash
tmux new-session -d -s new1_topup_bfcl_gptoss bash -c '
cd /home/y-guo/reproduce/new1/envs/bfcl
LOCAL_SERVER_ENDPOINT=tokyo108 LOCAL_SERVER_PORT=8103 \
venv/bin/bfcl generate --model openai/gpt-oss-120b \
  --test-category multi_turn_base --skip-server-setup \
  --local-model-path /net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b \
  --num-threads 4 \
  --result-dir /home/y-guo/reproduce/new1/envs/runs/full_v2_topup/bfcl_gptoss \
  2>&1 | tee /home/y-guo/reproduce/new1/envs/runs/full_v2_topup/logs/bfcl_gptoss.log'
```

## 4. 双登记

```bash
cd /home/y-guo/reproduce/new1
python3 ops/gpu_jobs.py register --name bfcl_gptoss_topup \
  --piece "tokyo108:0:new1_srv_gptoss_bfcl_t108g0:/home/y-guo/reproduce/new1/envs/serve_logs/new1_srv_gptoss_bfcl_t108g0.log" \
  --piece "$(hostname):-:new1_topup_bfcl_gptoss:/home/y-guo/reproduce/new1/envs/runs/full_v2_topup/logs/bfcl_gptoss.log"
python3 ops/record.py start --name bfcl_gptoss_topup --track collect \
  --cmd "bfcl generate --model openai/gpt-oss-120b --test-category multi_turn_base(经 chat 端点,reasoning high)" \
  --host tokyo108 --gpu 0 --model gpt-oss-120b \
  --data envs/runs/full_v2_topup/bfcl_gptoss \
  --note "补 v1 缺口:bfcl 无 gpt-oss 轨迹,跨模型双向矩阵需要它"
```

## 5. 收尾(批次跑完)

- 完成判据:result.json 200 个 id 齐(`python3 -c` 数行数)。
- 杀服务:ssh tokyo108 tmux kill-session new1_srv_gptoss_bfcl_t108g0,nvidia-smi 确认 g0 归零。
- `gpu_jobs.py finish bfcl_gptoss_topup` + `record.py finish <run_id> --metric n_traj=200`。
- **v3 数据集缺这一批**(v3 建库先于本批),要出 v3.1:
  `build_dataset.py --runs envs/runs/full_v1 --runs envs/runs/full_v2_topup --out envs/bert_data/v3.1`
  跨模型矩阵实验以 v3.1 为准。
