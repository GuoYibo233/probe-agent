# 整分支终审报告（ticket-run Phase 4）

- 日期：2026-08-14
- 审者：opus final reviewer（general-purpose agent，按 prompts/final-reviewer.md），
  中途撞月度消费上限断连一次，续跑后完成；两份子审计（skills 文档面、测试面）回收并由终审者复验。
- 范围：`52cb4c1..64e8c3d`，只审 `research-loop/` 下的代码与文档（账目改动未逐行审）。
- 机械门禁终审者自己复跑：`tests/run_all.py` 268 passed / 0 failed、
  `ledger.py gen-schemas --check` 绿、`spec_lint.py` 0 errors、工作树干净。
- 结论：门禁全绿但报 16 条挡合并 findings（每条附复现，非读码推断）。
- 主会话处置：四条裁决题（F8/F9/F13/F15）的裁决见 audit-merge.md 自决点 #146–149，
  修复走单个 sonnet 修复 agent + 范围限定复审（skill Phase 4 流程）。

以下为终审者报告原文。

---

# 终审结论：不干净，16 条挡合并

范围：`52cb4c1..64e8c3d`，只审 `research-loop/` 下的代码与文档（账目改动未逐行审）。`research-loop/` 之外只动了 `MAP.md`（+8 行，plugin 总行），`run.py` 未动，无 `__pycache__` 入库——符合 plan 约束 9。

机械门禁我自己重跑了一遍：`tests/run_all.py` 268 passed / 0 failed（28.9s）、`ledger.py gen-schemas --check` 绿、`spec_lint.py` 0 errors、工作树干净。**门禁全绿但产品有硬伤**——下面每条我都给了复现，不是读码推断。

我的分类标准：产品缺陷（跑出错结果或假绿）与文档教错路进挡合并；测试写法只在它是 spec §9 点名验收项时进挡合并，其余进观察。

---

## 一、挡合并 findings

### A 组：溯源与门禁真的坏了

**F1（最重）spec 条目解析器是"第一个含 id 字符串的 md"，两处各写一份，两个方向都出错**
位置：`research-loop/scripts/trace_check.py:284-291`（`_find_spec_file`）与 `research-loop/scripts/ledger_cmds/launchcmd.py:116-142`（`_check_spec_approval`）

- 假红（我复现）：把 issue 工单按 `tables/rows.json` `issue_min` 要求写上回指的 item_id 之后，`trace_check` 报 `approval.spec_unreadable: launch order r-001: spec .../issues/01-demo.md has no valid frontmatter`，exit 1。原因是 specs 账默认路径 `.scratch/` 与 issues 账默认路径 `.scratch/*/issues/` 在盘上重叠，排序把 `issues/01-demo.md` 排在 `spec.md` 前面。本仓库 `.scratch/research-loop/` 就是这个布局，`plan.md`、`audit-merge.md` 同住 specs 根下且提及各种 id。
- 假绿（我复现）：在同目录放一个排序靠前、自带 frontmatter 且 `approved_by` 非空的 md（正文只要提到 IT-001），把真 spec 的 `approved_by` 清空后，`ledger.py launch-order` 仍然 exit 0 收下发射单——spec §5 的发射前批准门禁被一个无关文件满足。
- 为什么挡：`skills/deploy-layer/references/spec-items.md:31-36` 教的是"跑 trace_check 到全绿再上桌"，这条路在标准布局下永远走不通；同时批准门禁可被绕过。两个承重点各塌一半。
- 修法：把解析器提进 `_lib`，合成一个 `find_spec_files(cfg, item_id) -> list[Path]`，判据是"能解析出 frontmatter 且正文含 item_id"（`spec-items.md:7-9` 已写死每份 spec 必带 frontmatter，工单天然被排除）；命中 0 个报 not found，命中 ≥2 个报歧义并列出全部路径，禁止静默取第一个。`launchcmd` 与 `trace_check` 都改调它。

