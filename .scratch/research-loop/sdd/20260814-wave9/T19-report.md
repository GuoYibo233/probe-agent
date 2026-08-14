# T19 报告：§V 第二轮修复（jobs 合并 / evidence_lint 误火 / render 状态列 / routes 拆列 / 表注）

工单：`.scratch/research-loop/issues/19-vloop2-code.md`
分支：`ticket/20260814-wave9/T19`（工作树 `/home/y-guo/reproduce/new1-wt/20260814-wave9-T19`，已删除，分支保留）
base: `5926300cd507d73afb0f69ecb5ede4e11ab36eb9`
head: `7fa9d1caa02c72d6dcdc3b1e05e4f5c1e79dd8fc`

## 一、做了什么（对照工单逐条）

### A. launch.py 首次登记 merge（#161；verdict v2-hop4-2）

`research-loop/scripts/fallback/launch.py` 里发射时的 jobs 登记（原
159-168 一带的整体赋值）改成与收尾更新（219-225）相同的 merge 形态：
`entry = jobs.get(order["run_id"], {})` 起步，只更新发射器自有五键
（launch_order_ref/state/started_at/finished_at/log_path），逐键赋值后
`jobs[order["run_id"]] = entry` 写回。外来键（escalation_ref/
sampler_verdict/sampler_verdict_at 等）不在这五键范围内，原样保留。
同时把模块顶部 docstring 第 3 步的说明补了一句，指明两处写都走 merge。

### B. evidence_lint 四类机械误火豁免（#159；verdict v1-oversight-3、
v2-hop6-4/5/6）

`research-loop/scripts/evidence_lint.py` 规则 2（no-repro-command）新增
四条豁免，规则 1（banned-word）未动：

1. `> ` 开头的摘录行（`_is_quote_line`）：整行跳过 rule2 的扫描，不进
   `_strip_exempt`/`_asserts_number` 判断。
2. 新增 `_HEADING_NUM_RE = re.compile(r"^\s*#{0,6}\s*\d+[.)]\s*")`，放进
   `_STRIP_PATTERNS` 首位：只剥行首的 `## 2.`/`3.` 一类标题或列表编号，
   不动行中数字。
3. 新增 `_SECTION_REF_RE = re.compile(r"§\d+")`：剥除 `§N`（含括号形
   `(§1)` 里的 `§1`，剩下空括号 `()`，无数字）。
4. 新增 `_ALNUM_TOKEN_RE = re.compile(r"\b[A-Za-z_]+\d+\b")`：剥除字母
   紧连数字的单 token（python3/sha256/attempt1/utf8）。因为要求字母数字
   之间无空格，"attempt 1" 这类带空格的序数词天然不命中，保持触发。
5. 保护集构建逻辑改成沿 `$ ` 行往下追反斜杠续行（`while lines[j]...
   endswith("\\")`），续行结束后再检查其后是否紧跟 `= ` 回显行——修前只
   保护 `$ ` 行本身与紧邻的一行 `= ` 行。

模块 docstring 规则 2 段落同步重写，把五条豁免和"序数词刻意不豁免"的
理由写进去。

### C. render blocked 状态列与分组（#160；verdict v1-router-1）

`research-loop/scripts/ledger_cmds/querycmd.py::_run_render_blocked`：
- 分组键改为 `row.get("from_layer") if row.get("status") == "answered"
  else row.get("to_layer")`——answered 行按 from_layer（欠 close 的一方）
  分组，open 行仍按 to_layer（欠答复的一方）分组。
- 分组遍历的层序表从单一的 `blocked.to_layer` 枚举改成
  `blocked.to_layer` 枚举 + `blocked.from_layer` 枚举里 to_layer 没有
  的层（run/oversight）拼接而成——因为 answered 行现在可能落到
  from_layer 独有的那两层，只用旧的 to_layer 顺序表会漏打印。
- 表头加一列 `status`，每行末尾追加该行的 status 值。

### D. routes.json 命令拆列（#160；verdict v1-router-2）

`research-loop/tables/routes.json` 的 8 条 `kind=command` 行新增 `cmd`
字段，只装可粘贴执行的命令尾巴：

