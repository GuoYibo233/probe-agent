# MAP — 对照图：程序与产出文件

> **这份文件回答两个问题：仓库里每个程序是干什么的、怎么用；每份产出文件是什么设定下跑出来的什么结果。**
> 建于 2026-08-01（盘点截止 17:30 JST），由六路逐目录实测盘点汇成，每条都读过文件本体，不是凭印象写的。
> 手工维护：加了新程序、建了新数据集、run 状态变了，就更新对应行。与四本账的分工——
> `TIMELINE.md` 记为什么、`RESULTS.md` 记数字、`DATA.md` 记数据口径、`WORKPLAN.md` 记计划，本文记**东西在哪、怎么用、哪个产物对应哪个设定**。
> 词表见 `plans/PLAINWORDS.md`。⚠️ 标记 = 已知的坑，§9 汇总。

---

## 0. 一张总览

```
采集                标注               训练(四格)            评测                 注入实测
envs/collect/  →  pipeline/annotate → pipeline/train  →  pipeline/eval   →   pipeline/inject
run_*.py           build.py            train_mbert_*     eval_tool.py         replay_inject.py
(vLLM 服务上)      param_label.py      train_causal_*    eval_*_call.py       exec_calls.py
     ↓                  ↓                  ↓             summarize_matrix     sweep_theta.py
envs/runs/<批次>   pipeline/data/      pipeline/runs/    REPLAY/EXTRACT/      pipeline/inject/runs/
原始轨迹 jsonl     <版本>/<模型>/      <批次>_<模型>_<格>  CALLGEN_REPORT      + THETA_CURVE.{md,json}

记账贯穿全程：ops/record.py（数字账 runs.jsonl → RESULTS.md）+ ops/gpu_jobs.py（台账 jobs.json）
旧线（envs/bert* 三件套）已被 pipeline/ 取代，产物仍在、仍被引用，见 §5.1/§6.1。
```

---

## 1. 现役流水线程序（pipeline/）

### 1.1 采集段

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `envs/collect/common.py` | 采集器共用库：Chat 客户端（raw=completions 自拼模板切思考；chat=chat 端点读 `message.reasoning`，给 gpt-oss）+ TrajLog 落盘（每步一行 JSON，type 分 meta/gen/env/final）。服务端 5xx 按 1/2/4/8 秒退避重试 4 次 | 不能单独跑，被四个 run_*.py import |
| `envs/collect/run_appworld.py` | AppWorld 采集：模型每轮写 python 代码块调 apis.*，在持久 IPython shell 里执行 | `python run_appworld.py --base-url http://HOST:PORT/v1 --model <m> --split dev --n 0 --outdir ../runs/<批次>/appworld_<模型> --exp <名> [--shard-id i --num-shards n --resume]`，`--n 0`=整个 split |
| `envs/collect/run_tales.py` | TALES 采集：ReAct 单命令文本循环 | 同上风格，`--game cookingworld --seeds 31,32,…`，`--game-params` 覆盖难度串 |
| `envs/collect/run_alfworld.py` | ALFWorld 采集：一段思考 + 一条从候选列表逐字抄的动作；按单 game 文件 register_game 绕开 NFS 全量扫描；题单读 `envs/alfworld/splits/*.txt` | 同上风格，`--split train/val/test`（映射官方 train/valid_seen/valid_unseen），`--max-steps 50` |
| `envs/collect/run_tau2.py` | tau2-bench 采集：agent 扮客服 + LLM 用户模拟器扮客户，airline/retail 两域。**2026-08-01 新写，代码就绪、一条未采**。文件头列了 7 条与官方排行榜不可比的偏差（文本协议非原生 function call、一轮限一次调用、args_lossy 静默丢参标记等） | `envs/tau2-bench/.venv/bin/python envs/collect/run_tau2.py --base-url … --model … --domain airline --split test --n 2 --outdir … --exp …`；纯 CPU 自测 `--selftest` |
| `pipeline/collect/gen_launch.py` | 采集批次发射清单生成器：吃 manifest json，吐 `launch_servers.py`/`launch_clients.sh`/`MANIFEST.md`。只生成不执行，真发射走 gpu-run | `python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_w0.json`；试生成 `--dry-run --out-override /tmp/x/` |
| `pipeline/collect/manifest_w0.json` | w0_aw_official 批（appworld 官方分区）的清单：tokyo108 六个 vLLM 实例 + 14 客户端分片 | 被 gen_launch.py 读 |
| `pipeline/collect/manifest_c2.json` | c2_alfworld 批的清单：三实例（q36 一 + gptoss 二）+ 6 分片，每模型 474 题 | 同上 |
| `pipeline/collect/gen_alfworld_splits.py` | 生成 ALFWorld 官方分区题单（train 200 六类等比抽样 / val 140 / test 134），入库为唯一真源 | `python3 … --data-root envs/alfworld/data/json_2.1.1 --out-dir envs/alfworld/splits --n-train 200`；产 SPLIT_REPORT.json |
| `pipeline/collect/gen_bfcl_splits.py` | 生成 BFCL 题单：BFCL 无官方分区，把冻结的 v3_1 老三堆原样转成题单（140/40/20），四道门禁（无交集/并集=200/行数/不静默覆盖） | `python3 … --out-dir pipeline/splits/bfcl_mtb_v1`；⚠️ 重跑老随机规则复现不出老三堆（老脚本 rng 三环境共用），入库 txt 是唯一真源 |

