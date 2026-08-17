# METHOD — 探针投机执行工具调用：方法规范

> **状态：定稿（2026-08-08）。**
> 本文写"方法应当是什么"。怎么跑归 `.claude/skills/probe-pipeline/`，
> 词汇定义归 `CONTEXT.md`，数字归 `RESULTS.md`——本文一概不重复。
> 与现状代码的差异集中在 §6 对齐清单；定稿后按清单改代码，文档为准。
>
> **三色标注（全文规矩）**：每一项标【现状】/【已定要改】/【想法待定】，
> 三种身份绝不混写。【现状】= 代码今天就是这样；【已定要改】= 已拍板、
> 待动手；【想法待定】= 有想法、没定案，只许试验不许当口径。

## 0 性质

这是一个实验。主干循环（§1）定死，其余每一环都是排队待试的方法轴（§3）；
工作方式以小规模可行性试验为常态。效果好坏一律以跑出的数字为准，
本文档不预写任何结论。

## 1 主干（定死）

> agent 大模型在环境里逐步做任务；每当思考推进到一个句子切口，
> 旁路的探针看一眼当前前缀；触发规则说"出手"时，产出一条预测的
> 工具调用并取得其结果；把调用与结果以文本形式塞回切口处，
> 模型从那里接着写。

【现状】现役实例化：gpt-oss-120b + AppWorld，活跑驱动器
`pipeline/inject/live_appworld.py` + 探针服务 `pipeline/inject/probe_server.py`
（`/score` 打分、`/gen` 生成整条调用、`/render` 出 harmony 前缀 token id、
`/encode` 给注入后重发分词）。三个臂的名字见 `CONTEXT.md`：chat baseline / with probe / no probe。

## 2 铁律（凌驾于一切轴）

### 2.1 同设铁律

基线与方法必须是同一套实验设置：同模型、同服务、同采样、同解码；
方法侧不得引入基线没有的解码手段。

检验办法 = **空注入对照**：全套机器挂上、一次不出手（no probe 臂，
`--no-probe`），输出与 chat baseline（`envs/collect/run_appworld.py --api chat`）
逐步对比。
允许小浮动。依据一次偶然观测：hcap 采集时第 2 步与对照重发用了同一个
prompt（1457 token）、temperature 0，一次 8192 撞顶、一次 136 正常收尾
——单次观测、非受控实测，见 `learn/vllm/reference/token-walk.html`；
vLLM 侧受控复跑至今没做过（`learn/vllm/lessons/0004` 原话
"vLLM 侧我们没有做过对照实测"）。浮动数字报告出来由人判，
逐字节一致不作保证。

同设的一个运行时前提：chat baseline 的 prompt 日期由服务端 `datetime.now()` 生成，
活跑前缀日期由 `/render` 客户端钉死——两边要可比，发射 vLLM 时必须设
`VLLM_SYSTEM_START_DATE` 与钉死日期一致（见 §6-④）。

已修掉的三处渲染口径差：
- 2026-08-10 z1 冒烟抓到：`build_prefix` 走模型 jinja 模板，developer 正文与
  `<|end|>` 之间多 `\n\n` 两字符，chat 端点的 harmony 渲染器与采集手拼串都
  没有——no probe 臂曾因此第 0 步即分叉。修后 `/render` 与 chat 服务端渲染逐字节
  全等（实测 1533=1533）。
- 2026-08-18 逐层对 vLLM 0.26.0 源码抓到两条，都在 jinja 文本路：(a) content
  为空的 assistant 轮，chat 端点整条丢掉，jinja 照渲染一条空 final 消息（实测
  同一段历史 367 vs 373 token）；(b) content 里字面的 `<|end|>` `<|channel|>`
  等标记，chat 端点当普通文本编码，completions 端点分词收成真特殊 token
  （实测 377 vs 370 token）。两条一旦触发，此后每步 prompt 永久偏离。修法：
  `/render` 改走 `pipeline/inject/harmony_render.py`，照抄 chat 端点的三步渲染
  直接出 token id，驱动器把 prompt 以 id 列表发；裁判测试
  `tests/test_harmony_render.py` 用 vLLM 自己的函数对逐 token 相等（vllm-env 下跑）。
  同一次对码确认逐层相同的还有：采样参数、停止 token（`<|return|>` `<|call|>`
  `<|endoftext|>` 两路都由 generation_config 并入）、max_tokens、输出切分口径
  （截断在思考中/畸形头/伪造 user 轮五种输出实测同结果）、AppWorld 种子与截断。
  剩下对不齐的只有服务端批组成的数值抖动（`VLLM_BATCH_INVARIANT` 缺省关，
  z1 实测两臂 prompt token 数相同仍在生成中途分叉），以及畸形输出/上下文撞顶
  时的处理路径（chat 端点回 500/400；2026-08-18 起 `run_appworld.py` 也按题兜底
  记 abort，对比时只比两边都有结果的题）。
  **2026-08-18 五题实跑（`cmp_chat_noprobe_5`）核了一遍**：同一 prompt、同一
  前缀缓存状态下，chat 端点与 completions(ids) 输出逐字同（冷 13/13、暖 13/13）；
  同一 prompt 清缓存前后输出 13/13 不同——贪心分叉来自服务端前缀缓存命中多少
  （数值路径随之变），不来自端点。`VLLM_BATCH_INVARIANT=1` 对 MXFP4 的
  gpt-oss-120b 起不来（要 amd-quark，且反量化 bf16 单卡放不下）。分叉位 top-1/top-2
  logprob 差全是 bf16 一格（0/0.125/0.25）的平局位，两态扰动 ≤0.17 nat（`srv4`）。
  **裁决（2026-08-18）：当噪声**，两臂不追逐字同，靠题量平；种子对 argmax 无用。

