# 塞法回放实验（splice_replay）——计划

2026-08-18。回答一个问题：探针开火时把预取结果**塞回去的方式**，哪种让模型
少想、直接往下走、不去议论注入本身。探针权重已删，所以先用上帝视角回放：
拿 5 条 chat baseline 轨迹（`cmp_chat_noprobe_5/chat`），每步在思考的四个
位置切开，把这一步代码块的真实执行输出按十种塞法拼进去，让 gpt-oss-120b 续
写一步，只量单步行为。不跑到底、不 evaluate、不判预测对错。

## 1. 事件

- 来源：`cmp_chat_noprobe_5/chat/appworld_gptoss/appworld_<tid>.jsonl` 五条。
- 取步：content 里恰好一个 ```python 块，且块里恰好一个 `apis.x.y(` 调用
  （68 步里 52 步入选；1 步无代码、13 步多调用/无调用、2 步与同题另一条逐字重复
  ——多调用块的 stdout 不是"那一条调用的返回"，各臂拼不出同一份 CALL/RESULT）。
  52 步里 40 步代码块就是裸 `print(CALL)`（`code_is_print_call`），另 12 步有
  赋值/额外 print，RESULT 是整块 stdout；3 步采集时顶到 8192（`baseline_capped`）；
  25 步下一步的工具与本步不同（`next_distinct`），其余 27 步同一工具换参数。
- 去重：3d9a636_1/2/3 同一道题，前几步的 prompt + 思考逐字相同；按
  `(prefix_ids, reasoning)` 哈希去重，只留一份（相同输入的续写不会给新信息）。
- 每事件存：traj/step、prefix 消息（到该步之前）、reasoning 全文、CALL（代码里
  那条完整 `apis.x.y(...)`，`parse_call.complete_call` 配平）、CODE（代码块原文）、
  RESULT（env.result，采集时已截 4000）、baseline_out_tok（该步 usage.out）、
  next_tool（下一步代码块首个调用工具名，没有就 None）。
- 思考太短（`< MIN_THINK`=40 字符）的步不取。

## 2. 切口（轴三）

- 比例 66 / 75 / 80 / 100，按 reasoning **字符数**算。
- 66/75/80：该比例处**之前最近的句尾**（`live_appworld.sent_cuts` 同款：
  `SENT_RE=(?<=[.!?])\s+|\n` 的 `m.end()`，含 `MIN_THINK//2` 过滤）。两个比例落到
  同一句尾就合并成一条记录，`fracs` 字段列出它代表哪几个比例。
- 100 = reasoning 全文末尾（模型已经想完，NOTE 追加在思考结尾、正文之前）。
- head = reasoning[:cut]。66/75/80 的 head 以空白结尾，100 的不以空白结尾。

## 3. 臂（轴一 × 轴二）

记号：`A_OPEN = <|channel|>analysis<|message|>`，`SWITCH = <|end|><|start|>assistant<|channel|>final<|message|>`，
`NOTE(x) = "[SYSTEM NOTE: prefetched CALL = RESULT]"` 等措辞见下表。所有臂的
prompt 前缀 = `harmony_render.render_ids(msgs 到该步)`（chat 端点同款 id）。

| 臂 | prompt 末尾（prefix_ids 之后） | 备注 |
|---|---|---|
| nofill | `A_OPEN + head` | 锚：不塞任何东西的续写 |
| p1_n0 | `A_OPEN + head + sep + "[SYSTEM NOTE: prefetched CALL = RESULT]\n"` | 现状 |
| p1_n1 | … `"I already ran:\nCODE\nand got:\nRESULT\n"` | 第一人称（塞 CODE，句句为真） |
| p1_n2 | … "```python\nCODE\n```\nExecution output:\nRESULT\n" | 环境口吻（塞 CODE） |
| p1_n3 | … `RESULT + "\n"` | 裸结果 |
| p1_n0p | 同 p1_n0，且 system prompt 末尾加 `PERMIT` 句 | 事先预告 |
| p2_n0 | `A_OPEN + head + sep + "[SYSTEM NOTE: prefetched CALL = RESULT]" + SWITCH` | 塞完强切正文（`inject_stop`） |
| p2_n1 | 同上，措辞换 n1（NOTE 无尾换行，直接接 SWITCH） | |
| p3k | openai_harmony 渲染：…, assistant/analysis(head.rstrip()), assistant/final(CODE 块 content), user("Execution output:\nRESULT"), `<|start|>assistant` | 伪造整轮·**留**思考 |
| p4 | openai_harmony 渲染：system 声明 python 工具, …, assistant/analysis(head.rstrip()), assistant→python/analysis(CODE)`<|call|>`, python→assistant/analysis(RESULT), `<|start|>assistant` | harmony 原生 python 工具 |

`sep`（缝修法，只对 p1/p2）：head 以空白结尾（66/75/80 切口）→ `""`，NOTE 直接
接在空白后（换行切口另起一行、空格切口 inline）；head 无尾空白（100% 切口）→ `"\n"`。
理由：`.\n\n` + `\n[` 会合并成 `.\n\n\n` 把模型自己的最后一个 token 换掉；`. ` +
`\n[` 虽保住 `.` 却多出一个 ` \n` 怪 token；`.\n\n` + `[S` 与 `. ` + `[S` 都干净、
`.` 原样。实际 178 个切口里 88 个以空格结尾、38 个以换行结尾、52 个（100%）无尾空白。

不进本批（上帝视角下退化）：p3（伪造整轮丢思考 = 直接跳到原轨迹下一步）、
p5（结果随下一轮 user 一起到 = baseline 本身）。真探针（预测可能错、只塞一条）
时它们才有区别。

## 4. 续写

- `/v1/completions`，prompt 为 token id，`temperature=0`，`stop=["<|return|>"]`，
  `skip_special_tokens=False`，`max_tokens=8192`（采集时整步上限；p3k/p4 是新一条
  assistant 消息，同一上限）。
- 事件 ≈ 50 × 切口 ≤ 4 × 臂 10 ≈ 2000 条，并发 16，一张 H200。
- 每条落 raw.jsonl：event、frac、arm、prompt_tok、gen_tok、text、finish_reason。
- prompt 全部先 dry-run 出 decode 文本，人眼过每臂一条。

## 5. 指标（每臂 × 每切口）

动作 = 正文里的 ```python 块；没有正文但模型自己发了 python 调用（p4 的自然续写，
harmony 把它放 analysis 通道、`to=python`、以 `<|call|>` 收尾）也算动作
（`action = final_code | python_call`）。工具级 = `apis.x.y`，调用级 = 整条调用去空白后逐字比。

1. token：`own_tok = head_tok + gen_tok`（拼接串不算，模型自己写的），主参照是
   **同事件同切口的 nofill**（`vs_nofill_own`）；`saved_own = baseline_out − own_tok`
   只做旁证——baseline 的 usage.out 里 commentary 段与消息头的账对不齐，nofill 对
   baseline 会有几个 token 的常数偏移（reviewer 量到 ≈ +7），别当管线错。
2. `has_action`；`python_call`（模型自己叫了 python）。
3. `repeated` / `repeated_call`：动作里的工具 / 整条调用 == 被塞进去的那条（又跑了一遍）。
4. `next_hit` / `next_hit_call`：== 原轨迹下一步的首个工具 / 整条调用（往下走了）；
   27/52 个事件下一步与本步同工具，所以工具级 next_hit 只在 `next_distinct` 子集
   （25 事件）上能读（`next_hit_distinct`），调用级两边都能读。
5. `uses_result`：代码里的字符串字面量出现在 RESULT 里、且不在切口前 prompt 文本里。
6. `mentions`：`system note` / `prefetch` / `the note says` 等；`mentions_already`：
   `already ran/called/executed`。**只对 prompt 里给了这些词的臂（n0/n0p/n1）有意义**，
   其余臂接近 0 是词不在场，不是行为；p2 把 analysis 通道关掉了，这类话本来就没地方写。
7. 结构：`reopen_analysis`（p2 后又开 analysis）、`stopped_on_call`（任一臂停在 `<|call|>`
   上——它是模型 generation_config 的 eos，vLLM 对所有臂都停，stop_reason=200012）、
   `truncated`（finish_reason == length）、`think_chars_after`（模型自己又想了多少字符，
   不含塞进去的 NOTE、不含 python 调用段）。
8. 分层：`by_arm` / `by_arm_uncapped` / `by_arm_print_call` / `by_arm_not_print_call` /
   `by_frac`。

出 `SPLICE_REPORT.{json,md}` + `per_row.jsonl`。

## 6. 会影响结果的裁决点（我的选择 / 备选）

| # | 裁决 | 我的选择 | 备选 |
|---|---|---|---|
| D1 | 事件只取单调用块 | 是（54 步） | 全取 67 步，多调用块 RESULT 标注偏差 |
| D2 | 同题重复步去重 | 是 | 不去重（n 虚高） |
| D3 | CALL 用什么 | 代码里那条完整 `apis.x.y(...)` | 整个代码块 |
| D4 | RESULT 用什么 | 该步 env.result 原文（块 stdout，含 print 之外的赋值逻辑影响） | 无更精确来源 |
| D5 | 缝修法 sep | head 以空白结尾不加前导 `\n`（空格切口 NOTE inline，换行切口另起行） | 一律加 `\n`（现状：换行切口吃掉一个 token，空格切口多一个 ` \n` token） |
| D6 | 关闭 analysis 的臂 head 去尾空白 | p2 不去（NOTE 接在空白后）；p3k/p4 `rstrip()` 再 `<|end|>` | 全不去（`\n\n<|end|>` 是模型没见过的形态） |
| D7 | p4 的 system prompt 声明 python 工具 | 声明（那是训练格式的一部分） | 不声明，只拼工具往返 |
| D8 | max_tokens | 一律 8192 | 8192 − 已占 token |
| D9 | p3/p5 不进本批 | 不进（上帝视角下退化） | 进，当上限锚 |
| D10 | 100% 切口 | reasoning 末尾（无句尾要求） | 最后一个句尾 |
| D11 | p4 的停止符 | `<|return|>` 之外加 `<|call|>`：模型再叫 python 就停，记 `python_again` | 不加（模型会自己编造工具返回接着写） |
| D12 | 采集时顶到 8192 的步（3/52） | 保留，标 `baseline_capped`，报告 by_arm 与 by_arm_uncapped 各出一份 | 剔除 |
| D3' | 各措辞塞哪个 | n0 用那条调用 CALL（现状锚，对 12/52 个非裸 print 块不完全真，报告分层）；n1/n2/p3k/p4 塞代码块原文 CODE（句句为真） | 全用 CALL |
| D13 | reviewer 指出 n1 "I already ran print(CALL)" 对 12 个块是假话 | n1 改成 `I already ran:\nCODE\nand got:\nRESULT` | 保留 print(CALL) 措辞、报告分层 |
| D14 | 缝的参照系 | 参照是**模型生成的 id**（句尾空格属于被丢弃的下一个 token ` Then`），不是 `enc(head)`（它会把尾空格编成孤立 ` ` token）；D5' 下 `.` 原样、空格并进 ` [`，与模型自己写 ` Then` 同构 | 按 enc(head) 比（reviewer 的比法，178 个切口 138 个"不同"，但那个孤立 ` ` 模型从没生成过） |

## 7. 交付物

- `pipeline/inject/splice_replay.py`：`events` / `run` / `score` 三个子命令。
- `tests/test_splice_replay.py`：每臂字节形态（假分词器 + 真分词器各一遍）、
  切口落点、sep 规则、评分函数边界样本。
- `run.py` 注册 `splice-events`（CPU）、`splice-run`（handoff）、`splice-score`（CPU）。
- 产物目录：`/net/.../pipeline/inject/runs/splice_replay_v1/`。
