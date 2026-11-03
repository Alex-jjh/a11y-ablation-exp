#!/usr/bin/env python3
"""Offline detector of the six AMT defect kinds on saved real web pages.

Input: pages saved by Alex in Chrome (scripts/realworld/CAPTURE.md), either the JSON file of
capture_snippet.js (`*.rwk.json`) or Chrome's "Save page as > Webpage, Single File" (`*.mhtml`,
`*.mht`). Output, per page: for each kind the number of instances, up to N examples (trimmed
outerHTML, accessible name, BrowserGym tree line) and a verdict on how the instance's form
compares with the form codemod.py writes into BreakingWeb; plus the BrowserGym-style tree text.

Saved pages are untrusted. The analyser
  - reads each file as bytes in Python and never gives the browser a file:// URL;
  - starts Chromium with a new, empty profile directory per page (deleted afterwards), with
    JavaScript disabled for the page (context java_script_enabled=False), service workers
    blocked, and a Content-Security-Policy of script-src 'none' on the served document;
  - blocks all network: every request goes through a route handler that serves the saved
    document (JSON: at http://rwk.invalid/page; MHTML: the archive's own parts at their saved
    locations) and aborts everything else; DNS resolution is mapped to NOTFOUND and a dead
    proxy (127.0.0.1:9) is set, so a request that escaped the handler would still fail;
  - strips <meta http-equiv=refresh> before serving, removes <noscript> (rendered as markup
    when scripts are off, but not shown to the original user) and reports every request and
    whether the final URL is still the served one.
The analyser's own code (BrowserGym's element marking, the DOM dump) runs through DevTools
evaluation, which the page's script setting does not block. BrowserGym's marking script waits
on a timer for an IntersectionObserver; timers do not run with scripts disabled, so a copy of
the script is patched to compute the same visibility ratio synchronously from element boxes
and the viewport (ancestor clipping is not modelled; the analyser reports the full tree as
primary and the viewport tree only as approximate).

Signatures, per kind. Each is the observable form that codemod.py produces in BreakingWeb
(codemod docstring; docs/feasibility/2026-10-30-variant-gate.md (b) observation rules;
2026-10-30-on-path-dose.md name-loss ladder). Verdicts: `exact` = the markup form codemod.py
writes; `equivalent` = other markup, same tree outcome for the agent; `kind-only` = the defect
kind is present but neither markup nor tree outcome equals the variant's.
  names      AX role button/link, rendered, and either
               empty: AX name empty (exact if no aria-label/aria-labelledby attribute,
                      equivalent if they exist but are empty or resolve to nothing); subtype
                      icon-only when it contains svg/img/<i>/an icon class;
               glyph-only: the name has no letter or digit ('▲', '☆', an icon-font character),
                      the visible content of an icon control after its aria-label is gone
                      (exact if no aria-label/labelledby, equivalent otherwise);
               ambiguous: the same normalised name is shared by >=2 rendered controls of the
                      same role; for links only when they point to >=2 different hrefs. exact
                      when the name comes from content (the codemod form: aria-label removed,
                      visible text left), equivalent when it comes from aria-label/labelledby/
                      title (same tree outcome).
             (variant: aria-label removed, the name falls back to visible text or to nothing;
              ladder rungs `empty` and `ambiguous`, the primary on-path flag)
  labels     rendered input (not hidden/submit/reset/button/image), textarea, select with no
             programmatic label: no associated <label> (for= or wrapping; DOM .labels), no
             aria-label, no aria-labelledby resolving to text, no title. exact: a visible
             <label> with no associated control sits in the same container (up to 3 ancestors,
             only one unlabelled control there): the codemod's "htmlFor removed" form; also
             exact: no visible label text at all (nothing or a placeholder), the codemod's
             "aria-label removed" form; equivalent: other visible short text in the container
             (div/span "Email" next to the field): the text is in the tree, the control unnamed.
  alt        rendered <img> without an alt attribute, no aria-label/labelledby/title, role not
             presentation/none, box larger than 2x2 px (exact; alt="" is decorative and is
             counted in context only). Subtype sole-content when it is the only content of a
             link or button whose name is empty.
  headings   rendered element that is not h1-h6, legend, caption, th, td or dt (these carry
             their own semantics) and has no heading role, display block-level,
             text 2-120 characters (>=50% letters, <=15 words, not ending in ':'), no interactive
             element inside or around it, no block-level text descendant, not inside a heading,
             table cell, label, legend, summary or option, no text run ending in ':' (the bold
             lead-in of "Status: active"), and styled like a heading relative to the page's
             dominant text size D (length-weighted mode of text font sizes): a text run is
             heading-styled if size >= HEAD_R1*D (1.25), or weight >= 600 and size >= HEAD_R3*D
             (1.1) and the text has <= 8 words; the element qualifies if its own text is
             heading-styled or heading-styled runs make up >= half of its text (signature
             heading-styled-text). A second, weaker tier takes bold short text that is not larger:
             weight >= 600, size >= HEAD_RW*D (0.85), <= 8 words, same coverage rule, and the
             element is a block tag (div, p, li, dd, section, header, figcaption; a
             span or strong made block by a flex parent does not count) (signature
             bold-short-text: small bold section labels such as "COMMUNITIES"; more false alarms).
             exact if the element is a div (codemod form), else equivalent.
             Styles come from the capture's data-rwk-f stamps (the original render) when present,
             else from this render (MHTML carries the page CSS).
  landmarks  page level: which core landmark roles (banner, navigation, main, contentinfo,
             complementary) the AX tree has. Instances: rendered non-landmark containers that
             name a region in their aria-label or, failing that, in their class/id tokens (BEM
             modifiers after `--` ignored; the last region word wins, so `topbar__nav` is a nav):
             header/masthead/
             topbar/banner -> banner, nav/navbar/navigation/menubar/sidenav -> navigation,
             main/maincontent or id content/page-content -> main, footer -> contentinfo,
             sidebar/aside -> complementary; outermost of their type, not containing a real
             landmark of that role, banner/contentinfo not inside article/aside/main/nav/section
             or a main/nav/aside-like container (Chrome's scoping), with a region-sized box
             (>= half the viewport wide for banner/main/contentinfo, >= 150 px tall for
             complementary/main) or >= 3 links/buttons for navigation. Instance exact if a div.
             Page verdict exact = no core landmark and >= 1 instance (the codemod's page: every
             region a div); partial = some core landmarks and >= 1 instance.
  tableheads rendered <table> (role not presentation/none) with >= 2 rows and >= 2 cells in some
             row, no th and no columnheader/rowheader role: exact if the first row is a styled
             header row (inside thead, or bolder / differently aligned / larger than the second
             row: the codemod keeps th's bold+center as td); kind-only otherwise, and dropped
             when Chrome classes it a layout table. ARIA role=table/grid with rows and cells and
             no header role: equivalent.

The thresholds of `headings` are calibrated on the BreakingWeb clean builds (record
docs/feasibility/2026-11-02-realworld-kit.md); the other signatures have no tuned constants
beyond the size floors stated above.

Usage: analyze.py OUT_DIR PATH... [--examples N] [--strip-attr NAME ...] [--quiet]
       PATH is a file or a directory (searched for *.rwk.json, *.mhtml, *.mht).
Run with the BreakingWeb venv python (Playwright 1.44, Chromium 125, BrowserGym 0.14.3) and -I.
"""
import argparse
import collections
import email
import email.policy
import glob
import json
import os
import pkgutil
import re
import shutil
import sys
import tempfile

