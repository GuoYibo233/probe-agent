"""TALES(TextWorld-Express)闭环 runner:collect/run_tales.py 的探针版。

口径同 run_appworld_loop(baseline/shadow/truncate/fork)。fork 机制 =
TWX 官方 clone():serialize/deserialize 即"同 seed 重置+动作史重放",
deploy-scout 调研判级可行(microsoft/tale-suite,详见 DESIGN.md)。

题干/历史构造与 build_dataset.jsonl_events(tales 分支)对齐:
task=taskDescription,hist=(动作原文, 环境返回),按步追加;
标签=命令首词(动词),截断合成动作=裸动词(占位;tales 多数动词带宾语,
正确率归 T10,机械流程验证不受影响)。

用法(tales venv;两服务已起):
  venv/bin/python ../loop/run_tales_loop.py --base-url http://H:8107/v1 \
      --model <vllm模型id> --game cookingworld --seeds 7 \
      --outdir ../loop/runs/tales_demo --mode shadow \
      --probe-url http://H:8201 --theta <tales_v3 的θ>
"""

import argparse
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(LOOP.parent / "collect"))
from accounting import EpisodeLedger, tokenize_count  # noqa: E402
from probe_client import ProbeClient, ProbeMonitor  # noqa: E402
from stream_chat import StreamingChat  # noqa: E402
from run_tales import ACT_RE, SYSTEM  # noqa: E402


def synth_action(label):
    """占位:裸动词。T7 参数头就位后换(动词+宾语)。"""
    return label


class ForkedTWX:
    """TALES 壳的 self.env(原生 TWX)clone 出来的分支,step 字段语义
    补齐到与壳一致(won/score 百分制),分支只用 step。"""

    def __init__(self, raw):
        self.env = raw

    def step(self, action):
        obs, reward, done, info = self.env.step(action)
        info["won"] = info.get("tasksuccess", False)
        info["score"] = int(info.get("score", 0) * 100)
        return obs, reward, done, info


def gen_step(chat, msgs, mon, base_url, model):
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


def run_episode(env, task, chat, args, ledger, probe, mode,
                start_msgs=None, start_hist=None, start_step=0,
                fork_budget=0, fork_counter=None):
    msgs = start_msgs
    hist = list(start_hist or [])
    score, done, won = 0.0, False, False
    for step in range(start_step, args.max_steps):
        mon = None
        if mode != "baseline" and probe is not None:
            mon = ProbeMonitor(
                probe, args.theta,
                "truncate" if mode == "truncate" else "shadow",
                task, hist, f"{ledger.path.stem}|s{step}", sink=ledger.probe)
        g, hit = gen_step(chat, msgs, mon, args.base_url, args.model)
        ledger.gen(step, g)

        if hit:
            action = synth_action(hit["label"])
            content = f"ACTION: {action}"
            ledger.trigger(step, dict(hit, truncated=True))
        else:
            content = g["content"]
            m = ACT_RE.search(content)
            action = (m.group(1) if m
                      else content.strip().split("\n")[-1]).strip()
            if mon and mon.first_trigger:
                actual = action.split()[0].lower() if action.split() else None
                ledger.trigger(step, dict(mon.first_trigger, truncated=False),
                               agent_actual=actual,
                               match=(actual == mon.first_trigger["label"]))
                if (mode == "fork" and fork_counter is not None
                        and fork_counter[0] < fork_budget):
                    fork_counter[0] += 1
                    _run_fork(env, task, args, ledger, mon.first_trigger,
                              g["reasoning"].strip(), msgs, hist, step,
                              fork_counter[0])

        obs2, reward, done, si = env.step(action)
        score, won = si.get("score", score), si.get("won", False)
        hist.append((action, obs2))
        ledger.env_step(step, action, obs2, score=score)
        msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": obs2})
        if done:
            break
    return score, done, won


def _run_fork(env, task, args, parent_ledger, trig, think, msgs, hist,
              step, n):
    """TWX clone() 现场复制;分支从截断点走到底,探针关。
    clone 挂在 TALES 壳内的原生 TWX 上(壳无 clone,勘察确认可穿透)。"""
    env2 = ForkedTWX(env.env.clone())
    led = EpisodeLedger(
        parent_ledger.path.with_name(
            parent_ledger.path.stem + f"_fork{n}.jsonl"),
        {"mode": "fork_branch", "parent_step": step, "trigger": trig})
    prefix = think[:trig["at_char"]]
    prefix_tok = tokenize_count(args.base_url, args.model, prefix)
    led.gen(f"fork_s{step}", {"usage": {"in": 0, "out": prefix_tok},
                              "wall_s": 0.0, "aborted": True,
                              "reasoning": prefix})
    action = synth_action(trig["label"])
    obs2, reward, done, si = env2.step(action)
    bhist = list(hist) + [(action, obs2)]
    led.env_step(step, action, obs2, score=si.get("score"))
    bmsgs = [dict(m) for m in msgs]
    bmsgs.append({"role": "assistant", "content": f"ACTION: {action}"})
    bmsgs.append({"role": "user", "content": obs2})
    score, done2, won = (si.get("score", 0.0), done, si.get("won", False))
    if not done:
        chat = StreamingChat(args.base_url, args.model)
        score, done2, won = run_episode(
            env2, task, chat, args, led, probe=None, mode="baseline",
            start_msgs=bmsgs, start_hist=bhist, start_step=step + 1)
    led.close(success=won, score=score, done=done2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--game", default="cookingworld")
    ap.add_argument("--seeds", default="7")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--game-params", default=None)
    ap.add_argument("--mode", default="shadow",
                    choices=["baseline", "shadow", "truncate", "fork"])
    ap.add_argument("--probe-url", default="http://127.0.0.1:8201")
    ap.add_argument("--theta", type=float, required=True)
    ap.add_argument("--fork-max", type=int, default=1)
    args = ap.parse_args()

    import tales.textworld_express as twx
    from tales.textworld_express import TextWorldExpressEnv
    params = {g[1]: g[2] for g in twx.TASKS}
    if args.game_params:
        params[args.game] = args.game_params

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    probe = ProbeClient(args.probe_url) if args.mode != "baseline" else None
    chat = StreamingChat(args.base_url, args.model)

    for seed in [int(s) for s in args.seeds.split(",")]:
        env = TextWorldExpressEnv(args.game, params[args.game])
        obs, info = env.reset(seed=seed)
        task = info.get("taskDescription", "")
        led = EpisodeLedger(
            outdir / f"tales_{args.game}_s{seed}_{args.mode}.jsonl",
            {"env": "tales/twx", "game": args.game, "seed": seed,
             "mode": args.mode, "theta": args.theta, "model": args.model})
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Task: {task}\n\n{obs}"}]
        counter = [0]
        score, done, won = run_episode(
            env, task, chat, args, led, probe, args.mode,
            start_msgs=msgs, fork_budget=args.fork_max,
            fork_counter=counter)
        led.close(success=won, score=score, done=done, n_forks=counter[0])
        print(f"game={args.game} seed={seed} mode={args.mode} "
              f"score={score} won={won} forks={counter[0]}", flush=True)


if __name__ == "__main__":
    main()
