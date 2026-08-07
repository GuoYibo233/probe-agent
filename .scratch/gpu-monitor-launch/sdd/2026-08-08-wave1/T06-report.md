# T06 报告 — 网页与 json 出口

工单：`.scratch/gpu-monitor-launch/issues/06-web-json-outlet.md`
spec 对应节：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 7（工单原文直接点名"步骤照实施计划 Task 7 执行"）。
分支：`ticket/20260808-par/T06`，工作树 `/home/y-guo/reproduce/new1-wt/20260808-par-T06`（已按协议删除，分支保留）。

## 做了什么

对照工单三条验收要求：

1. **网页测试通过：/json 与落盘文件一致，根路径 200 且正文含任务名、判定和最后采样时刻。**
   `ops/sampler.py` 新增 `WebServer` 类（内部起 `http.server.ThreadingHTTPServer`），
   `_WebHandler.do_GET` 按 path 分流：
   - `/json`：现读 `monitor_dir/latest.json`，原文用 `Content-Type: application/json` 吐出去；文件不在/读不了返回 503（约定，工单未点名这一分支的状态码，我按"读不到就说读不到"选了 503 而非假装 200）。
   - `/`（及其它任何 path）：调纯函数 `render_html(latest)` 拼 HTML，200 返回。表列 JOB/分片/HOST/GPU/判定/进度/速率/token/ETA/SESSION；顶部横幅 `最后采样 HH:MM:SS`；事故记录块渲染 `latest["incidents_tail"]`；台账外 session 块渲染 `latest["extras"]`；`<meta http-equiv="refresh" content="30">` 30 秒自动刷新。
   - 网页线程只读落盘文件（`_load_latest_from(monitor_dir)` 每次请求都重新 `Path.read_text()`），不引用采样线程内存里的任何变量——手动验证见下方"实测两次真实起进程"。

2. **过期亮红的阈值从判定引擎的 DEFAULTS 生成进页面，不另抄一个数。**
   `render_html` 里 `stale_after_s = verdicts.DEFAULTS["sample_interval_s"] * 3`，这个算出来的数值直接嵌进页面内联 `<script>` 的 `staleAfterS` 变量，客户端 JS 每 5 秒比一次 `Date.now()/1000 - sampledAt`，超过就给 `#banner` 加 `stale` 类（CSS 变红）。没有在别处重复写 `60*3` 或 `180` 这样的字面量。

3. **commit。** 见下方 commit 清单。

顺带做的（工单范围内，不是额外加戏）：
- `main()` 加 `--port`（默认 8377，工单指定的默认值），非 `--once` 时先起 `WebServer` daemon 线程再进采样循环，采样循环结束（理论上不会，除非未来加了退出路径）时 `web.stop()`。
- `MAP.md` 里 `ops/sampler.py` 那一行同步补了网页出口的描述——这行本来就该反映这个文件现在能做什么，不算另开的活。

## 怎么验证的

### 自动化测试

新写 `tests/test_sampler_web.py`（Step 1 先写失败测试，确认 `AttributeError: module 'sampler' has no attribute 'WebServer'` 后再实现）：
- `test_json_matches_latest_file`：`WebServer(port=0, ...)` 起服务，`urllib.request` 抓 `/json`，断言与写进 fixture 的 latest.json 字典相等。
- `test_json_content_type`：断言 `Content-Type: application/json`。
- `test_root_returns_200_with_task_table`：抓 `/` 断言 200，正文含任务名（`x`）、判定（`健康`/`已挂`）、`sampled_at` 对应的 `HH:MM:SS` 时间戳文本。
- `test_root_renders_incidents_and_extras`：断言事故记录的 note 文本和台账外 session 名都出现在正文里。
- `test_stale_threshold_from_verdicts_defaults`：断言 `verdicts.DEFAULTS["sample_interval_s"] * 3` 算出来的数值原样出现在正文（即页面里嵌的确实是从 DEFAULTS 生成的数，不是另抄的字面量）。
- `test_missing_latest_file_returns_200_with_placeholder`：latest.json 不存在时，`/` 仍 200，正文含"无采样"占位文案。

跑法与输出：

