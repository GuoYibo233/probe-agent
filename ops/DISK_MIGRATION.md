# 磁盘搬迁协调笔记（2026-08-01）

背景：home quota 打满，c2_train 在 tokyo105 上死过任务。冷数据搬到 net 盘，
原位置留软链接。**有两个对话在同时做搬迁，动手前先读这份文件，别打架。**

## 本对话（quota 清理线）已完成

NFS 根：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/`（镜像 home 目录结构）

已搬走并换成软链接（rsync 后逐目录核对过文件数）：
- `envs/bert_runs`（27G）、`envs/bert_data`（8.1G）
- `fig1_pilot/alfworld_data`（2.2G）
- `pipeline/runs/c1_*` 全部 12 个（约 19G）

没碰的：
- `pipeline/runs/c2_*` —— c2_gptoss_cgen 还在 tokyo105 GPU7 上训练，别动
- `pipeline/data/` —— 活任务在读
- `pipeline/runs/smoke/` —— **归 ro1 那个对话管**（见下）

## ro1 对话（另一条线）在做的

它把 `pipeline/runs/smoke/ro1*` 逐个换成软链接，NFS 根用的是另一套：
`/net/tokyo100-10g/data/str01_01/y-guo/new1_runs/`。

两套 NFS 根并存（`reproduce/new1/` vs `new1_runs/`），要不要统一由用户定。

## 第二轮（2026-08-01 晚，用户批准后执行）

- 搬走：整个 `/home/y-guo/self-ensemble`（42G）→ NFS 同名目录，原位软链，9691 个文件核对一致
- 删除（全部可用 uv 重建）：`related_work` 五个 `.venv`（33G）、`fig1_pilot/fig1-env`（15G）、
  `reproduce/SDFT/.venv`（9.6G）、`reading_nlp_ex1/minimind/.venv`（5.3G）
- `uv cache clean`：清掉 65.8GiB（prune 只能清 594KB，真正占量的是与已删 venv 硬链接的包本体）
- `.vscode-server`：删 7 个旧 server 版本 + 3 个孤儿二进制，保留现役三个（e4c7e7b1 / 1b50d58d / f6cfa2ea）
- 只动了 /home/y-guo 自己的东西；vllm 缓存（3.3G）与 ACL2026 未动

## 遗留手尾

- `/net/.../y-guo/reproduce/new1/pipeline/runs/smoke` 是本对话留下的**过时不完整副本**
  （比 home 少 2 个后写入的文件），应删除；本对话没有 /net 写权限删不掉。
- `uv cache prune` 被权限拦截，没跑；用户可自己跑（`.cache/uv` 名义 67G，
  与各 venv 硬链接共享，quota 只记一次）。
