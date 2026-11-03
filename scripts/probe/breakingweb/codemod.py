#!/usr/bin/env python3
"""Source-level accessibility defects for one BreakingWeb environment (a "site built with defect X").

Each kind rewrites the JSX in src/**/*.tsx the way a developer who omitted the semantics
would have written it, keeps every class name and event handler (so React binds as
before), and rewrites tag selectors in src/**/*.css so the page looks the same.

Kinds and their real-world grounding (see literature/syntheses/2026-10-29-DQ-form.md):
  landmarks  header/nav/main/footer/aside -> div, landmark roles dropped
             (WebAIM2026: 46.1% of home pages have <main>; div-only layouts)
  headings   h1-h6 -> div styled like the heading (W3C failure F2)
  names      aria-label removed from buttons and links: icon-only controls become empty,
             labelled ones fall back to their visible text (WebAIM2026: empty buttons
             30.6%, empty links 46.3% of pages; ambiguous repeated link text, SC 2.4.4)
  labels     htmlFor and aria-label/aria-labelledby removed from form controls (also when
             passed as keys of an *inputProps object to a field component); visible text kept (WebAIM2026: 51% of pages have unlabeled inputs; failure F68)
  alt        alt removed from img (WebAIM2026: 16.2% of images lack alt)
  tableheads th -> td (failure F91)
  none       rebuild only (sham / noise run)

How the look is kept for tag-replacing kinds (headings, landmarks, tableheads); revised
2026-10-30 after the booking headings variant changed page height (version of 2026-10-29
is in git history, commit 8b66c92):
  1. Every author type selector for a replaced tag T matches the replacement too, with the
     same specificity: T -> :is(T, R:where([data-amt="T"])) where R is the replacement tag
     (div or td); both arguments have specificity (0,0,1), so the cascade order is kept.
  2. Author type selectors for the replacement tag R no longer match replacements:
     R -> R:not(:where([data-amt])), specificity still (0,0,1). Without this, rules such as
     `.lms-table td {...}` would start to style converted th cells.
  3. The UA defaults the replaced tag had (font-size, margins, weight, alignment) are added
     inside `@layer amt-ua`. Unlayered author rules beat layered rules whatever their
     specificity, just as author rules beat the UA stylesheet; so resets such as
     `* { margin: 0 }` (booking) still win. The 2026-10-29 version added these defaults
     unlayered with zero specificity after the app's CSS, so they beat `*` resets: that was
     the booking height change.
  4. Chromium's sectioning rules for h1 (h1 inside article/aside/nav/section gets a smaller
     size) are reproduced for replaced h1 and for real h1 inside a replaced nav/aside.
  The values are those of Chromium 125 (the browser BrowserGym launches here), checked by
  ua_delta.py, which compares every computed property of real and replaced elements.
  Limit: th's `text-align: -internal-center` cannot be written in author CSS; the layer
  uses `center`, which differs from a real th only when its row inherits a non-initial
  text-align. ua_delta.py reports this case.

Tag matching (revised 2026-10-30): a JSX start tag is matched up to its own `>` with brace
groups and quoted strings consumed whole. The 2026-10-29 pattern stopped at the `>` of an
arrow function (`onChange={(e) => ...}`), so attributes after a handler were not removed
(on the 2026-10-29 sources: 77 of 544 button/link tags kept aria-label for `names`, 114 of
268 form-control tags kept it for `labels`).

The script refuses CSS that uses @layer (the amt-ua layer must be the lowest author layer)
and reports risks it cannot fix: *-of-type selectors (a replaced tag changes the sibling
type count), attribute selectors on attributes the kind removes, and script code that
queries the replaced tags.

Usage: codemod.py ENV_SRC_DIR KIND      (writes in place; revert with git checkout)
       prints a dict of change counts and risk counts
"""
import glob
import os
import re
import sys

UA = {  # Chromium 125 UA stylesheet values for headings (checked by ua_delta.py)
    'h1': 'display:block;font-size:2em;margin-block:0.67em;font-weight:bold',
    'h2': 'display:block;font-size:1.5em;margin-block:0.83em;font-weight:bold',
    'h3': 'display:block;font-size:1.17em;margin-block:1em;font-weight:bold',
    'h4': 'display:block;margin-block:1.33em;font-weight:bold',
    'h5': 'display:block;font-size:0.83em;margin-block:1.67em;font-weight:bold',
    'h6': 'display:block;font-size:0.67em;margin-block:2.33em;font-weight:bold',
}
# Chromium: h1 nested in 1..5 sectioning elements (article, aside, nav, section)
H1_SECTIONED = ['font-size:1.5em;margin-block:0.83em', 'font-size:1.17em;margin-block:1em',
                'font-size:1em;margin-block:1.33em', 'font-size:0.83em;margin-block:1.67em',
                'font-size:0.67em;margin-block:2.33em']
