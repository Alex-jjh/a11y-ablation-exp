# v2 ablation platform: architecture of the code and data

> **Summary:** How the v2 platform is split: six packages with one job each (built environments, gates, the AWS gateway, the run engine, traces and observer notes, the store), joined only by JSON Schemas in `schemas/` and one Python interface (`converse()`); a disposable machine whose evidence lives in a private Hugging Face dataset as packed, checksummed, versioned snapshots; and where the copied v1 folders came from. It follows option C of the platform-split proposal (`docs/2026-11-02-platform-split-proposal.md` in the v1 repository) and Echo's `echo-ai-exp/docs/ARCHITECTURE.md`. As of 2026-11-02 the packages are skeletons; the code is still in `scripts/probe/breakingweb/` as run.

## 1. Principles

- **The machine is a cache.** `/tmp/amt-syn` and the DevSpace can be destroyed. Code and documents live in git; evidence lives in the private dataset `alexjiang04/a11y-ablation-data`. Grounds: proposal F6 (about 20,000 evidence files existed only in `/tmp`).
- **One job per package.** Each package has one reason to change and a list of what it must not know about (section 2). Grounds: proposal F5 (scripts import each other through `sys.path` and call `/tmp` paths). How it could be wrong: over-built for one pilot. Mitigation: packages are filled only from code that already exists, in Stage 0.
- **Contracts are files.** Packages exchange JSON that matches `schemas/`; none reads another's internals. Grounds: proposal F10 (a committed artefact differed from what its script wrote, with no record).
- **Immutable, versioned artefacts.** A trace, a gate result, a run and an observer note are written once with a manifest (file list, sha256, producing code). Nothing downstream edits upstream. Observer output is a separate artefact, never written into the trace (D-015).
- **The model rule is code, not convention.** Only `abl_gateway` touches AWS, and it refuses any model id outside the allowlist (D-011, D-012).
- **No BreakingWeb code leaves the machine.** BreakingWeb has no LICENSE. Bundles and sources are rebuilt from `052f0f0` and recorded by hash (`studies/v2-pilot/DESIGN.md` §3: the `none` rebuild is byte-identical to clean).

## 2. Packages

| Package | Job | Depends on | Must not know about |
|---|---|---|---|
| [`abl_envs`](../abl_envs/README.md) | (env, kind, codemod hash) to a served build with a path-free content hash, on a private copy, on 127.0.0.1; restore afterwards | Node 24, pnpm 10.15.0, BreakingWeb clone | models, AWS, HF |
| [`abl_gates`](../abl_gates/README.md) | judge a variant against clean: look, function, replay, observation footprint, on-path dose | `abl_envs`, `schemas/` | models, AWS |
| [`abl_gateway`](../abl_gateway/README.md) | `converse()` under the model rule, with tool use, reasoning capture, error kinds and a fake | boto3, profile `codex-DO-NOT-DELETE` | harnesses, cells, HF |
| [`abl_run`](../abl_run/README.md) | design + bundles to cells to episodes, resumable; harness adapters `h1` and `bu` | `abl_envs`, `abl_gateway` interface, `abl_traces`, `schemas/` | boto3, HF |
| [`abl_traces`](../abl_traces/README.md) | immutable traces, segments, blinded packets, observer job and quote check, observer notes | `schemas/`, `abl_gateway` interface | where data is stored, the cell behind a `trace_id` |
| [`abl_store`](../abl_store/README.md) | pack, manifest, push and pull to the private dataset | zstandard, huggingface_hub | the meaning of any schema |

Later: `abl_census` (real-world prevalence of each defect kind, same detection rule as the codemod), from `scripts/realworld/`; and a WebArena adapter in `abl_envs` (a new HTML-level injector; v1 operators read at a pinned commit, never imported).

Study-specific material stays in `studies/<study>/`: task selection, cost and precision planning, the registered `design.yaml`, the codebook and observer prompt.

## 3. Data contracts

| Artefact | Schema | Made by | Stored in |
|---|---|---|---|
| bundle manifest | [`bundle_manifest`](../schemas/bundle_manifest.schema.json) | `abl_envs` | series `bundles-<codemod8>` (hashes and build logs only) |
| gate result | written in Stage 0 from the `docs/feasibility/2026-10-30-*.json` shapes | `abl_gates` | with the gate run's snapshot |
| cell | [`cell`](../schemas/cell.schema.json) | `abl_run` from `design.yaml` | rebuilt on demand; its sha256 is in the run manifest |
| run manifest | [`run_manifest`](../schemas/run_manifest.schema.json) | `abl_run` | `pilot-<run_id>` |
| episode (trace) and step | [`episode`](../schemas/episode.schema.json), [`step`](../schemas/step.schema.json) | `abl_traces` | `pilot-<run_id>` segments |
| observer note | [`observer_note`](../schemas/observer_note.schema.json); its `coding` follows `studies/v2-pilot/trace_observer_prompt.md` §3.2/§3.3 | `abl_traces` | `observer-<run_id>-<observer>` |
| snapshot manifest | [`snapshot_manifest`](../schemas/snapshot_manifest.schema.json) (Echo format `echo-data/1`) | `abl_store` | next to its shards |

