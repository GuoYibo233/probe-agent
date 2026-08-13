# T13 报告：oversight 面四件——evidence_lint / verify_report / spotcheck / regression_check

工单：`.scratch/research-loop/issues/13-oversight.md`
需求源：本工单 + `plan.md §C6`（报告体裁机验约定）+ `spec.md R3`（§3）+
`spec.md §4` 四脚本注释块 + `tables/rows.json`（`evidence_lint_exempt`、
`inspection_report_header`、`batch_report_header.rejections`、
`spec_header.withdrawals`、`story_row.metric_names`）。

## 一、做了什么（对照工单逐条）

### 1. `research-loop/scripts/evidence_lint.py`

`evidence_lint.py FILE [FILE ...]`，纯 stdlib 文本 lint，不读工程配置、不碰账本。

两类违规，逐条 `<file>:<line>: <rule>: <detail>`，任一违规 `exit 1`：

- **`banned-word`**（违禁结论词，plan.md §C6 双语词表：通过/没问题/符合预期/
  passed/looks good/no problems/as expected/all good/everything is fine）——
  英文词用 `\b...\b`（大小写不敏感）匹配，避免"surpassed"内含"passed"这类
  子串误报；中文词按纯子串匹配（`\b` 对中文没有干净的词边界语义）。
  **字段级豁免**：frontmatter 里 `verdict`/`rejections`/`withdrawals` 三个
  字段的整行豁免（rows.json `evidence_lint_exempt._field_level` 明确
  "字段级豁免登记在各自行条目"；spec.md R3 也说"结构化枚举字段...
  evidence_lint 按字段豁免"）——豁免只到这三个字段，frontmatter 里别的字段
  （如 `batch_id`）仍然照查，用测试
  `test_evidence_lint_other_frontmatter_fields_are_still_scanned` 钉死。
- **`no-repro-command`**（有数字无复现命令）——正文行剥完六类豁免形态
  （ISO 时间戳、YYYY-MM-DD、`chk-.../batch-id` 的 `...-YYYYMMDD-N` 尾形、
  `[A-Z]\d{3,}` id 形、`path:line` 形、≥7 位十六进制串）后仍剩数字才算
  经验数值；剩数值的行向下 3 行内无 `$ ` 开头行即违规。**这条豁免是块级的**：
  frontmatter 整块跳过（不分字段），跟 rule 1 的字段级豁免刻意不同——工单
  原文 rule 1 写"字段行豁免"、rule 2 写"frontmatter 行"豁免，两处措辞本身
  就不对称，我按字面分别实现。`$ ` 行自身和其后紧邻的 `= ` 回显行不参与
  "是否需要复现命令"的判定（它们是被检查的对象，不是需要复现命令的对象）。

### 2. `research-loop/scripts/verify_report.py`

`verify_report.py FILE [--project-root PATH]`，机械校验三样，任一失败 `exit 1`
并逐条打印 `<file>:<line>: <check>: <detail>`，末尾一行汇总 `verify_report:
<N> failures`：

- `path:line` 引用：路径相对工程根 `stat()` 存在、行数 ≥ 引用行号。
- 摘录回比：路径引用行之后 2 行内的 `> ` 引用块，其文本（去掉 `> ` 前缀）
  必须逐字（子串）出现在被引文件全文里——按工单原文"逐字出现在被引文件里"
  实现为全文子串匹配，不锁定到具体行号。
- 复现命令回比：`$ cmd` 行 + 紧邻下一行 `= value`——`_lib.split_cmd` 后
  `_lib.run_argv(cwd=工程根)` 重跑，取 stdout 最后非空行；声明值能解析成
  int/float 就数值比（容差 1e-9），否则整串字符串比；命令退出非 0 直接算失败。

`--project-root` 未给时按 `_lib.find_project_root()`（从 cwd 向上找）解析，
跟 `trace_check.py` 的既有约定一致。

### 3. `research-loop/scripts/spotcheck.py`

`spotcheck.py --file PATH --seed N [--k K]`（`--k` 默认 5——工单没给具体
默认值，是我自己定的一个数，不是从表里抄来的，写在这里留痕）。

