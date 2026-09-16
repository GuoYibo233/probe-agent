"""Acceptance tests for the preset line (the redesign spec is at .scratch/gen-preset/spec.md).

Three presets are active: `default` is the one generation setting for the whole
line, and every entry's `--preset` defaults to it; `gptoss_default` is OpenAI's
official recommended setting; `gptoss_bfcl_high` is the BFCL line's setting.
This pins down four things: the presets and the model table are themselves valid;
`default`'s client section and server section match item by item; every entry's
`--preset` defaults to `default`; a sampling key written in a preset's client
section flows into the request body.
Temperature has exactly one source, the preset file, so every assertion below
reads back the value from the preset file.
"""
import ast
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import preset_loader as PL  # noqa: E402
from model_registry import resolve  # noqa: E402

APPWORLD_PY = ROOT / "envs/appworld/venv/bin/python"

# Every entry that takes --preset. Defaults are read straight from the source: the
# collector and splice_replay each need a dedicated venv to import, so reading the
# source works on any machine.
PRESET_ENTRYPOINTS = [
    "envs/collect/run_appworld.py",
    "envs/collect/run_alfworld.py",
    "envs/collect/run_tales.py",
    "envs/collect/run_tau2.py",
    "pipeline/inject/live_appworld.py",
    "pipeline/inject/replay_inject.py",
    "pipeline/inject/splice_replay.py",
    "pipeline/inject/ident3_gate.py",
]


def _preset_arg_defaults(rel_path):
    """Table every `--preset` argparse default in the source, in the order they appear.
    A file with N subcommands has N entries (replay_inject's run is one of them);
    the whole table is asserted together, so a second occurrence added later is
    still pinned down."""
    tree = ast.parse((ROOT / rel_path).read_text())
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "--preset"):
            for kw in node.keywords:
                if kw.arg == "default":
                    out.append(ast.literal_eval(kw.value))
    return out


INJECT_DIR = ROOT / "pipeline/inject"


def _import_inject(name):
    """live_appworld/replay_inject import same-directory modules from each other, so this goes through sys.path."""
    if str(INJECT_DIR) not in sys.path:
        sys.path.insert(0, str(INJECT_DIR))
    import importlib
    return importlib.import_module(name)


class TestModelsJson(unittest.TestCase):
    def test_resolve_unchanged_after_migration(self):
        # Before and after moving into configs/models.json, the resolve result must not change by a single character
        self.assertEqual(
            resolve("gpt-oss-120b"),
            "/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b")
        self.assertEqual(
            resolve("qwen3.6"),
            "/net/tokyo100-10g/data/str01_01/zhou-y/models/Qwen3.6-27B")

    def test_every_entry_has_path_and_note(self):
        m = PL.load_models()
        for k, v in m["models"].items():
            self.assertTrue(v.get("path"), k)
            self.assertTrue(v.get("note"), k)
        for alias, tgt in m["aliases"].items():
            self.assertIn(tgt, m["models"], alias)


class TestPresetsValidate(unittest.TestCase):
    def test_all_presets_pass(self):
        for name in PL.list_presets():
            p = json.loads((PL.PRESET_DIR / f"{name}.json").read_text())
            self.assertEqual(PL.validate(p), [], name)

    def test_unknown_key_rejected(self):
        p = {"model": "gpt-oss-120b", "client": {"tempreature": 0.5}}
        self.assertTrue(any("unknown key" in e for e in PL.validate(p)))

    def test_unknown_model_rejected(self):
        p = {"model": "no-such-model"}
        self.assertTrue(any("not in models.json" in e for e in PL.validate(p)))


