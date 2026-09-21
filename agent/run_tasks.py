"""Run each task and seed of a piece's rotation to completion, claiming tasks across pieces and writing the record."""
# venv: the environment's (appworld today)
from __future__ import annotations

# TODO(gyb, 2026-09-18): this file was renamed from agent/loop.py on gyb's order, because the old
# name did not say what the file does. The tree document, the contracts and the older
# tickets still use the old name. Delete this comment once every program of the tree is
# written (after wave 7).

import argparse
import dataclasses
import json
import sys
import time
import urllib.error
from pathlib import Path

from data.environments import open_env, requested_pairs
from data.trajectory_record import open_record, to_messages
from experimental_settings import schema
from jobs import registry
from models.agent_models.service import Client as AgentClient
from models.probe_models.service import Client as ProbeClient

from agent import step_with_probe, step_without_probe

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


def _canonical_json(obj) -> str:
    """1.1's canonical JSON text: sorted keys, no ascii escaping, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _meta_fields(cfg, task_id: str, seed: int | None, env_seed, split: str, arm: str,
                  task_text: str, piece_i: int) -> dict:
    """The meta row's shared field set (1.1), task_text aside: the normal write and the exception-guard write both call this."""
    return dict(
        stage=cfg._stage, env=cfg.data.env, task_id=task_id, seed=seed,
        env_seed=env_seed, split=split, arm=arm, instructions=cfg.data.instructions,
        task_text=task_text, agent_model=cfg.models.agent,
        generation=_canonical_json(dataclasses.asdict(cfg.generation)),
        inject=(_canonical_json(dataclasses.asdict(cfg.inject)) if cfg.inject is not None else None),
        commit=cfg._commit, run_key=cfg._key, owner_session=f"{cfg._stage}-{cfg._key}-{piece_i}",
    )


def _parse_piece(text: str) -> tuple[int, int]:
    i_str, _, n_str = text.partition("/")
    return int(i_str), int(n_str)


