"""BFCL 闭环 handler:QwenHandler 的流式+探针版(T9)。

不改 venv、不进注册表 —— demo 驱动(run_bfcl_demo.py)直接 import 本类构造。
口径由 loop_cfg["mode"] 决定:
  baseline  阻塞生成,等价原版,只记账(总账下限)
  shadow    流式生成 + 每句界探,只记不动;步末与 agent 实际调用核对
  truncate  流式生成,首次过 θ 断流(vLLM 弃算),合成调用注入对话
  fork      shadow 式生成;触发事件在步末复制现场跑分支到任务结束
            (分支内探针关闭、每事件限 fork 一次、禁嵌套 —— 规划书铁律)

现场复制依据 bfcl_eval 勘察(2026-07-30):环境实例挂在 multi_turn_utils
模块 globals(),key=f"{model}_{entry_id}_{class}_instance"(re.sub [-./:]→_);
multi_turn_base 全部涉事类可安全 deepcopy(框架自己逐轮 deepcopy 做 state_log)。
思考期间环境状态不变,步末 fork 与流中 fork 等价。
"""

import re
import sys
import time
from copy import deepcopy
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP_DIR))
from accounting import EpisodeLedger, tokenize_count  # noqa: E402
from probe_client import ProbeClient, ProbeMonitor  # noqa: E402
from textproto import HIST_ROUNDS  # noqa: E402

import bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils as mtu  # noqa: E402
from bfcl_eval.constants.default_prompts import MAXIMUM_STEP_LIMIT  # noqa: E402
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import (  # noqa: E402
    execute_multi_turn_func_call, is_empty_execute_response,
)
from bfcl_eval.model_handler.local_inference.qwen import QwenHandler  # noqa: E402
from overrides import override  # noqa: E402

BFCL_CALL = re.compile(r"(\w+)\(")  # 与 build_dataset.BFCL_CALL 同一正则


def default_synth(label):
    """T7 抽取头就位前的占位参数产线:只提交工具名、零参数。
    demo 验证机械流程用;正式跑分换成抽取头。"""
    return f"[{label}()]"


