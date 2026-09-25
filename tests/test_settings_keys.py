"""Every named setting of every workflow file loads, plain and under --debug, and its run keys behave
as a launch relies on: stable across processes, moved by exactly the stage fields and eras that
feed them and by nothing else, and refused on a bad name or a bad override."""
# venv: probe
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from experimental_settings import schema

SETTINGS_DIR = REPO_ROOT / "experimental_settings"
KEY_RE = re.compile(r"[0-9a-f]{12}")


def _workflow_files() -> list[Path]:
    return sorted(p for p in SETTINGS_DIR.glob("*.yaml") if p.stem != "debug")


def _setting_names(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text()) or {}
    return [name for name in doc if name not in schema.RESERVED_TOP_LEVEL]


def _load(path: Path, name: str, *, debug: bool = False, overrides: dict | None = None):
    return schema.load(path, name, debug=debug, overrides=overrides or {})


def _keys(setting) -> dict[str, str]:
    return {stage: schema.key(stage, setting) for stage in setting._workflow}


def _first_setting(stem: str):
    path = SETTINGS_DIR / f"{stem}.yaml"
    return path, _setting_names(path)[0]


def _moved(path: Path, name: str, overrides: dict) -> list[str]:
    before = _keys(_load(path, name)[0])
    after = _keys(_load(path, name, overrides=overrides)[0])
    return [stage for stage in before if before[stage] != after[stage]]


class EverySettingLoadsTest(unittest.TestCase):

    def test_every_named_setting_loads_plain_and_debug(self):
        n = 0
        for path in _workflow_files():
            for name in _setting_names(path):
                for debug in (False, True):
                    with self.subTest(file=path.stem, setting=name, debug=debug):
                        settings = _load(path, name, debug=debug)
                        self.assertGreaterEqual(len(settings), 1)
                        for s in settings:
                            self.assertEqual(s._debug, debug)
                            self.assertTrue(s._workflow)
                            for stage, k in _keys(s).items():
                                self.assertRegex(k, KEY_RE, f"{stage} key")
                            n += 1
        self.assertGreater(n, 0, "no settings found under experimental_settings/")

    def test_debug_moves_every_key_and_the_run_dir(self):
        cfg = yaml.safe_load((REPO_ROOT / "constants" / "path_outputs.yaml").read_text())
        root = Path(cfg["root"])
        for path in _workflow_files():
            for name in _setting_names(path):
                real = _load(path, name)[0]
                debug = _load(path, name, debug=True)[0]
                for stage in real._workflow:
                    with self.subTest(file=path.stem, setting=name, stage=stage):
                        k_real, k_debug = schema.key(stage, real), schema.key(stage, debug)
                        self.assertNotEqual(k_real, k_debug)
                        self.assertEqual(schema.run_dir(stage, real), root / stage / k_real)
                        self.assertEqual(schema.run_dir(stage, debug),
                                         root / cfg["debug_subdir"] / stage / k_debug)

    def test_equal_stage_inputs_give_equal_keys(self):
        """Two settings share a stage's directory exactly when that stage's fields, models and
        upstream keys agree (e.g. a baseline and a probe setting over the same sample section)."""
        loaded = [s for p in _workflow_files() for n in _setting_names(p) for s in _load(p, n)]
        seen: dict[tuple[str, str], str] = {}
        for s in loaded:
            for stage in s._workflow:
                folded = {e["name"] for e in schema.STAGES[stage]["upstream"] if e["key"] == "fold"}
                upstream = {n: k for n, k in schema.upstream(stage, s).items() if n in folded}
                inputs = json.dumps({"f": schema.fields_of(stage, s), "m": schema.models_of(stage, s),
                                     "u": upstream}, sort_keys=True, default=str)
                k = schema.key(stage, s)
                if (stage, inputs) in seen:
                    self.assertEqual(seen[(stage, inputs)], k, f"{stage} of {s._file}/{s._name}")
                seen[(stage, inputs)] = k
                for (other_stage, other_inputs), other_k in seen.items():
                    if other_stage == stage and other_inputs != inputs:
                        self.assertNotEqual(other_k, k, f"{stage} of {s._file}/{s._name}")

    def test_keys_are_the_same_in_a_fresh_process(self):
        """The key is canonical JSON, so hash seeding and dict order in another process change nothing."""
        path, name = _first_setting("train_probe")
        here = _keys(_load(path, name)[0])
        code = (
            "import json, sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]);"
            "from experimental_settings import schema;"
            "s = schema.load(Path(sys.argv[2]), sys.argv[3], debug=False, overrides={})[0];"
            "print(json.dumps({st: schema.key(st, s) for st in s._workflow}))")
        env = dict(os.environ, PYTHONHASHSEED="12345")
        out = subprocess.run([sys.executable, "-c", code, str(REPO_ROOT), str(path), name],
                             capture_output=True, text=True, env=env, check=True).stdout
        self.assertEqual(json.loads(out), here)


