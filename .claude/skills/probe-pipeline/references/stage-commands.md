# stage-commands — 五段流水线的照抄命令表

本文件是 collect / annotate / train / eval / inject 五段的命令模板,接口逐字抄自 `pipeline/` 源码(2026-07-31 c1 批次的代码状态),照抄替换占位符即可跑。
配套的流程说明在同目录上一层的 `SKILL.md`;判分口径与数据设定不在本文件,在 `references/invariants.md`。
占位符约定:`<MODEL>` = q35/q36/gptoss 之类的模型短名,`<BATCH>` = 批次前缀(如 c1),`<ENV>` = appworld/bfcl/tales,`<DATA_ROOT>` = 数据集目录(如 `pipeline/data/aw_official_v1/<MODEL>`)。

## 0. 环境与路径常量

| 环境 | 绝对路径 | transformers | 管哪条线 |
|---|---|---|---|
| mbert-env | `/home/y-guo/reproduce/new1/mbert-env/bin/python` | 4.57.6 | ModernBERT:mtool / mext,以及评它们的 eval |
| cprobe-env | `/home/y-guo/reproduce/new1/cprobe-env/bin/python` | 5.14.1 | 因果模型:ctool / cgen,以及评它们的 eval |

两个环境互不升级(混合架构在旧版分块增量喂会静默算错,这是钉版本的原因)。**纯 CPU 脚本**(只用标准库,任意 `python3`,不占卡):`collect/gen_launch.py`、`annotate/build.py`、`annotate/param_label.py`、`annotate/accept_v3diff.py`、`eval/summarize_matrix.py`。其余全部要显卡。

| 名目 | 路径 |
|---|---|
| 工程根 | `/home/y-guo/reproduce/new1` |
| 数据根 | `/home/y-guo/reproduce/new1/pipeline/data/<批次数据集名>/<MODEL>` |
| runs 根 | `/home/y-guo/reproduce/new1/pipeline/runs`(smoke 产物在 `pipeline/runs/smoke/<rid>_smoke`) |
| 日志目录 | `/home/y-guo/reproduce/new1/logs` |
| 采集 envs 根 | `/home/y-guo/reproduce/new1/envs`(轨迹落在 `envs/runs/<run_id>/`) |
| vLLM 服务日志 | `/home/y-guo/reproduce/new1/envs/serve_logs` |
| 模型权重 | `/net/tokyo100-10g/data/str01_01/y-guo/models`(别人的在 `.../zhou-y/models`) |

底座权重(写死在脚本里,换底座要改代码):
- ModernBERT-base → `/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base`(train_mbert_tool.py:32、train_mbert_extract.py:37)
- Qwen3-0.6B-Base → `/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base`(train_causal_tool.py:50、train_causal_callgen.py:40)

---

## 1. collect — 采集

**干什么**:吃一份 manifest json,生成 vLLM 服务发射器 + 客户端分片发射器 + 人读的清单;**只生成不执行**,不 ssh 不碰显卡。

```bash
cd /home/y-guo/reproduce/new1
# 试生成(先看一眼,绝不碰 envs/)
python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_<BATCH>.json \
  --dry-run --out-override /tmp/genlaunch_<BATCH>/
# 正式生成 -> envs/runs/<run_id>/
python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_<BATCH>.json
```

| flag | 必填 | 说明 |
|---|---|---|
| `--config` | 是 | manifest json,模板见 `pipeline/collect/manifest_w0.json` |
| `--dry-run` | 否 | 必须同时给 `--out-override`,否则退 2 |
| `--out-override` | 否 | 改写到别处 |
| `--force` | 否 | 允许覆盖目标目录已有同名文件 |

