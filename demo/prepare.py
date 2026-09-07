#!/usr/bin/env python3
"""demo/prepare.py —— 给 debugger 演示构建两样假件:一份很小的数据集,一个很小的模型。

真正要看的训练代码是 pipeline/train/train_causal_share.py(cgen / cparam 两格
共用的缓存复用训练器),那个文件一个字都不改。训练器本来就留了两扇门:
`--base <模型目录>` 走 build(path=...) 加载任意目录里的模型,`--device cpu`
不碰显卡。本脚本只负责把这两扇门后面的东西换成 CPU 上几秒钟就能跑完的假件:

1. demo/data/{train,val}.jsonl:合成的 AppWorld 风格标注样本。字段与
   pipeline/annotate/build.py 产出的真数据逐个相同(text / label / w / depth /
   sent_idx / n_sents / event / traj / unit / model / step / label_call /
   args_named)。切点用 rules.boundaries,题干用 rules.assemble,调用串用
   build.make_call,三个都是真流水线的同一份函数;只有轨迹内容是编写的。
2. demo/tiny_qwen3/:随机初始化的两层 Qwen3(hidden 64),结构与真底座同族,
   分词器是真 Qwen3-0.6B-Base 的分词器(从 NFS 拷贝一份进来)。词表大小取
   len(tok):真分词器分出来的 token id 最高到十五万,词表开小了 embedding
   会越界。

大产物按 CLAUDE.md 的铁律直接写 net 盘:本脚本先把 demo/tiny_qwen3 与
demo/runs 做成指向 net 盘镜像目录(--net-root)下同名目录的软链,与
pipeline/data、pipeline/runs 同一个做法,home 里只留代码、数据 jsonl 与软链。

跑完之后脚本自己用 share_data.load_events 把两份数据各按 cgen / cparam 加载
一遍,把每个事件的全文 token 数、拼接长度、行数打印出来,再按 --tok-budget
打印一下 epoch 0 的每个逻辑小批会切成几个物理块:训练循环里最值得下断点的
地方就是这几层。

用法:
  CUDA_VISIBLE_DEVICES= cprobe-env/bin/python demo/prepare.py
  python3 run.py demo-prep            # 同一件事,走注册表
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline/annotate"))
sys.path.insert(0, str(ROOT / "pipeline/train"))

import rules                                   # noqa: E402  切点 / 题干的唯一真源
from build import make_call                    # noqa: E402  调用串的唯一真源

DEFAULT_SEED = 20260907
# net 盘镜像目录(CLAUDE.md:大产物落 /net/.../reproduce/new1/ 下镜像本目录结构)
NET_DEMO = Path("/net/tokyo100-10g/data/str01_01/y-guo/reproduce/new1/demo")
# 这两个目录是大产物(小模型 54 MB,每次训练产物约 55 MB),做成软链落 net 盘
NET_LINKED = ("tiny_qwen3", "runs")


def link_to_net(name, net_root):
    """demo/<name> 做成指向 net_root/<name> 的软链。已经是软链就只保证目标目录
    存在;是实体目录就硬停,不替用户搬东西(里面的内容都能重新构建)。"""
    link = ROOT / "demo" / name
    target = net_root / name
    if link.is_symlink():
        link.resolve().mkdir(parents=True, exist_ok=True)
        return link, link.resolve()
    if link.exists():
        raise SystemExit(
            f"{link} 是实体目录,不是软链。按 CLAUDE.md 铁律大产物要落 net 盘:"
            f"先把这个目录删掉或者挪走(内容都能用本脚本重新构建),再跑本脚本。")
    target.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return link, target

# ---------------------------------------------------------------- 编轨迹用的素材
# 工具名与保名参数都照 AppWorld 的样子编;参数 value 不带引号,与真数据一致
# (真数据里 `args_named` 是 [{'key': 'app_name', 'value': 'phone'}] 这种形状,
# make_call 拼出来就是 `apis.api_docs.show_api_descriptions(app_name=phone)`)。
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

# 思考句的模板。{task} / {app} / {tool} 三个槽位由 rng 填。第一句照真数据的
# 样子转述任务,最后一句点名要调的工具;中间从池子里抽。
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
    """编一个事件:一条任务、零到两轮历史、一段 n_sents 句的思考、一个工具。"""
    task = rng.choice(TASKS)
    tool, named = rng.choice(TOOLS)
    app = tool.split(".")[1]
    n_hist = rng.choice([0, 1, 1, 2])
    hist = HISTORY_ROUNDS[:n_hist]
    middle = rng.sample(MIDDLE_SENTENCES, k=max(n_sents - 2, 0))
    sents = ([FIRST_SENTENCE.format(task=task)]
             + [s.format(app=app) for s in middle]
             + [LAST_SENTENCE.format(tool=tool)])
    # 第一句后面换行(真数据里任务转述句后面就是换行),其余句子空格相接;
    # rules.SENT_RE 两种分隔都认,切出来的行数 = 句数。
    think = sents[0] + "\n" + " ".join(sents[1:])
    unit = f"demo{idx:02d}_1"
    traj = f"appworld_demo/appworld_{unit}_r0"
    return dict(task=task, hist=hist, think=think, tool=tool,
                named=[dict(key=k, value=v) for k, v in named],
                traj=traj, unit=unit, model="demo", step=n_hist)


def make_rows(events):
    """事件 -> 样本行。逐字段照 pipeline/annotate/build.py 的 make_samples
    (w = 1/m,m 是这个事件的切点数;depth 是切点在思考全文里的位置比例)。"""
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
    """两层 Qwen3 随机初始化 + 真分词器,存成 from_pretrained 能直接装的目录。"""
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(tok_src)
    special = {}
    for name in ("bos_token_id", "eos_token_id", "pad_token_id"):
        val = getattr(tok, name)
        if val is not None:
            special[name] = val
    # 结构照 tests/test_share_trainer.py 的 _tiny_config;tie_word_embeddings
    # 改成 True,与真底座 Qwen3-0.6B-Base 的 config.json 一致。
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
    """用训练器真正会走的函数把假件装一遍:build(path=...) 装模型,
    share_data.load_events 装数据,chunk_by_budget 看装块。"""
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
                    help="真分词器所在目录,缺省 train_causal_callgen.MODELS['qwen']")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n-train", type=int, default=12)
    ap.add_argument("--n-val", type=int, default=6)
    ap.add_argument("--tok-budget", type=int, default=768,
                    help="自检时按这个预算印装块结果(与 launch.json 里的值一致)")
    ap.add_argument("--events-per-mb", type=int, default=4)
    ap.add_argument("--skip-model", action="store_true",
                    help="只重新构建数据,不动 demo/tiny_qwen3")
    ap.add_argument("--net-root", default=str(NET_DEMO),
                    help="demo/tiny_qwen3 与 demo/runs 软链指向的 net 盘目录")
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
        print("[model] --skip-model: demo/tiny_qwen3 未动")
    else:
        import train_causal_callgen
        tok_src = args.tok_src or train_causal_callgen.MODELS["qwen"]
        if not Path(tok_src).exists():
            raise SystemExit(f"分词器目录不存在:{tok_src}(NFS 没挂?或者用 "
                             "--tok-src 指一个别的 Qwen3 目录)")
        n_params, vocab = write_model(model_dir, tok_src, args.seed)
        print(f"[model] {model_dir}: {n_params} params, vocab {vocab}, "
              f"tokenizer copied from {tok_src}")

    self_check(data_dir, model_dir, args.tok_budget, args.events_per_mb)


if __name__ == "__main__":
    main()
