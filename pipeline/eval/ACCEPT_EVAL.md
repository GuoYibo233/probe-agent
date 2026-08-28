# eval 段验收（规格 §6.5）— 2026-07-31

结论：**PASS**。新 `pipeline/eval/eval_tool.py` 在 `--legacy-splits --cached-logits`
下重跑 v3 的 bfcl 分类头，产出的 `REPLAY_REPORT.json` 与旧
`envs/bert_runs/bfcl_v3/REPLAY_REPORT.json` **逐字节相同**（不止 temperature /
chosen_theta / test_frozen 三块，全文件相同；`.md` 也逐字节相同）。
加跑的因果探针那一份（`bfcl_v3_causal_qwen`）同样逐字节相同。

零 GPU：两次都走 `--cached-logits`，只读旧 `logits_*.pt` 做 CPU 后处理，
mbert 侧 12 秒跑完。

## 0. 第二轮更正（2026-08-28，不改动上面的历史结论）

本文档记的是 2026-07-31 代码状态下的验收结果，当时的判据是"逐字节相同"。第二轮（工单 07，spec 16.2）起 `eval_tool.py` 的 `REPLAY_REPORT.json` 无论 `--overlong` 传哪个值都会多写 `overlong_mode` 与四个计数键（`n_oow` / `n_skipped_bounds` / `n_dropped_events` / `n_dropped_bounds`，没发生的写 0）；cgen / cparam 的报告同样多写 `overlong_mode` 与各自那套计数。现在再跑本文①②两条命令，报告不会再与旧产物逐字节相同——**新判据是"除这几个新键外，其余现有键不变"**，不再要求整份文件字节级相同。

## 1. 验收命令

入口是仓库根 `run.py`：`eval-tool-mbert` / `eval-tool-causal` 两条任务对应同一个
`eval_tool.py` 的两个 `--head`（`--head` 与解释器都由注册表钉死，命令里不再写）。
两条任务都登记为发射类，`python3 run.py <task> …` 只把命令打印出来不执行——本文这两条
是纯 CPU 验收（`--cached-logits`），把打印出来的命令原样手跑即可
（出命令带脏树门禁：工作树脏时加 `--allow-dirty` 才打印，这不是跳过 run.py，
是 run.py 自己的逃生口）。

规格给的命令（本次实跑时多加了 `--report-dir`，理由见 §4 偏离①）：

```bash
python3 run.py eval-tool-mbert --env bfcl \
  --run  /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3 \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --cached-logits \
  --report-dir /home/y-guo/reproduce/new1/pipeline/eval/accept_bfcl_v3
```

⚠️ `bfcl_v3` 是**冻结的旧 run，它的 `logits_*.pt` 没有指纹档**——直接照上面跑会被
§1.1 那道校验挡住。先补档再跑（做法与理由见 §1.1）。

自加的第二条（因果头路径的同款验收）：

```bash
python3 run.py eval-tool-causal --env bfcl \
  --run  /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3_causal_qwen \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --cached-logits \
  --report-dir /home/y-guo/reproduce/new1/pipeline/eval/accept_bfcl_v3_causal
```

⚠️ 同上：这条也要先按 §1.1 补一次指纹档，再带 `--cached-logits` 跑。

产物落在 `pipeline/eval/accept_bfcl_v3{,_causal}/`，旧目录一个字节没动
（旧 `REPLAY_REPORT.json` 的 md5 跑前跑后都是 `18f948fe…`，
causal 那份是 `1893a059…`）。

### 1.1 旧冻结 run 的 logits 没有指纹档，要先补一次

2026-08-02（审计 B9）起 `eval_tool.py` 给每份 `logits_<sp>.pt` 配一个
`logits_<sp>.meta.json`，里面记着产它那份 `best/` 权重的指纹（**每个权重文件的
大小 + 首尾各 64KB 的 sha1，不含 mtime**）与行数。带 `--cached-logits` 时缺这个
文件就 `SystemExit`——旧缓存无从判断出自哪份权重，不许拿它冒充。

本文两条验收命令读的都是**这套机制之前**产的 logits，所以没有 `.meta.json`。
处置：把命令里的 `--cached-logits` 换成 `--adopt-logits-fingerprint` 先跑一遍，
**其余参数一个字不改**（`--env` / `--run` / `--data` / `--legacy-splits` 都仍要给，
`--report-dir` 给不给都行，这一趟不写报告）：

```bash
python3 run.py eval-tool-mbert --env bfcl \
  --run  /home/y-guo/reproduce/new1/envs/bert_runs/bfcl_v3 \
  --data /home/y-guo/reproduce/new1/envs/bert_data/v3 \
  --legacy-splits --adopt-logits-fingerprint
```

它做的事：给 `--run` 下每份已存在的 `logits_<sp>.pt` 写出 `.meta.json`，然后
**直接退出，不评测**。放行条件是 `best/` 下**所有**权重文件的 mtime 都不比该
logits 新——只有这样才能证明"当前权重就是产这些 logits 的权重"；权重更新就报
"权重比 logits 新"并拒绝认领。补完再按上面的原命令带 `--cached-logits` 跑验收。

不想认领也行：**去掉 `--cached-logits` 重算一次**，重算会自动写指纹。代价是这两条
就不再是零 GPU 的 12 秒验收了，而且重算出的报告要能与旧产物逐字节相同才算数。

