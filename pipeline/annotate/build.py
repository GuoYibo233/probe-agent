"""轨迹 -> 单模型单环境的样本数据集(新流水线 annotate 段主构建器)。

源 = envs/collect/build_dataset.py,规则一字不改(全句边界前缀 / 事件内等权
/ 标签 = 该步真实调用的工具名),只改五处:
① 按 config.model_full 过滤事件(一模型一套数据);
② 切分不 shuffle,读官方题单文件定 train/val/test(unit 不在题单 -> 报错退出);
③④ 输出堆名 train/val/test,输出目录 = config.data_out;
⑤ 报告名 ANNOTATE_REPORT.md。
样本 dict 另追加两字段:label_call(规范化完整调用串)、args_named(保名参数表)。

两个旋钮(2026-08-21,np821 批):
- weight_mode:uniform(缺省)= 每步等权 w=1;per_event = 旧口径 w=1/m_i,
  只给 G8 复现验收线用。
- max_bounds:每事件切点上限,缺省 64,透传 rules.boundaries 的抽稀。
两者都是 CLI > 配置字段 > 缺省;旧配置不写这两个字段又不给旗标时,除了权重
口径本身,一切照旧。

输入: --config 指向的实验配置 json(schema 见 plans/2026-07-31-pipeline-engineering.md §2.3)
输出: <data_out>/{train,val,test}.jsonl tool_vocab.json router_stats.md
      qa_sample.txt ANNOTATE_REPORT.md

用法: python3 build.py --config pipeline/configs/aw_q35.json
      python3 build.py --config pipeline/configs/p1_gptoss.json \\
              --weight-mode per_event --max-bounds 64      # G8 复现
"""

import argparse
import glob
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import (ALF_TEMPLATES, AW_CALL, BFCL_CALL,  # noqa: E402
                   HIST_ROUNDS, MAX_BOUNDS, MIN_THINK, MODEL_OF, SEED,
                   alf_split, assemble, boundaries, first_call_args,
                   first_call_named)

SPLITS = ("train", "val", "test")

# alfworld:模板切不动的动作计数(不静默丢,报告里逐项印出来)。
# 键 = rules.alf_split 的落空原因;param_label.py 有一份同口径的副本。
ALF_DROP = Counter()


# ---------- 轨迹 -> 事件(【照抄】build_dataset.py,只多带一个保名参数表) ----------
# 事件 = dict(env, model, unit, traj, step, task, hist, think, tool, args, named)

def jsonl_events(runs, pattern, env):
    for f in sorted(glob.glob(str(runs / pattern))):
        batch = Path(f).parent.name           # e.g. appworld_q36
        model = MODEL_OF.get(batch.rsplit("_", 1)[1])
        if model is None:                     # 评分/日志等非模型目录
            continue
        recs = [json.loads(l) for l in open(f)]
        meta = recs[0]
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        envs = {r["step"]: r for r in recs if r["type"] == "env"}
        task = meta.get("instruction") or meta.get("task") or ""
        traj = f"{batch}/{Path(f).stem}"
        unit = (f"seed{meta.get('seed')}" if env == "tales"
                else str(meta.get("task_id") or Path(f).stem))
        hist = []
        for st in sorted(gens):
            g, e = gens[st], envs.get(st)
            if e is None:
                break
            think = (g.get("reasoning") or "").strip()
            action = (e.get("action") or "").strip()
            if not action:
                continue
            if env == "appworld":
                m = AW_CALL.search(action)
                if m and len(think) >= MIN_THINK:
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think,
                               tool=f"apis.{m.group(1)}.{m.group(2)}",
                               args=first_call_args(action, AW_CALL) or [],
                               named=first_call_named(action, AW_CALL) or [])
            elif env == "alfworld":
                # 模板细分口径:官方 13 条动作模板最长前缀匹配,介词位切具名参数。
                # 切不动 -> 整步丢弃 + 计数(绝不退回下面 else 的动词切法)。
                tool, named, why = alf_split(action)
                if why:
                    ALF_DROP[why] += 1
                elif len(think) >= MIN_THINK:
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think, tool=tool,
                               args=[v for _k, v in named],
                               named=list(named))
            else:  # tales:标签 = 命令首词(动词)
                verb = action.split()[0].lower() if action.split() else ""
                if verb and len(think) >= MIN_THINK:
                    rest = action.split()[1:]
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think, tool=verb,
                               args=[" ".join(rest)] if rest else [],
                               named=([("arg", " ".join(rest))] if rest
                                      else []))
            hist.append((action, e.get("result", "")))


