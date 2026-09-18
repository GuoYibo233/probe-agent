"""The generation step with the probe attached: score the model's own reasoning as it streams, fire early, splice the result in and resume."""
# venv: the environment's
from __future__ import annotations

# TODO(gyb, 2026-09-18): this file was renamed from agent/inject.py on gyb's order, because the old
# name did not say what the file does. The tree document, the contracts and the older
# tickets still use the old name. Delete this comment once every program of the tree is
# written (after wave 7).

import time

from agent import step_without_probe
from agent.injected_text_formats import FORMATS
from data import probe_input
from data.environments import Environment
from data.trajectory_record import Writer
import models
from models.probe_models.service import Client as ProbeClient

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
ARMS = ("probe", "no_probe", "probe_nofill")


def system_text(cfg) -> str | None:
    """FORMATS[cfg.inject.format].system_text when that entry's placement is p1, None otherwise (a p2 entry's system text is applied by the family's wrap_prefetch instead, 7.3)."""
    if cfg.inject is None:
        return None
    fmt = FORMATS[cfg.inject.format]
    return fmt.system_text if fmt.placement == "p1" else None


def ensure_health(clients: step_without_probe.Clients, cfg) -> None:
    """The /health refusal (7.2), taken once by agent/run_tasks.py before the walk, unconditionally across the three arms."""
    mod = models.agent(cfg.models.agent).module
    want_family = cfg.models.agent_row["family"]
    if mod.NAME != want_family:
        raise SystemExit(
            f"agent.step_with_probe.ensure_health: family {mod.NAME!r} of models.agent {cfg.models.agent!r} "
            f"differs from the frozen models.agent_row family {want_family!r}"
        )

    probe: ProbeClient = clients.probe
    health = probe.health()
    if not health.get("decode"):
        raise SystemExit(
            f"agent.step_with_probe.ensure_health: probe /health decode: expected True, got {health.get('decode')!r}"
        )
    if FORMATS[cfg.inject.format].needs_special and not health.get("encode_special"):
        raise SystemExit(
            f"agent.step_with_probe.ensure_health: probe /health encode_special: expected True for format "
            f"{cfg.inject.format!r}, got {health.get('encode_special')!r}"
        )
    want_score_key = cfg._upstream["probe_score.train"]
    got_score_key = health.get("score_train_key")
    if got_score_key != want_score_key:
        raise SystemExit(
            f"agent.step_with_probe.ensure_health: probe /health score_train_key: expected {want_score_key!r}, "
            f"got {got_score_key!r}"
        )
    want_gen_key = cfg._upstream["probe_gen.train"]
    got_gen_key = health.get("gen_train_key")
    if got_gen_key != want_gen_key:
        raise SystemExit(
            f"agent.step_with_probe.ensure_health: probe /health gen_train_key: expected {want_gen_key!r}, "
            f"got {got_gen_key!r}"
        )


def token_boundary(bounds: list[tuple[int, int]], pos: int) -> tuple[int, int] | None:
    """The last (n_chars, n_ids) boundary no later than character position pos, or None when there is none."""
    best = None
    for n_chars, n_ids in bounds:
        if n_chars > pos:
            break
        if best is None or n_chars > best[0]:
            best = (n_chars, n_ids)
    return best


def find_head(gen_ids: list[int], raw: str, pos: int, k0: int, decode) -> tuple[int, str]:
    """The shortest id prefix of gen_ids whose decoded text covers character position pos; raises on a decode/stream mismatch, never silently."""
    if not gen_ids:
        raise RuntimeError("find_head: no generated ids yet")
    k = max(1, min(k0, len(gen_ids)))
    txt = decode(gen_ids[:k])
    while len(txt) < pos and k < len(gen_ids):
        k += 1
        txt = decode(gen_ids[:k])
    while k > 1:
        prev = decode(gen_ids[:k - 1])
        if len(prev) < pos:
            break
        k, txt = k - 1, prev
    if len(txt) < pos:
        raise RuntimeError(
            f"find_head: decoding all {len(gen_ids)} ids gives ({len(txt)} chars), "
            f"which does not cover the cut at {pos}"
        )
    n = min(len(txt), len(raw))
    if txt[:n] != raw[:n]:
        raise RuntimeError(
            f"find_head: decode(ids[:{k}]) does not match the streamed text: "
            f"{txt[max(0, n - 60):n]!r} vs {raw[max(0, n - 60):n]!r}"
        )
    return k, txt


