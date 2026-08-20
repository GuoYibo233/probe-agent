# stage-commands — 五段流水线的照抄命令表

本文件是 collect / annotate / train / eval / inject 五段的命令模板,参数接口逐字抄自 `pipeline/` 源码(2026-07-31 c1 批次的代码状态),照抄替换占位符即可跑。
**所有命令一律从仓库根 `run.py` 进(2026-08-02 起的 CLAUDE.md 铁律),不许直接调底层脚本**:解释器由注册表选、固定参数由注册表带、GPU 任务只拼命令交 gpu-run。本文件给的是每个任务要传哪些参数;任务名与解释器的真源是 `run.py`(`python3 run.py list` / `show <task>` 可查)。
配套的流程说明在上一层的 `SKILL.md`;判分口径与数据设定不在本文件,在同目录的 `invariants.md`。
占位符约定:`<MODEL>` = q35/q36/gptoss 之类的模型短名,`<BATCH>` = 批次前缀(如 c1),`<ENV>` = appworld/bfcl/tales,`<DATA_ROOT>` = 数据集目录(如 `pipeline/data/aw_official_v1/<MODEL>`)。

## 0. 环境与路径常量

| 环境 | 绝对路径 | transformers | 管哪条线 |
|---|---|---|---|
| mbert-env | `/home/y-guo/reproduce/new1/mbert-env/bin/python` | 4.57.6 | ModernBERT:mtool / mext,以及评它们的 eval |
| cprobe-env | `/home/y-guo/reproduce/new1/cprobe-env/bin/python` | 5.14.1 | 因果模型:ctool / cgen / cparam,以及评它们的 eval |

两个环境互不升级(混合架构在旧版分块增量喂会静默算错,这是钉版本的原因)。**走 run.py 就不用自己选解释器**——上表只是让你看懂报错来自哪条线。

各环境的版本锁快照在 `ops/env_locks/`(一个 venv 一份 `uv pip freeze` 的 txt,含上表两个和 `envs/` 下的采集/服务环境),说明与生成命令见该目录的 `README.md`。**重大升级前先重生成对应快照并 commit**,再动手装包——这样"某环境突然行为不一样"时能直接 `git log -p` 对出是哪个包变了,不用重趟一遍装包过程。

**哪些任务占卡、哪些不占:完整清单一律现查 `python3 run.py list`,标 `[发射]` 的才交 gpu-run**(run.py 对它们只把命令拼出来打印),没标的直接跑完出结果;本文件不再抄一份会过期的名单。两个例外要知道:① `launch-probe` / `launch-eval` 列表里不带 `[发射]` 标(它们自己 ssh+tmux 发射,不是交出命令),但同样过脏树门禁;② `ann-check-callstr` 是第三类——不占卡,但 import 链上有 torch,注册表给它钉的是 cprobe-env 并清空 `CUDA_VISIBLE_DEVICES`,绕过 run.py 手写 `python3 pipeline/annotate/check_callstr.py` 必死在 ModuleNotFoundError。单个任务的解释器/固定参数/是否过门禁看 `python3 run.py show <task>`。
标 `[发射]` 的任务不用再手动"`show` 出命令 → 复制进 tmux → 手打三条登记"：
`python3 run.py launch <task> [参数...] --run-id ID --track 方向 --piece host:gpus`
一条命令做完探卡→tmux→30 秒验活→台账/record/RUNMETA 三处登记（见 gates.md G16）；
`launch-probe`/`launch-eval` 是给排卡表批量场景的专用发射壳，同样接了这套登记。

| 名目 | 路径 |
|---|---|
| 工程根 | `/home/y-guo/reproduce/new1` |
| 数据根 | `/home/y-guo/reproduce/new1/pipeline/data/<批次数据集名>/<MODEL>` |
| runs 根 | `/home/y-guo/reproduce/new1/pipeline/runs`(smoke 产物在 `pipeline/runs/smoke/<rid>_smoke`) |
| 日志目录 | `/home/y-guo/reproduce/new1/logs` |
| 采集 envs 根 | `/home/y-guo/reproduce/new1/envs`(轨迹落在 `envs/runs/<run_id>/`) |
| vLLM 服务日志 | `/home/y-guo/reproduce/new1/envs/serve_logs` |
| 模型权重 | `/net/tokyo100-10g/data/str01_01/y-guo/models`(别人的在 `.../zhou-y/models`) |

底座权重(写死在脚本里,换底座要改代码;**只记常量名不记行号——这批行号漂过一次**,要定位就 `grep -n` 常量名):
- ModernBERT-base → `/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base`
  (`train_mbert_tool.py` 与 `train_mbert_extract.py` 各有一个模块级常量 `MODEL`)
- Qwen3-0.6B-Base → `/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base`
  (`train_causal_tool.py` 的 `MODELS` 表、`train_causal_callgen.py` 的 `QWEN`)

---

## 1. collect — 采集

**干什么**:吃一份 manifest json,生成 vLLM 服务发射器 + 客户端分片发射器 + 人读的清单;**只生成不执行**,不 ssh 不碰显卡。

