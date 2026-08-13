# T08 报告 —— 发射单写入 + approve-spec + affects 回填

工单：`.scratch/research-loop/issues/08-launch-order.md`
分支：`ticket/20260814-wave4/T08`
工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave4-T08`（收尾已 `git worktree remove`，分支保留）

## 一、做了什么（对照工单逐条）

新建 `research-loop/scripts/ledger_cmds/launchcmd.py`（`ledger.py` 的
`_SUBCOMMAND_MODULES` 表里 `launch-order`/`approve-spec` 早已指向
`launchcmd`，这次是把这个占位坑填上，没有改 `ledger.py` 本身）。

### `approve-spec SPECFILE --by NAME`

- `_lib.parse_frontmatter` 解析失败（不是 `---` 起头的文件）直接让它的
  `RLError` 原样传出去——`ledger.py` 的 `main()` 统一接 `RLError` 打印+退出
  2，不需要在这里重新包一层。
- 三字段重写：`approved_by=args.by`、`approved_date=_lib.today()`、
  `approved_digest=_lib.spec_digest(path)`（digest 在改写前读，反正批准动作
  不碰正文，改写前后 digest 必然一致）；`spec_version` 只在原来是
  `None`（缺失或显式 null）时补 1，其余原样保留（含 `withdrawals` 等）。
- 正文字节：`parse_frontmatter` 拆出的 `body` 是原文本的一个后缀切片，
  没有做任何逐行改写，直接拼回新文件——天然逐字节保真，不需要额外校验逻辑。
- 头部按 `key: json.dumps(value)` 逐行重新序列化再拼 `---` 分隔线；写入前
  `_lib.locked(path)` 持锁（工单没点名要锁，但 spec §5"写入两式……都持文件
  锁"是通例，照做）。

### `launch-order --layer deploy --file DRAFT.json`

按工单给定的顺序实现，全过才写盘：

1. `--layer != deploy` → `launch_order.layer: launch-order is a
   deploy-layer action`。
2. `_lib.validate(draft, schema, "launch_order")`——`schema = _lib.
   load_schema("launch_order")`，单入口，不自己另写校验逻辑。
3. 注册表三查：`_lib.check_in_registry(draft["argv"], cfg,
   ledger="launch_order", field="registry_task")`（这个函数本身就做"前缀匹配
   + task 在 registry_query 清单 + registry_query null 时拒且文案含 not
   wired"三件事，`principlescmd.py` 已经在用同一个函数，工单要求的"同一函数"
   落实在这里）；它返回的 `task` 只是 argv 里实际出现的 token，工单要求的
   "token == draft.registry_task"是它没管的第四层比较，这里单独加一句，
   不等就报工单原文写死的字面文案
   `launch_order.registry_task: token after registry prefix does not
   match`（没有 `(got: ...)` 后缀——工单反引号里的字面串没带这个后缀，其余
   三条 `_lib.fail` 消息工单同样给了完整反引号字面串，照抄）。
4. 批准门禁：`quick=true` 时整条跳过（不只是 `spec_ref` 为空才跳过——工单
   原文"quick=true → 本条整个跳过"）；否则 `spec_ref` 非空才查：递归扫
   `cfg.ledger_path("specs")`（沙盒默认 `.scratch/`）下的 `*.md`，找"文本里
   含这个 item_id 字符串 **且** `parse_frontmatter` 解析成功"的文件（两个
   条件都不满足的文件直接跳过，不让它的解析失败拖垮整条命令）；按路径排序
   取第一个命中的当"该 item 的家"（工单没规定多文件命中时怎么办，这里选
   了个确定性最强的处理，见"自查发现"）。找不到 → `launch_order.spec_ref:
   spec item not found`；找到但 `approved_by` 空 → `launch_order.spec_ref:
   spec not approved`（工单原文这条只反引号了 `spec not approved` 四个词，
   没带 `launch_order.spec_ref:` 前缀——判断这是工单在引用消息正文时的省写，
   不是要求这条消息脱离 `_lib.fail` 的统一格式单独裸打，所以还是用
   `_lib.fail("launch_order", "spec_ref", "spec not approved", item_id)`
   走通用格式，见"自查发现"第 1 条）；digest 重算不等 →
   `launch_order.spec_ref: approval_stale`。
5. `decision_refs`（`quick=true` 下允许是 `None`，按空表处理）逐个查
   `decisions.jsonl`：不存在 → `launch_order.decision_refs: decision not
   found`；存在但 `status != decided` → `launch_order.decision_refs:
   decision is not status=decided`（这两条工单没给字面文案，自己按
   `_lib.fail` 惯例起的名）。
6. `promoted_from` 非空：目标文件 `<launch_orders 目录>/<pf>.json` 不存在 →
   `launch_order.promoted_from: promoted launch order not found`（文案自
   拟）；存在但 `quick` 不是 `true` → 工单原文字面
   `launch_order.promoted_from: promoted_from must point to a quick
   launch order`。按工单说明，`promoted_from` 指向的单里字段是否跟本单
   一致（seed/argv 等）不在这里查，归 T11 trace_check。
7. 全部通过后才写盘：`<launch_orders 目录>/<run_id>.json`，
   `_lib.locked` 持这一个文件的锁，`json.dumps(indent=2)`；同路径重写就是
   覆盖，天然幂等。写完**才**做 affects 回填：`decision_refs` 非空时持
   `decisions.jsonl` 锁，对每个引用的 D 行，`run_id` 不在它的 `affects`
   里就 `{**row, affects: affects+[run_id]}` 过一遍 `_lib.validate` 再
   `_lib.inplace_update`（`affects` 在 `writes.json` 的
   `form2_inplace_whitelist.decisions` 白名单里）；已经在 `affects` 里就
   跳过——这就是"重跑即修复"的落点，也是测试 6 要验的幂等性。

### `helpers.py`（共享测试基建，非本工单 Create 清单里的文件，但工单
Comments 明确点名要改）

`make_sandbox()` 调 `make_stub_registry()` 时补一个 `"noop": [sys.
executable, "-c", "pass"]` 任务。工单原话："helpers 的 stub 注册一个
`noop` 任务即可"——起因是沙盒里 `registry_cmd` 是
`{sys.executable} {绝对路径}/stub_registry.py`，而
`helpers.make_launch_order()` 给的默认 `argv` 是相对形式
`["python3", "stub_registry.py", "check-p001"]`，两者前缀对不上，直接拿
默认值去过 `check_in_registry` 必炸。测试里没有直接用这个默认 `argv`，
而是自己写了 `_registry_argv(root, task)`：从沙盒的 `research-loop.json`
读真实 `registry_cmd`、`shlex.split` 出前缀、拼上 task 名，构造出真正能过
三查的 `argv`。

## 二、怎么验证的

### `python3 research-loop/tests/run_all.py test_launch_order`

```
PASS test_launch_order.test_approval_gate_not_stale_after_header_only_edits
PASS test_launch_order.test_approval_gate_rejects_unapproved_then_passes_after_approve
PASS test_launch_order.test_approval_gate_stale_after_body_edit
PASS test_launch_order.test_approve_spec_preserves_body_bytes_and_sets_header_fields
PASS test_launch_order.test_approve_spec_rejects_file_without_frontmatter
PASS test_launch_order.test_promoted_from_missing_target_rejected
PASS test_launch_order.test_promoted_from_pointing_to_non_quick_rejected
PASS test_launch_order.test_promoted_from_pointing_to_quick_passes
PASS test_launch_order.test_quick_false_missing_refs_rejected_by_schema
PASS test_launch_order.test_quick_true_all_refs_null_writes_successfully
PASS test_launch_order.test_registry_argv_prefix_mismatch_rejected
PASS test_launch_order.test_registry_query_null_rejected_not_wired
PASS test_launch_order.test_registry_task_not_listed_rejected
PASS test_launch_order.test_registry_token_mismatch_rejected_with_exact_message
PASS test_launch_order.test_same_run_id_twice_is_idempotent_and_affects_backfill_dedups
-- run_all: 15 passed, 0 failed
```

工单 1-7 条测试与函数的对应：1→`test_quick_false_missing_refs_rejected_
by_schema`；2→`test_registry_argv_prefix_mismatch_rejected` +
`test_registry_token_mismatch_rejected_with_exact_message` +
`test_registry_task_not_listed_rejected` +
`test_registry_query_null_rejected_not_wired`（工单给的四个子场景一个场景
一个函数）；3→`test_approval_gate_rejects_unapproved_then_passes_after_
approve` + `test_approval_gate_stale_after_body_edit` +
`test_approval_gate_not_stale_after_header_only_edits`；4→
`test_quick_true_all_refs_null_writes_successfully`；5→
`test_promoted_from_missing_target_rejected` +
`test_promoted_from_pointing_to_non_quick_rejected` +
`test_promoted_from_pointing_to_quick_passes`；6→`test_same_run_id_twice_
is_idempotent_and_affects_backfill_dedups`；7→`test_approve_spec_
preserves_body_bytes_and_sets_header_fields`（另加
`test_approve_spec_rejects_file_without_frontmatter`，工单要求段落里点了
"parse_frontmatter 失败 → 拒"这条行为但没编进"测试"清单，边界处补的）。

### 全量：`python3 research-loop/tests/run_all.py`

```
-- run_all: 156 passed, 0 failed
```

（15 个新测试 + 此前六张工单遗留的 141 个，全绿，没有破坏任何既有测试。）

### `gen-schemas --check` / `spec_lint.py`（本工单没碰 `tables/`
或 `spec.md`，跑一遍确认没有连带破坏）

```
$ python3 research-loop/scripts/ledger.py gen-schemas --check; echo exit=$?
exit=0
$ python3 .scratch/research-loop/spec_lint.py 2>&1 | tail -3
-- spec_lint: 0 errors, 0 warnings
```

### 语法检查

```
$ python3 -m py_compile research-loop/scripts/ledger_cmds/launchcmd.py \
    research-loop/tests/test_launch_order.py research-loop/tests/helpers.py
