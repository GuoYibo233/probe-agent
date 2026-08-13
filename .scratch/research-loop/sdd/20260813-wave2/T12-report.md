# T12 output_check.py + error_classify.py — 实现报告

工单：`.scratch/research-loop/issues/12-output-error.md`
分支：`ticket/20260813-wave2/T12`，base `41ed1236afe1642140d1f38e14740a9fc6656cd2`
工作树：`/home/y-guo/reproduce/new1-wt/20260813-wave2-T12`（已按协议删除，分支保留）

## 做了什么

### output_check.py --launch-order PATH

`research-loop/scripts/output_check.py`：读发射单 JSON（取 `artifact_dir` +
`expected_outputs`），逐条 `{path_glob, min_bytes?, min_lines?, required_keys?[]}`
比对：

- `path_glob` 用 `Path(artifact_dir).glob(...)`（相对 cwd 解析 artifact_dir，
  与 `tests/helpers.run_script` 的 `cwd=root` 约定一致），只认命中的文件
  （目录命中不计），零命中 → 该条 `missing-output`。
- 命中的每个文件：`min_bytes` 给了才比字节数，`min_lines` 给了才比行数，
  `required_keys` 非空才解析首个非空行；三条各自独立可各产生一条失败，
  同一文件可能同时出现在多条失败里。
- 解析首行失败或首行不是 JSON 对象（例如是数组/标量），一律按"缺键"处理——
  与工单"解析失败也算"一致。
- 条目内验数优先级 → 全局优先级：任一条目 `missing-output` → 整体
  `missing-output`；否则任一条目 `empty-output` → 整体 `empty-output`；
  否则 `ok`。
- stdout 只打印一行 `{"verdict": ..., "failures": [{glob, file, why}]}`；
  `verdict=ok` → exit 0，否则 exit 4。
- 本脚本不看实验进程的退出码——只看磁盘上落了什么，天然满足工单
  "退出码 0 + 产物空 → empty-output，不得记 ok"（没有让退出码影响判定的
  代码路径）。
- 发射单文件读不出来 / JSON 解析失败 / 缺 `artifact_dir` 等字段：
  stderr 报错，exit 2（区别于 verdict 的 0/4，工单未点名此分支，按
  `_lib.RLError` 的"报错走 stderr + 非零 exit"惯例处理）。

### error_classify.py --error-classes PATH [--exit-code N] [--log PATH] [--output-check V]

`research-loop/scripts/error_classify.py`：读分类表 `{规则名: {"match":
{...}, "action": ...}}`，按文件里的键序（Python dict 保序 = JSON 对象里出现的
顺序）逐条试：

- 每条规则的 `match` 只认三个键：`exit_code`（数值等）、`log_regex`（对
  `--log` 全文 `re.search`）、`output_check`（字符串等）；出现未知键直接
  报错退出（分类表本身写错比静默漏判更值得暴露）。
- AND 语义：规则给几个 match 键就都要中；调用方没给对应 CLI 输入的键
  （比如规则要 `log_regex` 但没传 `--log`）一律算不中，不当自由通过。
- 第一条全中的规则 → `{"rule": 名, "action": 动作}`；全不中 →
  `{"rule": null, "action": "unknown"}`——不猜，升级动作留给调用方（R8）。
- exit code 恒为 0：`unknown` 是合法分类结果，不是脚本失败；只有分类表
  读不出来才报错走 exit 2。

## 怎么验证的

`research-loop/tests/test_output_error.py`，12 个测试函数，全走子进程调脚本
（`helpers.run_script`，与已有 `test_lib.py` 的测试基建一致），断言 stdout
尾行 JSON 与进程退出码：

