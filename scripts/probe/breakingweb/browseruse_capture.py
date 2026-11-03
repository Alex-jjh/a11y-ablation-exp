#!/usr/bin/env python3
"""Capture the page text the stock browser-use agent sends to its LLM, for clean and variant
builds of a BreakingWeb environment, and diff them. No LLM is called.

Why: BreakingWeb's leaderboard text agents run stock browser-use (stock_browseruse_eval.py),
not BrowserGym. Its observation is a DOM serialisation, not the accessibility tree, so a
source-level defect can leave a different footprint there than in the BrowserGym text the
variant gate measures (docs/feasibility/2026-10-30-variant-gate.md, "What this does not show").

What is captured (browser-use as installed in the BreakingWeb venv, 0.13.14)
  Per page, the `<browser_state>` block of the agent's user message, produced by the library's
  own code: BrowserSession.get_browser_state_summary(include_screenshot=True) (the call of
  Agent._prepare_context) and AgentMessagePrompt._get_browser_state_description() with the
  Agent defaults (include_attributes = DEFAULT_INCLUDE_ATTRIBUTES,
  max_clickable_elements_length = 40000). That block holds page_stats, tabs, page_info and the
  serialised DOM (DOMTreeSerializer.serialize_tree). The rest of the user message (task,
  history, step counter) does not depend on the page. The Browser is configured as
  stock_browseruse_eval.run_episode does: headless, highlight_elements=False, chromium_sandbox=
  False, allowed_domains 127.0.0.1/localhost, viewport 1280x720 (Gemini/default; --viewport
  1024x768 for Claude, 1600x900 for GPT). The viewport screenshot the vision channel receives is
  saved too.
  Pages: as variant_run.py / variant_gate.py: the start page of the first N tasks (sorted task
  ids; default 2) and, in the first task's session, the env's static routes from App.tsx
  (amazon: the fixed list incl. '@product', the first product link on the start page).
  Settling: after navigation the state is taken repeatedly (0.8 s apart, up to 8 times) until
  two consecutive normalised texts agree; the last one is kept. `*[N]` ("new since the previous
  state") markers therefore refer to the previous capture of the same page.

Subcommands (BreakingWeb venv python; BW_ROOT = a private checkout to build in, default
/tmp/amt-syn/bw-bu-src/BreakingWeb; BW_PORT = backend port on 127.0.0.1, default 8099)
  drive ENV OUT [--kinds k1,k2] [--clean 2] [--tasks 2] [--viewport WxH]
      restores ENV and shared sources from git, builds clean --clean times (capture after each:
      clean0, clean1, ... gives the noise floor), then per kind applies codemod.py (the copy next
      to this file) to ENV and shared sources, builds, captures, restores. Ends with a restore
      and a clean rebuild. Records codemod counts in OUT/<env>/builds.json.
  _capture ENV OUTDIR [--tasks 2] [--viewport WxH]   one capture of the current build (used by
      drive in a fresh process; BreakingWeb checks the server manifest against sources at import)
  diff ENV OUT [--gate GATE_DIR]
      per page: clean0 vs every other build, on the serialised DOM after normalisation (selector
      indices -> [#], `*` new-markers dropped, session ids masked). Every changed line pair is
      classified (attribute keys removed / added / value changed, tag changed, text changed,
      element line added/removed). With --gate (default /tmp/amt-syn/bw-gate/final) the same
      pages' BrowserGym observations from the variant gate are diffed too, for comparison.
      Writes OUT/<env>/bu_diff.json and prints a summary.
      Removed-value fate (aria-label, image_alt): full / partial / none / empty, by the words of the
      removed value still printed on the element line or in its subtree (see removed_value_fate).
  validate ENV OUTDIR [--tasks 30] [--traj ~/.hf-stage-bw/gemini_3_1_pro/tasks]
      captures the clean start page of the first N tasks with a recorded clean run and checks each
      recorded step-1 click ('Clicked <tag> "<text>..." aria-label=<20 chars>') against the captured
      selector map -> OUTDIR/validate.json. Run on a clean build.
  summary OUT ENV1 [ENV2 ...]  -> OUT/summary.json (small; copied next to the record)

Outputs: OUT/<env>/<build>/<page>.bu.txt (browser_state block), <page>.bu.json (url, page_stats,
selector map: index, tag, printed attributes, AX role and name), <page>.bu.png (viewport
screenshot). Regenerable; nothing here is committed.

Run (example):
  C=~/.workspace/_refsrc/BreakingWeb; mkdir -p /tmp/amt-syn/bw-bu-src && cp -a $C /tmp/amt-syn/bw-bu-src/
  export PATH=$HOME/.local/share/mise/installs/node/24.20.0/bin:$HOME/.local/bin:$PATH BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
  export ANONYMIZED_TELEMETRY=false BROWSER_USE_CLOUD_SYNC=false
  cd /tmp/amt-syn/bw-bu-src/BreakingWeb && PYTHONPATH=$PWD $C/.venv/bin/python \
     ~/.workspace/ai-agent-accessibility/scripts/probe/breakingweb/browseruse_capture.py drive amazon /tmp/amt-syn/bw-bu \
     --kinds none,landmarks,headings,names,labels,alt
The backend binds to 127.0.0.1 only and is stopped after each capture.
"""
import argparse
import asyncio
import difflib
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOT = os.environ.get('BW_ROOT', '/tmp/amt-syn/bw-bu-src/BreakingWeb')
PORT = int(os.environ.get('BW_PORT', '8099'))
HOST = '127.0.0.1'
ENVROOT = f'{ROOT}/breakingweb/environments'
NODE = os.path.expanduser('~/.local/share/mise/installs/node/24.20.0/bin')
ROUTES = {'amazon': ['home', 'search?q=headphones', '@product', 'cart', 'checkout', 'orders', 'wishlist', 'settings',
                     'account', 'returns', 'categories', 'deals', 'notifications', 'gift-cards', 'customer-service']}