## 2. 对比字段清单与逐字段结论

判定口径是规格点名的三块，逐字段结果如下（两次验收同样结论）：

| 字段 | bfcl_v3（mbert 头） | bfcl_v3_causal_qwen（因果头） |
|---|---|---|
| `temperature` | 一致：1.5218 | 一致：1.3883 |
| `chosen_theta` | 一致：{"0.1": 0.725, "0.05": 0.95} | 一致：{"0.1": 0.8, "0.05": 0.925} |
| `test_frozen["0.1"]` | 一致：θ=0.725, n=226, coverage 0.8894, trig_acc 0.8955, earliness 0.6897, wrong_spec 0.0929, ci 三项全等 | 一致：θ=0.8, n=226, coverage 0.8805, trig_acc 0.9347, earliness 0.6826, wrong_spec 0.0575, ci 三项全等 |
| `test_frozen["0.05"]` | 一致：θ=0.95, n=226, coverage 0.5929, trig_acc 0.9925, earliness 0.6152, wrong_spec 0.0044, ci 三项全等 | 一致：θ=0.925, n=226, coverage 0.8009, trig_acc 0.9779, earliness 0.5596, wrong_spec 0.0177, ci 三项全等 |

判定之外的字段也一并比了，全部一致（所以 `diff` 全文件为空）：
`env`、`theta_sweep_calB`（20 档 θ 的 agg 全等）、`stoptime_calibration_test`、
`depth_bucket_acc_test`、`prior_baseline_event_acc`、`n_events_test`（226）、
`speculation_economics`（calB_sweep + test_frozen 两段），
以及因果头独有的 `probe_backbone`、`probe_cost_test`。

bootstrap 置信区间能逐位对上，说明 `random.Random(SEED=20260729)` 的取用次序
也与旧脚本一致——这是最容易被改动打乱的一处，专门确认过。

## 3. 另外跑过的新口径冒烟（不属于 §6.5，但顺手验了新分支）

`--legacy-splits` 关掉后的 val/test 新口径路径，用 4 个事件的小数据在 CPU 上跑通：

```bash
python3 run.py eval-tool-causal --env bfcl \
  --device cpu --run /tmp/eval_smoke/run --data /tmp/eval_smoke/data \
  --report-dir /tmp/eval_smoke/rep
```

（同上：run.py 出命令，这条 `--device cpu` 的冒烟把打印出来的命令原样手跑；
run/best 是指向 `envs/bert_runs/bfcl_v3_causal_qwen/best` 的软链，只读；
logits 写进 /tmp，旧目录未被写入。）这条路径验的是：`CausalProbe` 从
`pipeline/train/train_causal_tool.py` 导入并加载 backbone + head.pt、
按事件整段一次前向取边界位 logits、温度与 θ 都在 val 上定、test 冻结、
`probe_cost_test` 计数。全程无 GPU。

## 4. 偏离与自行决策（规格未覆盖处）

1. **新增 `--report-dir`**（默认 = `--run`，行为不变）。规格 §6.5 要求
   "把新报告写到临时目录，绝不覆盖旧文件"，但源脚本把报告硬写进 run 目录，
   不加这个开关就没法在不碰旧件的前提下验收。口径无影响。
2. **新增 `--device`**（默认 cuda）。源 `eval_replay.py` 把 `dev` 写死成 "cuda"；
   `eval_replay_causal.py` 本来就有 `--device`。合并成一个脚本后统一暴露，
   CPU 验收/冒烟要用。
3. **`--data` 语义分叉**：新口径下 `--data` 直接指 `<data_out>`（规格 §6.1②），
   但 v3 旧数据是 `<data>/<env>/` 两层。所以 `--legacy-splits` 下 `--data`
   退回旧语义（拼 `/<env>`），只此一处，写在 `--help` 里。
4. **因果头的 tokenizer 无条件加载**：`--cached-logits` 只跳过模型，不跳
   tokenizer——因为 `probe_cost_test` 要用它数 token。这是【照抄】旧
   `eval_replay_causal.py` 的行为（旧脚本也是无条件 `AutoTokenizer.from_pretrained`），
   第一版我写成了跟着 cached 一起跳，导致报告少两个字段，已改回并重跑验收。
5. **因果头的两个诊断字段只在 `--head causal` 时出现**（`probe_backbone`、
   `probe_cost_test`）。规格 §3.6 的字段清单里没有它们，但旧因果报告有；
   保留 = 新旧因果报告可逐字节对账，且 mbert 报告的字段集合一个不多。
6. **`.md` 标题**：因果头沿用旧标题 `# 回放评测 — bfcl（因果探针 qwen）`，
   mbert 头沿用 `# 回放评测 — bfcl`。不这么分，md 就对不上字节。
7. **旧字段名一律不改**（§2.5）：新口径下温度和 θ 都在 val 上定，
   但报告里仍叫 `theta_sweep_calB`、`stoptime_calibration_test`，
   md 里"calB 上无满足约束的 θ"这句也照抄没改。下游按名读的脚本不受影响。
8. **验收产物入不入 git 未定**：`pipeline/eval/accept_bfcl_v3{,_causal}/` 里的
   `REPLAY_REPORT.json` 不在 `.gitignore` 覆盖范围内（`pipeline/data`、
   `pipeline/runs` 才是）。留着当验收凭证，是否入库交主对话定。
