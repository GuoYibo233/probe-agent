"""LoRA adapters: flags, wrapping, and merging shared by the three causal training scripts
(ctool/cgen/cparam).

The `--lora` family of flags, the seven-piece set of target modules, and the merge-and-save
approach for all three scripts come from this one module -- no copy is allowed anywhere else
(an isomorphic table is bound to drift, and that drift is silent).

**peft is a lazy dependency**: this module does not import peft at the top level; every peft
import lives inside a function body, and those functions are only called on the `--lora`
branch. When `--lora` isn't passed, neither this module nor the three training scripts touch
peft themselves.

⚠️ But the statement "peft isn't in the process" does not hold, and it isn't up to us: when
peft is installed in the environment, line 66 of transformers 5.14.1's `trainer_utils.py`
does `from peft import PeftModel`, and `get_linear_schedule_with_warmup`, which all three
scripts import, reaches that line through `optimization.py`. So once peft is installed in
cprobe-env, peft gets pulled into sys.modules even without passing `--lora` -- that's
transformers' own import chain, unrelated to this module's branching, and it doesn't change
any numbers.

**The save contract stays unchanged** is a hard constraint of this whole approach: LoRA
training does not save the adapter, it first calls `merge_and_unload` to fold the adapter
back into the base, then calls `save_pretrained` the same way each cell already does. So the
eval side needs zero changes -- the files under `best/` are item for item identical to what
full-parameter training saves.

**Why the merge needs a deep copy first**: `merge_and_unload()` unpacks in place (it adds the
lora weights into base_layer, then swaps lora.Linear back to nn.Linear), and the original
loses its adapter the instant this runs. Since all three scripts follow the pattern "after
each round of evaluation, save best by metric, then keep training the next round," the
original still has to keep training, so only a deep copy can be merged. The copy is freed
the moment it's done being used.
"""

# Qwen3's standard set of seven: four attention pieces + three MLP pieces
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                  "gate_proj", "up_proj", "down_proj"]

DEFAULT_RANK = 16
DEFAULT_ALPHA = 32
DEFAULT_DROPOUT = 0.05
DEFAULT_LR = 2e-4          # Replaces the full-parameter lr default when --lora is on


def add_args(ap):
    """Attach the `--lora` family to argparse (all three scripts share one set of names and defaults)."""
    g = ap.add_argument_group("LoRA")
    g.add_argument("--lora", action="store_true",
                   help="train the base model with LoRA (train only the adapter, merge back into the base before saving; "
                        "off by default = full-parameter fine-tuning, same behavior as before this flag set was added)")
    g.add_argument("--lora-rank", type=int, default=DEFAULT_RANK,
                   help=f"LoRA rank r (default {DEFAULT_RANK})")
    g.add_argument("--lora-alpha", type=int, default=DEFAULT_ALPHA,
                   help=f"LoRA scaling alpha (default {DEFAULT_ALPHA})")
    g.add_argument("--lora-dropout", type=float, default=DEFAULT_DROPOUT,
                   help=f"LoRA dropout (default {DEFAULT_DROPOUT})")
    g.add_argument("--lora-lr", type=float, default=DEFAULT_LR,
                   help=f"learning rate when --lora is on (default {DEFAULT_LR}); "
                        "if --lr is given explicitly on the command line, --lr takes precedence")


def resolve_lr(args, full_default):
    """Decide the learning rate: an explicit `--lr` wins first, then `--lora-lr` when `--lora`
    is on, then the full-parameter default last.

    The reason the three scripts' `--lr` default was changed to None is exactly to tell
    apart "not passed" from "passed a value that happens to equal the default" -- otherwise
    there would be no way to know whether to use `--lora-lr` when `--lora` is on.
    """
    if args.lr is not None:
        return args.lr
    return args.lora_lr if args.lora else full_default


def wrap(hf_model, args):
    """Inject a LoRA adapter into hf_model in place, return the peft wrapper (kept only for
    merging).

    `get_peft_model` injects **in place**: the seven classes of nn.Linear on the hf_model
    object itself are swapped for lora.Linear, and every non-adapter parameter is set to
    requires_grad=False. So the caller's original variable keeps working as before (forward
    / generate / config / gradient_checkpointing are all unchanged), and only saving switches
    to `save_merged()`. The returned wrapper has no purpose other than merging.
    """
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(
        r=args.lora_rank, lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=list(TARGET_MODULES), bias="none")
    return get_peft_model(hf_model, cfg)


def merged_copy(wrapped):
    """Deep-copy the peft wrapper, then `merge_and_unload`, and return the merged HF model.

    The original is untouched (it still needs to keep training); the returned copy is a
    plain HF model, and what `save_pretrained` writes out is item for item identical to
    what full-parameter training saves. The caller `del`s it after use -- normally that
    happens through `save_merged()`.
    """
    import copy
    return copy.deepcopy(wrapped).merge_and_unload()


def save_merged(wrapped, dest, dev):
    """Save the merged copy to dest, then discard it on the spot and return the GPU memory
    (the save entry point for all three scripts).

    The copy must be freed right inside this function: if the caller holds onto it across
    rounds, the next merge would leave three bases sitting in GPU memory at once (the
    original + the previous copy + the new copy), and a 4B model on a 48G card would blow
    up immediately.
    """
    merged = merged_copy(wrapped)
    merged.save_pretrained(dest)
    del merged
    if str(dev).startswith("cuda"):
        import torch
        torch.cuda.empty_cache()


def prepare_grad_ckpt(hf_model):
    """A necessary step for LoRA + gradient checkpointing: make the embedding output
    require_grad.

    When not a single input inside a checkpoint segment requires grad, the whole segment
    builds no graph, so LoRA parameters get no gradient, and **it raises no error** (full-
    parameter training never hits this, because the embedding itself is already trainable).

    transformers 5.14.1's `gradient_checkpointing_enable()` already calls this once on its
    own when main_input_name is input_ids (modeling_utils.py lines 3353-3361), so this is
    just an extra safety net; if the hook is already attached it is not attached again
    (attaching twice would drop the old hook's handle).
    """
    if getattr(hf_model, "_require_grads_hook", None) is not None:
        return
    if hasattr(hf_model, "enable_input_require_grads"):
        hf_model.enable_input_require_grads()


def opt_params(params, use_lora):
    """The parameter list that goes into the optimizer: with LoRA on, keep only the ones with
    requires_grad (the adapter + each cell's own head).

    With LoRA off, return as is, order unchanged -- AdamW's state is built in order, and
    changing the order amounts to running a different experiment.
    """
    ps = list(params)
    return [p for p in ps if p.requires_grad] if use_lora else ps


def meta_block(args, lr):
    """The "lora" block in meta.json; the caller doesn't write this key at all when `--lora` isn't on."""
    return dict(rank=args.lora_rank, alpha=args.lora_alpha,
                dropout=args.lora_dropout, lr=lr,
                target_modules=list(TARGET_MODULES))
