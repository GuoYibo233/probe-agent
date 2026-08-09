"""从原始 appworld 轨迹逐字重建 gpt-oss 当时看到的 harmony prompt。

为什么需要它:注入实验要在思考段中途截断、塞入工具结果、再让 vLLM 续写。
vLLM 的 chat 端点做不到这件事——它的模板永远只在末尾吐 `<|start|>assistant`,
且拒绝回灌带 `<|channel|>` 的历史消息(chat_template.jinja 会 raise)。所以必须
走 completions 端点,自己把 prompt 拼到"思考写到一半"那个位置。

口径来源(改任何一条都会让重建串与采集时不一致):
- SYSTEM / NO_CODE_MSG / 历史拼法: envs/collect/run_appworld.py:17-36, 85-107
- 采集参数 reasoning_effort=high: envs/runs/w0_aw_official/launch_clients.sh
- harmony 模板: 模型目录下 chat_template.jinja,由 apply_chat_template 套
- 环境返回在采集时已截到 4000 字符并原样写进日志,所以日志里的 result 与模型
  当时看到的逐字相同(run_appworld.py:104-107)

两道自检(都不需要 GPU):
- check_system_verbatim(): 回源文件比对 SYSTEM 常量,漂了就报错
- verify_traj(): 用日志里的 usage.in(服务端记的 prompt_tokens)对账重建后的
  token 数,逐步比

已知的两处不确定(verify_traj 会把它们分类计数,不要静默吞掉):
- Current date: 模板调 strftime_now 取当天日期,轨迹里没记。w0 这批采于
  2026-07-31,所以只在同一天重建才对得上;assert_date() 负责拦住跨日重建。
- 少数步的 assistant content 里混进了字面的 `<|...|>` 标记(模型自己吐出来的),
  重新 tokenize 时会被收成特殊 token,与服务端当时按普通文本算的不一致。
  has_literal_harmony() 负责把这些步标出来。
"""

import json
import re
from pathlib import Path

# 【照抄 envs/collect/run_appworld.py:17-36】check_system_verbatim() 保证不漂移
SYSTEM = """You are an autonomous agent operating a phone-like environment \
on behalf of your supervisor.

Rules:
- Each turn, write exactly ONE ```python ... ``` code block. It is executed \
in a persistent IPython shell and you ONLY see what is printed — always wrap \
calls whose result you need in print(...), e.g. \
print(apis.spotify.show_playlists(...))
- Call app APIs as: apis.{app_name}.{api_name}(...)
- Explore first: apis.api_docs.show_app_descriptions(), \
apis.api_docs.show_api_descriptions(app_name=...), \
apis.api_docs.show_api_doc(app_name=..., api_name=...)
- Your supervisor's identity: print(apis.supervisor.show_profile()) gives \
their email/phone; print(apis.supervisor.show_account_passwords()) gives \
their password for each app. NEVER guess usernames or passwords.
- Login pattern: token = apis.spotify.login(username=<supervisor email>, \
password=<password from the list>)["access_token"], then pass \
access_token=token to that app's other APIs.
- When the task is fully done, call apis.supervisor.complete_task() \
(pass answer=... if the task asks a question)."""

# 【照抄 run_appworld.py:98-100】没写代码块那一步,发给模型的是这一句,
# 而日志里写的是 result="NO_CODE_BLOCK"——两者不同,重放时必须换回来
NO_CODE_MSG = ("No ```python``` block found. Reply with "
               "exactly one python code block.")
NO_CODE_MARK = "NO_CODE_BLOCK"

# 采集时 gpt-oss 走 chat 端点 + reasoning_effort=high
REASONING_EFFORT = "high"

# harmony 里 analysis 通道的开头。apply_chat_template(add_generation_prompt=True)
# 只吐到 `<|start|>assistant` 为止,通道标记由模型自己生成,所以要我们手动接上
ANALYSIS_OPEN = "<|channel|>analysis<|message|>"

