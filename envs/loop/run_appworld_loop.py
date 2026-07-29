"""AppWorld 闭环 runner:collect/run_appworld.py 的探针版(T9 环境接入层)。

口径 --mode:baseline(阻塞,总账下限)/shadow(只记不动)/truncate(首触断流
提交合成调用)/fork(shadow 生成+触发步复制现场跑分支,分支内探针关闭)。
fork 机制 = 动作史重放:新开 AppWorld 实例(experiment_name 加 _forkN,
防实验目录互踩)逐条重放已执行代码块 —— 我们全程录动作,重放即现场复制。

题干/历史构造与 build_dataset.jsonl_events(appworld 分支)逐条对齐:
task=instruction,hist=(代码块原文, 环境输出[:4000]),按步追加。

用法(appworld venv;两服务已起:vLLM + probe_server):
  venv/bin/python ../loop/run_appworld_loop.py --base-url http://H:8107/v1 \
      --model <vllm模型id> --split dev --n 1 --outdir ../loop/runs/aw_demo \
      --mode shadow --probe-url http://H:8201 --theta <appworld_v3 的θ>
"""

import argparse
import os
import re
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(LOOP.parent / "collect"))
from accounting import EpisodeLedger, tokenize_count  # noqa: E402
from probe_client import ProbeClient, ProbeMonitor  # noqa: E402
from stream_chat import StreamingChat  # noqa: E402
from common import Chat  # noqa: E402
from run_appworld import CODE_RE, SYSTEM  # noqa: E402

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")  # 与 build_dataset 同源


def synth_code(label):
    """占位参数产线:label='apis.app.api' → 零参调用。T7 就位后替换。"""
    return f"```python\nprint({label}())\n```"


def gen_step(chat, msgs, mon, base_url, model):
    """一步生成:流式+monitor。返回 (g, hit)。"""
    hit_box = []

    def on_think(raw):
        h = mon.feed(raw.lstrip())
        if h:
            hit_box.append(h)
            return "abort"
        return None

    g = chat(msgs, on_think=on_think if mon else None)
    if not g["aborted"] and mon:
        mon.feed(g["reasoning"].strip())
        mon.finalize()
    if g["aborted"] and g["usage"]["out"] is None:
        g["usage"]["out"] = tokenize_count(base_url, model, g["raw"])
        g["usage"]["in"] = 0
    return g, (hit_box[0] if hit_box else None)


