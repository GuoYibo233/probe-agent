"""The row train writes per example after training: the true tool, the classifier's score and logits, or the generator's text, for eval to read with no GPU."""
from __future__ import annotations

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
    "task_id": pl.Utf8,
    "depth": pl.Float32,
    "split": pl.Utf8,
    "tool": pl.Utf8,
    "method": pl.Utf8,
    "target": pl.Utf8,
    "score": pl.Float32,
    "label_pred": pl.Utf8,
    "logits": pl.List(pl.Float32),
    "text_pred": pl.Utf8,
    "gen_tokens": pl.Int32,
    "version": pl.Int32,
}

DEFAULTS: dict[str, Any] = {name: None for name in SCHEMA}

REQUIRED: frozenset[str] = frozenset({
    "example_id", "event_id", "task_id", "depth", "split", "tool", "method", "target", "version",
})


def write(path: Path, df: pl.DataFrame) -> None:
    """Stamp version, fill any column of SCHEMA the frame does not carry, select the declared order, and write."""
    df = df.with_columns(pl.lit(VERSION, dtype=pl.Int32).alias("version"))
    for name, dtype in SCHEMA.items():
        if name not in df.columns:
            df = df.with_columns(pl.lit(DEFAULTS[name], dtype=dtype).alias(name))
    write_frame(path, df.select(list(SCHEMA)), schema=SCHEMA)


def read(path: Path) -> pl.DataFrame:
    """Read a prediction file against this format's schema."""
    return read_frame(path, schema=SCHEMA, defaults=DEFAULTS, required=REQUIRED, version=VERSION)