**F2 `--project-root` 指错路径 → 检查工具报 0 errors 并 exit 0**
位置：`trace_check.py:688-689`、`regression_check.py:167-169`、`verify_report.py:222-225`、`doctor.py:500-501`
复现：沙盒里种一条断链（story 引用不存在的 run），正常跑 `trace_check` 是 `3 errors` / exit 1；加 `--project-root` 指向一个没有 `research-loop.json` 的目录，输出变成 `trace_check: 0 errors, 0 warnings`、exit 0。`regression_check` 同样出一份 `story_rows_read: 0` 的空报告、exit 0。
为什么挡：三份 skill 文档教的正是带这个参数的写法（`deploy-layer/references/closeout.md:13`、`spec-items.md:35`、`oversight/references/inspection.md:22`），打错一个字得到"全绿"，正好骗过收官门禁。
修法：四个脚本统一——显式 `--project-root` 时先查 `(root/"research-loop.json").exists()`，不存在报错 exit 2；`doctor` 另外把 root 透传给它拉起的子进程（现在只靠 cwd，导致同一次体检里各段看的根不一致）。

**F3 doctor 误报"撤销中断"，照它给的修法重跑会多开一条待决条**
位置：`doctor.py:380-388`（`reopened` 判据）＋ `blockedcmd.py:344-346`（重开查重判据）
复现：B001 答复后撤销 → 机械重开 B002（open），doctor 说 `no half-state anomalies found`；等 B002 被正常答复（answered）之后，doctor 立刻报 `interrupted withdrawal: blocked B001 is withdrawn but not fully converged -> re-run: ledger.py blocked withdraw B001`；照做，账上多出 B003 open，同一个已经答完的问题第三次回到用户待办队列。
为什么挡：这是"重跑即修复"契约的反例——修复动作生产脏数据，脏数据还落在用户待决队列里。
修法：doctor 的 `reopened` 判据改成"存在 `ref=<blocked_id>` 的行"（不论状态）；blockedcmd 的查重键同样放宽到 ref 单键，并顺手改 `tables/writes.json` `blocked_transitions.withdrawn._idempotency` 那句 `(ref, status=open)`（改表属 R5 的账本 schema 变更面，要留痕）。

**F4 一行坏 JSON 让 ledger.py 全线裸崩**
位置：`_lib.py:173-183`（`_read_jsonl_file`）、`_lib.py:228`（`inplace_update` 的 `json.loads`）
复现：往 `ops/blocked.jsonl` 追一段截断的行（写一半被杀的形态），`ledger.py status` / `query blocked` / `blocked open` 三条全部 exit 1 + `json.decoder.JSONDecodeError` 裸栈：不是契约的 exit 2，没有 `<账名>.<字段>: <说明>` 文案，也没说是哪个文件哪一行。doctor 靠 `build_report` 兜底活着，但 half-state 段只印 `section failed: ... Unterminated string ... char 23`，同样不报文件名。
为什么挡：每个会话开工第一条命令就是 `status`（spec §2 会话开工必读），账本写坏的时刻正是最需要工具能用的时刻；trace_check 在 T11 已按这条修过（`trace_check.py:200-208`），共享库这一处没跟上，同一类只修了一半。
修法：`_read_jsonl_file` 逐行 try/except，走 `_lib.fail(path.stem, f"line {n}", "is not valid JSON", line[:80])`；`inplace_update` 的循环同样处理。

**F5 撤销的"无用户原话拒"三条路只落实了一条**
位置：`storycmd.py:118-122` 查了；`blockedcmd.py:291`（`_run_withdraw`）与 `decisionscmd.py:233`（`_run_decision_withdraw`）没查
复现：`decision-withdraw D001 --reason ""` 与 `blocked withdraw B001 --reason ""` 都 exit 0，落账 `withdrawn_reason` 是空串。
为什么挡：`tables/writes.json` `withdrawal_proxy._rule` 是对撤销体裁整体说的，spec §9 也把它列成验收项；三条路两条没执行。
修法：两处各加一句与 storycmd 相同的 `not reason.strip()` 检查，文案走 `_lib.fail`。

**F6 principles-lint 静默丢弃格式坏的行**
位置：`principlescmd.py:99-101`（`len(cells) != len(header): continue`）
复现：往 METHOD.md 追一行少一格的 P003（rationale 空、criterion_cmd 不在注册表），`principles-lint` 一个字不提；同一行补齐成 8 格立刻报出两条违规。
为什么挡：principles-lint 是 R1 的唯一机验口，行解析不了就当不存在，等于给"漏一条原则"开后门。
修法：把跳过的行收集起来，按 `principles.<行号>.format: malformed row (expected N cells, got M)` 一起报，解析行为不变、只补报告。