```
$ python3 research-loop/tests/run_all.py test_output_error
PASS test_output_error.test_error_classify_and_semantics_partial_match_does_not_count
PASS test_output_error.test_error_classify_exit_code_rule_hits_oom_kill
PASS test_output_error.test_error_classify_first_matching_rule_wins_key_order
PASS test_output_error.test_error_classify_log_regex_rule_hits_cuda_oom
PASS test_output_error.test_error_classify_output_check_rule_hits_escalate
PASS test_output_error.test_error_classify_unknown_when_nothing_matches
PASS test_output_error.test_output_check_glob_with_no_match_is_missing_output
PASS test_output_error.test_output_check_missing_output_wins_priority_over_empty_output
PASS test_output_error.test_output_check_missing_required_key_is_empty_output
PASS test_output_error.test_output_check_ok_when_products_are_all_present
PASS test_output_error.test_output_check_short_file_is_empty_output
PASS test_output_error.test_output_check_zero_byte_file_is_empty_output
-- run_all: 12 passed, 0 failed
```

对照工单第 4 部分四类测试要求逐一落位：

1. `output_check`：`test_output_check_ok_when_products_are_all_present`
   （齐全→ok/0）、`test_output_check_zero_byte_file_is_empty_output`
   （0 字节→empty-output/4）、`test_output_check_glob_with_no_match_is_missing_output`
   （无命中→missing-output）、`test_output_check_missing_required_key_is_empty_output`
   （缺键→empty-output）、`test_output_check_short_file_is_empty_output`
   （行数不足→empty-output）。另补一条
   `test_output_check_missing_output_wins_priority_over_empty_output`
   验证跨条目的 verdict 优先级。
2. 三类特征各命中一条：`test_error_classify_exit_code_rule_hits_oom_kill`
   （137→swap-card）、`test_error_classify_log_regex_rule_hits_cuda_oom`
   （CUDA out of memory→retry）、
   `test_error_classify_output_check_rule_hits_escalate`
   （empty-output→escalate）。
3. AND 语义：`test_error_classify_and_semantics_partial_match_does_not_count`
   （exit_code 中、log_regex 不中 → 不算命中，整体 unknown）。
4. 全不中：`test_error_classify_unknown_when_nothing_matches`。另补一条
   `test_error_classify_first_matching_rule_wins_key_order` 验证键序优先。

跑了完整套件确认没有破坏既有测试：

```
$ python3 research-loop/tests/run_all.py
-- run_all: 44 passed, 0 failed
```

（32 条既有 `test_lib.py` + 本工单新增 12 条，全绿。）

`run.py selfcheck` 未跑——本工单不改 `run.py` 注册表（工单范围声明已写明
"不改 run.py / MAP.md"）。

## commit 清单

- `1bd48c0` `T12: add output_check.py + error_classify.py (run-layer output/error contract)`
  —— 新增三个文件：`research-loop/scripts/output_check.py`、
  `research-loop/scripts/error_classify.py`、
  `research-loop/tests/test_output_error.py`。

## 自查发现与存疑

- **failures 的粒度**：一个文件同时违反 `min_bytes`/`min_lines`/
  `required_keys` 会在 `failures` 里出现多条（同一 `file` 不同 `why`），
  工单没有明说是"每条件一条"还是"每文件一条"，我按前者实现——更贴近 R3
  "差异定位"精神（逐点说清哪里不对），且工单给的 `{glob, file, why}` 单数
  `why` 字段形状暗示一条失败对应一个具体原因，不是聚合摘要。
- **`file` 字段是相对路径**：等于 `Path(artifact_dir).glob(...)` 返回的路径
  （即 `artifact_dir` 前缀 + 匹配片段），不是绝对路径。工单只给了字段名
  没给格式要求；我没有额外 resolve 成绝对路径，避免引入对 cwd 之外信息
  的依赖（部署层写发射单时用的就是相对 `artifact_dir`，产物钉代码
  RUNMETA 那条路径惯例也是仓库相对路径）。
- **非法输入的报错通道**（发射单文件读不出来、分类表键非法）：工单没有
  点名这两种分支的行为，我按 `_lib.py` 既有惯例（stderr 报错 + 非零 exit，
  与 verdict 的 0/4 分开）处理，exit code 用了 2（不与 output_check 的
  0/4、error_classify 的恒 0 冲突）。这是我自行裁决的边界情况，不影响
  工单点名的验收项，标记为存疑供复核。
