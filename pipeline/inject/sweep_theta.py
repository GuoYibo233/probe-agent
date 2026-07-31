"""θ 扫描驱动壳:一列 θ 自动跑完 run+score,并把六点曲线装配成主报。

要回答的问题:评测主报要从"钉死风险档报两个点"换成"按触发门槛扫一条曲线",
横轴 θ(或换算成覆盖率),纵轴两条——省了多少 token、正确率降多少。
(2026-08-01 用户定;计划见 WORKPLAN"2026-08-01 排程",格点六个:
0.50/0.70/0.80/0.875/0.925/0.95)

为什么要这个壳:换 θ 原来得手动重跑一遍 plan/run/score,五遍下来容易漏参数、
漏记账;而 run 段要在多个 gpt-oss 服务之间排队,手排必然让一部分服务空转。

两个子命令:
  run    给一列 run 目录 + 一池服务地址,并发把 run 段跑完再各自 score。
         一个 θ 占一个服务,服务空出来就接下一个 θ。幂等:已有 INJECT_REPORT.json
         的 θ 直接跳过,断点续跑不重算。
  curve  把已完成的各 θ 目录装配成曲线(markdown 表 + json)。

口径铁律(曲线成立的前提):
- 各点只允许差 θ 一个变量。plan 段的 ctool/cgen/data/traj_root/miss_policy
  必须完全一致,run 段的 arms/max_tokens/concurrency 也必须一致——
  concurrency 变了服务端批组成就变,greedy 续写的 token 数会有数值抖动
  (replay_inject.py 文件头已列这条已知偏差)。本壳对所有 θ 用同一个 --concurrency。
- 省 token 用**部署总账**,不是"注入成功那些事件的均值":
      省 token 比例 = Σ(inject 段省下的 token) / Σ(nofill 段在全部出手事件上的 token)
  分母是**全部出手事件**。出手了但预测不对因而没注入的(skip 口径),省 0 但照样
  占分母——否则会把"探针猜错"的代价从省 token 轴上抹掉,报出偏乐观的数。
- 正确率轴在 skip 口径下量的是**调用一致率**(预测的整条调用与真实是否一致),
  不是任务级成绩。任务级要等 miss_policy=execute 落地。这条差别必须写进报告,
  不许静默当成"正确率"。

用法:
  # run 段:六个 θ 铺到三个专用服务上
  cprobe-env/bin/python pipeline/inject/sweep_theta.py run \\
      --runs pipeline/inject/runs/aw_gptoss_th050,...,aw_gptoss_th095 \\
      --services http://tokyo108:8111/v1,http://tokyo108:8112/v1,http://tokyo108:8113/v1

  # 曲线装配
  cprobe-env/bin/python pipeline/inject/sweep_theta.py curve \\
      --runs pipeline/inject/runs/aw_gptoss_th050,... \\
      --out pipeline/inject/THETA_CURVE
"""

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PY = str(ROOT / "cprobe-env" / "bin" / "python")
REPLAY = str(HERE / "replay_inject.py")

# 打印锁:多线程同时写 stdout 会串行
_PRINT = threading.Lock()


def say(msg):
    with _PRINT:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ run

def service_alive(url, timeout=10):
    """探 /v1/models 有没有 gpt-oss-120b。发请求前先确认服务在,否则白跑一轮。"""
    probe = url.rstrip("/")
    if probe.endswith("/v1"):
        probe += "/models"
    else:
        probe += "/v1/models"
    try:
        with urllib.request.urlopen(probe, timeout=timeout) as r:
            return b"gpt-oss-120b" in r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def stage_done(d, stage, tag=""):
    """幂等判据。run 看 raw.jsonl 行数够不够,score 看 INJECT_REPORT.json 在不在。"""
    if stage == "score":
        return (d / f"INJECT_REPORT{tag}.json").exists()
    raw = d / f"raw{tag}.jsonl"
    if not raw.exists():
        return False
    # 期望行数 = nofill(每个出手事件一条) + inject(实际注入的一条)
    cfg = json.loads((d / "plan_config.json").read_text())
    want = cfg["n_planned"] + cfg["n_inject"]
    got = sum(1 for _ in open(raw))
    # 允许个别请求失败(r10 就有 1 条失败),差 1% 以内算跑完
    return got >= want * 0.99


