"""通用 vLLM 发射器:读 configs/presets/<名>.json 的 server 节起一个服务。

与手写的 envs/serve_logs/launch_vllm_*.py 同构(ssh + tmux + tee 日志),
区别是模型路径经 model_registry.resolve() 解析、启动参数和环境变量全部
来自预设文件,发射时把预设全文抄一份到日志目录(<session>.preset.json),
回头查"这台服务当时是什么设置"不用翻 shell 历史。

用法(发射本身走 gpu-run skill,这里只拼命令和起 tmux):
  python3 serve_preset.py --preset default --gpu 5
  python3 serve_preset.py --preset default --gpu 5 --dry-run
GPU 卡号故意不进预设:挑卡是发射时按实探空卡定的,跟着 gpu-run 走。
"""

import argparse
import json
import shlex
import shutil
import subprocess
from pathlib import Path

from model_registry import resolve
from preset_loader import load_preset

WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"


def build(preset, gpu, host=None, port=None, session=None):
    """预设 + 覆盖项 -> (host, session, ssh 整条命令, 服务命令串)。"""
    srv = preset.get("server")
    if not srv:
        raise SystemExit(f"预设 {preset['_name']} 没有 server 节,发射不了;"
                         "带 server 节的预设才能起服务")
    host = host or srv["host"]
    port = port or srv["port"]
    session = session or f"new1_vllm_{host}_{preset['_name']}"
    cmd = (f"{VLLM} serve {resolve(preset['model'])} "
           f"--served-model-name {srv['served_model_name']} "
           f"--port {port} --host 0.0.0.0 "
           f"--gpu-memory-utilization {srv['gpu_memory_utilization']}")
    if srv.get("max_model_len"):
        cmd += f" --max-model-len {srv['max_model_len']}"
    if srv.get("extra_flags"):
        cmd += f" {srv['extra_flags']}"
    envs = dict(srv.get("env") or {})
    envs["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    envs["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env_str = " ".join(f"{k}={v}" for k, v in envs.items())
    log = f"{WORKDIR}/{session}.log"
    inner = f"cd {WORKDIR} && {env_str} {cmd} 2>&1 | tee {log}"
    tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
    return host, session, tmux, cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preset", required=True,
                    help="configs/presets/ 下的文件名(不带 .json)")
    ap.add_argument("--gpu", required=True, help="CUDA_VISIBLE_DEVICES 的值")
    ap.add_argument("--host", default=None, help="覆盖预设 server.host")
    ap.add_argument("--port", type=int, default=None, help="覆盖预设 server.port")
    ap.add_argument("--session", default=None,
                    help="tmux 会话名,缺省 new1_vllm_<host>_<预设名>")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印 ssh+tmux 命令,不执行、不抄预设")
    a = ap.parse_args()

    preset = load_preset(a.preset)
    host, session, tmux, _ = build(preset, a.gpu, a.host, a.port, a.session)
    if a.dry_run:
        print(f"ssh -n {host} {shlex.quote(tmux)}")
        return
    shutil.copy(preset["_path"], f"{WORKDIR}/{session}.preset.json")
    subprocess.run(["ssh", "-n", host, tmux], check=True)
    print("launched", session, "on", host,
          "-> log:", f"{WORKDIR}/{session}.log",
          "preset:", f"{WORKDIR}/{session}.preset.json")


if __name__ == "__main__":
    main()
