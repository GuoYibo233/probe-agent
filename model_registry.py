"""本工程唯一的模型地址映射的读取口。表本体在 configs/models.json
(2026-08-20 搬过去的,gen-preset 改造),这里只留读取器,
resolve() 的签名和行为与搬家前一字不改。

所有脚本经 resolve() 取路径,不许硬编码。
新增模型:在 configs/models.json 的 models 里加一条(别名全小写)。
本地目录优先写绝对路径;走 HF 缓存的写 hub ID。
CLI 用法: python3 model_registry.py qwen3.6
"""

import json
from pathlib import Path

_D = json.loads((Path(__file__).resolve().parent
                 / "configs" / "models.json").read_text())
MODELS = {k: (v["path"], v["note"]) for k, v in _D["models"].items()}
ALIASES = dict(_D.get("aliases", {}))


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
