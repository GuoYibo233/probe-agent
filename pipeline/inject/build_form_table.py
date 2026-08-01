"""统计每个工具在真实轨迹里的调用形态,给拼回实验的骨架用。规格:
plans/2026-08-01-splice-impl-spec.md §D2

骨架臂(skel_*)要在思考里塞一句 `print(apis.venmo.login` 这样的半截调用,
让大模型接着写参数。塞什么壳子不能拍脑袋:gpt-oss 写 `show_app_descriptions`
这种查文档的调用惯用 `print(...)` 包住,写 `login` 这种要拿返回值的惯用
`token = apis...` 赋值。壳子选错,模型第一步就得先把我们写的那行推翻。

所以先把两批已采轨迹(full_v1 + full_v2_topup 的 appworld_gptoss)里每步 final
代码块的首条调用扒出来,按工具聚合成 {tool: {n, print_share, assign_share,
top_var}},运行时查表决定壳子:assign_share >= 0.5 用赋值形(变量名取 top_var),
否则用 print 形,表里没见过的工具兜底 print。

**只读 full_v1 / full_v2_topup,绝不碰 w0_aw_official**——那是留给活跑的 test 集,
从它身上统计形态等于把答案先看一遍。

用法:python pipeline/inject/build_form_table.py
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[2]

# 【照抄 envs/collect/run_appworld.py:38】提代码块用同一条正则
CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)
# 【照抄 pipeline/annotate/rules.py:55】工具名口径只有一份
AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")
# 赋值形:整行左边只有一个变量名和一个等号(`x ==` 这种比较不算)
ASSIGN_RE = re.compile(r"^\s*(\w+)\s*=$")

# 训练/统计用的两批轨迹,相对工程根。w0 test 集不在这里,也不许加进来
DEFAULT_ROOTS = ("envs/runs/full_v1/appworld_gptoss",
                 "envs/runs/full_v2_topup/appworld_gptoss")
DEFAULT_OUT = "pipeline/inject/form_table.json"


def call_form(code):
    """一段代码里首条 apis 调用的形态。返回 (tool, form, var) 或 None。

    form 取五种之一:
      assign      `x = apis...`            —— 拿返回值再用
      print       `print(apis...`          —— 直接看输出
      print_multi `print("x:", apis...`    —— 也是 print 包裹,但壳子带别的参数
      bare        行首就是 apis...          —— 裸调用
      other       其余(嵌在 if / for / 别的调用里)
    只有 assign 会带 var。
    """
    m = AW_CALL.search(code or "")
    if m is None:
        return None
    tool = f"apis.{m.group(1)}.{m.group(2)}"
    ls = code.rfind("\n", 0, m.start()) + 1
    pre = code[ls:m.start()].rstrip()
    am = ASSIGN_RE.match(pre)
    if am:
        return tool, "assign", am.group(1)
    if pre.endswith("print("):
        return tool, "print", None
    if "print(" in pre:
        return tool, "print_multi", None
    if pre == "":
        return tool, "bare", None
    return tool, "other", None


def scan(roots):
    """扫轨迹目录,返回 (per_tool 形态计数, per_tool 变量名计数, 文件/记录统计)。"""
    forms = defaultdict(Counter)
    vars_ = defaultdict(Counter)
    stat = Counter()
    for root in roots:
        files = sorted(Path(root).glob("*.jsonl"))
        stat["files"] += len(files)
        for fp in files:
            for line in open(fp):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    stat["bad_line"] += 1
                    continue
                if r.get("type") != "gen":
                    continue
                stat["gen"] += 1
                m = CODE_RE.search(r.get("content") or "")
                if m is None:
                    stat["no_code_block"] += 1
                    continue
                got = call_form(m.group(1))
                if got is None:
                    stat["no_api_call"] += 1
                    continue
                tool, form, var = got
                forms[tool][form] += 1
                stat[f"form_{form}"] += 1
                if var:
                    vars_[tool][var] += 1
    return forms, vars_, stat


def build(forms, vars_):
    """形态计数 -> form_table.json 的内容。"""
    table = {}
    for tool, c in sorted(forms.items()):
        n = sum(c.values())
        top_var = vars_[tool].most_common(1)[0][0] if vars_[tool] else None
        table[tool] = dict(
            n=n,
            print_share=round(c["print"] / n, 4),
            assign_share=round(c["assign"] / n, 4),
            top_var=top_var)
    return table


def load_table(path=None):
    """读 form_table.json;文件不在就返回空表(骨架全走 print 兜底)。"""
    p = Path(path or (PROJ_ROOT / DEFAULT_OUT))
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def skeleton(pred_label, table):
    """骨架串:查表决定 print 壳还是赋值壳。

    **一律不带尾左括号**——分词器实测(规格 §前置事实):`print(apis.venmo.login(`
    的尾左括号在真实续写里会和参数名融成 `(username` 一个 token,前缀必分叉;
    砍到 `print(apis.venmo.login` 则 6/6 严格前缀吻合。
    传进来的必须是 pred_label(探针预测),绝不许是 label(真值)。
    """
    e = table.get(pred_label) or {}
    if e.get("assign_share", 0.0) >= 0.5 and e.get("top_var"):
        return f"{e['top_var']} = {pred_label}"
    return "print(" + pred_label


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--roots", nargs="+", default=None,
                    help=f"轨迹目录(默认 {' '.join(DEFAULT_ROOTS)},"
                         "相对工程根)。w0 test 集不许进来")
    ap.add_argument("--out", default=None,
                    help=f"输出 json(默认 {DEFAULT_OUT})")
    ap.add_argument("--top", type=int, default=15,
                    help="摘要里打印几个高频工具")
    a = ap.parse_args()

    roots = [Path(r) if Path(r).is_absolute() else PROJ_ROOT / r
             for r in (a.roots or DEFAULT_ROOTS)]
    for r in roots:
        if "w0_" in str(r):
            raise SystemExit(f"{r} 是 test 集,形态表不许从它统计")
        if not r.is_dir():
            raise SystemExit(f"轨迹目录不在:{r}")

    forms, vars_, stat = scan(roots)
    table = build(forms, vars_)
    out = Path(a.out) if a.out else PROJ_ROOT / DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, ensure_ascii=False, indent=1))

    n_assign = [t for t, e in table.items() if e["assign_share"] >= 0.5]
    print(json.dumps(dict(roots=[str(r) for r in roots], out=str(out),
                          n_tools=len(table),
                          n_calls=sum(e["n"] for e in table.values()),
                          n_assign_form=len(n_assign),
                          scan=dict(stat)), ensure_ascii=False, indent=1))
    print("\nassign 形的工具(骨架写 `var = apis...`):")
    for t in sorted(n_assign, key=lambda x: -table[x]["n"]):
        e = table[t]
        print(f"  {t:52s} n={e['n']:5d} assign={e['assign_share']:.2f} "
              f"var={e['top_var']}")
    print(f"\n高频工具 top{a.top}(骨架样例):")
    for t, e in sorted(table.items(), key=lambda kv: -kv[1]["n"])[:a.top]:
        print(f"  {t:52s} n={e['n']:5d} print={e['print_share']:.2f} "
              f"assign={e['assign_share']:.2f} -> {skeleton(t, table)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
