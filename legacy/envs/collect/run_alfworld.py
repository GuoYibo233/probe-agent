"""ALFWorld (TextWorld version) driver: each turn is "one thinking + one action," fully
recorded on both the input and output side.

The question set is the checked-in envs/alfworld/splits/{train,val,test}.txt, one unit id per
line, shaped like
  pick_cool_then_place_in_recep-Lettuce-None-CounterTop-10/trial_T20190909_174840_771703
Our three splits map to the official partitions: train->train, val->valid_seen,
test->valid_unseen.

Calls register_game directly on **a single game file**, bypassing AlfredTWEnv's full directory
scan (it would os.walk the whole partition and json.load both files of every trial -- train
has 3553 questions, and that is extremely slow on NFS). Registering a single question returns
a **non-batched** env: step takes a string and returns scalars, and the fields in infos are
also scalars/flat lists, without that extra [0] layer.

Usage:
  python run_alfworld.py --base-url http://HOST:8101/v1 --model qwen3.6-27b \
      --split val --n 1 --outdir ../runs/smoke_alf --exp smoke
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import TrajLog, chat_of, settings_from_args  # noqa: E402

REPO = "/home/y-guo/reproduce/new1"
DATA_ROOT = f"{REPO}/envs/alfworld/data"
SPLIT_DIR = f"{REPO}/envs/alfworld/splits"

# our three splits -> ALFWorld's official partition directory names
PARTITION = {"train": "train", "val": "valid_seen", "test": "valid_unseen"}

# Prompt. Three prohibitions (c2 plan §4 / task spec §3.4):
#   1) Do not write `put X in/on Y` -- alfworld >=0.4.0 has changed to `move X to Y`
#      (envs/alfworld/data/logic/alfred.twl2:211, tested: `move {o} to {r}`); the old syntax
#      only gets back "Nothing happens.", silently.
#      Here we simply **fix no template at all**, and always have the model copy verbatim from
#      the current turn's candidate list -- the candidates come from the environment itself,
#      so they are naturally in the current version's syntax.
#   2) Do not use ReAct's `think:` as a separate step (that produces a fake step of
#      action=think:...).
#   3) Do not copy fig1_pilot's 'reply with only one command, and nothing else' -- that leaves
#      reasoning empty, and build.py's 40-character gate would drop the whole step. Here we
#      explicitly require reasoning before the action.
SYSTEM = """You are an agent acting in a simulated household. Each turn you \
are shown the current observation and the exact list of commands the game \
will accept right now.

How to reply:
- First reason it out, in a few sentences: what the task needs next, where the \
target object is most likely to be, which places you have already ruled out, \
and why the command you are about to send makes progress. Never skip this.
- Then end your reply with exactly one line, with nothing after it:
  ACTION: <command>
- The command must be copied VERBATIM from the "Admissible commands" list of \
the CURRENT turn — same verb, same object numbers, same word order, no added \
articles. Write `take mug 1 from desk 1`, never `take the mug from the desk`. \
Do not invent phrasings and do not reuse the wording of an older turn.
- Never send `help`. It is listed but it only reprints this briefing and \
wastes a turn.
- Every command the parser cannot apply gets the same blank answer, \
"Nothing happens." That message means your command was rejected, never that \
the world quietly changed. When you see it, choose a DIFFERENT command; \
sending the same one again wastes a turn.

How this world works:
- Objects and receptacles are numbered (mug 1, countertop 3). Many objects \
start out hidden inside closed receptacles: you have to go to a receptacle and \
open it before its contents appear in the observation and in the list.
- You can only act on things at the place you are standing, so a plan usually \
runs: go to a candidate location, open it if it is closed, take the object, go \
to where it must end up, then place it there with the placement command the \
list offers you.
- Heating, cooling and cleaning each have their own command that names both \
the object and the appliance to use, and you must be carrying the object and \
standing at that appliance.
- To look at something under a lamp, carry the object and use the lamp.
- look re-describes where you are, inventory lists what you carry, and examine \
gives the details of one thing. They each cost a turn, so use them on purpose.

