# T07 report — runs-append + principles-lint + render principles

Branch: `ticket/20260814-wave3/T07`, base `6cce8bc9eef192110ae8343c32ea89d5f2a00302`,
head `b3abeba93371cb7a637e432d4c5a39b46f4bc0f4`.

## 做了什么

对照工单四条要求逐条核对：

1. **原则表解析 `parse_principles(path) -> list[dict]`**（`principlescmd.py`，
   供 T09/T11 import）：找文件里第一个表头含 `principle_id` 单元格的 md 表，
   按 helpers.py 造的八列取列名；按 `|` 切分（转义 `\|` 当字面量 `|`，见下方
   "自查发现" 第一条）、strip；返回行 dict 列表。列数与表头不一致的行跳过
   （不抛异常）。

2. **`runs-append --layer deploy --principle PID`**（`runscmd.py`）：
   - `--layer != deploy` → 拒，消息与工单给定文案逐字相同：
     `runs.layer: runs-append only accepts --layer deploy`。
   - `registry_cmd` 为 null → 拒 `config.registry_cmd: not wired (null);
     cannot run criterion`（工单未给定字面文案，仿 `check_in_registry` 既有
     null-lock 消息风格）。
   - PID 查无 → 拒 `principles.principle_id: not found (got: 'PID')`
     （字面文案工单未给定，走 `_lib.fail()` 标准格式）；`criterion_cmd` 空
     → 拒，消息与工单给定文案逐字相同：
     `principles.criterion_cmd: not wired (【想法待定】); cannot run criterion`。
   - `split_cmd`（禁管道/换行）→ `check_in_registry`（与
     `_lib.check_in_registry` 共用，同发射单一套判定）→
     `_lib.run_argv(argv, cwd=工程根)` 计时。
   - 只有 `exit_code == 0` 且 `_lib.last_json_line(stdout)` 解出的 dict 同时
     含 `value`、`evidence_path` 两键才落行；否则不写任何行，stderr 打印
     "did not produce a valid result" + 该次判据进程 stderr 末 20 行 +
     "escalate per R8" 提示，exit 2。
   - `run_id = chk-<PID>-<YYYYMMDD>-<序>`：序 = 跨档（`include_archive=True`）
     统计既有同前缀 `run_id` 行数 + 1；生成后再查一次是否已存在同 `run_id`
     （判据行重复拒），防御性留痕，正常流程下不可达（见"自查"第三条）。
   - 行字段严格按 `runs.criterion` schema：`status=ok`、`principle_id=PID`、
     `value`/`output_dir` 取自判据尾行 JSON、`commit=_lib.git_head(root)`、
     `elapsed_s`（四舍五入取整）、`recorded_at=_lib.now_iso()`、
     `schema_version=1`；`metric_name`/`arm` 与其余未点名字段一律 null。
   - 锁：`with _lib.locked(runs_path):` 包住"读existing→算run_id→查重→
     validate→append"整段，与 `record.py` 同一把（同文件名 `.lock` 约定）。
     `validate()` 后 `jsonl_append()`；stdout 打整行行 JSON。

3. **`principles-lint [--file PATH]`**（`principlescmd.py`）：逐条检查、
   收集全部违规（不是遇错即停），每条格式
   `principles.<PID>.<列>: <说明>`，任一错 exit 1：
   - `principle_id` 重复（每个重复 PID 一行 `duplicate principle_id (<n> rows)`）。
   - `applies_when` / `rationale` 空。
   - `status` 不在 `enums["principles.status"]`。
   - `criterion_cmd` 含管道/换行（对任意非空 cmd 一律检查，不分状态）。
   - `status ∈ {【现状】,【已定要改】}`：cmd 空 → 拒；cmd 非空 → 过
     `check_in_registry`（`registry_query` null → 报文含 "registry_query not
     wired"，不放行）。
   - `【想法待定】`：cmd 空放行；cmd 非空同样过注册表检查。

