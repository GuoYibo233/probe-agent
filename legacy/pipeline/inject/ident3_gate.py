"""ident3 pre-launch gate (stdlib, CPU): prove that the chat endpoint and
/render render **id-for-id identical** prompts for the same set of messages,
then allow the three arms to start.

Checks two things; if either fails, exit non-zero and the job script
refuses to run based on that:
1. vLLM service's date pin (VLLM_SYSTEM_START_DATE) matches /render's
   COLLECT_DATE -- if vLLM isn't pinned it falls back to today
   (harmony_utils.get_system_message falls back to datetime.now()), and the
   chat arm would diverge from the other two arms right at step 0 of every
   question, while all three arms would still run to completion, with no
   visible cause in the report.
2. The chat endpoint returns prompt_token_ids (return_token_ids in effect)
   and they are id-for-id equal to /render's -- this is the precondition
   for "the three arms are token-for-token identical," pinned once before
   launch.

Usage:
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
    ap.add_argument("--preset", default="default",
                    help="a set of generation settings from configs/presets/<name>.json; "
                         "the gate request's temperature is read from this preset's client section")
    a = ap.parse_args()
    # Sampling keys come from the preset's client section; temperature has only
    # this one source
    root = str(HERE.parents[1])
    if root not in sys.path:
        sys.path.append(root)
    from preset_loader import load_preset, require_temperature  # noqa: E402
    pre = load_preset(a.preset)
    temperature = require_temperature(pre["client"]["temperature"], pre["_name"])
    R.check_system_verbatim()
    msgs = [{"role": "system", "content": R.SYSTEM},
            {"role": "user", "content": "Task from supervisor: gate check."},
            {"role": "assistant", "content": "```python\nprint(1)\n```"},
            {"role": "user", "content": "Execution output:\n1\n"}]
    ren = post(a.probe_url.rstrip("/") + "/render",
               dict(messages=msgs, effort=a.effort))
    chat = post(a.base_url.rstrip("/") + "/chat/completions",
                dict(model=a.model, messages=msgs, max_tokens=1,
                     temperature=temperature, return_token_ids=True,
                     reasoning_effort=a.effort))
    pids = chat.get("prompt_token_ids")
    if pids is None:
        print("GATE FAIL: chat endpoint did not return prompt_token_ids (return_token_ids not taking effect?)")
        return 2
    rid = ren["prefix_ids"]
    if pids == rid:
        print(f"GATE OK: chat prompt_token_ids == /render prefix_ids "
              f"({len(rid)} ids; date pinned for {ren.get('n_tokens')} tokens, "
              f"render start_date={R.COLLECT_DATE})")
        return 0
    n = min(len(pids), len(rid))
    i = next((j for j in range(n) if pids[j] != rid[j]), n)
    dec = post(a.probe_url.rstrip("/") + "/decode",
               dict(ids=pids[max(0, i - 12): i + 12]))["text"]
    dec2 = post(a.probe_url.rstrip("/") + "/decode",
                dict(ids=rid[max(0, i - 12): i + 12]))["text"]
    print(f"GATE FAIL: chat prompt ids ({len(pids)}) != /render ({len(rid)}),"
          f" first mismatched position {i}\n  chat  : {dec!r}\n  render: {dec2!r}\n"
          f"  most likely vLLM did not pin VLLM_SYSTEM_START_DATE={R.COLLECT_DATE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
