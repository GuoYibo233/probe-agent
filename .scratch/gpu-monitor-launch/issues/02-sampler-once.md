# 02 — 采样器单轮走通，三份落盘文件出来

**What to build:** 采样器能把一轮采样从头走到尾：读台账 active 的任务清单，tail 各分片日志抓心跳，探 tmux 存活（探测失败 fail-closed），调判定引擎算判定，落盘最新结果、累计状态和逐轮历史三份文件（NFS 的 monitor 目录，环境变量可以把目录指到别处）。补射后时间轴重开、同一条心跳不重复计数这两条账也在这一步立住。`run.py sampler` 挂进注册表，支持采一轮就退的冒烟模式。步骤照实施计划 Task 6 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** resolved

- [ ] 采样器测试通过：假台账两分片（一活一死），活的判定是健康或 warm-up 中，死的判定是已挂，累计 token 读对
- [ ] 三份落盘文件都出现并且能 json.load；再采一轮，没变的日志不重复追加心跳
- [ ] `python3 run.py sampler --once` 在真台账上跑完不炸
- [ ] `python3 run.py selfcheck` 通过并 commit

## Comments

- 2026-08-08 ticket-run：DONE。分支 ticket/20260808-par/T02（base 5be5d08，head d7f3435，新增 ops/sampler.py + tests/test_sampler.py + run.py 挂 sampler + MAP.md 行），合并 commit 93d5bdd（MAP.md 与 T08 加行冲突，取并集解决，两行互不相干）。修复 0 轮，无 minors。cannotVerify 两条主会话处理：selfcheck 在合并后完整环境下亲测 63 任务全部就位（工作树里 rc=1 是缺 venv 的结构性问题，实证解释成立）；kind="service" 的端到端链路属工单 13 范围，T13 收账时核。验收项三真台账 `sampler --once` 主会话亲测 exit 0，NFS monitor 目录出 latest.json/state.json，rows=0 与台账当前无 active 任务一致。concerns 六条已读，均为实现取舍说明（load_reg 本模块化、build_row 收整 job 字典、state.json 多三个键、事故字段留工单 12、service 集成测试留工单 13、selfcheck 工作树限制），无需动作。报告：sdd/2026-08-08-wave1/T02-report.md。
