# 缓存复用训练器的注意力前向用形态 A 加 mem-efficient 内核（2026-08-28，CPU 与 GPU 验证都已过，冒烟与终验的结论在第七、八节，学习率扫描的排卡与网格在第九节）

这份文件回答 plan-8-28 交下来的四个问题：打包前向在当前版本的 HF Qwen3 加 torch 下会落到哪个注意力内核、math 内核的显存要多少；备选的缓存接力形态能不能带梯度、能不能配 LoRA；两种形态在 CPU 上和旧训练器逐行前向的 loss 差多少；bf16 下的对齐容差怎么定。六节按顺序是：版本事实、推荐的形态与掩码构造、内核选择与显存估算、CPU 等价验证结果、bf16 容差建议、GPU 验证清单。全篇的名字定死：「旧训练器」指 `pipeline/train/train_causal_callgen.py` 的逐行前向；「形态 A」指打包一次前向；「形态 B」指缓存接力；「前缀」指事件全文的 token 序列；「目标段」指一行里公共前缀之后的尾巴加目标串；「内核」指 torch 的 `scaled_dot_product_attention`（下面简称 sdpa）背后四种实现之一：flash、mem-efficient、math、cudnn。

所有脚本在 `/home/y-guo/.claude/jobs/b39c625e/tmp/a2/`（任务临时目录，任务删除的时候会一起清掉），在仓库根用 `cprobe-env/bin/python` 跑。仓库代码一行没改。

## 一、版本事实全部从 cprobe-env 里装的代码和头文件里读出来

- python 3.11.15，torch 2.11.0+cu128，transformers 5.14.1，peft 0.20.0。flash-attn 没有装（`plans/2026-08-28-plan.md` 第 9.4 节）。
- Qwen3-0.6B-Base 的 `config.json`：28 层，隐藏维 1024，16 个注意力头，8 个 KV 头，`head_dim` 128，`attention_dropout` 0.0，没有滑窗层。
- 旧训练器加载权重用 float32（`train_causal_callgen.py` 第 225 行），训练前向套 `torch.autocast("cuda", dtype=torch.bfloat16)`（第 489 行），注意力实现没有指定，加载出来是 `sdpa`（第 9.4 节核对过，这次 CPU 脚本打印的也是 `attn_impl=sdpa`）。
- 4 维掩码怎么传：`transformers/masking_utils.py` 第 817 到 819 行，`attention_mask` 是 4 维张量（或者 `BlockMask`）就原样返回，不再做任何加工；`models/qwen3/modeling_qwen3.py` 第 414 行把原样返回的掩码当成 `full_attention` 层的掩码，第 426 行逐层传进注意力。所以 4 维掩码直接进 sdpa，dtype 由调用方定（bool 的 True 表示可以看；浮点的 0 表示可以看、-inf 表示不可以看，两种 torch 都接）。
- 有掩码的时候 sdpa 走什么参数：`transformers/integrations/sdpa_attention.py` 第 97 到 100 行，掩码非空就 `repeat_kv` 把 K、V 从 8 个头复制成 16 个头（第 28 到 38 行的 `use_gqa_in_sdpa` 只在掩码为空的时候才用 `enable_gqa`）；第 120 行 `is_causal` 在掩码非空时置 False；第 154 到 163 行调 `torch.nn.functional.scaled_dot_product_attention(query, key, value, attn_mask=attention_mask, dropout_p=dropout, scale=scaling, is_causal=is_causal)`。
- position_ids 怎么流：`modeling_qwen3.py` 第 397 到 400 行只在调用方没给的时候生成 `arange`，第 421 行 `self.rotary_emb(hidden_states, position_ids)` 直接吃调用方给的 `[B, L]` 张量，每个位置的旋转角度只由调用方给的 position_ids 决定。
- torch 里内核的默认优先级：`torch._C._get_sdp_priority_order()` 返回 `[1, 2, 0, 3, 4]`，对应 `SDPBackend` 的 FLASH_ATTENTION、EFFICIENT_ATTENTION、MATH、CUDNN_ATTENTION、OVERRIDEABLE。四个开关 `flash_sdp_enabled / mem_efficient_sdp_enabled / math_sdp_enabled / cudnn_sdp_enabled` 默认全 True。
- flash 内核对掩码的态度：`torch/include/ATen/native/transformers/sdp_utils_cpp.h` 第 260 到 263 行 `check_for_attn_mask`，掩码非空直接拒绝（警告原文 `Flash Attention does not support non-null attn_mask.`）。第 270 到 292 行 `check_attn_mask_shape`：掩码要求 `requires_grad` 为假、形状是 2 维或者 4 维，并且批和头两维各自为 1 或者等于 q 的批和头数。第 493 到 526 行：GPU 上的融合内核要求掩码最后一维 stride 为 1。
- autocast 名单：`torch/include/ATen/autocast_mode.h` 第 853 行把 `scaled_dot_product_attention` 列在 `AT_FORALL_LOWER_PRECISION_FP` 里，所以 bf16 autocast 下进 sdpa 的 q、k、v 和浮点掩码都会被转成 bf16。CPU 上实测同样成立（fp32 输入在 `torch.autocast("cpu", dtype=torch.bfloat16)` 里出来是 bf16）。
- math 内核的中间量精度：sdpa 的 docstring 原文 `For math backend, all intermediates are kept in torch.float if inputs are in torch.half or torch.bfloat16.`。CPU 上用 `saved_tensors_hooks` 实测：bf16 输入、`sdpa_kernel([SDPBackend.MATH])`，反向传播保存的注意力矩阵是 `(1, 16, L, L)` 的 float32，每次调用一份（同一存储的两个视图，只算一份）。
- flex_attention 在 cprobe-env 里可用：`transformers.utils.is_torch_flex_attn_available()` 返回 True，`torch.nn.attention.flex_attention` 能 import。HF 的接法在 `transformers/integrations/flex_attention.py`：第 92 行用 `torch.compile(flex_attention)` 编译一次并缓存，第 282 到 288 行接受 `BlockMask` 或者一张 4 维加性掩码（4 维加性掩码会被当成 `score_mod` 逐元素加进分数，不省算力），第 274 行要求 dropout 为 0（Qwen3 的 attention_dropout 正好是 0）。`BlockMask.shape` 返回 4 元组，所以 `masking_utils.py` 第 818 行的原样放行对 `BlockMask` 同样成立。
- 缓存对象：`transformers/cache_utils.py` 第 143 到 144 行 `DynamicLayer.update` 用 `torch.cat` 把新 K、V 接到旧的后面，没有 detach、没有 no_grad，梯度链保留；第 163 行 `crop` 把缓存切短。
- 梯度检查点和缓存互斥：`transformers/modeling_layers.py` 第 77 到 84 行，训练态开了梯度检查点的时候，`use_cache=True` 被强制改成 False 并打警告。
- 带缓存一次喂多个 token 的掩码：`masking_utils.py` 第 235 到 278 行 `_ignore_causal_mask_sdpa`，只有 `q_length == 1`、或者 `kv_length == q_length`、或者缓存为空的时候才跳过建掩码；缓存非空并且 q 长度大于 1 的情形会正常建一张右下对齐的因果掩码，形态 B 不会撞上 ctool 文档头里记的 LFM2 分块增量静默算错（那是 LFM2 卷积层的问题，Qwen3 只有注意力）。
- `logits_to_keep` 接 1 维下标张量：`modeling_qwen3.py` 第 504 到 505 行，`self.lm_head(hidden_states[:, slice_indices, :])`，可以只在 loss 位过输出层。

## 二、推荐的形态 A 是打包一次前向，配一张掩码和一份自定义 position_ids

### 2.1 序列由前缀接上 K 个目标段组成

一个事件的序列是「前缀」接上 K 个目标段。前缀是事件全文（最大 sent_idx 那一行的 text）按 `add_special_tokens=False` 分出来的 P 个 token。第 k 行按旧训练器的办法分词：`prompt_k = tok(text_k + "\n[CALL] ")`，`tgt_k = tok(label_call_k) + [eos]`；`p_k` 是 `prompt_k` 和前缀从头逐个比较、相同部分的长度（草案 2.4 节的公共前缀规则）；尾巴 `tail_k = prompt_k[p_k:]`；目标段 `seg_k = tail_k + tgt_k`。这次抽的 34 行里 `len(prompt_k) - p_k` 是 5（32 行）或者 4（2 行），也就是尾巴正好是分隔串的 5 个 token，或者分隔串首个换行和行文本末尾并成一个 token 之后剩下的 4 个；没有出现尾巴为空的行。

### 2.2 掩码、position_ids 和 loss 位按下面的代码构造（脚本 `packed_common.py` 的 `build_packed` 原样精简）

```python
P = len(full_ids); seq = list(full_ids); pos = list(range(P)); segs = []
for k, r in enumerate(rows):
    p = lcp(r["prompt"], full_ids)           # 公共前缀长度
    tail = r["prompt"][p:]; start = len(seq); seg = tail + r["tgt"]
    seq += seg; pos += list(range(p, p + len(seg)))          # 位置编号从 p 接着数
    segs.append(dict(p=p, start=start, end=start + len(seg), n_tail=len(tail)))
L = len(seq)
allow = torch.zeros(L, L, dtype=torch.bool)
allow[:P, :P] = torch.ones(P, P, dtype=torch.bool).tril()   # 前缀内因果
for s in segs:
    allow[s["start"]:s["end"], :s["p"]] = True               # 第 k 段看前缀的前 p_k 位
    n = s["end"] - s["start"]
    allow[s["start"]:s["end"], s["start"]:s["end"]] = torch.ones(n, n, dtype=torch.bool).tril()  # 段内因果
# loss 位:logits 第 j 位预测 seq[j+1];目标 token t 的预测位是目标 token t 前一个 token 的位置
qpos, ys, row_id = [], [], []
for i, (r, s) in enumerate(zip(rows, segs)):
    for t, y in enumerate(r["tgt"]):
        j = s["p"] - 1 if (t == 0 and s["n_tail"] == 0) else s["start"] + s["n_tail"] + t - 1
        qpos.append(j); ys.append(y); row_id.append(i)
```

前向和 loss：

```python
out = model(input_ids=seq[None], attention_mask=allow[None, None],     # bool, [1, 1, L, L]
            position_ids=pos[None], use_cache=False,
            logits_to_keep=torch.tensor(sorted(set(qpos))))            # 只在 loss 位过输出层
ce = F.cross_entropy(out.logits[0, col_of(qpos)].float(), torch.tensor(ys), reduction="none")
row_ce = index_add(ce, row_id) / count(row_id)                        # 每行 = 目标 token CE 的平均,与 inst_ce 同口径
loss = (row_ce * w).sum() / w.sum()                                    # 逻辑小批内按 w 加权(草案 2.2)
```

labels 不用摆成移位一格的 `[B, L]` 张量，直接用 `(qpos, ys, row_id)` 三个下标表。理由是尾巴为空的行首个目标 token 的预测位落在前缀里，移位表达不了尾巴为空的情况，下标表可以。

### 2.3 一批放多个事件的时候序列沿批维摆

按 token 预算把几个事件放进一个物理批（草案 2.2 的物理层）的时候，序列沿批维摆，各自补到批内最长的 L：`input_ids [B, L]`、`position_ids [B, L]`、掩码 `[B, 1, L, L]`。pad 位的掩码行只让 pad 自己看自己（全 False 的行会让 softmax 出 NaN），pad 位不进 loss 位表。不要把几个事件串成一条更长的序列，原因是注意力算力随 L 平方涨，沿批维摆才是线性的。

### 2.4 掩码用 bf16 加性张量，每个物理批造一次，L 补到 16 的倍数

CPU 上 bool 掩码和 0 / -inf 的浮点掩码算出来的 loss 逐位相同（第四节）。GPU 上 bool 掩码和浮点掩码差在显存：`saved_tensors_hooks` 实测（CPU 版 flash 内核，bf16），bool 掩码每次 sdpa 调用都被转成一份新的 bf16 加性掩码并保存到反向传播，两次调用保存了两份不同存储；直接传现成的 bf16 加性掩码，两次调用保存的是同一份存储。折到 28 层：L 为 9,100 的时候 bool 掩码要多留 28 × 9,100² × 2 字节约 4.6 GB，bf16 加性掩码只留一份 166 MB。所以推荐每个物理批造一次 bf16 的加性掩码（0 / -inf），不在每层重造。mem-efficient 内核还有一条对齐要求，torch v2.11.0 源码 `aten/src/ATen/native/transformers/attention.cpp` 的 `preprocess_mask` 先用 `aligned_tensor<16>` 检查掩码除最后一维以外各维的 stride 都是 16 的倍数、最后一维 stride 为 1，不满足就由 `pad_bias` 用 `at::pad` 在最后一维补齐再切片回来（复制一份），然后 `expand` 到 `[批, 头, L, L]`（视图，不复制）；同一个文件里 bool 掩码在进内核之前先经 `convert_boolean_attn_mask` 用 `at::where` 转成 0 / -inf 的浮点张量，每次调用新造一份。所以掩码造成 bf16 加性、连续、L 是 16 的倍数，28 层就共用一份存储；实际差多少显存在 GPU 上量（第六节第 5 步）。