The schemas are drafts (`/0`). They are frozen at Stage 0, together with the codemod and wrapper hashes. The episode and step schemas take their field names from the `trace.json` that `h1_wrapper.py` wrote on 2026-11-02 (`/tmp/amt-syn/traces/`, n = 8 smoke runs), plus three changes the decisions require:

| Change | Grounds | How it could be wrong | What would change it |
|---|---|---|---|
| `response.tool_uses` holds the action; no text parsing | D-013; Sonnet 5.5 wrote tool-call XML on 51% of smoke steps (`docs/feasibility/2026-11-02-wrapper-smoke.md`) | a harness may need a free-text final answer | if a task needs a text answer, it becomes a `send_message` tool, not a parser |
| `reasoning_visibility` with an explicit `none` | proposal F11: GPT-5.6 returns one encrypted block, Sonnet 5.5 can return none on easy steps | a model may return reasoning in a block type not listed | a new block type is added to the enum, never dropped |
| opaque `trace_id` (HMAC of `cell_id` under a per-run salt) and masked host:port in packets | D-015, READINESS B-5 and D-17 (8 of 8 first-use observers saw raw paths) | the observation itself shows the defect (TRACE-CODING §2) | nothing: the guess field measures what blinding cannot hide |
| kinds `names_empty` and `names_fallback` instead of `names` | D-014, READINESS D-12: only the empty-name part is a WCAG failure (F68, SC 4.1.2) | the split may leave a cell with too few on-path tasks | if an env has no N1a control on a strict task path, its `names_empty` cell is dropped for that env and reported |

## 4. Storage, packing and recovery

- **Dataset.** `alexjiang04/a11y-ablation-data`, private (checked before every write). Layout `snapshots/<series>/<version>/MANIFEST.json` plus `shard-NNNNN.tar.zst`; version tags `<series>-<version>`.
- **Series.** `feasibility-2026-10` (uploaded 2026-11-02, `provenance/DATA.md`), `bundles-<codemod8>`, `pilot-<run_id>`, `observer-<run_id>-<observer>`, `census-<date>`.
- **Pack before upload.** Echo measured 5,000 small files at 624.7 s per-file download against 3.8 s packed (`echo-ai-exp/ops/bench_upload.py`, 2026-10-12). The pilot plans 4,718 runs and about 77,000 steps (`studies/v2-pilot/cost.json`), so `abl_traces` closes segments and `abl_store` uploads only closed segments.
- **Shard size.** At most 2 GB. The first snapshot needed one 846 MB shard for 1.8 GB raw.
- **What never goes up.** BreakingWeb clones, sources and bundles; MHTML snapshots of BreakingWeb pages (they embed the built CSS); credentials; the `trace_id` salt in a run's `KEY/` (kept apart from traces); raw real-world captures. Published BreakingWeb trajectories (`~/.hf-stage-bw`) are recorded by file list and sha256 only until their licence is checked (DESIGN §9).
- **Restore.** Download a version and unpack it with `echo_data.unpack` (sha256 checked on write); `abl_store pull` after Stage 0. A bootstrap script (venvs, BreakingWeb at `052f0f0` plus the four allowed diffs, pulls) goes in `ops/` in Stage 0.

## 5. Where things came from

| Here | From | How |
|---|---|---|
| `docs/feasibility/` (67 files), `studies/v2-pilot/` (14), `scripts/probe/breakingweb/` (23), `scripts/realworld/` (21) | `ai-agent-accessibility` at `5e4a05a`, same relative paths | `cp -p` of `git ls-files`; 125 of 125 sha256 equal to the source blobs (`provenance/MANIFEST.md`). The v1 repository keeps its copies; its `docs/archive/crosswalk.md` points here |
| `/tmp/amt-syn` evidence | the feasibility work of 2026-10-29 to 2026-11-02 | packed to series `feasibility-2026-10` v1 (`provenance/DATA.md`) |
| layout and `abl_store` | Echo `echo-ai-exp` at `d96629b` | followed; `echo_data` to be vendored with a provenance file |

The same relative paths keep the 203 relative links of the copied documents resolving (0 broken, checked 2026-11-02) and keep `pilot_plan.py:54` (repository root as `HERE/../../..`) and the paths in `design.yaml` valid. The scripts still name 62 absolute paths in the v1 repository or `/tmp/amt-syn`; they change when the code moves into packages.

## 6. Stage 0 work in this repository (not done)

1. `pyproject.toml` (Python 3.12, uv) and per-package tests.
2. Fill the packages from the scripts named in each package README, with the defect fixes F-1 to F-7 (`studies/v2-pilot/DEFECTS.md`) and the READINESS decisions D-1 to D-17.
3. Update `design.yaml` paths (`codemod.path`, `regenerate`, the H1 wrapper) to package paths before the Stage 0 hashes are taken.
4. Regression tests from existing evidence: codemod plus build on `052f0f0` reproduces the bundle hashes; `ua_delta.py` positive control; `pc_break`; `pilot_plan.py all` regenerates `studies/v2-pilot/` with no diff; `abl_gateway` against its fake (an id outside the allowlist is refused, reasoning blocks kept, `none` recorded when absent).
5. `ops/bootstrap.sh`, a sync of `/tmp/amt-syn` outputs (clone copies excluded), and a restore drill.
