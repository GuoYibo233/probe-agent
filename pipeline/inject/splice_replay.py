"""塞法回放:探针开火时把预取结果**怎么拼回去**,哪种让模型少想、直接往下走。
计划:plans/2026-08-18-splice-replay.md(臂、切口、指标、裁决点 D1–D12 都在那)。

上帝视角:拿 chat baseline 轨迹,每步在思考的四个比例位置切开,把该步代码块的
真实执行输出按十种塞法拼进去,让 gpt-oss-120b 续写一步。只量单步行为,不判
预测对错、不跑到底、不 evaluate。探针权重已删,这条线不需要探针。

三段,各自落盘(cprobe-env 跑;只依赖 openai_harmony + 标准库):
  events  轨迹 -> events.jsonl(每事件:CALL/CODE/RESULT/四个切口/基线 token)
  run     每事件 x 切口 x 臂 发 /v1/completions(prompt 为 token id)-> raw.jsonl
  score   解析 -> per_row.jsonl + SPLICE_REPORT.{json,md}

  cprobe-env/bin/python pipeline/inject/splice_replay.py events \\
      --traj-root <chat 轨迹目录> --out <run 目录>
  cprobe-env/bin/python pipeline/inject/splice_replay.py run \\
      --run-dir <run 目录> --base-url http://tokyo108:8103/v1 --model gpt-oss-120b \\
      [--arms ...] [--dry-run] [--limit N]
  cprobe-env/bin/python pipeline/inject/splice_replay.py score --run-dir <run 目录>

prompt 全部是 token id:前缀 = harmony_render.render_ids(chat 端点同款);文本臂
接 encode(<|channel|>analysis<|message|> + head + 拼接串);p3k/p4 整段由
openai_harmony 渲染(不手拼字节)。encode 用 harmony 自带的 o200k_harmony,与
gpt-oss HF 分词器同表(2026-08-18 实测同一串 id 逐个相同)。
"""

import argparse
import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                             # noqa: E402
import harmony_render as H                                      # noqa: E402
from rules import MIN_THINK, SENT_RE                            # noqa: E402
from parse_call import complete_call, CALL_START                # noqa: E402
from replay_inject import PERMIT, SWITCH, DEFAULT_STOP, CODE_RE  # noqa: E402
from live_appworld import parse_step, sent_cuts                 # noqa: E402

A_OPEN = "<|channel|>analysis<|message|>"
CALL_MARK = "<|call|>"
CALL_ID = 200012                # <|call|> 的 token id:模型 generation_config 的 eos 之一,
                                # vLLM 默认并进 stop_token_ids,停在它上面时 stop_reason 是
                                # 这个 int(不是字符串),所有臂都会在这停(D11)
FRACS = [0.66, 0.75, 0.80, 1.00]
MAX_STEP_TOKENS = 8192          # 采集时整步上限(envs/collect/common.py:48)

# 措辞(轴二)。n0 沿用 replay_inject.NOTE_TMPL 的方括号形(现状锚,塞那条调用
# CALL——12/52 个事件代码块不是裸 print(CALL),RESULT 是整块 stdout,这句对它们
# 不完全真,报告按 code_is_print_call 分层看);n1/n2 塞代码块原文 CODE,句句为真
# (D3'/D13);n2 抄的是模型每轮看到的 user 消息形态
def note_body(kind, call, code, result):
    if kind == "n0":
        return f"[SYSTEM NOTE: prefetched {call} = {result}]"
    if kind == "n1":
        return f"I already ran:\n{code}\nand got:\n{result}"
    if kind == "n2":
        return f"```python\n{code}\n```\nExecution output:\n{result}"
    if kind == "n3":
        return result
    raise ValueError(kind)


