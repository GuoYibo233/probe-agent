# T07 报告 — 终端出口改读采样历史

工单：`.scratch/gpu-monitor-launch/issues/07-terminal-outlet.md`
参照：`docs/plans/2026-08-08-gpu-monitor-launch.md` Task 8（工单正文点名）
分支：`ticket/20260808-par/T07`，工作树 `new1-wt/20260808-par-T07`（已清理）
commit：`873f478`

## 做了什么

工单四条要求逐条对照：

1. **没有采样器在跑的时候：警告行加老表照出，json 出口输出合法 JSON。**
   `ops/gpu_jobs.py` 新增 `read_latest()`（读 `MONITOR_DIR/latest.json`，
   返回 `(latest_dict|None, age_s|None)`，文件不在/读不了/JSON 坏了都
   返回 `(None, None)`）。`cmd_status`/`cmd_watch`/`cmd_json` 三处都先调
   `read_latest()`，`latest is None or age_s > FRESH_S`（`FRESH_S=300.0`）
   就走过期分支：终端两个出口打印 `_stale_warning()` 给出的原文
   `采样器不在跑(最后采样 <时刻|无>),现场实探一次`，再走原有
   `collect()` + `fmt_table()` 老路；json 出口过期时输出
   `{"rows": collect(), "sampler_stale": True}`（裸列表加不了字段，
   套一层 `rows` 键，键名与 `latest.json` 本来的键名对上）。

2. **指一份假的最新采样文件：新表出得来，判定、进度、速率、ETA 各列都渲染。**
   新鲜分支调用新写的 `fmt_table_v2(rows, sampled_at)`：表头第一行
   `最后采样 HH:MM:SS`；列 `JOB/HOST/GPU/判定/PROGRESS/RATE/TOK/ETA/SESSION`
   （工单原文列表）。PROGRESS 用 sampler 已经算好的 `progress_pct`
   拼成 `done/total (pct%) unit`；RATE 按数量级选单位——
   `recent_rate >= 1` 保留 `/s`，否则乘 3600 显示 `/h`（工单原文
   "乘 3600 显示 /h 或保留 /s 按数量级" 没给精确阈值，这条边界是我按
   "批任务常见速率 <1/s、vLLM 类吞吐常见 >=1/s" 定的，写进了
   `_fmt_rate_v2` 的 docstring，供复核）；TOK 用千分位缩写
   （`_fmt_tok_short`：`>=1e6` 用 `X.YM`，`>=1e3` 用 `Xk`）拼成
   `tok_in/tok_out`；ETA 把 `eta_s` 转 `HH:MM`。

3. **已完成和已挂两种判定仍有收尾与看日志的提示行。**
   `fmt_table_v2` 按 job 分组：一个 job 下所有分片判定都是
   `verdicts.V_DONE`（已完成）才输出
   `已完成 = 全部分片判定已完成——该收尾了: python3 run.py gpu-jobs finish <job>`；
   任意一行判定是 `verdicts.V_DEAD`（已挂）就输出
   `已挂 = session 没了，进度未到 100%，看日志: <第一条已挂行的 log 路径>`。
   两条提示的措辞是照 `fmt_table()` 原有的 DONE/EXIT 两行改写的——原文本
   依赖旧的 `state` 字段（"session 已退" / "进度 100%"），现在直接读采样器
   算好的 `verdict` 字段，语义对得上但字面不是逐字照抄，算是工单
   "措辞沿用" 这条里我拿的一个不影响功能的小判断，写进了下面的存疑。

4. **commit。** `873f478`，见上。

`free`/`register`/`finish` 三个命令一行没动，仍然只经 `collect()`/
`live_sessions()` 现场实探（对照 diff：改动只碰了 `cmd_status`/
`cmd_watch`/新增的 `cmd_json`，`cmd_free`/`cmd_register`/`cmd_finish`/
`cmd_finish_force` 原样未动）。

## 怎么验证的

### 自动化测试

新增 `tests/test_gpu_jobs.py`（这条流水线目前没有现成的 `gpu_jobs.py`
测试先例，跟 `test_sampler.py`/`test_sampler_web.py` 一样的风格：用
`NEW1_MONITOR_DIR`/monkeypatch `gpu_jobs.REG_PATH` 把落盘目录和台账指
到 tmp）。四个测试类：

- `TestReadLatest`：文件不在 → `(None, None)`；新鲜文件 → `age_s < 5`；
  一小时前的旧文件 → `age_s > FRESH_S`；JSON 坏了 → `(None, None)`。
