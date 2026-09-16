"""AppWorld driver: the model writes one Python code block calling apis each turn, executed
step by step, fully recorded on both the input and output side.

Usage:
  python run_appworld.py --base-url http://HOST:8101/v1 --model qwen3.5-27b \
      --split dev --n 2 --outdir ../runs/smoke_q35 --exp smoke_q35
  # multiple trajectories per question (the temperature>0 sampling convention): a seed is
  # issued per trajectory, and the filename carries the sample index
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
    """--seeds and --traj-per-task combine into a seed table; the k-th trajectory uses the k-th
    seed. Returning None = a single trajectory with no seed given, everything follows the old
    convention from before the multi-sample rework. Multi-sample runs without a seed cannot be
    reproduced at temperature 1, so n > 1 without --seeds is rejected outright.
    """
    if n < 1:
        raise SystemExit(f"--traj-per-task must be >= 1, currently {n}")
    if seeds_arg is None:
        if n > 1:
            raise SystemExit(f"--traj-per-task {n} requires --seeds"
                             " (multi-sample with temperature >0 isn't reproducible without seeds)")
        return None
    try:
        seeds = [int(s.strip()) for s in seeds_arg.split(",")]
    except ValueError:
        raise SystemExit(f"--seeds only accepts comma-separated integers, currently {seeds_arg!r}")
    if len(seeds) != n:
        raise SystemExit(f"--seeds gave {len(seeds)} seeds,"
                         f" which doesn't match --traj-per-task {n}")
    return seeds


def traj_path(outdir, tid, k, n):
    """The k-th trajectory's on-disk path. When n == 1, the filename is identical, character for
    character, to before the rework (downstream code recognizes old batches by
    appworld_<task_id>.jsonl)."""
    stem = f"appworld_{tid}" if n == 1 else f"appworld_{tid}_r{k}"
    return Path(outdir) / f"{stem}.jsonl"


def is_done(path):
    """--resume's completion criterion: the file exists and already has a final record inside it
    (the criterion is pulled out of the main loop as-is, to make it unit-testable)."""
    return path.exists() and '"type": "final"' in path.read_text()


def exp_name(base, k, n):
    """AppWorld's experiment_name. Reopening the same (experiment_name, task_id) once,
    AppWorld.__init__ -> initialize() -> _prepare_directories() first does shutil.rmtree on
    that question's output directory (appworld/environment.py:434), which means the k-th
    trajectory's dbs/logs/misc get wiped by the (k+1)-th, and evaluate() only recognizes the
    last run (evaluate looks things up on disk by experiment_name+task_id, same file, lines
    571-575). The environment state itself carries no residue (it reloads from the question's
    own db every time), but the outputs would overwrite each other, so multi-sample runs get a
    separate experiment directory per trajectory."""
    return base if n == 1 else f"{base}_r{k}"


def traj_meta(eff, tid, instr, chat, k, n):
    """Trajectory meta's fixed fields. When n == 1, the keys are in the same order and hold the
    same values as before the rework; sample_idx is appended only for multi-sample runs
    (downstream build/param_label does not read it)."""
    meta = {"env": "appworld", "task_id": tid,
            "model": eff["model"], "instruction": instr,
            "preset": eff["preset"], "gen_settings": chat.settings()}
    if n > 1:
        meta["sample_idx"] = k
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="default",
                    help="a set of generation settings from configs/presets/<name>.json;"
                         " default: default; args explicitly given on the command line override preset values")
    ap.add_argument("--base-url", help="can be omitted when the preset has a server section")
    ap.add_argument("--model", help="can be omitted when the preset has a server section")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--n", type=int, default=2, help="0 = the whole split")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", default="smoke")
    ap.add_argument("--api", default=None,
                    choices=["raw", "chat", "harmony"],
                    help="default raw (when the preset gives none either)")
    ap.add_argument("--reasoning-effort", default=None,
                    help="harmony's Reasoning tier. Under --api chat, not passing it defaults to high "
                         "(matches live_appworld --effort's default; the server default is "
                         "medium, measured 2026-08-18 -- without giving it explicitly, it differs from no-probe by one word)")
    ap.add_argument("--start-date", default=None,
                    help="pin the Current date in the prompt under harmony mode"
                         " (default 2026-08-06)")
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--traj-per-task", type=int, default=1,
                    help="how many trajectories to collect per task (default 1 = the old settings). >1 requires --seeds")
    ap.add_argument("--seeds", default=None,
                    help="comma-separated list of integer seeds, length must == --traj-per-task;"
                         " the k-th trajectory uses the k-th seed; the seed goes into both the request body and the trajectory meta")
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks already finished in outdir")
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
    # One Chat per trajectory: when a seed list is present, the seed advances per entry, so it
    # goes into the request body (common.Chat._sample_extras) and into the trajectory meta's
    # gen_settings.seed.
    chats = [chat_of(eff)] if seeds is None else \
        [chat_of({**eff, "seed": s}) for s in seeds]

    ids = load_task_ids(args.split)
    if args.n:
        ids = ids[: args.n]
    ids = ids[args.shard_id:: args.num_shards]
    # One experiment_name per shard, so concurrent runs don't clobber each other's AppWorld
    # experiment directories.
    exp = args.exp if args.num_shards == 1 else f"{args.exp}_s{args.shard_id}"
    multi_note = "" if n_traj == 1 else \
        f" traj/task={n_traj} seeds={','.join(str(s) for s in seeds)}"
    print(f"shard {args.shard_id}/{args.num_shards}: {len(ids)} tasks "
          f"exp={exp}{multi_note}", flush=True)

    tok_in = tok_out = 0
    n_done = 0
    total = len(ids) * n_traj   # Heartbeat counts by trajectory; the unit stays "task" (no change needed in the sampler).
    heartbeat.emit(0, total, "task", tok_in=0, tok_out=0)

    # Outer loop over tasks, inner loop over sample index; when n_traj == 1 this is the original
    # "one per task".
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
                # A single task's crash must not take the whole shard down with it (2026-08-18, same fix as
                # live_appworld): a server-side 400 (context limit hit) or 500 (harmony parser raises
                # HarmonyError) that still fails after 4 retries lands here. The world is still open, so
                # evaluation proceeds as usual; the failure is recorded honestly, with the abort field stating
                # which step and what error.
                abort = f"step{step}:{type(e).__name__}:{str(e)[:200]}"
                print(f"task={tag} STEP_ERROR {abort}", flush=True)
            try:
                ev = world.evaluate()
                ev_s = str(ev.to_dict() if hasattr(ev, "to_dict") else ev)[:600]
            except Exception as e:  # Don't drop the trajectory just because evaluation failed.
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
