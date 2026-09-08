#!/bin/bash
# Rerun of the plan for the eight arms spliced back together: 16-sample smoke test + new-field self-check first, full run only after it passes.
# Usage: splice_plan_job.sh <gpu_idx>   (any free A6000 on tokyo105/106)
# θ=0.925 matches the old th0925 point, cgen greedy; gen_call should reproduce the old plan byte-for-byte;
# the only additions are the three fields pred_id/pred_label/gen_min_p.
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
assert rows, 'smoke plan empty'
missing = [k for k in ('pred_id', 'pred_label', 'gen_min_p')
           if k not in rows[0]]
assert not missing, f'missing new fields {missing}'
# God's-eye redline self-check: pred_label is the probe's prediction, and it must strictly cross-imply tool_ok
bad = [r['event'] for r in rows
       if (r['pred_label'] == r['label']) != r['tool_ok']]
assert not bad, f'pred_label does not match tool_ok: {bad[:5]}'
n = sum(1 for r in rows if r['gen_min_p'] is not None)
print('SMOKE_FIELDS_OK', len(rows), 'gen_min_p_nonnull', n)
EOF

$PY pipeline/inject/replay_inject.py plan $ARGS \
  --out pipeline/inject/runs/aw_gptoss_splice_th0925
echo PLAN_STAGE_DONE
