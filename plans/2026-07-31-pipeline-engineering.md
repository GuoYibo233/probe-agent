# 新流水线施工规格书 — 2026-07-31（详版）

> 写给执行模型的规格书：每段给到文件级、字段级、命令级，执行方**不需要做任何设计决策**。
> 配套文档：总计划 `2026-07-31-pipeline-plan.md`（为什么这么做）、
> 执行手册 `2026-07-31-execution-playbook.md`（GPU 发射与用户规矩）。
> 本文管"代码怎么写"。

---

## 0. 执行守则（先读，违反即返工）

1. **按 §4 → §5 → §6 → §7 → §8 的顺序做**，每段末尾的验收不过，不许进下一段。
2. **抄写优先**：标了【照抄】的函数/常量/正则，从源文件原样复制，一个字符不改；
   标了【改动】的只改列出的那几处；标了【新写】的按本文的规格写。
   不确定某处该抄还是该写 → 默认抄。
3. 字段名、超参、目录名、文件名**全部以本文表格为准**，不许自己发明。
4. 遇到本文没覆盖的决策点 → **停下来问用户**，不要猜。
5. **禁改清单（永远）**：`envs/` 下一切旧文件、`envs/bert_data/v3*`、
   `envs/bert_runs/*`、`RESULTS.md`（渲染产物）、`ops/runs.jsonl`（只增不改）。
   新代码只在 `pipeline/` 下写。
6. 每个脚本头部写 docstring：干什么、输入输出、用法示例（照旧脚本的风格）。

## 1. 目录树（第一步一次建齐）

```
pipeline/
  configs/                      # 实验配置 json，进 git
    aw_q35.json  aw_q36.json  aw_gptoss.json
  collect/
    gen_launch.py               # 【新写】发射清单生成器（§7）
  annotate/
    rules.py                    # 【照抄】切分规则常量与函数（§4.1）
    build.py                    # 【改动】主构建器，源 = build_dataset.py（§4.2）
    param_label.py              # 【改动】参数区间标签，源 = envs/bert/param_label.py（§4.3）
    accept_v3diff.py            # 【新写】验收脚本（§4.5）
  train/
    input_modes.py              # 【照抄】envs/bert/input_modes.py 整文件
    train_mbert_tool.py         # 【改动】源 = envs/bert/train_probe.py（§5.1）
    train_mbert_extract.py      # 【改动】源 = envs/bert/train_extractor.py（§5.2）
    train_causal_tool.py        # 【改动】源 = envs/bert/train_causal_probe.py（§5.3）
    train_causal_callgen.py     # 【新写】因果+参数生成（§5.4）
  eval/
    eval_tool.py                # 【改动】源 = envs/bert/eval_replay.py（§6.1）
    eval_mbert_call.py          # 【改动】源 = envs/bert/eval_extract.py + param_tiers.py（§6.2）
    eval_causal_call.py         # 【新写】因果生成判分器（§6.3）
    summarize_matrix.py         # 【新写】12 格汇总表（§6.4）
  inject/
    check_bundle.py             # 【新写】产物加载校验器（§8）
  data/                         # 产物，不进 git
  runs/                         # 产物，不进 git
```

`.gitignore` 末尾追加（原文照抄）：

```
pipeline/data/**
!pipeline/data/**/
!pipeline/data/**/*.md
pipeline/runs/**
!pipeline/runs/**/
!pipeline/runs/**/*.md
```

## 2. 全局约定

### 2.1 解释器（用错环境 = 事故）

