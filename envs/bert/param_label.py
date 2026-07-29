"""T7①抽取头标签:每事件每参数,在每个样本 text 里定位参数值子串(纯 CPU)。

- 事件重抽:复用 build_dataset 的正则/过滤/事件 key,但**保参数名**
  (kwarg 取名字,位置参数取 pos0/pos1/...;tales 参数名固定 arg);
  值的归一化与 build_dataset 完全一致(strip 后 strip("\\"'"));空值跳过
- 参数 key = f"{tool}.{参数名}"
- 定位:在样本自己的 text 里取**最靠末尾一次**出现(str.rfind),记 [start,end);
  找不到记 found=false(=抽不到,抽取头要学会输出它)
- 产物: v3_params/<env>/{train,calA,calB,test}.jsonl(不重存 text,按
  event+sent_idx 回 v3 连接)+ PARAM_LABEL_REPORT.md + CHECK_50.md

用法: python3 param_label.py [--runs DIR ...] [--data DIR] [--out DIR]
"""

import argparse
import glob
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path("/home/y-guo/reproduce/new1/envs")
sys.path.insert(0, str(BASE / "collect"))
from build_dataset import (AW_CALL, BFCL_CALL, MIN_THINK,  # noqa: E402
                           MODEL_OF)

SEED = 20260729
ENVS = ("appworld", "tales", "bfcl")
SPLITS = ("train", "calA", "calB", "test")
CTX = 80          # CHECK_50 上下文字符数
KEEP_OK = 60      # 每环境蓄水池:已定位样例
KEEP_NG = 20      # 每环境蓄水池:抽不到样例


# ---------- 保名版参数解析(与 build_dataset.split_args 同切法) ----------

def split_args_named(argstr):
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
    out, pos = [], 0
    for v in vals:
        m = re.match(r"(\w+)\s*=\s*(.+)", v, re.S)
        if m:
            out.append((m.group(1), m.group(2).strip().strip("\"'")))
        else:
            out.append((f"pos{pos}", v.strip().strip("\"'")))
            pos += 1
    return out


def first_call_named(code, name_re):
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
                return split_args_named(code[i + 1: j])
    return []


def mkparams(tool, named):
    """(名,值) -> [(key,value)],空值跳过,同 key 保留首次。"""
    out, seen = [], set()
    for name, val in named:
        if not val:
            continue
        k = f"{tool}.{name}"
        if k in seen:
            continue
        seen.add(k)
        out.append((k, val))
    return out


# ---------- 三环境:轨迹 -> (事件 key, 工具, 参数表) ----------

def jsonl_events(runs, pattern, env):
    for f in sorted(glob.glob(str(runs / pattern))):
        batch = Path(f).parent.name
        if MODEL_OF.get(batch.rsplit("_", 1)[1]) is None:
            continue
        recs = [json.loads(l) for l in open(f)]
        gens = {r["step"]: r for r in recs if r["type"] == "gen"}
        envs = {r["step"]: r for r in recs if r["type"] == "env"}
        traj = f"{batch}/{Path(f).stem}"
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
                    tool = f"apis.{m.group(1)}.{m.group(2)}"
                    yield (f"{traj}|s{st}", tool,
                           mkparams(tool,
                                    first_call_named(action, AW_CALL) or []))
            else:
                parts = action.split()
                verb = parts[0].lower() if parts else ""
                if verb and len(think) >= MIN_THINK:
                    rest = " ".join(parts[1:])
                    yield (f"{traj}|s{st}", verb,
                           mkparams(verb, [("arg", rest)] if rest else []))


def bfcl_events(runs):
    for d in sorted(runs.glob("bfcl_*")):
        if MODEL_OF.get(d.name.rsplit("_", 1)[1]) is None:
            continue
        seen = set()
        # sorted:build_dataset 此处用裸 glob,readdir 序不稳,重跑事件数会飘
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
                k = 0
                for role, c, rc in msgs:
                    if role == "assistant" and rc.strip() and c.strip():
                        k += 1
                        m = BFCL_CALL.search(c)
                        if m and len(rc.strip()) >= MIN_THINK:
                            tool = m.group(1)
                            yield (f"{d.name}/{entry['id']}|s{k}", tool,
                                   mkparams(tool,
                                            first_call_named(c, BFCL_CALL)
                                            or []))


def collect_events(runs_dirs):
    by_env = {e: {} for e in ENVS}
    dup = Counter()
    for runs in runs_dirs:
        streams = [
            ("appworld", jsonl_events(runs, "appworld_*/appworld_*.jsonl",
                                      "appworld")),
            ("tales", jsonl_events(runs, "tales_*/tales_*.jsonl", "tales")),
            ("bfcl", bfcl_events(runs)),
        ]
        for env, it in streams:
            for key, tool, params in it:
                if key in by_env[env]:
                    dup[env] += 1
                    continue
                by_env[env][key] = (tool, params)
    return by_env, dup


