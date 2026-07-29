# ModernBERT 部署情报

> 侦察日期：2026-07-28　情报来源：deploy-scout agent（只读官方文档/源码/issue，未实机验证）
> 用途预设：uv 管理环境、48G A6000 或 H200、研究实验（拿 hidden state / 做 encoder 特征）
> **本文所有命令、参数、引文均逐字来自抓取到的官方页面；我的判断部分已单独标注。**

## TL;DR（部署前必读的四条）

1. **别 clone 研究仓库** AnswerDotAI/ModernBERT——那是给预训练用的。你只需要 `transformers` + HF 权重。
2. **dtype 用 bf16，绝不用纯 fp16**——issue 区最高频的 NaN 族根因就在这。
3. **transformers 钉 4.5x，别用 5.x**——5.1 起移除 `reference_compile`，社区所有排错帖失效。
4. **flash-attn 先不装**——新版不再默认走 FA2，`sdpa` 够用，编译 FA 是最可能吃掉半天的一步。

---

## 抓取记录

| URL | 结果 |
|---|---|
| https://raw.githubusercontent.com/AnswerDotAI/ModernBERT/main/README.md | 成功（全文） |
| https://huggingface.co/answerdotai/ModernBERT-base/raw/main/README.md | 成功（全文 173 行） |
| https://huggingface.co/answerdotai/ModernBERT-base/raw/main/config.json | 成功 |
| https://huggingface.co/answerdotai/ModernBERT-large/raw/main/config.json | 成功 |
| https://huggingface.co/answerdotai/ModernBERT-base/raw/main/tokenizer_config.json | 成功 |
| https://huggingface.co/answerdotai/ModernBERT-base/raw/6e461621ae9e/README.md（2024-12 旧版模型卡） | 成功 |
| https://huggingface.co/api/models/answerdotai/ModernBERT-base（+large，+commits，+author 列表） | 成功 |
| https://raw.githubusercontent.com/huggingface/transformers/main/docs/source/en/model_doc/modernbert.md | 成功 |
| .../transformers/{main,v4.48.0,v4.57.1,v5.0.0,v5.1.0,v5.5.0,v5.14.1}/…/modeling_modernbert.py + configuration_modernbert.py | 成功 |
| https://arxiv.org/abs/2412.13663 + https://arxiv.org/html/2412.13663v2 | 成功（Table 2 原文已提取） |
| GitHub issue 页 / API：AnswerDotAI#163 #174 #227，transformers #35382 #35388 #35574 #35988，PR #43030 | 成功 |
| https://raw.githubusercontent.com/Dao-AILab/flash-attention/main/README.md | 成功 |
| https://pypi.org/pypi/transformers/json | 成功（latest 5.14.1，requires_python >=3.10.0） |

---

## 项目概况

**ModernBERT** — BERT 架构的现代化重做：encoder-only、8192 原生上下文、RoPE + 局部/全局交替注意力 + unpadding。

- 研究仓库：https://github.com/AnswerDotAI/ModernBERT
- 论文：arXiv 2412.13663（v1 2024-12-18, v2 2024-12-19）
- 许可证：**Apache-2.0**。模型卡原话："We release the ModernBERT model architectures, model weights, training codebase under the Apache 2.0 license."（架构 + 权重 + 训练代码全开放，可商用）

**活跃度**（GitHub API，2026-07-28 抓取）：star 1704，open issues 66，最近 commit `2026-03-01T18:41:03Z "Pretraining documentation (#253)"`；上一个 commit 是 `2025-02-20 "Add efficiency scripts (#197)"`——**2025 年 3 月到 2026 年 3 月这一年研究仓库几乎零代码提交**。issue 有维护者回（NohTow 2025-11-27 在 #163、warner-benjamin 2025-12-12 在 #163），但延迟以月计。

**关键定位**（README 原话）：

> "This is the research repository for ModernBERT, focused on pre-training and evaluations. If you're seeking the HuggingFace version, designed to integrate with any common pipeline, please head to the ModernBERT Collection on HuggingFace"

拿 hidden state 做特征 **完全不需要 clone 这个仓库**。conda/composer/flash_attn==2.6.3 那套只对预训练有意义。

### 官方模型 ID 与规模

