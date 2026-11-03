#!/usr/bin/env python3
"""Task-level feasibility by trajectory replay (the 'cell gate'): is a task still solvable on a
defect variant by the same mouse and keyboard input that solves it on the clean build?

Question. variant_gate.py shows a variant looks the same at rest; click_effect.py shows single
actions from rest have the same effect. Neither shows that a whole task path still works. A
successful recorded clean run is a reference solution (CTL-2 of Chen2026a: the reference
solution must be graded as solved). If the same input sequence also solves the task on the
variant, the task stays feasible for a sighted mouse user under that defect.

Method (no LLM anywhere).
  compile  On the clean build, every recorded browser-use action of a successful run is mapped
           to low-level input. The acted-on element is resolved with path_replay.locate(): the
           recorded target role+name (aria-label / placeholder / visible text from
           extracted_content) resolved to a DOM element, ties broken by distance to the recorded
           click/input coordinates (action_results metadata click_x/click_y, input_x/input_y),
           and the element under the recorded point as the fallback when no name matches.
           The recorded coordinates are not replayed raw: browser-use scrolls the element into
           view before it clicks, so they are viewport coordinates of a scroll state the replay
           does not have (`point_agrees` in the script records how often the element at the raw
           point is the resolved one). The element is then brought into view with mouse-wheel
           events at a point over its scroll container (or over a non-scrolling part of the page
           for the window), and acted on at a point of its visible box whose hit test is the
           element: click = mouse click; fill = mouse click, then the text is filled into the
           focused element (document.activeElement; Playwright fill, which also handles date
           inputs); select = mouse click, then the option is set on the focused <select>;
           press = keyboard press; scroll = wheel; back = history back. Read-only actions
           (finish, dropdown_options, find_*, search_page, wait, noop) do nothing. The compile
           run executes exactly these input ops (it is replay run 0), and writes the op list
           (the 'script'). An action that could not be expressed as input (element not found,
           no hit point, focus not reached by the click) is recorded with a reason and the task
           is not input-pure; it is excluded from the reference set.
  play     Replays a script by its input ops only: no element lookup, no names, no selectors.
           Every run opens a fresh backend session of the task (POST /api/env/<env>/session
           {task_id}, as stock_browseruse_eval.py) and a fresh browser context (viewport
           1280x720, Gemini's harness viewport; Date fixed at 2026-10-30T09:00Z at every load
           and then running; requests to hosts other than 127.0.0.1 aborted, so remote images
           never load in either arm; Chromium smooth scrolling off). Before each click op the
           element under the point is recorded (tag, text, class, box of its control ancestor)
           and after each action the URL path, so a run can be compared step by step with the
           compile run. At the end: POST /api/env/<env>/evaluate {session_id}, BreakingWeb's own
           scorer of the final backend state (the call stock_browseruse_eval.py makes).
  drive    Per environment in a private BreakingWeb checkout (BW_ROOT): restore sources, build
           clean, compile, play clean 3 times; then for each kind: codemod.py on env + shared
           sources, build, play every reference-set task once (re-played twice more if it
           fails), restore; the `none` sham is built and played last (a late clean control).
           A kind whose built bundle is byte-identical to clean is not played (identical_bundle).
           Sources are restored and clean rebuilt at the end, also on error.
           Controls: `--null` adds a do-nothing run per reference task on clean (start page opened,
           no input, evaluated; CTL-1 of Chen2026a: must fail); kind `pc_break` is the known-answer
           break of click_effect.py (every 2nd button onClick -> onDoubleClick, every 2nd link out of
           the Tab order; must make tasks fail). `--controls-only` skips the sham on such a pass.
  summary  Reference set (input-pure and evaluator pass on 3/3 clean plays) and the task x kind
           feasibility matrix over all environments; controls listed separately.

Usage (BreakingWeb venv python; PATH with node 24.20.0 and pnpm 10.15.0;
BREAKINGWEB_AUTO_BUILD_FRONTENDS=0; BW_ROOT = private checkout, also on PYTHONPATH; BW_PORT =
backend port, bound to 127.0.0.1):
  replay.py drive ENV OUT [--kinds landmarks,headings,...] [--traj ~/.hf-stage-bw/gemini_3_1_pro/tasks]
                          [--workers 2] [--reps 3] [--tasks FILE] [--null] [--controls-only]
        (as run: drive ENV OUT --kinds <gate-passing kinds>, then drive ENV OUT --kinds pc_break --null
         --controls-only; driver /tmp/amt-syn/bw-replay/run_env.sh CHECKOUT PORT OUT ENV KINDS ...)
  replay.py compile ENV OUT [--tasks FILE]          (server must be up on BW_PORT; clean build)
  replay.py play ENV OUT BUILD [--rep K] [--tasks FILE]
  replay.py summary OUT                             -> OUT/summary.json, prints the tables
Outputs: OUT/<env>/scripts/<task>.json (compiled script + compile-run eval); OUT/<env>/runs/
<build>/<task>.r<K>.json (one play run); OUT/<env>/builds.json (build log, bundle hashes).
OUT e.g. /tmp/amt-syn/bw-replay.
"""
import argparse
import glob
import hashlib
import json
import multiprocessing as mp
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemod  # noqa: E402
import path_replay as pr  # noqa: E402  (locate, parse_ec, select_listings, raw_index)
import variant_gate as vg  # noqa: E402  (build, restore; BW_ROOT/BW_PORT read there)