```bash
cd /home/y-guo/reproduce/new1
# 试生成(先看一眼,绝不碰 envs/)
python3 run.py gen-launch --config pipeline/collect/manifest_<BATCH>.json \
  --dry-run --out-override /tmp/genlaunch_<BATCH>/
# 正式生成 -> envs/runs/<run_id>/
python3 run.py gen-launch --config pipeline/collect/manifest_<BATCH>.json
```

| flag | 必填 | 说明 |
|---|---|---|
| `--config` | 是 | manifest json,模板见 `pipeline/collect/manifest_w0.json` |
| `--dry-run` | 否 | 必须同时给 `--out-override`,否则退 2 |
| `--out-override` | 否 | 改写到别处 |
| `--force` | 否 | 允许覆盖目标目录已有同名文件 |

**输入**:manifest 必需 `run_id` / `servers[]{host,gpu,model_key,port,session,extra_flags,card}` / `clients[]{tag,model_key,split,num_shards,shard_ports[],outdir,exp}`;可选 `envs_root`(默认 `envs`)、`client_session_prefix`(默认由 run_id 前两段拼,`w0_aw_official` → `new1_w0aw`)。
**输出**:`envs/runs/<run_id>/launch_servers.py`、`launch_clients.sh`(0o775)、`MANIFEST.md`。
**退出码**:正常 0;所有校验失败一律 `sys.exit(2)`——server 必须同一台机、model_key 必须在表里(只认 q35/q36/gptoss)、端口/session/卡不许重复、`len(shard_ports)==num_shards`、分片端口必须存在且模型匹配、目标已有同名文件且无 `--force`。`outdir` 非标准名只 WARN 并强制改成 `<env>_<model_key>`(`env` 取 manifest 顶层的 `env` 字段,缺省 `appworld`;下游按目录名尾巴认模型,改名会被静默跳过)。

生成完的两个发射器仍然要占卡跑 → **走 gpu-run skill 发射,不要手搓 ssh/nohup**。

---

## 2. annotate — 标注

**干什么**:把原始轨迹切成"思考前缀 → 该步调用哪个工具"的样本集(build.py),再给每个样本标出参数值的字符区间(param_label.py)。两步都是纯 CPU。

```bash
cd /home/y-guo/reproduce/new1
# 三步一条链(推荐):build -> param_label -> check_callstr,同一份 config
python3 run.py recipe annotate-chain --set config=pipeline/configs/<BATCH>_<MODEL>.json
# 或者逐步跑
python3 run.py ann-build         --config pipeline/configs/<BATCH>_<MODEL>.json
python3 run.py ann-params        --config pipeline/configs/<BATCH>_<MODEL>.json
python3 run.py ann-check-callstr --config pipeline/configs/<BATCH>_<MODEL>.json
# 可选:改过 rules.py/build.py 后的一致性验收(路径全写死,无参数)
python3 run.py ann-accept-v3diff
```

配方跑完看 `python3 run.py status`;中途炸了修完接着走
`python3 run.py recipe annotate-chain --id <id> --resume`。
⚠️ 配方引擎本身有个冒烟件:`python3 run.py recipe engine-smoke`——两步纯 CPU 自测
(跑两次 `parse-call-selftest`),验的是 `state.json` / 日志 / 续跑路径**这套机制**
本身没坏,不验流水线数据。改过引擎或怀疑 `--resume` 不对时先跑它,别拿正式标注链当试验田。

第三步 `ann-check-callstr` 是 **G19–G22 的实现**(不占卡,但注册表给它钉了
cprobe-env——脚本 import eval_causal_call → torch,系统 python3 没有;
必须在前两步之后跑),产物
`<DATA_ROOT>/CALLSTR_CHECK.md`;它同时做五道硬门禁与四类"只报不拦"的已知偏差,
细节见 `gates.md §1` 的 G19–G22。

**bfcl 那批(`bfcl_mtb_v1`)的完整命令,可直接照抄换环境**——注意 bfcl 没有官方分区,
题单要先自己生成一次(做法与门禁见 `extending.md §4.6`):

```bash
cd /home/y-guo/reproduce/new1
# ① 题单:先 --dry-run 看统计,再落盘(第二次跑会被"不静默覆盖"门禁挡住,除非 --force)
python3 run.py gen-bfcl-splits --dry-run
python3 run.py gen-bfcl-splits --out-dir pipeline/splits/bfcl_mtb_v1
wc -l pipeline/splits/bfcl_mtb_v1/{train,val,test}.txt      # 必须 140 / 40 / 20
# ② 三个模型各三步(等价写法:三次 recipe annotate-chain,每次换 config)
for M in q35 q36 gptoss; do
  python3 run.py ann-build         --config pipeline/configs/bfcl_$M.json || break
  python3 run.py ann-params        --config pipeline/configs/bfcl_$M.json || break
  python3 run.py ann-check-callstr --config pipeline/configs/bfcl_$M.json || break
done
```

其他环境的题单生成器同样在注册表里,换任务名即可:
`gen-alf-splits`(ALFWorld,⚠️ 无防覆盖门禁)、`gen-tau2-splits`(tau2 三域)、
`gen-toolhop-splits`(ToolHop 695/200/100)。