- **`match` 未知键直接报错**（error_classify.py）：工单只说了三个合法键，
  没说遇到第四个键该怎么办；我选择报错而不是静默忽略，理由是分类表本身
  写错（比如手滑打错键名）比"这条规则永远不中"更值得在当场暴露，
  不算工单要求之外的行为分叉（没有新增 CLI 参数或输出字段），但仍是
  我自行裁决，一并标记存疑。

## 修复第 1 轮（2026-08-13）

工作树：`/home/y-guo/reproduce/new1-wt/20260813-wave2-T12-fix1`（已按协议删除，
分支 `ticket/20260813-wave2/T12` 保留）。收到 2 条 critical findings，逐条修。

### F1：error_classify.py 对畸形分类表条目未做错误处理，直接崩溃退出

先复现，确认 findings 描述的两条路径都真实存在：

```
$ python3 error_classify.py --error-classes classes.json --exit-code 1
# classes.json = {"bad-rule": {"match": {"exit_code": 1}}}
Traceback (most recent call last):
  ...
KeyError: 'action'

$ python3 error_classify.py --error-classes classes2.json --log log.txt
# classes2.json = {"bad-regex-rule": {"match": {"log_regex": "(unclosed"}, "action": "retry"}}
Traceback (most recent call last):
  ...
re.error: missing ), unterminated subpattern at position 0
```

两处都改成显式检查、抛 `ValueError`，走 `main()` 里已经存在的
`except ValueError`（原本就是给"未知 match 键"那条报错准备的通道，
不需要新开分支）：

- `_rule_matches()`：`log_regex` 命中判定时把 `re.search(...)` 包进
  `try/except re.error`，抓到就转 `ValueError("error-classes: invalid
  log_regex ...: ...")`。`log_text is None`（没传 `--log`）仍然先短路
  返回 `False`，不会去调 `re.search`——和改前的短路语义一致，只是
  "log_text 有值但 regex 本身写错"这条新路径不再裸崩。
- `classify()`：规则全中之后，取 `rule["action"]` 前先判
  `"action" not in rule`，没有就抛 `ValueError("error-classes: rule
  ... is missing required key 'action'")`。

改完复现同样两条命令，现在都是干净退出：

```
$ python3 error_classify.py --error-classes classes.json --exit-code 1
error_classify: error-classes: rule 'bad-rule' is missing required key 'action'
exit=2

$ python3 error_classify.py --error-classes classes2.json --log log.txt
error_classify: error-classes: invalid log_regex '(unclosed': missing ), unterminated subpattern at position 0
exit=2
```

stdout 为空（没有半行 JSON），exit=2，和分类表读不出来、`match` 出现
未知键这两条既有的干净报错路径完全同构——三种"分类表写坏了"的子情形现在
共用同一套错误处理，不再有第四种（裸 traceback）。

### F2：output_check.py 对 expected_outputs 条目里的类型错误未做错误处理，直接崩溃退出

先复现：

```
$ python3 output_check.py --launch-order launch_order.json
# launch_order.json 的 expected_outputs = [{"path_glob": "out.txt", "min_bytes": "not-a-number"}]
Traceback (most recent call last):
  ...
TypeError: '<' not supported between instances of 'int' and 'str'
```

在 `check_file()` 里，`min_bytes`/`min_lines` 各自在真正做 `<` 比较之前
先判类型（`isinstance(x, (int, float))`），不是数字就抛
`ValueError("expected_outputs: min_bytes/min_lines must be a number, got
...")`。finding 只演示了 `min_bytes` 的崩溃，但 `min_lines` 在同一个
函数里 9 行之后是完全对称的同类缺口（`if n_lines < min_lines:` 同样没有
类型防护），会被下一轮复验用同一手法打回来，所以两个字段一起补，
不是额外范围——没有新增字段、没有改动 `required_keys` 分支、没有碰
verdict 优先级逻辑。

`main()` 里 `run()` 外层的 `except` 元组原来是
`(OSError, json.JSONDecodeError, KeyError)`，加了 `ValueError` 进去，
让这条新路径走进已经在用的"发射单读不出来"清空报错通道
（`output_check: failed to read launch order ...` + exit 2），不新开
消息格式、不新开 exit code。

