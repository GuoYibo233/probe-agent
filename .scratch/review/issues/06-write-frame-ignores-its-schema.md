# 06 write_frame never uses the schema it is handed, so the parquet on disk does not carry the declared types

Status: needs-triage
Severity: minor
File: data/__init__.py:102-114
Contract: Part 1 ("`def write_frame(path, df, *, schema: dict) -> None`"), 1.3 (the prediction column types)
Errata: not recorded. Errata "Part 1 (`write_frame`)" settles the `.parquet`-only refusal; errata "Parts 1.2 and 1.3 (the writer's signature)" gives `write(path, df)` the job of stamping `version` and selecting the declared columns in order, and neither says the dtypes are applied.

## Finding

`write_frame` takes `schema` and never reads it:

```python
def write_frame(path: Path, df: pl.DataFrame, *, schema: dict[str, pl.DataType]) -> None:
    path = Path(path)
    if path.suffix != ".parquet":
        raise ValueError(f"{path}: write_frame accepts .parquet only, got suffix {path.suffix!r}")
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    df.write_parquet(tmp)
    os.replace(tmp, path)
```

Its two callers, `data/training_data.py:64-70` and `data/probe_output.py:48-54`,
fill the columns the frame lacks with `pl.lit(DEFAULTS[name], dtype=dtype)` and
select the declared order, but neither casts a column the frame already carries.
So the declared types are enforced on the way in through `read_frame`'s
`.cast(present, strict=True)` and nowhere on the way out.

The deviation is on disk in the section-4 `--debug` runs (read with
`pl.read_parquet_schema` against each format's `SCHEMA`):

```
debug/train/0f3e343f0eca/predictions.parquet   score: Float64 (declared Float32), logits: List(Float64) (declared List(Float32))
debug/train/22a0980de899/predictions.parquet   score: Float64 (declared Float32), logits: List(Float64) (declared List(Float32))
debug/train/5b398c217e13/predictions.parquet   gen_tokens: Int64 (declared Int32)
debug/build/b565f5ab1b94/examples.parquet      none (the builder casts the frame itself before calling write)
```

## Failure scenario

Two concrete ones today, both on `predictions.parquet`:

1. `logits` is written as `List(Float64)`. Contract 1.4 budgets the column at
   "about 150 classes and float32 ... roughly 600 bytes a row"; the file holds
   twice that, on every prediction row of every split of every classifier train
   run, which is the largest column of the largest file `train` writes.
2. Anything that opens the file without going through `probe_output.read` — a
   person with polars, or a future reader — sees `score` as `Float64` and
   `gen_tokens` as `Int64`, so the format's own table (1.3) is not what the file
   says. The types only become true after a read that casts them.

A third is latent: `write` keeps a column the caller supplied as all-`None`,
which polars infers as `Null` dtype; `read_frame` counts a `Null` column as
absent (errata "Part 1 (`read_frame` and a null column)"), so such a column in
`REQUIRED` makes `read` raise "required column absent" on a file `write` had
just accepted.

## Proposed fix

Use the parameter the contract already passes. In `data/__init__.py`,
`write_frame` casts the frame to `schema` (`df.select(list(schema)).cast(schema,
strict=True)`) before it writes the temporary file, so the declared column list,
the declared order and the declared types are one rule applied in one place, and
a frame that cannot hold its declared type fails at the writer instead of at the
next reader. The two `write` functions then keep only the `version` stamp and
the `DEFAULTS` fill.
