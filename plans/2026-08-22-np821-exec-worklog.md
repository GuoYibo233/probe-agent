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

## b17_cgen 三次落位定稿（2026-08-23 07:17–07:2x）

- b17_ctool 07:17 在 H100 gpu1 收官（acc 0.6867、ALIGN PASS 2.14e-04、
  墙钟约 1.5h），销号 + record finish 完毕，gpu1 实测 0 MiB。
- cgen 重发到 gpu1：用只含 cgen 一格的临时排卡表
  （`$CLAUDE_JOB_DIR/tmp/np821b17_cgen_only_placement.json`，不进 git）
  发射，避开 launch-probe 对已完成 ctool 格的「重发→守卫秒退→假登记」坑；
  正式表 `ops/np821b17_placement.json` 的 cgen 行同步改成 108 gpu1 留档。
- 登记实况：台账 active 有正确的新 session 条目（launch-probe 的
  「登记失败」WARN 与实况不符，以 jobs.json 为准）；record start 复用
  05:44 那条（commit 7dbd28e，重复 run_id 拒新增），实际发射 commit 是
  097d81c——差异只有排卡表与 worklog，训练代码同一版，RUNMETA 第 4 条
  钉的是 097d81c，追溯以 RUNMETA 为准。
- 全批 12 run 的落位定格：b06=H100×3、b17 ctool/cparam=H100 gpu1/2、
  b17 cgen=H100 gpu1（接棒 ctool）、l17=Ada×3、l4=H200×3。
- 四批训练是否跨批并行占卡（smoke 实测速度后裁，过程性，记本文件）。
- LoRA smoke 实测 ETA 若跑不成立，裁换卡/缩配（口径类，进 TIMELINE）。
- e2 各批风险档按 REPLAY_REPORT 的 chosen_theta 定（口径既定，只记执行结果）。

## b17 两格收官（2026-08-24 15:34）

- cgen best_val_ce 0.512（H100 gpu1 接棒 ctool，含改道折腾，从 097d81c
  重发算起墙钟约 32.2h）；cparam best_val_ce 0.3378（H100 gpu2，约 30.1h）。
- 两 run 逐个销号 + record finish，b17 批 3/3 齐。全参两批（b06/b17）
  六格全部收官。

## l4_cgen 收官（2026-08-25 04:25），9/12 齐

- best_val_ce 0.371（Qwen3-4B LoRA+gc，H200，墙钟约 64.2h）。末 epoch
  val_ce 0.5716 比 best 差，best/ 取自更早 epoch，权重文件齐。
- 销号 + record finish 完毕。余 3 格：l4_cparam 在末次验证段（H200 验证
  约 2.5h，预计 08-25 晨收）；l17 cgen/cparam 在第 2 epoch 边界验证
  （Ada，预计 08-26 晨收）。

## l4_cparam 收官（2026-08-25 04:5x），10/12 齐，l4 批 3/3

- best_val_ce 0.3375（Qwen3-4B LoRA+gc，H200，墙钟约 64.4h）。末 epoch
  val_ce 0.4186、val_exact_params 0.77，best/ 权重齐。销号 + record
  finish 完毕。
- 108 实探：gpu3/4/5 归零（l4 释放干净，且原占 gpu3 的他人进程已走）；
  gpu0/1/2 各 34–36G 被他人占用（b17 08-24 已收官，非我方残留）。
  预写的 eval_tool 排卡表指向 108 gpu0-3，届时按实探改排。
- 余 2 格：l17 cgen/cparam（Ada，g11650/17484，预计 08-26 晨收）。

## 分工变更：评测线移交分支会话（2026-08-26 03:5x）

- 用户开分支会话「new-exp-plan ⑂ 我想先评测一下目前微调好的部分」，
  下令先评测已训完的 10 格。两会话分工：
  分支管全部评测线（e1_tool/e2_call/矩阵、驱动器 t2→t3→e1 推进、
  Phase D 收官、Phase E 回写 skill）；本会话只管 l17 cgen/cparam
  训练监控与收官（销号 + record finish + 回执 + commit），收官后
  发消息通知分支，由分支补发 l17 的 e2_call。
- 本会话从此不敲 `run.py pipeline`、不发评测任务，避免重复发射与
  state.json 冲突。台账两边都只经 run.py gpu-jobs/record 写（有锁）；
  git 提交各自只 add 自己动的文件。
- 分支 03:5x 实探：108 六卡全空、105 八卡全空（此前占 108 gpu0/1/2 的
  他人进程已走），评测优先用 108。

## 裁决 7：评测不另做 smoke，用发射验活 + 首进度行代替（分支会话，2026-08-26 03:5x）

