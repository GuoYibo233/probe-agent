"""CPU-only regression test for the fullhist arm (T12d).

Two things are proved here, no GPU and no model server involved:

  A) mem/nomem prompt parity — the pre-change fig1_run.py is pulled straight out
     of git (`git show <ref>:fig1_pilot/fig1_run.py`), loaded as a second module,
     and both its episode() and the new one are driven by the SAME scripted fake
     env, fake LLM client and freshly seeded RNG. Every per-step prompt is
     captured and compared byte-for-byte (sha256 over the whole prompt list).

  B) fullhist behaviour — the block really contains earlier episodes' full
     transcripts, and over budget it drops WHOLE episodes oldest-first, then
     (newest episode alone still too big) drops that episode's oldest turns.

Usage:  ./fig1-env/bin/python test_prompt_parity.py [--ref HEAD]
Exit code 0 = all checks pass.
"""

import argparse
import hashlib
import importlib.util
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SEED = 20260729  # project convention; no other source of randomness here


# ---------------------------------------------------------------- fakes

class FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMsg(content)


class FakeResp:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]
        self.usage = FakeUsage()


class FakeCompletions:
    """Records every user prompt; always answers with the 1st admissible cmd.

    Answering with a constant also exercises the 'same action 3x in a row ->
    rng.choice(others)' branch, so RNG consumption is compared too.
    """

    def __init__(self, sink):
        self.sink = sink

    def create(self, model=None, messages=None, **kw):
        self.sink.append({"system": messages[0]["content"],
                          "user": messages[1]["content"],
                          "kw": repr(sorted(kw.items()))})
        return FakeResp("go to cabinet 1")


class FakeClient:
    def __init__(self, sink):
        self.chat = type("C", (), {"completions": FakeCompletions(sink)})()


class FakeEnv:
    """Scripted ALFWorld stand-in: never finishes, observations vary in length
    (some over the 300-char clip), admissible list changes every step."""

    def __init__(self):
        self.t = 0

    def _info(self):
        n = 3 + (self.t % 4)
        cmds = ["go to cabinet 1", "look", "inventory"]
        cmds += [f"go to drawer {i}" for i in range(1, n)]
        return {"admissible_commands": [cmds], "won": [False]}

    def reset(self):
        obs = ("-= Welcome to TextWorld! =- You are in a kitchen. "
               "Your task is to: put a mug in cabinet.")
        return [obs], self._info()

    def step(self, actions):
        self.t += 1
        pad = "shelf clutter " * (5 + 30 * (self.t % 2))  # sometimes > 300 chars
        obs = f"You take step {self.t} after '{actions[0]}'. {pad}"
        return [obs], [0], [False], self._info()

    def close(self):
        pass


MEM_BLOCK_SAMPLE = (
    "Task: put a mug in cabinet.\n"
    "Successful actions: go to countertop 1 -> take mug 1 from countertop 1 -> "
    "go to cabinet 1 -> open cabinet 1 -> move mug 1 to cabinet 1\n"
    "\n"
    "Task: put a spoon in drawer.\n"
    "Successful actions: go to drawer 2 -> open drawer 2 -> move spoon 1 to drawer 2"
)


# ---------------------------------------------------------------- helpers

def load_old_module(ref):
    src = subprocess.run(
        ["git", "show", f"{ref}:fig1_pilot/fig1_run.py"],
        cwd=HERE.parent, capture_output=True, text=True, check=True).stdout
    tmp = Path(tempfile.mkdtemp()) / "fig1_run_old.py"
    tmp.write_text(src)
    return load_module("fig1_run_old", tmp), src


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_episode(mod, memory_block, max_steps=12):
    sink = []
    rec = mod.episode(FakeEnv(), FakeClient(sink), "fake-model", max_steps,
                      memory_block, 2048, True, random.Random(SEED))
    rec = {k: v for k, v in rec.items() if k != "wall_s"}  # timing is not content
    return sink, rec


def digest(prompts):
    h = hashlib.sha256()
    for p in prompts:
        h.update(p["system"].encode() + b"\x00" + p["user"].encode()
                 + b"\x00" + p["kw"].encode() + b"\x01")
    return h.hexdigest()


def ep(idx, success, n_turns, obs_len=40):
    return {"episode_idx": idx, "success": success,
            "task": f"put object {idx} in receptacle {idx}.",
            "turns": [[f"act{idx}_{j}", f"obs{idx}_{j} " + "x" * obs_len]
                      for j in range(n_turns)]}


