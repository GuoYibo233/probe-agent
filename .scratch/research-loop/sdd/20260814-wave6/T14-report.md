# T14 doctor.py — 实现报告

工单：`.scratch/research-loop/issues/14-doctor.md`
分支：`ticket/20260814-wave6/T14`（工作树 `new1-wt/20260814-wave6-T14`，已删除，分支保留）
base：`e8539e0d6022dc84626f0669d7e95eb99ff3dbbb`
head：`0c23d9dfc351801c8028ca958628951e18a462ac`

## 一、做了什么（对照工单逐条）

### 范围声明

- 只落两个新文件：`research-loop/scripts/doctor.py`、`research-loop/tests/test_doctor.py`。
  没碰 `run.py` / `MAP.md`（工单明写"不改"）。
- `research-loop/tables/routes.json` 里"体检一下 / doctor"这条路由早在之前的 ticket
  就已经登记，指向"doctor.py 一键检查（§4）"，本单不需要再改路由表。

### CLI 形态

`doctor.py [--project-root P] [--out PATH]`：
- `--project-root` 缺省时按 `_lib.find_project_root()` 从 cwd 向上找；找不到
  → stderr 报 "project not wired" + exit 2（跟 `trace_check.py`/`regression_check.py`
  同一套"连体检都开不了"的约定，工单没规定这条，是我按仓库既有惯例补的）。
- 项目找到之后一律 exit 0（"体检是建议件"）。
- 报告永远打到 stdout；给了 `--out` 就额外原样写一份到那个路径；从不写
  `reports/`，从不写任何账本目录（测试里拿"跑前跑后整个沙盒文件清单+sha256
  不变"直接钉死这条，不是只看"没往 reports/ 写"）。
- 末行固定 `doctor: <N> findings across 10 sections`（M 恒为 10，十节每次都跑、
  都出现，不会因为某节没内容就消失）。

### 十节逐一对照

1. **config**：subprocess 跑 `ledger.py config-check`（cwd=项目根，不用 `--root`），
   stdout+stderr 原样转贴。exit≠0 记 1 个 finding；exit=0 时那些"null key ...
   -> locks/default"的信息行不算 finding（干净沙盒测试直接断言总数为 0，
   验证了这条）。
2. **trace**：subprocess 跑 `trace_check.py`，转贴。findings 数从它自己的汇总行
   `trace_check: N errors, M warnings` 解析出 N+M；解析不到（异常输出）才退化成
   "exit≠0 记 1"。
3. **evidence**：列 `reports/*.md`（非递归），对每个文件单独起一次
   `evidence_lint.py <file>`（工单原话"逐个"），各自的 stdout 行数就是该文件
   findings 数，全部转贴。目录不存在或没有 md 文件都各给一行说明，0 findings。
4. **principles**：subprocess 跑 `ledger.py principles-lint`，转贴；exit≠0 时
   findings = stderr 非空行数（`principlescmd._lint_errors` 本来就是一条违规一行）。
5. **regression**：runs 账（跨档）里挑 `recorded_at` 最大的非空 `batch_id`，
   跑 `regression_check.py --batch <id> --dry-run`（`--dry-run` 是硬约束，不然
   会越权写 `reports/`，那是监察面独占地盘）；没有批次只出一行 "skipped: ..."，
   0 findings。regression_check 本身只报事实不判（R2），exit=0 时这节 findings
   恒 0——它不是"违规检测器"。
6. **caps**：对每个 jsonl 账（`tables/ledgers.json` 里 format=jsonl 的主表键，
   加上项目实际接线了的可选账 runs_legacy）算有效 cap = `research-loop.json`
   的 `ledger_caps` 覆盖值，没覆盖就取 `ledgers.json` 表默认；cap=null（runs/
   runs_legacy 恒 null）跳过。行数 ≥ cap → finding，文案按工单原话写死
   "archive lands in v1.1; trim manually or raise the cap"。
7. **archives**：对同一批 jsonl 账，检查 `<name>.archive.jsonl` 是否存在，存在
   就报行数；不管存不存在都不算 finding（v1 没有 archive 执行件，这节 v1 常态
   就是空）。
8. **worktrees**：`git worktree list --porcelain` 除主工作树外的条目，加上仓库旁
   `<repo>-wt/` 目录下的子目录清单（这正是本次任务自己在用的那套约定：
   `new1-wt/20260814-wave6-T14`）；非 git 仓库时不报错，只说明跳过，0 findings。
