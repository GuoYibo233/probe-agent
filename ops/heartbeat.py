#!/usr/bin/env python3
"""心跳:长程任务脚本向采样器上报进度的唯一通道(设计文档 §2)。

一行 = 前缀 "@hb " + 一个 JSON。必填 done/total/unit/ts,选填
tok_in/tok_out(累计值)/loss/status("done"=正常收尾)。
进主循环先 emit(0, total, unit) 一条——那是"模型加载完了"的标志。
只用标准库:任何 venv 都要能 import 本文件。
"""
import json
import sys
import time

PREFIX = "@hb "
_REQUIRED = ("done", "total", "unit", "ts")


def emit(done, total, unit, *, tok_in=None, tok_out=None, loss=None,
         status=None, stream=None):
    rec = {"done": int(done), "total": int(total), "unit": str(unit),
           "ts": round(time.time(), 1)}
    if tok_in is not None:
        rec["tok_in"] = int(tok_in)
    if tok_out is not None:
        rec["tok_out"] = int(tok_out)
    if loss is not None:
        rec["loss"] = round(float(loss), 5)
    if status is not None:
        rec["status"] = str(status)
    out = stream or sys.stdout
    out.write(PREFIX + json.dumps(rec) + "\n")
    out.flush()


def parse(line):
    """心跳行 -> dict;不是合法心跳行返回 None(监控端只认这个入口)。"""
    line = line.strip()
    if not line.startswith(PREFIX):
        return None
    try:
        rec = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(rec, dict) or any(k not in rec for k in _REQUIRED):
        return None
    return rec
