"""活跑注入线的探针服务(cprobe-env,GPU)。设计书:plans/2026-08-01-live-inject-design.md

驱动器(live_appworld.py)跑在 appworld venv 里,没有 torch/transformers,
所以三件"模型侧"的事都收进本服务,HTTP JSON 交接:

  POST /score  {"text": 探针输入}          -> {"conf","label","fired"}
               置信度 = softmax(logits/T).max(),T 在启动时从 ctool 的
               REPLAY_REPORT.json 读定,θ 由 --theta 必传;fired = conf >= theta
  POST /gen    {"text": 触发点的探针输入}  -> {"call": 整条预测调用}
               【照抄 replay_inject.gen_calls 的口径】text + call_sep 后
               greedy 续写,截到首行
  POST /render {"messages":[...]}          -> {"prefix": harmony 前缀串}
               rebuild.build_prefix,pin_date=COLLECT_DATE(2026-08-02 起
               活跑与回放同口径钉采集日;vLLM 侧配套钉法见 METHOD.md §6-④)
  GET  /health                             -> 启动配置回显(θ/T/模型路径等)

探针前向口径(设计书 §4.1,与训练/回放的已知差别):
  训练与回放评测按事件整段一次前向、在各边界 token 位取 logits
  (eval_tool.score_causal);活跑看不见未来,只能"逐前缀前向、取最后一个真实
  token 位的 logits"。因果注意力下两者数学等价,残差只剩前缀边界处的分词效应。
  --selftest 用存好的 logits_test.pt 逐事件量化这条差别(见下)。

单线程 HTTP 即可:驱动器是串行的,一次只有一个请求在飞。

用法:
  # 服务(GPU;两个 0.6B 探针 bf16 约 3GB)。--theta 必传,不给就拒跑(METHOD.md 轴4)
  cprobe-env/bin/python pipeline/inject/probe_server.py serve \\
      --theta 0.925 --port 8790 --device cuda:0

  # 自检(纯 CPU 也能跑,float32;抽 N 个测试堆事件对账触发行为)
  cprobe-env/bin/python pipeline/inject/probe_server.py selftest \\
      --theta 0.925 --events 3 --device cpu
"""

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "train"))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                           # noqa: E402

# 默认路径全部取自 θ=0.925 那次注入回放的 plan_config.json —— 活跑线评的
# 就是同一对探针,换探针必须显式传参
CTOOL = PROJ / "pipeline/runs/c1_gptoss_ctool"
CGEN = PROJ / "pipeline/runs/c1_gptoss_cgen"
GPTOSS_TOK = "/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b"


def load_ctool(run, dev):
    """【照抄 eval_tool.load_causal】backbone 从 best/ 读、head 从 best/head.pt 读。"""
    from train_causal_tool import CausalProbe                 # noqa: E402
    meta = json.loads((run / "best" / "meta.json").read_text())
    label2id = json.loads((run / "best" / "label_map.json").read_text())
    id2label = {v: k for k, v in label2id.items()}
    model = CausalProbe(run / "best", meta["n_labels"])
    model.head.load_state_dict(
        torch.load(run / "best" / "head.pt", map_location="cpu"))
    if str(dev).startswith("cuda"):
        model.backbone = model.backbone.to(torch.bfloat16)
    model = model.to(dev).eval()
    tok = AutoTokenizer.from_pretrained(run / "best")
    if tok.truncation_side != "left":
        # 训练侧显式 left(train_causal_tool.build);保存的 tokenizer 丢了这条
        # 就会静默右截、砍掉思考尾巴 —— 宁可在这里改回来并喊一声
        print(f"[warn] ctool tokenizer truncation_side="
              f"{tok.truncation_side},改回 left", flush=True)
        tok.truncation_side = "left"
    rep = json.loads((run / "REPLAY_REPORT.json").read_text())
    return model, tok, meta, id2label, rep["temperature"]


