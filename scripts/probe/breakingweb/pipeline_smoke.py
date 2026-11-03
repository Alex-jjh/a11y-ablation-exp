"""Engineering smoke test of the v2 pilot pipeline (H1, BrowserGym AXTree text harness). Not data.

One arm = one episode: restore the sources of a private BreakingWeb checkout, optionally apply one
codemod kind (env + shared sources), build the env, start the harness's own backend on 127.0.0.1,
run BreakingWeb's own `agent_eval.run_episode` with `agent.LLMAgent(provider='bedrock')`, then
restore the sources. Nothing in the checkout is edited except by the codemod, which is undone.

What it adds around the shipped harness (logging and checks only, the request fields are unchanged):
  - a pass-through proxy around the boto3 bedrock-runtime client of `LLMAgent`: per call it logs
    the request fields sent (modelId, inferenceConfig, additionalModelRequestFields if any,
    number of messages, characters), latency, stopReason, usage (input/output/cache tokens), the
    content block types returned and any exception; it marks a call as `agent` (system prompt
    present) or `summary` (the history-summary call of `trim_messages`).
  - a BreakingWebTask subclass whose setup installs the replay's isolation (page Date shim at
    2026-10-30T09:00Z, requests to hosts other than 127.0.0.1 aborted) before the task navigates,
    and after navigation fetches the served index.html and every JS/CSS asset it references and
    hashes them against the files in static/envs/<env>/ on disk (`served_check`).
  - a credential check: AWS_BEARER_TOKEN_BEDROCK and AWS_BEDROCK_API_KEY must be unset before and
    after the client is built; it records the boto3 credential *method* and the client region,
    never a credential value.
  - bundle hash of static/envs/<env> in two forms: `bundle` (path-free) and `bundle_fx6` (the
    replay record's formula with paths as in /tmp/amt-syn/bw-fx-src6/BreakingWeb, so it is
    comparable with /tmp/amt-syn/bw-replay/final/<env>/builds.json).

Inputs: TASK (BreakingWeb task id), ARM (`clean` or a codemod kind), OUT dir.
Env: BW_ROOT = private checkout (also on PYTHONPATH and the cwd: `python -m uvicorn` puts the cwd
first on sys.path), BW_PORT = backend port, AWS_PROFILE, AWS_BEDROCK_REGION; Node 24 + pnpm 10.15.0
on PATH; BREAKINGWEB_AUTO_BUILD_FRONTENDS=0.
Outputs: OUT/<TASK>__<ARM>/episode.json (run_episode result, per-call LLM log, per-step token
table, build, served check, credential check, git status after restore) and a printed summary.

`served TASK ARM OUT` (no LLM): builds ARM, starts the backend, loads /env/<env>/ in Chromium and
compares the loaded assets with disk; writes OUT/served_<TASK>__<ARM>.json; restores the sources.

Run (BreakingWeb venv python):
  cd $BW_ROOT && BW_ROOT=$PWD PYTHONPATH=$PWD BW_PORT=8391 AWS_PROFILE=codex-DO-NOT-DELETE \
    AWS_BEDROCK_REGION=us-west-2 python pipeline_smoke.py run TASK ARM OUT [--max-steps 15] \
    [--model us.anthropic.claude-opus-5-5]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import codemod  # noqa: E402
import variant_gate as vg  # noqa: E402  (restore, build; BW_ROOT read there)
from replay import DATE_SHIM  # noqa: E402

ROOT, PORT = vg.ROOT, vg.PORT
FX6 = '/tmp/amt-syn/bw-fx-src6/BreakingWeb'
BIND_DIFFS = {'breakingweb/app.py', 'scripts/_sweep_common.sh', 'scripts/breakingweb.sh', 'scripts/run_gmail_sweep.sh'}


def bundle_hashes(envname):
    h, h6 = hashlib.sha256(), hashlib.sha256()
    for p in sorted(glob.glob(f'{ROOT}/breakingweb/static/envs/{envname}/**', recursive=True)):
        if os.path.isfile(p):
            data = open(p, 'rb').read()
            rel = os.path.relpath(p, ROOT)
            h.update(rel.encode()); h.update(data)
            h6.update(f'{FX6}/{rel}'.encode()); h6.update(data)
    return h.hexdigest()[:16], h6.hexdigest()[:16]


def git_status():
    r = subprocess.run('git status --short', cwd=ROOT, shell=True, capture_output=True, text=True)
    return [ln[3:] for ln in r.stdout.splitlines()]


# ----------------------------------------------------------------------------- LLM logging proxy
class ConverseLog:
    def __init__(self, client):
        self._c = client
        self.calls = []

    def __getattr__(self, name):
        return getattr(self._c, name)

    def converse(self, **kw):
        msgs = kw.get('messages', [])
        rec = {'i': len(self.calls), 'kind': 'agent' if kw.get('system') else 'summary',
               'sent': {'modelId': kw.get('modelId'), 'inferenceConfig': kw.get('inferenceConfig'),
                        'additionalModelRequestFields': kw.get('additionalModelRequestFields'),
                        'n_messages': len(msgs),
                        'chars': sum(len(b.get('text', '')) for m in msgs for b in m['content'])
                        + sum(len(b.get('text', '')) for b in kw.get('system') or [])},
               't0': time.time()}
        try:
            r = self._c.converse(**kw)
        except Exception as e:
            rec.update(latency_s=round(time.time() - rec['t0'], 2), error=f'{type(e).__name__}: {str(e)[:400]}')
            self.calls.append(rec)
            raise
        blocks = r.get('output', {}).get('message', {}).get('content', [])
        rec.update(latency_s=round(time.time() - rec['t0'], 2), stopReason=r.get('stopReason'),
                   usage=r.get('usage'), block_types=[next(iter(b)) for b in blocks],
                   text_chars=sum(len(b.get('text', '')) for b in blocks if 'text' in b),
                   reasoning_chars=sum(len(str(b.get('reasoningContent', ''))) for b in blocks if 'reasoningContent' in b),
                   server_latency_ms=(r.get('metrics') or {}).get('latencyMs'))
        self.calls.append(rec)
        return r


# ----------------------------------------------------------------------------- isolated task
def make_task_class(served):
    from breakingweb.browsergym_task import BreakingWebTask

    class SmokeTask(BreakingWebTask):
        def setup(self, page):
            ctx = page.context
            ctx.add_init_script(DATE_SHIM)
            served['external_aborted'] = []

            def route(r):
                host = urllib.parse.urlparse(r.request.url).hostname
                if host in ('127.0.0.1', 'localhost') or r.request.url.startswith(('data:', 'blob:')):
                    r.continue_()
                else:
                    served['external_aborted'].append(r.request.url[:120]); r.abort()
            ctx.route('**/*', route)
            loaded = []
            page.on('response', lambda r: loaded.append(r) if re.search(r'/env/[^/]+/assets/', r.url) else None)
            out = super().setup(page)
            # Freshly installed init script applies from the first navigation, which setup performs.
            served['page_date_ms'] = page.evaluate('() => Date.now()')
            served['server_started_by_task'] = self._server_proc is not None
            served['start_url'] = page.url.split('?')[0]
            served.update(check_served(self._env_id, [(r.url, r.body()) for r in loaded]))
            return out

        def force_evaluate(self, page):
            res = super().force_evaluate(page)
            served['force_evaluate'] = res  # run_episode drops it unless its score beats the in-loop one
            return res

    return SmokeTask


def check_served(envname, bodies):
    """Compare the JS/CSS assets the browser loaded for the start page with the on-disk build."""
    disk = f'{ROOT}/breakingweb/static/envs/{envname}'
    res = {'served_assets': [], 'served_match': bool(bodies)}
    on_disk = sorted(os.path.basename(p) for p in glob.glob(f'{disk}/assets/*'))
    for url, body in bodies:
        name = os.path.basename(urllib.parse.urlparse(url).path)
        f = f'{disk}/assets/{name}'
        same = os.path.exists(f) and open(f, 'rb').read() == body
        res['served_assets'].append({'url': url.split('?')[0], 'sha': hashlib.sha256(body).hexdigest()[:16],
                                     'disk_match': same, 'n_aria_label': body.count(b'aria-label'),
                                     'n_htmlFor': body.count(b'htmlFor'),
                                     'has_recipient_aria': b'Recipient username' in body})
        res['served_match'] &= same
    res['disk_assets'] = on_disk
    res['all_disk_assets_loaded'] = sorted(a['url'].rsplit('/', 1)[-1] for a in res['served_assets']) == on_disk
    return res


# ----------------------------------------------------------------------------- run
def cmd_run(a):
    from breakingweb.tasks._registry import get_task
    envname = get_task(a.task).env_id
    odir = f'{a.out}/{a.task}__{a.arm}'
    os.makedirs(odir, exist_ok=True)
    rec = {'task': a.task, 'env': envname, 'arm': a.arm, 'model': a.model, 'max_steps': a.max_steps,
           'root': ROOT, 'port': PORT, 'breakingweb_module': None, 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    import breakingweb
    rec['breakingweb_module'] = os.path.dirname(breakingweb.__file__)
    assert rec['breakingweb_module'].startswith(ROOT), 'breakingweb imported from outside BW_ROOT'
    assert os.path.realpath(os.getcwd()) == os.path.realpath(ROOT), 'cwd must be BW_ROOT (python -m uvicorn)'

    vg.restore(envname)
    try:
        if a.arm != 'clean':
            rec['codemod'] = {'env': codemod.rewrite(f'{vg.ENVROOT}/{envname}/src', a.arm),
                              'shared': codemod.rewrite(f'{vg.ENVROOT}/shared/src', a.arm)}
        ok, blog = vg.build(envname)
        rec['build_ok'] = ok
        if not ok:
            rec['build_log_tail'] = blog[-1500:]
            raise SystemExit('build failed')
        rec['bundle'], rec['bundle_fx6'] = bundle_hashes(envname)
        rec['git_status_built'] = git_status()

        # credentials: no bearer token; record method + region only
        cred = {'bearer_env_before': 'AWS_BEARER_TOKEN_BEDROCK' in os.environ,
                'api_key_env_before': bool(os.environ.get('AWS_BEDROCK_API_KEY')),
                'AWS_PROFILE': os.environ.get('AWS_PROFILE'), 'AWS_BEDROCK_REGION': os.environ.get('AWS_BEDROCK_REGION')}
        assert not cred['bearer_env_before'] and not cred['api_key_env_before'], 'bearer token or API key set'
        from breakingweb.agent import LLMAgent
        agent = LLMAgent(model=a.model, provider='bedrock')
        c = agent.client
        cred.update(bearer_env_after='AWS_BEARER_TOKEN_BEDROCK' in os.environ, client_region=c.meta.region_name,
                    credential_method=getattr(c._request_signer._credentials, 'method', None),
                    signature_version=c.meta.config.signature_version)
        assert not cred['bearer_env_after']
        rec['credentials'] = cred
        log = ConverseLog(c)
        agent.client = log

        served = {}
        from browsergym.core.action.highlevel import HighLevelActionSet
        from browsergym.core.env import BrowserEnv
        aset = HighLevelActionSet(subsets=['bid', 'chat', 'infeas'], multiaction=False)
        env = BrowserEnv(task_entrypoint=make_task_class(served),
                         task_kwargs={'task_id': a.task, 'server_host': '127.0.0.1', 'server_port': PORT},
                         headless=True, action_mapping=aset.to_python_code)
        from breakingweb.agent_eval import run_episode
        t0 = time.time()
        try:
            ep = run_episode(env, agent, max_steps=a.max_steps, timeout_seconds=1800, verbose=True)
        finally:
            env.close()
        rec['wall_s'] = round(time.time() - t0, 1)
        rec['served'] = served
        rec['episode'] = ep
        rec['llm_calls'] = [{k: v for k, v in x.items() if k != 't0'} for x in log.calls]
        steps = []
        agent_calls = [x for x in log.calls if x['kind'] == 'agent']
        for i, st in enumerate(ep['trajectory']):
            cl = agent_calls[i] if i < len(agent_calls) else {}
            u = cl.get('usage') or {}
            steps.append({'step': st['step'], 'action': st['raw_action'], 'status': st['status'],
                          'error': (st.get('last_action_error') or '')[:160], 'targets': st.get('targets'),
                          'in': u.get('inputTokens'), 'out': u.get('outputTokens'),
                          'cache_read': u.get('cacheReadInputTokens'), 'cache_write': u.get('cacheWriteInputTokens'),
                          'stop': cl.get('stopReason'), 'latency_s': cl.get('latency_s'),
                          'blocks': cl.get('block_types'), 'sent_chars': (cl.get('sent') or {}).get('chars')})
        rec['steps'] = steps
    finally:
        vg.restore(envname)
        ok2, _ = vg.build(envname)
        rec['restored_rebuild_ok'] = ok2
        rec['bundle_after_restore'], rec['bundle_after_restore_fx6'] = bundle_hashes(envname)
        rec['git_status_after_restore'] = git_status()
        rec['only_bind_diffs_after'] = set(rec['git_status_after_restore']) <= BIND_DIFFS
        json.dump(rec, open(f'{odir}/episode.json', 'w'), indent=1, default=str)
    ev = rec['episode']['evaluation']
    tin = sum((x.get('usage') or {}).get('inputTokens', 0) for x in rec['llm_calls'])
    tout = sum((x.get('usage') or {}).get('outputTokens', 0) for x in rec['llm_calls'])
    print(json.dumps({'arm': a.arm, 'steps': rec['episode']['steps'], 'completed': rec['episode']['completed'],
                      'success': ev.get('success'), 'score': ev.get('score'), 'calls': len(rec['llm_calls']),
                      'in': tin, 'out': tout, 'bundle_fx6': rec['bundle_fx6'], 'served_match': served.get('served_match'),
                      'restored': rec['only_bind_diffs_after'], 'cred_method': rec['credentials']['credential_method']}))


def cmd_served(a):
    """No LLM: build ARM, start the backend, load the env root page, compare loaded assets with disk, restore."""
    from breakingweb.runner import start_server, wait_for_server
    from playwright.sync_api import sync_playwright
    from breakingweb.tasks._registry import get_task
    envname = get_task(a.task).env_id
    rec = {'arm': a.arm, 'env': envname}
    vg.restore(envname)
    try:
        if a.arm != 'clean':
            codemod.rewrite(f'{vg.ENVROOT}/{envname}/src', a.arm); codemod.rewrite(f'{vg.ENVROOT}/shared/src', a.arm)
        rec['build_ok'] = vg.build(envname)[0]
        rec['bundle'], rec['bundle_fx6'] = bundle_hashes(envname)
        proc = start_server('127.0.0.1', PORT)
        try:
            assert wait_for_server('127.0.0.1', PORT, timeout=90)
            with sync_playwright() as pw:
                b = pw.chromium.launch(); pg = b.new_page(); loaded = []
                pg.on('response', lambda r: loaded.append(r) if re.search(r'/env/[^/]+/assets/', r.url) else None)
                pg.goto(f'http://127.0.0.1:{PORT}/env/{envname}/smoke')  # bare /env/<env>/ redirects to /; pg.wait_for_load_state('networkidle')
                rec.update(check_served(envname, [(r.url, r.body()) for r in loaded])); b.close()
        finally:
            proc.terminate(); proc.wait(timeout=15)
    finally:
        vg.restore(envname); vg.build(envname)
        rec['git_status_after_restore'] = git_status()
        rec['only_bind_diffs_after'] = set(rec['git_status_after_restore']) <= BIND_DIFFS
    os.makedirs(a.out, exist_ok=True)
    json.dump(rec, open(f'{a.out}/served_{a.task}__{a.arm}.json', 'w'), indent=1)
    print(json.dumps({k: rec[k] for k in ('arm', 'bundle_fx6', 'served_match', 'all_disk_assets_loaded', 'only_bind_diffs_after')}))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    r = sp.add_parser('run')
    r.add_argument('task'); r.add_argument('arm'); r.add_argument('out')
    r.add_argument('--max-steps', type=int, default=15)
    r.add_argument('--model', default='us.anthropic.claude-opus-5-5')
    v = sp.add_parser('served')
    v.add_argument('task'); v.add_argument('arm'); v.add_argument('out')
    a = ap.parse_args()
    if a.cmd == 'served':
        cmd_served(a)
    if a.cmd == 'run':
        if a.arm not in ('clean', 'landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads'):
            raise SystemExit('arm must be clean or a codemod kind')
        cmd_run(a)


if __name__ == '__main__':
    main()
