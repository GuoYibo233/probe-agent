"""The program that turns a sample run's task records into example rows for the three probe methods, split into train/val/test, with the build gates and report.md."""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

import polars as pl
import yaml

from data import event_id, example_id, record_id
from data import probe_input, trajectory_record, training_data
from data.environments import open_env, requested_pairs
from experimental_settings import schema
from jobs import registry

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


def main(run_dir: Path) -> None:
    """Build `examples.parquet` for one build run directory (contracts 2.5, 1.2, 1.7, 2.3, 1.5)."""
    run_dir = Path(run_dir)
    cfg = schema.load_frozen(run_dir)
    hb = registry.beat(run_dir, 0)

    env = open_env(cfg.data.env)

    triples = requested_pairs(env, cfg.sample.split, cfg.sample.tasks, cfg.sample.n_tasks, cfg.sample.seeds)
    pairs = [(task_id, seed) for _split, task_id, seed in triples]

    sample_dir = schema.run_dir_of("sample", cfg._upstream["sample"], debug=cfg._debug)

    # 2.5's completeness gate: every requested pair needs a done record.
    done = trajectory_record.done_pairs(sample_dir, pairs)
    missing = [pair for pair in pairs if pair not in done]
    if missing:
        raise ValueError(
            f"build: {len(missing)} requested (task_id, seed) pair(s) have no done record "
            f"in {sample_dir}: {missing}"
        )

    hb.emit(0, len(pairs), "row")

    # Resolve the split files (their paths, for consumed.json) and each split's task ids
    # (through env.tasks, which is what jobs/launch.py and run.py also call, 2.3).
    datasets_path = Path(__file__).resolve().parents[1] / "constants" / "path_datasets.yaml"
    with open(datasets_path) as f:
        datasets_doc = yaml.safe_load(f)
    splits_block = datasets_doc[cfg.data.env]["splits"]
    split_files: list[dict] = []
    split_ids: dict[str, set[str]] = {}
    for split_name, split_path in splits_block.items():
        ids = env.tasks(split_name)
        split_ids[split_name] = set(ids)
        p = Path(split_path)
        split_files.append({
            "path": str(p),
            "sha1": hashlib.sha1(p.read_bytes()).hexdigest(),
            "n_rows": len(ids),
        })

    # 2.5's split gates: a task id in two splits, or a record's task id in none of them.
    split_names = sorted(split_ids)
    for i in range(len(split_names)):
        for j in range(i + 1, len(split_names)):
            dup = split_ids[split_names[i]] & split_ids[split_names[j]]
            if dup:
                raise ValueError(
                    f"build: task id(s) {sorted(dup)} appear in both splits "
                    f"{split_names[i]!r} and {split_names[j]!r}"
                )
    official_union: set[str] = set()
    for ids in split_ids.values():
        official_union |= ids
    record_task_ids = {task_id for task_id, _seed in pairs}
    unknown = record_task_ids - official_union
    if unknown:
        raise ValueError(
            f"build: task id(s) {sorted(unknown)} of the records are in none of the "
            f"environment's official split lists"
        )

    # 2.5: build reads only the records of the pairs in its own key.
    df = trajectory_record.read_dir(sample_dir, pairs)
    # TODO(gyb, 2026-09-22): these beats are not progress. Every record is already read by the
    # line above, and this loop then counts 0 to len(pairs) in an instant, so `run.py ls` shows
    # the build at 100% before the per-record work below (the cuts and the probe text of every
    # step, which is where the time goes) has started. Fix: drop this loop and emit one beat per
    # record from inside the `for task_id, seed in pairs` loop below, after that record's rows
    # are appended (review ticket 43).
    for i in range(len(pairs)):
        hb.emit(i + 1, len(pairs), "row")

    # 2.5's abort gate.
    final_rows = df.filter(pl.col("type") == "final")
    n_final = final_rows.height
    n_aborted = int(final_rows["abort"].is_not_null().sum())
    abort_frac = (n_aborted / n_final) if n_final else 0.0
    if abort_frac > cfg.build.max_abort_frac:
        raise ValueError(
            f"build: {n_aborted}/{n_final} records aborted (share {abort_frac:.4f}) exceeds "
            f"build.max_abort_frac={cfg.build.max_abort_frac}"
        )

    weight_mode = cfg.build.weight_mode
    split_source = cfg.build.split_source
    split_ratio = cfg.build.split_ratio

    rows: list[dict] = []
    events_total = 0
    skip_no_action = 0
    skip_no_call = 0
    skip_short_think = 0
    cuts_per_event: list[int] = []
    refused_calls: list[dict] = []

    for task_id, seed in pairs:
        rid = record_id(task_id, seed)
        rec_df = df.filter(pl.col("record_id") == rid)
        meta_row = rec_df.filter(pl.col("type") == "meta").row(0, named=True)
        task_text = meta_row["task_text"]
        agent_model = meta_row["agent_model"]
        benchmark_split = meta_row["split"]

        # 2.5's split-column rule, one value per record.
        if split_source == "env":
            row_split = env.SPLIT_ROLE[benchmark_split]
        else:
            frac = int(hashlib.sha1(task_id.encode()).hexdigest()[:8], 16) / 2**32
            names = ("train", "val", "test")
            cum = 0.0
            row_split = names[-1]
            for name, share in zip(names, split_ratio):
                cum += share
                if frac < cum:
                    row_split = name
                    break

        gen_rows = {row["step"]: row for row in rec_df.filter(pl.col("type") == "gen").iter_rows(named=True)}
        env_rows = {row["step"]: row for row in rec_df.filter(pl.col("type") == "env").iter_rows(named=True)}

        history: list[tuple[str, str]] = []
        for step in sorted(gen_rows):
            gen_row = gen_rows[step]
            if step not in env_rows:
                raise ValueError(f"build: record {rid} step {step}: a gen row has no matching env row")
            env_row = env_rows[step]
            events_total += 1

            thinking = (gen_row["reasoning"] or "").strip()
            action = (env_row["action"] or "").strip()

            if action == "":
                skip_no_action += 1
                continue

            # TODO(gyb, 2026-09-22): OPEN DESIGN QUESTION, to be discussed with the others before
            # any code changes; not a bug to fix on sight. The label of a step is the FIRST
            # `apis.<app>.<api>(` call of its code block and every later call is ignored, while
            # the agent model often writes several calls in one block: in the --debug records on
            # disk (debug/sample and debug/inject, 36 record files, 200 steps with code) 81 steps
            # hold more than one call, up to 10 in one block. So the probe learns "the first call
            # of the block", and an inject run speculates that one call only, a small share of a
            # many-call step. The options named so far: limit the agent to one call per block in
            # the instructions (data/environments/appworld.py), label some other call of the
            # block, or keep the first-call rule knowingly. The --debug records stop at 6 steps
            # per task, so count again on a full-scale sample before deciding.
            parsed = env.split_args(action)
            if parsed is None:
                skip_no_call += 1
                history.append((action, env_row["result"]))
                continue

            if len(thinking) < cfg.build.min_think or thinking == "":
                skip_short_think += 1
                history.append((action, env_row["result"]))
                continue

            tool, call_args, _span = parsed

            # Owner ruling, 2026-09-18 (RULING-9): a call build_call refuses, or one that
            # fails the round-trip gate, is skipped and counted exactly like a non-parsing
            # action, instead of stopping the build. The affirmative condition is "the call
            # rebuilds and round-trips"; everything else takes the skip path.
            build_error: str | None = None
            try:
                call = env.build_call(tool, call_args)
            except ValueError as e:
                call = None
                build_error = str(e)

            round_trip = env.split_args(call) if build_error is None else None
            call_rebuilds_and_round_trips = (
                build_error is None and round_trip is not None
                and round_trip[0] == tool and round_trip[1] == call_args
            )

            if not call_rebuilds_and_round_trips:
                if build_error is not None:
                    reason = build_error
                else:
                    reason = (
                        f"call {call!r} does not round-trip through split_args/build_call "
                        f"(built from tool={tool!r} args={call_args!r}, re-parsed to {round_trip!r})"
                    )
                skip_no_call += 1
                refused_calls.append({"record_id": rid, "step": step, "reason": reason})
                history.append((action, env_row["result"]))
                continue

            offsets = probe_input.cuts(thinking, cfg.build.min_think, cfg.build.max_cuts)
            n_cuts = len(offsets)
            cuts_per_event.append(n_cuts)
            eid = event_id(rid, step)
            for cut_index, cut in enumerate(offsets):
                text = probe_input.assemble(
                    task_text, history, thinking[:cut], cfg.build.hist_rounds, cfg.build.probe_result_cap
                )
                depth = round(cut / len(thinking), 4)
                ex_id = example_id(eid, cut_index)

                # 2.5's row gates.
                if text == "":
                    raise ValueError(f"build: example {ex_id}: text is empty")
                if not (0.0 <= depth <= 1.0):
                    raise ValueError(f"build: example {ex_id}: depth {depth} is outside [0, 1]")
                if not text.endswith(thinking[:cut]):
                    raise ValueError(
                        f"build: example {ex_id}: text does not end with the thinking prefix at cut {cut}"
                    )

                weight = 1.0 if weight_mode == "uniform" else round(1.0 / n_cuts, 6)
                rows.append({
                    "example_id": ex_id,
                    "event_id": eid,
                    "record_id": rid,
                    "task_id": task_id,
                    "seed": seed,
                    "step": step,
                    "cut": cut,
                    "cut_index": cut_index,
                    "n_cuts": n_cuts,
                    "depth": depth,
                    "text": text,
                    "tool": tool,
                    "call": call,
                    "args": [{"key": k, "value": v} for k, v in call_args],
                    "weight": weight,
                    "split": row_split,
                    "env": cfg.data.env,
                    "agent_model": agent_model,
                })

            history.append((action, env_row["result"]))

    schema_wo_version = {name: dtype for name, dtype in training_data.SCHEMA.items() if name != "version"}
    if rows:
        frame = pl.DataFrame(rows, infer_schema_length=None, schema_overrides={"args": schema_wo_version["args"]})
        for name, dtype in schema_wo_version.items():
            if name in frame.columns:
                frame = frame.with_columns(pl.col(name).cast(dtype, strict=True))
            else:
                frame = frame.with_columns(pl.lit(training_data.DEFAULTS[name], dtype=dtype).alias(name))
        frame = frame.select(list(schema_wo_version))
    else:
        frame = pl.DataFrame(schema=schema_wo_version)

    seen_splits = sorted(set(frame["split"].to_list())) if frame.height else []
    pre_cap_counts = {name: frame.filter(pl.col("split") == name).height for name in seen_splits}

    # 2.5's per-split cap: the first max_examples rows of each split, in example_id order.
    if cfg.build.max_examples is not None:
        capped = [
            frame.filter(pl.col("split") == name).sort("example_id").head(cfg.build.max_examples)
            for name in seen_splits
        ]
        final_frame = pl.concat(capped) if capped else frame
    else:
        final_frame = frame
    post_cap_counts = {name: final_frame.filter(pl.col("split") == name).height for name in seen_splits}
    cap_dropped = sum(pre_cap_counts[name] - post_cap_counts[name] for name in seen_splits)

    training_data.write(run_dir / "examples.parquet", final_frame)

    consumed: list[dict] = []
    for task_id, seed in pairs:
        path = trajectory_record.record_path(sample_dir, task_id, seed)
        consumed.append({
            "path": str(path),
            "sha1": hashlib.sha1(path.read_bytes()).hexdigest(),
            "n_rows": df.filter(pl.col("record_id") == record_id(task_id, seed)).height,
        })
    consumed.extend(split_files)
    (run_dir / "consumed.json").write_text(json.dumps(consumed, ensure_ascii=False, indent=2) + "\n")

    agent_models = sorted({row["agent_model"] for row in df.filter(pl.col("type") == "meta").iter_rows(named=True)})
    tool_counts = Counter(final_frame["tool"].to_list())
    train_tools = set(final_frame.filter(pl.col("split") == "train")["tool"].to_list())
    val_test_tools = set(final_frame.filter(pl.col("split").is_in(["val", "test"]))["tool"].to_list())
    unseen_tools = sorted(val_test_tools - train_tools)
    depth_deciles = Counter(min(9, int(d * 10)) for d in final_frame["depth"].to_list())
    text_lens = sorted(len(t) for t in final_frame["text"].to_list())

    def _pct(lens: list[int], p: float) -> int:
        if not lens:
            return 0
        return lens[min(len(lens) - 1, int(len(lens) * p))]

    if cuts_per_event:
        cuts_min, cuts_max = min(cuts_per_event), max(cuts_per_event)
        cuts_median = statistics.median(cuts_per_event)
    else:
        cuts_min = cuts_max = cuts_median = 0

    per_split_lines = []
    for name in ("train", "val", "test"):
        sub = final_frame.filter(pl.col("split") == name)
        n_tasks = sub["task_id"].n_unique() if sub.height else 0
        n_events = sub["event_id"].n_unique() if sub.height else 0
        per_split_lines.append(f"- {name}: {n_tasks} tasks, {n_events} events, {sub.height} examples")

    refused_call_lines = [
        f"  - record={entry['record_id']} step={entry['step']}: {entry['reason']}"
        for entry in refused_calls
    ]

    report_lines = [
        "# build report",
        "",
        f"- key={cfg._key} env={cfg.data.env} agent_model={','.join(agent_models)} "
        f"commit={cfg._commit} debug={cfg._debug}",
        f"- records={len(pairs)} events={events_total} "
        f"events_skipped_no_action={skip_no_action} events_skipped_no_call={skip_no_call} "
        f"events_skipped_short_think={skip_short_think} examples={final_frame.height}",
        f"- calls build_call refused or that failed the round-trip gate: {len(refused_calls)}",
        *refused_call_lines,
        f"- cuts per event: min={cuts_min} median={cuts_median} max={cuts_max} (cap {cfg.build.max_cuts})",
        "- per split:",
        *per_split_lines,
        f"- tool vocabulary: {len(tool_counts)} classes; top5 {tool_counts.most_common(5)}",
        f"- long tail (appears fewer than 5 times): {sum(1 for c in tool_counts.values() if c < 5)} classes",
        f"- tools in val or test and never in train: {unseen_tools}",
        f"- examples per depth decile: {[depth_deciles.get(i, 0) for i in range(10)]}",
        f"- text length p50={_pct(text_lens, 0.5)} p90={_pct(text_lens, 0.9)} "
        f"max={text_lens[-1] if text_lens else 0}",
        f"- abort share {abort_frac:.4f} against build.max_abort_frac={cfg.build.max_abort_frac}",
        f"- per-split build.max_examples cap dropped {cap_dropped} rows",
    ]
    (run_dir / "report.md").write_text("\n".join(report_lines) + "\n")

    counts = {
        "records": len(pairs),
        "events": events_total,
        "events_skipped_no_action": skip_no_action,
        "events_skipped_no_call": skip_no_call,
        "events_skipped_short_think": skip_short_think,
        "examples": final_frame.height,
        "examples_train": post_cap_counts.get("train", 0),
        "examples_val": post_cap_counts.get("val", 0),
        "examples_test": post_cap_counts.get("test", 0),
        "tools": len(tool_counts),
        "tools_unseen_in_train": len(unseen_tools),
    }
    registry.write_done(
        run_dir,
        stage="build",
        key=cfg._key,
        commit=cfg._commit,
        counts=counts,
        versions=cfg._versions,
        metrics={},
        report="report.md",
    )
    hb.finish()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the probe training dataset from a sample run's task records.")
    parser.add_argument("--run-dir", required=True, type=Path, help="the build stage's own run directory")
    args = parser.parse_args()
    if not args.run_dir.exists():
        raise SystemExit(f"build: --run-dir {args.run_dir} does not exist")
    main(args.run_dir)
