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

## 待办的裁决点（预告）

- 标注 a1_stats 切点分布出来后裁 `max_bounds`（口径类，进 TIMELINE）。
- 四批训练是否跨批并行占卡（smoke 实测速度后裁，过程性，记本文件）。
- LoRA smoke 实测 ETA 若跑不成立，裁换卡/缩配（口径类，进 TIMELINE）。
- e2 各批风险档按 REPLAY_REPORT 的 chosen_theta 定（口径既定，只记执行结果）。