`random.Random(seed).sample(range(1, 总行数+1), min(K, 总行数))` 抽行号；
stdout 单个 JSON：`{"fingerprint": {"rows": 总行数, "sha256": 文件原始字节
哈希}, "samples": [{"ref": "<--file 原样字符串>:<行号>", "excerpt": 该行
UTF-8 解码后前 80 字符}]}`。`sha256` 在 `splitlines()` 之前对整个文件的原始
字节算，独立于行怎么切；同 seed 同文件两次跑字节级一致（`json.dumps` 无
`sort_keys` 也稳定，因为字段顺序在代码里是固定写死的，不依赖集合迭代顺序）。

### 4. `research-loop/scripts/regression_check.py`

`regression_check.py --batch BATCH_ID [--dry-run] [--project-root PATH]`。

对每条故事账 `status=active` 的 claim：

- `metric_names` 为空/null → 明列进 Skipped 表的 `claim_id`（不进对照清单，
  也不静默漏掉——§9 原话）。
- `metric_names` 非空 → 对每个 metric_name，取该 claim `evidence_runs` 行里
  `metric_name` 相同的行作为旧值，按各行自己的 `filter` 分组；每个出现过的
  `filter` 取值，去新批（`runs` 账 `batch_id=BATCH_ID`）里 `metric_name`+
  `filter` 都相同的行作新值；**新值存在才出一条对照**
  `{claim_id, metric_name, filter, old: [{run_id, value, filter}, ...],
  new: [...]}`——没有任何"是否冲突"的判断句，`old`/`new` 只是数据列表。
  这个"按 filter 分组、每组各自判断新值是否存在"的具体输出粒度是我的设计
  选择（工单只给了字段名 `{claim_id, metric_name, filter, old, new}`，没给
  完整的分组/聚合规则细节），T14 doctor.py 接这个脚本时如果需要别的粒度，
  需要回头看。

输出一份 md 报告：frontmatter 溯源块（`batch_id`/`generated_at`/`git_head`/
`story_rows_read`/`runs_rows_read`）+ 正文两张表（Comparisons、Skipped）。
`--dry-run` 只打印到 stdout、不落盘（reports/ 是监察面独占写权，doctor 不能
越权写）；不带 `--dry-run` 同时打印并写 `reports/regression-<BATCH_ID>.md`。
输出里没有出现过 "conflict" 这个词（含大小写变体都没有），测试
`test_regression_check_comparison_carries_old_and_new_with_no_judgment_language`
直接断言 `"conflict" not in out.lower()`。

### 5. `research-loop/tests/test_oversight.py`

26 个测试，覆盖工单测试清单的四组要求（对应工单第 68-83 行逐条）：
- evidence_lint：正文 "everything passed" 揪出；"surpassed" 不误报（词边界）；
  frontmatter verdict/rejections/withdrawals 豁免（含在这三个字段里嵌违禁词
  验证真豁免，不是碰巧没词）；别的 frontmatter 字段仍照查；"count = 42" 无
  `$` 行揪出、有则不报（含 3 行窗口内）；六类豁免形态各自不报；`$`/`=` 行
  不自举；多文件聚合报告。
- verify_report：全真 exit 0；死路径、行号越界、摘录差一字、伪造计数、
  命令非零退出，各自被抓。
- spotcheck：同 seed 两跑字节一致；文件加一行后 rows 与 sha256 都变；
  samples 自校验（按 ref 读行、前 80 字符与 excerpt 相等）；k 大于总行数时
  截到总行数不崩。
- regression_check：对照条目含 old/new 数值且无判语；metric_names 空的
  claim 明列 Skipped；`status=retired` 的 claim 既不进对照也不进 Skipped；
  `--dry-run` 前后 reports/ 目录文件列表不变；不带 `--dry-run` 落盘且内容与
  stdout 一致；新批没有匹配数据时不产生对照条目、不崩。

## 二、怎么验证的

```
$ python3 research-loop/tests/run_all.py test_oversight
```
```
PASS test_oversight.test_evidence_lint_banned_word_in_body_is_caught
...(26 条 PASS)
-- run_all: 26 passed, 0 failed
```

```
$ python3 research-loop/tests/run_all.py
```
```
...
-- run_all: 247 passed, 0 failed
```
（T13 之前六波累计的既有测试也一并跑了一遍，247 条全绿，没有回归。）

```
$ python3 -m py_compile research-loop/scripts/evidence_lint.py research-loop/scripts/verify_report.py research-loop/scripts/spotcheck.py research-loop/scripts/regression_check.py research-loop/tests/test_oversight.py
```
无输出，正常退出。