ROOT, PORT = vg.ROOT, vg.PORT
TRAJ = os.path.expanduser('~/.hf-stage-bw/gemini_3_1_pro/tasks')
VIEWPORT = (1280, 720)
KINDS = ['landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads']
READ_ONLY = {'finish', 'dropdown_options', 'find_elements', 'find_text', 'search_page', 'wait', 'noop', 'extract'}
DATE_T0 = 1793437200000  # 2026-10-30T09:00:00Z, as click_effect.py
DATE_SHIM = '''(() => { const T0 = %d, RD = Date, p0 = performance.now();
  function D(...a) { if (!new.target) return new RD(D.now()).toString(); return a.length ? new RD(...a) : new RD(D.now()); }
  D.prototype = RD.prototype; D.now = () => T0 + Math.floor(performance.now() - p0); D.parse = RD.parse; D.UTC = RD.UTC;
  Object.setPrototypeOf(D, RD); window.Date = D; })();''' % DATE_T0

GEOM_JS = r'''(el) => {
  const r = el.getBoundingClientRect(), clips = [];
  let p = el.parentElement;
  while (p && p !== document.body && p !== document.documentElement) {
    const cs = getComputedStyle(p);
    if (/(auto|scroll|overlay)/.test(cs.overflowY) && p.scrollHeight > p.clientHeight + 1) {
      const q = p.getBoundingClientRect();
      clips.push({top: q.top + p.clientTop, bottom: q.top + p.clientTop + p.clientHeight, left: q.left, right: q.right,
                  st: p.scrollTop, max: p.scrollHeight - p.clientHeight});
    }
    p = p.parentElement;
  }
  return {r: {top: r.top, bottom: r.bottom, left: r.left, right: r.right, w: r.width, h: r.height},
          clips: clips, vw: innerWidth, vh: innerHeight, sy: scrollY,
          maxy: document.documentElement.scrollHeight - innerHeight};
}'''

# a point over no nested scroller (for window wheel scrolling)
FREE_POINT_JS = r'''(pts) => {
  const scrolls = e => { for (let p = e; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      const cs = getComputedStyle(p); if (/(auto|scroll|overlay)/.test(cs.overflowY) && p.scrollHeight > p.clientHeight + 1) return true; }
    return false; };
  for (const [x, y] of pts) { const e = document.elementFromPoint(x, y); if (e && !scrolls(e) && e.tagName !== 'IFRAME') return [x, y]; }
  return null;
}'''

# a point inside a given scroller's visible box whose hit test lies inside that scroller
INNER_POINT_JS = r'''(args) => {
  const [el, depth] = [args.el, args.depth];
  let p = el.parentElement, k = -1, sc = null;
  while (p && p !== document.body && p !== document.documentElement) {
    const cs = getComputedStyle(p);
    if (/(auto|scroll|overlay)/.test(cs.overflowY) && p.scrollHeight > p.clientHeight + 1) { k++; if (k === depth) { sc = p; break; } }
    p = p.parentElement;
  }
  if (!sc) return null;
  const q = sc.getBoundingClientRect();
  const top = Math.max(q.top, 0), bot = Math.min(q.bottom, innerHeight), lef = Math.max(q.left, 0), rig = Math.min(q.right, innerWidth);
  for (const fy of [0.5, 0.3, 0.7, 0.15, 0.85]) for (const fx of [0.5, 0.25, 0.75, 0.1, 0.9]) {
    const x = lef + (rig - lef) * fx, y = top + (bot - top) * fy, e = document.elementFromPoint(x, y);
    if (e && sc.contains(e)) {
      // the innermost scroller under the point must be sc itself
      let inner = null; for (let t = e; t && t !== sc; t = t.parentElement) { const cs = getComputedStyle(t);
        if (/(auto|scroll|overlay)/.test(cs.overflowY) && t.scrollHeight > t.clientHeight + 1) { inner = t; break; } }
      if (!inner) return [x, y];
    }
  }
  return null;
}'''

# a point of the element's visible box whose hit test is the element (or a descendant, or a
# <label> whose control is the element)
HIT_POINT_JS = r'''(el) => {
  const r = el.getBoundingClientRect();
  const top = Math.max(r.top, 0), bot = Math.min(r.bottom, innerHeight), lef = Math.max(r.left, 0), rig = Math.min(r.right, innerWidth);
  if (bot - top < 1 || rig - lef < 1) return {pt: null, why: 'not_in_viewport'};
  const ok = e => e && (e === el || el.contains(e));
  const okLabel = e => { const l = e && e.closest && e.closest('label'); return l && l.control === el; };
  let lab = null;
  for (const fy of [0.5, 0.3, 0.7, 0.15, 0.85]) for (const fx of [0.5, 0.3, 0.7, 0.15, 0.85]) {
    const x = Math.round((lef + (rig - lef) * fx) * 100) / 100, y = Math.round((top + (bot - top) * fy) * 100) / 100;
    const e = document.elementFromPoint(x, y);
    if (ok(e)) return {pt: [x, y], via: 'self'};
    if (!lab && okLabel(e)) lab = [x, y];
  }
  if (lab) return {pt: lab, via: 'label'};
  // a visually hidden control (opacity 0 / 1px) styled through its label: click the label
  if (el.labels && el.labels.length) { for (const l of el.labels) { const q = l.getBoundingClientRect();
      if (q.width > 0 && q.height > 0 && q.top >= 0 && q.bottom <= innerHeight) { const x = q.left + q.width / 2, y = q.top + q.height / 2;
        const e = document.elementFromPoint(x, y); if (e && (e === l || l.contains(e))) return {pt: [x, y], via: 'label_box'}; } } }
  const e = document.elementFromPoint((lef + rig) / 2, (top + bot) / 2);
  return {pt: null, why: 'occluded', by: e ? e.tagName.toLowerCase() + '.' + (e.className && e.className.baseVal === undefined ? String(e.className).slice(0, 60) : '') : null};
}'''

# what is under a point: the hit element and its nearest control ancestor (diagnostics only)
SIG_JS = r'''(pt) => {
  const e = document.elementFromPoint(pt[0], pt[1]);
  if (!e) return null;
  const c = e.closest('a,button,input,select,textarea,label,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=option],[role=checkbox],[role=radio],[tabindex],[onclick]') || e;
  const r = c.getBoundingClientRect(), t = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  return {tag: e.tagName.toLowerCase(), ctag: c.tagName.toLowerCase(), text: t(c.innerText || c.value || ''),
          cls: typeof c.className === 'string' ? c.className.slice(0, 120) : '',
          box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]};
}'''

