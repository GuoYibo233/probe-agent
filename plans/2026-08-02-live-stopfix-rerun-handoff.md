# 交接书：活跑停止符 bug 修复 → 验证 → high 双臂重跑

> 写于 2026-08-02，交给新对话执行。上一会话已完成六臂活跑 + 归因，本文自足，
> 不需要读旧对话。词表见 `plans/PLAINWORDS.md`；活跑=in-loop live rollout。

## 0. 一句话任务

修 `live_appworld.py` 的回合越界 bug（模型自演环境污染上下文），用 14 道确诊题
冒烟验证，然后 high 档 probe/noprobe 双臂全量重跑（v2），出干净的
"探针 vs 无探针"任务级成功率。慢的问题两条根都已处理或将随本修复消失（§4）。

## 1. 案情（已坐实，不必复查）

- 六臂活跑已收官，run_id：`20260802_0136_live_aw_gptoss`（high 双臂）、
  `20260802_0240_live_aw_effort`、`20260802_0306_live_aw_probe_effort`。
  数字在 `RESULTS.md`，逐臂 LIVE_REPORT 在
  `pipeline/inject/runs/live_aw_gptoss/<arm>/`（v1 证据，**不许覆盖**）。
- v1 终表：w0 基线 28.6%(48/168)；probe(high) 11.9%(20)；noprobe(high) 7.1%(12)；
  low/med 四臂 4.8–8.9%（effort 结论定性成立，**不重跑**）。
- 差距归因（14 题多 agent 逐题验尸，14/14 排除日期假设）：
  **停止符漏洞**。`live_appworld.py:150` 用 `stop=DEFAULT_STOP`，而
  `replay_inject.py:156` `DEFAULT_STOP=["<|return|>"]`——没把 `<|end|>` 当回合
  终点。harmony 历史里 assistant 收尾渲染成 `<|end|>`，模型时常学样用 `<|end|>`
  结束 final 后**继续写**：伪造 `<|start|>assistant` 新回合 + 伪造
  `Execution output:` 假环境返回（假 API 文档/假密码/假回执），整段进
  `msgs` 污染后续，模型以为活干完了，真 API 一次没调，空手 `complete_task`，
  测试全 `no_op_fail`。
- 污染面（gen content 含伪造 "Execution output:" 的题）：noprobe 22%(37/168)、
  probe 12%、其余臂 5–11%；中毒≈必死（各臂中毒题成功 0–2）。
  撞 64k 的题（noprobe 39/probe 27）一部分也是假回合吹大上下文的下游。
- 诚实条款：v1 里 probe 的 +4.8pt 优势有一部分是"探针出手恰好打断越界续写"
  （中毒率 12% vs 22%），**修完才知道干净优势**。这是重跑的核心动机。

## 2. 修复规格（只动 `pipeline/inject/live_appworld.py`）

盯住 `gen_step`（约 130–205 行）。结构：分段 completions 循环（每段
`--chunk-tokens`=64），累计文本 `full`；解析在 195–205 行：
`full.partition(END_MARK)` 切思考，`rest.split(FINAL_OPEN)[1]` 取 content。
`END_MARK="<|end|>"`（第一次出现=analysis 结束，合法）、
`FINAL_OPEN` 从 replay_inject import。

改两处，皆以"final 通道已开启"为前提（`END_MARK in full` 且 `FINAL_OPEN in rest`）：

1. **客户端截断（必做，兜底）**：content 里扫描第一个
   `<|end|>` / `<|start|>` / `<|return|>`，有则截断到它之前、本步判 done、
   跳出分段循环。伪造内容进不了 msgs，token 不再白烧。
2. **动态 stop（建议，省 token）**：final 开启后的后续分段请求，把 stop 换成
   `["<|return|>", "<|end|>", "<|start|>"]`。不能全程用——第一个 `<|end|>`
   是 analysis→final 的合法转场，会把思考掐死。

红线：
- **不动 `replay_inject.py` 的 `DEFAULT_STOP`**——回放实验已入账，语义不能漂。
- 158–162 行的 `done` 判定与 8192 单步上限逻辑先读懂再动，别顺手重构。
- 顺手加 `--task-ids`（逗号分隔）参数：现在只有 `--n`/分片，没法点名跑题，
  冒烟要用（见 §3）。

## 3. 验证协议（过了才准全量）

1. **解析单测**（纯 CPU）：构造含越界的合成文本
   `"think...<|end|>" + FINAL_OPEN + "正文```python\ncode\n```<|end|><|start|>assistant伪造..."`
   过新解析，断言 content 恰好截到伪造前。
2. **14 道确诊题冒烟**（w0 全做对过，v1 活跑全做错）：
   `024c982_2 0a9d82a_2 0d01c76_1 13547f5_3 31dc501_1 3b8fb7a_3 522e5e5_2
   59fae45_1 634f342_2 8749218_1 9dabbc9_1 c77c005_2 f3f60f0_1 ff58e36_2`
   用 `--task-ids` 跑 noprobe 模式进独立 smoke 目录。验收线：
   (a) 全部 content 零 "Execution output:"、零 `<|start|>`；
   (b) 成功率显著回升（w0 在这 14 题上 14/14，修好后预期救回大半；
   若仍 <7/14，停下重新归因再全量）。
3. 冒烟过 → 全量。

## 4. "慢"的两条根（都已处理，别重复造闸）

- **静态分片堵尾**：已换动态领题 `--pool`（mkdir 原子票，commit 4c7588d），
  `live_arm_job.sh` 已带 `--pool` 并在起跑前 `rm -rf .claims`。重跑直接受益。
