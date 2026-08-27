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
  concurrency 变了服务端批组成就变,续写的 token 数会有数值抖动
  (replay_inject.py 文件头已列这条已知偏差)。本壳对所有 θ 用同一个 --concurrency。
- 省 token 用**部署总账**,不是"注入成功那些事件的均值":
      省 token 比例 = Σ(inject 段省下的 token) / Σ(nofill 段在全部出手事件上的 token)
  分母是**全部出手事件**。出手了但预测不对因而没注入的(skip 口径),省 0 但照样
  占分母——否则会把"探针猜错"的代价从省 token 轴上抹掉,报出偏乐观的数。
- 正确率轴量的是**调用一致率**(预测的整条调用与真实是否一致),**不是任务级成绩**。
  两个口径的差别:
    skip 档    猜错就不注入,于是猜错的代价没进注入内容这条账(偏乐观)
    execute 档 猜错也注入(注入真实报错),代价进账了 —— 但它量到的仍是**单步**
               调用一致率。execute **给不出 appworld 的 Test 分数**:一个事件只
               续写一步、不跑到底、不调 world.evaluate()。真正的任务级那条轴要
               另建 in-loop rollout(采集循环里挂探针、触发就注入、走完整题再
               评测),是一批新采集,不在本壳范围内。
  报告里把 execute 档写成"任务级正确率"就是虚报。
- execute 档多两段前置(都是纯 CPU、不占卡,**可以与别的 θ 点的 run 段并行**):
  exec_calls.py 真执行 -> merge-exec 合成 plan_exec.jsonl。依赖顺序是
  plan -> exec -> merge-exec -> run -> score;本壳的 run 段用 --plan-file
  指到 plan_exec.jsonl,并在发射前检查有没有漏跑 exec 段。
- **各点的 plan 段必须同参数同机器**,尤其 `--bs` 要一致。实测(2026-08-01,
  θ=0.925 跑两次:r10 用 `--bs 32` 在 tokyo105,th0925 用默认 `--bs 8` 在 tokyo106):
  探针出手这一层完全可复现——出手事件集合、触发句位置、深度、工具级预测
  四项零差异;分叉出在参数产线的生成上,14/1061 条(1.3%)写出了不同的
  调用(例:同一事件 r10 写 show_api_doc(...show_album),th0925 写 ...show_liked_songs),
  连带 full_call_ok 差 7 个、可注入数 689 vs 686。
  已定位的原因是 **batch size 变了**:left padding 长度随之变,批内前向的浮点
  舍入不同,近似平局处 argmax 被翻转。(另有 446/1061 个 conf 在第 7 位小数上
  不同,那是 CPU softmax 归约顺序随线程数变,不改变任何出手决定——sent_idx
  零差异可证。)
  影响只有 0.4%,远小于各 θ 点之间的差,但混参会在曲线里掺进一个异构点。
  所以铁律:一条曲线的六个点用同一个 --bs、同一台机器,并在报告里写明。

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
import os
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


def config_of(d, plan_file="plan.jsonl"):
    """plan 文件对应的 config。execute 档换成 plan_exec.jsonl 后,期望行数与
    permit 口径都要从 plan_exec_config.json 读 —— 硬读 plan_config.json 会拿到
    exec 段之前的旧统计(n_inject 那时是 0),幂等判据就永远说"没跑完"。"""
    return json.loads((d / (Path(plan_file).stem + "_config.json")).read_text())


def stage_done(d, stage, tag="", plan_file="plan.jsonl"):
    """幂等判据。run 看 raw.jsonl 行数够不够,score 看 INJECT_REPORT.json 在不在。"""
    if stage == "score":
        return (d / f"INJECT_REPORT{tag}.json").exists()
    raw = d / f"raw{tag}.jsonl"
    if not raw.exists():
        return False
    # 期望行数 = nofill(每个出手事件一条) + inject(实际注入的一条)
    cfg = config_of(d, plan_file)
    want = cfg["n_planned"] + cfg["n_inject"]
    got = sum(1 for _ in open(raw))
    # 允许个别请求失败(r10 就有 1 条失败),差 1% 以内算跑完
    return got >= want * 0.99