| 模型 ID | 层数 | hidden | 参数量（safetensors 实测） | 下载量 |
|---|---|---|---|---|
| `answerdotai/ModernBERT-base` | 22 | 768 | 149,655,232 (F32) | 6,742,478 |
| `answerdotai/ModernBERT-large` | 28 | 1024 | 395,881,664 (F32) | 1,256,117 |
| `answerdotai/ModernBERT-Large-Instruct` | — | — | 未抓取 | 477 |
| `answerdotai/ModernBERT-{base,large}-training-checkpoints` | — | — | 中间检查点 | 0 |

模型卡措辞："ModernBERT-base - 22 layers, 149 million parameters" / "ModernBERT-large - 28 layers, 395 million parameters"。两个模型 lastModified 都是 **2025-01-15**，权重一年半没动过。

来源：https://huggingface.co/answerdotai/ModernBERT-base 、 https://huggingface.co/api/models?author=answerdotai&search=ModernBERT

---

## 安装

模型卡当前版本（逐字）：

```sh
pip install -U transformers>=4.48.0
```

```bash
pip install flash-attn
```

来源：https://huggingface.co/answerdotai/ModernBERT-base/raw/main/README.md（第 50 行、第 58 行）

**关于"早期必须装 git 版"——已核实属实，但已过期。** 2024-12-26 版模型卡原话：

```sh
pip install git+https://github.com/huggingface/transformers.git
```

配的说明是 "Until the next `transformers` release, doing so requires installing transformers from main"。这句话在 2025-01-15 的 commit `ae3cb1ed2030 "Mention that users should use transformers v4.48.0 (#50)"` 里被替换成了 `pip install -U transformers>=4.48.0`。

来源：https://huggingface.co/answerdotai/ModernBERT-base/raw/6e461621ae9e/README.md 、 https://huggingface.co/api/models/answerdotai/ModernBERT-base/commits/main

**今天没有任何理由装 git 版**：ModernBERT 从 v4.48.0 起进主干，PyPI 上 transformers 最新是 5.14.1（requires_python >=3.10.0）。

### 研究仓库装法（只有做预训练才需要，逐字）

```bash
conda env create -f environment.yaml
# if the conda environment errors out set channel priority to flexible:
# conda config --set channel_priority flexible
conda activate bert24
# if using H100s clone and build flash attention 3
# git clone https://github.com/Dao-AILab/flash-attention.git
# cd flash-attention/hopper
# python setup.py install
# install flash attention 2 (model uses FA3+FA2 or just FA2 if FA3 isn't supported)
pip install "flash_attn==2.6.3" --no-build-isolation
# or download a precompiled wheel from https://github.com/Dao-AILab/flash-attention/releases/tag/v2.6.3
# or limit the number of parallel compilation jobs
# MAX_JOBS=8 pip install "flash_attn==2.6.3" --no-build-isolation
```

来源：https://raw.githubusercontent.com/AnswerDotAI/ModernBERT/main/README.md

---

## flash-attention：装不装、装不上会怎样

- **不是必需，有 fallback。** transformers 文档给的 AutoModel 例子直接写的是 `attn_implementation="sdpa"`；modeling 源码里 `_supports_flash_attn = True`、`_supports_sdpa = True`、`_supports_flex_attn = True`、`_supports_attention_backend = True`。
  来源：https://raw.githubusercontent.com/huggingface/transformers/main/docs/source/en/model_doc/modernbert.md 、 .../modeling_modernbert.py（第 349-352 行）

- **默认行为在 2026 年初变了，这是最容易踩的一条。** 官方文档现在明确写：

  > "Since ModernBERT no longer defaults to FlashAttention2, you must explicitly set `attn_implementation="flash_attention_2"` when loading the model for padding-free usage."

  改动来自 PR #43030 "[Model] Refactor modernbert with the attention interface"（merged 2026-01-29）。旧版（v4.48 时代）行为见 tomaarsen 在 issue #35382 的描述："By default, ModernBERT uses Flash Attention 2 (if installed & training on CUDA) for efficient training."
  来源：docs/modernbert.md 、 https://github.com/huggingface/transformers/pull/43030 、 https://github.com/huggingface/transformers/issues/35382