### B 组：文档教的路走不通或走出错账

**F7 `spotcheck.py` 按文档的写法跑不起来**
位置：`skills/oversight/references/spotcheck.md:13` 写 `spotcheck.py <material>`；真 CLI 是 `--file PATH --seed N [--k K]`，两个都必填（`scripts/spotcheck.py:70-72`）。子审计实测报 `error: the following arguments are required: --file, --seed`。
修法：改成 `--file <material> --seed <固定整数> [--k <n>]`，并加一句"种子由调用方定且必须写进报告"——文档"同命令同样本"的说法只在 (file, seed, k) 固定时成立。

**F8 `query --spec-item` 这个过滤维度不存在**
位置：`skills/oversight/references/inspection.md:11` 列了它，`.scratch/research-loop/spec.md:93` 也列了它；`querycmd.py:259-268` 没有这个参数，`tables/ledgers.json:31` 写的过滤集是 `--batch/--run/--since/--metric`。
为什么挡：监察面被告知有一个不存在的切片维度，而 R3 报告的"全量扫描"陈述正是靠这些维度支撑的。
修法：三选一但不能维持现状——删文档与 spec §1 那句；或者实现它（runs 行没有 spec 字段，得经发射单 `spec_ref` 做 join，工作量不小）；或者改成指向已有维度的说明。

**F9 `--grant spec-standing-gpu-1h` 文档教、代码拒**
位置：`skills/deploy-layer/references/r5-choices.md:41` 对 `blockedcmd.py:196-201`
复现（我跑的）：`blocked answer B001 --layer deploy --answer ... --chosen one --grant spec-standing-gpu-1h` → exit 2，`blocked.grant_ref: grant is not active (got: 'spec-standing-gpu-1h')`。同一份文档 `:31` 又说常设授权"proceed directly with no grant in force"，前后自相矛盾；`ledger.py decision --authorized-by spec-standing-gpu-1h` 那条路却收（`decisionscmd.py:181`）——同一个字面量两个写入口一收一拒。
修法：二选一并写死。要么 blockedcmd 放行这个字面量（`authorized_by` 直接落它，同步改 `writes.json` `r5_choice_assembly.field_map` 里"否则 `grant:<grant_ref>`"那句）；要么删掉 `:41` 的括号，改成"常设授权按 §2.6 直接干、不经 blocked answer"。

**F10 照文档做，agent 的自决会被记成用户的裁决**
位置：`r5-choices.md:23`（`--to-layer` "usually user"）与 `:36-38`（用 `--layer deploy` 答它）对 `blockedcmd.py:166-171`
症状（子审计实测）：`to_layer=user` 的行答复时 `answered_by` 被强制成 `user`，于是机械拼出的 decision 是 `decided_by=user`、`authorized_by=<答复会话自己写的 answer 正文>`，不指向任何 grant。R6 存在的意义就是留下"这是 agent 自决"的痕迹，这条路把痕迹反过来写了。
为什么挡：这是审计链造假，且是照文档做出来的。
修法：文档写清 `to_layer=user` 的条目只能转录用户原话，自决一律用 `to_layer=idea|deploy` 加真 grant 或走 `ledger.py decision`；代码侧补一条机验更稳——`to_layer=user` 的答复禁止带 `--grant`（带了就说明不是用户在裁决）。

**F11 R6 留痕唯一的命令在文档里一次都没出现**
位置：`skills/deploy-layer/SKILL.md:75-77` 要求"每个自决都写抉择账留痕"，`r5-choices.md:31` 说常设授权可以直接干——都没说写什么。唯一能写的是 `ledger.py decision --layer L --question --options --chosen --reason --where --authorized-by [--decided-by agent] ...`（`decisionscmd.py:94-106`），全 plugin 无文档。
修法：补进 `r5-choices.md` 的"Which mode applies"与"Recording the ruling"两节。

