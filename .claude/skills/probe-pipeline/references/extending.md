# extending — 接入新模型 / 新环境 / 新训练方法 / 新 split 的改动清单

本文件回答一件事:要在这条五段流水线上加**新的被探测模型**(§1)、**全新环境**(§2)、**新训练方法即新格**(§3)、**新 split 方法**(§4),到底要动哪些文件的哪几行,漏改会报错还是会静默出错;§5 是静默失败点总表,§6 是"改完之后怎么把新方法写回 skill"。
逐条结论都标了 `文件:行号`(2026-07-31 c1 批次的代码状态);流程说明在上一层 `SKILL.md`,照抄命令去同目录 `stage-commands.md`,判分口径去 `invariants.md`。

**横切一条(2026-08-02 起,四种情形通用)**:下面每一份必改清单都隐含最后一步——
把新脚本/新格/新配方挂进仓库根 `run.py` 的注册表(TASKS / RECIPES / CELLS /
EVAL_CELLS),同一个 commit 里完成,`python3 run.py selfcheck` 通过才算改完。
漏挂的后果是静默的:入口地图缺这一格,下一个人回到手翻文档考古的老路;
训练格漏挂更直接——`ops/launch_probe.py` 的格表就是从 run.py 的 `CELLS` import 的,
没挂 = 发射器不认识这个格。**评测格表的真源同样在 run.py,是它的 `EVAL_CELLS`**
(格 → `(run.py 任务名, 依赖的工具格|None)`),`ops/launch_eval.py` 只 import、
并从对应 TASKS 条目取解释器/脚本/固定参数,别处不许再抄一份同构表。

---

## 1. 情形 A:加一个新的被探测模型(同环境 appworld)

全流水线只有**三处**枚举了模型短名:`rules.py:18`、`gen_launch.py:47-54`、`summarize_matrix.py:67`。其余全部按 `--data` / config 走路径。

### 1.1 必改清单

| 文件:行 | 改什么 | 漏改的后果 | 改动量 |
|---|---|---|---|
| `pipeline/annotate/rules.py:18` | `MODEL_OF` 加一行 `"<key>": "<model_full>"` | `build.py:41-43` / `param_label.py:42-43` 拿 `MODEL_OF.get(目录名尾巴)` 认模型,取不到就 `continue` **静默跳过整个采集目录**;单模型建库时后续 `build.py:225-227` 会因"过滤后零事件"退 1(响),但同批别的模型照常出数 | 加一行 |
| `pipeline/collect/gen_launch.py:47-54` | `MODEL_TABLE` 加一条 `dict(served=, const=ZMODELS/YMODELS, weights=, family=)` | `gen_launch.py:93-94`(server)与 `105-107`(client)`die` 退 2,响 | 加一条 |
| `pipeline/collect/gen_launch.py:47-54` 的 `family` 字段 | 只有 `"qwen"` 与 `"gptoss"` 两族有分支 | ⚠️**静默**:`serve_flags()`(`gen_launch.py:172-177`)把非 qwen 一律当 gptoss 发旗标(只给 `--gpu-memory-utilization 0.92`,不给 tool-call parser);`gen_clients` 同理(`gen_launch.py:266`)会给它加 `--preset default`(2026-08-20 起走预设文件,展开后 = harmony / effort high / 温度 1.0 / top_p 1.0 / max_tokens 8192,预设在 `configs/presets/`)。生成的发射脚本能跑,只是服务端解析口径不对 | 新族要加一个分支 |
| 新建 `pipeline/configs/<BATCH>_<MODEL>.json` | 照抄 `pipeline/configs/aw_q35.json`(19 行),换 `model_short` / `model_full` / `data_out` 三处 | `model_full` 必须与 `MODEL_OF` 的值**逐字**相同,否则 `build.py:225-227` 退 1(响) | 新建一份 json |
| 新建 `pipeline/collect/manifest_<BATCH>.json` | 照抄 `pipeline/collect/manifest_w0.json`,加 `servers[]` 与 `clients[]` | 校验规则见 `gen_launch.py:86-122`(单机、端口/session/卡不重复、`len(shard_ports)==num_shards`、分片端口的模型必须对上),全部 `die` 退 2,响 | 新建一份 json |
| `pipeline/eval/summarize_matrix.py:82` | `--models` 默认表加新模型,或每次命令行显式传全 | ⚠️**静默**:不传就是这条默认表,新模型的四行**根本不出现在矩阵表里**,脚本退 0、stdout 也不提 | 改一行 / 命令行加参数 |
| `ops/<BATCH>_placement.json` | 照 `ops/c1_placement.json`(12 行)加四行(model/cell/host/gpu,ctool 那行带 `--align-tol`) | 排卡表是人读的输入,漏了只是重发时要重新推机位 | 加四行 |

### 1.2 不用改的(省得白费功夫)

- **四个训练脚本一个字都不用改**。`--env` 在训练侧**纯粹是日志标签**:四个脚本各有一条 `ap.add_argument("--env", default="appworld", …)`,`args.env` 的全部用处就是 `log(event="start", env=args.env, …)` 那一行,外加 mext 与 ctool 写 `best/meta.json` 时带上它——没有任何一处进入数据路径或损失。(**按 `--env` / `args.env` grep,不引行号:这批行号漂过。**)
- **底座权重常量不用改**:`train_mbert_tool.py` 与 `train_mbert_extract.py` 的模块级常量 `MODEL`(ModernBERT-base)、`train_causal_tool.py` 的 `MODELS` 表、`train_causal_callgen.py` 的 `QWEN`(**按常量名 grep,不引行号——这批行号漂过一次**)。这四个是**探针自己的骨架**,与被探测的 agent 模型无关。
- **四个 eval 脚本不用改**:模型全靠 `--run` / `--data` 指路径。
- **`pipeline/inject/check_bundle.py` 不用改**:全文无环境常量也无模型表,参数只有 `--run/--data/--head/--device/--dtype/--index/--temperature/--max-len`(全在它的 `main()` 里,grep `add_argument`)。
- **`pipeline/annotate/accept_v3diff.py` 不用改**:输入路径写死旧数据(模块级常量 `BASE` / `RUNS` / `V3`),它只负责证明新代码复现旧口径,不该跟着新模型走。
- `rules.py` 的 `AW_CALL`/`BFCL_CALL` 两个正则常量不用改——同环境同解析。

### 1.3 最短路径

1. 改 `rules.py:18` + `gen_launch.py:47-54`,写 config 与 manifest → **stage-commands §1** 生成发射器(先 `--dry-run --out-override`)。
2. **stage-commands §1** 正式生成 → 走 gpu-run 采集,验 outdir 名必须是 `appworld_<key>`(`gen_launch.py:117-122` 会强制改名并 WARN)。
3. **stage-commands §2**:`build.py` + `param_label.py`,各一次,同一份 config。
4. **stage-commands §3**:各格 `--smoke` → **§5** `check_bundle.py --device cpu` → 各格全量。
5. **stage-commands §4.1** 的依赖顺序:先 `eval_tool.py`(mtool/ctool),再 `eval_mbert_call.py` / `eval_causal_call.py`。
6. **stage-commands §4.2** 的 `summarize_matrix.py`,**记得带 `--models ... <新模型>`**。

---

## 2. 情形 B:加一个全新环境

### 2.1 必改清单

