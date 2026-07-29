"""闭环探针服务:把训好的探针(ModernBERT best/)挂成 HTTP 微服务。

跑在 mbert-env(1 张卡),各环境 venv 用 stdlib urllib 零依赖调用。
只做纯打分:POST /score {"text": ...} → 温度校准后的 label/conf/top5;
θ 判断是客户端 monitor 的事。打分参数与 eval_replay.score 完全同轨
(bf16 / sdpa / max_len 4096 / 左截断),温度默认读 run 目录的
REPLAY_REPORT.json。每次请求逐条记 jsonl —— serving 对照里
"探针开销单独成列"的原始数据就是这份日志。

用法(mbert-env):
  CUDA_VISIBLE_DEVICES=0 mbert-env/bin/python envs/loop/probe_server.py \
      --run envs/bert_runs/bfcl_v3 --port 8201
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import torch

# sdpa 禁 cuDNN 后端:cuDNN attention 对每个新序列长度在 CPU 上重建执行
# 计划(profiler 实测 22 层 ×35ms ≈ 770ms/新长度,GPU 实际算力仅 2.4ms),
# 线上变长请求等于每次都付。禁掉后走 flash,任意新长度 11-15ms。
torch.backends.cuda.enable_cudnn_sdp(False)

from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Probe:
    def __init__(self, run, temperature=None, device="cuda", max_len=4096):
        run = Path(run)
        label2id = json.loads((run / "best" / "label_map.json").read_text())
        self.id2label = {v: k for k, v in label2id.items()}
        self.tok = AutoTokenizer.from_pretrained(run / "best")
        self.tok.truncation_side = "left"
        # reference_compile 关掉,免得 serving 进程里 dynamo 编译添乱
        # (按长度慢的真凶是 cuDNN sdp,见文件头);数值一致性由
        # smoke_dry 全量对账兜底。
        self.model = AutoModelForSequenceClassification.from_pretrained(
            run / "best", torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            reference_compile=False).to(device).eval()
        if temperature is None:
            temperature = json.loads(
                (run / "REPLAY_REPORT.json").read_text())["temperature"]
        self.T = float(temperature)
        self.device = device
        self.max_len = max_len

    @torch.no_grad()
    def score(self, text):
        enc = self.tok([text], truncation=True, max_length=self.max_len,
                       return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        logits = self.model(**enc).logits.float().cpu()[0]
        probs = torch.softmax(logits / self.T, -1)
        top = torch.topk(probs, k=min(5, probs.numel()))
        return {"label": self.id2label[int(probs.argmax())],
                "conf": round(float(probs.max()), 6),
                "top5": [[self.id2label[int(i)], round(float(p), 4)]
                         for p, i in zip(top.values, top.indices)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--port", type=int, default=8201)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--log", default=None,
                    help="请求日志 jsonl,默认 <run>/probe_server.jsonl")
    args = ap.parse_args()

    probe = Probe(args.run, args.temperature)
    log_path = Path(args.log or Path(args.run) / "probe_server.jsonl")
    log_f = open(log_path, "a")
    # 预热:首次前向含编译/显存分配,不能算进线上开销
    probe.score("Task: warmup\n[HISTORY]\n(start)\n[THINKING]\nwarmup " * 8)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 静音默认 stderr 访问日志
            pass

        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True, "T": probe.T,
                                 "n_labels": len(probe.id2label)})
            else:
                self._send(404, {"error": "unknown path"})

        def do_POST(self):
            if self.path != "/score":
                self._send(404, {"error": "unknown path"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n))
                t0 = time.time()
                out = probe.score(req["text"])
                out["ms"] = round((time.time() - t0) * 1000, 1)
                self._send(200, out)
                log_f.write(json.dumps(
                    {"t": round(time.time(), 3), "ms": out["ms"],
                     "n_chars": len(req["text"]), "label": out["label"],
                     "conf": out["conf"]}, ensure_ascii=False) + "\n")
                log_f.flush()
            except Exception as e:
                self._send(500, {"error": str(e)})

    # 必须单线程:PyTorch cuBLAS 句柄按线程缓存,thread-per-request 会让
    # 每个请求付一次句柄重建(实测 ~760ms vs 同线程 14ms)。客户端本就串行。
    srv = HTTPServer(("0.0.0.0", args.port), H)
    print(f"probe server ready :{args.port} run={args.run} "
          f"T={probe.T} labels={len(probe.id2label)}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