两脚本共用同一份 config,**一模型一份**。config 字段(照抄 `pipeline/configs/aw_q35.json`):

| 字段 | 含义 |
|---|---|
| `run_family` / `model_short` | 只进报告标题 |
| `env` | appworld / tales / bfcl,决定事件抽取器 |
| `model_full` | 按它过滤事件(如 `qwen3.5-27b`),一模型一套数据 |
| `traj_runs[]` | 轨迹目录列表,绝对路径 |
| `traj_runs[]` 的层级 | ⚠️ 必须写到 **run 目录本身**(`envs/runs/full_v1`),不是它的父目录(`envs/runs`)。写父目录会把 smoke 批次静默并进来,退 0 无告警(`extending.md §5 #20`,门禁 G21) |
| `official_split_files.{train,val,test}` | 题单 txt,每行一个 task_id。**环境没有官方分区时也用这个字段**,指向 `pipeline/splits/<批次>/` 下自己生成的题单(见 `extending.md §4.6`) |
| `split_mode` | 纯装饰,**没有任何代码读它**(`extending.md §5 #12`) |
| `split_desc` | 可选,**报告文案从它取**。默认 `"官方题单,任务实例级"`;没有官方分区的环境必须写(bfcl 写的是 `"冻结 v3_1 老三堆,任务实例级;BFCL 无官方分区"`),不写会被门禁 G22 拦住 |
| `data_out` | 数据集输出目录 = 后续所有 `--data` |
| `seed` | 默认 20260729 |

**输出**:`<DATA_ROOT>/{train,val,test}.jsonl`、`tool_vocab.json`、`router_stats.md`、`qa_sample.txt`、`ANNOTATE_REPORT.md`;param_label 再写 `<DATA_ROOT>/params/{train,val,test}.jsonl` + `PARAM_LABEL_REPORT.md` + `CHECK_50.md`;check_callstr 再写 `<DATA_ROOT>/CALLSTR_CHECK.md`(它**只读不写**数据本体)。
**退出码**:0;`raise SystemExit`(=1)三种——过滤后没有 `model_full` 的事件、**有 unit 不在任何官方题单里**(拒绝静默丢弃,换环境时最常炸的一条:题单文件路径写错或换了 split 命名就会全量报错)、未知 env。自检 assert 失败也是 1(前缀=原文切片 200 抽检、unit 不跨 split、每堆 20 unit 题单归属)。accept_v3diff 特殊:**全一致=0,有任何不一致=1**,报告写 `pipeline/annotate/ACCEPT_V3DIFF.md`。

---

## 3. train — 训练格

**干什么**:同一份数据训各格。现役三格(2026-08-21 起 m 线停跑):ctool(因果模型判工具种类)、cgen(因果模型直接写整条调用)、cparam(因果模型给定工具名只写参数段,数据与 cgen 同源零新标注);停跑存档两格:mtool(ModernBERT 判工具种类)、mext(ModernBERT 圈参数区间),仍可单发。各格互不依赖,可全并行。底座三档:ctool/cgen/cparam 都认 `--base qwen(0.6B,默认)/qwen17(1.7B)/qwen4(4B)`,**一个批次只跑一档底座**(run_id 没有档位段,混档撞 rid,见 extending §3.4)。**训练全要显卡 → 走 gpu-run skill 发射,不要手搓 ssh/nohup。**

先冒烟(每格加 `--smoke`,产物写 `pipeline/runs/smoke/`,不污染正式目录),再全量。以下是 c1 批次**真实跑过的 12 条命令**的形态(每格一条,只有模型段不同):

各训练格都是发射类任务:`run.py` 只把完整命令**拼出来打印**(解释器与脚本路径由
注册表填,不带 cd/CUDA_VISIBLE_DEVICES/tee——那是 gpu-run 发射模板的活),
发射本身走 gpu-run。⚠️ 出命令前过脏树门禁:`git status --porcelain` 非空就拒绝,
先 commit;非要跑加 `--allow-dirty`。**这道门连 `run.py show <task>` 也过**
(2026-08-02 加固,审计 A3)——文档里"用 show 出命令"这条路不许成为绕门的后门,
`show <task> --allow-dirty` 才放行。

```bash
cd /home/y-guo/reproduce/new1
R=pipeline/runs; D=pipeline/data/aw_official_v1
python3 run.py train-mtool --data $D/q35 --out $R/c1_q35_mtool
python3 run.py train-mext  --data $D/q35 --out $R/c1_q35_mext
# ctool 的 --base qwen 已固定在注册表里,不用再传;--align-tol 是唯一动过的超参
python3 run.py train-ctool --data $D/q35 --out $R/c1_q35_ctool --align-tol 3e-4
# cgen/cparam 的 --base 默认 qwen(0.6B),换档传 --base qwen17 / qwen4
python3 run.py train-cgen  --data $D/q35 --out $R/c1_q35_cgen
# cparam(2026-08-21 新格):给定工具名只生成参数
python3 run.py train-cparam --data $D/<m> --out $R/<batch>_<m>_cparam
```

