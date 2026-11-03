#!/usr/bin/env python3
"""On-path dose of each accessibility-information kind for every BreakingWeb task.

Question: for each task (519) and each defect kind of codemod.py (names, labels, headings,
landmarks, tableheads, alt), how much of that kind lies on the path an agent actually takes,
and which tasks give on-path and off-path cells with baseline headroom.

Inputs
  ~/.hf-stage-bw/                 clean trajectory.json files from BreakingWeb/breakingweb-results-v2
                                  (gemini_3_1_pro, gemini_3_flash, gpt_5_4, gpt_5_4_mini, opus_4_7,
                                  qwen3_vl_235b) and -v3 (sonnet_46, opus_47_retry, pixel_*), no screenshots
  /tmp/amt-syn/bw-path/<model>/   replay records written by path_replay.py (one JSON per task)
  /tmp/amt-syn/bw-variants/<env>/clean/*.all.txt   BrowserGym route captures of the 2026-10-29 batch

Outputs
  /tmp/amt-syn/bw-path/analysis/task_kind.csv     one row per task x kind (primary path: Gemini 3.1 Pro)
  /tmp/amt-syn/bw-path/analysis/runs.csv          one row per clean run (all models) with validity and success
  /tmp/amt-syn/bw-path/analysis/actions.csv       one row per replayed acted-on control (static vs replay class)
  /tmp/amt-syn/bw-path/analysis/summary.json      everything the record reports, also copied to
                                                  docs/feasibility/2026-10-30-on-path-dose.json

Run: python3 on_path_dose.py   (standard library only; reads the paths above)

Definitions are in the docstrings of the functions below and in the record
docs/feasibility/2026-10-30-on-path-dose.md.
"""
import csv
import glob
import json
import os
import re
import statistics
from collections import Counter, defaultdict

HF = os.path.expanduser('~/.hf-stage-bw')
REPLAY = '/tmp/amt-syn/bw-path'
ROUTES = '/tmp/amt-syn/bw-variants'
OUT = f'{REPLAY}/analysis'
DOC_JSON = os.path.expanduser('~/.workspace/ai-agent-accessibility/docs/feasibility/2026-10-30-on-path-dose.json')
ENVS = {'amazon': 'amazon', 'booking': 'booking', 'gmail': 'gmail', 'lms': 'lms', 'pp': 'patient_portal',
        'reddit': 'reddit', 'rh': 'robinhood'}
KINDS = ['names', 'labels', 'headings', 'landmarks', 'tableheads', 'alt']
# browser-use models with a full 519-task clean sweep (the headroom panel)
PANEL = ['gemini_3_1_pro', 'gemini_3_flash', 'gpt_5_4', 'gpt_5_4_mini', 'opus_4_7', 'sonnet_46']
# tasks with a 'hardened (v2)' solvability test in the public release (breakingweb/tests/test_*_upgrade.py):
# the published runs predate the hardening, so their outcomes are for an older task version
HARDENED = {os.path.basename(f)[5:-11] for f in glob.glob('/tmp/amt-syn/bw-clean/breakingweb/tests/test_*_upgrade.py')}
STOP = set('a an the to of for in on this that and or as with at by is it your my from into'.split())

SEL_RE = {  # a find_elements CSS selector that names the kind (it would match fewer or no nodes in the variant)
    'headings': re.compile(r'(?<![\w\-.#])h[1-6](?![\w\-])|role=["\']?heading'),
    'landmarks': re.compile(r'(?<![\w\-.#])(header|nav|main|footer|aside)(?![\w\-])|role=["\']?(banner|navigation|main|contentinfo|complementary|search|region)'),
    'tableheads': re.compile(r'(?<![\w\-.#])th(?![\w\-])'),
    'alt': re.compile(r'\[alt'),
    'names': re.compile(r'(?<![\w\-])(a|button|\*)?\[aria-label'),
    'labels': re.compile(r'label\[for|(?<![\w\-.#])label(?![\w\-])|(input|textarea|select)\[aria-label'),
}


def toks(s):
    return {t for t in re.findall(r'[a-z0-9]+', (s or '').lower()) if t not in STOP}


def loss_class(clean, post, had_source):
    """Class of a name change when one source is removed.

    no_source: the element has no attribute of this kind (nothing to remove);
    empty: the name becomes empty; lost: a content word of the clean name is missing from the
    new name; changed: the string changes but every content word survives; kept: unchanged."""
    if not had_source:
        return 'no_source'
    post = (post or '').strip()
    if not post:
        return 'empty'
    if toks(clean) - toks(post):
        return 'lost'
    if re.sub(r'\s+', ' ', (clean or '').strip().lower()) != re.sub(r'\s+', ' ', post.lower()):
        return 'changed'
    return 'kept'


def ladder(clean, post, had_source, peers):
    """loss_class plus 'ambiguous': the new name is non-empty but now shared with another visible
    control of the same kind while the clean name was unique (path_replay.py `peers`)."""
    c = loss_class(clean, post, had_source)
    if c in ('no_source', 'empty') or not peers:
        return c
    if (peers.get('same_post') or 0) > 0 and (peers.get('same_clean') or 0) == 0:
        return 'ambiguous'
    return c


