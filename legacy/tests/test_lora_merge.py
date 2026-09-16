"""Unit test for the LoRA save/load contract: merge immediately after wrapping the
adapter, and the weights must be item-for-item equal to the original base.

This guards the path in `pipeline/train/lora_util.py` where "merge_and_unload first,
then save_pretrained" runs after training finishes. LoRA's B matrix is zero-initialized,
so right after wrapping and before any training, the adapter's contribution to the
weights is always zero, and the merged model must be **item-for-item allclose** to the
original base. If this breaks, the merge step is wired wrong somewhere (e.g. the scaling
factor multiplied incorrectly, or merged into the wrong layer), and that kind of error
does not raise once written to disk -- the eval side loads it back just fine, only the
weights are broken.

A few other things are tested together:
- that all seven target modules were really swapped for LoRA layers (missing one does
  not raise, it just means that part of the base was never trained);
- that the merged copy is a deep copy, so the original still carries the adapter after
  merging and can keep training (all three scripts follow "save best, keep training the
  next round"; if the original were dismantled in place, the second round onward would
  be training a different model);
- that the weights written to disk and read back are still item-for-item allclose to
  the original base (the save entry point `save_merged`);
- that with gradient checkpointing on, the adapter really receives gradients (peft's
  classic trap: when no input in a checkpoint segment has require_grad, that whole
  segment never builds a graph, and gradients are all None without raising);
- flag defaults and the learning-rate precedence (explicit --lr > --lora-lr > the
  full-parameter default).

The model is a randomly initialized two-layer Qwen3 (built in memory, no reading from
disk, no download), runs in seconds on CPU.

How to run it (needs torch/transformers/peft, so use cprobe-env):
  cprobe-env/bin/python -m unittest tests.test_lora_merge -v
When the system python3 runs the full discover, this module skips entirely (no torch);
that does not count as a failure.
"""
import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

try:
    import torch
    import transformers
    from transformers import AutoModel, AutoModelForCausalLM
    import peft  # noqa: F401
    import lora_util
except ImportError as e:                      # The system python3 lacks torch/peft
    raise unittest.SkipTest(f"needs the cprobe-env interpreter (torch/transformers/peft): {e}")


SEED = 20260729          # The test fixture's own fixed seed; the training script switched to 42 from np821 onward, this test does not follow


def tiny_config():
    """A randomly initialized two-layer Qwen3: same family structure as the three base tiers, small enough to run in seconds on CPU."""
    return transformers.Qwen3Config(
        hidden_size=32, intermediate_size=64, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=8,
        vocab_size=64, max_position_embeddings=64, tie_word_embeddings=False)


def lora_args(rank=16, alpha=32, dropout=0.05, lr=2e-4, lora=True):
    """Fabricate an argparse result: these are exactly the fields the three training scripts pass to lora_util."""
    return argparse.Namespace(lora=lora, lora_rank=rank, lora_alpha=alpha,
                              lora_dropout=dropout, lora_lr=lr)


def snapshot(model):
    return {k: v.detach().clone() for k, v in model.state_dict().items()}


