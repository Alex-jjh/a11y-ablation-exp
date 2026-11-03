# a11y-ablation-exp: the v2 ablation platform

> **Summary:** The experiment platform of v2 of the AI agent accessibility study: remove one kind of accessibility information at a time from BreakingWeb's React apps, keep the page the same for a sighted mouse user, and measure LLM web-agent task success and behaviour. This repository holds the v2 code, protocol and records; evidence lives in the private Hugging Face dataset `alexjiang04/a11y-ablation-data`. It was scaffolded on 2026-11-02 from the v1 repository (`ai-agent-accessibility` at `5e4a05a`) by byte-identical copies of four folders. The six packages are empty skeletons with their contracts; code moves into them in Stage 0.

## Status (2026-11-02)

- Scaffold only: no commit yet, no remote. Alex makes the first commit.
- Code as run is in `scripts/probe/breakingweb/` and `scripts/realworld/`. Those scripts still call paths in the v1 repository and `/tmp/amt-syn` (62 references); they are moved into packages, with paths fixed, in Stage 0 before the Stage 0r hashes are taken.
- Pilot protocol: [`studies/v2-pilot/`](studies/v2-pilot/). Pre-run checklist: [`READINESS.md`](studies/v2-pilot/READINESS.md) (13 blockers, 17 decisions); defect register: [`DEFECTS.md`](studies/v2-pilot/DEFECTS.md).
- Decisions of 2026-11-02 (paper repository `DECISIONS.md` D-011 to D-016): Bedrock-only models, Sonnet 5.5 and GPT-5.6-sol in the pilot; native tool calling for every model; `names` split into `names_empty` and `names_fallback`, landmarks covering named `section` and `form`; every trace coded blind to the condition; this separate repository and dataset.

## Layout

```
a11y-ablation-exp/
  README.md  CLAUDE.md  .gitignore
  docs/
    ARCHITECTURE.md       packages, contracts, storage, where things came from
    feasibility/          copied byte-identical: the dated feasibility records (paths of their date)
  schemas/                JSON Schemas shared by all packages
  abl_envs/               built environments: codemod, build, content hash, serve on 127.0.0.1, restore
  abl_gates/              is a variant the defect and nothing else: look, function, replay, footprint
  abl_gateway/            the only AWS code: converse() under the model rule, tool use, reasoning capture
  abl_run/                design + bundles -> cells -> episodes, resumable
  abl_traces/             immutable traces, blinded packets, observer notes
  abl_store/              pack, manifest, push and pull to the private dataset
  scripts/probe/breakingweb/   copied byte-identical: the feasibility scripts as run
  scripts/realworld/           copied byte-identical: the real-world exemplar kit (start of a later abl_census)
  studies/v2-pilot/            copied byte-identical: the pilot protocol
  provenance/
    MANIFEST.md           the 125 copied files, sha256, source commit
    SHA256SUMS.copied     the same list for sha256sum -c
    DATA.md               what is in the dataset and how it was checked
    code/                 one-shot scripts (the 2026-11-02 evidence packer)
```

The four copied folders keep their relative paths so that every relative link and every path in `design.yaml` still resolves: 203 relative links in this repository, 0 broken, with the paper repository as a sibling in `~/.workspace/`.

## Related repositories

| Repository | Role |
|---|---|
| `~/.workspace/ai-agent-accessibility` | v1 (26 AMT operators on WebArena), frozen at tag `v1-final` (`b562fc6`); keeps its copies of the four folders; crosswalk rows in its `docs/archive/crosswalk.md` point here |
| `~/.workspace/ai-accessibility-paper` | project state (`STATUS.md`), decisions (`DECISIONS.md`), literature close-reads (`literature/papers/`) |
| `~/.workspace/_refsrc/BreakingWeb` | the shared BreakingWeb clone at `052f0f0`, read-only for experiments; work happens in private copies |
| `~/.workspace/Reference-project-echo/echo-ai-exp` | the Echo platform this layout follows (`docs/ARCHITECTURE.md`); `abl_store` will vendor its `echo_data` |

## Data

`alexjiang04/a11y-ablation-data` (private). Series `feasibility-2026-10`, version `v1`: the `/tmp/amt-syn` evidence as of 2026-11-02, one 846 MB shard. Contents, exclusions and checks: [`provenance/DATA.md`](provenance/DATA.md).

## Rules for agents

[`CLAUDE.md`](CLAUDE.md): model rule, credentials, privacy, 127.0.0.1, BreakingWeb licence, git.
