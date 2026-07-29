"""V2: when did the model internally commit to web_search (vs get_weather)?

Reuses the trajectory from tool_probe_v1_out.pt. Tracks the tokens that
distinguish the two candidate tools and renders an interactive slice page.
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
n_full = len(full_ids)


def tid(s: str) -> int:
    ids = tok.encode(s, add_special_tokens=False)
    return ids[0]


# tokens that discriminate the two tools + task concepts
targets = {
    " web": tid(" web"),
    "web": tid("web"),
    " search": tid(" search"),
    "_search": tid("_search"),
    " weather": tid(" weather"),
    "_weather": tid("_weather"),
    " forecast": tid(" forecast"),
    " Tokyo": tid(" Tokyo"),
}
print({k: (v, repr(tok.decode([v]))) for k, v in targets.items()})

lens_logits, model_logits, input_ids = lens.apply(model, full_text, max_seq_len=n_full + 8)
layers = sorted(lens_logits)[:-1]  # drop final layer (actual output)

# best (min) rank across mid layers, per position
print("\nper-position best lens rank across layers (generation region):")
hdr = "pos  emitted-tok    " + "".join(f"{k:>10}" for k in targets)
print(hdr)
best = {}
for name, t in targets.items():
    ranks = torch.stack(
        [(lens_logits[l] > lens_logits[l][:, t].unsqueeze(1)).sum(1) for l in layers]
    )  # [n_layers, n_pos]
    best[name] = ranks.min(0).values

for p in range(n_prompt, n_full):
    row = f"{p:<4} {repr(tok.decode([full_ids[p]]))[:14]:<15}"
    row += "".join(f"{best[k][p].item():>10}" for k in targets)
    print(row)

# interactive slice page over the generated region
pinned = set(targets.values())
sl = compute_slice(
    model, lens, full_text,
    pinned_token_ids=pinned,
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
print(f"\nwrote tool_probe_slice.html ({len(html)//1024} KiB)")
