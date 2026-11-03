# abl_run: cells to episodes

> **Summary:** Reads a study's `design.yaml`, builds the cell list deterministically, and runs each cell as one episode through a harness adapter (`h1`: BreakingWeb's text agent through the wrapper; `bu`: stock browser-use), resumable, writing through `abl_traces`. Empty skeleton: the code is still in `scripts/probe/breakingweb/` as run.

## Single job

Execute a design. One reason to change: how cells are scheduled or a harness is driven.

## Inputs and outputs

| Direction | What | Contract |
|---|---|---|
| in | `studies/<study>/design.yaml` | the study's registered design |
| in | bundle manifests | [`bundle_manifest`](../schemas/bundle_manifest.schema.json); a run refuses a cell whose served bundle differs from its manifest |
| in | a gateway object | `abl_gateway` interface (`converse()`), never boto3 |
| out | cell list | [`cell`](../schemas/cell.schema.json); its sha256 goes into the run manifest. Each cell gets an opaque `trace_id` from a per-run salt (D-015) |
| out | run manifest | [`run_manifest`](../schemas/run_manifest.schema.json) |
| out | episodes | through `abl_traces` ([`episode`](../schemas/episode.schema.json)) |

## Depends on / must not know about

- Depends on: `abl_envs`, the `abl_gateway` interface, `abl_traces`, `schemas/`.
- Must not know about: boto3, AWS, Hugging Face.

## Comes from (Stage 0)

`h1_wrapper.py run` (H1 adapter), `pipeline_smoke.py` and `browseruse_capture.py` (bu adapter), the `cells` part of `pilot_plan.py`, `h1_budget.py` (per-task step caps, D-6). Task selection, cost and precision (`pilot_plan.py select/cost`, `pilot_precision.py`) are study-specific and stay with the study in `studies/v2-pilot/`.

## Rules

- Backends on 127.0.0.1, one private clone copy and port per concurrent episode.
- An infrastructure failure (a call over 120 s, a credential stop) is rerun, not scored (D-4).
- Untested so far: the 120 s timeout and 8-way concurrency (READINESS B-12).
