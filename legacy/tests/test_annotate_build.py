"""annotate/build.py's two new knobs and four new statistics (pure CPU, fake trajectory
directory).

What this covers: the three-tier priority (CLI > config field > default) for weight_mode
(uniform = equal weight per step / per_event = the old spec, w=1/m_i) and max_bounds (the cut
cap); rules.boundaries gives the same result with no cap argument as with 64; the four new
statistics appear only when the config carries trajs_per_unit, and the numbers check out. Plus
one G8 unit-test miniature: on the same fake trajectory, the pre-change build.py+rules.py
(checked out from commit 808266a and run) and the current code with `--weight-mode per_event
--max-bounds 64` produce seven output files that are byte-identical.

    python3 -m unittest tests.test_annotate_build -v
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "pipeline" / "annotate"
BUILD = ANN / "build.py"
sys.path.insert(0, str(ANN))

import build as B                                              # noqa: E402
import rules as R                                              # noqa: E402

# The commit before the change: the G8 miniature runs its build.py + rules.py as the control
# group.
# Pinned to a sha, not HEAD -- once this change is committed, HEAD is no longer "before the
# change".
PIN = "808266a"

OUT_FILES = ("train.jsonl", "val.jsonl", "test.jsonl", "tool_vocab.json",
             "router_stats.md", "qa_sample.txt", "ANNOTATE_REPORT.md")


def tid_of(name):
    """Fake task_id. Does not use the built-in hash(): string hash is salted per process, so the
    question-set file would not match."""
    return f"{zlib.crc32(name.encode()) % 10 ** 7:07d}_1"


def think_text(n, tag):
    """n sentences of thinking -> exactly n untruncated cuts (each sentence ~52 characters, clears
    the MIN_THINK//2 gate)."""
    return " ".join(
        f"Step {i} of {tag} needs a careful second look at the data."
        for i in range(n))


def write_traj(path, tid, n_step=1, n_sent=3, tag="a", final_steps=None):
    """Write one fake appworld trajectory (meta + gen/env per step + final)."""
    recs = [dict(type="meta", env="appworld", task_id=tid,
                 model="gpt-oss-120b", instruction=f"do task {tid}",
                 preset="default", gen_settings=dict(seed=42))]
    for st in range(n_step):
        call = f"print(apis.venmo.show_account(idx={st}))"
        recs.append(dict(type="gen", step=st,
                         reasoning=think_text(n_sent, tag),
                         content=f"```python\n{call}\n```"))
        recs.append(dict(type="env", step=st, action=call + "\n", result="ok"))
    recs.append(dict(type="final",
                     steps=n_step if final_steps is None else final_steps,
                     completed=True))
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in recs))


