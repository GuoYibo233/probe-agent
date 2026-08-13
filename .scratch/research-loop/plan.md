# research-loop plugin 实施计划

> **执行方式：** 工单批量执行走 `.claude/skills/ticket-run/SKILL.md`（仓库唯一入口）。
> 工单在 `issues/`，按 Blocked by 分波。实现者只读工单与工单点名的 spec 节。
> 实施完成后由主会话跑验证循环（本文件 §V），迭代到全绿。

**目标：** 把 `.scratch/research-loop/spec.md`（v2 内核版）实现成可安装的机器级
plugin：五个 skill + inspector agent + 九个脚本 + fallback 五件 + 生成的 schemas/，
全部自测通过，九场景假铁轨自测走通。

**架构：** 散文内核 + 五数据表已定稿；实现从表单向生成 schemas，脚本共用一个
纯 stdlib 的 `_lib.py`；ledger.py 是薄分发器，子命令一组一个模块（可并行施工）。

**技术栈：** Python 3.10，纯标准库（零第三方依赖——机器级 plugin 不得假设任何
虚拟环境）。测试用自带的 stdlib 跑器 `tests/run_all.py`，不用 pytest。

**Spec：** `.scratch/research-loop/spec.md`（唯一设计真源）＋
`research-loop/tables/*.json` 五表（封闭清单唯一成文处）。

## 全局约束（每张工单默认继承）

1. **plugin 本体一律英文**：SKILL.md、脚本报错信息、注释、测试名（spec §4）。
2. **纯 stdlib**：禁止 import 任何第三方包。本机只有 `python3` 没有 `python`。
3. **plugin 根**：`/home/y-guo/reproduce/new1/research-loop/`（在 new1 仓库里开发，
   git 管版本；机器级安装是后续动作，不在本计划）。
4. **表是唯一真源**：封闭清单（枚举、字段、写权、路由、配置键）一律从
   `research-loop/tables/*.json` 读，代码里不许复写一份。schemas/ 由
   `ledger.py gen-schemas` 生成，禁手改，键序 `sort_keys=True` + `indent=2` +
   尾换行，重复生成逐字节相同。
5. **报错格式定死**：schema/写权类拒绝一律
   `<账名>.<字段路径>: <说明> (got: <实际值>)`，经 `_lib.fail()` 单点产出（spec §9）。
6. **schema 校验单入口**：两个 runs 写入口、发射单写入、四本 jsonl 账写入共用
   `_lib.validate()`（spec §9）。
7. **写入纪律**：jsonl 追加与就地更新都持文件锁（`<账文件>.lock`，fcntl.flock）；
   就地更新只许 `tables/writes.json` form2 白名单字段；复合动作按 writes.json
   `_write_order` 写序（翻状态最后写），按 `_idempotency` 查重（重跑即修复）。
8. **v1 裁掉的**（spec §10）：archive 执行件（doctor 只做 cap 告警）、hooks、
   web 界面、多研究线目录树、通知/时限提醒。读侧的 `--include-archive` 钩子照实现
   （glob `<name>.archive.jsonl`，v1 里不存在就是空集），写侧跨档就地更新不做。
9. **不碰 new1 工程件**：plugin 脚本不是 run.py 注册表任务，工单一律
   **不改 run.py、不改 MAP.md**（MAP.md 的 plugin 总行由主会话在脚手架 commit
   里加好）。new1 挂接七项（spec §9 挂接清单）不在本计划，单独走 R5。
10. **测试命令**：`python3 research-loop/tests/run_all.py [test_模块名]`。
    每张工单交付前自己那份测试文件全过，且全量跑一遍不破坏别人的。

## 目录结构（脚手架 commit 建好，工单只填内容）