PATH_JS = "() => location.pathname.replace(/^\\/env\\/[^/]+/, '') || '/'"


# ----------------------------------------------------------------------------- browser helpers
def http_json(url, method='GET', payload=None, timeout=60):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={'Content-Type': 'application/json'} if body else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        t = r.read().decode()
        return json.loads(t) if t else {}


def settle(page, ms=350):
    try:
        page.wait_for_load_state('networkidle', timeout=4000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def wait_still(page, handle=None, cap_ms=2000):
    """Wait until the window scroll position (and the element's box) stop changing."""
    last, t0 = None, time.time()
    while (time.time() - t0) * 1000 < cap_ms:
        try:
            cur = page.evaluate('(el) => [scrollY, el ? el.getBoundingClientRect().top : 0]', handle)
        except Exception:
            cur = None
        if cur == last and cur is not None:
            return
        last = cur
        page.wait_for_timeout(80)


def new_run(browser, base, env_id, task):
    created = http_json(f'{base}/api/env/{env_id}/session', 'POST', {'task_id': task})
    sid = created['session_id']
    url = f"{base}/env/{env_id}{created.get('start_path', '/')}?session={urllib.parse.quote(sid)}&agent_mode=1"
    ctx = browser.new_context(viewport={'width': VIEWPORT[0], 'height': VIEWPORT[1]})
    ctx.add_init_script(DATE_SHIM)
    ext = []

    def route(r):
        host = urllib.parse.urlparse(r.request.url).hostname
        if host in ('127.0.0.1', 'localhost') or r.request.url.startswith(('data:', 'blob:')):
            r.continue_()
        else:
            ext.append(r.request.url[:120]); r.abort()
    ctx.route('**/*', route)
    page = ctx.new_page()
    resp = page.goto(url)
    if resp is None or resp.status >= 400:
        raise RuntimeError(f'start page HTTP {resp.status if resp else None}')
    settle(page, 600)
    return sid, ctx, page, ext


def end_run(base, env_id, sid, ctx):
    try:
        ev = http_json(f'{base}/api/env/{env_id}/evaluate', 'POST', {'session_id': sid})
        out = {'success': ev.get('success'), 'score': ev.get('score'),
               'failed_checks': [c.get('desc') for c in ev.get('checks') or [] if not c.get('passed')],
               'failed_negative': [c.get('desc') for c in ev.get('negative_checks') or [] if not c.get('passed')]}
    except Exception as e:
        out = {'error': str(e)[:300]}
    try:
        http_json(f'{base}/api/env/{env_id}/session/{urllib.parse.quote(sid)}', 'DELETE')
    except Exception:
        pass
    try:
        ctx.close()
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------- input ops
def exec_op(page, op, diag=None):
    """Execute one input op. Returns an error string or None. `diag` collects the hit
    signature under click points."""
    k = op['op']
    if k == 'wheel':
        page.mouse.move(op['x'], op['y'])
        page.mouse.wheel(0, op['dy'])
        wait_still(page)
        page.wait_for_timeout(120)
    elif k == 'click':
        if diag is not None:
            try:
                diag.append(page.evaluate(SIG_JS, [op['x'], op['y']]))
            except Exception:
                diag.append(None)
        page.mouse.click(op['x'], op['y'])
        settle(page)
    elif k == 'fill':
        h = page.evaluate_handle('() => document.activeElement').as_element()
        tag = h.evaluate('e => e.tagName.toLowerCase() + (e.isContentEditable ? ":ce" : "")') if h else None
        if not h or tag in ('body', 'html'):
            return 'fill: nothing focused'
        if op.get('append'):
            page.keyboard.press('End'); page.keyboard.insert_text(op['text'])
        else:
            h.fill(op['text'], timeout=4000)
        settle(page)
    elif k == 'select':
        h = page.evaluate_handle('() => document.activeElement').as_element()
        if not h or h.evaluate('e => e.tagName') != 'SELECT':
            return 'select: focused element is not a <select>'
        how = op['how']
        if how == 'value':
            h.select_option(value=op['v'], timeout=4000)
        elif how == 'label':
            h.select_option(label=op['v'], timeout=4000)
        else:
            h.select_option(index=op['v'], timeout=4000)
        settle(page)
    elif k == 'key':
        page.keyboard.press(op['key'])
        settle(page)
    elif k == 'back':
        page.go_back(); settle(page)
    elif k == 'pause':
        page.wait_for_timeout(op.get('ms', 500))
    else:
        return f'unknown op {k}'
    return None


def bring_into_view(page, h, ops):
    """Wheel-scroll until the element's box is in the viewport and inside every scroll container.
    Appends the wheel ops it executed. Returns None or a reason string."""
    for _ in range(10):
        g = h.evaluate(GEOM_JS)
        r, vh, vw = g['r'], g['vh'], g['vw']
        if r['w'] == 0 and r['h'] == 0:
            return 'zero_box'
        cy = (r['top'] + r['bottom']) / 2
        bad = None
        for depth, c in enumerate(g['clips']):
            if not (c['top'] <= cy <= c['bottom']) and not (r['top'] >= c['top'] and r['bottom'] <= c['bottom']):
                if (cy < c['top'] and c['st'] > 0) or (cy > c['bottom'] and c['st'] < c['max'] - 1):
                    bad = (depth, c)
                    break
        if bad is None:
            if 4 <= cy <= vh - 4 or (r['top'] >= 0 and r['bottom'] <= vh):
                return None
            if (cy < 0 and g['sy'] <= 0) or (cy > vh and g['sy'] >= g['maxy'] - 1):
                return 'window_scroll_limit'
            dy = round(cy - vh / 2)
            pts = [(vw / 2, vh / 2), (vw * 0.9, vh / 2), (vw * 0.1, vh / 2), (vw / 2, vh * 0.25), (vw / 2, vh * 0.75),
                   (vw * 0.95, vh * 0.9), (vw * 0.05, vh * 0.9), (vw * 0.98, vh * 0.1)]
            pt = page.evaluate(FREE_POINT_JS, pts)
            if pt is None:
                return 'no_free_point_for_window_wheel'
        else:
            depth, c = bad
            dy = round(cy - (c['top'] + c['bottom']) / 2)
            pt = page.evaluate(INNER_POINT_JS, {'el': h, 'depth': depth})
            if pt is None:
                return 'no_point_over_scroller'
        op = {'op': 'wheel', 'x': round(pt[0], 2), 'y': round(pt[1], 2), 'dy': dy}
        before = h.evaluate('e => e.getBoundingClientRect().top')
        exec_op(page, op)
        ops.append(op)
        after = h.evaluate('e => e.getBoundingClientRect().top')
        if abs(after - before) < 0.5:
            return 'wheel_no_effect'
    return 'scroll_not_converged'


def centre_in_window(page, h, ops):
    """One window wheel that brings the element's centre to the middle of the viewport."""
    g = h.evaluate(GEOM_JS)
    cy = (g['r']['top'] + g['r']['bottom']) / 2
    dy = round(cy - g['vh'] / 2)
    if abs(dy) < 8 or (dy < 0 and g['sy'] <= 0) or (dy > 0 and g['sy'] >= g['maxy'] - 1):
        return
    vw, vh = g['vw'], g['vh']
    pts = [(vw / 2, vh / 2), (vw * 0.9, vh / 2), (vw * 0.1, vh / 2), (vw / 2, vh * 0.25), (vw / 2, vh * 0.75)]
    pt = page.evaluate(FREE_POINT_JS, pts)
    if pt is None:
        return
    op = {'op': 'wheel', 'x': round(pt[0], 2), 'y': round(pt[1], 2), 'dy': dy}
    exec_op(page, op)
    ops.append(op)


RESELECT_JS = r"""(a) => {
  const t = s => (s || '').replace(/\s+/g, ' ').trim();
  const has = el => [...el.options].some(o => a.how === 'value' ? o.value === a.v : t(o.text) === a.v);
  if (has(a.el)) return null;
  const vis = [...document.querySelectorAll('select')].filter(e => e.getClientRects().length && has(e));
  if (!vis.length) return null;
  const listed = a.listed || [];
  const score = e => listed.length ? -Math.abs([...e.options].length - listed.length) + ([...e.options].every(o => listed.includes(t(o.text))) ? 10 : 0) : 0;
  vis.sort((x, y) => score(y) - score(x));
  return vis.indexOf(vis[0]) >= 0 ? [...document.querySelectorAll('select')].indexOf(vis[0]) : null;
}"""


def reselect(page, h, ec, raw):
    """A recorded select names its option. If the name-resolved <select> has no such option,
    take the visible <select> that has it (best match of the listed options)."""
    m = re.match(r'Selected option: (.*) \(value: (.*)\)\s*$', ec, re.S)
    listed = [ln[2:].strip() for ln in ec.splitlines() if ln.startswith('- ')]
    if m:
        how, v = 'value', m.group(2)
    else:
        v = ((raw or {}).get('select_dropdown') or {}).get('text')
        how = 'label'
        if v is None:
            return h, False
    i = page.evaluate(RESELECT_JS, {'el': h, 'how': how, 'v': v, 'listed': listed})
    if i is None:
        return h, False
    h2 = page.evaluate_handle('(i) => document.querySelectorAll("select")[i]', i).as_element()
    return (h2, True) if h2 is not None else (h, False)


def opt_choice(handle, ec, listing, raw):
    """Which option a recorded select chose: (how, value) for the select op."""
    m = re.match(r'Selected option: (.*) \(value: (.*)\)\s*$', ec, re.S)
    if not m and ec.startswith('Available dropdown options'):
        want = ((raw or {}).get('select_dropdown') or {}).get('text')
        listed = [ln[2:].strip() for ln in ec.splitlines() if ln.startswith('- ')]
        if want is not None and want in listed:
            labs = handle.evaluate("el => [...el.options].map(o => o.text.replace(/\\s+/g, ' ').trim())")
            if want not in labs:
                return None, f'option not on the resolved select: {want!r}'
            return ('label', want), 'listed_option_applied'
        return None, 'recorded select failed'
    if not m:
        return None, 'no recorded option'
    lab, val = m.group(1), m.group(2)
    opts = handle.evaluate("el => [...el.options].map(o => [o.value, o.text.replace(/\\s+/g, ' ').trim()])")
    if any(o[0] == val for o in opts):
        return ('value', val), None
    if any(o[1] == lab.strip() for o in opts):
        return ('label', lab.strip()), None
    if listing and val in listing[1] and listing[1].index(val) < len(opts):
        return ('index', listing[1].index(val)), 'by_index'
    return None, f'option not found: {val!r}'


# ----------------------------------------------------------------------------- compile
def compile_task(path, out, base, browser):
    d = json.load(open(path))
    task = d['task_id']
    from breakingweb.tasks._registry import get_task
    env_id = get_task(task).env_id
    rec = {'task_id': task, 'env_id': env_id, 'recorded_success': (d.get('evaluation') or {}).get('success'),
           'viewport': VIEWPORT, 'actions': [], 'pure': True, 'impure': []}
    sid = ctx = None
    try:
        sid, ctx, page, ext = new_run(browser, base, env_id, task)
        steps = d['agent'].get('trajectory') or []
        listings = pr.select_listings(steps)
        for s in steps:
            acts = s.get('actions') or []
            tgts = s.get('action_targets') or [{}] * len(acts)
            ress = s.get('action_results') or [{}] * len(acts)
            ras = s.get('raw_actions') or []
            for j, a in enumerate(acts):
                t = tgts[j] if j < len(tgts) else {}
                r = (ress[j] if j < len(ress) else {}) or {}
                kind = a.get('action')
                ec = r.get('extracted_content') or ''
                ar = {'step': s.get('step'), 'j': j, 'action': kind, 'target': t, 'ec': ec[:160],
                      'path_before': page.evaluate(PATH_JS), 'ops': []}
                rec['actions'].append(ar)
                try:
                    if kind in READ_ONLY:
                        ar['noop'] = True
                    elif kind == 'scroll':
                        m = re.search(r'Scrolled (down|up) (\d+)px', ec)
                        m2 = re.search(r'Scrolled (down|up) ([\d.]+) pages?', ec)
                        dy = None
                        if m:
                            dy = int(m.group(2)) * (1 if m.group(1) == 'down' else -1)
                        elif m2:
                            dy = int(float(m2.group(2)) * VIEWPORT[1]) * (1 if m2.group(1) == 'down' else -1)
                        if dy is not None:
                            pts = [(VIEWPORT[0] / 2, VIEWPORT[1] / 2)]
                            op = {'op': 'wheel', 'x': pts[0][0], 'y': pts[0][1], 'dy': dy}
                            exec_op(page, op); ar['ops'].append(op)
                        else:
                            ar['noop'] = 'scroll_unparsed'
                    elif kind == 'press':
                        mm = re.match(r'Sent keys: (.*)', ec)
                        key = (mm.group(1).strip() if mm else (a.get('key') or a.get('keys'))) or 'Enter'
                        op = {'op': 'key', 'key': key}
                        exec_op(page, op); ar['ops'].append(op)
                    elif kind == 'back':
                        op = {'op': 'back'}
                        exec_op(page, op); ar['ops'].append(op)
                    elif kind in ('click', 'fill', 'select'):
                        lst = listings.get(pr.raw_index(s, j))
                        h, info = pr.locate(page, a, t, r, lst)
                        ar['locate'] = info
                        if kind == 'select' and h is not None:
                            h, moved = reselect(page, h, ec, ras[j] if j < len(ras) else None)
                            if moved:
                                ar['locate'] = dict(info, how=info.get('how', '') + '+option_match')
                        md = r.get('metadata') or {}
                        x, y = md.get('click_x', md.get('input_x')), md.get('click_y', md.get('input_y'))
                        if h is not None and x is not None:
                            ar['point_agrees'] = page.evaluate('(a) => { const e = document.elementFromPoint(a.x, a.y); return !!e && (e === a.el || a.el.contains(e)); }',
                                                               {'x': x, 'y': y, 'el': h})
                        if h is None:
                            raise RuntimeError('element not found: ' + info.get('how', ''))
                        why = bring_into_view(page, h, ar['ops'])
                        if why:
                            ar['view'] = why
                        hp = h.evaluate(HIT_POINT_JS)
                        if not hp.get('pt'):
                            # covered by a sticky bar at the viewport edge: wheel it to the middle
                            centre_in_window(page, h, ar['ops'])
                            hp = h.evaluate(HIT_POINT_JS)
                        for _w in range(6):
                            # covered (a toast, a closing overlay): wait as a user would, up to 3 s
                            if hp.get('pt'):
                                break
                            op = {'op': 'pause', 'ms': 500}
                            exec_op(page, op); ar['ops'].append(op)
                            hp = h.evaluate(HIT_POINT_JS)
                        if not hp.get('pt'):
                            raise RuntimeError(f"no hit point: {hp.get('why')} {hp.get('by') or ''}")
                        ar['hit_via'] = hp.get('via')
                        cop = {'op': 'click', 'x': hp['pt'][0], 'y': hp['pt'][1]}
                        if kind == 'select':
                            choice, note = opt_choice(h, ec, lst, ras[j] if j < len(ras) else None)
                            if note:
                                ar['select_note'] = note
                            if choice is None:
                                raise RuntimeError(note)
                        diag = []
                        exec_op(page, cop, diag); ar['ops'].append(cop); ar['sig'] = diag[0]
                        if kind in ('fill', 'select'):
                            focused = h.evaluate('e => document.activeElement === e || e.contains(document.activeElement)')
                            if not focused:
                                raise RuntimeError('click did not focus the control')
                            if kind == 'fill':
                                op = {'op': 'fill', 'text': a.get('value', '')}
                                if a.get('clear') is False:
                                    op['append'] = True
                            else:
                                op = {'op': 'select', 'how': choice[0], 'v': choice[1]}
                            err = exec_op(page, op)
                            if err:
                                raise RuntimeError(err)
                            ar['ops'].append(op)
                            # as path_replay.py: a filled control is not matched again within the step
                            h.evaluate("el => el.setAttribute('data-amt-used', '1')")
                    else:
                        raise RuntimeError(f'unhandled action {kind}')
                except Exception as e:
                    ar['error'] = str(e).splitlines()[0][:300]
                    rec['pure'] = False
                    rec['impure'].append(f"step {s.get('step')}.{j} {kind}: {ar['error'][:120]}")
                ar['path_after'] = page.evaluate(PATH_JS)
            try:
                page.evaluate("() => document.querySelectorAll('[data-amt-used]').forEach(e => e.removeAttribute('data-amt-used'))")
            except Exception:
                pass
        rec['ext_blocked'] = len(ext)
    except Exception:
        rec['fatal'] = traceback.format_exc()[-1500:]
        rec['pure'] = False
    finally:
        rec['eval'] = end_run(base, env_id, sid, ctx) if sid else {'error': 'no session'}
    json.dump(rec, open(out, 'w'), indent=0)
    return task, rec['pure'], rec['eval'].get('success')


# ----------------------------------------------------------------------------- play
def play_task(script_path, out, base, browser, null=False):
    sc = json.load(open(script_path))
    if null:  # do-nothing control (CTL-1): open the start page, act on nothing, evaluate
        sc = dict(sc, actions=[])
    task, env_id = sc['task_id'], sc['env_id']
    rec = {'task_id': task, 'actions': []}
    sid = ctx = None
    try:
        sid, ctx, page, ext = new_run(browser, base, env_id, task)
        for ar in sc['actions']:
            pa = {'path_before': page.evaluate(PATH_JS), 'sigs': []}
            for op in ar['ops']:
                err = exec_op(page, op, pa['sigs'])
                if err:
                    pa['error'] = err
                    break
            pa['path_after'] = page.evaluate(PATH_JS)
            rec['actions'].append(pa)
        rec['ext_blocked'] = len(ext)
    except Exception:
        rec['fatal'] = traceback.format_exc()[-1500:]
    finally:
        rec['eval'] = end_run(base, env_id, sid, ctx) if sid else {'error': 'no session'}
    json.dump(rec, open(out, 'w'))
    return task, rec['eval'].get('success')


def _worker(args):
    mode, jobs, base = args
    from playwright.sync_api import sync_playwright
    done = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-smooth-scrolling'])
        for i, (src, out) in enumerate(jobs):
            if i and i % 30 == 0:
                browser.close(); browser = p.chromium.launch(headless=True, args=['--disable-smooth-scrolling'])
            t0 = time.time()
            try:
                res = compile_task(src, out, base, browser) if mode == 'compile' else play_task(src, out, base, browser, mode == 'null')
            except Exception as e:
                res = (os.path.basename(out), f'error {e}')
            done.append(res)
            print(mode, *res, f'{time.time() - t0:.0f}s', flush=True)
        browser.close()
    return done


def run_jobs(mode, jobs, base, workers):
    jobs = [j for j in jobs if not os.path.exists(j[1])]
    if not jobs:
        return []
    chunks = [jobs[i::workers] for i in range(workers)]
    with mp.get_context('spawn').Pool(len([c for c in chunks if c])) as pool:
        res = pool.map(_worker, [(mode, c, base) for c in chunks if c])
    return [x for r in res for x in r]


# ----------------------------------------------------------------------------- server
class Server:
    def __init__(self, logpath):
        from breakingweb.runner import ensure_controller_secret
        from breakingweb.backend.security import CONTROLLER_SECRET_ENV
        env = dict(os.environ, PYTHONPATH=ROOT)
        env[CONTROLLER_SECRET_ENV] = ensure_controller_secret()
        self.log = open(logpath, 'a')
        self.proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'breakingweb.app:app', '--host', '127.0.0.1',
                                      '--port', str(PORT), '--log-level', 'warning'], cwd=ROOT, env=env,
                                     stdout=self.log, stderr=self.log)
        from breakingweb.runner import wait_for_server
        if not wait_for_server('127.0.0.1', PORT, timeout=90):
            self.stop()
            raise SystemExit('backend did not start')
        self.base = f'http://127.0.0.1:{PORT}'

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except Exception:
            self.proc.kill()
        self.log.close()


