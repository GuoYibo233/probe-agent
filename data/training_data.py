"""The row build writes per cut of a trajectory: the record and cut it came from, the text the probe sees, and all three probe methods' targets."""
from __future__ import annotations

# TODO(gyb, 2026-09-18): rename the three format files together once every wave has merged, not
# before (in-flight ticket branches import them): data/training_data.py ->
# data/training_data_format.py, data/trajectory_record.py -> data/trajectory_record_format.py,
# data/probe_output.py -> data/probe_output_format.py. The present names read as programs; each
# file holds a table's columns plus its write() and read(). In the same pass rewrite this file's
# first docstring line so it says what the file is for (the table the build stage hands to the
# train stage), and carry the names and the sentence into README.md, experimental_settings/schema.py's
# stage table, the tree document, the contracts, the tickets and the folder plans; search every
# code directory, the last rename missed schema.py.

from pathlib import Path
from typing import Any

import polars as pl

from data import read_frame, write_frame

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
    "example_id": pl.Utf8,
    "event_id": pl.Utf8,
    "record_id": pl.Utf8,
    "task_id": pl.Utf8,
    "seed": pl.Int64,
    "step": pl.Int32,
    "cut": pl.Int32,
    "cut_index": pl.Int32,
    "n_cuts": pl.Int32,
    "depth": pl.Float32,
    "text": pl.Utf8,
    "tool": pl.Utf8,
    "call": pl.Utf8,
    "args": pl.List(pl.Struct({"key": pl.Utf8, "value": pl.Utf8})),
    "weight": pl.Float32,
    "split": pl.Utf8,
    "env": pl.Utf8,
    "agent_model": pl.Utf8,
    "version": pl.Int32,
}

DEFAULTS: dict[str, Any] = {name: None for name in SCHEMA}

REQUIRED: frozenset[str] = frozenset({
    "example_id", "event_id", "record_id", "task_id", "seed", "step",
    "cut", "cut_index", "n_cuts", "depth", "text", "tool", "call", "weight", "split", "version",
})


def write(path: Path, df: pl.DataFrame) -> None:
    """Stamp version, fill any column of SCHEMA the frame does not carry, select the declared order, and write."""
    df = df.with_columns(pl.lit(VERSION, dtype=pl.Int32).alias("version"))
    for name, dtype in SCHEMA.items():
        if name not in df.columns:
            df = df.with_columns(pl.lit(DEFAULTS[name], dtype=dtype).alias(name))
    write_frame(path, df.select(list(SCHEMA)), schema=SCHEMA)


def read(path: Path) -> pl.DataFrame:
    """Read an example file against this format's schema."""
    return read_frame(path, schema=SCHEMA, defaults=DEFAULTS, required=REQUIRED, version=VERSION)
