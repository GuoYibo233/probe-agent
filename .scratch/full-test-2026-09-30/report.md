# Full-test run of 2026-09-30: results

168 test tasks, seed 42, one run per setting, gpt-oss-120b with instructions v2, history 3 rounds.
The probes are the August imports (0.6B full: ctool `train-f80df32ec8e4`, cgen `train-c01a3052dca5`; 4B LoRA: ctool `train-4bd4a2483c43`, cgen `train-9fc3053bacbb`).
Every number below is read from the run's score report, records or heartbeats; `solved` is the score report's success count over 168 tasks.

## 1. Every run

| run | key | solved | aborts | vs baseline: +/- (p) | vs no-probe: +/- (p) | tasks fired | fires | fire hit rate | steps/task | out tokens/task | hours |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | sample-c160f9b60374 | 95/168 | 0 | - | - | 0/168 | 0 | - | 20.0 | 36838 | 5.9 |
| no-probe | inject-74712990ac26 | 94/168 | 0 | +20 / -21 (1.00) | - | 0/168 | 0 | - | 20.6 | 37046 | 3.2 |
| probe 0.6B full p1_e1 theta 0.6 | inject-72c23fd46459 | 100/168 | 0 | +29 / -24 (0.58) | +25 / -19 (0.45) | 168/168 | 1942 | 42.7% | 18.9 | 32836 | 6.5 |
| probe 0.6B full p1_e1 theta 0.9 | inject-ad366c00da69 | 107/168 | 1 | +29 / -17 (0.10) | +32 / -19 (0.09) | 168/168 | 480 | 34.4% | 19.7 | 35655 | 3.2 |
| probe 0.6B full p2_e1 theta 0.6 | inject-1c7b8ffdd0ab | 96/168 | 0 | +28 / -27 (1.00) | +22 / -20 (0.88) | 168/168 | 2120 | 40.6% | 19.4 | 30462 | 3.0 |
| probe 0.6B full p2_e1 theta 0.9 | inject-80e10e89df9c | 97/168 | 0 | +32 / -30 (0.90) | +25 / -22 (0.77) | 168/168 | 574 | 23.3% | 19.8 | 32847 | 3.1 |
| probe 0.6B full p2_e2 theta 0.6 | inject-dc35488d6337 | 104/168 | 0 | +31 / -22 (0.27) | +31 / -21 (0.21) | 168/168 | 2338 | 36.9% | 20.3 | 29619 | 3.1 |
| probe 0.6B full p2_e2 theta 0.9 | inject-eda749a39d28 | 91/168 | 0 | +22 / -26 (0.67) | +20 / -23 (0.76) | 168/168 | 721 | 18.7% | 20.5 | 31052 | 3.0 |
| no-fill 0.6B full theta 0.6 | inject-ed14606424c0 | 104/168 | 0 | +29 / -20 (0.25) | +24 / -14 (0.14) | 168/168 | 2241 | 64.3% | 20.8 | 38080 | 14.7 |
| probe 4B LoRA p1_e1 theta 0.6 | inject-f5787ec9c62c | 106/168 | 0 | +29 / -18 (0.14) | +28 / -16 (0.10) | 168/168 | 2120 | 41.8% | 18.9 | 32905 | 3.7 |
| probe 4B LoRA p1_e1 theta 0.9 | inject-bab0be3ab39c | 92/168 | 0 | +21 / -24 (0.77) | +20 / -22 (0.88) | 168/168 | 635 | 35.4% | 19.9 | 34928 | 4.0 |
| probe 4B LoRA p2_e1 theta 0.6 | inject-216699c06f2f | 99/168 | 0 | +30 / -26 (0.69) | +25 / -20 (0.55) | 168/168 | 2325 | 41.5% | 19.4 | 31120 | 3.6 |
| probe 4B LoRA p2_e1 theta 0.9 | inject-792c4cf33d29 | 91/168 | 0 | +22 / -26 (0.67) | +19 / -22 (0.76) | 168/168 | 695 | 30.5% | 19.5 | 33155 | 3.8 |
| probe 4B LoRA p2_e2 theta 0.6 | inject-de47f00b28d0 | 90/168 | 0 | +22 / -27 (0.57) | +20 / -24 (0.65) | 168/168 | 2490 | 34.5% | 19.9 | 28562 | 3.3 |
| probe 4B LoRA p2_e2 theta 0.9 | inject-3415d8a5c5e8 | 88/168 | 0 | +20 / -27 (0.38) | +21 / -27 (0.47) | 168/168 | 767 | 24.3% | 19.7 | 32153 | 3.7 |
| no-fill 4B LoRA theta 0.6 | inject-65f7690bb03a | 100/168 | 0 | +22 / -17 (0.52) | +24 / -18 (0.44) | 168/168 | 2543 | 63.9% | 20.5 | 38131 | 9.7 |

