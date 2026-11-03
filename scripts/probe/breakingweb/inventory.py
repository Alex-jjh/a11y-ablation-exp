"""Accessibility-information inventory of BreakingWeb start pages, as the text agent sees them.

For each sampled task: reset the BrowserGym env (clean condition), take axtree_object,
flatten it with the same arguments as breakingweb/agent.py, and count per information kind:
landmarks (and whether named), headings (and whether the level is printed), tables
(table/row/columnheader/rowheader/cell), named vs unnamed buttons/links/textboxes/comboboxes/
checkboxes, images (named or not), ARIA states (expanded, selected, checked, pressed, ...).
Writes one JSON line per page to the output file.  Usage: inventory.py OUT.jsonl N_PER_ENV
"""
import json, re, sys, collections, glob, os
sys.path.insert(0, os.path.expanduser('~/.workspace/_refsrc/BreakingWeb'))
from breakingweb.browsergym_env import make_env
from browsergym.utils.obs import flatten_axtree_to_str

LANDMARK = {'banner', 'navigation', 'main', 'contentinfo', 'complementary', 'region', 'search', 'form'}
CONTROL = {'button', 'link', 'textbox', 'searchbox', 'combobox', 'checkbox', 'radio', 'menuitem', 'tab', 'switch', 'option', 'spinbutton', 'slider'}
TABLE = {'table', 'grid', 'row', 'columnheader', 'rowheader', 'cell', 'gridcell'}
STATES = {'expanded', 'selected', 'checked', 'pressed', 'disabled', 'required', 'invalid', 'haspopup', 'level'}

def val(d, k='value'):
    return (d or {}).get(k) or ''

def page_stats(obs):
    nodes = obs['axtree_object']['nodes']
    c = collections.Counter(); props = collections.Counter()
    for n in nodes:
        if n.get('ignored'):
            continue
        role = val(n.get('role')); name = str(val(n.get('name'))).strip()
        if role in LANDMARK:
            c[f'landmark:{role}'] += 1; c['landmark_named' if name else 'landmark_unnamed'] += 1
        if role == 'heading':
            c['heading'] += 1
            lvl = [p for p in n.get('properties', []) if p.get('name') == 'level']
            if lvl: c['heading_has_level_prop'] += 1
        if role in TABLE: c[f'table:{role}'] += 1
        if role in CONTROL:
            c[f'ctl:{role}'] += 1; c[f'ctl:{role}:{"named" if name else "unnamed"}'] += 1
        if role in ('img', 'image'):
            c['img'] += 1; c['img_named' if name else 'img_unnamed'] += 1
        for p in n.get('properties', []):
            if p.get('name') in STATES: props[p['name']] += 1
    txt = flatten_axtree_to_str(obs['axtree_object'], extra_properties=obs.get('extra_element_properties', {}),
                                with_clickable=True, with_visible=True, filter_visible_only=True, filter_with_bid_only=True)
    t = collections.Counter()
    for line in txt.splitlines():
        m = re.match(r"\s*\[\w+\]\s+(\w+)", line)
        if m: t[m.group(1)] += 1
    head_lines = [l for l in txt.splitlines() if re.match(r"\s*\[\w+\]\s+heading", l)]
    return {'tree': dict(c), 'states': dict(props), 'text_roles': dict(t), 'text_chars': len(txt),
            'heading_lines_with_level': sum(1 for l in head_lines if 'level' in l), 'heading_lines': len(head_lines),
            'sample_heading': head_lines[:2], 'sample_landmark': [l for l in txt.splitlines() if re.match(r"\s*\[\w+\]\s+(navigation|main|banner|contentinfo|complementary|region)", l)][:3]}

def main(out, n):
    root = os.path.expanduser('~/.workspace/_refsrc/BreakingWeb/breakingweb/tasks')
    with open(out, 'w') as f:
        for env_dir in sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))):
            for path in sorted(glob.glob(os.path.join(root, env_dir, '*.yaml')))[:n]:
                tid = os.path.basename(path)[:-5]
                try:
                    env = make_env(tid, headless=True)
                    obs, info = env.reset()
                    rec = {'task': tid, 'env': env_dir, 'url': obs.get('url'), **page_stats(obs)}
                    env.close()
                except Exception as e:  # noqa: BLE001
                    rec = {'task': tid, 'env': env_dir, 'error': f'{type(e).__name__}: {str(e)[:200]}'}
                f.write(json.dumps(rec) + '\n'); f.flush()
                print(tid, rec.get('error') or rec['text_chars'], flush=True)

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
