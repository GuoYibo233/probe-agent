#!/bin/bash
# 第二轮评测批 队列 C:T6 bfcl gptoss 侧三格 + T7 抽取头触发时刻(tokyo105 g2,串行,失败不中断)
# T6 顺序:主场(最小,当队首 smoke) -> 冷迁移 -> 只换校准
WD=/home/y-guo/reproduce/new1
PY=$WD/mbert-env/bin/python
LOG=$WD/logs/new1_q_t67_t105g2.log
export CUDA_VISIBLE_DEVICES=2
cd $WD || exit 1

for D in eval-gptoss_cal-gptoss eval-qwen_cal-gptoss eval-qwen_cal-qwen; do
  echo "=== JOB T6 bfcl_v3_xgptoss x $D START $(date -Is)" >> $LOG
  $PY $WD/envs/bert/eval_replay.py --env bfcl \
    --run $WD/envs/bert_runs/xmodel/bfcl_v3_xgptoss__$D \
    --data $WD/envs/bert_data/v3_1_xmodel/$D >> $LOG 2>&1
  echo "=== JOB T6 $D EXIT $?  $(date -Is)" >> $LOG
done

echo "=== JOB T7 bfcl extract risk0.05 START $(date -Is)" >> $LOG
$PY $WD/envs/bert/eval_extract.py --env bfcl \
  --run $WD/envs/bert_runs/bfcl_v3 \
  --extractor $WD/envs/bert_runs/bfcl_ext_v3 --risk 0.05 >> $LOG 2>&1
echo "=== JOB T7 EXIT $?  $(date -Is)" >> $LOG

echo "=== QUEUE DONE $(date -Is)" >> $LOG
