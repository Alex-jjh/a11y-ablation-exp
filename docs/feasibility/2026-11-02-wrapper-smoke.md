# H1 wrapper smoke test with real models (2026-11-02)

> **Summary:** Engineering check, not data. Eight episodes ran through `h1_wrapper.py` (sha256 f1342dbe1035d706, unchanged) with Sonnet 5.5 and GPT-5.6-sol on two reference tasks outside the pilot sample and the sealed set. Each task ran on the clean build and on one variant: `gmail_access_review_audit` (names strictly on path) on `names`, and `pp_medication_conflict` (labels strictly on path) on `labels`. The wrapper did what it is meant to do in all 8 runs. Every trace is complete, and all 239 prompt hashes were recomputed from the traces alone. The forced evaluator verdict is stored in every run. M1 passed, the isolation self-check passed, no temperature was sent, all 207 summary calls succeeded, and the sources were restored. The removed names and labels reached the agent. The smoke test found four problems, none of them in the wrapper's core logic. (1) Sonnet 5.5 writes Anthropic tool-call XML (`<invoke name="click">…`) instead of the Python action the system prompt asks for, in 86 of 170 steps (51%). 68 of those steps became action errors. On `pp_medication_conflict` both Sonnet runs ran out of steps (45 of 45), with 21 format errors each. GPT-5.6 did this in 0 of 69 steps. (2) `--expect-bundle` cannot use design.yaml's gmail and patient_portal hashes, because the wrapper hard-codes the `bw-fx-src6` path prefix. The built bytes are identical to the replay record's. (3) GPT-5.6's Converse usage leaves its reasoning tokens out of `outputTokens` and reports most input as cache read or cache write, so its cost cannot be read from the trace. (4) The backend's wall-clock time appears in the observation. Cost per step at list price: Sonnet 5.5 $0.056 (Anthropic list price; Bedrock price [unverified]). GPT-5.6-sol $0.025 to $0.049 at the placeholder price, before its unreported reasoning tokens [unverified]. Total spend about $13.

Question served: does the H1 wrapper work end to end with the two pilot models, on a real task, on a variant build, with several runs at once, before Stage 0s? Model rule: only Bedrock via `codex-DO-NOT-DELETE`. No Gemini call was made. Nothing was committed. The paper repository, DESIGN, design.yaml and the wrapper were not edited.

## 1. Credentials

One 16-token Converse call per model through the wrapper's own client factory (`make_real_client`). Output: `/tmp/amt-syn/h1-smoke/cred_check.json`.

| Model id (works) | Region | Credential method | Result |
|---|---|---|---|
| `us.anthropic.claude-sonnet-5-5` | us-west-2 | custom-process (no bearer token) | `OK`, end_turn, 18 in / 4 out |
| `us.openai.gpt-5.6-sol` | us-east-2 | custom-process | `OK`, end_turn, 13 in / 5 out |

The Sonnet 5.5 id the task proposed is the one that works. It is already in the wrapper's allowlist.

## 2. Task and build choice

| Choice | What | Grounds | How it could be wrong | What would change it |
|---|---|---|---|---|
| Pool | Replay reference set (195) minus the sample and the sealed tasks (152): 43 tasks | `studies/v2-pilot/select.json`; `docs/feasibility/2026-10-30-replay-feasibility.json` `matrix` | None for the smoke purpose | — |
| names task | `gmail_access_review_audit`: names on path and strict (8 changed instances on the Gemini route), labels on path but not strict; `names` cell feasible by replay; panel 3 of 6; L_ref 14, cap 60 | `docs/feasibility/2026-10-30-on-path-dose.json` `tasks[...].kinds`; `/tmp/amt-syn/h1/budget.json` | Strictness comes from the replay of one Gemini route. Another route could avoid the change | — |
| labels task | `pp_medication_conflict`: labels strict (4), names not strict; `labels` feasible; panel 3 of 6; L_ref 13, cap 45 | same | same | — |
| Why these two | They are the shortest strict tasks for each kind outside the sample and the sealed set. The shortest is cheapest, and a short task makes a budget-only failure easy to see | ours | A short task does not stress the history trim or the 120 s timeout | A Stage 0s run on a long task |
| Builds | Three private copies of `/tmp/amt-syn/h1-test/BreakingWeb` (release 052f0f0 + the four bind diffs): `clean` (gmail and patient_portal clean), `gmail-names`, `pp-labels`. Built with `codemod.py` (sha256 02b3190ff81d153f) on env + shared sources, `pnpm build`, then `h1_wrapper.py manifest` | Run recipe; `/tmp/amt-syn/h1-smoke/build.sh` | — | — |

