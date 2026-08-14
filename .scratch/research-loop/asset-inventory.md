# 资产账：重设计之后现有的东西还有什么能利用

盘点数据我收到三片（账本 CLI 与子命令、机器检查程序、结构化表与 schema），共 28 个条目。另外三片没有到我手里，缺口在本文最后一节点名。文中标"我实测"的数字是我这次自己跑命令得到的，其余标了出处的来自盘点与复核。

## 零、先说两条会改变判定标尺的事

任务书给我的第 3 条标尺（example 由 verifier 在干净沙盒里真跑、结构化子集比对）已经被 `.scratch/research-loop/redesign.md` 第十四节推翻。我自己读了原文（第 205-211 行）：「example 是写在角色 skill 里的一段示范……它不进机器，不被任何程序执行，也不参与比对」「连带撤销：verifier（例子验证程序）这个东西从共性清单里删除……词表的 17 个词随之减到 16 个」。第十四节开头写明「本节位阶高于前面所有节」。

同一份文档新增的第十五节（第 217-273 行）把账本从九本砍到六本：decisions、issues、handoffs、runs、grants、feedback。assumption 并进 decisions，launch order 并进 handoffs（用 work_type 区分），原则并进 decisions（没有父引用的根决定）。三片盘点全部是对着现在 22 本账的 `tables/ledgers.json` 做的，凡是判词里写"跟着账本走"的条目，都要按六本账再算一遍。

## 一、三个数

- 能原样留用：**9 件**
- 要改造：**17 件**
- 退役：**1 件**（`tables/routes.json`）

另有 1 个条目在我收到的数据里被截断，覆盖 `schemas/` 下 9 个文件。这 9 个是 `ledger.py gen-schemas` 从 `tables/rows.json` 与 `tables/ledgers.json` 生成的产物，源表改完重跑生成器就跟着变，不用手改，所以没有算进上面三个数。

九件原样留用的是：`configcmd.py`、`freezecmd.py`、`principlescmd.py`、`storycmd.py`、`ledger_cmds/__init__.py`、`error_classify.py`、`output_check.py`、`spotcheck.py`、`verify_report.py`。

十七件要改造的是：`ledger.py`、`blockedcmd.py`、`decisionscmd.py`、`feedbackcmd.py`、`genschemas.py`、`launchcmd.py`、`querycmd.py`、`runscmd.py`、`statuscmd.py`、`doctor.py`、`trace_check.py`、`evidence_lint.py`、`regression_check.py`、`tables/config.json`、`tables/ledgers.json`、`tables/writes.json`、`tables/rows.json`。

## 二、施工机器能复用什么

第一段要的四件施工机器（工单带验收命令、波脚本改"验收红不算完加修三轮废掉重做"、收账后置机器核对、发射看门狗），现有底子只有一件。

- `/home/y-guo/reproduce/new1/.claude/skills/ticket-run/wave.js`（203 行）：波内工单并行、每张一棵工作树一条分支、实现到评审到修复的循环都在这里，`MAX_ROUNDS = 5` 在第 21 行，第 165 行写着第 4 轮起换升级模型。要改两处：一是它现在没有任何执行 shell 的路径（我实测 `exec`、`spawn`、`require(` 三个词零命中），只派 agent，所以"工单带验收命令、退出码 0 才算完"是新写；二是"修三轮废掉重做"和现在的"修五轮"是两件事，循环体要重写。
- `/home/y-guo/reproduce/new1/.claude/skills/ticket-run/prompts/` 四份提示词（implementer 51 行、reviewer 38 行、re-reviewer 29 行、final-reviewer 24 行）：实现者与评审者的规程模板，能当骨架留用。
- `/home/y-guo/reproduce/new1/.claude/skills/ticket-run/SKILL.md`（116 行）：第 75 行起的 Phase 3 收账，现在是主会话人工读，第 7 条要的"收账后置机器核对"没有对应程序。
- 看门狗：我在 `.claude/skills/` 下 grep「看门狗」和「watchdog」，零命中；`gpu-run/scripts/` 里只有 `gpu_status.sh` 一个脚本。这件是从零造。

