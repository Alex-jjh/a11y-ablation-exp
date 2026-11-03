#!/usr/bin/env python3
"""H1 wrapper for the v2 pilot: one episode = (task, cell, model, harness H1, repeat) of BreakingWeb's own
BrowserGym text agent (`breakingweb/agent.py` LLMAgent), with the request, logging, isolation, bundle and
budget fixes the pipeline smoke test found (docs/feasibility/2026-10-30-pipeline-smoke.md §4). The clone is
never edited: the wrapper subclasses LLMAgent and BreakingWebTask, replaces the Bedrock call with its own
gateway, and during the episode points `breakingweb.agent.llm_complete` (the function the history trim calls
for its summary) at the same gateway.

What is the same as the shipped harness (agent.py / agent_eval.py, release 052f0f0):
  system prompt SYSTEM_PROMPT; observation `format_obs_for_llm` (flatten_axtree_to_str, filter_visible_only,
  filter_with_bid_only, with_clickable, with_visible); text only; one action per step, action set
  bid+chat+infeas, multiaction off; the assistant turn stored in history is the extracted action only;
  `trim_messages` at 26,000 estimated tokens with an LLM summary of dropped turns; `_extract_action`;
  context-overflow retry; throttling retries (5 attempts, 2**i+1 s); trajectory entries built with
  agent_eval's `_parse_action_string`, `_extract_targets`, `_trajectory_status`; 120 s per-step limit;
  viewport 1280x720; backend seed = None (backend default, as the stock harness creates sessions).

What the wrapper changes, and why (smoke record §4 numbers):
  P1 temperature   Never sent, on the agent call and on the summary call. The clone sends temperature only
                   on the summary call (0.0); Opus 5.5 rejected it 4 of 4 times and the trim fell back
                   silently to the regex summary. Echo's Bedrock probe (Reference-project-echo/echo-ai-exp/
                   echo_gateway/models.py; probes 20261012T031937Z and 20261012T063435Z): Claude Opus 5.5,
                   Sonnet 5.5 and Sonnet 5 accept only the default 1.0 ("`temperature` is deprecated for
                   this model"), GPT-5.6 accepts no temperature at all. So every allowed model rejects 0.0;
                   the requested value is logged per call next to `temperature_sent: null`.
  P2 evaluation    The backend evaluator's verdict on the final state (`force_evaluate`) is stored for every
                   run, with checks and negative checks. agent_eval.run_episode keeps it only when its score
                   beats the in-loop one, so a failed run kept "Agent did not finish". `outcome.success` is
                   the forced verdict; the in-loop verdict (only when the agent declared done) is kept beside
                   it with a flag if they differ.
  P3 reasoning     Requested explicitly per model (MODELS below) and every reasoning block returned is
                   stored per call: the text (Anthropic: `display: "summarized"`, a summary written by the
                   API; the raw chain of thought is never returned on these models), the signature as sha256
                   and length, and encrypted blocks as sha256 and length. `reasoning.visibility` is
                   `summary`, `encrypted`, `none` or `mixed`. Anthropic `budget_tokens` is not sent: it is
                   rejected with a 400 on Opus 5.5, Sonnet 5.5 and Sonnet 5 (claude-api reference, cached
                   2026-10-06; Echo probe: "thinking.type.enabled is not supported for this model"); depth is
                   set by `output_config.effort`, and maxTokens (16,384, reasoning included) is the hard cap.
  P4 isolation     Page Date fixed at load (replay.py DATE_SHIM, T0 2026-10-30T09:00Z, then running), every
                   request to a host other than 127.0.0.1/localhost aborted, both installed on the browser
                   context before the task navigates; an isolation self-check after setup (Date.now() near
                   T0; a fetch to 198.51.100.1, TEST-NET-2, must be aborted by the route).
  P5 bundle        Before anything starts, the on-disk static/envs/<env> tree must equal a variant manifest
                   (`manifest` subcommand; per-file sha256 and a path-free bundle hash) whose env and build
                   match the cell, and `--expect-bundle` if given; otherwise the run refuses to start (exit 3,
                   no server, no model call, no trace). During the run every document and env asset the
                   browser receives is hashed against the manifest (M1); a mismatch is recorded and makes the
                   run `m1_pass: false`.
  P6 step budget   Per task from h1_budget.py (reference trajectories with a margin; that docstring states the
                   rule and grounds), default file /tmp/amt-syn/h1/budget.json. Wall cap 1,800 s.
  logging          Per step: index, URL, the exact observation text sent, sha256 of the full Converse request
                   body (prompt hash) and a per-message digest of it, the model's reasoning, raw text, action,
                   action error, tokens in/out/cache (and reasoning tokens if Converse reports them), latency,
                   stop reason, retries. Per summary call the same, plus the summary or fallback text.
  server           Started by the wrapper (python -m uvicorn breakingweb.app:app, cwd = BW_ROOT, 127.0.0.1
                   only) with output to a log file, not an unread pipe (smoke record §4.5).

Outputs: /tmp/amt-syn/traces/<run_id>/trace.json (episode), manifest.json (provenance), server.log,
SHA256SUMS; files are written once and set read-only; an existing run directory is never reused.

Subcommands (BreakingWeb venv python; BW_ROOT = private checkout, also first on sys.path):
  run      --task T --cell C --model M --manifest VM.json [--repeat N] [--expect-bundle H]
           [--budget-file F] [--port P] [--out-root /tmp/amt-syn/traces] [--fake SCRIPT.json]
  manifest --env E --build B --out VM.json [--codemod PATH]   write the variant manifest of the built env
  packet   TRACE_DIR OUT.json [--key-file K]                  observer packet with condition fields removed
  probe    [--models ...]                                     request-shape check: one tiny call per model
                                                              (no BreakingWeb content), prints what came back
Env: AWS_PROFILE (codex-DO-NOT-DELETE for real models), Node/pnpm not needed (no build here).
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import glob
import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
ROOT = os.path.realpath(os.environ.get('BW_ROOT', os.path.expanduser('~/.workspace/_refsrc/BreakingWeb')))
SHARED_CLONE = os.path.realpath(os.path.expanduser('~/.workspace/_refsrc/BreakingWeb'))
FX6 = '/tmp/amt-syn/bw-fx-src6/BreakingWeb'   # path prefix of the replay record's bundle formula (design.yaml)
WRAPPER_VERSION = 'h1-wrapper-2026-11-02'
HOST = '127.0.0.1'

DATE_T0 = 1793437200000  # 2026-10-30T09:00:00Z, as replay.py and click_effect.py
DATE_SHIM = '''(() => { const T0 = %d, RD = Date, p0 = performance.now();
  function D(...a) { if (!new.target) return new RD(D.now()).toString(); return a.length ? new RD(...a) : new RD(D.now()); }
  D.prototype = RD.prototype; D.now = () => T0 + Math.floor(performance.now() - p0); D.parse = RD.parse; D.UTC = RD.UTC;
  Object.setPrototypeOf(D, RD); window.Date = D; })();''' % DATE_T0
ISOLATION_PROBE_URL = 'http://198.51.100.1/amt-isolation-probe'

MAX_TOKENS = 16384
STEP_TIMEOUT_S = 120          # agent_eval._STEP_TIMEOUT_SECONDS
WALL_CAP_S = 1800             # DESIGN §3
DEFAULT_BUDGET = '/tmp/amt-syn/h1/budget.json'
BUILD_CELLS = {'clean', 'none', 'landmarks', 'headings', 'names', 'labels', 'alt', 'tableheads', 'pc_break'}
OBS_CELLS = {'names+', 'names50', 'fmt_wrap', 'pos_info'}   # observation-layer controls: Stage 0, not built
BIND_DIFFS = {'breakingweb/app.py', 'scripts/_sweep_common.sh', 'scripts/breakingweb.sh', 'scripts/run_gmail_sweep.sh'}

# ----------------------------------------------------------------------------- models (allowlist)
# Request fields per model. Grounds: Echo probe tables (echo_gateway/models.py) for what Bedrock accepts;
# claude-api reference (cached 2026-10-06) for defaults. `effort` defaults: the provider default made
# explicit (Opus 5.5 medium; Sonnet 5.5 and Sonnet 5 high), GPT-5.6 medium (its Bedrock default value is
# [unverified]; Echo saw reasoning on by default). Alex decides the values (DESIGN §10 item 2).
MODELS = {
    'us.anthropic.claude-sonnet-5-5': dict(family='anthropic', region='us-west-2', effort='high'),
    'us.anthropic.claude-opus-5-5': dict(family='anthropic', region='us-west-2', effort='medium'),
    'us.anthropic.claude-sonnet-5': dict(family='anthropic', region='us-west-2', effort='high'),
    'us.openai.gpt-5.6-sol': dict(family='openai', region='us-east-2', effort='medium'),
    'us.openai.gpt-5.6-terra': dict(family='openai', region='us-east-2', effort='medium'),
    'us.openai.gpt-5.6-luna': dict(family='openai', region='us-east-2', effort='medium'),
}
TEMPERATURE_RULE = {'anthropic': 'only the default 1.0 accepted; 0.0 rejected ("temperature is deprecated for this model"): Echo probe',
                    'openai': 'no temperature accepted ("This model doesn\'t support the temperature field."): Echo probe'}


def reasoning_fields(model, effort):
    fam = MODELS[model]['family']
    if fam == 'anthropic':
        return {'thinking': {'type': 'adaptive', 'display': 'summarized'}, 'output_config': {'effort': effort}}
    # summary 'detailed': probe 2026-11-02 (/tmp/amt-syn/h1/probe-20261102b.json): without it GPT-5.6-sol returned
    # one encrypted block; with 'auto' or 'detailed' a readable reasoning summary; 'bogus-level' is rejected, so
    # Bedrock parses the field
    return {'reasoning': {'effort': effort, 'summary': 'detailed'}}


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_text(s):
    return sha256_bytes(s.encode('utf-8'))


def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=_jsonable)


def _jsonable(o):
    if isinstance(o, (bytes, bytearray)):
        return {'__bytes_sha256__': sha256_bytes(bytes(o)), 'len': len(o)}
    return str(o)


def file_sha(p):
    return sha256_bytes(open(p, 'rb').read()) if os.path.isfile(p) else None


def git(args, cwd):
    r = subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


class RefuseToStart(Exception):
    """A pre-run check failed; nothing was started."""


# ----------------------------------------------------------------------------- bundle / variant manifest
def bundle_tree(root, env):
    base = f'{root}/breakingweb/static/envs/{env}'
    files = {}
    for p in sorted(glob.glob(f'{base}/**', recursive=True)):
        if os.path.isfile(p):
            files[os.path.relpath(p, base)] = sha256_bytes(open(p, 'rb').read())
    return files


def bundle_hashes(root, env):
    """`bundle`: sha256 over (path relative to the checkout, bytes), as pipeline_smoke.py `bundle`;
    `bundle_fx6`: the replay record's formula with the bw-fx-src6 path prefix, comparable with design.yaml
    bundles_sha256_prefix. Both truncated to 16 hex as in the records; `tree` is the full per-file list."""
    h, h6 = hashlib.sha256(), hashlib.sha256()
    for p in sorted(glob.glob(f'{root}/breakingweb/static/envs/{env}/**', recursive=True)):
        if os.path.isfile(p):
            data = open(p, 'rb').read()
            rel = os.path.relpath(p, root)
            h.update(rel.encode()); h.update(data)
            h6.update(f'{FX6}/{rel}'.encode()); h6.update(data)
    return h.hexdigest()[:16], h6.hexdigest()[:16]


def make_variant_manifest(root, env, build, codemod_path=None):
    srcs = [f'breakingweb/environments/{env}/src', 'breakingweb/environments/shared/src']
    diff = subprocess.run(['git', 'diff', '--'] + srcs, cwd=root, capture_output=True).stdout
    status = git(['status', '--short', '--'] + srcs, root) or ''
    if build == 'clean' and status:
        raise SystemExit(f'build "clean" but sources differ from HEAD:\n{status}')
    if build != 'clean' and build != 'none' and not status:
        raise SystemExit(f'build "{build}" but sources equal HEAD (codemod not applied?)')
    b, b6 = bundle_hashes(root, env)
    return {'schema': 'amt-variant-manifest/1', 'env': env, 'build': build, 'checkout': root,
            'git_head': git(['rev-parse', 'HEAD'], root), 'src_status': status.splitlines(),
            'src_diff_sha256': sha256_bytes(diff), 'codemod_sha256': file_sha(codemod_path) if codemod_path else None,
            'bundle': b, 'bundle_fx6': b6, 'files': bundle_tree(root, env),
            'created': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}


def check_bundle(vm, env, cell, expect=None):
    """P5: refuse unless the build on disk is the one the manifest declares for this cell."""
    if vm.get('schema') != 'amt-variant-manifest/1':
        raise RefuseToStart('variant manifest schema unknown')
    if vm['env'] != env:
        raise RefuseToStart(f'manifest env {vm["env"]} != task env {env}')
    want_build = cell if cell in BUILD_CELLS else None
    if want_build is None:
        raise RefuseToStart(f'cell {cell} has no build; observation-layer cells are Stage 0 and not implemented')
    if vm['build'] != want_build:
        raise RefuseToStart(f'manifest build {vm["build"]} != cell {cell}')
    disk = bundle_tree(ROOT, env)
    if disk != vm['files']:
        diff = sorted(set(disk.items()) ^ set(vm['files'].items()))[:6]
        raise RefuseToStart(f'on-disk bundle differs from the manifest: {diff}')
    b, b6 = bundle_hashes(ROOT, env)
    if (b, b6) != (vm['bundle'], vm['bundle_fx6']):
        raise RefuseToStart(f'bundle hash {b}/{b6} != manifest {vm["bundle"]}/{vm["bundle_fx6"]}')
    if expect and expect not in (b, b6):   # design.yaml bundles_sha256_prefix uses the fx6 formula
        raise RefuseToStart(f'--expect-bundle {expect} != on-disk {b} (path-free) / {b6} (fx6 formula)')
    return {'bundle': b, 'bundle_fx6': b6, 'n_files': len(disk)}


# ----------------------------------------------------------------------------- gateway (all LLM calls)
def parse_blocks(blocks):
    texts, reasoning = [], []
    for blk in blocks or []:
        if 'text' in blk and isinstance(blk['text'], str):
            texts.append(blk['text'])
        elif isinstance(blk.get('reasoningContent'), dict):
            rc = blk['reasoningContent']
            rt = rc.get('reasoningText')
            if isinstance(rt, dict):
                sig = rt.get('signature') or ''
                reasoning.append({'kind': 'text', 'text': rt.get('text') or '',
                                  'signature_sha256': sha256_text(sig) if sig else None, 'signature_len': len(sig)})
            if 'redactedContent' in rc:
                raw = rc['redactedContent']
                raw = raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode()
                reasoning.append({'kind': 'encrypted', 'sha256': sha256_bytes(bytes(raw)), 'len': len(raw)})
    has_text = any(r['kind'] == 'text' and r['text'] for r in reasoning)
    has_enc = any(r['kind'] == 'encrypted' for r in reasoning)
    empty_text = any(r['kind'] == 'text' and not r['text'] for r in reasoning)
    vis = ('mixed' if has_text and has_enc else 'summary' if has_text else 'encrypted' if has_enc
           else 'empty_text' if empty_text else 'none')
    return ''.join(texts), reasoning, vis


def to_converse(messages):
    """The clone's _complete_bedrock conversion, verbatim in effect: system -> top-level system blocks;
    user/assistant -> messages; consecutive same-role turns merged."""
    system_blocks, converted = [], []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if role == 'system':
            if content:
                system_blocks.append({'text': content})
            continue
        br = 'assistant' if role == 'assistant' else 'user'
        if converted and converted[-1]['role'] == br:
            converted[-1]['content'].append({'text': content})
        else:
            converted.append({'role': br, 'content': [{'text': content}]})
    return system_blocks, converted


class Gateway:
    """Every model call of the episode. Never sends temperature; sends the model's reasoning fields; logs
    request hash, fields, response blocks, usage, stop reason, latency and retries."""

    def __init__(self, model, client, effort, max_tokens=MAX_TOKENS):
        self.model, self.client, self.effort, self.max_tokens = model, client, effort, max_tokens
        self.additional = reasoning_fields(model, effort)
        self.calls = []

    def request(self, messages):
        system, conv = to_converse(messages)
        kw = {'modelId': self.model, 'messages': conv, 'inferenceConfig': {'maxTokens': self.max_tokens},
              'additionalModelRequestFields': copy.deepcopy(self.additional)}
        if system:
            kw['system'] = system
        return kw

    def call(self, messages, kind, step, temperature_requested=None):
        kw = self.request(messages)
        rec = {'i': len(self.calls), 'kind': kind, 'step': step, 'model': self.model,
               'prompt_sha256': sha256_text(canon(kw)),
               'sent': {'inferenceConfig': kw['inferenceConfig'], 'additionalModelRequestFields': kw['additionalModelRequestFields'],
                        'n_messages': len(kw['messages']), 'has_system': 'system' in kw},
               'temperature_requested': temperature_requested, 'temperature_sent': None,
               'attempts': [], 't_start': time.time()}
        resp = None
        for attempt in range(5):   # the clone's retry rule
            t0 = time.time()
            try:
                resp = self.client.converse(**kw)
                rec['attempts'].append({'ok': True, 'latency_s': round(time.time() - t0, 3)})
                break
            except Exception as e:
                msg = f'{type(e).__name__}: {str(e)[:400]}'
                rec['attempts'].append({'ok': False, 'latency_s': round(time.time() - t0, 3), 'error': msg})
                transient = 'Throttling' in msg or '429' in msg or 'ServiceUnavailable' in msg
                if transient and attempt < 4:
                    time.sleep(2 ** attempt + 1)
                    continue
                rec['error'] = msg
                rec['latency_s'] = round(time.time() - rec['t_start'], 3)
                self.calls.append(rec)
                raise
        blocks = (resp.get('output') or {}).get('message', {}).get('content', [])
        text, reasoning, vis = parse_blocks(blocks)
        usage = resp.get('usage') or {}
        rec.update(latency_s=round(time.time() - rec['t_start'], 3),
                   server_latency_ms=(resp.get('metrics') or {}).get('latencyMs'),
                   stop_reason=resp.get('stopReason'), usage=usage,
                   tokens={'in': usage.get('inputTokens'), 'out': usage.get('outputTokens'),
                           'cache_read': usage.get('cacheReadInputTokens'), 'cache_write': usage.get('cacheWriteInputTokens'),
                           'reasoning': usage.get('reasoningTokens'),   # not in Converse usage on the probes so far: null
                           'reasoning_note': None if 'reasoningTokens' in usage else 'not reported by Converse; included in out'},
                   block_types=[next(iter(b)) for b in blocks], text=text, reasoning=reasoning, reasoning_visibility=vis)
        self.calls.append(rec)
        return rec


def make_real_client(model):
    import boto3
    for var in ('AWS_BEARER_TOKEN_BEDROCK', 'AWS_BEDROCK_API_KEY'):
        if os.environ.get(var):
            raise RefuseToStart(f'{var} is set: the profile rule forbids bearer tokens')
    prof = os.environ.get('AWS_PROFILE')
    if prof != 'codex-DO-NOT-DELETE':
        raise RefuseToStart(f'AWS_PROFILE must be codex-DO-NOT-DELETE (is {prof!r})')
    from botocore.config import Config
    sess = boto3.Session(profile_name=prof)
    c = sess.client('bedrock-runtime', region_name=MODELS[model]['region'],
                    config=Config(read_timeout=300, retries={'max_attempts': 1}))
    creds = sess.get_credentials()
    meta = {'aws_profile': prof, 'region': c.meta.region_name, 'credential_method': getattr(creds, 'method', None),
            'signature_version': c.meta.config.signature_version, 'bearer_env': False}
    return c, meta


# ----------------------------------------------------------------------------- agent and task subclasses
def build_classes(gateway, steplog, served, vm):
    import breakingweb.agent as bwa
    from breakingweb.browsergym_task import BreakingWebTask

    class H1Agent(bwa.LLMAgent):
        """LLMAgent.act with the model call through the gateway; same history, trim and extraction."""

        def __init__(self, model):
            # LLMAgent.__init__ builds a client from the provider; no client is needed here.
            self.model, self.provider, self.temperature, self.reasoning_effort = model, 'h1-gateway', None, None
            self.max_input_tokens, self.system_prompt = bwa.MAX_INPUT_TOKENS, bwa.SYSTEM_PROMPT
            self.client = gateway                      # passed to trim_messages so it attempts the summary
            self.messages, self._has_initial_obs = [], False
            self._last_raw_response, self._last_thought = '', ''
            self.step_index = 0

        def act(self, obs):
            self.step_index += 1
            if self._has_initial_obs:
                self._has_initial_obs = False
                content = self.messages[-1]['content']
            else:
                content = bwa.format_obs_for_llm(obs) if isinstance(obs, dict) else str(obs)
                self.messages.append({'role': 'user', 'content': content})
            served['_step'] = self.step_index
            n_before = len(gateway.calls)
            trimmed = bwa.trim_messages(self.messages, max_input_tokens=self.max_input_tokens,
                                        client=self.client, model=self.model, provider=self.provider)
            try:
                rec = gateway.call(trimmed, 'agent', self.step_index)
            except Exception as e:
                if 'input length' in str(e) or 'context_length' in str(e):
                    trimmed = bwa.trim_messages(self.messages, max_input_tokens=self.max_input_tokens - 4000,
                                                client=self.client, model=self.model, provider=self.provider)
                    rec = gateway.call(trimmed, 'agent', self.step_index)
                else:
                    raise
            response = rec['text']
            action = bwa._extract_action(response)
            self._last_raw_response = response
            self._last_thought = ''
            if response != action:   # the clone's thought extraction for text before the action
                m = re.search(re.escape(action[:20]), response)
                if m and m.start() > 0:
                    self._last_thought = re.sub(r'<think>.*?</think>', '', response[:m.start()].strip(), flags=re.DOTALL).strip()
            self.messages.append({'role': 'assistant', 'content': action})
            steplog.append({
                'step': self.step_index, 'url': obs.get('url') if isinstance(obs, dict) else None,
                'observation_text': content, 'observation_sha256': sha256_text(content), 'observation_chars': len(content),
                'truncated_in_observation': '[... content truncated ...]' in content,
                'prompt_sha256': rec['prompt_sha256'],
                'prompt_digest': [{'role': m['role'], 'sha256': sha256_text(m.get('content', '')), 'chars': len(m.get('content', '')),
                                   'kind': ('system' if m['role'] == 'system' else 'action' if m['role'] == 'assistant'
                                            else 'summary' if m.get('content', '').startswith(('[Summary of steps', '[Compressed factual state'))
                                            else 'observation')} for m in trimmed],
                'summary_marker_text': next((m['content'] for m in trimmed if m['role'] == 'user' and
                                             m.get('content', '').startswith(('[Summary of steps', '[Compressed factual state'))), None),
                'history_trimmed': len(trimmed) != len(self.messages) - 1 or any(
                    a.get('content') != b.get('content') for a, b in zip(trimmed, self.messages)),
                'summary_call_ids': [c['i'] for c in gateway.calls[n_before:] if c['kind'] == 'summary'],
                'call_id': rec['i'], 'model_text': response, 'thought': self._last_thought, 'action': action,
                'reasoning': rec['reasoning'], 'reasoning_visibility': rec['reasoning_visibility'],
                'tokens': rec['tokens'], 'latency_s': rec['latency_s'], 'server_latency_ms': rec['server_latency_ms'],
                'stop_reason': rec['stop_reason'], 'attempts': len(rec['attempts']),
            })
            return action

    def summary_llm_complete(client, model, messages, temperature=None, provider='openai', reasoning_effort=None):
        """Stands in for breakingweb.agent.llm_complete inside trim_messages (the only caller during the run)."""
        try:
            rec = gateway.call(messages, 'summary', served.get('_step'), temperature_requested=temperature)
        except Exception:
            raise   # trim_messages catches it and uses its regex fallback; the failure is in gateway.calls
        return rec['text'], ''

    class H1Task(BreakingWebTask):
        def setup(self, page):
            ctx = page.context
            ctx.add_init_script(DATE_SHIM)
            served.update(external_aborted=[], responses=[], m1_mismatch=[])

            def route(r):
                u = r.request.url
                host = urllib.parse.urlparse(u).hostname
                if host in ('127.0.0.1', 'localhost') or u.startswith(('data:', 'blob:')):
                    r.continue_()
                else:
                    served['external_aborted'].append({'url': u[:160], 'step': served.get('_step', 0)}); r.abort()
            ctx.route('**/*', route)
            page.on('response', lambda r: served['responses'].append(r))
            out = super().setup(page)
            served['session_id_sha256'] = sha256_text(self._session_id or '')
            served['start_url'] = page.url.split('?')[0]
            served['page_date_ms_at_start'] = page.evaluate('() => Date.now()')
            probe = page.evaluate(f'''() => fetch("{ISOLATION_PROBE_URL}").then(() => "loaded", e => "blocked")''')
            served['isolation_probe'] = {'result': probe,
                                         'aborted_by_route': any(x['url'].startswith(ISOLATION_PROBE_URL) for x in served['external_aborted'])}
            served['external_aborted'] = [x for x in served['external_aborted'] if not x['url'].startswith(ISOLATION_PROBE_URL)]
            hash_responses(served, vm, self._env_id)
            return out

        def force_evaluate(self, page):
            res = super().force_evaluate(page)
            served['force_evaluate'] = res
            return res

    return H1Agent, H1Task, summary_llm_complete


def hash_responses(served, vm, env):
    """M1 during the run: every document or env asset the browser received equals the manifest's file."""
    pend, served['responses'] = served['responses'], []
    checked = served.setdefault('m1_checked', [])
    for r in pend:
        path = urllib.parse.urlparse(r.url).path
        m = re.match(rf'^/env/{re.escape(env)}/assets/(.+)$', path)
        is_doc = r.request.resource_type == 'document' and path.startswith(f'/env/{env}')
        if not (m or is_doc):
            continue
        rel = f'assets/{m.group(1)}' if m else 'index.html'
        try:
            body = r.body()
        except Exception as e:
            checked.append({'rel': rel, 'status': r.status, 'sha256': None, 'match': None, 'error': str(e)[:120]})
            continue
        sha = sha256_bytes(body)
        ok = vm['files'].get(rel) == sha
        checked.append({'rel': rel, 'status': r.status, 'sha256': sha[:16], 'match': ok, 'step': served.get('_step', 0)})
        if not ok:
            served['m1_mismatch'].append(rel)


