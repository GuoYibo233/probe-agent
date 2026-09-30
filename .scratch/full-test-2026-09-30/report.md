# Full-test run of 2026-09-30: results

168 test tasks, seed 42, one run per setting, gpt-oss-120b with instructions v2, history 3 rounds.
The probes are the August imports (0.6B full: ctool `train-f80df32ec8e4`, cgen `train-c01a3052dca5`; 4B LoRA: ctool `train-4bd4a2483c43`, cgen `train-9fc3053bacbb`).
Every number below is read from the run's score report, records or heartbeats; `solved` is the score report's success count over 168 tasks.

**Unfinished runs (numbers below are partial for them):** probe 0.6B full p1_e1 theta 0.6 (73/168 records), probe 0.6B full p1_e1 theta 0.9 (36/168 records), probe 0.6B full p2_e1 theta 0.6 (0/168 records), probe 0.6B full p2_e1 theta 0.9 (0/168 records), probe 0.6B full p2_e2 theta 0.6 (0/168 records), probe 0.6B full p2_e2 theta 0.9 (0/168 records), no-fill 0.6B full theta 0.6 (20/168 records), probe 4B LoRA p1_e1 theta 0.6 (137/168 records), probe 4B LoRA p1_e1 theta 0.9 (0/168 records), probe 4B LoRA p2_e1 theta 0.6 (134/168 records), probe 4B LoRA p2_e1 theta 0.9 (0/168 records), probe 4B LoRA p2_e2 theta 0.6 (155/168 records), probe 4B LoRA p2_e2 theta 0.9 (0/168 records), no-fill 4B LoRA theta 0.6 (20/168 records)

## 1. Every run

| run | key | solved | aborts | vs baseline: +/- | vs no-probe: +/- | tasks fired | fires | fire hit rate | steps/task | out tokens/task | hours |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | sample-c160f9b60374 | 95/168 | 0 | - | - | 0/168 | 0 | - | 20.0 | 36838 | 5.9 |
| no-probe | inject-74712990ac26 | 94/168 | 0 | +20 / -21 | - | 0/168 | 0 | - | 20.6 | 37046 | 3.2 |
| probe 0.6B full p1_e1 theta 0.6 | inject-72c23fd46459 | - | - | - | - | 73/73 | 770 | 41.7% | 16.9 | 29882 | 4.5 |
| probe 0.6B full p1_e1 theta 0.9 | inject-ad366c00da69 | - | - | - | - | 34/36 | 95 | 30.5% | 15.6 | 26836 | 0.5 |
| probe 0.6B full p2_e1 theta 0.6 | inject-1c7b8ffdd0ab | - | - | - | - | - | - | - | - | - | - |
| probe 0.6B full p2_e1 theta 0.9 | inject-80e10e89df9c | - | - | - | - | - | - | - | - | - | - |
| probe 0.6B full p2_e2 theta 0.6 | inject-dc35488d6337 | - | - | - | - | - | - | - | - | - | - |
| probe 0.6B full p2_e2 theta 0.9 | inject-eda749a39d28 | - | - | - | - | - | - | - | - | - | - |
| no-fill 0.6B full theta 0.6 | inject-ed14606424c0 | - | - | - | - | 20/20 | 257 | 63.8% | 19.5 | 39658 | 0.5 |
| probe 4B LoRA p1_e1 theta 0.6 | inject-f5787ec9c62c | - | - | - | - | 137/137 | 1676 | 42.8% | 17.9 | 30703 | 2.7 |
| probe 4B LoRA p1_e1 theta 0.9 | inject-bab0be3ab39c | - | - | - | - | - | - | - | - | - | - |
| probe 4B LoRA p2_e1 theta 0.6 | inject-216699c06f2f | - | - | - | - | 134/134 | 1800 | 42.1% | 18.8 | 29778 | 2.7 |
| probe 4B LoRA p2_e1 theta 0.9 | inject-792c4cf33d29 | - | - | - | - | - | - | - | - | - | - |
| probe 4B LoRA p2_e2 theta 0.6 | inject-de47f00b28d0 | - | - | - | - | 154/155 | 2215 | 34.9% | 19.1 | 26365 | 2.7 |
| probe 4B LoRA p2_e2 theta 0.9 | inject-3415d8a5c5e8 | - | - | - | - | - | - | - | - | - | - |
| no-fill 4B LoRA theta 0.6 | inject-65f7690bb03a | - | - | - | - | 20/20 | 311 | 63.7% | 20.3 | 37698 | 0.4 |

`vs baseline: +a / -b`: a tasks this run solved that the baseline did not, b the reverse; the same against the no-probe run. `fire hit rate`: share of fires whose predicted API name is in the code the agent executed at that step.

## 2. Solved tasks, mean over runs of a group (probe arm only)

| group | mean solved of 168 (n runs, min-max) |
|---|---|
| pair 0.6B full | - |
| pair 4B LoRA | - |
| format p1_e1 | - |
| format p2_e1 | - |
| format p2_e2 | - |
| theta 0.6 | - |
| theta 0.9 | - |
| all probe-arm runs | - |
| baseline | 95 |
| no-probe | 94 |
| no-fill 0.6B full theta 0.6 | - |
| no-fill 4B LoRA theta 0.6 | - |

## 3. Success on tasks where the probe fired at least once, against the same tasks in the no-probe run

| run | tasks fired | solved among them | no-probe solved the same tasks | tasks never fired | solved among them | no-probe solved the same tasks |
|---|---|---|---|---|---|---|

## 4. Tasks by how many of the 14 probe-pair runs solved them


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