### 2.5 备选形态 B（缓存接力）能带梯度，但是留作对照不上训练

形态 B 是：前缀 `use_cache=True` 过一遍拿到 `DynamicCache`，各行按 `p_k` 从大到小排，每行先 `cache.crop(p_k)` 再把目标段作为一条新输入接着算，position_ids 从 `p_k` 接着数。CPU 实测（第四节的 form_b 项）：3 行的 loss 和旧训练器最大差 1.3e-6，loss 反向之后前缀输入嵌入的梯度非空，463 个前缀位置里 462 个梯度非零（唯一为零的是前缀最后一个 token，没有任何目标段看前缀最后一个 token，前缀最后一个 token 也不在 loss 位里）。所以形态 B 在 transformers 5.14.1 里能带梯度。LoRA 下同样能用：peft 只换 nn.Linear，不碰 forward 的参数。

形态 B 的两个硬伤是从代码读出来的。第一，`modeling_layers.py` 第 82 到 84 行让梯度检查点和 `use_cache` 互斥，1.7B 和 4B 在 48G 卡上靠 `--grad-ckpt` 才装得下（`plans/2026-08-22-np821-exec-worklog.md` 的经验），形态 B 等于关掉了 `--grad-ckpt`。第二，`DynamicLayer.update` 每次都 `torch.cat` 出一份新的 K、V 张量，cat 出来的 K、V 张量会被所在段的注意力反向保存，所以 45 段各自留一份 `p_k` 长的 K、V 副本：按平均 `p_k` 4,000、8 个 KV 头、head_dim 128、bf16、K 和 V 两份、28 层算，一个 8192 的事件要留 45 × 4,000 × 8 × 128 × 2 × 2 × 28 字节约 20 GB，形态 A 保存的 K、V 只有整条序列的一份（repeat_kv 之后 16 头），9,100 × 16 × 128 × 2 × 2 × 28 字节约 2.1 GB。把 45 段合成一个 padded batch 接缓存会更糟：缓存要沿批维扩成 45 份再 cat，每层 45 × 8 × 8,300 × 128 × 2 × 2 字节约 1.5 GB，28 层约 43 GB。

裁决：用形态 A。形态 A 和 ctool 的整段一次前向只差一张掩码和一份 position_ids，梯度检查点、LoRA、按 token 预算沿批维组批都直接可用，CPU 上三样都验证过。形态 B 只留作对照实现，不上训练。

## 三、内核显式钉在 mem-efficient，math 内核在 8192 上装不下

### 3.1 形态 A 在 GPU 上要显式钉 mem-efficient（默认顺序在 H100 上落到 cuDNN，见第七节）

按第一节的事实推：掩码非空，flash 直接拒绝；优先级下一个是 mem-efficient，mem-efficient 接 4 维掩码（bool 或者浮点），head_dim 128、bf16、dropout 0、掩码不带梯度、批和头两维为 1，都在允许范围里；只要 mem-efficient 的资格检查通过，就轮不到 math。cudnn 排在 math 后面，默认情况下碰不到。第七节的 GPU 实测推翻了默认选择这一半：H100 上默认选择落到了 cuDNN，mem-efficient 只有显式钉才会用上。推断的每一条都要在 GPU 上用 `torch.backends.cuda.can_use_efficient_attention(SDPAParams(q, k, v, mask, 0.0, False, False), debug=True)` 对真实形状问一遍，再用 profiler 看内核名（第六节第 1 到 3 步，脚本 `gpu_kernel_check.py`）。

训练代码里推荐把前向和反向包在 `with torch.nn.attention.sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION]):` 里。这样 mem-efficient 不能用的时候 torch 直接报错，而不是悄悄退到 math 然后在 8192 的事件上爆显存。

### 3.2 math 内核在 8192 上要留住 120 GB 的注意力矩阵

math 内核每层保存一份 `(1, 16, L, L)` 的 float32 注意力矩阵（第一节实测），也就是每层 16 × L² × 4 字节，28 层合计 28 × 16 × L² × 4 字节。三个 L 的账：

| 序列长 L | 每层保存的注意力矩阵 | 28 层合计 |
|---|---|---|
| 8,192（只有前缀） | 4.29 GB（4.00 GiB） | 120.3 GB（112.0 GiB） |
| 9,100（8192 前缀 + 45 段 × 约 20 个 token） | 5.30 GB（4.94 GiB） | 148.4 GB（138.2 GiB） |
| 10,000 | 6.40 GB（5.96 GiB） | 179.2 GB（166.9 GiB） |

这三个数只是反向传播要留住的部分；前向算每一层的时候，分数矩阵、加掩码之后的副本、softmax 输出会同时存在，瞬时峰值还要再高。H100 一共 95,830 MiB（93.6 GiB，`plans/2026-08-28-plan.md` 第 9.2 节），H200 143,771 MiB（140.4 GiB）。math 内核在 L 为 4,096 的时候已经要 30 GB，8192 起步的形态 A 在 math 内核上任何一张卡都装不下。

### 3.3 mem-efficient 内核留住的激活随 L 线性涨，9,100 的事件约 33 GB

mem-efficient 不实体化 L × L × 头数的矩阵，反向保存的是每个 query 位置的 logsumexp（16 × L 个数）和 K、V 本身。随 L 平方涨的只剩掩码：bool 一份 L² 字节，bf16 加性一份 2 L² 字节，L 为 9,100 的时候分别是 83 MB 和 166 MB；bool 掩码按 2.4 节的实测会被每层各转一份，要多留约 4.6 GB。其余激活随 L 线性涨，每个 token 的字节数在 CPU 上用 `saved_tensors_hooks` 量过：

脚本 `mem_probe.py`（结果 `mem_probe.json`）在 CPU 上把形态 A 的前向过一遍（随机 token，前缀加 8 段各 20 个 token），用 `saved_tensors_hooks` 记下自动求导为反向传播保存的每一个张量，按存储去重，最后两维都等于 L 的归「L × L 类」，其余归「其他类」。L 为 2,048 的一组（L 为 1,024 的那组把 1,024 维的隐状态和 1,024 × 1,024 的权重误归进了 L × L 类，只用来做差分）：

| 内核 | 精度 | L × L 类保存的张量 | L × L 类合计 | 折成每层每 L² 的字节 | 其他类合计 |
|---|---|---|---|---|---|
| flash-cpu（GPU 上 mem-efficient 的替身） | bf16 autocast | 1 份 `(1, 1, 2048, 2048)` bf16 掩码 | 8.4 MB | 0.07 | 6.23 GB |
| math | bf16 autocast | 28 份 `(1, 16, 2048, 2048)` fp32 加 28 份 `(2048, 2048)` bf16 掩码副本 | 7.75 GB | 66.0（64 是注意力矩阵，2 是掩码副本） | 6.69 GB |
| flash-cpu | fp32 | 1 份 fp32 掩码 | 16.8 MB | 0.14 | 10.00 GB |
| math | fp32 | 28 份 fp32 注意力矩阵加 28 份 fp32 掩码副本 | 7.99 GB | 68.0 | 9.53 GB |

math 内核的 64 字节每 L² 每层就是 16 个头 × 4 字节，和 3.2 节的解析式一致；math 路径还会每层各复制一份掩码，flash-cpu 接现成的浮点掩码 28 层共用一份。

其他类里有一块不随 L 变的固定量（autocast 给 0.6B 权重做的 bf16 副本，反向要用），所以每 token 的字节数用 L 为 1,024 和 2,048 两点做差分（1,024 那点把误归的隐状态加回来）：bf16 autocast 下每 token 2.42 MB，固定量约 1.2 GB；fp32 下每 token 3.68 MB，固定量约 2.4 GB（fp32 下这块是权重本体，不另占显存）。外推到 GPU 训练（bf16 autocast，mem-efficient）：L 为 8,192 的时候留住的激活约 19.8 加 1.2 等于 21 GB；9,100 的时候 22.0 加 1.2 等于 23 GB；10,000 的时候 24.2 加 1.2 等于 25 GB。再加静态部分：fp32 权重 2.4 GB、梯度 2.4 GB、AdamW 两份状态 4.8 GB，合计 9.6 GB。一个 9,100 的事件单独成批，留住的总量约 33 GB，H100 的 93.6 GiB 剩六成。33 GB 是「留住的」不是「峰值」：旧训练器每批 4 条 4096 的 A_h100 冒烟按同一套系数算是留住约 55 GB（16,384 个 token × 2.42 MB 加全位置 logits 5.0 GB 加静态 9.6 GB），实测峰值 80.0 GB（第 9.2 节），峰值比留住的量高四成多，瞬时张量和分配器碎片都在里面。所以 9,100 的峰值按四到五成余量估在 45 到 50 GB，最终以第六节第 2 步量到的数为准。

另一笔随 L 涨的账是输出层：旧训练器对全部位置算词表 logits（第 9.4 节），L 为 9,100 的时候 bf16 logits 是 9,100 × 151,936 × 2 字节约 2.8 GB；形态 A 用 `logits_to_keep` 只在 loss 位算，45 行约 900 个目标 token 只要 0.27 GB，CE 里 `.float()` 的那份也只有 0.55 GB。

### 3.4 flex_attention 省一半注意力算力，但是要编译，留作后手

flex 的好处是块稀疏：形态 A 的掩码里，前缀因果去掉一半、各目标段只看自己和前缀前 p_k 位，flex 按 128 × 128 的块跳过全 False 的块，注意力算力大约减半；mem-efficient 接显式掩码的时候要把 L² 个分数全算出来再加掩码，不省算力。代价有三条：第一，要在 GPU 节点上 `torch.compile` 出 Triton 内核（HF 在 `flex_attention.py` 第 92 行编译一次并缓存，形状变了会重编译，直到 dynamo 转成动态形状），首次编译要几十秒到几分钟，np821 的训练环境没有验证过 inductor 能编译；第二，每个物理批要在 GPU 上 `create_block_mask` 造一次块掩码，本身是几毫秒到几十毫秒的开销；第三，模型要以 `attn_implementation="flex_attention"` 加载，评测端和 ctool 都还是 sdpa，两条路的数值会有 bf16 量级的差。

算力账（粗算）：注意力每层前向约 4 × L² × 128 × 16 次浮点运算，28 层，前向加反向按前向的 3.5 倍算（mem-efficient 的反向要重算一遍前向）；线性层按非嵌入参数 0.44B、每个 token 前向 2 × 0.44e9、前向加反向 3 倍算。L 为 9,100 的时候注意力 6.6e13、线性层 2.4e13，注意力占七成；中位数事件（前缀 1,271 加 45 段约 2,200 个 token）注意力 3.9e12、线性层 5.8e12，注意力占四成。flex 把注意力算力减半，折到整个事件是省两成（中位数事件）到三成半（最长事件）。

裁决：第一版用 sdpa 加 mem-efficient，原因是 mem-efficient 的显存已经够用（3.3 节），而 inductor 编译链在训练节点上没有验证过；flex 留作冒烟之后的速度优化，预期收益两到三成半，要不要做等冒烟量出每秒行数再定。形态 A 的 `allow` 矩阵可以直接翻成 flex 的 `mask_mod`：预先造三个长 L 的张量 `seg_of`（前缀为 0、第 k 段为 k）、`p_of`（每个位置所属段的 p_k，前缀位为自己的下标加 1）、`start_of`，`mask_mod(b, h, q, kv) = (kv <= q) & ((seg_of[q] == 0) | (kv < p_of[q]) | (seg_of[kv] == seg_of[q]))`。

## 四、CPU 上形态 A 和旧训练器的每行 loss 在 fp32 下差 2e-6（脚本 `cpu_equiv_check.py`，结果 `equiv_result.json`，日志 `cpu_equiv_check.log`）