- 事实：驱动器 e1/e2/m1 的完成判据只看产物文件（各批 ctool 的
  REPLAY_REPORT.json、cgen/cparam 的 CALLGEN/PARAM_REPORT.json、
  MATRIX md），不看 state.json 的发射标记；t2_full 要 12 格全齐才放行。
  所以现在用 `launch-eval` 直接评已训完的格，之后驱动器敲到评测段会
  直接认作完成，不冲突（skill C4 本来就写着"逐格收官逐格派评测"）。
- 裁决：不另做评测 smoke。依据：同一版评测代码在 p1 的 b06/b17 两批
  （0.6B、1.7B 底座）全量跑通过；三个训练脚本存 best/ 前都
  merge_and_unload，LoRA 格 best/ 与全参格逐项同构（l4 model.safetensors
  16.09G、l17 6.88G，都是合并后整模），评测脚本一律 from_pretrained(best/)
  零改动装回；cgen/cparam 评测的数据三方对拍（头 meta.data / --data /
  ctool meta.data）都指向 nyapass_aw_v1/gptoss。用 `--limit` 做 smoke 要
  复制 16G 的 run 目录，代价高于收益。替代验证点 = 发射 30 秒验活 +
  首条 @hb 进度行。

## 评测发射回执：四批 ctool（2026-08-26 03:58）

- `launch-eval tool` 逐批发：b06→108 gpu0（H100）、b17→gpu1（H100）、
  l17→gpu2（H100）、l4→gpu3（H200），四格 ALIVE，record start 钉
  commit 1edd5ae（树干净），run_id `eval_np821{b06,b17,l17,l4}_gptoss_ctool`。
- 验证点过：四格权重装完后 100 秒内都到 @hb 100/2556（先评 dev 堆
  2556 事件，再评 test 堆 8533 事件）。
- **RUNMETA WARN 文案与实况不符（要回写 skill）**：launch-eval 打
  "没给 --outdir，RUNMETA 没写"，但它随后自己往 `<run>/RUNMETA.json`
  的 `launches` 追加了一条 kind=eval_tool（03:58:10，带 session/gpu/
  log/排卡表）。按 WARN 手补 `run.py runmeta` 的那条（03:59:07）成了
  重复项。回看训练 run 同样：launch-probe 的 12:03:50 条 + 手补的
  12:05:20 条。重复项无害（追溯链只多不少），以后 launch-probe /
  launch-eval 发射后**不再手补 runmeta**，改为读 RUNMETA 核实。
- 监控 b8phu882x：REPLAY_REPORT 落地/日志出错叫醒，30 分钟心跳。
  报告落地后读 chosen_theta 定风险档、写 eval_call 排卡表、发
  b06/b17/l4 的 cgen/cparam 评测；l17 的 call 档等母会话通知训练收官。

## ctool 评测收官 ×3 + call 档发射 ×2（2026-08-26 04:37–04:45）

- 速率实测：评测按事件走（dev 2556 + test 8533 事件），H100 上 0.6B/1.7B
  各约 4.6–4.8 事件/秒，H200 上 4B 约 3.7 事件/秒；一批 ctool 评测约
  40 分钟，远快于按 p1 样本行数外推的 2–3 小时。
- 三批 REPLAY_REPORT（test 冻结，n=8533，先验基线 0.3867）：

  | 批 | θ(0.05) | θ(0.1) | 0.05 档 coverage / trig_acc / earliness / wrong_spec | 温度 |
  |---|---|---|---|---|
  | b06 | 0.975 | 0.9 | 0.261 / 0.9529 / 0.565 / 0.0123 | 1.1959 |
  | b17 | 0.975 | 0.925 | 0.3288 / 0.9533 / 0.4758 / 0.0154 | 1.2359 |
  | l17 | 0.95 | 0.85 | 0.3401 / 0.9476 / 0.5042 / 0.0178 | 1.24 |

  三批 0.05 档都有解，call 档一律缺省风险档（不加 --risk）。
  三格逐个销号 + record finish（run_id `eval_np821<b>_gptoss_ctool`）。
- b06 call 档 04:38 发 108 gpu4/gpu5（H200），b17 call 档 04:45 发
  gpu0/gpu1（H100），四格 ALIVE；排卡表
  `ops/np821{b06,b17}_eval_call_placement.json` 随台账一起提交
  （d4ff119 / e6d1a39）。b06 两格 40 秒内出首进度：cgen 8/2227、
  cparam 16/2227（2227 = θ=0.975 触发的 test 事件数；cparam 跑
  gt_tool / pred_tool 两遍）。RUNMETA 的 eval_call 条由 launch-eval 自写，
  未手补。
