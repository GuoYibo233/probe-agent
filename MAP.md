# MAP — 代码地图：每个程序是干什么的、怎么用

> 建于 2026-08-01 的全量盘点，2026-08-02 清场后缩编：产物对照部分（旧数据集 /
> 训练 run / 注入曲线 / 旧方向目录）全部删除，历史见 git 快照 commit `b1f5b9c`。
> 本文只回答：仓库里每个程序是干什么的、怎么用。手工维护：加了新程序就更新对应行。
> 四本账的分工——`TIMELINE.md` 记为什么、`RESULTS.md` 记数字、`DATA.md` 记数据口径、
> `WORKPLAN.md` 记计划。⚠️ 标记 = 已知的坑，§4 汇总。

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
2026-08-02 清场后所有产出目录为空，上面一行是"产物落在哪"的约定，不是现状。
```

---

## 1. 流水线程序（pipeline/ 与 envs/collect/）

### 1.1 采集段

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `envs/collect/common.py` | 采集器共用库：Chat 客户端（raw=completions 自拼模板切思考；chat=chat 端点读 `message.reasoning`，给 gpt-oss）+ TrajLog 落盘（每步一行 JSON，type 分 meta/gen/env/final）。服务端 5xx 按 1/2/4/8 秒退避重试 4 次 | 不能单独跑，被四个 run_*.py import |
| `envs/collect/run_appworld.py` | AppWorld 采集：模型每轮写 python 代码块调 apis.*，在持久 IPython shell 里执行。`--api chat` 就是 chat baseline（不传 `--reasoning-effort` 按 high）；单题异常按题兜底，final 记 `abort` | `python3 run.py collect-aw --base-url http://HOST:PORT/v1 --model <m> --split dev --n 0 --outdir envs/runs/<批次>/appworld_<模型> --exp <名> [--shard-id i --num-shards n --resume]`，`--n 0`=整个 split；相对 `--outdir` 按仓库根解析 |
| `envs/collect/run_tales.py` | TALES 采集：ReAct 单命令文本循环 | 同上风格，`--game cookingworld --seeds 31,32,…`，`--game-params` 覆盖难度串 |
| `envs/collect/run_alfworld.py` | ALFWorld 采集：一段思考 + 一条从候选列表逐字抄的动作；按单 game 文件 register_game 绕开 NFS 全量扫描；题单读 `envs/alfworld/splits/*.txt` | 同上风格，`--split train/val/test`（映射官方 train/valid_seen/valid_unseen），`--max-steps 50` |
| `envs/collect/run_tau2.py` | tau2-bench 采集：agent 扮客服 + LLM 用户模拟器扮客户，airline/retail 两域。文件头列了 7 条与官方排行榜不可比的偏差（文本协议非原生 function call、一轮限一次调用、args_lossy 静默丢参标记等） | `python3 run.py collect-tau2 --base-url … --model … --domain airline --split test --n 2 --outdir … --exp …`（解释器 `envs/tau2-bench/.venv` 由注册表带上）；纯 CPU 自测 `python3 run.py collect-tau2 --selftest` |
| `envs/collect/build_dataset.py` | 旧线建库脚本（v2 终稿规则，轨迹→四堆数据集），已被 `pipeline/annotate/` 取代，注册表仍挂着 | 历史入口，新活别用 |
| `pipeline/collect/gen_launch.py` | 采集批次发射清单生成器：吃 manifest json，吐 `launch_servers.py`/`launch_clients.sh`/`MANIFEST.md`。只生成不执行，真发射走 gpu-run | `python3 run.py gen-launch --config pipeline/collect/manifest_w0.json`；试生成 `python3 run.py gen-launch --config … --dry-run --out-override /tmp/x/` |
| `pipeline/collect/manifest_*.json` | 采集批次清单样例（服务器摆位 + 客户端分片），旧批次的两份留作模板 | 被 gen_launch.py 读 |
| `pipeline/collect/gen_alfworld_splits.py` | 生成 ALFWorld 官方分区题单（train 六类等比抽样 / val / test），入库为唯一真源 | `python3 run.py gen-alf-splits --data-root envs/alfworld/data/json_2.1.1 --out-dir envs/alfworld/splits --n-train 200`；产 SPLIT_REPORT.json；⚠️ 无防覆盖门禁，重跑直接改写已入库题单 |
| `pipeline/collect/gen_bfcl_splits.py` | 生成 BFCL 题单：把冻结的 v3_1 老三堆原样转成题单，四道门禁（无交集/并集/行数/不静默覆盖） | `python3 run.py gen-bfcl-splits --out-dir pipeline/splits/bfcl_mtb_v1`；⚠️ 老三堆 txt 随 2026-08-02 清场删除且老随机规则复现不出来，要用得从 git 快照 `b1f5b9c` 找回 |
| `pipeline/collect/gen_tau2_splits.py` `gen_toolhop_splits.py` | 其余环境的题单生成器 | `python3 run.py show <task>` 看注册表口径 |

