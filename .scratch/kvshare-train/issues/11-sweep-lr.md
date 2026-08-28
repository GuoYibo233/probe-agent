# 11 学习率扫描的驱动与报表：`pipeline/train/sweep_lr.py`（`plan` / `report`），注册为 `sweep-lr`

Status: ready-for-agent
Blocked by: （无）
Spec: `.scratch/kvshare-train/spec.md` 16.6（两个子命令）、16.8（发射由主会话做，本工单不发射）、16.9（测试）。改动只在新文件 `pipeline/train/sweep_lr.py`、`run.py`（`TASKS` 加一条 `sweep-lr`）、新测试 `tests/test_sweep_lr.py`。不改训练器、不改文档（`MAP.md` 那一行归工单 12）。

## 背景

gyb 裁决学习率要扫。规模（决定 27）：四个底座配置 × 三个学习率 = 12 次 run，cgen 格、1 个 epoch、`--eval-per-epoch 4`，按 `val_ce` 最低选。发射走 gpu-run（主会话），本工单只做「出清单」和「收表」两件事，都是 CPU 任务。

## 要做的

1. `pipeline/train/sweep_lr.py`，`argparse` 两个子命令：
   - `plan [--grid <json>] [--data <dir>] [--out-root <dir>] [--py <python>] [--track kvshare-lr-sweep] [--write <plan.json>]`。网格常量 `GRID`（列表，每项 `dict(tag, base, lora: bool, lrs: list, tok_budget: int, card: str, extra: list)`）初值：`b06`（`qwen`, 全参, `[1e-5, 2e-5, 5e-5]`, 16384, "H100", []）、`b17`（`qwen17`, 全参, 同上, 16384, "H200", []）、`l17`（`qwen17`, LoRA, `[1e-4, 2e-4, 5e-4]`, 16384, "H100", []）、`l4`（`qwen4`, LoRA, 同上, 16384, "H200", []）。`tok_budget / card / extra` 三项主会话拿到排卡结论后会改常量，写成一眼能改的样子。run_id = `ks828<tag>_gptoss_cgen_lr<lr>`，`<lr>` 由 `f"{lr:.0e}"` 去掉指数前导零得到（`1e-05` → `1e-5`，`2e-04` → `2e-4`）。产物目录 `<out_root>/<run_id>`，`--out-root` 默认 `pipeline/runs/sweep`（仓库根相对路径，`plan` 输出里写成绝对路径），`--data` 默认 `pipeline/data/nyapass_aw_v1/gptoss`，`--py` 默认 `<仓库根>/cprobe-env/bin/python`（仓库根按 `Path(__file__).resolve().parents[2]` 取）。每条命令 = `<py> <仓库根>/pipeline/train/train_causal_share.py --mode cgen --base <base> --env appworld --data <data 绝对路径> --out <out 绝对路径> --lr <lr> --tok-budget <tb> --epochs 1 --eval-per-epoch 4 --log-every 10 --mem-probe` 加 `--lora`（`lora` 为真时）加 `extra`（`--log-every 10` 必须写：默认 50 在约 506 次更新的一个 epoch 里只出 10 条 step）。输出：stdout 先打一张 Markdown 表（`run_id | tag | base | lora | lr | tok_budget | card`），再打 12 行 `python3 run.py launch --cmd '<cmd>' --run-id <run_id> --track <track> --outdir <out>`（`shlex.quote` 整条命令）；`--write` 给了就把清单写成 JSON 数组（每条 `run_id, tag, base, lora, lr, tok_budget, card, cmd, outdir`）。`--grid` 给一个 JSON 文件时整体替换 `GRID`（格式同常量）。
   - `report --runs <路径或 glob，nargs="+"> --out <目录>`：每个 run 目录读 `train_log.jsonl`：`start` 事件取 `base, lora（键在不在）, lr, tok_budget, n_train_events, dropped_events_train`；全部 `eval` 事件取 `frac, val_ce, val_exact_call`（或 `val_exact_params`；键不在写 `null`）；`done` 取 `best_val_ce, best_frac, wall_s`；`step` 事件里 `peak_mem_gb` 的最大值；`mem_probe_summary` 的 `worst_gb`（没有就 `null`，兼容旧探针只有 `mem_probe` 事件的 run：取各 `mem_probe` 的 `peak_mem_gb` 最大值）。配置的分组键 = `(base, lora)`，组内按 lr 升序。写 `<out>/SWEEP_REPORT.json`（列表，每条上面全部字段加 `run_id, status`）与 `<out>/SWEEP_REPORT.md`（一张表：`run_id | lr | val_ce@1 | @2 | @3 | @4 | best_val_ce | best_frac | val_exact(best) | peak_mem_gb | worst_gb | wall_s | status`；`status` 是 `done` 或 `running`，running 的行 best 列写目前为止最低的 eval；每组 `best_val_ce` 最低的一行在 run_id 前加 `*`）。表前一行写生成时间与读了几个目录，表后不写任何结论句。找不到 `train_log.jsonl` 的目录打一行警告并跳过，不报错。
2. `run.py` `TASKS` 加 `"sweep-lr"`：`desc="学习率扫描的清单(plan)与收表(report),发射仍走 gpu-run"`，`stage="train"`，`py="cprobe"`，`script` 指向新文件，`notes` 写两个子命令的用法与 `GRID` 常量在哪。字段集照现有 CPU 条目（第 195 行 `gen-toolhop-splits` 是先例：`stage / py / script / desc / notes`），不写 `gpu` 键（GPU 任务才写 `gpu=True`）；`cmd_list / cmd_show` 直接下标取 `desc` 与 `stage`，缺一个 KeyError。
3. 测试 `tests/test_sweep_lr.py`（纯 CPU，不需要 torch）：(a) `plan` 用默认 `GRID` 出 12 条，run_id 两两不同，每条 `cmd` 含 `--lr <该值>` 与 `--log-every 10`，`lora` 为真的含 `--lora`、为假的不含，`--out` 以 run_id 结尾；`lr` 格式化 `1e-05 → 1e-5`、`2e-04 → 2e-4`、`5e-05 → 5e-5`；(b) `report` 在 `tempfile` 里手造两个 run 目录（一个有 `start` + 4 条 `eval` + `done` + 两条 `step` + `mem_probe_summary`，一个只有 `start` + 1 条 `eval`），出表：JSON 两条、`status` 各对、`*` 标在 `best_val_ce` 最低那行、缺 `done` 的行 `status == "running"`。

## 验收

- `cprobe-env/bin/python -m unittest tests.test_sweep_lr` 通过；`python3 -m unittest tests.test_sweep_lr` 也通过（脚本不 import torch）。
- `python3 run.py selfcheck` 通过，任务数从 76 变 77。
- `python3 run.py sweep-lr plan` 打印 12 行 `run.py launch` 命令；`python3 run.py sweep-lr plan --write /tmp/x.json` 落 JSON。
- 不改训练器、不改文档。
