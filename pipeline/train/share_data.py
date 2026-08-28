"""share_data.py —— cgen / cparam 共用的纯 CPU 数据与分词模块。

给谁用:
- `train_causal_share.py`(工单 03,新训练器,cgen/cparam 两格共用)
- `train_causal_tool.py` / `pipeline/eval/eval_tool.py`(工单 02,只用
  `read_position` 一个函数;`eval_tool.py` 要在 mbert-env 下 import 本模块)

模块顶层只许 stdlib 与 torch:两个旧训练器(`train_causal_callgen.py`、
`train_causal_param.py`)模块层有 transformers >= 5.14 的版本门,mbert-env
(transformers 4.57.6)下顶层 import 会 `raise SystemExit`,而 `eval_tool.py`
在 mbert-env 下也要 import 本模块拿 `read_position`。所以对两个旧脚本
(以及 `pipeline/annotate/rules.py`,同一条纪律)的 import 一律延迟到
`load_events` 函数体内,`read_position` 不碰任何训练脚本。

规则来源:`.scratch/kvshare-train/spec.md` 第 2、3、4、5、11.3 节。
"""
import json
import random
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent

# 右 pad 用的占位 token id。pad 行只在 batch_mask 里当 query 看自己(spec
# 第 4 节:整行不可看会让 softmax 出 NaN),从不参与损失、也不会被任何真实
# token 看到,所以这个 id 具体取什么值不影响任何真实输出,0 对任何词表都合法。
PAD_TOKEN_ID = 0


def _lazy_imports():
    """延迟 import 两个旧训练脚本的常量/函数,以及 `rules.MAX_BOUNDS`。

    两个旧脚本模块顶层有 transformers >= 5.14 的版本门,mbert-env 下顶层
    import 会 `SystemExit`;这个函数只在真正要用它们的地方(`load_events`)
    调用,不在 `share_data.py` 模块顶层碰它们(spec 3.3)。
    """
    train_dir = str(_HERE)
    if train_dir not in sys.path:
        sys.path.insert(0, train_dir)
    annotate_dir = str(_HERE.parent / "annotate")
    if annotate_dir not in sys.path:
        sys.path.insert(0, annotate_dir)
    import train_causal_callgen as cgen_mod
    import train_causal_param as cparam_mod
    from rules import MAX_BOUNDS
    return cgen_mod, cparam_mod, MAX_BOUNDS