class BuildCase(unittest.TestCase):
    """One tempdir per test case: fake trajectory directory + three question-set files + config +
    output directory."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="annbuild_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.runs = self.tmp / "runs" / "appworld_gptoss"
        self.runs.mkdir(parents=True)
        self.out = self.tmp / "out"

    # ---------- fixture factory ----------

    def traj(self, unit_name, r=None, **kw):
        """Build one trajectory, return its task_id. If r is given, use a filename with the sampling
        index."""
        tid = tid_of(unit_name)
        stem = f"appworld_{tid}" if r is None else f"appworld_{tid}_r{r}"
        write_traj(self.runs / f"{stem}.jsonl", tid, **kw)
        return tid

    def splits(self, train, val, test):
        """Three official question-set files (shaped like the real files, no trailing newline)."""
        d = self.tmp / "splits"
        d.mkdir(exist_ok=True)
        for name, units in (("train", train), ("val", val), ("test", test)):
            (d / f"{name}.txt").write_text("\n".join(units))
        return {name: str(d / f"{name}.txt")
                for name in ("train", "val", "test")}

    def config(self, files, name="cfg.json", **extra):
        cfg = dict(run_family="fake_v1", env="appworld", model_short="gptoss",
                   model_full="gpt-oss-120b",
                   traj_runs=[str(self.tmp / "runs")],
                   split_mode="official", official_split_files=files,
                   data_out=str(self.out), seed=20260729)
        cfg.update(extra)
        p = self.tmp / name
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
        return p

    # ---------- run and read ----------

    def build(self, cfg, *flags, script=BUILD):
        p = subprocess.run(
            [sys.executable, str(script), "--config", str(cfg), *flags],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def samples(self, split="train"):
        txt = (self.out / f"{split}.jsonl").read_text()
        return [json.loads(l) for l in txt.splitlines()]

    def all_samples(self):
        out = []
        for sp in ("train", "val", "test"):
            out += self.samples(sp)
        return out

    def report(self):
        return (self.out / "ANNOTATE_REPORT.md").read_text().splitlines()


class TestWeightMode(BuildCase):
    """1/2: the weight spec and CLI overriding the config field."""

    def fixture(self, **extra):
        a = self.traj("wa", n_sent=3)
        b = self.traj("wb", n_sent=5)
        c = self.traj("wc", n_sent=7)
        return self.config(self.splits([a], [b], [c]), **extra)

    def test_default_is_uniform(self):
        cfg = self.fixture()
        self.build(cfg)
        ws = {s["w"] for s in self.all_samples()}
        self.assertEqual(ws, {1.0})
        self.assertIn("- rules: full-sentence-boundary prefix / w=1, each step equally weighted / three-way split "
                      "(official task list, task-instance level) / one model, one dataset", self.report())

    def test_per_event_keeps_old_weight(self):
        cfg = self.fixture()
        self.build(cfg, "--weight-mode", "per_event")
        for s in self.all_samples():
            self.assertEqual(s["w"], round(1.0 / s["n_sents"], 6))
        self.assertIn("- rules: full-sentence-boundary prefix / w=1/m_i, events equally weighted / three-way split "
                      "(official task list, task-instance level) / one model, one dataset", self.report())

    def test_cfg_field_read(self):
        cfg = self.fixture(weight_mode="per_event")
        self.build(cfg)
        for s in self.all_samples():
            self.assertEqual(s["w"], round(1.0 / s["n_sents"], 6))

    def test_cli_beats_cfg_field(self):
        cfg = self.fixture(weight_mode="per_event", max_bounds=64)
        self.build(cfg, "--weight-mode", "uniform", "--max-bounds", "4")
        ss = self.all_samples()
        self.assertEqual({s["w"] for s in ss}, {1.0})
        self.assertEqual(max(s["n_sents"] for s in ss), 4)

    def test_bad_weight_mode_in_cfg_dies(self):
        cfg = self.fixture(weight_mode="whatever")
        p = subprocess.run(
            [sys.executable, str(BUILD), "--config", str(cfg)],
            capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("weight_mode", p.stderr)


class TestMaxBounds(BuildCase):
    """3/4: the cut cap takes effect + boundaries' default-argument compatibility."""

    def fixture(self, **extra):
        a = self.traj("ma", n_sent=100)     # 100 untruncated cuts
        b = self.traj("mb", n_sent=5)
        c = self.traj("mc", n_sent=7)
        return self.config(self.splits([a], [b], [c]), **extra)

    def test_default_cap_is_64(self):
        self.build(self.fixture())
        self.assertEqual(len(self.samples("train")), 64)
        self.assertEqual({s["n_sents"] for s in self.samples("train")}, {64})

    def test_explicit_cap(self):
        self.build(self.fixture(), "--max-bounds", "16")
        self.assertEqual(len(self.samples("train")), 16)

    def test_cfg_cap(self):
        self.build(self.fixture(max_bounds=8))
        self.assertEqual(len(self.samples("train")), 8)

    def test_default_equals_explicit_64(self):
        cfg = self.fixture()
        self.build(cfg)
        keep = self.tmp / "keep64"
        shutil.copytree(self.out, keep)
        self.build(cfg, "--max-bounds", "64")
        for name in OUT_FILES:
            self.assertEqual((keep / name).read_bytes(),
                             (self.out / name).read_bytes(), name)

    def test_cap_below_two_dies(self):
        cfg = self.fixture()
        p = subprocess.run(
            [sys.executable, str(BUILD), "--config", str(cfg),
             "--max-bounds", "1"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("max_bounds", p.stderr)

    def test_cap_zero_in_config_dies_too(self):
        # The config branch is judged by whether the key is present: writing 0 must not silently be
        # swapped to 64 by an or -- it must hit the same <2 hard block as CLI's 0 (a hole caught by
        # the 2026-08-22 review)
        cfg = self.fixture(max_bounds=0)
        p = subprocess.run(
            [sys.executable, str(BUILD), "--config", str(cfg)],
            capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("max_bounds", p.stderr)

    def test_boundaries_default_arg(self):
        txt = think_text(100, "z")
        self.assertEqual(R.boundaries(txt), R.boundaries(txt, 64))
        self.assertEqual(R.boundaries(txt), R.boundaries(txt, R.MAX_BOUNDS))
        self.assertEqual(len(R.boundaries(txt, 10 ** 9)), 100)
        self.assertEqual(len(R.boundaries(txt)), 64)


class TestNewStats(BuildCase):
    """5: the gating and numbers for the four new statistics."""

    PREFIXES = ("- cut-point count (untruncated)", "- events hitting the cut-point cap",
                "- identical trajectories", "- trajectories at the step-count cap")

    def fixture(self, **extra):
        # A: two identical trajectories (same tag, same step count -> reasoning/content equal at every step)
        a = self.traj("sa", r=0, n_sent=3, tag="same")
        self.traj("sa", r=1, n_sent=3, tag="same")
        # B: 100 untruncated cuts, and the final step count caps at 30
        b = self.traj("sb", r=0, n_sent=100, tag="long", final_steps=30)
        # C: one ordinary trajectory
        c = self.traj("sc", r=0, n_sent=3, tag="plain")
        return self.config(self.splits([a], [b], [c]), **extra)

    def test_stats_absent_without_gate(self):
        self.build(self.fixture())
        for line in self.report():
            for pre in self.PREFIXES:
                self.assertFalse(line.startswith(pre), line)

    def test_stats_present_and_correct(self):
        self.build(self.fixture(trajs_per_unit=2))
        rep = self.report()
        # untruncated cut counts = [3, 3, 3, 100] (A's two trajectories one event each, B one, C one)
        # p50=ub[2]=3, p90=p99=ub[3]=100; over 32/64/128/256 -> 1/1/0/0
        self.assertIn("- cut-point count (untruncated) per event: min 3 p50 3 p90 100 p99 100"
                      " max 100; events exceeding 32/64/128/256 1/1/0/0", rep)
        self.assertIn("- events hitting the cut-point cap (64): 1", rep)
        self.assertIn("- identical trajectories: 1 pairs (involving 1 tasks); scanned 4 trajectories, counted only, not deduplicated",
                      rep)
        self.assertIn("- trajectories at the step-count cap (30): 1 (involving 1 tasks)", rep)

    def test_cap_line_follows_max_bounds(self):
        self.build(self.fixture(trajs_per_unit=2), "--max-bounds", "32")
        self.assertIn("- events hitting the cut-point cap (32): 1", self.report())

    def test_no_duplicate_when_trajs_differ(self):
        # same unit, two trajectories but different tag -> text differs at every step, not counted as
        # the same trajectory
        a = self.traj("da", r=0, n_sent=3, tag="x")
        self.traj("da", r=1, n_sent=3, tag="y")
        b = self.traj("db", r=0, n_sent=3, tag="z")
        c = self.traj("dc", r=0, n_sent=3, tag="w")
        cfg = self.config(self.splits([a], [b], [c]), trajs_per_unit=2)
        self.build(cfg)
        self.assertIn("- identical trajectories: 0 pairs (involving 0 tasks); scanned 4 trajectories, counted only, not deduplicated",
                      self.report())
        self.assertIn("- trajectories at the step-count cap (30): 0 (involving 0 tasks)", self.report())


class TestLegacyBytes(BuildCase):
    """6: the G8 unit-test miniature -- hand-worked expectations for the old semantics + a
    byte-for-byte comparison against the pre-change code."""

    def fixture(self):
        a = self.traj("ga", n_sent=100)
        b = self.traj("gb", n_sent=5)
        c = self.traj("gc", n_sent=7)
        return self.config(self.splits([a], [b], [c]))

    def test_old_semantics_by_hand(self):
        cfg = self.fixture()
        self.build(cfg, "--weight-mode", "per_event", "--max-bounds", "64")
        ss = self.all_samples()
        # w = 1/m_i; m = min(untruncated cut count, 64)
        want = {100: 64, 5: 5, 7: 7}
        got = {s["n_sents"] for s in ss}
        self.assertEqual(got, set(want.values()))
        for s in ss:
            self.assertEqual(s["w"], round(1.0 / s["n_sents"], 6))
        rep = self.report()
        self.assertIn("- SEED=20260729 MAX_BOUNDS=64 env=appworld"
                      " model=gpt-oss-120b", rep)
        self.assertIn("- rules: full-sentence-boundary prefix / w=1/m_i, events equally weighted / three-way split "
                      "(official task list, task-instance level) / one model, one dataset", rep)
        self.assertTrue(any(l.startswith("- boundary count per event: min 5 med 7 max 64"
                                         " (cap 64)") for l in rep), rep)
        for line in rep:
            for pre in TestNewStats.PREFIXES:
                self.assertFalse(line.startswith(pre), line)

    def test_make_samples_defaults_are_old_semantics(self):
        # accept_v3diff.py reproduces the old v3 data with make_samples(events) and passes no arguments
        # at all, so the function's defaults must still be the old spec (w=1/m_i, cap 64).
        self.fixture()
        with warnings.catch_warnings():
            # jsonl_events is the old way of writing `[json.loads(l) for l in open(f)]`; calling it directly
            # in-process floods a screen of ResourceWarning -- this is just noise here, not a regression.
            warnings.simplefilter("ignore", ResourceWarning)
            events = B.collect_events([self.tmp / "runs"], "appworld")
        self.assertEqual(B.make_samples(events),
                         B.make_samples(events, "per_event", R.MAX_BOUNDS))
        self.assertNotEqual(B.make_samples(events),
                            B.make_samples(events, "uniform", R.MAX_BOUNDS))

    def test_byte_identical_to_pre_change_code(self):
        old = self.tmp / "oldann"
        old.mkdir()
        for f in ("build.py", "rules.py"):
            p = subprocess.run(["git", "show", f"{PIN}:pipeline/annotate/{f}"],
                               cwd=str(ROOT), capture_output=True)
            if p.returncode != 0:
                self.skipTest(f"could not get {PIN}'s {f}: {p.stderr[:200]}")
            (old / f).write_bytes(p.stdout)
        cfg = self.fixture()
        self.build(cfg, script=old / "build.py")        # control group: the pre-change code
        ref = self.tmp / "ref"
        shutil.copytree(self.out, ref)
        self.build(cfg, "--weight-mode", "per_event", "--max-bounds", "64")
        # The two .md reports (router_stats.md, ANNOTATE_REPORT.md) are excluded: their
        # wording was translated to English on 2026-09-08, so their bytes no longer match
        # the pinned commit. Every data file is still compared byte for byte.
        for name in (n for n in OUT_FILES if not n.endswith(".md")):
            self.assertEqual((ref / name).read_bytes(),
                             (self.out / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
