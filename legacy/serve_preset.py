"""General-purpose vLLM launcher: reads the server section of configs/presets/<name>.json and
starts one service.

Structurally the same as the handwritten envs/serve_logs/launch_vllm_*.py (ssh + tmux + tee
logging); the difference is the model path is resolved via model_registry.resolve(), and the
startup args and environment variables all come from the preset file. At launch time the full
preset is copied into the log directory (<session>.preset.json), so checking "what were this
service's settings at the time" later does not require digging through shell history.

Usage (the launch itself goes through the gpu-run skill; this only assembles the command and
starts tmux):
  python3 serve_preset.py --preset default --gpu 5
  python3 serve_preset.py --preset default --gpu 5 --dry-run
The GPU card number is deliberately kept out of the preset: picking a card is decided at launch
time by a live check of free cards, following gpu-run.
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
    """preset + overrides -> (host, session, the full ssh command, the service command string)."""
    srv = preset.get("server")
    if not srv:
        raise SystemExit(f"preset {preset['_name']} has no server section, cannot launch; "
                         "only a preset with a server section can start a service")
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
                    help="file name under configs/presets/ (without .json)")
    ap.add_argument("--gpu", required=True, help="value of CUDA_VISIBLE_DEVICES")
    ap.add_argument("--host", default=None, help="override the preset's server.host")
    ap.add_argument("--port", type=int, default=None, help="override the preset's server.port")
    ap.add_argument("--session", default=None,
                    help="tmux session name, default new1_vllm_<host>_<preset name>")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the ssh+tmux command only, do not execute or copy the preset")
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
