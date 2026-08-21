"""annotate/build.py 的两个新旋钮与四样新统计(纯 CPU,假轨迹目录)。

盖住的事:weight_mode(uniform 每步等权 / per_event 旧口径 w=1/m_i)与
max_bounds(切点上限)的三层优先级(CLI > 配置字段 > 缺省)、rules.boundaries
不带上限参数时与带 64 同结果、四样新统计只在配置带 trajs_per_unit 时出现且
数字对得上,外加一条 G8 的单测缩影:同一份假轨迹,改动前的 build.py+rules.py
(从 commit 808266a 取出来跑)与现在的代码加 `--weight-mode per_event
--max-bounds 64`,七个产物文件逐字节相同。

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

# 改动前的那次提交:G8 缩影拿它的 build.py + rules.py 跑对照组。
# 钉死 sha 而不是 HEAD——本次改动 commit 进去以后 HEAD 就不再是"改动前"了。
PIN = "808266a"

OUT_FILES = ("train.jsonl", "val.jsonl", "test.jsonl", "tool_vocab.json",
             "router_stats.md", "qa_sample.txt", "ANNOTATE_REPORT.md")


def tid_of(name):
    """假 task_id。不用内置 hash():字符串 hash 每进程加盐,题单文件会对不上。"""
    return f"{zlib.crc32(name.encode()) % 10 ** 7:07d}_1"


def think_text(n, tag):
    """n 句思考 -> 未截断切点恰好 n 个(每句 ~52 字符,过得了 MIN_THINK//2 闸门)。"""
    return " ".join(
        f"Step {i} of {tag} needs a careful second look at the data."
        for i in range(n))


def write_traj(path, tid, n_step=1, n_sent=3, tag="a", final_steps=None):
    """写一条假 appworld 轨迹(meta + 每步 gen/env + final)。"""
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
    """每个用例一个 tempdir:假轨迹目录 + 三份题单 + 配置 + 产物目录。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="annbuild_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.runs = self.tmp / "runs" / "appworld_gptoss"
        self.runs.mkdir(parents=True)
        self.out = self.tmp / "out"

    # ---------- 假件工厂 ----------

    def traj(self, unit_name, r=None, **kw):
        """造一条轨迹,返回它的 task_id。r 给了就用带采样序号的文件名。"""
        tid = tid_of(unit_name)
        stem = f"appworld_{tid}" if r is None else f"appworld_{tid}_r{r}"
        write_traj(self.runs / f"{stem}.jsonl", tid, **kw)
        return tid

    def splits(self, train, val, test):
        """三份官方题单(照真文件的样子,不带末尾换行)。"""
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

    # ---------- 跑与读 ----------

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
    """1/2:权重口径与 CLI 覆盖配置字段。"""

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
        self.assertIn("- 规则:全句边界前缀 / w=1 每步等权 / 三路切分"
                      "(官方题单,任务实例级) / 一模型一数据集", self.report())

    def test_per_event_keeps_old_weight(self):
        cfg = self.fixture()
        self.build(cfg, "--weight-mode", "per_event")
        for s in self.all_samples():
            self.assertEqual(s["w"], round(1.0 / s["n_sents"], 6))
        self.assertIn("- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分"
                      "(官方题单,任务实例级) / 一模型一数据集", self.report())

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
    """3/4:切点上限生效 + boundaries 的缺省参数兼容性。"""

    def fixture(self, **extra):
        a = self.traj("ma", n_sent=100)     # 未截断切点 100 个
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
        # 配置分支按"键在不在"判:写 0 不许被 or 静默换成 64,要和 CLI 的
        # 0 一样命中 <2 硬拦(评审 2026-08-22 抓的洞)
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
    """5:四样新统计的门控与数字。"""

    PREFIXES = ("- 切点数(未截断)", "- 命中切点上限", "- 完全相同轨迹",
                "- 步数达上限")

    def fixture(self, **extra):
        # A:两条一模一样的轨迹(同 tag 同步数 -> 逐步 reasoning/content 全等)
        a = self.traj("sa", r=0, n_sent=3, tag="same")
        self.traj("sa", r=1, n_sent=3, tag="same")
        # B:未截断切点 100 个,且 final 步数顶到 30
        b = self.traj("sb", r=0, n_sent=100, tag="long", final_steps=30)
        # C:普通一条
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
        # 未截断切点数 = [3, 3, 3, 100](A 两条各一事件、B 一条、C 一条)
        # p50=ub[2]=3, p90=p99=ub[3]=100;超 32/64/128/256 -> 1/1/0/0
        self.assertIn("- 切点数(未截断)每事件: min 3 p50 3 p90 100 p99 100"
                      " max 100;超 32/64/128/256 的事件 1/1/0/0", rep)
        self.assertIn("- 命中切点上限(64)的事件: 1", rep)
        self.assertIn("- 完全相同轨迹: 1 对(涉及 1 题);扫描轨迹 4 条,只计数不去重",
                      rep)
        self.assertIn("- 步数达上限(30)的轨迹: 1 条(涉及 1 题)", rep)

    def test_cap_line_follows_max_bounds(self):
        self.build(self.fixture(trajs_per_unit=2), "--max-bounds", "32")
        self.assertIn("- 命中切点上限(32)的事件: 1", self.report())

    def test_no_duplicate_when_trajs_differ(self):
        # 同 unit 两条但 tag 不同 -> 逐步文本不等,不算相同轨迹
        a = self.traj("da", r=0, n_sent=3, tag="x")
        self.traj("da", r=1, n_sent=3, tag="y")
        b = self.traj("db", r=0, n_sent=3, tag="z")
        c = self.traj("dc", r=0, n_sent=3, tag="w")
        cfg = self.config(self.splits([a], [b], [c]), trajs_per_unit=2)
        self.build(cfg)
        self.assertIn("- 完全相同轨迹: 0 对(涉及 0 题);扫描轨迹 4 条,只计数不去重",
                      self.report())
        self.assertIn("- 步数达上限(30)的轨迹: 0 条(涉及 0 题)", self.report())


class TestLegacyBytes(BuildCase):
    """6:G8 的单测缩影——旧语义手工期望 + 与改动前代码逐字节对拍。"""

    def fixture(self):
        a = self.traj("ga", n_sent=100)
        b = self.traj("gb", n_sent=5)
        c = self.traj("gc", n_sent=7)
        return self.config(self.splits([a], [b], [c]))

    def test_old_semantics_by_hand(self):
        cfg = self.fixture()
        self.build(cfg, "--weight-mode", "per_event", "--max-bounds", "64")
        ss = self.all_samples()
        # w = 1/m_i;m = min(未截断切点数, 64)
        want = {100: 64, 5: 5, 7: 7}
        got = {s["n_sents"] for s in ss}
        self.assertEqual(got, set(want.values()))
        for s in ss:
            self.assertEqual(s["w"], round(1.0 / s["n_sents"], 6))
        rep = self.report()
        self.assertIn("- SEED=20260729 MAX_BOUNDS=64 env=appworld"
                      " model=gpt-oss-120b", rep)
        self.assertIn("- 规则:全句边界前缀 / w=1/m_i 事件等权 / 三路切分"
                      "(官方题单,任务实例级) / 一模型一数据集", rep)
        self.assertTrue(any(l.startswith("- 边界数每事件: min 5 med 7 max 64"
                                         "(上限 64)") for l in rep), rep)
        for line in rep:
            for pre in TestNewStats.PREFIXES:
                self.assertFalse(line.startswith(pre), line)

    def test_make_samples_defaults_are_old_semantics(self):
        # accept_v3diff.py 拿 make_samples(events) 复现 v3 旧数据,一个参数都不传,
        # 所以函数缺省必须还是旧口径(w=1/m_i、上限 64)。
        self.fixture()
        with warnings.catch_warnings():
            # jsonl_events 是 `[json.loads(l) for l in open(f)]` 的老写法,
            # 进程内直接调它会刷一屏 ResourceWarning;这里只是噪音,不是回归。
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
                self.skipTest(f"取不到 {PIN} 的 {f}:{p.stderr[:200]}")
            (old / f).write_bytes(p.stdout)
        cfg = self.fixture()
        self.build(cfg, script=old / "build.py")        # 对照组:改动前的代码
        ref = self.tmp / "ref"
        shutil.copytree(self.out, ref)
        self.build(cfg, "--weight-mode", "per_event", "--max-bounds", "64")
        for name in OUT_FILES:
            self.assertEqual((ref / name).read_bytes(),
                             (self.out / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
