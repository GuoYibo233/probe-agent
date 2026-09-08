"""Service launcher for the run segment of the eight-arm splice-back: one gpt-oss-120b on
each of three free H100s on tokyo108.

Same parameters verbatim as launch_vllm_thsweep4.py (same model, same --served-model-name,
--max-model-len 65536, --gpu-memory-utilization 0.92, the same three environment variables,
compile cache and logs both go to /net -- /home has an NFS server-side quota, and filling it
can kill vllm too), only the card and port change. Since 2026-08-10 it also sets one more
variable than thsweep4, VLLM_SYSTEM_START_DATE (pins the service-side prompt date,
METHOD.md §6-④):

  gpt-oss-120b -> H100 GPU 0, port 8114   (shard s0: nofill,skel_switch)
  gpt-oss-120b -> H100 GPU 1, port 8115   (shard s1: inject,inject_stop,
                                           switch_only,skel_b)
  gpt-oss-120b -> H100 GPU 2, port 8116   (shard s2: skel_bare,skel_a)
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

CACHE_ROOT = "/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache"
LOGDIR = f"{CACHE_ROOT}/logs"

GPTOSS_FLAGS = "--max-model-len 65536 --gpu-memory-utilization 0.92"

# Same-settings premise (METHOD.md §2.1/§6-④): the chat baseline's prompt date is generated
# by the service side; the live-run prefix is pinned by /render to rebuild.COLLECT_DATE; for
# the two sides to be comparable, the service side must also be pinned to the same day.
SYSTEM_START_DATE = "2026-07-31"   # = pipeline/inject/rebuild.py COLLECT_DATE

JOBS = [
    (0, 8114, "new1_splice_srv_a_t108g0"),
    (1, 8115, "new1_splice_srv_b_t108g1"),
    (2, 8116, "new1_splice_srv_c_t108g2"),
]


def main() -> None:
    subprocess.run(["ssh", "-n", HOST, f"mkdir -p {LOGDIR}"], check=True)
    for gpu, port, session in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{LOGDIR}/{session}.log"
        cmd = (
            f"{VLLM} serve {YMODELS}/gpt-oss-120b "
            f"--served-model-name gpt-oss-120b "
            f"--port {port} --host 0.0.0.0 {GPTOSS_FLAGS}"
        )
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"VLLM_CACHE_ROOT={CACHE_ROOT} TRITON_CACHE_DIR={CACHE_ROOT}/triton "
            f"VLLM_SYSTEM_START_DATE={SYSTEM_START_DATE} "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} > {log} 2>&1"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print(f"launched {session} gpu {gpu} port {port} -> log: {log}")


if __name__ == "__main__":
    main()