os.environ.setdefault('ANONYMIZED_TELEMETRY', 'false')
os.environ.setdefault('BROWSER_USE_CLOUD_SYNC', 'false')


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


def auto_routes(envname):
    src = open(f'{ENVROOT}/{envname}/src/App.tsx').read()
    seen = []
    for p in (p.strip('/') for p in re.findall(r'<Route\s+path="([^"]*)"', src)):
        if p and p != 'launch' and ':' not in p and '*' not in p and p not in seen:
            seen.append(p)
    return seen[:15]


def route_label(r):
    return 'route__' + r.replace('/', '_').replace('?', '_').replace('=', '-')


# ----------------------------------------------------------------------------- capture
def http_json(url, method='GET', payload=None):
    from breakingweb.runner import controller_headers
    body = json.dumps(payload).encode() if payload is not None else None
    headers = dict(controller_headers())
    if body:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode()
        return json.loads(t) if t else {}


def norm_text(t):
    t = re.sub(r'session=[^&\s]+', 'session=S', t)
    t = re.sub(r'^Tab \w{4}:', 'Tab T:', t, flags=re.M)
    t = re.sub(r'Current tab: \w{4}', 'Current tab: T', t)
    t = re.sub(r'\*?\[\d+\]', '[#]', t)
    return t


async def state_text(browser):
    from browser_use.agent.prompts import AgentMessagePrompt
    from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES
    st = await browser.get_browser_state_summary(include_screenshot=True)
    mp = AgentMessagePrompt(browser_state_summary=st, file_system=None, include_attributes=DEFAULT_INCLUDE_ATTRIBUTES,
                            max_clickable_elements_length=40000)
    return st, mp._get_browser_state_description()


def selector_summary(st):
    from browser_use.dom.serializer.serializer import DOMTreeSerializer
    from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES
    out = []
    for idx, n in sorted((st.dom_state.selector_map or {}).items()):
        ax = n.ax_node
        out.append({'index': idx, 'tag': n.tag_name,
                    'printed_attrs': DOMTreeSerializer._build_attributes_string(n, DEFAULT_INCLUDE_ATTRIBUTES, ''),
                    'ax_role': ax.role if ax else None, 'ax_name': ax.name if ax else None,
                    'aria_label': (n.attributes or {}).get('aria-label'),
                    'text': n.get_all_children_text().strip()[:80]})
    return out


async def settle_and_grab(browser, out, label):
    import base64
    await asyncio.sleep(0.8)
    prev, st, txt = None, None, None
    for _ in range(8):
        st, txt = await state_text(browser)
        n = norm_text(txt)
        if n == prev:
            break
        prev = n
        await asyncio.sleep(0.8)
    open(f'{out}/{label}.bu.txt', 'w').write(txt)
    json.dump({'url': st.url, 'title': st.title, 'selector_map': selector_summary(st)},
              open(f'{out}/{label}.bu.json', 'w'), indent=0)
    if st.screenshot:
        open(f'{out}/{label}.bu.png', 'wb').write(base64.b64decode(st.screenshot))


