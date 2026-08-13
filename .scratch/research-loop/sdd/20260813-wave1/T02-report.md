# T02 报告 —— 共用库 `_lib.py` + 测试基建

工单：`.scratch/research-loop/issues/02-lib.md`
分支：`ticket/20260813-wave1/T02`
工作树：`/home/y-guo/reproduce/new1-wt/20260813-wave1-T02`（收尾已 `git worktree remove`，分支保留）

## 一、做了什么（对照工单逐条）

### 接口（plan.md §C1 全部函数与类）

在 `research-loop/scripts/_lib.py` 里逐个实现，签名与 plan.md §C1 一字不差：

- `plugin_root()` / `load_tables()` / `find_project_root(start=None)`。
- `Config` + `load_config(root)`：`.data` 是原样读到的 `research-loop.json`
  （文件不存在时 `{}`）；`.get(key)` 缺省或显式 null 都退到插件默认
  （`runtime_factor=3`、`roles`、`standing_authorization`、
  `inspection_policy="always"`，其余键无默认即 `None`——这四个默认值是按
  plan.md §C1 注释里给的字面量写死的，`tables/config.json` 本身只有文档字段
  没有机读默认值，无法从表里派生）；`.null_locked(key)` 只看原始 data 是否
  缺失/null，不套默认；`.ledger_path(name)` 用 config 的 `ledgers` 覆盖
  `tables/ledgers.json`（含 `optional_ledgers`）的 `default_path`，相对
  `root` 解析，含 `<artifact_dir>`/`<raw_data_roots>` 模板的路径原样返回
  字符串。
- `RLError`（`.message` 即成品文案）+ `fail(ledger, field_path, msg,
  value=_MISSING)`：只有显式传了 `value`（含 `None`）才加 `(got: ...)`
  后缀。
- `locked(path)`：`str(path)+".lock"`，父目录自动建，`fcntl.flock` EX，
  contextmanager，释放后关 fd。
- `jsonl_rows(path, include_archive=False)`：文件缺 `[]`；跳过空行；
  `include_archive=True` 先读 `<name>.archive<ext>`（存在才读）再读主文件。
- `jsonl_append(path, row)`：一行一个 `json.dumps(ensure_ascii=False)`。
- `inplace_update(path, key_field, key_value, updates, whitelist)`：越白名单
  逐字段 `fail(path.stem, field, "field is not in-place updatable")`；行找
  不到 `fail(path.stem, key_field, "row not found", key_value)`；实现按原始
  行文本逐行比对，只重写命中的那一行，其余行原样保留字节，写临时文件 +
  `os.replace` 原子替换。
- `alloc_id(rows, id_field, prefix)`：同前缀最大数字 +1，3 位零填充，超
  999 自然变宽。
- `now_iso()` / `today()`：`RL_FAKE_NOW`（ISO 秒级字符串）存在则直接返回
  它（`today()` 取前 10 位）。
- `load_schema(name)` / `validate(row, schema, ledger)`：`validate()` 按
  §C3 逐条实现——required 齐全、`additionalProperties=false` 拒生字段、
  type 联合（bool 显式排除出 integer 与 number）、enum、const、integer
  minimum、array 逐元素查 items（递归复用同一条类型检查路径）；
  `conditional`：`when` 支持单对象或对象数组（数组=全部成立，字段缺按
  `None` 比，op 只认 `eq|neq|in`）；`require` 条件成立时字段必须存在且非
  null；`allow_null` 语义按工单原文实现——只有被某个 `allow_null` 条目列名
  的字段，才需要"至少一条列它的 conditional 成立"才能为 null，未被列名的
  字段可空性纯看 `type` 是否含 `"null"`。单入口、遇第一处违规立即
  `fail()`（不是收集全部错误再报）。
- `run_argv(argv, cwd=None, timeout=None)`：`subprocess.run` 不经 shell，
  返回 `(exit_code, stdout, stderr, elapsed_s)`；超时时 `exit_code=None`，
  `elapsed_s` 是实际耗时。
- `split_cmd(cmd, ledger, field)`：含 `|` 或换行直接 `fail()`，否则
  `shlex.split`。
- `last_json_line(stdout)`：只看最后一个非空行，非 JSON 或非 dict 都返回
  `None`（不往前继续找）。
