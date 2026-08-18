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

## 2026-08-18 三臂逐 token 同（ident3_v1）：活跑重发改用模型自己的 token id，5 题 × 10 遍量噪声

- 触发：gyb 要求把 chat baseline / no probe / probe-but-nofill 做到逐 token 同，5 题
  每题每臂 10 遍看结果。探针权重已删，nofill 臂用伪触发（每步第 5 个句尾切口开火、
  中断、按模型自己的 id 重发、什么都不塞）。
- 决定（实现层，计划 `plans/2026-08-18-ident3.md` §5 E1–E13）：活跑流带
  `return_token_ids`，开火重发 = 前缀 + 模型自己生成的 id[:k] + 单独编码的 NOTE，
  不再把文本整段重分词；head = 盖住句尾标点的最短 id 前缀、切口按起点计数（两者只看
  token 序列不看流分块——vLLM 有 stop 串时压 9 字符不吐、生产快时多 token 并块，
  块边界不是 token 边界）；步预算按留下的 id 算；发射前门禁核 chat 的
  prompt_token_ids 与 /render 逐 id 相等。
- 事实（`ident3_v1`，RESULTS.md；`…/runs/ident3_v1/IDENT3_REPORT.md`）：150 跑 0 失败；
  跨臂 prompt id sha 1780/1780 全等（三臂喂引擎的 prompt 逐 id 同已成立）；
  2175 对同题配对没有一对整题逐 token 全同，每题每臂 10 遍 10 条不同轨迹；首分叉在
  第 0 步的比例同臂对 chat-chat 137/225、noprobe-noprobe 144/225、nofill-nofill
  131/225，跨臂 chat-noprobe 308/500、chat-nofill 499/500、noprobe-nofill 496/500；
  成功 chat 14/50、noprobe 13/50、nofill 20/50；nofill 564 次中断重发里 534 次
  （0.947）逐位复现被丢弃的溢出 token。三臂并行打同一副本（批组成随时变）。
- 与上一条"服务端数值抖动当噪声"的关系：这批数字是那层噪声在整题上的量；同臂
  10 遍之间就已经条条不同，臂间比较只能靠题量。
- 未做：真探针下的活跑（要先重训探针）；nofill 与 noprobe 首分叉几乎全在第 0 步而
  同臂对只有六成——这个差别没有分析，先记事实。

## 2026-08-18 立项：塞法回放（splice_replay_v1）——探针开火时结果怎么拼回去，先上帝视角量单步

- 触发：对比 with probe 重发 prompt 与 no probe 时量到重分词缝——NOTE 前导 `\n`
  与模型的 `.\n\n` 合成一个 token（换行切口 3558/3865 不齐，空格切口全齐）；
  顺势问"塞回去的方式"本身哪种最好。探针权重已删（`c1_gptoss_*`），活跑起不来。
- 决定（gyb）：不等探针，拿 5 条 chat baseline 轨迹做上帝视角回放：52 个单调用步 ×
  思考的 66/75/80/100% 句尾切口 × 十臂（思考内 4 种措辞 + system 预告 / 塞完强切
  正文 ×2 / 伪造整轮留思考 / harmony 原生 python 工具），每条只续一步，不跑到底、
  不 evaluate、不判预测对错。切口比例四个点是 gyb 定的。
- 裁决点 D1–D14 全在 `plans/2026-08-18-splice-replay.md` §6（缝修法 D5'：head 以
  空白结尾不加前导换行；n1 措辞改塞代码块原文 D13；`<|call|>` 是 eos、所有臂都停 D11）。
- 结果：`splice_replay_v1_srv`（RESULTS.md）；`…/pipeline/inject/runs/splice_replay_v1/SPLICE_REPORT.md`。
  上帝视角下退化的两种塞法（伪造整轮丢思考 = 跳到下一步；结果随下一轮到 = baseline）没跑。
- 未做：真探针下的活跑（要先重训探针）；把胜出塞法接进 live_appworld。

## 2026-08-18 裁决：服务端数值抖动当噪声，不再追逐字复现

- 触发：`cmp_chat_noprobe_5_srv4` 量了 7 个冷/暖分叉位——top-1/top-2 logprob 差全是
  0、0.125、0.25（bf16 logit 一格 0.125），6 个至少一态精确平局；两态同位 top-1
  logprob 差 ≤0.17 nat。分叉出在模型本来分不出高下的位上，是服务端 bf16 + 缓存
  命中数决定数值路径的属性，不是臂的属性；种子对 argmax 无用。
- 决定（gyb）：当噪声。不做"关前缀缓存 + 串行"的复现验证，不追两臂逐字同；
  两臂对比靠题量平这层噪声。上一条"没定案前不放量"的挂起解除。
- 未验、留档：同进程内"关缓存 + 串行"是否逐字稳定；跨进程重启是否稳定。

## 2026-08-18 五题实跑：no probe 与 chat baseline 的分叉来自前缀缓存状态，不来自端点

- 触发：`cmp_chat_noprobe_5`（tokyo108 单副本 gpt-oss-120b，`VLLM_SYSTEM_START_DATE`
  钉 2026-07-31；两臂各跑 test_normal 前 5 题，串行、一次只飞一个请求）。
- 事实：五题第 0 步 prompt token 数两臂全等（341/341/341/336/337）；3 题第 0 步
  输出就不同，2 题到第 2/3 步才分叉；成败 chat 3/5、no probe 3/5，题不同。
  同 prompt 反复打：暖缓存下 completions(ids) 与 chat 逐字同；清缓存后重发与
  暖时不同（13/13），冷/暖两态内部各自两端点逐字同（13/13）。chat 跑里第 0 步
  "异样"的三题正是当时那条 prompt 首次进服务（缓存未命中）。
- 决定：no probe 与 chat baseline 的口径对齐到此为止（渲染/采样/停止/切分已逐层
  同）；两臂要可比，下一步是把服务端状态压成一致（候选：`--no-enable-prefix-caching`
  + 串行；`VLLM_BATCH_INVARIANT=1` 对 MXFP4 起不来，作废）。没定案前不放量。
- 产物：`/net/.../pipeline/inject/runs/cmp_chat_noprobe_5/{chat,noprobe,analysis}`；
  台账 `cmp_chat_noprobe_5_srv{,2,3}`。

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