```
research-loop/
├── .claude-plugin/plugin.json          # {"name":"research-loop","version":"0.1.0",...}
├── tables/                             # 五表（从 .scratch/research-loop/tables/ git mv 过来）
├── skills/
│   ├── research-loop/SKILL.md          # 路由薄壳（T15）
│   ├── idea-layer/SKILL.md + references/
│   ├── deploy-layer/SKILL.md + references/
│   ├── run-layer/SKILL.md + references/
│   └── oversight/SKILL.md + references/
├── agents/inspector.md                 # (T15)
├── schemas/                            # 生成物（T03）：8 个 *.schema.json + owners.default.json
├── scripts/
│   ├── _lib.py                         # (T02) 共用库
│   ├── ledger.py                       # (T03) 薄分发器
│   ├── ledger_cmds/                    # 子命令模块（各工单一人一模块，避免同文件冲突）
│   │   ├── __init__.py                 # (T03)
│   │   ├── genschemas.py               # (T03) gen-schemas [--check]
│   │   ├── configcmd.py                # (T04) config-check / init
│   │   ├── blockedcmd.py               # (T05) blocked open/answer/close/withdraw
│   │   ├── decisionscmd.py             # (T05) grant / decision / decision withdraw
│   │   ├── storycmd.py                 # (T06) story add/retire
│   │   ├── feedbackcmd.py              # (T06) feedback add/review
│   │   ├── runscmd.py                  # (T07) runs-append
│   │   ├── principlescmd.py            # (T07) principles-lint / render principles
│   │   ├── launchcmd.py                # (T08) launch-order / approve-spec
│   │   ├── querycmd.py                 # (T09) query / render blocked
│   │   ├── statuscmd.py                # (T09) status
│   │   └── freezecmd.py                # (T10) freeze-legacy
│   ├── trace_check.py                  # (T11)
│   ├── output_check.py                 # (T12)
│   ├── error_classify.py               # (T12)
│   ├── evidence_lint.py                # (T13)
│   ├── verify_report.py                # (T13)
│   ├── spotcheck.py                    # (T13)
│   ├── regression_check.py             # (T13)
│   ├── doctor.py                       # (T14)
│   └── fallback/
│       ├── registry.py                 # (T10)
│       ├── launch.py                   # (T10)
│       ├── record.py                   # (T10)
│       ├── fake_experiment.py          # (T10)
│       └── fake_metrics.py             # (T10)
└── tests/
    ├── run_all.py                      # (脚手架) stdlib 跑器
    ├── helpers.py                      # (T02) 沙盒工厂 + 行工厂 + run_ledger()
    ├── test_lib.py                     # (T02)
    ├── test_genschemas.py              # (T03)
    ├── test_config.py                  # (T04)
    ├── test_blocked_decisions.py       # (T05)
    ├── test_story_feedback.py          # (T06)
    ├── test_runs_principles.py         # (T07)
    ├── test_launch_order.py            # (T08)
    ├── test_query_status.py            # (T09)
    ├── test_fallback.py                # (T10)
    ├── test_trace_check.py             # (T11)
    ├── test_output_error.py            # (T12)
    ├── test_oversight.py               # (T13)
    ├── test_doctor.py                  # (T14)
    └── test_e2e.py                     # (T16) 九场景
```

## 共用契约（工单间接口，签名照抄不许改）

### C1 `_lib.py` API（T02 产出，全体消费）

