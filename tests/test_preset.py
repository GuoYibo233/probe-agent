"""预设线的验收测试(改造 spec 在 .scratch/gen-preset/spec.md)。

现役预设三份:`default` 是全线唯一的生成口径,每个入口的 `--preset` 缺省就是它;
`gptoss_default` 是 OpenAI 官方推荐口径;`gptoss_bfcl_high` 是 BFCL 线的口径。
这里钉四件事:预设与模型表本身合格;`default` 的 client 节与 server 节逐项对得上;
每个入口的 `--preset` 缺省是 `default`;预设 client 节的采样键写了就进请求体。
温度这个键只有预设文件一个来源,所以下面的断言全部回读预设文件的值。
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

# 每个吃 --preset 的入口。缺省值直接从源码里读:采集器与 splice_replay 各自
# 要专用 venv 才 import 得动,读源码这条路在任何机器上都走得通。
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
    """源码里每一处 `--preset` argparse 参数的 default,按出现顺序成表。
    一个文件里有几个子命令就有几处(replay_inject 的 run 是其中一处),
    整表一起断言,以后长出第二处也照样钉住。"""
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
    """live_appworld/replay_inject 互相 import 同目录模块,得走 sys.path。"""
    if str(INJECT_DIR) not in sys.path:
        sys.path.insert(0, str(INJECT_DIR))
    import importlib
    return importlib.import_module(name)


class TestModelsJson(unittest.TestCase):
    def test_resolve_unchanged_after_migration(self):
        # 搬进 configs/models.json 前后,resolve 的结果一个字都不许变
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
        self.assertTrue(any("未知键" in e for e in PL.validate(p)))

    def test_unknown_model_rejected(self):
        p = {"model": "no-such-model"}
        self.assertTrue(any("不在 models.json" in e for e in PL.validate(p)))


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
        # 预设里的 null = 不指定,要落到 fallback,不是覆盖成 None
        out = PL.merge_client({"max_tokens": None}, {"max_tokens": None},
                              {"max_tokens": 8192})
        self.assertEqual(out["max_tokens"], 8192)

    def test_cli_beats_preset_on_sampling_key(self):
        # 各入口把 temperature 挂在 cli 一侧:命令行显式给了就压过预设
        pre = PL.load_preset("default")["client"]
        out = PL.merge_client({"temperature": 0.25}, pre, {})
        self.assertEqual(out["temperature"], 0.25)


class TestDefaultPreset(unittest.TestCase):
    """`default` 是现役唯一口径:client 节的采样档 + server 节的服务参数,
    两节都在这里逐项钉住(server 节抄 envs/runs/nyapass/launch_servers.py)。"""

    def test_loads_and_validates(self):
        # load_preset 内部就调 validate,不合格会抛;这里再对原始 json(不带
        # load_preset 事后加的 _name/_path)显式校验一遍,与
        # TestPresetsValidate.test_all_presets_pass 同一种查法
        PL.load_preset("default")   # 不抛 = 过校验
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
        # CLI 未显式给的时候,温度取预设 client 节写的那个值
        pre = PL.load_preset("default")
        out = PL.merge_client({"temperature": None}, pre["client"], {})
        self.assertEqual(out["temperature"], pre["client"]["temperature"])

    def test_gen_launch_default_preset_name(self):
        # manifest 没写 gptoss_client_preset 时,发射清单生成器用的预设名
        gl_dir = str(ROOT / "pipeline/collect")
        if gl_dir not in sys.path:
            sys.path.insert(0, gl_dir)
        import gen_launch as GL
        self.assertEqual(GL.GPTOSS_CLIENT_PRESET_DEFAULT, "default")


class TestRequireTemperature(unittest.TestCase):
    """生成入口的温度检查:温度是个数就放行,预设写 null 就当场停下。"""

    def test_number_passes_through(self):
        pre = PL.load_preset("default")
        self.assertEqual(
            PL.require_temperature(pre["client"]["temperature"], "default"),
            1.0)

    def test_null_temperature_stops(self):
        # gptoss_bfcl_high 的温度跟着 BFCL 自己那一档走,拿它跑生成入口要报错
        pre = PL.load_preset("gptoss_bfcl_high")
        with self.assertRaises(SystemExit) as cm:
            PL.require_temperature(pre["client"]["temperature"],
                                   pre["_name"])
        self.assertIn("gptoss_bfcl_high", str(cm.exception))


class TestEntrypointPresetDefault(unittest.TestCase):
    """每个吃 --preset 的入口,argparse 缺省都是 default。"""

    def test_every_entrypoint_defaults_to_default(self):
        for rel in PRESET_ENTRYPOINTS:
            defaults = _preset_arg_defaults(rel)
            self.assertTrue(defaults, f"{rel} 里要有带 default 的 --preset 参数")
            self.assertEqual(defaults, ["default"] * len(defaults), rel)


class TestBfclPresetFields(unittest.TestCase):
    """gptoss_bfcl_high 的 client 节:BFCL 线的口径。"""

    def test_bfcl_high(self):
        c = PL.load_preset("gptoss_bfcl_high")["client"]
        # temperature=None:BFCL 线沿用 BFCL 自带的那一档
        self.assertEqual((c["api"], c["reasoning_effort"], c["temperature"],
                          c["max_tokens"]), ("chat", "high", None, 16384))


class TestServeCmdFromDefault(unittest.TestCase):
    """serve_preset 用 default 的 server 节拼 vllm serve 命令。"""

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
        pre = PL.load_preset("gptoss_bfcl_high")   # 这份没有 server 节
        with self.assertRaises(SystemExit):
            SP.build(pre, gpu=0)


class TestEntrypointsCompile(unittest.TestCase):
    """改过的入口全部能编译(语法层;import 层的等价见下一个类)。"""

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


@unittest.skipUnless(APPWORLD_PY.exists(), "appworld venv 不在这台机器上")
class TestCollectorSettings(unittest.TestCase):
    """采集器口径:settings_from_args 不传 --preset 就落在 default 上,
    预设 client 节的采样键流进产出(在 appworld venv 里跑,common 要 openai)。
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

