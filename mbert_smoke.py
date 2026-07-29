"""ModernBERT 本地部署冒烟测试。

权重在 NFS 上，不走 HF 下载；HF_HOME 也指到 net，防止任何自动下载写满家目录。
用法：mbert-env/bin/python mbert_smoke.py
"""

import os

MODEL_DIR = "/net/tokyo100-10g/data/str01_01/y_guo/models/modernbert-base"
os.environ.setdefault("HF_HOME", "/net/tokyo100-10g/data/str01_01/y-guo/hf")
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 断网加载，撞到下载就立刻报错而不是偷偷拉

import torch
import transformers
from transformers import AutoTokenizer, AutoModel, AutoModelForMaskedLM

print(f"transformers {transformers.__version__} / torch {torch.__version__}")
print(f"cuda available: {torch.cuda.is_available()}  device_count: {torch.cuda.device_count()}")

tok = AutoTokenizer.from_pretrained(MODEL_DIR)

# --- 检查 1：fill-mask，官方模型卡的例子，正确答案是 Paris ---
mlm = AutoModelForMaskedLM.from_pretrained(
    MODEL_DIR,
    dtype=torch.bfloat16,       # 维护者口径：ModernBERT 训练用 AMP-BF16，别碰纯 fp16
    attn_implementation="sdpa",       # 不装 flash-attn
).to("cuda").eval()

text = "The capital of France is [MASK]."
inputs = tok(text, return_tensors="pt").to("cuda")
with torch.no_grad():
    logits = mlm(**inputs).logits
masked_index = inputs["input_ids"][0].tolist().index(tok.mask_token_id)
pred = tok.decode(logits[0, masked_index].argmax(axis=-1))
print(f"[fill-mask] {text!r} -> {pred!r}   {'PASS' if pred.strip() == 'Paris' else 'FAIL'}")

# --- 检查 2：hidden state 维度，做特征时真正要的那个 ---
enc = AutoModel.from_pretrained(
    MODEL_DIR, dtype=torch.bfloat16, attn_implementation="sdpa"
).to("cuda").eval()

batch = tok(
    ["should I call a tool here?", "thanks, that explanation was clear"],
    return_tensors="pt",
    padding=True,
)
batch = {k: v.to("cuda") for k, v in batch.items()}
with torch.no_grad():
    out = enc(**batch, output_hidden_states=True)

last = out.last_hidden_state
print(f"[hidden] last_hidden_state {tuple(last.shape)}  dtype={last.dtype}")
print(f"[hidden] 层数(含 embedding 输出) {len(out.hidden_states)}  期望 23 = 22 层 + 1")
print(f"[hidden] 是否含 NaN: {torch.isnan(last).any().item()}")

# 池化成一条句向量——router 那类任务真正会用的形态
mask = batch["attention_mask"].unsqueeze(-1).to(last.dtype)
sent_vec = (last * mask).sum(1) / mask.sum(1)
print(f"[hidden] mean-pool 句向量 {tuple(sent_vec.shape)}  期望 (2, 768)")

ok = last.shape[-1] == 768 and len(out.hidden_states) == 23 and not torch.isnan(last).any()
print(f"\n{'ALL PASS' if ok and pred.strip() == 'Paris' else 'CHECK FAILED'}")
