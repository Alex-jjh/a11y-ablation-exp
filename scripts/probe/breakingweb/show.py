import sys
from breakingweb.browsergym_env import make_env
from browsergym.utils.obs import flatten_axtree_to_str
env = make_env(sys.argv[1], headless=True); obs, _ = env.reset()
txt = flatten_axtree_to_str(obs['axtree_object'], extra_properties=obs.get('extra_element_properties', {}), with_clickable=True, with_visible=True, filter_visible_only=True, filter_with_bid_only=True)
L = txt.splitlines(); i = next((k for k, l in enumerate(L) if sys.argv[2] in l), None)
print('lines', len(L), 'chars', len(txt)); print('\n'.join(L[max(0, (i or 0)-2):(i or 0)+4]) if i is not None else f'"{sys.argv[2]}" NOT IN OBSERVATION')
env.close()
