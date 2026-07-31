"""θ 扫描曲线的 plan 段发射壳（五个 θ 点，tokyo106 五张 A6000 各一个）。

结构照抄 envs/serve_logs/launch_vllm_trio.py：一个 JOBS 表 + tmux 起会话 +
"会话已存在就 SKIP"的保护。plan 段只吃 0.6B 参数产线，单卡 48G 富余得多，
所以一张卡一个 θ、五个并行。

曲线的硬约束：五个点只允许差 --theta 一个变量，别的参数（ctool/cgen/data/
traj-root/miss-policy）从 COMMON 里来，改只能改一处。

  发射五个全量点：  python3 pipeline/inject/launch_plan_sweep.py
  只发 smoke（θ=0.80，--limit 4，tokyo106 g0）： ... launch_plan_sweep.py --smoke
  execute 档（另一组 run 目录，目录名自动加 _exec）：
      python3 pipeline/inject/launch_plan_sweep.py --miss-policy execute --only th0925
  execute 档的 plan 段跑完后还有两段纯 CPU 前置才能进 run：
      exec_calls.py（envs/appworld/venv 解释器，真执行）→ replay_inject.py merge-exec

tokyo106 驱动只到 CUDA 12.2（ops/gpu_state.md 坑 1），上这台机器前先用 smoke
实测一次 cu128 轮子能不能起——smoke 就是兼容性测试与 --theta 生效测试合一。
"""
import argparse
import shlex
import subprocess

HOST = "tokyo106"
ROOT = "/home/y-guo/reproduce/new1"
PY = f"{ROOT}/cprobe-env/bin/python"
LOGDIR = f"{ROOT}/pipeline/inject/logs"

# 曲线的硬约束在这里落地:所有点共用同一串参数,改只能改这一处。
# --miss-policy 不写死在这里 —— 它是命令行参数(--miss-policy),因为 execute
# 档要另铺一组 run 目录,而写死成 skip 就只能改代码才能发 execute 那一组
COMMON = (
    "--ctool-run pipeline/runs/c1_gptoss_ctool "
    "--cgen-run  pipeline/runs/c1_gptoss_cgen "
    "--data      pipeline/data/aw_official_v1/gptoss "
    "--traj-root envs/runs/w0_aw_official/appworld_gptoss"
)

# (gpu, theta, run_id)。th0925 是第六点:与历史 run aw_gptoss_r10 同 θ,重新生成
# 一份 plan(不复用旧产物),run 段跑专用服务 + concurrency 16,用来量 serving
# 条件对 token 计数的扰动。
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
                    help="只发这些点(逗号分隔的 tag,如 th0925)。留空=全发。"
                         "已跑完的点会话已经消失,SKIP 保护挡不住,补发单点必须用它")
    ap.add_argument("--miss-policy", default="skip",
                    choices=["skip", "oracle", "execute"],
                    help="预测与真实不符时怎么办。execute 档的 run 目录名会加 "
                         "_exec 后缀,别把两个口径的 plan 写进同一个目录 —— "
                         "一条曲线只允许一个 miss_policy")
    ap.add_argument("--suffix", default="",
                    help="run 目录后缀。留空时 execute 档自动用 _exec")
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
