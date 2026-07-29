"""Print sampled generation text for var-smoke diagnosis."""
import sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, "/home/y-guo/reproduce/new1/oracle_inject")
import oracle_v1

tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-4B")
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen3.5-4B", dtype=torch.bfloat16, device_map="cuda",
    attn_implementation="sdpa")
model.eval()
torch.manual_seed(1)

qs = oracle_v1.build_questions(2, 7)
for q in qs:
    msgs = [{"role": "system", "content": oracle_v1.SYSTEM + oracle_v1.PERMIT},
            {"role": "user", "content": q["question"]}]
    ptext = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                    enable_thinking=True, tokenize=False)
    ids = tok(ptext, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=400, do_sample=True,
                             temperature=0.6, top_p=0.95,
                             pad_token_id=tok.eos_token_id)
    text = tok.decode(out[0, ids.shape[1]:], skip_special_tokens=False)
    print("=" * 30, q["question"])
    print(text[:1500])
    print("CALL match:", bool(oracle_v1.CALL_RE.search(text)))
