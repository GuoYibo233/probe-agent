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

三个 arm(run 阶段用 --arms 选,可只跑一部分):
  baseline   不跑。直接用原轨迹的数字(模型当时自己写完了整步),
             即"完全不注入"那一档
  nofill     从截断点续写但不注入。用来验证续写管线本身没引入偏差——
             它应当≈baseline,对不上说明重建或采样口径有问题,这时
             inject 的差值也不可信
  inject     从截断点续写并注入工具结果

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
- 采集时 temperature=0.0(envs/collect/common.py:20),所以续写也用 greedy;
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

# 这些 inject_source 没有可注入的内容,inject 臂不发请求(但照样占省 token 的分母)。
# "none" = skip 档猜错;"exec_pending" = execute 档还没跑 exec 段;
# "exec_missing" = execute 段没给出记录(unit 中途炸了 / 该步轨迹里没执行过)。
# **exec_missing 绝不静默退回 "none"** —— 退回就等于又把猜错的代价抹掉了。
NO_INJECT = {"none", "exec_pending", "exec_missing"}


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
        rec = dict(fired=False, ok=False, sent_idx=None, row=None,
                   label=items[0][1]["label"])
        for _, r, p in items:
            conf, pred = float(p.max()), int(p.argmax())
            if conf >= theta:
                rec.update(fired=True, ok=(pred == r["y"]), conf=conf,
                           sent_idx=r["sent_idx"], row=r)
                break
        out[k] = rec
    return out


