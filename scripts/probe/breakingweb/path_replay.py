#!/usr/bin/env python3
"""Replay recorded browser-use trajectories on the clean BreakingWeb build and record, at
every step, which accessibility information is on the page and on the element acted on.

Why: the on-path dose of each defect kind (names, labels, headings, landmarks, tableheads,
alt) must be measured on the states an agent actually passes through, not on routes
(docs/feasibility/2026-10-29-breakingweb.md, "Open"). A trajectory gives the actions and
the acted-on element's aria-label, but not the page's headings, landmarks, tables or the
label association of a form control. Replaying the actions on the same seeded task and
reading the live DOM gives them, and the backend evaluator tells whether the replay
reached the same end state as the recorded run (replay fidelity).

Inputs
  TRAJ_ROOT   directory with <task>__clean/trajectory.json (e.g. ~/.hf-stage-bw/gemini_3_1_pro/tasks)
  OUT_DIR     one JSON per task is written to OUT_DIR/<task>.json (skipped if it exists)
  --tasks     optional file with one task id per line (default: every task in TRAJ_ROOT)
  --only-success   replay only runs whose recorded evaluation.success is true
  --port      backend port on 127.0.0.1 (default 8091); --workers N (default 3)
  --viewport  WxH (default 1280x720, the stock harness viewport for Gemini)
  AMT_REPLAY_LOOSE=1 (environment) for variant builds: when the recorded name matches nothing,
              match on visible text, attributes and position instead (used to check that a
              codemod variant changes exactly what the clean replay predicts)

Output per task (OUT_DIR/<task>.json)
  states[]   one per step before its first action and one after the last action: URL path,
             counts of every instance the source-level codemod would change (DOM selectors
             identical to codemod.py: h1-h6/role=heading; header/nav/main/footer/aside and
             landmark roles; th; img with alt), split into whole document and viewport, and
             the AX-tree role counts BrowserGym would serialise (heading, landmarks,
             columnheader/rowheader, named img).
  actions[]  one per recorded action: how the element was found (exact/ambiguous/missing),
             its attributes (aria-label, placeholder, id, label[for] text, wrapping label,
             visible text, alt of child images, enclosing landmark, preceding heading) and its
             accessible name from Chrome's AX tree three times: clean, with aria-label and
             aria-labelledby removed (the `names` kind), and with those plus label[for]
             removed (the `labels` kind). Attributes are removed for the measurement only
             and restored at once. `peers`: how many other visible controls of the same kind
             share the element's name before and after the removal (DOM approximation).
  replay_eval  the backend evaluator on the replayed end state; recorded_success from the
             trajectory.

Run against a private clean copy, because other probes rebuild variant bundles in the shared
checkout while they run (seen on 2026-10-30: variant_gate.py rebuilt booking during a replay):
  C=~/.workspace/_refsrc/BreakingWeb; D=/tmp/amt-syn/bw-clean
  mkdir -p $D && git -C $C archive HEAD | tar -x -C $D
  cp $C/breakingweb/app.py $D/breakingweb/app.py          # the 127.0.0.1 bind fix
  (cd $C/breakingweb/environments && for n in node_modules */node_modules; do cp -a $n $D/breakingweb/environments/$n; done)
  export PATH=$HOME/.local/share/mise/installs/node/24.20.0/bin:$HOME/.local/bin:$PATH BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
  (cd $D/breakingweb/environments && pnpm --filter @breakingweb/shared build && for e in amazon booking gmail lms patient_portal reddit robinhood; do pnpm --filter @breakingweb/$e build; done)
  cd $D && PYTHONPATH=$D $C/.venv/bin/python <this file> ~/.hf-stage-bw/gemini_3_1_pro/tasks /tmp/amt-syn/bw-path/gemini_3_1_pro --only-success

The backend binds to 127.0.0.1 only and is stopped at the end. The page is not modified
apart from the temporary attribute removals around each name measurement and a
data-amt-probe attribute used to address the element over CDP.
"""
import argparse
import glob
import json
import multiprocessing as mp
import os
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request

LM_SEL = ('header,nav,main,footer,aside,[role=banner],[role=navigation],[role=main],'
          '[role=contentinfo],[role=complementary],[role=search],[role=region]')
HEAD_SEL = 'h1,h2,h3,h4,h5,h6,[role=heading]'

