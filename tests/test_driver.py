"""pipeline/driver.py 的状态机边界测试(设计稿 §7 的七条)。

驱动器自己不碰真机器:探测与子进程全在 `driver.Probes` 的注入点上,这里把它们
换成假函数,拿一棵临时目录树当仓库根,把整条状态机干跑一遍——初始态推进、
脏树拒绝发射、smoke 判据、a1 停点、G6 完整性、状态文件拒绝覆盖、--status 只读。

假件里要造 id 一律用 zlib.crc32(repo 既有约定,不用内置 hash())。
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
    """一条假轨迹:首行 meta(带 gen_settings.seed),末行 final。"""
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
    """一棵临时目录树当仓库根:ROOT / LOG_ROOT / RUNS_DIR / SERVE_LOG_DIR 四个
    模块常量都指过去,真仓库一个字节都不碰。"""

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
            f.write_text(self.tids[i])          # 一堆一题,题单无末尾换行
            self.split_files[sp] = str(f)
        self.data_out = self.root / "data" / "nyapass_aw_v1" / "gptoss"
        self.cfg_path = self.write_cfg()
        self.manifest_path = self.write_manifest()

    # ---- 假配置 ----

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

    # ---- 假件 ----

    def make_gen_files(self):
        d = self.root / "envs" / "runs" / "nyapass"
        d.mkdir(parents=True, exist_ok=True)
        for n in D.GEN_FILES:
            (d / n).write_text("# fake\n")
        return d

    def cfg(self):
        return D.load_cfg(self.cfg_path)

    def probes(self, **kw):
        """全部注入点先钉成"会当场炸"的默认值,用例只放开自己要用的那几个——
        忘了注入就会炸出来,而不是悄悄走真探测。"""
        def boom(name):
            def _f(*a, **k):
                raise AssertionError(f"用例没注入 {name},却被调用了")
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
    """设计稿 §7 测试项 1/2:c1 完成 -> c2 脏树 blocked -> 干净树发射退 3。"""

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
        st = self.read_state()          # 落盘且可重读
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
        """session 存在性必须排在探卡前:服务起来后自己占卡,顺序反了会把
        已经发射好的批次永远挡在 blocked 上。"""
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
                         probe_free=lambda h, g: (False, "占用中: 12345, 8MiB"))
        ev, code = D.step_c2_servers(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("G2", ev["event"])
        self.assertIn("占用中", ev["detail"])


class TestServerHealth(DriverCase):
    """c3_health:日志见 startup complete 才算健康。日志里还没有那句话时,按
    tmux session 死活分叉——session 还在算 warm-up 继续等,探不到就 blocked,
    不跟 warm-up 挤同一个出口无限等(评审 C8)。"""

    def servers(self):
        return json.loads(self.manifest_path.read_text())["servers"]

    def write_serve_log(self, idx, healthy=True):
        s = self.servers()[idx]
        p = D.SERVE_LOG_DIR / f"{s['session']}.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"INFO 起了\n{D.HEALTH_MARK}\n" if healthy
                     else "INFO 正在装权重\n")
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
        self.assertIn("warm-up", ev["detail"])

    def test_c3_blocked_when_the_session_is_gone(self):
        s = self.write_serve_log(0, healthy=False)
        self.write_serve_log(1, healthy=True)
        pr = self.probes(has_session=lambda h, x: False,
                         http_get=lambda u, **k: (True, "{}"))
        ev, code = D.step_c3_health(self.cfg(), D.fresh_state(self.cfg()), pr)
        self.assertEqual(code, 1)
        self.assertIn("探不到", ev["event"])
        self.assertIn(s["session"], ev["detail"])          # 死的是哪个
        self.assertIn(f"{s['session']}.log", ev["detail"])  # 去哪读日志
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
    """评审 C9:三件发射物是照哪一份 manifest 生成的,真正去跑它们的 c2/c5
    要对得上——manifest 改了卡号却忘了 --force 重生成,当场拦住。"""

    def primed(self):
        """c1 认领已有生成物,顺手把 manifest 的 sha1 记进状态。"""
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
        st = D.fresh_state(cfg)             # 老状态文件里没有这个键
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
    """设计稿 §7 测试项 3:c4 的 G4 判据。"""

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
        self.assertIn("3 个轨迹文件", ev["detail"])

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
        self.assertIn("末行不是 type=final", ev["detail"])

    def test_c4_blocked_when_the_seed_table_is_short(self):
        """种子表比 K 短:给那条准备好的 blocked,不许抛 IndexError(评审 C10)。
        场景是上一轮用完整种子表跑出了 4 个文件,人手改配置时漏掉两个种子。"""
        self.write_cfg(collect={"manifest": "manifest.json",
                                "run_id": "nyapass", "seeds": [42, 67]})
        cfg = self.cfg()
        self.write_smoke(cfg, seeds=[42, 67, 4267, 6742])
        ev, code = D.step_c4_smoke(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("种子表", ev["event"])
        self.assertIn("2 个", ev["detail"])

    def test_smoke_traj_check_does_not_index_past_the_seed_table(self):
        cfg = self.cfg()
        d = self.write_smoke(cfg)
        ok, why = D.smoke_traj_check(d, self.k, [42, 67], "appworld")
        self.assertFalse(ok)
        self.assertIn("种子表", why)

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
    """设计稿 §7 测试项 5:c6 的 G6/G7。"""

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
        self.assertIn("8 个轨迹文件", ev["detail"])
        self.assertIn("--resume", ev["detail"])

    def test_c6_waits_while_clients_alive(self):
        cfg = self.cfg()
        self.fill_outdir(cfg, n_units=2)
        pr = self.probes(local_host=lambda: "tokyo105",
                         has_session=lambda h, s: True)
        ev, code = D.step_c6_done(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0)
        self.assertFalse(ev["advance"])
        self.assertIn("还活着", ev["detail"])

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
        self.assertIn("探不动", ev["detail"])


class TestAnnotateStop(DriverCase):
    """设计稿 §7 测试项 4:a1 的 max_bounds 停点。"""

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
    """设计稿 §7 测试项 6/7:状态文件拒绝覆盖 + --status 只读。"""

    def prime(self):
        self.make_gen_files()
        with patch.object(D, "git_dirty", lambda: []):
            code, _ = self.run_main("--config", str(self.cfg_path))
        self.assertEqual(code, 0)
        return self.root / "logs" / "pipeline" / "nyapass_aw_v1" / "state.json"

    def test_refuses_corrupt_state(self):
        p = self.prime()
        p.write_text("{ 这不是 json")
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path))
        self.assertIn("读不动", str(cm.exception))
        self.assertEqual(p.read_text(), "{ 这不是 json")   # 没被覆盖

    def test_refuses_state_with_unknown_step(self):
        p = self.prime()
        st = json.loads(p.read_text())
        st["step"] = "c9_nonexistent"
        p.write_text(json.dumps(st))
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path))
        self.assertIn("步骤名不认识", str(cm.exception))

    def test_refuses_state_of_another_batch(self):
        """批次身份换了(照 run.py recipe 的 params 一致性先例):拒绝覆盖。"""
        p = self.prime()
        before = p.read_text()
        self.write_cfg(model_full="gpt-oss-20b")
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--config", str(self.cfg_path))
        self.assertIn("拒绝覆盖", str(cm.exception))
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
        """标记是人要动的东西(死掉的批次得靠人删),--status 就得印出来。"""
        p = self.prime()
        st = json.loads(p.read_text())
        D.mark_launched(st, D.launch_key("t2_full", "np821b06"), "full")
        p.write_text(json.dumps(st, ensure_ascii=False))
        code, out = self.run_main("--config", str(self.cfg_path), "--status")
        self.assertEqual(code, 0)
        self.assertIn("发射标记", out)
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
        self.assertIn("不认识的参数", str(cm.exception))


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
        """驱动器印的 p50/p90/p99 与 ANNOTATE_REPORT 存档的必须是同一个数:
        两边都用下标式 floor(评审 C4;原来 driver 是 ceil 最近秩,q*n 是整数时
        与 build 差一格)。"""
        s = list(range(1, 101))
        self.assertEqual(D.pct(s, 0.5), 51)
        self.assertEqual(D.pct(s, 0.9), 91)
        self.assertEqual(D.pct(s, 0.99), 100)

        def q(vals, p):        # pipeline/annotate/build.py:468 的 q(),逐字抄
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
        self.assertFalse(D.file_contains(p, "没有这句话"))

    def test_placement_paths_are_per_batch(self):
        cfg = self.cfg()
        self.assertTrue(str(D.placement_of(cfg, "np821b06"))
                        .endswith("ops/np821b06_placement.json"))
        self.assertTrue(str(D.placement_of(cfg, "np821b06", "eval_tool"))
                        .endswith("ops/np821b06_eval_tool_placement.json"))

    def test_run_dir_honors_manifest_envs_root(self):
        # gen_launch 尊重 manifest 的 envs_root 覆盖,驱动器的完成判据必须
        # 找同一个位置(空转验收 2026-08-22 抓到的真 bug:曾写死 ROOT/envs)
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
        (run / "REPLAY_REPORT.json").write_text("坏文件")
        self.assertFalse(D.theta_all_null(run))


class TestClientLaunch(DriverCase):
    """c5:发射客户端分片 + G16 三处登记(已登记的跳过)。"""

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
        self.assertEqual(code, 0)             # 没发射就不是 3
        self.assertTrue(ev["advance"])
        # 只剩 RUNMETA 那一条(append 不覆盖,重复补一条是既定行为)
        self.assertEqual(len(seen), 1)
        self.assertIn("runmeta", seen[0])

    def test_c5_blocked_on_dirty_tree(self):
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [" M a.py", " M b.py"])
        ev, code = D.step_c5_clients(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("commit", ev["detail"])


class TestAnnotateBuildGates(DriverCase):
    """a2/a3:产物齐不齐 + G9 题单 + 逐字节重建对比。"""

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
        self.assertIn("产物不齐", ev["event"])

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
            (self.data_out / "train.jsonl").write_text("重建出来不一样\n")
            return 0, ""

        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg),
                                   self.probes(run_cmd=fake_run))
        self.assertEqual(code, 1)
        self.assertIn("train.jsonl", ev["detail"])
        ref = self.data_out.parent / f"{self.data_out.name}_rebuild_ref"
        self.assertTrue(ref.is_dir())          # 证据留着
        self.assertEqual((ref / "train.jsonl").read_text(),
                         "content of train.jsonl\n")

    def test_a3_refuses_when_an_old_ref_dir_is_left_over(self):
        self.make_artifacts()
        (self.data_out.parent / f"{self.data_out.name}_rebuild_ref").mkdir()
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("备份还在", ev["event"])

    def test_a3_blocked_when_a_task_id_is_in_two_splits(self):
        self.make_artifacts()
        Path(self.split_files["val"]).write_text(self.tids[0])
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("同时在", ev["detail"])

    def test_a3_blocked_when_qa_sample_is_missing(self):
        self.make_artifacts()
        (self.data_out / "qa_sample.txt").unlink()
        cfg = self.cfg()
        ev, code = D.step_a3_gates(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 1)
        self.assertIn("G11", ev["event"])


class TestLaterStages(DriverCase):
    """t1..m1 的转移逻辑(判据用假产物,发射用假 run_cmd)。这几步真跑在执行块,
    这里钉的是"判据不过就 blocked、不放行"和"一次调用只发一批"。"""

    batch = "np821b06"
    cells = ("ctool", "cgen", "cparam")

    def rid(self, cell):
        return f"{self.batch}_gptoss_{cell}"

    def write_train_log(self, d, losses, done=False, align=None,
                        start=True, best=False):
        """一份假 train_log.jsonl。`losses` 给几个数就写几条 event=step 记录——
        真跑起来每 50 个优化步才写一条,smoke 只跑 6~16 步,所以现实里的 smoke
        日志通常是零条(评审 C6),这里的条数就照"实际落盘几条"造。"""
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
        """三格 smoke 的假产物。缺省 = 一次跑通的样子:start + done + best/,
        ctool 另有 ALIGN_CHECK PASS。"""
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
        self.assertIn("loss 没降", ev["detail"])
        self.make_smokes(ok=True)
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0)
        self.assertTrue(ev["advance"])

    def test_t1_passes_with_zero_step_records(self):
        """现实里的 smoke 日志一条 event=step 都没有(每 50 个优化步才写一条,
        smoke 只跑 6~16 步):start + done + best/ 齐就算过,detail 里记一句
        loss 序列太短没判(评审 C6)。"""
        cfg = self.cfg()
        self.make_smokes(losses=[])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg),
                                   self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 0, ev["detail"])
        self.assertTrue(ev["advance"])
        self.assertIn("太短", ev["detail"])
        self.assertIn("0 条 event=step", ev["detail"])

    def test_t1_blocked_when_done_is_missing(self):
        """跑完 = train_log 里有 event=done。缺 done 一律不许放行。"""
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
        self.assertIn("best 不在", ev["detail"])

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
        """一条记录:不判降没降,过。两条且没降:拦。"""
        cfg = self.cfg()
        pr = self.probes(git_dirty=lambda: [])
        self.make_smokes(losses=[9.9])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertIn("1 条 event=step", ev["detail"])
        self.make_smokes(losses=[1.0, 2.0])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 1)
        self.assertIn("loss 没降", ev["detail"])
        self.make_smokes(losses=[2.0, 1.5, 1.0])
        ev, code = D.step_t1_smoke(cfg, D.fresh_state(cfg), pr)
        self.assertEqual(code, 0, ev["detail"])
        self.assertNotIn("太短", ev["detail"])

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
        self.assertFalse(ev["advance"])       # 指针不动,等跑完再敲
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
        self.assertEqual(code, 1)             # 没排卡表 -> blocked,不是放行
        self.assertIn("_placement.json", ev["detail"])

    # ---- 发射标记(评审 C2/C7):同一批只发一次,发过就只等不重发 ----

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
        # 第二次敲:判据还没满足、标记在 -> 等待退 0,launcher 一次都不许再调
        # (self.probes() 的 run_cmd 是"被调用就炸"的假件)
        ev, code = D.step_t2_full(cfg, st, self.probes(git_dirty=lambda: []))
        self.assertEqual(code, 0)
        self.assertEqual(ev["status"], "ready")
        self.assertFalse(ev["advance"])
        self.assertIn("不重发", ev["event"])      # 不是"本次已发射"那句假账
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
        # 报告出来了就照推进,标记在不在都不管
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
        self.assertEqual(len(seen), 2)        # 一批 x 两个风险档
        risks = sorted(a[a.index("--risk") + 1] for a in seen)
        self.assertEqual(risks, ["0.05", "0.1"])
        ev, code = D.step_m1_matrix(cfg, D.fresh_state(cfg), self.probes())
        self.assertEqual(code, 0)             # 产物在了就不再跑


class TestRealConfigs(unittest.TestCase):
    """入库的两份配置本身:字段齐、路径存在、端口/种子对得上。"""

    def test_np821_config_loads(self):
        cfg = D.load_cfg(REPO / "pipeline" / "configs" / "np821_gptoss.json")
        self.assertEqual(cfg["run_family"], "nyapass_aw_v1")
        self.assertEqual(cfg["weight_mode"], "uniform")
        self.assertEqual(cfg["trajs_per_unit"], 4)
        self.assertEqual(cfg["collect"]["seeds"], [42, 67, 4267, 6742])
        # a1 停点 2026-08-22 已裁(裁决 2):留 64 也必须显式写进配置,驱动器
        # 从此按这个值造数据;缺了它 a1 会再次停下等裁决。
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
        for p in ports:                          # 四端口各三片,铺匀
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
