"""Task sample, cell list and cost estimate for the v2 pilot (studies/v2-pilot/).

No LLM is called and no environment is built. Everything is computed from the
2026-10-30 feasibility summaries, the BreakingWeb task YAMLs, the recorded
Gemini-3.1-Pro clean trajectories (used as recorded data only) and the gate
captures.

Inputs
  docs/feasibility/2026-10-30-replay-feasibility.json   reference set, matrix, bundles, pc_break
  docs/feasibility/2026-10-30-on-path-dose.json         panel tiers, on/off flags, hardened flag
  ~/.workspace/_refsrc/BreakingWeb/breakingweb/tasks/*/*.yaml   expected_steps per task
  ~/.hf-stage-bw/gemini_3_1_pro/tasks/<task>__clean/trajectory.json   recorded actions per run
  /tmp/amt-syn/bw-gate/final/<env>/clean0/*.txt         BrowserGym viewport observations (size)

Outputs (OUT, default /tmp/amt-syn/pilot/)
  select.json   pool, frozen pilot sample, sealed (held-out) tasks, per-task on/off flags
  cells.json    every (harness, model, task, cell, repeats) row of the run matrix
  cost.json     runs, steps, tokens and dollars under the stated assumptions
  files         (command) writes studies/v2-pilot/cells_by_task.json and updates the
                generated sections of studies/v2-pilot/design.yaml (cells, size, tasks)
                from cells.json; the hand-written sections of design.yaml are kept

Selection rule (fixed 2026-10-30, before any agent run; DESIGN.md section 5)
  pool   = replay reference set (3/3 clean replays, do-nothing fails)
           AND not hardened AND panel tier A (4-6 of 6 published panel models solved)
           AND no 'unstable' verdict in any replay cell
  sample = all pool tasks on-path for tableheads (primary flag), then a stratified
           random fill by env to N_PILOT, quota proportional to the env's remaining
           pool, at least 3 per env (or all if fewer); RNG seeded with
           sha256("amt-v2-pilot-2026-10-30"); within an env, tasks are drawn in
           the RNG's shuffle of the sorted task ids.
  sealed = pool minus sample (no study-model run on them until the main study).

Run
  python3 pilot_plan.py select [OUT]
  python3 pilot_plan.py cells  [OUT]
  python3 pilot_plan.py cost   [OUT]
  python3 pilot_plan.py files  [OUT]
  python3 pilot_plan.py all    [OUT]   (select, cells, cost, files)
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import random
import statistics as st
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FEAS = os.path.join(REPO, "docs", "feasibility")
BW = os.path.expanduser("~/.workspace/_refsrc/BreakingWeb")
TRAJ = os.path.expanduser("~/.hf-stage-bw/gemini_3_1_pro/tasks")
GATE = "/tmp/amt-syn/bw-gate/final"

N_PILOT = 64
SEED_TEXT = "amt-v2-pilot-2026-10-30"
KINDS = ["landmarks", "headings", "names", "labels", "alt", "tableheads"]
ENV_LONG = {"pp": "patient_portal", "rh": "robinhood"}

# Repeats per cell (DESIGN.md section 4). Clean: 2 screening + 4 baseline.
R = {
    "bg": {"clean": 6, "none": 3, "kind": 3, "sham": 3, "fmt": 3, "pos_info": 2, "pos_func": 2},
    "bu": {"clean": 5, "none": 3, "kind": 3},
}
# Revision of 2026-10-30 after review (DESIGN.md, "Review response"):
#   - kinds run on on-path (primary flag) tasks only; the off-path cells are dropped
#     (the on/off contrast is not estimable at these counts);
#   - names~ (source paraphrase sham) replaced by names+ (observation-layer add-back on the
#     names build: clean names restored on changed lines, variant form kept), on names
#     on-path tasks; names50 (names+ on a seeded half of the changed lines) on strict tasks;
#   - fmt_indent replaced by fmt_wrap (landmark-keeping format control) on all 64 tasks;
#   - browser-use arm (H2) keeps clean, none and names only.
MODELS = ["us.anthropic.claude-opus-5-5", "us.openai.gpt-5.6-sol"]
N_POS = 24   # tasks per positive control and per format control
BU_ENVS = ["amazon", "gmail", "pp"]   # envs with a measured browser-use footprint
BU_KINDS = ["names"]
# Off-path cells are run only where the on-path dose record found natural off-path
# tasks within the env (2026-10-30-on-path-dose.md section 5); elsewhere a kind is
# run only on tasks whose path carries it.
OFFPATH_ENVS = {
    "names": {"amazon", "booking", "gmail", "reddit", "robinhood"},
    "labels": {"amazon", "booking", "reddit", "robinhood"},
    "tableheads": {"booking", "gmail", "robinhood"},
}

# Cost assumptions (DESIGN.md section 9); every number is stated in cost.json.
ASSUME = {
    "chars_per_token": 3.3,          # ours; AX text has many short tokens
    "system_tokens": 700,            # agent.py SYSTEM_PROMPT plus task line
    "history_cap_tokens_est": 26000, # agent.py MAX_INPUT_TOKENS, estimated as len/2.5
    "est_chars_per_token": 2.5,      # agent.py _estimate_tokens
    "clean_success": 0.70,           # prior: tier-A tasks, panel mean ~0.6-0.75
    "extra_steps_success": 3,        # scrolls, send_msg_to_user, retries
    "output_tokens_per_step": {"us.anthropic.claude-opus-5-5": 600, "us.openai.gpt-5.6-sol": 900},
    "price_per_mtok": {              # input, output USD
        "us.anthropic.claude-opus-5-5": [4.0, 20.0],   # Anthropic list price; Bedrock price [unverified]
        "us.openai.gpt-5.6-sol": [4.0, 20.0],          # PLACEHOLDER [unverified]: read Bedrock pricing before the run
    },
    "bu_input_tokens_per_step": 11000,   # system ~4k + browser_state ~3-4k + screenshot ~1.5k + history ~2k (ours)
    "bu_steps_success_factor": 1.0,      # browser-use steps ~= recorded Gemini steps
    "bu_steps_fail": 30,                 # half of the 60-step cap (ours)
}


def load():
    rep = json.load(open(os.path.join(FEAS, "2026-10-30-replay-feasibility.json")))
    dose = json.load(open(os.path.join(FEAS, "2026-10-30-on-path-dose.json")))
    return rep, dose


def task_yaml():
    import yaml
    out = {}
    for p in glob.glob(os.path.join(BW, "breakingweb", "tasks", "*", "*.yaml")):
        y = yaml.safe_load(open(p))
        if isinstance(y, dict) and y.get("task_id"):
            out[y["task_id"]] = y
    return out


def select(out_dir):
    rep, dose = load()
    ref = set(rep["matrix"])
    unstable = {t for t, m in rep["matrix"].items() if "unstable" in m.values()}
    pool = []
    for t in sorted(ref):
        d = dose["tasks"][t]
        if d["hardened"] or d["panel_k"] < 4 or t in unstable:
            continue
        pool.append(t)
    info = {}
    for t in pool:
        d = dose["tasks"][t]
        env = ENV_LONG.get(d["env"], d["env"])
        info[t] = {
            "env": env,
            "panel_k": d["panel_k"],
            "on_primary": {k: bool(d["kinds"][k][1]) for k in KINDS},
            "on_strict": {k: bool(d["kinds"][k][2]) for k in KINDS},
            "dose": {k: d["kinds"][k][0] for k in KINDS},
        }
    rng = random.Random(int(hashlib.sha256(SEED_TEXT.encode()).hexdigest(), 16))
    must = sorted(t for t in pool if info[t]["on_primary"]["tableheads"])
    rest = [t for t in pool if t not in must]
    by_env = defaultdict(list)
    for t in rest:
        by_env[info[t]["env"]].append(t)
    for e in by_env:
        rng.shuffle(by_env[e])
    n_fill = N_PILOT - len(must)
    envs = sorted(by_env)
    quota = {e: min(len(by_env[e]), 3) for e in envs}
    left = n_fill - sum(quota.values())
    # proportional allocation of the remainder (largest remainder method)
    remain = {e: len(by_env[e]) - quota[e] for e in envs}
    tot = sum(remain.values())
    raw = {e: left * remain[e] / tot for e in envs}
    add = {e: min(remain[e], int(math.floor(raw[e]))) for e in envs}
    short = left - sum(add.values())
    for e in sorted(envs, key=lambda e: -(raw[e] - math.floor(raw[e]))):
        if short <= 0:
            break
        if add[e] < remain[e]:
            add[e] += 1
            short -= 1
    sample = list(must)
    for e in envs:
        sample += by_env[e][: quota[e] + add[e]]
    sample = sorted(sample)
    sealed = sorted(set(pool) - set(sample))

    def counts(ts):
        c = {"n": len(ts), "env": dict(Counter(info[t]["env"] for t in ts))}
        for k in KINDS:
            c[f"{k}_on"] = sum(info[t]["on_primary"][k] for t in ts)
            c[f"{k}_on_strict"] = sum(info[t]["on_strict"][k] for t in ts)
        return c

    res = {
        "rule": __doc__.split("Selection rule")[1].split("Run\n")[0].strip(),
        "seed_text": SEED_TEXT,
        "pool": counts(pool),
        "sample": counts(sample),
        "sealed": counts(sealed),
        "sample_tasks": sample,
        "sealed_tasks": sealed,
        "task_info": {t: info[t] for t in pool},
        "excluded_unstable": sorted(unstable),
    }
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, "select.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("pool", "sample", "sealed")}, indent=1))
    return res


def cells(out_dir):
    rep, _ = load()
    sel = json.load(open(os.path.join(out_dir, "select.json")))
    info = sel["task_info"]
    ident = {}   # env/kind -> bundle identical to clean
    for env, b in rep["bundles"].items():
        for k in KINDS:
            ident[(env, k)] = (k not in b) or (b[k]["bundle"] == b["clean"]["bundle"])
    # booking alt failed the variant gate
    gate_fail = {("booking", "alt")}
    pcb = rep["controls"]["pc_break"]
    pcb_infeasible = {t for env, v in pcb.items() for t in v.get("not_feasible", {})}
    rows = []
    sample = sel["sample_tasks"]
    pos_tasks = sorted(t for t in sample if t in pcb_infeasible)
    rng = random.Random(int(hashlib.sha256((SEED_TEXT + "/pos").encode()).hexdigest(), 16))
    rng.shuffle(pos_tasks)
    pos_tasks = sorted(pos_tasks[:N_POS])
    fmt_tasks = list(sample)
    rng.shuffle(fmt_tasks)
    fmt_tasks = sorted(fmt_tasks[:N_POS])
    for m in MODELS:
        for t in sample:
            env = info[t]["env"]
            on = info[t]["on_primary"]
            strict = info[t]["on_strict"]
            rows.append(("bg", m, t, "clean", R["bg"]["clean"]))
            rows.append(("bg", m, t, "none", R["bg"]["none"]))
            for k in KINDS:
                if ident.get((env, k), True) or (env, k) in gate_fail:
                    continue
                if not on[k]:
                    continue
                rows.append(("bg", m, t, k, R["bg"]["kind"]))
            if on["names"]:
                rows.append(("bg", m, t, "names+", R["bg"]["sham"]))
            if strict["names"]:
                rows.append(("bg", m, t, "names50", R["bg"]["sham"]))
            if on["labels"]:
                rows.append(("bg", m, t, "labels~", R["bg"]["sham"]))
            rows.append(("bg", m, t, "fmt_wrap", R["bg"]["fmt"]))
            if t in fmt_tasks:
                rows.append(("bg", m, t, "pos_info", R["bg"]["pos_info"]))
            if t in pos_tasks:
                rows.append(("bg", m, t, "pc_break", R["bg"]["pos_func"]))
            if env in [ENV_LONG.get(e, e) for e in BU_ENVS]:
                rows.append(("bu", m, t, "clean", R["bu"]["clean"]))
                rows.append(("bu", m, t, "none", R["bu"]["none"]))
                for k in BU_KINDS:
                    if not ident.get((env, k), True) and on[k]:
                        rows.append(("bu", m, t, k, R["bu"]["kind"]))
    res = {
        "rows": [dict(harness=h, model=m, task=t, cell=c, repeats=r) for h, m, t, c, r in rows],
        "pos_func_tasks": pos_tasks,
        "pos_info_tasks": fmt_tasks,
        "identical_bundles": sorted(f"{e}/{k}" for (e, k), v in ident.items() if v),
    }
    agg = Counter()
    for h, m, t, c, r in rows:
        agg[(h, c)] += r
    res["runs_by_harness_cell_both_models"] = {f"{h}/{c}": n for (h, c), n in sorted(agg.items())}
    res["runs_total"] = sum(r for *_, r in rows)
    json.dump(res, open(os.path.join(out_dir, "cells.json"), "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("runs_by_harness_cell_both_models", "runs_total", "identical_bundles")}, indent=1))
    return res


def obs_tokens_per_env():
    out = {}
    for env in ["amazon", "booking", "gmail", "lms", "patient_portal", "reddit", "robinhood"]:
        fs = [f for f in glob.glob(os.path.join(GATE, env, "clean0", "*.txt")) if not f.endswith(".all.txt")]
        if not fs:
            out[env] = 3000 / ASSUME["chars_per_token"]
            continue
        out[env] = st.mean(len(open(f).read()) for f in fs) / ASSUME["chars_per_token"]
    return out


def bg_run_tokens(n_steps, obs_tok):
    """Input tokens of one BrowserGym run: history grows by one observation per step
    until agent.py's trim cap (26k estimated tokens = 65k chars) is reached."""
    cap = ASSUME["history_cap_tokens_est"] * ASSUME["est_chars_per_token"] / ASSUME["chars_per_token"]
    tot = 0.0
    for k in range(1, n_steps + 1):
        tot += min(ASSUME["system_tokens"] + k * (obs_tok + 40), cap)
    return tot


