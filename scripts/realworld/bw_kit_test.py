#!/usr/bin/env python3
"""Known-answer test of analyze.py on BreakingWeb: clean builds vs codemod variants, saved like real pages.

capture ENV OUT [--kinds k1,...] [--tasks N]
    In the checkout BW_ROOT (a private copy; never the shared clone), build ENV clean, then once
    per kind with codemod.py on the env and shared sources (variant_gate.py's build and restore
    functions), and save every page the variant gate captures (start pages of the first N tasks
    plus the env's static routes; variant_gate.ROUTES / auto_routes) with harness.save(): the
    capture snippet's JSON and the Blink MHTML. BrowserGym marks the page before each save, so
    every element carries the gate's `bid`; clean and variant builds have the same bids (gate dom
    check), which lets the evaluation align elements. Sources are restored and the env rebuilt
    clean at the end. Backend on 127.0.0.1:BW_PORT.
analyze OUT [ENV ...] [--workers W]
    analyze.py on every saved page. JSON pages are analysed with the codemod's data-amt markers
    stripped (--strip-attr data-amt), so detection cannot use them; the capture stamps keep the
    original styles. MHTML pages are analysed as saved (their CSS needs data-amt for the look).
    Writes OUT/analysis/<env>/<build>/<page>.{json,mhtml}.res.json (result + compact element list).
evaluate OUT
    Per env x kind x format, against clean:
      count_clean / count_variant   instances of the kind's signature (all pages);
      new                           instances in the variant whose element (by bid) is not an
                                    instance in clean, or is one with another signature (reddit's
                                    'Upvote' x25 is ambiguous in clean and glyph-only '▲' in names);
      explained                     new instances the codemod accounts for: the element, an
                                    ancestor or a descendant changed (tag or attributes), or, for
                                    names/ambiguous, another member of its name group changed, or,
                                    for labels, a changed element within its 3-ancestor container;
      unexplained                   new - explained: detector responses to something the codemod
                                    did not do (false positives of the known-answer test);
      unexplained_strict            new instances whose own element was not changed (names: or a
                                    member of its name group; labels: or an element in its
                                    3-ancestor container; headings: or one of 2 ancestors, since
                                    the detector reports the innermost text block; tableheads: or
                                    a cell): the stricter reading, without the generic ancestor
                                    rule (every element inside a converted <main> has a changed
                                    ancestor);
      targets                       changed elements of the kind that are rendered in the variant
                                    (names: a/button with role link/button; labels: controls whose
                                    own attributes or whose label changed; alt: img; headings: h1-h6
                                    turned div; landmarks: header/nav/main/footer/aside turned div;
                                    tableheads: tables whose th turned td; headings and landmarks
                                    only elements whose clean AX role was heading / a landmark),
                                    and how many the detector reports (names targets are split by
                                    the name-loss ladder: empty / glyph (no letter or digit left) / shared /
                                    unique-changed / kept;
                                    labels targets by whether the control's name was kept,
                                    changed or emptied);
      page verdicts                 landmarks page verdict clean -> variant.
    Writes OUT/evaluation.json and prints a table.
stripcheck OUT [--workers W]
    The JSON pages of the tag-replacing kinds (headings, landmarks, tableheads) analysed again
    without stripping data-amt; per-kind counts must equal the stripped analysis. Writes
    OUT/stripcheck.json.
"""
import argparse
import collections
import glob
import json
import multiprocessing as mp
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'probe', 'breakingweb'))
KINDS = ['names', 'labels', 'alt', 'headings', 'landmarks', 'tableheads']
NOISE_ATTR = re.compile(r'^(data-rwk-|data-amt|browsergym|aria-roledescription$|aria-description$|value$|checked$)')


