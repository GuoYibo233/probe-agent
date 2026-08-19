"""采集批次的发射清单生成器(施工规格书 §7)。

吃一份 manifest json(服务表 + 分片表),吐三个文件到 `envs/runs/<run_id>/`:

  launch_servers.py   照 envs/serve_logs/launch_vllm_topup.py 的模板:
                      ssh + tmux 起 vLLM,环境变量三件套一字不差
                      (LD_LIBRARY_PATH / VLLM_USE_FLASHINFER_SAMPLER=0 /
                       CUDA_DEVICE_ORDER=PCI_BUS_ID)
  launch_clients.sh   照 envs/runs/full_v2_topup/launch_clients.sh 的 tm()/aw() 结构
  MANIFEST.md         人读的服务表 + 分片表

本脚本**只生成不执行**:不 ssh、不 tmux、不碰显卡。真正发射由 gpu-run 流程按
执行手册 §3 走。模型权重路径与旗标是查表写死的(表见执行手册 §3.2)。

manifest schema(见 pipeline/collect/manifest_w0.json):
  run_id      str
  servers[]   {host, gpu, model_key, port, session, extra_flags, card?}
  clients[]   {tag, model_key, split, num_shards, shard_ports[], outdir, exp}
              shard_ports[k] = 第 k 个分片打哪个端口(长度必须 == num_shards)
  可选:env(采集环境,appworld|alfworld,默认 appworld;决定采集器/venv/步数上限
        与 outdir 前缀)、envs_root(默认 /home/y-guo/reproduce/new1/envs)、
        client_session_prefix(默认由 run_id 前两段拼出,w0_aw_official -> new1_w0aw)

用法:
  # 正式生成(写 envs/runs/<run_id>/,已存在同名文件时拒绝覆盖,除非 --force)
  python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_w0.json
  # 试生成(只写别处,绝不碰 envs/)
  python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_w0.json \
      --dry-run --out-override /tmp/genlaunch_test/
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ----------------------------------------------------------------- 查表(写死)

REPO = "/home/y-guo/reproduce/new1"
ENVS_ROOT = f"{REPO}/envs"
SERVE_LOG_DIR = f"{REPO}/envs/serve_logs"
VLLM_BIN = f"{REPO}/envs/vllm-env/bin/vllm"
ZMODELS = "/net/tokyo100-10g/data/str01_01/zhou-y/models"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

# 执行手册 §3.2 的模型表:权重目录 / served-model-name / 旗标家族
MODEL_TABLE = {
    "q35": dict(served="qwen3.5-27b", const="ZMODELS", weights="Qwen3.5-27B",
                family="qwen"),
    "q36": dict(served="qwen3.6-27b", const="ZMODELS", weights="Qwen3.6-27B",
                family="qwen"),
    "gptoss": dict(served="gpt-oss-120b", const="YMODELS",
                   weights="gpt-oss-120b", family="gptoss"),
}

# Qwen 通用旗标(生成文件里以 QWEN_FLAGS 常量出现,与模板一字不差)
QWEN_FLAGS_SRC = ('    "--reasoning-parser deepseek_r1 --max-model-len 65536 "\n'
                  '    "--gpu-memory-utilization 0.92 "\n'
                  '    "--enable-auto-tool-choice --tool-call-parser qwen3_coder"\n')
# gpt-oss 不带 Qwen 旗标,只要显存占比
GPTOSS_SERVE_FLAGS = "--gpu-memory-utilization 0.92"
# gpt-oss 客户端追加旗标。2026-08-20 起走预设文件,gptoss_chat_high 展开后
# 与旧串 "--api chat --reasoning-effort high" 逐项等价(tests/test_preset.py 钉着)
GPTOSS_CLIENT_EXTRA = "--preset gptoss_chat_high"

# 采集器统一参数(执行手册 §3.4)
CLIENT_COMMON = "--n 0 --max-steps 30"

# 环境表:manifest 顶层可选字段 "env" 选一行,缺省 appworld(老 manifest 行为不变)。
# 每行说明该环境用哪个 venv、哪个采集器、生成的 shell 函数叫什么、统一参数是什么。
ENV_TABLE = {
    "appworld": dict(venv="appworld", runner="run_appworld.py", fn="aw",
                     common=CLIENT_COMMON),
    "alfworld": dict(venv="alfworld", runner="run_alfworld.py", fn="alf",
                     common="--n 0 --max-steps 50"),
}
DEFAULT_ENV = "appworld"

REPLICA_LETTERS = "ABCDEFGH"


def die(msg):
    print(f"gen_launch: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


# ----------------------------------------------------------------- manifest

def load_manifest(path):
    cfg = json.loads(Path(path).read_text())
    for key in ("run_id", "servers", "clients"):
        if key not in cfg:
            die(f"manifest 缺字段 {key}")
    run_id = cfg["run_id"]
    warns = []

    env = cfg.get("env", DEFAULT_ENV)
    if env not in ENV_TABLE:
        die(f"未知 env {env}(表里只有 {sorted(ENV_TABLE)})")
    cfg["env"] = env

    hosts = {s["host"] for s in cfg["servers"]}
    if len(hosts) != 1:
        die("所有服务实例必须在同一台机器上(模板里 HOST 是单个常量);"
            f"本 manifest 出现 {sorted(hosts)}。要跨机请先改模板结构。")

    seen_port, seen_sess, seen_gpu = {}, set(), set()
    for s in cfg["servers"]:
        if s["model_key"] not in MODEL_TABLE:
            die(f"未知 model_key {s['model_key']}(表里只有 {sorted(MODEL_TABLE)})")
        if s["port"] in seen_port:
            die(f"端口 {s['port']} 被两个实例复用")
        seen_port[s["port"]] = s
        if s["session"] in seen_sess:
            die(f"session 名重复:{s['session']}")
        seen_sess.add(s["session"])
        if (s["host"], s["gpu"]) in seen_gpu:
            die(f"同一张卡被排了两次:{s['host']} GPU {s['gpu']}")
        seen_gpu.add((s["host"], s["gpu"]))

    for c in cfg["clients"]:
        if c["model_key"] not in MODEL_TABLE:
            die(f"未知 model_key {c['model_key']}")
        if len(c["shard_ports"]) != c["num_shards"]:
            die(f"分片 {c['tag']}: shard_ports 长度 {len(c['shard_ports'])} "
                f"!= num_shards {c['num_shards']}")
        for p in c["shard_ports"]:
            if p not in seen_port:
                die(f"分片 {c['tag']} 指向端口 {p},但服务表里没有这个端口")
            if seen_port[p]["model_key"] != c["model_key"]:
                die(f"分片 {c['tag']}(model={c['model_key']})指向端口 {p},"
                    f"那是 {seen_port[p]['model_key']} 的实例")
        # outdir 强制标准名:下游事件抽取按目录名尾巴认模型,别的名字会被静默跳过
        std = f"{env}_{c['model_key']}"
        if c.get("outdir") and c["outdir"] != std:
            warns.append(f"分片 {c['tag']} 的 outdir {c['outdir']!r} 不是标准名,"
                         f"已强制改为 {std!r}")
        c["outdir"] = std

    cfg["envs_root"] = cfg.get("envs_root", ENVS_ROOT)
    if "client_session_prefix" not in cfg:
        parts = run_id.split("_")
        tail = "".join(parts[:2]) if len(parts) >= 2 else run_id
        cfg["client_session_prefix"] = f"new1_{tail}"
    return cfg, warns


def replica_map(servers):
    """同一模型的第几个副本 -> A/B/C…(只用于注释和 MANIFEST)。"""
    seen, out = {}, {}
    for s in servers:
        k = s["model_key"]
        i = seen.get(k, 0)
        seen[k] = i + 1
        out[s["session"]] = REPLICA_LETTERS[i] if i < len(REPLICA_LETTERS) else str(i)
    return out


# ----------------------------------------------------------------- 服务端

SERVER_MAIN = '''


def main() -> None:
    for gpu, session, cmd in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{WORKDIR}/{session}.log"
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print("launched", session, "gpu", gpu, "-> log:", log)


if __name__ == "__main__":
    main()
'''


def serve_flags(server):
    """该实例的完整旗标串(生成文件里的 f-string 片段)。"""
    fam = MODEL_TABLE[server["model_key"]]["family"]
    base = "{QWEN_FLAGS}" if fam == "qwen" else GPTOSS_SERVE_FLAGS
    extra = (server.get("extra_flags") or "").strip()
    return f"{base} {extra}".strip() if extra else base


def gen_servers(cfg):
    host = cfg["servers"][0]["host"]
    rep = replica_map(cfg["servers"])
    n_models = len({s["model_key"] for s in cfg["servers"]})
    lines = [f'"""{cfg["run_id"]} 采集批次的服务发射器:{n_models} 模型 '
             f'{len(cfg["servers"])} 实例,占 {host} {len(cfg["servers"])} 卡'
             f'(gen_launch.py 生成,勿手改)。',
             ""]
    for s in cfg["servers"]:
        m = MODEL_TABLE[s["model_key"]]
        card = s.get("card", "GPU")
        note = (s.get("extra_flags") or "").strip()
        note = f", {note}" if note else ""
        lines.append(f'  {m["served"]:<13s} -> {card} GPU {s["gpu"]}, '
                     f'port {s["port"]}   (副本 {rep[s["session"]]}{note})')
    lines += ["",
              "坑:H100(95G)上跑 Qwen 必须 --max-num-seqs 512"
              "(Mamba cache 只够 612 块,默认 1024 会崩)。",
              f"用法: python3 {Path('launch_servers.py').name}",
              '"""',
              "import shlex",
              "import subprocess",
              "",
              f'HOST = "{host}"',
              f'WORKDIR = "{SERVE_LOG_DIR}"',
              f'VLLM = "{VLLM_BIN}"',
              f'ZMODELS = "{ZMODELS}"',
              f'YMODELS = "{YMODELS}"',
              "",
              "QWEN_FLAGS = (",
              QWEN_FLAGS_SRC.rstrip("\n"),
              ")",
              "",
              "JOBS = ["]
    for s in cfg["servers"]:
        m = MODEL_TABLE[s["model_key"]]
        lines.append(f'    ({s["gpu"]}, "{s["session"]}",')
        lines.append(f'     f"{{VLLM}} serve {{{m["const"]}}}/{m["weights"]} '
                     f'--served-model-name {m["served"]} "')
        lines.append(f'     f"--port {s["port"]} --host 0.0.0.0 {serve_flags(s)}"),')
    lines.append("]")
    return "\n".join(lines) + SERVER_MAIN