**输入**:manifest 必需 `run_id` / `servers[]{host,gpu,model_key,port,session,extra_flags,card}` / `clients[]{tag,model_key,split,num_shards,shard_ports[],outdir,exp}`;可选 `envs_root`(默认 `envs`)、`client_session_prefix`(默认由 run_id 前两段拼,`w0_aw_official` → `new1_w0aw`)。
**输出**:`envs/runs/<run_id>/launch_servers.py`、`launch_clients.sh`(0o775)、`MANIFEST.md`。
**退出码**:正常 0;所有校验失败一律 `sys.exit(2)`——server 必须同一台机、model_key 必须在表里(只认 q35/q36/gptoss)、端口/session/卡不许重复、`len(shard_ports)==num_shards`、分片端口必须存在且模型匹配、目标已有同名文件且无 `--force`。`outdir` 非标准名只 WARN 并强制改成 `appworld_<model_key>`(下游按目录名尾巴认模型,改名会被静默跳过)。

生成完的两个发射器仍然要占卡跑 → **走 gpu-run skill 发射,不要手搓 ssh/nohup**。

---

## 2. annotate — 标注

**干什么**:把原始轨迹切成"思考前缀 → 该步调用哪个工具"的样本集(build.py),再给每个样本标出参数值的字符区间(param_label.py)。两步都是纯 CPU。

```bash
cd /home/y-guo/reproduce/new1
python3 pipeline/annotate/build.py       --config pipeline/configs/<BATCH>_<MODEL>.json
python3 pipeline/annotate/param_label.py --config pipeline/configs/<BATCH>_<MODEL>.json
# 可选:改过 rules.py/build.py 后的一致性验收(路径全写死,无参数)
python3 pipeline/annotate/accept_v3diff.py
```

两脚本共用同一份 config,**一模型一份**。config 字段(照抄 `pipeline/configs/aw_q35.json`):

| 字段 | 含义 |
|---|---|
| `run_family` / `model_short` | 只进报告标题 |
| `env` | appworld / tales / bfcl,决定事件抽取器 |
| `model_full` | 按它过滤事件(如 `qwen3.5-27b`),一模型一套数据 |
| `traj_runs[]` | 轨迹目录列表,绝对路径 |
| `official_split_files.{train,val,test}` | 官方题单 txt,每行一个 task_id |
| `data_out` | 数据集输出目录 = 后续所有 `--data` |
| `seed` | 默认 20260729 |

**输出**:`<DATA_ROOT>/{train,val,test}.jsonl`、`tool_vocab.json`、`router_stats.md`、`qa_sample.txt`、`ANNOTATE_REPORT.md`;param_label 再写 `<DATA_ROOT>/params/{train,val,test}.jsonl` + `PARAM_LABEL_REPORT.md` + `CHECK_50.md`。
**退出码**:0;`raise SystemExit`(=1)三种——过滤后没有 `model_full` 的事件、**有 unit 不在任何官方题单里**(拒绝静默丢弃,换环境时最常炸的一条:题单文件路径写错或换了 split 命名就会全量报错)、未知 env。自检 assert 失败也是 1(前缀=原文切片 200 抽检、unit 不跨 split、每堆 20 unit 题单归属)。accept_v3diff 特殊:**全一致=0,有任何不一致=1**,报告写 `pipeline/annotate/ACCEPT_V3DIFF.md`。

---

## 3. train — 四格训练

**干什么**:同一份数据训四个格——mtool(ModernBERT 判工具种类)、mext(ModernBERT 圈参数区间)、ctool(因果模型判工具种类)、cgen(因果模型直接写整条调用)。四格互不依赖,可全并行。**四格全要显卡 → 走 gpu-run skill 发射,不要手搓 ssh/nohup。**

先冒烟(每格加 `--smoke`,产物写 `pipeline/runs/smoke/`,不污染正式目录),再全量。以下是 c1 批次**真实跑过的 12 条命令**的形态(每格一条,只有模型段不同):

