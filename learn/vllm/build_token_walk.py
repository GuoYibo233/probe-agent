#!/usr/bin/env python3
"""把 hcap 抓到的原始 token 流转成"点一下前进一个 token"的课页。

**确定性转换器**:唯一真源是 NFS 上的原始记录(run_id=hcap),页面每次由它
现生成。手改产物 = 下次重跑被覆盖。

它做的事:
  1. 读轨迹 jsonl(--api harmony 录的,带 out_token_ids)与工具调用单发 json
  2. 用 harmony 编码器把每个 token id 解成它自己的那一小段字符串
  3. 按 vllm/parser/harmony.py:46-56 的同一套规则,逐 token 标出
     当前频道 / 收件人 / 这个 token 的去向(思考/正文/丢掉/结构)
  4. 把这些嵌进 HTML,配 assets/tokenwalk.{css,js} 做逐 token 步进

第 3 步那套规则在这里重写了一遍(JS 里不跑真解析器),所以它必须和
vllm 那份逐条对上——改 vllm 版本时要回头核这一段。

要在 envs/vllm-env 里跑(需要 openai_harmony 解码 token id)。
用法:
  python3 run.py build-token-walk --traj <轨迹jsonl> --toolcall <json> --out <页面html>
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

HEAD_RE = re.compile(
    r"<\|channel\|>(?P<channel>[^\s<]+)"
    r"(?:\s+to=(?P<recipient>[^\s<]+))?"
    r"(?:\s*<\|constrain\|>(?P<ctype>[^\s<]+))?"
    r"\s*<\|message\|>")
CLOSERS = ("<|end|>", "<|return|>", "<|call|>")


def die(msg, code=2):
    print(f"build_token_walk: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def bucket_of(channel, recipient):
    """vllm/parser/harmony.py:46-56 的规则,逐条照搬。"""
    if recipient:
        return "tool"
    if channel == "analysis":
        return "reasoning"
    if channel == "final" or (channel == "commentary" and not recipient):
        return "content"
    return "drop"


def segments_of(text):
    """扫出每段消息体的字符区间。头部与收尾标记不属于任何消息体。"""
    segs = []
    pos = 0
    while True:
        m = HEAD_RE.search(text, pos)
        if not m:
            break
        start = m.end()
        end, closer = len(text), ""
        for tok in CLOSERS:
            i = text.find(tok, start)
            if i != -1 and i < end:
                end, closer = i, tok
        segs.append({"start": start, "end": end,
                     "channel": m.group("channel"),
                     "recipient": m.group("recipient"),
                     "constrain": m.group("ctype"),
                     "closer": closer})
        pos = end + len(closer) if closer else end
        if not closer:
            break
    return segs


def walk(token_ids, enc):
    """每个 token 一条记录:id、它自己那段字符串、所在频道、去向。"""
    pieces = [enc.decode([tid]) for tid in token_ids]
    text = "".join(pieces)
    segs = segments_of(text)
    out, cur = [], 0
    for tid, s in zip(token_ids, pieces):
        lo = cur
        cur += len(s)
        seg = next((g for g in segs if g["start"] <= lo < g["end"]), None)
        if seg is None:
            channel, recipient, bucket = None, None, "frame"
        else:
            channel, recipient = seg["channel"], seg["recipient"]
            bucket = bucket_of(channel, recipient)
        out.append({"id": tid, "s": s, "ch": channel,
                    "rcp": recipient, "b": bucket})
    return out, text, segs


def load_traj(path, enc, max_steps):
    steps, meta = [], {}
    for line in Path(path).read_text().splitlines():
        r = json.loads(line)
        if r["type"] == "meta":
            meta = r
        elif r["type"] == "gen":
            if not r.get("out_token_ids"):
                die(f"第 {r['step']} 步没有 out_token_ids —— 这条轨迹不是 "
                    "--api harmony 录的,换一条")
            toks, text, segs = walk(r["out_token_ids"], enc)
            steps.append({
                "step": r["step"], "tokens": toks, "text": text,
                "n_prompt": len(r["prompt_token_ids"] or []),
                "prompt_tail": (r.get("prompt_text") or "")[-260:],
                "finish": r.get("finish_reason"),
                "stop": r.get("stop_reason"),
                "usage": r["usage"], "wall_s": r.get("wall_s"),
                "segs": [{k: g[k] for k in
                          ("channel", "recipient", "constrain", "closer")}
                         for g in segs],
            })
        elif r["type"] == "env":
            if steps and steps[-1]["step"] == r["step"]:
                steps[-1]["env"] = (r.get("result") or "")[:900]
                steps[-1]["action"] = (r.get("action") or "")[:900]
        elif r["type"] == "final":
            meta["final"] = r
    if max_steps:
        steps = steps[:max_steps]
    return meta, steps


def load_toolcall(path, enc):
    d = json.loads(Path(path).read_text())
    toks, text, segs = walk(d["out_token_ids"], enc)
    return {"step": "tool", "tokens": toks, "text": text,
            "n_prompt": len(d["prompt_token_ids"] or []),
            "prompt_tail": d["prompt_text"][-260:],
            "finish": d.get("finish_reason"), "stop": d.get("stop_reason"),
            "usage": {"in": d["usage"]["prompt_tokens"],
                      "out": d["usage"]["completion_tokens"]},
            "question": d["question"], "tool_names": d["tool_names"],
            "segs": [{k: g[k] for k in
                      ("channel", "recipient", "constrain", "closer")}
                     for g in segs]}


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>逐 token 看一个真实任务被处理</title>
<link rel="stylesheet" href="../assets/lesson.css">
<link rel="stylesheet" href="../assets/tokenwalk.css">
</head>
<body>
<div class="wrap wide">

<p class="kicker">Reference · vLLM 0.26.0 · run_id hcap</p>
<h1>逐 token 看一个真实任务被处理</h1>
<p class="standfirst">下面每一个 token 都是 2026-08-06 从 tokyo108 那台 gpt-oss-120b 上现抓的：客户端自己拼 harmony 提示词走 <code>/v1/completions</code>，带 <code>return_token_ids</code>，服务端把真实生成的 token id 原样交回来。点「下一个 token」，看它一个一个落进哪个桶。</p>

<div class="note">
<p><strong>题目</strong>：{QUESTION}<br>
AppWorld <code>test_normal</code> 任务 <code>{TASK_ID}</code>，一共走了 {N_STEPS} 步。{FINAL_NOTE}</p>
</div>

<div id="tw"></div>

<h2>这台机器上真实发生的事</h2>

<div class="tbl-scroll">
<table>
<thead><tr><th>项</th><th>值</th></tr></thead>
<tbody>
{FACTS}
</tbody>
</table>
</div>

<p class="src">原始记录在 <code>{TRAJ}</code>，工具调用单发在 <code>{TOOLCALL}</code>。服务端配置见 <code>{SRVLOG}</code>。本页由 <code>learn/vllm/build_token_walk.py</code> 从这些文件现生成，手改会被下次重跑覆盖。</p>

<h2>抓这批数据时撞见的两件事</h2>

<h3>一、自己拼和让 vLLM 拼，结果一模一样</h3>

<p>拿第 2 步开跑前那一组消息，同一台服务、同一个时刻，两条路各发一次：</p>

<div class="tbl-scroll">
<table>
<thead><tr><th>路径</th><th>prompt token</th><th>输出 token</th><th>reasoning</th><th>content</th></tr></thead>
<tbody>
<tr><td class="key">自拼 harmony 走 /v1/completions</td><td>1457</td><td>136</td><td>349 字</td><td>120 字</td></tr>
<tr><td class="key">交 messages 走 /v1/chat/completions</td><td>1457</td><td>136</td><td>349 字</td><td>120 字</td></tr>
</tbody>
</table>
</div>

<p>content 的前 120 个字符也逐字相同。四项全等，说明手拼那份 harmony 串和服务端 <code>openai_harmony</code> 渲出来的是同一串——之前只有"逐字节比对渲染结果"这一条代码层证据，这次是端到端跑出来的。</p>

<h3>二、同一个 prompt、temperature 0，两次跑出来不一样长</h3>

<p>采集时第 2 步撞了 <code>max_tokens</code> 上限：8192 个输出 token，401 段消息，模型在一次生成里自己编环境返回、一轮接一轮往下写，始终没吐 <code>&lt;|return|&gt;</code>。上面那张对照表里同一个 prompt（prompt token 同为 1457）重发一次，只有 136 个输出 token 就正常收尾了。</p>

<p>第 6 步和第 8 步也是 8192 撞顶，形态一样。这条轨迹一共 13 步、输出 token 合计 39088，其中三步占了 24576。</p>

<div class="note">
<p><strong>这两个数只是观测。</strong>为什么同一个 prompt 在 temperature 0 下会跑出两种长度，本页不给解释——没查到证据之前不写机制。</p>
</div>

<div class="foot">
<p><a class="local" href="../reference/prompt-assembly.html">← 速查卡：prompt 是怎么拼出来的</a></p>
</div>

</div>
<script id="twdata" type="application/json">{DATA}</script>
<script src="../assets/tokenwalk.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True, help="--api harmony 录的轨迹 jsonl")
    ap.add_argument("--toolcall", required=True, help="工具调用单发 json")
    ap.add_argument("--out", required=True, help="课页 html 输出路径")
    ap.add_argument("--srvlog", default="/net/tokyo100-10g/data/str01_01/"
                    "y-guo/vllm_cache/logs/new1_hcap_srv.log")
    ap.add_argument("--max-steps", type=int, default=0, help="0 = 全要")
    a = ap.parse_args()

    from openai_harmony import HarmonyEncodingName, load_harmony_encoding
    enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

    meta, steps = load_traj(a.traj, enc, a.max_steps)
    if not steps:
        die(f"{a.traj} 里一个 gen 记录都没有")
    tc = load_toolcall(a.toolcall, enc)

    data = {"meta": meta, "steps": steps, "toolcall": tc}
    fin = meta.get("final", {})
    n_tok = sum(len(s["tokens"]) for s in steps)
    facts = [
        ("模型", "gpt-oss-120b (mxfp4)，tokyo108 GPU 2 (H100 95G)，端口 8113"),
        ("采样", "temperature 0.0，reasoning effort high，max_tokens 8192"),
        ("提示词", "客户端自拼，Current date 钉死 2026-08-06"),
        ("请求参数", "add_special_tokens=false，skip_special_tokens=false，"
                 "return_token_ids=true"),
        ("这条轨迹", f"{len(steps)} 步，输出 token 合计 {n_tok}，"
                 f"任务完成={fin.get('completed')}"),
        ("工具调用单发", f"另抓一条带函数工具的生成，输出 {len(tc['tokens'])} 个 token，"
                   f"停在 id {tc['stop']}"),
    ]
    body = PAGE.format(
        QUESTION=html.escape(meta.get("instruction", "")),
        TASK_ID=html.escape(meta.get("task_id", "")),
        N_STEPS=len(steps),
        FINAL_NOTE=("这一版没做完就停了，页面照录不改。"
                    if not fin.get("completed") else ""),
        FACTS="\n".join(f"<tr><td class=\"key\">{html.escape(k)}</td>"
                        f"<td>{html.escape(v)}</td></tr>" for k, v in facts),
        TRAJ=html.escape(a.traj), TOOLCALL=html.escape(a.toolcall),
        SRVLOG=html.escape(a.srvlog),
        DATA=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))

    out = Path(a.out).resolve()
    out.write_text(body, encoding="utf-8")
    print(f"build_token_walk: {len(steps)} 步 / {n_tok} token "
          f"+ 工具单发 {len(tc['tokens'])} token -> {out}")


if __name__ == "__main__":
    main()