- `TestFmtTableV2`：假 rows 渲染出全部列（判定值、`3/10 (30.0%) task`
  的进度格式、`72/h` 的速率换算、`1.2M/340k` 的 token 缩写、`01:02` 的
  ETA 换算）；空 rows 仍出表头占位；`已完成` 全分片的 job 出收尾提示；
  `已挂` 的行出看日志提示。
- `TestCmdJson`：无采样器 → `sampler_stale: True` 且 `rows == []`（台账
  为空）；新鲜 latest.json → 原样吐出，不带 `sampler_stale` 字段；过期
  → `sampler_stale: True` 加老 `collect()` 结果。
- `TestCmdStatus`：无采样器 → 警告行原文 + 老表；新鲜 latest.json →
  新表（不含"现场实探一次"，含"最后采样"/"判定"/extras 里的
  `stray_session`）。

```
$ python3 -m unittest tests.test_gpu_jobs -v
...
Ran 13 tests in 4.043s
OK
```

改动波及的全部单测（含 sampler/verdicts/launch 系列）整体跑了一遍：

```
$ python3 -m unittest discover -s tests -v 2>&1 | tail -5
...
Ran 92 tests in 6.890s
OK
```

`python3 run.py selfcheck`：worktree 里报 16 处"缺解释器/程序"，但这些
都是各 env 的 venv（`envs/appworld/venv` 等）——venv 不进 git，新建的
worktree 里没有这些目录，是 worktree 本身的产物隔离导致，不是本次改动
引入的问题。同一条 selfcheck 在主仓工作树（有真实 venv）上跑是
"63 任务 / 4 配方,全部就位"。本工单没碰 `run.py` 注册表（`gpu-jobs`
任务条目原样未动，只改了脚本内部实现），selfcheck 门槛按规程不是硬
要求，仍跑了一遍确认没有把台账相关的任务定义弄坏。

### 工单 Step 2 指定的手动验证

工作树里没有设 `NEW1_MONITOR_DIR`（走默认 NFS 路径）时，登录机上真的
有 T14 上线的采样器在跑，所以 `python3 run.py gpu-jobs` 直接走的是
新鲜分支（表头 `最后采样 07:23:52`），不是工单 Step 2 描述的"没有采样
器在跑"那个场景。为了照工单原文验证到位，另外补了两组：

**场景 A（`NEW1_MONITOR_DIR` 指到空 tmp 目录，模拟采样器不在跑）：**

```
$ NEW1_MONITOR_DIR=/tmp/t07-empty-mon python3 run.py gpu-jobs
采样器不在跑(最后采样 无),现场实探一次
台账为空——当前没有登记中的任务。发射走 gpu-run skill 会自动登记。
...
$ NEW1_MONITOR_DIR=/tmp/t07-empty-mon python3 run.py gpu-jobs json \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('json ok', d.get('sampler_stale'))"
json ok True
```

**场景 B（假的最新采样文件）：**

```
$ NEW1_MONITOR_DIR=/tmp/t07-fake-mon python3 run.py gpu-jobs
最后采样 07:24:35
JOB      HOST      GPU  判定  PROGRESS           RATE   TOK       ETA    SESSION
-------  --------  ---  --  -----------------  -----  --------  -----  -------------------
fakejob  tokyo106  0    健康  5/20 (25.0%) task  180/h  500k/12k  00:05  new1_fakejob_t106g0
```

判定、进度、速率、ETA、token 各列都渲染，表头带最后采样时刻，符合验收
要求 2。

**场景 C（已完成/已挂两种判定的提示行）：**

```
JOB      HOST  GPU  判定   PROGRESS             RATE  TOK  ETA  SESSION
-------  ----  ---  ---  -------------------  ----  ---  ---  -------
donejob  h     0    已完成  10/10 (100.0%) task  -     -    -    s0
deadjob  h     1    已挂   3/10 (30.0%) task    -     -    -    s1

已完成 = 全部分片判定已完成——该收尾了: python3 run.py gpu-jobs finish donejob
已挂 = session 没了，进度未到 100%，看日志: /tmp/deadjob.log
```

符合验收要求 3。三组临时 `NEW1_MONITOR_DIR` 目录（`/tmp/t07-empty-mon`
`/tmp/t07-fake-mon` `/tmp/t07-tips-mon`）验证完都删了。

## commit 清单

- `873f478` T07: gpu-jobs 三出口改读采样历史(新鲜用latest.json,过期亮警告退回实探)
  （改 `ops/gpu_jobs.py`，新增 `tests/test_gpu_jobs.py`，同步 `MAP.md`
  对应行）

## 自查发现与存疑

- **发现并当场改掉的 bug**：第一版 `已挂` 提示行写成了 f-string 里带
  `100%%`——那是从旧 `fmt_table()` 的 `%`-格式化字符串直接抄的写法，
  但 f-string 不做 `%` 转义，会字面输出两个百分号。自查时发现并改成
  `100%`（单个百分号），已在 commit 里。