def path_fidelity(rec, traj_steps):
    """Share of steps whose replayed URL path equals the recorded one, and share of acted-on
    targets that were located."""
    rec_paths = {s.get('step'): s.get('replay_path') for s in traj_steps}
    st = [x for x in rec.get('states', []) if x.get('step') != 'end']
    same = sum(1 for x in st if rec_paths.get(x['step']) == x['path'])
    acted = [a for a in rec.get('actions', []) if a['action'] in ('click', 'fill', 'select', 'dropdown_options')]
    loc = sum(1 for a in acted if a.get('el'))
    return (same / len(st) if st else None), (loc / len(acted) if acted else 1.0)


def parse_ec(ec):
    ec = ec or ''
    m = re.match(r'^Clicked (\w+)', ec)
    tag = m.group(1) if m else None
    q = re.search(r'"(.*)"(?: aria-label=.*)?$', ec, re.S)
    vis = q.group(1) if q else ''
    trunc = vis.endswith('...')
    if trunc:
        vis = vis[:-3]
    return tag, re.sub(r'\s+', ' ', vis).strip(), trunc


# ---------------------------------------------------------------- runs

def run_dirs():
    """(model, source, config, glob) for every clean-run directory."""
    out = []
    for m in ['gemini_3_1_pro', 'gemini_3_flash', 'gpt_5_4', 'gpt_5_4_mini', 'opus_4_7', 'qwen3_vl_235b']:
        out.append((m, 'v2', 'bu_40steps_600s', f'{HF}/{m}/tasks/*__clean/trajectory.json'))
    out.append(('sonnet_46', 'v3', 'bu_unverified', f'{HF}/v3/sonnet_46/tasks/*__clean/trajectory.json'))
    out.append(('opus_4_7', 'v3_retry', 'bu_60steps_1200s', f'{HF}/v3/opus_47_retry/tasks/*__clean/trajectory.json'))
    out.append(('opus_4_7', 'v3_credfix', 'bu_60steps_1200s', f'{HF}/v3/opus_47_retry/credfix_retry/tasks/*__clean/trajectory.json'))
    for m in ['pixel_gemini_31_pro', 'pixel_gpt_54', 'pixel_opus_47']:
        out.append((m, 'v3', 'pixel_60steps_1200s', f'{HF}/v3/{m}/**/tasks/*__clean/trajectory.json'))
    return out


def load_runs():
    runs = []
    for model, source, config, pat in run_dirs():
        for f in sorted(glob.glob(pat, recursive=True)):
            d = json.load(open(f))
            a = d.get('agent') or {}
            tr = a.get('trajectory') or []
            ev = d.get('evaluation') or {}
            err = a.get('error')
            valid = bool(tr) and not err
            runs.append({'task': d['task_id'], 'env': d['task_id'].split('_')[0], 'model': model, 'source': source,
                         'config': config, 'harness': 'pixel' if model.startswith('pixel') else 'browser-use',
                         'success': bool(ev.get('success')), 'valid': valid, 'n_steps': len(tr),
                         'completed': a.get('completed'), 'elapsed': a.get('elapsed_seconds'),
                         'hit_wall': (a.get('elapsed_seconds') or 0) >= 590 and not a.get('completed'),
                         'path': f, 'traj': tr if model in PANEL or model == 'qwen3_vl_235b' else None})
    return runs


# ---------------------------------------------------------------- static exposure from a trajectory

def static_exposure(tr):
    """What the trajectory alone shows (no replay): acted-on buttons/links with an aria-label and how
    their name would change if it were removed (compared with the visible text in extracted_content),
    and find_elements selectors / extract actions that name a kind. Also the visited URL paths."""
    names = Counter(); name_items = []
    sel_hits = Counter(); extract_n = 0; paths = []
    for s in tr:
        for p in (s.get('replay_path'), s.get('result_path')):
            if p and (not paths or paths[-1] != p):
                paths.append(p)
        acts = s.get('actions') or []; tg = s.get('action_targets') or []; rs = s.get('action_results') or []
        for j, a in enumerate(acts):
            t = tg[j] if j < len(tg) else {}
            r = rs[j] if j < len(rs) else {}
            ec = (r or {}).get('extracted_content') or ''
            if a.get('action') == 'click':
                tag, vis, trunc = parse_ec(ec)
                if tag in ('button', 'a'):
                    aria = (t or {}).get('name') or ''
                    c = loss_class(aria, vis, bool(aria))
                    if c == 'lost' and trunc:
                        c = 'lost_or_truncated'
                    names[c] += 1
                    if aria:
                        name_items.append((aria, vis, c))
        for ra in s.get('raw_actions') or []:
            if 'find_elements' in ra and isinstance(ra['find_elements'], dict):
                sel = ra['find_elements'].get('selector') or ''
                for k, rx in SEL_RE.items():
                    if rx.search(sel):
                        sel_hits[k] += 1
            if 'extract' in ra:
                extract_n += 1
    return {'names': names, 'name_items': name_items, 'sel_hits': sel_hits, 'extract_n': extract_n, 'paths': paths}


# ---------------------------------------------------------------- route inference

