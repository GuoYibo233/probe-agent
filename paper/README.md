# paper/ — 论文写作专区

这个目录只管"写论文"这一件事：正文草稿、LaTeX 源文件、图表源文件、投稿检查清单。
实验代码、数据、运行记录不放这里（照旧走 ops/ 三层记录）。

## 目录约定

- `FORMATTING.md` — ACLPUB 官方格式规则的本地对照表（来源见文件头），写作和投稿前自查用。
- LaTeX 模板用官方 style files：https://github.com/acl-org/acl-style-files
  （clone 下来的模板仓库属第三方代码，不进本仓库 git，放在本目录下会被忽略或另放。）
- 草稿、表格、图源文件后续按需建子目录（如 `figures/`、`tables/`、`sections/`）。

## 硬约束提醒

- 与 `/home/y-guo/ACL2026` 隔离：不引用其文件。
- 数字一律出自 `ops/runs.jsonl` / `RESULTS.md`，写进论文的每个数要能追到 run_id。