def bundle_hash(envname):
    h = hashlib.sha256()
    for p in sorted(glob.glob(f'{ROOT}/breakingweb/static/envs/{envname}/**', recursive=True)):
        if os.path.isfile(p):
            h.update(p.encode()); h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


def env_trajs(envname, traj_root, tasks_file=None):
    want = set(open(tasks_file).read().split()) if tasks_file else None
    out = []
    prefix = {'patient_portal': 'pp', 'robinhood': 'rh'}.get(envname, envname)
    for p in sorted(glob.glob(f'{traj_root}/{prefix}_*__clean/trajectory.json')):
        task = os.path.basename(os.path.dirname(p)).rsplit('__', 1)[0]
        if want is not None and task not in want:
            continue
        d = json.load(open(p))
        if not (d.get('evaluation') or {}).get('success'):
            continue
        from breakingweb.tasks._registry import get_task
        if get_task(task).env_id != envname:
            continue
        out.append((task, p))
    return out


# ----------------------------------------------------------------------------- drive
def cmd_drive(envname, outroot, kinds, a):
    out = f'{outroot}/{envname}'
    os.makedirs(f'{out}/scripts', exist_ok=True)
    mpath = f'{out}/builds.json'
    meta = json.load(open(mpath)) if os.path.exists(mpath) else {}
    trajs = env_trajs(envname, a.traj, a.tasks)
    log = f'{out}/server.log'

    def note(*x):
        print(f'=== {envname}', *x, time.strftime('%H:%M:%S'), flush=True)
    vg.restore(envname)
    try:
        # clean: compile + reps
        if not meta.get('clean', {}).get('done'):
            ok, blog = vg.build(envname)
            if not ok:
                raise SystemExit('clean build failed\n' + blog[-1500:])
            meta['clean'] = {'bundle': bundle_hash(envname)}
            srv = Server(log)
            try:
                note('compile', len(trajs), 'tasks')
                run_jobs('compile', [(p, f'{out}/scripts/{t}.json') for t, p in trajs], srv.base, a.workers)
                for k in range(a.reps):
                    note('clean play', k)
                    os.makedirs(f'{out}/runs/clean', exist_ok=True)
                    run_jobs('play', [(f'{out}/scripts/{t}.json', f'{out}/runs/clean/{t}.r{k}.json') for t, _ in trajs
                                      if json.load(open(f'{out}/scripts/{t}.json')).get('pure')], srv.base, a.workers)
            finally:
                srv.stop()
            meta['clean']['done'] = True
            json.dump(meta, open(mpath, 'w'), indent=1)
        ref = reference_set(out, [t for t, _ in trajs], a.reps)
        json.dump(ref, open(f'{out}/reference.json', 'w'), indent=1)
        note('reference set', sum(1 for v in ref.values() if v['ref']), 'of', len(ref))
        ref_tasks = [t for t, v in ref.items() if v['ref']]
        names = kinds + ([] if a.controls_only else ['none'])
        if a.null and not meta.get('null', {}).get('done'):
            vg.restore(envname)
            ok, blog = vg.build(envname)
            srv = Server(log)
            try:
                os.makedirs(f'{out}/runs/null', exist_ok=True)
                note('null control', len(ref_tasks))
                run_jobs('null', [(f'{out}/scripts/{t}.json', f'{out}/runs/null/{t}.r0.json') for t in ref_tasks], srv.base, a.workers)
            finally:
                srv.stop()
            meta['null'] = {'done': True, 'bundle': bundle_hash(envname), 'build_ok': ok}
            json.dump(meta, open(mpath, 'w'), indent=1)
        for name in names:
            if meta.get(name, {}).get('done'):
                continue
            vg.restore(envname)
            rec = {}
            if name == 'pc_break':
                import click_effect
                rec['codemod'] = click_effect.pc_break([f'{vg.ENVROOT}/{envname}/src', f'{vg.ENVROOT}/shared/src'])
            elif name != 'none':
                rec['codemod'] = {'env': codemod.rewrite(f'{vg.ENVROOT}/{envname}/src', name),
                                  'shared': codemod.rewrite(f'{vg.ENVROOT}/shared/src', name)}
            ok, blog = vg.build(envname)
            rec['build_ok'] = ok
            if not ok:
                rec['build_log_tail'] = blog[-1500:]
            else:
                rec['bundle'] = bundle_hash(envname)
                if name != 'none' and rec['bundle'] == meta['clean']['bundle']:
                    rec['identical_bundle'] = True
                else:
                    srv = Server(log)
                    try:
                        os.makedirs(f'{out}/runs/{name}', exist_ok=True)
                        note(name, 'play', len(ref_tasks))
                        run_jobs('play', [(f'{out}/scripts/{t}.json', f'{out}/runs/{name}/{t}.r0.json') for t in ref_tasks],
                                 srv.base, a.workers)
                        failed = [t for t in ref_tasks if not (json.load(open(f'{out}/runs/{name}/{t}.r0.json'))['eval'].get('success'))]
                        rec['first_fail'] = failed
                        if failed:
                            note(name, 'recheck', len(failed))
                            for k in (1, 2):
                                run_jobs('play', [(f'{out}/scripts/{t}.json', f'{out}/runs/{name}/{t}.r{k}.json') for t in failed],
                                         srv.base, a.workers)
                    finally:
                        srv.stop()
            rec['done'] = True
            meta[name] = rec
            vg.restore(envname)
            json.dump(meta, open(mpath, 'w'), indent=1)
    finally:
        vg.restore(envname)
        vg.build(envname)
        note('restored and rebuilt clean')