一把发全批走排卡发射器 `python3 run.py launch-probe`(格表的唯一真源是 `run.py`
的 `CELLS`,`ops/launch_probe.py` 从它 import);先 `--dry-run` 看机位。
它自己有一个 `--force`,**原样透传给四个训练脚本**:`launch-probe smoke` 重跑同一批
必须带它——smoke 的 `--out` 是从 `<batch>_<model>_<cell>_smoke` 确定性推出来的,
第二次会被"同 out 已有 `train_log.jsonl`"守卫拦成 SKIP/退出。full 档同理,
只有确认要覆盖那个目录才加。
它**发射成功后自动往每个 `--out` 目录 append 一条 `RUNMETA.json`**
(时间/机器/kind/实际命令/commit/branch/dirty + 脏文件清单,append 不覆盖,
同目录二次发射留两条),产物从此能钉回代码版本。手搓发射(不经 launch-probe)
要自己补一条:`python3 run.py runmeta <outdir> --cmd '<实际命令>'`。

换批次时把 `q35` 换成 `<MODEL>`、`c1` 换成 `<BATCH>`、数据集名换掉即可。run_id 一律 `<BATCH>_<MODEL>_<格名>`,四处一致(数据目录名 / tmux session / 台账 name / commit message)。

| flag | 谁有 | 说明 |
|---|---|---|
| `--data` | 各格 | 必填,`<DATA_ROOT>`;mext 另可用 `--params`(默认 `<DATA_ROOT>/params`) |
| `--out` | 各格 | 必填,防覆盖旧件 |
| `--force` | 各格 | **2026-08-02 起(审计 B7)**:不传时,`--out` 下已经有 `train_log.jsonl` 就**直接 SystemExit 拒绝开训**——那个目录训过一次,再训会把两次产物混进同一个 `best/` 且无法归属。正常处置是**换一个 `--out`**;确认要覆盖才加 `--force`。→ 重发某一格前先看目标目录有没有 `train_log.jsonl`,别把这个退出当成脚本坏了 |
| `--base qwen` | 仅 ctool | **必填**,choices 只有 `qwen` |
| `--align-tol` | 仅 ctool | 默认 1e-4;长窗口下 fp32 舍入噪声会把绝对差顶到 1e-4,c1 批次统一用 `3e-4`。判是不是真算错看报告里的 reldiff:1e-6 量级=纯噪声,1e-3 以上=真算错,放宽也没用 |
| `--align-only` | 仅 ctool | 只跑对齐检查即退(0),开训前想单独验就用它 |
| `--base` | ctool/cgen/cparam | 三档 qwen=0.6B / qwen17=1.7B / qwen4=4B(权重都在 NFS models 盘)。ctool 必填(注册表已带 qwen);cgen/cparam 默认 qwen。发射换档走排卡表 extra(`--base qwen17`,argparse 后写的赢) |
| `--smoke` | 各格 | cgen/cparam(以及停跑的 mtool/mext) = 500 训练 / 200 评估实例,ctool = 200 / 80 事件,均 1 epoch |
| `--env` | 各格 | 默认 appworld,**仅作日志标签**,不影响数据路径 |
| `--device` | 除 mtool | 默认 cuda |
| `--readonly-env` | 各格 | choices `appworld/bfcl`,默认不传(**不传 = 字节级旧行为**)。传了即"只读+弃权"口径(ro1 批起):mtool/ctool 真值折叠、词表 = 只读工具(原顺序)+ 末位哨兵 `<NON_READONLY>`;mext/cgen 只在只读事件上训任务,非只读样本仅当开火头负例;cparam 非只读样本整条丢弃(它没有开火头)。真值表在 `pipeline/annotate/readonly/<env>.json`,表外标签超 5% 硬停(`readonly_map.audit`)。产物多一份 `<out>/READONLY.json` |
| `--fire-head` | mext/cgen(cparam 没有这旗) | 随训开火头(二值:该边界参数是否全就绪)。ready 真值按 `(event, sent_idx)` 联表 `params/<split>.jsonl`;mext 走独立样本流第二次前向,cgen 取 prompt 末位置(labels 最后一个 -100)的 logit 以免看见目标串。产物 `best/fire_head.pt`,`meta.json` 记 `fire_head: true` |
| `--grad-ckpt` | ctool/mext | OOM 唯一合规处置(invariants §6)。ro1 实测:开火头双前向让 q36/gptoss 长序列档在 48G 卡必 OOM,带此旗原卡重发即解。**z1 实测(2026-08-10)更宽:gptoss 轨迹的 ctool/cgen 不带 fire-head、默认超参也在 48G A6000 直接 OOM**——cgen 没有本旗,处置是换 H100/H200 大卡(`launch --refire` 换 `--piece` 即可)或降 `--bs` |

其余全用默认(`--max-len 4096`;mbert 两格 `--bs 8 --accum 4 --lr 2e-5`,因果两格 `--bs 4 --accum 8 --lr 1e-5`;一律 `--epochs 3`)。**本轮 12 次训练除 ctool 的 `--align-tol` 外没动过任何超参。**