- **装不上 flash-attn 的代价**：拿不到 unpadding / padding-free 路径（文档："Padding-free inference and training requires `flash_attention_2` as the attention implementation"），速度损失可观（issue #35988 报告者称 FA 带来 ~10x，但那是 Windows 场景且同帖被指出该 wheel 有问题）。**功能上 SDPA 完全能跑。**

- **flash-attn 自身的安装门槛**（官方 README）：CUDA toolkit、PyTorch 2.2+、`packaging`/`psutil`/`ninja`、Linux、CUDA 12.0 and above；支持 Ampere/Ada/Hopper（A100、RTX 3090、RTX 4090、H100），Turing 要另一个 repo。安装命令逐字：`pip install flash-attn --no-build-isolation`，内存不够时 `MAX_JOBS=4 pip install flash-attn --no-build-isolation`。
  来源：https://raw.githubusercontent.com/Dao-AILab/flash-attention/main/README.md

---

## 硬件要求

- **显存**：论文 Table 2（NVIDIA RTX 4090 单卡，averaged over 10 runs）原文数字：
  `ModernBERT 149M 1604 148.1 147.3 98 123.7 133.8`
  `ModernBERT 395M 770 52.3 52.9 48 46.8 49.8`
  列含义按表头是「Params | 短上下文(512) 最大 batch size | 短上下文吞吐 fixed/variable | 长上下文(8192) 最大 batch size | 长上下文吞吐 fixed/variable（千 token/s）」。
  即 **24GB 卡上 base 在 8192 长度能开到 batch 98，large 能开到 48**。
  来源：https://arxiv.org/html/2412.13663v2（Table 2 及 4.2 节 "All efficiency evaluations are ran on a single NVIDIA RTX 4090"）

- **权重体积**：base 149.6M / large 395.9M 参数，Hub 上存的是 F32。bf16 加载时权重本身 base ≈0.3GB、large ≈0.8GB。（参数量是抓取事实；GB 换算是推算。）

- **单卡能不能跑**：能，24GB 消费卡就绰绰有余。48G A6000 / H200 属于严重过剩。

- **CUDA / 驱动**：模型卡和 transformers 文档 **都没有写 ModernBERT 自己的 CUDA 版本要求**。唯一硬约束来自可选依赖 flash-attn（CUDA 12.0+、Ampere 及以上）。ModernBERT 预训练用的是 8x H100（模型卡 Training 一节："Hardware: Trained on 8x H100 GPUs."）。

- **最大序列长度**：`max_position_embeddings: 8192`（两个 config.json 都是），tokenizer `model_max_length = 8192`。模型卡："native context length of up to 8,192 tokens"，Limitations 里提醒 "using the full 8,192 tokens window may be slower than short-context inference"。

---

## 依赖雷区

### 1. transformers 版本是唯一硬门槛：`>=4.48.0`

低于此版本 `model_type: "modernbert"` 不认识。

### 2. transformers 4.x 与 5.x 之间 ModernBERT 的 API 有实质变化（逐版本源码核对）

| 版本 | `modeling_modernbert.py` 里 `reference_compile` 出现次数 |
|---|---|
| v4.48.0 | 15 |
| v4.57.1 | 15 |
| v5.0.0 | 15 |
| v5.1.0 | **0** |
| v5.5.0 | 0 |
| v5.14.1 | 0 |
| main | 0 |

**`reference_compile` 在 transformers 5.1.0 起从 modeling 代码里彻底消失**，只在 `ModernBertConfig.to_dict()` 里留了一行 `output.pop("reference_compile", None)` 作向后兼容。网上 2025 年那些"加 `reference_compile=False` 就好了"的答案，在 5.1+ 上已经无效。

来源：各 tag 的 raw 源码 + https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/modernbert/configuration_modernbert.py（第 154-157 行）

### 3. config 结构在 main 上已重写

`ModernBertConfig` 现在是 `@strict` 的 dataclass（`from huggingface_hub.dataclasses import strict`），字段变成 `layer_types: list[str] | None`、`rope_parameters: dict[...]`；老的 `global_attn_every_n_layers` / `global_rope_theta` / `local_rope_theta` 走 `__post_init__(**kwargs)` 和 `convert_rope_params_to_dict` 做 BC 转换。**Hub 上的 config.json 还是老格式**（有 `global_attn_every_n_layers: 3`、`global_rope_theta: 160000.0`）。

