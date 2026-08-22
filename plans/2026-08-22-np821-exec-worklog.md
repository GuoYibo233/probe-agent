# np821 执行块 worklog（2026-08-22 开跑，Claude 自主运行）

gyb 2026-08-22 授权：执行块全程自主运行，所有停点由 Claude 裁决并落档，gyb 回来检查。
本文件是过程性裁决与推进纪录；口径类裁决另记 TIMELINE。计划本体在
`plans/2026-08-21-np821-plan.md`。

## 开跑前预检（执行块 todo 1 + 追加三路，2026-08-22 早）

- NFS 空间：/net/tokyo100-10g/data/str01_01 可用 43T。本批需求最坏加总约 187G
  （新数据集 ≈ p1 的 1.3G×4 = 5.2G；新轨迹 ≈ 479M×4 ≈ 1.9G；test 档 logits
  缓存 ≈ 32M×4 = 128M；12 个训练 run 的 checkpoint 按 p1 实测三档外推，全 4B
  档最坏 15G×12 = 180G）。占可用不到 0.5%，放行。
- 配置核对：np821_gptoss.json、manifest_np821.json、configs/presets/default.json
  逐项与计划口径总表一致；gpt-oss-120b 权重 15 个分片在 NFS 齐全；题单
  wc -l 89/56/167（无末尾换行，实际 90/57/168，共 315 题）。
- DATA.md 开工检查清单九条过完：数据版本进 run_family（nyapass_aw_v1）、种子
  写死进 manifest、生成设置走新预设 default（预设名与展开后的 gen_settings
  自动落轨迹 meta）；逐字节重建对比、TIMELINE 补录排在标注环节。
- 工作树干净，HEAD a8566db。

## 裁决 1：采集卡位照 manifest 占位值 2/3/4/5，不改

实探（gpu-jobs free）tokyo108 六张大卡全 FREE。占位值 2/3/4/5 正好是
1×H100 95G + 3×H200 143G，三张 H200 全拿，是六张里能凑出的显存最大的四张组合；
不改文件工作树保持干净，c2 的 G2 门禁发射时又实探了一次兜底。属过程性裁决，
不进 TIMELINE。

## 采集发射回执（2026-08-22 05:40–05:50）

驱动器五敲全过（gpu-runner agent 执行）：

- c1_gen：三件生成物落 envs/runs/nyapass/（launch_servers.py /
  launch_clients.sh / MANIFEST.md），卡号端口逐条核对。
- c2_servers：四个 vLLM 实例发射，session
  `new1_nyapass_srv_gptoss{a,b,c,d}_t108g{2,3,4,5}`，端口 8103/8106/8107/8108。
- c3_health：05:40:42 起轮询，05:44:42 四端口全通，用时约 4 分钟，无 session 掉线。
- c4_smoke：1 题 × 4 条轨迹 264 秒跑完，G4 判据全过——4 个文件 `_r0.._r3` 齐、
  末行 final、meta 种子 42/67/4267/6742 按 r0..r3 逐条对上、温度 1.0 /
  effort high / 预设 default。4 条里 3 条 eval success=True、1 条 False
  （轨迹质量不是门禁项，照常放行）。
- c5_clients：12 个客户端分片发射（登录机，session
  `new1_nyapass_gptr_s0..s3` / `gpdv_s0..s1` / `gptn_s0..s5`），分片任务数
  360+228+672 = 1260 与题单×4 对上。三处登记驱动器自动补齐：gpu-jobs 五个名
  （nyapass + nyapass_srv_a..d）、record start（run_id nyapass、track
  collect_nyapass、commit a8566db、树干净）、RUNMETA.json 第 1 条。

发射后指针停在 c6_done（launched）。产物目录
`envs/runs/nyapass/appworld_gptoss/`，客户端日志 `envs/runs/nyapass/logs/`，
服务日志 `envs/serve_logs/`。

## 监控安排

常驻采样器在跑（网页 8377）。主会话另架一个常驻监控（5 分钟一轮）：
12 个客户端 session 全退 → 叫醒推进 c6（先杀四个 vLLM 再敲，G7 才过得去）；
服务 session 数变化或 90 分钟无新文件 → 叫醒排查。
预计墙钟 6 小时起（p1 实测折 52 题/h/实例 × 4 实例，温度 1 只会更慢）。

## 等待期侦察摘要（2026-08-22 上午，两个 agent 读代码所得，行号见 agent 报告）

后九步路线的要点，验证与开跑都按这里走：

