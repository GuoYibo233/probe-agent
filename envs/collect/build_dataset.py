"""轨迹 -> 三环境各自的 BERT 种类头数据集(v2 终稿,覆盖旧四刀版)。

终稿规则(2026-07-29 与用户+导师意见逐条敲定,WORKPLAN C2-2t):
- 一道题 = 一个前缀:永远从思考第一个字开始,尾巴停在句子边界(代码只停整行)
- **全边界**:每事件切出全部句子边界(上限 64,均匀抽、永保末尾),
  训练损失用 w=1/m_i 事件内等权 —— 与部署"每个句边界都被调用"分布一致
- 标签 = 该步真实调用的工具名,全自动零人工;**一环境一数据集**(不合训)
- 切分单位 = **任务实例**(AppWorld task_id / TALES seed / BFCL entry id):
  同一实例在不同生成模型下的轨迹同进同出,防姊妹泄漏
- 四路切分 train/calA/calB/test = 70/10/10/10(calA 拟温度,calB 回放扫阈值,
  test 冻结后只跑一次);calB/test 天然含全边界,可直接回放
- 种子固定,重跑逐样本一致;顺产路由统计表 + 频率先验基线

用法: python3 build_dataset.py [--runs DIR ...] [--out DIR]
默认 runs=full_v1,可追加 --runs .../full_v2_topup 后重跑(确定性重建)。
"""

import argparse
import json
import glob
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20260729
BASE = Path("/home/y-guo/reproduce/new1/envs")
MAX_BOUNDS = 64       # 每事件边界上限(gpt-oss 超长思考防爆)
MIN_THINK = 40        # 字符;再短的思考没有可切性
HIST_ROUNDS = 3       # 题干里保留最近几轮工具历史
RESULT_CAP = 400      # 每条环境返回在题干里的字符上限
MODEL_OF = {"q35": "qwen3.5-27b", "q36": "qwen3.6-27b", "gptoss": "gpt-oss-120b"}

# 句子边界:换行,或 .!? 后跟空白(小数点/apis.x.y 的点后无空白,天然排除)
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")


def boundaries(text):
    """全部合法切点(字符偏移,前缀=text[:i]),含全文末尾,上限 MAX_BOUNDS。"""
    pts = sorted({m.end() for m in SENT_RE.finditer(text)} | {len(text)})
    pts = [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]
    if not pts:
        pts = [len(text)]
    if len(pts) > MAX_BOUNDS:
        keep = {len(pts) - 1}
        step = (len(pts) - 1) / (MAX_BOUNDS - 1)
        keep.update(round(k * step) for k in range(MAX_BOUNDS - 1))
        pts = [pts[j] for j in sorted(keep)]
    return pts


def clip(s, cap=RESULT_CAP):
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]


def assemble(task, history, think_prefix):
    lines = [f"Task: {task}", "[HISTORY]"]
    if history:
        lines += [f"{a} -> {clip(r)}" for a, r in history[-HIST_ROUNDS:]]
    else:
        lines.append("(start)")
    lines += ["[THINKING]", think_prefix]
    return "\n".join(lines)


# ---------- 参数抽取(路由统计用) ----------

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")
BFCL_CALL = re.compile(r"(\w+)\(")


def split_args(argstr):
    vals, buf, depth, q = [], "", 0, None
    for ch in argstr:
        if q:
            buf += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            vals.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        vals.append(buf.strip())
    out = []
    for v in vals:
        m = re.match(r"\w+\s*=\s*(.+)", v, re.S)
        out.append((m.group(1) if m else v).strip().strip("\"'"))
    return out


def first_call_args(code, name_re):
    m = name_re.search(code)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    for j in range(i, len(code)):
        if code[j] == "(":
            depth += 1
        elif code[j] == ")":
            depth -= 1
            if depth == 0:
                return split_args(code[i + 1: j])
    return []


