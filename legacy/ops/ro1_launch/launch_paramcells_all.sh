#!/bin/bash
set -e
tmux new-session -d -s ro1aw_q35_mext /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q35_mext.sh
ssh tokyo107 'tmux new-session -d -s ro1aw_q36_mext /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q36_mext.sh'
ssh tokyo107 'tmux new-session -d -s ro1aw_gptoss_mext /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_gptoss_mext.sh'
ssh tokyo107 'tmux new-session -d -s ro1bf_q35_mext /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q35_mext.sh'
ssh tokyo106 'tmux new-session -d -s ro1bf_q36_mext /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q36_mext.sh'
ssh tokyo106 'tmux new-session -d -s ro1bf_gptoss_mext /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_gptoss_mext.sh'
ssh tokyo108 'tmux new-session -d -s ro1aw_q35_cgen /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q35_cgen.sh'
ssh tokyo108 'tmux new-session -d -s ro1aw_q36_cgen /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q36_cgen.sh'
ssh tokyo108 'tmux new-session -d -s ro1bf_q35_cgen /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q35_cgen.sh'
ssh tokyo108 'tmux new-session -d -s ro1bf_q36_cgen /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q36_cgen.sh'
ssh tokyo108 'tmux new-session -d -s ro1aw_gptoss_cgen /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_gptoss_cgen.sh'
ssh tokyo108 'tmux new-session -d -s ro1bf_gptoss_cgen /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_gptoss_cgen.sh'
echo PARAM12-LAUNCHED
