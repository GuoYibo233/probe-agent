"""The record one task run leaves: six row kinds in one flush-per-row jsonl file, with the claim, release, read and message-rebuilding functions its callers share."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import polars as pl

from data import read_frame, record_id as _record_id

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

SCHEMA: dict[str, pl.DataType] = {
    "type": pl.Utf8,
    "step": pl.Int32,
    "ts": pl.Float64,
    "version": pl.Int32,
    "record_id": pl.Utf8,
    "stage": pl.Utf8,
    "env": pl.Utf8,
    "task_id": pl.Utf8,
    "seed": pl.Int64,
    "env_seed": pl.Int64,
    "split": pl.Utf8,
    "arm": pl.Utf8,
    "instructions": pl.Utf8,
    "task_text": pl.Utf8,
    "agent_model": pl.Utf8,
    "generation": pl.Utf8,
    "inject": pl.Utf8,
    "commit": pl.Utf8,
    "run_key": pl.Utf8,
    "owner_session": pl.Utf8,
    "reasoning": pl.Utf8,
    "content": pl.Utf8,
    "usage": pl.Struct({"in": pl.Int64, "out": pl.Int64}),
    "wall_s": pl.Float64,
    "finish_reason": pl.Utf8,
    "stop_reason": pl.Utf8,
    "prefix_tok": pl.Int32,
    "prefix_sha": pl.Utf8,
    "gen_ids": pl.List(pl.Int32),
    "n_inject": pl.Int32,
    "discard": pl.Struct({"chars": pl.Int64, "tokens": pl.Int64, "events": pl.Int32}),
    "fire_index": pl.Int32,
    "cut": pl.Int32,
    "n_checked": pl.Int32,
    "conf": pl.Float64,
    "pred_label": pl.Utf8,
    "gen_call": pl.Utf8,
    "exec_code": pl.Utf8,
    "arg_modes": pl.List(pl.Utf8),
    "exec_out": pl.Utf8,
    "exec_ok": pl.Boolean,
    "error_kind": pl.Utf8,
    "note": pl.Utf8,
    "format": pl.Utf8,
    "head_tok": pl.Int32,
    "head_chars": pl.Int32,
    "note_tok": pl.Int32,
    "discarded_chars": pl.Int32,
    "overflow_ids": pl.List(pl.Int32),
    "spec_s": pl.Float64,
    "overflow_tok": pl.Int32,
    "new_tok": pl.Int32,
    "match_len": pl.Int32,
    "identical": pl.Boolean,
    "action": pl.Utf8,
    "result": pl.Utf8,
    "steps": pl.Int32,
    "completed": pl.Boolean,
    "abort": pl.Utf8,
    "judge": pl.Utf8,
    "success": pl.Boolean,
    "tokens_in": pl.Int64,
    "tokens_out": pl.Int64,
    "finished_at": pl.Float64,
}

DEFAULTS: dict[str, Any] = {name: None for name in SCHEMA}
DEFAULTS["n_inject"] = 0

REQUIRED: frozenset[str] = frozenset({
    "type", "ts", "version", "record_id", "stage", "env",
    "task_id", "seed", "split", "task_text", "agent_model", "owner_session",
})

# Stamped by Writer.row itself; a caller that also passes one of these raises.
_STAMPED = frozenset({"type", "ts", "version", "record_id"})


def record_path(dir: Path, task_id: str, seed: int) -> Path:
    """Build the path of one task run's record file under the run directory."""
    return Path(dir) / "records" / f"{_record_id(task_id, seed)}.jsonl"