```
$ python3 -m unittest tests.test_sampler tests.test_sampler_web -v
...
test_unreachable_returns_false (tests.test_sampler.TestProbePort) ... ok
test_missing_log_returns_empty (tests.test_sampler.TestReadBeats) ... ok
test_reads_only_valid_heartbeat_lines (tests.test_sampler.TestReadBeats) ... ok
test_files_are_valid_json (tests.test_sampler.TestSampleOnce) ... ok
test_refire_resets_state_and_counts (tests.test_sampler.TestSampleOnce) ... ok
test_round (tests.test_sampler.TestSampleOnce) ... ok
test_json_content_type (tests.test_sampler_web.TestWebServer) ... ok
test_json_matches_latest_file (tests.test_sampler_web.TestWebServer) ... ok
test_missing_latest_file_returns_200_with_placeholder (tests.test_sampler_web.TestWebServer) ... ok
test_root_renders_incidents_and_extras (tests.test_sampler_web.TestWebServer) ... ok
test_root_returns_200_with_task_table (tests.test_sampler_web.TestWebServer) ... ok
test_stale_threshold_from_verdicts_defaults (tests.test_sampler_web.TestWebServer) ... ok

----------------------------------------------------------------------
Ran 12 tests in 3.237s

OK
```
（旧的 `tests.test_sampler` 六条一并跑了一遍，确认没有回归。）

`python3 -m py_compile ops/sampler.py tests/test_sampler_web.py` → `compile ok`。

### 手动验证：实测两次真实起进程

第一次，`--interval 300 --port 18377`，起后立刻（约 2 秒）`curl /json`：拿到 `{"error": "not sampled yet"}`——因为那一轮 `sample_once()` 还在跑（真实台账触发了跨机 ssh 探活，没那么快），这正好证明网页线程和采样线程互不阻塞：网页服务已经能应答，只是磁盘上还没有新的 `latest.json`。

第二次，同样起法，等 15 秒后再 `curl`：

```
$ curl -s http://127.0.0.1:18378/json | python3 -m json.tool | head -6
{
    "sampled_at": 1786140913.6448956,
    "rows": [],
    ...
$ curl -s http://127.0.0.1:18378/ | grep -o "最后采样[^<]*" | head -1
最后采样 07:15:13
```
落盘完成后网页立刻能读到新结果，时间戳格式正确。用完 `kill` 掉进程、`rm -rf` 掉临时 `NEW1_MONITOR_DIR`。

另外用 `NEW1_MONITOR_DIR=/tmp/... python3 run.py sampler --once` 冒烟了一遍 `--once` 路径（不开网页线程），确认没有破坏原有单轮流程，`latest.json` 正常写出。

`python3 run.py selfcheck`：在这个工作树里跑出 16 处"缺失"，全部是 `envs/`、`cprobe-env`、`mbert-env` 这些被 `.gitignore` 排除、只在主仓（home）目录下建过的第三方环境/虚拟环境，worktree checkout 不会带出未跟踪目录——回到主仓工作树跑同一条命令是"63 任务 / 4 配方, 全部就位"。这条不是我这次改动引入的问题，是工作树协议本身对未跟踪目录的已知局限，与 `ops/sampler.py`/`MAP.md` 的改动无关。本工单没有碰 `run.py` 的 TASKS/RECIPES 注册表本身（`sampler` 任务条目早就在,工单 02 时已经把"开网页"写进了 desc），所以严格说不在"改了 run.py 注册表相关的东西"这条规则触发范围内，但仍然跑了一遍做交叉检查。

## commit 清单

- `5897417` — `T06: monitor: 采样器网页出口(/ 任务表 + /json,只读 latest.json)`
  - `ops/sampler.py`：加 `html`/`http.server`/`threading` 三个 import；新增 `_load_latest_from`、`render_html`、`_WebHandler`、`WebServer`；`main()` 加 `--port`（默认 8377），非 `--once` 时起/停 web 线程。
  - `tests/test_sampler_web.py`：新建，6 条测试。
  - `MAP.md`：`ops/sampler.py` 那一行补上网页出口的描述和 `--port` 用法。

## 自查发现与存疑

- `/json` 在 `latest.json` 缺失时返回什么状态码，工单和 spec Task 7 都没点名（Task 7 只写了"latest.json 原文"，隐含前提是文件已存在）。我选了 503 + `{"error": "not sampled yet"}`——理由是"读不到就直说读不到"比假装 200 返回空/占位 JSON 更贴合仓库的 fail-closed 基调，但这是我自己的裁决，不是工单写死的接口,如果主会话/后续工单（比如 08 终端出口或未来的 agent 消费方）对这个状态码有别的期望，需要回来改。这条算一个存疑点，不影响 DONE 状态,因为工单验收标准里没有涉及"文件不存在时 /json 的行为"。
- `probe_free`/`register_all`（工单 10 发射公共件）等其它工单不在本单范围内，没有touch。
- 没有触碰 `ops/gpu_jobs.py`（那是工单 07 的范围），也没有触碰 `run.py` 的 sampler 任务条目本身（描述早已写"开网页"，无需再改）。