class TestMergePrecedence(unittest.TestCase):
    FB = {"api": "raw", "reasoning_effort": None}

    def test_cli_beats_preset(self):
        out = PL.merge_client({"api": "chat", "reasoning_effort": "low"},
                              {"api": "harmony", "reasoning_effort": "high"},
                              self.FB)
        self.assertEqual(out["api"], "chat")
        self.assertEqual(out["reasoning_effort"], "low")

    def test_preset_beats_fallback(self):
        out = PL.merge_client({"api": None, "reasoning_effort": None},
                              {"api": "chat", "reasoning_effort": "high"},
                              self.FB)
        self.assertEqual(out["api"], "chat")
        self.assertEqual(out["reasoning_effort"], "high")

    def test_fallback_when_both_absent(self):
        out = PL.merge_client({"api": None, "reasoning_effort": None},
                              None, self.FB)
        self.assertEqual(out["api"], "raw")
        self.assertIsNone(out["reasoning_effort"])

    def test_preset_null_falls_through(self):
        # null in a preset means unspecified, so it falls back -- it must not overwrite to None
        out = PL.merge_client({"max_tokens": None}, {"max_tokens": None},
                              {"max_tokens": 8192})
        self.assertEqual(out["max_tokens"], 8192)

    def test_cli_beats_preset_on_sampling_key(self):
        # Every entry attaches temperature on the cli side: an explicit command-line value overrides the preset
        pre = PL.load_preset("default")["client"]
        out = PL.merge_client({"temperature": 0.25}, pre, {})
        self.assertEqual(out["temperature"], 0.25)


class TestDefaultPreset(unittest.TestCase):
    """`default` is the only active setting: the client section's sampling profile plus
    the server section's serving parameters -- both sections are pinned down here
    item by item (the server section is copied from envs/runs/nyapass/launch_servers.py)."""

    def test_loads_and_validates(self):
        # load_preset already calls validate internally and raises on failure; here we
        # explicitly validate the raw json again (without the _name/_path load_preset
        # adds afterward), the same check as TestPresetsValidate.test_all_presets_pass
        PL.load_preset("default")   # No raise means validation passes
        raw = json.loads((PL.PRESET_DIR / "default.json").read_text())
        self.assertEqual(PL.validate(raw), [])

    def test_client_fields(self):
        pre = PL.load_preset("default")
        self.assertEqual(pre["model"], "gpt-oss-120b")
        c = pre["client"]
        self.assertEqual(
            (c["api"], c["reasoning_effort"], c["temperature"], c["top_p"],
             c["max_tokens"], c["stop"], c["start_date"], c["seed"]),
            ("harmony", "high", 1.0, 1.0, 8192, None, "2026-08-06", None))

    def test_server_fields(self):
        srv = PL.load_preset("default")["server"]
        self.assertEqual(
            (srv["host"], srv["port"], srv["served_model_name"],
             srv["gpu_memory_utilization"]),
            ("tokyo108", 8103, "gpt-oss-120b", 0.92))
        self.assertEqual(srv["env"], {
            "LD_LIBRARY_PATH":
                "/home/y-guo/reproduce/new1/envs/cuda-compat-13.0",
            "VLLM_USE_FLASHINFER_SAMPLER": "0"})

    def test_base_url_from_server_node(self):
        self.assertEqual(PL.base_url_of(PL.load_preset("default")),
                         "http://tokyo108:8103/v1")

    def test_merge_client_takes_preset_temperature(self):
        # When the CLI does not give an explicit value, temperature takes the value written in the preset's client section
        pre = PL.load_preset("default")
        out = PL.merge_client({"temperature": None}, pre["client"], {})
        self.assertEqual(out["temperature"], pre["client"]["temperature"])

    def test_gen_launch_default_preset_name(self):
        # The preset name the launch-manifest generator uses when gptoss_client_preset is absent from the manifest
        gl_dir = str(ROOT / "pipeline/collect")
        if gl_dir not in sys.path:
            sys.path.insert(0, gl_dir)
        import gen_launch as GL
        self.assertEqual(GL.GPTOSS_CLIENT_PRESET_DEFAULT, "default")


class TestRequireTemperature(unittest.TestCase):
    """Temperature check for the generation entry: a numeric temperature passes, a preset with null stops it on the spot."""

    def test_number_passes_through(self):
        pre = PL.load_preset("default")
        self.assertEqual(
            PL.require_temperature(pre["client"]["temperature"], "default"),
            1.0)

    def test_null_temperature_stops(self):
        # gptoss_bfcl_high's temperature follows BFCL's own setting, so running the generation entry with it must error
        pre = PL.load_preset("gptoss_bfcl_high")
        with self.assertRaises(SystemExit) as cm:
            PL.require_temperature(pre["client"]["temperature"],
                                   pre["_name"])
        self.assertIn("gptoss_bfcl_high", str(cm.exception))


class TestEntrypointPresetDefault(unittest.TestCase):
    """For every entry that takes --preset, the argparse default is default."""

    def test_every_entrypoint_defaults_to_default(self):
        for rel in PRESET_ENTRYPOINTS:
            defaults = _preset_arg_defaults(rel)
            self.assertTrue(defaults, f"{rel} should have a --preset argument with a default")
            self.assertEqual(defaults, ["default"] * len(defaults), rel)


