"""configs/ 的读取器,纯标准库(采集 venv 装不进 pydantic 2,教训在
envs/collect/common.py 文件头)。

configs/models.json  是唯一模型地址映射,model_registry.py 从这里读;
configs/presets/*.json 一份文件一套生成设置:model 别名 + server 节
(vLLM 启动参数,serve_preset.py 吃) + client 节(采样参数,各入口吃)。
两节都可省;client 节里 null = 不指定,落到调用方原有缺省。

入口脚本的用法(三层优先级 CLI 显式值 > 预设值 > 原有缺省):

    from preset_loader import load_preset, merge_client
    pre = load_preset(args.preset) if args.preset else None
    eff = merge_client({"api": args.api, ...},          # None = 用户没显式给
                       (pre or {}).get("client"),
                       {"api": "raw", ...})             # 原有缺省
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS_JSON = ROOT / "configs" / "models.json"
PRESET_DIR = ROOT / "configs" / "presets"

# client 节的合法键 -> 期望类型(None 永远合法)
CLIENT_KEYS = {
    "api": str,
    "reasoning_effort": str,
    "temperature": (int, float),
    "top_p": (int, float),
    "max_tokens": int,
    "stop": list,
    "start_date": str,
    "seed": int,
}

# server 节的合法键 -> 期望类型
SERVER_KEYS = {
    "host": str,
    "port": int,
    "served_model_name": str,
    "gpu_memory_utilization": (int, float),
    "max_model_len": int,
    "env": dict,
    "extra_flags": str,
}

TOP_KEYS = {"desc", "model", "server", "client"}


def load_models():
    """返回 {"models": {别名: {"path","note"}}, "aliases": {短名: 别名}}。"""
    d = json.loads(MODELS_JSON.read_text())
    return {"models": d["models"], "aliases": d.get("aliases", {})}


def list_presets():
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def _check_node(name, node, keys, errs):
    for k, v in node.items():
        if k not in keys:
            errs.append(f"{name} 节有未知键 {k!r}(合法键: {sorted(keys)})")
        elif v is not None and not isinstance(v, keys[k]):
            errs.append(f"{name}.{k} 类型不对: {type(v).__name__}({v!r})")
    if name == "server" and node.get("env") is not None:
        for ek, ev in node["env"].items():
            if not isinstance(ek, str) or not isinstance(ev, str):
                errs.append(f"server.env 的键值都必须是字符串: {ek!r}={ev!r}")


def validate(preset, models=None):
    """返回问题清单(空 = 合格)。models 不传就现读 models.json。"""
    errs = []
    unknown = set(preset) - TOP_KEYS
    if unknown:
        errs.append(f"顶层有未知键 {sorted(unknown)}(合法键: {sorted(TOP_KEYS)})")
    if "model" not in preset:
        errs.append("缺顶层 model(models.json 里的别名)")
    else:
        m = models or load_models()
        key = m["aliases"].get(preset["model"], preset["model"])
        if key not in m["models"]:
            errs.append(f"model 别名 {preset['model']!r} 不在 models.json 里")
    if "client" in preset:
        _check_node("client", preset["client"], CLIENT_KEYS, errs)
    if "server" in preset:
        _check_node("server", preset["server"], SERVER_KEYS, errs)
        for need in ("host", "port", "served_model_name"):
            if preset["server"].get(need) is None:
                errs.append(f"server 节缺 {need}(发射器拼不出命令)")
    return errs


def load_preset(name):
    """按名字读一份预设并校验;名字就是 configs/presets/ 下的文件名去掉 .json。"""
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"预设 {name!r} 不存在;现有预设: {list_presets()}")
    preset = json.loads(path.read_text())
    errs = validate(preset)
    if errs:
        raise ValueError(f"预设 {name} 不合格:\n" + "\n".join(errs))
    preset["_name"] = name
    preset["_path"] = str(path)
    return preset


def merge_client(cli, client_node, fallbacks):
    """逐键合并:CLI 显式值(非 None) > 预设值(非 null) > fallbacks 里的原缺省。
    三处都没有的键落 None。只处理 cli 与 fallbacks 里出现过的键——
    预设里多出来的键(比如采集器用不上的 stop)不会被硬塞给调用方。
    """
    node = client_node or {}
    out = {}
    for k in set(cli) | set(fallbacks):
        if cli.get(k) is not None:
            out[k] = cli[k]
        elif node.get(k) is not None:
            out[k] = node[k]
        else:
            out[k] = fallbacks.get(k)
    return out


def base_url_of(preset):
    """server 节拼 /v1 端点;没有 server 节返回 None。"""
    srv = preset.get("server")
    if not srv:
        return None
    return f"http://{srv['host']}:{srv['port']}/v1"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(load_preset(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        for n in list_presets():
            print(f"{n:24s} {json.loads((PRESET_DIR / (n + '.json')).read_text()).get('desc', '')}")