`vs baseline: +a / -b (p)`: a tasks this run solved that the baseline did not, b the reverse, p the exact two-sided sign test over those a+b tasks; the same against the no-probe run. `fire hit rate`: share of fires whose predicted API name is in the code the agent executed at that step. `hours`: span of the loop heartbeats over every launch of the directory (the baseline and the three directories that first ran their 20-task probe check include the gap between the two launches).

## 2. Solved tasks, mean over runs of a group (probe arm only)

| group | mean solved of 168 (n runs, min-max) |
|---|---|
| pair 0.6B full | 99.2 (n=6, 91-107) |
| pair 4B LoRA | 94.3 (n=6, 88-106) |
| format p1_e1 | 101.2 (n=4, 92-107) |
| format p2_e1 | 95.8 (n=4, 91-99) |
| format p2_e2 | 93.2 (n=4, 88-104) |
| theta 0.6 | 99.2 (n=6, 90-106) |
| theta 0.9 | 94.3 (n=6, 88-107) |
| all probe-arm runs | 96.8 (n=12, 88-107) |
| baseline | 95 |
| no-probe | 94 |
| no-fill 0.6B full theta 0.6 | 104 |
| no-fill 4B LoRA theta 0.6 | 100 |

## 3. Tasks bucketed by how many times the probe fired in them, with the no-probe run's result on the same tasks

Each cell: tasks in the bucket, solved in this run / solved in the no-probe run. The probe fired at least once in every task of every run.

| run | 1-3 fires | 4-8 fires | 9-15 fires | 16+ fires |
|---|---|---|---|---|
| probe 0.6B full p1_e1 theta 0.6 | 2 tasks, 0 / 1 | 41 tasks, 30 / 31 | 95 tasks, 61 / 55 | 30 tasks, 9 / 7 |
| probe 0.6B full p1_e1 theta 0.9 | 125 tasks, 80 / 68 | 43 tasks, 27 / 26 | - | - |
| probe 0.6B full p2_e1 theta 0.6 | 1 tasks, 0 / 1 | 25 tasks, 20 / 18 | 96 tasks, 60 / 62 | 46 tasks, 16 / 13 |
| probe 0.6B full p2_e1 theta 0.9 | 96 tasks, 57 / 55 | 71 tasks, 39 / 39 | 1 tasks, 1 / 0 | - |
| probe 0.6B full p2_e2 theta 0.6 | 1 tasks, 0 / 1 | 20 tasks, 15 / 15 | 93 tasks, 59 / 57 | 54 tasks, 30 / 21 |
| probe 0.6B full p2_e2 theta 0.9 | 69 tasks, 37 / 38 | 92 tasks, 50 / 54 | 7 tasks, 4 / 2 | - |
| no-fill 0.6B full theta 0.6 | 1 tasks, 1 / 1 | 23 tasks, 23 / 20 | 88 tasks, 58 / 53 | 56 tasks, 22 / 20 |
| probe 4B LoRA p1_e1 theta 0.6 | 1 tasks, 0 / 0 | 31 tasks, 22 / 23 | 94 tasks, 68 / 60 | 42 tasks, 16 / 11 |
| probe 4B LoRA p1_e1 theta 0.9 | 87 tasks, 45 / 49 | 79 tasks, 46 / 44 | 2 tasks, 1 / 1 | - |
| probe 4B LoRA p2_e1 theta 0.6 | - | 22 tasks, 20 / 17 | 85 tasks, 52 / 57 | 61 tasks, 27 / 20 |
| probe 4B LoRA p2_e1 theta 0.9 | 64 tasks, 35 / 42 | 102 tasks, 56 / 52 | 1 tasks, 0 / 0 | 1 tasks, 0 / 0 |
| probe 4B LoRA p2_e2 theta 0.6 | - | 11 tasks, 8 / 10 | 87 tasks, 58 / 61 | 70 tasks, 24 / 23 |
| probe 4B LoRA p2_e2 theta 0.9 | 61 tasks, 30 / 36 | 97 tasks, 57 / 54 | 10 tasks, 1 / 4 | - |
| no-fill 4B LoRA theta 0.6 | - | 14 tasks, 12 / 13 | 78 tasks, 54 / 54 | 76 tasks, 34 / 27 |

