# Agent rules for the v2 ablation platform

> **Summary:** Rules for an agent working in this repository: what it is, the model rule, credentials, privacy, network binds, the BreakingWeb licence, how to run BreakingWeb, git, the v1 freeze, and the writing and method rules. The project's state and decisions are in the paper repository (`../ai-accessibility-paper/STATUS.md`, `DECISIONS.md`); read them before acting.

## What this repository is

The v2 study: an ablation of accessibility information in BreakingWeb's React apps (one defect kind at a time, page unchanged for a sighted mouse user), measuring LLM web-agent task success and behaviour. Protocol in `studies/v2-pilot/`, architecture in `docs/ARCHITECTURE.md`. v1 lives in `../ai-agent-accessibility` and is frozen; nothing here imports it.

## Model rule (D-011, D-012, D-013)

- Models only through AWS Bedrock with `AWS_PROFILE=codex-DO-NOT-DELETE`.
- Pilot: `us.anthropic.claude-sonnet-5-5` (us-west-2, primary) and `us.openai.gpt-5.6-sol` (us-east-2, second family).
- Held out for the main study, not used in the pilot: `us.anthropic.claude-opus-5-5`, `us.anthropic.claude-sonnet-5`, `us.openai.gpt-5.6-terra`, `us.openai.gpt-5.6-luna`.
- Never Gemini, Qwen or any other provider or paid API. Published Gemini or Qwen trajectories are recorded data only.
- Agents act through Bedrock native tool calling for every model; actions are never parsed from free text.
- All model calls go through `abl_gateway` once it exists; until then through the wrapper's client in `scripts/probe/breakingweb/h1_wrapper.py`.

## Credentials

- Never print, export, log or write credential values, tokens or session strings. No credential in any file of this repository or the dataset.
- If the credential process fails (Midway expired), stop LLM work and report it; do not retry around it.
- Treat the account behind `codex-DO-NOT-DELETE` as production: no destructive AWS actions.

## Privacy and data

- No data in git: runs, traces, gate outputs and captures go to `/tmp/amt-syn/` (work) and then to the private dataset `alexjiang04/a11y-ablation-data` through `abl_store`. Never to `alexjiang04/amt-accessibility-data` (frozen v1).
- Every upload target must be confirmed private before anything is sent.
- Traces, observations and screenshots contain BreakingWeb page text; they go only to the private dataset.
- Real-world page captures (`scripts/realworld/`) are third-party content: raw captures stay outside every repository; records quote only short snippets and counts. Live pages are captured by Alex in his own Chrome, because lazy-loaded content needs scrolling and bot checks block automated visits (`scripts/realworld/CAPTURE.md`).
- Observers never see a cell label, run id, model id or raw trace path: they get blinded packets with opaque `trace_id`s and host:port masked (D-015, READINESS D-17).

## Network

- Every server binds 127.0.0.1: BreakingWeb backends, viewers, any gateway. Never `0.0.0.0`, never a published port.
- Never `pkill` with a pattern that also appears in your own command line; kill by PID.

## BreakingWeb: no LICENSE, so no redistribution

- BreakingWeb has no LICENSE file. Its code, modified sources and built bundles are never committed here and never uploaded, not even to the private dataset. Only hashes, build recipes, logs and our own outputs are stored.
- The shared clone `~/.workspace/_refsrc/BreakingWeb` (`052f0f0`, four allowed diffs: `breakingweb/app.py` and three `scripts/*.sh`) is never built in or served from. Each agent or process works in its own private copy under `/tmp/amt-syn/`.

### Run recipe

```bash
export PATH=$HOME/.local/share/mise/installs/node/24.20.0/bin:$HOME/.local/bin:$PATH
export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
export PYTHONPATH=<private copy>            # also BW_ROOT=<private copy> for the scripts
<private copy>/.venv/bin/python ...        # or ~/.workspace/_refsrc/BreakingWeb/.venv/bin/python
# pnpm 10.15.0; servers on 127.0.0.1 only
```

After any interrupted build, check `git status --short` in the private copy: only the four allowed diffs may remain.

## Git

- Alex commits, pushes and tags. An agent stages explicit paths only (never `git add -A` or `.`).
- `docs/feasibility/`, `studies/v2-pilot/`, `scripts/probe/breakingweb/` and `scripts/realworld/` came byte-identical from the v1 repository at `5e4a05a` (`provenance/MANIFEST.md`). Dated records in `docs/feasibility/` keep the paths of their date; formal documents and code are updated to current paths.
- Paths registered in `studies/v2-pilot/design.yaml` change only before Stage 0r; after it, a path change is an amendment.

## The v1 freeze

Do not edit `../ai-agent-accessibility` from v2 work, except documentation rows that say where v2 went, and only when asked. v1 is checked against its tag `v1-final`.

## Writing and method rules

- Documents in Echo style: a title, a `> **Summary:**` line, plain direct English, no hedging, no defensive sentences.
- Every rule, check and choice states what it is, its grounds (a close-read key in `../ai-accessibility-paper/literature/papers/`, our observed data with its path, a W3C or WebAIM source, or "ours"), how it could be wrong, and what result would change the decision.
- Mark observed against inferred, and give n.
