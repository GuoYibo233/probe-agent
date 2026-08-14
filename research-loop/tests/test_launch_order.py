"""Tests for ledger_cmds/launchcmd.py -- `launch-order` and `approve-spec`
(issues/08-launch-order.md). Numbered comment blocks below correspond to
the ticket's "测试" list 1-7 (approve-spec's own round-trip test is folded
into blocks 3 and 7, matching the ticket's own grouping)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import _lib
import helpers

SPEC_BODY = "Item IT-001 does the thing.\n"


def _sandbox(tmp):
    return helpers.make_sandbox(Path(tmp))


def _cfg(root):
    return _lib.load_config(root)


def _read_config(root):
    return json.loads((root / "research-loop.json").read_text(encoding="utf-8"))


def _write_config(root, data):
    (root / "research-loop.json").write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _registry_argv(root, task, *extra):
    """Build an argv that actually starts with the sandbox's real
    registry_cmd prefix (sys.executable + absolute stub_registry.py path) --
    helpers.make_launch_order()'s default argv is a relative-form stand-in
    that does NOT align with that prefix (2026-08-13 wave1 note on this
    ticket)."""
    cfg = _cfg(root)
    prefix = _lib.split_cmd(cfg.get("registry_cmd"), "test", "registry_cmd")
    return prefix + [task] + list(extra)


def _draft(root, **over):
    task = over.pop("registry_task", "noop")
    argv = over.pop("argv", None)
    if argv is None:
        argv = _registry_argv(root, task)
    return helpers.make_launch_order(registry_task=task, argv=argv, **over)


def _write_draft(root, name, row) -> Path:
    path = root / f"{name}.json"
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    return path


def _launch_order(root, path, layer="deploy"):
    return helpers.run_ledger(root, "launch-order", "--layer", layer, "--file", str(path))


def _approve_spec(root, path, by="user"):
    return helpers.run_ledger(root, "approve-spec", str(path), "--by", by)


def _launch_orders_dir(root) -> Path:
    return _cfg(root).ledger_path("launch_orders")


def _decisions_rows(root):
    return _lib.jsonl_rows(_cfg(root).ledger_path("decisions"))


def _write_spec(root, rel=".scratch/demo/spec.md") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "spec_version": 1,
        "approved_by": None,
        "approved_date": None,
        "approved_digest": None,
        "withdrawals": [],
    }
    lines = ["---\n"]
    for key, value in header.items():
        lines.append(f"{key}: {json.dumps(value)}\n")
    lines.append("---\n")
    path.write_text("".join(lines) + SPEC_BODY, encoding="utf-8")
    return path


def _write_approved_spec_with_body(root, rel, body, *, approved_by="user") -> Path:
    """Write and approve (correctly recomputed approved_digest) a spec file
    at `rel` whose body is exactly `body` -- same two-phase digest dance
    _write_spec()'s own approved=True path does, but for an arbitrary path
    and body (used to build an unrelated-but-genuinely-approved decoy)."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "spec_version": 1, "approved_by": None, "approved_date": None,
        "approved_digest": None, "withdrawals": [],
    }
    lines = ["---\n"] + [f"{k}: {json.dumps(v)}\n" for k, v in header.items()] + ["---\n"]
    path.write_text("".join(lines) + body, encoding="utf-8")
    digest = _lib.spec_digest(path)
    header["approved_by"] = approved_by
    header["approved_date"] = _lib.today()
    header["approved_digest"] = digest
    lines = ["---\n"] + [f"{k}: {json.dumps(v)}\n" for k, v in header.items()] + ["---\n"]
    path.write_text("".join(lines) + body, encoding="utf-8")
    return path