KINDS = ['names', 'labels', 'alt', 'headings', 'landmarks', 'tableheads']
HEAD_R1, HEAD_R3, HEAD_RW = 1.25, 1.1, 0.85
SERVE_URL = 'http://rwk.invalid/page'
STAMP_CSS = ('[data-rwk-d="none"]{display:none!important}[data-rwk-v="h"]{visibility:hidden!important}'
             '[data-rwk-v="v"]{visibility:visible!important}')
CSP = "script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'"
LANDMARK_ROLES = {'banner', 'navigation', 'main', 'contentinfo', 'complementary', 'search', 'region', 'form'}
CORE = ['banner', 'navigation', 'main', 'contentinfo', 'complementary']
BLOCK = {'block', 'flex', 'grid', 'list-item', 'table-caption', 'flow-root', '-webkit-box'}
HEADING_TAGS = {f'h{i}' for i in range(1, 7)}
BLOCK_TAGS = {'div', 'p', 'li', 'dd', 'section', 'header', 'figcaption'}
INTERACTIVE_TAGS = {'a', 'button', 'input', 'select', 'textarea', 'summary', 'label', 'option'}
INTERACTIVE_ROLES = {'button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'switch', 'option', 'textbox', 'combobox'}
REGION_WORDS = {'header': 'banner', 'masthead': 'banner', 'topbar': 'banner', 'banner': 'banner',
                'nav': 'navigation', 'navbar': 'navigation', 'navigation': 'navigation', 'menubar': 'navigation',
                'sidenav': 'navigation', 'main': 'main', 'maincontent': 'main', 'footer': 'contentinfo',
                'sidebar': 'complementary', 'aside': 'complementary'}
MAIN_IDS = {'content', 'main-content', 'maincontent', 'page-content', 'main_content', 'pagecontent'}
LANDMARK_TAG_ROLE = {'header': 'banner', 'nav': 'navigation', 'main': 'main', 'footer': 'contentinfo', 'aside': 'complementary'}
SCOPING_TAGS = {'article', 'aside', 'main', 'nav', 'section'}
LABELABLE_SKIP_TYPES = {'hidden', 'submit', 'reset', 'button', 'image'}

# ----------------------------------------------------------------------------- loading

def load_json_capture(path):
    rec = json.load(open(path, encoding='utf-8'))
    if not str(rec.get('format', '')).startswith('rwk-capture-'):
        raise ValueError(f'{path}: not an rwk capture (format={rec.get("format")!r})')
    html = rec['html']
    if rec.get('doctype') == 'html' and rec.get('compat_mode', 'CSS1Compat') == 'CSS1Compat':
        html = '<!DOCTYPE html>' + html
    meta = {k: rec.get(k) for k in ('format', 'url', 'title', 'captured_at', 'user_agent', 'viewport', 'compat_mode', 'lang', 'stats')}
    return {'kind': 'json', 'root_url': SERVE_URL, 'parts': {SERVE_URL: ('text/html; charset=utf-8', html.encode('utf-8'))}, 'meta': meta}


def load_mhtml(path):
    msg = email.message_from_bytes(open(path, 'rb').read(), policy=email.policy.default)
    root_loc = msg.get('Snapshot-Content-Location')
    parts, first_html = {}, None
    for part in msg.walk():
        if part.is_multipart():
            continue
        loc = part.get('Content-Location')
        cid = part.get('Content-ID')
        body = part.get_payload(decode=True) or b''
        ctype = part.get_content_type()
        cs = part.get_content_charset()
        full_ct = ctype + (f'; charset={cs}' if cs else '')
        if loc:
            parts.setdefault(loc, (full_ct, body))
        if cid:
            parts.setdefault('cid:' + cid.strip('<>'), (full_ct, body))
        if ctype == 'text/html' and first_html is None:
            first_html = loc or ('cid:' + cid.strip('<>') if cid else None)
    root = root_loc if root_loc in parts else first_html
    if not root:
        raise ValueError(f'{path}: no text/html part')
    meta = {'format': 'mhtml', 'url': strip_query(root), 'title': msg.get('Subject'), 'captured_at': msg.get('Date'),
            'user_agent': None, 'viewport': None, 'stats': {'parts': len(parts)}}
    return {'kind': 'mhtml', 'root_url': root, 'parts': parts, 'meta': meta}


def strip_query(u):
    return re.split(r'[?#]', u or '', 1)[0]


RE_REFRESH = re.compile(rb'<meta\b[^>]*http-equiv\s*=\s*["\']?\s*refresh[^>]*>', re.I)
RE_HEAD = re.compile(rb'<head\b[^>]*>', re.I)
RE_SHADOW_TPL = re.compile(rb'(<template\b[^>]*\bshadowrootmode\s*=\s*["\']?(?:open|closed)["\']?[^>]*>)', re.I)


def prepare_html(body):
    """Bytes of the saved document -> bytes served: no meta refresh, Blink's MHTML `shadowmode`
    templates renamed to the standard `shadowrootmode`, stamp CSS in head and in every shadow root."""
    body = RE_REFRESH.sub(b'', body)
    body = re.sub(rb'(<template\b[^>]*?)\bshadowmode(\s*=)', rb'\1shadowrootmode\2', body, flags=re.I)
    style = f'<style data-rwk-analyzer="stamps">{STAMP_CSS}</style>'.encode()
    m = RE_HEAD.search(body)
    body = (body[:m.end()] + style + body[m.end():]) if m else (style + body)
    return RE_SHADOW_TPL.sub(lambda mm: mm.group(1) + style, body)


# ----------------------------------------------------------------------------- browser side

def mark_js():
    js = pkgutil.get_data('browsergym.core', 'javascript/frame_mark_elements.js').decode()
    a = 'new IntersectionObserver('
    b = 'await until(() => elems_to_be_visited.size == 0, visibility_marking_timeout);'
    assert js.count(a) == 1 and js.count(b) == 1, 'BrowserGym marking script changed; re-check the patch'
    js = js.replace(a, 'new (class { constructor(cb, o) { this.els = []; } observe(e) { this.els.push(e); } disconnect() {} })(')
    js = js.replace(b, '''for (const e of intersection_observer.els) {
            const r = e.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
            const iw = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)), ih = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
            const area = r.width * r.height;
            const ratio = area > 0 ? (iw * ih) / area : ((r.width > 0 || r.height > 0) && r.left <= vw && r.right >= 0 && r.top <= vh && r.bottom >= 0 ? 1 : 0);
            e.setAttribute('browsergym_visibility_ratio', Math.round(ratio * 100) / 100);
            elems_to_be_visited.delete(e);
        }''')
    return js


CLEAN_JS = '''(strip) => {
  const out = {noscript_removed: 0, bids_renamed: 0, stripped: 0, browsergym_attrs: 0};
  const visit = (root) => {
    for (const el of [...root.querySelectorAll('noscript')]) { el.remove(); out.noscript_removed++; }
    for (const el of root.querySelectorAll('*')) {
      if (el.hasAttribute('bid')) { el.setAttribute('data-rwk-obid', el.getAttribute('bid')); el.removeAttribute('bid'); out.bids_renamed++; }
      for (const a of [...el.attributes]) {
        if (a.name.startsWith('browsergym')) { el.removeAttribute(a.name); out.browsergym_attrs++; }
        else if (strip.includes(a.name)) { el.removeAttribute(a.name); out.stripped++; }
        else if ((a.name === 'aria-roledescription' || a.name === 'aria-description') && a.value.startsWith('browsergym_id_')) {
          const v = a.value.replace(/^browsergym_id_\\S+\\s?/, ''); if (v) el.setAttribute(a.name, v); else el.removeAttribute(a.name); out.browsergym_attrs++; }
      }
      if (el.shadowRoot) visit(el.shadowRoot);
    }
  };
  visit(document);
  return out;
}'''

DUMP_JS = '''() => {
  const out = [];
  const trim = (s, n) => s.length > n ? s.slice(0, n) + '...' : s;
  const VOID = new Set(['area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr']);
  const esc = (v) => v.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  const snippet = (el) => {   // outerHTML-like, at most ~400 characters, without the analyser's attributes
    let out = '';
    const emit = (n) => {
      if (out.length > 400) return;
      if (n.nodeType === 3) { out += n.data.replace(/\\s+/g, ' ').replace(/</g, '&lt;'); return; }
      if (n.nodeType !== 1) return;
      const t = n.tagName.toLowerCase();
      out += '<' + t;
      for (const a of n.attributes) if (a.name !== 'bid' && !a.name.startsWith('browsergym') && !a.name.startsWith('data-rwk-') && !(a.name === 'value' && a.value === '')) out += ` ${a.name}="${esc(a.value.slice(0, 120))}"`;
      out += '>';
      if (VOID.has(t)) return;
      for (const c of n.childNodes) emit(c);
      if (out.length <= 400) out += `</${t}>`;
    };
    emit(el);
    return out.length > 400 ? out.slice(0, 400) + '...' : out;
  };
  const walk = (root, inShadow) => {
    for (const el of root.querySelectorAll('*')) {
      const bid = el.getAttribute('bid');
      if (bid !== null) {
        const cs = getComputedStyle(el), r = el.getBoundingClientRect();
        let own = ''; for (const c of el.childNodes) if (c.nodeType === 3) own += c.data;
        const attrs = {}; for (const a of el.attributes) if (a.name !== 'bid' && !a.name.startsWith('browsergym')) attrs[a.name] = a.value.slice(0, 300);
        let p = el.parentElement || (el.parentNode && el.parentNode.host) || null;
        while (p && p.getAttribute && p.getAttribute('bid') === null) p = p.parentElement || (p.parentNode && p.parentNode.host) || null;
        const rec = {bid, tag: el.tagName.toLowerCase(), attrs, parent: p && p.getAttribute ? p.getAttribute('bid') : null,
          own: own.replace(/\\s+/g, ' ').trim().slice(0, 300), text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 300),
          cs: [parseFloat(cs.fontSize), cs.fontWeight, cs.display, cs.visibility, cs.textAlign],
          rect: [Math.round(r.x + scrollX), Math.round(r.y + scrollY), Math.round(r.width), Math.round(r.height)], shadow: inShadow};
        if (['input', 'textarea', 'select'].includes(rec.tag)) {
          rec.labels = el.labels ? el.labels.length : 0;
          const ids = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
          const rt = el.getRootNode();
          rec.labelledby_text = ids.map(i => { const t = rt.getElementById ? rt.getElementById(i) : null; return t ? t.textContent.trim() : ''; }).join(' ').trim();
        }
        if (rec.tag === 'label') rec.label_control = el.control ? el.control.getAttribute('bid') : null;
        if (!['html', 'head', 'body', 'script', 'style', 'meta', 'link', 'title'].includes(rec.tag)) rec.html = snippet(el);
        out.push(rec);
      }
      if (el.shadowRoot) walk(el.shadowRoot, true);
    }
  };
  walk(document, false);
  return {elements: out, viewport: [innerWidth, innerHeight], doc: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
          url: location.href, compat: document.compatMode, ran: document.documentElement.getAttribute('data-rwk-script-ran')};
}'''


def render(loaded, viewport, strip_attrs):
    """Serve the saved page with scripts and network off; return AX tree, flattened text, DOM dump, request log."""
    from playwright.sync_api import sync_playwright
    from browsergym.core import observation as bobs
    from browsergym.utils.obs import flatten_axtree_to_str
    profile = tempfile.mkdtemp(prefix='rwk-profile-')
    log = []
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                profile, headless=True, java_script_enabled=False, service_workers='block', viewport=viewport,
                proxy={'server': 'http://127.0.0.1:9'}, accept_downloads=False,
                args=['--host-resolver-rules=MAP * ~NOTFOUND', '--no-pings', '--dns-prefetch-disable',
                      '--disable-background-networking', '--disable-sync', '--disable-extensions'])
            parts = loaded['parts']

            def route(r):
                u = r.request.url
                if u in parts:
                    ct, body = parts[u]
                    headers = {'content-type': ct}
                    if u == loaded['root_url'] or ct.startswith('text/html'):
                        body = prepare_html(body); headers['content-security-policy'] = CSP
                    log.append({'url': u[:200], 'type': r.request.resource_type, 'action': 'served'})
                    r.fulfill(status=200, headers=headers, body=body)
                else:
                    log.append({'url': u[:200], 'type': r.request.resource_type, 'action': 'aborted'})
                    r.abort()
            ctx.route('**/*', route)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(30000)
            try:
                page.goto(loaded['root_url'], wait_until='load', timeout=20000)
            except Exception:  # noqa: BLE001  (a hung sub-resource; the DOM is parsed)
                page.wait_for_load_state('domcontentloaded')
            cleaned = page.evaluate(CLEAN_JS, list(strip_attrs))
            js = mark_js()

            def mark(frame, fbid):
                frame.evaluate(js, [fbid, 'bid', 'standard_html'])
                for ch in frame.child_frames:
                    try:
                        el = ch.frame_element(); b = el.get_attribute('bid')
                        if b and el.content_frame() == ch and re.match(r'^[a-z][a-zA-Z]*$', b):
                            mark(ch, b)
                    except Exception:  # noqa: BLE001
                        pass
            mark(page.main_frame, '')
            ax = bobs.extract_merged_axtree(page)
            snap = bobs.extract_dom_snapshot(page)
            extra = bobs.extract_dom_extra_properties(snap, 1.0)
            bobs._post_extract(page)
            dump = page.evaluate(DUMP_JS)
            kw = dict(extra_properties=extra, with_clickable=True, with_visible=True, filter_with_bid_only=True)
            tree_all = flatten_axtree_to_str(ax, filter_visible_only=False, **kw)
            tree_vp = flatten_axtree_to_str(ax, filter_visible_only=True, **kw)
            final_url = page.url
            ctx.close()
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return {'ax': ax, 'tree_all': tree_all, 'tree_viewport': tree_vp, 'dom': dump, 'requests': log,
            'cleaned': cleaned, 'final_url': final_url}