**输出**:
- mtool → `<out>/best/`(HF 权重 + tokenizer + `label_map.json`)+ `train_log.jsonl`
- mext → `<out>/best/{model.pt(裸 state_dict,不是 HF 目录), tokenizer, meta.json}` + `train_log.jsonl`
- ctool → `<out>/ALIGN_CHECK.json` + `<out>/best/{HF backbone, tokenizer, head.pt, label_map.json, meta.json}` + `train_log.jsonl`
- cgen → `<out>/best/`(HF 权重 + tokenizer + `meta.json`,内含 `call_sep`)+ `train_log.jsonl`
- cparam → `<out>/best/`(HF 权重 + tokenizer + `meta.json`,内含 `call_sep` 与 `param_only: true`)+ `train_log.jsonl`

**退出码**:除 ctool 外无显式非 0。**ctool 的对齐检查 FAIL → `sys.exit(2)`**(整段一次前向 vs 逐 token 增量前向,末位置隐状态/logits 必须 max|diff| < tol),`ALIGN_CHECK.json` 无论过不过都会先落盘,拿它看 reldiff 再决定是放宽 tol 还是查版本。

---

## 4. eval — 回放评测

**干什么**:在 val 上拟温度、扫触发门槛 θ,再在 test 上冻结跑一次出数;然后在触发点上评参数/整条调用。

### 4.1 依赖顺序(不能颠倒)

1. **先评工具格**(现役 ctool;m 线停跑前还有 mtool):`eval_tool.py` 产出 `REPLAY_REPORT.json` 与 `logits_test.pt` / `logits_val.pt`。工具格之间互不依赖,可并行。
2. **再评参数/调用格**:`eval_mbert_call.py` 吃**同模型 mtool** 的报告与 logits;`eval_causal_call.py`(cgen)与 `eval_causal_param.py`(cparam)都吃**同模型 ctool** 的报告与 logits。跨模型串会 assert 失败。
3. **最后汇总**:`summarize_matrix.py`(纯 CPU)。

前两步占卡 → **走 gpu-run skill 发射,不要手搓 ssh/nohup**。

### 4.2 命令

```bash
cd /home/y-guo/reproduce/new1
R=pipeline/runs; D=pipeline/data/aw_official_v1

# 工具格:同一个 eval_tool.py 按 --head 分岔成两条任务,解释器由注册表选
# (mbert 头 → mbert-env;causal 头 → cprobe-env,它要 import train_causal_tool.py)
python3 run.py eval-tool-mbert  --env <ENV> --run $R/<BATCH>_<MODEL>_mtool --data $D/<MODEL>
python3 run.py eval-tool-causal --env <ENV> --run $R/<BATCH>_<MODEL>_ctool --data $D/<MODEL>

# 参数格
python3 run.py eval-mcall --env <ENV> --run $R/<BATCH>_<MODEL>_mtool \
  --extractor $R/<BATCH>_<MODEL>_mext --data $D/<MODEL>
python3 run.py eval-ccall --env <ENV> --ctool-run $R/<BATCH>_<MODEL>_ctool \
  --cgen-run $R/<BATCH>_<MODEL>_cgen --data $D/<MODEL>
# cparam:同一批 ctool 触发点跑 gt_tool/pred_tool 两口径,报告写进 --cparam-run
python3 run.py eval-cparam --env <ENV> --ctool-run $R/<BATCH>_<MODEL>_ctool \
  --cparam-run $R/<BATCH>_<MODEL>_cparam --data $D/<MODEL>

# 汇总(纯 CPU,run.py 直接跑;缺报告的格自动标 PENDING,可边跑边看)
python3 run.py matrix --runs-dir $R --out $R/MATRIX_REPORT.md --prefix <BATCH>
python3 run.py matrix --runs-dir $R --out $R/MATRIX_REPORT_risk10.md --prefix <BATCH> --risk 0.1

# "只读+弃权"批(ro1 起):三个 eval 都加 --readonly-env <ENV>(须与训练侧一致,双向保险丝见 §4.4);
# 参数格另可加 --self-fire 出自主开火块。ro1 实跑形态:
python3 run.py eval-tool-mbert --env bfcl --run $R/ro1bf_q35_mtool --data $D/q35 --readonly-env bfcl
python3 run.py eval-mcall --env bfcl --run $R/ro1bf_q35_mtool \
  --extractor $R/ro1bf_q35_mext --data $D/q35 --readonly-env bfcl --self-fire
python3 run.py eval-ccall --env bfcl --ctool-run $R/ro1bf_q35_ctool \
  --cgen-run $R/ro1bf_q35_cgen --data $D/q35 --readonly-env bfcl --self-fire
```

