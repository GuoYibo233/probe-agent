# T01 脚手架（主会话执行，不派发）

Status: ready-for-agent
Blocked by: —
执行者：主会话（不进 ticket-run）

## 内容

1. 建 `research-loop/` 目录树（见 plan.md 目录结构），含空的
   `scripts/ledger_cmds/__init__.py` 占位、`.claude-plugin/plugin.json`、
   `tests/run_all.py` stdlib 跑器。
2. `git mv .scratch/research-loop/tables research-loop/tables`（表单一真源随实现走）。
3. `spec_lint.py` 的 `TABLES` 改指 `ROOT.parent.parent / "research-loop" / "tables"`，
   spec.md §0.5 加一句表的新住址，跑 `python3 spec_lint.py` 确认全绿。
4. `MAP.md` 加一行 research-loop plugin 总条目（此后工单不再碰 MAP.md）。
5. audit-merge.md 记实施期自决点（plugin 落点、表搬家、纯 stdlib、分发器拆包、
   生成物弃 _note、报告体裁约定）。
6. commit。

## Comments
