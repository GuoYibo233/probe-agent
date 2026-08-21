# DATA — 数据设定与口径

> 只写设定与口径，**不写结论**——结论归 `RESULTS.md`。
> 2026-08-02 清场后重建。旧阶段的数据口径见 git 快照 commit `b1f5b9c`。
> 新阶段第一批数据造出来时，把"怎么采的 / 怎么变成样本 / 版本 / 规模与
> 先验基线"按节补进来。

## 新实验开工前的检查清单

旧阶段踩过的坑抽成的通用规则，每开一批新实验按顺序过一遍：

1. **用的是哪一版数据？** 版本不同的数字不可比，版本号写进 run_id 和记录。
2. **先验基线取对了吗？** 先验基线随数据版本变，每版单独记，不许跨版本套用。
3. **档位/难度编号只用一套定义。** 代码里的编号和文档里的编号一旦有两套就会颠倒。
4. **要比耗时吗？** 先确认对比的两条臂跑在同一型号的卡上，否则耗时列作废。
5. **种子写死了吗？** 造数据/训练一律固定随机种子并写进报告，重跑逐样本一致。
6. **重建过的数据做逐字节对比了吗？** 建库脚本有排序不稳定的前科，重建后必须比对。
7. **同一个探针要评多个数据配置吗？** 用符号链接分身，否则回放报告互相覆盖。
8. **动了 `WORKPLAN.md` 里任何一条判断吗？** 补一条 `TIMELINE.md`。
9. **生成设置走预设了吗？** 换 effort/温度/预算这类生成设置，先在
   `configs/presets/` 开一份新预设（不改旧份），run_id 里带上预设名；
   轨迹 meta 会自动落 preset 名和展开后的 gen_settings，事后可核对。

## aw_p1_v1 — p1 批采集数据（2026-08-21 造）

**怎么采的**：run_id `p1`。被采模型 gpt-oss-120b（双 vLLM 实例，tokyo108
两张 H200），预设 `gptoss_harmony_high`（api harmony、reasoning_effort high、
温度 0.0、start_date 2026-08-06），`--max-steps 30`，seed 20260729。题单是
AppWorld 官方三堆全量 315 题：train 90 / dev 57 / test_normal 168，文件在
`envs/appworld/data/datasets/{train,dev,test_normal}.txt`（⚠️ 三份 txt 末尾
无换行，`wc -l` 各少 1）。轨迹 315 份全部末行 final，落
`envs/runs/p1/appworld_gptoss`（穿软链在 NFS）。

**怎么变成样本**：配方 `annotate-chain`（ann-build → ann-params →
ann-check-callstr），config `pipeline/configs/p1_gptoss.json`。规则：全句边界
前缀、事件内等权 w=1/m_i、每事件边界上限 MAX_BOUNDS=64、官方题单任务实例级
三路切分（dev 作 val）。

**版本与规模**（数字出自 `ANNOTATE_REPORT.md`）：数据目录
`pipeline/data/aw_p1_v1/gptoss`（NFS）。事件 4048、样本 175359；
train 90 实例·1098 事件·46438 样本 / val 57·675·29202 / test 168·2275·99719；
工具词表 83 类（长尾出现<5 次的 57 类）；题干长度 p50=4645 / p90=13364 /
max=47019 字符（超 4096 token 由训练脚本左截）。参数标注在 `params/` 三堆，
行数与主数据逐堆相同。

**先验基线**：test 事件级频率先验 0.419（全猜最高频工具
`apis.api_docs.show_api_doc`）。本版单独记，不跨版本套用。

**门禁与重建**：`check_callstr` 门禁 A（模型归属 175359 行全对）、
B（样本键全唯一，315 unit 各对一条 traj）、D（题单归属全量核对）通过；
C 跳过（appworld 不走 runs.glob 路径）、E 跳过（无 SPLIT_REPORT.json，
官方切分无此件）。真值调用串回读 4041/4048（0.9983），含逗号参数实例
5/5267。重建对比（检查清单第 6 条）：build+param_label 重跑一遍，
七个数据文件与全部报告逐字节 cmp 一致。

**口径备注**：与 aw_official_v1 的数字不可比（effort 档不同，见
`plans/2026-08-21-p1-collection-plan.md` 生成设置一节），只作数量级参照。