# ----------------------------------------------------------------- 客户端

CLIENT_TM = '''tm() { # session cmd
  tmux has-session -t "$1" 2>/dev/null && { echo "SKIP $1"; return; }
  tmux new-session -d -s "$1" "$2 2>&1 | tee $F/logs/$1.log"
  echo "launched $1"
}
'''


def gen_clients(cfg):
    e = ENV_TABLE[cfg["env"]]
    prefix = cfg["client_session_prefix"]
    port2host = {s["port"]: s["host"] for s in cfg["servers"]}
    by_model = {}
    for c in cfg["clients"]:
        by_model.setdefault(c["model_key"], []).append(c)

    out = ["#!/bin/bash",
           f"# {cfg['run_id']} 客户端发射器(gen_launch.py 生成,勿手改)。"
           "幂等:--resume 自动跳过已完成题。"]
    for key, cs in by_model.items():
        m = MODEL_TABLE[key]
        ports = sorted({p for c in cs for p in c["shard_ports"]})
        desc = ", ".join(f"{c['split']} {c['num_shards']} 分片" for c in cs)
        out.append(f"# {m['served']}({'/'.join(str(p) for p in ports)}): {desc}")
    out += ["# 每个分片一个本机 tmux session,日志在 logs/。",
            f"E={cfg['envs_root']}",
            f"F=$E/runs/{cfg['run_id']}",
            "mkdir -p $F/logs",
            f'GPTOSS_EXTRA="{GPTOSS_CLIENT_EXTRA}"',
            "",
            CLIENT_TM,
            f"{e['fn']}() {{ # tag model url extra split num_shards shard_id "
            "exp outdir_tag",
            f'  tm "{prefix}_$1_s$7" \\',
            f'    "$E/{e["venv"]}/venv/bin/python $E/collect/{e["runner"]} \\',
            f'      --base-url $3 --model $2 --split $5 {e["common"]} $4 \\',
            f'      --outdir $F/{cfg["env"]}_$9 --exp $8 --num-shards $6 '
            '--shard-id $7 \\',
            '      --resume"',
            "}",
            ""]
    for c in cfg["clients"]:
        m = MODEL_TABLE[c["model_key"]]
        extra = '"$GPTOSS_EXTRA"' if m["family"] == "gptoss" else '""'
        out.append(f"# ---- {m['served']}: {c['split']} {c['num_shards']} 分片 ----")
        for sid, port in enumerate(c["shard_ports"]):
            url = f"http://{port2host[port]}:{port}/v1"
            out.append(f"{e['fn']} {c['tag']} {m['served']} {url} {extra} "
                       f"{c['split']} "
                       f"{c['num_shards']} {sid} {c['exp']} {c['model_key']}")
        out.append("")
    out += ['echo "---- sessions ----"',
            f"tmux ls | grep {prefix} | wc -l"]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- MANIFEST.md