| 脚本 | 解释器 |
|---|---|
| annotate/*、collect/*、eval/summarize_matrix.py | 任意 python3（纯标准库） |
| train_mbert_*.py、eval_tool.py（评 mbert run）、eval_mbert_call.py | `/home/y-guo/reproduce/new1/mbert-env/bin/python` |
| train_causal_*.py、eval_tool.py（评 causal run）、eval_causal_call.py | `/home/y-guo/reproduce/new1/cprobe-env/bin/python` |

### 2.2 常量（全部【照抄】，出处在括号里）

| 常量 | 值 | 出处 |
|---|---|---|
| SEED | 20260729 | 各旧脚本 |
| MIN_THINK / MAX_BOUNDS / HIST_ROUNDS / RESULT_CAP | 40 / 64 / 3 / 400 | build_dataset.py |
| SENT_RE | `(?<=[.!?])\s+|\n` | build_dataset.py |
| MODEL_OF | {"q35":"qwen3.5-27b","q36":"qwen3.6-27b","gptoss":"gpt-oss-120b"} | build_dataset.py |
| THETAS | 0.5 到 0.975 步长 0.025 共 20 档 | eval_replay.py |
| RISK_TARGETS | [0.10, 0.05] | eval_replay.py |
| BOOT | 1000 | eval_replay.py |
| ALIGN_TOL | 1e-4 | train_causal_probe.py |
| ModernBERT 权重 | `/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base` | train_probe.py |
| Qwen3-0.6B-Base 权重 | `/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base` | train_causal_probe.py |
| CALL_SEP | `"\n[CALL] "` | 本文新定（§5.4） |
| FIND | `"\n[FIND] "` | train_extractor.py |

### 2.3 实验配置 schema（configs/aw_q35.json 完整示例）

```json
{
  "run_family": "aw_official_v1",
  "env": "appworld",
  "model_short": "q35",
  "model_full": "qwen3.5-27b",
  "traj_runs": ["/home/y-guo/reproduce/new1/envs/runs/full_v1",
                 "/home/y-guo/reproduce/new1/envs/runs/full_v2_topup",
                 "/home/y-guo/reproduce/new1/envs/runs/w0_aw_official"],
  "split_mode": "official",
  "official_split_files": {
    "train": "/home/y-guo/reproduce/new1/envs/appworld/data/datasets/train.txt",
    "val":   "/home/y-guo/reproduce/new1/envs/appworld/data/datasets/dev.txt",
    "test":  "/home/y-guo/reproduce/new1/envs/appworld/data/datasets/test_normal.txt"
  },
  "data_out": "/home/y-guo/reproduce/new1/pipeline/data/aw_official_v1/q35",
  "seed": 20260729
}
```

q36 / gptoss 两份只改 `model_short` / `model_full` / `data_out` 最后一段。

### 2.4 run_id 规则（四处一致：数据目录 / tmux / 台账 / commit）

训练 run_id = `c1_<model_short>_<cell>`，cell ∈ {mtool, mext, ctool, cgen}。
共 3 × 4 = 12 个。产物目录 = `pipeline/runs/<run_id>/`。

### 2.5 堆名映射（新旧对照，改代码时用）

新流水线只有三堆：**train / val / test**。改旧脚本时的机械替换规则：
- 旧代码读 `calA.jsonl` 的地方 → 读 `val.jsonl`
- 旧代码读 `calB.jsonl` 的地方 → 读 `val.jsonl`（温度和门槛都在同一个 val 上定）
- 日志/报告里的字段名 `calA_weighted_acc` 等**保持原名不改**（下游脚本按名读）

## 3. 数据契约（字段级）

### 3.1 轨迹 jsonl（采集器产物，只读不改）

一个任务一个文件 `appworld_<task_id>.jsonl`，每行一条：

| type | 字段 | 说明 |
|---|---|---|
| `meta` | 首行；`task_id`, `instruction`, … | 事件抽取取 `instruction` 当题干、`task_id` 当 unit |
| `gen` | `step`, `reasoning`, … | `reasoning` = 思考原文（一字未删） |
| `env` | `step`, `action`, `result` | action = 模型写的代码块 |
| `final` | `steps`, `completed`, `eval` | 存在 `"type": "final"` 即该任务已完成（--resume 的判据） |

### 3.2 样本 jsonl（annotate 产物）

旧 11 字段【照抄 build_dataset.py 的 dict】+ 新 2 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| text | str | `Task: …\n[HISTORY]\n…\n[THINKING]\n<前缀>`（assemble() 产出） |
| label | str | 工具名（appworld 形如 `apis.spotify.login`） |
| w | float | 1/m，m = 该事件切点数，round 6 位 |
| depth | float | 切点字符位 / 思考全长，round 4 位 |
| sent_idx / n_sents | int | 第几个切点 / 共几个 |
| event | str | `f"{traj}|s{step}"`，事件主键 |
| traj / unit / model / step | str/str/str/int | 轨迹名 / 任务实例 / 生成模型全名 / 步号 |
| **label_call**（新） | str | 规范化完整调用，见 §3.3 |
| **args_named**（新） | list | `[{"key":k,"value":v}, …]`，见 §3.3 |

### 3.3 label_call 规范（新，annotate 构造）

- 参数解析用【照抄】`envs/bert/param_label.py` 的 `split_args_named()`（保参数名版；
  kwarg 取名字，位置参数取 `pos0/pos1/…`）。
- 值归一化与旧口径完全一致：`strip()` 后 `strip("\"'")`。空值跳过。
- `args_named` = 按调用里出现顺序的 `[{"key","value"}]`。
- `label_call` = `f"{label}({', '.join(f'{k}={v}' for k,v in args_named)})"`；
  无参数时 = `f"{label}()"`。

### 3.4 参数区间标签 jsonl（annotate 产物，给 mext 用）

与 `envs/bert_data/v3_params` 同构【照抄 param_label.py 的输出逻辑】：
每行 `{event, sent_idx, w, params:[{key, value, start, end, found}]}`，
start/end 是参数值在**该样本自己 text** 里最靠末尾一次出现的字符区间
（`str.rfind`），找不到 `found=false`。

### 3.5 训练产物布局

| 格 | `pipeline/runs/<run_id>/` 下 |
|---|---|
| mtool | `best/`（HF 权重+tokenizer+`label_map.json`）、`train_log.jsonl`；eval 后追加 `logits_val.pt`、`logits_test.pt`、`REPLAY_REPORT.{json,md}` |
| mext | `best/`（`model.pt`+tokenizer+`meta.json`）、`train_log.jsonl` |
| ctool | `best/`（backbone HF 权重+tokenizer+`head.pt`+`label_map.json`+`meta.json`）、`ALIGN_CHECK.json`、`train_log.jsonl`；eval 后同 mtool |
| cgen | `best/`（HF 权重+tokenizer+`meta.json`）、`train_log.jsonl` |

### 3.6 REPLAY_REPORT.json 关键字段（eval_tool 产物，【照抄】旧结构）

`temperature`、`theta_sweep_calB`（内容是 val 扫出来的，字段名不改）、
`chosen_theta`（{"0.1": θ, "0.05": θ}）、`test_frozen`（每档 theta/coverage/
trig_acc/earliness/wrong_spec/ci）、`stoptime_calibration_test`、
`depth_bucket_acc_test`、`prior_baseline_event_acc`、`n_events_test`、
`speculation_economics`。`probe_server.py` 读其中的 `temperature`，格式不许动。

## 4. annotate 段

### 4.1 rules.py【照抄】

从 `envs/collect/build_dataset.py` 原样复制：SEED、MAX_BOUNDS、MIN_THINK、
HIST_ROUNDS、RESULT_CAP、MODEL_OF、SENT_RE、`boundaries()`、`clip()`、
`assemble()`、`split_args()`、`first_call_args()`、AW_CALL、BFCL_CALL。
再从 `envs/bert/param_label.py` 复制 `split_args_named()`。

### 4.2 build.py【改动】（源 = build_dataset.py）

CLI：`python build.py --config pipeline/configs/aw_q35.json`

流程（源脚本已有的步骤全保留，改动只有五处）：

1. 事件抽取：【照抄】`jsonl_events()`（appworld 分支）。pattern 仍是
   `appworld_*/appworld_*.jsonl`——**采集目录必须叫 `appworld_q35` 这类标准名**
   （尾巴对上 MODEL_OF 的键，否则该目录被静默跳过——这是实测过的坑）。
2. 【改动①】按 `config.model_full` 过滤事件：`ev["model"] == model_full` 才留。
3. 【改动②】切分：不再 shuffle。读三个官方题单文件（每行一个 task_id），
   `part[unit] = "train"/"val"/"test"` 按 unit 属于哪个文件定；
   unit 不在任何题单里 → **报错退出**（不许静默丢）。
4. 造样本：【照抄】全边界循环，dict 里追加 §3.3 的 `label_call`、`args_named`
  （用事件的 tool + 保名参数重解析 action 得到）。
5. 【改动③】输出堆名 `train/val/test`；【改动④】输出目录 = `config.data_out`；
   【改动⑤】报告文件名 `ANNOTATE_REPORT.md`。
6. 自检【照抄】：前缀断言 200 条、unit 不跨堆断言。追加一条【新写】：
   从每堆抽 20 个 unit，断言其确实出现在对应官方题单文件里。
7. `tool_vocab.json`（该模型自己的事件工具集）、`router_stats.md`、
   `qa_sample.txt`、报告【照抄】（含频率先验基线，报告里写 test 堆的）。

随后跑 4.3：`python param_label.py --config <同一份>`——产
`<data_out>/params/{train,val,test}.jsonl`（§3.4 格式，逻辑【照抄】旧 param_label.py，
只改输入输出路径与堆名）。

### 4.4 产物清单（每模型一套）

`pipeline/data/aw_official_v1/<model_short>/`：
`train.jsonl val.jsonl test.jsonl tool_vocab.json router_stats.md
qa_sample.txt ANNOTATE_REPORT.md params/{train,val,test}.jsonl`

### 4.5 验收（accept_v3diff.py【新写】，不过不许进 §5）

目的：证明事件抽取 + 切样本核心与 v3 逐字节一致（切分法不同，所以不比堆归属）。

1. 用 rules.py + build.py 的抽取与造样本代码，跑 v3 的输入
   （`--runs envs/runs/full_v1 envs/runs/full_v2_topup`，env=bfcl，**不过滤模型**）。
2. 读 `envs/bert_data/v3/bfcl/{train,calA,calB,test}.jsonl` 四堆合并，
   按主键 `(event, sent_idx)` 建索引。
3. 断言：两边样本数相等；每条的 `text/label/w/depth/n_sents/traj/unit/model/step`
   全等（新字段不比）。
4. 输出 `ACCEPT_V3DIFF.md`：两边条数、逐字段不一致计数（必须全 0）。
5. appworld 侧再跑一遍同样对比（v3 appworld），同样必须全 0。

### 4.6 自检清单

- [ ] rules.py 里每个常量与 build_dataset.py 逐一 diff 过
- [ ] 官方题单三个文件行数 = 90 / 57 / 168（注意文件无末尾换行，别用 wc -l 直接当真）
- [ ] 三个模型的 train 堆 unit 集合完全相同（都是那 90 题）
- [ ] label_call 抽查 20 条：工具名 == label，参数与 action 原文对得上
- [ ] ACCEPT_V3DIFF.md 全 0

## 5. train 段（四格）

### 5.1 train_mbert_tool.py【改动】（源 = train_probe.py，mbert-env）

改动清单（其余一字不改，含超参 lr 2e-5 / bs 8 / accum 4 / epochs 3 /
maxlen 4096 / 左截断 / fp32 权重 + bf16 autocast / w 加权损失 / warmup 5% / clip 1.0）：
1. `--data` 语义改为直接指向 `<data_out>`（含 tool_vocab.json 的目录）；
2. 评估文件 `calA.jsonl` → `val.jsonl`（§2.5）；
3. 默认 `--out` 去掉，`--out` 必填（防覆盖）。
smoke 语义【照抄】：500 训练样本 / 200 评估样本 / 1 epoch。

CLI 示例：
```
mbert-env/bin/python pipeline/train/train_mbert_tool.py \
  --data pipeline/data/aw_official_v1/q35 --out pipeline/runs/c1_q35_mtool