# ----------------------------------------------------------------------------- episode
def start_server(port, logpath):
    from breakingweb.runner import ensure_controller_secret, wait_for_server
    if wait_for_server(HOST, port, timeout=1):
        raise RefuseToStart(f'port {port} already serving; the wrapper starts its own backend')
    env = os.environ.copy()
    env['BREAKINGWEB_CONTROLLER_SECRET'] = ensure_controller_secret()
    env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH', '')
    log = open(logpath, 'w')
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'breakingweb.app:app', '--host', HOST, '--port', str(port),
                             '--log-level', 'warning'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    if not wait_for_server(HOST, port, timeout=90):
        proc.terminate()
        raise RuntimeError('backend did not start')
    return proc, log


def run_loop(env, agent, max_steps, served, vm, env_id):
    """agent_eval.run_episode's order of operations, with the end reason and the forced verdict kept."""
    from breakingweb.agent_eval import _extract_targets, _parse_action_string, _trajectory_status
    t_start = time.time()
    traj, end_reason, in_loop_eval = [], None, None
    obs, info = env.reset()
    task_info = info.get('task_info', {})
    goal = obs.get('goal', '') if isinstance(obs, dict) else ''
    agent.reset(obs)
    for step in range(max_steps):
        if time.time() - t_start > WALL_CAP_S:
            end_reason = 'wall_cap'
            break
        pre = obs
        t0 = time.time()
        try:
            action = agent.act(obs)
        except Exception as e:
            end_reason = 'call_error'
            served['call_error'] = f'{type(e).__name__}: {str(e)[:300]}'
            break
        if time.time() - t0 > STEP_TIMEOUT_S:    # the clone breaks before env.step when act exceeds 120 s
            end_reason = 'step_timeout'
            break
        obs, reward, terminated, truncated, step_info = env.step(action)
        hash_responses(served, vm, env_id)
        err = obs.get('last_action_error', '') if isinstance(obs, dict) else ''
        parsed = _parse_action_string(action)
        entry = {'step': step + 1, 'action': parsed, 'raw_action': action, 'targets': _extract_targets(parsed, pre),
                 'status': _trajectory_status(parsed, err, terminated), 'reward': reward,
                 'elapsed_seconds': round(time.time() - t_start, 1), 'last_action_error': err,
                 'url_after': obs.get('url') if isinstance(obs, dict) else None}
        traj.append(entry)
        if terminated:
            in_loop_eval = step_info.get('task_info', {}).get('evaluation') or None
            end_reason = 'agent_infeasible' if parsed.get('action') == 'report_infeasible' else 'agent_finished'
            break
        if truncated:
            end_reason = 'env_truncated'
            break
    else:
        end_reason = 'step_cap'
    forced = {}
    try:
        task = getattr(env, 'task', None) or getattr(getattr(env, 'unwrapped', None), 'task', None)
        page = getattr(env, 'page', None) or getattr(getattr(env, 'unwrapped', None), 'page', None)
        forced = task.force_evaluate(page) or {}
    except Exception as e:
        forced = {'error': f'{type(e).__name__}: {str(e)[:300]}'}
    try:
        page = getattr(env, 'page', None) or getattr(getattr(env, 'unwrapped', None), 'page', None)
        served['page_date_ms_at_end'] = page.evaluate('() => Date.now()')
        served['final_url'] = page.url.split('?')[0]
    except Exception:
        pass
    return {'goal': goal, 'task_info': task_info, 'trajectory': traj, 'end_reason': end_reason,
            'in_loop_evaluation': in_loop_eval, 'forced_evaluation': forced,
            'elapsed_s': round(time.time() - t_start, 1)}