def new_browser(viewport, tmp):
    from browser_use import Browser
    os.makedirs(f'{tmp}/dl', exist_ok=True)
    return Browser(headless=True, viewport={'width': viewport[0], 'height': viewport[1]}, highlight_elements=False,
                   allowed_domains=[HOST, 'localhost'], user_data_dir=f'{tmp}/ud', downloads_path=f'{tmp}/dl',
                   traces_dir=f'{tmp}/tr', chromium_sandbox=False)


async def capture_pages(envname, out, tasks, viewport, start_only=False):
    base = f'http://{HOST}:{PORT}'
    for i, t in enumerate(tasks):
        created = http_json(f'{base}/api/env/{envname}/session', 'POST', {'task_id': t})
        sid = created['session_id']
        q = f'session={urllib.parse.quote(sid)}&agent_mode=1'
        launch = f"{base}/env/{envname}{created.get('start_path', '/home')}?{q}"
        tmp = tempfile.mkdtemp(prefix='amt-bu-')
        browser = new_browser(viewport, tmp)
        try:
            await browser.start()
            await browser.navigate_to(launch)
            await settle_and_grab(browser, out, t)
            if i == 0 and not start_only:
                page = await browser.get_current_page()
                for r in ROUTES.get(envname) or auto_routes(envname):
                    if r == '@product':
                        href = await page.evaluate("() => { const a = [...document.querySelectorAll('a[href*=\"/product/\"]')][0]; return a ? a.getAttribute('href') : '' }")
                        if not href:
                            continue
                        r = href.split('/env/' + envname + '/')[-1].lstrip('/').split('?')[0]
                    sep = '&' if '?' in r else '?'
                    await browser.navigate_to(f'{base}/env/{envname}/{r}{sep}{q}')
                    await settle_and_grab(browser, out, route_label(r))
        finally:
            await browser.kill()
            try:
                http_json(f'{base}/api/env/{envname}/session/{urllib.parse.quote(sid)}', 'DELETE')
            except Exception:
                pass


def cmd_capture_inner(envname, out, n_tasks, viewport, task_file=None):
    sys.path.insert(0, ROOT)
    from breakingweb.runner import start_server, wait_for_server
    tasks = sorted(os.path.basename(p)[:-5] for p in glob.glob(f'{ROOT}/breakingweb/tasks/{envname}/*.yaml'))[:n_tasks]
    if task_file:
        tasks = [l.strip() for l in open(task_file) if l.strip()]
    os.makedirs(out, exist_ok=True)
    if wait_for_server(HOST, PORT, timeout=1):
        raise SystemExit(f'port {PORT} already serves something; choose another BW_PORT')
    proc = start_server(HOST, PORT)
    try:
        if not wait_for_server(HOST, PORT, timeout=90):
            raise SystemExit('server did not start: ' + proc.stderr.read().decode()[-2000:])
        asyncio.run(capture_pages(envname, out, tasks, viewport, start_only=bool(task_file)))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


def capture_subprocess(envname, out, n_tasks, viewport):
    r = subprocess.run([sys.executable, os.path.abspath(__file__), '_capture', envname, out, '--tasks', str(n_tasks),
                        '--viewport', f'{viewport[0]}x{viewport[1]}'],
                       cwd=ROOT, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=ROOT))
    if r.returncode:
        raise SystemExit(f'capture failed for {out}:\n{r.stdout[-1500:]}\n{r.stderr[-3000:]}')


def cmd_drive(envname, outroot, kinds, n_clean, n_tasks, viewport):
    import codemod
    out = f'{outroot}/{envname}'
    os.makedirs(out, exist_ok=True)
    meta_path = f'{out}/builds.json'
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    meta['_viewport'] = list(viewport)
    restore(envname)
    try:
        for i in range(n_clean):
            name = f'clean{i}'
            if name in meta:
                continue
            ok, log = build(envname)
            if not ok:
                raise SystemExit(f'clean build failed:\n{log}')
            t0 = time.time()
            capture_subprocess(envname, f'{out}/{name}', n_tasks, viewport)
            meta[name] = {'build_ok': True, 'capture_s': round(time.time() - t0)}
            json.dump(meta, open(meta_path, 'w'), indent=1)
            print(name, 'captured', flush=True)
        for kind in kinds:
            if kind in meta:
                continue
            restore(envname)
            counts = {'env': codemod.rewrite(f'{ENVROOT}/{envname}/src', kind),
                      'shared': codemod.rewrite(f'{ENVROOT}/shared/src', kind)}
            ok, log = build(envname)
            rec = {'build_ok': ok, 'codemod': counts}
            if ok:
                capture_subprocess(envname, f'{out}/{kind}', n_tasks, viewport)
            else:
                rec['build_log_tail'] = log[-1500:]
            meta[kind] = rec
            restore(envname)
            json.dump(meta, open(meta_path, 'w'), indent=1)
            print(kind, 'captured' if ok else 'BUILD FAILED', counts, flush=True)
    finally:
        restore(envname)
        build(envname)