```python
plugin_root() -> Path            # scripts/ 的上一级
load_tables() -> dict            # {"ledgers","rows","writes","config","routes"} 五表
find_project_root(start=None) -> Path | None   # 向上找 research-loop.json
load_config(root) -> Config
# Config.data: dict; Config.get(key): 键缺省取 tables/config.json 的 plugin 默认
#   （runtime_factor=3, roles={"inspector_model":"opus","reader_model":"sonnet"},
#    standing_authorization={"max_expected_runtime_s":3600,"resource":"compute"},
#    inspection_policy="always"）
# Config.ledger_path(name) -> Path   # config.ledgers 覆盖 > tables/ledgers.json default_path，相对 root 解析
# Config.null_locked(key) -> bool    # 该键是否为 null/缺失

class RLError(Exception)         # .message 即成品文案；CLI 捕获后 stderr 打印、exit 2
fail(ledger, field_path, msg, value=_MISSING) -> NoReturn
# raise RLError(f"{ledger}.{field_path}: {msg}" + (f" (got: {value!r})" if given))

locked(path: Path)               # with locked(p): ... ; flock EX on str(p)+".lock"
jsonl_rows(path, include_archive=False) -> list[dict]   # 文件缺 -> []
jsonl_append(path, row)          # 调用方持锁；一行一 json.dumps(ensure_ascii=False)
inplace_update(path, key_field, key_value, updates: dict, whitelist: set) -> dict
# 越白名单字段 -> fail(); 行不存在 -> fail(); 临时文件 + os.replace 原子换
alloc_id(rows, id_field, prefix) -> str    # 前缀+3位零填充 max+1（D001；超999自然进位 D1000）
now_iso() -> str                 # 秒级 ISO；env RL_FAKE_NOW 存在则用它（测试钩子）
today() -> str                   # YYYY-MM-DD，同上

load_schema(name) -> dict        # 读 plugin schemas/<name>.schema.json
validate(row, schema, ledger) -> None      # 语义见 C3
run_argv(argv, cwd=None, timeout=None) -> (exit_code, stdout, stderr, elapsed_s)
split_cmd(cmd, ledger, field) -> list[str] # shlex.split；含 '|' 或换行 -> fail()
last_json_line(stdout) -> dict | None      # 最后一个非空行 json.loads 成 dict，否则 None
registry_tasks(cfg) -> list[str] | None    # 跑 registry_query，一行一个任务名；registry_query 为 null -> None
check_in_registry(argv: list[str], cfg, *, ledger, field) -> str
# 校验 shlex.split(registry_cmd) 是 argv 前缀、其后首 token 即任务名、任务在
# registry_tasks() 清单；registry_query 为 null -> fail(...“registry_query not wired”)
# 返回任务名。launchcmd 与 principlescmd、trace_check 三处共用这一个函数。
parse_frontmatter(text) -> (dict, str)     # ---定界头；值先试 json.loads，失败按原样字符串
spec_digest(path) -> str         # sha256(第二条 '---' 行之后的原始字节)（rows.json spec_header._digest_rule）
git_head(root) -> str            # HEAD sha；脏树加 "-dirty"；非 git 仓库 -> "no-git"
```

### C2 ledger.py CLI 面（分发器 T03 定死，模块各自实现）

```
ledger.py gen-schemas [--check]
ledger.py config-check [--root PATH]
ledger.py init [--root PATH] [--non-interactive] [--set key=JSON ...] [--force]
ledger.py blocked open   --layer L --to-layer T --kind K --ref REF --question Q
                         --evidence E1 [E2 ...] [--where W] [--options O1 O2 ...]
ledger.py blocked answer --layer L BID --answer TEXT [--answered-by user]
                         [--chosen V] [--grant DID]
ledger.py blocked close  --layer L BID
ledger.py blocked withdraw BID --reason TEXT              # 不收 --layer（撤销代笔）
ledger.py grant    --layer L --question Q --reason TEXT --scope-desc D
                   --scope-globs G1 [G2 ...] [--expires ISO]
ledger.py decision --layer L --question Q --options O1 [O2 ...] --chosen V
                   --reason R --where W --authorized-by A
                   [--decided-by user|agent] [--principle-ref P] [--affects X ...]
ledger.py decision-withdraw DID --reason TEXT [--superseded-by DID2]   # 不收 --layer
ledger.py story add --layer idea --claim C --evidence-runs R1,R2
                    --baseline-runs .. --candidate-runs .. [--metric-names m1,m2]
                    --selection-rule S --derivation-command CMD
                    --principle-id P --role ROLE
ledger.py story retire SID --reason TEXT [--superseded-by SID2]        # 不收 --layer
ledger.py feedback add --layer L --context C --problem P --suggestion S
ledger.py feedback review --layer user --ref FID --verdict accepted|rejected [--note N]
ledger.py runs-append --layer deploy --principle PID
ledger.py launch-order --layer deploy --file DRAFT.json
ledger.py approve-spec SPECFILE --by NAME
ledger.py query LEDGER [--batch B] [--run R] [--spec-item S] [--since ISO]
                       [--metric M] [--status ST] [--to-layer L] [--kind K]
                       [--all-rows] [--include-archive]
ledger.py status --layer L
ledger.py principles-lint [--file PATH]
ledger.py render principles|blocked        # 维护/渲染动作不收 --layer（writes.json maintenance_exempt）
ledger.py freeze-legacy --confirm          # 不收 --layer
```

