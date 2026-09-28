"""Qwen's tokenizer quirks, pad token, head attach point, LoRA target modules and restore/serving dtype."""
# venv: probe
from __future__ import annotations

DTYPE = "bfloat16"          # the restore/serving dtype; a row's result.dtype overrides at training
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]
HEAD_LAYER = "last_hidden_state"


def prepare_tokenizer(tok) -> None:
    """Set the pad token and this backbone's truncation/padding sides, in place."""
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"      # keep the tail of the thinking
    tok.padding_side = "right"        # every supervision position is a real token


# TODO(gyb, 2026-09-22): OPEN, to be discussed; the head may change afterwards. Nothing about
# the classification head can be set from a setting today. Three things are fixed in code: the
# head is one linear layer with no hidden layer (below); it reads the backbone's last layer
# (HEAD_LAYER above); and it reads the last token of the probe's text only
# (models/probe_models/base.py, the event_end position). If the discussion wants any of these
# varied, each becomes a field of the `probe` section in experimental_settings/schema.py whose
# default is today's behaviour, so no existing run directory goes stale (README section 3,
# recipe 3); a setting that states another value gets its own train key.
def attach_head(model, n_labels: int):
    """Build and attach the classification head reading the hidden state at HEAD_LAYER."""
    import torch

    hidden_size = model.config.get_text_config().hidden_size
    return torch.nn.Linear(hidden_size, n_labels, dtype=torch.float32)
