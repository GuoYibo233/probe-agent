#!/usr/bin/env python3
"""Install the gpt_oss_chat handler into the bfcl venv and register the model; idempotent,
safe to rerun.

1. Copy gpt_oss_chat.py -> venv's model_handler/local_inference/
2. Append an "openai/gpt-oss-120b" registration block at the end of model_config.py (marked,
   so reruns skip it)
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = Path("/home/y-guo/reproduce/new1/envs/bfcl/venv/lib/python3.11/"
            "site-packages/bfcl_eval")
MARK = "# ---- new1 patch: gpt-oss-120b chat handler ----"

BLOCK = f'''

{MARK}
from bfcl_eval.model_handler.local_inference.gpt_oss_chat import GptOssChatHandler

MODEL_CONFIG_MAPPING["openai/gpt-oss-120b"] = ModelConfig(
    model_name="openai/gpt-oss-120b",
    display_name="gpt-oss-120b (Prompt, chat)",
    url="https://huggingface.co/openai/gpt-oss-120b",
    org="OpenAI",
    license="apache-2.0",
    model_handler=GptOssChatHandler,
    input_price=None,
    output_price=None,
    is_fc_model=False,
    underscore_to_dot=False,
)
'''


def main():
    dst = SITE / "model_handler" / "local_inference" / "gpt_oss_chat.py"
    shutil.copyfile(HERE / "gpt_oss_chat.py", dst)
    print("copied handler ->", dst)

    cfg = SITE / "constants" / "model_config.py"
    text = cfg.read_text()
    if MARK in text:
        print("model_config already patched, skip")
    else:
        cfg.write_text(text + BLOCK)
        print("patched", cfg)

    from importlib import invalidate_caches
    invalidate_caches()


if __name__ == "__main__":
    main()