### 2.2 注入格式同效

注入进思考链的内容，落到 token 层必须与模型自己写出的思考完全同效——
格式不多不少、特殊 token 一个不差。拆成四条可验判据：

| # | 判据 | 状态 |
|---|---|---|
| R1 | 注入只落在思考段内部，思考一闭合就停手 | 【现状】满足（`live_appworld.py:273-279`） |
| R2 | 注入内容本身零特殊 token（纯文本模板） | 【现状】满足（`replay_inject.py:147`） |
| R3 | 注入后重发的整串重编码后是合法 harmony 串、与原生成逐 token 对齐；重分词缝（`live_appworld.py:320`）每次机制检查实测 | 【现状】已验（2026-08-10 z1 冒烟：10/10 注入事件服务端分词与 openai_harmony 重编码逐位一致，见 `plans/2026-08-10-z1-smoke-report.md`） |
| R4 | 请求参数与已验证等价的采集路一致 | 【现状】满足。2026-08-18 起 prompt 以 token id 发，服务端不再分词，`add_special_tokens` 无作用已去掉；`skip_special_tokens=False` 保留（输出切分要看标记） |

## 3 轴（每轴：现役取值 + 进线口 + 待试）

**轴1 探针读什么**
【现状】重拼文本：`assemble(task, history, 思考前缀)`（`pipeline/annotate/rules.py`），
探针自己的 tokenizer 重新编码。
【想法待定】读 agent 大模型的隐藏状态（以后继续，不在本仓库先做）。

**轴2 探针用什么模型**
【现状】四格：mtool/mext = ModernBERT-base，ctool/cgen = Qwen3-0.6B-Base
（探针自己的骨架，与被探测模型无关）。训练/评测入口见 `run.py` 的
`CELLS`/`EVAL_CELLS`。

**轴3 参数怎么来**
【现状】活跑现役 = cgen 整条生成（`/gen`）。离线另有两条已实现待用：
mext 区间抽取；骨架臂（工具名钉死、参数模型自写，`replay_inject.py` skel 系）。

**轴4 触发规则**
【现状】ctool softmax（温度 T 校准）最大概率 ≥ θ，切口从早到晚首过线出手。
θ **永远手动给定，不给就拒绝启动**：
活跑 `--theta`【现状】必传无默认（§6-① 2026-08-10 改齐）；
离线 `--theta` 手动 或 `--risk` 查 `REPLAY_REPORT.json` 风险档（保留）。
进线口：`external_fire` 判定文件（JSONL 每行
`{"event":…, "fire": bool, "sent_idx": int|null}`，给了它 θ 完全不参与，
`replay_inject.py:217-258`）——外部训练的触发模型从这里进，管线不改。
未接线：fire-head（训练侧可训，注入链零引用）。只记录：cgen min_ps。

**轴5 塞什么**
【现状】NOTE 模板 `\n[SYSTEM NOTE: prefetched {call} = {result}]\n`。
活跑一律真执行：出手就执行、返回什么注什么（报错也注），
执行走"存档→执行→回档→重冻时间"，世界状态不留痕。
离线三档 miss_policy：skip / oracle / execute（各量各的，口径见
`replay_inject.py` 文件头）。
【想法待定】塞什么的新方案另开会话讨论，不进本文档。

**轴6 何时塞**
【现状】思考的句子切口上、首过线出手、每步最多注一次
（`--max-inject-per-step` 默认 1）。

**轴7 工具类型**
【现状】不区分——只读的和会写的一视同仁出手。
【想法待定】只读/写分治（fire-head 的 readonly 标签是这根轴仅有的代码痕迹），
以后再说。

**轴8 一步之内何时收手**
【现状】四条：每步最多注一次；一步里探测的切口数有上限（MAX_BOUNDS）；
思考段一闭合就停探；每步有 token 预算（stop=`<|return|>`）。

