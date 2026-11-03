#!/usr/bin/env python3
"""Per-task step budget for harness H1 (BrowserGym AXTree text, one action per step), derived from the
recorded reference trajectories. No LLM, no browser.

Question. The pilot must not fail a task because the step cap ran out while the agent was still on a
workable route (pipeline smoke record §4.6: both Opus 5.5 runs used 11-12 of their 15 steps reaching a
below-the-fold link; under the DESIGN cap of 1.5 x expected_steps = 10 they would have failed before the
form). How many H1 steps does a successful run need, and what cap leaves room for that?

Counting rules (written before looking at any study-model run; the only study-model data used are the 2
smoke episodes, which motivated the question and are not used to fit anything):
  H1 step   one BrowserGym action (click, fill, select_option, press, scroll, go_back, send_msg_to_user ...).
  acts(run) actions of a published browser-use run that need an H1 step: click, fill, select, press, back,
            scroll. Not counted: finish (counted once below), wait, noop, and the read-only browser-use
            actions with no H1 counterpart (search_page, find_elements, find_text, extract, dropdown_options;
            in H1 the agent reads the observation instead).
  wheel(t)  wheel ops in the compiled replay script of task t (replay.py compile: an element was outside the
            viewport and had to be scrolled to). browser-use clicks an element by index without scrolling;
            the H1 agent sees only the viewport (filter_visible_only=True), so each such element costs it at
            least one scroll step. One step per wheel op is a lower bound (ours).
  L_ref(t)  acts(Gemini-3.1-Pro reference run) + wheel(t) + 1 (send_msg_to_user). The shortest known route.
  need(run) acts(run) + wheel(t) + 1 for every successful published clean run of t by any of the 6 panel
            models (gemini_3_1_pro, gemini_3_flash, gpt_5_4, gpt_5_4_mini, opus_4_7, qwen3_vl_235b). The
            published runs are browser-use runs of non-study models: recorded data only.
  ratio     need(run) / L_ref(t): how much longer than the shortest route real successful agents went.

Cap rule (proposed; compared against the DESIGN rule cap_design = int(1.5 x expected_steps)):
  cap(t) = min(CEIL, max(cap_design(t), ceil(K x L_ref(t)) + A))
  K = the 95th percentile of ratio over all successful published runs on reference tasks (pooled over
      models), A = an additive allowance for orientation steps that do not scale with route length (the
      smoke runs spent ~10 steps finding one link), CEIL = 60 (stock browser-use's own cap; bounds cost).
  The script reports, for each rule, the share of successful published runs whose need exceeds the cap
  (the share that would have failed on budget alone), and the mean cap over the pilot sample (cost).

Inputs: ~/.hf-stage-bw/<model>/tasks/<task>__clean/trajectory.json (published runs),
/tmp/amt-syn/bw-replay/final/<env>/scripts/<task>.json and reference.json (replay record),
the clone's task YAMLs (expected_steps), studies/v2-pilot/select.json (sample).
Output: JSON to OUT (default /tmp/amt-syn/h1/budget.json) and a printed summary.
Run: python3 h1_budget.py [OUT] [--k K] [--a A]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
HF = os.path.expanduser('~/.hf-stage-bw')
REPLAY = '/tmp/amt-syn/bw-replay/final'
BW = os.path.expanduser('~/.workspace/_refsrc/BreakingWeb')
PANEL = ['gemini_3_1_pro', 'gemini_3_flash', 'gpt_5_4', 'gpt_5_4_mini', 'opus_4_7', 'qwen3_vl_235b']
STEP_ACTS = {'click', 'fill', 'select', 'press', 'back', 'scroll'}
CEIL = 60


def task_yaml():
    import yaml
    out = {}
    for p in glob.glob(f'{BW}/breakingweb/tasks/*/*.yaml'):
        d = yaml.safe_load(open(p))
        if isinstance(d, dict) and d.get('task_id'):
            out[d['task_id']] = d
    return out


def acts(traj):
    return sum(1 for s in traj for a in (s.get('actions') or [s.get('action')]) if (a or {}).get('action') in STEP_ACTS)


def load():
    ref, wheel = set(), {}
    for env_dir in sorted(glob.glob(f'{REPLAY}/*/')):
        r = json.load(open(f'{env_dir}/reference.json'))
        for t, v in r.items():
            if v.get('ref'):
                ref.add(t)
                s = json.load(open(f'{env_dir}/scripts/{t}.json'))
                wheel[t] = sum(1 for a in s['actions'] for o in a['ops'] if o['op'] == 'wheel')
    runs = {}
    for m in PANEL:
        for p in glob.glob(f'{HF}/{m}/tasks/*__clean/trajectory.json'):
            t = os.path.basename(os.path.dirname(p)).rsplit('__', 1)[0]
            d = json.load(open(p))
            runs.setdefault(t, {})[m] = {'success': bool((d.get('evaluation') or {}).get('success')),
                                         'acts': acts(d['agent']['trajectory'])}
    return ref, wheel, runs


def pct(xs, q):
    xs = sorted(xs)
    i = (len(xs) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', nargs='?', default='/tmp/amt-syn/h1/budget.json')
    ap.add_argument('--k', type=float, default=None, help='multiplier (default: 95th percentile of ratio)')
    ap.add_argument('--a', type=int, default=10, help='additive orientation allowance (H1 only; see docstring)')
    a = ap.parse_args()
    yam = task_yaml()
    ref, wheel, runs = load()
    sel = json.load(open(f'{REPO}/studies/v2-pilot/select.json'))
    sample = sel['sample_tasks']
    L = {t: runs[t]['gemini_3_1_pro']['acts'] + wheel[t] + 1 for t in ref if 'gemini_3_1_pro' in runs.get(t, {})}
    needs, ratios = [], []
    for t in L:
        for m, r in runs[t].items():
            if r['success']:
                n = r['acts'] + wheel[t] + 1
                needs.append((t, m, n))
                ratios.append(n / L[t])
    K = a.k if a.k is not None else round(pct(ratios, 0.95), 2)

    def cap_design(t):
        return int((yam[t].get('expected_steps') or 30) * 1.5)

    def cap_new(t):
        return min(CEIL, max(cap_design(t), math.ceil(K * L[t]) + a.a))

    def over(capf):
        bad = [(t, m, n, capf(t)) for t, m, n in needs if n > capf(t)]
        return len(bad), bad

    nd, bad_d = over(cap_design)
    nn, bad_n = over(cap_new)
    per_task = {t: {'env': yam[t]['env_id'] if 'env_id' in yam[t] else None, 'expected_steps': yam[t].get('expected_steps'),
                    'L_ref': L[t], 'wheel': wheel[t], 'cap_design': cap_design(t), 'cap_h1': cap_new(t),
                    'panel_need': {m: r['acts'] + wheel[t] + 1 for m, r in runs[t].items() if r['success']}}
                for t in sorted(L)}
    smoke = ['reddit_compose_message']
    res = {
        'rule': f'cap = min({CEIL}, max(int(1.5 x expected_steps), ceil(K x L_ref) + A))',
        'K': K, 'A': a.a, 'CEIL': CEIL,
        'n_reference_tasks': len(L), 'n_successful_published_runs': len(needs),
        'ratio_quantiles': {q: round(pct(ratios, q), 2) for q in (0.5, 0.75, 0.9, 0.95, 0.99)},
        'over_cap_design': {'n': nd, 'share': round(nd / len(needs), 4)},
        'over_cap_h1': {'n': nn, 'share': round(nn / len(needs), 4), 'runs': bad_n},
        'sample': {
            'n': len(sample),
            'mean_cap_design': round(st.mean(cap_design(t) for t in sample), 1),
            'mean_cap_h1': round(st.mean(cap_new(t) for t in sample), 1),
            'max_cap_h1': max(cap_new(t) for t in sample),
            'n_tasks_cap_raised': sum(cap_new(t) > cap_design(t) for t in sample),
            'over_cap_design_in_sample': sum(1 for t, m, n in needs if t in sample and n > cap_design(t)),
            'over_cap_h1_in_sample': sum(1 for t, m, n in needs if t in sample and n > cap_new(t)),
            'successful_runs_in_sample': sum(1 for t, m, n in needs if t in sample),
        },
        'smoke_tasks': {t: per_task.get(t) for t in smoke},
        'per_task': per_task,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('per_task', 'over_cap_h1')} |
                     {'over_cap_h1': {k: v for k, v in res['over_cap_h1'].items() if k != 'runs'}}, indent=1))


if __name__ == '__main__':
    main()