工单的"验收命令"字段有三条现成的命令可以填，都是退出码可判的：
- `python3 research-loop/tests/run_all.py`（65 行，标准库跑手，本机没装 pytest）。我实测输出 `-- run_all: 319 passed, 0 failed`。
- `python3 research-loop/scripts/ledger.py gen-schemas --check`。我实测退出码 0。
- `python3 research-loop/scripts/doctor.py`（580 行，十段只读体检）。

## 三、verifier 能复用什么

verifier 已被第十四节撤销，所以这一组要分两半答。

**如果不再造 verifier**，现成顶得上一部分职责的机器手段有四件，但它们管的都是数据与数据之间不脱节，管不了 spec 与代码不脱节：`gen-schemas --check`（源表与生成产物对账）、`tests/run_all.py`（319 项）、`doctor.py`（十段体检）、`trace_check.py`（八项跨账引用检查）。第十四节自己把这个敞口写明了：「spec 与 codebase 脱节没有机器兜底了……这个敞口等结构定下来另想办法，不在本轮解决，也不许用 example 去补」。

**如果以后要补机器兜底**，下面这几件是现成零件，抬手就能用，不用重造：

- `research-loop/tests/helpers.py`（488 行）是核心。`make_sandbox`（第 69 行）按 `tables/` 建一份配置齐全的临时工程、建五个目录、写一份桩注册表；`make_git_sandbox`（第 124 行）、`make_rails_sandbox`（第 136 行）是另外两种前置状态；`run_ledger`（第 256 行）和 `run_script`（第 261 行）用子进程跑命令并收退出码；第 281 到 476 行有八个行工厂（`make_blocked_row`、`make_decision_row`、`make_grant_row`、`make_story_row`、`make_runs_row_normal`、`make_runs_row_criterion`、`make_launch_order`、`make_suggestion_row`）。"干净沙盒副本加前置状态加跑命令"这三件全在这里，而且 319 个测试正在用。
- `research-loop/scripts/_lib.py` 的 `validate()`（第 393 行）加 `_when_matches()`（第 326 行，条件必填）是现成的结构化比对引擎，比对"这些字段出现且等于这些值"用得上。
- `research-loop/scripts/fallback/` 五件（`fake_experiment.py` 69 行、`fake_metrics.py` 57 行、`launch.py` 252 行、`record.py` 200 行、`registry.py` 58 行）是插件自带的假铁轨。`fake_experiment.py` 的第一行文档串自称「plugin self-test fixture only……兜底三件同时充当 plugin 自测的假铁轨」。要跑发射类动作又不占显卡，桩发射器是现成的。

## 四、改名与加字段要动哪些文件

### 三处撞名，两处还没裁

1. **blocked 改叫 issues，撞已有的 issues 账本。** `tables/ledgers.json` 第 16 行的 `issues` 是工单 md 账（`.scratch/*/issues/`，owner=deploy），第 19 行的 `blocked` 是待决升级账（`ops/blocked.jsonl`，cap 500），是两件事。硬取 `issues` 这个名字的地方：`trace_check.py` 第 259 到 263 行、`statuscmd.py` 第 85 行和第 100 行；行结构里有独立的 `issue_min` 块和三处 `$ref_to: issues.issue_id`；产物里有 `schemas/blocked.schema.json` 第 113 行、`schemas/decisions.schema.json` 第 47 行、`schemas/launch_order.schema.json` 第 93 行、`schemas/owners.default.json` 第 10 行。redesign.md 第 149 行把 blocked 改 issues 当纯机械改名列进第一段，全文没有一个字提到这处重名。要先定名字才能动手。
2. **role 撞 config.json 已有的 roles 键。** `tables/config.json` 的 `roles` 键装的是 `{inspector_model, reader_model}`，默认值硬写在 `scripts/_lib.py` 第 97 行，`configcmd.py` 第 39 行的 `_DEFAULTED_KEYS` 写死了这个键名，`tests/test_lib.py` 第 547 行对这个字面量做断言。这处 redesign.md 里也没有检查过。
3. **verifier 撞 verify_report.py。** 这个文件的文档串自称 the mechanical verifier。第十四节撤销 verifier 之后这处消失，记在这里备查。

