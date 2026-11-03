#!/usr/bin/env python3
"""Self-test of the real-world kit on pages we write ourselves; no real site is fetched.

1. Fixtures (fixtures/*.html, one positive and one negative page per kind, plus privacy.html):
   rendered with scripts ON in a fresh Chromium, as Alex's Chrome would show them (served from
   http://fixture.test/ by a route handler; nothing leaves the process), saved with
   harness.save() as .rwk.json (capture_snippet.js) and .mhtml (Blink serializer), then
   analysed by analyze.py. Expectation: a positive page has exactly EXPECT[kind] instances of
   its kind with the stated verdicts and 0 of every other kind; a negative page has 0 of every
   kind. Both formats must agree.
2. Privacy: the saved privacy.rwk.json must contain none of the planted secrets (e-mail, typed
   and prefilled input values, textarea text, contenteditable draft, csrf values, session
   query string, long digit runs, base64 session, inline-script state). The MHTML of the same
   page is checked too and the secrets it keeps are reported (CAPTURE.md's warning).
3. Isolation: two hand-made hostile inputs (JSON and MHTML) with inline scripts, an onerror
   handler, meta refresh, @import, external stylesheet/image/iframe/prefetch/video poster
   and a <noscript> link, all pointing at a beacon HTTP server on 127.0.0.1 (loopback is not
   covered by the proxy or the DNS rule, so only the route handler stands between the page
   and the server). Expectation: 0 hits on the beacon, no script marker, final URL unchanged,
   noscript content absent from the tree.

Usage: selftest.py OUT_DIR    (BreakingWeb venv python, -I). Writes OUT_DIR/selftest.json.
"""
import http.server
import io
import json
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze  # noqa: E402
import harness  # noqa: E402

FIX = os.path.join(HERE, 'fixtures')
# kind -> (expected count, expected verdict counts)
EXPECT = {
    'names': (8, {'exact': 8}),          # 2 empty icon buttons (one in an open shadow root) + 3 "Add to Cart" + 3 "Details"
    'labels': (4, {'exact': 3, 'equivalent': 1}),   # 2 orphan <label>, 1 placeholder-only, 1 span text
    'alt': (2, {'exact': 2}),
    'headings': (5, {'exact': 5}),       # 2 section titles + 3 card titles as styled divs
    'landmarks': (4, {'exact': 4}),      # header, nav, #content, footer as divs
    'tableheads': (1, {'exact': 1}),
}
SECRETS = ['jane.doe@example.com', 'secret-typed-text', 'prefilled-private-value', 'typed private message', 'draft private body',
           'hiddenCsrfTokenValue123', 'metaCsrfTokenValue', 's3cr3tSESSIONvalue', '4839201', '5550012', '98765432',
           'ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5', '__STATE__', '1234567890']


def png(w, h, rgb):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), rgb).save(b, 'PNG'); return b.getvalue()


def capture_fixtures(out):
    from playwright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True)
    imgs = {f'/img/p{i}.png': png(120, 120, c) for i, c in enumerate([(200, 80, 80), (80, 160, 90), (70, 90, 200)], 1)}
    imgs['/img/px.png'] = png(1, 1, (0, 0, 0))
    names = sorted(f[:-5] for f in os.listdir(FIX) if f.endswith('.html'))
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--host-resolver-rules=MAP * ~NOTFOUND'])
        for n in names:
            ctx = b.new_context(viewport={'width': 1280, 'height': 720})

            def route(r):
                path = re.sub(r'^http://fixture\.test', '', r.request.url).split('?')[0]
                if path.endswith('.html'):
                    r.fulfill(body=open(os.path.join(FIX, path.lstrip('/')), 'rb').read(), content_type='text/html; charset=utf-8')
                elif path == '/site.css':
                    r.fulfill(body=open(os.path.join(FIX, 'site.css'), 'rb').read(), content_type='text/css')
                elif path in imgs:
                    r.fulfill(body=imgs[path], content_type='image/png')
                else:
                    r.abort()
            ctx.route('**/*', route)
            pg = ctx.new_page()
            pg.goto(f'http://fixture.test/{n}.html', wait_until='load')
            pg.wait_for_timeout(200)
            harness.save(pg, os.path.join(out, n))
            ctx.close()
        b.close()
    return names


