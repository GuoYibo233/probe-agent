#!/bin/bash
set -e
tmux new-session -d -s ro1aw_q35_mtool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q35_mtool.sh
tmux new-session -d -s ro1aw_q35_ctool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q35_ctool.sh
tmux new-session -d -s ro1aw_q36_mtool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q36_mtool.sh
tmux new-session -d -s ro1aw_q36_ctool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_q36_ctool.sh
tmux new-session -d -s ro1aw_gptoss_mtool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_gptoss_mtool.sh
tmux new-session -d -s ro1aw_gptoss_ctool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1aw_gptoss_ctool.sh
tmux new-session -d -s ro1bf_gptoss_ctool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_gptoss_ctool.sh
ssh tokyo107 'tmux new-session -d -s ro1bf_q35_mtool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q35_mtool.sh'
ssh tokyo107 'tmux new-session -d -s ro1bf_q35_ctool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q35_ctool.sh'
ssh tokyo107 'tmux new-session -d -s ro1bf_q36_mtool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q36_mtool.sh'
ssh tokyo107 'tmux new-session -d -s ro1bf_q36_ctool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_q36_ctool.sh'
ssh tokyo106 'tmux new-session -d -s ro1bf_gptoss_mtool /home/y-guo/reproduce/new1/ops/ro1_launch/run_ro1bf_gptoss_mtool.sh'
echo LAUNCHED-ALL-12