设定：Qwen3-0.6B-Base float32，CPU 36 线程，`torch.set_float32_matmul_precision("highest")`，模型 train 模式（Qwen3 没有 dropout，数值和 eval 相同）。事件从 val 集（`pipeline/data/nyapass_aw_v1/gptoss/val.jsonl`，2,556 个事件）里挑「行数在 2 到 8 之间、全文不超过 4,000 字符、各行 text 互为前缀」的 139 个候选，种子 42 随机抽 5 个：`appworld_383cbac_2_r3|s4`（3 行，前缀 463 个 token，打包后 505）、`appworld_0d8a4ee_2_r3|s1`（8 行，282，426）、`appworld_57c3486_3_r0|s1`（8 行，286，430）、`appworld_530b157_2_r2|s5`（7 行，545，704）、`appworld_50e1ac9_2_r3|s3`（8 行，491，675），一共 34 行、505 个目标 token。每行 loss 的平均值 2.14，最大 4.04。

四种算法对每一行各算一遍：「旧训练器整批」是旧训练器的 collate 加 inst_ce 的做法（右补齐成一批，只在目标位取 CE，输出层只在需要的位置算，lm_head 是逐位置线性层，取子集不改数值）；「旧训练器单行」是每行单独成批不补齐；「形态 A bool 掩码」和「形态 A 浮点掩码」。fp32 和 bf16 autocast 各跑一遍。差值统计（34 行的每行 loss，505 个 token 的逐 token CE）：

| 比较对象 | fp32 每行最大绝对差 | fp32 每行最大相对差 | fp32 逐 token 最大绝对差 | bf16 每行最大绝对差 | bf16 每行平均绝对差 | bf16 逐 token 最大绝对差 |
|---|---|---|---|---|---|---|
| 形态 A bool 掩码 对 旧训练器整批 | 2.15e-6 | 8.4e-7 | 2.77e-5 | 3.63e-2 | 8.87e-3 | 1.32e-1 |
| 形态 A 浮点掩码 对 旧训练器整批 | 2.15e-6 | 8.4e-7 | （同上） | 3.63e-2 | 8.87e-3 | （同上） |
| 形态 A bool 掩码 对 形态 A 浮点掩码 | 0 | 0 | 0 | 0 | 0 | 0 |
| 旧训练器单行 对 旧训练器整批（补齐带来的基线差） | 2.15e-6 | 1.2e-6 | 3.24e-5 | 2.99e-2 | 5.27e-3 | 1.27e-1 |
| 旧训练器整批 bf16 对 自己的 fp32 | | | | 2.95e-2 | 7.99e-3 | 2.13e-1 |
| 形态 A bf16 对 自己的 fp32 | | | | 2.98e-2 | 7.76e-3 | 3.16e-1 |

五个事件的 fp32 每行 loss 逐行列在 `equiv_result.json` 的 `events[*].runs.fp32.row_loss` 里，例如第一个事件旧训练器整批是 `[2.640049, 1.08333, 1.120073]`，形态 A 是 `[2.640049, 1.08333, 1.120074]`。

三项附加检查都在第一个事件（3 行）上做，全部在 fp32：形态 B 每行 loss 对旧训练器整批最大差 1.31e-6，前缀输入嵌入梯度最大绝对值 0.599，463 个前缀位置里 462 个梯度非零；形态 A 开梯度检查点（`gradient_checkpointing_enable()`）之后每行 loss 和不开的差 0，反向能跑，嵌入层梯度最大绝对值 4.23；形态 A 套 peft LoRA（`lora_util.py` 的七件套，r 16、alpha 32）之后每行 loss 和底座差 0（B 矩阵初始为零），392 个 LoRA 参数全部拿到梯度，底座参数 0 个有梯度。

补一组大事件（spec 第 9 节把对齐检查改成抽全文 2,048 个 token 以内、行数不限的事件，上面 5 个事件的规模盖不住）：同一个脚本加 `--min-rows 30 --max-rows 64 --max-chars 9000 --dtypes fp32`，种子 42 从 1,008 个候选里抽 3 个，`appworld_6171bbc_3_r0|s5`（42 行，前缀 1,095，打包后 2,145）、`appworld_37a8675_1_r3|s15`（64 行，1,961，3,689）、`appworld_0d8a4ee_2_r1|s1`（45 行，696，1,505），一共 151 行、2,833 个目标 token，只跑 fp32（结果 `equiv_result_long_fp32.json`）。形态 A 对旧训练器整批的每行最大绝对差 2.62e-6（相对 1.8e-6），逐 token 最大 2.38e-5；补齐基线每行 3.10e-6、逐 token 1.72e-5。尾巴长度出现了 4、5、6 三种（6 是分隔串的换行没有和行末并上、反而多分出一个 token 的情形），没有空尾巴。

下面是解读。fp32 下形态 A 对旧训练器的差（每行 2.15e-6）和旧训练器自己补齐与不补齐的差（2.15e-6）完全同量级，逐 token 的 2.77e-5 对 3.24e-5 也是，所以形态 A 的掩码和 position_ids 是对的，剩下的差是 fp32 的累加顺序噪声。bool 掩码和浮点掩码逐位相同，说明 CPU 内核对两种 dtype 走的是同一条算术路径。bf16 下形态 A 对旧训练器的每行差（最大 3.6e-2、平均 8.9e-3）和「旧训练器补齐对不补齐」（3.0e-2、5.3e-3）、「同一形态 bf16 对 fp32」（3.0e-2、8.0e-3）三者同量级，bf16 的舍入本身就有这么大，形态之间的差没有额外贡献。

## 五、对齐容差分两道：fp32 门禁每行 2e-5，bf16 粗筛每行平均 2e-2

### 5.1 ctool 的 `--align-tol` 验证的是缓存增量前向和整段前向是同一个函数

`train_causal_tool.py` 第 200 到 240 行 `align_check`：取 val 集全文最长的一个事件（第 335 行），截断到 `--max-len`，fp32、`torch.set_float32_matmul_precision("highest")`（第 208 行，关 TF32），算两遍底座前向：整段一次前向，和逐 token 增量前向（每次喂 1 个 token 带 `past_key_values`，第 218 到 222 行），比较末位置的隐状态和分类头 logits 的最大绝对差（第 226 到 228 行），两个差都小于 `tol` 才 PASS，否则 `sys.exit(2)` 拒绝开训（第 345 到 354 行）。默认 `ALIGN_TOL = 1e-4`（第 76 行）。`3e-4` 是 c1 批次按 T8 先例放宽的值（`.claude/skills/probe-pipeline/references/invariants.md` 第 97 行：三个 ctool 的 hidden maxdiff 8.39e-5 到 1.68e-4、相对差 2.3e-6 到 3.3e-6，判为 fp32 噪声，记在 TIMELINE 2026-07-31 c1 条），np821 四个 ctool 的 `align_maxdiff_hidden` 是 9.78e-5 到 2.37e-4（`RESULTS.md` 第 23 到 32 行）。`--align-tol` 验证的是「缓存增量前向和整段前向是同一个函数」，量的是 4096 个 token 之后隐状态的绝对差，全程 fp32，和 bf16 训练无关，也不比较 loss。

### 5.2 正确性门禁在 fp32 上定，bf16 只做粗筛

新训练器的对齐验收分两道。

第一道是正确性门禁，fp32、`highest` 精度、TF32 关，随机抽若干事件，形态 A 对旧训练器整批的每行 loss 最大绝对差不超过 2e-5，逐 token 最大绝对差不超过 3e-4（2026-08-28 按第七节的 GPU 实测从 1e-5 / 1e-4 放宽）。依据：CPU 上 5 个短事件实测每行 2.15e-6、逐 token 2.77e-5，3 个大事件（最多 64 行、打包后 3,689）每行 2.62e-6、逐 token 2.38e-5；GPU（H100，新路径 mem-efficient）上同样 5 个短事件每行 4.41e-6、逐 token 3.05e-5，补齐基线每行 5.01e-6、逐 token 6.91e-5；spec 第 9 节的抽样规模（约 380 行、7,000 个 token）比这大 10 倍，最大值还会往上走，所以门槛按 GPU 的数再放一档，理由和估算在第七节；掩码或者 position_ids 错一个位置，一行的 loss 会动 1e-2 到 1 的量级，远在门槛之上。把差值和同一次运行里「旧训练器单行对整批」的基线差一起打印，差值超过基线 3 倍就算可疑，即使差值本身还在 2e-5 以内（GPU 上基线里的单行批没有掩码，按第七节的资格表排除推断走的是 math 内核，实测的基线差比新路径的差还大，所以基线线只当告警不当门禁）。

第二道是 bf16 粗筛，在 GPU 冒烟之前用真实内核跑一次（`gpu_kernel_check.py` 第 6 步），34 行以上，形态 A 对旧训练器整批的每行 loss 平均绝对差不超过 2e-2、最大绝对差不超过 1e-1。依据：CPU 实测平均 8.9e-3、最大 3.6e-2，GPU（H100，mem-efficient）实测平均 9.31e-3、最大 3.07e-2，bf16 对 fp32 自己的差就有平均 8.0e-3、最大 3.0e-2，门槛留 2 到 3 倍。这道筛只能抓「整段错位」这种把 loss 挪掉 0.1 以上的错，抓不住细微的掩码错，所以不能替代第一道。

不建议把 ctool 的 3e-4 搬过来：那是 fp32 隐状态的绝对差，量的对象、精度、可比性都和 bf16 的 loss 差不同。

## 六、GPU 上主会话要跑七步验证（脚本 `gpu_kernel_check.py`，单卡，约十几分钟）

```
CUDA_VISIBLE_DEVICES=0 cprobe-env/bin/python /home/y-guo/.claude/jobs/b39c625e/tmp/a2/gpu_kernel_check.py \
    --max-len 8192 --math-L 2048 --grad-ckpt --lora --out /home/y-guo/.claude/jobs/b39c625e/tmp/a2/gpu_result.json
```

脚本自己从 val 集挑全文 token 不超过 8192 的最长事件做形态 A 的打包序列，七步各写一段进 JSON：

1. 内核资格。对真实形状的 q、k、v（bf16，`[1, 16, L, 128]`）加 bool 掩码和 bf16 加性掩码各问一遍 `can_use_flash_attention / can_use_efficient_attention / can_use_cudnn_attention`（`debug=True`，拒绝理由以警告形式打印并收进 JSON）。预期：flash False（掩码非空），efficient True。efficient 为 False 就要读理由，形态 A 的显存前提不成立。
2. 强制 mem-efficient。`sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])` 里整模型前向加反向（autocast bf16），记 `torch.cuda.max_memory_allocated`、耗时、profiler 里含 `efficient / fmha / cutlass` 的内核名。这一步的峰值就是 8192 事件在形态 A 下的显存数，和 H100 的 93.6 GiB 比较余量。
3. 默认选择。不套上下文再跑一遍，内核名要和第 2 步相同。不同就说明默认优先级在真实形状上没选 mem-efficient，训练代码必须显式套上下文。
4. math 内核在 L 2048 上的峰值对照解析式 28 × 16 × L² × 4 字节（L 为 2048 的时候是 7.5 GB），校准 3.2 节的表。
5. 掩码变体。bool 对 bf16 加性、L 补到 16 的倍数对不补，四个组合各记峰值，定训练代码里掩码的 dtype 和是否补齐。
6. bf16 对齐差值。5 个短事件、34 行，旧训练器整批对形态 A 的每行 loss 差值分布，给 5.2 节第二道门槛的 GPU 数。
7. `--grad-ckpt` 和 `--lora` 各跑一次 8192 事件的峰值，给 1.7B 和 4B 在 48G 卡上的排卡用。

第 2 步的峰值是全 8192 前缀加 45 段的单事件数，物理批按 token 预算放多个短事件的峰值要在冒烟里另量。

## 七、GPU 七步验证的结果：形态 A 的前提成立，最长事件在 bf16 补齐掩码下峰值 26.65 GiB