（review 撞 reviewer 那处 redesign.md 第 158 行已经裁过，反馈账的 review 审批行不动。）

### 改名体量

我用 `grep -o` 实测出现次数：**blocked 出现在 41 个文件里**，前六名是 `tests/test_blocked_decisions.py` 174 次、`blockedcmd.py` 119 次、`tests/test_e2e.py` 81 次、`doctor.py` 56 次、`tests/test_lib.py` 50 次、`tests/test_query_status.py` 40 次。**oversight 出现在 30 个文件里**，前五名是 `skills/oversight/SKILL.md` 13 次、`decisionscmd.py` 8 次、`evidence_lint.py` 6 次、`tables/writes.json` 5 次、`regression_check.py` 与 `tests/test_blocked_decisions.py` 各 4 次。改名的一大半工作量在测试里，盘点的 14 条改造清单没有一条提到测试。

### 两处改漏了不会报错

- `decisionscmd.py` 第 85 到 88 行：`non_oversight_layers` 是读表之后用字面量 `"oversight"` 做减法。把角色改名成 reviewer 而漏掉这一行，过滤条件永远不成立，reviewer 会静默拿到 grant 和 decision 的写权，不报错。
- `feedbackcmd.py` 第 17 行：`_SUGGESTION_LAYERS` 是硬编码四值集合，第 24 行的报错文案又把四个值抄了一遍。只往表里加 analysis 而不改这里，analysis 提不了反馈，错误信息里连 analysis 这个词都不会出现。

### 不用改代码的

`--layer` 的可选值有四处（`blockedcmd.py` 第 45 行、`launchcmd.py` 第 47 行、`runscmd.py` 第 124 行、`statuscmd.py` 第 368 行），都是注册时现从 `tables/writes.json` 的 `layer_param.values` 读的。把表里四个值换成五个，这四个文件零行代码改动。真正写死角色字面量的只有上面那两处。

### 机械改名要跳过的假朋友

`domain` 这个词只出现在 `configcmd.py`（4 处）和 `tables/config.json`（18 处），意思是"取值范围"，是配置键说明的栏名，跟要新建的 work_type 无关。扫 `domain` 会把这 22 处一起扫掉。

### 加字段落在哪

`decisions_row` 的必填清单在 `tables/rows.json` 第 248 到 260 行，十一个字段里没有 work_type，也没有指回上层决定的引用字段。三处写口要同步补：`decisionscmd.py` 的 grant 和 decision 两条，`blockedcmd.py` 第 359 到 380 行 r5-choice 机械拼装的 decision 行。追溯链检查扩到 `trace_check.py`，现成模板是 `check_forward_chain` 对 `decision_refs` 的处理（第 298 到 339 行：查目标存在，再查 `status == decided`），双向核对的模板是 `check_affects`（第 327 到 337 行与第 400 到 425 行）。

还有一处没人提：`research-loop/.claude-plugin/plugin.json` 的 description 现在写的是「three working layers, four on-disk channels……an independent oversight plane」，是插件自己的门面。

## 五、机器检查能留几个

八个检查程序，原样留 4 个，改 4 个。

