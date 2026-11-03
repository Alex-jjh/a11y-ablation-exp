# Pipeline smoke test: BrowserGym agent on Bedrock, clean build and one variant (2026-10-30)

> **Summary:** Engineering check, not data. Two episodes ran with BreakingWeb's own BrowserGym agent (`breakingweb/agent.py`, provider `bedrock`, `us.anthropic.claude-opus-5-5`, us-west-2, profile `codex-DO-NOT-DELETE`, no bearer token) on `reddit_compose_message`: one on the clean build and one on the `labels` variant, 15 steps each. The pipeline works. Both runs completed without a call error. Steps and per-call tokens were logged. The variant served to the browser is byte-identical to the build on disk and to the replay record's `labels` bundle. The removed label reached the agent: the recipient box read `textbox 'Recipient username'` on clean and `textbox 'To: u/username'` on the variant. The sources were restored afterwards. Both runs hit the 15-step cap before sending the message, and both scored 0. Cost was $1.07 and $1.06 per episode ($0.071 per step) at the $4/$20 list price, with no prompt caching. The pilot's cost model underestimates input tokens by 1.77x for this case. Four harness problems need a fix before Stage 0s: (1) the history-summary call fails on every try because Opus 5.5 rejects `temperature`; (2) `run_episode` throws away the evaluator result of a failed run; (3) Opus 5.5 thinks by default and the clone drops the reasoning blocks; (4) the stock `make_env` has no Date shim and does not abort remote requests.

Question served: does the H1 pipeline of the v2 pilot (`studies/v2-pilot/DESIGN.md` §3, Stage 0s in §7) run end to end on Bedrock, deliver the variant it claims, score the final backend state, and cost what `cost.json` says? Model rule: only Bedrock Anthropic/OpenAI models through `codex-DO-NOT-DELETE`. The published Gemini runs were used only as recorded data, to pick the task. No Gemini call was made.

Script: `scripts/probe/breakingweb/pipeline_smoke.py` (`run TASK ARM OUT`, `served TASK ARM OUT`; the docstring states inputs, outputs and how to run). Outputs: `/tmp/amt-syn/bw-smoke/out/` (regenerable; `reddit_compose_message__{clean,labels}/episode.json` hold the full conversation, every LLM call and the trajectory). Summary JSON next to this record: [`2026-10-30-pipeline-smoke.json`](2026-10-30-pipeline-smoke.json).

## 1. What ran

- **Checkout.** A private copy, `/tmp/amt-syn/bw-smoke/BreakingWeb` (copied from `/tmp/amt-syn/bw-fx-src6/BreakingWeb`, release `052f0f0` plus the four bind fixes). The shared clone `~/.workspace/_refsrc/BreakingWeb` was not built or edited, and its `git status` still shows only the four bind diffs. The backend was started by the harness's own `BreakingWebTask._ensure_server` on 127.0.0.1:8391.
- **Task.** `reddit_compose_message`, chosen by these rules:
  - it is in the replay reference set (3/3 clean replays; `2026-10-30-replay-feasibility.json` `matrix`);
  - it is outside the pilot pool, sample and sealed set (panel tier B, 3 of 6 published models solved it; `studies/v2-pilot/select.json`), so no pilot or main-study task was touched. DESIGN Stage 0s also uses tasks outside the pool;
  - the `labels` kind is on its path (on-path dose JSON: labels 3, names 2; the Gemini run fills `textbox 'Recipient username'`);
  - it is short (expected_steps 7; Gemini needed 4 browser-use steps).
- **Variant.** `labels`, which passed the variant gate on reddit (`2026-10-30-variant-gate.json`: PASS, 37 DOM targets, 22 visible observation lines). The codemod made 36 control aria-label and 11 `htmlFor` changes in the env, plus 5 and 1 in the shared sources.
- **Agent.** `LLMAgent(model='us.anthropic.claude-opus-5-5', provider='bedrock')` and `agent_eval.run_episode(max_steps=15, timeout_seconds=1800)`, both as shipped. The step cap is 15 as instructed. The pilot's rule, 1.5 x expected_steps, would give 10 here.
- **Added around the harness (logging and isolation only; the request fields are unchanged).**
  - A pass-through proxy on the boto3 client logs each Converse call: the fields sent, latency, stopReason, usage and the content block types returned.
  - A `BreakingWebTask` subclass installs the replay's Date shim (2026-10-30T09:00Z) and aborts requests to hosts other than 127.0.0.1, as DESIGN §3 fixes. It records which JS/CSS assets the browser loaded and compares their bytes with disk, and it keeps the result of `force_evaluate`.
  - The shipped `make_env` does neither of these isolation steps.

## 2. Checks

