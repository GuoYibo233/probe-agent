# T13 — vLLM 服务档

工单: `.scratch/gpu-monitor-launch/issues/13-vllm-service.md`
参照: `docs/plans/2026-08-08-gpu-monitor-launch.md` Task 15(工单点名的实施步骤来源)

## 做了什么

逐条对工单验收要求:

1. **吞吐行解析测试通过:真实样本行抽出生成速率、prompt 速率和并发数,无匹配返回 None**

   `ops/sampler.py` 新增 `VLLM_STATS_RE`(正则)+ `parse_vllm_stats(text)` +
   `read_vllm_stats(log_path, max_bytes=8192)`:

   - `parse_vllm_stats(text)`:从文本里抽所有 `Avg prompt throughput: X
     tokens/s, Avg generation throughput: Y tokens/s, Running: N reqs`
     匹配,取**最后一条**(text 可能是多行 tail,取最新一次采样),返回
     `{"prompt_tok_s": X, "gen_tok_s": Y, "running": N}`;无匹配返回
     `None`。
   - fixture 行**不是手造文本**:2026-08-08 现场核对
     `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log`
     第 9421 行,与实施计划文档给的样例逐字节一致(`grep -n "19:50:14"`
     核对过,见"怎么验证的"一节)。测试里另外用了同一份真实日志第 112 行
     (`Running: 0 reqs`,并发数不同、数值不同)做第二条断言,避免实现把
     fixture 的具体数字焊死。
   - `read_vllm_stats(log_path)`:tail 8192 字节,调 `parse_vllm_stats`;
     文件不存在(`OSError`)或这一轮日志里没有吞吐行(vLLM 引擎空闲时该行
     降级 debug 不打印)都返回 `None`——调用方(见下)决定要不要沿用上一轮
     的显示值,这个函数本身不猜。

2. **服务分片不走心跳解析,判定只由端口探测决定**

   - `sample_once()` 改成按 `piece.get("kind")` 分支:`kind=="service"`
     的分片 `beats=[]`(不再调用 `heartbeat.parse`,即不调用
     `read_beats`)、改调 `read_vllm_stats(piece["log"])` 拿
     `vllm_stats`;非 service 分片行为不变(`read_beats` 照旧)。
   - `update_piece_state()` 新增可选参数 `vllm_stats=None`:service 分片
     这一轮有值就存进 `ps["vllm_stats"]`,没有值(引擎空闲断流)就保留
     上一轮的旧值不动——`spec.md`"空闲不打吞吐行不算停摆"这条不只是不
     触发判定,显示位也不该因为断流就闪回空白。
   - `build_row()`:`kind=="service"` 时,`tok_in`/`tok_out` 两个显示位
     从 `ps["vllm_stats"]` 取(`prompt_tok_s`/`gen_tok_s`),不再从
     `last_beat`(心跳协议字段)取;`last_beat` 对 service 分片本来就永远
     是空 dict,因为 `recent_beats` 从不会被喂心跳。
   - 判定路径完全没动:`verdicts._judge_service` 早在 T02 就已经只吃
     `alive`/`port_ok`/`port_ever_ok`/`port_fail_rounds`/
     `since_launch_s`/`warmup_s` 六个字段,不看 `done`/`total`/心跳时间
     轴——这次改动确认了这一点(测试里往服务分片的日志里混了一行合法
     `@hb` 文本,断言它完全没被算进 `recent_beats`/`first_beat`,判定
     只跟 `probe_port` 的返回值走)。

3. **fixture 用 2026-08-08 从真实日志核实过的原文**:见上文验收项 1,以及
   "怎么验证的"一节的 `grep` 记录。

4. **服务分片登记时日志字段要填真实路径**:这条工单原话是发射/登记时的
   操作要求,不是代码约束——`piece["log"]` 本来就是自由字符串字段,
   `read_vllm_stats(piece["log"])` 不对路径做任何假设(不拼 workdir、
   不猜相对路径),给什么路径就读什么路径。代码侧没有需要新增的东西;
   实测时用的临时 fixture 路径故意放在跟 `workdir` 不相干的目录下
   (`tests/test_vllm_stats.py` 的 `TestServicePieceSampling.setUp`),
   验证这条路径无关性成立。

5. **commit**:见下方 commit 清单。

## 怎么验证的

先核对 fixture 是不是真实原文(不是照抄计划文档,是现场重新 grep 一遍):

