#!/usr/bin/env python3
"""判定引擎:纯函数,零 IO(设计文档 §4)。采样器喂状态进来,拿判定出去。
六格判定按固定优先级判,命中即停:已完成→已挂→疑似卡死→warm-up 中→变慢→健康。
时钟纪律:跨机不比钟——beat_age_s/since_launch_s 由采样器用自己的钟算好喂进来,
心跳 ts 只在 rates() 里同机做差。所有常数收在 DEFAULTS,别处不许硬编码。
"""
from statistics import median

V_DONE, V_DEAD, V_STALL = "已完成", "已挂", "疑似卡死"
V_WARMUP, V_SLOW, V_OK = "warm-up 中", "变慢", "健康"

DEFAULTS = dict(
    sample_interval_s=60.0,   # 采样器一轮的间隔
    stall_mult=5.0,           # 判定线 = 5 × 典型心跳间隔
    stall_floor_samples=3,    # 判定线下限 = 3 轮采样(采样粒度以下分不清停没停)
    escalate_mult=3.0,        # 升级线 = 判定线 × 3
    warmup_line_s=1800.0,     # warm-up 上限,默认 30 分钟
    recent_beats=10,          # 近期速率窗口:最近 ≤10 条心跳
    typical_beats=20,         # 典型心跳间隔:最近 ≤20 个间隔的中位数
    min_intervals=3,          # 攒够 3 个间隔才用自适应判定线
    slow_ratio=0.5,           # 变慢 = 近期速率 < 平均 × 0.5
    port_fail_rounds=3,       # 服务:连续 3 轮端口不应答 = 疑似卡死
)


def typical_gap_s(beat_ts, cfg=DEFAULTS):
    """最近 ≤typical_beats 个心跳间隔的中位数;间隔不足 min_intervals 个返回 None。"""
    ts = list(beat_ts)[-(cfg["typical_beats"] + 1):]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    if len(gaps) < cfg["min_intervals"]:
        return None
    return median(gaps)


def stall_line_s(beat_ts, cfg=DEFAULTS, override=None):
    """判定线(秒)。override=发射时的 --stall-line;样本不足返回 None
    (调用方用 warm-up 上限顶着,长 task/长 step 开局不误报)。"""
    if override is not None:
        return float(override)
    gap = typical_gap_s(beat_ts, cfg)
    if gap is None:
        return None
    return max(cfg["stall_mult"] * gap,
               cfg["stall_floor_samples"] * cfg["sample_interval_s"])


def rates(first_beat, recent_beats, cfg=DEFAULTS):
    """(平均速率, 近期速率),单位 done/秒;算不出的为 None。
    first_beat: 首条心跳 {'ts','done'}(采样器累计状态里存的,不依赖日志尾)。
    recent_beats: 最近 ≤typical_beats 条心跳(升序)。分母全在心跳时间轴上。"""
    if not first_beat or not recent_beats:
        return None, None
    last = recent_beats[-1]
    avg = None
    dt = last["ts"] - first_beat["ts"]
    if dt > 0 and last["done"] >= first_beat["done"]:
        avg = (last["done"] - first_beat["done"]) / dt
    w = recent_beats[-cfg["recent_beats"]:]
    recent = None
    if len(w) >= 2:
        dtw = w[-1]["ts"] - w[0]["ts"]
        if dtw > 0 and w[-1]["done"] >= w[0]["done"]:
            recent = (w[-1]["done"] - w[0]["done"]) / dtw
    return avg, recent


def _judge_service(p, cfg):
    if p["alive"] is False:
        return V_DEAD, True
    if p.get("port_ok"):
        return V_OK, False
    if not p.get("port_ever_ok"):
        if p["since_launch_s"] > p["warmup_s"]:
            esc = p["since_launch_s"] > p["warmup_s"] * cfg["escalate_mult"]
            return V_STALL, esc
        return V_WARMUP, False
    n = p.get("port_fail_rounds", 0)
    if n >= cfg["port_fail_rounds"]:
        esc = n >= cfg["port_fail_rounds"] * cfg["escalate_mult"]
        return V_STALL, esc
    return V_OK, False


def judge(p, cfg=DEFAULTS):
    """一个分片一轮恰好一格。返回 (判定, 是否达升级线)。
    已完成、变慢对服务类不适用(设计 §4 末尾),服务走 _judge_service。"""
    if p["kind"] == "service":
        return _judge_service(p, cfg)
    done, total = p.get("done"), p.get("total")
    if p.get("status") == "done" or (done is not None and total
                                     and done >= total):
        return V_DONE, False
    if p["alive"] is False:
        return V_DEAD, True
    warm = not p["has_beat"]
    age = p["since_launch_s"] if warm else p["beat_age_s"]
    line = p["warmup_s"] if (warm or p.get("stall_s") is None) else p["stall_s"]
    if age > line:
        esc_line = (p["escalate_s"] if p.get("escalate_s") is not None
                    else line * cfg["escalate_mult"])
        return V_STALL, age > esc_line
    if warm:
        return V_WARMUP, False
    if (p.get("recent_rate") is not None and p.get("avg_rate")
            and p["recent_rate"] < cfg["slow_ratio"] * p["avg_rate"]):
        return V_SLOW, False
    return V_OK, False