PAGE_JS = r"""
(args) => {
  const LM = args.lm, HS = args.hs;
  const R = el => { if (!el.getClientRects().length) return false; const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return false;
    if (el.closest('[aria-hidden="true"]')) return false; return true; };
  const VP = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth; };
  const sel = s => [...document.querySelectorAll(s)].filter(R);
  const both = els => ({doc: els.length, vp: els.filter(VP).length});
  const heads = sel(HS), lms = sel(LM), ths = sel('th'), tables = sel('table'), imgs = sel('img');
  const ctl = 'a,button,[role=button],[role=link]';
  const altImgs = imgs.filter(i => (i.getAttribute('alt') || '').trim());
  // images whose alt is the only name source of the control around them
  const soleAlt = altImgs.filter(i => { const c = i.closest(ctl); if (!c) return false;
    if ((c.getAttribute('aria-label') || '').trim()) return false;
    return !(c.innerText || '').trim(); });
  const inCtl = altImgs.filter(i => i.closest(ctl));
  return {
    path: location.pathname.replace(/^\/env\/[^/]+/, '') || '/',
    scroll_h: document.documentElement.scrollHeight, scroll_y: Math.round(scrollY),
    headings: both(heads), heading_text: heads.slice(0, 60).map(h => (h.innerText || '').trim().slice(0, 80)),
    landmarks: both(lms), landmark_tags: lms.map(e => e.getAttribute('role') || e.tagName.toLowerCase()),
    th: both(ths), tables: both(tables),
    img: both(imgs), img_alt: both(altImgs), img_alt_in_control: both(inCtl), img_alt_sole_name: both(soleAlt),
    labels_for: sel('label[for]').length,
    controls_aria: sel('input[aria-label],textarea[aria-label],select[aria-label],input[aria-labelledby],textarea[aria-labelledby],select[aria-labelledby]').length,
    buttons_links_aria: sel('a[aria-label],button[aria-label],a[aria-labelledby],button[aria-labelledby]').length,
  };
}
"""

TARGET_JS = r"""
(el, args) => {
  const LM = args.lm, HS = args.hs;
  const t = s => (s || '').replace(/\s+/g, ' ').trim();
  const id = el.id || '';
  let labelFor = [];
  if (id) { try { labelFor = [...document.querySelectorAll('label[for="' + CSS.escape(id) + '"]')].map(l => t(l.innerText)); } catch (e) {} }
  const wrap = el.closest('label');
  const lm = el.closest(LM);
  let prevHeading = null;
  const heads = [...document.querySelectorAll(HS)];
  for (const h of heads) { if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING || h.contains(el)) prevHeading = t(h.innerText).slice(0, 80); }
  const r = el.getBoundingClientRect();
  return {
    tag: el.tagName.toLowerCase(), type: el.getAttribute('type'), role: el.getAttribute('role'),
    aria_label: el.getAttribute('aria-label'), aria_labelledby: el.getAttribute('aria-labelledby'),
    placeholder: el.getAttribute('placeholder'), title: el.getAttribute('title'), id: id,
    label_for: labelFor, label_wrap: wrap ? t(wrap.innerText).slice(0, 120) : null,
    text: t(el.innerText).slice(0, 200), child_img_alt: [...el.querySelectorAll('img')].map(i => i.getAttribute('alt')),
    landmark: lm ? (lm.getAttribute('role') || lm.tagName.toLowerCase()) : null,
    in_table: !!el.closest('table'), prev_heading: prevHeading,
    rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
  };
}
"""

PEERS_JS = r"""
(el) => {
  // Is the element still told apart from the other visible controls of its kind once the
  // defect removes its aria-label (buttons, links) or its label association (form controls)?
  // Names are approximated from the DOM: buttons/links by text content plus child img alt;
  // controls by placeholder, wrapping label text or title. Exact AX names are in `ax`.
  const t = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const R = e => e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden';
  const isCtl = ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName);
  const sel = isCtl ? 'input:not([type=hidden]),textarea,select' : 'a,button';
  const txt = e => t((e.innerText || '') + ' ' + [...e.querySelectorAll('img')].map(i => i.getAttribute('alt') || '').join(' '));
  const ctlPost = e => { const w = e.closest('label'); return t(e.getAttribute('placeholder') || (w ? w.innerText : '') || e.getAttribute('title') || ''); };
  const ctlClean = e => { const a = e.getAttribute('aria-label'); if (a && a.trim()) return t(a);
    if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return t(l.innerText); }
    return ctlPost(e); };
  const post = e => isCtl ? ctlPost(e) : txt(e);
  const clean = e => isCtl ? ctlClean(e) : (t(e.getAttribute('aria-label')) || txt(e));
  const els = [...document.querySelectorAll(sel)].filter(R).filter(e => e !== el);
  const p = post(el), c = clean(el);
  return {n_peers: els.length, same_post: p ? els.filter(e => post(e) === p).length : null,
          same_clean: c ? els.filter(e => clean(e) === c).length : null, post: p.slice(0, 120), clean: c.slice(0, 120)};
}
"""

