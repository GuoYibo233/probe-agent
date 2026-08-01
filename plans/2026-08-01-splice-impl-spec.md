# 拼回实验实现规格（实现与审查的合同）

上游定稿：`plans/2026-08-01-splice-settings.md`。本文件把它翻译成可执行的代码改动清单，
字段名/臂名/常量在此钉死，实现与审查都以本文件为准。

## 前置事实（侦察已核实，行号基于 2026-08-01 05:13 版 replay_inject.py，936 行）

- replay_fire 156-173：`pred` 只出现在 167（赋值）和 169（算 ok），rec 不存；label2id 在 244 行读入（方向：工具名→id）。
- gen_calls 176-213：generate 在 202，无 output_scores；207 行截首行。
- miss_policy 分发 299-310；plan 记录构造 313-330；plan_config 336-351。
- run 段：one() 565-602；arm 唯一分叉 579-581；prompt 拼接 582；dry-run 583-590；
  arms 解析 536；todo 过滤 549-551；NO_INJECT 定义 141；断点续跑键 (event, arm) 542-548。
- score 段：cmd_score 640-862；split_channels 632-637；FINAL_OPEN 134；CODE_RE 122；
  first_api_call 216-219；nofill 当省 token 分母 656-657；saved 计算 675-677。
- ctool 工件在 NFS：`/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/pipeline/runs/c1_gptoss_ctool/`
  （本地 c2_* 是 alfworld 的，别碰）。temperature=1.1923，chosen_theta={0.1:0.925, 0.05:0.975}。
- **分词器铁律（实测 6/6）**：骨架一律**不带尾左括号**——`print(apis.venmo.login(` 的尾 `(`
  在真实续写里会和参数名融合成 `(username` 一个 token，前缀必分叉；砍到
  `print(apis.venmo.login` 则 6/6 严格前缀吻合。`print(` 自身的左括号没事。
- special token 均为单 token：`<|end|>`=200007 `<|start|>`=200006 `<|channel|>`=200005
  `<|message|>`=200008 `<|return|>`=200002。
- cgen 生成阶段现在不存 token 概率（generate 无 output_scores），自触发分数必须重新生成才有。

## 命名钉死（禁止改名、禁止另起同义词）

- plan 新字段：`pred_id`(int|None)、`pred_label`(str|None)、`gen_min_p`(float|None)
- 臂名：`nofill` `inject` `inject_stop` `skel_bare` `skel_a` `skel_b` `skel_switch` `switch_only`
- 常量：`SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"`；`FENCE_OPEN = "```python\n"`
- 新文件（都在 pipeline/inject/）：`parse_call.py` `build_form_table.py` `extract_completed.py`
  `acceptance.py`；产物 `pipeline/inject/form_table.json`
- 臂与四设置的对应：乙 = skel_* 四臂（骨架钉工具名，大模型写参数）；
  甲丙的正确率锚点 = switch_only（大模型自写整条）；甲丙的算力账 = acceptance.py；
  丁 = 已跑完的 execute 档旧曲线，本次不重跑。

## A. replay_inject.py — plan 段

- A1 replay_fire：169-170 的 rec.update 增 `pred=pred`。
- A2 cmd_plan：读 label2id 后建反查表 id2label；plan 记录增 `pred_id`、
  `pred_label=id2label.get(pred_id)`。真值 `label` 字段原样保留。
  **骨架消费的是 pred_label，绝不许用 label（上帝视角红线）。**
- A3 gen_calls 改返回 `(calls, min_ps)`：generate 加
  `return_dict_in_generate=True, output_scores=True`；逐 token softmax 取所选 token
  概率，min 只统计**到首个换行 token 为止**（与 207 行截首行对齐），eos 后剔除；
  空生成记 None。批内 left-padding 的 scores 对齐要单独小心。plan 记录增 `gen_min_p`。
- A4 plan CLI 增 `--decision-file`（默认 None）。JSONL 格式：
  `{"event": ..., "fire": bool, "sent_idx": int|null}`。给了就完全替代 θ 判定
  （fire=false → 不触发；sent_idx null → 该事件首句）；`theta_source="external:<路径>"`；
  conf 照旧算（ctool softmax 该句 max），便于对账。这是给用户在训的产阈值模型留的接口。
- A5 plan_config 增 `decision_file`、`n_gen_min_p`（非 None 计数）。

## B. replay_inject.py — run 段（臂语义）

- B1 把 579-582 的 note 逻辑改成按 arm 构造 splice 串，`prompt = prefix + R.ANALYSIS_OPEN + head + splice`：

  | arm | splice |
  |---|---|
  | nofill | `""` |
  | inject | `NOTE_TMPL.format(...)`（现状不变） |
  | inject_stop | `NOTE_TMPL.format(...) + SWITCH` |
  | skel_bare | `"\n" + FENCE_OPEN + skeleton(p)` |
  | skel_a | `"\nThus code:\n" + FENCE_OPEN + skeleton(p)` |
  | skel_b | `"\nSo we will do: " + skeleton(p)` |
  | skel_switch | `SWITCH + FENCE_OPEN + skeleton(p)` |
  | switch_only | `SWITCH` |

  `skeleton(p)`：用 `pred_label` 查 form_table（CLI `--form-table`，默认
  `pipeline/inject/form_table.json`）：assign 形 → `f"{var} = {pred_label}"`；
  否则 → `"print(" + pred_label`。**一律不带尾左括号。**
- B2 todo 过滤（549-551）改：inject/inject_stop 沿用 NO_INJECT 保护；
  skel_* 要求 `p.get("pred_label")` 非空；switch_only 无额外要求。
