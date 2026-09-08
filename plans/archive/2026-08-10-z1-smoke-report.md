# z1 冒烟验收报告 — METHOD.md §5 三条线全部走通

2026-08-10。批次计划见 `plans/2026-08-10-z1-plan.md`。本报告只摆事实。
产物已按用户指示删除（删除清单见文末），数字的原始出处是删除前的 z1 产物，
关键中间数已转录进本报告与 `RESULTS.md`。

## 链路事实（从零到活跑）

| 段 | 事实 |
|---|---|
| 采集 | 20 题（train 12 / dev 4 / test_normal 4），gpt-oss-120b，`--api harmony --reasoning-effort high --start-date 2026-07-31`，全程约 44 分钟，token 账 in 1,308,335 / out 475,082。20/20 轨迹带 final 记录 |
| 标注 | 219 事件 / 8,572 样本 / 词表 7 工具；三堆 5,656 / 1,432 / 1,484；参数标注 9,420 条，found_rate 0.894；门禁 A/B/D 过、E 按官方题单跳过；调用串回读 219/219 |
| 训练 | ctool 与 cgen 在 tokyo105 A6000(48G) 双双 CUDA OOM，`--refire` 补射 tokyo108 H100(95G) 后跑通：ctool 4 分钟（best calA_weighted_acc 0.6199），cgen 69 分钟（best_val_ce 0.2344，val_exact_call 0.69） |
| 评测 | eval-tool-causal 出 REPLAY_REPORT：temperature 1.8227，chosen_theta {0.10: 0.75, 0.05: 0.775}，val 触发扫描 36 事件 |
| 活跑 | θ=0.65 手动（val 扫描该点 coverage 0.64 / trig_acc 0.74），test_normal 前 2 题（3d9a636_1/2），max-steps 30，三臂串行 |

## §5 三条验收线

**(i) 每次出手五样可指认：过。** 修复后 probe 臂出手 10 次（7+3）。spec 记录
逐条带齐：第几步（step）、哪个切口（cut，思考坐标）、多确信（conf，如 0.711）、
猜了什么并执行返回了什么（pred_label + gen_call + exec_out + exec_ok，
其中 step=4 一次 exec_ok=False，"报错也注"分支真实走到）、塞了什么（note 全文）。
同 step 的 gen 记录里 NOTE 在思考内、其后能看到模型接写
（样例接写开头："We also need phone app API docs."）。

**(ii) R3 token 比对：过，10/10。** 每个注入事件重建"注入后重发的整串"，
vLLM `prompt_token_ids` 回读的服务端分词与 openai_harmony 重编码逐位一致，
最长一串 11,091 token。修复前首轮同样 13/13（该检查衡量重发串自洽性，
与 render 口径差无关）。

**(iii) 空注入对照：数字如下，浮动容不容忍由人判。** chat 路 vs `--no-probe` 臂
同 2 题：3d9a636_1 前 2 步逐字相同、第 2 步分叉；3d9a636_2 前 3 步逐字相同、
第 3 步分叉。两个分叉步的 prompt token 数两臂完全相同（1456、5418），
分叉位在生成中途、前缀逐字相同之后的单个词（"prints" vs "will return"）。
与 `learn/vllm/lessons/0004`（贪心不可复现）现象一致。两臂任务成败一致
（两题均 success=False，failures 内容同类）。

## 冒烟抓出并修掉的两个真问题

1. **`/render` 与 chat 基线差 2 字符（修复 commit `99e538f` + 返工 `字误修正`）**：
   `build_prefix` 走模型 jinja 模板，模板第 248 行在 developer 正文与 `<|end|>`
   之间塞 `\n\n`；chat 端点的 harmony 渲染器与采集手拼串都没有（hcap 已验
   两者逐字相同）。修法：渲染后只剥 developer 段末尾这一处。修复前 (iii)
   两题首分叉步都是 0；修复后 `/render` 与 chat 服务端渲染逐字节全等（1533=1533），
   首分叉退到 2/3 步。首次提交的正则把 `\1\2` 写成 `\1\3`（/render 500），
   本地实跑 build_prefix 验证后返工——124 单测没有一个盖住 build_prefix，测试缺口记录在案。
2. **probe_server `/health` 回显 bug（同 commit 修）**：config() 回显模块常量
   默认路径（`c1_*`，已不存在），不是实际装载路径；装载一直走真实入参
   （z1 服务温度 1.8227 只出自 z1 报告可证）。修后回显真实路径。

## 顺带的运行时事实

- vLLM 服务两次发射就绪耗时 306s / ~120s（NFS 编译缓存热）。
- 采样器事故链首次真实触发：两次训练 OOM 死亡均被判"已挂"写入
  `incidents.jsonl`（含此前 mth_datepin 手杀共 3 条），事故 agent 均因
  cron 环境 PATH 解析不到 `claude` 未拉起（`spawn_error` 照实入账）——
  与 `ops/gpu_state.md` 预告的缺口逐字吻合。
- gptoss 轨迹训 ctool/cgen（无 fire-head、默认超参）在 48G A6000 直接 OOM，
  95G H100 可跑——比 skill 里"fire-head 双前向才 OOM"的记录更宽。
- 采集/训练心跳、`launch --refire`、`--service` 探活全链在真实任务上走了一遍。

## 删除清单执行记录

按用户指示删除（见文末命令），保留：本报告、批次计划、config、
`RESULTS.md`/`runs.jsonl` 记录、两个修复 commit。