⚠️ 题单落点不统一：bfcl 题单在 `pipeline/splits/bfcl_mtb_v1/`，alfworld 题单在 `envs/alfworld/splits/`，appworld 直接用官方 `envs/appworld/data/datasets/{train,dev,test_normal}.txt`（val 对应官方 dev.txt）。

### 1.2 标注段（轨迹 → 数据集，纯 CPU）

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/annotate/rules.py` | 切分规则唯一真源（常量+纯函数，逐字抄自旧线）：SEED=20260729、MAX_BOUNDS=64、MIN_THINK=40 字符、历史留 3 轮、环境返回截 400 字符、句边界=换行或 `.!?`+空白 | 只被 import，不能单独跑 |
| `pipeline/annotate/build.py` | 主构建器：轨迹切成"思考前缀→工具名"样本，一模型一环境一套；样本带 `label_call`（规范化完整调用串）与 `args_named`。unit 不在任何题单 → 退 1 | `python3 pipeline/annotate/build.py --config pipeline/configs/<env>_<model>.json` |
| `pipeline/annotate/param_label.py` | 抽取头标签：每个参数值在样本 text 里 `rfind` 定位字符区间，找不到记 found=false | `python3 … --config 同上`；产 `params/` 三堆 + PARAM_LABEL_REPORT.md + CHECK_50.md |
| `pipeline/annotate/check_callstr.py` | 后置门禁：真值调用串能否被评测侧 parse_call 原样切回 + 五道结构硬核对（模型过滤/主键唯一/题单归属等） | ⚠️ 必须 `cprobe-env/bin/python`（模块层 import torch），stage-commands 第 68 行写 python3 是错的；目前只在 bfcl 三套数据上跑过 |
| `pipeline/annotate/accept_v3diff.py` → `ACCEPT_V3DIFF.md` | G8 复现验收：新代码喂 v3 当年输入，九字段逐条与旧数据比。结论 PASS（bfcl 36343 样本、appworld 111767 样本全零差异） | `python3 pipeline/annotate/accept_v3diff.py`（无参数，路径写死） |
| `pipeline/configs/aw_{q35,q36,gptoss}.json` | appworld 标注配置：轨迹源 full_v1+full_v2_topup+w0_aw_official，split_mode=official（官方题单），产 `pipeline/data/aw_official_v1/<模型>/` | `--config` 传入 |
| `pipeline/configs/alf_{q36,gptoss}.json` | alfworld 标注配置（无 q35）：轨迹源 c2_alfworld，官方题单，产 `alf_official_v1/` | 同上 |
| `pipeline/configs/bfcl_{q35,q36,gptoss}.json` | bfcl 标注配置：轨迹源 full_v1+full_v2_topup，split_mode=frozen_v3_1，产 `bfcl_mtb_v1/` | 同上 |

### 1.3 训练段（四格；发射壳在 ops/，见 §3）

四格 = 底座 × 头。mtool/mext 用 `mbert-env`（transformers 4.57.6），ctool/cgen 用 `cprobe-env`（5.14.1），互不升级。

| 格 | 程序 | 学什么 | 关键设定与坑 |
|---|---|---|---|
| mtool | `pipeline/train/train_mbert_tool.py` | ModernBERT-base + 分类头：前缀→工具名 | `--data <数据集> --out pipeline/runs/<批>_<模型>_mtool [--smoke] [--input-mode full/no-think/no-hist]`；加权 CE（w=1/m_i），左截 4096 保思考尾巴；产 `best/`(HF 目录)+train_log.jsonl（⚠️ append，同 --out 重跑会续写） |
| mext | `pipeline/train/train_mbert_extract.py` | ModernBERT + 起止指针头 + 可答头：参数值在哪段字符 | 实例=(样本×参数)，查询串 `\n[FIND] 工具.参数` 拼在末尾；⚠️ 权重是裸 `best/model.pt`（state_dict），不是 HF 目录 |
| ctool | `pipeline/train/train_causal_tool.py` | Qwen3-0.6B-Base + 线性分类头：整段一次前向、每个句边界放监督 | `--base qwen` 必填；**开训前对齐检查是铁律**（整段 vs 逐 token 增量，maxdiff<tol，FAIL 退 2；c1/c2 统一 `--align-tol 3e-4`）；48G 卡常 OOM → `--grad-ckpt` |
| cgen | `pipeline/train/train_causal_callgen.py` | Qwen3-0.6B-Base 微调：直接续写整条调用（`\n[CALL] ` 分隔） | 底座硬编码不接受 --base；选 best 只看 val 加权 CE；48G 卡需 `--grad-ckpt`（gptoss 侧数据在 A6000 上仍可能 OOM，c1 那格迁 H200 才跑完） |
| （共用） | `pipeline/train/input_modes.py` | 消融切割器 full/no-think/no-hist 的单一真源，训练评测 import 同一份 | 肉眼核对：`python3 … --data … --env … --split test` |

### 1.4 评测段

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/eval/eval_tool.py` | 工具格回放：val 拟温度 + 20 档 θ（0.5–0.975 步长 0.025）里按风险档（0.10/0.05）选"满足精度约束下触发比例最大"的 θ，test 冻结出数 | mbert：`mbert-env/bin/python … --env <e> --run <run> --data <d>`；因果头：`cprobe-env/bin/python … --head causal`；`--cached-logits` 纯 CPU 重算（换 θ 不碰 GPU）。⚠️ logits 永远写进 `--run`，`--report-dir` 只改报告 |
| `pipeline/eval/eval_mbert_call.py` | mext 触发时刻评测：吃 mtool 的温度与 θ，触发前缀上抽参数，按无参/选择/自由三档报 | `--run <mtool run> --extractor <mext run> --risk 0.05`；⚠️ 报告写进 `--extractor`；θ 为 null 硬退 1（q35 因此无 EXTRACT_REPORT） |
| `pipeline/eval/eval_causal_call.py` | cgen 触发时刻评测：ctool 触发点上 greedy 写整条调用，判 tool_ok/参数/full_call_ok | `--ctool-run … --cgen-run … --data …`；⚠️ 报告写进 `--cgen-run` |
| `pipeline/eval/summarize_matrix.py` | 矩阵汇总：12 run 收一张表，缺报告标 PENDING | `python3 … --runs-dir pipeline/runs --out …/MATRIX_REPORT.md [--prefix c1] [--models q35 q36 gptoss] [--risk 0.05]`；⚠️ N/A 显示成 PENDING、固定读单风险档，引用必须配文字 |
| `pipeline/eval/ACCEPT_EVAL.md` + `accept_bfcl_v3{,_causal}/` | G12 复现验收：新 eval 喂旧产物，与旧报告逐字节相同。PASS | 凭证，只读 |