```

### 5.2 train_mbert_extract.py【改动】（源 = train_extractor.py，mbert-env）

改动清单：数据路径（文本 = `<data_out>`，参数 = `<data_out>/params`）、
`calA`→`val`、`--out` 必填。其余（FIND 后缀拼接、最小覆盖 token 跨度、
宽松/严格双口径、可答头 BCE + span CE、MAX_SPAN_TOK=64）一字不改。

### 5.3 train_causal_tool.py【改动】（源 = train_causal_probe.py，cprobe-env）

改动清单：数据路径、`calA`→`val`、只留 `--base qwen`。
**对齐检查那一段一字不改**（开训必过，FAIL 即 exit 2；--align-only 先单独跑一遍）。
超参照抄：lr 1e-5 / bs 4 事件 / accum 8 / epochs 3。

### 5.4 train_causal_callgen.py【新写】（cprobe-env）

**做什么**：把 Qwen3-0.6B-Base 微调成"看题干，生成完整调用串"。

- 模型：`AutoModelForCausalLM.from_pretrained(QWEN_PATH, dtype=torch.float32)`；
  tokenizer 照 build()【照抄 train_causal_probe.py】：pad=eos、
  `truncation_side="left"`、`padding_side="right"`。
- 一条训练实例 = 一条样本：输入串 = `text + CALL_SEP`，目标串 = `label_call + eos`。
- 构造（防左截吃掉目标）：先 tokenize 目标（不截断）得 `tgt_ids`（长度 L_t，
  超 160 token 的实例直接丢弃并计数）；再 tokenize 输入串，
  `max_length = 4096 - L_t`，左截；拼接 `input_ids = prompt_ids + tgt_ids`，
  `labels = [-100]*len(prompt_ids) + tgt_ids`。批内右 padding，pad 位 labels=-100。
- 损失：逐实例算目标段 mean CE，记 `ce_i`；批损失 = `Σ(w_i·ce_i)/Σw_i`
  （w 沿用样本的 1/m 事件等权）。
- 超参对齐 ctool：lr 1e-5、bs 4、accum 8、epochs 3、warmup 5%、clip 1.0、
  fp32 权重 + bf16 autocast、SEED 固定。
- 每 epoch 评估：val 全量 masked-CE（选 best 的唯一依据，越低越好）+
  从 val 定种子抽 200 条 greedy 生成（max_new_tokens=96，遇 `\n` 或 eos 停），
  报 `val_exact_call`（生成串 == label_call 的比例，只进日志不选 best）。
- smoke：500 / 200 / 1 epoch。日志事件名与旧脚本同构
  （start/step/eval/save_best/done；eval 行字段 `val_ce`、`val_exact_call`）。
- 产物：`best/`（save_pretrained + tokenizer + meta.json 记 base_path/data/
  max_len/seed/epoch/transformers 版本）。

### 5.5 12 run 矩阵（发射清单，执行手册 Phase C 引用）

| run_id | 脚本 | 解释器 | 数据 | 依赖 |
|---|---|---|---|---|
| c1_{q35,q36,gptoss}_mtool | train_mbert_tool.py | mbert-env | 各自 data_out | 无 |
| c1_{q35,q36,gptoss}_mext | train_mbert_extract.py | mbert-env | 各自 data_out + params | 无 |
| c1_{q35,q36,gptoss}_ctool | train_causal_tool.py | cprobe-env | 各自 data_out | 对齐检查过 |
| c1_{q35,q36,gptoss}_cgen | train_causal_callgen.py | cprobe-env | 各自 data_out | 无 |

12 个全独立可并行；单个约 1–2.5 小时（A6000）。**评测有依赖**：见 §6 开头。

## 6. eval 段

**依赖顺序**：先评 6 个 tool run（各自出 REPLAY_REPORT + logits），
再评 6 个参数 run（mext 用 mtool 的触发点，cgen 用 ctool 的触发点）。

### 6.1 eval_tool.py【改动】（源 = eval_replay.py）

改动清单（其余全部【照抄】：首次越阈回放、agg、经济换算、bootstrap、
stop-time 校准、深度十桶、先验基线、报告双格式）：
1. splits 循环 `("calA","calB","test")` → `("val","test")`；
   温度在 val 拟，θ 也在 val 扫（§2.5），test 冻结不变。
2. `--data` 指 `<data_out>`；`--run` 必填。
3. 评 causal run 时（`--head causal` 开关【新写】）：加载方式改为
   【照抄 train_causal_probe.py 的 CausalProbe + build()】，backbone 从
   `best/` 读、head 从 `best/head.pt` 读；打分时按事件整段一次前向、
   在每个边界位取 logits（复用其 collate 的定位逻辑）。cached-logits 路径不变。
4. `--legacy-splits` 开关【新写】：读旧的 calA/calB/test 并完全按旧逻辑跑
   （只为 §6.5 验收用）。

### 6.2 eval_mbert_call.py【改动】（源 = eval_extract.py + param_tiers.py 一起搬）

改动清单：`--data`/`--params` 指新目录、`calA`→`val`。
其余【照抄】：触发点取自 `--run`（mtool）的 REPLAY_REPORT 温度 + chosen_theta、
在触发前缀上跑抽取头、宽松/严格/整调用三档、三档分层（param_tiers 读
router_stats.md）。产 `EXTRACT_REPORT.{json,md}` 于 mext run 目录。

### 6.3 eval_causal_call.py【新写】（cprobe-env）

1. 输入：`--ctool-run`（读 REPLAY_REPORT.json 的 temperature 与
   chosen_theta["0.05"]，及 `logits_test.pt`）、`--cgen-run`、`--data`。
2. 触发点：【照抄 eval_extract.py 的 replay_fire()】在 test 堆上求每事件
   首次过 θ 的样本行。
3. 对每个触发事件：prompt = 触发样本 `text + CALL_SEP`，greedy 生成
   max_new_tokens=96，遇 `\n` 或 eos 停，得 `gen_call`。
4. 解析 gen_call：工具名用【照抄】AW_CALL（appworld）/BFCL_CALL（bfcl），
   参数用【照抄】split_args_named + 同一套归一化。解析失败记 `parse_fail`。
5. 判分（对照真值 = 触发样本的 label 与 args_named）：
   - `tool_ok` = 解析出的工具名 == label；
   - 参数逐个：**宽松** = 归一化后值相等；**严格** = 未归一化原串相等；
     键不匹配（多参/少参/名错）= 该参数错；
   - `params_all_ok` = 全部参数宽松对（无参事件恒真，单独成列）；
   - `full_call_ok` = tool_ok 且 params_all_ok。
6. 产 `CALLGEN_REPORT.{json,md}` 于 cgen run 目录：n_fired、tool_ok、
   parse_fail、params_all_ok（宽松/严格）、full_call_ok、无参事件占比，
   以及分工具 top10 明细表。

### 6.4 summarize_matrix.py【新写】（纯标准库）

读 12 个 run 目录的报告，输出 `pipeline/runs/MATRIX_REPORT.md`：
一张 12 行表（模型 × 格），列 = 风险 0.05 档的 coverage / trig_acc /
earliness / wrong_spec（tool 格），或 full_call_ok / params_all_ok（参数格），
外加每模型的 test 事件数与先验基线。缺报告的格标 `PENDING`。

### 6.5 验收（不过不许进 Phase C 发射）

零 GPU，复用旧缓存：

```
mbert-env/bin/python pipeline/eval/eval_tool.py --env bfcl \
  --run /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3 \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --cached-logits