CANDIDATES_JS = r"""
(args) => {
  const t = s => (s || '').replace(/\s+/g, '').toLowerCase();
  const R = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const tags = args.tags, name = args.name, vis = t(args.vis), out = [];
  const els = [...document.querySelectorAll(tags)].filter(R);
  els.forEach((el, i) => {
    if (args.fresh && el.hasAttribute('data-amt-used')) return;
    let score = 0;
    if (name) {
      if (el.getAttribute('aria-label') === name) score = 3;
      else if (el.getAttribute('placeholder') === name) score = 3;
      else if (el.getAttribute('aria-label') && t(el.getAttribute('aria-label')).startsWith(t(name))) score = 1;
      else if (el.getAttribute('aria-label') && t(el.getAttribute('aria-label')).replace(/[0-9]+/g, '#') === t(name).replace(/[0-9]+/g, '#')) score = 1;
    }
    if (vis) {
      const tx = t(el.innerText);
      if (tx === vis) score += 2; else if (tx.startsWith(vis)) score += 1;
    }
    if (args.checkbox && el.type === 'checkbox') score += 1;
    for (const [k, v] of Object.entries(args.attrs || {})) { if (el.getAttribute(k) === v) score += 1; else if (k === 'type' || k === 'name') score -= 5; }
    if (!name && !vis && args.anyok) score += 1;
    if (args.optval !== null && el.tagName === 'SELECT') {
      const vals = [...el.options].map(o => o.value), labs = [...el.options].map(o => t(o.text));
      if (vals.includes(args.optval)) score += 2; else if (args.optlab && labs.includes(t(args.optlab))) score += 1;
    }
    if (score > 0) { const r = el.getBoundingClientRect();
      out.push({i: i, score: score, cx: r.x + r.width / 2, cy: r.y + r.height / 2}); }
  });
  return {n: els.length, cands: out};
}
"""

ROLE_TAGS = {'button': 'button', 'link': 'a', 'textbox': 'input,textarea', 'combobox': 'select'}


def parse_ec(ec):
    """Visible text and tag from a browser-use extracted_content line."""
    ec = ec or ''
    m = re.match(r'^Clicked (\w+)', ec)
    tag = m.group(1) if m else None
    vis = None
    q = re.search(r'"(.*)"(?: aria-label=.*)?$', ec, re.S)
    if q:
        vis = q.group(1)
    trunc = bool(vis and vis.endswith('...'))
    if trunc:
        vis = vis[:-3]
    if vis is not None:
        vis = re.sub(r'\s+', ' ', vis).strip()
    return tag, vis, trunc


def select_listings(steps):
    """browser-use element index -> (DOM id, [option values]) from 'Found select dropdown' results."""
    out = {}
    for st in steps:
        for r in st.get('action_results') or []:
            ec = (r or {}).get('extracted_content') or ''
            m = re.match(r'Found select dropdown \(Index: (\d+), Type: select, ID: ([^,]*), ', ec)
            if m:
                vals = re.findall(r'^\d+: text=".*?", value="(.*?)"', ec, re.M)
                out[int(m.group(1))] = (m.group(2).strip(), vals)
    return out


def raw_index(step, j):
    ra = (step.get('raw_actions') or [])
    if j < len(ra):
        for v in ra[j].values():
            if isinstance(v, dict) and 'index' in v:
                return v['index']
    return None


