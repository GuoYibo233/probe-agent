# T04 config-check + init -- 实现报告

工单：`.scratch/research-loop/issues/04-config.md`
分支：`ticket/20260814-wave3/T04`（工作树 `new1-wt/20260814-wave3-T04`，已删除）
base：`6cce8bc9eef192110ae8343c32ea89d5f2a00302`
head：`5f12e54ec699821444c810a340f967a1243cc187`

## 做了什么

新建两个文件，均在 `research-loop/` plugin 内，不改 `run.py`/`MAP.md`：

- `research-loop/scripts/ledger_cmds/configcmd.py`
- `research-loop/tests/test_config.py`

### config-check [--root PATH]

`register(subparsers)` 挂两个子解析器（`config-check`、`init`），`run(args)` 按
`args.command` 分流——这是 ledger.py 分发器已有的"一个模块多个子命令"协议
（`_SUBCOMMAND_MODULES` 里 `config-check`/`init` 都指向 `configcmd`），照抄
`genschemas.py` 的模块协议（`register`+`run`）。

结构性检查按工单给的五条顺序实现，任一命中立即 `fail()`（`_lib.fail` 产出
`config.<键路径>: <说明> (got: <value>)` 格式，每条都带 value 参数保证
"(got: ...)" 后缀必现）：

1. `ledgers` 键集与 `owners` 键集严格相等——不等时报对称差集（点名具体哪些键）。
2. `ledgers` 每个键须在 `tables/ledgers.json` 主表或 `optional_ledgers`；主表
   每个键须出现在 `config.ledgers`；键或值含 `.archive.` 子串一律拒（先查
   archive 再查未知名，同一个 key 上 archive 检查先触发，不会被"未知账名"
   分支抢先报出，见测试 9）。
3. `owners` 值须在 `tables/writes.json` `owner_values` 九值域内，报错文案里把
   九值域全列出来。
4. `ledger_caps`：键须是已知账名（主表∪optional）；`runs`/`runs_legacy` 只许
   `null`；其余键对应账 `format` 须是 `jsonl`，否则拒。
5. `inspection_policy`：非 null 时只收 `"always"`（v1 值域）；null 本身不算
   结构错误，留给下面的 null 报告处理。

结构通过后打印 null 报告：遍历 `tables/config.json` 的 18 个顶层键（含
`rails.build` 等含点的字面字符串键，跟 `helpers.make_sandbox()` 已有的用法
一致，不是嵌套 dict），`cfg.null_locked(key)`（缺失或显式 null）为真的逐行打
`null key <key> -> locks: <null_effect 原文>`；`roles`/
`standing_authorization`/`runtime_factor` 三个键改打
`null key <key> -> default: <cfg.get(key) 的 JSON>`（`cfg.get()` 已经把
`_lib.py` 里的 plugin 默认值算出来了，不用在 configcmd 里再抄一份默认表）。

结构错误走本模块内部捕获，`config-check` 命令本身 exit 1（不是 `RLError`
冒泡到 dispatcher 后的 exit 2）——工单明确要求 exit 1，`ledger.py` 顶层的
`except RLError` 是给"调用方式错了"这类问题用的 exit 2，两者语义不同，所以
在 `_run_config_check`/`_run_init` 里各自 `try/except RLError` 后 `return 1`。

`--root` 未给时用 `_lib.find_project_root()`（从 cwd 向上找），找不到就退回
cwd 本身（保证总有个路径可以拼进"config not found: <path>"消息，不是 None）。
research-loop.json 完全不存在时打印 `config not found: <path> (run: ledger.py
init)` 到 stderr，exit 1（工单没点名这条但 config-check 被 dispatcher 排除在
"未接线拒绝"门禁外，意味着它必须自己稳妥处理"配置压根不存在"这个状态，不能
崩；补了测试 11）。

### init [--root PATH] [--non-interactive] [--set key=JSON ...] [--force]

