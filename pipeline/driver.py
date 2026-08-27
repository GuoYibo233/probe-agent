#!/usr/bin/env python3
"""流水线驱动器(施工设计稿 §7):一条命令,断点续跑,每敲一次最多推进一步。

它是编排器,不是新的实验代码——采集/标注/训练/评测每一步都转手给现成的入口
(`run.py <task>` / `run.py recipe` / `launch_servers.py` / `launch_clients.sh` /
`launch-probe` / `launch-eval`),自己只做三件事:判断当前哪一步能推进、把门禁
(G1-G22)当场验一遍、把结果写进状态文件。

用法:
  python3 run.py pipeline --config pipeline/configs/np821_gptoss.json
  python3 run.py pipeline --config <同一份配置> --status   # 只读打印,不推进

状态文件: logs/pipeline/<run_family>/state.json(logs/ 在 .gitignore 里,状态
变化不弄脏工作树)。分步日志同目录 <step>.log,子进程的 stdout/stderr 全进去。

退出码(设计稿 §7):
  0  推进了一步 / 已全部完成 / 上一步发的活还没跑完(原样等下次敲)
  3  本次发射了 GPU 任务(等它跑完再敲)
  4  awaiting_decision:有事要人裁决,决定写进批次配置再敲
  1  门禁失败(原因同时落状态文件与 stderr)

发射登记(2026-08-22 评审 C2/C7 的修法):t2_full / e1_tool / e2_call 真的调了
launcher 才在状态文件的 `launched` 里记一条标记。同一批第二次敲,判据没满足
且标记在,驱动器不再重发,返回 0 并让人去 `python3 run.py gpu-jobs` 看——
退出码 3 从此只代表"本次真的发出去了",不会再有"发过了还报已发射"的假账。

步骤表(appworld 批次实例化,一步一个推进函数,转移表就是下面的 STEPS):
  collect   c1_gen c2_servers c3_health c4_smoke c5_clients c6_done
  annotate  a1_stats a2_build a3_gates
  train     t1_smoke t2_full t3_close
  eval      e1_tool e2_call m1_matrix

三条实现纪律(设计稿 §7 末):
  - 探测与外部动作全收在 `Probes` 里,单测换成假函数就能干跑整条状态机;
  - 判据宁可 blocked 也不放行——t1 之后的几步真跑在执行块,代码里 TODO 注明
    还要硬化哪里,但一处也没有"查不到就当过";
  - ssh 探测一律带 `-o BatchMode=yes -o ConnectTimeout=10`(gpu_jobs 先例;
    launch_common.has_session 没带这两个旗标,别照抄它)。
"""

import filecmp
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import git_dirty  # noqa: E402  (launch_cmd.py:40 的先例:复用 run.py)

sys.path.insert(0, str(ROOT / "ops"))
from launch_common import local_host, probe_free  # noqa: E402

PYRUN = [sys.executable, str(ROOT / "run.py")]
LOG_ROOT = ROOT / "logs" / "pipeline"
SERVE_LOG_DIR = ROOT / "envs" / "serve_logs"   # gen_launch 生成的服务发射器写这里
RUNS_DIR = ROOT / "pipeline" / "runs"

# gen_launch.py 的三件生成物(完成判据就是它们在不在)
GEN_FILES = ("launch_servers.py", "launch_clients.sh", "MANIFEST.md")
# build.py 的七件 + param_label.py 的五件 = 逐字节重建对比的对象(设计稿 §9)
BUILD_FILES = ("train.jsonl", "val.jsonl", "test.jsonl", "tool_vocab.json",
               "router_stats.md", "qa_sample.txt", "ANNOTATE_REPORT.md")
PARAM_FILES = ("params/train.jsonl", "params/val.jsonl", "params/test.jsonl",
               "params/PARAM_LABEL_REPORT.md", "params/CHECK_50.md")
# check_callstr.py 的产物只验在不在:它由 check 那一步产出,不参与重建对比
CHECK_FILE = "CALLSTR_CHECK.md"

HEALTH_MARK = "Application startup complete"   # G3 的日志判据
FREE_MB = 100          # G7:显存归零的容差(驱动残留几十 MiB 是常态)
SSH_OPTS = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=10")

# 批次配置里"这次运行是谁"的那几个键。状态文件按它们的指纹认账:指纹变了
# 就是换了一次运行,拒绝往人家的状态上写(照 run.py run_recipe 的 params
# 一致性先例)。weight_mode/max_bounds 故意不算进去——max_bounds 本来就是
# a1_stats 停点裁决之后由人补写进同一份配置的。
IDENT_KEYS = ("run_family", "env", "model_short", "model_full", "data_out",
              "traj_runs", "trajs_per_unit")


# ---------------------------------------------------------------- 探测与外部动作

def ssh_argv(host, cmd):
    """本机走 bash -c,远程走 ssh。BatchMode 让没配免密时当场失败而不是挂在
    密码提示上,ConnectTimeout 让机器掉线时 10 秒返回。"""
    if host == local_host():
        return ["bash", "-c", cmd]
    return ["ssh", "-n", *SSH_OPTS, host, cmd]


def has_session(host, sess):
    """host 上有没有名为 sess 的 tmux session。探不动(ssh 失败)按"没有"报,
    调用方各自决定这算不算门禁失败——c2/c5 拿它决定发不发,c6 拿它区分
    "还在跑"和"全死了",两处都不会因为探不动而误判成完成。"""
    argv = ssh_argv(host, f"tmux has-session -t {shlex.quote(sess)}")
    return subprocess.run(argv, capture_output=True, text=True).returncode == 0