# 臂表:(位置, 措辞, 是否加 PERMIT)。位置 p1=思考内续写 p2=塞完强切正文
# p3k=伪造整轮留思考 p4=harmony 原生 python 工具
ARMS = {
    "nofill": ("p1", None, False),
    "p1_n0": ("p1", "n0", False),
    "p1_n1": ("p1", "n1", False),
    "p1_n2": ("p1", "n2", False),
    "p1_n3": ("p1", "n3", False),
    "p1_n0p": ("p1", "n0", True),
    "p2_n0": ("p2", "n0", False),
    "p2_n1": ("p2", "n1", False),
    "p3k": ("p3k", None, False),
    "p4": ("p4", None, False),
}
ARMS_ALL = list(ARMS)


def enc(text):
    return list(H.encoding().encode(text, allowed_special="all"))


def enc_plain(text):
    """编码**不该含控制标记**的文本(head / NOTE / RESULT / CODE)。文本里若混进
    字面 <|end|> 之类,allowed_special="all" 会把它收成真特殊 token 静默毁掉
    prompt(harmony_render 文件头写的那种事故),这里直接拒绝。"""
    ids = enc(text)
    e = H.encoding()
    bad = [i for i in ids if e.is_special_token(i)]
    if bad:
        raise ValueError(f"文本里有字面控制标记 {[H.decode([i]) for i in bad]},"
                         "拼进 prompt 会变成真特殊 token")
    return ids


def sep_for(head):
    """缝修法(D5/D5'):head 以空白结尾(66/75/80 切口都是,句尾空白之后)就不加
    前导换行,NOTE 直接接在空白后——`.\\n\\n`+`\\n[` 会合并成 `.\\n\\n\\n` 把模型自己
    的最后一个 token 换掉;`. `+`\\n[` 虽保住 `.` 却多出一个 ` \\n` 怪 token;
    `.\\n\\n`+`[S` 与 `. `+`[S`(inline)都干净、`.` 原样。只有 head 无尾空白
    (100% 切口)才加 `\\n` 另起一行。"""
    return "" if head[-1:].isspace() else "\n"


# ---------------------------------------------------------------- events

def cut_points(think, fracs=FRACS):
    """比例 -> 切口。<1 的比例取该比例字符位之前最近的句尾(sent_cuts 同款);
    1.0 取全文末尾。同一切口的比例合并。返回 [(cut, [fracs])],按 cut 升序。"""
    cuts = sent_cuts(think)
    got = {}
    for f in fracs:
        if f >= 1.0:
            c = len(think)
        else:
            pos = int(round(len(think) * f))
            cand = [c for c in cuts if c <= pos]
            if not cand:
                continue                    # 该比例之前没有合法句尾:这个比例没有事件
            c = cand[-1]
        got.setdefault(c, []).append(f)
    return sorted(got.items())