- B3 raw 记录沿用 `note_chars` 字段名存 `len(splice)`，不改名；dry-run 分支同样走 splice。
- B4 `--arms` 默认值不动（"nofill,inject"），新臂显式传。

## C. replay_inject.py — score 段

- C1 final 重建：`ARMS_FINAL = {"inject_stop", "skel_switch", "switch_only"}`——这些臂的
  续写从 final 通道**内**开始，直接对 text 调 split_channels 会得 final=""（全灭）。
  对它们：analysis 剩余=""，final = 臂的 final 侧拼入串 + text；拼入串分别为
  skel_switch=`FENCE_OPEN+skeleton`、switch_only=`""`、inject_stop=`""`。
  skel_bare/a/b 仍走原 split_channels（骨架在 analysis 里）。
- C2 完整调用抽取：用 parse_call.complete_call 在 final（骨架臂另在 analysis 的骨架处）
  找括号配平 + 围栏闭合的终点。新列：
  - `skeleton_done`：骨架臂专用，调用是否补完（括号配平，且有围栏时围栏闭合）
  - `tool_rewritten`：骨架臂专用，`tool_out 非空且 != pred_label`
  - `post_think_chars`：skel_bare/a/b = 骨架补完点到 FINAL_OPEN 出现前的 analysis 字符数
    （没转场则记 analysis 剩余全长）；ARMS_FINAL 臂 = 0；inject/nofill = None
  - `call_out`：抽出的完整裸调用串 `apis.x.y(...)`（供对账），进 per_event
- C3 主对照换口径：`saved_tok = baseline_out_tok - out_tok`（**主对照=原轨迹**）；
  新列 `nofill_delta = nofill_out_tok - out_tok` 只作管线体检；聚合 saved_* 全部用新口径；
  md 报告口径行写明"主对照=原轨迹，nofill 仅体检"。
- C4 桶：骨架臂按 `name_hit = (pred_label == label)` 分桶聚合（乙的猜错桶）；
  cgen 系臂沿用 by_hit(full_call_ok)。
- C5 per_event 增列：`pred_label` `gen_min_p` `call_out` `skeleton_done`
  `tool_rewritten` `post_think_chars` `nofill_delta`。老 raw/plan 缺字段时用
  .get 兜底，不许崩。

## D. 新文件（都在 pipeline/inject/）

- D1 `parse_call.py`（纯 stdlib，会被 replay_inject 与 extract_completed 共同 import）：
  - `complete_call(text, start=0) -> (call_str|None, end_idx|None)`：从 start 起找首个
    `apis.` 调用起点，括号配平到闭合；引号（' 与 "）内的括号忽略，处理反斜杠转义。
  - `find_fence_close(text, start) -> int|None`。
  - 文件底部 `if __name__ == "__main__":` 放自测用例（含引号内括号、转义、未闭合）。
- D2 `build_form_table.py`：扫 `envs/runs/full_v1/appworld_gptoss` +
  `envs/runs/full_v2_topup/appworld_gptoss`（**不碰 w0 test 集**），从每步 final content
  的 fenced code 里抽首条 apis 调用形态：print 包裹 / 赋值（`var = apis...`）/ 裸；
  按工具聚合 `{tool: {n, print_share, assign_share, top_var}}` 写 form_table.json。
  规则：assign_share ≥ 0.5 → form=assign 且 var=top_var；否则 print；运行时未见工具兜底 print。
- D3 `extract_completed.py`：`--run-dir --arms` → 读 plan.jsonl + raw<tag>.jsonl，
  按 C2 逻辑抽 call_out，输出 `<run-dir>/exec_in_<arm>.jsonl`：plan 记录原样 +
  `gen_call` 替换为 call_out + 增 `source_arm`；call_out 为 None 的跳过并计数。
  字段必须满足 exec_calls.py `--plan` 实际读取的字段（**先读 exec_calls.py 核对**）。
- D4 `acceptance.py`：`--run-dir --plan-file --tokenizer`，输入 per_event<tag>.jsonl
  （要求含 switch_only 臂）+ plan.jsonl：
  - 甲：逐事件 `pred_label == switch_only 的 tool_out`，报接受率与 n。
  - 丙：cgen `gen_call` vs switch_only 的 `call_out`（裸调用对裸调用），gpt-oss 分词器
    编码后最长公共前缀 → `accept_len`、`accept_frac=LCP/len(draft)`、`exact`；
    报中位数/p10/p90。
  - 备用精确路：`--base-url` 给了才跑（completions echo+logprobs max_tokens=0，
    rank≠1 即拒绝点），报两路不一致率；没给标 skipped。
  - 输出 `<run-dir>/ACCEPT_REPORT.json`。

## E. 审查陷阱清单（reviewer 逐条打勾，缺一不可）

1. 骨架用 pred_label 而非 label（上帝视角红线）。
2. 骨架无尾左括号（分词器实测铁律）。
3. skel_* 有 pred_label 非空保护；inject_stop 有 NO_INJECT 保护。
4. ARMS_FINAL 的 split 特判存在（否则这些臂 final="" 全灭）。
5. gen_min_p 批内对齐正确（left padding + eos 剔除 + 首行截断三者一致）。
6. 断点续跑键 (event, arm) 语义未破坏；老 raw/plan 进新 score 不崩（.get 兜底）。
7. saved_tok 已换原轨迹主对照，nofill 只剩体检列。
8. extract_completed 输出字段满足 exec_calls.py 实际消费。
9. form_table 不读 w0 test 集。
10. dry-run 对全部新臂可跑（无 vLLM、无 GPU）。
11. py_compile 全过；parse_call 自测通过。

## 范围

本次只做代码就绪（纯 CPU 可验证部分）。重跑 plan（cgen 要 GPU）、vLLM run、
exec、score 出数属于下一阶段，走 gpu-run。