class TestLoraMerge(unittest.TestCase):
    """The merged-back weights must be item-for-item allclose to the original base (tested once for each of the two base types)."""

    def _roundtrip(self, model):
        before = snapshot(model)
        wrapped = lora_util.wrap(model, lora_args())
        merged = lora_util.merged_copy(wrapped)
        after = merged.state_dict()
        self.assertEqual(set(after), set(before),
                         "the merged state_dict key set changed -- the on-disk format is now a different shape")
        bad = [k for k in before
               if not torch.allclose(after[k], before[k], atol=1e-6, rtol=1e-5)]
        self.assertEqual(bad, [], f"these weights do not match the original backbone after merging: {bad[:5]}")
        return wrapped, merged

    def test_causal_lm_merge_equals_base(self):
        """The base cgen / cparam use: AutoModelForCausalLM."""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        model.eval()
        _wrapped, merged = self._roundtrip(model)
        self.assertIsInstance(merged, type(model))

    def test_base_model_merge_equals_base(self):
        """The base ctool uses: AutoModel (no language-model head, only outputs hidden states)."""
        torch.manual_seed(SEED)
        model = AutoModel.from_config(tiny_config())
        model.eval()
        _wrapped, merged = self._roundtrip(model)
        self.assertIsInstance(merged, type(model))

    def test_all_seven_target_modules_wrapped(self):
        """Not one of the seven target modules may be missed: whichever linear-layer type is missed never participates in training, and it does not raise."""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        lora_util.wrap(model, lora_args())
        hit = set()
        for name, mod in model.named_modules():
            if hasattr(mod, "lora_A"):
                hit.add(name.rsplit(".", 1)[-1])
        self.assertEqual(hit, set(lora_util.TARGET_MODULES))

    def test_only_adapters_trainable(self):
        """After wrapping, only the adapter remains trainable; the base is entirely frozen."""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        lora_util.wrap(model, lora_args())
        train = [n for n, p in model.named_parameters() if p.requires_grad]
        self.assertTrue(train, "not a single trainable parameter, LoRA was not wrapped on")
        self.assertTrue(all("lora_" in n for n in train),
                        f"these non-adapter parameters are still trainable: {[n for n in train if 'lora_' not in n][:5]}")
        # opt_params only collects the trainable batch
        picked = lora_util.opt_params(model.parameters(), True)
        self.assertEqual(len(picked), len(train))

    def test_original_keeps_adapters_after_merge(self):
        """Merging uses a deep-copied copy: the original still carries the adapter after merging, and can keep training."""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        wrapped = lora_util.wrap(model, lora_args())
        lora_util.merged_copy(wrapped)
        still = [n for n, _ in model.named_parameters() if "lora_" in n]
        self.assertTrue(still, "the original's adapter was torn off in place -- the second round of training is not the same model anymore")

    def test_save_merged_writes_base_equivalent_checkpoint(self):
        """The save entry point: weights written to disk and loaded back must be item-for-item allclose to the original base, and the original still carries the adapter."""
        import tempfile
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        before = snapshot(model)
        wrapped = lora_util.wrap(model, lora_args())
        with tempfile.TemporaryDirectory() as d:
            lora_util.save_merged(wrapped, Path(d) / "best", "cpu")
            back = AutoModelForCausalLM.from_pretrained(Path(d) / "best")
        after = back.state_dict()
        self.assertEqual(set(after), set(before))
        bad = [k for k in before
               if not torch.allclose(after[k], before[k], atol=1e-6, rtol=1e-5)]
        self.assertEqual(bad, [], f"reading it back from disk does not match the original backbone: {bad[:5]}")
        self.assertTrue([n for n, _ in model.named_parameters() if "lora_" in n],
                        "the original's adapter is gone after saving the checkpoint")

    def test_merge_reflects_trained_adapter(self):
        """Fill the B matrix with nonzero values; the merged weights must change accordingly -- proving the merge is really merging."""
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        before = snapshot(model)
        wrapped = lora_util.wrap(model, lora_args(rank=4, alpha=8))
        n_touched = 0
        with torch.no_grad():
            for _n, p in model.named_parameters():
                if "lora_B" in _n:
                    p.fill_(0.01)
                    n_touched += 1
        self.assertGreater(n_touched, 0)
        after = lora_util.merged_copy(wrapped).state_dict()
        moved = [k for k in before
                 if not torch.allclose(after[k], before[k], atol=1e-6, rtol=1e-5)]
        self.assertEqual(len(moved), n_touched,
                         "the number of weights changed by the adapter does not match the count of lora_B")