# ----------------------------------------------------------------------------- capture
def _capture(envname, out, n_tasks):
    import variant_gate as vg
    import harness
    sys.path.insert(0, vg.ROOT)
    from breakingweb.browsergym_env import make_env
    from urllib.parse import urlsplit
    tasks = sorted(os.path.basename(p)[:-5] for p in glob.glob(f'{vg.ROOT}/breakingweb/tasks/{envname}/*.yaml'))[:n_tasks]
    os.makedirs(out, exist_ok=True)
    for i, t in enumerate(tasks):
        env = make_env(t, headless=True, server_port=vg.PORT)
        obs, _ = env.reset()
        page = env.unwrapped.page
        page.wait_for_timeout(300)
        env.unwrapped._get_obs()
        harness.save(page, f'{out}/{t}')
        if i == 0:
            u = urlsplit(obs['url']); base = f'{u.scheme}://{u.netloc}/env/{envname}/'; q = u.query
            for r in vg.ROUTES.get(envname) or vg.auto_routes(envname):
                if r == '@product':
                    href = page.evaluate("() => { const a = [...document.querySelectorAll('a[href*=\"/product/\"]')][0]; return a ? a.getAttribute('href') : null }")
                    if not href:
                        continue
                    r = href.split('/env/' + envname + '/')[-1].lstrip('/').split('?')[0]
                sep = '&' if '?' in r else '?'
                page.goto(base + r + sep + q); page.wait_for_load_state('networkidle'); page.wait_for_timeout(500)
                env.unwrapped._get_obs()
                harness.save(page, f'{out}/route__' + r.replace('/', '_').replace('?', '_').replace('=', '-'))
        env.close()


def cmd_capture(envname, outroot, kinds, n_tasks):
    import variant_gate as vg
    import codemod
    out = f'{outroot}/captures/{envname}'
    os.makedirs(out, exist_ok=True)
    meta_path = f'{out}/builds.json'
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}

    def cap(name):
        r = subprocess.run([sys.executable, '-I', os.path.abspath(__file__), '_capture', envname, f'{out}/{name}', '--tasks', str(n_tasks)],
                           cwd=vg.ROOT, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=vg.ROOT))
        if r.returncode:
            raise SystemExit(f'capture failed for {name}:\n{r.stderr[-3000:]}')
    vg.restore(envname)
    try:
        for name in ['clean'] + kinds:
            if name in meta:
                continue
            vg.restore(envname)
            counts = None
            if name != 'clean':
                counts = {'env': codemod.rewrite(f'{vg.ENVROOT}/{envname}/src', name), 'shared': codemod.rewrite(f'{vg.ENVROOT}/shared/src', name)}
            ok, log = vg.build(envname)
            if not ok:
                raise SystemExit(f'{name} build failed:\n{log}')
            cap(name)
            meta[name] = {'codemod': counts}
            vg.restore(envname)
            json.dump(meta, open(meta_path, 'w'), indent=1)
            print(envname, name, 'captured', flush=True)
    finally:
        vg.restore(envname)
        vg.build(envname)


# ----------------------------------------------------------------------------- analyze
def _one(job):
    path, dest, strip = job
    import analyze
    sys.setrecursionlimit(10000)
    try:
        res, r, items = analyze.analyze_file(path, examples=3, strip_attrs=strip)
    except Exception as e:  # noqa: BLE001
        return path, f'{type(e).__name__}: {e}'
    pg = analyze.Page(r)
    els = []
    for b in pg.order:
        e = pg.els[b]
        els.append({'b': b, 'o': e['attrs'].get('data-rwk-obid'), 't': e['tag'], 'p': e['parent'],
                    'a': {k: v for k, v in e['attrs'].items() if not NOISE_ATTR.match(k)},
                    'h': pg.hidden(b), 'r': pg.role(b), 'n': pg.name(b), 'lc': e.get('label_control')})
    res['items'] = {k: [{x: i.get(x) for x in ('bid', 'orig_bid', 'signature', 'subtype', 'verdict', 'tag', 'html', 'accessible_name', 'tree_line')}
                        for i in v] for k, v in items.items()}
    res['els'] = els
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump(res, open(dest, 'w'))
    return path, None


