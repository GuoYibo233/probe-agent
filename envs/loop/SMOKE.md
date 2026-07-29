# T9 闭环管线 smoke/demo 执行手册(B 线备好,发射权在 A 线)

两张卡、三步走,每步幂等。全部走 gpu-run 流程(探卡→smoke→commit→tmux→登记)。
B 线代码已自测:句界检测 170 条真实思考零失配;monitor 触发语义单测过;
bfcl venv 导入/测例装载/handler 构造过。

## 前置:两个服务

① vLLM 起 qwen3.5-27b(1 张 H100/H200;**不设 --served-model-name**,
模型 id=权重路径,与 bfcl_q35 采集批次约定一致):

```bash
envs/vllm-env/bin/vllm serve \
  /net/tokyo100-10g/data/str01_01/zhou-y/models/Qwen3.5-27B \
  --port 8107 --host 0.0.0.0
# 就绪:curl -s http://<host>:8107/v1/models | grep Qwen3.5
```

② 探针服务(1 张卡,几 GB 显存即可,mbert-env):

```bash
cd /home/y-guo/reproduce/new1
CUDA_VISIBLE_DEVICES=<g> mbert-env/bin/python envs/loop/probe_server.py \
  --run envs/bert_runs/bfcl_v3 --port 8201
# 就绪:curl -s http://<host>:8201/health   → {"ok": true, "T": 1.5218, ...}
```

## 第一步:干闭环对账(只用探针服务,不用 vLLM;纯 CPU 客户端)

```bash
cd /home/y-guo/reproduce/new1
# 先 30 事件试跑(测延迟与联通)
python3 envs/loop/smoke_dry.py --server http://<host>:8201 \
  --run envs/bert_runs/bfcl_v3 --data envs/bert_data/v3/bfcl --limit 30
# 全量(与 REPLAY_REPORT 一致性判定,约几千次请求)
python3 envs/loop/smoke_dry.py --server http://<host>:8201 \
  --run envs/bert_runs/bfcl_v3 --data envs/bert_data/v3/bfcl
```

**判据**:末行 `PASS: 与离线回放一致`;附带 probe_ms p50/p90(预期几十 ms)。
FAIL → 停,回报 B 线(温度/label_map/截断有诈,别继续)。

## 第二步:单任务四口径 demo(T9 验收演示)

```bash
cd /home/y-guo/reproduce/new1/envs/bfcl
LOCAL_SERVER_ENDPOINT=<vllm主机> LOCAL_SERVER_PORT=8107 \
venv/bin/python ../loop/run_bfcl_demo.py --entry multi_turn_base_0 \
  --modes baseline,shadow,truncate,fork \
  --probe-url http://<探针主机>:8201 --out ../loop/runs/demo1
```

**判据**(T9 验收原文对照):
- 四口径各产一份 `runs/demo1/multi_turn_base_0_<mode>.jsonl` 账本
  + `_result.json`;fork 口径额外产 `_fork1.jsonl` 分支账本;
- 汇总表能看到:触发位置(步/句界/字符)、预测工具、截断口径的合成调用、
  影子口径的 agent 实际调用与命中核对、fork 主线 vs 分支的 token 差;
- 探针开销单独成列(probe_ms 总和 + probe_server.jsonl 逐请求日志)。

已知限:参数产线是占位(`[tool()]` 零参数,T7 抽取头就位后替换),截断/fork
分支的环境执行大概率报参数错——**这不挡验收**,demo 验证的是机械流程
(触发→断流→注入→fork→记账),调用正确率归 T10 正式跑分管。

## 第三步:复跑验证(可复现性)

同命令再跑一遍 `--out ../loop/runs/demo2`,对比两次触发位置与 token 账
(temperature=0.001,应基本一致;vLLM 数值抖动允许小差)。

## 收尾

- 服务杀净、显存归零;demo 属工程验证,不进 runs.jsonl 正式记录,
  但发射/销号照走台账。
- 结果回报 B 线(或贴 runs/demo1 汇总输出),B 线据此修管线。
