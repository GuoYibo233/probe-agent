"""第15步 v0: TraceLab 真实任务流的相似度分布(纯CPU,工具序列相似度).

Session profile = tool_name count vector. Questions:
1. 相邻 session(同 user,按时间)相似度分布 -> 真实流里 L0/L1/L2 各占多少
2. 相似任务间隔: 距最近一个 sim>0.8 的早先 session 隔几个 session
3. 跨 project 高相似对频率(假相似的粗代理)
"""

import gzip
import json
import math
from collections import Counter, defaultdict

SRC = ("/home/y-guo/reproduce/new1/related_work/TraceLab/data/"
       "syfi_coding_trace.jsonl.gz")

sessions = {}
for line in gzip.open(SRC, "rt"):
    d = json.loads(line)
    sid = d["session_id"]
    s = sessions.setdefault(sid, {
        "user": d.get("user"), "project": d.get("project"),
        "t0": None, "tools": Counter(), "rounds": 0})
    s["rounds"] += 1
    for t in d.get("tools") or []:
        s["tools"][t.get("tool_name", "?")] += 1
    ts = (d.get("timing_events") or [{}])[0].get("timestamp")
    if ts and (s["t0"] is None or ts < s["t0"]):
        s["t0"] = ts

sess = [dict(sid=k, **v) for k, v in sessions.items()
        if v["t0"] and sum(v["tools"].values()) >= 3]
print(f"sessions total={len(sessions)}, usable(>=3 tool calls)={len(sess)}")


def cos(a, b):
    num = sum(a[k] * b[k] for k in a if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return num / (na * nb) if na and nb else 0.0


by_user = defaultdict(list)
for s in sess:
    by_user[s["user"]].append(s)

adj_sims, spacings, cross_proj_hi, same_proj_hi = [], [], 0, 0
for u, ss in by_user.items():
    ss.sort(key=lambda x: x["t0"])
    for i in range(1, len(ss)):
        sim = cos(ss[i]["tools"], ss[i - 1]["tools"])
        adj_sims.append(sim)
        # spacing to nearest earlier similar session (window 50)
        sp = None
        for j in range(i - 1, max(-1, i - 51), -1):
            s2 = cos(ss[i]["tools"], ss[j]["tools"])
            if s2 > 0.8:
                sp = i - j
                if ss[i]["project"] == ss[j]["project"]:
                    same_proj_hi += 1
                else:
                    cross_proj_hi += 1
                break
        if sp:
            spacings.append(sp)

adj_sims.sort()
n = len(adj_sims)
q = lambda p: adj_sims[int(p * n)]
print(f"\n相邻 session 工具相似度 (n={n}):")
print(f"  p10={q(.1):.2f} p25={q(.25):.2f} p50={q(.5):.2f} "
      f"p75={q(.75):.2f} p90={q(.9):.2f}")
lo = sum(1 for x in adj_sims if x < 0.3) / n
mid = sum(1 for x in adj_sims if 0.3 <= x <= 0.8) / n
hi = sum(1 for x in adj_sims if x > 0.8) / n
print(f"  <0.3(≈L0/无关): {lo:.1%}   0.3-0.8(≈L1/部分相似): {mid:.1%}   "
      f">0.8(≈L2/重复): {hi:.1%}")
spacings.sort()
m = len(spacings)
print(f"\n相似任务间隔 (sim>0.8, 50窗内命中 {m}/{n}={m/n:.1%}):")
if m:
    print(f"  p50={spacings[m//2]} sessions, p90={spacings[int(.9*m)]}")
hp = same_proj_hi + cross_proj_hi
print(f"\n高相似对里跨 project 比例(假相似粗代理): "
      f"{cross_proj_hi}/{hp} = {cross_proj_hi/max(1,hp):.1%}")
