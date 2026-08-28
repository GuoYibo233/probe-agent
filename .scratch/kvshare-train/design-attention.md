# 缓存复用训练器的注意力前向用形态 A 加 mem-efficient 内核（2026-08-28，CPU 验证已过，GPU 验证待主会话做）

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

## 三、内核会落到 mem-efficient，math 内核在 8192 上装不下

### 3.1 形态 A 在 GPU 上按优先级落到 mem-efficient

按第一节的事实推：掩码非空，flash 直接拒绝；优先级下一个是 mem-efficient，mem-efficient 接 4 维掩码（bool 或者浮点），head_dim 128、bf16、dropout 0、掩码不带梯度、批和头两维为 1，都在允许范围里；只要 mem-efficient 的资格检查通过，就轮不到 math。cudnn 排在 math 后面，默认情况下碰不到。推断的每一条都要在 GPU 上用 `torch.backends.cuda.can_use_efficient_attention(SDPAParams(q, k, v, mask, 0.0, False, False), debug=True)` 对真实形状问一遍，再用 profiler 看内核名（第六节第 1 到 3 步，脚本 `gpu_kernel_check.py`）。

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

## 五、对齐容差分两道：fp32 门禁每行 1e-5，bf16 粗筛每行平均 2e-2

### 5.1 ctool 的 `--align-tol` 验的是缓存增量前向和整段前向是同一个函数

`train_causal_tool.py` 第 200 到 240 行 `align_check`：取 val 集全文最长的一个事件（第 335 行），截断到 `--max-len`，fp32、`torch.set_float32_matmul_precision("highest")`（第 208 行，关 TF32），算两遍底座前向：整段一次前向，和逐 token 增量前向（每次喂 1 个 token 带 `past_key_values`，第 218 到 222 行），比较末位置的隐状态和分类头 logits 的最大绝对差（第 226 到 228 行），两个差都小于 `tol` 才 PASS，否则 `sys.exit(2)` 拒绝开训（第 345 到 354 行）。默认 `ALIGN_TOL = 1e-4`（第 76 行）。`3e-4` 是 c1 批次按 T8 先例放宽的值（`.claude/skills/probe-pipeline/references/invariants.md` 第 97 行：三个 ctool 的 hidden maxdiff 8.39e-5 到 1.68e-4、相对差 2.3e-6 到 3.3e-6，判为 fp32 噪声，记在 TIMELINE 2026-07-31 c1 条），np821 四个 ctool 的 `align_maxdiff_hidden` 是 9.78e-5 到 2.37e-4（`RESULTS.md` 第 23 到 32 行）。`--align-tol` 验的是「缓存增量前向和整段前向是同一个函数」，量的是 4096 个 token 之后隐状态的绝对差，全程 fp32，和 bf16 训练无关，也不比较 loss。

### 5.2 正确性门禁在 fp32 上定，bf16 只做粗筛

新训练器的对齐验收分两道。

第一道是正确性门禁，fp32、CPU、`highest` 精度，随机抽 5 个短事件（就用 `cpu_equiv_check.py` 的抽法，每个事件十几秒），形态 A 对旧训练器整批的每行 loss 最大绝对差不超过 1e-5，逐 token 最大绝对差不超过 1e-4。依据：5 个短事件实测每行 2.15e-6、逐 token 2.77e-5，3 个大事件（最多 64 行、打包后 3,689）实测每行 2.62e-6、逐 token 2.38e-5，门槛各留约 4 倍余量；掩码或者 position_ids 错一个位置，一行的 loss 会动 1e-2 到 1 的量级，远在门槛之上。把差值和同一次运行里「旧训练器单行对整批」的基线差一起打印，差值超过基线 3 倍就算可疑，即使差值本身还在 1e-5 以内。

第二道是 bf16 粗筛，在 GPU 冒烟之前用真实内核跑一次（`gpu_kernel_check.py` 第 6 步），34 行以上，形态 A 对旧训练器整批的每行 loss 平均绝对差不超过 2e-2、最大绝对差不超过 1e-1。依据：CPU 实测平均 8.9e-3、最大 3.6e-2，bf16 对 fp32 自己的差就有平均 8.0e-3、最大 3.0e-2；GPU 上 mem-efficient 内核的累加顺序和 CPU 不同，门槛留 2 到 3 倍。这道筛只能抓「整段错位」这种把 loss 挪掉 0.1 以上的错，抓不住细微的掩码错，所以不能替代第一道。

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