def one_theta(d, svc, a):
    """一个 θ 的 run + score。返回 (dir, ok, note)。"""
    d = Path(d)
    cfg = json.loads((d / "plan_config.json").read_text())
    theta = cfg["theta"]
    log = HERE / "logs" / f"new1_thsw_run_{d.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    if stage_done(d, "run", a.tag):
        say(f"θ={theta} run 段已完成,跳过")
    else:
        cmd = [PY, REPLAY, "run",
               "--plan", str(d / "plan.jsonl"),
               "--base-url", svc,
               "--model", a.model,
               "--arms", a.arms,
               "--concurrency", str(a.concurrency),
               "--max-tokens", str(a.max_tokens),
               "--timeout", str(a.timeout)]
        if a.tag:
            cmd += ["--tag", a.tag]
        say(f"θ={theta} run 段起飞 -> {svc} (期望 "
            f"{cfg['n_planned'] + cfg['n_inject']} 条,日志 {log.name})")
        with open(log, "w") as f:
            f.write(f"# {' '.join(cmd)}\n")
            f.flush()
            rc = subprocess.run(cmd, cwd=str(ROOT), stdout=f,
                                stderr=subprocess.STDOUT).returncode
        if rc != 0:
            return (str(d), False, f"run 段退出码 {rc},看 {log}")
        if not stage_done(d, "run", a.tag):
            return (str(d), False, f"run 段跑完但产物不足,看 {log}")
        say(f"θ={theta} run 段完成")

    if stage_done(d, "score", a.tag):
        say(f"θ={theta} score 已完成,跳过")
        return (str(d), True, "已完成(跳过)")
    cmd = [PY, REPLAY, "score", "--run-dir", str(d)]
    if a.tag:
        cmd += ["--tag", a.tag]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        return (str(d), False, f"score 退出码 {r.returncode}: {r.stderr[-400:]}")
    say(f"θ={theta} score 完成")
    return (str(d), True, "ok")


def cmd_run(a):
    dirs = [Path(x.strip()) for x in a.runs.split(",") if x.strip()]
    svcs = [x.strip() for x in a.services.split(",") if x.strip()]
    missing = [d for d in dirs if not (d / "plan.jsonl").exists()]
    if missing and not a.skip_missing:
        raise SystemExit("这些 θ 还没有 plan.jsonl(plan 段没跑完?):\n  "
                         + "\n  ".join(str(d) for d in missing))
    if missing:
        # 分波发射用:plan 段先完成的先跑,别让服务空等
        say("跳过还没就绪的 θ(plan 段未完成):"
            + ", ".join(d.name for d in missing))
        dirs = [d for d in dirs if d not in missing]
        if not dirs:
            raise SystemExit("没有一个 θ 就绪,不发")
    dead = [s for s in svcs if not service_alive(s)]
    if dead:
        raise SystemExit("这些服务探活失败,先把服务起好:\n  " + "\n  ".join(dead))
    say(f"{len(dirs)} 个 θ 铺到 {len(svcs)} 个服务上,"
        f"concurrency={a.concurrency} arms={a.arms}")

    # 服务池:一个 θ 占一个服务,跑完还回池子,空出来就接下一个
    pool = queue.Queue()
    for s in svcs:
        pool.put(s)

    def work(d):
        svc = pool.get()
        try:
            return one_theta(d, svc, a)
        finally:
            pool.put(svc)

    results = []
    # 大的 θ 点先起(触发多的先跑),尾巴上不容易剩个大活拖时间
    order = sorted(dirs, key=lambda d: -json.loads(
        (d / "plan_config.json").read_text())["n_planned"])
    with ThreadPoolExecutor(max_workers=len(svcs)) as ex:
        futs = {ex.submit(work, d): d for d in order}
        for fu in as_completed(futs):
            results.append(fu.result())

    print("\n=== θ 扫描结果 ===")
    bad = 0
    for d, ok, note in sorted(results):
        print(f"{'OK ' if ok else 'FAIL'} {Path(d).name:28s} {note}")
        bad += (not ok)
    if bad:
        raise SystemExit(f"{bad} 个 θ 没跑成,别急着装曲线")
    print("全部完成,可以跑 curve 子命令装配曲线")


# ---------------------------------------------------------------- curve

def load_point(d, tag=""):
    """读一个 θ 目录,算出曲线上这一点的诚实数字。"""
    d = Path(d)
    rep_p = d / f"INJECT_REPORT{tag}.json"
    per_p = d / f"per_event{tag}.jsonl"
    if not rep_p.exists():
        return None
    rep = json.loads(rep_p.read_text())
    cfg = rep["config"]
    per = [json.loads(l) for l in open(per_p)]
    nof = [r for r in per if r["arm"] == "nofill"]
    inj = [r for r in per if r["arm"] == "inject"]

    # 部署总账:分母是**全部出手事件**的 nofill token(含出手但没注入的),
    # 分子是实际省下的 token。skip 口径下没注入的那些省 0,但照样占分母。
    denom = sum(r["out_tok"] for r in nof)
    saved = sum(r["saved_tok"] for r in inj if r["saved_tok"] is not None)
    n_fired = cfg["n_fired"]
    n_events = cfg["n_events_test"]
    n_inject = cfg["n_inject"]

    # 正确率轴(skip 口径 = 调用一致率,不是任务级成绩)
    tool_ok = sum(1 for r in nof if r["tool_ok"]) / len(nof) if nof else None
    full_ok = n_inject / n_fired if n_fired else None

    ia = rep["by_arm"].get("inject", {})
    # 死区诊断:后 40% 才出手的占多少(这些平均是亏 token 的)
    late = sum(1 for r in inj if r["depth"] >= 0.6)
    return dict(
        theta=cfg["theta"], miss_policy=cfg["miss_policy"],
        theta_source=cfg.get("theta_source", "risk-derived"),
        n_events=n_events, n_fired=n_fired, n_inject=n_inject,
        coverage=round(n_fired / n_events, 4) if n_events else None,
        # —— 纵轴一:省 token ——
        saved_tok_total=saved,
        nofill_tok_total=denom,
        saved_ratio_deployed=round(saved / denom, 5) if denom else None,
        saved_tok_mean_injected=ia.get("saved_tok_mean"),
        saved_tok_median_injected=ia.get("saved_tok_median"),
        saved_positive=ia.get("saved_positive"),
        # —— 纵轴二:正确率(skip 口径 = 调用一致率) ——
        tool_ok=round(tool_ok, 4) if tool_ok is not None else None,
        full_call_ok=round(full_ok, 4) if full_ok is not None else None,
        # —— 机制诊断 ——
        adopted=ia.get("advanced"), repeated=ia.get("repeated_injected"),
        truncated=ia.get("truncated"),
        late_trigger_share=round(late / len(inj), 4) if inj else None,
        run_dir=str(d))