# ----------------------------------------------------------------------------- diff
ATTR_KEYS = None


def attr_keys():
    global ATTR_KEYS
    if ATTR_KEYS is None:
        from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES
        ATTR_KEYS = sorted(set(DEFAULT_INCLUDE_ATTRIBUTES) | {'image_alt', 'image_title', 'image_label', 'image_src',
                                                              'compound_components', 'format', 'expected_format'},
                           key=len, reverse=True)
    return ATTR_KEYS


ELEM_RE = re.compile(r'^(\t*)((?:\|SHADOW\((?:open|closed)\)\|)?(?:\|scroll element\|?|\|IFRAME\||\|FRAME\|)?\[?#?\]?)<(\w+)(.*?) ?/>(.*)$')


def parse_line(line):
    """-> dict(kind='elem'|'text'|'other', depth, tag, prefix, attrs{key: value}, rest)"""
    m = ELEM_RE.match(line)
    if not m:
        d = len(line) - len(line.lstrip('\t'))
        return {'kind': 'text', 'depth': d, 'text': line.strip()}
    depth, prefix, tag, attrs, rest = len(m.group(1)), m.group(2), m.group(3), m.group(4).strip(), m.group(5)
    keys = '|'.join(re.escape(k) for k in attr_keys())
    parts = re.split(rf'(?:^|\s)({keys})=', attrs)
    a = {}
    for k, v in zip(parts[1::2], parts[2::2]):
        a[k] = v.strip()
    return {'kind': 'elem', 'depth': depth, 'tag': tag.lower(), 'prefix': prefix, 'attrs': a, 'rest': rest.strip()}


def dom_lines(txt):
    """Lines of the serialised DOM (after 'Interactive elements...:'), normalised."""
    t = norm_text(txt)
    head, _, body = t.partition('\nInteractive elements')
    body = body.split(':\n', 1)[1] if ':\n' in body else body
    stats = re.search(r'<page_stats>(.*?)</page_stats>', head)
    info = re.search(r'<page_info>(.*?)</page_info>', head)
    return (stats.group(1) if stats else ''), (info.group(1) if info else ''), [l for l in body.split('\n') if l.strip()]


def classify_pair(a, b):
    """What changed between two lines judged to be the same element/text."""
    pa, pb = parse_line(a), parse_line(b)
    ch = []
    if pa['kind'] != pb['kind']:
        return ['line_kind_changed']
    if pa['depth'] != pb['depth']:
        ch.append('depth')
    if pa['kind'] == 'text':
        if pa['text'] != pb['text']:
            ch.append('text')
        return ch
    if pa['tag'] != pb['tag']:
        ch.append(f"tag:{pa['tag']}->{pb['tag']}")
    if pa['prefix'] != pb['prefix']:
        ch.append(f"prefix:{pa['prefix']}->{pb['prefix']}")
    for k in sorted(set(pa['attrs']) | set(pb['attrs'])):
        if k in pa['attrs'] and k not in pb['attrs']:
            ch.append(f'-attr:{k}')
        elif k in pb['attrs'] and k not in pa['attrs']:
            ch.append(f'+attr:{k}')
        elif pa['attrs'][k] != pb['attrs'][k]:
            ch.append(f'~attr:{k}')
    if pa['rest'] != pb['rest']:
        ch.append('suffix')
    return ch


def line_sig(l):
    p = parse_line(l)
    if p['kind'] == 'text':
        return 'TEXT:' + p['text']
    return f"ELEM:{p['tag']}"