**F12 principles 文档把 lint 规则写反（【已撤销】）**
位置：`skills/idea-layer/references/principles.md:23-25` 说"Every other status value requires a non-empty criterion_cmd … principles-lint enforces this too"；`principlescmd.py:163-178` 只对 【现状】/【已定要改】 要求，【已撤销】 明确豁免。
为什么挡：撤销一条未接线原则的会话会照文档拒绝改动或者去编一个判据。
修法：改成"只有两个在用状态要求判据；【已撤销】 无此要求"。

**F13 证据体裁文档与 evidence_lint 打架，照文档写的溯源块过不了自己的 lint**
位置：`skills/oversight/references/report-genre.md:16` 把 `tables/rows.json` `evidence_lint_exempt.metadata_kinds` 复述成五类，把"账本行数"漏成"ledger line numbers"；`:30-32` 又告诉写作者溯源三件不需要 `$ ` 行。`evidence_lint.py:75-96` 的豁免只在 frontmatter 块内生效，正文里的行数会被判 `no-repro-command`（我自己的样例里 `Row 42 ...` 那行就被判了）。
为什么挡：监察面按自己的文档写报告，会被自己的 lint 打回。
修法：(a) 表与 linter 二选一对齐（表说行数豁免，linter 没豁免）；(b) 文档写明溯源块必须落在 `---` frontmatter 里面，因为那是唯一真正覆盖行数的豁免。

**F14 路由表写了一条不存在的命令形态**
位置：`tables/routes.json:14`：`"有什么在等我" → ledger.py blocked 渲染（待决队列视图）`；`blocked` 只有 `open|answer|close|withdraw`，真命令是 `ledger.py render blocked`。
为什么挡：这张表就是路由薄壳的全部内容，用户最常说的一句话直接指向一个无效命令。
修法：改成 `ledger.py render blocked`（表是真源，改完复跑 spec_lint）。

### C 组：同一份契约三方不一致

**F15 `status` 的输出形态：spec §2 说三块分层视图，表里没有，代码也没有，四份 skill 却照 spec 写**
位置：`.scratch/research-loop/spec.md:129-135`（① 本层工作面 ② 本层待决队列＝open 且 to_layer=本层 ＋ answered 且 from_layer=本层 ③ 有效授权）对 `tables/rows.json:1164-1183`（`status_view` 里 `open_blocked` 是"status=open 的全部"，没有"answered 且 from_layer=本层"这一项）对 `statuscmd.py:367-383`（一坨扁平 JSON，15 个字段，`--layer` 只写进 `layer` 字段，不做任何过滤）对四份 skill（`idea-layer/SKILL.md:38-41`、`deploy-layer/SKILL.md:33-37`、`run-layer/SKILL.md:32-34`、`oversight/SKILL.md:33-35` 都描述"三块分层视图"）。
我自己跑 `status --layer deploy` 与 `--layer run` 的输出确认：字段集完全相同，`open_blocked` 不按 to_layer 过滤，"本层提出且已答复"的那一项根本不存在。
为什么挡：这是"会话开工必读"的唯一命令，四份 skill 教会话去读一个不存在的输出形态，会话会把别层的待决条当成自己的队列。
修法：spec §2 是设计权威，正解是补表再补码——`rows.json` `status_view` 加两项（本层待答的 open、本层提出且已 answered 的），`statuscmd` 实现，四份文档自动变真（改表走 R5 留痕）。临时止血是改四份文档描述现状，但那样就丢了 spec §2 承诺的隔层。

### D 组：验收证据缺口

**F16 spec §9 九场景里两条的关键断言不成立**
位置：`tests/test_e2e.py:438-451`（场景⑤）、`tests/test_e2e.py:209-237` 与 `:276-278`（场景①）
⑤ 把 `--kind failure --evidence <log_path>` 传进去再断言读回来还是它——测的是自己刚写的字符串，spec 要的"blocked 新增一条 kind=failure 且 evidence 带日志路径"没被验证；① 的"核查 clean"是手写一份 `verdict: clean` 的 md 再断言读回来是 clean，`evidence_lint` / `verify_report` 一个都没跑（工单 Comments 记的是主会话手工跑过一次，回归套里没有，commit 64e8c3d 记的就是这件事）。
为什么挡：这两条是"九场景走通"这句验收话的一部分，现在的写法回归不了——报告模板或两个 lint 任一改动都不会让测试变红。
修法：⑤ 断言 evidence 路径真实存在且日志含失败特征，或把日志喂给 `error_classify.py` 断言不返回 `unknown`；① 写完报告后加两行 `helpers.run_script(root, "evidence_lint.py", path)` 与 `verify_report.py`，各断言 exit 0。

