"""One-shot compatibility check for two causal-LM probe backbones (CPU, fp32).

Checks, per model:
  a) AutoTokenizer loads
  b) SequenceClassification model loads (num_labels=10)
  c) ~500-token English text forward -> logits shape
  d) prefill-vs-incremental alignment: one-shot forward vs 4-chunk forward with
     cache reuse; max abs diff of the last position must be fp32 noise (<1e-4).
     This validates "feed several tokens at once while the cache is non-empty"
     on the hybrid (conv + attention) LFM2 architecture.

Run with the cprobe-env interpreter:
  /home/y-guo/reproduce/new1/cprobe-env/bin/python envs/bert/check_causal_candidates.py
"""

import sys
import traceback

import torch
import transformers
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
from transformers.modeling_layers import GenericForSequenceClassification

MODELS = {
    "Qwen3-0.6B-Base": "/net/tokyo100-10g/data/str01_01/y-guo/models/Qwen3-0.6B-Base",
    "LFM2.5-350M-Base": "/net/tokyo100-10g/data/str01_01/y-guo/models/LFM2.5-350M-Base",
}

NUM_LABELS = 10
N_CHUNKS = 4
TOL = 1e-4
SEED = 0

PARAGRAPH = (
    "Large language models used as tool-calling agents spend most of their wall clock time "
    "waiting for external services to answer. A router that reads the hidden state of the "
    "decoder at an early layer can decide, well before the final token is emitted, whether "
    "the model is about to request a tool at all, and if so which one. Because the decision "
    "is made from an internal representation rather than from decoded text, the dispatcher "
    "can begin the network round trip speculatively and discard the result when the model "
    "turns out to want something else. The interesting question is not whether such a probe "
    "can be trained, which is easy, but how far down the stack the signal appears, how it "
    "behaves under distribution shift between benchmarks, and what the cost of a wrong guess "
    "actually is once the retry path is measured end to end. A second question concerns the "
    "backbone itself: a small causal model reused as a classifier must expose stable hidden "
    "states when a prefix has already been cached, otherwise every incremental step silently "
    "disagrees with a clean forward pass over the same text and the probe learns noise. "
)


def register_lfm2_sequence_classification():
    """LFM2 ships no official classification head; wrap the generic one.

    Mirrors the upstream Qwen3 pattern:
        class Qwen3ForSequenceClassification(GenericForSequenceClassification, Qwen3PreTrainedModel):
            pass
    """
    from transformers.models.lfm2.configuration_lfm2 import Lfm2Config
    from transformers.models.lfm2.modeling_lfm2 import Lfm2PreTrainedModel

    class Lfm2ForSequenceClassification(GenericForSequenceClassification, Lfm2PreTrainedModel):
        pass

    AutoModelForSequenceClassification.register(Lfm2Config, Lfm2ForSequenceClassification)

    # transformers>=5.x: _LazyAutoMapping.register() silently returns without
    # doing anything when the config class lives under `transformers.*` (a guard
    # against remote code hijacking native configs). Lfm2Config is native, so the
    # public register() call above is a no-op and AutoModelForSequenceClassification
    # would still raise "Unrecognized configuration class". Inject directly.
    mapping = AutoModelForSequenceClassification._model_mapping
    if Lfm2Config not in mapping:
        mapping._extra_content[Lfm2Config] = Lfm2ForSequenceClassification
        print("   (public register() was a no-op for a native config; "
              "injected into _model_mapping._extra_content)")
    assert Lfm2Config in mapping, "Lfm2Config still not in AutoModelForSequenceClassification mapping"
    return Lfm2ForSequenceClassification


def build_text(tok, target_tokens=500):
    text = PARAGRAPH
    while len(tok(text)["input_ids"]) < target_tokens:
        text = text + PARAGRAPH
    ids = tok(text)["input_ids"][:target_tokens]
    return tok.decode(ids), ids