### 4. 一个隐藏差异

main 的 `ModernBertConfig` 里 `classifier_pooling` 默认值是 `"cls"`，而 Hub config.json 里显式写的是 `"mean"`。如果自己 `ModernBertConfig()` 造配置而不是 `from_pretrained`，池化方式会和官方权重不一致。

### 5. 无需编译的 kernel

HF 版本没有自定义 CUDA kernel，纯 PyTorch + 可选 FA2。研究仓库那套（composer、MosaicBERT、flash_attn==2.6.3、FA3 源码编译）才是真麻烦，但用不到。

### 6. 没有 `token_type_ids`

模型卡明说 "ModernBERT does not use token type IDs... you can omit the `token_type_ids` parameter"；tokenizer_config 的 `model_input_names = ['input_ids', 'attention_mask']`。**老的 BERT 代码直接 `**tokenizer(...)` 传过去在旧版会炸。**

---

## 最小可跑代码

### 模型卡版（逐字，第 63-80 行）

```python
from transformers import AutoTokenizer, AutoModelForMaskedLM

model_id = "answerdotai/ModernBERT-base"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForMaskedLM.from_pretrained(model_id)

text = "The capital of France is [MASK]."
inputs = tokenizer(text, return_tensors="pt")
outputs = model(**inputs)

# To get predictions for the mask:
masked_index = inputs["input_ids"][0].tolist().index(tokenizer.mask_token_id)
predicted_token_id = outputs.logits[0, masked_index].argmax(axis=-1)
predicted_token = tokenizer.decode(predicted_token_id)
print("Predicted token:", predicted_token)
# Predicted token:  Paris
```

### pipeline 版（模型卡第 84-98 行，逐字）

```python
import torch
from transformers import pipeline
from pprint import pprint

pipe = pipeline(
    "fill-mask",
    model="answerdotai/ModernBERT-base",
    torch_dtype=torch.bfloat16,
)

input_text = "He walked to the [MASK]."
results = pipe(input_text)
pprint(results)
```

### transformers 官方文档版（逐字，含显式 attn_implementation）

```python
import torch

from transformers import AutoModelForMaskedLM, AutoTokenizer


tokenizer = AutoTokenizer.from_pretrained(
    "answerdotai/ModernBERT-base",
)
model = AutoModelForMaskedLM.from_pretrained(
    "answerdotai/ModernBERT-base",
    device_map="auto",
    attn_implementation="sdpa"
)
inputs = tokenizer("Plants create [MASK] through a process known as photosynthesis.", return_tensors="pt").to(model.device)

with torch.no_grad():
    outputs = model(**inputs)
    predictions = outputs.logits

masked_index = torch.where(inputs['input_ids'] == tokenizer.mask_token_id)[1]
predicted_token_id = predictions[0, masked_index].argmax(dim=-1)
predicted_token = tokenizer.decode(predicted_token_id)

print(f"The predicted token is: {predicted_token}")
```

### padding-free 版（文档逐字，注意它要求 FA2）

```python
import torch

from transformers import AutoModelForMaskedLM, AutoTokenizer, DataCollatorWithFlattening


model_id = "answerdotai/ModernBERT-base"
tokenizer = AutoTokenizer.from_pretrained(model_id)
collator = DataCollatorWithFlattening(return_flash_attn_kwargs=True)


def prepare_text_for_padding_free(texts):
    # base tokenization with padding and subsequent flattening
    inputs_dict = tokenizer(texts, return_tensors="pt", padding=True).to(model.device)
    flattened_features = collator(
        [
            {"input_ids": i[a.bool()].tolist()}
            for i, a in zip(inputs_dict["input_ids"], inputs_dict["attention_mask"])
        ]
    )

    for k, v in flattened_features.items():
        if isinstance(v, torch.Tensor):
            flattened_features[k] = v.to(model.device)

    return flattened_features


inputs = prepare_text_for_padding_free(
    ["The capital of France is [MASK].", "ModernBERT is a [MASK] model."]
)
model = AutoModelForMaskedLM.from_pretrained(
    model_id, attn_implementation="flash_attention_2", device_map="cuda"
)

# Optional: use torch.compile for faster inference
# model.forward = torch.compile(model.forward, fullgraph=True)

out = model(**inputs)
```

