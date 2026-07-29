"""V3: is the lens signal beatable by just reading the model's output logits?

For ' web' and ' search', compare at each position:
  - best rank across mid layers under the Jacobian lens
  - rank in the model's actual final-layer logits (next-token distribution)
Also re-render the slice page small (only pinned tokens tracked).
"""

import torch
import transformers

import jlens
from jlens.vis import build_page, compute_slice

MODEL_NAME = "Qwen/Qwen3.5-4B"
LENS_REPO = "neuronpedia/jacobian-lens"
LENS_FILE = "qwen3.5-4b/jlens/Salesforce-wikitext/Qwen3.5-4B_jacobian_lens_n1000.pt"
LENS_REVISION = "qwen-n1000"

d = torch.load("tool_probe_v1_out.pt", weights_only=False)
full_ids, n_prompt = d["full_ids"], d["n_prompt"]
n_full = len(full_ids)

tok = transformers.AutoTokenizer.from_pretrained(MODEL_NAME)
hf = transformers.AutoModelForCausalLM.from_pretrained(
    MODEL_NAME, dtype=torch.bfloat16
).cuda()
hf.eval()
model = jlens.from_hf(hf, tok)
lens = jlens.JacobianLens.from_pretrained(
    LENS_REPO, filename=LENS_FILE, revision=LENS_REVISION
)
full_text = tok.decode(full_ids)


def tid(s: str) -> int:
    return tok.encode(s, add_special_tokens=False)[0]


targets = {" web": tid(" web"), " search": tid(" search"), " weather": tid(" weather")}

lens_logits, model_logits, input_ids = lens.apply(model, full_text, max_seq_len=n_full + 8)
layers = sorted(lens_logits)[:-1]


def ranks(logits: torch.Tensor, t: int) -> torch.Tensor:
    return (logits > logits[:, t].unsqueeze(1)).sum(1)


# precompute rank tensors once per (source, token)
lens_best, out_rank = {}, {}
for name, t in targets.items():
    lens_best[name] = torch.stack([ranks(lens_logits[l], t) for l in layers]).min(0).values
    out_rank[name] = ranks(model_logits, t)

print("pos  emitted-tok      | lens-best(web) out(web) | lens-best(search) out(search)")
for p in range(n_prompt, min(n_full, 540)):
    row = f"{p:<4} {repr(tok.decode([full_ids[p]]))[:15]:<17}|"
    for name in (" web", " search"):
        row += f" {lens_best[name][p].item():>10} {out_rank[name][p].item():>8} |"
    print(row)

# small self-contained page
sl = compute_slice(
    model, lens, full_text,
    pinned_token_ids=set(targets.values()) | {tid(" Tokyo"), tid(" umbrella"), tid("<tool_call>")},
    max_tracked=0,
    top_n=8,
    last_n_tokens=n_full - n_prompt + 12,
    max_seq_len=n_full + 8,
    mask_display=True,
)
html, raw, payload = build_page(
    sl, full_text,
    title="Qwen3.5-4B tool-call trajectory under the Jacobian lens",
    description="Umbrella-in-Tokyo prompt; model deliberates get_weather vs "
                "web_search, then calls web_search. Pinned: tool/argument tokens.",
    mode="embed",
)
open("tool_probe_slice.html", "w").write(html)
print(f"wrote tool_probe_slice.html ({len(html)//1024} KiB)")