Built bundles against the replay record (observed). The wrapper's path-free `bundle` hashes are gmail clean 9c7744c75667b4a0, gmail names 705d80882958c27e, pp clean b9b79205c2100ebe and pp labels 5789bbd5ce7eb4a9. Its `bundle_fx6` values (4e6ba057845f7c34, 14d1b7be5421d2cd, 14524144610349a2, b8c28115c2ec986b) do not equal design.yaml's (7634cb0da104cfb3, 3f9075b3e8fd7f10, 5a2e2af83a8f814b, 0d5461daf71105ff). Recomputing the record's formula over the same bytes, with the prefix of the checkout each env was built in, reproduces all four design.yaml values exactly: `bw-fx-src3` for gmail and `bw-fx-src5` for patient_portal (`/tmp/amt-syn/h1-smoke/prefix_check.py`). The builds are byte-identical to the gated and replayed ones; only the hash formula differs (§5, W1).

## 3. Runs (observed, n = 8, one repeat each)

Four sequences ran at once: one per copy, plus a second sequence on the `clean` copy for the other env. Each run had its own backend on its own port (8411-8442, 127.0.0.1 only). Wrapper defaults were used: Sonnet 5.5 effort `high`; GPT-5.6 effort `medium` and `reasoning.summary: detailed`; maxTokens 16,384; no temperature. Started 04:48:29Z, all done by 04:59Z.

| Task | Cell | Model | Outcome (forced evaluator) | End | Steps / cap | Action errors | Steps with tool-call XML | Reasoning per step | Summary calls | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|
| gmail_access_review_audit | clean | Sonnet 5.5 | success 1.0 (3 checks, 8 negative) | agent_finished | 34 / 60 | 10 | 14 | summary 11, none 23 | 24 | 186 |
| gmail_access_review_audit | names | Sonnet 5.5 | success 1.0 | agent_finished | 46 / 60 | 16 | 23 | summary 27, none 19 | 36 | 307 |
| pp_medication_conflict | clean | Sonnet 5.5 | fail 0.0 ("no candidate satisfied predicates") | step_cap | 45 / 45 | 23 (21 XML) | 24 | summary 40, none 5 | 40 | 548 |
| pp_medication_conflict | labels | Sonnet 5.5 | fail 0.0 (same check) | step_cap | 45 / 45 | 23 (21 XML) | 25 | summary 42, none 3 | 30 | 388 |
| gmail_access_review_audit | clean | GPT-5.6-sol | success 1.0 | agent_finished | 14 / 60 | 0 | 0 | summary 12, encrypted 2 | 1 | 47 |
| gmail_access_review_audit | names | GPT-5.6-sol | success 1.0 | agent_finished | 20 / 60 | 0 | 0 | summary 13, encrypted 6, none 1 | 15 | 99 |
| pp_medication_conflict | clean | GPT-5.6-sol | success 1.0 | agent_finished | 19 / 45 | 1 (select timeout) | 0 | summary 18, encrypted 1 | 1 | 76 |
| pp_medication_conflict | labels | GPT-5.6-sol | success 1.0 | agent_finished | 16 / 45 | 0 | 0 | summary 13, encrypted 3 | 0 | 57 |

Trace files (each directory also holds `manifest.json`, `server.log`, `SHA256SUMS`):

- `/tmp/amt-syn/traces/20261102T044834Z__gmail_access_review_audit__clean__anthropic.claude-sonnet-5-5__h1__r0__978d3b/trace.json`
- `/tmp/amt-syn/traces/20261102T044834Z__gmail_access_review_audit__names__anthropic.claude-sonnet-5-5__h1__r0__ae10c3/trace.json`
- `/tmp/amt-syn/traces/20261102T044834Z__pp_medication_conflict__clean__anthropic.claude-sonnet-5-5__h1__r0__8ce407/trace.json`
- `/tmp/amt-syn/traces/20261102T044834Z__pp_medication_conflict__labels__anthropic.claude-sonnet-5-5__h1__r0__c9451a/trace.json`
- `/tmp/amt-syn/traces/20261102T045151Z__gmail_access_review_audit__clean__openai.gpt-5.6-sol__h1__r0__eebf10/trace.json`
- `/tmp/amt-syn/traces/20261102T045352Z__gmail_access_review_audit__names__openai.gpt-5.6-sol__h1__r0__88c5eb/trace.json`
- `/tmp/amt-syn/traces/20261102T045514Z__pp_medication_conflict__labels__openai.gpt-5.6-sol__h1__r0__76d8f6/trace.json`
- `/tmp/amt-syn/traces/20261102T045753Z__pp_medication_conflict__clean__openai.gpt-5.6-sol__h1__r0__5bb0c2/trace.json`