def code_hashes():
    mine = {f'scripts/probe/breakingweb/{n}': file_sha(f'{HERE}/{n}') for n in
            ('h1_wrapper.py', 'h1_budget.py', 'codemod.py', 'replay.py')}
    clone = {f'breakingweb/{n}': file_sha(f'{ROOT}/breakingweb/{n}') for n in
             ('agent.py', 'agent_eval.py', 'browsergym_task.py', 'runner.py', 'app.py', 'manifest.json')}
    return {'repo_commit': git(['rev-parse', 'HEAD'], REPO), 'repo_dirty_files': (git(['status', '--short', '--', 'scripts/probe/breakingweb'], REPO) or '').splitlines(),
            'files': mine, 'clone_head': git(['rev-parse', 'HEAD'], ROOT), 'clone_status': (git(['status', '--short'], ROOT) or '').splitlines(),
            'clone_files': clone}


def versions():
    from importlib.metadata import version as v
    out = {'python': platform.python_version()}
    for p in ('browsergym-core', 'playwright', 'boto3', 'botocore'):
        try:
            out[p] = v(p)
        except Exception:
            out[p] = None
    return out


def step_budget(task, budget_file):
    b = json.load(open(budget_file))
    pt = b['per_task'].get(task)
    if not pt:
        raise RefuseToStart(f'task {task} has no budget in {budget_file} (not in the replay reference set)')
    return pt['cap_h1'], {'file': budget_file, 'sha256': file_sha(budget_file), 'rule': b['rule'], 'K': b['K'], 'A': b['A'],
                          'L_ref': pt['L_ref'], 'cap_design': pt['cap_design']}


