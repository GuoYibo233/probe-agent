"""活跑注入线驱动器(appworld venv,纯 CPU)。设计书:plans/2026-08-01-live-inject-design.md

回答的问题:探针实时出手、把预测调用的真实执行返回注进思考,**整道题**还做不做
得对、省不省 token。这是回放线(单步续写)给不出的任务级成绩,2026-08-01 用户
拍板立项。评测全程不判预测对错:出手就执行、返回什么注什么(报错也注)。

一步之内(设计书 §2):
  1. 消息历史照采集脚本拼(SYSTEM 从 rebuild 取,启动时回源核对);
  2. harmony 前缀问探针服务要(/render;appworld venv 没有 transformers);
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
        错误种类、注入行全文
  env   每步真代码与执行输出(与采集侧同款)
  final steps/completed/eval(结构化 dict,不存 str——打分要读它)

用法(冒烟,val 分区 2 题;测试堆不拿来调试):
  envs/appworld/venv/bin/python pipeline/inject/live_appworld.py \\
      --base-url http://tokyo108:8103/v1 --probe-url http://tokyo108:8790 \\
      --split dev --n 2 --outdir pipeline/inject/runs/live_smoke \\
      --exp live_smoke
  对照臂(同路径不挂探针,回放线 nofill 的活跑版): 加 --no-probe
"""

import argparse
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
from replay_inject import (DEFAULT_STOP, FINAL_OPEN, NOTE_TMPL,  # noqa: E402
                           post_completions)

APPWORLD_HOME = "/home/y-guo/reproduce/new1/envs/appworld"
END_MARK = "<|end|>"
MAX_BOUNDS = 64            # rules.MAX_BOUNDS 同值:活跑最多查这么多切口(§4.2)
MAX_STEP_TOKENS = 8192     # 采集时 max_tokens=8192(common.py:20),整步上限对齐