# ----------------------------------------------------------------------------- page model

class Page:
    def __init__(self, r):
        self.els = {e['bid']: e for e in r['dom']['elements']}
        self.order = [e['bid'] for e in r['dom']['elements']]
        self.kids = collections.defaultdict(list)
        for b in self.order:
            p = self.els[b]['parent']
            if p is not None:
                self.kids[p].append(b)
        self.ax = {}
        for n in r['ax']['nodes']:
            b = n.get('browsergym_id')
            if b is not None and (b not in self.ax or not n.get('ignored')):
                self.ax[b] = n
        self.vw, self.vh = r['dom']['viewport']
        self.lines = {}
        self.all_lines = r['tree_all'].splitlines()
        for line in self.all_lines:
            m = re.match(r'\s*\[([^\]]+)\]', line)
            if m:
                self.lines.setdefault(m.group(1), line.strip()[:300])
        self.stamped = any('data-rwk-f' in e['attrs'] for e in r['dom']['elements'])
        self._hidden = {}
        self.D = self.dominant_size()

    def ancestors(self, b):
        p = self.els[b]['parent']
        while p is not None:
            yield p
            p = self.els[p]['parent']

    def descendants(self, b):
        st = list(self.kids.get(b, []))
        while st:
            x = st.pop()
            yield x
            st.extend(self.kids.get(x, []))

    def _gone(self, b):
        """display:none or aria-hidden=true on the element or an ancestor (memoised)."""
        if b in self._hidden:
            return self._hidden[b]
        e = self.els[b]
        g = e['cs'][2] == 'none' or e['attrs'].get('aria-hidden') == 'true' or (e['parent'] is not None and self._gone(e['parent']))
        self._hidden[b] = g
        return g

    def hidden(self, b):
        """Not rendered for a sighted user or not exposed: display none / aria-hidden up the chain, or
        computed visibility (inherited) not visible. With a JSON capture the stamps make these the
        original page's values."""
        return self._gone(b) or self.els[b]['cs'][3] != 'visible'

    def font(self, b):
        """(size px, weight, display, align): capture stamp (original render) if present, else this render."""
        e = self.els[b]
        s = e['attrs'].get('data-rwk-f')
        if s:
            fs, fw, disp, al = (s.split('|') + ['', '', '', ''])[:4]
            try:
                return float(fs), int(float(fw)), disp, al
            except ValueError:
                pass
        try:
            fw = int(float(e['cs'][1]))
        except ValueError:
            fw = 700 if e['cs'][1] == 'bold' else 400
        return e['cs'][0], fw, e['cs'][2], e['cs'][4]

    def box(self, b):
        e = self.els[b]
        s = e['attrs'].get('data-rwk-box')
        if s:
            try:
                return [int(v) for v in s.split(',')]
            except ValueError:
                pass
        return e['rect']

    def dominant_size(self):
        w = collections.Counter()
        for b in self.order:
            e = self.els[b]
            if e['own'] and not self.hidden(b):
                w[round(self.font(b)[0])] += len(e['own'])
        return float(w.most_common(1)[0][0]) if w else 16.0

    def role(self, b):
        n = self.ax.get(b)
        return (n.get('role') or {}).get('value', '') if n else ''

    def name(self, b):
        n = self.ax.get(b)
        return str((n.get('name') or {}).get('value', '') if n else '').strip()

    def ignored(self, b):
        n = self.ax.get(b)
        return True if n is None else bool(n.get('ignored'))

    def example(self, b, **extra):
        e = self.els[b]
        line = self.lines.get(b)
        if line is None:   # generic elements are not printed; show the text line that stands in for them
            t = e['text'][:60].replace("'", "\\'")
            hit = next((x.strip() for x in self.all_lines if t and f"'{t}" in x), None) if len(e['text']) <= 120 else None
            line = (hit[:300] + '   (text of an unprinted generic element)') if hit else '(generic element: not printed; its children appear one level up)'
        d = {'bid': b, 'orig_bid': e['attrs'].get('data-rwk-obid'), 'tag': e['tag'], 'html': e.get('html') or f'<{e["tag"]}>',
             'accessible_name': self.name(b), 'ax_role': self.role(b), 'tree_line': line}
        d.update(extra)
        return d


