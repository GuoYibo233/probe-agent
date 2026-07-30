#!/bin/bash
# T6 tales gptoss 侧三格评测(tokyo105 g7,串行,失败不中断)
# 顺序:主场 -> 冷迁移 -> 只换校准
WD=/home/y-guo/reproduce/new1
PY=$WD/mbert-env/bin/python
LOG=$WD/logs/bert_t6_xgptoss_eval_tales_t105g7.log
export CUDA_VISIBLE_DEVICES=7
cd $WD || exit 1

for D in eval-gptoss_cal-gptoss eval-qwen_cal-gptoss eval-qwen_cal-qwen; do
  echo "=== JOB T6 tales_v3_xgptoss x $D START $(date -Is)" >> $LOG
  $PY $WD/envs/bert/eval_replay.py --env tales \
    --run $WD/envs/bert_runs/xmodel/tales_v3_xgptoss__$D \
    --data $WD/envs/bert_data/v3_1_xmodel/$D >> $LOG 2>&1
  echo "=== JOB T6 tales $D EXIT $?  $(date -Is)" >> $LOG
done

echo "=== QUEUE DONE $(date -Is)" >> $LOG
