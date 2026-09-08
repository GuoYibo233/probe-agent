#!/usr/bin/env python3
"""spec_lint: mechanically checks that spec.md's prose is consistent with the data
tables in tables/.

Design rationale (2026-08-13 user refactor order): closed enumerations are written out
once, in tables/ only; prose references must not restate them. Defects this script
catches:
  E1 tables inconsistent with each other (a table is broken on its own)
  E2 prose contains an old enumeration that conflicts with a table ("written in two
     places, drifted in one" -- the top defect class across 15 rounds of review)
  E3 prose re-grows a closed enumeration (a routing table, a pipeline enum chain)
  E4 rows.json's managed block lacks enough to generate a schema (missing
     required/properties/primary_key, required out of bounds, $enum pointing to a
     nonexistent enum, $ref_to pointing to a nonexistent ledger, a jsonl ledger row
     type missing schema_version) -- the static precondition for section 0.5 item 5,
     "generated from the table"
  W1 a snake_case backtick word in the prose is not in any table's vocabulary
     (suspected invented field)

Scope: static consistency check on the design draft. Consistency between generated
artifacts (schemas/ and the owners default table) and the tables is not this script's
job -- that belongs to the implementation-time artifact, ledger.py gen-schemas --check.

exit 0 = clean (warnings do not block); exit 1 = has errors.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SPEC = ROOT / "spec.md"
# Tables have lived at repo-root research-loop/tables/ alongside the plugin itself since the
# 2026-08-13 rollout (the landing of §0.5 rule 5, "spec and implementation share one source of
# truth"); spec_lint points at that same copy.
TABLES = ROOT.parent.parent / "research-loop" / "tables"

# snake_case words that legitimately appear in prose but do not belong to any table (W1
# allowlist)
ALLOW = {
    "research_loop",  # word-splitting variants of research-loop.json
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
            fail(f"E1 {f.name}: JSON parse failed: {e}")
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
    """Every key name / field name / enum value / sentinel value that ever appears in a table -> vocabulary."""
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
    """rows.json enums + the value domains from writes.json -> {enum name: frozenset(values)}."""
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
            err(f"E1 missing table tables/{need}.json")
    if ERRORS:
        return
    led = tabs["ledgers"]["ledgers"]
    owner_domain = set(tabs["writes"]["owner_values"])
    for name, spec in led.items():
        if spec["owner"] not in owner_domain:
            err(f"E1 ledgers.json {name}.owner={spec['owner']} not in writes.json owner_values")
        if spec.get("cap") is not None and spec["format"] != "jsonl":
            err(f"E1 ledgers.json {name}: a non-jsonl ledger must not set cap")
    if led.get("runs", {}).get("cap") is not None:
        err("E1 ledgers.json runs.cap must be null only")
    for name, spec in tabs["ledgers"].get("optional_ledgers", {}).items():
        if spec["owner"] not in owner_domain:
            err(f"E1 ledgers.json optional {name}.owner not in owner_values")
    # the form2 allowlist ledger must exist
    for acct in tabs["writes"]["write_forms"]["form2_inplace_whitelist"]:
        if acct.startswith("_"):
            continue
        if acct not in led:
            err(f"E1 writes.json in-place update whitelist points to a nonexistent ledger {acct}")
    check_generatable(tabs)


# E4: the managed block in rows.json must be enough to generate the schema (the static
# precondition of §0.5 rule 5).
# block name -> corresponding ledger name (the schema_version requirement applies only to
# ledgers with format=jsonl).
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
            err(f"E4 rows.json missing managed block {bname}")
            continue
        missing = [k for k in ("required", "properties", "primary_key")
                   if k not in node]
        if missing:
            err(f"E4 {bname} missing {'/'.join(missing)}")
            continue
        props = set(node["properties"])
        for r in node["required"]:
            if r not in props:
                err(f"E4 {bname} required field {r} not in properties")
        for k in node["primary_key"]:
            if k not in props:
                err(f"E4 {bname} primary_key field {k} not in properties")
        for fname, prop in node["properties"].items():
            if not isinstance(prop, dict):
                err(f"E4 {bname}.{fname} is not a dialect field object")
                continue
            for d in field_defs(prop):
                if "$enum" in d and d["$enum"] not in enums:
                    err(f"E4 {bname}.{fname} $enum={d['$enum']} not in rows.enums")
                for ref in ([d["$ref_to"]] if isinstance(d.get("$ref_to"), str)
                            else d.get("$ref_to") or []):
                    if ref.split(".")[0] not in led:
                        err(f"E4 {bname}.{fname} $ref_to={ref} ledger name not in ledgers.json")
        for cond in node.get("conditional", []):
            whens = cond.get("when")
            whens = whens if isinstance(whens, list) else [whens]
            for w in whens:
                if not isinstance(w, dict) or w.get("op") not in ("eq", "neq", "in"):
                    err(f"E4 {bname} conditional's op is invalid: {w}")
                elif w.get("field") not in props:
                    err(f"E4 {bname} conditional references a nonexistent field {w.get('field')}")
            for k in cond.get("require", []) + cond.get("allow_null", []):
                if k not in props:
                    err(f"E4 {bname} conditional target field {k} not in properties")
        if led.get(acct, {}).get("format") == "jsonl" \
                and "schema_version" not in node["required"]:
            err(f"E4 {bname} corresponding jsonl ledger {acct}, required must include schema_version")


def strip_fences(text):
    return re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text,
                  flags=re.S)


def check_prose(tabs):
    text = SPEC.read_text()
    prose = strip_fences(text)
    lines = prose.splitlines()
    enums = collect_enums(tabs)
    vocab = collect_vocab(tabs)

    # E3: the routing table must not be restated in prose
    for i, ln in enumerate(lines, 1):
        if re.search(r"\|\s*用户说\s*\|", ln):
            err(f"E3 spec.md:{i} routing table restated (the single source of truth is tables/routes.json)")

    # E2: pipeline enum chain conflicts with the enum inside the table
    chain_re = re.compile(r"(?:[\w【】一-鿿-]+\|){2,}[\w【】一-鿿-]+")
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("|"):  # md table rows do not count as an enum chain
            continue
        for m in chain_re.finditer(ln):
            members = set(m.group(0).split("|"))
            if any(members <= evals for evals in enums.values()):
                continue  # falling entirely inside a table's enum = a legitimate reference
            for ename, evals in enums.items():
                if len(members & evals) >= 2 and not members <= evals:
                    err(f"E2 spec.md:{i} enum chain `{m.group(0)}` conflicts with {ename}"
                        f" (extra {sorted(members - evals)})")
                    break
            else:
                if len(members) >= 4:
                    warn(f"W2 spec.md:{i} enum chain with 4+ members `{m.group(0)}` doesn't correspond to any table enum"
                         " -- a closed list belongs in tables/")

    # W1: unrecognized snake_case words inside backticks
    for i, ln in enumerate(lines, 1):
        for m in re.finditer(r"`([a-z][a-z0-9_.]{3,})`", ln):
            tok = m.group(1)
            parts = re.split(r"[.]", tok)
            if all(p in vocab or not re.fullmatch(r"[a-z][a-z0-9_]+", p)
                   for p in parts):
                continue
            warn(f"W1 spec.md:{i} `{tok}` isn't in any table's vocabulary (invented a new field?)")


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