四个 eval 任务全是发射类:`run.py` 只打印命令,发射交 gpu-run,出命令前过脏树门禁
(连 `run.py show <task>` 也过——出命令这条路不是绕门的后门;非要脏树出命令加
`--allow-dirty`)。`--head mbert` / `--head causal` 已固定在注册表里,**不要再手传**。
排卡一把发走 `python3 run.py launch-eval`——它在发 call 档前硬检查依赖的工具格
有没有 `REPLAY_REPORT.json`,没有就退,替 §4.1 的依赖顺序上锁;评测格表的唯一真源
是 `run.py` 的 `EVAL_CELLS`(格 → 任务名 + 依赖的工具格),`ops/launch_eval.py`
只 import。它同样**发射成功后自动写 `RUNMETA.json`**(append 一条 commit + 实际命令,
不覆盖),但**落点与 §3 不同,别沿用那段的 `--out` 口径**:tool 档写进它的 `--run`
目录(=`<BATCH>_<MODEL>_<mtool|ctool>`),call 档写进**头自己的目录**
(mext / cgen 那个 run,不是它依赖的工具格目录),`kind` 分别记 `eval_tool` / `eval_call`。
两档的 RUNMETA 落点与各自报告的落点是一致的(EXTRACT_REPORT 在 mext 目录、
CALLGEN_REPORT 在 cgen 目录,见 §7 第一条)。记账失败只打 `WARN` 不中断发射,
看到 WARN 要自己补 `python3 run.py runmeta <目录> --cmd '<命令>' --kind eval_tool|eval_call`。

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
| `--cached-logits` | eval_tool | 读已存的 `logits_*.pt` 跳过推理,纯 CPU 后处理,重出报告时用它不占卡。**2026-08-02 起有权重指纹校验(审计 B9)**:每份 `logits_<sp>.pt` 旁边配一个 `logits_<sp>.meta.json`,记 `best/` 下每个权重文件的指纹(**大小 + 首尾各 64KB 的 sha1,不含 mtime**——正常拷贝/恢复不该作废缓存)与行数;正常跑(不带本旗)会自动写/更新这份指纹。带本旗时两种情况硬退:**缺 `.meta.json`**(旧缓存无从判断出自哪份权重)、**指纹对不上**(权重被重训或覆盖过,拒绝拿旧 logits 冒充新权重的结果)。指纹不符只能去掉本旗重算;**缺指纹**(指纹机制之前产的旧 logits)多一条路,见下一行 |
| `--adopt-logits-fingerprint` | eval_tool | **给指纹机制之前产的 logits 补档**,单独一趟跑:把 `--cached-logits` 换成本旗、其余参数照旧(`--env` / `--run` / `--data` 都仍必填),它给 `--run` 下每份已存在的 `logits_<sp>.pt` 写出 `.meta.json` 然后**直接 return 退出,不评测**。放行条件是 `best/` 下**所有**权重文件的 mtime 都不比该 logits 新——只有这样才能证明"当前权重就是产这些 logits 的权重";权重更新就 SystemExit,提示去掉 `--cached-logits` 重算。`best/` 下一个权重文件都没有时也 SystemExit(没东西可认领)。补完再按原命令带 `--cached-logits` |
| `--report-dir` | eval_tool | 默认 = `--run`;验收/试跑时指向别处以免覆盖旧件 |
| `--legacy-splits` | eval_tool | 读旧 calA/calB/test 三堆,仅历史验收用,新批次不要碰 |
| `--risk` | 两个 call | 默认 0.05,见 §4.3 |
| `--limit` | 两个 call | 截前 N 触发事件,冒烟用 |
| `--device` | 三个 eval | 默认 cuda |
| `--bs` | **只有两个 call 脚本有** | 默认 8。⚠️ `eval_tool.py` **没有这个 flag**——它的批大小是脚本里的常量:mbert 头走 `score()` 的默认 `bs=16`,因果头走 `EVAL_BS = 4`(事件/批)。想改只能改代码,命令行传 `--bs` 会被 argparse 拒 |
| `--readonly-env` | 三个 eval | choices `appworld/bfcl`,默认不传。传了:真值折叠,触发条件加"argmax ≠ 弃权哨兵",参数指标只算真值为只读的触发事件;eval_tool 报告多 `readonly_stats` 块,`prior_baseline_event_acc` 改在**折叠后**词表上取最高频(de1c781 修的坑:折叠前取会把 bfcl 先验错印成 0.0)。**双向保险丝**:run 的 `best/label_map.json` 含哨兵 ⇔ 必须传本旗,单边即 SystemExit |
| `--self-fire` | 两个 call | 自主开火评测:θ_fire 在 val 扫、test 冻结一次,触发点由参数格自己的开火头定。**必须与 `--readonly-env` 同传**(ready 定义依赖只读真值表),否则 SystemExit。要求参数格是 `--fire-head` 训的。只加 `self_fire` 报告块,旧字段一个不动 |
| `--fire-bs` | 两个 call | 开火打分批大小,0 = 沿用 `--bs` |
| `--params` | 两个 call | 参数标签目录,默认 `<data>/params`;self-fire 用它算 ready 真值 |

**输入 / 输出**:

| 脚本 | 读 | 写 |
|---|---|---|
| eval_tool | `<DATA_ROOT>/{val,test}.jsonl` + `tool_vocab.json`;`<run>/best/label_map.json`(causal 另读 `meta.json`、`head.pt`) | `<run>/logits_val.pt`、`<run>/logits_test.pt`、`<report-dir>/REPLAY_REPORT.{json,md}` |
| eval_mbert_call | `<run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json`;`<DATA_ROOT>/test.jsonl` + `router_stats.md`;`<DATA_ROOT>/params/test.jsonl`;`<extractor>/best/` | `<extractor>/EXTRACT_REPORT.{json,md}` |
| eval_causal_call | `<ctool-run>/REPLAY_REPORT.json` + `logits_test.pt` + `best/label_map.json`;`<DATA_ROOT>/test.jsonl`;`<cgen-run>/best/`(`call_sep` 从它的 meta.json 读,不硬编码) | `<cgen-run>/CALLGEN_REPORT.{json,md}` |
| summarize_matrix | 各 run 的 `REPLAY_REPORT.json`(mtool/ctool)、`EXTRACT_REPORT.json`(mext)、`CALLGEN_REPORT.json`(cgen) | `--out` 指的 .md,同时打到 stdout |