- 监控 b7pufajd8 盯 call 档（读台账自动纳入新发的格）。l4 ctool 报告
  未落（H200 上 4B 慢一档），落地后 call 档落 gpu2/gpu3。

## l4 ctool 收官 + call 档发射（2026-08-26 04:46–04:50），四批 ctool 评测齐

- l4 REPLAY_REPORT（test 冻结 n=8533）：θ(0.05)=0.975、θ(0.1)=0.875；
  0.05 档 coverage 0.2569 / trig_acc 0.9599 / earliness 0.3886 /
  wrong_spec 0.0103；温度 1.2704。0.05 有解 → 缺省档。销号 + record
  finish（H200 约 48 分钟）。
- l4 call 档 04:50 发 108 gpu2（cgen，H100）/ gpu3（cparam，H200——两遍
  生成给快卡），ALIVE，钉 15c90e8。至此 108 六卡跑 b06/b17/l4 六个
  call 档评测；四批 ctool 评测报告全在，驱动器 e1_tool 判据已满足。
- 四批 0.05 档 θ 全部有解，e2 的 `--risk 0.1` 退让条款一次都没触发。

## b06 call 档收官（2026-08-26 05:00–05:0x），b06 批三格评测齐

- 两格都是 risk 0.05、θ 0.975、触发 2227 = 评分 2227 个 test 事件、
  parse_fail 0、无参数事件占 0.467。H200 上 cparam 约 22 分钟、cgen
  约 23 分钟（生成速率 1.1–1.4 条/秒）。
- cgen：tool_ok 0.9057 / params_all_ok 0.8702 / full_call_ok 0.8276 /
  exact_call_ok 0.8289 / 参数实例准确率 0.7406（2120 个参数实例）。
- cparam：pred_tool 口径 tool_ok 0.9529 / params_all_ok 0.9026 /
  full_call_ok 0.8752 / exact_call_ok 0.8765 / 参数实例准确率 0.8182
  （2079 个实例）；gt_tool 口径 params_all_ok 0.9106 / 参数实例准确率
  0.8693（1997 个实例）。
- 两格销号 + record finish（run_id `eval_np821b06_gptoss_{cgen,cparam}`）。
- b06 两档矩阵已出：`pipeline/runs/MATRIX_np821b06_r0.05.md` / `_r0.1.md`
  （NFS 产物目录，驱动器 m1 同款命令与文件名）。矩阵脚本两条已知显示
  局限这次都出现：m 线两格（本批没训）标 PENDING；0.1 档表里 cgen/cparam
  两行仍是 0.05 档触发点（θ 0.975）的数——引用 0.1 档表必须配文字说明。

## b17 call 档收官（2026-08-26 05:06–05:0x），b17 批三格评测齐

- 两格都是 risk 0.05、θ 0.975、触发 2806 = 评分 2806 个 test 事件、
  parse_fail 0、无参数事件占 0.3977。H100 上 cgen 约 26 分钟、cparam
  约 27 分钟。
- cgen：tool_ok 0.9006 / params_all_ok 0.8254 / full_call_ok 0.7887 /
  exact_call_ok 0.7876 / 参数实例准确率 0.6927（3095 个实例）。
- cparam：pred_tool 口径 tool_ok 0.9533 / params_all_ok 0.8795 /
  full_call_ok 0.8525 / exact_call_ok 0.8521 / 参数实例准确率 0.8116
  （2957 个实例）；gt_tool 口径 params_all_ok 0.8902 / 参数实例准确率
  0.864（2830 个实例）。
- 两格销号 + record finish；b17 两档矩阵随后出。

## l4 call 档收官（2026-08-26 05:13–05:1x），l4 批三格评测齐；108 六卡归零

- 两格都是 risk 0.05、θ 0.975、触发 2192 = 评分 2192 个 test 事件、
  parse_fail 0、无参数事件占 0.3828。cgen（H100）约 23 分钟、cparam
  （H200）约 24 分钟。
- cgen：tool_ok 0.9056 / params_all_ok 0.8472 / full_call_ok 0.8294 /
  exact_call_ok 0.8271 / 参数实例准确率 0.7291（2676 个实例）。
- cparam：pred_tool 口径 tool_ok 0.9599 / params_all_ok 0.8828 /
  full_call_ok 0.8654 / exact_call_ok 0.8645 / 参数实例准确率 0.8251
  （2590 个实例）；gt_tool 口径 params_all_ok 0.8969 / 参数实例准确率
  0.8794（2488 个实例）。
- 两格销号 + record finish。108 实探：评测 session 清零、六卡显存全
  0 MiB（G7 过）。评测线台账 active 里 np821 相关条目清空。
