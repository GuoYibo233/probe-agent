#!/bin/bash
set -e
tmux new-session -d -s ro1aw_q35_mext_smoke /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q35_mext_smoke.sh
ssh tokyo106 'tmux new-session -d -s ro1aw_q35_cgen_smoke /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q35_cgen_smoke.sh'
ssh tokyo107 'tmux new-session -d -s ro1bf_q35_mext_smoke /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q35_mext_smoke.sh'
ssh tokyo106 'tmux new-session -d -s ro1bf_q35_cgen_smoke /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q35_cgen_smoke.sh'
echo SMOKE4-LAUNCHED