- 已存在且无 `--force` → stderr `config exists (use --force)`，exit 1；
  `--force` 放行（不合并旧内容，直接整份重新生成骨架覆盖，"放行"按字面读作
  "让写入这一步通过"）。
- `--root` 不做向上查找（跟 `config-check` 不同）——init 是"在这里新建一个
  工程"的动作，向上找到别的工程的 research-loop.json 再往那边写会是很危险
  的行为，所以固定用 `--root` 或 cwd 本身，不查祖先目录。
- 骨架：`ledgers` 取 `tables/ledgers.json` 主表每键的 `default_path`（
  `optional_ledgers` 不进）；`owners` 直接读
  `research-loop/schemas/owners.default.json`（T03 gen-schemas 已生成、随仓
  库提交的文件），不问、不由 `--set` 覆盖；其余键：`--set key=JSON` 给了用
  给的值（`json.loads`，失败退回原始字符串——`--set registry_cmd='"python3
  x.py"'` 这种带引号的 JSON 字符串字面量会被解出来变成 Python 字符串
  `"python3 x.py"`，验证见测试 7），没给且非 `--non-interactive` 时逐键
  `input()` 问（提示里带 `tables/config.json` 该键的 `example`），空回车留
  `null`；`--non-interactive` 整段跳过，未被 `--set` 覆盖的键一律留 `null`。
- 写盘（`json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)`，跟
  `tests/helpers.py` 里 sandbox 写法一致的格式）后，内部直接调用
  `_check_structure`（跟 config-check 共用同一个函数，不是拉子进程重新跑一遍
  `ledger.py config-check`）验证结构、打印 null 报告——工单"产物写盘后自动跑
  一遍 config-check，结构必须过"这条按"复用同一段校验逻辑"实现，不是真的开
  子进程；语义等价，省一次进程开销也避免两份校验逻辑分叉。

## 怎么验证的

`tests/test_config.py` 11 条，覆盖工单列的全部 8 条 + 3 条自补边界：

```
$ python3 research-loop/tests/run_all.py test_config
PASS test_config.test_archive_companion_name_in_config_ledgers_rejected_specifically
PASS test_config.test_config_check_with_no_config_file_exits_1
PASS test_config.test_init_non_interactive_then_config_check_is_clean_and_key_sets_match
PASS test_config.test_init_twice_without_force_rejected_with_force_allowed
PASS test_config.test_interactive_init_skips_set_keys_blank_is_null_non_blank_is_parsed
PASS test_config.test_ledger_caps_rejects_non_jsonl_and_runs_cap_allows_jsonl
PASS test_config.test_null_registry_cmd_reported_with_verbatim_null_effect
PASS test_config.test_owners_bad_value_fails_config_check_and_lists_the_nine_values
PASS test_config.test_owners_missing_a_key_fails_config_check_naming_the_mismatch
PASS test_config.test_set_flag_with_quoted_json_string_becomes_a_plain_string
PASS test_config.test_unknown_ledger_name_in_config_ledgers_fails_config_check
-- run_all: 11 passed, 0 failed
```

工单 8 条 ↔ 测试对照：

| 工单条目 | 测试函数 |
|---|---|
| 1 init 非交互→config-check 0，owners=ledgers 键集 | `test_init_non_interactive_then_config_check_is_clean_and_key_sets_match` |
| 2 二次 init 无/有 --force | `test_init_twice_without_force_rejected_with_force_allowed` |
| 3 删 owners 一键→键集不等 | `test_owners_missing_a_key_fails_config_check_naming_the_mismatch` |
| 4 owners 值改 nobody→九值域提示 | `test_owners_bad_value_fails_config_check_and_lists_the_nine_values` |
| 5 ledger_caps 三种取值 | `test_ledger_caps_rejects_non_jsonl_and_runs_cap_allows_jsonl` |
| 6 registry_cmd=null→null 报告 | `test_null_registry_cmd_reported_with_verbatim_null_effect` |
| 7 --set 带引号字符串 | `test_set_flag_with_quoted_json_string_becomes_a_plain_string` |
| 8 config.ledgers 塞未知账名 | `test_unknown_ledger_name_in_config_ledgers_fails_config_check` |