def load_cgen(run, dev):
    """【照抄 replay_inject.gen_calls 的加载】,常驻不卸载。"""
    meta = json.loads((run / "best" / "meta.json").read_text())
    tok = AutoTokenizer.from_pretrained(run / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        run / "best",
        dtype=torch.bfloat16 if str(dev).startswith("cuda")
        else torch.float32).to(dev).eval()
    return model, tok, meta


class Probe:
    def __init__(self, ctool_run, cgen_run, tokenizer_path, theta, dev):
        self.dev = dev
        self.theta = theta
        (self.ct, self.ct_tok, self.ct_meta,
         self.id2label, self.T) = load_ctool(Path(ctool_run), dev)
        self.cg, self.cg_tok, self.cg_meta = load_cgen(Path(cgen_run), dev)
        self.oss_tok = AutoTokenizer.from_pretrained(tokenizer_path)
        self.max_len = self.ct_meta["max_len"]

    @torch.no_grad()
    def score(self, text):
        enc = self.ct_tok([text], truncation=True, max_length=self.max_len,
                          return_tensors="pt")
        enc = {k: v.to(self.dev) for k, v in enc.items()}
        h = self.ct.backbone(input_ids=enc["input_ids"],
                             attention_mask=enc["attention_mask"],
                             use_cache=False).last_hidden_state
        lg = self.ct.head(h[0, -1].float().unsqueeze(0))[0]
        p = torch.softmax(lg / self.T, -1)
        conf = float(p.max())
        return dict(conf=round(conf, 6),
                    label=self.id2label[int(p.argmax())],
                    fired=conf >= self.theta)

    @torch.no_grad()
    def gen(self, text, max_new=96):
        meta = self.cg_meta
        prompt = text + meta.get("call_sep", "\n[CALL] ")
        enc = self.cg_tok([prompt], truncation=True,
                          max_length=max(meta.get("max_len", 4096) - max_new, 1),
                          add_special_tokens=False,
                          return_tensors="pt").to(self.dev)
        g = self.cg.generate(**enc, do_sample=False, max_new_tokens=max_new,
                             eos_token_id=self.cg_tok.eos_token_id,
                             pad_token_id=self.cg_tok.pad_token_id)
        txt = self.cg_tok.batch_decode(g[:, enc["input_ids"].shape[1]:],
                                       skip_special_tokens=True)[0]
        return dict(call=txt.split("\n")[0].strip())

    def render(self, messages, effort=None):
        # effort 不传 = 采集口径(high);effort 对照臂传 low/medium
        # pin_date=COLLECT_DATE(2026-08-02 改):活跑与 w0 的框架对齐排查发现
        # 当天日期是相对采集口径的无谓扰动,贪心解码下会放大成轨迹分叉;
        # 回放线一直钉采集日,活跑从 v2 起同口径。
        return dict(prefix=R.build_prefix(self.oss_tok, messages,
                                          effort=effort or R.REASONING_EFFORT,
                                          pin_date=R.COLLECT_DATE))

    def config(self):
        return dict(theta=self.theta, temperature=self.T,
                    ctool=str(CTOOL), cgen=str(CGEN),
                    n_labels=self.ct_meta["n_labels"],
                    max_len=self.max_len, device=str(self.dev))


