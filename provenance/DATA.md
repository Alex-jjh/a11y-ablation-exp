# Data: what is stored off this machine

> **Summary:** v2 evidence lives in the private Hugging Face dataset `alexjiang04/a11y-ablation-data`. The first snapshot, series `feasibility-2026-10` version `v1`, is the feasibility evidence of `/tmp/amt-syn` as of 2026-11-02 05:40 UTC: 23,176 files, 1.80 GB raw, one 846 MB zstd tar shard plus `MANIFEST.json`. It holds gate, function-equivalence, replay, path-replay, browser-use footprint, smoke, H1 wrapper self-test and smoke traces, real-world kit runs and pilot planning outputs. It holds no BreakingWeb clone, source, built bundle or BreakingWeb page snapshot; those 535,682 files were left out by five rules, and the 1,794 source copies and snapshots among them are listed by sha256 only. The upload was checked by listing the dataset and by downloading the shard and verifying its sha256 and all 23,176 file hashes.

## The dataset

| Item | Value |
|---|---|
| Dataset | `alexjiang04/a11y-ablation-data` (repo type dataset, created 2026-11-02) |
| Visibility | private. Checked before upload: `dataset_info(...).private` is `True`, and an anonymous request to `https://huggingface.co/api/datasets/alexjiang04/a11y-ablation-data` returned HTTP 401 (`x-error-message: Invalid username or password.`) |
| Not to be confused with | `alexjiang04/amt-accessibility-data`: the frozen v1 data, checked by the v1 repository's `data/SHA256SUMS`. Nothing v2 goes there |
| Layout | `snapshots/<series>/<version>/MANIFEST.json` plus `shard-NNNNN.tar.zst`, as Echo's `echo_data` (`echo_data/snapshot.py:4-5`) |
| Version tags | Not created. Echo's convention is a tag `<series>-<version>` per snapshot; this workflow's rule forbids tagging. The tag to create is `feasibility-2026-10-v1` at dataset commit `02a42a32d8b27efe8fda5eb4db9d6afe6a735774` |

## Snapshot `feasibility-2026-10/v1`

| Item | Value |
|---|---|
| Dataset commit | `02a42a32d8b27efe8fda5eb4db9d6afe6a735774` |
| Remote path | `snapshots/feasibility-2026-10/v1/` |
| Shard | `shard-00000.tar.zst`, 846,166,792 bytes, sha256 `195827fe4745e88905c14163f6ebba87c9eeccb29e4d1b44fddc034ade277d38`, 23,176 files |
| Manifest | `MANIFEST.json`, 6,515,215 bytes, sha256 `95fbeb3ac1da7b7bd538c6e1f4e1cbb70c076bdd9add0c531cd58390c144e213`, format `echo-data/1` |
| Raw size | 1,802,377,166 bytes; 24,790 JSONL rows |
| Shard limit | 2,000,000,000 bytes (decimal); one shard was enough |
| Compression | zstd level 10, tar (PAX), single frame per shard, checksummed |
| Source | `/tmp/amt-syn` at 2026-11-02T05:40:50Z. No file in it had changed in the hour before (checked with `find -newermt '-60 min'`) |
| Packer | `provenance/code/pack_feasibility_2026_10.py` (sha256 `ecaf4caf7bbb6fe952b4c054fd76ad34f2f4ff7f293a00c4d7a5568e513480a1`), which decides the file list and calls Echo's `echo_data.pack` from `Reference-project-echo/echo-ai-exp` at `d96629b` (imported, not copied). Python: `/home/alexjia/.venvs/abl-store` (zstandard 0.25.0, huggingface_hub 2.3.0) |
| Code commit in the manifest | `null` (this repository has no commit yet). `meta.producing_scripts_sha256` lists the sha256 of every script in `scripts/probe/breakingweb/` and `scripts/realworld/`, the packer and Echo's `pack.py` and `safety.py` |
| Hashes as run | Scripts were revised while the evidence was made. `bw-gate/final_script_hashes.txt` and each run's `manifest.json` inside the shard record the hashes as run |

### What is in it (by top folder of `/tmp/amt-syn`)

| Folder | Files | MB | What it is |
|---|---|---|---|
| `bw-gate` | 6,059 | 688.1 | variant gate: observations, DOM dumps, screenshots, `gate.json` per env ([variant gate](../docs/feasibility/2026-10-30-variant-gate.md)); `final/` is the frozen pilot input (`pilot_plan.py:58`) |
| `bw-fx` | 4,220 | 466.2 | function equivalence ([record](../docs/feasibility/2026-10-30-function-equivalence.md)) |
| `rwk` | 3,460 | 253.6 | real-world kit on BreakingWeb pages and its self-test ([record](../docs/feasibility/2026-11-02-realworld-kit.md)); `.rwk.json` detections and analysis kept, MHTML snapshots of BreakingWeb pages left out |
| `bw-variants` | 1,873 | 230.0 | 2026-10-29 variant reports ([record](../docs/feasibility/2026-10-29-breakingweb.md)) |
| `bw-path` | 2,649 | 57.1 | path replays of published trajectories ([on-path dose](../docs/feasibility/2026-10-30-on-path-dose.md)); the codemod source trees `cm_*` left out |
| `bw-bu`, `bw-bu-test` | 1,239 | 56.2 | browser-use footprint ([record](../docs/feasibility/2026-10-30-browseruse-footprint.md)) |
| `bw-replay`, `bw-replay-test` | 3,269 | 11.6 | replay feasibility ([record](../docs/feasibility/2026-10-30-replay-feasibility.md)) |
| `traces`, `h1-smoke`, `h1-test`, `h1` | 144 | 7.5 | H1 wrapper smoke traces (8 runs, Sonnet 5.5 and GPT-5.6-sol), self-tests, packets, budget and probe outputs ([wrapper](../docs/feasibility/2026-11-02-h1-wrapper.md), [smoke](../docs/feasibility/2026-11-02-wrapper-smoke.md)) |
| `bw-smoke` | 5 | 0.2 | pipeline smoke outputs ([record](../docs/feasibility/2026-10-30-pipeline-smoke.md)) |
| `pilot`, `pilot2`, `pilot-cost-20261102` | 23 | 0.8 | pilot planning outputs before trimming (proposal F10) |
| `split-check-20261102` | 101 | 2.3 | the 2026-11-02 split check: `git archive` copy of the three v2 folders and its regenerated outputs (proposal section 1); its `.git/` left out |
| `hf_files.json`, `hf_files_v3.json`, `hf_v3_dl.log` | 3 | 24.5 | listings of the published BreakingWeb dataset and the download log |
| others (`bw-fx-test`, `bw-probe`, `DQ-form`, `DQ-dose`, `rwk-scratch`, `bw-gate-old`, `bw-fakedate`, `csstest`, three `bw-bu-*.log`, `bw-bu-run.sh`) | 131 | 4.2 | small probes, logs and their scripts (all ours) |