| 文件:行 | 改什么 | 漏改的后果 | 改动量 |
|---|---|---|---|
| `pipeline/annotate/build.py:135-148` | `collect_events` 加 `elif env == "<新env>"` 分支,指定 glob 模式 | `build.py:146` `raise SystemExit(f"未知环境")` 退 1,响 | 加一个分支 |
| `pipeline/annotate/param_label.py:114-130` | 同上,另一份独立的 `collect_events` | `param_label.py:124` 同样 SystemExit,响 | 加一个分支 |
| `pipeline/annotate/build.py:63-79` | `jsonl_events` 里的事件抽取:`63-69` 是 appworld 分支,`70-79` 是 else | ⚠️**静默**:else 是 **catch-all**,注释写着 tales,但**任何非 appworld 的 env 都会落进来**,拿到"命令首词 = 工具名、剩下整串 = 唯一参数"的语义。数据能造出来、报告也正常,只是标签口径全错 | 加一个分支 |
| `pipeline/annotate/param_label.py:56-69` | 同一处 catch-all,参数侧的副本 | 同上,且两份必须同口径,否则 `param_label.py:202` 的 `assert tool == r["label"]` 才会响 | 加一个分支 |
| `pipeline/annotate/build.py:50-51` | `unit` 派生:`env=="tales"` 用 `seed<n>`,其余用 `meta["task_id"]`,再退到文件名 | 新环境若 meta 里没有 `task_id`,unit 变成文件名 → 对不上题单 → `build.py:235-237` 退 1(响,但错误信息会指向题单而不是这里) | 加一个分支 |
| `pipeline/annotate/rules.py:55-56` | 调用正则。新环境的调用语法若既不是 `apis.x.y(` 也不是 `名字(`,要新增一条 | 正则不匹配 = 该步不产事件,**静默少样本** | 加一个常量 |
| `pipeline/eval/eval_causal_call.py:117-124` | `parse_call` 的 `name_re` 与工具名拼法,现在是"appworld 用 AW_CALL,**其余一律 BFCL_CALL**" | ⚠️**静默**:新环境走 BFCL_CALL 兜底,解析出来的工具名与真值对不上,`tool_ok` 全 false,数字整体塌陷,退出码 0 | 加一个分支 |
| 七处 `--env` 的 `choices` | `eval_tool.py:223-224`、`eval_mbert_call.py:108-109`、`eval_causal_call.py:196-197`、`train_mbert_tool.py:83-84`、`train_mbert_extract.py:212-213`、`train_causal_tool.py:231-232`、`train_causal_callgen.py:180-181` | argparse 直接拒绝,响 | 七处各加一个字符串 |
| `pipeline/collect/gen_launch.py` 的 `ENV_TABLE` | 加一条 `"<新env>": dict(venv=, runner=, fn=, common=)`——`venv` = `envs/<venv>/venv` 下的解释器、`runner` = `envs/collect/` 下的采集器文件名、`fn` = 生成的 sh 里那个函数叫什么、`common` = 该环境的统一客户端参数(如 `--n 0 --max-steps 50`) | `load_manifest` 校验 `cfg["env"]` 必须在 `ENV_TABLE` 里,不在就 `die` 退 2,**响**。客户端生成段 `gen_clients` 与清单生成段 `gen_manifest_md` 都只查这张表,表里有了就自动出对的 sh,不用改代码 | 加一条 |
| config 的 `official_split_files`(`aw_q35.json:12-16`) | 三份 txt,每行一个 unit id | `build.py:190-205` 读它切分;有 unit 不在任何题单 → `build.py:235-237` 退 1(响),**换环境时最先炸的就是这条** | 三个路径 |

### 2.2 要新写的东西

| 新写什么 | 照抄哪个模板 | 硬约束 |
|---|---|---|
| 采集器 `envs/collect/run_<env>.py` | `envs/collect/run_appworld.py`(124 行)或 `run_tales.py`(102 行) | 必须用 `envs/collect/common.py:94-104` 的 `TrajLog`:首行 `type:"meta"`(带 `task_id`)、逐步一条 `type:"gen"`(字段 `step`/`reasoning`)+ 一条 `type:"env"`(字段 `step`/`action`/`result`)、末行 `type:"final"`。`build.py:46-47` 按 `type` 分桶,`:55-56` 只认 `reasoning` 与 `action` |
| 落盘命名 | `run_appworld.py:75`/`:82` | 目录 `<env>_<model_key>`(尾巴要能被 `MODEL_OF` 认出)、文件 `<env>_<id>.jsonl`;`build.py:140` 的 glob 是 `appworld_*/appworld_*.jsonl`,新环境要给出对应的一对 |
| gen_launch 的客户端函数 | **不用写**——`gen_clients` 已经参数化,函数名取 `ENV_TABLE[env]["fn"]`、解释器取 `["venv"]`、采集器取 `["runner"]`、统一参数取 `["common"]`,`outdir` 统一拼 `<env>_<model_key>`(`load_manifest` 里的 `std = f"{env}_{c['model_key']}"` 强制,非标准名只 WARN 并改掉) | 所以这一格的活是 **§2.1 里给 `ENV_TABLE` 加一条 + 本节上一行写 `envs/collect/run_<env>.py`**,**不是**再复制一个 `aw()` 出来。`MANIFEST.md` 里 outdir 那句说明也是从 `cfg["env"]` 拼的,跟着自动对 |
| 若"工具"不是函数调用形(如 ALFWorld 的自然语言动作) | 无现成模板 | `label_call` 的拼法(`build.py:158-162` 的 `make_call`)与参数切分(`rules.py:106-152` 的 `split_args_named`/`first_call_named`/`mkparams`)整套要重定义,`eval_causal_call.py:138` 那条"切法必须与 rules 一致"的 assert 也要跟着改。**这是情形 B 里唯一一块真正的设计工作,其余都是加分支** |

### 2.3 最短路径

1. 先解决题单:拿到新环境的官方 train/val/test 三份 id 清单(`build.py:190-193` 只要求"每行一个 id、去空行")。**这一步不落地就别往下走**,`build.py:235-237` 会全量报错。
2. 写采集器 → 手跑 1 题验轨迹格式(首行 meta 有 task_id、末行 final)。
3. 给 `gen_launch.py` 的 `ENV_TABLE` 加一条(不用改客户端生成代码) → **stage-commands §1** `--dry-run` 看生成的 sh 对不对 → 正式采集(gpu-run)。
4. 改 annotate 五处分支(collect_events ×2、jsonl_events ×2、unit 派生)+ 正则 → **stage-commands §2** 建库;`ANNOTATE_REPORT.md` 的工具词表与频率先验基线是第一道人眼验收。
5. 改七处 `choices` + `eval_causal_call.py:117-124` → **stage-commands §3 / §4** 照常跑,训练与 eval 主体不动。
6. `accept_v3diff.py` 对新环境**没有对照旧数据**,G8 那道门在新环境上无效——要另想验收办法(见 §7)。

### 2.4 先验成本估计(只数代码,不估工时)

