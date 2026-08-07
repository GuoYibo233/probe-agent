# T14 — 采样器上线：实现报告

## 状态：BLOCKED

工单三条验收，第 1 条完成、第 2 条用等价方式验证、第 3 条卡在权限系统上没法做——crontab 看门狗那一步被 Claude Code 的 auto-mode 权限分类器拦了，写 crontab 的动作直接被拒绝，不是我技术上做不到，是权限系统不让做。详情见下面"自查发现与存疑"。

## 做了什么（对照工单逐条）

工单指向实施计划 Task 9，三步：起常驻进程、装看门狗、验证。按顺序执行：

**Step 1：起常驻进程。** 在主仓 `/home/y-guo/reproduce/new1`（不是我的临时工作树）里跑：

```
tmux new-session -d -s new1_sampler 'python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

日志里 `[sampler] cwd=/home/y-guo/reproduce/new1` 确认进程 cwd 指向主仓，不是工作树；工单评论里明确要求的约束（不许指向临时工作树，因为工作树收尾会删）满足。session 目前活着（`tmux ls` 里 `new1_sampler: 1 windows`），日志三行,无报错:

```
[sampler] cwd=/home/y-guo/reproduce/new1
  python3 /home/y-guo/reproduce/new1/ops/sampler.py
[sampler] web on :8377
```

**Step 2：装看门狗。** 按计划先备份 crontab（`crontab -l > /tmp/crontab.bak`，此步本身没被拦，执行后确认当时无 crontab：`no crontab for y-guo`），再要把下面这行装进去：

```
*/5 * * * * tmux has-session -t new1_sampler 2>/dev/null || tmux new-session -d -s new1_sampler 'python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'
```

写入动作（`... | crontab -`）被 Claude Code 的 auto-mode 权限分类器拒绝，报错原文：

> Permission for this action was denied by the Claude Code auto mode classifier. Reason: Blocked by classifier. ... To allow this type of action in the future, the user can add a Bash permission rule to their settings.

试了两次（一次带备份合并在同一条命令里、一次单独只跑安装行），两次都被拦；`crontab -l`（纯读）不受影响,能正常跑。按实现者规程"不许工作绕过权限拒绝"的要求，我没有尝试用别的手段绕过这道拦截（比如直接写 `/var/spool/cron` 下的文件、用 `at` 代替、写 python 库改 crontab）。crontab 目前是空的,没有被我改动过,`/tmp/crontab.bak` 是空文件（备份于改动前生成，内容与改动前的空状态一致）。

**Step 3：验证。**

- `curl -s localhost:8377/json` 出合法 JSON,已验证:
  ```
  {"sampled_at": 1786143706.27, "rows": [], "extras": {"tokyo105": ["7-29run", "7-31run", "flow-8-1", "new1_sampler", "rc-claude"]}, "incidents_tail": []}
  ```
  `rows` 为空是真实情况——当时台账（`ops/jobs.json` 的 `active`）为空，没有登记中的 GPU 任务在跑，不是采样器的问题。`extras` 里能看到 `new1_sampler` 自己这个 session（台账外提醒机制在工作,符合设计）。
- 浏览器（端口转发）看任务表：我没有真实浏览器可用,用 `curl -s -o /tmp/t14-root.html -w "HTTP %{http_code}"` 代替看了根路径返回,HTTP 200,正文里有 `<title>new1 长程任务监控</title>`、`<h2>任务表</h2>`、`<table...>`,当前显示"当前没有登记在跑的任务"（与台账为空一致）。这是等价验证,不是工单要求的浏览器人眼确认,用户拿浏览器端口转发打开 `localhost:8377` 应该能看到同样内容,但这句话是我基于代码返回内容的推断,不是我亲眼在浏览器里看到的。
- 杀 session 等 5 分钟看 crontab 拉回来：做不了,因为 Step 2 没装成功,没有看门狗可测。**没有实际去杀这个正在跑的 session 来测试**,因为看门狗不在,杀了就是真的下线,不是测试。

## 怎么验证的

- `python3 -m unittest discover -s tests -v`（在我的工作树、部署动作之前跑,确认起点代码健康）：
  ```
  Ran 41 tests in 3.249s
  OK
  ```
- `NEW1_MONITOR_DIR=/tmp/t14-monitor-smoke python3 run.py sampler --once` 冒烟（隔离目录,不碰生产 monitor 目录）：跑通,`latest.json` 是合法 JSON,`rows` 为空（隔离目录没有台账）。
- 部署后 `curl -s localhost:8377/json | python3 -m json.tool`：合法 JSON,内容见上。
- `curl -s -o /tmp/t14-root.html -w "HTTP %{http_code}"`：`HTTP 200`,内容见上。
- `tmux ls | grep sampler`：`new1_sampler: 1 windows (created Sat Aug 8 07:23:39 2026)`,部署后多次复查仍在。
- `tail -30 /net/.../monitor/sampler.log`：三行,无 traceback。

## commit 清单

无。本工单按实施计划 Task 9 只涉及"登录机 crontab（系统状态,不是仓库文件）"和常驻 tmux session,不改任何仓库文件,工作树 `git status --short` 全程干净,没有可 commit 的改动。工作树已 `git worktree remove` 删除,分支 `ticket/20260808-par/T14` 留着（`base == head == ec1da2841499d0689e464e8743a33cb8851022b3`,无新 commit）。

## 自查发现与存疑

1. **crontab 写入被 Claude Code 权限系统拦,不是我判断要不要做的问题。** 工单常规约定里"禁止发射 GPU 进程"是唯一的自我限制项,采样器不是 GPU 进程,工单评论也明确要求我把 tmux/crontab 指向主仓——这些都指向"这一步该由我实际执行"。但 auto-mode 分类器把"写 crontab"这个动作本身拦下来了,报错原文提示"用户可以加一条 Bash 权限规则来放行"。这是环境层面的权限边界,我没有权限绕过,也按规程不该绕过。**需要用户决策**：要么用户自己手动装这行 crontab（备份文件在 `/tmp/crontab.bak`,要装的行贴在上面 Step 2）,要么用户给 Claude Code 加一条允许 crontab 写入的 Bash 权限规则后重跑这一步。
2. **tmux session 我留着没杀。** 虽然验收条目 3（crontab 5 分钟拉回）做不了,但 session 本身已经在跑,满足"上线后网页能看到真任务"里"上线"这半句（真任务那半句要等有真实 GPU 任务登记进台账才能看到,现在台账是空的,不是我能控制的）。留着这个 session 是有意为之——工单目标是让它常驻,没有看门狗不代表现在应该关掉它,关掉反而是倒退。如果用户认为应该等看门狗装完一起上线,请告诉我,我会去把它杀掉。
3. **验收条目 2（浏览器看任务表）我只做了等价的 curl 验证**,没有真实浏览器可用。已在上面写明是等价验证不是原始要求的验证方式,请用户自己用端口转发确认一次比较稳妥。
4. **遗留提醒（工单评论里点名,转记不用我做）**：后续工单 12（事故触发）、13（vLLM 服务档）合并进 main 后,现在这个 `new1_sampler` session 跑的是合并前的代码,需要重启一次才吃到新代码。这件事需要主会话在 12/13 合并后记得处理。
5. 部署时主仓 `git status --short` 里有一条 `.scratch/gpu-monitor-launch/sdd/2026-08-08-wave1/T09-report.md` 的未提交改动,是并行跑的 T09 工单自己在写报告,与本工单无关,我没有碰它。
