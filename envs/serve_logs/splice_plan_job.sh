#!/bin/bash
# 拼回八臂的 plan 重跑:先 16 条 smoke + 新字段自检,过了才放全量。
# 用法: splice_plan_job.sh <gpu_idx>   (tokyo105/106 任一空 A6000)
# θ=0.925 与旧 th0925 同点、cgen greedy,gen_call 应与旧 plan 逐字复现;
# 新增的只有 pred_id/pred_label/gen_min_p 三个字段。
set -e
cd /home/y-guo/reproduce/new1
export CUDA_VISIBLE_DEVICES="$1"
PY=./cprobe-env/bin/python
ARGS="--ctool-run pipeline/runs/c1_gptoss_ctool \
 --cgen-run pipeline/runs/c1_gptoss_cgen \
 --data pipeline/data/aw_official_v1/gptoss \
 --traj-root envs/runs/w0_aw_official/appworld_gptoss \
 --miss-policy skip --theta 0.925"

$PY pipeline/inject/replay_inject.py plan $ARGS --limit 16 \
  --out pipeline/inject/runs/smoke_splice_plan

$PY - <<'EOF'
import json
rows = [json.loads(l)
        for l in open('pipeline/inject/runs/smoke_splice_plan/plan.jsonl')]
assert rows, 'smoke plan 空'
missing = [k for k in ('pred_id', 'pred_label', 'gen_min_p')
           if k not in rows[0]]
assert not missing, f'新字段缺 {missing}'
# 上帝视角红线自检:pred_label 是探针预测,必须与 tool_ok 严格互推
bad = [r['event'] for r in rows
       if (r['pred_label'] == r['label']) != r['tool_ok']]
assert not bad, f'pred_label 与 tool_ok 对不上: {bad[:5]}'
n = sum(1 for r in rows if r['gen_min_p'] is not None)
print('SMOKE_FIELDS_OK', len(rows), 'gen_min_p_nonnull', n)
EOF

$PY pipeline/inject/replay_inject.py plan $ARGS \
  --out pipeline/inject/runs/aw_gptoss_splice_th0925
echo PLAN_STAGE_DONE
