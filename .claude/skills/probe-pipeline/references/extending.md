# extending — 接入新模型 / 新环境的改动清单

本文件回答一件事:要在这条五段流水线上加一个**新的被探测模型**或一个**全新环境**,到底要动哪些文件的哪几行,漏改会报错还是会静默出错。
逐条结论都标了 `文件:行号`(2026-07-31 c1 批次的代码状态);流程说明在上一层 `SKILL.md`,照抄命令去同目录 `stage-commands.md`,判分口径去 `invariants.md`。

---

## 1. 情形 A:加一个新的被探测模型(同环境 appworld)

全流水线只有**三处**枚举了模型短名:`rules.py:18`、`gen_launch.py:47-54`、`summarize_matrix.py:67`。其余全部按 `--data` / config 走路径。

### 1.1 必改清单

| 文件:行 | 改什么 | 漏改的后果 | 改动量 |
|---|---|---|---|
| `pipeline/annotate/rules.py:18` | `MODEL_OF` 加一行 `"<key>": "<model_full>"` | `build.py:41-43` / `param_label.py:42-43` 拿 `MODEL_OF.get(目录名尾巴)` 认模型,取不到就 `continue` **静默跳过整个采集目录**;单模型建库时后续 `build.py:225-227` 会因"过滤后零事件"退 1(响),但同批别的模型照常出数 | 加一行 |
| `pipeline/collect/gen_launch.py:47-54` | `MODEL_TABLE` 加一条 `dict(served=, const=ZMODELS/YMODELS, weights=, family=)` | `gen_launch.py:93-94`(server)与 `105-107`(client)`die` 退 2,响 | 加一条 |
| `pipeline/collect/gen_launch.py:47-54` 的 `family` 字段 | 只有 `"qwen"` 与 `"gptoss"` 两族有分支 | ⚠️**静默**:`serve_flags()`(`gen_launch.py:172-177`)把非 qwen 一律当 gptoss 发旗标(只给 `--gpu-memory-utilization 0.92`,不给 tool-call parser);`gen_clients` 同理(`gen_launch.py:266`)会给它加 `--api chat --reasoning-effort high`。生成的发射脚本能跑,只是服务端解析口径不对 | 新族要加一个分支 |
| 新建 `pipeline/configs/<BATCH>_<MODEL>.json` | 照抄 `pipeline/configs/aw_q35.json`(19 行),换 `model_short` / `model_full` / `data_out` 三处 | `model_full` 必须与 `MODEL_OF` 的值**逐字**相同,否则 `build.py:225-227` 退 1(响) | 新建一份 json |
| 新建 `pipeline/collect/manifest_<BATCH>.json` | 照抄 `pipeline/collect/manifest_w0.json`,加 `servers[]` 与 `clients[]` | 校验规则见 `gen_launch.py:86-122`(单机、端口/session/卡不重复、`len(shard_ports)==num_shards`、分片端口的模型必须对上),全部 `die` 退 2,响 | 新建一份 json |
| `pipeline/eval/summarize_matrix.py:67` | `--models` 默认表加新模型,或每次命令行显式传全 | ⚠️**静默**:不传就是这条默认表,新模型的四行**根本不出现在矩阵表里**,脚本退 0、stdout 也不提 | 改一行 / 命令行加参数 |
| `ops/<BATCH>_placement.json` | 照 `ops/c1_placement.json`(12 行)加四行(model/cell/host/gpu,ctool 那行带 `--align-tol`) | 排卡表是人读的输入,漏了只是重发时要重新推机位 | 加四行 |

### 1.2 不用改的(省得白费功夫)