def cmd_events(a):
    root, out = Path(a.traj_root), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    R.check_system_verbatim()
    fracs = [float(x) for x in a.fracs.split(",")]
    seen, evs = set(), []
    stat = dict(steps=0, no_code=0, not_one_call=0, short_think=0, dup=0,
                kept=0, baseline_capped=0, code_is_print_call=0)
    for f in sorted(root.glob("appworld_*.jsonl")):
        meta, gens, envs, _ = R.load_traj(f)
        tid = meta["task_id"]
        for st in sorted(gens):
            stat["steps"] += 1
            g, e = gens[st], envs.get(st)
            if e is None or e.get("action") is None:
                stat["no_code"] += 1
                continue
            m = CODE_RE.search(g.get("content") or "")
            if not m:
                stat["no_code"] += 1
                continue
            code = m.group(1).strip()
            if len(CALL_START.findall(code)) != 1:
                stat["not_one_call"] += 1        # D1:多调用块 / 无调用块都不取
                continue
            think = (g.get("reasoning") or "").strip()
            if len(think) < MIN_THINK:
                stat["short_think"] += 1
                continue
            call, _ = complete_call(code)
            if call is None:
                stat["not_one_call"] += 1      # 括号配不平,当抽不出那条调用
                continue
            msgs = R.build_messages(meta, gens, envs, st)
            key = hashlib.sha1(json.dumps([msgs, think]).encode()).hexdigest()
            if key in seen:
                stat["dup"] += 1
                continue
            seen.add(key)
            cps = cut_points(think, fracs)      # 1.0 在 fracs 里就一定非空
            nxt = gens.get(st + 1)
            nm = CODE_RE.search((nxt or {}).get("content") or "")
            nt = CALL_START.search(nm.group(1)) if nm else None
            next_call = complete_call(nm.group(1))[0] if nm else None
            cm = CALL_START.match(call)
            base = (g.get("usage") or {}).get("out")
            # D12:采集时该步顶到 max_tokens=8192 的,基线 out 是被截的数,
            # 省 token 的账对它不公平,标出来,score 里分开看
            capped = base is not None and base >= MAX_STEP_TOKENS
            stat["baseline_capped"] += int(capped)
            stat["code_is_print_call"] += int(code == f"print({call})")
            evs.append(dict(
                event=f"{tid}_s{st}", traj_path=str(f), task_id=tid, step=st,
                think_chars=len(think), call=call,
                call_tool=f"apis.{cm.group(1)}.{cm.group(2)}",
                code=code, result=e["result"],
                baseline_out_tok=base, baseline_capped=capped,
                next_tool=(f"apis.{nt.group(1)}.{nt.group(2)}" if nt else None),
                next_call=next_call,
                # n0 的措辞对"裸 print(CALL)"之外的块不完全真;报告按这个分层
                code_is_print_call=(code == f"print({call})"),
                cuts=[dict(cut=c, fracs=fs) for c, fs in cps]))
            stat["kept"] += 1
    with open(out / "events.jsonl", "w") as w:
        for ev in evs:
            w.write(json.dumps(ev, ensure_ascii=False) + "\n")
    cfg = dict(traj_root=str(root), fracs=fracs, stat=stat,
               n_events=len(evs), n_cuts=sum(len(e["cuts"]) for e in evs),
               date=time.strftime("%Y-%m-%d"), arms=ARMS_ALL)
    (out / "events_config.json").write_text(json.dumps(cfg, indent=1,
                                                       ensure_ascii=False))
    print(json.dumps(cfg, ensure_ascii=False))


# ---------------------------------------------------------------- prompt

def prefix_messages(ev, permit=False):
    """该步之前的 chat 消息(照 run_appworld 拼法)。permit 在 system 末尾加预告句。"""
    meta, gens, envs, _ = R.load_traj(Path(ev["traj_path"]))
    msgs = R.build_messages(meta, gens, envs, ev["step"])
    if permit:
        msgs = [dict(m) for m in msgs]
        msgs[0]["content"] = msgs[0]["content"] + PERMIT
    return msgs, gens


