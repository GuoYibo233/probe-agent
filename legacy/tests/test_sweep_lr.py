"""tests/test_sweep_lr.py -- ticket `.scratch/kvshare-train/issues/11-sweep-lr.md`,
corresponding to spec `.scratch/kvshare-train/spec.md` 16.6 (the plan/report
subcommands) and 16.9 (ticket 11 test points). Pure CPU, does not import torch,
hand-builds a small `train_log.jsonl`, does not read the live large data directory.
"""
import json
import sys
import tempfile
import unittest
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/train"))

import sweep_lr as SL  # noqa: E402


def _write_jsonl(path, events):
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


class TestFmtLr(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(SL.fmt_lr(1e-5), "1e-5")
        self.assertEqual(SL.fmt_lr(5e-5), "5e-5")
        self.assertEqual(SL.fmt_lr(2e-4), "2e-4")
        self.assertEqual(SL.fmt_lr(1e-4), "1e-4")
        self.assertEqual(SL.fmt_lr(5e-4), "5e-4")
        self.assertEqual(SL.fmt_lr(2e-3), "2e-3")


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.data_dir = ROOT / "pipeline/data/nyapass_aw_v1/gptoss"
        self.out_root = ROOT / "pipeline/runs/sweep"

    def test_default_grid_twelve_unique_rows(self):
        rows = SL.build_plan(SL.GRID, self.data_dir, self.out_root, "/x/python")
        self.assertEqual(len(rows), 12)
        run_ids = [r["run_id"] for r in rows]
        self.assertEqual(len(run_ids), len(set(run_ids)))

        for r in rows:
            self.assertIn(f"--lr {r['lr_s']}", r["cmd"])
            self.assertIn("--log-every 10", r["cmd"])
            if r["lora"]:
                self.assertIn("--lora", r["cmd"].split())
            else:
                self.assertNotIn("--lora", r["cmd"].split())
            self.assertTrue(r["outdir"].endswith(r["run_id"]))

        by_lr = {r["lr"]: r["lr_s"] for r in rows}
        self.assertEqual(by_lr[1e-5], "1e-5")
        self.assertEqual(by_lr[5e-5], "5e-5")
        self.assertEqual(by_lr[2e-4], "2e-4")
        self.assertEqual(by_lr[1e-4], "1e-4")
        self.assertEqual(by_lr[5e-4], "5e-4")
        self.assertEqual(by_lr[2e-3], "2e-3")

    def test_cli_plan_prints_twelve_launch_lines_and_writes_json(self):
        with tempfile.TemporaryDirectory() as td:
            write_path = Path(td) / "plan.json"
            buf = StringIO()
            with redirect_stdout(buf):
                rc = SL.main(["plan", "--write", str(write_path)])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            launch_lines = [l for l in out.splitlines()
                            if l.startswith("python3 run.py launch")]
            self.assertEqual(len(launch_lines), 12)
            for l in launch_lines:
                self.assertIn("--piece <host>:<gpus>", l)

            written = json.loads(write_path.read_text())
            self.assertEqual(len(written), 12)
            for rec in written:
                for key in ("run_id", "tag", "base", "lora", "lr",
                            "tok_budget", "card", "cmd", "outdir"):
                    self.assertIn(key, rec)

    def test_grid_with_colliding_lr_exits(self):
        grid = [dict(tag="x", base="qwen", lora=False,
                     lrs=[1e-5, 1.2e-5], tok_budget=16384, card="Ada",
                     extra=[])]
        with tempfile.TemporaryDirectory() as td:
            grid_path = Path(td) / "grid.json"
            grid_path.write_text(json.dumps(grid))
            buf = StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    SL.main(["plan", "--grid", str(grid_path)])


class TestReport(unittest.TestCase):
    def _make_done_run(self, root, run_id, base="qwen", lora=False, lr=1e-5):
        d = root / run_id
        d.mkdir()
        start = dict(event="start", base=base, lr=lr, tok_budget=16384,
                     n_train_events=4126, dropped_events_train=1)
        if lora:
            start["lora"] = dict(rank=16)
        events = [start]
        for frac, ce in [(1, 0.9), (2, 0.7), (3, 0.6), (4, 0.5)]:
            events.append(dict(event="eval", ep=0, frac=frac, gstep=frac * 10,
                                val_ce=ce, val_exact_call=round(1 - ce, 3)))
        events.append(dict(event="step", ep=0, gstep=10, peak_mem_gb=20.1))
        events.append(dict(event="step", ep=0, gstep=20, peak_mem_gb=22.4))
        events.append(dict(event="mem_probe_summary", worst_gb=26.2))
        events.append(dict(event="done", best_val_ce=0.5, best_ep=0,
                            best_frac=4, total_rows=1000, wall_s=3600.0))
        _write_jsonl(d / "train_log.jsonl", events)
        return d

    def _make_running_run(self, root, run_id, base="qwen", lora=False,
                          lr=5e-5, first_ce=0.8):
        d = root / run_id
        d.mkdir()
        start = dict(event="start", base=base, lr=lr, tok_budget=16384,
                     n_train_events=4126, dropped_events_train=1)
        if lora:
            start["lora"] = dict(rank=16)
        events = [start,
                  dict(event="eval", ep=0, frac=1, gstep=10,
                       val_ce=first_ce, val_exact_call=0.1)]
        _write_jsonl(d / "train_log.jsonl", events)
        return d

    def _make_run_with_mem_probe_events_only(self, root, run_id, base="qwen",
                                             lora=False, lr=1e-4):
        """A run directory from an old probe that only writes `mem_probe` events and has no `mem_probe_summary`."""
        d = root / run_id
        d.mkdir()
        start = dict(event="start", base=base, lr=lr, tok_budget=16384,
                     n_train_events=4126, dropped_events_train=1)
        if lora:
            start["lora"] = dict(rank=16)
        events = [start,
                  dict(event="eval", ep=0, frac=1, gstep=10,
                       val_ce=0.8, val_exact_call=0.1),
                  dict(event="mem_probe", peak_mem_gb=18.3),
                  dict(event="mem_probe", peak_mem_gb=21.5)]
        _write_jsonl(d / "train_log.jsonl", events)
        return d

    def test_worst_gb_falls_back_to_mem_probe_max_without_summary(self):
        """When `mem_probe_summary` is missing, `worst_gb` falls back to the max of
        `peak_mem_gb` across the `mem_probe` events (the old-probe compatibility
        branch explicitly required by ticket item 1)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = self._make_run_with_mem_probe_events_only(
                root, "ks828l17_gptoss_cgen_lr1e-4")
            rec = SL.summarize_run(d)
            self.assertEqual(rec["worst_gb"], 21.5)

    def test_val_exact_takes_last_available_point_not_best_frac(self):
        """Final-review O2 regression test (spec 16.6): under `--gen-eval-at last`,
        only the evaluation point at epoch end counts `val_exact_call`, but the
        numerically best `best_val_ce` may fall at an earlier point -- `val_exact`
        should take "the evaluation point that has a value" (here frac=2), not
        the point where `best_frac` is (frac=1, which has no `val_exact_call`);
        the column name and cell follow the `val_exact(@ep.frac)` / `0.42@0.2`
        format."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "ks828l4_gptoss_cgen_lr2e-3"
            d.mkdir()
            events = [
                dict(event="start", base="qwen4", lr=2e-3, tok_budget=16384,
                     n_train_events=100, dropped_events_train=0),
                # frac=1: numerically the best point, has no val_exact_call under --gen-eval-at last.
                dict(event="eval", ep=0, frac=1, gstep=10, val_ce=0.30),
                # frac=2: end of epoch, val_ce is worse than frac=1, but only this point has val_exact counted.
                dict(event="eval", ep=0, frac=2, gstep=20, val_ce=0.40,
                     val_exact_call=0.42),
                dict(event="done", best_val_ce=0.30, best_ep=0, best_frac=1,
                     total_rows=100, wall_s=10.0),
            ]
            _write_jsonl(d / "train_log.jsonl", events)

            rec = SL.summarize_run(d)
            self.assertEqual(rec["best_val_ce"], 0.30)
            self.assertEqual(rec["best_frac"], 1)
            self.assertEqual(rec["val_exact"], 0.42)
            self.assertEqual(rec["val_exact_frac"], "0.2")

            out_dir = root / "report"
            rc = SL.main(["report", "--runs", str(d), "--out", str(out_dir)])
            self.assertEqual(rc, 0)
            data = json.loads((out_dir / "SWEEP_REPORT.json").read_text())
            self.assertEqual(data[0]["val_exact"], 0.42)
            self.assertEqual(data[0]["val_exact_frac"], "0.2")
            md = (out_dir / "SWEEP_REPORT.md").read_text()
            self.assertIn("val_exact(@ep.frac)", md)
            self.assertIn("0.42@0.2", md)

    def test_report_two_runs_status_star_and_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._make_done_run(root, "ks828b06_gptoss_cgen_lr1e-5",
                                base="qwen", lora=False, lr=1e-5)
            self._make_running_run(root, "ks828b06_gptoss_cgen_lr5e-5",
                                   base="qwen", lora=False, lr=5e-5,
                                   first_ce=0.8)
            out_dir = root / "report"
            rc = SL.main(["report", "--runs", str(root / "ks828*"),
                          "--out", str(out_dir)])
            self.assertEqual(rc, 0)

            data = json.loads((out_dir / "SWEEP_REPORT.json").read_text())
            self.assertEqual(len(data), 2)
            by_id = {r["run_id"]: r for r in data}
            self.assertEqual(
                by_id["ks828b06_gptoss_cgen_lr1e-5"]["status"], "done")
            self.assertEqual(
                by_id["ks828b06_gptoss_cgen_lr5e-5"]["status"], "running")
            # the running row's best is the lowest eval so far (the only one, 0.8).
            self.assertEqual(
                by_id["ks828b06_gptoss_cgen_lr5e-5"]["best_val_ce"], 0.8)

            md = (out_dir / "SWEEP_REPORT.md").read_text()
            # the done row's best_val_ce=0.5 is lower than the running row's 0.8, marked with *.
            self.assertIn("*ks828b06_gptoss_cgen_lr1e-5", md)
            self.assertNotIn("*ks828b06_gptoss_cgen_lr5e-5", md)
            # (ep,frac) combination union: done ran 4 points (0,1)..(0,4), running ran (0,1),
            # union size is 4.
            combo_cols = [l for l in md.splitlines()
                          if l.startswith("| run_id |")][0]
            val_ce_cols = [c for c in combo_cols.split("|")
                          if c.strip().startswith("val_ce@")]
            self.assertEqual(len(val_ce_cols), 4)

    def test_missing_train_log_is_skipped_not_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "empty_run").mkdir()
            out_dir = root / "report"
            buf = StringIO()
            with redirect_stdout(buf):
                rc = SL.main(["report", "--runs", str(root / "empty_run"),
                              "--out", str(out_dir)])
            self.assertEqual(rc, 0)
            data = json.loads((out_dir / "SWEEP_REPORT.json").read_text())
            self.assertEqual(data, [])


if __name__ == "__main__":
    unittest.main()
