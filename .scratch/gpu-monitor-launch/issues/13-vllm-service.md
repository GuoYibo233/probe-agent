# 13 — vLLM 服务档

**What to build:** 服务类分片（vLLM）在窗口里正确显示：死活判定只看端口应答（/health 路径，以实测为准），吞吐行只解析出 token 速率放进显示位、不进判定，空闲不打吞吐行不算停摆。吞吐行解析的 fixture 用 2026-08-08 从真实日志核实过的原文。服务分片登记时日志字段要填真实路径（vLLM 的日志不在任务目录下）。步骤照实施计划 Task 15 执行。

**Blocked by:** 02 采样器单轮走通

**Status:** resolved

- [x] 吞吐行解析测试通过：真实样本行抽出生成速率、prompt 速率和并发数，无匹配返回 None
- [x] 服务分片不走心跳解析，判定只由端口探测决定
- [x] commit

## Comments

- 2026-08-08 主会话转记（来自 T09 收账）：T09 把 --service 实现成设 kind="service" 的布尔旗标、--port 落进透传参数，但 rich piece 字段表里没有 port 字段——服务分片从发射到采样器 probe_port(host, port) 的 port 传递路径整份计划都没定义。T13 实现时要么把 port 落进 piece/台账字段并让采样器读到，要么在报告里明确说明 port 从哪来；这条是 T13 收账时主会话必核项。
- 2026-08-09 ticket-run 中间账：DONE 于分支 ticket/20260808-par/T13（base 2ce9834，head 3540212），0 轮修复，minor 一条（sampler.py 续行缩进差一格）。**合并压后**：分支改 ops/sampler.py，与工作树里等用户统一提交的 T12 改动同文件，等那笔落地再合并、跑测试、标 resolved。评审确认的真实缺口（转记工单 18 与最终汇报）：port 字段无发射路径自动写入——launch 的 --port 只透传不进 rich piece，register 不支持 --port/--kind，真实 vLLM 服务档要生效得手工 register_all() 或手改 jobs.json；是否另开工单补由用户定。/health 返回 200 的假设与 T02 一致、未经真实服务实测。报告：sdd/2026-08-08-wave1/T13-report.md。
- 2026-08-09 主会话收账：T12 那笔（commit 088bac9）落地后合并分支（merge commit bd2d991）。冲突两处：sampler.py 的 import（两边都收）、MAP.md 的 sampler 行（以 HEAD 为底并入 T13 的服务分片句）。合并后 117 测试全绿。port 传递缺口照旧记在工单 18，由用户裁决是否另开工单。标 resolved。