def http_json(url, method='GET', payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={'Content-Type': 'application/json'} if body else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode()
        return json.loads(t) if t else {}


class Prober:
    def __init__(self, page):
        self.page = page
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.send('Accessibility.enable')

    def page_state(self):
        st = self.page.evaluate(PAGE_JS, {'lm': LM_SEL, 'hs': HEAD_SEL})
        try:
            nodes = self.cdp.send('Accessibility.getFullAXTree')['nodes']
            roles = {}
            for n in nodes:
                if n.get('ignored'):
                    continue
                r = (n.get('role') or {}).get('value')
                if r in ('heading', 'banner', 'navigation', 'main', 'contentinfo', 'complementary', 'search',
                         'region', 'form', 'columnheader', 'rowheader', 'image', 'img', 'table', 'grid'):
                    if r in ('image', 'img'):
                        nm = (n.get('name') or {}).get('value') or ''
                        r = 'img_named' if nm.strip() else 'img_unnamed'
                    roles[r] = roles.get(r, 0) + 1
            st['ax_roles'] = roles
        except Exception as e:  # AX tree is optional evidence
            st['ax_error'] = str(e)[:200]
        return st

    def ax_name(self):
        doc = self.cdp.send('DOM.getDocument', {'depth': 0})
        nid = self.cdp.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': '[data-amt-probe]'})['nodeId']
        if not nid:
            return None
        nodes = self.cdp.send('Accessibility.getPartialAXTree', {'nodeId': nid, 'fetchRelatives': False})['nodes']
        for n in nodes:
            if not n.get('ignored'):
                return (n.get('name') or {}).get('value', '')
        return nodes[0].get('name', {}).get('value', '') if nodes else None

    def names(self, handle):
        """AX name clean / without aria-label(ledby) / also without label[for]; restores attributes."""
        out = {}
        handle.evaluate("el => el.setAttribute('data-amt-probe', '1')")
        try:
            out['clean'] = self.ax_name()
            saved = handle.evaluate("""el => { const s = {al: el.getAttribute('aria-label'), alb: el.getAttribute('aria-labelledby')};
                el.removeAttribute('aria-label'); el.removeAttribute('aria-labelledby'); return s; }""")
            out['no_aria'] = self.ax_name()
            saved_for = handle.evaluate("""el => { const ids = []; if (el.id) { document.querySelectorAll('label[for="' + CSS.escape(el.id) + '"]').forEach(l => { ids.push(l); }); }
                window.__amtLabels = ids; ids.forEach(l => l.removeAttribute('for')); return ids.length; }""")
            out['no_aria_no_for'] = self.ax_name()
            handle.evaluate("""(el, s) => { if (s.al !== null) el.setAttribute('aria-label', s.al); if (s.alb !== null) el.setAttribute('aria-labelledby', s.alb);
                (window.__amtLabels || []).forEach(l => l.setAttribute('for', el.id)); window.__amtLabels = []; }""", saved)
            out['labels_for_removed'] = saved_for
        finally:
            handle.evaluate("el => el.removeAttribute('data-amt-probe')")
        return out


def locate(page, action, target, result, listing=None):
    if listing and listing[0]:
        h = page.query_selector('#' + listing[0])
        if h is not None and h.is_visible():
            return h, {'how': 'exact_id', 'n_cands': 1, 'score': 9}
    role = (target or {}).get('role')
    name = (target or {}).get('name') or ''
    ec = (result or {}).get('extracted_content') or ''
    tag, vis, trunc = parse_ec(ec)
    if role in ROLE_TAGS:
        tags = ROLE_TAGS[role]
    elif role:
        tags = role
    else:
        return None, {'how': 'no_target'}
    if tag == 'input':
        tags = 'input'
    is_checkbox = 'type=checkbox' in ec
    attrs = {}
    head = ec.split('"', 1)[0] if ec.startswith('Clicked') else ''
    for k, v in re.findall(r'\b(type|name|role)=([^\s"]+)', head):
        attrs[k] = v
    val = (action or {}).get('value') or ''
    if action.get('action') == 'fill' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', val):
        attrs['type'] = 'date'
    optval = optlab = None
    m = re.match(r'Selected option: (.*) \(value: (.*)\)\s*$', ec, re.S)
    if m:
        optlab, optval = m.group(1), m.group(2)
    res = page.evaluate(CANDIDATES_JS, {'tags': tags, 'name': name, 'vis': vis if not name else None,
                                         'checkbox': is_checkbox, 'optval': optval, 'optlab': optlab,
                                         'attrs': attrs, 'anyok': not name and not vis,
                                         'fresh': action.get('action') in ('fill', 'select')})
    cands = res['cands']
    if not cands and name and os.environ.get('AMT_REPLAY_LOOSE') == '1':
        # variant builds: the recorded aria-label may be gone; match on visible text/attributes/position
        res = page.evaluate(CANDIDATES_JS, {'tags': tags, 'name': '', 'vis': vis, 'checkbox': is_checkbox,
                                             'optval': optval, 'optlab': optlab, 'attrs': attrs, 'anyok': not vis,
                                             'fresh': action.get('action') in ('fill', 'select')})
        cands = res['cands']
    md = (result or {}).get('metadata') or {}
    x = md.get('click_x', md.get('input_x'))
    y = md.get('click_y', md.get('input_y'))
    if not cands and x is not None:
        # last resort: the element under the recorded click point, if it has the recorded tag
        h = page.evaluate_handle("(a) => { let el = document.elementFromPoint(a.x, a.y); while (el && !el.matches(a.tags)) el = el.parentElement; return el; }",
                                 {'x': x, 'y': y, 'tags': tags}).as_element()
        if h is not None:
            return h, {'how': 'point', 'n_cands': 1, 'score': 0}
    if not cands:
        return None, {'how': 'missing', 'tags': tags, 'name': name, 'vis': vis}
    best = max(c['score'] for c in cands)
    cands = [c for c in cands if c['score'] == best]
    how = 'exact' if len(cands) == 1 else 'ambiguous'
    if len(cands) > 1 and x is not None:
        cands.sort(key=lambda c: abs(c['cx'] - x) + abs(c['cy'] - y))
    handle = page.evaluate_handle("(a) => [...document.querySelectorAll(a.tags)].filter(el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')[a.i]",
                                  {'tags': tags, 'i': cands[0]['i']}).as_element()
    return handle, {'how': how, 'n_cands': len(cands), 'score': best, 'alts': [c['i'] for c in cands[1:5]], 'tags': tags}


def settle(page, ms=350):
    try:
        page.wait_for_load_state('networkidle', timeout=4000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def do_action(page, a, handle, result, listing=None, raw=None):
    kind = a.get('action')
    ec = (result or {}).get('extracted_content') or ''
    if kind == 'click':
        try:
            handle.click(timeout=4000)
        except Exception:
            handle.evaluate('el => el.click()')
    elif kind == 'fill':
        try:
            handle.fill(a.get('value', ''), timeout=4000)
        except Exception:
            handle.evaluate("(el, v) => { el.focus(); el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }", a.get('value', ''))
    elif kind == 'select':
        m = re.match(r'Selected option: (.*) \(value: (.*)\)\s*$', ec, re.S)
        if not m and ec.startswith('Available dropdown options'):
            # browser-use reported a failed selection but the recorded run's end state can still
            # contain it (React-controlled selects); apply the requested option if it is listed
            want = ((raw or {}).get('select_dropdown') or {}).get('text')
            listed = [l[2:].strip() for l in ec.splitlines() if l.startswith('- ')]
            if want is not None and want in listed:
                handle.select_option(label=want, timeout=4000)
                return 'listed_option_applied'
            return False
        if not m:
            return False
        lab, val = m.group(1), m.group(2)
        opts = handle.evaluate("el => [...el.options].map(o => [o.value, o.text.replace(/\\s+/g, ' ').trim()])")
        if any(o[0] == val for o in opts):
            handle.select_option(value=val, timeout=4000)
        elif any(o[1] == lab.strip() for o in opts):
            handle.select_option(label=lab.strip(), timeout=4000)
        elif listing and val in listing[1] and listing[1].index(val) < len(opts):
            handle.select_option(index=listing[1].index(val), timeout=4000)  # same position, data drifted
            return 'by_index'
        else:
            raise RuntimeError(f'option not found: {val!r} / {lab[:60]!r}')
    else:
        return False
    return True


def replay_task(path, out_dir, base, viewport, browser):
    d = json.load(open(path))
    task = d['task_id']
    out = f'{out_dir}/{task}.json'
    if os.path.exists(out):
        return task, 'skip'
    from breakingweb.tasks._registry import get_task
    env_id = get_task(task).env_id
    created = http_json(f'{base}/api/env/{env_id}/session', 'POST', {'task_id': task})
    sid = created['session_id']
    url = f"{base}/env/{env_id}{created.get('start_path', '/')}?session={urllib.parse.quote(sid)}&agent_mode=1"
    ctx = browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]})
    page = ctx.new_page()
    import breakingweb
    rec = {'task_id': task, 'env_id': env_id, 'breakingweb_root': os.path.dirname(os.path.dirname(breakingweb.__file__)), 'recorded_success': (d.get('evaluation') or {}).get('success'),
           'model': d['agent'].get('model'), 'viewport': viewport, 'states': [], 'actions': []}
    try:
        resp = page.goto(url)
        if resp is None or resp.status >= 400:
            raise RuntimeError(f'start page HTTP {resp.status if resp else None}: {page.inner_text("body")[:200]}')
        settle(page, 600)
        pr = Prober(page)
        steps = d['agent'].get('trajectory') or []
        listings = select_listings(steps)
        cur_path = lambda: page.evaluate("() => location.pathname.replace(/^\\/env\\/[^/]+/, '') || '/'")
        for si, s in enumerate(steps):
            expected_next = steps[si + 1].get('replay_path') if si + 1 < len(steps) else None
            st = pr.page_state(); st['step'] = s.get('step'); rec['states'].append(st)
            acts = s.get('actions') or []
            tgts = s.get('action_targets') or [{}] * len(acts)
            ress = s.get('action_results') or [{}] * len(acts)
            for j, a in enumerate(acts):
                t = tgts[j] if j < len(tgts) else {}
                r = ress[j] if j < len(ress) else {}
                kind = a.get('action')
                arec = {'step': s.get('step'), 'j': j, 'action': kind, 'target': t,
                        'ec': ((r or {}).get('extracted_content') or '')[:240], 'path': st['path']}
                if kind in ('click', 'fill', 'select', 'dropdown_options'):
                    try:
                        lst = listings.get(raw_index(s, j))
                        h, info = locate(page, a, t, r, lst)
                        arec['locate'] = info
                        if h is not None:
                            arec['el'] = h.evaluate(TARGET_JS, {'lm': LM_SEL, 'hs': HEAD_SEL})
                            try:
                                arec['peers'] = h.evaluate(PEERS_JS)
                            except Exception as e:
                                arec['peers_error'] = str(e)[:200]
                            try:
                                arec['ax'] = pr.names(h)
                            except Exception as e:
                                arec['ax_error'] = str(e)[:200]
                            if kind in ('fill', 'select'):
                                h.evaluate("el => el.setAttribute('data-amt-used', '1')")
                            if kind != 'dropdown_options':
                                ras = s.get('raw_actions') or []
                                url_before = page.url
                                arec['done'] = do_action(page, a, h, r, lst, ras[j] if j < len(ras) else None)
                                settle(page)
                                # an ambiguous navigating click: if the next recorded page is not reached,
                                # try the other candidates from the same starting URL
                                if (kind == 'click' and info.get('how') == 'ambiguous' and j == len(acts) - 1
                                        and expected_next and expected_next != st['path'] and cur_path() != expected_next):
                                    arec['retry'] = 'failed'
                                    for k, alt in enumerate(info.get('alts') or []):
                                        page.goto(url_before); settle(page, 500)
                                        h2 = page.evaluate_handle("(a) => [...document.querySelectorAll(a.tags)].filter(el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')[a.i]",
                                                                  {'tags': info['tags'], 'i': alt}).as_element()
                                        if h2 is None:
                                            continue
                                        el2 = h2.evaluate(TARGET_JS, {'lm': LM_SEL, 'hs': HEAD_SEL})
                                        try:
                                            pe2 = h2.evaluate(PEERS_JS)
                                        except Exception:
                                            pe2 = None
                                        try:
                                            ax2 = pr.names(h2)
                                        except Exception:
                                            ax2 = None
                                        do_action(page, a, h2, r)
                                        settle(page)
                                        if cur_path() == expected_next:
                                            arec['retry'] = k + 1
                                            arec['el'], arec['ax'], arec['peers'] = el2, ax2, pe2
                                            break
                    except Exception as e:
                        arec['error'] = str(e)[:300]
                elif kind == 'press':
                    try:
                        key = a.get('key') or a.get('keys') or 'Enter'
                        m = re.match(r'Sent keys: (.*)', arec['ec'])
                        page.keyboard.press((m.group(1).strip() if m else key) or 'Enter')
                        settle(page)
                    except Exception as e:
                        arec['error'] = str(e)[:300]
                elif kind == 'scroll':
                    m = re.search(r'Scrolled (down|up) (\d+)px', arec['ec'])
                    m2 = re.search(r'Scrolled (down|up) ([\d.]+) pages?', arec['ec'])
                    dy = None
                    if m:
                        dy = int(m.group(2)) * (1 if m.group(1) == 'down' else -1)
                    elif m2:
                        dy = int(float(m2.group(2)) * viewport[1]) * (1 if m2.group(1) == 'down' else -1)
                    if dy is not None:
                        page.mouse.move(viewport[0] / 2, viewport[1] / 2)
                        page.mouse.wheel(0, dy)
                        page.wait_for_timeout(300)
                elif kind == 'back':
                    try:
                        page.go_back(); settle(page)
                    except Exception as e:
                        arec['error'] = str(e)[:300]
                rec['actions'].append(arec)
            try:
                page.evaluate("() => document.querySelectorAll('[data-amt-used]').forEach(e => e.removeAttribute('data-amt-used'))")
            except Exception:
                pass
        st = pr.page_state(); st['step'] = 'end'; rec['states'].append(st)
        try:
            ev = http_json(f'{base}/api/env/{env_id}/evaluate', 'POST', {'session_id': sid})
            rec['replay_eval'] = {'success': ev.get('success'), 'score': ev.get('score'), 'reasoning': (ev.get('reasoning') or '')[:1500]}
        except Exception as e:
            rec['replay_eval'] = {'error': str(e)[:300]}
    except Exception as e:
        rec['fatal'] = traceback.format_exc()[-1500:]
    finally:
        try:
            http_json(f'{base}/api/env/{env_id}/session/{urllib.parse.quote(sid)}', 'DELETE')
        except Exception:
            pass
        ctx.close()
    json.dump(rec, open(out, 'w'))
    return task, (rec.get('replay_eval') or {}).get('success')


