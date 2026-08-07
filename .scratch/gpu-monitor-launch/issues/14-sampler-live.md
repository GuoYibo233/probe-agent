# 14 — 采样器上线

**What to build:** 采样器在登录机 tmux 常驻起来（session 名 new1_sampler，日志 tee 到 monitor 目录），crontab 每 5 分钟查一次 session、不在就拉起（装之前先备份 crontab）。采样器无状态，重启后从采样历史恢复接着算。上线后网页能看到真任务。步骤照实施计划 Task 9 执行。

**Blocked by:** 06 网页与 json 出口

**Status:** ready-for-agent

- [ ] curl 本机 8377 端口的 /json 出合法 JSON
- [ ] 浏览器（端口转发）看到任务表
- [ ] 杀掉 session 之后 5 分钟内 crontab 把采样器拉回来