def build_prompt(arm, ev, head, msgs, content):
    """返回 (prompt_ids, prefix_len, splice_text)。
    prefix_len = 前缀(止于 <|start|>assistant)的 token 数,之后的都算本轮的字节;
    splice_text = 拼进去、但不是模型自己写的那截(记账 + 人眼核对)。"""
    where, kind, _ = ARMS[arm]
    prefix = H.render_ids(msgs, effort="high", start_date=R.COLLECT_DATE)
    if where == "p1":
        if kind is None:
            splice = ""
        else:
            splice = sep_for(head) + note_body(kind, ev["call"], ev["code"],
                                               ev["result"]) + "\n"
        # 控制标记与正文分开编码(特殊 token 本来就是分词边界,分开编与整串编
        # 逐 id 相同),正文走 enc_plain 拒字面控制标记
        return prefix + enc(A_OPEN) + enc_plain(head + splice), len(prefix), splice
    if where == "p2":
        note = sep_for(head) + note_body(kind, ev["call"], ev["code"], ev["result"])
        splice = note + SWITCH
        return (prefix + enc(A_OPEN) + enc_plain(head + note) + enc(SWITCH),
                len(prefix), splice)
    # 结构臂:整段交 openai_harmony 渲染
    from openai_harmony import (Author, Conversation, Message,
                                RenderConversationConfig, Role, SystemContent,
                                ReasoningEffort, ToolNamespaceConfig)
    hm = H.to_harmony_messages(msgs, effort="high", start_date=R.COLLECT_DATE)
    body = head.rstrip()                    # D6:analysis 以模型自己的字收尾再 <|end|>
    for t in (body, content, ev["code"], ev["result"]):
        enc_plain(t)                        # 同一道门:字面控制标记直接拒
    cfg = RenderConversationConfig(auto_drop_analysis=False)

    def render(ms):
        return list(H.encoding().render_conversation_for_completion(
            Conversation.from_messages(ms), Role.ASSISTANT, config=cfg))
    if where == "p3k":
        hm += [Message.from_role_and_content(Role.ASSISTANT, body)
               .with_channel("analysis"),
               Message.from_role_and_content(Role.ASSISTANT, content)
               .with_channel("final"),
               Message.from_role_and_content(
                   Role.USER, f"Execution output:\n{ev['result']}")]
    elif where == "p4":
        # D7:system 里声明 python 工具(训练格式的一部分)
        sysc = (SystemContent.new()
                .with_reasoning_effort(ReasoningEffort.HIGH)
                .with_conversation_start_date(R.COLLECT_DATE)
                .with_tools(ToolNamespaceConfig.python()))
        hm[0] = Message.from_role_and_content(Role.SYSTEM, sysc)
        hm += [Message.from_role_and_content(Role.ASSISTANT, body)
               .with_channel("analysis"),
               Message.from_role_and_content(Role.ASSISTANT, ev["code"])
               .with_channel("analysis").with_recipient("python"),
               Message.from_author_and_content(
                   Author.new(Role.TOOL, "python"), ev["result"])
               .with_channel("analysis").with_recipient("assistant")]
    else:
        raise ValueError(arm)
    n_added = 3
    # 前缀 = 本臂自己的"到该步之前的历史"渲染(p4 的 system 多了工具声明,
    # 所以不能拿文本臂的 prefix 长度充数);它渲染出来止于 <|start|>assistant,
    # 正好是全串的前缀,断言钉死
    own_prefix = render(hm[:-n_added])
    ids = render(hm)
    if ids[:len(own_prefix)] != own_prefix:
        raise RuntimeError(f"{arm}: 结构臂前缀不是全串前缀,渲染器行为变了")
    if where == "p3k" and own_prefix != prefix:
        raise RuntimeError("p3k 前缀应与 chat 渲染逐 token 同")
    return ids, len(own_prefix), H.decode(ids[len(own_prefix):])


# ---------------------------------------------------------------- run

def post_json(url, payload, timeout, retries=4):
    body = json.dumps(payload).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError:
            raise                            # 400 之类不重试,原样往外抛
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    retry {att + 1}: {e}", flush=True)
            time.sleep(2 ** att)