`--layer` 取值域 = `tables/writes.json` layer_param（idea|deploy|run|oversight，
user 只有 feedback review 收）。所有子命令跑前先做 config-check 快查
（Config 缺失 = 未接线，除 gen-schemas/init 外一律拒；被 null 锁的功能按
`tables/config.json` null_effect 拒并点名是哪个 null 键）。

### C3 校验语义（validate 单入口）

按生成的 schema 检查：required 齐全；additionalProperties=false 拒生字段；
type（联合数组按任一命中；bool 不算 integer）；enum / const；integer 的 minimum；
array 逐元素查 items。conditional 语义：

- `when`（对象或对象数组，数组=全部成立）：op ∈ eq|neq|in，字段缺按 None 比。
- `require`: 条件成立时字段必须**存在且非 null**。
- `allow_null`: 被任何 allow_null 条目列名的字段，**只有**在至少一条列它的
  conditional 成立时才许为 null；没被任何 allow_null 列名的字段，可空性只看 type。
  （例：runs 普通行 metric_name 列在 status≠ok 的 allow_null 里 → status=ok 时
  非空硬性；filter 没被列 → 按 type 恒可空。）

### C4 生成物形态（gen-schemas）

八块 → 八文件（块名→文件名）：story_row→story、decisions_row→decisions、
blocked_row→blocked、feedback_rows.suggestion→feedback.suggestion、
feedback_rows.review→feedback.review、runs_row_normal→runs.normal、
runs_row_criterion→runs.criterion、launch_order→launch_order（后缀 .schema.json）。
变换：`$enum` 就地展开成 `{"enum": [...]}`；`$ref_to` 原样保留（注解，校验器不读，
存在性归 trace_check）；`const`/`type`/`items`/`minimum` 照搬；`_note` 与其余
文档键（rows.json `_doc_keys`）**丢弃**（生成物不携带散文，说明留在表里——
这是英文本体与中文表的边界处理，已记自决点）。顶层键：
`$comment`(固定一句 generated-by + DO NOT EDIT)、`ledger`、`primary_key`、
`type:"object"`、`required`、`additionalProperties`、`properties`、`conditional`。
`owners.default.json` = ledgers.json 主表（不含 optional_ledgers）的 {账名: owner}。
序列化统一 `json.dumps(x, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`。

### C5 fallback 台账（jobs）最小形态

`ops/jobs.json` = `{run_id: {launch_order_ref, state, started_at, finished_at,
log_path, escalation_ref, sampler}}`，state ∈ running|done|failed|timeout。
statuscmd 的 jobs 读法要宽容：dict 或 list 都收，认 run_id/name 键与
state/status 键（新 1 真台账是另一种形状，挂接期不改它）。

### C6 报告体裁机验约定（oversight 三件与 SKILL.md 共用）

- 复现命令行 = 以 `$ ` 开头的行；其后紧邻的 `= <值>` 行是申报的命令输出值。
- evidence_lint 的"有数字无复现命令"：含数字的散文行，向下 3 行内没有 `$ ` 行
  即违规；豁免面按 `tables/rows.json` evidence_lint_exempt（ISO 时间戳、
  ≥7 位十六进制、`path:line` 形态、YYYY-MM-DD、id 形态 [A-Z]\d{3}、
  frontmatter 的 verdict/rejections/withdrawals 字段行）。
