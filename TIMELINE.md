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

## 2026-08-18 no probe 的 prompt 改成 chat 端点同款 token id，三个臂定名

- 决定：no probe 与 chat baseline 之间凡是代码能对齐的差异一律向 chat 端点
  对齐：`/render` 不再走 jinja 出文本，改照抄 vLLM chat 端点的渲染直接出
  token id，驱动器把 prompt 以 id 列表发；chat baseline 的 `--reasoning-effort`
  缺省改 high、单题异常按题兜底。服务端批组成的数值抖动不在客户端能对的
  范围，留待发射时试 `VLLM_BATCH_INVARIANT`。
- 依据：同日逐层对 vLLM 0.26.0 源码并实测，jinja 文本路在两处与 chat 端点
  不齐（空 content 的 assistant 轮被 chat 端点整条丢掉；content 里字面
  `<|...|>` 标记被 completions 端点收成真特殊 token），任一触发后每步 prompt
  永久偏离；其余各层（采样参数、停止 token、输出切分、环境种子）对码相同。
  细节在 `METHOD.md` §2.1 与 §6-⑤⑥，裁判测试 `tests/test_harmony_render.py`。
- 定名：chat baseline / with probe / no probe（`CONTEXT.md`，同日）。
- 与旧记录的关系：2026-08-02 `awdiag_job.sh` 排查「活跑 noprobe 17.3% vs
  w0 28.6%」时上述两处与 `\n\n` 渲染差、chat 侧日期未钉都还在，那次数字
  不能归因到单一原因。

## 2026-08-08 探针线重启，定性为实验空间，METHOD.md 立为方法真源

- 决定：重启探针投机执行工具调用这条线，定性从"一个定死的方法"改成
  "一个实验空间"：主干循环定死，探针读什么、用什么模型、参数怎么来、
  触发怎么判、塞什么、何时塞、工具类型怎么分、一步之内何时收手，
  一共八根轴排队待试。方法规范落在根目录 `METHOD.md`（当日定稿），
  文档为准、操作向文档改齐。
- 定案要点：θ 永远手动给定，不给就拒绝启动；同设铁律与空注入对照立为
  机制验收；注入格式同效四判据（R1 到 R4）；工具类型暂不区分；
  旧阶段数字一概不作参照；现役 setting 是 gpt-oss-120b 加 AppWorld。
- 依据：2026-08-08 的 grilling 会话逐题定案，词汇当日收进 `CONTEXT.md`
  （同时把词汇表范围从监控/发射扩成全仓库）。

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
