# Mission: vLLM (server-side inference)

## Why

Every piece of experiment data in new1 comes out of a vLLM service: trajectory collection, injection continuation, live runs.
Get one flag wrong on the server side and the settings for the whole batch of data change, quietly, with no error, just different numbers.
Right now that judgment call always goes through asking Claude. The goal is for gyb to be able to look at a command line and a startup log himself and know this service's settings: whether they can be trusted, and which knob the next batch of experiments should change.

## Success looks like

- Look at a `vllm serve` command line plus its startup log and be able to state the per-request context limit, the KV pool capacity, the actual concurrency limit, and which parser got attached automatically, without checking the docs or asking anyone.
- When the next batch of experiments switches model or environment, be able to judge on his own which vLLM features are worth using and which are traps (prefix caching, structured output, logprobs, quantization formats, tool-call parsing).
- When writing the paper's methods and appendix, be able to state accurately how server-side configuration affects the settings results were produced under (token accounting, concurrency, context length, why results across batches are not comparable).
- Stop treating the vLLM-adjacent code in `pipeline/inject/` as a black box: closing the decode mid-stream, rebuilding the harmony prefix, `skip_special_tokens=False`, each one now maps to a specific server behavior.

## Constraints

- The course material lives in `new1/learn/vllm/`, checked into git, versioned alongside the code.
- Every number in every lesson must come from this repo's code, the vLLM 0.26.0 source installed on this machine, or our own servers' logs. No invented examples, no unverified knowledge of parameters.
- Taught in Chinese. Rules follow the `humanizer-gyb` skill: plain words first, facts and interpretation separated with facts first, every number carries what it refers to and where it came from.
- One lesson at a time, short.

## Out of scope

- The training side (the probe four-format training code): that is a separate line of work, not taught here.
- vLLM's CUDA kernels and scheduler internals, unless some experiment result forces us to look inside.
- Deployment operations (Kubernetes, multi-machine clusters, autoscaling): we only have four machines, started and stopped by hand.
