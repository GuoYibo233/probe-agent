"""Minimal OpenAI-compatible chat server backed by HF transformers.

Plan B for machines whose driver can't run recent vLLM wheels. Serves
/v1/models and /v1/chat/completions (non-streaming, one request at a time).
Same port convention as the vLLM fleet, so fig1_run.py works unchanged.

Usage: python hf_server.py --model Qwen/Qwen3.5-4B --port 8712
"""

import argparse
import time

import torch
import transformers
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen/Qwen3.5-4B")
ap.add_argument("--port", type=int, default=8712)
args = ap.parse_args()

tok = transformers.AutoTokenizer.from_pretrained(args.model)
model = transformers.AutoModelForCausalLM.from_pretrained(
    args.model, dtype=torch.bfloat16, device_map="cuda"
)
model.eval()

app = FastAPI()


class ChatReq(BaseModel):
    model: str = ""
    messages: list
    max_tokens: int = 1024
    temperature: float = 0.0
    chat_template_kwargs: dict = {}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": args.model, "object": "model"}]}


@app.post("/v1/chat/completions")
def chat(req: ChatReq):
    enc = tok.apply_chat_template(
        req.messages, add_generation_prompt=True, return_tensors="pt",
        **req.chat_template_kwargs,
    )
    ids = enc["input_ids"] if not isinstance(enc, torch.Tensor) else enc
    ids = ids.to("cuda")
    n_in = ids.shape[1]
    t0 = time.time()
    with torch.inference_mode():
        out = model.generate(
            ids,
            max_new_tokens=req.max_tokens,
            do_sample=req.temperature > 0,
            temperature=req.temperature if req.temperature > 0 else None,
            pad_token_id=tok.eos_token_id,
        )
    gen = out[0, n_in:]
    text = tok.decode(gen, skip_special_tokens=True)
    return {
        "id": "chatcmpl-hf",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": args.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": n_in,
            "completion_tokens": int(gen.shape[0]),
            "total_tokens": n_in + int(gen.shape[0]),
            "wall_s": round(time.time() - t0, 2),
        },
    }


uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
