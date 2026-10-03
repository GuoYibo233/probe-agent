"""The probe's cut enumeration and prompt assembly, shared by the offline builder and the live injector so neither builds its own probe text."""
from __future__ import annotations

import re

SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")
_NON_SPACE_RE = re.compile(r"\S")


def cuts(thinking: str, min_think: int, max_cuts: int) -> list[int]:
    """Enumerate offline cut offsets into a finished thinking text, at the end of the whitespace run (or newline) that follows each sentence plus a terminal cut, thinned to at most max_cuts."""
    if max_cuts < 2:
        raise ValueError(f"max_cuts must be at least 2, got {max_cuts}")
    pts = sorted({m.end() for m in SENT_RE.finditer(thinking)} | {len(thinking)})
    pts = [p for p in pts if len(thinking[:p].strip()) >= min_think // 2]
    if not pts:
        pts = [len(thinking)]
    if len(pts) > max_cuts:
        keep = {len(pts) - 1}
        step = (len(pts) - 1) / (max_cuts - 1)
        keep.update(round(k * step) for k in range(max_cuts - 1))
        pts = [pts[j] for j in sorted(keep)]
    return pts


# TODO(gyb, 2026-09-22): the contracts still state the old live rule (an `m.start()` offset) in
# two places, 1.7 and Part 9(a) decision 31 ("There are two cut rules, not one"); both are the
# owner's to update.
def cuts_live(thinking_so_far: str, min_think: int) -> list[int]:
    """Enumerate streaming cut offsets into a growing thinking prefix, by the rule `cuts` holds: each offset is the end of the whitespace run (or newline) that follows a sentence, so the probe's text ends with that whitespace as it does in training. A cut is taken once a non-whitespace character has followed it: whitespace at the end of the stream may still be growing, and the build strips the whitespace that ends the thinking, so it holds no cut there. No terminal cut and no thinning. The caller hands over the thinking with its leading whitespace stripped, the form the build cuts."""
    n_settled = len(thinking_so_far.rstrip())
    # `cuts` keeps an offset p when len(thinking[:p].strip()) >= min_think // 2. The stripped
    # length of a prefix reaches k once the prefix holds the first non-whitespace character at
    # or after index lead + k - 1, so that one index settles the filter for every offset, and
    # this function, called once per streamed delta, reads the text once per call.
    k = min_think // 2
    first_kept = 0
    if k > 0:
        lead = len(thinking_so_far) - len(thinking_so_far.lstrip())
        reach = _NON_SPACE_RE.search(thinking_so_far, lead + k - 1)
        if reach is None:
            return []
        first_kept = reach.start() + 1
    return [
        m.end()
        for m in SENT_RE.finditer(thinking_so_far)
        if first_kept <= m.end() < n_settled
    ]


def _clip(s: str, cap: int) -> str:
    """Clip a history observation to at most cap characters, keeping the head and tail."""
    if cap < 100:
        raise ValueError(f"probe_result_cap must be at least 100, got {cap}")
    s = str(s)
    return s if len(s) <= cap else s[: cap - 60] + " ...[cut]... " + s[-40:]


# The probe reads the task, the last hist_rounds tool rounds and the thinking so far (the owner's
# decision of 2026-09-22 and of 2026-09-30: a setting gives hist_rounds a value that covers a whole
# record, and build.probe_prefix_max_chars bounds the text before the thinking). Each history line
# is the round's whole code block plus its result clipped to probe_result_cap. Under a budget, the
# oldest of the kept rounds are cut one by one until the task line, the headers and the remaining
# round lines fit, so the probe always sees the task, the newest rounds and the thinking, and the
# build and the live side produce the same text from the same rule (the budget is in characters so
# the build needs no tokenizer). The thinking is not counted, so the rounds a step keeps depend on
# the task and the history alone: every cut of one step, offline and live, starts with the same
# lines, which the trainer's packing relies on (one shared prefix per event; a per-cut budget
# gave the cuts of one step different first rounds and a 1.3-million-token block, 2026-10-03).
# A text whose rounds are all cut carries a history line saying so, so the probe can tell it from
# a first step's "(start)".
EMPTY_HISTORY = "(start)"
CUT_HISTORY = "(earlier rounds cut)"


def _lines(
    task: str,
    history: list[tuple[str, str]],
    thinking_prefix: str,
    hist_rounds: int,
    probe_result_cap: int,
    max_chars: int | None,
) -> tuple[list[str], int]:
    """The probe text's lines and the count of kept rounds the budget cut from the front."""
    if hist_rounds < 0:
        raise ValueError(f"hist_rounds must be at least 0, got {hist_rounds}")
    if max_chars is not None and max_chars < 1:
        raise ValueError(f"max_chars must be at least 1, got {max_chars}")
    # history[-0:] is the whole list, so hist_rounds = 0 (no rounds) is spelled out
    kept = history[-hist_rounds:] if hist_rounds > 0 else []
    head = [f"Task: {task}", "[HISTORY]"]
    tail = ["[THINKING]", thinking_prefix]
    rounds = [f"{action} -> {_clip(observation, probe_result_cap)}" for action, observation in kept]
    n_cut = 0
    if max_chars is not None and rounds:
        # the budget covers the lines before the thinking: the joined text holds one newline
        # between consecutive lines, so each of these lines costs its length plus one
        total = sum(len(s) + 1 for s in head + rounds)
        while rounds and total > max_chars:
            total -= len(rounds[0]) + 1
            rounds = rounds[1:]
            n_cut += 1
    if not rounds:
        rounds = [CUT_HISTORY if n_cut > 0 else EMPTY_HISTORY]
    return head + rounds + tail, n_cut


def assemble(
    task: str,
    history: list[tuple[str, str]],
    thinking_prefix: str,
    hist_rounds: int,
    probe_result_cap: int,
    max_chars: int | None = None,
) -> str:
    """Build the probe's input text from the task, the last hist_rounds tool rounds, and the thinking so far; under max_chars (build.probe_prefix_max_chars) the oldest kept rounds are cut until the lines before the thinking fit."""
    lines, _n_cut = _lines(task, history, thinking_prefix, hist_rounds, probe_result_cap, max_chars)
    return "\n".join(lines)


def rounds_cut(
    task: str,
    history: list[tuple[str, str]],
    thinking_prefix: str,
    hist_rounds: int,
    probe_result_cap: int,
    max_chars: int | None,
) -> int:
    """How many of the kept rounds `assemble` cuts from the front under max_chars, the same for every thinking prefix of the step; 0 without a budget."""
    _lines_out, n_cut = _lines(task, history, thinking_prefix, hist_rounds, probe_result_cap, max_chars)
    return n_cut
