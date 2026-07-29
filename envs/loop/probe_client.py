"""探针客户端 + 触发监视器(任何 venv 可 import,仅 stdlib)。

ProbeMonitor 吃流式思考文本:每个新句界拼前缀(textproto.assemble,与训练
样本逐字节同源)→ 问探针服务 → 按 θ 出决定。三种姿态:
  off      不探(基线组)
  shadow   全程探、只记不动(影子记录;fork 对照 = shadow + 上层在触发点起分支)
  truncate 首次过 θ 返回打断信号(截断组)
触发语义与回放协议一致:首次越阈,只计那一下;shadow 触发后继续探后续句界
(诊断数据,不影响"首触"记录)。
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from textproto import BoundaryTracker, assemble  # noqa: E402


class ProbeClient:
    def __init__(self, base_url, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path):
        with urllib.request.urlopen(self.base_url + path,
                                    timeout=self.timeout) as r:
            return json.loads(r.read())

    def health(self):
        return self._get("/health")

    def score(self, text):
        req = urllib.request.Request(
            self.base_url + "/score",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read())
        out["client_ms"] = round((time.time() - t0) * 1000, 1)
        return out


class ProbeMonitor:
    """一个事件(一步生成)一个 monitor。

    feed(思考全文)/finalize() → None(继续)或打断决定 dict(仅 truncate
    姿态,含 label/conf/at_char/boundary_idx/probe_ms),调用方收到即中止生成。
    shadow 姿态从不打断:首触事后读 monitor.first_trigger(思考期间环境状态
    不变,fork 对照在步末拿步前状态起分支即可,无需流中现场快照)。
    sink: callable(dict),逐次探针调用的记账出口(可给 EpisodeLedger.probe)。
    """

    def __init__(self, client, theta, mode, task, hist, event_id, sink=None):
        assert mode in ("off", "shadow", "truncate")
        self.client, self.theta, self.mode = client, theta, mode
        self.task, self.hist, self.event_id = task, list(hist), event_id
        self.sink = sink or (lambda rec: None)
        self.tracker = BoundaryTracker()
        self.first_trigger = None
        self.n_probes = 0

    def _probe_at(self, text, p, idx):
        prefix = text[:p]
        out = self.client.score(assemble(self.task, self.hist, prefix))
        self.n_probes += 1
        rec = {"event": self.event_id, "boundary_idx": idx, "at_char": p,
               "label": out["label"], "conf": out["conf"],
               "ms": out["ms"], "client_ms": out["client_ms"]}
        self.sink(rec)
        if self.first_trigger is None and out["conf"] >= self.theta:
            self.first_trigger = {"label": out["label"], "conf": out["conf"],
                                  "at_char": p, "boundary_idx": idx,
                                  "probe_ms": out["ms"]}
            if self.mode == "truncate":
                return dict(self.first_trigger, action="truncate")
        return None

    def feed(self, think_text):
        if self.mode == "off":
            return None
        for p in self.tracker.feed(think_text):
            hit = self._probe_at(think_text, p, len(self.tracker.emitted) - 1)
            if hit and hit["action"] == "truncate":
                return hit
        return None

    def finalize(self):
        """生成自然结束:补探全文末尾切点(与训练分布对齐)。"""
        if self.mode == "off":
            return None
        for p in self.tracker.finalize():
            hit = self._probe_at(self.tracker.text, p,
                                 len(self.tracker.emitted) - 1)
            if hit:
                return hit
        return None