def cmd_run(a):
    d = Path(a.run_dir)
    R.check_system_verbatim()               # run/score 也重建 prompt,同样回源核对
    H.encoding()                            # 线程池之前先把编码器装好(懒加载不线程安全)
    evs = [json.loads(l) for l in open(d / "events.jsonl")]
    if a.limit:
        evs = evs[:a.limit]
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in arms if x not in ARMS]
    if bad:
        raise SystemExit(f"未知 arm:{bad};可选 {ARMS_ALL}")
    rp = d / f"raw{a.tag}.jsonl"
    done = set()
    if rp.exists() and not a.dry_run:
        for l in open(rp):
            try:
                o = json.loads(l)
                done.add((o["event"], o["cut"], o["arm"]))
            except Exception:
                pass
    todo = [(ev, c, arm) for ev in evs for c in ev["cuts"] for arm in arms
            if (ev["event"], c["cut"], arm) not in done]
    print(f"事件 {len(evs)} 切口 {sum(len(e['cuts']) for e in evs)} x 臂 {arms}"
          f";已有 {len(done)},待跑 {len(todo)},并发 {a.concurrency}", flush=True)
    if a.dry_run:
        todo = todo[:a.limit or 12]

    lock, cache, clock = threading.Lock(), {}, threading.Lock()
    stat = dict(n=0, fail=0, t0=time.time())

    def msgs_of(ev, permit):
        k = (ev["event"], permit)
        with clock:
            if k not in cache:
                cache[k] = prefix_messages(ev, permit)
            return cache[k]

    def one(ev, c, arm):
        _, _, permit = ARMS[arm]
        msgs, gens = msgs_of(ev, permit)
        think = (gens[ev["step"]].get("reasoning") or "").strip()
        head = think[:c["cut"]]
        content = gens[ev["step"]].get("content") or ""
        ids, plen, splice = build_prompt(arm, ev, head, msgs, content)
        head_tok = len(enc(A_OPEN + head))
        rec = dict(event=ev["event"], cut=c["cut"], fracs=c["fracs"], arm=arm,
                   prompt_tok=len(ids), prefix_tok=plen, head_tok=head_tok,
                   splice_tok=len(ids) - plen - head_tok, splice=splice)
        if a.dry_run:
            # 只看缝:head 末尾 30 个 token 起到 prompt 末尾,再截 1200 字符
            rec["prompt_tail"] = H.decode(ids[max(0, plen + head_tok - 30):])[:1200]
            return rec
        # D11:<|call|> 已在模型 generation_config 的 eos 里,vLLM 默认对所有臂
        # 都停(stop_reason=200012);这里再挂字符串停止符只是保险
        stop = list(DEFAULT_STOP) + [CALL_MARK]
        t0 = time.time()
        r = post_json(a.base_url.rstrip("/") + "/completions", dict(
            model=a.model, prompt=ids, max_tokens=a.max_tokens,
            temperature=0.0, stop=stop, skip_special_tokens=False),
            a.timeout)
        ch = r["choices"][0]
        rec.update(text=ch["text"], finish_reason=ch.get("finish_reason"),
                   stop_reason=ch.get("stop_reason"),
                   prompt_tok=r["usage"]["prompt_tokens"],
                   gen_tok=r["usage"]["completion_tokens"],
                   wall_s=round(time.time() - t0, 2))
        return rec

    sink = open(rp, "a") if not a.dry_run else None
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(one, ev, c, arm): (ev["event"], c["cut"], arm)
                for ev, c, arm in todo}
        for fu in as_completed(futs):
            key = futs[fu]
            try:
                rec = fu.result()
            except Exception as e:
                stat["fail"] += 1
                print(f"  FAIL {key}: {type(e).__name__}: {e}", flush=True)
                continue
            with lock:
                if a.dry_run:
                    print(json.dumps(rec, ensure_ascii=False))
                else:
                    sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    sink.flush()
                stat["n"] += 1
                if stat["n"] % 50 == 0:
                    el = time.time() - stat["t0"]
                    rate = stat["n"] / el
                    left = (len(todo) - stat["n"]) / rate if rate else 0
                    print(f"  {stat['n']}/{len(todo)} {rate:.2f} req/s "
                          f"ETA {left/60:.1f} min", flush=True)
    if sink:
        sink.close()
        print(f"完成 {stat['n']}/{len(todo)};失败 {stat['fail']} -> {rp}")
    else:
        print(f"dry-run 打印 {stat['n']} 条,没落盘")


# ---------------------------------------------------------------- score

# 议论注入本身。"the note" 单独会误中 simple_note / "the notes app",所以只认
# 带动词的搭配;"already ran" 单列(n1 措辞自带这三个词,nofill 里也可能自然出现,
# 两边一起看)
MENTION_RE = re.compile(
    r"system note|prefetch|the note says|note above|according to the note|"
    r"per the note|given the note|from the note", re.I)
ALREADY_RE = re.compile(r"already ran|already called|already executed", re.I)
STR_LIT_RE = re.compile(r"""(?:"([^"\\\n]{3,})"|'([^'\\\n]{3,})')""")


