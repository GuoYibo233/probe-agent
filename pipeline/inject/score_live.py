"""活跑注入线打分器(cprobe-env,纯 CPU)。设计书:plans/2026-08-01-live-inject-design.md

输入:
  --live-dir   live_appworld.py 的输出目录(live_*.jsonl)
  --base-root  对照 = 已采轨迹目录(envs/runs/w0_aw_official/appworld_gptoss),
               只取活跑侧出现过的 task_id,按题配对
输出:LIVE_REPORT.{json,md} 写进 --live-dir

口径(设计书 §1;两处不可比要带上:对照批次的服务条件与日期行都与活跑不同):
- 任务成败:活跑 final.eval 的结构化 dict;对照 final.eval 是 str,
  ast.literal_eval 解;两边都以 success 字段为准,解不出算 unknown 单列。
- token 账两条:billed = 分段生成的 completion token 全部(含触发后丢弃的
  溢出);kept = billed - 溢出 token 估算。溢出只记了字符数,token 估算用
  gpt-oss tokenizer 现算注入前被丢弃文本不可行(原文没存),所以 kept 只报
  字符口径,billed 是 token 口径的唯一真账。对照的每步 out token 取
  usage.out(服务端记的 completion_tokens)。
- 出手事后账(评测时不可知、打分时才算):预测调用与该步真发出代码块首条
  完整调用的一致性(工具级/整条级;整条级用 parse_call 括号配平提取,别拿
  "apis. 到块尾"整段比——print 壳和多语句会让全对的预测也判不一致)、
  注入后该步是否又调了同一工具(重调)。
- task_error 单列:live_appworld 对单题临时故障(服务重启/网络抖动)补的
  final(abort=task_error:*, steps=-1)不是真实成败,只计 n_task_error,
  不进 live_success 的分母。

用法:
  cprobe-env/bin/python pipeline/inject/score_live.py \\
      --live-dir pipeline/inject/runs/live_smoke \\
      --base-root envs/runs/w0_aw_official/appworld_gptoss
"""

import argparse
import ast
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from parse_call import complete_call                         # noqa: E402

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")


def first_call(code):
    m = AW_CALL.search(code or "")
    return f"apis.{m.group(1)}.{m.group(2)}" if m else None


def norm_call(s):
    """比整条调用用:去空白差异(gen_call 是去引号规范串,真代码带引号,
    整条级一致性只在'去引号后逐字相同'时判真——与回放 full_call_ok 同口径)。"""
    return re.sub(r"\s+", "", (s or "").replace('"', "").replace("'", ""))


def success_of(ev):
    if isinstance(ev, dict):
        if "success" in ev:
            return bool(ev["success"])
        return None
    if isinstance(ev, str):
        try:
            d = ast.literal_eval(ev)
            if isinstance(d, dict) and "success" in d:
                return bool(d["success"])
        except Exception:
            pass
        # 对照轨迹的 eval 是被截断过的 str(实测 w0 168 条里 135 条
        # literal_eval 失败);success 键在串首,正则兜底(summarize_full 同口径)。
        m = re.search(r"'success': (True|False)", ev)
        if m:
            return m.group(1) == "True"
    return None


def read_live(path):
    recs = [json.loads(l) for l in open(path)]
    # 单题在建世界阶段就炸时,文件里只有兜底的 task_error final,没有 meta 行
    # ——meta 用 None 顶住,调用方从文件名兜出 task_id。
    meta = recs[0] if recs and recs[0].get("type") == "meta" else None
    gens = [r for r in recs if r.get("type") == "gen"]
    envs = {r["step"]: r for r in recs if r.get("type") == "env"}
    specs = [r for r in recs if r.get("type") == "spec"]
    final = next((r for r in recs if r.get("type") == "final"), None)
    return meta, gens, envs, specs, final