def open_record(dir: Path, task_id: str, seed: int) -> "Writer | None":
    """Exclusively claim a task's record file and return its Writer, or None when another piece already holds it."""
    path = record_path(dir, task_id, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return None
    return Writer(path, fd, task_id, seed)


class Writer:
    """Writes one record file row by row, flushing after every row so a killed writer keeps everything it wrote."""

    def __init__(self, path: Path, fd: int, task_id: str, seed: int) -> None:
        self._path = path
        self._file = os.fdopen(fd, "w")
        self._task_id = task_id
        self._seed = seed
        self._rows: list[dict[str, Any]] = []

    def row(self, kind: str, **fields: Any) -> None:
        """Write one JSON row, stamping type/ts (and, on a meta row, version/record_id)."""
        stamped = _STAMPED & set(fields)
        if stamped:
            raise ValueError(
                f"row {kind!r}: caller may not set stamped column(s) {sorted(stamped)}"
            )
        unknown = set(fields) - set(SCHEMA)
        if unknown:
            raise ValueError(f"row {kind!r}: undeclared field(s) {sorted(unknown)}")
        row: dict[str, Any] = {"type": kind, "ts": time.clock_gettime(time.CLOCK_REALTIME)}
        if kind == "meta":
            row["version"] = VERSION
            row["record_id"] = _record_id(self._task_id, self._seed)
        row.update(fields)
        self._file.write(json.dumps(row) + "\n")
        self._file.flush()
        self._rows.append(row)

    def frame(self) -> pl.DataFrame:
        """Return the rows written so far, held in memory, in the same column order and dtypes read() returns."""
        return _rows_to_frame(self._rows)

    def close(self) -> None:
        """Close the underlying file."""
        self._file.close()


def _last_line(path: Path) -> str | None:
    """Read the tail of the file and return its last non-empty line, without reading the whole file."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return None
        block = 8192
        data = b""
        pos = size
        while True:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
            if b"\n" in data.rstrip(b"\n") or pos == 0:
                break
    lines = data.rstrip(b"\n").split(b"\n")
    if not lines or not lines[-1]:
        return None
    return lines[-1].decode("utf-8")


def _first_line(path: Path) -> str | None:
    """Return the file's first line."""
    with open(path, "r") as f:
        line = f.readline()
    return line.rstrip("\n") if line else None


def is_done(path: Path) -> bool:
    """True when the file's last line parses and its type is final, whatever abort says."""
    line = _last_line(path)
    if line is None:
        return False
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return False
    return row.get("type") == "final"


def owner(path: Path) -> str | None:
    """The meta row's owner_session, or None when the first line does not parse as a meta row."""
    line = _first_line(path)
    if line is None:
        return None
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if row.get("type") != "meta":
        return None
    return row.get("owner_session")


def done_pairs(dir: Path, pairs: list[tuple[str, int]]) -> set[tuple[str, int]]:
    """The subset of pairs whose record file is_done, reading one line per file."""
    out: set[tuple[str, int]] = set()
    for task_id, seed in pairs:
        path = record_path(dir, task_id, seed)
        if path.exists() and is_done(path):
            out.add((task_id, seed))
    return out


def release(dir: Path, live_sessions: set[str], unowned_age_s: float) -> list[Path]:
    """Delete and return every unfinished record file whose owner is not live, and every unowned record file older than the margin."""
    records_dir = Path(dir) / "records"
    if not records_dir.is_dir():
        return []
    released: list[Path] = []
    now = time.time()
    for path in sorted(records_dir.glob("*.jsonl")):
        if is_done(path):
            continue
        who = owner(path)
        if who is not None:
            if who not in live_sessions:
                path.unlink()
                released.append(path)
        elif now - path.stat().st_mtime > unowned_age_s:
            path.unlink()
            released.append(path)
    return released


def read(path: Path) -> pl.DataFrame:
    """Read one record file, filling record_id on every row from that file's meta row."""
    df = read_frame(path, schema=SCHEMA, defaults=DEFAULTS, required=REQUIRED, version=VERSION)
    meta_id = df.filter(pl.col("type") == "meta")["record_id"][0]
    return df.with_columns(pl.lit(meta_id).alias("record_id"))


def read_dir(dir: Path, pairs: list[tuple[str, int]]) -> pl.DataFrame:
    """Read exactly the pairs' record files, skipping every file whose is_done is false, and concatenate."""
    frames = []
    for task_id, seed in pairs:
        path = record_path(dir, task_id, seed)
        if path.exists() and is_done(path):
            frames.append(read(path))
    if not frames:
        return pl.DataFrame(schema=SCHEMA)
    return pl.concat(frames)


def to_messages(
    df: pl.DataFrame,
    upto_step: int,
    task_text: str,
    instructions: str,
    no_code: str,
    extra_developer: str | None,
) -> list[dict]:
    """Rebuild the conversation exactly as the model saw it, for the steps before upto_step (exclusive)."""
    developer = instructions if extra_developer is None else f"{instructions}\n\n{extra_developer}"
    messages: list[dict] = [
        {"role": "developer", "content": developer},
        {"role": "user", "content": task_text},
    ]
    gen_by_step = {row["step"]: row for row in df.filter(pl.col("type") == "gen").iter_rows(named=True)}
    env_by_step = {row["step"]: row for row in df.filter(pl.col("type") == "env").iter_rows(named=True)}
    for step in range(upto_step):
        gen_row = gen_by_step[step]
        env_row = env_by_step[step]
        messages.append({"role": "assistant", "content": gen_row["content"]})
        content = env_row["result"] if env_row["action"] is not None else no_code
        messages.append({"role": "user", "content": content})
    return messages


def _rows_to_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Build a DataFrame from in-memory row dicts, in the same schema and fill rule as read()."""
    if not rows:
        return pl.DataFrame(schema=SCHEMA)
    df = pl.DataFrame(rows, infer_schema_length=None)
    for name, dtype in SCHEMA.items():
        if name in df.columns:
            df = df.with_columns(pl.col(name).cast(dtype, strict=True))
        else:
            df = df.with_columns(pl.lit(DEFAULTS[name], dtype=dtype).alias(name))
    df = df.select(list(SCHEMA))
    meta_rows = df.filter(pl.col("type") == "meta")
    if meta_rows.height:
        df = df.with_columns(pl.lit(meta_rows["record_id"][0]).alias("record_id"))
    return df
