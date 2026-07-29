"""Smoke test: one ALFWorld episode driven by Qwen3.5-4B via vLLM.

Measures per-episode wall clock, token usage, steps, success — the same
four metrics the Fig 1 pilot will track.
"""

import os
import re
import sys
import time

os.environ["ALFWORLD_DATA"] = "/home/y-guo/reproduce/new1/fig1_pilot/alfworld_data"

import yaml
from openai import OpenAI

import alfworld.agents.environment as environment

VLLM_URL = os.environ.get("VLLM_URL", "http://tokyo108:8712/v1")
MODEL = "Qwen/Qwen3.5-4B"
MAX_STEPS = 40

client = OpenAI(base_url=VLLM_URL, api_key="dummy")

config = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "base_config.yaml")))
env = environment.get_environment("AlfredTWEnv")(config, train_eval="train")
env = env.init_env(batch_size=1)

obs, info = env.reset()
task_obs = obs[0]
print("TASK:", task_obs.split("Your task is to:")[-1].strip()[:200])

SYSTEM = (
    "You are an agent in a household environment. At each turn you are given "
    "the current observation and the list of admissible commands. Reply with "
    "EXACTLY ONE command copied verbatim from the admissible list. No other text."
)

history = []
n_tokens_in = n_tokens_out = 0
t0 = time.time()
success = False

for step in range(MAX_STEPS):
    admissible = info["admissible_commands"][0]
    hist_txt = "\n".join(f"> {a}\n{o}" for a, o in history[-8:])
    user = (
        f"{task_obs}\n\n=== recent history ===\n{hist_txt}\n\n"
        f"=== admissible commands ===\n" + "\n".join(admissible) + "\n\nNext command:"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        max_tokens=2048,
        temperature=0.0,
    )
    n_tokens_in += resp.usage.prompt_tokens
    n_tokens_out += resp.usage.completion_tokens
    raw = resp.choices[0].message.content or ""
    # strip any thinking block, take last non-empty line
    txt = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    lines = [l.strip("` >") for l in txt.splitlines() if l.strip()]
    action = lines[-1] if lines else "look"
    if action not in admissible:
        # fuzzy: first admissible command contained in the reply
        matches = [a for a in admissible if a in txt]
        action = matches[0] if matches else "look"
    obs, scores, dones, info = env.step([action])
    o = obs[0]
    history.append((action, o[:300]))
    print(f"[{step:02d}] {action}  ->  {o[:80]!r}")
    if dones[0]:
        success = scores[0] > 0 or "You won" in o
        break

wall = time.time() - t0
print("\n=== EPISODE METRICS ===")
print(f"success={success} steps={len(history)} wall={wall:.1f}s "
      f"tokens_in={n_tokens_in} tokens_out={n_tokens_out}")