```bash
# mtool  [mbert-env]
/home/y-guo/reproduce/new1/mbert-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_mbert_tool.py --data /home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35 --out /home/y-guo/reproduce/new1/pipeline/runs/c1_q35_mtool
# mext   [mbert-env]
/home/y-guo/reproduce/new1/mbert-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_mbert_extract.py --data /home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35 --out /home/y-guo/reproduce/new1/pipeline/runs/c1_q35_mext
# ctool  [cprobe-env]  注意 --base qwen 必填、--align-tol 是唯一动过的超参
/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_tool.py --base qwen --data /home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35 --out /home/y-guo/reproduce/new1/pipeline/runs/c1_q35_ctool --align-tol 3e-4
# cgen   [cprobe-env]  没有 --base,底座硬编码 Qwen3-0.6B-Base
/home/y-guo/reproduce/new1/cprobe-env/bin/python /home/y-guo/reproduce/new1/pipeline/train/train_causal_callgen.py --data /home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35 --out /home/y-guo/reproduce/new1/pipeline/runs/c1_q35_cgen
```

换批次时把 `q35` 换成 `<MODEL>`、`c1` 换成 `<BATCH>`、数据集名换掉即可。run_id 一律 `<BATCH>_<MODEL>_<格名>`,四处一致(数据目录名 / tmux session / 台账 name / commit message)。

| flag | 谁有 | 说明 |
|---|---|---|
| `--data` | 四格 | 必填,`<DATA_ROOT>`;mext 另可用 `--params`(默认 `<DATA_ROOT>/params`) |
| `--out` | 四格 | 必填,防覆盖旧件 |
| `--base qwen` | 仅 ctool | **必填**,choices 只有 `qwen` |
| `--align-tol` | 仅 ctool | 默认 1e-4;长窗口下 fp32 舍入噪声会把绝对差顶到 1e-4,c1 批次统一用 `3e-4`。判是不是真算错看报告里的 reldiff:1e-6 量级=纯噪声,1e-3 以上=真算错,放宽也没用 |
| `--align-only` | 仅 ctool | 只跑对齐检查即退(0),开训前想单独验就用它 |
| `--smoke` | 四格 | mtool/mext/cgen = 500 训练 / 200 评估实例,ctool = 200 / 80 事件,均 1 epoch |
| `--env` | 四格 | 默认 appworld,**仅作日志标签**,不影响数据路径 |
| `--device` | 除 mtool | 默认 cuda |

其余全用默认(`--max-len 4096`;mbert 两格 `--bs 8 --accum 4 --lr 2e-5`,因果两格 `--bs 4 --accum 8 --lr 1e-5`;一律 `--epochs 3`)。**本轮 12 次训练除 ctool 的 `--align-tol` 外没动过任何超参。**

**输出**:
- mtool → `<out>/best/`(HF 权重 + tokenizer + `label_map.json`)+ `train_log.jsonl`
- mext → `<out>/best/{model.pt(裸 state_dict,不是 HF 目录), tokenizer, meta.json}` + `train_log.jsonl`
- ctool → `<out>/ALIGN_CHECK.json` + `<out>/best/{HF backbone, tokenizer, head.pt, label_map.json, meta.json}` + `train_log.jsonl`
- cgen → `<out>/best/`(HF 权重 + tokenizer + `meta.json`,内含 `call_sep`)+ `train_log.jsonl`

**退出码**:三格无显式非 0。**ctool 的对齐检查 FAIL → `sys.exit(2)`**(整段一次前向 vs 逐 token 增量前向,末位置隐状态/logits 必须 max|diff| < tol),`ALIGN_CHECK.json` 无论过不过都会先落盘,拿它看 reldiff 再决定是放宽 tol 还是查版本。

---

## 4. eval — 回放评测

**干什么**:在 val 上拟温度、扫触发门槛 θ,再在 test 上冻结跑一次出数;然后在触发点上评参数/整条调用。

### 4.1 依赖顺序(不能颠倒)

1. **先评 6 个工具格**(3 模型 × mtool/ctool):`eval_tool.py` 产出 `REPLAY_REPORT.json` 与 `logits_test.pt` / `logits_val.pt`。6 个之间互不依赖,可并行。
2. **再评参数格**:`eval_mbert_call.py` 吃**同模型 mtool** 的报告与 logits;`eval_causal_call.py` 吃**同模型 ctool** 的报告与 logits。跨模型串会 assert 失败。
3. **最后汇总**:`summarize_matrix.py`(纯 CPU)。

