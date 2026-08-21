"""AppWorld 驱动:模型每轮写一个 python 代码块调 apis,逐步执行,进出全录。

用法:
  python run_appworld.py --base-url http://HOST:8101/v1 --model qwen3.5-27b \
      --split dev --n 2 --outdir ../runs/smoke_q35 --exp smoke_q35
  # 每题多条轨迹(温度 >0 的采样口径):种子逐条派,文件名带采样序号
  python run_appworld.py --preset default --base-url ... --split train \
      --traj-per-task 4 --seeds 42,67,4267,6742 --outdir ... --exp np821tr
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


def resolve_seeds(seeds_arg, n):
    """--seeds 与 --traj-per-task 合成一张种子表,第 k 条轨迹用第 k 个种子。
    返回 None = 单条轨迹又没点种子,一切照多样本改造前的老口径。
    温度 1 下不带种子的多样本复现不了,所以 n > 1 缺 --seeds 直接拒。
    """
    if n < 1:
        raise SystemExit(f"--traj-per-task 必须 >= 1,现在是 {n}")
    if seeds_arg is None:
        if n > 1:
            raise SystemExit(f"--traj-per-task {n} 必须配 --seeds"
                             "(温度 >0 的多样本不带种子复现不了)")
        return None
    try:
        seeds = [int(s.strip()) for s in seeds_arg.split(",")]
    except ValueError:
        raise SystemExit(f"--seeds 只收逗号分隔的整数,现在是 {seeds_arg!r}")
    if len(seeds) != n:
        raise SystemExit(f"--seeds 给了 {len(seeds)} 个种子,"
                         f"与 --traj-per-task {n} 对不上")
    return seeds


def traj_path(outdir, tid, k, n):
    """第 k 条轨迹的落盘路径。n == 1 时文件名与改造前一字不差
    (下游按 appworld_<task_id>.jsonl 认老批次)。"""
    stem = f"appworld_{tid}" if n == 1 else f"appworld_{tid}_r{k}"
    return Path(outdir) / f"{stem}.jsonl"


def is_done(path):
    """--resume 的完成判据:文件在,而且里面已经有 final 记录
    (判据从主循环原样搬出来,好单测)。"""
    return path.exists() and '"type": "final"' in path.read_text()


def exp_name(base, k, n):
    """AppWorld 的 experiment_name。同一 (experiment_name, task_id) 重开一次,
    AppWorld.__init__ -> initialize() -> _prepare_directories() 会先
    shutil.rmtree 掉该题的输出目录(appworld/environment.py:434),也就是说
    第 k 条轨迹的 dbs/logs/misc 会被第 k+1 条抹掉、evaluate() 只认最后一次
    (evaluate 按 experiment_name+task_id 查磁盘,同文件 571-575 行)。
    环境状态本身不带残留(每次从题目自带的 db 重新装),但产物会互相覆盖,
    所以多样本逐条分开一个实验目录。"""
    return base if n == 1 else f"{base}_r{k}"


def traj_meta(eff, tid, instr, chat, k, n):
    """轨迹 meta 的固定字段。n == 1 时逐键同序、取值与改造前一致;
    sample_idx 只在多样本时追加(下游 build/param_label 不读它)。"""
    meta = {"env": "appworld", "task_id": tid,
            "model": eff["model"], "instruction": instr,
            "preset": eff["preset"], "gen_settings": chat.settings()}
    if n > 1:
        meta["sample_idx"] = k
    return meta


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
    ap.add_argument("--traj-per-task", type=int, default=1,
                    help="每题采几条轨迹(缺省 1 = 老口径)。>1 必须配 --seeds")
    ap.add_argument("--seeds", default=None,
                    help="逗号分隔的整数种子表,长度必须 == --traj-per-task;"
                         "第 k 条轨迹用第 k 个种子,种子进请求体也进轨迹 meta")
    ap.add_argument("--resume", action="store_true",
                    help="跳过 outdir 里已写完的任务")
    args = ap.parse_args()
    n_traj = args.traj_per_task
    seeds = resolve_seeds(args.seeds, n_traj)
    eff = settings_from_args(args)
    if eff["api"] == "chat" and eff["reasoning_effort"] is None:
        eff["reasoning_effort"] = "high"

    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    os.chdir("/home/y-guo/reproduce/new1/envs/appworld")
    from appworld import AppWorld, load_task_ids
    # 一条轨迹一个 Chat:种子表在场时逐条换种子,种子从而进请求体
    # (common.Chat._sample_extras)也进轨迹 meta 的 gen_settings.seed
    chats = [chat_of(eff)] if seeds is None else \
        [chat_of({**eff, "seed": s}) for s in seeds]

    ids = load_task_ids(args.split)
    if args.n:
        ids = ids[: args.n]
    ids = ids[args.shard_id:: args.num_shards]
    # 每个 shard 一个 experiment_name,免得并发跑时 AppWorld 的实验目录互相踩
    exp = args.exp if args.num_shards == 1 else f"{args.exp}_s{args.shard_id}"
    multi_note = "" if n_traj == 1 else \
        f" traj/task={n_traj} seeds={','.join(str(s) for s in seeds)}"
    print(f"shard {args.shard_id}/{args.num_shards}: {len(ids)} tasks "
          f"exp={exp}{multi_note}", flush=True)

    tok_in = tok_out = 0
    n_done = 0
    total = len(ids) * n_traj   # 心跳按轨迹数,unit 仍是 "task"(采样器不改)
    heartbeat.emit(0, total, "task", tok_in=0, tok_out=0)

    # 外层题、内层采样序号;n_traj == 1 时就是原来的"每题一条"
    for tid, k in [(t, j) for t in ids for j in range(n_traj)]:
        tag = tid if n_traj == 1 else f"{tid} r{k}"
        chat = chats[k]
        out_path = traj_path(outdir, tid, k, n_traj)
        if args.resume and is_done(out_path):
            print(f"task={tag} SKIP (done)", flush=True)
            n_done += 1
            heartbeat.emit(n_done, total, "task", tok_in=tok_in,
                           tok_out=tok_out)
            continue
        with AppWorld(task_id=tid,
                      experiment_name=exp_name(exp, k, n_traj)) as world:
            instr = world.task.instruction
            log = TrajLog(out_path,
                          traj_meta(eff, tid, instr, chat, k, n_traj))
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
                print(f"task={tag} STEP_ERROR {abort}", flush=True)
            try:
                ev = world.evaluate()
                ev_s = str(ev.to_dict() if hasattr(ev, "to_dict") else ev)[:600]
            except Exception as e:  # 评测失败不弃轨迹
                ev_s = f"eval_error: {e}"
            log.w({"type": "final", "steps": step + 1,
                   "completed": completed, "abort": abort, "eval": ev_s})
            log.close()
            print(f"task={tag} steps={step + 1} completed={completed} "
                  f"abort={abort} eval={ev_s[:120]}", flush=True)
            n_done += 1
            heartbeat.emit(n_done, total, "task", tok_in=tok_in,
                           tok_out=tok_out)

    heartbeat.emit(n_done, total, "task", tok_in=tok_in, tok_out=tok_out,
                   status="done")


if __name__ == "__main__":
    main()
