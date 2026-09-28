"""Conventions the three on-disk formats share: the id chain and the schema-driven frame reader/writer."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import polars as pl


def record_id(task_id: str, seed: int) -> str:
    """Build the id of one task run from its task id and trajectory seed."""
    return f"{task_id}__s{seed}"


def event_id(record_id: str, step: int) -> str:
    """Build the id of one step of a record."""
    return f"{record_id}|s{step}"


def example_id(event_id: str, cut_index: int) -> str:
    """Build the id of one cut of an event."""
    return f"{event_id}|c{cut_index}"


def _file_schema(path: Path) -> dict[str, pl.DataType]:
    """Read a file's own schema without reading its data."""
    if path.suffix == ".parquet":
        return dict(pl.read_parquet_schema(path))
    return dict(pl.scan_ndjson(path, infer_schema_length=None).collect_schema())


def _recorded_version(path: Path, present: dict[str, pl.DataType]) -> int:
    """The maximum non-null value of the declared version column, 0 when that column is absent."""
    if "version" not in present:
        return 0
    if path.suffix == ".parquet":
        column = pl.read_parquet(path, columns=["version"])["version"]
    else:
        column = pl.read_ndjson(path, schema={"version": present["version"]})["version"]
    column = column.drop_nulls()
    if column.len() == 0:
        return 0
    return int(column.max())


def read_frame(
    path: Path,
    *,
    schema: dict[str, pl.DataType],
    defaults: dict[str, Any],
    required: frozenset[str],
    version: int,
) -> pl.DataFrame:
    """Read a jsonl or parquet file against a declared schema.

    Raises, naming the path, when the file is missing or empty; raises, naming
    the column, the path and the file's recorded version, when a required
    column is absent from the file; raises when the file's recorded version is
    above `version`; raises, naming the path, on a declared column present with
    a value the declared dtype cannot hold. Every other declared column absent
    from the file is filled from `defaults`, and the result carries the
    declared columns in declared order.
    """
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f"{path}: file is missing or empty")

    file_schema = _file_schema(path)
    present = {
        name: dtype
        for name, dtype in schema.items()
        if name in file_schema and file_schema[name] != pl.Null
    }

    missing_required = sorted(name for name in required if name not in present)
    recorded = _recorded_version(path, present)
    if missing_required:
        raise ValueError(
            f"{path}: required column(s) {missing_required} absent from the file "
            f"(recorded version {recorded})"
        )
    if recorded > version:
        raise ValueError(
            f"{path}: recorded version {recorded} is newer than the reading code's version {version}"
        )

    try:
        if path.suffix == ".parquet":
            df = pl.read_parquet(path, columns=list(present)).cast(present, strict=True)
        else:
            df = pl.read_ndjson(path, schema=present)
    except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError) as exc:
        raise ValueError(f"{path}: column holds a value its declared type cannot hold: {exc}") from exc

    for name, dtype in schema.items():
        if name not in present:
            df = df.with_columns(pl.lit(defaults[name], dtype=dtype).alias(name))
    return df.select(list(schema))


def write_frame(path: Path, df: pl.DataFrame, *, schema: dict[str, pl.DataType]) -> None:
    """Write a DataFrame to parquet through a same-directory temporary file, then atomically replace the target.

    Raises, naming the suffix, when `path` is not `.parquet`: a task record's
    jsonl is written row by row by `Writer.row` under the flush-per-row rule,
    so no jsonl bulk writer has a caller.
    """
    path = Path(path)
    if path.suffix != ".parquet":
        raise ValueError(f"{path}: write_frame accepts .parquet only, got suffix {path.suffix!r}")
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    df.write_parquet(tmp)
    os.replace(tmp, path)