### 1.2 标注段（轨迹 → 数据集，纯 CPU）

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/annotate/rules.py` | 切分规则唯一真源（常量+纯函数）：SEED=20260729、MAX_BOUNDS=64、MIN_THINK=40 字符、历史留 3 轮、环境返回截 400 字符、句边界=换行或 `.!?`+空白 | 只被 import，不能单独跑 |
| `pipeline/annotate/build.py` | 主构建器：轨迹切成"思考前缀→工具名"样本，一模型一环境一套；样本带 `label_call`（规范化完整调用串）与 `args_named`。unit 不在任何题单 → 退 1 | `python3 run.py ann-build --config pipeline/configs/<env>_<model>.json` |
| `pipeline/annotate/param_label.py` | 抽取头标签：每个参数值在样本 text 里 `rfind` 定位字符区间，找不到记 found=false | `python3 run.py ann-params --config 同上`；产 `params/` 三堆 + PARAM_LABEL_REPORT.md + CHECK_50.md |
| `pipeline/annotate/check_callstr.py` | 后置门禁：真值调用串能否被评测侧 parse_call 原样切回 + 五道结构硬核对（模型过滤/主键唯一/题单归属等） | `python3 run.py ann-check-callstr --config 同上`；⚠️ 它模块层 import torch，必须 `cprobe-env` 解释器，且要清空 `CUDA_VISIBLE_DEVICES`——两件事注册表都替你办了 |
| `pipeline/annotate/accept_v3diff.py` | G8 复现验收器：新代码喂旧输入，九字段逐条与旧数据比 | `python3 run.py ann-accept-v3diff`（无参数，路径写死；⚠️ 写死的旧数据已随清场删除，此验收只对旧阶段有意义） |
| `pipeline/configs/*.json` | 标注配置（环境×模型一份：轨迹源、题单模式、落点） | `--config` 传入；新批次照抄一份改字段 |

### 1.3 训练段（四格；发射壳在 ops/，见 §3）

四格 = 底座 × 头。mtool/mext 用 `mbert-env`（transformers 4.57.6），ctool/cgen 用 `cprobe-env`（5.14.1），互不升级。

| 格 | 程序 | 学什么 | 关键设定与坑 |
|---|---|---|---|
| mtool | `pipeline/train/train_mbert_tool.py` | ModernBERT-base + 分类头：前缀→工具名 | `--data <数据集> --out pipeline/runs/<批>_<模型>_mtool [--smoke] [--input-mode full/no-think/no-hist]`；加权 CE（w=1/m_i），左截 4096 保思考尾巴；产 `best/`(HF 目录)+train_log.jsonl（⚠️ append，同 --out 重跑会续写）；⚠️ **同 out 二次训练默认拒绝**——`--out` 下已有 `train_log.jsonl` 就 SystemExit 不开训，`--force` 是唯一逃生口，四格同此语义 |
| mext | `pipeline/train/train_mbert_extract.py` | ModernBERT + 起止指针头 + 可答头：参数值在哪段字符 | 实例=(样本×参数)，查询串 `\n[FIND] 工具.参数` 拼在末尾；⚠️ 权重是裸 `best/model.pt`（state_dict），不是 HF 目录 |
| ctool | `pipeline/train/train_causal_tool.py` | Qwen3-0.6B-Base + 线性分类头：整段一次前向、每个句边界放监督 | `--base qwen` 必填；**开训前对齐检查是铁律**（整段 vs 逐 token 增量，maxdiff<tol，FAIL 退 2；参考值 `--align-tol 3e-4`）；48G 卡常 OOM → `--grad-ckpt` |
| cgen | `pipeline/train/train_causal_callgen.py` | Qwen3-0.6B-Base 微调：直接续写整条调用（`\n[CALL] ` 分隔） | 底座硬编码不接受 --base；选 best 只看 val 加权 CE；48G 卡需 `--grad-ckpt`（大数据侧仍可能 OOM，旧阶段迁 H200 才跑完过） |
| （共用） | `pipeline/train/input_modes.py` | 消融切割器 full/no-think/no-hist 的单一真源，训练评测 import 同一份 | 肉眼核对：`python3 … --data … --env … --split test` |

### 1.4 评测段

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/eval/eval_tool.py` | 工具格回放：val 拟温度 + 20 档 θ（0.5–0.975 步长 0.025）里按风险档（0.10/0.05）选"满足精度约束下触发比例最大"的 θ，test 冻结出数 | mbert 头：`python3 run.py eval-tool-mbert --env <e> --run <run> --data <d>`；因果头：`python3 run.py eval-tool-causal …`（`--head` 与解释器都由注册表钉死）。两条都是发射类，run.py 只出命令、发射走 gpu-run；`--cached-logits` 纯 CPU 重算（换 θ 不碰 GPU）。⚠️ logits 永远写进 `--run`，`--report-dir` 只改报告 |
| `pipeline/eval/eval_mbert_call.py` | mext 触发时刻评测：吃 mtool 的温度与 θ，触发前缀上抽参数，按无参/选择/自由三档报 | `python3 run.py eval-mcall --env <e> --run <mtool run> --extractor <mext run> --data <d> --risk 0.05`（发射类）；⚠️ 报告写进 `--extractor`；θ 为 null 硬退 1 |
| `pipeline/eval/eval_causal_call.py` | cgen 触发时刻评测：ctool 触发点上 greedy 写整条调用，判 tool_ok/参数/full_call_ok | `python3 run.py eval-ccall --env <e> --ctool-run … --cgen-run … --data …`（发射类）；⚠️ 报告写进 `--cgen-run` |
| `pipeline/eval/summarize_matrix.py` | 矩阵汇总：多 run 收一张表，缺报告标 PENDING | `python3 run.py matrix --runs-dir pipeline/runs --out …/MATRIX_REPORT.md [--prefix …] [--models …] [--risk 0.05]`；⚠️ N/A 显示成 PENDING、固定读单风险档，引用必须配文字 |

评测依赖顺序：先工具格（出温度与 θ）→ 后参数格。两档皆无解记 N/A，不放宽、不借用别格触发点。

### 1.5 注入段（离线注入实测 + θ 扫描）

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/inject/replay_inject.py` | 主程序，四个子命令。plan：按 θ（`--theta` 直接钉，或 `--risk` 反查）从已落盘 logits 重排触发点、cgen 产预测调用（占卡，0.6B 级）。run：对每个触发点做 nofill/inject 两条臂真实续写（要大模型服务）。score：token 账与调用一致率（纯 CPU）。merge-exec：把执行档结果合进 plan（纯 CPU） | 一条子命令一个任务名：`python3 run.py inject-plan / inject-run / inject-score / inject-merge-exec …`（plan/run 发射类走 gpu-run，score/merge 纯 CPU 直跑）；参数细节 `python3 run.py show <task>` |
| ↳ miss_policy 三档 | skip=猜错不注入只记账（偏乐观）；oracle=一律注入正确结果（机制上限）；execute=真环境执行预测调用、真实返回（含报错）注入 | ⚠️ 文件头写死：execute 量到的仍是单步调用一致率，**不是任务级成绩**，报成任务级即虚报 |
| `pipeline/inject/rebuild.py` | 从原始轨迹逐字重建 gpt-oss 的 harmony prompt（chat 端点做不到思考中途截断续写，必须 completions 自拼）。两道自检：SYSTEM 常量回源比对、逐步 token 数对账。`build_prefix`（jinja 文本路）2026-08-18 起只供离线回放线；活跑改用下一行 |
| `pipeline/inject/harmony_render.py` | 照抄 vLLM chat 端点的三步渲染，把 messages 直接渲染成 harmony prompt **token id**（只依赖 openai_harmony）；`/render` 用它。修的是 jinja 文本路两处与 chat 不齐（空 content 轮、字面 `<\|...\|>` 标记）| 库；裁判测试 `envs/vllm-env/bin/python -m unittest tests.test_harmony_render`（用 vLLM 自己的函数当裁判，别的解释器 skip） | 纯库，被 replay_inject import。⚠️ Current date 只有与采集同日重建才对得上，assert_date 拦跨日 |
| `pipeline/inject/exec_calls.py` | execute 档执行段：每 unit 起 AppWorld 实例重放前缀→save_state→执行补引号的预测调用→load_state 回档→真代码对账。缓存键含 REQUOTE_VERSION\|unit\|step\|前缀指纹\|调用串，与 θ 无关、跨 θ 复用 | `python3 run.py exec-calls --plan … --out … --cache … --exp …`（appworld venv 由注册表带上，纯 CPU 直跑）；⚠️ 只能 `envs/appworld/venv/bin/python` 跑；`--num-shards 4 --shard-id i` 并行；默认跑完即删 appworld 输出目录（`--keep-outputs` 关闭），/home 配额炸过 |
| `pipeline/inject/launch_plan_sweep.py` | θ 扫描 plan 段发射壳：多点铺多卡 | `python3 run.py launch-plan-sweep`（发射类）；`--smoke`；`--only <点名>`（补发单点必须用它）；`--miss-policy execute` 时 run 目录自动加 `_exec` 后缀 |
| `pipeline/inject/sweep_theta.py` | θ 扫描驱动：run 段把一列 θ 自动排队跑 run+score（幂等，有 INJECT_REPORT 就跳过）；curve 段装配多点曲线 + 服务侧对照 + 逐指标噪声地板 | run：`python3 run.py sweep-run --runs <逗号列表> --services <逗号列表> --concurrency 16`（发射类）；curve：`python3 run.py sweep-curve --runs <同列表> --out … [--control <对照目录>]`（纯 CPU）。⚠️ 口径铁律：各点只许差 θ 一个变量，同 --bs 同机器（实测 batch size 变了 greedy 生成会翻个别条） |
| `pipeline/inject/check_bundle.py` | 产物加载校验：训好的权重换个进程装得起来、打得出分（非精度评测） | `python3 run.py check-bundle-mbert --run <run> --data <d>`（纯 CPU）／`check-bundle-causal`（发射类）；产 BUNDLE_CHECK.txt |
| `pipeline/inject/parse_call.py` `build_form_table.py` `extract_completed.py` `acceptance.py` | 调用串解析、表格装配、完成轨迹抽取、验收器等支撑件 | 被上面几件 import 或按注册表任务名跑 |

### 1.6 活跑注入线（任务级评测）

评测全程不判预测对错——出手就在正身世界上"存档→执行→回档→重冻时间"拿真实返回
（报错也原样），注入 `[SYSTEM NOTE: prefetched {call} = {result}]`（无授权句），
丢弃切口后溢出、继续分段生成。设计书随清场删除，要看去 git 快照 `b1f5b9c`
的 `plans/2026-08-01-live-inject-design.md`。

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `pipeline/inject/live_appworld.py` | 驱动器：整题活跑（with probe / no probe 两臂）。prompt 以 token id 发（/render 前缀 + 注入后 /encode），不出手的步与 chat 端点喂引擎的 id 串相同。分段生成（每段 `--chunk-tokens` 默认 64，贪心），每个新句子级切口问探针，首过 θ 触发注入（默认每步至多 1 次），`<\|end\|>` 后放大段长收尾；每题落一个 `live_<task_id>.jsonl`（meta/gen/spec/env/final）。自带 `--selftest-shadow <轨迹>`（无服务验证三连不污染正身） | `python3 run.py live-appworld --base-url <vLLM /v1> --probe-url <probe_server> --split test_normal --outdir … --exp …`（发射类）；⚠️ 只能 `envs/appworld/venv/bin/python` 跑；对照臂加 `--no-probe`；分片 `--num-shards/--shard-id`；默认跑完即删 appworld 输出目录 |
| `pipeline/inject/probe_server.py` | 探针服务（GPU，两个 0.6B 约 3GB）：/score 前缀→置信度、/gen 触发点→整条预测调用、/render messages→harmony 前缀 token id（`harmony_render`，与 chat 端点逐 token 同；appworld venv 没有 transformers/openai_harmony，渲染只能放这侧）、/encode 生成文本→id（注入后重发用）、/health 配置回显（含 `render=harmony_ids`，驱动器据此拒老服务）。`selftest` 子命令拿存好的 logits 对账活跑口径 | serve：`python3 run.py probe-serve --theta <θ> --port 8790 --device cuda:0`（发射类）；selftest：`python3 run.py probe-selftest --theta <θ> --events 2`（纯 CPU）。--theta 必传无默认（METHOD.md 轴4） |
| `pipeline/inject/score_live.py` | 打分器（纯 CPU）：活跑轨迹 + 已采对照轨迹按题配对 → `LIVE_REPORT.{json,md}`。任务成败、billed token（含丢弃溢出）、出手事后账 | `python3 run.py score-live --live-dir <outdir> --base-root <对照轨迹根>`（纯 CPU） |

已知口径差（报告必带）：探针逐前缀前向 vs 训练侧整段前向（分词边界效应）；
切口只查前 64 个真实切口；注入内容"单条调用返回" vs 回放线"整块 stdout"；
harmony 日期行是活跑当天，与对照批采集日不同。

---

## 2. 服务与辅助件（envs/serve_logs/ 等）

`envs/serve_logs/launch_vllm_*.py`（vLLM 发射脚本，按批次参数化）、
`launch_splice_clients.py` / `live_arm_job.sh` / `splice_plan_job.sh` / `awdiag_job.sh`
（客户端与作业壳）、`accept_test.py` / `accept_tools_test.py` / `gptoss_accept_test.py`
（服务端验收：接口通、工具调用格式对）、`launch_smoke3env.py` / `launch_smokestb.py`
（多环境冒烟）；`envs/collect/bfcl_gptoss/`（gpt-oss 进 BFCL 的 chat 端点 handler +
install_patch.py）。发射类一律 `python3 run.py show <task>` 出命令、gpu-run 发射。

---

## 3. 记账与发射工具（ops/ 与根目录）

| 程序/文件 | 干什么 | 怎么用 |
|---|---|---|
| `run.py` | **一切注册表任务的唯一入口**；CPU 任务直跑，发射类只出命令（过脏树门禁）；训练四格 `CELLS`、评测格 `EVAL_CELLS` 的唯一真源 | `python3 run.py list / show <task> / <task> … / recipe <name> / status / selfcheck` |
| `ops/record.py` | 数字账 CLI：start（发射时记，自动抓 git HEAD 与脏否）/ finish（补数字与结论）/ render（重渲染 RESULTS.md）/ list / show | `python3 run.py record start --run-id X --track <方向> …`；`… record finish RUN_ID --metric k=v --conclusion …`；`… record render`。⚠️ 要 run_id 四处一致只能用 `--run-id`：`--name` 会自动加时间戳前缀 |
| `ops/gpu_jobs.py` | GPU 台账 CLI：register / finish / watch / free / status / json。free/register/finish 卡的实时占用永远现场探测；register 现在多数由 `run.py launch`（经 `launch_common.register_all`）自动调用，手打这条命令是漏登记的补录路径。status/watch/json 三个终端出口改读采样器（`ops/sampler.py`）落盘的 `latest.json`（工单 07）：最后采样时刻在 `FRESH_S`=300 秒内就用它渲染（`read_latest()`/`fmt_table_v2()`，表头带最后采样时刻，判定/进度/速率/token/ETA 全部现成，末尾列台账外 tmux session——漏 register 的手搓发射），过期打一行警告退回现有的现场实探 `collect()` 老路；json 出口过期时给老 `collect()` 结果外加 `sampler_stale: true` | `python3 run.py gpu-jobs register --name N --workdir W --piece host:gpus:session:logpath …`；`… free`；`… finish NAME [--force]`；⚠️ watch 对 shiga 误报 EXIT（ssh host key）；`NEW1_MONITOR_DIR` 环境变量可把采样历史读取目录指到别处（单测用） |
| `ops/jobs.json` | 台账本体 | 只经 register/finish 读写 |
| `ops/heartbeat.py` | 心跳：长程脚本向采样器上报进度的唯一通道。一行 = 前缀 `@hb ` + 一个 JSON，必填 `done/total/unit/ts`，选填 `tok_in/tok_out/loss/status`；`emit()` 写、`parse()` 读，只用标准库（任何 venv 都能 import）。进主循环先 `emit(0, total, unit)` 一条，把模型加载耗时甩出心跳时间轴外；新脚本不接 = 窗口里永远 warm-up 中（见 `extending.md §3.2`） | 库，不单独跑：`import heartbeat` 后 `heartbeat.emit(done, total, unit, ...)` |
| `ops/verdicts.py` | 判定引擎，纯函数零 IO：六格判定（已完成/已挂/疑似卡死/warm-up 中/变慢/健康）按固定优先级判，命中即停；`DEFAULTS` 收全部常量（判定线=5×典型心跳间隔、升级线=判定线×3、warm-up 上限 30 分钟等），别处不许硬编码；判定线按任务自己的心跳间隔自适应（`typical_gap_s`） | 库，不单独跑：采样器 `import verdicts as V` 调用 |
| `ops/launch_common.py` | 发射公共件：探卡 `probe_free`（ssh 查计算进程，占用/探测失败都算非 FREE，fail-closed）、`local_host`/`has_session`/`tmux_launch`（本机 vs 远程 ssh 分支）、`register_all`（三处登记一口气：台账 rich 分片 → `record.py start` 子进程 → RUNMETA，任何一步失败原样中止，重复 run_id 在台账这步就被拒）。只是库，不接注册表；被谁接见 `run.py launch`（工单 09）与两个排卡发射器（工单 11） | 不单独跑，`import launch_common` 后调用 |
| `ops/launch_cmd.py` | `run.py launch` 子命令本体（工单 09/10）：把发射钉死成十步——解析参数 → task/`--cmd` 两种模式 → `gate_dirty` 脏树门禁 → `--run-id`/`--track` 必填校验 → pieces 解析+分片注入（shardable 才许多 `--piece`，自动注入 `--shard-id`/`--num-shards`）+ session/log 命名 → `--dry-run` 只打印不登记 → 逐 piece `probe_free` 非 FREE 整次拒绝 → `tmux_launch` → 30 秒验活窗口 → `launch_common.register_all` 三处登记+打印监控入口；补射模式 `cmd_refire` 只改台账该 piece 的 host/gpus/log/launched_at，不新开 record、不重复 register | `python3 run.py launch <task> [参数...] --run-id ID --track 方向 --piece host:gpus [--piece ...] [--outdir DIR] [--service] [--dry-run]`；`… launch --cmd '<命令>' --workdir DIR …`（注册表外逃生口）；`… launch --refire RUN_ID --idx N [--piece host:gpus]`（补射） |
| `ops/sampler.py` | 长程任务采样器（常驻）：60 秒一轮读台账、tail 日志抓心跳（`ops/heartbeat.py`）、ssh 探存活、`ops/verdicts.py` 算判定，落盘 NFS monitor 目录的 `latest.json`/`state.json`/`history/<job>.jsonl`；补射（launched_at 变了）整段状态重开、同一条心跳不重复计数；同进程开 `WebServer`（`ThreadingHTTPServer`），网页线程只读落盘的 `latest.json`，不碰采样线程内存，采样端 ssh 卡住不影响出页——根路径出任务表（`render_html` 纯函数拼，判定/进度/速率/token/ETA/事故记录/台账外 session，30 秒自动刷新，过期阈值 `sample_interval_s*3` 从 `verdicts.DEFAULTS` 生成，不另抄数），`/json` 出 `latest.json` 原文。事故触发全链已接通（2026-08-08 用户授权后实装）：`should_trigger(row, ps)` 判是否拉事故 agent（达升级线且当前没开着事故才触发，允许补射的条件是判定已挂且这个分片位还没补射过）、`build_incident_prompt(row, allow_refire)` 拼提示词（`INCIDENT_PROMPT` 模板）、`maybe_trigger_incidents` 每轮扫描命中即写 `incidents.jsonl` + `spawn_agent` 拉无头 claude 子进程（模型钉 opus，输出进 `monitor/incidents/<事故编号>.out`），`incident_open` 随本轮 `state.json` 落盘防重复触发。手动演练经用户 2026-08-08 裁决取消，全链只有单测（mock 子进程）背书，没有真实拉过一次 opus。服务类分片（`kind=="service"`，工单 13）不走心跳解析：`sample_once` 改读 `read_vllm_stats(log)`（`VLLM_STATS_RE` 抓 vLLM 吞吐行，2026-08-08 从真实日志核实的格式，`vllm/v1/metrics/loggers.py:263-313`），吞吐行断流（引擎空闲降级 debug 不打印）不重置显示值；判定仍只由 `probe_port`（`/health`）决定，吞吐行只借用 `tok_in`/`tok_out` 这两个显示位出 prompt/生成速率（tokens/s），不进 `verdicts.judge` | `python3 run.py sampler --once`（采一轮就退，冒烟用）；`… sampler --interval 60 --port 8377`（常驻，登录机 tmux 里跑；`--port` 默认 8377）；`NEW1_MONITOR_DIR` 环境变量可把落盘目录指到别处（单测用） |
| `ops/launch_probe.py` | 四格训练的通用 tmux 发射壳（批次/数据/环境参数化）。**gate 型任务：run.py 真执行它，它自己 ssh+tmux 发射**，所以出手前过脏树门禁。has_session/tmux 模板/探卡/登记已接 `launch_common`（工单 11）：每格发射前 `probe_free` 实探目标卡，非 FREE 打印原因跳过该格（排卡表半空常见，不整表拒绝）；每格 LAUNCHED 后 RUNMETA 照旧写完，再 `register_all` 自动补台账（track=`probe_<batch>`）与 `record.py start`——登记失败（如撞了重复 run_id）只 WARN 不中断发射循环，因为 tmux 那格已经真的发出去了 | `python3 run.py launch-probe smoke --batch <b> --data-root <d> --env <e> --model <m> --host <h> --gpus …`；`full … --placement <排卡表.json>`（一格一行 host/gpu/extra）；`--dry-run` 只打印，不探卡不登记；`--force` 透传（smoke 重跑必用） |
| `ops/launch_eval.py` | 评测格的 tmux 发射壳，格表从 run.py import；依赖顺序硬检查（call 档发射前查工具格 REPLAY_REPORT.json）与训练产物存在检查照旧不动。同 `launch_probe.py` 接了 `launch_common`：每格发射前 `probe_free`，非 FREE 跳过该格；LAUNCHED 后 RUNMETA 照旧+`register_all` 自动登记台账/record（track=`eval_<batch>`，run_id = session 原样，**不去掉 `eval_` 前缀**——去掉会跟同一格训练 job 的 rid `{batch}_{model}_{cell}` 撞车，训练 job 按 SKILL.md Phase D 通常还没销号，F1 复核） | 经注册表评测任务间接用；`python3 run.py launch-eval tool/call --batch <b> --data-root <d> --env <e> --placement <排卡表.json>` |
| `ops/runmeta.py` | 产物钉代码：往产物目录写 RUNMETA.json（commit+argv+脏清单）；发射器自动调，手搓发射必须补 | `python3 run.py runmeta <产物目录> --cmd '<完整命令>'` |
| `ops/gpu_state.md` | 集群慢变量：tokyo105(=shiga) 8×A6000、106 10×A6000、107 4×RTX6000Ada、108(=saitama) 3×H100+3×H200；驱动/CUDA/坑（cu128 轮子在 12.2 驱动机可跑、HF 缓存在 NFS 等） | 挑卡前读 |
| `ops/env_locks/` | 环境锁文件 | 环境变更时核对 |
| `learn/vllm/build_artifact.py` | 课页 → artifact 单文件的确定性转换器：内联 `assets/` 的样式与脚本、去掉文档外壳、本地链接降级成纯文本；出口自检拦 doctype/body/相对路径/外链资源 | `python3 run.py build-lesson-artifact --lesson learn/vllm/lessons/<课页>.html`；`--check` 只校验同步（发布前先跑）；⚠️ `*.artifact.html` 是渲染产物，手改会被下次重跑覆盖——要改改课页或 `learn/vllm/assets/` |
| `model_registry.py` | 模型地址映射，脚本一律经 resolve() 取路径 | `python3 model_registry.py <别名>`；⚠️ 落后于磁盘：LFM2.5-350M-Base 与 Qwen3-0.6B-Base（cgen 硬编码在用）都没注册 |

---

## 3.5 research-loop plugin（`research-loop/`，机器级通用件）

| 程序 | 干什么 | 怎么用 |
|---|---|---|
| `research-loop/` 整目录 | 研究循环 plugin 本体（三层 + 监察面 + 账本机制）：五个 skill、inspector agent、九个脚本、fallback 假铁轨、从 `research-loop/tables/` 生成的 schemas/。设计稿在 `.scratch/research-loop/spec.md`，工单在同目录 `issues/` | 入口 `python3 research-loop/scripts/ledger.py <子命令>`；自测 `python3 research-loop/tests/run_all.py`。**不是 run.py 注册表任务**，不挂 TASKS；new1 挂接（写仓库根 research-loop.json）是后续单独一步 |

---

## 4. 环境与权重

**训练两环境（uv 建，⚠️ 均未装 pip，版本读自 dist-info）：**

| 环境 | Python / transformers / torch | 管什么 |
|---|---|---|
| `mbert-env` | 3.11.15 / **4.57.6（钉死）** / 2.11.0+cu128 | mtool、mext 训练与评测 |
| `cprobe-env` | 3.11.15 / **5.14.1（≥5.14 线）** / 2.11.0+cu128 | ctool、cgen 训练与评测（`--head causal` 的 eval 也必须它，import 链带 torch）；两环境互不升级 |

**基准环境（envs/ 下）：** `appworld`（pip 包 0.1.3.post1，venv 是 exec_calls/live_appworld 的唯一解释器）、`alfworld`（0.4.2，data 软链 → NFS `envs/alfworld_data`，2026-08-02 改指）、`bfcl`（bfcl_eval 2026.3.23；⚠️ 自带独立 cu13 系 torch 2.13.0）、`tales`（tale_suite 1.0.0rc2，捆带 alfworld/scienceworld 等）、`tau2-bench`（唯一真源码 clone，.venv 装 tau2 1.0.1）、`toolhop` + `toolhop-env`、`stabletoolbench` + `stb-server-env`、`vllm-env`（vllm 0.26.0 服务环境）、`cuda-compat-13.0`（驱动 580 兼容库）。toolhop/stabletoolbench 数据实体在 NFS，home 是软链。

**权重（`/net/tokyo100-10g/data/str01_01/y-guo/models/`）：** gpt-oss-120b 122G（含 original/ 65G 参考格式，vLLM 用不到）、ModernBERT-base 3.0G（含 onnx/ 1.5G 用不到）、Qwen3-0.6B-Base 1.2G、LFM2.5-350M-Base 681M。⚠️ 后两个未进 model_registry。两个 27B Qwen 在 zhou-y 共享盘（registry 有条目）；Qwen3-8B 等走 HF 缓存（`HF_HOME=/net/…/y-guo/hf`）。

---

## 5. 还成立的坑（清场后复核，2026-08-02）

1. **磁盘配额**：/home 用户配额炸过两次（训练存权重、appworld 输出目录）。大产物一律直接写 NFS；exec_calls/live_appworld 默认删中间目录自保。
2. **`.claude/skills/probe-pipeline/references/stage-commands.md` 落后于代码**：inject 主线缺失、check_callstr 解释器写错。照它跑之前以本文和 `run.py show` 为准。
3. **model_registry 缺条目**：LFM2.5-350M-Base、Qwen3-0.6B-Base 未注册（后者 cgen 硬编码在用）。
4. **跨批 token 数不可直比**：不同服务实现、不同 --bs、不同并发都会抖；同一条曲线必须同服务同 --bs 同机。
5. **bfcl 冻结题单已删**：老随机规则复现不出老三堆，要用从 git 快照 `b1f5b9c` 找回（§1.1）。
6. **发射前 commit 铁律**：旧阶段执行率为零，记录里的 HEAD 大多追不回真实代码。新阶段从第一发起就守住。
