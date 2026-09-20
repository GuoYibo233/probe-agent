# 26 The --attach-only path runs neither check of 7.1's check table

Status: needs-triage
Severity: minor
File: models/agent_models/service.py:197-207
Contract: 7.1 ("Then it runs the check table before reporting healthy": health, model, render equals server)
Errata: not recorded (errata "7.1 (`--attach-only`) / 7.4" narrows what `_attach` may compare over `GET /v1/models` to the served model name and `max_model_len`; it says nothing about the check table, and errata "7.1 (the agent service's health row)" only rewords the health row's deadline)

## Finding

`serve()` has two exits. The attach exit writes the endpoint file and returns:

```python
197     if args.attach_only:
198         if not args.attached_to:
199             raise SystemExit(...)
202         _attach(base_url, row)
203         _write_endpoint_file(
204             endpoint_path, replica=args.replica, base_url=base_url, host=host, port=args.port,
205             pid=None, flags=vars(args), claims=claims, attached_to=args.attached_to,
206         )
207         return
```

The start exit runs the contract's three rows:

```python
215         _wait_healthy(root_url, proc)
216         _check_model(base_url, row)
217         _check_render(base_url, row, m, cfg)
```

`_attach` asks `GET /v1/models` and compares `id` and `max_model_len`
(`:128-131`), which covers the health row and the model row. The render row —
"for one fixture conversation, `gptoss.render_ids(messages, effort, date)`
computed in this venv equals the `prompt_token_ids` the chat endpoint returns"
— is never run for an attaching piece.

Skipping it is probably right and not merely missing: the attached server was
started by another run with that run's `VLLM_SYSTEM_START_DATE`
(`:74`), while `_check_render` renders with **this** run's
`cfg.generation.date`, so a second run whose `generation.date` differs from the
server owner's would be refused by a check whose subject (the chat endpoint's
own rendering) no loop ever uses — the loop's prompts are token ids the probe
service rendered (`agent/run_tasks.py:97`, contracts 7.3 item 1). The contract
sentence and the code cannot both stand, and nothing records which one the
build chose.

## Failure scenario

Two readings, both live today:

1. Read the contract as written and the code is incomplete: an attaching run
   never proves that its rendering agrees with the server it will drive, for any
   fixture at all, while the run that started the same server did.
   `jobs/launch.py:770-801` compares the whole frozen `result:` block through
   `claims`, so the gap is narrow but real — it is exactly the 2026-08-18
   jinja-path divergence the render row exists for.
2. Read the code as right and the contract's "Then it runs the check table" is
   false of the attach branch, so the next reader of 7.1 (a second agent family's
   author, per `README.md:382-389`) implements the check table on both branches
   and every attach with a non-matching `generation.date` is refused — a
   `launch_failed` on the run that was supposed to be the cheap one, because
   attaching exists precisely to avoid a second 120B server.

## Proposed fix

Record the decision rather than leave the two readings open. In
`.scratch/from-zero/contract-errata.md`, under 7.1, state what the build does
and why: `--attach-only` runs the health and model rows through `_attach`'s
`GET /v1/models` comparison and does not run the render row, because the chat
endpoint's rendering on an attached server carries the owning run's
`VLLM_SYSTEM_START_DATE` while the loop's prompt ids come from the probe
service's `/render` (7.2, 7.3), so a render comparison there would refuse every
attach whose `generation.date` differs from the server owner's without saying
anything about the ids the attaching run will send. Add the same sentence as a
comment above `models/agent_models/service.py:197`, where the branch is taken,
so the omission reads as a decision instead of an oversight.
