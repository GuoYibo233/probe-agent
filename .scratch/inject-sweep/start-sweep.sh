#!/usr/bin/env bash
# The hand-off sequence of the 2026-09-29 inject sweep, run in tmux on tokyo108 so
# that it survives the desktop session. Every launch goes through run.py.
#   1. wait for the real 20-task baseline sample (sample-21c9079f0c45) to finish
#   2. wrap it up (done.json, teardown, score)
#   3. walk the eight imported probes (train = import, on tokyo105/106 cards)
#   4. walk them again (the imported evals)
#   5. commit the registry rows
#   6. start the three queues, each in its own tmux session
set -uo pipefail
cd /home/y-guo/reproduce/new1
PY=external/probe-env/bin/python
LOG=.scratch/inject-sweep/queue-logs/start-sweep.log
mkdir -p .scratch/inject-sweep/queue-logs
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

SAMPLE=/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/outputs/sample/21c9079f0c45
IMPORTS="imp_ctool_0pt6b_full imp_cgen_0pt6b_full imp_ctool_1pt7b_full imp_cgen_1pt7b_full imp_ctool_1pt7b_lora imp_cgen_1pt7b_lora imp_ctool_4b_lora imp_cgen_4b_lora"

loop_done() {
  local nd=0 p s
  for p in 0 1 2 3 4 5; do
    s=$(tail -1 "$SAMPLE/heartbeat/$p-0.jsonl" 2>/dev/null | python3 -c 'import sys,json;r=json.loads(sys.stdin.read() or "{}");print(r.get("status") or "")' 2>/dev/null)
    [ "$s" = "done" ] && nd=$((nd+1))
  done
  [ $nd = 6 ]
}

log "step 1: waiting for the baseline sample"
until loop_done; do sleep 60; done
log "sample loop pieces done"

log "step 2: baseline wrap-up"
$PY run.py baseline gpt_oss_120b_appworld_t20 --cards tokyo108:5 2>&1 | grep -v '^@hb' | tee -a "$LOG"

log "step 3: imports"
$PY run.py train_probe $IMPORTS --cards tokyo105:1,2,3,4 --cards tokyo106:0,1,2,3 2>&1 | grep -v '^@hb' | tee -a "$LOG"
log "waiting for the eight import pieces"
for i in $(seq 1 60); do
  n=0
  for s in $IMPORTS; do
    d=$($PY run.py where train_probe $s train 2>/dev/null | tail -1)
    [ -f "$d/done.json" ] && n=$((n+1))
  done
  log "imports done: $n/8"
  [ $n = 8 ] && break
  sleep 60
done

log "step 4: imported evals"
$PY run.py train_probe $IMPORTS --cards tokyo105:1,2,3,4 --cards tokyo106:0,1,2,3 2>&1 | grep -v '^@hb' | tee -a "$LOG"

log "step 5: commit the registry rows"
git add jobs/runs.jsonl jobs/RESULTS.md && git commit -q -m "20-task baseline sample-21c9079f0c45 and its score; the eight imported probes (train = import) and their imported evals

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && log "committed $(git log --oneline -1)"

log "step 6: start the queues"
Q=.scratch/inject-sweep/queue.py
C=.scratch/inject-sweep/children
H=tokyo105,tokyo107,tokyo106
tmux new-session -d -s queue-108-5 "cd /home/y-guo/reproduce/new1 && python3 $Q --server tokyo108:5 --probe-hosts $H --slots 2 --children $C/queue-108-5.txt; sleep 3600"
tmux new-session -d -s queue-108-0 "cd /home/y-guo/reproduce/new1 && python3 $Q --server tokyo108:0 --probe-hosts $H --slots 1 --children $C/queue-108-0.txt; sleep 3600"
tmux new-session -d -s queue-108-2 "cd /home/y-guo/reproduce/new1 && python3 $Q --server tokyo108:2 --probe-hosts $H --slots 1 --children $C/queue-108-2.txt; sleep 3600"
log "queues started: $(tmux ls | grep -c queue-108) sessions; logs under .scratch/inject-sweep/queue-logs/"
