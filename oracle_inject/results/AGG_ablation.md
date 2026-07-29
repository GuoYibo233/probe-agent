
## Qwen/Qwen3.5-4B
- baseline: n=60, 发起调用 60, 未调用(幻觉/直答) 0
- baseline(有调用): acc=0.95, mean gen_tokens=144, mean tokens_to_call=128

| cond | offset | n | mean saved tok | call-skip | acc |
|---|---|---|---|---|---|
| inject | start | 60 | -1056 | 1.00 | 0.00 |
| inject | 0 | 60 | -1 | 1.00 | 1.00 |
| inject | 25 | 60 | -15 | 0.52 | 0.72 |
| inject | 50 | 60 | -59 | 0.80 | 0.82 |
| inject | 100 | 60 | -644 | 0.93 | 0.35 |
| inject | 200 | 60 | -863 | 0.97 | 0.17 |
| inject_wrong | 50 | 60 | -77 | 0.82 | 0.13 |
