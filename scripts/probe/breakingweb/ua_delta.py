#!/usr/bin/env python3
"""Check that codemod.py's look-keeping CSS reproduces the replaced tags' UA styles in Chromium.

Question: after codemod.py replaces h1-h6 / landmarks / th by div / td, does every element
on the page keep every computed CSS property and its box, under the kinds of author CSS
the BreakingWeb apps use (no CSS, a `* {margin:0;padding:0}` reset as in booking, tag and
descendant rules on headings, td and th, and a `tr {text-align:right}` case that the layer
is known not to reproduce)?

Method: one fixture page with headings at top level and inside nested sectioning elements
(1-6 deep), landmarks containing h1, a card, and a table with th in thead and tbody. The
clean page uses the real tags; the variant page is the same HTML passed through
codemod.rewrite_markup, its author CSS through codemod.rewrite_css, plus codemod.ua_layer.
For every element (matched by document order) all computed properties
(getComputedStyle, every property name) and getBoundingClientRect are compared.
Chromium is the Playwright build in the BreakingWeb venv (the browser BrowserGym launches).

Positive control: the same comparison with the 2026-10-29 look-keeping CSS (OLD_CSS below,
copied from that version: unlayered zero-specificity defaults, `T -> :is(T,[data-amt=T])`)
must show mismatches under `star_reset` (the booking mechanism); reported as kind "old_*".

Inputs: none (fixture is inline). Output: JSON to stdout and to OUT if given:
  {kind: {css_case: {"elements": n, "mismatched_elements": n, "examples": [...]}}}
Run:  ~/.workspace/_refsrc/BreakingWeb/.venv/bin/python ua_delta.py [OUT.json]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codemod  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

BODY = '''
<header class="top"><nav><a href="#">home</a><h1>Nav title</h1></nav></header>
<main>
<h1>A</h1><h2>B</h2><h3>C</h3><h4>D</h4><h5>E</h5><h6>F</h6>
<section><h1>S1</h1><article><h1>S2</h1><section><h1>S3</h1><aside><h1>S4</h1>
<nav><h1>S5</h1><section><h1>S6</h1><h2>S6b</h2></section></nav></aside></section></article></section>
<div class="card"><h2>Card title</h2><div>card body</div><p>para</p></div>
<aside role="complementary"><h1>Side</h1><h3>side h3</h3></aside>
<div role="heading" aria-level="2">aria heading</div>
<table class="t"><thead><tr><th>Head 1</th><th>Head 2</th></tr></thead>
<tbody><tr><th>row head</th><td>cell</td></tr></tbody></table>
<table class="r"><tr><th>right row head</th><td>x</td></tr></table>
</main>
<footer><p>foot</p><h2>Footer h2</h2></footer>
'''
CSS = {
    'no_author_css': '',
    'star_reset': '* { box-sizing: border-box; margin: 0; padding: 0; } body { font-size: 14px; line-height: 1.5; }',
    'tag_rules': ('h1, h2, h3 { margin: 0 0 4px; } .card h2 { font-size: 18px; } div { padding: 1px; } '
                  'main > div { border: 1px solid #ccc; } .t td { border-bottom: 1px solid red; padding: 6px; } '
                  '.t th { font-weight: 600; text-align: left; } nav h1 { color: blue; } header { height: 40px; } '
                  'h2 + div { color: green; } footer { margin-top: 10px; }'),
    'tr_text_align_right': '.r tr { text-align: right; }',
}
JS = '''() => [...document.querySelectorAll('body *')].map(e => {
  const s = getComputedStyle(e), o = {};
  for (let i = 0; i < s.length; i++) o[s[i]] = s.getPropertyValue(s[i]);
  const r = e.getBoundingClientRect();
  return {tag: e.tagName, text: (e.firstChild && e.firstChild.nodeType === 3 ? e.firstChild.data : '').slice(0, 20),
          rect: [r.x, r.y, r.width, r.height].map(v => Math.round(v * 100) / 100), style: o};
})'''


def old_css(css, kind):
    """2026-10-29 codemod CSS (positive control)."""
    import re
    tags = {'landmarks': codemod.LANDMARK_TAGS, 'headings': codemod.HEADING_TAGS, 'tableheads': ['th']}[kind]
    for t in tags:
        css = re.sub(rf'(?<![\w\-.#:\[="]){t}(?![\w\-])(?=[^{{}}]*\{{)', f':is({t},[data-amt="{t}"])', css)
    extra = {'headings': '\n'.join(f':where([data-amt="{h}"]){{{v}}}' for h, v in codemod.UA.items()),
             'landmarks': ':where([data-amt="header"],[data-amt="nav"],[data-amt="main"],[data-amt="footer"],[data-amt="aside"]){display:block}',
             'tableheads': ':where([data-amt="th"]){font-weight:bold;text-align:-internal-center}'}[kind]
    return css + '\n' + extra


def page_html(body, css):
    return f'<!doctype html><html><head><style>{css}</style></head><body>{body}</body></html>'


def main(out=None):
    res = {}
    noop = lambda k, n=1: None
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        res['chromium'] = b.version
        for kind in ('headings', 'landmarks', 'tableheads', 'old_headings', 'old_landmarks', 'old_tableheads'):
            res[kind] = {}
            k = kind.replace('old_', '')
            vbody = codemod.rewrite_markup(BODY, k, noop)
            for case, css in CSS.items():
                pg.set_content(page_html(BODY, css)); A = pg.evaluate(JS)
                vcss = old_css(css, k) if kind.startswith('old_') else codemod.rewrite_css(css, k, noop) + '\n' + codemod.ua_layer(k)
                pg.set_content(page_html(vbody, vcss)); B = pg.evaluate(JS)
                assert len(A) == len(B), (kind, case, len(A), len(B))
                ex, bad = [], 0
                for a, v in zip(A, B):
                    d = {k: [a['style'][k], v['style'].get(k)] for k in a['style'] if a['style'][k] != v['style'].get(k)}
                    if a['rect'] != v['rect']:
                        d['rect'] = [a['rect'], v['rect']]
                    if d:
                        bad += 1
                        ex.append({'clean': a['tag'], 'variant': v['tag'], 'text': a['text'], 'diff': d})
                res[kind][case] = {'elements': len(A), 'mismatched_elements': bad, 'examples': ex[:6]}
        b.close()
    s = json.dumps(res, indent=1)
    print(s)
    if out:
        open(out, 'w').write(s)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