（无输出，exit 0）
```

## 三、commit 清单

- `6b6c381` — `T08: launch-order + approve-spec (launchcmd.py)`
  （`launchcmd.py` + `test_launch_order.py` + `helpers.py` 的 `noop`
  任务，功能与测试同一逻辑单元，一次提交）。

## 四、自查发现与存疑

1. **"spec not approved" 消息前缀的解读选择**：工单反引号里只写了
   `spec not approved` 四个字，没带 `launch_order.spec_ref:` 前缀，跟另外
   两条（`spec item not found`、`approval_stale`）都明确给了带前缀的完整
   字面串不一致。判断这是工单在这一处只引用了消息正文（省写前缀），因为
   全仓库每一处报错都经 `_lib.fail(ledger, field, msg)` 统一产出
   `<ledger>.<field>: <msg>` 格式，没有任何先例是裸打不带前缀的字符串；
   按这个格式实现出来的实际文案是
   `launch_order.spec_ref: spec not approved`。测试用 `in` 做子串匹配，
   两种理解都能过；如果工单本意就是要一条不带前缀的裸消息，这里需要改。
2. **spec_ref 命中多个文件时取哪个**：工单"递归找含该 item_id 字符串且带
   frontmatter 的 *.md"没规定如果多个文件都命中该怎么办。实现按路径排序
   取第一个（确定性最强的简单处理），没有对"命中多个"这件事本身报错或
   给出提示。真实工程里一个 item_id 大概率只应该出现在它自己的 spec
   文件里，多命中更可能是误用；这里没有加额外检测，YAGNI。
3. **`_backfill_affects` 对同一 `decision_refs` 里出现重复 D 号的处理**：
   一次函数调用里先整体读一次 `decisions.jsonl` 到内存 `by_id`，逐个
   `ref` 处理时不重新读盘；如果 `decision_refs` 里出现同一个 `decision_id`
   两次（正常情况下不应该发生，工单没提这个场景），第二次处理时用的还是
   第一次处理前的旧快照，可能导致 `affects` 被同一个 run_id 追加两次而不是
   一次。没有为这个没被要求的场景加防御，按 YAGNI 处理，测试 6 验的是
   "同一条命令跑两遍"的幂等（这条测过、绿），不是"一次draft 里 decision_
   refs 自身有重复"。
4. **锁的粒度**：写发射单文件时锁的是 `<run_id>.json` 这一个文件本身
   （不是整个 `launch_orders/` 目录），跟 `_lib.locked()` 一贯"按具体文件
   路径加锁"的用法一致；affects 回填单独在写完发射单**之后**再拿
   `decisions.jsonl` 的锁（不是嵌套在同一个 `with` 块里），是刻意按 spec
   §5"先落盘、affects 后写"这句话把两步物理拆成两个独立的临界区，而不是
   `blockedcmd.py` 里那种"外层锁套内层锁、一次 `with` 块里做完两件事"的
   写法——两种模式的选择依据是 spec 原文有没有要求"崩溃只能停在旧状态或
   多一条孤儿行"这种跨文件原子性语义；这里 affects 缺失只是索引缺失，
   trace_check 会报、重跑同一条命令会自愈，不需要嵌套锁提供的那种保证。

---

## 五、修复第 1 轮（F1/F2/F3）

分支：`ticket/20260814-wave4/T08`（同一条分支上追加一个 commit，不新开分支）
工作树：`/home/y-guo/reproduce/new1-wt/20260814-wave4-T08-fix1`（收尾已
`git worktree remove`，分支保留）

### F1（important）——approve-spec 的读-算-写不在同一把锁保护范围内

**问题**：上一轮实现里 `_run_approve_spec` 只在最后 `path.write_text(...)`
这一步外面套了 `with _lib.locked(path):`；前面的 `path.read_text()`、
`parse_frontmatter`、算三字段、拼 `new_text` 全程不持锁。跟仓库里所有其它
读-改-写（`decisionscmd._run_decision_withdraw`、`blockedcmd._run_answer`
/`_run_close`/`_run_withdraw`）的写法拧着——那几处全是先 `with
_lib.locked(path):` 拿锁、锁内读当前状态、锁内算 merged、锁内写，没有一处
是"锁只包写不包读"。破坏后果：两次 `approve-spec` 并发跑在同一个 spec
文件上，第二次调用可能读到第一次写入前的旧内容，写回时把第一次的批准结果
静默覆盖掉，不报错。

**修法**：把 `text = path.read_text(...)` 到 `path.write_text(...)` 整段
挪进 `with _lib.locked(path):` 块内，锁的持有范围从"只包写"改成"包读-算-
写全程"，跟 `blockedcmd.py`/`decisionscmd.py` 的写法对齐。函数体逻辑一字
未改，只是缩进和锁的开合位置变了，新增一段注释说明为什么要这样锁
（对照 `decisionscmd._run_decision_withdraw`）。

文件：`research-loop/scripts/ledger_cmds/launchcmd.py` `_run_approve_spec`
（原第77-101行 → 现第77-108行）。

### F2（important）——approve-spec 的 spec_version 缺省置1行为没有测试覆盖

**问题**：`test_approve_spec_preserves_body_bytes_and_sets_header_fields`
唯一验证 `spec_version` 的用例用的 fixture（`_write_spec()`）一开始就写死
`spec_version: 1`，approve-spec 跑之前就已经是 1，"缺则置 1" 这条 if
分支走不走结果都一样，未被验证。

**修法**：加了一个 fixture-only 辅助函数 `_write_spec_custom(root, rel,
header)`（跟 `_write_spec` 平行、接受调用方给的 header dict，用来构造
`_write_spec` 硬编码逻辑造不出的边界形状），再加两条测试：

- `test_approve_spec_defaults_missing_spec_version_key_to_one`：frontmatter
  完全不写 `spec_version` 这一行（键不存在）。
- `test_approve_spec_defaults_null_spec_version_to_one`：frontmatter 显式
  写 `spec_version: null`。

两条都断言 `approve-spec` 跑完后 `fields["spec_version"] == 1`。

**验证这两条测试真的钉住了这个分支**：临时把 `launchcmd.py` 里
`if fields.get("spec_version") is None: fields["spec_version"] = 1`
两行删掉重跑，两条新测试都变红（其余 16 条不受影响）：

```
FAIL test_launch_order.test_approve_spec_defaults_missing_spec_version_key_to_one
FAIL test_launch_order.test_approve_spec_defaults_null_spec_version_to_one
-- run_all: 16 passed, 2 failed
```

验证完把改动还原（`diff` 确认与改动前逐字节相同）。

文件：`research-loop/tests/test_launch_order.py`（新增
`_write_spec_custom` 辅助函数 + 两条测试函数，插在原有
`test_approve_spec_rejects_file_without_frontmatter` 之后）。

### F3（important）——quick=true 豁免批准门禁在 spec_ref 非空场景下没有测试覆盖

**问题**：`launchcmd.py` 里门禁跳过条件是"quick=true 就跳过"（比 spec.md
字面"spec_ref 空的 quick 发射单豁免"更宽的解读），但现有测试所有
`quick=true` 的用例都同时把 `spec_ref=None`，没有一条测试构造
"quick=true 但 spec_ref 非空、且该 spec 未批准"的场景去验证这条门禁真的
整条跳过而不是报 `spec not approved`。上一轮实现者自己在报告里点出了这个
解读分歧，但没留测试钉死实际行为，是回归风险最高但没有测试兜底的地方。

**修法**：加了一条测试
`test_quick_true_with_nonnull_unapproved_spec_ref_skips_approval_gate`：
先写一个存在但未批准的 spec 文件（`approved_by` 仍是 null），构造
`quick=true, spec_ref="IT-001"` 的发射单草稿，断言 `launch-order` 返回
`code == 0`——如果门禁在这个场景下真的跑了，会因为 spec 未批准报
`spec not approved` 而不是 0。

**验证这条测试真的钉住了实际选择的宽读法**：临时把跳过条件从
`if not draft.get("quick") and draft.get("spec_ref") is not None:` 改成
`if draft.get("spec_ref") is not None:`（窄读法：quick 不再整体豁免），
重跑后新测试变红：

```
FAIL test_launch_order.test_quick_true_with_nonnull_unapproved_spec_ref_skips_approval_gate
AssertionError: ('', "launch_order.spec_ref: spec not approved (got: 'IT-001')\n")
-- run_all: 17 passed, 1 failed
```

验证完把改动还原（`diff` 确认与改动前逐字节相同）。生产代码本身对这条
finding **未改动**——工单原文"quick=true → 本条整个跳过"，上一轮的宽读法
就是工单字面意思，这条 finding 要补的是测试覆盖，不是改行为。

文件：`research-loop/tests/test_launch_order.py`（新增测试函数，插在
`test_approval_gate_not_stale_after_header_only_edits` 之后、第 4 节
"quick=true 全豁免"的分节注释之前）。

### 测试

`python3 research-loop/tests/run_all.py test_launch_order`：

```
PASS test_launch_order.test_approval_gate_not_stale_after_header_only_edits
PASS test_launch_order.test_approval_gate_rejects_unapproved_then_passes_after_approve
PASS test_launch_order.test_approval_gate_stale_after_body_edit
PASS test_launch_order.test_approve_spec_defaults_missing_spec_version_key_to_one
PASS test_launch_order.test_approve_spec_defaults_null_spec_version_to_one
PASS test_launch_order.test_approve_spec_preserves_body_bytes_and_sets_header_fields
PASS test_launch_order.test_approve_spec_rejects_file_without_frontmatter
PASS test_launch_order.test_promoted_from_missing_target_rejected
PASS test_launch_order.test_promoted_from_pointing_to_non_quick_rejected
PASS test_launch_order.test_promoted_from_pointing_to_quick_passes
PASS test_launch_order.test_quick_false_missing_refs_rejected_by_schema
PASS test_launch_order.test_quick_true_all_refs_null_writes_successfully
PASS test_launch_order.test_quick_true_with_nonnull_unapproved_spec_ref_skips_approval_gate
PASS test_launch_order.test_registry_argv_prefix_mismatch_rejected
PASS test_launch_order.test_registry_query_null_rejected_not_wired
PASS test_launch_order.test_registry_task_not_listed_rejected
PASS test_launch_order.test_registry_token_mismatch_rejected_with_exact_message
PASS test_launch_order.test_same_run_id_twice_is_idempotent_and_affects_backfill_dedups
-- run_all: 18 passed, 0 failed
```

（15 条原有 + 3 条新增，F1 的锁改动不新增测试用例——它是并发场景，这个
仓库的测试基建里没有并发测试设施，跟锁改动本身对齐周边代码风格的定性一致，
用已有 18 条测试全绿来确认没有把读-改-写的行为改坏。）

全量：`python3 research-loop/tests/run_all.py`

```
-- run_all: 159 passed, 0 failed
```

（156 + 3 新增，全绿。）

`gen-schemas --check` / `spec_lint.py`（本轮没碰 `tables/` 或 `spec.md`）：

```
$ python3 research-loop/scripts/ledger.py gen-schemas --check; echo exit=$?
exit=0
$ python3 .scratch/research-loop/spec_lint.py 2>&1 | tail -3
-- spec_lint: 0 errors, 0 warnings
```

语法检查：

```
$ python3 -m py_compile research-loop/scripts/ledger_cmds/launchcmd.py \
    research-loop/tests/test_launch_order.py research-loop/tests/helpers.py
（无输出，exit 0）
```

### commit

- `2fffc36` — `T08: fix1 -- approve-spec read-modify-write lock scope +
  missing test coverage (F1/F2/F3)`（`launchcmd.py` 的锁范围改动 +
  `test_launch_order.py` 的三条新增测试，同一逻辑单元一次提交）。

### 自查

- diff 只碰了 findings 点名的两个文件（`launchcmd.py` +
  `test_launch_order.py`），`git diff --stat` 确认无越界改动。
- 没有借这一轮顺手做 findings 之外的重构；`_check_spec_approval` 里
  "命中多个 spec 文件取第一个"等第一轮自查里存疑但未被 finding 点名的地方
  保持原样未动。
- F1 的注释新增了对照 `decisionscmd._run_decision_withdraw` 的说明，帮后人
  理解为什么这里要锁读；没有改动其余任何函数的锁范围。
