"""gen-preset 改造的验收测试(2026-08-20,spec 在 .scratch/gen-preset/spec.md)。

三块:预设与模型表本身合格;五份预设展开后与改造前的写死值逐项相等;
发射器对 gptoss_chat_high 拼出的命令与旧手写发射器 launch_vllm_gptoss.py
逐字符相等。等价性不靠肉眼,靠这里钉死。

第四块(2026-08-21 采样键转发对齐):预设 client 节的采样键写了就进请求体,
四类入口(采集/活跑/回放/BFCL)逐一钉;不写时请求体与对齐前逐键相等。
"""
import importlib.util
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


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    FB = {"api": "raw", "reasoning_effort": None, "temperature": 0.0}

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
        self.assertEqual(out["temperature"], 0.0)

    def test_preset_null_falls_through(self):
        # 预设里的 null = 不指定,要落到 fallback,不是覆盖成 None
        out = PL.merge_client({"temperature": None}, {"temperature": None},
                              {"temperature": 0.0})
        self.assertEqual(out["temperature"], 0.0)


class TestPresetsMatchOldHardcoded(unittest.TestCase):
    """五份预设的 client 节 == 改造前五处写死值(spec 的现状表)。"""

    def c(self, name):
        return PL.load_preset(name)["client"]

    def test_chat_high(self):
        c = self.c("gptoss_chat_high")
        self.assertEqual((c["api"], c["reasoning_effort"], c["temperature"],
                          c["max_tokens"]), ("chat", "high", 0.0, 8192))

    def test_harmony_medium(self):
        c = self.c("gptoss_harmony_medium")
        self.assertEqual((c["api"], c["reasoning_effort"], c["temperature"],
                          c["max_tokens"], c["start_date"]),
                         ("harmony", None, 0.0, 8192, "2026-08-06"))

    def test_bfcl_high(self):
        c = self.c("gptoss_bfcl_high")
        # temperature=None:沿用 BFCL 自带的档,与旧 handler 只写死
        # max_tokens/effort 一致
        self.assertEqual((c["reasoning_effort"], c["temperature"],
                          c["max_tokens"]), ("high", None, 16384))

    def test_live_high(self):
        c = self.c("gptoss_live_high")
        self.assertEqual((c["reasoning_effort"], c["temperature"],
                          c["max_tokens"], c["stop"]),
                         ("high", 0.0, 8192, ["<|return|>"]))

    def test_replay(self):
        c = self.c("gptoss_replay")
        self.assertEqual((c["temperature"], c["max_tokens"], c["stop"]),
                         (0.0, 8192, ["<|return|>"]))


class TestServeCmdEqualsOldLauncher(unittest.TestCase):
    """serve_preset 对 gptoss_chat_high 拼的命令 == launch_vllm_gptoss.py。"""

    def test_cmd_and_tmux_identical(self):
        old = _load_module(ROOT / "envs/serve_logs/launch_vllm_gptoss.py",
                           "launch_vllm_gptoss")
        import serve_preset as SP
        pre = PL.load_preset("gptoss_chat_high")
        # 老发射器 GPU=5、session=new1_vllm_t108_gptoss;喂同样的覆盖项
        host, session, tmux, cmd = SP.build(pre, gpu=old.GPU,
                                            session=old.SESSION)
        self.assertEqual(cmd, old.CMD)
        self.assertEqual(host, "tokyo108")
        old_log = f"{old.WORKDIR}/{old.SESSION}.log"
        old_inner = (
            f"cd {old.WORKDIR} && "
            "LD_LIBRARY_PATH=/home/y-guo/reproduce/new1/envs/cuda-compat-13.0 "
            "VLLM_USE_FLASHINFER_SAMPLER=0 "
            "CUDA_DEVICE_ORDER=PCI_BUS_ID "
            f"CUDA_VISIBLE_DEVICES={old.GPU} {old.CMD} 2>&1 | tee {old_log}")
        import shlex
        self.assertEqual(tmux,
                         f"tmux new-session -d -s {old.SESSION} "
                         f"{shlex.quote(old_inner)}")

    def test_preset_without_server_refuses(self):
        import serve_preset as SP
        pre = PL.load_preset("gptoss_replay")
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
        "pipeline/collect/gen_launch.py", "pipeline/eval/eval_tool.py",
    ]

    def test_all_compile(self):
        for f in self.FILES:
            py_compile.compile(str(ROOT / f), doraise=True)