fails = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="HEAD", help="git ref holding the pre-change file")
    a = ap.parse_args()

    new = load_module("fig1_run_new", HERE / "fig1_run.py")
    old, old_src = load_old_module(a.ref)

    print(f"A) mem/nomem prompt parity vs {a.ref} "
          f"(old file {len(old_src)} bytes)")
    check("old file predates fullhist", "fullhist" not in old_src)

    for arm, block in [("nomem", ""), ("mem", MEM_BLOCK_SAMPLE)]:
        po, ro = run_episode(old, block)
        pn, rn = run_episode(new, block)
        do, dn = digest(po), digest(pn)
        check(f"{arm}: {len(pn)} prompts, sha256 {dn[:16]}… identical",
              do == dn and len(po) == len(pn) == 12,
              "" if do == dn else f"old {do[:16]}… != new {dn[:16]}…")
        check(f"{arm}: episode() record identical", ro == rn,
              "" if ro == rn else f"{ro} != {rn}")
        if arm == "mem":
            check("mem: header string unchanged",
                  "=== experience from earlier similar tasks ===" in pn[0]["user"])
        else:
            check("nomem: no context block, prompt starts at the task obs",
                  pn[0]["user"].startswith("-= Welcome to TextWorld!")
                  and "experience from earlier" not in pn[0]["user"])
        check(f"{arm}: no fullhist key in record", "transcript" not in rn)

    print("\nB) fullhist block construction")
    tr = [ep(0, True, 3), ep(1, False, 4), ep(2, True, 2), ep(3, True, 5)]
    words = lambda s: len(s.split())  # deterministic stand-in tokenizer

    blk, st = new.build_fullhist_block(tr, 10 ** 6, words)
    check("no budget pressure: all 4 episodes kept",
          st["fullhist_eps_included"] == 4 and not st["fullhist_truncated"], str(st))
    check("earlier transcripts present verbatim (actions AND observations)",
          all(f"> act{i}_0" in blk for i in range(4))
          and all(f"obs{i}_0" in blk for i in range(4)))
    check("episodes ordered oldest -> newest",
          blk.index("episode 0") < blk.index("episode 1")
          < blk.index("episode 2") < blk.index("episode 3"))
    check("failure episodes included too (unlike mem arm)",
          "episode 1 (failure)" in blk)

    per_ep = [words(new.render_episode_transcript(t)) for t in tr]
    budget = per_ep[-1] + per_ep[-2] + 4          # room for ~2 newest episodes
    blk2, st2 = new.build_fullhist_block(tr, budget, words)
    check("over budget: whole episodes dropped OLDEST-first",
          st2["fullhist_eps_dropped_oldest"] == 2
          and st2["fullhist_eps_included"] == 2
          and st2["fullhist_truncated"] is True, str(st2))
    check("over budget: oldest gone, newest kept",
          "act0_0" not in blk2 and "act1_0" not in blk2
          and "act2_0" in blk2 and "act3_0" in blk2)
    check("over budget: block within budget", words(blk2) <= budget,
          f"{words(blk2)} <= {budget}")

    tiny = words(new.render_episode_transcript(ep(3, True, 2))) - 2
    blk3, st3 = new.build_fullhist_block(tr, tiny, words)
    check("newest alone too big: only newest episode survives",
          st3["fullhist_eps_included"] == 1
          and st3["fullhist_eps_dropped_oldest"] == 3, str(st3))
    check("newest alone too big: its OLDEST turns cut first",
          st3["fullhist_turns_head_cut"] > 0
          and "act3_0" not in blk3 and "act3_4" in blk3,
          f"head_cut={st3['fullhist_turns_head_cut']}")
    check("newest alone too big: block within budget", words(blk3) <= tiny,
          f"{words(blk3)} <= {tiny}")

    blk0, st0 = new.build_fullhist_block([], 10 ** 6, words)
    check("episode 0 has empty block, zeroed stats",
          blk0 == "" and st0["fullhist_eps_included"] == 0
          and not st0["fullhist_truncated"])

    print("\nC) fullhist prompt end-to-end (same fakes, mocked LLM)")
    pf, rf = run_episode_fullhist(new, blk)
    check("fullhist header used", new.FULLHIST_HEADER in pf[0]["user"])
    check("mem header NOT used", new.MEM_HEADER not in pf[0]["user"])
    check("prior-episode transcript inside the prompt",
          "> act0_0" in pf[0]["user"] and "obs3_4" in pf[0]["user"])
    check("current-episode sections still there",
          "=== recent history ===" in pf[0]["user"]
          and "=== admissible commands ===" in pf[0]["user"])
    check("transcript captured for the next episode's block",
          isinstance(rf.get("transcript"), list) and len(rf["transcript"]) == 12
          and len(rf["transcript"][0]) == 2)

    print("\n--- sample fullhist prompt (first 700 chars of step 0) ---")
    print(pf[0]["user"][:700])
    print("--- ... ---\n")

    print(f"{'ALL CHECKS PASSED' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


def run_episode_fullhist(mod, block, max_steps=12):
    sink = []
    rec = mod.episode(FakeEnv(), FakeClient(sink), "fake-model", max_steps,
                      block, 2048, True, random.Random(SEED),
                      memory_header=mod.FULLHIST_HEADER, keep_transcript=True)
    return sink, rec


if __name__ == "__main__":
    sys.exit(main())
