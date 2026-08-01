"""把拼回实验各臂续写里补完的那条调用抽出来,喂给 exec_calls.py。规格:
plans/2026-08-01-splice-impl-spec.md §D3

骨架臂只钉工具名,参数是大模型自己写的——所以"这条调用到底长什么样"要等续写
回来才知道。这个脚本按 score 段 C2 的同一套口径,从 raw<tag>.jsonl 的续写里
括号配平抽出裸调用,把 plan 记录里的 gen_call 换成它,写成
`exec_in_<arm>.jsonl`。exec_calls.py --plan 吃的就是这个文件,它真去 appworld
里执行一遍,才能给出这条调用对不对。

exec_calls.py 从 plan 记录里读的字段(replay_unit + main 里逐条核过):
event / unit / step / traj_path / gen_call,外加 .get 的 full_call_ok 与
n_calls_in_block。所以这里 plan 记录整条复制,一个字段都不能少;但 full_call_ok
讲的是被换掉的那条 cgen 草稿对不对,对新调用已经失真 —— 它正是 exec_calls.py
--selfcheck 与 merge-exec 验收线挑事件的依据,所以按新调用重算(= 新调用与
label_call 逐字相同),旧值挪到 orig_full_call_ok 留档。n_calls_in_block 与
traj_bare_print 数的是轨迹里录下的那个代码块,与换不换调用无关,原样保留。

抽取位置按臂分两类:
- skel_bare / skel_a / skel_b:骨架塞在 analysis 里,调用从骨架处起头,
  所以要把骨架串接回续写前面再找。
- inject_stop / skel_switch / switch_only:续写从 final 通道**内**开始,
  对 text 直接 split_channels 会得空 final,所以 final = 臂的拼入串 + text。
- nofill / inject:老口径,split_channels 之后在 final 里找。

用法:
  python pipeline/inject/extract_completed.py \\
      --run-dir pipeline/inject/runs/aw_gptoss_splice --arms skel_a,switch_only
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parse_call                                            # noqa: E402
from build_form_table import load_table, skeleton            # noqa: E402

# 规格 §命名钉死。replay_inject.py 里有同名常量,两边必须逐字相同
SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"
FENCE_OPEN = "```python\n"
FINAL_OPEN = "<|channel|>final<|message|>"
# 【照抄 envs/collect/run_appworld.py:38】提代码块用同一条正则
CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)

# 续写从 final 通道内开始的臂:它们的 text 里没有 FINAL_OPEN
ARMS_FINAL = {"inject_stop", "skel_switch", "switch_only"}
# 骨架落在 analysis 里的臂
ARMS_SKEL_ANALYSIS = {"skel_bare", "skel_a", "skel_b"}
# 要骨架的全部臂:没有 pred_label 就没得拼,直接跳过
ARMS_SKEL = ARMS_SKEL_ANALYSIS | {"skel_switch"}
# 骨架前面带围栏开栏的臂(skel_b 是白话引出,没有围栏)
ARMS_FENCED = {"skel_bare", "skel_a", "skel_switch"}


def split_channels(text):
    """把续写切成 (analysis 剩余, final 内容)。【与 replay_inject.py:632 同】"""
    if FINAL_OPEN in text:
        head, tail = text.split(FINAL_OPEN, 1)
        return head, tail
    return text, ""


def rebuild_sides(arm, text, skel):
    """还原(analysis 侧, final 侧)两段可搜索的文本。

    拼进 prompt 的那截(骨架、开栏)不在 text 里,但调用是从它起头的,
    所以要接回来才找得到调用起点。
    """
    if arm in ARMS_FINAL:
        pre = FENCE_OPEN + skel if arm == "skel_switch" else ""
        return "", pre + text
    if arm in ARMS_SKEL_ANALYSIS:
        analysis, final = split_channels(text)
        pre = FENCE_OPEN if arm in ARMS_FENCED else ""
        return pre + skel + analysis, final
    return split_channels(text)


def call_of(arm, text, skel, pred_label):
    """按 C2 口径抽这条臂的完整裸调用。返回 (call_out|None, 在哪段找到)。

    骨架臂先看骨架**那个位置**上补没补完:骨架不带尾左括号,不锚位置的话,
    模型另起一行自己写的调用会被当成骨架补完的那条(score 段同款锚定,
    两边口径必须逐字一致,否则 per_event 的 call_out 与送去执行的对不上)。
    骨架被模型自己推翻时退回正文段,抽它真正写出来的那条。
    """
    analysis, final = rebuild_sides(arm, text, skel)
    if arm in ARMS_SKEL and skel and pred_label:
        where = "final" if arm in ARMS_FINAL else "analysis"
        seg = final if arm in ARMS_FINAL else analysis
        pre = FENCE_OPEN if arm in ARMS_FENCED else ""
        call, _ = parse_call.call_at(seg, len(pre + skel) - len(pred_label))
        if call is not None:
            return call, where
    call, _ = parse_call.complete_call(final)
    return (call, "final") if call is not None else (None, None)


def rewritten_in_final(arm, text, skel, pred_label):
    """骨架补完了,但模型在正文段又换了个工具?

    与 score 段的 tool_rewritten 同一口径:正文段的代码块里第一条调用的工具名。
    这类事件送去真执行的是骨架处那条,也就是模型自己已经放弃的调用。
    """
    _, final = rebuild_sides(arm, text, skel)
    b = CODE_RE.search(final)
    m = parse_call.CALL_START.search(b.group(1)) if b else None
    return bool(m) and m.group(0)[:-1] != pred_label


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--plan-file", default="plan.jsonl",
                    help="run-dir 里的 plan 文件名(execute 档是 plan_exec.jsonl)")
    ap.add_argument("--tag", default="", help="raw<tag>.jsonl 的后缀")
    ap.add_argument("--arms", required=True,
                    help="逗号分隔的臂名,每条臂出一个 exec_in_<arm>.jsonl")
    ap.add_argument("--form-table", default=None,
                    help="骨架形态表(默认 pipeline/inject/form_table.json)")
    a = ap.parse_args()

    d = Path(a.run_dir)
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    table = load_table(a.form_table)
    plan = {}
    for line in open(d / a.plan_file):
        p = json.loads(line)
        plan[p["event"]] = p
    raw = defaultdict(dict)
    for line in open(d / f"raw{a.tag}.jsonl"):
        o = json.loads(line)
        raw[o["event"]][o["arm"]] = o        # 后写的覆盖先写的,与 score 段同

    summary = {}
    for arm in arms:
        rows, stat = [], Counter()
        for ev, byarm in raw.items():
            o = byarm.get(arm)
            p = plan.get(ev)
            if o is None or p is None:
                continue
            if o.get("dry"):                 # dry-run 记录没有续写
                stat["dry"] += 1
                continue
            stat["n"] += 1
            # 骨架用 pred_label,绝不许用 label(上帝视角红线)
            pred_label = p.get("pred_label")
            if arm in ARMS_SKEL and not pred_label:
                stat["no_pred_label"] += 1
                continue
            skel = skeleton(pred_label, table) if pred_label else ""
            text = o.get("text") or ""
            call, where = call_of(arm, text, skel, pred_label)
            if call is None:
                stat["no_call"] += 1
                continue
            stat[f"found_in_{where}"] += 1
            if where == "analysis" and rewritten_in_final(arm, text, skel,
                                                          pred_label):
                # 抽的是骨架处那条,可模型在正文段又换了个工具:送去执行的
                # 是它自己已经放弃的调用。数出来,别让这部分混进成绩里
                stat["rewritten_in_final"] += 1
            rec = dict(p)
            rec["gen_call"] = call
            rec["source_arm"] = arm
            # plan 里的 full_call_ok 讲的是被换掉的那条 cgen 草稿对不对,对新
            # 调用已经失真;而 exec_calls.py 的 --selfcheck 与 merge-exec 的验收
            # 线都拿它挑事件,原样搬过去就是让一条与真值完全不同的调用带着
            # full_call_ok=True 进 MATCH/DIFF 比对,DIFF 报假警、selfcheck 非零
            # 退出。按新调用重算(真值缺失就记 None,过不了验收线的筛子),
            # 旧值挪去 orig_full_call_ok 留档。
            # n_calls_in_block 不动:它数的是**轨迹里录下的那个代码块**有几条
            # 调用(plan 段从 baseline_action 数的),和 traj_bare_print 一样是
            # "单独执行一条调用能不能与录下的 stdout 比"的门槛,不是草稿的属性
            truth = p.get("label_call")
            rec["orig_full_call_ok"] = p.get("full_call_ok")
            rec["full_call_ok"] = (call == truth) if truth else None
            rows.append(rec)
        out = d / f"exec_in_{arm}.jsonl"
        with open(out, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary[arm] = dict(out=str(out), n_written=len(rows), **dict(stat))
        print(f"{arm}: {len(rows)} 条 -> {out}  ({dict(stat)})", flush=True)

    print(json.dumps(dict(run_dir=str(d), plan_file=a.plan_file, tag=a.tag,
                          form_table=str(a.form_table or "默认"),
                          arms=summary), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
