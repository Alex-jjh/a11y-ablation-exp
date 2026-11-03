#!/usr/bin/env python3
"""Build a source-level defect variant of one BreakingWeb environment and measure it.

For ENV and KIND: restore the env's and shared sources from git, apply codemod.py, build
the env, then for each sampled task capture (a) the BrowserGym observation text the
AXTree agent receives and (b) a full-page screenshot; the same is captured for the clean
build first.  Then report, per task: observation lines that changed (with examples) and
the share of pixels that differ.  Sources are restored at the end.

Usage (from the BreakingWeb repo root, PYTHONPATH=.):
  variant_run.py ENV KIND N_TASKS OUT_DIR
"""
import difflib, glob, io, json, os, subprocess, sys
import numpy as np
from PIL import Image

ROOT = os.path.expanduser('~/.workspace/_refsrc/BreakingWeb')
ENVROOT = f'{ROOT}/breakingweb/environments'
NODE = os.path.expanduser('~/.local/share/mise/installs/node/24.20.0/bin')
ENVDIR = {'pp': 'patient_portal', 'rh': 'robinhood'}


def sh(cmd, cwd=ROOT):
    env = dict(os.environ, PATH=f'{NODE}:{os.path.expanduser("~/.local/bin")}:{os.environ["PATH"]}')
    r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f'FAILED: {cmd}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    return r.stdout


def restore(envname):
    sh(f'git checkout -- breakingweb/environments/{envname}/src breakingweb/environments/shared/src')


def build(envname):
    sh('pnpm build', cwd=f'{ENVROOT}/{envname}')


ROUTES = {
    'amazon': ['home', 'search?q=headphones', '@product', 'cart', 'checkout', 'orders', 'wishlist', 'settings',
               'account', 'returns', 'categories', 'deals', 'notifications', 'gift-cards', 'customer-service'],
}


def auto_routes(envname):
    """Static (parameter-free) routes declared in the env's App.tsx, max 15."""
    import re
    src = open(f'{ENVROOT}/{envname}/src/App.tsx').read()
    paths = [p.strip('/') for p in re.findall(r'<Route\s+path="([^"]*)"', src)]
    seen = []
    for p in paths:
        if p and p != 'launch' and ':' not in p and '*' not in p and p not in seen:
            seen.append(p)
    return seen[:15]


def capture(tasks, out, envname):
    """For the first task: every route of the env; for the others: the start page."""
    from breakingweb.browsergym_env import make_env
    from browsergym.utils.obs import flatten_axtree_to_str
    from urllib.parse import urlsplit
    os.makedirs(out, exist_ok=True)
    def grab(env, obs, label):
        kw = dict(extra_properties=obs.get('extra_element_properties', {}), with_clickable=True, with_visible=True, filter_with_bid_only=True)
        open(f'{out}/{label}.txt', 'w').write(flatten_axtree_to_str(obs['axtree_object'], filter_visible_only=True, **kw))
        open(f'{out}/{label}.all.txt', 'w').write(flatten_axtree_to_str(obs['axtree_object'], filter_visible_only=False, **kw))
        env.unwrapped.page.screenshot(path=f'{out}/{label}.png', full_page=True)
    for i, t in enumerate(tasks):
        env = make_env(t, headless=True)
        obs, _ = env.reset()
        grab(env, obs, t)
        if i == 0:
            page = env.unwrapped.page
            u = urlsplit(obs['url']); base = f'{u.scheme}://{u.netloc}/env/{envname}/'; q = u.query
            for r in ROUTES.get(envname) or auto_routes(envname):
                if r == '@product':
                    href = page.evaluate("() => { const a = [...document.querySelectorAll('a[href*=\"/product/\"]')][0]; return a ? a.getAttribute('href') : null }")
                    if not href:
                        continue
                    r = href.split('/env/' + envname + '/')[-1].lstrip('/').split('?')[0]
                sep = '&' if '?' in r else '?'
                page.goto(base + r + sep + q); page.wait_for_load_state('networkidle'); page.wait_for_timeout(500)
                grab(env, env.unwrapped._get_obs(), 'route__' + r.replace('/', '_').replace('?', '_').replace('=', '-'))
        env.close()


def pixdiff(a, b):
    A, B = Image.open(a).convert('RGB'), Image.open(b).convert('RGB')
    if A.size != B.size:
        return {'size_clean': A.size, 'size_variant': B.size, 'diff_share': None}
    x, y = np.asarray(A, dtype=np.int16), np.asarray(B, dtype=np.int16)
    d = (np.abs(x - y).sum(axis=2) > 30)
    return {'size': A.size, 'diff_share': round(float(d.mean()), 5)}


def main(env_id, kind, n, out):
    envname = ENVDIR.get(env_id, env_id)
    tasks = sorted(os.path.basename(p)[:-5] for p in glob.glob(f'{ROOT}/breakingweb/tasks/{envname}/*.yaml'))[:n]
    restore(envname)
    clean = f'{out}/{envname}/clean'
    if not os.path.exists(clean):
        build(envname); capture(tasks, clean, envname)
    import ast
    counts = {'env': ast.literal_eval(sh(f'{sys.executable} /tmp/amt-syn/bw-probe/codemod.py {ENVROOT}/{envname}/src {kind}').strip()),
              'shared': ast.literal_eval(sh(f'{sys.executable} /tmp/amt-syn/bw-probe/codemod.py {ENVROOT}/shared/src {kind}').strip())}
    try:
        build(envname)
        var = f'{out}/{envname}/{kind}'
        capture(tasks, var, envname)
    finally:
        restore(envname); build(envname)
    report = {'env': envname, 'kind': kind, 'codemod_counts_env': counts, 'tasks': []}
    labels = sorted(os.path.basename(p)[:-4] for p in glob.glob(f'{var}/*.txt') if not p.endswith('.all.txt'))
    for t in labels:
        if not os.path.exists(f'{clean}/{t}.txt'):
            continue
        rec = {'page': t}
        for suffix, key in (('.txt', 'visible'), ('.all.txt', 'all')):
            a = open(f'{clean}/{t}{suffix}').read().splitlines(); b = open(f'{var}/{t}{suffix}').read().splitlines()
            diff = [l for l in difflib.unified_diff(a, b, lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
            rec[key] = {'lines_clean': len(a), 'removed': sum(1 for l in diff if l[0] == '-'), 'added': sum(1 for l in diff if l[0] == '+'), 'examples': diff[:10]}
        rec['pixels'] = pixdiff(f'{clean}/{t}.png', f'{var}/{t}.png')
        report['tasks'].append(rec)
    json.dump(report, open(f'{out}/{envname}/{kind}.report.json', 'w'), indent=1)
    for r in report['tasks']:
        v, a = r['visible'], r['all']
        print(f"{r['page'][:42]:42} visible -{v['removed']}/{v['lines_clean']}  all -{a['removed']}/{a['lines_clean']}  pix {r['pixels'].get('diff_share')}")
    print('codemod:', counts)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4])
