#!/usr/bin/env python
"""L4 (假相似) 生成器 —— ALFWorld 位置改换对,规范 L3L4_and_metrics_draft.md §2.2 第 1 类。

编辑族 varepsilon = "换 trial":同一个任务目录 (task_type-obj-mrecep-recep-scene) 下的
不同 trial_T*,任务指令逐字相同(引擎生成的 templated goal,本脚本逐字比对而不假设),
但物体初始摆放由不同随机种子生成 → 记忆里的搜索路线可能全部扑空。

收录判据(§2.1):
  1. 表面相似达标 sim(x', x) >= tau —— 本轮不做,见 --sim-filter(占位接口)。
     位置改换对指令逐字相同,是相似度的上界情形,tau 过滤预期几乎全过。
  2. 旧解回放必败 —— 逐条机械执行:把种子 trial 的专家演示动作序列原样喂给目标
     trial 的真引擎,终局 won == False 才收录。不通过即丢弃。

陷阱强度(§2.4)自动定级:
  d* = 首次矛盾信号(动作不在 admissible / 观察为 "Nothing happens" 等无变化反馈)
       之前已执行的轨迹比例 = i / len(demo)
  T1: d* < 0.25   T2: 0.25 <= d* < 1   T3: 全程无矛盾信号,仅终局判分失败(静默错误)

专家演示来源:alfworld 自带的 handcoded expert(AlfredExpert wrapper,
config.general.training_method='dagger' + train_eval='train' 时由
info["extra.expert_plan"] 逐步给出)。在种子 trial 上贪心跟随该 plan 直到 won,
得到的动作串即"存储解 pi*"。用活体 rollout 而不用 game.tw-pddl 里的 walkthrough 字段,
因为 walkthrough 的物体编号与 demangler 运行时编号不保证一致(实测有 alarmclock 2
vs alarmclock 1 的错位)。--demo-source walkthrough 保留另一条路供对照。

纯 CPU。随机种子固定,同参数重跑逐字节一致。
"""

import argparse
import json
import os
import random
import sys
import time
from collections import OrderedDict
from pathlib import Path

DEFAULT_SEED = 20260729
SCRIPT_VERSION = "gen_l4_alfworld.py/2026-07-30"

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_DATA_ROOT = REPO / "fig1_pilot" / "alfworld_data" / "json_2.1.1"
DEFAULT_CONFIG = REPO / "fig1_pilot" / "base_config.yaml"