def gpu_used_mb(host, gpus):
    """G7:目标卡上还占着多少显存(MiB)。返回 int;探不动返回 None——
    fail-closed,调用方按"没归零"处理。"""
    cmd = (f"nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits "
           f"-i {shlex.quote(str(gpus))}")
    r = subprocess.run(ssh_argv(host, cmd), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    tot = 0
    for line in r.stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            tot += int(line)
        except ValueError:
            return None
    return tot


def http_get(url, timeout=10):
    """G3 的第二条判据。返回 (ok, 正文或原因)。用 curl 而不是 urllib:
    执行手册与 MANIFEST.md 里写的就是这条 curl,两边保持同一个动作。"""
    r = subprocess.run(["curl", "-s", "-m", str(timeout), url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"curl rc={r.returncode} {(r.stderr or '').strip()[:120]}"
    if not r.stdout.strip():
        return False, "空回应"
    return True, r.stdout.strip()[:200]


def run_cmd(argv, cwd=None, log=None, env=None):
    """跑一条子命令。输出同时进 stdout 和分步日志,返回 (rc, 输出文本)。"""
    argv = [str(a) for a in argv]
    line = shlex.join(argv)
    print("  $ " + line, flush=True)
    r = subprocess.run(argv, cwd=str(cwd or ROOT), capture_output=True,
                       text=True, env=env)
    out = (r.stdout or "") + (r.stderr or "")
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as f:
            f.write(f"# [{time.strftime('%F %T')}] {line}\n{out}"
                    f"# rc={r.returncode}\n")
    if out.strip():
        print(out.rstrip("\n"), flush=True)
    return r.returncode, out


def boundary_counts(cfg):
    """a1_stats 的原料:每个事件未截断的切点数。照 accept_v3diff.py:21-22 的
    先例把 pipeline/annotate 塞进 sys.path 再 import,不复制一份切点逻辑。"""
    d = str(ROOT / "pipeline" / "annotate")
    if d not in sys.path:
        sys.path.insert(0, d)
    from build import collect_events            # noqa: PLC0415
    from rules import boundaries                # noqa: PLC0415
    events = collect_events([Path(r) for r in cfg["traj_runs"]], cfg["env"])
    events = [e for e in events if e["model"] == cfg["model_full"]]
    # max_bounds 开到 10**9 = 不截断:统计要的是"本来有多少切点",
    # 才答得了"64 这个上限砍掉了多少"
    return [len(boundaries(e["think"], max_bounds=10 ** 9)) for e in events]


def ledger_names():
    """台账 active 里的任务名(只读;写台账一律走 CLI)。"""
    p = ROOT / "ops" / "jobs.json"
    if not p.exists():
        return set()
    try:
        reg = json.loads(p.read_text())
    except Exception:
        return set()
    return {j.get("name") for j in reg.get("active", [])}


def record_events():
    """runs.jsonl 里每个 run_id 记过哪些事件({run_id: {"start","finish"}})。"""
    p = ROOT / "ops" / "runs.jsonl"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        rid = ev.get("run_id")
        if rid:
            out.setdefault(rid, set()).add(ev.get("ev"))
    return out


class Probes:
    """探测与外部动作的注入点。缺省是上面那几个真家伙,单测传假的进来就能
    把整条状态机干跑一遍(设计稿 §7:探测函数注入可 mock)。"""

    def __init__(self, **kw):
        self.git_dirty = git_dirty
        self.probe_free = probe_free
        self.has_session = has_session
        self.local_host = local_host
        self.gpu_used_mb = gpu_used_mb
        self.http_get = http_get
        self.run_cmd = run_cmd
        self.boundary_counts = boundary_counts
        self.ledger_names = ledger_names
        self.record_events = record_events
        for k, v in kw.items():
            if not hasattr(self, k):
                raise TypeError(f"Probes 没有 {k} 这个探测点")
            setattr(self, k, v)


# ---------------------------------------------------------------- 配置读取

def load_cfg(path):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise SystemExit(f"批次配置不在: {p}")
    try:
        cfg = json.loads(p.read_text())
    except Exception as e:
        raise SystemExit(f"批次配置读不动 {p}: {type(e).__name__}: {e}")
    for k in ("run_family", "env", "model_short", "model_full", "data_out",
              "traj_runs", "collect"):
        if k not in cfg:
            raise SystemExit(f"批次配置缺字段 {k}: {p}")
    for k in ("manifest", "run_id"):
        if k not in cfg["collect"]:
            raise SystemExit(f"批次配置的 collect 节缺字段 {k}: {p}")
    cfg["_path"] = str(p)
    return cfg


def manifest_path(cfg):
    p = Path(cfg["collect"]["manifest"])
    return p if p.is_absolute() else ROOT / p


def manifest_of(cfg):
    """采集 manifest。读一次缓存在 cfg 里(一次调用只推进一步,不必操心失效)。"""
    if "_manifest" not in cfg:
        p = manifest_path(cfg)
        if not p.exists():
            raise SystemExit(f"采集 manifest 不在: {p}")
        cfg["_manifest"] = json.loads(p.read_text())
    return cfg["_manifest"]


def run_dir(cfg):
    """采集批次目录。manifest 可带 envs_root 覆盖(gen_launch 同款规则,缺省
    envs/);manifest 不在时按缺省拼——c1 会在发射前拦住缺 manifest,别在
    这里抢先炸。"""
    if manifest_path(cfg).exists():
        er = manifest_of(cfg).get("envs_root")
        if er:
            return Path(er) / "runs" / cfg["collect"]["run_id"]
    return ROOT / "envs" / "runs" / cfg["collect"]["run_id"]


def outdir_of(cfg):
    """采集产物目录。名字必须是 <env>_<model_key> 标准名(G5),gen_launch 强制
    改名,这里按同一条规则现拼,不从 manifest 抄。"""
    return run_dir(cfg) / f"{cfg['env']}_{cfg['model_short']}"


def smoke_dir(cfg):
    return run_dir(cfg) / "smoke" / f"{cfg['env']}_{cfg['model_short']}"


def k_of(cfg):
    return int(cfg.get("trajs_per_unit", 1))


def seeds_of(cfg):
    return list(cfg["collect"].get("seeds") or [])


def data_out(cfg):
    return Path(cfg["data_out"])


def data_root(cfg):
    """launch-probe / launch-eval 的 --data-root:数据集版本目录(其下一模型
    一子目录),即 data_out 的父目录。"""
    return data_out(cfg).parent


def unit_list(path):
    """官方题单:一行一个 task_id,文件无末尾换行(G9 的坑),按行 split 去空行。
    与 build.read_unit_list 同一条规则。"""
    return [ln.strip() for ln in Path(path).read_text().split("\n") if ln.strip()]


def split_lists(cfg):
    files = cfg.get("official_split_files") or {}
    return {k: unit_list(v) for k, v in files.items()}


def n_units(cfg):
    return sum(len(v) for v in split_lists(cfg).values())


def train_cfg(cfg):
    return cfg.get("train") or {}


def batches_of(cfg):
    return list((train_cfg(cfg).get("batches") or {}).keys())


def cells_of(cfg):
    return list(train_cfg(cfg).get("cells") or [])


def run_ids_of(cfg):
    """训练/评测的 run_id,四处一致的那个名字:<批次>_<模型>_<格>。"""
    return [f"{b}_{cfg['model_short']}_{c}"
            for b in batches_of(cfg) for c in cells_of(cfg)]


def placement_of(cfg, batch, stage=""):
    """排卡表路径。配置里 train.placement 给的是基名(如 ops/np821_placement.json),
    真表一批一份——照 p1 的命名法(ops/p1b06_placement.json、
    ops/p1b06_eval_tool_placement.json)在同目录按批次名找。找不到就 blocked,
    不猜。stage 为 "" / "eval_tool" / "eval_call"。"""
    base = Path(train_cfg(cfg).get("placement") or "ops/placement.json")
    if not base.is_absolute():
        base = ROOT / base
    tail = f"_{stage}_placement.json" if stage else "_placement.json"
    return base.parent / f"{batch}{tail}"


# ---------------------------------------------------------------- 小工具

def file_contains(path, needle, block=1 << 20):
    """大日志里找一句话。分块流式读,别把几百兆的 vLLM 日志整个吃进内存。"""
    p = Path(path)
    if not p.exists():
        return False
    nb = needle.encode()
    tail = b""
    with open(p, "rb") as f:
        while True:
            buf = f.read(block)
            if not buf:
                return False
            if nb in tail + buf:
                return True
            # 留 len(needle)-1 字节接下一块,跨块边界的那句话才不会漏
            tail = buf[-(len(nb) - 1):] if len(nb) > 1 else b""


def traj_files(d, env):
    return sorted(Path(d).glob(f"{env}_*.jsonl")) if Path(d).is_dir() else []


def _first_last(path, tail_bytes=65536):
    """轨迹文件的首行(meta)与末行(final)。只读头一行 + 末尾 64KB——G6 要
    对 1260 个 NFS 上的文件各看一眼,整份读进来太贵;final 记录里 eval 已经
    截到 600 字,一条记录远不到 64KB。"""
    p = Path(path)
    if not p.is_file():
        return None, None
    with open(p, "rb") as f:
        first = f.readline()
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - tail_bytes))
        tail = f.read()
    lines = [ln for ln in tail.decode("utf-8", "replace").split("\n") if ln.strip()]
    if not lines:
        return None, None
    return first.decode("utf-8", "replace").strip() or None, lines[-1]


def is_final(path):
    """末行是不是 type=final(G4/G6 的逐文件判据)。"""
    _, last = _first_last(path)
    if last is None:
        return False
    try:
        return json.loads(last).get("type") == "final"
    except Exception:
        return False


def meta_seed(path):
    """轨迹 meta 里这条轨迹用的种子(gen_settings.seed);读不出返回 None。"""
    first, _ = _first_last(path)
    if first is None:
        return None
    try:
        return (json.loads(first).get("gen_settings") or {}).get("seed")
    except Exception:
        return None


def final_steps(path):
    """末行 final 记录里的 steps(30 步上限命中题数用得着);读不出返回 None。"""
    _, last = _first_last(path)
    if last is None:
        return None
    try:
        rec = json.loads(last)
        return rec.get("steps") if rec.get("type") == "final" else None
    except Exception:
        return None


def pct(sorted_vals, q):
    """下标式百分位:取第 floor(q*n) 个下标(0 起数),不插值,好对账。

    定义必须与 pipeline/annotate/build.py:468 报告里的 q() 逐字一致——a1_stats
    印进状态文件的 p50/p90/p99 是人裁决 max_bounds 的依据,a2 之后 build.py 又
    把同名数字写进 ANNOTATE_REPORT 存档,两套定义会在 q*n 恰好是整数时差一格
    (2026-08-22 评审 C4)。这里照 build 的下标式改,一批数据只有一个说法。
    """
    n = len(sorted_vals)
    return sorted_vals[min(n - 1, max(0, int(q * n)))]


def dist_of(counts):
    s = sorted(counts)
    return dict(n_events=len(s), min=s[0], p50=pct(s, 0.5), p90=pct(s, 0.9),
                p99=pct(s, 0.99), max=s[-1],
                over_32=sum(1 for x in s if x > 32),
                over_64=sum(1 for x in s if x > 64),
                over_128=sum(1 for x in s if x > 128),
                over_256=sum(1 for x in s if x > 256))


def client_sessions(cfg):
    """launch_clients.sh 会起的 tmux session 名。命名法照 gen_launch.py 的
    `tm "{prefix}_$1_s$7"`,prefix 缺省由 run_id 前两段拼出。"""
    mf = manifest_of(cfg)
    prefix = mf.get("client_session_prefix")
    if not prefix:
        parts = mf["run_id"].split("_")
        tail = "".join(parts[:2]) if len(parts) >= 2 else mf["run_id"]
        prefix = f"new1_{tail}"
    out = []
    for c in mf["clients"]:
        for sid in range(c["num_shards"]):
            out.append(f"{prefix}_{c['tag']}_s{sid}")
    return out


def client_log(cfg, sess):
    return run_dir(cfg) / "logs" / f"{sess}.log"


def srv_job_name(cfg, i):
    """服务分片在台账里的任务名。照 p1 的先例一实例一条(p1_srv_a/p1_srv_b)。"""
    return f"{cfg['collect']['run_id']}_srv_{chr(ord('a') + i)}"


def step_log(cfg, name):
    return LOG_ROOT / cfg["run_family"] / f"{name}.log"


def head_lines(lines, n=8):
    body = "\n".join("  " + x for x in lines[:n])
    return body + (f"\n  ...共 {len(lines)} 行" if len(lines) > n else "")


# ---------------------------------------------------------------- 事件与状态

def _ev(status, event, detail="", decision=None, advance=False):
    return dict(status=status, event=event, detail=detail,
                decision_needed=decision, advance=advance)


def advanced(event, detail=""):
    """这一步做完了,指针往前挪一格。"""
    return _ev("ready", event, detail, advance=True), 0


def launched(event, detail="", advance=True):
    """本次发射了 GPU 任务,等它跑完再敲。"""
    return _ev("launched", event, detail, advance=advance), 3


def blocked(event, detail):
    """门禁没过。原因落状态文件 + stderr,指针不动。"""
    return _ev("blocked", event, detail), 1


def waiting(event, detail):
    """上一步发的活还在跑,不是失败也不是完成:原样等下次敲。"""
    return _ev("ready", event, detail), 0


def decide(event, detail, question):
    """停点:有事要人裁决,决定写进批次配置再敲。"""
    return _ev("awaiting_decision", event, detail, decision=question), 4


def ident_of(cfg):
    ident = {k: cfg.get(k) for k in IDENT_KEYS}
    ident["collect_run_id"] = cfg["collect"]["run_id"]
    blob = json.dumps(ident, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def fresh_state(cfg):
    return dict(config=cfg["_path"], run_family=cfg["run_family"],
                ident=ident_of(cfg), stage=STEPS[0]["stage"],
                step=STEPS[0]["name"], status="ready", reason=None,
                decision_needed=None, launched={}, history=[])


def state_path(cfg):
    return LOG_ROOT / cfg["run_family"] / "state.json"


def load_state(cfg):
    """读状态。读不动 / 键不全 / 步骤名不认识 / 批次身份对不上,一律拒绝往上写
    ——照 run.py run_recipe 的 params 一致性先例:宁可让人来看一眼,也不许把
    另一次运行的状态覆盖掉。"""
    p = state_path(cfg)
    if not p.exists():
        return fresh_state(cfg)
    try:
        st = json.loads(p.read_text())
    except Exception as e:
        raise SystemExit(f"状态文件读不动 {p}: {type(e).__name__}: {e};"
                         "人工确认它的来历后删掉再敲(驱动器不覆盖看不懂的状态)")
    if not isinstance(st, dict):
        raise SystemExit(f"状态文件不是一个对象: {p};人工确认后删掉再敲")
    miss = [k for k in ("run_family", "ident", "step", "status") if k not in st]
    if miss:
        raise SystemExit(f"状态文件缺字段 {miss}: {p};人工确认后删掉再敲")
    if st["step"] != "done" and st["step"] not in STEP_NAMES:
        raise SystemExit(f"状态文件里的步骤名不认识: {st['step']}({p});"
                         "人工确认后删掉再敲")
    if st["ident"] != ident_of(cfg) or st["run_family"] != cfg["run_family"]:
        raise SystemExit(
            f"{p} 记的是另一组批次参数的运行(ident={st['ident']},"
            f"本次 ident={ident_of(cfg)}),拒绝覆盖;"
            f"换个 run_family,或把配置对齐回原来那组")
    st.setdefault("history", [])
    st.setdefault("reason", None)
    st.setdefault("decision_needed", None)
    # 发射标记跟着状态文件走(旧状态没有这个键 -> 补一个空的,老账当没发过)
    if not isinstance(st.get("launched"), dict):
        st["launched"] = {}
    st["config"] = cfg["_path"]
    return st


def save_state(cfg, st):
    """原子写:tmp + os.replace,照 run.py save_state。"""
    d = state_path(cfg).parent
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    os.replace(tmp, d / "state.json")


def apply_event(st, step, event):
    """把一次推进的结果写进状态:状态字段 + 一条 history。advance 才挪指针,
    挪到底就是 done。"""
    st["status"] = event["status"]
    st["reason"] = event["detail"] or None
    st["decision_needed"] = event["decision_needed"]
    st["history"].append(dict(t=time.strftime("%F %T"), step=step["name"],
                              event=event["event"], detail=event["detail"]))
    if event["advance"]:
        i = STEP_NAMES.index(step["name"])
        if i + 1 < len(STEPS):
            st["step"] = STEPS[i + 1]["name"]
            st["stage"] = STEPS[i + 1]["stage"]
        else:
            st["step"] = "done"
            st["status"] = "done"
    return st


# --------------------------------------------------- 发射标记(评审 C2/C7 的修法)

def launch_key(step_name, batch):
    """发射标记的键。一步一批一条,不同批次 / 不同步骤不会串。"""
    return f"{step_name}:{batch}"


def launch_marker(state, key):
    d = state.get("launched")
    return d.get(key) if isinstance(d, dict) else None


def mark_launched(state, key, what=""):
    """驱动器真的调了 launcher 才记这一条(rc=0 之后)。"""
    if not isinstance(state.get("launched"), dict):
        state["launched"] = {}
    state["launched"][key] = {"t": time.strftime("%F %T"), "what": what}
    return state["launched"][key]


def already_launched(what, key, mark, extra=""):
    """判据没满足但这一批的标记在:不重发,原样等(退 0)。

    绝不在这里报 launched/退 3——launcher 对已在跑的 session 只打印 SKIP 也退 0,
    拿 rc 当"本次发射了"会写出假发射记录;而已经跑完的那一格 session 早没了,
    盲发还会给它补一条假 RUNMETA、把 run_id 重新塞回台账 active(评审 C2/C7)。
    """
    return waiting(f"{what}早先已发射过,本次不重发",
                   f"标记 {key} 记的发射时间是 {mark.get('t')}"
                   + (f"({mark.get('what')})" if mark.get("what") else "")
                   + ";判据还没满足,可能还在跑,也可能中途死了。看它到哪了:\n"
                     "  python3 run.py gpu-jobs\n"
                     "  python3 run.py gpu-jobs watch\n"
                   + (extra + "\n" if extra else "")
                   + f"确认那批既没在跑也没跑完(比如崩了),把状态文件 launched "
                     f"下的 {key!r} 删掉再敲,驱动器才会重发")


# ---------------------------------------------------------------- 门禁小件

def gate_clean_tree(pr, what):
    """G1:发射前工作树必须干净。返回 None 表示过,否则返回 blocked 事件。
    记录里存的 HEAD 只有工作树干净时才追得回真实代码(CLAUDE.md 铁律),
    所以这里没有 --allow-dirty 逃生口:驱动器是编排器,commit 是人的活。"""
    lines = pr.git_dirty()
    if lines is None:
        return blocked("G1 工作树探不动",
                       f"git status 失败,按脏树处理,拒绝{what};"
                       "确认 git 环境后先 commit 再敲")
    if lines:
        return blocked("G1 工作树脏",
                       f"{len(lines)} 行没提交,拒绝{what}——"
                       f"发射前先 commit(CLAUDE.md 铁律):\n{head_lines(lines)}")
    return None


def manifest_sha1(cfg):
    """采集 manifest 文件字节的 sha1。文件不在返回 None。"""
    p = manifest_path(cfg)
    if not p.is_file():
        return None
    return hashlib.sha1(p.read_bytes()).hexdigest()


def gate_manifest_unchanged(cfg, state, what):
    """C9:生成物是按哪一份 manifest 生成的,得对得上。

    c1_gen 生成(或认领)三件发射物时把当时那份 manifest 的 sha1 记进状态;
    真正去执行那三件东西的 c2/c5 再算一遍比对。人改了 manifest 的卡号或
    session 名却忘了 `gen-launch --force` 重生成时,这里当场 blocked——
    否则 c2 会拿新卡号过 G2、却去跑写着旧卡号的 launch_servers.py,把 vLLM
    起在旧卡旧 session 上,c3 再永远等一个不会出现的日志。

    返回 None 表示过;老状态里没记过 sha1 的,补记一条再放行(不拿缺记当失败)。
    """
    cur = manifest_sha1(cfg)
    if cur is None:
        return blocked("采集 manifest 不在", str(manifest_path(cfg)))
    old = state.get("manifest_sha1")
    if not old:
        state["manifest_sha1"] = cur
        return None
    if old != cur:
        return blocked(
            "manifest 与生成发射物时的那份对不上",
            f"{manifest_path(cfg)} 在 c1_gen 生成三件发射物之后改过"
            f"(记的 sha1 {old[:12]},现在是 {cur[:12]});{run_dir(cfg)} 下的"
            f"launch_servers.py / launch_clients.sh 里的卡号、session 名、端口"
            f"还是旧的,直接{what}会跑错卡。先重新生成:\n"
            f"  python3 run.py gen-launch --config {manifest_path(cfg)} --force\n"
            "重生成前顺手再核一遍 servers[].gpu 是不是真空着、session 名有没有"
            "跟着改;生成完把状态文件 logs/pipeline/"
            f"{cfg['run_family']}/state.json 里的 manifest_sha1 删掉(或改成新值)"
            "再敲,驱动器才会认这份新的")
    return None


def smoke_traj_check(d, k, seeds, env):
    """G4 的判据:K 个文件、每个末行 final、每个 meta 的种子与种子表逐位对上。
    返回 (ok, 说清哪条不过的文本)。"""
    if seeds and len(seeds) < k:
        # 种子表比 K 短:照直报判据不过,别让 seeds[i] 抛 IndexError 把
        # 本来准备好的 blocked 变成一份 traceback(评审 C10)
        return False, (f"种子表只有 {len(seeds)} 个({seeds}),按每题 {k} 条"
                       f"要 {k} 个,逐位对不了")
    files = traj_files(d, env)
    if len(files) != k:
        return False, (f"{d} 下有 {len(files)} 个轨迹文件,按每题 {k} 条应该是 "
                       f"{k} 个:{[f.name for f in files]}")
    probs = []
    for i in range(k):
        if k > 1:
            hit = [f for f in files if f.stem.endswith(f"_r{i}")]
            if len(hit) != 1:
                probs.append(f"第 {i} 条轨迹(文件名 _r{i} 结尾)找到 {len(hit)} 个")
                continue
            f = hit[0]
        else:
            f = files[0]
        if not is_final(f):
            probs.append(f"{f.name} 末行不是 type=final")
        if seeds:
            got = meta_seed(f)
            if got != seeds[i]:
                probs.append(f"{f.name} 的 gen_settings.seed={got},"
                             f"种子表第 {i} 位是 {seeds[i]}")
    return (not probs), "\n".join(probs)


def annotate_artifacts(cfg):
    """标注段该有的产物。前 12 件是 build + param_label 造的(逐字节重建对比
    的对象),第 13 件 CALLSTR_CHECK.md 由门禁脚本产出,只验在不在。"""
    return list(BUILD_FILES) + list(PARAM_FILES) + [CHECK_FILE]


def missing_artifacts(cfg):
    out = data_out(cfg)
    return [n for n in annotate_artifacts(cfg) if not (out / n).is_file()]


def train_log_records(run_out):
    p = Path(run_out) / "train_log.jsonl"
    if not p.is_file():
        return []
    recs = []
    for line in p.read_text().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:
            continue
    return recs


def smoke_train_check(run_out, cell):
    """G14 的机器可查的那半:smoke 真跑完了 + ctool 的 ALIGN_CHECK PASS。

    判据 = train_log.jsonl 里有 event=start、有 event=done,且 best/ 在;
    ctool 另加 ALIGN_CHECK.json 的 PASS。缺 done 或缺 best/ 一律不过——
    "跑完了"这件事不许含糊过去。

    loss 在降只在有两条以上 event=step 记录时才判:三个训练脚本每 50 个优化步
    才写一条 step 记录(train_causal_tool.py:422 的 `if gstep % 50 == 0`),而
    --smoke 把训练量钉死在 6~16 个优化步,所以一次跑通的 smoke 通常一条 step
    记录都没有(实测 logs/new1_p1b17_gptoss_ctool_smoke_gc_t108g0.log:
    [[EXITCODE:0]] + event=done,0 条 event=step)。记录不够两条时不拦,只把
    "loss 序列太短,没判"记进这一步的 history detail(评审 C6)。

    返回 (ok, 不过的原因, 过了但要记一笔的备注)。

    TODO(执行块硬化):"在降"现在只比首尾两个 loss 记录,真跑起来要不要看
    斜率、要不要连 ckpt 能不能装回(G15)一起验,等第一批 smoke 的实际
    train_log 出来再定。
    """
    p = Path(run_out)
    if not (p / "train_log.jsonl").is_file():
        return False, f"{p}/train_log.jsonl 不在(smoke 没跑,或产物目录不是这个)", ""
    recs = train_log_records(p)
    if not any(r.get("event") == "start" for r in recs):
        return False, f"{p}/train_log.jsonl 里没有 event=start 记录", ""
    if not any(r.get("event") == "done" for r in recs):
        n_eval = sum(1 for r in recs if r.get("event") == "eval")
        return False, (f"{p}/train_log.jsonl 里没有 event=done"
                       f"(smoke 还没跑完;已有 {n_eval} 条 eval 记录)"), ""
    if not (p / "best").is_dir():
        return False, f"{p}/best 不在(smoke 跑完了却没存出最好的那份)", ""
    note = ""
    losses = [r["loss"] for r in recs
              if r.get("event") == "step" and isinstance(r.get("loss"), (int, float))]
    if len(losses) >= 2:
        if losses[-1] >= losses[0]:
            return False, f"{p} 的 loss 没降:首 {losses[0]} 末 {losses[-1]}", ""
    else:
        note = (f"{p}: train_log.jsonl 只有 {len(losses)} 条 event=step 记录,"
                "loss 序列太短,这一格的降没降没判(smoke 每 50 个优化步才写一条,"
                "跑不到那么多)")
    if cell == "ctool":
        a = p / "ALIGN_CHECK.json"
        if not a.is_file():
            return False, f"{p}/ALIGN_CHECK.json 不在(G13 对齐检查没跑)", ""
        try:
            rep = json.loads(a.read_text())
        except Exception as e:
            return False, f"{a} 读不动: {type(e).__name__}: {e}", ""
        if not rep.get("PASS"):
            return False, (f"{a} 的 PASS={rep.get('PASS')}"
                           f"(hidden maxdiff {rep.get('maxdiff_hidden')})"), ""
    return True, "", note


def full_train_check(run_out):
    """t2 的完成判据:best/ 在 + train_log 跑到 event=done。
    TODO(执行块硬化):"3 epoch 跑满"现在认的是训练脚本自己写的 done 记录;
    真要逐 epoch 核对得先定死 eval 记录的条数口径,等第一批全量跑完再收。"""
    p = Path(run_out)
    if not (p / "best").is_dir():
        return False, f"{p}/best 不在"
    recs = train_log_records(p)
    if not any(r.get("event") == "done" for r in recs):
        n_eval = sum(1 for r in recs if r.get("event") == "eval")
        return False, f"{p}/train_log.jsonl 里没有 event=done(已跑完 {n_eval} 个 epoch)"
    return True, ""


def theta_all_null(ctool_run):
    """双档风险都无解 -> 这一批的 call 档记 N/A(gates.md §3.4 的口径)。
    报告读不动按"不是 N/A"处理,别让读文件失败伪装成合法缺格。"""
    p = Path(ctool_run) / "REPLAY_REPORT.json"
    if not p.is_file():
        return False
    try:
        rep = json.loads(p.read_text())
    except Exception:
        return False
    ch = rep.get("chosen_theta")
    if not isinstance(ch, dict) or not ch:
        return False
    return all(v is None for v in ch.values())


# ---------------------------------------------------------------- collect 六步

def step_c1_gen(cfg, state, pr=None):
    """c1_gen:按 manifest 生成采集批次的三件发射物。已在则视为完成——
    gen-launch 不带 --force 拒绝覆盖,别硬跑。"""
    pr = pr or Probes()
    d = run_dir(cfg)
    have = [n for n in GEN_FILES if (d / n).exists()]
    if len(have) == len(GEN_FILES):
        # 认领已有生成物也要记 sha1:c2/c5 拿它核"生成物是不是按现在这份
        # manifest 生成的"(C9)。认领的这一份只能按"人自己保证对得上"记账,
        # 记下来之后再改 manifest 就拦得住了。
        h = manifest_sha1(cfg)
        if h:
            state["manifest_sha1"] = h
        return advanced("三件生成物已在", str(d))
    if have:
        miss = [n for n in GEN_FILES if n not in have]
        return blocked("生成物只有半套",
                       f"{d} 下已有 {have},缺 {miss};gen-launch 不带 --force 会"
                       "拒绝覆盖——人工确认残件来历后删掉,或自己带 --force 重生成")
    mp = manifest_path(cfg)
    if not mp.exists():
        return blocked("采集 manifest 不在", str(mp))
    rc, _ = pr.run_cmd(PYRUN + ["gen-launch", "--config", str(mp)],
                       cwd=ROOT, log=step_log(cfg, "c1_gen"))
    if rc != 0:
        return blocked("gen-launch 退非零",
                       f"rc={rc};日志 {step_log(cfg, 'c1_gen')}")
    miss = [n for n in GEN_FILES if not (d / n).exists()]
    if miss:
        return blocked("gen-launch 跑完但生成物不齐", f"{d} 下缺 {miss}")
    h = manifest_sha1(cfg)
    if h:
        state["manifest_sha1"] = h
    return advanced("三件生成物已生成", str(d))


def step_c2_servers(cfg, state, pr=None):
    """c2_servers:G1 脏树 -> G2 实探空卡 -> 发射 vLLM(launch_servers.py 幂等)。"""
    pr = pr or Probes()
    bad = gate_manifest_unchanged(cfg, state, "发射采集服务")
    if bad:
        return bad
    mf = manifest_of(cfg)
    servers = mf["servers"]
    bad = gate_clean_tree(pr, "发射采集服务")
    if bad:
        return bad
    # session 存在性必须排在探卡前面:服务起来之后自己就占着卡,再探必然
    # 非 FREE,顺序反了会把"已经发射好的批次"永远挡在 blocked 上
    down = [s for s in servers if not pr.has_session(s["host"], s["session"])]
    if not down:
        return advanced(f"{len(servers)} 个服务 session 全在",
                        ", ".join(s["session"] for s in servers))
    busy = []
    for s in down:
        ok, why = pr.probe_free(s["host"], str(s["gpu"]))
        if not ok:
            busy.append(f"{s['host']}:{s['gpu']} {why}")
    if busy:
        return blocked("G2 目标卡非 FREE",
                       "\n".join(busy) + "\n换卡要改 manifest 的 servers[].gpu "
                       "与 session 名,再带 --force 重跑 gen-launch")
    rc, _ = pr.run_cmd([sys.executable, "launch_servers.py"],
                       cwd=run_dir(cfg), log=step_log(cfg, "c2_servers"))
    if rc != 0:
        return blocked("launch_servers.py 退非零",
                       f"rc={rc};日志 {step_log(cfg, 'c2_servers')}")
    return launched(f"{len(down)} 个 vLLM 实例已发射",
                    "起齐要几分钟,下一步 c3_health 验 G3")


def step_c3_health(cfg, state, pr=None):
    """c3_health:G3 每实例日志见 startup complete 且 /v1/models 有返回。

    日志里还没有那句话时,再探一次 tmux session:session 还在 = 服务在
    warm-up,状态不动等下次敲;session 探不到 = 这个实例起来就没了(vLLM 显存
    不够当场崩最常见),日志里那句话永远不会出现,再等也没用——blocked,把
    session 名和日志路径摆出来让人去读(评审 C8)。has_session 在 ssh 探不动时
    也返回 False,所以措辞写"探不到"而不是断言"崩了"。
    """
    pr = pr or Probes()
    bad, dead = [], []
    for s in manifest_of(cfg)["servers"]:
        log = SERVE_LOG_DIR / f"{s['session']}.log"
        if not file_contains(log, HEALTH_MARK):
            if pr.has_session(s["host"], s["session"]):
                bad.append(f"{s['session']}: 日志里还没有 {HEALTH_MARK!r}"
                           f"(session 还在,按 warm-up 等);日志 {log}")
            else:
                dead.append(f"{s['session']}({s['host']}:{s['port']}): "
                            f"tmux session 探不到,日志里也没有 {HEALTH_MARK!r};"
                            f"日志 {log}")
            continue
        ok, why = pr.http_get(f"http://{s['host']}:{s['port']}/v1/models")
        if not ok:
            bad.append(f"{s['host']}:{s['port']}/v1/models 没回应: {why}")
    if dead:
        return blocked("G3 有实例的 session 探不到",
                       "\n".join(dead + bad)
                       + "\n这几个实例不会自己回来:读日志尾部找原因"
                         "(显存不够、端口占用最常见),处理完在 "
                       + str(run_dir(cfg)) + " 下重发 "
                         "`python3 launch_servers.py`(幂等,只补没起来的)")
    if bad:
        return waiting("G3 服务未齐", "\n".join(bad))
    n = len(manifest_of(cfg)["servers"])
    return advanced(f"G3 {n} 实例全绿", "日志见 startup complete 且 /v1/models 有返回")


def step_c4_smoke(cfg, state, pr=None):
    """c4_smoke:G4 一题采集,判据 = K 个文件 / 末行 final / 种子逐位对上。"""
    pr = pr or Probes()
    mf = manifest_of(cfg)
    d, k, seeds = smoke_dir(cfg), k_of(cfg), seeds_of(cfg)
    # 种子表长度先查:排在 smoke_traj_check 后面的话,短种子表会先让
    # seeds[i] 抛 IndexError,人看到的是 traceback 而不是这条 blocked(评审 C10)
    if k > 1 and len(seeds) != k:
        return blocked("种子表与每题轨迹数对不上",
                       f"trajs_per_unit={k},collect.seeds 有 {len(seeds)} 个"
                       f":{seeds};两边对齐了再敲")
    ok, why = smoke_traj_check(d, k, seeds, cfg["env"])
    if ok:
        return advanced("G4 smoke 判据已满足", str(d))
    s0 = mf["servers"][0]
    preset = mf.get("gptoss_client_preset") or "default"
    cmd = PYRUN + ["collect-aw", "--preset", preset,
                   "--base-url", f"http://{s0['host']}:{s0['port']}/v1",
                   # 端点与模型名照 manifest 的 servers[0] 显式给,压过预设
                   # server 节 —— smoke 打的是这一批真发射的那个服务
                   "--model", cfg["model_full"],
                   "--split", "train", "--n", "1", "--max-steps", "30",
                   "--outdir", str(d), "--exp", f"{cfg['collect']['run_id']}smk"]
    if k > 1:
        cmd += ["--traj-per-task", str(k),
                "--seeds", ",".join(str(x) for x in seeds)]
    rc, _ = pr.run_cmd(cmd, cwd=ROOT, log=step_log(cfg, "c4_smoke"))
    if rc != 0:
        return blocked("smoke 采集退非零",
                       f"rc={rc};日志 {step_log(cfg, 'c4_smoke')}")
    ok, why = smoke_traj_check(d, k, seeds, cfg["env"])
    if not ok:
        return blocked("G4 smoke 判据不过", why)
    return advanced("G4 smoke 过", f"{k} 条轨迹 / 种子 {seeds} 逐条对上")


def step_c5_clients(cfg, state, pr=None):
    """c5_clients:发射客户端分片 + 三处登记(G16 的手搓补录路径)。"""
    pr = pr or Probes()
    bad = gate_manifest_unchanged(cfg, state, "发射采集客户端")
    if bad:
        return bad
    mf = manifest_of(cfg)
    bad = gate_clean_tree(pr, "发射采集客户端")
    if bad:
        return bad
    host = pr.local_host()
    sess = client_sessions(cfg)
    down = [s for s in sess if not pr.has_session(host, s)]
    fired = False
    if down:
        rc, _ = pr.run_cmd(["bash", "launch_clients.sh"], cwd=run_dir(cfg),
                           log=step_log(cfg, "c5_clients"))
        if rc != 0:
            return blocked("launch_clients.sh 退非零",
                           f"rc={rc};日志 {step_log(cfg, 'c5_clients')}")
        fired = True
    ok, why = register_collect(cfg, pr, host, sess)
    if not ok:
        return blocked("三处登记没做全", why)
    if fired:
        return launched(f"{len(down)} 个客户端分片已发射", f"三处登记已补齐;共 {len(sess)} 分片")
    return advanced("客户端分片全在,登记已齐", f"共 {len(sess)} 分片")


def register_collect(cfg, pr, host, sess):
    """G16 三处登记:台账(客户端一条 + 每个服务实例一条)、record start、
    RUNMETA。已经登记过的跳过——重复登记会被 CLI 当场拒(护栏,不是障碍)。"""
    rid = cfg["collect"]["run_id"]
    mf = manifest_of(cfg)
    names = pr.ledger_names()
    log = step_log(cfg, "c5_clients")
    if rid not in names:
        pieces = []
        for s in sess:
            pieces += ["--piece", f"{host}:cpu:{s}:{client_log(cfg, s)}"]
        rc, _ = pr.run_cmd(
            PYRUN + ["gpu-jobs", "register", "--name", rid,
                     "--workdir", str(run_dir(cfg)),
                     "--note", f"{cfg['run_family']} 采集批客户端 {len(sess)} 分片"
                               f"(每题 {k_of(cfg)} 条,种子 {seeds_of(cfg)})"]
            + pieces, cwd=ROOT, log=log)
        if rc != 0:
            return False, f"gpu-jobs register {rid} 退 {rc}"
    for i, s in enumerate(mf["servers"]):
        name = srv_job_name(cfg, i)
        if name in names:
            continue
        rc, _ = pr.run_cmd(
            PYRUN + ["gpu-jobs", "register", "--name", name,
                     "--workdir", str(SERVE_LOG_DIR),
                     "--note", f"{cfg['run_family']} 采集批 {cfg['model_full']} "
                               f"实例(port {s['port']}),采集全程常驻,收官时杀",
                     "--piece",
                     f"{s['host']}:{s['gpu']}:{s['session']}:"
                     f"{SERVE_LOG_DIR / (s['session'] + '.log')}",
                     "--kind", "service", "--port", str(s["port"])],
            cwd=ROOT, log=log)
        if rc != 0:
            return False, f"gpu-jobs register {name} 退 {rc}"
    if "start" not in pr.record_events().get(rid, set()):
        rc, _ = pr.run_cmd(
            PYRUN + ["record", "start", "--run-id", rid,
                     "--track", f"collect_{rid}",
                     "--cmd", f"bash {run_dir(cfg) / 'launch_clients.sh'}",
                     "--host", host, "--gpu", "cpu",
                     "--model", cfg["model_full"],
                     "--data", str(outdir_of(cfg)),
                     "--log", str(run_dir(cfg) / "logs"),
                     "--note", f"{cfg['run_family']} 采集:每题 {k_of(cfg)} 条轨迹"],
            cwd=ROOT, log=log)
        if rc != 0:
            return False, f"record start {rid} 退 {rc}"
    out = outdir_of(cfg)
    out.mkdir(parents=True, exist_ok=True)
    rc, _ = pr.run_cmd(PYRUN + ["runmeta", str(out), "--cmd",
                                f"bash {run_dir(cfg) / 'launch_clients.sh'}",
                                "--kind", "collect"], cwd=ROOT, log=log)
    if rc != 0:
        return False, f"runmeta {out} 退 {rc}"
    return True, ""


def step_c6_done(cfg, state, pr=None):
    """c6_done:G6 完整性 -> G7 显存归零 -> 台账销号 + record 收尾。"""
    pr = pr or Probes()
    k, n = k_of(cfg), n_units(cfg)
    want = n * k
    files = traj_files(outdir_of(cfg), cfg["env"])
    bad_tail = [f.name for f in files if not is_final(f)]
    if len(files) != want or bad_tail:
        detail = (f"G6 未齐: {outdir_of(cfg)} 下 {len(files)} 个轨迹文件,"
                  f"应有 {n} 题 x {k} 条 = {want}")
        if bad_tail:
            detail += f";另有 {len(bad_tail)} 个末行不是 final: {bad_tail[:5]}"
        host = pr.local_host()
        alive = [s for s in client_sessions(cfg) if pr.has_session(host, s)]
        if alive:
            return waiting("采集还在跑", detail + f";{len(alive)} 个客户端 session 还活着")
        return blocked("G6 未齐且客户端全死",
                       detail + ";客户端 session 一个都不在——"
                       "`bash launch_clients.sh` 幂等且带 --resume,重发补缺题")
    capped = [f.name for f in files if (final_steps(f) or 0) >= 30]
    mf = manifest_of(cfg)
    hot = []
    for s in mf["servers"]:
        if pr.has_session(s["host"], s["session"]):
            hot.append(f"{s['session']} 还活着(tmux kill-session -t {s['session']})")
            continue
        used = pr.gpu_used_mb(s["host"], s["gpu"])
        if used is None:
            hot.append(f"{s['host']}:{s['gpu']} 显存探不动,按没归零处理")
        elif used > FREE_MB:
            hot.append(f"{s['host']}:{s['gpu']} 还占着 {used} MiB")
    if hot:
        return blocked("G7 显存未归零",
                       "采集齐了,先把服务 session 杀干净再敲:\n" + head_lines(hot))
    log = step_log(cfg, "c6_done")
    names = pr.ledger_names()
    for name in [cfg["collect"]["run_id"]] + [srv_job_name(cfg, i)
                                              for i in range(len(mf["servers"]))]:
        if name not in names:
            continue
        rc, _ = pr.run_cmd(PYRUN + ["gpu-jobs", "finish", name], cwd=ROOT, log=log)
        if rc != 0:
            return blocked("台账销号失败", f"gpu-jobs finish {name} 退 {rc}")
    rid = cfg["collect"]["run_id"]
    evs = pr.record_events().get(rid, set())
    if "start" in evs and "finish" not in evs:
        # 数字(题数/轨迹数/30 步上限命中)是人补的,驱动器只把状态收掉
        rc, _ = pr.run_cmd(
            PYRUN + ["record", "finish", rid, "--status", "ok",
                     "--metric", f"trajs={len(files)}", "--metric", f"units={n}",
                     "--metric", f"steps30_hit={len(capped)}"],
            cwd=ROOT, log=log)
        if rc != 0:
            return blocked("record 收尾失败", f"record finish {rid} 退 {rc}")
    return advanced("G6/G7 过,台账与记录已收尾",
                    f"{len(files)} 条轨迹({n} 题 x {k});30 步上限命中 {len(capped)} 条")


# ---------------------------------------------------------------- annotate 三步

def step_a1_stats(cfg, state, pr=None):
    """a1_stats:切点统计预跑,然后停在 max_bounds 的裁决上。
    配置里已经写了 max_bounds 就视为已裁决,不再停。"""
    pr = pr or Probes()
    if "max_bounds" in cfg:
        return advanced("max_bounds 已裁决",
                        f"配置里写着 max_bounds={cfg['max_bounds']},跳过停点")
    counts = pr.boundary_counts(cfg)
    if not counts:
        return blocked("扫不出事件",
                       f"traj_runs={cfg['traj_runs']} model={cfg['model_full']} "
                       "一个事件都没扫到,先确认采集产物与模型名")
    st = dist_of(counts)
    state["cutpoint_stats"] = st
    print("切点数分布(未截断):" + json.dumps(st, ensure_ascii=False))
    return decide("切点分布已出", json.dumps(st, ensure_ascii=False),
                  "max_bounds:留 64 还是抬;裁决后把 max_bounds 写进批次配置再敲")


def step_a2_build(cfg, state, pr=None):
    """a2_build:标注链 build -> param_label -> check_callstr(同一份配置)。
    完成判据 = 13 件产物在(前 12 件是 build+param_label 的,第 13 件是门禁产物)
    且 check_callstr 退 0。"""
    pr = pr or Probes()
    miss = missing_artifacts(cfg)
    if not miss:
        return advanced(f"{len(annotate_artifacts(cfg))} 件标注产物已在",
                        str(data_out(cfg)))
    rc, _ = pr.run_cmd(PYRUN + ["recipe", "annotate-chain",
                                "--set", f"config={cfg['_path']}"],
                       cwd=ROOT, log=step_log(cfg, "a2_build"))
    if rc != 0:
        return blocked("标注链退非零",
                       f"rc={rc}(门禁 A/B/D 在 check_callstr 里硬拦);"
                       f"日志 {step_log(cfg, 'a2_build')}")
    miss = missing_artifacts(cfg)
    if miss:
        return blocked("标注链跑完但产物不齐", f"{data_out(cfg)} 下缺 {miss}")
    return advanced("标注链跑完,产物齐", str(data_out(cfg)))


def step_a3_gates(cfg, state, pr=None):
    """a3_gates:G9 题单行数 + G11 抽查件摆出来 + 逐字节重建对比。"""
    pr = pr or Probes()
    lists = split_lists(cfg)
    if not lists:
        return blocked("G9 没有题单可核", "配置缺 official_split_files")
    probs, counts = [], {}
    seen = {}
    for name, ids in lists.items():
        counts[name] = len(ids)
        if not ids:
            probs.append(f"{name} 题单是空的")
        if len(set(ids)) != len(ids):
            probs.append(f"{name} 题单里有重复 task_id")
        for u in ids:
            if u in seen and seen[u] != name:
                probs.append(f"task_id {u} 同时在 {seen[u]} 与 {name} 两堆里")
            seen[u] = name
    if probs:
        return blocked("G9 题单核对不过", "\n".join(probs[:10]))
    out = data_out(cfg)
    for n in ("qa_sample.txt", CHECK_FILE):
        if not (out / n).is_file():
            return blocked("G11 抽查件不在", f"{out / n} 不在")
    ref = out.parent / f"{out.name}_rebuild_ref"
    if ref.exists():
        return blocked("上次重建对比的备份还在",
                       f"{ref} 是上一次逐字节重建对比留下的原始产物备份——"
                       "人工核对它与现产物的差别后再删掉它重来")
    rebuild = list(BUILD_FILES) + list(PARAM_FILES)
    ref.mkdir(parents=True)
    for rel in rebuild:
        dst = ref / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out / rel, dst)
    log = step_log(cfg, "a3_gates")
    for task in ("ann-build", "ann-params"):
        rc, _ = pr.run_cmd(PYRUN + [task, "--config", cfg["_path"]],
                           cwd=ROOT, log=log)
        if rc != 0:
            return blocked("重建跑失败",
                           f"{task} 退 {rc};原始产物的备份在 {ref},"
                           "人工核对后决定要不要拷回")
    diff = [rel for rel in rebuild
            if not filecmp.cmp(ref / rel, out / rel, shallow=False)]
    if diff:
        return blocked("逐字节重建对比不一致",
                       f"{len(diff)} 个文件两次重建不同: {diff};"
                       f"首次产物的备份在 {ref}(先别删,那是证据)")
    shutil.rmtree(ref)
    return advanced("G9/G11/逐字节重建全过",
                    f"题单 {counts};{len(rebuild)} 个文件两次重建逐字节相同")


# ---------------------------------------------------------------- train 三步

def step_t1_smoke(cfg, state, pr=None):
    """t1_smoke:每个训练批次(= 一个底座 x 一种训法)跑一次三格 smoke。

    TODO(执行块硬化):`launch-probe smoke` 现在不接每格的 `--base/--lora/
    --grad-ckpt`,而配置的 train 节也没写 smoke 用哪台机器哪三张卡,所以这一步
    只验判据、不代发——判据不过就 blocked 并把该跑的批次列清楚,不放行。"""
    pr = pr or Probes()
    bad = gate_clean_tree(pr, "发射训练 smoke")
    if bad:
        return bad
    todo, notes = [], []
    for b in batches_of(cfg):
        for c in cells_of(cfg):
            rid = f"{b}_{cfg['model_short']}_{c}"
            d = RUNS_DIR / "smoke" / f"{rid}_smoke"
            ok, why, note = smoke_train_check(d, c)
            if not ok:
                todo.append(f"{rid}: {why}")
            elif note:
                notes.append(note)
    if not todo:
        detail = ("train_log 有 event=start 与 event=done、best/ 在;"
                  "ctool 的 ALIGN_CHECK PASS;"
                  "有两条以上 event=step 记录的格另查了 loss 在降")
        if notes:
            detail += "\n" + head_lines(notes, 12)
        return advanced(f"{len(batches_of(cfg))} 批 x {len(cells_of(cfg))} 格 "
                        "smoke 判据全过", detail)
    return blocked("训练 smoke 还没过",
                   head_lines(todo, 12) + "\n每批一次三格 smoke,一格一张卡:\n"
                   f"  python3 run.py launch-probe smoke --batch <批次> "
                   f"--data-root {data_root(cfg)} --env {cfg['env']} "
                   f"--model {cfg['model_short']} --host <机器> --gpus a,b,c\n"
                   "(1.7B/4B 与 LoRA 档要带的 --base/--lora/--grad-ckpt "
                   "smoke 档还接不了,那几批先手发,判据仍按上面几条查)")


def step_t2_full(cfg, state, pr=None):
    """t2_full:按排卡表逐批发射全量训练。一次调用只发一批,发完退 3;
    十二个 run 全跑完(best/ 在 + train_log 有 done)才进下一步。

    同一批只发一次:发出去之后状态文件里记一条标记,后面再敲这一步,判据没
    满足就返回等待(退 0)而不是再调一次 launch-probe。不这么做的话,训练跑
    几小时期间每敲一次都会重发一遍整张排卡表——已经跑完的那一格 session 早
    没了、卡也空了,launch_probe 会真的重发,撞上训练脚本的 B7 守卫秒退,却先
    给那个已完成的 run 补了一条假 RUNMETA、把 run_id 重新塞回台账 active,
    而 launch_probe 无论发没发都退 0,驱动器还会一直报"已发射"退 3(评审 C2/C7)。
    """
    pr = pr or Probes()
    pend = []
    for rid in run_ids_of(cfg):
        ok, why = full_train_check(RUNS_DIR / rid)
        if not ok:
            pend.append((rid, why))
    if not pend:
        # 判据满足就推进,标记在不在都不管——标记只用来挡重发
        return advanced(f"{len(run_ids_of(cfg))} 个训练 run 全跑完",
                        "best/ 在且 train_log 有 event=done")
    pend_batches = [b for b in batches_of(cfg)
                    if any(rid.startswith(b + "_") for rid, _ in pend)]
    b = pend_batches[0]
    key = launch_key("t2_full", b)
    mark = launch_marker(state, key)
    if mark:
        return already_launched(
            f"{b} 批全量训练", key, mark,
            f"未完成的 run: {[r for r, _ in pend]};"
            f"还没轮到的批次: {[x for x in pend_batches if x != b] or '无'}")
    bad = gate_clean_tree(pr, "发射全量训练")
    if bad:
        return bad
    pl = placement_of(cfg, b)
    if not pl.exists():
        return blocked("排卡表不在",
                       f"{pl} 不在——{b} 这一批的排卡表要先落盘"
                       "(一批一份,照 ops/p1b06_placement.json 的形状)")
    rc, _ = pr.run_cmd(PYRUN + ["launch-probe", "full", "--batch", b,
                                "--data-root", str(data_root(cfg)),
                                "--env", cfg["env"], "--placement", str(pl)],
                       cwd=ROOT, log=step_log(cfg, "t2_full"))
    if rc != 0:
        return blocked("launch-probe 退非零",
                       f"rc={rc};日志 {step_log(cfg, 't2_full')}")
    mark_launched(state, key, f"launch-probe full --batch {b}")
    rest = [x for x in pend_batches if x != b]
    return launched(f"{b} 批已发射",
                    f"还没跑完的批次: {rest or '无'};"
                    f"未完成的 run: {[r for r, _ in pend]}", advance=False)


def step_t3_close(cfg, state, pr=None):
    """t3_close:G16 三处登记齐 + 逐 run record finish(数字由人补)。"""
    pr = pr or Probes()
    names = pr.ledger_names()
    evs = pr.record_events()
    probs, todo = [], []
    for rid in run_ids_of(cfg):
        d = RUNS_DIR / rid
        if not (d / "RUNMETA.json").is_file():
            probs.append(f"{rid}: {d}/RUNMETA.json 不在(G16 第三处)")
        e = evs.get(rid, set())
        if "start" not in e:
            probs.append(f"{rid}: runs.jsonl 里没有 start 事件(G16 第二处)")
        elif "finish" not in e:
            todo.append(rid)
        if rid in names:
            probs.append(f"{rid}: 还在台账 active 里,先 gpu-jobs finish")
    if probs:
        return blocked("G16 登记不齐", head_lines(probs, 12))
    if todo:
        cmds = [f"  python3 run.py record finish {rid} --status ok "
                f"--metric <数字> --conclusion <一句话>" for rid in todo]
        return blocked("还有 run 没记数字",
                       f"{len(todo)} 个 run 只有 start 没有 finish,数字要人补:\n"
                       + head_lines(cmds, 12))
    return advanced(f"{len(run_ids_of(cfg))} 个 run 三处登记齐、数字已记", "")


# ---------------------------------------------------------------- eval 三步

def step_e1_tool(cfg, state, pr=None):
    """e1_tool:各批 ctool 先评(launch-eval 自带依赖锁与登记)。
    完成判据 = 每批的 REPLAY_REPORT.json 在。发射标记同 t2_full(评审 C2/C7):
    发过一次就不重发,判据没满足只等,不报假发射。"""
    pr = pr or Probes()
    pend = [b for b in batches_of(cfg)
            if not (RUNS_DIR / f"{b}_{cfg['model_short']}_ctool"
                    / "REPLAY_REPORT.json").is_file()]
    if not pend:
        return advanced(f"{len(batches_of(cfg))} 批 ctool 报告全在", "")
    b = pend[0]
    key = launch_key("e1_tool", b)
    mark = launch_marker(state, key)
    if mark:
        return already_launched(f"{b} 批 ctool 评测", key, mark,
                                f"还没出报告的批次: {pend or '无'}")
    bad = gate_clean_tree(pr, "发射工具格评测")
    if bad:
        return bad
    pl = placement_of(cfg, b, "eval_tool")
    if not pl.exists():
        return blocked("评测排卡表不在",
                       f"{pl} 不在(照 ops/p1b06_eval_tool_placement.json 的形状)")
    rc, _ = pr.run_cmd(PYRUN + ["launch-eval", "tool", "--batch", b,
                                "--data-root", str(data_root(cfg)),
                                "--env", cfg["env"], "--placement", str(pl)],
                       cwd=ROOT, log=step_log(cfg, "e1_tool"))
    if rc != 0:
        return blocked("launch-eval tool 退非零",
                       f"rc={rc};日志 {step_log(cfg, 'e1_tool')}")
    mark_launched(state, key, f"launch-eval tool --batch {b}")
    return launched(f"{b} 批 ctool 评测已发射", f"还没出报告的批次: {pend[1:] or '无'}",
                    advance=False)


def step_e2_call(cfg, state, pr=None):
    """e2_call:cgen/cparam 评(同批 ctool 报告在才发)。θ 两档皆 null 的批次
    记 N/A 进状态,不当失败——双档退让是既定口径(gates.md §3.4)。
    发射标记同 t2_full(评审 C2/C7):同一批只发一次,发过就只等不重发。"""
    pr = pr or Probes()
    reports = {"cgen": "CALLGEN_REPORT.json", "cparam": "PARAM_REPORT.json"}
    na, pend = [], []
    for b in batches_of(cfg):
        ctool = RUNS_DIR / f"{b}_{cfg['model_short']}_ctool"
        if theta_all_null(ctool):
            na.append(b)
            continue
        for c in ("cgen", "cparam"):
            if c not in cells_of(cfg):
                continue
            if not (RUNS_DIR / f"{b}_{cfg['model_short']}_{c}"
                    / reports[c]).is_file():
                pend.append(b)
                break
    state["theta_na_batches"] = na
    if not pend:
        return advanced("call 档报告全在",
                        f"θ 两档皆 null 记 N/A 的批次: {na or '无'}")
    b = pend[0]
    key = launch_key("e2_call", b)
    mark = launch_marker(state, key)
    if mark:
        return already_launched(f"{b} 批 call 档评测", key, mark,
                                f"还没出报告的批次: {pend or '无'};"
                                f"N/A: {na or '无'}")
    bad = gate_clean_tree(pr, "发射调用格评测")
    if bad:
        return bad
    pl = placement_of(cfg, b, "eval_call")
    if not pl.exists():
        return blocked("评测排卡表不在",
                       f"{pl} 不在(照 ops/p1b06_eval_call_placement.json 的形状)")
    rc, _ = pr.run_cmd(PYRUN + ["launch-eval", "call", "--batch", b,
                                "--data-root", str(data_root(cfg)),
                                "--env", cfg["env"], "--placement", str(pl)],
                       cwd=ROOT, log=step_log(cfg, "e2_call"))
    if rc != 0:
        return blocked("launch-eval call 退非零",
                       f"rc={rc};日志 {step_log(cfg, 'e2_call')}")
    mark_launched(state, key, f"launch-eval call --batch {b}")
    return launched(f"{b} 批 call 档评测已发射",
                    f"还没出报告的批次: {pend[1:] or '无'};N/A: {na or '无'}",
                    advance=False)


def step_m1_matrix(cfg, state, pr=None):
    """m1_matrix:两个风险档各出一份矩阵(一批一份)。产物在即 done。"""
    pr = pr or Probes()
    log = step_log(cfg, "m1_matrix")
    made = []
    for b in batches_of(cfg):
        for risk in ("0.05", "0.1"):
            out = RUNS_DIR / f"MATRIX_{b}_r{risk}.md"
            if out.is_file():
                continue
            rc, _ = pr.run_cmd(PYRUN + ["matrix", "--runs-dir", str(RUNS_DIR),
                                        "--out", str(out), "--prefix", b,
                                        "--risk", risk,
                                        "--models", cfg["model_short"]],
                               cwd=ROOT, log=log)
            if rc != 0:
                return blocked("matrix 退非零", f"{b} 风险 {risk} rc={rc};日志 {log}")
            if not out.is_file():
                return blocked("matrix 跑完但产物不在", str(out))
            made.append(out.name)
    return advanced("两档矩阵已出", f"本次新出 {made or '无(早就在了)'}")


# ---------------------------------------------------------------- 步骤表

STEPS = (
    dict(name="c1_gen", stage="collect", fn=step_c1_gen,
         desc="生成采集批次的三件发射物"),
    dict(name="c2_servers", stage="collect", fn=step_c2_servers,
         desc="G1 脏树 + G2 探卡 + 发射 vLLM 实例"),
    dict(name="c3_health", stage="collect", fn=step_c3_health,
         desc="G3 服务健康"),
    dict(name="c4_smoke", stage="collect", fn=step_c4_smoke,
         desc="G4 一题采集 smoke"),
    dict(name="c5_clients", stage="collect", fn=step_c5_clients,
         desc="发射客户端分片 + G16 三处登记"),
    dict(name="c6_done", stage="collect", fn=step_c6_done,
         desc="G6 完整性 + G7 显存归零 + 销号"),
    dict(name="a1_stats", stage="annotate", fn=step_a1_stats,
         desc="切点分布统计(max_bounds 停点)"),
    dict(name="a2_build", stage="annotate", fn=step_a2_build,
         desc="标注链 build/params/check"),
    dict(name="a3_gates", stage="annotate", fn=step_a3_gates,
         desc="G9 题单 + G11 抽查件 + 逐字节重建对比"),
    dict(name="t1_smoke", stage="train", fn=step_t1_smoke,
         desc="各批三格 smoke"),
    dict(name="t2_full", stage="train", fn=step_t2_full,
         desc="按排卡表发射全量训练"),
    dict(name="t3_close", stage="train", fn=step_t3_close,
         desc="G16 登记核对 + 逐 run 记数字"),
    dict(name="e1_tool", stage="eval", fn=step_e1_tool,
         desc="各批 ctool 评测"),
    dict(name="e2_call", stage="eval", fn=step_e2_call,
         desc="cgen/cparam 评测"),
    dict(name="m1_matrix", stage="eval", fn=step_m1_matrix,
         desc="两个风险档各出一份矩阵"),
)
STEP_NAMES = [s["name"] for s in STEPS]


def step_by_name(name):
    for s in STEPS:
        if s["name"] == name:
            return s
    raise SystemExit(f"不认识的步骤名: {name}")


# ---------------------------------------------------------------- 入口

def print_status(cfg, st):
    print(f"流水线 {st['run_family']}  配置 {st.get('config')}")
    print(f"  当前: {st.get('stage')} / {st['step']}  状态 {st['status']}")
    if st.get("reason"):
        print("  原因: " + str(st["reason"]).replace("\n", "\n        "))
    if st.get("decision_needed"):
        print(f"  待裁决: {st['decision_needed']}")
    if st.get("cutpoint_stats"):
        print("  切点分布: " + json.dumps(st["cutpoint_stats"], ensure_ascii=False))
    if st.get("launched"):
        # 发的活人要能看见:哪一批哪一步已经发出去过,以及发的时间
        print("  发射标记: " + ", ".join(
            f"{k}@{v.get('t')}" for k, v in sorted(st["launched"].items())))
    done = st["step"] == "done"
    idx = len(STEPS) if done else STEP_NAMES.index(st["step"])
    for i, s in enumerate(STEPS):
        mark = "x" if i < idx else (">" if i == idx else " ")
        print(f"  [{mark}] {s['name']:<12} {s['desc']}")
    for h in st.get("history", [])[-5:]:
        print(f"  {h['t']}  {h['step']:<12} {h['event']}")
    print(f"  状态文件: {state_path(cfg)}")
    return 0


def main(argv):
    cfg_path, only_status = None, False
    it = iter(argv)
    for a in it:
        if a == "--config":
            cfg_path = next(it, None)
            if cfg_path is None:
                raise SystemExit("--config 后面要跟一份批次配置 json")
        elif a == "--status":
            only_status = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            raise SystemExit(f"不认识的参数: {a}(只认 --config / --status)")
    if not cfg_path:
        raise SystemExit("要 --config <批次配置 json>(run.py show pipeline 看用法)")
    cfg = load_cfg(cfg_path)
    st = load_state(cfg)
    if only_status:
        return print_status(cfg, st)
    if st["step"] == "done":
        print(f"流水线 {cfg['run_family']} 已全部完成。状态: {state_path(cfg)}")
        return 0
    step = step_by_name(st["step"])
    print(f"[{step['name']}] {step['desc']}")
    event, code = step["fn"](cfg, st)
    apply_event(st, step, event)
    save_state(cfg, st)
    print(f"-> {event['status']}: {event['event']}")
    if event["detail"]:
        out = sys.stderr if code == 1 else sys.stdout
        print(event["detail"], file=out)
    if event["decision_needed"]:
        print(f"待裁决: {event['decision_needed']}")
    nxt = "done" if st["step"] == "done" else st["step"]
    print(f"下一步: {nxt}   状态: {state_path(cfg)}   退出码 {code}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
