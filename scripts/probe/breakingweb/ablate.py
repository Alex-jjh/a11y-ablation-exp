"""Prototype of observation-layer ablation on a BreakingWeb page.

Transforms a deep copy of BrowserGym's axtree_object before flattening (the page is
untouched), prints line-level diffs per ablation, then checks that a bid whose name was
removed is still actionable on the real page.  Usage: ablate.py TASK_ID
"""
import copy, difflib, sys
from breakingweb.browsergym_env import make_env
from browsergym.utils.obs import flatten_axtree_to_str

LANDMARK = {'banner', 'navigation', 'main', 'contentinfo', 'complementary', 'region', 'search', 'form'}
TABLE = {'table', 'grid', 'row', 'rowgroup', 'columnheader', 'rowheader', 'cell', 'gridcell'}

def set_role(n, r): n['role'] = {'type': 'role', 'value': r}
def clear_name(n): n['name'] = {'type': 'computedString', 'value': ''}

ABLATIONS = {
    'landmarks->generic': lambda n: n.get('role', {}).get('value') in LANDMARK and set_role(n, 'generic'),
    'headings->generic': lambda n: n.get('role', {}).get('value') == 'heading' and set_role(n, 'generic'),
    'tables->generic': lambda n: n.get('role', {}).get('value') in TABLE and set_role(n, 'generic'),
    'control-names->empty': lambda n: n.get('role', {}).get('value') in ('button', 'link', 'textbox', 'combobox', 'checkbox', 'tab') and clear_name(n),
    'img-names->empty': lambda n: n.get('role', {}).get('value') in ('img', 'image') and clear_name(n),
}

def flat(obs, tree):
    return flatten_axtree_to_str(tree, extra_properties=obs.get('extra_element_properties', {}), with_clickable=True,
                                 with_visible=True, filter_visible_only=True, filter_with_bid_only=True)

env = make_env(sys.argv[1], headless=True)
obs, _ = env.reset()
base = flat(obs, obs['axtree_object'])
print('base lines', len(base.splitlines()), 'chars', len(base))
for name, fn in ABLATIONS.items():
    t = copy.deepcopy(obs['axtree_object'])
    for n in t['nodes']:
        fn(n)
    ab = flat(obs, t)
    diff = [l for l in difflib.unified_diff(base.splitlines(), ab.splitlines(), lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
    print(f'\n== {name}: {len(diff)//2} lines changed, chars {len(base)} -> {len(ab)}')
    for l in diff[:4]:
        print('  ', l[:120])
# the page itself is unchanged, so a renamed link is still clickable by its bid
link = next(l for l in base.splitlines() if " link '" in l)
bid = link.split('[')[1].split(']')[0]
url0 = obs['url']
obs2, *_ = env.step(f"click('{bid}')")
print('\nclicked', link.strip()[:80], '| url', url0, '->', obs2['url'], '| error:', obs2.get('last_action_error') or 'none')
env.close()
