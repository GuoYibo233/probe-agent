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


# TODO(gyb, 2026-09-22): owner's decision: the probe reads the task and EVERY earlier round of the
# record in full, and train.max_len is raised to hold it. Today it reads the last
# build.hist_rounds = 3 rounds only. Each history line stays what it is now, the whole code block
# of a round plus its result clipped to build.probe_result_cap.
# What to do: (1) the settings give build.hist_rounds a value that covers a whole record
# (sample.max_steps = 30 today); (2) measure the token length of the longest text per event on a
# full-scale build and set train.max_len from that measurement. The --debug build b565f5ab1b94
# (3 rounds of history, 6 steps per task) already reports p50 3347, p90 10150 and max 26752
# characters, and the trainer drops a whole event whose longest text passes train.max_len
# (8192 tokens today), so raising hist_rounds alone would drop the late steps of long tasks.
# Two limits on max_len: the probe backbone's context length, and card memory, since a training
# block holds 2 * max_len tokens (train/methods/ctool.py) and the live probe service scores
# texts of the same length. The measured max_len also has to make truncation rare on the live
# side: training drops an overlong event whole, while the live score truncates an overlong text
# from the left (models/probe_models/qwen.py), which removes the `Task:` line and the oldest
# history, a shape of text the probe never saw in training.
# build.hist_rounds is in the build key and in the inject key
# (PROBE_TEXT_FIELDS) and train.max_len is in the train key, so build, train, eval and inject
# all re-key; sample stays.
def assemble(
    task: str,
    history: list[tuple[str, str]],
    thinking_prefix: str,
    hist_rounds: int,
    probe_result_cap: int,
) -> str:
    """Build the probe's input text from the task, the last hist_rounds tool rounds, and the thinking so far."""
    lines = [f"Task: {task}", "[HISTORY]"]
    lines += [
        f"{action} -> {_clip(observation, probe_result_cap)}"
        for action, observation in history[-hist_rounds:]
    ] or ["(start)"]
    lines += ["[THINKING]", thinking_prefix]
    return "\n".join(lines)