- **四个训练脚本一个字都不用改**。`--env`(`train_mbert_tool.py:83-84`、`train_mbert_extract.py:212-213`、`train_causal_tool.py:231-232`、`train_causal_callgen.py:180-181`)在训练侧**纯粹是日志标签**——全部用处只有 `train_mbert_tool.py:140`、`train_mbert_extract.py:273` 与 `321`(写 meta.json)、`train_causal_tool.py:321`/`364`、`train_causal_callgen.py:242`,没有任何一处进入数据路径或损失。
- **底座权重常量不用改**:`train_mbert_tool.py:32`、`train_mbert_extract.py:37`(ModernBERT-base)、`train_causal_tool.py:49-50`(`MODELS` 表)、`train_causal_callgen.py:40`(`QWEN`)。这四个是**探针自己的骨架**,与被探测的 agent 模型无关。
- **三个 eval 脚本不用改**:模型全靠 `--run` / `--data` 指路径。
- **`pipeline/inject/check_bundle.py` 不用改**:全文无环境常量也无模型表,参数只有 `--run/--data/--head/--device/--dtype/--index/--temperature/--max-len`(`check_bundle.py:162-174`)。
- **`pipeline/annotate/accept_v3diff.py` 不用改**:输入路径写死旧数据(`accept_v3diff.py:24-25`),它只负责证明新代码复现旧口径,不该跟着新模型走。
- `rules.py:55-56` 的 `AW_CALL`/`BFCL_CALL` 不用改——同环境同解析。

### 1.3 最短路径

1. 改 `rules.py:18` + `gen_launch.py:47-54`,写 config 与 manifest → **stage-commands §1** 生成发射器(先 `--dry-run --out-override`)。
2. **stage-commands §1** 正式生成 → 走 gpu-run 采集,验 outdir 名必须是 `appworld_<key>`(`gen_launch.py:117-122` 会强制改名并 WARN)。
3. **stage-commands §2**:`build.py` + `param_label.py`,各一次,同一份 config。
4. **stage-commands §3**:四格 `--smoke` → **§5** `check_bundle.py --device cpu` → 四格全量。
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
| `pipeline/collect/gen_launch.py:226-275` | 整个客户端生成段写死 appworld:`aw()` 函数体调 `envs/collect/run_appworld.py`(`:258`)、统一参数 `CLIENT_COMMON`(`:66`)、`outdir` 强制 `appworld_<model_key>`(`:117-122`) | 生成的 `launch_clients.sh` 会去跑 appworld 采集器,响(采集器自己会崩) | 改一段(约 40 行) |
| config 的 `official_split_files`(`aw_q35.json:12-16`) | 三份 txt,每行一个 unit id | `build.py:190-205` 读它切分;有 unit 不在任何题单 → `build.py:235-237` 退 1(响),**换环境时最先炸的就是这条** | 三个路径 |

### 2.2 要新写的东西

| 新写什么 | 照抄哪个模板 | 硬约束 |
|---|---|---|
| 采集器 `envs/collect/run_<env>.py` | `envs/collect/run_appworld.py`(124 行)或 `run_tales.py`(102 行) | 必须用 `envs/collect/common.py:94-104` 的 `TrajLog`:首行 `type:"meta"`(带 `task_id`)、逐步一条 `type:"gen"`(字段 `step`/`reasoning`)+ 一条 `type:"env"`(字段 `step`/`action`/`result`)、末行 `type:"final"`。`build.py:46-47` 按 `type` 分桶,`:55-56` 只认 `reasoning` 与 `action` |
| 落盘命名 | `run_appworld.py:75`/`:82` | 目录 `<env>_<model_key>`(尾巴要能被 `MODEL_OF` 认出)、文件 `<env>_<id>.jsonl`;`build.py:140` 的 glob 是 `appworld_*/appworld_*.jsonl`,新环境要给出对应的一对 |
| gen_launch 的客户端函数 | `gen_launch.py:256-262` 的 `aw()` | 复制成 `<env>()` 或参数化;`MANIFEST.md` 里 outdir 那句说明在 `:316` |
| 若"工具"不是函数调用形(如 ALFWorld 的自然语言动作) | 无现成模板 | `label_call` 的拼法(`build.py:158-162` 的 `make_call`)与参数切分(`rules.py:106-152` 的 `split_args_named`/`first_call_named`/`mkparams`)整套要重定义,`eval_causal_call.py:138` 那条"切法必须与 rules 一致"的 assert 也要跟着改。**这是情形 B 里唯一一块真正的设计工作,其余都是加分支** |