def bfcl_events(runs):
    for d in sorted(runs.glob("bfcl_*")):
        model = MODEL_OF.get(d.name.rsplit("_", 1)[1])
        if model is None:                     # 评分/日志等非模型目录
            continue
        seen = set()
        for f in sorted(glob.glob(str(d / "**" / "*multi_turn*result.json"),
                                  recursive=True)):
            for line in open(f):
                entry = json.loads(line)
                if entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                msgs = []

                def flat(o):
                    if isinstance(o, dict):
                        role, c = o.get("role"), o.get("content")
                        if role in ("user", "assistant", "tool") \
                                and isinstance(c, str):
                            msgs.append((role, c,
                                         o.get("reasoning_content") or ""))
                        else:
                            for v in o.values():
                                flat(v)
                    elif isinstance(o, list):
                        for v in o:
                            flat(v)
                flat(entry["inference_log"])
                task, hist, k = "", [], 0
                for role, c, rc in msgs:
                    if role == "user":
                        task = c
                    elif role == "assistant" and rc.strip() and c.strip():
                        k += 1
                        m = BFCL_CALL.search(c)
                        if m and len(rc.strip()) >= MIN_THINK:
                            yield dict(env="bfcl", model=model,
                                       unit=entry["id"],
                                       traj=f"{d.name}/{entry['id']}",
                                       step=k, task=task, hist=list(hist),
                                       think=rc.strip(), tool=m.group(1),
                                       args=first_call_args(c, BFCL_CALL) or [],
                                       named=first_call_named(c, BFCL_CALL)
                                       or [])
                        hist.append((c.strip()[:200], ""))
                        del hist[:-HIST_ROUNDS]
                    elif role == "tool" and hist:
                        a, _ = hist[-1]
                        hist[-1] = (a, c)


def collect_events(runs_dirs, env):
    """按环境把多个 runs 目录的事件拼起来(顺序 = runs 目录顺序)。"""
    events = []
    for runs in runs_dirs:
        if env == "appworld":
            it = jsonl_events(runs, "appworld_*/appworld_*.jsonl", "appworld")
        elif env == "tales":
            it = jsonl_events(runs, "tales_*/tales_*.jsonl", "tales")
        elif env == "alfworld":
            it = jsonl_events(runs, "alfworld_*/alfworld_*.jsonl", "alfworld")
        elif env == "bfcl":
            it = bfcl_events(runs)
        else:
            raise SystemExit(f"未知环境: {env}")
        events.extend(it)
    return events


# ---------- 新增两字段(§3.3) ----------

def norm_named(named):
    """保名参数表 -> [{"key","value"}],按调用里出现顺序,空值跳过。"""
    return [dict(key=k, value=v) for k, v in named if v]


def make_call(tool, args_named):
    """label_call = tool(k=v, k=v);无参数时 tool()。"""
    inner = ", ".join(f"{a['key']}={a['value']}" for a in args_named)
    return f"{tool}({inner})"


# ---------- 造题(全边界 + 等权,【照抄】,dict 追加两字段) ----------

