# 14 — 采样器上线

**What to build:** 采样器在登录机 tmux 常驻起来（session 名 new1_sampler，日志 tee 到 monitor 目录），crontab 每 5 分钟查一次 session、不在就拉起（装之前先备份 crontab）。采样器无状态，重启后从采样历史恢复接着算。上线后网页能看到真任务。步骤照实施计划 Task 9 执行。

**Blocked by:** 06 网页与 json 出口

**Status:** claimed

- [ ] curl 本机 8377 端口的 /json 出合法 JSON
- [ ] 浏览器（端口转发）看到任务表
- [ ] 杀掉 session 之后 5 分钟内 crontab 把采样器拉回来

## Comments

- 2026-08-08 主会话转记（发射前部署约束，实现时必须照办）：其一，常驻 tmux session 和 crontab 看门狗行必须指向主仓 /home/y-guo/reproduce/new1 的代码与 run.py，绝不许指向你自己的临时工作树路径（收尾会被删除，指过去就是悬空）；其二，后续工单 12（事故触发）、13（vLLM 服务档）合并进 main 后采样器需要重启一次才吃到新代码，这件事记进你的报告提醒主会话，不用你做。