4. **`render principles`**（`principlescmd.py`，不收 `--layer`，走
   `ledger.py` 自己的 `render` parser + `_RENDER_TARGET_MODULES["principles"]`
   分派到本模块）：只重写 `last_tested` 一列。每个 PID 取 `runs.jsonl`
   （跨档）里 `principle_id=PID` 且 `recorded_at` 最新的一条判据行 →
   `ok (<value>) <YYYY-MM-DD>`（日期取 `run_id` 的 `<YYYYMMDD>` 段，转成
   `-` 分隔展示）；无行 → `—`。逐行只替换该行最后一个单元格的文本，
   其余字节（含表头、分隔行、其余单元格的原始空白）原样保留。

## 怎么验证的

`python3 research-loop/tests/run_all.py`（全量）：

```
-- run_all: 77 passed, 0 failed
```

其中新增 `test_runs_principles.py` 19 条，单独跑：

```
python3 research-loop/tests/run_all.py test_runs_principles
-- run_all: 19 passed, 0 failed
```

覆盖工单测试清单六条：
1. `test_runs_append_rejects_non_deploy_layer`（`--layer run` → exit 2，
   消息命中，`runs.jsonl` 零行）。
2. `test_runs_append_failed_criterion_appends_no_row_and_exits_2`
   （stub `check-fail` exit 1）+
   `test_runs_append_bad_json_tail_appends_no_row_and_exits_2`
   （stub `check-bad-tail` 尾行非 JSON）——两者均不落行、exit 2。
3. `test_runs_append_success_appends_valid_row_and_increments_sequence`：
   行过 `_lib.validate(row, runs.criterion schema)`；`value == 3`、
   `output_dir == "ops/evidence.txt"`、`run_id ==
   "chk-P001-20260813-1"`（`RL_FAKE_NOW` 钉死日期）；再跑一遍 →
   `run_id == "chk-P001-20260813-2"`。
4. `test_runs_append_commit_field_reports_no_git_outside_a_repo`
   （非 git 沙盒 → `commit == "no-git"`）+
   `test_runs_append_commit_field_reports_dirty_suffix_on_a_dirty_git_tree`
   （git 沙盒、commit 后再写文件致脏 → `commit` 以 `-dirty` 结尾）。
5. principles-lint 六种各一条测试（重复 PID / 空 rationale / 空
   applies_when / 【现状】空 cmd / cmd 不在注册表 / cmd 带管道符）+
   `registry_query` 置 null 一条，外加两条正向用例（合法表 exit 0、
   【想法待定】空 cmd 放行）防止误报。
6. `test_render_principles_backfills_last_tested_and_preserves_other_bytes`：
   跑过判据后 `last_tested` 含子串 `"ok (3) 2026-08-13"`；P001 行只有
   最后一个单元格变化（`rsplit("|", 2)` 前段逐字节相同）；P002 行、表头、
   分隔行逐行字节相同；`test_render_principles_no_runs_row_gives_em_dash`
   补一条无判据行时渲染出 `—`。

`python3 -m py_compile` 三个新文件均通过。未改 `run.py` / `MAP.md`，
按范围声明未跑 `run.py selfcheck`。

## commit 清单

- `4e74a70` — `T07: runs-append (criterion run) + principles-lint + render
  principles`：`principlescmd.py` + `runscmd.py` 两文件。
- `b3abeba` — `T07: add test_runs_principles.py`：测试文件。

## 自查发现与存疑

1. **md 表 `\|` 转义是本工单在需求之外做的设计决定，不是照抄工单**。
   工单原文只说"按 `|` 切分、strip"；但若真按字面纯朴素切分（不认转义），
   `criterion_cmd` 单元格里放一个真实管道符会把该行拆成 9 格而不是 8 格，
   `parse_principles` 会把整行当"列数不对"直接跳过——`principles-lint`
   的"cmd 带管道符"检查测试点因此永远打不到（畸形行悄悄消失而不是报错）。
   我按 CommonMark 表格惯例加了 `\|` 转义识别（分割时不认被反斜杠转义的
   `|`，取出后再把 `\|` 换回字面 `|`），让"cmd 带管道符"这类真实存在但
   有害的值能存活过解析、被 lint 抓到，而不是被静默丢弃一整行。工单测试
   清单里"cmd 带管道符"这一条能测到，正是靠这个决定；若这个决定不合适，
   影响面仅限 `principlescmd.py` 的 `_split_row`/`_CELL_SPLIT_RE`
   两处（`parse_principles` 与 `render` 共用同一份切分函数）。