本工单范围声明"不改 run.py / MAP.md"，且四个脚本是独立 stdlib 脚本、不挂
`ledger.py` 分发器，所以没有跑 `run.py selfcheck`（这个 repo 顶层命令跟
research-loop plugin 是两回事，plugin 自己的验收口子是
`research-loop/tests/run_all.py`）。

## 三、commit 清单

工作树 `/home/y-guo/reproduce/new1-wt/20260814-wave5-T13`，分支
`ticket/20260814-wave5/T13`，起点 `882dd1dd9f3d71ef2286e994fb1ba2e8763a2a8b`。

- `9250ac3` — `T13: oversight face four scripts -- evidence_lint / verify_report / spotcheck / regression_check`
  （新增 5 个文件：4 个脚本 + test_oversight.py，共 1272 行，一次性提交
  ——四个脚本互相独立、测试文件覆盖全部四个，没有能再拆的自然边界，
  拆成多个 commit 只会让某个 commit 单独跑测试跑不过）。

## 四、自查发现与存疑

1. **"≥7 位十六进制串"豁免规则字面上会漏掉纯数字长数值**——rows.json
   `evidence_lint_exempt.metadata_kinds` 写的是"git HEAD/commit"对应
   "≥7 位十六进制串"，我按字面实现为 `[0-9a-fA-F]{7,}`（不要求真的出现
   a-f 字母）。副作用：一个 7 位以上的纯十进制数字（比如"处理了 1234567
   条记录"，没有 `$` 命令跟着）**不会**被 `no-repro-command` 规则揪出来，
   因为它被这条豁免正则当成"疑似哈希"剥掉了。我验证过这个行为
   （见下方 bash 记录），是工单原文豁免规则的直接字面推论，不是实现漏洞，
   但这是一个真实的检出盲区，值得记在这里。
   ```
   $ python3 -c "
   import sys; sys.path.insert(0,'research-loop/scripts')
   import evidence_lint as el
   print(el._asserts_number('run for 1000000 steps'))
   "
   = False
   ```

2. **rule 1（违禁词）frontmatter 豁免是字段级、rule 2（有数字无复现命令）
   frontmatter 豁免是块级**——这是我对工单原文两处不同措辞（"字段行豁免"
   vs "frontmatter 行"）做的字面区分解读，有 spec.md R3 "按字段豁免" 和
   rows.json `_field_level` 两处旁证支持 rule 1 是字段级，但工单本身没有
   把这个不对称显式点破。我认为证据链够充分所以没有停下来问，但这是一个
   我做出的解读判断，不是照抄，标在这里方便复核。

3. **spotcheck `--k` 默认值 5** 是我自己定的，工单没给数字（只给了
   `[--k K]` 是可选参数这个事实）。如果后续别的脚本/skill 假设了某个特定
   默认值，需要对齐。

4. **regression_check 的分组粒度**（按 filter 分组、每个 filter 各出一条
   对照）是我在字段清单 `{claim_id, metric_name, filter, old, new}` 之上
   自己定的具体聚合方式，工单没给出更细的规则。T14（doctor）会调用这个
   脚本的 `--dry-run`，如果 doctor 那边对输出结构有隐含预期，需要回头核对。

5. 没有发现需要改动本工单范围外文件的情况；四个脚本严格独立于
   `ledger.py`/`ledger_cmds/`，没有触碰任何已有文件。

## 五、修复轮 1（评审 finding F1）

### finding

**F1（critical）**：`evidence_lint.py:83` 的 `_HEX_RE = re.compile(r"\b[0-9a-fA-F]{7,}\b")`
只要求连续 7 位以上落在 `[0-9a-fA-F]` 字符集内，不要求真的出现 a-f 字母。
一句没有 `$` 复现命令跟随的"处理了 1234567 条记录"会被这条豁免当成"疑似
git 哈希"整体剥掉，`no-repro-command` 规则完全不报——削弱了 R3 在 T13 里
唯一的机械把关点。评审给出的复验命令：
`el._asserts_number('we processed 1234567 records total')` 返回 `False`
（对照 6 位数 `123456` 返回 `True`）。

### 怎么修的

在 `_HEX_RE` 前加一个零宽前瞻，要求匹配到的这段 hex 字符里至少出现一个
a-f 字母（大小写不敏感）才算"疑似哈希"；纯 0-9 数字的连续串不再被这条
豁免剥掉，会正常留给 `_asserts_number` 判定为经验数值：