# ---------- 蓄水池抽样(定长,种子固定) ----------

class Pool:
    def __init__(self, cap, rng):
        self.cap, self.rng, self.n, self.buf = cap, rng, 0, []

    def offer(self, item):
        self.n += 1
        if len(self.buf) < self.cap:
            self.buf.append(item)
        else:
            j = self.rng.randrange(self.n)
            if j < self.cap:
                self.buf[j] = item


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", action="append", default=None)
    ap.add_argument("--data", default=str(BASE / "bert_data" / "v3"))
    ap.add_argument("--out", default=str(BASE / "bert_data" / "v3_params"))
    args = ap.parse_args()
    runs_dirs = [Path(r) for r in (args.runs or
                                   [BASE / "runs" / "full_v1",
                                    BASE / "runs" / "full_v2_topup"])]
    data_root, out_root = Path(args.data), Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    by_env, dup = collect_events(runs_dirs)
    for env in ENVS:
        print(f"re-extracted {env}: {len(by_env[env])} events "
              f"(dup skipped {dup[env]})", flush=True)

    report = [f"# v3_params 参数定位报告(param_label.py)\n",
              f"- SEED={SEED} runs={[str(r) for r in runs_dirs]}",
              f"- data={data_root} out={out_root}",
              "- 定位口径:样本自身 text 内 str.rfind(最靠末尾一次出现);"
              "找不到 = 抽不到(found=false)",
              "- 参数 key = 工具名.参数名(kwarg 取名,位置参数 pos0/1/...,"
              "tales 固定 arg);空值跳过\n"]
    checks = {}

    for env in ENVS:
        evmap = by_env[env]
        out = out_root / env
        out.mkdir(parents=True, exist_ok=True)
        pool_ok, pool_ng = Pool(KEEP_OK, rng), Pool(KEEP_NG, rng)

        v3_events = set()
        miss_ev = Counter()          # v3 有、重抽无
        n_rows = Counter()
        n_par = Counter()
        n_found = Counter()
        dep_tot = [0] * 10
        dep_hit = [0] * 10
        last_tot = last_hit = 0
        n_assert = 0
        n_short = 0      # 已定位且值 ≤3 字符(rfind 易撞巧合子串)
        n_inthink = 0    # 已定位且落在 [THINKING] 段内(非抄题干/历史)
        noparam_ev = set()

        for sp in SPLITS:
            with open(out / f"{sp}.jsonl", "w") as fo:
                for line in open(data_root / env / f"{sp}.jsonl"):
                    r = json.loads(line)
                    ev = r["event"]
                    v3_events.add(ev)
                    hit = evmap.get(ev)
                    if hit is None:
                        miss_ev[sp] += 1
                        continue
                    tool, params = hit
                    assert tool == r["label"], (ev, tool, r["label"])
                    if not params:
                        noparam_ev.add(ev)
                    text = r["text"]
                    th0 = text.rfind("\n[THINKING]\n") + 12
                    b = min(9, int(r["depth"] * 10))
                    last = r["sent_idx"] == r["n_sents"] - 1
                    plist = []
                    for k, v in params:
                        s = text.rfind(v)
                        if s < 0:
                            plist.append(dict(key=k, value=v, start=-1,
                                              end=-1, found=False))
                            pool_ng.offer((env, k, v, text[-120:]))
                        else:
                            e = s + len(v)
                            assert text[s:e] == v, (ev, k)
                            n_assert += 1
                            plist.append(dict(key=k, value=v, start=s,
                                              end=e, found=True))
                            n_found[sp] += 1
                            dep_hit[b] += 1
                            last_hit += last
                            n_short += len(v) <= 3
                            n_inthink += s >= th0
                            pool_ok.offer((env, k, v, s, e, text))
                        n_par[sp] += 1
                        dep_tot[b] += 1
                        last_tot += last
                    n_rows[sp] += 1
                    fo.write(json.dumps(
                        dict(event=ev, sent_idx=r["sent_idx"],
                             label=r["label"], w=r["w"], model=r["model"],
                             unit=r["unit"], params=plist),
                        ensure_ascii=False) + "\n")

        extra = len(set(evmap) - v3_events)
        tot_par = sum(n_par.values())
        tot_found = sum(n_found.values())
        checks[env] = (pool_ok.buf, pool_ng.buf)
        report += [
            f"\n## {env}",
            f"- 重抽事件 {len(evmap)} / v3 事件 {len(v3_events)};"
            f"v3 有而重抽缺 {sum(miss_ev.values())} 样本"
            f"(按 split {dict(miss_ev)});重抽有而 v3 无 {extra} 事件",
            f"- 无参事件 {len(noparam_ev)}"
            f"({len(noparam_ev)/max(len(v3_events),1):.1%})",
            f"- 样本行 {sum(n_rows.values())} / 参数实例 {tot_par} / "
            f"已定位 {tot_found}(**总定位率 {tot_found/max(tot_par,1):.3f}**)",
            f"- 区间断言 text[start:end]==value: {n_assert}/{n_assert} ✓",
            "",
            "| split | 样本行 | 参数实例 | 定位率 |",
            "|---|---|---|---|",
        ]
        for sp in SPLITS:
            report.append(f"| {sp} | {n_rows[sp]} | {n_par[sp]} | "
                          f"{n_found[sp]/max(n_par[sp],1):.3f} |")
        report += [
            "",
            "深度十桶定位率(0.0=思考刚开头,0.9=思考末尾):",
            "",
            "| 桶 | " + " | ".join(f"{i/10:.1f}" for i in range(10)) + " |",
            "|---|" + "---|" * 10,
            "| 定位率 | " + " | ".join(
                f"{dep_hit[i]/dep_tot[i]:.3f}" if dep_tot[i] else "-"
                for i in range(10)) + " |",
            "| 参数实例 | " + " | ".join(str(dep_tot[i])
                                         for i in range(10)) + " |",
            "",
            f"- 末边界(整段思考读完)定位率 {last_hit/max(last_tot,1):.3f}"
            f"({last_hit}/{last_tot})",
            f"- 已定位里落在 [THINKING] 段内的占 "
            f"{n_inthink/max(tot_found,1):.3f}(其余抄自题干/历史)",
            f"- 已定位里值 ≤3 字符的占 {n_short/max(tot_found,1):.3f}"
            "(短值 rfind 可能撞上巧合子串,标签噪声上界)",
        ]
        print(f"{env}: params={tot_par} found_rate="
              f"{tot_found/max(tot_par,1):.3f}", flush=True)

    report += [
        "\n## 对照锚点与已知噪声",
        "- 先行试点:提前 25 token 时参数字面串仅 33.8% 已出现;"
        "本表深度桶给出全景版本(桶越靠左=触发越早=定位率越低),"
        "口径差别在于本表在整条 text(题干+历史+思考前缀)里找,"
        "试点只看思考,故本表最左桶显著高于 33.8%。",
        "- 竞品 SPORK 参数起步正确率 7.6%(抽取头正确率的下限锚)。",
        "- 噪声:短值(如 `20`/`token`)的 rfind 可能撞上巧合子串,"
        "CHECK_50 已见实例;各环境占比见上文 ≤3 字符行,"
        "抽取头评测按同一口径打分,故该噪声对训练/评测一致,不产生偏袒。",
    ]
    (out_root / "PARAM_LABEL_REPORT.md").write_text("\n".join(report) + "\n")

    # ---------- CHECK_50 ----------
    quota_ok = {"appworld": 17, "tales": 17, "bfcl": 16}
    quota_ng = {"appworld": 4, "tales": 3, "bfcl": 3}
    md = [f"# CHECK_50 — 参数定位人工核对件(SEED={SEED})\n",
          "定位区间用【】标出,前后各 80 字符上下文;逐条核对"
          "【】里是不是该参数该有的值。\n"]
    i = 0
    for env in ENVS:
        ok, _ = checks[env]
        for (e, k, v, s, en, text) in ok[:quota_ok[env]]:
            i += 1
            head = text[max(0, s - CTX):s].replace("\n", "⏎")
            body = text[s:en].replace("\n", "⏎")
            tail = text[en:en + CTX].replace("\n", "⏎")
            md += [f"### [{i}] {e} — `{k}`",
                   f"- value: `{v}`  区间 [{s},{en})",
                   f"```\n...{head}【{body}】{tail}...\n```"]
    md += ["\n## 抽不到(found=false)案例 — 核对是否确实未出现\n"]
    j = 0
    for env in ENVS:
        _, ng = checks[env]
        for (e, k, v, tail) in ng[:quota_ng[env]]:
            j += 1
            md += [f"### [NG{j}] {e} — `{k}`",
                   f"- value: `{v}`",
                   f"- text 末 120 字符:\n```\n{tail}\n```"]
    (out_root / "CHECK_50.md").write_text("\n".join(md) + "\n")
    print(f"done -> {out_root}(CHECK_50: {i} 定位 / {j} 抽不到)")


if __name__ == "__main__":
    main()