def _lcp(a, b):
    """`a`、`b` 的最长公共前缀长度(逐 token 比到第一个不同处)。"""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _pad16(n):
    """把 `n` 向上补到 16 的倍数,和 `batch_mask` 的 `L_pad` 补齐同口径。

    `chunk_by_budget`/`worst_blocks` 的预算判据都要用这个补齐后的长度
    (spec 第 5 节;工单第 1 条:『chunk_by_budget 的预算判据同样用
    L_pad』),不是补齐前的 `packed_len`——真实显存/算力看的是 `batch_mask`
    补齐之后的物理块长度。
    """
    return ((n + 15) // 16) * 16


def full_token_ids(tok, full_text):
    """事件全文分词,唯一算法源(spec 16.2):`load_events` 装 `e["full_ids"]`、
    三个评测脚本的 `drop-event` 判据都调这个函数或下面的 `n_full_tokens`,
    分词只有一份真源。`add_special_tokens=False, truncation=False`——不截断,
    要的是全文真实 token 数。
    """
    return tok(full_text, add_special_tokens=False,
              truncation=False)["input_ids"]


def n_full_tokens(tok, full_text):
    """`full_token_ids` 只要长度时的薄封装(评测端的 `drop-event` 判据只要计数,
    不需要 `full_ids` 本身)。"""
    return len(full_token_ids(tok, full_text))


def event_full_texts(rows):
    """按 event 分组,取每组 `sent_idx` 最大那一行的 `text`(spec 16.2)。

    只给评测端的 `--overlong drop-event` 用:不过滤行,不动 `load_events`
    里 `events_all.append(dict(...))` 那段分组——那段钉着 3.2 节的随机数
    消耗顺序,这个函数是给评测端另起的一份、跟训练侧的抽样顺序无关。

    `rows`:一批原始行 dict(至少含 `event`、`sent_idx`、`text`)。
    -> dict[event] -> full_text
    """
    groups = {}
    for r in rows:
        groups.setdefault(r["event"], []).append(r)
    return {ev: max(rs, key=lambda r: r["sent_idx"])["text"]
           for ev, rs in groups.items()}


def select_keys(mode, keys, n_full, prompt_len, excluded_rows, max_len, max_new):
    """按 `--overlong` 与 ctool 的行剔除筛选一批 key(事件)(spec 16.2)。

    `mode`:"left" / "skip" / "drop-event"。
    `keys`:`dict[key] -> list[int]`,每个 key 的候选行下标列表——该事件在
        ctool 的 `rows`/`logits_test.pt` 里对应的全部行下标。这份列表只用来
        判"ctool 剔除之后这个 key 还有没有候选行",跟 `mode` 的筛选逻辑
        (下面用 `n_full`/`prompt_len`)彼此独立。
    `n_full`:`dict[key] -> int`,事件全文 token 数(只有 `mode="drop-event"`
        时用得到;别的 mode 可以传空字典)。
    `prompt_len`:`dict[key] -> int`,`L(k)`——提示 token 数(cparam 传两套
        提示长度的最大值;`left`/`skip`/`drop-event` 三种 mode 都只用这一个
        数判"提示是否超长")。
    `excluded_rows`:`set[int]`,ctool 传来的剔除行下标集合(`rows`/`logits`
        位置,`logits_test.meta.json` 的 `excluded_idx`)。
    `max_len`、`max_new`:int。

    -> (kept_keys: list[key], counts: dict(n_left_truncated, n_skipped_rows,
        n_dropped_events, n_excluded_by_ctool))

    四个判据的顺序对每个 key 写死:先看 ctool 剔除(候选行剔光就整个 key
    不判分,计 `n_excluded_by_ctool`,不再看下面的 mode 判据),再按 `mode`
    走 `drop-event`(事件全文超长整个丢,计 `n_dropped_events`)或 `skip`
    (提示超长整行不进,计 `n_skipped_rows`)或都不丢时的『提示仍超长』
    (`left` 与 `drop-event` 都计 `n_left_truncated`,`skip` 不会走到这里,
    因为提示超长的行已经在上一步被剔掉)。
    """
    if mode not in ("left", "skip", "drop-event"):
        raise ValueError(
            f"select_keys: mode 只支持 left/skip/drop-event,拿到 {mode!r}")
    thresh = max_len - max_new
    kept = []
    counts = dict(n_left_truncated=0, n_skipped_rows=0,
                 n_dropped_events=0, n_excluded_by_ctool=0)
    for k in keys:
        if all(i in excluded_rows for i in keys[k]):
            counts["n_excluded_by_ctool"] += 1
            continue
        if mode == "drop-event" and n_full[k] > max_len:
            counts["n_dropped_events"] += 1
            continue
        if prompt_len[k] > thresh:
            if mode == "skip":
                counts["n_skipped_rows"] += 1
                continue
            counts["n_left_truncated"] += 1
        kept.append(k)
    return kept, counts


# ---------------------------------------------------------------- 数据与分词

def load_events(path, tok, mode, max_len, ro=None, limit=0, order="random"):
    """装载一个 split(`train.jsonl` 或 `val.jsonl`),按 spec 3.2~3.5。

    各步顺序写死(随机数发生器的消耗顺序决定抽样结果,spec 3.2):
    分组 -> 前缀性质抽查(对丢弃之前的全部事件)-> 每个事件全文分词得到
    `n_full`,按丢弃规则丢事件级超长事件 -> 按 `limit`/`order` 取子集 ->
    只对留下的事件做逐行分词与行级丢弃。

    `mode` = "cgen":目标串 = `tok(label_call) + [eos]`,尾巴 = `CALL_SEP`。
    `mode` = "cparam":目标串 = `param_target(label, label_call) + [eos]`,
    尾巴 = `param_prompt_tail(label)`,`param_target` 返回 None 的行整条
    丢弃并计 `assembly_mismatch`。

    `ro` 非 None 时(`--readonly-env`)非只读的行整条丢弃,计数记在 `ro`
    里(`ro` = dict(set=.., labels=[], kept=0, dropped=0),口径照
    `CallDS`/`ParamDS` 的 readonly 分支)。

    `limit > 0` 时按 `order` 从丢弃超长事件之后的事件里取前 `limit` 个:
    "random" 用一个新建的 `random.Random(SEED)` 打乱后取前 limit 个;
    "shortest" 按 `n_full` 升序取前 limit 个。取完之后按文件里首次出现的
    顺序重新排列(返回顺序的保序契约不因取子集的方式而改变)。

    返回 `(events, counts)`:
    - `events`:列表,每个事件是 `dict(event, n_full, packed_len,
      prefix_len, full_ids, rows)`,`rows` = `[(sent_idx, text, p, seg_ids,
      seg_lab, w, gen), ...]`(第 6 位 `gen` = `dict(tgt=<目标串>,
      tool=<工具名或 None>)`,给 `train_causal_share.py` 的 `--gen-eval`
      生成式评估用,spec 16.3、工单 08)。事件顺序 = 文件里首次出现的顺序;行顺序 =
      `sent_idx` 升序 —— 这两条保序是契约,对齐检查靠它按位置配对。
      `full_ids`(事件全文分词结果)与 `packed_len`/`prefix_len`(拼接
      序列长度、公共前缀上界 P = max_k p_k)是给 `pack_event` 用的。
    - `counts`:`dict(dropped_events, dropped_rows_tgt, assembly_mismatch,
      n_rows)`。

    两道硬停(照 `train_causal_param.py` 第 337~353 行搬):这个 split 装载
    后 0 行就退出;`mode="cparam"` 时剥离失败率(`assembly_mismatch` 占比)
    超过 `train_causal_param.ASSEMBLY_MISMATCH_LIMIT` 也退出。
    """
    if mode not in ("cgen", "cparam"):
        raise ValueError(f"load_events: mode 只支持 cgen/cparam,拿到 {mode!r}")
    if order not in ("random", "shortest"):
        raise ValueError(f"load_events: order 只支持 random/shortest,拿到 {order!r}")

    cgen_mod, cparam_mod, MAX_BOUNDS = _lazy_imports()
    SEED = cgen_mod.SEED               # cgen/cparam 的 SEED 值相同(42)
    MAX_TGT_TOK = cgen_mod.MAX_TGT_TOK if mode == "cgen" else cparam_mod.MAX_TGT_TOK

    # ---- 分组:事件顺序 = 文件里首次出现的顺序,组内按 sent_idx 升序 ----
    groups = {}
    order_list = []
    for line in open(path):
        r = json.loads(line)
        ev_id = r["event"]
        if ev_id not in groups:
            groups[ev_id] = []
            order_list.append(ev_id)
        groups[ev_id].append(r)
    events_all = []
    for idx, ev_id in enumerate(order_list):
        rs = sorted(groups[ev_id], key=lambda r: r["sent_idx"])
        events_all.append(dict(event=ev_id, orig_idx=idx,
                               full_text=rs[-1]["text"], rows_raw=rs))

    # ---- 前缀性质抽查(对丢弃之前的全部事件,SEED 固定) ----
    rng_spot = random.Random(SEED)
    for e in rng_spot.sample(events_all, min(50, len(events_all))):
        assert all(e["full_text"].startswith(r["text"]) for r in e["rows_raw"]), \
            f"事件 {e['event']} 的样本 text 不互为前缀"

    # ---- 每个事件全文分词得到 n_full,按丢弃规则丢事件级超长事件 ----
    # 判据只看事件全文的 token 数,不看拼接序列长度(拼接序列由 token 预算
    # 兜底)。
    dropped_events = 0
    events_kept = []
    for e in events_all:
        full_ids = full_token_ids(tok, e["full_text"])
        if len(full_ids) > max_len:
            dropped_events += 1
            continue
        e["full_ids"] = full_ids
        e["n_full"] = len(full_ids)
        events_kept.append(e)

    # ---- 按 limit/order 取子集,取完恢复文件序 ----
    if limit and limit > 0:
        if order == "random":
            rng = random.Random(SEED)
            rng.shuffle(events_kept)
            events_kept = events_kept[:limit]
        else:                                          # "shortest"
            events_kept = sorted(events_kept, key=lambda e: e["n_full"])[:limit]
        events_kept.sort(key=lambda e: e["orig_idx"])

    # ---- 只对留下的事件做逐行分词与行级丢弃 ----
    dropped_rows_tgt = 0
    assembly_mismatch = 0
    n_rows = 0
    events = []
    for e in events_kept:
        rows = []
        for r in e["rows_raw"]:
            if ro is not None:
                ro["labels"].append(r["label"])
                if r["label"] not in ro["set"]:
                    ro["dropped"] += 1
                    continue
                ro["kept"] += 1
            if mode == "cgen":
                tail = cgen_mod.CALL_SEP
                tgt_str = r["label_call"]
                tool = None
                tgt_ids = tok(tgt_str,
                             add_special_tokens=False)["input_ids"]
                tgt_ids = tgt_ids + [tok.eos_token_id]
            else:
                tail = cparam_mod.param_prompt_tail(r["label"])
                tgt_str = cparam_mod.param_target(r["label"], r["label_call"])
                if tgt_str is None:
                    assembly_mismatch += 1
                    continue
                tool = r["label"]
                tgt_ids = tok(tgt_str, add_special_tokens=False)["input_ids"]
                tgt_ids = tgt_ids + [tok.eos_token_id]
            if len(tgt_ids) > MAX_TGT_TOK:
                dropped_rows_tgt += 1
                continue
            old_ids = tok(r["text"] + tail, add_special_tokens=False,
                          truncation=False)["input_ids"]
            p = _lcp(old_ids, e["full_ids"])
            tail_ids = old_ids[p:]
            assert len(tail_ids) >= 1, (
                f"事件 {e['event']} sent_idx={r['sent_idx']}: 公共前缀 p={p} "
                f"吃掉了整条尾巴(len(old_ids)={len(old_ids)})——分隔串跟"
                "全文延续撞车了,查 tokenizer 版本。")
            seg_ids = tail_ids + tgt_ids
            seg_lab = [-100] * len(tail_ids) + tgt_ids
            gen = dict(tgt=tgt_str, tool=tool)
            rows.append((r["sent_idx"], r["text"], p, seg_ids, seg_lab,
                        float(r["w"]), gen))
            n_rows += 1
        if not rows:
            # 这个事件的全部行都在行级丢弃(readonly/tgt 过长/mismatch)里
            # 丢光了,事件本身没有任何训练信号,不进返回列表——它的行已经
            # 分别记进 dropped_rows_tgt/assembly_mismatch/ro 里了,这里不用
            # 再单独计数(dropped_events 专属"事件全文过长"那一条判据)。
            continue
        prefix_len = max(row[2] for row in rows)
        packed_len = prefix_len + sum(len(row[3]) for row in rows)
        events.append(dict(event=e["event"], n_full=e["n_full"],
                           packed_len=packed_len, prefix_len=prefix_len,
                           full_ids=e["full_ids"], rows=rows))

    # ---- 两道硬停(照 train_causal_param.py 第 337~353 行搬) ----
    if n_rows == 0:
        raise SystemExit(
            f"{path} 装载后是 0 行(dropped_events={dropped_events}, "
            f"dropped_rows_tgt={dropped_rows_tgt}, "
            f"assembly_mismatch={assembly_mismatch})——"
            "选 best 的指标没有分母,硬停。")
    if mode == "cparam":
        tot = n_rows + assembly_mismatch
        limit_frac = cparam_mod.ASSEMBLY_MISMATCH_LIMIT
        if tot and assembly_mismatch / tot > limit_frac:
            raise SystemExit(
                f"{path} 的剥离失败率 {assembly_mismatch}/{tot} = "
                f"{assembly_mismatch / tot:.3f} 超过 {limit_frac}——"
                "上游拼串口径漂移,硬停。")

    # ---- 拼接长度上界断言(防 tokenizer 版本漂移把尾巴撑长) ----
    worst = max((e["packed_len"] for e in events), default=0)
    bound = max_len + MAX_BOUNDS * (MAX_TGT_TOK + 8)
    assert worst <= bound, (
        f"最长拼接序列 {worst} 超过上界 {bound}"
        f"(max_len={max_len}, MAX_BOUNDS={MAX_BOUNDS}, MAX_TGT_TOK={MAX_TGT_TOK})"
        "——tokenizer 版本漂移把尾巴撑长了,硬停。")

    counts = dict(dropped_events=dropped_events, dropped_rows_tgt=dropped_rows_tgt,
                 assembly_mismatch=assembly_mismatch, n_rows=n_rows)
    return events, counts


# ---------------------------------------------------------------- 前向形态

def pack_event(ev):
    """一个事件的拼接序列(spec 第 4 节):

    ```
    tokens    = full_ids[:P] + seg_1 + seg_2 + ... + seg_K   # P = max_k p_k
    positions = [0..P-1] + [p_1, p_1+1, ...] + [p_2, p_2+1, ...] + ...
    labels    = [-100]*P + seg_lab_1 + ... + seg_lab_K
    ```

    返回 `(tokens, positions, labels, row_index, seg_bounds)`,均为
    python list(torch 化留给 `batch_mask`,因为那里才定 batch 维与 pad
    长度):
    - `row_index[i]`:token i 属于第几行(`ev["rows"]` 的下标,0-based),
      前缀是 -1。
    - `seg_bounds[k]`:第 k 行的段在 `tokens` 里的 `[start, end)` 半开区间。
    """
    P = ev["prefix_len"]
    tokens = list(ev["full_ids"][:P])
    positions = list(range(P))
    labels = [-100] * P
    row_index = [-1] * P
    seg_bounds = []
    for k, row in enumerate(ev["rows"]):
        _sent_idx, _text, p, seg_ids, seg_lab, _w = row[:6]
        start = len(tokens)
        tokens.extend(seg_ids)
        positions.extend(range(p, p + len(seg_ids)))
        labels.extend(seg_lab)
        row_index.extend([k] * len(seg_ids))
        seg_bounds.append((start, len(tokens)))
    return tokens, positions, labels, row_index, seg_bounds


def _allowed_from_packed(positions, row_index, seg_bounds, L):
    """`allowed_mask`/`batch_mask` 共用的核心:[L, L] bool 张量(True=可看)。

    注意力允许关系(spec 第 4 节):前缀内部因果;第 k 段的第 i 个 token 可看
    前缀的前 p_k 个位置和本段的前 i+1 个 token;段与段之间互不可见;前缀
    看不到任何目标段。
    """
    row_t = torch.tensor(row_index, dtype=torch.long)
    idx = torch.arange(L)
    is_prefix = row_t < 0
    causal = idx.unsqueeze(0) <= idx.unsqueeze(1)          # [i, j] = (j <= i)

    qp = torch.zeros(L, dtype=torch.long)                  # 每个目标段位置的 p_k
    for start, end in seg_bounds:
        qp[start:end] = positions[start]

    prefix_prefix = is_prefix.unsqueeze(1) & is_prefix.unsqueeze(0) & causal
    same_row = row_t.unsqueeze(1) == row_t.unsqueeze(0)
    seg_self = same_row & (~is_prefix).unsqueeze(1) & causal
    seg_sees_prefix = ((~is_prefix).unsqueeze(1) & is_prefix.unsqueeze(0)
                       & (idx.unsqueeze(0) < qp.unsqueeze(1)))
    return prefix_prefix | seg_self | seg_sees_prefix


def allowed_mask(ev):
    """一个事件 `[L, L]` 的 bool 张量(True = 可看),按 spec 第 4 节。"""
    tokens, positions, labels, row_index, seg_bounds = pack_event(ev)
    return _allowed_from_packed(positions, row_index, seg_bounds, len(tokens))


def batch_mask(packed_list, L_pad):
    """把一个物理块的若干 `pack_event` 结果右 pad 到 `L_pad`(16 的倍数)。

    `packed_list`:`[pack_event(ev), ...]`,调用方已经对块内每个事件跑过
    `pack_event`。

    返回 `(input_ids, position_ids, mask, loss_idx)`:
    - `input_ids`:`[B, L_pad]` long;pad 位置是 `PAD_TOKEN_ID`(pad 行只看
      自己,这个值不影响任何真实 token 的输出)。
    - `position_ids`:`[B, L_pad]` long;pad 位置从这一事件最后一个真实
      位置接着数(spec 第 4 节:『补到 16 的 pad 位也要给 position_ids
      〔接着数〕』),不是写死 0。
    - `mask`:`[B, 1, L_pad, L_pad]` bf16 加性掩码(可看 0、不可看 -inf);
      pad 作为 query 的行只让 pad 看自己(整行不可看会让 softmax 出 NaN,
      真实 token 看不到 pad)。
    - `loss_idx`:`[(batch_idx, qpos, target_id, row_idx), ...]`。用
      `labels` 数组本身取值(不移位 labels):`labels[t] != -100` 的目标
      token 由 logits 在位置 `t-1` 算出,所以 query 位置是 `t-1`、目标 id
      是 `labels[t]`、行号是 `row_index[t]`。pad 位置不产生任何 `loss_idx`
      条目(pad 不会出现在 `labels` 里)。
    """
    assert L_pad % 16 == 0, f"L_pad 必须是 16 的倍数,拿到 {L_pad}"
    B = len(packed_list)
    input_ids = torch.full((B, L_pad), PAD_TOKEN_ID, dtype=torch.long)
    position_ids = torch.zeros((B, L_pad), dtype=torch.long)
    mask = torch.empty((B, 1, L_pad, L_pad), dtype=torch.bfloat16)
    loss_idx = []
    for b, packed in enumerate(packed_list):
        tokens, positions, labels, row_index, seg_bounds = packed
        L = len(tokens)
        assert L <= L_pad, f"事件长度 {L} 超过物理块 pad 长度 {L_pad}"
        input_ids[b, :L] = torch.tensor(tokens, dtype=torch.long)
        position_ids[b, :L] = torch.tensor(positions, dtype=torch.long)
        if L < L_pad:
            last_pos = positions[-1] if positions else -1
            position_ids[b, L:] = torch.arange(
                last_pos + 1, last_pos + 1 + (L_pad - L), dtype=torch.long)
        allowed = _allowed_from_packed(positions, row_index, seg_bounds, L)
        block = torch.full((L_pad, L_pad), float("-inf"), dtype=torch.bfloat16)
        real = torch.zeros((L, L), dtype=torch.bfloat16)
        real.masked_fill_(~allowed, float("-inf"))
        block[:L, :L] = real
        for i in range(L, L_pad):                          # pad 作为 query 只看自己
            block[i, i] = 0.0
        mask[b, 0] = block
        for t in range(1, L):
            if labels[t] != -100:
                loss_idx.append((b, t - 1, labels[t], row_index[t]))
    return input_ids, position_ids, mask, loss_idx


def epoch_minibatches(events, seed, ep, events_per_mb):
    """一个 epoch 的事件顺序与逻辑小批切法(spec 16.5,工单 10):训练循环与
    `cost`/`loop` 显存探针唯一共用的真源——探针踩的块必须是训练真会遇到
    的块。`events` 本身不被修改(先 `list(events)` 复制一份再打乱)。

    `random.Random(seed + ep).shuffle` 打乱后按 `events_per_mb` 个一组切成
    逻辑小批,和旧写法(训练循环原来自己做的这两步)逐个相同。
    """
    epoch_events = list(events)
    random.Random(seed + ep).shuffle(epoch_events)
    return [epoch_events[i:i + events_per_mb]
           for i in range(0, len(epoch_events), events_per_mb)]


def chunk_by_budget(events, tok_budget):
    """spec 第 5 节第二条的贪心装块。

    事件按 `packed_len` 降序,贪心装块:块的『事件数 × L_pad』<= `tok_budget`
    (`L_pad` = 块内最长 `packed_len` 补到 16 的倍数,`_pad16`——预算判据
    和 `batch_mask` 的补齐同口径,不是补齐前的 `packed_len` 本身,spec 第
    5 节);单个事件超预算时独自成块(允许超预算)。

    返回块列表,每块是事件列表(块内顺序 = 装入顺序,即 `packed_len` 降序
    内的先后顺序;block 只定"谁在一起过一次前向",不承诺文件序契约,那条
    契约只属于 `load_events` 的返回值)。
    """
    ordered = sorted(events, key=lambda e: e["packed_len"], reverse=True)
    blocks = []
    current = []
    current_max = 0
    for e in ordered:
        n = len(current) + 1
        cand_max = current_max if current else e["packed_len"]
        if n * _pad16(cand_max) <= tok_budget:
            current.append(e)
            current_max = cand_max
        else:
            if current:
                blocks.append(current)
            current = [e]
            current_max = e["packed_len"]
    if current:
        blocks.append(current)
    return blocks


def worst_blocks(events, tok_budget, events_per_mb):
    """给 `--mem-probe` 用(spec 第 10 节):返回两份事件列表。

    第一份是只含『`packed_len` 最大的单个事件』的列表(长度 1)。

    第二份(『最满块』)不借用 `chunk_by_budget`:真实训练时一个逻辑小批
    只有 `events_per_mb` 个事件(spec 第 5 节),`chunk_by_budget` 只在这
    `events_per_mb` 个事件上跑装块,块内事件数天然 <= `events_per_mb`;
    但 `worst_blocks` 是在全量训练集上找最坏块,如果直接对全量事件跑
    `chunk_by_budget` 再挑"块内最长最大"的那块,块内事件数不受
    `events_per_mb` 约束,找出来的块在真实训练里可能永远不会出现。所以
    最满块单独按工单定义的算法搜:`B` 取 2 到 `events_per_mb`,把 events
    按 `packed_len` 降序排好,对每个 B 用大小为 B 的滑动窗口从最长的一端
    往下扫,取第一个满足 `B * L_pad <= tok_budget` 的窗口(`L_pad` = 窗口
    内最长 `packed_len` 补到 16 的倍数,`_pad16`;降序排列下窗口内最长恰好
    是窗口首元素,窗口往下移这个值只会变小或不变,所以第一个满足条件的
    窗口就是这个 B 能达到的最大 `B * L_pad`);几个 B 各自的最优窗口里,取
    `B * L_pad` 最大的那一组。找不到任何满足条件的窗口(事件数不够、或
    预算太小连 2 个事件都装不下)时,第二份返回空列表。
    """
    if not events:
        return [], []
    longest = max(events, key=lambda e: e["packed_len"])
    ordered = sorted(events, key=lambda e: e["packed_len"], reverse=True)
    n_events = len(ordered)
    best_group = []
    best_product = -1
    for b in range(2, events_per_mb + 1):
        for i in range(n_events - b + 1):
            window = ordered[i:i + b]
            l_pad = _pad16(window[0]["packed_len"])
            product = b * l_pad
            if product <= tok_budget:
                if product > best_product:
                    best_product = product
                    best_group = window
                break                       # 降序排列下首个满足即该 B 的最优窗口
    return [longest], best_group


# ---------------------------------------------------------------- 读取位置

def read_position(offsets, full_text, cut, keep):
    """spec 11.3 的读取位置规则。

    `offsets`:tokenizer 的 `offset_mapping`(每项 `(start, end)` 字符偏移
    半开区间);`full_text`:全文;`cut`:切点的字符位置;`keep`:这一行
    `attention_mask` 的和(真实 token 数,只在 `offsets[:keep]` 里找)。

    `j` = 起始位置 < `cut` 的最后一个真实 token(覆盖字符 `cut-1` 的那个
    token)。`end_j <= cut` 时读 `j`;`end_j > cut` 且 `full_text[cut:end_j]`
    全是空白时也读 `j`;否则读 `j-1`。两种情况返回 -1(找不到):没有任何
    真实 token 的起始位置 < `cut`;要退回 `j-1` 而 `j = 0`。
    """
    j = -1
    for t in range(keep - 1, -1, -1):
        if offsets[t][0] < cut:
            j = t
            break
    if j < 0:
        return -1
    end_j = offsets[j][1]
    if end_j <= cut:
        return j
    if full_text[cut:end_j].isspace():
        return j
    if j == 0:
        return -1
    return j - 1
