# Teaching working notes

## User preferences (must hold while teaching)

- Taught in Chinese. Rules follow the `humanizer-gyb` skill: plain words first, at most one new term per paragraph,
  confident assertions with no hedging, facts and interpretation separated with facts first, every number carries what it refers to and where it came from.
- **No guessing.** Do not make a judgment call about a number without having read the actual file. If the reason cannot be found, say "could not find it"; do not paper over it with a made-up explanation.
  This is a hard rule from CLAUDE.md, and it holds equally in teaching material.
- Every number in a lesson must be traceable back to the source file by grep (source line number, log file name, repo path).
- No praise. Do not evaluate whether his questions are good or not.

## Workspace conventions

- Lands in `new1/learn/vllm/`, checked into git (user's call, 2026-08-04).
- Lessons and reference cards both link `assets/lesson.css`, quizzes use `assets/quiz.js`. For a new lesson, read `assets/` first before touching anything; do not rewrite the same thing again.
- `build_artifact.py` is already registered in `run.py` (`build-lesson-artifact`) and written into `MAP.md` §3.
  The original position that "course material isn't a program, so it doesn't go in MAP" is void now that this converter exists.

## Publishing workflow (when the user wants an artifact)

```
python3 run.py build-lesson-artifact --lesson learn/vllm/lessons/<lesson page>.html
python3 run.py build-lesson-artifact --lesson <same as above> --check   # confirm it is in sync
# then publish <name>.artifact.html with the Artifact tool
```

- `*.artifact.html` is a rendered artifact; **hand-editing it is void** every time. Edit the lesson page or `assets/`, then rerun the converter.
- Republishing the same lesson must reuse the same file path, or it will not update the same URL.
- The favicon is fixed at 🔎; do not change it unless the whole course changes theme (the user recognizes the tab by the icon).
- **The reference card also needs its own artifact publish**: the `class="local"` links in the lesson page get downgraded to plain text in the published version, so if the card does not have its own URL, it does not exist on the artifact. Use 📇 as the card's favicon to distinguish it from the course's 🔎.
- Published so far:

  | Page | URL |
  |---|---|
  | Lesson 1, startup log | https://claude.ai/code/artifact/893a47d1-3eba-460f-97f9-6f5aeabee6b3 |
  | Lesson 2, prefix caching and token accounting | https://claude.ai/code/artifact/0928d158-fb92-4c16-9ff6-b1902bf37af1 |
  | Lesson 3, stop conditions | https://claude.ai/code/artifact/a8c5d973-bd30-4054-88ae-1ea44aae3801 |
  | Lesson 4, greedy and reproducibility | https://claude.ai/code/artifact/a82f9232-f848-4a19-beac-ff66b1cdcefc |
  | Lesson 5, streaming and abort | https://claude.ai/code/artifact/970aa33c-31c7-4439-9167-4aa5e1f4d3bb |
  | Card, startup log decoder | https://claude.ai/code/artifact/76705f6f-f7e5-4bf4-b794-02fb1c03d13f |
  | Card, token accounting | https://claude.ai/code/artifact/8898e677-f0ac-461e-a47b-2379f1ccc71d |
  | Card, request parameters | https://claude.ai/code/artifact/1f84040b-dd7c-4df4-bda6-bcbb406dd627 |

## Visual rules (set 2026-08-04)

The first version's style was warm beige plus serif plus terracotta red, exactly the look AI-generated design tends to cluster around, and it has been replaced. The current one: a cool gray-blue ground, terminal INFO cyan as the accent, numbers called out in a log marked in amber, right and wrong handled separately in green and red.
Headings sans-serif, body serif, data monospace, three roles kept separate. Chinese text does not embed a font (CJK font files are too large and CSP blocks the CDN), so everything falls back to the system font stack. Both light and dark themes need to be handled; `:root[data-theme=...]` must override `prefers-color-scheme`.
The body background must be written explicitly; the artifact shell injects a light body style.

## Data sources (priority order, high to low, when writing a lesson)

1. `envs/vllm-env/lib/python3.12/site-packages/vllm/`: the actual 0.26.0 source we are running.
2. `/net/tokyo100-10g/data/str01_01/y-guo/vllm_cache/logs/*srv*.log`: our own servers' startup logs.
3. `docs.vllm.ai`: official docs, which describe the latest version; where it disagrees with 0.26.0, the source wins.

## Open items and leads

- **One thing not yet resolved**: both H100s' KV memory is 20.45 GiB, but the number of tokens they hold differs
  (475,669 at a 65,536 limit, 528,934 at a 131,072 limit). Same bytes, different capacity, suspected to be related to how sliding-window layers are chunked, not verified. Already marked honestly as a gap in Lesson 1.
- **Another thing not yet resolved**: `launch_vllm_w0.py:10` says `--max-num-seqs` defaults to 1024, but the 0.26.0 source has 128. Where 1024 came from cannot be found (the Qwen service log from that time has been deleted).
- What `VLLM_USE_FLASHINFER_SAMPLER=0` does has been resolved (envs.py:838-840), but why we turned it off has no record anywhere in this repo.
- **The raw artifacts have already been cleared out**: `$NFS/envs/runs/aw_pathdiag/` is entirely gone, so the per-item `prompt_tokens` for the 08-02 chat collection batch can no longer be retrieved. Lesson 2 can only use the server log's aggregate numbers. To teach per-item numbers in the future, confirm the artifacts still exist first.

## Completed so far

- Lesson 1, startup log (2026-08-04): five for five correct, see `learning-records/0002-*`.
- Lesson 2, prefix caching and token accounting (2026-08-04): covered three prompt lengths,
  that `Avg prompt throughput` only counts the recomputed part, that the hit rate is token-level plus a 1000-request sliding window,
  that `--enable-prompt-tokens-details` defaults off and we have never given it.
  Companion reference card `reference/token-accounting.html`.
- Lesson 3, stop conditions (2026-08-04): two separate stop mechanisms; a stop string matches against the decoded text,
  and that text is controlled by `skip_special_tokens` (default True) -> a stop string made of special tokens fails silently.
  The collection line's raw mode `stop=["<|im_end|>"]` was doing nothing at all, backstopped only by the EOS token.
- Lesson 4, reproducibility (2026-08-04): temperature<1e-5 takes the argmax path, so seed does nothing;
  but `VLLM_BATCH_INVARIANT` defaults off -> results vary with batch composition, so concurrency is a hidden variable.
- Lesson 5, streaming and abort (2026-08-04): a dropped connection really does trigger a server-side abort (async_llm.py:587-594),
  but `enable_log_requests` defaults off and cannot be grepped out of the log; the missing usage on an aborted segment can only be approximated from the chunk count.
  Companion reference card `reference/request-params.html` (serves lessons 3 through 5).

**These five lessons are one complete round:** startup log -> token accounting -> stop conditions -> reproducibility -> streaming and abort, together tracing one request's whole path from being sent to being received back. Adding a lesson means starting a new round, not patching a hole in this one.

## Candidates for the next round (not yet written, ranked by fit with MISSION)

1. Tool calling and the harmony channel: `--tool-call-parser`, how gpt-oss's analysis/commentary/final
   three channels get split apart on the server side, what `think_span()` actually depends on.
2. Scheduling and queuing: `--max-num-seqs`, the two counters Running/Waiting, when preemption
   happens, and how that relates to the concurrency limit from Lesson 1. (This would also settle
   the NOTES mystery about `--max-num-seqs` reading 1024 instead of 128.)
3. Quantization and numerics: exactly which tensors `gpt_oss_mxfp4` quantizes, what the KV cache dtype is,
   and whether it compounds with the numerical jitter from Lesson 4.
