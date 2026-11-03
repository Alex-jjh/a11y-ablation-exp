#!/usr/bin/env python3
"""Variant QA gate: does a source-level defect variant change only the target information?

For one BreakingWeb environment, the script builds the clean app several times (rebuilds give
the noise floor) and each defect variant once (codemod.py on the env and shared sources),
captures every page (2 task start pages plus the env's static routes, as variant_run.py),
and then judges each variant against the first clean build, page by page.

A cell (env x kind) PASSES only if every page passes every gating check:
  build      `pnpm build` exits 0; for tag-replacing kinds the built CSS contains the
             amt-ua layer (the look-keeping rules survived minification).
  console    no console error or page error that no clean build had on that page
             (messages normalised for asset hashes and line:column).
  size       full-page screenshot size and document scrollWidth/scrollHeight equal clean.
  pixels     a pixel is changed if the sum over RGB of |difference| > TOL (30, as on
             2026-10-29). Pixels inside the boxes of loaded <img> elements are left out: their
             raster output varied between identical clean builds (amazon product photos), and
             the images themselves are covered by the dom check (same src and attributes),
             the layout check (same box, same overflow) and the load flag. On the rest:
             (i) the changed share must not exceed the env's noise floor (max share over all
             clean-vs-clean pairs and pages); (ii) no changed pixel may lie outside the page's
             noise region (8x8 blocks changed in any clean-vs-clean pair, grown by one block).
             Reported only: the share inside images, the verdict of the same rule with images
             included (strict_rule_ok, the rule of the first full run), the exact (tolerance 0)
             share and a block SSIM.
  layout     every element's page box (getBoundingClientRect + scroll) equals clean, except
             elements whose box differs between clean builds.
  dom        elements align one to one with clean (same count, same bids); the only tag and
             attribute changes are the kind's own (table KIND_DOM below); text unchanged.
  obs        the BrowserGym observation (viewport text and full text, the flattening of
             BreakingWeb's agent) differs from clean only as the kind's rule allows. Targets
             are the elements the dom check found changed, looked up by bid; the rule never
             searches by the removed role or name. Rules:
               none        identical.
               headings    a target `heading` line is removed; its subtree moves up one
                           level; StaticText lines may appear in its place if their text is
                           part of the heading's name.
               landmarks   as headings for target lines with a landmark role (banner,
                           navigation, main, contentinfo, complementary, search, region,
                           form); a target may instead stay as a neutral line (generic,
                           Section, group) with the same bid.
               names/labels/alt  only the name of target lines may change, plus the name of
                           their ancestors whose role takes its name from content (ARIA
                           accname: button, cell, checkbox, columnheader, gridcell, heading,
                           link, menuitem*, option, radio, row, rowheader, switch, tab,
                           tooltip, treeitem; Chrome's LabelText); labels: a target label may also
                           lose BrowserGym's `clickable` flag (counted as label_clickable_lost:
                           clicking the text no longer focuses the control). StaticText children of
                           those lines may appear or vanish (BrowserGym hides StaticText
                           contained in the parent's name). labels: a control whose <label
                           for> was removed is a target. alt: target image lines may appear or
                           vanish (img alt="" is presentational; without alt it is an image).
               tableheads  target columnheader/rowheader lines become gridcell/cell lines
                           with the same bid and name.
             If clean builds differ in the observation of a page, the page is unresolved and
             fails (fail closed).
Reported, not gating: dose (DOM targets, observation lines changed), residual target
elements and roles left in the variant, block SSIM, exact-pixel share, codemod risk counts.

Usage (uses the BreakingWeb venv python; cwd and PYTHONPATH = the checkout being built):
  env BW_ROOT=<checkout> (default ~/.workspace/_refsrc/BreakingWeb), BW_PORT=<backend port, 127.0.0.1>
  variant_gate.py capture ENV OUT [--clean N] [--kinds k1,k2] [--tasks 2]
  variant_gate.py evaluate ENV OUT            -> OUT/<env>/gate.json, prints the verdicts
  variant_gate.py summary OUT                 -> OUT/summary.json (all envs), prints the table
ENV: amazon booking gmail lms patient_portal reddit robinhood. OUT e.g. /tmp/amt-syn/bw-gate.
Captures go to OUT/<env>/<build>/<page>.{txt,all.txt,png,dom.json}; builds are clean0..cleanN-1
and the kinds. Sources are restored with git checkout after every variant and at the end.
"""
import argparse
import ast
import collections
import difflib
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemod  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
# BW_ROOT: the BreakingWeb checkout to build in. Use a private copy when another process serves
# the main checkout (builds write breakingweb/static/envs, which the server serves).
ROOT = os.environ.get('BW_ROOT', os.path.expanduser('~/.workspace/_refsrc/BreakingWeb'))
PORT = int(os.environ.get('BW_PORT', '8080'))
# codemod used for kinds written KIND@old (positive control): the 2026-10-29 version from git
ALT_CODEMOD = os.environ.get('ALT_CODEMOD', '/tmp/amt-syn/bw-gate/codemod_2026-10-29.py')
ENVROOT = f'{ROOT}/breakingweb/environments'
NODE = os.path.expanduser('~/.local/share/mise/installs/node/24.20.0/bin')
KINDS = ['none', 'landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads']
TOL = 30
BLOCK = 8

ROUTES = {'amazon': ['home', 'search?q=headphones', '@product', 'cart', 'checkout', 'orders', 'wishlist', 'settings',
                     'account', 'returns', 'categories', 'deals', 'notifications', 'gift-cards', 'customer-service']}