a = S()                                      # 不传 --preset
b = S(preset="gptoss_default",
      model="gpt-oss-120b", base_url="http://tokyo108:8103/v1")
c = S(preset="default", reasoning_effort="low")   # CLI 压过预设
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
        # default 带 server 节:端点与模型名省得掉
        self.assertEqual(a["base_url"], "http://tokyo108:8103/v1")
        self.assertEqual(a["model"], "gpt-oss-120b")
        # gptoss_default 的 temperature/top_p 要流到产出,seed 留 null
        self.assertEqual(b_sample, [1.0, 1.0, None])
        self.assertEqual(c_effort, "low")       # CLI 压过预设


class TestSamplingForwarding(unittest.TestCase):
    """采样键写进预设就进请求体(2026-08-21 对齐)。此前 top_p/seed 只有采集线
    转发——活跑/回放的合并兜底里没有这两个键,预设写了也静默不生效。
    兜底表覆盖下面这几个键;temperature 由 --preset(缺省 default)在合并的
    cli 一侧给出,值只出自预设文件。"""

    SAMPLING_KEYS = {"top_p", "max_tokens", "stop", "seed"}

    def test_live_fb_covers_sampling_keys(self):
        # merge_client 只处理 cli∪fallbacks 里的键:兜底缺一个键 = 那个键失效
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
    """preset-sweep:参数网格 -> 一批合格预设文件,名字即口径。"""

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
            SW.parse_grid("api=chat")            # 非采样键
        with self.assertRaises(SystemExit):
            SW.parse_grid("temperature=abc")     # 转不成数
        with self.assertRaises(SystemExit):
            SW.parse_grid("temperature")         # 没有 =

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
            self.assertEqual(p0["model"], "gpt-oss-120b")  # base 的其余照抄
            with self.assertRaises(SystemExit):   # 同名拒绝覆盖
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
    """BFCL handler 在仓库环境 import 不了(要 BFCL venv 的 bfcl_eval),
    只 exec NEW1_PRESET_PREFIX_END 以上的预设读取段——那一段纯标准库。"""

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
        # 环境变量缺席时读仓库根的 configs/presets/default.json
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
