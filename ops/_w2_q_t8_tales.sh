#!/bin/bash
# 第二轮评测批 队列 B:T8 因果探针回放 tales 三配置(tokyo105 g1,串行,失败不中断)
# 顺序 = 从小到大:lfm(350M) -> qwen(0.6B/4096) -> qwen8k(0.6B/8192)
WD=/home/y-guo/reproduce/new1
PY=$WD/cprobe-env/bin/python
LOG=$WD/logs/new1_q_t8b_t105g1.log
export CUDA_VISIBLE_DEVICES=1
cd $WD || exit 1

for RUN in tales_v3_causal_lfm tales_v3_causal_qwen tales_v3_causal_qwen8k; do
  echo "=== JOB $RUN START $(date -Is)" >> $LOG
  $PY $WD/envs/bert/eval_replay_causal.py --env tales \
    --run $WD/envs/bert_runs/$RUN >> $LOG 2>&1
  echo "=== JOB $RUN EXIT $?  $(date -Is)" >> $LOG
done
echo "=== QUEUE DONE $(date -Is)" >> $LOG
