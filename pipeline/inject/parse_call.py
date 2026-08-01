"""从续写文本里切出一条完整的 apis 调用(纯标准库)。规格:
plans/2026-08-01-splice-impl-spec.md §D1

拼回实验里"模型有没有把调用写完"这件事没法用正则判——参数里带括号、带引号、
带转义的调用一抓一大把(`print(apis.phone.send_message(message="Hi :) (really)"))`),
正则只会在第一个 `)` 上收手。所以这里手写一遍括号配平:引号(单双、三引号)内的
括号不算数,反斜杠转义跳过下一个字符,`#` 之后到行尾算注释。

被 replay_inject.py(score 段 C2)与 extract_completed.py 共同 import,
所以这个文件只许依赖标准库:cprobe-env 与将来任何裸 python 都得 import 得动。

自测:python pipeline/inject/parse_call.py
"""

import re

# 调用起点。与 pipeline/annotate/rules.py 的 AW_CALL 逐字相同——工具名口径只有
# 一份,这里另写一条正则只是为了不依赖那个包,写法必须一致
CALL_START = re.compile(r"apis\.(\w+)\.(\w+)\(")

FENCE = "```"


def complete_call(text, start=0):
    """从 start 起找首条 apis 调用,括号配平到闭合。

    返回 (call_str, end_idx):call_str 是从 `apis.` 到配平右括号的裸调用串,
    end_idx 是右括号的**后一位**(可直接当下一次搜索的 start)。
    找不到调用起点、或到文末都没配平,返回 (None, None)。
    """
    s = text or ""
    m = CALL_START.search(s, start)
    if m is None:
        return None, None
    i, depth, quote = m.end() - 1, 0, None      # i 停在那个左括号上
    while i < len(s):
        c = s[i]
        if quote is not None:                   # 字符串里:只找收尾引号
            if c == "\\":
                i += 2                          # 转义吃掉下一个字符
                continue
            if s.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if c in "\"'":                          # 进字符串,三引号优先匹配
            quote = c * 3 if s.startswith(c * 3, i) else c
            i += len(quote)
            continue
        if c == "#":                            # 注释吃到行尾
            nl = s.find("\n", i)
            if nl < 0:
                return None, None
            i = nl + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return s[m.start():i + 1], i + 1
        i += 1
    return None, None


def call_at(text, pos):
    """text 的 pos 位置上**正好起头**的那条完整调用;那里不是调用起点就返回
    (None, None)。

    骨架臂要的是这个:骨架把 `apis.x.y` 钉死在已知位置上(拼进 prompt 那截的
    末尾就是工具名本身),模型接着写参数才算补完。按铁律骨架不带尾左括号,而
    CALL_START 要 `apis.x.y(` 才匹配 —— 模型不接着写 `(` 而是另起一行自己写
    一条调用时,complete_call 会一路搜到模型那条,于是骨架报成补完了、抽出来
    的也是模型自己那条。锚住位置才分得清"补完骨架"和"推翻骨架另写"。
    """
    call, end = complete_call(text, pos)
    if call is None or end - len(call) != pos:
        return None, None
    return call, end


def find_fence_close(text, start=0):
    """从 start 起找收尾围栏 ```,返回它的**后一位**;没有返回 None。

    只认三个反引号本身,不管开栏——调用方负责把 start 放在开栏之后
    (拼回实验里开栏 ```python 是我们自己塞进 prompt 的,不在续写里)。
    """
    j = (text or "").find(FENCE, start)
    return None if j < 0 else j + len(FENCE)


if __name__ == "__main__":
    cases = [
        # (文本, 期望 call_str)
        ("print(apis.venmo.login(username='a'))",
         "apis.venmo.login(username='a')"),
        # 引号内的括号不算数
        ('apis.phone.send_message(message="hi :) (really)")',
         'apis.phone.send_message(message="hi :) (really)")'),
        # 反斜杠转义的引号不收尾
        (r'apis.file_system.write(text="say \") here")',
         r'apis.file_system.write(text="say \") here")'),
        # 嵌套调用
        ("x = apis.a.b(c=apis.d.e(f=1), g=2)\nprint(x)",
         "apis.a.b(c=apis.d.e(f=1), g=2)"),
        # 三引号里的括号
        ('apis.a.b(t="""a ) b""", u=1)', 'apis.a.b(t="""a ) b""", u=1)'),
        # 注释里的右括号不收手
        ("apis.a.b(\n  x=1,  # )))\n  y=2)",
         "apis.a.b(\n  x=1,  # )))\n  y=2)"),
        # 未闭合
        ("print(apis.venmo.login(username='a'", None),
        # 骨架被截断在左括号之前(拼回实验的骨架形态)
        ("print(apis.venmo.login", None),
        # 根本没有调用
        ("just some thinking text", None),
    ]
    for txt, want in cases:
        got, end = complete_call(txt)
        assert got == want, f"complete_call({txt!r}) -> {got!r} 期望 {want!r}"
        if want is None:
            assert end is None, (txt, end)
        else:
            assert txt[end - len(want):end] == want, (txt, end)

    # start 偏移:跳过第一条,拿第二条
    two = "apis.a.b()\nprint(apis.c.d(x=1))"
    first, e1 = complete_call(two)
    assert first == "apis.a.b()", first
    second, _ = complete_call(two, e1)
    assert second == "apis.c.d(x=1)", second

    # 锚位:骨架 `print(apis.venmo.login` 的工具名起点在第 6 位
    sk = "print(apis.venmo.login"
    pos = len(sk) - len("apis.venmo.login")
    ok = sk + "(username='a'))\n```\n"
    assert call_at(ok, pos)[0] == "apis.venmo.login(username='a')"
    # 模型不补参数、另起一行自己写一条:那不叫骨架补完
    bad = sk + "\nWait, wrong.\nprint(apis.api_docs.show_api_doc('venmo'))"
    assert complete_call(bad)[0] == "apis.api_docs.show_api_doc('venmo')"
    assert call_at(bad, pos) == (None, None)
    # 骨架处没配平也不算补完
    assert call_at(sk + "(username='a'", pos) == (None, None)

    # 围栏
    assert find_fence_close("code```\ntail") == 7
    assert find_fence_close("no fence here") is None
    assert find_fence_close("```a```", 3) == 7

    print("parse_call 自测通过:%d 条 complete_call + 偏移 + 锚位 3 条 + 围栏 3 条"
          % len(cases))
