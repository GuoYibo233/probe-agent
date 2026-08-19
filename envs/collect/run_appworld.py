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
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops"))
import heartbeat  # noqa: E402
from common import TrajLog, chat_of, settings_from_args  # noqa: E402

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
    ap.add_argument("--preset", default=None,
                    help="configs/presets/<名>.json 的一套生成设置;"
                         "命令行显式给的参数压过预设值")
    ap.add_argument("--base-url", help="预设带 server 节时可省")
    ap.add_argument("--model", help="预设带 server 节时可省")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--n", type=int, default=2, help="0 = 整个 split")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--api", default=None,
                    choices=["raw", "chat", "harmony"],
                    help="缺省 raw(预设也没给时)")
    ap.add_argument("--reasoning-effort", default=None,
                    help="harmony 的 Reasoning 档。--api chat 下不传按 high "
                         "(与 live_appworld --effort 缺省一致;服务端缺省是 "
                         "medium,2026-08-18 实测,不显式给就与 no probe 差一个词)")
    ap.add_argument("--start-date", default=None,
                    help="harmony 模式下钉死 prompt 里的 Current date"
                         "(缺省 2026-08-06)")
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="跳过 outdir 里已写完的任务")
    args = ap.parse_args()
    eff = settings_from_args(args)
    if eff["api"] == "chat" and eff["reasoning_effort"] is None:
        eff["reasoning_effort"] = "high"

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    os.chdir("/home/y-guo/reproduce/new1/envs/appworld")
    from appworld import AppWorld, load_task_ids
    chat = chat_of(eff)

    ids = load_task_ids(args.split)
    if args.n:
        ids = ids[: args.n]
    ids = ids[args.shard_id:: args.num_shards]
    # 每个 shard 一个 experiment_name,免得并发跑时 AppWorld 的实验目录互相踩
    exp = args.exp if args.num_shards == 1 else f"{args.exp}_s{args.shard_id}"
    print(f"shard {args.shard_id}/{args.num_shards}: {len(ids)} tasks "
          f"exp={exp}", flush=True)

    tok_in = tok_out = 0
    n_done = 0
    heartbeat.emit(0, len(ids), "task", tok_in=0, tok_out=0)

    for tid in ids:
        out_path = outdir / f"appworld_{tid}.jsonl"
        if args.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            print(f"task={tid} SKIP (done)", flush=True)
            n_done += 1
            heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in,
                           tok_out=tok_out)
            continue
        with AppWorld(task_id=tid, experiment_name=exp) as world:
            instr = world.task.instruction
            log = TrajLog(outdir / f"appworld_{tid}.jsonl",
                          {"env": "appworld", "task_id": tid,
                           "model": eff["model"], "instruction": instr,
                           "preset": eff["preset"],
                           "gen_settings": chat.settings()})
            msgs = [{"role": "system", "content": SYSTEM},
                    {"role": "user",
                     "content": f"Task from supervisor: {instr}"}]
            completed = False
            step = -1
            abort = None
            try:
                for step in range(args.max_steps):
                    g = chat(msgs)
                    tok_in += g["usage"]["in"]
                    tok_out += g["usage"]["out"]
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
            except Exception as e:
                # 单题炸了不许陪葬整个分片(2026-08-18,与 live_appworld 同款):
                # 服务端 400(上下文撞顶)/ 500(harmony 解析器抛 HarmonyError)
                # 重试 4 次仍失败会落到这里。世界还开着,照常 evaluate,
                # 失败记诚实,abort 字段说明是哪一步、什么错。
                abort = f"step{step}:{type(e).__name__}:{str(e)[:200]}"
                print(f"task={tid} STEP_ERROR {abort}", flush=True)
            try:
                ev = world.evaluate()
                ev_s = str(ev.to_dict() if hasattr(ev, "to_dict") else ev)[:600]
            except Exception as e:  # 评测失败不弃轨迹
                ev_s = f"eval_error: {e}"
            log.w({"type": "final", "steps": step + 1,
                   "completed": completed, "abort": abort, "eval": ev_s})
            log.close()
            print(f"task={tid} steps={step + 1} completed={completed} "
                  f"abort={abort} eval={ev_s[:120]}", flush=True)
            n_done += 1
            heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in,
                           tok_out=tok_out)

    heartbeat.emit(n_done, len(ids), "task", tok_in=tok_in, tok_out=tok_out,
                   status="done")


if __name__ == "__main__":
    main()