class TestBfclPresetFields(unittest.TestCase):
    """gptoss_bfcl_high's client section: the BFCL line's setting."""

    def test_bfcl_high(self):
        c = PL.load_preset("gptoss_bfcl_high")["client"]
        # temperature=None: the BFCL line keeps using BFCL's own built-in setting
        self.assertEqual((c["api"], c["reasoning_effort"], c["temperature"],
                          c["max_tokens"]), ("chat", "high", None, 16384))


class TestServeCmdFromDefault(unittest.TestCase):
    """serve_preset assembles the vllm serve command from default's server section."""

    def test_cmd_carries_server_node_values(self):
        import serve_preset as SP
        pre = PL.load_preset("default")
        host, session, tmux, cmd = SP.build(pre, gpu=5)
        self.assertEqual(host, "tokyo108")
        self.assertEqual(session, "new1_vllm_tokyo108_default")
        self.assertIn("--gpu-memory-utilization 0.92", cmd)
        self.assertIn("--served-model-name gpt-oss-120b", cmd)
        self.assertIn("--port 8103", cmd)
        self.assertIn(resolve("gpt-oss-120b"), cmd)
        self.assertIn("VLLM_USE_FLASHINFER_SAMPLER=0", tmux)
        self.assertIn("LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/"
                      "envs/cuda-compat-13.0", tmux)
        self.assertIn("CUDA_VISIBLE_DEVICES=5", tmux)

    def test_preset_without_server_refuses(self):
        import serve_preset as SP
        pre = PL.load_preset("gptoss_bfcl_high")   # This one has no server section
        with self.assertRaises(SystemExit):
            SP.build(pre, gpu=0)


class TestEntrypointsCompile(unittest.TestCase):
    """Every changed entry compiles (syntax level; import-level equivalence is in the next class)."""

    FILES = [
        "preset_loader.py", "model_registry.py", "serve_preset.py", "run.py",
        "envs/collect/common.py", "envs/collect/run_appworld.py",
        "envs/collect/run_alfworld.py", "envs/collect/run_tales.py",
        "envs/collect/run_tau2.py", "envs/collect/bfcl_gptoss/gpt_oss_chat.py",
        "pipeline/inject/live_appworld.py", "pipeline/inject/replay_inject.py",
        "pipeline/inject/splice_replay.py", "pipeline/inject/ident3_gate.py",
        "pipeline/inject/acceptance.py",
        "pipeline/collect/gen_launch.py", "pipeline/eval/eval_tool.py",
    ]

    def test_all_compile(self):
        for f in self.FILES:
            py_compile.compile(str(ROOT / f), doraise=True)