def check_model(name, path):
    print("=" * 78)
    print(f"[{name}] {path}")
    print("=" * 78)
    res = {"tokenizer": False, "load": False, "forward": False, "align": False, "maxdiff": None}

    # ---- a) tokenizer -------------------------------------------------------
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    print(f"a) tokenizer OK: {type(tok).__name__} vocab={len(tok)} "
          f"pad_token_id={tok.pad_token_id} eos_token_id={tok.eos_token_id}")
    res["tokenizer"] = True

    # ---- b) model -----------------------------------------------------------
    cfg = AutoConfig.from_pretrained(path, num_labels=NUM_LABELS)
    # GenericForSequenceClassification pools the last non-pad token, which needs
    # config.pad_token_id to be defined.
    if cfg.get_text_config().pad_token_id is None:
        cfg.get_text_config().pad_token_id = tok.pad_token_id
        print(f"   (config.pad_token_id was None -> set to {tok.pad_token_id})")
    torch.manual_seed(SEED)
    model = AutoModelForSequenceClassification.from_pretrained(
        path, config=cfg, dtype=torch.float32
    )
    model.eval()
    n_par = sum(p.numel() for p in model.parameters())
    print(f"b) model OK: {type(model).__name__} params={n_par/1e6:.1f}M "
          f"dtype={next(model.parameters()).dtype} pad_token_id={model.config.get_text_config().pad_token_id}")
    res["load"] = True

    # ---- c) ~500 token forward ---------------------------------------------
    text, ids = build_text(tok, 500)
    input_ids = torch.tensor([ids], dtype=torch.long)
    attn = torch.ones_like(input_ids)
    with torch.no_grad():
        out_full = model(input_ids=input_ids, attention_mask=attn, use_cache=False,
                         output_hidden_states=True)
    print(f"c) forward OK: n_tokens={input_ids.shape[1]} logits={tuple(out_full.logits.shape)}")
    res["forward"] = True

    # ---- d) one-shot vs chunked-with-cache ---------------------------------
    h_full_last = out_full.hidden_states[-1][:, -1, :]  # [1, hidden]
    logits_full = out_full.logits                       # [1, num_labels]

    n = input_ids.shape[1]
    bounds = [round(n * i / N_CHUNKS) for i in range(N_CHUNKS + 1)]
    past = None
    h_inc_last = None
    logits_inc = None
    with torch.no_grad():
        for i in range(N_CHUNKS):
            s, e = bounds[i], bounds[i + 1]
            chunk = input_ids[:, s:e]
            out = model(
                input_ids=chunk,
                attention_mask=torch.ones((1, e), dtype=torch.long),
                past_key_values=past,
                use_cache=True,
                output_hidden_states=True,
            )
            past = out.past_key_values
            h_inc_last = out.hidden_states[-1][:, -1, :]
            logits_inc = out.logits
    chunk_sizes = [bounds[i + 1] - bounds[i] for i in range(N_CHUNKS)]

    d_h = (h_full_last - h_inc_last).abs().max().item()
    d_l = (logits_full - logits_inc).abs().max().item()
    ref = h_full_last.abs().max().item()
    ok = max(d_h, d_l) < TOL
    res["align"] = ok
    res["maxdiff"] = (d_h, d_l)
    print(f"d) alignment: chunks={chunk_sizes} (cache non-empty for chunks 2..{N_CHUNKS})")
    print(f"   last-position hidden max|diff| = {d_h:.3e}   (|h|max = {ref:.3f})")
    print(f"   pooled logits    max|diff| = {d_l:.3e}")
    print(f"   -> {'PASS' if ok else 'FAIL'} (tol {TOL})")

    if not ok:
        diagnose_chunking(model, tok)
    return res


def diagnose_chunking(model, tok):
    """Localise an alignment failure: is it cache reuse at all, or only
    multi-token chunks fed into a non-empty cache?"""
    print("   diagnostic sweep (short text):")
    ids = tok(PARAGRAPH)["input_ids"][:32]
    x = torch.tensor([ids], dtype=torch.long)
    n = x.shape[1]
    with torch.no_grad():
        h_ref = model(input_ids=x, attention_mask=torch.ones_like(x), use_cache=False,
                      output_hidden_states=True).hidden_states[-1]

    def run(splits, label):
        past, hs, s = None, [], 0
        with torch.no_grad():
            for sz in splits:
                e = s + sz
                o = model(input_ids=x[:, s:e],
                          attention_mask=torch.ones((1, e), dtype=torch.long),
                          past_key_values=past, use_cache=True, output_hidden_states=True)
                past = o.past_key_values
                hs.append(o.hidden_states[-1])
                s = e
        h = torch.cat(hs, dim=1)
        print(f"     {label:34s} last-pos {abs_max(h[:, -1] - h_ref[:, -1]):.3e}   "
              f"whole-seq {abs_max(h - h_ref):.3e}")

    run([n], "one shot, no cache reuse")
    run([n - 8] + [1] * 8, "prefill + 8 x 1-token decode")
    run([n - 8, 4, 4], "prefill + 2 chunks of 4")
    run([n - 8, 2, 2, 2, 2], "prefill + 4 chunks of 2")


def abs_max(t):
    return t.abs().max().item()


def main():
    print(f"python      : {sys.version.split()[0]}")
    print(f"torch       : {torch.__version__}")
    print(f"transformers: {transformers.__version__}")
    torch.set_grad_enabled(False)

    register_lfm2_sequence_classification()
    print("registered Lfm2ForSequenceClassification -> AutoModelForSequenceClassification\n")

    summary = {}
    for name, path in MODELS.items():
        try:
            summary[name] = check_model(name, path)
        except Exception:
            traceback.print_exc()
            summary[name] = {"error": True}
        print()

    print("=" * 78)
    print("SUMMARY")
    for name, r in summary.items():
        if r.get("error"):
            print(f"  {name}: ERROR")
            continue
        dh, dl = r["maxdiff"]
        print(f"  {name}: tok={r['tokenizer']} load={r['load']} fwd={r['forward']} "
              f"align={'PASS' if r['align'] else 'FAIL'} "
              f"(hidden {dh:.3e} / logits {dl:.3e})")
    bad = [k for k, r in summary.items() if r.get("error") or not r.get("align")]
    print("VERDICT:", "all candidates usable" if not bad else f"NOT usable: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
