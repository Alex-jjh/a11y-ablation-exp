#!/usr/bin/env python3
"""Functional equivalence of a source-level defect variant: does every mouse click and key press
on the captured pages have the same effect as on the clean build?

Question. variant_gate.py showed that each passing env x kind variant looks the same at rest
(pixels, boxes, sizes). That says nothing about what happens when a sighted mouse or keyboard
user acts. This script replays the same actions on clean and variant and compares the effects.

Pages. The same pages as variant_gate.py: the start pages of the env's first 2 tasks (sorted
task ids) and the env's static routes (ROUTES / auto_routes of variant_gate.py), opened in a
session of the first task. Every trial opens its page in a NEW backend session (POST
/api/env/<env>/session, seed None = the seed BrowserGym uses) and a NEW browser context, so no
backend or browser state (cookies, localStorage) carries over between trials. Viewport 1280x720.
The page's Date starts at a fixed instant on every load (DATE_T0) and then runs, so relative
times ("2 min ago") are the same in every run. Navigations to other hosts are blocked and recorded.

Targets (enumerated once, on the clean0 build, then fixed for every build).
  An element is a candidate if (a) Chrome's accessibility tree gives it an interactive role
  (INTERACTIVE_ROLES), (b) its React props carry a click/mouse/pointer handler (React delegates
  events to the root, so per-element listeners are not visible to getEventListeners), (c) its
  computed cursor is `pointer` and its parent's is not (cursor is inherited), or (d) it is a
  <label> (BrowserGym marks labels clickable). It must have a box, be visible, and a hit test at
  its click point (centre of its first client rect, after scrolling the page so the point is at
  viewport y=360 if it is below the fold) must land on it or inside it. Candidates whose click
  points hit the same deepest element are merged (the innermost is kept). Kept per page: up to
  --max-clicks targets; if there are more, at least 3/4 of the cap go to candidates whose click
  point is in the first viewport and the rest to below-fold candidates, each part evenly spaced
  in document order (spread()). Buttons for the keyboard trials:
  focusable candidates with AX role button (or <button>), first viewport first, up to --max-keys.
  Element identity is the index in document.querySelectorAll('*'), stable across builds because
  the gate found the DOM aligned one to one with clean (same count, same order).

Trials per page.
  click:<i>   scroll as above, mouse click at the stored page coordinates.
  enter:<i>, space:<i>   focus element i with element.focus(), press Enter / Space.
  tab         from a fresh load, press Tab up to min(focusable + 2, 60) times; record the
              focused element after each press.
Effect signature (click/enter/space):
  hit       element at the click point before the click (index); focused_ok for key trials
  url       URL after, with the session id removed (evaluate also replaces epoch-ms values by {ts})
  same_doc  whether the document survived (a full reload or navigation ends the observer)
  muts      MutationObserver records (childList, attributes, characterData) from the action until
            the network has been idle for 400 ms (max 5 s), plus 2 frames; counts agree if
            |a-b| <= max(5, 0.5 max(a,b)) (tolerance set from clean0 vs clean1, see muts_close)
  reqs      backend requests (same origin, path under /api/) made after the action: sorted
            "METHOD path?query status", session id replaced by {sid}
  dialogs   visible dialog/menu/listbox/tooltip/popover elements (role or tag) by index;
            js_dialogs: alert/confirm/prompt type and text (accepted); popups: new pages opened;
            ext: blocked navigations to other hosts
  fixed     count of visible position:fixed elements
  focus     document.activeElement after (index)
  n_el      element count after
  console   new console errors (normalised)
  pixels    viewport screenshot after the action (animations disabled, caret hidden) compared
            with the clean0 screenshot of the same trial: changed pixels (summed RGB difference
            > 30, as in variant_gate.py), boxes of loaded <img> elements excluded (their rasters
            vary between identical builds on amazon); 8x8 changed-block mask stored for clean1
Comparison (evaluate). For every trial and field, clean1 vs clean0 says whether the field is
stable. A variant mismatch is a stable field that differs from clean0, or an unstable field
whose variant value is outside {clean0, clean1} (muts: outside the clean range and tolerance; pixels:
changed blocks outside the clean1 change region of the trial, grown by one block, unioned with
the env noise region: blocks changed in any clean1 trial whose change was small, <= 921 px). A
trial whose screenshot differs only because the action scrolls the page and the scroll position at
the screenshot differs (scroll_after) is unresolved, not a mismatch. Flagged trials (mismatch or
unresolved) are retested by `recheck`, which decides confirmed or cleared. The `none` sham is
evaluated the same way and estimates the false-mismatch rate. Mismatches the kind implies are
classed as expected: for `labels`, a click on a <label> whose `for` was removed no longer
focuses its control (focus, and what follows from it: pixels of the focus ring, muts, the
scroll that brings a focused control into view).

Usage (BreakingWeb venv python; BW_ROOT = a private BreakingWeb checkout, BW_PORT = backend port
on 127.0.0.1; PATH with node 24.20.0 and pnpm 10.15.0, BREAKINGWEB_AUTO_BUILD_FRONTENDS=0):
  click_effect.py drive ENV OUT [--kinds k1,k2,...] [--max-clicks 40] [--max-keys 8]
        builds clean twice (clean0, clean1) and each kind (codemod.py on env + shared sources),
        runs all trials on each build, restores the sources after every variant and at the end,
        then rebuilds clean. A kind whose built bundle is byte-identical to clean0 is not run
        (recorded as identical_bundle); the `none` sham is always run (a third clean run, made
        later, judged like a variant: its mismatches estimate the false-mismatch rate).
        --workers N (default 2) trial processes share the build's server.
        Kind `pc_break` is a positive control of the comparison (see pc_break()).
  click_effect.py evaluate ENV OUT     -> OUT/<env>/function.json, prints per-kind verdicts
  click_effect.py recheck ENV OUT --kind KIND [--n 3]
        retests the trials the cell flagged (mismatch or unresolved): rebuilds clean and the variant
        and runs each flagged trial n times on each with a longer settle (network idle 1 s, cap 15 s,
        scroll position stable). Confirmed = some field takes values in the variant runs that no clean
        run takes, or every variant screenshot is further from the first clean screenshot than any other
        clean screenshot is (loaded-image boxes excluded). -> OUT/<env>/recheck_<kind>.json; rerun
        evaluate to apply it. --judge-only recomputes the verdicts from the runs on disk.
  click_effect.py summary OUT          -> OUT/summary.json, prints the table
Outputs: OUT/<env>/targets.json (pages, targets, keyboard buttons); OUT/<env>/<build>/trials.jsonl
(one record per trial); OUT/<env>/clean0/shots/*.png (reference screenshots); OUT/<env>/clean1/
masks.npz (clean-vs-clean block masks); OUT/<env>/<kind>/mismatch_shots/ (variant screenshots of
pixel mismatches). OUT e.g. /tmp/amt-syn/bw-fx.
"""
import argparse
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemod  # noqa: E402
import variant_gate as vg  # noqa: E402  (build, restore, routes; BW_ROOT/BW_PORT read there)