@unittest.skipUnless(APPWORLD_PY.exists(), "appworld venv is not on this machine")
class TestCollectorSettings(unittest.TestCase):
    """Collector setting: when settings_from_args is not given --preset, it falls back to
    default, and the sampling keys in the preset's client section flow into the output
    (this runs in the appworld venv, where common needs openai).
    """

    CODE = r"""
import json, sys
from argparse import Namespace
sys.path.insert(0, "{collect}")
from common import settings_from_args

def S(**kw):
        base = dict(preset=None, api=None, reasoning_effort=None, start_date=None,
                                model=None, base_url=None)
        base.update(kw)
        return settings_from_args(Namespace(**base))

a = S()                                      # do not pass --preset
b = S(preset="gptoss_default",
            model="gpt-oss-120b", base_url="http://tokyo108:8103/v1")
c = S(preset="default", reasoning_effort="low")   # CLI overrides the preset
print(json.dumps([a, [b["temperature"], b["top_p"], b["seed"]],
                                    c["reasoning_effort"]]))
"""

    def test_no_preset_lands_on_default(self):
        code = self.CODE.format(collect=ROOT / "envs/collect")
        r = subprocess.run([str(APPWORLD_PY), "-c", code],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        a, b_sample, c_effort = json.loads(r.stdout)
        self.assertEqual(a["preset"], "default")
        self.assertEqual(a["temperature"], 1.0)
        self.assertEqual(a["top_p"], 1.0)
        self.assertEqual(a["api"], "harmony")
        self.assertEqual(a["reasoning_effort"], "high")
        self.assertEqual(a["max_tokens"], 8192)
        self.assertEqual(a["start_date"], "2026-08-06")
        # default carries a server section: the endpoint and model name can be omitted
        self.assertEqual(a["base_url"], "http://tokyo108:8103/v1")
        self.assertEqual(a["model"], "gpt-oss-120b")
        # gptoss_default's temperature/top_p must flow into the output, seed stays null
        self.assertEqual(b_sample, [1.0, 1.0, None])
        self.assertEqual(c_effort, "low")       # CLI overrides the preset


class TestSamplingForwarding(unittest.TestCase):
    """A sampling key written into a preset flows into the request body (aligned 2026-08-21).
    Before this, only the collection line forwarded top_p/seed -- the merge fallback for
    live runs/replay did not have these two keys, so writing them into a preset had no
    effect, silently. The fallback table covers the keys below; temperature is given on
    the cli side of the merge by --preset (default: default), with its value coming only
    from the preset file."""

    SAMPLING_KEYS = {"top_p", "max_tokens", "stop", "seed"}

    def test_live_fb_covers_sampling_keys(self):
        # merge_client only handles keys in cli∪fallbacks: a key missing from the fallback means that key does not take effect
        la = _import_inject("live_appworld")
        self.assertEqual(self.SAMPLING_KEYS - set(la.PRESET_FB), set())

    def test_replay_fb_covers_sampling_keys(self):
        ri = _import_inject("replay_inject")
        self.assertEqual(self.SAMPLING_KEYS - set(ri.PRESET_FB), set())

    def test_live_payload_carries_preset_temperature(self):
        la = _import_inject("live_appworld")
        t = PL.load_preset("default")["client"]["temperature"]
        a = Namespace(model="gpt-oss-120b", temperature=t,
                      stop=["<|return|>"], top_p=None, seed=None)
        self.assertEqual(
            la.gen_payload(a, [11, 22], 100),
            dict(model="gpt-oss-120b", prompt=[11, 22], max_tokens=100,
                 temperature=t, stop=["<|return|>"],
                 skip_special_tokens=False))

    def test_live_payload_carries_top_p_seed(self):
        la = _import_inject("live_appworld")
        a = Namespace(model="m", temperature=1.0, stop=["<|return|>"],
                      top_p=0.9, seed=7)
        p = la.gen_payload(a, [1], 5)
        self.assertEqual((p["top_p"], p["seed"]), (0.9, 7))

    def test_replay_payload_carries_preset_temperature(self):
        ri = _import_inject("replay_inject")
        t = PL.load_preset("default")["client"]["temperature"]
        a = Namespace(model="gpt-oss-120b", temperature=t, max_tokens=8192,
                      stop=["<|return|>"], top_p=None, seed=None)
        self.assertEqual(
            ri.gen_payload(a, "P"),
            dict(model="gpt-oss-120b", prompt="P", max_tokens=8192,
                 temperature=t, stop=["<|return|>"],
                 skip_special_tokens=False))

    def test_replay_payload_carries_top_p_seed(self):
        ri = _import_inject("replay_inject")
        a = Namespace(model="m", temperature=1.0, max_tokens=64,
                      stop=["<|return|>"], top_p=0.9, seed=7)
        p = ri.gen_payload(a, "P")
        self.assertEqual((p["top_p"], p["seed"]), (0.9, 7))


class TestPresetSweep(unittest.TestCase):
    """preset-sweep: a parameter grid -> a batch of valid preset files, the name is the setting."""

    def test_expand_cartesian_order(self):
        import sweep_preset as SW
        pts = SW.expand([("temperature", [0.2, 0.7]), ("top_p", [0.9, 1.0])])
        self.assertEqual(pts, [
            {"temperature": 0.2, "top_p": 0.9},
            {"temperature": 0.2, "top_p": 1.0},
            {"temperature": 0.7, "top_p": 0.9},
            {"temperature": 0.7, "top_p": 1.0}])

    def test_parse_grid_types_follow_client_keys(self):
        import sweep_preset as SW
        self.assertEqual(SW.parse_grid("seed=1,2"), ("seed", [1, 2]))
        self.assertEqual(SW.parse_grid("temperature=0.2"),
                         ("temperature", [0.2]))
        self.assertEqual(SW.parse_grid("reasoning_effort=low,high"),
                         ("reasoning_effort", ["low", "high"]))

    def test_parse_grid_rejects_bad_input(self):
        import sweep_preset as SW
        with self.assertRaises(SystemExit):
            SW.parse_grid("api=chat")            # Not a sampling key
        with self.assertRaises(SystemExit):
            SW.parse_grid("temperature=abc")     # Cannot convert to a number
        with self.assertRaises(SystemExit):
            SW.parse_grid("temperature")         # No =

    def test_main_writes_valid_presets_and_refuses_overwrite(self):
        import sweep_preset as SW
        with tempfile.TemporaryDirectory() as td:
            SW.main(["--base", "gptoss_default",
                     "--grid", "temperature=0.2,0.7", "--grid", "top_p=0.9",
                     "--out-dir", td])
            files = sorted(Path(td).glob("*.json"))
            self.assertEqual([f.stem for f in files], [
                "gptoss_default__temperature0.2__top_p0.9",
                "gptoss_default__temperature0.7__top_p0.9"])
            for f in files:
                self.assertEqual(PL.validate(json.loads(f.read_text())),
                                 [], f.name)
            p0 = json.loads(files[0].read_text())
            self.assertEqual((p0["client"]["temperature"],
                              p0["client"]["top_p"]), (0.2, 0.9))
            self.assertEqual(p0["model"], "gpt-oss-120b")  # Copy the rest of base as is
            with self.assertRaises(SystemExit):   # Reject overwriting a same-named entry
                SW.main(["--base", "gptoss_default",
                         "--grid", "temperature=0.2,0.7",
                         "--grid", "top_p=0.9", "--out-dir", td])

    def test_dry_run_writes_nothing(self):
        import sweep_preset as SW
        with tempfile.TemporaryDirectory() as td:
            SW.main(["--base", "gptoss_default", "--grid", "seed=1,2,3",
                     "--out-dir", td, "--dry-run"])
            self.assertEqual(list(Path(td).glob("*.json")), [])

    def test_duplicate_grid_key_rejected(self):
        import sweep_preset as SW
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                SW.main(["--base", "gptoss_default",
                         "--grid", "seed=1", "--grid", "seed=2",
                         "--out-dir", td])


class TestBfclHandlerPreset(unittest.TestCase):
    """The BFCL handler cannot be imported in the repo environment (it needs bfcl_eval
    from the BFCL venv), so only exec the preset-reading section above
    NEW1_PRESET_PREFIX_END -- that section is pure standard library."""

    SRC = (ROOT / "envs/collect/bfcl_gptoss/gpt_oss_chat.py").read_text()

    def run_prefix(self, preset_path):
        prefix = self.SRC.split("NEW1_PRESET_PREFIX_END")[0]
        old = os.environ.pop("NEW1_PRESET_JSON", None)
        try:
            if preset_path:
                os.environ["NEW1_PRESET_JSON"] = str(preset_path)
            ns = {}
            exec(compile(prefix, "gpt_oss_chat_prefix", "exec"), ns)
            return ns
        finally:
            if old is None:
                os.environ.pop("NEW1_PRESET_JSON", None)
            else:
                os.environ["NEW1_PRESET_JSON"] = old

    def test_no_env_reads_default_preset(self):
        # When the environment variable is absent, read configs/presets/default.json at the repo root
        c = PL.load_preset("default")["client"]
        ns = self.run_prefix(None)
        self.assertEqual(ns["_PRESET_PATH"],
                         str(PL.PRESET_DIR / "default.json"))
        self.assertEqual((ns["_MAX_TOKENS"], ns["_EFFORT"]),
                         (c["max_tokens"], c["reasoning_effort"]))
        self.assertEqual(ns["_CLIENT"]["temperature"], c["temperature"])
        self.assertEqual(ns["_sample_kwargs"](), {"top_p": c["top_p"]})

    def test_gptoss_default_forwards_top_p(self):
        ns = self.run_prefix(PL.PRESET_DIR / "gptoss_default.json")
        self.assertEqual(ns["_EFFORT"], "medium")
        self.assertEqual(ns["_sample_kwargs"](), {"top_p": 1.0})

    def test_seed_forwarded(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            json.dump({"client": {"top_p": 0.9, "seed": 7}}, f)
            f.flush()
            ns = self.run_prefix(f.name)
        self.assertEqual(ns["_sample_kwargs"](), {"top_p": 0.9, "seed": 7})


if __name__ == "__main__":
    unittest.main()
