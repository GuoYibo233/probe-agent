"""miss_policy=execute 的 exec 段:把探针预测出的调用放回 appworld 真环境里执行。

要回答的问题:skip 档在探针猜错时直接不注入,于是"猜错的代价"从账上消失了
(1061 个出手事件里 372 个猜错被跳过,正确率轴偏乐观)。execute 档要让每一次
出手都真的落地:把该题的环境重放到那一步,执行预测出的那条调用,**不管返回的是
真结果还是报错,都原样注入**。猜错的代价这才进账。

做法(每个 unit 一个 AppWorld 实例,按 step 升序前进):
  1. 到达目标 step 之前,先把该 step 上的事件处理掉——此时环境状态正是模型
     当时写那段思考时面对的状态;
  2. `save_state` 存档 → 执行"补回引号后的预测调用" → `load_state` 回档 →
     `_set_datetime()` 重新冻时间 → 断言冻结时刻没漂;
  3. 执行该 step 录下的真代码,把输出与轨迹里录下的 result 逐字比,
     不一致就把该 unit 之后的事件标 prefix_verbatim=False(见已知偏差①)。

**这个文件是整条流水线里唯一 import appworld 的地方**,只能用
`envs/appworld/venv/bin/python` 跑;cprobe-env 里 `import appworld` 是
ModuleNotFoundError(实测)。所以 exec 段做成独立文件 + 独立解释器 + jsonl 交接:
plan.jsonl(cprobe-env 产)→ 本文件 → exec_calls.jsonl →
`replay_inject.py merge-exec`(cprobe-env)→ plan_exec.jsonl。
纯 CPU,不占卡。

边界(execute 档做不到的那部分,别在报告里写成别的):
- **execute 档不产出 appworld 任务级成绩。** 本文件一个事件只执行"那一条预测
  调用",不让模型继续走完整题、也不调 `world.evaluate()`。所以它量到的是
  **单步调用一致率 + 猜错时注入的真实报错**,不是 appworld 的 Test 分数。
  真正的任务级那条轴需要 in-loop rollout(run_appworld.py 的循环里挂探针、
  触发就注入、走完整题再 evaluate),那是另一批采集,不在本文件范围内。

已知偏差(报告里都要带上,别静默):
① 前缀重放的保真度只在 3 条轨迹 28 步上实测过 100%(2026-08-01)。带随机性的
   api、时间相关的 api、4000 字符截断处的边界都可能漂。所以每一步都拿录下的
   result 逐字核对,漂了的事件标 prefix_verbatim=False / drift_step=<步号>,
   报告里单列——不核对就等于拿一个错的状态去执行预测调用再把结果当真账报。
② 注入内容依赖 requote 这个**启发式**:plan.jsonl 里的 gen_call 是 annotate 侧
   去掉引号的规范化串(annotate/rules.py:133 的 strip("\"'")),
   长这样 `apis.api_docs.show_api_doc(app_name=venmo, api_name=search_users)`,
   直接执行全是 NameError。补引号的分支逐参数落进 arg_modes,报告里给分支计数。
   `{app_name, api_name}` 强制成字符串这条是**经验硬编码**(appworld api_docs
   的这两个参数永远是字符串),换环境/换工具族会静默走错分支——所以要有验收线。
   **验收线只收三条同时成立的事件**:预测与真实一致(full_call_ok)、代码块只含
   1 个调用、且该代码块就是一句干净的 `print(调用)`(整行注释不算)。这三条里
   缺一条,"单独执行那条调用的输出"与"录下的整块 stdout"根本不可比,收进来只会
   给自己报假警——实测两种假警:①代码块是
   `print("passwords:", apis.supervisor.show_account_passwords())`,单调用没错,
   但录下的 stdout 多个前缀、还走 python repr 而不是 appworld 那个转 json 的
   print;②调用本身报错时 traceback 会回显源码,引号风格不同就逐字不等
   (轨迹里是 app_name="spotify",requote 补的是 'spotify')——所以报错的情况
   比 err_tail(),只比异常行之后的消息。
   实测(2026-08-01):前 4 个 unit 上 17/17;13 个 unit 80 个事件上 53/53
   (逐字 52 + 报错消息一致 1),排除 1 个不可比的。
⑥ 全量 1061 个事件里,hit+单调用的有 664 个,其中 643 个是干净 print
   ——验收线的分母就是这 643 个,另外 21 个不可比、单列不算。
③ execute 档把注入内容从"整块 stdout"换成"那一条调用的返回"。这其实修掉了
   replay_inject.py 文件头列的那条多调用偏差(99/1061 个事件的代码块含多个
   调用),代价是 hit 事件与已跑完的 skip/oracle 六点曲线不再逐字可比。
   所以 score 段必须按 inject_source 分桶,不许混成一条均值。
④ 缓存键里带 REQUOTE_VERSION:改了 requote 的规则必须把这个常量 +1,
   否则旧缓存会被静默复用。
⑤ 一个进程只能有一个活着的 AppWorld:`initialize()` 与 `load_state()` 都调
   `AppWorld.close_all()`(environment.py:368/751),它会停掉所有时间冻结器、
   清 DB 缓存、关掉 ApiCollection——第二个实例会把第一个静默弄坏。
   所以并发只能靠多进程 + 各自 experiment_name,不能在一个进程里开两个世界。

用法:
  # smoke(4 个 unit,约 1 分钟,纯 CPU;绿的标准见 --selfcheck 的退出码)
  envs/appworld/venv/bin/python pipeline/inject/exec_calls.py \\
      --plan pipeline/inject/runs/aw_gptoss_r10/plan.jsonl \\
      --out  /tmp/exec_smoke.jsonl --cache /tmp/exec_cache_smoke.jsonl \\
      --exp  smoke_execprobe --limit-units 4 --selfcheck

  # 全量:4 分片,每片一个进程(纯 CPU,可与别的 θ 点的 run 段并行)
  for i in 0 1 2 3; do envs/appworld/venv/bin/python \\
      pipeline/inject/exec_calls.py \\
      --plan pipeline/inject/runs/aw_gptoss_th0925/plan.jsonl \\
      --out  pipeline/inject/runs/aw_gptoss_th0925/exec_calls.jsonl \\
      --cache pipeline/inject/exec_cache/aw_gptoss.jsonl \\
      --exp  aw_exec_th0925 --num-shards 4 --shard-id $i & done; wait
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "annotate"))

from rules import AW_CALL, first_call_named            # noqa: E402

# appworld 的 path_store 要求进程 cwd 是这个目录(run_appworld.py:63 同)
APPWORLD_HOME = "/home/y-guo/reproduce/new1/envs/appworld"

# 采集时 world.execute 的输出截到 4000 字符再落盘
# 【照抄 envs/collect/run_appworld.py:105】。不截就让注入内容的长度分布与
# traj_hit 不可比,省 token 那条轴会静默偏移。
TRUNC = 4000

# 随机种子:AppWorld 的默认值就是 100(environment.py:97),采集时没显式传。
# 工程铁律是种子写进代码并落进报告,所以这里显式钉死并写进 meta。
APPWORLD_SEED = 100

# 回档用的存档名。固定一个名字反复覆盖(_save_state 是 delete_if_exists=True)
CKPT = "probe"

# requote 规则版本。**改了下面 requote() 的任何一条分支就必须 +1**,
# 否则缓存键不变、旧结果被静默复用(已知偏差④)
REQUOTE_VERSION = 1

IDENT = re.compile(r"^[A-Za-z_]\w*$")
POSKEY = re.compile(r"^pos\d+$")

# appworld 的 api_docs 这两个参数永远是字符串。经验硬编码,见已知偏差②
ALWAYS_STR = {"app_name", "api_name"}


# ------------------------------------------------------------- requote

def requote(call, user_ns):
    """把去引号的预测调用串补成可执行 python。返回 (代码, 每个参数走了哪条分支)。

    分支顺序(逐参数,顺序不能换):
      unparsable_raw  整串连 `apis.<app>.<api>(` 都凑不出来(全量 1061 条里有 2 条,
                      形如 `apis.login(...)`)。**原样丢进环境让它报错并计数,
                      不许 skip** —— skip 掉就又把探针猜错的代价抹掉了,
                      而这正是 execute 档要修的病。
      forced_str      键在 ALWAYS_STR 里,强制 repr 成字符串(全量 1454/1475)
      literal         ast.literal_eval 认得(数字/True/None/列表,全量 1 个)
      shell_var       是标识符且前缀重放后 shell 里真有这个变量
                      (接住 `access_token=access_token` 这类真变量引用)
      quoted          其余一律 repr 成字符串(全量 20 个里剩下的)
    参数顺序照 first_call_named 的出现顺序,不排序。

    **shell_var 这条分支本质上是有歧义的**,而且歧义在真实数据里就有:
    全量 1061 条里非 api_docs 的 20 个参数值,既有 `password=phone_password`
    (确实该当变量看)也有 `password=b4GXZH6`、`password=_7JMKRg`(是字面口令,
    却也符合标识符长相)。`v in user_ns` 这个条件把后者挡住了——口令串不会正好
    是个变量名——但只要哪次真撞上(比如模型给某个变量取名叫 `email`,而探针预测
    的又是字面值 `email`),就会静默走错分支。所以每个参数的分支都落进 arg_modes,
    报告里给计数;真要抓,看 hit 单调用事件的 matched_traj_result 那条验收线。
    """
    m = AW_CALL.search(call or "")
    if not m:
        return f"print({call})", ["unparsable_raw"]
    tool = f"apis.{m.group(1)}.{m.group(2)}"
    named = first_call_named(call, AW_CALL) or []
    parts, modes = [], []
    for k, v in named:
        pos = bool(POSKEY.match(k))          # 位置参数(全量 0 个,防御性保留)
        if k in ALWAYS_STR:
            val, mode = repr(v), "forced_str"
        else:
            try:
                ast.literal_eval(v)          # 数字 / True / None / 列表 / 字典
                val, mode = v, "literal"
            except Exception:
                if IDENT.match(v) and v in user_ns:
                    val, mode = v, "shell_var"
                else:
                    val, mode = repr(v), "quoted"
        parts.append(val if pos else f"{k}={val}")
        modes.append(("pos_" + mode) if pos else mode)
    return f"print({tool}({', '.join(parts)}))", modes


# 该步录下的代码是不是"就一句 print(某个 apis 调用)"。只有这种步的 stdout
# 才与"单独执行那条调用"可比 —— 实测有事件的代码块是
# `print("passwords:", apis.supervisor.show_account_passwords())`,
# 单调用没错,但录下的 stdout 多个前缀、而且走的是 python repr 而非 appworld
# 那个会转 json 的 print,拿它当验收线就是自己给自己报假警
# 故意不加 re.S:带 . 跨行会把 `print(apis.a.b())\nprint(apis.c.d())` 也认成
# 一句(末尾那个 `)` 匹配到第二句上去),踩过。多行的单调用块一律判成"不干净",
# 宁可保守地把它排除在验收线之外
BARE_PRINT = re.compile(r"print\(\s*apis\.\w+\.\w+\([^\n]*\)\s*\)")


def is_bare_print(code):
    """该步录下的代码是不是"就一句 print(某个 apis 调用)"(整行注释不算)。

    注释与空行不产生任何 stdout,所以带一行 `# 说明` 的代码块照样与"单独执行
    那条调用"可比。不剔注释就会把全量 664 个 hit+单调用事件里的 167 个误判成
    不可比(实测:497 -> 664),白白砍掉验收线的分母。
    """
    body = [ln for ln in (code or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    return len(body) == 1 and bool(BARE_PRINT.fullmatch(body[0].strip()))


def err_tail(out):
    """报错文本里去掉"回显源码"那几行,只留异常行及其后面的消息。不是报错返回 None。

    为什么要这个:appworld 的报错文本把出错的**源码行**原样回显进 traceback,
    所以"探针预测的调用"与"当时真执行的调用"哪怕语义完全一样,只要引号风格不同
    (轨迹里是 app_name="spotify",requote 补的是 app_name='spotify'),
    逐字比就会不一致。实测踩到过这一条。比异常行之后的消息才是比"错得一样不一样"。
    """
    if out is None or not out.startswith("Execution failed"):
        return None
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^([A-Za-z_][\w.]*)\s*:", line.strip()):
            return "\n".join(lines[i:])
    return out


def error_kind(out):
    """从 execute 的返回里认出错误种类。不是报错返回 None。

    这个函数是**唯一真源**:merge-exec 会拿 exec_out 重算一遍,不信缓存里那个
    字段 —— 否则改了分类规则,旧缓存里的旧标签会静默留在报告里。

    http_4xx 单独拎出来是因为 appworld 把"api 名字不存在""参数不对"都变成
    422 之类的状态码(实测:探针猜出 `apis.api_docs.show_api_doc(
    app_name='spotify', api_name='add_tracks_to_playlist')`,拿回
    `Exception: Response status code is 422: {"message":"No APIs with name ...`)。
    笼统记一个 Exception 就看不出探针到底错在哪。
    """
    if out is None or not out.startswith("Execution failed"):
        return None
    if "timed out" in out:
        return "timeout"
    if "Syntax error in line" in out:
        return "SyntaxError"
    m = re.search(r"Response status code is (\d+)", out)
    if m:
        return f"http_{m.group(1)}"
    # python traceback 的最后一行是 `ExcName: msg`,但 msg 可能自带换行
    # (上面那个 422 的 json 就占了最后一行),所以从后往前找第一个 `名字:`。
    # 注意别写成"名字必须以 Error/Exception 结尾"——裸的 `Exception:` 只有 9 个
    # 字符,会被"前缀 + 后缀"的正则漏掉(踩过)
    for line in reversed([x.strip() for x in out.splitlines() if x.strip()]):
        m = re.match(r"^([A-Za-z_][\w.]*)\s*:", line)
        if m:
            return m.group(1).rsplit(".", 1)[-1]
    return "unknown"


# ------------------------------------------------------------- traj / cache

def load_steps(traj_path):
    """轨迹里真正被执行过的步:[(step, 当时执行的代码, 当时录下的 result)]。

    直接取 env 记录的 action —— 它就是采集时传给 world.execute 的那个字符串
    (envs/collect/run_appworld.py:104-106),比拿 gen 的 content 再用 CODE_RE
    重抽一遍少一个环节。action is None 的步(NO_CODE_BLOCK)没执行过,跳过。
    """
    envs = {}
    with open(traj_path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("type") == "env" and r.get("action") is not None:
                envs[r["step"]] = r
    return [(st, envs[st]["action"], envs[st].get("result") or "")
            for st in sorted(envs)]


def prefix_sigs(steps):
    """每个 step 之前**真正执行过的代码**的累积指纹,给缓存键当轨迹身份用。

    为什么非有不可:appworld 的 unit 名在三个模型(gptoss/q35/q36)之间完全相同
    (`envs/runs/w0_aw_official/` 下三份、同名 unit 文件),但各自轨迹在同一个 unit
    上执行的代码不同,世界状态就不同。缓存键若只有 unit+step,换一批轨迹跑
    execute 会**静默**复用别人世界的执行结果;更糟的是命中缓存时前缀重放整段
    不跑,`prefix_verbatim` 直接抄缓存里的 True —— 既污染注入内容,又同时关掉
    唯一能发现污染的那个哨兵,报告里的 n_drift 会是个假 0。
    (实测复现过:把 plan 的 traj_path 从 appworld_gptoss 换成 appworld_q35,
    再用 gptoss 建的缓存跑,8/8 全部命中、一个世界都没建、exec_out 逐字相同。)

    世界状态由"这一步之前执行了什么"决定,所以指纹取前缀而非整条轨迹。
    """
    out, h = {}, hashlib.sha1()
    for st, action, _ in steps:
        out[st] = h.hexdigest()[:16]         # 该 step **之前**的前缀
        h.update(f"{st}\x00{action}\x00".encode())
    return out


def cache_key(unit, step, gen_call, psig):
    raw = f"{REQUOTE_VERSION}|{unit}|{step}|{psig}|{gen_call}"
    return hashlib.sha1(raw.encode()).hexdigest()


def cache_files(cache_path):
    """同一个 cache 主名下的所有分片文件。

    每个分片进程写自己的 `<stem>.s<id>.jsonl`(>4KB 的行用 O_APPEND 并发写会
    交错,所以不共享同一个文件),读的时候把兄弟文件全读进来 —— 六个 θ 点之间
    绝大部分预测调用因此能直接命中缓存(状态与 θ 无关)。

    匹配必须精确到 `<stem>.jsonl` 与 `<stem>.s<N>.jsonl` 两种形状——原来的
    前缀 glob(`<stem>*`)会把 `<stem>_v2.s0.jsonl`、`<stem>2.jsonl` 这类
    别的批次的缓存静默吞进来(审计 B8)。
    """
    p = Path(cache_path)
    if not p.parent.is_dir():
        return []
    pat = re.compile(re.escape(p.stem) + r"(\.s\d+)?" + re.escape(p.suffix) + r"$")
    return sorted(str(f) for f in p.parent.iterdir() if pat.fullmatch(f.name))


def _reqver_write(p, h):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")          # 四分片并发跑,写档要原子
    tmp.write_text(json.dumps({"requote_version": REQUOTE_VERSION,
                               "src_sha1": h}))
    os.replace(tmp, p)


def check_requote_version(cache_main):
    """机械守卫(审计 B8):requote()/cache_key() 的**可执行结构**变了但
    REQUOTE_VERSION 没 +1 就拒绝跑——键不变会静默复用旧口径的结果。
    注释/docstring 改动不算(先过 ast 归一化再取哈希)。
    档案存 <主名>.reqver.json,首跑自动建档;+1 后自动换档(旧键自然失效)。"""
    import ast
    import inspect
    src = inspect.getsource(requote) + inspect.getsource(cache_key)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    h = hashlib.sha1(ast.unparse(tree).encode()).hexdigest()
    p = cache_main.with_name(cache_main.stem + ".reqver.json")
    if p.exists():
        try:
            old = json.loads(p.read_text())
        except Exception:
            sys.exit(f"缓存版本档案损坏: {p}——人工确认后删掉重跑"
                     "(会按当前源码重建档案),别当成没档案静默放行。")
        if old.get("src_sha1") == h:
            if old.get("requote_version") != REQUOTE_VERSION:
                _reqver_write(p, h)     # 只 +1 没改源码:档案跟上常量
            return
        if old.get("requote_version") == REQUOTE_VERSION:
            sys.exit(
                f"requote()/cache_key() 的源码变了,但 REQUOTE_VERSION 还是 "
                f"{REQUOTE_VERSION}——缓存键不变,旧结果会被静默复用。"
                f"确认是逻辑变更就把 REQUOTE_VERSION +1 再跑;"
                f"档案: {p}")
    _reqver_write(p, h)


def load_cache(cache_path):
    cache = {}
    for fp in cache_files(cache_path):
        with open(fp) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:            # 半行(进程被杀)直接丢
                    continue
                if o.get("key"):
                    cache[o["key"]] = o
    return cache


# ------------------------------------------------------------- 一个 unit

def replay_unit(AppWorld, unit, rows, traj_path, exp, cache, cache_sink,
                stats, out, probe=True):
    """把一个 unit 重放到各事件所在的 step 并执行预测调用,记录追加进 out。

    落盘分工:执行结果**当场**写进 cache_sink(进程被杀也不白跑),事件记录追加
    进调用方给的 out 列表、由调用方统一写文件 —— 函数内不碰文件,免得漏写某条
    路径(比如整 unit 命中缓存那条);out 由调用方持有,所以 unit 中途炸了
    已经做完的事件也还在,不会白跑。

    probe=False 是"干净重放"模式:一个探测调用都不插,只逐步核对录下的 result。
    --selfcheck 在漂了的 unit 上用它给漂移定责(是重放本身不保真,还是探测调用
    写了库没回干净)。
    """
    steps = load_steps(traj_path)
    have = {st for st, _, _ in steps}
    # 这两张表让"比对录下的 result"这件事不依赖是否真去执行了(整 unit 命中
    # 缓存那条路径也要能算),所以在建世界之前先备好
    rec_of = {st: r for st, _, r in steps}
    psig = prefix_sigs(steps)                # 缓存键里的轨迹身份,见 prefix_sigs
    bare_of = {st: is_bare_print(c) for st, c, _ in steps}
    by_step = {}
    for r in rows:
        by_step.setdefault(r["step"], []).append(r)

    def compare(eout, st):
        """把"执行返回"与"轨迹里录下的 result"比三种:逐字 / 只比报错消息 /
        该步录下的代码是不是一句干净的 print(调用)。"""
        recorded = rec_of.get(st)
        return dict(matched_traj_result=(eout == recorded),
                    matched_traj_error=(
                        None if err_tail(eout) is None
                        or err_tail(recorded) is None
                        else err_tail(eout) == err_tail(recorded)),
                    traj_bare_print=bare_of.get(st))

    # 该 step 之前的步都得先执行到位;最后一个需要的 step 上的真代码不用再执行
    last_needed = max(by_step) if by_step else -1
    missing = [r for r in rows if r["step"] not in have]
    for r in missing:                        # 轨迹里这步没执行过(NO_CODE_BLOCK)
        out.append(dict(event=r["event"], unit=unit, step=r["step"],
                        gen_call=r["gen_call"], exec_code=None, arg_modes=None,
                        exec_out=None, exec_ok=None,
                        error_kind="step_not_in_traj",
                        prefix_verbatim=None, drift_step=None,
                        matched_traj_result=None, cache_hit=False, wall_s=0.0,
                        full_call_ok=r.get("full_call_ok"),
                        n_calls_in_block=r.get("n_calls_in_block")))
        stats["step_not_in_traj"] += 1

    todo = [r for r in rows if r["step"] in have]
    if not todo:
        return out

    # 全部命中缓存 -> 连世界都不用建(θ 之间补跑主要靠这条)
    hits = {r["event"]: cache.get(cache_key(unit, r["step"], r["gen_call"],
                                            psig[r["step"]]))
            for r in todo}
    if probe and all(hits.values()):
        for r in todo:
            c = dict(hits[r["event"]])
            c.pop("key", None)
            c.update(event=r["event"], unit=unit, step=r["step"],
                     gen_call=r["gen_call"], cache_hit=True, wall_s=0.0,
                     dt_guard=None, full_call_ok=r.get("full_call_ok"),
                     n_calls_in_block=r.get("n_calls_in_block"),
                     # 三个比对字段现算,不抄缓存里那份:老缓存可能是上一版
                     # 比法写的,抄过来就把旧口径静默带进报告
                     **compare(c.get("exec_out"), r["step"]))
            out.append(c)
            stats["cache_hit"] += 1
            stats["exec_ok" if c.get("exec_ok") else "exec_err"] += 1
        stats["unit_all_cached"] += 1
        return out

    world = AppWorld(task_id=unit, experiment_name=exp,
                     random_seed=APPWORLD_SEED)
    try:
        # 时间守卫的基准:单元开局的冻结时刻。load_state 只做 _load_state +
        # _execute_preamble,不重新冻时间(environment.py:748-754),所以回档后
        # 必须显式 _set_datetime() 再核一遍——不核就可能拿真实时间去执行调用。
        t_frozen = world.execute("print(DateTime.now())").strip()
        dt_guard = not t_frozen.startswith("Execution failed")
        if dt_guard:
            stats["dt_guard_ok"] += 1
            if t_frozen != str(world.task.datetime):
                stats["dt_ne_task_datetime"] += 1
        else:
            stats["dt_guard_broken"] += 1

        verbatim, drift_at, clean_outs = True, None, []
        for st, code, recorded in steps:
            if st > last_needed:
                break
            for i, r in enumerate(by_step.get(st, []) if probe else []):
                t0 = time.time()
                key = cache_key(unit, st, r["gen_call"], psig[st])
                hit = cache.get(key)
                if hit:
                    rec = dict(hit)
                    rec.pop("key", None)
                    rec.update(event=r["event"], unit=unit, step=st,
                               cache_hit=True)
                    stats["cache_hit"] += 1
                else:
                    code_x, modes = requote(r["gen_call"], world.shell.user_ns)
                    last_event_of_unit = (st == last_needed and
                                          i == len(by_step[st]) - 1)
                    # 存档 -> 执行 -> 回档,三连必须成对:漏回档不会报错,
                    # 但同 unit 后面所有事件的状态被静默污染(risk 2)。
                    # 所以 finally 兜底,并且回档后重新冻时间 + 断言。
                    world.save_state(CKPT)
                    try:
                        eout = str(world.execute(code_x))[:TRUNC]
                    finally:
                        if not last_event_of_unit:
                            world.load_state(CKPT)
                            world._set_datetime()
                            if dt_guard:
                                now = world.execute(
                                    "print(DateTime.now())").strip()
                                if now != t_frozen:
                                    raise RuntimeError(
                                        f"回档后时间漂了:{now!r} != "
                                        f"{t_frozen!r} ({unit} s{st})")
                    ek = error_kind(eout)
                    rec = dict(exec_code=code_x, arg_modes=modes,
                               exec_out=eout, exec_ok=(ek is None),
                               error_kind=ek,
                               prefix_verbatim=verbatim, drift_step=drift_at,
                               cache_hit=False, **compare(eout, st))
                    cache_sink.write(json.dumps(
                        dict(key=key, appworld_seed=APPWORLD_SEED,
                             requote_version=REQUOTE_VERSION, **rec),
                        ensure_ascii=False) + "\n")
                    cache_sink.flush()
                    rec.update(event=r["event"], unit=unit, step=st)
                rec.update(gen_call=r["gen_call"], dt_guard=dt_guard,
                           wall_s=round(time.time() - t0, 3),
                           full_call_ok=r.get("full_call_ok"),
                           n_calls_in_block=r.get("n_calls_in_block"))
                # prefix_verbatim / drift_step 反映"走到该事件时前缀有没有漂",
                # 缓存里那份是首次执行时的值,这里以本次重放为准
                rec["prefix_verbatim"], rec["drift_step"] = verbatim, drift_at
                out.append(rec)
                stats["exec_ok" if rec.get("exec_ok") else "exec_err"] += 1

            if st == last_needed:            # 到目标步就停,本步真代码不用执行
                break
            got = str(world.execute(code))[:TRUNC]
            clean_outs.append((st, got))
            if got != recorded and verbatim:
                verbatim, drift_at = False, st
                stats["unit_drift"] += 1
        return out if probe else clean_outs
    finally:
        world.close()


# ------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--plan", required=True, help="plan.jsonl(execute 或 skip 档都行)")
    ap.add_argument("--out", required=True, help="exec_calls.jsonl;分片会自动加 .s<id>")
    ap.add_argument("--cache", required=True,
                    help="跨 θ 复用的执行缓存(append-only jsonl,分片各写一份)")
    ap.add_argument("--exp", required=True, help="appworld experiment_name 前缀")
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--limit-units", type=int, default=0)
    ap.add_argument("--keep-outputs", action="store_true",
                   help="不删每个 unit 跑完后的 appworld 输出目录(默认删)。"
                        "appworld 每个 unit 留 ~90KB 的 dbs/checkpoints/logs,"
                        "而 /home 是有配额的共享盘(2026-08-01 实测过一次"
                        "Disk quota exceeded)—— 跑完就删,把占用压到一个 unit")
    ap.add_argument("--selfcheck", action="store_true",
                    help="只在 hit 且单调用的事件上算 MATCH/DIFF/EXEC_ERR,"
                         "有 DIFF 或有 unit 漂了就非零退出")
    a = ap.parse_args()

    # 路径一律先 resolve 再 chdir:先 chdir 后解析相对路径 = 静默找不到文件
    plan_p = Path(a.plan).resolve()
    out_p = Path(a.out).resolve()
    # 缓存的读写路径必须分开:**写**只写自己那一片(>4KB 的行并发 O_APPEND 会
    # 交错),**读**要读主名下所有兄弟分片。原来两者共用一个变量,加完 .s<id>
    # 后缀再拿去 glob,只能匹配到自己那片 —— 跨分片、跨 θ 的缓存复用从来没生效过
    # (而"θ 之间补跑靠缓存"正是 execute 档铺六个点的唯一省时机制)。
    cache_main = Path(a.cache).resolve()
    if a.num_shards > 1:                     # 一片一个文件,免得并发写交错
        out_p = out_p.with_name(f"{out_p.stem}.s{a.shard_id}{out_p.suffix}")
    cache_p = cache_main.with_name(
        f"{cache_main.stem}.s{a.shard_id}{cache_main.suffix}")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    cache_p.parent.mkdir(parents=True, exist_ok=True)

    plan = [json.loads(l) for l in open(plan_p)]
    by_unit = {}
    for p in plan:
        # plan 里的 traj_path 是**相对工程根**的(replay_inject.py 从根目录跑),
        # 而本文件要 chdir 到 envs/appworld —— 所以必须在 chdir 之前就锚回根目录。
        # 这条踩过:不锚就是 FileNotFoundError,整批 unit 全废
        tp = Path(p["traj_path"])
        p["traj_path"] = str(tp if tp.is_absolute() else
                             (PROJ_ROOT / tp).resolve())
        by_unit.setdefault(p["unit"], []).append(p)
    # 分片按 unit 切,同一 unit 的事件必须落在同一个进程(共用一个世界)
    # 【照抄 envs/collect/run_appworld.py:69】的切法
    units = sorted(by_unit)
    if a.limit_units:
        units = units[:a.limit_units]
    units = units[a.shard_id::a.num_shards]
    exp = a.exp if a.num_shards == 1 else f"{a.exp}_s{a.shard_id}"

    done = set()                             # 断点续跑
    if out_p.exists():
        for l in open(out_p):
            try:
                done.add(json.loads(l)["event"])
            except Exception:
                pass
    check_requote_version(cache_main)        # 逻辑变了没 +1 版本号 -> 拒绝跑
    cache = load_cache(cache_main)           # 读主名 -> 兄弟分片全进来
    print(f"shard {a.shard_id}/{a.num_shards}: {len(units)} units "
          f"{sum(len(by_unit[u]) for u in units)} events exp={exp} "
          f"已有 {len(done)} 条 缓存 {len(cache)} 条 seed={APPWORLD_SEED}",
          flush=True)

    os.chdir(APPWORLD_HOME)
    from appworld import AppWorld                              # noqa: E402

    stats = Counter()
    recs, unit_err, t00 = [], [], time.time()
    sink, csink = open(out_p, "a"), open(cache_p, "a")
    for i, u in enumerate(units):
        rows = [r for r in by_unit[u] if r["event"] not in done]
        if not rows:
            continue
        t0 = time.time()
        got = []
        try:
            replay_unit(AppWorld, u, rows, rows[0]["traj_path"], exp,
                        cache, csink, stats, got)
        except Exception as e:
            # unit 中途炸掉:已做完的事件照样落盘(got 是我们持有的),
            # 剩下的事件在 exec_calls.jsonl 里就是缺的 —— merge-exec 会把它们
            # 标成 exec_missing 并单独计数,绝不静默退回"没注入"
            unit_err.append(dict(unit=u, error=f"{type(e).__name__}: {e}",
                                 done=len(got), want=len(rows)))
            stats["unit_error"] += 1
            print(f"  UNIT FAIL {u}: {type(e).__name__}: {e} "
                  f"(已完成 {len(got)}/{len(rows)})", flush=True)
        recs += got
        for r in got:                        # 事件记录只在这里落盘,一条不漏
            sink.write(json.dumps(r, ensure_ascii=False) + "\n")
        sink.flush()
        if not a.keep_outputs:
            # 这个 unit 的世界已经关了,它的 dbs/checkpoints/logs 没人再读。
            # 留着就是 168 × 90KB 堆在配额盘上,还挡住下一个 θ 点
            shutil.rmtree(Path(APPWORLD_HOME) / "experiments" / "outputs" /
                          exp / "tasks" / u, ignore_errors=True)
        print(f"  [{i + 1}/{len(units)}] {u} {len(rows)} ev "
              f"{time.time() - t0:.1f}s ok={stats['exec_ok']} "
              f"err={stats['exec_err']} cache={stats['cache_hit']} "
              f"drift={stats['unit_drift']}", flush=True)
    sink.close()
    csink.close()

    meta = dict(plan=str(plan_p), out=str(out_p), cache=str(cache_p), exp=exp,
                num_shards=a.num_shards, shard_id=a.shard_id,
                appworld_seed=APPWORLD_SEED,
                requote_version=REQUOTE_VERSION, trunc=TRUNC,
                n_units=len(units), n_events=len(recs),
                wall_s=round(time.time() - t00, 1),
                arg_modes=dict(Counter(
                    m for r in recs for m in (r.get("arg_modes") or []))),
                error_kind=dict(Counter(
                    r["error_kind"] for r in recs if r.get("error_kind"))),
                stats=dict(stats), unit_errors=unit_err)
    try:
        Path(str(out_p) + ".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1))
    except OSError as e:
        # 事件记录已经逐条 flush 过了,这里炸掉不丢结果;但要说清是磁盘问题,
        # 别让人以为是逻辑错。/home 是有配额的共享盘,实测踩过 Errno 122
        print(f"meta 写不下去({e})—— 事件记录已落盘 {out_p},"
              f"腾出空间后重跑会命中缓存,几秒钟就完", flush=True)
        raise
    print(json.dumps(meta, ensure_ascii=False, indent=1), flush=True)

    if not a.selfcheck:
        return 0

    # ---- 验收线:预测的调用与真实一致(hit)、代码块只含 1 个调用、而且那个
    #      代码块就是一句干净的 print(调用) —— 这三条同时成立时,"单独执行这条
    #      调用"的输出才应当与轨迹里录下的 result 对得上。三条里缺一条就说明
    #      两边根本不可比,算进验收线只会给自己报假警(实测两种假警:
    #      ① 代码块是 print("passwords:", apis...) ,录下的 stdout 多个前缀;
    #      ② 调用本身报错时 traceback 回显源码,引号风格不同就逐字不等)。
    n_match = n_match_err = n_diff = n_err = n_skip = 0
    for r in recs:
        if not (r.get("full_call_ok") and r.get("n_calls_in_block") == 1):
            continue
        if not r.get("traj_bare_print"):
            n_skip += 1
            tag = "SKIP_MIX"          # 录下的代码块不是一句干净的 print(调用)
        elif r.get("exec_out") is None:
            n_err += 1
            tag = "NO_EXEC"
        elif r["matched_traj_result"]:
            n_match += 1
            tag = "MATCH"
        elif r.get("matched_traj_error"):
            n_match_err += 1          # 报错消息一致,只差 traceback 里回显的引号
            tag = "MATCH_ERR"
        elif not r["exec_ok"]:
            n_err += 1
            tag = "EXEC_ERR"
        else:
            n_diff += 1
            tag = "DIFF"
        print(f"  {tag:9s} {r['unit']} s{r['step']} modes={r.get('arg_modes')} "
              f"| {str(r.get('exec_code'))[:86]} "
              f"| out={str(r.get('exec_out'))[:58]!r}", flush=True)
    bad_pv = [r["unit"] for r in recs if r.get("prefix_verbatim") is False]
    bad_dt = [r["unit"] for r in recs if r.get("dt_guard") is False]
    print(f"\nselfcheck: hit+单调用+干净print 的事件 MATCH {n_match} "
          f"MATCH_ERR {n_match_err} DIFF {n_diff} EXEC_ERR/NO_EXEC {n_err}"
          f"(另有 {n_skip} 个 hit+单调用事件因为代码块不是一句干净的 print "
          f"而不可比,不算进验收线);前缀漂了的 unit {sorted(set(bad_pv))};"
          f"时间守卫失效的 unit {sorted(set(bad_dt))};unit 级失败 {unit_err}")

    # 漂了就给漂移定责:干净重放(一个探测都不插)也漂 = 重放本身不保真;
    # 只有带探测才漂 = 探测调用写了库、回档没回干净(risk 2)
    for u in sorted(set(bad_pv)):
        rows = by_unit[u]
        try:
            clean = replay_unit(AppWorld, u, rows, rows[0]["traj_path"],
                                exp + "_clean", {}, open(os.devnull, "w"),
                                Counter(), [], probe=False)
        except Exception as e:
            print(f"  定责失败 {u}: {type(e).__name__}: {e}")
            continue
        rec = {st: r for st, _, r in load_steps(rows[0]["traj_path"])}
        bad = [st for st, got in clean if got != rec.get(st)]
        print(f"  {u} 干净重放也漂的步: {bad} "
              f"({'重放不保真' if bad else '疑似探测调用没回干净'})")
        if not a.keep_outputs:
            shutil.rmtree(Path(APPWORLD_HOME) / "experiments" / "outputs" /
                          (exp + "_clean"), ignore_errors=True)

    ok = (n_diff == 0 and n_err == 0 and not bad_pv and not bad_dt
          and not unit_err and n_match > 0)
    print("selfcheck " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