# w0_aw_official 这批的采集日期(文件 mtime 全落在 2026-07-31 06:02~08:14)
COLLECT_DATE = "2026-07-31"

_SRC = Path(__file__).resolve().parents[2] / "envs/collect/run_appworld.py"
_SYS_RE = re.compile(r'^SYSTEM = """(.*?)"""$', re.S | re.M)
_LITERAL_HARMONY = re.compile(r"<\|[a-z_]+\|>")
# 只有这两个完整串会让 chat_template.jinja:263-265 抛异常;单个 <|...|> 不会。
# has_literal_harmony() 比这宽得多(它标的是"token 数可能对不上"的步)。
_GUARD_STRS = ("<|channel|>analysis<|message|>", "<|channel|>final<|message|>")


def needs_guard_bypass(msgs):
    """这组 messages 是否会撞上模板的 <|channel|> 检查。"""
    return any(m.get("role") == "assistant"
               and any(g in (m.get("content") or "") for g in _GUARD_STRS)
               for m in msgs)


def check_system_verbatim(src=_SRC):
    """回源文件比对 SYSTEM 常量。采集脚本改了这里而本文件没跟着改 -> 报错。"""
    m = _SYS_RE.search(Path(src).read_text())
    if not m:
        raise RuntimeError(f"在 {src} 里找不到 SYSTEM 字面量")
    want = m.group(1).replace("\\\n", "")
    if want != SYSTEM:
        raise RuntimeError(
            f"SYSTEM 与采集脚本不一致,重建出来的 prompt 不是模型当时看到的。\n"
            f"源文件 {src} 长度={len(want)},本文件长度={len(SYSTEM)}")
    return True


def load_traj(path):
    """读一条轨迹 -> (meta, gens, envs, final)。gens/envs 按 step 建索引。"""
    recs = [json.loads(l) for l in open(path)]
    meta = recs[0]
    gens = {r["step"]: r for r in recs if r.get("type") == "gen"}
    envs = {r["step"]: r for r in recs if r.get("type") == "env"}
    final = next((r for r in recs if r.get("type") == "final"), None)
    return meta, gens, envs, final


def build_messages(meta, gens, envs, step):
    """重建模型在第 step 步发请求时的 messages(不含该步自己的输出)。

    【照抄 run_appworld.py:85-107】:
    - 首两条 = system + "Task from supervisor: {instruction}"
    - 每轮追加 assistant(只放 content,思考不回灌) + user(执行输出)
    - 没有代码块的那一轮,user 换成 NO_CODE_MSG
    历史是全量累积,不截断轮数。
    """
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": f"Task from supervisor: {meta['instruction']}"}]
    for j in sorted(k for k in gens if k < step):
        g, e = gens[j], envs.get(j)
        msgs.append({"role": "assistant", "content": g.get("content") or ""})
        if e is None:
            # 轨迹在这一步断了(采集中途挂掉),后面的重建无意义
            raise ValueError(f"step {j} 缺 env 记录,无法重建 step {step}")
        if e.get("action") is None or e.get("result") == NO_CODE_MARK:
            msgs.append({"role": "user", "content": NO_CODE_MSG})
        else:
            msgs.append({"role": "user",
                         "content": f"Execution output:\n{e['result']}"})
    return msgs