- `registry_tasks(cfg)`：`registry_query` 为 null 返回 `None`；否则
  `split_cmd` + `run_argv`，逐行去空白收集任务名。
- `check_in_registry(argv, cfg, *, ledger, field)`：`registry_cmd` 为 null
  `fail(..., "registry_cmd not wired (null); cannot verify task")`；
  `shlex.split(registry_cmd)` 必须是 `argv` 前缀，否则 `fail()`；
  `argv` 里前缀之后必须还有 token（否则 `fail()`）；该 token 即任务名；
  `registry_tasks(cfg)` 为 `None`（即 `registry_query` 是 null）
  `fail(..., "registry_query not wired (null); cannot verify task")`；
  任务不在清单里 `fail()`；全过返回任务名。
- `parse_frontmatter(text)`：首行必须是 `---`，到下一条 `---` 行为止是头
  部，每行 `key: value`，value 先 `json.loads`，失败按原样字符串；返回
  `(fields, body)`，body 是第二条 `---` 行之后的原文（逐字符重建，含原始
  换行）。
- `spec_digest(path)`：对文件原始字节按行边界（`\r\n`/`\n`/`\r`）找出所有
  等于 `---` 的整行，取第二条之后的原始字节做 `sha256`。专门验证过
  `bytes.splitlines()` 不会把 UTF-8 续字节 `0x85`（中文等多字节字符可能包含
  该字节）误判成换行——`bytes.splitlines()` 只认 ASCII 行边界，不像
  `str.splitlines()` 那样认 NEL/LS/PS，见下文"自查发现"。
- `git_head(root)`：`git rev-parse HEAD`；`git status --porcelain` 非空加
  `-dirty`；非 git 仓库（`rev-parse` 非零退出）返回 `"no-git"`。

### `tests/helpers.py`

- `make_stub_registry(root, tasks)`：在 `root/stub_registry.py` 生成一个
  纯 stdlib 的 stub：`--list` 一行一个任务名；`<task> [args...]` 转发到
  `tasks[task] + args` 并透传退出码。`tasks` 通过
  `json.loads({tasks_json!r})` 的方式内嵌进生成脚本源码（避免 Python/JSON
  字面量语法差异带来的转义问题）。
- `make_sandbox(tmp)`：写好接线的 `research-loop.json`——`ledgers` 全键取
  `tables/ledgers.json` 的 `default_path`；`owners` 优先读插件的
  `schemas/owners.default.json`（T03 尚未生成，目前恒走 fallback：按
  `ledgers.json` 的 `owner` 列逐键拼）；`registry_cmd`/`registry_query`/
  `record_cmd` 都指向新建的 stub registry（分别是本体、`--list`、
  `record` 三个 task）；`runtime_factor=3`；
  `raw_data_roots=[str(root/"net")]`；`tables/config.json` 里没被上述六项
  覆盖的其余全部键（按该表 `keys` 动态枚举，不在代码里另抄一份清单）
  显式置 `null`。建好 `ops/`、`ops/launch_orders/`、`plans/`、`reports/`、
  `.scratch/` 五个目录，写 `METHOD.md`（工单给的示例表原样落盘，含
  `check-p001` 那一行）。返回工程根。
- `make_git_sandbox(tmp)`：`make_sandbox` 之后 `git init` + 配置身份 +
  `git add -A` + 一次性 commit 全部文件。
- `run_ledger(root, *args, env=None)` / `run_script(root, script_name,
  *args, env=None)`：subprocess 跑 `scripts/ledger.py` 或
  `scripts/<script_name>`，cwd=root，透传 `(exit_code, stdout, stderr)`。
- `write_jsonl(path, rows)`：裸写，不持锁（fixture 用）。
- 八个行工厂：`make_blocked_row` / `make_decision_row` / `make_grant_row`
  / `make_story_row` / `make_runs_row_normal` / `make_runs_row_criterion`
  / `make_launch_order` / `make_suggestion_row`，都是"合理默认字段 +
  `**over` 覆盖"的模式。每个工厂产出的字段都手动对照过
  `tables/rows.json` 对应块的 `required`/`conditional` 逐条核对（见下文
  "怎么验证的"里的沙盒验证）。

## 二、怎么验证的

### `python3 research-loop/tests/run_all.py test_lib`