原样留用：
- `scripts/error_classify.py`（126 行）：读故障分类表按顺序试规则，全不中就报 unknown，从不猜。三个旧词零命中，输入全由命令行给。
- `scripts/spotcheck.py`（86 行）：固定种子抽样器，同一个文件、种子、条数每次抽出同一批行，输出整份文件的 sha256 和抽中行的前 80 字符。第 9 条要的"排查反常结果时抽样读原始输出"就是它。
- `scripts/verify_report.py`（248 行）：核验报告里的 `path:line` 引用、`> ` 摘录逐字对上原文、`$ 命令`加`= 值`重跑对账。
- `scripts/output_check.py`（189 行）：按发射单的 expected_outputs 查产物落地情况，`expected_outputs` 为空也判红。这一件是暂判——它是发射单格式的纯消费者，而发射单格式在第二段要重做。

要改造：
- `scripts/doctor.py`（580 行）：十段里 caps 和 archives 两段从 `tables/ledgers.json` 现读账名（第 244 行），账本改名后自动跟着走；五段是纯转发。真要改代码的只有 half-state 一段，56 处 blocked 全集中在这里，另有三条补救命令文本在第 377、417、457 行。
- `scripts/trace_check.py`（695 行，插件里最长的检查脚本）：八项跨账引用检查，是加"依据决定"追溯链最省事的落点。但它自己硬取 `issues` 这个账本名（第 259 到 263 行、第 319 到 324 行），撞名会打到它。
- `scripts/evidence_lint.py`（275 行）：功能代码一行都不用改，只有第 2 行文档串的 `Oversight-face lint` 会被机械改名扫到。它管的是报告体裁（结论词禁用、断言数字三行内必须带 `$` 复现命令）。
- `scripts/regression_check.py`（200 行）：比对算法在第 55 到 75 行的 `build_comparisons`，值得留；外壳（写进 reports/、被 oversight 技能调用）跟着角色归属走，归 analysis 还是 reviewer 没定。

`tables/routes.json`（26 行，19 条路由）是唯一判退役的一件。退役前要先拆一处机器依赖：`statuscmd.py` 第 267 到 294 行按 say 列前缀取 to 列原文，塞进 status 输出的 `waiting_on[].action`；`rows.json` 的 status_view 契约写死「action 取值只许是 routes.json 的 to 列已有动作名」；`tests/test_query_status.py` 第 412 行起有一个测试专门断言这件事，`tests/test_lib.py` 第 565 行断言 tables 键集合恰好是那五张表。另外第 21 行把 `doctor.py` 注册成用户触发命令，`tables/writes.json` 第 120 行和第 127 行把 doctor 写进归档流程。直接删，status 命令和这两个测试当天先坏。

## 六、散文文档里有什么值得抢救

这一组我手上的盘点数据没有覆盖，三片里没有一片负责 `skills/` 和 `agents/`。下面的行数是我自己扫的，判断依据是别片的交叉引用。

`research-loop/skills/` 五个 SKILL.md 加 14 份 references，再加 `agents/inspector.md`，共 24 个 md、1860 行。按第十四节「五个角色是五个 skill，不是五份散文说明书」，这批整体退役。里面有五处是规矩本体，不是散文：

- `skills/oversight/references/report-genre.md`（43 行）：证据体裁的成文，`evidence_lint.py` 和 `verify_report.py` 是它的执法者，通例第 5 条保留了这条规矩。
- `skills/deploy-layer/references/launch-orders.md`（131 行）：发射单格式的成文。第二段要重做 launch order 格式，这是唯一的现成底稿。
- `skills/deploy-layer/references/failures-inbound.md`（112 行）加 `skills/run-layer/references/failures.md`（72 行）：error_classes 表由谁定义、谁消费，是通例第 7 条的成文。
- `skills/run-layer/references/execute.md`（165 行）：第 24 行是全仓唯一写了 `doctor.py` 调用点的技能文档，另有第 72 行调 `output_check.py`。
- `research-loop/agents/inspector.md`（65 行）：检查 subagent 的三件套调用清单（trace_check、evidence_lint、verify_report），模型写 opus。