## 4 现役落地图

| 环节 | 代码 | 备注 |
|---|---|---|
| 采集 | `envs/collect/run_appworld.py` + `common.py` | chat baseline 与 harmony 全录都在这 |
| 标注 | `pipeline/annotate/build.py` / `param_label.py` / `rules.py` | 标签=该步实际调用；样本按句边界切前缀 |
| 训练 | `pipeline/train/` 四格 | 唯一真源 `run.py` CELLS |
| 评测 | `pipeline/eval/` | 产 `REPLAY_REPORT.json`（T 与各风险档 θ） |
| 离线注入 | `pipeline/inject/replay_inject.py` | plan/run/merge-exec/score |
| 真实执行 | `pipeline/inject/exec_calls.py` | 正身世界存档→执行→回档 |
| 活跑 | `pipeline/inject/live_appworld.py` + `probe_server.py` | 每题 `live_{task_id}.jsonl`：meta/gen/spec/env/final 五种记录 |

## 5 机制检查（验收套餐）

顺序：文档定稿 → §6 清单改齐 → 冒烟。**冒烟 2 道题**，及格线三件：

- (i) **每次出手五样可指认**：日志 spec 记录里齐着——第几步/哪个切口/
  多确信/猜了什么调用执行返回了什么/塞了什么，且后续 gen 记录能看到模型怎么接。
- (ii) **R3 token 比对**：注入后重发的串带 `return_token_ids` 回读，
  与 openai_harmony 重编码序列逐位对（hcap 工具链现成）。
- (iii) **空注入对照**：同批题，chat baseline 与 no probe 臂各跑一遍，
  逐步对比输出，报"相同/分叉"计数——浮动容不容忍，人看了数字再定，不预设阈值。

准确率浮动检验（"少少浮动"）放冒烟通过后的第一个正式批次——批量才量得出。
旧阶段数字一概不作参照。

## 6 对齐清单（文档 ≠ 现状之处；定稿后动手，改齐走三件套）

**四件全部于 2026-08-10 改齐**，此表留作依据记录：

| # | 改什么 | 依据 | 落点 |
|---|---|---|---|
| ① | `probe_server.py` `--theta` 去默认 0.925、改必传 | 轴4：θ 永远手动，不给就拒跑 | `probe_server.py` argparse `required=True`，serve/selftest 两个子命令都管 |
| ② | `live_appworld.py:1` 指向已删设计书 `plans/2026-08-01-live-inject-design.md` 的断指针，改指本文件 | 08-02 清场删了 plans/ | 文件头已改指 METHOD.md |
| ③ | `live_appworld.py` open_stream 载荷补 `add_special_tokens: False` | §2.2-R4；采集路显式钉死，活跑靠缺省碰对（tokenizer post_processor=ByteLevel，静态证据缺省无害，仍须显式） | 载荷字典加键（全文件唯一 completions 请求点） |
| ④ | 活跑/对照用的 vLLM 发射脚本设 `VLLM_SYSTEM_START_DATE`=钉死日期 | §2.1 同设前提 | `launch_vllm_splice.py` 钉 2026-07-31（=`rebuild.COLLECT_DATE`）；其余 launch_vllm_* 是一次性发射器，要用时再钉 |

2026-08-18 追加两件（chat baseline 与 no probe 对码，已改齐）：

| # | 改什么 | 依据 | 落点 |
|---|---|---|---|
| ⑤ | `/render` 改出 token id（照抄 chat 端点渲染），驱动器 prompt 以 id 发，注入后重发经 `/encode` | §2.1 两条渲染口径差 (a)(b) | `harmony_render.py` 新增；`probe_server.py` `/render` `/encode` `/health` 回显 `render=harmony_ids`；`live_appworld.py` 开跑前核该字段，老服务拒跑；`cprobe-env` 加 openai-harmony（锁文件已更新） |
| ⑥ | `run_appworld.py --api chat` 不传 `--reasoning-effort` 按 high；单题异常按题兜底记 `abort` | 服务端缺省 medium 与 no probe 缺省 high 差一个词；chat 端点 500/400 不该陪葬整个分片 | `run_appworld.py` argparse 后置缺省；主循环 try/except，final 多 `abort` 字段 |

## 7 定案记录（2026-08-08 grilling 会话）

方法定性为实验空间（主干+轴）；检查顺序 = 文档→对码→冒烟；
机制层验收（每次注入可指认），不追旧数字；setting = gpt-oss + AppWorld；
文档住根目录 METHOD.md，词汇归 CONTEXT.md（扩为全仓库词汇表）；
θ 永远手动；工具类型暂不区分；停止轴限定"一步之内"。
逐题决议见会话记录，定稿时在 TIMELINE.md 补一条方向决策。