2. **`config.registry_cmd` 为 null 时的拒绝文案是我设计的**，工单只给了
   语义（"锁判据实跑"）没给字面文案；我仿照 `_lib.check_in_registry` 里
   `registry_query`/`registry_cmd` 两处既有 null-lock 消息的风格写成
   `config.registry_cmd: not wired (null); cannot run criterion`。同样，
   "PID 查无" 的拒绝文案（`principles.principle_id: not found (got: ...)`）
   与"同 run_id 已存在"的拒绝文案（`runs.run_id: criterion run already
   recorded (got: ...)`）工单都只给了语义没给字面文案，我按 `_lib.fail()`
   全仓统一格式写的。
3. **"同 run_id 已存在 → 拒"这条防御检查在当前代码路径下是死代码**：
   `run_id` 的序号来自"锁内读现有行数 + 1"，同一把锁下不存在外部并发写者
   能在这两步之间插进一行同名记录，所以这条 `any(row.get("run_id") ==
   run_id ...)` 检查目前测不到（也没写专门测试去测它）。工单原文明确
   要求这条检查，我按要求实现了，但没有为它单独找一个能触发的场景写测试
   ——正常流程下确实触发不了，只有手工在锁外造出一条同名行才能测到，
   我认为不值得为此专门污染测试夹具，留在这里请复核确认这个判断。
4. `runs-append` 失败时打到 stderr 的 "escalate per R8" 提示文案是我写的
   （工单只写了"提示 escalate per R8"这个要求，没给字面文案）；测试只断言
   了子串（进程自身 stderr 内容如 "boom"、不落行、exit 2），没有锁死这句
   提示的完整措辞，后续想改这句话不会破坏现有测试。

## 修复第 1 轮（2026-08-14）

工作树 `/home/y-guo/reproduce/new1-wt/20260814-wave3-T07-fix1`，分支
`ticket/20260814-wave3/T07`，base `b3abeba93371cb7a637e432d4c5a39b46f4bc0f4`
（上一轮 head），修复 commit `462f429`。逐条对照未决 findings：

### F1（critical）：ledger 文件缺失时三个入口裸抛 FileNotFoundError

**改法**：`parse_principles(path)`（`principlescmd.py`）和 `_render(args)`
（同文件）原先都直接 `Path(path).read_text(...)`，不检查文件是否存在。
现在两处都先做 `if not path.exists(): _lib.fail("principles", "file", "not
found", str(path))` 再读——`_lib.fail()` 抛 `RLError`，`ledger.py`
`main()` 统一捕获、打印到 stderr、`exit 2`（`ledger.py:231-233`），与仓库
既有的 `<ledger>.<field>: <msg>` 格式（例如 `runscmd.py` 里
`principles.principle_id: not found (got: 'P999')` 那条）保持一致；参照
了 `_lib.py` 里 `inplace_update()`（215-216 行）、`load_schema()`
（283-284 行）已有的"先 `exists()` 检查再读"写法。三个入口
（`principles-lint`、`runs-append`、`render principles`）都经由
`parse_principles`/`_render` 读文件，一次改动全覆盖。

`fail()` 的三个参数选的是 `("principles", "file", "not found")`，拼出
`principles.file: not found (got: '<path>')`——`"file"` 这个字段名是我
按仓库既有命名习惯（`ledger.<field>`）新起的，工单和 spec 都没有给这个
场景的字面文案，其余两个既有拒绝分支（PID 查无、registry_cmd 为 null）
工单也同样只给语义没给字面文案，属同一类"文案自定"决定。

**手工复现验证**（在修复前的代码上，重放 finding 给的三条命令，确认
问题真实存在，然后在修复后的代码上重跑确认已消失）：

