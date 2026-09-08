# p1 批次采集计划 — 给新探针三种训法 × 三档底座供数据

2026-08-21 定。上游设计是 `plans/2026-08-21-new-probe-training.md`：ModernBERT 线停跑，
因果线扩成三种训法（ctool / cgen / cparam）× 三档底座（0.6B / 1.7B / 4B）。
NFS 上的数据集目录现在是空的（2026-08-02 清场删了旧轨迹，z1 冒烟批测完也删了），
所以这轮比较要先从采集走起。本计划只管采集与造数据；训练怎么发（SFT 细节、
第一轮 1.7B 的超参）另行讨论，不在本文件里定。

## Phase 0 五变量

| 变量 | 取值 | 依据 |
|---|---|---|
| BATCH | `p1` | 新前缀,与 w0/c1/c2/z1/ro1 都不撞 |
| ENV | `appworld` | 现役 setting（METHOD.md：gpt-oss-120b 加 AppWorld,TIMELINE 2026-08-08） |
| MODELS | `gptoss` 单模型 | 用户 2026-08-21 裁决：九格比较的变量全在探针侧,一个被探测模型够用 |
| CELLS | `ctool cgen cparam` | m 线两格 2026-08-21 起停跑（设计文档第一条总体决定） |
| DATA_ROOT | `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/data/aw_p1_v1/` | 大产物直落 NFS 铁律;数据版本号跟批次走,与 aw_official_v1 / aw_z1_v1 都不混 |

## 规模

- 官方题单三堆全量：train 90 题、dev 57 题（作 val）、test_normal 168 题，共 315 题
  （用户 2026-08-21 裁决）。
- 题单直接用 `envs/appworld/data/datasets/{train,dev,test_normal}.txt`。
  三份题单两两无交集,2026-08-21 已实测（244 个场景各 3 变体,无一场景跨堆）;
  发射前照例再跑一遍 `comm` 对拍留证。
- ⚠️ 三份 txt 文件末尾都没有换行,`wc -l` 各少 1（89/56/167）,G9 核数时按 +1 算。

## 生成设置（effort 档 2026-08-21 已裁决）

用户裁决：新开 `gptoss_harmony_high` 预设（照抄 harmony_medium,只把
reasoning_effort 改成 high;DATA.md §7 第 9 条：换 effort 开新预设不改旧份）。
理由：活跑线的 `gptoss_live_high` 预设是 effort high,探针上场时读的是 high 档
生成的思考,训练数据取同一档,分布对得上。代价照实记：high 档思考更长,采集墙钟
和每事件切点数都会比 medium 口径涨;与 z1 小样口径不同（z1 数字本无参照价值）。

| 预设 | api | effort | 温度 | start_date | 状态 |
|---|---|---|---|---|---|
| `gptoss_harmony_high` | harmony | high | 0.0 | 沿用 2026-08-06 | 本批用,要新建 |
| `gptoss_harmony_medium` | harmony | 不传（提示词落 medium） | 0.0 | 2026-08-06 | 旧口径留档不动 |

其余口径定死：`--api harmony`（活跑线走 /render harmony token id,采集同 api 口径）、
温度 0.0、seed 全链 20260729、`--max-steps 30`（gen_launch CLIENT_COMMON 现值）。

## 采集前的准备工作（五件,都是 CPU,2026-08-21 当天全部做完）

1. **`envs/runs` 软链** ✅：home 的 `envs/runs` 清场后不存在,而 gen_launch 生成的
   客户端 sh 里解释器路径和产物路径同用一个 `envs_root`,不能把 envs_root 指到 NFS。
   已按既有惯例建软链：`envs/runs -> /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/envs/runs`
   （实测穿链能看到 NFS 侧的 hcap 目录）,并已往 `.gitignore` 的「已搬 NFS 的目录软链」
   节加裸名条目 `envs/runs`（尾斜杠匹配不到软链本体,2026-08-02 踩过）。
2. **gen_launch 的 gptoss 客户端预设改成可配** ✅：原来写死
   `GPTOSS_CLIENT_EXTRA = "--preset gptoss_chat_high"`。已加 manifest 顶层可选字段
   `gptoss_client_preset`：缺省 `gptoss_chat_high` 老 manifest 行为逐字节不变,
   给了名字就校验 `configs/presets/<名>.json` 存在（缺文件退 2）。
   顺手把 MANIFEST.md 模板里写死的「六实例起齐」改成按实际实例数出字。
   stage-commands §7 的接口回写随本轮 Phase E 一起做。