---

## 二、不挡合并的观察

- `storycmd.py:137` 把 `writes.json` 的 story 白名单硬编码成字面 set，兄弟模块都读表；值现在一致，只是漂移风险。
- 三份"读发射单目录"的实现：`trace_check.py:180`、`doctor.py:326`、`querycmd.py:76`，错误处理各不相同；两份 jobs.json 宽容读法：`trace_check.py:211`、`statuscmd.py:128`。建议合进 `_lib`。
- `trace_check.py:95-136` 内联了一份 `parse_principles` 副本（ImportError 兜底）；F6 修完解析器，这份会静默走偏。
- id 分配跨档不一致：`blockedcmd.py:131,232,349` 与 `decisionscmd.py:139,205` 只读主文件，`storycmd.py:88`、`feedbackcmd.py:33,65` 读归档。v1.1 归档落地前不修就是 id 重用。`launchcmd.py:148` 的 decision 存在性校验同样没跨档（spec §2.1 要求校验类跨档）。
- `inspection_report` 的空判据两处不同：`statuscmd.py:223` 用 `== ""`，`trace_check.py:636` 用 `.strip()`。实测：报告头写成 `"   "` 或没这个字段，`status` 的 `batches_pending_inspection` 是空的，而 `--closeout` 照报 empty——部署层的工作面看不见那件会卡住收官的事。
- `output_check.py:132` 把 `artifact_dir` 按 cwd 解析，`record.py:84` 按工程根解析。实测：换个 cwd 跑同一张发射单，verdict 从 ok 变成 missing-output、exit 4。
- `record.py:114` 丢弃 `metrics_cmd` 的退出码：抽数命令中途失败但尾行仍是合法 JSON 时，数字照样入账。
- `launchcmd.py:217` 对所有 quick 单整体豁免批准门禁（spec §5 字面只豁免"spec_ref 空的 quick 单"）；`trace_check.py:367` 与它一致，两边至少没打架。
- `launch.py:49` 超时退出码 1，与任务自己的 exit 1 撞车，只能靠台账 `state=timeout` 区分。`workdir` 为子目录的分支没有测试，但实测走通（launch → RUNMETA → jobs → record 全链 exit 0）。
- `_lib.py:452-460` `registry_tasks` 不看 `registry_query` 的退出码：查询命令挂了会表现成"任务不在注册表"。
- `runscmd.py:62` 跑判据不设超时，判据挂住会挂住部署层会话。
- `genschemas.py:126-138` 的 `--check` 只比对生成清单里的文件，`schemas/` 里多出的陈旧文件照样过。
- `trace_check.py:147` 的 `_err` 只产 severity=error，汇总行的 warnings 恒为 0。
- `launchcmd.py:99-105` 的 `approve-spec` 会把其他 frontmatter 字段重新 JSON 序列化（`title: my demo spec` → `title: "my demo spec"`），模块 docstring 却说"其他头字段原样不动"；正文与 digest 不受影响。
- `storycmd.py:150` 的 `--layer` 没有 `choices=`，与所有兄弟模块不同。
- `regression_check` 把每个 (metric, filter) 对都列出来，不区分"冲突"与"一致"；spec §2.5 的"回归警报"说的是冲突清单。
- `ledger.py:85-95` 的 `_import_cmd_module` 只捕 ImportError，非 ImportError 的 import 期异常会带崩裸 `--help`（`--help` 今天跑得通，已验证）；改成捕 Exception 是一个词的事。
- 常设授权的阈值 `standing_authorization.max_expected_runtime_s` 除 config-check 的 null 报告外无人读，没有任何机验拿它对过发射单的 `expected_runtime_s`。
- `tables/rows.json:744,757,761` 说 arm/quick/filter "可空"，机器形态里 arm/quick 不可空；今天无影响。
- 测试面（子审计给的，按"测试写法"归档）：`test_blocked_decisions.py:236-240` 与 `:385-392` 两条拒绝面测试其实是被 argparse 的 choices 挡掉的，删掉代码里的权限检查测试照样过；`test_blocked_decisions.py:560-570` 丢掉 stderr 只断言 exit 2（argparse 报错也是 2）；场景③只比 acc 一个指标的 value（`test_e2e.py:376-380`）、场景④的 status 是写死的字面量而不是取自 output_check 的 verdict（`:393-394`）、场景⑥没断言 `attempts[0].log_path`（`:489-491`）、场景⑨的 or 断言有一条死分支（`:743`）；`test_genschemas.py:226` 的期望值来自被测代码同一张表；`test_config.py:265` 的 in-process init 把 14 行 config 报告漏进跑器 stdout。
- `tests/helpers.py` 的默认件自相矛盾：`:24` 的 METHOD_MD 判据命令与 `:90` 的 registry_cmd 前缀对不上（裸 `make_sandbox` 跑 `principles-lint` 直接 exit 1），`:431`/`:444` 的发射单 argv 与 metrics_cmd 同病；已经攒了五处本地绕行（`test_runs_principles.py:21-34`、`test_doctor.py:30-47`、`test_trace_check.py:152-165`、`test_launch_order.py:36-52`、`test_e2e.py:34-36,57-66`）。修法：`METHOD_MD` 改成 `method_md(registry_cmd)` 在 `make_sandbox` 里调用，`make_launch_order` 加可选 `root=`。另外 `helpers.py:196-203` 那段注释说明 F1 的重叠问题当初是知道的，选择在 fixture 里绕开——所以 e2e 覆盖是绕着这个 bug 长出来的。
- 文档面其余（子审计给的）：`blocked close` 全 plugin 无文档，而 `ledgers.json:20` 把 open|answered 都算活跃，照文档走的循环排不空队列；R9 的 `feedback add/review` 无任何文档；三个干活层从没被告知 jsonl 账要走 `ledger.py query`（这条纪律只出现在给监察面开豁免的地方）；`ledger.py grant` 无文档页；`regression_check` 的调用形态无文档；`closeout.md:10` 让人交 `research-loop.json` 的路径而 `inspector.md:40` 需要的是目录；`research-loop/SKILL.md:41` 把 config-check 当成看退出码的门（它 null 遍地也 exit 0）；三份 SKILL.md 复述了本层账本清单（今天与表一致）；`<plugin-root>` 的措辞在五份 SKILL.md 里都少数了一级；`execute.md:40-42` 让运行层登记台账，没说兜底发射器已经登过；`inspector.md` 的 tools 没给 Write，唯一产物只能靠 Bash 重定向写。