def norm(s):
    return re.sub(r'\s+', ' ', s or '').strip().casefold()


def tokens(e):
    raw = ' '.join([e['attrs'].get('class', ''), e['attrs'].get('id', '')])
    raw = re.sub(r'--[\w-]*', ' ', raw)            # BEM modifiers (`feed-page--with-sidebar`) describe, not name
    raw = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw)
    return [t.lower() for t in re.split(r'[^A-Za-z0-9]+', raw) if t]


# ----------------------------------------------------------------------------- detectors

def det_names(pg):
    out, groups = [], collections.defaultdict(list)
    for b in pg.order:
        role = pg.role(b)
        if role not in ('button', 'link') or pg.ignored(b) or pg.hidden(b):
            continue
        e = pg.els[b]; a = e['attrs']
        nm = pg.name(b)
        has_aria = 'aria-label' in a or 'aria-labelledby' in a
        if not nm:
            imgs = [d for d in pg.descendants(b) if pg.els[d]['tag'] == 'img' and not pg.hidden(d)]
            if imgs and not e['text'] and any('alt' not in pg.els[d]['attrs'] for d in imgs):
                continue  # named only by an image without alt: reported by the alt kind (sole-content-of-control)
            icon = any(pg.els[d]['tag'] in ('svg', 'img', 'i', 'picture') or any('icon' in t for t in tokens(pg.els[d]))
                       for d in pg.descendants(b)) or any('icon' in t for t in tokens(e))
            out.append(pg.example(b, signature='empty', subtype='icon-only' if icon else 'no-content',
                                  verdict='equivalent' if has_aria else 'exact'))
            continue
        if not any(ch.isalnum() for ch in nm):
            out.append(pg.example(b, signature='glyph-only', subtype=nm[:10], verdict='equivalent' if has_aria else 'exact'))
            continue
        groups[(role, norm(nm))].append(b)
    for (role, nm), bs in groups.items():
        if len(bs) < 2:
            continue
        if role == 'link':
            hrefs = {re.sub(r'/+$', '', pg.els[b]['attrs'].get('href', '')) for b in bs}
            if len(hrefs) < 2:
                continue
        for b in bs:
            a = pg.els[b]['attrs']
            aria = (a.get('aria-label') or '').strip() or (a.get('aria-labelledby') or '').strip() or \
                ((a.get('title') or '').strip() and not pg.els[b]['text'])
            out.append(pg.example(b, signature='ambiguous', subtype=f'shared by {len(bs)}', verdict='equivalent' if aria else 'exact'))
    return out


