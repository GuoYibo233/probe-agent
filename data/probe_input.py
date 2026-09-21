"""The probe's cut enumeration and prompt assembly, shared by the offline builder and the live injector so neither builds its own probe text."""
from __future__ import annotations

import re

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
SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")


def cuts(thinking: str, min_think: int, max_cuts: int) -> list[int]:
    """Enumerate offline cut offsets into a finished thinking text, at each sentence end plus a terminal cut, thinned to at most max_cuts."""
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


# TODO(gyb, 2026-09-22): the two cut rules end the probe's text at different characters, and the
# owner's decision is to unify them on the training side's form: the text ends WITH the
# whitespace or newline that follows the sentence.
#   - `cuts` (training) takes m.end(): the text ends "...the playlist. " or "...the playlist.\n".
#   - `cuts_live` (inject) takes m.start(): the text ends "...the playlist.".
# The classifier reads the hidden state of the last token, so the live probe sees a last token
# it never saw in training. The two docstrings are also swapped against the code: m.end() is the
# start of the next sentence, m.start() is the end of this one.
# Fix: `cuts_live` takes m.end() as `cuts` does. Two things go with it. (1) While the thinking
# streams, a whitespace run may still be growing ("." then "\n" then "\n"), and the training text
# holds the whole run, so a live cut is taken only once a non-whitespace character has followed
# the run. (2) data/build_training_dataset.py strips the thinking before it cuts and
# agent/step_with_probe.py does not; the live side strips the leading whitespace the same way, so
# the two texts are equal character for character. `cuts` itself stays as it is, so no build or
# train run goes stale: bump VERSION with "stale": ("inject",). Contracts 1.7 states m.start()
# for the live rule and becomes stale with this change (an agent does not edit the contracts).
def cuts_live(thinking_so_far: str, min_think: int) -> list[int]:
    """Enumerate streaming cut offsets into a growing thinking prefix, at each sentence start, with no terminal cut and no thinning."""
    return [
        m.start()
        for m in SENT_RE.finditer(thinking_so_far)
        if len(thinking_so_far[: m.start()].strip()) >= min_think // 2
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
# texts of the same length. build.hist_rounds is in the build key and in the inject key
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
