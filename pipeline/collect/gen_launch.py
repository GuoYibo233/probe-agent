"""Launch manifest generator for a collection batch (construction spec §7).

Consumes one manifest json (server table + piece table), and spits out three
files into `envs/runs/<run_id>/`:

  launch_servers.py   follows the template in envs/serve_logs/launch_vllm_topup.py:
                       ssh + tmux to start vLLM, with the three environment
                       variables matching exactly
                       (LD_LIBRARY_PATH / VLLM_USE_FLASHINFER_SAMPLER=0 /
                        CUDA_DEVICE_ORDER=PCI_BUS_ID)
  launch_clients.sh   follows the tm()/aw() structure of
                       envs/runs/full_v2_topup/launch_clients.sh
  MANIFEST.md         human-readable server table + piece table

This script **only generates, never executes**: no ssh, no tmux, does not touch
any GPU. The actual launch goes through the gpu-run flow per the runbook §3.
Model weight paths and flags are looked up from a fixed table (see runbook
§3.2).

manifest schema (see pipeline/collect/manifest_w0.json):
  run_id      str
  servers[]   {host, gpu, model_key, port, session, extra_flags, card?}
  clients[]   {tag, model_key, split, num_shards, shard_ports[], outdir, exp}
              shard_ports[k] = which port the k-th piece hits (length must == num_shards)
  Optional: env (collection environment, appworld|alfworld, default appworld;
        determines the collector/venv/step cap and the outdir prefix),
        envs_root (default /home/y-guo/reproduce/new1/envs),
        client_session_prefix (default built from run_id's first two segments,
        w0_aw_official -> new1_w0aw),
        traj_per_task + seed_family (how many trajectories per item + the
        per-item seed table; give both or neither, lengths must match; not
        given = one trajectory per item, and the output is byte-identical to
        before these two fields were added)

Usage:
  # real generation (writes envs/runs/<run_id>/; refuses to overwrite an
  # existing file of the same name unless --force)
  python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_w0.json
  # dry generation (writes only elsewhere, never touches envs/)
  python3 pipeline/collect/gen_launch.py --config pipeline/collect/manifest_w0.json \
      --dry-run --out-override /tmp/genlaunch_test/
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ----------------------------------------------------------------- lookup table (fixed)

REPO = "/home/y-guo/reproduce/new1"
ENVS_ROOT = f"{REPO}/envs"
SERVE_LOG_DIR = f"{REPO}/envs/serve_logs"
VLLM_BIN = f"{REPO}/envs/vllm-env/bin/vllm"
ZMODELS = "/net/tokyo100-10g/data/str01_01/zhou-y/models"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

# Runbook §3.2's model table: weights directory / served-model-name / flag family
MODEL_TABLE = {
    "q35": dict(served="qwen3.5-27b", const="ZMODELS", weights="Qwen3.5-27B",
                family="qwen"),
    "q36": dict(served="qwen3.6-27b", const="ZMODELS", weights="Qwen3.6-27B",
                family="qwen"),
    "gptoss": dict(served="gpt-oss-120b", const="YMODELS",
                   weights="gpt-oss-120b", family="gptoss"),
}

# Qwen common flags (appears in the generated file as the QWEN_FLAGS constant, matching the template exactly)
QWEN_FLAGS_SRC = ('    "--reasoning-parser deepseek_r1 --max-model-len 65536 "\n'
                  '    "--gpu-memory-utilization 0.92 "\n'
                  '    "--enable-auto-tool-choice --tool-call-parser qwen3_coder"\n')
# gpt-oss carries no Qwen flags, only the GPU memory fraction
GPTOSS_SERVE_FLAGS = "--gpu-memory-utilization 0.92"
# gpt-oss client appends flags: one --preset carries the whole generation setting
# (configs/presets/<name>.json). The preset name comes from the manifest's top-level
# optional field "gptoss_client_preset"; when the field is absent, use the default
# below, which is the one setting currently active project-wide (harmony / effort
# high / temperature 1.0 / top_p 1.0 / max_tokens 8192 / Current date 2026-08-06);
# tests/test_preset.py pins this down.
GPTOSS_CLIENT_PRESET_DEFAULT = "default"

# Collector's uniform parameters (runbook §3.4)
CLIENT_COMMON = "--n 0 --max-steps 30"

# Environment table: the manifest's top-level optional field "env" selects one row, default appworld (old manifest behavior unchanged).
# Each row states which venv that environment uses, which collector, what the generated shell function is called, and what the uniform parameters are.
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


def is_int(v):
    """true in json is bool, and bool is a subclass of int -- validating integer fields must exclude it."""
    return isinstance(v, int) and not isinstance(v, bool)


# ----------------------------------------------------------------- manifest

def load_manifest(path):
    cfg = json.loads(Path(path).read_text())
    for key in ("run_id", "servers", "clients"):
        if key not in cfg:
            die(f"manifest missing field {key}")
    run_id = cfg["run_id"]
    warns = []

    env = cfg.get("env", DEFAULT_ENV)
    if env not in ENV_TABLE:
        die(f"unknown env {env}(the table only has {sorted(ENV_TABLE)})")
    cfg["env"] = env

    preset = cfg.get("gptoss_client_preset", GPTOSS_CLIENT_PRESET_DEFAULT)
    pf = Path(REPO) / "configs" / "presets" / f"{preset}.json"
    if not pf.exists():
        die(f"gptoss_client_preset {preset!r} has no matching preset file:{pf}")
    cfg["gptoss_client_preset"] = preset

    # Multi-sample rule (since 2026-08-21, np821): the two fields only count if they
    # appear as a pair; giving neither means the old rule of one trajectory per item.
    # Validation runs before generation, so unpaired fields never get spliced into the launch script.
    n_traj, family = cfg.get("traj_per_task"), cfg.get("seed_family")
    if (n_traj is None) != (family is None):
        die("traj_per_task and seed_family must both be given or both omitted"
            f"(currently traj_per_task={n_traj!r} / seed_family={family!r})")
    if n_traj is not None:
        if not is_int(n_traj) or n_traj < 1:
            die(f"traj_per_task must be an integer >= 1, currently {n_traj!r}")
        if not isinstance(family, list) or not family or \
                not all(is_int(s) for s in family):
            die(f"seed_family must be a non-empty list of integers, currently {family!r}")
        if len(family) != n_traj:
            die(f"seed_family has {len(family)} seeds, which does not match traj_per_task "
                f"{n_traj}")
        if env != "appworld":
            die(f"traj_per_task/seed_family are currently only recognized by the appworld collector"
                f"(run_appworld.py's --traj-per-task/--seeds); this manifest "
                f"env is {env}")

    hosts = {s["host"] for s in cfg["servers"]}
    if len(hosts) != 1:
        die("all service instances must be on the same machine (HOST is a single constant in the template);"
            f"this manifest has {sorted(hosts)}. To go cross-machine, change the template structure first.")

    seen_port, seen_sess, seen_gpu = {}, set(), set()
    for s in cfg["servers"]:
        if s["model_key"] not in MODEL_TABLE:
            die(f"unknown model_key {s['model_key']}(the table only has {sorted(MODEL_TABLE)})")
        if s["port"] in seen_port:
            die(f"port {s['port']} is reused by two instances")
        seen_port[s["port"]] = s
        if s["session"] in seen_sess:
            die(f"duplicate session name:{s['session']}")
        seen_sess.add(s["session"])
        if (s["host"], s["gpu"]) in seen_gpu:
            die(f"the same card was scheduled twice:{s['host']} GPU {s['gpu']}")
        seen_gpu.add((s["host"], s["gpu"]))

    for c in cfg["clients"]:
        if c["model_key"] not in MODEL_TABLE:
            die(f"unknown model_key {c['model_key']}")
        if len(c["shard_ports"]) != c["num_shards"]:
            die(f"piece {c['tag']}: shard_ports length {len(c['shard_ports'])} "
                f"!= num_shards {c['num_shards']}")
        for p in c["shard_ports"]:
            if p not in seen_port:
                die(f"piece {c['tag']} points to port {p}, but the service table has no such port")
            if seen_port[p]["model_key"] != c["model_key"]:
                die(f"piece {c['tag']}(model={c['model_key']}) points to port {p},"
                    f"which is an instance of {seen_port[p]['model_key']}")
        # outdir is forced to a standard name: downstream event extraction identifies the model by the directory-name suffix, any other name gets silently skipped
        std = f"{env}_{c['model_key']}"
        if c.get("outdir") and c["outdir"] != std:
            warns.append(f"piece {c['tag']}'s outdir {c['outdir']!r} is not the standard name,"
                         f"forced to {std!r}")
        c["outdir"] = std

    cfg["envs_root"] = cfg.get("envs_root", ENVS_ROOT)
    if "client_session_prefix" not in cfg:
        parts = run_id.split("_")
        tail = "".join(parts[:2]) if len(parts) >= 2 else run_id
        cfg["client_session_prefix"] = f"new1_{tail}"
    return cfg, warns


def multi_flags(cfg):
    """Flag string appended to the collector for multi-sample collection; when the manifest
    doesn't set those two fields it is an empty string, and the caller uses this to emit
    the old-rule output unchanged."""
    n_traj = cfg.get("traj_per_task")
    if n_traj is None:
        return ""
    return (f"--traj-per-task {n_traj} "
            f"--seeds {','.join(str(s) for s in cfg['seed_family'])}")


def replica_map(servers):
    """Which replica number of the same model -> A/B/C... (used only for comments and MANIFEST)."""
    seen, out = {}, {}
    for s in servers:
        k = s["model_key"]
        i = seen.get(k, 0)
        seen[k] = i + 1
        out[s["session"]] = REPLICA_LETTERS[i] if i < len(REPLICA_LETTERS) else str(i)
    return out


# ----------------------------------------------------------------- server side

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
    """The full flag string for this instance (an f-string fragment in the generated file)."""
    fam = MODEL_TABLE[server["model_key"]]["family"]
    base = "{QWEN_FLAGS}" if fam == "qwen" else GPTOSS_SERVE_FLAGS
    extra = (server.get("extra_flags") or "").strip()
    return f"{base} {extra}".strip() if extra else base


def gen_servers(cfg):
    host = cfg["servers"][0]["host"]
    rep = replica_map(cfg["servers"])
    n_models = len({s["model_key"] for s in cfg["servers"]})
    lines = [f'"""{cfg["run_id"]} collection batch service launcher: {n_models} models '
             f'{len(cfg["servers"])} instances, occupying {host} {len(cfg["servers"])} cards'
             f'(generated by gen_launch.py, do not hand-edit).',
             ""]
    for s in cfg["servers"]:
        m = MODEL_TABLE[s["model_key"]]
        card = s.get("card", "GPU")
        note = (s.get("extra_flags") or "").strip()
        note = f", {note}" if note else ""
        lines.append(f'  {m["served"]:<13s} -> {card} GPU {s["gpu"]}, '
                     f'port {s["port"]}   (replica {rep[s["session"]]}{note})')
    lines += ["",
              "gotcha: running Qwen on H100(95G) requires --max-num-seqs 512"
              "(the Mamba cache only holds 612 blocks; the default 1024 will crash).",
              f"usage: python3 {Path('launch_servers.py').name}",
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


# ----------------------------------------------------------------- client side

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
           f"# {cfg['run_id']} client launcher(generated by gen_launch.py, do not hand-edit)."
           "Idempotent: --resume automatically skips completed tasks."]
    for key, cs in by_model.items():
        m = MODEL_TABLE[key]
        ports = sorted({p for c in cs for p in c["shard_ports"]})
        desc = ", ".join(f"{c['split']} {c['num_shards']} pieces" for c in cs)
        out.append(f"# {m['served']}({'/'.join(str(p) for p in ports)}): {desc}")
    multi = multi_flags(cfg)
    out += ["# each piece is one local tmux session; logs are in logs/.",
            f"E={cfg['envs_root']}",
            f"F=$E/runs/{cfg['run_id']}",
            "mkdir -p $F/logs",
            f'GPTOSS_EXTRA="--preset {cfg["gptoss_client_preset"]}"']
    if multi:   # multiple trajectories per item: treats every piece of the environment the same way, so it lives inside the function body
        out.append(f'MULTI="{multi}"')
    out += ["",
            CLIENT_TM,
            f"{e['fn']}() {{ # tag model url extra split num_shards shard_id "
            "exp outdir_tag",
            f'  tm "{prefix}_$1_s$7" \\',
            f'    "$E/{e["venv"]}/venv/bin/python $E/collect/{e["runner"]} \\',
            f'      --base-url $3 --model $2 --split $5 {e["common"]} $4 \\',
            f'      --outdir $F/{cfg["env"]}_$9 --exp $8 --num-shards $6 '
            '--shard-id $7 \\',
            f'      --resume{" $MULTI" if multi else ""}"',
            "}",
            ""]
    for c in cfg["clients"]:
        m = MODEL_TABLE[c["model_key"]]
        extra = '"$GPTOSS_EXTRA"' if m["family"] == "gptoss" else '""'
        out.append(f"# ---- {m['served']}: {c['split']} {c['num_shards']} pieces ----")
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
    multi = multi_flags(cfg)
    n_shards = sum(c["num_shards"] for c in cfg["clients"])
    L = [f"# Launch manifest — {cfg['run_id']}", "",
         f"generated by gen_launch.py(do not hand-edit). {len(cfg['servers'])} service instances / "
         f"{n_shards} client pieces.", "",
         "## Service table", "",
         "| host | GPU idx | card | model | served-model-name | port | extra flags | session | log |",
         "|---|---|---|---|---|---|---|---|---|"]
    for s in cfg["servers"]:
        m = MODEL_TABLE[s["model_key"]]
        extra = (s.get("extra_flags") or "").strip() or "—"
        L.append(f"| {s['host']} | {s['gpu']} | {s.get('card', '—')} | "
                 f"{s['model_key']}(replica {rep[s['session']]}) | {m['served']} | "
                 f"{s['port']} | {extra} | `{s['session']}` | "
                 f"`{SERVE_LOG_DIR}/{s['session']}.log` |")
    L += ["",
          "Qwen shared flags:`--reasoning-parser deepseek_r1 --max-model-len 65536 "
          "--gpu-memory-utilization 0.92 --enable-auto-tool-choice "
          "--tool-call-parser qwen3_coder`;",
          f"gpt-oss does not carry Qwen flags, it only needs `{GPTOSS_SERVE_FLAGS}`.", "",
          "## Piece table", "",
          "| tag | model | split | num-shards | shard-id → port | outdir | exp | session |",
          "|---|---|---|---|---|---|---|---|"]
    for c in cfg["clients"]:
        m = MODEL_TABLE[c["model_key"]]
        mapping = ", ".join(f"s{i}→{p}" for i, p in enumerate(c["shard_ports"]))
        L.append(f"| {c['tag']} | {m['served']} | {c['split']} | {c['num_shards']} | "
                 f"{mapping} | `$F/{c['outdir']}` | {c['exp']} | "
                 f"`{prefix}_{c['tag']}_s<k>` |")
    L += ["",
          f"`$F` = `{cfg['envs_root']}/runs/{cfg['run_id']}`, log `$F/logs/<session>.log`.",
          f"client shared args `{e['common']} --resume`;"
          f"gpt-oss pieces additionally get `--preset {cfg['gptoss_client_preset']}`."]
    if multi:
        L.append(f"{cfg['traj_per_task']} trajectories per task: all pieces additionally get "
                 f"`{multi}`, the k-th trajectory uses the k-th seed,"
                 f"trajectories land at `appworld_<task_id>_r<k>.jsonl`.")
    L += [f"outdir must always use the standard name `{cfg['env']}_<model_key>`"
          "(downstream event extraction identifies the model from the directory name's suffix).",
          "", "## Launch order", "",
          f"1. `python3 launch_servers.py`({len(cfg['servers'])} instances all up, log shows "
          "\"Application startup complete\" and `curl -s http://<host>:<port>/v1/models` responds)",
          "2. smoke: 1 task per model (see runbook §3.3)",
          "3. `bash launch_clients.sh`",
          "4. dual registration: `ops/gpu_jobs.py register` + `ops/record.py start`",
          ""]
    return "\n".join(L)