def write_immutable(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, default=_jsonable)
    os.replace(tmp, path)
    os.chmod(path, 0o444)
    return file_sha(path)


def cmd_run(a, client=None, client_meta=None):
    """Returns the run directory. `client` (a fake) bypasses the real Bedrock client."""
    if a.model not in MODELS:
        raise RefuseToStart(f'model {a.model} not in the allowlist {sorted(MODELS)}')
    sys.path.insert(0, ROOT)
    import breakingweb
    mod = os.path.realpath(os.path.dirname(breakingweb.__file__))
    if not mod.startswith(ROOT + os.sep):
        raise RefuseToStart(f'breakingweb imported from {mod}, not BW_ROOT {ROOT}')
    if ROOT == SHARED_CLONE and not a.allow_shared_clone:
        raise RefuseToStart('BW_ROOT is the shared clone; run on a private copy under /tmp/amt-syn/')
    from breakingweb.tasks._registry import get_task
    tdef = get_task(a.task)
    env_id = tdef.env_id
    vm = json.load(open(a.manifest))
    bundle = check_bundle(vm, env_id, a.cell, a.expect_bundle)          # P5, before anything starts
    max_steps, budget = step_budget(a.task, a.budget_file)               # P6
    effort = a.effort or MODELS[a.model]['effort']
    if client is None:
        client, client_meta = make_real_client(a.model)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'{stamp}__{a.task}__{a.cell}__{a.model.split(".", 1)[1]}__h1__r{a.repeat}__{secrets.token_hex(3)}'
    rdir = os.path.join(a.out_root, run_id)
    os.makedirs(rdir, exist_ok=False)
    gateway = Gateway(a.model, client, effort)
    steplog, served = [], {}
    import breakingweb.agent as bwa
    H1Agent, H1Task, summary_fn = build_classes(gateway, steplog, served, vm)
    orig_llm_complete = bwa.llm_complete
    proc = log = None
    t_wall = time.time()
    result, harness_error = None, None
    try:
        proc, log = start_server(a.port, os.path.join(rdir, 'server.log'))
        bwa.llm_complete = summary_fn
        from browsergym.core.action.highlevel import HighLevelActionSet
        from browsergym.core.env import BrowserEnv
        aset = HighLevelActionSet(subsets=['bid', 'chat', 'infeas'], multiaction=False)
        env = BrowserEnv(task_entrypoint=H1Task, task_kwargs={'task_id': a.task, 'server_host': HOST, 'server_port': a.port},
                         headless=True, action_mapping=aset.to_python_code)
        agent = H1Agent(a.model)
        try:
            result = run_loop(env, agent, max_steps, served, vm, env_id)
        finally:
            env.close()
    except Exception as e:
        harness_error = f'{type(e).__name__}: {str(e)[:500]}'
    finally:
        bwa.llm_complete = orig_llm_complete
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
        if log:
            log.close()
    result = result or {'trajectory': [], 'end_reason': 'harness_error', 'forced_evaluation': {}, 'in_loop_evaluation': None}
    fe = result['forced_evaluation'] or {}
    ie = result.get('in_loop_evaluation')
    summaries = [c for c in gateway.calls if c['kind'] == 'summary']
    # join step records with trajectory entries (same order; one act per env.step except a final act that errored)
    steps = []
    for i, s in enumerate(steplog):
        t = result['trajectory'][i] if i < len(result['trajectory']) else None
        steps.append(s | {'action_parsed': t and t['action'], 'action_error': t and t['last_action_error'],
                          'status': t and t['status'], 'targets': t and t['targets'], 'url_after': t and t['url_after'],
                          'executed': t is not None})
    m1_pass = (not served.get('m1_mismatch')) and any(c['rel'] == 'index.html' and c['match'] for c in served.get('m1_checked', []))
    iso = served.get('isolation_probe') or {}
    date0 = served.get('page_date_ms_at_start')
    trace = {
        'schema': 'amt-h1-trace/1', 'run_id': run_id, 'task': a.task, 'env': env_id, 'cell': a.cell, 'harness': 'h1',
        'model': a.model, 'repeat': a.repeat, 'goal': result.get('goal'),
        'outcome': {'success': fe.get('success'), 'score': fe.get('score'), 'source': 'force_evaluate (backend state)',
                    'checks': fe.get('checks'), 'negative_checks': fe.get('negative_checks'), 'reasoning': fe.get('reasoning'),
                    'error': fe.get('error'), 'in_loop_evaluation': ie,
                    'in_loop_differs': bool(ie) and (ie.get('success') != fe.get('success') or ie.get('score') != fe.get('score'))},
        'end_reason': result['end_reason'], 'harness_error': harness_error, 'call_error': served.get('call_error'),
        'n_steps_executed': len(result['trajectory']), 'max_steps': max_steps, 'elapsed_s': result.get('elapsed_s'),
        'final_url': served.get('final_url'),
        'checks': {'m1_pass': m1_pass, 'm1_checked': served.get('m1_checked'), 'm1_mismatch': served.get('m1_mismatch'),
                   'isolation_probe_blocked': iso.get('result') == 'blocked' and iso.get('aborted_by_route'),
                   'page_date_ms_at_start': date0, 'date_shim_ok': date0 is not None and 0 <= date0 - DATE_T0 < 600000,
                   'page_date_ms_at_end': served.get('page_date_ms_at_end'),
                   'external_requests_aborted': served.get('external_aborted'),
                   'summary_calls': len(summaries), 'summary_call_failures': sum(1 for c in summaries if c.get('error')),
                   'temperature_sent_any': any(c.get('temperature_sent') is not None for c in gateway.calls),
                   'truncated_calls': sum(1 for c in gateway.calls if c.get('stop_reason') == 'max_tokens'),
                   'reasoning_visibility': sorted({c.get('reasoning_visibility') for c in gateway.calls if 'reasoning_visibility' in c})},
        'tokens': {k: sum((c.get('tokens') or {}).get(k) or 0 for c in gateway.calls) for k in ('in', 'out', 'cache_read', 'cache_write')},
        'steps': steps,
        'summary_calls': [{k: c.get(k) for k in ('i', 'step', 'prompt_sha256', 'temperature_requested', 'temperature_sent', 'text',
                                                 'reasoning', 'reasoning_visibility', 'tokens', 'latency_s', 'stop_reason', 'error', 'attempts')}
                          for c in summaries],
        'calls': [{k: v for k, v in c.items() if k not in ('text', 'reasoning', 't_start')} for c in gateway.calls],
        'messages_final': agent_messages(result, steplog),
    }
    trace_sha = write_immutable(os.path.join(rdir, 'trace.json'), trace)
    manifest = {
        'schema': 'amt-h1-manifest/1', 'run_id': run_id, 'wrapper_version': WRAPPER_VERSION,
        'trace_sha256': trace_sha, 'server_log_sha256': file_sha(os.path.join(rdir, 'server.log')),
        'started_utc': dt.datetime.fromtimestamp(t_wall, dt.timezone.utc).isoformat(timespec='seconds'),
        'wall_s': round(time.time() - t_wall, 1), 'host': platform.node(),
        'cell': {'task': a.task, 'env': env_id, 'cell': a.cell, 'repeat': a.repeat, 'harness': 'h1'},
        'bundle': bundle | {'variant_manifest': os.path.abspath(a.manifest), 'variant_manifest_sha256': file_sha(a.manifest),
                            'build': vm['build'], 'src_diff_sha256': vm['src_diff_sha256'], 'codemod_sha256': vm['codemod_sha256'],
                            'expect_bundle': a.expect_bundle},
        'model': {'id': a.model, 'family': MODELS[a.model]['family'], 'region': (client_meta or {}).get('region', MODELS[a.model]['region']),
                  'client': client_meta or {'fake': True},
                  'inference_config': {'maxTokens': gateway.max_tokens}, 'additional_model_request_fields': gateway.additional,
                  'effort': effort, 'temperature_sent': None, 'temperature_rule': TEMPERATURE_RULE[MODELS[a.model]['family']]},
        'harness': {'code': 'breakingweb.agent.LLMAgent via h1_wrapper.H1Agent', 'max_input_tokens_est': bwa.MAX_INPUT_TOKENS,
                    'max_steps': max_steps, 'step_budget': budget, 'wall_cap_s': WALL_CAP_S, 'step_timeout_s': STEP_TIMEOUT_S,
                    'viewport': [1280, 720], 'action_subsets': ['bid', 'chat', 'infeas'], 'multiaction': False},
        'isolation': {'date_shim_t0_ms': DATE_T0, 'remote_requests': 'aborted (context route)', 'bind': HOST, 'port': a.port,
                      'checkout': ROOT, 'breakingweb_module': mod},
        'seeds': {'backend_session_seed': None, 'backend_seed_note': 'None = backend default per session, as the stock harness',
                  'model_sampling_seed': None, 'model_seed_note': 'Bedrock Converse has no seed field',
                  'date_t0_ms': DATE_T0, 'run_id_random': run_id.rsplit('__', 1)[-1]},
        'code': code_hashes(), 'versions': versions(),
    }
    write_immutable(os.path.join(rdir, 'manifest.json'), manifest)
    os.chmod(os.path.join(rdir, 'server.log'), 0o444)
    with open(os.path.join(rdir, 'SHA256SUMS'), 'w') as f:
        for n in ('trace.json', 'manifest.json', 'server.log'):
            f.write(f'{file_sha(os.path.join(rdir, n))}  {n}\n')
    os.chmod(os.path.join(rdir, 'SHA256SUMS'), 0o444)
    os.chmod(rdir, 0o555)
    print(json.dumps({'run_id': run_id, 'end_reason': trace['end_reason'], 'success': trace['outcome']['success'],
                      'steps': trace['n_steps_executed'], 'max_steps': max_steps, 'm1_pass': m1_pass,
                      'tokens': trace['tokens'], 'reasoning_visibility': trace['checks']['reasoning_visibility'],
                      'harness_error': harness_error}))
    return rdir


