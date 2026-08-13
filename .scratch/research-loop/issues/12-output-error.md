# T12 output_check.py + error_classify.py（运行层两件）

Status: claimed
Blocked by: 02

## 范围声明

research-loop plugin 件，不改 run.py / MAP.md；英文、纯 stdlib。需求源：
本工单 + spec.md §4 两脚本注释、R8 + `tables/rows.json`
（launch_order.expected_outputs 形状、error_classes `_shape`）。

## 文件

- Create: `research-loop/scripts/output_check.py`
- Create: `research-loop/scripts/error_classify.py`
- Create: `research-loop/tests/test_output_error.py`

## 要求

### output_check.py --launch-order PATH

对发射单 expected_outputs 逐条比（每条
{path_glob, min_bytes?, min_lines?, required_keys?[]}）：

- glob 相对 artifact_dir 解析；无命中 → 该条 `missing-output`。
- 命中的每个文件：字节数 < min_bytes → `empty-output`；行数 < min_lines →
  `empty-output`；required_keys 非空 → 文件首个非空行按 JSON 解析、
  缺任一键 → `empty-output`（解析失败也算）。
- verdict 优先级：任一 missing-output → missing-output；否则任一
  empty-output → empty-output；否则 ok。
- stdout 尾行单个 JSON：`{"verdict": ..., "failures": [{glob, file, why}]}`；
  verdict=ok → exit 0，否则 exit 4。
- **实验进程退出码 0 + 产物空 → 本脚本给 empty-output**（§9：不得记 ok）。

### error_classify.py --error-classes PATH [--exit-code N] [--log PATH] [--output-check V]

- 分类表 JSON：`{规则名: {"match": {exit_code?|log_regex?|output_check?},
  "action": "retry"|"swap-card"|"escalate"}}`，按文件里的键序逐条试。
- 一条规则里给了几个 match 键就 AND 几个：exit_code 数值等；log_regex 对
  --log 文件全文 re.search；output_check 字符串等于 --output-check。
- 第一条全中的规则 → stdout 尾行 `{"rule": 名, "action": 动作}`，exit 0。
- 全不中 → `{"rule": null, "action": "unknown"}`，exit 0——**不猜**，
  升级动作归调用方（R8：运行层只机械升级）。

## 测试（test_output_error.py）

1. output_check：产物齐全 → ok exit 0；文件在但 0 字节 → empty-output
   exit 4；glob 无命中 → missing-output；required_keys 缺键 → empty-output；
   min_lines 不足 → empty-output。
2. 三类特征各一条规则命中正确动作（§9）：exit_code=137 → 规则 oom-kill →
   swap-card；log 里有 `CUDA out of memory` → retry；
   output_check=empty-output → escalate。
3. exit_code 和 log_regex 同给且只中一个 → 不算命中（AND 语义）。
4. 全不中 → action=unknown，rule=null。

## Comments
