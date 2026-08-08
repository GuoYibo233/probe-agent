---
name: handoff
description: 给当前工作线写交接书，让任何接手 session 五分钟内无缝接管。全流程：实探现状（台账/日志/git/runs.jsonl）→ 半成品收敛 → 按六节定式整文件重写 memory 里的 handoff → 同步索引 → 主导权交割（旧 session 收尾模式或立即停手，二选一写死）。Invoke whenever Dungeon♂Master says "写交接书"、"handoff"、"交接一下"、"换个 session"、"收尾交接"、or a session winds down with work still in flight.
version: 1.1.0
---

# handoff — 工作线交接书

交接书的读者是一个什么都不知道的新 session。验收标准只有一条：
新 session 只读这一份文件 + 它指向的路径，能在 5 分钟内接管所有在跑任务、
不踩已知坑、不擅自开未拍板的工作。

## 铁律

- **现状必须实探，不抄记忆不抄旧交接书**。在跑任务逐个 tail 日志拿当下进度，
  写进交接书的每个状态都带绝对时刻（JST）；ETA 写绝对时刻，不写"还有 2 小时"。
- **一条工作线只留一份交接书**，文件名 `handoff-<线名>.md`，放本项目 memory 目录
  （系统提示里给出的那个）。新交接 = 整文件重写，不追记不打补丁——历史在
  git/TIMELINE 里，交接书只描述现在。工作线终结时删文件 + 摘除 MEMORY.md 索引行。
- **未拍板事项单独一节**，逐条注明"问过没答 / 没问过"，接手 session 禁止擅自开工。
- **主导权交割**：一条工作线同一时刻只有一个主导 session。旧 session 写完交接书后
  二选一——**收尾模式**（只看护在跑任务到毕业 + 履行已拍板的收尾义务，即 gpu-run
  Phase 6a 五连）或**立即停手**（什么都不碰）——选了哪个白纸黑字写进交接书，不许含糊。
  两种姿态下都不接新工作，新想法一律写进交接书的队列。接手 session 动手前先确认
  没有别的 session 还在动这条线（两个 session 同时自认主导 = 重复发射 + 互杀 tmux）。
- **半成品先收敛**：交接前，干到一半的手头活能收口的收口并 commit；收不了口的
  回滚到干净状态，在"未结的账"里记四行账目——目标是什么 / 做到哪了 / 还剩什么 /
  下一步的具体命令。不许把没有账目的脏工作树留给接手 session。

## Phase 1 — 实探（四路取证）

1. `python3 run.py gpu-jobs json`：active 台账；逐 piece tail 日志取真实进度。
   判定/速率/ETA 的采样历史目前只在网页出口 `http://localhost:8377/json`
   （登录机常驻采样器落的 `latest.json`）齐全——终端 `gpu-jobs json` 接读同一份
   历史仍在推进（工单 07），接上之前进度靠 tail 日志人工读。
2. `git log --oneline -5` + `git status --short`：HEAD 在哪、有哪些未提交的账。
3. `tail ops/runs.jsonl`：哪些 run_id 有 start 没 finish。
4. 读 `WORKPLAN.md` 当前节 + `TIMELINE.md` 最新条，确认方向没变；变了先补 TIMELINE。

## Phase 2 — 写交接书（六节定式）

```markdown
# <线名> 交接书（<YYYY-MM-DD HH:MM JST>，交接自 session <短id>）
> 旧 session 退场姿态：收尾模式看护到毕业 / 立即停手（二选一写死，附时刻）
## 在跑的任务        台账名 / host / tmux / 当下进度@时刻(来源:`run.py gpu-jobs json` + 采样历史 `http://localhost:8377/json`) / 完成判据 / ETA 绝对时刻 / 收尾义务
## 下一步队列（已拍板） 按序；每条给可直接复制执行的命令 + 成功判据
## 未拍板事项        禁止擅自开工；注明问过没答 / 没问过
## 资产地图          数据 / 脚本 / 环境 / 权重的真实路径；逐条标注是否已 commit
## 已知坑            接手别再踩
## 未结的账          未提交文件 / 没 finish 的 run_id / 没销号的台账 / 没杀的服务
```

frontmatter 按 memory 规范（`type: project`），description 里写明
"接手 session 先读这条"。

## Phase 3 — 落地

1. Write 整文件覆盖到 `<memory目录>/handoff-<线名>.md`。
2. 同步 `MEMORY.md` 索引行（没有就加，有就更新措辞）。
3. 向用户复述三件事：交接书位置、在跑任务一句话清单、
   本 session 收尾模式下还会做哪些动作（此后不接新工作）。