```
PASS test_lib.test_alloc_id_empty_table_gives_first_id
PASS test_lib.test_alloc_id_increments_from_existing_max
PASS test_lib.test_alloc_id_widens_past_999
PASS test_lib.test_check_in_registry
PASS test_lib.test_config_get_falls_back_to_plugin_defaults
PASS test_lib.test_fail_message_format_matches_spec
PASS test_lib.test_fail_without_value_omits_got_suffix
PASS test_lib.test_find_project_root_walks_up_and_returns_none_when_unwired
PASS test_lib.test_git_head_reports_no_git_and_dirty_suffix
PASS test_lib.test_inplace_update_is_atomic_and_leaves_other_rows_byte_identical
PASS test_lib.test_inplace_update_rejects_missing_row
PASS test_lib.test_inplace_update_rejects_non_whitelisted_field_with_exact_message
PASS test_lib.test_last_json_line_variants
PASS test_lib.test_locked_blocks_another_process_and_releases_on_exit
PASS test_lib.test_make_sandbox_wires_jsonl_rows_and_ledger_path
PASS test_lib.test_now_iso_reads_rl_fake_now
PASS test_lib.test_parse_frontmatter_splits_header_and_body
PASS test_lib.test_plugin_root_and_load_tables
PASS test_lib.test_spec_digest_stable_across_header_edits_changes_with_body
PASS test_lib.test_split_cmd_rejects_pipes_and_newlines
PASS test_lib.test_today_reads_date_part_of_rl_fake_now
PASS test_lib.test_validate_additional_properties_rejects_unknown_field
PASS test_lib.test_validate_allow_null_gated_by_condition
PASS test_lib.test_validate_array_items_checked_per_element
PASS test_lib.test_validate_bool_is_not_treated_as_integer
PASS test_lib.test_validate_conditional_require_single_when
PASS test_lib.test_validate_conditional_require_when_is_array_of_two_conditions
PASS test_lib.test_validate_const
PASS test_lib.test_validate_enum
PASS test_lib.test_validate_minimum
PASS test_lib.test_validate_required_field_missing
PASS test_lib.test_validate_type_union_accepts_any_member_and_rejects_others
-- run_all: 32 passed, 0 failed
```

`python3 research-loop/tests/run_all.py`（全量跑一遍，此刻仓库里只有
`test_lib.py` 一个测试文件）结果同上，32 passed 0 failed。

工单点名的 10 条测试与我写的函数对应关系：1→3 个 `test_alloc_id_*`；
2→3 个 `test_inplace_update_*`；3→11 个 `test_validate_*`（required / 生
字段 / type 联合 / bool 不算 integer / enum / const / minimum / items /
conditional require 单条件 / conditional require 双条件数组 /
allow_null，一条独立函数一个）；4→2 个 `test_fail_*`（原文给的用例 +
补一个不传 value 的对照）；5→`test_split_cmd_rejects_pipes_and_newlines`
+ `test_last_json_line_variants`；6→`test_parse_frontmatter_*` +
`test_spec_digest_*`；7→`test_check_in_registry`（内含前缀不符/任务不在
清单/registry_query 缺文案含"not wired"/合法通过返回任务名四个子断言，
外加工单接口段里额外描述的 registry_cmd 为 null 情形一并核对）；
8→`test_locked_blocks_another_process_and_releases_on_exit`；
9→`test_now_iso_*` + `test_today_*`；
10→`test_make_sandbox_wires_jsonl_rows_and_ledger_path`。

额外补的边界测试（工单"测试"节没单独点名，但都是 §C1 接口表里的公开函数，
供后续全部工单消费，出问题会全线牵连，所以按"改动边界补测试"补上）：
`test_config_get_falls_back_to_plugin_defaults`（验证四个插件默认值字面
量）、`test_plugin_root_and_load_tables`、
`test_find_project_root_walks_up_and_returns_none_when_unwired`、
`test_git_head_reports_no_git_and_dirty_suffix`。`load_schema()` 没写
测试——它读插件自己的 `schemas/`，T03 之前该目录不存在，要测就得在共享的
插件目录里现造 fixture 文件，波内其他工单同时在跑，怕互相踩，留给 T03
自己在生成物就位后测。

### 非提交的沙盒验证（八个行工厂过真实 schema）