```

判定：新产出的报告与 `envs/bert_runs/bfcl_v3/REPLAY_REPORT.json` 既有文件
逐字段比对，`temperature / chosen_theta / test_frozen` 三块**完全一致**
（把新报告写到临时目录，绝不覆盖旧文件）。输出 `ACCEPT_EVAL.md` 记录比对结果。

## 7. collect 段：gen_launch.py【新写】

输入：manifest json（执行手册 §3.2/§3.4 的两张表就是第一份 manifest 的内容）：

```json
{"run_id": "w0_aw_official",
 "servers": [{"host":"tokyo108","gpu":3,"model_key":"q35","port":8101,
               "session":"new1_w0_srv_q35a_t108g3","extra_flags":""}, ...],
 "clients": [{"tag":"q35tr","model_key":"q35","split":"train","num_shards":2,
               "shard_ports":[8101,8102],"outdir":"appworld_q35","exp":"w0q35tr"}, ...]}
```

输出三个文件到 `envs/runs/<run_id>/`：`launch_servers.py`（照
launch_vllm_topup.py 模板，环境变量三件套与 ssh+tmux 结构一字不差）、
`launch_clients.sh`（照 full_v2_topup/launch_clients.sh 的 tm()/aw() 结构）、
`MANIFEST.md`（人读的两张表）。模型权重路径与旗标查表写死在脚本里
（表在执行手册 §3.2）。**outdir 必须是 `appworld_<model_key>` 标准名**（§4.2 的坑）。
gen_launch 只生成不执行；执行由 gpu-run 流程按手册走。

## 8. inject 段：check_bundle.py【新写】

- `--run <dir> --data <data_out> --head {mbert,causal}`：
  按 `probe_server.py` 的 Probe 类同款方式加载（mbert：
  AutoModelForSequenceClassification of `best/` + label_map.json +
  REPLAY_REPORT.json 的 temperature；causal：CausalProbe 方式 backbone+head.pt）。
- 从 test.jsonl 读第一条样本，前向出 softmax，打印：预测工具、置信度、
  是否过 chosen_theta["0.05"]、真值。能跑通即凭证，写 `BUNDLE_CHECK.txt` 于 run 目录。
- CPU 可跑（`--device cpu`）。

## 9. 总验收清单（Phase C 发射前逐项打勾）

- [ ] §4.5 ACCEPT_V3DIFF.md：bfcl + appworld 两侧全 0
- [ ] §6.5 ACCEPT_EVAL.md：三块字段完全一致
- [ ] 三份配置的 data_out 都产齐 §4.4 清单里的 10 个文件
- [ ] 三个模型 train 堆 unit 集合相同、val=57 题、test=168 题
- [ ] 四格 smoke 各跑通（mtool/mext/ctool/cgen，ctool 含 ALIGN_CHECK PASS）
- [ ] check_bundle.py 对 smoke 产物跑通
- [ ] 全部新代码 commit，工作树干净