ROOT, PORT = vg.ROOT, vg.PORT
KINDS = ['none', 'landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads']
TOL = 30
BLOCK = 8
DATE_T0 = 1793437200000  # 2026-10-30T09:00:00Z
INTERACTIVE_ROLES = {'button', 'link', 'checkbox', 'radio', 'textbox', 'searchbox', 'combobox', 'listbox', 'option',
                     'menuitem', 'menuitemcheckbox', 'menuitemradio', 'tab', 'switch', 'slider', 'spinbutton',
                     'treeitem', 'LabelText', 'DisclosureTriangle', 'ToggleButton', 'PopUpButton', 'textField'}
MUT_EDGES = [0, 3, 20, 100, 500]
SETTLE = {'long': False}

DATE_SHIM = '''(() => { const T0 = %d, RD = Date, p0 = performance.now();
  function D(...a) { if (!new.target) return new RD(D.now()).toString(); return a.length ? new RD(...a) : new RD(D.now()); }
  D.prototype = RD.prototype; D.now = () => T0 + Math.floor(performance.now() - p0); D.parse = RD.parse; D.UTC = RD.UTC;
  Object.setPrototypeOf(D, RD); window.Date = D; })();''' % DATE_T0

ENUM_JS = r'''(args) => {
  const all = [...document.querySelectorAll('*')];
  const ax = new Set(args.ax), W = innerWidth, H = innerHeight;
  const reactClick = e => { for (const k in e) if (k.startsWith('__reactProps$')) { const p = e[k] || {};
      return !!(p.onClick || p.onMouseDown || p.onMouseUp || p.onPointerDown || p.onPointerUp || p.onDoubleClick); } return false; };
  const cand = [];
  for (let i = 0; i < all.length; i++) {
    const e = all[i], why = [];
    if (ax.has(i)) why.push('ax');
    if (reactClick(e)) why.push('react');
    const cs = getComputedStyle(e);
    if (cs.cursor === 'pointer' && !(e.parentElement && getComputedStyle(e.parentElement).cursor === 'pointer')) why.push('pointer');
    if (e.tagName === 'LABEL') why.push('label');
    if (!why.length) continue;
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const rs = e.getClientRects(); if (!rs.length) continue;
    const b = e.getBoundingClientRect(); if (b.width < 1 || b.height < 1) continue;
    const r = rs.length > 1 ? rs[0] : b; if (r.width < 1 || r.height < 1) continue;
    cand.push({i, tag: e.tagName, why, cx: r.x + r.width / 2 + scrollX, cy: r.y + r.height / 2 + scrollY,
               box: [b.x + scrollX, b.y + scrollY, b.width, b.height].map(v => Math.round(v * 10) / 10),
               text: (e.innerText || e.value || e.getAttribute('placeholder') || '').replace(/\s+/g, ' ').trim().slice(0, 60),
               focusable: e.tabIndex >= 0 && !e.disabled, disabled: !!e.disabled,
               label_for: e.tagName === 'LABEL' ? (e.htmlFor || null) : null});
  }
  const out = [];
  for (const c of cand) {
    let sy = 0;
    if (c.cy >= H || c.cx >= W) { sy = Math.max(0, Math.round(c.cy - H / 2)); }
    window.scrollTo({top: sy, left: 0, behavior: 'instant'});
    const vx = c.cx - scrollX, vy = c.cy - scrollY;
    if (vx < 0 || vy < 0 || vx >= W || vy >= H) continue;
    const hit = document.elementFromPoint(vx, vy);
    if (!hit || !(all[c.i] === hit || all[c.i].contains(hit))) continue;
    c.scroll = sy; c.fold = sy > 0; c.hit = all.indexOf(hit); c.x = Math.round(vx * 100) / 100; c.y = Math.round(vy * 100) / 100;
    out.push(c);
  }
  window.scrollTo({top: 0, left: 0, behavior: 'instant'});
  return {n_el: all.length, height: document.documentElement.scrollHeight, cand: cand.length, out,
          n_focusable: all.filter(e => e.tabIndex >= 0 && !e.disabled && e.getClientRects().length).length};
}'''

PRE_JS = r'''(args) => {
  const all = [...document.querySelectorAll('*')];
  window.__amt = {muts: 0};
  const mo = new MutationObserver(rs => { window.__amt.muts += rs.length; });
  mo.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  let hit = null;
  if (args.x !== null) { const h = document.elementFromPoint(args.x, args.y); hit = h ? all.indexOf(h) : null; }
  let focused_ok = null;
  if (args.focus !== null) { const e = all[args.focus]; if (e) e.focus(); focused_ok = !!e && document.activeElement === e; }
  return {hit, focused_ok, scrollY: Math.round(scrollY), n_el: all.length};
}'''

POST_JS = r'''() => {
  const all = [...document.querySelectorAll('*')];
  const vis = e => { const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false;
                     const cs = getComputedStyle(e); return cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const dsel = 'dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true],[role=menu],[role=listbox],[role=tooltip],[popover]';
  const dialogs = [...document.querySelectorAll(dsel)].filter(vis).map(e => all.indexOf(e));
  let fixed = 0; for (const e of all) { if (getComputedStyle(e).position === 'fixed' && vis(e)) fixed++; }
  const imgs = [...document.images].filter(i => i.complete && i.naturalWidth > 0).map(i => { const r = i.getBoundingClientRect();
      return [r.x, r.y, r.width, r.height]; }).filter(r => r[2] > 0 && r[3] > 0 && r[1] < innerHeight && r[1] + r[3] > 0);
  const ae = document.activeElement;
  return {same_doc: !!window.__amt, muts: window.__amt ? window.__amt.muts : null, dialogs, fixed,
          focus: ae ? all.indexOf(ae) : null, focus_tag: ae ? ae.tagName : null, n_el: all.length, imgs,
          scrollY: Math.round(scrollY), title: document.title};
}'''

TAB_JS = r'''() => { const all = [...document.querySelectorAll('*')]; const ae = document.activeElement;
  return ae ? [all.indexOf(ae), ae.tagName] : [null, null]; }'''


# ----------------------------------------------------------------------------- helpers
def bucket(n):
    if n is None:
        return None
    for k, e in enumerate(MUT_EDGES):
        if n <= e:
            return k
    return len(MUT_EDGES)


def tasks_of(envname):
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(f'{ROOT}/breakingweb/tasks/{envname}/*.yaml'))[:2]