def cmd_analyze(outroot, workers, envs=None):
    jobs = []
    for f in sorted(glob.glob(f'{outroot}/captures/*/*/*.rwk.json')) + sorted(glob.glob(f'{outroot}/captures/*/*/*.mhtml')):
        env, build, name = f.split('/')[-3:]
        if envs and env not in envs:
            continue
        fmt = 'json' if f.endswith('.rwk.json') else 'mhtml'
        stem = re.sub(r'\.(rwk\.json|mhtml)$', '', name)
        dest = f'{outroot}/analysis/{env}/{build}/{stem}.{fmt}.res.json'
        if not os.path.exists(dest):
            jobs.append((f, dest, ['data-amt'] if fmt == 'json' else []))
    print(len(jobs), 'pages to analyse', flush=True)
    with mp.get_context('spawn').Pool(workers) as pool:
        for i, (path, err) in enumerate(pool.imap_unordered(_one, jobs), 1):
            if err:
                print('ERROR', path, err, flush=True)
            if i % 50 == 0:
                print(i, 'done', flush=True)


# ----------------------------------------------------------------------------- evaluate
class Els:
    def __init__(self, res):
        self.by_b = {e['b']: e for e in res['els']}
        self.by_o = {e['o']: e for e in res['els'] if e['o'] is not None}
        self.kids = collections.defaultdict(list)
        for e in res['els']:
            if e['p'] is not None:
                self.kids[e['p']].append(e['b'])

    def anc(self, o, n=10**6):
        e = self.by_o.get(o); out = []
        while e and e['p'] is not None and len(out) < n:
            e = self.by_b.get(e['p'])
            if e and e['o'] is not None:
                out.append(e['o'])
        return out

    def desc(self, o):
        e = self.by_o.get(o)
        if not e:
            return []
        st, out = list(self.kids.get(e['b'], [])), []
        while st:
            b = st.pop(); x = self.by_b[b]
            if x['o'] is not None:
                out.append(x['o'])
            st.extend(self.kids.get(b, []))
        return out


def _attrs(a):
    # URL query values differ between builds (BreakingWeb session ids) and, in JSON captures, are
    # salted hashes that differ per capture; compare URLs without them
    return {k: (re.split(r'[?#]', x, 1)[0] if k in ('href', 'src', 'action', 'srcset') else x) for k, x in a.items()}


def changed_set(c, v):
    ch = set()
    for o, ve in v.by_o.items():
        ce = c.by_o.get(o)
        if ce is None or ce['t'] != ve['t'] or _attrs(ce['a']) != _attrs(ve['a']):
            ch.add(o)
    return ch