自补 3 条（implementer.md："没点名就在你改动的边界处补测试"）：

- `test_archive_companion_name_in_config_ledgers_rejected_specifically`：工单
  要求 2 里"归档伴生名拒"单独有一条判断逻辑（跟"未知账名"是两条不同分支），
  两者都会命中同一个坏 key，需要确认真正触发的是 archive 分支（断言消息文本
  是 "archive companion name is not a ledger"，不是 "not a known ledger"）。
- `test_interactive_init_skips_set_keys_blank_is_null_non_blank_is_parsed`：
  交互 input() 分支工单要求要实现但列出的 8 条测试都用 `--non-interactive`，
  没人验证过它；用 `builtins.input` 打桩验证空回车留 null、非空按
  json.loads/字符串解析、已被 --set 回答的键不再问。
  直接在进程内调 `configcmd._run_init(SimpleNamespace(...))`，不经子进程
  （子进程模式没法喂 input() 的桩）。
- `test_config_check_with_no_config_file_exits_1`：config-check 被 dispatcher
  排除在"未接线拒绝"门禁之外，意味着它必须自己稳妥处理配置完全不存在这个
  状态；工单没点名但这是 config-check 的一条可达路径，不测就是没验证过的
  代码路径。

之后跑了全量套件确认没有连带破坏：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 69 passed, 0 failed
```

`selfcheck` 未跑：本工单没有改动 `run.py` 注册表（工单范围声明本身就写明
"不改 run.py / MAP.md"），实现者规程里"改了 run.py 注册表相关的东西才跑
selfcheck"这条不适用。

## commit 清单

- `5f12e54` `T04: research-loop plugin -- ledger.py config-check + init` ——
  新增 `configcmd.py` + `test_config.py`，一次提交（结构检查+null 报告+init
  骨架生成是同一个功能面，没有再拆的自然边界）。

## 自查发现与存疑

- **结构检查 1 的报错锚点**：键集不等时消息固定挂在 `config.owners`（不管是
  `ledgers` 多还是 `owners` 多），理由是"owners 应该镜像 ledgers"这个方向性
  更自然（工单里 owners 是从 ledgers 派生：`init` 自动生成 owners 就是照抄
  ledgers 键集）。工单原文只说"点名键集不等"，没规定报错锚在哪一侧、要不要
  分别列出"多了什么/少了什么"两个集合——我用对称差集（`sorted(a ^ b)`）一次
  性列出所有不同的键，没有分别标注"这个键 ledgers 有 owners 没有"还是反过来。
  如果验收者期望更明确的"missing/extra"双向措辞，这里需要改。
- **inspection_policy 的 null 报告文案有点别扭**：它不在
  `roles`/`standing_authorization`/`runtime_factor` 那三个"default:" 特例
  里（工单原文明确只点名这三个），所以走的是通用分支，打出来是
  `null key inspection_policy -> locks: 取默认 always`——"locks:" 后面接的
  是"取默认 always"这句本来是描述默认值而非"锁什么"的文案，读起来有点拧巴。
  这是照抄 `tables/config.json` 原文的必然结果（工单："null_effect 文案...
  照抄"），不是我引入的不一致，但验收时如果观感上过不去，需要回 spec 改
  `inspection_policy` 的 null_effect 措辞或者把它也并入三键特例，这两个都
  超出本工单能自行拍板的范围，没动。
- **config-check 对"配置完全不存在"的处理是我自己扩的**：工单只给了"结构性
  错误 exit 1"和"null 报告 exit 0"两条路径，没写"文件压根不存在"该怎么办。
  我按跟 dispatcher 主 gate 消息同一个文风（"xxx not found (run: ...)"）自己
  定了 `config not found: <path> (run: ledger.py init)` / exit 1，并补了
  测试。这属于工单没点名但代码可达、需要有确定行为的分支，按实现者规程
  "没点名就在你改动的边界处补测试"处理，没有回问用户；如果验收者认为这个
  分支该有不同的文案或退出码，是可以讨论的点。
- 没有发现需要 `NEEDS_CONTEXT` 或 `BLOCKED` 的缺口：工单给的数值/命名/接口
  签名（`--root`/`--non-interactive`/`--set`/`--force`、五条结构检查、null
  报告两种格式、八条测试）都是完整、不矛盾的，没有需要用户裁决的地方。

## 修复第 1 轮（3 条 findings）

分支：`ticket/20260814-wave3/T04`（工作树
`new1-wt/20260814-wave3-T04-fix1`，已删除，检出已有分支非新建）
base（修复前 head）：`5f12e54ec699821444c810a340f967a1243cc187`
head：`412771ee6cb4cbac0df67d06c0bd2f488a66baed`

### F1（critical）：ledger_caps 键校验域来源不一致——已修

**怎么修的**：`configcmd.py` `_check_structure` 第 4 条检查里，键存在性
判断从 `known_ledger_names`（`tables/ledgers.json` 主表 ∪ optional_ledgers
的静态全集）改成 `ledgers_keys`（`cfg.data.get("ledgers")` 解出来的
config.ledgers 实际键集，检查 1 已经算过、复用同一个变量）。理由跟
finding 一致：工单要求 4 的裸词"ledgers"沿用要求 1 里"ledgers = config
文件里的 ledgers 字段"这个措辞习惯，不是指静态表全集；未挂接的 optional
账（当前唯一一个是 `runs_legacy`）在没被挂进 config.ledgers 之前，不该
被允许出现在 ledger_caps 里，即便给的值是 null（满足 runs/runs_legacy
只许 null 那条子规则）。`format=jsonl` 的账类型判断仍然要查
`tables/ledgers.json`（config.ledgers 本身只有路径没有 format 字段），
这部分逻辑没动——检查 2 已经保证走到检查 4 时，config.ledgers 里的每个
键都在主表或 optional 表里能查到 format，所以查表安全。

补了一条回归测试
`test_ledger_caps_rejects_a_ledger_name_not_hooked_into_config_ledgers`：
`init --non-interactive` 后 config.ledgers 不含 `runs_legacy`（optional
账未挂接），塞 `ledger_caps: {"runs_legacy": null}`，断言 config-check
exit 1 且消息含 `config.ledger_caps.runs_legacy` 与 `key is not a known
ledger`——改之前这个用例会以 exit 0 静默放行。

### F2（important）：三个 default 键的 null 报告格式无测试断言——已修

**怎么修的**：没有改产品代码（这条本身就是"代码对但没测过"），补测试
`test_null_report_shows_plugin_default_for_roles_and_runtime_factor_and_standing_authorization`：
`init --non-interactive` 后对 `roles`/`standing_authorization`/
`runtime_factor` 三键逐一断言 config-check stdout 里出现
`null key <key> -> default: <cfg.get(key) 的 json.dumps 原文>`
这一整行，并且反向断言这三键不出现通用分支的 `-> locks:` 前缀，确认真
正命中的是 `_DEFAULTED_KEYS` 分支而不是普通分支侥幸凑出相似文本。

### F3（important）：--root PATH 两条命令均零覆盖——已修

**怎么修的**：没有改产品代码，补三条测试：

- `test_root_flag_for_config_check_is_used_regardless_of_cwd`：cwd 设成
  跟项目毫无祖先关系的另一个目录，显式传 `--root <project_root>`，断言
  exit 0——验证 `_root_by_walking_up` 的"给了 --root 直接用"分支。
- `test_config_check_walks_up_from_a_subdirectory_without_root_flag`：不
  传 `--root`，cwd 设成 `root/a/b`（真正的项目子孙目录，不是 cwd==root
  这种平凡情形），断言 exit 0——验证 `_lib.find_project_root()` 真的会
  向上走出子目录找到 research-loop.json。
- `test_root_flag_for_init_writes_at_given_root_not_cwd`：cwd 和
  `--root` 目标目录设成两个不相关目录，`init --non-interactive --root
  <target>`，断言配置文件写在 target 底下、cwd 底下没有——验证
  `_root_for_init` 用的是 `--root` 而不是 cwd，且（跟 config-check 不
  同）确实不做向上查找。

### 怎么验证的

```
$ python3 research-loop/tests/run_all.py test_config
PASS test_config.test_archive_companion_name_in_config_ledgers_rejected_specifically
PASS test_config.test_config_check_walks_up_from_a_subdirectory_without_root_flag
PASS test_config.test_config_check_with_no_config_file_exits_1
PASS test_config.test_init_non_interactive_then_config_check_is_clean_and_key_sets_match
PASS test_config.test_init_twice_without_force_rejected_with_force_allowed
PASS test_config.test_interactive_init_skips_set_keys_blank_is_null_non_blank_is_parsed
PASS test_config.test_ledger_caps_rejects_a_ledger_name_not_hooked_into_config_ledgers
PASS test_config.test_ledger_caps_rejects_non_jsonl_and_runs_cap_allows_jsonl
PASS test_config.test_null_registry_cmd_reported_with_verbatim_null_effect
PASS test_config.test_null_report_shows_plugin_default_for_roles_and_runtime_factor_and_standing_authorization
PASS test_config.test_owners_bad_value_fails_config_check_and_lists_the_nine_values
PASS test_config.test_owners_missing_a_key_fails_config_check_naming_the_mismatch
PASS test_config.test_root_flag_for_config_check_is_used_regardless_of_cwd
PASS test_config.test_root_flag_for_init_writes_at_given_root_not_cwd
PASS test_config.test_set_flag_with_quoted_json_string_becomes_a_plain_string
PASS test_config.test_unknown_ledger_name_in_config_ledgers_fails_config_check
-- run_all: 16 passed, 0 failed
```

（原 11 条 + 补 5 条：F1 回归 1 条、F2 断言 1 条、F3 覆盖 3 条 = 16 条。）

全量套件确认无连带破坏：

```
$ python3 research-loop/tests/run_all.py
...
-- run_all: 74 passed, 0 failed
```

（原 69 条 + 新增 5 条 = 74 条，全绿。）

`selfcheck` 未跑：本轮改动没碰 `run.py` 注册表，跟第一轮同样理由不适用。

### commit 清单

- `412771e` `T04: fix ledger_caps key domain; add null-report and --root
  coverage` —— `configcmd.py` 改 3 行（F1 修复）+ `test_config.py` 补 5
  条测试（F1 回归 + F2 + F3 三条），一次提交。

### 自查发现与存疑

- F2、F3 都是"补测试，不改产品代码"——自查过 `configcmd.py` 现有实现
  在这两条 finding 描述的分支下行为本身没问题（三键 default 分支文案
  正确、`--root` 两个函数逻辑本来就分别处理了显式给值和默认值两种情况），
  findings 指出的缺口纯粹是测试覆盖缺口，所以没有产品代码改动。
- F1 修复后重新过了一遍第一轮报告里"自查发现与存疑"那三条遗留点
  （结构检查 1 报错锚点固定在 `config.owners`、`inspection_policy` 的
  null 报告文案挂在通用 `locks:` 分支下读起来别扭、"配置完全不存在"是
  自行扩展的行为）——这三条跟本轮三个 findings 无关，且都需要验收者或
  用户裁决（不是实现细节），本轮没有动它们，留给下一轮或用户决定。
