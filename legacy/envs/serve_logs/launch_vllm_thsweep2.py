"""Second batch of gpt-oss-120b services for the run segment of the θ sweep: three replicas,
landing on the three H100s that were freed up.

After c2_alfworld collection wrapped up (474+474 trajectories all ended with "type": "final"),
the three cards it occupied, tokyo108 GPU 0/1/2 (H100 95G), became free. The first batch of
services (launch_vllm_thsweep.py) runs 8111/8112/8113 on three H200s, but with only three
services for six θ points, half the time was spent queuing; this batch connects the remaining
three θ points too, giving all six points one-to-one full concurrency.

  gpt-oss-120b -> H100 GPU 0, port 8114   (replica D)
  gpt-oss-120b -> H100 GPU 1, port 8115   (replica E)
  gpt-oss-120b -> H100 GPU 2, port 8116   (replica F)

Parameters are **identical, verbatim, to the first batch** (model path / served-model-name /
max-model-len 65536 / gpu-memory-utilization 0.92 / the three environment variables); otherwise
the service-side convention would not be consistent across the six points: concurrency and
batch composition affect the token count of greedy continuation (this known deviation is
already listed in the replay_inject.py file header), so the service-side parameters especially
must not differ.

H100 is 95G while H200 is 143G; 0.92 × 95G ≈ 87G. During collection, the same model on these
three cards measured 89G in actual use, which fits.
"""
import shlex
import subprocess

HOST = "tokyo108"
WORKDIR = "/home/y-guo/reproduce/new1/envs/serve_logs"
VLLM = "/home/y-guo/reproduce/new1/envs/vllm-env/bin/vllm"
YMODELS = "/net/tokyo100-10g/data/str01_01/y-guo/models"

GPTOSS_FLAGS = "--max-model-len 65536 --gpu-memory-utilization 0.92"

JOBS = [
    (0, 8114, "new1_thsw_srv_d_t108g0"),
    (1, 8115, "new1_thsw_srv_e_t108g1"),
    (2, 8116, "new1_thsw_srv_f_t108g2"),
]


def main() -> None:
    for gpu, port, session in JOBS:
        probe = subprocess.run(
            ["ssh", "-n", HOST, f"tmux has-session -t {session} 2>/dev/null"])
        if probe.returncode == 0:
            print("SKIP (session exists):", session)
            continue
        log = f"{WORKDIR}/{session}.log"
        cmd = (
            f"{VLLM} serve {YMODELS}/gpt-oss-120b "
            f"--served-model-name gpt-oss-120b "
            f"--port {port} --host 0.0.0.0 {GPTOSS_FLAGS}"
        )
        inner = (
            f"cd {WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"CUDA_VISIBLE_DEVICES={gpu} {cmd} 2>&1 | tee {log}"
        )
        tmux = f"tmux new-session -d -s {session} {shlex.quote(inner)}"
        subprocess.run(["ssh", "-n", HOST, tmux], check=True)
        print(f"launched {session} gpu {gpu} port {port} -> log: {log}")


if __name__ == "__main__":
    main()
