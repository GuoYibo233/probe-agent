"""Probe service for the live-run injection line (cprobe-env, GPU). Method spec: METHOD.md
(the old design doc was removed in the 08-02 cleanup).

The driver (live_appworld.py) runs inside the appworld venv, which has no
torch/transformers, so all three "model-side" jobs are folded into this service,
handed off over HTTP JSON:

  POST /score  {"text": probe input}          -> {"conf","label","fired"}
               confidence = softmax(logits/T).max(); T is read at startup from ctool's
               REPLAY_REPORT.json and fixed there; theta is required via --theta;
               fired = conf >= theta
  POST /gen    {"text": probe input at the threshold}  -> {"call": the full predicted call}
               [mirrors replay_inject.gen_calls's convention] after text + call_sep,
               continue generation greedily and cut it to the first line
  POST /render {"messages":[...],"effort":?} -> {"prefix_ids":[token id...],
               "n_tokens", "prefix": decoded text (for human eyes only)}
               harmony_render.render_ids: mirrors the vLLM chat endpoint's rendering,
               emits token ids directly, identical token-for-token to the chat baseline
               (since 2026-08-18; before that it went through jinja to text and was
               then tokenized by completions, which disagreed with chat in two places --
               empty-content turns and literal <|...|> markers, see the header of
               harmony_render.py). Date pinned to COLLECT_DATE (matching pin method on
               the vLLM side: METHOD.md section 6-4)
  POST /encode {"text": generated text}          -> {"ids":[...]}
               gpt-oss HF tokenizer's encode(add_special_tokens=False). Since 2026-08-18
               (ident3), the head resent after injection uses the model-generated token
               ids directly; /encode is only used to encode NOTE on its own:
               prompt = prefix_ids + head_ids + encode(NOTE)
  POST /decode {"ids":[...]}                -> {"text": ...}
               HF tokenizer's decode(skip_special_tokens=False); the driver checks
               decode(head_ids) == the text prefix received in the stream before it resends
  GET  /health                             -> echoes back the startup config (theta/T/model
               path/render convention, etc). The driver checks render == "harmony_ids"
               before it starts running, to guard against pointing at a stale service

Probe forward-pass convention (design doc section 4.1; known difference from
training/replay):
  Training and replay evaluation run one forward pass over the whole event and take
  logits at each boundary token position (eval_tool.score_causal); the live run can't
  see the future, so it can only do "forward pass per prefix, take the logits at the
  last real token position." Under causal attention the two are mathematically
  equivalent; the only residual is a tokenization effect at the prefix boundary.
  --selftest uses the saved logits_test.pt to quantify this difference event by event
  (see below).

Single-threaded HTTP is enough: the driver is serial, only one request is in flight
at a time.

Usage:
  # serve (GPU; two 0.6B probes in bf16, about 3GB). --theta is required, refuses to
  # run without it (METHOD.md axis 4)
  cprobe-env/bin/python pipeline/inject/probe_server.py serve \\
      --theta 0.925 --port 8790 --device cuda:0

  # selftest (runs on plain CPU too, float32; samples N test-stack events and checks
  # firing behavior)
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

import harmony_render as HR                                   # noqa: E402
import rebuild as R                                           # noqa: E402

# All default paths come from the plan_config.json of that theta=0.925 injection replay --
# the live-run line evaluates that exact same pair of probes; swapping probes requires
# passing the args explicitly
CTOOL = PROJ / "pipeline/runs/c1_gptoss_ctool"
CGEN = PROJ / "pipeline/runs/c1_gptoss_cgen"
GPTOSS_TOK = "/net/tokyo100-10g/data/str01_01/y-guo/models/gpt-oss-120b"


def encode_ids(tok, text, special=False):
    """Text -> gpt-oss token ids for the driver's resend after a fire (2026-09-12).
    special=False: control markers such as <|end|> inside the text stay plain text (a `think`
    format's injected text carries zero special tokens, METHOD.md R2, even when a result
    happens to contain one). special=True: the markers become their special tokens (an `after`
    format closes the thinking and appends a prefetch message)."""
    return tok.encode(text, add_special_tokens=False,
                      split_special_tokens=(not special))


def load_ctool(run, dev):
    """[Mirrors eval_tool.load_causal] loads the backbone from best/ and the head from best/head.pt."""
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
        # The training side sets this explicitly to left (train_causal_tool.build); if the saved
        # tokenizer loses this setting it will silently right-truncate and cut off the tail of
        # the thinking -- better to fix it back here and raise a warning
        print(f"[warn] ctool tokenizer truncation_side="
              f"{tok.truncation_side}, changing back to left", flush=True)
        tok.truncation_side = "left"
    rep = json.loads((run / "REPLAY_REPORT.json").read_text())
    return model, tok, meta, id2label, rep["temperature"]


def load_cgen(run, dev):
    """[Mirrors replay_inject.gen_calls's loading], stays resident, never unloaded."""
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
    def __init__(self, ctool_run, cgen_run, tokenizer_path, theta, dev,
                 render_only=False):
        self.ctool_run, self.cgen_run = str(ctool_run), str(cgen_run)
        self.dev = dev
        self.theta = theta
        self.render_only = render_only
        self.oss_tok = AutoTokenizer.from_pretrained(tokenizer_path)
        if render_only:
            # Only open /render /encode /health: comparing the no-probe arm against the chat baseline
            # needs no probe (added 2026-08-18; at this point the c1_gptoss_* probes had already
            # been deleted in the 08-02 cleanup and not yet retrained). Any call to /score /gen gets
            # a flat 503, never silently pretends a probe is there
            self.ct = self.cg = None
            self.ct_meta = dict(n_labels=None, max_len=None)
            self.T = None
            self.max_len = None
            return
        (self.ct, self.ct_tok, self.ct_meta,
         self.id2label, self.T) = load_ctool(Path(ctool_run), dev)
        self.cg, self.cg_tok, self.cg_meta = load_cgen(Path(cgen_run), dev)
        self.max_len = self.ct_meta["max_len"]

    def _need_probes(self, what):
        if self.render_only:
            raise RuntimeError(f"{what}: the service was started with --render-only, no probe installed")

    @torch.no_grad()
    def score(self, text):
        self._need_probes("/score")
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
        self._need_probes("/gen")
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
        # effort not passed = the collection convention (high); the effort-control arm passes
        # low/medium
        # date pinned to COLLECT_DATE (changed 2026-08-02): the live-run vs w0 framework
        # alignment investigation found that the current date is a needless perturbation
        # relative to the collection convention, which decoding amplifies into trajectory
        # divergence; the replay line has always pinned the collection day, and the live run
        # has used the same convention since v2
        ids = HR.render_ids(messages, effort=effort or R.REASONING_EFFORT,
                            start_date=R.COLLECT_DATE)
        return dict(prefix_ids=ids, n_tokens=len(ids), prefix=HR.decode(ids))

    def encode(self, text, special=False):
        return dict(ids=encode_ids(self.oss_tok, text, special))

    def decode(self, ids):
        # 2026-08-18 (ident3): after the driver cuts the head at a token boundary, it uses this
        # to check decode(head_ids) == the text prefix received in the stream, and refuses to
        # resend if they don't match.
        # skip_special_tokens=False: <|channel|> and the like are tokens the model actually wrote
        return dict(text=self.oss_tok.decode(ids, skip_special_tokens=False))

    def config(self):
        return dict(theta=self.theta, temperature=self.T,
                    ctool=None if self.render_only else self.ctool_run,
                    cgen=None if self.render_only else self.cgen_run,
                    render_only=self.render_only,
                    n_labels=self.ct_meta["n_labels"],
                    max_len=self.max_len, device=str(self.dev),
                    render="harmony_ids", decode=True, encode_special=True,
                    start_date=R.COLLECT_DATE)


def serve(a):
    if a.theta is None and not a.render_only:
        sys.exit("--theta is required (METHOD.md axis 4: θ is always manual); use --render-only for render-only mode")
    probe = Probe(a.ctool_run, a.cgen_run, a.tokenizer, a.theta, a.device,
                  render_only=a.render_only)
    print(f"probe ready: {json.dumps(probe.config())}", flush=True)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):                 # Silence the default access log
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
                elif self.path == "/encode":
                    out = probe.encode(req["text"], bool(req.get("special", False)))
                elif self.path == "/decode":
                    out = probe.decode(req["ids"])
                else:
                    self._reply(dict(error="unknown path"), 404)
                    return
                out["wall_s"] = round(time.time() - t0, 4)
                self._reply(out)
            except Exception as e:                     # The driver needs to see the original error text
                self._reply(dict(error=f"{type(e).__name__}: {e}"), 500)

    print(f"listening on :{a.port}", flush=True)
    HTTPServer(("0.0.0.0", a.port), H).serve_forever()


