# Full-test run of 2026-09-30: results

168 test tasks, seed 42, one run per setting, gpt-oss-120b with instructions v2, history 3 rounds.
The probes are the August imports (0.6B full: ctool `train-f80df32ec8e4`, cgen `train-c01a3052dca5`; 4B LoRA: ctool `train-4bd4a2483c43`, cgen `train-9fc3053bacbb`).
Every number below is read from the run's score report, records or heartbeats; `solved` is the score report's success count over 168 tasks.

**Unfinished runs (numbers below are partial for them):** no-fill 0.6B full theta 0.6 (117/168 records)

## 1. Every run

| run | key | solved | aborts | vs baseline: +/- | vs no-probe: +/- | tasks fired | fires | fire hit rate | steps/task | out tokens/task | hours |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | sample-c160f9b60374 | 95/168 | 0 | - | - | 0/168 | 0 | - | 20.0 | 36838 | 5.9 |
| no-probe | inject-74712990ac26 | 94/168 | 0 | +20 / -21 | - | 0/168 | 0 | - | 20.6 | 37046 | 3.2 |
| probe 0.6B full p1_e1 theta 0.6 | inject-72c23fd46459 | 100/168 | 0 | +29 / -24 | +25 / -19 | 168/168 | 1942 | 42.7% | 18.9 | 32836 | 6.5 |
| probe 0.6B full p1_e1 theta 0.9 | inject-ad366c00da69 | 107/168 | 1 | +29 / -17 | +32 / -19 | 168/168 | 480 | 34.4% | 19.7 | 35655 | 3.2 |
| probe 0.6B full p2_e1 theta 0.6 | inject-1c7b8ffdd0ab | 96/168 | 0 | +28 / -27 | +22 / -20 | 168/168 | 2120 | 40.6% | 19.4 | 30462 | 3.0 |
| probe 0.6B full p2_e1 theta 0.9 | inject-80e10e89df9c | 97/168 | 0 | +32 / -30 | +25 / -22 | 168/168 | 574 | 23.3% | 19.8 | 32847 | 3.1 |
| probe 0.6B full p2_e2 theta 0.6 | inject-dc35488d6337 | 104/168 | 0 | +31 / -22 | +31 / -21 | 168/168 | 2338 | 36.9% | 20.3 | 29619 | 3.1 |
| probe 0.6B full p2_e2 theta 0.9 | inject-eda749a39d28 | 91/168 | 0 | +22 / -26 | +20 / -23 | 168/168 | 721 | 18.7% | 20.5 | 31052 | 3.0 |
| no-fill 0.6B full theta 0.6 | inject-ed14606424c0 | - | - | - | - | 117/117 | 1475 | 64.8% | 19.6 | 35611 | 12.6 |
| probe 4B LoRA p1_e1 theta 0.6 | inject-f5787ec9c62c | 106/168 | 0 | +29 / -18 | +28 / -16 | 168/168 | 2120 | 41.8% | 18.9 | 32905 | 3.7 |
| probe 4B LoRA p1_e1 theta 0.9 | inject-bab0be3ab39c | 92/168 | 0 | +21 / -24 | +20 / -22 | 168/168 | 635 | 35.4% | 19.9 | 34928 | 4.0 |
| probe 4B LoRA p2_e1 theta 0.6 | inject-216699c06f2f | 99/168 | 0 | +30 / -26 | +25 / -20 | 168/168 | 2325 | 41.5% | 19.4 | 31120 | 3.6 |
| probe 4B LoRA p2_e1 theta 0.9 | inject-792c4cf33d29 | 91/168 | 0 | +22 / -26 | +19 / -22 | 168/168 | 695 | 30.5% | 19.5 | 33155 | 3.8 |
| probe 4B LoRA p2_e2 theta 0.6 | inject-de47f00b28d0 | 90/168 | 0 | +22 / -27 | +20 / -24 | 168/168 | 2490 | 34.5% | 19.9 | 28562 | 3.3 |
| probe 4B LoRA p2_e2 theta 0.9 | inject-3415d8a5c5e8 | 88/168 | 0 | +20 / -27 | +21 / -27 | 168/168 | 767 | 24.3% | 19.7 | 32153 | 3.7 |
| no-fill 4B LoRA theta 0.6 | inject-65f7690bb03a | 100/168 | 0 | +22 / -17 | +24 / -18 | 168/168 | 2543 | 63.9% | 20.5 | 38131 | 9.7 |

`vs baseline: +a / -b`: a tasks this run solved that the baseline did not, b the reverse; the same against the no-probe run. `fire hit rate`: share of fires whose predicted API name is in the code the agent executed at that step.

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
| no-fill 0.6B full theta 0.6 | - |
| no-fill 4B LoRA theta 0.6 | 100 |

## 3. Success on tasks where the probe fired at least once, against the same tasks in the no-probe run

| run | tasks fired | solved among them | no-probe solved the same tasks | tasks never fired | solved among them | no-probe solved the same tasks |
|---|---|---|---|---|---|---|
| probe 0.6B full p1_e1 theta 0.6 | 168 | 100 | 94 | 0 | 0 | 0 |
| probe 0.6B full p1_e1 theta 0.9 | 168 | 107 | 94 | 0 | 0 | 0 |
| probe 0.6B full p2_e1 theta 0.6 | 168 | 96 | 94 | 0 | 0 | 0 |
| probe 0.6B full p2_e1 theta 0.9 | 168 | 97 | 94 | 0 | 0 | 0 |
| probe 0.6B full p2_e2 theta 0.6 | 168 | 104 | 94 | 0 | 0 | 0 |
| probe 0.6B full p2_e2 theta 0.9 | 168 | 91 | 94 | 0 | 0 | 0 |
| probe 4B LoRA p1_e1 theta 0.6 | 168 | 106 | 94 | 0 | 0 | 0 |
| probe 4B LoRA p1_e1 theta 0.9 | 168 | 92 | 94 | 0 | 0 | 0 |
| probe 4B LoRA p2_e1 theta 0.6 | 168 | 99 | 94 | 0 | 0 | 0 |
| probe 4B LoRA p2_e1 theta 0.9 | 168 | 91 | 94 | 0 | 0 | 0 |
| probe 4B LoRA p2_e2 theta 0.6 | 168 | 90 | 94 | 0 | 0 | 0 |
| probe 4B LoRA p2_e2 theta 0.9 | 168 | 88 | 94 | 0 | 0 | 0 |
| no-fill 4B LoRA theta 0.6 | 168 | 100 | 94 | 0 | 0 | 0 |

## 4. Tasks by how many of the 14 probe-pair runs solved them

Over 13 probe-pair runs with a score.

| solved by k runs | tasks | of which baseline solved | of which no-probe solved |
|---|---|---|---|
| 0 | 13 | 0 | 0 |
| 1 | 11 | 1 | 2 |
| 2 | 10 | 5 | 2 |
| 3 | 7 | 1 | 1 |
| 4 | 9 | 4 | 2 |
| 5 | 9 | 5 | 2 |
| 6 | 8 | 1 | 5 |
| 7 | 11 | 6 | 5 |
| 8 | 7 | 4 | 3 |
| 9 | 11 | 4 | 7 |
| 10 | 15 | 14 | 13 |
| 11 | 12 | 9 | 9 |
| 12 | 19 | 19 | 18 |
| 13 | 26 | 22 | 25 |

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