- 已训完 10 格的评测至此全部收官（4 个 ctool + 6 个 call 档）；剩 l17
  的 cgen/cparam 评测等母会话通知训练收官。

## l17_cparam 训练收官（2026-08-26 14:3x，母会话），11/12 齐

- best_val_ce 0.3146（Qwen3-1.7B LoRA+gc，Ada，墙钟约 98.3h）。末 epoch
  val_ce 0.4518、val_exact_params 0.725，best/ 权重齐。销号 + record
  finish 完毕。
- 余 1 格：l17_cgen 在末次验证段（12:05 前后进验证，预计 15:00 前后出
  done），收官后一并通知分支发 l17 的 call 档评测。

## l17_cgen 训练收官（2026-08-26 14:5x，母会话），12/12 训练全收

- best_val_ce 0.3814（Qwen3-1.7B LoRA+gc，Ada，墙钟约 98.7h）。末 epoch
  val_ce 0.643、val_exact_call 0.505，best/ 权重齐。销号 + record finish
  完毕；107 四卡实测 4 MiB 基线，释放干净。
- np821 十二格训练至此全部收官。四批 best_val_ce 汇总（cgen/cparam）：
  b06 0.4793/0.396、b17 0.512/0.3378、l17 0.3814/0.3146、l4 0.371/0.3375；
  四 ctool best_calA_weighted_acc：b06 0.6883、b17 0.6867、l17 0.6974、
  l4 0.7016。
- 训练监控收摊（监控任务在 TRAIN_ALL_DONE 后自行结束），已发消息通知
  分支会话补发 l17 的 call 档评测并出 l17 矩阵。本会话职责清空。

## l17 call 档发射（2026-08-26 15:0x，分支会话）

- 分支亲核母会话的收官事实：两格 train_log 的 done 事件（0.3814 /
  0.3146）、best/ 权重齐、runs.jsonl 有 finish、台账 active 空、树干净在
  7076c34、108 六卡实探全空。
- l17 ctool 的 0.05 档 θ=0.95 有解 → call 档缺省风险档。排卡表
  `ops/np821l17_eval_call_placement.json`（cgen→108 gpu0、cparam→gpu1）
  提交 fad9abe 后 `launch-eval call` 发射，两格 ALIVE，record start 钉
  fad9abe。监控 b7pufajd8 从台账自动纳入。
- 驱动器此时不敲：e2_call 见 l17 两份报告缺、又无发射标记，会再发一遍
  l17 的 call 档（驱动器不查台账里在飞的 eval 任务）。等报告落地再敲
  t2→t3→e1→e2→m1 一路过，m1 只补 l17 两档矩阵（已存在的六份跳过）。

## 根因修复：RUNMETA 两个写手 → register_all 唯一写手（2026-08-26 15:1x）

- 根因：`launch_common.register_all` 自带 RUNMETA 步（给 outdir 才写，顺序
  台账→记录→RUNMETA），两个排卡发射器 `launch_probe` / `launch_eval` 为了
  "发射真实发生就先钉代码、后面登记拒绝也不能丢"在调它之前各自先
  `append_runmeta` 一条（带 session/gpu/log/排卡表），再传 `outdir=None`
  ——于是 register_all 打出 "WARN 没给 --outdir，RUNMETA 没写"，与实况相反。
- 修法（肯定式、单一写手）：RUNMETA 步挪到 register_all 最前面（顺序改为
  RUNMETA→台账→记录），新增 `runmeta_kind` / `runmeta_extra` 参数，写失败
  只 WARN；两个发射器删掉私写，改传 outdir + kind + extra。`run.py launch`
  没给 --outdir 时的 WARN 保留（那是真没写）。
- 测试：`tests/test_launch_{probe,eval}.py` 去掉对私写的 patch，改为断言
  outdir/kind/extra 传到了 register_all；`tests/test_launch_common.py` 加
  两条（record 拒绝时 RUNMETA 已落盘；kind/extra 进了记录且只有一条）。
  四份发射器测试 57 条全过，`run.py selfcheck` 过。
- 文档：gpu-run SKILL.md Phase 4 的登记顺序与 WARN 语义改写；probe-pipeline
  的 stage-commands 里"launch-probe 不写 RUNMETA / 看到 WARN 要自己补"两句
  等回写 agent 交付后由本会话改（避免与 agent 同时编辑同一文件）。
- 本批 12 个训练 run 与 6 个评测 run 目录里已有的重复 RUNMETA 条目
  （发射器一条 + 手补一条）原样保留：追溯链只多不少，不回头删产物记录。