```
$ grep -n "19:50:14" /net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/new1_diag_srv_a.log
```
```
9421:(APIServer pid=263921) INFO 08-02 19:50:14 [loggers.py:310] Engine 000: Avg prompt throughput: 785.1 tokens/s, Avg generation throughput: 671.8 tokens/s, Running: 4 reqs, Waiting: 0 reqs, GPU KV cache usage: 11.2%, Prefix cache hit rate: 97.1%
```
逐字节与实施计划 Task 15 给出的样例一致。

新写的测试(TDD:先跑一遍确认全部因为 `AttributeError`/断言失败红,截图
略,写完实现后是这份全绿输出):

```
$ python3 -m unittest tests.test_vllm_stats -v
```
```
test_extracts_real_fixture_line (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_extracts_second_real_line (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_multiple_lines_takes_the_last (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_no_match_returns_none (tests.test_vllm_stats.TestParseVllmStats) ... ok
test_missing_file_returns_none (tests.test_vllm_stats.TestReadVllmStats) ... ok
test_no_throughput_line_returns_none (tests.test_vllm_stats.TestReadVllmStats) ... ok
test_reads_tail_of_log_file (tests.test_vllm_stats.TestReadVllmStats) ... ok
test_healthy_port_ignores_fake_heartbeat_line_and_shows_rate (tests.test_vllm_stats.TestServicePieceSampling) ... ok
test_idle_no_throughput_line_keeps_last_known_rate_for_display (tests.test_vllm_stats.TestServicePieceSampling) ... ok
test_port_down_gives_dead_verdict_regardless_of_throughput_line (tests.test_vllm_stats.TestServicePieceSampling) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.049s

OK
```

10 条里:`TestParseVllmStats`/`TestReadVllmStats` 七条是纯函数单测(工单
验收项 1);`TestServicePieceSampling` 三条是集成冒烟(工单验收项 2)——
分别验证「端口健康+日志里混一行合法 `@hb` 也不进心跳,显示位吃到吞吐行」
「端口探测失败给已挂,不管吞吐行还在不在」「吞吐行断流(第二轮日志没有
吞吐行)判定仍健康、显示位沿用上一轮」。

全仓测试(与其它并行工单在各自工作树里的改动互不干扰):

```
$ python3 -m unittest discover -s tests -v
```
```
...(89 条,含新增 10 条)
----------------------------------------------------------------------
Ran 89 tests in 3.544s

OK
```

```
$ python3 run.py selfcheck
```
```
selfcheck: 63 任务 / 4 配方, 16 处缺失
```
16 条全部是 `envs/*/venv`、`cprobe-env`、`mbert-env` 等第三方 venv 目录
在这个新建的 `git worktree` 里天然不存在(不进 git,`.gitignore` 排除)——
与 T09 报告记录的现象一致,不是本次改动引入的问题;在主仓工作树
(`/home/y-guo/reproduce/new1`)跑同一条命令的历史记录里也确认过是
"全部就位"。本工单没有新建/改动 `run.py` 的 TASKS/RECIPES 注册表条目
(只改了 `ops/sampler.py` 内部逻辑),所以这次没有单独重新核对主仓
selfcheck——性质与 T09 记录的完全一样,不重复验证。

## commit 清单

- `3540212` — `T13: monitor: vLLM 服务档(端口探测进判定,吞吐行只做速率显示)`
  改动:`ops/sampler.py`(新增 `parse_vllm_stats`/`read_vllm_stats`,
  `sample_once`/`update_piece_state`/`build_row` 三处按 `kind=="service"`
  分支)、`tests/test_vllm_stats.py`(新建,10 条测试)、`MAP.md`(补一句
  `ops/sampler.py` 行的行为说明)。

## 自查发现与存疑