3. **预设** ✅：`configs/presets/gptoss_harmony_high.json` 已建
   （照抄 harmony_medium,只改 reasoning_effort 为 high）,preset_loader 实测装载：
   api=harmony / effort=high / 温度 0.0 / start_date 2026-08-06。
4. **标注 config** ✅：`pipeline/configs/p1_gptoss.json` 已建,照抄 `aw_gptoss.json` 改四处：
   `run_family: "aw_p1_v1"`、`traj_runs: ["/home/y-guo/reproduce/new1/envs/runs/p1"]`
   （经软链落 NFS,目录本体就是 run 目录,不嵌套——静默点 #20）、
   `data_out: <DATA_ROOT>/gptoss`、题单三个路径照旧。
5. **manifest** ✅：`pipeline/collect/manifest_p1.json` 已建,结构照 manifest_w0：
   - servers：tokyo108 GPU 4/5（H200）起 2 个 gpt-oss-120b 实例（权重 63G,A6000 48G
     装不下只能大卡;这是预排,发射前 G2 实探空卡,卡号有变改 manifest 重新生成,
     排卡结果落 `ops/p1_placement.json`）。
   - clients：单模型三堆 7 分片 —— train 2、dev 1、test_normal 4,全部 `--resume`,
     outdir 标准名 `appworld_gptoss`（gen_launch 强制,别的名字下游静默跳过）。
   - 已 `--dry-run --out-override` 干跑验证：2 服务实例 / 7 分片,客户端
     `GPTOSS_EXTRA="--preset gptoss_harmony_high"`,outdir `$F/appworld_gptoss` 落软链后端。
   - 生成物 launch_servers.py / launch_clients.sh 按 2026-08-02 裁决不进 run.py 注册表。
- 三份题单 comm 对拍已跑：dev∩train = 0、dev∩test_normal = 0、test_normal∩train = 0。

## 发射与验收（全程走 gpu-run skill,本计划只列门禁对应物）

1. G1 发射前 commit（脏树硬门禁）→ G2 实探空卡 → `run.py gen-launch --config manifest_p1.json`
   先 `--dry-run` 看生成的 sh,再正式生成。
2. 起服务 → G3 服务健康全绿 → G4 先跑 1 题 smoke（验轨迹首行 meta 带 task_id、
   末行 final、meta 里 preset 与 gen_settings 落对）→ 放量。
3. 墙钟参照（推算,不是实测）：w0 批六服务三模型 3-5 小时;p1 的 gptoss 题量是
   w0 gptoss 侧（168 题）的约 1.9 倍,服务实例数相同,粗算 6-10 小时。
   c1 实测 gptoss 思考远长于 q36（每事件中位 51 个切点对 3 个）,客户端并发开高一档。
4. 收尾：G6 完整性 —— `appworld_gptoss/` 下 315 个 `appworld_<task_id>.jsonl`,
   每文件末行 `type:"final"`;G7 显存归零 → `gpu-jobs finish` → `record finish` → commit。

## 造数据（CPU,采集收尾后）

1. `build.py` + `param_label.py` 各一次,config 用 `p1_gptoss.json`。
2. 门禁：G9 三堆行数核对（89+1 / 56+1 / 167+1）;G10 单模型批不适用;
   G11 label_call 抽查;`check_callstr` 全量门禁照跑。
3. `ANNOTATE_REPORT.md` 的工具词表与频率先验基线人眼验收,数字进 DATA.md
   （只写设定与口径,结论归 RESULTS.md）。
4. 参照系：aw_official_v1 的 gptoss 侧当年出 2138 个样本级实例、先验 0.404
   （talks/20260809/data/01-settings.md）;口径不同（api 与 effort 可能都变了）,
   数字不可比,只作数量级参照。

## 训练批次的一条约定（先立在这里,发射时照办）