- **失控沉思烧 token**：最胖 10% 题占 19% 生成量零成功——主体就是越界自演，
  本修复顺带治掉。**60k/题预算闸经用户讨论明确不加**，别自作主张补。

## 5. 重跑规格（v2，只跑 high 双臂）

- **新目录，别覆盖 v1**：`pipeline/inject/runs/live_aw_gptoss_v2/{probe,noprobe}`。
  `live_arm_job.sh` 的 outdir 是写死的——加个版本变量或第二参数再用。
- 服务（都要现起，上一轮已全部释放、显存归零）：
  - vLLM ×3：`python3 envs/serve_logs/launch_vllm_splice.py`
    （tokyo108 g0/1/2 → 8114/8115/8116，会跳过已存在 session；
    发射前 `ops/gpu_jobs.py free` 实探，g5 可能被隔壁会话 ro1aw 评测占着，别碰）。
  - 探针服务：tokyo105 g0，port 8790，tmux `new1_live_probe_t105g0`：
    `cd /home/y-guo/reproduce/new1 && CUDA_VISIBLE_DEVICES=0 ./cprobe-env/bin/python
    pipeline/inject/probe_server.py serve --port 8790 --device cuda:0`
    （日志进 NFS logs 目录。high 档用老 /render 即可，effort 字段无关）。
- 臂参数照 v1：`--split test_normal --max-steps 30`，probe 臂无额外 flag、
  noprobe 臂 `--no-probe`；θ=0.925 在探针服务里，别动。
- 双臂各 12 工人，PORTS 轮转 8114/8115/8116，tmux session
  `new1_live_run_probe_t108` / `new1_live_run_np_t108`（在 tokyo108 上起）。
- 走 **gpu-run skill 全生命周期**：发射前 commit → tmux → 台账
  `gpu_jobs.py register`（run_id 建议 `live_aw_gptoss_v2`）→
  `record.py start --track C2-3 --seed 20260729` → 监控 → 收尾五连。
- 预计时长：v1 双臂约 3.5h；修复砍掉越界烧的 token + `--pool` 去尾，应明显更快。

## 6. 打分与判读

- 逐臂：`cprobe-env/bin/python pipeline/inject/score_live.py
  --live-dir pipeline/inject/runs/live_aw_gptoss_v2/<arm>
  --base-root envs/runs/w0_aw_official/appworld_gptoss`
  （score_live 已修三处 bug——commit b31f57d，直接用，别回滚）。
- 判读顺序：
  1. noprobe_v2 vs w0 28.6%：框架对齐度。若仍差一大截，剩余嫌疑=64-token
     分段边界重分词漂移（日期假设已死于 14/14 排除，不必再挖）；
  2. probe_v2 vs noprobe_v2：**干净的方法优势**，这是要的最终数字；
  3. 撞 64k 题数应双双大降（v1: 27/39）；
  4. 中毒率复测应为 0（§1 的 grep 口径）。
- 收官：record finish 记数字；结论若改动 v1 那条 TIMELINE 的判断
  （2026-08-02"活跑六臂收官"条，内含红旗），**必须追加新 TIMELINE 条目**
  说明 v2 取代 v1 口径；LIVE_REPORT 入库 commit。

## 7. 坑单（每条都踩过）

- 登录机 `python`→`python3`；grep 是 ugrep 7.5.0，`-qv` 空输入返回 0，
  判断脚本只用正向匹配。
- 一切远程命令**绝对路径**；`cd && a & b &` 的 cd 只绑第一个后台任务，
  死过 11 个分片——批量发射用脚本，别拼串。
- 只用 tmux（禁 bare ssh/nohup）；日志写
  `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/`，本地读有
  NFS 属性缓存延迟，从 tokyo108 读。
- HTTP 400=上下文超 65536，驱动已接住记 `abort=context_overflow_400`
  照常 evaluate（commit 2c8efaa），别改语义。
- 发射前 `gpu_jobs.py free` 实探空卡，别人的进程=禁区；发射前必 commit；
  大产物进 net 盘；收尾必须杀服务+显存归零+销号，别占卡过夜。
- 进程计数用 `--exp` 精确匹配（`noprobe` 包含 `probe`，ps 会自匹配多数）。

## 8. 指针

- 代码：`pipeline/inject/live_appworld.py`（修这里）、
  `pipeline/inject/replay_inject.py`（只 import，别改）、
  `envs/serve_logs/live_arm_job.sh`、`envs/serve_logs/launch_vllm_splice.py`、
  `pipeline/inject/score_live.py`、`pipeline/inject/probe_server.py`。
- 数据：v1 六臂 `pipeline/inject/runs/live_aw_gptoss/`；w0 对照
  `envs/runs/w0_aw_official/appworld_gptoss/`（168 条，只读）。
- 33 道全量分歧题（w0 对活跑错、非撞线，冒烟 14 题之外的备用验证集）：
  024c982_2 09b0ee6_2 0a9d82a_2 0d01c76_1 0d01c76_2 1150ed6_3 13547f5_3
  31dc501_1 31dc501_2 31dc501_3 325d6ec_1 3b8fb7a_3 425a494_2 522e5e5_2
  59fae45_1 59fae45_3 5a83b05_2 634f342_2 8749218_1 8749218_2 8749218_3
  9dabbc9_1 c77c005_2 c77c005_3 ccf4b82_3 cef9191_2 cef9191_3 f323bae_3
  f3f60f0_1 f3f60f0_2 f3f60f0_3 ff58e36_2 ff58e36_3
- 相关 commit：2c8efaa（400 补丁）、4c7588d（--pool）、966b05e（六臂收官账）、
  b31f57d（score_live 三修，另会话）。
