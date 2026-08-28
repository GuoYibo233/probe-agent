# 04 probe-pipeline skill 回写

Status: ready-for-agent
Blocked by: 02, 03（并且要等主会话的 GPU 冒烟裁决出来：`--max-len` 与 `--tok-budget` 的定值会在本工单的 Comments 里给出，没有那条 Comment 不许开工）
Spec: `.scratch/kvshare-train/spec.md` 第 8、13 节；回写规矩 `.claude/skills/probe-pipeline/SKILL.md` Phase E（第 231 到 261 行）与 `references/extending.md` §6

## 要做的

按 `extending.md` §6 的对照表逐行打勾，只改下面六份文件，写法照各文件既有格式：

1. `MAP.md` 第 88 行那张训练表：cgen、cparam 两行的程序列改成 `pipeline/train/train_causal_share.py`，关键设定列用工单 03 报告里的文案；ctool 行的关键设定列补工单 02 报告里的文案；新增一行 `(共用)` 给 `pipeline/train/share_data.py`（文案在工单 01 报告）；新增一行 `(参照)` 给两个旧脚本，写「逐行参照实现，只用于对齐检查与对照，产物不进矩阵」。
2. `.claude/skills/probe-pipeline/references/stage-commands.md`：§3 训练命令与参数表加 `train_causal_share.py` 的真实命令（从工单 03 报告里抄 CPU 冒烟命令，GPU 命令由 `python3 run.py show train-cgen` 生成），参数表加 `--mode / --tok-budget / --events-per-mb / --accum / --eval-per-epoch / --align-*`；第 213 行的 smoke 限额行加新训练器的 40 个训练事件 / 16 个评估事件；§3.4 或批次前缀所在位置补 `ks828`（新口径的批次前缀，`ks828b06` / `ks828l17` 这样的形状）；§7 接口陷阱加三条：`--mode` 必填、`train-cgen-rows` 是参照不是现役、`--tok-budget` 超预算的事件独自成块。ctool 的参数表改默认值（`--max-len` 定值、`--accum 2`）。
3. `references/invariants.md`：先 `grep -n "4096\|accum 8\|32 个事件\|截断\|epochs 3\|bs 4"` 把所有写着旧口径的行找全（至少有：causal 超参那行的「bs 4 事件 / accum 8 / epochs 3」、cgen 目标构造那行的「按 max_length = 4096 − …左截」、上限那行、第 52 行「smoke 规模」那行——新训练器的 `--smoke` 是按全文 token 数升序取 40 / 16 个事件，不是按 SEED 随机抽），ctool 的 `--bs/--accum` 按 Comment 里的定值写，逐行改成新口径——上限（Comments 里的定值）、超长事件整条丢弃、一次更新 8 个事件（cgen/cparam 是 4 个事件一个逻辑小批 × 累积 2，ctool 是 bs 4 × accum 2）、cgen/cparam 1 个 epoch 每四分之一评一次、ctool 3 个 epoch、`--tok-budget` 定值。每处保留一句「np821 批用的是 4096 / 32 个事件 / 3 个 epoch」。
4. `references/extending.md`：§5 静默表加三行。#25：位置 `train_causal_tool.py` 与 `eval_tool.py` 的读取位置规则，触发条件是切点前的 token 跨过切点并且切点后是空白，症状是 6.3% 的切点读到句尾标点前一个词的隐状态、训练与离线评测内部一致所以数字不报错；写明 2026-08-28 已改规则让读取位置和全文一次分词的边界一致，**不许写成「活跑错位已修」**（活跑生成的 token 边界和离线全文分词可能不同，是另一个坑，spec 11.3 末段）。#26：`train-cgen-rows` / `train-cparam-rows` 走旧脚本（4096、左截、3 个 epoch），产物 `meta.json` 没有 `trainer` 字段、run_id 形状和现役相同，拿去评测会混进矩阵分不出来。#27：`share_data.py` 顶层 import 旧训练脚本会让 mbert-env 下的 `eval_tool` / `eval_mbert_call` 在 import 阶段 `SystemExit`（版本门在旧脚本模块层），症状是 `eval-tool-mbert` 开跑即死并打「解释器用错了?」。§3 开头第 113 到 121 行的「新格 / 新训法轴」判据后加一句：换实现（格名、数据、评测不变，只换训练脚本）走「新训法轴」那条路，先例是 2026-08-28 的 `train_causal_share.py`；§3.4 的 run_id 那条补一句新口径写进批次前缀 `ks828`。
5. `.claude/skills/probe-pipeline/SKILL.md`：Phase 0 或对应位置提到 cgen/cparam 训练脚本名的地方改成新脚本名（先 `grep -n callgen` 找）。
6. `references/gates.md`：只改写着旧口径数字（4096 / 32 个事件 / 截断）的说明文字，不加门禁编号，不改门禁语义。

## 验收

- `grep -n '^#' .claude/skills/probe-pipeline/references/*.md` 引用的章节号与门禁号都对得上（SKILL.md 第 259 到 260 行的自查）。
- 不新增门禁编号（这次没有新门禁）。
- 不改 `TIMELINE.md`（主会话写）。
- 报告里列出每一处改动的文件与行号。