# ----------------------------------------------------------------------------- build
def sh(cmd, cwd=ROOT, check=True):
    env = dict(os.environ, PATH=f'{NODE}:{os.path.expanduser("~/.local/bin")}:{os.environ["PATH"]}',
               BREAKINGWEB_AUTO_BUILD_FRONTENDS='0')
    r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, env=env)
    if check and r.returncode:
        raise SystemExit(f'FAILED: {cmd}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    return r


def restore(envname):
    sh(f'git checkout -- breakingweb/environments/{envname}/src breakingweb/environments/shared/src')


def build(envname):
    r = sh('pnpm build', cwd=f'{ENVROOT}/{envname}', check=False)
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def built_css(envname):
    return ''.join(open(f).read() for f in glob.glob(f'{ROOT}/breakingweb/static/envs/{envname}/assets/*.css'))


def auto_routes(envname):
    src = open(f'{ENVROOT}/{envname}/src/App.tsx').read()
    seen = []
    for p in (p.strip('/') for p in re.findall(r'<Route\s+path="([^"]*)"', src)):
        if p and p != 'launch' and ':' not in p and '*' not in p and p not in seen:
            seen.append(p)
    return seen[:15]


# ----------------------------------------------------------------------------- capture
DOM_JS = '''() => {
  const sx = window.scrollX, sy = window.scrollY, d = document.documentElement;
  return {width: d.scrollWidth, height: d.scrollHeight, els: [...document.querySelectorAll('*')].filter(e => e.id !== 'amt-capture-noscrollbar').map(e => {
    const a = {};
    for (const at of e.attributes) if (!at.name.startsWith('browsergym') && at.name !== 'bid') a[at.name] = at.value;
    const r = e.getBoundingClientRect();
    let t = ''; for (const c of e.childNodes) if (c.nodeType === 3) t += c.data;
    return [e.getAttribute('bid'), e.tagName, a, [r.x + sx, r.y + sy, r.width, r.height].map(v => Math.round(v * 10) / 10),
            t.replace(/\\s+/g, ' ').trim().slice(0, 200),
            e.tagName === 'IMG' ? (e.complete && e.naturalWidth > 0) : null,
            [e.scrollWidth > e.clientWidth, e.scrollHeight > e.clientHeight]];
  })};
}'''
CONSOLE = []


def _patch_console():
    from breakingweb.browsergym_task import BreakingWebTask
    if getattr(BreakingWebTask, '_amt_patched', False):
        return
    orig = BreakingWebTask.setup

    def setup(self, page):
        page.on('console', lambda m: CONSOLE.append({'type': m.type, 'text': m.text}) if m.type in ('error', 'warning') else None)
        page.on('pageerror', lambda e: CONSOLE.append({'type': 'pageerror', 'text': str(e)}))
        return orig(self, page)
    BreakingWebTask.setup = setup
    BreakingWebTask._amt_patched = True


SEGMENT = 8192


def shoot(page, path, width, height):
    """Full-page screenshot; pages taller than SEGMENT px are captured as clipped segments and
    stitched, because a single capture of a very tall page (booking reviews, 109,230 px) came back
    unpainted below the first ~1,000 px in some builds."""
    if height <= SEGMENT:
        page.screenshot(path=path, full_page=True)
        return
    import io
    parts = []
    for y in range(0, height, SEGMENT):
        h = min(SEGMENT, height - y)
        png = page.screenshot(full_page=True, clip={'x': 0, 'y': y, 'width': width, 'height': h})
        parts.append(Image.open(io.BytesIO(png)).convert('RGB'))
    img = Image.new('RGB', (parts[0].width, sum(p.height for p in parts)))
    y = 0
    for p in parts:
        img.paste(p, (0, y)); y += p.height
    img.save(path)


def capture(envname, out, n_tasks):
    sys.path.insert(0, ROOT)
    _patch_console()
    from breakingweb.browsergym_env import make_env
    from browsergym.utils.obs import flatten_axtree_to_str
    from urllib.parse import urlsplit
    tasks = sorted(os.path.basename(p)[:-5] for p in glob.glob(f'{ROOT}/breakingweb/tasks/{envname}/*.yaml'))[:n_tasks]
    os.makedirs(out, exist_ok=True)

    def grab(env, obs, label):
        kw = dict(extra_properties=obs.get('extra_element_properties', {}), with_clickable=True, with_visible=True,
                  filter_with_bid_only=True)
        open(f'{out}/{label}.txt', 'w').write(flatten_axtree_to_str(obs['axtree_object'], filter_visible_only=True, **kw))
        open(f'{out}/{label}.all.txt', 'w').write(flatten_axtree_to_str(obs['axtree_object'], filter_visible_only=False, **kw))
        page = env.unwrapped.page
        # Playwright hides scrollbars during a full-page capture, and whether a scrollbar is still
        # painted (and counted in the image size) is a race. Hide them first, for the DOM boxes and
        # the screenshot alike, and wait two frames; the observation above is taken before this.
        cdp = page.context.new_cdp_session(page)
        cdp.send('Emulation.setScrollbarsHidden', {'hidden': True})
        # inner overflow scrollbars are not covered by the emulation and were still painted in some
        # builds only (booking home); remove them with a capture-only style, the same for every build.
        # Overflow itself stays checked: the DOM dump records each element's overflow state.
        page.evaluate("""() => { const s = document.createElement('style'); s.id = 'amt-capture-noscrollbar';
            s.textContent = '*::-webkit-scrollbar{width:0!important;height:0!important;display:none!important}';
            document.head.appendChild(s); }""")
        page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
        page.wait_for_timeout(300)
        dom = page.evaluate(DOM_JS)
        dom['console'] = list(CONSOLE); CONSOLE.clear()
        dom['url'] = page.url
        json.dump(dom, open(f'{out}/{label}.dom.json', 'w'))
        shoot(page, f'{out}/{label}.png', dom['width'], dom['height'])
        page.evaluate("() => { const s = document.getElementById('amt-capture-noscrollbar'); if (s) s.remove(); }")
        cdp.send('Emulation.setScrollbarsHidden', {'hidden': False})
        cdp.detach()

    for i, t in enumerate(tasks):
        CONSOLE.clear()
        env = make_env(t, headless=True, server_port=PORT)
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


def capture_subprocess(envname, out, n_tasks):
    """Capture in a fresh process: BreakingWeb's client checks that the server's manifest
    fingerprint equals the one it computed at import, and the manifest marks an env stale
    when its sources (shared/src included) are newer than its bundle, so a process that
    imported the app before a codemod run would refuse every later server."""
    r = subprocess.run([sys.executable, os.path.abspath(__file__), '_capture', envname, out, '--tasks', str(n_tasks)],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'capture failed for {out}:\n{r.stderr[-3000:]}')


def cmd_capture(envname, outroot, n_clean, kinds, n_tasks):
    out = f'{outroot}/{envname}'
    os.makedirs(out, exist_ok=True)
    meta_path = f'{out}/builds.json'
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    restore(envname)
    try:
        for i in range(n_clean):
            name = f'clean{i}'
            if name in meta:
                continue
            ok, log = build(envname)
            if not ok:
                raise SystemExit(f'clean build failed:\n{log}')
            capture_subprocess(envname, f'{out}/{name}', n_tasks)
            meta[name] = {'build_ok': True}
            json.dump(meta, open(meta_path, 'w'), indent=1)
        for kind in kinds:
            if kind in meta:
                continue
            restore(envname)
            if '@' in kind:  # positive control: another codemod version, e.g. headings@old
                base = kind.split('@')[0]
                counts = {d: ast.literal_eval(sh(f'{sys.executable} {ALT_CODEMOD} {ENVROOT}/{d}/src {base}').stdout.strip())
                          for d in (envname, 'shared')}
            else:
                counts = {'env': codemod.rewrite(f'{ENVROOT}/{envname}/src', kind),
                          'shared': codemod.rewrite(f'{ENVROOT}/shared/src', kind)}
            ok, log = build(envname)
            rec = {'build_ok': ok, 'codemod': counts, 'build_log_tail': log[-1500:]}
            if ok:
                css = built_css(envname)
                rec['css_layer_in_build'] = 'amt-ua' in css
                rec['css_has_where_guard'] = ':where([data-amt' in css
                capture_subprocess(envname, f'{out}/{kind}', n_tasks)
            meta[kind] = rec
            restore(envname)
            json.dump(meta, open(meta_path, 'w'), indent=1)
    finally:
        restore(envname)
        build(envname)


# ----------------------------------------------------------------------------- pixels
def load_rgb(p):
    return np.asarray(Image.open(p).convert('RGB'))


def changed_mask(a, b, tol):
    m = np.zeros(a.shape[:2], bool)
    for y in range(0, a.shape[0], 2048):
        d = np.abs(a[y:y + 2048].astype(np.int16) - b[y:y + 2048].astype(np.int16)).sum(axis=2)
        m[y:y + 2048] = d > tol
    return m


def blocks(m):
    H, W = m.shape
    Hp, Wp = -(-H // BLOCK) * BLOCK, -(-W // BLOCK) * BLOCK
    p = np.zeros((Hp, Wp), bool); p[:H, :W] = m
    return p.reshape(Hp // BLOCK, BLOCK, Wp // BLOCK, BLOCK).any(axis=(1, 3))


def grow(bm):
    g = bm.copy()
    g[1:] |= bm[:-1]; g[:-1] |= bm[1:]
    g2 = g.copy(); g2[:, 1:] |= g[:, :-1]; g2[:, :-1] |= g[:, 1:]
    return g2


def image_mask(dom, shape):
    """Pixels inside the boxes of loaded <img> elements (page coordinates = screenshot pixels)."""
    m = np.zeros(shape[:2], bool)
    for e in dom['els']:
        if e[1] == 'IMG' and len(e) > 5 and e[5]:
            x, y, w, h = e[3]
            x0, y0 = max(0, int(np.floor(x))), max(0, int(np.floor(y)))
            x1, y1 = min(shape[1], int(np.ceil(x + w))), min(shape[0], int(np.ceil(y + h)))
            if x1 > x0 and y1 > y0:
                m[y0:y1, x0:x1] = True
    return m


def block_ssim(a, b):
    """SSIM on non-overlapping 8x8 grey blocks; returns (mean, min over 64x64 tiles of the block mean)."""
    def grey(x):
        return x[..., 0] * 0.299 + x[..., 1] * 0.587 + x[..., 2] * 0.114   # float64: float32 E[xy]-E[x]E[y] gave SSIM(A,A) < 1
    H, W = a.shape[:2]; H8, W8 = H // BLOCK * BLOCK, W // BLOCK * BLOCK
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    vals = []
    for y in range(0, H8, 1024):
        x1 = grey(a[y:min(y + 1024, H8), :W8]); x2 = grey(b[y:min(y + 1024, H8), :W8])
        h = x1.shape[0]
        r1 = x1.reshape(h // BLOCK, BLOCK, W8 // BLOCK, BLOCK); r2 = x2.reshape(h // BLOCK, BLOCK, W8 // BLOCK, BLOCK)
        m1, m2 = r1.mean((1, 3)), r2.mean((1, 3))
        d1, d2 = r1 - m1[:, None, :, None], r2 - m2[:, None, :, None]
        v1, v2 = (d1 * d1).mean((1, 3)), (d2 * d2).mean((1, 3))
        cov = (d1 * d2).mean((1, 3))
        vals.append(((2 * m1 * m2 + C1) * (2 * cov + C2)) / ((m1 ** 2 + m2 ** 2 + C1) * (v1 + v2 + C2)))
    s = np.concatenate(vals)
    th, tw = s.shape[0] // 8 * 8, s.shape[1] // 8 * 8
    tiles = s[:th, :tw].reshape(th // 8, 8, tw // 8, 8).mean((1, 3)) if th and tw else s
    return round(float(s.mean()), 5), round(float(tiles.min()), 5)


# ----------------------------------------------------------------------------- observation
LINE = re.compile(r'^(\t*)(?:\[([^\]]+)\] )?(\S+)(.*)$')
NAME_FROM_CONTENT = {'button', 'cell', 'checkbox', 'columnheader', 'gridcell', 'heading', 'link', 'menuitem',
                     'menuitemcheckbox', 'menuitemradio', 'option', 'radio', 'row', 'rowheader', 'switch', 'tab',
                     'tooltip', 'treeitem', 'LabelText', 'StaticText'}
REMOVE_ROLES = {'headings': {'heading'},
                'landmarks': {'banner', 'navigation', 'main', 'contentinfo', 'complementary', 'search', 'region', 'form'}}
NEUTRAL = {'generic', 'Section', 'group'}
CELL_ROLES = {'columnheader', 'rowheader', 'gridcell', 'cell'}
IMAGE_ROLES = {'image', 'img', 'presentation', 'none'}


class Node:
    __slots__ = ('depth', 'bid', 'role', 'name', 'rest', 'parent', 'children')


def parse_obs(text):
    nodes, stack = [], []
    for line in text.split('\n'):
        if not line.strip():
            continue
        m = LINE.match(line)
        n = Node(); n.depth = len(m.group(1)); n.bid = m.group(2); n.role = m.group(3); rest = m.group(4)
        n.name = None
        if rest[:2] in (" '", ' "'):
            q, i = rest[1], 2
            while i < len(rest) and rest[i] != q:
                i += 2 if rest[i] == '\\' else 1
            n.name = ast.literal_eval(rest[1:i + 1]); rest = rest[i + 1:]
        n.rest = rest; n.children = []
        while stack and stack[-1].depth >= n.depth:
            stack.pop()
        n.parent = stack[-1] if stack else None
        if n.parent:
            n.parent.children.append(n)
        stack.append(n); nodes.append(n)
    return nodes


def diff_opcodes(a, b):
    """Non-equal blocks (i1, i2, j1, j2) between two line lists, from git's histogram diff
    (difflib's SequenceMatcher is near-quadratic on long, repetitive observations)."""
    import tempfile
    if a == b:
        return []
    with tempfile.TemporaryDirectory() as d:
        open(f'{d}/a', 'w').write('\n'.join(a) + '\n'); open(f'{d}/b', 'w').write('\n'.join(b) + '\n')
        r = subprocess.run(['git', 'diff', '--no-index', '--no-color', '--diff-algorithm=histogram', '-U0', f'{d}/a', f'{d}/b'],
                           capture_output=True, text=True)
    ops = []
    for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', r.stdout, re.M):
        a0, al, b0, bl = int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)
        i1 = a0 if al == 0 else a0 - 1; j1 = b0 if bl == 0 else b0 - 1
        ops.append((i1, i1 + al, j1, j1 + bl))
    return ops


def norm_ws(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def normalize(nodes, kind, targets):
    """-> list of (key, depth, node, placeholder?) after the kind's allowed edits are abstracted."""
    name_free = set()   # nodes whose name may change
    if kind in ('names', 'labels', 'alt'):
        for n in nodes:
            if n.bid in targets:
                name_free.add(id(n)); p = n.parent
                while p is not None:
                    if p.role in NAME_FROM_CONTENT:
                        name_free.add(id(p))
                    p = p.parent
    out = []

    def visit(n, depth):
        splice = kind in REMOVE_ROLES and n.bid in targets and (n.role in REMOVE_ROLES[kind] or n.role in NEUTRAL)
        if splice:
            out.append((f'<<T:{n.bid}>>', depth, n, True))
            for c in n.children:
                visit(c, depth)
            return
        if n.role == 'StaticText' and n.parent is not None and id(n.parent) in name_free:
            return
        role, name = n.role, n.name
        if kind == 'tableheads' and n.bid in targets and role in CELL_ROLES:
            role = 'CELL'
        if id(n) in name_free:
            name = '<N>'
        rest = n.rest
        if kind == 'labels' and n.bid in targets and role == 'LabelText':
            rest = rest.replace(', clickable', '')
        if kind == 'alt' and n.bid in targets and role in IMAGE_ROLES:
            out.append((f'<<I:{n.bid}>>', depth, n, True))
            return
        key = f"{'[' + n.bid + '] ' if n.bid else ''}{role}{'' if name is None else ' ' + repr(name)}{rest}"
        out.append((key, depth, n, False))
        for c in n.children:
            visit(c, depth + 1)
    for n in nodes:
        if n.parent is None:
            visit(n, 0)
    return out


def obs_check(clean_text, var_text, kind, targets):
    """-> (ok, violations[list of str], n_lines_changed_raw)"""
    a, b = clean_text.split('\n'), var_text.split('\n')
    raw_ops = diff_opcodes(a, b)
    raw = sum((i2 - i1) + (j2 - j1) for i1, i2, j1, j2 in raw_ops)
    if kind == 'none' or not targets:
        return not raw_ops, [' | '.join(['-' + x for x in a[i1:i2][:2]] + ['+' + x for x in b[j1:j2][:2]]) for i1, i2, j1, j2 in raw_ops[:6]], raw
    A = normalize(parse_obs(clean_text), kind, targets)
    B = normalize(parse_obs(var_text), kind, targets)
    ka = ['\t' * d + k for k, d, _, _ in A]; kb = ['\t' * d + k for k, d, _, _ in B]
    viol = []
    W = 4  # removed target lines within this many clean lines may explain inserted StaticText
    for i1, i2, j1, j2 in diff_opcodes(ka, kb):
        C, V = A[i1:i2], B[j1:j2]
        ok = False
        if kind in REMOVE_ROLES and all(p for _, _, _, p in C):
            near = [(norm_ws(n.name), d) for _, d, n, p in A[max(0, i1 - W):i2 + W] if p and n.name is not None]
            ok = all(n.role == 'StaticText' and any(norm_ws(n.name) in nm and d == dd for nm, dd in near) for _, d, n, _ in V) \
                and (C or V)
        if kind == 'alt' and all(p for _, _, _, p in C) and all(p for _, _, _, p in V):
            ok = True
        if not ok:
            viol.append(' | '.join(['-' + x for x in ka[i1:i2][:3]] + ['+' + x for x in kb[j1:j2][:3]]))
    return not viol, viol[:6], raw


# ----------------------------------------------------------------------------- dom
KIND_DOM = {  # allowed per-element changes: (removed attrs by tag, tag map)
    'none': {},
    'landmarks': {'remove': {'*': {'role'}}, 'tags': codemod.LANDMARK_TAGS, 'repl': 'DIV'},
    'headings': {'remove': {'*': {'role'}}, 'tags': codemod.HEADING_TAGS, 'repl': 'DIV'},
    'names': {'remove': {'A': {'aria-label', 'aria-labelledby'}, 'BUTTON': {'aria-label', 'aria-labelledby'}}},
    'labels': {'remove': {'LABEL': {'for'}, 'INPUT': {'aria-label', 'aria-labelledby'},
                          'TEXTAREA': {'aria-label', 'aria-labelledby'}, 'SELECT': {'aria-label', 'aria-labelledby'}}},
    'alt': {'remove': {'IMG': {'alt'}}},
    'tableheads': {'tags': ['th'], 'repl': 'TD'},
}
ROLE_VALUES = {'landmarks': set(codemod.LANDMARK_ROLES), 'headings': {'heading'}}


def norm_attr(v):
    if v is None:
        return None
    v = re.sub(r'session=[\w-]+', 'session=S', v)
    return re.sub(r'/assets/([\w.-]+?)-[A-Za-z0-9_-]{8}\.(js|css)', r'/assets/\1.\2', v)


def dom_noise(doms):
    """Indices / (index, attr) that differ among clean builds; None if structure differs."""
    base = doms[0]['els']
    if any(len(d['els']) != len(base) or [e[0] for e in d['els']] != [e[0] for e in base] for d in doms[1:]):
        return None
    attr, rect, text = set(), set(), set()
    for d in doms[1:]:
        for i, (x, y) in enumerate(zip(base, d['els'])):
            for k in set(x[2]) | set(y[2]):
                if norm_attr(x[2].get(k)) != norm_attr(y[2].get(k)):
                    attr.add((i, k))
            if x[3] != y[3] or x[6:7] != y[6:7]:
                rect.add(i)
            if x[4] != y[4]:
                text.add(i)
    return attr, rect, text


def dom_check(clean, var, kind, noise):
    """-> (violations, layout_violations, target_bids, n_targets, label_for_ids)"""
    a, b = clean['els'], var['els']
    if len(a) != len(b) or [e[0] for e in a] != [e[0] for e in b]:
        return [f'element sequence differs: clean {len(a)} vs variant {len(b)} elements'], [], set(), 0, set()
    rule = KIND_DOM[kind]
    attr_noise, rect_noise, text_noise = noise
    viol, lay, targets, for_ids = [], [], set(), set()
    for i, (x, y) in enumerate(zip(a, b)):
        bid, tag_a, at_a, r_a, t_a = x[:5]
        _, tag_b, at_b, r_b, t_b = y[:5]
        changed = False
        if tag_a != tag_b:
            if tag_a.lower() in rule.get('tags', []) and tag_b == rule['repl'] and at_b.get('data-amt') == tag_a.lower():
                changed = True
            else:
                viol.append(f'[{bid}] tag {tag_a}->{tag_b}')
        for k in set(at_a) | set(at_b):
            va, vb = norm_attr(at_a.get(k)), norm_attr(at_b.get(k))
            if va == vb or (i, k) in attr_noise:
                continue
            rem = rule.get('remove', {})
            allowed_rm = rem.get(tag_a, set()) | rem.get('*', set())
            if vb is None and k in allowed_rm and (k != 'role' or va in ROLE_VALUES.get(kind, set())):
                changed = True
                if k == 'for':
                    for_ids.add(va)
            elif va is None and k == 'data-amt' and tag_a != tag_b:
                pass
            else:
                viol.append(f'[{bid}] {tag_a} attr {k}: {va!r}->{vb!r}')
        if t_a != t_b and i not in text_noise:
            viol.append(f'[{bid}] {tag_a} text {t_a[:40]!r}->{t_b[:40]!r}')
        if r_a != r_b and i not in rect_noise:
            lay.append(f'[{bid}] {tag_a} box {r_a}->{r_b}')
        elif x[6:7] != y[6:7] and i not in rect_noise:
            lay.append(f'[{bid}] {tag_a} overflow {x[6:7]}->{y[6:7]}')
        if changed and bid:
            targets.add(bid)
    n_targets = len(targets)
    if for_ids:  # controls labelled by a removed <label for>
        for bid, tag, at, *_ in a:
            if at.get('id') in for_ids and bid:
                targets.add(bid)
    return viol, lay, targets, n_targets, for_ids


def residual(var_dom, var_all_text, kind):
    els = var_dom['els']
    if kind == 'headings':
        dom = sum(1 for e in els if e[1] in ('H1', 'H2', 'H3', 'H4', 'H5', 'H6') or e[2].get('role') == 'heading')
    elif kind == 'landmarks':
        dom = sum(1 for e in els if e[1] in ('HEADER', 'NAV', 'MAIN', 'FOOTER', 'ASIDE') or e[2].get('role') in codemod.LANDMARK_ROLES)
    elif kind == 'names':
        dom = sum(1 for e in els if e[1] in ('A', 'BUTTON') and ('aria-label' in e[2] or 'aria-labelledby' in e[2]))
    elif kind == 'labels':
        dom = sum(1 for e in els if (e[1] == 'LABEL' and 'for' in e[2]) or (e[1] in ('INPUT', 'TEXTAREA', 'SELECT') and ('aria-label' in e[2] or 'aria-labelledby' in e[2])))
    elif kind == 'alt':
        dom = sum(1 for e in els if e[1] == 'IMG' and 'alt' in e[2])
    elif kind == 'tableheads':
        dom = sum(1 for e in els if e[1] == 'TH')
    else:
        return {}
    roles = {'headings': {'heading'}, 'landmarks': REMOVE_ROLES['landmarks'], 'tableheads': {'columnheader', 'rowheader'}}.get(kind)
    obs = sum(1 for n in parse_obs(var_all_text) if n.role in roles) if roles else None
    return {'dom_elements': dom, 'obs_lines': obs}


# ----------------------------------------------------------------------------- evaluate
def norm_console(t):
    t = re.sub(r'/assets/([\w.-]+?)-[A-Za-z0-9_-]{8}\.(js|css)', r'/assets/\1.\2', t)
    return re.sub(r':\d+:\d+', '', t)


def cmd_evaluate(envname, outroot):
    out = f'{outroot}/{envname}'
    meta = json.load(open(f'{out}/builds.json'))
    cleans = sorted(k for k in meta if k.startswith('clean'))
    pages = sorted(os.path.basename(p)[:-4] for p in glob.glob(f'{out}/{cleans[0]}/*.png'))
    # ---- noise floor
    floor = {'pairs': [], 'per_page': {}}
    noise_blocks, noise_blocks_strict, dom_noises, obs_noisy, clean_console = {}, {}, {}, {}, {}
    for pg in pages:
        imgs = [load_rgb(f'{out}/{c}/{pg}.png') for c in cleans]
        doms = [json.load(open(f'{out}/{c}/{pg}.dom.json')) for c in cleans]
        shares, nb, nbs = [], None, None
        for i in range(len(cleans)):
            for j in range(i + 1, len(cleans)):
                if imgs[i].shape != imgs[j].shape:
                    shares.append(None); continue
                m = changed_mask(imgs[i], imgs[j], TOL)
                im = image_mask(doms[i], m.shape) | image_mask(doms[j], m.shape)
                strict = float(m.mean())
                bs = blocks(m); nbs = bs if nbs is None else (nbs | bs)
                m &= ~im
                shares.append(float(m.mean()))
                bm = blocks(m); nb = bm if nb is None else (nb | bm)
                floor['pairs'].append({'page': pg, 'pair': [cleans[i], cleans[j]], 'share': round(float(m.mean()), 6),
                                       'share_with_images': round(strict, 6)})
        noise_blocks[pg] = grow(nb) if nb is not None else None
        noise_blocks_strict[pg] = grow(nbs) if nbs is not None else None
        floor['per_page'][pg] = {'max_share': None if None in shares else round(max(shares), 6),
                                 'sizes_equal': None not in shares,
                                 'noise_blocks': int(nb.sum()) if nb is not None else None}
        del imgs
        dom_noises[pg] = dom_noise(doms)
        clean_console[pg] = collections.Counter()
        for d in doms:
            for k, v in collections.Counter(norm_console(m['text']) for m in d['console'] if m['type'] in ('error', 'pageerror')).items():
                clean_console[pg][k] = max(clean_console[pg][k], v)
        obs_noisy[pg] = any(open(f'{out}/{c}/{pg}{s}').read() != open(f'{out}/{cleans[0]}/{pg}{s}').read()
                            for c in cleans[1:] for s in ('.txt', '.all.txt'))
        floor['per_page'][pg].update({'dom_stable': dom_noises[pg] is not None, 'obs_stable': not obs_noisy[pg],
                                      'dom_noisy_attrs': len(dom_noises[pg][0]) if dom_noises[pg] else None,
                                      'dom_noisy_boxes': len(dom_noises[pg][1]) if dom_noises[pg] else None})
    valid = [p['share'] for p in floor['pairs'] if p['share'] is not None]
    floor['env_floor_share'] = round(max(valid), 6) if valid else None
    vs = [p['share_with_images'] for p in floor['pairs'] if p.get('share_with_images') is not None]
    floor['env_floor_share_with_images'] = round(max(vs), 6) if vs else None
    floor['n_clean_builds'] = len(cleans)
    floor['n_pairs'] = len(floor['pairs'])
    # ---- variants
    ref = cleans[0]
    cells = {}
    for kind in [k for k in KINDS if k in meta] + sorted(k for k in meta if '@' in k):
        rec = meta[kind]
        rule = kind.split('@')[0]
        cell = {'build_ok': rec['build_ok'], 'codemod': rec.get('codemod'), 'pages': {}}
        reasons = collections.Counter()
        if not rec['build_ok']:
            reasons['build failed'] += 1
        if rec['build_ok'] and rule in codemod.REPLACE and '@' not in kind and not rec.get('css_layer_in_build'):
            reasons['amt-ua layer missing from built CSS'] += 1
        for pg in pages if rec['build_ok'] else []:
            r = {}
            if not os.path.exists(f'{out}/{kind}/{pg}.png'):
                reasons['page not captured'] += 1; continue
            cd, vd = json.load(open(f'{out}/{ref}/{pg}.dom.json')), json.load(open(f'{out}/{kind}/{pg}.dom.json'))
            # console
            vc = collections.Counter(norm_console(m['text']) for m in vd['console'] if m['type'] in ('error', 'pageerror'))
            new = vc - clean_console[pg]
            r['console_new'] = list(new)[:5]
            # size
            A, B = load_rgb(f'{out}/{ref}/{pg}.png'), load_rgb(f'{out}/{kind}/{pg}.png')
            r['size'] = {'clean': [A.shape[1], A.shape[0], cd['width'], cd['height']], 'variant': [B.shape[1], B.shape[0], vd['width'], vd['height']]}
            size_ok = A.shape == B.shape and (cd['width'], cd['height']) == (vd['width'], vd['height'])
            # pixels
            px_ok = False
            if A.shape == B.shape:
                m = changed_mask(A, B, TOL)
                im = image_mask(cd, m.shape) | image_mask(vd, m.shape)
                share_strict = float(m.mean())
                bms, nbks = blocks(m), noise_blocks_strict[pg]
                outside_strict = int((bms & ~nbks).sum()) if nbks is not None else int(bms.sum())
                share_img = float((m & im).sum() / max(1, im.sum()))
                m &= ~im
                share = float(m.mean())
                bm = blocks(m)
                nbk = noise_blocks[pg]
                outside = int((bm & ~nbk).sum()) if nbk is not None else int(bm.sum())
                ssim_mean, ssim_min = block_ssim(A, B)
                r['pixels'] = {'share': round(share, 6), 'share_with_images': round(share_strict, 6),
                               'share_inside_images': round(share_img, 6), 'image_pixels': int(im.sum()),
                               'share_exact': round(float(changed_mask(A, B, 0).mean()), 6),
                               'changed_blocks': int(bm.sum()), 'blocks_outside_noise': outside,
                               'ssim_mean': ssim_mean, 'ssim_min_tile': ssim_min}
                fl = floor['env_floor_share'] or 0.0
                px_ok = share <= fl and outside == 0
                # the rule before the image exclusion (first full run), reported only
                r['pixels']['strict_rule_ok'] = share_strict <= (floor['env_floor_share_with_images'] or 0.0) and outside_strict == 0
            del A, B
            # dom + layout
            if dom_noises[pg] is None:
                dv, lv, targets, n_t, _ = ['clean builds differ in DOM structure (unresolved)'], [], set(), 0, set()
            else:
                dv, lv, targets, n_t, _ = dom_check(cd, vd, rule, dom_noises[pg])
            r['dom_violations'] = dv[:6]; r['n_dom_violations'] = len(dv)
            r['layout_violations'] = lv[:6]; r['n_layout_violations'] = len(lv)
            r['dom_targets'] = n_t
            # obs
            ov = []
            r['obs_lines_changed'] = {}
            for s, key in (('.txt', 'visible'), ('.all.txt', 'all')):
                ok, viol, raw = obs_check(open(f'{out}/{ref}/{pg}{s}').read(), open(f'{out}/{kind}/{pg}{s}').read(), rule, targets)
                r['obs_lines_changed'][key] = raw
                ov += [f'{key}: {v}' for v in viol]
            if obs_noisy[pg]:
                ov.insert(0, 'clean builds differ in observation (unresolved)')
            r['obs_violations'] = ov[:8]; r['n_obs_violations'] = len(ov)
            if rule == 'labels':  # label lost its association: BrowserGym no longer marks it clickable
                ca = {n.bid for n in parse_obs(open(f'{out}/{ref}/{pg}.all.txt').read()) if n.role == 'LabelText' and 'clickable' in n.rest}
                cb = {n.bid for n in parse_obs(open(f'{out}/{kind}/{pg}.all.txt').read()) if n.role == 'LabelText' and 'clickable' in n.rest}
                r['label_clickable_lost'] = len(ca - cb)
            r['residual'] = residual(vd, open(f'{out}/{kind}/{pg}.all.txt').read(), rule)
            r['broken_images_clean'] = sum(1 for e in cd['els'] if len(e) > 5 and e[5] is False)
            r['broken_images_variant'] = sum(1 for e in vd['els'] if len(e) > 5 and e[5] is False)
            fails = []
            if new: fails.append('console')
            if not size_ok: fails.append('size')
            if size_ok and not px_ok: fails.append('pixels')
            if dv: fails.append('dom')
            if lv: fails.append('layout')
            if ov: fails.append('obs')
            r['fails'] = fails
            for f in fails:
                reasons[f] += 1
            cell['pages'][pg] = r
        cell['n_pages'] = len(cell['pages'])
        cell['reasons'] = dict(reasons)
        cell['verdict'] = 'PASS' if not reasons else 'FAIL'
        cell['noop'] = all(p['obs_lines_changed']['all'] == 0 for p in cell['pages'].values()) if cell['pages'] else None
        cell['dose'] = {'pages_with_obs_change': sum(1 for p in cell['pages'].values() if p['obs_lines_changed']['all']),
                        'obs_lines_changed_all': sum(p['obs_lines_changed']['all'] for p in cell['pages'].values()),
                        'obs_lines_changed_visible': sum(p['obs_lines_changed']['visible'] for p in cell['pages'].values()),
                        'dom_targets': sum(p['dom_targets'] for p in cell['pages'].values())}
        cell['pages_failing_strict_pixel_rule'] = sum(1 for p in cell['pages'].values() if 'pixels' in p and not p['pixels']['strict_rule_ok'])
        cell['label_clickable_lost'] = sum(p.get('label_clickable_lost', 0) for p in cell['pages'].values())
        cell['max_pixel_share'] = max([p.get('pixels', {}).get('share', 0) for p in cell['pages'].values()] or [0])
        cell['residual_dom'] = sum((p['residual'] or {}).get('dom_elements') or 0 for p in cell['pages'].values())
        cells[kind] = cell
        print(f"{envname:15} {kind:11} {cell['verdict']:4} pages={cell['n_pages']:2} reasons={cell['reasons']} "
              f"dose={cell['dose']['obs_lines_changed_all']} maxpix={cell['max_pixel_share']:.5f} residual={cell['residual_dom']}")
    # ---- specificity control: each variant judged by every other kind's dom+obs rule must fail on
    # some page whenever the variant changed anything (dose > 0); a pass would mean the rules are
    # too loose to tell the kinds apart.
    controls = {}
    for x in [k for k in KINDS if k in meta and meta[k]['build_ok'] and k != 'none']:
        if not cells[x]['dose']['dom_targets']:
            continue
        controls[x] = {}
        for y in KINDS:
            if y == x:
                continue
            fails = 0
            for pg in pages:
                if dom_noises[pg] is None:
                    continue
                cd, vd = json.load(open(f'{out}/{ref}/{pg}.dom.json')), json.load(open(f'{out}/{x}/{pg}.dom.json'))
                dv, _, t, _, _ = dom_check(cd, vd, y, dom_noises[pg])
                ok, _, _ = obs_check(open(f'{out}/{ref}/{pg}.all.txt').read(), open(f'{out}/{x}/{pg}.all.txt').read(), y, t)
                fails += bool(dv) or not ok
            controls[x][y] = fails
        print(f"{envname:15} control {x:11} pages failing under other rules: {controls[x]}")
    res = {'env': envname, 'tol': TOL, 'block': BLOCK, 'pages': pages, 'floor': floor, 'cells': cells,
           'specificity_control': controls}
    json.dump(res, open(f'{out}/gate.json', 'w'), indent=1)
    print(f"{envname}: floor share {floor['env_floor_share']} over {floor['n_pairs']} pairs; "
          f"pages with clean obs noise {sum(obs_noisy.values())}, unstable DOM {sum(1 for v in dom_noises.values() if v is None)}")
    return res


def cmd_summary(outroot):
    rows = {}
    for f in sorted(glob.glob(f'{outroot}/*/gate.json')):
        g = json.load(open(f))
        rows[g['env']] = {'floor_share': g['floor']['env_floor_share'], 'n_pages': len(g['pages']),
                          'n_clean_builds': g['floor']['n_clean_builds'],
                          'cells': {k: {'verdict': c['verdict'], 'reasons': c['reasons'], 'noop': c['noop'], 'dose': c['dose'],
                                        'max_pixel_share': c['max_pixel_share'], 'residual_dom': c['residual_dom'],
                                        'codemod_env': (c['codemod'] or {}).get('env'), 'codemod_shared': (c['codemod'] or {}).get('shared')}
                                    for k, c in g['cells'].items()},
                          'specificity_control': g.get('specificity_control')}
    json.dump(rows, open(f'{outroot}/summary.json', 'w'), indent=1)
    cols = KINDS + sorted({k for r in rows.values() for k in r['cells'] if '@' in k})
    print('env'.ljust(15) + ''.join(k.ljust(14) for k in cols) + '   (* = no observation change)')
    for e, r in rows.items():
        print(e.ljust(15) + ''.join((r['cells'].get(k, {}).get('verdict', '-') + ('*' if r['cells'].get(k, {}).get('noop') else '')).ljust(14) for k in cols))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['capture', 'evaluate', 'summary', '_capture'])
    ap.add_argument('args', nargs='+')
    ap.add_argument('--clean', type=int, default=3)
    ap.add_argument('--kinds', default=','.join(KINDS))
    ap.add_argument('--tasks', type=int, default=2)
    a = ap.parse_args()
    if a.cmd == '_capture':
        capture(a.args[0], a.args[1], a.tasks)
    elif a.cmd == 'capture':
        cmd_capture(a.args[0], a.args[1], a.clean, a.kinds.split(','), a.tasks)
    elif a.cmd == 'evaluate':
        cmd_evaluate(a.args[0], a.args[1])
    else:
        cmd_summary(a.args[0])