评测依赖顺序：先 6 个工具格（出温度与 θ）→ 后 6 个参数格。两档皆无解记 N/A，不放宽、不借用别格触发点。

### 1.5 注入段（离线注入实测 + θ 扫描）

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/inject/replay_inject.py` | 主程序，四个子命令。plan：按 θ（`--theta` 直接钉，或 `--risk` 反查）从已落盘 logits 重排触发点、cgen 产预测调用（占卡，0.6B 级）。run：对每个触发点做 nofill/inject 两条臂真实续写（要 gpt-oss 服务）。score：token 账与调用一致率（纯 CPU）。merge-exec：把执行档结果合进 plan（纯 CPU） | plan：`cprobe-env/bin/python … plan --ctool-run … --cgen-run … --data … --traj-root … --theta 0.925 --miss-policy skip --out pipeline/inject/runs/<名>`；run：`… run --plan <dir>/plan.jsonl --base-url http://tokyo108:8103/v1 --model gpt-oss-120b --arms nofill,inject --concurrency 16`；score：`… score --run-dir <dir>` |
| ↳ miss_policy 三档 | skip=猜错不注入只记账（现有全部曲线用它，偏乐观）；oracle=一律注入正确结果（机制上限）；execute=真环境执行预测调用、真实返回（含报错）注入 | ⚠️ 文件头写死：execute 量到的仍是单步调用一致率，**不是任务级成绩**，报成任务级即虚报 |
| `pipeline/inject/rebuild.py` | 从原始轨迹逐字重建 gpt-oss 的 harmony prompt（chat 端点做不到思考中途截断续写，必须 completions 自拼）。两道自检：SYSTEM 常量回源比对、逐步 token 数对账 | 纯库，被 replay_inject import。⚠️ Current date 只有与采集同日重建才对得上，assert_date 拦跨日 |
| `pipeline/inject/exec_calls.py` | execute 档执行段：每 unit 起 AppWorld 实例重放前缀→save_state→执行补引号的预测调用→load_state 回档→真代码对账。缓存键含 REQUOTE_VERSION\|unit\|step\|前缀指纹\|调用串，与 θ 无关、跨 θ 复用 | ⚠️ 只能 `envs/appworld/venv/bin/python` 跑（唯一 import appworld 的文件）；纯 CPU；`--num-shards 4 --shard-id i` 四进程并行；默认跑完即删 appworld 输出目录（`--keep-outputs` 关闭），因为 /home 配额 2026-08-01 炸过一次 |
| `pipeline/inject/launch_plan_sweep.py` | θ 扫描 plan 段发射壳：六点铺 tokyo106 六卡 | `python3 …`（全发）；`--smoke`；`--only th0925`（补发单点必须用它）；`--miss-policy execute` 时 run 目录自动加 `_exec` 后缀 |
| `pipeline/inject/sweep_theta.py` | θ 扫描驱动：run 段把一列 θ 自动排队跑 run+score（幂等，有 INJECT_REPORT 就跳过）；curve 段装配六点曲线 + 服务侧对照 + 逐指标噪声地板 | run：`cprobe-env/bin/python … run --runs <逗号列表> --services <逗号列表> --concurrency 16`；curve：`… curve --runs <同列表> --out pipeline/inject/THETA_CURVE [--control <对照目录>]`。⚠️ 口径铁律：六点只许差 θ 一个变量，同 --bs 同机器（实测 batch size 变了 greedy 生成翻 14/1061 条） |
| `pipeline/inject/check_bundle.py` | 产物加载校验：训好的权重换个进程装得起来、打得出分（非精度评测） | `--run <run> --data <d> --head mbert/causal --device cpu`；产 BUNDLE_CHECK.txt |

### 1.6 活跑注入线（2026-08-01 立项，任务级评测；设计书 `plans/2026-08-01-live-inject-design.md`）

