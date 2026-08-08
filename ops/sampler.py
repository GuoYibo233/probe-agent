#!/usr/bin/env python3
"""采样器:长程任务的常驻监控进程(设计文档 §3-§5)。
每轮:读台账 → tail 日志抓心跳(NFS 本地读) → ssh 探存活 → verdicts.judge
→ append 采样历史 + 原子写 latest.json/state.json。
本文件只做 IO 和攒状态,判定口径全在 ops/verdicts.py。stdlib only。
用法: sampler.py [--once] [--interval 60] [--port 8377](网页 Task 7 加)
"""
import argparse
import html
import http.server
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS))
import heartbeat  # noqa: E402
import verdicts  # noqa: E402
from gpu_jobs import live_sessions, DEFAULT_HOSTS  # noqa: E402
import gpu_jobs  # noqa: E402

# 本地副本,不直接复用 gpu_jobs.load_reg——那个函数体里读的是
# gpu_jobs 模块自己的全局 REG_PATH,单测靠 monkeypatch
# `sampler.REG_PATH` 把台账指到 tmp 目录,只有这里自己读这个名字才生效。
REG_PATH = gpu_jobs.REG_PATH


def load_reg():
    """台账读入口——读的是本模块的 REG_PATH(默认与 gpu_jobs.REG_PATH
    同一个文件),单测把它指到 tmp 目录。"""
    if not os.path.exists(REG_PATH):
        return {"active": [], "history": []}
    with open(REG_PATH) as f:
        return json.load(f)


MONITOR_DIR = Path(os.environ.get(
    "NEW1_MONITOR_DIR",
    "/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/monitor"))

# state.json 里 recent_beats 的截断长度——和判定引擎"典型心跳间隔"用的
# 窗口(typical_beats)对齐,超出这个窗口的心跳对判定已经没有意义
_BEATS_CAP = verdicts.DEFAULTS["typical_beats"]

# 连续这么多轮探测失败(设计文档 §4)只在 row 上亮红,不触发事故——
# 分不清死活就不动手,fail-closed 一以贯之
_PROBE_FAIL_ROUNDS_RED = 10


def read_beats(log_path, max_bytes=262144):
    """日志尾 max_bytes 字节里的所有心跳行(升序)。tqdm 的 \\r 先换 \\n。
    文件不存在/读不了返回空列表——采样是常驻循环,单个分片的日志问题
    不许把整轮采样弄炸。"""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = tail.replace("\r", "\n").splitlines()
    beats = []
    for line in lines:
        rec = heartbeat.parse(line)
        if rec is not None:
            beats.append(rec)
    return beats


# vLLM 吞吐行(工单 13/实施计划 Task 15):2026-08-08 从真实日志核实的格式,
# 源于 vllm 0.26.0 `vllm/v1/metrics/loggers.py:263-313`。默认每 10 秒一条,
# 引擎空闲时降级成 debug 不打印——断流不代表停摆,判定不看这行,只用来
# 出 token 速率显示位。原文样例(逐字节核对过):
#   Engine 000: Avg prompt throughput: 785.1 tokens/s, Avg generation
#   throughput: 671.8 tokens/s, Running: 4 reqs, Waiting: 0 reqs, ...
VLLM_STATS_RE = re.compile(
    r"Avg prompt throughput:\s*([\d.]+)\s*tokens/s,\s*"
    r"Avg generation throughput:\s*([\d.]+)\s*tokens/s,\s*"
    r"Running:\s*(\d+)\s*reqs")


def parse_vllm_stats(text):
    """vLLM 吞吐行 -> {"prompt_tok_s","gen_tok_s","running"};无匹配 None。
    `text` 可以是多行,命中多条时取最后一条(最新一次采样)。只做速率显示,
    不进判定(判定是 probe_port,见 verdicts._judge_service)。"""
    matches = list(VLLM_STATS_RE.finditer(text))
    if not matches:
        return None
    m = matches[-1]
    return {"prompt_tok_s": float(m.group(1)), "gen_tok_s": float(m.group(2)),
            "running": int(m.group(3))}


def read_vllm_stats(log_path, max_bytes=8192):
    """服务分片日志尾 max_bytes 字节里最新一条吞吐行(工单 13)。日志读不了
    或这一轮没有吞吐行(引擎空闲降级 debug)都返回 None——调用方决定是否
    沿用上一轮的显示值,这里不猜。"""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    return parse_vllm_stats(tail)