def cmd_curve(a):
    dirs = [x.strip() for x in a.runs.split(",") if x.strip()]
    pts, skipped = [], []
    for d in dirs:
        p = load_point(d, a.tag)
        (pts if p else skipped).append(p or d)
    if not pts:
        raise SystemExit("一个点都没装上(都还没 score?)")
    pts.sort(key=lambda p: p["theta"])

    pol = sorted({p["miss_policy"] for p in pts})
    L = ["# θ 扫描曲线:省 token vs 正确率", "",
         f"- 点数 {len(pts)}  θ 从 {pts[0]['theta']} 到 {pts[-1]['theta']}",
         f"- miss_policy = {','.join(pol)}",
         f"- 事件总数 {pts[0]['n_events']}(test 段全部工具调用事件)", ""]
    if len(pol) > 1:
        L.append("> ⚠️ 各点 miss_policy 不一致,不能画在同一条曲线上。")
        L.append("")
    L += [
        "> **省 token 比例 = 部署总账**:分子是 inject 段实际省下的 token 总和,",
        "> 分母是 nofill 段在**全部出手事件**上的 token 总和。出手但预测不对、",
        "> 因而没注入的事件省 0 却照样占分母——探针猜错的代价不许从这一轴上抹掉。",
        "> **正确率这一轴在 skip 口径下量的是调用一致率**(预测的整条调用与真实是否",
        "> 一致),**不是任务级成绩**。任务级要等 miss_policy=execute 落地。",
        "> 采纳率 = 续写去干了别的事(说明吃下了注入);重调率 = 又调了一遍被注入的工具。",
        "", "## 主表", "",
         "| θ | 覆盖率 | 出手 | 注入 | 省token比例(部署) | 省token总量 | "
         "注入均省 | 注入中位 | 省为正 | 工具对 | 整条调用对 | 采纳 | 重调 | 晚出手占比 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in pts:
        L.append(
            f"| {p['theta']} | {p['coverage']} | {p['n_fired']} | "
            f"{p['n_inject']} | {p['saved_ratio_deployed']} | "
            f"{p['saved_tok_total']} | {p['saved_tok_mean_injected']} | "
            f"{p['saved_tok_median_injected']} | {p['saved_positive']} | "
            f"{p['tool_ok']} | {p['full_call_ok']} | {p['adopted']} | "
            f"{p['repeated']} | {p['late_trigger_share']} |")

    # 主图的两条线单列一张窄表,方便直接誊进论文
    L += ["", "## 主图两条线(横轴覆盖率)", "",
          "| 覆盖率 | θ | 省 token 比例 | 调用一致率 |", "|---|---|---|---|"]
    for p in pts:
        L.append(f"| {p['coverage']} | {p['theta']} | "
                 f"{p['saved_ratio_deployed']} | {p['full_call_ok']} |")
    if skipped:
        L += ["", "## 还没装上的点(没有 INJECT_REPORT.json)", ""]
        L += [f"- {s}" for s in skipped]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    out.with_suffix(".json").write_text(
        json.dumps(dict(points=pts, skipped=skipped), ensure_ascii=False,
                   indent=1))
    print("\n".join(L))
    print(f"\n落盘 -> {out.with_suffix('.md')} / {out.with_suffix('.json')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="并发把各 θ 的 run+score 跑完")
    p.add_argument("--runs", required=True, help="逗号分隔的 run 目录")
    p.add_argument("--services", required=True,
                   help="逗号分隔的服务 base-url,一个 θ 占一个")
    p.add_argument("--model", default="gpt-oss-120b")
    p.add_argument("--arms", default="nofill,inject")
    p.add_argument("--concurrency", type=int, default=16,
                   help="各 θ 必须用同一个值,变了服务端批组成就变")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--tag", default="")
    p.add_argument("--skip-missing", action="store_true",
                   help="plan 段还没跑完的 θ 跳过而不报错(分波发射用)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("curve", help="装配曲线")
    p.add_argument("--runs", required=True)
    p.add_argument("--out", default="pipeline/inject/THETA_CURVE")
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_curve)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