`.scratch/research-loop/` 下的散文：`spec.md` 48649 字节、`spec.en.md` 41555 字节、`audit-merge.md` 70171 字节、`plan.md` 18761 字节、`review-adoption-plan.json` 235782 字节、`spec_lint.py` 11137 字节。其中 `spec_lint.py` 是机械校验 spec.md 与 `tables/` 数据表是否一致的脚本。第十四节撤销 verifier 之后，它是仓库里唯一一件"拿机器判说明书还准不准"的现成东西。第十四节明写这个敞口本轮不解决，我只报告这件东西存在。

## 七、复核推翻的判定

1. **`storycmd.py` 原判要改，实际不用改。** 改造理由写的是"--layer 的合法取值改成新五角色枚举"，但这个文件的 `--layer` 根本没有 choices（第 168 行），全文只有第 75 行一句 `if args.layer != "idea"`，idea 在五角色里原样保留。改判原样留用。翻案条件只有一个：如果参数名 `--layer` 整体改叫 `--role`，它要动；但那样另外七个文件全要动，而 redesign.md 第 149 行的机械改名清单里没有这一条。
2. **`evidence_lint.py` 原判不用改，实际要改一处。** 第 2 行文档串是 `Oversight-face lint`，机械改名扫得到。功能代码仍是零改动。另外它的留用依据引错了：被引的那句在 redesign.md 第 114 行，前面带着「我先替你分的一处（可否决）」，第 187 行还把它列进「还悬着三条」，是未定案项，不是已裁项。
3. **`tables/ledgers.json` 和 `tables/rows.json` 原判把 blocked 改 issues 当直白改名。** 实际撞已有账本键，八九处硬取要一起改，得先定新名字，不是表里改一行字。
4. **`tables/writes.json` 原判"改表里的值就够"。** 实际代码里有两份硬编码副本，其中 `decisionscmd.py` 第 85 到 88 行那处改漏了会静默放宽写权。另外 `blocked_transitions.open.legal_to` 不只是值域，是一张楼梯拓扑，analysis 是平级角色不是楼层，没有现成映射。
5. **`doctor.py` 条目有三处事实错。** 它不是 scripts/ 最长的（我实测 trace_check 695 行、_lib 619 行、doctor 580 行）；它不是"从不写盘"（第 576 到 577 行 `--out PATH` 会落盘，准确说法是不写 reports/ 和任何账本目录）；说"没有任何技能文档写运行 doctor.py"是错的（execute.md 第 24 行有，routes.json 第 21 行把它注册成用户触发命令）。所以 routes.json 退役要连 doctor 这一行一起处理，原改造清单四条里没有它。
6. **`trace_check.py` 原判的依据不成立。** 依据是"blocked、oversight、domain 三个旧词零命中所以改名碰不到它"。三词零命中属实，但这个查法只找旧名，看不见它硬取的是新名 `issues`（第 259 到 263 行、第 319 到 324 行）。同一份盘点在 doctor 条目里查出了撞名，却把 trace_check"不用碰"的结论留着，两条不自洽。另外"36 个测试全仓单文件最多"不对，`test_blocked_decisions.py` 41 个最多。
7. **`tables/rows.json` 原判"没有任何指向上层决定的现成字段"，说反了。** `decision_refs` 就在这张表里（第 983 到 992 行），还带着 `check_affects` 的双向核对，是"依据决定"字段最现成的模板。同类的还有 `decisions_row` 自己的 `authorized_by`（形态 `grant:D00x`）和 `principle_ref`。这句话如果不纠正，主会话会以为要从零发明字段形态。
8. **`launchcmd.py` 判要改是对的，理由是错的。** 它写的理由是"layer_choices 的来源换成新角色枚举"，那是零行改动（见第四节）。真正让它必须改的是 redesign.md 第 150 行把 launch order 格式明列进第二段的施工清单。
9. **`configcmd.py` 判不用改成立，但"完全数据驱动"这句要打折。** 硬编码有三处：第 153 行把 cap 规则写死、第 164 到 166 行 inspection_policy 的键名和唯一合法值写死、第 39 行三个键名写死。三处都不是角色名或账本名，所以五角色重设计确实碰不到，前提是 runs、runs_legacy、inspection_policy、roles 这四个键名不动。

