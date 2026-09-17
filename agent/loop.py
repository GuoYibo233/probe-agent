"""Run each task and seed of a piece's rotation to completion, claiming tasks across pieces and writing the record."""
# venv: the environment's (appworld today)
from __future__ import annotations

import argparse
import dataclasses
import json
import time
import urllib.error
from pathlib import Path

from data.environments import open_env, requested_pairs
from data.trajectory_record import open_record, to_messages
from experimental_settings import schema
from jobs import registry
from models.agent_models.service import Client as AgentClient
from models.probe_models.service import Client as ProbeClient

from agent import generate, inject

VERSION = 1


def _canonical_json(obj) -> str:
    """1.1's canonical JSON text: sorted keys, no ascii escaping, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _parse_piece(text: str) -> tuple[int, int]:
    i_str, _, n_str = text.partition("/")
    return int(i_str), int(n_str)


def _wait_for_endpoints(run_dir: Path, agent_path: Path, probe_path: Path, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while not (agent_path.exists() and probe_path.exists()):
        if time.monotonic() > deadline:
            missing = [p for p in (agent_path, probe_path) if not p.exists()]
            raise SystemExit(
                f"agent.loop: {run_dir}: endpoint file(s) did not appear within {timeout_s}s: {missing}"
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

    clients = generate.Clients(
        agent=AgentClient(agent_doc["base_url"], cfg.models.agent_row["served_model_name"]),
        probe=ProbeClient(probe_doc["base_url"]),
    )

    health = clients.probe.health()
    if health.get("render") != "ids":
        raise SystemExit(f"agent.loop: probe /health render: expected 'ids', got {health.get('render')!r}")
    if health.get("family") != cfg.models.agent_row["family"]:
        raise SystemExit(
            f"agent.loop: probe /health family: expected {cfg.models.agent_row['family']!r}, "
            f"got {health.get('family')!r}"
        )
    if health.get("weights") != cfg.models.agent_row["weights"]:
        raise SystemExit(
            f"agent.loop: probe /health weights: expected {cfg.models.agent_row['weights']!r}, "
            f"got {health.get('weights')!r}"
        )

    if cfg.inject is not None:
        inject.ensure_health(clients, cfg)

    gen_step = inject.step if cfg.inject is not None else generate.step
    extra = inject.system_text(cfg)

    triples = requested_pairs(env, run.split, run.tasks, run.n_tasks, run.seeds)
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
                writer.row(
                    "meta", stage=cfg._stage, env=cfg.data.env, task_id=task_id, seed=seed,
                    env_seed=env.SEED, split=split, arm=arm, instructions=cfg.data.instructions,
                    task_text=task_text, agent_model=cfg.models.agent,
                    generation=_canonical_json(dataclasses.asdict(cfg.generation)),
                    inject=(_canonical_json(dataclasses.asdict(cfg.inject)) if cfg.inject is not None else None),
                    commit=cfg._commit, run_key=cfg._key, owner_session=f"{cfg._stage}-{cfg._key}-{i}",
                )
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
            except Exception as exc:  # one task's failure must not take the whole piece down (errata)
                t1 = time.clock_gettime(time.CLOCK_MONOTONIC)
                if not meta_written:
                    writer.row(
                        "meta", stage=cfg._stage, env=cfg.data.env, task_id=task_id, seed=seed,
                        env_seed=env.SEED, split=split, arm=arm, instructions=cfg.data.instructions,
                        task_text="", agent_model=cfg.models.agent,
                        generation=_canonical_json(dataclasses.asdict(cfg.generation)),
                        inject=(_canonical_json(dataclasses.asdict(cfg.inject)) if cfg.inject is not None else None),
                        commit=cfg._commit, run_key=cfg._key, owner_session=f"{cfg._stage}-{cfg._key}-{i}",
                    )
                writer.row(
                    "final", steps=steps_done, completed=False,
                    abort=f"task_error:{type(exc).__name__}",
                    judge=_canonical_json({"success": False, "task_error": str(exc)}), success=False,
                    tokens_in=tokens_in, tokens_out=tokens_out, wall_s=round(t1 - t0, 2),
                    finished_at=time.clock_gettime(time.CLOCK_REALTIME),
                )
                writer.close()
            finally:
                env.close()

            done += 1
            hb.emit(done, len(triples), "task", tok_in=tokens_in, tok_out=tokens_out)
    finally:
        hb.finish()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="python -m agent.loop")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--piece", required=True, type=_parse_piece, help="i/n")
    args = ap.parse_args()
    main(args.run_dir, args.piece)