class Beacon(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        Beacon.hits.append(self.path); self.send_response(200); self.end_headers(); self.wfile.write(b'x')

    def log_message(self, *a):
        pass


def hostile_inputs(out, port):
    os.makedirs(out, exist_ok=True)
    bo = f'http://127.0.0.1:{port}'
    html = f'''<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={bo}/refresh">
<link rel="stylesheet" href="{bo}/a.css"><link rel="prefetch" href="{bo}/prefetch"><link rel="preconnect" href="{bo}">
<style>@import url({bo}/import.css); body {{ background: url({bo}/bg.png); }}</style>
<script>document.documentElement.setAttribute('data-rwk-script-ran', 'inline'); fetch('{bo}/fetch');</script></head>
<body><h1>Hostile page</h1><img src="{bo}/img.png" onerror="document.documentElement.setAttribute('data-rwk-script-ran','onerror')">
<iframe src="{bo}/frame"></iframe><video poster="{bo}/poster.png"></video><noscript><a href="/ns">noscript link</a></noscript>
<a href="javascript:document.documentElement.setAttribute('data-rwk-script-ran','js-url')">Go</a>
<form action="{bo}/submit"><input name="q" autofocus></form></body></html>'''
    rec = {'format': 'rwk-capture-1', 'url': 'http://hostile.test/', 'doctype': 'html', 'compat_mode': 'CSS1Compat',
           'viewport': {'width': 1280, 'height': 720}, 'html': html.replace('<!DOCTYPE html>', '')}
    json.dump(rec, open(os.path.join(out, 'hostile.rwk.json'), 'w'))
    # MHTML with a script part and an html root at a real-looking location
    import email.mime.multipart, email.mime.text, email.mime.base  # noqa: E401
    m = email.mime.multipart.MIMEMultipart('related')
    m['Snapshot-Content-Location'] = 'https://hostile.test/page'
    h = email.mime.text.MIMEText(html, 'html', 'utf-8'); h['Content-Location'] = 'https://hostile.test/page'; m.attach(h)
    s = email.mime.text.MIMEText(f"document.documentElement.setAttribute('data-rwk-script-ran','part');", 'javascript', 'utf-8')
    s['Content-Location'] = 'https://hostile.test/app.js'; m.attach(s)
    open(os.path.join(out, 'hostile.mhtml'), 'wb').write(m.as_bytes())
    return [os.path.join(out, 'hostile.rwk.json'), os.path.join(out, 'hostile.mhtml')]


def main(out):
    res = {'fixtures': {}, 'privacy': {}, 'isolation': {}, 'failures': []}
    fx = os.path.join(out, 'fixtures')
    names = capture_fixtures(fx)
    ana = os.path.join(out, 'fixtures-analysis')
    os.makedirs(ana, exist_ok=True)
    for n in names:
        for fmt in ('rwk.json', 'mhtml'):
            path = os.path.join(fx, f'{n}.{fmt}')
            r, raw, items = analyze.analyze_file(path, examples=20)
            json.dump(r, open(os.path.join(ana, f'{n}.{fmt}.analysis.json'), 'w'), indent=1)
            open(os.path.join(ana, f'{n}.{fmt}.tree.txt'), 'w').write(raw['tree_all'])
            counts = {k: r['kinds'][k]['count'] for k in analyze.KINDS}
            verd = {k: r['kinds'][k]['by_verdict'] for k in analyze.KINDS}
            row = {'counts': counts, 'verdicts': verd, 'page_verdict': {k: r['kinds'][k]['page_verdict'] for k in analyze.KINDS},
                   'aborted': r['safety']['requests_aborted'], 'style_source': r['context']['style_source']}
            res['fixtures'][f'{n}.{fmt}'] = row
            if n == 'privacy':
                continue
            kind, pol = n.rsplit('_', 1)
            for k in analyze.KINDS:
                if pol == 'pos' and k == kind:
                    ec, ev = EXPECT[k]
                    if counts[k] != ec or verd[k] != ev:
                        res['failures'].append(f'{n}.{fmt}: {k} count {counts[k]} {verd[k]}, expected {ec} {ev}')
                elif counts[k]:
                    res['failures'].append(f'{n}.{fmt}: {k} count {counts[k]} {verd[k]}, expected 0; e.g. '
                                           + json.dumps([(i["html"][:120], i.get("signature")) for i in r["kinds"][k]["examples"][:2]]))
            if pol == 'pos' and kind == 'landmarks' and row['page_verdict']['landmarks'] != 'exact':
                res['failures'].append(f'{n}.{fmt}: landmarks page verdict {row["page_verdict"]["landmarks"]}, expected exact')
    # privacy
    js = open(os.path.join(fx, 'privacy.rwk.json')).read()
    mh = open(os.path.join(fx, 'privacy.mhtml')).read()
    mh_dec = re.sub(r'=\r?\n', '', mh).replace('=3D', '=')
    res['privacy'] = {'json_leaks': [s for s in SECRETS if s in js], 'mhtml_keeps': [s for s in SECRETS if s in mh_dec],
                      'json_stats': json.loads(js)['stats'], 'json_has_masked_email_text': 'Signed in as [email]' in js,
                      'json_keeps_submit_text': 'Save changes' in js, 'json_keeps_in_page_anchor': 'href=\\"#help\\"' in js,
                      'json_query_hashed': bool(re.search(r'/orders\?session=h[0-9a-z]+&(?:amp;)?u=h[0-9a-z]+', js))}
    if not res['privacy']['json_query_hashed']:
        res['failures'].append('privacy: query values not replaced by hashes')
    if res['privacy']['json_leaks']:
        res['failures'].append(f'privacy: JSON keeps {res["privacy"]["json_leaks"]}')
    # isolation
    srv = http.server.HTTPServer(('127.0.0.1', 0), Beacon)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    for path in hostile_inputs(os.path.join(out, 'hostile'), port):
        Beacon.hits.clear()
        r, raw, _ = analyze.analyze_file(path)
        iso = {'beacon_hits': list(Beacon.hits), 'script_marker': r['safety']['page_script_marker'],
               'final_url_is_served_url': r['safety']['final_url_is_served_url'], 'served': r['safety']['requests_served'],
               'aborted': r['safety']['requests_aborted'], 'aborted_sample': r['safety']['aborted_sample'],
               'noscript_in_tree': 'noscript link' in raw['tree_all'], 'cleanup': r['safety']['cleanup']}
        res['isolation'][os.path.basename(path)] = iso
        if iso['beacon_hits'] or iso['script_marker'] or not iso['final_url_is_served_url'] or iso['noscript_in_tree']:
            res['failures'].append(f'isolation {os.path.basename(path)}: {iso}')
    srv.shutdown()
    json.dump(res, open(os.path.join(out, 'selftest.json'), 'w'), indent=1)
    for k, v in res['fixtures'].items():
        print(f'{k:28s}', ' '.join(f'{kk}={vv}' for kk, vv in v['counts'].items()))
    print('privacy', json.dumps(res['privacy']))
    print('isolation', json.dumps(res['isolation']))
    print('FAILURES' if res['failures'] else 'ALL PASS', *res['failures'], sep='\n')
    return 1 if res['failures'] else 0


if __name__ == '__main__':
    sys.setrecursionlimit(10000)
    sys.exit(main(sys.argv[1]))