def _wait_for_endpoints(run_dir: Path, agent_path: Path, probe_path: Path, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while not (agent_path.exists() and probe_path.exists()):
        if time.monotonic() > deadline:
            missing = [p for p in (agent_path, probe_path) if not p.exists()]
            raise SystemExit(
                f"agent.run_tasks: {run_dir}: endpoint file(s) did not appear within {timeout_s}s: {missing}"
            )
        time.sleep(1.0)


def main(run_dir: str | Path, piece: tuple[int, int]) -> None:
    """Read the frozen setting, walk this piece's rotation of requested triples, and write one record per task."""
    i, _n = piece
    run_dir = Path(run_dir)
    cfg = schema.load_frozen(run_dir)
    run = cfg.inject if cfg.inject is not None else cfg.sample
    arm = "sample" if cfg.inject is None else cfg.inject.arm

    env = open_env(cfg.data.env)

    replica = i % run.replicas
    agent_path = run_dir / f"service_agent_{replica}.json"
    probe_path = run_dir / "service_probe_0.json"
    _wait_for_endpoints(run_dir, agent_path, probe_path, registry.DEFAULTS["launch_timeout_s"])
    agent_doc = json.loads(agent_path.read_text())
    probe_doc = json.loads(probe_path.read_text())

    clients = step_without_probe.Clients(
        agent=AgentClient(agent_doc["base_url"], cfg.models.agent_row["served_model_name"]),
        probe=ProbeClient(probe_doc["base_url"]),
    )

    health = clients.probe.health()
    if health.get("render") != "ids":
        raise SystemExit(f"agent.run_tasks: probe /health render: expected 'ids', got {health.get('render')!r}")
    if health.get("family") != cfg.models.agent_row["family"]:
        raise SystemExit(
            f"agent.run_tasks: probe /health family: expected {cfg.models.agent_row['family']!r}, "
            f"got {health.get('family')!r}"
        )
    if health.get("weights") != cfg.models.agent_row["weights"]:
        raise SystemExit(
            f"agent.run_tasks: probe /health weights: expected {cfg.models.agent_row['weights']!r}, "
            f"got {health.get('weights')!r}"
        )

    if cfg.inject is not None:
        step_with_probe.ensure_health(clients, cfg)

    gen_step = step_with_probe.step if cfg.inject is not None else step_without_probe.step
    extra = step_with_probe.system_text(cfg)

    triples = requested_pairs(env, run.split, run.tasks, run.n_tasks, run.seeds)
    # TODO(gyb, 2026-09-22): the pieces start one task apart, so all of them walk nearly the same
    # stretch of the list and keep meeting each other's claims. Start piece i at
    # i * len(triples) // n instead, and keep the claim files: each piece then works its own
    # stretch, a piece that finishes early walks on into the next stretch, and a dead piece's
    # tasks are still picked up. Only the order tasks run in changes, no record does.
    triples = triples[i:] + triples[:i]

    hb = registry.beat(run_dir, i)
    hb.emit(0, len(triples), "task")
    done = 0
    try:
        for split, task_id, seed in triples:
            writer = open_record(run_dir, task_id, seed)
            if writer is None:
                continue  # another piece holds this record; move on, deleting nothing

            history: list[tuple[str, str]] = []
            steps_done = 0
            completed = False
            abort: str | None = None
            tokens_in = tokens_out = 0
            meta_written = False
            t0 = time.clock_gettime(time.CLOCK_MONOTONIC)
            try:
                env.open(task_id, seed)
                task_text = env.task_text
                writer.row("meta", **_meta_fields(cfg, task_id, seed, env.SEED, split, arm, task_text, i))
                meta_written = True

                try:
                    for step_index in range(run.max_steps):
                        messages = to_messages(
                            writer.frame(), step_index, task_text,
                            env.INSTRUCTIONS[cfg.data.instructions], env.NO_CODE_MESSAGE, extra,
                        )
                        prefix_ids = clients.probe.render(
                            messages, cfg.generation.effort, cfg.generation.date
                        )["prefix_ids"]
                        res = gen_step(env, clients, cfg, writer, messages, prefix_ids, history,
                                       task_text, step_index, seed)
                        writer.row("gen", step=step_index, **dataclasses.asdict(res))
                        tokens_in += res.usage.get("in", 0)
                        tokens_out += res.usage.get("out", 0)

                        obs = env.step(res.content)
                        writer.row("env", step=step_index, action=obs.action,
                                  result=obs.observation, error_kind=obs.error_kind)
                        steps_done = step_index + 1
                        if obs.action is not None and obs.action.strip():
                            history.append((obs.action.strip(), obs.observation))
                        if obs.completed:
                            completed = True
                            break
                except urllib.error.HTTPError as exc:
                    if exc.code != 400:
                        raise
                    abort = "context_overflow_400"

                judge = env.judge()
                t1 = time.clock_gettime(time.CLOCK_MONOTONIC)
                writer.row(
                    "final", steps=steps_done, completed=completed, abort=abort,
                    judge=_canonical_json(judge), success=judge["success"],
                    tokens_in=tokens_in, tokens_out=tokens_out, wall_s=round(t1 - t0, 2),
                    finished_at=time.clock_gettime(time.CLOCK_REALTIME),
                )
                writer.close()
            # TODO(gyb, 2026-09-22): this handler also catches a service that is gone. When the
            # agent server or the probe service stops answering, every task after this one fails
            # within seconds, each gets a final row, and a final row certifies the task as run:
            # no later launch runs it again, `retry sample` does not clear it, and build then
            # refuses on max_abort_frac. Fix: a connection failure of the render call or of the
            # generation step (urllib.error.URLError, an HTTP status other than 400,
            # http.client.HTTPException, ConnectionError, TimeoutError, all after the client's
            # own retries) writes no final row and ends this piece with SystemExit, so the next
            # launch releases the unfinished record and the task runs again. With it, the
            # heartbeat's finish() at the end of main() moves out of its `finally`, so that a
            # piece that exits this way, or crashes, does not report itself done (review
            # ticket 31).
            except Exception as exc:  # one task's failure must not take the whole piece down (errata)
                t1 = time.clock_gettime(time.CLOCK_MONOTONIC)
                if not meta_written:
                    writer.row("meta", **_meta_fields(cfg, task_id, seed, env.SEED, split, arm, "", i))
                writer.row(
                    "final", steps=steps_done, completed=False,
                    abort=f"task_error:{type(exc).__name__}",
                    judge=_canonical_json({"success": False, "task_error": str(exc)}), success=False,
                    tokens_in=tokens_in, tokens_out=tokens_out, wall_s=round(t1 - t0, 2),
                    finished_at=time.clock_gettime(time.CLOCK_REALTIME),
                )
                writer.close()
            finally:
                # a raising close() must cost only this task's teardown, not the piece's walk
                try:
                    env.close()
                except Exception as exc:
                    print(
                        f"agent.run_tasks: task {task_id} seed {seed}: env.close() failed: {exc}",
                        file=sys.stderr,
                    )

            done += 1
            hb.emit(done, len(triples), "task", tok_in=tokens_in, tok_out=tokens_out)
    finally:
        hb.finish()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="python -m agent.run_tasks")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--piece", required=True, type=_parse_piece, help="i/n")
    args = ap.parse_args()
    main(args.run_dir, args.piece)