- a1 停点：驱动器自己按 max_bounds=10^9 扫全部轨迹出未截断切点分布
  （p50/p90/p99/max + 超 32/64/128/256 计数），写进 state.json 的
  cutpoint_stats。裁决写法是往 np821_gptoss.json 顶层加 `"max_bounds": <数>`，
  留 64 也必须显式写。max_bounds 不进状态指纹，改配置不会撞 ident。
- max_bounds 语义：限每事件（一步的 think 文本）切出的样本数；超限走
  下标近似等距抽稀、末尾切点永远保留，抽掉的是思考中后段的渐进决策点样本。
  p1 基线：4048 事件、每事件边界数 min 1 / med 56 / max 64（这份统计
  本身被 64 截断过，p1 的真实截断率读不出来）。
- a2 每敲整链重跑 annotate-chain（build → param_label → check_callstr），
  门禁 A/B/D 在 check_callstr 里硬拦；a3 做 G9/G11 加 12 件产物重建逐字节
  cmp（备份目录 `<data_out>_rebuild_ref`，NFS 要多备一份数据集大小）。
- 改完配置进训练段之前必须 commit（t1 一开头查脏树）。
- t1_smoke 只验判据：12 格 smoke 要手发，产物目录必须叫
  `pipeline/runs/smoke/<批>_gptoss_<格>_smoke`。b06 可走
  `launch-probe smoke`；b17/l17/l4 逐格手发 train_causal_{tool,callgen,param}.py
  `--smoke`，旗标照 p1 台账同形（b17: --base qwen17 --grad-ckpt；l17: 再加
  --lora；l4: --base qwen4 --lora --grad-ckpt；ctool 带 --align-tol 3e-4）。
- smoke 排布草案（兼答排卡两问）：b06 与 b17 六格放 tokyo107 48G 实测
  装不装得下（b17 若 OOM 则答案记「48G 装不下」，该格 smoke 挪 108 重跑过门禁）；
  l17 与 l4 六格放 tokyo108 大卡实测 LoRA 速度。
- t2_full 一敲发一批、四批严格串行（pend[0]），跨批并行要手发且有
  「驱动器补发假 RUNMETA」的坑——是否跨批并行等 smoke 实测速度后再裁。
- 驱动器不读 batches 里的 base/mode，--base/--lora/--grad-ckpt 全由排卡表
  extra 决定；12 份排卡表（4 训练 + 4 eval_tool + 4 eval_call）现在一份都
  没有，要在各自发射前手写，形状照 p1 的同名表。
- 评测风险档：ctool 一次算完 0.05/0.10 两档进 REPLAY_REPORT.json；发 e2 之前
  先读各批 REPLAY_REPORT 的 chosen_theta——0.05 有解按缺省发，无解就把
  `--risk 0.1` 写进该批 eval_call 表的 extra（写 0.1 不许写 0.10，矩阵按
  字符串键取数）并在报告标注。这样 0.05 无解不会变成 tmux 里静默退 1。
- launch-probe/launch-eval 发射后驱动器退出码不保证进程活着（§6.3 偏离）：
  发完必读 logs/pipeline/nyapass_aw_v1/t2_full.log 等分步日志尾部的
  alive check，再用 gpu-jobs 盯。

## 采集收官回执（2026-08-22 10:38–11:0x）

- 12 个客户端全部自然退出，1260/1260 文件全部末行 final（主会话逐文件核过，
  零坏件）；41 条轨迹顶到 30 步上限。
- 四个 vLLM session 杀净，GPU 2/3/4/5 显存实测 0 MiB；驱动器 c6 一敲全过：
  五个号销掉、record finish 落 trajs=1260 / units=315 / steps30_hit=41
  （41 与主会话独立核数一致）。
- 实测墙钟：05:50 发射到 10:5x 收齐约 5 小时，速率约 260 条/小时（四实例），
  比 p1 折算的预估略快。

## 裁决 2：max_bounds 留 64（口径类，已进 TIMELINE 2026-08-22 条）

a1 停点统计：15216 事件，未截断切点 p50 60 / p90 246 / p99 572 / max 842，
超 32/64/128/256 的事件 10417/7271/4019/1408。各候选上限下的分堆样本量
（boundary_counts 同款代码实算）：

| 上限 | train | dev | test_normal | 总量 | train 对 p1(46438) |
|---|---|---|---|---|---|
| 64 | 186479 | 115211 | 391893 | 693583 | ×4.02 |
| 96 | 238893 | 148731 | 505964 | 893588 | ×5.14 |
| 128 | 277594 | 174279 | 590482 | 1042355 | ×5.98 |
| 256 | 358380 | 228864 | 768824 | 1356068 | ×7.72 |
| 不截 | 402722 | 263063 | 881153 | 1546938 | ×8.67 |

