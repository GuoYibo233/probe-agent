"""The table of the five ways an early speculation result is written into the token stream."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# VERSION rule: read this before you edit this file (errata "3.3 / 8.6", gyb 2026-09-18).
# Bump VERSION only when some existing setting would now produce a different output of a stage
# that lists this file in the stage table of experimental_settings/schema.py. A new feature
# behind a new setting field whose default reproduces the old behaviour, a message, a comment
# or a report layout does not bump.
# Every bump adds one VERSION_HISTORY entry: {<new version>: {"why": "<one sentence>",
# "stale": (<stage names>)}}. "stale" names the stages (sample, build, train, eval, inject,
# score) whose existing outputs can no longer be used; leave "stale" out and every stage is
# stale. The key folds the highest version that made a stage stale, so a bump that leaves a
# stage usable keeps that stage's run directory. When unsure, list the stage.
VERSION = 1
VERSION_HISTORY = {}

EXPLAIN = ("The system already ran {call} for you and got:\n{result}\n"
           "You can use this result without calling it.")
MARKER = "[Prefetch] {call} = {result}"
SYSTEM_EXTRA = (
    "\n\nSometimes a prefetched result appears while you reason, either as a line starting with "
    "[Prefetch] or as a message from a sender named prefetch. It means the system already ran "
    "that call for you; use the result without calling it again.")


@dataclass
class Format:
    """One entry of FORMATS: where the body goes, whether it needs control tokens, its extra system text, and its renderer."""

    placement: str                                              # "p1" or "p2"
    needs_special: bool
    system_text: str | None
    render: Callable[[str, str, bool, str | None], str]


def _render_note(call: str, exec_out: str, exec_ok: bool, error_kind: str | None) -> str:
    return "[SYSTEM NOTE: prefetched {call} = {result}]\n".format(call=call, result=exec_out)


def _render_p1_e1(call: str, exec_out: str, exec_ok: bool, error_kind: str | None) -> str:
    return ("[Prefetch: " + EXPLAIN + "]\n").format(call=call, result=exec_out)


def _render_p1_e2(call: str, exec_out: str, exec_ok: bool, error_kind: str | None) -> str:
    return (MARKER + "\n").format(call=call, result=exec_out)


def _render_p2_e1(call: str, exec_out: str, exec_ok: bool, error_kind: str | None) -> str:
    return EXPLAIN.format(call=call, result=exec_out)


def _render_p2_e2(call: str, exec_out: str, exec_ok: bool, error_kind: str | None) -> str:
    return "{call} = {result}".format(call=call, result=exec_out)


FORMATS = {
    "note": Format("p1", False, None, _render_note),
    "p1_e1": Format("p1", False, None, _render_p1_e1),
    "p1_e2": Format("p1", False, SYSTEM_EXTRA, _render_p1_e2),
    "p2_e1": Format("p2", True, None, _render_p2_e1),
    "p2_e2": Format("p2", True, SYSTEM_EXTRA, _render_p2_e2),
}
