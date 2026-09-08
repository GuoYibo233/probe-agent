# 工作计划

> 会被覆盖重写的当前计划。决策历史归 `TIMELINE.md`，两者分工不能颠倒。

当前主线是 np821 批（计划全文 `plans/archive/2026-08-21-np821-plan.md`，口径定案见
TIMELINE 2026-08-21 两条）。位置：施工块已完成并一个 commit 收口，
执行块还没开始。

1. **执行块**（按计划 §4 的依赖序走，入口是驱动器
   `python3 run.py pipeline --config pipeline/configs/np821_gptoss.json`）：
   NFS 空间预检 → 采集 1260 条 → 标注（切点分布停点裁决 `max_bounds`）→
   三格 smoke 加排卡表 → 四批训练 → 评测 → 矩阵 → Phase D 收官 +
   Phase E 回写 skill。
2. **回写清单**（下次动到对应代码时一并做，np821 本批明确不动）：
   - `pipeline/eval/eval_tool.py:49` 写死的 `SEED = 20260729`：评测五脚本
     本批零改动，下次动评测代码时把种子并入 42 家族并重跑 G12 验收线。
   - `pipeline/train/train_mbert_tool.py` / `train_mbert_extract.py` 的
     `SEED = 20260729`：m 线 2026-08-21 起停跑，重启那天一并换。
   - `pipeline/collect/gen_*_splits.py` 四个切分生成器的 `SEED = 20260729`：
     它们是已入库题单的一次性生成器，常量是冻结产物的档案，动它们等于
     换切分，要动必须连题单一起重新裁决。
   - `envs/collect/build_dataset.py:27` 的 `SEED = 20260729`（注册表里的
     build-dataset-legacy，已被 pipeline/annotate/ 取代的旧线历史入口）：
     常量是冻结产物 bert_data v2 的档案（出厂报告头一行印着这个 SEED），
     动它等于换旧数据的复现口径，与四个切分生成器同一条标准，不动。
     施工时全仓清点漏了这处，2026-08-22 验收补记。
   - `pipeline/inject/replay_inject.py:399` 与 `pipeline/inject/score_live.py:119`
     按 `appworld_<unit>.jsonl` 反查轨迹文件：多样本批的文件名带 `_r<k>` 后缀，
     反查会全部落空且是静默计数丢弃不报错（replay_inject 会退 0 出一份空
     plan）。哪天这两条线（回放注入、活跑打分）要吃多样本批的数据，先把
     反查改成用样本行自带的 `traj` 字段拼路径；同一趟里
     `pipeline/inject/exec_calls.py:573` 按 unit 分组也要改成按 traj 分组，
     不然同题四条轨迹的事件会全被拍到一条轨迹上。np821 执行块用不到这两条线。