def atomic_write(path, obj):
    """tmp + os.replace,与 run.py save_state 同款——半写文件永远不会被
    出口读到。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def append_jsonl(path, lines):
    """采样历史一个任务一个文件,逐轮追加(每行一个采样点)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def load_state():
    """state.json 不在/坏了 -> {}(采样器无状态重启后从这里恢复,
    读不到就当从零开始,不许把常驻进程弄死)。"""
    p = MONITOR_DIR / "state.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def read_incidents_tail(n=20):
    """incidents.jsonl 的最后 n 行(Task 14 才会真的写这个文件;
    文件还不存在时返回空列表——不是错误)。"""
    p = MONITOR_DIR / "incidents.jsonl"
    try:
        lines = p.read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


INCIDENT_PROMPT = """你是 new1 工程的事故 agent,只干"把实验办好"一件事,不写给人看的报告。
事故: 任务 {job} 分片 {idx}(session {session},host {host},GPU {gpus})判定 {verdict}。
日志: {log}
先看现场: tail -c 8192 '{log}' | tr '\\r' '\\n' | tail -40
台账 json: cd /home/y-guo/reproduce/new1 && python3 run.py gpu-jobs json
规则(不许越线):
- {refire_clause}
- 判定是 疑似卡死: 只读日志定位原因,禁止 kill 任何 session、禁止改任何文件。
- 只碰这一个分片,别的任务一概不动。
- 结束时输出一行: DONE <你做了什么,15 字内>。
"""

_REFIRE_ALLOWED_CLAUSE = (
    "判定是 已挂: 读日志定位死因后补射一次: "
    "`python3 run.py launch --refire {job} --idx {idx}`;"
    "原卡被占(命令会报错)时 `python3 run.py gpu-jobs free` 挑空卡后加 "
    "`--piece <host>:<gpus>` 重试一次")
_REFIRE_DENIED_CLAUSE = "这个分片补射额度已用完: 只验尸,不许再发射任何东西"


def should_trigger(row, ps):
    """事故触发的纯函数规则(设计 §5,工单 12):`row["escalated"]` 为真,
    且 `ps["incident_open"]` 为空才触发——同一次事故只拉一次 agent。
    `allow_refire` = 判定是 已挂 且这个分片位还没补射过
    (`ps["refires"] == 0`)。返回 (是否触发, 是否许补射)。"""
    if not row.get("escalated"):
        return False, False
    if ps.get("incident_open"):
        return False, False
    allow_refire = (row["verdict"] == verdicts.V_DEAD
                     and ps.get("refires", 0) == 0)
    return True, allow_refire


def build_incident_prompt(row, allow_refire):
    """row + 补射许可 -> 事故 agent 的提示词(纯函数,工单 12)。"""
    if allow_refire:
        refire_clause = _REFIRE_ALLOWED_CLAUSE.format(
            job=row["job"], idx=row["idx"])
    else:
        refire_clause = _REFIRE_DENIED_CLAUSE
    return INCIDENT_PROMPT.format(
        job=row["job"], idx=row["idx"], session=row.get("session"),
        host=row.get("host"), gpus=row.get("gpus"), verdict=row["verdict"],
        log=row.get("log"), refire_clause=refire_clause)


def maybe_trigger_incidents(rows, st):
    """事故触发在 Task 14(工单 12)实装,这里先占位。"""
    pass


def piece_key(job_name, idx):
    return f"{job_name}#{idx}"


