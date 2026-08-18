"""ident3 发射前门禁(stdlib,CPU):证明 chat 端点与 /render 对同一组消息渲出
**逐 id 相同**的 prompt,再放三臂开跑。

查的是两件事,任一不过就退出非零、作业脚本据此拒跑:
1. vLLM 服务的日期钉(VLLM_SYSTEM_START_DATE)与 /render 的 COLLECT_DATE 一致
   ——vLLM 没钉就用今天(harmony_utils.get_system_message 退回 datetime.now()),
   chat 臂会在每题第 0 步就与另两臂分叉,而三臂各自都能跑完,报告里看不出原因。
2. chat 端点回 prompt_token_ids(return_token_ids 生效)且与 /render 逐 id 相等
   ——这是"三臂逐 token 同"的前提,发射前钉一次。

用法:
  python3 pipeline/inject/ident3_gate.py --base-url http://tokyo108:8114/v1 \\
      --probe-url http://localhost:8795 [--model gpt-oss-120b] [--effort high]
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                            # noqa: E402


def post(url, payload, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--probe-url", required=True)
    ap.add_argument("--model", default="gpt-oss-120b")
    ap.add_argument("--effort", default="high")
    a = ap.parse_args()
    R.check_system_verbatim()
    msgs = [{"role": "system", "content": R.SYSTEM},
            {"role": "user", "content": "Task from supervisor: gate check."},
            {"role": "assistant", "content": "```python\nprint(1)\n```"},
            {"role": "user", "content": "Execution output:\n1\n"}]
    ren = post(a.probe_url.rstrip("/") + "/render",
               dict(messages=msgs, effort=a.effort))
    chat = post(a.base_url.rstrip("/") + "/chat/completions",
                dict(model=a.model, messages=msgs, max_tokens=1,
                     temperature=0.0, return_token_ids=True,
                     reasoning_effort=a.effort))
    pids = chat.get("prompt_token_ids")
    if pids is None:
        print("GATE FAIL: chat 端点没回 prompt_token_ids(return_token_ids 没生效?)")
        return 2
    rid = ren["prefix_ids"]
    if pids == rid:
        print(f"GATE OK: chat prompt_token_ids == /render prefix_ids "
              f"({len(rid)} ids;日期钉 {ren.get('n_tokens')} tokens, "
              f"render start_date={R.COLLECT_DATE})")
        return 0
    n = min(len(pids), len(rid))
    i = next((j for j in range(n) if pids[j] != rid[j]), n)
    dec = post(a.probe_url.rstrip("/") + "/decode",
               dict(ids=pids[max(0, i - 12): i + 12]))["text"]
    dec2 = post(a.probe_url.rstrip("/") + "/decode",
                dict(ids=rid[max(0, i - 12): i + 12]))["text"]
    print(f"GATE FAIL: chat prompt ids ({len(pids)}) != /render ({len(rid)}),"
          f" 首个不等位 {i}\n  chat  : {dec!r}\n  render: {dec2!r}\n"
          f"  多半是 vLLM 没钉 VLLM_SYSTEM_START_DATE={R.COLLECT_DATE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