- **存疑 1（RATE 单位切换阈值）**：工单原文"乘 3600 显示 `/h` 或保留
  `/s` 按数量级"没给精确的切换点。我定的是 `recent_rate >= 1` 用 `/s`，
  否则乘 3600 用 `/h`。这条阈值是我自己按常见速率量级估的，没有更权威
  的依据，如果跟其他出口（网页 `render_html` 固定用 `/s`，不做单位切
  换）的显示习惯不一致，需要用户确认是否要改。
- **存疑 2（提示行措辞）**：工单要求"措辞沿用现有 `fmt_table`"，但旧
  措辞里嵌了旧字段语义（"session 已退"/"进度 100%"），跟新的
  `verdict` 字段不是同一个判断依据。我保留了旧措辞的骨架（"该收尾
  了"/"看日志"两个关键短语原样留着），但整句不是逐字照抄。如果用户想
  要逐字复用旧句子，这里需要再调整措辞，不影响功能。
- **未触碰**：`ops/jobs.json`、`run.py` 注册表、`free`/`register`/
  `finish` 三个命令、`ops/sampler.py`、`ops/verdicts.py` 全部原样未动。

## 修复第 1 轮（评审 findings F1/F2）

分支：`ticket/20260808-par/T07`（同一分支），工作树
`new1-wt/20260808-par-T07-fix1`（已清理），commit `f5a864a`。

### F1（critical）—— read_latest() 补 shape/类型防护

**问题**：`read_latest()` 只 catch `(OSError, ValueError)`，挡住了
"文件不在" 和 "JSON 语法坏了" 两类，但 latest.json 一旦是合法 JSON
却不是预期 shape（顶层不是 dict，或 `sampled_at` 类型不对），会在
`read_latest()` 内部或调用方里抛未捕获异常，让 `status`/`watch`/
`json` 三个出口直接 Traceback 退出，而不是工单要求的"过期就打警告退回
实探"。

**怎么修的**：`read_latest()` 在 `json.load()` 成功之后加两层校验：

1. `latest` 不是 `dict`（比如顶层是数组）—— 直接返回 `(None, None)`，
   不再往下调 `latest.get(...)`。
2. `sampled_at` 字段存在但类型不是 `int`/`float`（含排除 `bool`，因为
   `bool` 是 `int` 子类但语义上不该被当时间戳用）—— 也返回
   `(None, None)`，不把畸形的 `latest` 透传给调用方（调用方的
   `_stale_warning()` 同样会在 `datetime.fromtimestamp()` 上对字符串
   类型的 `sampled_at` 炸掉，所以这里选择连 `latest` 一起吞掉，而不是
   只吞 `age_s`）。
3. `sampled_at` 字段整个缺失（原有语义，不是本轮新增）——保留原行为：
   返回 `(latest, None)`，`latest` 原样透传，调用方靠 `age_s is None`
   走过期分支。
4. 额外包了一层 `try/except (TypeError, OverflowError, OSError)` 包住
   `time.time() - sampled_at` 这一步算术本身，防御性覆盖极端数值（比如
   超大浮点数溢出）。

docstring 同步改写，把新覆盖的两类畸形 shape 写进"都返回 (None, None)"
的清单。

**怎么验证的**：

新增 3 个 `TestReadLatest` 用例（`tests/test_gpu_jobs.py`）：

- `test_sampled_at_wrong_type_returns_none_none`：`sampled_at` 是字符串
  → `(None, None)`。
- `test_top_level_not_dict_returns_none_none`：顶层是 `[]` → `(None, None)`。
- `test_missing_sampled_at_field_returns_latest_and_none_age`：
  `sampled_at` 字段整个缺失（区别于类型错）→ `(latest, None)`，确认原
  有行为没被新校验误伤。

按 finding 给的原始复现命令重跑，两个场景都从"直接 Traceback 退出"
变成"警告行 + 老表，exit 0"：