def evaluate_pair(cres, vres, kind):
    if ':' in kind:   # 'headings:strong' = the headings kind restricted to its heading-styled-text tier
        base, tier = kind.split(':')
        sig = {'strong': 'heading-styled-text', 'weak': 'bold-short-text'}[tier]
        def only(res):
            r = dict(res); r['items'] = dict(res['items']); r['items'][base] = [i for i in res['items'][base] if i['signature'] == sig]
            r['items'][kind] = r['items'][base]; r['kinds'] = dict(res['kinds']); r['kinds'][kind] = res['kinds'][base]
            return r
        out = evaluate_pair(only(cres), only(vres), base)
        return out
    c, v = Els(cres), Els(vres)
    ch = changed_set(c, v)
    Dc = {(i['orig_bid'], i['signature']) for i in cres['items'][kind]}
    vitems = {i['orig_bid']: i for i in vres['items'][kind]}
    new = [o for o, i in vitems.items() if (o, i['signature']) not in Dc]   # a new element, or a new signature on it
    groups = collections.defaultdict(set)
    for i in vres['items']['names']:
        if i['signature'] == 'ambiguous':
            groups[(v.by_o[i['orig_bid']]['r'], (i['accessible_name'] or '').casefold())].add(i['orig_bid'])

    def explained(o):
        if o in ch or any(a in ch for a in v.anc(o)) or any(d in ch for d in v.desc(o)):
            return True
        if kind == 'names' and vitems[o]['signature'] == 'ambiguous':
            g = groups.get((v.by_o[o]['r'], (vitems[o]['accessible_name'] or '').casefold()), set())
            return any(x in ch for x in g)
        if kind == 'labels':
            for a in v.anc(o, 3):
                if any(d in ch for d in v.desc(a)):
                    return True
        return False
    unexpl = [o for o in new if not explained(o)]

    def strict(o):   # the change sits on the instance itself (kind-specific reach)
        if o in ch:
            return True
        if kind == 'names' and vitems[o]['signature'] == 'ambiguous':
            g = groups.get((v.by_o[o]['r'], (vitems[o]['accessible_name'] or '').casefold()), set())
            return any(x in ch for x in g)
        if kind == 'labels':
            return any(any(d in ch for d in v.desc(a)) for a in v.anc(o, 3))
        if kind == 'headings':
            return any(a in ch for a in v.anc(o, 2))
        if kind == 'tableheads':
            return any(d in ch for d in v.desc(o))
        return False
    unstrict = [o for o in new if not strict(o)]
    # targets
    targets, ladder = [], collections.Counter()
    if kind == 'names':
        names_v = collections.Counter((e['r'], e['n'].casefold()) for e in v.by_o.values() if e['r'] in ('button', 'link') and not e['h'] and e['n'])
        for o in ch:
            e = v.by_o[o]
            if e['t'] in ('a', 'button') and e['r'] in ('button', 'link') and not e['h']:
                ce = c.by_o.get(o)
                if not e['n']:
                    cls = 'empty'
                elif not any(ch.isalnum() for ch in e['n']):
                    cls = 'glyph'
                elif ce and ce['n'] == e['n']:
                    cls = 'kept'
                elif names_v[(e['r'], e['n'].casefold())] > 1:
                    cls = 'shared'
                else:
                    cls = 'unique-changed'
                ladder[(cls, o in vitems)] += 1
                targets.append(o)
    elif kind == 'labels':
        relabelled = set()
        for o in ch:
            ce = c.by_o.get(o)
            if ce and ce['t'] == 'label' and ce['lc']:
                ctl = c.by_b.get(ce['lc'])
                if ctl and ctl['o']:
                    relabelled.add(ctl['o'])
        for o in set(x for x in ch if v.by_o[x]['t'] in ('input', 'textarea', 'select')) | relabelled:
            e = v.by_o.get(o)
            if e and not e['h'] and not (e['t'] == 'input' and e['a'].get('type', 'text').lower() in ('hidden', 'submit', 'reset', 'button', 'image')):
                targets.append(o)
                ce = c.by_o.get(o)
                cls = 'name-kept' if ce and ce['n'] == e['n'] else ('name-empty' if not e['n'] else 'name-changed')
                ladder[(cls, o in vitems)] += 1
    elif kind == 'alt':
        targets = [o for o in ch if v.by_o[o]['t'] == 'img' and not v.by_o[o]['h']]
    elif kind in ('headings', 'landmarks'):
        tags = {'headings': {f'h{i}' for i in range(1, 7)}, 'landmarks': {'header', 'nav', 'main', 'footer', 'aside'}}[kind]
        roles = {'headings': {'heading'}, 'landmarks': {'banner', 'navigation', 'main', 'contentinfo', 'complementary', 'search', 'region', 'form'}}[kind]
        targets = [o for o in ch if c.by_o.get(o) and c.by_o[o]['t'] in tags and c.by_o[o]['r'] in roles and not v.by_o[o]['h']]
    elif kind == 'tableheads':
        tabs = set()
        for o in ch:
            if c.by_o.get(o) and c.by_o[o]['t'] == 'th':
                for a in v.anc(o):
                    if v.by_o[a]['t'] == 'table':
                        tabs.add(a); break
        targets = [o for o in tabs if not v.by_o[o]['h']]
    # a heading target counts as detected when the detector reports it or a descendant (the
    # detector reports the innermost block that carries the text, e.g. <h1><div>Title</div></h1>)
    hit = (lambda o: o in vitems or any(d in vitems for d in v.desc(o))) if kind == 'headings' else (lambda o: o in vitems)
    det_t = [o for o in targets if hit(o)]
    missed = [o for o in targets if not hit(o)]
    return {'count_clean': len(Dc), 'count_variant': len(vitems), 'new': len(new), 'explained': len(new) - len(unexpl),
            'unexplained': len(unexpl), 'unexplained_examples': [vitems[o] for o in unexpl[:3]],
            'unexplained_strict': len(unstrict), 'unexplained_strict_examples': [vitems[o] for o in unstrict[:3]],
            'targets': len(targets), 'targets_detected': len(det_t),
            'missed_examples': [{'html': (vres['items_lookup'].get(o) or {}).get('html') if 'items_lookup' in vres else None, 'tag': v.by_o[o]['t'],
                                 'name': v.by_o[o]['n'], 'role': v.by_o[o]['r'], 'attrs': {k: x[:60] for k, x in v.by_o[o]['a'].items()}} for o in missed[:3]],
            'ladder': {f'{k[0]}|{"detected" if k[1] else "not"}': n for k, n in ladder.items()},
            'new_by_verdict': dict(collections.Counter(vitems[o]['verdict'] for o in new)),
            'new_by_signature': dict(collections.Counter(vitems[o]['signature'] for o in new)),
            'page_verdict': [cres['kinds'][kind]['page_verdict'], vres['kinds'][kind]['page_verdict']],
            'changed_elements': len(ch)}


