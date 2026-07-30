"""切分规则常量与函数(【照抄】旧代码,新流水线的唯一真源)。

- 前七项常量 + SENT_RE + boundaries/clip/assemble/split_args/first_call_args
  + AW_CALL/BFCL_CALL:原样复制自 envs/collect/build_dataset.py
- split_args_named/first_call_named/mkparams:原样复制自 envs/bert/param_label.py

输入输出:本文件只放纯函数与常量,不读写任何文件。
用法示例: from rules import boundaries, assemble, AW_CALL
"""

import re

SEED = 20260729
MAX_BOUNDS = 64       # 每事件边界上限(gpt-oss 超长思考防爆)
MIN_THINK = 40        # 字符;再短的思考没有可切性
HIST_ROUNDS = 3       # 题干里保留最近几轮工具历史
RESULT_CAP = 400      # 每条环境返回在题干里的字符上限
MODEL_OF = {"q35": "qwen3.5-27b", "q36": "qwen3.6-27b", "gptoss": "gpt-oss-120b"}

# 句子边界:换行,或 .!? 后跟空白(小数点/apis.x.y 的点后无空白,天然排除)
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")


def boundaries(text):
    """全部合法切点(字符偏移,前缀=text[:i]),含全文末尾,上限 MAX_BOUNDS。"""
    pts = sorted({m.end() for m in SENT_RE.finditer(text)} | {len(text)})
    pts = [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]
    if not pts:
        pts = [len(text)]
    if len(pts) > MAX_BOUNDS:
        keep = {len(pts) - 1}
        step = (len(pts) - 1) / (MAX_BOUNDS - 1)
        keep.update(round(k * step) for k in range(MAX_BOUNDS - 1))
        pts = [pts[j] for j in sorted(keep)]
    return pts


def clip(s, cap=RESULT_CAP):
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]


def assemble(task, history, think_prefix):
    lines = [f"Task: {task}", "[HISTORY]"]
    if history:
        lines += [f"{a} -> {clip(r)}" for a, r in history[-HIST_ROUNDS:]]
    else:
        lines.append("(start)")
    lines += ["[THINKING]", think_prefix]
    return "\n".join(lines)


# ---------- 参数抽取(路由统计用) ----------

AW_CALL = re.compile(r"apis\.(\w+)\.(\w+)\(")
BFCL_CALL = re.compile(r"(\w+)\(")


def split_args(argstr):
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
    out = []
    for v in vals:
        m = re.match(r"\w+\s*=\s*(.+)", v, re.S)
        out.append((m.group(1) if m else v).strip().strip("\"'"))
    return out


def first_call_args(code, name_re):
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
                return split_args(code[i + 1: j])
    return []


# ---------- 保名版参数解析(与 split_args 同切法) ----------

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
