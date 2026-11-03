#!/usr/bin/env python3
"""How many of the function-equivalence trials act on an element the defect kind changed?

Question. click_effect.py compares the effect of each click and key press on clean and variant.
A preserved result is informative for a kind only if the trials act on elements the kind changed
(treated elements), not only on untouched ones. This script counts, per env x kind, the click and
key targets that are treated.

Grounding. Changed elements come from the variant gate's DOM dumps (variant_gate.py capture,
GATE/<env>/<build>/<page>.dom.json): every element in document order with tag and attributes, on
the same pages as click_effect.py. An element is changed if its tag or attributes differ between
clean0 and the variant at the same index (attribute values normalised as in the gate: session ids
and asset hashes) (the gate found the DOM aligned one to one). Ancestry is
read from the live clean page: ancestors of target i by parentElement, descendants as the
preorder range i+1 .. i+count(i.querySelectorAll('*')). Pages whose element count differs from
targets.json or from the dumps are skipped and counted (pages_misaligned).

Classes per target (document index i):
  self      element i itself changed (names: the button lost aria-label; labels: the label lost
            `for`, or the input lost aria-label; headings: a clickable heading became a div)
  inside    a descendant changed (alt: an image inside a link lost alt)
  within    an ancestor changed (the link sits in a nav or heading that became a div)
  none      no changed element on its ancestor-descendant line

Inputs:  FX (click_effect.py output dir, e.g. /tmp/amt-syn/bw-fx/final), GATE (variant_gate.py
         output, e.g. /tmp/amt-syn/bw-gate/final), ENV; the clean build of ENV must be in
         BW_ROOT's static/envs; BW_PORT a free port on 127.0.0.1 (same environment as click_effect.py).
Output:  FX/<env>/treated.json  {kind: {click: {self, inside, within, none}, key: {...}, pages_misaligned}}
Run:     BW_ROOT=<clean checkout> BW_PORT=8121 PYTHONPATH=$BW_ROOT <venv python> click_treated.py FX GATE ENV
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import click_effect as ce  # noqa: E402

KINDS = ['landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads']
ANC_JS = '''(idx) => { const all = [...document.querySelectorAll('*')]; const pos = new Map(all.map((e, i) => [e, i]));
  return {n: all.length, t: idx.map(i => { const e = all[i]; if (!e) return null; const anc = [];
    for (let p = e.parentElement; p; p = p.parentElement) anc.push(pos.get(p));
    return [anc, e.querySelectorAll('*').length]; })}; }'''


def changed(c, v):
    if c[1] != v[1]:
        return True
    strip = lambda a: {k: ce.vg.norm_attr(x) for k, x in a.items() if k != 'data-amt'}   # session ids, asset hashes
    return strip(c[2]) != strip(v[2])


def main(fx, gate, env):
    pages = json.load(open(f'{fx}/{env}/targets.json'))['pages']
    R = ce.Runner(env)
    lines = {}
    try:
        for pg in pages:
            idx = sorted({c['i'] for c in pg['clicks'] + pg['keys']})
            ctx, page, sid, rec = R.open(pg)
            try:
                r = page.evaluate(ANC_JS, idx)
            finally:
                ctx.close()
            lines[pg['key']] = (r['n'], dict(zip(idx, r['t'])))
    finally:
        R.close()
    res = {}
    for kind in KINDS:
        if not os.path.isdir(f'{gate}/{env}/{kind}'):
            continue
        cnt = {'click': dict.fromkeys(['self', 'inside', 'within', 'none'], 0),
               'key': dict.fromkeys(['self', 'inside', 'within', 'none'], 0), 'pages_misaligned': 0, 'examples': []}
        for pg in pages:
            pc, pv = f'{gate}/{env}/clean0/{pg["key"]}.dom.json', f'{gate}/{env}/{kind}/{pg["key"]}.dom.json'
            n_live, line = lines[pg['key']]
            if not (os.path.exists(pc) and os.path.exists(pv)):
                cnt['pages_misaligned'] += 1; continue
            dc, dv = json.load(open(pc))['els'], json.load(open(pv))['els']
            if not (len(dc) == len(dv) == pg['n_el'] == n_live):
                cnt['pages_misaligned'] += 1; continue
            ch = {i for i in range(len(dc)) if changed(dc[i], dv[i])}
            for group, tg in (('click', pg['clicks']), ('key', pg['keys'])):
                for c in tg:
                    i = c['i']; anc, nd = line[i]
                    cls = ('self' if i in ch else 'inside' if any(j in ch for j in range(i + 1, i + 1 + nd))
                           else 'within' if any(a in ch for a in anc) else 'none')
                    cnt[group][cls] += 1
                    if cls == 'self' and len(cnt['examples']) < 5:
                        cnt['examples'].append({'page': pg['key'], 'i': i, 'tag': c['tag'], 'text': c['text'][:40],
                                                'clean': [dc[i][1], dc[i][2]], 'variant': [dv[i][1], dv[i][2]]})
        res[kind] = cnt
    json.dump(res, open(f'{fx}/{env}/treated.json', 'w'), indent=1)
    print(env, {k: (v['click'], v['key'], v['pages_misaligned']) for k, v in res.items()})


if __name__ == '__main__':
    main(*sys.argv[1:4])