def cmd_evaluate(outroot):
    ev = {'cells': {}, 'clean_examples': {}, 'format_agreement': {}}
    for envdir in sorted(glob.glob(f'{outroot}/analysis/*')):
        env = os.path.basename(envdir)
        clean = {os.path.basename(f)[:-9]: f for f in glob.glob(f'{envdir}/clean/*.res.json')}
        cache = {}

        def load(f):
            if f not in cache:
                cache[f] = json.load(open(f))
            return cache[f]
        # clean detections (natural instances) and JSON-vs-MHTML agreement
        agree = collections.Counter()
        for key, f in clean.items():
            if key.endswith('.json'):
                r = load(f)
                for k in KINDS:
                    for i in r['items'][k]:
                        ev['clean_examples'].setdefault(f'{env}|{k}', []).append({'page': key, **{x: i[x] for x in ('signature', 'verdict', 'html', 'accessible_name', 'tree_line')}})
        for build in sorted(os.listdir(envdir)):
            for f in glob.glob(f'{envdir}/{build}/*.json.res.json'):
                m = f.replace('.json.res.json', '.mhtml.res.json')
                if os.path.exists(m):
                    a, b = load(f), load(m)
                    for k in KINDS:
                        agree[(k, a['kinds'][k]['count'] == b['kinds'][k]['count'])] += 1
        ev['format_agreement'][env] = {k: f"{agree[(k, True)]}/{agree[(k, True)] + agree[(k, False)]}" for k in KINDS}
        for kind in KINDS + ['headings:strong']:
            vdir = f'{envdir}/{kind.split(":")[0]}'
            if not os.path.isdir(vdir):
                continue
            for fmt in ('json', 'mhtml'):
                tot = collections.Counter(); pages = 0; per_page = []; ladder = collections.Counter(); unex, missed = [], []
                pv = collections.Counter(); nbv = collections.Counter(); nbs = collections.Counter()
                for key, cf in sorted(clean.items()):
                    if not key.endswith('.' + fmt):
                        continue
                    vf = f'{vdir}/{os.path.basename(cf)}'
                    if not os.path.exists(vf):
                        continue
                    pages += 1
                    r = evaluate_pair(load(cf), load(vf), kind)
                    for x in ('count_clean', 'count_variant', 'new', 'explained', 'unexplained', 'unexplained_strict', 'targets', 'targets_detected', 'changed_elements'):
                        tot[x] += r[x]
                    ladder.update(r['ladder']); nbv.update(r['new_by_verdict']); nbs.update(r['new_by_signature'])
                    pv[f'{r["page_verdict"][0]}->{r["page_verdict"][1]}'] += 1
                    unex += [{'page': key, **u} for u in r['unexplained_examples'] + r['unexplained_strict_examples']]
                    missed += [{'page': key, **u} for u in r['missed_examples']]
                    per_page.append({'page': key, 'clean': r['count_clean'], 'variant': r['count_variant'], 'new': r['new'],
                                     'targets': r['targets'], 'detected': r['targets_detected'], 'changed': r['changed_elements']})
                ev['cells'][f'{env}|{kind}|{fmt}'] = {'pages': pages, **dict(tot), 'ladder': dict(ladder), 'new_by_verdict': dict(nbv),
                                                     'new_by_signature': dict(nbs), 'page_verdicts': dict(pv),
                                                     'pages_variant_gt_clean': sum(1 for p in per_page if p['variant'] > p['clean']),
                                                     'pages_with_targets': sum(1 for p in per_page if p['targets']),
                                                     'pages_with_targets_detected': sum(1 for p in per_page if p['targets'] and p['variant'] > p['clean']),
                                                     'unexplained_examples': unex[:5], 'missed_examples': missed[:5], 'per_page': per_page}
        cache.clear()
    json.dump(ev, open(f'{outroot}/evaluation.json', 'w'), indent=1)
    print(f'{"cell":32s} pages clean var new expl unexpl targets det  pages(tgt/det)')
    for k, c in ev['cells'].items():
        print(f'{k:32s} {c["pages"]:5d} {c.get("count_clean",0):5d} {c.get("count_variant",0):4d} {c.get("new",0):4d} {c.get("explained",0):4d} '
              f'{c.get("unexplained",0):6d} {c.get("targets",0):7d} {c.get("targets_detected",0):4d}  {c["pages_with_targets"]}/{c["pages_with_targets_detected"]}')
    print(json.dumps(ev['format_agreement']))