def route_table():
    """BrowserGym route captures of the clean build: per env, page key -> counts of AX lines per kind."""
    tab = {}
    for envkey, envname in ENVS.items():
        d = f'{ROUTES}/{envname}/clean'
        pages = {}
        for f in glob.glob(f'{d}/*.all.txt'):
            key = os.path.basename(f)[:-8]
            txt = open(f).read()
            pages[key] = {
                'headings': len(re.findall(r"\] heading '", txt)),
                'landmarks': len(re.findall(r"\] (banner|navigation|main|contentinfo|complementary|search|region) ", txt)),
                'tableheads': len(re.findall(r"\] (columnheader|rowheader) ", txt)),
                'alt': len(re.findall(r"\] (img|image) '[^']+'", txt)),
            }
        tab[envkey] = pages
    return tab


def route_key(envkey, path, pages):
    p = (path or '/').strip('/')
    if not p:
        starts = sorted(k for k in pages if not k.startswith('route__'))
        return (starts[0], 'start') if starts else (None, 'unmatched')
    k = 'route__' + p.replace('/', '_')
    if k in pages:
        return k, 'static_route'
    first = p.split('/')[0]
    cand = sorted(x for x in pages if x.startswith('route__' + first))
    if cand and '/' in p:
        return cand[0], 'param_route_example'
    if cand and first in ('search',):
        return cand[0], 'static_route'
    return None, 'unmatched'


# ---------------------------------------------------------------- replay exposure

def replay_exposure(rec):
    """Exact exposure from one replay record (path_replay.py)."""
    out = {'located': 0, 'acted': 0, 'names': Counter(), 'labels_ax': Counter(), 'labels_bu': Counter(),
           'name_n': Counter(), 'label_n': Counter(), 'targets_in_landmark': 0, 'targets_after_heading': 0,
           'targets_in_table': 0, 'target_n': 0, 'items': []}
    for a in rec.get('actions', []):
        if a['action'] not in ('click', 'fill', 'select', 'dropdown_options'):
            continue
        out['acted'] += 1
        el = a.get('el'); ax = a.get('ax')
        if not el or not ax:
            continue
        out['located'] += 1
        out['target_n'] += 1
        out['targets_in_landmark'] += el.get('landmark') is not None
        out['targets_after_heading'] += el.get('prev_heading') is not None
        out['targets_in_table'] += bool(el.get('in_table'))
        tag = el['tag']
        has_aria = bool((el.get('aria_label') or '').strip() or el.get('aria_labelledby'))
        if tag in ('button', 'a'):
            c = ladder(ax.get('clean'), ax.get('no_aria'), has_aria, a.get('peers'))
            out['names'][c] += 1
            out['items'].append(('names', el.get('aria_label'), ax.get('clean'), ax.get('no_aria'), c, a.get('ec', '')[:120]))
        elif tag in ('input', 'textarea', 'select') and (el.get('type') or '').lower() not in ('hidden', 'submit', 'button'):
            has_for = bool(el.get('label_for'))
            c = ladder(ax.get('clean'), ax.get('no_aria_no_for'), has_aria or has_for, a.get('peers'))
            out['labels_ax'][c] += 1
            # browser-use shows aria-label as an attribute; label[for] text stays on the page as plain text
            if has_aria:
                keep = ' '.join([el.get('placeholder') or '', ' '.join(el.get('label_for') or []), el.get('label_wrap') or '', el.get('title') or ''])
                cb = loss_class(el.get('aria_label') or '', keep, True)
            else:
                cb = 'no_source'
            out['labels_bu'][cb] += 1
            src = 'aria' if has_aria else ('for' if has_for else ('wrap' if el.get('label_wrap') else ('placeholder' if el.get('placeholder') else 'none')))
            out['items'].append(('labels', src, ax.get('clean'), ax.get('no_aria_no_for'), c, a.get('ec', '')[:120]))
    st = rec.get('states', [])
    def mx(k, part):
        return max([s[k][part] for s in st if k in s] or [0])
    heads = set()
    for s in st:
        heads.update(h for h in s.get('heading_text', []) if h)
    axr = lambda r: max([(s.get('ax_roles') or {}).get(r, 0) for s in st] or [0])
    out['page'] = {
        'headings': {'doc': mx('headings', 'doc'), 'vp': mx('headings', 'vp'), 'distinct': len(heads),
                     'ax': axr('heading')},
        'landmarks': {'doc': mx('landmarks', 'doc'), 'vp': mx('landmarks', 'vp'),
                      'ax': max([sum((s.get('ax_roles') or {}).get(r, 0) for r in ('banner', 'navigation', 'main', 'contentinfo', 'complementary', 'search', 'region')) for s in st] or [0])},
        'tableheads': {'doc': mx('th', 'doc'), 'vp': mx('th', 'vp'), 'ax': max([(s.get('ax_roles') or {}).get('columnheader', 0) + (s.get('ax_roles') or {}).get('rowheader', 0) for s in st] or [0]),
                       'states_with': sum(1 for s in st if s.get('th', {}).get('doc', 0) > 0)},
        'alt': {'doc': mx('img_alt', 'doc'), 'vp': mx('img_alt', 'vp'), 'in_control': mx('img_alt_in_control', 'doc'),
                'sole_name': mx('img_alt_sole_name', 'doc'), 'ax': axr('img_named')},
    }
    out['paths'] = []
    for s in st:
        if not out['paths'] or out['paths'][-1] != s['path']:
            out['paths'].append(s['path'])
    out['n_states'] = len(st)
    return out