两次发射都在 tokyo108 GPU 0（H100 NVL，93.10 GiB）上，产物目录 `pipeline/runs/smoke/kvshare_gpu_kernel_check/`（`RUNMETA.json` 记 HEAD 024b34f）。第一次发射（日志 `logs/new1_kvshare_gpu_kernel_check_t108g0.log`）跑到第 3 步，第 4 步崩：脚本把前缀截到 2,048 却没有过滤行，16 行的尾巴各自带着 2,048 之后的整段 prompt，math 内核要分配 101.85 GiB。改脚本后第二次发射（日志 `logs/new1_kvshare_gpu_kernel_check_t108g0.r1.log`）九步都跑完，只有第 6 步的两遍对齐报错，原因在 7.1 节；再改脚本后第三次发射（日志 `logs/new1_kvshare_gpu_kernel_check_t108g0.r2.log`，`gpu_result.json` 最终版）九步全过、`errors` 为空，下面的数全部取第三次的 JSON。JSON 里记的环境：torch 2.11.0+cu128，`priority_order` `[1, 2, 0, 3, 4]`，`float32_matmul_precision` highest，`allow_tf32_matmul` False。脚本挑出来的最长事件是 `appworld_6bdbc26_1_r2|s17`：64 行，前缀 8,167 个 token，打包后 L 9,381，补到 16 的倍数是 9,392。

七步的事实（峰值都是 `torch.cuda.max_memory_allocated`，括号里是比进入每一步之前多出的量；秒数是前向加反向的墙钟，第 2、3 步含 profiler 开销）：

1. 内核资格：bool 掩码和 bf16 加性掩码两种情况下 `can_use_flash_attention` 都是 False，`can_use_efficient_attention` 都是 True，`can_use_cudnn_attention` 都是 True；fp32 的 q、k、v 加 fp32 加性掩码：flash False、efficient True、cudnn False（日志第 6 行原文 `Expected query, key and value to all be of dtype: {Half, BFloat16}`）；bf16、无掩码、K/V 8 头（`enable_gqa`）：flash True、efficient False（日志第 7 行原文 `For dense input, both fused kernels require query, key and value to have the same num_heads`）、cudnn True。
2. 强制 mem-efficient（bool 掩码）：峰值 31.08 GiB（多 28.86 GiB），2.96 秒，内核名 `fmha_cutlassF_bf16_aligned_64x128_rf_sm80` 和 `fmha_cutlassB_bf16_aligned_128x128_k128_sm80`；64 行 loss 平均 3.2452。
3. 默认选择（同一输入）：峰值 31.11 GiB（多 28.83 GiB），4.27 秒，内核名 `aten::_scaled_dot_product_cudnn_attention` 加 `cudnn_generated_fort_native_sdpa_sm90_flash_fprop_wgmma_f16` 与对应的 `bprop`；64 行 loss 平均 3.2500。
4. math 内核在短序列上：事件 `appworld_68ee2c9_1_r3|s2`（全文正好 2,048 个 token，64 行里装进 42 行），P 2,048、L 2,552，解析式 28 × 16 × 2,552² × 4 字节 = 10.87 GiB；math 峰值 22.55 GiB（多 20.26 GiB），2.18 秒；同一输入 mem-efficient 峰值 10.37 GiB（多 8.09 GiB），0.14 秒。42 行 loss 平均 math 2.3924、mem-efficient 2.3873。
5. 掩码四种变体（强制 mem-efficient）：bool 不补齐（L 9,381）31.11 GiB；bf16 加性不补齐 31.20 GiB；bool 补到 9,392 是 31.17 GiB；bf16 加性补到 9,392 是 26.65 GiB（多 24.36 GiB）。四种的 64 行 loss 平均都是 3.2452。
6. 对齐差值（第四节同样的 5 个短事件，34 行、505 个目标 token；新路径套 EFFICIENT，参照路径默认选择）。fp32（autocast 关、`highest`、TF32 关）：形态 A 对旧训练器整批的每行最大绝对差 4.41e-6（平均 1.66e-6，90 分位 3.06e-6，最大相对差 3.1e-6），逐 token 最大 3.05e-5（平均 5.11e-6）；补齐基线（旧训练器单行对整批）每行最大 5.01e-6、逐 token 最大 6.91e-5；34 行 loss 平均 2.1379，和 CPU 的 2.1379 相同。bf16 autocast：每行最大 3.07e-2、平均 9.31e-3、90 分位 2.03e-2，逐 token 最大 2.32e-1、平均 2.01e-2；补齐基线每行最大 3.03e-2、平均 8.83e-3，逐 token 最大 1.83e-1；34 行 loss 平均 2.1402。第二次发射这一步两遍都报 `RuntimeError: No available kernel. Aborting execution.`，torch 的拒绝理由原文是 `For dense input, both fused kernels require query, key and value to have the same num_heads. Query.sizes(): [1, 16, 463, 128], Key sizes(): [1, 8, 463, 128], Value sizes(): [1, 8, 463, 128] instead.`，原因和修法在 7.1 节。
7. `--grad-ckpt`：峰值 6.34 GiB（多 4.06 GiB），1.22 秒；`--lora`（r 16，七件套）：峰值 31.18 GiB（多 28.86 GiB），1.0 秒。

下面是解读。

形态 A 的前提成立：mem-efficient 接形态 A 的真实形状（L 9,381、head_dim 128、bf16、4 维掩码），第 2 步的内核名就是 cutlass 的 mem-efficient 前向和反向，四种掩码变体和 `--grad-ckpt`、`--lora` 都在同一个内核上跑通，loss 平均逐位相同。

默认内核选择在 H100 上落到 cuDNN，不是 3.1 节推的 mem-efficient；`priority_order` 在 GPU 上读出来仍是 flash、efficient、math、cudnn，所以 torch 在选择时对 sm90 另有偏好，选择逻辑在编译进 .so 的 `sdp_utils.cpp` 里，本次没有追。cuDNN 和 mem-efficient 的 64 行 loss 平均差 4.8e-3（3.2500 对 3.2452），是两个 bf16 内核的舍入路径不同。裁决不变并且理由加强：训练与评估都显式套 `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])`，把内核钉死，不随 torch 默认顺序、cuDNN 版本和显卡型号漂移。

掩码定 bf16 加性、L 补到 16 的倍数：比另外三种省 4.5 GiB，和 2.4 节的预测一致（28 层各留一份 9,392² × 2 字节的掩码副本是 4.60 GiB；bool 掩码每层被 `convert_boolean_attn_mask` 转一份，bf16 不补齐每层被 `pad_bias` 复制一份，只有 bf16 补齐的那一份被 28 层共用）。

math 校准：同一输入 math 比 mem-efficient 多 12.17 GiB，解析式给 10.87 GiB，多出的 12% 是前向瞬时张量；64 字节每 L² 每层的系数成立，3.2 节的表照旧（L 9,381 要 147 GiB，任何卡装不下）。

显存余量：最长单事件在 bf16 补齐掩码下峰值 26.65 GiB，脚本里有 fp32 权重和梯度、没有优化器状态，训练时再加 AdamW 两份状态 4.47 GiB 是 31.1 GiB，对 H100 的 93.10 GiB 剩 62 GiB（67%）。多出的 24.36 GiB 折成每 token 2.72 MB（含瞬时），比 3.3 节估的留住量 2.42 MB 高 12%。按每 token 2.72 MB 估物理块：`--tok-budget` 16,384 个 token 的块约 41.5 GiB 激活，加静态 8.9 GiB 约 50 GiB，H100 占 54%；32,768 的块约 92 GiB，H100 装不下。16,384 和 32,768 两个块量的数是估算，spec 第 10 节的 `--mem-probe` 会量到真值。

排卡（48G 卡，RTX 6000 Ada 49,140 MiB = 48.0 GiB）：`--grad-ckpt` 把最长单事件从 31.1 GiB 压到 6.34 GiB，`--lora` 不省激活（31.18 对 31.08）。0.6B 全参不开检查点，最长单事件 31.1 GiB 装得下（余 35%），但 16,384 的块约 50 GiB 装不下，所以 48G 卡上 0.6B 要么开检查点要么把块量压到约 14,000 个 token 以内；1.7B（隐藏维 2048，28 层）的每 token 激活约是 0.6B 的 2 倍，4B（2560，36 层）约 3.2 倍，最长单事件不开检查点分别约 49 GiB 和 78 GiB，48G 卡上两个底座都必须 `--grad-ckpt`，LoRA 不能替代（1.7B、4B 的倍数是按隐藏维乘层数推的，没有实测）。

对齐门槛（spec 第 9 节）：fp32 每行最大差 4.41e-6 在 1e-5 以内（余量 2.3 倍），逐 token 3.05e-5 在 1e-4 以内（3.3 倍），基线告警线 max(3 × 5.01e-6, 1e-6) = 1.5e-5 也没有碰到；bf16 每行平均 9.31e-3 在 2e-2 以内（2.1 倍），最大 3.07e-2 在 1e-1 以内（3.3 倍），并且和补齐基线（8.83e-3、3.03e-2）同量级。GPU 上 fp32 的每行噪声是 CPU 的 2 倍（4.41e-6 对 2.15e-6），逐 token 相当（3.05e-5 对 2.77e-5）。基线里「单行」那一批在 fp32 下没有掩码，按第 1 条的资格表排除推断（fp32 那一组 cudnn False，无掩码 K/V 8 头那一组 efficient False，flash 不接 fp32）只剩 math 内核可选；JSON 里没有「fp32 加无掩码加 K/V 8 头」这一组的资格查询，也没有参照路径的 profiler 内核名，所以「单行批走 math」是推断不是实测。按这个推断，单行批和「整批」的 mem-efficient 不是同一个内核，基线的差（每行 5.01e-6、逐 token 6.91e-5）比新路径对整批的差还大就说得通；3 倍基线的告警线会偏松，真正把关的是绝对线。spec 第 9 节抽的是 6 个全文 2,048 以内、最多 64 行的事件，约 380 行、7,000 个 token，比第 6 条的 34 行多 10 倍，最大值会随样本数往上走（CPU 上从 34 行到 151 行，每行最大差从 2.15e-6 到 2.62e-6；逐 token 从 2.77e-5 到 2.38e-5，没有涨）。按 GPU 的 4.41e-6 再放 1.3 倍估 380 行的每行最大约 6e-6，1e-5 的余量只剩 1.7 倍，门禁误拦会直接挡住开训；所以建议每行的线改 2e-5（对 6e-6 留 3 倍，离 5.2 节估的掩码错一位 1e-2 仍差 500 倍），逐 token 的线改 3e-4（GPU 基线 6.91e-5 已经接近 1e-4，7,000 个 token 的最大值大概率越过 1e-4；3e-4 离每 token 真错的 1e-2 差 30 倍）。第二道 bf16 的 2e-2 / 1e-1 不动。

### 7.1 第 6 步的报错原因，以及训练器要绕的约束

原因：对齐检查的参照路径里有一批是「单行不补齐」，没有 padding，HF 的 `_ignore_causal_mask_sdpa` 跳过建掩码，`use_gqa_in_sdpa` 在掩码为空时返回 True，K、V 保持 8 头不做 `repeat_kv`，直接把 `enable_gqa=True` 传给 sdpa；mem-efficient 内核不支持 GQA（sdpa 的 docstring 原文 `Grouped Query Attention (GQA) is an experimental feature. It currently works only for Flash_attention and math kernel on CUDA tensor`），强制 EFFICIENT 的上下文里 flash 和 cudnn 又被关掉，于是没有内核可用。新路径永远带掩码，`repeat_kv` 到 16 头，不会撞上，第 2、3、5、7 步都在同一个上下文里跑通就是证据。

脚本的修法：`alignment()` 只给新路径套 `sdpa_kernel([EFFICIENT_ATTENTION])`，参照路径用默认选择；第 1 步多问两种资格（fp32 query 加 fp32 掩码；bf16 无掩码且 K/V 8 头）把「mem-efficient 不接 GQA」的约束写进 JSON。第三次发射的第 6 步就是这么跑通的，数在上面第 6 条，5.2 节的门槛按这些数改过。

训练器要绕的约束（spec 第 9 节要加一句）：对齐检查的参照路径（旧 `collate` 加 `inst_ce`）不套 `sdpa_kernel([EFFICIENT_ATTENTION])`，用默认内核选择；只有新路径（形态 A，永远带掩码）套。更一般的规则：凡是没有掩码的 sdpa 调用（HF 在 2 维掩码全 True 或者掩码为空的时候会跳过建掩码并开 `enable_gqa`）都不能放进强制 EFFICIENT 的上下文。训练器自己的训练和评估前向都是形态 A，都带掩码，不受影响。

## 八、冒烟与速度档的结果：新训练器每秒行数是旧训练器的 23 到 67 倍，上限 8192 与预算 16384 定案

本节先摆事实（8.1 到 8.4），再写判读（8.5）。产物目录都在 `pipeline/runs/smoke/` 下，数字全部从各目录的 `train_log.jsonl` 和 `ALIGN_CHECK.json` 读出来（复核脚本 `verify/speed_judge.py`，六个对照数按 spec 第 10 节的线性插值算出来）。