# ----------------------------------------------------------------- main flow

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="manifest json")
    ap.add_argument("--dry-run", action="store_true",
                    help="trial generation: write only to the --out-override directory, never touch envs/")
    ap.add_argument("--out-override", default=None,
                    help="rewrite to a different directory (required when --dry-run is set)")
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting existing same-name files in the target directory")
    args = ap.parse_args()

    cfg, warns = load_manifest(args.config)
    for w in warns:
        print("gen_launch: WARN:", w)

    if args.dry_run and not args.out_override:
        die("--dry-run must be paired with --out-override (prevents accidentally writing to a live collection directory)")
    outdir = Path(args.out_override) if args.out_override else \
        Path(cfg["envs_root"]) / "runs" / cfg["run_id"]
    outdir.mkdir(parents=True, exist_ok=True)

    files = {"launch_servers.py": gen_servers(cfg),
             "launch_clients.sh": gen_clients(cfg),
             "MANIFEST.md": gen_manifest_md(cfg)}
    exist = [n for n in files if (outdir / n).exists()]
    if exist and not args.force:
        die(f"{outdir} already has {exist}, refusing to overwrite (add --force to overwrite)")

    for name, text in files.items():
        p = outdir / name
        p.write_text(text)
        if name.endswith(".sh"):
            os.chmod(p, 0o775)
        print("wrote", p)
    print(f"gen_launch: {len(cfg['servers'])} server instances / "
          f"{sum(c['num_shards'] for c in cfg['clients'])} pieces"
          f"{' (dry-run)' if args.dry_run else ''}; generates only, does not execute.")


if __name__ == "__main__":
    main()
