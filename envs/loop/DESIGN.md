# T9 闭环管线设计书(B 线,2026-07-30)

对应任务规划书 T9/T10(`plans/2026-07-30-task-plan.md`)。词表沿用规划书 §0。

## 架构:四件套 + 环境接入层

```
┌ 环境 venv(bfcl/appworld/tales 各自的) ─────────────────┐
│ 闭环 runner / handler                                    │
│   StreamingChat ──流式思考──▶ ProbeMonitor ──HTTP──▶ 探针服务│
│        │  ◀─"abort"(截断)──      │                (mbert-env,│
│        ▼                         ▼ sink              1 张卡) │
│   环境执行 ◀─合成调用─      EpisodeLedger                    │
└──────────────────────────────────────────────────────────┘
```

- `textproto.py` 文本协议层:re-export `build_dataset.assemble/clip/SENT_RE`
  (在线前缀与训练样本**逐字节同源**,不复制逻辑)+ 增量句界检测器
  BoundaryTracker。**已验证**:170 条 v3 真实思考文本、1-7 字符随机 chunk
  流式喂入,切点与 `build_dataset.boundaries` 未抽样全集零失配。
  与训练分布的两处刻意差异:①不做 MAX_BOUNDS=64 抽样(线上每句界都探,
  训练的 w=1/m 等权就是按此部署分布设计);②思考不足 MIN_THINK 的事件
  训练时被剔除,线上流式无法预知思考总长,只靠"前缀≥20 字符才探"兜底。
- `probe_server.py` 探针 HTTP 微服务(mbert-env,GPU):纯打分,
  POST /score → 温度校准后 label/conf/top5。打分参数与 eval_replay
  完全同轨(bf16/sdpa/max_len 4096/左截断);温度默认读 run 目录
  REPLAY_REPORT.json。逐请求 jsonl 日志 = "探针开销单独成列"的原始数据。
  各环境 venv 经 stdlib urllib 调用,零依赖入侵。
- `probe_client.py` ProbeClient + ProbeMonitor:一步生成一个 monitor,
  θ 判断在客户端。姿态 off/shadow/truncate;触发语义=回放协议的首次越阈。
- `stream_chat.py` StreamingChat:common.Chat raw 模式的流式版,提示词
  拼法复用 Chat.build_prompt(逐字节一致)。on_think 回调返回 "abort" 即
  断开连接(vLLM 客户端断开即弃算)。
- `accounting.py` EpisodeLedger:墙钟/token/成败三表;被打断的生成用
  vLLM /tokenize 端点补精确 token 数(同模型同分词器)。

## 五口径怎么用这套件

| 口径 | monitor 姿态 | 生成 | 备注 |
|---|---|---|---|
| 基线 | off | 阻塞或流式均可 | 不起探针服务,总账下限 |
| 截断 | truncate | 流式 | 触发→abort→合成调用递给环境,θ 扫数档 |
| 预取 | shadow | 流式 | 触发→后台线程执行只读调用;agent 自发调用时核对递上;限 bfcl/appworld |
| 影子记录 | shadow | 流式 | 只记不动;线上精度 vs 回放评测对账 |
| fork 对照 | shadow | 流式 | 触发点复制现场起分支,见下 |

fork 铁律(规划书已拍板):每个触发事件只在首次过 θ 处 fork 一次,
分支内探针关闭(mode=off),禁止嵌套。分支走投机路线(=截断动作)到任务
结束,与主线对比 token 账与成败。

## fork 的现场复制:两档机制

deploy-scout 调研结论(microsoft/tale-suite + 各引擎源码,2026-07-30):

1. **通用档(全环境可用)——动作史重放**:我们逐步全录动作,fork =
   新开环境实例(同 task_id/seed)+ 逐条重放动作史。成本 O(steps)。
   - tales:采集用的 TextWorldExpressEnv 有官方 `clone()`,内部就是
     seed+动作史重放(serialize/deserialize),置信度高;tale-suite 仓库
     自带 `scripts/test_replay_determinism.py` 可当预检。
   - appworld:AppWorld(task_id, experiment_name) 换 experiment_name
     新开实例重放,防实验目录互踩(run_appworld.py 已有此机制)。
   - bfcl:环境是纯 Python 类实例,另有快照档(见下)。