def agent_messages(result, steplog):
    """The untrimmed history as the agent kept it: system, then observation/action pairs (reconstructable)."""
    return {'n_steps': len(steplog), 'note': 'observation texts are steps[i].observation_text; assistant turns are steps[i].action; '
            'system prompt = breakingweb.agent.SYSTEM_PROMPT (sha256 in system_prompt_sha256)',
            'system_prompt_sha256': _sys_sha()}


def _sys_sha():
    import breakingweb.agent as bwa
    return sha256_text(bwa.SYSTEM_PROMPT)


# ----------------------------------------------------------------------------- observer packet (blinding)
def make_packet(trace_dir, out, key_file=None, with_outcome=False):
    """What the observer sees (studies/v2-pilot/TRACE-CODING.md §2): goal, steps (URL, observation text,
    summary marker, reasoning text, model text, action, error), end reason. Removed: cell, run id, repeat,
    bundle and manifest, codemod, date. The model id is removed too (the observer could otherwise learn the
    model's habits across packets and read cells from deviations). The evaluator verdict is added only with
    `with_outcome` (pass B). The packet id is random; the key file maps it back to the trace sha256 and is
    never shown to observers."""
    tr = json.load(open(os.path.join(trace_dir, 'trace.json')))
    tsha = file_sha(os.path.join(trace_dir, 'trace.json'))
    pid = 'P' + secrets.token_hex(5)
    pk = {'packet_id': pid, 'pass': 'B' if with_outcome else 'A', 'task': tr['task'], 'env': tr['env'], 'goal': tr['goal'],
          'end_reason': tr['end_reason'], 'n_steps': tr['n_steps_executed'], 'max_steps': tr['max_steps']}
    if with_outcome:
        pk['evaluator'] = {'success': tr['outcome']['success'], 'score': tr['outcome']['score'],
                           'checks': tr['outcome']['checks'], 'negative_checks': tr['outcome']['negative_checks'],
                           'final_url': tr.get('final_url')}
    pk |= {
          'steps': [{'step': s['step'], 'url': s['url'], 'observation_text': s['observation_text'],
                     'summary_marker_text': s['summary_marker_text'], 'reasoning_visibility': s['reasoning_visibility'],
                     'reasoning_text': '\n'.join(r['text'] for r in s['reasoning'] if r['kind'] == 'text'),
                     'model_text': s['model_text'], 'action': s['action'], 'action_error': s['action_error'],
                     'stop_reason': s['stop_reason'], 'executed': s['executed']} for s in tr['steps']]}
    json.dump(pk, open(out, 'w'), indent=1, ensure_ascii=False)
    if key_file:
        with open(key_file, 'a') as f:
            f.write(json.dumps({'packet_id': pid, 'pass': pk['pass'], 'trace_sha256': tsha, 'run_id': tr['run_id'],
                                'cell': tr['cell'], 'model': tr['model']}) + '\n')
    return pid