class KeyMovementTest(unittest.TestCase):

    def test_train_field_moves_train_and_eval_only(self):
        path, name = _first_setting("train_probe")
        self.assertEqual(_moved(path, name, {"train.lr": "3.0e-5"}), ["train", "eval"])

    def test_build_field_moves_build_and_downstream(self):
        path, name = _first_setting("train_probe")
        self.assertEqual(_moved(path, name, {"build.max_cuts": "8"}), ["build", "train", "eval"])

    def test_sample_field_moves_every_stage(self):
        path, name = _first_setting("train_probe")
        self.assertEqual(_moved(path, name, {"sample.max_steps": "10"}),
                         ["sample", "build", "train", "eval"])
        path, name = _first_setting("baseline")
        self.assertEqual(_moved(path, name, {"sample.max_steps": "10"}), ["sample", "score"])

    def test_eval_field_moves_eval_only(self):
        path, name = _first_setting("train_probe")
        self.assertEqual(_moved(path, name, {"eval.bootstrap": "10"}), ["eval"])

    def test_inject_theta_moves_inject_and_score(self):
        path, name = _first_setting("inject")
        self.assertEqual(_moved(path, name, {"inject.theta": "0.9"}), ["inject", "score"])

    def test_launch_only_fields_move_nothing(self):
        """pieces and notes change how or why a run is launched, never what it produces."""
        path, name = _first_setting("train_probe")
        for override in ({"sample.pieces": "2"}, {"sample.replicas": "2"}, {"meta.notes": "'why'"}):
            with self.subTest(override=override):
                self.assertEqual(_moved(path, name, override), [])

    def test_era_row_moves_its_stage_and_downstream(self):
        path, name = _first_setting("train_probe")
        before = _keys(_load(path, name)[0])
        real_era_of = schema.era_of
        schema.era_of = lambda stage: real_era_of(stage) + (1 if stage == "build" else 0)
        try:
            after = _keys(_load(path, name)[0])
        finally:
            schema.era_of = real_era_of
        self.assertEqual([st for st in before if before[st] != after[st]], ["build", "train", "eval"])


class RefusalTest(unittest.TestCase):

    def _refused(self, path: Path, name: str, overrides: dict | None = None) -> str:
        with self.assertRaises(schema.SchemaError) as cm:
            _load(path, name, overrides=overrides)
        return str(cm.exception)

    def test_unknown_and_reserved_names(self):
        path, _ = _first_setting("train_probe")
        self.assertIn("no such setting", self._refused(path, "no_such_setting_here"))
        for reserved in schema.RESERVED_TOP_LEVEL:
            self.assertIn("reserved", self._refused(path, reserved))

    def test_unknown_override_field(self):
        path, name = _first_setting("train_probe")
        self.assertIn("not a field", self._refused(path, name, {"train.no_such_field": "1"}))

    def test_override_of_a_section_the_workflow_does_not_read(self):
        path, name = _first_setting("baseline")
        self.assertIn("no stage", self._refused(path, name, {"probe.method": "ctool"}))

    def test_theta_outside_unit_interval(self):
        path, name = _first_setting("inject")
        for theta in ("1.5", "-0.1"):
            with self.subTest(theta=theta):
                self._refused(path, name, {"inject.theta": theta})


if __name__ == "__main__":
    unittest.main()
