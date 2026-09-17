"""The probe's cut enumeration and prompt assembly, shared by the offline builder and the live injector so neither builds its own probe text."""
from __future__ import annotations

import re

VERSION = 1
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