def reference_set(out, tasks, reps):
    ref = {}
    for t in tasks:
        sp = f'{out}/scripts/{t}.json'
        if not os.path.exists(sp):
            continue
        sc = json.load(open(sp))
        runs = []
        for k in range(reps):
            rp = f'{out}/runs/clean/{t}.r{k}.json'
            runs.append(json.load(open(rp))['eval'].get('success') if os.path.exists(rp) else None)
        ref[t] = {'pure': sc.get('pure'), 'impure': sc.get('impure'), 'compile_success': sc['eval'].get('success'),
                  'clean_runs': runs, 'ref': bool(sc.get('pure')) and all(r is True for r in runs)}
    return ref


# ----------------------------------------------------------------------------- summary
def diverge(script, run):
    """First action whose path_after or click-hit text/box differs from the compile run."""
    for i, (ca, pa) in enumerate(zip(script['actions'], run.get('actions') or [])):
        if pa.get('error'):
            return {'i': i, 'step': ca['step'], 'action': ca['action'], 'why': 'op error: ' + pa['error'], 'target': ca.get('target'), 'ec': ca.get('ec')}
        sig = ca.get('sig')
        if sig and pa.get('sigs'):
            ps = pa['sigs'][0] or {}
            if ps.get('text') != sig.get('text') or ps.get('box') != sig.get('box'):
                return {'i': i, 'step': ca['step'], 'action': ca['action'], 'why': 'different element under click point',
                        'clean': sig, 'variant': ps, 'target': ca.get('target'), 'ec': ca.get('ec')}
        if pa.get('path_after') != ca.get('path_after'):
            return {'i': i, 'step': ca['step'], 'action': ca['action'], 'why': 'different path after action',
                    'clean': ca.get('path_after'), 'variant': pa.get('path_after'), 'target': ca.get('target'), 'ec': ca.get('ec')}
    if len(run.get('actions') or []) < len(script['actions']):
        return {'why': 'run stopped early', 'fatal': (run.get('fatal') or '')[-300:]}
    return None


