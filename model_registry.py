"""本工程唯一的模型地址映射。所有脚本经 resolve() 取路径,不许硬编码。

新增模型:在 MODELS 里加一行 (别名全小写)。本地目录优先写绝对路径;
走 HF 缓存的写 hub ID。CLI 用法: python model_registry.py qwen3.6
"""

from pathlib import Path

NET = "/net/tokyo100-10g/data/str01_01/zhou-y/models"

MODELS = {
    # 别名: (路径或 hub ID, 备注)。共享盘 NET 是正主,/home/zhou-y/hf_models 是旧副本。
    "qwen3.5-4b":  ("Qwen/Qwen3.5-4B",  "HF 缓存;fig1/traj pilot 主力"),
    "qwen3-8b":    ("Qwen/Qwen3-8B",    "HF 缓存;probe v1 / pilot8b"),
    "qwen3.5-9b":  ("/home/zhou-y/hf_models/Qwen3.5-9B",  "旧目录;共享盘暂无"),
    "qwen3.5-27b": (f"{NET}/Qwen3.5-27B", "共享盘,2026-07-28 验完整(11/11 分片)"),
    "qwen3.6-27b": (f"{NET}/Qwen3.6-27B",
                    "共享盘,2026-07-28 验完整(16 分片+tokenizer);多模态壳 "
                    "Qwen3_5ForConditionalGeneration,64 层,bf16 52G,单 48G 卡放不下"),
    "gpt-oss-120b": ("/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b",
                     "自有副本,2026-07-28 下完并验收(15 分片+tokenizer,~61G 主权重);"
                     "MoE 激活 5B 级,单 H200 可载;original/ 子目录 65G 是参考格式,"
                     "vLLM 用不到"),
    "modernbert-base": ("/net/tokyo100-10g/data/str01_01/y-guo/models/ModernBERT-base",
                        "自有副本,2026-07-29 验收(config+model.safetensors 571M+tokenizer);"
                        "ModernBertForMaskedLM,149M 参数,max_pos 8192;"
                        "onnx/ 子目录 1.5G 是导出格式,transformers 用不到"),
}
ALIASES = {"qwen3.6": "qwen3.6-27b", "qwen3.5": "qwen3.5-27b"}


def resolve(name: str) -> str:
    key = ALIASES.get(name.lower(), name.lower())
    if key not in MODELS:
        raise KeyError(f"unknown model '{name}'; known: {sorted(MODELS)}")
    path, _ = MODELS[key]
    if path.startswith("/") and not Path(path).exists():
        raise FileNotFoundError(f"{key}: {path} 不存在(NFS 没挂?)")
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(resolve(sys.argv[1]))
    else:
        for k, (p, note) in MODELS.items():
            print(f"{k:14s} {p}   # {note}")
