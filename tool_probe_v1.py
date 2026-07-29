"""V1 probe: does the Jacobian lens see an upcoming tool call before it is emitted?

Setup: Qwen3.5-4B with two tools (get_weather, web_search). Ask a question that
needs get_weather. The model thinks, then emits a <tool_call> JSON. We re-run
the full text through the lens and, for a handful of target tokens (the
<tool_call> marker, the tool name, the argument city), measure the earliest
generated position where each token enters the lens top-K at any mid layer —
compared with the position where it is actually emitted.
"""

import json

import torch
import transformers

import jlens

MODEL_NAME = "Qwen/Qwen3.5-4B"
LENS_REPO = "neuronpedia/jacobian-lens"
LENS_FILE = "qwen3.5-4b/jlens/Salesforce-wikitext/Qwen3.5-4B_jacobian_lens_n1000.pt"
LENS_REVISION = "qwen-n1000"
MAX_NEW_TOKENS = 700
TOP_K = 10

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name in English"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for up-to-date information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

QUESTION = (
    "I'm flying to Tokyo tomorrow morning and I can't decide whether to pack "
    "an umbrella. Think carefully about what information you need, then act."
)


def main() -> None:
    tok = transformers.AutoTokenizer.from_pretrained(MODEL_NAME)
    hf = transformers.AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, dtype=torch.bfloat16
    ).cuda()
    hf.eval()

    prompt = tok.apply_chat_template(
        [{"role": "user", "content": QUESTION}],
        tools=TOOLS,
        add_generation_prompt=True,
        tokenize=False,
    )
    prompt_ids = tok(prompt, return_tensors="pt").input_ids.cuda()
    print(f"prompt tokens: {prompt_ids.shape[1]}")

    with torch.no_grad():
        out = hf.generate(
            prompt_ids,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=None,
            top_p=None,
            top_k=None,
            pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0, prompt_ids.shape[1]:]
    gen_text = tok.decode(gen_ids)
    print("=== generation ===")
    print(gen_text)
    print("==================")

    full_ids = out[0].tolist()
    n_prompt = prompt_ids.shape[1]
    n_full = len(full_ids)
    if n_full > 1024:
        print(f"WARNING: {n_full} tokens, truncating analysis window")

    # --- lens ---
    model = jlens.from_hf(hf, tok)
    lens = jlens.JacobianLens.from_pretrained(
        LENS_REPO, filename=LENS_FILE, revision=LENS_REVISION
    )
    print(lens)

    full_text = tok.decode(full_ids)
    lens_logits, model_logits, input_ids = lens.apply(
        model, full_text, max_seq_len=n_full + 8
    )
    ids = input_ids[0].tolist()
    if ids != full_ids:
        print(f"NOTE: retokenization drift, {len(ids)} vs {n_full} tokens; "
              "aligning targets by re-searching in retokenized ids")
        n_prompt_new = None
        # locate generation start: find last assistant header
        hdr = tok.encode("<|im_start|>assistant", add_special_tokens=False)
        for i in range(len(ids) - len(hdr), -1, -1):
            if ids[i:i + len(hdr)] == hdr:
                n_prompt_new = i + len(hdr)
                break
        n_prompt = n_prompt_new if n_prompt_new is not None else n_prompt
        full_ids = ids

    # --- target tokens ---
    def first_tid(s: str) -> int:
        return tok.encode(s, add_special_tokens=False)[0]

    targets = {
        "<tool_call>": first_tid("<tool_call>"),
        "get_weather(first-tok)": first_tid("get_weather"),
        '"weather"-word': first_tid(" weather"),
        "Tokyo": first_tid(" Tokyo"),
        "umbrella": first_tid(" umbrella"),
    }
    print("target token ids:", {k: (v, tok.decode([v])) for k, v in targets.items()})

    # emission positions (first occurrence in the generated region)
    emit_pos = {}
    for name, tid in targets.items():
        emit_pos[name] = next(
            (p for p in range(n_prompt, len(full_ids)) if full_ids[p] == tid), None
        )

    # --- ranks per (layer, position) ---
    layers = sorted(lens_logits)
    n_pos = lens_logits[layers[0]].shape[0]
    gen_range = range(n_prompt, n_pos)

    results = {}
    for name, tid in targets.items():
        per_layer = {}
        for layer in layers:
            logits = lens_logits[layer]  # [n_pos, vocab]
            tgt = logits[:, tid]
            ranks = (logits > tgt.unsqueeze(1)).sum(dim=1)  # 0 = top-1
            per_layer[layer] = ranks
        results[name] = per_layer

    print(f"\ngeneration region: positions {n_prompt}..{n_pos - 1}")
    print(f"\n{'token':<22} {'emitted@':>9} {'first in-lens top-%d@' % TOP_K:>22} "
          f"{'lookahead':>10}  earliest layer")
    summary = {}
    for name, tid in targets.items():
        first_hit, first_layer = None, None
        for p in gen_range:
            for layer in layers[:-1]:  # exclude final layer (= actual output)
                if results[name][layer][p] < TOP_K:
                    first_hit, first_layer = p, layer
                    break
            if first_hit is not None:
                break
        e = emit_pos[name]
        look = (e - first_hit) if (e is not None and first_hit is not None) else None
        summary[name] = dict(emit=e, first_hit=first_hit, layer=first_layer, lookahead=look)
        print(f"{name:<22} {str(e):>9} {str(first_hit):>22} {str(look):>10}  {first_layer}")

    # rank trajectory of the tool-name token at a few layers, over thinking region
    print("\nrank of get_weather first-token across generated positions (sample layers):")
    sample_layers = [l for l in layers[:-1]][:: max(1, len(layers) // 6)][:6]
    name = "get_weather(first-tok)"
    header = "pos  tok           " + "".join(f"L{l:<7}" for l in sample_layers)
    print(header)
    e = emit_pos[name] or (n_pos - 1)
    for p in range(n_prompt, min(e + 2, n_pos)):
        row = f"{p:<4} {tok.decode([full_ids[p]])[:12]:<13} "
        row += "".join(f"{results[name][l][p].item():<8}" for l in sample_layers)
        print(row)

    torch.save(
        dict(full_ids=full_ids, n_prompt=n_prompt, summary=summary,
             targets=targets, gen_text=gen_text),
        "tool_probe_v1_out.pt",
    )
    print("\nsaved tool_probe_v1_out.pt")


if __name__ == "__main__":
    main()