def load_replays(model):
    recs = {}
    for f in glob.glob(f'{REPLAY}/{model}/*.json'):
        r = json.load(open(f))
        recs[r['task_id']] = r
    return recs


# ---------------------------------------------------------------- per task x kind

def onpath_flags(rx):
    """Primary binary per kind from one replay. See the record for the reasoning."""
    n = rx['names']; la = rx['labels_ax']; p = rx['page']
    return {
        'names': (n['empty'] + n['ambiguous'] + n['lost']) > 0,
        'labels': (la['empty'] + la['ambiguous'] + la['lost']) > 0,
        'headings': p['headings']['doc'] > 0,
        'landmarks': p['landmarks']['doc'] > 0,
        'tableheads': p['tableheads']['doc'] > 0,
        'alt': p['alt']['doc'] > 0,
    }


def strict_flags(rx):
    """Stricter binary: names/labels empty or ambiguous only; page kinds in the viewport of a visited state
    (BrowserGym serialises only visible nodes); alt only where it is the sole name of a control."""
    n = rx['names']; la = rx['labels_ax']; p = rx['page']
    return {'names': (n['empty'] + n['ambiguous']) > 0, 'labels': (la['empty'] + la['ambiguous']) > 0, 'headings': p['headings']['vp'] > 0,
            'landmarks': p['landmarks']['vp'] > 0, 'tableheads': p['tableheads']['vp'] > 0,
            'alt': p['alt']['sole_name'] > 0}


def counts(rx):
    n = rx['names']; la = rx['labels_ax']; p = rx['page']
    return {'names': n['empty'] + n['ambiguous'] + n['lost'], 'labels': la['empty'] + la['ambiguous'] + la['lost'],
            'headings': p['headings']['doc'], 'landmarks': p['landmarks']['doc'],
            'tableheads': p['tableheads']['doc'], 'alt': p['alt']['doc']}


def q(vals):
    vals = sorted(vals)
    if not vals:
        return None
    def pct(x):
        k = (len(vals) - 1) * x; f = int(k); c = min(f + 1, len(vals) - 1)
        return round(vals[f] + (vals[c] - vals[f]) * (k - f), 2)
    return {'n': len(vals), 'median': pct(0.5), 'p25': pct(0.25), 'p75': pct(0.75), 'max': vals[-1],
            'share_gt0': round(sum(1 for v in vals if v > 0) / len(vals), 3)}