2. **快照档(能用就用,O(1))**:bfcl 的多轮环境状态是进程内类实例,
   copy.deepcopy 直接复制(待 bfcl_eval 源码勘察确认无不可拷对象)。

**T9 的"tales 存档待调研"风险已解除:判级可行。**

## 环境接入层(逐环境)

- **bfcl(先做,T9 验收环境)**:不重写 runner,子类化 bfcl_eval 的
  OSSHandler(qwen 用的 completions handler),换 `_query_prompting` 为
  StreamingChat+monitor 版;截断时把合成回复经
  `_add_assistant_message_prompting` 注入。历史构造对齐 build_dataset.
  bfcl_events:hist 条目=(assistant 文本 strip 后取前 200 字符, tool 返回),
  task=最近一条 user 消息。接缝细节待 bfcl_eval 源码勘察报告回来后定稿。
- **appworld/tales**:自家 run_*.py 改造(Chat→StreamingChat+monitor),
  hist/task 构造与 build_dataset.jsonl_events 对齐
  (appworld:result 截 4000;tales:动作原文)。
  已落地:`run_appworld_loop.py`(fork=新实例重放动作史,experiment_name
  加 _forkN 防目录互踩)/`run_tales_loop.py`(fork=壳内原生 TWX 的官方
  clone(),ForkedTWX shim 补齐 step 字段语义)。各自 venv 导入检查过;
  端到端联调等 bfcl demo 通过后排。

## 计时基建

- 三表:墙钟(每步 wall_s+总墙钟)/token 账(in/out 每步,截断步经
  /tokenize 补精确数)/成败(环境原生判定:bfcl checker、appworld
  evaluate、tales won)。
- serving 对照:基线组与实验组同一 vLLM 服务配置;探针开销单独成列
  (探针服务逐请求日志:ms/n_chars/conf)。

## 已知风险与未决

- vLLM 流式 include_usage 在客户端 abort 时拿不到 usage → 已用
  /tokenize 兜底,demo 时核对两条路径数字一致性。
- gpt-oss(chat 端点)的流式思考字段:chat stream 的 delta.reasoning
  字段名待实测;T9 demo 用 qwen(raw completions),gpt-oss 留到 T10 前补。
- ~~bfcl_eval 状态对象可 deepcopy 与否~~ 已确认安全(勘察报告:
  multi_turn_base 涉事类无句柄/锁,框架自身逐轮 deepcopy 做 state_log)。
- 探针服务单卡单请求延迟(~几十 ms 量级预期)在 demo 时实测,写进报告。
- 参数产线:demo 用占位合成(`[tool()]` 零参数),T7 抽取头就位后经
  loop_cfg["synth"] 挂真产线;截断口径的调用正确率在此之前无意义。
- fork 口径的 wall_s_total 含分支耗时(分支是对照仪器不是产线),主线
  墙钟以逐步 gen wall_s 求和为准 —— T10 汇总脚本按此口径。

## bfcl 接入实现(2026-07-30 落地)

`bfcl_loop_handler.QwenLoopHandler(QwenHandler)`:不改 venv、不进注册表,
demo 驱动直接构造。覆盖 `_query_prompting`(流式+monitor+截断合成)/
`_parse_query_response_prompting`(dict 直通)/轮次钩子(fork 续跑要知道
剩几轮)。fork 现场复制:multi_turn_utils 模块缓存里 deepcopy 实例挂
`<entry>_forkN` key,分支自跑迷你多轮循环(阻塞生成、探针关、账本独立)。
驱动 `run_bfcl_demo.py` 一 entry 四口径顺跑+汇总表。
已自测(CPU):venv 导入、200 测例装载带函数文档、task_hist 与
bfcl_events 逐条对齐、handler 构造。GPU demo 见 SMOKE.md,发射权在 A 线。
