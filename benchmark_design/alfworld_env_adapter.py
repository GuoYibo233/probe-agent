#!/usr/bin/env python
"""ALFWorld EnvAdapter —— 把真 TextWorld 引擎包成记忆被试要的 reset/step 协议。

对齐目标:`related_work/evo_mem_INTEGRATION.md` §2.3 约定的鸭子类型环境

    class EnvAdapter:
        def reset(self) -> str                      # 初始 observation
        def step(self, action: str) -> tuple        # (obs, reward, done, info)
            # info 需含 {"success": bool, "progress": float}

被试侧(`evo_memory/agents/*.py::run_multi_turn`)真正用到的只有:
`environment.reset()` 的返回值当第一条观察、`environment.step(action_str)` 解包成
四元组、`info["progress"]` 读进度、`done` 时 `info.get("success", False)` 定成败。
本适配器逐条满足,并额外挂了一批诊断字段(见 §info 契约),多出来的字段被试会无视。

引擎侧沿用 `benchmark_design/gen_l4_alfworld.py`(D 线真引擎回放验证)那一套:
`AlfredTWEnv` 子类只喂一个 game 文件、跳过全库扫描;`domain_randomization=False`
保证物体编号可复现;纯 CPU。venv 用 `fig1_pilot/fig1-env`(alfworld + textworld 1.7.0
装在那里;`jlens-env` 没有 alfworld,见 GEN_REPORT.md 坑 10)。

--------------------------------------------------------------------------
info 契约
--------------------------------------------------------------------------
协议必需:
  success   bool   引擎的 won(只有真赢才 True;超步截断是 False)
  progress  float  score / max_score。**alfred 游戏没有中间分**:score 全程 0,
                   达成目标那一步跳 1,max_score 引擎不给(恒 None)⇒ 兜底 1.0。
                   所以 progress 事实上是二值的,想要部分进度只能用我们自己的
                   d*/档位机器(gen_l4_alfworld.py),别指望引擎。
诊断附加:
  won / lost / done / truncated / after_done
  score / max_score / reward / steps / max_steps
  action_raw / action / alias_used / admissible / world_changed / no_change_feedback
  invalid_action        = (not admissible) or no_change_feedback,与 gen_l4 的
                         "矛盾信号"判据同口径,可直接拿来算 d*
  admissible_commands   当前步之后的合法动作表
  goal / game_file / task_id / expert_plan(仅 expert_plan=True 时)

reward 定义为本步的 score 增量(0 或 1),累计分在 info["score"]。
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

DEFAULT_SEED = 20260729
ADAPTER_VERSION = "alfworld_env_adapter.py/2026-07-30"

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_DATA_ROOT = REPO / "fig1_pilot" / "alfworld_data" / "json_2.1.1"
DEFAULT_CONFIG = REPO / "fig1_pilot" / "base_config.yaml"

# 观察文本里代表"环境什么也没发生"的反馈前缀(与 gen_l4_alfworld.py 同一张表)
NO_CHANGE_PREFIXES = (
    "nothing happens",
    "you can't",
    "you cannot",
    "that's not something",
)

_BANNER_RE = re.compile(r"^-=\s*Welcome to TextWorld.*?=-\s*", re.DOTALL)
_ACTION_PREFIX_RE = re.compile(r"^(?:>\s*|action\s*:\s*|命令\s*:\s*)", re.IGNORECASE)
_PUT_RE = re.compile(r"^put\s+(.+?)\s+(?:in/on|into|onto|in|on|to)\s+(.+)$")


# --------------------------------------------------------------------------
# 任务解析
# --------------------------------------------------------------------------

def resolve_game_file(task: Union[str, Path, Dict[str, Any]],
                      data_root: Union[str, Path] = DEFAULT_DATA_ROOT,
                      split: str = "train") -> Path:
    """把各种写法的 task 归一成 game.tw-pddl 的绝对路径。

    支持:
      - 直接给 .tw-pddl 文件路径
      - 给 trial 目录(里面有 game.tw-pddl)
      - 给 "<task_dir>/<trial>" 或 "<split>/<task_dir>/<trial>"(相对 data_root)
      - 只给 "<task_dir>":取排序后第一个 trial(确定性,便于随手冒烟)
      - 给 dict(例如 l4_alfworld_pairs.jsonl 的一条记录):依次试
        game_file / target_game / seed_game,再退回 split+task_dir+trial 拼路径
    """
    data_root = Path(data_root)

    if isinstance(task, dict):
        for key in ("game_file", "target_game", "seed_game"):
            if task.get(key):
                return resolve_game_file(task[key], data_root, task.get("split", split))
        task_dir = task.get("task_dir")
        trial = task.get("trial") or task.get("target_trial") or task.get("seed_trial")
        if task_dir and trial:
            return resolve_game_file(f"{task_dir}/{trial}", data_root,
                                     task.get("split", split))
        raise ValueError(f"无法从 dict 里解析出游戏文件:keys={sorted(task)}")

    p = Path(str(task))
    cands: List[Path] = []
    if p.is_absolute():
        cands.append(p)
    else:
        cands += [data_root / split / p, data_root / p, Path.cwd() / p]

    for c in cands:
        if c.is_file():
            return c.resolve()
        if (c / "game.tw-pddl").is_file():
            return (c / "game.tw-pddl").resolve()
        if c.is_dir():
            trials = sorted(c.glob("trial_*/game.tw-pddl"))
            if trials:
                return trials[0].resolve()
    raise FileNotFoundError(f"找不到游戏文件:task={task!r}(试过 {[str(c) for c in cands]})")


# --------------------------------------------------------------------------
# 适配器
# --------------------------------------------------------------------------

class AlfWorldEnvAdapter:
    """一个 adapter 实例 = 一个 batch-1 的真 TextWorld 引擎坐席。

    典型用法(被试侧)::

        env = AlfWorldEnvAdapter(task=rec["target_game"])   # 或 reset(task=...) 时再给
        success, progress, state = agent.run_multi_turn(
            task_id=env.task_id, goal=env.goal, environment=env,
            environment_info=env.environment_info())
        env.close()

    reset 既支持协议要求的无参调用(被试就是这么调的),也支持 `reset(task)` 换游戏
    ——同一个 adapter 可以串着跑一条任务流,省下反复建引擎的开销。
    """

    def __init__(self,
                 task: Union[str, Path, Dict[str, Any], None] = None,
                 *,
                 data_root: Union[str, Path] = DEFAULT_DATA_ROOT,
                 config_path: Union[str, Path] = DEFAULT_CONFIG,
                 split: str = "train",
                 max_steps: int = 50,
                 seed: int = DEFAULT_SEED,
                 expert_plan: bool = False,
                 alias_actions: bool = True,
                 strip_banner: bool = False,
                 task_id: Optional[str] = None):
        self.data_root = Path(data_root)
        self.config_path = Path(config_path)
        self.split = split
        self.max_steps = int(max_steps)
        self.seed = int(seed)
        self.expert_plan = bool(expert_plan)
        self.alias_actions = bool(alias_actions)
        self.strip_banner = bool(strip_banner)

        self._pending_task = task
        self._env = None
        self._env_key = None
        self._info: Dict[str, Any] = {}
        self.game_file: Optional[Path] = None
        self.task_id: Optional[str] = task_id
        self.goal: str = ""
        self.initial_observation: str = ""
        self.last_observation: str = ""
        self.steps: int = 0
        self.score: int = 0
        self.max_score: float = 1.0
        self.done: bool = False
        self.won: bool = False
        self.history: List[Dict[str, Any]] = []
        self._cfg = None

    # -- 引擎 ------------------------------------------------------------

    def _reseed(self, *parts):
        """按内容确定性播全局 RNG。

        GEN_REPORT.md 坑 1:alfworld 的 handcoded expert 走全局 `random`,而全局
        random 每个进程用 urandom 自动播种 —— 不管它,expert_plan 跨运行不可复现。
        expert_plan=False 时用不到 expert,但照播无害,保持与 gen_l4 同口径。
        """
        key = "|".join(str(p) for p in parts).encode()
        s = (self.seed ^ zlib.crc32(key)) & 0x7FFFFFFF
        random.seed(s)
        try:
            import numpy as np
            np.random.seed(s % (2 ** 32))
        except Exception:
            pass

    def _load_config(self):
        if self._cfg is not None:
            return self._cfg
        os.environ.setdefault("ALFWORLD_DATA", str(self.data_root.parent))
        import yaml
        cfg = yaml.safe_load(open(self.config_path))
        cfg.setdefault("general", {})
        cfg["general"]["use_cuda"] = False              # 纯 CPU 铁律
        cfg.setdefault("env", {})
        cfg["env"]["domain_randomization"] = False      # 物体编号必须可复现
        self._cfg = cfg
        return cfg

    def _build_env(self, game_file: Path):
        """建一个只跑这一个 game 的 batch-1 环境。

        不直接用 AlfredTWEnv.init_env,因为它的 request_infos 里没有 score/moves,
        而 moves 是判"世界到底动了没有"最干净的引擎级信号(失败动作不涨 moves)。
        """
        import textworld
        import textworld.gym
        import alfworld.agents.environment as environment
        from alfworld.agents.environment.alfred_tw_env import (
            AlfredDemangler, AlfredExpert, AlfredInfos)

        cfg = self._load_config()
        base_cls = environment.get_environment("AlfredTWEnv")

        class _OneGameEnv(base_cls):
            def __init__(self, config, game_files):
                self.config = config
                self.train_eval = "train"
                self.game_files = list(game_files)
                self.num_games = len(self.game_files)

        wrappers = [AlfredDemangler(shuffle=False), AlfredInfos]
        request_infos = textworld.EnvInfos(
            won=True, lost=True, score=True, max_score=True, moves=True,
            admissible_commands=True, command_templates=True, extras=["gamefile"])
        extras_expert = False
        if self.expert_plan:
            wrappers.append(AlfredExpert(cfg["env"].get("expert_type", "handcoded")))
            request_infos.extras.append("expert_plan")
            extras_expert = True

        _ = _OneGameEnv(cfg, [str(game_file)])   # 保留库侧构造语义(config 校验)
        env_id = textworld.gym.register_games(
            [str(game_file)], request_infos, batch_size=1, asynchronous=True,
            max_episode_steps=self.max_steps, wrappers=wrappers)
        self._has_expert_extra = extras_expert
        return textworld.gym.make(env_id)

    # -- 协议 ------------------------------------------------------------

    def reset(self, task: Union[str, Path, Dict[str, Any], None] = None) -> str:
        """加载(或重载)游戏,返回初始观察。

        协议要求 `reset()` 无参可调 —— 被试就是这么调的;`task` 是我们自己的
        任务流用的扩展,给了就换游戏。
        """
        if task is not None:
            self._pending_task = task
            self.task_id = None
        if self._pending_task is None:
            raise ValueError("没有指定 task:构造时传 task=,或 reset(task=...)")

        game_file = resolve_game_file(self._pending_task, self.data_root, self.split)
        key = (str(game_file), self.max_steps, self.expert_plan)
        if key != self._env_key:
            self.close()
            self._reseed("build", game_file)
            self._env = self._build_env(game_file)
            self._env_key = key
        self.game_file = game_file
        if not self.task_id:
            # 稳定可读的任务号:alfworld/<split>/<task_dir>/<trial>
            self.task_id = "/".join(["alfworld", self.split,
                                     game_file.parent.parent.name, game_file.parent.name])

        self._reseed("reset", game_file)
        obs, info = self._env.reset()
        self._info = info
        text = self._clean_obs(obs[0])
        self.initial_observation = text
        self.last_observation = text
        self.goal = text.split("Your task is to:")[-1].strip() if "Your task is to:" in text else ""
        self.steps = 0
        self.score = int(self._scalar("score") or 0)
        ms = self._scalar("max_score")
        self.max_score = float(ms) if ms else 1.0     # 引擎对 alfred 恒给 None
        self.done = False
        self.won = False
        self.history = []
        return text

    def step(self, action: Any) -> Tuple[str, float, bool, Dict[str, Any]]:
        """执行一个动作,返回 (obs, reward, done, info)。

        容错(全部不抛异常,坏动作只是"什么也没发生"):
          - 非字符串 / None / 空串 → 归一成字符串照喂,引擎回 "Nothing happens."
          - 大小写、`Action:` 前缀、引号、句末标点 → 归一化后再喂
            (**坑**:引擎大小写敏感,`Go To Sofa 1` 直接静默变 Nothing happens)
          - `put X in/on Y` → 保守改写成 `move X to Y`(仅当改写后才合法)
          - 终局之后再 step → 不再动引擎,原地返回终局观察,info["after_done"]=True
        """
        if self._env is None:
            raise RuntimeError("先 reset() 再 step()")

        raw = "" if action is None else str(action)
        norm, alias_used = self._normalize_action(raw)

        if self.done:
            info = self._pack_info(reward=0.0, raw=raw, norm=norm, alias_used=alias_used,
                                   admissible=False, world_changed=False,
                                   no_change=False, after_done=True)
            return self.last_observation, 0.0, True, info

        admissible_before = self.admissible_commands
        admissible = norm in admissible_before
        moves_before = self._scalar("moves") or 0

        obs, scores, dones, info = self._env.step([norm])
        self._info = info
        text = self._clean_obs(obs[0])
        self.last_observation = text
        self.steps += 1

        prev_score = self.score
        self.score = int(self._first(scores) or 0)
        reward = float(self.score - prev_score)
        self.done = bool(self._first(dones))
        self.won = bool(self._scalar("won"))
        moves_after = self._scalar("moves") or 0
        world_changed = moves_after > moves_before
        no_change = self._is_no_change(text)

        out = self._pack_info(reward=reward, raw=raw, norm=norm, alias_used=alias_used,
                              admissible=admissible, world_changed=world_changed,
                              no_change=no_change, after_done=False)
        self.history.append({
            "i": self.steps - 1, "action": norm, "action_raw": raw,
            "admissible": admissible, "reward": reward, "score": self.score,
            "done": self.done, "won": self.won, "obs": text[:200],
        })
        return text, reward, self.done, out

    def close(self):
        if self._env is not None:
            try:
                self._env.close()
            except Exception:
                pass
        self._env = None
        self._env_key = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # -- 给被试的动作空间说明(run_multi_turn 的 environment_info kwarg)------

    def environment_info(self, include_admissible: bool = True) -> str:
        lines = [
            "You are interacting with a text-based household environment (ALFWorld / TextWorld).",
            "Emit exactly one command per turn, lowercase, no trailing punctuation.",
            "Command templates supported by this engine:",
        ]
        for t in self.command_templates:
            lines.append(f"  - {t}")
        lines += [
            "Notes:",
            "  - '{r}' is a receptacle (e.g. 'drawer 1'), '{o}' an object (e.g. 'mug 2').",
            "  - To place a held object use 'move <obj> to <recep>'"
            " (this engine's grammar has no 'put <obj> in/on <recep>').",
            "  - You must 'go to <recep>' before interacting with things on/in it,"
            " and 'open <recep>' before taking from a closed one.",
            "  - Unparsable or illegal commands answer 'Nothing happens.' and waste a step.",
        ]
        if include_admissible and self.admissible_commands:
            lines.append("Currently admissible commands: "
                         + ", ".join(self.admissible_commands))
        return "\n".join(lines)

    # -- 只读视图 --------------------------------------------------------

    @property
    def admissible_commands(self) -> List[str]:
        v = self._info.get("admissible_commands")
        return list(v[0]) if v else []

    @property
    def command_templates(self) -> List[str]:
        v = self._info.get("command_templates")
        if not v or v[0] is None:
            return []
        return list(v[0])

    @property
    def expert_next_action(self) -> Optional[str]:
        """expert_plan=True 时:handcoded expert 建议的下一步(诊断用,非协议)。"""
        v = self._info.get("extra.expert_plan")
        if not v or not v[0]:
            return None
        a = v[0][0] if isinstance(v[0], (list, tuple)) else v[0]
        return a

    @property
    def progress(self) -> float:
        return min(1.0, max(0.0, self.score / (self.max_score or 1.0)))

    # -- 内部 ------------------------------------------------------------

    @staticmethod
    def _first(seq):
        try:
            return seq[0]
        except Exception:
            return seq

    def _scalar(self, key):
        v = self._info.get(key)
        if isinstance(v, (list, tuple)):
            return v[0] if v else None
        return v

    def _clean_obs(self, text: str) -> str:
        t = text.strip()
        if self.strip_banner:
            t = _BANNER_RE.sub("", t).strip()
        return t

    @staticmethod
    def _is_no_change(text: str) -> bool:
        o = text.strip().lower()
        return any(o.startswith(p) for p in NO_CHANGE_PREFIXES)

    def _normalize_action(self, raw: str) -> Tuple[str, bool]:
        a = raw.strip()
        a = _ACTION_PREFIX_RE.sub("", a).strip()
        a = a.strip("`\"'“”‘’ ").strip()
        a = re.sub(r"\s+", " ", a).lower()
        a = a.rstrip(".,;!?。 ").strip()
        if not self.alias_actions or not a:
            return a, False
        # 保守别名:只有"原样不合法、改写后合法"才动手,免得把引擎真支持的
        # 'put {outero} in {r}' / 'put {o} into {outero}' 也改掉。
        adm = self.admissible_commands
        if adm and a not in adm:
            m = _PUT_RE.match(a)
            if m:
                cand = f"move {m.group(1).strip()} to {m.group(2).strip()}"
                if cand in adm:
                    return cand, True
        return a, False

    def _pack_info(self, *, reward, raw, norm, alias_used, admissible,
                   world_changed, no_change, after_done) -> Dict[str, Any]:
        truncated = bool(self.done and not self.won and self.steps >= self.max_steps)
        info = {
            # —— 协议必需 ——
            "success": bool(self.won),
            "progress": self.progress,
            # —— 终局与计分 ——
            "won": bool(self.won),
            "lost": bool(self._scalar("lost")),
            "done": bool(self.done),
            "truncated": truncated,
            "after_done": bool(after_done),
            "score": self.score,
            "max_score": self.max_score,
            "reward": reward,
            "steps": self.steps,
            "max_steps": self.max_steps,
            # —— 动作诊断(算 d*/矛盾信号用,与 gen_l4_alfworld.py 同口径)——
            "action_raw": raw,
            "action": norm,
            "alias_used": alias_used,
            "admissible": admissible,
            "world_changed": world_changed,
            "no_change_feedback": no_change,
            "invalid_action": bool((not admissible) or no_change),
            "admissible_commands": self.admissible_commands,
            # —— 身份 ——
            "goal": self.goal,
            "task_id": self.task_id,
            "game_file": str(self.game_file) if self.game_file else None,
            "adapter": ADAPTER_VERSION,
        }
        if self.expert_plan:
            info["expert_plan"] = self.expert_next_action
        return info


# 协议里的名字(INTEGRATION §2.3 写作 EnvAdapter)
EnvAdapter = AlfWorldEnvAdapter


# ==========================================================================
# 冒烟
# ==========================================================================

# 三个游戏 + 一串硬编码的合法动作。动作串取自 D 线 gen_l4_alfworld.py 真引擎
# rollout 出来并验证 won=True 的 pi*(l4_alfworld_pairs.jsonl 的 seed 侧),
# 这里写死,冒烟不依赖任何数据文件。
SMOKE_GAMES = [
    {
        "trial": "pick_and_place_simple-RemoteControl-None-Dresser-217/"
                 "trial_T20190909_053839_725206",
        "goal": "put some remotecontrol on dresser.",
        "actions": [
            "go to sofa 1",
            "take remotecontrol 1 from sofa 1",
            "go to dresser 1",
            "move remotecontrol 1 to dresser 1",
        ],
    },
    {
        "trial": "pick_and_place_simple-CellPhone-None-Safe-323/"
                 "trial_T20190907_234512_145231",
        "goal": "put a cellphone in safe.",
        "actions": [
            "go to sidetable 1", "go to sidetable 2", "go to safe 1", "open safe 1",
            "close safe 1", "go to dresser 1", "take cellphone 2 from dresser 1",
            "go to safe 1", "open safe 1", "move cellphone 2 to safe 1",
        ],
    },
    {
        "trial": "pick_and_place_simple-Candle-None-Toilet-409/"
                 "trial_T20190908_142251_407168",
        "goal": "put a candle in toilet.",
        "actions": [
            "go to toilet 1", "go to drawer 1", "open drawer 1", "close drawer 1",
            "go to drawer 2", "open drawer 2", "close drawer 2", "go to drawer 3",
            "open drawer 3", "take candle 2 from drawer 3", "close drawer 3",
            "go to toilet 1", "move candle 2 to toilet 1",
        ],
    },
]

# 前三条是"表面脏、语义合法"的写法(归一化能救回),后四条是真非法。
# 三条各去不同的家具:引擎里"go to <当前位置>"本身就不合法,复用同一个目标会
# 把"已经站在那儿"误当成归一化失败。
# 一个 L4 位置改换陷阱对(GEN_REPORT.md §1 冒烟第 1 条):同一任务目录换 trial,
# 指令逐字相同,把种子 trial 的 pi* 原样喂给目标 trial 会在第 6 步(take ... from
# dresser 1)扑空。用来交叉验证本适配器的 invalid_action 与 D 线生成器同口径。
L4_PARITY = {
    "target_trial_path": "pick_and_place_simple-CellPhone-None-Safe-323/"
                         "trial_T20190907_234526_733036",
    "demo": [
        "go to sidetable 1", "go to sidetable 2", "go to safe 1", "open safe 1",
        "close safe 1", "go to dresser 1", "take cellphone 2 from dresser 1",
        "go to safe 1", "open safe 1", "move cellphone 2 to safe 1",
    ],
    "first_bad_index": 6,
    "d_star": 0.6,
}

BAD_ACTIONS = [
    "Go To Sofa 1",                        # 大小写 → 归一化救回
    "go to dresser 1.",                    # 句末句号 → 归一化救回
    "  Action: go to coffeetable 1  ",     # 前缀 + 多余空白 → 归一化救回
    "fly to the moon",                     # 纯胡说
    "take remotecontrol 1 from dresser 1",  # 语法对、事实不成立(人不在 dresser 前)
    "open sofa 1",                         # 对象类型不对(沙发不能开)
    "",                                    # 空动作
    None,                                  # 连字符串都不是
]


def _fail(msg):
    raise AssertionError(msg)


def _check(cond, msg):
    print(f"    {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        _fail(msg)


def smoke(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--obs-chars", type=int, default=90)
    ap.add_argument("--games", type=int, default=3)
    args = ap.parse_args(argv)

    def mk(task, **kw):
        return AlfWorldEnvAdapter(task, data_root=args.data_root,
                                  config_path=args.config, **kw)

    print("=" * 78)
    print(f"ALFWorld EnvAdapter 冒烟  ({ADAPTER_VERSION})")
    print(f"data_root = {args.data_root}")
    print("=" * 78)

    # ---- 1. 协议签名 -----------------------------------------------------
    print("\n[1] 协议签名(INTEGRATION §2.3)")
    import inspect
    sig_reset = inspect.signature(AlfWorldEnvAdapter.reset)
    required = [p for n, p in list(sig_reset.parameters.items())[1:]
                if p.default is inspect.Parameter.empty]
    _check(not required, "reset() 可无参调用(被试就是这么调的)")
    _check(len(inspect.signature(AlfWorldEnvAdapter.step).parameters) == 2,
           "step(action) 单参")

    # ---- 2. 三个游戏走通 reset→step→终局 --------------------------------
    print("\n[2] 硬编码合法动作串:reset → step → 终局")
    finals = []
    for gi, g in enumerate(SMOKE_GAMES[:args.games], 1):
        env = mk(g["trial"])
        obs = env.reset()
        print(f"\n  --- 游戏 {gi}: {g['trial'].split('/')[0]}")
        print(f"      task_id : {env.task_id}")
        print(f"      初始观察: {obs[:260].replace(chr(10), ' | ')}")
        print(f"      goal    : {env.goal!r}   (期望 {g['goal']!r})")
        _check(isinstance(obs, str) and len(obs) > 50, "reset() 返回非空字符串观察")
        _check(env.goal == g["goal"], "初始观察里的任务指令与预期逐字相同")
        _check(len(env.admissible_commands) > 0, "reset 后拿到 admissible_commands")

        prev_done = False
        for a in g["actions"]:
            o, r, d, info = env.step(a)
            flag = "" if info["admissible"] else "  <== NOT ADMISSIBLE"
            print(f"      [{info['steps']:>2}] {a:<38} r={r:+.0f} score={info['score']} "
                  f"done={int(d)} success={int(info['success'])} "
                  f"| {o[:args.obs_chars].replace(chr(10), ' ')}{flag}")
            _check(isinstance(o, str), f"step 返回观察是字符串 ({a})")
            if not prev_done:
                _check(info["admissible"], f"硬编码动作合法:{a}")
            prev_done = d
        _check(d is True, "最后一步 done=True")
        _check(info["success"] is True, "info['success']=True(引擎 won)")
        _check(info["progress"] == 1.0, "info['progress']=1.0")
        _check(info["truncated"] is False, "终局不是超步截断")
        _check(info["score"] == 1 and r == 1.0, "达成目标那一步 score 0→1、reward=+1")
        finals.append((env.task_id, info["score"], info["success"]))

        # 终局之后再 step:不抛异常、不再动引擎
        o2, r2, d2, i2 = env.step("look")
        _check(d2 is True and i2["after_done"] is True and o2 == o,
               "终局后再 step:done 保持 True、after_done=True、观察不变")
        env.close()

    # ---- 3. 非法动作容错 -------------------------------------------------
    print("\n[3] 非法动作容错(同一集里先乱来,再照样完成任务)")
    g = SMOKE_GAMES[0]
    env = mk(g["trial"])
    env.reset()
    for a in BAD_ACTIONS:
        o, r, d, info = env.step(a)
        tag = ("归一化后合法" if info["admissible"] else
               ("别名改写" if info["alias_used"] else "引擎拒绝"))
        print(f"      {str(a)!r:<40} -> {o[:70].replace(chr(10),' ')!r:<74} "
              f"norm={info['action']!r} adm={int(info['admissible'])} "
              f"world_changed={int(info['world_changed'])} "
              f"invalid={int(info['invalid_action'])} done={int(d)} [{tag}]")
        _check(isinstance(o, str) and d is False and info["success"] is False,
               f"坏动作不抛异常、不终局、success 保持 False:{a!r}")
    # 三个"归一化能救回"的、以及四个真非法的,分别核对
    hist = env.history
    _check(all(h["admissible"] for h in hist[:3]),
           "大小写/句号/Action: 前缀三例被归一化救回,成为合法动作")
    _check(all(not h["admissible"] for h in hist[3:]),
           "胡说/事实不成立/类型不对/空动作四例判为非法")
    _check(all(env._is_no_change(h["obs"]) for h in hist[3:]),
           "四例非法动作的观察都是 'Nothing happens.' 一类无变化反馈")
    # 乱来之后世界状态没被搞坏:继续把任务做完
    for a in g["actions"]:
        o, r, d, info = env.step(a)
    _check(info["success"] is True, "乱来 8 步之后仍能完成任务(引擎状态未被污染)")
    print(f"      收官:steps={info['steps']} score={info['score']} "
          f"success={info['success']}")
    env.close()

    # ---- 4. put 别名 ------------------------------------------------------
    print("\n[4] 'put X in/on Y' 别名(论文/ReAct 提示词里的写法,本引擎语法没有)")
    env = mk(g["trial"])
    env.reset()
    for a in g["actions"][:3]:
        env.step(a)
    o, r, d, info = env.step("put remotecontrol 1 in/on dresser 1")
    print(f"      raw={info['action_raw']!r} -> norm={info['action']!r} "
          f"alias_used={info['alias_used']} | {o[:70]}")
    _check(info["alias_used"] and info["success"] is True,
           "'put X in/on Y' 被保守改写成 'move X to Y' 并完成任务")
    env.close()

    env = mk(g["trial"], alias_actions=False)
    env.reset()
    for a in g["actions"][:3]:
        env.step(a)
    o, r, d, info = env.step("put remotecontrol 1 in/on dresser 1")
    print(f"      alias_actions=False 时:{o[:60]!r} invalid={info['invalid_action']}")
    _check(info["invalid_action"] and not info["success"],
           "关掉别名后同一动作被引擎拒绝(证明别名确实在起作用,不是巧合)")
    env.close()

    # ---- 5. 超步截断 ≠ 成功 ---------------------------------------------
    print("\n[5] 超步截断:done=True 但 success=False")
    env = mk(g["trial"], max_steps=3)
    env.reset()
    for i in range(3):
        o, r, d, info = env.step("look")
    print(f"      steps={info['steps']} done={d} success={info['success']} "
          f"truncated={info['truncated']} progress={info['progress']}")
    _check(d is True and info["success"] is False and info["truncated"] is True,
           "步数用尽 → done=True / success=False / truncated=True")
    env.close()

    # ---- 6. 可复现 -------------------------------------------------------
    print("\n[6] 可复现(固定种子 + domain_randomization=False)")
    def run_once(trial, actions):
        env = mk(trial)
        obs = env.reset()
        rec = [obs]
        for a in actions:
            o, r, d, i = env.step(a)
            rec.append(f"{a}|{r}|{d}|{o}")
        env.close()
        return hashlib.md5("\n".join(rec).encode()).hexdigest()

    h1 = run_once(g["trial"], g["actions"])
    h2 = run_once(g["trial"], g["actions"])
    env = mk(g["trial"])
    o_a = env.reset(); o_b = env.reset()          # 同一实例二次 reset
    env.close()
    print(f"      两个实例整集轨迹 md5: {h1} / {h2}")
    _check(h1 == h2, "两次独立运行的整集轨迹 md5 相同")
    _check(o_a == o_b, "同一实例二次 reset 观察逐字相同")

    # ---- 7. 一个实例串跑多任务 -------------------------------------------
    print("\n[7] 一个 adapter 串跑多任务(reset(task) 换游戏)")
    env = mk(SMOKE_GAMES[0]["trial"])
    seen = []
    for g2 in SMOKE_GAMES[:args.games]:
        env.reset(task=g2["trial"])
        for a in g2["actions"]:
            o, r, d, info = env.step(a)
        seen.append((env.goal, info["success"], info["steps"]))
        print(f"      {env.goal:<36} success={info['success']} steps={info['steps']}")
    env.close()
    _check(all(s[1] for s in seen), "串跑的每个任务都到 won")
    _check(len({s[0] for s in seen}) == len(seen), "换 task 确实换了游戏(指令各不相同)")

    # ---- 8. 真被试代码路径(evo_mem ReActAgent + 桩 LLM,零 API)----------
    print("\n[8] 真被试代码路径:evo_memory ReActAgent.run_multi_turn(桩 LLM,不联网)")
    ok8 = _smoke_with_evomem(mk, SMOKE_GAMES[0])
    _check(ok8, "被试 run_multi_turn 驱动本适配器 → success=True / progress=1.0")

    # ---- 9. expert_plan 通道 --------------------------------------------
    print("\n[9] expert_plan=True:引擎自带 handcoded expert 逐步带路")
    env = mk(SMOKE_GAMES[1]["trial"], expert_plan=True, max_steps=60)
    env.reset()
    acts = []
    for _ in range(60):
        a = env.expert_next_action or "look"
        acts.append(a)
        o, r, d, info = env.step(a)
        if d:
            break
    print(f"      expert 自己走了 {info['steps']} 步 → success={info['success']}")
    print(f"      前 5 步: {acts[:5]}")
    _check(info["success"] is True, "expert 通道能独立走到 won")
    _check(all(h["admissible"] for h in env.history), "expert 给的每一步都合法")
    env.close()

    # ---- 10. 与 D 线生成器口径一致 ---------------------------------------
    print("\n[10] 与 gen_l4_alfworld.py 的矛盾信号/d* 口径一致(硬编码 L4 陷阱对)")
    env = mk(L4_PARITY["target_trial_path"], max_steps=len(L4_PARITY["demo"]) + 5)
    env.reset()
    first = None
    for i, a in enumerate(L4_PARITY["demo"]):
        o, r, d, info = env.step(a)
        if info["invalid_action"] and first is None:
            first = i
        if d:
            break
    d_star = None if first is None else first / len(L4_PARITY["demo"])
    print(f"      旧解回放 target trial: won={info['success']} "
          f"首次矛盾@{first} ({L4_PARITY['demo'][first]!r}) d*={d_star:.3f}")
    print(f"      GEN_REPORT.md 冒烟第 1 条记的是 首次矛盾@{L4_PARITY['first_bad_index']} "
          f"d*={L4_PARITY['d_star']:.3f}")
    _check(info["success"] is False, "L4 陷阱对上旧解回放确实失败")
    _check(first == L4_PARITY["first_bad_index"] and abs(d_star - L4_PARITY["d_star"]) < 1e-9,
           "info['invalid_action'] 定出的首次矛盾点与 d* 与 D 线生成器逐位相同")
    env.close()

    print("\n" + "=" * 78)
    print("SMOKE OK —— 10 组检查全通")
    print("=" * 78)
    return 0


def _smoke_with_evomem(mk, game) -> bool:
    """用 evo_mem 的真 agent(ReActAgent)驱动适配器,LLM 换成回放桩。

    目的是让协议对齐这件事不靠我自己复述:被试侧的 reset()/step() 解包、
    info["progress"]、info["success"] 全部走它自己的代码。
    """
    evo = REPO / "related_work" / "evo_mem"
    if str(evo) not in sys.path:
        sys.path.insert(0, str(evo))
    try:
        from evo_memory.agents.react import ReActAgent
        from evo_memory.llm.base import BaseLLM, LLMResponse
    except Exception as exc:
        print(f"      SKIP(evo_memory 不可导入:{type(exc).__name__}: {exc})")
        return True

    class ScriptedLLM(BaseLLM):
        """按硬编码动作串逐条吐 'Thought/Action',不发任何网络请求。"""

        def __init__(self, actions):
            super().__init__(model_name="scripted-stub", api_key="none")
            self.actions = list(actions)
            self.i = 0

        def _generate(self, messages, **kwargs):
            a = self.actions[self.i] if self.i < len(self.actions) else "look"
            self.i += 1
            return LLMResponse(
                content=f"Thought: replaying stored plan step {self.i}.\nAction: {a}",
                model=self.model_name, usage={"total_tokens": 0})

    env = mk(game["trial"])
    llm = ScriptedLLM(game["actions"])
    agent = ReActAgent(llm=llm, max_steps=len(game["actions"]) + 2)
    env.reset()          # 先探一次拿 goal / 动作空间说明(被试内部还会再 reset 一次)
    goal, envinfo = env.goal, env.environment_info()
    success, progress, state = agent.run_multi_turn(
        task_id=env.task_id, goal=goal, environment=env, environment_info=envinfo)
    print(f"      goal={goal!r}")
    print(f"      被试返回 success={success} progress={progress} "
          f"观察数={len(state.observations)} LLM 调用={llm.total_requests}(桩)")
    print(f"      environment_info 摘要: {envinfo.splitlines()[3].strip()} ...")
    env.close()
    return bool(success) and progress == 1.0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--smoke":
        return smoke(argv[1:])
    if argv and argv[0] == "--goal":
        # 小工具:打一个游戏的初始观察与动作空间说明
        env = AlfWorldEnvAdapter(argv[1])
        print(env.reset())
        print("-" * 60)
        print(env.environment_info())
        env.close()
        return 0
    print(__doc__)
    print("用法:  fig1_pilot/fig1-env/bin/python benchmark_design/alfworld_env_adapter.py --smoke")
    print("      fig1_pilot/fig1-env/bin/python benchmark_design/alfworld_env_adapter.py --goal <task_dir/trial>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