def _write_spec_custom(root, rel, header) -> Path:
    """Fixture-only spec write with a caller-given header dict -- unlike
    _write_spec (which hardcodes spec_version: 1), this lets a test build
    frontmatter where the spec_version key is missing entirely or present as
    an explicit null."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---\n"]
    for key, value in header.items():
        lines.append(f"{key}: {json.dumps(value)}\n")
    lines.append("---\n")
    path.write_text("".join(lines) + SPEC_BODY, encoding="utf-8")
    return path


def _set_header_fields(path, **updates):
    """Fixture-only header mutation (not launchcmd's own write path) --
    used to exercise header-only vs body edits against spec_digest."""
    fields, body = _lib.parse_frontmatter(path.read_text(encoding="utf-8"))
    fields.update(updates)
    lines = ["---\n"]
    for key, value in fields.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")
    lines.append("---\n")
    path.write_text("".join(lines) + body, encoding="utf-8")


def _decided_d001(root, **over):
    row = helpers.make_decision_row(decision_id="D001", status="decided", affects=[])
    row.update(over)
    helpers.write_jsonl(_cfg(root).ledger_path("decisions"), [row])


# ---------------------------------------------------------------------------
# 1. quick=false missing spec_ref/issue_ref/decision_refs -> schema
#    conditional rejects before any registry/approval/decision work happens.
# ---------------------------------------------------------------------------


def test_quick_false_missing_refs_rejected_by_schema():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        row = _draft(root, quick=False, spec_ref=None, issue_ref=None, decision_refs=None)
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.spec_ref" in err


# ---------------------------------------------------------------------------
# 2. registry three-check: prefix mismatch, token mismatch (exact message),
#    task not listed, registry_query null ("not wired").
# ---------------------------------------------------------------------------


def test_registry_argv_prefix_mismatch_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            argv=["not-the-registry-cmd", "noop"],
        )
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.registry_task" in err


def test_registry_token_mismatch_rejected_with_exact_message():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        # argv's own token ("record") is a real registered task, so the
        # first two registry checks pass -- only the token != registry_task
        # comparison should fire.
        row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            registry_task="noop", argv=_registry_argv(root, "record"),
        )
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.registry_task: token after registry prefix does not match" in err


def test_registry_task_not_listed_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            registry_task="ghost-task", argv=_registry_argv(root, "ghost-task"),
        )
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.registry_task: task is not in the registry" in err


def test_registry_query_null_rejected_not_wired():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        cfg_data = _read_config(root)
        cfg_data["registry_query"] = None
        _write_config(root, cfg_data)

        row = _draft(root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None)
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "not wired" in err


# ---------------------------------------------------------------------------
# 3. pre-launch approval gate: unapproved rejected, approved passes,
#    body edit after approval -> approval_stale, header-only edits
#    (withdrawals append / spec_version+1) -> still not stale.
# ---------------------------------------------------------------------------


def test_approval_gate_rejects_unapproved_then_passes_after_approve():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        spec_path = _write_spec(root)
        _decided_d001(root)

        row = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=["D001"], run_id="run-001",
        )
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.spec_ref: spec not approved" in err

        code, out, err = _approve_spec(root, spec_path, by="user")
        assert code == 0, (out, err)

        code, out, err = _launch_order(root, path)
        assert code == 0, (out, err)


def test_approval_gate_ambiguous_spec_ref_rejected_not_first_match():
    # F1 false-green repro (sdd/final-review.md): an unrelated file that
    # happens to also mention the same item_id, carries its own valid
    # frontmatter with a correctly-approved header, and sorts alphabetically
    # before the real spec ("another/spec.md" < "demo/spec.md") -- the old
    # per-caller "first parseable+matching file wins" search picked this
    # decoy and let the launch through even though the *real* spec item was
    # never approved. find_spec_files instead reports every match and both
    # callers refuse to guess among them. Rerun this fixture against the
    # pre-fix launchcmd.py and it exits 0 (bug reproduced); against the fix,
    # it's a hard reject naming both files.
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        decoy_path = _write_approved_spec_with_body(
            root, ".scratch/another/spec.md",
            "Unrelated spec that happens to also mention IT-001 in passing.\n",
        )
        real_spec_path = _write_spec(root)  # .scratch/demo/spec.md -- never approved

        row = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=[], run_id="run-001",
        )
        path = _write_draft(root, "run-001", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.spec_ref" in err
        assert str(decoy_path) in err
        assert str(real_spec_path) in err


def test_approval_gate_stale_after_body_edit():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        spec_path = _write_spec(root)
        code, out, err = _approve_spec(root, spec_path, by="user")
        assert code == 0, (out, err)

        # touch the body -- approved_digest was computed before this edit.
        spec_path.write_text(
            spec_path.read_text(encoding="utf-8") + "!", encoding="utf-8"
        )

        row = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=[], run_id="run-002",
        )
        path = _write_draft(root, "run-002", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.spec_ref: approval_stale" in err


def test_approval_gate_not_stale_after_header_only_edits():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        spec_path = _write_spec(root)
        code, out, err = _approve_spec(root, spec_path, by="user")
        assert code == 0, (out, err)

        # header-only edit #1: append a withdrawals entry.
        _set_header_fields(
            spec_path,
            withdrawals=[{"date": _lib.today(), "by": "user", "reason": "unrelated note"}],
        )
        row = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=[], run_id="run-a",
        )
        path = _write_draft(root, "run-a", row)
        code, out, err = _launch_order(root, path)
        assert code == 0, (out, err)

        # header-only edit #2: bump spec_version.
        fields, _body = _lib.parse_frontmatter(spec_path.read_text(encoding="utf-8"))
        _set_header_fields(spec_path, spec_version=fields.get("spec_version", 1) + 1)
        row2 = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=[], run_id="run-b",
        )
        path2 = _write_draft(root, "run-b", row2)
        code, out, err = _launch_order(root, path2)
        assert code == 0, (out, err)


def test_quick_true_with_nonnull_unapproved_spec_ref_skips_approval_gate():
    """quick=true -> the whole approval gate is skipped (spec.md §2.6
    "quick=true -> 本条整个跳过"), not only when spec_ref happens to be
    null. spec_ref here names a real, but unapproved, spec item -- if the
    gate ran at all it would reject with "spec not approved" (as
    test_approval_gate_rejects_unapproved_then_passes_after_approve does for
    quick=false); this pins down that quick=true bypasses that check
    entirely rather than narrowing it to spec_ref-is-null."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _write_spec(root)  # exists, unapproved (approved_by stays null)

        row = _draft(
            root, quick=True, spec_ref="IT-001", issue_ref=None, decision_refs=None,
            run_id="run-quick-spec-ref",
        )
        path = _write_draft(root, "run-quick-spec-ref", row)

        code, out, err = _launch_order(root, path)
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 4. quick=true with all three refs null -> every gate waived, write
#    succeeds.
# ---------------------------------------------------------------------------


def test_quick_true_all_refs_null_writes_successfully():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            run_id="run-quick-1", batch_id="quick-20260814-1",
        )
        path = _write_draft(root, "run-quick-1", row)

        code, out, err = _launch_order(root, path)
        assert code == 0, (out, err)

        lo_path = _launch_orders_dir(root) / "run-quick-1.json"
        assert lo_path.exists()
        written = json.loads(lo_path.read_text(encoding="utf-8"))
        assert written["run_id"] == "run-quick-1"
        assert written["quick"] is True
        # #157: helpers.make_launch_order()'s default expected_outputs is a
        # real, non-empty contract now -- schema validation (minItems: 1)
        # passes it same as everything else here, pinned down explicitly.
        assert written["expected_outputs"]