来源：https://raw.githubusercontent.com/huggingface/transformers/main/docs/source/en/model_doc/modernbert.md

---

## 关键参数

### config.json（Hub 实际值）

| 参数 | base | large | 作用 | 来源 |
|---|---|---|---|---|
| `max_position_embeddings` | 8192 | 8192 | 上下文上限 | config.json |
| `hidden_size` | 768 | 1024 | hidden state 维度（做特征时要的那个数） | config.json |
| `num_hidden_layers` | 22 | 28 | 层数 | config.json |
| `intermediate_size` | 1152 | 2624 | GeGLU 中间维 | config.json |
| `num_attention_heads` | 12 | 16 | — | config.json |
| `vocab_size` | 50368 | 50368 | — | config.json |
| `local_attention` | 128 | 128 | 局部注意力窗口总宽（main 里 `sliding_window` property = `local_attention // 2`） | config.json + configuration_modernbert.py:159-167 |
| `global_attn_every_n_layers` | 3 | 3 | 每 3 层一次全局注意力 | config.json |
| `global_rope_theta` / `local_rope_theta` | 160000.0 / 10000.0 | 同 | RoPE base | config.json |
| `classifier_pooling` | `"mean"` | `"mean"` | 分类头池化（main 默认值却是 `"cls"`） | config.json + configuration_modernbert.py:104 |
| `deterministic_flash_attn` | false | false | 文档："If `False`, inference will be faster but not deterministic." | configuration_modernbert.py:53-54 |
| `sparse_prediction` | false（config 未写，源码默认 False） | 同 | MLM 用稀疏预测而非稠密 logits | configuration_modernbert.py:55-56, 109 |
| `sparse_pred_ignore_index` | -100 | -100 | — | configuration_modernbert.py:57-58 |
| `torch_dtype` | `"float32"` | `"float32"` | **Hub 存的是 fp32，不显式指定就按 fp32 加载** | config.json |
| `pad/bos/eos/cls/sep_token_id` | 50283 / 50281 / 50282 / 50281 / 50282 | 同 | — | config.json |

### 只在 transformers 4.48 ~ 5.0 存在的参数（5.1+ 已从 modeling 移除）

| 参数 | 默认值 | 文档原话 | 来源 |
|---|---|---|---|
| `reference_compile` | `None` | "Whether to compile the layers of the model which were compiled during pretraining. If `None`, then parts of the model will be compiled if 1) `triton` is installed, 2) the model is not on MPS, 3) the model is not shared between devices, and 4) the model is not resized after initialization." | v4.48.0 configuration_modernbert.py:107-111, 169 |
| `repad_logits_with_grad` | `False` | "When True, ModernBertForMaskedLM keeps track of the logits' gradient when repadding for output. This only applies when using Flash Attention 2 with passed labels." | v4.48.0 configuration_modernbert.py:112-114 |

`attn_implementation` 可取值：`"sdpa"`（文档示例用的）、`"flash_attention_2"`（padding-free 必需）、`"eager"`（issue #35382 里 tomaarsen 提到）。

---

## 已知的坑（issue 区）

### 1. CPU 上推理直接崩

`ValueError: Pointer argument (at 0) cannot be accessed from Triton (cpu tensor?)`，栈里是 `rotary_kernel[grid]`。原因是编译路径把 triton kernel 拉起来了。社区解法（来自 HF discussion #10，issue 里确认有效，逐字）：

```
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_DIR,
    reference_compile=False
)
```

**注意：这个解法只对 transformers ≤5.0 有效**（见依赖雷区第 2 条）。
来源：https://github.com/huggingface/transformers/issues/35388

### 2. `RuntimeError` when training with `torch_compile`

tomaarsen 原话："FA2 isn't currently properly compatible with `torch` compilation. This is one of the reasons that we trained with specific components compiled (controllable via `reference_compile` in the model config) rather than the full model." 给出的规避是 `attn_implementation="sdpa"`（他补充这比直接跑 FA2 慢得多）。ArthurZucker 2025-01 认为新版 flash 已兼容；但 2025-08 有人在 torch 2.7.0+cu126 / transformers 4.53.0 / flash_attn 2.8.1 上仍复现，自述加 `gradient_checkpointing=True` 到 TrainingArguments 后可绕过。umarbutler 2025-08 怀疑根因是 pytorch/pytorch#159492。
来源：https://github.com/huggingface/transformers/issues/35382

