# abl_gates: is a variant the defect and nothing else

> **Summary:** Judges a built variant against clean before any agent runs on it: same look, same function for a mouse user, task still solvable by replay, and what each harness observation loses. No LLM. Empty skeleton: the code is still in `scripts/probe/breakingweb/` as run.

## Single job

Decide, per (env, kind) cell, PASS or FAIL with a reason, and measure the dose on task paths. One reason to change: a gate rule.

## Inputs and outputs

| Direction | What | Contract |
|---|---|---|
| in | clean and variant builds | `bundle_manifest` ([schema](../schemas/bundle_manifest.schema.json)) and a served port from `abl_envs` |
| in | recorded clean trajectories | the published BreakingWeb trajectories, file list and sha256 only in the dataset (`provenance/DATA.md`) |
| out | gate result per cell (look, console, boxes, DOM diff, allowed-diff rule; function equivalence; replay matrix; on-path dose; browser-use footprint) | JSON per gate as in `docs/feasibility/2026-10-30-*.json`; a `gate_result` schema is written in Stage 0 from those files |

## Depends on / must not know about

- Depends on: `abl_envs`, Playwright 1.44 / Chromium 125 in the BreakingWeb venv, `schemas/`.
- Must not know about: models, AWS, Hugging Face.

## Comes from (Stage 0)

`variant_gate.py`, `ua_delta.py`, `click_effect.py`, `click_treated.py`, `replay.py`, `replay_report.py`, `path_replay.py`, `on_path_dose.py`, `variant_check.py`, `browseruse_capture.py`. Known gaps to close: the residual check tests tags, not computed roles (READINESS R-L), and M2a/M2b/M10 have not run on the current codemod (B-3).

## Tests

Their existing known-answer controls become regression tests: `ua_delta.py`'s positive control, the `pc_break` break (106 of 195 tasks fail 3/3), the do-nothing agent (0 of 195 pass).