class TestLoraGradCkpt(unittest.TestCase):
    """LoRA + gradient checkpointing: the adapter must really receive gradients.

    This is peft's classic trap -- when not one input in a checkpoint segment has
    require_grad, that whole segment never builds a graph, the adapter's gradients are
    all None, and it **does not raise** -- it only shows up as the loss not moving.
    """

    def _grads(self, use_grad_ckpt):
        torch.manual_seed(SEED)
        model = AutoModelForCausalLM.from_config(tiny_config())
        lora_util.wrap(model, lora_args())
        if use_grad_ckpt:
            model.gradient_checkpointing_enable()
            model.config.use_cache = False
            lora_util.prepare_grad_ckpt(model)
        model.train()
        ids = torch.randint(0, 64, (2, 16))
        model(input_ids=ids, labels=ids).loss.backward()
        return {n: p.grad for n, p in model.named_parameters()
                if "lora_A" in n or "lora_B" in n}

    def test_adapters_get_gradients_with_grad_ckpt(self):
        g = self._grads(True)
        self.assertTrue(g, "not a single adapter parameter")
        none = [n for n, v in g.items() if v is None]
        self.assertEqual(none, [], f"these adapters got no gradient under gradient checkpointing: {none[:5]}")
        # At the first step, look only at lora_B: B is zero-initialized, so dL/dA is naturally
        # all zero at the first step, and only dL/dB being nonzero shows the gradient really
        # flowed into the adapter.
        zero = [n for n, v in g.items() if "lora_B" in n and not v.any()]
        self.assertEqual(zero, [], f"these lora_B gradients are all zero: {zero[:5]}")

    def test_adapters_get_gradients_without_grad_ckpt(self):
        g = self._grads(False)
        none = [n for n, v in g.items() if v is None]
        self.assertEqual(none, [], f"these adapters got no gradient: {none[:5]}")


class TestLoraFlags(unittest.TestCase):
    """Flags and the meta block: the three scripts share this one, defaults are hardcoded here."""

    def _parser(self):
        ap = argparse.ArgumentParser()
        ap.add_argument("--lr", type=float, default=None)
        lora_util.add_args(ap)
        return ap

    def test_defaults(self):
        a = self._parser().parse_args([])
        self.assertFalse(a.lora)
        self.assertEqual(a.lora_rank, 16)
        self.assertEqual(a.lora_alpha, 32)
        self.assertEqual(a.lora_dropout, 0.05)
        self.assertEqual(a.lora_lr, 2e-4)

    def test_lr_resolution(self):
        p = self._parser()
        # LoRA off, no --lr given: the full-parameter default
        self.assertEqual(lora_util.resolve_lr(p.parse_args([]), 1e-5), 1e-5)
        # LoRA on, no --lr given: falls back to --lora-lr
        self.assertEqual(
            lora_util.resolve_lr(p.parse_args(["--lora"]), 1e-5), 2e-4)
        # LoRA on but --lr given explicitly: the explicit value wins
        self.assertEqual(
            lora_util.resolve_lr(p.parse_args(["--lora", "--lr", "3e-5"]),
                                 1e-5), 3e-5)
        # LoRA on and --lora-lr changed
        self.assertEqual(
            lora_util.resolve_lr(p.parse_args(["--lora", "--lora-lr", "1e-3"]),
                                 1e-5), 1e-3)

    def test_meta_block(self):
        a = self._parser().parse_args(
            ["--lora", "--lora-rank", "8", "--lora-alpha", "64",
             "--lora-dropout", "0.1"])
        m = lora_util.meta_block(a, 2e-4)
        self.assertEqual(m, dict(rank=8, alpha=64, dropout=0.1, lr=2e-4,
                                 target_modules=lora_util.TARGET_MODULES))
        # The table in meta is a copy: changing it must not pollute the module constant
        m["target_modules"].append("mlp")
        self.assertEqual(len(lora_util.TARGET_MODULES), 7)

    def test_opt_params_passthrough_without_lora(self):
        """With LoRA off, the parameter table passes through unchanged, order preserved (AdamW's state is built in order)."""
        ps = [torch.nn.Parameter(torch.zeros(2)) for _ in range(3)]
        ps[1].requires_grad_(False)
        self.assertEqual(lora_util.opt_params(ps, False), ps)


if __name__ == "__main__":
    unittest.main()
