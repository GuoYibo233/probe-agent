"""文本层注入的离线回放实验(appworld / gpt-oss)。

要回答的问题:探针在思考段中途判定"接下来要调这个工具"的那一刻,把该工具的
结果直接拼进思考流,模型能不能少写一大段、还照样发出正确的调用。

三段式,分开跑,各自落盘:
  plan   算触发点 + 生成预测调用 + 决定注入内容 -> plan.jsonl
         (要 GPU,但只用 0.6B 的参数产线;探针触发点直接读已落盘的 logits)
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
  execute    起 appworld 把环境重放到该步、真执行预测出的调用取返回
             (真·无脑全注入,尚未实现,接口已留)

口径与已知偏差(报告里都要带上,别静默):
- 注入的 result 是该步整个代码块的 stdout,而探针预测的是代码块里第一个
  api 调用(build.py:70-72 的 label 口径)。一个代码块含多个调用时,注入的
  内容比"那一个调用的返回"更多。第一版接受这个偏差,report 里单列该比例。
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

  cprobe-env/bin/python pipeline/inject/replay_inject.py run \\
      --plan pipeline/inject/runs/aw_gptoss_r10/plan.jsonl \\
      --base-url http://tokyo108:8103/v1 --model gpt-oss-120b \\
      --arms nofill,inject

  cprobe-env/bin/python pipeline/inject/replay_inject.py score \\
      --run-dir pipeline/inject/runs/aw_gptoss_r10
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "annotate"))

import rebuild as R                                          # noqa: E402
from rules import AW_CALL, boundaries                        # noqa: E402

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
    theta = rep["chosen_theta"].get(str(a.risk))
    if theta is None:
        raise SystemExit(f"θ 里没有 risk={a.risk}:{rep['chosen_theta']}")

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
        elif hit:
            inj_call, inj_res, src = gen_call, result, "traj_hit"
        elif a.miss_policy == "skip":
            inj_call, inj_res, src = None, None, "none"
        else:                                    # execute
            raise NotImplementedError(
                "--miss-policy execute 需要把 appworld 环境重放到该步再真执行"
                "预测出的调用;接口留在这里,尚未实现")

        action = envs[st].get("action") or ""
        plan.append(dict(
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
            traj_path=str(tp)))

    with open(out_dir / "plan.jsonl", "w") as f:
        for p in plan:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    cfg = dict(ctool_run=str(ctool), cgen_run=str(cgen), data=str(data),
               traj_root=str(root), risk=a.risk, theta=theta, temperature=T,
               miss_policy=a.miss_policy, permit=a.permit,
               n_events_test=n_events, n_fired=len(keys), n_planned=len(plan),
               drop=dict(drop),
               n_inject=sum(1 for p in plan if p["inject_source"] != "none"),
               n_hit=sum(1 for p in plan if p["full_call_ok"]),
               n_multicall=sum(1 for p in plan if p["n_calls_in_block"] > 1),
               n_literal=sum(1 for p in plan if p["literal_harmony"]))
    (out_dir / "plan_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1))
    print(json.dumps(cfg, ensure_ascii=False, indent=1))


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
    from transformers import AutoTokenizer
    plan_path = Path(a.plan)
    out_dir = plan_path.parent
    cfg = json.loads((out_dir / "plan_config.json").read_text())
    plan = [json.loads(l) for l in open(plan_path)]
    if a.limit:
        plan = plan[:a.limit]
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    tok = AutoTokenizer.from_pretrained(a.tokenizer)

    sink = open(out_dir / f"raw{a.tag}.jsonl", "a")
    done = set()
    rp = out_dir / f"raw{a.tag}.jsonl"
    if rp.exists():
        for l in open(rp):
            try:
                o = json.loads(l)
                done.add((o["event"], o["arm"]))
            except Exception:
                pass
    n_skip = 0
    for i, p in enumerate(plan):
        meta, gens, envs, _ = R.load_traj(Path(p["traj_path"]))
        msgs = R.build_messages(meta, gens, envs, p["step"])
        if a.permit or cfg.get("permit"):
            msgs[0]["content"] = msgs[0]["content"] + PERMIT
        prefix = R.build_prefix(tok, msgs)
        if not a.assume_date:
            R.assert_date(prefix)
        think = (gens[p["step"]].get("reasoning") or "").strip()
        head = think[:p["cut"]]
        head_tok = len(tok.encode(head, add_special_tokens=False))

        for arm in arms:
            if (p["event"], arm) in done:
                n_skip += 1
                continue
            if arm == "inject" and p["inject_source"] == "none":
                continue
            note = ""
            if arm == "inject":
                note = NOTE_TMPL.format(call=p["inject_call"],
                                        result=p["inject_result"])
            prompt = prefix + R.ANALYSIS_OPEN + head + note
            if a.dry_run:
                sink.write(json.dumps(dict(
                    event=p["event"], arm=arm, dry=True,
                    prompt_chars=len(prompt), head_tok=head_tok,
                    note_chars=len(note),
                    prompt_tok=len(tok.encode(prompt,
                                              add_special_tokens=False)),
                    baseline_out_tok=p["baseline_out_tok"],
                    tail=prompt[-160:]), ensure_ascii=False) + "\n")
                continue
            t0 = time.time()
            r = post_completions(a.base_url, dict(
                model=a.model, prompt=prompt, max_tokens=a.max_tokens,
                temperature=0.0, stop=DEFAULT_STOP,
                skip_special_tokens=False), a.timeout)
            ch = r["choices"][0]
            sink.write(json.dumps(dict(
                event=p["event"], arm=arm, text=ch["text"],
                finish_reason=ch.get("finish_reason"),
                prompt_tok=r["usage"]["prompt_tokens"],
                gen_tok=r["usage"]["completion_tokens"],
                head_tok=head_tok,
                note_chars=len(note), wall_s=round(time.time() - t0, 2),
            ), ensure_ascii=False) + "\n")
            sink.flush()
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(plan)} done", flush=True)
    sink.close()
    print(f"完成 {len(plan)} 条 x {arms};跳过已有 {n_skip} 条 -> {rp}")


# ---------------------------------------------------------------- score

def split_channels(text):
    """把续写切成 (analysis 剩余, final 内容)。"""
    if FINAL_OPEN in text:
        head, tail = text.split(FINAL_OPEN, 1)
        return head, tail
    return text, ""


def cmd_score(a):
    d = Path(a.run_dir)
    cfg = json.loads((d / "plan_config.json").read_text())
    plan = {json.loads(l)["event"]: json.loads(l)
            for l in open(d / "plan.jsonl")}
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
    p.add_argument("--miss-policy", default="skip",
                   choices=["skip", "oracle", "execute"])
    p.add_argument("--permit", action="store_true", help="system 里加授权句")
    p.add_argument("--device", default="cuda")
    p.add_argument("--bs", type=int, default=8)
    p.add_argument("--max-new-tokens", type=int, default=96)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_plan)

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
    p.add_argument("--assume-date", action="store_true",
                   help="承认重建日期与采集日期不同,继续跑")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("score")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--tag", default="")
    p.set_defaults(fn=cmd_score)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
