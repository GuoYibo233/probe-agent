# new1 工程规则

## GPU 任务：唯一入口是 gpu-run skill

任何要用显卡跑的程序（训练/推理/探针/vLLM，不分大小）一律走
`.claude/skills/gpu-run/SKILL.md` 的全生命周期流水线：
探卡 → 挑卡 → smoke → tmux 发射 → 登记台账 → 交监控命令 → 巡检 → 收尾/中断。
禁止绕过它手搓 ssh/nohup 启动。

- 集群慢变量（驱动/CUDA/坑）：`ops/gpu_state.md`
- 任务台账：`ops/jobs.json`，只通过 `python ops/gpu_jobs.py register/finish` 读写
- 用户自助监控：`python ops/gpu_jobs.py watch`
- 实时空卡：`python ops/gpu_jobs.py free`（永不信缓存的占用状态）

## 其他铁律

- 与 `/home/y-guo/ACL2026` 完全隔离：不读写其数据/代码/结果（硬件共用没问题）。
- 环境一律 uv 管理。
- 模型权重下载到 `/net/tokyo100-10g/data/str01_01/y-guo/models`，不放 /home。
- 动手前先取得同意；一个请求只做那一件事。