### 3. NaN 全家桶（ModernBERT 最高频的报错族）

涉及 AnswerDotAI#163 #174 #224 #227、transformers #35574 #35988 #38720、HF discussion #59。已核实三条结论：

- **维护者官方口径**（warner-benjamin，AnswerDotAI#163，2025-12-12，逐字）：
  > "ModernBERT was trained in AMP-BF16. Finetuning in pure FP16 isn't an expected use case. Use AMP-BF16 or AMP-FP16 with PyTorch SDPA or preferably Flash Attention installed."

  同帖用户 beapirate 给出根因："Training a HF ModernBERT model in pure fp16 causes NaN weights after the first optimizer step. The root cause is Adam's default eps=1e-8 rounding to zero in fp16."

- **升级 torch 常能解决**：tomaarsen 在 #35574（2025-02-04）："I've seen `nan`'s more often now, and often times they were resolved by upgrading `torch`: `pip install -U torch`"

- **#35988 的 FA2 NaN 是 Windows 预编译 wheel 的问题**，不是 Linux 场景：报告环境 RTX 3090 / torch 2.5.1+cu124 / transformers 4.48.2 / flash-attn 2.7.1.post1 / Windows，评论指出那个 58MB 的 wheel "only suitable for inference and cannot be used for training"（正确编译的约 178MB）。

- **仍然开着的**：AnswerDotAI#174 "ModernBertModel works on the CPU but fails on the GPU"（GPU 上全 NaN，2025-01-08 开，无解法）；#35574 里"batch>1 时除一条外全是 NaN，batch=1 正常"这个现象没有公开定论。

### 4. `forward() got an unexpected keyword argument 'num_items_in_batch'`

transformers #35838 / #36074，均已 closed——老 transformers + 新 Trainer 组合时的签名不匹配。

### 5. ONNX 导出报错

transformers #35545（closed）。Hub 上 base 已经有官方导出好的 `onnx/model.onnx` 及 fp16/int8/q4 量化版，**别自己导**。

### 6. 多卡预训练比单卡还慢

AnswerDotAI#220（2025-03-31，至今 open，无回复）——只影响用研究仓库做预训练的人。

---

## 落地建议（这一节是 agent 的判断，不是文档原话）

**1. 别碰研究仓库。** 用途是"拿 hidden state / 做 encoder 特征"的话，README 自己就把你劝走了。conda + composer + `flash_attn==2.6.3` 那套是为复现 2T token 预训练准备的，装它是纯亏。要的只有 `transformers` + `torch`。

**2. uv 装法**（对官方 pip 命令的改写，不是文档原文）：

```
uv venv --python 3.11
uv pip install "transformers>=4.48.0" torch
```

建议 **显式钉一个 4.5x 的 transformers 而不是让 uv 解到 5.14.x**，两个理由：
- 5.1+ 移除了 `reference_compile`，网上所有 2025 年的 ModernBERT 排错帖（尤其 CPU triton 那条）在 5.x 上对不上号；
- `ModernBertConfig` 在 main 上已改成 `@strict` dataclass + `layer_types`/`rope_parameters` 新字段，而 Hub 上的 config.json 还是 2025-01 的老格式，BC 转换路径未经实机验证。

一周冲刺里，用一个和社区排错帖对得上的版本比用最新版划算。如果已有别的库把 transformers 拉到 5.x，别硬降，但要预期坑 1、2 的解法失效。

**3. 48G A6000 / H200 上跑 ModernBERT-large 是杀鸡用牛刀。** 论文在 24GB 的 4090 上，large 在 8192 长度都能开到 batch 48。48G 卡上 base 可以直接把 batch 拉到几百做特征抽取。真正的瓶颈会是 tokenization 和 IO，不是显存。

**4. dtype 选 bf16，别碰 fp16。** 维护者原话就是 ModernBERT 训练用 AMP-BF16，纯 fp16 微调"不是预期用法"。A6000（Ampere）和 H200（Hopper）都原生支持 bf16。这一条能规避掉 issue 区一半的 NaN 帖。

