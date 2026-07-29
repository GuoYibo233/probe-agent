"""T9 单任务端到端演示:bfcl multi_turn_base 单 entry,多口径顺跑。

演示三件套(T9 验收):截断 / 影子记录 / fork 对照各一次,外加基线。
日志可见:触发位置、提交的调用、与 agent 本意调用的核对、fork 分支 token 差。

前置(两张卡,由 A 线发射):
  ① vLLM 起 qwen3.5-27b(不设 --served-model-name,模型 id=权重路径,
     与 bfcl_q35 批次采集时的约定一致)
  ② mbert-env 起探针服务:probe_server.py --run envs/bert_runs/bfcl_v3

用法(bfcl venv,纯 CPU 进程):
  cd /home/y-guo/reproduce/new1/envs/bfcl
  LOCAL_SERVER_ENDPOINT=<vllm主机> LOCAL_SERVER_PORT=<端口> \
  venv/bin/python ../loop/run_bfcl_demo.py --entry multi_turn_base_0 \
      --modes baseline,shadow,truncate,fork \
      --probe-url http://<探针主机>:8201 --out ../loop/runs/demo1
"""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP_DIR))
from bfcl_loop_handler import QwenLoopHandler, mtu  # noqa: E402

from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING  # noqa: E402
from bfcl_eval.utils import load_dataset_entry  # noqa: E402

QWEN_PATH = "/net/tokyo100-10g/data/str01_01/zhou-y/models/Qwen3.5-27B"


def purge_instances(entry_id):
    """清 multi_turn_utils 模块缓存里本 entry(含 fork)的实例,口径间互不串。"""
    for k in [k for k in list(vars(mtu))
              if entry_id in k and k.endswith("_instance")]:
        delattr(mtu, k)


def summarize(out_dir, entry_id, modes):
    rows = {}
    for f in sorted(Path(out_dir).glob(f"{entry_id}_*.jsonl")):
        recs = [json.loads(l) for l in open(f)]
        fin = next((r for r in recs if r["type"] == "final"), None)
        trigs = [r for r in recs if r["type"] == "trigger"]
        name = f.stem[len(entry_id) + 1:]
        rows[name] = {"final": fin, "triggers": trigs}

    print("\n" + "=" * 72)
    print(f"演示汇总 — {entry_id}")
    for name, r in rows.items():
        f = r["final"] or {}
        print(f"\n[{name}] tokens_out={f.get('gen_tokens_out')} "
              f"wall={f.get('wall_s_total')}s probes={f.get('probe_calls')} "
              f"probe_ms_sum={f.get('probe_ms')} aborted={f.get('n_aborted')}")
        for t in r["triggers"]:
            print(f"  触发@{t['step']} sent#{t.get('boundary_idx')} "
                  f"char{t.get('at_char')} conf={t.get('conf')} "
                  f"预测={t.get('label')} 截断={t.get('truncated')} "
                  f"agent实际={t.get('agent_actual')} 命中={t.get('match')}")
    base = rows.get("baseline", {}).get("final") or {}
    for name, r in rows.items():
        if name.startswith("fork") and "branch" not in str(
                (r["final"] or {}).get("mode", "")):
            pass
    # fork 分支 token 差:主线(fork 口径) vs 分支账本
    main = rows.get("fork", {}).get("final")
    branch = next((r["final"] for n, r in rows.items()
                   if n.startswith("fork_fork")), None)
    if main and branch:
        print(f"\n[fork 对照] 主线 tokens_out={main['gen_tokens_out']} "
              f"分支 tokens_out={branch['gen_tokens_out']} "
              f"差={main['gen_tokens_out'] - branch['gen_tokens_out']}")
    print("=" * 72)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", default="multi_turn_base_0")
    ap.add_argument("--modes", default="baseline,shadow,truncate,fork")
    ap.add_argument("--registry", default="Qwen/Qwen3-32B",
                    help="bfcl 注册名(qwen 批次采集用的同款)")
    ap.add_argument("--local-model-path", default=QWEN_PATH)
    ap.add_argument("--probe-url", default="http://127.0.0.1:8201")
    ap.add_argument("--theta", type=float, default=0.95,
                    help="bfcl_v3 风险≤0.05 档的 θ")
    ap.add_argument("--temperature", type=float, default=0.001)
    ap.add_argument("--fork-max", type=int, default=1)
    ap.add_argument("--out", default=str(LOOP_DIR / "runs" / "demo1"))
    args = ap.parse_args()

    entries = load_dataset_entry("multi_turn_base",
                                 include_prereq=False)
    entry = next(e for e in entries if e["id"] == args.entry)
    print(f"entry={args.entry} turns={len(entry['question'])} "
          f"classes={entry['involved_classes']}")

    config = MODEL_CONFIG_MAPPING[args.registry]
    results = {}
    for mode in args.modes.split(","):
        purge_instances(args.entry)
        print(f"\n{'#' * 24} 口径: {mode} {'#' * 24}")
        handler = QwenLoopHandler(
            model_name=config.model_name, temperature=args.temperature,
            registry_name=args.registry, is_fc_model=config.is_fc_model,
            loop_cfg={"mode": mode, "probe_url": args.probe_url,
                      "theta": args.theta, "out_dir": args.out,
                      "fork_max": args.fork_max})
        handler.spin_up_local_server(
            num_gpus=1, gpu_memory_utilization=0.9, backend="vllm",
            skip_server_setup=True, local_model_path=args.local_model_path)
        r = handler.inference(deepcopy(entry), include_input_log=False,
                              exclude_state_log=True)
        results[mode] = r
        (Path(args.out) / f"{args.entry}_{mode}_result.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=1, default=str))
    purge_instances(args.entry)

    summarize(args.out, args.entry, args.modes.split(","))


if __name__ == "__main__":
    main()
