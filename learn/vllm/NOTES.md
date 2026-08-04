# 教学工作笔记

## 用户偏好（授课时必须守）

- 中文讲。规则以 `humanizer-gyb` skill 为准：白话先行、一段最多一个新词、
  自信断言不对冲、事实和解读分开且事实在前、每个数字带指代和出处。
- **不许猜。**没读过实际文件就不许对数字下判断。查不到理由就写"查不到"，不要圆一个说法出来。
  这是 CLAUDE.md 的铁律，在教学材料里同样成立。
- 课里的每个数字都要能 grep 回原始文件（源码行号 / 日志文件名 / 仓库路径）。
- 不夸。不评价他的问题好不好。

## 工作区约定

- 落点 `new1/learn/vllm/`，进 git（2026-08-04 用户拍板）。
- 课与速查卡都链 `assets/lesson.css`，测验用 `assets/quiz.js`。新课先读 `assets/` 再动手，
  别把同样的东西再写一遍。
- `build_artifact.py` 已挂进 `run.py`（`build-lesson-artifact`）并写进 `MAP.md` §3。
  当初说"教材不是程序、不挂 MAP"，出了这个转换器之后作废。

## 发布流程（用户要 artifact 时）

```
python3 run.py build-lesson-artifact --lesson learn/vllm/lessons/<课页>.html
python3 run.py build-lesson-artifact --lesson <同上> --check   # 确认同步
# 再用 Artifact 工具发 <名>.artifact.html
```

- `*.artifact.html` 是渲染产物，**手改一律作废**——改课页或 `assets/`，重跑转换器。
- 同一课重新发布必须复用同一个文件路径，才会更新到同一个 URL。
- favicon 固定 🔎，除非整门课换主题，否则不要改（用户靠图标认标签页）。
- **速查卡也要单独发 artifact**：课页里的 `class="local"` 链接在发布版上被降级成纯文本，
  卡没有自己的 URL 就等于在 artifact 上不存在。卡的 favicon 用 📇 与课的 🔎 区分。
- 已发布：

  | 页 | URL |
  |---|---|
  | 第 1 课 启动日志 | https://claude.ai/code/artifact/893a47d1-3eba-460f-97f9-6f5aeabee6b3 |
  | 第 2 课 前缀缓存与 token 账 | https://claude.ai/code/artifact/0928d158-fb92-4c16-9ff6-b1902bf37af1 |
  | 第 3 课 停止条件 | https://claude.ai/code/artifact/a8c5d973-bd30-4054-88ae-1ea44aae3801 |
  | 第 4 课 greedy 与可复现性 | https://claude.ai/code/artifact/a82f9232-f848-4a19-beac-ff66b1cdcefc |
  | 第 5 课 流式与中止 | https://claude.ai/code/artifact/970aa33c-31c7-4439-9167-4aa5e1f4d3bb |
  | 卡 启动日志解码 | https://claude.ai/code/artifact/76705f6f-f7e5-4bf4-b794-02fb1c03d13f |
  | 卡 token 账 | https://claude.ai/code/artifact/8898e677-f0ac-461e-a47b-2379f1ccc71d |
  | 卡 请求参数 | https://claude.ai/code/artifact/1f84040b-dd7c-4df4-bda6-bcbb406dd627 |

## 视觉规则（2026-08-04 定）

第一版样式是暖米色 + 衬线 + 陶土红，正是 AI 生成设计最扎堆的一套，已换掉。现在这套：
底色冷灰蓝、主色用终端 INFO 的青、日志里被点名的数字用琥珀、对错另走绿红。
标题无衬线 / 正文衬线 / 数据等宽三个角色分开。中文不内嵌字体（CJK 字库太大且 CSP 挡 CDN），
全部走系统字族。深浅两套主题都要照顾，`:root[data-theme=…]` 必须压得过 `prefers-color-scheme`。
body 背景必须显式写——artifact 外壳会注入浅色 body 样式。

## 数据源（写课时优先级从高到低）

1. `envs/vllm-env/lib/python3.12/site-packages/vllm/` — 我们真正在跑的 0.26.0 源码。
2. `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/*srv*.log` — 我们自己服务器的启动日志。
3. `docs.vllm.ai` — 官方文档，写的是最新版，跟 0.26.0 对不上的地方以源码为准。

## 待办与线索

- **一处没查清**：两台 H100 的 KV 内存都是 20.45 GiB，装得下的 token 数却不同
  （65,536 上限时 475,669；131,072 上限时 528,934）。同样的字节、不同的容量，
  怀疑跟滑窗层的分块方式有关，没验证。已在第 1 课里如实标为空白。
- **另一处没查清**：`launch_vllm_w0.py:10` 说 `--max-num-seqs` 默认 1024，
  0.26.0 源码里是 128。1024 的来源找不到（当时的 Qwen 服务日志已删）。
- `VLLM_USE_FLASHINFER_SAMPLER=0` 的作用查清了（envs.py:838-840），
  但我们为什么关它，仓库里没有任何记录。
- **原始产物已被清场删除**：`$NFS/envs/runs/aw_pathdiag/` 整个不在了，
  所以 08-02 那批 chat 采集的逐条 `prompt_tokens` 拿不到了，
  第 2 课只能用服务端日志的聚合数。以后要讲逐条数字，先确认产物还在。

## 已讲完

- 第 1 课 启动日志（2026-08-04）：五题全对，见 `learning-records/0002-*`。
- 第 2 课 前缀缓存与 token 账（2026-08-04）：讲了三个 prompt 长度、
  `Avg prompt throughput` 只数重算部分、命中率是 token 级 + 1000 条滑窗、
  `--enable-prompt-tokens-details` 默认关且我们从没给过。
  配套速查卡 `reference/token-accounting.html`。
- 第 3 课 停止条件（2026-08-04）：两套停止机制；停止串在解码后的文本上匹配，
  而那段文本受 `skip_special_tokens` 控制（默认 True）→ 特殊标记做的停止串静默失效。
  采集线 raw 模式的 `stop=["<|im_end|>"]` 就是空转的，靠 EOS token 兜底。
- 第 4 课 可复现性（2026-08-04）：temperature<1e-5 走 argmax，seed 无用；
  但 `VLLM_BATCH_INVARIANT` 默认关 → 结果随批组成变，所以并发是隐藏变量。
- 第 5 课 流式与中止（2026-08-04）：断连真的触发服务端 abort（async_llm.py:587-594），
  但 `enable_log_requests` 默认关，日志里 grep 不到；中止段的 usage 缺失只能用块数近似。
  配套速查卡 `reference/request-params.html`（服务于 3–5 三课）。

**这五课是一轮完整的：**启动日志 → token 账 → 停止条件 → 可复现性 → 流式中止，
串起来是一条请求从发出到收回的全程。要加课就是开新一轮，不是补这一轮的洞。

## 下一轮的候选（还没写，按与 MISSION 的贴合度排）

1. 工具调用与 harmony 通道：`--tool-call-parser`、gpt-oss 的 analysis/commentary/final
   三个通道在服务端怎么被切开，`think_span()` 依赖的到底是什么。
2. 调度与排队：`--max-num-seqs`、Running/Waiting 两个计数、抢占（preemption）
   什么时候发生，跟第 1 课那个并发上限是什么关系。（顺带能查掉 NOTES 里
   `--max-num-seqs` 1024 对不上 128 那个悬案。）
3. 量化与数值：`gpt_oss_mxfp4` 到底量化了哪些张量，KV cache dtype 是什么，
   跟第 4 课的数值抖动有没有叠加。