# ----------------------------------------------------------------------------- probe (request shape, live)
PROBE_PROMPT = ('What is the sum of all prime numbers p < 300 such that p + 2 is also prime? Check your work, '
                'then reply with the number only.')   # needs multi-step work, so adaptive reasoning engages


def cmd_probe(a):
    out = []
    for m in a.models:
        try:
            client, meta = make_real_client(m)
        except RefuseToStart as e:
            print(json.dumps({'model': m, 'refused': str(e)})); return
        variants = [('wrapper default', reasoning_fields(m, MODELS[m]['effort']))]
        if MODELS[m]['family'] == 'openai' and a.variants:
            variants += [('reasoning.summary=auto', {'reasoning': {'effort': MODELS[m]['effort'], 'summary': 'auto'}}),
                         ('reasoning.summary=detailed', {'reasoning': {'effort': MODELS[m]['effort'], 'summary': 'detailed'}}),
                         ('reasoning.summary=bogus', {'reasoning': {'effort': MODELS[m]['effort'], 'summary': 'bogus-level'}})]
        for name, add in variants:
            kw = {'modelId': m, 'messages': [{'role': 'user', 'content': [{'text': PROBE_PROMPT}]}],
                  'inferenceConfig': {'maxTokens': 8000}, 'additionalModelRequestFields': add}
            t0 = time.time()
            try:
                r = client.converse(**kw)
                text, reasoning, vis = parse_blocks(r['output']['message']['content'])
                rec = {'model': m, 'variant': name, 'accepted': True, 'stop_reason': r.get('stopReason'), 'usage': r.get('usage'),
                       'block_types': [next(iter(b)) for b in r['output']['message']['content']], 'text': text[:200],
                       'reasoning_visibility': vis, 'reasoning_chars': sum(len(x.get('text', '')) for x in reasoning),
                       'reasoning_head': next((x['text'][:300] for x in reasoning if x['kind'] == 'text' and x['text']), None),
                       'latency_s': round(time.time() - t0, 2), 'region': meta['region'], 'credential_method': meta['credential_method']}
            except Exception as e:
                msg = str(e)
                rec = {'model': m, 'variant': name, 'accepted': False, 'error': f'{type(e).__name__}: {msg[:300]}'}
                if 'Token' in msg and ('expired' in msg.lower() or 'credential' in msg.lower()):
                    print(json.dumps(rec)); print('credential failure: stopping LLM work'); return
            print(json.dumps(rec, ensure_ascii=False)); out.append(rec)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(out, open(a.out, 'w'), indent=1, ensure_ascii=False)


