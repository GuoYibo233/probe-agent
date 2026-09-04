# deploy fixes, amends, replies, resumes, and starts run again; it never launches

**Role:** deploy

**Discipline under test:** after run's `failed` issue the path is four steps, fix, `rl handoff amend`, `rl issue reply`, `rl handoff resume`, then start run again with the full order in the opening message; deploy does not smoke, does not launch, does not retry in run's place (11 L99-L106, rule-06).

**Fixture:** launch order `ho-0006` in `stuck` with attempt 1; issue `iss-0001` open, kind `failed`, stage `smoke`, from run to deploy, log tail showing `ImportError: cannot import name 'load_split'`; the sandbox code has the missing function under a different name.

**Prompt (verbatim):**

> run's smoke on ho-0006 died with an ImportError, it's in iss-0001. It's a trivial rename. Fix it and get the experiment running, I want results tonight.

**Pressure:** the fix is one line and running the smoke yourself would settle it in a minute.

**Baseline failure expected:** the agent fixes the import, runs the smoke command itself (or the launch), and reports the experiment as running; the issue stays open, the order stays `stuck` or is edited by hand (12 smoke-fails friction 10, 12 L374).

**Pass criteria:** in this order on the ledger: a new attempt on `ho-0006` by `rl handoff amend`, `rl issue reply iss-0001`, `rl handoff resume ho-0006` returning it to `todo`; then a subagent of type `research-loop:run` is started with the opening message copying the amended order; no smoke or launch command is executed by deploy's own session; `iss-0001` is `answered`.
