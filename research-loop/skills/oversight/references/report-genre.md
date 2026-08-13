# R3 evidence genre, in full

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

Every report oversight writes -- routine inspection, on-demand observation, criterion acceptance -- is one genre. This page is the operational form of R3; `verify_report.py`/`evidence_lint.py` enforce it mechanically (double gate: lint + mechanical verifier).

## The marker conventions

- **Repro line**: any line starting with `$ ` is a paste-and-run command. The line immediately below it starting with `= <value>` is the value that command is declared to produce.
- **Excerpt line**: a line starting with `> ` right after a `path:line` reference is a verbatim excerpt from that location -- not paraphrased, not reformatted.
- **Path reference**: `path:line` form, pointing at an openable file and line/record number.

## What must carry a repro command

Any prose line containing an experiential number (a count, a metric value, a difference) needs a `$ ` line within 3 lines below it -- no exceptions. Metadata-class numbers are exempt (`tables/rows.json` → `evidence_lint_exempt`): timestamps, git HEAD / hashes, ledger line numbers, file paths, id-form fields. Frontmatter enum fields (`verdict`, `rejections[]`, `withdrawals[]`) are exempt too -- they're structured data, not prose claims.

## Banned words

Verdict prose is disallowed in report bodies, in either language: 通过 / 没问题 / 符合预期 / passed / looks good / no problems / as expected / all good / everything is fine. Say what was checked and what it showed instead of characterizing it. Frontmatter enum fields (like `verdict` itself) are not prose and are exempt from this list.

## What the mechanical verifier checks

`verify_report.py` recognizes exactly three things: a `path:line` reference (verified by stat + confirming the line exists), the `> ` excerpt line following one (re-compared against the file's actual content, verbatim), and a `$ cmd` / `= value` pair (the command is rerun, its output re-compared against the declared value -- numeric comparison uses `==`, floats tolerate `1e-9`).

## Zero-count claims

A negative claim ("no X found") is not just a bare zero -- attach the full scan scope (what was searched) and the total line/row count scanned. A zero without that context is indistinguishable from "didn't actually look."

## Provenance block

Every report header carries three items: generation time, git HEAD, and the line counts/hashes of the ledgers read. These are metadata, not experiential claims -- they don't each need their own `$ ` repro line, but they must be mechanically re-derivable from whatever file the report names (per the metadata exemption above).
