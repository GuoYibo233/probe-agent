"""Launch shell for the plan cell of the theta sweep curve (five theta
points, tokyo106 five A6000 cards, one each).

Structure copied from envs/serve_logs/launch_vllm_trio.py: one JOBS table +
tmux session start + "SKIP if the session already exists" protection. The
plan cell only consumes the 0.6B parameter production line; a single card
has much more than 48G to spare, so it's one card per theta, five in
parallel.

Hard constraint of the curve: the five points may only differ in the single
variable --theta; the other parameters (ctool/cgen/data/traj-root/miss-policy)
come from COMMON, so a change can only be made in one place.

  Launch all five full points:  python3 pipeline/inject/launch_plan_sweep.py
  Launch smoke only (theta=0.80, --limit 4, tokyo106 g0): ... launch_plan_sweep.py --smoke
  execute cell (a separate set of run directories, with _exec auto-appended to the directory name):
      python3 pipeline/inject/launch_plan_sweep.py --miss-policy execute --only th0925
  After the execute cell's plan segment finishes, two more pure-CPU steps must run before entering run:
      exec_calls.py (envs/appworld/venv interpreter, actually executes) → replay_inject.py merge-exec

tokyo106's driver only goes up to CUDA 12.2 (ops/gpu_state.md pitfall 1);
before using this machine, actually test with smoke whether the cu128 wheel
can even start -- smoke doubles as both a compatibility test and a
--theta-takes-effect test.
"""
import argparse
import shlex
import subprocess

HOST = "tokyo106"
ROOT = "/home/y-guo/reproduce/new1"
PY = f"{ROOT}/cprobe-env/bin/python"
LOGDIR = f"{ROOT}/pipeline/inject/logs"

# The curve's hard constraint lands here: all points share one string of
# parameters, and a change can only be made here.
# --miss-policy is not hardcoded here -- it's a command-line argument
# (--miss-policy), because the execute cell needs a separate set of run
# directories, and hardcoding it to skip would mean code has to change just
# to launch the execute set
COMMON = (
    "--ctool-run pipeline/runs/c1_gptoss_ctool "
    "--cgen-run  pipeline/runs/c1_gptoss_cgen "
    "--data      pipeline/data/aw_official_v1/gptoss "
    "--traj-root envs/runs/w0_aw_official/appworld_gptoss"
)

# (gpu, theta, run_id). th0925 is the sixth point: same theta as the
# historical run aw_gptoss_r10, regenerates a plan (does not reuse the old
# outputs), and the run segment runs a dedicated service + concurrency 16,
# used to measure the perturbation serving conditions have on token counts.
POINTS = [
    (0, "0.50", "aw_gptoss_th050"),
    (1, "0.70", "aw_gptoss_th070"),
    (2, "0.80", "aw_gptoss_th080"),
    (3, "0.875", "aw_gptoss_th0875"),
    (4, "0.95", "aw_gptoss_th095"),
    (5, "0.925", "aw_gptoss_th0925"),
]

SMOKE = (0, "0.80", "_smoke_th080", "--limit 4")


def plan_cmd(theta, run_id, policy="skip", extra=""):
    return (f"{PY} pipeline/inject/replay_inject.py plan {COMMON} "
            f"--miss-policy {policy} "
            f"--theta {theta} --out pipeline/inject/runs/{run_id}"
            + (f" {extra}" if extra else ""))


def launch(gpu, session, cmd, log):
    probe = subprocess.run(
        ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
    if probe.returncode == 0:
        print("SKIP (session exists):", session)
        return
    inner = (f"cd {ROOT} && CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}")
    tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
    subprocess.run(["ssh", "-n", HOST, tmux], check=True)
    print(f"launched {session} on {HOST} gpu {gpu} -> {log}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", default="",
                    help="launch only these points (comma-separated tags, e.g. th0925). Leave empty = launch all. "
                         "For a point that already finished, its session is gone -- the SKIP guard cannot catch it, so refiring a single point must use this flag")
    ap.add_argument("--miss-policy", default="skip",
                    choices=["skip", "oracle", "execute"],
                    help="what to do when the prediction does not match the ground truth. The execute version's run dir name gets "
                         "an _exec suffix; do not write plans from the two settings into the same dir -- "
                         "one curve allows only one miss_policy")
    ap.add_argument("--suffix", default="",
                    help="run dir suffix. When left empty, the execute version automatically uses _exec")
    a = ap.parse_args()
    suf = a.suffix or ("_exec" if a.miss_policy == "execute" else "")

    if a.smoke:
        gpu, theta, run_id, extra = SMOKE
        session = "new1_thsw_smoke_t106g0"
        launch(gpu, session, plan_cmd(theta, run_id + suf, a.miss_policy,
                                      extra), f"{LOGDIR}/{session}.log")
        return

    only = [t for t in a.only.split(",") if t]
    for gpu, theta, run_id in POINTS:
        tag = run_id.replace("aw_gptoss_", "")
        if only and tag not in only:
            continue
        session = f"new1_thsw_plan_{tag}{suf}_t106g{gpu}"
        launch(gpu, session, plan_cmd(theta, run_id + suf, a.miss_policy),
               f"{LOGDIR}/{session}.log")


if __name__ == "__main__":
    main()