@unittest.skipUnless(APPWORLD_PY.exists(), "appworld venv 不在这台机器上")
class TestCollectorEquivalence(unittest.TestCase):
    """采集器口径等价:--preset gptoss_chat_high 与显式旗标,
    settings_from_args 的产出逐键相等(在 appworld venv 里跑,common 要 openai)。
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
    eff = settings_from_args(Namespace(**base))
    if eff["api"] == "chat" and eff["reasoning_effort"] is None:
        eff["reasoning_effort"] = "high"     # run_appworld 的原有规则
    return eff

a = S(preset="gptoss_chat_high")
b = S(api="chat", reasoning_effort="high",
      model="gpt-oss-120b", base_url="http://tokyo108:8103/v1")
c = S(preset="gptoss_harmony_medium",
      model="gpt-oss-120b", base_url="http://tokyo108:8103/v1")
d = S(api="harmony",
      model="gpt-oss-120b", base_url="http://tokyo108:8103/v1")
e = S(preset="gptoss_chat_high", reasoning_effort="low")   # CLI 压过预设
f = S(preset="gptoss_default")   # top_p 要流到产出里(2026-08-21 对齐)
print(json.dumps([a, b, c, d, e["reasoning_effort"],
                  [f["temperature"], f["top_p"], f["seed"]]]))
"""

    def test_preset_equals_explicit_flags(self):
        code = self.CODE.format(collect=ROOT / "envs/collect")
        r = subprocess.run([str(APPWORLD_PY), "-c", code],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        a, b, c, d, e_effort, f_sample = json.loads(r.stdout)
        a.pop("preset"), b.pop("preset"), c.pop("preset"), d.pop("preset")
        self.assertEqual(a, b)   # chat 口径:预设 == 显式旗标
        self.assertEqual(c, d)   # harmony 口径:预设 == 显式旗标
        self.assertEqual(e_effort, "low")
        # gptoss_default 的 temperature/top_p 要流到产出,seed 留 null
        self.assertEqual(f_sample, [1.0, 1.0, None])


class TestSamplingForwarding(unittest.TestCase):
    """采样键写进预设就进请求体(2026-08-21 对齐)。此前 top_p/seed 只有采集线
    转发——活跑/回放的合并兜底里没有这两个键,预设写了也静默不生效。"""

    SAMPLING_KEYS = {"temperature", "top_p", "max_tokens", "stop", "seed"}

    def test_live_fb_covers_sampling_keys(self):
        # merge_client 只处理 cli∪fallbacks 里的键:兜底缺一个键 = 那个键失效
        la = _import_inject("live_appworld")
        self.assertEqual(self.SAMPLING_KEYS - set(la.PRESET_FB), set())

    def test_replay_fb_covers_sampling_keys(self):
        ri = _import_inject("replay_inject")
        self.assertEqual(self.SAMPLING_KEYS - set(ri.PRESET_FB), set())

    def test_live_payload_default_unchanged(self):
        # top_p/seed 不给时,请求体与加键之前逐键相等(ident3 口径不受影响)
        la = _import_inject("live_appworld")
        a = Namespace(model="gpt-oss-120b", temperature=0.0,
                      stop=["<|return|>"], top_p=None, seed=None)
        self.assertEqual(
            la.gen_payload(a, [11, 22], 100),
            dict(model="gpt-oss-120b", prompt=[11, 22], max_tokens=100,
                 temperature=0.0, stop=["<|return|>"],
                 skip_special_tokens=False))

    def test_live_payload_carries_top_p_seed(self):
        la = _import_inject("live_appworld")
        a = Namespace(model="m", temperature=1.0, stop=["<|return|>"],
                      top_p=0.9, seed=7)
        p = la.gen_payload(a, [1], 5)
        self.assertEqual((p["top_p"], p["seed"]), (0.9, 7))

    def test_replay_payload_default_unchanged(self):
        ri = _import_inject("replay_inject")
        a = Namespace(model="gpt-oss-120b", temperature=0.0, max_tokens=8192,
                      stop=["<|return|>"], top_p=None, seed=None)
        self.assertEqual(
            ri.gen_payload(a, "P"),
            dict(model="gpt-oss-120b", prompt="P", max_tokens=8192,
                 temperature=0.0, stop=["<|return|>"],
                 skip_special_tokens=False))

    def test_replay_payload_carries_top_p_seed(self):
        ri = _import_inject("replay_inject")
        a = Namespace(model="m", temperature=1.0, max_tokens=64,
                      stop=["<|return|>"], top_p=0.9, seed=7)
        p = ri.gen_payload(a, "P")
        self.assertEqual((p["top_p"], p["seed"]), (0.9, 7))


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

    def test_no_env_defaults_unchanged(self):
        ns = self.run_prefix(None)
        self.assertEqual((ns["_MAX_TOKENS"], ns["_EFFORT"]), (16384, "high"))
        self.assertEqual(ns["_sample_kwargs"](), {})

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