def one_theta(d, svc, a):
    """一个 θ 的 run + score,带目录锁。返回 (dir, ok, note)。

    同一个 θ 不许被两个池子同时跑。run 段自带断点续跑(读 raw.jsonl 建已完成
    集合只补缺的),所以**单进程杀掉重启是安全的、零损失**;但两个进程并行会
    各自读一次已完成集合再同时往同一个 raw.jsonl 追加,既重复干活又写重复行。
    锁文件记 pid 与起始时间,便于判断是残留锁还是真有进程在跑。
    """
    d = Path(d)
    lk = d / ".run_lock"
    if lk.exists():
        try:
            info = json.loads(lk.read_text())
        except Exception:
            info = {}
        return (str(d), False,
                f"被别的进程占着(锁 {lk.name} pid={info.get('pid')} "
                f"起于 {info.get('t')});确认没进程在跑再删这个锁文件")
    lk.write_text(json.dumps(dict(pid=os.getpid(),
                                  t=time.strftime("%F %T"), svc=svc)))
    try:
        return _one_theta(d, svc, a)
    finally:
        lk.unlink(missing_ok=True)


def _one_theta(d, svc, a):
    cfg = config_of(d, a.plan_file)
    theta = cfg["theta"]
    log = HERE / "logs" / f"new1_thsw_run_{d.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    if stage_done(d, "run", a.tag, a.plan_file):
        say(f"θ={theta} run 段已完成,跳过")
    else:
        cmd = [PY, REPLAY, "run",
               "--plan", str(d / a.plan_file),
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
        # 追加而非截断:run 段能断点续跑,重启后上一轮的日志要留着好查
        with open(log, "a") as f:
            f.write(f"\n# [{time.strftime('%F %T')}] {' '.join(cmd)}\n")
            f.flush()
            rc = subprocess.run(cmd, cwd=str(ROOT), stdout=f,
                                stderr=subprocess.STDOUT).returncode
        if rc != 0:
            return (str(d), False, f"run 段退出码 {rc},看 {log}")
        if not stage_done(d, "run", a.tag, a.plan_file):
            return (str(d), False, f"run 段跑完但产物不足,看 {log}")
        say(f"θ={theta} run 段完成")

    if stage_done(d, "score", a.tag, a.plan_file):
        say(f"θ={theta} score 已完成,跳过")
        return (str(d), True, "已完成(跳过)")
    cmd = [PY, REPLAY, "score", "--run-dir", str(d),
           "--plan-file", a.plan_file]
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
    missing = [d for d in dirs if not (d / a.plan_file).exists()]
    if missing and not a.skip_missing:
        raise SystemExit(f"这些 θ 还没有 {a.plan_file}(plan 段没跑完?"
                         "execute 档还要跑完 exec_calls.py + merge-exec):\n  "
                         + "\n  ".join(str(d) for d in missing))
    if missing:
        # 分波发射用:plan 段先完成的先跑,别让服务空等
        say(f"跳过还没就绪的 θ(没有 {a.plan_file}):"
            + ", ".join(d.name for d in missing))
        dirs = [d for d in dirs if d not in missing]
        if not dirs:
            raise SystemExit("没有一个 θ 就绪,不发")
    # execute 档的依赖顺序检查:plan -> exec -> merge-exec -> run。
    # 漏跑 exec 段就等于拿一堆空注入内容去占着服务跑一整轮,发之前挡住
    pend = []
    for d in dirs:
        n = sum(1 for l in open(d / a.plan_file)
                if json.loads(l)["inject_source"] == "exec_pending")
        if n:
            pend.append(f"{d.name}: {n} 个事件还是 exec_pending")
    if pend:
        raise SystemExit("这些 θ 的 exec 段没跑完(纯 CPU、不占卡,先补上):\n  "
                         + "\n  ".join(pend))
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
    order = sorted(dirs, key=lambda d: -config_of(d, a.plan_file)["n_planned"])
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

    # 口径认戳:新版 score 把 saved_tok 换成了原轨迹主对照(saved_baseline
    # ="traj"),老口径的数搬进了 nofill_delta 列。曲线的每个数字都必须和
    # 历史点同一把尺(nofill 分母),所以 traj 报告一律改读 nofill_delta。
    sb = rep.get("saved_baseline", "nofill")
    if sb == "nofill":
        sv_of = lambda r: r["saved_tok"]
    elif sb == "traj":
        sv_of = lambda r: r.get("nofill_delta")
    else:
        raise SystemExit(f"{rep_p}: 不认识的 saved_baseline={sb!r}")
    if sb == "traj" and inj and all(sv_of(r) is None for r in inj):
        raise SystemExit(f"{per_p}: traj 口径但 nofill_delta 全空,没法换算")

    # 部署总账:分母是**全部出手事件**的 nofill token(含出手但没注入的),
    # 分子是实际省下的 token。skip 口径下没注入的那些省 0,但照样占分母。
    denom = sum(r["out_tok"] for r in nof)
    saved = sum(sv_of(r) for r in inj if sv_of(r) is not None)
    n_fired = cfg["n_fired"]
    n_events = cfg["n_events_test"]
    n_inject = cfg["n_inject"]

    # 正确率轴 = 调用一致率(整条调用与真实是否一致),**不是任务级成绩**
    tool_ok = sum(1 for r in nof if r["tool_ok"]) / len(nof) if nof else None
    is_exec = cfg.get("miss_policy") == "execute"
    if is_exec:
        # execute 档不能拿 n_inject/n_fired 当调用一致率:exec_scope=all 下
        # 出手事件全都注入了,这个比值恒等于 1,会把正确率轴报成满分。
        # 直接数 per_event 里的 full_call_ok(skip 档两种算法数值相同,
        # 所以只在 execute 分支换算法,skip 的历史曲线一个数都不动)
        full_ok = (sum(1 for r in nof if r["full_call_ok"]) / len(nof)
                   if nof else None)
    else:
        full_ok = n_inject / n_fired if n_fired else None
    ex = rep.get("exec") or {}

    ia = rep["by_arm"].get("inject", {})
    # 死区诊断:后 40% 才出手的占多少(这些平均是亏 token 的)
    late = sum(1 for r in inj if r["depth"] >= 0.6)

    # —— 时机头的上限空间 ——
    # 同一批出手事件、同一个分母,只换"哪些事件真的注入"这一个决定:
    #   现行  = 预测对就注入(上面的 saved_ratio_deployed)
    #   深度阈值 = 只在思考段前若干比例处注入(现成信号能吃到多少)
    #   上帝时机 = 只在事后看真能省的那些事件注入(完美时机的上限)
    # 三者之差就是"时机值不值得学"的直接量。
    injd = {r["event"]: r for r in inj}
    nofd = {r["event"]: r for r in nof}

    def spend(fire):
        return sum((injd[e]["out_tok"] if (e in injd and fire(e))
                    else nofd[e]["out_tok"]) for e in nofd)

    def ratio(fire):
        return (denom - spend(fire)) / denom if denom else None

    oracle = ratio(lambda e: (sv_of(injd[e]) or 0) > 0)
    best_cut, best_r = None, -1e9
    for c in [i / 20 for i in range(1, 21)]:
        r = ratio(lambda e, c=c: injd[e]["depth"] < c)
        if r is not None and r > best_r:
            best_cut, best_r = c, r
    losing = [r for r in inj if (sv_of(r) or 0) <= 0]

    # by_arm 的 saved_* 聚合在 traj 报告里是原轨迹口径,曲线要 nofill 口径,
    # 只能从 per_event 现算(算法与 replay_inject 的 agg 逐字同)
    if sb == "traj":
        sv = sorted(x for x in (sv_of(r) for r in inj) if x is not None)
        sv_mean = round(sum(sv) / len(sv), 1) if sv else None
        sv_median = sv[len(sv) // 2] if sv else None
        sv_pos = (round(sum(1 for x in sv if x > 0) / len(sv), 4)
                  if sv else None)
    else:
        sv_mean = ia.get("saved_tok_mean")
        sv_median = ia.get("saved_tok_median")
        sv_pos = ia.get("saved_positive")
    return dict(
        theta=cfg["theta"], miss_policy=cfg["miss_policy"],
        theta_source=cfg.get("theta_source", "risk-derived"),
        n_events=n_events, n_fired=n_fired, n_inject=n_inject,
        coverage=round(n_fired / n_events, 4) if n_events else None,
        # —— 纵轴一:省 token ——
        saved_tok_total=saved,
        nofill_tok_total=denom,
        saved_ratio_deployed=round(saved / denom, 5) if denom else None,
        saved_tok_mean_injected=sv_mean,
        saved_tok_median_injected=sv_median,
        saved_positive=sv_pos,
        per_event_baseline=sb,
        # —— 纵轴二:调用一致率(**不是任务级成绩**) ——
        tool_ok=round(tool_ok, 4) if tool_ok is not None else None,
        full_call_ok=round(full_ok, 4) if full_ok is not None else None,
        # —— execute 档专属:猜错的代价 ——
        exec_error_rate=ex.get("exec_error_rate"),
        n_exec_error=ex.get("n_exec_error"),
        n_exec_missing=ex.get("n_exec_missing"),
        n_exec_drift=ex.get("n_drift"),
        exec_acceptance=(f"{ex['acceptance_matched']}/{ex['acceptance_n']}"
                         if ex.get("acceptance_n") else None),
        # —— 机制诊断 ——
        adopted=ia.get("advanced"), repeated=ia.get("repeated_injected"),
        truncated=ia.get("truncated"),
        # 失控率:续写一路写到 max_tokens 上限才停。这本身是个结果——注入会
        # 把它压下去(实测 θ=0.95:不注入 8.0%、注入 4.8%);同时它也是求和型
        # 指标不稳的根源:一条失控生成 ~8192 token,普通的才几百,翻转一条就
        # 摆动八千,而翻不翻只取决于浮点噪声。
        trunc_nofill=(round(sum(r["finish_reason"] == "length" for r in nof)
                            / len(nof), 4) if nof else None),
        trunc_inject=(round(sum(r["finish_reason"] == "length" for r in inj)
                            / len(inj), 4) if inj else None),
        late_trigger_share=round(late / len(inj), 4) if inj else None,
        # —— 时机头的上限空间 ——
        saved_ratio_oracle_timing=round(oracle, 5) if oracle is not None else None,
        saved_ratio_best_depth=round(best_r, 5) if best_r > -1e8 else None,
        best_depth_cut=best_cut,
        headroom_captured=(round((saved / denom) / oracle, 4)
                           if oracle and denom and oracle > 0 else None),
        n_losing_inject=len(losing),
        tok_lost_by_losing=-sum(sv_of(r) or 0 for r in losing),
        tok_gained_by_winning=sum(sv_of(r) for r in inj
                                  if (sv_of(r) or 0) > 0),
        run_dir=str(d))


def cmd_curve(a):
    dirs = [x.strip() for x in a.runs.split(",") if x.strip()]
    ctrl_dirs = [x.strip() for x in (a.control or "").split(",") if x.strip()]
    pts, skipped = [], []
    for d in dirs:
        p = load_point(d, a.tag)
        (pts if p else skipped).append(p or d)
    ctrls = [q for q in (load_point(d, a.tag) for d in ctrl_dirs) if q]
    if not pts:
        raise SystemExit("一个点都没装上(都还没 score?)")
    dup = {p["theta"] for p in pts}
    if len(dup) != len(pts):
        raise SystemExit(
            f"主曲线里有重复的 θ({sorted(dup)}) —— 同一个 θ 两行会让报告自相矛盾。"
            "架构对照/口径对照那类副本请用 --control 传,别混进 --runs。")
    pts.sort(key=lambda p: p["theta"])
    ctrls.sort(key=lambda p: p["theta"])

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
        "> **正确率这一轴量的是调用一致率**(预测的整条调用与真实是否一致),",
        "> **不是任务级成绩**。",
        "> 采纳率 = 续写去干了别的事(说明吃下了注入);重调率 = 又调了一遍被注入的工具。"]
    if "skip" in pol:
        L += ["> **skip 口径**:预测不对就不注入,所以猜错的代价没进"
              "**注入内容**这条账(只进了省 token 的分母)。"]
    if "execute" in pol:
        L += ["> **execute 口径**:预测不对也注入 —— 把预测调用放回 appworld 真"
              "环境执行,拿回什么就注入什么(包括报错),猜错的代价这才全进账。",
              "> 但它量到的仍是**单步调用一致率**:一个事件只续写一步、不跑到底、",
              "> 不调 world.evaluate()。**execute 给不出 appworld 的 Test "
              "分数**,写成「任务级正确率」就是虚报。"]
    L += ["", "## 主表", "",
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

    if "execute" in pol:
        L += ["", "## execute 档:猜错的代价长什么样", "",
              "> 真执行的返回原样注入,报错也注入。**报错率** = 探针猜出来的"
              "那条调用在真环境里根本跑不通的比例;",
              "> **验收线**是 hit 且代码块只含一个调用的事件里,执行输出与轨迹里"
              "录下的 result 逐字相同的个数(补引号那步有没有补错,看这一栏)。",
              "> **前缀漂移**是重放到该步时输出与录下的不一致 —— 这些事件是拿错"
              "状态执行的,不能当真账。",
              "",
              "| θ | 注入 | 执行报错 | 报错率 | 没拿到执行记录 | 前缀漂移 | 验收线 |",
              "|---|---|---|---|---|---|---|"]
        for p in pts:
            if p["miss_policy"] != "execute":
                continue
            L.append(f"| {p['theta']} | {p['n_inject']} | "
                     f"{p['n_exec_error']} | {p['exec_error_rate']} | "
                     f"{p['n_exec_missing']} | {p['n_exec_drift']} | "
                     f"{p['exec_acceptance']} |")

    # 时机头的上限空间:同一批出手事件、同一个分母,只换"哪些真注入"这一个决定
    L += ["", "## 时机值不值得学(同一批出手事件,只换出手时刻的决定)", "",
          "> 三列都是部署总账口径、同一个分母。**现行** = 预测对就注入;",
          "> **深度阈值** = 只在思考段前若干比例处注入(现成信号,不用学);",
          "> **上帝时机** = 事后只在真能省的事件上注入(完美时机的上限)。",
          "> 吃到上限的比例 = 现行 / 上帝时机。这一栏越低,时机头的空间越大。",
          "",
          "| θ | 现行 | 深度阈值(最优切点) | 上帝时机 | 吃到上限 | "
          "亏token的注入 | 省下 | 倒亏 |",
          "|---|---|---|---|---|---|---|---|"]
    for p in pts:
        L.append(
            f"| {p['theta']} | {p['saved_ratio_deployed']} | "
            f"{p['saved_ratio_best_depth']} (depth<{p['best_depth_cut']}) | "
            f"{p['saved_ratio_oracle_timing']} | {p['headroom_captured']} | "
            f"{p['n_losing_inject']}/{p['n_inject']} | "
            f"{p['tok_gained_by_winning']} | {p['tok_lost_by_losing']} |")
    if ctrls:
        # 对照点:同一个 θ、同一份 plan,只换服务侧条件(卡型/负载/并发)重跑一遍。
        # 曲线本身的六个点必须同架构;这张表回答的是"换条件到底差多少",
        # 也就是曲线上的差值有多少可能只是 serving 噪声。
        base = {p["theta"]: p for p in pts}
        L += ["", "## 服务侧对照(同 θ 同 plan,只换服务条件重跑)", "",
              "> 续写在服务端批组成变化下会有数值抖动"
              "(replay_inject.py 文件头已列这条已知偏差)。",
              "> 这张表量的就是那点抖动:同一个 θ、同一份 plan,换一批服务重跑,",
              "> 省 token 比例差多少。**这个差值是曲线的噪声地板**——曲线上小于",
              "> 它的起伏不能当成真实趋势来读。", "",
              "| θ | 主曲线 省token比例 | 对照 省token比例 | 差 | "
              "主曲线 调用一致率 | 对照 调用一致率 | 对照来源 |",
              "|---|---|---|---|---|---|---|"]
        gaps = []
        for q in ctrls:
            b = base.get(q["theta"])
            if b is None:
                L.append(f"| {q['theta']} | (主曲线无此点) | "
                         f"{q['saved_ratio_deployed']} | — | — | "
                         f"{q['full_call_ok']} | {Path(q['run_dir']).name} |")
                continue
            g = (q["saved_ratio_deployed"] - b["saved_ratio_deployed"]
                 if None not in (q["saved_ratio_deployed"],
                                 b["saved_ratio_deployed"]) else None)
            if g is not None:
                gaps.append(abs(g))
            L.append(
                f"| {q['theta']} | {b['saved_ratio_deployed']} | "
                f"{q['saved_ratio_deployed']} | "
                f"{('%+.5f' % g) if g is not None else '—'} | "
                f"{b['full_call_ok']} | {q['full_call_ok']} | "
                f"{Path(q['run_dir']).name} |")
        if gaps:
            L += ["", f"**求和型指标的噪声地板 = {max(gaps):.5f}**"
                  f"(对照点里最大的绝对差,共 {len(gaps)} 对)。"]

        # 逐指标算噪声地板,并跟该指标在主曲线上的跨度比 —— 噪声大过跨度的
        # 那条轴根本不能画。求和型的"省 token 比例"实测就栽在这里:一条失控
        # 生成 ~8192 token,翻不翻只取决于浮点噪声,总量就被这枚硬币主导。
        METRICS = [("省token比例(求和)", "saved_ratio_deployed"),
                   ("省token中位", "saved_tok_median_injected"),
                   ("省为正", "saved_positive"),
                   ("调用一致率", "full_call_ok"),
                   ("采纳率", "adopted"),
                   ("失控率(不注入)", "trunc_nofill"),
                   ("失控率(注入)", "trunc_inject")]
        L += ["", "### 逐指标:噪声地板 vs 主曲线跨度", "",
              "> 噪声地板 = 三对对照里同 θ 两次跑的最大绝对差(只换服务条件)。",
              "> 跨度 = 该指标在主曲线六个点上的最大值减最小值。",
              "> **噪声地板 ≥ 跨度的指标不能画进主图**——它测到的全是抖动。", "",
              "| 指标 | 噪声地板 | 主曲线跨度 | 跨度/噪声 | 能不能画 |",
              "|---|---|---|---|---|"]
        for name, key in METRICS:
            ns = [abs(q[key] - base[q["theta"]][key])
                  for q in ctrls
                  if q["theta"] in base and q.get(key) is not None
                  and base[q["theta"]].get(key) is not None]
            vs = [p[key] for p in pts if p.get(key) is not None]
            if not ns or len(vs) < 2:
                continue
            nf, span = max(ns), max(vs) - min(vs)
            r = span / nf if nf else float("inf")
            L.append(f"| {name} | {nf:.4f} | {span:.4f} | {r:.1f}x | "
                     f"{'可' if r >= 3 else ('勉强' if r >= 2 else '**不可**')} |")
        L += ["", "> 判据:跨度至少要有噪声的 3 倍才算能读,2-3 倍勉强,不足 2 倍不可。"]

    if skipped:
        L += ["", "## 还没装上的点(没有 INJECT_REPORT.json)", ""]
        L += [f"- {s}" for s in skipped]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text("\n".join(L) + "\n")
    out.with_suffix(".json").write_text(
        json.dumps(dict(points=pts, controls=ctrls, skipped=skipped),
                   ensure_ascii=False,
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
    p.add_argument("--plan-file", default="plan.jsonl",
                   help="execute 档用 plan_exec.jsonl(config/幂等判据都跟着它)")
    p.add_argument("--skip-missing", action="store_true",
                   help="plan 段还没跑完的 θ 跳过而不报错(分波发射用)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("curve", help="装配曲线")
    p.add_argument("--runs", required=True)
    p.add_argument("--out", default="pipeline/inject/THETA_CURVE")
    p.add_argument("--control", default="",
                   help="服务侧对照点(同 θ 同 plan、只换服务条件重跑的副本),"
                        "单列一张表算噪声地板,不混进主曲线")
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_curve)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
