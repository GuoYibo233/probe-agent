"""The row build writes per cut of a trajectory: the record and cut it came from, the text the probe sees, and all three probe methods' targets."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from data import read_frame, write_frame

VERSION = 1

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