### 8.1 三个速度档的六个对照数与倍数

三个速度档都是 0.6B 全参 cgen，tokyo108 H100 NVL（93.10 GiB = 99.97 GB），`--max-events 450 --log-every 3 --eval-per-epoch 1 --mem-probe`，450 个事件 20,641 行 57 次更新（113 个逻辑小批，最后一组只有 1 个）。三个 run 只差 `--tok-budget`（`b16k` 16,384、`b24k` 24,576）和 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`（`b16k_es`，预算 16,384）。对照数是 spec 第 1 节从 `np821b06_gptoss_cgen`（旧训练器，同一张 H100）取的六个数。

| 对照点 | 旧训练器 | b16k（倍数） | b24k（倍数） | b16k_es（倍数） |
|---|---|---|---|---|
| ips 在 1,600 行处 | 2.76 | 185.6（67 倍） | 152.5（55 倍） | 180.4（65 倍） |
| ips 在 9,600 行处 | 3.26 | 189.5（58 倍） | 155.3（48 倍） | 178.8（55 倍） |
| ips 在 19,200 行处 | 3.97 | 184.1（46 倍） | 155.8（39 倍） | 177.0（45 倍） |
| ips_win 在 0 到 1,600 行 | 2.77 | 185.6（67 倍） | 152.5（55 倍） | 180.4（65 倍） |
| ips_win 在 8,000 到 9,600 行 | 3.94 | 203.8（52 倍） | 168.6（43 倍） | 188.3（48 倍） |
| ips_win 在 17,600 到 19,200 行 | 6.24 | 145.3（23 倍） | 135.2（22 倍） | 148.5（24 倍） |

三个 run 的 `train_s`（本 epoch 训练秒数，不含评估）是 112.3 / 131.4 / 116.1 秒，`wall_s`（含 `--mem-probe` 的全集加载、对齐检查、epoch 末对 20,034 行 val 的评估）是 582.9 / 621.4 / 590.6 秒，epoch 末 `val_ce` 0.2608 / 0.2604 / 0.2615。

### 8.2 峰值与探针

`peak_mem_gb` 是 `torch.cuda.max_memory_allocated()` 除以 1e9，每条 step 日志取完重置；`mem_probe` 两块是训练前的探针（`with_optimizer_state: true`，做完一次前向反向再做一次 lr 置 0 的 `opt.step()` 之后读取峰值）。

| run | 探针最长事件（B=1，L_pad 9,504） | 探针最满块 | step 日志里的峰值 | 对 93.10 GiB 的余量 |
|---|---|---|---|---|
| b16k | 31.43 GB（29.3 GiB） | 51.11 GB（47.6 GiB，B=2，L_pad 8,192） | 60.59 GB（56.4 GiB） | 39% |
| b24k | 31.43 GB（29.3 GiB） | 75.05 GB（69.9 GiB，B=3，L_pad 8,192） | 80.91 GB（75.4 GiB） | 19% |
| b16k_es | 31.40 GB（29.2 GiB） | 51.10 GB（47.6 GiB，B=2，L_pad 8,192） | 60.56 GB（56.4 GiB） | 39% |

### 8.3 末尾窗口的 token 组成，以及补齐浪费

三个 run 的种子相同、事件顺序相同，每个 3 次更新的窗口里行数逐条相同（1,233 / 1,187 / 1,164 / 1,024 / 990 / 1,026 / 1,205 / 861 / 1,314 / 1,083 / 1,036 / 1,080 / 1,194 / 1,061 / 1,155 / 1,030 / 1,123 / 1,002 / 873）。把同一份抽样（`load_events` 的 `limit=450, order="random"`）和 `random.Random(42)` 的打乱在 CPU 上复现，按 `chunk_by_budget(16384)` 装块后统计每个窗口的 token：第 51 次更新所在的窗口（17,643 到 18,766 行）补齐后 98,352 个 token 是全程最大，每行 87.6 个；第 54 次（18,766 到 19,768 行）95,072 个，每行 94.9 个是全程最高；第 57 次（19,768 到 20,641 行，尾组只有 1 个逻辑小批）61,568 个，每行 70.5 个。b16k 各窗口按补齐后 token 算的吞吐：第 51 次 12.9k、第 54 次 13.0k、第 57 次 15.8k、第 24 次 16.9k、第 33 次 16.5k token 每秒，其余窗口在 14.0k 到 15.8k 之间。450 个事件一个 epoch 补齐后一共 1,649,168 个 token，真实 1,179,563 个，补齐部分占 28%。

### 8.4 两道对齐门与三格冒烟

三个速度档和 cgen 冒烟档的 `ALIGN_CHECK.json` 相同（同一批 6 个 val 事件、154 行、2,877 个目标 token）：逐行最大差 5.48e-6（门槛 2e-5），逐 token 最大差 4.29e-5（门槛 3e-4），补齐基线 1.08e-5（3 倍 3.2e-5 没有触发告警），bf16 逐行平均 8.43e-3（门槛 2e-2）、最大 4.32e-2（门槛 1e-1），全部 PASS。cparam 冒烟档：同 6 个事件 154 行、1,916 个目标 token，逐行 9.30e-6、逐 token 4.72e-5、基线 1.00e-5，bf16 平均 9.74e-3、最大 4.87e-2，PASS。

三格冒烟档（plan-8-28 的发射记录：H200 的 3、4、5 号卡）：cgen 40 个训练事件 284 行、16 个评估事件 81 行、`dropped_events` 训练 1 个、val 3 个、5 次更新、4 次评估 `val_ce` 1.7044 → 1.4554 → 1.3344 → 1.2938，`wall_s` 151.5；cparam 同样的事件数与行数，`val_ce` 2.5151 → 1.9831 → 1.7027 → 1.5926，`wall_s` 153.4；ctool（`ks828b06_gptoss_ctool_smoke`，工单 02 改过丢弃规则与上限 8192）对齐检查逐 token 模式 8,167 个 token，`maxdiff_hidden` 1.03e-4、`maxdiff_logits` 1.36e-5，容差 3e-4 PASS，相对差 1.46e-6 / 1.87e-6，200 个训练事件 80 个评估事件 25 次更新，`dropped_events` 训练 1 个、val 3 个，`n_bound_dropped` 0，`calA_weighted_acc` 0.408、`calA_lastbound_acc` 0.425（冒烟规模，不作数）。ctool 在 H100（tokyo108 gpu0，93.10 GiB）上的显存两次发射（产物 `ks828b06_gptoss_ctool_h100mem` 与 `ks828b06_gptoss_ctool_h100mem_bs2`，都是 `--smoke` 200 个训练事件、上限 8192，外面包一层 `memwrap.sh` 每 2 秒记一次 nvidia-smi 的 `memory.used`）：第一次用当时的默认值 `--bs 4 --accum 2`，对齐检查过了之后训练第一批前向在 `F.linear` 里 OOM，报错原文 `Tried to allocate 154.00 MiB. GPU 0 has a total capacity of 93.10 GiB of which 146.88 MiB is free. Including non-PyTorch memory, this process has 92.94 GiB memory in use. Of the allocated memory 77.61 GiB is allocated by PyTorch, and 14.58 GiB is reserved by PyTorch but unallocated.`，nvidia-smi 115 个样本的最大值 87,179 MiB（2 秒一次，没有采到崩溃那一刻的峰）；第二次改 `--bs 2 --accum 4`（HEAD 7008dff）跑通，165 个样本最大 56,859 MiB（90 分位 56,855，中位 34,699），25 次更新，对齐 PASS（同上 1.03e-4），`dropped_events` 训练 1 个、val 3 个，`n_bound_dropped` 0，`calA_weighted_acc` 0.394、`calA_lastbound_acc` 0.4125（冒烟规模，不作数）。ctool 的默认值随之改成 `--bs 2 --accum 4`（决定 15 的退路，一次更新仍是 8 个事件）。

### 8.5 判读与裁决（决定 21 已采纳）

上限 `--max-len` 留 8192：最长事件的探针 31.4 GB，b16k 训练里的峰值 56.4 GiB 对 93.10 GiB 余量 39%，b24k 的 75.4 GiB 也还有 19%，都在 10% 的裁决线上面。

预算 `--tok-budget` 定 16,384：b24k 比 b16k 末尾累计每秒行数慢 15%（最后一条 step 的 `ips` 157.1 对 183.7），六个对照点分别慢 17.8 / 18.1 / 15.4 / 17.8 / 17.3 / 7.0%，平均慢 16%；峰值高 20 GB，而且探针低估真峰（下一段），b24k 碰上两个最满块同组会顶到 85 到 90 GB，余量掉到 10% 线附近；b16k 又快又稳。

`expandable_segments` 不开：b16k_es 比 b16k 慢 3%，峰值相同，57 次更新里看不到收益；整 epoch 会不会晚期碎片化没有测，全量训练遇到 OOM 再回头试。

S4（掩码在主线程上构造）不做：各窗口按补齐 token 算的吞吐稳定在 12.9k 到 16.9k token 每秒，CPU 造掩码的份额从日志里分不出来，估的收益不超过 10%。数据里更大的杠杆是补齐浪费 28%：4 个事件的逻辑小批里 B 为 2 到 4 的块把短事件补到块内最长，改装块策略只动物理层、不动更新口径，留作全量之后的优化。

探针为什么比训练峰值低 9.5 GB（b16k 51.1 对 60.6 GB）：探针的峰值是两个时刻取大，反向期间是「权重 2.4 GB 加激活加正在生成的梯度」，反向期间优化器状态还没有分配（第一次 `opt.step()` 才建）；`opt.step()` 之后是「权重加梯度加状态 = 9.6 GB」，但激活已经释放。训练的真峰在一组里第二个逻辑小批的反向期间，那一段时间里优化器状态 4.8 GB 和第一个小批的梯度 2.4 GB 都在，7.2 GB 就是差额的大头，剩下约 2.3 GB 是块形状差异。探针的改法（工单 06）：先 `zero_grad(set_to_none=False)` 加一次 lr 置 0 的 `opt.step()` 把状态建好，再把最满块连做两次前向反向、中间不 `zero_grad`（accum 为 2 的时候两个最满块同组是真实会出现的最坏情况），第二次反向后读取峰值，再 `opt.state.clear()`。预期 b16k 约 60 GB。

末尾窗口的 145 行每秒不是尾组或评估造成的：`train_s` 不含评估，评估在第 57 次更新之后；8.3 节的复现说明第 51、54 两个窗口正好落在每行 token 最多的一段（87.6 和 94.9 个），按 token 算的吞吐和别的窗口同一量级，长序列略低是注意力 L² 的份额变大。三个 run 窗口形状一模一样也说明是数据决定的。

ctool 在 H100 上按 `--bs 2 --accum 4` 走：`--bs 4` 在 8192 上限下第一批就 OOM，崩溃时 PyTorch 已分配 77.61 GiB 加 14.58 GiB 预留未用，也就是碎片把 93.10 GiB 吃满；`--bs 2` 的 nvidia-smi 峰值 56,859 MiB（55.5 GiB，含分配器缓存）对 93.10 GiB 余量 40%。8.4 节的 ctool 数是冒烟规模的 200 个事件，全量训练的批里会出现更长的事件组合，`--bs 2` 的余量要在全量的第一个 epoch 里再看一眼 nvidia-smi。

整 epoch 的训练时间按 b16k 的 185 行每秒估：train 集 186,479 行约 1,008 秒，加上四次评估、对齐检查和 `--mem-probe` 的全集加载（这三项在冒烟里没有单独计时，`wall_s` 减 `train_s` 是 471 秒，其中一次 20,034 行的评估）。

### 8.6 终验：最终代码（1414e8e）的四个 run，以及探针剩下 4.1 GB 差额的来源

先摆事实。四个 run 的 `RUNMETA.json` 都记 commit 1414e8e（工单 05、06 合并之后），产物在 `pipeline/runs/smoke/ks828b06_gptoss_{cgen_final_b16k, cgen_final_b24k_probe, cparam_final_smoke, ctool_final_smoke}`。

`cgen_final_b16k`（H100，450 个事件 20,641 行 57 次更新，预算 16,384，带探针）：ips 在 1,600 / 9,600 / 19,200 行处 187.2 / 191.9 / 187.6，ips_win 三个跨度 187.2 / 206.2 / 156.2，`train_s` 109.7 秒，`wall_s` 585.3 秒，epoch 末 `val_ce` 0.2610；step 日志里的峰值 58.47 GB（上一轮同配置 60.59）；改后的探针（状态先建、最满块两次反向、每块各自 reset）最满块 54.38 GB（B=2，L_pad 8,192），最长事件 36.47 GB（B=1，L_pad 9,504）。`cgen_final_b24k_probe`（16 个事件 2 次更新，只为探针）：最满块 76.47 GB（B=3，L_pad 8,192），最长事件 36.49 GB；上一轮 b24k 整程峰值 80.91。`cparam_final_smoke`（40 个事件 284 行 5 次更新）：对齐逐行 9.30e-6、逐 token 4.72e-5、基线 1.00e-5，bf16 平均 9.74e-3、最大 4.87e-2，PASS；`val_ce` 2.515 → 1.5927，step 峰值 15.09 GB。`ctool_final_smoke`（H200，默认值已是 `--bs 2 --accum 4`）：对齐 8,167 个 token `maxdiff_hidden` 1.03e-4 PASS，25 次更新，`dropped_events` 1 / 3，eval 事件自记 `peak_mem_gb` 47.337（allocated），`calA_weighted_acc` 0.3973、`calA_lastbound_acc` 0.4125。四份 `ALIGN_CHECK.json` 的数和上一轮逐位相同。

上一轮 b16k 和这一轮 final_b16k 逐窗口的 step 峰值（GB，19 个窗口按第 3 到 57 次更新）：52.00 → 49.34、56.00 → 52.72、55.60 → 52.40、60.04 → 57.31、53.78 → 51.91、53.02 → 50.22、56.24 → 52.30、57.97 → 54.85、55.95 → 53.03、57.18 → 54.51、49.39 → 46.07、56.04 → 52.41、52.83 → 50.16、60.59 → 58.47、54.74 → 51.98、57.75 → 55.58、54.32 → 51.34、57.64 → 54.56、55.13 → 52.30，每个窗口低 1.9 到 3.9 GB，最小的降幅在第 42 次更新的窗口（2.12），最大的在第 21 次（3.94）。

块形状的复现（同 8.3 节的方法，对 final_b16k 的每个窗口列出「token 最多的块」和「损失位最多的块」，损失位 = 目标 token 数）：峰值窗口（第 42 次更新，58.47 GB）token 最多的块和损失位最多的块是同一块，B=3、L_pad 5,344、16,032 个 token、192 行、4,736 个损失位，是全程损失位最多的块；第 12 次更新的窗口（57.31 GB）是 B=4、L_pad 4,064、16,256 个 token、198 行、3,820 个损失位；最低的第 33 次窗口（46.07 GB）token 最多的块只有 13,760 个 token、2,299 个损失位。19 个窗口的峰值对「窗口内 token 最多的块的 token 数」的相关系数 0.73，对「损失位最多的块的损失位数」0.49。探针在全集里挑的最满块是 `appworld_d0b1f43_1_r0|s3` 和 `appworld_60d0b5b_1_r2|s2`（各 64 行，拼接长度 8,186 和 8,171），B=2、L_pad 8,192、16,384 个 token、128 行、1,984 个损失位；最长事件 `appworld_aa8502b_2_r2|s6`（64 行，9,492 个 token，1,344 个损失位）。

下面是判读，按 plan-8-28 的四个问题。

第一，探针剩下的 4.1 GB 差额来自损失位的数量，「行数多损失位多的块」的猜测成立，但要加一个限定：峰值块同时要 token 接近预算。每个损失位在输出层要留下四份 151,936 维的向量（autocast 下 lm_head 出的 bf16 logits、CE 用的 fp32 副本、fp32 的 logits 梯度、回传给 lm_head 的 bf16 梯度，合计约 1.8 MB）；峰值块比探针块多 2,752 个损失位，就是约 5.0 GB，少 352 个 token 按每 token 2.7 MB 扣回约 1.0 GB，净差约 4.0 GB，和实测的 4.1 GB 对得上。相关系数 0.73 对 0.49 说明 token 数仍是主项，损失位是第二项，真正的最坏块是「a × token 数 + b × 损失位数」最大的一块，探针只按 token 数挑选会漏掉第二项。最长事件的探针（36.5 GB）离峰值很远，在预算 16,384 下从来不是约束。

第二，60.59 到 58.47 的降幅是 S1 的效果，机理不是 `hidden_states` 元组本身，而是旧写法调的是 `Qwen3ForCausalLM.forward`，默认 `logits_to_keep=0` 会对全部位置过一遍 lm_head，一个 16,384 个 token 的块就是 16,384 × 151,936 × 2 字节 = 4.98 GB 的 bf16 张量，在前向结束的那一刻和全部激活同时活着；S1 改成直接调 backbone 之后这块没有了。降幅 1.9 到 3.9 GB 小于 4.98 GB，是因为峰值时刻不一定在前向结束：损失位多的块，反向开始时的 logits 梯度更大，峰值在反向开始，全位置 logits 已经释放，所以第 42 次窗口（损失位 4,736）降幅最小 2.12，第 21 次窗口（token 最多的块只有 1,475 个损失位）降幅最大 3.94。

第三，最长事件探针从 31.43 到 36.47 多出的 5.04 GB，主项是优化器状态 4.77 GB（5.96 亿参数 × 2 份 fp32），另外两项大致抵消：改后的探针从一开始就常驻 2.38 GB 的梯度，而旧探针的峰值时刻梯度还没生成完；S1 又去掉了最长事件的全位置 logits 9,504 × 151,936 × 2 字节 = 2.89 GB。三项合计约 4.3 GB，和 5.04 差 0.7 GB，日志里没有逐时刻的分解，分不到更细。

第四，探针的建议。决定 25 用「最满块 × 1.1 再打碎片折」当下界估计，按这一轮的数能用：4.1 / 54.4 = 7.5%，在 1.1 倍以内。下一步不必改成跑真实训练循环两个小批，epoch 0 的逻辑小批组成由种子决定，探针可以直接枚举 epoch 0 的全部物理块（同 `chunk_by_budget`），挑选两块跑：token 数最大的一块和损失位数最大的一块（或者直接按 2.7 MB × token 数 + 1.8 MB × 损失位数 挑选最大的一块），用现在的累积条件各跑一次，取大者。按同一个公式校正这一轮的探针：54.38 + 1.83 × 2.752 − 2.7 × 0.352 = 58.5 GB，和实测 58.47 差 0.1 GB。「最长事件」的探针可以不跑，改成损失位最多的块。

## 九、学习率扫描的排卡、探针的挑块方式、生成式评估的代价、学习率网格（2026-08-28 晚，plan-8-28 第二轮四问）

本节先摆依据（9.1 到 9.3 只有事实和计算），再按四个问题给结论（9.4 到 9.7）。扫描的设定照 plan-8-28 的来信：cgen 格，四个底座配置 b06（Qwen3-0.6B-Base 全参）、b17（1.7B 全参）、l17（1.7B LoRA r16）、l4（4B LoRA r16）各扫三个学习率、各 1 个 epoch，数据 `pipeline/data/nyapass_aw_v1/gptoss`，`--eval-per-epoch 4`；可用卡 H100 NVL 96 GB 三张、H200 NVL 143 GB 三张、RTX 6000 Ada 48 GB 四张、A6000 48 GB 十八张。

### 9.1 显存模型：三个探针点校准出「固定项 10.9 GB 加每 token 2.44 MB 加每损失位 1.8 MB」，再按层内张量逐项推到 1.7B 和 4B

8.6 节的两个数（每 token 2.7 MB、每损失位 1.8 MB）是从差值算出来的，每 token 2.7 MB 里混着损失位的份额。把 `cgen_final_b16k` 的两个探针点联立（最满块 54.38 GB 是 16,384 个 token 加 1,984 个损失位，最长事件 36.47 GB 是 9,504 个 token 加 1,344 个损失位，都在优化器状态已建、梯度常驻的条件下量），每损失位按 1.8 MB 扣掉后每 token 是 2.44 MB，固定项是 10.86 GB。固定项的账对得上：fp32 权重 2.38 GB（596.05M 个参数，从 safetensors 头文件数出来）、autocast 缓存的 bf16 权重副本 1.19 GB、fp32 梯度 2.38 GB、AdamW 两份状态 4.77 GB，合计 10.73 GB，差 0.13 GB。校验点：final_b16k 整程峰值那一块（B=3、L_pad 5,344，16,032 个 token、4,736 个损失位）按 10.86 + 2.44 × 16.032 + 1.8 × 4.736 算是 58.5 GB，实测 58.47；`cgen_final_b24k_probe` 的最满块（24,576 个 token，损失位数没记，按 3 个 64 行事件约 3,000 估）算是 76.2 GB，实测 76.47。开梯度检查点的每 token 系数从第七节第 7 步反推：`--grad-ckpt` 下最长事件多出 4.36 GB，扣掉 1,344 个损失位的 2.42 GB 剩 1.94 GB，除以 9,392 个 token 是 0.21 MB。

三个底座的每 token 激活按层内为反向保存的张量逐项推（单位是每 token 每层的字节；隐藏维 d、中间维 I、q 的总维 nq = 头数 × 128、K/V 经 `repeat_kv` 之后也是 nq；三个底座的 `config.json`：0.6B d 1024、I 3072、28 层、16 头；1.7B d 2048、I 6144、28 层、16 头；4B d 2560、I 9728、36 层、32 头；K/V 头都是 8、head_dim 都是 128）：随 d 走的六项（两个 RMSNorm 的 fp32 输入各 4d、两个 RMSNorm 的 bf16 输出各 2d、`o_proj` 和 `down_proj` 的 bf16 输出各 2d）合计 16d；随注意力维走的（q/k/v 投影输出、q_norm 与 k_norm 的输入输出、旋转后的 q 与 k、`repeat_kv` 出来的 K 与 V、sdpa 的输出和 logsumexp）0.6B 与 1.7B 都是 38,976 字节，4B 是 67,712 字节；随 I 走的（gate、up、silu、乘积四个 bf16 输出）8I。每层合计 0.6B 79,936 字节、1.7B 120,896 字节、4B 186,496 字节；乘层数后 0.6B 是 2.24 MB（实测 2.44 的 92%，差额是没列进来的瞬时张量），1.7B 是 0.6B 的 1.51 倍，4B 是 3.00 倍。开检查点的时候留住的是每层的 fp32 输入 4d 乘层数再加一层的重算量：1.7B 是 0.6B 的 1.80 倍，4B 是 2.85 倍。把倍率套在实测系数上：不开检查点每 token 0.6B 2.44、1.7B 3.68、4B 7.32 MB；开检查点 0.6B 0.21、1.7B 0.38、4B 0.60 MB。每损失位的 1.8 MB 只随词表走（四份 151,936 维向量），三个底座相同，开不开检查点也相同（logits 在检查点段之外）。

固定项（GB，十进制；参数量从 safetensors 头文件数出来：1.7B 1,720.57M，4B 4,022.47M；LoRA r16 挂七件套的参数量按 r × (输入维 + 输出维) 逐模块算：1.7B 17.43M，4B 33.03M）：b17 全参 fp32 权重 6.88 加 bf16 副本 3.44 加梯度 6.88 加两份状态 13.76 是 30.97；l17 是 6.88 加 3.44 加 LoRA 四份 0.28 是 10.60；l4 是 16.09 加 8.04 加 0.53 是 24.66。另外 `lora_util.save_merged` 存最好版本的时候 `copy.deepcopy(wrapped)` 在显卡上再复制一份 fp32 底座（`lora_util.py` 第 80 到 87 行），l17 瞬时多 6.9 GB，l4 瞬时多 16.1 GB，每次 `val_ce` 创新低都会发生一次。

### 9.2 epoch 0 的 1,577 个物理块（CPU 复现，脚本 `enum_blocks.py`，结果 `enum_blocks.json`）

扫描的 12 个 run 种子相同（`SEED` 42）、分词器相同（三个 Qwen3 底座共用一份词表）、预算相同，所以 epoch 0 的物理块序列 12 个 run 完全一样，在 CPU 上按 `share_data.load_events`（全集、`limit=0`）、`random.Random(42)` 打乱、每 4 个事件一个逻辑小批、`chunk_by_budget(16384)` 复现一遍就是真值（脚本与结果收在 `verify/enum_blocks.py` 与 `verify/enum_blocks.json`，在仓库根用 `cprobe-env/bin/python` 跑，train 集逐行分词 490 秒，val 集 327 秒）。事实：train 集丢 1 个超长事件后 4,126 个事件、186,415 行（`load_events` 的 `n_rows`），1,032 个逻辑小批、516 次更新（热身 int(516 × 0.05) = 25 步），1,577 个物理块（B=1 的 347 块，B=2 的 402 块，B=3 的 337 块，B=4 的 491 块），补齐后一共 14,961,456 个 token，真实 10,635,282 个，补齐占 28.9%，损失位一共 2,714,738 个；每块的损失位十分位是 14 / 279 / 549 / 1,088 / 1,454 / 1,741 / 2,023 / 2,313 / 2,653 / 3,038，最大 5,696，超过 4,000 的块 15 个，超过 5,000 的 2 个。token 最多的块是 B=4、L_pad 4,096 的 16,384 个 token（正好 16,384 个 token 的块有 8 个，损失位从 1,649 到 4,271，脚本取到的第一块只有 2,249 个损失位）；损失位最多的块是 B=2、L_pad 6,368 的 12,736 个 token、5,696 个损失位（第 950 个逻辑小批，第 475 组）；「token 数 / 最大 token 数 + 损失位数 / 最大损失位数」最大的块是 B=3、L_pad 5,120 的 15,360 个 token、4,992 个损失位。按 9.1 的系数算每块的「每 token 系数 × token 数 + 1.8 × 损失位数」，不开检查点的时候最大的块是 16,384 个 token 加 4,271 个损失位的一块（第 490 组；0.6B 47.7 GB，1.7B 68.0 GB），开检查点的时候 0.6B 和 1.7B 最大的都是损失位最多的那一块（12,736 个 token 加 5,696 个损失位），4B 最大的是 15,360 加 4,992 那一块，三块的代价彼此差不到 3%。最长事件 `appworld_aa8502b_2_r2|s6` 拼接后 9,492 个 token、1,344 个损失位，在任何一个系数下都排不进前三。

val 集丢 3 个超长事件后 2,553 个事件、115,019 行，在评估预算 32768 下 220 个物理块，补齐只占 1%（全集一起装块，块里最多 58 个事件），损失位最多的块 11,270 个（B=12、L_pad 2,720），token 最多的块 32,768 个（B=4、L_pad 8,192，3,776 个损失位）。评估在 `torch.no_grad` 下，每个损失位只有 bf16 logits 和 fp32 副本两份共 0.9 MB，11,270 个是 10.1 GB，层内激活不保存，评估的峰值在每个配置里都不高于训练的峰值。

### 9.3 时间的依据：训练吞吐、评估耗时、装载耗时、旧评测脚本的生成速率

训练吞吐只有 0.6B 的实测：`cgen_final_b16k` 450 个事件 20,641 行 `train_s` 109.7 秒是 188 行每秒，按补齐 token 算是 1,649,168 / 109.7 = 15.0k token 每秒（8.3 节各窗口 12.9k 到 16.9k）。全 epoch 按 token 算是 14,961,456 / 15,000 = 997 秒，按行算是 186,415 / 188 = 991 秒，两个口径都是 16.6 分钟。评估耗时：同一个 run 的 `eval` 事件时间戳减最后一条 `step` 的时间戳是 27.4 秒过 20,034 行 val，731 行每秒，115,019 行是 157 秒，四次 10.5 分钟。装载耗时：该 run 从台账登记的发射时刻 15:09 到 `start` 事件的 15:12:25 是 3 分半（装模型、对齐检查、450 个事件的分词），`--mem-probe` 的全集重新分词从 `start` 到第一条 `mem_probe` 事件是 423 秒；CPU 复现里 train 全集分词 490 秒、val 全集 327 秒。扫描的 run 是全集，所以 `start` 之前要分词 train 与 val 全集约 13.5 分钟，`--mem-probe` 打开的时候 `main()` 第 751 行会把 train 全集再分词一遍（`--max-events 0` 的时候 `tr_events` 本来就是全集，第 751 行没有复用），再花 8 分钟。

旧训练器的评估里生成那一段没有单独计时，可用的实测是评测脚本 `eval_causal_call.py` 的生成（`generate()` 第 204 到 225 行：HF `generate`、greedy、左 padding、`max_new_tokens` 96、`--bs` 默认 8、bf16 权重、提示左截到 `max_len − 96` 即 4,000 个 token）：np821 四个底座的 cgen 评测日志 `logs/eval_np821{b06,b17,l17,l4}_gptoss_cgen.log` 里每 8 条一条心跳，b06（H200）2,227 条 21.9 分钟是 1.70 条每秒、每批 8 条的中位 3.7 秒（10 分位 0.7、90 分位 9.1）；b17（H100）1.85 条每秒、中位 2.9 秒；l17（H100）2.02 条每秒、中位 2.5 秒；l4（H100）1.57 条每秒、中位 4.4 秒（90 分位 9.2）。cparam 的评测跑 gt_tool 和 pred_tool 两遍，每批中位 0.6 到 1.5 秒（目标串短，早停）。旧训练器里生成评估的常量：`MAX_GEN_TOK = 96`（`train_causal_callgen.py` 第 85 行、`train_causal_param.py` 第 83 行都是 96；来信里写的 cgen 160 是 `MAX_TGT_TOK`，第 84 行），`GEN_N = 200`，`--gen-bs` 默认 8，生成的时候模型是 fp32 权重套 bf16 autocast、`@torch.no_grad()`（第 308 到 332 行）。旧训练器整个 epoch 末评估（115,211 行 CE 加 200 条生成）b06 在 H100 上稳态 33.7 分钟、b17 52 分钟、l17（Ada）170 分钟、l4（H200）113 分钟（各 run 的 `train_log.jsonl` 里 `eval` 减最后一条 `step` 的时间戳再扣掉剩余步数）。

旧训练器同卡同数据的整程比值（记忆里的 np821 墙钟表，3 个 epoch）：b17 全参加检查点在 H100 上 30 小时对 b06 无检查点 18 小时是 1.67 倍；l4 LoRA 加检查点在 H200 上 64.3 小时对 b06 是 3.6 倍；l17 LoRA 加检查点在 Ada 上 98.5 小时对 b06 是 5.5 倍。算力账（估计）：线性层 FLOPs 随非嵌入参数走，0.6B 0.44B、1.7B 1.41B、4B 3.63B，比值 1 / 3.2 / 8.3；注意力 FLOPs 随头数 × head_dim × 层数走，比值 1 / 1 / 2.57；0.6B 在 15k token 每秒的时候按 3.4 节的算式折算（L 取 5,000，每 token 前向加反向约 6.6 GFLOP）约 100 TFLOPS，是 H100 NVL bf16 稠密峰值 835 TFLOPS 的 12%，大底座的利用率会更高，所以时间比值低于 FLOPs 比值。下面 9.4 用的倍率是估计：1.7B 不开检查点 1.5 到 2 倍，开检查点再乘 1.3；4B LoRA 开检查点 3.5 到 5 倍；LoRA 比全参略快（冻结权重不算权重梯度）算 0.8 到 1 倍；48G 卡对 H100 的倍率取 Ada 3.3 到 4、A6000 5 到 7（p1 批 0.6B LoRA 加检查点在 A6000 上 1.2 行每秒对 H100 全参 11 行每秒）。

### 9.4 第一问：排卡

下面是判读。峰值估计 = 固定项 + 每 token 系数 × 最坏块 token 数 + 1.8 MB × 最坏块损失位数，最坏块按 9.2 的枚举对每个配置各取代价最大的一块，再乘 1.1（决定 25 的探针折）和卡容量比较。卡容量按 torch 看到的总量：H100 93.10 GiB = 100.0 GB，H200 140.4 GiB = 150.8 GB，48G 卡按 nvidia-smi 的 49,140 MiB 折 51 GB。裁决线照 spec 第 10 节：乘 1.1 之后余量不足 10% 就不上。

| 配置 | 固定项 | 最坏块（token，损失位） | 激活加损失位 | 峰值估计 | 乘 1.1 | H100 100 GB | H200 151 GB | 48G 卡 51 GB |
|---|---|---|---|---|---|---|---|---|
| b06 不开检查点 | 10.9 | 16,384，4,271 | 40.0 + 7.7 | 58.5 | 64.4 | 64%，上 | 43%，上 | 装不下 |
| b06 开检查点 | 10.9 | 12,736，5,696 | 2.7 + 10.3 | 23.8 | 26.2 | 26% | 17% | 51%，上 |
| b17 不开检查点 | 31.0 | 16,384，4,271 | 60.3 + 7.7 | 99.0 | 108.9 | 109%，装不下 | 72%，上 | 装不下 |
| b17 开检查点 | 31.0 | 12,736，5,696 | 4.8 + 10.3 | 46.1 | 50.7 | 51%，上 | 34% | 99%，装不下 |
| l17 不开检查点 | 10.6 | 16,384，4,271 | 60.3 + 7.7 | 78.6 | 86.5 | 87%，余 13%，再打碎片折就不够 | 57%，上 | 装不下 |
| l17 开检查点 | 10.6 | 12,736，5,696 | 4.8 + 10.3 | 25.7 | 28.3 | 28% | 19% | 55%，上（存最好版本瞬时再加 6.9，到 69%） |
| l4 开检查点 | 24.7 | 15,360，4,992 | 9.2 + 9.0 | 42.9 | 47.2 | 47%，上 | 31%，上 | 93%，装不下（存最好版本瞬时再加 16.1） |
| l4 不开检查点 | 24.7 | 16,384，4,271 | 119.9 + 7.7 | 152 | 168 | 装不下 | 装不下 | 装不下 |

`--tok-budget` 四个配置都取 16384：显存表里没有一个配置需要退预算才能上推荐的卡，b24k 在 0.6B 上慢 16%（8.5 节），预算相同 12 个 run 的物理块序列就完全相同（9.2），底座之外没有第二个变量。`--grad-ckpt` 的取法：b06 在 H100 或 H200 上不开、在 48G 卡上开；b17 在 H200 上不开、在 H100 上开；l17 在 H200 上不开、在 H100 或 48G 卡上开；l4 只能开，并且只能上 H100 或 H200（48G 卡上 93% 已经过线，存最好版本的时候深拷贝再加 16 GB 必炸）。每个配置的墙钟估计（分钟；训练按 9.3 的倍率乘 16.6 分钟，评估按 4 次乘 2.6 分钟再乘同一倍率，`start` 之前的装载与对齐 0.6B 约 17 分钟、1.7B 约 20 分钟、4B 约 25 分钟，`--mem-probe` 不复用 `tr_events` 的话各再加 8 分钟）：b06 在 H100 不开检查点 17 + 10.5 + 17 约 45 分钟；b06 在 48G 卡开检查点 110 到 155 加 52 到 74 加 17 约 3 到 4 小时；b17 在 H200 不开检查点 25 到 34 加 21 加 20 约 66 到 75 分钟；b17 在 H100 开检查点 33 到 44 加 21 加 20 约 74 到 85 分钟；l17 在 H200 不开检查点 20 到 27 加 21 加 20 约 60 到 70 分钟；l17 在 48G 卡开检查点 86 到 140 加 69 到 84 加 20 约 2.9 到 4 小时；l4 在 H100 或 H200 开检查点 60 到 85 加 36 到 52 加 25 约 2 到 2.7 小时。上面的分钟数不确定度是三到五成，只有 0.6B 在 H100 上那一行有实测基础。

排卡方案两个。方案甲是 12 个 run 一次全开：H200 三张给 b17 不开检查点（72%），H100 三张给 l4 开检查点（47%），Ada 三张给 l17 开检查点（55%），A6000 三张给 b06 开检查点（51%），一张 Ada 和十五张 A6000 空着；总墙钟由 48G 卡上的 b06 和 l17 决定，约 3 到 4 小时，好处是发射一次、不用等第二波。方案乙是 9 张卡两波：H100 三张给 l4 开检查点（2 到 2.7 小时）；H200 三张先跑 b17 不开检查点（66 到 75 分钟）、跑完接 l17 不开检查点（60 到 70 分钟），合计 2.1 到 2.4 小时；Ada 三张给 b06 开检查点（训练 16.6 × 1.3 × 3.3 到 4 是 71 到 86 分钟，评估 35 到 42，装载 17，合计 2.1 到 2.4 小时）；总墙钟约 2 到 2.7 小时，由 l4 决定，代价是 H200 上要发第二波。两个方案的差（约 1 小时）小于估计的不确定度，我推荐方案乙，理由是 l4 那三个 run 无论怎么排都要 2 到 2.7 小时，方案乙把 l4 之外的九个 run 都压到 l4 的长度以内，而方案甲让 48G 卡上的 b06 和 l17 两组 run 成为长尾；如果 plan-8-28 更看重一次发完，方案甲也不会 OOM。两个方案里 b06 都不在 H100 上跑，原因是 H100 要留给 l4：l4 开检查点 47 GB 上 H100 有 53% 余量，上 48G 卡过线。

三件要在发射前处理的事。第一，`--mem-probe` 的全集重分词（9.3 的 8 分钟）在扫描里是纯浪费，`main()` 第 750 到 754 行在 `args.max_events == 0` 的时候应当直接把 `tr_events` 传给 `run_mem_probe`；第二，扫描 run 都开 `--mem-probe`，探针在开训前就把最坏块量出来，OOM 会发生在前 30 分钟而不是训练中途；第三，产物盘：最好版本全参 fp32 落盘 0.6B 2.4 GB、1.7B 6.9 GB、4B 合并后 16.1 GB，12 个 run 合计约 97 GB，每次 `val_ce` 创新低重写一次，NFS 上要有位置。

### 9.5 第二问：探针的 `cost` 挑块方式

下面是判读。`cost` 模式不带系数、只跑两块，在 epoch 0 上会漏掉真峰，但漏得不多，加一块就补上。9.2 的枚举给出反例：不开检查点的时候代价最大的块是 16,384 个 token 加 4,271 个损失位，既不是脚本取到的「token 最多的块」（16,384 加 2,249，估 54.9 GB），也不是「损失位最多的块」（12,736 加 5,696，估 52.2 GB），真峰 58.5 GB 比两块的大者高 3.6 GB（6%）；开检查点的时候损失位那一项占大头（1.8 MB 对每 token 0.21 到 0.60 MB），损失位最多的块就是代价最大的块，两块模式不漏。漏的原因是 token 数最大的块有 8 个并列（都是 16,384 个 token，损失位从 1,649 到 4,271），脚本取到哪一块由排序的稳定性决定。补法两条，都不带系数：取 token 最多的块的时候并列的按损失位多的优先，取损失位最多的块的时候并列的按 token 多的优先；再加第三块，「token 数 / 最大 token 数 + 损失位数 / 最大损失位数」最大的那一块（epoch 0 是 15,360 加 4,992，估 57.3 GB）。三块各在「状态已建、连做两次反向」的条件下量，`worst` 取三者最大。按 9.1 的五套系数在 1,577 块上核过：三块里的最大值和线性模型的最大值五套都相同（差 0）；只挑两块、并列不按规则的时候，0.6B 不开检查点差 7.6%（激活加损失位那一项 44.0 对 47.7 GB）、1.7B 不开检查点差 5.4%、4B 开检查点差 1.7%、0.6B 与 1.7B 开检查点差 0。「最长事件」那一条在 `cost` 模式里不必单独跑：枚举的是真实物理块，最长事件要么已经在某一块里，要么在预算小于最长事件拼接长度的时候独自成块，两种情况都被枚举覆盖；epoch 0 的最长事件（9,492 个 token、1,344 个损失位）在任何系数下都排不进前三。枚举要用训练循环同一条路径：`random.Random(SEED + ep)` 打乱、`events_per_mb` 切逻辑小批、`chunk_by_budget`，`--epochs` 大于 1 的时候每个 epoch 各枚举一遍取并集（CPU 上几秒）。`tokens` 模式留着当保守上界：全集里两个最长事件拼成的块不是真实块，token 数只会比真实块多。

`loop` 模式我看到六个坑，第三条对三种模式都成立。第一，`sch.step()` 不能调：调了调度器就少一步，热身只有 25 步，少一步是 4%。第二，lr 置 0 的 `opt.step()` 会把真实梯度写进 AdamW 的两份状态并把 `step` 计数记成 1，探针后必须 `opt.state.clear()`（现行 `run_mem_probe` 第 299 行已经这么做），`weight_decay` 那一项 `p.mul_(1 − lr × wd)` 在 lr 为 0 的时候是空操作，参数不动。第三，随机数：LoRA dropout 0.05 在探针的前向里消耗 CUDA 随机数流，之后正式训练每一层的 dropout 掩码就和不带探针的 run 不同（Qwen3 没有 dropout，只有 `--lora` 受影响），三种模式都应当在探针前后保存和恢复 `torch.get_rng_state()` 与 `torch.cuda.get_rng_state()`，`random.Random(SEED + ep)` 是独立实例不受影响。第四，峰值计数器要在挑中的更新组第一次前向之前 `reset_peak_memory_stats`、在第二个逻辑小批最后一块反向之后读，`clip_grad_norm_` 之后或者 `opt.step()` 之后读也一样（`max_memory_allocated` 是 reset 之后的高水位，不随释放回落；状态已经预建，`opt.step()` 不再分配）。第五，结束的时候 `opt.zero_grad(set_to_none=True)`，否则累积的梯度带进第一次真实更新。第六，`loop` 只跑一组，一组里第二个逻辑小批反向期间的梯度常驻和 `cost` 模式的「同一块连做两次反向」是同一个条件，所以 `loop` 在真峰上给不出 `cost` 给不出的数；`loop` 唯一多出来的是块形状变化引起的分配器行为，而一组两个小批看不出碎片（ctool 那次 OOM 的 14.58 GiB 预留未用是整程积累的）。所以我的建议是 `tokens` 和 `cost` 两个模式必做、默认 `cost`，`loop` 可以不做；要做就按上面六条写，并且把挑组的规则定成「含代价最大块的那一组」。

另外一条和探针无关但同一段代码里的事：探针在 `lora_util.wrap` 和 `gradient_checkpointing_enable` 之后跑（`main()` 第 657 到 663 行在第 750 行之前），量到的就是训练用的形态，探针晚于包装和检查点开启的顺序在现行代码里是对的。

### 9.6 第三问：生成式评估回来的代价

下面是判读。一次 200 条 greedy 生成在 H100 上的秒数按评测脚本的实测折算：每批 8 条的中位 2.5 到 4.4 秒、四个底座的总速率 1.57 到 2.02 条每秒（9.3），200 条是 25 批，按总速率是 100 到 130 秒。底座大小几乎不影响总速率（l4 1.57 对 b06 1.70），说明 bs 8 的逐 token 解码是按内核发射次数计时的，不是按 FLOPs。训练器里的条件比评测脚本差三处：fp32 权重套 autocast 并且在 `no_grad` 下，autocast 的权重缓存不生效，每一步都重新把 28 层或 36 层的七个权重转成 bf16（每层多七次发射，约多两成）；`--lora` 的时候适配器没有合并，每个线性层多两次小矩阵乘加一次缩放和一次相加（每层七个模块，发射次数接近翻倍）；提示左截到 `max_len − 96` 是 8,096 个 token 而不是 4,000，预填充翻倍（4B 上一批 8 × 8,096 个 token 的预填充约 0.5 PFLOP，约 1 秒）。所以估计：0.6B 全参一次生成评估约 2 到 3 分钟，4B LoRA 约 3 到 5 分钟；每 epoch 评四次就是 0.6B 8 到 12 分钟、4B 12 到 20 分钟。对照同一个 run 的训练和 CE 评估：0.6B 的训练 16.6 分钟、CE 评估四次 10.5 分钟，生成评估会把评估的时间翻倍、把整个 run 拉长两到三成；4B 的训练 60 到 85 分钟，生成评估占一到两成。cparam 的生成短得多（评测里每批中位 0.6 到 1.5 秒），一次约 20 到 40 秒。上面的分钟数是用评测脚本的速率外推的估计，训练器里的实际数要等第一次带 `--gen-n` 的 run 才有。如果要做成参数，`--gen-n 0` 关闭、默认 0 和决定 4 一致；开的时候建议只在 `frac = E` 的那一次评估做，四次里只做最后一次。

### 9.7 第四问：学习率网格

下面是判读。先算三个锚点。旧训练器一次更新 32 行（`--bs 4 --accum 8`），每个 epoch 5,828 次更新；新训练器一次更新 8 个事件平均 361 行（186,415 / 516），每个 epoch 516 次更新，行数是 11.3 倍、更新次数是 1/11.3。第一个锚点是「批大小不影响最优学习率」，也就是旧值 1e-5。第二个锚点是 Adam 常用的平方根规则，学习率随批大小的平方根走，11.3 的平方根是 3.4，得 3.4e-5；调查笔记 2.4 节里 Measuring the Effects of Data Parallelism 的原话说没有任何一条按批大小调学习率的规则可靠，换了批大小要重新调，所以平方根只是量级。第三个锚点是总位移相等：学习率对更新次数的积分决定参数沿平均梯度方向走多远，旧调度（17,484 步、热身 874、线性降到 0）在 epoch 0 的积分是峰值的 4,653 倍，新调度（516 步、热身 25、线性降到 0）整程的积分是峰值的 258 倍，比值 18.0，新训练器要在一个 epoch 里走完旧训练器 epoch 0 走过的路，峰值要 1.8e-4；旧 b06 cgen 的 `val_ce` 在 epoch 0 末最低（0.4793，之后两个 epoch 上升），说明旧训练器 epoch 0 末附近的位移量是够用的，再往后走反而过拟合。三个锚点相差 18 倍，所以一个 5 倍跨度的网格（草稿 2.3 的 {1e-5, 2e-5, 5e-5}）只能盖住前两个锚点，第三个锚点在网格外面；反过来只盖第三个锚点也不行，因为一次更新里的 361 行来自同一批 8 个事件，行与行共享前缀、目标高度相关，梯度的独立样本数介于 8 个事件和 361 行之间，噪声尺度的缩减不到 11.3 倍，平方根规则可能高估也可能低估。

推荐的网格：全参 {1e-5, 5e-5, 2e-4}，LoRA {1e-4, 5e-4, 2e-3}，四个底座配置按训法各用一套，不按底座改。全参三点的取法：1e-5 是旧值和第一个锚点，2e-4 是第三个锚点（1.8e-4 取整），5e-5 是对数中点（几何均值 4.5e-5 取整，也盖住平方根锚点 3.4e-5 的邻域）；跨度 20 倍、相邻 4 到 5 倍，调查笔记里扫描类来源的相邻档是 2 到 5 倍（SDFT {5e-6, 1e-5, 5e-5} 就有一档 5 倍）。LoRA 三点按调查笔记 2.2 节两篇实测的 10 倍关系（LoRA Learns Less and Forgets Less、LoRA Without Regret）对全参三点逐点乘 10，乘出来的三对 (1e-5, 1e-4)、(5e-5, 5e-4)、(2e-4, 2e-3) 可以直接检验 10 倍关系在这份数据上成不成立；现役的 2e-4 落在 1e-4 和 5e-4 之间，离两端都在一档以内；2e-3 在 Beware of the Batch Size 扫过的 1e-5 到 3e-3 范围之内，是 LoRA 三点里最可能发散的一点，发散本身也是答案（上界），一个 run 只有一两个小时。不按底座改的理由和 08-21 的裁决相同：只变底座一个变量；调查笔记 2.7 节按宽度的规则（LoRA 最优学习率随宽度的 −1/2 次方）给 0.6B 到 4B 的比值 0.63，µP 的 1/宽度规则给 0.6B 到 1.7B 的比值 0.5，都小于一档（4 到 5 倍）；torchtune 给 4B 全参 5e-6 的记录对本轮不适用，本轮的 4B 是 LoRA。和最小版的差别：最小版 {1e-5, 2e-5, 5e-5} 与 {1e-4, 2e-4, 5e-4} 都是旧值往上一到两档、跨度 5 倍，在更新单位没变的前提下是合理的；更新单位变了以后，第三个锚点在最小版之外，所以网格跨度从 5 倍放到 20 倍，上端从 5e-5 提到 2e-4，下端保留旧值当对照。判读规则先定好：最好的一点落在网格边上（1e-5 或 2e-4）就往那一边再加一档（3e-6 或 5e-4），落在中间就算扫完。

两处附带的事。热身 25 步在 2e-4 上比旧的 874 步短得多，spec 第 5 节的 5% 不动，但 step 日志里没有梯度范数，`clip_grad_norm_` 的返回值应当记进 `step` 事件，高学习率那一格是不是一直在被裁剪从日志里才看得出来。选最好版本用四个评估点里 `val_ce` 最低的一个，学习率线性降到 0 的调度下第四个点大概率就是最低，四个点的曲线本身是判读网格的依据，要保留在 `train_log.jsonl` 里。
