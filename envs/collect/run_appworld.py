"""AppWorld 驱动:模型每轮写一个 python 代码块调 apis,逐步执行,进出全录。

用法:
  python run_appworld.py --base-url http://HOST:8101/v1 --model qwen3.5-27b \
      --split dev --n 2 --outdir ../runs/smoke_q35 --exp smoke_q35
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import Chat, TrajLog  # noqa: E402

SYSTEM = """You are an autonomous agent operating a phone-like environment \
on behalf of your supervisor.

Rules:
- Each turn, write exactly ONE ```python ... ``` code block. It is executed \
in a persistent IPython shell and you ONLY see what is printed — always wrap \
calls whose result you need in print(...), e.g. \
print(apis.spotify.show_playlists(...))
- Call app APIs as: apis.{app_name}.{api_name}(...)
- Explore first: apis.api_docs.show_app_descriptions(), \
apis.api_docs.show_api_descriptions(app_name=...), \
apis.api_docs.show_api_doc(app_name=..., api_name=...)
- Your supervisor's identity: print(apis.supervisor.show_profile()) gives \
their email/phone; print(apis.supervisor.show_account_passwords()) gives \
their password for each app. NEVER guess usernames or passwords.
- Login pattern: token = apis.spotify.login(username=<supervisor email>, \
password=<password from the list>)["access_token"], then pass \
access_token=token to that app's other APIs.
- When the task is fully done, call apis.supervisor.complete_task() \
(pass answer=... if the task asks a question)."""

CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--n", type=int, default=2, help="0 = 整个 split")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--api", default="raw", choices=["raw", "chat"])
    ap.add_argument("--reasoning-effort", default=None)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="跳过 outdir 里已写完的任务")
    args = ap.parse_args()

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    os.chdir("/home/y-guo/reproduce/new1/envs/appworld")
    from appworld import AppWorld, load_task_ids
    chat = Chat(args.base_url, args.model, api=args.api,
                reasoning_effort=args.reasoning_effort)

    ids = load_task_ids(args.split)
    if args.n:
        ids = ids[: args.n]
    ids = ids[args.shard_id:: args.num_shards]
    # 每个 shard 一个 experiment_name,免得并发跑时 AppWorld 的实验目录互相踩
    exp = args.exp if args.num_shards == 1 else f"{args.exp}_s{args.shard_id}"
    print(f"shard {args.shard_id}/{args.num_shards}: {len(ids)} tasks "
          f"exp={exp}", flush=True)

    for tid in ids:
        out_path = outdir / f"appworld_{tid}.jsonl"
        if args.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            print(f"task={tid} SKIP (done)", flush=True)
            continue
        with AppWorld(task_id=tid, experiment_name=exp) as world:
            instr = world.task.instruction
            log = TrajLog(outdir / f"appworld_{tid}.jsonl",
                          {"env": "appworld", "task_id": tid,
                           "model": args.model, "instruction": instr})
            msgs = [{"role": "system", "content": SYSTEM},
                    {"role": "user",
                     "content": f"Task from supervisor: {instr}"}]
            completed = False
            step = -1
            for step in range(args.max_steps):
                g = chat(msgs)
                log.w({"type": "gen", "step": step, **g})
                m = CODE_RE.search(g["content"])
                msgs.append({"role": "assistant", "content": g["content"]})
                if not m:
                    log.w({"type": "env", "step": step, "action": None,
                           "result": "NO_CODE_BLOCK"})
                    msgs.append({"role": "user", "content":
                                 "No ```python``` block found. Reply with "
                                 "exactly one python code block."})
                    continue
                code = m.group(1)
                out = str(world.execute(code))
                log.w({"type": "env", "step": step, "action": code,
                       "result": out[:4000]})
                msgs.append({"role": "user",
                             "content": f"Execution output:\n{out[:4000]}"})
                if world.task_completed():
                    completed = True
                    break
            try:
                ev = world.evaluate()
                ev_s = str(ev.to_dict() if hasattr(ev, "to_dict") else ev)[:600]
            except Exception as e:  # 评测失败不弃轨迹
                ev_s = f"eval_error: {e}"
            log.w({"type": "final", "steps": step + 1,
                   "completed": completed, "eval": ev_s})
            log.close()
            print(f"task={tid} steps={step + 1} completed={completed} "
                  f"eval={ev_s[:120]}", flush=True)


if __name__ == "__main__":
    main()
