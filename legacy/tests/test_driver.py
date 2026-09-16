"""Boundary tests for pipeline/driver.py's state machine (the seven items in design draft section 7).

The driver itself never touches real machines: probing and subprocesses all go
through the injection points on `driver.Probes`; here they're swapped for fake
functions, a temporary directory tree stands in as the repo root, and the whole
state machine is run through dry -- initial-state advancement, dirty-tree
launch rejection, smoke criteria, the a1 stopping point, G6 completeness,
state-file overwrite rejection, --status being read-only.

Fakes always build ids with zlib.crc32 (the repo's existing convention, not the
built-in hash()).
"""
import io
import json
import sys
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipeline"))
import driver as D  # noqa: E402

SPLITS = ("train", "val", "test")


def fake_tid(i):
    return f"task_{zlib.crc32(f'u{i}'.encode()) % 100000:05d}"


def write_traj(path, tid, seed, steps=5, final=True):
    """A fake trajectory: first line is meta (with gen_settings.seed), last line is final."""
    lines = [json.dumps({"env": "appworld", "task_id": tid,
                         "model": "gpt-oss-120b", "instruction": "x",
                         "preset": "default",
                         "gen_settings": {"api": "harmony", "seed": seed}}),
             json.dumps({"type": "gen", "step": 0, "reasoning": "think",
                         "content": "c"})]
    if final:
        lines.append(json.dumps({"type": "final", "steps": steps,
                                 "completed": True, "abort": None, "eval": ""}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


class DriverCase(unittest.TestCase):
    """A temporary directory tree stands in as the repo root: the four module
    constants ROOT / LOG_ROOT / RUNS_DIR / SERVE_LOG_DIR all point there; the real
    repo isn't touched by a single byte."""

    n_units = 3
    k = 4

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        for name, val in (("ROOT", self.root),
                          ("LOG_ROOT", self.root / "logs" / "pipeline"),
                          ("RUNS_DIR", self.root / "pipeline" / "runs"),
                          ("SERVE_LOG_DIR", self.root / "envs" / "serve_logs")):
            p = patch.object(D, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.tids = [fake_tid(i) for i in range(self.n_units)]
        self.split_files = {}
        d = self.root / "splits"
        d.mkdir(parents=True)
        for i, sp in enumerate(SPLITS):
            f = d / f"{sp}.txt"
            f.write_text(self.tids[i])          # one task per batch, task list has no trailing newline
            self.split_files[sp] = str(f)
        self.data_out = self.root / "data" / "nyapass_aw_v1" / "gptoss"
        self.cfg_path = self.write_cfg()
        self.manifest_path = self.write_manifest()

    # ---- fake config ----

    def write_cfg(self, **over):
        cfg = {"run_family": "nyapass_aw_v1", "env": "appworld",
               "model_short": "gptoss", "model_full": "gpt-oss-120b",
               "traj_runs": [str(self.root / "envs" / "runs" / "nyapass")],
               "split_mode": "official",
               "official_split_files": dict(self.split_files),
               "data_out": str(self.data_out), "seed": 42,
               "weight_mode": "uniform", "trajs_per_unit": self.k,
               "collect": {"manifest": "manifest.json", "run_id": "nyapass",
                           "seeds": [42, 67, 4267, 6742]},
               "train": {"cells": ["ctool", "cgen", "cparam"],
                         "batches": {"np821b06": {"base": "qwen", "mode": "full"}},
                         "placement": "ops/np821_placement.json"}}
        cfg.update(over)
        p = self.root / "cfg.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False))
        return p

    def write_manifest(self, n_servers=2):
        mf = {"run_id": "nyapass", "env": "appworld",
              "gptoss_client_preset": "default", "traj_per_task": self.k,
              "seed_family": [42, 67, 4267, 6742],
              "envs_root": str(self.root / "envs"),
              "servers": [{"host": "tokyo108", "gpu": 2 + i, "card": "H200",
                           "model_key": "gptoss", "port": 8103 + i,
                           "session": f"new1_nyapass_srv_gptoss{chr(97 + i)}_t108g{2 + i}",
                           "extra_flags": ""} for i in range(n_servers)],
              "clients": [{"tag": "gptr", "model_key": "gptoss", "split": "train",
                           "num_shards": 2, "shard_ports": [8103, 8104],
                           "outdir": "appworld_gptoss", "exp": "np821gptr"}]}
        p = self.root / "manifest.json"
        p.write_text(json.dumps(mf, ensure_ascii=False))
        return p

    # ---- fakes ----

    def make_gen_files(self):
        d = self.root / "envs" / "runs" / "nyapass"
        d.mkdir(parents=True, exist_ok=True)
        for n in D.GEN_FILES:
            (d / n).write_text("# fake\n")
        return d

    def cfg(self):
        return D.load_cfg(self.cfg_path)

    def probes(self, **kw):
        """All injection points are first pinned to defaults that "blow up on the spot";
        the test case only opens up the few it actually needs -- forgetting to inject
        blows up loudly instead of silently falling through to real probing."""
        def boom(name):
            def _f(*a, **k):
                raise AssertionError(f"test case did not inject {name}, yet it was called")
            return _f
        base = {n: boom(n) for n in
                ("git_dirty", "probe_free", "has_session", "local_host",
                 "gpu_used_mb", "http_get", "run_cmd", "boundary_counts",
                 "ledger_names", "record_events")}
        base.update(kw)
        return D.Probes(**base)

    def run_main(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = D.main(list(argv))
        return code, buf.getvalue()

    def read_state(self):
        return json.loads((self.root / "logs" / "pipeline" / "nyapass_aw_v1"
                           / "state.json").read_text())


class TestStepTable(DriverCase):
    def test_step_names_unique_and_callable(self):
        self.assertEqual(len(D.STEP_NAMES), len(set(D.STEP_NAMES)))
        for s in D.STEPS:
            self.assertTrue(callable(s["fn"]), s["name"])
            self.assertIn(s["stage"], ("collect", "annotate", "train", "eval"))

    def test_apply_event_advances_and_finishes(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        self.assertEqual(st["step"], "c1_gen")
        for s in D.STEPS:
            ev, _ = D.advanced("x")
            D.apply_event(st, s, ev)
        self.assertEqual(st["step"], "done")
        self.assertEqual(st["status"], "done")
        self.assertEqual(len(st["history"]), len(D.STEPS))


class TestCollectHead(DriverCase):
    """Design draft section 7, test items 1/2: c1 completes -> c2 dirty tree blocked -> clean-tree launch exits 3."""

    def test_c1_done_then_c2_blocked_on_dirty_tree(self):
        self.make_gen_files()
        with patch.object(D, "git_dirty", lambda: []):
            code, out = self.run_main("--config", str(self.cfg_path))
        self.assertEqual(code, 0)
        st = self.read_state()
        self.assertEqual(st["step"], "c2_servers")
        self.assertEqual(st["status"], "ready")

        with patch.object(D, "git_dirty", lambda: [" M pipeline/driver.py"]):
            code, out = self.run_main("--config", str(self.cfg_path))
        self.assertEqual(code, 1)
        st = self.read_state()          # written to disk and re-readable
        self.assertEqual(st["step"], "c2_servers")
        self.assertEqual(st["status"], "blocked")
        self.assertIn("commit", st["reason"])
        self.assertIn("pipeline/driver.py", st["reason"])

    def test_c2_launches_when_clean_and_free(self):
        self.make_gen_files()
        calls = []

        def fake_run(argv, cwd=None, log=None, env=None):
            calls.append((list(map(str, argv)), str(cwd)))
            return 0, ""

        pr = self.probes(git_dirty=lambda: [],
                         has_session=lambda h, s: False,
                         probe_free=lambda h, g: (True, ""),
                         run_cmd=fake_run)
        cfg = self.cfg()
        ev, code = D.step_c2_servers(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 3)
        self.assertEqual(ev["status"], "launched")
        self.assertTrue(ev["advance"])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0][-1].endswith("launch_servers.py"))
        self.assertEqual(calls[0][1], str(D.run_dir(cfg)))

    def test_c2_skips_probe_when_sessions_already_up(self):
        """Session existence must be checked before probing cards: once the service is
        up it occupies the card itself; getting the order backwards would leave an
        already-launched batch stuck on blocked forever."""
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [],
                         has_session=lambda h, s: True)
        ev, code = D.step_c2_servers(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_c2_blocked_when_gpu_busy(self):
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [],
                         has_session=lambda h, s: False,
                         probe_free=lambda h, g: (False, "busy: 12345, 8MiB"))
        ev, code = D.step_c2_servers(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("G2", ev["event"])
        self.assertIn("busy", ev["detail"])


class TestServerHealth(DriverCase):
    """c3_health: only counts as healthy once the log shows startup complete. When
    the log doesn't have that line yet, branch on whether the tmux session is
    alive -- session still alive counts as warm-up and keeps waiting, session
    gone means blocked; it doesn't share the same exit with warm-up and wait
    forever (review C8)."""

    def servers(self):
        return json.loads(self.manifest_path.read_text())["servers"]

    def write_serve_log(self, idx, healthy=True):
        s = self.servers()[idx]
        p = D.SERVE_LOG_DIR / f"{s['session']}.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"INFO started\n{D.HEALTH_MARK}\n" if healthy
                     else "INFO loading weights\n")
        return s

    def test_c3_advances_when_every_instance_is_green(self):
        for i in range(2):
            self.write_serve_log(i)
        pr = self.probes(http_get=lambda u, **k: (True, "{}"))
        ev, code = D.step_c3_health(self.cfg(), D.fresh_state(self.cfg()), pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertTrue(ev["advance"])

    def test_c3_waits_while_the_session_is_still_alive(self):
        self.write_serve_log(0, healthy=False)
        self.write_serve_log(1, healthy=True)
        pr = self.probes(has_session=lambda h, s: True,
                         http_get=lambda u, **k: (True, "{}"))
        ev, code = D.step_c3_health(self.cfg(), D.fresh_state(self.cfg()), pr)
        self.assertEqual(code, 0)
        self.assertEqual(ev["status"], "ready")
        self.assertFalse(ev["advance"])
        self.assertIn("warming up and wait", ev["detail"])

    def test_c3_blocked_when_the_session_is_gone(self):
        s = self.write_serve_log(0, healthy=False)
        self.write_serve_log(1, healthy=True)
        pr = self.probes(has_session=lambda h, x: False,
                         http_get=lambda u, **k: (True, "{}"))
        ev, code = D.step_c3_health(self.cfg(), D.fresh_state(self.cfg()), pr)
        self.assertEqual(code, 1)
        self.assertIn("session cannot be found", ev["event"])
        self.assertIn(s["session"], ev["detail"])          # which one died
        self.assertIn(f"{s['session']}.log", ev["detail"])  # where to read the log
        self.assertIn("launch_servers.py", ev["detail"])

    def test_c3_waits_when_only_the_http_probe_is_silent(self):
        for i in range(2):
            self.write_serve_log(i)
        pr = self.probes(http_get=lambda u, **k: (False, "curl rc=7"))
        ev, code = D.step_c3_health(self.cfg(), D.fresh_state(self.cfg()), pr)
        self.assertEqual(code, 0)
        self.assertFalse(ev["advance"])
        self.assertIn("curl rc=7", ev["detail"])


class TestManifestHash(DriverCase):
    """Review C9: which manifest the three launch artifacts were generated from
    must match the c2/c5 that actually run them -- if the manifest's card number
    changed but --force regeneration was forgotten, catch it on the spot."""

    def primed(self):
        """c1 claims existing outputs, and while at it records the manifest's sha1 into the state."""
        self.make_gen_files()
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        ev, code = D.step_c1_gen(cfg, st, self.probes())
        self.assertEqual(code, 0)
        self.assertEqual(st["manifest_sha1"], D.manifest_sha1(cfg))
        return st

    def bump_manifest(self):
        mf = json.loads(self.manifest_path.read_text())
        mf["servers"][0]["gpu"] = 7
        mf["servers"][0]["session"] = "new1_nyapass_srv_gptossa_t108g7"
        self.manifest_path.write_text(json.dumps(mf, ensure_ascii=False))

    def test_c1_records_the_hash_when_it_generates(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        pr = self.probes(run_cmd=lambda a, **k: (self.make_gen_files()
                                                 and (0, "")))
        ev, code = D.step_c1_gen(cfg, st, pr)
        self.assertEqual(code, 0)
        self.assertEqual(st["manifest_sha1"], D.manifest_sha1(cfg))

    def test_c2_blocked_when_the_manifest_changed_after_generation(self):
        st = self.primed()
        self.bump_manifest()
        ev, code = D.step_c2_servers(self.cfg(), st, self.probes())
        self.assertEqual(code, 1)
        self.assertIn("gen-launch", ev["detail"])
        self.assertIn("--force", ev["detail"])
        self.assertIn("manifest_sha1", ev["detail"])

    def test_c2_proceeds_when_the_manifest_is_unchanged(self):
        st = self.primed()
        pr = self.probes(git_dirty=lambda: [], has_session=lambda h, s: True)
        ev, code = D.step_c2_servers(self.cfg(), st, pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertTrue(ev["advance"])

    def test_c2_backfills_a_missing_hash_instead_of_blocking(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)             # the old state file doesn't have this key
        self.assertNotIn("manifest_sha1", st)
        pr = self.probes(git_dirty=lambda: [], has_session=lambda h, s: True)
        ev, code = D.step_c2_servers(cfg, st, pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertEqual(st["manifest_sha1"], D.manifest_sha1(cfg))

    def test_c5_blocked_when_the_manifest_changed(self):
        st = self.primed()
        self.bump_manifest()
        ev, code = D.step_c5_clients(self.cfg(), st, self.probes())
        self.assertEqual(code, 1)
        self.assertIn("launch_clients.sh", ev["detail"])

    def test_c5_backfills_a_missing_hash(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        pr = self.probes(git_dirty=lambda: [], local_host=lambda: "tokyo105",
                         has_session=lambda h, s: True,
                         ledger_names=lambda: {"nyapass", "nyapass_srv_a",
                                               "nyapass_srv_b"},
                         record_events=lambda: {"nyapass": {"start"}},
                         run_cmd=lambda a, **k: (0, ""))
        ev, code = D.step_c5_clients(cfg, st, pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertEqual(st["manifest_sha1"], D.manifest_sha1(cfg))


class TestSmokeGate(DriverCase):
    """Design draft section 7, test item 3: c4's G4 criterion."""

    def write_smoke(self, cfg, seeds=None, n=None, final=True):
        d = D.smoke_dir(cfg)
        seeds = seeds if seeds is not None else D.seeds_of(cfg)
        n = n if n is not None else self.k
        for i in range(n):
            write_traj(d / f"appworld_{self.tids[0]}_r{i}.jsonl",
                       self.tids[0], seeds[i], final=final)
        return d

    def test_c4_passes_when_files_and_seeds_line_up(self):
        cfg = self.cfg()
        self.write_smoke(cfg)
        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_c4_blocked_when_a_file_is_missing(self):
        cfg = self.cfg()
        self.write_smoke(cfg, n=3)
        pr = self.probes(run_cmd=lambda *a, **k: (0, ""))
        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("3 trajectory files", ev["detail"])

    def test_c4_blocked_when_seed_is_wrong(self):
        cfg = self.cfg()
        self.write_smoke(cfg, seeds=[42, 67, 4267, 999])
        pr = self.probes(run_cmd=lambda *a, **k: (0, ""))
        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("_r3", ev["detail"])
        self.assertIn("6742", ev["detail"])

    def test_c4_blocked_when_tail_is_not_final(self):
        cfg = self.cfg()
        self.write_smoke(cfg, final=False)
        pr = self.probes(run_cmd=lambda *a, **k: (0, ""))
        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("last line is not type=final", ev["detail"])

    def test_c4_blocked_when_the_seed_table_is_short(self):
        """Seed table shorter than K: return blocked for that entry that's ready, must
        not raise IndexError (review C10). The scenario is a previous round that
        produced 4 files with a full seed table, and a manual config edit dropped two
        seeds."""
        self.write_cfg(collect={"manifest": "manifest.json",
                                "run_id": "nyapass", "seeds": [42, 67]})
        cfg = self.cfg()
        self.write_smoke(cfg, seeds=[42, 67, 4267, 6742])
        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("seed table", ev["event"])
        self.assertIn("2", ev["detail"])

    def test_smoke_traj_check_does_not_index_past_the_seed_table(self):
        cfg = self.cfg()
        d = self.write_smoke(cfg)
        ok, why = D.smoke_traj_check(d, self.k, [42, 67], "appworld")
        self.assertFalse(ok)
        self.assertIn("seed table", why)

    def test_c4_command_carries_multisample_flags(self):
        cfg = self.cfg()
        seen = []

        def fake_run(argv, cwd=None, log=None, env=None):
            seen.append([str(a) for a in argv])
            self.write_smoke(cfg)
            return 0, ""

        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(run_cmd=fake_run))
        self.assertEqual(code, 0)
        argv = seen[0]
        self.assertIn("collect-aw", argv)
        self.assertIn("--traj-per-task", argv)
        self.assertEqual(argv[argv.index("--traj-per-task") + 1], "4")
        self.assertEqual(argv[argv.index("--seeds") + 1], "42,67,4267,6742")
        self.assertEqual(argv[argv.index("--preset") + 1], "default")
        self.assertEqual(argv[argv.index("--model") + 1], "gpt-oss-120b")


class TestCollectDone(DriverCase):
    """Design draft section 7, test item 5: c6's G6/G7."""

    def fill_outdir(self, cfg, n_units=None, k=None):
        d = D.outdir_of(cfg)
        n_units = self.n_units if n_units is None else n_units
        k = self.k if k is None else k
        for tid in self.tids[:n_units]:
            for i in range(k):
                write_traj(d / f"appworld_{tid}_r{i}.jsonl", tid,
                           D.seeds_of(cfg)[i])
        return d

    def test_c6_advances_when_all_trajs_are_in(self):
        cfg = self.cfg()
        self.fill_outdir(cfg)
        calls = []

        def fake_run(argv, cwd=None, log=None, env=None):
            calls.append([str(a) for a in argv])
            return 0, ""

        pr = self.probes(local_host=lambda: "tokyo105",
                         has_session=lambda h, s: False,
                         gpu_used_mb=lambda h, g: 0,
                         ledger_names=lambda: {"nyapass", "nyapass_srv_a"},
                         record_events=lambda: {"nyapass": {"start"}},
                         run_cmd=fake_run)
        ev, code = D.step_c6_done(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertTrue(ev["advance"])
        joined = [" ".join(c) for c in calls]
        self.assertTrue(any("gpu-jobs finish nyapass" in j for j in joined))
        self.assertTrue(any("record finish nyapass" in j for j in joined))

    def test_c6_blocked_when_short_and_clients_dead(self):
        cfg = self.cfg()
        self.fill_outdir(cfg, n_units=2)
        pr = self.probes(local_host=lambda: "tokyo105",
                         has_session=lambda h, s: False)
        ev, code = D.step_c6_done(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("8 trajectory files", ev["detail"])
        self.assertIn("--resume", ev["detail"])

    def test_c6_waits_while_clients_alive(self):
        cfg = self.cfg()
        self.fill_outdir(cfg, n_units=2)
        pr = self.probes(local_host=lambda: "tokyo105",
                         has_session=lambda h, s: True)
        ev, code = D.step_c6_done(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0)
        self.assertFalse(ev["advance"])
        self.assertIn("still alive", ev["detail"])

    def test_c6_blocked_when_gpu_memory_not_free(self):
        cfg = self.cfg()
        self.fill_outdir(cfg)
        pr = self.probes(local_host=lambda: "tokyo105",
                         has_session=lambda h, s: False,
                         gpu_used_mb=lambda h, g: 41000)
        ev, code = D.step_c6_done(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("G7", ev["event"])
        self.assertIn("41000", ev["detail"])

    def test_c6_treats_unprobeable_gpu_as_not_free(self):
        cfg = self.cfg()
        self.fill_outdir(cfg)
        pr = self.probes(local_host=lambda: "tokyo105",
                         has_session=lambda h, s: False,
                         gpu_used_mb=lambda h, g: None)
        ev, code = D.step_c6_done(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("GPU memory cannot be probed", ev["detail"])


class TestAnnotateStop(DriverCase):
    """Design draft section 7, test item 4: a1's max_bounds stopping point."""

    def test_a1_awaits_decision_without_max_bounds(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        pr = self.probes(boundary_counts=lambda c: [1, 5, 40, 70, 300])
        ev, code = D.step_a1_stats(cfg, st, pr)
        self.assertEqual(code, 4)
        self.assertEqual(ev["status"], "awaiting_decision")
        self.assertIn("max_bounds", ev["decision_needed"])
        self.assertEqual(st["cutpoint_stats"]["n_events"], 5)
        self.assertEqual(st["cutpoint_stats"]["max"], 300)
        self.assertEqual(st["cutpoint_stats"]["over_64"], 2)
        self.assertFalse(ev["advance"])

    def test_a1_skips_stop_when_max_bounds_is_decided(self):
        self.write_cfg(max_bounds=64)
        cfg = self.cfg()
        ev, code = D.step_a1_stats(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])
        self.assertIn("64", ev["detail"])

    def test_a1_blocked_when_no_events(self):
        cfg = self.cfg()
        pr = self.probes(boundary_counts=lambda c: [])
        ev, code = D.step_a1_stats(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)


class TestStateFile(DriverCase):
    """Design draft section 7, test items 6/7: state-file overwrite rejection + --status read-only."""

    def prime(self):
        self.make_gen_files()
        with patch.object(D, "git_dirty", lambda: []):
            code, _ = self.run_main("--config", str(self.cfg_path))
        self.assertEqual(code, 0)
        return self.root / "logs" / "pipeline" / "nyapass_aw_v1" / "state.json"

    def test_refuses_corrupt_state(self):
        p = self.prime()
        p.write_text("{ this isn't json")
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path))
        self.assertIn("cannot read state file", str(cm.exception))
        self.assertEqual(p.read_text(), "{ this isn't json")   # wasn't overwritten

    def test_refuses_state_with_unknown_step(self):
        p = self.prime()
        st = json.loads(p.read_text())
        st["step"] = "c9_nonexistent"
        p.write_text(json.dumps(st))
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path))
        self.assertIn("unrecognized step name", str(cm.exception))

    def test_refuses_state_of_another_batch(self):
        """The batch identity changed (following run.py recipe's params-consistency precedent): reject the overwrite."""
        p = self.prime()
        before = p.read_text()
        self.write_cfg(model_full="gpt-oss-20b")
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path))
        self.assertIn("refusing to overwrite", str(cm.exception))
        self.assertEqual(p.read_text(), before)

    def test_status_is_read_only(self):
        p = self.prime()
        before = p.read_text()
        code, out = self.run_main("--config", str(self.cfg_path), "--status")
        self.assertEqual(code, 0)
        self.assertEqual(p.read_text(), before)
        self.assertIn("c2_servers", out)
        self.assertIn("nyapass_aw_v1", out)

    def test_status_shows_launch_markers(self):
        """Marks something that needs a human to act on it (a dead batch has to be deleted by a human), so --status must print it."""
        p = self.prime()
        st = json.loads(p.read_text())
        D.mark_launched(st, D.launch_key("t2_full", "np821b06"), "full")
        p.write_text(json.dumps(st, ensure_ascii=False))
        code, out = self.run_main("--config", str(self.cfg_path), "--status")
        self.assertEqual(code, 0)
        self.assertIn("launch marker", out)
        self.assertIn("t2_full:np821b06", out)

    def test_status_on_fresh_run_writes_nothing(self):
        code, out = self.run_main("--config", str(self.cfg_path), "--status")
        self.assertEqual(code, 0)
        self.assertIn("c1_gen", out)
        self.assertFalse((self.root / "logs" / "pipeline" / "nyapass_aw_v1"
                          / "state.json").exists())

    def test_atomic_write_leaves_no_tmp(self):
        p = self.prime()
        self.assertTrue(p.exists())
        self.assertFalse((p.parent / "state.json.tmp").exists())

    def test_unknown_flag_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path), "--force")
        self.assertIn("unrecognized argument", str(cm.exception))


class TestGenStep(DriverCase):
    def test_c1_runs_gen_launch_when_nothing_is_there(self):
        seen = []

        def fake_run(argv, cwd=None, log=None, env=None):
            seen.append([str(a) for a in argv])
            self.make_gen_files()
            return 0, ""

        cfg = self.cfg()
        ev, code = D.step_c1_gen(cfg, D.fresh_state(cfg),
                                 self.probes(run_cmd=fake_run))
        self.assertEqual(code, 0)
        self.assertIn("gen-launch", seen[0])
        self.assertEqual(seen[0][seen[0].index("--config") + 1],
                         str(self.manifest_path))

    def test_c1_blocked_on_half_a_set(self):
        d = self.root / "envs" / "runs" / "nyapass"
        d.mkdir(parents=True)
        (d / "MANIFEST.md").write_text("x")
        cfg = self.cfg()
        ev, code = D.step_c1_gen(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("--force", ev["detail"])


class TestHelpers(DriverCase):
    def test_client_sessions_follow_gen_launch_naming(self):
        cfg = self.cfg()
        self.assertEqual(D.client_sessions(cfg),
                         ["new1_nyapass_gptr_s0", "new1_nyapass_gptr_s1"])

    def test_pct_matches_the_build_report_definition(self):
        """The p50/p90/p99 the driver prints and the ones archived in ANNOTATE_REPORT
        must be the same numbers: both sides use index-style floor (review C4; the
        driver used to do ceil-nearest-rank, which was off by one slot from build
        when q*n is an integer)."""
        s = list(range(1, 101))
        self.assertEqual(D.pct(s, 0.5), 51)
        self.assertEqual(D.pct(s, 0.9), 91)
        self.assertEqual(D.pct(s, 0.99), 100)

        def q(vals, p):        # q() from pipeline/annotate/build.py:468, copied verbatim
            return vals[min(len(vals) - 1, int(len(vals) * p))]

        for n in (1, 2, 3, 7, 10, 20, 100, 137, 1000):
            vals = list(range(n))
            for p in (0.5, 0.9, 0.99):
                self.assertEqual(D.pct(vals, p), q(vals, p), (n, p))

    def test_file_contains_spans_block_boundary(self):
        p = self.root / "big.log"
        mark = D.HEALTH_MARK
        head = "a" * (1 << 20) + mark[:5]
        p.write_text(head + mark[5:] + "\nrest\n")
        self.assertTrue(D.file_contains(p, mark))
        self.assertFalse(D.file_contains(p, "this sentence isn't there"))

    def test_placement_paths_are_per_batch(self):
        cfg = self.cfg()
        self.assertTrue(str(D.placement_of(cfg, "np821b06"))
                        .endswith("ops/np821b06_placement.json"))
        self.assertTrue(str(D.placement_of(cfg, "np821b06", "eval_tool"))
                        .endswith("ops/np821b06_eval_tool_placement.json"))

    def test_run_dir_honors_manifest_envs_root(self):
        # gen_launch honors the manifest's envs_root override, the driver's completion
        # criterion must look in the same place (a real bug caught by the 2026-08-22
        # dry-run acceptance check: it used to hardcode ROOT/envs)
        other = self.root / "elsewhere"
        mf = json.loads(self.manifest_path.read_text())
        mf["envs_root"] = str(other)
        self.manifest_path.write_text(json.dumps(mf, ensure_ascii=False))
        self.assertEqual(D.run_dir(self.cfg()), other / "runs" / "nyapass")

    def test_run_dir_falls_back_when_manifest_missing(self):
        cfg = self.cfg()
        cfg["collect"]["manifest"] = str(self.root / "no_such_manifest.json")
        cfg.pop("_manifest", None)
        self.assertEqual(D.run_dir(cfg),
                         D.ROOT / "envs" / "runs" / "nyapass")

    def test_theta_all_null_needs_a_readable_report(self):
        run = self.root / "r"
        run.mkdir()
        self.assertFalse(D.theta_all_null(run))
        (run / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": None, "0.1": None}}))
        self.assertTrue(D.theta_all_null(run))
        (run / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": None, "0.1": 0.9}}))
        self.assertFalse(D.theta_all_null(run))
        (run / "REPLAY_REPORT.json").write_text("bad file")
        self.assertFalse(D.theta_all_null(run))


class TestClientLaunch(DriverCase):
    """c5: launches client pieces + G16 the three registrations (already-registered ones are skipped)."""

    def test_c5_fires_and_registers_three_places(self):
        cfg = self.cfg()
        seen = []

        def fake_run(argv, cwd=None, log=None, env=None):
            seen.append([str(a) for a in argv])
            return 0, ""

        pr = self.probes(git_dirty=lambda: [], local_host=lambda: "tokyo105",
                         has_session=lambda h, s: False,
                         ledger_names=lambda: set(), record_events=lambda: {},
                         run_cmd=fake_run)
        ev, code = D.step_c5_clients(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 3)
        self.assertTrue(ev["advance"])
        joined = [" ".join(c) for c in seen]
        self.assertTrue(any(c[0] == "bash" for c in seen))
        self.assertTrue(any("gpu-jobs register --name nyapass " in j
                            for j in joined))
        self.assertTrue(any("--name nyapass_srv_a" in j for j in joined))
        self.assertTrue(any("--name nyapass_srv_b" in j for j in joined))
        self.assertTrue(any("--kind service" in j for j in joined))
        self.assertTrue(any("record start --run-id nyapass" in j for j in joined))
        self.assertTrue(any("runmeta" in j for j in joined))

    def test_c5_skips_registrations_already_done(self):
        cfg = self.cfg()
        seen = []
        pr = self.probes(git_dirty=lambda: [], local_host=lambda: "tokyo105",
                         has_session=lambda h, s: True,
                         ledger_names=lambda: {"nyapass", "nyapass_srv_a",
                                               "nyapass_srv_b"},
                         record_events=lambda: {"nyapass": {"start"}},
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_c5_clients(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0)             # not 3 if nothing was launched
        self.assertTrue(ev["advance"])
        # only the RUNMETA entry remains (append doesn't overwrite; adding a duplicate entry is expected behavior)
        self.assertEqual(len(seen), 1)
        self.assertIn("runmeta", seen[0])

    def test_c5_blocked_on_dirty_tree(self):
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [" M a.py", " M b.py"])
        ev, code = D.step_c5_clients(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("commit", ev["detail"])


class TestAnnotateBuildGates(DriverCase):
    """a2/a3: whether the outputs are complete + G9 task list + byte-for-byte rebuild comparison."""

    def make_artifacts(self):
        out = self.data_out
        for rel in D.annotate_artifacts(self.cfg()):
            p = out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"content of {rel}\n")
        return out

    def test_a2_advances_when_artifacts_are_there(self):
        self.make_artifacts()
        cfg = self.cfg()
        ev, code = D.step_a2_build(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_a2_runs_the_chain_then_rechecks(self):
        cfg = self.cfg()
        seen = []

        def fake_run(argv, cwd=None, log=None, env=None):
            seen.append([str(a) for a in argv])
            self.make_artifacts()
            return 0, ""

        ev, code = D.step_a2_build(cfg, D.fresh_state(cfg),
                                   self.probes(run_cmd=fake_run))
        self.assertEqual(code, 0)
        self.assertIn("annotate-chain", seen[0])

    def test_a2_blocked_when_chain_leaves_holes(self):
        cfg = self.cfg()
        pr = self.probes(run_cmd=lambda a, **k: (0, ""))
        ev, code = D.step_a2_build(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("the artifacts are incomplete", ev["event"])

    def test_a3_passes_when_rebuild_is_byte_identical(self):
        self.make_artifacts()
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg),
                                   self.probes(run_cmd=lambda a, **k: (0, "")))
        self.assertEqual(code, 0, ev["detail"])
        self.assertTrue(ev["advance"])
        self.assertFalse((self.data_out.parent
                          / f"{self.data_out.name}_rebuild_ref").exists())

    def test_a3_blocked_when_rebuild_differs(self):
        self.make_artifacts()
        cfg = self.cfg()

        def fake_run(argv, cwd=None, log=None, env=None):
            (self.data_out / "train.jsonl").write_text("rebuilt result differs\n")
            return 0, ""

        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg),
                                   self.probes(run_cmd=fake_run))
        self.assertEqual(code, 1)
        self.assertIn("train.jsonl", ev["detail"])
        ref = self.data_out.parent / f"{self.data_out.name}_rebuild_ref"
        self.assertTrue(ref.is_dir())          # keep the evidence
        self.assertEqual((ref / "train.jsonl").read_text(),
                         "content of train.jsonl\n")

    def test_a3_refuses_when_an_old_ref_dir_is_left_over(self):
        self.make_artifacts()
        (self.data_out.parent / f"{self.data_out.name}_rebuild_ref").mkdir()
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("the backup from the last rebuild comparison is still there", ev["event"])

    def test_a3_blocked_when_a_task_id_is_in_two_splits(self):
        self.make_artifacts()
        Path(self.split_files["val"]).write_text(self.tids[0])
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("is in both train and val piles", ev["detail"])

    def test_a3_blocked_when_qa_sample_is_missing(self):
        self.make_artifacts()
        (self.data_out / "qa_sample.txt").unlink()
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("G11", ev["event"])


class TestLaterStages(DriverCase):
    """The transition logic for t1..m1 (criteria use fake outputs, launching uses a
    fake run_cmd). These steps actually run in the execution block; what's pinned
    down here is "blocked and no green light when the criteria aren't met" and
    "one call launches only one batch"."""

    batch = "np821b06"
    cells = ("ctool", "cgen", "cparam")

    def rid(self, cell):
        return f"{self.batch}_gptoss_{cell}"

    def write_train_log(self, d, losses, done=False, align=None,
                        start=True, best=False):
        """A fake train_log.jsonl. However many numbers `losses` is given, that many
        event=step records get written -- in a real run one gets written only every
        50 optimizer steps, and smoke only runs 6-16 steps, so in reality the smoke
        log usually has zero of them (review C6); the count here is built to match
        "however many actually get written to disk"."""
        d.mkdir(parents=True, exist_ok=True)
        rows = [{"event": "start", "steps": len(losses)}] if start else []
        rows += [{"event": "step", "ep": 0, "gstep": i + 1, "loss": x}
                 for i, x in enumerate(losses)]
        if done:
            rows.append({"event": "done", "best_calA_weighted_acc": 0.9})
        (d / "train_log.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
        if best:
            (d / "best").mkdir(parents=True, exist_ok=True)
        if align is not None:
            (d / "ALIGN_CHECK.json").write_text(
                json.dumps({"PASS": align, "maxdiff_hidden": 1e-5}))

    def smoke_dir_of(self, cell):
        return D.RUNS_DIR / "smoke" / f"{self.rid(cell)}_smoke"

    def make_smokes(self, ok=True, losses=None, **over):
        """Fake outputs for the three-cell smoke test. Default = what one clean run
        looks like: start + done + best/, ctool additionally has ALIGN_CHECK PASS."""
        for c in self.cells:
            opts = dict(done=True, best=True,
                        align=True if c == "ctool" else None)
            opts.update(over)
            self.write_train_log(
                self.smoke_dir_of(c),
                losses if losses is not None else ([2.0, 1.0] if ok
                                                   else [1.0, 2.0]),
                **opts)

    def make_full_runs(self, done=True):
        for c in self.cells:
            d = D.RUNS_DIR / self.rid(c)
            self.write_train_log(d, [2.0, 1.0], done=done)
            (d / "best").mkdir(parents=True, exist_ok=True)

    def make_placement(self, stage=""):
        d = self.root / "ops"
        d.mkdir(parents=True, exist_ok=True)
        tail = f"_{stage}_placement.json" if stage else "_placement.json"
        p = d / f"{self.batch}{tail}"
        p.write_text(json.dumps([{"model": "gptoss", "cell": "ctool",
                                  "host": "tokyo108", "gpu": 0}]))
        return p

    def test_t1_blocked_until_smoke_criteria_hold(self):
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("launch-probe smoke", ev["detail"])
        self.make_smokes(ok=False)
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("loss did not drop", ev["detail"])
        self.make_smokes(ok=True)
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_t1_passes_with_zero_step_records(self):
        """In reality the smoke log has zero event=step entries (one gets written only
        every 50 optimizer steps, and smoke only runs 6-16 steps): start + done +
        best/ all being present counts as passing, and detail records a line saying
        the loss sequence was too short to judge (review C6)."""
        cfg = self.cfg()
        self.make_smokes(losses=[])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 0, ev["detail"])
        self.assertTrue(ev["advance"])
        self.assertIn("too short", ev["detail"])
        self.assertIn("only 0 event=step records", ev["detail"])

    def test_t1_blocked_when_done_is_missing(self):
        """Done = train_log has an event=done entry. Missing done never gets a green light."""
        cfg = self.cfg()
        self.make_smokes(losses=[], done=False)
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 1)
        self.assertIn("event=done", ev["detail"])

    def test_t1_blocked_when_best_dir_is_missing(self):
        cfg = self.cfg()
        self.make_smokes(losses=[], best=False)
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 1)
        self.assertIn("does not exist", ev["detail"])

    def test_t1_blocked_when_start_is_missing(self):
        cfg = self.cfg()
        self.make_smokes(losses=[], start=False)
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 1)
        self.assertIn("event=start", ev["detail"])

    def test_t1_blocked_when_ctool_align_check_fails(self):
        cfg = self.cfg()
        self.make_smokes(losses=[])
        (self.smoke_dir_of("ctool") / "ALIGN_CHECK.json").write_text(
            json.dumps({"PASS": False, "maxdiff_hidden": 0.4}))
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 1)
        self.assertIn("PASS=False", ev["detail"])

    def test_t1_loss_check_only_engages_from_two_step_records(self):
        """One record: don't judge whether it dropped, pass. Two records and it didn't drop: block."""
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [])
        self.make_smokes(losses=[9.9])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertIn("only 1 event=step records", ev["detail"])
        self.make_smokes(losses=[1.0, 2.0])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("loss did not drop", ev["detail"])
        self.make_smokes(losses=[2.0, 1.5, 1.0])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertNotIn("too short", ev["detail"])

    def test_t1_blocked_on_dirty_tree_before_anything_else(self):
        cfg = self.cfg()
        self.make_smokes(ok=True)
        pr = self.probes(git_dirty=lambda: [" M x.py"])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("commit", ev["detail"])

    def test_t2_launches_one_batch_and_stays_put(self):
        cfg = self.cfg()
        self.make_placement()
        seen = []
        pr = self.probes(git_dirty=lambda: [],
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_t2_full(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 3)
        self.assertFalse(ev["advance"])       # pointer doesn't move, check again once it's done
        self.assertIn("launch-probe", seen[0])
        self.assertIn("full", seen[0])

    def test_t2_blocked_without_placement(self):
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [])
        ev, code = D.step_t2_full(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("_placement.json", ev["detail"])

    def test_t2_advances_when_every_run_is_done(self):
        cfg = self.cfg()
        self.make_full_runs(done=True)
        ev, code = D.step_t2_full(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_t2_counts_a_run_without_done_as_pending(self):
        cfg = self.cfg()
        self.make_full_runs(done=False)
        pr = self.probes(git_dirty=lambda: [])
        ev, code = D.step_t2_full(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)             # no card schedule -> blocked, not a green light
        self.assertIn("_placement.json", ev["detail"])

    # ---- launch marker (review C2/C7): the same batch launches only once, once launched it only waits and doesn't relaunch ----

    def test_t2_marks_the_launch_and_never_relaunches_the_same_batch(self):
        cfg = self.cfg()
        self.make_placement()
        st = D.fresh_state(cfg)
        seen = []
        pr = self.probes(git_dirty=lambda: [],
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_t2_full(cfg, st, pr)
        self.assertEqual(code, 3)
        self.assertEqual(len(seen), 1)
        self.assertIn(D.launch_key("t2_full", self.batch), st["launched"])
        # Second check: criteria still not met, marker present -> wait, exit 0,
        # launcher must not be called again even once (self.probes()'s run_cmd is a
        # fake that blows up if called)
        ev, code = D.step_t2_full(cfg, st, self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 0)
        self.assertEqual(ev["status"], "ready")
        self.assertFalse(ev["advance"])
        self.assertIn("not relaunching this time", ev["event"])      # not the fake "already launched this time" line
        self.assertIn("gpu-jobs", ev["detail"])
        self.assertEqual(len(seen), 1)

    def test_t2_advances_even_when_the_marker_is_there(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        D.mark_launched(st, D.launch_key("t2_full", self.batch), "full")
        self.make_full_runs(done=True)
        ev, code = D.step_t2_full(cfg, st, self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_t2_does_not_mark_when_the_launcher_fails(self):
        cfg = self.cfg()
        self.make_placement()
        st = D.fresh_state(cfg)
        pr = self.probes(git_dirty=lambda: [], run_cmd=lambda a, **k: (2, "boom"))
        ev, code = D.step_t2_full(cfg, st, pr)
        self.assertEqual(code, 1)
        self.assertEqual(st["launched"], {})

    def test_e1_marks_the_launch_and_waits_next_time(self):
        cfg = self.cfg()
        self.make_placement("eval_tool")
        st = D.fresh_state(cfg)
        seen = []
        pr = self.probes(git_dirty=lambda: [],
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_e1_tool(cfg, st, pr)
        self.assertEqual(code, 3)
        self.assertIn(D.launch_key("e1_tool", self.batch), st["launched"])
        ev, code = D.step_e1_tool(cfg, st, self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 0)
        self.assertFalse(ev["advance"])
        self.assertIn("gpu-jobs", ev["detail"])
        self.assertEqual(len(seen), 1)
        # once the report is out, advance regardless, marker present or not doesn't matter
        d = D.RUNS_DIR / self.rid("ctool")
        d.mkdir(parents=True, exist_ok=True)
        (d / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": 0.9, "0.1": 0.8}}))
        ev, code = D.step_e1_tool(cfg, st, self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_e2_marks_the_launch_and_waits_next_time(self):
        cfg = self.cfg()
        d = D.RUNS_DIR / self.rid("ctool")
        d.mkdir(parents=True, exist_ok=True)
        (d / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": 0.9, "0.1": 0.8}}))
        self.make_placement("eval_call")
        st = D.fresh_state(cfg)
        seen = []
        pr = self.probes(git_dirty=lambda: [],
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_e2_call(cfg, st, pr)
        self.assertEqual(code, 3)
        self.assertIn(D.launch_key("e2_call", self.batch), st["launched"])
        ev, code = D.step_e2_call(cfg, st, self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 0)
        self.assertFalse(ev["advance"])
        self.assertIn("gpu-jobs", ev["detail"])
        self.assertEqual(len(seen), 1)

    def test_launch_markers_survive_save_and_load_and_do_not_collide(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        D.mark_launched(st, D.launch_key("t2_full", self.batch), "full")
        D.mark_launched(st, D.launch_key("e1_tool", self.batch), "tool")
        D.save_state(cfg, st)
        back = D.load_state(self.cfg())
        self.assertEqual(sorted(back["launched"]),
                         [f"e1_tool:{self.batch}", f"t2_full:{self.batch}"])
        self.assertTrue(back["launched"][f"t2_full:{self.batch}"]["t"])
        self.assertNotEqual(D.launch_key("t2_full", "b1"),
                            D.launch_key("e1_tool", "b1"))
        self.assertNotEqual(D.launch_key("t2_full", "b1"),
                            D.launch_key("t2_full", "b2"))

    def test_old_state_without_the_launched_key_counts_as_never_launched(self):
        cfg = self.cfg()
        st = D.fresh_state(cfg)
        st.pop("launched")
        D.save_state(cfg, st)
        back = D.load_state(self.cfg())
        self.assertEqual(back["launched"], {})

    def test_t3_checks_three_registrations(self):
        cfg = self.cfg()
        self.make_full_runs()
        ev, code = D.step_t3_close(
            cfg, D.fresh_state(cfg),
            self.probes(ledger_names=lambda: set(), record_events=lambda: {}))
        self.assertEqual(code, 1)
        self.assertIn("RUNMETA.json", ev["detail"])
        for c in self.cells:
            (D.RUNS_DIR / self.rid(c) / "RUNMETA.json").write_text("{}")
        evs = {self.rid(c): {"start"} for c in self.cells}
        ev, code = D.step_t3_close(
            cfg, D.fresh_state(cfg),
            self.probes(ledger_names=lambda: set(), record_events=lambda: evs))
        self.assertEqual(code, 1)
        self.assertIn("record finish", ev["detail"])
        evs = {self.rid(c): {"start", "finish"} for c in self.cells}
        ev, code = D.step_t3_close(
            cfg, D.fresh_state(cfg),
            self.probes(ledger_names=lambda: set(), record_events=lambda: evs))
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_t3_blocks_while_still_in_the_ledger(self):
        cfg = self.cfg()
        self.make_full_runs()
        for c in self.cells:
            (D.RUNS_DIR / self.rid(c) / "RUNMETA.json").write_text("{}")
        evs = {self.rid(c): {"start", "finish"} for c in self.cells}
        ev, code = D.step_t3_close(
            cfg, D.fresh_state(cfg),
            self.probes(ledger_names=lambda: {self.rid("ctool")},
                        record_events=lambda: evs))
        self.assertEqual(code, 1)
        self.assertIn("gpu-jobs finish", ev["detail"])

    def test_e1_launches_then_advances(self):
        cfg = self.cfg()
        self.make_placement("eval_tool")
        seen = []
        pr = self.probes(git_dirty=lambda: [],
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_e1_tool(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 3)
        self.assertFalse(ev["advance"])
        self.assertIn("launch-eval", seen[0])
        d = D.RUNS_DIR / self.rid("ctool")
        d.mkdir(parents=True, exist_ok=True)
        (d / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": 0.9, "0.1": 0.8}}))
        ev, code = D.step_e1_tool(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_e2_records_na_when_theta_is_null_in_both_risks(self):
        cfg = self.cfg()
        d = D.RUNS_DIR / self.rid("ctool")
        d.mkdir(parents=True, exist_ok=True)
        (d / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": None, "0.1": None}}))
        st = D.fresh_state(cfg)
        ev, code = D.step_e2_call(cfg, st, self.probes())
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])
        self.assertEqual(st["theta_na_batches"], [self.batch])

    def test_e2_launches_when_reports_are_missing(self):
        cfg = self.cfg()
        d = D.RUNS_DIR / self.rid("ctool")
        d.mkdir(parents=True, exist_ok=True)
        (d / "REPLAY_REPORT.json").write_text(
            json.dumps({"chosen_theta": {"0.05": 0.9, "0.1": 0.8}}))
        self.make_placement("eval_call")
        seen = []
        pr = self.probes(git_dirty=lambda: [],
                         run_cmd=lambda a, **k: (seen.append([str(x) for x in a])
                                                 or (0, "")))
        ev, code = D.step_e2_call(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 3)
        self.assertIn("call", seen[0])

    def test_m1_makes_one_matrix_per_batch_and_risk(self):
        cfg = self.cfg()
        seen = []

        def fake_run(argv, cwd=None, log=None, env=None):
            argv = [str(a) for a in argv]
            seen.append(argv)
            Path(argv[argv.index("--out") + 1]).parent.mkdir(parents=True,
                                                             exist_ok=True)
            Path(argv[argv.index("--out") + 1]).write_text("# matrix\n")
            return 0, ""

        ev, code = D.step_m1_matrix(cfg, D.fresh_state(cfg),
                                    self.probes(run_cmd=fake_run))
        self.assertEqual(code, 0)
        self.assertEqual(len(seen), 2)        # one batch x two risk profiles
        risks = sorted(a[a.index("--risk") + 1] for a in seen)
        self.assertEqual(risks, ["0.05", "0.1"])
        ev, code = D.step_m1_matrix(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)             # once the output exists, don't run again


class TestRealConfigs(unittest.TestCase):
    """The two checked-in configs themselves: fields are complete, paths exist, ports/seeds line up."""

    def test_np821_config_loads(self):
        cfg = D.load_cfg(REPO / "pipeline" / "configs" / "np821_gptoss.json")
        self.assertEqual(cfg["run_family"], "nyapass_aw_v1")
        self.assertEqual(cfg["weight_mode"], "uniform")
        self.assertEqual(cfg["trajs_per_unit"], 4)
        self.assertEqual(cfg["collect"]["seeds"], [42, 67, 4267, 6742])
        # The a1 stopping point was ruled on 2026-08-22 (ruling 2): keeping 64 must
        # also be written explicitly into the config, and from now on the driver builds
        # data by this value; without it a1 will stop again waiting for a ruling.
        self.assertEqual(cfg["max_bounds"], 64)
        for p in cfg["official_split_files"].values():
            self.assertTrue(Path(p).is_file(), p)
        self.assertTrue(D.manifest_path(cfg).is_file())

    def test_np821_manifest_matches_config(self):
        cfg = D.load_cfg(REPO / "pipeline" / "configs" / "np821_gptoss.json")
        mf = json.loads(D.manifest_path(cfg).read_text())
        self.assertEqual(mf["run_id"], cfg["collect"]["run_id"])
        self.assertEqual(mf["traj_per_task"], cfg["trajs_per_unit"])
        self.assertEqual(mf["seed_family"], cfg["collect"]["seeds"])
        self.assertEqual(mf["gptoss_client_preset"], "default")
        self.assertEqual(len(mf["servers"]), 4)
        ports = [s["port"] for s in mf["servers"]]
        self.assertEqual(len(set(ports)), 4)
        self.assertEqual(len(set(s["gpu"] for s in mf["servers"])), 4)
        self.assertEqual(len(set(s["session"] for s in mf["servers"])), 4)
        shards = [p for c in mf["clients"] for p in c["shard_ports"]]
        self.assertEqual(len(shards), 12)
        self.assertEqual(sorted(set(shards)), sorted(ports))
        for p in ports:                          # three pieces per port across four ports, spread evenly
            self.assertEqual(shards.count(p), 3)
        for c in mf["clients"]:
            self.assertEqual(len(c["shard_ports"]), c["num_shards"])

    def test_registry_entry(self):
        sys.path.insert(0, str(REPO))
        import run as R
        t = R.TASKS["pipeline"]
        self.assertEqual(t["stage"], "ops")
        self.assertEqual(t["py"], "sys")
        self.assertEqual(t["script"], "pipeline/driver.py")
        self.assertFalse(t.get("gpu", False))
        self.assertFalse(t.get("handoff", False))
        self.assertFalse(R.gate_of(t))



if __name__ == "__main__":
    unittest.main()