def main():
    os.makedirs(OUT, exist_ok=True)
    runs = load_runs()
    tasks = sorted({r['task'] for r in runs if r['model'] == 'gemini_3_1_pro'})
    S = {'n_tasks': len(tasks)}

    # ---- runs and headroom
    by_task = defaultdict(list)
    for r in runs:
        by_task[r['task']].append(r)
    with open(f'{OUT}/runs.csv', 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['task', 'env', 'model', 'source', 'config', 'harness', 'valid', 'success', 'n_steps', 'completed', 'hit_wall'])
        for r in runs:
            w.writerow([r['task'], r['env'], r['model'], r['source'], r['config'], r['harness'], r['valid'], r['success'], r['n_steps'], r['completed'], r['hit_wall']])
    run_counts = Counter((r['model'], r['source'], r['valid']) for r in runs)
    S['runs'] = [{'model': m, 'source': s, 'valid': v, 'n': n} for (m, s, v), n in sorted(run_counts.items())]
    S['runs_success'] = {f'{m}/{s}': {'valid': sum(1 for r in runs if r['model'] == m and r['source'] == s and r['valid']),
                                       'success': sum(1 for r in runs if r['model'] == m and r['source'] == s and r['valid'] and r['success']),
                                       'hit_wall': sum(1 for r in runs if r['model'] == m and r['source'] == s and r['hit_wall'])}
                         for (m, s) in sorted({(r['model'], r['source']) for r in runs})}
    head = {}
    for t in tasks:
        rs = [r for r in by_task[t] if r['valid']]
        bu = [r for r in rs if r['harness'] == 'browser-use']
        px = [r for r in rs if r['harness'] == 'pixel']
        panel = {}
        for m in PANEL:
            mine = [r for r in bu if r['model'] == m and r['source'] in ('v2', 'v3')]
            panel[m] = mine[0]['success'] if mine else None
        head[t] = {'env': t.split('_')[0], 'n_runs_all': len(rs), 'n_runs_bu': len(bu), 'n_runs_pixel': len(px),
                   'bu_success': sum(r['success'] for r in bu), 'pixel_success': sum(r['success'] for r in px),
                   'panel': panel, 'panel_k': sum(1 for v in panel.values() if v), 'panel_n': sum(1 for v in panel.values() if v is not None),
                   'gemini': panel['gemini_3_1_pro']}
        head[t]['bu_rate'] = round(head[t]['bu_success'] / len(bu), 3) if bu else None
    S['headroom'] = {
        'runs_per_task_all': q([h['n_runs_all'] for h in head.values()]),
        'runs_per_task_bu': q([h['n_runs_bu'] for h in head.values()]),
        'runs_per_task_pixel': q([h['n_runs_pixel'] for h in head.values()]),
        'panel_k_hist': dict(sorted(Counter(h['panel_k'] for h in head.values()).items())),
        'panel_k_hist_gemini_solved': dict(sorted(Counter(h['panel_k'] for h in head.values() if h['gemini']).items())),
        'per_env': {e: {'n': sum(1 for h in head.values() if h['env'] == e),
                        'gemini_solved': sum(1 for h in head.values() if h['env'] == e and h['gemini']),
                        'mean_panel_rate': round(statistics.mean(h['panel_k'] / h['panel_n'] for h in head.values() if h['env'] == e and h['panel_n']), 3),
                        'gemini_solved_panel_ge4': sum(1 for h in head.values() if h['env'] == e and h['gemini'] and h['panel_k'] >= 4)}
                    for e in ENVS},
        'pixel_tasks_with_runs': sum(1 for h in head.values() if h['n_runs_pixel']),
    }

    # ---- static exposure for every browser-use run of the panel (and route inference)
    rt = route_table()
    static = {}
    for r in runs:
        if r['traj'] is None or not r['valid']:
            continue
        static[(r['task'], r['model'], r['source'])] = static_exposure(r['traj'])

    # ---- replays
    replay_models = [m for m in PANEL if os.path.isdir(f'{REPLAY}/{m}')]
    reps = {m: load_replays(m) for m in replay_models}
    fidelity = {}
    for m, recs in reps.items():
        ok = [r for r in recs.values() if (r.get('replay_eval') or {}).get('success')]
        acted = sum(1 for r in recs.values() for a in r['actions'] if a['action'] in ('click', 'fill', 'select', 'dropdown_options'))
        loc = sum(1 for r in recs.values() for a in r['actions'] if a['action'] in ('click', 'fill', 'select', 'dropdown_options') and a.get('el'))
        amb = sum(1 for r in recs.values() for a in r['actions'] if (a.get('locate') or {}).get('how') == 'ambiguous')
        fidelity[m] = {'replayed': len(recs), 'replay_success': len(ok), 'fatal': sum(1 for r in recs.values() if r.get('fatal')),
                       'acted': acted, 'located': loc, 'ambiguous': amb,
                       'located_share': round(loc / acted, 3) if acted else None}
    S['replay_fidelity'] = fidelity

    # replay exposures
    rx = {m: {t: replay_exposure(r) for t, r in recs.items()} for m, recs in reps.items()}
    good = {m: {t for t, r in recs.items() if (r.get('replay_eval') or {}).get('success')} for m, recs in reps.items()}
    # measured: the replay followed the recorded path (>= 90% of steps on the recorded URL path and
    # >= 90% of acted-on targets located) or reached a passing end state
    traj_of = {(r['task'], r['model']): r['traj'] for r in runs if r['traj'] is not None and r['source'] in ('v2', 'v3')}
    measured, pf = {}, {}
    for m, recs in reps.items():
        measured[m] = set()
        for t, r in recs.items():
            sp, lp = path_fidelity(r, traj_of.get((t, m)) or [])
            pf[(m, t)] = (sp, lp)
            if t in good[m] or ((sp or 0) >= 0.9 and lp >= 0.9):
                measured[m].add(t)
    for m in reps:
        fidelity[m]['measured'] = len(measured[m])
        sps = [pf[(m, t)][0] for t in reps[m] if pf[(m, t)][0] is not None]
        fidelity[m]['step_path_agreement'] = q([round(x, 3) for x in sps])
        fidelity[m]['replay_success_hardened'] = sum(1 for t in good[m] if t in HARDENED)
        fidelity[m]['replayed_hardened'] = sum(1 for t in reps[m] if t in HARDENED)

    # ---- static vs replay agreement (names), Gemini
    agree = Counter()
    act_rows = []
    for m in replay_models:
        for t, r in reps[m].items():
            st_items = static.get((t, m, 'v2')) or static.get((t, m, 'v3'))
            for a in r['actions']:
                el, ax = a.get('el'), a.get('ax')
                if a['action'] != 'click' or not el or not ax or el['tag'] not in ('button', 'a'):
                    continue
                tag, vis, trunc = parse_ec(a.get('ec'))
                aria = (a.get('target') or {}).get('name') or ''
                sc = loss_class(aria, vis, bool(aria))
                if sc == 'lost' and trunc:
                    sc = 'lost_or_truncated'
                has_aria = bool((el.get('aria_label') or '').strip() or el.get('aria_labelledby'))
                rc = loss_class(ax.get('clean'), ax.get('no_aria'), has_aria)
                if m == 'gemini_3_1_pro':
                    agree[(sc, rc)] += 1
                act_rows.append([m, t, a['step'], el['tag'], aria, vis, sc, ax.get('clean'), ax.get('no_aria'), rc])
    for m in replay_models:
        for t, r in reps[m].items():
            for a in r['actions']:
                el, ax = a.get('el'), a.get('ax')
                if not el or not ax or el['tag'] not in ('input', 'textarea', 'select'):
                    continue
                has_aria = bool((el.get('aria_label') or '').strip() or el.get('aria_labelledby'))
                has_for = bool(el.get('label_for'))
                rc = loss_class(ax.get('clean'), ax.get('no_aria_no_for'), has_aria or has_for)
                src = 'aria' if has_aria else ('for' if has_for else ('wrap' if el.get('label_wrap') else ('placeholder' if el.get('placeholder') else 'none')))
                act_rows.append([m, t, a['step'], el['tag'] + ':' + (el.get('type') or ''), el.get('aria_label') or '', src, '', ax.get('clean'), ax.get('no_aria_no_for'), rc])
    with open(f'{OUT}/actions.csv', 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['model', 'task', 'step', 'tag', 'aria_label_or_name', 'visible_text_or_label_source', 'static_class', 'ax_clean', 'ax_after', 'replay_class'])
        w.writerows(act_rows)
    S['names_static_vs_replay_gemini'] = {f'{a}|{b}': n for (a, b), n in sorted(agree.items())}

    # action-level class totals (replay, per model, per env)
    cls = {}
    for m in replay_models:
        for kind, key in (('names', 'names'), ('labels_ax', 'labels_ax'), ('labels_bu', 'labels_bu')):
            tot = Counter()
            per_env = defaultdict(Counter)
            for t, x in rx[m].items():
                tot.update(x[key]); per_env[t.split('_')[0]].update(x[key])
            cls[f'{m}/{kind}'] = {'all': dict(tot), 'per_env': {e: dict(c) for e, c in per_env.items()}}
    S['action_classes'] = cls

    # labels: name sources of acted-on controls (Gemini)
    srcs = Counter(); srcs_env = defaultdict(Counter)
    for t, r in reps.get('gemini_3_1_pro', {}).items():
        for a in r['actions']:
            el = a.get('el')
            if not el or el['tag'] not in ('input', 'textarea', 'select') or (el.get('type') or '') in ('hidden', 'submit', 'button'):
                continue
            has_aria = bool((el.get('aria_label') or '').strip() or el.get('aria_labelledby'))
            s = '+'.join([x for x, c in (('aria', has_aria), ('for', bool(el.get('label_for'))), ('wrap', bool(el.get('label_wrap'))), ('placeholder', bool(el.get('placeholder')))) if c]) or 'none'
            srcs[s] += 1; srcs_env[t.split('_')[0]][s] += 1
    S['label_sources_gemini'] = {'all': dict(srcs.most_common()), 'per_env': {e: dict(c.most_common()) for e, c in srcs_env.items()}}

    # ---- route inference vs replay (page kinds), Gemini
    route_cmp = Counter(); coverage = Counter()
    route_flag = {}
    for t in tasks:
        st = static.get((t, 'gemini_3_1_pro', 'v2'))
        if not st:
            continue
        env = t.split('_')[0]
        keys = []
        for p in st['paths']:
            k, how = route_key(env, p, rt[env])
            coverage[how] += 1
            if k:
                keys.append(k)
        flags = {}
        for kind in ('headings', 'landmarks', 'tableheads', 'alt'):
            flags[kind] = any(rt[env][k][kind] > 0 for k in keys) if keys else None
        route_flag[t] = flags
        x = rx.get('gemini_3_1_pro', {}).get(t)
        if x and t in measured.get('gemini_3_1_pro', set()):
            for kind in ('headings', 'landmarks', 'tableheads', 'alt'):
                # compare with AX-role presence in the replay (same unit as the route capture)
                truth = x['page'][kind]['ax'] > 0
                route_cmp[(kind, str(flags[kind]), str(truth))] += 1
    S['route_inference'] = {'path_match': dict(coverage),
                            'vs_replay_ax': {f'{k}|route={a}|replay={b}': n for (k, a, b), n in sorted(route_cmp.items())}}

    # ---- per task x kind table (primary: Gemini replay; static fallback)
    rows = []
    tk = {}
    for t in tasks:
        h = head[t]
        x = rx.get('gemini_3_1_pro', {}).get(t)
        rep_ok = t in good.get('gemini_3_1_pro', set())
        meas = t in measured.get('gemini_3_1_pro', set())
        st = static.get((t, 'gemini_3_1_pro', 'v2'))
        # agreement across other models' successful replays
        others = [rx[m][t] for m in replay_models if m != 'gemini_3_1_pro' and t in measured.get(m, set())]
        for kind in KINDS:
            row = {'task': t, 'env': h['env'], 'kind': kind, 'gemini_success': h['gemini'], 'panel_k': h['panel_k'],
                   'panel_n': h['panel_n'], 'n_runs_bu': h['n_runs_bu'], 'bu_success': h['bu_success'],
                   'replay_ok': rep_ok, 'measured': meas, 'hardened': t in HARDENED}
            if x is not None and meas:
                row['count'] = counts(x)[kind]
                row['on_path'] = onpath_flags(x)[kind]
                row['on_path_strict'] = strict_flags(x)[kind]
                row['source'] = 'replay'
            elif st is not None and kind == 'names':
                n = st['names']
                row['count'] = n['empty'] + n['lost'] + n['lost_or_truncated']
                row['on_path'] = row['count'] > 0
                row['on_path_strict'] = n['empty'] > 0
                row['source'] = 'static'
            elif st is not None and kind in route_flag.get(t, {}) and route_flag[t][kind] is not None:
                row['count'] = None
                row['on_path'] = route_flag[t][kind]
                row['on_path_strict'] = None
                row['source'] = 'route'
            else:
                row['count'] = None; row['on_path'] = None; row['on_path_strict'] = None; row['source'] = 'none'
            if st is not None:
                row['bu_query'] = st['sel_hits'].get(kind, 0)
                row['bu_extract'] = st['extract_n']
            ofl = [onpath_flags(o)[kind] for o in others]
            row['other_models_n'] = len(ofl)
            row['other_models_on'] = sum(ofl)
            row['other_models_on_strict'] = sum(strict_flags(o)[kind] for o in others)
            rows.append(row)
            tk[(t, kind)] = row
    cols = ['task', 'env', 'kind', 'gemini_success', 'replay_ok', 'measured', 'hardened', 'source', 'count', 'on_path', 'on_path_strict',
            'other_models_n', 'other_models_on', 'bu_query', 'bu_extract', 'panel_k', 'panel_n', 'n_runs_bu', 'bu_success']
    with open(f'{OUT}/task_kind.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)

    # ---- distributions per env x kind (replayed, replay-successful Gemini paths)
    dist = {}
    for kind in KINDS:
        dist[kind] = {}
        for e in list(ENVS) + ['all']:
            sel = [r for r in rows if r['kind'] == kind and r['source'] == 'replay' and r['measured'] and (e == 'all' or r['env'] == e)]
            dist[kind][e] = {'count': q([r['count'] for r in sel]),
                             'on_path': sum(1 for r in sel if r['on_path']),
                             'on_path_strict': sum(1 for r in sel if r['on_path_strict']),
                             'n': len(sel)}
    S['distribution_gemini_replay'] = dist
    # page-kind extra detail: viewport, AX, target region
    extra = defaultdict(list)
    for t, x in rx.get('gemini_3_1_pro', {}).items():
        if t not in measured['gemini_3_1_pro']:
            continue
        e = t.split('_')[0]
        extra[('target_in_landmark', e)].append(x['targets_in_landmark'] / x['target_n'] if x['target_n'] else 0)
        extra[('target_after_heading', e)].append(x['targets_after_heading'] / x['target_n'] if x['target_n'] else 0)
        extra[('target_in_table', e)].append(x['targets_in_table'] / x['target_n'] if x['target_n'] else 0)
        extra[('th_states_share', e)].append(x['page']['tableheads']['states_with'] / x['n_states'] if x['n_states'] else 0)
        extra[('alt_sole_name', e)].append(x['page']['alt']['sole_name'])
        extra[('alt_in_control', e)].append(x['page']['alt']['in_control'])
        extra[('headings_distinct', e)].append(x['page']['headings']['distinct'])
        extra[('headings_vp', e)].append(x['page']['headings']['vp'])
        extra[('tableheads_vp', e)].append(x['page']['tableheads']['vp'])
    S['page_detail_gemini_replay'] = {f'{k}/{e}': q(v) for (k, e), v in sorted(extra.items())}

    # ---- agreement of on-path flags across models (successful replays of the same task)
    agr = {}
    for kind in KINDS:
        both = Counter()
        for t in tasks:
            if t not in measured.get('gemini_3_1_pro', set()):
                continue
            g = onpath_flags(rx['gemini_3_1_pro'][t])[kind]
            for m in replay_models:
                if m == 'gemini_3_1_pro' or t not in measured.get(m, set()):
                    continue
                o = onpath_flags(rx[m][t])[kind]
                both[(g, o)] += 1
        n = sum(both.values())
        kappa = None
        if n:
            po = (both[(True, True)] + both[(False, False)]) / n
            pg = (both[(True, True)] + both[(True, False)]) / n
            pot = (both[(True, True)] + both[(False, True)]) / n
            pe = pg * pot + (1 - pg) * (1 - pot)
            kappa = round((po - pe) / (1 - pe), 3) if pe < 1 else None
        agr[kind] = {'pairs': n, 'agree': round((both[(True, True)] + both[(False, False)]) / n, 3) if n else None, 'kappa': kappa,
                     'gemini_on_other_on': both[(True, True)], 'gemini_on_other_off': both[(True, False)],
                     'gemini_off_other_on': both[(False, True)], 'gemini_off_other_off': both[(False, False)]}
    S['cross_model_agreement'] = agr

    # ---- browser-use channel use (all panel runs, static): find_elements selectors naming a kind
    chan = {}
    for kind in KINDS:
        runs_with = Counter(); runs_tot = Counter()
        for (t, m, s), st in static.items():
            runs_tot[m] += 1
            runs_with[m] += st['sel_hits'].get(kind, 0) > 0
        chan[kind] = {m: {'runs': runs_tot[m], 'runs_with_query': runs_with[m]} for m in runs_tot}
    S['bu_selector_use'] = chan
    S['bu_extract_runs'] = {m: sum(1 for (t, mm, s), st in static.items() if mm == m and st['extract_n']) for m in {k[1] for k in static}}

    # ---- candidate pools per kind
    gem_steps = {r['task']: r['n_steps'] for r in runs if r['model'] == 'gemini_3_1_pro' and r['source'] == 'v2'}
    pools = {}
    for variant in ('primary', 'strict'):
        fk, ok_ = ('on_path', 'other_models_on') if variant == 'primary' else ('on_path_strict', 'other_models_on_strict')
        for kind in KINDS:
            cand = [r for r in rows if r['kind'] == kind and r['gemini_success'] and r['replay_ok'] and not r['hardened'] and r['source'] == 'replay']
            def tier(r):
                return 'A' if r['panel_k'] >= 4 else ('B' if r['panel_k'] >= 2 else 'C')
            def robust_on(r):
                return r[fk] and (r['other_models_n'] == 0 or r[ok_] / r['other_models_n'] >= 0.5)
            def robust_off(r):
                return (not r[fk]) and r[ok_] == 0
            on = [r for r in cand if robust_on(r)]
            off = [r for r in cand if robust_off(r)]
            def bal(rs):
                if not rs:
                    return None
                return {'n': len(rs), 'mean_gemini_steps': round(statistics.mean(gem_steps[r['task']] for r in rs), 1),
                        'mean_panel_k': round(statistics.mean(r['panel_k'] for r in rs), 2),
                        'env': dict(Counter(r['env'] for r in rs))}
            onA = [r for r in on if tier(r) == 'A']; offA = [r for r in off if tier(r) == 'A']
            pools[f'{variant}/{kind}'] = {
                'eligible': len(cand),
                'on': {t: sum(1 for r in on if tier(r) == t) for t in 'ABC'},
                'off': {t: sum(1 for r in off if tier(r) == t) for t in 'ABC'},
                'mixed': len(cand) - len(on) - len(off),
                'balance_on_tierA': bal(onA), 'balance_off_tierA': bal(offA),
                'envs_with_both_tierA': sorted(e for e in ENVS if any(r['env'] == e for r in onA) and any(r['env'] == e for r in offA)),
                'on_dose_tierA': q([r['count'] for r in onA if r['count'] is not None]),
                'on_tasks_tierA': sorted([(r['task'], r['count']) for r in onA], key=lambda x: (-(x[1] or 0), x[0])),
                'off_tasks_tierA': sorted(r['task'] for r in offA),
                'on_tasks_tierB': sorted(r['task'] for r in on if tier(r) == 'B'),
                'off_tasks_tierB': sorted(r['task'] for r in off if tier(r) == 'B'),
            }
    S['pools'] = pools
    # exposure ladder for element kinds among eligible tier-A tasks: none / weak (words lost, still
    # unique) / strong (empty or ambiguous), per env
    lad = {}
    for kind in ('names', 'labels'):
        c = defaultdict(Counter)
        for r in rows:
            if r['kind'] != kind or not (r['gemini_success'] and r['replay_ok'] and not r['hardened'] and r['source'] == 'replay') or r['panel_k'] < 4:
                continue
            lvl = 'strong' if r['on_path_strict'] else ('weak' if r['on_path'] else 'none')
            c[r['env']][lvl] += 1; c['all'][lvl] += 1
        lad[kind] = {e: dict(v) for e, v in c.items()}
    S['ladder_tierA'] = lad
    vc = f'{OUT}/variant_check.json'
    if os.path.exists(vc):
        S['variant_check'] = json.load(open(vc))
    # compact per-task table: headroom plus [count, on_path, on_path_strict, source] per kind
    S['tasks'] = {}
    for t in tasks:
        h = head[t]
        S['tasks'][t] = {'env': h['env'], 'gemini': h['gemini'], 'panel_k': h['panel_k'], 'panel_n': h['panel_n'],
                         'runs_bu': h['n_runs_bu'], 'succ_bu': h['bu_success'], 'runs_px': h['n_runs_pixel'],
                         'succ_px': h['pixel_success'], 'replay_ok': t in good.get('gemini_3_1_pro', set()),
                         'measured': t in measured.get('gemini_3_1_pro', set()), 'hardened': t in HARDENED,
                         'kinds': {k: [tk[(t, k)].get('count'), tk[(t, k)].get('on_path'), tk[(t, k)].get('on_path_strict'),
                                       tk[(t, k)].get('source'), tk[(t, k)].get('other_models_on'), tk[(t, k)].get('other_models_n')]
                                   for k in KINDS}}
    S['replay_failed_gemini_solved'] = sorted(t for t in tasks if head[t]['gemini'] and t in reps.get('gemini_3_1_pro', {}) and t not in good.get('gemini_3_1_pro', set()))
    json.dump(S, open(f'{OUT}/summary.json', 'w'), indent=1, default=str)
    json.dump(S, open(DOC_JSON, 'w'), separators=(',', ':'), default=str)
    print(json.dumps({k: S[k] for k in ('n_tasks', 'replay_fidelity')}, indent=1))


if __name__ == '__main__':
    main()