**5. flash-attn 建议先不装。** 理由：
- 现在的 transformers 不再默认走 FA2，必须手写 `attn_implementation="flash_attention_2"` 才吃得到，等于多一个显式开关；
- 只有 padding-free 路径强依赖它，做特征抽取用固定长度 batch 就行；
- 编译 flash-attn 是整个流程里最可能吃掉半天的一步（官方说 64 核机器 3-5 分钟，没 ninja 要 2 小时，内存不够还得 `MAX_JOBS`）。

先用 `attn_implementation="sdpa"` 跑通全流程，确认速度不够了再回头装。

**6. 预计会卡在哪一步**：大概率不是安装，而是
- (a) 老 BERT 代码里的 `token_type_ids` 直接传进去炸掉；
- (b) 第一次 GPU 前向出 NaN 时不知道该怪 dtype 还是怪 attention 实现——遇到就先切 `attn_implementation="sdpa"` + bf16 + 升级 `torch`，这三板斧覆盖了 issue 区绝大多数已解决案例。

**7. 拿 hidden state 的具体写法没有官方逐字来源。** 模型卡和 transformers 文档给的例子全是 MLM / fill-mask，没有 `output_hidden_states=True` 的官方片段。`ModernBertModel` 存在（`[[autodoc]] ModernBertModel - forward`），main 上它的 forward 签名开头是 `input_ids, attention_mask, position_ids, ...`，标准 HF 用法应该成立，但**这是推断，不是抓到的文档**。

**8. 集群选机**：一张 48G 卡（tokyo106/107 上的 A6000）足够，把 H200 留给别的任务。

---

## 未核实清单（部署时若撞上，先查这里）

- **ModernBERT 在 transformers 5.x（5.1+，含最新 5.14.1）上能否直接加载 Hub 上 2025-01 的老格式 config.json 而不报错。** 源码显示有 BC 路径（`__post_init__(**kwargs)` 吃 `global_attn_every_n_layers`、`convert_rope_params_to_dict` 吃 `global_rope_theta`/`local_rope_theta`），但 config 类现在带 `@strict` 装饰器，config.json 里还有 `position_embedding_type`、`gradient_checkpointing`、`_name_or_path` 等字段不在 dataclass 字段表里——会被吞还是抛异常，未跑代码无法确认。
- **在 transformers ≥5.1 上传 `reference_compile=False` 给 `from_pretrained` 会怎样**（静默忽略 / 报错 / 仍走 BC pop）。
- **超过 8192 token 输入的实际行为**（截断、报错、还是 RoPE 外推出垃圾）。文档只说 "native context length of up to 8,192"，没写越界语义。
- **论文 Table 2 的 benchmark dtype**（bf16 还是 fp16），只抓到 GPU 型号和 "averaged over 10 runs"。
- **`answerdotai/ModernBERT-Large-Instruct` 的具体规格、训练方式、许可证**——只从 HF API 拿到它存在、下载量 477，模型卡未抓。
- **AnswerDotAI#174（GPU 全 NaN）和 #35574（batch>1 才 NaN）的最终根因**，两处都没有结论性回复。
- **具体的 CUDA / 驱动最低版本**：ModernBERT 自己的文档从未给出，只有 flash-attn 的 CUDA 12.0+。
- ~~**hidden state 抽取的官方代码片段**：不存在于任何抓到的官方页面。~~ → 2026-07-28 实机验证可用，见下。

---

# 本地部署实录（2026-07-28，shiga，实机验证 ALL PASS）

**权重已在本地，不需要下载**：`/net/tokyo100-10g/data/str01_01/y_guo/models/modernbert-base/`
（2025-12-31 下的完整官方 base：safetensors + pytorch_model.bin + tokenizer + 全套 onnx 量化版。config.json 逐字段与官方 Hub 版一致。）

**存储目录归属——记牢，这里有个坑**：

| 目录 | 属主 | 能不能用 |
|---|---|---|
| `/net/tokyo100-10g/data/str01_01/y-guo/` | y-guo | ✅ 主力目录，已用 1.3T |
| `/net/tokyo100-10g/data/str01_01/y_guo/` | y-guo | ✅ ModernBERT 权重在这 |
| `/net/tokyo100-10g/data/str01_01/yguo/` | **zjiang** | ❌ **不是你的，别写** |