**退出码**:eval_tool 正常路径无显式非 0;`--cached-logits` 下有三条硬退——缺 `logits_<sp>.meta.json`、权重指纹对不上(两条都是 SystemExit,见 §4.4 该行)、logits 行数与数据行数不符(assert 退 1,意味着 `--data` 与当次评测不同源)。另外 `best/` 下一个权重文件都找不到时建不了指纹,也 SystemExit。两个 call 脚本:该 risk 档 θ 为 null → `SystemExit` 退 1。`eval_causal_call` 另有一条 assert 防止调用切分口径与 `annotate/rules.py` 漂移。summarize_matrix 永远 0。

---

## 5. inject — 产物校验

**干什么**:证明这套权重换个进程也装得起来、打得出分。**能跑通即凭证**,不是精度评测。冒烟阶段就该跑一次。

```bash
cd /home/y-guo/reproduce/new1
# mbert 头(mtool/mext 产物);注册表已带 --head mbert --device cpu,run.py 直接跑,不占卡
python3 run.py check-bundle-mbert --run pipeline/runs/<BATCH>_<MODEL>_mtool --data <DATA_ROOT>
# causal 头(ctool 产物);注册表已带 --head causal,默认 cuda
python3 run.py check-bundle-causal --run pipeline/runs/<BATCH>_<MODEL>_ctool --data <DATA_ROOT>
```

⚠️ 两条的执行方式不一样:`check-bundle-mbert` 是 CPU 任务,run.py 当场跑完出结果;
`check-bundle-causal` 在注册表里标了 `gpu=True`,run.py **只打印命令**交 gpu-run
——handoff 是按任务定的,加 `--device cpu` 也照样只打印,不会当场执行。

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
S1 (CPU)  run.py gen-launch --config manifest_<BATCH>.json --dry-run --out-override /tmp/... → 看清单
S2 (CPU)  run.py gen-launch --config manifest_<BATCH>.json                → envs/runs/<BATCH>/
S3 (GPU)  launch_servers.py → smoke 每模型 1 题 → launch_clients.sh       ★ 采集,耗时最长
          (这两个是 gen-launch 的生成物,一次性发射器不进注册表)
S4 (CPU)  run.py ann-build  --config configs/<BATCH>_<MODEL>.json         ← 等 S3 轨迹落齐
S5 (CPU)  run.py ann-params --config 同一份 config                        ← 等 S4 的 jsonl
          (S4+S5+check 也可一条 run.py recipe annotate-chain --set config=...)
S6 (GPU)  run.py train-<格> ... --smoke,产物进 pipeline/runs/smoke/       ← 等 S5
S7 (CPU)  run.py check-bundle-mbert 对 smoke 产物跑一遍                    ← 等 S6
S8 (GPU)  run.py train-<格> 各格全量(或 run.py launch-probe 一把排卡)     ← 等 S7 放行
S9 (GPU)  run.py eval-tool-mbert / eval-tool-causal × 6                   ← 等 S8 对应格训完
S10(GPU)  run.py eval-mcall(吃同模型 mtool)/ eval-ccall(吃同模型 ctool) ← 等 S9
          (S9+S10 排卡一把发走 run.py launch-eval,它替依赖顺序上锁)
