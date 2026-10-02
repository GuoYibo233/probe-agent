# 03 close a dead incarnation before a relaunch

Status: resolved
Blocked by: 01
Spec: .scratch/card-record-and-remaining-time/spec.md (section "The dead incarnation")

## What to do

Today a walk or a `refire` lets an open run whose pieces are dead through the launch gate
(`gate_open_row`, `jobs/launch.py:237`) and appends a new start row; `fold()`
(`jobs/registry.py:463-465`) then clears the run's finish, and the dead incarnation never
gets a finish row or a card record.

Before `launch()` (`jobs/launch.py`, the start-row append at `:1291-1307`) or `refire()`
(`:1605-1618`) appends a start row to a run that is still open, and every piece of the open
incarnation reads `dead` or `not started` (`registry.launch_failed()`, `:921`, without its
age condition), append that incarnation's `launch_failed` finish row through
`append_finish`, under the same lock hold as the new start row. `retry` reaches the same
code through the walk.

## Acceptance

- A CPU-only unit test: an open run with one dead train piece, then a relaunch, leaves a
  `launch_failed` finish row with a `card_record` between the two start rows.
- `run.py selfcheck` green; all CPU test modules pass. No `jobs/versions.yaml` row (no stage's
  code set holds `jobs/` or `run.py`).

## Comments

- 2026-10-02, wave 2 (ticket-run): DONE with no fix round. Branch ticket/2026-10-02-wave2/T03 (f37f098..29c8de4), merged at 488c590 (README tests/ line and the test docstring merged as the union with tickets 01 and 02). Selfcheck green, all eight test modules pass.
  - Minor for the final review: F1, a ragged line in the `refire()` docstring.
  - Shelved: a CPU stage (`build`, `eval`, `score`) whose process died and is walked again still gets no finish row for the dead incarnation. The ticket names `launch()` and `refire()` only, and a CPU stage carries no card record, which is what this feature records.
  - Left as it was (implementer's concern): `registry.free()` runs before the dead incarnation is closed, so while its start row is younger than `launch_timeout_s` its card still counts as reserved and the relaunch lands on another card. Changing that changes placement, which is gyb's call.