These are 8 single runs of 2 tasks. Success rates, model comparisons and clean-versus-variant differences are not read from them.

## 4. The checks the task asked for

| Check | Result (observed) | How it was checked | How it could be wrong |
|---|---|---|---|
| Complete trace | 8 of 8. Every step has URL, observation text, prompt hash and digest, reasoning blocks and visibility, model text, action, error, tokens, latency, stop reason | `/tmp/amt-syn/h1-smoke/analyze.py` → `analysis.json` | — |
| Trace reproducible | 239 of 239 prompt hashes recomputed from trace + manifest alone (`h1_selftest.recompute_prompt_sha`) | `/tmp/amt-syn/h1-smoke/recompute.py` | — |
| Immutability | All files read-only; SHA256SUMS valid in 8 of 8 | analyze.py | — |
| Reasoning stored | Every reasoning block is stored per call. Sonnet: readable summary on 120 of 170 steps; the other 50 have no reasoning block, because adaptive thinking skipped the turn (as in the probe, record 2026-11-02-h1-wrapper §2). GPT: summary on 56 of 69 steps, encrypted only on 12, none on 1, despite `summary: detailed` | per-step `reasoning_visibility` | The reason a GPT step returns only an encrypted block is not known (inferred: short reasoning gets no summary) |
| Evaluator stored | 8 of 8: `force_evaluate` verdict, checks and the 8 negative checks. `in_loop_differs` false in all 6 runs that declared done | trace `outcome` | — |
| Bundle hash | Pre-run check passed (on-disk tree = manifest) and M1 passed during the run (index.html + 2 assets hashed against the manifest) in 8 of 8. `--expect-bundle` was not used: see W1 | trace `checks.m1_*` | M1 hashes only what the browser fetched, 3 files per env, which is the whole bundle here |
| Isolation | Date shim and the remote-abort self-check passed in 8 of 8; 0 external requests aborted during the runs | trace `checks` | The backend clock still shows (W4) |
| Request fields | `temperature_sent_any` false; 0 of 207 summary calls failed; 0 retries; no throttling with 4 runs at once | trace `checks`, `calls` | — |
| Defect delivered | gmail names: 125 (GPT) and 265 (Sonnet) `button ''`-type lines in the observations, 0 on clean; for example `button 'Star Follow-up on venue estimate'` became `button ''`. pp labels: the appointment form's `combobox 'Select provider'` / `'Select appointment slot'` / `'Select appointment type'` became `combobox ''`, 28 and 49 lines, 0 on clean | observation diff, clean vs variant | Counts include repeats across steps |
| No budget-only failure | 6 of 8 runs ended by the agent, with steps to spare (GPT used 14-20 of 45-60; Sonnet on gmail 34 and 46 of 60). The 2 Sonnet `pp` runs hit the cap, but not on budget alone: 21 of 45 steps in each were format errors (W2), and the summaries show a loop of doubt. The correct provider is the oddly named "Claims Office", which Sonnet called "a data glitch" on most steps and selected only at steps 35 and 40. GPT picked it and succeeded on both builds | step log, reasoning text | Whether 15 more steps would have saved the Sonnet runs is unknown. The codebook's F4 (stopped on route) and E4 (loop) are for the observer to code, not this record |
| Sources restored | Both variant copies restored with `git checkout` and rebuilt clean. Each rebuilt bundle equals the clean manifest (gmail 9c7744c75667b4a0, pp b9b79205c2100ebe). All three copies and the shared clone show only the four bind diffs | `git status`, `manifest --build clean` | — |
| 120 s step timeout | Not reached. Longest agent call 72.5 s: a Sonnet runaway that repeated `<invoke name="scroll">` until maxTokens 16,384 (2 calls, `pp` clean steps 3 and 5) | trace `calls` | At lower Bedrock throughput the same runaway would pass 120 s and end the run as `step_timeout` |
| Blinded packet | `packet` ran on all 8 traces; no cell, model, run id or repeat field is present | `/tmp/amt-syn/h1-smoke/packets/` | Content leaks the condition, see W5 |

## 5. Problems found

