"""ALFWorld(TextWorld 版)驱动:每轮「一段思考 + 一条动作」,进出全录。

题单是入库的 envs/alfworld/splits/{train,val,test}.txt,每行一个 unit id,形如
  pick_cool_then_place_in_recep-Lettuce-None-CounterTop-10/trial_T20190909_174840_771703
三堆按官方分区映射:train->train、val->valid_seen、test->valid_unseen。

按**单个 game 文件**直接 register_game,绕开 AlfredTWEnv 的全量目录扫描
(它会 os.walk 整个分区并 json.load 每个 trial 的两个文件,train 有 3553 题,
NFS 上极慢)。单题注册返回的是**非批量** env:step 收字符串、返回标量,
infos 里的字段也都是标量/扁平列表,没有 [0] 那层。

用法:
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

# 我们的三堆 -> ALFWorld 官方分区目录名
PARTITION = {"train": "train", "val": "valid_seen", "test": "valid_unseen"}

# 提示词。三条禁令(c2 计划 §4 / 任务书 §3.4):
#   1) 不写 `put X in/on Y` —— alfworld >=0.4.0 已改成 `move X to Y`
#      (envs/alfworld/data/logic/alfred.twl2:211 实测 `move {o} to {r}`),
#      老语法只会换来 "Nothing happens.",而且一声不吭。
#      这里干脆**不定死任何模板**,一律让模型从当轮候选列表逐字抄 ——
#      候选来自环境本身,天然是当前版本的语法。
#   2) 不用 ReAct 的 `think:` 单独成步(那会造出 action=think:... 的假步)。
#   3) 不照抄 fig1_pilot 的"只回一条命令、不许有别的字" —— 那样 reasoning
#      为空,build.py 的 40 字符门槛会把整步丢掉。这里明确要求先推理再动作。
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
    """unit id 含斜杠(~92 字符),落盘前 `/` -> `__`。

    题单实测字符集只有 [A-Za-z0-9_/-] 且**没有任何 `__`**,所以这个映射
    单射可逆:unescape_unit(escape_unit(u)) == u。
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

    # AlfredDemangler 把内部 id 换成人读的名字;AlfredInfos 才是填
    # extra.gamefile 的那个 wrapper —— 只挂 Demangler 的话该字段永远是 None。
    request_infos = textworld.EnvInfos(won=True, admissible_commands=True,
                                       extras=["gamefile"])
    env_id = textworld.gym.register_game(
        gamefile, request_infos, max_episode_steps=max_steps,
        wrappers=[AlfredDemangler(), AlfredInfos()])
    return textworld.gym.make(env_id)


def user_turn(task, obs, step, max_steps, admissible=None):
    """当轮 user 消息。候选列表只挂在**最新**一轮,历史轮回落成不带候选的短版,
    免得 50 步下来把上下文撑爆。"""
    head = (f"Task: {task}\nTurn {step + 1} of {max_steps}.\n\n"
            f"Observation:\n{obs}")
    if admissible is None:
        return head
    lines = "\n".join(f"- {c}" for c in admissible)
    return f"{head}\n\nAdmissible commands:\n{lines}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="default",
                    help="configs/presets/<名>.json 的一套生成设置;"
                         "缺省 default;命令行显式给的参数压过预设值")
    ap.add_argument("--base-url", help="预设带 server 节时可省")
    ap.add_argument("--model", help="预设带 server 节时可省")
    ap.add_argument("--split", default="val", choices=sorted(PARTITION))
    ap.add_argument("--n", type=int, default=1, help="0 = 整个 split")
    ap.add_argument("--max-steps", type=int, default=50)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--api", default=None, choices=["raw", "chat"],
                    help="缺省 raw(预设也没给时)")
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="跳过 outdir 里已写完的题")
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
        # 题单与实际加载的题错位是不报错的事故,这里当场断言掐掉
        loaded = infos.get("extra.gamefile")
        if loaded and os.path.realpath(loaded) != os.path.realpath(gamefile):
            raise SystemExit(f"gamefile 错位: 要 {gamefile},环境加载了 {loaded}")

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
        last_user = 1                       # msgs 里最新那条 user 的下标
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
            else:                            # 兜底:内容最后一行非空串
                tail = [ln for ln in g["content"].strip().split("\n")
                        if ln.strip()]
                action = tail[-1].strip() if tail else ""
            # 历史轮退回不带候选的短版,只有最新一轮带完整候选
            msgs[last_user]["content"] = last_plain

            if not action:
                # 无可解析动作也必须补一条 env —— build.py:55-56 一旦发现某 step
                # 有 gen 无 env 就 break 掉整条轨迹的后续步
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
        # 成败判 won,不判 done —— done 还包括步数耗尽
        log.w({"type": "final", "steps": step + 1, "score": score,
               "done": bool(done), "won": won})
        log.close()
        env.close()
        print(f"task={uid} steps={step + 1} score={score} won={won}",
              flush=True)


if __name__ == "__main__":
    main()
