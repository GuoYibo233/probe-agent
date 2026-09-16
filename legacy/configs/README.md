# configs/ -- the single source of truth for generation settings

This directory manages generation settings (model addresses, vLLM launch args,
sampling params); `pipeline/configs/` manages data batches (which trajectories,
how they are split) -- do not mix the two up.

Two things live here:

- `models.json`: the single mapping of model addresses. `model_registry.py`
  reads from here, and scripts always take the path through `resolve()`,
  never hardcoded.
- `presets/<name>.json`: one file, one set of generation settings. `model` is
  an alias from models.json; the `server` block is vLLM launch args (`serve_preset.py`
  consumes it; launching goes through `run.py show serve-preset`); the `client`
  block is sampling params (api / reasoning_effort / temperature / top_p / max_tokens /
  stop / start_date / seed, consumed by the `--preset` flag of the collector, the
  live run, and replay; the BFCL handler takes it through the environment variable
  `NEW1_PRESET_JSON`). A null in the block means unspecified, falling back to
  the caller's own existing default. temperature comes only from the client
  block; when a preset writes it as null, the generation entry point stops on
  the spot through `require_temperature` and names which preset it was (except
  the BFCL handler, which uses BFCL's own built-in setting when it is null).

The range each of the client block's eight keys is taken from, across the four
entry points (aligned 2026-08-21; before this, top_p/seed were taken only by
the collection line, silently unreachable from the live run / replay / BFCL,
now pinned down by TestSamplingForwarding and TestBfclHandlerPreset in
`tests/test_preset.py`):

| key | collection line (4 collectors) | BFCL | live run | replay |
|---|---|---|---|---|
| temperature / top_p / max_tokens / seed | taken | taken | taken | taken |
| reasoning_effort | taken (chat/harmony basis) | taken | taken | not used (effort is fixed in the replayed prefix) |
| stop | not taken (raw is fixed to `<\|im_end\|>`, chat/harmony do not pass it) | not taken | taken | taken |
| api / start_date | taken | not taken | not taken | not taken |

Whenever a new sampling key is added, four places move together: the CLIENT_KEYS
in `preset_loader.py`, the fallback in `envs/collect/common.py`'s
settings_from_args, the PRESET_FB in the live run and replay, and the BFCL
handler's preset-reading block; `tests/test_preset.py`'s SAMPLING_KEYS expands
along with them (a missing-key fallback in the live run / replay will fail red;
the other two spots are watched by the value assertions in
TestCollectorSettings and TestBfclHandlerPreset).

Three rules:

1. An argument given explicitly on the command line always overrides the
   preset value (the merge logic lives in `preset_loader.py`).
2. Adding a new set of settings = adding one json file. After adding one, run
   `python3 run.py selfcheck` (checks alias resolution and field types) and
   `python3 -m unittest tests.test_preset`.
3. A run that used a preset carries the preset name in its run_id (DATA.md's
   checklist, item 9).

Three presets currently exist, their values pinned by `tests/test_preset.py`:

- `default` is the one setting in service across the whole line; every entry
  point's `--preset` defaults to it. client block: api harmony / effort high /
  temperature 1.0 / top_p 1.0 / max_tokens 8192 / stop null / start_date
  2026-08-06 / seed null; server block: tokyo108:8103, gpt-oss-120b, VRAM
  fraction 0.92 (`serve_preset.py` launches it directly).
- `gptoss_default` is OpenAI's own recommended setting (temperature=1.0 /
  top_p=1.0 / top_k=0 / min_p=0.0 / effort medium / context 131072; the source
  and the comparison are written in its desc).
- `gptoss_bfcl_high` is the BFCL line's setting (api chat / effort high /
  max_tokens 16384; temperature is left null, the BFCL handler uses its own
  setting; no server block). When the BFCL handler has no `NEW1_PRESET_JSON`
  set, it reads `default`, taking max_tokens 8192 / top_p 1.0 / temperature
  1.0; when pointed at `gptoss_bfcl_high`, it takes max_tokens 16384, with
  temperature from BFCL's own setting.

Do not hand-edit a preset to "tweak parameters while you're at it" -- open a new
preset for that, with a name that states the setting clearly. For sweeping a
group of parameters, no need to hand-open N presets: `python3 run.py
preset-sweep --base <name> --grid key=value,value,...` (multiple --grid flags
take the cartesian product) generates a whole grid of presets in one command,
named `<base>__<key><value>...`, which is itself the setting; commit right
after generating them, then launch point by point.
