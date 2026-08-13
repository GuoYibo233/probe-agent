# T14 doctor.py（一键体检，只查不动）

Status: ready-for-agent
Blocked by: 04, 07, 09, 11, 13

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + spec.md §4 doctor 注释块（逐条即需求）、§5"复合动作的中断一致性"
③（半状态 doctor 扫出，修复=重跑原命令）、§10（archive 只做 cap 告警）。

## 文件

- Create: `research-loop/scripts/doctor.py`
- Create: `research-loop/tests/test_doctor.py`

## 要求

CLI：`doctor.py [--project-root P] [--out PATH]`。报告只出 stdout；--out 给了
另写用户指定路径；**不写 reports/、不写任何账本目录**（测试盯死）。
exit 恒 0（体检是建议件）；末行汇总 `doctor: <N> findings across <M> sections`。

分节（每节独立跑，单节崩溃 → 该节记 `section failed: <尾 3 行 stderr>`
继续下一节——§9"单项检查件挂掉能正确汇总"）：

1. **config**：subprocess 跑 `ledger.py config-check`，转贴输出。
2. **trace**：subprocess 跑 `trace_check.py`，转贴。
3. **evidence**：reports/ 下全部 *.md 逐个 `evidence_lint.py`，转贴。
4. **principles**：subprocess 跑 `ledger.py principles-lint`，转贴。
5. **regression**：runs 账里最新 batch_id（recorded_at 最大的非空 batch_id）
   跑 `regression_check.py --batch <id> --dry-run`；没有批次 → 一行 skipped。
6. **caps**：各 jsonl 账行数 vs 有效 cap（config ledger_caps 覆盖表默认）；
   行数 ≥ cap → finding（v1 只告警：archive 执行件排 v1.1，建议文案写
   "archive lands in v1.1; trim manually or raise the cap"）。
7. **archives**：`*.archive.jsonl` 存在 → 汇报行数（v1 一般为零节）。
8. **worktrees**：`git worktree list --porcelain` 除主工作树外的条目 +
   仓库旁 `<repo>-wt/` 残留目录清单。
9. **half-state 三类扫描**（直接读 jsonl，跨档；修复建议 = 重跑原命令原文）：
   - 孤儿 decision：decisions 行 blocked_ref 非空，而对应 blocked 行
     decision_ref 为空或不等 → 建议
     `re-run: ledger.py blocked answer <BID> ...`；
   - 撤销中断：blocked status=withdrawn 但同步 decision 仍 decided，或
     缺 (ref=BID, status=open) 重开条 → 建议
     `re-run: ledger.py blocked withdraw <BID> --reason ...`；
   - affects 缺失/不一致：发射单 decision_refs 与 decisions.affects 对不上
     → 建议 `re-run: ledger.py launch-order --layer deploy --file <单路径>`。
10. **workplan**：直接 subprocess 跑 `ledger.py status --layer deploy`
    转贴（"工作面段直接调 status，不重复实现跨账本派生"）。

代码检查不在范围（归 rails.build 会话收尾，spec 成文）。

## 测试（test_doctor.py）

1. 干净沙盒：exit 0、各节出现、findings 计数为 0 或仅 null 键报告。
2. 三类半状态 fixture（裸写造）各被报出，且建议行含 `re-run:`；
   跑 doctor 前后沙盒全目录（文件清单 + sha）不变——只查不动。
3. 单项崩溃汇总：把 METHOD.md 原则表破坏成非法（重复 PID），principles
   节红但 doctor 正常跑完其余节、exit 0。
4. caps：blocked 账裸写 501 行、cap=500 → caps 节 finding。
5. --out 写出的文件与 stdout 一致。

## Comments