def selftest(a):
    """Checks the live-run convention against the saved test stack (design doc section 4.1);
    needs neither a GPU nor the service.

    For each sampled event: run every one of its boundary prefixes through the same
    forward pass as /score, and compare against the logits from the whole-event forward
    pass in logits_test.pt:
      - firing-behavior consistency: is the boundary index of the first theta crossing
        the same (this is the only quantity that affects the experiment)
      - max absolute difference in confidence (for reference only)
    Then run the firing prefix through the same generation as /gen, and compare against
    the gen_call in the theta=0.925 replay's plan.jsonl.
    Exit code: 0 if all firing boundaries agree, 1 if any disagree (a numeric difference
    is only printed, not treated as failure -- bf16/float32 and tokenization-boundary
    effects are expected to cause small differences).
    """
    if a.theta is None:
        sys.exit("--theta is required (to cross-check the replay where θ=0.925, pass 0.925)")
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
    print(f"selftest: {len(keys) - bad}/{len(keys)} events have consistent firing behavior", flush=True)
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("serve", serve), ("selftest", selftest)]:
        p = sub.add_parser(name)
        p.add_argument("--ctool-run", default=str(CTOOL))
        p.add_argument("--cgen-run", default=str(CGEN))
        p.add_argument("--tokenizer", default=GPTOSS_TOK)
        p.add_argument("--theta", type=float, default=None,
                       help="fire threshold, required (METHOD.md axis 4: θ is always manual, refuse to run if not given)")
        p.add_argument("--device", default="cuda:0")
        p.set_defaults(fn=fn)
    sub.choices["serve"].add_argument("--port", type=int, default=8790)
    sub.choices["serve"].add_argument(
        "--render-only", action="store_true",
        help="do not install a probe, only enable /render /encode /health (CPU is enough; for comparing the "
             "no-probe arm vs chat baseline). /score /gen return 500")
    sub.choices["selftest"].add_argument("--events", type=int, default=3)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
