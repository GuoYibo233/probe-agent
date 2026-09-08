"""Unified trajectory storage. One JSONL per trajectory, recording four things at every step:
the model input (incremental), the model's raw output (reasoning kept verbatim), the action,
and the environment's raw return.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from openai import OpenAI

# The harmony system-message template. The vLLM server generates the same text with
# openai_harmony; it is hand-assembled here because openai_harmony depends on pydantic 2, and
# installing it into envs/appworld/venv would displace the pydantic 1.10.26 that appworld
# needs (tested: importing it directly breaks). The hand-assembled version has been verified
# byte-for-byte against the official renderer (2026-08-06, 813 characters / 174 tokens, exact
# match).
HARMONY_SYSTEM = (
    "You are ChatGPT, a large language model trained by OpenAI.\n"
    "Knowledge cutoff: 2024-06\n"
    "Current date: {date}\n"
    "\n"
    "Reasoning: {effort}\n"
    "\n"
    "# Valid channels: analysis, commentary, final. "
    "Channel must be included for every message."
)

# The header of one harmony message: <|channel|>channel [to=recipient] [<|constrain|>type] <|message|>
HARMONY_HEAD = re.compile(
    r"<\|channel\|>(?P<channel>[^\s<]+)"
    r"(?:\s+to=(?P<recipient>[^\s<]+))?"
    r"(?:\s*<\|constrain\|>(?P<ctype>[^\s<]+))?"
    r"\s*<\|message\|>")


class Chat:
    """Default (api='raw') goes through /v1/completions; the Qwen chat template is assembled by
    hand (explicit <think> opening), and the raw output is cut by hand at </think> -- the
    thinking segment never goes through the server-side parser, so nothing is lost.
    api='chat' goes through /v1/chat/completions; the thinking is taken from message.reasoning
    -- used for gpt-oss (harmony format, server-side openai_gptoss parser); reasoning_effort
    takes effect only in this mode.
    api='harmony' also goes through /v1/completions, but the harmony prompt is assembled by
    hand and the raw output is cut by hand along channels (skip_special_tokens=False +
    return_token_ids=True) -- the server-side HarmonyParser plays no part at all, so segments
    that fall into the IGNORE tier are not silently dropped, and the generated token ids are
    stored into the trajectory as-is. The date is pinned by the client, so the prefix stays the
    same across reruns on a different day. Past assistant turns only backfill content (matching
    the official template: thinking does not go back into context).
    temperature must be passed by the caller; its value comes from the preset's client section
    (merged by settings_from_args; the default preset default = temperature 1.0) -- the preset
    is this key's only source.
    """

    def __init__(self, base_url, model, temperature, max_tokens=8192,
                 api="raw", reasoning_effort=None, start_date="2026-08-06",
                 top_p=None, seed=None):
        self.client = OpenAI(base_url=base_url, api_key="EMPTY", timeout=600)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api = api
        self.reasoning_effort = reasoning_effort
        self.start_date = start_date
        # top_p/seed default to None = do not go into the request body, so behavior is byte-for-byte
        # identical to before these parameters were added; they are only sent when the preset or the
        # caller gives them explicitly (the sampling convention for temperature>0 needs seed to be
        # reproducible)
        self.top_p = top_p
        self.seed = seed

    def settings(self):
        """This collection run's generation settings, for the trajectory meta -- without this, there
        is no way to later tell which settings a batch of trajectories was run with (before
        2026-08-20, trajectory meta held only model)."""
        return {"api": self.api, "model": self.model,
                "temperature": self.temperature, "top_p": self.top_p,
                "max_tokens": self.max_tokens, "seed": self.seed,
                "reasoning_effort": self.reasoning_effort,
                "start_date": self.start_date if self.api == "harmony" else None}

    def _sample_extras(self):
        """top_p/seed only go into the request body when given explicitly."""
        d = {}
        if self.top_p is not None:
            d["top_p"] = self.top_p
        if self.seed is not None:
            d["seed"] = self.seed
        return d

    @staticmethod
    def build_prompt(messages):
        parts = []
        for m in messages:
            parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n<think>\n")
        return "".join(parts)

    def build_harmony_prompt(self, messages):
        """The leading system message goes into developer per the official convention; the rest is
        carried over as-is. The tail leaves a bare <|start|>assistant, with the channel left
        for the model to choose.
        """
        parts = []
        rest = list(messages)
        instructions = None
        if rest and rest[0]["role"] in ("system", "developer"):
            instructions = rest[0]["content"]
            rest = rest[1:]
        parts.append("<|start|>system<|message|>" + HARMONY_SYSTEM.format(
            date=self.start_date,
            effort=self.reasoning_effort or "medium") + "<|end|>")
        if instructions is not None:
            parts.append("<|start|>developer<|message|># Instructions\n\n"
                         + instructions + "<|end|>")
        for m in rest:
            if m["role"] == "assistant":
                parts.append("<|start|>assistant<|channel|>final<|message|>"
                             + m["content"] + "<|end|>")
            else:
                parts.append(f"<|start|>{m['role']}<|message|>"
                             + m["content"] + "<|end|>")
        parts.append("<|start|>assistant")
        return "".join(parts)

    @staticmethod
    def split_harmony(raw):
        """Cut the raw output carrying special tokens into segments by channel. No segment is dropped
        -- one whose channel is unrecognized still goes into segments, just not into
        reasoning/content.
        """
        segs = []
        pos = 0
        # generation continues right after <|start|>assistant, so the first segment's head is <|channel|>
        while True:
            m = HARMONY_HEAD.search(raw, pos)
            if not m:
                break
            body_start = m.end()
            end = len(raw)
            end_tok = ""
            for tok in ("<|end|>", "<|return|>", "<|call|>"):
                i = raw.find(tok, body_start)
                if i != -1 and i < end:
                    end, end_tok = i, tok
            segs.append({"channel": m.group("channel"),
                         "recipient": m.group("recipient"),
                         "constrain": m.group("ctype"),
                         "text": raw[body_start:end],
                         "closed_by": end_tok})
            pos = end + len(end_tok) if end_tok else end
            if not end_tok:
                break
        reasoning = "\n".join(s["text"] for s in segs
                              if s["channel"] == "analysis")
        content = "\n".join(s["text"] for s in segs
                            if s["channel"] == "final"
                            or (s["channel"] == "commentary"
                                and not s["recipient"]))
        return segs, reasoning, content

    def __call__(self, messages, tries=4):
        """A server-side 500 takes the whole shard down with it -- gpt-oss's harmony parser throws
        'unexpected tokens remaining in message header' when the thinking runs especially long.
        Back off and retry; only raise once retries are exhausted and it still fails, leaving
        it to the caller to decide whether to drop the trajectory or drop the whole batch.
        """
        last = None
        for i in range(tries):
            try:
                return self._once(messages)
            except Exception as e:  # connection errors / 5xx / parse failures all get retried
                last = e
                if i < tries - 1:
                    time.sleep(2 ** i)
        raise last

    def _once(self, messages):
        if self.api == "chat":
            return self._chat(messages)
        if self.api == "harmony":
            return self._harmony(messages)
        t0 = time.time()
        r = self.client.completions.create(
            model=self.model, prompt=self.build_prompt(messages),
            temperature=self.temperature, max_tokens=self.max_tokens,
            stop=["<|im_end|>"], **self._sample_extras())
        raw = r.choices[0].text
        reasoning, sep, content = raw.partition("</think>")
        if not sep:  # thinking truncated for being too long: count it all as thinking, with empty content
            reasoning, content = raw, ""
        return {
            "reasoning": reasoning.strip("\n"),
            "content": content.strip(),
            "raw": raw,
            "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens},
            "wall_s": round(time.time() - t0, 2),
        }

    def _chat(self, messages):
        t0 = time.time()
        # return_token_ids (2026-08-18 ident3): vLLM hands back the prompt and generated token ids
        # together (openai client extra=allow, the fields stay on choice/response); this only stores
        # two extra fields and changes no behavior -- the three-arm token-by-token comparison needs it
        extra = {"return_token_ids": True}
        if self.reasoning_effort:
            extra["reasoning_effort"] = self.reasoning_effort
        r = self.client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
            extra_body=extra, **self._sample_extras())
        ch = r.choices[0]
        m = ch.message
        reasoning = (getattr(m, "reasoning", None)
                     or getattr(m, "reasoning_content", None) or "")
        content = m.content or ""
        return {
            "reasoning": reasoning,
            "content": content,
            "raw": None,
            "out_token_ids": getattr(ch, "token_ids", None),
            "prompt_token_ids": getattr(r, "prompt_token_ids", None),
            "finish_reason": ch.finish_reason,
            "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens},
            "wall_s": round(time.time() - t0, 2),
        }

    def _harmony(self, messages):
        """Skip the openai client -- its response model does not recognize the token_ids /
        prompt_token_ids that vLLM adds; go through stdlib and receive the JSON directly, so no
        field is dropped.
        """
        t0 = time.time()
        prompt = self.build_harmony_prompt(messages)
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "add_special_tokens": False,   # the harmony string already carries <|start|>, don't add another
            "skip_special_tokens": False,  # default True would strip out the channel markers
            "return_token_ids": True,      # the server hands back the actually generated ids
            **self._sample_extras(),
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer EMPTY"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            r = json.loads(resp.read())
        ch = r["choices"][0]
        raw = ch["text"]
        segs, reasoning, content = self.split_harmony(raw)
        return {
            "reasoning": reasoning,
            "content": content,
            "raw": raw,
            "segments": segs,
            "prompt_text": prompt,
            "out_token_ids": ch.get("token_ids"),
            "prompt_token_ids": ch.get("prompt_token_ids"),
            "finish_reason": ch.get("finish_reason"),
            "stop_reason": ch.get("stop_reason"),
            "usage": {"in": r["usage"]["prompt_tokens"],
                      "out": r["usage"]["completion_tokens"]},
            "wall_s": round(time.time() - t0, 2),
        }


DEFAULT_PRESET = "default"


def settings_from_args(args, fallbacks=None):
    """Settings merge shared by the four collectors. --preset points at
    configs/presets/<name>.json. Three priority tiers: an explicit command-line value > a
    non-null value in the preset's client section > the original default. Returns a dict
    holding base_url, model, the preset name, and all of Chat's generation parameters.
    --preset defaults to DEFAULT_PRESET, so every collection run lands on a named preset;
    temperature's only source is the preset's client section, attached on the cli side when
    merging.
    When the preset carries a server section, --base-url/--model can be omitted: the endpoint
    is assembled from host:port, and the model name is taken from served_model_name.
    """
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from preset_loader import (load_preset, merge_client, base_url_of,
                               require_temperature)
    pre = load_preset(getattr(args, "preset", None) or DEFAULT_PRESET)
    fb = {"api": "raw", "reasoning_effort": None,
          "top_p": None, "max_tokens": 8192, "seed": None,
          "start_date": "2026-08-06"}
    fb.update(fallbacks or {})
    # seed is deliberately left out of this tuple (the ruling from the 2026-08-21 multi-sample
    # rework): run_tau2.py:879's --seed is the tau2 environment / user-simulator seed, defaulting
    # to the non-None constant rules.SEED; merging it in through cli would stuff seed into the
    # request body and the trajectory meta's gen_settings, immediately changing outputs under the
    # old convention. The seed written in the preset's client section already takes effect through
    # the fallbacks path (fb has a "seed" key), and multi-sample collection's per-trajectory seed
    # is set directly by run_appworld.py overwriting eff["seed"] -- neither path needs --seed
    # recognized here.
    # temperature does go into this tuple: collectors' temperature comes entirely from the
    # preset's client section (the cli side gets None, and the preset value lands on merge);
    # whenever a --temperature flag is added, an explicit value will beat the preset under the
    # same priority order.
    cli = {k: getattr(args, k, None)
           for k in ("api", "reasoning_effort", "start_date", "temperature")}
    eff = merge_client(cli, pre.get("client"), fb)
    eff["temperature"] = require_temperature(eff["temperature"], pre["_name"])
    srv = pre.get("server") or {}
    eff["model"] = getattr(args, "model", None) or srv.get("served_model_name")
    eff["base_url"] = getattr(args, "base_url", None) or base_url_of(pre)
    eff["preset"] = pre["_name"]
    for need in ("base_url", "model"):
        if not eff[need]:
            raise SystemExit(f"missing --{need.replace('_', '-')}"
                             " (required when the preset has no server section)")
    return eff


def chat_of(eff):
    """The result of settings_from_args -> Chat."""
    return Chat(eff["base_url"], eff["model"], api=eff["api"],
                temperature=eff["temperature"], max_tokens=eff["max_tokens"],
                reasoning_effort=eff["reasoning_effort"],
                start_date=eff["start_date"],
                top_p=eff["top_p"], seed=eff["seed"])


class TrajLog:
    def __init__(self, path, meta):
        self.f = open(path, "w")
        self.w({"type": "meta", **meta})

    def w(self, rec):
        self.f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()
