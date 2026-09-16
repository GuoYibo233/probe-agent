#!/usr/bin/env python3
"""demo/prepare.py -- builds two fake artifacts for the debugger demo: a very small dataset and
a very small model.

The training code that actually matters is pipeline/train/train_causal_share.py (the
cache-reuse trainer shared by the cgen / cparam cells); that file is not touched at all. The
trainer already leaves two doors open: `--base <model dir>` goes through build(path=...) to
load a model from any directory, and `--device cpu` skips the GPU. This script's only job is to
swap in fakes behind those two doors that finish in a few seconds on CPU:

1. demo/data/{train,val}.jsonl: synthetic AppWorld-style annotated samples. The fields match
   the real data produced by pipeline/annotate/build.py field for field (text / label / w /
   depth / sent_idx / n_sents / event / traj / unit / model / step / label_call /
   args_named). Cuts use rules.boundaries, the prompt uses rules.assemble, and the call string
   uses build.make_call -- all three are the same functions as the real pipeline; only the
   trajectory content is made up.
2. demo/tiny_qwen3/: a randomly-initialized 2-layer Qwen3 (hidden 64), structurally the same
   family as the real base model. The tokenizer is the real Qwen3-0.6B-Base tokenizer (copied
   in from NFS). The vocab size is set to len(tok): the real tokenizer produces token ids up to
   150,000, and a smaller vocab would make the embedding index out of range.

Per the CLAUDE.md hard rule, large outputs go straight to the net drive: this script first
turns demo/tiny_qwen3 and demo/runs into symlinks pointing at the same-named directories under
the net-drive mirror directory (--net-root), the same approach used for pipeline/data and
pipeline/runs -- home keeps only the code, the data jsonl files, and the symlinks.

After it finishes, the script loads both datasets itself with share_data.load_events, once
each for cgen / cparam, and prints each event's full-text token count, concatenated length, and
line count; it then prints, per --tok-budget, how many physical chunks each logical epoch-0
minibatch splits into -- these are the layers most worth setting a breakpoint in during the
training loop.

Usage:
  CUDA_VISIBLE_DEVICES= cprobe-env/bin/python demo/prepare.py
  python3 run.py demo-prep            # same thing, through the registry
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/annotate"))
sys.path.insert(0, str(ROOT / "pipeline/train"))

import rules                                   # noqa: E402  sole source of truth for cuts / prompts
from build import make_call                    # noqa: E402  sole source of truth for the call string

DEFAULT_SEED = 20260907
# net-drive mirror directory (CLAUDE.md: large outputs go under /net/.../reproduce/new1/,
# mirroring this directory's structure)
NET_DEMO = Path("/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/demo")
# these two directories are large outputs (the small model is 54 MB, each training run's
# output is about 55 MB) -- turn them into symlinks onto the net drive
NET_LINKED = ("tiny_qwen3", "runs")


def link_to_net(name, net_root):
    """Turn demo/<name> into a symlink pointing at net_root/<name>. If it is already a symlink,
    just make sure the target directory exists; if it is a real directory, hard-stop instead of
    moving things for the user (everything inside it can be rebuilt anyway)."""
    link = ROOT / "demo" / name
    target = net_root / name
    if link.is_symlink():
        link.resolve().mkdir(parents=True, exist_ok=True)
        return link, link.resolve()
    if link.exists():
        raise SystemExit(
            f"{link} is a real directory, not a symlink. Per the CLAUDE.md hard rule, large outputs must go to the net drive:"
            f"first delete or move this directory (its contents can all be rebuilt by this script), then rerun this script.")
    target.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return link, target

# ---------------------------------------------------------------- material for composing trajectories
# Tool names and argument names are made up in the style of AppWorld; argument values carry no
# quotes, matching the real data (in the real data, `args_named` has the shape
# [{'key': 'app_name', 'value': 'phone'}], and make_call assembles it into
# `apis.api_docs.show_api_descriptions(app_name=phone)`).
TOOLS = [
    ("apis.api_docs.show_app_descriptions", []),
    ("apis.api_docs.show_api_descriptions", [("app_name", "phone")]),
    ("apis.supervisor.show_profile", []),
    ("apis.phone.search_contacts", [("query", "family")]),
    ("apis.phone.send_message", [("phone_number", "555-0134"),
                                 ("message", "Please get on venmo.")]),
    ("apis.venmo.show_account", []),
    ("apis.todoist.show_tasks", [("status", "pending")]),
    ("apis.gmail.search_emails", [("query", "invoice"), ("page_limit", "5")]),
    ("apis.spotify.play_song", [("song_id", "17")]),
    ("apis.file_system.show_directory", [("path", "/home/user")]),
]

TASKS = [
    "Send the following phone message to my parents and siblings, who do not "
    "have a venmo account, \"Please get on venmo.\".",
    "Show me the pending tasks on my todo list.",
    "Play the song I listened to most last week on Spotify.",
    "Find the invoice emails from last month and tell me the total amount.",
    "List the files in my home directory.",
    "Check how much money is in my venmo account.",
    "What is my supervisor's phone number?",
    "Look up which apps are available on this phone.",
]

HISTORY_ROUNDS = [
    ("apis.api_docs.show_app_descriptions()",
     "[{'name': 'phone', 'description': 'A phone app for calls, messages and "
     "contacts.'}, {'name': 'venmo', 'description': 'A payment app.'}, "
     "{'name': 'todoist', 'description': 'A todo list app.'}]"),
    ("apis.supervisor.show_profile()",
     "{'first_name': 'Ava', 'last_name': 'Kim', 'phone_number': '555-0100', "
     "'email': 'ava.kim@example.com'}"),
    ("apis.api_docs.show_api_descriptions(app_name=phone)",
     "[{'name': 'search_contacts', 'description': 'Search contacts by "
     "relationship or name.'}, {'name': 'send_message', 'description': "
     "'Send a text message to a phone number.'}]"),
    ("apis.phone.search_contacts(query=family)",
     "[{'name': 'Mom', 'phone_number': '555-0134'}, {'name': 'Dad', "
     "'phone_number': '555-0135'}, {'name': 'Liam', 'phone_number': "
     "'555-0136'}]"),
]

# Templates for thinking sentences. The three slots {task} / {app} / {tool} are filled by rng.
# The first sentence restates the task the way the real data does, the last sentence names the
# tool to call, and the middle ones are drawn from a pool.
FIRST_SENTENCE = "The user asks: \"Task from supervisor: {task}\""
LAST_SENTENCE = "So the next call is {tool}."
MIDDLE_SENTENCES = [
    "We need to be an autonomous agent operating a phone-like environment on "
    "behalf of the supervisor.",
    "First we should look at the list of apps to see which ones are relevant.",
    "The task mentions the {app} app, so that app is the natural starting point.",
    "Before calling anything we need the exact API name and its parameters.",
    "Let's check the documentation for the {app} app.",
    "We already know the supervisor's profile, so the next step is the {app} app.",
    "The result of that call will tell us what to do next.",
    "There is no need to ask the supervisor for clarification here.",
    "The history shows we have not called the {app} app yet.",
    "Each API returns JSON, so we can parse the fields directly.",
]


def _synth_event(rng, idx, n_sents):
    """Compose one event: one task, zero to two turns of history, an n_sents-sentence thinking
    passage, and one tool."""
    task = rng.choice(TASKS)
    tool, named = rng.choice(TOOLS)
    app = tool.split(".")[1]
    n_hist = rng.choice([0, 1, 1, 2])
    hist = HISTORY_ROUNDS[:n_hist]
    middle = rng.sample(MIDDLE_SENTENCES, k=max(n_sents - 2, 0))
    sents = ([FIRST_SENTENCE.format(task=task)]
             + [s.format(app=app) for s in middle]
             + [LAST_SENTENCE.format(tool=tool)])
    # A newline follows the first sentence (in the real data a newline follows the task-restating
    # sentence too); the remaining sentences are joined with spaces. rules.SENT_RE recognizes both
    # separators, so the number of lines after cutting equals the number of sentences.
    think = sents[0] + "\n" + " ".join(sents[1:])
    unit = f"demo{idx:02d}_1"
    traj = f"appworld_demo/appworld_{unit}_r0"
    return dict(task=task, hist=hist, think=think, tool=tool,
                named=[dict(key=k, value=v) for k, v in named],
                traj=traj, unit=unit, model="demo", step=n_hist)


def make_rows(events):
    """Event -> sample row. Field for field, following make_samples in pipeline/annotate/build.py
    (w = 1/m, where m is this event's number of cuts; depth is the cut's position ratio within
    the full thinking text)."""
    rows = []
    for ev in events:
        pts = rules.boundaries(ev["think"])
        m = len(pts)
        w = round(1.0 / m, 6)
        label_call = make_call(ev["tool"], ev["named"])
        for si, cut in enumerate(pts):
            rows.append(dict(
                text=rules.assemble(ev["task"], ev["hist"], ev["think"][:cut]),
                label=ev["tool"], w=w,
                depth=round(cut / len(ev["think"]), 4),
                sent_idx=si, n_sents=m,
                event=f"{ev['traj']}|s{ev['step']}",
                traj=ev["traj"], unit=ev["unit"], model=ev["model"],
                step=ev["step"], label_call=label_call,
                args_named=ev["named"]))
    return rows


def write_data(out_dir, seed, n_train, n_val):
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    written = {}
    idx = 0
    for split, n in (("train", n_train), ("val", n_val)):
        events = []
        for _ in range(n):
            n_sents = rng.randint(3, 7)
            events.append(_synth_event(rng, idx, n_sents))
            idx += 1
        rows = make_rows(events)
        path = out_dir / f"{split}.jsonl"
        with open(path, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        written[split] = (len(events), len(rows))
    return written


def write_model(out_dir, tok_src, seed):
    """A randomly-initialized 2-layer Qwen3 plus the real tokenizer, saved as a directory that
    from_pretrained can load directly."""
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(tok_src)
    special = {}
    for name in ("bos_token_id", "eos_token_id", "pad_token_id"):
        val = getattr(tok, name)
        if val is not None:
            special[name] = val
    # Structure follows _tiny_config in tests/test_share_trainer.py; tie_word_embeddings is
    # changed to True, matching the real base model's Qwen3-0.6B-Base config.json.
    cfg = transformers.Qwen3Config(
        hidden_size=64, intermediate_size=128, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        vocab_size=len(tok), max_position_embeddings=8192,
        tie_word_embeddings=True, rope_theta=1000000, **special)
    torch.manual_seed(seed)
    model = AutoModelForCausalLM.from_config(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    n_params = sum(p.numel() for p in model.parameters())
    return n_params, len(tok)


def self_check(data_dir, model_dir, tok_budget, events_per_mb):
    """Load the fakes once through the functions the trainer actually calls: build(path=...) loads
    the model, share_data.load_events loads the data, and chunk_by_budget checks the
    chunking."""
    import share_data
    import train_causal_callgen

    tok, model, base_path = train_causal_callgen.build(
        "cpu", attn_impl="sdpa", path=str(model_dir))
    print(f"[model] build(path={base_path}) ok: "
          f"{sum(p.numel() for p in model.parameters())} params, "
          f"{model.config.num_hidden_layers} layers, hidden {model.config.hidden_size}")
    for mode in ("cgen", "cparam"):
        for split in ("train", "val"):
            events, counts = share_data.load_events(
                data_dir / f"{split}.jsonl", tok, mode, max_len=8192, limit=0)
            print(f"[{mode}/{split}] {len(events)} events, {counts['n_rows']} rows, "
                  f"dropped_events={counts['dropped_events']} "
                  f"dropped_rows_tgt={counts['dropped_rows_tgt']} "
                  f"assembly_mismatch={counts['assembly_mismatch']}")
            for ev in events:
                print(f"    {ev['event']:<44} n_full={ev['n_full']:>4} "
                      f"prefix_len={ev['prefix_len']:>4} "
                      f"packed_len={ev['packed_len']:>4} rows={len(ev['rows'])}")
            if split == "train":
                mbs = share_data.epoch_minibatches(
                    events, train_causal_callgen.SEED, 0, events_per_mb)
                splits = [len(share_data.chunk_by_budget(mb, tok_budget))
                          for mb in mbs]
                print(f"    epoch 0: {len(mbs)} logical minibatches of "
                      f"{events_per_mb} events; blocks per minibatch at "
                      f"--tok-budget {tok_budget}: {splits}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-data", default=str(ROOT / "demo/data"))
    ap.add_argument("--out-model", default=str(ROOT / "demo/tiny_qwen3"))
    ap.add_argument("--tok-src", default=None,
                    help="dir where the real tokenizer lives, default train_causal_callgen.MODELS['qwen']")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n-train", type=int, default=12)
    ap.add_argument("--n-val", type=int, default=6)
    ap.add_argument("--tok-budget", type=int, default=768,
                    help="print packing-block results at this budget during self-check (matches the value in launch.json)")
    ap.add_argument("--events-per-mb", type=int, default=4)
    ap.add_argument("--skip-model", action="store_true",
                    help="rebuild data only, don't touch demo/tiny_qwen3")
    ap.add_argument("--net-root", default=str(NET_DEMO),
                    help="the net-drive dir that demo/tiny_qwen3 and demo/runs symlinks point to")
    args = ap.parse_args()

    data_dir = Path(args.out_data)
    model_dir = Path(args.out_model)

    for name in NET_LINKED:
        link, target = link_to_net(name, Path(args.net_root))
        print(f"[net] {link.relative_to(ROOT)} -> {target}")

    written = write_data(data_dir, args.seed, args.n_train, args.n_val)
    for split, (n_ev, n_rows) in written.items():
        print(f"[data] {data_dir / (split + '.jsonl')}: {n_ev} events, {n_rows} rows")

    if args.skip_model:
        print("[model] --skip-model: demo/tiny_qwen3 untouched")
    else:
        import train_causal_callgen
        tok_src = args.tok_src or train_causal_callgen.MODELS["qwen"]
        if not Path(tok_src).exists():
            raise SystemExit(f"tokenizer dir doesn't exist: {tok_src} (NFS not mounted? or use "
                             "--tok-src to point at a different Qwen3 dir)")
        n_params, vocab = write_model(model_dir, tok_src, args.seed)
        print(f"[model] {model_dir}: {n_params} params, vocab {vocab}, "
              f"tokenizer copied from {tok_src}")

    self_check(data_dir, model_dir, args.tok_budget, args.events_per_mb)


if __name__ == "__main__":
    main()
