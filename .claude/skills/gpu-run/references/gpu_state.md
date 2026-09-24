Surveyed on: 2026-07-29 (measured, not hearsay).

## Hardware and drivers

| Host | Alias | GPUs | VRAM per card | Driver | CUDA | Python | RAM |
|---|---|---|---|---|---|---|---|
| tokyo105 | shiga | 8x RTX A6000 (idx 0-7) | 47 GiB | 575.64.03 | **12.9** | 3.10.12 | 251G |
| tokyo106 | -- | 10x RTX A6000 (idx 0-9) | 47 GiB | 535.230.02 | **12.2** | 3.10.12 | 251G |
| tokyo107 | -- | 4x RTX 6000 Ada (idx 0-3) | 47 GiB | 535.113.01 | **12.2** | 3.10.12 | 251G |
| tokyo108 | saitama | 3x H100 NVL (idx 0-2, 93 GiB) + 3x H200 NVL (idx 3-5, 140 GiB) | see left | 570.195.03 | **12.8** | 3.12.3 | 503G |

## Known traps

1. **tokyo106/107 drivers only go up to CUDA 12.2** -- newer vLLM/torch
   builds needing cu124+ wheels may report driver incompatibility on these
   two; when a package install reports a CUDA version error, think of this
   first, and switch to tokyo105/108 or downgrade the wheel version.
   - **Measured exception (2026-07-29)**: a cu128-wheel torch runs on
     106/107 (CUDA minor-version forward compatibility), so do not avoid these
     two machines for this trap alone; downgrade the wheel only when a driver
     error actually shows up. The pool's card counts and each card's memory
     are the per-host card lists of `constants/cards.yaml`.
2. **Dedupe the aliases**: shiga=tokyo105, saitama=tokyo108, only four
   physical machines. Always use tokyo names for probing and allocation,
   never treat an alias as a fifth machine and double-count a card.
3. **tokyo108 has mixed card types**: idx 0-2 are H100 (93 GiB), idx 3-5 are
   H200 (140 GiB); pick idx by VRAM need, do not default to starting from 0.
4. `/home` is shared over NFS across the whole cluster, paths are consistent
   everywhere; logs can be read locally, no need for ssh.
5. The HF cache is on NFS: `HF_HOME=/net/tokyo100-10g/data/str01_01/y-guo/hf`
   (Qwen3.5-4B/9B, the whole Qwen3 family, the whole Qwen2.5 family already
   cached); model weights also download here, not to /home.

## Machines outside the pool (do not use)

- tokyo104: 8x Quadro RTX 8000 46G, old Turing cards with no bf16, last
  resort.
- tokyo101: driver broken (NVML mismatch), needs a reboot, leave it alone.
- tokyo100/102/103/199, yebis, setagaya: ssh unreachable (measured
  2026-07-25).