# ---------- 三环境:轨迹 -> 事件 ----------
# 事件 = dict(env, model, unit, traj, step, task, hist, think, tool, args)

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
                               args=first_call_args(action, AW_CALL) or [])
            else:  # tales:标签 = 命令首词(动词)
                verb = action.split()[0].lower() if action.split() else ""
                if verb and len(think) >= MIN_THINK:
                    rest = action.split()[1:]
                    yield dict(env=env, model=model, unit=unit, traj=traj,
                               step=st, task=task, hist=list(hist),
                               think=think, tool=verb,
                               args=[" ".join(rest)] if rest else [])
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
                                       args=first_call_args(c, BFCL_CALL) or [])
                        hist.append((c.strip()[:200], ""))
                        del hist[:-HIST_ROUNDS]
                    elif role == "tool" and hist:
                        a, _ = hist[-1]
                        hist[-1] = (a, c)


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", action="append",
                    default=None, help="轨迹目录,可多次;默认 full_v1")
    ap.add_argument("--out", default=str(BASE / "bert_data" / "v2"))
    args = ap.parse_args()
    runs_dirs = [Path(r) for r in (args.runs or [BASE / "runs" / "full_v1"])]
    out_root = Path(args.out)
    rng = random.Random(SEED)

    by_env = defaultdict(list)
    for runs in runs_dirs:
        for ev in jsonl_events(runs, "appworld_*/appworld_*.jsonl", "appworld"):
            by_env["appworld"].append(ev)
        for ev in jsonl_events(runs, "tales_*/tales_*.jsonl", "tales"):
            by_env["tales"].append(ev)
        for ev in bfcl_events(runs):
            by_env["bfcl"].append(ev)

    report = [f"# bert_data v2 出厂报告\n\n- SEED={SEED} MAX_BOUNDS={MAX_BOUNDS}"
              f" runs={[str(r) for r in runs_dirs]}",
              "- 规则:全句边界前缀 / w=1/m_i 事件等权 / 任务实例级四路切分"
              " / 一环境一数据集\n"]

    for env in ("appworld", "tales", "bfcl"):
        events = by_env[env]
        if not events:
            report.append(f"\n## {env}\n- 无事件,跳过")
            continue
        out = out_root / env
        out.mkdir(parents=True, exist_ok=True)

        # 任务实例级切分(同实例跨模型同进同出)
        units = sorted({ev["unit"] for ev in events})
        rng.shuffle(units)
        n = len(units)
        c1, c2, c3 = int(n * .7), int(n * .8), int(n * .9)
        part = {u: ("train" if i < c1 else "calA" if i < c2
                    else "calB" if i < c3 else "test")
                for i, u in enumerate(units)}

        # 造题(全边界 + 等权)
        samples = []
        for ev in events:
            pts = boundaries(ev["think"])
            m = len(pts)
            for si, cut in enumerate(pts):
                prefix = ev["think"][:cut]
                samples.append(dict(
                    text=assemble(ev["task"], ev["hist"], prefix),
                    label=ev["tool"], w=round(1.0 / m, 6),
                    depth=round(cut / len(ev["think"]), 4),
                    sent_idx=si, n_sents=m,
                    event=f"{ev['traj']}|s{ev['step']}",
                    traj=ev["traj"], unit=ev["unit"], model=ev["model"],
                    step=ev["step"]))

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
        for name in ("train", "calA", "calB", "test"):
            with open(out / f"{name}.jsonl", "w") as f:
                for s in splits[name]:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")

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
        bl = [e_m for e_m in (len(boundaries(e["think"])) for e in events)]
        dep = Counter(min(9, int(s["depth"] * 10)) for s in samples)
        lens = sorted(len(s["text"]) for s in samples)
        prior_tool = vocab.most_common(1)[0][0]
        test_events = {s["event"]: s["label"] for s in splits["test"]}
        prior_acc = (sum(1 for v in test_events.values() if v == prior_tool)
                     / max(1, len(test_events)))
        trajs = {e["traj"] for e in events}
        report += [
            f"\n## {env}",
            f"- 轨迹 {len(trajs)} / 任务实例 {len(units)} / 事件 {len(events)}"
            f" / 样本 {len(samples)}",
            f"- 边界数每事件: min {min(bl)} med {sorted(bl)[len(bl)//2]}"
            f" max {max(bl)}(上限 {MAX_BOUNDS})",
            "- 切分(任务实例级): " + " / ".join(
                f"{sp} {len({s['unit'] for s in splits[sp]})}实例·"
                f"{len({s['event'] for s in splits[sp]})}事件·"
                f"{len(splits[sp])}样本"
                for sp in ("train", "calA", "calB", "test")),
            f"- 工具词表 {len(vocab)} 类;top5 {vocab.most_common(5)}",
            f"- 长尾(出现<5次): {sum(1 for c in vocab.values() if c < 5)} 类",
            f"- 深度十桶样本数: {[dep.get(i, 0) for i in range(10)]}",
            f"- 题干长度 p50={lens[len(lens)//2]}"
            f" p90={lens[int(len(lens)*.9)]} max={lens[-1]} 字符"
            "(超 4096 token 由训练脚本左截)",
            f"- 频率先验基线(test 事件级,猜 {prior_tool}): {prior_acc:.3f}",
            "- 自检: 前缀断言 200/200 ✓;实例不跨 split ✓",
        ]
        print(f"{env}: events={len(events)} samples={len(samples)} "
              f"vocab={len(vocab)}")

    (out_root / "BUILD_REPORT.md").write_text("\n".join(report) + "\n")
    print("done ->", out_root)


if __name__ == "__main__":
    main()
