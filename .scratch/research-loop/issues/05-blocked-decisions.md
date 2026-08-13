# T05 待决账全跃迁 + r5 拼装 + 抉择账（grant/decision/R6）

Status: claimed
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `research-loop/tables/writes.json`（blocked_transitions /
r5_choice_assembly / withdrawal_proxy / owner_values.per-kind）+
`tables/rows.json`（blocked_row / decisions_row / enums）+ spec.md §5、R5、R6。
写入一律 `_lib.validate`（用 T03 生成的 schemas/）+ `_lib.locked`。

## 文件

- Create: `research-loop/scripts/ledger_cmds/blockedcmd.py`
- Create: `research-loop/scripts/ledger_cmds/decisionscmd.py`
- Create: `research-loop/tests/test_blocked_decisions.py`

## 要求

### blocked open（--layer L，L 即 from_layer）

id 自增 B 前缀；status=open；raised_at=now_iso()；kind=r5-choice 必带
--where/--options（schema conditional 兜底，但 CLI 先给可读报错）；
evidence 至少一项；validate 后持锁 append。

### blocked answer（--layer L BID）

- 行必须存在且 status=open，否则
  `blocked.status: illegal transition to answered (got: '<当前值>')`。
- 写权：to_layer=user 时任何 --layer 放行，但 answered_by 强制 "user"
  （显式传 `--answered-by` 非 user → 拒）且 --answer 非空（用户原话）；
  to_layer≠user 时 --layer 必须等于 to_layer，否则
  `blocked.to_layer: only to_layer may write answered (got: '<L>')`。
- answered_by = "user"（--answered-by user 时）否则 = --layer 值。
- kind=r5-choice 追加规则（writes.json r5_choice_assembly 逐条照办）：
  - 缺 --chosen → 拒。
  - answered_by≠user → --grant 必传且指向有效 grant（kind=grant、
    status=decided、未过期、无 superseded_by），否则拒（R6 机验落点）。
  - 机械拼装 decision 行：kind=decision、where/question/options 抄 blocked 行、
    chosen=--chosen、reason=--answer 原文、decided_by 按 answered_by 映射
    （user→user 否则 agent）、authorized_by（user→answer 原话；否则
    `grant:<DID>`）、blocked_ref=BID、affects=（blocked.ref 是 B 前缀则 []
    否则 [blocked.ref]）、raised_at=blocked.raised_at、decided_at=now、
    status=decided、scope/principle_ref/superseded_by/withdrawn_* = null。
  - 写序（`_write_order`）：① 先按 blocked_ref=BID 查已有 status=decided 的
    decision——命中复用不再 append（幂等），未命中 append；② 最后就地更新
    blocked（status/answer/answered_at/answered_by/grant_ref/decision_ref，
    全在 form2 白名单内）。同一 BID 至多一条 decided 同步 decision，违反即拒。
- 非 r5 kind：只做就地更新（status=answered + answer/answered_at/answered_by，
  --grant 给了就存 grant_ref）。

### blocked close（--layer L BID）

--layer 必须 == from_layer；当前 status ∈ {open, answered}；就地 status=closed。

### blocked withdraw（BID --reason TEXT，**不收 --layer**）

撤销代笔特例（writes.json withdrawal_proxy + blocked_transitions.withdrawn）：

- 只对 status=answered 的行；open 行 → 拒
  `blocked.status: withdraw applies to answered rows; from_layer should close open rows`；
  已 withdrawn 的行 → 只做步骤①②的收敛修复（幂等），exit 0。
- 三步写序照 `_write_order`：
  ① 同步 decision 置 withdrawn：经 decision_ref；decision_ref 为空按
    decisions.blocked_ref=BID 反查孤儿；找到且 status=decided →
    就地 {status: withdrawn, withdrawn_by: "user", withdrawn_reason: reason}；
    已 withdrawn 跳过。
  ② 机械重开：先按 (ref=BID, status=open) 查重，命中跳过；未命中 append 新条——
    from_layer/to_layer/kind/question/where/options/evidence 逐字抄旧条，
    ref=BID，status=open，raised_at=now，新 blocked_id。
  ③ 旧条最后翻：status=withdrawn，answer = 旧 answer +
    `"\n[withdrawn by user: <reason>]"`。

### grant（decisionscmd，--layer ∈ idea|deploy|run）

kind=grant、decided_by=user、authorized_by=reason=用户原话（--reason）、
scope={desc: --scope-desc, path_globs: --scope-globs, expires_at: --expires|null}
三件缺一 → 拒 `decisions.scope: grant requires structured scope`；
where/options/chosen=null、affects=[]、raised_at=decided_at=now、status=decided。
--layer=oversight → 拒（owner_values.per-kind：均不含 oversight）。

### decision（直接写 kind=decision）

- decided_by 缺省 agent。decided_by=user → 只收 --layer deploy；
  decided_by=agent → --layer ∈ idea|deploy|run 且 authorized_by 必须是
  `grant:D0xx`（且该 grant 有效）或字面 `spec-standing-gpu-1h`，否则拒（R6）。
  oversight 一律拒。
- where/options/chosen 必填（schema conditional）；affects=--affects 或 []。

### decision-withdraw（DID --reason TEXT，不收 --layer）

就地 {status: withdrawn, withdrawn_by: "user", withdrawn_reason: reason,
superseded_by: --superseded-by（给了先验证存在）}。

### 导出函数（T09 消费）

```python
def active_grants(rows: list[dict], now: str) -> list[dict]
# kind=grant & status=decided & (scope.expires_at null 或 > now) & superseded_by null
```

## 测试（test_blocked_decisions.py，spec §9 对应条目逐一落）

1. open：r5-choice 缺 --where/--options 拒；合法 open 落行 B001。
2. answer 写权：to_layer=deploy 的条用 --layer run 答 → 拒；--layer deploy 过。
3. 非法跃迁：closed 条再 answer 拒；withdrawn 条 close 拒。
4. r5：answer 缺 --chosen 拒；--answered-by 缺省（=layer≠user）缺 --grant 拒；
   给过期 grant 拒；给有效 grant 过，decision 拼装落行、decision_ref 回填、
   authorized_by=`grant:D00x`、decided_by=agent。
5. answered_by=user 路（--answered-by user）：不要求 --grant，
   decision.decided_by=user、authorized_by=answer 原话。
6. to_layer=user 特例：--layer run 也能答，answered_by 恰为 "user"；
   `--answered-by run` → 拒。
7. answer-r5 同一命令重复执行两次：decisions 行数不变、decision_ref 不变（幂等）。
8. withdraw：open 条拒；answered 条一次撤销后——旧条 status=withdrawn 且
   answer 尾部含原话附注、同步 decision status=withdrawn + withdrawn_reason、
   新开条字段逐字沿用 + ref=旧 BID + status=open；重复执行整条命令，
   行数与引用不变（幂等）。
9. 孤儿反查：手工把 blocked.decision_ref 抹成 null（fixture 裸写），withdraw
   仍能经 decisions.blocked_ref 找到同步 decision 置 withdrawn。
10. grant：缺 --scope-globs 拒；oversight 拒；有效 grant 进 active_grants；
    expires 过期/被 superseded 不进。
11. decision：decided_by=agent 无 authorized_by 拒；authorized_by=
    `spec-standing-gpu-1h` 过；decided_by=user 且 --layer idea 拒（只收 deploy）。
12. 崩溃面：模拟"①做完②没做"（fixture：手写一条 decided decision 带
    blocked_ref，blocked 行仍 open）→ 重跑 answer 命令收敛：不长第二条
    decision、blocked 翻 answered、decision_ref 回填。

## Comments
