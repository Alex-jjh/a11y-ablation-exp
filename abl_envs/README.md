# abl_envs: built environments

> **Summary:** Turns (environment, kind, codemod hash) into a served BreakingWeb build with a known content hash, on a private copy of the clone, served on 127.0.0.1 only, and restores the copy afterwards. Empty skeleton: the code is still in `scripts/probe/breakingweb/` as run.

## Single job

Make and serve the page under test. One reason to change: how a variant is produced or served.

## Inputs and outputs

| Direction | What | Contract |
|---|---|---|
| in | BreakingWeb clone at `052f0f0` with only the four allowed diffs (`breakingweb/app.py`, three `scripts/*.sh`) | checked by `git status --short` before and after every build |
| in | environment id, kind, codemod file | kinds of `studies/v2-pilot/DESIGN.md` §4.1 and `DEFECTS.md`; `names` is built as two kinds, `names_empty` and `names_fallback` (D-014); `landmarks` also converts named `section` and strips names from `form` (D-014, F-1) |
| out | `bundle_manifest` per build | [`schemas/bundle_manifest.schema.json`](../schemas/bundle_manifest.schema.json): path-free content hash (D-16), file list, codemod sha256, toolchain |
| out | a running backend on `127.0.0.1:<port>` and the private copy restored | port and copy path returned to the caller |

## Depends on / must not know about

- Depends on: Node 24.20.0, pnpm 10.15.0, the BreakingWeb clone, `schemas/`.
- Must not know about: models, AWS, Hugging Face, cells, traces.

## Comes from (Stage 0)

`codemod.py` (with fixes F-1, F-3, F-5, F-6 of `studies/v2-pilot/DEFECTS.md`), the build-and-restore parts of `variant_run.py`, `variant_gate.py`, `click_effect.py` and `replay.py`, `h1_wrapper.py manifest`, `inventory.py`, `batch.sh`. The controls not yet built (`names_tagged`/`names+`, `names50`, `labels~`, machinery shams, `fmt_wrap`, `pos_info`; READINESS B-2) are new kinds here.

## Rules

- Never build in the shared clone `~/.workspace/_refsrc/BreakingWeb`; one private copy per process under `/tmp/amt-syn/`.
- Bind 127.0.0.1 only. A bundle or the clone is never committed or uploaded; only hashes, recipes and build logs.
- The bundle hash does not include the checkout path (READINESS B-4: the old formula refused byte-identical builds).
