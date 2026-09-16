# pipeline/configs/ -- data batch configs

This directory manages data batch configs (one json = one annotate/build-database
setting for an environment x model combination: the trajectory source directory,
the problem-list mode, where output lands, the seed). Tasks like `ann-build` take
these with `--config`. Generation settings (model addresses, vLLM launch args,
sampling params) do not live here -- they live in the repo root's `configs/`
(models.json + presets/); do not put them in the wrong place.