| # | Problem (observed) | Grounds | Consequence | Proposed fix | What would change the decision |
|---|---|---|---|---|---|
| W1 | `bundle_fx6` uses the `bw-fx-src6` path prefix for every env. design.yaml's hashes were made in different checkouts per env (src3 gmail, src5 patient_portal, src6 reddit), so `--expect-bundle <design.yaml value>` refuses gmail and patient_portal builds that are byte-identical to the gated ones | prefix recomputation in §2 | M1 against design.yaml cannot run as written for 2 of 3 envs checked (the other envs not checked) | Record path-free content hashes (the wrapper's `bundle`, or a hash over sorted per-file sha256) for every frozen build in design.yaml and compare those. Keep the old values only as a cross-reference | None; a path inside a content hash is a defect |
| W2 | Sonnet 5.5 answers with tool-call XML instead of the Python call the system prompt asks for ("Respond with a single Python function call… no markdown"). 86 of 170 steps (51%) contained `<invoke`. 68 became `ValueError: Received an empty action` or another action error, and each costs a step. After such an error, the next step was XML again in 21 of 69 cases. It happens with and without a reasoning block (70 of 120 steps with a summary, 16 of 50 without). GPT-5.6: 0 of 69. Opus 5.5 in the 2026-10-30 smoke (stock harness, no `display` field): 0 occurrences in 30 steps | traces; `/tmp/amt-syn/bw-smoke/out/*/episode.json` | For Sonnet 5.5, H1 success then measures format compliance as much as task skill. It also spends about half the step budget, which interacts with the cap. The extra steps fall on all cells alike, but if Sonnet is the pilot model, run variance and the variance components that size the main study would be inflated. The cause is inferred: Sonnet 5.5 defaults to its trained tool-call form when a prompt lists functions and no `tools` field is sent. Whether `display: "summarized"` or effort `high` contributes is [unverified] | Decide before Stage 0 (Alex): (a) keep the stock harness and treat format failures as the model's behaviour, coded H2, with the cap raised by the measured waste; (b) add a parser in the wrapper that maps a single `<invoke name=X><parameter …>` to `X(...)`, a logged harness change applied to every model and cell; (c) use GPT-5.6 / Opus 5.5 for H1 as DESIGN states. A cheap check first: replay about 20 recorded Sonnet prompts with effort `medium` and with `display` omitted, and count XML replies (about $1) | If XML drops below 5% under some field setting, use that setting. If not, (b) is the smallest change that keeps H1 a test of the page, not of output format |
| W3 | GPT-5.6 usage on Bedrock: `inputTokens` holds only the uncached part (2 tokens per call). The rest is reported as `cacheReadInputTokens` and `cacheWriteInputTokens`, without the wrapper sending any cache point. `outputTokens` is 23-44 on calls that return a 272-character reasoning summary, so reasoning tokens are not in `outputTokens` (inferred). The wrapper's note "not reported by Converse; included in out" is true for Claude and not for GPT | traces `calls[].usage` | GPT cost is under-counted by an unknown amount; the cost model must sum in + cache read + cache write | Fix the per-family note in the wrapper. Read the true billed tokens from AWS billing (Cost Explorer, or the Bedrock invocation log) for these 4 runs before the GPT price in cost.json is set | If billing shows reasoning tokens charged at the output rate, GPT's cost per step rises by about (reasoning tokens x $20/M); recompute cost.json |
| W4 | The backend's clock appears in what the agent sees: `gridcell 'Booked at 11/2/2026, 4:56:12 AM'` after booking. The Date shim fixes only the page's `Date` | trace observation text | Observation text, and so prompt hashes, differ by run time. Date-relative backend logic ("next available slot") could drift across run days. This was already known from the on-path record §6, but it is now seen in the agent's input | Keep day-blocking as the control (DESIGN). Log the backend time per run. A backend clock shim is a clone edit, so it is Alex's call | A Stage 0s pair of runs on different days that shows a different "next available slot" on the same task |
| W5 | Packets hide the condition fields, but the content reveals model and setup: Sonnet's `<invoke>` XML and GPT's bold-heading summaries identify the model, and the URL in each observation carries the port (`127.0.0.1:8442`). In this smoke the port was fixed per copy, so it mapped to the cell | packets in `/tmp/amt-syn/h1-smoke/packets/` | Observers could learn the cell from the port | Draw ports at random per run, or rewrite `127.0.0.1:<port>` to a fixed token in the packet. Model identity cannot be hidden from content; record it as a known limit in TRACE-CODING §2 | — |

