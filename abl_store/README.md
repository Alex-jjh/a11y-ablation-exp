# abl_store: pack, manifest, push, pull

> **Summary:** Packs a folder into zstd tar shards with a `MANIFEST.json` (file list, sha256, sizes, rows, producing code), pushes versions to the private dataset `alexjiang04/a11y-ablation-data` and pulls them back. It knows nothing about what the files mean. Empty skeleton: the first snapshot was packed by `provenance/code/pack_feasibility_2026_10.py` calling Echo's `echo_data.pack` at `d96629b`.

## Single job

Move artefacts between this machine and the private dataset without changing a byte. One reason to change: the storage format or the store.

## Inputs and outputs

| Direction | What | Contract |
|---|---|---|
| in | a folder, or an explicit file list, plus `meta` | caller decides what goes in; the deny list (credentials, `KEY/`) always applies |
| out | `snapshots/<series>/<version>/MANIFEST.json` + `shard-NNNNN.tar.zst` | [`snapshot_manifest`](../schemas/snapshot_manifest.schema.json) (format `echo-data/1`); version tag `<series>-<version>` |
| out | pulled and verified tree | every file's sha256 checked while writing |

## Depends on / must not know about

- Depends on: `zstandard`, `huggingface_hub` (venv `/home/alexjia/.venvs/abl-store` today).
- Must not know about: schemas' meaning, experiments, AWS.

## Comes from (Stage 0)

Echo's `echo_data` (`pack.py`, `safety.py`, `store.py`, `snapshot.py`, `segments.py`) at `d96629b`, vendored with a provenance file. Every write first confirms the dataset is private; an unconfirmed visibility aborts (Echo `store.py:24-27`).

## Series

`feasibility-2026-10` (uploaded, `provenance/DATA.md`), then `bundles-<codemod8>` (hash lists and build logs only), `pilot-<run_id>` (trace segments), `observer-<run_id>-<observer>`, `census-<date>` (platform-split proposal §8).
