#!/usr/bin/env python3
"""Check the replay's predicted post-defect names and counts against real codemod variants.

Question: path_replay.py predicts, on the clean build, what an acted-on element's accessible
name becomes when its aria-label (names) or its aria-label and label[for] (labels) are removed,
and counts the headings, landmarks, th and img alt that the codemod would change. Are these
predictions what the source-level variant (codemod.py, the reference by D-008) actually renders?

Inputs (all written by path_replay.py on the same 70-task sample of solved Gemini 3.1 Pro runs)
  /tmp/amt-syn/bw-path/variant_clean_loose/   clean build, loose matching (the reference)
  /tmp/amt-syn/bw-path/variant_names/         codemod names on every env + shared
  /tmp/amt-syn/bw-path/variant_labels/        codemod labels
  /tmp/amt-syn/bw-path/variant_pagekinds/     codemod headings + landmarks + tableheads + alt together
  /tmp/amt-syn/bw-path/variantfix_{names,labels}/  the same with TAG_BODY's first alternative changed from
                                              [^<>] to [^<>{}] (codemod_fixed.py in /tmp/amt-syn/bw-path/)
  All variant replays use AMT_REPLAY_LOOSE=1; codemod.py sha256 71a8d729a8eac09d.
Output
  /tmp/amt-syn/bw-path/analysis/variant_check.json (read by on_path_dose.py)
Run: python3 variant_check.py
"""
import glob
import json
import os
import re
from collections import Counter

B = '/tmp/amt-syn/bw-path'


def load(d):
    return {json.load(open(f))['task_id']: json.load(open(f)) for f in glob.glob(f'{B}/{d}/*.json')}


def norm(s):
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()


def acts(rec):
    return {(a['step'], a['j']): a for a in rec.get('actions', []) if a.get('el') and a.get('ax')}


def main():
    ref = load('variant_clean_loose')
    out = {'n_tasks_ref': len(ref), 'ref_replay_success': sum(1 for r in ref.values() if (r.get('replay_eval') or {}).get('success'))}
    for prefix, kind, pred_key, tags in [(p, k, pk, tg) for p in ('variant', 'variantfix') for k, pk, tg in
                                         (('names', 'no_aria', ('button', 'a')), ('labels', 'no_aria_no_for', ('input', 'textarea', 'select')))]:
        if not os.path.isdir(f'{B}/{prefix}_{kind}'):
            continue
        var = load(f'{prefix}_{kind}')
        c = Counter(); examples = []
        residual = Counter()
        for t, vr in var.items():
            if t not in ref:
                continue
            ra, va = acts(ref[t]), acts(vr)
            for k, a in ra.items():
                if a['el']['tag'] not in tags:
                    continue
                b = va.get(k)
                if b is None or b['el']['tag'] != a['el']['tag']:
                    c['unaligned'] += 1
                    continue
                pred, obs = norm(a['ax'].get(pred_key)), norm(b['ax'].get('clean'))
                c['match' if pred == obs else 'mismatch'] += 1
                if pred != obs and len(examples) < 25:
                    examples.append({'task': t, 'step': k[0], 'tag': a['el']['tag'], 'clean': a['ax'].get('clean'),
                                     'predicted': a['ax'].get(pred_key), 'variant': b['ax'].get('clean'),
                                     'variant_aria_label': b['el'].get('aria_label'), 'variant_label_for': b['el'].get('label_for')})
                if b['el'].get('aria_label') or b['el'].get('aria_labelledby'):
                    residual['aria_left'] += 1
                if kind == 'labels' and b['el'].get('label_for'):
                    residual['label_for_left'] += 1
        out[f'{prefix}_{kind}'] = {'n_tasks_variant': len(var),
                     'variant_replay_success': sum(1 for r in var.values() if (r.get('replay_eval') or {}).get('success')),
                     'compare': dict(c), 'residual_in_variant': dict(residual), 'mismatch_examples': examples}
    var = load('variant_pagekinds')
    pk = {}
    for key in ('headings', 'landmarks', 'th', 'img_alt'):
        tot_ref = tot_var = states = nz = 0
        for t, vr in var.items():
            for s in vr.get('states', []):
                states += 1
                tot_var += s[key]['doc']
                nz += s[key]['doc'] > 0
            for s in ref.get(t, {}).get('states', []):
                tot_ref += s[key]['doc']
        pk[key] = {'states_variant': states, 'instances_variant_sum': tot_var, 'states_with_any_left': nz,
                   'instances_clean_sum': tot_ref}
    left = Counter()
    for t, vr in var.items():
        for s in vr.get('states', []):
            for x in s.get('landmark_tags', []):
                left[x] += 1
    pk['landmark_kinds_left'] = dict(left)
    out['pagekinds'] = {'n_tasks_variant': len(var), 'variant_replay_success': sum(1 for r in var.values() if (r.get('replay_eval') or {}).get('success')), 'counts': pk}
    os.makedirs(f'{B}/analysis', exist_ok=True)
    json.dump(out, open(f'{B}/analysis/variant_check.json', 'w'), indent=1)
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != 'mismatch_examples'} if isinstance(v, dict) else v) for k, v in out.items()}, indent=1))


if __name__ == '__main__':
    main()