def det_labels(pg):
    out, unl = [], []
    for b in pg.order:
        e = pg.els[b]; a = e['attrs']
        if e['tag'] not in ('input', 'textarea', 'select') or pg.hidden(b):
            continue
        if e['tag'] == 'input' and a.get('type', 'text').lower() in LABELABLE_SKIP_TYPES:
            continue
        if e.get('labels') or (a.get('aria-label') or '').strip() or e.get('labelledby_text') or (a.get('title') or '').strip():
            continue
        unl.append(b)
    unl_set = set(unl)
    orphans = [b for b in pg.order if pg.els[b]['tag'] == 'label' and not pg.els[b].get('label_control')
               and pg.els[b]['text'] and not pg.hidden(b)]
    paired = {}
    for lb in orphans:
        for anc in list(pg.ancestors(lb))[:3]:
            cs = [d for d in pg.descendants(anc) if d in unl_set]
            if len(cs) == 1:
                paired.setdefault(cs[0], lb); break
            if len(cs) > 1:
                break
    for b in unl:
        e = pg.els[b]; nm = pg.name(b)
        src = 'placeholder' if nm and nm == (e['attrs'].get('placeholder') or '').strip() else ('none' if not nm else 'other')
        if b in paired:
            out.append(pg.example(b, signature='unassociated-label', verdict='exact', name_from=src,
                                  label_html=pg.els[paired[b]].get('html'), label_text=pg.els[paired[b]]['text'][:80]))
            continue
        near = ''
        for anc in list(pg.ancestors(b))[:3]:
            ctrls = [d for d in pg.descendants(anc) if pg.els[d]['tag'] in ('input', 'textarea', 'select') and not pg.hidden(d)]
            if len(ctrls) > 1:
                break
            t = pg.els[anc]['text']
            if t and len(t) <= 80:
                near = t; break
        out.append(pg.example(b, signature='text-near-control' if near else 'no-visible-label',
                              verdict='equivalent' if near else 'exact', name_from=src, nearby_text=near[:80]))
    return out