## 已验证可用的环境

环境路径：`/home/y-guo/reproduce/new1/mbert-env`

```bash
uv venv mbert-env --python 3.11
VIRTUAL_ENV=$PWD/mbert-env uv pip install "transformers>=4.48,<5.0"
VIRTUAL_ENV=$PWD/mbert-env uv pip install torch --index-url https://download.pytorch.org/whl/cu128
```

实测装出来的版本：**transformers 4.57.6 / torch 2.11.0+cu128 / triton 3.6.0 / Python 3.11.15**

## ★ 踩到的唯一一个坑：torch 的 CUDA 版本

**症状**（直接 `uv pip install torch` 装到 cu13 版时）：

```
RuntimeError: The NVIDIA driver on your system is too old (found version 12090).
```
且 `torch.cuda.is_available()` 返回 False，但 `device_count()` 返回 1 —— 这个自相矛盾的组合就是 driver/wheel 不匹配的特征。

**根因**：PyPI 默认的 torch 现在是 cu13 构建（torch 2.13.0+cu130），要求 CUDA 13 驱动；集群实际是 **驱动 575.64.03 / CUDA 12.9**。

**解法**：从 cu128 索引装 torch，即上面那条 `--index-url https://download.pytorch.org/whl/cu128`。

**这一条正是原笔记「未核实清单」里那条"ModernBERT 自己的文档从未给出 CUDA / 驱动最低版本"的实际后果——问题不出在 ModernBERT，出在 torch 的默认 wheel 越跑越前面。以后在这个集群装任何 torch 都要显式指定 cu128。**

## 冒烟脚本与实测结果

脚本：`/home/y-guo/reproduce/new1/mbert_smoke.py`

```bash
CUDA_VISIBLE_DEVICES=0 mbert-env/bin/python mbert_smoke.py
```

实测输出：

```
transformers 4.57.6 / torch 2.11.0+cu128
cuda available: True  device_count: 1
[fill-mask] 'The capital of France is [MASK].' -> ' Paris'   PASS
[hidden] last_hidden_state (2, 9, 768)  dtype=torch.bfloat16
[hidden] 层数(含 embedding 输出) 23  期望 23 = 22 层 + 1
[hidden] 是否含 NaN: False
[hidden] mean-pool 句向量 (2, 768)  期望 (2, 768)

ALL PASS
```

已验证的事实：
- bf16 + `attn_implementation="sdpa"`（**没装 flash-attn**）在 A6000 上正常，无 NaN。
- `output_hidden_states=True` 返回 23 个张量（22 层 + embedding 输出），最后一层维度 768。**原报告说"官方文档没有 hidden state 片段、只能推断"——现已实机确认标准 HF 用法成立。**
- 从本地目录 `from_pretrained("<绝对路径>")` 直接加载有效，配合 `HF_HUB_OFFLINE=1` 可确保不偷偷联网。

## 两个 API 变化（相对官方 2024 年底的模型卡）

1. **`torch_dtype=` 已废弃** → 用 `dtype=`。transformers 4.57 会警告 "`torch_dtype` is deprecated! Use `dtype` instead!"，官方模型卡上的老写法还能跑但会告警。
2. **`TRANSFORMERS_CACHE` 已废弃** → 用 `HF_HOME`。警告原文："Using `TRANSFORMERS_CACHE` is deprecated and will be removed in v5 of Transformers."
   注意：`~/.bashrc` 第 3、12 行和 `~/.profile` 第 8 行都还在 export `TRANSFORMERS_CACHE`。目前 `HF_HOME` 和 `HF_HUB_CACHE` 也都设了、指向同一处 net 目录，所以现在没问题；**但升到 transformers 5 之后那三行就会失效**，届时缓存可能悄悄回落到家目录。

## 环境变量现状（来自 ~/.bashrc，已确认生效）

```
HF_HOME=/net/tokyo100-10g/data/str01_01/y-guo/hf
HF_HUB_CACHE=/net/tokyo100-10g/data/str01_01/y-guo/hf/hub
TRANSFORMERS_CACHE=/net/tokyo100-10g/data/str01_01/y-guo/hf/hub   # 已废弃，见上
```

缓存已经指到 net，不会写满家目录。