def cost(out_dir):
    sel = json.load(open(os.path.join(out_dir, "select.json")))
    cl = json.load(open(os.path.join(out_dir, "cells.json")))
    yam = task_yaml()
    obs = obs_tokens_per_env()
    info = sel["task_info"]
    per_task = {}
    for t in sel["sample_tasks"]:
        d = json.load(open(os.path.join(TRAJ, f"{t}__clean", "trajectory.json")))
        tr = d["agent"]["trajectory"]
        acts = sum(len(s.get("actions") or [s.get("action")]) for s in tr)
        cap = int((yam[t].get("expected_steps") or 30) * 1.5)
        s_ok = min(cap, acts + ASSUME["extra_steps_success"])
        o = obs[info[t]["env"]]
        p = ASSUME["clean_success"]
        bg_steps = p * s_ok + (1 - p) * cap
        bg_in = p * bg_run_tokens(s_ok, o) + (1 - p) * bg_run_tokens(cap, o)
        bu_steps = p * len(tr) * ASSUME["bu_steps_success_factor"] + (1 - p) * ASSUME["bu_steps_fail"]
        per_task[t] = dict(bg_steps=bg_steps, bg_in=bg_in, bu_steps=bu_steps,
                           bu_in=bu_steps * ASSUME["bu_input_tokens_per_step"], cap=cap)
    tot = defaultdict(lambda: defaultdict(float))
    for r in cl["rows"]:
        pt = per_task[r["task"]]
        key = (r["harness"], r["model"])
        n = r["repeats"]
        steps = pt["bg_steps"] if r["harness"] == "bg" else pt["bu_steps"]
        tin = pt["bg_in"] if r["harness"] == "bg" else pt["bu_in"]
        tot[key]["runs"] += n
        tot[key]["steps"] += n * steps
        tot[key]["input_tokens"] += n * tin
        tot[key]["output_tokens"] += n * steps * ASSUME["output_tokens_per_step"][r["model"]]
    rows = {}
    grand = 0.0
    for (h, m), v in sorted(tot.items()):
        pi, po = ASSUME["price_per_mtok"][m]
        usd = v["input_tokens"] / 1e6 * pi + v["output_tokens"] / 1e6 * po
        grand += usd
        rows[f"{h}/{m}"] = {k: round(x) for k, x in v.items()} | {"usd": round(usd)}
    res = {
        "assumptions": ASSUME,
        "obs_tokens_per_env": {k: round(v) for k, v in obs.items()},
        "mean_per_run": {
            "bg_steps": round(st.mean(p["bg_steps"] for p in per_task.values()), 1),
            "bg_input_tokens": round(st.mean(p["bg_in"] for p in per_task.values())),
            "bg_step_cap": round(st.mean(p["cap"] for p in per_task.values()), 1),
            "bu_steps": round(st.mean(p["bu_steps"] for p in per_task.values()), 1),
        },
        "by_harness_model": rows,
        "usd_total": round(grand),
        "usd_range_x0.5_x2": [round(grand * 0.5), round(grand * 2)],
    }
    json.dump(res, open(os.path.join(out_dir, "cost.json"), "w"), indent=1)
    print(json.dumps(res, indent=1, default=str))
    return res