| say | cmd |
|---|---|
| 有什么在等我 | `ledger.py render blocked` |
| 这类事你自己定（授权） | `ledger.py grant --layer <本层> --question <事项> --reason <理由> --scope-desc <用途> --scope-globs <path_glob...>` |
| 我收回那条决定 | `null`（`_note`: 多步程序，见 to 列指向的规则） |
| 这个不行，重做（打回） | `null`（`_note`: 多步程序，见 to 列指向的规则） |
| 审一下反馈 | `ledger.py feedback review --layer user --ref <fb_id> --verdict accepted|rejected` |
| 体检一下 / doctor | `doctor.py` |
| 接一下这个工程 / init | `ledger.py init` |
| 我们跑到哪了 / 接着干 | `ledger.py status --layer <本层>` |

`to` 列原文全部保留不动。grant/feedback review/status 三行的 cmd 里带
`<占位符>`（尖括号记法沿用 `to` 列既有约定），因为这几条命令的真实取值
（--layer/--question/--scope-globs 等）由调用当场决定，没有固定字面量。
grant 的 `--scope-desc`/`--scope-globs` 落进 cmd：读了
`scripts/ledger_cmds/decisionscmd.py::_run_grant`，缺这两个会被
`_lib.fail("decisions", "scope", "grant requires structured scope")`
拒掉，所以这条 cmd 不能只写 `ledger.py grant --layer ...` 就收尾。
撤销、打回两行经工单点名"没有单条命令"，cmd 置 null 加 `_note`。

另在 `_kind` 旁新增 `_cmd` 表头文档字段，说明 cmd 列的读法和它与 `to`
列的分工（router SKILL.md 那份文字工单点名归 T20，未动）。

### E. 表注六处（工单标题写"五处"，正文列了 6 条，我按正文六条条目
逐条实现，未改动工单文字本身）

`research-loop/tables/rows.json`：

1. `runs_row_normal._dup_rule` 补 #158 两段式重试纪律原文。
2. `launch_order.properties.resources._note` 补空值形态是 `{}`（字段
   required、不可 null——v2-hop1-1）。
3. `jobs_min_additions._required_additions.escalation_ref` 补"多次升级
   只存最新一条，历史查 blocked 账本身"（#161 尾句；v2-hop4-3）。
4. `status_view.pending_launch_orders` 补半句"获准重试的新单自然落入
   本字段（#158）"。
5. `status_view.batches_pending_report` 补"失败/空产物 run 的批次同样
   欠报告——报告解释失败也是报告（v2-hop3-4）"。
6. `decisions_row.scope._note` 补授权覆盖判定原文（v1-idea-1）：fork
   触及的文件/产物全部落在 `path_globs` 内，且 `desc` 用途白话涵盖该
   fork 主题，两条同时成立才算覆盖，拿不准即不覆盖走开条。

六处全是 `_` 前缀文档字段（或不进 `gen-schemas` 的表块，如
`jobs_min_additions`/`status_view`），对生成的 schema 文件没有影响——
`gen-schemas --check` 验证过。

## 二、怎么验证的

### 2.1 单元测试（新增/改动测试的"修前红修后绿"）

先把五处代码/表改动（launch.py/evidence_lint.py/querycmd.py/
routes.json/rows.json）整体 `git stash`，只留新增和改动的测试，跑一遍
确认三个受影响的测试模块各自红：

```
$ python3 tests/run_all.py test_fallback
```
```
-- run_all: 15 passed, 1 failed
FAIL test_fallback.test_launch_relaunch_merges_jobs_entry_keeping_run_layer_backrefs
```

```
$ python3 tests/run_all.py test_oversight
```
```
-- run_all: 31 passed, 5 failed
```
（5 个新增的 evidence_lint 豁免测试全红，非回归两条本就通过。）

```
$ python3 tests/run_all.py test_query_status
```
```
-- run_all: 17 passed, 1 failed
FAIL test_query_status.test_render_blocked_groups_open_by_to_layer_answered_by_from_layer
```

`git stash pop` 恢复代码/表改动后，三个模块全绿，随后跑全量：

```
$ python3 tests/run_all.py
```
```
-- run_all: 319 passed, 0 failed
```

### 2.2 gen-schemas --check + spec_lint 双绿（工单 D 段要求）

```
$ python3 scripts/ledger.py gen-schemas --check
```
（在 `research-loop/` 目录下运行，exit 0，无输出。）

