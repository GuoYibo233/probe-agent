"""Fig 1 pilot: joint speed+accuracy learning curves on repeated similar tasks.

Runs a controlled stream of k ALFWorld episodes at a chosen similarity level,
in one of two settings:
  nomem — every episode starts fresh (floor)
  mem   — naive memory: successful trajectories from earlier episodes are
          appended to the prompt as experience

Per-episode metrics: success, env steps, wall seconds, tokens in/out.
Output: one JSON line per episode.

Similarity levels (constructed from game file paths,
e.g. pick_and_place_simple-HandTowel-None-GarbageCan-416/trial_X/game.tw-pddl):
  L0 — the exact same trial repeated k times
  L1 — same task-type+object+receptacle, different scene/trial
  L2 — same task-type, different object/receptacle
"""

import argparse
import json
import os
import random
import re
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("ALFWORLD_DATA", "/home/y-guo/reproduce/new1/fig1_pilot/alfworld_data")

import yaml
from openai import OpenAI

import alfworld.agents.environment as environment

HERE = Path(__file__).parent

SYSTEM = (
    "You are an agent in a household environment. At each turn you are given "
    "the current observation and the list of admissible commands. Reply with "
    "EXACTLY ONE command copied verbatim from the admissible list. No other text.\n"
    "Strategy: to 'put X in/on Y' you must first FIND X (objects are often inside "
    "closed receptacles — 'go to' one, then 'open' it to see its contents), then "
    "'take X from ...', then 'go to Y', open Y if closed, and 'move X to Y'. "
    "Search systematically: check likely receptacles one by one, opening each. "
    "Never repeat an action that did not change the state."
)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setting", choices=["nomem", "mem"], required=True)
    ap.add_argument("--level", choices=["L0", "L1", "L2"], default="L0")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--task-type", default="pick_and_place_simple")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--url", default=os.environ.get("VLLM_URL", "http://tokyo108:8712/v1"))
    ap.add_argument("--model", default="Qwen/Qwen3.5-4B")
    ap.add_argument("--out", required=True)
    ap.add_argument("--think", action="store_true", help="enable model thinking mode")
    ap.add_argument("--max-tokens", type=int, default=256)
    return ap.parse_args()


def build_stream(all_games, level, task_type, k, rng):
    """Pick k game files forming a controlled-similarity stream."""
    # group: task dir name -> (tasktype, obj, recep) parsed from path
    def key(p):
        name = Path(p).parent.parent.name  # e.g. pick_and_place_simple-HandTowel-None-GarbageCan-416
        parts = name.split("-")
        return parts[0], parts[1], parts[3]  # tasktype, obj, recep

    of_type = [p for p in all_games if key(p)[0] == task_type]
    assert of_type, f"no games of type {task_type}"
    if level == "L0":
        g = rng.choice(of_type)
        return [g] * k
    if level == "L1":
        by_obj_recep = defaultdict(list)
        for p in of_type:
            by_obj_recep[key(p)[1:]].append(p)
        pool = max(by_obj_recep.values(), key=len)
        assert len(pool) >= 2, "no object/recep pair with >=2 trials"
        stream = [pool[i % len(pool)] for i in range(k)]
        rng.shuffle(stream)  # decouple stream position from game difficulty
        return stream
    # L2: same task type, spread over objects
    rng.shuffle(of_type)
    stream = of_type[:k] if len(of_type) >= k else [of_type[i % len(of_type)] for i in range(k)]
    rng.shuffle(stream)
    return stream


def episode(env, client, model, max_steps, memory_block, max_tokens, think, rng):
    obs, info = env.reset()
    task_obs = obs[0]
    history = []
    tin = tout = 0
    t0 = time.time()
    success = False
    for _ in range(max_steps):
        admissible = info["admissible_commands"][0]
        hist_txt = "\n".join(f"> {a}\n{o}" for a, o in history[-8:])
        user = ""
        if memory_block:
            user += f"=== experience from earlier similar tasks ===\n{memory_block}\n\n"
        user += (
            f"{task_obs}\n\n=== recent history ===\n{hist_txt}\n\n"
            f"=== admissible commands ===\n" + "\n".join(admissible)
            + "\n\nDo not repeat an action whose last result showed no change. Next command:"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=0.0,
            extra_body={"chat_template_kwargs": {"enable_thinking": think}},
        )
        tin += resp.usage.prompt_tokens
        tout += resp.usage.completion_tokens
        raw = resp.choices[0].message.content or ""
        txt = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        lines = [l.strip("` >") for l in txt.splitlines() if l.strip()]
        action = lines[-1] if lines else "look"
        if action not in admissible:
            matches = [a for a in admissible if a in txt]
            action = matches[0] if matches else "look"
        # break behavioral loops: same action 3x in a row -> random other admissible
        recent = [a for a, _ in history[-2:]]
        if len(recent) == 2 and recent[0] == recent[1] == action:
            others = [a for a in admissible if a != action]
            if others:
                action = rng.choice(others)
        obs, scores, dones, info = env.step([action])
        history.append((action, obs[0][:300]))
        if dones[0]:
            success = bool(info.get("won", [False])[0]) or scores[0] > 0
            break
    return {
        "success": success,
        "steps": len(history),
        "wall_s": round(time.time() - t0, 2),
        "tokens_in": tin,
        "tokens_out": tout,
        "task": task_obs.split("Your task is to:")[-1].strip()[:150],
        "actions": [a for a, _ in history],
    }


def main():
    args = parse_args()
    rng = random.Random(args.seed)
    client = OpenAI(base_url=args.url, api_key="dummy")

    config = yaml.safe_load(open(HERE / "base_config.yaml"))
    config["general"] = config.get("general", {})
    config["general"]["training_method"] = "dqn"  # plain env, no expert wrapper
    config.setdefault("rl", {}).setdefault("training", {})["max_nb_steps_per_episode"] = args.max_steps + 5

    base = environment.get_environment("AlfredTWEnv")(config, train_eval="train")
    stream = build_stream(base.game_files, args.level, args.task_type, args.k, rng)
    print(f"stream ({args.level}):")
    for p in stream:
        print("  ", Path(p).parent.parent.name, Path(p).parent.name)

    experiences = []  # (task, actions, success)
    out = open(args.out, "w")
    for i, game in enumerate(stream):
        base.game_files = [game]
        env = base.init_env(batch_size=1)
        mem_block = ""
        if args.setting == "mem" and experiences:
            blocks = []
            for task, actions, succ in experiences[-5:]:
                if succ:
                    blocks.append(f"Task: {task}\nSuccessful actions: {' -> '.join(actions)}")
            mem_block = "\n\n".join(blocks)
        r = episode(env, client, args.model, args.max_steps, mem_block,
                    args.max_tokens, args.think, rng)
        r.update(episode_idx=i, level=args.level, setting=args.setting,
                 game=str(Path(game).parent.parent.name) + "/" + str(Path(game).parent.name))
        experiences.append((r["task"], r["actions"], r["success"]))
        out.write(json.dumps(r) + "\n")
        out.flush()
        env.close()
        print(f"[ep {i:02d}] success={r['success']} steps={r['steps']} "
              f"wall={r['wall_s']}s in={r['tokens_in']} out={r['tokens_out']}")
    out.close()


if __name__ == "__main__":
    main()
