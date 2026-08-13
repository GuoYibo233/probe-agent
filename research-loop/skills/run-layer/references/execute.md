# Executing a launch order

`<plugin-root>` means the plugin root, three levels up from this file
(`../../..`).

## Take a job only when a launch order says exactly what to run

This layer never starts something from a verbal description or a half-written plan -- only from a launch order file already on disk, fully specified (`tables/rows.json` → `launch_order`). If what's being asked for isn't a launch order yet, that's a deploy-layer job, not this layer's.

## Execution

Whatever `rails.gpu` resolves to in config runs the order: a skill name means route the launch there, a command/script path means run it directly with the launch order's path as the argument. On a bare project (or during plugin self-test) that resolves to the fallback:

```
python3 <plugin-root>/scripts/fallback/launch.py <launch_order> [--project-root <root>]
```

**A dirty working tree always refuses the launch** -- except paths matching config's `dirty_exempt_globs`. Refusal escalates back to deploy (see `references/failures.md`); it never launches "just this once" against uncommitted code.

## After it lands

Before anything downstream trusts a number from this run, check the artifact:

```
python3 <plugin-root>/scripts/output_check.py --launch-order <launch_order>
```

An exit code of 0 with an empty artifact is not `ok` -- it's `empty-output`, and that distinction is what feeds R8's escalation path, not a judgment call made here.

## Recording

runs.jsonl normal rows go through the project's bookkeeping script (config `record_cmd`), or on a bare project, the fallback:

```
python3 <plugin-root>/scripts/fallback/record.py --launch-order <launch_order> [--status <status>]
```

This is the only path that writes a normal row -- never hand-type a number into runs.jsonl from a log (R7).

## Job-ledger registration

Register the launch and its completion into the job ledger. At minimum this needs the two backrefs and the sampler's verdict -- `launch_order_ref`, `escalation_ref` (pointing at a blocked entry, when one was opened), and the stall/dead/ok verdict with its timestamp (`tables/rows.json` → `jobs_min_additions`; thresholds in config `stall_thresholds`). The rest of the job ledger's fields follow whatever the project already has.

## Zero code write

If running the order surfaces a code problem, this layer does not patch it -- see `references/failures.md` for what happens instead. Fixing code here would be writing outside this layer's authority, no matter how small the fix looks.