def serve(a):
    probe = Probe(a.ctool_run, a.cgen_run, a.tokenizer, a.theta, a.device)
    print(f"probe ready: {json.dumps(probe.config())}", flush=True)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):                 # 静音默认访问日志
            pass

        def _reply(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._reply(probe.config())
            else:
                self._reply(dict(error="unknown path"), 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads(self.rfile.read(n))
                t0 = time.time()
                if self.path == "/score":
                    out = probe.score(req["text"])
                elif self.path == "/gen":
                    out = probe.gen(req["text"])
                elif self.path == "/render":
                    out = probe.render(req["messages"], req.get("effort"))
                else:
                    self._reply(dict(error="unknown path"), 404)
                    return
                out["wall_s"] = round(time.time() - t0, 4)
                self._reply(out)
            except Exception as e:                     # 驱动器要看到错误原文
                self._reply(dict(error=f"{type(e).__name__}: {e}"), 500)

    print(f"listening on :{a.port}", flush=True)
    HTTPServer(("0.0.0.0", a.port), H).serve_forever()


def selftest(a):
    """拿存好的测试堆对账活跑口径(设计书 §4.1),不需要 GPU 也不需要服务。

    对每个抽中的事件:把它全部边界前缀逐条走 /score 同款前向,与
    logits_test.pt 里整段前向的 logits 比:
      - 触发行为一致性:首过 θ 的边界序号是否相同(这是唯一影响实验的量)
      - 置信度最大绝对差(数值参考)
    再对触发前缀走 /gen 同款生成,与 θ=0.925 回放 plan.jsonl 里的 gen_call 比。
    退出码:触发边界全一致 = 0,有不一致 = 1(数值差只打印不判死——bf16/float32
    与分词边界效应本来就允许小差)。
    """
    probe = Probe(a.ctool_run, a.cgen_run, a.tokenizer, a.theta, a.device)
    data = PROJ / "pipeline/data/aw_official_v1/gptoss"
    label2id = json.loads(
        (Path(a.ctool_run) / "best" / "label_map.json").read_text())
    rows = [r for r in (json.loads(l) for l in open(data / "test.jsonl"))
            if r["label"] in label2id]
    logits = torch.load(Path(a.ctool_run) / "logits_test.pt",
                        map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)

    plan_p = PROJ / "pipeline/inject/runs/aw_gptoss_th0925/plan.jsonl"
    plan = {json.loads(l)["event"]: json.loads(l)
            for l in open(plan_p)} if plan_p.exists() else {}

    from collections import defaultdict
    ev = defaultdict(list)
    for i, r in enumerate(rows):
        ev[r["event"]].append((r["sent_idx"], i, r))
    keys = sorted(ev)[: a.events]

    bad = 0
    for k in keys:
        items = sorted(ev[k])
        stored_fire = live_fire = None
        max_dc = 0.0
        for si, i, r in items:
            p_stored = torch.softmax(logits[i] / probe.T, -1)
            if stored_fire is None and float(p_stored.max()) >= probe.theta:
                stored_fire = si
            s = probe.score(r["text"])
            max_dc = max(max_dc, abs(s["conf"] - float(p_stored.max())))
            if live_fire is None and s["fired"]:
                live_fire = si
        ok = stored_fire == live_fire
        bad += 0 if ok else 1
        line = (f"event={k} bounds={len(items)} "
                f"stored_fire={stored_fire} live_fire={live_fire} "
                f"max|Δconf|={max_dc:.4f} {'OK' if ok else 'MISMATCH'}")
        if k in plan and live_fire is not None:
            fire_row = next(r for si, _i, r in items if si == live_fire)
            g = probe.gen(fire_row["text"])
            line += (f" gen_call{'==' if g['call'] == plan[k]['gen_call'] else '!='}"
                     f"plan({plan[k]['gen_call'][:60]!r})")
        print(line, flush=True)
    print(f"selftest: {len(keys) - bad}/{len(keys)} 事件触发行为一致", flush=True)
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("serve", serve), ("selftest", selftest)]:
        p = sub.add_parser(name)
        p.add_argument("--ctool-run", default=str(CTOOL))
        p.add_argument("--cgen-run", default=str(CGEN))
        p.add_argument("--tokenizer", default=GPTOSS_TOK)
        p.add_argument("--theta", type=float, required=True,
                       help="触发阈值,必传(METHOD.md 轴4:θ 永远手动,不给就拒跑)")
        p.add_argument("--device", default="cuda:0")
        p.set_defaults(fn=fn)
    sub.choices["serve"].add_argument("--port", type=int, default=8790)
    sub.choices["selftest"].add_argument("--events", type=int, default=3)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
