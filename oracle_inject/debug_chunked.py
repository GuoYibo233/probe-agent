import sys, torch
sys.path.insert(0, "/home/y-guo/reproduce/new1/oracle_inject")
import oracle_v1
import oracle_v2_variance as v2
from transformers import AutoModelForCausalLM, AutoTokenizer

tok = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-4B")
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3.5-4B", dtype=torch.bfloat16,
    device_map="cuda", attn_implementation="sdpa")
model.eval()
v2.DO_SAMPLE, v2.TEMPERATURE, v2.TOP_P = True, 0.6, 0.95
torch.manual_seed(1)
q = oracle_v1.build_questions(2, 7)[0]
msgs = [{"role":"system","content":v2.SYSTEM+v2.PERMIT},{"role":"user","content":q["question"]}]
ptext = tok.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=True, tokenize=False)
ids = tok(ptext, return_tensors="pt", add_special_tokens=False).input_ids.to(model.device)
ids2, text = v2.gen_until(model, tok, ids, lambda t: v2.CALL_RE.search(t) or v2.ANS_RE.search(t), 600)
print("gen:", ids2.shape[1]-ids.shape[1], "CALL:", bool(v2.CALL_RE.search(text)))
print(text[:800]); print("...TAIL..."); print(text[-500:])
