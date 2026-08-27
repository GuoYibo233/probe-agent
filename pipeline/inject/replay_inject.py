"""文本层注入的离线回放实验(appworld / gpt-oss)。

要回答的问题:探针在思考段中途判定"接下来要调这个工具"的那一刻,把该工具的
结果直接拼进思考流,模型能不能少写一大段、还照样发出正确的调用。

四段式,分开跑,各自落盘(exec 与 merge-exec 只有 miss_policy=execute 才需要):
  plan   算触发点 + 生成预测调用 + 决定注入内容 -> plan.jsonl
         (要 GPU,但只用 0.6B 的参数产线;探针触发点直接读已落盘的 logits)
  exec   把 appworld 环境重放到该步、真执行预测出的调用 -> exec_calls.jsonl
         (纯 CPU,不占卡;**在 exec_calls.py 里,只能用
          envs/appworld/venv/bin/python 跑** —— cprobe-env 里 import appworld
          是 ModuleNotFoundError,实测)
  merge-exec  plan.jsonl + exec_calls.jsonl 左连接 -> plan_exec.jsonl
         (纯 CPU;之后的 run/score 都吃 plan_exec.jsonl)
  run    重建 prompt、发 vLLM completions 续写 -> raw.jsonl
         (要 gpt-oss-120b 服务,单卡 H200)
  score  解析、算 token 账与调用一致率 -> INJECT_REPORT.{json,md}
         (纯 CPU)

八个 arm(run 阶段用 --arms 选,可只跑一部分;默认仍是 nofill,inject):
  baseline     不跑。直接用原轨迹的数字(模型当时自己写完了整步),
               省 token 的**主对照**就是它
  nofill       从截断点续写但不注入。管线体检线:它应当≈baseline,对不上
               说明重建或采样口径有问题,这批数字就都不可信
  inject       从截断点续写并注入工具结果([SYSTEM NOTE] 模板)
  inject_stop  注入之后紧跟通道切换字节,掐掉"收到结果还要重新盘一遍"
  skel_bare    思考段里拼围栏 + 骨架(工具名由探针钉死,大模型只写参数)
  skel_a       骨架前加一句 "Thus code:" 再开围栏
  skel_b       散文式骨架("So we will do: "),不开围栏
  skel_switch  通道切换 + 围栏 + 骨架,骨架直接落在正文段
  switch_only  只切通道、不给骨架,大模型自写整条 —— 正确率锚点

"预测的调用与实际不符时怎么办"是 --miss-policy,三个值:
  skip       不注入,该事件只记账(零环境依赖,最快出第一条曲线)
  oracle     不管预测对错,一律注入真实调用的真实结果(上帝视角,量注入
             机制本身的上限;预测准确率的影响被剥离出去)
  execute    起 appworld 把环境重放到该步(逐步核对录下的 result)、把去引号的
             预测调用补回引号、在真环境里执行,**不管成功还是报错都原样注入**
             (真·无脑全注入)。猜错的代价这才进账 —— skip 档那 372 个猜错
             直接跳过、正确率轴偏乐观的问题就没了。
             `--exec-scope all`(默认)连 hit 事件也一起执行,口径统一;
             `--exec-scope miss` 只执行猜错的,hit 事件仍走 traj_hit。

**execute 档量到的是"单步调用一致率 + 猜错时注入真实报错",不是 appworld 的
任务级成绩(Test 分数)。** 本文件一个事件只续写一步,不跑到底、不调
`world.evaluate()`。任务级那条轴需要另建 in-loop rollout(run_appworld.py 的
循环里挂探针、触发就注入、走完整题再 evaluate),不在本文件范围内。
报告里把 execute 档写成"任务级正确率"就是虚报。

口径与已知偏差(报告里都要带上,别静默):
- 省 token 的主对照是**原轨迹**该步的 out token(盘上现成:模型当时从截断点
  一路写到发出调用实际花了多少),nofill 只当管线体检线 —— 从 cut 处重新
  tokenize 再续写无法逐字重现原始 token 流,两条线要一起看。
  这个口径盖在 INJECT_REPORT 的 `saved_baseline` 键上,读 per_event 求和的下游
  (sweep_theta curve)必须先认戳。旧报告(saved_tok 相对 nofill)重跑 score 会
  被挡下,要换口径得整条 θ 曲线一起重跑并显式加 `--rebaseline`。
- 注入的 result 是该步整个代码块的 stdout,而探针预测的是代码块里第一个
  api 调用(build.py:70-72 的 label 口径)。一个代码块含多个调用时,注入的
  内容比"那一个调用的返回"更多。第一版接受这个偏差,report 里单列该比例。
  execute 档**修掉**了这条(注入内容变成"那一条调用的返回"),代价是 hit 事件
  与已跑完的 skip/oracle 六点曲线不再逐字可比 —— 所以 score 段按
  inject_source 分桶,不许把 traj_hit 与 exec_pred 混成一条均值。
- execute 档的注入内容依赖 requote 这个**启发式**(gen_call 的参数值被 annotate
  剥了引号,rules.py:133),补错就是给探针记假账。逐参数的分支落在 arg_modes 里,
  分支计数进报告;验收线见 exec_calls.py --selfcheck。
- execute 档的前缀重放保真度**逐步核对**轨迹里录下的 result,漂了的事件标
  prefix_verbatim=False,报告里单列 —— 不核对就等于拿一个错的状态去执行预测
  调用、再把结果当真账报出来。
- 续写的采样键与采集来自同一份预设(--preset,缺省 default);
  但服务端批处理下的数值抖动仍可能让 nofill 与 baseline 不逐字相同。
- 少数步的历史里混有字面 harmony 标记,重新 tokenize 与采集时差几个 token
  (rebuild.py 顶部注释),plan 阶段标记为 literal_harmony。

用法:
  cprobe-env/bin/python pipeline/inject/replay_inject.py plan \\
      --ctool-run pipeline/runs/c1_gptoss_ctool \\
      --cgen-run  pipeline/runs/c1_gptoss_cgen \\
      --data      pipeline/data/aw_official_v1/gptoss \\
      --traj-root envs/runs/w0_aw_official/appworld_gptoss \\
      --out       pipeline/inject/runs/aw_gptoss_r10 \\
      --risk 0.1 --miss-policy skip

  θ 扫描曲线(2026-08-01 用户已批的六点格)用 --theta 直接钉阈值,盖过 --risk 反查:
      ... plan --theta 0.80 --out pipeline/inject/runs/aw_gptoss_th080 ...
  一个 θ 一个 run 目录,plan/run/score 各自独立落盘;驱动壳见 sweep_theta.py

  cprobe-env/bin/python pipeline/inject/replay_inject.py run \\
      --plan pipeline/inject/runs/aw_gptoss_r10/plan.jsonl \\
      --base-url http://tokyo108:8103/v1 --model gpt-oss-120b \\
      --arms nofill,inject

  骨架/转场臂要 plan 里存过 pred_label(探针预测的工具名),形态表由
  build_form_table.py 产,缺了就一律 print 形:
      ... run --arms skel_bare,skel_a,skel_b,skel_switch,switch_only \\
          --form-table pipeline/inject/form_table.json

  cprobe-env/bin/python pipeline/inject/replay_inject.py score \\
      --run-dir pipeline/inject/runs/aw_gptoss_r10

  # execute 档:plan 之后先跑 exec 段(纯 CPU,另一个解释器),再 merge,再 run
  envs/appworld/venv/bin/python pipeline/inject/exec_calls.py \\
      --plan  pipeline/inject/runs/aw_gptoss_exec/plan.jsonl \\
      --out   pipeline/inject/runs/aw_gptoss_exec/exec_calls.jsonl \\
      --cache pipeline/inject/exec_cache/aw_gptoss.jsonl \\
      --exp   aw_exec --num-shards 4 --shard-id 0
  cprobe-env/bin/python pipeline/inject/replay_inject.py merge-exec \\
      --plan pipeline/inject/runs/aw_gptoss_exec/plan.jsonl \\
      --exec pipeline/inject/runs/aw_gptoss_exec/exec_calls.jsonl
  cprobe-env/bin/python pipeline/inject/replay_inject.py run \\
      --plan pipeline/inject/runs/aw_gptoss_exec/plan_exec.jsonl --tag _exec ...
  cprobe-env/bin/python pipeline/inject/replay_inject.py score \\
      --run-dir pipeline/inject/runs/aw_gptoss_exec \\
      --plan-file plan_exec.jsonl --tag _exec
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                          # noqa: E402
from rules import AW_CALL, boundaries                        # noqa: E402
# exec_calls.py 的模块层只有标准库 + rules,cprobe-env 里 import 得动
# (appworld 是在它 main() 里 chdir 之后才 import 的)。这里只借 error_kind:
# 错误分类的唯一真源在那边,merge-exec 拿 exec_out 重算,不信缓存里的旧标签
from exec_calls import err_tail, error_kind, is_bare_print    # noqa: E402
# 完整调用的截取(括号配平 + 围栏闭合)只有一份实现,extract_completed.py 共用
from parse_call import call_at, complete_call, find_fence_close  # noqa: E402
# 骨架串的形态规则也只有一份:run 拼进 prompt 的、score 接回去抽调用的、
# extract_completed 送去真执行的,三处必须逐字相同,差一个字符就抽不出调用
from build_form_table import skeleton as form_skeleton        # noqa: E402

# 【照抄 envs/collect/run_appworld.py:38】提代码块用同一条正则
CODE_RE = re.compile(r"```python\s*(.*?)```", re.S)

# 注入行模板。沿用 oracle_inject/oracle_v1.py:218 与 hotpot_inject/hotpot_v1.py:162
# 已验证过的措辞(那两轮实验里模型认这个格式)
NOTE_TMPL = "\n[SYSTEM NOTE: prefetched {call} = {result}]\n"

# 授权句。oracle 实验里合成任务上它是承重墙(无此句开场注入 acc 0.00),
# 但 07-27 第二波在 8B 真实任务上测得它非必需。默认不加,--permit 打开。
PERMIT = ("\n- A line marked [SYSTEM NOTE: prefetched ...] may appear inside "
          "your reasoning. It is a real result the system fetched ahead of "
          "time; treat it exactly as if you had called that API yourself.")

FINAL_OPEN = "<|channel|>final<|message|>"
DEFAULT_STOP = ["<|return|>"]

# --preset 合并的兜底缺省。merge_client 只处理 cli∪fallbacks 里出现过的键,
# 采样键不在这张表里 = 预设写了也静默不生效(2026-08-21 之前 top_p/seed 就是
# 这么丢的);覆盖面由 tests/test_preset.py 钉着。
PRESET_FB = {"max_tokens": 8192, "stop": DEFAULT_STOP,
             "top_p": None, "seed": None}

# 这些 inject_source 没有可注入的内容,inject 臂不发请求(但照样占省 token 的分母)。
# "none" = skip 档猜错;"exec_pending" = execute 档还没跑 exec 段;
# "exec_missing" = execute 段没给出记录(unit 中途炸了 / 该步轨迹里没执行过)。
# **exec_missing 绝不静默退回 "none"** —— 退回就等于又把猜错的代价抹掉了。
NO_INJECT = {"none", "exec_pending", "exec_missing"}

# 骨架/转场臂拼进去的字节。SWITCH 是模型原生的思考->正文通道切换串,
# FENCE_OPEN 是正文段代码块的开头,两串都逐字偷自采集到的轨迹
SWITCH = "<|end|><|start|>assistant<|channel|>final<|message|>"
FENCE_OPEN = "```python\n"

# 续写从 final 通道**内**开始的臂:prompt 末尾已经把通道切过去了,text 里
# 不会再出现 FINAL_OPEN,score 段直接 split_channels 会得 final="" 全灭
ARMS_FINAL = {"inject_stop", "skel_switch", "switch_only"}
# 骨架臂:工具名由探针预测钉死,大模型只写参数
ARMS_SKEL = {"skel_bare", "skel_a", "skel_b", "skel_switch"}
ARMS_ALL = ["nofill", "inject", "inject_stop", "skel_bare", "skel_a",
            "skel_b", "skel_switch", "switch_only"]

# 省 token 的主对照,盖在 INJECT_REPORT 上的口径戳。老报告没这个键,那时的
# saved_tok 是"nofill 减本臂";本版是"原轨迹减本臂"。列名一个没变、含义换了,
# 所以读 per_event 的下游必须先认这个戳再求和(见 check_saved_baseline)
SAVED_BASELINE = "traj"


def config_path_for(plan_path):
    """plan 文件名 -> 同目录里对应的 config 名。

    plan.jsonl -> plan_config.json;plan_exec.jsonl -> plan_exec_config.json。
    execute 档换了 plan 文件却还读 plan_config.json,permit 口径与统计就都错了。
    """
    p = Path(plan_path)
    return p.parent / (p.stem + "_config.json")


# ---------------------------------------------------------------- plan

def replay_fire(rows, probs, theta):
    """【照抄 pipeline/eval/eval_causal_call.py:54-71】每事件首次过 θ 的样本行。"""
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out = {}
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None, pred=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta:
                # pred 必须存下来:骨架臂拼的是探针预测的工具名,只记对错
                # 不记名字的话下游就只能拿真值去拼,整条曲线变上帝视角
                rec.update(fired=True, ok=(pred == r["y"]), conf=conf,
                           pred=pred, sent_idx=r["sent_idx"], row=r)
                break
        out[k] = rec
    return out


def external_fire(rows, probs, path):
    """外部判定文件替代 θ 判定,返回与 replay_fire 同形的表。

    JSONL 每行一个事件:{"event":..., "fire": bool, "sent_idx": int|null},
    sent_idx 给 null 就取该事件首句。给了这个文件,θ 完全不参与判定;
    conf 照旧算(ctool softmax 在该句上的 max),只为对账留个数。
    用户在训的产阈值模型训好后直接产这个文件接进来,管线不改。
    """
    dec = {}
    for l in open(path):
        l = l.strip()
        if l:
            o = json.loads(l)
            dec[o["event"]] = o
    ev = defaultdict(list)
    for r, p in zip(rows, probs):
        ev[r["event"]].append((r["sent_idx"], r, p))
    out, n_oob, n_unknown = {}, 0, 0
    for k, items in ev.items():
        items.sort(key=lambda x: x[0])
        rec = dict(fired=False, ok=False, sent_idx=None, row=None, pred=None,
                   label=items[0][1]["label"])
        d = dec.get(k)
        if d is None:
            n_unknown += 1
        elif d.get("fire"):
            want = d.get("sent_idx")
            pick = (items[0] if want is None
                    else next((it for it in items if it[0] == want), None))
            if pick is None:
                # 判定文件点了一个数据集里没有的句子:算不触发并计数,
                # 静默丢掉就等于偷偷改了触发集大小
                n_oob += 1
            else:
                _, r, p = pick
                conf, pred = float(p.max()), int(p.argmax())
                rec.update(fired=True, ok=(pred == r["y"]), conf=conf,
                           pred=pred, sent_idx=r["sent_idx"], row=r)
        out[k] = rec
    print(f"外部判定 {path}:{len(dec)} 条,事件没被判定 {n_unknown},"
          f"点到不存在的句子 {n_oob}", flush=True)
    return out


def gen_calls(cgen_dir, texts, device, bs, max_new):
    """跑参数产线,在触发点前缀上 greedy 写出整条调用。

    【照抄 eval_causal_call.py:171-192 的 generate()】——同样的 left padding、
    同样截到首行、同样从 meta.json 读 call_sep,保证与 CALLGEN_REPORT 可对账。

    返回 (calls, min_ps)。min_ps 是每条调用里**最弱那个 token 的概率**,给
    cgen 自触发用(整条最弱概率过阈值才算敢发)。生成时不留概率,事后只能
    整批重跑才拿得到,所以在这里顺手取。
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    meta = json.loads((cgen_dir / "best" / "meta.json").read_text())
    sep, max_len = meta.get("call_sep", "\n[CALL] "), meta.get("max_len", 4096)
    tok = AutoTokenizer.from_pretrained(cgen_dir / "best")
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.truncation_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        cgen_dir / "best",
        dtype=torch.bfloat16 if str(device).startswith("cuda")
        else torch.float32).to(device).eval()
    prompts = [t + sep for t in texts]
    out, min_ps, prev = [], [], tok.padding_side
    tok.padding_side = "left"
    # 这两个 id 上就停:eos 是真写完了,pad 是 generate 给已结束的序列补的位
    stop_ids = {i for i in (tok.eos_token_id, tok.pad_token_id)
                if isinstance(i, int)}
    nl = {}                              # token id -> 解出来带不带换行

    def has_nl(tid):
        if tid not in nl:
            nl[tid] = "\n" in tok.decode([tid])
        return nl[tid]

    with torch.no_grad():
        for i in range(0, len(prompts), bs):
            enc = tok(prompts[i:i + bs], truncation=True,
                      max_length=max(max_len - max_new, 1), padding=True,
                      add_special_tokens=False, return_tensors="pt").to(device)
            g = model.generate(**enc, do_sample=False, max_new_tokens=max_new,
                               eos_token_id=tok.eos_token_id,
                               pad_token_id=tok.pad_token_id,
                               return_dict_in_generate=True,
                               output_scores=True)
            new = g.sequences[:, enc["input_ids"].shape[1]:]
            # left padding 下每行的生成段都从同一列开始,所以 scores[t] 对上的
            # 就是 new[:, t] —— 换成右 padding 每行起点不同,这里必错位
            cols = [torch.softmax(s.float(), -1).gather(
                        1, new[:, t:t + 1]).squeeze(1)
                    for t, s in enumerate(g.scores)]
            ps = torch.stack(cols, 1).cpu() if cols else None
            txt = tok.batch_decode(new, skip_special_tokens=True)
            out += [t.split("\n")[0].strip() for t in txt]
            for b in range(new.shape[0]):
                mp = None
                for t in range(0 if ps is None else ps.shape[1]):
                    tid = int(new[b, t])
                    if tid in stop_ids:      # eos 及其后的补位都不算
                        break
                    p = float(ps[b, t])
                    mp = p if mp is None else min(mp, p)
                    # 首行到此为止,与上面 split("\n")[0] 对齐。带换行的那个
                    # token 算进去:它常常是 `)\n` 这种,漏掉就漏了尾括号一步
                    if has_nl(tid):
                        break
                min_ps.append(mp)            # 一个 token 都没生成就记 None
            print(f"  gen {min(i + bs, len(prompts))}/{len(prompts)}",
                  flush=True)
    tok.padding_side = prev
    del model
    torch.cuda.empty_cache()
    return out, min_ps