两次发射都在 tokyo108 GPU 0（H100 NVL，93.10 GiB）上，产物目录 `pipeline/runs/smoke/kvshare_gpu_kernel_check/`（`RUNMETA.json` 记 HEAD 024b34f）。第一次发射（日志 `logs/new1_kvshare_gpu_kernel_check_t108g0.log`）跑到第 3 步，第 4 步崩：脚本把前缀截到 2,048 却没有过滤行，16 行的尾巴各自带着 2,048 之后的整段 prompt，math 内核要分配 101.85 GiB。改脚本后补射（日志 `logs/new1_kvshare_gpu_kernel_check_t108g0.r1.log`，`gpu_result.json` 09:28 落盘），九步都跑完，第 6 步的两遍对齐报错，原因在 7.1 节。JSON 里记的环境：torch 2.11.0+cu128，`priority_order` `[1, 2, 0, 3, 4]`，`float32_matmul_precision` highest，`allow_tf32_matmul` False。脚本挑出来的最长事件是 `appworld_6bdbc26_1_r2|s17`：64 行，前缀 8,167 个 token，打包后 L 9,381，补到 16 的倍数是 9,392。

七步的事实（峰值都是 `torch.cuda.max_memory_allocated`，括号里是比进入每一步之前多出的量；秒数是前向加反向的墙钟，第 2、3 步含 profiler 开销）：

1. 内核资格：bool 掩码和 bf16 加性掩码两种情况下 `can_use_flash_attention` 都是 False，`can_use_efficient_attention` 都是 True，`can_use_cudnn_attention` 都是 True。
2. 强制 mem-efficient（bool 掩码）：峰值 31.08 GiB（多 28.86 GiB），3.06 秒，内核名 `fmha_cutlassF_bf16_aligned_64x128_rf_sm80` 和 `fmha_cutlassB_bf16_aligned_128x128_k128_sm80`；64 行 loss 平均 3.2452。
3. 默认选择（同一输入）：峰值 31.11 GiB（多 28.83 GiB），4.5 秒，内核名 `aten::_scaled_dot_product_cudnn_attention` 加 `cudnn_generated_fort_native_sdpa_sm90_flash_fprop_wgmma_f16` 与对应的 `bprop`；64 行 loss 平均 3.2500。
4. math 内核在短序列上：事件 `appworld_68ee2c9_1_r3|s2`（全文正好 2,048 个 token，64 行里装进 42 行），P 2,048、L 2,552，解析式 28 × 16 × 2,552² × 4 字节 = 10.87 GiB；math 峰值 22.55 GiB（多 20.26 GiB），2.33 秒；同一输入 mem-efficient 峰值 10.38 GiB（多 8.09 GiB），0.14 秒。42 行 loss 平均 math 2.3924、mem-efficient 2.3873。
5. 掩码四种变体（强制 mem-efficient）：bool 不补齐（L 9,381）31.11 GiB；bf16 加性不补齐 31.20 GiB；bool 补到 9,392 是 31.17 GiB；bf16 加性补到 9,392 是 26.65 GiB（多 24.36 GiB）。四种的 64 行 loss 平均都是 3.2452。
6. 对齐差值：bf16 和 fp32 两遍都报 `RuntimeError: No available kernel. Aborting execution.`，日志第 15 行 torch 给的拒绝理由原文是 `For dense input, both fused kernels require query, key and value to have the same num_heads. Query.sizes(): [1, 16, 463, 128], Key sizes(): [1, 8, 463, 128], Value sizes(): [1, 8, 463, 128] instead.`，没有拿到数。
7. `--grad-ckpt`：峰值 6.35 GiB（多 4.07 GiB），1.22 秒；`--lora`（r 16，七件套）：峰值 31.16 GiB（多 28.84 GiB），1.02 秒。

下面是解读。

形态 A 的前提成立：mem-efficient 接形态 A 的真实形状（L 9,381、head_dim 128、bf16、4 维掩码），第 2 步的内核名就是 cutlass 的 mem-efficient 前向和反向，四种掩码变体和 `--grad-ckpt`、`--lora` 都在同一个内核上跑通，loss 平均逐位相同。

默认内核选择在 H100 上落到 cuDNN，不是 3.1 节推的 mem-efficient；`priority_order` 在 GPU 上读出来仍是 flash、efficient、math、cudnn，所以 torch 在选择时对 sm90 另有偏好，选择逻辑在编译进 .so 的 `sdp_utils.cpp` 里，本次没有追。cuDNN 和 mem-efficient 的 64 行 loss 平均差 4.8e-3（3.2500 对 3.2452），是两个 bf16 内核的舍入路径不同。裁决不变并且理由加强：训练与评估都显式套 `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION])`，把内核钉死，不随 torch 默认顺序、cuDNN 版本和显卡型号漂移。