- 违禁结论词表（中英双语，正文行查、frontmatter 枚举字段豁免）：
  通过 / 没问题 / 符合预期 / passed / looks good / no problems / as expected /
  all good / everything is fine。
- verify_report 认三样：`path:line` 引用（stat + 行存在）、路径引用后的
  `> ` 摘录行（原文回比）、`$ cmd` + `= 值`（重跑回比，数值按 == 比，浮点 1e-9）。

## 工单一览（Blocked by 图）

| 工单 | 内容 | Blocked by |
|---|---|---|
| T02 | `_lib.py` + helpers.py + test_lib | — |
| T03 | ledger.py 分发器 + gen-schemas + schemas/ 生成落盘 | 02 |
| T04 | config-check + init | 03 |
| T05 | blocked 全跃迁 + r5 拼装 + grant/decision + R6 | 03 |
| T06 | story + feedback | 03 |
| T07 | runs-append + principles-lint + render principles | 03 |
| T08 | launch-order + approve-spec + affects 回填 | 03, 05 |
| T09 | query + status + render blocked | 03 |
| T10 | fallback 五件 + freeze-legacy | 03 |
| T11 | trace_check | 03 |
| T12 | output_check + error_classify | 02 |
| T13 | evidence_lint + verify_report + spotcheck + regression_check | 03 |
| T14 | doctor | 04, 07, 09, 11, 13 |
| T15 | 五个 SKILL.md + references + inspector agent（英文） | 04, 05, 06, 07, 08, 09 |
| T16 | 九场景 e2e 自测 | 04, 05, 06, 07, 08, 09, 10, 11, 12 |

波次预估：W1={02}，W2={03,12}，W3={04,05,06,07}，W4={08,09,10,11}，
W5={13,15,16}，W6={14}。

## §V 验证循环（实施完成后，主会话直接执行，不进工单）

用户要求原文："派出几个小的agent试着加载审核这些skill隔离验证每一层的功能
都无误，层之间的通信协议一直可靠。"

- **V0 机械门禁**：`python3 spec_lint.py` 全绿；`ledger.py gen-schemas --check`
  全绿；`tests/run_all.py` 全绿。不绿不进 V1。
- **V1 分层隔离加载**：每个 skill 一个 subagent（模型 sonnet，模拟"天真执行者"），
  上下文只给：该层 SKILL.md 路径 + 一个沙盒工程目录（tests/helpers.py 造，
  预埋若干账目）。指令：照 SKILL.md 字面执行开工动作和两三件本层典型动作，
  逐条报告哪里含糊、哪条命令失败、哪里被迫读了不该读的上下文。
- **V2 通信协议接力**：一条链多个 subagent（sonnet），每个只知道自己层的
  SKILL.md 与沙盒路径，任务细节零传递——一切靠落盘账本接力：
  部署层写发射单 → 运行层用 fallback 铁轨发射+记账 → 运行层撞 fail 开
  blocked → 部署层 status 看到、answer → r5-choice 链拼 decision →
  idea 层 story 裁决入账。收尾机验：trace_check 全绿 + 每一跳的输入只来自盘上。
- **V3 越权探针**：sonnet agent 按清单试非法动作（--layer 传错、跳层升级、
  quick 行进 story、脏字段就地更新、绕过滤读全表），全部必须被机器拒绝。
- **裁断**：V1–V3 的发现由 opus agent 复核（对抗式：先试图驳回），确认的
  回修（小修主会话直接改，大修开补丁工单再走 ticket-run），循环到连续一轮零发现。

## 范围外（本轮不做）

- new1 挂接七项（spec §9 挂接清单）：动真铁轨（record.py 行型改造、freeze-legacy
  实跑、METHOD.md 改造、RESULTS 渲染器），按 spec 要求逐项过 R5，等用户点头。
- spec.en.md 同步、机器级安装（拷贝/软链到 ~/.claude）、archive 执行件（v1.1）。