def files(out_dir):
    """Write cells_by_task.json and the generated sections of design.yaml (study folder)."""
    import yaml
    study = os.path.join(REPO, "studies", "v2-pilot")
    sel = json.load(open(os.path.join(out_dir, "select.json")))
    cl = json.load(open(os.path.join(out_dir, "cells.json")))
    info = sel["task_info"]
    tasks = {}
    for r in cl["rows"]:
        if r["model"] != MODELS[0]:
            continue
        t = r["task"]
        d = tasks.setdefault(t, {"env": info[t]["env"],
                                 "on_primary": [k for k in KINDS if info[t]["on_primary"][k]],
                                 "on_strict": [k for k in KINDS if info[t]["on_strict"][k]]})
        d.setdefault(r["harness"], {})[r["cell"]] = r["repeats"]
    cbt = {
        "note": "Per task: cell -> repeats per model (same for both models). Regenerate with scripts/probe/breakingweb/pilot_plan.py all.",
        "runs_total_both_models": cl["runs_total"],
        "runs_by_harness_cell_both_models": cl["runs_by_harness_cell_both_models"],
        "pos_func_tasks": cl["pos_func_tasks"],
        "pos_info_tasks": cl["pos_info_tasks"],
        "tasks": tasks,
    }
    json.dump(cbt, open(os.path.join(study, "cells_by_task.json"), "w"), indent=1)
    yp = os.path.join(study, "design.yaml")
    head = [l for l in open(yp).read().splitlines() if l.startswith("#")][:3]
    y = yaml.safe_load(open(yp))
    y["size"]["runs_total"] = cl["runs_total"]
    y["size"]["runs_by_harness_cell_both_models"] = cl["runs_by_harness_cell_both_models"]
    y["tasks"] = tasks
    for c in ("pos_info",):
        y["cells"][c]["tasks"] = cl["pos_info_tasks"]
    y["cells"]["pc_break"]["tasks"] = cl["pos_func_tasks"]
    txt = yaml.safe_dump(y, sort_keys=False, width=140, allow_unicode=True)
    open(yp, "w").write("\n".join(head) + "\n" + txt)
    print("wrote", os.path.join(study, "cells_by_task.json"), yp)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/amt-syn/pilot"
    if cmd in ("select", "all"):
        select(out)
    if cmd in ("cells", "all"):
        cells(out)
    if cmd in ("cost", "all"):
        cost(out)
    if cmd in ("files", "all"):
        files(out)