- **要新写的文件:2 类** —— 1 个采集器(`envs/collect/run_<env>.py`,模板 102–124 行)、每模型 1 份 config(19 行)+ 1 份 manifest。
- **要加的分支:11 处** —— `build.collect_events` 1、`build.jsonl_events` 1、`build` 的 unit 派生 1、`param_label.collect_events` 1、`param_label.jsonl_events` 1、`rules` 正则 1、`eval_causal_call.parse_call` 1、`gen_launch.ENV_TABLE` 加一条(**是查表不是写分支**)1、`gen_launch.MODEL_TABLE`(若同时换模型)1,外加 `--env choices` 7 处(算 1 处批量改)、`summarize_matrix --prefix/--models` 1。
- **一行不动的:5 个文件** —— 四个训练脚本 + `inject/check_bundle.py`。`eval_tool.py` 与 `eval_mbert_call.py` 也只动 choices 一行。
- **风险集中度**:11 处分支里有 4 处漏改**不报错**(见 §5 的 #5 #6 #7 #10),其余漏改都会当场退非 0。

---

## 3. 情形 C:加一种新训练方法(新格)

"格" = 骨架 × 头。现状五格(m 线两格 2026-08-21 起停跑,仍可单发;因果三格的
底座 2026-08-21 起扩成三档 `--base qwen/qwen17/qwen4`,三个脚本各一份同构
`MODELS` 表,没有单一真源,加档要改三处):

**行号一律不引**(这批漂过一次):下表的定位靠常量名与日志事件名 grep——选 best 的判断都在 `log(event="eval", …)` 之后那个 `if`,存盘都在紧跟着的 `log(event="save_best", …)` 之前。

| 格 | 脚本 | 骨架 | 头 | 选 best 的指标 | `best/` 存盘格式 |
|---|---|---|---|---|---|
| mtool | `train_mbert_tool.py` | ModernBERT(常量 `MODEL`) | 序列分类 | val 加权 acc(日志字段 `calA_weighted_acc`,越大越好) | HF 目录(`save_pretrained`)+ tokenizer + `label_map.json` |
| mext | `train_mbert_extract.py` | ModernBERT(常量 `MODEL`) | span 抽取(start/end/可答) | val 参数 acc(日志字段 `calA_param_acc`,越大越好) | **裸 state_dict** `best/model.pt`(`torch.save(model.state_dict(), …)`)+ tokenizer + `meta.json` |
| ctool | `train_causal_tool.py` | Qwen3 三档(常量 `MODELS`,`--base` 必填) | 线性头挂末位隐状态 | val 加权 acc(日志字段 `calA_weighted_acc`,越大越好) | backbone HF + `head.pt` + `label_map.json` + `meta.json` |
| cgen | `train_causal_callgen.py` | Qwen3 三档(常量 `MODELS`,`--base` 默认 qwen) | 语言建模(直接写整条调用) | val 加权 masked-CE(日志字段 `val_ce`,**越低越好**) | HF 目录 + tokenizer + `meta.json` |
| cparam | `train_causal_param.py` | Qwen3 三档(常量 `MODELS`,`--base` 默认 qwen) | 语言建模(给定工具名与左括号,只写参数段;目标从 `label_call` 按 `label+"("` 前缀剥离,对不上整条丢弃计 `assembly_mismatch`) | val 加权 masked-CE(日志字段 `val_ce`,**越低越好**;`val_exact_params` 只进日志) | HF 目录 + tokenizer + `meta.json`(含 `param_only: true`) |

⚠️ **先分清"新格"与"新训法轴",清单只对前者**。np821 加的 `--lora` 不是新格:
格没变(还是 ctool/cgen/cparam)、数据没变、评测脚本一行没改,变的只是底座怎么训。
这类扩展**不走 §3.1 的必改清单**(不用新写训练脚本、不用登记 `CELLS` /
`EVAL_CELLS` / `summarize_matrix` 的三张表),要做的是三件:① **实现收在一个共用
模块里**——LoRA 收在 `pipeline/train/lora_util.py`,三个因果格共用旗标、默认值、
target modules,别处不许再抄一份(同构表必漂移,而那种漂移是静默的);② **存档
契约不许变**——LoRA 存 `best/` 之前先 `merge_and_unload` 并回底座再
`save_pretrained`,`best/` 与全参训练存的逐项同构,四个评测脚本零改动装得回;
③ **新轴写进 run_id 的批次前缀而不是格名**(§3.4 的 run_id 那条)。新格才往下走 §3.1。

**"换实现"也不走 §3.1,先例是 2026-08-28 的 `train_causal_share.py`**:格名(还是 cgen/cparam)、数据不改,四个评测脚本判分一字不改、输入构造第二轮加了 `--overlong` 一个开关(默认 `left` 时逐字段不变,spec 16.2),只换训练脚本本身(旧逐行前向换成一个事件一次前向、共享前缀)。判据和"新训法轴"一样看**格/数据/评测有没有变**——变的只是"用什么脚本训出这个格",不是"多训了一种法子"或"加了一个新格",所以也不登记 `CELLS` / `EVAL_CELLS` / `summarize_matrix` 三张表(只需要把已登记的 `CELLS`/`TASKS` 条目**指向新脚本**,不是新增一行);旧脚本冻结为对齐参照,经专门的 `<格>-rows` 任务发射,产物不进矩阵(见 §5 #26)。第二轮(工单 07-10)加的 `--overlong` / `--gen-eval` / `--align-rule` / `--mem-probe-pick` 四个开关也是同款"换实现不算新格"的先例:全是参数,默认值等于推荐值(spec 16.1 的表),不新增格、不登记三张表。

### 3.1 必改清单

| 文件:行 | 改什么 | 漏改的后果 | 改动量 |
|---|---|---|---|
| 新建 `pipeline/train/train_<新格>.py` | 模板选法见 §3.2 | —— | 新写 180–372 行(四个现成脚本的行数区间) |
| 仓库根 `run.py` 的 `CELLS`(训练格表唯一真源) | 加一行 `"<格名>": (解释器, 脚本绝对路径, base_args)`,并把格名加进 `CELL_ORDER` | `ops/launch_probe.py` 从 run.py import 这张表,`build()` 里 `CELLS[cell]` KeyError,响;顺带 `TASKS` 也要加一条 `train-<格名>`,否则 `run.py` 里没有这个任务 | 加一行 |
| 仓库根 `run.py` 的 `EVAL_CELLS`(评测格表唯一真源) | 加一行 `"<格名>": ("<eval 任务名>", "<依赖的工具格>" 或 None)` | `ops/launch_eval.py` 从这里 import 并据此排依赖顺序,漏挂 = 排卡发射器发不出这个格的评测 | 加一行 |
| `pipeline/eval/summarize_matrix.py:24` | `CELLS` 元组加格名 | ⚠️**静默**:新格四行**根本不进矩阵表**,脚本退 0、stdout 不提 | 加一项 |
| `pipeline/eval/summarize_matrix.py:25-27` | `REPORT_OF` 加 `"<格名>": "<报告文件名>.json"` | `read_cell` 在 `:37` `REPORT_OF[cell]` KeyError,响 | 加一项 |
| `pipeline/eval/summarize_matrix.py:41-73` | 取数的四分支 | ⚠️**静默**:新格落到 `:70-73` 的 else,按 `params_all_ok`/`full_call_ok` 取字段,名字对不上就 `rep.get()` 全 None → 表里一整行 `-`,状态列却写着 `OK` | 加一个分支 |
| `pipeline/inject/check_bundle.py:82-160` + `:165` | 加一个 Bundle 类 + `--head` 加一个 choice | 两个现成类都要求 `best/label_map.json` 并让 `probs()` 吐类别分布(`:104-110`、`:145-160`);非分类头拿现成类装会当场崩(响)。不加 = **这个格没有 inject 凭证**(mext/cgen 现在就是这个状态) | 加一个类(约 40 行) |

### 3.2 能照抄什么、不能照抄什么

**四个训练脚本之间几乎不共享代码**,全流水线只有一处真 import:`train_mbert_tool.py:30` 的 `from input_modes import apply_mode`(`pipeline/train/input_modes.py`),**只有 mtool 一个格用**——所以 `--input-mode`(`train_mbert_tool.py:96-98`)也只有 mtool 有。其余全是各自复制粘贴:

| 部件 | 四份各在哪 | 抄的时候注意 |
|---|---|---|
| `SEED` 常量 + `torch.manual_seed`/`random.seed` | 每个训练脚本一份模块级 `SEED`(另有 `rules.py` 第五份),按常量名 grep;设种子紧跟在 argparse 之后 | **各脚本一份独立常量,没有单一真源**,而且 np821 起**取值已经分家**:`rules.py` 与三个因果脚本换成种子家族首位 **42**,两个 mbert 脚本(m 线停跑)仍是 20260729。新格照它所在那条线的现值写死,别照抄本表里的数字;换种子家族要全仓 grep 一遍取值点 |
| `collate()` 与 Dataset 类 | `collate` mtool`:56` / mext`:124` / ctool`:98` / cgen`:76`;数据集 `JsonlDS`(mtool`:36`)/ `InstDS`+`join_rows`(mext`:63`)/ `load_events`+`EventDS`(ctool)/ `CallDS`(cgen`:58-63`) | 八份签名各不相同,一律不能复用;按"新格吃什么标签"挑最近的抄 |
| `train_log.jsonl` 的 `log()` 闭包 | mtool`:132-138` / mext`:265-267` / ctool`:313-315` / cgen`:234-236` | 一律 `open(..., "a")` **追加模式**;事件名约定 `start`/`step`/`eval`/`save_best`/`done`,新格不照这套写,读日志的人和 job-monitor 都认不出 |
| 心跳 emit(`ops/heartbeat.py`) | 五个训练脚本、四个 eval 脚本、`run_appworld.py` 已接(`import heartbeat` / `heartbeat.emit` grep 定位,不引行号;`run_tales.py`/`run_alfworld.py`/`run_tau2.py` 尚未接) | **新采集/训练/评测脚本必须接 `ops/heartbeat.py`(进主循环 emit(0,...),每单位 emit,收尾 status=done),不接的脚本在窗口里永远是 warm-up 中** |
| smoke 限额 | mtool`:118`、mext`:247`、cgen`:210` 都是 500/200 **实例**;ctool`:269` 是 200/80 **事件** | 新格自己定,定完写进 stage-commands §3 的表 |
| 日志字段旧名 | `calA_weighted_acc`(mtool`:168`)、`calA_param_acc`(mext`:323`)、`best_calA_weighted_acc`(ctool`:368`) | 堆名早已是 val,字段名故意保留旧的 `calA_*`(规格 `plans/2026-07-31-pipeline-engineering.md:330` 明令"保持原名不改,下游按名读") |

**模板怎么选**:换头不换骨架 → 抄同骨架那两个里更近的一个(ModernBERT 线抄 mtool/mext,Qwen 线抄 ctool/cgen);换骨架不换头 → 抄同头那一个,只改权重常量与加载方式;**新目标函数** → 抄 cgen,它是四个里损失最独立的(masked-CE,`:13-14`)。

### 3.3 评测侧:四个评测脚本的适用边界

| 脚本 | 只吃什么 | 新格能不能复用 |
|---|---|---|
| `eval_tool.py` | 任何**分类头**:要 `best/label_map.json`(`:253`);mbert 分支走 `AutoModelForSequenceClassification`(`:270-272`),causal 分支 `from train_causal_tool import CausalProbe`(`:69-70`) | 分类头 + 现有两种骨架之一 → **一行不用改直接复用**;新骨架 → 在 `:255-272` 加第三个 `--head` 选项 |
| `eval_mbert_call.py` | **只吃 mext**:`:28-29` 直接 `from train_mbert_extract import FIND, collate, decode, load_extractor, span_ok` | 换头就得换 import,等于新写 |
| `eval_causal_call.py` | **只吃 cgen**:`:238-249` 按 HF CausalLM 装 `best/`,`:239` 从 meta 读 `call_sep` | 同上;它也是最独立的,新写评测脚本抄它 |
| `eval_causal_param.py` | **只吃 cparam**:meta 没有 `param_only: true` 即 SystemExit(格保险丝,防误喂 cgen run——那样工具名会被写两遍,数字静默变形)。同一批 ctool 触发点跑两口径:gt_tool 喂真值工具名(纯填参能力)、pred_tool 喂分类头 argmax(系统乙真实数字),判分前重组 `工具名+"("+生成串` 再走 cgen 同一套 parse/判分 | 2026-08-21 照 eval_causal_call.py 抄出来的先例;矩阵四列只读 pred_tool 块 |

三个 call 脚本的共同结构:从工具格 `REPLAY_REPORT.json` 取温度与 θ(`eval_mbert_call.py:125-130`、`eval_causal_call.py:495-497`、`eval_causal_param.py:328-330`),再靠 `logits_test.pt` 的行数 assert 对齐(`:139` / `:569` / `:397`)。新的"依赖格"照这个结构写。

### 3.4 依赖关系与门禁

- **独立格 vs 依赖格**:mtool/ctool 只吃数据集,互不依赖;mext/cgen 要吃**同模型工具格**的触发点(`eval_mbert_call.py:140`、`eval_causal_call.py:229` 的 `replay_fire`)。新格只要是"在触发点上评",就必须排在工具格之后,顺序照 stage-commands §4.1。
- **对齐检查(G13)只对因果骨架有意义**:`--align-only` / `--align-tol` 与 FAIL 时的 `sys.exit(2)` 只在 `train_causal_tool.py:229-244` 区;**cgen 用同一个骨架却没有这套检查**(grep `align` 在 callgen 无命中)。新格是因果骨架且要做增量投机 → 该抄;是 encoder 骨架 → 不需要。**smoke(G14)** 判据是 `train_log` 有 start 与 done + ckpt 能存能读 + 能被 `check_bundle.py --device cpu` 装起来(stage-commands §5),所以 §3.1 里那个 Bundle 类不是可选项。("loss 在降"这一项 smoke 规模上判不了,新格照抄"每 50 gstep 写一条 `event=step`"的写法就会同样判不了,见 gates §1 的 G14 行。)
- **run_id 没有底座档位段,也没有训法段**(`{batch}_{model}_{cell}`):同一格换 `--base` 档或换训法重训会撞 rid,两次产物无法归属。约定**一个训练批次只跑一档底座 + 一种训法**,两者都写进批次前缀(p1 线的 p1b06/p1b17/p1b4;np821 线的 np821b06/np821b17/np821l17/np821l4,`b`=全参、`l`=LoRA),换档换训法一律在排卡表 extra 里写 `--base <档>` / `--lora`(2026-08-21 定档位,np821 加训法轴)。**驱动器不读批次配置里的 `base`/`mode` 字段**,排卡表 extra 才是真源。**"换实现"同理写进批次前缀**(§3 开头的先例):2026-08-28 起的新口径(丢弃规则、上限、更新单位都变了)前缀是 `ks828` 加档位训法段,如 `ks828b06`、`ks828l17`;`np821` 前缀不许再用于新口径的 run,两条口径的数字不可比(stage-commands §3.2)。**学习率扫描的 run_id 是四段**(`sweep_lr.py`,spec 16.6,工单 11):`ks828<tag>_gptoss_cgen_lr<lr>`,比这里的三段 `{batch}_{model}_{cell}` 多一段;产物落 `pipeline/runs/sweep/`,不进矩阵、不进 `summarize_matrix`(stage-commands §3.2 同款说明)。
- **run_id 对格名几乎没有约束**:拼接点三处(`ops/launch_probe.py:67` 的 `rid = f"{batch}_{model}_{cell}"`、`summarize_matrix.py:75` 的 `rid = f"{args.prefix}_{m}_{c}"`、排卡表的 `cell` 字段),两处查表都是精确匹配(`launch_probe.py:66` 的 `CELLS[cell]`、`summarize_matrix.py:22` 的 `REPORT_OF`),**没有任何代码反解 run_id**(未读到反解逻辑)。格名含下划线不会崩,只会让 `ops/launch_probe.py:112`(smoke 档)/`:123`(full 档)拼的 session 名人读歧义。建议单段小写。
- **显存按"开不开 `--grad-ckpt`"估,不按模型大小估**:np821 实测 0.6B 全参**不带** gc 的峰值(60–77 GiB)比 1.7B 全参**带** gc(35–44 GiB)高一倍,LoRA + gc 又低一档(17–38 GiB)。四档形态的实测峰值表在 `stage-commands.md §3.1`,挑卡前查它;两次踩坑的经过见 `gates.md §3.9`(smoke 过了全量仍 OOM)与 `§3.10`(0.6B 全参在 48G 上三格全 OOM)。

### 3.5 最短路径

1. 先答"改的是骨架还是头" → 按 §3.2 末段选模板 → 写训练脚本 → 双环境 `py_compile` → `--smoke` 跑一遍(**stage-commands §3**),看 loss 与 `best/` 落盘。
2. 加 `check_bundle.py` 的 Bundle 类 → `--device cpu` 验产物(**stage-commands §5**)。
3. 按 §3.3 判能不能复用 `eval_tool.py`;不能就照 `eval_causal_call.py` 新写(**stage-commands §4**)。
4. 四处登记:`summarize_matrix.py:24-27`、仓库根 `run.py` 的 `CELLS`+`CELL_ORDER`(训练格表真源)、同文件的 `EVAL_CELLS`(评测格表真源)、`ops/<batch>_placement.json`。
5. **回写 skill(§6)**。

---

## 4. 情形 D:加一种新 split 方法

现状:切法的唯一实现是 `build.py:190-205`(`read_unit_list` + `official_split`),`main()` 在 `:231` 调它一次;**此后全流水线再没有第二处做过切分**。

### 4.1 `split_mode` 的真实结论:声明了但没接线的字段,不是能用的开关

- 三份 config 都写了 `"split_mode": "official"`(`pipeline/configs/aw_q35.json:11`、`aw_q36.json:11`、`aw_gptoss.json:11`),规格的 schema 示例里也有(`plans/2026-07-31-pipeline-engineering.md:102`)。
- **但全仓库没有任何代码读它**(grep `split_mode` 只命中上面四处)。`build.py:214-219` 从 cfg 只取 `env`/`model_full`/`traj_runs`/`data_out`/`seed`;`official_split()`(`:196-205`)直接拿 `cfg["official_split_files"]`,不看 mode。
- 结论:它是**规格里给这件事留的名字,实现时没接线**。接线很便宜——在 `build.py:231` 前加一个按 `cfg.get("split_mode", "official")` 的分发,官方切法原样保留,新切法各写一个返回同样 `(part, lists)` 的函数。

### 4.2 必改清单

| 文件:行 | 改什么 | 漏改的后果 | 改动量 |
|---|---|---|---|
| `pipeline/annotate/build.py:196-205` | 新写 `<mode>_split(cfg, events)`,返回契约必须与 `official_split()` 完全一致:`(part: unit→堆名, lists: 堆名→unit 集合)` | 契约不一致时,`:231-237` 的 missing 判定、`:249-250` 的不跨 split 自检、`:254` 的分桶、`:266` 的题单归属抽查会各自崩在不同地方(响,但报错信息会指向错的地方) | 加一个函数 |
| `pipeline/annotate/build.py:231` | 按 `cfg["split_mode"]` 分发 | ⚠️**静默**:不分发就永远走官方切法,config 里写了新 mode 也没人理,数据照造 | 加三行 |
| `pipeline/annotate/build.py:32` `SPLITS` | 堆名或堆数要变时 | `:256` 按它写文件、`:262` 按它抽查;**`param_label.py:31` 另有一份独立的同名常量**,两处不同步 → `param_label.py:191-193` 去读不存在的 `<堆>.jsonl`,FileNotFoundError(响) | 两处各改一行 |
| `pipeline/annotate/build.py:202-204` | 新切法若可能产生堆间重叠,要加一条重叠 assert | ⚠️**静默**:现状是 `part[u] = name` 后写覆盖、**零重叠检查**(详见 §5 #4) | 加一个 assert |
| `pipeline/annotate/build.py:260-267` | 官方切法专用的自检 3 | ⚠️**静默**:随机/分层切法下 `lists` 是自己造的,`assert u in lists[name]`(`:266`)**恒真**,自检形同虚设却照样在报告里打 ✓(`:341-342`) | 换一条自检 |
| `pipeline/configs/*.json` 的 `split_desc` | 报告里"规则"行与"切分"行的文案从这个字段取(`bfcl_mtb_v1` 批次接的线),默认值 = 旧说法"官方题单,任务实例级" | ⚠️**静默**:不写这个字段就照打"官方题单",`ANNOTATE_REPORT.md` 自己撒谎。`check_callstr.py` 门禁 E 已把这条静默变成硬拦(条件:题单目录的 `SPLIT_REPORT.json` 里 `official_split_exists: false`) | 写一个 json 字段 |

### 4.3 下游对堆名的硬依赖(全部按文件名假设 split 的地方)

| 位置 | 读哪堆 |
|---|---|
| 四个训练脚本 | 写死 `train.jsonl` + `val.jsonl`:mtool`:120-121`、mext`:252-253`(经 `join_rows`,`:66`+`:68` 同时开 `<data>/<split>.jsonl` 与 `<params>/<split>.jsonl`)、ctool`:274`+`:298`、cgen`:215-216` |
| `eval_tool.py:245-251` | 新口径 `("val","test")`,legacy `("calA","calB","test")`;`fit_sp` 与 `sweep_sp` 都是 val |
| `eval_tool.py:274-291` | 按 `split_names` 循环,顺带把 logits 存成 `logits_<sp>.pt` |
| `eval_tool.py:314` | **`splits["test"]` 写死**——不管 `split_names` 怎么变,必须有一堆叫 test |
| 三个下游脚本 | 写死 `test.jsonl`:`eval_mbert_call.py:134`(另加 `:144` 的 `params/test.jsonl`)、`eval_causal_call.py:223`、`check_bundle.py:197` |

**堆数不是 3 会在哪崩**:K 折切法把 K 个堆写进同一个目录后,四个训练脚本只认 `train.jsonl`/`val.jsonl`(FileNotFoundError,响),`eval_tool.py:314` 只认 `test`(KeyError,响)。→ 可行做法是**每折造一个独立的 `data_out` 目录**(折内仍叫 train/val/test),这样下游一行都不用改,run_id 里带折号即可。

### 4.4 评测三步对 val/test 的硬依赖,以及旧字段名

`eval_tool.py:293-325` 三步全写死:温度在 `fit_sp`(=val)拟(`:294-295`)、θ 在 `sweep_sp`(=val)扫(`:298-311`)、冻结在 `"test"`(`:314`)。少 val → `:276` 读文件即崩(响);少 test → `:314` KeyError(响)。**没有"只有 train/test 两堆"的降级路径**,新切法必须保证至少两堆、且其中一堆叫 test。
另外 `eval_tool.py:356` 的 `theta_sweep_calB` 与 `:366` 的 `calB_sweep` 沿用旧堆名、实际扫的是 val,训练日志的 `calA_*` 同理(见 §3.2 末行);规格 `plans/2026-07-31-pipeline-engineering.md:330` 明令保留旧名给下游按名读。换 split 方法后这些名字会**更**误导(随机切之后还叫 calB),要改就得同步改读的一侧并写进 `invariants.md`。

### 4.5 最短路径

1. 先答两个问题:堆数是不是 3、其中一堆是不是叫 test。都是 → 只动 `build.py`;否 → 按 §4.3 末段改造成"一折一目录"。
2. `build.py`:加切法函数 → `:231` 加分发 → 换掉 `:260-267` 的自检 → 改 `:329-333` 的文案;`param_label.py:31` 的 `SPLITS` 跟着改(它**不重做切分**,只按堆名读 build 的产物,`:191-193`)。
3. 重建库,用 `ANNOTATE_REPORT.md` 的三堆实例数核对(**stage-commands §2**)。
4. 新 split = **新数据集版本号**(SKILL.md Phase 0 的 `<DATA_ROOT>`),旧数字一律不可比 → 回写 `invariants.md §2` + `TIMELINE.md`。

### 4.6 环境根本没有官方 train/val/test 分区时怎么办(ALFWorld + bfcl 两个先例)

**先别急着写新切法函数**。§4.1–§4.5 那整张必改清单(新写切法函数、`:231` 加分发、换掉自检 3)只在"切的规则要变"时才触发。环境没有官方分区≠要换切法——**把题单一次性定下来写成 txt,仍走 `official_split()`,清单整张都不触发**。两个先例都是这么做的:

| | ALFWorld(`alf_official_v1`) | BFCL(`bfcl_mtb_v1`) |
|---|---|---|
| 官方给什么 | 三个分区目录(train / valid_seen / valid_unseen),但**不给 id 清单文件**,官方枚举方式是 `os.walk`,遍历序跨机不保证一致 | **什么都不给**。本机 `bfcl_eval==2026.3.23` 的 `BFCL_v4_multi_turn_base.json` 实测 200 条,字段只有 `['excluded_function','id','initial_config','involved_classes','path','question']`,**无 split 字段**;`TEST_COLLECTION_MAPPING` 全是 test 集合。它是纯评测榜 |
| 题单怎么来 | `pipeline/collect/gen_alfworld_splits.py`:val/test 取官方两个分区全量,train 在官方 train 里六类等比例分层抽样 | `pipeline/collect/gen_bfcl_splits.py`:**冻结老线 v3_1 已经用过的那三堆**(`envs/bert_data/v3_1/bfcl/` 的 train / calA∪calB / test → 140/40/20),不重新 shuffle |
| 为什么这么选 | 官方分区本身就是 train/val/test,只有 train 需要抽样(原始分布倾斜) | 为了**保住与老数字的同场地**:test 那 20 题原封不动,新因果头数字与 `RESULTS.md` 里老分类头的 bfcl 数字落在同一块地上 |

**bfcl 这条路上踩到的三件事,下次照抄**:

1. **"重新执行老规则"不等于"复现老切分"**。老脚本 `envs/collect/build_dataset.py:224` 的 rng 是三个环境**共用**、bfcl 排在 appworld/tales 之后,随机数状态已被前两个环境消耗掉。实测 `random.Random(20260729).shuffle(sorted(units))` 复现出的 test 与老 test 只重合 1/20。要保可比性只能**读老产物的 unit 字段反推**,不能重跑规则。
2. **题单的推导源可能不在 git 里**。bfcl 的推导源是 `envs/bert_data/v3_1/bfcl/*.jsonl`,而 `.gitignore` 只放 `envs/bert_data/**/*.md` 进库——那四个 jsonl 删了就再也推不出来。所以**入库的 txt 是唯一真源**,`SPLIT_REPORT.json` 里记的 md5 只是审计线索、不是"能一键重生成"的承诺。`gen_bfcl_splits.py` 为此加了一道门禁:已入库的 txt 与本次算出的不同时**拒绝覆盖**,要覆盖得显式 `--force`。
3. **题单落哪**:`pipeline/splits/<批次>/`。别放 `envs/<env>/splits/`——`.gitignore` 把 `envs/bfcl/`、`envs/appworld/`、`envs/tales/` 整目录当第三方 clone 忽略,题单放进去不入库(alfworld 是自建目录、`.gitignore` 专门为 `envs/alfworld/splits/` 开了口子,所以它在那儿是对的)。工程里因此有两个题单落点,新环境一律用 `pipeline/splits/`。

**必写的四道门禁**(`gen_bfcl_splits.py` 里全是 `sys.exit` 硬拦,照抄):① 三堆两两无交集(对应 §5 #4:`official_split` 是后写覆盖、零重叠检查);② 三堆并集 == 官方全集文件的 id 全集且无多余(**没有官方分区也几乎总有一个"官方全集"文件可以当锚**,这是唯一能拿到的外部校验);③ 每堆行数硬核对(G9);④ 不静默覆盖已入库的题单。

**又添两个先例(2026-08-02,tau2_official_v1 / toolhop_v1,四道门禁照抄)**:

- **tau2 = 第三种情形:官方有 train/test 但没有 val**(三域 `split_tasks.json`
  实测 train∩test=0、train∪test==base)。处理:官方 test 原封冻结,val 从官方
  train 抽官方 test 的**半数**,抽剩当 train;门禁 ② 之外加一条"各域本堆 test
  逐字 == 官方 test"的冻结承诺。SPLIT_REPORT 的 `official_split_exists` 记
  **false**(val 不是官方堆),借门禁 E 逼 config 写诚实的 `split_desc`。
- **toolhop = 纯自切**(995 条平铺列表、无 split 字段):比例对齐 bfcl 的
  70/20/10,按 `answer_type` 六类分层、每层配额最大余数法。分层键只挑**干净的
  枚举字段**——它的 `domain` 字段是大小写混乱的自由文本('Film'/'film' 并存),
  当分层键就是自欺。
- **抽样种子一律按子集独立派生** `random.Random(f"{SEED}:{domain或层名}")`,
  不共用一个 rng 流——共用流的死法 bfcl 那条(上文第 1 件)已实测:任何一个
  子集的规模变了,后面全部对不上。

---

## 5. 静默失败点总表

报错的坑会自己暴露,静默的不会。下面每一条都是"改错/漏改之后脚本照常退 0,只是数字变了或样本少了"。

| # | 位置 | 触发条件 | 症状 |
|---|---|---|---|
| 1 | `build.py:41-43` / `param_label.py:42-43` | 采集目录名尾巴(`rsplit("_",1)[1]`)不在 `MODEL_OF` | **整个目录被跳过**。同批其他模型照常出数;补采时新起了个不同名目录(如 `appworld_gptoss2`)最容易中招 |
| 2 | `build.py:40-41` | 轨迹写进了别的模型的 outdir | **模型张冠李戴**。模型归属**只看目录名**;`run_appworld.py:82-84` 写进 meta 的 `model` 字段全流水线无人读过(grep 无消费方) |
| 3 | `build.py:140` | 文件名不是 `appworld_*.jsonl` | glob 不命中,**静默少样本** |
| 4 | `build.py:196-205` | 三份官方题单之间有重叠 unit | `part[u]=name` 按 `SPLITS=("train","val","test")` 顺序后写覆盖,**test 最后写赢**,全程无重叠检查 → 划分静默变形、train/test 边界失守 |
| 5 | `build.py:70-79` / `param_label.py:63-69` | 新 env 复用 `jsonl_events` 但没加分支 | else 是 catch-all,**任何非 appworld 都拿 tales 的"动词=工具名"语义**,数据照造 |
| 6 | `rules.py:18` | 两个 key 映到同一个 `model_full` | `build.py:225` 的过滤把两批轨迹**静默合并**,直接破"永不合并同族"的口径(SKILL.md Phase 0) |
| 7 | `eval_causal_call.py:155-157` / `eval_causal_param.py:149-151` | `--env` 传错 | 只换正则不报错。appworld 数据传 `--env bfcl`,`apis.spotify.login(` 会被解析成工具 `login`,**tool_ok 全 false、数字整体塌陷**。注意:同一个 `--env` 在 `eval_tool.py`(只用于 `:239` 的 legacy 路径拼接与 `:355`/`:380` 的标题)和 `eval_mbert_call.py`(只用于 `:210`/`:225` 的标题字段)里**纯属标签**——四个 eval 里只有 `eval_causal_call.py` 与 `eval_causal_param.py` 两个真影响判分 |
| 8 | `summarize_matrix.py:82` | 忘了给 `--models` 加新模型 | 该模型全部格**整体不出现在表里**,退 0 且 stdout 不提示 |
| 9 | `summarize_matrix.py:53-73` + `108-111` | 某个参数格是在 `--risk 0.1` 下跑出来的 | `--risk` 只作用于 tool 格的 `test_frozen[risk]`(`:42`);参数格两列**无条件读该 run 的报告**,而 `EXTRACT_REPORT.json` / `CALLGEN_REPORT.json` / `PARAM_REPORT.json` 是单文件覆盖写 → 0.05 档的表里会混进 0.10 档的数 |
| 10 | `gen_launch.py:172-177` + `:266` | 新模型 `family` 既不是 qwen 也不是 gptoss | 走 else,**按 gptoss 发服务旗标与客户端旗标**,发射脚本照常生成 |
| 11 | 四个训练脚本的 `--env` | 传错 | 只污染 `train_log.jsonl` 与 `best/meta.json` 的标签,数字不受影响(反向的静默:看日志的人会被误导) |
| 12 | `pipeline/configs/*.json` 的 `split_mode` 字段 | 改它 | **全流水线没有任何代码读这个字段**(grep 无命中),纯装饰。`bfcl_mtb_v1` 那三份 config 写的是 `"frozen_v3_1"`,同样没人读——它只是给人看的标记。**真正被读的是同批新加的 `split_desc`**(`build.py` 报告文案从它取,见 #18) |
| 13 | `eval_causal_call.py:228` / `eval_mbert_call.py:139` | 跨模型串 run 与 data | 唯一的防线是 `len(rows) == logits.shape[0]` 的形状 assert;两个模型的 test 行数**恰好相等**时就静默串味 |
| 14 | `summarize_matrix.py:24` | 加了新格没往 `CELLS` 登记 | 新格**整体不进矩阵表**,退 0 且 stdout 不提(与 #8 同源:这个脚本的两张表全靠常量枚举) |
| 15 | `summarize_matrix.py:70-73` | 新格的报告字段名不叫 `params_all_ok` / `full_call_ok` | 落进 else 分支,`rep.get()` 全取到 `None` → 表里一整行 `-`,**状态列却写着 OK**,比 PENDING 更容易被当成"跑出来就是这么差" |
| 16 | `build.py:231` | config 里写了新 `split_mode` 但没在这里加分发 | **永远走官方切法**,配置形同虚设,数据照造照出报告 |
| 17 | `build.py:260-267` | 新切法沿用官方切法的自检 3 | `lists` 是新切法自己造的,`assert u in lists[name]` 恒真,自检失效却照样在 `:341-342` 打 ✓ |
| 18 | `build.py` 的两行报告文案 / `eval_tool.py:356` `:366` | 换了切法没改文案与字段名 | 报告里写着"官方题单"、字段叫 `theta_sweep_calB`,数字却来自别的切法/别的堆。**已部分接线**(`bfcl_mtb_v1` 批次):`build.py` 的"规则"行与"切分"行都改成从 `cfg.get("split_desc", "官方题单,任务实例级")` 取,不写该字段的 config 保持旧说法;`check_callstr.py` 门禁 E 会**硬拦**"SPLIT_REPORT.json 说没有官方分区、报告里却印着『官方题单』"这种撒谎。`eval_tool.py` 那两个 `calB` 旧字段名**仍未动**(规格明令保留给下游按名读) |
| 19 | `train_mbert_tool.py:30` `:96-98` | 拿 `--input-mode` 做 T5 消融 | `apply_mode` **只有 mtool 一个格 import**;其余各格连这个参数都没有(传了会被 argparse 拒,响),但"各格一起做消融"这件事会**静默只做成一格** |
| 20 | `build.py:101`(`runs.glob("bfcl_*")`)+ config 的 `traj_runs[]` | `traj_runs` 写成 run 目录的**父目录**(如 `/envs/runs` 而不是 `/envs/runs/full_v1`) | glob 只在该目录**平级**找 `bfcl_*`,于是命中的是 21 题的 smoke 批次 `envs/runs/bfcl_q35/`;若父目录与正确的 run 目录**同时**列进 `traj_runs`,smoke 批次的 traj 名(`bfcl_q35/<id>`)与全量批次逐字相同,同一批 event key **重复进库**、退 0、无告警,只是样本数悄悄涨。实测 bfcl q35 从 11094 涨到 12395 样本(+1301),报告里三堆实例数全都还是 140/40/20,肉眼看不出来。防线:`check_callstr.py` 门禁 C(traj_runs 项下不许再有嵌套 run 目录)+ 门禁 B(`(event, sent_idx)` 全局唯一、一个 unit 只对一条 traj) |
| 21 | `build.py:154-156`(`make_call`)对 `eval_causal_call.py:83-116`(`split_named_raw`) | 真值参数值里含**逗号** | `make_call` 是 `", ".join(f"{k}={v}")` 手拼、**不加引号**,eval 侧按顶层逗号切 → 一条真值被切成 `k=前半` + `pos0=后半`,`params_all_ok` / `full_call_ok` 被**静默压低**,生成侧写得再对也拿不到分。实测(`check_callstr.py` 全量算的,不是抽样;两批都是三模型加总):bfcl 3325 事件里 **83 条回读失败(2.50%)**、5027 个参数实例里 229 个含逗号(4.56%);appworld 16030 事件里 **76 条(0.47%)**、24674 个参数实例里 104 个含逗号(0.42%)。所以 bfcl 的参数侧数字天生比 appworld 难看 **约 5.3 倍**,原因是 bfcl 的工具里有 `send_message` / `resolve_ticket` / `post_tweet` 这类自由文本参数,而 appworld 的参数多是 id 与短字段。`rules.py` 的 ALFWorld 有 `ALF_BAD_CHARS` 逗号闸门专门拦这件事,appworld / bfcl 都没有;**不要单给一个环境补闸门**(appworld 的 c1_* 十二格已按无闸门口径上账,补了就不是一把尺子)。防线:`check_callstr.py` 偏差 1 逐批量出天花板,写进 `CALLSTR_CHECK.md` |
| 22 | `eval_mbert_call.py:274`(`pick_theta`,`eval_causal_call.py` 同款) | 拿 `self_fire.theta_sweep_val` 扫描表对着 risk 找"达标行"来判有没有解 | 选 θ_fire 的真实约束是 `fire_acc ≥ 1-risk`(开火**精度**),而扫描表里的 `wrong_fire_rate` 是按**全事件**归一的另一个数——后者 ≤ risk 时该档照样可能 null。ro1 批实测:bf_q36_mext 在 θ=0.95 处 wrong_fire_rate 0.09 ≤ 0.1 但 fire_acc 只有 0.78,0.1 档判 null 是**正确行为**;不知道这条的人会把它当 bug 去"修",一修就换了契约 |
| 23 | `pipeline/driver.py` 的 `step_e2_call` / `step_m1_matrix`(按函数名 grep) | 手发了评测(`launch-eval`)、报告还没落地时敲 `run.py pipeline`;或某批 call 档报告没齐就先出了那批矩阵 | 两条都退 0、都不报警。① `e2_call` 的判据只有"报告文件在不在"加"它自己的发射标记在不在",**不查台账里在飞的 eval 任务**——手发的那批两样都不满足,于是**再发一遍**,两个进程写同一份报告;② `m1_matrix` 见 `MATRIX_<批>_r{0.05,0.1}.md` 已存在**就跳过**,所以报告没齐时出的那张带 PENDING 的早产表会**永久留着**,后面再敲驱动器也不重出,读表的人拿到的是缺格的旧数。防线:**G23**(敲驱动器前确认手发的评测不在飞)与 **G24**(出矩阵前确认该批报告齐) |
| 24 | `pipeline/driver.py` 的 `step_t2_full`(docstring 里写着这个场景) | 对**部分完成**的批再敲 t2_full(比如删了 `launched` 标记想补一格) | 它重发整张排卡表,已完成的格撞训练脚本的"同 out 已有 `train_log.jsonl`"守卫秒退,**但登记在守卫之前就做了**:那个早跑完的 run 被补一条假 RUNMETA、run_id 被塞回台账 active,而 `launch_probe` 发没发都退 0。台账多个不会自己消失的僵尸条目,追溯链里多一条没跑过的命令。补一格的正确做法见 `stage-commands.md §3`(只含那一格的临时排卡表) |
| 25 | `train_causal_tool.py` 的 `collate` 与 `eval_tool.py` 的 `score_causal`(2026-08-28 前的读取位置循环:`for t in range(keep-1, -1, -1): if 0 < ends[t] <= b`) | 切点前的 token 跨过切点(token 起始位置 < 切点 < 结束位置)并且切点到结束位置之间的字符全是空白 | 约 6.3% 的切点读到句尾标点前一个词的隐状态(草稿 4.4 实测)。训练侧 `collate` 与离线评测侧 `score_causal` 用的是同一段旧循环,两边内部一致,数字不报错也不互相矛盾,肉眼看不出偏差。2026-08-28 起两处都改走 `share_data.read_position`,读取位置和全文一次分词的边界一致——**这只修了训练/离线评测这一段,不许写成"活跑错位已修"**:活跑时模型自己生成的 token 边界和离线全文分词的边界可能不同(比如活跑先出 `."\n` 再出 `\n`,离线合成一个 `."\n\n`),那是分词边界的另一个坑,这一轮没有解决(spec 11.3 末段) |
| 26 | `run.py` 的 `train-cgen-rows` / `train-cparam-rows`(指向冻结的旧逐行脚本 `train_causal_callgen.py` / `train_causal_param.py`) | 拿这两个任务发射出的 run 目录去评测、进矩阵 | 走的是旧口径(`--max-len 4096`、逐行左截、3 个 epoch),产物 `best/meta.json` 没有 `trainer` 字段,run_id 形状和现役 `train-cgen`/`train-cparam` 相同(`<批次>_<model>_cgen` / `<批次>_<model>_cparam`);评测脚本与 `summarize_matrix.py` 都不检查 `trainer` 字段,混进矩阵之后**分不出这一行数字来自哪个训练器**——8192、不截断、1 epoch 的现役口径和 4096、左截、3 epoch 的参照口径会被当成同一批数字 |
| 27 | `pipeline/train/share_data.py` | 在 mbert-env(transformers 4.57.6)下 import `share_data`,而它的模块顶层直接 import 了 `train_causal_callgen` / `train_causal_param`(这两个旧脚本模块层有版本门) | `eval_tool.py` / `eval_mbert_call.py` 在 import 阶段直接 `SystemExit`,表现是"`eval-tool-mbert` 开跑即死",容易被误判成"解释器用错了?"——实际是 `share_data` 把旧脚本的版本门带进了 mbert-env。根因修复(工单 01 已按此实现):`share_data` 模块顶层只留 stdlib + torch,对这两个旧脚本以及 `rules.MAX_BOUNDS` 的 import 全部延迟到 `load_events` 函数体内 |
| 28 | `eval_causal_call.py` / `eval_causal_param.py` 的 `drop-event` 计数与 `eval_tool.py` 的 `overlong_mode` | cgen/cparam 用某一种 `--overlong` 跑,而 ctool 评测用的是另一种(比如 ctool 用 `drop-event` 丢过事件、cgen/cparam 却用 `left`) | ctool 已丢的事件在 cgen/cparam 那边根本不存在触发点,cgen/cparam 看到的是 `n_excluded_by_ctool` 非零而不是自己的 `n_dropped_events` 涨——两份报告各记各的 `overlong_mode`,不对着一起看会把"ctool 丢过的事件"错当成"cgen/cparam 自己判定超长"(spec 16.2) |
| 29 | `train_causal_share.py` 的 `--gen-eval` 生成段(`model.generate`) | 生成调用被套进 `_attn_ctx(dev)` 上下文 | `generate` 不带 4D 掩码、HF 走 `enable_gqa=True`,mem-efficient 内核不接 GQA,报 `No available kernel`;工单 08 的守卫测试(`ast` 找 `_attn_ctx(` 的调用点,只许落在前向 `_forward_packed` 与反向 `backward_logical_minibatch` / `_fwd_bwd_block` 三处,生成路径永远不许)专防这个回归 |
| 30 | `share_data.py` 的行元组(`load_events` 行元组从 0 数的第 6 位 `gen` 字典,与代码注释同一记法)与手造行元组的测试 | 手造行元组只给 6 位,缺第 6 位 `gen = dict(tgt=..., tool=...)` | `pack_event` 的拆包已经是 `row[:6]`,7 位元组不会报 `ValueError`,但 `--gen-eval` 拿不到 `gen` 字段做抽样与目标串,生成式评估要么静默漏行要么在别处报 `KeyError`;新测试手造行元组必须带全 7 位 |
| 31 | `train_causal_share.py` 的 `run_mem_probe` 系(`_mem_probe_tokens`/`_mem_probe_cost`/`_mem_probe_loop`) | 探针前后不保存/恢复 `random`/`torch`/`torch.cuda` 的随机数状态 | LoRA dropout 消耗的随机数流被探针多跑的那几次前反向偷走,带 `--mem-probe` 与不带的两次训练 `train_log.jsonl` 的 `loss` 不再逐条相同(不挂 `--lora` 时 dropout=0,这条测不出区分度) |
| 32 | `_mem_probe_loop` | 每组更新(lr 置 0 的 `opt.step()`)后不 `opt.state.clear()` | AdamW 的 `exp_avg`/`exp_avg_sq`/`step` 计数照写不误,lr=0 只保证参数值不变、不保证优化器状态不变;不清空的话探针之后的正式训练从一个非空优化器状态起步,和真实"从头训"的轨迹不一致 |
| 33 | `eval_tool.py` 的 `--cached-logits` | 用不同 `--overlong` 跑出的 `logits_<sp>.pt` 行数刚好相同(三种模式都写全行数,行数不随模式变) | 旧缓存(没有 `overlong_mode` 键的 `.meta.json`)按 `left` 处理;`.meta.json` 记的 `overlong_mode` 与本次 `--overlong` 不同时已用硬停堵住(不同就 `SystemExit`)——这里记的是为什么要有这道硬停:`skip`/`drop-event` 剔掉的是不同下标,行数相同但内容不同的两份缓存会互相冒充 |
| 34 | `eval_tool.py` 的 `drop-event`(取事件全文走 `train_causal_tool.py` 的规则:先按 `label in label2id` 过滤行再取最后一行文本)与 `eval_causal_call.py`/`eval_causal_param.py` 的 `drop-event`(取事件全文走 `share_data.event_full_texts`,不过滤行直接取 `sent_idx` 最大那行文本) | 一个事件里最大 `sent_idx` 的那一行 label 不在词表里 | 两边在这种情况下取到的不是同一段"全文",`dropped_events` 计数也可能不同;每个评测脚本只跟自己的训练器同规则,不能拿 ctool 的丢弃数去推 cgen/cparam 会不会丢同一个事件(冒烟里两边巧合相同不代表规则相同) |
| 35 | `eval_tool.py` 的 `--overlong skip`/`drop-event` 与 `summarize_matrix.py` | ctool 评测用非 `left` 模式跑,报告进矩阵 | `skip`/`drop-event` 改变 `n_events_scored`(`summarize_matrix.py` 读 pred_tool 块用它),矩阵里看不到 `overlong_mode`,不同模式的 run 混进一张矩阵分不出口径;矩阵只收 `left` 的评测,其他模式的数只进各自的报告(spec 16.10 #35) |
| 36 | `train_causal_share.py` 的 `mem_probe_summary`(`scope=run`) | `--mem-probe-pick cost`/`loop` 配 `--smoke` 或 `--max-events` 跑探针,拿 `worst_gb` 去排全量的卡 | `scope=run` 的 `worst_gb` 只覆盖本次 run 抽样出的事件,`--smoke` 取的是全文 token 数最短的 40 个事件,量到的是最小块;排全量的卡要用 `scope=full`(`tokens`)的数(spec 16.10 #36;第二轮 b06 smoke2 的 cost worst 15.35 GB 对全集 tokens 探针 54.38 GB) |
| 37 | `train_causal_share.py` 的 `.backward()`(`backward_logical_minibatch`/`_fwd_bwd_block`)配 `--grad-ckpt` | 只把前向套进 `_attn_ctx`(mem-efficient 内核),`.backward()` 在上下文外 | 梯度检查点的重算发生在 `.backward()` 里,重算走默认内核选择(cuDNN),保存的张量元数据对不上,torch 报 `CheckpointError: Recomputed values ... have different metadata`(2026-08-28 l4 冒烟 `ks828l4_gptoss_cgen_smoke` 在探针第一次反向就崩;b06 开检查点同样会撞);`.backward()` 也套 `_attn_ctx`,守卫测试允许的调用点是前向一处加反向两处,生成路径仍不许套(spec 16.10 #37,提交 b5cee8d) |

---

## 6. 回写本 skill

这条 skill 是活的:**任何一次用它加了新东西,收尾时必须把新东西写回文档**,否则下一次调用还是按旧方法走,而且下一个人读到的清单是错的。照下表打勾。

| 你这次做了什么 | 更新哪份文档的哪一节 | 更新什么内容 |
|---|---|---|
| 加了新模型 | `extending §1` / `stage-commands §0` | §1 的三处枚举表补上新短名;§0 若引入了新权重目录,补一行路径 |
| 加了新环境 | `extending §2` / `SKILL.md` Phase 0 的 `<ENV>` 行 / `stage-commands §1 §2` | §2 的分支清单标注"这个环境已接";Phase 0 的候选环境列表加名;§1 的 outdir 命名规则、§2 的 config `env` 字段取值同步 |
| 加了新格 | `extending §3` / `SKILL.md` Phase 0 的 `<CELLS>` 行与 Phase C4 的依赖图 / `stage-commands §3 §4` | §3 的格表加一行(骨架/头/best 格式/选 best 指标四列都要填);§3 的命令表加一条真实跑过的命令;§4 的依赖顺序图标出新格排在哪一层 |
| 加了新训法轴(格没变,只换底座怎么训,如 LoRA) | `extending §3` 开头的"新格 vs 新训法轴" + `§3.4` 的 run_id 行 / `stage-commands §3` 的旗标表与 §3.2 / `invariants §3` | §3 写清共用模块在哪、存档契约有没有变;§3.4 补一句新轴写进批次前缀;旗标表补 flag 行;invariants 记死新轴的超参默认值 |
| 实测了硬件占用(显存峰值、装不装得下) | `stage-commands §3.1` 的显存表 / `gates §3` 加案例 / `gpu-run` 的 `references/launch-methodology.md` Step 2 | 表里按"底座档 × 训法 × 开不开 gc"一行,写峰值与结论;OOM 有故事的进 gates §3;gpu-run 那侧只留一句结论加指路,细表不抄第二份 |
| 实测了某一段的墙钟 | `stage-commands` 对应段的耗时参考(eval 是 §4.5) | **先写清这一段按什么计数**(事件?触发事件?样本行?),再给量与分钟数——不写单位的分钟数下一批就用错 |
| 加了新 split 方法 | `extending §4` / `invariants.md §2` | §4.1 的 `split_mode` 结论从"没接线"改成"已接线,取值有 X/Y";invariants §2 记录新切法的口径与"与旧数字不可比"这句 |
| 改了任何写死的口径 | `invariants.md` 对应节 + `TIMELINE.md` | invariants 改数;TIMELINE 追加一条说明"为什么改、改之前的数字作废到什么程度" |
| 踩了一个新坑 | `gates.md §3` 加一个案例 / 本文件 §5 加一行 | 坑会报错 → 进 gates §3;坑**不报错** → 必须进 §5 静默总表,并写清"症状长什么样" |
| 新加了门禁 | `gates.md §1` 总表加一行 | 编号顺延,同时在 SKILL.md 对应 Phase 里引用 |
| 改了脚本接口(加/删/改 flag、改产物路径) | `stage-commands` 对应节 + `stage-commands §7 接口陷阱` | 参数表改字段;新增的不对称行为(产物写向、覆盖语义)进 §7 |

**原则一:什么该进 skill,什么是这批次一次性的事。** 判据是"下一批次还会不会碰上"。**进 skill**:改了代码接口、加了新分支、发现了一个静默失败点、定下了一条新口径、新增了一道门禁——这些下一批次一定会再遇上。**不进 skill**:某次排卡表怎么分的(`ops/<batch>_placement.json` 自己留档就够)、某个 run 跑了多久、某次某张卡坏了、某个模型这一批的具体数字——这些属于 `RESULTS.md` / `TIMELINE.md` / `ops/jobs.json`。一句话:**skill 只收"方法",不收"这批的结果"**。边界情形——同一个坑第二次踩到,不管当时觉得多偶然,一律进 skill。

**原则二:回写时机是"当场记、收尾写"。** 发现的当下先在批次计划 `plans/<日期>-<batch>-plan.md` 里记一行原始现象(哪个文件哪一行、什么症状),因为细节两小时后就丢了;正式改 skill 放在 Phase D 收官时一并做,和 `record.py finish` / TIMELINE 补条同一轮。理由:实验跑到一半改 skill,会让"这批用的到底是哪版方法"说不清——skill 的改动必须和批次收官在同一个 commit 边界上。

**原则三:回写必须 commit,且和数字分开。** skill 的改动跟着 Phase D 第 6 步的收官 commit 一起进库即可,但 commit message 里要**单独点名**改了哪几节,让人从日志能查到方法是哪一版——`skill: probe-pipeline 补 <批次> 的方法改动——extending §3 加 <格名> 格 / §5 新增静默点 #23 / gates 新增 G23`。如果这一批只改了 skill 没出数字(例如只是清点),那就单独一个 `skill:` 前缀的 commit,不要混进 `exp:` 或 `data:`。

⚠️ **门禁编号 G1–G24 已占用,新门禁从 G25 起顺延,不许复用旧号**——SKILL.md 与本文件都按号引用,复用旧号会让两处指向不同的东西。(G19–G22 是 `check_callstr.py` 那批;G23–G24 是 np821 批加的"驱动器与手发评测混用"两道,见 `gates.md §1`。)

---

## 7. 未解之处

- **非 qwen / 非 gpt-oss 的第三种服务旗标**没有现成模板。`gen_launch.py` 只有 `QWEN_FLAGS_SRC`(`:57-59`)与 `GPTOSS_SERVE_FLAGS`(`:61`)两套,新族(如 Llama 的 tool-call parser)该配什么旗标,本仓库未读到。
- ~~ALFWorld 在本仓库不存在~~ → **已接入,这条作废**。`envs/alfworld/`(自建目录,含 `data`/`splits`/`venv`/`logs`)已在位;`run.py` 里有 `collect-alf`(解释器 `envs/alfworld/venv/bin/python`,脚本 `envs/collect/run_alfworld.py`)与 `gen-alf-splits`(`pipeline/collect/gen_alfworld_splits.py`,官方三个分区目录抽题单,做法见 §4.6 左栏);`rules.py` 也已有 ALFWorld 的 `ALF_BAD_CHARS` 逗号闸门(§5 #21)。⚠️ 遗留一点:`gen-alf-splits` **没有防覆盖门禁**(run.py 该任务的 notes 原话是"重跑直接改写已入库 txt",别的三个 `gen-*-splits` 都有 `--force` 门禁)。另注:`gen_launch.py` 的客户端生成段是**查 `ENV_TABLE`** 的(常量 `ENV_TABLE`,现有 `appworld` / `alfworld` 两条,各带 venv/runner/fn/统一参数;`gen_clients` 与 `gen_manifest_md` 都按 `cfg["env"]` 取),加新环境 = 往这张表加一条 + 写对应 `run_<env>.py`,§2.1/§2.2 已按此写。
- ~~一个环境是否必须配一个采集器,存疑~~ → **bfcl 就是反例,已确认**。bfcl 没有自己的采集器,`build.bfcl_events` 直接读外部 BFCL 工具产出的原生结果文件:`<traj_run>/bfcl_<模型>/**/*multi_turn*result.json`,逐行 json、按 `entry["id"]` 去重,事件从 `entry["inference_log"]` 里扁平化出的 `(role, content, reasoning_content)` 三元组抽。本轮实测的两个 run 目录是 `envs/runs/full_v1`(q35 + q36)与 `envs/runs/full_v2_topup`(gptoss),合计 200 题 × 3 模型 = 595 条有事件的轨迹 / 3325 事件。同目录下的 `bfcl_<模型>_score/` 是评分目录,靠 `MODEL_OF.get(rsplit("_",1)[1])` 取不到模型而被跳过(不是靠白名单)。
- **tales 链路未验证**。`eval_causal_call.py:119` 对 tales 走 `BFCL_CALL`,而 tales 的标签是动词、`label_call` 由 `build.py:158-162` 拼成 `verb(arg=...)`,形式上能对上,但 c1 批次没跑过 tales 的 cgen 格,未实测。
- **新环境下 G8(ACCEPT_V3DIFF)失效**。`accept_v3diff.py:24-25`/`:108` 把输入路径与环境列表写死成 `("bfcl","appworld")` 的旧数据,新环境没有旧数据可复现,这道门该换成什么验收,规格里未读到。
- **非分类头的 inject 凭证没有定义**。`check_bundle.py:165` 只有 `mbert`/`causal` 两个选项,两个 Bundle 类都以"吐类别分布 + 查 `label_map.json`"为接口(`:104-110`、`:145-160`),所以 **mext 与 cgen 两个格至今没有 BUNDLE_CHECK**。抽取头/生成头的"能装起来"该怎么验(生成一条?抽一个区间?),规格里未读到。
- **K 折 / 留一法的 run_id 与记账约定未读到**。§4.3 建议的"一折一目录"会让 run 数翻 K 倍,折号写进 run_id 的哪一段、`ops/jobs.json` 与 `record.py` 怎么归并同一折的多个 run,现有文档里没有相关约定。