def make_samples(events, weight_mode="per_event", max_bounds=MAX_BOUNDS):
    """事件 -> 样本。两个参数的缺省 = 改动前的语义(w=1/m_i、上限 64),
    所以老调用方(accept_v3diff.py 拿它复现 v3 数据)一个字不用改;
    main() 一律显式传生效值。"""
    samples = []
    for ev in events:
        pts = boundaries(ev["think"], max_bounds)
        m = len(pts)
        w = 1.0 if weight_mode == "uniform" else round(1.0 / m, 6)
        args_named = norm_named(ev.get("named") or [])
        label_call = make_call(ev["tool"], args_named)
        for si, cut in enumerate(pts):
            prefix = ev["think"][:cut]
            samples.append(dict(
                text=assemble(ev["task"], ev["hist"], prefix),
                label=ev["tool"], w=w,
                depth=round(cut / len(ev["think"]), 4),
                sent_idx=si, n_sents=m,
                event=f"{ev['traj']}|s{ev['step']}",
                traj=ev["traj"], unit=ev["unit"], model=ev["model"],
                step=ev["step"],
                label_call=label_call,
                args_named=[dict(a) for a in args_named]))
    return samples


# ---------- 多样本批次的独立扫描(2026-08-21;不碰事件流) ----------
#
# 这两样统计问的是"原始轨迹本身长什么样",事件流答不了:相同轨迹要比逐步
# 原文(事件流只留过滤后的 think),步数上限要读 final 记录(事件流根本不带)。
# 所以再读一遍文件,读法(目录过滤、unit 口径)与 jsonl_events 保持同一套。

# 采集侧每题步数上限,按环境来(gen_launch.py ENV_TABLE 的 --max-steps:
# appworld 30、alfworld 50);表里没有的环境统计记"不适用"。
STEP_CAP = {"appworld": 30, "alfworld": 50}

TRAJ_PATTERNS = {"appworld": "appworld_*/appworld_*.jsonl",
                 "tales": "tales_*/tales_*.jsonl",
                 "alfworld": "alfworld_*/alfworld_*.jsonl"}


def traj_files(runs_dirs, env, model_full):
    """本批要扫的原始轨迹文件清单;bfcl 没有逐步轨迹文件 -> None。"""
    pattern = TRAJ_PATTERNS.get(env)
    if pattern is None:
        return None
    out = []
    for runs in runs_dirs:
        for f in sorted(glob.glob(str(runs / pattern))):
            batch = Path(f).parent.name       # e.g. appworld_gptoss
            if MODEL_OF.get(batch.rsplit("_", 1)[1]) != model_full:
                continue                      # 别的模型/非模型目录
            out.append(f)
    return out


