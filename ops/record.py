#!/usr/bin/env python3
"""new1 实验记录 CLI（零依赖，标准库）。

三层记录体系的中间层：统计数字。
  方向层  TIMELINE.md   人手写，只增不改（一条 = 一次方向决策）
  数字层  ops/runs.jsonl → RESULTS.md   本脚本维护
  数据层  NFS 上的原始轨迹/权重，不进 git，靠 run_id 目录名 + report.md 追溯

用法:
  record.py start --name NAME --track TRACK [选项]   # 发射后立刻记
  record.py start --run-id ID --track TRACK [选项]
      --cmd "..."          实际执行的命令行
      --host h --gpu 0,1   跑在哪
      --model M --seed N   模型与随机种子
      --param k=v          可重复，实验参数
      --data PATH          原始数据落盘位置
      --note TEXT          一句话说明这次想验证什么
  record.py finish RUN_ID [选项]                     # 收尾时补数字
      --status ok|fail|killed
      --metric k=v         可重复，关键数字
      --data PATH          最终数据位置（覆盖 start 时的）
      --conclusion TEXT    一句话结论
  record.py render      # 重新渲染 RESULTS.md（start/finish 会自动调用）
  record.py list        # 一行一个 run
  record.py show RUN_ID # 单个 run 的全部字段

runs.jsonl 是 append-only 事件流，永不改写既有行——这样 git diff 永远是纯新增，
历史不可能被悄悄篡改。RESULTS.md 是它的渲染产物，可随时重建。
run_id 是贯穿全局的主键：原始数据目录名 / tmux session 名 / 台账 name /
commit message 里都用它，四个地方能互相跳。
"""
import json
import os
import subprocess
import sys
from datetime import datetime