前两步占卡 → **走 gpu-run skill 发射,不要手搓 ssh/nohup**。

### 4.2 命令

```bash
cd /home/y-guo/reproduce/new1
R=/home/y-guo/reproduce/new1/pipeline/runs; D=/home/y-guo/reproduce/new1/pipeline/data/aw_official_v1

# 工具格:mbert 头用 mbert-env,causal 头用 cprobe-env(它要 import pipeline/train/train_causal_tool.py)
mbert-env/bin/python  pipeline/eval/eval_tool.py --env <ENV> --run $R/<BATCH>_<MODEL>_mtool --data $D/<MODEL>
cprobe-env/bin/python pipeline/eval/eval_tool.py --env <ENV> --head causal --run $R/<BATCH>_<MODEL>_ctool --data $D/<MODEL>

# 参数格
mbert-env/bin/python  pipeline/eval/eval_mbert_call.py  --env <ENV> --run $R/<BATCH>_<MODEL>_mtool \
  --extractor $R/<BATCH>_<MODEL>_mext --data $D/<MODEL>
cprobe-env/bin/python pipeline/eval/eval_causal_call.py --env <ENV> --ctool-run $R/<BATCH>_<MODEL>_ctool \
  --cgen-run $R/<BATCH>_<MODEL>_cgen --data $D/<MODEL>

# 汇总(纯 CPU,缺报告的格自动标 PENDING,可边跑边看)
python3 pipeline/eval/summarize_matrix.py --runs-dir $R --out $R/MATRIX_REPORT.md --prefix <BATCH>
python3 pipeline/eval/summarize_matrix.py --runs-dir $R --out $R/MATRIX_REPORT_risk10.md --prefix <BATCH> --risk 0.1
```

### 4.3 `--risk` 双档策略

`eval_tool.py` 固定扫 20 档 θ(0.5→0.975,步长 0.025),对 `RISK_TARGETS = [0.10, 0.05]` 各挑一个"满足触发精度约束前提下覆盖率最大"的 θ,写进 `REPLAY_REPORT.json` 的 `chosen_theta`。约束太紧时该档是 `null`。所以参数格照这个顺序走:

1. 先用默认 `--risk 0.05`;
2. 报告里 `chosen_theta["0.05"]` 是 `null` → `eval_*_call.py` 直接 `SystemExit`(退 1),改传 `--risk 0.1` 重跑;
3. 两档皆 `null` → 这一格判 **N/A**,不再重试(c1 批次的 `q35_mtool` 就是两档全 null,所以 `c1_q35_mext` 至今没有 EXTRACT_REPORT)。

### 4.4 参数表(只列会改的)

| flag | 脚本 | 说明 |
|---|---|---|
| `--env` | 三个 eval | **必填**,choices tales/appworld/bfcl;`eval_causal_call.py` 用它选调用解析正则(appworld 用 `apis.x.y(`,其余用 `名字(`) |
| `--head mbert\|causal` | eval_tool | 默认 mbert;causal 走 backbone + head.pt 路径 |
| `--cached-logits` | eval_tool | 读已存的 `logits_*.pt` 跳过推理,纯 CPU 后处理,重出报告时用它不占卡 |
| `--report-dir` | eval_tool | 默认 = `--run`;验收/试跑时指向别处以免覆盖旧件 |
| `--legacy-splits` | eval_tool | 读旧 calA/calB/test 三堆,仅历史验收用,新批次不要碰 |
| `--risk` | 两个 call | 默认 0.05,见 §4.3 |
| `--limit` | 两个 call | 截前 N 触发事件,冒烟用 |
| `--device` / `--bs` | 全部 | 默认 cuda / 8(eval_tool 的因果打分批大小写死 4) |

**输入 / 输出**:

