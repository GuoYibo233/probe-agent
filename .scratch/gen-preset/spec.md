# spec: 生成设置进配置文件（gen-preset）

Status: ready-for-agent
日期: 2026-08-20。裁决人 gyb，两个关键选择都选了 a：模型表搬进配置文件；
vLLM 发射也吃配置。目标是「py 文件只留逻辑，模型和设置放配置，以后能按名字
选很多套设置」。

## 现状（改动前）

gpt-oss 的生成设置散在五处，值不一致：

| 位置 | temperature | max_tokens | effort | stop |
|---|---|---|---|---|
| `envs/collect/common.py:48` Chat 缺省 | 0.0 | 8192 | None（harmony 提示词里落 medium） | 无 |
| `envs/collect/run_appworld.py:65` + `gen_launch.py:64` | 同上 | 同上 | chat 模式钉 high | 无 |
| `envs/collect/bfcl_gptoss/gpt_oss_chat.py:58-61` | BFCL 自带 | 16384（写死） | high（写死） | 无 |
| `pipeline/inject/live_appworld.py:76,387-388,549` | 0.0 | 8192 | high | `["<\|return\|>"]` |
| `pipeline/inject/replay_inject.py:812-813,1283` | 0.0 | 8192（CLI 缺省） | 不适用（续写） | `["<\|return\|>"]` |

模型路径的现状：`model_registry.py` 自称唯一映射但零个 import 方；
`envs/serve_logs/launch_vllm_*.py` 13 个发射器各自写死路径/端口/环境变量；
NFS 上 LFM2.5-350M-Base、Qwen3-0.6B-Base、MirrorAPI-Cache 三个在用的模型
没进注册表（MAP.md:177 记了前两个；MirrorAPI-Cache 在 run.py:414 写死）。

轨迹 meta 现在只记 env/task_id/model/instruction（run_appworld.py:100-102），
采样参数与 effort 全都没落痕。

## 设计

### 文件布局

```
configs/
  README.md          # 头一行写清与 pipeline/configs/ 的分工
  models.json        # 唯一模型地址映射（model_registry.py 改从这里读）
  presets/
    gptoss_chat_high.json      # 采集线 chat 口径（=现状 gen_launch 的 gptoss 附加旗标）
    gptoss_harmony_medium.json # 采集线 harmony 口径（=现状 run_appworld --api harmony 缺省）
    gptoss_bfcl_high.json      # BFCL 线（=现状 gpt_oss_chat.py 写死值）
    gptoss_live_high.json      # 活跑线（=现状 live_appworld 缺省）
    gptoss_replay.json         # 回放续写线（=现状 replay_inject run 缺省）
```

`pipeline/configs/` 管数据批次（哪些轨迹、怎么切分），`configs/` 管生成设置
（模型、服务端参数、采样参数）。两边 README 头一行互相指认。

### models.json 结构

```json
{
  "models": {"别名": {"path": "...", "note": "..."}},
  "aliases": {"qwen3.6": "qwen3.6-27b", "qwen3.5": "qwen3.5-27b"}
}
```

搬 `model_registry.py` 的 MODELS/ALIASES 全部条目，补三条：
LFM2.5-350M-Base、Qwen3-0.6B-Base、MirrorAPI-Cache（路径都在
`/net/tokyo100-10g/data/str01_01/y-guo/models/` 下，2026-08-20 ls 验证在盘）。
`model_registry.py` 改成读 json 的薄壳，`resolve()` 签名与行为一字不改，
`python3 model_registry.py <别名>` 的 CLI 行为也不改。

### 预设结构（configs/presets/<名>.json）

```json
{
  "desc": "一句话说明这套设置是哪条线的什么口径",
  "model": "gpt-oss-120b",
  "server": {
    "host": "tokyo108",
    "port": 8103,
    "served_model_name": "gpt-oss-120b",
    "gpu_memory_utilization": 0.92,
    "max_model_len": null,
    "env": {"VLLM_USE_FLASHINFER_SAMPLER": "0",
            "LD_LIBRARY_PATH": "/home/y-guo/reproduce/new1/envs/cuda-compat-13.0"},
    "extra_flags": ""
  },
  "client": {
    "api": "chat",
    "reasoning_effort": "high",
    "temperature": 0.0,
    "top_p": null,
    "max_tokens": 8192,
    "stop": null,
    "start_date": null,
    "seed": null
  }
}
```

server 节与 client 节都可省（活跑/回放预设不带 server 节，服务另起）。
null 等于「不指定，用调用方原有缺省」。GPU 卡号不进预设：挑卡是发射时
gpu-run 的事，`serve_preset.py` 用 `--gpu` 接。

### 读取器 preset_loader.py（仓库根，纯标准库）

