# T11 trace_check.py（溯源检查 + 收官门禁）

Status: claimed
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + spec.md §4 trace_check 注释块（逐条即需求）、§2 总规矩
（可追溯链双向）、§5（affects 与 decision_refs：发射单是权威）、§9
trace_check 各条 + `tables/rows.json`（batch_report_header、spec_header）。
校验/追溯一律**跨档读**（include_archive=True，spec §2.1）。

## 文件

- Create: `research-loop/scripts/trace_check.py`
- Create: `research-loop/tests/test_trace_check.py`

## 要求

CLI：`trace_check.py [--project-root P] [--closeout BATCH_ID]`。
输出一行一发现 `<check>: <detail>`，末行汇总
`trace_check: <N> errors, <M> warnings`；有 error exit 1。

检查清单（每条独立函数，逐条实现）：

1. **发射单正链**：每张非 quick 发射单——spec_ref 能在 specs 目录某 md 里
   找到（字符串含 item_id）；issue_ref 文件存在；decision_refs 各在
   decisions 账且 status=decided。quick=true 的单豁免这三样（§2.6，不误报）。
2. **批准面**：spec_ref 非空的单，重算 approved_digest 不等 → 报
   `approval_stale`（approved_by 空 → 报 not-approved）。quick 单不受影响。
3. **affects 一致性**（发射单是权威）：发射单 decision_refs 里的 D，其
   affects 必须含该 run_id → 缺报 `affects-missing`（修复动作 = 重跑写发射单
   命令，写进 detail）；反向：decisions.affects 里的 run_id 若有对应发射单，
   该单 decision_refs 必须含此 D → 不含报 `affects-extra`。
4. **runs 反链**：普通行——runmeta_path 文件存在、RUNMETA.launch_order_ref
   指向存在的发射单、该发射单 run_id 与行 run_id 一致；
   判据缩减行——principle_id 在原则文档里存在（import
   principlescmd.parse_principles 若在，否则自带同款解析）+ criterion_cmd
   过 check_in_registry（registry_query null → 报 unwired error，不放行）。
5. **jobs 反链**：台账各条 launch_order_ref 存在。
6. **story 引用**：各 active claim 的三个 run 列表跨档存在、非 quick。
7. **promoted_from 沿用面**：promoted_from 非空的单，与来源 quick 单比对
   seed/dataset_version/argv/env_name/filter 五字段，逐字相等，否则报
   `promotion-field-drift`（列出改了哪个字段）。
8. **--closeout BATCH_ID**：附加门禁——该批批次报告存在；frontmatter
   inspection_report **非空**（平时空串不报，closeout 模式空串报错）；
   报告 run_ids 全部已入 runs 账。加上以上全部常规检查，全绿才 exit 0。

## 测试（test_trace_check.py，fixture 全裸写）

1. 断链各报：spec_ref 查无 / issue 文件缺 / decision_ref 查无 /
   runmeta_path 缺 / launch_order_ref 缺 / jobs 引用缺。
2. quick 单三 refs 全 null → 零误报；判据缩减行 → 不查 spec_ref 链、
   改查 principle_id + 注册表，PID 不在原则文档 → 报错。
3. 跨档：被引 run 行只在 runs.archive.jsonl → 不报断链。
4. 批准面：正文改一标点 → approval_stale；只追 withdrawals / spec_version+1
   → 不报。
5. affects：缺 → affects-missing 且 detail 含重跑指引；多 → affects-extra。
6. promoted_from：改 seed → promotion-field-drift 点名 seed；五字段全同 → 绿。
7. --closeout：inspection_report="" → 报错；填了路径 → 过；平时（无
   --closeout）空串不报。
8. 全绿 fixture：exit 0 且汇总行 `0 errors`。

## Comments