def diff_lines(A, B):
    """Ops over normalised lines. Lines equal up to depth count as 'depth' changes; replaced blocks
    are paired line by line where the element tag or text matches, else counted as removed/added."""
    sm = difflib.SequenceMatcher(a=[l.strip() for l in A], b=[l.strip() for l in B], autojunk=False)
    rec = {'equal': 0, 'depth_only': 0, 'removed': [], 'added': [], 'changed': []}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if A[i] == B[j]:
                    rec['equal'] += 1
                else:
                    rec['depth_only'] += 1
            continue
        a, b = A[i1:i2], B[j1:j2]
        # greedy pairing on element signature (same tag, or same text) in order
        sm2 = difflib.SequenceMatcher(a=[line_sig(x) for x in a], b=[line_sig(x) for x in b], autojunk=False)
        for op2, k1, k2, l1, l2 in sm2.get_opcodes():
            if op2 == 'equal' or (op2 == 'replace' and (k2 - k1) == (l2 - l1)):
                for k, l in zip(range(k1, k2), range(l1, l2)):
                    rec['changed'].append({'clean': a[k], 'variant': b[l], 'what': classify_pair(a[k], b[l]), 'j': j1 + l})
            else:
                rec['removed'] += a[k1:k2]
                rec['added'] += b[l1:l2]
    return rec


INFO_ATTRS = ('placeholder', 'title', 'id', 'name', 'value', 'alt', 'image_alt', 'image_title', 'image_label', 'aria-label')


def toks(x):
    return set(re.findall(r'[a-z0-9]+', (x or '').lower()))


def subtree(B, j):
    """Text lines and informative attribute values below element line j (deeper indentation)."""
    d0 = len(B[j]) - len(B[j].lstrip('\t'))
    texts, attrs = [], []
    for l in B[j + 1:]:
        d = len(l) - len(l.lstrip('\t'))
        if d <= d0:
            break
        p = parse_line(l)
        if p['kind'] == 'text':
            texts.append(p['text'])
        else:
            attrs += [v for k, v in p['attrs'].items() if k in INFO_ATTRS]
    return texts, attrs


def removed_value_fate(rec, B, page_text):
    """For each changed element line that lost an aria-label or image_alt: is the removed value still
    in what the agent sees? full = every word of the value is in the element's remaining attributes or
    its subtree text; partial = some words; none = no word, but the element still prints text or an
    informative attribute; empty = the element line keeps no text and no informative attribute (an
    unnamed control); elsewhere = the exact value is printed somewhere else on the page."""
    out = []
    for x in rec['changed']:
        for key in ('aria-label', 'image_alt'):
            if f'-attr:{key}' not in x['what']:
                continue
            val = parse_line(x['clean'])['attrs'].get(key, '')
            pv = parse_line(x['variant'])
            texts, sub_attrs = subtree(B, x['j'])
            own = [v for k, v in pv['attrs'].items() if k in INFO_ATTRS]
            have = toks(' '.join(texts + sub_attrs + own))
            vt = toks(val)
            if val.endswith('...'):  # cap_text_length cut the value at 100 characters: drop the cut word
                cut = re.findall(r'[a-z0-9]+', val[:-3].lower())
                if cut and not val[:-3].endswith(' '):
                    vt = toks(' '.join(cut[:-1]))
            cover = len(vt & have) / len(vt) if vt else 1.0
            fate = 'full' if cover >= 0.999 else 'partial' if cover > 0 else ('empty' if not (texts or sub_attrs or own) else 'none')
            j = x['j']
            near = toks(' '.join(parse_line(l).get('text', '') for l in B[max(0, j - 3):j] + B[j + 1:j + 4]))
            out.append({'key': key, 'value': val[:100], 'fate': fate, 'cover': round(cover, 2), 'tag': pv.get('tag'),
                        'nearby_full': bool(vt) and vt <= (near | have),
                        'remaining': ' | '.join(own + texts + sub_attrs)[:100],
                        'elsewhere': bool(val) and val.lower() in page_text.lower().replace(f'{key}={val}'.lower(), '')})
    return out


def change_counts(rec):
    c = {}
    for x in rec['changed']:
        for w in x['what']:
            c[w] = c.get(w, 0) + 1
    for l in rec['removed']:
        p = parse_line(l)
        k = f"-line:{p['tag']}" if p['kind'] == 'elem' else '-line:text'
        c[k] = c.get(k, 0) + 1
    for l in rec['added']:
        p = parse_line(l)
        k = f"+line:{p['tag']}" if p['kind'] == 'elem' else '+line:text'
        c[k] = c.get(k, 0) + 1
    if rec['depth_only']:
        c['depth_only'] = rec['depth_only']
    return c