三堆事件数 train 4127 / dev 2556 / test_normal 8533。裁决理由四条见 TIMELINE
当日条（预算吻合、等权下长尾支配、抽稀保深度覆盖、可逆）。

## smoke 回执（2026-08-22 中午，12 格全过）

判据四项（start/done/best/、ctool 加 ALIGN PASS）12 格全过，四个 ctool 的
对齐检查全 PASS（b06_ctool 的 align_maxdiff_hidden 4.53e-05，tol 3e-4 内）。
排卡两问的硬答案：

- **48G 装不下 0.6B 全参（无检查点）**：tokyo107 上三格全 OOM（traceback
  存档 `logs/smoke_np821b06_cparam.oom_t107.log`），挪大卡后实测峰值
  ctool 60.2 / cgen 76.8 / cparam 76.7 GiB——差的不是一点。装下装不下的
  分水岭是 `--grad-ckpt`，不是模型大小。
- **48G 装得下 1.7B 全参+检查点**：峰值 ctool 35.4 / cgen 44.1 /
  cparam 44.1 GiB，对 47.5 GiB 可用只剩 3.4 GiB 余量。
- LoRA 显存小：l17 峰值 17.3/34.7/34.7，l4 峰值 32.1/37.6/37.6 GiB。
- smoke 的 ips 是污染下限（区间含验证前向与 200 条生成，step 事件在 smoke
  规模下一条都不写），不用于 ETA；ETA 基准换 p1 实跑墙钟。

p1 实跑墙钟（runs.jsonl，×1 数据）：b06 在 H100 上 ctool 0.57h、cgen/cparam
各 6.07h；b17 在 H200 上 ctool 0.55h、cgen/cparam 各 8.72h；LoRA 在 A6000 上
只有 ctool 完成过（l17 1.53h / l4 3.53h），cgen/cparam 无 finish 记录。

## 裁决 3：四批排卡与并行策略（过程性）

数据 ×4.02 推算：b06 的 cgen/cparam 在 H100 约 24.4h；b17 同格在 H200 约
35h（H100 略慢）。排布：

- 现在发三批：b06 → 108 H100 idx0/1/2（唯一装得下 60–77G 峰值的空卡组）；
  l4 → 108 H200 idx3/4/5（最大模型配最快卡）；l17 → 107 Ada idx0/1/2
  （峰值 ≤35G 余量 13G，零 OOM 风险）。
- b17 等 b06 跑完接它腾出的 H100 idx0/1/2（约 +24h，驱动器串行顺序正好
  轮到它）。b17 不上 Ada：44.1G 贴 48G 只剩 3.4G，几十小时的 run 不冒
  中途 OOM 的险。Ada idx3 留备用。
- 驱动器只敲两次 t2（发 b06、b06 完发 b17）；l17/l4 用 launch-probe full
  手动发（同一登记代码路径）。两次敲之外 t2 不敲，避开「部分完成批被
  驱动器补发假 RUNMETA」（driver.py:1260-1269 注释的场景）。
- LoRA 大卡速度无历史数据：发射后 1–2 小时从 train_log 的 step 事件取
  实测 ips 重算 ETA 落档，跑不成立再裁（见待办）。

## 训练三批发射回执（2026-08-22 下午）

- t1 门禁 12 格 smoke 判据全过（loss 在降一项 smoke 规模写不出 step 记录，
  驱动器按已知口径记「没判」不拦）。
- t2 第一敲发 np821b06 → H100 idx0/1/2，三格 ALIVE；l4 → H200 idx3/4/5、
  l17 → Ada idx0/1/2 用 launch-probe full 手动发，六格 ALIVE。九格全部
  record start 在 commit 1b9334f（树干净）。
- launch-probe 不写 RUNMETA（WARN 实录），九个 run 已逐个补
  `runmeta --kind train`，命令取自台账 cmd 字段，追溯链完整。
- b06_cgen 的 start 记录确认全量在训：n_train 186479 / 总步数 17484
  （批 32、3 epoch）。
- 监控：采样器 + 30 分钟心跳（step 事件的 ips 直读），b06 三格 done 即
  叫醒敲 t2 发 b17（接 H100 0/1/2），任何格无 done 死亡即告警。

## 待办的裁决点（预告）

- ~~标注 a1_stats 切点分布出来后裁 `max_bounds`~~（已裁：留 64，见上）。
- ~~四批训练是否跨批并行占卡~~（已裁：三批即发 + b17 接棒，见裁决 3）。
- ~~裁决 4 待做~~（已裁，见下）。

## 裁决 4：LoRA 实测 ETA 跑得成立（过程性，2026-08-22 15:02 终算）

