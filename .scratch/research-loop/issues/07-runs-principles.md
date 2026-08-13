# T07 runs-append（判据 run）+ principles-lint + render principles

Status: claimed
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + spec.md §5"判据 run 执行契约"、R1、R7 + `tables/rows.json`
（runs_row_criterion、principles_columns 含 `_exec_rule`、
structured_output_contract）+ `tables/config.json`（registry_query null_effect）。

## 文件

- Create: `research-loop/scripts/ledger_cmds/runscmd.py`
- Create: `research-loop/scripts/ledger_cmds/principlescmd.py`
- Create: `research-loop/tests/test_runs_principles.py`

## 要求

### 原则表解析（principlescmd 内共用函数，T09/T11 也 import）

```python
def parse_principles(path: Path) -> list[dict]
# 找文件里第一个表头含 principle_id 的 md 表；列名即 helpers.py 造的
# METHOD.md 八列（principle_id/status/scope/applies_when/principle/
# rationale/criterion_cmd/last_tested）；按 | 切分、strip；返回行 dict 列表
```

### runs-append --layer deploy --principle PID

1. --layer ≠ deploy → 拒 `runs.layer: runs-append only accepts --layer deploy`。
2. config：registry_cmd 为 null → 拒（null_effect：锁判据实跑）。
3. PID 查无 → 拒；criterion_cmd 空 → 拒
   `principles.criterion_cmd: not wired (【想法待定】); cannot run criterion`。
4. `split_cmd`（禁管道/换行）→ `check_in_registry`（与发射单共用同一函数）→
   `run_argv(cwd=工程根)` 计时。
5. **只有退出码 0 且尾行解析出含 value 与 evidence_path 的 JSON 才落行**；
   否则不落任何行、stderr 转贴末 20 行 + 提示 escalate per R8，exit 2。
6. run_id = `chk-<PID>-<YYYYMMDD>-<序>`（序 = 既有同前缀行数+1，跨档查）；
   同 run_id 已存在 → 拒（判据行重复拒）。
7. 行字段（runs.criterion schema）：status=ok、principle_id=PID、value、
   output_dir=evidence_path、commit=git_head(工程根)（脏树自带 -dirty）、
   elapsed_s、recorded_at=now_iso()、schema_version=1；
   metric_name/arm=null、其余可空字段 null。
8. 锁：`<runs路径>.lock`（与 record.py 同一把——同一文件名约定）；
   validate 后 append；stdout 打整行 JSON。

### principles-lint [--file PATH]

逐条检查，任一错 exit 1，格式 `principles.<PID>.<列>: <说明>`：
principle_id 重复；applies_when 空；rationale 空；status 不在
enums["principles.status"]；status ∈ {【现状】,【已定要改】} 时
criterion_cmd 空或不过 check_in_registry（registry_query null → 报
`registry_query not wired`，**不放行**）；criterion_cmd 含管道/换行；
【想法待定】空 cmd 放行、非空 cmd 也过注册表检查。

### render principles（维护动作，不收 --layer）

只重写 last_tested 一列：每个 PID 取 runs 判据行（principle_id=PID，跨档）
按 recorded_at 最新一条 → `ok (<value>) <YYYY-MM-DD>`（日期取 run_id 的
日期段，spec 成文的日期来源）；无行 → `—`。其余字节一律不动。

## 测试（test_runs_principles.py）

1. --layer run → 拒。
2. stub 任务 `check-fail`（exit 1）→ 不落行、exit 2；
   `check-bad-tail`（尾行非 JSON）→ 不落行、exit 2。
3. `check-p001` 正常 → 行过 runs.criterion schema、value=3、
   output_dir=ops/evidence.txt、run_id=chk-P001-<今天>-1；再跑一遍 → 序=2。
4. commit 字段：沙盒是 git 仓库且脏 → 值带 `-dirty`；非 git 沙盒 → `no-git`。
5. principles-lint：重复 PID / 空 rationale / 空 applies_when / 【现状】空 cmd /
   cmd 不在注册表 / cmd 带管道符，六种各报错；【想法待定】空 cmd 放行；
   config 的 registry_query 置 null → lint 报 not wired 且 exit 1。
6. render：跑过判据后 last_tested 变 `ok (3) <今天>`，文件其余部分字节不变
   （比对渲染前后除该列外的内容）。

## Comments

- 2026-08-14 预警（T03 落地后的对接契约，实现前必读 ledger.py 现状）：
  ① `render` 的 argparse parser 由 ledger.py 自己注册（只有一个 target 位置
  参数），target→模块映射在 ledger.py 的 `_RENDER_TARGET_MODULES`
  （principles→principlescmd）。本工单**不要**给 render 注册 parser，只需在
  principlescmd.run(args) 里认 `args.command == 'render'` 分支；认为映射不对
  就回头改 ledger.py 那张表。
  ② 分组子命令未实现时 dispatcher 的文案是 `not implemented yet: <顶层子命令名>`
  （不带二级动词）；本工单测试如断言这条 stderr，按这个格式来，不合适就改
  ledger.py 的 `_dispatch()` 并说明。

- 2026-08-14 wave3 收账：DONE，1 轮 0 修复，commit 范围 6cce8bc..462f429，
  merge 进 main。主仓复跑全量 141/141 过。cannotVerify 留待后波：与
  fallback/record.py 的锁文件名约定（T10 落地后核）；parse_principles 返回
  形状是否满足 T09/T11（落地后核）。"同 run_id 已存在拒"在单进程+持锁路径下
  不可达，按工单要求保留、无单测，留档。concern：md 表格 `\|` 转义是超出
  工单字面"按 | 切分"的设计决定（没有它工单要求的管道符 lint 测试不可达），
  范围限于 principlescmd.py，认可留档。