def analyze(arm, splice, text):
    """把拼接串 + 续写还原成整轮 assistant 文本,切成 (thinking, content)。
    p1/nofill:整轮 = A_OPEN + head + splice + text(head 不在这里,只切 text 也
    行——通道头在 splice 前面已经写在 prompt 里,text 从 analysis 内部开始);
    p2:text 从 final 内部开始;p3k/p4:text 从 <|start|>assistant 之后开始。"""
    where = ARMS[arm][0]
    if where == "p1":
        return parse_step(A_OPEN + text)      # 头补回去,parse_step 认得
    if where == "p2":
        think, content = parse_step(A_OPEN + splice + text)   # splice 末尾是 SWITCH
        note = splice[:-len(SWITCH)].strip()
        t = think.lstrip()
        if note and t.startswith(note):       # 拼进去的 NOTE 不算模型"又想了"
            think = t[len(note):]
        return think, content
    # p3k/p4:模型自己发起的 python 调用段(to=python … <|call|>)不是"想",剔掉再切;
    # 它单独由 python_call_code 抽出来当动作
    return parse_step(PY_CALL_RE.sub("", text))


# 模型自己写的 python 调用段。实测(smoke)它写的是
# `<|start|>assistant<|channel|>analysis to=python code<|message|>CODE<|call|>`
# (收件人在通道后、还带 " code"),harmony 库渲染的是 `<|start|>assistant to=python
# <|channel|>analysis<|message|>`;两种都认:从 " to=python" 起吞到 <|call|>/文末,
# 连带紧挨着的 <|start|>assistant / <|channel|>analysis 头
PY_CALL_RE = re.compile(
    r"(?:<\|start\|>assistant)?(?:<\|channel\|>analysis)? to=python.*?<\|message\|>"
    r".*?(?:<\|call\|>|$)", re.S)


def python_call_code(text):
    """模型自己发起的 python 调用(analysis 通道、收件人 python):`to=python` 之后
    第一个 <|message|> 到 <|call|>/文末的那段代码;没有就 None。"""
    i = text.find(" to=python")
    if i < 0:
        return None
    j = text.find("<|message|>", i)
    if j < 0:
        return None
    body = text[j + len("<|message|>"):]
    return body.split(CALL_MARK, 1)[0]


def stopped_on_call(o):
    """这条续写是不是停在 <|call|> 上(vLLM 记 int 200012;字符串停止符命中时记字符串)。"""
    return o.get("stop_reason") in (CALL_ID, CALL_MARK)


def norm_call(c):
    return re.sub(r"\s+", "", c) if c else None


def first_tool(code):
    m = CALL_START.search(code or "")
    return f"apis.{m.group(1)}.{m.group(2)}" if m else None