def run_episode(world, instr, chat, args, ledger, probe, mode,
                start_msgs=None, start_hist=None, start_step=0,
                fork_budget=0, fork_ctx=None):
    """跑一集(或 fork 分支的后半集)。返回 (completed, actions)。
    fork_ctx: (task_id, 已执行动作史, 分支序号计数 list) —— 仅 fork 口径用。"""
    msgs = start_msgs if start_msgs is not None else [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Task from supervisor: {instr}"}]
    hist = list(start_hist or [])
    actions = []
    completed = False
    for step in range(start_step, args.max_steps):
        mon = None
        if mode != "baseline" and probe is not None:
            mon = ProbeMonitor(
                probe, args.theta,
                "truncate" if mode == "truncate" else "shadow",
                instr, hist, f"{ledger.path.stem}|s{step}",
                sink=ledger.probe)
        g, hit = gen_step(chat, msgs, mon, args.base_url, args.model)
        ledger.gen(step, g)

        if hit:  # truncate:合成调用顶替正文
            content = synth_code(hit["label"])
            ledger.trigger(step, dict(hit, truncated=True))
        else:
            content = g["content"]
            if mon and mon.first_trigger:
                m = AW_CALL.search(content)
                actual = f"apis.{m.group(1)}.{m.group(2)}" if m else None
                ledger.trigger(step, dict(mon.first_trigger, truncated=False),
                               agent_actual=actual,
                               match=(actual == mon.first_trigger["label"]))
                if (mode == "fork" and fork_ctx is not None
                        and fork_ctx[2][0] < fork_budget):
                    fork_ctx[2][0] += 1
                    _run_fork(args, ledger, mon.first_trigger,
                              g["reasoning"].strip(), msgs, hist, step,
                              actions, fork_ctx)

        msgs.append({"role": "assistant", "content": content})
        m = CODE_RE.search(content)
        if not m:
            msgs.append({"role": "user", "content":
                         "No ```python``` block found. Reply with exactly "
                         "one python code block."})
            continue
        code = m.group(1)
        out = str(world.execute(code))
        actions.append(code)
        hist.append((code, out[:4000]))
        ledger.env_step(step, code, out)
        msgs.append({"role": "user",
                     "content": f"Execution output:\n{out[:4000]}"})
        if world.task_completed():
            completed = True
            break
    return completed, actions


def _run_fork(args, parent_ledger, trig, think, msgs, hist, step,
              actions, fork_ctx):
    """动作史重放式 fork:新实例重放已执行代码,分支从截断点走到底,探针关。"""
    from appworld import AppWorld
    task_id, _, counter = fork_ctx
    n = counter[0]
    exp = f"{args.exp}_fork{n}"
    led = EpisodeLedger(
        parent_ledger.path.with_name(
            parent_ledger.path.stem + f"_fork{n}.jsonl"),
        {"task_id": task_id, "mode": "fork_branch", "parent_step": step,
         "trigger": trig})
    prefix = think[:trig["at_char"]]
    prefix_tok = tokenize_count(args.base_url, args.model, prefix)
    led.gen(f"fork_s{step}", {"usage": {"in": 0, "out": prefix_tok},
                              "wall_s": 0.0, "aborted": True,
                              "reasoning": prefix})
    with AppWorld(task_id=task_id, experiment_name=exp) as w2:
        for code in actions:               # 现场复制=重放动作史
            w2.execute(code)
        bmsgs = [dict(m) for m in msgs]
        bmsgs.append({"role": "assistant", "content": synth_code(trig["label"])})
        bhist = list(hist)
        # 分支第 0 步:执行合成调用
        m = CODE_RE.search(synth_code(trig["label"]))
        code = m.group(1)
        out = str(w2.execute(code))
        bhist.append((code, out[:4000]))
        led.env_step(step, code, out)
        bmsgs.append({"role": "user",
                      "content": f"Execution output:\n{out[:4000]}"})
        chat = StreamingChat(args.base_url, args.model)
        done, _ = run_episode(w2, "", chat, args, led, probe=None,
                              mode="baseline", start_msgs=bmsgs,
                              start_hist=bhist, start_step=step + 1)
        try:
            ev = str(w2.evaluate())[:600]
        except Exception as e:
            ev = f"eval_error: {e}"
    led.close(success=done, eval=ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--task-ids", default=None, help="逗号分隔,给了就不看 --n")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", default="loop_demo")
    ap.add_argument("--mode", default="shadow",
                    choices=["baseline", "shadow", "truncate", "fork"])
    ap.add_argument("--probe-url", default="http://127.0.0.1:8201")
    ap.add_argument("--theta", type=float, required=True)
    ap.add_argument("--fork-max", type=int, default=1)
    args = ap.parse_args()

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    os.chdir("/home/y-guo/reproduce/new1/envs/appworld")
    from appworld import AppWorld, load_task_ids

    probe = ProbeClient(args.probe_url) if args.mode != "baseline" else None
    chat = StreamingChat(args.base_url, args.model)
    ids = (args.task_ids.split(",") if args.task_ids
           else load_task_ids(args.split)[: args.n])

    for tid in ids:
        with AppWorld(task_id=tid, experiment_name=args.exp) as world:
            instr = world.task.instruction
            led = EpisodeLedger(
                outdir / f"appworld_{tid}_{args.mode}.jsonl",
                {"env": "appworld", "task_id": tid, "mode": args.mode,
                 "theta": args.theta, "model": args.model})
            counter = [0]
            done, _ = run_episode(
                world, instr, chat, args, led, probe, args.mode,
                fork_budget=args.fork_max, fork_ctx=(tid, None, counter))
            try:
                ev = str(world.evaluate())[:600]
            except Exception as e:
                ev = f"eval_error: {e}"
            led.close(success=done, eval=ev, n_forks=counter[0])
            print(f"task={tid} mode={args.mode} done={done} "
                  f"forks={counter[0]} eval={ev[:100]}", flush=True)


if __name__ == "__main__":
    main()
