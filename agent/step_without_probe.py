"""The plain generation step: stream tokens from the agent model to end of turn, exposing the stream so step_with_probe.py can iterate it instead."""
# venv: the environment's
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import models
from models.agent_models.service import Client as AgentClient

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

# Set once the family of cfg.models.agent has been compared against
# cfg.models.agent_row["family"] in this process (errata: taken once per
# process, not once per step).
_family_checked = False


@dataclass
class StepResult:
    """The gen row's non-derived fields, filled by both step_without_probe.step and step_with_probe.step."""

    reasoning: str
    content: str
    usage: dict                 # {"in": int, "out": int}
    wall_s: float
    finish_reason: str | None
    stop_reason: str | None
    prefix_tok: int
    prefix_sha: str
    gen_ids: list[int] | None
    n_inject: int
    discard: dict                # {"chars": int, "tokens": int, "events": int}


@dataclass
class Clients:
    """The two service clients a step needs, constructed once by agent/run_tasks.py from its endpoint files."""

    agent: AgentClient
    probe: object                # kept generic (7.3): the probe service's client class is never named in this file


def ids_sha(ids: list[int]) -> str:
    """sha1 of the comma-joined decimal token ids, so two prompts can be compared id for id without storing either whole."""
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()


def _store_token_ids(cfg) -> bool:
    """Read store_token_ids off the one section the frozen setting holds (5.1's cfg.inject is None test)."""
    return cfg.sample.store_token_ids if cfg.inject is None else cfg.inject.store_token_ids


def _check_family_once(cfg, mod) -> None:
    global _family_checked
    if _family_checked:
        return
    want = cfg.models.agent_row["family"]
    if mod.NAME != want:
        raise SystemExit(
            f"agent.step_without_probe: family {mod.NAME!r} of models.agent {cfg.models.agent!r} differs "
            f"from the frozen models.agent_row family {want!r}"
        )
    _family_checked = True


def stream(clients: Clients, cfg, prefix_ids: list[int], seed: int | None, *, budget: int | None = None):
    """Open one token stream from the agent client, with the per-request max_tokens either the step budget or the given one (a resend after a fire needs a shrunken budget, errata)."""
    generation = {
        "max_tokens": cfg.generation.max_step_tokens if budget is None else budget,
        "temperature": cfg.generation.temperature,
        "top_p": cfg.generation.top_p,
        "stop": cfg.generation.stop,
    }
    return clients.agent.stream(prefix_ids, generation, seed)


def step(env, clients: Clients, cfg, writer, messages: list[dict], prefix_ids: list[int],
         history: list[tuple[str, str]], task_text: str, step_index: int, seed: int | None) -> StepResult:
    """Stream one turn from the agent model to end of turn, with no probe attached; the baseline path step_with_probe.step replaces."""
    del env, writer, messages, history, task_text  # accepted only so the two step implementations are substitutable (7.3)
    mod = models.agent(cfg.models.agent).module
    _check_family_once(cfg, mod)

    t0 = time.clock_gettime(time.CLOCK_MONOTONIC)
    st = stream(clients, cfg, prefix_ids, seed)
    state: dict = {}
    out = {"reasoning": "", "content": ""}
    gen_ids: list[int] = []
    for delta, ids in st:
        gen_ids += ids
        out = mod.parse(delta, state)
    t1 = time.clock_gettime(time.CLOCK_MONOTONIC)

    if st.usage:
        usage = {"in": st.usage.get("prompt_tokens", 0), "out": st.usage.get("completion_tokens", 0)}
    else:
        usage = {"in": 0, "out": st.n_ids}

    return StepResult(
        reasoning=out["reasoning"],
        content=out["content"],
        usage=usage,
        wall_s=round(t1 - t0, 2),
        finish_reason=st.finish_reason,
        stop_reason=st.stop_reason,
        prefix_tok=len(prefix_ids),
        prefix_sha=ids_sha(prefix_ids),
        gen_ids=gen_ids if _store_token_ids(cfg) else None,
        n_inject=0,
        discard={"chars": 0, "tokens": 0, "events": 0},
    )
