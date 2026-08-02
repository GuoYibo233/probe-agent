# TIMELINE — 方向决策线

> **这个文件只增不改**，新的加在最上面。它不是计划书，是"什么时候因为什么改了主意"。
>
> 三个文件分工，别搞混：
> - `WORKPLAN.md` = 当前计划，会被覆盖重写 → 回答"现在要干什么"
> - `TIMELINE.md` = 决策历史，永不覆盖 → 回答"当初为什么这么定"
> - `RESULTS.md` = 实验数字总表（自动生成）→ 回答"数据长什么样"
>
> 旧阶段（2026-07 ~ 2026-08-02，隐藏状态探针投机执行工具调用线）的全部历史
> 在 git 快照 commit `b1f5b9c` 及更早提交里，本文件不再回溯。

## 2026-08-02 清场，开新阶段

- 决定：旧阶段实验全部终止，结果不再需要。仓库只保留现役代码
  （`run.py` 注册表引用的 `pipeline/` `ops/` `envs/`）、部署好的环境、模型权重。
- 删除：NFS 实验产物约 116G（pipeline 训练/注入产物、new1_runs、bert_runs、
  bert_data、原始轨迹）；home 侧旧线代码目录、方向/论文文档、一次性发射脚本、
  文献 clone。删前先打快照 commit，git 里可回溯（NFS 数据除外，已不可恢复）。
- 保留：`envs/` 各基准环境（alfworld 数据挪到 NFS `envs/alfworld_data`，
  软链已改指）、mbert-env / cprobe-env / vllm-env 等虚拟环境、
  `/net/tokyo100-10g/data/str01_01/y-guo/models` 模型权重。
- 四本账（TIMELINE / DATA / runs.jsonl→RESULTS / WORKPLAN）清零重建骨架，
  记账机制（`ops/record.py`、`ops/gpu_jobs.py`、run.py 注册表）原样保留。