```python
# Character class [0-9a-fA-F] alone also matches a pure-decimal run (no
# a-f letter at all) -- that would silently strip a genuine >=7-digit
# empirical number (sample count, step count, ...) as if it were a git
# hash. A leading lookahead requires at least one a-f letter to actually
# occur among the run's hex characters before the run counts as
# hash-shaped; a run of nothing but digits 0-9 is left for _asserts_number
# to see.
_HEX_RE = re.compile(r"\b(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{7,}\b")
```

同步把模块顶部 docstring 里描述 rule 2 豁免形态的那句话也改了，把"hex
run of >=7 chars"改成"hex run of >=7 chars containing at least one a-f
letter"，并显式写明纯数字串不在这条豁免之内。

真正的 git commit hash（比如 `deadbeef1`）本来就几乎总是带 a-f 字母，这条
前瞻不影响它继续被豁免；只有"恰好 7 位以上、且恰好一个 a-f 字母都不含"的
纯十进制数（真实经验数值的常见形态）才会从"被豁免"变成"被豁免规则放行、
落回 `_asserts_number` 正常判定"。

修了工单原有测试 `test_evidence_lint_exempt_shapes_never_need_a_repro_command`
里的 `"commit deadbeef1\n"` 这个 fixture 本身就含 a-f 字母，不受影响，
原样保留、无需改动。

新增回归测试锁死这个边界（`test_oversight.py`）：

```python
def test_evidence_lint_pure_decimal_long_number_is_not_hex_exempt():
    # A >=7-digit number with no a-f letter at all is not hash-shaped -- it
    # must not be swallowed by the git-HEAD/commit exemption, or a genuine
    # unsupported empirical claim (sample count, step count, ...) would go
    # unreported (F1, T13 wave5 fix round 1).
    text = "we processed 1234567 records total\nnothing else nearby\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp) / "report.md", text)

        code, out, err = helpers.run_script(tmp, "evidence_lint.py", str(path))

        assert code == 1
        assert f"{path}:1: no-repro-command:" in out
```

### 怎么验证的

评审给出的复验命令，改前 `False`、改后 `True`（真正命中）；`deadbeef1`
（真实含字母的 hex 形态）仍然 `False`（继续豁免）：

```
$ python3 -c "
import sys; sys.path.insert(0,'research-loop/scripts')
import evidence_lint as el
print('1234567 records ->', el._asserts_number('we processed 1234567 records total'))
print('123456 (6-digit ctrl) ->', el._asserts_number('123456'))
print('deadbeef1 (real hex) ->', el._asserts_number('commit deadbeef1'))
"
= 1234567 records -> True
= 123456 (6-digit ctrl) -> True
= deadbeef1 (real hex) -> False
```

```
$ python3 research-loop/tests/run_all.py test_oversight
```
```
PASS test_oversight.test_evidence_lint_banned_word_in_body_is_caught
...(27 条 PASS，含新增的 test_evidence_lint_pure_decimal_long_number_is_not_hex_exempt)
-- run_all: 27 passed, 0 failed
```

全量回归，确认修复轮没有影响其他 12 个测试文件：

```
$ python3 research-loop/tests/run_all.py
```
```
...
-- run_all: 248 passed, 0 failed
```

```
$ python3 -m py_compile research-loop/scripts/evidence_lint.py research-loop/tests/test_oversight.py
```
无输出，正常退出。

### commit

工作树 `/home/y-guo/reproduce/new1-wt/20260814-wave5-T13-fix1`，分支
`ticket/20260814-wave5/T13`（复用原分支，检出已有分支）。

- `T13: fix F1 -- hex exemption no longer swallows pure-decimal 7+ digit numbers`
  （`evidence_lint.py` 加前瞻要求 a-f 字母 + docstring 同步措辞；
  `test_oversight.py` 新增一条回归测试锁死这个边界）。

### 自查

- 只改了 F1 点名的 `_HEX_RE` 一处正则和相邻 docstring 措辞，没有动
  `_STRIP_PATTERNS` 里其它五个豁免形态、没有动 rule 1（违禁词）逻辑、
  没有动 verify_report/spotcheck/regression_check 三个脚本——按 findings
  逐条修、不扩大范围。
- 没有改动本工单范围外的文件。
