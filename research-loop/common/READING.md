# Reading discipline: how every role reads files and ledgers

<!-- Source: 09 L21 (the reading sentences the design document gives; 06 L270 says the same). Every role SKILL.md has a reading section that points here instead of restating this. -->

Before opening any file, decide which question the read has to answer, then pick the smallest read that answers it. Every character read in stays in the context and crowds out the judgment that comes later, so the size of a read is a cost, not a detail.

- Large files are never read whole. Read the section that answers the question.
- Sampling an experiment's output means pulling a few records and looking at their textual shape, not loading the output.
- Logs are located with `grep` and with their head and tail, not read top to bottom.
- Ledgers are read only through the `rl` query commands (the seven query kinds `show`, `list`, `trace`, `status`, `inbox`, `stale`, `doctor`, 05 L100), only for the part you need, and at the latest version by default. Files under `loop/` are never opened directly.
- `rl inbox` and `rl decision stale` list only what concerns the orders this session holds, never the whole store.
- Be especially wary of reads that pollute the context heavily.
