"""The row train writes per example after training: the true tool, the classifier's score and logits, or the generator's text, for eval to read with no GPU."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from data import read_frame, write_frame

# The on-disk format's compatibility number, stamped into every row and checked by read_frame
# (a file recorded above it is refused): it moves when the row shape changes in a way an old
# reader cannot take. It is not the code era; that is jobs/versions.yaml.
FORMAT_VERSION = 1

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
    df = df.with_columns(pl.lit(FORMAT_VERSION, dtype=pl.Int32).alias("version"))
    for name, dtype in SCHEMA.items():
        if name not in df.columns:
            df = df.with_columns(pl.lit(DEFAULTS[name], dtype=dtype).alias(name))
    write_frame(path, df.select(list(SCHEMA)), schema=SCHEMA)


def read(path: Path) -> pl.DataFrame:
    """Read a prediction file against this format's schema."""
    return read_frame(path, schema=SCHEMA, defaults=DEFAULTS, required=REQUIRED, version=FORMAT_VERSION)