9. **half-state**：三类扫描，全部直接读 jsonl（不经任何子脚本），修复建议一律是
   "重跑原命令"的字面文案：
   - 孤儿 decision：decisions 行 `blocked_ref` 非空，但对应 blocked 行
     `decision_ref` 为空或不等 → `re-run: ledger.py blocked answer <BID> ...`；
   - 撤销中断：blocked 行 status=withdrawn，但它同步的 decision（先查
     `decision_ref`，查不到再按 `decisions.blocked_ref` 反查，跟
     `blockedcmd._run_withdraw` 自己的恢复逻辑用同一套查法）仍是 status=decided，
     或者缺一条 `(ref=BID, status=open)` 的重开条 → 二者任一命中都报
     `re-run: ledger.py blocked withdraw <BID> --reason ...`；
   - affects 缺失：发射单 `decision_refs` 指向的某条 decision，它的 `affects`
     没把这个 run_id 列回去 → `re-run: ledger.py launch-order --layer deploy
     --file <发射单自己的路径>`（发射单原地重写是幂等的，回填 affects 会补齐）。
   只做"缺失"方向（forward），不做"decisions.affects 多出一个发射单没认的
   run_id"（affects-extra）那个反方向——那个方向没有"重跑同一条写命令就能收敛"
   的修复动作，本来就该留给 trace 节自己的 `affects-extra` finding，不是这节的
   活。
10. **workplan**：subprocess 跑 `ledger.py status --layer deploy`，转贴；findings
    数取返回 JSON 里 `inconsistencies[]` 的条数（这是 status_view 里唯一明确定义
    为"问题"的字段；`pending_user_decisions`/`open_blocked` 这些是正常在办清单，
    不算问题，没往 findings 里算）。

### 单节崩溃隔离

每节包一层 `try/except Exception`：正常跑完的节把它自己的行拼进报告、findings
累加；节内部抛未捕获异常（不是子进程返回非零——那是正常 finding，是 doctor 自己
这段 Python 代码炸了）→ 记一行 `section failed: <末 3 行 traceback>`，findings 记
1，继续跑下一节，整体最后仍 exit 0。

## 二、怎么验证的

`research-loop/tests/test_doctor.py`，8 个测试，逐条对应工单"测试"里的 5 项
（第 3 项我拆成了"红但不崩"+"真崩溃"两个测试，后者是补的，见下）：

```
$ cd new1-wt/20260814-wave6-T14 && python3 research-loop/tests/run_all.py test_doctor
PASS test_doctor.test_doctor_a_genuinely_crashing_section_is_caught_and_the_rest_still_runs
PASS test_doctor.test_doctor_affects_mismatch_is_reported_and_sandbox_is_untouched
PASS test_doctor.test_doctor_caps_section_flags_ledger_at_or_over_cap
PASS test_doctor.test_doctor_clean_sandbox_all_sections_present_and_zero_findings
PASS test_doctor.test_doctor_interrupted_withdrawal_is_reported_and_sandbox_is_untouched
PASS test_doctor.test_doctor_orphan_decision_is_reported_and_sandbox_is_untouched
PASS test_doctor.test_doctor_out_file_matches_stdout
PASS test_doctor.test_doctor_principles_violation_is_red_but_doctor_completes_and_exits_zero
-- run_all: 8 passed, 0 failed
```

全量回归（含新测试，共 267 个）：

```
$ python3 research-loop/tests/run_all.py
-- run_all: 267 passed, 0 failed
```

测试对应关系：
1. 干净沙盒 → `test_doctor_clean_sandbox_all_sections_present_and_zero_findings`：
   十节标题都出现，末行精确等于 `doctor: 0 findings across 10 sections`。这里
   把 `helpers.METHOD_MD` 默认 fixture 换成了按 sandbox 实际 `registry_cmd`
   现写的一份（默认 fixture 那条 criterion_cmd 是字面 "python3 stub_registry.py
   check-p001"，跟 `make_sandbox()` 生成的绝对路径 `registry_cmd` 对不上，
   principles-lint 会红——这是共享 fixture 本来的样子，不是 doctor 的问题；
   `test_runs_principles.py` 自己每个用例也都是这么重写 METHOD.md 的）。