class Runner:
    """One backend server (127.0.0.1:PORT) and one Chromium for the current build."""

    def __init__(self, envname, serve=True):
        sys.path.insert(0, ROOT)
        os.chdir(ROOT)
        from breakingweb.runner import start_server, wait_for_server
        from breakingweb.tasks._registry import get_task
        from playwright.sync_api import sync_playwright
        self.env = envname
        self.base = f'http://127.0.0.1:{PORT}'
        self.srv = None
        if serve:
            if wait_for_server('127.0.0.1', PORT, timeout=1):
                raise SystemExit(f'port {PORT} already serves something; choose a free BW_PORT')
            self.srv = start_server('127.0.0.1', PORT)
            if not wait_for_server('127.0.0.1', PORT, timeout=60):
                raise SystemExit('server did not start')
        self.get_task = get_task
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=True)

    def close(self):
        try:
            self.browser.close(); self.pw.stop()
        finally:
            if self.srv is not None:
                self.srv.terminate(); self.srv.wait(timeout=20)

    def session(self, task):
        from breakingweb.browsergym_task import _http_json
        td = self.get_task(task)
        c = _http_json(f'{self.base}/api/env/{td.env_id}/session', method='POST', payload={'task_id': task, 'seed': None})
        return c['session_id'], c.get('start_path', td.start_path or '/')

    def url_for(self, pg, sid, start):
        q = f'session={urllib.parse.quote(sid)}&agent_mode=1'
        if pg['route'] is None:
            return f'{self.base}/env/{self.env}{start}?{q}'
        r = pg['route']; sep = '&' if '?' in r else '?'
        return f'{self.base}/env/{self.env}/{r}{sep}{q}'

    def open(self, pg):
        """New session + new context + load; returns (ctx, page, sid, rec)."""
        sid, start = self.session(pg['task'])
        ctx = self.browser.new_context(viewport={'width': 1280, 'height': 720})
        ctx.add_init_script(DATE_SHIM)
        rec = {'reqs': [], 'ext': [], 'js_dialogs': [], 'popups': [], 'console': [], 'inflight': 0, 'last': time.time(),
               'on': False}
        base = self.base

        def route(route_):
            req = route_.request
            if req.is_navigation_request() and not req.url.startswith(base):
                if rec['on']:
                    rec['ext'].append(req.url.split('?')[0])
                return route_.abort()
            return route_.continue_()
        ctx.route(lambda u: not u.startswith(base), route)
        page = ctx.new_page()

        def norm(u):
            u = u.replace(sid, '{sid}').replace(urllib.parse.quote(sid), '{sid}')
            p = urllib.parse.urlsplit(u)
            q = '&'.join(x for x in p.query.split('&') if x and not x.startswith('session=') and x != 'agent_mode=1')
            return p.path + ('?' + q if q else '')

        def on_req(r):
            if rec['on']:
                rec['inflight'] += 1; rec['last'] = time.time()

        def on_done(r, failed=False):
            if rec['on']:
                rec['inflight'] = max(0, rec['inflight'] - 1); rec['last'] = time.time()
                if r.url.startswith(base) and '/api/' in r.url:
                    st = 'failed'
                    if not failed:
                        try:
                            st = r.response().status if r.response() else 'none'
                        except Exception:
                            st = 'none'
                    rec['reqs'].append(f'{r.method} {norm(r.url)} {st}')
        page.on('request', on_req)
        page.on('requestfinished', lambda r: on_done(r))
        page.on('requestfailed', lambda r: on_done(r, True))

        def on_dialog(d):
            if rec['on']:
                rec['js_dialogs'].append(f'{d.type}: {d.message[:80]}')
            try:
                d.accept()
            except Exception:
                pass
        page.on('dialog', on_dialog)
        page.on('console', lambda m: rec['console'].append(re.sub(r'\d+', '#', m.text)[:160])
                if rec['on'] and m.type == 'error' else None)
        page.on('pageerror', lambda e: rec['console'].append(re.sub(r'\d+', '#', str(e))[:160]) if rec['on'] else None)
        ctx.on('page', lambda p: (rec['popups'].append(norm(p.url)) if rec['on'] else None, p.close()))
        rec['norm'] = norm
        page.goto(self.url_for(pg, sid, start))
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(300)
        return ctx, page, sid, rec

    @staticmethod
    def settle(page, rec, quiet=0.4, cap=5.0):
        if SETTLE['long']:   # recheck: network idle 1 s (cap 15 s), then scrollY unchanged for 3 checks
            quiet, cap = 1.0, 15.0
        t0 = time.time()
        while time.time() - t0 < cap:
            page.wait_for_timeout(100)
            if rec['inflight'] == 0 and time.time() - rec['last'] >= quiet:
                break
        if SETTLE['long']:
            last, same = None, 0
            while same < 3 and time.time() - t0 < cap + 5:
                y = page.evaluate('() => scrollY'); same = same + 1 if y == last else 0; last = y
                page.wait_for_timeout(100)
            page.wait_for_timeout(300)
        page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')


# ----------------------------------------------------------------------------- enumerate
def spread(xs, n):
    """n items evenly spaced in document order (all of them if n >= len)."""
    if n >= len(xs):
        return list(xs)
    if n <= 0:
        return []
    return [xs[int(k * len(xs) / n)] for k in range(n)]


def page_list(R):
    tasks = tasks_of(R.env)
    pages = [{'key': t, 'task': t, 'route': None} for t in tasks]
    ctx, page, sid, rec = R.open(pages[0])
    try:
        for r in vg.ROUTES.get(R.env) or vg.auto_routes(R.env):
            if r == '@product':
                href = page.evaluate("() => { const a = [...document.querySelectorAll('a[href*=\"/product/\"]')][0]; return a ? a.getAttribute('href') : null }")
                if not href:
                    continue
                r = href.split('/env/' + R.env + '/')[-1].lstrip('/').split('?')[0]
            pages.append({'key': 'route__' + r.replace('/', '_').replace('?', '_').replace('=', '-'), 'task': tasks[0], 'route': r})
    finally:
        ctx.close()
    return pages


def ax_indices(page):
    """Document indices of elements Chrome's AX tree gives an interactive role."""
    page.evaluate("() => { const a = document.querySelectorAll('*'); for (let i = 0; i < a.length; i++) a[i].setAttribute('data-amt-i', i); }")
    cdp = page.context.new_cdp_session(page)
    nodes = cdp.send('Accessibility.getFullAXTree')['nodes']
    out = {}
    for n in nodes:
        role = (n.get('role') or {}).get('value')
        if n.get('ignored') or role not in INTERACTIVE_ROLES or 'backendDOMNodeId' not in n:
            continue
        try:
            d = cdp.send('DOM.describeNode', {'backendNodeId': n['backendDOMNodeId']})['node']
        except Exception:
            continue
        at = d.get('attributes') or []
        for k in range(0, len(at), 2):
            if at[k] == 'data-amt-i':
                out[int(at[k + 1])] = role
    cdp.detach()
    page.evaluate("() => { for (const e of document.querySelectorAll('[data-amt-i]')) e.removeAttribute('data-amt-i'); }")
    return out