def cmd_score(a):
    d = Path(a.run_dir)
    R.check_system_verbatim()
    evs = {}
    for l in open(d / "events.jsonl"):
        ev = json.loads(l)
        evs[ev["event"]] = ev
    raw = {}
    for l in open(d / f"raw{a.tag}.jsonl"):
        o = json.loads(l)
        raw[(o["event"], o["cut"], o["arm"])] = o        # 后写覆盖先写
    cache = {}

    def pre_text(ev, cut):
        k = (ev["event"], cut)
        if k not in cache:
            msgs, gens = prefix_messages(ev)
            think = (gens[ev["step"]].get("reasoning") or "").strip()
            cache[k] = "\n".join(m["content"] for m in msgs) + "\n" + think[:cut]
        return cache[k]

    rows = []
    for (evn, cut, arm), o in raw.items():
        ev = evs.get(evn)
        if ev is None or "text" not in o:
            continue
        think, content = analyze(arm, o["splice"], o["text"])
        m = CODE_RE.search(content)
        py_code = python_call_code(o["text"])
        # 模型这一步的"动作":正文代码块;没有正文、但自己发了 python 调用
        # (p4 的自然续写就是这样,harmony 把它放 analysis 通道)也算动作
        if m:
            code, action = m.group(1), "final_code"
        elif py_code is not None:
            code, action = py_code, "python_call"
        else:
            code, action = "", None
        tool = first_tool(code)
        call_out = complete_call(code)[0]
        pre = pre_text(ev, cut)
        lits = {x or y for x, y in STR_LIT_RE.findall(code)}
        used = sorted(s for s in lits if s in ev["result"] and s not in pre)
        # 结构:p2 之后又开 analysis;任何臂停在 <|call|> 上(模型想叫工具)
        reopen = ("<|channel|>analysis" in o["text"]) if ARMS[arm][0] == "p2" \
            else None
        on_call = stopped_on_call(o)
        base = ev.get("baseline_out_tok")
        own_tok = o["head_tok"] + o["gen_tok"]      # 模型自己写的(拼接串不算)
        wire_tok = o["prompt_tok"] - o["prefix_tok"] + o["gen_tok"]
        # 有动作才进 repeated/next_hit/advanced 的分母
        rep_tool = (tool == ev["call_tool"]) if tool else None
        rep_call = (norm_call(call_out) == norm_call(ev["call"])) if call_out else None
        nxt_tool = (tool == ev["next_tool"]) if tool and ev["next_tool"] else None
        nxt_call = ((norm_call(call_out) == norm_call(ev["next_call"]))
                    if call_out and ev.get("next_call") else None)
        rows.append(dict(
            event=evn, cut=cut, fracs=o["fracs"], arm=arm,
            head_tok=o["head_tok"], splice_tok=o["splice_tok"],
            gen_tok=o["gen_tok"], own_tok=own_tok, wire_tok=wire_tok,
            baseline_out_tok=base, baseline_capped=ev.get("baseline_capped"),
            code_is_print_call=ev.get("code_is_print_call"),
            next_distinct=(ev["next_tool"] is not None
                           and ev["next_tool"] != ev["call_tool"]),
            saved_own=(base - own_tok) if base is not None else None,
            saved_wire=(base - wire_tok) if base is not None else None,
            has_code=bool(m), action=action, has_action=action is not None,
            tool_out=tool, call_out=call_out,
            repeated=rep_tool, repeated_call=rep_call,
            next_hit=nxt_tool, next_hit_call=nxt_call,
            advanced=((tool != ev["call_tool"]) if tool else None),
            uses_result=bool(used), used_literals=used[:5],
            mentions=bool(MENTION_RE.search(o["text"])),
            mentions_already=bool(ALREADY_RE.search(o["text"])),
            reopen_analysis=reopen, stopped_on_call=on_call,
            python_call=(py_code is not None),
            think_chars_after=len(think.strip()), content_chars=len(content),
            finish_reason=o.get("finish_reason"), stop_reason=o.get("stop_reason")))
    # 同事件同切口的 nofill 当参照:own_tok 差(拼接串不算)——比 baseline 更贴,
    # baseline 的 usage.out 里 commentary 段与消息头的账对不齐(体检线会有几个
    # token 的常数偏移,别当管线错)
    nof = {(r["event"], r["cut"]): r["own_tok"] for r in rows if r["arm"] == "nofill"}
    for r in rows:
        n = nof.get((r["event"], r["cut"]))
        r["vs_nofill_own"] = (n - r["own_tok"]) if n is not None else None
    with open(d / f"per_row{a.tag}.jsonl", "w") as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    def agg(rs):
        n = len(rs)
        if not n:
            return {}
        def rate(k):
            v = [r[k] for r in rs if r[k] is not None]
            return round(sum(bool(x) for x in v) / len(v), 3) if v else None
        def rate_where(k, cond):
            v = [r[k] for r in rs if r[k] is not None and r[cond]]
            return round(sum(bool(x) for x in v) / len(v), 3) if v else None
        def med(k):
            v = sorted(r[k] for r in rs if r[k] is not None)
            return v[len(v) // 2] if v else None
        def mean(k):
            v = [r[k] for r in rs if r[k] is not None]
            return round(sum(v) / len(v), 1) if v else None
        return dict(n=n, gen_tok_med=med("gen_tok"), own_tok_med=med("own_tok"),
                    vs_nofill_own_med=med("vs_nofill_own"),
                    saved_own_med=med("saved_own"), saved_own_mean=mean("saved_own"),
                    saved_wire_med=med("saved_wire"),
                    has_code=rate("has_code"), has_action=rate("has_action"),
                    python_call=rate("python_call"),
                    repeated=rate("repeated"), repeated_call=rate("repeated_call"),
                    next_hit=rate("next_hit"), next_hit_call=rate("next_hit_call"),
                    next_hit_distinct=rate_where("next_hit", "next_distinct"),
                    advanced=rate("advanced"),
                    uses_result=rate("uses_result"), mentions=rate("mentions"),
                    mentions_already=rate("mentions_already"),
                    reopen_analysis=rate("reopen_analysis"),
                    stopped_on_call=rate("stopped_on_call"),
                    truncated=round(sum(r["finish_reason"] == "length"
                                        for r in rs) / n, 3),
                    think_after_med=med("think_chars_after"))

    by_arm = defaultdict(list)
    by_arm_frac = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_arm[r["arm"]].append(r)
        for f in r["fracs"]:
            by_arm_frac[f"{f:.2f}"][r["arm"]].append(r)
    rep = dict(run_dir=str(d), n_rows=len(rows),
               n_rows_baseline_capped=sum(bool(r["baseline_capped"]) for r in rows),
               by_arm={k: agg(v) for k, v in by_arm.items()},
               by_arm_uncapped={k: agg([r for r in v if not r["baseline_capped"]])
                                for k, v in by_arm.items()},
               # n0 措辞只对裸 print(CALL) 的块句句为真,分层看
               by_arm_print_call={k: agg([r for r in v if r["code_is_print_call"]])
                                  for k, v in by_arm.items()},
               by_arm_not_print_call={k: agg([r for r in v if not r["code_is_print_call"]])
                                      for k, v in by_arm.items()},
               by_frac={f: {k: agg(v) for k, v in arms.items()}
                        for f, arms in sorted(by_arm_frac.items())})
    (d / f"SPLICE_REPORT{a.tag}.json").write_text(
        json.dumps(rep, indent=1, ensure_ascii=False))
    cols = ["n", "own_tok_med", "vs_nofill_own_med", "saved_own_med", "has_action",
            "python_call", "repeated", "repeated_call", "next_hit", "next_hit_call",
            "next_hit_distinct", "uses_result", "mentions", "mentions_already",
            "reopen_analysis", "stopped_on_call", "truncated", "think_after_med"]
    lines = [f"# SPLICE_REPORT{a.tag}", "", f"rows={len(rows)}",
             "", "## by arm", "", "| arm | " + " | ".join(cols) + " |",
             "|" + "---|" * (len(cols) + 1)]
    for k in ARMS_ALL:
        if k in rep["by_arm"]:
            v = rep["by_arm"][k]
            lines.append(f"| {k} | " + " | ".join(str(v.get(c)) for c in cols) + " |")
    for f, arms in rep["by_frac"].items():
        lines += ["", f"## frac {f}", "", "| arm | " + " | ".join(cols) + " |",
                  "|" + "---|" * (len(cols) + 1)]
        for k in ARMS_ALL:
            if k in arms:
                v = arms[k]
                lines.append(f"| {k} | " + " | ".join(str(v.get(c)) for c in cols) + " |")
    (d / f"SPLICE_REPORT{a.tag}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("events")
    e.add_argument("--traj-root", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--fracs", default=",".join(str(f) for f in FRACS))
    e.set_defaults(fn=cmd_events)
    r = sp.add_parser("run")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--base-url", default="http://tokyo108:8103/v1")
    r.add_argument("--model", default="gpt-oss-120b")
    r.add_argument("--arms", default=",".join(ARMS_ALL))
    r.add_argument("--max-tokens", type=int, default=MAX_STEP_TOKENS)   # D8
    r.add_argument("--concurrency", type=int, default=16)
    r.add_argument("--timeout", type=int, default=1800)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--tag", default="")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sp.add_parser("score")
    s.add_argument("--run-dir", required=True)
    s.add_argument("--tag", default="")
    s.set_defaults(fn=cmd_score)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
