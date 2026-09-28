"""Run each task and seed of a piece's rotation to completion, claiming tasks across pieces and writing the record."""
# venv: the environment's (appworld today)
from __future__ import annotations

import argparse
import dataclasses
import http.client
import json
import sys
import time
import urllib.error
from pathlib import Path

from data.environments import open_env, requested_pairs
from data.trajectory_record import done_pairs, open_record, to_messages
from experimental_settings import schema
from jobs import launch, registry
from models.agent_models.service import Client as AgentClient
from models.probe_models.service import Client as ProbeClient

from agent import step_with_probe, step_without_probe



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


class _ServiceGone(Exception):
    """The agent server or the probe service stopped answering, after the client's own retries."""


def _is_connection_failure(exc: Exception) -> bool:
    """True when exc says a service failed, as opposed to this task: no connection, a timeout, a broken stream, or an HTTP status other than 400 (400 is the agent server's context overflow, one task's own failure). The agent client raises the HTTPError itself; the probe client raises RuntimeError from the HTTPError its service answered with, so the status is read off the cause there."""
    status = exc if isinstance(exc, urllib.error.HTTPError) else exc.__cause__
    if isinstance(status, urllib.error.HTTPError):
        return status.code != 400
    return isinstance(exc, (urllib.error.URLError, http.client.HTTPException,
                            ConnectionError, TimeoutError))


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
    i, n = piece
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
    # Piece i starts at its own stretch of the list and the claim files stay: a piece that
    # finishes its stretch walks on into the next one, and a dead piece's tasks are still
    # picked up. Only the order tasks run in depends on this, no record does.
    start = i * len(triples) // n
    triples = triples[start:] + triples[:start]

    hb = registry.beat(run_dir, i)
    hb.emit(0, len(triples), "task")
    done = 0
    # The heartbeat's finish() comes after the walk and outside any `finally`: a piece that
    # crashes, or exits because a service is gone, does not report itself done.
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
                    # the two calls that reach a service; the clients have already retried
                    try:
                        prefix_ids = clients.probe.render(
                            messages, cfg.generation.effort, cfg.generation.date
                        )["prefix_ids"]
                        res = gen_step(env, clients, cfg, writer, messages, prefix_ids, history,
                                       task_text, step_index, seed)
                    except Exception as exc:
                        if _is_connection_failure(exc):
                            raise _ServiceGone(f"{type(exc).__name__}: {exc}") from exc
                        raise
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
        # A service that stopped answering is not this task's failure: every task after it
        # would fail within seconds, and a final row certifies a task as run for good. So the
        # record gets no final row and the piece ends here; the next launch releases the
        # unfinished record (its owner is no longer live) and the task runs again.
        # Owner ruling 2026-09-24 (ruling 7), confirmed as coded: a probe-service status other
        # than 400 (500 included, which the service answers for any handler exception, so a text
        # that reliably fails it ends the piece at the same task on every relaunch) ends this piece
        # (a 5xx after the client's retries, any other status at once). A piece that ends this
        # way writes no `done` beat, and once every piece of the run reads `dead` (the loop pieces
        # and every service piece: each agent replica and the probe service) and the start row is
        # older than `launch_timeout_s`, `run.py ls` / `sync` close the run as `launch_failed`;
        # while one service piece is still up, the run stays open.
        except _ServiceGone as exc:
            writer.close()
            raise SystemExit(
                f"agent.run_tasks: task {task_id} seed {seed}: a service stopped answering "
                f"({exc}); this piece ends with the record left unfinished"
            ) from exc
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
    hb.finish()

    # When every requested pair has a finished record, this run's services are ended here, so a
    # run whose pieces finish overnight frees its cards at once. teardown_services leaves alone
    # a server another live run is attached to. done.json and the finish row stay run.py's to
    # write on the next walk, so nothing a later stage reads depends on this.
    # TODO(gyb, 2026-09-22): contracts 2.3 ("Ending the service pieces") still says
    # teardown_services has two callers, run.py and jobs/launch.launch; this is the third, and
    # the contracts are the owner's to update.
    pairs =[(task_id, seed) for _split, task_id, seed in triples]
    if done_pairs(run_dir, pairs) == set(pairs):
        ended = launch.teardown_services(run_dir)
        print(f"agent.run_tasks: every requested record is finished; ended services: {ended}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="python -m agent.run_tasks")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--piece", required=True, type=_parse_piece, help="i/n")
    args = ap.parse_args()
    main(args.run_dir, args.piece)
