# T08 发射单写入 + approve-spec + affects 回填

Status: claimed
Blocked by: 03, 05

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + spec.md §5"发射单与台账的顺序"（含发射前批准门禁）、§2.6（快车道
与转正）+ `tables/rows.json`（launch_order、spec_header 三条 `_rule`）+
`tables/writes.json`（maintenance 无关；affects 属 decisions form2 白名单）。

## 文件

- Create: `research-loop/scripts/ledger_cmds/launchcmd.py`
- Create: `research-loop/tests/test_launch_order.py`

## 要求

### approve-spec SPECFILE --by NAME

`parse_frontmatter` 失败 → 拒（spec 文件头必须是 --- frontmatter）。
重写头部三字段：approved_by=NAME、approved_date=today()、
approved_digest=spec_digest(文件)；spec_version 缺则置 1；**正文字节一律不动**，
头部其他字段（withdrawals 等）保留原样。

### launch-order --layer deploy --file DRAFT.json

校验顺序（全过才写盘）：

1. --layer ≠ deploy 拒。
2. draft 过 launch_order schema（`_lib.validate` 单入口）。
3. 注册表三查（`check_in_registry` 同一函数）：registry_cmd 是 argv 前缀；
   前缀后首 token == draft.registry_task（不等 →
   `launch_order.registry_task: token after registry prefix does not match`）；
   任务在 registry_query 清单；registry_query null → 拒不放行。
4. 批准门禁：spec_ref 非 null →
   在 config 的 specs 目录（默认 .scratch/）递归找含该 item_id 字符串且带
   frontmatter 的 *.md；找不到 → 拒 `launch_order.spec_ref: spec item not found`；
   找到 → approved_by 空 → 拒 `spec not approved`；
   `spec_digest` 重算 ≠ approved_digest → 拒
   `launch_order.spec_ref: approval_stale`。quick=true → 本条整个跳过。
5. decision_refs 每个必须存在于 decisions 账且 status=decided，否则拒。
6. promoted_from 非 null → `ops/launch_orders/<pf>.json` 必须存在（拒）且其
   quick==true（拒 `promoted_from must point to a quick launch order`）。
   （沿用字段一致性归 trace_check，写入侧不查。）
7. 写盘 `<launch_orders目录>/<run_id>.json`（同路径重写幂等，允许覆盖）；
   **然后** affects 回填：对每个 decision_refs 的 D，若其 affects 不含 run_id，
   持 decisions 锁就地 append 进 affects（form2 白名单字段）。
   写序固定：发射单先落盘、affects 后写（spec §5 成文）。

## 测试（test_launch_order.py）

fixture：helpers.make_launch_order() 给合法 draft（argv 用 stub_registry 任务
`fake-任务`——helpers 的 stub 注册一个 `noop` 任务即可）；spec 文件
`.scratch/demo/spec.md` 带 frontmatter + 正文含 `IT-001`；decisions 账裸写
一条 decided 的 D001。

1. quick=false 缺 spec_ref/issue_ref/decision_refs → schema conditional 拒。
2. argv 前缀不是 registry_cmd → 拒；前缀后首 token ≠ registry_task → 拒；
   task 不在 --list 清单 → 拒；config.registry_query=null → 拒且文案含
   not wired。
3. 未 approve 的 spec → `spec not approved` 拒；`approve-spec` 后同 draft 过；
   往 spec 正文加一个标点 → `approval_stale` 拒；只往头部 withdrawals 追一条
   或 spec_version+1 → 不 stale、照过。
4. quick=true 且三 refs 全 null → 全部门禁豁免、写盘成功。
5. promoted_from 指向不存在 → 拒；指向 quick=false 的单 → 拒；
   指向 quick=true 的单 → 过。
6. 同 run_id 写两遍：目录里仍一个文件；D001.affects 恰好含一次该 run_id
   （回填幂等）。
7. approve-spec：批准前后正文字节逐字相同（读原文件比对），头部三字段就位。

## Comments

- 2026-08-13 预警（wave1 实现者发现）：helpers.make_launch_order() 的默认 argv
  （相对形式）与 make_sandbox() 生成的 registry_cmd（sys.executable+绝对路径）
  不对齐；本工单测试造发射单时用 config 里实际 registry_cmd 拼 argv 并 override，
  别指望默认值能过 check_in_registry。

- 2026-08-14 wave4 收账：DONE，1 轮 0 修复，commit 范围 963bdaa..2fffc36，
  merge 进 main。主仓复跑全量 204/204 过。concerns 留档："spec not approved"
  实现带 `launch_order.spec_ref:` 前缀（按 _lib.fail 惯例，判断工单是省写）；
  spec_ref 递归搜索多文件命中时按路径排序取第一个（未去重未报错）；
  单张 draft 内 decision_refs 含重复 id 时 affects 回填会重复追加（跨命令
  重跑幂等已测绿，单内重复未测、工单未提）。

- 2026-08-14 补记：续跑复审新增 minor N1（test_launch_order.py 的
  _write_spec 与 _write_spec_custom 约 8 行拼 header 逻辑重复，纯 fixture
  风格问题），留档给终审顺手清。
