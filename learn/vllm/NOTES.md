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
- 已发布：
  - 第 1 课 → https://claude.ai/code/artifact/893a47d1-3eba-460f-97f9-6f5aeabee6b3
  - 第 2 课 → https://claude.ai/code/artifact/0928d158-fb92-4c16-9ff6-b1902bf37af1

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

## 下一课的候选（按与 MISSION 的贴合度排）

1. 停止条件与特殊标记：`stop`、`skip_special_tokens=False`、`finish_reason`，
   对应 `replay_inject.py` 和 `live_appworld.py` 里最容易出静默错的地方。
2. 采样参数与可复现性：`temperature=0.0` 到底保不保证逐条一致，跨 batch size 为什么会飘
   （`sweep_theta.py` 的口径铁律就是被这件事逼出来的）。
3. 流式与中途 `close()`：`live_appworld.py` 的 `Stream` 靠断连让服务端停止解码，
   服务端到底什么时候真的释放槽位（这条要先去 0.26.0 源码里核实，别凭印象讲）。