def first_api_call(code):
    """代码块里第一个 apis.x.y 调用的工具名。找不到返回 None。"""
    m = AW_CALL.search(code or "")
    return f"apis.{m.group(1)}.{m.group(2)}" if m else None


def cmd_plan(a):
    import torch
    ctool, cgen = Path(a.ctool_run), Path(a.cgen_run)
    data, root = Path(a.data), Path(a.traj_root)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    R.check_system_verbatim()

    rep = json.loads((ctool / "REPLAY_REPORT.json").read_text())
    T = rep["temperature"]
    # θ 三种来源:外部判定文件(给了就完全接管,θ 不参与)、风险档反查(原口径,
    # 与 eval 的 chosen_theta 一致)、--theta 直接给(θ 扫描曲线用)。温度标定 T
    # 与风险档无关,几种来源都用同一个 T,所以曲线上各点只差判定阈值,可直接横向比。
    if a.decision_file:
        theta, theta_source = None, f"external:{a.decision_file}"
    elif a.theta is not None:
        theta, theta_source = a.theta, "explicit"
    else:
        theta = rep["chosen_theta"].get(str(a.risk))
        if theta is None:
            raise SystemExit(f"θ 里没有 risk={a.risk}:{rep['chosen_theta']}")
        theta_source = f"risk={a.risk}"

    # 行过滤必须与 eval 侧逐行一致,否则与 logits_test.pt 不同序
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    id2label = {v: k for k, v in label2id.items()}   # 反查:预测 id -> 工具名
    rows = [r for r in (json.loads(l) for l in open(data / "test.jsonl"))
            if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)
    probs = torch.softmax(logits / T, -1)
    fired = (external_fire(rows, probs, a.decision_file) if a.decision_file
             else replay_fire(rows, probs, theta))

    keys = [k for k in dict.fromkeys(r["event"] for r in rows)
            if fired[k]["fired"]]
    n_events = len({r["event"] for r in rows})
    print(f"事件 {n_events} 触发 {len(keys)} (θ={theta} 来源 {theta_source} "
          f"T={T:.4f} risk={a.risk})", flush=True)
    if a.limit:
        keys = keys[:a.limit]

    print(f"参数产线生成 {len(keys)} 条调用 ...", flush=True)
    calls, min_ps = gen_calls(cgen, [fired[k]["row"]["text"] for k in keys],
                              a.device, a.bs, a.max_new_tokens)

    traj_cache, plan, drop = {}, [], defaultdict(int)
    for k, gen_call, gen_min_p in zip(keys, calls, min_ps):
        row = fired[k]["row"]
        tp = root / f"appworld_{row['unit']}.jsonl"
        if tp not in traj_cache:
            if not tp.exists():
                drop["traj_missing"] += 1
                continue
            traj_cache[tp] = R.load_traj(tp)
        meta, gens, envs, _ = traj_cache[tp]
        st = row["step"]
        if st not in gens or st not in envs:
            drop["step_missing"] += 1
            continue
        think = (gens[st].get("reasoning") or "").strip()
        b = boundaries(think)
        if row["sent_idx"] >= len(b):
            drop["sent_idx_oob"] += 1
            continue
        cut = b[row["sent_idx"]]
        # 自检:重算出来的前缀必须与数据集里探针吃的那一段逐字相同
        ds_think = row["text"].split("[THINKING]\n", 1)[-1]
        if think[:cut] != ds_think:
            drop["prefix_mismatch"] += 1
            continue
        try:
            msgs = R.build_messages(meta, gens, envs, st)
        except ValueError:
            drop["history_broken"] += 1
            continue

        truth_call = row.get("label_call")
        hit = (gen_call == truth_call)
        result = envs[st].get("result") or ""
        if a.miss_policy == "oracle":
            inj_call, inj_res, src = truth_call, result, "traj_oracle"
        elif a.miss_policy == "execute" and (not hit or a.exec_scope == "all"):
            # 注入内容还不知道 —— 要等 exec 段真去环境里执行一遍。
            # plan 段跑在 GPU 上(cgen 产线),这里绝不能 import appworld
            inj_call, inj_res, src = gen_call, None, "exec_pending"
        elif hit:
            inj_call, inj_res, src = gen_call, result, "traj_hit"
        elif a.miss_policy == "skip":
            inj_call, inj_res, src = None, None, "none"
        else:                                    # 到不了:上面三条已穷举
            raise AssertionError(f"miss_policy={a.miss_policy} 没有分支")

        action = envs[st].get("action") or ""
        rec = dict(
            event=k, unit=row["unit"], traj=row["traj"], step=st,
            sent_idx=row["sent_idx"], depth=row["depth"], cut=cut,
            think_len=len(think), conf=fired[k].get("conf"),
            label=row["label"], label_call=truth_call, gen_call=gen_call,
            # 探针预测的工具名。骨架臂拼的是它,**不是 label**(真值只留着算
            # name_hit),拿 label 去拼整条曲线就成了上帝视角
            pred_id=fired[k].get("pred"),
            pred_label=id2label.get(fired[k].get("pred")),
            gen_min_p=gen_min_p,
            tool_ok=fired[k]["ok"], full_call_ok=hit,
            inject_call=inj_call, inject_result=inj_res, inject_source=src,
            baseline_out_tok=(gens[st].get("usage") or {}).get("out"),
            baseline_action=action,
            baseline_tool=first_api_call(action),
            n_calls_in_block=len(AW_CALL.findall(action)),
            literal_harmony=R.has_literal_harmony(msgs),
            traj_path=str(tp))
        if a.miss_policy == "execute":
            # 只在 execute 档加这几个字段:skip/oracle 的 plan.jsonl 必须保持
            # 逐字节不变(它们已有实战产出,变了就毁掉六点曲线的可比性)
            rec.update(traj_result=result,      # 录下的整块 stdout,给验收线用
                       exec_code=None, arg_modes=None, exec_ok=None)
        plan.append(rec)

    with open(out_dir / "plan.jsonl", "w") as f:
        for p in plan:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    cfg = dict(ctool_run=str(ctool), cgen_run=str(cgen), data=str(data),
               traj_root=str(root), risk=a.risk, theta=theta,
               theta_source=theta_source, temperature=T,
               decision_file=a.decision_file,
               miss_policy=a.miss_policy, permit=a.permit,
               n_events_test=n_events, n_fired=len(keys), n_planned=len(plan),
               drop=dict(drop),
               n_gen_min_p=sum(1 for p in plan
                               if p.get("gen_min_p") is not None),
               n_inject=sum(1 for p in plan
                            if p["inject_source"] not in NO_INJECT),
               n_hit=sum(1 for p in plan if p["full_call_ok"]),
               n_multicall=sum(1 for p in plan if p["n_calls_in_block"] > 1),
               n_literal=sum(1 for p in plan if p["literal_harmony"]))
    if a.miss_policy == "execute":
        # 同上:只在 execute 档加,skip/oracle 的 plan_config.json 逐字节不变
        cfg.update(exec_scope=a.exec_scope,
                   n_exec_pending=sum(1 for p in plan
                                      if p["inject_source"] == "exec_pending"))
    (out_dir / "plan_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1))
    print(json.dumps(cfg, ensure_ascii=False, indent=1))


# ----------------------------------------------------------- merge-exec

def expand_exec(spec):
    """把 --exec 的规格展开成实际文件表。

    exec_calls.py 分片时会自动把 `exec_calls.jsonl` 写成 `exec_calls.s0.jsonl`,
    所以这里先按原名找,找不到就按 `<stem>*<suffix>` 收分片 —— 少收一片就等于
    白白多出一批 exec_missing。
    """
    import glob
    out = []
    for tok in (x.strip() for x in spec.split(",")):
        if not tok:
            continue
        hits = sorted(glob.glob(tok))
        if not hits:
            p = Path(tok)
            hits = sorted(glob.glob(str(p.parent / (p.stem + "*" + p.suffix))))
        if not hits:
            raise SystemExit(f"找不到 exec 产物:{tok}")
        out += hits
    return out


def cmd_merge_exec(a):
    """plan.jsonl + exec_calls.jsonl 左连接 -> plan_exec.jsonl。

    exec 记录缺失的事件标 exec_missing 并单独计数,**绝不静默退回 "none"**
    —— 退回就等于又把探针猜错的代价抹掉了,而这正是 execute 档要修的病。
    """
    plan_p = Path(a.plan)
    out_dir = plan_p.parent
    cfg = json.loads(config_path_for(plan_p).read_text())
    if cfg.get("miss_policy") != "execute":
        raise SystemExit(f"{plan_p} 的 miss_policy={cfg.get('miss_policy')},"
                         "不是 execute 档,没有 exec 段可合")
    plan = [json.loads(l) for l in open(plan_p)]

    files = expand_exec(a.exec)
    ex = {}
    for fp in files:
        for l in open(fp):
            try:
                o = json.loads(l)
            except Exception:                # 半行(进程被杀)直接丢
                continue
            ex[o["event"]] = o               # 后写的覆盖先写的
    print(f"exec 产物 {len(files)} 个文件 {len(ex)} 条:"
          + ", ".join(Path(f).name for f in files), flush=True)

    n = defaultdict(int)
    modes, ekind, miss_why = Counter(), Counter(), Counter()
    rows = []
    for p in plan:
        r = dict(p)
        if p["inject_source"] != "exec_pending":
            # exec-scope=miss 下的 hit 事件(traj_hit)、oracle、skip 的 none:
            # 一个字节都不动,原样过
            n[p["inject_source"]] += 1
            rows.append(r)
            continue
        e = ex.get(p["event"])
        # 错误分类拿 exec_out 现算,不信 exec 记录里那个字段:缓存可能是旧规则
        # 写的,直接抄就把旧标签静默带进报告
        ek = error_kind(e.get("exec_out")) if e else None
        if e is None or e.get("exec_out") is None:
            r["inject_result"], r["inject_source"] = None, "exec_missing"
            why = ("no_record" if e is None
                   else (e.get("error_kind") or "no_output"))
            r["exec_missing_reason"] = why
            miss_why[why] += 1
            n["exec_missing"] += 1
        else:
            r["inject_result"] = e["exec_out"]
            r["inject_source"] = "exec_pred" if ek is None else "exec_error"
            n[r["inject_source"]] += 1
        if e is not None:
            # 三条比对也现算(用 plan 自己的 traj_result / baseline_action),
            # 同样不抄 exec 记录里那份 —— 缓存可能是上一版比法写的
            eo, tr = e.get("exec_out"), p.get("traj_result")
            r.update(exec_code=e.get("exec_code"),
                     arg_modes=e.get("arg_modes"), exec_ok=(ek is None),
                     error_kind=ek,
                     prefix_verbatim=e.get("prefix_verbatim"),
                     drift_step=e.get("drift_step"),
                     matched_traj_result=(eo == tr),
                     matched_traj_error=(
                         None if err_tail(eo) is None or err_tail(tr) is None
                         else err_tail(eo) == err_tail(tr)),
                     traj_bare_print=is_bare_print(p.get("baseline_action")),
                     exec_cache_hit=e.get("cache_hit"))
            modes.update(e.get("arg_modes") or [])
            if ek:
                ekind[ek] += 1
        rows.append(r)

    with open(out_dir / "plan_exec.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    inj = [r for r in rows if r["inject_source"] not in NO_INJECT]
    fired_exec = [r for r in rows if r["inject_source"] in
                  ("exec_pred", "exec_error")]
    verb = [r for r in fired_exec if r.get("matched_traj_result") is not None]
    # 验收线只收"三条同时成立"的事件:预测与真实一致、代码块只含一个调用、
    # 且那个代码块就是一句干净的 print(调用)。缺一条两边就不可比,收进来只会
    # 报假警(详见 exec_calls.py 的 BARE_PRINT / err_tail 注释)
    acc = [r for r in fired_exec
           if r.get("full_call_ok") and r.get("n_calls_in_block") == 1
           and r.get("traj_bare_print")]
    acc_ok = [r for r in acc if r.get("matched_traj_result")
              or r.get("matched_traj_error")]
    mixed = [r for r in fired_exec
             if r.get("full_call_ok") and r.get("n_calls_in_block") == 1
             and not r.get("traj_bare_print")]
    out = dict(cfg)
    out.update(
        exec_files=[str(f) for f in files], plan_file="plan_exec.jsonl",
        n_inject=len(inj), by_inject_source=dict(n),
        n_exec_pred=n["exec_pred"], n_exec_error=n["exec_error"],
        n_exec_missing=n["exec_missing"], exec_missing_reason=dict(miss_why),
        exec_error_rate=(round(n["exec_error"] / len(fired_exec), 4)
                         if fired_exec else None),
        arg_modes=dict(modes), error_kind=dict(ekind),
        n_drift=sum(1 for r in fired_exec
                    if r.get("prefix_verbatim") is False),
        # 验收线:hit + 单调用 + 代码块是一句干净的 print(调用),
        # 执行输出与录下的 result 对得上(逐字,或报错时报错消息一致)
        acceptance_matched=len(acc_ok), acceptance_n=len(acc),
        acceptance_exact=sum(1 for r in acc if r.get("matched_traj_result")),
        acceptance_excluded_mixed=len(mixed),
        matched_traj_result_all=(
            round(sum(1 for r in verb if r["matched_traj_result"]) / len(verb),
                  4) if verb else None))
    (out_dir / "plan_exec_config.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if n["exec_missing"]:
        print(f"\n注意:{n['exec_missing']} 个事件没有 exec 记录,标为 "
              f"exec_missing、inject 臂不发请求,但照样占省 token 的分母。"
              f"原因分布 {dict(miss_why)}")


# ---------------------------------------------------------------- run

def load_form_table(path):
    """工具名 -> 骨架形态(build_form_table.py 从原生轨迹统计出来的)。

    文件不在就返回空表、骨架一律走 print 形,并且只告警一次 —— 少一张统计表
    不该让骨架实验跑不起来,但也不能静默地当成"所有工具都是 print 形"。
    """
    p = Path(path)
    if not p.exists():
        print(f"注意:form_table 不存在({p}),骨架一律用 print 形;"
              "要按工具分流赋值形先跑 build_form_table.py", flush=True)
        return {}
    return json.loads(p.read_text())


def skeleton(p, form_table):
    """一条 plan 记录的骨架串。没有预测工具名就返回 None。

    拼的是**探针预测的 pred_label,绝不能用真值 label** —— 拿真值去拼,整条
    曲线就成了上帝视角。
    形态分流(赋值形 `var = apis.x.y` 还是 `print(apis.x.y`)与"一律不带尾左
    括号"那条分词器铁律都在 build_form_table.skeleton 里,这里只取值、兜空。
    """
    name = p.get("pred_label")
    if not name:
        return None
    return form_skeleton(name, form_table)


def build_splice(arm, p, form_table):
    """按 arm 拼"接在思考段 head 后面的那一截"。

    返回 None 表示这条事件这个臂拼不出来(骨架臂没有 pred_label),
    正常路径下已经被 todo 过滤挡掉了。
    """
    if arm == "nofill":
        return ""
    if arm in ("inject", "inject_stop"):
        note = NOTE_TMPL.format(call=p["inject_call"],
                                result=p["inject_result"])
        # inject_stop 多一串通道切换:把"收到结果还要重新盘一遍"直接掐掉
        return note + SWITCH if arm == "inject_stop" else note
    if arm == "switch_only":
        return SWITCH
    sk = skeleton(p, form_table)
    if sk is None:
        return None
    if arm == "skel_bare":
        return "\n" + FENCE_OPEN + sk
    if arm == "skel_a":
        return "\nThus code:\n" + FENCE_OPEN + sk
    if arm == "skel_b":
        return "\nSo we will do: " + sk
    if arm == "skel_switch":
        return SWITCH + FENCE_OPEN + sk
    raise SystemExit(f"未知 arm:{arm}(可选 {','.join(ARMS_ALL)})")


def spliced_tail(arm, p, form_table):
    """续写之前就喂进去、但不落在 raw 的 text 里的那一截(围栏 + 骨架)。

    score 段抽调用必须把它接回 text 前面:`apis.` 的起点在 prompt 里,text
    只剩参数,不接回去解析器根本找不到调用起点。骨架臂里 bare/a/b 的骨架
    落在 analysis 段,switch 的落在 final 段。
    """
    if arm not in ARMS_SKEL:
        return ""
    sk = skeleton(p, form_table)
    if sk is None:
        return ""
    return sk if arm == "skel_b" else FENCE_OPEN + sk


def sample_extras(a):
    """top_p/seed 只在显式给了的时候进请求体(envs/collect/common.py 的
    Chat._sample_extras 同款口径):不给时请求体与加这两个键之前逐字节一致。"""
    d = {}
    if getattr(a, "top_p", None) is not None:
        d["top_p"] = a.top_p
    if getattr(a, "seed", None) is not None:
        d["seed"] = a.seed
    return d


def gen_payload(a, prompt):
    """塞法回放主生成请求的请求体。预设 client 节的采样键(temperature/
    top_p/max_tokens/stop/seed)全在这一处落地,tests/test_preset.py 钉着。"""
    return dict(model=a.model, prompt=prompt, max_tokens=a.max_tokens,
                temperature=a.temperature, stop=a.stop,
                skip_special_tokens=False, **sample_extras(a))


def post_completions(base_url, payload, timeout, retries=4):
    url = base_url.rstrip("/") + "/completions"
    body = json.dumps(payload).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if att == retries - 1:
                raise
            print(f"    retry {att + 1}: {e}", flush=True)
            time.sleep(2 ** att)


def cmd_run(a):
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from transformers import AutoTokenizer

    # --preset 合并(CLI 显式值 > 预设 client 节 > 原缺省),展开值挂回 a;
    # --preset 缺省 default,temperature 这个键只从预设文件来
    root = str(HERE.parents[1])
    if root not in sys.path:
        sys.path.append(root)
    from preset_loader import load_preset, merge_client, require_temperature
    pre = load_preset(a.preset)
    eff = merge_client(
        {"max_tokens": a.max_tokens,
         "temperature": getattr(a, "temperature", None)},
        pre.get("client"),
        PRESET_FB)
    a.max_tokens = eff["max_tokens"]
    a.temperature = require_temperature(eff["temperature"], pre["_name"])
    a.stop = eff["stop"]
    a.top_p = eff["top_p"]
    a.seed = eff["seed"]

    plan_path = Path(a.plan)
    out_dir = plan_path.parent
    # config 跟着 plan 文件名走:plan_exec.jsonl 配 plan_exec_config.json。
    # 硬读 plan_config.json 会在 execute 档拿错 permit 口径与统计
    cfg = json.loads(config_path_for(plan_path).read_text())
    plan = [json.loads(l) for l in open(plan_path)]
    if a.limit:
        plan = plan[:a.limit]
    pend = sum(1 for p in plan if p["inject_source"] == "exec_pending")
    if pend:
        raise SystemExit(
            f"{plan_path} 里有 {pend} 个事件还是 exec_pending(注入内容为空)。"
            "execute 档的依赖顺序是 plan -> exec_calls.py -> merge-exec -> run,"
            "先把 exec 段跑完再来")
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in arms if x not in ARMS_ALL]
    if bad:
        raise SystemExit(f"未知 arm:{','.join(bad)};可选 {','.join(ARMS_ALL)}")
    form_table = load_form_table(a.form_table)
    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    add_permit = bool(a.permit or cfg.get("permit"))

    rp = out_dir / f"raw{a.tag}.jsonl"
    done = set()
    if rp.exists():                              # 断点续跑
        for l in open(rp):
            try:
                o = json.loads(l)
                done.add((o["event"], o["arm"]))
            except Exception:
                pass

    def wanted(p, arm):
        """这个臂在这条事件上有没有料可拼。缺料的不发请求,但照样占分母。"""
        if arm in ("inject", "inject_stop"):
            return p["inject_source"] not in NO_INJECT   # 没内容可注入
        if arm in ARMS_SKEL:
            return bool(p.get("pred_label"))             # 骨架钉不出工具名
        return True

    todo = [(p, arm) for p in plan for arm in arms
            if (p["event"], arm) not in done and wanted(p, arm)]
    if (any(x in ARMS_SKEL for x in arms)
            and not any(p.get("pred_label") for p in plan)):
        print("注意:这份 plan 里一条 pred_label 都没有(旧版 plan 段不存探针"
              "预测的工具名),骨架臂会被整批过滤 —— 先重跑 plan", flush=True)
    print(f"计划 {len(plan)} 条 x {arms};已有 {len(done)} 条,待跑 "
          f"{len(todo)} 条,并发 {a.concurrency}", flush=True)

    sink = open(rp, "a")
    lock, cache, clock = threading.Lock(), {}, threading.Lock()
    stat = dict(n=0, t0=time.time(), fail=0)

    def traj_of(path):
        with clock:
            if path not in cache:
                cache[path] = R.load_traj(Path(path))
            return cache[path]

    def one(p, arm):
        meta, gens, envs, _ = traj_of(p["traj_path"])
        msgs = R.build_messages(meta, gens, envs, p["step"])
        if add_permit:
            msgs = [dict(m) for m in msgs]
            msgs[0]["content"] = msgs[0]["content"] + PERMIT
        prefix = R.build_prefix(tok, msgs,
                                pin_date=None if a.no_pin_date
                                else R.COLLECT_DATE)
        if not a.assume_date:
            R.assert_date(prefix)
        think = (gens[p["step"]].get("reasoning") or "").strip()
        head = think[:p["cut"]]
        head_tok = len(tok.encode(head, add_special_tokens=False))
        splice = build_splice(arm, p, form_table)
        prompt = prefix + R.ANALYSIS_OPEN + head + splice
        if a.dry_run:
            return dict(event=p["event"], arm=arm, dry=True,
                        prompt_chars=len(prompt), head_tok=head_tok,
                        note_chars=len(splice),
                        prompt_tok=len(tok.encode(
                            prompt, add_special_tokens=False)),
                        baseline_out_tok=p["baseline_out_tok"],
                        tail=prompt[-160:])
        t0 = time.time()
        r = post_completions(a.base_url, gen_payload(a, prompt), a.timeout)
        ch = r["choices"][0]
        return dict(event=p["event"], arm=arm, text=ch["text"],
                    finish_reason=ch.get("finish_reason"),
                    prompt_tok=r["usage"]["prompt_tokens"],
                    gen_tok=r["usage"]["completion_tokens"],
                    head_tok=head_tok, note_chars=len(splice),
                    wall_s=round(time.time() - t0, 2))

    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = {ex.submit(one, p, arm): (p["event"], arm) for p, arm in todo}
        for fu in as_completed(futs):
            ev, arm = futs[fu]
            try:
                rec = fu.result()
            except Exception as e:
                stat["fail"] += 1
                print(f"  FAIL {ev} {arm}: {type(e).__name__}: {e}",
                      flush=True)
                continue
            with lock:
                sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
                sink.flush()
                stat["n"] += 1
                if stat["n"] % 50 == 0:
                    el = time.time() - stat["t0"]
                    rate = stat["n"] / el
                    left = (len(todo) - stat["n"]) / rate if rate else 0
                    print(f"  {stat['n']}/{len(todo)} "
                          f"{rate:.2f} req/s ETA {left/60:.1f} min",
                          flush=True)
    sink.close()
    print(f"完成 {stat['n']}/{len(todo)};失败 {stat['fail']} -> {rp}")


# ---------------------------------------------------------------- score

def split_channels(text):
    """把续写切成 (analysis 剩余, final 内容)。"""
    if FINAL_OPEN in text:
        head, tail = text.split(FINAL_OPEN, 1)
        return head, tail
    return text, ""


def check_saved_baseline(d, tag, rebaseline):
    """覆盖旧报告之前先比一次省 token 的口径,两种口径不许在同一批目录里换班。

    saved_tok 从"相对 nofill"换成"相对原轨迹"之后,per_event 的列名一个没改,
    数值换了含义。下游 sweep_theta 的 curve 子命令把各 θ 目录的 per_event 直接
    求和成一条曲线,只重跑其中一个 θ 的 score,曲线就变成一半旧口径一半新口径
    ——表面上看不出来,列名与历史行完全一样。所以这里挡一道:目录里躺着的报告
    口径与本版不同就停,真要换得把同一条曲线上的全部 θ 点一起重跑。
    """
    rep = d / f"INJECT_REPORT{tag}.json"
    if not rep.exists():
        return
    try:
        old = json.loads(rep.read_text()).get("saved_baseline")
    except (ValueError, OSError):
        return                      # 旧报告本身坏了,照常覆盖
    if old == SAVED_BASELINE:
        return
    if rebaseline:
        print(f"[口径切换] {rep.name}:saved_baseline {old!r} -> "
              f"{SAVED_BASELINE!r}。同一条 θ 曲线上的其余点也要重跑 score,"
              "否则 sweep_theta curve 会把两种口径的 saved_tok 求和到一起")
        return
    raise SystemExit(
        f"{rep} 是 saved_baseline={old!r} 的旧报告(saved_tok = nofill 的 out "
        f"token 减本臂),本版写的是 {SAVED_BASELINE!r}(saved_tok = 原轨迹该步的 "
        "out token 减本臂)。两者列名相同、含义不同:只重跑这一个目录,拿它装出来的 "
        "θ 曲线就是两种口径求和,报表上分辨不出来。确认要换口径、并且会把同一条"
        "曲线的全部 θ 点都重跑一遍,再加 --rebaseline。")


def cmd_score(a):
    d = Path(a.run_dir)
    # 先挡口径,再干几分钟的解析活:换口径这件事要在覆盖发生之前就拦下来
    check_saved_baseline(d, a.tag, a.rebaseline)
    plan_p = d / a.plan_file
    cfg = json.loads(config_path_for(plan_p).read_text())
    is_exec = cfg.get("miss_policy") == "execute"
    # 骨架臂的骨架串本身不在 raw 里,要按同一张形态表重新拼一遍才能抽调用;
    # run 与 score 之间换了 form_table,这里重建出来的骨架就对不上了
    form_table = load_form_table(a.form_table)
    plan = {json.loads(l)["event"]: json.loads(l) for l in open(plan_p)}
    raw = defaultdict(dict)
    for l in open(d / f"raw{a.tag}.jsonl"):
        o = json.loads(l)
        raw[o["event"]][o["arm"]] = o          # 后写的覆盖先写的

    per, by_arm = [], defaultdict(list)
    for ev, arms in raw.items():
        p = plan.get(ev)
        if p is None:
            continue
        nof = arms.get("nofill")
        nof_out = (nof["head_tok"] + nof["gen_tok"]) if nof else None
        for arm, o in arms.items():
            tail = spliced_tail(arm, p, form_table)
            if arm in ARMS_SKEL and o.get("note_chars") is not None:
                # run 与 score 之间换了形态表(重跑 build_form_table、assign_share
                # 跨过 0.5、或忘了传同一张表),这里重建的骨架就不是当初喂进去的
                # 那串,skeleton_done / call_out / post_think 会整体静默偏移。
                # raw 里存着当初拼进去那截的字符数,拿它对一下当场就能发现
                sp = build_splice(arm, p, form_table)
                if sp is None or len(sp) != o["note_chars"]:
                    raise SystemExit(
                        f"form_table 对不上:{ev} {arm} run 时拼进去 "
                        f"{o['note_chars']} 字符,照 {a.form_table} 重建出 "
                        f"{len(sp) if sp is not None else 0} 字符 —— "
                        "score 必须用 run 时的同一张表")
            if arm in ARMS_FINAL:
                # 这些臂的续写从 final 通道**内**开始:text 里根本不会再出现
                # FINAL_OPEN,拿 split_channels 去切会得 final="" 一片全灭。
                # analysis 剩余记空,final = 拼进去的那一截 + 续写
                rest, final = "", tail + o["text"]
            else:
                rest, final = split_channels(o["text"])
                rest = tail + rest      # 骨架在 analysis 里,接回去才找得到起点
            m = CODE_RE.search(final)
            code = m.group(1) if m else ""
            tool = first_api_call(code)
            sk_call, skel_done, tool_rw, post_think = None, None, None, None
            if arm in ARMS_FINAL:
                post_think = 0          # 已经在正文段里,没有"补完后又想"这一段
            if arm in ARMS_SKEL:
                # 骨架所在的那一段:bare/a/b 在 analysis,switch 在 final。
                # 补完与否、补完后还想多久,都从这一段量。
                # 调用起点是**已知位置**:tail 的末尾就是 pred_label 本身。骨架
                # 按铁律不带尾左括号,不锚这个位置的话,模型另起一行自己写的那条
                # 会被当成"骨架补完了"(实测:模型写 "Wait, that is wrong." 再自己
                # 换个工具,skeleton_done 照样报 True),这条设置的头号指标就废了
                seg = final if arm == "skel_switch" else rest
                pred = p.get("pred_label") or ""
                sk_call, sk_end = (call_at(seg, len(tail) - len(pred))
                                   if tail and pred else (None, None))
                fenced = tail.startswith(FENCE_OPEN)
                fin = (find_fence_close(seg, sk_end)
                       if sk_call is not None and fenced else None)
                skel_done = sk_call is not None and (fin is not None
                                                     or not fenced)
                # 没进正文段(骨架臂常常不转场)时 tool 是 None:那是"没写正文",
                # 不是"没改写",记 None 让它不进分母,否则改写率被稀释成偏低
                tool_rw = (tool != p.get("pred_label")) if tool else None
                if arm not in ARMS_FINAL and sk_call is not None:
                    # 骨架补完点(有围栏就算到围栏闭合)到转场之间又想了多少字符;
                    # 没转场的话 rest 就是整段续写,一路量到末尾
                    end = fin if fin is not None else sk_end
                    post_think = len(rest) - end
            # 完整调用:骨架臂取骨架处补完的那条(工具名钉死之后模型自己写的
            # 参数,也正是 extract_completed.py 送去真执行的那条),抽不到再退
            # 回正文段;其余臂只看正文段。两边口径必须一致,否则对不了账。
            # 注意 tool_rewritten=True 的事件上抽的仍是骨架处那条,而模型在正文
            # 段已经换了工具 —— 那个子集送去真执行,量的是模型自己放弃的调用,
            # 出数时要按 tool_rewritten 分开读(md 报告的口径行里写了)
            call_out = (sk_call if sk_call is not None
                        else complete_call(final)[0])
            out_tok = o["head_tok"] + o["gen_tok"]
            base = p.get("baseline_out_tok")
            # 主对照是 baseline(原轨迹):模型当时从这一步自己写到发出调用实际
            # 花了多少 out token,盘上现成。nofill 降级为管线体检线 —— 它与本臂
            # 的 prompt 构造方式完全相同(同样重建、同样在 cut 处截断、同样重新
            # tokenize),只差拼进去那一截,所以 nofill≈baseline 才说明重建与
            # 采样口径没跑偏,这批数字才放行。
            rec = dict(
                event=ev, arm=arm, depth=p["depth"], conf=p["conf"],
                inject_source=p["inject_source"],
                full_call_ok=p["full_call_ok"], tool_ok=p["tool_ok"],
                pred_label=p.get("pred_label"), gen_min_p=p.get("gen_min_p"),
                name_hit=(p.get("pred_label") == p["label"]),
                out_tok=out_tok, nofill_out_tok=nof_out,
                baseline_out_tok=base,
                saved_tok=(base - out_tok) if base else None,
                saved_ratio=(round((base - out_tok) / base, 4)
                             if base else None),
                nofill_delta=((nof_out - out_tok)
                              if nof_out is not None else None),
                baseline_drift=(out_tok - base) if base else None,
                gen_tok=o["gen_tok"], head_tok=o["head_tok"],
                has_code=bool(m), tool_out=tool, call_out=call_out,
                skeleton_done=skel_done, tool_rewritten=tool_rw,
                post_think_chars=post_think,
                # 注入成功的样子是"跳过被注入的那个调用、直接干下一件事",
                # 所以 repeated 高才是坏事(模型无视了注入)。
                # 注意 appworld 把调用嵌在 python 里、结果常要赋值给变量再用,
                # 所以重调一次未必等于无视注入,两个指标要一起看。
                repeated_injected=(tool == p["label"]),
                advanced=(tool is not None and tool != p["label"]),
                same_as_baseline_step=(tool == p["baseline_tool"]),
                finish_reason=o["finish_reason"])
            if is_exec:
                # 只在 execute 档加:skip/oracle 的 per_event.jsonl 逐字节不变
                rec.update(
                    exec_ok=p.get("exec_ok"),
                    matched_traj_result=p.get("matched_traj_result"),
                    prefix_verbatim=p.get("prefix_verbatim"),
                    error_kind=p.get("error_kind"),
                    arg_modes=p.get("arg_modes"))
            per.append(rec)
            by_arm[arm].append(rec)

    def agg(rs):
        n = len(rs)
        if not n:
            return {}
        sv = sorted(r["saved_tok"] for r in rs if r["saved_tok"] is not None)
        sr = [r["saved_ratio"] for r in rs if r["saved_ratio"] is not None]
        dr = sorted(abs(r["baseline_drift"]) for r in rs
                    if r["baseline_drift"] is not None)
        nd = sorted(r["nofill_delta"] for r in rs
                    if r["nofill_delta"] is not None)
        sd = [r["skeleton_done"] for r in rs if r["skeleton_done"] is not None]
        tw = [r["tool_rewritten"] for r in rs
              if r["tool_rewritten"] is not None]
        pt = sorted(r["post_think_chars"] for r in rs
                    if r["post_think_chars"] is not None)
        return dict(
            n=n,
            saved_tok_mean=round(sum(sv) / len(sv), 1) if sv else None,
            saved_tok_median=sv[len(sv) // 2] if sv else None,
            saved_ratio_mean=round(sum(sr) / len(sr), 4) if sr else None,
            saved_positive=(round(sum(1 for x in sv if x > 0) / len(sv), 4)
                            if sv else None),
            out_tok_mean=round(sum(r["out_tok"] for r in rs) / n, 1),
            has_code=round(sum(r["has_code"] for r in rs) / n, 4),
            repeated_injected=round(sum(r["repeated_injected"]
                                        for r in rs) / n, 4),
            advanced=round(sum(r["advanced"] for r in rs) / n, 4),
            baseline_drift_median=dr[len(dr) // 2] if dr else None,
            # 体检线:nofill 与本臂的差,只看管线有没有跑偏,不当收益
            nofill_delta_median=nd[len(nd) // 2] if nd else None,
            skeleton_done=round(sum(sd) / len(sd), 4) if sd else None,
            tool_rewritten=round(sum(tw) / len(tw), 4) if tw else None,
            post_think_median=pt[len(pt) // 2] if pt else None,
            truncated=round(sum(r["finish_reason"] == "length"
                                for r in rs) / n, 4))

    # 按触发深度分桶:免费拿到"注入位置 vs 收益"曲线,看死区在不在
    buckets = defaultdict(lambda: defaultdict(list))
    for r in per:
        buckets[min(int(r["depth"] * 5), 4)][r["arm"]].append(r)

    # saved_tok 的主对照写进报告:老报告没这个键,读的人(和下游算曲线的
    # sweep_theta)才分得清手上这份 per_event 是"相对原轨迹"还是老的
    # "相对 nofill" —— 两种口径的 saved_tok 混进同一个比值就是算错
    out = dict(run_dir=str(d), config=cfg, saved_baseline=SAVED_BASELINE,
               by_arm={k: agg(v) for k, v in by_arm.items()},
               by_depth={f"{b*0.2:.1f}-{(b+1)*0.2:.1f}":
                         {k: agg(v) for k, v in arms.items()}
                         for b, arms in sorted(buckets.items())},
               by_hit={
                   "hit": {k: agg([r for r in v if r["full_call_ok"]])
                           for k, v in by_arm.items()},
                   "miss": {k: agg([r for r in v if not r["full_call_ok"]])
                            for k, v in by_arm.items()}})
    # 骨架臂的猜错桶是 name_hit(探针预测的工具名对不对),不是 full_call_ok:
    # 骨架只钉工具名,参数是大模型现写的,拿整条调用的对错分桶分错了东西
    skel = {k: v for k, v in by_arm.items() if k in ARMS_SKEL}
    if skel:
        out["by_name_hit"] = {
            "hit": {k: agg([r for r in v if r["name_hit"]])
                    for k, v in skel.items()},
            "miss": {k: agg([r for r in v if not r["name_hit"]])
                     for k, v in skel.items()}}
    if is_exec:
        # execute 档必须按注入来源分桶:exec_pred 注入的是"那一条调用的返回",
        # traj_hit 注入的是"整块 stdout",99/1061 个多调用块上这俩不是一回事。
        # 混成一条均值就是把两种口径搅在一起,报出来的省 token 说明不了什么。
        src_of = {}
        for r in per:
            src_of.setdefault(r["inject_source"], []).append(r)
        out["by_inject_source"] = {
            s: {arm: agg([r for r in rs if r["arm"] == arm])
                for arm in sorted({r["arm"] for r in rs})}
            for s, rs in sorted(src_of.items())}
        pl = list(plan.values())
        fired_exec = [p for p in pl if p["inject_source"] in
                      ("exec_pred", "exec_error")]
        # 验收线的三条门槛见 merge-exec 里的注释:缺一条两边不可比
        acc = [p for p in fired_exec
               if p.get("full_call_ok") and p.get("n_calls_in_block") == 1
               and p.get("traj_bare_print")]
        vb = [p for p in fired_exec
              if p.get("matched_traj_result") is not None]
        out["exec"] = dict(
            note="正确率是单步调用一致率,不是 appworld 任务级成绩",
            exec_scope=cfg.get("exec_scope"),
            n_exec_pred=sum(1 for p in pl
                            if p["inject_source"] == "exec_pred"),
            n_exec_error=sum(1 for p in pl
                             if p["inject_source"] == "exec_error"),
            n_exec_missing=sum(1 for p in pl
                               if p["inject_source"] == "exec_missing"),
            exec_error_rate=(round(sum(1 for p in fired_exec
                                       if p["inject_source"] == "exec_error")
                                   / len(fired_exec), 4)
                             if fired_exec else None),
            # 验收线:hit + 单调用 + 代码块是一句干净的 print(调用)
            acceptance_matched=sum(1 for p in acc
                                   if p.get("matched_traj_result")
                                   or p.get("matched_traj_error")),
            acceptance_exact=sum(1 for p in acc
                                 if p.get("matched_traj_result")),
            acceptance_n=len(acc),
            acceptance_excluded_mixed=sum(
                1 for p in fired_exec
                if p.get("full_call_ok") and p.get("n_calls_in_block") == 1
                and not p.get("traj_bare_print")),
            matched_traj_result=(round(sum(1 for p in vb
                                           if p["matched_traj_result"])
                                       / len(vb), 4) if vb else None),
            n_drift=sum(1 for p in fired_exec
                        if p.get("prefix_verbatim") is False),
            arg_modes=dict(Counter(m for p in fired_exec
                                   for m in (p.get("arg_modes") or []))),
            error_kind=dict(Counter(p["error_kind"] for p in fired_exec
                                    if p.get("error_kind"))))
    (d / f"INJECT_REPORT{a.tag}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    with open(d / f"per_event{a.tag}.jsonl", "w") as f:
        for r in per:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    L = [f"# 注入回放报告 {d.name}", "",
         f"- 口径 risk={cfg['risk']} θ={cfg['theta']} "
         f"miss_policy={cfg['miss_policy']} permit={cfg.get('permit')}",
         f"- 事件 {cfg['n_events_test']} 触发 {cfg['n_fired']} "
         f"入计划 {cfg['n_planned']} 可注入 {cfg['n_inject']}", "",
         "> 省 token 的**主对照是原轨迹**:saved_tok = 原轨迹该步的 out token",
         "> 减本臂的 out token(原轨迹那个数是模型当时自己从这里写到发出调用",
         "> 实际花掉的,盘上现成)。",
         "> **nofill 只是管线体检线**:nofill体检 = nofill 的 out token 减本臂的,",
         "> 用来看重建与采样口径有没有跑偏(nofill≈原轨迹才放行整批数字),不当收益。",
         "> repeated_injected = 续写又调了一遍被注入的工具(越低越说明采纳了注入),",
         "> 但 appworld 把调用嵌在 python 里、结果常要赋值给变量,重调未必等于无视。",
         "", "## 按 arm", "",
         "| arm | n | 省token均值 | 省token中位 | 省比例 | 省为正 | 出token均值 "
         "| 出代码块 | 重调被注入的 | 推进 | nofill体检中位 | 撞长度上限 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in out["by_arm"].items():
        L.append(f"| {k} | {v['n']} | {v['saved_tok_mean']} | "
                 f"{v['saved_tok_median']} | {v['saved_ratio_mean']} | "
                 f"{v['saved_positive']} | {v['out_tok_mean']} | "
                 f"{v['has_code']} | {v['repeated_injected']} | "
                 f"{v['advanced']} | {v['nofill_delta_median']} | "
                 f"{v['truncated']} |")
    L += ["", "## 按触发深度分桶(死区诊断)", "",
          "| depth | arm | n | 省token均值 | 重调被注入的 | 推进 |",
          "|---|---|---|---|---|---|"]
    for b, arms in out["by_depth"].items():
        for k, v in arms.items():
            L.append(f"| {b} | {k} | {v['n']} | {v['saved_tok_mean']} | "
                     f"{v['repeated_injected']} | {v['advanced']} |")
    if "by_name_hit" in out:
        L += ["", "## 骨架臂(工具名由探针钉死,大模型只写参数)", "",
              "> 骨架补完 = 模型**接着骨架那个位置**把调用写完(括号配平,拼了围栏"
              "的还要围栏闭合);另起一行自己写一条不算补完。",
              "> 工具名被改写 = 模型在正文段换了个工具,分母只算写出了正文调用的"
              "事件(没转场的记 None,要跟出代码块那一列一起读)。",
              "> 补完后又想 = 骨架补完点到转场之间的字符数。",
              "> name_hit = 探针预测的工具名与原轨迹一致;猜错桶就是这条设置要付的代价。",
              "> **call_out(送去真执行的那条)一律取骨架处补完的那条**:工具名被"
              "改写的那部分事件上,执行的是模型自己已经放弃的调用,那个子集的执行"
              "正确率不能当这条设置的成绩读。",
              "",
              "| arm | n | 骨架补完 | 工具名被改写 | 补完后又想(中位字符) | "
              "猜对 n | 猜对省token中位 | 猜错 n | 猜错省token中位 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for k in out["by_name_hit"]["hit"]:
            v = out["by_arm"][k]
            h = out["by_name_hit"]["hit"][k]
            ms = out["by_name_hit"]["miss"][k]
            L.append(f"| {k} | {v['n']} | {v['skeleton_done']} | "
                     f"{v['tool_rewritten']} | {v['post_think_median']} | "
                     f"{h.get('n', 0)} | {h.get('saved_tok_median')} | "
                     f"{ms.get('n', 0)} | {ms.get('saved_tok_median')} |")
    if is_exec:
        e = out["exec"]
        L.insert(4, "> ⚠️ **execute 档:这里的正确率是单步调用一致率,不是 "
                    "appworld 任务级成绩。** 一个事件只续写一步、不跑到底、"
                    "不调 world.evaluate()。任务级那条轴要另建 in-loop rollout。")
        L += ["", "## execute 档口径", "",
              f"- exec_scope = {e['exec_scope']};真执行 "
              f"{e['n_exec_pred'] + e['n_exec_error']} 个事件,其中报错 "
              f"{e['n_exec_error']} 个(报错率 {e['exec_error_rate']}),"
              f"没拿到执行记录 {e['n_exec_missing']} 个",
              f"- **验收线**:预测与真实一致、代码块只含 1 个调用、且该代码块就是"
              f"一句干净的 print(调用) —— 这类事件里执行输出与轨迹录下的 result "
              f"对得上 {e['acceptance_matched']}/{e['acceptance_n']}"
              f"(其中逐字相同 {e['acceptance_exact']},其余是调用本身报错、"
              f"报错消息一致但 traceback 回显的引号风格不同)。另有 "
              f"{e['acceptance_excluded_mixed']} 个 hit+单调用事件因为代码块不是"
              f"一句干净的 print 而两边不可比,没算进验收线",
              f"- 全部真执行事件里输出与录下的 result 逐字相同的比例 "
              f"{e['matched_traj_result']}(多调用块本来就不该相同,这里只作参考)",
              f"- 前缀重放漂了的事件 {e['n_drift']}(拿错状态执行的,报告里不能"
              f"当真账)",
              f"- 补引号的分支计数 {e['arg_modes']}",
              f"- 执行报错的种类 {e['error_kind']}", "",
              "> 猜错的代价在这一档才进账:预测调用报错时,报错文本原样注入,"
              "用的还是同一个 [SYSTEM NOTE: prefetched ...] 模板(与 hit 事件可比)。",
              "", "### 按注入来源分桶(**不许混成一条均值**)", "",
              "| 来源 | arm | n | 省token均值 | 省token中位 | 省比例 | "
              "出token均值 | 出代码块 | 重调被注入的 | 推进 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for s, arms in out["by_inject_source"].items():
            for k, v in arms.items():
                L.append(f"| {s} | {k} | {v['n']} | {v['saved_tok_mean']} | "
                         f"{v['saved_tok_median']} | {v['saved_ratio_mean']} | "
                         f"{v['out_tok_mean']} | {v['has_code']} | "
                         f"{v['repeated_injected']} | {v['advanced']} |")
    (d / f"INJECT_REPORT{a.tag}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--ctool-run", required=True)
    p.add_argument("--cgen-run", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--traj-root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--risk", type=float, default=0.1)
    p.add_argument("--theta", type=float, default=None,
                   help="直接钉 θ,盖过 --risk 的反查(θ 扫描曲线用)")
    p.add_argument("--decision-file", default=None,
                   help="外部逐事件判定 JSONL:{event, fire, sent_idx},给了就"
                        "完全替代 θ 判定(产阈值模型的接口),conf 照旧算")
    p.add_argument("--miss-policy", default="skip",
                   choices=["skip", "oracle", "execute"])
    p.add_argument("--exec-scope", default="all", choices=["all", "miss"],
                   help="只在 miss_policy=execute 生效。all=连 hit 事件也真执行"
                        "(口径统一,顺手修掉多调用块那条偏差);"
                        "miss=只执行猜错的,hit 仍走 traj_hit(与旧曲线可比)")
    p.add_argument("--permit", action="store_true", help="system 里加授权句")
    p.add_argument("--device", default="cuda")
    p.add_argument("--bs", type=int, default=8)
    p.add_argument("--max-new-tokens", type=int, default=96)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("merge-exec",
                       help="plan.jsonl + exec_calls.jsonl -> plan_exec.jsonl")
    p.add_argument("--plan", required=True)
    p.add_argument("--exec", required=True,
                   help="exec_calls.py 的产物;分片会自动收 <stem>*<suffix>,"
                        "也接受逗号分隔的多个文件")
    p.set_defaults(fn=cmd_merge_exec)

    p = sub.add_parser("run")
    p.add_argument("--plan", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", default="gpt-oss-120b")
    p.add_argument("--tokenizer", default="/net/tokyo100-10g/data/str01_01/"
                                          "y-guo/models/gpt-oss-120b")
    p.add_argument("--arms", default="nofill,inject",
                   help="可选 " + ",".join(ARMS_ALL))
    p.add_argument("--form-table", default=str(HERE / "form_table.json"),
                   help="build_form_table.py 的产物,决定骨架是 print 形还是"
                        "赋值形;文件不在就一律 print 形")
    p.add_argument("--preset", default="default",
                   help="configs/presets/<名>.json 的一套生成设置"
                        "(temperature/top_p/max_tokens/stop/seed);"
                        "缺省 default;命令行显式给的压过预设值")
    # 采集时 max_tokens=8192(envs/collect/common.py 的 Chat 缺省)。设小了 nofill
    # 会被截断,与 baseline 不可比 —— 单步 baseline_out_tok 实测有到 5681 的
    p.add_argument("--max-tokens", type=int, default=None,
                   help="缺省 8192(预设也没给时)")
    p.add_argument("--dry-run", action="store_true",
                   help="只拼 prompt 落盘,不发请求(验证拼接,不占服务)")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tag", default="")
    p.add_argument("--permit", action="store_true")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--no-pin-date", action="store_true",
                   help="不把 Current date 钉回采集日(默认钉,保证逐字重建)")
    p.add_argument("--assume-date", action="store_true",
                   help="承认重建日期与采集日期不同,继续跑")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("score")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--plan-file", default="plan.jsonl",
                   help="execute 档用 plan_exec.jsonl(config 名跟着它推)")
    p.add_argument("--form-table", default=str(HERE / "form_table.json"),
                   help="必须与 run 时用的是同一张表:骨架串不落在 raw 里,"
                        "抽调用要照它重新拼一遍")
    p.add_argument("--tag", default="")
    p.add_argument("--rebaseline", action="store_true",
                   help="允许把旧口径(saved_tok 相对 nofill)的报告覆盖成新口径"
                        "(相对原轨迹)。只重跑一个 θ 点会让 sweep_theta curve "
                        "两种口径求和,加这个开关就是承诺整条曲线一起重跑")
    p.set_defaults(fn=cmd_score)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