```
$ mkdir -p /tmp/t07f1-strtype /tmp/t07f1-toplist
$ echo '{"sampled_at":"x"}' > /tmp/t07f1-strtype/latest.json
$ echo '[]' > /tmp/t07f1-toplist/latest.json

$ NEW1_MONITOR_DIR=/tmp/t07f1-strtype python3 ops/gpu_jobs.py; echo "exit=$?"
采样器不在跑(最后采样 无),现场实探一次
台账为空——当前没有登记中的任务。发射走 gpu-run skill 会自动登记。
...
exit=0

$ NEW1_MONITOR_DIR=/tmp/t07f1-toplist python3 ops/gpu_jobs.py; echo "exit=$?"
采样器不在跑(最后采样 无),现场实探一次
台账为空——当前没有登记中的任务。发射走 gpu-run skill 会自动登记。
...
exit=0

$ NEW1_MONITOR_DIR=/tmp/t07f1-strtype python3 ops/gpu_jobs.py json; echo "exit=$?"
{
  "rows": [],
  "sampler_stale": true
}
exit=0

$ NEW1_MONITOR_DIR=/tmp/t07f1-toplist python3 ops/gpu_jobs.py json; echo "exit=$?"
{
  "rows": [],
  "sampler_stale": true
}
exit=0
```

`cmd_watch` 内部同一个 `read_latest()` 调用点（现在是共用的
`_print_table_from_latest_or_fallback()`），同一份防护同时覆盖三个出
口，未单独复测。

### F2（important）—— cmd_status/cmd_watch 的新鲜度分支去重

**问题**：`cmd_status()` 和 `cmd_watch()` 里各自内联了一份完全相同的
"读 latest → 新鲜渲染/过期回退" 5 行逻辑，`FRESH_S` 判定条件或渲染选
择要改，两处都要同步改，容易漏改一处。

**怎么修的**：把这段逻辑抽成新函数
`_print_table_from_latest_or_fallback()`：内部调 `read_latest()`，新
鲜就打印 `fmt_table_v2()` 并返回 `latest.get("extras") or {}`；否则打
印 `_stale_warning()`，走 `collect(with_extras=True)` + `fmt_table()`
，返回 `extras`。`cmd_status()`/`cmd_watch()` 各自只剩一行调用
`extras = _print_table_from_latest_or_fallback()`，后面打印 extras 提
示行的部分（两处提示文案本来就不同——status 是"漏 register?别的对话
在用?"，watch 是精简版）保留在各自函数里，没有强行合并成不该合并的
东西。

`cmd_json()` 的判断分支没有被这次抽取覆盖——它跟 status/watch 走的渲
染路径不同（json 序列化 vs 表格打印），finding 也只点了 status/watch
两处，没有把 json 算进重复范围，保持工单原范围不扩大改动。

**怎么验证的**：抽取是纯重构（同一段逻辑挪进函数），行为靠既有测试兜
底——`TestCmdStatus` 两个用例（无采样器/新鲜 latest.json）改动前后都
通过；未单独为 `cmd_watch` 补测试（原报告里 `cmd_watch` 就没有专门的
自动化测试，`while True` 循环不便单测，工单验收也没点名要 watch 专属
测试，保持原有测试覆盖边界不扩大）。

### 测试结果汇总

```
$ python3 -m unittest tests.test_gpu_jobs -v 2>&1 | tail -20
...
Ran 16 tests in 3.372s
OK
```

```
$ python3 -m unittest discover -s tests 2>&1 | grep -E "Ran |OK|FAILED"
Ran 95 tests in 6.615s
OK
```

（92 → 95：本轮新增 3 个 `TestReadLatest` 边界用例。）

`python3 run.py selfcheck`：worktree 里同样报 16 处"缺解释器/程序"，
与原报告记录的一致——都是各 env 的 venv 缺失，worktree 产物隔离导致，
不是本次改动引入。`gpu-jobs` 任务条目未动。

### commit 清单（本轮）

- `f5a864a` T07: 修复第 1 轮——read_latest() 补 shape/类型防护(F1),
  status/watch 新鲜度分支去重(F2)
  （改 `ops/gpu_jobs.py`：`read_latest()` 加 shape/类型校验，
  `cmd_status`/`cmd_watch` 抽出 `_print_table_from_latest_or_fallback()`；
  改 `tests/test_gpu_jobs.py`：新增 3 个 `TestReadLatest` 边界用例）

### 自查发现与存疑（本轮）

- 没有发现新的 bug。
- F1 修复时多想了一步：`sampled_at` 类型不对该不该保留 `latest` 只把
  `age_s` 置 `None`？选了连 `latest` 一起吞掉——原因是 `_stale_warning()`
  同样直接读 `latest.get("sampled_at")` 传给
  `datetime.fromtimestamp()`，如果只吞 `age_s` 不吞 `latest`，畸形的
  `sampled_at` 字符串会在 `_stale_warning()` 里换个地方炸，没有真正堵
  住 finding 描述的那类问题。这个判断不影响验收要求，记在这里供复核。
- F2 抽取时确认过 `cmd_json()` 不在 finding 范围内，没有顺手把它也拉
  进来合并——finding 原文只点名 `cmd_status`/`cmd_watch` 两处，保持范
  围不扩大。