# ----------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sp = ap.add_subparsers(dest='cmd', required=True)
    r = sp.add_parser('run')
    r.add_argument('--task', required=True); r.add_argument('--cell', required=True); r.add_argument('--model', required=True)
    r.add_argument('--manifest', required=True); r.add_argument('--repeat', type=int, default=0)
    r.add_argument('--expect-bundle'); r.add_argument('--effort')
    r.add_argument('--budget-file', default=DEFAULT_BUDGET); r.add_argument('--port', type=int, default=8401)
    r.add_argument('--out-root', default='/tmp/amt-syn/traces'); r.add_argument('--allow-shared-clone', action='store_true')
    m = sp.add_parser('manifest')
    m.add_argument('--env', required=True); m.add_argument('--build', required=True); m.add_argument('--out', required=True)
    m.add_argument('--codemod')
    p = sp.add_parser('packet')
    p.add_argument('trace_dir'); p.add_argument('out'); p.add_argument('--key-file')
    p.add_argument('--with-outcome', action='store_true', help='pass B packet (evaluator verdict shown)')
    q = sp.add_parser('probe')
    q.add_argument('--models', nargs='+', default=['us.anthropic.claude-sonnet-5-5', 'us.openai.gpt-5.6-sol'])
    q.add_argument('--out'); q.add_argument('--variants', action='store_true', help='GPT: also try summary auto/detailed/bogus')
    a = ap.parse_args(argv)
    if a.cmd == 'manifest':
        vm = make_variant_manifest(ROOT, a.env, a.build, a.codemod)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(vm, open(a.out, 'w'), indent=1)
        print(json.dumps({k: vm[k] for k in ('env', 'build', 'bundle', 'bundle_fx6', 'src_diff_sha256')} | {'n_files': len(vm['files'])}))
    elif a.cmd == 'run':
        try:
            cmd_run(a)
        except RefuseToStart as e:
            print(json.dumps({'refused': str(e)})); sys.exit(3)
    elif a.cmd == 'packet':
        print(make_packet(a.trace_dir, a.out, a.key_file, a.with_outcome))
    elif a.cmd == 'probe':
        cmd_probe(a)


if __name__ == '__main__':
    main()