2. 三类半状态 → 三个独立测试，每个都在跑 doctor 前后拍一次
   `{相对路径: sha256}` 快照并断言相等，同时断言输出里含
   `re-run:` 那句完整建议行。
3. 单项检查件挂掉：
   - `test_doctor_principles_violation_is_red_but_doctor_completes_and_exits_zero`——
     工单原话的 fixture（METHOD.md 塞两行同 principle_id），principles 节红、
     其余九节仍出现、exit 0。
   - `test_doctor_a_genuinely_crashing_section_is_caught_and_the_rest_still_runs`——
     这条是我补的：把 `ledger_caps` 直接改成字符串（绕过 config-check，正常
     流程写不出这种配置），逼 `_section_caps` 里的 `.get()` 真炸出
     `AttributeError`，验证 `section failed: ...` 这条契约文本本身确实生效，
     不只是"重复 PID 那种正常 finding 不会拖垮全局"这一层更弱的保证。
4. caps → `test_doctor_caps_section_flags_ledger_at_or_over_cap`：blocked 账裸写
   501 行（cap 取插件默认 500），断言 `caps.blocked: 501 rows >= cap 500` 和
   文案原句都出现。
5. `--out` → `test_doctor_out_file_matches_stdout`：文件内容与 stdout 逐字相同。

## 三、commit 清单

- `0c23d9d` — T14: add doctor.py one-shot health check + tests
  （`research-loop/scripts/doctor.py` 新建 + `research-loop/tests/test_doctor.py`
  新建，共 776 行）

## 四、自查发现与存疑

- **findings 计数口径是我按工单字面意思设计出来的，工单没有给出精确公式**。
  工单只写了"报告只出建议清单"和几条测试断言（0、非 0、"finding"三个字），
  没有规定"trace 节的 N 是不是该等于 trace_check 自己那行的 N+M"这类细节。
  我选的口径（各节分别用最贴近该子工具自身语义的方式数，如上文逐节所写）
  能让每条工单测试断言过，但如果之后有别的会话/测试对某节的精确计数有不同
  预期，这是唯一可能对不上的地方。
- **workplan 节的 findings 只算 `inconsistencies[]`，不算
  `pending_user_decisions`/`open_blocked` 等在办清单**。这是我的判断：
  status_view 里明确写着"跨账对不上只列进 inconsistencies[]"，其余字段是正常
  待办，不是"体检异常"。工单原文没有明说这节该不该有 findings 概念，是我
  自己补的口径。
- **`re-run: ledger.py blocked answer <BID> ...` 这类建议行里的 "..." 是字面
  三个点**，跟工单原文的写法一模一样——doctor 不知道当初调用时真实的
  `--answer`/`--chosen`/`--grant` 参数是什么，只能指出该重跑哪条命令族，
  不去猜参数。
- 撤销中断的检测用了跟 `blockedcmd._run_withdraw` 自己完全同一套"先查
  `decision_ref`，查不到再按 `blocked_ref` 反查"的恢复逻辑，是刻意对齐的，
  不是巧合——这样 doctor 报出来的半状态，跟命令自己重跑时能收敛到的状态
  是同一件事。
- 目前没有为 evidence 节多文件场景单独补测试（第 3 节"逐个跑"多文件汇总的
  情况），单文件场景已覆盖（干净沙盒的"无文件"分支 + 别的测试间接跑过带
  内容文件的路径不多）。工单测试列表没点这条，按 YAGNI 没加，如果需要可以
  再补一个"两个 report 文件、一脏一净"的用例。
- caps/archives 两节遍历的是"所有 jsonl 格式账"（含 runs——cap 恒 null 会被
  跳过），不是只遍历工单例句提到的 story/decisions/blocked/feedback 四个；
  我理解这样更贴合"各 jsonl 账"这句字面意思，但如果原意就是那四个固定账，
  这里会多算 runs/runs_legacy（后两者目前不会真的产生行，因为 cap 恒 null）。

## 五、修复轮 1（F1）

分支：`ticket/20260814-wave6/T14`（工作树
`new1-wt/20260814-wave6-T14-fix1`，已删除，分支保留）
base：`0c23d9dfc351801c8028ca958628951e18a462ac`（上一轮 head）
head：`0e0fad8`

### F1（critical）：project 未接线时 exit 2，违反工单"exit 恒 0"

**判定**：finding 成立，按字面读法修。