```
$ python3 .scratch/research-loop/spec_lint.py
```
```
-- spec_lint: 0 errors, 0 warnings
```
（在 `/home/y-guo/reproduce/new1-wt/20260814-wave9-T19` 根目录下运行。）

### 2.3 测试清单对照工单"测试"节

1. A：`test_launch_relaunch_merges_jobs_entry_keeping_run_layer_backrefs`
   ——预置 escalation_ref/sampler_verdict/sampler_verdict_at 后同 run_id
   重发，断言三键仍在、state 变 done、log_path 变 attempt2.log。
2. B：五个新测试对应工单点名的五个形状（`## 2.` 标题、`(§1)`、
   `> ` 带数字摘录行、`python3`、`$ ` 反斜杠续行）各自过 lint（code==0）；
   两个非回归测试（`row count: 5` 仍命中、"attempt 1"/"attempt 2" 仍
   命中）。
3. C：`test_render_blocked_groups_open_by_to_layer_answered_by_from_layer`
   ——open 行（from_layer=run, to_layer=deploy）落在 `## deploy` 段且行
   末 `| open |`；answered 行（from_layer=idea, to_layer=deploy）落在
   `## idea` 段且行末 `| answered |`；closed 行不出现；表头带 status 列。
4. D/E：spec_lint + gen-schemas --check 双绿，见 2.2。

## 三、commit 清单

| sha | 说明 |
|---|---|
| `4070e56` | T19: launch.py jobs 首次登记改 merge，不再整体覆盖外来键（#161） |
| `ba76e7e` | T19: evidence_lint 收四类机械误火，门不松（#159） |
| `3882b69` | T19: render blocked 补 status 列，answered 行改按 from_layer 分组（#160） |
| `386158e` | T19: routes.json 命令拆列，kind=command 行新增 cmd 字段（#160） |
| `7fa9d1c` | T19: rows.json 补五处表注（#158/v2-hop1-1/#161/v2-hop3-4/v1-idea-1） |

## 四、自查发现与存疑

- `7fa9d1c` 的 commit 标题写"补五处表注"，但正文列的是六条（工单第 E
  节标题本身写"表注五处"却列了 6 个编号条目——工单原文的计数与内容对
  不上，我按正文六条逐条实现，commit 标题沿用了工单标题的"五处"没有
  改口径，属于我自己留下的一处标题/正文不一致，不影响内容正确性，如
  需要可另发一条 commit 改标题措辞。
- routes.json 的 grant/feedback review/status 三行 cmd 字段包含
  `<占位符>` 而非纯字面量可粘贴命令，因为这几条命令的实际参数
  （--layer 取哪个层、--scope-globs 填什么 glob）在工单三个例子
  （render blocked / doctor.py / status --layer <本层>）里唯一带占位符
  的就是 status 那条，我把这个记法平移到了 grant 和 feedback review 上
  ——读 `decisionscmd.py`/`feedbackcmd.py` 的 argparse 定义确认了这几个
  参数是必填的（grant 的 `--scope-desc`/`--scope-globs` 缺一即被
  `_run_grant` 拒绝；feedback review 的 `--ref`/`--verdict` 都是
  required=True），所以带占位符是唯一诚实的写法，但工单本身没有给出
  这两行 cmd 的期望文本，这是我在需求空白处做的选择，不是照抄工单
  数值。
- routes.json `_kind` 旁新增的 `_cmd` 表头文档字段不在工单"文件"清单
  的逐条要求文字里明确点名（工单只说"kind=command 的行新增 cmd 字段"，
  没说要不要配一段表头说明），我按 `_kind` 已有的先例加了一段，判断
  是保持表自描述的一致性，不是本轮验收要求的必需项——如果这算超出范围
  可以直接删掉这一个 key，不影响其余改动。
- 工单第 D 段"撤销/打回两行（12/13）没有单条命令"里的行号 12/13 与
  routes.json 实际数组下标或文件行号都对不上（我数过：不管按 0-based
  还是 1-based、全量行还是仅 command 行计数，都对不上 12/13）；我没有
  按数字定位，而是按语义（"我收回那条决定"=撤销、"这个不行，重做（打回）"
  =打回）直接锁定这两行，工单原文的"（12/13）"括注可能是笔误或指代
  另一版本文件，我没有改工单文字，只是没有采用这个数字定位。