def det_alt(pg):
    out = []
    for b in pg.order:
        e = pg.els[b]; a = e['attrs']
        if e['tag'] != 'img' or pg.hidden(b) or 'alt' in a:
            continue
        if (a.get('aria-label') or '').strip() or (a.get('aria-labelledby') or '').strip() or (a.get('title') or '').strip():
            continue
        if a.get('role', '').lower() in ('presentation', 'none'):
            continue
        bx = pg.box(b)
        w = bx[2] or int(re.sub(r'\D', '', a.get('width', '') or '0') or 0)
        h = bx[3] or int(re.sub(r'\D', '', a.get('height', '') or '0') or 0)
        if w <= 2 or h <= 2:
            continue
        sub = 'standalone'
        for anc in pg.ancestors(b):
            if pg.role(anc) in ('link', 'button'):
                sub = 'sole-content-of-control' if not pg.name(anc) else 'inside-named-control'
                break
        out.append(pg.example(b, signature='img-without-alt', subtype=sub, verdict='exact', src_file=os.path.basename(strip_query(a.get('src', '')))[:80]))
    return out


def heading_like(pg, b):
    """None or the reason dict: the visual heading test of det_headings."""
    e = pg.els[b]
    if e['tag'] in HEADING_TAGS | INTERACTIVE_TAGS | {'legend', 'caption', 'th', 'td', 'dt'} \
            or e['attrs'].get('role') in INTERACTIVE_ROLES | {'heading'} \
            or pg.role(b) in INTERACTIVE_ROLES | {'heading'} or pg.hidden(b):
        return None
    disp = pg.font(b)[2] if e['own'] else e['cs'][2]
    if disp not in BLOCK:
        return None
    t = e['text']
    if not (2 <= len(t) <= 120) or len(t.split()) > 15:
        return None
    chars = re.sub(r'\s', '', t)
    if not chars or sum(c.isalpha() for c in chars) / len(chars) < 0.5:
        return None
    for anc in pg.ancestors(b):
        ae = pg.els[anc]
        if ae['tag'] in HEADING_TAGS | {'a', 'button', 'label', 'legend', 'summary', 'option', 'td', 'th', 'caption', 'select'} \
                or ae['attrs'].get('role') in INTERACTIVE_ROLES | {'heading'}:
            return None
    if t.endswith(':'):
        return None  # a bare label
    runs = [b] if e['own'] else []
    for d in pg.descendants(b):
        de = pg.els[d]
        if de['tag'] in INTERACTIVE_TAGS or de['attrs'].get('role') in INTERACTIVE_ROLES:
            return None
        if de['own'] and not pg.hidden(d):
            if pg.font(d)[2] in BLOCK:
                return None
            runs.append(d)
    if not runs:
        return None
    if any(pg.els[x]['own'].endswith(':') for x in runs):
        return None  # "<strong>Status:</strong> active": the lead-in of a label/value pair

    words = len(t.split())

    def strong(x):
        fs, fw = pg.font(x)[:2]
        r = fs / pg.D
        return r >= HEAD_R1 or (fw >= 600 and r >= HEAD_R3 and words <= 8)

    def weak(x):
        fs, fw = pg.font(x)[:2]
        return e['tag'] in BLOCK_TAGS and fw >= 600 and fs / pg.D >= HEAD_RW and words <= 8
    total = sum(len(pg.els[x]['own']) for x in runs)
    for tier, styled in (('heading-styled-text', strong), ('bold-short-text', weak)):
        covered = sum(len(pg.els[x]['own']) for x in runs if styled(x))
        if (e['own'] and styled(b)) or (total and covered / total >= 0.5):
            bearer = max((x for x in runs if styled(x)), key=lambda x: pg.font(x)[0])
            fs, fw = pg.font(bearer)[:2]
            return {'signature': tier, 'font_px': fs, 'weight': fw, 'ratio_to_D': round(fs / pg.D, 2),
                    'styled_share': round(covered / total, 2) if total else None}
    return None


def det_headings(pg):
    out = []
    for b in pg.order:
        why = heading_like(pg, b)
        if why:
            e = pg.els[b]
            out.append(pg.example(b, verdict='exact' if e['tag'] == 'div' else 'equivalent', dominant_px=pg.D, **why))
    return out


