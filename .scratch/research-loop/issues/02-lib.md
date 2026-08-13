# T02 共用库 `_lib.py` + 测试基建

Status: resolved
Blocked by: 01

## 范围声明

本工单属 research-loop plugin（机器级通用件，非 new1 工程任务）：
**不改 run.py、不改 MAP.md**。代码、注释、报错信息一律英文；纯 Python 3.10
标准库，禁第三方依赖。需求源：本工单 + `.scratch/research-loop/plan.md`
§C1/§C3（签名与语义照抄）+ 点名的表文件。

## 文件

- Create: `research-loop/scripts/_lib.py`
- Create: `research-loop/tests/helpers.py`
- Create: `research-loop/tests/test_lib.py`

## 接口（Produces——后续全部工单按这些签名消费）

plan.md §C1 的全部函数与类，逐个实现，签名一字不差。补充语义：

- `locked(path)`：锁文件是 `str(path)+".lock"`，父目录自动建；
  `fcntl.flock(fd, LOCK_EX)`，contextmanager，释放后关 fd。
- `jsonl_rows(path, include_archive=False)`：文件缺返回 `[]`；跳过空行；
  `include_archive=True` 时先读 `<name>.archive.jsonl`（存在才读）再读主文件。
- `inplace_update(path, key_field, key_value, updates, whitelist)`：
  updates 里出现白名单外字段 → `fail(path.stem, field, "field is not in-place updatable")`；
  行找不到 → `fail(path.stem, key_field, "row not found", key_value)`；
  写临时文件 + `os.replace` 原子替换。调用方持锁。
- `alloc_id(rows, id_field, prefix)`：取现有同前缀 id 的最大数字 +1，
  3 位零填充（`D001`；超 999 自然变宽 `D1000`）。
- `now_iso()/today()`：环境变量 `RL_FAKE_NOW`（ISO 秒级）存在则以它为准。
- `validate(row, schema, ledger)`：语义按 plan.md §C3 逐条实现；错误一律经
  `fail(ledger, field_path, msg, value)`，嵌套路径写成 `scope.expires_at`、
  `argv[2]`。类型检查注意 bool 不算 integer（Python 的 bool 是 int 子类，要排除）。
- `check_in_registry(argv, cfg, *, ledger, field)`：
  `shlex.split(cfg.get("registry_cmd"))` 必须是 argv 的前缀；其后首 token 即任务名；
  任务必须在 `registry_tasks(cfg)` 清单里；`registry_query` 为 null →
  `fail(ledger, field, "registry_query not wired (null); cannot verify task")`。
  registry_cmd 为 null → 同样 fail（点名 registry_cmd）。返回任务名。
- `parse_frontmatter(text)`：文件必须以 `---` 行开头，到下一个 `---` 行为头部；
  每行 `key: value`，value 先试 `json.loads`，失败按原样字符串；返回
  `(fields_dict, body_str)`，body 是第二条 `---` 行之后的全部原文。
- `spec_digest(path)`：对第二条 `---` 行之后的**原始字节**做 sha256 hexdigest
  （`tables/rows.json` spec_header `_digest_rule`）。
- `git_head(root)`：`git rev-parse HEAD`；`git status --porcelain` 非空加
  `-dirty` 后缀；非 git 仓库返回 `"no-git"`。

`Config`：
- `load_config(root)` 读 `root/research-loop.json`；`Config.get(key)` 缺省值取
  `research-loop/tables/config.json` 里的 plugin 默认（runtime_factor=3、
  roles、standing_authorization、inspection_policy=always；其余键无默认即 None）。
- `Config.ledger_path(name)`：config 的 ledgers[name] 覆盖
  `tables/ledgers.json` 的 default_path，相对 root 解析；含 `<artifact_dir>` 或
  `<raw_data_roots>` 模板的路径原样返回字符串不解析（调用方处理）。
- `Config.null_locked(key) -> bool`。

`helpers.py`（测试基建，后续所有 test_*.py 消费）：