用户裁决：回放 execute 档三步（合并缓存→续写→打分）放弃；任务级成绩改由这条线出。
评测全程不判预测对错——出手就在正身世界上"存档→执行→回档→重冻时间"拿真实返回
（报错也原样），注入 `[SYSTEM NOTE: prefetched {call} = {result}]`（无授权句），
丢弃切口后溢出、继续分段生成。θ=0.925、T=1.1923（c1_gptoss_ctool 的工作点）。

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/inject/live_appworld.py` | 驱动器：整题活跑。分段生成（每段 `--chunk-tokens` 默认 64，贪心），每个新句子级切口问探针，首过 θ 触发注入（默认每步至多 1 次），`<|end|>` 后放大段长收尾；每题落一个 `live_<task_id>.jsonl`（meta/gen/spec/env/final，final.eval 存结构化 dict）。自带 `--selftest-shadow <轨迹>`（无服务验证三连不污染正身，2026-08-01 PASS） | ⚠️ 只能 `envs/appworld/venv/bin/python` 跑（与 exec_calls.py 并列的两个 import appworld 处）；`--base-url <vLLM /v1> --probe-url <probe_server> --split test_normal --outdir … --exp …`；对照臂加 `--no-probe`；分片 `--num-shards/--shard-id`；默认跑完即删 appworld 输出目录（配额教训） |
| `pipeline/inject/probe_server.py` | 探针服务（GPU，两个 0.6B 约 3GB）：/score 前缀→置信度（softmax(logits/T) 最大值）、/gen 触发点→整条预测调用、/render messages→harmony 前缀（appworld venv 没有 transformers，渲染只能放这侧）、/health 配置回显。`selftest` 子命令拿存好的 logits_test.pt 对账活跑口径（逐前缀前向 vs 整段前向） | serve：`cprobe-env/bin/python … serve --port 8790 --device cuda:0`；selftest：`… selftest --events 2 --device cpu`（纯 CPU 可跑） |
| `pipeline/inject/score_live.py` | 打分器（纯 CPU）：活跑轨迹 + 已采对照轨迹按题配对 → `LIVE_REPORT.{json,md}`。任务成败、billed token（含丢弃溢出）、出手事后账（工具/整条一致率、重调率、执行错误种类） | `cprobe-env/bin/python … --live-dir <outdir> --base-root envs/runs/w0_aw_official/appworld_gptoss` |

已知口径差（设计书 §4，报告必带）：探针逐前缀前向 vs 训练側整段前向（分词边界效应）；
切口只查前 64 个真实切口（回放是等距抽样）；注入内容"单条调用返回" vs 六点曲线"整块
stdout"；harmony 日期行是活跑当天，与 2026-07-31 采的对照批不同。

⚠️ `.claude/skills/probe-pipeline/references/stage-commands.md` 那张命令表落后于现状：inject 段只写了 check_bundle（θ 扫描/执行档主线一个字没有）、缺 alfworld 批次命令、check_callstr 解释器写错、缺 `--input-mode` 与 `--models`。照那张表找不到 THETA_CURVE 是怎么来的，以本文为准。

---

## 2. 旧线程序（envs/，已被 pipeline/ 取代但产物仍被引用）

`envs/collect/build_dataset.py`（v2 终稿规则建库，产 bert_data v2/v3/v3_1）、`envs/bert/train_probe.py`（ModernBERT 训练）、`train_extractor.py`、`train_causal_probe.py`（因果探针，`--base qwen|lfm`，lfm=LFM2.5-350M-Base）、`eval_replay.py`（回放协议原版：calA 拟温度→calB 扫 θ→test 冻结）、`eval_replay_causal.py`、`eval_replay_mode.py`（消融包装）、`eval_extract.py`、`param_label.py`、`param_tiers.py`（三档档位表）、`make_xmodel_splits.py`（跨模型两侧物化，符号链接分身）、`input_modes.py`。新旧对应：build_dataset→annotate/build，train_probe→train_mbert_tool，eval_replay→eval_tool（G8/G12 验收证明口径逐字一致）。旧线用四堆命名 train/calA/calB/test，新线是 train/val/test（val 兼任拟温度与扫门槛）。

辅助件：`envs/loop/probe_server.py`（探针 HTTP 微服务，闭环用，POST /score 返回温度校准后的置信度，θ 判断留给客户端）；`fig1_pilot/hf_server.py`（纯 transformers 的最小 OpenAI 兼容服务，单请求串行，vLLM 起不来的机器的替补——⚠️ 与 vLLM 不逐位一致，跨批比较 token 数先查服务是不是同一套）；`envs/collect/bfcl_gptoss/`（gpt-oss 进 BFCL 的 chat 端点 handler + install_patch.py）；`envs/serve_logs/launch_vllm_*.py`（vLLM 发射脚本）。

---

## 3. 记账与发射工具（ops/ 与根目录）

| 程序/文件 | 干什么 | 怎么用 |
|---|---|---|
| `ops/record.py` | 数字账 CLI：start（发射时记，自动抓 git HEAD 与脏否）/ finish（补数字与结论）/ render（重渲染 RESULTS.md）/ list / show | `record.py start --name X --track <方向> …`；`record.py finish RUN_ID --metric k=v --conclusion …`；`record.py render` |
| `ops/gpu_jobs.py` | GPU 台账 CLI：register / finish / watch / free / status / json。卡的实时占用永远现场探测 | `gpu_jobs.py register --name N --workdir W --piece host:gpus:session:logpath …`；`gpu_jobs.py free`；⚠️ watch 对 shiga 误报 EXIT（ssh host key） |
| `ops/jobs.json` | 台账本体。现役 1 条：`c2_train`（8 piece）。⚠️ 其中 5 格实际已死（见 §5.2），台账未销号 | 只经 gpu_jobs.py 读写 |
| `ops/launch_probe.py` | 四格训练的通用 tmux 发射壳（批次/数据/环境参数化），当前入口 | `launch_probe.py smoke --batch c2 --data-root pipeline/data/alf_official_v1 --env alfworld --model q36 --host tokyo107 --gpus 0,1,2,3`；`launch_probe.py full --batch c2 … --placement ops/c2_placement.json` |
| `ops/launch_c1.py` | 上者的前身（c1 专用写死版），已被泛化版取代 | 留档 |
| `ops/c1_placement.json` / `c2_placement.json` | 排卡表：一格一行 host/gpu/extra。c1=12 格（tokyo105+106）；c2=8 格（q36→tokyo107 g0-3，gptoss→tokyo105 g4-7；cgen 带 --grad-ckpt，ctool 带 --align-tol 3e-4） | 喂 launch_probe full |
| `ops/_w2_*.sh` / `_w3_*.sh` | 07-30 夜里那两波评测的一次性串行队列脚本，已跑完成为历史 | 留档 |
| `ops/gpu_state.md` | 集群慢变量：tokyo105(=shiga) 8×A6000、106 10×A6000、107 4×RTX6000Ada、108(=saitama) 3×H100+3×H200；驱动/CUDA/六条坑（cu128 轮子在 12.2 驱动机可跑、HF 缓存在 NFS 等） | 挑卡前读 |
| `model_registry.py` | 模型地址映射，脚本一律经 resolve() 取路径 | `python model_registry.py <别名>`；⚠️ 落后于磁盘：LFM2.5-350M-Base 与 Qwen3-0.6B-Base（cgen 硬编码在用）都没注册 |
| `mbert_smoke.py` | ModernBERT 部署冒烟（fill-mask + hidden_states 23 层无 NaN） | `mbert-env/bin/python mbert_smoke.py`；⚠️ 内写路径用了下划线 `y_guo`，与全仓库连字符 `y-guo` 不一致，复用前先核 |
| `tool_probe_v{1,2,3}.py` | jlens 试点三件（2026-07-17）：工具调用信号在中间层可读表征里出现得比口头早多少；v3 对照"直接读输出 logits" | 历史试验件；产物 tool_probe_v1_out.pt / v2.log / v3.log / tool_probe_slice.html（723KB 交互页）。⚠️ 无正式结论文档 |
| `logs/` | 276 个日志。现役命名 `new1_<批>_<模型>_<格>_t<机>g<卡>.log`；07-29 之前是旧代号体系（hp8b/fig1m/w2_8b 等） | 训练进度直接 tail 本地文件（NFS 共享，不用 ssh） |

---

## 4. 数据产出对照

### 4.1 原始轨迹批次（envs/runs/，不进 git）

| 批次 | 什么设定 | 规模与成色 |
|---|---|---|
| `full_v1`（07-29） | 三环境×三模型第一批：appworld dev 57 题；tales 加难串 seed 31–50、40 步上限；bfcl 200 题×两 Qwen（无 gpt-oss） | 631 条轨迹 / 约 8789 个带思考事件 / 94MB。tales 三模型胜率全 0（40 步内无人通关，作训练数据合格） |
| `full_v2_topup`（07-30） | 补缺口：appworld train 90 题与 tales seed 51–80（q36+gptoss 跑）；另补 bfcl 的 gpt-oss 200 条（chat 端点 handler） | 240 条 jsonl + 1 份 bfcl result.json / 78MB。⚠️ gpt-oss 思考在顶层 `reasoning_content` 字段（list[list[str]]），去 inference_log 找会假阴性 |
| `w0_aw_official`（07-31） | appworld 官方分区第 0 波：q35 补 train 90 + 三模型各 test_normal 168 | 594 个 jsonl 全 final 收尾 / 56MB（run `20260731_0607_w0_aw_official`） |
| `c2_alfworld`（07-31） | ALFWorld 官方分区：q36+gptoss 各 474 题（train200/val140/test134），50 步上限 | 948 个 jsonl / 94MB；胜率 q36 0.909 / gptoss 0.762；动作按 13 条模板切，99.95% 切得动（run `c2_alfworld`） |
| `full_tales_L1` / `L2` | TALES 难度探索批（seed 101–120，L1 六房 60 步 / L2 十一房 80 步） | 各 60 条。⚠️ **一条也没进任何数据集**，别和训练数据那批混（DATA.md §8.2 的教训） |
| 其余小批 | calib_*/smoke_*/pipecheck*/probe_v0/bfcl 早期评分目录/shardtest 等 | 校准与冒烟遗迹，非正式数据源 |

### 4.2 数据集

**旧血脉 `envs/bert_data/`**（一环境一数据集，四堆 70/10/10/10，自切分）：

| 版本 | 设定 | 关键数 |
|---|---|---|
| v1 | 三环境合训一词表、按轨迹切三路——**规则不同，弃用，数字与后代不可比** | 193 类 / 25005 样本 |
| v2 | 终稿规则首落地，源=full_v1 | appworld 2772 事件先验 0.226；tales 2039/0.672；bfcl 2265/0.038 |
| v3 | 加 full_v2_topup 重建；⚠️ bfcl 建库早于 gpt-oss 批落地，故与 v2 相同 | appworld 5552 事件先验 0.298；tales 3907/0.556；bfcl 2265/0.049 |
| v3_1 | 只补 bfcl 的 gpt-oss；appworld/tales 与 v3 逐字节同（md5 核过） | bfcl 595 轨迹/3325 事件/0.042；⚠️ BUILD_REPORT 标题都写"v2 出厂报告"（文案 bug，认目录名） |
| v3_params / v3_1_params | 参数区间标注派生 | 定位率 appworld 0.833/tales 0.807/bfcl 0.917；⚠️ v3_params 的 bfcl 重抽多 217 事件（时点不同步，v3_1_params 已清零） |
| v3_xmodel / v3_1_xmodel | 按 model 字段切两侧 + 考侧×校准侧目录（符号链接） | 训练侧事件 qwen/gptoss：tales 1425/1235，appworld 2434/1211，bfcl 1605/748 |

**新血脉 `pipeline/data/`**（一模型一数据集，官方/冻结题单，train/val/test；与旧血脉数字互不可比）：

| 数据集 | 切分 | 每模型规模（轨迹/事件/样本/词表/先验基线） |
|---|---|---|
| `aw_official_v1/{q35,q36,gptoss}` | appworld 官方题单 train90/val57/test168 实例，三模型同题 | q35 315/6340/70440/143 类/0.174；q36 315/5738/52104/151/0.159；gptoss 315/3952/166103/85/**0.404**。⚠️ gptoss 边界数中位 51（上限 64 就在旁边），按样本数横比三模型会反直觉，比事件数 |
| `alf_official_v1/{q36,gptoss}` | ALFWorld 官方题单 train200/val140/test134 | q36 474/8947/149273/12 类/**0.548 猜 go**；gptoss 474/12883/633392/12/0.470。工具格必须显著超过先验才算学到 |
| `bfcl_mtb_v1/{q35,q36,gptoss}` | 冻结 v3_1 老三堆（140/40/20 题） | q35 200/1209/11094/94 类/0.058；q36 196/1056/25249/0.066（⚠️ test 实到 19/题单 20，差 1 待查）；gptoss 199/1060/32163/0.037。真值调用串回读天花板 0.97 上下（CALLSTR_CHECK.md） |

### 4.3 C3 侧数据（benchmark_design/，与探针线无关）

`l3_2wiki_items.jsonl`（两跳拼接 4244 条）、`l4_2wiki_pairs.jsonl`（极性翻转 6494 对）、`l4_alfworld_pairs*.jsonl`（位置改换 10/259 对，真引擎回放"照抄必败"才收录）；生成脚本 `gen_l3_2wiki.py`/`gen_l4_2wiki.py`/`gen_l4_alfworld.py`，种子 20260729，同参两跑 md5 一致；`--sim-filter` 接口留好未接（等 bge-large-en-v1.5）。⚠️ 相似度档两套编号取值颠倒：代码 L0/L1/L2 = 正典 L2/L2⁻/L1，转换 `benchmark_design/metrics.py --legacy-levels`。

---

## 5. 训练产出对照

### 5.1 旧线 `envs/bert_runs/`（ModernBERT/因果探针，自切分场地）

| 目录 | 什么设定 | 状态/关键数 |
|---|---|---|
| `{tales,appworld,bfcl}_v2` | bf16 硬训（浮点缺陷） | **作废，不得引用**（TIMELINE 07-29） |
| `{…}_v2fix` | fp32+autocast 修复版，数据 v2 | bfcl 达标（θ0.925 精度 0.966/触发 0.620）；appworld 边缘；tales 不达标 |
| `{…}_v3` | 数据翻倍版，终审 | bfcl 达标（0.9925/0.5929）；appworld、tales 不达标。含 logits_*.pt 可纯 CPU 重算 |
| `{…}_v3_nothink` / `_nohist` | 砍思考/砍历史消融 | appworld_nohist 达标 0.954/0.22；⚠️ nothink 的触发比例口径与完整输入不可比 |
| `{…}_ext_v3` | 抽取头 | bfcl：触发 134 事件、完整调用 0.9179；⚠️ 严格列不可用（BPE 边界，报告自曝） |
| `{…}_v3_causal_qwen` / `_causal_lfm`（+`tales_…_qwen8k`） | 因果探针两底座；开训前 ALIGN_CHECK | appworld qwen 底座 0.9621/0.3338 开门；成本比 bfcl 19.8/appworld 26.4/tales 34.1；8k 窗对照=噪声级 |
| `{…}_v3_xqwen` / `_xgptoss` + `xmodel/` 24 目录 | 跨模型两侧训练 + 主场/冷迁移/只换校准/混训评测（符号链接分身防覆盖） | 部署结论：bfcl 只换校准可救（0.971），appworld/tales 须重训 |
| `bfcl_v3_1_mixed` | 混训（v3_1 两侧合训） | 训练完成 calA 0.7847；天花板评测数字在 run `20260730_1835` |

### 5.2 新线 `pipeline/runs/`（官方分区场地）

**c1 批（appworld，12 格，07-31 全收官）**——每格对应 runs.jsonl 里同名 run_id：

| 格 | q35 | q36 | gptoss |
|---|---|---|---|
| mtool | 两档 θ 皆 null，无工作点 | 双档有解 0.1724/0.9208 | 0.05 null；0.10 档 test 0.8642<0.90 **契约未兑现** |
| mext | 评测 N/A（上游无触发点） | 0.05 档 full_call_ok 0.9324 | 0.10 档 0.6755（上游弱+带参多，别与 q36 直比） |
| ctool | 双档有解 0.1642/0.9292 | 0.10 档 0.2911/0.9368 | **双档有解 0.4963/0.9057**（十二格覆盖之王） |
| cgen | 0.05 档 exact_call 0.8858 | 0.10 档 0.8103 | 0.05 档 0.7852；⚠️ 迁卡跑的（A6000 OOM→H200），残局在 `_aborted_c1_gptoss_cgen_t106g3` |

**c2 批（alfworld，8 格，08-01 04:44 发射）——截至 08-01 17:30 的真实状态，⚠️ 台账与 RESULTS 仍全记 running**：

| 格 | 状态 | 细节 |
|---|---|---|
| c2_q36_mtool | ✅ 训练完，未评测 | best calA 加权 acc 0.972（ep2） |
| c2_q36_cgen | ✅ 训练完，未评测 | best val CE 0.041，val_exact_call 0.895 |
| c2_q36_ctool | ❌ CUDA OOM | 对齐 PASS 后第一步反传就 OOM，零产出；需 --grad-ckpt 或换卡重发 |
| c2_q36_mext | ❌ 存权重写崩 | torch.save 抛 iostream error；⚠️ 留下的 best/model.pt 只有健康权重的 1/14，大概率写坏，复用前必须先验证能 load |
| c2_gptoss_mtool | ❌ 磁盘配额超限 | 日志 flush 报 Disk quota exceeded，第一次 eval 都没到 |
| c2_gptoss_mext | ❌ 疑同因死 | 日志 07:23 写半行中断，与配额崩溃时间窗重叠 |
| c2_gptoss_ctool | ❌ CUDA OOM | 同 q36_ctool |
| c2_gptoss_cgen | 🟡 在跑 | 17:28 仍在写日志，ep0 第 3750/25245 步（约 15%），2.62 步/秒 |

---

## 6. 注入产出（pipeline/inject/）

| 产物 | 什么设定 | 结果要点 |
|---|---|---|
| `runs/smoke_gptoss_r10` | 8 事件冒烟 | 流程验证 |
| `runs/aw_gptoss_r10` | 单点全量：θ=0.925（risk0.1 反查）、skip 档、共享服务 concurrency 4 | run `20260801_0113`：注入推进率 0.62 vs 不注入 0.10；前 20% 注入省 377.7 tok、后 40% 亏 636–697；21.8% 触发落最差区间——死区第三次复现 |
| `runs/aw_gptoss_th050…th095` 六点 | θ 曲线主体：六点只差 --theta，skip 档，专用服务 concurrency 16 | runs `20260801_0407/0413_*` 六条；覆盖 0.9097→0.4242，调用一致率 0.3445→0.6902，省 token 中位 −40～0 |
| `runs/aw_gptoss_th{0875,0925,095}_h100` | 服务侧对照：同 θ 同 plan 只换服务 | ⚠️ **runs.jsonl 里没有记录**，只能从目录与 THETA_CURVE 读；最大差 0.1528 定为求和型指标噪声地板 |
| `THETA_CURVE.{md,json}` | 六点曲线主报（sweep_theta curve 产） | 逐指标可读性判定：省 token 比例（求和）噪声 0.1528>跨度 0.1075 **不可画**；省 token 中位 5.7× 可；调用一致率噪声 0 可；失控率两项不可。⚠️ 主表里 −0.10299 那列报告自己已声明不可读，引用别踩 |
| `exec_cache/`（⚠️ git 未跟踪未 ignore） | execute 档执行缓存：θ=0.925 那批 1061 个触发事件的真环境执行结果，四分片，缓存键与 θ 无关 | 执行段 08-01 08:52 四分片全绿（s0：exec_ok 246/err 14/drift 1）。**2026-08-01 用户裁决：合并→续写→打分三步放弃**，任务级成绩改由活跑注入线（§1.6）出；缓存留档不动，execute 档永久停在"零最终数字" |

---

## 7. 旧方向目录（C1/C3 与更早）

| 目录 | 回答什么 | 程序与关键产物 |
|---|---|---|
| `oracle_inject/` | C1 起点判决实验：正确结果在思考不同位置注入值多少 | oracle_v1.py（偏移 d 网格+错注+无授权消融）/ v2_variance（5 种子误差棒）/ v3_2hop；FINDINGS.md：开场注入省 81–91%、死区提前 25–50tok、错注 acc 崩 0.02–0.14。⚠️ results/*.log 实为 JSON Lines |
| `hotpot_inject/` | 死区在真实多跳问答复现 + comparison/bridge 分型 | hotpot_v1.py（`--model … --types comparison,bridge --hop1-offsets …`）；FINDINGS.md 三波；T11 方差批=run `20260730_0413`（1338 条、3 种子） |
| `closed_loop/` | 置信度开火 vs 固定时机（v0）+ 记忆攒厚后开火塌到 t=0 | loop_v0.py / flagship_v0.py（硬编码常量，无 CLI）；RESULTS_v0.md：p>0.99 省 token 87→4、lead≤32 平均 −6.4；FLAGSHIP_v0.md：错误流 t=0 开火率 50% |
| `traj_pipeline/` | 隐藏态里有没有信号（头①③④先导） | collect/labeler/train_probe_v0v1/param_head/timing_head；PILOT_NOTES.md：头① AUROC 0.981(4B)/0.899(8B 混合)；头③候选池覆盖 33.8% 是瓶颈；头④ Spearman 0.454 未超 lead 基线 |
| `fig1_pilot/` | C3 先导：存解法/不存解法/全历史三条臂 ALFWorld 矩阵 | fig1_run.py + hf_server.py + alfworld_data；results/*.jsonl（8bfull_* 与 fullhist_*）；ANALYSIS_8bfull.md。⚠️ 文件名用代码那套 L 编号 |
| `benchmark_design/` | C3 协议本体：指标、上限、L3/L4 生成、六被试 | metrics.py（Speedup@k/CTC/NTI+五条防幸存者断言，`--legacy-levels`）/ oracle_ceiling.py / evomem_driver.py / gen_l3/l4_*；GEN_REPORT.md、ORACLE_CEILING_8bfull.md（+21.0% 只在完全重复档）、FIDELITY_T12C.md（被试保真度：DC 两个失真需声明、AWM 建议不报） |
| `tracelab_analysis/` | 相似任务在真实负载占比 | similarity_v0.py（无参数纯 CPU）；RESULTS_v0.md：相邻会话相似度 p50 0.93、>0.8 占 68.4%、跨 project 假相似 10.8% |
| `jacobian-lens/` | Anthropic J-lens 参考实现（第三方） | 配根目录 tool_probe_v1-3 使用，见 §3 |
| `related_work/` | 七个竞品仓库 clone + 四份调研判决书 | DEPLOYED.md（均只装依赖未试跑，除 jlens）；SURVEY_VERDICTS、evo_mem_INTEGRATION（官方 Evaluator 跑不通，只借 agent/memory 模块自写 driver） |
| `paper/`、`paper_notes/`、`paper_draft/` | 论文区 | paper/speculator/main.tex 已编译（协议节 4 页）；六篇竞品笔记；本次新增 `paper_draft/PAPER_DRAFT_20260801.md`（实验现状论文体草稿）。⚠️ sec_benchmark_protocol.md 是 C3 协议的英文行文版，数字要回原始报告核对，别重复计入 |
| `deploy_notes/` | ModernBERT 部署侦察 | modernbert.md + 根目录 mbert_smoke.py |

---

## 8. 环境与权重

**训练三环境（uv 建，⚠️ 均未装 pip，版本读自 dist-info）：**

| 环境 | Python / transformers / torch | 管什么 |
|---|---|---|
| `mbert-env` | 3.11.15 / **4.57.6（钉死）** / 2.11.0+cu128 | mtool、mext 训练与评测 |
| `cprobe-env` | 3.11.15 / **5.14.1（≥5.14 线）** / 2.11.0+cu128 | ctool、cgen 训练与评测（`--head causal` 的 eval 也必须它，import 链带 torch）；两环境互不升级 |
| `jlens-env` | 3.12.13 / 5.14.1 / 2.9.1+cu128 | jlens 本体 + 被复用跑 hotpot_inject 与 L3/L4 生成（只因要新 transformers） |

**基准环境（envs/ 下）：** `appworld`（pip 包 0.1.3.post1）、`alfworld`（0.4.2，data 软链 fig1_pilot/alfworld_data）、`bfcl`（bfcl_eval 2026.3.23；⚠️ 自带独立 cu13 系 torch 2.13.0）、`tales`（tale_suite 1.0.0rc2，捆带 alfworld/scienceworld 等）、`tau2-bench`（唯一真源码 clone，.venv 装 tau2 1.0.1）、`vllm-env`（vllm 0.26.0 服务环境）、`cuda-compat-13.0`（驱动 580 兼容库，推断给 cu13 轮子用，未证实）。

**权重（`/net/tokyo100-10g/data/str01_01/y-guo/models/`）：** gpt-oss-120b 122G（含 original/ 65G 参考格式，vLLM 用不到）、ModernBERT-base 3.0G（含 onnx/ 1.5G 用不到）、Qwen3-0.6B-Base 1.2G、LFM2.5-350M-Base 681M。⚠️ 后两个未进 model_registry。两个 27B Qwen 在 zhou-y 共享盘（registry 有条目）；Qwen3-8B 等走 HF 缓存（`HF_HOME=/net/…/y-guo/hf`）。

---

## 9. 坑与悬空状态总表（2026-08-01）

1. **c2 八格：5 死 1 跑 2 完未评**（§5.2），台账 `c2_train` 未销号、RESULTS 八条全挂 running。死因三类：ctool 双格 OOM（缺 --grad-ckpt 或卡太小）、磁盘配额两格、疑似配额一格。q36_mext 留下的权重疑似写坏。
2. **磁盘配额**：/home 用户配额 08-01 炸过两次（训练存权重、appworld 输出目录）。exec_calls 已默认删中间目录自保；训练侧无对策，重发前先清配额。
3. **execute 档已弃**（2026-08-01 用户裁决）：执行缓存全齐但 merge/score 不再做；任务级成绩改由活跑注入线（§1.6，programs 已写、待冒烟）出。
4. **θ 曲线求和口径不可读**：噪声地板 0.1528 > 跨度 0.1075；可读的是调用一致率与省 token 中位。三个 _h100 对照目录未进 runs.jsonl。
5. **stage-commands.md 落后**：inject 主线缺失、alfworld 批次缺失、check_callstr 解释器写错（§1.5 尾注）。probe-pipeline skill 按 Phase E 规矩欠一次回写。
6. **exec_cache/ 未跟踪未 ignore**；`pipeline/eval/accept_*` 两目录入库与否"未定"。
7. **两套 L 编号取值颠倒**（§4.3）；引用带 L 数字先对表。
8. **跨批 token 不可直比**：hf_server 与 vLLM 两套服务、不同 --bs、不同并发都会抖；同一条曲线必须同服务同 --bs 同机。
9. **bfcl 悬案三件**：q36 反低于 q35 疑聊天模板（未查）；v3_params 重抽多 217 事件（v3_1 已消）；bfcl_mtb_v1/q36 test 实到 19/题单 20（待查）。
10. **registry/路径小雷**：model_registry 缺两条新权重；mbert_smoke.py 路径 `y_guo` 下划线疑笔误。
11. **发射时工作树常年脏**：多数 run 的 commit 追不回真实代码；"发射前 commit"铁律执行率为零，可复现性靠种子+验收线兜底。
12. **TIMELINE 欠两条人写条目**：execute 档口径更正（给不出任务级成绩）、评测主报换曲线。