---

## 三、交接清单十条的处置

1. `_lib` 无守卫 json.loads → **挡合并 F4**（实测了 blast radius）。
2. trace_check `--project-root` 假干净 → **挡合并 F2**（文档正是这么教的，所以升级了）。
3. `--help` import 全部模块 → 不挡，维持原取舍，附一个词的加固建议。
4. helpers 默认件不对齐 → 不挡，但绕行已有五处（不是两处），一起修掉。
5. output_check 的 min_bytes 类型错文案 → 不挡；同一段里 cwd 解析那条更值得修。
6. launch 超时退出码 / workdir 分支无测试 → 不挡；workdir 分支实测走通，只是没测试。
7. test_launch_order 的 8 行重复 → 不挡。
8. evidence_lint 十六进制豁免吞十进制 → **已经修好了**，实测 7 位十进制会被判、git HEAD 被豁免（commit 3dfaa86），这条从清单里划掉。
9. 各处自定文案 → 不挡，除 F13 那处文档与 linter 真打架的。
10. 自决点 #138-145 → 全部认可，不推翻。#145（`launch_order_ref=run_id`）单独核过：`launch.py:137` 写 run_id、发射单按 `<run_id>.json` 命名、`trace_check` 按文件名 stem 索引，三处闭合。

修复排序建议：F1 → F2 → F15 是一组（都动溯源/视图这条主干，且 F1 修完 e2e 的 fixture 绕行要跟着拆）；F3/F4/F5/F6 是四个独立小修；B 组八条文档改动可以并成一波；F16 跟着 F1 一起改测试。
