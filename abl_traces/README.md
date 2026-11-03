# abl_traces: traces, packets and observer notes

> **Summary:** Writes each episode once as an immutable trace with every step, reasoning block and tool call; closes traces into upload segments; makes the blinded packet an observer reads (opaque id, host:port masked); runs the observer job and checks its quotes; stores each observer's coding as a separate note. Empty skeleton: the code is still in `scripts/probe/breakingweb/h1_wrapper.py` (`trace.json`, `packet`).

## Single job

Record what the agent did and what an observer said about it, apart. One reason to change: the trace or note format.

## Inputs and outputs

| Direction | What | Contract |
|---|---|---|
| in | step records from `abl_run` | [`step`](../schemas/step.schema.json) |
| out | `trace.json` + `manifest.json` + `SHA256SUMS` per episode | [`episode`](../schemas/episode.schema.json); never edited after it is closed |
| out | segments `records/segment-NNNNNN.jsonl` (closed every 500 records or 10 minutes) | Echo's segment rule (`echo-ai-exp/docs/ARCHITECTURE.md` §4); `abl_store` uploads only closed segments |
| out | blinded packet per trace | `studies/v2-pilot/TRACE-CODING.md` §2: no cell, build, bundle hash, run id, repeat, date or model; host:port masked (D-17); evaluator verdict only in pass B |
| out | observer note per trace, pass and observer | [`observer_note`](../schemas/observer_note.schema.json); its `coding` follows `studies/v2-pilot/trace_observer_prompt.md` §3.2/§3.3 |

## Depends on / must not know about

- Depends on: `schemas/`; the `abl_gateway` interface for the observer's own LLM calls (same allowlist).
- Must not know about: where data is stored, AWS credentials, the cell behind a `trace_id` (the salt stays in the run's `KEY/`).

## Rules (D-015; READINESS B-5, B-6)

- Every trace is coded by observers blind to the condition. Observers get packet paths only, never raw trace paths (the first use leaked them on 8 of 8 traces).
- A coding whose quote is not an exact substring of the named packet field is rejected and re-requested once, then set to `na` with reason `evidence_invalid`.
- Notes are saved with the trace sha256 and the packet sha256, never written into the trace.
- Coding scope and observers: every H1 trace; O1 and O2 as decided under READINESS D-9.