run_id 的拼法是 `<batch>_<model>_<cell>`,里面没有底座档位这一段;同一格用两档底座
训两次会撞 run_id。所以**一个训练批次只跑一档底座**：0.6B 用 `p1b06`、1.7B 用
`p1b17`、4B 用 `p1b4` 当 batch 前缀。SFT 讨论 2026-08-21 已收口（定案记 TIMELINE
当日「第一轮训练定案」条）：第一轮 0.6B 与 1.7B 一起跑,全参、超参锁 0.6B 现值,
两档 × 三格 = 6 个单卡任务排 tokyo108 的 6 张大卡;另开 LoRA 试验线排 tokyo106
的 A6000,覆盖三档底座（批次前缀 `p1l06` / `p1l17` / `p1l4`,gyb 2026-08-21 追加
4B;三档 × 三格 = 9 个单卡任务,tokyo106 十张卡放得下;训法不同也各占一个批次
前缀）,不进锁超参的横比。4B 的 LoRA 在 48G 上装不装得下没实测,发射前 smoke
说了算,挤不进用梯度检查点旗标。

**发射前 smoke 结论（2026-08-21 实测,详见各 smoke 日志 logs/new1_p1*_smoke*）**：
- 1.7B 全参在 H100 95G 三格全部 backward OOM（进程用到 90-93 GiB 再要
  4.64 GiB 失败;ctool 对齐检查本身 PASS,maxdiff_hidden 2.02e-4）。
  处置:p1b17 三格全参加 `--grad-ckpt`（只省激活显存,锁死的超参一个不动）,
  补一轮 gc smoke 过了再发,正式排 H200。
- LoRA 九格里八格 48G 首轮 OOM,加 `--grad-ckpt` 后八格全部退 0;唯一首轮
  就过的 p1l06_ctool 峰值 46114 MiB,离 48G 只剩约 2.5G。处置:九格统一带
  `--grad-ckpt`（0.6B+gc+lora+ctool 组合没单独 smoke,但比已实测过的
  1.7B 同款严格更轻）。4B 的 cgen/cparam 带 gc 峰值 46426 MiB,边距窄,
  正式跑靠采样器盯,挂了 refire。
- 排卡表五张已按此改定:`ops/p1{b06,b17,l06,l17,l4}_placement.json`。

## 自主执行授权（gyb 2026-08-21 离开前口头授权）

gyb 离开期间由 Claude 自主走完整条链，不再逐步请示：
1. 采集放量后盯到收尾（G6 315 文件末行 final / G7 显存归零 / finish / record finish / 提交台账）。
2. 标注造数据（build + param_label,G9/G11/check_callstr/逐字节重建对比,ANNOTATE_REPORT 数字进 DATA.md）。
3. LoRA 实现验收 + 已批的三包修复（保险丝三条/口径补齐三件/测试四件）+ skill 回写欠账,全部落 commit 之后才发训练。
4. 训练 smoke（1.7B 全参显存、LoRA 三档、4B LoRA 挤不进就开梯度检查点）→ 发射前 commit →
   并行发射：全参 p1b06+p1b17 共 6 个单卡任务上 tokyo108,LoRA p1l06/p1l17/p1l4 共 9 个上 tokyo106。
5. 训练发射前如果 research-loop 会话的两个文档（CLAUDE.md/plans/research-loop-parts）还脏着,
   单独一笔注明来源的 commit 收进去过脏树门禁,不和代码改动混在一笔里。
6. 评测也已授权（gyb 2026-08-21 补授权）：训练收尾后按 EVAL_CELLS 依赖序发
   （先 eval-ctool,后 eval-cgen / eval-cparam,cparam 依赖同批同模型 ctool 的
   REPLAY_REPORT）,五个训练批次各自出报告,`summarize_matrix --prefix <批>` 逐批
   出矩阵,record finish 记数;全链跑完写总汇报。评审发现与已批修复清单在
   `plans/2026-08-21-review-findings.md`。

## DATA.md §7 检查清单过账

1. 数据版本 aw_p1_v1,写进 config 与 run_id。 2. 先验基线：ANNOTATE_REPORT 自带,
按本版本单独记。 3. 档位编号：单模型单环境,不适用。 4. 耗时对比：不做。
5. 种子 20260729 全链。 6. 重建对比：aw_official_v1 的欠账这次补上 ——
build 完重建一次做逐字节 cmp（bfcl_mtb_v1 批已有先例流程）。 7. 探针多配置分身：
本批一份数据配九格,评测报告各写各的 run 目录,不共文件,不适用。
8. WORKPLAN 判断变动：收官时核,动了就补 TIMELINE。