OPS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(OPS)
RUNS_PATH = os.path.join(OPS, "runs.jsonl")
RESULTS_PATH = os.path.join(ROOT, "RESULTS.md")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def git_state():
    """当前代码版本。dirty=True 意味着这条记录的 commit 追不回真实代码。"""
    def g(*a):
        try:
            r = subprocess.run(["git", "-C", ROOT] + list(a),
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""
    return {"commit": g("rev-parse", "--short", "HEAD"),
            "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(g("status", "--porcelain"))}


def append(ev):
    with open(RUNS_PATH, "a") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def load():
    """把事件流折叠成 {run_id: 合并记录}，保持首次出现的顺序。"""
    runs = {}
    if not os.path.exists(RUNS_PATH):
        return runs
    with open(RUNS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            rid = ev["run_id"]
            r = runs.setdefault(rid, {"run_id": rid, "status": "running",
                                      "metrics": {}, "params": {}})
            kind = ev.pop("ev")
            if kind == "start":
                r["started_at"] = ev.get("t")
                for k in ("track", "commit", "branch", "dirty", "cmd", "host",
                          "gpu", "model", "seed", "data", "note"):
                    if ev.get(k) not in (None, ""):
                        r[k] = ev[k]
                r["params"].update(ev.get("params") or {})
            elif kind == "finish":
                r["finished_at"] = ev.get("t")
                r["status"] = ev.get("status", "ok")
                r["metrics"].update(ev.get("metrics") or {})
                for k in ("data", "conclusion"):
                    if ev.get(k):
                        r[k] = ev[k]
    return runs


def kv(pairs):
    out = {}
    for p in pairs:
        if "=" not in p:
            sys.exit(f"参数要写成 k=v，收到: {p}")
        k, v = p.split("=", 1)
        try:
            v = float(v) if ("." in v or "e" in v.lower()) else int(v)
        except ValueError:
            pass
        out[k] = v
    return out


def fmt_metrics(m):
    if not m:
        return "-"
    return " ".join(f"{k}={v}" for k, v in m.items())


def render():
    runs = load()
    lines = [
        "# RESULTS — 实验统计数字总表",
        "",
        "> 本文件由 `python ops/record.py render` 自动生成，**不要手改**。",
        "> 数据源是 append-only 的 `ops/runs.jsonl`；改数字请补一条 finish 事件。",
        "> 方向决策的来龙去脉看 [TIMELINE.md](TIMELINE.md)，原始数据不在 git 里。",
        "",
    ]
    if not runs:
        lines += ["（还没有记录。发射实验时走 gpu-run skill 会自动写入。）", ""]
    else:
        lines += [
            "| run_id | 日期 | 方向 | commit | 模型 | 状态 | 关键数字 | 结论 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in reversed(list(runs.values())):
            c = r.get("commit", "-")
            if r.get("dirty"):
                c += "+dirty"
            lines.append("| `{}` | {} | {} | `{}` | {} | {} | {} | {} |".format(
                r["run_id"], r.get("started_at", "-"), r.get("track", "-"), c,
                r.get("model", "-"), r.get("status", "-"),
                fmt_metrics(r.get("metrics")),
                (r.get("conclusion") or "-").replace("|", "/"),
            ))
        lines += ["", "## 逐条详情", ""]
        for r in reversed(list(runs.values())):
            lines.append(f"### `{r['run_id']}`")
            lines.append("")
            if r.get("note"):
                lines.append(f"- **想验证什么**：{r['note']}")
            if r.get("conclusion"):
                lines.append(f"- **结论**：{r['conclusion']}")
            lines.append("- **方向**：{} ｜ **状态**：{} ｜ **起止**：{} → {}".format(
                r.get("track", "-"), r.get("status", "-"),
                r.get("started_at", "-"), r.get("finished_at", "未收尾")))
            lines.append("- **代码**：`{}`{} (分支 {})".format(
                r.get("commit", "-"),
                "  ⚠️ 发射时工作树是脏的，这个 commit 追不回真实代码"
                if r.get("dirty") else "",
                r.get("branch", "-")))
            if r.get("host"):
                lines.append("- **机器**：{} GPU {}".format(
                    r["host"], r.get("gpu", "-")))
            if r.get("model") or r.get("seed") is not None:
                lines.append("- **模型 / 种子**：{} / {}".format(
                    r.get("model", "-"), r.get("seed", "-")))
            if r.get("params"):
                lines.append("- **参数**：{}".format(fmt_metrics(r["params"])))
            if r.get("metrics"):
                lines.append("- **数字**：{}".format(fmt_metrics(r["metrics"])))
            if r.get("data"):
                lines.append(f"- **原始数据**：`{r['data']}`（不在 git 里）")
            if r.get("cmd"):
                lines.append(f"- **命令**：`{r['cmd']}`")
            lines.append("")
    with open(RESULTS_PATH, "w") as f:
        f.write("\n".join(lines))
    return len(runs)


def cmd_start(argv):
    ev = {"ev": "start", "t": now(), "params": {}}
    name = None
    params = []
    it = iter(argv)
    for a in it:
        if a == "--run-id":
            ev["run_id"] = next(it)
        elif a == "--name":
            name = next(it)
        elif a in ("--track", "--cmd", "--host", "--gpu", "--model",
                   "--data", "--note"):
            ev[a[2:]] = next(it)
        elif a == "--seed":
            ev["seed"] = int(next(it))
        elif a == "--param":
            params.append(next(it))
        else:
            sys.exit(f"未知参数 {a}\n\n{__doc__}")
    if not ev.get("run_id"):
        if not name:
            sys.exit("start 需要 --run-id 或 --name")
        ev["run_id"] = datetime.now().strftime("%Y%m%d_%H%M_") + name
    if not ev.get("track"):
        sys.exit("start 需要 --track（这个实验服务于哪个方向，跟 TIMELINE.md 对齐）")
    if ev["run_id"] in load():
        sys.exit(f"run_id {ev['run_id']} 已存在，换一个")
    ev["params"] = kv(params)
    ev.update(git_state())
    append(ev)
    render()
    print(f"已记录 start: {ev['run_id']}  (commit {ev['commit']}"
          f"{'，⚠️ 工作树是脏的：先 commit 再发射，否则追溯断链' if ev['dirty'] else ''})")
    print(f"收尾时: python ops/record.py finish {ev['run_id']} "
          f"--metric k=v --conclusion \"...\"")


def cmd_finish(argv):
    if not argv or argv[0].startswith("--"):
        sys.exit("finish 需要 RUN_ID")
    ev = {"ev": "finish", "t": now(), "run_id": argv[0], "status": "ok"}
    metrics = []
    it = iter(argv[1:])
    for a in it:
        if a in ("--status", "--data", "--conclusion"):
            ev[a[2:]] = next(it)
        elif a == "--metric":
            metrics.append(next(it))
        else:
            sys.exit(f"未知参数 {a}\n\n{__doc__}")
    runs = load()
    if ev["run_id"] not in runs:
        sys.exit(f"没有 run_id {ev['run_id']}——先 record.py start，或查 record.py list")
    ev["metrics"] = kv(metrics)
    append(ev)
    render()
    print(f"已记录 finish: {ev['run_id']}  {fmt_metrics(ev['metrics'])}")
    print("数字改变了 WORKPLAN 里的判断？追加一条 TIMELINE.md 并 commit。")


def cmd_list():
    runs = load()
    if not runs:
        print("还没有记录。")
        return
    for r in runs.values():
        print("{:<28} {:<12} {:<8} {}".format(
            r["run_id"], r.get("track", "-")[:12], r.get("status", "-"),
            fmt_metrics(r.get("metrics"))))


def cmd_show(rid):
    runs = load()
    if rid not in runs:
        sys.exit(f"没有 run_id {rid}")
    print(json.dumps(runs[rid], indent=2, ensure_ascii=False))


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "start":
        cmd_start(args[1:])
    elif args[0] == "finish":
        cmd_finish(args[1:])
    elif args[0] == "render":
        print(f"RESULTS.md 已重建（{render()} 条记录）")
    elif args[0] == "list":
        cmd_list()
    elif args[0] == "show":
        cmd_show(args[1])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