def _resume_fields(pending: dict, gen_ids: list[int], stop_reason: str | None) -> dict:
    """match_len/identical between the resent continuation's new ids and the ids discarded at the last fire."""
    new = gen_ids[pending["head_tok"] + pending["note_tok"]:]
    overflow = pending["overflow_ids"]
    m = 0
    while m < min(len(new), len(overflow)) and new[m] == overflow[m]:
        m += 1
    return {
        "fire_index": pending["fire_index"],
        "overflow_tok": len(overflow),
        "new_tok": len(new),
        "match_len": m,
        "identical": m == len(overflow) and len(new) >= len(overflow),
        "stop_reason": stop_reason,
    }


def step(env: Environment, clients: step_without_probe.Clients, cfg, writer: Writer, messages: list[dict],
         prefix_ids: list[int], history: list[tuple[str, str]], task_text: str, step_index: int,
         seed: int | None) -> step_without_probe.StepResult:
    """Iterate generate's token stream, score each cut, fire on the first crossing of theta, splice the result in and resume."""
    del messages
    mod = models.agent(cfg.models.agent).module
    store_ids = cfg.inject.store_token_ids
    fmt = FORMATS[cfg.inject.format]

    t0 = time.clock_gettime(time.CLOCK_MONOTONIC)

    raw = ""
    gen_ids: list[int] = []
    bounds: list[tuple[int, int]] = [(0, 0)]
    state: dict = {}
    out = {"reasoning": "", "content": ""}
    checked: set[int] = set()
    n_checked = 0
    n_inject = 0
    fire_index = 0
    accepted = 0
    probing = cfg.inject.arm != "no_probe"
    pending: dict | None = None
    discard = {"chars": 0, "tokens": 0, "events": 0}
    usage_in = usage_out = 0
    finish_reason = stop_reason = None

    while True:
        budget = max(1, cfg.generation.max_step_tokens - len(gen_ids))
        st = step_without_probe.stream(clients, cfg, prefix_ids + gen_ids, seed, budget=budget)
        fired = False
        for delta, ids in st:
            raw += delta
            gen_ids += ids
            bounds.append((len(raw), len(gen_ids)))
            out = mod.parse(delta, state)
            if not probing or n_inject >= cfg.inject.max_inject_per_step:
                continue
            if not any(c in delta for c in ".!?\n"):
                continue
            thinking_so_far = out["reasoning"]
            if not raw.endswith(thinking_so_far):
                probing = False
                continue
            ts = len(raw) - len(thinking_so_far)
            if len(thinking_so_far.strip()) < cfg.build.min_think:
                continue
            for cut in probe_input.cuts_live(thinking_so_far, cfg.build.min_think):
                if cut in checked or cut <= accepted:
                    continue
                if n_checked >= cfg.inject.max_cuts:
                    probing = False
                    break
                checked.add(cut)
                n_checked += 1
                probe_text = probe_input.assemble(
                    task_text, history, thinking_so_far[:cut],
                    cfg.build.hist_rounds, cfg.build.probe_result_cap,
                )
                if cfg.inject.fire_nth_cut > 0:
                    conf, pred_label = None, None
                    fire_now = n_checked == cfg.inject.fire_nth_cut
                else:
                    scored = clients.probe.score(probe_text)
                    conf, pred_label = scored["conf"], scored["label"]
                    fire_now = conf >= cfg.inject.theta
                if not fire_now:
                    continue

                # ---- fire: back the cut off to a token boundary, the model's own ids ----
                pos = ts + cut
                k0 = token_boundary(bounds, pos)[1]
                k, head_txt = find_head(gen_ids, raw, pos, k0,
                                        lambda ids: clients.probe.decode(ids)["text"])
                head_ids = gen_ids[:k]
                overflow_ids = gen_ids[k:]

                if cfg.inject.arm == "probe_nofill":
                    note = ""
                    gen_call = exec_code = arg_modes = exec_out = error_kind = spec_s = None
                    exec_ok = None
                else:
                    gen_call = clients.probe.generate(probe_text, cfg.inject.max_new)["call"]
                    completed_call = env.complete_call(gen_call)
                    spec = env.speculate(completed_call)
                    exec_code = spec["exec_code"]
                    arg_modes = spec["arg_modes"]
                    exec_out = spec["exec_out"]
                    exec_ok = spec["exec_ok"]
                    error_kind = spec["error_kind"]
                    spec_s = spec["spec_s"]
                    body = fmt.render(gen_call, exec_out, exec_ok, error_kind)
                    if fmt.placement == "p1":
                        note = ("" if head_txt[-1:].isspace() else "\n") + body
                    else:
                        note = mod.wrap_prefetch(body, fmt.system_text)
                note_ids = (clients.probe.encode(note, fmt.needs_special)["ids"] if note else [])

                discarded_chars = max(0, len(raw) - len(head_txt))
                discard["chars"] += discarded_chars
                discard["tokens"] += len(overflow_ids)
                discard["events"] += 1

                writer.row(
                    "spec", step=step_index, fire_index=fire_index, cut=cut, n_checked=n_checked,
                    conf=conf, pred_label=pred_label, gen_call=gen_call, exec_code=exec_code,
                    arg_modes=arg_modes, exec_out=exec_out, exec_ok=exec_ok, error_kind=error_kind,
                    note=note, format=cfg.inject.format, head_tok=k, head_chars=len(head_txt) - ts,
                    note_tok=len(note_ids), discarded_chars=discarded_chars,
                    overflow_ids=(overflow_ids if store_ids else None), spec_s=spec_s,
                )
                if pending is not None:
                    writer.row("resume", step=step_index, **_resume_fields(pending, gen_ids, st.stop_reason))

                raw = head_txt + note
                gen_ids = head_ids + note_ids
                bounds = [(len(raw), len(gen_ids))]
                state = {}
                out = mod.parse(raw, state)
                checked = set()
                accepted = (len(head_txt) - ts) + len(note)
                pending = {"overflow_ids": overflow_ids, "head_tok": k, "note_tok": len(note_ids),
                           "fire_index": fire_index}
                fire_index += 1
                n_inject += 1
                fired = True
                break
            if fired:
                break

        if st.usage:
            usage_in += st.usage.get("prompt_tokens", 0)
            usage_out += st.usage.get("completion_tokens", 0)
        else:
            usage_out += st.n_ids
        finish_reason, stop_reason = st.finish_reason, st.stop_reason

        if pending is not None and not fired:
            writer.row("resume", step=step_index, **_resume_fields(pending, gen_ids, st.stop_reason))
            pending = None
        if fired:
            st.close()
            continue
        break

    t1 = time.clock_gettime(time.CLOCK_MONOTONIC)
    return step_without_probe.StepResult(
        reasoning=out["reasoning"],
        content=out["content"],
        usage={"in": usage_in, "out": usage_out},
        wall_s=round(t1 - t0, 2),
        finish_reason=finish_reason,
        stop_reason=stop_reason,
        prefix_tok=len(prefix_ids),
        prefix_sha=step_without_probe.ids_sha(prefix_ids),
        gen_ids=gen_ids if store_ids else None,
        n_inject=n_inject,
        discard=discard,
    )