def gen_calls(cgen_dir, texts, device, bs, max_new):
    """跑参数产线,在触发点前缀上 greedy 写出整条调用。

    【照抄 eval_causal_call.py:171-192 的 generate()】——同样的 left padding、
    同样截到首行、同样从 meta.json 读 call_sep,保证与 CALLGEN_REPORT 可对账。
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
    out, prev = [], tok.padding_side
    tok.padding_side = "left"
    with torch.no_grad():
        for i in range(0, len(prompts), bs):
            enc = tok(prompts[i:i + bs], truncation=True,
                      max_length=max(max_len - max_new, 1), padding=True,
                      add_special_tokens=False, return_tensors="pt").to(device)
            g = model.generate(**enc, do_sample=False, max_new_tokens=max_new,
                               eos_token_id=tok.eos_token_id,
                               pad_token_id=tok.pad_token_id)
            txt = tok.batch_decode(g[:, enc["input_ids"].shape[1]:],
                                   skip_special_tokens=True)
            out += [t.split("\n")[0].strip() for t in txt]
            print(f"  gen {min(i + bs, len(prompts))}/{len(prompts)}",
                  flush=True)
    tok.padding_side = prev
    del model
    torch.cuda.empty_cache()
    return out


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
    # θ 两种来源:风险档反查(原口径,与 eval 的 chosen_theta 一致)或 --theta 直接给
    # (θ 扫描曲线用)。温度标定 T 与风险档无关,两种来源都用同一个 T,所以曲线上
    # 各点只差判定阈值,可直接横向比。
    if a.theta is not None:
        theta, theta_source = a.theta, "explicit"
    else:
        theta = rep["chosen_theta"].get(str(a.risk))
        if theta is None:
            raise SystemExit(f"θ 里没有 risk={a.risk}:{rep['chosen_theta']}")
        theta_source = f"risk={a.risk}"

    # 行过滤必须与 eval 侧逐行一致,否则与 logits_test.pt 不同序
    label2id = json.loads((ctool / "best" / "label_map.json").read_text())
    rows = [r for r in (json.loads(l) for l in open(data / "test.jsonl"))
            if r["label"] in label2id]
    for r in rows:
        r["y"] = label2id[r["label"]]
    logits = torch.load(ctool / "logits_test.pt", map_location="cpu")
    assert len(rows) == logits.shape[0], (len(rows), logits.shape)
    fired = replay_fire(rows, torch.softmax(logits / T, -1), theta)

    keys = [k for k in dict.fromkeys(r["event"] for r in rows)
            if fired[k]["fired"]]
    n_events = len({r["event"] for r in rows})
    print(f"事件 {n_events} 触发 {len(keys)} (θ={theta} T={T:.4f} "
          f"risk={a.risk})", flush=True)
    if a.limit:
        keys = keys[:a.limit]

    print(f"参数产线生成 {len(keys)} 条调用 ...", flush=True)
    calls = gen_calls(cgen, [fired[k]["row"]["text"] for k in keys],
                      a.device, a.bs, a.max_new_tokens)

    traj_cache, plan, drop = {}, [], defaultdict(int)
    for k, gen_call in zip(keys, calls):
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
               miss_policy=a.miss_policy, permit=a.permit,
               n_events_test=n_events, n_fired=len(keys), n_planned=len(plan),
               drop=dict(drop),
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
    todo = [(p, arm) for p in plan for arm in arms
            if (p["event"], arm) not in done
            and not (arm == "inject" and p["inject_source"] in NO_INJECT)]
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
        note = (NOTE_TMPL.format(call=p["inject_call"],
                                 result=p["inject_result"])
                if arm == "inject" else "")
        prompt = prefix + R.ANALYSIS_OPEN + head + note
        if a.dry_run:
            return dict(event=p["event"], arm=arm, dry=True,
                        prompt_chars=len(prompt), head_tok=head_tok,
                        note_chars=len(note),
                        prompt_tok=len(tok.encode(
                            prompt, add_special_tokens=False)),
                        baseline_out_tok=p["baseline_out_tok"],
                        tail=prompt[-160:])
        t0 = time.time()
        r = post_completions(a.base_url, dict(
            model=a.model, prompt=prompt, max_tokens=a.max_tokens,
            temperature=0.0, stop=DEFAULT_STOP,
            skip_special_tokens=False), a.timeout)
        ch = r["choices"][0]
        return dict(event=p["event"], arm=arm, text=ch["text"],
                    finish_reason=ch.get("finish_reason"),
                    prompt_tok=r["usage"]["prompt_tokens"],
                    gen_tok=r["usage"]["completion_tokens"],
                    head_tok=head_tok, note_chars=len(note),
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


def cmd_score(a):
    d = Path(a.run_dir)
    plan_p = d / a.plan_file
    cfg = json.loads(config_path_for(plan_p).read_text())
    is_exec = cfg.get("miss_policy") == "execute"
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
            _, final = split_channels(o["text"])
            m = CODE_RE.search(final)
            code = m.group(1) if m else ""
            tool = first_api_call(code)
            out_tok = o["head_tok"] + o["gen_tok"]
            base = p.get("baseline_out_tok")
            # 主对照是 nofill:它与 inject 的 prompt 构造方式完全相同(同样的
            # 重建串、同样在 cut 处截断、同样重新 tokenize),唯一差别就是注入行。
            # baseline(原轨迹)只作参考——从 cut 处重新 tokenize 再 greedy 续写
            # 无法逐字重现原始 token 流,偏差实测可达数千 token,不能当基准。
            rec = dict(
                event=ev, arm=arm, depth=p["depth"], conf=p["conf"],
                inject_source=p["inject_source"],
                full_call_ok=p["full_call_ok"], tool_ok=p["tool_ok"],
                out_tok=out_tok, nofill_out_tok=nof_out,
                baseline_out_tok=base,
                saved_tok=(nof_out - out_tok) if nof_out is not None else None,
                saved_ratio=(round((nof_out - out_tok) / nof_out, 4)
                             if nof_out else None),
                baseline_drift=(out_tok - base) if base else None,
                gen_tok=o["gen_tok"], head_tok=o["head_tok"],
                has_code=bool(m), tool_out=tool,
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
            truncated=round(sum(r["finish_reason"] == "length"
                                for r in rs) / n, 4))

    # 按触发深度分桶:免费拿到"注入位置 vs 收益"曲线,看死区在不在
    buckets = defaultdict(lambda: defaultdict(list))
    for r in per:
        buckets[min(int(r["depth"] * 5), 4)][r["arm"]].append(r)

    out = dict(run_dir=str(d), config=cfg,
               by_arm={k: agg(v) for k, v in by_arm.items()},
               by_depth={f"{b*0.2:.1f}-{(b+1)*0.2:.1f}":
                         {k: agg(v) for k, v in arms.items()}
                         for b, arms in sorted(buckets.items())},
               by_hit={
                   "hit": {k: agg([r for r in v if r["full_call_ok"]])
                           for k, v in by_arm.items()},
                   "miss": {k: agg([r for r in v if not r["full_call_ok"]])
                            for k, v in by_arm.items()}})
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
         "> 省 token 一律相对 **nofill**(同样构造、同样截断、只差注入行)。",
         "> baseline_drift = 与原轨迹该步 out token 的差,只作参考:从 cut 处",
         "> 重新 tokenize 再 greedy 续写无法逐字重现原始 token 流。",
         "> repeated_injected = 续写又调了一遍被注入的工具(越低越说明采纳了注入),",
         "> 但 appworld 把调用嵌在 python 里、结果常要赋值给变量,重调未必等于无视。",
         "", "## 按 arm", "",
         "| arm | n | 省token均值 | 省token中位 | 省比例 | 省为正 | 出token均值 "
         "| 出代码块 | 重调被注入的 | 推进 | |base偏差|中位 | 撞长度上限 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in out["by_arm"].items():
        L.append(f"| {k} | {v['n']} | {v['saved_tok_mean']} | "
                 f"{v['saved_tok_median']} | {v['saved_ratio_mean']} | "
                 f"{v['saved_positive']} | {v['out_tok_mean']} | "
                 f"{v['has_code']} | {v['repeated_injected']} | "
                 f"{v['advanced']} | {v['baseline_drift_median']} | "
                 f"{v['truncated']} |")
    L += ["", "## 按触发深度分桶(死区诊断)", "",
          "| depth | arm | n | 省token均值 | 重调被注入的 | 推进 |",
          "|---|---|---|---|---|---|"]
    for b, arms in out["by_depth"].items():
        for k, v in arms.items():
            L.append(f"| {b} | {k} | {v['n']} | {v['saved_tok_mean']} | "
                     f"{v['repeated_injected']} | {v['advanced']} |")
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
    p.add_argument("--arms", default="nofill,inject")
    # 采集时 max_tokens=8192(envs/collect/common.py:20)。设小了 nofill 会被
    # 截断,与 baseline 不可比 —— 单步 baseline_out_tok 实测有到 5681 的
    p.add_argument("--max-tokens", type=int, default=8192)
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
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_score)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