def gym_diff(gate_dir, envname, build, page):
    a = f'{gate_dir}/{envname}/clean0/{page}'
    b = f'{gate_dir}/{envname}/{build}/{page}'
    out = {}
    for suf, key in (('.txt', 'viewport'), ('.all.txt', 'full')):
        if not (os.path.exists(a + suf) and os.path.exists(b + suf)):
            return None
        A, B = open(a + suf).read().splitlines(), open(b + suf).read().splitlines()
        d = [l for l in difflib.unified_diff(A, B, lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
        out[key] = {'lines': len(A), 'removed': sum(1 for l in d if l[0] == '-'), 'added': sum(1 for l in d if l[0] == '+')}
    return out


def pix_share(a, b):
    import numpy as np
    from PIL import Image
    if not (os.path.exists(a) and os.path.exists(b)):
        return None
    A, B = Image.open(a).convert('RGB'), Image.open(b).convert('RGB')
    if A.size != B.size:
        return 'size'
    x, y = np.asarray(A, dtype=np.int16), np.asarray(B, dtype=np.int16)
    return round(float((np.abs(x - y).sum(axis=2) > 30).mean()), 5)


def cmd_diff(envname, outroot, gate_dir):
    out = f'{outroot}/{envname}'
    meta = json.load(open(f'{out}/builds.json'))
    builds = [b for b in meta if not b.startswith('_') and b != 'clean0' and meta[b].get('build_ok')]
    pages = sorted(os.path.basename(p)[:-7] for p in glob.glob(f'{out}/clean0/*.bu.txt'))
    res = {'env': envname, 'viewport': meta.get('_viewport'), 'pages': pages, 'builds': {}}
    for b in builds:
        cell = {'codemod': meta[b].get('codemod'), 'pages': {}, 'totals': {}, 'examples': {}}
        for p in pages:
            fa, fb = f'{out}/clean0/{p}.bu.txt', f'{out}/{b}/{p}.bu.txt'
            if not os.path.exists(fb):
                cell['pages'][p] = {'missing': True}
                continue
            sa, ia, A = dom_lines(open(fa).read())
            sb, ib, B = dom_lines(open(fb).read())
            rec = diff_lines(A, B)
            cc = change_counts(rec)
            raw_equal = norm_text(open(fa).read()) == norm_text(open(fb).read())
            pg = {'lines_clean': len(A), 'lines_variant': len(B), 'identical': raw_equal,
                  'page_stats_clean': sa, 'page_stats_variant': sb, 'page_info_equal': ia == ib,
                  'n_changed': len(rec['changed']), 'n_removed': len(rec['removed']), 'n_added': len(rec['added']),
                  'n_depth_only': rec['depth_only'], 'counts': cc,
                  'screenshot_pix_share': pix_share(f'{out}/clean0/{p}.bu.png', f'{out}/{b}/{p}.bu.png'),
                  'gym': gym_diff(gate_dir, envname, b if not b.startswith('clean') else 'clean1', p)}
            pg['removed_value_fate'] = removed_value_fate(rec, B, '\n'.join(B))
            cell['pages'][p] = pg
            for k, v in cc.items():
                cell['totals'][k] = cell['totals'].get(k, 0) + v
                ex = cell['examples'].setdefault(k, [])
                if len(ex) < 4:
                    src = ([x for x in rec['changed'] if k in x['what']][:1] or
                           [{'clean': l} for l in rec['removed'] if k.startswith('-line') and change_counts({'changed': [], 'removed': [l], 'added': [], 'depth_only': 0}).get(k)][:1] or
                           [{'variant': l} for l in rec['added'] if k.startswith('+line') and change_counts({'changed': [], 'removed': [], 'added': [l], 'depth_only': 0}).get(k)][:1])
                    for s in src:
                        ex.append({'page': p, **{kk: vv.strip()[:220] for kk, vv in s.items() if kk in ('clean', 'variant')}})
        fates = [f for v in cell['pages'].values() for f in v.get('removed_value_fate', [])]
        cell['removed_value_fate'] = {}
        for f in fates:
            k = f"{f['key']}:{f['fate']}"
            cell['removed_value_fate'][k] = cell['removed_value_fate'].get(k, 0) + 1
        cell['removed_value_elsewhere'] = sum(f['elsewhere'] for f in fates)
        cell['removed_value_nearby_full'] = {}
        for f in fates:
            if f['fate'] != 'full':
                k = f"{f['key']}:{f['fate']}"
                cell['removed_value_nearby_full'][k] = cell['removed_value_nearby_full'].get(k, 0) + bool(f['nearby_full'])
        cell['removed_value_fate_examples'] = {}
        for f in fates:
            ex = cell['removed_value_fate_examples'].setdefault(f"{f['key']}:{f['fate']}", [])
            if len(ex) < 4:
                ex.append({kk: f[kk] for kk in ('tag', 'value', 'remaining')})
        ch = [p for p, v in cell['pages'].items() if not v.get('identical', True)]
        cell['pages_changed'] = len(ch)
        cell['lines_changed'] = sum(v.get('n_changed', 0) + v.get('n_removed', 0) + v.get('n_added', 0) for v in cell['pages'].values())
        cell['lines_depth_only'] = sum(v.get('n_depth_only', 0) for v in cell['pages'].values())
        cell['lines_clean_total'] = sum(v.get('lines_clean', 0) for v in cell['pages'].values())
        g = [v['gym'] for v in cell['pages'].values() if v.get('gym')]
        cell['gym_viewport_lines_changed'] = sum(x['viewport']['removed'] + x['viewport']['added'] for x in g) if g else None
        cell['gym_full_lines_changed'] = sum(x['full']['removed'] + x['full']['added'] for x in g) if g else None
        cell['gym_pages_changed'] = sum(1 for x in g if x['full']['removed'] + x['full']['added'] > 0) if g else None
        sh_ = [v['screenshot_pix_share'] for v in cell['pages'].values() if isinstance(v.get('screenshot_pix_share'), float)]
        cell['screenshot_max_pix_share'] = max(sh_) if sh_ else None
        cell['screenshot_size_mismatch'] = sum(1 for v in cell['pages'].values() if v.get('screenshot_pix_share') == 'size')
        res['builds'][b] = cell
        print(f"{envname:15} {b:11} pages {len(ch)}/{len(pages)}  bu lines changed {cell['lines_changed']} "
              f"(+depth-only {cell['lines_depth_only']}) of {cell['lines_clean_total']}  gym full {cell['gym_full_lines_changed']}  "
              f"shot {cell['screenshot_max_pix_share']}  {dict(sorted(cell['totals'].items(), key=lambda x: -x[1])[:8])}  fate {cell['removed_value_fate']} nearby {cell['removed_value_nearby_full']} elsewhere {cell['removed_value_elsewhere']}")
    json.dump(res, open(f'{out}/bu_diff.json', 'w'), indent=1)


def cmd_summary(outroot, envs):
    s = {}
    for e in envs:
        d = json.load(open(f'{outroot}/{e}/bu_diff.json'))
        s[e] = {'n_pages': len(d['pages']), 'viewport': d['viewport'], 'cells': {}}
        for b, c in d['builds'].items():
            s[e]['cells'][b] = {k: c[k] for k in ('codemod', 'pages_changed', 'lines_changed', 'lines_depth_only',
                                                  'lines_clean_total', 'totals', 'gym_pages_changed',
                                                  'gym_viewport_lines_changed', 'gym_full_lines_changed',
                                                  'screenshot_max_pix_share', 'screenshot_size_mismatch',
                                                  'removed_value_fate', 'removed_value_elsewhere', 'removed_value_nearby_full',
                                                  'removed_value_fate_examples')}
            s[e]['cells'][b]['examples'] = {k: v[:2] for k, v in c['examples'].items()}
    json.dump(s, open(f'{outroot}/summary.json', 'w'), indent=1)
    print(f'{outroot}/summary.json')


# ----------------------------------------------------------------------------- validate
def cmd_validate(envname, outdir, traj_root, n_tasks, viewport):
    """Fidelity of the capture against recorded runs: capture the clean start page of N tasks that
    have a recorded clean trajectory (fresh session, fresh browser each, as the harness does), then
    for each index the recorded step 1 acted on, check that the captured selector map has that index
    with the recorded tag and leading text (from the action result 'Clicked <tag> "<text>..."').
    Index = CDP backend node id, so a match means the same DOM was built in the same order.
    content_match: an element in the captured selector map has the recorded tag, the recorded leading
    text (first 30 characters, whitespace normalised) and the recorded aria-label prefix (20 characters,
    empty if none was recorded); index_match additionally requires the same index."""
    trajs = sorted(glob.glob(f'{traj_root}/{envname}_*__clean/trajectory.json'))
    if envname == 'patient_portal':
        trajs = sorted(glob.glob(f'{traj_root}/pp_*__clean/trajectory.json'))
    tasks = [os.path.basename(os.path.dirname(t))[:-len('__clean')] for t in trajs][:n_tasks]
    os.makedirs(outdir, exist_ok=True)
    tf = f'{outdir}/tasks.txt'
    open(tf, 'w').write('\n'.join(tasks))
    if not glob.glob(f'{outdir}/*.bu.json'):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), '_capture', envname, outdir, '--task-file', tf,
                            '--viewport', f'{viewport[0]}x{viewport[1]}'], cwd=ROOT, capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=ROOT))
        if r.returncode:
            raise SystemExit(r.stderr[-3000:])
    rows = []
    for t in tasks:
        tr = json.load(open(f'{traj_root}/{t}__clean/trajectory.json'))
        steps = tr['agent'].get('trajectory') or []
        if not steps or not os.path.exists(f'{outdir}/{t}.bu.json'):
            continue
        sel = {e['index']: e for e in json.load(open(f'{outdir}/{t}.bu.json'))['selector_map']}
        s0 = steps[0]
        norm = lambda x: re.sub(r'\s+', ' ', x or '').strip()
        for j, raw in enumerate(s0.get('raw_actions') or []):
            name, args = list(raw.items())[0]
            if not isinstance(args, dict) or 'index' not in args:
                continue
            results = s0.get('action_results') or []
            ec = ((results[j] if j < len(results) else {}) or {}).get('extracted_content') or ''
            m = re.match(r'Clicked (\w+)((?: [\w-]+=[^"]*?)*?)(?: "(.*?)(?:\.\.\.)?")?(?: id=\S+| name=\S+)*(?: aria-label=(.{1,20}))?$', ec, re.S)
            if not m:
                rows.append({'task': t, 'action': name, 'index': args['index'], 'recorded': ec[:120], 'parsed': False})
                continue
            tag, text, al = m.group(1), norm(m.group(3)), (m.group(4) or '')
            cands = [e for e in sel.values() if e['tag'] == tag and norm(e['text'])[:len(text)] == text[:30]
                     and (e.get('aria_label') or '')[:20] == al]
            rows.append({'task': t, 'action': name, 'index': args['index'], 'recorded': ec[:120], 'parsed': True,
                         'tag': tag, 'text': text, 'aria_label20': al, 'content_match': bool(cands),
                         'index_match': args['index'] in sel and sel[args['index']] in cands,
                         'captured': [f"[{e['index']}]<{e['tag']}> {e['text'][:40]} | {e.get('aria_label')}" for e in cands[:2]]})
    n = len(rows)
    summ = {'env': envname, 'tasks': len(tasks), 'indexed_actions_step1': n,
            'parsed_click_results': sum(r['parsed'] for r in rows),
            'content_match': sum(bool(r.get('content_match')) for r in rows),
            'index_match': sum(bool(r.get('index_match')) for r in rows)}
    json.dump({'summary': summ, 'rows': rows}, open(f'{outdir}/validate.json', 'w'), indent=1)
    print(json.dumps(summ))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['drive', '_capture', 'diff', 'summary', 'validate'])
    ap.add_argument('env')
    ap.add_argument('out', nargs='?')
    ap.add_argument('more', nargs='*')
    ap.add_argument('--kinds', default='none,landmarks,headings,names,labels,alt,tableheads')
    ap.add_argument('--clean', type=int, default=2)
    ap.add_argument('--tasks', type=int, default=2)
    ap.add_argument('--viewport', default='1280x720')
    ap.add_argument('--gate', default='/tmp/amt-syn/bw-gate/final')
    ap.add_argument('--task-file')
    ap.add_argument('--traj', default=os.path.expanduser('~/.hf-stage-bw/gemini_3_1_pro/tasks'))
    a = ap.parse_args()
    vp = tuple(int(x) for x in a.viewport.split('x'))
    if a.cmd == 'drive':
        cmd_drive(a.env, a.out, [k for k in a.kinds.split(',') if k], a.clean, a.tasks, vp)
    elif a.cmd == '_capture':
        cmd_capture_inner(a.env, a.out, a.tasks, vp, a.task_file)
    elif a.cmd == 'validate':
        cmd_validate(a.env, a.out, a.traj, a.tasks, vp)
    elif a.cmd == 'diff':
        cmd_diff(a.env, a.out, a.gate)
    else:  # summary OUT ENV...: here `env` holds OUT and `out` + `more` the envs
        cmd_summary(a.env, [a.out] + a.more)


if __name__ == '__main__':
    main()
