#!/usr/bin/env python3
"""Save pages that we render ourselves (fixtures, BreakingWeb builds) the way Alex saves real pages.

`save(page, stem)` runs capture_snippet.js in the live page exactly as pasted in the DevTools
console, except that the last line (`rwkCapture({download: true});`) is replaced by a call that
returns the record instead of downloading it, and writes `<stem>.rwk.json`. It also writes
`<stem>.mhtml` with DevTools' Page.captureSnapshot (format mhtml), which runs Blink's MHTML
serializer, the one Chrome's "Save page as > Webpage, Single File" uses [assumption: same
serializer; the output header says "Saved by Blink"].

Only for pages we serve ourselves; it never navigates anywhere.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SNIPPET = os.path.join(HERE, 'capture_snippet.js')
LAST = 'rwkCapture({download: true});'


def snippet_return_js():
    src = open(SNIPPET).read().rstrip()
    lines = src.splitlines()
    assert lines[-1].strip() == LAST, 'capture_snippet.js must end with the download call'
    body = '\n'.join(lines[:-1])
    return '() => {\n' + body + '\nreturn rwkCapture({download: false});\n}'


def save(page, stem, mhtml=True):
    rec = page.evaluate(snippet_return_js())
    os.makedirs(os.path.dirname(stem) or '.', exist_ok=True)
    json.dump(rec, open(stem + '.rwk.json', 'w'))
    if mhtml:
        cdp = page.context.new_cdp_session(page)
        data = cdp.send('Page.captureSnapshot', {'format': 'mhtml'})['data']
        cdp.detach()
        open(stem + '.mhtml', 'w', newline='').write(data)
    return rec
