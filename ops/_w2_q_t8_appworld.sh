#!/bin/bash
# 第二轮评测批 队列 A:T8 因果探针回放 appworld 两底座(tokyo105 g0,串行,失败不中断)
WD=/home/y-guo/reproduce/new1
PY=$WD/cprobe-env/bin/python
LOG=$WD/logs/new1_q_t8a_t105g0.log
export CUDA_VISIBLE_DEVICES=0
cd $WD || exit 1

for RUN in appworld_v3_causal_lfm appworld_v3_causal_qwen; do
  echo "=== JOB $RUN START $(date -Is)" >> $LOG
  $PY $WD/envs/bert/eval_replay_causal.py --env appworld \
    --run $WD/envs/bert_runs/$RUN >> $LOG 2>&1
  echo "=== JOB $RUN EXIT $?  $(date -Is)" >> $LOG
done
echo "=== QUEUE DONE $(date -Is)" >> $LOG
