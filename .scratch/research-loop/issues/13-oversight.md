# T13 监察面四件：evidence_lint / verify_report / spotcheck / regression_check

Status: claimed
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + plan.md §C6（报告体裁机验约定，逐条即需求）+ spec.md R3、§4 四脚本
注释 + `tables/rows.json`（evidence_lint_exempt、inspection_report_header、
batch_report_header.rejections、spec_header.withdrawals、story_row.metric_names）。

## 文件

- Create: `research-loop/scripts/evidence_lint.py`
- Create: `research-loop/scripts/verify_report.py`
- Create: `research-loop/scripts/spotcheck.py`
- Create: `research-loop/scripts/regression_check.py`
- Create: `research-loop/tests/test_oversight.py`

## 要求

### evidence_lint.py FILE [FILE ...]

两类违规，一行一报 `<file>:<line>: <rule>: <detail>`，任一违规 exit 1：

1. **违禁结论词**（plan.md §C6 双语词表）：正文行查；frontmatter 的
   verdict / rejections / withdrawals 字段行豁免（rows.json 成文豁免面）。
2. **有数字无复现命令**：含数字的正文行，向下 3 行内无 `$ ` 开头行 → 违规。
   豁免（evidence_lint_exempt 的机器形态，先剥再判）：ISO 时间戳、
   YYYY-MM-DD、≥7 位十六进制串（git HEAD/哈希）、`path:line` 形态、
   id 形态 `[A-Z]\d{3,}` 与 `chk-…`/batch id 形态、frontmatter 行、
   `$ ` 行自身与其 `= ` 回显行。剥完还剩数字才算经验数值。

### verify_report.py FILE [--project-root P]

机械校验器，三样都查，任一失败 exit 1 并逐条打印：

1. `path:line` 引用：路径（相对工程根）stat 存在、行数 ≥ line。
2. 摘录回比：紧跟在含路径引用行之后 2 行内的 `> ` 引用块，其文本必须逐字
   出现在被引文件里。
3. 复现命令回比：`$ cmd` 行 + 下一行 `= value`——`split_cmd` 后
   `run_argv(cwd=工程根)` 重跑，取 stdout 最后非空行：整数/浮点按数值比
   （浮点容差 1e-9），否则字符串全等。命令退出非 0 也算失败。

### spotcheck.py --file PATH --seed N [--k K]

固定种子抽样：`random.Random(seed)` 从文件行号里 sample min(K, 行数) 个；
stdout 单个 JSON：`{"fingerprint": {"rows": 总行数, "sha256": 文件字节哈希},
"samples": [{"ref": "<path>:<行号>", "excerpt": 该行前 80 字符}]}`。
同 seed 同文件 → 输出逐字节一致；文件动一字节 → fingerprint 变。

### regression_check.py --batch BATCH_ID [--dry-run] [--project-root P]

新批次 vs 故事账 active claim 同口径重比（只报事实不判，R2）：

- 对每个 active claim：metric_names 为空/null → 进 `skipped` 清单
  （显式列出 claim_id，不报冲突也不静默漏掉——§9）。
- metric_names 非空：对每个 metric，取该 claim 各 evidence_runs 行
  （metric_name 相同）的 (run_id, value, filter) 为旧值；取新批
  （runs 账 batch_id=BATCH_ID）中 metric_name 相同且 filter 相同的行为新值；
  新值存在 → 出一条对照 `{claim_id, metric_name, filter,
  old: [...], new: [...]}`（无任何"是否冲突"的判语）。
- 输出 md 报告：对照清单 + skipped 清单 + R3 溯源块（生成时间、git HEAD、
  所读账本行数）。--dry-run → 只打 stdout **不落盘**（doctor 用，避免越权写
  reports/）；无 --dry-run → 同时写 `reports/regression-<BATCH_ID>.md`。

## 测试（test_oversight.py）

1. evidence_lint：正文一句 "everything passed" → 揪出；frontmatter
   `verdict: clean` → 不报；"count = 42" 无 `$ ` 行 → 揪出；同句下一行给
   `$ wc -l x` → 不报；`2026-08-13`、7 位以上 sha、`ops/x.jsonl:12`、
   `B003` → 都不报（豁免面）。
2. verify_report：伪造计数（`= 43` 实际 42）→ 抓出；死路径 / 行号越界 →
   抓出；摘录与原文差一字 → 抓出；全真 → exit 0。
3. spotcheck：同 seed 两跑输出一致；文件加一行 → fingerprint.rows 与
   sha 都变；samples 的 ref 行号可回查（自校验：按 ref 读行 == excerpt 前缀）。
4. regression_check：fixture——active claim（metric_names=["acc"]，
   evidence run r1 acc=0.9）+ 新批 r9 行 acc=0.7 同 filter → 对照条目含
   old 0.9 / new 0.7，无判语（输出里不得出现 conflict 一词的判断句，只有
   数据字段）；metric_names 空的 claim → skipped 明列；
   --dry-run 前后 reports/ 目录无新文件，无 --dry-run 落
   reports/regression-<batch>.md。

## Comments
