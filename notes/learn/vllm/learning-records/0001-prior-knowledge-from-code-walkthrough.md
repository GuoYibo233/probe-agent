# Starting point: already walked through the vLLM call code and cross-checked it against the official docs

Before the course started on 2026-08-04, gyb had already gone through two passes: one pass over all of this repo's vLLM-related code (the service launch scripts, the collection client, the injection client), and one pass cross-checking those claims against the official docs and the local 0.26.0 source.
So Lesson 1 does not need to cover "what scripts do we have" or "what's the difference between the chat endpoint and the completions endpoint" again; those are already the foundation.

## Evidence

- He actively asked to "cross-check against the official docs," which shows he knows code comments and remembered parameter values can both be wrong and need primary verification.
- This pass found four errors, two of them mine: `--gpu-memory-utilization 0.92` equals 0.26.0's default value;
  `1,475,384 tokens / 22.51x` is the H200's number, not the H100's.

## Implications

- The starting point is set at "can read the launch scripts," so Lesson 1 goes straight into the startup log.
- He accepts the practice of saying plainly "no record found" rather than papering over it (why `VLLM_USE_FLASHINFER_SAMPLER=0`
  is turned off could not be found anywhere in the repo, and it was marked as such). Later lessons should handle unresolved points the same way, without smoothing them over.
- He verifies numbers by hand himself. Every number given in a lesson must be traceable back to source, and he must never be given something he cannot verify.