def _piece_launched_at(piece, job):
    """分片没有 launched_at(手工 register 的旧格式)就退回 job 的
    started_at,再没有就当 now——宽松处理,登录机和发射机都是 NTP 机器,
    分钟级误差可接受。"""
    la = piece.get("launched_at")
    if la is not None:
        return float(la)
    started = job.get("started_at")
    if started:
        try:
            return datetime.strptime(started, "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            pass
    return time.time()


def probe_port(host, port, timeout=3):
    """服务类分片的端口探测:HTTP GET http://host:port/health,
    连接被拒/超时/任何异常 -> False。vLLM 的 /health 返回 200
    (工单 13 核对后如有出入改这里)。"""
    try:
        with urllib.request.urlopen(
                f"http://{host}:{port}/health", timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _new_piece_state(launched_at, refires=0):
    return {
        "first_beat": None,
        "recent_beats": [],
        "last_new_beat_mono": None,
        "last_done": None,
        "last_total": None,
        "last_unit": None,
        "last_status": None,
        "launched_at": launched_at,
        "alive_last": None,
        "probe_fail_rounds": 0,
        "port_ok": None,
        "port_ever_ok": False,
        "port_fail_rounds": 0,
        "vllm_stats": None,
        "verdict": None,
        "escalated_since_mono": None,
        "incident_open": False,
        "refires": refires,
    }


def update_piece_state(st, job, idx, piece, beats, alive, now_mono,
                        vllm_stats=None):
    """攒一个分片的累计状态(设计 §3):
    - launched_at 变了(补射) -> 整段状态重开,refires += 1
    - beats 里比 last_done/last_ts 新的条目 append 进 recent_beats(截
      ≤ typical_beats 条),并刷新 last_new_beat_mono = now_mono
    - first_beat 只在第一次见到心跳时记
    - alive: None(探测失败) -> alive_last 沿用,probe_fail_rounds += 1;
      True/False -> 直取,probe_fail_rounds = 0
    - 服务类:port_ok 由 probe_port() 出,port_ever_ok/port_fail_rounds
      同理攒;`vllm_stats` 是调用方(sample_once)传进来的这一轮吞吐行解析
      结果(工单 13),只做速率显示,不进判定——这一轮没有吞吐行(引擎空闲
      降级 debug,读不到日志)时 vllm_stats=None,沿用上一轮的显示值,不
      因为断流就把速率显示闪回空白(spec:"空闲不打吞吐行不算停摆")
    返回值是这个分片的状态字典(已经就地挂在 st 里,st 由调用方落盘)。
    """
    key = piece_key(job["name"], idx)
    launched_at = _piece_launched_at(piece, job)
    prev = st.get(key)
    if prev is None:
        ps = _new_piece_state(launched_at, refires=0)
        st[key] = ps
    elif prev.get("launched_at") != launched_at:
        ps = _new_piece_state(launched_at, refires=prev.get("refires", 0) + 1)
        st[key] = ps
    else:
        ps = prev

    # 存活
    if alive is None:
        ps["probe_fail_rounds"] = ps.get("probe_fail_rounds", 0) + 1
    else:
        ps["alive_last"] = alive
        ps["probe_fail_rounds"] = 0

    # 心跳去重与累计
    last_key = None
    if ps["recent_beats"]:
        lb = ps["recent_beats"][-1]
        last_key = (lb["ts"], lb["done"])
    added_new = False
    for b in beats:
        cur = (b["ts"], b["done"])
        if last_key is None or cur > last_key:
            if ps["first_beat"] is None:
                ps["first_beat"] = {"ts": b["ts"], "done": b["done"]}
            ps["recent_beats"].append({
                "ts": b["ts"], "done": b["done"],
                "tok_in": b.get("tok_in"), "tok_out": b.get("tok_out"),
                "loss": b.get("loss"), "status": b.get("status"),
            })
            last_key = cur
            added_new = True
        ps["last_total"] = b.get("total")
        ps["last_unit"] = b.get("unit")
        ps["last_status"] = b.get("status")
    if added_new:
        ps["last_new_beat_mono"] = now_mono
        ps["last_done"] = last_key[1]
    if len(ps["recent_beats"]) > _BEATS_CAP:
        ps["recent_beats"] = ps["recent_beats"][-_BEATS_CAP:]

    # 服务类:端口探测 + 吞吐行显示(工单 13,判定只用 port_ok,不用 vllm_stats)
    if piece.get("kind") == "service":
        port = piece.get("port")
        port_ok = probe_port(piece["host"], port) if port else False
        ps["port_ok"] = port_ok
        if port_ok:
            ps["port_ever_ok"] = True
            ps["port_fail_rounds"] = 0
        else:
            ps["port_fail_rounds"] = ps.get("port_fail_rounds", 0) + 1
        if vllm_stats is not None:
            ps["vllm_stats"] = vllm_stats

    return ps


def build_row(job, idx, piece, ps, now_mono, now_wall):
    """状态 -> 出口 row:调 verdicts.stall_line_s(override=piece 里的
    stall_line) / rates / judge,算 progress_pct 和 eta_s(近期速率没值
    退回平均;都没值 None)。"""
    kind = piece.get("kind", "batch")
    beat_ts = [b["ts"] for b in ps.get("recent_beats", [])]
    stall_s = verdicts.stall_line_s(beat_ts, override=piece.get("stall_line"))
    escalate_s = piece.get("escalate_line")
    warmup_s = job.get("monitor", {}).get(
        "warmup_s", verdicts.DEFAULTS["warmup_line_s"])
    avg_rate, recent_rate = verdicts.rates(
        ps.get("first_beat"), ps.get("recent_beats", []))

    beat_age_s = None
    if ps.get("last_new_beat_mono") is not None:
        beat_age_s = now_mono - ps["last_new_beat_mono"]
    since_launch_s = now_wall - ps.get("launched_at", now_wall)

    p = {
        "kind": kind,
        "alive": ps.get("alive_last"),
        "done": ps.get("last_done"),
        "total": ps.get("last_total"),
        "status": ps.get("last_status"),
        "has_beat": ps.get("first_beat") is not None,
        "since_launch_s": since_launch_s,
        "beat_age_s": beat_age_s,
        "warmup_s": warmup_s,
        "stall_s": stall_s,
        "escalate_s": escalate_s,
        "avg_rate": avg_rate,
        "recent_rate": recent_rate,
        "port_ok": ps.get("port_ok"),
        "port_ever_ok": ps.get("port_ever_ok", False),
        "port_fail_rounds": ps.get("port_fail_rounds", 0),
    }
    verdict, escalated = verdicts.judge(p)
    ps["verdict"] = verdict

    done, total = ps.get("last_done"), ps.get("last_total")
    progress_pct = None
    if done is not None and total:
        progress_pct = round(100 * done / total, 1)
    eta_s = None
    if done is not None and total is not None:
        remaining = total - done
        # 近期速率没值(None)才退回平均;近期速率恰好是 0(真的停了)不能
        # 被 truthy 判断当成"没值"悄悄换成平均速率
        rate_for_eta = recent_rate if recent_rate is not None else avg_rate
        if remaining >= 0 and rate_for_eta:
            eta_s = remaining / rate_for_eta

    last_beat = ps["recent_beats"][-1] if ps.get("recent_beats") else {}
    probe_fail_rounds = ps.get("probe_fail_rounds", 0)

    # 服务类的 tok_in/tok_out 显示位复用心跳协议的同名字段位置,但语义换成
    # 吞吐速率(tokens/s)而不是累计计数——服务分片不产生心跳,last_beat
    # 永远是空 dict,这里改从 vllm_stats 取(工单 13:吞吐行只做显示,不进判定)
    if kind == "service":
        vs = ps.get("vllm_stats") or {}
        tok_in, tok_out = vs.get("prompt_tok_s"), vs.get("gen_tok_s")
    else:
        tok_in, tok_out = last_beat.get("tok_in"), last_beat.get("tok_out")

    return {
        "job": job["name"], "idx": idx, "host": piece["host"],
        "gpus": piece.get("gpus"), "session": piece.get("session"),
        "kind": kind, "verdict": verdict, "escalated": escalated,
        "done": done, "total": total, "unit": ps.get("last_unit"),
        "progress_pct": progress_pct,
        "avg_rate": avg_rate, "recent_rate": recent_rate,
        "tok_in": tok_in, "tok_out": tok_out,
        "loss": last_beat.get("loss"), "eta_s": eta_s,
        "log": piece.get("log"),
        "probe_failed": probe_fail_rounds >= _PROBE_FAIL_ROUNDS_RED,
        "probe_fail_rounds": probe_fail_rounds,
        "refires": ps.get("refires", 0),
    }


def sample_once():
    reg = load_reg()
    hosts = {p["host"] for j in reg["active"] for p in j["pieces"]} | set(DEFAULT_HOSTS)
    live = live_sessions(hosts)
    st = load_state()
    rows, per_job_lines = [], {}
    now_mono, now_wall = time.monotonic(), time.time()
    for job in reg["active"]:
        for idx, piece in enumerate(job["pieces"]):
            sess_set = live.get(piece["host"])
            alive = None if sess_set is None else (piece["session"] in sess_set)
            # 服务分片(工单 13):不走心跳解析,日志走 read_vllm_stats 只取
            # 吞吐行做显示;判定单独由 update_piece_state 里的 probe_port 定。
            if piece.get("kind") == "service":
                beats, vllm_stats = [], read_vllm_stats(piece["log"])
            else:
                beats, vllm_stats = read_beats(piece["log"]), None
            ps = update_piece_state(st, job, idx, piece, beats, alive,
                                    now_mono, vllm_stats=vllm_stats)
            row = build_row(job, idx, piece, ps, now_mono, now_wall)
            rows.append(row)
            per_job_lines.setdefault(job["name"], []).append(dict(row, t=now_wall))

    registered = {}
    for j in reg["active"]:
        for p in j["pieces"]:
            registered.setdefault(p["host"], set()).add(p["session"])
    extras = {}
    for h, sess_set in live.items():
        if sess_set is None:
            continue
        unreg = sorted(sess_set - registered.get(h, set()))
        if unreg:
            extras[h] = unreg

    latest = {"sampled_at": now_wall, "rows": rows, "extras": extras,
              "incidents_tail": read_incidents_tail()}
    for jname, lines in per_job_lines.items():
        append_jsonl(MONITOR_DIR / "history" / f"{jname}.jsonl", lines)
    atomic_write(MONITOR_DIR / "state.json", st)
    atomic_write(MONITOR_DIR / "latest.json", latest)
    maybe_trigger_incidents(rows, st)  # Task 14(工单 12)前先放空函数 pass
    return latest


def _load_latest_from(monitor_dir):
    """网页出口读落盘文件,不碰采样线程的内存(设计 §3)——latest.json
    不在/坏了返回 None,调用方渲染"无采样"占位,不许报错。"""
    p = Path(monitor_dir) / "latest.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def render_html(latest):
    """采样结果(latest.json 的内容,或 None) -> 任务表网页,纯函数不做
    IO。表列:JOB/分片/HOST/GPU/判定/进度/速率/token/ETA/SESSION。
    30 秒 <meta refresh>;过期亮红的阈值 = sample_interval_s * 3,从
    verdicts.DEFAULTS 生成进页面,不另抄一个数(工单 06 验收要求)。"""
    stale_after_s = verdicts.DEFAULTS["sample_interval_s"] * 3

    def esc(x):
        return html.escape("" if x is None else str(x))

    def fmt_rate(r):
        return "-" if r is None else f"{r:.4g}/s"

    def fmt_tok(v):
        return "-" if v is None else str(v)

    def fmt_eta(v):
        if v is None:
            return "-"
        m, s = divmod(max(0, int(v)), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}"

    if latest is None:
        body = "<p>无采样:latest.json 不在或读不了,采样器可能没起。</p>"
        sampled_at_js = "null"
        stamp = "-"
    else:
        sampled_at = latest.get("sampled_at")
        stamp = (time.strftime("%H:%M:%S", time.localtime(sampled_at))
                 if sampled_at else "-")
        sampled_at_js = "null" if sampled_at is None else repr(sampled_at)

        row_lines = []
        for r in latest.get("rows", []):
            pct = ("-" if r.get("progress_pct") is None
                   else f"{r['progress_pct']}%")
            tok = f"{fmt_tok(r.get('tok_in'))}/{fmt_tok(r.get('tok_out'))}"
            row_lines.append(
                "<tr><td>{job}</td><td>{idx}</td><td>{host}</td>"
                "<td>{gpus}</td><td>{verdict}</td><td>{pct}</td>"
                "<td>{rate}</td><td>{tok}</td><td>{eta}</td>"
                "<td>{sess}</td></tr>".format(
                    job=esc(r.get("job")), idx=esc(r.get("idx")),
                    host=esc(r.get("host")), gpus=esc(r.get("gpus")),
                    verdict=esc(r.get("verdict")), pct=esc(pct),
                    rate=fmt_rate(r.get("recent_rate")), tok=esc(tok),
                    eta=fmt_eta(r.get("eta_s")),
                    sess=esc(r.get("session"))))
        rows_body = ("\n".join(row_lines) if row_lines else
                     "<tr><td colspan=10>当前没有登记在跑的任务</td></tr>")

        incident_lines = []
        for inc in latest.get("incidents_tail", []):
            t = inc.get("t")
            t_str = (time.strftime("%H:%M:%S", time.localtime(t))
                     if t else "-")
            incident_lines.append(
                "<li>[{t}] {job}#{idx} {verdict}: {note}</li>".format(
                    t=esc(t_str), job=esc(inc.get("job")),
                    idx=esc(inc.get("idx")), verdict=esc(inc.get("verdict")),
                    note=esc(inc.get("note"))))
        incidents_body = ("\n".join(incident_lines) if incident_lines else
                          "<li>没有事故记录</li>")

        extras_lines = []
        for h_name, sessions in latest.get("extras", {}).items():
            extras_lines.append(
                "<li>{h}: {s}</li>".format(
                    h=esc(h_name), s=esc(", ".join(sessions))))
        extras_body = ("\n".join(extras_lines) if extras_lines else
                        "<li>没有台账外 session</li>")

        body = f"""
<h2>任务表</h2>
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>JOB</th><th>分片</th><th>HOST</th><th>GPU</th><th>判定</th>
<th>进度</th><th>速率</th><th>token</th><th>ETA</th><th>SESSION</th></tr>
{rows_body}
</table>
<h2>事故记录</h2>
<ul>{incidents_body}</ul>
<h2>台账外 session</h2>
<ul>{extras_body}</ul>
"""

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>new1 长程任务监控</title>
<style>
  body {{ font-family: sans-serif; }}
  #banner {{ padding: 6px 10px; margin-bottom: 10px; background: #eee; }}
  #banner.stale {{ background: #f88; color: #300; font-weight: bold; }}
  table {{ border-collapse: collapse; }}
  th, td {{ padding: 4px 8px; }}
</style>
</head>
<body>
<div id="banner">最后采样 {esc(stamp)}</div>
{body}
<script>
(function () {{
  var sampledAt = {sampled_at_js};
  var staleAfterS = {stale_after_s};
  function tick() {{
    var banner = document.getElementById("banner");
    if (sampledAt === null) {{
      banner.classList.add("stale");
      return;
    }}
    var ageS = (Date.now() / 1000) - sampledAt;
    if (ageS > staleAfterS) {{
      banner.classList.add("stale");
    }} else {{
      banner.classList.remove("stale");
    }}
  }}
  tick();
  setInterval(tick, 5000);
}})();
</script>
</body></html>
"""


class _WebHandler(http.server.BaseHTTPRequestHandler):
    """monitor_dir 由 WebServer 用子类动态挂上去(类属性,handler 每次
    请求都是新实例,没法走 __init__ 传参)。"""
    monitor_dir = None

    def log_message(self, fmt, *args):
        pass  # 访问日志没必要污染采样器的 stderr

    def do_GET(self):
        latest = _load_latest_from(self.monitor_dir)
        if self.path == "/json":
            if latest is None:
                self._send(503, b'{"error": "not sampled yet"}',
                            "application/json")
            else:
                body = json.dumps(latest, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json")
            return
        body = render_html(latest).encode("utf-8")
        self._send(200, body, "text/html; charset=utf-8")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WebServer:
    """采样器网页出口(工单 06):独立线程,do_GET 每次现读 monitor_dir/
    latest.json,不碰采样线程的内存——采样那边 ssh 卡住不影响出页
    (设计 §3)。/ 出任务表网页,/json 出 latest.json 原文。"""

    def __init__(self, port, monitor_dir):
        handler = type("_BoundHandler", (_WebHandler,),
                        {"monitor_dir": Path(monitor_dir)})
        self.httpd = http.server.ThreadingHTTPServer(("", port), handler)
        self._thread = None

    @property
    def server_address(self):
        return self.httpd.server_address

    def start(self):
        self._thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="采一轮就退(冒烟用)")
    ap.add_argument("--interval", type=float,
                    default=verdicts.DEFAULTS["sample_interval_s"])
    ap.add_argument("--port", type=int, default=8377,
                    help="网页/json 出口端口(工单 06)")
    a = ap.parse_args()
    web = None
    if not a.once:
        web = WebServer(port=a.port, monitor_dir=MONITOR_DIR)
        web.start()
        print(f"[sampler] web on :{a.port}", file=sys.stderr, flush=True)
    while True:
        t0 = time.monotonic()
        try:
            sample_once()
        except Exception as e:  # 单轮失败不许弄死常驻进程
            print(f"[sampler] round failed: {e}", file=sys.stderr, flush=True)
        if a.once:
            break
        time.sleep(max(1.0, a.interval - (time.monotonic() - t0)))
    if web is not None:
        web.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
