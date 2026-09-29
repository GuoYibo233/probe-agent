# The 40-minute monitor, run on tokyo108

Why on the host: the desktop session runs on yebis, outside the cluster
network, and dies with the laptop. A Claude Code session inside tmux on
tokyo108 keeps running, reads `run.py ls` in place, and shares the repo,
skills, memory and login through the NFS home.

## Start it (once)

```bash
ssh tokyo108
tmux new -s monitor
cd /home/y-guo/reproduce/new1
claude
```

Pick a permission mode that lets it run read-only Bash (the monitor agent
only reads: `run.py ls`, logs, heartbeat files). Then paste one line:

```
/loop 40m Dispatch the job-monitor agent with model opus. It reads `external/probe-env/bin/python run.py ls inject`, `run.py ls train_probe` and `run.py ls baseline` (no --debug), and for every open run reports: status, progress, measured rate, ETA from that rate, heartbeat age, and each piece's verdict (dead, suspected stall, not started, escalated). It reads the piece log of any dead or stalled piece and quotes the failing line. It kills nothing and launches nothing. Write the report to .scratch/inject-sweep/monitor/<YYYY-MM-DD-HHMM>.md (create the directory if missing) with the problems first, then the healthy runs in one table, then the recommended action for each problem. If nothing is open, write one line saying so.
```

Detach with `Ctrl-b d`; reattach with `tmux attach -t monitor`. Stop the loop
by typing `/loop stop` in that session or by killing the tmux session.

## Reading it from anywhere

The reports are files under `.scratch/inject-sweep/monitor/`, newest last.
The desktop session (or any other) reads them; nothing has to be forwarded.
Acting on a problem (kill, refire, retry, a new queue launch) stays with the
main conversation and goes through the gpu-run skill.
