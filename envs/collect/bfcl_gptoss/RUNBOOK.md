# bfcl_gptoss 补采执行手册(2026-07-30)

> 2026-08-20 gen-preset 改造:handler 的 max_tokens/effort/temperature 可由
> 环境变量 `NEW1_PRESET_JSON=<configs/presets/某份.json 的绝对路径>` 指定
> (取其 client 节的非 null 值);不设环境变量走写死缺省,行为与改造前一致。
> 现成的一份:`configs/presets/gptoss_bfcl_high.json`(= 旧写死值)。

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

正规入口是 `python3 run.py collect-bfcl <bfcl 的参数...>`——`cwd=envs/bfcl` 与
`BFCL_PROJECT_ROOT` 由注册表带上,不用自己 cd 和 export;下面两段仍写 `venv/bin/bfcl`
的原始形态,因为 `bfcl` 是 venv 里的 console script,`collect-bfcl` 就是它的注册壳,
两者跑的是同一个可执行文件(服务端两个环境变量 `LOCAL_SERVER_ENDPOINT` /
`LOCAL_SERVER_PORT` 仍要自己给)。

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
# 思考在结果条目顶层 reasoning_content 字段,形状 list[list[str]](按轮按步);
# 旧版脚本去 inference_log 里找 role=assistant 会得到空列表假阴性(2026-07-30 实测修正)
rc = e.get("reasoning_content") or []
print("思考字符数(逐轮逐步):", [[len(s) for s in turn] for turn in rc][:10])
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
python3 run.py gpu-jobs register --name bfcl_gptoss_topup \
  --piece "tokyo108:0:new1_srv_gptoss_bfcl_t108g0:/home/y-guo/reproduce/new1/envs/serve_logs/new1_srv_gptoss_bfcl_t108g0.log" \
  --piece "$(hostname):-:new1_topup_bfcl_gptoss:/home/y-guo/reproduce/new1/envs/runs/full_v2_topup/logs/bfcl_gptoss.log"
python3 run.py record start --name bfcl_gptoss_topup --track collect \
  --cmd "bfcl generate --model openai/gpt-oss-120b --test-category multi_turn_base(经 chat 端点,reasoning high)" \
  --host tokyo108 --gpu 0 --model gpt-oss-120b \
  --data envs/runs/full_v2_topup/bfcl_gptoss \
  --note "补 v1 缺口:bfcl 无 gpt-oss 轨迹,跨模型双向矩阵需要它"
```

## 5. 收尾(批次跑完)

- 完成判据:result.json 200 个 id 齐(`python3 -c` 数行数)。
- 杀服务:ssh tokyo108 tmux kill-session new1_srv_gptoss_bfcl_t108g0,nvidia-smi 确认 g0 归零。
- `python3 run.py gpu-jobs finish bfcl_gptoss_topup` +
  `python3 run.py record finish <run_id> --metric n_traj=200`。
- **v3 数据集缺这一批**(v3 建库先于本批),要出 v3.1:
  `python3 run.py build-dataset-legacy --runs envs/runs/full_v1 --runs envs/runs/full_v2_topup --out envs/bert_data/v3.1`
  (cprobe 解释器由注册表带上)
  跨模型矩阵实验以 v3.1 为准。