## 4. Tasks by how many of the 14 probe-pair runs solved them

Over 14 probe-pair runs with a score.

| solved by k runs | tasks | of which baseline solved | of which no-probe solved |
|---|---|---|---|
| 0 | 13 | 0 | 0 |
| 1 | 11 | 1 | 2 |
| 2 | 8 | 3 | 1 |
| 3 | 7 | 3 | 2 |
| 4 | 9 | 2 | 1 |
| 5 | 5 | 4 | 1 |
| 6 | 12 | 4 | 5 |
| 7 | 4 | 2 | 3 |
| 8 | 11 | 6 | 4 |
| 9 | 7 | 3 | 4 |
| 10 | 13 | 7 | 9 |
| 11 | 11 | 10 | 10 |
| 12 | 12 | 9 | 9 |
| 13 | 20 | 20 | 19 |
| 14 | 25 | 21 | 24 |

## 5. Files

| run | run directory | score report |
|---|---|---|
| baseline | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/c160f9b60374 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/447fec4a995e/report.md |
| no-probe | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/74712990ac26 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/0dc3e77edb87/report.md |
| probe 0.6B full p1_e1 theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/72c23fd46459 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/879f2c59b26c/report.md |
| probe 0.6B full p1_e1 theta 0.9 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/ad366c00da69 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/08c20c746611/report.md |
| probe 0.6B full p2_e1 theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/1c7b8ffdd0ab | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/afc063b72ecd/report.md |
| probe 0.6B full p2_e1 theta 0.9 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/80e10e89df9c | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/426d4e37c7b4/report.md |
| probe 0.6B full p2_e2 theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/dc35488d6337 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/c562643a4911/report.md |
| probe 0.6B full p2_e2 theta 0.9 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/eda749a39d28 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/dac8b20dbf63/report.md |
| no-fill 0.6B full theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/ed14606424c0 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/7b4cf3204616/report.md |
| probe 4B LoRA p1_e1 theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/f5787ec9c62c | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/b0b2e33791ac/report.md |
| probe 4B LoRA p1_e1 theta 0.9 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/bab0be3ab39c | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/200423969f0a/report.md |
| probe 4B LoRA p2_e1 theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/216699c06f2f | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/4aff829c7a7e/report.md |
| probe 4B LoRA p2_e1 theta 0.9 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/792c4cf33d29 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/531120a32225/report.md |
| probe 4B LoRA p2_e2 theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/de47f00b28d0 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/c21fd916c5c2/report.md |
| probe 4B LoRA p2_e2 theta 0.9 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/3415d8a5c5e8 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/9022c71faac2/report.md |
| no-fill 4B LoRA theta 0.6 | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/inject/65f7690bb03a | /net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/score/39d0fa306660/report.md |

Registry: `jobs/runs.jsonl` and `jobs/RESULTS.md`; queue logs: `.scratch/full-test-2026-09-30/queue-logs/`.
