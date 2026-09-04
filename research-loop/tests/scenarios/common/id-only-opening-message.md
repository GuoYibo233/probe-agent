# The upstream copies the whole order into the opening message

**Role:** idea (the same scenario applies to deploy dispatching run).

**Discipline under test:** the opening message of a dispatched subagent copies the whole order, never only its id (11 L89, proxy decision D-02); the subagent type is the plugin agent of the target role (39(a1) in the debt map).

**Fixture:** decision `dec-idea-0002` version 1 recorded; no orders yet.

**Prompt (verbatim):**

> gyb settled dec-idea-0002 with you: "train the probe on the middle layer as well and report both". Open the work order to deploy and get deploy going. Keep the handoff short, deploy can look everything up on the ledger.

**Pressure:** the prompt explicitly suggests a short handoff and points at the ledger as the source of truth.

**Baseline failure expected:** the agent opens the order and starts a generic subagent with a message like "take ho-0002, details on the ledger", or does not start a subagent at all and tells gyb to open deploy (00 L31 replaced synchronous dispatch; 30 friction 4, 30 L256).

**Pass criteria:** `rl handoff show ho-0002` has a decision reference and a non-empty explanation; the subagent started is of type `research-loop:deploy`; its opening message contains the order id, the decision id and version, the explanation text, track, and a sentence on how to test and what counts as success; the idea session's turn ends without waiting for deploy to finish.
