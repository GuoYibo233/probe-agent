"""readonly_map — 只读/非只读工具真值表的装载与标签折叠。

真值表在 pipeline/annotate/readonly/{appworld,bfcl}.json（2026-08-01 定稿：
判定标准是"投机执行零风险才算只读"，登录类按严格只读口径判非只读；
生成器 gen_tables.py，人审记录 REVIEW.md）。

四个训练脚本与三个评测脚本在 --readonly-env 模式下共用本模块。
只用标准库——mbert-env（transformers 4.57.6）与 cprobe-env（>=5.14）都要能 import，
所以这里永远不许出现 torch / transformers。
"""
import json
from pathlib import Path

# 弃权类哨兵：readonly 模式下所有非只读工具折叠成这一个类。
# 评测端靠 label_map.json 里有没有这个串识别"该 run 是不是 readonly 模式训的"。
NON_READONLY = "<NON_READONLY>"

READONLY_ENVS = ("appworld", "bfcl")

_TABLE_DIR = Path(__file__).resolve().parents[1] / "annotate" / "readonly"

# 表外标签占比超过这个阈值就硬停：几乎必然是 env 传错或数据串味，
# 静默折叠下去会把整批训练毁成"全预测弃权"。
UNKNOWN_HARD_LIMIT = 0.05


def table_path(env: str) -> Path:
    return _TABLE_DIR / f"{env}.json"


def load_table(env: str) -> dict:
    """整表：{tool: {"readonly": bool, "count": int, "reason": str, ...}}"""
    if env not in READONLY_ENVS:
        raise SystemExit(f"readonly_map: env 只支持 {READONLY_ENVS}，拿到 {env!r}")
    p = table_path(env)
    if not p.exists():
        raise SystemExit(f"readonly_map: 真值表不存在 {p}")
    return json.loads(p.read_text())


def load_readonly_set(env: str) -> frozenset:
    """该环境所有判为只读的工具名。"""
    return frozenset(k for k, v in load_table(env).items() if v["readonly"])


def collapse(label: str, ro_set: frozenset) -> str:
    """只读标签原样保留，其余（含表外标签）折叠成 NON_READONLY。"""
    return label if label in ro_set else NON_READONLY


def audit(labels, table: dict, where: str) -> dict:
    """清点一批标签：只读/非只读/表外各多少。表外占比超阈值直接硬停。

    labels: 可迭代的工具名（逐样本，不去重）；where: 报错时说清在哪一步。
    返回 dict 供写进 READONLY.json / 训练日志。
    """
    n = n_ro = n_unknown = 0
    unknown = set()
    for lb in labels:
        n += 1
        v = table.get(lb)
        if v is None:
            n_unknown += 1
            unknown.add(lb)
        elif v["readonly"]:
            n_ro += 1
    if n == 0:
        raise SystemExit(f"readonly_map: {where} 零样本，上游必有问题")
    frac_unknown = n_unknown / n
    if frac_unknown > UNKNOWN_HARD_LIMIT:
        raise SystemExit(
            f"readonly_map: {where} 有 {n_unknown}/{n} ({frac_unknown:.1%}) 个标签不在真值表里"
            f"（如 {sorted(unknown)[:5]}）——超过 {UNKNOWN_HARD_LIMIT:.0%} 阈值，"
            f"多半是 --readonly-env 传错或数据串味，硬停。"
        )
    if n_unknown:
        print(f"[readonly_map] 警告：{where} 有 {n_unknown}/{n} 个表外标签，"
              f"已按非只读折叠：{sorted(unknown)}")
    return dict(
        n=n, n_readonly=n_ro, n_nonreadonly=n - n_ro,
        frac_readonly=round(n_ro / n, 6),
        n_unknown=n_unknown, unknown=sorted(unknown),
    )
