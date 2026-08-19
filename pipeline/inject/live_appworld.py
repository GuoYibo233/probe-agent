"""活跑注入线驱动器(appworld venv,纯 CPU)。方法规范:METHOD.md(旧设计书已随 08-02 清场删除)

回答的问题:探针实时出手、把预测调用的真实执行返回注进思考,**整道题**还做不做
得对、省不省 token。这是回放线(单步续写)给不出的任务级成绩,2026-08-01 用户
拍板立项。评测全程不判预测对错:出手就执行、返回什么注什么(报错也注)。

一步之内(设计书 §2):
  1. 消息历史照采集脚本拼(SYSTEM 从 rebuild 取,启动时回源核对);
  2. harmony 前缀问探针服务要(/render 出 token id,与 chat 端点渲染逐 token
     相同;appworld venv 没有 transformers/openai_harmony);
  3. 分段生成:每段 --chunk-tokens 个 token,贪心,stop=<|return|>;
  4. 每个新句子级切口把 assemble(task, hist, thinking[:cut]) 发 /score,
     首过 θ 触发(切口查满 MAX_BOUNDS 个就歇手,口径差见设计书 §4.2);
  5. 触发:/gen 出整条调用 -> 正身世界 save_state -> requote -> 执行 ->
     截 4000 -> load_state 回档 -> _set_datetime() 重冻 -> 时间守卫断言
     (【照抄 exec_calls.replay_unit】,finally 兜底)-> NOTE 拼在切口处,
     切口后的溢出文本丢弃(丢弃量记账)-> 继续分段生成;
  6. <|end|> 出现后停止探测,段长放大到 --tail-tokens 跑完该步;final 通道
     取代码块,正身世界执行,喂回输出,进下一步。默认每步最多注一次。

进程与环境(设计书 §3):
  **本文件与 exec_calls.py 是整条流水线仅有的两个 import appworld 的地方**,
  只能用 envs/appworld/venv/bin/python 跑;一个进程一个世界(AppWorld 的
  close_all 会弄坏并存实例),并发靠 --num-shards 多进程。

落盘:每题一个 live_{task_id}.jsonl,记录类型:
  meta  任务与全部口径(θ/T/服务端点/chunk 尺寸/探针配置回显)
  gen   每步聚合:thinking/content/逐段 usage 累加/丢弃溢出的字符与 token 数
  spec  每次出手:切口、置信度、预测调用、requote 分支、执行返回(截 4000)、
        错误种类、注入行全文;v6 加 head_tok/dropped_chars/overflow_ids
  resume 每次重发续写收尾:新 id 与被丢弃 id 的 match_len/identical(v6)
  env   每步真代码与执行输出(与采集侧同款)
  final steps/completed/eval(结构化 dict,不存 str——打分要读它)

用法(冒烟,val 分区 2 题;测试堆不拿来调试):
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \\
      --base-url http://tokyo108:8103/v1 --probe-url http://tokyo108:8790 \\
      --split dev --n 2 --outdir pipeline/inject/runs/live_smoke \\
      --exp live_smoke
  对照臂(同路径不挂探针,回放线 nofill 的活跑版): 加 --no-probe
  probe but nofill 臂(ident3,2026-08-18;探针权重已删,伪触发):
      加 --fire-nth-cut 5 --nofill(第 5 个句尾切口中断,head 用模型自己的
      token id 原样重发,什么都不塞)

v6(2026-08-18 ident3):流带 return_token_ids,gen 记录多 gen_ids(整步 token id);
开火重发 prompt = prefix_ids + gen_ids[:k](切口退到 token 边界,/decode 核对)
+ /encode(NOTE),不再整段重分词;spec 记 overflow_ids(中断时丢弃的 id),
resume 记录记重发续写与之逐位比的 match_len/identical。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                            # noqa: E402
from rules import MIN_THINK, SENT_RE, assemble                 # noqa: E402
from exec_calls import (APPWORLD_SEED, TRUNC, CKPT, error_kind,  # noqa: E402
                        requote)
from replay_inject import DEFAULT_STOP, NOTE_TMPL              # noqa: E402

APPWORLD_HOME = "/home/y-guo/reproduce/new1/envs/appworld"
END_MARK = "<|end|>"
MAX_BOUNDS = 64            # rules.MAX_BOUNDS 同值:活跑最多查这么多切口(§4.2)
MAX_STEP_TOKENS = 8192     # 采集时 max_tokens=8192(common.py:20),整步上限对齐

# v4(2026-08-02):与 w0 的 chat 路径逻辑同构。三条对齐:
# (1) 不预填通道头——prompt 止于 <|start|>assistant,模型自己写
#     <|channel|>analysis<|message|>,与 chat 渲染逐字节相同;
#     v5(2026-08-18):prompt 直接以 token id 发(/render 出 id,照抄 chat 端点
#     渲染),不再让 completions 端点分词——空 content 轮与字面 <|...|> 标记
#     两处的 chat/completions 口径差随之消掉(harmony_render.py 文件头);
# (2) 流式一枪解码——一步一个 stream=true 请求,服务器不间断解码,
#     只在探针真开火时 close() 中止重发(注入本身要改 prompt,缝不可约);
# (3) 停止只认 <|return|>,final 后模型续写的消息照 vLLM HarmonyParser
#     并进 content(chat 同款,含 1.3% 的伪造尾巴——消息级解析下是干净散文,
#     v1 的毒是裸标记漏进文本,这里不存在)。


def parse_step(full):
    """整步生成文本 -> (thinking, content)。按 vLLM HarmonyParser 同款口径
    切通道(vllm/parser/harmony.py::_SegmentType + parse):analysis->thinking,
    final 与无收件人的 commentary->content,各自多段 \n 连接。

    2026-08-02 诊断教训:v2 及之前只取 final,把模型写在 commentary 通道的行动
    叙述整段静默丢掉(step-0 实测 w0 content 带散文 152/168,活跑只有 4/168)。
    喂回历史的"自己"长期没有散文,模型把叙述欲塞进 complete_task(answer=...),
    而不问问题的题 answer 标准答案是 null,一塞就死。content 必须与 chat 逐字对齐。

    full 是 <|start|>assistant 之后的全部生成文本:首条消息自带
    <|channel|>analysis<|message|> 头(v4 不预填);兼容老口径(头在 prompt 里,
    full 直接以正文开头)。<|return|> 是引擎停止符,文本里若出现(理论分支)
    从它起全部截掉——引擎在那本来就停了。"""
    full = full.split("<|return|>", 1)[0]
    reasoning, content = [], []
    for i, seg in enumerate(full.split(END_MARK)):
        if i == 0 and not seg.lstrip().startswith("<|channel|>"):
            ch, has_rcpt, body = "analysis", False, seg   # 老口径:头在 prompt
        else:
            hdr, sep, body = seg.partition("<|message|>")
            hdr = hdr.strip()
            # 合法头 = [<|start|>assistant[ to=x]]<|channel|>CH[垃圾];
            # 非助手消息(伪造 user/system 回合)或残段一律丢——vLLM 同款。
            if not sep or not (hdr.startswith("<|start|>assistant")
                               or hdr.startswith("<|channel|>")):
                continue
            m = re.match(r"\s*([a-z]+)", hdr.partition("<|channel|>")[2])
            ch = m.group(1) if m else ""
            has_rcpt = " to=" in hdr
        if ch == "analysis" and body:
            reasoning.append(body)
        elif (ch == "final" or (ch == "commentary" and not has_rcpt)) and body:
            content.append(body)
    return "\n".join(reasoning), "\n".join(content)


def think_span(raw):
    """raw(<|start|>assistant 之后的生成文本)里 analysis 正文的 (start, end)。
    头没写全或首条消息不是 analysis 返回 None;end 在消息未闭合时 = len(raw)。"""
    m = raw.find("<|message|>")
    if m < 0:
        return None
    hdr = raw[:m]
    if END_MARK in hdr or "analysis" not in hdr:
        return None
    end = raw.find(END_MARK, m)
    start = m + len("<|message|>")
    return (start, end if end >= 0 else len(raw))


def sent_starts(text):
    """句尾切口按**起点**(标点之后、空白之前,`m.start()`)列出——活跑用这个。
    流式下句尾空白是一段段到的:`. ` 先到、`\\n` 后到,按 `m.end()` 记的话同一个
    句尾会先后算成两个切口(p 与 p+1),"第 N 个切口"就随分块变;起点不随后续
    空白移动,同一句尾永远只算一次。MIN_THINK//2 过滤照旧(strip 后长度,与
    end 口径等价)。回放线的 sent_cuts(按 end)保持不动。"""
    pts = sorted({m.start() for m in SENT_RE.finditer(text)})
    return [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]


def sent_cuts(text):
    """真实句子级切口(不含全文末尾伪切口)。

    与 rules.boundaries 的差别(设计书 §4.2):不做 MAX_BOUNDS 等距抽样——
    抽样结果随文本增长而变,活跑下会让"已探测过的切口"集合失效;上限改由
    调用方数"已探测次数"来管。MIN_THINK 过滤照抄。
    """
    pts = sorted({m.end() for m in SENT_RE.finditer(text)})
    return [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]


class Stream:
    """流式 /v1/completions。iter 出 (文本增量, token id 增量);中途 close()
    即中止服务端解码。请求带 return_token_ids=True(vLLM 0.26:每块的
    token_ids 与 text 是同一步解码的增量,文本可能因未凑齐的 UTF-8 字节
    滞后于 id,所以两者按块一起交出去,调用方按块记边界)。
    收尾后 finish/usage 可读(带 include_usage;被中止时 usage 为 None,
    调用方用收到的 id 数记 gen token)。"""

    def __init__(self, base_url, payload, timeout):
        url = base_url.rstrip("/") + "/completions"
        body = json.dumps(dict(payload, stream=True, return_token_ids=True,
                               stream_options={"include_usage": True})).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        self.resp = urllib.request.urlopen(req, timeout=timeout)
        self.finish = None
        self.stop_reason = None
        self.usage = None
        self.n_chunks = 0
        self.n_ids = 0

    def __iter__(self):
        for line in self.resp:
            if not line.startswith(b"data: "):
                continue
            data = line[6:].strip()
            if data == b"[DONE]":
                break
            ck = json.loads(data)
            if ck.get("usage"):
                self.usage = ck["usage"]
            for c in ck.get("choices") or []:
                if c.get("finish_reason"):
                    self.finish = c["finish_reason"]
                    self.stop_reason = c.get("stop_reason")
                text = c.get("text") or ""
                ids = c.get("token_ids") or []
                if text or ids:
                    self.n_chunks += 1
                    self.n_ids += len(ids)
                    yield text, ids
        self.close()

    def close(self):
        try:
            self.resp.close()
        except Exception:
            pass


def open_stream(base_url, payload, timeout, retries=3):
    for att in range(retries):
        try:
            return Stream(base_url, payload, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    stream retry {att + 1}: {e}", flush=True)
            time.sleep(2 ** att)


def http_json(url, payload, timeout=600, retries=3):
    body = json.dumps(payload, ensure_ascii=False).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())
            if isinstance(out, dict) and out.get("error"):
                raise RuntimeError(f"{url}: {out['error']}")
            return out
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    retry {att + 1} {url}: {e}", flush=True)
            time.sleep(2 ** att)


class W:
    """一题一个 jsonl,逐条 flush(进程被杀不白跑)。"""

    def __init__(self, path, meta):
        self.f = open(path, "w")
        self.w(dict(type="meta", **meta))

    def w(self, rec):
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def speculate(world, gen_call, t_frozen, dt_guard):
    """正身世界上"存档->执行预测调用->回档->重冻时间->断言"。
    【照抄 exec_calls.replay_unit 的三连】。返回 spec 记录字段。"""
    code_x, modes = requote(gen_call, world.shell.user_ns)
    world.save_state(CKPT)
    try:
        eout = str(world.execute(code_x))[:TRUNC]
    finally:
        world.load_state(CKPT)
        world._set_datetime()
        if dt_guard:
            now = world.execute("print(DateTime.now())").strip()
            if now != t_frozen:
                raise RuntimeError(f"回档后时间漂了:{now!r} != {t_frozen!r}")
    ek = error_kind(eout)
    return dict(exec_code=code_x, arg_modes=modes, exec_out=eout,
                exec_ok=(ek is None), error_kind=ek)


def token_boundary(bounds, pos):
    """bounds = 每个流块结束处的 (n_chars, n_ids),n_chars 单调不减;
    返回不晚于字符位 pos 的最后一个边界 (n_chars, n_ids)。同一 n_chars 有多个
    边界(文本滞后于 id)时取 id 数最少的那个。没有就返回 None。
    只当 find_head 的起点:流文本会落后于 id(见 find_head),块边界不是准的。"""
    best = None
    for c, k in bounds:
        if c > pos:
            break
        if best is None or c > best[0]:
            best = (c, k)
    return best


def find_head(gen_ids, raw, pos, k0, decode):
    """head = 最短的 id 前缀,其解码文本盖住字符位 pos(句尾切口的起点 = 标点
    之后)。返回 (k, head_text)。也就是"含句尾标点的那个 token"为止:`.` 与
    ` Then` 分开时 head 止于 `.`;`.\\n\\n` 是一个 token 时 head 连它一起。
    这个规则只看模型的 token 序列,不看流怎么分块。

    为什么不能按块边界 (len(raw), len(gen_ids)) 算:vLLM 有 stop 串时压着
    len(stop)-1 个字符不吐(v1/engine/detokenizer.py get_next_output_text 的
    stop_buffer_length,<|return|> 是 10 字符 → 文本恒比 id 落后 9 字符 ≈ 2 个
    token;smoke 实测 decode(head_ids) 多出 ' We have'),多字节字符没凑齐时也压;
    生产端快过消费端时几个 token 并成一块。所以 k 要拿 decode 逐个核出来,
    块边界 k0 只当起点。decode 是 HTTP 调用,每次开火通常只要几次。
    head_text 与流文本的公共部分必须逐字相同(不同就抛错,不静默)。"""
    if not gen_ids:
        raise RuntimeError("find_head: 还没有生成 id")
    k = max(1, min(k0, len(gen_ids)))
    txt = decode(gen_ids[:k])
    while len(txt) < pos and k < len(gen_ids):          # 往前进到盖住 pos
        k += 1
        txt = decode(gen_ids[:k])
    while k > 1:                                        # 再退到最短
        prev = decode(gen_ids[:k - 1])
        if len(prev) < pos:
            break
        k, txt = k - 1, prev
    if len(txt) < pos:
        raise RuntimeError(f"find_head: 全部 {len(gen_ids)} 个 id 解码后 "
                           f"({len(txt)} 字符)盖不住切口 {pos}")
    n = min(len(txt), len(raw))
    if txt[:n] != raw[:n]:
        raise RuntimeError(f"find_head: decode(ids[:{k}]) 与流文本不一致:"
                           f"{txt[max(0, n - 60):n]!r} vs {raw[max(0, n - 60):n]!r}")
    return k, txt


def ids_sha(ids):
    """token id 列表的 sha1(逗号串);chat 臂存整段 prompt_token_ids,
    活跑臂只存这个,打分侧两边算同一个 sha 就是逐 id 比。"""
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()


def sep_for(head):
    """NOTE 前的缝(2026-08-18 splice_replay D5'):head 以空白结尾就不再加换行
    (换行切口另起一行、空格切口 inline),否则加一个 \\n。head 是模型自己的
    token,NOTE 单独编码,模型的最后一个 token 不会被合并改写。"""
    return "" if head[-1:].isspace() else "\n"


def log_resume(log, step, pending, gen_ids, st):
    """重发续写出的同位新 id 与上次中断时被丢弃的 id 逐位比
    (nofill 下这就是"token 同的重发能不能复现模型自己的续写")。"""
    new = gen_ids[pending["head_tok"] + pending["note_tok"]:]
    ov = pending["overflow_ids"]
    m = 0
    while m < min(len(new), len(ov)) and new[m] == ov[m]:
        m += 1
    log.w(dict(type="resume", step=step, overflow_tok=len(ov),
               new_tok=len(new), match_len=m,
               identical=(m == len(ov) and len(new) >= len(ov)),
               finish=st.finish, stop_reason=st.stop_reason))


def gen_step(a, prefix_ids, task, hist, world, t_frozen, dt_guard, log, step):
    """v4:一步一枪流式生成,与 w0 的 chat 解码同构。
    prefix_ids = harmony 前缀 token id,止于 <|start|>assistant(无预填);
    raw = 之后的全部生成文本(模型自己写通道头),gen_ids = 与之对应的 token id
    (流带 return_token_ids,逐块攒;v6 2026-08-18 ident3)。
    发请求时 prompt = prefix_ids + gen_ids:不出手的步 prompt 就是 chat 端点
    会喂给引擎的那串 id;开火后重发的 head 也是模型自己生成的 id 原样
    (切口退到不晚于它的 token 边界,重发前 /decode 核对),NOTE 单独 /encode
    接在后面——不再把文本整段重分词,重分词缝只剩 NOTE 自己。
    探测骑在流上:新句子切口出现就打分(真探针 /score;或 --fire-nth-cut 伪
    触发:第 N 个切口开火),开火才 close() 中断、(--nofill 则什么都不塞)、重发
    续写——不开火的步是单请求不间断解码,与 chat 完全同款。
    每次中断把切口后已生成、被丢弃的 id 存进 spec 记录(overflow_ids),重发续
    写出的同位新 id 与它逐位比,写一条 resume 记录(match_len/identical)。
    返回 (thinking, content, usage聚合, 溢出账, 出手数, gen_ids)。"""
    raw = ""
    gen_ids = []
    bounds = [(0, 0)]          # 每块结束处 (len(raw), len(gen_ids))
    usage = dict(prompt_tok=0, gen_tok=0, req=0)
    discard = dict(chars=0, tokens=0, events=0)
    checked = set()            # 已探测切口(thinking 坐标)
    n_checked = 0
    n_inject = 0
    probing = not a.no_probe
    accepted = 0               # 注入点之前的 thinking 长度(重启后不回探)
    pending = None             # 上次中断丢弃的 id,等重发续写出来后逐位比

    while True:
        # prompt 一律 token id:前缀来自 /render(chat 同款渲染);gen_ids 是
        # 模型自己生成的 id(开火后 = head_ids + NOTE 的 id)
        prompt = list(prefix_ids) + list(gen_ids)
        # 步预算按**留下的** id 算(chat 一步 8192 全是留下的;中断丢弃的溢出
        # 只进 usage 账,不吃预算——否则 nofill 步比别的臂早顶到 length)
        st = open_stream(a.base_url, dict(
            model=a.model, prompt=prompt,
            max_tokens=max(1, a.max_step_tokens - len(gen_ids)),
            temperature=a.temperature, stop=a.stop,
            skip_special_tokens=False), a.timeout)
        usage["req"] += 1
        fired = False
        for delta, ids in st:
            raw += delta
            gen_ids += ids
            bounds.append((len(raw), len(gen_ids)))
            if not probing or n_inject >= a.max_inject_per_step:
                continue
            if not any(c in delta for c in ".!?\n"):
                continue           # 没有新句尾就不必重扫(流式逐 token 到达)
            span = think_span(raw)
            if span is None:
                continue           # 通道头还没写全
            ts, te = span
            if te < len(raw):
                probing = False    # analysis 已闭合,进入 commentary/final
                continue
            t_all = raw[ts:]
            for cut in sent_starts(t_all):
                if cut in checked or cut <= accepted:
                    continue
                if n_checked >= MAX_BOUNDS:
                    probing = False
                    break
                checked.add(cut)
                n_checked += 1
                if a.fire_nth_cut:
                    # 伪触发(探针权重已删):第 N 个切口开火,不打 /score /gen
                    s = dict(conf=None, label=None,
                             fired=(n_checked == a.fire_nth_cut))
                else:
                    s = http_json(a.probe_url + "/score",
                                  dict(text=assemble(task, hist, t_all[:cut])))
                if not s["fired"]:
                    continue
                # ---- 开火:head = 盖住句尾标点的最短 id 前缀(模型自己的 id)----
                pos = ts + cut                          # raw 坐标(标点之后)
                _, k0 = token_boundary(bounds, pos)
                k, head_txt = find_head(
                    gen_ids, raw, pos, k0,
                    lambda ids: http_json(a.probe_url + "/decode",
                                          dict(ids=ids))["text"])
                head_ids = gen_ids[:k]
                overflow_ids = gen_ids[k:]
                if a.nofill:
                    g, note = None, ""
                    spec = dict(exec_code=None, arg_modes=None, exec_out=None,
                                exec_ok=None, error_kind=None)
                else:
                    g = http_json(a.probe_url + "/gen",
                                  dict(text=assemble(task, hist, t_all[:cut])))
                    spec = speculate(world, g["call"], t_frozen, dt_guard)
                    note = sep_for(head_txt) + NOTE_TMPL.lstrip("\n").format(
                        call=g["call"], result=spec["exec_out"])
                note_ids = (http_json(a.probe_url + "/encode",
                                      dict(text=note))["ids"] if note else [])
                discard["chars"] += max(0, len(raw) - len(head_txt))
                discard["tokens"] += len(overflow_ids)
                discard["events"] += 1
                log.w(dict(type="spec", step=step, cut=cut,
                           n_checked=n_checked, conf=s["conf"],
                           pred_label=s["label"],
                           gen_call=g["call"] if g else None,
                           note=note, nofill=bool(a.nofill),
                           discarded_chars=max(0, len(raw) - len(head_txt)),
                           head_chars=len(head_txt) - ts,
                           head_ends_ws=head_txt[-1:].isspace(),
                           head_tok=k, note_tok=len(note_ids),
                           head_tail=head_txt[-40:],
                           n_chunks=st.n_chunks,
                           overflow_ids=overflow_ids, **spec))
                if pending is not None:     # 同步第二次开火:先把上次的账结掉
                    log_resume(log, step, pending, gen_ids, st)
                raw = head_txt + note        # 文本以 decode(head) 为准,溢出丢弃
                gen_ids = head_ids + note_ids
                bounds = [(len(raw), len(gen_ids))]
                pending = dict(head_tok=k, note_tok=len(note_ids),
                               overflow_ids=overflow_ids)
                accepted = (len(head_txt) - ts) + len(note)
                checked = set()                # 偏移整体位移,旧集合作废
                n_inject += 1
                fired = True
                break
            if fired:
                break
        # 账:完整收尾有 usage;被中止时用本请求收到的 id 数(含丢弃的溢出)
        if st.usage:
            usage["prompt_tok"] += st.usage.get("prompt_tokens", 0)
            usage["gen_tok"] += st.usage.get("completion_tokens", 0)
        else:
            usage["gen_tok"] += st.n_ids
        if pending is not None and not fired:
            log_resume(log, step, pending, gen_ids, st)
            pending = None
        if fired:
            st.close()
            continue               # 开火后续写(head 是模型自己的 id)
        break                      # stop=<|return|> 或预算打满,整步收官

    # 收官核对:文本与 id 要对得上(decode(gen_ids) = raw + 停止 token 的文本
    # 或 = raw)。不等就打印告警并把 text_ids_consistent=False 记进 gen 记录,
    # 打分侧能看见;不在这里抛——整题成绩不能因记录核对失败作废。
    consistent = None
    if n_inject:
        full = http_json(a.probe_url + "/decode", dict(ids=gen_ids))["text"]
        consistent = full.startswith(raw) and \
            full[len(raw):] in ("", "<|return|>", "<|call|>")
        if not consistent:
            print(f"    WARN step {step}: decode(gen_ids) 与 raw 不一致 "
                  f"(len {len(full)} vs {len(raw)})", flush=True)
    t_final, content = parse_step(raw)
    return (t_final, content, usage, discard, n_inject, gen_ids, consistent)


def probe_cfg_problem(cfg, need_decode=False):
    """/health 回显不合口径就给一句拒跑理由,合口径返回 None。
    老服务的 /render 出的是 jinja 文本,与 chat 端点两处不齐(harmony_render.py
    文件头);教训:老 8790 曾静默丢 effort 字段按 high 渲,指错服务不报错只出错数。"""
    if cfg.get("render") != "harmony_ids":
        return (f"probe 服务 /health 没回 render=harmony_ids(拿到 "
                f"{cfg.get('render')!r}),是旧版 probe_server,拒跑")
    if need_decode and not cfg.get("decode"):
        return ("probe 服务 /health 没回 decode=true:开火重发要 /decode 核对 "
                "head_ids(2026-08-18 ident3),是旧版 probe_server,拒跑")
    return None


def claim(outdir, tid):
    """mkdir 抢票(NFS 上原子)。谁建成谁跑,输家静默跳过。

    票根只在工人硬死(连 task_error final 都没写)时残留,所以发射脚本
    每次起跑前整个清掉 .claims/——凡是没有 final 的题都重新开抢。
    """
    d = outdir / ".claims"
    d.mkdir(exist_ok=True)
    try:
        (d / tid).mkdir()
        return True
    except FileExistsError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", required=True, help="vLLM /v1 端点")
    ap.add_argument("--probe-url", required=True, help="probe_server 端点")
    ap.add_argument("--model", default=None,
                    help="缺省 gpt-oss-120b(预设也没给时)")
    ap.add_argument("--split", default="test_normal")
    ap.add_argument("--n", type=int, default=0, help="0 = 整个 split")
    ap.add_argument("--task-ids", default="",
                    help="逗号分隔,点名只跑这些题(冒烟验证用);"
                         "先于 --n 与分片/领题生效")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", required=True, help="appworld experiment_name 前缀")
    ap.add_argument("--chunk-tokens", type=int, default=64)
    ap.add_argument("--tail-tokens", type=int, default=1024,
                    help="<|end|> 之后(或不挂探针时)的段长")
    ap.add_argument("--max-inject-per-step", type=int, default=1)
    ap.add_argument("--preset", default=None,
                    help="configs/presets/<名>.json 的一套生成设置"
                         "(effort/temperature/步预算/stop);"
                         "命令行显式给的参数压过预设值")
    ap.add_argument("--effort", default=None,
                    choices=["high", "medium", "low"],
                    help="harmony 模板的 Reasoning 档;缺省 high(预设也没给时)。"
                         "采集口径=high,effort 对照臂传 low/medium")
    ap.add_argument("--no-probe", action="store_true",
                    help="对照臂:同一条分段生成路径,不挂探针不注入")
    ap.add_argument("--fire-nth-cut", type=int, default=0,
                    help="伪触发(探针权重已删时用):每步第 N 个句尾切口开火一次,"
                         "不打 /score;0=用真探针 /score")
    ap.add_argument("--nofill", action="store_true",
                    help="开火时什么都不塞(不 /gen、不投机执行、不写 NOTE),"
                         "只中断+按模型自己的 token id 重发续写")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--pool", action="store_true",
                    help="动态领题:工人跑完一题就去全量单抢下一题(mkdir 原子票),"
                         "慢题不再堵死静态分片;--shard-id 退化为工人号")
    ap.add_argument("--keep-outputs", action="store_true",
                    help="保留 appworld 每题的输出目录(默认跑完即删,配额教训)")
    ap.add_argument("--selftest-shadow", metavar="TRAJ",
                    help="不连任何服务:重放这条已采轨迹的前若干步,做一次"
                         "存档/执行/回档三连,再继续重放并逐字核对——证明投机"
                         "执行不污染正身。")
    a = ap.parse_args()
    if a.no_probe and (a.fire_nth_cut or a.nofill):
        ap.error("--no-probe 与 --fire-nth-cut/--nofill 互斥(no probe 臂不开火)")

    # --preset 合并(CLI 显式值 > 预设 client 节 > 原缺省),展开值挂回 a,
    # 下游只认 a.*;不传 --preset 时逐键落回原缺省,行为与加参数前一致
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.append(root)
    from preset_loader import load_preset, merge_client
    pre = load_preset(a.preset) if a.preset else None
    eff = merge_client(
        {"reasoning_effort": a.effort},
        (pre or {}).get("client"),
        {"reasoning_effort": "high", "temperature": 0.0,
         "max_tokens": MAX_STEP_TOKENS, "stop": DEFAULT_STOP})
    a.effort = eff["reasoning_effort"]
    a.temperature = eff["temperature"]
    a.max_step_tokens = eff["max_tokens"]
    a.stop = eff["stop"]
    a.model = (a.model
               or ((pre or {}).get("server") or {}).get("served_model_name")
               or "gpt-oss-120b")

    # 路径一律先 resolve 再 chdir【exec_calls.py 同款教训】
    outdir = Path(a.outdir).resolve()
    shadow_traj = Path(a.selftest_shadow).resolve() if a.selftest_shadow \
        else None
    outdir.mkdir(parents=True, exist_ok=True)
    R.check_system_verbatim()
    os.chdir(APPWORLD_HOME)
    from appworld import AppWorld, load_task_ids

    if shadow_traj:
        return selftest_shadow(AppWorld, shadow_traj, a)

    # /render 两个臂都要(appworld venv 没有 transformers),服务必须在
    with urllib.request.urlopen(a.probe_url + "/health", timeout=30) as r:
        probe_cfg = json.loads(r.read())
    print(f"probe: {probe_cfg}", flush=True)
    bad = probe_cfg_problem(probe_cfg, need_decode=not a.no_probe)
    if bad:
        sys.exit(bad)

    ids = load_task_ids(a.split)
    if a.task_ids:
        want = [t.strip() for t in a.task_ids.split(",") if t.strip()]
        missing = sorted(set(want) - set(ids))
        if missing:
            sys.exit(f"--task-ids 有 {len(missing)} 个不在 split "
                     f"{a.split}: {missing}")
        ids = want
    if a.n:
        ids = ids[: a.n]
    if a.pool:
        # 动态领题:不切片,所有工人抢同一张全量单;按工人号错位起跑,
        # 抢锁碰撞只发生在追尾时。静态分片的教训:一道慢题堵死整条分片,
        # 别的分片跑完了也帮不上,尾巴全是它拖的。
        ids = ids[a.shard_id:] + ids[: a.shard_id]
    else:
        ids = ids[a.shard_id:: a.num_shards]
    exp = a.exp if a.num_shards == 1 else f"{a.exp}_s{a.shard_id}"
    print(f"shard {a.shard_id}/{a.num_shards}: {len(ids)} tasks exp={exp} "
          f"pool={a.pool}", flush=True)

    for tid in ids:
        out_path = outdir / f"live_{tid}.jsonl"
        if a.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            if not a.pool:              # pool 模式 12 工人各刷一遍,太吵
                print(f"task={tid} SKIP (done)", flush=True)
            continue
        if a.pool and not claim(outdir, tid):
            continue
        try:
            run_task(AppWorld, tid, exp, out_path, a, probe_cfg)
        except Exception as e:
            # 单题炸了不许陪葬整个分片:补一条失败 final(resume 不会再撞),
            # 打印后继续下一题。教训:首跑 400 没人接,5/24 分片整队阵亡
            with open(out_path, "a") as f:
                f.write(json.dumps(dict(
                    type="final", steps=-1, completed=False,
                    abort=f"task_error:{type(e).__name__}",
                    eval=dict(success=False,
                              task_error=str(e)[:300])), ensure_ascii=False)
                    + "\n")
            print(f"task={tid} TASK_ERROR {type(e).__name__}: {str(e)[:200]}",
                  flush=True)
        if not a.keep_outputs:             # appworld 每题 ~90KB,配额教训
            shutil.rmtree(Path("experiments/outputs") / exp / "tasks" / tid,
                          ignore_errors=True)


def run_task(AppWorld, tid, exp, out_path, a, probe_cfg):
    with AppWorld(task_id=tid, experiment_name=exp,
                  random_seed=APPWORLD_SEED) as world:
        instr = world.task.instruction
        log = W(out_path, dict(
            env="appworld", task_id=tid, model=a.model, instruction=instr,
            arm=("no_probe" if a.no_probe else
                 "probe_nofill" if a.nofill else "probe"),
            fire=(f"nth_cut:{a.fire_nth_cut}" if a.fire_nth_cut else "probe"),
            nofill=bool(a.nofill), token_exact_resend=True,
            effort=a.effort, probe=probe_cfg, preset=a.preset,
            gen_settings=dict(temperature=a.temperature,
                              max_step_tokens=a.max_step_tokens,
                              stop=a.stop),
            chunk_tokens=a.chunk_tokens, tail_tokens=a.tail_tokens,
            max_inject_per_step=a.max_inject_per_step,
            appworld_seed=APPWORLD_SEED, date=time.strftime("%Y-%m-%d")))
        # 时间守卫基准【照抄 exec_calls】:开局冻结时刻
        t_frozen = world.execute("print(DateTime.now())").strip()
        dt_guard = not t_frozen.startswith("Execution failed")

        msgs = [{"role": "system", "content": R.SYSTEM},
                {"role": "user",
                 "content": f"Task from supervisor: {instr}"}]
        hist = []                          # 探针输入的 (action, result) 历史
        completed, step, abort = False, -1, None
        try:
            for step in range(a.max_steps):
                prefix_ids = http_json(a.probe_url + "/render",
                                       dict(messages=msgs,
                                            effort=a.effort))["prefix_ids"]
                t0 = time.time()
                # v4:不预填通道头,prompt 止于 <|start|>assistant(chat 同款)
                (think, content, usage, discard, n_inj, gen_ids,
                 consistent) = gen_step(a, prefix_ids, instr, hist, world,
                                        t_frozen, dt_guard, log, step)
                # prefix 不整段存(每步几万 id),存 sha1 + 长度;chat 臂存了整段
                # prompt_token_ids,打分侧对 sha 就是逐 id 比
                log.w(dict(type="gen", step=step, reasoning=think,
                           content=content, usage=usage, discard=discard,
                           n_inject=n_inj, wall_s=round(time.time() - t0, 2),
                           prefix_tok=len(prefix_ids), prefix_sha=ids_sha(prefix_ids),
                           text_ids_consistent=consistent, gen_ids=gen_ids))
                msgs.append({"role": "assistant", "content": content})
                m = re.search(r"```python\s*(.*?)```", content, re.S)
                if not m:
                    log.w(dict(type="env", step=step, action=None,
                               result="NO_CODE_BLOCK"))
                    msgs.append({"role": "user", "content": R.NO_CODE_MSG})
                    continue
                code = m.group(1)
                out = str(world.execute(code))
                log.w(dict(type="env", step=step, action=code,
                           result=out[:TRUNC]))
                msgs.append({"role": "user",
                             "content": f"Execution output:\n{out[:TRUNC]}"})
                hist.append((code.strip(), out[:TRUNC]))
                if world.task_completed():
                    completed = True
                    break
        except urllib.error.HTTPError as e:
            # vLLM 400 = prompt 顶到 65536 上下文,连一个 chunk 都放不下,
            # 这一题走不下去了。世界还开着:照常 evaluate,把失败记诚实。
            # 双臂同规则中止,口径对称;非 400 照旧往上抛
            if e.code != 400:
                raise
            abort = "context_overflow_400"
        try:
            ev = world.evaluate()
            ev = ev.to_dict() if hasattr(ev, "to_dict") else ev
            if not isinstance(ev, dict):
                ev = dict(repr=str(ev)[:600])
        except Exception as e:
            ev = dict(eval_error=str(e)[:600])
        log.w(dict(type="final", steps=step + 1, completed=completed,
                   abort=abort, eval=ev))
        log.close()
        print(f"task={tid} steps={step + 1} completed={completed} "
              f"eval={json.dumps(ev, ensure_ascii=False)[:120]}", flush=True)


def selftest_shadow(AppWorld, traj_path, a):
    """投机执行三连的无服务自检:重放已采轨迹前 K 步 -> 三连一次 -> 继续重放,
    每步输出与轨迹录下的 result 逐字比。回档要是没回干净,后续步立刻漂。"""
    from exec_calls import load_steps
    steps = load_steps(traj_path)
    if len(steps) < 3:
        print(f"轨迹只有 {len(steps)} 步,换条长的")
        return 1
    k = min(2, len(steps) - 1)
    tid = json.loads(open(traj_path).readline())["task_id"]
    probe_call = "apis.api_docs.show_app_descriptions()"
    with AppWorld(task_id=tid, experiment_name=f"{a.exp}_shadowtest",
                  random_seed=APPWORLD_SEED) as world:
        t_frozen = world.execute("print(DateTime.now())").strip()
        dt_guard = not t_frozen.startswith("Execution failed")
        bad = 0
        for i, (st, code, recorded) in enumerate(steps):
            if i == k:
                spec = speculate(world, probe_call, t_frozen, dt_guard)
                print(f"[三连@step{st}] exec_ok={spec['exec_ok']} "
                      f"out={spec['exec_out'][:80]!r}", flush=True)
            got = str(world.execute(code))[:TRUNC]
            same = got == recorded
            bad += 0 if same else 1
            print(f"step{st} {'OK' if same else 'DRIFT'}", flush=True)
            if not same:
                print(f"  want={recorded[:100]!r}\n  got ={got[:100]!r}")
    print(f"selftest-shadow: {'PASS' if bad == 0 else f'FAIL({bad} 步漂了)'}",
          flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