def build_prefix(tok, msgs, effort=REASONING_EFFORT, pin_date=COLLECT_DATE):
    """套 harmony 模板,返回到 `<|start|>assistant` 为止的 prompt 串。

    pin_date:模板第 202 行调 strftime_now 把**运行当天**的日期写进 prompt,
    所以跨日重建会静默产生与采集时不同的串。把它钉回采集日,重建才是逐字的。
    传 None 关掉(那就得靠 assert_date 拦)。

    占位符那一段:模板 263-265 行发现 assistant 的 content 里含完整的
    `<|channel|>analysis<|message|>` / `<|channel|>final<|message|>` 就 raise。
    但采集时 vLLM 服务端是原样渲染的——模型当时确实看到了那些字面标记
    (模型自己把控制标记当文本吐了出来)。所以这里拿占位符绕过检查、渲染完再
    换回原文,保证重建串与采集时逐字一致,而不是去改内容。
    """
    subs, safe = {}, []
    for i, m in enumerate(msgs):
        c = m.get("content") or ""
        if m.get("role") == "assistant" and any(g in c for g in _GUARD_STRS):
            key = f"\x00HARMONY{i}\x00"
            subs[key] = c
            safe.append({**m, "content": key})
        else:
            safe.append(m)
    s = tok.apply_chat_template(safe, tokenize=False,
                                add_generation_prompt=True,
                                reasoning_effort=effort)
    for k, v in subs.items():
        if k not in s:
            raise RuntimeError(f"占位符 {k!r} 渲染后不见了,换回原文会失败")
        s = s.replace(k, v)
    if pin_date:
        s, n = re.subn(r"(Current date: )\d{4}-\d{2}-\d{2}",
                       lambda m: m.group(1) + pin_date, s, count=1)
        if not n:
            raise RuntimeError("模板里没有 Current date 行,钉日期失败")
    # jinja 模板在 developer 正文后、<|end|> 前多塞一个 "\n\n"(模板 248 行,
    # 无 tools 分支);chat 端点的 harmony 渲染器与采集时的手拼串都没有它
    # (hcap 已验两者逐字相同)。只剥 developer 段末尾这一处,否则 /render 出的
    # prompt 与 chat 基线差 2 字符,贪心解码从第 0 步就分叉(z1 冒烟实测)。
    s = re.sub(r"(<\|start\|>developer<\|message\|>(?:(?!<\|end\|>).)*?)\n\n(<\|end\|>)",
               r"\1\2", s, count=1, flags=re.S)
    return s


def assert_date(prefix, expect=COLLECT_DATE):
    """模板把当天日期写死进 prompt。跨日重建会静默产生不同的串,这里拦住。"""
    m = re.search(r"Current date: (\d{4}-\d{2}-\d{2})", prefix)
    if not m:
        raise RuntimeError("重建串里找不到 Current date 行,模板可能变了")
    if m.group(1) != expect:
        raise RuntimeError(
            f"重建日期 {m.group(1)} != 采集日期 {expect}。harmony 模板用的是"
            f"运行当天的日期,跨日重建的 prompt 与采集时不一致。"
            f"要么改天跑,要么显式传 --assume-date 承认这处偏差。")
    return True


def has_literal_harmony(msgs):
    """messages 里是否混进了字面 harmony 标记(会让 token 数对不上)。"""
    return any(_LITERAL_HARMONY.search(m["content"] or "") for m in msgs)


def thinking_prefix(tok, prefix, think_cut, effort=REASONING_EFFORT):
    """拼到"思考写到一半"的完整 completions prompt。"""
    return prefix + ANALYSIS_OPEN + think_cut


def verify_traj(tok, path, max_steps=None):
    """用日志里的 usage.in 对账重建后的 token 数,返回逐步结果。

    usage.in 是服务端记的 prompt_tokens(envs/collect/common.py:88),是唯一
    能校验"重建串是否就是模型当时看到的串"的外部尺子。
    """
    meta, gens, envs, _ = load_traj(path)
    out = []
    for st in sorted(gens):
        if max_steps is not None and st >= max_steps:
            break
        want = (gens[st].get("usage") or {}).get("in")
        if want is None:
            continue
        try:
            msgs = build_messages(meta, gens, envs, st)
        except ValueError:
            break
        prefix = build_prefix(tok, msgs)
        got = len(tok.encode(prefix, add_special_tokens=False))
        out.append(dict(step=st, want=want, got=got, diff=got - want,
                        literal=has_literal_harmony(msgs)))
    return out
