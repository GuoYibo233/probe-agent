# 02 — 采样器单轮走通，三份落盘文件出来

**What to build:** 采样器能把一轮采样从头走到尾：读台账 active 的任务清单，tail 各分片日志抓心跳，探 tmux 存活（探测失败 fail-closed），调判定引擎算判定，落盘最新结果、累计状态和逐轮历史三份文件（NFS 的 monitor 目录，环境变量可以把目录指到别处）。补射后时间轴重开、同一条心跳不重复计数这两条账也在这一步立住。`run.py sampler` 挂进注册表，支持采一轮就退的冒烟模式。步骤照实施计划 Task 6 执行。

**Blocked by:** 01 心跳模块与判定引擎

**Status:** claimed

- [ ] 采样器测试通过：假台账两分片（一活一死），活的判定是健康或 warm-up 中，死的判定是已挂，累计 token 读对
- [ ] 三份落盘文件都出现并且能 json.load；再采一轮，没变的日志不重复追加心跳
- [ ] `python3 run.py sampler --once` 在真台账上跑完不炸
- [ ] `python3 run.py selfcheck` 通过并 commit