## 6. Tokens and cost per step

Prices. Sonnet 5.5: $2 input / $10 output / $0.20 cache read per million tokens, the Anthropic first-party list price (claude-api reference, cached 2026-10-06); the Bedrock price is [unverified]. No cache tokens were used, because the wrapper sends no cache point, as in the stock harness. GPT-5.6-sol: $4 / $20, the DESIGN §9 placeholder [unverified]. The cache-read price is unknown, so two values are shown: all input-side tokens at $4 (upper bound for input), and cache read at 0.1x. Both exclude GPT's unreported reasoning tokens (W3).

| Run | Steps | Input-side tokens / step | Output tokens / step | Summary calls | Cost | Cost / step | GPT cost / step, cache read at 0.1x |
|---|---|---|---|---|---|---|---|
| gmail clean, Sonnet 5.5 | 34 | 23,694 | 327 | 24 | $1.72 | $0.051 | — |
| gmail names, Sonnet 5.5 | 46 | 24,212 | 437 | 36 | $2.43 | $0.053 | — |
| pp clean, Sonnet 5.5 | 45 | 25,599 | 1,405 | 40 | $2.94 | $0.065 | — |
| pp labels, Sonnet 5.5 | 45 | 23,744 | 674 | 30 | $2.44 | $0.054 | — |
| gmail clean, GPT-5.6-sol | 14 | 11,836 | 48 | 1 | $0.68 | $0.048 | $0.019 |
| gmail names, GPT-5.6-sol | 20 | 14,118 | 141 | 15 | $1.19 | $0.059 | $0.054 |
| pp clean, GPT-5.6-sol | 19 | 11,141 | 130 | 1 | $0.90 | $0.047 | $0.014 |
| pp labels, GPT-5.6-sol | 16 | 9,186 | 105 | 0 | $0.62 | $0.039 | $0.009 |

Per model (summary calls included):

- **Sonnet 5.5**, 170 steps: 24,352 input and 734 output tokens per step, $0.056 per step, $9.53 in total. Summary calls are 5.6% of input tokens and add 461 s of latency over 130 calls, because a run over the 26,000-token trim threshold makes a summary call on every later step. Median agent-call latency is 1.5-5.5 s.
- **GPT-5.6-sol**, 69 steps: 11,692 input-side and 111 output tokens per step (reasoning excluded). Cost per step is $0.025 to $0.049 at the placeholder price, $1.76 to $3.38 in total.
- Sonnet's input per step is 2.2 times the cost model's 10.9k (cost.json `bg_input_tokens / bg_steps`). Its runs are longer (34-46 steps against GPT's 14-20), so the history sits near the trim cap.
- Total spend of this smoke: about $13, plus the 2 credential calls.

## 7. Decisions for Alex

1. **W2, Sonnet 5.5 format failures.** Choose (a) stock behaviour, (b) a logged `<invoke>` parser for all models, or (c) a different H1 model. Proposed: run the $1 replay check of request fields first, then (b) if XML persists. This bears on the choice of Sonnet 5.5 for the pilot.
2. **W1, bundle hashes.** Re-key design.yaml `bundles_sha256_prefix` to path-free content hashes before Stage 0 hashes are frozen (proposed).
3. **W3, GPT cost.** Read the billed tokens of the 4 GPT runs (2026-11-02 04:51-04:59Z, us-east-2) from AWS billing before cost.json is recomputed.
4. **W5, packets.** Draw ports at random per run, or mask the host:port in packets (proposed: mask).

## 8. Files

| File | What |
|---|---|
| `/tmp/amt-syn/h1-smoke/cred_check.py`, `cred_check.json` | Credential check |
| `/tmp/amt-syn/h1-smoke/build.sh`, `vm-*.json`, `codemod-*.txt`, `build-*.log` | Builds and variant manifests |
| `/tmp/amt-syn/h1-smoke/runseq.sh`, `seq-*.log` | Episode driver and wrapper output |
| `/tmp/amt-syn/h1-smoke/analyze.py`, `analysis.json` | Per-trace checks, tokens, cost |
| `/tmp/amt-syn/h1-smoke/recompute.py` | Prompt-hash recomputation |
| `/tmp/amt-syn/h1-smoke/prefix_check.py` | Bundle-prefix check (W1) |
| `/tmp/amt-syn/h1-smoke/packets/` | Blinded pass-A packets and key file |
| `/tmp/amt-syn/h1-smoke/{clean,gmail-names,pp-labels}/BreakingWeb` | Private copies, restored to clean |