## 八、盘点里发现的意外事实

1. **redesign.md 在盘点期间被改过。** 复核员看到 mtime 从 03:17 走到 03:26、行数 185 变 215；我这次读到的是 273 行，改动时间 03:31。新增第十四节和第十五节，第十四节自称位阶高于前面所有节。任务书给我的第 3 条标尺（example 真跑、verifier 比对）已经作废。
2. **第十五节把账本从九本砍到六本，三片盘点的地基被改写。** 现在 `tables/ledgers.json` 里是 22 本账，新树只有 decisions、issues、handoffs、runs、grants、feedback 六本，外加 `EVALUATION.md` 和 `analysis/` 目录。`principlescmd.py` 判原样留用的理由是"只吃 METHOD.md 的八列表和 runs 行、跟角色无关"，这条依然对，但 principles 这本账本身要被并进 decisions，所以它留不留是另一个问题。
3. **第十四节说"现有代码里 `ledger.py init` 干的就是这件事"，与代码不符。** `configcmd.py` 的 `_run_init`（第 254 到 292 行）只写一个 `research-loop.json`，然后自己过一遍 config-check，不建任何目录、不建任何账本文件。真正会建目录的代码在 `tests/helpers.py` 第 116 行（`_SANDBOX_DIRS` 是 ops、ops/launch_orders、plans、reports、.scratch）。init 要按第十五节建那棵树，是新写，能抄的是 helpers.py。
4. **我只拿到三片，没被任何人判过的大件有五处。** 最要紧的是 `research-loop/scripts/_lib.py`（619 行）：schema 校验引擎 `validate()` 与条件必填 `_when_matches()`、带文件锁的 jsonl 追加、白名单就地更新、`alloc_id`、注册表校验、frontmatter 解析、spec 摘要、git HEAD 都在这里，是全插件共用的底座，六本账重建时最该先看它。另外四处是 `tests/` 16 个文件 8672 行、`scripts/fallback/` 5 件 636 行、`skills/` 与 `agents/` 24 个 md 1860 行、`.claude-plugin/plugin.json`。
5. **上一次盘点没跑成，这次的结果不写回去，第十一节还是空的。** 第十四节自己记了一句：第十一节的资产盘点 workflow 六分片并行没有留下任何产物，`workflows/` 目录下只有脚本目录，既无 journal 也无 transcript。我 find 全仓（深度 3）没有 `workflows` 目录。redesign.md 第 165 到 167 行现在是一句占位话。
6. **施工机器离第一段的要求差三件。** `wave.js` 里没有任何执行 shell 的路径（`exec`、`spawn`、`require(` 全零命中），它只派 agent；`MAX_ROUNDS` 是 5 不是三轮废掉重做；收账在 SKILL.md 的 Phase 3，是主会话人工读；看门狗在 `.claude/skills/` 下零命中。四件里只有波脚本有底子。
7. **测试基线是我自己跑的。** `python3 research-loop/tests/run_all.py` 输出 `-- run_all: 319 passed, 0 failed`；`python3 research-loop/scripts/ledger.py gen-schemas --check` 退出码 0。本机没有 pytest，`tests/run_all.py` 是标准库写的跑手。这说明现有代码是能跑的真代码，不是设想稿。
8. **插件门面还写着旧结构。** `.claude-plugin/plugin.json` 的 description 是「Layered research-loop process plugin: three working layers, four on-disk channels, criterion gates, structured ledgers, and an independent oversight plane.」
9. **规模合计。** Python 代码 15570 行（`scripts/` 根 3255、`ledger_cmds/` 3007、`fallback/` 636、`tests/` 8672），tables 加 schemas 2604 行，skills 加 agents 1860 行。