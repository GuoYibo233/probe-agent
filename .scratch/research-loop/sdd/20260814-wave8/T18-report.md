# T18 报告：§V 第一轮修复——skill 文档面

工单：`.scratch/research-loop/issues/18-vloop-docs.md`
分支：`ticket/20260814-wave8/T18`（base `3d103248af45717f806ec0686559388f7952024a`，
head `29b919308204e48ef242c22cd6ac1f39346af645`——即下方 commit 清单末条）
工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave8-T18`（收尾已删除，分支保留）

范围声明照抄工单：只动 `research-loop/skills/**` 与本工单点名的表 `_note`
文本（`tables/rows.json` 里 `launch_order` 的八个字段说明）；不改代码。
写文档前读了 T17 的 commit diff（3f941d9/3a30e9e/8937e0a/cad4770）与工单
Comments 里 wave7 收账记录，教的是 T17 落地后的真实 CLI 行为（`--blocked-ref`
两步路、`--decision-ref` 校验清单、`legal_to` 跳层锚点、jobs 键名、
error_classify 缺表兜底、`expected_outputs minItems:1`、story `--baseline-runs`
可空、routes.json `kind` 列），不是第一轮跑出来的旧行为。

## 做了什么

按工单三份新文件 + 逐条既有文件修，对照 `sdd/vloop-round1-verdict.json`
的 39 条 finding（37 个 finding id + #154）逐一核对落点：

**新参考文件三件**

1. `idea-layer/references/answering.md`（v1-idea-1，blocker）：idea 层
   如何答复 `to_layer=idea` 的 open 条——读行（`query blocked --status open
   --to-layer idea`）、按 kind 分三种答复形态（r5-choice 机械拼 decision；
   非 r5 走 T17 的两步路 `decision --blocked-ref` + `answer --decision-ref`；
   转录用户裁决走平答 `--answered-by user`）、answered 后由 from_layer
   消化并 close 的生命周期（含 idea 自己向 user 开条、user 答复后 idea
   作为 from_layer 收尾 close 的对称情形）。
2. `deploy-layer/references/failures-inbound.md`（v1-deploy-1 /
   v2-hop3-2/3，blocker）：kind=failure 升级条的处理规程——读 evidence
   原文、`ops/error_classes.json` 的真实字段契约（对齐 `error_classify.py`
   的 `_MATCH_KEYS`/`_rule_matches`）与首次起表方法、裁决分岔（自愈+补表
   / 继续升级）按 R5/R6 纪律、r5-choices.md 的机械拼装范围收窄声明的落点、
   答复与收尾（同样带 close 步骤，覆盖 deploy 自己再向上开条的场景）。
3. `oversight/references/regression.md`（v1-oversight-5，blocker）：
   `regression_check.py` 的职责、调用形态（`--batch`/`--dry-run`）、
   输出读法（Comparisons/Skipped 表 + provenance）、与 doctor `--dry-run`
   调用路径的分工、与批次核查（inspector 三件套）的先后关系——不属于
   收官三件套派发契约，是 oversight 会话自己跑的独立动作。

**既有文件逐条修**（按 finding id 归组，完整清单见工单原文，此处列文件
与要点，不逐条复述）

- `research-loop/SKILL.md`（v1-router-1/2）：How to read the table 补两句
  ——CLI 目标统一调用形；`kind` 列 handoff/command 两类目标各自处置，
  只有 handoff 能设定接收会话层身份。
- `idea-layer/SKILL.md`（v2-hop5-1/2）：§2 status 三块+两附注块逐字段
  点名；§3 补 query-only 读法纪律句；§4/§6 挂 answering.md。
- `idea-layer/references/story.md`（v1-idea-2/3）：`--baseline-runs`
  改可选（对齐 T17）、单臂语义+baseline==candidate 拒绝说明、
  `principle_id` 补进走查清单。
- `deploy-layer/SKILL.md`（v1-deploy-1、v2-hop3-5、v2-hop5-1）：§2 同上
  逐字段点名；§4 channel3 补 rails.build null-lock + config-check、
  channel4 挂 failures-inbound.md；§6 补 ticket 行（指回 §4）与失败升级行。
- `deploy-layer/references/r5-choices.md`（v2-hop3-3）：机械拼装范围
  显式收窄到 `kind=r5-choice`，非此 kind 的答复指向 failures-inbound.md
  的两步路。
- `deploy-layer/references/closeout.md`（v1-deploy-4）：新增 Step 0
  "写批次报告"，字段清单+`inspection_report` 留空语义+触发 Step 1 的前提。
- `deploy-layer/references/launch-orders.md`（v2-hop1-1/2/3/4/5/6、
  v2-hop3-4）：draft 文件格式（JSON、无独立宽松 schema）+ 用后即删；
  `run_id` 缺省命名（对齐 evidence_lint 豁免）；`decision_refs` 空数组
  的合法语义；`created_by`/`expected_commit`（含 `no-git` 哨兵）说明；
  `created_at` naive 本地时间 + overdue 交叉核对影响；新增
  "Sourcing expected_outputs" 节（从注册表任务实际产物取值，禁生造
  glob）。
- `tables/rows.json`（v2-hop1-1/2/5，表 `_note` 文本，工单点名范围内）：
  `launch_order` 的 `batch_id`/`env_name`/`workdir`/`expected_commit`/
  `smoke_cmd`/`artifact_dir`/`created_by` 七处字面 "..." 占位填实文，
  `created_at` 的 note 补 "naive 本地时间" 说明——与 launch-orders.md 的
  散文互相印证。`dataset_version` 的 "..." 占位工单未点名，未动（YAGNI）。
- `run-layer/SKILL.md`（v1-run-2、v2-hop3-5、v2-hop5-1）：§2 逐字段点名
  （含 `open_blocked` 对 run 恒空的机器事实——`blocked.to_layer` 枚举无
  `run` 值）；§3 补 `ops/jobs.json` 直接编辑权（对齐 deploy §3 句式）；
  §4 补 `rails.gpu` null-lock + config-check 提醒。
- `run-layer/references/execute.md`（v1-run-2/3/4/5、
  v2-hop2-1/2/4/6、v2-hop4-1/2/3/4，本工单篇幅最大的一处改动）：
  Execution 节重写为两类拒发（脏树含未跟踪未忽略文件、expected_commit
  不符，同错误码同升级文案）+ 静默 stdout（子进程输出全在 attempt<N>.log）
  + 重发不幂等（真实重跑、attempt 累加不覆写）；After it lands 节补三态
  verdict 说明；Recording 节补"拒发不触发本步"+ `output_check` verdict
  到 `record --status` 的映射表（含"省略 --status 时的默认推导只在
  verdict=ok 时正确"的显式警告）；Job-ledger registration 节重写——
  fallback launcher 自己写的基础键 vs 本层直接编辑补的两个必加键
  （escalation_ref/sampler_verdict+_at）、预检被拒不落 jobs 条目、
  fallback 判定映射（done/failed→ok、timeout→stall）。
- `run-layer/references/failures.md`（v2-hop4-5）：新增"Consuming the
  answer"节——deploy 答复后不算收尾，run 作为 from_layer 消化+close。
- `oversight/SKILL.md`（v1-oversight-5、v2-hop3-5、v2-hop5-1）：§2 逐字段
  点名（含 `open_blocked` 对 oversight 同样恒空的机器事实）；§4 补通用
  rails config-check 提醒句（oversight 本身不转交任何 rails，但该句是
  工单对四份 SKILL.md 的一致性要求）；§6 挂 regression.md。
- `oversight/references/inspection.md`（v1-oversight-4/6/7/8）：reading
  exemption 节补 `query LEDGER` 完整调用示例（含 `--spec-item` 的
  发射单 join 说明）+ jobs（reader subagent）与 launch_orders（直读）
  两个 query 拒收的账各自的替代读法；步骤 3 补文件名约定
  `reports/<batch_id>.md`；新增"Who reads this report"节说明消费方是
  deploy 收官步（回填 `inspection_report` 字段）。
- `oversight/references/report-genre.md`（#154）：补合规 id 形状豁免
  （命中 `_ID_DATE_SEQ_RE` 的 `run_id`/`batch_id` 全文任意位置豁免）
  vs 不合规含数字标识符（须入 frontmatter 或配 `$ ` 行）的对照句。

## 怎么验证的

文档工单不加代码测试；交付门按工单原文三项，均跑在最终 commit（`29b9193`）：

```
$ python3 .scratch/research-loop/spec_lint.py
-- spec_lint: 0 errors, 0 warnings

$ cd research-loop && python3 scripts/ledger.py gen-schemas --check
（exit 0，无输出）

$ python3 tests/run_all.py
-- run_all: 311 passed, 0 failed
```

311 与 T17 收尾时的基线一致（本工单未改代码，不预期数字变化）。

第四项交付门"每条上表 finding 在文档里能指到落点"：39 条（37 个
finding id + #154）逐条核对完成，见上"做了什么"节的分组归因；另跑了
交叉引用检查确认三份新文件与既有文件间的 `references/*.md` 链接全部
指向真实存在的文件（无死链）：

```
$ grep -rn "answering.md\|failures-inbound.md\|regression.md" research-loop/skills/
（核对全部命中行落点：SKILL.md 挂载行 + 相互引用行，无死链）
```

## commit 清单

- `1c03bd6` T18: idea-layer docs -- answering.md (v1-idea-1), story.md
  single-arm+principle_id (v1-idea-2/3), query discipline + status field
  enumeration (v2-hop5-1/2) —— `skills/idea-layer/SKILL.md`、
  `skills/idea-layer/references/story.md`、
  `skills/idea-layer/references/answering.md`（新建）
- `6f8524d` T18: deploy-layer docs -- failures-inbound.md
  (v1-deploy-1, v2-hop3-2/3), closeout.md batch-report step (v1-deploy-4),
  launch-orders.md field sourcing+draft disposal
  (v2-hop1-1/2/3/4/5/6, v2-hop3-4), r5-choices.md scoped to r5-choice
  (v2-hop3-3), rails.build config-check gate (v2-hop3-5), rows.json
  launch_order note fill-in —— `skills/deploy-layer/SKILL.md`、
  `skills/deploy-layer/references/{closeout,launch-orders,r5-choices}.md`、
  `skills/deploy-layer/references/failures-inbound.md`（新建）、
  `tables/rows.json`
- `36a13b3` T18: run-layer docs -- execute.md rewrite (v1-run-2/3/4/5,
  v2-hop2-1/2/4/6, v2-hop4-1/2/3/4), failures.md close step (v2-hop4-5),
  jobs.json direct-edit right + rails.gpu config-check gate ——
  `skills/run-layer/SKILL.md`、
  `skills/run-layer/references/{execute,failures}.md`
- `80c3879` T18: oversight docs -- regression.md (v1-oversight-5),
  inspection.md query example+jobs/launch_orders read paths+report
  filename+consumer (v1-oversight-4/6/7/8), report-genre.md id-shape
  exemption (#154) —— `skills/oversight/SKILL.md`、
  `skills/oversight/references/{inspection,report-genre}.md`、
  `skills/oversight/references/regression.md`（新建）
- `29b9193` T18: router SKILL.md -- CLI invocation form + handoff/command
  kind semantics (v1-router-1/2) —— `skills/research-loop/SKILL.md`

## 自查发现与存疑

1. **`tables/rows.json` `dataset_version` 字段的 "..." 占位未动**：finding
   v2-hop1-5 原文只点名 batch_id/env_name/workdir/artifact_dir/smoke_cmd
   （判"无害，自解释"）+ expected_commit/created_by（判"不无害，需要真内容"）
   两处；工单要求句"batch_id/env_name/workdir/artifact_dir/smoke_cmd 及
   两处'...'占位"精确对应这七个字段，不含 `dataset_version`（同样是
   "..." 但工单与源 finding 都未点名）。按 YAGNI 与"只动本工单点名的表
   _note 文本"的范围声明，未动它，留字面占位。是否需要一并补，请复核。
2. **oversight/run 两层 SKILL.md 的 rails.\* config-check 提醒句是否
   过度**：oversight 本身不转交任何 `rails.*`（不像 idea/deploy/run 各
   自实际持有一个 rails 出口），补的是一句"这个面不转交任何 rails，
   但要核对时走 config-check"的诚实陈述，不是编造一个不存在的转交场景。
   工单原文"四份层 SKILL.md 各补一句"字面要求四份都补，已照办；若认为
   oversight 这句是无实质信息的填充，可裁掉，不影响其余三份。
3. **`run-layer`/`oversight` 两层 `open_blocked` 恒空的机器事实**（
   `blocked.to_layer` 枚举只有 user/idea/deploy，无 run/oversight 值）
   工单原文未直接点名，是我核对 v2-hop5-1 逐字段点名要求时读 `rows.json`
   enums 与 `blockedcmd.py` 代码顺带发现并写进文档的——判断依据：
   v2-hop5-1 要求"队列=open_blocked/answered_blocked"逐块点名字段，
   若只点名不说明这两层的 open_blocked 恒空，读者会以为自己漏配了什么。
   标在这里供复核，非工单逐字要求，是我在范围内做的合理延伸。
4. **failures-inbound.md 里"往 error_classes.json 加规则"的写法未连带
   校验脚本自测**：工单声明"不改代码"，文档只教怎么手写这张表（字段
   契约对齐 `error_classify.py` 源码），未生成任何示例表文件落盘，
   纯文档教学，不产生可测的副作用。
5. **execute.md 篇幅显著变长**（约 40 行→144 行）：工单本条囊括
   v1-run-2/3/4/5、v2-hop2-1/2/4/6、v2-hop4-1/2/3/4 共九个 finding id，
   全部落在这一个文件的两三个小节里，篇幅增长是这批 finding 密度的
   直接结果，未夹带工单未要求的内容。

未发现工单要求之外我自己引入的行为或说明；未使用 GPU；未改
`run.py`/`MAP.md`（工单声明本来就不涉及）；未改任何 `scripts/*.py`
代码文件。

## 第 1 轮修复（fix1，head `d8e168b`）

分支 `ticket/20260814-wave8/T18` 检出到独立工作树
`/home/y-guo/reproduce/new1-wt/20260814-wave8-T18-fix1`（收尾已删除，分支
保留），在原 head `29b9193` 基础上追加一个 commit。两条 finding 均判
CONFIRMED，逐条核对判据表/源码后修复，未做工单未要求的重构。

### F1（critical）：answering.md 声称 oversight 可以对 idea 开条

**核对**：`tables/writes.json` → `blocked_transitions.open.legal_to` 实测：

```json
{"run": ["deploy"], "deploy": ["idea", "user"], "idea": ["user"], "oversight": ["user", "deploy"]}
```

`oversight` 的合法目标只有 `user`/`deploy`，不含 `idea`——finding 判据成立，
`answering.md` 第 7-8 行与第 95-96 行两处断言均与此表矛盾，且与同一 commit
里 `idea-layer/SKILL.md` §4 "In, channel 2 (deploy → idea)"（只提 deploy）
自相矛盾。

**怎么改**：

1. 开篇句「Only `deploy` and `oversight` may open one here」改为
   「Only `deploy` may open one here」，并补一句显式对照
   （`deploy` 的合法目标是 `idea`/`user`，`oversight` 的合法目标是
   `user`/`deploy`，`oversight` 永远不能开一条指向 `idea` 的行），把判据
   表的具体内容摆出来，不再是笼统一句带过。
2. 「After answering: who closes it」节里「that's whichever layer opened
   it (deploy or oversight)」+ 占位符 `--layer <deploy|oversight>` 改为
   唯一正确答案：`from_layer` 恒为 `deploy`，命令写实
   `--layer deploy`，并点出这是判据表里"合法开条方只有 deploy 一家"的
   直接推论（"see above"回指开篇的判据表复述）。

改动范围只限这两处断言本身；文件其余部分（三种答复形态、r5-choice 拼装、
`--decision-ref` 校验清单等）未动，也未在此工单核实范围。

### F2（critical）：execute.md 只列两类拒发，漏第三类『无效 --project-root』

**核对**：读 `scripts/fallback/launch.py::run()` 与
`scripts/_lib.py::resolve_project_root`：显式传入的 `--project-root` 若
目录下没有 `research-loop.json`，`resolve_project_root` 抛
`RLError(f"--project-root {root} has no research-loop.json (wrong path?)")`；
`launch.py::main()` 的 `except _lib.RLError` 捕获后打印 `exc.message` 到
stderr、返回 2——没有"escalate to deploy layer"文案，退出码也是 2 不是 3，
与脏树/`expected_commit`两类（exit 3、"escalate to deploy layer"）行为形态
不同。且此项检查在 `run()` 函数体内顺序上先于脏树检查（`_project_root(args)`
调用发生在 workdir 计算之前）。另确认这条校验逻辑是
`trace_check.py`/`regression_check.py`/`verify_report.py`/`doctor.py` 四
支脚本共用的同一个 `_lib.resolve_project_root`（`_lib.py` 该函数 docstring
自己点名"F2"和这四支脚本）。finding 判据成立，工单第 55-62 行原文三项
并列（脏树 / expected_commit 不符 / 无效 --project-root）确实只交付了
前两项。

**怎么改**：

1. 「Two refusal categories」改「Three rejection categories」，把无效
   `--project-root` 插为类别 1（按代码里的真实执行顺序排在最前面，脏树
   与 `expected_commit` 顺延为类别 2/3），写清共享的校验函数、真实
   stderr 文案、退出码 2（而非 3）、以及"没有 escalate to deploy layer
   文案，因为这是发射器被错误调用，不是仓库状态问题"这条与另外两类的
   本质区别；并写清不传 `--project-root` 完全不会走到这条路径（走
   `find_project_root()` 从 cwd 向上找）。
2. 该列表后原有一句「Either refusal escalates back to deploy ... neither
   refusal ever gets an entry in the job ledger at all」是针对"恰好两类"
   写的收尾句，加入类别 1 后原句在数量上不再成立，改写为「Categories 2
   and 3 both escalate back to deploy ... Category 1 gets no job-ledger
   entry either, but it is not a deploy-layer escalation」，把"两类都升级
   给 deploy""类别 1 不升级但同样不落 jobs 条目"分开说清楚。
3. 「Job-ledger registration」节原句「right after both refusal checks
   above pass」同样是"恰好两类"的用词，改「right after every check above
   passes」；原句「the refusal stderr is archived into the escalation
   entry's evidence instead, not dropped」只对类别 2/3 成立（它们真的会
   开一条 `kind=failure` 的 blocked 行，stderr 存档进它的 evidence）——
   类别 1 走的是 `main()` 的 `except` 直接返回，从不经过任何 blocked 行
   开条逻辑，stderr 哪儿也没存档。补写清楚这条区别，不让读者误以为类别 1
   的 stderr 也会被自动归档。

**写作中自己发现并改正的一处错误**：第一版草稿在解释"类别 1 为什么不
经过升级条归档"时，写的理由是"`run_id` 还没从发射单读出来"——重新核对
`launch.py::run()` 源码后发现这个理由是错的：发射单 JSON（含 `run_id`
字段）在 `_project_root(args)` 调用**之前**就已经解析进 `order` 字典了，
`run_id` 其实是可读的。改成准确理由：`main()` 的异常处理直接打印并返回，
根本不经过任何"开一条 blocked 行"的代码路径，跟 `run_id` 是否已解析无关。
成文前已改正，未留错误陈述。

**自查发现、未动的相邻问题**（不在两条 finding 范围内，未修，供复核）：
`tables/rows.json` → `jobs_min_additions._precheck_refusal` 的 `_note`
文本写的是"发射在预检被拒时不写 jobs 条目；拒绝的 stderr 原文存档进
升级条 evidence 文件——不是丢弃，是换了个账本"，这句话对类别 2/3
成立，对类别 1（现在也算"预检被拒"的一种）不成立——它的 stderr 确实
被丢弃了，不换账本。这条 `_note` 不在本工单点名范围内（T18 原范围声明
只动 `launch_order` 的七个字段），也不在本轮两条 finding 内，故未动；
若后续需要让这张表本身也反映三类拒发的区别，需要新工单裁定范围。

### 测试

```
$ python3 .scratch/research-loop/spec_lint.py
-- spec_lint: 0 errors, 0 warnings

$ cd research-loop && python3 scripts/ledger.py gen-schemas --check
（exit 0，无输出）

$ python3 tests/run_all.py 2>&1 | tail -5
PASS test_trace_check.test_story_refs_broken_run_reference_reported
PASS test_trace_check.test_story_refs_quick_run_reference_reported
-- run_all: 311 passed, 0 failed
```

311 与 T18 原轮一致（本轮仍是纯文档修复，未改代码，不预期数字变化）。

### commit 清单

- `d8e168b` T18: fix1 -- correct oversight-can-open-idea claim, add
  missing --project-root refusal category —— `skills/idea-layer/
  references/answering.md`、`skills/run-layer/references/execute.md`

### 状态

两条 finding 均已修复并验证，返回 `DONE`。
