"""Incident triggering (ticket 12, implementation plan Task 14) -- the pure-function part.

Test seam (spec `Testing Decisions`): "the incident-trigger rules are unit-tested inside
pure functions" -- should_trigger covers all four cases, build_incident_prompt checks
the content wording.

The implementation of `spawn_agent`/`maybe_trigger_incidents` and the integration tests
for these two functions were not finished this round (see the ticket report's "self-check
findings and open questions" section) -- out of scope for this file.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ops"))

import sampler  # noqa: E402
import verdicts  # noqa: E402


def _row(job="x", idx=0, verdict=verdicts.V_DEAD, escalated=True, **kw):
    r = {"job": job, "idx": idx, "host": "tokyo106", "gpus": "0",
         "session": "new1_x_t106g0", "verdict": verdict,
         "escalated": escalated, "log": "/tmp/x.log"}
    r.update(kw)
    return r


def _ps(incident_open=False, refires=0):
    return {"incident_open": incident_open, "refires": refires}


class TestShouldTrigger(unittest.TestCase):
    def test_first_dead_allows_refire(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_DEAD, escalated=True), _ps(refires=0))
        self.assertEqual((trig, allow), (True, True))

    def test_dead_already_refired_denies_refire(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_DEAD, escalated=True), _ps(refires=1))
        self.assertEqual((trig, allow), (True, False))

    def test_incident_already_open_does_not_retrigger(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_DEAD, escalated=True),
            _ps(incident_open="x#0@123", refires=0))
        self.assertFalse(trig)

    def test_stall_below_escalate_line_does_not_trigger(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_STALL, escalated=False), _ps())
        self.assertFalse(trig)

    def test_stall_past_escalate_line_triggers_without_refire(self):
        trig, allow = sampler.should_trigger(
            _row(verdict=verdicts.V_STALL, escalated=True), _ps(refires=0))
        self.assertEqual((trig, allow), (True, False))


class TestBuildIncidentPrompt(unittest.TestCase):
    def test_allow_refire_contains_refire_command(self):
        row = _row(verdict=verdicts.V_DEAD, log="/tmp/x.log")
        prompt = sampler.build_incident_prompt(row, allow_refire=True)
        self.assertIn("/tmp/x.log", prompt)
        self.assertIn("python3 run.py gpu-jobs json", prompt)
        self.assertIn("python3 run.py launch --refire x --idx 0", prompt)

    def test_deny_refire_contains_no_refire_wording(self):
        row = _row(verdict=verdicts.V_DEAD, log="/tmp/x.log")
        prompt = sampler.build_incident_prompt(row, allow_refire=False)
        self.assertIn("/tmp/x.log", prompt)
        self.assertIn("python3 run.py gpu-jobs json", prompt)
        self.assertIn("autopsy only, do not launch anything else", prompt)
        self.assertNotIn("--refire x --idx 0", prompt)


class TestMaybeTriggerIncidents(unittest.TestCase):
    """The trigger closed loop: mock out spawn_agent (no real process spawned), check the
    incident record, incident_open gets set, a second call does not re-trigger. Writes
    to disk under a temporary MONITOR_DIR."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = sampler.MONITOR_DIR
        sampler.MONITOR_DIR = pathlib.Path(self._tmp.name)
        self._spawned = []
        self._old_spawn = sampler.spawn_agent
        sampler.spawn_agent = lambda prompt, out: self._spawned.append(
            (prompt, str(out)))

    def tearDown(self):
        sampler.MONITOR_DIR = self._old_dir
        sampler.spawn_agent = self._old_spawn
        self._tmp.cleanup()

    def test_trigger_writes_record_and_sets_open(self):
        row = _row()
        st = {sampler.piece_key("x", 0): sampler._new_piece_state(0.0)}
        sampler.maybe_trigger_incidents([row], st)
        self.assertEqual(len(self._spawned), 1)
        prompt, out = self._spawned[0]
        self.assertIn("/tmp/x.log", prompt)
        self.assertIn("--refire", prompt)
        recs = sampler.read_incidents_tail()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["job"], "x")
        self.assertTrue(recs[0]["allow_refire"])
        self.assertEqual(recs[0]["out"], out)
        self.assertTrue(st[sampler.piece_key("x", 0)]["incident_open"])

    def test_second_round_does_not_retrigger(self):
        row = _row()
        st = {sampler.piece_key("x", 0): sampler._new_piece_state(0.0)}
        sampler.maybe_trigger_incidents([row], st)
        sampler.maybe_trigger_incidents([row], st)
        self.assertEqual(len(self._spawned), 1)
        self.assertEqual(len(sampler.read_incidents_tail()), 1)

    def test_healthy_row_never_triggers(self):
        row = _row(verdict=verdicts.V_OK, escalated=False)
        st = {sampler.piece_key("x", 0): sampler._new_piece_state(0.0)}
        sampler.maybe_trigger_incidents([row], st)
        self.assertEqual(self._spawned, [])


class TestSpawnAgentArgs(unittest.TestCase):
    """spawn_agent's subprocess arguments: mock Popen, assert the headless flag combination and redirection."""

    def test_popen_args(self):
        import os
        import tempfile
        calls = []

        class FakePopen:
            def __init__(self, argv, **kw):
                calls.append((argv, kw))

        old = sampler.subprocess.Popen
        sampler.subprocess.Popen = FakePopen
        # tests/__init__ sets NEW1_NO_SPAWN globally (the C1 fallback switch); what this test
        # needs is exactly "the arguments at real launch time", so remove it temporarily and
        # restore it after the test
        saved_env = os.environ.pop("NEW1_NO_SPAWN", None)
        try:
            with tempfile.TemporaryDirectory() as d:
                sampler.spawn_agent("PROMPT", pathlib.Path(d) / "a.out")
        finally:
            sampler.subprocess.Popen = old
            if saved_env is not None:
                os.environ["NEW1_NO_SPAWN"] = saved_env
        argv, kw = calls[0]
        # From C3 onward, argv[0] is the absolute path resolved by shutil.which, no longer a bare string
        self.assertTrue(argv[0].endswith("claude"), argv[0])
        self.assertEqual(argv[1:3], ["-p", "PROMPT"])
        model_i = argv.index("--model")
        self.assertEqual(argv[model_i + 1], "opus")
        self.assertIn("--dangerously-skip-permissions", argv)
        self.assertTrue(kw["start_new_session"])
        self.assertEqual(kw["stdin"], sampler.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
