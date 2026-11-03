#!/usr/bin/env python3
"""Offline test of h1_wrapper.py with a scripted fake model client. No LLM call.

Tests (each prints PASS/FAIL with the reason; exit 1 if any fails):
  T1 reference run   reddit_compose_message (replay reference set, outside the pilot pool) on the clean
                     build with an Anthropic-shaped fake that follows the recorded Gemini route by role+name
                     read from the observation text it receives (scrolls when the target is not in view).
                     Must: evaluator success, end_reason agent_finished, every step field present, reasoning
                     text stored with signature hashed, prompt hash recomputable from the trace alone, no
                     temperature sent, M1 pass, Date shim and remote-abort self-check pass, files read-only,
                     SHA256SUMS valid, run directory not reusable.
  T2 failed run      Same task, GPT-shaped fake (encrypted reasoning only) that only scrolls, step cap 12 from a
                     test budget file, history-trim threshold lowered to 6,000 estimated tokens so the
                     summary call runs. Must: end_reason step_cap, forced evaluation stored with its checks
                     (success false), summary calls logged with temperature_requested 0.0 and sent null,
                     reasoning visibility `encrypted`.
  T3 refusals        Manifest with one file hash changed; --expect-bundle wrong; model not in the allowlist;
                     observation-layer cell. Must refuse before any server, model call or trace.
  T4 packet          Pass A packet has no evaluator, cell, run id, model or repeat; pass B adds the evaluator;
                     the key file maps the packet back to the trace sha256.
  T5 Date shim       h1_wrapper.DATE_SHIM is byte-identical to replay.py's.
Run: BW_ROOT=<private copy> PYTHONPATH=<private copy> <BreakingWeb venv python> h1_selftest.py OUT_DIR
Needs a clean reddit build in BW_ROOT and the budget file from h1_budget.py.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import h1_wrapper as W  # noqa: E402

TASK = 'reddit_compose_message'
ROUTE = [  # the recorded Gemini route (replay script /tmp/amt-syn/bw-replay/final/reddit/scripts/reddit_compose_message.json)
    ('click', 'link', 'Messages', None, ('link', 'Home')),   # in the sidebar scroller: hover it, then wheel
    ('click', 'button', 'Compose new message', None, None),
    ('fill', 'textbox', 'Recipient username', 'QuantumPanda', None),
    ('fill', 'textbox', 'Message subject', 'Question about your AskReddit post', None),
    ('fill', 'textbox', 'Message body', 'Hey, I found your recent post really interesting. Could you share the source for that claim about honey?', None),
    ('click', 'button', 'Send message', None, None),
]


class FakeBedrock:
    """Answers Converse calls like Bedrock: reasoning block(s), then a text block with one action."""

    def __init__(self, family, policy):
        self.family, self.policy, self.calls, self.i, self.scrolls, self.hovered = family, policy, [], 0, 0, False
        self.problems = []

    def converse(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        if 'temperature' in kw.get('inferenceConfig', {}):
            self.problems.append('temperature sent')
        add = kw.get('additionalModelRequestFields') or {}
        if self.family == 'anthropic' and add.get('thinking', {}).get('display') != 'summarized':
            self.problems.append('anthropic call without display summarized')
        if self.family == 'openai' and 'effort' not in add.get('reasoning', {}):
            self.problems.append('openai call without reasoning.effort')
        last = kw['messages'][-1]['content'][-1]['text']
        if 'system' not in kw:   # history-summary call
            text, why = 'Summary: the agent scrolled the feed several times.', 'summarising dropped turns'
        else:
            text, why = self.act(last)
        if self.family == 'anthropic':
            blocks = [{'reasoningContent': {'reasoningText': {'text': f'(fake reasoning) {why}', 'signature': 'fake-signature-' + str(len(self.calls))}}}]
        else:
            blocks = [{'reasoningContent': {'redactedContent': b'\x00fake-opaque-' + str(len(self.calls)).encode()}}]
        chars = sum(len(b.get('text', '')) for m in kw['messages'] for b in m['content'])
        return {'output': {'message': {'role': 'assistant', 'content': blocks + [{'text': text}]}},
                'stopReason': 'end_turn', 'metrics': {'latencyMs': 3},
                'usage': {'inputTokens': int(chars / 2.33), 'outputTokens': 40 + len(text) // 3, 'totalTokens': 0}}

    def act(self, obs):
        if self.policy == 'scroll':
            return 'scroll(0, 400)', 'scroll policy'
        if self.i >= len(ROUTE):
            return "send_msg_to_user('done')", 'route complete'
        kind, role, name, value, anchor = ROUTE[self.i]
        m = re.search(r"\[([^\]]+)\] " + re.escape(role) + r" '" + re.escape(name) + r"'", obs)
        if not m and anchor and not self.hovered:
            h = re.search(r"\[([^\]]+)\] " + re.escape(anchor[0]) + r" '" + re.escape(anchor[1]) + r"'", obs)
            if h:
                self.hovered = True
                return f'hover({h.group(1)!r})', f'move the mouse over the scroller of {name!r}'
        if not m:
            self.scrolls += 1
            if self.scrolls > 8:
                return 'noop()', f'{role} {name!r} never seen'
            return 'scroll(0, 500)', f'{role} {name!r} not in view'
        self.i += 1
        self.scrolls, self.hovered = 0, False
        if kind == 'fill':
            return f'fill({m.group(1)!r}, {value!r})', f'fill {name}'
        return f'click({m.group(1)!r})', f'click {role} {name}'


def args(**kw):
    base = dict(task=TASK, cell='clean', model='us.anthropic.claude-sonnet-5-5', manifest=None, repeat=0,
                expect_bundle=None, effort=None, budget_file=W.DEFAULT_BUDGET, port=8396, out_root=None,
                allow_shared_clone=False)
    base.update(kw)
    return argparse.Namespace(**base)


RESULTS = []


def check(name, ok, why=''):
    RESULTS.append((name, bool(ok), why))
    print(f'{"PASS" if ok else "FAIL"}  {name}{"  -- " + why if why and not ok else ""}')


def port_free(p):
    s = socket.socket()
    try:
        return s.connect_ex(('127.0.0.1', p)) != 0
    finally:
        s.close()


def recompute_prompt_sha(tr, man, k):
    """Rebuild the k-th agent request from the trace alone: each message of the step's prompt digest is
    looked up by sha256 among the system prompt, the stored observation texts, actions and summary markers."""
    import breakingweb.agent as bwa
    pool = {W.sha256_text(bwa.SYSTEM_PROMPT): bwa.SYSTEM_PROMPT}
    for s in tr['steps']:
        for txt in (s['observation_text'], s['action'], s['summary_marker_text']):
            if txt is not None:
                pool[W.sha256_text(txt)] = txt
    msgs = [{'role': d['role'], 'content': pool[d['sha256']]} for d in tr['steps'][k]['prompt_digest']]
    g = W.Gateway(tr['model'], None, man['model']['effort'], man['model']['inference_config']['maxTokens'])
    return W.sha256_text(W.canon(g.request(msgs)))


def t1(out, vm_path):
    fake = FakeBedrock('anthropic', 'route')
    rdir = W.cmd_run(args(manifest=vm_path, out_root=f'{out}/traces'), client=fake, client_meta={'fake': True, 'region': 'us-west-2'})
    tr = json.load(open(f'{rdir}/trace.json'))
    man = json.load(open(f'{rdir}/manifest.json'))
    check('T1 evaluator success', tr['outcome']['success'] is True, json.dumps(tr['outcome'])[:300])
    check('T1 end_reason agent_finished', tr['end_reason'] == 'agent_finished', tr['end_reason'])
    need = ['step', 'url', 'observation_text', 'prompt_sha256', 'reasoning', 'action', 'action_error', 'tokens',
            'latency_s', 'stop_reason', 'model_text', 'reasoning_visibility']
    missing = [(s['step'], k) for s in tr['steps'] for k in need if k not in s or s[k] is None and k != 'action_error']
    check('T1 every step has every field', not missing and tr['steps'], str(missing[:5]))
    check('T1 tokens in/out on every step', all(s['tokens']['in'] and s['tokens']['out'] for s in tr['steps']))
    check('T1 reasoning text stored, signature hashed',
          all(s['reasoning'] and s['reasoning'][0]['kind'] == 'text' and s['reasoning'][0]['text'].startswith('(fake reasoning)')
              and len(s['reasoning'][0]['signature_sha256']) == 64 for s in tr['steps']))
    check('T1 reasoning visibility summary', tr['checks']['reasoning_visibility'] == ['summary'], str(tr['checks']['reasoning_visibility']))
    ok = all(recompute_prompt_sha(tr, man, k) == tr['steps'][k]['prompt_sha256'] for k in range(len(tr['steps'])))
    check('T1 prompt hash recomputable from trace', ok)
    agent_calls = [c for c in fake.calls if 'system' in c]
    check('T1 observation text = what the fake received',
          len(agent_calls) == len(tr['steps']) and
          all(agent_calls[i]['messages'][-1]['content'][-1]['text'] == tr['steps'][i]['observation_text'] for i in range(len(tr['steps']))))
    check('T1 no temperature sent', not fake.problems and not tr['checks']['temperature_sent_any'], str(fake.problems))
    check('T1 M1 served = manifest', tr['checks']['m1_pass'] and tr['checks']['m1_checked'], str(tr['checks']['m1_checked'])[:300])
    check('T1 isolation self-check', tr['checks']['isolation_probe_blocked'] and tr['checks']['date_shim_ok'],
          f"{tr['checks']['isolation_probe_blocked']} {tr['checks']['page_date_ms_at_start']}")
    check('T1 url per step', all(s['url'] and s['url'].startswith('http://127.0.0.1') for s in tr['steps']))
    files = ['trace.json', 'manifest.json', 'server.log', 'SHA256SUMS']
    check('T1 files read-only', all(not os.access(f'{rdir}/{f}', os.W_OK) for f in files) and not os.access(rdir, os.W_OK))
    sums = dict(reversed(l.split('  ')) for l in open(f'{rdir}/SHA256SUMS').read().split('\n') if l)
    check('T1 SHA256SUMS valid', all(hashlib.sha256(open(f'{rdir}/{n}', 'rb').read()).hexdigest() == h for n, h in sums.items()))
    check('T1 manifest trace hash', man['trace_sha256'] == sums['trace.json'])
    check('T1 manifest fields', all(k in man for k in ('code', 'bundle', 'model', 'seeds', 'harness', 'isolation', 'versions'))
          and man['bundle']['bundle_fx6'] == json.load(open(vm_path))['bundle_fx6'] and man['model']['temperature_sent'] is None)
    try:
        os.makedirs(rdir, exist_ok=False); reuse = True
    except FileExistsError:
        reuse = False
    check('T1 run dir not reusable', not reuse)
    return rdir


def t2(out, vm_path):
    import breakingweb.agent as bwa
    b = json.load(open(W.DEFAULT_BUDGET))
    b['per_task'][TASK]['cap_h1'] = 12
    bf = f'{out}/budget_test.json'
    json.dump(b, open(bf, 'w'))
    saved = bwa.MAX_INPUT_TOKENS
    bwa.MAX_INPUT_TOKENS = 6000
    try:
        fake = FakeBedrock('openai', 'scroll')
        rdir = W.cmd_run(args(manifest=vm_path, out_root=f'{out}/traces', model='us.openai.gpt-5.6-sol', budget_file=bf, port=8397),
                         client=fake, client_meta={'fake': True, 'region': 'us-east-2'})
    finally:
        bwa.MAX_INPUT_TOKENS = saved
    tr = json.load(open(f'{rdir}/trace.json'))
    man = json.load(open(f'{rdir}/manifest.json'))
    check('T2 end_reason step_cap at 12', tr['end_reason'] == 'step_cap' and tr['n_steps_executed'] == 12, f"{tr['end_reason']} {tr['n_steps_executed']}")
    o = tr['outcome']
    check('T2 forced evaluation stored for the failed run', o['success'] is False and isinstance(o['checks'], list) and o['checks']
          and o['negative_checks'] is not None and o['source'].startswith('force_evaluate'), json.dumps(o)[:300])
    sc = tr['summary_calls']
    check('T2 summary calls ran and were logged', len(sc) >= 1 and all(c['temperature_requested'] == 0.0 and c['temperature_sent'] is None
                                                                  and not c['error'] and c['text'] for c in sc), f'{len(sc)} calls')
    check('T2 summary text reached the agent prompt', any(s['summary_marker_text'] and 'Summary: the agent scrolled' in s['summary_marker_text']
                                                          for s in tr['steps']))
    check('T2 reasoning visibility encrypted', tr['checks']['reasoning_visibility'] == ['encrypted']
          and all(r['kind'] == 'encrypted' and len(r['sha256']) == 64 for s in tr['steps'] for r in s['reasoning']))
    check('T2 openai request shape', not fake.problems and man['model']['additional_model_request_fields'] == {'reasoning': {'effort': 'medium', 'summary': 'detailed'}},
          str(fake.problems))
    check('T2 trim threshold recorded', man['harness']['max_input_tokens_est'] == 6000)
    trimmed = [k for k, st in enumerate(tr['steps']) if st['history_trimmed']]
    check('T2 trimmed prompts recomputable from trace', trimmed and
          all(recompute_prompt_sha(tr, man, k) == tr['steps'][k]['prompt_sha256'] for k in range(len(tr['steps']))),
          f'{len(trimmed)} trimmed steps')
    return rdir


def t3(out, vm_path):
    vm = json.load(open(vm_path))
    bad = copy.deepcopy(vm)
    k = next(iter(bad['files']))
    bad['files'][k] = '0' * 64
    bad_path = f'{out}/manifest_bad.json'
    json.dump(bad, open(bad_path, 'w'))
    cases = [('changed file hash', dict(manifest=bad_path)),
             ('wrong --expect-bundle', dict(manifest=vm_path, expect_bundle='0123456789abcdef')),
             ('model not allowed', dict(manifest=vm_path, model='google.gemini-3.1-pro')),
             ('observation-layer cell', dict(manifest=vm_path, cell='names+')),
             ('cell/build mismatch', dict(manifest=vm_path, cell='names'))]
    for name, kw in cases:
        root = f'{out}/traces_refuse'
        os.makedirs(root, exist_ok=True)
        before = set(os.listdir(root))
        fake = FakeBedrock('anthropic', 'route')
        try:
            W.cmd_run(args(out_root=root, port=8398, **kw), client=fake, client_meta={'fake': True})
            refused, why = False, 'ran'
        except W.RefuseToStart as e:
            refused, why = True, str(e)
        check(f'T3 refuse: {name}', refused and not fake.calls and set(os.listdir(root)) == before and port_free(8398), why[:200])
        print(f'      reason: {why[:160]}')


def t4(out, rdir):
    kf = f'{out}/packet_key.jsonl'
    pa = W.make_packet(rdir, f'{out}/packet_A.json', kf, with_outcome=False)
    pb = W.make_packet(rdir, f'{out}/packet_B.json', kf, with_outcome=True)
    A = json.load(open(f'{out}/packet_A.json'))
    B = json.load(open(f'{out}/packet_B.json'))

    def keys(o):
        if isinstance(o, dict):
            return set(o) | set().union(*[keys(v) for v in o.values()]) if o else set(o)
        if isinstance(o, list):
            return set().union(*[keys(v) for v in o]) if o else set()
        return set()
    forbidden = {'cell', 'run_id', 'repeat', 'model', 'bundle', 'manifest', 'codemod'}
    check('T4 pass A hides condition and outcome', not (keys(A) & forbidden) and 'evaluator' not in A, str(keys(A) & forbidden))
    check('T4 pass B adds only the evaluator', not (keys(B) & forbidden) and 'evaluator' in B and set(B) - set(A) == {'evaluator'})
    lines = [json.loads(l) for l in open(kf)]
    tsha = hashlib.sha256(open(f'{rdir}/trace.json', 'rb').read()).hexdigest()
    check('T4 key file maps packets to the trace', {l['packet_id'] for l in lines} >= {pa, pb} and all(l['trace_sha256'] == tsha for l in lines))


def t5():
    import replay
    check('T5 DATE_SHIM identical to replay.py', W.DATE_SHIM == replay.DATE_SHIM and W.DATE_T0 == replay.DATE_T0)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/amt-syn/h1-test/selftest'
    os.makedirs(out, exist_ok=True)
    vm_path = f'{out}/reddit__clean.json'
    vm = W.make_variant_manifest(W.ROOT, 'reddit', 'clean')
    json.dump(vm, open(vm_path, 'w'), indent=1)
    print(f'BW_ROOT {W.ROOT}; reddit clean bundle {vm["bundle"]} / fx6 {vm["bundle_fx6"]}')
    t5()
    t3(out, vm_path)
    r1 = t1(out, vm_path)
    t4(out, r1)
    r2 = t2(out, vm_path)
    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)
    summary = {'passed': sum(1 for _, ok, _ in RESULTS if ok), 'failed': n_fail, 't1_run': r1, 't2_run': r2,
               'results': [{'test': n, 'pass': ok, 'why': w} for n, ok, w in RESULTS]}
    json.dump(summary, open(f'{out}/selftest.json', 'w'), indent=1)
    print(json.dumps({k: summary[k] for k in ('passed', 'failed', 't1_run', 't2_run')}))
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