def scan_raw_trajs(files, env):
    """-> dict(n_traj, dup_pairs, dup_units, cap_trajs, cap_units)。

    dup:同 unit 内逐步 (reasoning, content) 序列完全相等的轨迹**对**数
        (三条全同算 3 对),只计数不去重;dup_units = 出过重复的题数。
    cap:final 记录 steps >= 该环境步数上限 的轨迹条数与涉及题数;
        环境不在 STEP_CAP 表里时 cap 记 None(报告印"不适用")。
    """
    cap = STEP_CAP.get(env)
    by_unit = defaultdict(list)
    cap_trajs, cap_units = 0, set()
    for f in files:
        recs = [json.loads(l) for l in open(f)]
        meta = recs[0]
        unit = (f"seed{meta.get('seed')}" if env == "tales"
                else str(meta.get("task_id") or Path(f).stem))
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        by_unit[unit].append(tuple(
            (gens[st].get("reasoning") or "", gens[st].get("content") or "")
            for st in sorted(gens)))
        fin = [r for r in recs if r["type"] == "final"]
        if cap is not None and fin and (fin[-1].get("steps") or 0) >= cap:
            cap_trajs += 1
            cap_units.add(unit)
    dup_pairs, dup_units = 0, set()
    for unit, sigs in by_unit.items():
        pairs = sum(n * (n - 1) // 2 for n in Counter(sigs).values() if n > 1)
        if pairs:
            dup_pairs += pairs
            dup_units.add(unit)
    return dict(n_traj=len(files), dup_pairs=dup_pairs,
                dup_units=len(dup_units), cap=cap, cap_trajs=cap_trajs,
                cap_units=len(cap_units))


# ---------- 官方题单切分(改动②) ----------

def read_unit_list(path):
    """官方题单:每行一个 task_id(文件无末尾换行,按行 split 后去空行)。"""
    txt = Path(path).read_text()
    return [ln.strip() for ln in txt.split("\n") if ln.strip()]


def official_split(cfg):
    """-> (part: unit->堆名, lists: 堆名->该题单的 unit 集合)"""
    files = cfg["official_split_files"]
    lists, part = {}, {}
    for name in SPLITS:
        units = read_unit_list(files[name])
        lists[name] = set(units)
        for u in units:
            part[u] = name
    return part, lists


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="实验配置 json(§2.3)")
    ap.add_argument("--weight-mode", choices=("uniform", "per_event"),
                    default=None,
                    help="样本权重口径;缺省读配置的 weight_mode,再缺省 uniform")
    ap.add_argument("--max-bounds", type=int, default=None,
                    help="每事件切点上限;缺省读配置的 max_bounds,再缺省 64")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    env = cfg["env"]
    model_full = cfg["model_full"]
    runs_dirs = [Path(r) for r in cfg["traj_runs"]]
    out = Path(cfg["data_out"])
    seed = cfg.get("seed", SEED)
    rng = random.Random(seed)
    # 生效值:CLI > 配置字段 > 缺省。缺省是新口径(每步等权),旧口径要显式点名。
    # 配置分支按"键在不在"判,不按真值判:写 0 这类非法值要落到下面的硬拦,
    # 不许被 or 静默换成缺省(评审 2026-08-22 抓的洞)。
    cfg_wm = cfg.get("weight_mode")
    weight_mode = (args.weight_mode if args.weight_mode is not None
                   else "uniform" if cfg_wm is None else cfg_wm)
    cfg_mb = cfg.get("max_bounds")
    max_bounds = (args.max_bounds if args.max_bounds is not None
                  else MAX_BOUNDS if cfg_mb is None else cfg_mb)
    if weight_mode not in ("uniform", "per_event"):
        raise SystemExit(f"未知 weight_mode: {weight_mode}"
                         "(只认 uniform/per_event)")
    if max_bounds < 2:
        # 上限 1 会让 rules.boundaries 的抽稀步长除以零,不许静默炸在半路。
        raise SystemExit(f"max_bounds 至少 2(给的是 {max_bounds})")

    events = collect_events(runs_dirs, env)
    n_all = len(events)
    # 改动①:一模型一套数据
    events = [ev for ev in events if ev["model"] == model_full]
    if not events:
        raise SystemExit(f"没有 model={model_full} 的事件(共扫到 {n_all} 事件)")
    out.mkdir(parents=True, exist_ok=True)

    # 改动②:官方题单切分,不 shuffle;unit 不在任何题单 -> 报错退出
    part, lists = official_split(cfg)
    units = sorted({ev["unit"] for ev in events})
    missing = [u for u in units if u not in part]
    if missing:
        raise SystemExit(
            f"{len(missing)} 个 unit 不在任何官方题单里,拒绝静默丢弃: "
            f"{missing[:10]}{' ...' if len(missing) > 10 else ''}")

    samples = make_samples(events, weight_mode, max_bounds)

    # 自检 1:前缀=原文切片(抽 200 逐题断言)
    ev_think = {f"{e['traj']}|s{e['step']}": e["think"] for e in events}
    for s in rng.sample(samples, min(200, len(samples))):
        think = s["text"].split("[THINKING]\n", 1)[1]
        assert ev_think[s["event"]].startswith(think), s["event"]
    # 自检 2:unit 不跨 split(结构性保证,再显式验一遍)
    seen_u = {}
    for s in samples:
        assert seen_u.setdefault(s["unit"], part[s["unit"]]) \
            == part[s["unit"]]

    splits = defaultdict(list)
    for s in samples:
        splits[part[s["unit"]]].append(s)
    for name in SPLITS:
        with open(out / f"{name}.jsonl", "w") as f:
            for s in splits[name]:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # 自检 3(新增):每堆抽 20 个 unit,断言确实在对应官方题单文件里
    check3 = []
    for name in SPLITS:
        us = sorted({s["unit"] for s in splits[name]})
        pick = rng.sample(us, min(20, len(us))) if us else []
        for u in pick:
            assert u in lists[name], (name, u)
        check3.append(f"{name} {len(pick)}/{len(pick)}")

    vocab = Counter(e["tool"] for e in events)
    (out / "tool_vocab.json").write_text(json.dumps(
        dict(vocab.most_common()), ensure_ascii=False, indent=1))

    # 路由统计表
    rt = defaultdict(lambda: dict(n=0, nargs=[], alen=[], hit=0, argn=0))
    for ev in events:
        r = rt[ev["tool"]]
        r["n"] += 1
        r["nargs"].append(len(ev["args"]))
        ctx = ev["think"] + "\n" + ev["task"] + "\n" + \
            "\n".join(a + str(b) for a, b in ev["hist"])
        for a in ev["args"]:
            if not a:
                continue
            r["argn"] += 1
            r["alen"].append(len(a))
            if a in ctx:
                r["hit"] += 1
    with open(out / "router_stats.md", "w") as f:
        f.write(f"# 路由统计表 — {env}(参数头裁决书)\n\n"
                "| 工具 | 事件数 | 参数数中位 | 逐字命中率 | 参数长中位 |\n"
                "|---|---|---|---|---|\n")
        for k in sorted(rt, key=lambda k: -rt[k]["n"]):
            r = rt[k]
            hitrate = f"{r['hit']/r['argn']:.2f}" if r["argn"] else "-"
            alen = int(statistics.median(r["alen"])) if r["alen"] else "-"
            f.write(f"| {k} | {r['n']} | "
                    f"{int(statistics.median(r['nargs']))} "
                    f"| {hitrate} | {alen} |\n")

    # QA 抽查
    with open(out / "qa_sample.txt", "w") as f:
        for i, s in enumerate(rng.sample(samples, min(20, len(samples)))):
            f.write(f"{'='*70}\n[QA {i}] label={s['label']} "
                    f"depth={s['depth']} sent {s['sent_idx']+1}/"
                    f"{s['n_sents']} traj={s['traj']}\n{s['text']}\n\n")

    # 报告
    bl = [e_m for e_m in (len(boundaries(e["think"], max_bounds))
                          for e in events)]
    dep = Counter(min(9, int(s["depth"] * 10)) for s in samples)
    lens = sorted(len(s["text"]) for s in samples)
    prior_tool = vocab.most_common(1)[0][0]
    test_events = {s["event"]: s["label"] for s in splits["test"]}
    prior_acc = (sum(1 for v in test_events.values() if v == prior_tool)
                 / max(1, len(test_events)))
    trajs = {e["traj"] for e in events}
    # 切分口径的文案。只影响报告里两行**文字**,不进任何样本字段,所以
    # 数据字节与改动前逐字节相同(已实测:aw_official_v1/q35 三堆 cmp 零差异)。
    # 默认值保持改动前的说法,appworld/alfworld 的 config 不必写。
    # bfcl 必须写:BFCL 没有官方分区,照打"官方题单"就是数字对、文案撒谎
    # (extending.md §5 静默点 #18),check_callstr.py 会硬拦这种撒谎。
    split_desc = cfg.get("split_desc", "官方题单,任务实例级")
    # 权重口径文案:per_event 一字不动(G8 复现要它逐字节对上),uniform 换说法。
    w_desc = "w=1/m_i 事件等权" if weight_mode == "per_event" else "w=1 每步等权"
    report = [
        f"# {cfg['run_family']} / {cfg['model_short']} annotate 出厂报告\n",
        f"- SEED={seed} MAX_BOUNDS={max_bounds} env={env}"
        f" model={model_full}",
        f"- runs={[str(r) for r in runs_dirs]}",
        f"- config={args.config} out={out}",
        f"- 规则:全句边界前缀 / {w_desc} / 三路切分"
        f"({split_desc}) / 一模型一数据集\n",
        f"## {env} — {cfg['model_short']}",
        f"- 轨迹 {len(trajs)} / 任务实例 {len(units)} / 事件 {len(events)}"
        f" / 样本 {len(samples)}(全模型事件 {n_all},过滤后留 {len(events)})",
        f"- 边界数每事件: min {min(bl)} med {sorted(bl)[len(bl)//2]}"
        f" max {max(bl)}(上限 {max_bounds})",
        f"- 切分({split_desc}): " + " / ".join(
            f"{sp} {len({s['unit'] for s in splits[sp]})}实例·"
            f"{len({s['event'] for s in splits[sp]})}事件·"
            f"{len(splits[sp])}样本"
            for sp in SPLITS),
        f"- 工具词表 {len(vocab)} 类;top5 {vocab.most_common(5)}",
        f"- 长尾(出现<5次): {sum(1 for c in vocab.values() if c < 5)} 类",
        f"- 深度十桶样本数: {[dep.get(i, 0) for i in range(10)]}",
        f"- 题干长度 p50={lens[len(lens)//2]}"
        f" p90={lens[int(len(lens)*.9)]} max={lens[-1]} 字符"
        "(超 4096 token 由训练脚本左截)",
        f"- 频率先验基线(test 事件级,猜 {prior_tool}): {prior_acc:.3f}",
        "- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓;"
        "题单归属抽查 " + " ".join(check3) + " ✓",
    ]
    if "trajs_per_unit" in cfg:
        # 多样本批次(每题多条轨迹)才出这四行:切点上限该不该抬要看未截断的
        # 切点分布,同题多条轨迹会不会撞成一模一样、有几条顶到步数上限,
        # 都是温度 1 多采样特有的问题。旧配置没这个键 -> 报告行集与改动前一致。
        # 全程不抽样、不用 rng。
        ub = sorted(len(boundaries(e["think"], 10**9)) for e in events)

        def q(p):
            return ub[min(len(ub) - 1, int(len(ub) * p))]

        report.append(
            f"- 切点数(未截断)每事件: min {ub[0]} p50 {q(.5)} p90 {q(.9)}"
            f" p99 {q(.99)} max {ub[-1]};超 32/64/128/256 的事件 "
            + "/".join(str(sum(1 for n in ub if n > t))
                       for t in (32, 64, 128, 256)))
        report.append(f"- 命中切点上限({max_bounds})的事件: "
                      f"{sum(1 for n in ub if n > max_bounds)}")
        files = traj_files(runs_dirs, env, model_full)
        if files is None:
            report.append("- 完全相同轨迹 / 步数达上限: "
                          f"不适用({env} 没有逐步轨迹文件)")
        else:
            raw = scan_raw_trajs(files, env)
            report.append(f"- 完全相同轨迹: {raw['dup_pairs']} 对"
                          f"(涉及 {raw['dup_units']} 题);"
                          f"扫描轨迹 {raw['n_traj']} 条,只计数不去重")
            if raw["cap"] is None:
                report.append(f"- 步数达上限的轨迹: 不适用"
                              f"({env} 不在 STEP_CAP 表里)")
            else:
                report.append(f"- 步数达上限({raw['cap']})的轨迹: "
                              f"{raw['cap_trajs']} 条"
                              f"(涉及 {raw['cap_units']} 题)")
    if env == "alfworld":
        # 模板切不动的动作:整步丢弃,但必须可观测。
        # no_template 占比高 = 提示词发的是老语法(put X in Y)或多余的自然语言,
        # 不是模型菜——这一行同时是语法断代的报警器。
        report.append(
            f"- 模板切不动而丢弃的步: {sum(ALF_DROP.values())} "
            f"({dict(sorted(ALF_DROP.items()))});"
            f"官方模板 {len(ALF_TEMPLATES)} 条,工具词表应 ≤{len(ALF_TEMPLATES)} 类")
    (out / "ANNOTATE_REPORT.md").write_text("\n".join(report) + "\n")
    if env == "alfworld":
        print(f"alfworld 切不动丢弃: {sum(ALF_DROP.values())} "
              f"{dict(sorted(ALF_DROP.items()))}")
    print(f"{env}/{cfg['model_short']}: events={len(events)} "
          f"samples={len(samples)} vocab={len(vocab)}")
    print("done ->", out)


if __name__ == "__main__":
    main()