### 2.3 最短路径

1. 先解决题单:拿到新环境的官方 train/val/test 三份 id 清单(`build.py:190-193` 只要求"每行一个 id、去空行")。**这一步不落地就别往下走**,`build.py:235-237` 会全量报错。
2. 写采集器 → 手跑 1 题验轨迹格式(首行 meta 有 task_id、末行 final)。
3. 改 `gen_launch.py` 客户端段 → **stage-commands §1** `--dry-run` 看生成的 sh 对不对 → 正式采集(gpu-run)。
4. 改 annotate 五处分支(collect_events ×2、jsonl_events ×2、unit 派生)+ 正则 → **stage-commands §2** 建库;`ANNOTATE_REPORT.md` 的工具词表与频率先验基线是第一道人眼验收。
5. 改七处 `choices` + `eval_causal_call.py:117-124` → **stage-commands §3 / §4** 照常跑,训练与 eval 主体不动。
6. `accept_v3diff.py` 对新环境**没有对照旧数据**,G8 那道门在新环境上无效——要另想验收办法(见 §4)。

### 2.4 先验成本估计(只数代码,不估工时)

- **要新写的文件:2 类** —— 1 个采集器(`envs/collect/run_<env>.py`,模板 102–124 行)、每模型 1 份 config(19 行)+ 1 份 manifest。
- **要加的分支:11 处** —— `build.collect_events` 1、`build.jsonl_events` 1、`build` 的 unit 派生 1、`param_label.collect_events` 1、`param_label.jsonl_events` 1、`rules` 正则 1、`eval_causal_call.parse_call` 1、`gen_launch` 客户端段 1、`gen_launch.MODEL_TABLE`(若同时换模型)1,外加 `--env choices` 7 处(算 1 处批量改)、`summarize_matrix --prefix/--models` 1。
- **一行不动的:5 个文件** —— 四个训练脚本 + `inject/check_bundle.py`。`eval_tool.py` 与 `eval_mbert_call.py` 也只动 choices 一行。
- **风险集中度**:11 处分支里有 4 处漏改**不报错**(见 §3 的 #5 #6 #7 #10),其余漏改都会当场退非 0。

---

## 3. 静默失败点总表

报错的坑会自己暴露,静默的不会。下面每一条都是"改错/漏改之后脚本照常退 0,只是数字变了或样本少了"。

| # | 位置 | 触发条件 | 症状 |
|---|---|---|---|
| 1 | `build.py:41-43` / `param_label.py:42-43` | 采集目录名尾巴(`rsplit("_",1)[1]`)不在 `MODEL_OF` | **整个目录被跳过**。同批其他模型照常出数;补采时新起了个不同名目录(如 `appworld_gptoss2`)最容易中招 |
| 2 | `build.py:40-41` | 轨迹写进了别的模型的 outdir | **模型张冠李戴**。模型归属**只看目录名**;`run_appworld.py:82-84` 写进 meta 的 `model` 字段全流水线无人读过(grep 无消费方) |
| 3 | `build.py:140` | 文件名不是 `appworld_*.jsonl` | glob 不命中,**静默少样本** |
| 4 | `build.py:196-205` | 三份官方题单之间有重叠 unit | `part[u]=name` 按 `SPLITS=("train","val","test")` 顺序后写覆盖,**test 最后写赢**,全程无重叠检查 → 划分静默变形、train/test 边界失守 |
| 5 | `build.py:70-79` / `param_label.py:63-69` | 新 env 复用 `jsonl_events` 但没加分支 | else 是 catch-all,**任何非 appworld 都拿 tales 的"动词=工具名"语义**,数据照造 |
| 6 | `rules.py:18` | 两个 key 映到同一个 `model_full` | `build.py:225` 的过滤把两批轨迹**静默合并**,直接破"永不合并同族"的口径(SKILL.md Phase 0) |
| 7 | `eval_causal_call.py:119-124` | `--env` 传错 | 只换正则不报错。appworld 数据传 `--env bfcl`,`apis.spotify.login(` 会被解析成工具 `login`,**tool_ok 全 false、数字整体塌陷**。注意:同一个 `--env` 在 `eval_tool.py`(只用于 `:239` 的 legacy 路径拼接与 `:355`/`:380` 的标题)和 `eval_mbert_call.py`(只用于 `:210`/`:225` 的标题字段)里**纯属标签**——三个 eval 里只有这一个真影响判分 |
| 8 | `summarize_matrix.py:67` | 忘了给 `--models` 加新模型 | 新模型四格**整体不出现在表里**,退 0 且 stdout 不提示 |
| 9 | `summarize_matrix.py:49-58` + `104-105` | 某个参数格是在 `--risk 0.1` 下跑出来的 | `--risk` 只作用于 tool 格的 `test_frozen[risk]`(`:38`);参数格两列**无条件读该 run 的报告**,而 `EXTRACT_REPORT.json` / `CALLGEN_REPORT.json` 是单文件覆盖写 → 0.05 档的表里会混进 0.10 档的数 |
| 10 | `gen_launch.py:172-177` + `:266` | 新模型 `family` 既不是 qwen 也不是 gptoss | 走 else,**按 gptoss 发服务旗标与客户端旗标**,发射脚本照常生成 |
| 11 | 四个训练脚本的 `--env` | 传错 | 只污染 `train_log.jsonl` 与 `best/meta.json` 的标签,数字不受影响(反向的静默:看日志的人会被误导) |
| 12 | `pipeline/configs/*.json` 的 `split_mode` 字段 | 改它 | **全流水线没有任何代码读这个字段**(grep 无命中),纯装饰 |
| 13 | `eval_causal_call.py:228` / `eval_mbert_call.py:139` | 跨模型串 run 与 data | 唯一的防线是 `len(rows) == logits.shape[0]` 的形状 assert;两个模型的 test 行数**恰好相等**时就静默串味 |

---

## 4. 未解之处

- **非 qwen / 非 gpt-oss 的第三种服务旗标**没有现成模板。`gen_launch.py` 只有 `QWEN_FLAGS_SRC`(`:57-59`)与 `GPTOSS_SERVE_FLAGS`(`:61`)两套,新族(如 Llama 的 tool-call parser)该配什么旗标,本仓库未读到。
- **ALFWorld 在本仓库不存在**。`envs/` 下只有 `appworld` / `tales`(TextWorld-Express)/ `tau2-bench` / `bfcl_*` 相关目录,ALFWorld 的官方 split 文件格式、task_id 形态、动作语法都未读到,§2 的清单对它只能给出"要改哪些位置",给不出"每处该填什么"。
- **一个环境是否必须配一个采集器,存疑**。`envs/collect/` 下只有 `run_appworld.py` 与 `run_tales.py` 两个采集器,bfcl 只有 `envs/collect/bfcl_gptoss/`(`gpt_oss_chat.py` / `install_patch.py` / `RUNBOOK.md` 三个文件,是给外部 BFCL 仓库打的补丁)。bfcl 轨迹的产出路径我未读到,所以"新环境必配采集器"这条可能有反例——也可能 bfcl 是外部工具产出后被 `build.py:83-132` 的 `bfcl_events` 直接读原生结果文件。
- **tales 链路未验证**。`eval_causal_call.py:119` 对 tales 走 `BFCL_CALL`,而 tales 的标签是动词、`label_call` 由 `build.py:158-162` 拼成 `verb(arg=...)`,形式上能对上,但 c1 批次没跑过 tales 的 cgen 格,未实测。
- **`ops/launch_c1.py` 与 `ops/c1_placement.json` 未入库**(git status 显示 `??`),不确定它们算不算流水线的正式组件;`ops/launch_c1.py:72` 的 smoke 写死 `"q35"`,若它是正式组件则情形 A 还要多改一处。
- **新环境下 G8(ACCEPT_V3DIFF)失效**。`accept_v3diff.py:24-25`/`:108` 把输入路径与环境列表写死成 `("bfcl","appworld")` 的旧数据,新环境没有旧数据可复现,这道门该换成什么验收,规格里未读到。
