# GPU 集群慢变量档案（new1）

> 只记不会分钟级变化的东西。**卡的实时占用永远现场探测**：
> `python ops/gpu_jobs.py free`（≈6 秒扫全集群）。
> 任务台账在 `ops/jobs.json`，只通过 `ops/gpu_jobs.py register/finish` 读写。
> 本文件更新时机：驱动升级、硬件变动、发现新坑。

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