# 观察文本里代表"环境什么也没发生"的反馈前缀(TextWorld/ALFRED 语法)
NO_CHANGE_PREFIXES = (
    "nothing happens",
    "you can't",
    "you cannot",
    "that's not something",
)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT),
                    help="json_2.1.1 目录")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="alfworld base config yaml")
    ap.add_argument("--split", default="train",
                    choices=["train", "valid_seen", "valid_train", "valid_unseen"])
    ap.add_argument("--task-type", default="pick_and_place_simple",
                    help="限定任务模板;--full 下被忽略(全模板)")
    ap.add_argument("--full", action="store_true",
                    help="遍历全部任务模板与全部候选对(慢,小时级)")
    ap.add_argument("--limit-pairs", type=int, default=0,
                    help="最多评估多少个候选对(0=不限)")
    ap.add_argument("--limit-valid", type=int, default=10,
                    help="收够多少个有效陷阱对就停(0=不限);--full 下默认不限")
    ap.add_argument("--demo-source", default="rollout", choices=["rollout", "walkthrough"])
    ap.add_argument("--max-demo-steps", type=int, default=150,
                    help="种子 rollout 的步数上限")
    ap.add_argument("--workers", type=int, default=1,
                    help="并行进程数;输出顺序与 workers 无关(按候选序回收)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=str(HERE / "l4_alfworld_pairs.jsonl"))
    ap.add_argument("--sim-filter", type=float, default=None, metavar="TAU",
                    help="[未实现] 表面相似度阈值 tau(§2.1 第 1 条)。等 bge-large "
                         "就位后接上;当前传入只会记进元数据并告警,不做任何过滤。")
    ap.add_argument("--trace-obs-chars", type=int, default=120,
                    help="回放轨迹里每步观察保留的字符数")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------
# 引擎
# --------------------------------------------------------------------------

_CFG = None
_ENV_MOD = None
_BASE_SEED = DEFAULT_SEED


def _reseed(*parts):
    """按内容确定性地重置全局 RNG。

    坑(实测):alfworld 的 HandCodedTWAgent 走的是全局 random,而全局 random 在每个
    进程启动时用 urandom 自动播种 —— 不管这个,同参数两次运行会给出不同的专家演示,
    进而不同的收录集合(第一次跑就撞上了:两次各 10 对,有 1 对不一样)。
    这里按 (基种子, 内容键) 逐次重播,既跨运行可复现,又与处理顺序/并行度无关。
    """
    import zlib
    key = "|".join(str(p) for p in parts).encode()
    s = (_BASE_SEED ^ zlib.crc32(key)) & 0x7FFFFFFF
    random.seed(s)
    try:
        import numpy as np
        np.random.seed(s % (2 ** 32))
    except Exception:
        pass


def _init_engine(config_path, data_root, base_seed=DEFAULT_SEED):
    """惰性初始化:装 alfworld 与 config(每个 worker 进程各做一次)。"""
    global _CFG, _ENV_MOD, _BASE_SEED
    _BASE_SEED = base_seed
    if _CFG is not None:
        return
    os.environ.setdefault("ALFWORLD_DATA", str(Path(data_root).parent))
    import yaml
    import alfworld.agents.environment as environment

    cfg = yaml.safe_load(open(config_path))
    cfg.setdefault("general", {})
    cfg["general"]["training_method"] = "dagger"   # 挂上 AlfredExpert,拿 expert_plan
    cfg["general"]["use_cuda"] = False             # 纯 CPU 铁律
    cfg["env"]["domain_randomization"] = False     # 命名必须可复现
    cfg.setdefault("dagger", {}).setdefault("training", {})
    _CFG = cfg
    _ENV_MOD = environment


def _make_env(game_file, max_steps):
    """只跑一个 game 文件的 batch=1 环境,跳过 AlfredTWEnv 的全库扫描。"""
    base_cls = _ENV_MOD.get_environment("AlfredTWEnv")

    class _OneGameEnv(base_cls):
        def __init__(self, config, game_files, train_eval="train"):
            self.config = config
            self.train_eval = train_eval
            self.game_files = list(game_files)
            self.num_games = len(self.game_files)

    cfg = _CFG
    cfg["dagger"]["training"]["max_nb_steps_per_episode"] = int(max_steps)
    return _OneGameEnv(cfg, [game_file]).init_env(batch_size=1)


def _task_of(obs_text):
    return obs_text.split("Your task is to:")[-1].strip()


def _is_no_change(obs_text):
    o = obs_text.strip().lower()
    return any(o.startswith(p) for p in NO_CHANGE_PREFIXES)


def expert_demo(game_file, max_steps):
    """在种子 trial 上跟随 handcoded expert 走到底,返回 (instruction, actions, won)。"""
    _reseed("demo", game_file, max_steps)
    env = _make_env(game_file, max_steps + 10)
    try:
        obs, info = env.reset()
        instruction = _task_of(obs[0])
        actions = []
        for i in range(max_steps):
            plan = info.get("extra.expert_plan") or [["look"]]
            act = plan[0][0] if isinstance(plan[0], (list, tuple)) else plan[0]
            obs, _scores, dones, info = env.step([act])
            # reset 后 expert 还没观察过环境,固定吐一个占位 "look",不算进 pi*
            if not (i == 0 and act == "look"):
                actions.append(act)
            if dones[0]:
                break
        won = bool(info.get("won", [False])[0])
        return instruction, actions, won
    finally:
        env.close()


def walkthrough_demo(game_file):
    with open(game_file) as f:
        return list(json.load(f).get("walkthrough") or [])


def replay(game_file, demo, obs_chars):
    """把 demo 机械回放到目标 trial,返回 (instruction, won, d_star, trace, first_bad)。"""
    _reseed("replay", game_file, "\x00".join(demo))
    env = _make_env(game_file, len(demo) + 10)
    try:
        obs, info = env.reset()
        instruction = _task_of(obs[0])
        trace = []
        d_star = None
        first_bad = None
        for i, act in enumerate(demo):
            admissible = act in info["admissible_commands"][0]
            obs, _scores, dones, info = env.step([act])
            otxt = obs[0].strip()
            no_change = _is_no_change(otxt)
            bad = (not admissible) or no_change
            trace.append({
                "i": i,
                "action": act,
                "admissible": admissible,
                "obs": otxt[:obs_chars],
            })
            if bad and d_star is None:
                d_star = i / len(demo)
                first_bad = {
                    "index": i,
                    "action": act,
                    "signal": "not_admissible" if not admissible else "no_change_feedback",
                    "obs": otxt[:obs_chars],
                }
            if dones[0]:
                break
        won = bool(info.get("won", [False])[0])
        return instruction, won, d_star, trace, first_bad
    finally:
        env.close()


def tier_of(d_star):
    """§2.4 陷阱强度分级。d_star is None ⇒ 全程无矛盾信号 ⇒ T3。"""
    if d_star is None:
        return "T3"
    if d_star < 0.25:
        return "T1"
    return "T2"


# --------------------------------------------------------------------------
# 候选枚举
# --------------------------------------------------------------------------

def parse_task_dir(name):
    """pick_and_place_simple-AlarmClock-None-Desk-307 → dict"""
    parts = name.split("-")
    if len(parts) < 5:
        return None
    return {
        "task_type": parts[0],
        "object": parts[1],
        "movable_recep": parts[2],
        "receptacle": parts[3],
        "scene": parts[4],
    }


def enumerate_candidates(data_root, split, task_type, full):
    """返回按路径排序的候选对列表 [(task_dir, seed_game, target_game, meta), ...]。

    同一任务目录下的有序对 (i, j), i != j —— 谁当种子谁当目标是两个不同的陷阱,
    d* 不对称(实测同一对反向 d* 可以从 0.25 变到 0.5),所以有序枚举。
    """
    root = Path(data_root) / split
    cands = []
    for task_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        name = task_dir.name
        # alfworld 官方 collect_game_files 同款排除
        if "movable" in name or "Sliced" in name:
            continue
        meta = parse_task_dir(name)
        if meta is None:
            continue
        if not full and task_type and meta["task_type"] != task_type:
            continue
        trials = sorted(t for t in task_dir.glob("trial_*/game.tw-pddl"))
        trials = [t for t in trials if _solvable(t)]
        if len(trials) < 2:
            continue
        for i, s in enumerate(trials):
            for j, t in enumerate(trials):
                if i == j:
                    continue
                cands.append((name, str(s), str(t), meta))
    return cands


def _solvable(game_file):
    try:
        with open(game_file) as f:
            return bool(json.load(f).get("solvable", False))
    except Exception:
        return False


# --------------------------------------------------------------------------
# 单对处理
# --------------------------------------------------------------------------

_DEMO_CACHE = OrderedDict()   # game_file -> (instruction, demo, won)
_DEMO_CACHE_MAX = 64


def _get_demo(game_file, args):
    key = (game_file, args.demo_source)
    if key in _DEMO_CACHE:
        _DEMO_CACHE.move_to_end(key)
        return _DEMO_CACHE[key]
    if args.demo_source == "walkthrough":
        demo = walkthrough_demo(game_file)
        # 指令仍需真引擎给,walkthrough 不带 goal 文本
        instruction, _, _ = expert_demo(game_file, 1)
        val = (instruction, demo, bool(demo))
    else:
        val = expert_demo(game_file, args.max_demo_steps)
    _DEMO_CACHE[key] = val
    if len(_DEMO_CACHE) > _DEMO_CACHE_MAX:
        _DEMO_CACHE.popitem(last=False)
    return val


def process_pair(cand, args):
    """返回 (status, record_or_reason)。status ∈ {'valid','reject','error'}"""
    task_dir, seed_game, target_game, meta = cand
    _init_engine(args.config, args.data_root, args.seed)
    try:
        instr_s, demo, won_s = _get_demo(seed_game, args)
        if not demo:
            return "reject", "empty_demo"
        if not won_s:
            return "reject", "seed_expert_failed"   # 种子上 pi* 本身不成立,没有"旧解"可谈

        instr_t, won_t, d_star, trace, first_bad = replay(target_game, demo, args.trace_obs_chars)

        if instr_s != instr_t:
            # 编辑族要求"指令逐字相同";引擎的 templated goal 有多种表面形式
            # (实测 'put a alarmclock in desk.' vs 'put some alarmclock on desk.'),
            # 不同就不是位置改换编辑,丢弃。
            return "reject", "instruction_mismatch"
        if won_t:
            # 旧解在目标 trial 上照样成功 ⇒ 不是陷阱(§2.1 第 2 条)
            return "reject", "replay_succeeded"

        tier = tier_of(d_star)
        rec = {
            "pair_id": f"alfworld/{args.split}/{task_dir}/{Path(seed_game).parent.name}"
                       f"->{Path(target_game).parent.name}",
            "level": "L4",
            "domain": "alfworld",
            "edit_family": "position_swap",       # §2.2 第 1 类:编辑 = 换 trial
            "split": args.split,
            "task_dir": task_dir,
            **meta,
            "instruction": instr_s,
            "instruction_identical": True,
            "seed_game": seed_game,
            "target_game": target_game,
            "seed_trial": Path(seed_game).parent.name,
            "target_trial": Path(target_game).parent.name,
            "demo_source": args.demo_source,
            "demo": demo,
            "demo_len": len(demo),
            "seed_expert_won": won_s,
            "replay_won": won_t,                  # 恒 False,收录判据
            "trap_valid": True,
            "d_star": d_star,
            "tier": tier,
            "first_contradiction": first_bad,
            "replay_trace": trace,
            "sim_filter": {"applied": False, "tau": args.sim_filter,
                           "note": "待 bge-large 就位后补 §2.1 第 1 条过滤"},
            "generator": SCRIPT_VERSION,
            "rng_seed": args.seed,
        }
        return "valid", rec
    except Exception as exc:  # 单对失败不该拖垮整批
        return "error", f"{type(exc).__name__}: {exc}"


def _worker(payload):
    cand, args_dict = payload
    args = argparse.Namespace(**args_dict)
    return process_pair(cand, args)


# --------------------------------------------------------------------------

def main(argv=None):
    args = parse_args(argv)
    if args.sim_filter is not None:
        print(f"[warn] --sim-filter {args.sim_filter} 收到但未实现(§2.1 第 1 条待 "
              f"bge-large 就位),本轮不做任何相似度过滤,仅记入元数据。", file=sys.stderr)
    if args.full and args.limit_valid == 10:
        args.limit_valid = 0

    t0 = time.time()
    cands = enumerate_candidates(args.data_root, args.split, args.task_type, args.full)
    rng = random.Random(args.seed)
    rng.shuffle(cands)          # 固定种子 ⇒ 候选序可复现
    if args.limit_pairs:
        cands = cands[:args.limit_pairs]
    scope = "全部任务模板" if args.full else f"task_type={args.task_type}"
    print(f"[enum] {len(cands)} 个候选有序对 (split={args.split}, {scope})")

    stats = {"evaluated": 0, "valid": 0, "reject": {}, "error": {}, "tier": {}}
    records = []

    def absorb(status, payload):
        stats["evaluated"] += 1
        if status == "valid":
            stats["valid"] += 1
            stats["tier"][payload["tier"]] = stats["tier"].get(payload["tier"], 0) + 1
            records.append(payload)
        elif status == "reject":
            stats["reject"][payload] = stats["reject"].get(payload, 0) + 1
        else:
            key = payload.split(":")[0]
            stats["error"][key] = stats["error"].get(key, 0) + 1

    if args.workers <= 1:
        for cand in cands:
            status, payload = process_pair(cand, args)
            absorb(status, payload)
            if args.limit_valid and stats["valid"] >= args.limit_valid:
                break
    else:
        # 分块并行:块内并行、块间串行,收够即停。
        # 结果按候选序回收后再截断 ⇒ 输出与 --workers 取值无关。
        import multiprocessing as mp
        args_dict = vars(args)
        chunk = max(args.workers * 4, 8)
        with mp.get_context("spawn").Pool(args.workers) as pool:
            for start in range(0, len(cands), chunk):
                block = cands[start:start + chunk]
                for status, payload in pool.map(_worker, [(c, args_dict) for c in block]):
                    absorb(status, payload)
                if args.limit_valid and stats["valid"] >= args.limit_valid:
                    break
    if args.limit_valid:
        records = records[:args.limit_valid]
        stats["valid"] = len(records)
        stats["tier"] = {}
        for r in records:
            stats["tier"][r["tier"]] = stats["tier"].get(r["tier"], 0) + 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    stats.update(
        candidates_enumerated=len(cands),
        elapsed_s=round(time.time() - t0, 1),
        out=str(out),
        seed=args.seed,
        generator=SCRIPT_VERSION,
        args=vars(args),
    )
    with open(str(out) + ".stats.json", "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"[done] 评估 {stats['evaluated']} 对 → 有效陷阱 {stats['valid']} 对 "
          f"({stats['elapsed_s']}s)")
    print(f"       档位分布 {stats['tier']}")
    print(f"       丢弃原因 {stats['reject']}")
    if stats["error"]:
        print(f"       异常 {stats['error']}")
    print(f"       → {out}")


if __name__ == "__main__":
    main()