```
$ python3 - <<'PY'   # sandbox 里删掉 METHOD.md 后跑三条命令
...
['principles-lint'] -> exit 2
stderr: principles.file: not found (got: '/tmp/t07f1/METHOD.md')
---
['runs-append', '--layer', 'deploy', '--principle', 'P001'] -> exit 2
stderr: principles.file: not found (got: '/tmp/t07f1/METHOD.md')
---
['render', 'principles'] -> exit 2
stderr: principles.file: not found (got: '/tmp/t07f1/METHOD.md')
---
PY
```

三条均是规整的 `exit 2` + `<ledger>.<field>: <msg>` 格式，不再是裸
Python 堆栈。

**新增测试**（`test_runs_principles.py`）：
- `test_parse_principles_rejects_a_missing_file`：直接单测
  `parse_principles()`，用 `try/except _lib.RLError` 断言完整消息文本
  （与 `test_lib.py` 里 `test_inplace_update_rejects_missing_row` 同一
  种写法）。
- `test_principles_lint_rejects_missing_principles_file` /
  `test_runs_append_rejects_missing_principles_file` /
  `test_render_principles_rejects_missing_principles_file`：三个 CLI
  级测试，各自在 sandbox 里 `unlink()` 掉 `METHOD.md` 后跑对应子命令，
  断言 `exit 2` 且 stderr 含 `principles.file: not found`；
  `runs-append` 那条额外断言 `runs.jsonl` 零行。

### F2（important）：runs-append 两条拒绝分支零测试覆盖

**改法**：不改生产代码（两条分支行为本身是对的，finding 也这么说），
只在 `test_runs_principles.py` 补两条测试：
- `test_runs_append_rejects_when_registry_cmd_is_null`：sandbox 建好后
  把 `research-loop.json` 的 `registry_cmd` 改写成 `null`，跑
  `runs-append`，断言 `exit 2`、stderr 含
  `config.registry_cmd: not wired (null); cannot run criterion`、
  `runs.jsonl` 零行。
- `test_runs_append_rejects_unknown_principle_id`：METHOD.md 只有
  `P001`，`--principle P999` 跑 `runs-append`，断言 `exit 2`、stderr 含
  `principles.principle_id: not found (got: 'P999')`、`runs.jsonl`
  零行。

两条断言的文案都是 finding 里手工实测记录下来的原话，直接锁死。

### 怎么验证的

```
$ python3 research-loop/tests/run_all.py test_runs_principles
...
-- run_all: 25 passed, 0 failed
```

（19 条原有 + 6 条新增：F1 四条 + F2 两条，全绿。）

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 83 passed, 0 failed
```

（全量：77 条原有 + 6 条新增，0 失败，0 条被改动或删除。）

```
$ python3 -m py_compile research-loop/scripts/ledger_cmds/principlescmd.py \
    research-loop/scripts/ledger_cmds/runscmd.py \
    research-loop/tests/test_runs_principles.py
```
（三文件均通过，无输出即成功。）

`git diff --stat`：只有 `principlescmd.py`（+10/-2）和
`test_runs_principles.py`（+82，无删改）两个文件改动，未碰 `runscmd.py`
生产代码（F2 只补测试，不改行为）、未碰 `run.py`/`MAP.md`（本工单范围
声明外）。

### commit 清单（本轮）

- `462f429` — `T07: fix 1 — reject missing principles file cleanly (F1),
  cover null registry_cmd / unknown PID rejections (F2)`：
  `principlescmd.py` + `test_runs_principles.py` 两文件。

### 自查发现与存疑（本轮）

- F1 的字段名 `"file"`（拼出 `principles.file: not found`）是我按
  `<ledger>.<field>` 命名习惯新起的，工单和 spec 都未给这个失败场景的
  字面文案；若后续工单（T09/T11，同样 import `parse_principles`）或
  spec 表 `principles_columns` 已经/将要定义一个更规范的字段名，改这一
  处即可，不影响调用方（三个入口都只依赖"抛 RLError、exit 2"这个契约，
  没有任何调用方对文案子串做匹配)。
- 未触碰上一轮报告"自查发现"第 3 条提到的"同 run_id 已存在"死代码路径
  ——不在本轮两条 finding 范围内，按"不许扩大范围重构"未动。