`tests/test_lib.py` 里的 `validate()` 测试用的是工单要求的"手写迷你
schema，不依赖 T03 生成物"。为确认 `helpers.py` 八个行工厂产出的字段
真的能通过 `rows.json` 对应块的完整约束（不只是"不报错"，是真的对齐
`required`/`conditional`），额外写了一段一次性脚本（未落盘进仓库）：
现场用 `rows.json` 的 `enums` 表把 `$enum` 就地展开成 `enum` 数组（gen-
schemas 那步变换的最小子集），拼出跟生成物同形的 schema，喂给
`_lib.validate()`：

```
OK   story
OK   decisions   (decision 与 grant 两种 kind 各测一次)
OK   blocked
OK   feedback.suggestion
OK   runs.normal
OK   runs.criterion
OK   launch_order
```

八个工厂全部一次通过，没有改代码。

## 三、commit 清单

- `d7b3fee` — `T02: research-loop plugin — _lib.py 共用库 + 测试基建`
  （`research-loop/scripts/_lib.py`、`research-loop/tests/helpers.py`、
  `research-loop/tests/test_lib.py` 三个新文件，一次性提交，逻辑上是一个
  不可拆分的整体：库函数与消费它们的测试/工厂互相印证，拆开中间态过不了
  自己的测试）。

## 四、自查发现与存疑

1. **`Config` 的四个默认值是写死的字面量，不是从表里读出来的。**
   `tables/config.json` 只有 `example`/`domain`/`null_effect` 这些文档字段，
   没有机读的 default 值；真正的默认值只在 plan.md §C1 的代码注释里以字面
   量形式给出（`runtime_factor=3` 等）。按工单原文"缺省值取
   research-loop/tables/config.json 里的 plugin 默认"，我把这四个值直接
   写进 `_lib.py` 的 `_CONFIG_DEFAULTS` 字典。这跟"表是唯一真源"的总纪律
   （规则 4）有一点张力——如果以后要改这四个默认值，得改代码而不是改表。
   但没有别的地方能读到这些默认值，只能这样做；记在这里留痕。
2. **`spec_digest` 的分隔符检测只要求"文件里存在两条 `---` 行"，不强制
   第一条必须是文件首行。** `parse_frontmatter` 严格要求首行是 `---`；
   `spec_digest` 的契约原文只说"对第二条 `---` 行之后的原始字节做
   sha256"，没有重复"必须是文件头"的约束，两个函数职责不同（一个做格式
   校验+解析，一个只管摘要），我按各自字面契约实现，没有互相拉齐。真正
   的"文件头必须是 `---` 定界"这条校验，工单没有点名给 `_lib.py`，应该
   落在消费 spec 头部的那个环节（T13 一类，读 `spec_header._header_rule`
   的地方）去做。
3. **`registry_cmd`/`registry_query`/`record_cmd` 在 `make_sandbox` 里都
   用绝对路径拼命令行**（`{sys.executable} {root/'stub_registry.py'}`），
   没有依赖"以 root 为 cwd"这个假设。工单原文的例子（`python3 run.py`）
   是相对写法，真实工程里靠"这些命令总是从项目根跑"这个约定成立；但
   `_lib.registry_tasks()` 内部 `run_argv()` 不传 `cwd`，用绝对路径能让
   沙盒里的调用不依赖调用方有没有 `cwd=root`，更适合当测试基建。这是我
   做的一个选择，后续工单如果需要测试"registry_cmd 是相对路径、必须
   cwd=root 才能跑通"这类场景，得自己另外搭 fixture，`make_sandbox` 目前
   不覆盖这条。
4. **`record_cmd` 指向的 `record` stub task 只是 `python3 -c "pass"`
   占位**，不做任何真实记账语义。工单原文"record_cmd 同"只要求它也指向
   一个 `make_stub_registry` 产物，没有规定它要做什么；真实的 record 行为
   由后续消费 `record_cmd` 的工单（写 `runs.jsonl` 普通行那条链路）决定，
   如果它们需要不同的桩行为，得自己调用 `make_stub_registry` 重新登记
   `record` 任务或者在自己的测试里另起一个 registry。
5. `load_schema()` 已按签名实现（读 `plugin_root()/schemas/<name>.schema.json`，
   缺文件抛 `RLError`），但没配测试——理由见上文"怎么验证的"最后一段。