class QwenLoopHandler(QwenHandler):

    def __init__(self, *a, loop_cfg=None, **kw):
        super().__init__(*a, **kw)
        cfg = dict(loop_cfg or {})
        self.mode = cfg.get("mode", "baseline")
        assert self.mode in ("baseline", "shadow", "truncate", "fork")
        self.theta = float(cfg.get("theta", 0.95))
        self.out_dir = Path(cfg.get("out_dir", LOOP_DIR / "runs" / "demo"))
        self.probe = (ProbeClient(cfg["probe_url"])
                      if self.mode != "baseline" else None)
        self.fork_max = int(cfg.get("fork_max", 1))
        self.synth = cfg.get("synth") or default_synth
        self._entry = None
        self._ledger = None
        self._turn_idx = -1
        self._step = 0
        self._forks_done = 0

    # ---- 生命周期:一 entry 一本账 ----

    @override
    def inference(self, test_entry, include_input_log, exclude_state_log):
        self._entry = test_entry
        self._turn_idx, self._step, self._forks_done = -1, 0, 0
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._ledger = EpisodeLedger(
            self.out_dir / f"{test_entry['id']}_{self.mode}.jsonl",
            {"entry": test_entry["id"], "mode": self.mode,
             "theta": self.theta, "model": self.model_name})
        try:
            return super().inference(test_entry, include_input_log,
                                     exclude_state_log)
        finally:
            # bfcl 成败由 evaluate 阶段离线判,账本只管 token/墙钟/触发
            self._ledger.close(success=None, n_forks=self._forks_done)

    # ---- 轮次跟踪(fork 分支续跑要知道剩几轮) ----

    @override
    def add_first_turn_message_prompting(self, inference_data,
                                         first_turn_message) -> dict:
        self._turn_idx, self._step = 0, 0
        return super().add_first_turn_message_prompting(
            inference_data, first_turn_message)

    @override
    def _add_next_turn_user_message_prompting(self, inference_data,
                                              user_message) -> dict:
        self._turn_idx += 1
        self._step = 0
        return super()._add_next_turn_user_message_prompting(
            inference_data, user_message)

    # ---- 题干/历史构造:与 build_dataset.bfcl_events 逐条对齐 ----

    @staticmethod
    def task_hist(messages):
        """task=最近一条 user;hist 只收(思考与正文都非空的)assistant,
        动作截 200 字符,tool 消息回填结果 —— 全部照抄 bfcl_events。"""
        task, hist = "", []
        for m in messages:
            role, c = m["role"], (m.get("content") or "")
            if role == "user":
                task = c
            elif role == "assistant":
                rc = (m.get("reasoning_content") or "").strip()
                if rc and c.strip():
                    hist.append((c.strip()[:200], ""))
                    del hist[:-HIST_ROUNDS]
            elif role == "tool" and hist:
                hist[-1] = (hist[-1][0], c)
        return task, hist

    # ---- 生成:阻塞(baseline)或流式+monitor ----

    @override
    def _query_prompting(self, inference_data):
        sid = f"t{self._turn_idx}s{self._step}"
        self._step += 1
        if self.mode == "baseline":
            api_response, latency = super()._query_prompting(inference_data)
            self._ledger.gen(sid, {
                "usage": {"in": api_response.usage.prompt_tokens,
                          "out": api_response.usage.completion_tokens},
                "wall_s": round(latency, 2)})
            return api_response, latency

        function = inference_data["function"]
        message = inference_data["message"]
        formatted_prompt = self._format_prompt(message, function)
        inference_data["inference_input_log"] = {
            "formatted_prompt": formatted_prompt}
        input_tokens = len(self.tokenizer.tokenize(formatted_prompt))
        if self.max_context_length < input_tokens + 2:
            leftover = 1000
        else:
            leftover = min(4096, self.max_context_length - input_tokens - 2)

        task, hist = self.task_hist(message)
        event_id = f"{self._entry['id']}|{sid}"
        mon = ProbeMonitor(
            self.probe, self.theta,
            "truncate" if self.mode == "truncate" else "shadow",
            task, hist, event_id, sink=self._ledger.probe)

        t0 = time.time()
        stream = self.client.completions.create(
            model=self.model_path_or_id, temperature=self.temperature,
            prompt=formatted_prompt, max_tokens=leftover, stream=True,
            stream_options={"include_usage": True}, timeout=72000)
        raw, usage, aborted, in_think, hit = "", None, False, True, None
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = {"in": chunk.usage.prompt_tokens,
                         "out": chunk.usage.completion_tokens}
            if not chunk.choices:
                continue
            prev = len(raw)
            raw += chunk.choices[0].text or ""
            if in_think and "</think>" in raw[max(0, prev - 12):]:
                in_think = False
            if in_think:
                # 左 strip 与训练侧 think=rc.strip() 的坐标系对齐
                hit = mon.feed(raw.lstrip())
                if hit:
                    aborted = True
                    stream.close()
                    break
        latency = time.time() - t0

        think_full, sep, content = raw.partition("</think>")
        think = think_full.strip("\n")
        if not aborted:
            # 思考收尾:与训练同源的 strip 后补探全文末尾切点
            mon.feed(think.strip())
            mon.finalize()

        if aborted:
            prefix = raw.lstrip()[:hit["at_char"]]
            resp = {"model_responses": self.synth(hit["label"]),
                    "reasoning_content": prefix,
                    "input_token": input_tokens,
                    "output_token": tokenize_count(
                        self.base_url, self.model_path_or_id, raw)}
            self._ledger.trigger(sid, dict(hit, truncated=True),
                                 agent_actual=None, match=None)
        else:
            content = content.lstrip("\n") if sep else raw
            if not sep:
                content = ""
            resp = {"model_responses": content, "reasoning_content": think,
                    "input_token": (usage or {}).get("in") or input_tokens,
                    "output_token": (usage or {}).get("out") or 0}
            if mon.first_trigger:
                m = BFCL_CALL.search(content)
                actual = m.group(1) if m else None
                self._ledger.trigger(
                    sid, dict(mon.first_trigger, truncated=False),
                    agent_actual=actual,
                    match=(actual == mon.first_trigger["label"]))
                if self.mode == "fork" and self._forks_done < self.fork_max:
                    trig = dict(mon.first_trigger)
                    trig["prefix"] = think.strip()[:trig["at_char"]]
                    self._run_fork(inference_data, trig, sid)

        self._ledger.gen(sid, {"usage": {"in": resp["input_token"],
                                         "out": resp["output_token"]},
                               "wall_s": round(latency, 2),
                               "aborted": aborted,
                               "reasoning": resp["reasoning_content"]})
        return resp, latency

    @override
    def _parse_query_response_prompting(self, api_response) -> dict:
        if isinstance(api_response, dict):  # 流式路径已是解析后形态
            return api_response
        return super()._parse_query_response_prompting(api_response)

    # ---- fork 对照:步末复制现场,分支探针关闭 ----

    def _run_fork(self, inference_data, trig, parent_sid):
        self._forks_done += 1
        eid = self._entry["id"]
        fork_id = f"{eid}_fork{self._forks_done}"
        mkey = self.model_name_underline_replaced
        for cname in self._entry["involved_classes"]:
            main_key = re.sub(r"[-./:]", "_",
                              f"{mkey}_{eid}_{cname}_instance")
            fork_key = re.sub(r"[-./:]", "_",
                              f"{mkey}_{fork_id}_{cname}_instance")
            if main_key in vars(mtu):
                setattr(mtu, fork_key, deepcopy(vars(mtu)[main_key]))

        # 分支第 0 步 = 触发点截断的合成回复;prefix 由调用方按触发偏移
        # 从 strip 后思考原文切好放进 trig
        prefix = trig["prefix"]
        synth_text = self.synth(trig["label"])
        led = EpisodeLedger(
            self.out_dir / f"{eid}_{self.mode}_fork{self._forks_done}.jsonl",
            {"entry": eid, "mode": "fork_branch", "parent_step": parent_sid,
             "trigger": trig, "fork_id": fork_id})
        prefix_tokens = tokenize_count(self.base_url, self.model_path_or_id,
                                       prefix)
        pending = {"model_responses": synth_text,
                   "reasoning_content": prefix,
                   "input_token": 0, "output_token": prefix_tokens}
        bdata = {"message": deepcopy(inference_data["message"]),
                 "function": inference_data["function"]}
        self._add_assistant_message_prompting(bdata, pending)
        led.gen("fork_t0", {"usage": {"in": 0, "out": prefix_tokens},
                            "wall_s": 0.0, "aborted": True,
                            "reasoning": prefix})

        turn, steps_in_turn = self._turn_idx, self._step
        while True:
            end_turn = False
            try:
                decoded = self.decode_execute(pending["model_responses"],
                                              has_tool_call_tag=False)
                if is_empty_execute_response(decoded):
                    end_turn = True
            except Exception:
                end_turn = True
            if end_turn:
                turn += 1
                if turn >= len(self._entry["question"]):
                    break
                QwenHandler._add_next_turn_user_message_prompting(
                    self, bdata, self._entry["question"][turn])
                steps_in_turn = 0
            else:
                exec_results, _ = execute_multi_turn_func_call(
                    decoded, self._entry["initial_config"],
                    self._entry["involved_classes"], mkey, fork_id,
                    long_context=False, is_evaL_run=False)
                pending["model_responses_decoded"] = decoded
                bdata = self._add_execution_results_prompting(
                    bdata, exec_results, pending)
                led.env_step(steps_in_turn, decoded,
                             exec_results[0] if exec_results else "")
                steps_in_turn += 1
                if steps_in_turn > MAXIMUM_STEP_LIMIT:
                    break
            api_response, lat = QwenHandler._query_prompting(self, bdata)
            pending = QwenHandler._parse_query_response_prompting(
                self, api_response)
            self._add_assistant_message_prompting(bdata, pending)
            led.gen(f"fork_t{turn}", {
                "usage": {"in": pending["input_token"],
                          "out": pending["output_token"]},
                "wall_s": round(lat, 2),
                "reasoning": pending.get("reasoning_content", "")})
        led.close(success=None, n_turns_total=len(self._entry["question"]),
                  turns_reached=turn)