```python
make_sandbox(tmp: Path) -> Path
# 造一个已接线沙盒工程：写 research-loop.json（ledgers 全键取默认路径、
# owners 取 schemas/owners.default.json 若存在否则按 tables/ledgers.json owner 列拼、
# registry_cmd/registry_query 指向 make_stub_registry 产物、record_cmd 同、
# runtime_factor=3、raw_data_roots=[str(tmp/"net")]、其余键 null），
# 建 ops/ ops/launch_orders/ plans/ reports/ .scratch/ 目录，
# 写 METHOD.md（含下述示例原则表）。返回工程根。
make_git_sandbox(tmp) -> Path      # make_sandbox + git init + 全部 commit（e2e 与脏树测试用）
make_stub_registry(root, tasks: dict[str, list[str]]) -> None
# 在 root/ 写 stub_registry.py：--list 打印任务名一行一个；
# `stub_registry.py <task> [args…]` 用 subprocess 转发到 tasks[task]+剩余参数，
# 透传退出码。tasks 以 json 内嵌进生成的脚本。
run_ledger(root, *args, env=None) -> (code, stdout, stderr)
# subprocess 跑 [sys.executable, <plugin>/scripts/ledger.py, *args]，cwd=root
run_script(root, script_name, *args, env=None) -> (code, stdout, stderr)
# 同上但跑 scripts/<script_name>
write_jsonl(path, rows)            # 裸写 fixture 用
make_blocked_row(**over) / make_decision_row(**over) / make_grant_row(**over) /
make_story_row(**over) / make_runs_row_normal(**over) /
make_runs_row_criterion(**over) / make_launch_order(**over) / make_suggestion_row(**over)
# 每个返回一份能过对应 schema 的合法 dict，关键字参数覆盖字段
```

METHOD.md 示例表（列名即 plugin 约定，T07 的解析器按它实现）：

```
| principle_id | status | scope | applies_when | principle | rationale | criterion_cmd | last_tested |
|---|---|---|---|---|---|---|---|
| P001 | 【现状】 | data | always | seeds are fixed | user said so 2026-08-13 | python3 stub_registry.py check-p001 | — |
| P002 | 【想法待定】 | eval | tbd | tbd idea | discussion 2026-08-13 | | — |
```

stub 任务 `check-p001` 的行为：stdout 最后一行打
`{"value": 3, "evidence_path": "ops/evidence.txt"}`，退出码 0。

## 测试（tests/test_lib.py，每条独立函数）

1. `alloc_id`: 空表→`B001`；`D009`→`D010`；`D999`→`D1000`。
2. `inplace_update` 白名单外字段拒，错误文案恰为
   `blocked.question: field is not in-place updatable`；行缺拒；原子替换后其余行字节不变。
3. `validate`（手写迷你 schema，不依赖 T03 生成物）：required 缺 / 生字段 /
   type 联合 / bool 不算 integer / enum / const / minimum / items 逐元素 /
   conditional require（条件成立缺字段拒、含 when 为数组的双条件）/
   allow_null（status=ok 时 metric_name=null 拒；status=failed 时放行；
   未被 allow_null 列名的可空字段恒放行）。
4. 错误格式：`fail("runs","metric_name","must not be null when status=ok", None)`
   产出 `runs.metric_name: must not be null when status=ok (got: None)`。
5. `split_cmd` 拒管道符与换行；`last_json_line` 取最后非空行、非 JSON 返回 None、
   非 dict（如 `[1,2]`）返回 None。
6. `parse_frontmatter`/`spec_digest`：改头部字段 digest 不变，正文加一个标点 digest 变。
7. `check_in_registry`（用 make_stub_registry）：前缀不符拒 / 任务不在清单拒 /
   registry_query 缺（config 置 null）拒且文案含 `not wired` / 合法通过返回任务名。
8. `locked`：持锁期间另一进程 `flock LOCK_EX|LOCK_NB` 失败（subprocess 一行探测）。
9. `now_iso` 吃 `RL_FAKE_NOW`。
10. `make_sandbox` 出来的工程跑 `jsonl_rows`/`Config.ledger_path` 正常。

跑法：`python3 research-loop/tests/run_all.py test_lib`（跑器 T01 已给）。

## Comments

- 2026-08-13 wave1 收账：DONE，0 修复轮，commit 范围 b737bf9..d7b3fee（merge 进 main）。
  主仓复跑 test_lib 32/32 过。cannotVerify 三条全是"等 T03/消费方工单"性质，
  留待后波核实：load_schema 无场地测、run_ledger 等 ledger.py 落地、
  make_launch_order 默认 argv 与 make_sandbox 的 registry_cmd 不对齐（下游要 override）。
  concerns 留档：Config 四个默认值是代码字面量（config.json 表只有文档字段无机读默认，
  工单原文如此）；record stub 是占位。
