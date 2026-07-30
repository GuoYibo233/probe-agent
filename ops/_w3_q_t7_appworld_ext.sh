#!/bin/bash
# T7 抽取头触发时刻评测:appworld_ext_v3 (tokyo105 g7,先 smoke 后全量)
# 注:risk=0.05 在 appworld_v3 分类头上不可行(chosen_theta {'0.1':0.975,'0.05':None}),
#     smoke 已实测报错退出;改用该分类头唯一可行的 risk=0.1 (θ=0.975)。
WD=/home/y-guo/reproduce/new1
PY=$WD/mbert-env/bin/python
LOG=$WD/logs/bert_t7_extractor_appworld_t105g7.log
export CUDA_VISIBLE_DEVICES=7
cd $WD || exit 1

echo "=== SMOKE limit=20 risk0.1 START $(date -Is)" >> $LOG
$PY $WD/envs/bert/eval_extract.py --env appworld \
  --run $WD/envs/bert_runs/appworld_v3 \
  --extractor $WD/envs/bert_runs/appworld_ext_v3 --risk 0.1 --limit 20 >> $LOG 2>&1
SM=$?
echo "=== SMOKE EXIT $SM  $(date -Is)" >> $LOG
if [ $SM -ne 0 ]; then
  echo "=== SMOKE FAILED, ABORT $(date -Is)" >> $LOG
  exit 1
fi

echo "=== JOB T7 appworld extract risk0.1 START $(date -Is)" >> $LOG
$PY $WD/envs/bert/eval_extract.py --env appworld \
  --run $WD/envs/bert_runs/appworld_v3 \
  --extractor $WD/envs/bert_runs/appworld_ext_v3 --risk 0.1 >> $LOG 2>&1
echo "=== JOB T7 EXIT $?  $(date -Is)" >> $LOG
echo "=== QUEUE DONE $(date -Is)" >> $LOG
