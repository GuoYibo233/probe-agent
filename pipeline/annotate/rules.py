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


# ---------- ALFWorld:自然语言动作 -> 工具名 + 具名参数(c2 批次,模板细分口径) ----------
#
# 唯一真源 = 本机 alfworld==0.4.2 装出来的动作语法文件
#   fig1_pilot/fig1-env/lib/python3.12/site-packages/alfworld/data/alfred.twl2
# 下表逐条对应该文件的 `template :: "..."` 行(行号写在注释里),共 13 条。
# 该文件里另有 8 行 template 不进本表,理由分三类:
#   - 重复:191/196/201/206 都是 `take {o} from {r}`,211/221 都是 `move {o} to {r}`,
#           236/241 都是 `examine {x}` —— 同一个表层模板的多个 action 定义
#   - movable-receptacle 变体:216 `put {o} into {outero}`、226 `put {outero} in {r}`
#           —— ALFWorld 自己会排除这类任务,故排除
#   - 元命令:425 `help` —— 不是环境动作,它的 feedback 文本反过来正好把这 13 条逐条列了一遍
#
# 参数键名口径:介词位取介词本身(to/from/with),前置宾语位取 obj;
# 全部匹配 `\w+`,满足 rules.split_args_named 对键的要求。

ALF_TEMPLATES = (
    ("go to {to}", 176),                    # action GotoLocation
    ("take {obj} from {from}", 191),        # action PickupObject(+196/201/206)
    ("move {obj} to {to}", 211),            # action PutObject(+221)
    ("heat {obj} with {with}", 269),        # action HeatObject
    ("clean {obj} with {with}", 284),       # action CleanObject
    ("cool {obj} with {with}", 299),        # action CoolObject
    ("slice {obj} with {with}", 314),       # action SliceObject
    ("examine {obj}", 236),                 # action examineReceptacle(+241)
    ("inventory", 231),                     # action inventory
    ("open {obj}", 181),                    # action OpenObject
    ("close {obj}", 186),                   # action CloseObject
    ("use {obj}", 246),                     # action ToggleObject
    ("look", 329),                          # action look
)

# 参数值里绝不允许出现的字符。逗号是硬要求:eval_causal_call.split_named_raw
# 按顶层逗号切参数,而 annotate 侧手拼 label_call 时不切,值里带逗号 = 静默扣分。
# 括号/引号同理会让 parse_call 的括号配平与 split_args_named 的去引号走偏。
ALF_BAD_CHARS = ",()[]{}\"'"

# 参数值的形状闸门:ALFWorld 的实体名一律是「单个纯字母类型名 + 空格 + 序号」
# (mug 1 / countertop 3 / sinkbasin 1 / bathtubbasin 1)——ALFRED 的物体类型是
# CamelCase 单词,textworld 小写后拼上序号。实测 fig1_pilot 全部 17510 条动作里的
# 146 个不同实体值 100% 是这个形状。
# 它拦的是**逗号闸门拦不住的那类污染**:模板尾槽是贪婪的 `(.+)`,所以
# `go to countertop 1 and take mug 1` 会匹配上 `go to {to}`,值变成
# "countertop 1 and take mug 1" —— 一条环境根本不接受的动作,却会静默变成
# 一条合法真值。`go to countertop 1.` 的尾点同理。这类一律落到兜底并被计数。
ALF_VALUE_RE = re.compile(r"[A-Za-z]+ \d+")


def _alf_compile(tpl):
    """`"take {obj} from {from}"` -> (工具名, [键...], 前导字面量, 编译好的正则)。"""
    parts = re.split(r"\{(\w+)\}", tpl)     # 偶下标=字面量,奇下标=参数名
    keys = parts[1::2]
    pat = ""
    for i, p in enumerate(parts):
        if i % 2 == 0:
            pat += re.escape(p)
        else:                               # 末个槽贪婪,其余非贪婪(最短优先)
            pat += "(.+)" if i == len(parts) - 2 else "(.+?)"
    return (parts[0].split()[0], keys, parts[0],
            re.compile("^" + pat + "$", re.IGNORECASE))


# 最长前缀优先:按前导字面量长度降序(`go to ` 必须排在任何 `go ` 之前)。
# sorted 稳定,同长度保持上表声明顺序。
ALF_RULES = sorted((_alf_compile(t) for t, _ln in ALF_TEMPLATES),
                   key=lambda r: -len(r[2]))
ALF_TOOLS = tuple(dict.fromkeys(r[0] for r in ALF_RULES))

# 生成侧解析用:只认这 13 个工具名开头的调用,与上表同源(不另立第二份名单)。
ALF_CALL = re.compile(
    r"\b(" + "|".join(sorted(ALF_TOOLS, key=len, reverse=True)) + r")\s*\(")


def alf_split(action):
    """ALFWorld 动作原文 -> (tool, [(键,值)], 落空原因)。

    切得动时 reason=None;切不动时返回 (None, [], 原因),**调用方必须计数**,
    绝不能静默换成别的口径(否则就退回被否掉的"首词=工具名"catch-all 切法)。

    原因三种:
      no_template  没有任何官方模板匹配(模型发了个不在 13 条模板里的串)
      empty_value  匹配上但某个槽是空白
      bad_char     值里含 ALF_BAD_CHARS(逗号/括号/引号)——留着会静默扣分
      odd_shape    值不是「类型名 + 空格 + 序号」(见 ALF_VALUE_RE),
                   多半是贪婪尾槽吞进了残句或标点
    """
    act = " ".join(str(action).split())      # 只做空白归一,不改大小写、不去标点
    if not act:
        return None, [], "no_template"
    for tool, keys, _lead, rx in ALF_RULES:
        m = rx.match(act)
        if not m:
            continue
        named = []
        for k, v in zip(keys, m.groups()):
            v = v.strip()
            if not v:
                return None, [], "empty_value"
            if any(c in v for c in ALF_BAD_CHARS):
                return None, [], "bad_char"
            if not ALF_VALUE_RE.fullmatch(v):
                return None, [], "odd_shape"
            named.append((k, v))
        return tool, named, None
    return None, [], "no_template"