方法说明：台账的 record 窗口时长不可信（p1b06_cgen 台账 6.07h、train_log
真实 5.60h），ETA 一律用 train_log 的 step 事件时间戳算。早期速率严重低估
稳态——p1 与 np821 的全参 cgen 前 100 步都只有 ~5.4 gstep/min，稳态爬到
13.5 以上；LoRA 没有这个爬速曲线，从头就稳。

两小时稳态窗口（13:01→15:02）实测：

- b06 cgen/cparam：稳态已过 16.7 gstep/min 且还在爬，剩余 ETA ≈ 15h，
  预计 08-23 早晨收官 → b17 接棒 H100。
- l17 cgen/cparam（Ada）：3.31 gstep/min，剩余 ≈ 85h（3.6 天），
  预计 08-26 凌晨收官。
- l4 cgen/cparam（H200）：3.31 gstep/min，剩余 ≈ 85h，同上。

裁决：**跑得成立，不砍不改**。依据：85h 远低于 A6000 推算的 170/380h
（换大卡的目的达到了）；b17 接棒用的是 b06 腾的 H100，与 LoRA 两批零冲突，
LoRA 跑满期间没有任何任务在等这六张卡；砍掉或缩配省不出任何东西，评测
和矩阵横竖要等这些 run。计划「ETA 跑不成立属推翻前提」的条款没有触发，
无口径变更，不进 TIMELINE。

三个 ctool 已全量收官并逐 run 收账（销号 + record finish）：
b06 acc 0.6883（H100 约 1.0h）、l17 acc 0.6974（Ada 约 3.2h）、
l4 acc 0.7016（H200 约 3.0h），ALIGN 全 PASS。

## b06 收官与 b17 接棒（2026-08-23 晨）+ 裁决 5：cgen 改道 Ada

- b06 全批收官：ctool acc 0.6883、cgen best_val_ce 0.4793、cparam
  best_val_ce 0.396，三 run 逐个销号 + record finish。epoch 边界验证
  （val 115211 行 + 200 生成）每次约 1 小时，两格墙钟约 18h。
- 变故：b06 腾出的 108 gpu0 与 l4_ctool 腾出的 gpu3 先后被他人进程占用
  （gpu0 用户 glin 51.8G 已跑 7h48m；gpu3 pid 3144460 50.9G）。别人的卡
  是禁区，不碰不等确定释放时间。
- 裁决 5：b17 的 ctool/cparam 落 108 gpu1/gpu2（H100，正常发射 ALIVE）；
  cgen 改道 107 Ada gpu3（备用卡）。依据：smoke 在 Ada 上实测 cgen 峰值
  44.1G 稳定跑完，全量峰值同构（max_len 同批大小同）；等被占大卡释放
  时长不可知。发射后 2 小时测 Ada 稳态速率：若 ETA 拖过 08-26 中午且
  届时有大卡已释放，早期止损重发（放弃 2 小时 Ada 进度换 35h 大卡时长）。
- 驱动器在第一次发射（gpu3 SKIP）时已打 launched 标记，补发走手动
  launch-probe（ctool/cparam 存活 SKIP，只发 cgen），三处登记齐，
  RUNMETA 三 run 补钉在 commit 7dbd28e。

## 裁决 6：b17_cgen 在 Ada 首个 backward 就 OOM，改等安全大卡（2026-08-23 05:50）

- 事实：发射 6 分钟后第一个 backward OOM（要 4.64G 只剩 3.61G；PyTorch
  实占 34.75G + 碎片保留 8.63G，traceback 在 tmux 日志
  `new1_np821b17_gptoss_cgen_t107g3.log` 全文保留）。smoke 的 500 条
  子集没踩到全量首批的序列组合——「smoke 峰值 44.1G 可容」这个裁决 5 的
  前提被实证推翻，48G 对 b17_cgen 全量记「装不下」。
- 裁决：不做 expandable_segments 分配器实验（省下的时间对不上 30 小时级
  run 中途再 OOM 的风险），cgen 改等安全大卡：b17_ctool 约 08:00 在
  H100 gpu1 收官后落 gpu1；108 的 gpu0/gpu3 被占卡若更早释放就用先空的。
  监控盯两个条件任一触发叫醒重发。
- 已清理：死 session 杀净（gpu3 显存 4 MiB 空卡基线）、台账销号；失败
  attempt 的 record start 留在 append-only 的 runs.jsonl 里，重发时再记
  一条新 start，不冲突。
- 四批训练是否跨批并行占卡（smoke 实测速度后裁，过程性，记本文件）。
- LoRA smoke 实测 ETA 若跑不成立，裁换卡/缩配（口径类，进 TIMELINE）。
- e2 各批风险档按 REPLAY_REPORT 的 chosen_theta 定（口径既定，只记执行结果）。
