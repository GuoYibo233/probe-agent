"""TALES(TextWorld-Express)驱动:ReAct 文本循环,进出全录。

用法:
  python run_tales.py --base-url http://HOST:8101/v1 --model qwen3.5-27b \
      --game cookingworld --seeds 7,8 --outdir ../runs/smoke_q35
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import Chat, TrajLog  # noqa: E402

SYSTEM = """You are playing a text-based game. At each turn you receive an \
observation. Think step by step, then reply with exactly one command on the \
last line, in the form:
ACTION: <command>
The game only understands its fixed verb set:
look around / inventory / open X / take X / put X in Y / move north|south|...
read cookbook
chop X | dice X | slice X   (requires: take knife first, X in inventory)
cook X in stove (=fry) | cook X in oven (=roast) | cook X in BBQ (=grill)
prepare meal   (when all ingredients are ready, must be in kitchen)
eat meal
Follow the cookbook recipe EXACTLY: gather ALL listed ingredients (some may
be in other rooms — move around to find them; the BBQ is usually in the
backyard), apply the EXACT preparation verb (grill≠roast≠fry), then
prepare meal in the kitchen."""

ACT_RE = re.compile(r"ACTION:\s*(.+)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--game", default="cookingworld")
    ap.add_argument("--seeds", default="7,8")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--api", default="raw", choices=["raw", "chat"])
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--game-params", default=None,
                    help="覆盖 TWX 默认难度参数串,如 'numLocations=5, ...'")
    ap.add_argument("--resume", action="store_true",
                    help="跳过 outdir 里已跑完的 seed")
    args = ap.parse_args()

    import tales.textworld_express as twx
    from tales.textworld_express import TextWorldExpressEnv
    params = {g[1]: g[2] for g in twx.TASKS}
    if args.game_params:
        params[args.game] = args.game_params

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    chat = Chat(args.base_url, args.model, api=args.api,
                reasoning_effort=args.reasoning_effort)

    for seed in [int(s) for s in args.seeds.split(",")]:
        out_path = outdir / f"tales_{args.game}_s{seed}.jsonl"
        if args.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            print(f"game={args.game} seed={seed} SKIP (done)", flush=True)
            continue
        env = TextWorldExpressEnv(args.game, params[args.game])
        obs, info = env.reset(seed=seed)
        log = TrajLog(outdir / f"tales_{args.game}_s{seed}.jsonl",
                      {"env": "tales/twx", "game": args.game, "seed": seed,
                       "model": args.model,
                       "task": info.get("taskDescription", "")})
        first = (f"Task: {info.get('taskDescription', '')}\n\n{obs}")
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": first}]
        score, done, won = 0.0, False, False
        step = -1
        for step in range(args.max_steps):
            g = chat(msgs)
            log.w({"type": "gen", "step": step, **g})
            m = ACT_RE.search(g["content"])
            action = (m.group(1) if m
                      else g["content"].strip().split("\n")[-1]).strip()
            obs2, reward, done, si = env.step(action)
            score, won = si.get("score", score), si.get("won", False)
            log.w({"type": "env", "step": step, "action": action,
                   "result": obs2, "reward": reward, "done": done,
                   "score": score, "won": won})
            msgs.append({"role": "assistant", "content": g["content"]})
            msgs.append({"role": "user", "content": obs2})
            if done:
                break
        log.w({"type": "final", "steps": step + 1, "score": score,
               "done": done, "won": won})
        log.close()
        print(f"game={args.game} seed={seed} steps={step + 1} "
              f"score={score} won={won}", flush=True)


if __name__ == "__main__":
    main()
