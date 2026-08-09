# GPU 集群慢变量档案（new1）

> 只记不会分钟级变化的东西。**卡的实时占用永远现场探测**：
> `python3 run.py gpu-jobs free`（≈6 秒扫全集群，仓库根执行）。
> 任务台账在 `ops/jobs.json`，只通过 `run.py gpu-jobs register/finish` 读写。
> 登录机常驻采样器算判定：`python3 run.py sampler --interval 60 --port 8377`；
> 网页 `http://localhost:8377`（ssh 端口转发）、`/json` 出机器可读判定。
> 本文件更新时机：驱动升级、硬件变动、发现新坑。

## 采样器部署事实（2026-08-08 上线，2026-08-09 final-review 补记）

- 常驻 tmux session 名 `new1_sampler`，跑在登录机，cwd 指主仓
  `/home/y-guo/reproduce/new1`（不是任何工作树——工作树收尾会删，指过去
  就是悬空）。
- 看门狗是 crontab，每 5 分钟探一次 session、不在就拉回来（`crontab -l`
  实测原文，2026-08-09）：
  `*/5 * * * * tmux has-session -t new1_sampler 2>/dev/null || tmux new-session -d -s new1_sampler 'cd /home/y-guo/reproduce/new1 && python3 run.py sampler 2>&1 | tee -a /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log'`。
  `cd` 在 tmux 起的 session 内部执行——cron 的默认 cwd 是 `$HOME`，不加
  这个 `cd` 会找不到 `run.py`。
- **cron 环境的 PATH 通常不继承登录 shell 的配置**——事故 agent
  （`ops/sampler.py` 的 `spawn_agent`）靠 `shutil.which("claude")`
  解析绝对路径，PATH 里找不到 `claude` 就会直接 `raise RuntimeError`
  （被 `maybe_trigger_incidents` 接住记进事故记录，不会拖垮采样循环，
  但那一次事故也就没有真的拉起 agent）。crontab 那一行要么把
  `claude` 所在目录写进 `PATH=` 前缀，要么确认 cron 默认 PATH 已经
  覆盖到它，否则事故 agent 这条链在 cron 环境下永远走不通。
- 采样器自己的日志 tee 到 NFS：
  `/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor/sampler.log`。
- **端口 8377 已经被这个常驻进程占用**——手敲
  `python3 run.py sampler --port 8377` 或裸起一个新的 `sampler.py` 会跟
  它冲突（`OSError: Address already in use`），排错/临时起第二份用别的端口。
- T12（事故触发）、T13（vLLM 服务档）合并进 main 后，这个常驻 session
  跑的还是合并前的代码，需要重启一次才吃到新代码——final-review 这一批
  改动（C1/C3 的 spawn_agent、sample_once 落盘顺序）合入后同理，由主会话
  记账重启，不在本次修复范围内。

勘察日期：2026-07-29（实测，非道听途说）

## 硬件与驱动

| Host | 别名 | GPUs | 单卡显存 | 驱动 | CUDA | Python | RAM |
|---|---|---|---|---|---|---|---|
| tokyo105 | shiga | 8× RTX A6000 (idx 0-7) | 48G | 575.64.03 | **12.9** | 3.10.12 | 251G |
| tokyo106 | — | 10× RTX A6000 (idx 0-9) | 48G | 535.230.02 | **12.2** | 3.10.12 | 251G |
| tokyo107 | — | 4× RTX 6000 Ada (idx 0-3) | 48G | 535.113.01 | **12.2** | 3.10.12 | 251G |
| tokyo108 | saitama | 3× H100 NVL (idx 0-2, 95G) + 3× H200 NVL (idx 3-5, 143G) | 见左 | 570.195.03 | **12.8** | 3.12.3 | 503G |

## 已知的坑

1. **tokyo106/107 驱动只到 CUDA 12.2**——需要 cu124+ 轮子的新版
   vLLM/torch 可能在这两台上报驱动不兼容；遇到装包报 CUDA 版本错，
   先想到这一条，换 tokyo105/108 或降轮子版本。
   - **实测例外（2026-07-29）**：cu128 轮子的 torch 在 106/107 上照常跑得动
     （CUDA 次版本前向兼容生效），不要因为这条就一律绕开这两台；
     算上它们，训练池实际可用 19 张卡。只有真报驱动错时才降轮子版本。
2. **别名去重**：shiga=tokyo105、saitama=tokyo108，物理机只有四台。
   探测和分配一律用 tokyo 名，绝不把别名当第五台机器双重占卡。
3. **tokyo108 卡型混插**：idx 0-2 是 H100(95G)，idx 3-5 是 H200(143G)，
   按显存需求选 idx，别默认从 0 开始拿。
4. `/home` 全集群 NFS 共享，路径处处一致；日志本地读即可，不用 ssh。
5. HF 缓存在 NFS：`HF_HOME=/net/tokyo100-10g/data/str01_01/y-guo/hf`
   （Qwen3.5-4B/9B、Qwen3 全家、Qwen2.5 全家已缓存）；模型权重也下这里，不放 /home。
6. hf_server 端口约定：`8712 + gpu_id`（tokyo108 上的历史约定）。

## 池外机器（别用）

- tokyo104：8× Quadro RTX 8000 46G，Turing 老卡无 bf16，最后手段。
- tokyo101：驱动坏（NVML mismatch），需重启，别动。
- tokyo100/102/103/199、yebis、setagaya：ssh 不通（2026-07-25 实测）。