def test_empty_expected_outputs_rejected_by_schema_before_write():
    """F1 (wave7 fix1): rows.json launch_order.expected_outputs carries
    minItems: 1, but that keyword only bites if _lib._check_value() actually
    reads it -- before this fix it silently passed straight through schema
    validation, so `launch-order --file draft.json` with `expected_outputs:
    []` wrote the file to disk (exit 0). output_check.py's own empty-list
    refusal is a read-time backstop for orders written before the minItems
    bump; it must not be the only gate. Nothing lands on disk here."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        row = _draft(root, expected_outputs=[], run_id="run-empty-outputs")
        path = _write_draft(root, "run-empty-outputs", row)

        code, out, err = _launch_order(root, path)
        assert code == 2, (out, err)
        assert "launch_order.expected_outputs" in err
        assert "minItems" in err

        lo_path = _launch_orders_dir(root) / "run-empty-outputs.json"
        assert not lo_path.exists()


# ---------------------------------------------------------------------------
# 5. promoted_from: missing target rejected, target quick=false rejected,
#    target quick=true passes.
# ---------------------------------------------------------------------------


def test_promoted_from_missing_target_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            run_id="run-promoted", promoted_from="ghost-run",
        )
        path = _write_draft(root, "run-promoted", row)

        code, out, err = _launch_order(root, path)
        assert code == 2
        assert "launch_order.promoted_from" in err


def test_promoted_from_pointing_to_non_quick_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        spec_path = _write_spec(root)
        _approve_spec(root, spec_path, by="user")
        _decided_d001(root)

        base_row = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=["D001"], run_id="run-base",
        )
        base_path = _write_draft(root, "run-base", base_row)
        code, out, err = _launch_order(root, base_path)
        assert code == 0, (out, err)

        promo_row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            run_id="run-promoted", promoted_from="run-base",
        )
        promo_path = _write_draft(root, "run-promoted", promo_row)
        code, out, err = _launch_order(root, promo_path)
        assert code == 2
        assert "launch_order.promoted_from: promoted_from must point to a quick launch order" in err


def test_promoted_from_pointing_to_quick_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        quick_row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            run_id="run-quick-base",
        )
        quick_path = _write_draft(root, "run-quick-base", quick_row)
        code, out, err = _launch_order(root, quick_path)
        assert code == 0, (out, err)

        promo_row = _draft(
            root, quick=True, spec_ref=None, issue_ref=None, decision_refs=None,
            run_id="run-promoted-2", promoted_from="run-quick-base",
        )
        promo_path = _write_draft(root, "run-promoted-2", promo_row)
        code, out, err = _launch_order(root, promo_path)
        assert code == 0, (out, err)


# ---------------------------------------------------------------------------
# 6. same run_id written twice: one file on disk, D001.affects contains the
#    run_id exactly once (backfill idempotency).
# ---------------------------------------------------------------------------


def test_same_run_id_twice_is_idempotent_and_affects_backfill_dedups():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        spec_path = _write_spec(root)
        _approve_spec(root, spec_path, by="user")
        _decided_d001(root)

        row = _draft(
            root, quick=False, spec_ref="IT-001", issue_ref="01-example",
            decision_refs=["D001"], run_id="run-affects",
        )
        path = _write_draft(root, "run-affects", row)

        for _ in range(2):
            code, out, err = _launch_order(root, path)
            assert code == 0, (out, err)

        matches = list(_launch_orders_dir(root).glob("run-affects.json"))
        assert len(matches) == 1

        by_id = {r["decision_id"]: r for r in _decisions_rows(root)}
        assert by_id["D001"]["affects"].count("run-affects") == 1


# ---------------------------------------------------------------------------
# 7. approve-spec: body bytes identical before/after, header fields set.
# ---------------------------------------------------------------------------


def test_approve_spec_preserves_body_bytes_and_sets_header_fields():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        spec_path = _write_spec(root)
        _, original_body = _lib.parse_frontmatter(spec_path.read_text(encoding="utf-8"))

        code, out, err = _approve_spec(root, spec_path, by="the user")
        assert code == 0, (out, err)

        new_text = spec_path.read_text(encoding="utf-8")
        fields, new_body = _lib.parse_frontmatter(new_text)
        assert new_body == original_body
        assert fields["approved_by"] == "the user"
        assert fields["approved_date"] == _lib.today()
        assert fields["approved_digest"] == _lib.spec_digest(spec_path)
        assert fields["spec_version"] == 1
        assert fields["withdrawals"] == []


def test_approve_spec_rejects_file_without_frontmatter():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        bad_path = root / "not-a-spec.md"
        bad_path.write_text("# no frontmatter here\n", encoding="utf-8")

        code, out, err = _approve_spec(root, bad_path)
        assert code == 2


def test_approve_spec_defaults_missing_spec_version_key_to_one():
    """The ticket's "spec_version 缺则置 1" default only actually fires when
    spec_version starts out missing or null -- _write_spec's own fixture
    always starts at 1, so test_approve_spec_preserves_body_bytes_and_
    sets_header_fields's `== 1` assertion passes whether or not the default
    branch runs. This pins the branch down with a frontmatter that has no
    spec_version key at all."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        header = {
            "approved_by": None,
            "approved_date": None,
            "approved_digest": None,
            "withdrawals": [],
        }
        spec_path = _write_spec_custom(root, ".scratch/demo/spec-missing-version.md", header)

        code, out, err = _approve_spec(root, spec_path, by="user")
        assert code == 0, (out, err)

        fields, _body = _lib.parse_frontmatter(spec_path.read_text(encoding="utf-8"))
        assert fields["spec_version"] == 1


def test_approve_spec_defaults_null_spec_version_to_one():
    """Same default branch as the missing-key case above, but the key is
    present with an explicit JSON null -- fields.get("spec_version") is None
    either way, but the frontmatter shape differs."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        header = {
            "spec_version": None,
            "approved_by": None,
            "approved_date": None,
            "approved_digest": None,
            "withdrawals": [],
        }
        spec_path = _write_spec_custom(root, ".scratch/demo/spec-null-version.md", header)

        code, out, err = _approve_spec(root, spec_path, by="user")
        assert code == 0, (out, err)

        fields, _body = _lib.parse_frontmatter(spec_path.read_text(encoding="utf-8"))
        assert fields["spec_version"] == 1
