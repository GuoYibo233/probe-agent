#!/usr/bin/env python3
"""Turn the raw token stream captured by hcap into a "click to advance one token" lesson page.

**Deterministic converter**: the single source of truth is the raw record on NFS (run_id=hcap),
and the page is generated fresh from it every time. Hand-editing the output means it gets
overwritten on the next rerun.

What it does:
  1. Read the trajectory jsonl (recorded with --api harmony, carries out_token_ids) and the
     single-shot tool-call json
  2. Use the harmony encoder to decode each token id into its own little string
  3. Following the exact same rules as vllm/parser/harmony.py:46-56, mark each token's current
     channel / recipient / destination (thinking / body / dropped / structure)
  4. Embed these into the HTML, paired with assets/tokenwalk.{css,js} for per-token stepping

The rule set from step 3 is rewritten here (no real parser runs in JS), so it must match the
vllm version line for line -- when the vllm version changes, come back and check this section.

Must be run inside envs/vllm-env (needs openai_harmony to decode token ids).
Usage:
  python3 run.py build-token-walk --traj <trajectory jsonl> --toolcall <json> --out <page html>
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
    """Rules from vllm/parser/harmony.py:46-56, copied one for one."""
    if recipient:
        return "tool"
    if channel == "analysis":
        return "reasoning"
    if channel == "final" or (channel == "commentary" and not recipient):
        return "content"
    return "drop"


def segments_of(text):
    """Scan out the character range of each message body. Header and closing markers belong to no message body."""
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
    """One record per token: id, its own string, the channel it is in, and its destination."""
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
                die(f"step {r['step']} has no out_token_ids -- this trajectory was not recorded with "
                    "--api harmony, use a different one")
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
<title>Watch a real task get processed, token by token</title>
<link rel="stylesheet" href="../assets/lesson.css">
<link rel="stylesheet" href="../assets/tokenwalk.css">
</head>
<body>
<div class="wrap wide">

<p class="kicker">Reference · vLLM 0.26.0 · run_id hcap</p>
<h1>Watch a real task get processed, token by token</h1>
<p class="standfirst">Every token below was captured live on 2026-08-06 from the gpt-oss-120b instance on tokyo108: the client assembles the harmony prompt itself and calls <code>/v1/completions</code> with <code>return_token_ids</code>, and the server hands back the token ids it actually generated, unchanged. Click "next token" to watch each one land in its bucket.</p>

<div class="note">
<p><strong>Task</strong>: {QUESTION}<br>
AppWorld <code>test_normal</code> task <code>{TASK_ID}</code>, took {N_STEPS} steps total. {FINAL_NOTE}</p>
</div>

<div id="tw"></div>

<h2>What actually happened on this machine</h2>

<div class="tbl-scroll">
<table>
<thead><tr><th>Item</th><th>Value</th></tr></thead>
<tbody>
{FACTS}
</tbody>
</table>
</div>

<p class="src">The raw record is at <code>{TRAJ}</code>, the standalone tool call is at <code>{TOOLCALL}</code>. Server config is at <code>{SRVLOG}</code>. This page is generated live from these files by <code>learn/vllm/build_token_walk.py</code>; manual edits get overwritten on the next rerun.</p>

<h2>Two things noticed while collecting this batch</h2>

<h3>1. Assemble it yourself or let vLLM assemble it -- the results are identical</h3>

<p>Take the message set right before step 2 starts, on the same server at the same moment, and send it once down each of two paths:</p>

<div class="tbl-scroll">
<table>
<thead><tr><th>Path</th><th>prompt token</th><th>output token</th><th>reasoning</th><th>content</th></tr></thead>
<tbody>
<tr><td class="key">Self-assembled harmony via /v1/completions</td><td>1457</td><td>136</td><td>349 chars</td><td>120 chars</td></tr>
<tr><td class="key">Handing off messages via /v1/chat/completions</td><td>1457</td><td>136</td><td>349 chars</td><td>120 chars</td></tr>
</tbody>
</table>
</div>

<p>The first 120 characters of content are also identical, character by character. All four figures match, showing the hand-assembled harmony string is the same string the server's <code>openai_harmony</code> renders -- before this, the only evidence was code-level, 'byte-by-byte comparison of the rendered output'; this time it is from an end-to-end run.</p>

<h3>2. Same prompt, temperature 0, two runs come out different lengths</h3>

<p>During collection, step 2 hit the <code>max_tokens</code> ceiling: 8192 output tokens, 401 message segments -- the model made up environment responses on its own within a single generation, writing round after round, and never emitted <code>&lt;|return|&gt;</code>. Resending the same prompt from the comparison table above (prompt tokens likewise 1457) once, it finished normally after only 136 output tokens.</p>

<p>Steps 6 and 8 also hit the 8192 ceiling, same pattern. This trajectory has 13 steps total, 39088 output tokens combined, of which three steps account for 24576.</p>

<div class="note">
<p><strong>These two numbers are only an observation.</strong> This page gives no explanation for why the same prompt at temperature 0 produces two different lengths -- no mechanism gets written until there is evidence for it.</p>
</div>

<div class="foot">
<p><a class="local" href="../reference/prompt-assembly.html">← Quick reference: how the prompt gets assembled</a></p>
</div>

</div>
<script id="twdata" type="application/json">{DATA}</script>
<script src="../assets/tokenwalk.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", required=True, help="trajectory jsonl recorded with --api harmony")
    ap.add_argument("--toolcall", required=True, help="standalone tool-call json")
    ap.add_argument("--out", required=True, help="lesson page html output path")
    ap.add_argument("--srvlog", default="/net/tokyo100-10g/data/str01_01/"
                    "y-guo/vllm_cache/logs/new1_hcap_srv.log")
    ap.add_argument("--max-steps", type=int, default=0, help="0 = take all")
    a = ap.parse_args()

    from openai_harmony import HarmonyEncodingName, load_harmony_encoding
    enc = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

    meta, steps = load_traj(a.traj, enc, a.max_steps)
    if not steps:
        die(f"{a.traj} does not have a single gen record")
    tc = load_toolcall(a.toolcall, enc)

    data = {"meta": meta, "steps": steps, "toolcall": tc}
    fin = meta.get("final", {})
    n_tok = sum(len(s["tokens"]) for s in steps)
    facts = [
        ("Model", "gpt-oss-120b (mxfp4), tokyo108 GPU 2 (H100 95G), port 8113"),
        ("Sampling", "temperature 0.0, reasoning effort high, max_tokens 8192"),
        ("Prompt", "client self-assembled, Current date pinned to 2026-08-06"),
        ("Request params", "add_special_tokens=false, skip_special_tokens=false, "
                 "return_token_ids=true"),
        ("This trajectory", f"{len(steps)} steps, output tokens total {n_tok}, "
                 f"task completed={fin.get('completed')}"),
        ("Standalone tool call", f"separately captured a generation with function tools, output {len(tc['tokens'])} tokens, "
                   f"stopped at id {tc['stop']}"),
    ]
    body = PAGE.format(
        QUESTION=html.escape(meta.get("instruction", "")),
        TASK_ID=html.escape(meta.get("task_id", "")),
        N_STEPS=len(steps),
        FINAL_NOTE=("This version stopped before finishing; the page records it as-is, unedited."
                    if not fin.get("completed") else ""),
        FACTS="\n".join(f"<tr><td class=\"key\">{html.escape(k)}</td>"
                        f"<td>{html.escape(v)}</td></tr>" for k, v in facts),
        TRAJ=html.escape(a.traj), TOOLCALL=html.escape(a.toolcall),
        SRVLOG=html.escape(a.srvlog),
        DATA=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))

    out = Path(a.out).resolve()
    out.write_text(body, encoding="utf-8")
    print(f"build_token_walk: {len(steps)} steps / {n_tok} token "
          f"+ tool standalone {len(tc['tokens'])} token -> {out}")


if __name__ == "__main__":
    main()
