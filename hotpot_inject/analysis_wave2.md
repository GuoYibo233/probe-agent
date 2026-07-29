# 第二波聚合(ok-only 配对;完整状态率在文末)

| model | ds | mode | type | cond | d | n | save | soft_c | soft_b | Δsoft |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-4B | hotp | std | brid | both_start | -1 | 39 | 448 | 0.74 | 0.44 | +0.31 |
| Qwen3-4B | hotp | std | brid | hop1 | -1 | 42 | 483 | 0.50 | 0.43 | +0.07 |
| Qwen3-4B | hotp | std | brid | hop1 | 0 | 32 | -156 | 0.47 | 0.47 | +0.00 |
| Qwen3-4B | hotp | std | brid | hop1 | 100 | 41 | -113 | 0.46 | 0.41 | +0.05 |
| Qwen3-4B | hotp | std | brid | hop1 | 25 | 38 | -180 | 0.55 | 0.47 | +0.08 |
| Qwen3-4B | hotp | std | brid | hop1 | 50 | 40 | -155 | 0.53 | 0.45 | +0.08 |
| Qwen3-4B | hotp | std | brid | hop2 | 0 | 13 | -8 | 0.54 | 0.46 | +0.08 |
| Qwen3-4B | hotp | std | brid | hop2 | 25 | 14 | 5 | 0.50 | 0.43 | +0.07 |
| Qwen3-4B | hotp | std | brid | hop2 | 50 | 14 | 9 | 0.50 | 0.43 | +0.07 |
| Qwen3-4B | hotp | std | brid | hop2_start | -1 | 13 | 452 | 0.69 | 0.46 | +0.23 |
| Qwen3-4B | hotp | std | comp | both_start | -1 | 44 | 393 | 0.73 | 0.61 | +0.11 |
| Qwen3-4B | hotp | std | comp | hop1 | -1 | 41 | 314 | 0.54 | 0.61 | -0.07 |
| Qwen3-4B | hotp | std | comp | hop1 | 0 | 38 | -47 | 0.68 | 0.63 | +0.05 |
| Qwen3-4B | hotp | std | comp | hop1 | 100 | 40 | -24 | 0.65 | 0.60 | +0.05 |
| Qwen3-4B | hotp | std | comp | hop1 | 25 | 40 | -123 | 0.65 | 0.60 | +0.05 |
| Qwen3-4B | hotp | std | comp | hop1 | 50 | 42 | -121 | 0.60 | 0.60 | +0.00 |
| Qwen3-4B | hotp | std | comp | hop2 | 0 | 26 | -31 | 0.69 | 0.73 | -0.04 |
| Qwen3-4B | hotp | std | comp | hop2 | 25 | 38 | -14 | 0.68 | 0.66 | +0.03 |
| Qwen3-4B | hotp | std | comp | hop2 | 50 | 38 | 2 | 0.68 | 0.66 | +0.03 |
| Qwen3-4B | hotp | std | comp | hop2_start | -1 | 38 | 291 | 0.61 | 0.66 | -0.05 |
| Qwen3-8B | 2wik | std | brid | both_start | -1 | 54 | 218 | 0.72 | 0.56 | +0.17 |
| Qwen3-8B | 2wik | std | brid | hop1 | -1 | 51 | 152 | 0.22 | 0.53 | -0.31 |
| Qwen3-8B | 2wik | std | brid | hop1 | 0 | 51 | -71 | 0.45 | 0.55 | -0.10 |
| Qwen3-8B | 2wik | std | brid | hop1 | 100 | 51 | 90 | 0.31 | 0.53 | -0.22 |
| Qwen3-8B | 2wik | std | brid | hop1 | 25 | 54 | -33 | 0.41 | 0.56 | -0.15 |
| Qwen3-8B | 2wik | std | brid | hop1 | 50 | 51 | 19 | 0.43 | 0.55 | -0.12 |
| Qwen3-8B | 2wik | std | brid | hop2 | 0 | 39 | 8 | 0.69 | 0.67 | +0.03 |
| Qwen3-8B | 2wik | std | brid | hop2 | 25 | 38 | 34 | 0.68 | 0.66 | +0.03 |
| Qwen3-8B | 2wik | std | brid | hop2 | 50 | 34 | 41 | 0.71 | 0.62 | +0.09 |
| Qwen3-8B | 2wik | std | brid | hop2_start | -1 | 37 | 171 | 0.73 | 0.65 | +0.08 |
| Qwen3-8B | 2wik | std | comp | both_start | -1 | 33 | 233 | 0.97 | 1.00 | -0.03 |
| Qwen3-8B | 2wik | std | comp | hop1 | -1 | 33 | 162 | 0.85 | 1.00 | -0.15 |
| Qwen3-8B | 2wik | std | comp | hop1 | 0 | 30 | -25 | 0.93 | 1.00 | -0.07 |
| Qwen3-8B | 2wik | std | comp | hop1 | 100 | 33 | 100 | 0.82 | 1.00 | -0.18 |
| Qwen3-8B | 2wik | std | comp | hop1 | 25 | 33 | -26 | 0.82 | 1.00 | -0.18 |
| Qwen3-8B | 2wik | std | comp | hop1 | 50 | 33 | 29 | 0.82 | 1.00 | -0.18 |
| Qwen3-8B | 2wik | std | comp | hop2 | 0 | 32 | 6 | 1.00 | 1.00 | +0.00 |
| Qwen3-8B | 2wik | std | comp | hop2 | 25 | 32 | 30 | 1.00 | 1.00 | +0.00 |
| Qwen3-8B | 2wik | std | comp | hop2 | 50 | 32 | 40 | 1.00 | 1.00 | +0.00 |
| Qwen3-8B | 2wik | std | comp | hop2_start | -1 | 32 | 167 | 0.81 | 1.00 | -0.19 |
| Qwen3-8B | hotp | npm | brid | hop1 | -1 | 55 | 454 | 0.51 | 0.55 | -0.04 |
| Qwen3-8B | hotp | npm | brid | hop1 | 0 | 55 | -29 | 0.58 | 0.55 | +0.04 |
| Qwen3-8B | hotp | npm | brid | hop1 | 100 | 55 | 102 | 0.49 | 0.55 | -0.05 |
| Qwen3-8B | hotp | npm | brid | hop1 | 25 | 54 | -36 | 0.50 | 0.56 | -0.06 |
| Qwen3-8B | hotp | npm | brid | hop1 | 50 | 54 | 19 | 0.54 | 0.54 | +0.00 |
| Qwen3-8B | hotp | npm | brid | hop2 | 0 | 16 | 29 | 0.69 | 0.69 | +0.00 |
| Qwen3-8B | hotp | npm | brid | hop2 | 25 | 16 | 40 | 0.69 | 0.69 | +0.00 |
| Qwen3-8B | hotp | npm | brid | hop2 | 50 | 16 | 11 | 0.69 | 0.69 | +0.00 |
| Qwen3-8B | hotp | npm | brid | hop2_start | -1 | 16 | 545 | 0.75 | 0.69 | +0.06 |
| Qwen3-8B | hotp | npm | comp | hop1 | -1 | 45 | 230 | 0.60 | 0.71 | -0.11 |
| Qwen3-8B | hotp | npm | comp | hop1 | 0 | 43 | -34 | 0.77 | 0.72 | +0.05 |
| Qwen3-8B | hotp | npm | comp | hop1 | 100 | 45 | 23 | 0.64 | 0.71 | -0.07 |
| Qwen3-8B | hotp | npm | comp | hop1 | 25 | 42 | -94 | 0.55 | 0.71 | -0.17 |
| Qwen3-8B | hotp | npm | comp | hop1 | 50 | 44 | -2 | 0.59 | 0.70 | -0.11 |
| Qwen3-8B | hotp | npm | comp | hop2 | 0 | 40 | -19 | 0.72 | 0.70 | +0.03 |
| Qwen3-8B | hotp | npm | comp | hop2 | 25 | 42 | 11 | 0.71 | 0.71 | +0.00 |
| Qwen3-8B | hotp | npm | comp | hop2 | 50 | 43 | 42 | 0.72 | 0.70 | +0.02 |
| Qwen3-8B | hotp | npm | comp | hop2_start | -1 | 40 | 223 | 0.62 | 0.70 | -0.07 |
| Qwen3-8B | hotp | std | brid | both_start | -1 | 48 | 457 | 0.67 | 0.50 | +0.17 |
| Qwen3-8B | hotp | std | brid | hop1 | -1 | 44 | 387 | 0.48 | 0.52 | -0.05 |
| Qwen3-8B | hotp | std | brid | hop1 | 0 | 46 | -42 | 0.52 | 0.50 | +0.02 |
| Qwen3-8B | hotp | std | brid | hop1 | 100 | 46 | 17 | 0.52 | 0.52 | +0.00 |
| Qwen3-8B | hotp | std | brid | hop1 | 25 | 46 | -196 | 0.48 | 0.52 | -0.04 |
| Qwen3-8B | hotp | std | brid | hop1 | 50 | 46 | -163 | 0.50 | 0.50 | +0.00 |
| Qwen3-8B | hotp | std | brid | hop2 | 0 | 16 | -88 | 0.75 | 0.69 | +0.06 |
| Qwen3-8B | hotp | std | brid | hop2 | 25 | 15 | -22 | 0.73 | 0.67 | +0.07 |
| Qwen3-8B | hotp | std | brid | hop2 | 50 | 15 | 43 | 0.73 | 0.67 | +0.07 |
| Qwen3-8B | hotp | std | brid | hop2_start | -1 | 16 | 341 | 0.69 | 0.69 | +0.00 |
| Qwen3-8B | hotp | std | comp | both_start | -1 | 46 | 327 | 0.72 | 0.74 | -0.02 |
| Qwen3-8B | hotp | std | comp | hop1 | -1 | 45 | 251 | 0.53 | 0.71 | -0.18 |
| Qwen3-8B | hotp | std | comp | hop1 | 0 | 42 | -41 | 0.69 | 0.71 | -0.02 |
| Qwen3-8B | hotp | std | comp | hop1 | 100 | 44 | -5 | 0.59 | 0.70 | -0.11 |
| Qwen3-8B | hotp | std | comp | hop1 | 25 | 45 | -67 | 0.58 | 0.71 | -0.13 |
| Qwen3-8B | hotp | std | comp | hop1 | 50 | 45 | -58 | 0.60 | 0.71 | -0.11 |
| Qwen3-8B | hotp | std | comp | hop2 | 0 | 40 | -12 | 0.70 | 0.72 | -0.03 |
| Qwen3-8B | hotp | std | comp | hop2 | 25 | 41 | 19 | 0.71 | 0.73 | -0.02 |
| Qwen3-8B | hotp | std | comp | hop2 | 50 | 41 | 30 | 0.73 | 0.73 | +0.00 |
| Qwen3-8B | hotp | std | comp | hop2_start | -1 | 40 | 248 | 0.60 | 0.75 | -0.15 |
| Qwen3-8B | hotp | wrg | brid | hop1 | -1 | 44 | 428 | 0.45 | 0.50 | -0.05 |
| Qwen3-8B | hotp | wrg | brid | hop1 | 50 | 47 | -118 | 0.43 | 0.49 | -0.06 |
| Qwen3-8B | hotp | wrg | brid | hop2 | 50 | 13 | 51 | 0.69 | 0.69 | +0.00 |
| Qwen3-8B | hotp | wrg | brid | hop2_start | -1 | 12 | 329 | 0.75 | 0.67 | +0.08 |
| Qwen3-8B | hotp | wrg | brid | wrong | 50 | 46 | -39 | 0.37 | 0.48 | -0.11 |
| Qwen3-8B | hotp | wrg | brid | wrong_start | -1 | 41 | 319 | 0.15 | 0.49 | -0.34 |
| Qwen3-8B | hotp | wrg | comp | hop1 | -1 | 46 | 251 | 0.61 | 0.74 | -0.13 |
| Qwen3-8B | hotp | wrg | comp | hop1 | 50 | 46 | -82 | 0.61 | 0.74 | -0.13 |
| Qwen3-8B | hotp | wrg | comp | hop2 | 50 | 42 | 24 | 0.79 | 0.76 | +0.02 |
| Qwen3-8B | hotp | wrg | comp | hop2_start | -1 | 42 | 247 | 0.64 | 0.76 | -0.12 |
| Qwen3-8B | hotp | wrg | comp | wrong | 50 | 43 | 24 | 0.60 | 0.72 | -0.12 |
| Qwen3-8B | hotp | wrg | comp | wrong_start | -1 | 42 | 176 | 0.57 | 0.76 | -0.19 |
| Qwen3.5-4B | 2wik | std | brid | both_start | -1 | 6 | -30 | 0.83 | 0.67 | +0.17 |
| Qwen3.5-4B | 2wik | std | brid | hop1 | -1 | 7 | 137 | 0.43 | 0.43 | +0.00 |
| Qwen3.5-4B | 2wik | std | brid | hop1 | 0 | 19 | 63 | 0.42 | 0.63 | -0.21 |
| Qwen3.5-4B | 2wik | std | brid | hop1 | 100 | 7 | 137 | 0.43 | 0.43 | +0.00 |
| Qwen3.5-4B | 2wik | std | brid | hop1 | 25 | 17 | 13 | 0.41 | 0.59 | -0.18 |
| Qwen3.5-4B | 2wik | std | brid | hop1 | 50 | 15 | 58 | 0.60 | 0.60 | +0.00 |
| Qwen3.5-4B | 2wik | std | brid | hop2 | 25 | 15 | -26 | 0.80 | 0.80 | +0.00 |
| Qwen3.5-4B | 2wik | std | brid | hop2 | 50 | 14 | 41 | 0.79 | 0.71 | +0.07 |
| Qwen3.5-4B | 2wik | std | comp | both_start | -1 | 40 | -22 | 0.95 | 0.95 | +0.00 |
| Qwen3.5-4B | 2wik | std | comp | hop1 | -1 | 16 | -68 | 0.88 | 0.94 | -0.06 |
| Qwen3.5-4B | 2wik | std | comp | hop1 | 0 | 12 | -23 | 0.83 | 0.92 | -0.08 |
| Qwen3.5-4B | 2wik | std | comp | hop1 | 100 | 19 | -65 | 0.89 | 0.95 | -0.05 |
| Qwen3.5-4B | 2wik | std | comp | hop1 | 25 | 42 | -142 | 0.83 | 0.98 | -0.14 |
| Qwen3.5-4B | 2wik | std | comp | hop1 | 50 | 37 | -123 | 0.86 | 0.95 | -0.08 |
| Qwen3.5-4B | 2wik | std | comp | hop2 | 25 | 28 | -18 | 1.00 | 1.00 | +0.00 |
| Qwen3.5-4B | 2wik | std | comp | hop2 | 50 | 28 | -18 | 1.00 | 1.00 | +0.00 |
| Qwen3.5-4B | 2wik | std | comp | hop2_start | -1 | 7 | -12 | 0.86 | 0.86 | +0.00 |
| Qwen3.5-4B | hotp | std | brid | hop1 | 0 | 14 | -26 | 0.50 | 0.57 | -0.07 |
| Qwen3.5-4B | hotp | std | brid | hop1 | 100 | 5 | -14 | 0.60 | 0.80 | -0.20 |
| Qwen3.5-4B | hotp | std | brid | hop1 | 25 | 8 | 1 | 0.62 | 0.62 | +0.00 |
| Qwen3.5-4B | hotp | std | brid | hop1 | 50 | 6 | 26 | 0.50 | 0.50 | +0.00 |
| Qwen3.5-4B | hotp | std | comp | both_start | -1 | 24 | -12 | 0.79 | 0.83 | -0.04 |
| Qwen3.5-4B | hotp | std | comp | hop1 | -1 | 16 | -113 | 0.56 | 0.88 | -0.31 |
| Qwen3.5-4B | hotp | std | comp | hop1 | 0 | 10 | -69 | 0.90 | 0.90 | +0.00 |
| Qwen3.5-4B | hotp | std | comp | hop1 | 100 | 15 | -118 | 0.60 | 0.93 | -0.33 |
| Qwen3.5-4B | hotp | std | comp | hop1 | 25 | 23 | -164 | 0.70 | 0.78 | -0.09 |
| Qwen3.5-4B | hotp | std | comp | hop1 | 50 | 28 | -119 | 0.64 | 0.82 | -0.18 |
| Qwen3.5-4B | hotp | std | comp | hop2 | 25 | 24 | -58 | 0.79 | 0.83 | -0.04 |
| Qwen3.5-4B | hotp | std | comp | hop2 | 50 | 24 | -58 | 0.79 | 0.83 | -0.04 |
| Qwen3.5-4B | hotp | std | comp | hop2_start | -1 | 8 | -88 | 0.62 | 0.75 | -0.12 |

## baseline 状态率(协议健康度)

| model | dataset | mode | n | ok | degen | forced |
|---|---|---|---|---|---|---|
| Qwen3-4B | hotpot | std | 120 | 0.92 | 0.03 | 0.05 |
| Qwen3-8B | 2wiki | std | 120 | 0.96 | 0.01 | 0.03 |
| Qwen3-8B | hotpot | npm | 120 | 0.95 | 0.00 | 0.05 |
| Qwen3-8B | hotpot | std | 240 | 0.94 | 0.00 | 0.06 |
| Qwen3-8B | hotpot | wrg | 120 | 0.94 | 0.01 | 0.05 |
| Qwen3.5-4B | 2wiki | std | 120 | 0.56 | 0.37 | 0.07 |
| Qwen3.5-4B | hotpot | std | 240 | 0.40 | 0.48 | 0.12 |