def enumerate_targets(R, max_clicks, max_keys):
    pages = page_list(R)
    for pg in pages:
        ctx, page, sid, rec = R.open(pg)
        try:
            ax = ax_indices(page)
            res = page.evaluate(ENUM_JS, {'ax': list(ax)})
            page.wait_for_timeout(500)
            n_after = page.evaluate("() => document.querySelectorAll('*').length")
        finally:
            ctx.close()
        merged = {}
        for c in res['out']:
            c['role'] = ax.get(c['i'])
            prev = merged.get(c['hit'])
            if prev is None or c['i'] > prev['i']:   # innermost candidate wins
                merged[c['hit']] = c
        cs = sorted(merged.values(), key=lambda c: c['i'])
        top = [c for c in cs if not c['fold']]
        below = [c for c in cs if c['fold']]
        n_top = min(len(top), max(max_clicks - len(below), (3 * max_clicks) // 4))
        keep = spread(top, n_top) + spread(below, max_clicks - n_top)
        keep.sort(key=lambda c: c['i'])
        btn = [c for c in cs if c['focusable'] and (c['role'] in ('button', 'ToggleButton', 'PopUpButton') or c['tag'] == 'BUTTON')]
        btn = ([c for c in btn if not c['fold']] + [c for c in btn if c['fold']])[:max_keys]
        pg.update(n_el=res['n_el'], n_el_after_enum=n_after, height=res['height'], n_candidates=res['cand'],
                  n_clickable=len(cs), n_clickable_top=len(top), n_clickable_below=len(below),
                  n_focusable=res['n_focusable'], clicks=keep, keys=sorted(btn, key=lambda c: c['i']))
        print(f"  {pg['key']}: {res['cand']} candidates, {len(cs)} clickable ({len(top)} in first viewport), "
              f"{len(keep)} kept, {len(btn)} buttons, {res['n_focusable']} focusable", flush=True)
    return pages


# ----------------------------------------------------------------------------- trials
def run_trial(R, pg, kind, tgt, ref_dir, mask_store, shot_dir, mis_dir, ref_imgs=()):
    t0 = time.time()
    out = {'page': pg['key'], 'trial': f"{kind}:{tgt['i']}" if tgt else kind}
    ctx = None
    try:
        ctx, page, sid, rec = R.open(pg)
        if kind == 'tab':
            seq = []
            for _ in range(min(pg['n_focusable'] + 2, 60)):
                page.keyboard.press('Tab')
                seq.append(page.evaluate(TAB_JS))
            out.update(seq=[s[0] for s in seq], seq_tags=[s[1] for s in seq], url=rec['norm'](page.url))
            return out
        if tgt['scroll']:
            page.evaluate(f"() => window.scrollTo({{top: {tgt['scroll']}, left: 0, behavior: 'instant'}})")
            page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
        sy = page.evaluate('() => Math.round(scrollY)')
        x, y = tgt['cx'], tgt['cy'] - sy
        pre = page.evaluate(PRE_JS, {'x': x if kind == 'click' else None, 'y': y, 'focus': tgt['i'] if kind != 'click' else None})
        rec['on'] = True; rec['last'] = time.time()
        if kind == 'click':
            page.mouse.click(x, y)
        else:
            page.keyboard.press('Enter' if kind == 'enter' else ' ')
        R.settle(page, rec)
        try:
            post = page.evaluate(POST_JS)
        except Exception:   # navigation in progress
            page.wait_for_load_state('load'); page.wait_for_timeout(300)
            post = page.evaluate(POST_JS)
        rec['on'] = False
        png = page.screenshot(animations='disabled', caret='hide')
        out.update(hit=pre['hit'], focused_ok=pre['focused_ok'], scroll_before=pre['scrollY'], url=rec['norm'](page.url),
                   same_doc=post['same_doc'], muts=post['muts'], mut_bucket=bucket(post['muts']), reqs=sorted(rec['reqs']),
                   dialogs=post['dialogs'], js_dialogs=rec['js_dialogs'], popups=rec['popups'], ext=sorted(set(rec['ext'])),
                   fixed=post['fixed'], focus=post['focus'], focus_tag=post['focus_tag'], n_el=post['n_el'],
                   console=sorted(set(rec['console'])), imgs=post['imgs'], scroll_after=post['scrollY'])
        name = f"{pg['key']}__{out['trial'].replace(':', '_')}.png"
        if shot_dir:
            open(f'{shot_dir}/{name}', 'wb').write(png)
        ref = f'{ref_dir}/{name}' if ref_dir else None
        if ref and os.path.exists(ref):
            a = np.asarray(Image.open(ref).convert('RGB')); b = np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
            if a.shape != b.shape:
                out['px'] = -1
            else:
                m = np.abs(a.astype(np.int16) - b.astype(np.int16)).sum(axis=2) > TOL
                for bx in (post['imgs'] + list(ref_imgs)):
                    x0, y0 = max(0, int(bx[0])), max(0, int(bx[1]))
                    m[y0:max(y0, int(np.ceil(bx[1] + bx[3]))), x0:max(x0, int(np.ceil(bx[0] + bx[2])))] = False
                out['px'] = int(m.sum())
                if mask_store is not None or out['px']:
                    bm = vg.blocks(m)
                    if mask_store is not None:
                        mask_store[name] = bm
                    out['px_blocks'] = [int(v) for v in np.flatnonzero(bm)[:4000]]
                    out['px_bshape'] = list(bm.shape)
                if out['px'] and mis_dir:
                    open(f'{mis_dir}/{name}', 'wb').write(png)
    except Exception as e:  # recorded, compared like any other field
        out['error'] = f'{type(e).__name__}: {str(e)[:200]}'
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
        out['secs'] = round(time.time() - t0, 2)
    return out


def all_trials(pages):
    return [(pg, kind, tgt) for pg in pages for kind, tgt in
            [('tab', None)] + [('click', c) for c in pg['clicks']] + [(k, c) for c in pg['keys'] for k in ('enter', 'space')]]


def trial_key(pg, kind, tgt):
    return (pg['key'], f"{kind}:{tgt['i']}" if tgt else kind)


def cmd_work(envname, outroot, build_name, w, nw):
    """Worker: trials j with j % nw == w, against the server the parent started."""
    out = f'{outroot}/{envname}'
    pages = json.load(open(f'{out}/targets.json'))['pages']
    ref_dir = f'{out}/clean0/shots' if build_name != 'clean0' else None
    shot_dir = f'{out}/clean0/shots' if build_name == 'clean0' else None
    mis_dir = f'{out}/{build_name}/mismatch_shots' if build_name not in ('clean0', 'clean1') else None
    for d in (shot_dir, mis_dir):
        if d:
            os.makedirs(d, exist_ok=True)
    masks = {} if build_name == 'clean1' else None
    ref_trials = load_trials(f'{out}/clean0/trials.jsonl') if build_name != 'clean0' else None
    R = Runner(envname, serve=False)
    try:
        with open(f'{out}/{build_name}/trials-{w}.jsonl', 'w') as f:
            for j, (pg, kind, tgt) in enumerate(all_trials(pages)):
                if j % nw != w:
                    continue
                ri = ((ref_trials or {}).get(trial_key(pg, kind, tgt)) or {}).get('imgs') or []
                rec = run_trial(R, pg, kind, tgt, ref_dir, masks, shot_dir, mis_dir, ri)
                f.write(json.dumps(rec) + '\n'); f.flush()
        if masks is not None:
            np.savez_compressed(f'{out}/{build_name}/masks-{w}.npz', **masks)
    finally:
        R.close()


def cmd_run(envname, outroot, build_name, max_clicks, max_keys, workers):
    """Run every trial on the build currently in static/envs (called in a fresh process):
    start the server, enumerate targets on clean0, then `workers` worker processes."""
    out = f'{outroot}/{envname}'
    os.makedirs(f'{out}/{build_name}', exist_ok=True)
    R = Runner(envname)
    try:
        tpath = f'{out}/targets.json'
        if not os.path.exists(tpath):
            if build_name != 'clean0':
                raise SystemExit('targets.json missing: run clean0 first')
            pages = enumerate_targets(R, max_clicks, max_keys)
            json.dump({'pages': pages, 'max_clicks': max_clicks, 'max_keys': max_keys}, open(tpath, 'w'), indent=1)
        pages = json.load(open(tpath))['pages']
        t0 = time.time()
        env = dict(os.environ, BREAKINGWEB_CONTROLLER_SECRET=os.environ.get('BREAKINGWEB_CONTROLLER_SECRET', ''))
        procs = [subprocess.Popen([sys.executable, os.path.abspath(__file__), '_work', envname, outroot, build_name,
                                   '--worker', f'{w}/{workers}'], cwd=ROOT, env=env, stderr=subprocess.PIPE, text=True)
                 for w in range(workers)]
        errs = [p.communicate()[1] for p in procs]
        if any(p.returncode for p in procs):
            raise SystemExit('worker failed:\n' + '\n'.join(e[-2000:] for e, p in zip(errs, procs) if p.returncode))
        recs = {}
        for w in range(workers):
            for r in map(json.loads, open(f'{out}/{build_name}/trials-{w}.jsonl')):
                recs[(r['page'], r['trial'])] = r
        with open(f'{out}/{build_name}/trials.jsonl', 'w') as f:
            for pg, kind, tgt in all_trials(pages):
                f.write(json.dumps(recs[trial_key(pg, kind, tgt)]) + '\n')
        for w in range(workers):
            os.remove(f'{out}/{build_name}/trials-{w}.jsonl')
        if build_name == 'clean1':
            masks = {}
            for w in range(workers):
                masks.update(dict(np.load(f'{out}/clean1/masks-{w}.npz'))); os.remove(f'{out}/clean1/masks-{w}.npz')
            np.savez_compressed(f'{out}/clean1/masks.npz', **masks)
        n_err = sum(1 for r in recs.values() if 'error' in r)
        print(f'  {build_name}: {len(recs)} trials ({n_err} with error) in {time.time() - t0:.0f} s', flush=True)
    finally:
        R.close()


def run_subprocess(envname, outroot, build_name, a):
    r = subprocess.run([sys.executable, os.path.abspath(__file__), '_run', envname, outroot, build_name,
                        '--max-clicks', str(a.max_clicks), '--max-keys', str(a.max_keys), '--workers', str(a.workers)],
                       cwd=ROOT, text=True,
                       stdout=sys.stdout, stderr=subprocess.PIPE)
    if r.returncode:
        raise SystemExit(f'run failed for {build_name}:\n{r.stderr[-3000:]}')


def bundle_hash(envname):
    h = hashlib.sha256()
    for p in sorted(glob.glob(f'{ROOT}/breakingweb/static/envs/{envname}/**', recursive=True)):
        if os.path.isfile(p):
            h.update(p.encode()); h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


def pc_break(src_dirs):
    """Positive control (known answer): break function without touching markup or look. In env and
    shared .tsx files, in sorted file order, every 2nd <button> start tag gets its onClick renamed to
    onDoubleClick (a single click then does nothing), and every 2nd <a>/<Link>/<NavLink> start tag gets
    tabIndex={-1} (it leaves the Tab order). The comparison must flag these."""
    n = {'button_onclick': 0, 'link_tabindex': 0}
    cnt = {'b': 0, 'a': 0}
    for src in src_dirs:
        for f in sorted(codemod.tsx_files(src)):
            s = open(f).read()

            def btn(m):
                if 'onClick=' not in m.group(0):
                    return m.group(0)
                cnt['b'] += 1
                if cnt['b'] % 2:
                    return m.group(0)
                n['button_onclick'] += 1
                return m.group(0).replace('onClick=', 'onDoubleClick=', 1)

            def lnk(m):
                if 'tabIndex' in m.group(0):
                    return m.group(0)
                cnt['a'] += 1
                if cnt['a'] % 2:
                    return m.group(0)
                n['link_tabindex'] += 1
                return re.sub(r'^<(a|Link|NavLink)\b', lambda x: f'<{x.group(1)} tabIndex={{-1}}', m.group(0))
            t = re.sub(r'<button\b' + codemod.TAG_BODY, btn, s)
            t = re.sub(r'<(?:a|Link|NavLink)\b(?=[\s>])' + codemod.TAG_BODY, lnk, t)
            if t != s:
                open(f, 'w').write(t)
    return n


def cmd_drive(envname, outroot, kinds, a):
    out = f'{outroot}/{envname}'
    os.makedirs(out, exist_ok=True)
    mpath = f'{out}/builds.json'
    meta = json.load(open(mpath)) if os.path.exists(mpath) else {}
    vg.restore(envname)
    try:
        for name in ['clean0', 'clean1'] + kinds:
            if name in meta and meta[name].get('done'):
                continue
            vg.restore(envname)
            rec = {}
            if name == 'pc_break':
                rec['codemod'] = pc_break([f'{vg.ENVROOT}/{envname}/src', f'{vg.ENVROOT}/shared/src'])
            elif name not in ('clean0', 'clean1'):
                rec['codemod'] = {'env': codemod.rewrite(f'{vg.ENVROOT}/{envname}/src', name),
                                  'shared': codemod.rewrite(f'{vg.ENVROOT}/shared/src', name)}
            ok, log = vg.build(envname)
            rec['build_ok'] = ok
            if not ok:
                rec['build_log_tail'] = log[-1500:]
            else:
                rec['bundle'] = bundle_hash(envname)
                if name not in ('clean0', 'clean1', 'none') and rec['bundle'] == meta.get('clean0', {}).get('bundle'):
                    rec['identical_bundle'] = True
                else:
                    print(f'=== {envname} {name} {time.strftime("%H:%M:%S")}', flush=True)
                    run_subprocess(envname, outroot, name, a)
            rec['done'] = True
            meta[name] = rec
            vg.restore(envname)
            json.dump(meta, open(mpath, 'w'), indent=1)
    finally:
        vg.restore(envname)
        vg.build(envname)


# ----------------------------------------------------------------------------- evaluate
SMALL_PX = 921   # 0.1% of the 1280x720 viewport
FIELDS = ['error', 'hit', 'focused_ok', 'url', 'same_doc', 'muts', 'reqs', 'dialogs', 'js_dialogs', 'popups', 'ext',
          'fixed', 'focus', 'n_el', 'console', 'px']


TS = re.compile(r'\b17\d{11}\b')   # epoch milliseconds (the pages' Date starts at DATE_T0)


def load_trials(p):
    """Trial records; epoch-ms timestamps in URLs and request paths (gmail and reddit search add
    `_t=<Date.now()>`) are replaced by {ts}."""
    if not os.path.exists(p):
        return None
    out = {}
    for r in map(json.loads, open(p)):
        if isinstance(r.get('url'), str):
            r['url'] = TS.sub('{ts}', r['url'])
        if r.get('reqs'):
            r['reqs'] = sorted(TS.sub('{ts}', x) for x in r['reqs'])
        out[(r['page'], r['trial'])] = r
    return out


def muts_close(a, b):
    """Mutation counts agree within the tolerance set from clean0 vs clean1 (largest ratio seen
    1.67 apart from one booking trial): |a-b| <= max(5, 0.5 * max(a, b))."""
    if a is None or b is None:
        return a == b
    return abs(a - b) <= max(5, 0.5 * max(a, b))


def cmd_evaluate(envname, outroot):
    out = f'{outroot}/{envname}'
    meta = json.load(open(f'{out}/builds.json'))
    tj = json.load(open(f'{out}/targets.json'))
    tinfo = {}
    for pg in tj['pages']:
        for c in pg['clicks'] + pg['keys']:
            tinfo[(pg['key'], c['i'])] = c
    c0, c1 = load_trials(f'{out}/clean0/trials.jsonl'), load_trials(f'{out}/clean1/trials.jsonl')
    masks = dict(np.load(f'{out}/clean1/masks.npz')) if os.path.exists(f'{out}/clean1/masks.npz') else {}
    # env noise region: blocks changed in any clean1-vs-clean0 trial with a small change (<= SMALL_PX
    # pixels), grown by one block. Large clean differences (a timing-dependent state) stay per trial.
    env_region = None
    for name, cm in masks.items():
        c1r = c1.get(tuple(name[:-4].rsplit('__', 1)[:1]) + (name[:-4].rsplit('__', 1)[1].replace('_', ':', 1),), {})
        if 0 < (c1r.get('px') or 0) <= SMALL_PX:
            env_region = cm.copy() if env_region is None else (env_region | cm if env_region.shape == cm.shape else env_region)
    env_region = vg.grow(env_region).ravel() if env_region is not None else None
    res = {'n_pages': len(tj['pages']), 'n_trials': len(c0),
           'trials_by_type': {t: sum(1 for k in c0 if k[1].split(':')[0] == t) for t in ('click', 'enter', 'space', 'tab')},
           'n_clickable_total': sum(p['n_clickable'] for p in tj['pages']),
           'n_clicks_kept': sum(len(p['clicks']) for p in tj['pages']),
           'n_keys_kept': sum(len(p['keys']) for p in tj['pages']), 'calibration': {}, 'cells': {}}
    # calibration: clean1 vs clean0
    unstable = {}
    for k, a in c0.items():
        b = c1.get(k, {})
        flds = ['seq'] if k[1] == 'tab' else FIELDS
        for f_ in flds:
            va, vb = a.get(f_), b.get(f_)
            if f_ == 'px':
                vb = b.get('px', 0); va = 0
            if f_ == 'muts' and muts_close(va, vb):
                continue
            if va != vb:
                unstable.setdefault(k, set()).add(f_)
    cal = {}
    for k, fs in unstable.items():
        for f_ in fs:
            cal[f_] = cal.get(f_, 0) + 1
    res['calibration'] = {'trials_with_unstable_field': len(unstable), 'by_field': cal,
                          'examples': [{'page': k[0], 'trial': k[1], 'fields': sorted(fs),
                                        'clean0': {f_: c0[k].get(f_) for f_ in fs if f_ != 'px'},
                                        'clean1': {f_: c1.get(k, {}).get(f_) for f_ in fs}} for k, fs in list(unstable.items())[:15]]}
    for kind in [k for k in meta if k not in ('clean0', 'clean1')]:
        m = meta[kind]
        cell = {'build_ok': m.get('build_ok'), 'codemod': m.get('codemod')}
        if m.get('identical_bundle'):
            cell.update(verdict='PRESERVED (identical bundle)', identical_bundle=True)
            res['cells'][kind] = cell; continue
        v = load_trials(f'{out}/{kind}/trials.jsonl')
        if not m.get('build_ok') or v is None:
            cell['verdict'] = 'NOT RUN'; res['cells'][kind] = cell; continue
        mism, expected, unresolved = [], [], []
        rc_path = f'{out}/recheck_{kind}.json'
        rc = json.load(open(rc_path)) if os.path.exists(rc_path) else None
        for k, a in c0.items():
            b = v.get(k)
            if b is None:
                mism.append({'page': k[0], 'trial': k[1], 'fields': ['missing']}); continue
            uf = unstable.get(k, set())
            bad = []
            flds = ['seq'] if k[1] == 'tab' else FIELDS
            for f_ in flds:
                if f_ == 'px':
                    px = b.get('px', 0)
                    if px == 0:
                        continue
                    if px < 0:
                        bad.append(f_); continue
                    name = f"{k[0]}__{k[1].replace(':', '_')}.png"
                    cm = masks.get(name) if 'px' in uf else None
                    region = vg.grow(cm).ravel() if cm is not None and b.get('px_bshape') == list(cm.shape) else None
                    if env_region is not None and b.get('px_bshape') and len(env_region) == b['px_bshape'][0] * b['px_bshape'][1]:
                        region = env_region if region is None else (region | env_region)
                    if region is not None and all(region[i] for i in b.get('px_blocks', [])):
                        continue
                    bad.append(f_); continue
                va, vb = a.get(f_), b.get(f_)
                if va == vb or (f_ == 'muts' and muts_close(va, vb)):
                    continue
                alt = c1.get(k, {}).get(f_)
                if f_ in uf:
                    if f_ == 'muts' and None not in (va, vb, alt) and (min(va, alt) <= vb <= max(va, alt) or muts_close(alt, vb)):
                        continue
                    if vb == alt:
                        continue
                bad.append(f_)
            if a.get('scroll_after') != b.get('scroll_after') and k[1] != 'tab':
                bad.append('scroll_after')
            if not bad:
                continue
            ti = tinfo.get((k[0], int(k[1].split(':')[1]))) if ':' in k[1] else None
            item = {'page': k[0], 'trial': k[1], 'fields': bad, 'target': ({x: ti.get(x) for x in ('tag', 'role', 'text', 'why', 'label_for')} if ti else None),
                    'clean0': {f_: a.get(f_) for f_ in bad if f_ not in ('px',)}, 'variant': {f_: b.get(f_) for f_ in bad}}
            if 'px' in bad:
                item['variant']['px_share'] = round(b.get('px', 0) / (1280 * 720), 5)
            if kind == 'labels' and ti and ti['tag'] == 'LABEL' and ti.get('label_for') and \
                    set(bad) <= {'focus', 'px', 'muts', 'fixed', 'dialogs', 'scroll_after'} and 'focus' in bad:
                item['class'] = 'expected: label click no longer focuses its control (F68)'
                expected.append(item)
            elif 'scroll_after' in bad and a.get('scroll_before') != a.get('scroll_after') and \
                    set(bad) <= {'scroll_after', 'px'}:
                item['class'] = 'unresolved: the action scrolls the page and the screenshot caught the scroll at another point'
                unresolved.append(item)
            else:
                mism.append(item)
        if rc is not None:   # retest of the flagged trials (cmd_recheck): keep only confirmed ones
            conf = {(x['page'], x['trial']): x for x in rc['trials'] if x['verdict'] == 'confirmed'}
            for x in mism + unresolved:
                x['recheck'] = rc_lookup(rc, x)
            cleared = [x for x in mism + unresolved if (x['page'], x['trial']) not in conf]
            mism = [x for x in mism + unresolved if (x['page'], x['trial']) in conf]
            unresolved = []
            cell['recheck'] = {'n_rechecked': len(rc['trials']), 'n_confirmed': len(conf), 'n_cleared': len(cleared),
                               'n_runs': rc['n'], 'cleared_examples': cleared[:10]}
        n_unstable_trials = sum(1 for k in c0 if k in unstable)
        cell.update(n_trials=len(c0), n_mismatch=len(mism), n_expected=len(expected), n_unresolved=len(unresolved),
                    unresolved=unresolved[:20],
                    mismatch_by_field={f_: sum(1 for x in mism if f_ in x['fields']) for f_ in FIELDS + ['seq', 'missing']
                                       if any(f_ in x['fields'] for x in mism)},
                    mismatch_by_type={t: sum(1 for x in mism if x['trial'].split(':')[0] == t) for t in ('click', 'enter', 'space', 'tab')},
                    mismatches=mism[:200], expected=expected[:60], n_unstable_trials=n_unstable_trials,
                    secs=round(sum(r.get('secs', 0) for r in v.values())))
        cell['verdict'] = ('MISMATCH' if mism else 'UNRESOLVED' if unresolved else
                           'PRESERVED except expected' if expected else 'PRESERVED')
        res['cells'][kind] = cell
    json.dump(res, open(f'{out}/function.json', 'w'), indent=1)
    print(f"{envname}: {res['n_pages']} pages, {res['n_trials']} trials {res['trials_by_type']}; "
          f"clean-vs-clean unstable trials {len(unstable)} {cal}")
    for kind, c in res['cells'].items():
        print(f"  {kind:12s} {c['verdict']:28s} mism={c.get('n_mismatch')} unres={c.get('n_unresolved')} expected={c.get('n_expected')} "
              f"{c.get('mismatch_by_field', '')} {c.get('mismatch_by_type', '')}")
    return res


def rc_lookup(rc, x):
    for t in rc['trials']:
        if t['page'] == x['page'] and t['trial'] == x['trial']:
            return {k: t[k] for k in ('verdict', 'fields_confirmed', 'clean', 'variant') if k in t}
    return None


RC_FIELDS = ['error', 'hit', 'focused_ok', 'url', 'same_doc', 'muts', 'reqs', 'dialogs', 'js_dialogs', 'popups', 'ext',
             'fixed', 'focus', 'n_el', 'console', 'scroll_after']


def _rc_run(envname, outroot, build_name, keys, n, kind):
    """Run the given trials n times each on the current build, with the long settle; screenshots kept
    in OUT/<env>/recheck/<kind>/<clean|kind>/<rep>/."""
    out = f'{outroot}/{envname}'
    pages = {p['key']: p for p in json.load(open(f'{out}/targets.json'))['pages']}
    d = f'{out}/recheck/{kind}/{build_name}'
    os.makedirs(d, exist_ok=True)
    SETTLE['long'] = True
    R = Runner(envname)
    res = []
    try:
        for rep in range(n):
            for page_key, trial in keys:
                pg = pages[page_key]
                kind, _, idx = trial.partition(':')
                tgt = next((c for c in pg['clicks'] + pg['keys'] if str(c['i']) == idx), None) if idx else None
                sd = f'{d}/{rep}'; os.makedirs(sd, exist_ok=True)
                r = run_trial(R, pg, kind, tgt, None, None, sd, None)
                r['rep'] = rep
                res.append(r)
    finally:
        R.close()
    json.dump(res, open(f'{d}/trials.json', 'w'))


def cmd_recheck(envname, outroot, kind, n):
    """Retest the trials a cell flagged (mismatch or unresolved): build clean, run each flagged trial
    n times with the long settle; build the variant, run them n times. A trial is confirmed when some
    field takes values in the variant runs that no clean run takes (muts: outside the clean range and
    tolerance), or when every variant screenshot differs from the first clean screenshot by more pixels
    than any other clean screenshot does. Otherwise it is cleared (the flag was run-to-run noise)."""
    out = f'{outroot}/{envname}'
    fj = json.load(open(f'{out}/function.json'))['cells'][kind]
    items = (fj.get('mismatches') or []) + (fj.get('unresolved') or [])
    if fj.get('n_mismatch', 0) > len(fj.get('mismatches') or []):
        raise SystemExit('more mismatches than listed; raise the list cap first')
    keys = sorted({(x['page'], x['trial']) for x in items})
    if not keys:
        print('nothing to recheck'); return
    vg.restore(envname)
    try:
        for build_name in ('clean', kind):
            vg.restore(envname)
            if build_name == 'pc_break':
                pc_break([f'{vg.ENVROOT}/{envname}/src', f'{vg.ENVROOT}/shared/src'])
            elif build_name != 'clean':
                codemod.rewrite(f'{vg.ENVROOT}/{envname}/src', kind); codemod.rewrite(f'{vg.ENVROOT}/shared/src', kind)
            ok, log = vg.build(envname)
            if not ok:
                raise SystemExit(f'build failed: {log}')
            r = subprocess.run([sys.executable, os.path.abspath(__file__), '_rc', envname, outroot, build_name, '--n', str(n), '--kind', kind,
                                '--keys', json.dumps(keys)], cwd=ROOT, text=True, stderr=subprocess.PIPE)
            if r.returncode:
                raise SystemExit(r.stderr[-3000:])
    finally:
        vg.restore(envname)
        vg.build(envname)
    judge_recheck(envname, outroot, kind, n, keys)


def judge_recheck(envname, outroot, kind, n, keys):
    """Verdicts from the recheck runs on disk (also: recheck --judge-only). Pixels inside the boxes
    of loaded <img> elements in either screenshot are left out, as in the main comparison."""
    out = f'{outroot}/{envname}'
    cl = json.load(open(f'{out}/recheck/{kind}/clean/trials.json')); va = json.load(open(f'{out}/recheck/{kind}/{kind}/trials.json'))
    shot = lambda b, rep, pk, tr: f"{out}/recheck/{kind}/{b}/{rep}/{pk}__{tr.replace(':', '_')}.png"

    recs = {(b, r['rep'], r['page'], r['trial']): r for b, R_ in (('clean', cl), (kind, va)) for r in R_}

    def px(p1, p2, r1, r2):
        if not (os.path.exists(p1) and os.path.exists(p2)):
            return None
        a = np.asarray(Image.open(p1).convert('RGB')); b = np.asarray(Image.open(p2).convert('RGB'))
        if a.shape != b.shape:
            return -1
        m = np.abs(a.astype(np.int16) - b.astype(np.int16)).sum(axis=2) > TOL
        for bx in (r1 or {}).get('imgs', []) + (r2 or {}).get('imgs', []):
            x0, y0 = max(0, int(bx[0])), max(0, int(bx[1]))
            m[y0:max(y0, int(np.ceil(bx[1] + bx[3]))), x0:max(x0, int(np.ceil(bx[0] + bx[2])))] = False
        return int(m.sum())
    trials = []
    for pk, tr in keys:
        C = [r for r in cl if (r['page'], r['trial']) == (pk, tr)]; V = [r for r in va if (r['page'], r['trial']) == (pk, tr)]
        conf = []
        flds = ['seq'] if tr == 'tab' else RC_FIELDS
        for f_ in flds:
            cv = [json.dumps(r.get(f_), sort_keys=True) for r in C]
            vv = [json.dumps(r.get(f_), sort_keys=True) for r in V]
            if f_ == 'muts':
                cm = [r.get('muts') for r in C]; vm = [r.get('muts') for r in V]
                if None in cm + vm:
                    if set(map(str, vm)) - set(map(str, cm)):
                        conf.append(f_)
                    continue
                lo, hi = min(cm), max(cm)
                if all(not (lo <= m <= hi) and not any(muts_close(c, m) for c in cm) for m in vm):
                    conf.append(f_)
                continue
            if f_ in ('url', 'reqs'):
                cv = [TS.sub('{ts}', x) for x in cv]; vv = [TS.sub('{ts}', x) for x in vv]
            if not set(vv) & set(cv):
                conf.append(f_)
        if tr != 'tab':
            ref = shot('clean', 0, pk, tr)
            r0 = recs.get(('clean', 0, pk, tr))
            cpx = [px(ref, shot('clean', rep, pk, tr), r0, recs.get(('clean', rep, pk, tr))) for rep in range(1, n)]
            vpx = [px(ref, shot(kind, rep, pk, tr), r0, recs.get((kind, rep, pk, tr))) for rep in range(n)]
            if None not in cpx + vpx and min(vpx) > max(cpx + [0]):
                conf.append('px')
        else:
            cpx = vpx = None
        summ = lambda R_: {f_: sorted({json.dumps(r.get(f_), sort_keys=True)[:160] for r in R_}) for f_ in (conf or ['url'])}
        trials.append({'page': pk, 'trial': tr, 'verdict': 'confirmed' if conf else 'cleared', 'fields_confirmed': conf,
                       'clean': summ(C), 'variant': summ(V), 'clean_px': cpx, 'variant_px': vpx})
    json.dump({'kind': kind, 'n': n, 'trials': trials}, open(f'{out}/recheck_{kind}.json', 'w'), indent=1)
    print(f"{envname} {kind}: {len(trials)} rechecked, {sum(t['verdict'] == 'confirmed' for t in trials)} confirmed")


def cmd_summary(outroot):
    allr = {}
    for p in sorted(glob.glob(f'{outroot}/*/function.json')):
        allr[p.split('/')[-2]] = json.load(open(p))
    slim = {}
    for e, r in allr.items():
        slim[e] = {k: r[k] for k in ('n_pages', 'n_trials', 'trials_by_type', 'n_clickable_total', 'n_clicks_kept', 'n_keys_kept')}
        slim[e]['calibration'] = {k: r['calibration'][k] for k in ('trials_with_unstable_field', 'by_field')}
        slim[e]['cells'] = {k: {x: c.get(x) for x in ('verdict', 'n_mismatch', 'n_unresolved', 'n_expected', 'mismatch_by_field',
                                                     'mismatch_by_type', 'n_unstable_trials', 'identical_bundle', 'recheck_counts')}
                            for k, c in r['cells'].items()}
        for k, c in r['cells'].items():
            if c.get('recheck'):
                slim[e]['cells'][k]['recheck_counts'] = {x: c['recheck'][x] for x in ('n_rechecked', 'n_confirmed', 'n_cleared', 'n_runs')}
        slim[e]['cells_examples'] = {k: (c.get('mismatches') or [])[:6] + (c.get('expected') or [])[:3] for k, c in r['cells'].items()}
    json.dump(slim, open(f'{outroot}/summary.json', 'w'), indent=1)
    kinds = KINDS
    print('env'.ljust(16) + ''.join(k[:10].ljust(14) for k in kinds))
    for e, r in slim.items():
        row = e.ljust(16)
        for k in kinds:
            c = r['cells'].get(k)
            if not c:
                row += '-'.ljust(14); continue
            row += (f"{c['verdict'][:4]} {c.get('n_mismatch')}/{c.get('n_expected')}" if not c.get('identical_bundle') else 'ident').ljust(14)
        print(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['drive', 'evaluate', 'summary', 'recheck', '_run', '_work', '_rc'])
    ap.add_argument('env', nargs='?')
    ap.add_argument('out', nargs='?')
    ap.add_argument('build', nargs='?')
    ap.add_argument('--kinds', default=','.join(KINDS))
    ap.add_argument('--max-clicks', type=int, default=40)
    ap.add_argument('--max-keys', type=int, default=8)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--worker', default='0/1')
    ap.add_argument('--n', type=int, default=3)
    ap.add_argument('--keys', default='[]')
    ap.add_argument('--kind')
    ap.add_argument('--judge-only', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'summary':
        return cmd_summary(a.env)
    if a.cmd == 'evaluate':
        return cmd_evaluate(a.env, a.out)
    if a.cmd == '_run':
        return cmd_run(a.env, a.out, a.build, a.max_clicks, a.max_keys, a.workers)
    if a.cmd == 'recheck' and a.judge_only:
        rc = json.load(open(f'{a.out}/{a.env}/recheck_{a.kind}.json'))
        return judge_recheck(a.env, a.out, a.kind, rc['n'], [(t['page'], t['trial']) for t in rc['trials']])
    if a.cmd == 'recheck':
        return cmd_recheck(a.env, a.out, a.kind, a.n)
    if a.cmd == '_rc':
        return _rc_run(a.env, a.out, a.build, [tuple(k) for k in json.loads(a.keys)], a.n, a.kind)
    if a.cmd == '_work':
        w, nw = map(int, a.worker.split('/'))
        return cmd_work(a.env, a.out, a.build, w, nw)
    cmd_drive(a.env, a.out, [k for k in a.kinds.split(',') if k], a)


if __name__ == '__main__':
    main()