Search systematically, remember which receptacles you have already opened, and \
do not wander: you have a limited number of turns."""

ACT_RE = re.compile(r"ACTION:\s*(.+)")
TASK_RE = re.compile(r"Your task is to:\s*(.+)")


def escape_unit(uid):
    """unit id contains slashes (~92 characters); `/` -> `__` before writing to disk.

    The question set's character set, verified, is only [A-Za-z0-9_/-] and **contains no
    `__` at all**, so this mapping is injective and reversible:
    unescape_unit(escape_unit(u)) == u.
    """
    return uid.replace("/", "__")


def unescape_unit(name):
    return name.replace("__", "/")


def read_split(split, split_dir):
    p = Path(split_dir) / f"{split}.txt"
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]


def make_env(gamefile, max_steps):
    import textworld
    import textworld.gym
    from alfworld.agents.environment.alfred_tw_env import (
        AlfredDemangler, AlfredInfos)

    # AlfredDemangler turns internal ids into human-readable names; AlfredInfos is the wrapper
    # that fills extra.gamefile -- with only Demangler attached, that field is always None.
    request_infos = textworld.EnvInfos(won=True, admissible_commands=True,
                                       extras=["gamefile"])
    env_id = textworld.gym.register_game(
        gamefile, request_infos, max_episode_steps=max_steps,
        wrappers=[AlfredDemangler(), AlfredInfos()])
    return textworld.gym.make(env_id)


def user_turn(task, obs, step, max_steps, admissible=None):
    """The current turn's user message. The candidate list is attached only to the **latest**
    turn; history turns fall back to a short version without candidates, so 50 steps don't
    blow up the context."""
    head = (f"Task: {task}\nTurn {step + 1} of {max_steps}.\n\n"
            f"Observation:\n{obs}")
    if admissible is None:
        return head
    lines = "\n".join(f"- {c}" for c in admissible)
    return f"{head}\n\nAdmissible commands:\n{lines}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="default",
                    help="a set of generation settings from configs/presets/<name>.json;"
                         " default: default; args explicitly given on the command line override preset values")
    ap.add_argument("--base-url", help="can be omitted when the preset has a server section")
    ap.add_argument("--model", help="can be omitted when the preset has a server section")
    ap.add_argument("--split", default="val", choices=sorted(PARTITION))
    ap.add_argument("--n", type=int, default=1, help="0 = the whole split")
    ap.add_argument("--max-steps", type=int, default=50)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--api", default=None, choices=["raw", "chat"],
                    help="default raw (when the preset gives none either)")
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks already finished in outdir")
    ap.add_argument("--data-root", default=DATA_ROOT)
    ap.add_argument("--split-dir", default=SPLIT_DIR)
    args = ap.parse_args()

    os.environ.setdefault("ALFWORLD_DATA", str(Path(args.data_root).resolve()))
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    eff = settings_from_args(args)
    chat = chat_of(eff)

    part = PARTITION[args.split]
    games = Path(args.data_root) / "json_2.1.1" / part
    ids = read_split(args.split, args.split_dir)
    if args.n:
        ids = ids[: args.n]
    ids = ids[args.shard_id:: args.num_shards]
    print(f"shard {args.shard_id}/{args.num_shards}: {len(ids)} tasks "
          f"split={args.split} partition={part} exp={args.exp}", flush=True)

    for uid in ids:
        out_path = outdir / f"alfworld_{escape_unit(uid)}.jsonl"
        if args.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            print(f"task={uid} SKIP (done)", flush=True)
            continue
        gamefile = games / uid / "game.tw-pddl"
        if not gamefile.exists():
            print(f"task={uid} MISSING {gamefile}", flush=True)
            continue

        env = make_env(str(gamefile), args.max_steps)
        obs, infos = env.reset()
        # a mismatch between the question set and the actually loaded question is a silent failure --
        # assert it out on the spot
        loaded = infos.get("extra.gamefile")
        if loaded and os.path.realpath(loaded) != os.path.realpath(gamefile):
            raise SystemExit(f"gamefile mismatch: wanted {gamefile}, the environment loaded {loaded}")

        m = TASK_RE.search(obs)
        task = m.group(1).strip() if m else obs.strip().split("\n")[-1]
        log = TrajLog(out_path,
                      {"env": "alfworld", "task_id": uid, "model": eff["model"],
                       "instruction": task, "split": args.split,
                       "partition": part, "gamefile": str(gamefile),
                       "exp": args.exp, "preset": eff["preset"],
                       "gen_settings": chat.settings()})
        adm = list(infos.get("admissible_commands") or [])
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user",
                 "content": user_turn(task, obs, 0, args.max_steps, adm)}]
        last_user = 1                       # index of the latest user message in msgs
        last_plain = user_turn(task, obs, 0, args.max_steps)
        score, done, won = 0.0, False, False
        step = -1
        for step in range(args.max_steps):
            g = chat(msgs)
            log.w({"type": "gen", "step": step, **g})
            msgs.append({"role": "assistant", "content": g["content"]})
            mm = ACT_RE.search(g["content"])
            if mm:
                action = mm.group(1).strip()
            else:                            # fallback: the content's last non-empty line
                tail = [ln for ln in g["content"].strip().split("\n")
                        if ln.strip()]
                action = tail[-1].strip() if tail else ""
            # history turns fall back to the short version without candidates; only the latest turn
            # carries the full candidates
            msgs[last_user]["content"] = last_plain

            if not action:
                # even with no parseable action, an env entry must still be appended -- build.py:55-56 breaks
                # off the rest of the trajectory's steps the moment a step has gen but no env
                log.w({"type": "env", "step": step, "action": None,
                       "result": "NO_ACTION"})
                nudge = ("No command found. End your reply with exactly one "
                         "line of the form `ACTION: <command>`, copied "
                         "verbatim from the admissible list below.\n\n"
                         + user_turn(task, obs, step + 1, args.max_steps, adm))
                msgs.append({"role": "user", "content": nudge})
                last_user = len(msgs) - 1
                last_plain = user_turn(task, obs, step + 1, args.max_steps)
                continue

            obs, score, done, infos = env.step(action)
            won = bool(infos.get("won", False))
            adm = list(infos.get("admissible_commands") or [])
            log.w({"type": "env", "step": step, "action": action,
                   "result": obs, "reward": score, "done": bool(done),
                   "score": score, "won": won})
            msgs.append({"role": "user",
                         "content": user_turn(task, obs, step + 1,
                                              args.max_steps, adm)})
            last_user = len(msgs) - 1
            last_plain = user_turn(task, obs, step + 1, args.max_steps)
            if done:
                break
        # success/failure is judged by won, not done -- done also includes running out of steps
        log.w({"type": "final", "steps": step + 1, "score": score,
               "done": bool(done), "won": won})
        log.close()
        env.close()
        print(f"task={uid} steps={step + 1} score={score} won={won}",
              flush=True)


if __name__ == "__main__":
    main()