| Check | Question | Grounds | How it could be wrong | What would change a decision | Result (observed) |
|---|---|---|---|---|---|
| Credentials | Does `agent.py` reach Bedrock through the profile, not a bearer token? | `agent.py` `create_client`: it sets `AWS_BEARER_TOKEN_BEDROCK` only if an API key is passed or `AWS_BEDROCK_API_KEY` is set; region from `AWS_BEDROCK_REGION`, default us-east-1 | An inherited env var sets the bearer path silently | Any bearer use: stop, the profile rule is broken | Both vars unset before and after the client was built; boto3 credential method `custom-process` (the profile's credential process), SigV4, region us-west-2. No credential value was read or printed |
| Run completes | Does an episode run to its end without harness errors? | ours | — | A crash or a call error would block Stage 0s | 2 of 2 episodes ran 15 steps; 30 of 30 agent calls returned `end_turn`; 0 action errors |
| Steps and tokens logged | Is there per-step usage for cost and truncation checks? | DESIGN §3 (the clone discards usage, `agent.py:222-266`) | Usage missing for some calls | Without usage, Stage 0s's cost and truncation gates cannot run | Usage on every successful call (input, output, cache read/write); stopReason on every call; the clone itself keeps none of this |
| Evaluator scores the final state | Is the score the backend evaluator's verdict on the final state, not the agent's claim? | `browsergym_task.force_evaluate`; replay record §1.2 | The episode record shows a placeholder instead of the evaluator | If the score is not from the evaluator, every failed run would be unscored | Variant run: the forced evaluation ran on the final state: `missing_create`, 0/1 checks, all 8 negative checks pass, score 0. Clean run: the forced evaluation also ran (by the code path), but `run_episode` dropped its result (problem 2), so the episode JSON shows "Agent did not finish". Its final state was the same: the message was never sent (the last action filled the subject) |
| Variant is the one served | Did the browser get the variant build? | replay record (bundle hashes); variant-gate residual check | Stale bundle, a server importing another checkout, or the SPA served from cache | A mismatch makes the run a delivery defect (DESIGN §8, M1) | Bundle `0ef6e9b8a8124fb9` in the replay record's formula = replay `labels` bundle; the loaded JS is byte-identical to disk, has 78 `aria-label` (clean 108) and 5 `htmlFor` (clean 17), and no `Recipient username` string (clean has it). `breakingweb` imported from the private copy, cwd = the copy. Clean: bundle `365a1921a7ad805b` = replay clean; loaded assets = disk (no-LLM `served` check on the same build, because the in-episode check of the clean run had a URL bug, fixed before the variant run) |
| Treatment reaches the agent | Does the agent's observation show the defect? | variant-gate observation rule for labels | — | No change on path: the cell is a no-op for this task | The recipient textbox the agent filled: clean `textbox 'Recipient username'`, variant `textbox 'To: u/username'` (the placeholder becomes the name) |
| Isolation | Date fixed, remote requests aborted? | DESIGN §3; replay record §1.2 | The init script is installed too late for the first page | Date drift between arms | Page `Date.now()` at start = 2026-10-30T09:00:00.57Z in both runs; 0 remote requests |
| Sources restored | Is the checkout clean afterwards? | run recipe | An interrupted run leaves the codemod in place | Any extra diff: rebuild before any later run | After each episode: restore, then rebuild; `git status` = the four bind diffs only; bundle after restore = clean `365a1921a7ad805b` |

## 3. Tokens and cost (observed, n = 2 episodes, 30 agent calls)

Price: Anthropic first-party list price for Opus 5.5, $4 input and $20 output per million tokens (the claude-api reference, cached 2026-10-06). The Bedrock price is [unverified], as in DESIGN §9.

| | clean | labels |
|---|---|---|
| steps (cap 15) | 15 | 15 |
| LLM calls (agent / summary) | 17 (15 / 2, both summary calls failed) | 17 (15 / 2, both failed) |
| input tokens | 258,742 | 253,400 |
| output tokens | 1,883 | 2,295 |
| cache read tokens | 0 | 0 |
| cost | $1.073 | $1.060 |
| cost per step | $0.0715 | $0.0706 |
| input per step: step 1, step 11, plateau | 3,290 / 24,772 / 26,395-27,775 | 3,291 / 23,247 / 26,275-27,624 |
| output per step: mean, max | 126, 333 | 153, 420 |
| calls with a reasoning block | 11 of 15 | 13 of 15 |
| latency per call, mean | 3.0 s | 3.1 s |
| episode wall clock | 67 s | 68 s |

Per-step rows (action, target, tokens, cost, latency, block types): `arms.<arm>.per_step` in the JSON.

- Input grows by about 2,200 tokens per step until `trim_messages` cuts the history at 26,000 *estimated* tokens (len/2.5). The real token count at that cut is about 27,500. The observation text tokenizes at 2.31-2.35 characters per token on all 30 calls.
- **Against the cost model (observed vs `pilot_plan.py`).** `pilot_plan.py` assumes 3.3 characters per token and 1,078 + 40 tokens per reddit step, and caps history at 19,697 real tokens. For a 15-step reddit run it predicts 144,660 input tokens; observed 258,742 and 253,400 (1.77x and 1.75x). Output was 126 and 153 tokens per step; the model assumes 600.
  - Inferred (ours): Opus input dominates the H1 budget ($1,483 of the $1,881 H1 Opus line in `cost.json`). The H1 Opus line would rise by roughly a third to two thirds, depending on run length. Long, capped runs sit at the plateau, where the ratio is 1.4x (27.5k vs 19.7k).
  - This is one task in one env. The ratio depends on observation size per env.
- **No prompt caching.** The clone sends no cache points, so every call pays full input. Before the trim, the history is append-only, so a Converse `cachePoint` after the system prompt and after the previous turn would be read from cache. That changes the request the clone sends, so it is a decision for Alex, not a Stage 0c item.

## 4. Harness problems found

1. **The history-summary call fails every time on Opus 5.5 (observed, 4 of 4 calls).** `trim_messages` calls `llm_complete(..., temperature=0.0)`. Bedrock returns `ValidationException: temperature is deprecated for this model`. `trim_messages` catches the exception and falls back silently to `_build_fallback_summary`. So every run past about 11 steps continues on the regex fallback, not an LLM summary.
   - DESIGN §3 plans to log summary failures but keeps the temperature as shipped.
   - Decision: the H1 wrapper must drop `temperature` for Opus 5.5 (and check GPT-5.6 in Stage 0s). Otherwise the pilot measures the fallback-summary harness. Either choice must be stated in DESIGN §3.
   - After the trim, the 7 calls (4 clean, 3 labels) returned 6 to 86 output tokens, and 6 of the 7 had no reasoning block. Before the trim, calls returned 33 to 420 tokens, all with a reasoning block. Whether the bare fallback context changes the agent's behaviour is open (ours).
2. **`run_episode` throws away the forced evaluation of failed runs (observed).** It replaces `evaluation` with the `force_evaluate` result only if that score is higher (`agent_eval.py`, after the loop). A run that ends at the cap with score 0 therefore keeps `{"reasoning": "Agent did not finish"}`, without checks, negative checks or failure kinds.
   - Fix used here: the task subclass stores the `force_evaluate` result.
   - The H1 wrapper must do the same. Otherwise failure analysis (which check failed, under which cell) has nothing to read.
3. **Opus 5.5 reasons by default and the reasoning is dropped (observed).** The clone sends no reasoning field. Opus 5.5 still returned `reasoningContent` blocks on 24 of 30 calls (default adaptive thinking; default effort `medium` per the claude-api reference [unverified on Bedrock]). `_complete_bedrock` keeps only the text blocks.
   - These tokens are billed in `outputTokens`, and the reasoning is not in the trajectory.
   - The wrapper's planned `additionalModelRequestFields` should set effort explicitly, so the setting is a recorded choice, not a default.
   - Logging the reasoning text would make failure reading possible.
4. **The shipped `make_env` has no isolation (observed in code).** `make_env` installs no Date shim and no route filter, so a plain run differs from the replay and from DESIGN §3. The subclass here adds both before navigation, and the check shows they took effect from the first page.
5. **Server start depends on the cwd (inferred from Python semantics, guarded here).** `runner.start_server` runs `python -m uvicorn breakingweb.app:app` with the caller's cwd, and `-m` puts the cwd first on `sys.path`. Started from a different checkout, it would serve that checkout's build. The script asserts cwd = `BW_ROOT`, and the served-asset check would catch a mismatch.
   - `start_server` also pipes the server's stdout and stderr without reading them. A long run with heavy logging could fill the pipe and stall the server [unverified; not seen in 2 x 68 s].
6. **Viewport-only observation hides the way to the goal (observed, 2 of 2 runs).** At the start, the reddit Messages link is below the fold in the sidebar. The agent sees only the viewport (`filter_visible_only=True`). Both runs spent their first 11 and 12 steps on search, the profile menu and scrolling. They clicked `link 'Messages'` at steps 12 (clean) and 13 (labels) and opened the compose form one step later.
   - Under the pilot cap (1.5 x 7 = 10 steps), both runs would fail before reaching the form.
   - This says nothing about the defect: the two arms took the same route until the form.
   - It does matter for task admission: a tier-B task can fail admission on step budget alone, as DESIGN §5 anticipates.
   - Inferred (ours): Stage 0s should report cap hits per task with the step at which the goal page was first reached.

## 5. What this does and does not show

- Shown: the run → log → evaluate → restore chain works for one model, one task and two builds. The served build matches the declared variant byte for byte, and the defect reaches the agent on its path.
- Not shown: anything about success rates, noise or defect effects (n = 2, both at the cap, step cap not the pilot's). GPT-5.6 on Bedrock and the browser-use harness (H2) were not run. The H1 wrapper of DESIGN §3 (`h1_wrapper.py`: maxTokens 16,384, reasoning field) does not exist yet; this run used the clone's request as shipped (maxTokens 4,096; no call came near it, max output 420).
- Decisions this informs:
  - the wrapper must drop `temperature` on the summary call, keep the forced evaluation, and set effort explicitly (§4);
  - the cost model's characters per token should be 2.33 for this observation text, not 3.3; recompute `cost.json` before Stage 0s's 1.5x budget gate;
  - prompt caching is an open option.