SECTIONING = ['article', 'aside', 'nav', 'section']
LANDMARK_TAGS = ['header', 'nav', 'main', 'footer', 'aside']
LANDMARK_ROLES = ['banner', 'navigation', 'main', 'contentinfo', 'complementary', 'search', 'region']
HEADING_TAGS = [f'h{i}' for i in range(1, 7)]
# kind -> (replaced tags, replacement tag)
REPLACE = {'landmarks': (LANDMARK_TAGS, 'div'), 'headings': (HEADING_TAGS, 'div'), 'tableheads': (['th'], 'td')}
# attributes each kind removes (for the attribute-selector risk scan)
REMOVED_ATTRS = {'landmarks': ['role'], 'headings': ['role'], 'names': ['aria-label', 'aria-labelledby'],
                 'labels': ['for', 'aria-label', 'aria-labelledby'], 'alt': ['alt'], 'tableheads': []}
# a JSX start tag's body up to its closing `>`: brace groups first (they may contain `=>` or
# `>`), nested three deep (template literals); plain characters exclude braces. The 2026-10-29
# version tried plain characters first, so the match ended at the `>` of `onChange={(e) => ...}`
# and attributes after such a handler were left in place.
BRACES = r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
TAG_BODY = r'(?:' + BRACES + r'|"[^"]*"|\'[^\']*\'|[^<>{}"\'])*>'
ATTR = r'(?:"[^"]*"|\'[^\']*\'|' + BRACES + r')'


def tsx_files(src):
    return [f for f in glob.glob(os.path.join(src, '**', '*.tsx'), recursive=True) if '/node_modules/' not in f]


def ts_files(src):
    return [f for f in glob.glob(os.path.join(src, '**', '*.ts'), recursive=True) if '/node_modules/' not in f] + tsx_files(src)


def css_files(src):
    return [f for f in glob.glob(os.path.join(src, '**', '*.css'), recursive=True) if '/node_modules/' not in f]


def _strip_prop_object_keys(s, keys, bump, counter):
    """Remove `"key": value,` entries from object literals passed as *inputProps / textareaProps /
    selectProps (gmail passes control aria-labels to a shared field component this way)."""
    out, i = [], 0
    for m in re.finditer(r'\b\w*(?:inputProps|InputProps|textareaProps|selectProps)=\{\{', s):
        if m.start() < i:
            continue
        start = m.end() - 1                      # the object's opening brace
        depth, j = 0, start
        while j < len(s):
            c = s[j]
            if c in '"\'`':                       # skip string / template literal
                q = c; j += 1
                while j < len(s) and s[j] != q:
                    j += 2 if s[j] == '\\' else 1
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = s[start:j + 1]
        for k in keys:
            body, n = re.subn(r'\s*["\']' + k + r'["\']\s*:\s*(?:"[^"]*"|\'[^\']*\'|`[^`]*`|' + BRACES + r'|[\w.]+)\s*,?', '', body)
            bump(counter, n)
        out.append(s[i:start]); out.append(body); i = j + 1
    out.append(s[i:])
    return ''.join(out)


def rewrite_markup(s, kind, bump):
    """JSX (or HTML) source -> the same source written without the kind's semantics."""
    if kind == 'landmarks':
        for t in LANDMARK_TAGS:
            s, n = re.subn(rf'<{t}(?=[\s>])', f'<div data-amt="{t}"', s); bump(t, n)
            s = re.sub(rf'</{t}>', '</div>', s)
        s, n = re.subn(r'\srole=["\'](?:' + '|'.join(LANDMARK_ROLES) + r')["\']', '', s); bump('role', n)
    elif kind == 'headings':
        for t in HEADING_TAGS:
            s, n = re.subn(rf'<{t}(?=[\s>])', f'<div data-amt="{t}"', s); bump(t, n)
            s = re.sub(rf'</{t}>', '</div>', s)
        s, n = re.subn(r'\srole=["\']heading["\']', '', s); bump('role', n)
    elif kind == 'names':
        # aria-label / aria-labelledby on intrinsic or component buttons and links
        def strip(m):
            bump('aria-label')
            return re.sub(r'\saria-(?:label|labelledby)=' + ATTR, '', m.group(0))
        s = re.sub(r'<(?:button|a|Link|NavLink|Button|IconButton)\b' + TAG_BODY, strip, s)
    elif kind == 'labels':
        s, n = re.subn(r'\shtmlFor=(?:"[^"]*"|\'[^\']*\'|\{[^{}]*\})', '', s); bump('htmlFor', n)
        def strip(m):
            bump('control-aria')
            return re.sub(r'\saria-(?:label|labelledby)=' + ATTR, '', m.group(0))
        s = re.sub(r'<(?:input|textarea|select)\b' + TAG_BODY, strip, s)
        s = _strip_prop_object_keys(s, ['aria-label', 'aria-labelledby'], bump, 'control-aria-props')
    elif kind == 'alt':
        def strip(m):
            bump('img')
            return re.sub(r'\salt=' + ATTR, '', m.group(0))
        s = re.sub(r'<img\b' + TAG_BODY, strip, s)
    elif kind == 'tableheads':
        s, n = re.subn(r'<th(?=[\s>])', '<td data-amt="th"', s); bump('th', n)
        s = re.sub(r'</th>', '</td>', s)
    elif kind == 'none':
        pass  # rebuild only: measures run-to-run noise of capture and rendering
    else:
        raise SystemExit(f'unknown kind {kind}')
    return s


