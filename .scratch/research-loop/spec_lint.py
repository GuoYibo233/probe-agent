#!/usr/bin/env python3
"""spec_lint: 机械校验 spec.md 散文与 tables/ 数据表的一致性。

设计依据（2026-08-13 用户重构令）：封闭清单只在 tables/ 成文一次，
散文引用不复述。本脚本抓的病：
  E1 表间不一致（表自己坏了）
  E2 散文里出现与表冲突的旧枚举（"两处成文一处漂移"——15 轮复审的头号缺陷类）
  E3 散文里重新长出封闭清单（路由表、管道枚举链）
  E4 rows.json 受管块不够生成 schema（缺 required/properties/primary_key、
     required 越界、$enum 指向不存在的枚举、$ref_to 指向不存在的账、
     jsonl 账行型缺 schema_version）——§0.5 第 5 条"从表生成"的静态前提
  W1 散文里的 snake_case 反引号词不在任何表的词汇表里（疑似发明了新字段）

定位：设计稿静态一致性检查。生成物（schemas/ 与 owners 默认表）与表的
一致性不归本脚本——那是实施期产物，归 ledger.py gen-schemas --check。

exit 0 = 干净（警告不拦）；exit 1 = 有 error。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SPEC = ROOT / "spec.md"
# 表自 2026-08-13 实施起随 plugin 本体住仓库根 research-loop/tables/（§0.5 第 5 条
# "spec 与实现共用一个真源"的落地），spec_lint 指向同一份。
TABLES = ROOT.parent.parent / "research-loop" / "tables"

# 散文里合法出现、但不属于任何表的 snake_case 词（W1 白名单）
ALLOW = {
    "research_loop",  # research-loop.json 的变体切词
    "audit_merge",
    "spec_lint", "spec_version",
    "principle_id", "item_id", "run_id", "batch_id", "blocked_id", "decision_id",
    "claim_id", "fb_id", "issue_id", "schema_version", "grant_ref", "decision_ref",
    "launch_order_ref", "escalation_ref", "runmeta_path", "criterion_cmd",
    "metrics_cmd", "smoke_cmd", "derivation_command", "how_to_read",
    "inspection_report", "expected_runtime_s", "expected_outputs", "expected_commit",
    "output_dir", "artifact_dir", "elapsed_s", "gpu_count", "recorded_at",
    "answered_by", "answered_at", "raised_at", "decided_at", "decided_by",
    "authorized_by", "superseded_by", "withdrawn_by", "withdrawn_reason",
    "retired_by", "retired_reason", "retired_date", "applies_when",
    "approved_by", "approved_date",
    "path_globs", "expires_at", "from_layer", "to_layer",
    "env_name", "dataset_version", "error_classes", "runs_schema",
    "no_log_growth_s", "gpu_idle_s", "startup_grace_s", "min_vram_gb",
    "evidence_path", "metric_name", "evidence_runs", "baseline_runs",
    "candidate_runs", "selection_rule", "spec_ref", "issue_ref", "decision_refs",
    "spec_items", "spec_item", "run_ids", "principle_ref", "created_by", "created_at",
    "output_check", "log_regex", "exit_code", "allow_card_swap", "max_attempts",
    "retriable_errors", "required_keys", "min_bytes", "min_lines", "path_glob",
}


def load_tables():
    tabs = {}
    for f in sorted(TABLES.glob("*.json")):
        try:
            tabs[f.stem] = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            fail(f"E1 {f.name}: JSON 解析失败: {e}")
    return tabs


ERRORS, WARNINGS = [], []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def fail(msg):
    print(msg)
    sys.exit(1)


def collect_vocab(tabs):
    """表里出现过的一切键名/字段名/枚举值/哨兵值 → 词汇表。"""
    vocab = set(ALLOW)

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                vocab.add(k)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            for tok in re.findall(r"[a-z][a-z0-9_]{2,}", node):
                vocab.add(tok)

    walk(tabs)
    return vocab


def collect_enums(tabs):
    """rows.json enums + writes.json 的取值域 → {enum名: frozenset(值)}。"""
    enums = {}
    for name, values in tabs.get("rows", {}).get("enums", {}).items():
        enums[name] = frozenset(values)
    w = tabs.get("writes", {})
    enums["--layer"] = frozenset(w.get("layer_param", {}).get("values", []) +
                                 list(w.get("layer_param", {}).get("special", {})))
    enums["owners"] = frozenset(w.get("owner_values", {}))
    return enums


def check_tables(tabs):
    for need in ("ledgers", "rows", "writes", "config", "routes"):
        if need not in tabs:
            err(f"E1 缺表 tables/{need}.json")
    if ERRORS:
        return
    led = tabs["ledgers"]["ledgers"]
    owner_domain = set(tabs["writes"]["owner_values"])
    for name, spec in led.items():
        if spec["owner"] not in owner_domain:
            err(f"E1 ledgers.json {name}.owner={spec['owner']} 不在 writes.json owner_values")
        if spec.get("cap") is not None and spec["format"] != "jsonl":
            err(f"E1 ledgers.json {name}: 非 jsonl 账不许设 cap")
    if led.get("runs", {}).get("cap") is not None:
        err("E1 ledgers.json runs.cap 只许 null")
    for name, spec in tabs["ledgers"].get("optional_ledgers", {}).items():
        if spec["owner"] not in owner_domain:
            err(f"E1 ledgers.json optional {name}.owner 不在 owner_values")
    # form2 白名单账必须存在
    for acct in tabs["writes"]["write_forms"]["form2_inplace_whitelist"]:
        if acct.startswith("_"):
            continue
        if acct not in led:
            err(f"E1 writes.json 就地更新白名单指向不存在的账 {acct}")
    check_generatable(tabs)


# E4: rows.json 受管块必须够生成 schema（§0.5 第 5 条的静态前提）。
# 块名 → 对应账名（schema_version 要求只对 format=jsonl 的账生效）。
GEN_BLOCKS = {
    "story_row": "story", "decisions_row": "decisions", "blocked_row": "blocked",
    "feedback_rows.suggestion": "feedback", "feedback_rows.review": "feedback",
    "runs_row_normal": "runs", "runs_row_criterion": "runs",
    "launch_order": "launch_orders",
}


def check_generatable(tabs):
    rows = tabs["rows"]
    enums = set(rows.get("enums", {}))
    led = dict(tabs["ledgers"]["ledgers"])
    led.update(tabs["ledgers"].get("optional_ledgers", {}))

    def field_defs(prop):
        yield prop
        if isinstance(prop.get("items"), dict):
            yield prop["items"]

    for bname, acct in GEN_BLOCKS.items():
        node = rows
        for part in bname.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if node is None:
            err(f"E4 rows.json 缺受管块 {bname}")
            continue
        missing = [k for k in ("required", "properties", "primary_key")
                   if k not in node]
        if missing:
            err(f"E4 {bname} 缺 {'/'.join(missing)}")
            continue
        props = set(node["properties"])
        for r in node["required"]:
            if r not in props:
                err(f"E4 {bname} required 字段 {r} 不在 properties")
        for k in node["primary_key"]:
            if k not in props:
                err(f"E4 {bname} primary_key 字段 {k} 不在 properties")
        for fname, prop in node["properties"].items():
            if not isinstance(prop, dict):
                err(f"E4 {bname}.{fname} 不是方言字段对象")
                continue
            for d in field_defs(prop):
                if "$enum" in d and d["$enum"] not in enums:
                    err(f"E4 {bname}.{fname} $enum={d['$enum']} 不在 rows.enums")
                for ref in ([d["$ref_to"]] if isinstance(d.get("$ref_to"), str)
                            else d.get("$ref_to") or []):
                    if ref.split(".")[0] not in led:
                        err(f"E4 {bname}.{fname} $ref_to={ref} 账名不在 ledgers.json")
        for cond in node.get("conditional", []):
            whens = cond.get("when")
            whens = whens if isinstance(whens, list) else [whens]
            for w in whens:
                if not isinstance(w, dict) or w.get("op") not in ("eq", "neq", "in"):
                    err(f"E4 {bname} conditional 的 op 非法: {w}")
                elif w.get("field") not in props:
                    err(f"E4 {bname} conditional 引用不存在的字段 {w.get('field')}")
            for k in cond.get("require", []) + cond.get("allow_null", []):
                if k not in props:
                    err(f"E4 {bname} conditional 目标字段 {k} 不在 properties")
        if led.get(acct, {}).get("format") == "jsonl" \
                and "schema_version" not in node["required"]:
            err(f"E4 {bname} 对应 jsonl 账 {acct}，required 必含 schema_version")


def strip_fences(text):
    return re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text,
                  flags=re.S)


def check_prose(tabs):
    text = SPEC.read_text()
    prose = strip_fences(text)
    lines = prose.splitlines()
    enums = collect_enums(tabs)
    vocab = collect_vocab(tabs)

    # E3: 路由表不许在散文里复述
    for i, ln in enumerate(lines, 1):
        if re.search(r"\|\s*用户说\s*\|", ln):
            err(f"E3 spec.md:{i} 路由表复述（唯一真源是 tables/routes.json）")

    # E2: 管道枚举链与表内枚举冲突
    chain_re = re.compile(r"(?:[\w【】一-鿿-]+\|){2,}[\w【】一-鿿-]+")
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("|"):  # md 表格行不算枚举链
            continue
        for m in chain_re.finditer(ln):
            members = set(m.group(0).split("|"))
            if any(members <= evals for evals in enums.values()):
                continue  # 完整落在某个表枚举里 = 合法引用
            for ename, evals in enums.items():
                if len(members & evals) >= 2 and not members <= evals:
                    err(f"E2 spec.md:{i} 枚举链 `{m.group(0)}` 与 {ename} 冲突"
                        f"（多出 {sorted(members - evals)}）")
                    break
            else:
                if len(members) >= 4:
                    warn(f"W2 spec.md:{i} 四元以上枚举链 `{m.group(0)}` 不对应任何表枚举"
                         "——封闭清单应进 tables/")

    # W1: 反引号里的 snake_case 生词
    for i, ln in enumerate(lines, 1):
        for m in re.finditer(r"`([a-z][a-z0-9_.]{3,})`", ln):
            tok = m.group(1)
            parts = re.split(r"[.]", tok)
            if all(p in vocab or not re.fullmatch(r"[a-z][a-z0-9_]+", p)
                   for p in parts):
                continue
            warn(f"W1 spec.md:{i} `{tok}` 不在任何表的词汇表里（发明了新字段？）")


def main():
    tabs = load_tables()
    check_tables(tabs)
    if not ERRORS:
        check_prose(tabs)
    for w in WARNINGS:
        print(w)
    for e in ERRORS:
        print(e)
    print(f"-- spec_lint: {len(ERRORS)} errors, {len(WARNINGS)} warnings")
    sys.exit(1 if ERRORS else 0)


if __name__ == "__main__":
    main()
