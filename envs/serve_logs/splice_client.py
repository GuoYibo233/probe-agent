"""拼回八臂 run 段客户端(一个分片一个进程,tmux 里跑)。

自排序:先等两个条件都满足 —— ①run 目录里出现 PLAN_OK(plan 重跑完、
主对话人工核过 pred_label/gen_min_p 之后 touch 的放行标记,光有
plan_config.json 不算,防止拿着坏 plan 烧八臂);②本分片的 vLLM 副本
/v1/models 返回 200。然后先发 12 条 smoke,确认真拿到续写才放全量。

分片按预期生成量配平(nofill/inject 全长续写最重,switch/stop 系直进
正文段最轻,skel_bare/a/b 骨架后还会想居中):
  s0 -> 8114: nofill,skel_switch
  s1 -> 8115: inject,inject_stop,switch_only,skel_b
  s2 -> 8116: skel_bare,skel_a
各分片 --tag .sN 各写各的 raw,收尾 cat 成 raw.jsonl 再 score;
断点续跑键 (event, arm) 在各自 tag 文件内自洽。
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/y-guo/reproduce/new1")
PY = str(ROOT / "cprobe-env/bin/python")
RI = str(ROOT / "pipeline/inject/replay_inject.py")
RUN_DIR = ROOT / "pipeline/inject/runs/aw_gptoss_splice_th0925"
PLAN_OK = RUN_DIR / "PLAN_OK"

SHARDS = {
    0: ("nofill,skel_switch", 8114),
    1: ("inject,inject_stop,switch_only,skel_b", 8115),
    2: ("skel_bare,skel_a", 8116),
}


def healthy(port):
    try:
        url = f"http://tokyo108:{port}/v1/models"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True, choices=SHARDS)
    a = ap.parse_args()
    arms, port = SHARDS[a.shard]

    t0 = time.time()
    while not (PLAN_OK.exists() and healthy(port)):
        print(f"[wait {int(time.time() - t0)}s] plan_ok={PLAN_OK.exists()} "
              f"svc{port}={healthy(port)}", flush=True)
        time.sleep(30)

    common = [PY, RI, "run",
              "--plan", str(RUN_DIR / "plan.jsonl"),
              "--base-url", f"http://tokyo108:{port}/v1",
              "--model", "gpt-oss-120b",
              "--arms", arms, "--concurrency", "16"]

    # smoke:头 12 条 plan 记录,每个臂都该发得出真请求;拿不到一条续写就
    # 停在这里,绝不放量
    smoke_tag = f".smoke{a.shard}"
    r = subprocess.run(common + ["--limit", "12", "--tag", smoke_tag],
                       cwd=ROOT)
    sp = RUN_DIR / f"raw{smoke_tag}.jsonl"
    n_ok = (sum(1 for l in open(sp) if json.loads(l).get("text"))
            if sp.exists() else 0)
    if r.returncode != 0 or n_ok == 0:
        print(f"SMOKE_FAIL rc={r.returncode} ok={n_ok}", flush=True)
        sys.exit(1)
    print(f"SMOKE_OK {n_ok} 条,放量", flush=True)
    sp.unlink()

    r = subprocess.run(common + ["--tag", f".s{a.shard}"], cwd=ROOT)
    print(f"CLIENT_DONE shard={a.shard} arms={arms} rc={r.returncode}",
          flush=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