- `load_models()` / `load_preset(name)` / `list_presets()`。
- `validate(preset)`：未知键、类型错、model 别名不在 models.json，三类都报错。
- `merge_client(cli, client_node, fallbacks)`：三层优先级
  CLI 显式值 > 预设值 > 原有缺省。cli 字典里 None 视为「没显式给」。
- 入口脚本里 argparse 原来带实义缺省的字段（如 live 的 --effort high、
  replay 的 --max-tokens 8192）改成 default=None，原缺省值挪进 fallbacks，
  这样才分得清「用户给了」和「落缺省」。效果不变。

### 七个入口接 --preset

run_appworld / run_alfworld / run_tales / run_tau2 / live_appworld /
replay_inject(run 子命令) 各加 `--preset 名`。合并后传给 Chat/请求体。
预设带 server 节时，`--model` 与 `--base-url` 可省：model 取
server.served_model_name，base_url 取 `http://{host}:{port}/v1`；
显式给了照旧压过。**不传 --preset 时一切行为与现在逐字节相同。**

bfcl 的 gpt_oss_chat.py 是拷进 BFCL venv 的文件，没有自己的 CLI，
改成读环境变量 `NEW1_PRESET_JSON`（预设文件的绝对路径）：设了就取
client 节的 max_tokens/reasoning_effort，没设走现在的写死值。

### 落痕

- Chat 加 `settings()` 方法，返回 api/model/temperature/max_tokens/
  reasoning_effort/start_date 字典；四个采集器把
  `gen_settings=chat.settings()` 和 `preset=<名或 None>` 塞进 TrajLog meta。
  annotate 侧 build.py 只按键取值，多键无害。
- live_appworld 的 meta dict（run_task 里）加 preset 名。
- serve_preset.py 发射时把预设全文抄一份到日志目录 `<session>.preset.json`。
- RUNMETA 自动抓 argv，preset 名随 argv 进 RUNMETA，不用额外做。
- run_id 带预设名写成 DATA.md 检查清单一条。

### serve_preset.py（仓库根）+ run.py 注册

读预设 server 节 + models.json 解析路径，拼与 launch_vllm_gptoss.py 同构的
ssh+tmux 命令。参数：`--preset` 必给、`--gpu` 必给、`--host/--port/--session`
覆盖预设、`--dry-run` 只打印不执行。session 缺省 `new1_vllm_<host>_<preset名>`。

run.py TASKS 加：

```python
"serve-preset": dict(stage="live", py="sys", script="serve_preset.py",
                     handoff=True, gpu=True, ...)
```

handoff+gpu：show 出命令、过脏树门禁、发射走 gpu-run。
gen_launch.py 的 `GPTOSS_CLIENT_EXTRA` 改成 `--preset gptoss_chat_high`
（展开后与旧串逐项等价），文档行同步。

### 验收

1. `run.py selfcheck` 扩展：逐份预设过 validate；models.json 每条有
   path+note、aliases 指向存在的键。
2. tests/test_preset.py（unittest，sys python3 可跑）：
   - 五份预设逐份 validate 通过；
   - resolve("gpt-oss-120b") 等于改前的路径字符串（防搬运抄错）；
   - merge_client 三层优先级各一个用例；
   - 等价性：gptoss_chat_high 展开后 == {api:chat, effort:high, temp:0.0,
     max_tokens:8192}；其余四份预设逐份对现状表；
   - serve_preset --dry-run 对 gptoss_chat_high 生成的 vllm serve 命令串,
     与 launch_vllm_gptoss.py 的 CMD 逐词对比（端口/旗标/环境变量）。
3. 各入口用各自 venv 的 python 跑 `--help` 或 py_compile，确认改后能 import。
4. 旧命令等价：用 appworld venv 起 run_appworld 的设置解析函数，
   `--preset gptoss_chat_high` 与 `--api chat --reasoning-effort high`
   两组 args 产出的 Chat 参数字典逐键相等。

### 不做的事

- 13 个旧 launch_vllm_*.py 一个不动，留作历史。
- 不给 qwen 线造预设（这次只管 gpt-oss；机制是通用的，加一份 json 就行）。
- vLLM 服务端参数里挑卡（GPU 号）不进预设。
- CELLS/EVAL_CELLS（训练/评测四格）不动，探针训练不是生成设置。

### 收尾清单

MAP.md（configs/ 与 serve_preset.py 与 preset_loader.py 三行、
model_registry 行更新、§已知坑里"缺条目"一条销掉）；
probe-pipeline references/stage-commands.md 与 extending.md 里
`--api chat --reasoning-effort high` 的位置回写 --preset 说法；
bfcl RUNBOOK.md 补 NEW1_PRESET_JSON；configs/README.md 与
pipeline/configs/README.md 互指；DATA.md 检查清单加一条；TIMELINE 补条目；
`run.py selfcheck` 全绿后代码+注册表+配置同一个 commit。