def worker(args):
    paths, out_dir, base, viewport = args
    from playwright.sync_api import sync_playwright
    done = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, path in enumerate(paths):
            if i and i % 40 == 0:  # bound memory of a long-lived browser
                browser.close(); browser = p.chromium.launch(headless=True)
            t0 = time.time()
            try:
                task, ok = replay_task(path, out_dir, base, viewport, browser)
            except Exception as e:
                task, ok = os.path.basename(os.path.dirname(path)), f'error {e}'
            done.append((task, ok))
            print(f'{task} {ok} {time.time() - t0:.0f}s', flush=True)
        browser.close()
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('traj_root'); ap.add_argument('out_dir')
    ap.add_argument('--tasks'); ap.add_argument('--only-success', action='store_true')
    ap.add_argument('--port', type=int, default=8091); ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--viewport', default='1280x720')
    a = ap.parse_args()
    vw, vh = (int(x) for x in a.viewport.split('x'))
    os.makedirs(a.out_dir, exist_ok=True)
    paths = sorted(glob.glob(f'{a.traj_root}/*__clean/trajectory.json'))
    if a.tasks:
        want = set(open(a.tasks).read().split())
        paths = [p for p in paths if os.path.basename(os.path.dirname(p)).rsplit('__', 1)[0] in want]
    if a.only_success:
        paths = [p for p in paths if (json.load(open(p)).get('evaluation') or {}).get('success')]
    paths = [p for p in paths if not os.path.exists(f"{a.out_dir}/{os.path.basename(os.path.dirname(p)).rsplit('__', 1)[0]}.json")]
    print(f'{len(paths)} trajectories to replay', flush=True)
    if not paths:
        return
    from breakingweb.runner import start_server, wait_for_server
    proc = start_server('127.0.0.1', a.port)
    try:
        if not wait_for_server('127.0.0.1', a.port, timeout=90):
            raise SystemExit('backend did not start')
        base = f'http://127.0.0.1:{a.port}'
        chunks = [paths[i::a.workers] for i in range(a.workers)]
        with mp.Pool(a.workers) as pool:
            res = pool.map(worker, [(c, a.out_dir, base, (vw, vh)) for c in chunks if c])
        flat = [x for r in res for x in r]
        print('replayed', len(flat), 'success', sum(1 for _, ok in flat if ok is True))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == '__main__':
    main()
