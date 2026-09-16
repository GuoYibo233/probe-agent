"""Client for the run segment of the eight-arm splice-back (one process per piece, run in tmux).

Self-sequencing: first wait for both conditions to hold -- ①PLAN_OK appears in the run
directory (a go-ahead marker touched after the plan rerun finishes and the main session has
manually checked pred_label/gen_min_p; plan_config.json alone does not count, to prevent
burning the eight arms on a bad plan); ②this piece's vLLM replica returns 200 on /v1/models.
Then it sends 12 smoke requests first, and only opens up to full volume once it actually gets
continuations back.

Pieces are balanced by expected generation volume (nofill/inject full-length continuation is
heaviest, switch/stop entering the body text directly is lightest, and skel_bare/a/b want to
sit in the middle after the skeleton):
  s0 -> 8114: nofill,skel_switch
  s1 -> 8115: inject,inject_stop,switch_only,skel_b
  s2 -> 8116: skel_bare,skel_a
Each piece writes its own raw file under --tag .sN; at wrap-up they are cat'ed together into
raw.jsonl before scoring; the resume key (event, arm) is self-consistent within each tag file.
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

    # smoke: the first 12 plan records; every arm should be able to send a real request; if it
    # cannot get even one continuation back, stop right here -- never open up the volume
    smoke_tag = f".smoke{a.shard}"
    r = subprocess.run(common + ["--limit", "12", "--tag", smoke_tag],
                       cwd=ROOT)
    sp = RUN_DIR / f"raw{smoke_tag}.jsonl"
    n_ok = (sum(1 for l in open(sp) if json.loads(l).get("text"))
            if sp.exists() else 0)
    if r.returncode != 0 or n_ok == 0:
        print(f"SMOKE_FAIL rc={r.returncode} ok={n_ok}", flush=True)
        sys.exit(1)
    print(f"SMOKE_OK {n_ok} items, ramp up", flush=True)
    sp.unlink()

    r = subprocess.run(common + ["--tag", f".s{a.shard}"], cwd=ROOT)
    print(f"CLIENT_DONE shard={a.shard} arms={arms} rc={r.returncode}",
          flush=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