工单 CLI 段原句"exit 恒 0（体检是建议件）"前后两句（"报告只出 stdout"
"不写 reports/、不写任何账本目录"）都是无条件陈述，紧接着才是"分节...
单节崩溃"那一段单独开的例外——工单只对"单节崩溃"这一种情况明写了例外
处理方式（记 finding 继续跑），没有对"项目没接线，压根定不到 root"这种
情况开第二个例外口子。上一轮实现者把这条按 `trace_check.py` /
`regression_check.py` 的既有惯例抄了"exit 2"，报告第四节里也没把这条
列进自查存疑清单——即工单没开这个口子，也没被主动提请复核。复查
spec.md §4 doctor 注释块、§5、§9、§10（工单点名的四处需求源）逐段过了
一遍，均未提及"project not wired"这个分支该走什么退出码，不构成对字面
读法的反证。

**修法**：`research-loop/scripts/doctor.py` `main()` 里，
`_lib.find_project_root()` 返回 `None` 时，stderr 上的诊断行
（"doctor: project not wired: ..."）保留不动，只把 `return 2` 改成
`return 0`。同步把模块 docstring（原文明写"a project that isn't wired
at all exits 2, the same 'can't even start' convention trace_check.py/
regression_check.py use"）和 `argparse` 的 `description` 里同样的
"exits 0 once it can find a wired project"表述改成无条件的"always exits
0 -- doctor is purely advisory"，避免文档和代码在这条上继续互相印证一个
错误的窄化读法。

新增回归测试 `test_doctor_unwired_project_still_exits_zero`：起一个空
临时目录（确认过 `/`、`/tmp`、`/home`、`/home/y-guo` 均无
`research-loop.json`，向上找不会误命中真实项目）当 cwd，不传
`--project-root` 直接跑 `doctor.py`，断言 exit 0、stderr 含
"project not wired"、stdout 为空。测试文件里原有 5 个编号小节
（1 干净沙盒 / 2 三类半状态 / 3 单项崩溃 / 4 caps / 5 --out）没动，新测试
按文件里的实际顺序接在"5. --out"之后编号为"6"，不打乱既有编号。

### 怎么验证的

```
$ cd new1-wt/20260814-wave6-T14-fix1 && python3 research-loop/tests/run_all.py test_doctor
PASS test_doctor.test_doctor_a_genuinely_crashing_section_is_caught_and_the_rest_still_runs
PASS test_doctor.test_doctor_affects_mismatch_is_reported_and_sandbox_is_untouched
PASS test_doctor.test_doctor_caps_section_flags_ledger_at_or_over_cap
PASS test_doctor.test_doctor_clean_sandbox_all_sections_present_and_zero_findings
PASS test_doctor.test_doctor_interrupted_withdrawal_is_reported_and_sandbox_is_untouched
PASS test_doctor.test_doctor_orphan_decision_is_reported_and_sandbox_is_untouched
PASS test_doctor.test_doctor_out_file_matches_stdout
PASS test_doctor.test_doctor_principles_violation_is_red_but_doctor_completes_and_exits_zero
PASS test_doctor.test_doctor_unwired_project_still_exits_zero
-- run_all: 9 passed, 0 failed
```

全量回归（含新测试，共 268 个，较修复前的 267 个多 1）：

```
$ python3 research-loop/tests/run_all.py
-- run_all: 268 passed, 0 failed
```

`git status --porcelain` 确认改动只落在 `research-loop/scripts/doctor.py`
和 `research-loop/tests/test_doctor.py` 两个文件，没有碰 `run.py` 注册表，
不需要跑 `run.py selfcheck`。

### commit

- `0e0fad8` — T14: exit 0 unconditionally, including unwired project (F1)

### 本轮自查发现与存疑

- 没有额外发现新问题；本轮只处理 F1 一条，改动范围严格限定在
  main() 的这一条分支 + 两处文档字符串 + 一条新测试，没有顺带碰其他九节
  的既有口径（那些口径工单本身没有精确公式，是上一轮的设计判断，不在
  本轮 finding 范围内，没有改动）。
- unwired 场景下 stdout 是否也该打印"doctor: 0 findings across 0/10
  sections"这类汇总行，工单和 finding 都没有要求，是我按"逐条修掉、不许
  扩大范围重构"的指示克制没加——finding 只质疑退出码，没质疑这个分支下
  报告内容的形状，加汇总行会是没被要求的新行为面。
