# §V 验证循环第二轮（2026-08-14）

执行形态同第一轮（15 agent：V1 五 sonnet 天真执行者 + V3 越权探针 19 项 +
V2 八跳接力全环 + opus 对抗复核），沙盒种子修掉第一轮三处自伤（不合规
run_id、B004 旧形状、回退预案不可达）。沙盒脚本同：
`$CLAUDE_JOB_DIR/tmp/seed_v_sandboxes.py`（round2）。

原始 findings 65 → **48 confirmed（blocker 3 / friction 25 / note 20）/
17 refuted**。完整裁决书：`sdd/vloop-round2-verdict.json`。

**V3 探针零 findings**：19 项全部被机器拒绝且零残留——第一轮放行的跳层开条
这次被 legal_to 表拒掉，T17 的五个新机验锚点（非 r5 带 grant 拒、两步路链错
拒、story 自比拒、空产物契约拒、缺分类表不崩）全部实测成立。权限面收口。

**V2 八跳**：链走到 发射单 → 发射失败 → 升级 → R6 两步路留痕（decisions 行
双向链接，第一轮的断点已闭合）→ 重试成功，然后断在"重试入账"：
`record.py` 的同 run_id 查重与 run 级一致性检查把成功重试的行拒了（旧行
status=empty-output 挡道），下游批次报告/核查/收官/story 全部被正确扣住
没走到。trace_check 干净。终态 B003（deploy→user）挂在待决队列等真用户，
协议行为正确。

三条 blocker：
- v2-hop4-1：记过账的失败 run 重试后无路入账（设计死角，两跳独立复现）。
- v2-hop4-2：launch.py 首次登记对 jobs 条目整体赋值不合并，重发同 run_id
  会静默抹掉 run 层已加的 escalation_ref / sampler_verdict 回指。
- v1-oversight-3：evidence_lint 的数字扫描对标题编号、`python3`、"attempt 1"、
  `> ` 摘录行全数误火，两个 oversight 会话各烧 4-5 轮才过 lint；管道禁令与
  无 shell 执行在体裁文档里只字未提。

其余 45 条全部是 friction/note 级文档缺口（字段枚举漏 pending_user_decisions
×3、材料占位符未绑定、分类步骤对预检拒发未豁免、escalate 目标无判据等）。
安全告警一条（v1-idea 把自猜裁决写成 decided_by=user 的 story 行）被复核
裁为 REFUTED：schema 钉死 const "user"，story 行按设计只转录用户裁决，
防呆不防伪，执行者本应停手——产品面无改动。

## 处置

四条设计裁决落 audit-merge.md #158–161；修复开补丁工单
`issues/19-vloop2-code.md`（代码+表）与 `issues/20-vloop2-docs.md`
（文档，Blocked by 19），走 ticket-run。修完起第三轮（种子回退预案改按
#158 的新 run_id 纪律），循环到连续一轮零 confirmed。
