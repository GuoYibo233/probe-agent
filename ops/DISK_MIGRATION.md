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
- `pipeline/runs/c2_*`（非 smoke）—— 2026-08-02 已全部软链化，现场 `ls -la` 验证：
  `c2_gptoss_{cgen,ctool,mext,mtool}`、`c2_q36_{cgen,ctool,mext,mtool}` 全部是
  `-> /net/.../reproduce/new1/pipeline/runs/c2_*` 的软链（不是本次审计大修对话做的，
  是 c2 训练发射脚本本身直接写 NFS 的产物，8 个软链 mtime 05:02 / 16:51 不等）
- `pipeline/data/` —— 活任务在读
- `pipeline/runs/smoke/` —— 2026-08-02 已由审计大修对话搬完，除 2 个活跑关联目录
  （`c2_q36_mtool_smoke`、`c2_q36_cgen_smoke`）外已全部软链化（见下）

## pipeline/runs/smoke/（2026-08-02 审计大修对话，E25）

盘点 19 个条目：6 个此前已是软链（ro1aw/ro1bf 的 cgen/ctool/mext，走 `new1_runs/` 那套根），
11 个实体目录本次 rsync -a --delete 逐个搬到 `reproduce/new1/` 这套根并核对
（文件数一致；`du -sb` 差异 <1%，4 个 <1KB 的小目录因 NFS 块分配 du 显示 1.4~1.5%
但用 `diff -r` + `wc -c` 核对内容字节级一致，判定通过）：
`align_gptoss`、`align_q35`、`align_q36`、`c1_q35_cgen_smoke`、`c1_q35_ctool_smoke`、
`c1_q35_mext_smoke`、`c1_q35_mtool_smoke`、`c2_q36_ctool_smoke`、`c2_q36_mext_smoke`、
`ro1aw_q35_mtool_smoke`、`ro1bf_q35_mtool_smoke`。

跳过 2 个未搬（仍是实体目录，别动）：
- `c2_q36_mtool_smoke`、`c2_q36_cgen_smoke` —— jobs.json 里 `c2_train_rerun2`
  这个 active 任务的 session 名 `new1_c2_q36_mtool_t107g0` / `new1_c2_q36_cgen_t107g1`
  与这两个目录名相关，按任务安全检查口径跳过（已用 `find -mmin -120` 核实这两个
  smoke 目录本身没有近期写入，且用日志时间戳确认活跑实际写的是
  `pipeline/runs/c2_q36_mtool` / `c2_q36_cgen`，不是 `smoke/` 下这两个目录——
  但为保险按名字关联规则原样跳过，没有强行验证后搬）。

两套 NFS 根并存（`ro1aw/ro1bf` 的 cgen/ctool/mext 三个用 `new1_runs/`，
其余全部用 `reproduce/new1/`），要不要统一由用户定，本次未改动已存在的软链路径。

## 第二轮（2026-08-01 晚，用户批准后执行）

- 搬走：整个 `/home/y-guo/self-ensemble`（42G）→ NFS 同名目录，原位软链，9691 个文件核对一致
- 删除（全部可用 uv 重建）：`related_work` 五个 `.venv`（33G）、`fig1_pilot/fig1-env`（15G）、
  `reproduce/SDFT/.venv`（9.6G）、`reading_nlp_ex1/minimind/.venv`（5.3G）
- `uv cache clean`：清掉 65.8GiB（prune 只能清 594KB，真正占量的是与已删 venv 硬链接的包本体）
- `.vscode-server`：删 7 个旧 server 版本 + 3 个孤儿二进制，保留现役三个（e4c7e7b1 / 1b50d58d / f6cfa2ea）
- 只动了 /home/y-guo 自己的东西；vllm 缓存（3.3G）与 ACL2026 未动

## 遗留手尾

- ~~`/net/.../y-guo/reproduce/new1/pipeline/runs/smoke` 是本对话留下的过时不完整副本，应删除~~
  —— 2026-08-02 审计大修对话已用 `rsync -a --delete` 把 home 侧 11 个实体目录逐个
  补齐覆盖进这套 NFS 根，现在是权威本体（home 侧对应条目已换软链，见上）。
  剩 `c2_q36_mtool_smoke` / `c2_q36_cgen_smoke` 2 个因活跑名字关联跳过，NFS 侧这两个
  仍是搬迁前的旧快照，等 c2_train_rerun2 结束后再补搬。
- `uv cache prune` 被权限拦截，没跑；`.cache/uv` 现场实测 **158M**（2026-08-02，
  与此前笔记的"名义 67G"口径不一致——67G 是清理前的历史记录，本次 `du -sh ~/.cache/uv`
  直接测得 158M，说明后续已经被清过或本来就没那么大，未深究原因）。