def region_of(pg, b):
    """Region a container names: aria-label words first (`<div aria-label="Gmail navigation">`),
    then class/id tokens, where the last region word wins (BEM `topbar__nav` is a nav)."""
    e = pg.els[b]
    hit = None
    for t in re.split(r'[^a-z]+', (e['attrs'].get('aria-label') or '').lower()):
        if t in REGION_WORDS:
            hit = REGION_WORDS[t]
    if hit:
        return hit
    for t in tokens(e):
        if t in REGION_WORDS:
            hit = REGION_WORDS[t]
    if hit:
        return hit
    if (e['attrs'].get('id') or '').lower() in MAIN_IDS:
        return 'main'
    return None


def is_landmark(pg, b):
    r = pg.role(b)
    return r if r in LANDMARK_ROLES and not pg.ignored(b) else None


def det_landmarks(pg):
    out, cand = [], {}
    for b in pg.order:
        if pg.hidden(b) or is_landmark(pg, b):
            continue
        e = pg.els[b]
        if e['tag'] in ('a', 'button', 'input', 'img', 'svg', 'span', 'li', 'ul', 'ol', 'i', 'label', 'form', 'table'):
            continue
        reg = region_of(pg, b)
        if not reg:
            continue
        ancs = list(pg.ancestors(b))
        if any(cand.get(a) == reg or is_landmark(pg, a) == reg for a in ancs):
            continue
        if any(is_landmark(pg, d) == reg for d in pg.descendants(b)):
            continue
        if reg in ('banner', 'contentinfo') and any(pg.els[a]['tag'] in SCOPING_TAGS or is_landmark(pg, a) in ('main', 'navigation', 'complementary', 'region')
                                                     or cand.get(a) in ('main', 'navigation', 'complementary') for a in ancs):
            continue
        x, y, w, h = pg.box(b)
        if reg in ('banner', 'contentinfo', 'main') and w < 0.5 * pg.vw:
            continue
        if reg in ('complementary', 'main') and h < 150:
            continue
        if reg == 'navigation' and sum(1 for d in pg.descendants(b) if pg.role(d) in ('link', 'button')) < 3:
            continue
        cand[b] = reg
    for b, reg in cand.items():
        out.append(pg.example(b, signature=f'{reg}-like-container', region=reg, verdict='exact' if pg.els[b]['tag'] == 'div' else 'equivalent',
                              box=pg.box(b)))
    return out


def landmark_context(pg):
    c = collections.Counter(is_landmark(pg, b) for b in pg.order if is_landmark(pg, b))
    return {r: c.get(r, 0) for r in CORE + ['search', 'region', 'form']}


def det_tableheads(pg):
    out = []
    near_table = {}
    for b in pg.order:
        t = None
        for a in pg.ancestors(b):
            if pg.els[a]['tag'] == 'table':
                t = a; break
        near_table[b] = t
    for b in pg.order:
        e = pg.els[b]
        if pg.hidden(b):
            continue
        if e['tag'] == 'table':
            if e['attrs'].get('role', '').lower() in ('presentation', 'none'):
                continue
            rows = [d for d in pg.descendants(b) if pg.els[d]['tag'] == 'tr' and near_table[d] == b and not pg.hidden(d)]
            rows.sort(key=pg.order.index)
            cells = {r: [c for c in pg.kids.get(r, []) if pg.els[c]['tag'] in ('td', 'th')] for r in rows}
            if len(rows) < 2 or max((len(v) for v in cells.values()), default=0) < 2:
                continue
            ths = [d for d in pg.descendants(b) if near_table[d] == b and (pg.els[d]['tag'] == 'th' or pg.role(d) in ('columnheader', 'rowheader'))]
            if ths:
                continue
            first, second = rows[0], rows[1]
            in_thead = pg.els[pg.els[first]['parent']]['tag'] == 'thead' if pg.els[first]['parent'] else False

            def style(r):
                fs = []
                for c in cells[r]:
                    bearers = [c] + [d for d in pg.descendants(c) if pg.els[d]['own']]
                    bearers = [x for x in bearers if pg.els[x]['own']] or [c]
                    fs.append(pg.font(bearers[0]))
                return fs
            s1, s2 = style(first), style(second)
            w1 = max((f[1] for f in s1), default=400); w2 = max((f[1] for f in s2), default=400)
            styled = (w1 >= 600 and w1 > w2) or ({f[3] for f in s1} != {f[3] for f in s2} and w1 >= w2) \
                or (max((f[0] for f in s1), default=0) > max((f[0] for f in s2), default=0) + 0.5)
            layout = pg.role(b) in ('LayoutTable', 'presentation', 'none', '')
            if styled or in_thead:
                out.append(pg.example(b, signature='th-less-table', subtype='styled-header-row' + (' (thead)' if in_thead else ''),
                                      verdict='exact', rows=len(rows), cols=max(len(v) for v in cells.values()),
                                      first_row=' | '.join(pg.els[c]['text'][:30] for c in cells[first])[:200]))
            elif not layout:
                out.append(pg.example(b, signature='th-less-table', subtype='no-header-row', verdict='kind-only', rows=len(rows),
                                      cols=max(len(v) for v in cells.values())))
        elif e['attrs'].get('role', '').lower() in ('table', 'grid', 'treegrid'):
            desc = list(pg.descendants(b))
            rows = [d for d in desc if pg.els[d]['attrs'].get('role') == 'row']
            cells = [d for d in desc if pg.els[d]['attrs'].get('role') in ('cell', 'gridcell')]
            heads = [d for d in desc if pg.els[d]['attrs'].get('role') in ('columnheader', 'rowheader') or pg.els[d]['tag'] == 'th']
            if len(rows) >= 2 and len(cells) >= 2 and not heads:
                out.append(pg.example(b, signature='aria-table-without-headers', verdict='equivalent', rows=len(rows)))
    return out


