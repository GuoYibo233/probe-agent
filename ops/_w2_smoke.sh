#!/bin/bash
# 第二轮评测批 smoke:tokyo105 g5,三条串行,失败不中断(用 ; 而非 &&)
WD=/home/y-guo/reproduce/new1
CP=$WD/cprobe-env/bin/python
MB=$WD/mbert-env/bin/python
LOG=$WD/logs/new1_smoke_w2_t105g5.log
export CUDA_VISIBLE_DEVICES=5
cd $WD || exit 1

echo "=== SMOKE 0 T8 appworld lfm START $(date -Is)" >> $LOG
$CP $WD/envs/bert/eval_replay_causal.py --env appworld \
  --run $WD/envs/bert_runs/_smoke_t8/appworld_lfm --smoke >> $LOG 2>&1
echo "=== SMOKE 0 EXIT $?" >> $LOG

echo "=== SMOKE 1 T8 tales qwen8k START $(date -Is)" >> $LOG
$CP $WD/envs/bert/eval_replay_causal.py --env tales \
  --run $WD/envs/bert_runs/_smoke_t8/tales_qwen8k --smoke >> $LOG 2>&1
echo "=== SMOKE 1 EXIT $?" >> $LOG

echo "=== SMOKE 2 T7 bfcl extract limit20 START $(date -Is)" >> $LOG
$MB $WD/envs/bert/eval_extract.py --env bfcl \
  --run $WD/envs/bert_runs/bfcl_v3 \
  --extractor $WD/envs/bert_runs/_smoke_t7/bfcl_ext --risk 0.05 --limit 20 >> $LOG 2>&1
echo "=== SMOKE 2 EXIT $?" >> $LOG

echo "=== ALLDONE $(date -Is)" >> $LOG