def _type_token(tag):
    # a type selector token: not part of a class/id/attribute/pseudo/name, not followed by a name char
    return rf'(?<![\w\-.#:\[="\'(@%]){tag}(?![\w\-(])'


def map_selectors(css, fn):
    """Apply fn to every selector prelude (text before `{` that is not an at-rule prelude)."""
    css = re.sub(r'/\*.*?\*/', lambda m: re.sub(r'[{}]', '', m.group(0)), css, flags=re.S)  # braces in comments
    def one(m):
        pre = m.group(2)
        return m.group(1) + (pre if pre.strip().startswith('@') or re.fullmatch(r'\s*[\d.%,\s]*(from|to)?[\d.%,\s]*', pre) else fn(pre))
    return re.sub(r'(^|[{};])([^{};]*)(?=\{)', one, css)


def rewrite_css(c, kind, bump):
    if kind not in REPLACE:
        return c
    tags, repl = REPLACE[kind]
    def fn(pre):
        n0 = pre
        pre = re.sub(_type_token(repl), f'{repl}:not(:where([data-amt]))', pre)   # step 2
        if pre != n0:
            bump(f'css-{repl}-guard')
        for t in tags:                                                             # step 1
            pre, n = re.subn(_type_token(t), f':is({t},{repl}:where([data-amt="{t}"]))', pre)
            bump(f'css-{t}', n)
        return pre
    return map_selectors(c, fn)


def ua_layer(kind):
    """UA defaults of the replaced tags, inside the lowest-priority author layer (step 3, 4)."""
    rules = []
    if kind == 'headings':
        rules += [f':where([data-amt="{h}"]){{{v}}}' for h, v in UA.items()]
    if kind == 'landmarks':
        rules.append(':where(' + ','.join(f'[data-amt="{t}"]' for t in LANDMARK_TAGS) + '){display:block}')
    if kind in ('headings', 'landmarks'):
        sect = ':where(' + ','.join(SECTIONING + ['div[data-amt="aside"]', 'div[data-amt="nav"]']) + ')'
        h1 = ':where(h1,div[data-amt="h1"])'
        for depth, v in enumerate(H1_SECTIONED, 1):
            rules.append(' '.join([sect] * depth + [h1]) + f'{{{v}}}')
    if kind == 'tableheads':
        rules.append(':where(td[data-amt="th"]){font-weight:bold;text-align:center}')
    if not rules:
        return ''
    return '@layer amt-ua{\n' + '\n'.join(rules) + '\n}'


def risks(src, kind, bump):
    """Things the rewrite cannot keep equal; reported, checked by the gate."""
    for f in css_files(src):
        c = open(f).read()
        if '@layer' in c and 'amt-ua' not in c:
            raise SystemExit(f'{f} uses @layer: the amt-ua layer would not be the lowest author layer')
        if kind in REPLACE:
            bump('risk-of-type-selectors', len(re.findall(r':(?:first|last|only|nth|nth-last)-of-type', c)))
        for a in REMOVED_ATTRS.get(kind, []):
            sel = re.findall(rf'\[{a}(?=[\]=~|^$*\s])[^\]]*\]', c)
            if a == 'role':
                roles = LANDMARK_ROLES if kind == 'landmarks' else ['heading']
                sel = [x for x in sel if any(r in x for r in roles)]
            bump(f'risk-css-attr-{a}', len(sel))
    if kind in REPLACE:
        tags = REPLACE[kind][0]
        pat = re.compile(r'(?:querySelector(?:All)?|closest|matches|getElementsByTagName)\(\s*[\'"`][^\'"`]*\b(?:'
                         + '|'.join(tags) + r')\b|tagName\s*===?\s*[\'"](?:' + '|'.join(t.upper() for t in tags) + ')')
        for f in ts_files(src):
            bump('risk-script-tag-query', len(pat.findall(open(f).read())))


def rewrite(src, kind):
    counts = {}
    def bump(k, n=1):
        if n:
            counts[k] = counts.get(k, 0) + n
    if kind not in ('landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads', 'none'):
        raise SystemExit(f'unknown kind {kind}')
    risks(src, kind, bump)
    for f in tsx_files(src):
        s0 = open(f).read()
        s = rewrite_markup(s0, kind, bump)
        if s != s0:
            open(f, 'w').write(s)
    for f in css_files(src):
        c0 = open(f).read()
        c = rewrite_css(c0, kind, bump)
        if c != c0:
            open(f, 'w').write(c); bump('css-files')
    extra = ua_layer(kind)
    if extra:
        main_css = sorted(css_files(src), key=len)[0]
        open(main_css, 'a').write('\n/* amt defect styles */\n' + extra + '\n')
    return counts


if __name__ == '__main__':
    print(rewrite(sys.argv[1], sys.argv[2]))