掩码定 bf16 加性、L 补到 16 的倍数：比另外三种省 4.5 GiB，和 2.4 节的预测一致（28 层各留一份 9,392² × 2 字节的掩码副本是 4.60 GiB；bool 掩码每层被 `convert_boolean_attn_mask` 转一份，bf16 不补齐每层被 `pad_bias` 复制一份，只有 bf16 补齐的那一份被 28 层共用）。

math 校准：同一输入 math 比 mem-efficient 多 12.17 GiB，解析式给 10.87 GiB，多出的 12% 是前向瞬时张量；64 字节每 L² 每层的系数成立，3.2 节的表照旧（L 9,381 要 147 GiB，任何卡装不下）。

显存余量：最长单事件在 bf16 补齐掩码下峰值 26.65 GiB，脚本里有 fp32 权重和梯度、没有优化器状态，训练时再加 AdamW 两份状态 4.47 GiB 是 31.1 GiB，对 H100 的 93.10 GiB 剩 62 GiB（67%）。多出的 24.36 GiB 折成每 token 2.72 MB（含瞬时），比 3.3 节估的留住量 2.42 MB 高 12%。按每 token 2.72 MB 估物理块：`--tok-budget` 16,384 个 token 的块约 41.5 GiB 激活，加静态 8.9 GiB 约 50 GiB，H100 占 54%；32,768 的块约 92 GiB，H100 装不下。16,384 和 32,768 两个块量的数是估算，spec 第 10 节的 `--mem-probe` 会量到真值。

排卡（48G 卡，RTX 6000 Ada 49,140 MiB = 48.0 GiB）：`--grad-ckpt` 把最长单事件从 31.1 GiB 压到 6.35 GiB，`--lora` 不省激活（31.16 对 31.08）。0.6B 全参不开检查点，最长单事件 31.1 GiB 装得下（余 35%），但 16,384 的块约 50 GiB 装不下，所以 48G 卡上 0.6B 要么开检查点要么把块量压到约 14,000 个 token 以内；1.7B（隐藏维 2048，28 层）的每 token 激活约是 0.6B 的 2 倍，4B（2560，36 层）约 3.2 倍，最长单事件不开检查点分别约 49 GiB 和 78 GiB，48G 卡上两个底座都必须 `--grad-ckpt`，LoRA 不能替代（1.7B、4B 的倍数是按隐藏维乘层数推的，没有实测）。

### 7.1 第 6 步的报错原因，以及训练器要绕的约束

原因：对齐检查的参照路径里有一批是「单行不补齐」，没有 padding，HF 的 `_ignore_causal_mask_sdpa` 跳过建掩码，`use_gqa_in_sdpa` 在掩码为空时返回 True，K、V 保持 8 头不做 `repeat_kv`，直接把 `enable_gqa=True` 传给 sdpa；mem-efficient 内核不支持 GQA（sdpa 的 docstring 原文 `Grouped Query Attention (GQA) is an experimental feature. It currently works only for Flash_attention and math kernel on CUDA tensor`），强制 EFFICIENT 的上下文里 flash 和 cudnn 又被关掉，于是没有内核可用。新路径永远带掩码，`repeat_kv` 到 16 头，不会撞上，第 2、3、5、7 步都在同一个上下文里跑通就是证据。

脚本的修法：`alignment()` 只给新路径套 `sdpa_kernel([EFFICIENT_ATTENTION])`，参照路径用默认选择；第 1 步多问两种资格（fp32 query 加 fp32 掩码；bf16 无掩码且 K/V 8 头）把「mem-efficient 不接 GQA」的约束写进 JSON。等补射出数再补 5.2 节第一道门槛在 GPU 上的依据。

训练器要绕的约束（spec 第 9 节要加一句）：对齐检查的参照路径（旧 `collate` 加 `inst_ce`）不套 `sdpa_kernel([EFFICIENT_ATTENTION])`，用默认内核选择；只有新路径（形态 A，永远带掩码）套。更一般的规则：凡是没有掩码的 sdpa 调用（HF 在 2 维掩码全 True 或者掩码为空的时候会跳过建掩码并开 `enable_gqa`）都不能放进强制 EFFICIENT 的上下文。训练器自己的训练和评估前向都是形态 A，都带掩码，不受影响。
