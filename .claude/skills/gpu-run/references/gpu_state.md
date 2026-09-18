Surveyed on: 2026-07-29 (measured, not hearsay).

## Hardware and drivers

| Host | Alias | GPUs | VRAM per card | Driver | CUDA | Python | RAM |
|---|---|---|---|---|---|---|---|
| tokyo105 | shiga | 8x RTX A6000 (idx 0-7) | 48G | 575.64.03 | **12.9** | 3.10.12 | 251G |
| tokyo106 | -- | 10x RTX A6000 (idx 0-9) | 48G | 535.230.02 | **12.2** | 3.10.12 | 251G |
| tokyo107 | -- | 4x RTX 6000 Ada (idx 0-3) | 48G | 535.113.01 | **12.2** | 3.10.12 | 251G |
| tokyo108 | saitama | 3x H100 NVL (idx 0-2, 95G) + 3x H200 NVL (idx 3-5, 143G) | see left | 570.195.03 | **12.8** | 3.12.3 | 503G |

## Known traps

1. **tokyo106/107 drivers only go up to CUDA 12.2** -- newer vLLM/torch
   builds needing cu124+ wheels may report driver incompatibility on these
   two; when a package install reports a CUDA version error, think of this
   first, and switch to tokyo105/108 or downgrade the wheel version.
   - **Measured exception (2026-07-29)**: cu128-wheel torch runs fine on
     106/107 as usual (CUDA minor-version forward compatibility kicks in), so
     do not automatically avoid these two just because of this trap; counting
     them, the training pool actually has 19 usable cards. Only downgrade the
     wheel version when a driver error actually shows up.
2. **Dedupe the aliases**: shiga=tokyo105, saitama=tokyo108, only four
   physical machines. Always use tokyo names for probing and allocation,
   never treat an alias as a fifth machine and double-count a card.
3. **tokyo108 has mixed card types**: idx 0-2 are H100 (95G), idx 3-5 are
   H200 (143G); pick idx by VRAM need, do not default to starting from 0.
4. `/home` is shared over NFS across the whole cluster, paths are consistent
   everywhere; logs can be read locally, no need for ssh.
5. The HF cache is on NFS: `HF_HOME=/net/tokyo100-10g/data/str01_01/y-guo/hf`
   (Qwen3.5-4B/9B, the whole Qwen3 family, the whole Qwen2.5 family already
   cached); model weights also download here, not to /home.
6. hf_server port convention: `8712 + gpu_id` (a historical convention on
   tokyo108).

## Machines outside the pool (do not use)

- tokyo104: 8x Quadro RTX 8000 46G, old Turing cards with no bf16, last
  resort.
- tokyo101: driver broken (NVML mismatch), needs a reboot, leave it alone.
- tokyo100/102/103/199, yebis, setagaya: ssh unreachable (measured
  2026-07-25).