| 脚本 | 读 | 写 |
|---|---|---|
| eval_tool | `<DATA_ROOT>/{val,test}.jsonl` + `tool_vocab.json`;`<run>/best/label_map.json`(causal 另读 `meta.json`、`head.pt`) | `<run>/logits_val.pt`、`<run>/logits_test.pt`、`<report-dir>/REPLAY_REPORT.{json,md}` |
| eval_mbert_call | `<run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json`;`<DATA_ROOT>/test.jsonl` + `router_stats.md`;`<DATA_ROOT>/params/test.jsonl`;`<extractor>/best/` | `<extractor>/EXTRACT_REPORT.{json,md}` |
| eval_causal_call | `<ctool-run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json`;`<DATA_ROOT>/test.jsonl`;`<cgen-run>/best/`(`call_sep` 从它的 meta.json 读,不硬编码) | `<cgen-run>/CALLGEN_REPORT.{json,md}` |
| summarize_matrix | 各 run 的 `REPLAY_REPORT.json`(mtool/ctool)、`EXTRACT_REPORT.json`(mext)、`CALLGEN_REPORT.json`(cgen) | `--out` 指的 .md,同时打到 stdout |

**退出码**:eval_tool 无显式非 0(但 `--cached-logits` 下 logits 行数与数据行数不符会 assert,退 1——这意味着 `--data` 与当次评测不同源)。两个 call 脚本:该 risk 档 θ 为 null → `SystemExit` 退 1。`eval_causal_call` 另有一条 assert 防止调用切分口径与 `annotate/rules.py` 漂移。summarize_matrix 永远 0。

---

## 5. inject — 产物校验

**干什么**:证明这套权重换个进程也装得起来、打得出分。**能跑通即凭证**,不是精度评测。冒烟阶段就该跑一次。

```bash
cd /home/y-guo/reproduce/new1
# mbert 头(mtool/mext 产物);CPU 就能跑,不必占卡
mbert-env/bin/python pipeline/inject/check_bundle.py --head mbert --device cpu \
  --run pipeline/runs/<BATCH>_<MODEL>_mtool --data <DATA_ROOT>
# causal 头(ctool 产物)
cprobe-env/bin/python pipeline/inject/check_bundle.py --head causal \
  --run pipeline/runs/<BATCH>_<MODEL>_ctool --data <DATA_ROOT>
```

| flag | 必填 | 说明 |
|---|---|---|
| `--run` / `--data` / `--head` | 是 | head ∈ mbert/causal |
| `--device` | 否 | 默认 cuda,给 `cpu` 就能零占卡校验 |
| `--dtype` | 否 | 默认 auto = cuda 上 bfloat16 / cpu 上 float32 |
| `--index` | 否 | 默认 0,取 test.jsonl 第几条 |
| `--temperature` | 否 | 覆盖 REPLAY_REPORT.json 的温度 |

**输入**:`<run>/best/`(label_map.json + 权重 + tokenizer,causal 另要 `head.pt`)、`<DATA_ROOT>/test.jsonl`;`<run>/REPLAY_REPORT.json` **可缺**——缺了就按 T=1.0、θ 记 N/A 走,这条路径专为"刚 smoke 完还没评测"设计。
**输出**:`<run>/BUNDLE_CHECK.txt`(内容同时打到 stdout):预测工具 / 置信度 / 是否过 θ / 真值 / top5 / 加载与前向耗时。
**退出码**:0;`test.jsonl` 里没有 `--index` 那条 → SystemExit 退 1。

---

## 6. 一个批次的完整命令序列

从零到矩阵表。`(CPU)` = 不占卡直接跑,`(GPU)` = **走 gpu-run skill 发射,不要手搓 ssh/nohup**。