Traces, observations and screenshots contain BreakingWeb page text and rendered pages. They are evidence, kept only in this private dataset (CLAUDE.md "Privacy").

### What was left out, and why

| Rule | Files | Where | Why | How it is still accounted for |
|---|---|---|---|---|
| `clone` | 533,757 | 18 `*/BreakingWeb` copies and 6 clone roots (`bw-clean`, `bw-var-*`, `bw-varfix-*`) | BreakingWeb has no LICENSE, so its code is not redistributed, and clones are re-creatable from `052f0f0` | `meta.clone_copies`: each copy with a git directory is at HEAD `052f0f0` with 4 modified tracked files (the allowed diffs: `breakingweb/app.py` and three `scripts/*.sh`). The 6 clone roots have no `.git` |
| `tooling` | 131 | `__pycache__/` (4 folders), `split-check-20261102/.git` | re-creatable | counts in `meta.excluded` |
| `bundle` | 0 | `static/envs/` outside clones | built bundles are BreakingWeb code; builds are byte-reproducible (`studies/v2-pilot/DESIGN.md` §3) | none found outside clones |
| `bw_source` | 730 | `bw-path/cm_orig`, `cm_now`, `cm_fixed` (243 files each: BreakingWeb `src/` trees before and after the codemod), `bw-probe/Home.tsx.orig` | BreakingWeb source | sha256 and size of each in `meta.excluded_hash_list` |
| `bw_snapshot` | 1,064 | `rwk/bw*/captures/**.mhtml` | Chrome MHTML of BreakingWeb pages embeds the built CSS (checked: `Content-Type: text/css` parts) | sha256 and size of each in `meta.excluded_hash_list`; the `.rwk.json` detections next to them are in the shard |

Recorded input not uploaded: `~/.hf-stage-bw` (published BreakingWeb trajectories, 387 MB, including Gemini and Qwen runs). Only its file list with sha256 (5,343 files, its `.cache/` skipped) is in `meta.recorded_inputs`, because the dataset's licence is checked in Stage 0 (`studies/v2-pilot/DESIGN.md` §9; platform-split proposal §8).

Safety checks before upload: Echo's deny list (credentials, `KEY/`) was applied by the packer; a grep of every packed file for AWS access key ids, `aws_secret_access_key`, `aws_session_token`, Hugging Face tokens, long bearer tokens and private-key headers found none.

### How the upload was checked

1. `verify_packed(deep=True)` on the local shard: 23,176 of 23,176 files match their manifest sha256.
2. Listing (`HfApi.list_repo_tree`, recursive): `.gitattributes`, `snapshots/feasibility-2026-10/v1/MANIFEST.json` (6,515,215 bytes) and `shard-00000.tar.zst` (846,166,792 bytes, LFS sha256 `195827fe…7d38`).
3. Download (`hf download ... --local-dir /tmp/abl-dl`) of both files: sha256 of the downloaded shard and manifest equal the local ones, and `verify_packed(deep=True)` on the downloaded copy checked all 23,176 files.

## Restore

```bash
hf download alexjiang04/a11y-ablation-data --repo-type dataset \
  --include 'snapshots/feasibility-2026-10/v1/*' --local-dir /tmp/abl-dl
/home/alexjia/.venvs/abl-store/bin/python -I -c "import sys; sys.path.insert(0,'/home/alexjia/.workspace/Reference-project-echo/echo-ai-exp'); \
from echo_data import pack as P; print(P.unpack('/tmp/abl-dl/snapshots/feasibility-2026-10/v1', '/tmp/amt-syn-restored'))"
```

`unpack` checks every file's sha256 while writing and refuses to overwrite. After Stage 0 this becomes `abl_store pull`.

## How this could be wrong, and what would change it

- **The snapshot is a point in time.** Outputs written to `/tmp/amt-syn` after 05:40:50Z (by later steps of this workflow or later runs) are not in `v1`. They go into a new version (`v2`) of the series or into their own series; `v1` is never edited.
- **Leaving out the MHTML snapshots** means the real-world kit cannot be re-run on those exact BreakingWeb captures from the dataset. They are re-creatable from a rebuild at `052f0f0` plus the capture script, and their hashes are listed. If the BreakingWeb authors grant storage (the Stage 0 licence request, READINESS B-13), the snapshots and the `cm_*` trees can be added as a new version.
- **Rule matching is by path.** A BreakingWeb file copied under an unexpected name outside the five rules would have been packed. The grep for `.tsx/.ts/.jsx/.orig` and the review of every packed `.py`, `.sh` and `.js` file (all ours: first lines read) make this unlikely, not impossible.
