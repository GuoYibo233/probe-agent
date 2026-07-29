
## Qwen/Qwen3-1.7B
- baseline: n=60, 发起调用 60, 未调用(幻觉/直答) 0
- baseline(有调用): acc=1.00, mean gen_tokens=26, mean tokens_to_call=16

| cond | offset | n | mean saved tok | call-skip | acc |
|---|---|---|---|---|---|
| inject | start | 60 | +3 | 1.00 | 1.00 |
| inject | 0 | 60 | +0 | 1.00 | 1.00 |
| inject | 25 | 60 | +3 | 1.00 | 1.00 |
| inject | 50 | 60 | +3 | 1.00 | 1.00 |
| inject | 100 | 60 | +3 | 1.00 | 1.00 |
| inject | 200 | 60 | +3 | 1.00 | 1.00 |
| inject_wrong | 50 | 60 | +4 | 1.00 | 0.00 |

## Qwen/Qwen3-4B
- baseline: n=60, 发起调用 44, 未调用(幻觉/直答) 16
- baseline(有调用): acc=0.98, mean gen_tokens=255, mean tokens_to_call=235

| cond | offset | n | mean saved tok | call-skip | acc |
|---|---|---|---|---|---|
| inject | start | 44 | +232 | 1.00 | 1.00 |
| inject | 0 | 44 | -3 | 1.00 | 1.00 |
| inject | 25 | 44 | -24 | 0.91 | 0.89 |
| inject | 50 | 44 | -16 | 0.86 | 0.91 |
| inject | 100 | 44 | +30 | 0.93 | 0.98 |
| inject | 200 | 44 | +132 | 0.93 | 0.91 |
| inject_wrong | 50 | 44 | -33 | 0.86 | 0.14 |

## Qwen/Qwen3-8B
- baseline: n=60, 发起调用 55, 未调用(幻觉/直答) 5
- baseline(有调用): acc=1.00, mean gen_tokens=230, mean tokens_to_call=215

| cond | offset | n | mean saved tok | call-skip | acc |
|---|---|---|---|---|---|
| inject | start | 55 | +208 | 1.00 | 1.00 |
| inject | 0 | 55 | -3 | 1.00 | 1.00 |
| inject | 25 | 55 | -15 | 0.93 | 0.89 |
| inject | 50 | 55 | -23 | 0.93 | 0.84 |
| inject | 100 | 55 | +38 | 0.95 | 0.89 |
| inject | 200 | 55 | +141 | 1.00 | 0.95 |
| inject_wrong | 50 | 55 | -11 | 0.91 | 0.09 |

## Qwen/Qwen3.5-4B
- baseline: n=60, 发起调用 43, 未调用(幻觉/直答) 17
- baseline(有调用): acc=0.98, mean gen_tokens=106, mean tokens_to_call=91

| cond | offset | n | mean saved tok | call-skip | acc |
|---|---|---|---|---|---|
| inject | start | 43 | +86 | 1.00 | 0.98 |
| inject | 0 | 43 | +1 | 1.00 | 1.00 |
| inject | 25 | 43 | +7 | 0.95 | 0.91 |
| inject | 50 | 43 | +29 | 1.00 | 0.79 |
| inject | 100 | 43 | +69 | 1.00 | 0.95 |
| inject | 200 | 43 | +85 | 1.00 | 0.98 |
| inject_wrong | 50 | 43 | +30 | 0.98 | 0.02 |

## Qwen/Qwen3.5-9B
- baseline: n=60, 发起调用 5, 未调用(幻觉/直答) 55
- baseline(有调用): acc=1.00, mean gen_tokens=611, mean tokens_to_call=596

| cond | offset | n | mean saved tok | call-skip | acc |
|---|---|---|---|---|---|
| inject | start | 5 | +599 | 1.00 | 1.00 |
| inject | 0 | 5 | +0 | 1.00 | 1.00 |
| inject | 25 | 5 | -376 | 0.80 | 0.60 |
| inject | 50 | 5 | -745 | 0.40 | 0.60 |
| inject | 100 | 5 | -496 | 0.60 | 0.60 |
| inject | 200 | 5 | -926 | 0.60 | 0.40 |
| inject_wrong | 50 | 5 | -501 | 0.60 | 0.40 |