def read_base(path):
    recs = [json.loads(l) for l in open(path)]
    gens = [r for r in recs if r.get("type") == "gen"]
    final = next((r for r in recs if r.get("type") == "final"), None)
    return gens, final


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live-dir", required=True)
    ap.add_argument("--base-root", required=True)
    a = ap.parse_args()
    live_dir = Path(a.live_dir)
    base_root = Path(a.base_root)

    rows, spec_rows = [], []
    for f in sorted(glob.glob(str(live_dir / "live_*.jsonl"))):
        meta, gens, envs, specs, final = read_live(f)
        tid = ((meta or {}).get("task_id")
               or Path(f).stem[len("live_"):])       # 文件名 live_<task_id>.jsonl
        if final is None:
            rows.append(dict(task=tid, arm=(meta or {}).get("arm"),
                             unfinished=True))
            continue
        billed = sum(g["usage"]["gen_tok"] for g in gens)
        reqs = sum(g["usage"]["req"] for g in gens)
        disc_c = sum(g["discard"]["chars"] for g in gens)

        bp = base_root / f"appworld_{tid}.jsonl"
        base = dict(success=None, out_tok=None, steps=None)
        if bp.exists():
            bg, bf = read_base(bp)
            base = dict(
                success=success_of((bf or {}).get("eval")),
                out_tok=sum((g.get("usage") or {}).get("out") or 0
                            for g in bg),
                steps=(bf or {}).get("steps"))

        for s in specs:
            act = (envs.get(s["step"]) or {}).get("action") or ""
            tool_pred = first_call(s["gen_call"])
            tool_real = first_call(act)
            real_call, _ = complete_call(act)
            spec_rows.append(dict(
                task=tid, step=s["step"], conf=s["conf"],
                exec_ok=s["exec_ok"], error_kind=s["error_kind"],
                arg_modes=s["arg_modes"],
                tool_agree=(tool_pred == tool_real and tool_pred is not None),
                call_agree=(real_call is not None and
                            norm_call(s["gen_call"]) == norm_call(real_call)),
                recalled=(tool_pred is not None and tool_pred in act),
                discarded_chars=s["discarded_chars"]))

        rows.append(dict(
            task=tid, arm=(meta or {}).get("arm"),
            success=success_of(final.get("eval")),
            steps=final["steps"], completed=final["completed"],
            task_error=str(final.get("abort") or "").startswith("task_error"),
            n_inject=sum(g.get("n_inject", 0) for g in gens),
            billed_tok=billed, n_req=reqs, discarded_chars=disc_c,
            base_success=base["success"], base_out_tok=base["out_tok"],
            base_steps=base["steps"]))

    errs = [r for r in rows if r.get("task_error")]
    done = [r for r in rows
            if not r.get("unfinished") and not r.get("task_error")]
    paired = [r for r in done if r["base_success"] is not None]

    def rate(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 4) if xs else None

    summary = dict(
        n_tasks=len(rows), n_done=len(done), n_paired=len(paired),
        n_task_error=len(errs),
        live_success=rate([r["success"] for r in done]),
        base_success=rate([r["base_success"] for r in paired]),
        live_success_paired=rate([r["success"] for r in paired]),
        inject_per_task=rate([r["n_inject"] for r in done]),
        billed_tok_sum=sum(r["billed_tok"] for r in done),
        base_out_tok_sum=sum(r["base_out_tok"] or 0 for r in paired),
        n_spec=len(spec_rows),
        spec_exec_ok=rate([s["exec_ok"] for s in spec_rows]),
        spec_tool_agree=rate([s["tool_agree"] for s in spec_rows]),
        spec_call_agree=rate([s["call_agree"] for s in spec_rows]),
        spec_recalled=rate([s["recalled"] for s in spec_rows]),
        spec_error_kinds=dict(Counter(
            s["error_kind"] for s in spec_rows if s["error_kind"])))

    (live_dir / "LIVE_REPORT.json").write_text(json.dumps(
        dict(summary=summary, tasks=rows, specs=spec_rows),
        ensure_ascii=False, indent=1))

    md = ["# 活跑注入线报告", "",
          "对照批次的服务条件与 harmony 日期行都与活跑不同(设计书 §1),",
          "token 总量对比要带这条保留;billed 含触发后丢弃的溢出。",
          "n_task_error 是临时故障(abort=task_error)的题数,这些题没进",
          "live_success 的分母;重跑前删掉对应 live_*.jsonl 才会重试。", "",
          "| 指标 | 值 |", "|---|---|"]
    if errs:
        md.insert(6, "task_error 题: " + ", ".join(r["task"] for r in errs))
    for k, v in summary.items():
        md.append(f"| {k} | {v} |")
    md += ["", "| task | arm | 成败 | 对照成败 | 步数 | 出手 | billed tok |"
              " 对照 out tok |", "|---|---|---|---|---|---|---|---|"]
    for r in done:
        md.append(f"| {r['task']} | {r['arm']} | {r['success']} | "
                  f"{r['base_success']} | {r['steps']} | {r['n_inject']} | "
                  f"{r['billed_tok']} | {r['base_out_tok']} |")
    (live_dir / "LIVE_REPORT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