def _nostrip(job):
    path, = job
    import analyze
    sys.setrecursionlimit(10000)
    res, _, _ = analyze.analyze_file(path, examples=0)
    return path, {k: res['kinds'][k]['count'] for k in KINDS}


def cmd_stripcheck(outroot, workers):
    """JSON variants of the tag-replacing kinds analysed again WITHOUT stripping data-amt; the
    counts must equal the stripped analysis (detection does not depend on the codemod's markers)."""
    files = [f for f in sorted(glob.glob(f'{outroot}/captures/*/*/*.rwk.json')) if f.split('/')[-2] in ('headings', 'landmarks', 'tableheads')]
    diff, n = [], 0
    with mp.get_context('spawn').Pool(workers) as pool:
        for path, counts in pool.imap_unordered(_nostrip, [(f,) for f in files]):
            env, build, name = path.split('/')[-3:]
            stored = json.load(open(f"{outroot}/analysis/{env}/{build}/{name.replace('.rwk.json', '')}.json.res.json"))
            n += 1
            for k in KINDS:
                if stored['kinds'][k]['count'] != counts[k]:
                    diff.append({'page': f'{env}/{build}/{name}', 'kind': k, 'stripped': stored['kinds'][k]['count'], 'kept': counts[k]})
    out = {'pages': n, 'kind_counts_compared': n * len(KINDS), 'differences': diff}
    json.dump(out, open(f'{outroot}/stripcheck.json', 'w'), indent=1)
    print(json.dumps({'pages': n, 'differences': len(diff)}), diff[:10])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--kinds', default=','.join(KINDS))
    ap.add_argument('--tasks', type=int, default=2)
    ap.add_argument('--workers', type=int, default=6)
    a = ap.parse_args()
    if a.cmd == '_capture':
        _capture(a.args[0], a.args[1], a.tasks)
    elif a.cmd == 'capture':
        cmd_capture(a.args[0], a.args[1], a.kinds.split(','), a.tasks)
    elif a.cmd == 'analyze':
        cmd_analyze(a.args[0], a.workers, a.args[1:] or None)
    elif a.cmd == 'evaluate':
        cmd_evaluate(a.args[0])
    elif a.cmd == 'stripcheck':
        cmd_stripcheck(a.args[0], a.workers)