- **`port` 字段目前没有任何发射路径自动写入(工单 Comments 点名的必核项)**:
  `ops/sampler.py` 里 `piece.get("port")` 这个读取点是 T02(工单 02)就
  已经写好的,这次我没有新增它,只是确认并依赖它。但完整链路上游——
  `ops/launch_cmd.py`(工单 09)——目前**没有任何代码把 `--port` 的值
  写进 rich piece**:`--port` 不在 `launch_cmd.py` 的 `_VALUE_FLAGS`/
  `_BOOL_FLAGS` 里,所以它和它的值都会落进 `extra`(未知旗标透传给
  任务),原样拼进发给 `vllm serve` 的命令行里——这对"把 `--port` 传给
  真正的服务进程"这件事是对的,但意味着 `register_all()` 组装的
  `rich_pieces` 字典里完全没有 `"port"` 这个键。也就是说,如果真按
  `python3 run.py launch serve-mirrorapi --service --piece host:gpu
  --run-id X --track Y -- --port 8125 ...` 这样发射一个服务,采样器这边
  `piece.get("port")` 会拿到 `None`,`update_piece_state` 里
  `port_ok = probe_port(...) if port else False` 直接短路成
  `False`(见 `ops/sampler.py` 的"服务类:端口探测"段),这个分片永远判
  不了"健康",只会卡在"warm-up 中"直到 warm-up 上限,然后转"疑似卡死"。

  我**没有**去改 `ops/launch_cmd.py`——理由:工单原文写的是"步骤照
  实施计划 Task 15 执行",Task 15 的 Files 清单只列了
  `ops/sampler.py`(改)+ `tests/test_vllm_stats.py`(新建),十个编号
  步骤里也完全没有提到要碰 `launch_cmd.py` 或 `--service`/`--port` 的
  解析;而工单 Comments 原话给了两条路都行的出口("要么把 port 落进
  piece/台账字段并让采样器读到，要么在报告里明确说明 port 从哪来")。
  在这两条之间,我选了"说清楚在报告里",没有顺手扩大这张工单的改动
  范围去碰 `launch_cmd.py`(那是工单 09 的文件,不在这张工单的
  "只动这张工单范围内的文件"边界内,擅自改动等于借工单 13 的名义做了
  工单 09 范围的事)。

  实际验证过的路径(测试里走的)是:`piece` 字典本身对 `"port"` 没有任何
  schema 校验,谁往里塞这个键、`sampler.py` 就读得到——`ops/gpu_jobs.py`
  的 `cmd_register`(手搓登记的老路径)目前也**没有** `--port`/`--kind`
  的 CLI 支持(只认 `--name`/`--workdir`/`--note`/`--piece
  host:gpus:session:log`),同样接不上 `kind="service"` + `port` 这两个
  字段。所以现状是:**没有任何一条现成命令行路径能把一个真实 vLLM 服务
  正确登记成 `kind="service"` 带 `port` 的台账条目**——想让这次改动在
  真实服务上生效,得靠人手工调用 `launch_common.register_all()`(Python
  级)或者直接手改 `ops/jobs.json` 把 `"kind": "service", "port": N` 塞
  进对应 piece。这是留给后续工单(或用户决策)的真实缺口,不是这张工单
  能力范围内能一并补上的。

- **`probe_port` 的 `/health` 假设没有真实验证**:`ops/sampler.py` 里
  `probe_port()` 的实现和它的注释("vLLM 的 /health 返回 200,工单 13
  核对后如有出入改这里")都是 T02 就写好的。这张工单规程明确禁止发射
  任何 GPU 进程,我没有起真实 vLLM 服务去实测 `/health` 的返回码,所以
  这条假设仍然停留在"未经这张工单实测"的状态——只是把这份存疑原样
  保留下来,没有假装验证过。

- **`tok_in`/`tok_out` 复用心跳协议的显示位这个设计选择不是工单原文
  逐字规定的**:实施计划 Task 15 的 Step 3 原话是"抓吞吐行 → row 的
  `tok_out` 速率显示位",只点名了 `tok_out` 一个字段。我额外把
  `prompt_tok_s` 放进了 `tok_in`(对称复用同一对"进/出"显示位,而不是
  另开新字段),这是我在没有更细规格时做的最小合理选择,不是按某处
  既有先例抄的——如果这两个位置将来要在网页/终端表里单独标"这是吞吐
  速率不是累计 token 数",需要另外定显示格式,这次没有改
  `render_html()` 的表头/单位标注,`tok` 列现在对服务分片显示的是纯数字
  (如 `785.1/671.8`),视觉上和批处理任务的累计 token 数长得一样,容易
  被人读错单位——值得下一次真的接一个服务分片跑起来之后肉眼核对一遍。

- 没有发射任何真实 GPU 进程或 tmux session;测试全部用临时目录 + 假日志
  文件 + monkeypatch `probe_port`/`live_sessions`,没有触碰真实台账
  (`ops/jobs.json`)、`ops/runs.jsonl`、任何 GPU 机器,也没有连接真实网络
  端口(`probe_port` 的单测用端口 1 触发 `ConnectionRefused`,这条测试
  在 T02 就有,这次没有改动)。
- 没有改 `run.py` 的 TASKS/RECIPES 注册表,`python3 run.py selfcheck` 不
  是这次改动要过的新门(不涉及新任务/新配方),仍然照工单纪律跑了一遍
  确认没有引入新的缺失项。