```
S1 (CPU)  gen_launch.py --config manifest_<BATCH>.json --dry-run --out-override /tmp/... → 看清单
S2 (CPU)  gen_launch.py --config manifest_<BATCH>.json                    → envs/runs/<BATCH>/
S3 (GPU)  launch_servers.py → smoke 每模型 1 题 → launch_clients.sh       ★ 采集,耗时最长
S4 (CPU)  build.py --config configs/<BATCH>_<MODEL>.json                  ← 等 S3 轨迹落齐
S5 (CPU)  param_label.py --config 同一份 config                            ← 等 S4 的 jsonl
S6 (GPU)  四格 --smoke,产物进 pipeline/runs/smoke/                        ← 等 S5
S7 (CPU)  check_bundle.py --device cpu 对 smoke 产物跑一遍                 ← 等 S6
S8 (GPU)  四格全量训练                                                     ← 等 S7 放行
S9 (GPU)  eval_tool.py × 6(每模型 mtool + ctool)                         ← 等 S8 对应格训完
S10(GPU)  eval_mbert_call.py(吃同模型 mtool)/ eval_causal_call.py(吃同模型 ctool) ← 等 S9
S11(CPU)  summarize_matrix.py 出 0.05 与 0.1 两档表                        ← 随时可跑,缺的标 PENDING
```

并行/串行:
- **S4/S5 逐模型独立**,三个模型可并行(纯 CPU,互不抢资源);同一模型内 S5 必须等 S4。
- **S8 四格 × 三模型 = 12 个 run 全并行**,只受卡数限制(c1 批次:tokyo105 八卡 + tokyo106 四卡)。
- **S9 六个并行**;S10 必须等对应的 S9,因为它要读 `REPLAY_REPORT.json` 的温度/θ 与 `logits_test.pt`。
- S11 任何时候都能跑,不完整就是一张带 PENDING 的表。
- 每次 GPU 发射前先 commit(记录里的 HEAD 只有工作树干净时才追得回真实代码),发射后双登记 `ops/gpu_jobs.py register` + `ops/record.py start`,收尾 `finish`。

---

## 7. 接口陷阱

- **产物写向不对称**:`eval_tool.py` 的 `logits_*.pt` 永远写进 `--run`(`--report-dir` 只改报告);`eval_mbert_call.py` 的报告写进 `--extractor` 而非 `--run`;`eval_causal_call.py` 的报告写进 `--cgen-run` 而非 `--ctool-run`。→ 去 mtool 目录找 EXTRACT_REPORT 会一无所获。
- **`train_log.jsonl` 是 append 模式**(四个训练脚本一致):同一个 `--out` 重跑会在旧日志后面续写,不清空。→ 读日志算轮次/耗时前先确认只有一段 `event=start`,否则数字是两次跑的混合。
- **`--env` 在训练脚本里只是日志标签**,数据路径完全由 `--data` 决定;但在三个 eval 脚本里 `--env` 是必填且**影响判分**(选调用解析正则)。→ 训练时写错无害,评测时写错会让工具名全判错。
- **cgen 没有 `--base`**,底座硬编码;ctool 的 `--base qwen` 却是必填。→ 换底座要改源码,不是加 flag。
- **mext 的权重是 `best/model.pt` 裸 state_dict**,不是 HF 目录,不能用 `from_pretrained` 直接读。→ 复用它必须走 `train_mbert_extract.load_extractor()`。
- **`--head causal` 的 eval_tool 会 import `pipeline/train/train_causal_tool.py`**,所以必须用 cprobe-env 跑;拿 mbert-env 跑 causal 头会在 import 或加载处炸。
- **两个 call 脚本对 θ 为 null 是硬失败**(退 1),不是跳过。→ 批量评测脚本要接住这个退出码并降档到 `--risk 0.1`,否则整批中断。
- **`build.py` 对"unit 不在官方题单"零容忍**(退 1)。→ 换环境(appworld→bfcl→alfworld)时,题单文件的命名与 task_id 格式必须先对齐,否则第一步就全量报错。
- **`gen_launch.py` 强制 `outdir = appworld_<model_key>`**,自定义名只会被 WARN 并改掉;下游事件抽取按目录名尾巴认模型,`MODEL_OF` 只认 q35/q36/gptoss(`annotate/rules.py:18`)。→ 新模型必须先往这张表里加一行,否则采到的轨迹会被静默跳过。
- **`--smoke` 不改 `--out`**:冒烟和全量传同一个 `--out` 会让冒烟权重占住 `best/`。→ 照 `ops/launch_c1.py` 的做法,冒烟一律写 `pipeline/runs/smoke/<rid>_smoke`。
