"""每题多条轨迹的采集口径(np821 施工稿 §2)。

三块:
1. run_appworld 的纯函数——文件名、种子表、resume 判据、轨迹 meta、
   AppWorld 的 experiment_name。不起真环境,只单测这几个函数。
2. 种子逐条派发:第 k 条轨迹的 Chat 拿第 k 个种子,种子既进请求体
   (_sample_extras)也进轨迹 meta 的 gen_settings。
3. gen_launch 的两个可选字段 traj_per_task / seed_family——带字段时旗标
   拼进客户端脚本,不带字段的老 manifest 生成物与加字段之前逐字节一致。

采集器在 appworld venv 里跑,本机 python3 没有 openai:先塞一个只占位的
假 openai 再按路径装载(common.py 只在 Chat.__init__ 里用 OpenAI())。
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
COLLECT = ROOT / "envs/collect"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_run_appworld():
    try:
        import openai  # noqa: F401
    except ModuleNotFoundError:   # 本机 python3 没有,塞个只占位的
        fake = types.ModuleType("openai")
        fake.OpenAI = lambda **kw: types.SimpleNamespace(**kw)
        sys.modules["openai"] = fake
    for p in (str(ROOT), str(COLLECT), str(ROOT / "ops")):
        if p not in sys.path:
            sys.path.insert(0, p)
    return _load(COLLECT / "run_appworld.py", "run_appworld")


RA = _load_run_appworld()
GL = _load(ROOT / "pipeline/collect/gen_launch.py", "gen_launch")

SEEDS = [42, 67, 4267, 6742]
FAMILY = "42,67,4267,6742"

# chat_of 只读这几个键;不依赖任何预设文件,免得与别的工单抢 configs/
EFF = {"base_url": "http://tokyo108:8103/v1", "model": "gpt-oss-120b",
       "api": "harmony", "temperature": 1.0, "top_p": 1.0, "max_tokens": 8192,
       "seed": None, "reasoning_effort": "high", "start_date": "2026-08-06",
       "preset": "default"}

FINAL_LINE = '{"type": "final", "steps": 3, "completed": true}\n'
META_LINE = '{"type": "meta", "task_id": "t1"}\n'


class TestTrajPath(unittest.TestCase):
    """N == 1 的文件名一字不改;N > 1 才带采样序号。"""

    def test_single_keeps_legacy_name(self):
        p = RA.traj_path(Path("/out"), "82e2fac_1", 0, 1)
        self.assertEqual(p, Path("/out/appworld_82e2fac_1.jsonl"))

    def test_multi_adds_sample_index(self):
        names = [RA.traj_path(Path("/out"), "82e2fac_1", k, 4).name
                 for k in range(4)]
        self.assertEqual(names, [f"appworld_82e2fac_1_r{k}.jsonl"
                                 for k in range(4)])

    def test_multi_never_collides_with_legacy(self):
        legacy = RA.traj_path(Path("/out"), "t1", 0, 1).name
        self.assertNotIn(legacy, [RA.traj_path(Path("/out"), "t1", k, 4).name
                                  for k in range(4)])


class TestExpName(unittest.TestCase):
    def test_single_unchanged(self):
        self.assertEqual(RA.exp_name("np821tr_s0", 0, 1), "np821tr_s0")

    def test_multi_suffixed(self):
        self.assertEqual([RA.exp_name("np821tr_s0", k, 4) for k in range(4)],
                         [f"np821tr_s0_r{k}" for k in range(4)])


class TestResolveSeeds(unittest.TestCase):
    def test_legacy_none(self):
        self.assertIsNone(RA.resolve_seeds(None, 1))

    def test_parses_list(self):
        self.assertEqual(RA.resolve_seeds(FAMILY, 4), SEEDS)

    def test_tolerates_spaces(self):
        self.assertEqual(RA.resolve_seeds(" 42 , 67 ", 2), [42, 67])

    def test_single_with_seed_allowed(self):
        self.assertEqual(RA.resolve_seeds("42", 1), [42])

    def test_multi_without_seeds_rejected(self):
        with self.assertRaises(SystemExit) as cm:
            RA.resolve_seeds(None, 4)
        self.assertIn("--seeds", str(cm.exception))

    def test_length_mismatch_rejected(self):
        for spec in ("42,67", "42,67,4267,6742,1"):
            with self.assertRaises(SystemExit) as cm:
                RA.resolve_seeds(spec, 4)
            self.assertIn("对不上", str(cm.exception))

    def test_non_integer_rejected(self):
        with self.assertRaises(SystemExit):
            RA.resolve_seeds("42,x", 2)

    def test_zero_traj_rejected(self):
        with self.assertRaises(SystemExit):
            RA.resolve_seeds(None, 0)


class TestResumeGranularity(unittest.TestCase):
    """resume 按 (题, 采样序号) 逐条判,不是按题整体判。"""

    def skip_set(self, outdir, ids, n):
        return {(tid, k) for tid in ids for k in range(n)
                if RA.is_done(RA.traj_path(outdir, tid, k, n))}

    def test_two_of_four_done(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            # t1 的 r0/r2 写完,r1 只有 meta,r3 根本没落盘
            (d / "appworld_t1_r0.jsonl").write_text(META_LINE + FINAL_LINE)
            (d / "appworld_t1_r1.jsonl").write_text(META_LINE)
            (d / "appworld_t1_r2.jsonl").write_text(META_LINE + FINAL_LINE)
            self.assertEqual(self.skip_set(d, ["t1"], 4),
                             {("t1", 0), ("t1", 2)})

    def test_legacy_file_does_not_count_for_multi(self):
        # 老批次的 appworld_t1.jsonl 不该让多样本的四条都算完成
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "appworld_t1.jsonl").write_text(META_LINE + FINAL_LINE)
            self.assertEqual(self.skip_set(d, ["t1"], 4), set())
            self.assertEqual(self.skip_set(d, ["t1"], 1), {("t1", 0)})

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(RA.is_done(Path(td) / "nope.jsonl"))


class TestSeedDispatch(unittest.TestCase):
    """chats[k].seed == seeds[k],且种子进请求体与轨迹 meta。"""

    def chats(self, seeds):
        return [RA.chat_of({**EFF, "seed": s}) for s in seeds]

    def test_each_trajectory_gets_its_own_seed(self):
        cs = self.chats(SEEDS)
        self.assertEqual([c.seed for c in cs], SEEDS)
        self.assertEqual([c.settings()["seed"] for c in cs], SEEDS)
        self.assertEqual([c._sample_extras()["seed"] for c in cs], SEEDS)

    def test_other_settings_untouched(self):
        cs = self.chats(SEEDS)
        for c in cs:
            s = c.settings()
            self.assertEqual((s["api"], s["temperature"], s["top_p"],
                              s["max_tokens"], s["reasoning_effort"]),
                             ("harmony", 1.0, 1.0, 8192, "high"))

    def test_legacy_single_chat_has_no_seed(self):
        c = RA.chat_of(EFF)
        self.assertIsNone(c.seed)
        self.assertNotIn("seed", c._sample_extras())
        self.assertIsNone(c.settings()["seed"])


class TestTrajMeta(unittest.TestCase):
    LEGACY_KEYS = ["env", "task_id", "model", "instruction", "preset",
                   "gen_settings"]

    def test_single_meta_keys_unchanged(self):
        chat = RA.chat_of(EFF)
        m = RA.traj_meta(EFF, "t1", "do it", chat, 0, 1)
        self.assertEqual(list(m), self.LEGACY_KEYS)
        self.assertEqual(m["gen_settings"], chat.settings())

    def test_multi_meta_carries_sample_idx_and_seed(self):
        chats = [RA.chat_of({**EFF, "seed": s}) for s in SEEDS]
        for k in range(4):
            m = RA.traj_meta(EFF, "t1", "do it", chats[k], k, 4)
            self.assertEqual(list(m), self.LEGACY_KEYS + ["sample_idx"])
            self.assertEqual(m["sample_idx"], k)
            self.assertEqual(m["gen_settings"]["seed"], SEEDS[k])


# ------------------------------------------------------------- gen_launch

BASE_MANIFEST = {
    "run_id": "np821t",
    "env": "appworld",
    "gptoss_client_preset": "gptoss_chat_high",
    "envs_root": "/home/y-guo/reproduce/new1/envs",
    "servers": [
        {"host": "tokyo108", "gpu": 2, "card": "H200", "model_key": "gptoss",
         "port": 8103, "session": "new1_np821_srv_gptossa_t108g2",
         "extra_flags": ""},
        {"host": "tokyo108", "gpu": 3, "card": "H200", "model_key": "gptoss",
         "port": 8106, "session": "new1_np821_srv_gptossb_t108g3",
         "extra_flags": ""},
        {"host": "tokyo108", "gpu": 4, "card": "H200", "model_key": "gptoss",
         "port": 8107, "session": "new1_np821_srv_gptossc_t108g4",
         "extra_flags": ""},
        {"host": "tokyo108", "gpu": 5, "card": "H200", "model_key": "gptoss",
         "port": 8108, "session": "new1_np821_srv_gptossd_t108g5",
         "extra_flags": ""},
    ],
    "clients": [
        {"tag": "nptr", "model_key": "gptoss", "split": "train",
         "num_shards": 4, "shard_ports": [8103, 8106, 8107, 8108],
         "outdir": "appworld_gptoss", "exp": "np821tr"},
        {"tag": "npdv", "model_key": "gptoss", "split": "dev",
         "num_shards": 2, "shard_ports": [8103, 8106],
         "outdir": "appworld_gptoss", "exp": "np821dv"},
    ],
}

FILES = ("launch_servers.py", "launch_clients.sh", "MANIFEST.md")


def write_manifest(td, **extra):
    cfg = json.loads(json.dumps(BASE_MANIFEST))   # 深拷贝,别改到模板
    cfg.update(extra)
    p = Path(td) / "manifest.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    return p


def generate(manifest, outdir):
    """--dry-run 干跑一次,返回三个生成物的文本。"""
    argv = ["gen_launch.py", "--config", str(manifest), "--dry-run",
            "--out-override", str(outdir)]
    with mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stdout(io.StringIO()):
        GL.main()
    return {n: (Path(outdir) / n).read_text() for n in FILES}


class TestGenLaunchMultiSample(unittest.TestCase):
    def gen(self, **extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        m = write_manifest(tmp.name, **extra)
        return generate(m, Path(tmp.name) / "out")

    def test_flags_land_in_client_script(self):
        out = self.gen(traj_per_task=4, seed_family=SEEDS)
        sh = out["launch_clients.sh"]
        self.assertIn(f'MULTI="--traj-per-task 4 --seeds {FAMILY}"', sh)
        self.assertIn("--resume $MULTI", sh)
        # 四实例:服务表四条 JOBS,train 四个分片各打一个端口
        self.assertEqual(out["launch_servers.py"].count('    (2, "'), 1)
        self.assertEqual(len([ln for ln in out["launch_servers.py"].splitlines()
                              if ln.startswith("    (")]), 4)
        aw = [ln for ln in sh.splitlines() if ln.startswith("aw ")]
        self.assertEqual(len(aw), 6)          # train 4 + dev 2
        for port in (8103, 8106, 8107, 8108):
            self.assertIn(f"http://tokyo108:{port}/v1", sh)

    def test_manifest_md_line(self):
        out = self.gen(traj_per_task=4, seed_family=SEEDS)
        self.assertIn(f"每题 4 条轨迹:所有分片额外 `--traj-per-task 4 "
                      f"--seeds {FAMILY}`", out["MANIFEST.md"])
        self.assertIn("appworld_<task_id>_r<k>.jsonl", out["MANIFEST.md"])

    def test_absent_fields_emit_no_new_flags(self):
        out = self.gen()
        for name, text in out.items():
            self.assertNotIn("--traj-per-task", text, name)
            self.assertNotIn("--seeds", text, name)
            self.assertNotIn("MULTI", text, name)

    def test_old_manifest_p1_untouched(self):
        """在库的老 manifest 生成物里一个新旗标都不许冒出来。"""
        with tempfile.TemporaryDirectory() as td:
            out = generate(ROOT / "pipeline/collect/manifest_p1.json",
                           Path(td) / "p1")
            for name, text in out.items():
                self.assertNotIn("--traj-per-task", text, name)
                self.assertNotIn("$MULTI", text, name)
            self.assertIn("      --resume\"", out["launch_clients.sh"])

    def test_with_minus_added_tokens_equals_without(self):
        """等价性钉子:带字段的生成物剥掉新增 token 后,与不带字段的逐字节相等。"""
        with_f = self.gen(traj_per_task=4, seed_family=SEEDS)
        without = self.gen()
        self.assertEqual(with_f["launch_servers.py"],
                         without["launch_servers.py"])
        sh = with_f["launch_clients.sh"] \
            .replace(f'MULTI="--traj-per-task 4 --seeds {FAMILY}"\n', "", 1) \
            .replace(" $MULTI", "", 1)
        self.assertEqual(sh, without["launch_clients.sh"])
        added = (f"每题 4 条轨迹:所有分片额外 `--traj-per-task 4 "
                 f"--seeds {FAMILY}`,第 k 条用第 k 个种子,"
                 f"轨迹落 `appworld_<task_id>_r<k>.jsonl`。\n")
        md = with_f["MANIFEST.md"].replace(added, "", 1)
        self.assertEqual(md, without["MANIFEST.md"])


class TestGenLaunchValidation(unittest.TestCase):
    def bad(self, **extra):
        with tempfile.TemporaryDirectory() as td:
            m = write_manifest(td, **extra)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as cm:
                    generate(m, Path(td) / "out")
            self.assertEqual(cm.exception.code, 2)
            return err.getvalue()

    def test_only_traj_per_task(self):
        self.assertIn("要么都给要么都不给", self.bad(traj_per_task=4))

    def test_only_seed_family(self):
        self.assertIn("要么都给要么都不给", self.bad(seed_family=SEEDS))

    def test_length_mismatch(self):
        self.assertIn("对不上", self.bad(traj_per_task=4,
                                         seed_family=[42, 67]))

    def test_bad_types(self):
        self.assertIn("整数", self.bad(traj_per_task="4", seed_family=SEEDS))
        self.assertIn("整数列表", self.bad(traj_per_task=1, seed_family=["42"]))
        self.assertIn(">= 1", self.bad(traj_per_task=0, seed_family=[]))

    def test_non_appworld_env_refused(self):
        # alfworld 的采集器没有这两个旗标,拼进去只会在发射时炸
        msg = self.bad(env="alfworld", traj_per_task=4, seed_family=SEEDS)
        self.assertIn("appworld", msg)


class TestMultiFlags(unittest.TestCase):
    def test_empty_without_fields(self):
        self.assertEqual(GL.multi_flags({}), "")

    def test_string_shape(self):
        self.assertEqual(
            GL.multi_flags({"traj_per_task": 4, "seed_family": SEEDS}),
            f"--traj-per-task 4 --seeds {FAMILY}")


if __name__ == "__main__":
    unittest.main()