改完复现：

```
$ python3 output_check.py --launch-order launch_order.json
output_check: failed to read launch order launch_order.json: expected_outputs: min_bytes must be a number, got 'not-a-number'
exit=2
```

stdout 为空，exit=2，和"发射单缺字段"（`KeyError`）那条既有的干净报错
路径同构。

### 新增测试

`research-loop/tests/test_output_error.py` 新增 4 个测试函数，覆盖
findings 的两条崩溃路径各一个（外加 F2 对称补的 `min_lines` 一个）：

- `test_error_classify_missing_action_field_errors_cleanly`
- `test_error_classify_invalid_log_regex_errors_cleanly`
- `test_output_check_non_numeric_min_bytes_errors_cleanly`
- `test_output_check_non_numeric_min_lines_errors_cleanly`

每条都断言 `code == 2`、`out.strip() == ""`（没有半行 JSON 混进 stdout）、
`err` 里带脚本前缀（`error_classify:` / `output_check:`）。

### 测试结果

```
$ python3 research-loop/tests/run_all.py test_output_error
PASS test_output_error.test_error_classify_and_semantics_partial_match_does_not_count
PASS test_output_error.test_error_classify_exit_code_rule_hits_oom_kill
PASS test_output_error.test_error_classify_first_matching_rule_wins_key_order
PASS test_output_error.test_error_classify_invalid_log_regex_errors_cleanly
PASS test_output_error.test_error_classify_log_regex_rule_hits_cuda_oom
PASS test_output_error.test_error_classify_missing_action_field_errors_cleanly
PASS test_output_error.test_error_classify_output_check_rule_hits_escalate
PASS test_output_error.test_error_classify_unknown_when_nothing_matches
PASS test_output_error.test_output_check_glob_with_no_match_is_missing_output
PASS test_output_error.test_output_check_missing_output_wins_priority_over_empty_output
PASS test_output_error.test_output_check_missing_required_key_is_empty_output
PASS test_output_error.test_output_check_non_numeric_min_bytes_errors_cleanly
PASS test_output_error.test_output_check_non_numeric_min_lines_errors_cleanly
PASS test_output_error.test_output_check_ok_when_products_are_all_present
PASS test_output_error.test_output_check_short_file_is_empty_output
PASS test_output_error.test_output_check_zero_byte_file_is_empty_output
-- run_all: 16 passed, 0 failed
```

完整套件（本模块 16 + `test_lib.py` 32，确认没有破坏既有测试）：

```
$ python3 research-loop/tests/run_all.py
-- run_all: 48 passed, 0 failed
```

`run.py selfcheck` 未跑——本工单不改 `run.py` 注册表，本轮修复也没碰
`run.py` 相关的任何东西。

### commit 清单

- `29a1711` `T12: fix F1/F2 -- malformed classify rules / non-numeric gates crash instead of erroring cleanly`
  —— 改动 `research-loop/scripts/error_classify.py`、
  `research-loop/scripts/output_check.py`、
  `research-loop/tests/test_output_error.py`。

### 自查发现与存疑

- 两条 finding 都通过复用已有的干净报错通道（`except ValueError`
  分支/元组）解决，没有新增 exit code、没有新增 stdout 字段、没有改动
  任何一条既有测试的期望值——改动面严格限定在"给两个已知会崩的分支补
  类型/键存在性检查"。
- F2 对称补了 `min_lines`（finding 原文只演示了 `min_bytes`）：这是
  同一函数里紧挨着的同类缺口，不补的话下一轮复验大概率会用
  `min_lines` 版本的复现命令再报一次同一条 finding，判定为"finding
  范围内的彻底修复"而非扩大范围重构。
- 未再触碰上一轮报告里标记的两条存疑（"发射单/分类表读不出来的报错
  通道""`match` 未知键直接报错"）——它们和本轮 findings 无关，且是
  上一轮已交代过理由的自行裁决，不在本轮修复范围内。
