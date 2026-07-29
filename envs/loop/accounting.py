"""闭环记账:墙钟 / token / 任务成败三表的最小实现(仅 stdlib)。

EpisodeLedger 一集(一个任务实例 × 一种口径)一本账,逐步记生成、逐次记
探针调用(monitor 的 sink 直接接 ledger.probe)、记触发与核对,close()
落 jsonl + 汇总。被打断的生成拿不到服务端 usage —— tokenize_count 用
vLLM /tokenize 端点(同模型同分词器)补精确 token 数。
"""

import json
import time
import urllib.request


def tokenize_count(base_url, model, text, timeout=60):
    """vLLM /tokenize:返回 text 的精确 token 数。base_url 含 /v1 与否皆可。"""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    req = urllib.request.Request(
        root + "/tokenize",
        data=json.dumps({"model": model, "prompt": text}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["count"]


class EpisodeLedger:
    def __init__(self, path, meta):
        self.path = path
        self.f = open(path, "w")
        self.t0 = time.time()
        self.sums = {"gen_tokens_out": 0, "gen_tokens_in": 0, "gen_wall_s": 0.0,
                     "probe_calls": 0, "probe_ms": 0.0, "n_triggers": 0,
                     "n_aborted": 0}
        self._w({"type": "meta", **meta})

    def _w(self, rec):
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()

    def gen(self, step, g, tokens_out=None):
        """g = StreamingChat/Chat 返回 dict。tokens_out:被打断时由调用方
        用 tokenize_count 补的精确数(usage 为 None 的情况)。"""
        out = g["usage"].get("out") if g.get("usage") else None
        if out is None:
            out = tokens_out or 0
        inn = (g["usage"].get("in") or 0) if g.get("usage") else 0
        self.sums["gen_tokens_out"] += out
        self.sums["gen_tokens_in"] += inn
        self.sums["gen_wall_s"] += g.get("wall_s", 0.0)
        self.sums["n_aborted"] += int(bool(g.get("aborted")))
        self._w({"type": "gen", "step": step, "wall_s": g.get("wall_s"),
                 "tokens_in": inn, "tokens_out": out,
                 "aborted": bool(g.get("aborted")),
                 "n_chars_think": len(g.get("reasoning", "") or "")})

    def probe(self, rec):
        """ProbeMonitor 的 sink。"""
        self.sums["probe_calls"] += 1
        self.sums["probe_ms"] += rec.get("ms", 0.0)
        self._w({"type": "probe", **rec})

    def trigger(self, step, decision, agent_actual=None, match=None):
        """首触记录;agent_actual/match 在事后核对时补(影子口径)。"""
        self.sums["n_triggers"] += 1
        self._w({"type": "trigger", "step": step, **decision,
                 "agent_actual": agent_actual, "match": match})

    def env_step(self, step, action, result_head, **extra):
        self._w({"type": "env", "step": step, "action": action,
                 "result_head": str(result_head)[:200], **extra})

    def close(self, success, **extra):
        total = {"type": "final", "success": success,
                 "wall_s_total": round(time.time() - self.t0, 2),
                 **{k: (round(v, 2) if isinstance(v, float) else v)
                    for k, v in self.sums.items()}, **extra}
        self._w(total)
        self.f.close()
        return total