def cmd_summary(outroot):
    envs = sorted(e for e in os.listdir(outroot) if os.path.exists(f'{outroot}/{e}/builds.json'))
    S = {'envs': {}, 'matrix': {}, 'cells': {}}
    for e in envs:
        out = f'{outroot}/{e}'
        meta = json.load(open(f'{out}/builds.json'))
        ref = json.load(open(f'{out}/reference.json')) if os.path.exists(f'{out}/reference.json') else {}
        n = len(ref)
        S['envs'][e] = {'sampled': n, 'pure': sum(1 for v in ref.values() if v['pure']),
                        'compile_pass': sum(1 for v in ref.values() if v['compile_success']),
                        'clean_pass_counts': {str(k): sum(1 for v in ref.values() if v['pure'] and sum(1 for r in v['clean_runs'] if r is True) == k) for k in range(4)},
                        'reference': sum(1 for v in ref.values() if v['ref']),
                        'impure_reasons': {}}
        for v in ref.values():
            for s in v['impure'] or []:
                key = re.sub(r'^step [\d.]+ ', '', s)
                key = re.sub(r"'.*", '', key)[:70]
                S['envs'][e]['impure_reasons'][key] = S['envs'][e]['impure_reasons'].get(key, 0) + 1
        # clean-vs-clean divergence of reference tasks (fidelity of the input script)
        ref_tasks = [t for t, v in ref.items() if v['ref']]
        cdiv = 0
        for t in ref_tasks:
            sc = json.load(open(f'{out}/scripts/{t}.json'))
            for k in range(3):
                rp = f'{out}/runs/clean/{t}.r{k}.json'
                if os.path.exists(rp) and diverge(sc, json.load(open(rp))):
                    cdiv += 1
                    break
        S['envs'][e]['ref_tasks_with_clean_divergence'] = cdiv
        if 'null' in meta:
            nl = [json.load(open(f'{out}/runs/null/{t}.r0.json'))['eval'] for t in ref_tasks if os.path.exists(f'{out}/runs/null/{t}.r0.json')]
            S.setdefault('null', {})[e] = {'n': len(nl), 'evaluator_pass': sum(1 for x in nl if x.get('success') is True),
                                           'passed_tasks': [t for t in ref_tasks if os.path.exists(f'{out}/runs/null/{t}.r0.json')
                                                            and json.load(open(f'{out}/runs/null/{t}.r0.json'))['eval'].get('success') is True]}
        for name, m in meta.items():
            if name in ('clean', 'null'):
                continue
            cell = {'build_ok': m.get('build_ok'), 'identical_bundle': bool(m.get('identical_bundle')), 'tasks': {}}
            for t in ref_tasks:
                if m.get('identical_bundle'):
                    cell['tasks'][t] = {'verdict': 'feasible_identical'}
                    S['matrix'].setdefault(t, {})[name] = 'feasible_identical'
                    continue
                runs = []
                for k in range(3):
                    rp = f'{out}/runs/{name}/{t}.r{k}.json'
                    if os.path.exists(rp):
                        runs.append(json.load(open(rp)))
                if not runs:
                    cell['tasks'][t] = {'verdict': 'not_run'}
                    continue
                succ = [r['eval'].get('success') is True for r in runs]
                if succ[0]:
                    v = 'feasible'
                elif not any(succ):
                    v = 'infeasible'
                else:
                    v = 'unstable'
                tr = {'verdict': v, 'runs': succ}
                if v != 'feasible':
                    sc = json.load(open(f'{out}/scripts/{t}.json'))
                    tr['diverge'] = [diverge(sc, r) for r in runs]
                    tr['failed_checks'] = runs[0]['eval'].get('failed_checks')
                    tr['failed_negative'] = runs[0]['eval'].get('failed_negative')
                else:
                    sc = json.load(open(f'{out}/scripts/{t}.json'))
                    dv = diverge(sc, runs[0])
                    if dv:
                        tr['diverge_but_pass'] = dv
                cell['tasks'][t] = tr
                if name != 'pc_break':
                    S['matrix'].setdefault(t, {})[name] = v
            vals = [x['verdict'] for x in cell['tasks'].values()]
            cell['n'] = len(vals)
            cell['counts'] = {k: vals.count(k) for k in sorted(set(vals))}
            S['cells'][f'{e}/{name}'] = cell
    json.dump(S, open(f'{outroot}/summary.json', 'w'), indent=1)
    print(f"{'env':16} sampled pure compile clean3/3 ref  divergent")
    for e, v in S['envs'].items():
        print(f"{e:16} {v['sampled']:7} {v['pure']:4} {v['compile_pass']:7} {v['clean_pass_counts']['3']:9} {v['reference']:4} {v['ref_tasks_with_clean_divergence']:5}")
    print()
    for c, v in S['cells'].items():
        print(f"{c:28} n={v['n']:3} {v['counts']}{' identical bundle' if v['identical_bundle'] else ''}")
    for e, v in S.get('null', {}).items():
        print(f"null control {e:16} n={v['n']:3} evaluator passes {v['evaluator_pass']} {v['passed_tasks']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['drive', 'compile', 'play', 'summary'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--kinds', default=','.join(KINDS))
    ap.add_argument('--traj', default=TRAJ)
    ap.add_argument('--tasks')
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--rep', type=int, default=0)
    ap.add_argument('--null', action='store_true', help='drive: also run the do-nothing control on clean')
    ap.add_argument('--controls-only', action='store_true', help='drive: do not add the none sham (used for a later control pass)')
    a = ap.parse_args()
    if a.cmd == 'summary':
        return cmd_summary(a.args[0])
    envname, outroot = a.args[0], a.args[1]
    if a.cmd == 'drive':
        return cmd_drive(envname, outroot, [k for k in a.kinds.split(',') if k], a)
    base = f'http://127.0.0.1:{PORT}'
    out = f'{outroot}/{envname}'
    trajs = env_trajs(envname, a.traj, a.tasks)
    if a.cmd == 'compile':
        os.makedirs(f'{out}/scripts', exist_ok=True)
        res = run_jobs('compile', [(p, f'{out}/scripts/{t}.json') for t, p in trajs], base, a.workers)
    else:
        build = a.args[2]
        os.makedirs(f'{out}/runs/{build}', exist_ok=True)
        res = run_jobs('play', [(f'{out}/scripts/{t}.json', f'{out}/runs/{build}/{t}.r{a.rep}.json') for t, _ in trajs
                                if os.path.exists(f'{out}/scripts/{t}.json')], base, a.workers)
    print(len(res), 'done,', sum(1 for r in res if r[-1] is True), 'evaluator passes')


if __name__ == '__main__':
    main()