def sent_cuts(text):
    """真实句子级切口(不含全文末尾伪切口)。

    与 rules.boundaries 的差别(设计书 §4.2):不做 MAX_BOUNDS 等距抽样——
    抽样结果随文本增长而变,活跑下会让"已探测过的切口"集合失效;上限改由
    调用方数"已探测次数"来管。MIN_THINK 过滤照抄。
    """
    pts = sorted({m.end() for m in SENT_RE.finditer(text)})
    return [p for p in pts if len(text[:p].strip()) >= MIN_THINK // 2]


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


def gen_step(a, prompt_head, task, hist, world, t_frozen, dt_guard, log, step):
    """分段生成一整步。prompt_head = harmony 前缀 + ANALYSIS_OPEN。
    返回 (thinking, content, usage聚合, 溢出账, 出手数)。"""
    think = ""                 # 已接受的思考(触发时截到切口、拼上 NOTE)
    raw_tail = ""              # think 之后累积的生成文本(可能含 <|end|> 与 final)
    usage = dict(prompt_tok=0, gen_tok=0, req=0)
    discard = dict(chars=0, events=0)
    checked = set()            # 已探测过的切口(在 think+raw_tail 里的字符偏移)
    n_checked = 0
    n_inject = 0
    probing = not a.no_probe

    while True:
        prompt = prompt_head + think + raw_tail
        r = post_completions(a.base_url, dict(
            model=a.model, prompt=prompt,
            max_tokens=(a.chunk_tokens if probing and END_MARK not in raw_tail
                        else a.tail_tokens),
            temperature=0.0, stop=DEFAULT_STOP,
            skip_special_tokens=False), a.timeout)
        ch = r["choices"][0]
        raw_tail += ch["text"]
        usage["prompt_tok"] += r["usage"]["prompt_tokens"]
        usage["gen_tok"] += r["usage"]["completion_tokens"]
        usage["req"] += 1

        done = (ch.get("finish_reason") == "stop"
                or usage["gen_tok"] >= MAX_STEP_TOKENS)

        if probing and n_inject < a.max_inject_per_step \
                and END_MARK not in raw_tail:
            # 思考还在写:探测新切口。思考全文 = think + raw_tail
            t_all = think + raw_tail
            for cut in sent_cuts(t_all):
                if cut in checked or cut <= len(think):
                    continue
                if n_checked >= MAX_BOUNDS:
                    probing = False
                    break
                checked.add(cut)
                n_checked += 1
                s = http_json(a.probe_url + "/score",
                              dict(text=assemble(task, hist, t_all[:cut])))
                if s["fired"]:
                    g = http_json(a.probe_url + "/gen",
                                  dict(text=assemble(task, hist, t_all[:cut])))
                    spec = speculate(world, g["call"], t_frozen, dt_guard)
                    note = NOTE_TMPL.format(call=g["call"],
                                            result=spec["exec_out"])
                    discard["chars"] += len(t_all) - cut
                    discard["events"] += 1
                    log.w(dict(type="spec", step=step, cut=cut,
                               n_checked=n_checked, conf=s["conf"],
                               pred_label=s["label"], gen_call=g["call"],
                               note=note, discarded_chars=len(t_all) - cut,
                               **spec))
                    think = t_all[:cut] + note
                    raw_tail = ""
                    checked = set()     # 偏移随截断+注入整体位移,旧集合作废;
                    n_inject += 1       # cut <= len(think) 的过滤挡住重查旧文本
                    if n_inject >= a.max_inject_per_step:
                        probing = False  # 注满配额:后面换大段生成,少打请求
                    done = False        # 注入后必须继续生成
                    break
        if done:
            break

    full = think + raw_tail
    if END_MARK in full:
        t_final, _, rest = full.partition(END_MARK)
        content = rest.split(FINAL_OPEN, 1)[1] if FINAL_OPEN in rest else ""
    else:                       # 整步没走到 final(超长截断):全算思考
        t_final, content = full, ""
    return (t_final, content.strip(), usage, discard, n_inject)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", required=True, help="vLLM /v1 端点")
    ap.add_argument("--probe-url", required=True, help="probe_server 端点")
    ap.add_argument("--model", default="gpt-oss-120b")
    ap.add_argument("--split", default="test_normal")
    ap.add_argument("--n", type=int, default=0, help="0 = 整个 split")
    ap.add_argument("--max-steps", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--exp", required=True, help="appworld experiment_name 前缀")
    ap.add_argument("--chunk-tokens", type=int, default=64)
    ap.add_argument("--tail-tokens", type=int, default=1024,
                    help="<|end|> 之后(或不挂探针时)的段长")
    ap.add_argument("--max-inject-per-step", type=int, default=1)
    ap.add_argument("--no-probe", action="store_true",
                    help="对照臂:同一条分段生成路径,不挂探针不注入")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--keep-outputs", action="store_true",
                    help="保留 appworld 每题的输出目录(默认跑完即删,配额教训)")
    ap.add_argument("--selftest-shadow", metavar="TRAJ",
                    help="不连任何服务:重放这条已采轨迹的前若干步,做一次"
                         "存档/执行/回档三连,再继续重放并逐字核对——证明投机"
                         "执行不污染正身。")
    a = ap.parse_args()

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

    ids = load_task_ids(a.split)
    if a.n:
        ids = ids[: a.n]
    ids = ids[a.shard_id:: a.num_shards]
    exp = a.exp if a.num_shards == 1 else f"{a.exp}_s{a.shard_id}"
    print(f"shard {a.shard_id}/{a.num_shards}: {len(ids)} tasks exp={exp}",
          flush=True)

    for tid in ids:
        out_path = outdir / f"live_{tid}.jsonl"
        if a.resume and out_path.exists() and \
                '"type": "final"' in out_path.read_text():
            print(f"task={tid} SKIP (done)", flush=True)
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
            arm=("no_probe" if a.no_probe else "probe"), probe=probe_cfg,
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
                prefix = http_json(a.probe_url + "/render",
                                   dict(messages=msgs))["prefix"]
                t0 = time.time()
                think, content, usage, discard, n_inj = gen_step(
                    a, prefix + R.ANALYSIS_OPEN, instr, hist, world,
                    t_frozen, dt_guard, log, step)
                log.w(dict(type="gen", step=step, reasoning=think,
                           content=content, usage=usage, discard=discard,
                           n_inject=n_inj, wall_s=round(time.time() - t0, 2)))
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