S11(CPU)  run.py matrix 出 0.05 与 0.1 两档表                             ← 随时可跑,缺的标 PENDING
```

并行/串行:
- **S4/S5 逐模型独立**,三个模型可并行(纯 CPU,互不抢资源);同一模型内 S5 必须等 S4。
- **S8 四格 × 三模型 = 12 个 run 全并行**,只受卡数限制(c1 批次:tokyo105 八卡 + tokyo106 四卡)。
- **S9 六个并行**;S10 必须等对应的 S9,因为它要读 `REPLAY_REPORT.json` 的温度/θ 与 `logits_test.pt`。
- S11 任何时候都能跑,不完整就是一张带 PENDING 的表。
- 每次 GPU 发射前先 commit(记录里的 HEAD 只有工作树干净时才追得回真实代码;run.py 对发射类任务是**硬门禁**,脏树直接拒绝出命令,`show` 出命令也一样拦,`--allow-dirty` 才放行)。**launch 自动写三处;手搓/register 补录路径仍在,漏了照旧算违规**——`python3 run.py launch <task> ...`(单任务)或 `launch-probe`/`launch-eval`(排卡批量)发射成功会自动做完台账登记 + `record.py start` + `<out>/RUNMETA.json` 三处;手搓发射(未接 launch 的老脚本)要自己补 `python3 run.py gpu-jobs register ...` + `python3 run.py record start ...` + `python3 run.py runmeta <outdir> --cmd '<命令>'`,收尾各跑一次 `finish`。

---

## 7. 接口陷阱

- **产物写向不对称**:`eval_tool.py` 的 `logits_*.pt` 永远写进 `--run`(`--report-dir` 只改报告);`eval_mbert_call.py` 的报告写进 `--extractor` 而非 `--run`;`eval_causal_call.py` 的报告写进 `--cgen-run` 而非 `--ctool-run`。→ 去 mtool 目录找 EXTRACT_REPORT 会一无所获。
- **`train_log.jsonl` 是 append 模式**(各训练脚本一致):同一个 `--out` 重跑会在旧日志后面续写,不清空。→ 读日志算轮次/耗时前先确认只有一段 `event=start`,否则数字是两次跑的混合。**2026-08-02 起这个坑被堵住了**:各格开训前先查 `--out` 下有没有 `train_log.jsonl`,有且没传 `--force` 就 SystemExit(见 §3 的 `--force` 行);所以现在只有显式 `--force` 才可能出现混合日志,读到两段 `event=start` 就说明有人加过 `--force`。
- **`--env` 在训练脚本里只是日志标签**,数据路径完全由 `--data` 决定;但在三个 eval 脚本里 `--env` 是必填且**影响判分**(选调用解析正则)。→ 训练时写错无害,评测时写错会让工具名全判错。
- **底座三档(2026-08-21 起)**:ctool 的 `--base` 必填(注册表带 `qwen`),cgen/cparam 默认 `qwen`;三个脚本各有一份同构 `MODELS` 表(qwen/qwen17/qwen4),**没有单一真源,加档要改三处**。发射时换档走排卡表 extra(argparse 后写的赢)。
- **eval_causal_param.py 的报告写进 `--cparam-run`**(PARAM_REPORT.{json,md});它带格保险丝:`best/meta.json` 没有 `param_only: true`(比如误喂 cgen 的 run)直接 SystemExit——cparam 的 prompt 自带工具名,喂 cgen run 会把工具名写两遍、数字静默变形,所以硬停。矩阵只读它的 **pred_tool 块**(系统乙口径),gt_tool 块只进报告。
- **gen_launch 的 gpt-oss 客户端预设 2026-08-21 起可配**:manifest 顶层可选字段 `gptoss_client_preset`,缺省 `gptoss_chat_high`(老 manifest 行为逐字节不变);给了名字就校验 `configs/presets/<名>.json` 存在,缺文件退 2。
- **launch_probe smoke 档的 `--gpus` 缺省 2026-08-21 起是 `0,1,2`**:张数必须等于 `CELL_ORDER` 长度(现为三格),给四张退 1。
- **mext 的权重是 `best/model.pt` 裸 state_dict**,不是 HF 目录,不能用 `from_pretrained` 直接读。→ 复用它必须走 `train_mbert_extract.load_extractor()`。
- **`--head causal` 的 eval_tool 会 import `pipeline/train/train_causal_tool.py`**,所以必须用 cprobe-env 跑;拿 mbert-env 跑 causal 头会在 import 或加载处炸。
- **两个 call 脚本对 θ 为 null 是硬失败**(退 1),不是跳过。→ 批量评测脚本要接住这个退出码并降档到 `--risk 0.1`,否则整批中断。**例外**:带 `--self-fire` 时 θ null 不退 1——旧模式块整块跳过、只出 `self_fire` 块并打一行提示;别把"跑完了"当成"旧口径也有数"。
- **`--self-fire` 与 `--readonly-env` 是绑定的**(缺一即 SystemExit);`--readonly-env` 自己又与 label_map 里的哨兵双向绑定(带哨兵的 run 不传旗、或不带哨兵的 run 传旗,都硬停)。→ 排查这类 SystemExit 先看 `best/label_map.json` 末位是不是 `<NON_READONLY>`,再看命令行,别去翻数据。
- **`build.py` 对"unit 不在官方题单"零容忍**(退 1)。→ 换环境(appworld→bfcl→alfworld)时,题单文件的命名与 task_id 格式必须先对齐,否则第一步就全量报错。
- **`gen_launch.py` 强制 `outdir = <env>_<model_key>`**(`env` 取 manifest 顶层的 `env` 字段,缺省 `appworld`;所以 appworld 批是 `appworld_q35`,alfworld 批是 `alfworld_q36`),自定义名只会被 WARN 并改掉;下游事件抽取按目录名尾巴认模型,`MODEL_OF` 只认 q35/q36/gptoss(`annotate/rules.py` 的 `MODEL_OF` 常量)。→ 新模型必须先往这张表里加一行,否则采到的轨迹会被静默跳过。
- **`--smoke` 不改 `--out`**:冒烟和全量传同一个 `--out` 会让冒烟权重占住 `best/`。→ 照 `ops/launch_probe.py:71` 的做法,冒烟一律写 `pipeline/runs/smoke/<rid>_smoke`。**2026-08-02 起这条有了硬拦**:各格都带 `--force`,不带它时 `--out` 下已有 `train_log.jsonl` 就拒绝开训(见 §3 的 `--force` 行),所以"冒烟占住正式目录"现在会当场退出而不是静默混产物。
