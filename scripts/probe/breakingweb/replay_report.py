#!/usr/bin/env python3
"""Small summary JSON for the replay-feasibility record, from replay.py outputs.

Inputs
  OUT        replay.py output root (e.g. /tmp/amt-syn/bw-replay/final), after `replay.py summary OUT`
             has written OUT/summary.json.
  DOSE_JSON  docs/feasibility/2026-10-30-on-path-dose.json (per-task on-path flags from
             path_replay.py, and the earlier replay outcome and the hardened flag per task).
  FX_DIR     click_effect.py output root (/tmp/amt-syn/bw-fx/final), for the bundle-hash
             comparison with the function-equivalence builds.
Output
  JSON on stdout: reference set per env with exclusion classes, the task x kind matrix, per-cell
  counts, how many reference tasks have each kind on the path (primary flag of on_path_dose.py),
  controls (do-nothing, pc_break), raw-coordinate agreement, op counts, and bundle hashes.
Run
  python3 replay_report.py OUT DOSE_JSON FX_DIR > docs/feasibility/2026-10-30-replay-feasibility.json
"""
import collections
import glob
import json
import os
import re
import sys

KINDS = ['landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads']


def main(out, dose_json, fx_dir):
    S = json.load(open(f'{out}/summary.json'))
    T = json.load(open(dose_json))['tasks']
    R = {'sources': {'replay_out': out, 'dose_json': dose_json}, 'envs': {}, 'cells': {}, 'matrix': S['matrix'],
         'controls': {}, 'on_path_reference': {}, 'raw_point_agrees': {}, 'ops_reference': {}, 'bundles': {}}
    pa = collections.Counter()
    ops = collections.Counter()
    hit_via = collections.Counter()
    for envdir in sorted(glob.glob(f'{out}/*/reference.json')):
        env = envdir.split('/')[-2]
        ref = json.load(open(envdir))
        cls = collections.Counter()
        imp = collections.Counter()
        for t, v in ref.items():
            if v['ref']:
                c = 'reference'
            elif not v['pure']:
                c = 'not_input_pure'
            elif not v['compile_success']:
                c = 'evaluator_fails_on_replay'
            else:
                c = 'unstable_on_clean'
            cls[c] += 1
            cls[f"{c}|earlier_replay_{'pass' if T[t]['replay_ok'] else 'fail'}{'|hardened' if T[t]['hardened'] else ''}"] += 1
            for s in v['impure'] or []:
                imp[re.sub(r"'.*", '', re.sub(r'^step [\d.]+ ', '', s))[:60]] += 1
            sc = json.load(open(f'{out}/{env}/scripts/{t}.json'))
            for a in sc['actions']:
                if 'point_agrees' in a:
                    pa[('reference' if v['ref'] else 'other', bool(a['point_agrees']))] += 1
                if v['ref']:
                    for o in a['ops']:
                        ops[o['op']] += 1
                    if a.get('hit_via'):
                        hit_via[a['hit_via']] += 1
        e = dict(S['envs'][env])
        e['classes'] = dict(sorted(cls.items()))
        e['impure_first_reasons'] = dict(imp.most_common())
        e['reference_tasks'] = sorted(t for t, v in ref.items() if v['ref'])
        R['envs'][env] = e
        ref_tasks = e['reference_tasks']
        for k in KINDS:
            on = [t for t in ref_tasks if T[t]['kinds'][k][1]]
            R['on_path_reference'].setdefault(k, {})[env] = {'n_ref': len(ref_tasks), 'on_path': len(on)}
        meta = json.load(open(f'{out}/{env}/builds.json'))
        fxm = json.load(open(f'{fx_dir}/{env}/builds.json')) if os.path.exists(f'{fx_dir}/{env}/builds.json') else {}
        R['bundles'][env] = {k: {'bundle': m.get('bundle'), 'fx_bundle': (fxm.get(k) or fxm.get('clean0' if k == 'clean' else k) or {}).get('bundle')}
                             for k, m in meta.items()}
    for c, v in S['cells'].items():
        env, kind = c.split('/')
        row = {'n': v['n'], 'counts': v['counts'], 'identical_bundle': v['identical_bundle']}
        nonf = {t: x for t, x in v['tasks'].items() if x['verdict'] not in ('feasible', 'feasible_identical')}
        if nonf:
            row['not_feasible'] = nonf
        dbp = sum(1 for x in v['tasks'].values() if x.get('diverge_but_pass'))
        row['passed_with_divergence'] = dbp
        if kind == 'pc_break':
            R['controls'].setdefault('pc_break', {})[env] = row
        else:
            R['cells'][c] = row
    R['controls']['null'] = S.get('null', {})
    R['raw_point_agrees'] = {f'{k[0]}|{k[1]}': n for k, n in sorted(pa.items())}
    R['ops_reference'] = dict(ops)
    R['hit_via_reference'] = dict(hit_via)
    json.dump(R, sys.stdout, indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:4])
