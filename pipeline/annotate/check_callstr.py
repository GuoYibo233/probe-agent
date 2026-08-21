#!/usr/bin/env python3
"""annotate 后置门禁:真值调用串能否被 eval 侧原样切回来 + 五道结构性硬核对(纯 CPU)。

要回答什么问题:build.py 写进每条样本的真值 `label_call`(手拼的 `tool(k=v, k=v)`),
拿 eval 侧的 `eval_causal_call.parse_call` 去切,能不能一字不差地切回 `args_named`?
切不回来的那部分,就是 `params_all_ok` 这个指标**永远拿不到的分**——生成侧写得再对
也判错,因为真值本身在 eval 的切法下不自洽。

为什么必须有这一步:`build.make_call` 是 `", ".join(f"{k}={v}")` 手拼、不加引号,而
eval 侧 `split_named_raw` 按**顶层逗号**切参数。参数值里带逗号就切散了。实测例:
    echo(content=Finally, in that file, Write my last question in it., file_name=79.pdf)
被切成 content=Finally / pos0=in that file / pos1=Write my last question in it. /
file_name=79.pdf。rules.py 里 ALFWorld 有 ALF_BAD_CHARS 逗号闸门专门拦这个,
appworld / bfcl 都没有。本脚本**只量不修**:appworld 的 c1_* 十二格数字已经按"无闸门"
的口径上账,给 bfcl 单独加闸门就不是一把尺子了。

顺带把五道结构性门禁一起做了(全部 sys.exit 硬拦,写在这里是因为它们都要在
build.py + param_label.py 跑完之后、拿成品数据集才能验):
  门禁 A 每行 model 字段 == cfg.model_full。防跨模型串味(extending.md §5 #13:
         唯一防线是 eval 侧 len(rows)==logits.shape[0] 的形状 assert,不能当保障)。
  门禁 B (event, sent_idx) 全局唯一,且一个 unit 在本模型下只对应一个 traj。
         这是 traj_runs 写错的照妖镜:把 traj_runs 写成父目录 envs/runs 时,
         build.py:101 的 runs.glob("bfcl_*") 会命中 21 题的 smoke 批次
         envs/runs/bfcl_q35/,它的 traj 名与 full_v1/bfcl_q35 逐字相同,
         同一批 event key 会重复进库、退 0、无告警,只是样本数悄悄涨。
  门禁 C traj_runs 的每一项都必须是"run 目录"本身,不能是 run 目录的父目录。
         判据:该项下**直接**有 bfcl_<模型> 子目录,且 `*/bfcl_<模型>` 不再命中
         任何目录(命中就说明它是父目录)。这是门禁 B 的上游拦截。
  门禁 D 每行的 unit 必须落在它所在堆的题单文件里(题单归属全量核对,不抽样)。
  门禁 E ANNOTATE_REPORT.md 的文案不许撒谎:SPLIT_REPORT.json 说
         official_split_exists=false 时,报告里不许出现"官方题单"。

报告里另外逐条列出四类**已知偏差**(不硬拦,但必须可见,不然没人知道数字为什么难看):
  偏差 1 真值调用串回读损失(上面那件事),按事件/参数两级给数。
  偏差 2 题单一致但实现实例有缺口:三个模型共用一份题单,某些 unit 的轨迹一个
         可用事件都没出(思考 <40 字符或调用解析不出),逐条列出缺哪些。
         现行门禁 G10「三模型 unit 集合完全相同」在 bfcl 上必然不成立。
  偏差 3 test 堆里出现、train 堆里没出现过的工具:这类在 label2id 里(词表按全堆
         统计),不会被 eval_tool.py 丢掉,而是必然判错 = 不可达的精度上限。
  偏差 4 test 堆事件数偏薄的告警:事件太少时 risk 档的 θ 可能全 null,
         eval_causal_call 直接 SystemExit 退 1(先例 c1_q35_mext)。

已知偏差(本脚本自己的):回读检查比的是"eval 切法 vs annotate 拼串",不检查生成侧;
`parse_call` 只看**第一个**匹配到的调用,与 build/param_label 的 first_call_* 同源。

用法: python3 pipeline/annotate/check_callstr.py --config pipeline/configs/bfcl_q35.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# 纯 CPU 脚本,但 eval_causal_call 内部 import torch。显式关掉可见显卡,
# 保证本脚本在任何情况下都碰不到 GPU。
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "eval"))
from rules import MODEL_OF, SEED                       # noqa: E402
# eval_causal_call 的 import 延后到 main() 里真正用到 norm/parse_call 的地方
# (偏差 1 回读检查)才做:它模块级 import torch,提前到这里会让整个文件在没装
# torch 的环境下连 import 都做不到,门禁 B 的 K 条判据/§8b 补强判据这些纯逻辑
# 就没法脱离 cprobe-env 单测(见 tests/test_check_callstr.py)。延迟不改变任何
# 输出字节:torch 什么时候被拉起来对 stdout/报告文件没有影响。

SPLITS = ("train", "val", "test")
THIN_TEST_EVENTS = 200      # test 事件数低于此值就报"θ 可能全 null"的风险
MAX_LIST = 12               # 报告里逐条列举的上限(超出只报数)
EXAMPLES = 5                # 回读失败的样例条数


def read_unit_list(path):
    """【照抄 build.py:read_unit_list】题单每行一个 unit,去空行。"""
    return [ln.strip() for ln in Path(path).read_text().split("\n")
            if ln.strip()]


def gate_c(traj_runs, env):
    """门禁 C:traj_runs 的每一项必须是 run 目录本身,不是它的父目录。"""
    if env != "bfcl":
        # 别的环境走 jsonl_events 的 glob("<env>_*/<env>_*.jsonl"),层级不同,
        # 这道门禁的判据不适用,直接跳过(不假装检查过)。
        return f"门禁 C 跳过(env={env} 不用 runs.glob 那条路径)"
    for r in traj_runs:
        p = Path(r)
        if not p.is_dir():
            sys.exit(f"[门禁 C] traj_runs 目录不存在: {p}")
        direct = [d for d in p.glob("bfcl_*")
                  if d.is_dir() and MODEL_OF.get(d.name.rsplit("_", 1)[1])]
        nested = [d for d in p.glob("*/bfcl_*")
                  if d.is_dir() and MODEL_OF.get(d.name.rsplit("_", 1)[1])]
        if nested:
            sys.exit(
                f"[门禁 C] traj_runs 项 {p} 看着是 run 目录的**父目录**:"
                f"它下面还有 {len(nested)} 个嵌套的 run 目录"
                f"(例 {nested[0]})。写父目录会让 build.py:101 的"
                f" runs.glob('bfcl_*') 只扫到平级的 smoke 批次、"
                f"或把 smoke 批次与全量批次重复并进来。请写到 run 目录一级。")
        if not direct:
            sys.exit(f"[门禁 C] traj_runs 项 {p} 下没有任何 bfcl_<模型> 子目录")
    return f"门禁 C {len(traj_runs)} 项 traj_runs 均为 run 目录本身 ✓"


def parse_sample_idx(traj):
    """从 traj 字符串(形如 "<batch>/<stem>")的 stem 尾部解析多样本采集的采样
    序号 `_r<k>`。解析不出(老式无后缀文件名)返回 None。"""
    stem = traj.rsplit("/", 1)[-1]
    m = re.search(r"_r(\d+)$", stem)
    return int(m.group(1)) if m else None


def gate_b_unit_traj(rows_by_split, K):
    """门禁 B 第二半:unit -> traj 判据(K 条判据,plans §4 + §8b 补强判据)。

    刻意写成不 import eval_causal_call/torch 的纯函数,好让它能脱离 cprobe-env
    单独单测(见 tests/test_check_callstr.py);第一半的样本键唯一判据
    ((event, sent_idx) 全局唯一,main() 里 138-143 行区域)不在这个函数里,
    维持原地不动。

    K = cfg.get("trajs_per_unit", 1)。K==1 时判据与文案与旧版逐字节一致
    (旧配置重跑 CALLSTR_CHECK.md 必须逐字节一致);K>1 时:
      - 每个 unit 必须恰好对应 K 条互异 traj;
      - §8b 补强判据 1:显式再核验一次 K 条 traj 互异(重复扫描产生同名 traj
        理论上已被样本键唯一判据拦下,这里的 set 聚合本就天然去重,再显式断言
        一次是防御性判据,报错文案与「条数不对」分开,便于区分症状);
      - §8b 补强判据 2:K 条 traj 文件名尾部的采样序号解析出来后必须恰好是
        {0..K-1} 各一个;解析不出(文件名不带 _r<k> 后缀)单独报错。

    rows_by_split: {split: [row, ...]},row 至少带 "unit"/"traj" 两个键。
    返回 (ok, msg):
      ok=True  时 msg 是成功文案(不含 "门禁 B 样本键..." 前缀,调用方自己拼)。
      ok=False 时 msg 是失败文案(不含 "[门禁 B] " 前缀,调用方自己拼再 sys.exit)。
    """
    u2t = {}
    for sp in SPLITS:
        for r in rows_by_split[sp]:
            u2t.setdefault(r["unit"], set()).add(r["traj"])

    if K == 1:
        # 旧口径原样保留:len(t) > 1 即死,判据与文案逐字节不变。
        multi = {u: sorted(t) for u, t in u2t.items() if len(t) > 1}
        if multi:
            return False, (f"{len(multi)} 个 unit 对应多个 traj,"
                           f"例 {list(multi.items())[:2]};同一模型下一个任务实例只应有一条轨迹")
        return True, f"{len(u2t)} 个 unit 各对一条 traj ✓"

    # K > 1:每个 unit 必须恰好 K 条 traj。例子里带 (实际条数, traj 列表),
    # 与 K 一并摆出来,别让人还得数 traj 列表的长度才知道差多少。
    bad_count = {u: (len(t), sorted(t)) for u, t in u2t.items()
                if len(t) != K}
    if bad_count:
        ex = list(bad_count.items())[:2]
        return False, (f"{len(bad_count)} 个 unit 的 traj 条数不是 "
                       f"trajs_per_unit={K},例(unit, (实际条数, traj)) {ex}")

    # §8b 补强判据 1:显式再断言一次 K 条 traj 互异。
    dup_units = [u for u, t in u2t.items() if len(t) != len(set(t))]
    if dup_units:
        return False, (f"{len(dup_units)} 个 unit 的 traj 出现重复字符串,"
                       f"例 {dup_units[:3]};多半是 traj_runs 把同一批轨迹扫了两遍")

    # §8b 补强判据 2:采样序号必须恰好是 {0..K-1} 各一个。
    unparsed, idx_of = [], {}
    for u, t in u2t.items():
        idxs = []
        for traj in sorted(t):
            k = parse_sample_idx(traj)
            if k is None:
                unparsed.append((u, traj))
            else:
                idxs.append(k)
        idx_of[u] = idxs
    if unparsed:
        return False, (f"{len(unparsed)} 条 traj 文件名不带采样序号(stem 尾部"
                       f"解析不出 _r<k>),例 {unparsed[:3]};trajs_per_unit="
                       f"{K} > 1 时每条 traj 文件名都必须带 _r0.._r{K - 1} "
                       f"的采样序号后缀")
    bad_idx = {u: sorted(idxs) for u, idxs in idx_of.items()
              if sorted(idxs) != list(range(K))}
    if bad_idx:
        ex = list(bad_idx.items())[:2]
        return False, (f"{len(bad_idx)} 个 unit 的采样序号不是 "
                       f"{{0..{K - 1}}} 各一个,例 {ex}")

    return True, f"{len(u2t)} 个 unit 各对恰好 {K} 条 traj ✓"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="实验配置 json(§2.3)")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    env = cfg["env"]
    model_full = cfg["model_full"]
    data = Path(cfg["data_out"])
    seed = cfg.get("seed", SEED)
    gates = []

    # ---------- 门禁 C(先做:它是 B 的上游拦截) ----------
    gates.append(gate_c(cfg["traj_runs"], env))

    # ---------- 读题单 ----------
    lists = {n: set(read_unit_list(cfg["official_split_files"][n]))
             for n in SPLITS}

    rows = {}
    for sp in SPLITS:
        p = data / f"{sp}.jsonl"
        if not p.is_file():
            sys.exit(f"数据集不存在: {p}(先跑 build.py)")
        rows[sp] = [json.loads(l) for l in open(p)]

    # ---------- 门禁 A:一模型一数据集 ----------
    bad_model = Counter(r["model"] for sp in SPLITS for r in rows[sp]
                        if r["model"] != model_full)
    if bad_model:
        sys.exit(f"[门禁 A] 数据集里混进了别的模型: {dict(bad_model)}"
                 f"(cfg.model_full={model_full})")
    gates.append(f"门禁 A 全部 {sum(len(rows[s]) for s in SPLITS)} 行 "
                 f"model=={model_full} ✓")

    # ---------- 门禁 B:样本键唯一 + unit 只对一个 traj ----------
    keyc = Counter((r["event"], r["sent_idx"]) for sp in SPLITS
                   for r in rows[sp])
    dupk = [k for k, c in keyc.items() if c > 1]
    if dupk:
        sys.exit(f"[门禁 B] (event, sent_idx) 重复 {len(dupk)} 个,"
                 f"例 {dupk[:3]};多半是 traj_runs 把同一批轨迹扫了两遍")
    K = cfg.get("trajs_per_unit", 1)
    gate_ok, gate_msg = gate_b_unit_traj(rows, K)
    if not gate_ok:
        sys.exit(f"[门禁 B] {gate_msg}")
    gates.append(f"门禁 B 样本键 {len(keyc)} 个全唯一;{gate_msg}")

    # ---------- 门禁 D:题单归属全量核对 ----------
    wrong = []
    for sp in SPLITS:
        for r in rows[sp]:
            if r["unit"] not in lists[sp]:
                wrong.append((sp, r["unit"]))
    if wrong:
        sys.exit(f"[门禁 D] {len(wrong)} 行的 unit 不在本堆题单里,例 {wrong[:3]}")
    gates.append("门禁 D 题单归属全量核对(非抽样)✓")

    # ---------- 门禁 E:报告文案不许撒谎 ----------
    sp_report = Path(cfg["official_split_files"]["train"]).parent \
        / "SPLIT_REPORT.json"
    if sp_report.is_file():
        meta = json.loads(sp_report.read_text())
        rp = data / "ANNOTATE_REPORT.md"
        txt = rp.read_text() if rp.is_file() else ""
        if meta.get("official_split_exists") is False and "官方题单" in txt:
            sys.exit(
                f"[门禁 E] {sp_report} 写着本环境没有官方分区,"
                f"但 {rp} 的文案里还印着「官方题单」。"
                f"请在 config 里写 split_desc 说明真实切法(build.py 从该字段取文案)。")
        gates.append(f"门禁 E 报告文案与 SPLIT_REPORT 一致 ✓"
                     f"(official_split_exists="
                     f"{meta.get('official_split_exists')})")
    else:
        gates.append(f"门禁 E 跳过(没找到 {sp_report})")

    # ---------- 偏差 1:真值调用串回读 ----------
    # 到这里才 import(见文件头注释:eval_causal_call 拉 torch,延后到真正用到
    # 的地方,好让门禁 A-E 与结构性判据能在没装 torch 的环境下跑/单测)。
    from eval_causal_call import norm, parse_call
    # 一个事件里所有样本共享同一条 label_call,按事件去重后逐条切。
    ev_call, ev_split = {}, {}
    for sp in SPLITS:
        for r in rows[sp]:
            ev_call.setdefault(r["event"], (r["label"], r["label_call"],
                                            r["args_named"]))
            ev_split.setdefault(r["event"], sp)
    n_ev = len(ev_call)
    bad_tool, bad_par, comma_val, ok = 0, [], 0, 0
    par_tot = par_ok = 0
    per_split_bad = Counter()
    for evk, (label, call, named) in sorted(ev_call.items()):
        for a in named:
            par_tot += 1
            if "," in a["value"]:
                comma_val += 1
        tool, raw = parse_call(call, env)
        got = [dict(key=k, value=norm(v)) for k, v in raw]
        if tool != label:
            bad_tool += 1
        if got == named:
            ok += 1
            par_ok += len(named)
        else:
            bad_par.append((evk, call, named, got))
            per_split_bad[ev_split[evk]] += 1
            # 逐参数记功:键值都对上的才算回读成功
            gset = {(a["key"], a["value"]) for a in got}
            par_ok += sum(1 for a in named
                          if (a["key"], a["value"]) in gset)

    # ---------- 偏差 2:题单缺口 ----------
    gap = {sp: sorted(lists[sp] - {r["unit"] for r in rows[sp]})
           for sp in SPLITS}

    # ---------- 偏差 3:test 有 / train 无的工具 ----------
    tools = {sp: Counter(r["label"] for r in rows[sp]) for sp in SPLITS}
    unseen = sorted(set(tools["test"]) - set(tools["train"]))
    unseen_ev = {t: len({r["event"] for r in rows["test"] if r["label"] == t})
                 for t in unseen}

    # ---------- 偏差 4:test 堆厚度 ----------
    test_ev = len({r["event"] for r in rows["test"]})

    md = [f"# {cfg['run_family']} / {cfg['model_short']} 真值调用串回读检查"
          f"(check_callstr.py)\n",
          f"- SEED={seed} env={env} model={model_full}",
          f"- config={args.config} data={data}",
          "- 口径:对每个事件的 label_call 调 "
          "`eval_causal_call.parse_call`,再把 `(key, norm(value))` 与该事件的 "
          "`args_named` 逐位比;全等才算回读成功。\n",
          "## 结构性门禁"]
    md += [f"- {g}" for g in gates]
    md += [
        "\n## 偏差 1:真值调用串回读",
        f"- 事件 {n_ev};回读成功 {ok}(**{ok/max(n_ev,1):.4f}**),"
        f"失败 {len(bad_par)}(**{len(bad_par)/max(n_ev,1):.4f}**)",
        f"- 失败按 split: {dict(per_split_bad) or '{}'}",
        f"- 工具名切不回来的事件: {bad_tool}",
        f"- 参数实例 {par_tot};回读成功 {par_ok}"
        f"(**{par_ok/max(par_tot,1):.4f}**)",
        f"- 参数值里含逗号的实例: {comma_val}"
        f"({comma_val/max(par_tot,1):.4f})← 这是失败的主因",
        f"- **结论:params_all_ok / full_call_ok 的天花板是 "
        f"{ok/max(n_ev,1):.4f}**,生成侧写得再对也拿不到剩下那部分。"
        f"不修口径的理由见文件头。",
        "",
        f"### 失败样例(前 {EXAMPLES} 条)",
    ]
    for evk, call, named, got in bad_par[:EXAMPLES]:
        md += [f"- `{evk}`",
               f"  - label_call: `{call}`",
               f"  - annotate 侧真值: `{named}`",
               f"  - eval 侧切回来: `{got}`"]
    if not bad_par:
        md.append("(无)")

    md += ["\n## 偏差 2:题单一致但实现实例有缺口",
           "三个模型共用同一份题单;某个 unit 的轨迹若一个可用事件都没出"
           "(思考 <40 字符 或 调用正则解析不出),该 unit 就不进本模型的数据集。"
           "所以现行门禁 G10「三模型 unit 集合完全相同」在 bfcl 上不成立,"
           "跨模型只是**近似**同题。"]
    for sp in SPLITS:
        g = gap[sp]
        shown = ", ".join(g[:MAX_LIST]) + (" ..." if len(g) > MAX_LIST else "")
        md.append(f"- {sp}: 题单 {len(lists[sp])} 题 -> 实现 "
                  f"{len({r['unit'] for r in rows[sp]})} 题;缺 {len(g)} 题"
                  + (f": {shown}" if g else ""))

    md += ["\n## 偏差 3:test 出现而 train 未出现的工具",
           "这类工具在 label2id 里(tool_vocab.json 按全堆统计),"
           "不会被 eval_tool.py 丢掉,而是**必然判错** = 不可达的精度上限。",
           f"- {len(unseen)} 类: {unseen_ev if unseen else '(无)'}",
           f"- 词表规模: train {len(tools['train'])} / val {len(tools['val'])}"
           f" / test {len(tools['test'])} 类"]

    md += ["\n## 偏差 4:test 堆厚度",
           f"- test 事件 {test_ev} / 实例 "
           f"{len({r['unit'] for r in rows['test']})}"
           f" / 样本 {len(rows['test'])}"]
    if test_ev < THIN_TEST_EVENTS:
        md.append(f"- ⚠ test 事件数 {test_ev} < {THIN_TEST_EVENTS}:"
                  f"bootstrap 置信区间会很宽,且低 risk 档(0.05)很可能没有触发点、"
                  f"θ 全 null 导致 eval_causal_call 直接 SystemExit 退 1"
                  f"(先例 c1_q35_mext)。交接时必须点明。")
    else:
        md.append(f"- test 事件数 {test_ev} ≥ {THIN_TEST_EVENTS},厚度正常")

    if sp_report.is_file():
        meta = json.loads(sp_report.read_text())
        md += ["\n## 题单真源",
               f"- 唯一真源 = 入库的 txt:{sp_report.parent}",
               f"- {meta.get('truth_source', '')}",
               f"- 推导源 md5: {meta.get('md5', {})}"]

    (data / "CALLSTR_CHECK.md").write_text("\n".join(md) + "\n")
    for g in gates:
        print(f"[gate] {g}")
    print(f"{env}/{cfg['model_short']}: 回读 {ok}/{n_ev} "
          f"({ok/max(n_ev,1):.4f}) 参数 {par_ok}/{par_tot} "
          f"含逗号 {comma_val};题单缺口 "
          f"{ {sp: len(gap[sp]) for sp in SPLITS} }")
    print(f"done -> {data / 'CALLSTR_CHECK.md'}")


if __name__ == "__main__":
    main()
