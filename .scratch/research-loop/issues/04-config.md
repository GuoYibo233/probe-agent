# T04 config-check + init

Status: ready-for-agent
Blocked by: 03

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + `research-loop/tables/config.json`（键表、`_null_lock_rule`、
`_fallback_rule`）+ `tables/ledgers.json`（`_cap_rules`）+
`tables/writes.json`（owner_values 九值）+ spec.md §7、§9 config-check 条。

## 文件

- Create: `research-loop/scripts/ledger_cmds/configcmd.py`
- Create: `research-loop/tests/test_config.py`

## 要求

### config-check [--root PATH]

结构性错误（任一命中 exit 1，格式 `config.<键路径>: <说明> (got: ...)`）：

1. `ledgers` 键集与 `owners` 键集必须严格相等。
2. `ledgers` 每个键必须在 tables/ledgers.json 主表或 optional_ledgers 里；
   主表每个键必须出现在 config.ledgers（严格相等 + 可选账挂了才多）。
   归档伴生名（含 `.archive.` 的值/键）拒。
3. `owners` 值必须在 writes.json owner_values 九值里。
4. `ledger_caps`：键 ⊆ ledgers 键且对应账 format=jsonl；`runs`/`runs_legacy`
   只许 null；非 jsonl 账设 cap 拒。
5. `inspection_policy` 只收 `always`（v1 值域）。

null 报告（不是错误，exit 0 时也打印）：逐个 null/缺失键打一行
`null key <key> -> locks: <null_effect>`（null_effect 文案从 tables/config.json
的 null_effect 列取，照抄）。roles/standing_authorization/runtime_factor 为
null 打 `-> default: <plugin默认>`。

### init [--root PATH] [--non-interactive] [--set key=JSON ...] [--force]

- 已有 research-loop.json 且无 `--force` → exit 1 `config exists (use --force)`。
- 生成骨架：`ledgers` 全键取 tables/ledgers.json default_path（optional 不进）；
  `owners` 从 `schemas/owners.default.json` 抄（**自动生成不询问**）；其余键：
  `--set key=JSON` 给了用给的（值过 json.loads，失败按字符串），没给留 null。
- 交互模式（默认）：逐键 `input()` 问（提示带 example 列），空回车 = null。
  `--non-interactive` 跳过全部询问。
- 产物写盘后自动跑一遍 config-check，结构必须过（"init 产物直接过"）。

## 测试（test_config.py）

1. `init --non-interactive` → config-check exit 0；owners 键集 == ledgers 键集。
2. init 后再 init 无 --force → exit 1；--force 放行。
3. 手动把 owners 里删一键 → config-check exit 1 点名键集不等。
4. owners 某值改成 `"nobody"` → exit 1 且文案含九值域提示。
5. `ledger_caps` 加 `{"principles": 100}`（md 账）→ exit 1；
   `{"runs": 500}` → exit 1（runs 只许 null）；`{"blocked": 500}` → 过。
6. registry_cmd 置 null → config-check exit 0 但输出含
   `null key registry_cmd` 与其 null_effect 原文。
7. `--set registry_cmd='"python3 x.py"'` 生效为字符串。
8. config.ledgers 塞一个 `"foo": "x.jsonl"` → exit 1（表里没有的账名）。

## Comments