def gen_manifest_md(cfg):
    e = ENV_TABLE[cfg["env"]]
    rep = replica_map(cfg["servers"])
    port2host = {s["port"]: s["host"] for s in cfg["servers"]}
    prefix = cfg["client_session_prefix"]
    n_shards = sum(c["num_shards"] for c in cfg["clients"])
    L = [f"# 发射清单 — {cfg['run_id']}", "",
         f"gen_launch.py 生成(勿手改)。服务 {len(cfg['servers'])} 实例 / "
         f"客户端 {n_shards} 分片。", "",
         "## 服务表", "",
         "| host | GPU idx | 卡 | 模型 | served-model-name | 端口 | 追加旗标 | session | 日志 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for s in cfg["servers"]:
        m = MODEL_TABLE[s["model_key"]]
        extra = (s.get("extra_flags") or "").strip() or "—"
        L.append(f"| {s['host']} | {s['gpu']} | {s.get('card', '—')} | "
                 f"{s['model_key']}(副本 {rep[s['session']]}) | {m['served']} | "
                 f"{s['port']} | {extra} | `{s['session']}` | "
                 f"`{SERVE_LOG_DIR}/{s['session']}.log` |")
    L += ["",
          "Qwen 通用旗标:`--reasoning-parser deepseek_r1 --max-model-len 65536 "
          "--gpu-memory-utilization 0.92 --enable-auto-tool-choice "
          "--tool-call-parser qwen3_coder`;",
          f"gpt-oss 不带 Qwen 旗标,只要 `{GPTOSS_SERVE_FLAGS}`。", "",
          "## 分片表", "",
          "| tag | 模型 | split | num-shards | shard-id → 端口 | outdir | exp | session |",
          "|---|---|---|---|---|---|---|---|"]
    for c in cfg["clients"]:
        m = MODEL_TABLE[c["model_key"]]
        mapping = ", ".join(f"s{i}→{p}" for i, p in enumerate(c["shard_ports"]))
        L.append(f"| {c['tag']} | {m['served']} | {c['split']} | {c['num_shards']} | "
                 f"{mapping} | `$F/{c['outdir']}` | {c['exp']} | "
                 f"`{prefix}_{c['tag']}_s<k>` |")
    L += ["",
          f"`$F` = `{cfg['envs_root']}/runs/{cfg['run_id']}`,日志 `$F/logs/<session>.log`。",
          f"客户端统一参数 `{e['common']} --resume`;"
          f"gpt-oss 分片额外 `{GPTOSS_CLIENT_EXTRA}`。",
          f"outdir 一律 `{cfg['env']}_<model_key>` 标准名"
          "(下游事件抽取按目录名尾巴认模型)。",
          "", "## 发射顺序", "",
          "1. `python3 launch_servers.py`(六实例起齐,日志出现 "
          "\"Application startup complete\" 且 `curl -s http://<host>:<port>/v1/models` 有返回)",
          "2. smoke:每模型 1 题(执行手册 §3.3)",
          "3. `bash launch_clients.sh`",
          "4. 双登记:`ops/gpu_jobs.py register` + `ops/record.py start`",
          ""]
    return "\n".join(L)


# ----------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="manifest json")
    ap.add_argument("--dry-run", action="store_true",
                    help="试生成:只写 --out-override 指定的目录,绝不碰 envs/")
    ap.add_argument("--out-override", default=None,
                    help="改写到别的目录(--dry-run 时必填)")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖目标目录里已有的同名文件")
    args = ap.parse_args()

    cfg, warns = load_manifest(args.config)
    for w in warns:
        print("gen_launch: WARN:", w)

    if args.dry_run and not args.out_override:
        die("--dry-run 必须配 --out-override(防止误写现役采集目录)")
    outdir = Path(args.out_override) if args.out_override else \
        Path(cfg["envs_root"]) / "runs" / cfg["run_id"]
    outdir.mkdir(parents=True, exist_ok=True)

    files = {"launch_servers.py": gen_servers(cfg),
             "launch_clients.sh": gen_clients(cfg),
             "MANIFEST.md": gen_manifest_md(cfg)}
    exist = [n for n in files if (outdir / n).exists()]
    if exist and not args.force:
        die(f"{outdir} 下已有 {exist},拒绝覆盖(要覆盖加 --force)")

    for name, text in files.items():
        p = outdir / name
        p.write_text(text)
        if name.endswith(".sh"):
            os.chmod(p, 0o775)
        print("wrote", p)
    print(f"gen_launch: {len(cfg['servers'])} 服务实例 / "
          f"{sum(c['num_shards'] for c in cfg['clients'])} 分片"
          f"{' (dry-run)' if args.dry_run else ''};只生成不执行。")


if __name__ == "__main__":
    main()