DETECTORS = {'names': det_names, 'labels': det_labels, 'alt': det_alt, 'headings': det_headings,
             'landmarks': det_landmarks, 'tableheads': det_tableheads}


def context(pg):
    c = collections.Counter()
    for b in pg.order:
        if pg.hidden(b):
            continue
        e = pg.els[b]; r = pg.role(b)
        if r == 'heading' and not pg.ignored(b):
            c['ax_headings'] += 1
        if r in ('button', 'link') and not pg.ignored(b):
            c['buttons_links'] += 1
        if e['tag'] == 'img':
            c['img'] += 1
            if e['attrs'].get('alt') == '':
                c['img_alt_empty_decorative'] += 1
        if e['tag'] in ('input', 'textarea', 'select') and not (e['tag'] == 'input' and e['attrs'].get('type', 'text').lower() in LABELABLE_SKIP_TYPES):
            c['form_controls'] += 1
        if e['tag'] == 'table':
            c['tables'] += 1
    return {**dict(c), 'landmarks': landmark_context(pg), 'dominant_text_px': pg.D, 'style_source': 'capture-stamps' if pg.stamped else 'this-render'}


def page_verdict(kind, items, ctx):
    if not items:
        return 'none'
    if kind == 'landmarks':
        return 'exact' if not any(ctx['landmarks'][r] for r in CORE) else 'partial'
    vs = collections.Counter(i['verdict'] for i in items)
    for v in ('exact', 'equivalent', 'kind-only'):
        if vs.get(v):
            return v
    return 'none'


def analyze_file(path, examples=5, strip_attrs=(), viewport=None):
    loaded = load_mhtml(path) if re.search(r'\.mht(ml)?$', path, re.I) else load_json_capture(path)
    vp = viewport or (loaded['meta'].get('viewport') or {})
    vp = {'width': int(vp.get('width') or 1280), 'height': int(vp.get('height') or 720)}
    r = render(loaded, vp, strip_attrs)
    pg = Page(r)
    ctx = context(pg)
    res = {'file': os.path.basename(path), 'input_format': loaded['kind'], 'meta': loaded['meta'], 'render_viewport': vp,
           'safety': {'requests_served': sum(1 for x in r['requests'] if x['action'] == 'served'),
                      'requests_aborted': sum(1 for x in r['requests'] if x['action'] == 'aborted'),
                      'aborted_sample': [x['url'] for x in r['requests'] if x['action'] == 'aborted'][:10],
                      'final_url_is_served_url': r['final_url'] == loaded['root_url'],
                      'page_script_marker': r['dom'].get('ran'), 'cleanup': r['cleaned']},
           'elements': len(pg.order), 'context': ctx, 'kinds': {}}
    all_items = {}
    for k in KINDS:
        items = DETECTORS[k](pg)
        all_items[k] = items
        res['kinds'][k] = {'count': len(items), 'page_verdict': page_verdict(k, items, ctx),
                           'by_verdict': dict(collections.Counter(i['verdict'] for i in items)),
                           'by_signature': dict(collections.Counter(i['signature'] for i in items)),
                           'examples': items[:examples]}
    return res, r, all_items


def expand(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for pat in ('*.rwk.json', '*.mhtml', '*.mht'):
                out += sorted(glob.glob(os.path.join(p, '**', pat), recursive=True))
        else:
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out')
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--examples', type=int, default=5)
    ap.add_argument('--strip-attr', action='append', default=[], help='remove this attribute everywhere before analysis')
    ap.add_argument('--all-items', action='store_true', help='also write every instance (not only examples)')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for f in expand(a.paths):
        stem = re.sub(r'\.rwk\.json$', '.json', os.path.basename(f), flags=re.I)
        try:
            res, r, items = analyze_file(f, a.examples, a.strip_attr)
        except Exception as e:  # noqa: BLE001
            rows.append({'file': os.path.basename(f), 'error': f'{type(e).__name__}: {str(e)[:300]}'})
            print('ERROR', f, e, file=sys.stderr)
            continue
        if a.all_items:
            res['all_items'] = items
        json.dump(res, open(os.path.join(a.out, stem + '.analysis.json'), 'w'), indent=1)
        open(os.path.join(a.out, stem + '.tree.txt'), 'w').write(r['tree_all'])
        open(os.path.join(a.out, stem + '.viewport.txt'), 'w').write(r['tree_viewport'])
        row = {'file': res['file'], 'format': res['input_format'], 'url': res['meta'].get('url'),
               **{k: f"{v['count']} {v['page_verdict']}" for k, v in res['kinds'].items()},
               'aborted': res['safety']['requests_aborted'], 'landmarks_present': [k for k, v in res['context']['landmarks'].items() if v]}
        rows.append(row)
        if not a.quiet:
            print(json.dumps(row), flush=True)
    json.dump(rows, open(os.path.join(a.out, 'summary.json'), 'w'), indent=1)
    with open(os.path.join(a.out, 'summary.md'), 'w') as fh:
        fh.write('# Real-world exemplar analysis\n\n> **Summary:** per page and kind: instances found, page verdict against the codemod form.\n\n')
        fh.write('| file | ' + ' | '.join(KINDS) + ' | landmarks present |\n|' + '---|' * (len(KINDS) + 2) + '\n')
        for row in rows:
            if 'error' in row:
                fh.write(f"| {row['file']} | error: {row['error']} |\n")
            else:
                fh.write(f"| {row['file']} | " + ' | '.join(row[k] for k in KINDS) + f" | {', '.join(row['landmarks_present']) or 'none'} |\n")


if __name__ == '__main__':
    main()
