"""One-shot: pack the v2 feasibility evidence in /tmp/amt-syn into zstd tar shards (series feasibility-2026-10).

Run (2026-11-02):
    /home/alexjia/.venvs/abl-store/bin/python -I provenance/code/pack_feasibility_2026_10.py \
        /tmp/amt-syn /tmp/abl-pack/feasibility-2026-10/v1

Packing is Echo's echo_data.pack (Reference-project-echo/echo-ai-exp at d96629b, imported, not copied).
This script only decides WHICH files go in, and records what was left out and why.

Exclusion rules (each excluded file is counted under the first rule that matches):
  clone        a BreakingWeb clone copy: a folder named BreakingWeb, or a clone root (bw-clean, bw-var-*,
               bw-varfix-*). BreakingWeb has no LICENSE, so its source is not redistributed, even privately.
  tooling      node_modules/, .venv/, .git/, __pycache__/ anywhere.
  bundle       built bundles: any path under static/envs/.
  bw_source    copies of BreakingWeb source outside clones: bw-path/cm_*/ (codemod before/after source trees),
               *.tsx, *.ts, *.jsx, *.orig.
  bw_snapshot  MHTML page snapshots of BreakingWeb apps (rwk/bw*/captures/**.mhtml): they embed the built CSS
               and markup of the bundles. Their .rwk.json detections are kept.
Files under bw_source and bw_snapshot are listed with sha256 in the manifest meta (hash only, no content), so the
evidence they were can still be matched to a rebuild.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ECHO = Path("/home/alexjia/.workspace/Reference-project-echo/echo-ai-exp")
V2 = Path("/home/alexjia/.workspace/a11y-ablation-exp")
V1 = Path("/home/alexjia/.workspace/ai-agent-accessibility")
HF_STAGE = Path("/home/alexjia/.hf-stage-bw")
sys.path.insert(0, str(ECHO))
from echo_data import pack as P  # noqa: E402

SHARD_LIMIT = 2_000_000_000  # 2 GB (decimal), the task's ceiling
CLONE_ROOT_GLOBS = ["bw-clean", "bw-var-*", "bw-varfix-*"]
TOOLING = {"node_modules", ".venv", ".git", "__pycache__"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def classify_dir(rel: str, name: str):
    if name == "BreakingWeb":
        return "clone"
    if "/" not in rel and any(fnmatch.fnmatchcase(rel, g) for g in CLONE_ROOT_GLOBS):
        return "clone"
    if name in TOOLING:
        return "tooling"
    if rel.endswith("static/envs") or "/static/envs/" in rel + "/":
        return "bundle"
    if fnmatch.fnmatchcase(rel, "bw-path/cm_*"):
        return "bw_source"
    return None


def classify_file(rel: str):
    if rel.endswith((".tsx", ".ts", ".jsx", ".orig")):
        return "bw_source"
    if rel.endswith(".mhtml") and fnmatch.fnmatchcase(rel, "rwk/bw*/captures/*"):
        return "bw_snapshot"
    return None


def walk(src: Path):
    keep, excluded = [], {}
    hashlisted = []
    clones = []
    for root, dirs, files in os.walk(src):
        rp = Path(root)
        rel_root = rp.relative_to(src).as_posix()
        rel_root = "" if rel_root == "." else rel_root
        kept_dirs = []
        for d in sorted(dirs):
            rel = f"{rel_root}/{d}" if rel_root else d
            full = rp / d
            if full.is_symlink():
                continue
            kind = classify_dir(rel, d)
            if kind is None:
                kept_dirs.append(d)
                continue
            n = 0
            for r2, _, f2 in os.walk(full):
                for fn in f2:
                    n += 1
                    if kind == "bw_source":
                        fp = Path(r2) / fn
                        hashlisted.append({"path": fp.relative_to(src).as_posix(), "rule": kind,
                                           "size": fp.stat().st_size, "sha256": sha256(fp)})
            excluded.setdefault(kind, {"files": 0, "dirs": []})
            excluded[kind]["files"] += n
            excluded[kind]["dirs"].append(rel)
            if kind == "clone":
                clones.append(rel)
        dirs[:] = kept_dirs
        for fn in sorted(files):
            full = rp / fn
            rel = f"{rel_root}/{fn}" if rel_root else fn
            if full.is_symlink() or not full.is_file():
                continue
            kind = classify_file(rel)
            if kind is None:
                keep.append(rel)
                continue
            excluded.setdefault(kind, {"files": 0, "dirs": []})
            excluded[kind]["files"] += 1
            hashlisted.append({"path": rel, "rule": kind, "size": full.stat().st_size, "sha256": sha256(full)})
    for k in excluded.values():
        k["dirs"] = sorted(k["dirs"])
    return keep, excluded, hashlisted, clones


def git(args, cwd):
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception as e:  # recorded, not fatal
        return f"ERROR {type(e).__name__}"


def clone_state(src: Path, rel: str):
    d = src / rel
    if not (d / ".git").exists():
        return {"path": rel, "git": None}
    st = git(["status", "--short", "--untracked-files=no"], d)
    return {"path": rel, "head": git(["rev-parse", "HEAD"], d), "modified_tracked": st.splitlines()}


def script_hashes():
    out = {}
    for sub in ("scripts/probe/breakingweb", "scripts/realworld"):
        for p in sorted((V2 / sub).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".sh", ".js"):
                out[p.relative_to(V2).as_posix()] = sha256(p)
    out["provenance/code/pack_feasibility_2026_10.py"] = sha256(Path(__file__).resolve())
    out["<echo>/echo_data/pack.py"] = sha256(ECHO / "echo_data/pack.py")
    out["<echo>/echo_data/safety.py"] = sha256(ECHO / "echo_data/safety.py")
    return out


def hf_stage_list():
    rows = []
    if not HF_STAGE.is_dir():
        return rows
    for p in sorted(HF_STAGE.rglob("*")):
        if p.is_file() and ".cache" not in p.relative_to(HF_STAGE).parts:
            rows.append({"path": p.relative_to(HF_STAGE).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)})
    return rows


def main():
    src, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    keep, excluded, hashlisted, clones = walk(src)
    meta = {
        "series": "feasibility-2026-10",
        "version": "v1",
        "what": "v2 (BreakingWeb ablation) feasibility evidence from /tmp/amt-syn: gate, function-equivalence, "
                "replay, path replay, browser-use footprint, smoke, H1 wrapper selftests and smoke traces, "
                "real-world kit runs, pilot planning outputs",
        "code_repository": {"name": "a11y-ablation-exp", "commit": None,
                            "note": "no commit yet; producing scripts identified by sha256 below"},
        "copied_from": {"repo": "ai-agent-accessibility", "commit": git(["rev-parse", "HEAD"], V1)},
        "producing_scripts_sha256": script_hashes(),
        "script_hashes_as_run_note": "scripts were revised during the work; bw-gate/final_script_hashes.txt and "
                                     "each run's manifest.json record the hashes as run",
        "excluded": excluded,
        "excluded_hash_list": hashlisted,
        "clone_copies": [clone_state(src, c) for c in clones],
        "recorded_inputs": {"hf_stage_bw": {"root": str(HF_STAGE),
                                            "note": "published BreakingWeb trajectories (incl. Gemini, Qwen runs); "
                                                    "file list and sha256 only, not uploaded (licence unchecked)",
                                            "files": hf_stage_list()}},
    }
    os.environ["ECHO_REPO"] = str(V2)
    m = P.pack(src, out, only_files=keep, shard_limit=SHARD_LIMIT, level=10, threads=3,
               name="feasibility-2026-10", meta=meta, progress=lambda s: print(s, flush=True))
    print(json.dumps({"totals": m["totals"], "shards": [{k: s[k] for k in ("name", "size", "files")} for s in m["shards"]],
                      "excluded": {k: v["files"] for k, v in excluded.items()},
                      "hash_listed": len(hashlisted)}, indent=1))


if __name__ == "__main__":
    main()
