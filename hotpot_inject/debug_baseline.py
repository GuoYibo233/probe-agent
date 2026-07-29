"""Print baseline generation text for one hotpot question (diagnosis)."""
import importlib.util
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

spec = importlib.util.spec_from_file_location(
    "hotpot_v1", "/home/y-guo/reproduce/new1/hotpot_inject/hotpot_v1.py")
h = importlib.util.module_from_spec(spec)
sys.argv = ["x"]
spec.loader.exec_module(h)

tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-4B")
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen3.5-4B", dtype=torch.bfloat16, device_map="cuda",
    attn_implementation="sdpa")
model.eval()

qs = h.load_questions(2)
q = qs["comparison"][0]
print("Q:", q["question"], "| gold:", q["answer"])
msgs = [{"role": "system", "content": h.SYSTEM + h.PERMIT},
        {"role": "user", "content": q["question"]}]
ptext = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                enable_thinking=True, tokenize=False)
pids = tok(ptext, return_tensors="pt",
           add_special_tokens=False).input_ids.to(model.device)
ids, gen, hops, ans = h.run_episode(model, tok, pids, q, 2500)
text = tok.decode(ids[0, pids.shape[1]:], skip_special_tokens=False)
print("gen_tokens:", gen, "hops:", [x["call_tok"] for x in hops], "ans:", ans)
print("---- HEAD ----")
print(text[:1200])
print("---- TAIL ----")
print(text[-1500:])
