# Task feasibility under each defect variant, by replay of recorded clean solutions (2026-10-30)

> **Summary:** We turned every successful Gemini-3.1-Pro clean run (374 tasks) into plain mouse and keyboard input on the clean build, without an LLM, and replayed it in fresh sessions scored by BreakingWeb's own evaluator. 195 tasks pass 3 of 3 clean replays; this is the reference set (amazon 42, booking 29, gmail 39, lms 11, patient portal 18, reddit 34, robinhood 22). Every replayed task passed either 0 or 3 of its 3 clean replays, never 1 or 2. We then replayed the reference set by the same input under each of the 36 defect cells that passed the variant gate and built differently from clean, plus the `none` sham. Every task stays feasible in every cell: 1,206 task-cells passed on the first run, 124 cells (alt where the env has no `<img>`) built byte-identical to clean, and 0 became infeasible. One booking task failed its first run in all five booking defect cells and in the sham, then passed both re-runs, so this is replay timing, not the defect. The controls behave as they should. A do-nothing run passes the evaluator on 0 of 195 tasks. The known-answer break `pc_break` (every second button's onClick moved to onDoubleClick, every second link out of the Tab order) makes 106 of 195 tasks fail 3 of 3. No cell has to be excluded for function. The limit: feasibility is shown for one path per task, Gemini's, and that path never clicks a `<label>`.

Question served: DQ-tasks, task gate and cell gate (`../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-tasks.md` F3, F5, F7, F10, F13). The redesign brief asks for "One reference trajectory per task that passes the evaluator 3/3 after reset while a do-nothing run fails", and says the bridge "needs scripted replay in every cell by recorded coordinates or node identity, never by the ablated information" (`2026-10-29-redesign-brief.md`, D on tasks). This record follows [2026-10-30-variant-gate.md](2026-10-30-variant-gate.md) (does each variant look the same at rest) and [2026-10-30-function-equivalence.md](2026-10-30-function-equivalence.md) (does each single action from rest have the same effect). It answers that record's open threat: "Sequences ... and other in-task states are not covered."

Scripts (in `scripts/probe/breakingweb/`, each with a docstring stating inputs, outputs and how to run):
- `replay.py`: compile, play, drive, summary.
- `replay_report.py`: the JSON next to this record.
- `path_replay.py` and `click_effect.py`: element resolution and the `pc_break` control, imported unchanged.

Drivers: `/tmp/amt-syn/bw-replay/run_env.sh` (one private checkout per env, `/tmp/amt-syn/bw-fx-src1..7/BreakingWeb`, ports 8311-8317 on 127.0.0.1). Raw outputs: `/tmp/amt-syn/bw-replay/final/` (18 MB, regenerable). Summary JSON: [2026-10-30-replay-feasibility.json](2026-10-30-replay-feasibility.json); keys are named below in brackets, and `matrix` is the task x kind table. Script hashes: `/tmp/amt-syn/bw-replay/script_hashes_launch.txt` (main run; that `replay.py` is kept as `/tmp/amt-syn/bw-replay/replay_as_main_run.py`), `script_hashes_controls.txt` and `script_hashes_end.txt`. Between the main run and the controls, the only change to the play code was the `null` switch: the compile and play functions used by the main run are otherwise unchanged (checked by diff). After the controls, only the docstring changed (the end hash).

## 1. Method

### 1.1 From a recorded run to input (compile)

- **Question.** Can a recorded browser-use solution be turned into input that a sighted mouse user could give, and that does not depend on the information a defect removes?
- **What compile does.** On the clean build, each recorded action is resolved to its element. Resolution uses `path_replay.locate`: the recorded target role and name (aria-label, placeholder, or the visible text from `extracted_content`) pick a DOM element; ties go to the element nearest the recorded click or input coordinates (`action_results[].metadata` `click_x/click_y`, `input_x/input_y`); if no name matches, the element under the recorded point is used. The element is then brought into view with mouse-wheel events: over its scroll container, or for the window over a point with no nested scroller. It is acted on at a point of its visible box where the hit test returns the element itself.
  - click: a mouse click.
  - fill: a mouse click, then the text is filled into the focused element (`document.activeElement`; Playwright fill, which also handles date inputs); `clear: false` appends.
  - select: a mouse click, then the option is set on the focused `<select>`.
  - Also: key press, wheel scroll, history back.
  - Read-only actions (finish, dropdown_options, find_*, search_page, wait, noop) do nothing.
  - If the element is covered (a toast, an overlay), compile waits in 500 ms steps up to 3 s, or wheels the element to the middle when a sticky bar covers it.
  - The compile run executes exactly these input ops, so it is run 0 of the replay. The ops are written as the task's script (`OUT/<env>/scripts/<task>.json`).
- **Grounds.**
  - DQ-tasks F5: "the replay that serves as the per-cell feasibility test must not locate elements through the information being ablated". Names are used only on the clean build, where nothing is removed. The variant replay reads no name, role or selector.
  - Why the recorded coordinates are not replayed raw (observed): browser-use scrolls an element into view before clicking, so the recorded point belongs to a scroll state the replay does not have. In the reference scripts, the element under the raw recorded point, taken before any scroll, is the resolved element in 1,663 of 2,119 actions that have coordinates (78%) [`raw_point_agrees`]. A raw-coordinate replay would act on the wrong element in about 1 action in 5.
- **How it could be wrong.**
  - Resolution can pick a wrong look-alike element. The 3/3 evaluator gate (1.3) catches this only when the wrong choice changes the end state.
  - Fill and select set the value on the focused control through Playwright, not through single keystrokes or the native popup. A variant that broke key handlers or the popup would be missed. No kind changes event handlers (codemod.py keeps them), so this is a coverage limit, not a known gap.
- **Exclusion rule (fixed before any variant replay).** A task is *input-pure* only if every action became input. Otherwise it is excluded and the first reason is logged: element not found, no hit point, the click did not focus the control, or the recorded option is missing.

### 1.2 Replay (play)

- Each play replays only the ops of the script.
- **Isolation:**
  - every run opens a new backend session (`POST /api/env/<env>/session {task_id}`, the call `stock_browseruse_eval.py` makes, so the backend default seed) and a new browser context;
  - viewport 1280x720, the stock harness viewport for Gemini;
  - the page's Date starts at 2026-10-30T09:00Z at every load and then runs (`DATE_SHIM`, as `click_effect.py`);
  - requests to hosts other than 127.0.0.1 are aborted, so remote images load in neither arm;
  - Chromium smooth scrolling is off;
  - settle after each op: network idle (cap 4 s) plus 350 ms.
- **Scoring:** `POST /api/env/<env>/evaluate {session_id}`, BreakingWeb's scorer of the final backend state, which is also how the leaderboard harness scores (`stock_browseruse_eval.py`, step 7). The harness sends no final answer text, so every task is scored on backend state only. A replay that does nothing in `finish` loses nothing.
- **Diagnostics.** Before each click, the element under the point is recorded (tag, text, class, the box of its control ancestor), and after each action the URL path. This lets a run be compared step by step with the compile run [`diverge`]. The verdict uses only the evaluator.

### 1.3 Reference set and cell verdicts

- **Reference set.** A task is in it if it is input-pure and passes the evaluator on 3 of 3 clean plays after reset.
  - Grounds: CTL-2 of [Chen2026a](../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md), "the reference solution must be graded as solved"; DQ-tasks F10 ([Wei2026](../../../ai-accessibility-paper/literature/papers/L_Wei2026.md): single runs flip, so a strict k-of-k gate keeps stable tasks); the brief's 3/3 rule.
- **Cell verdict per task.**
  - feasible: the first variant play passes.
  - infeasible: it fails, and so do two more plays.
  - unstable: mixed.
  - feasible_identical: the variant bundle is byte-identical to clean (sha256 over `static/envs/<env>`), so it was not played.
- **Cells played.** Every env x kind that passed the variant gate and builds differently from clean: 36 defect cells. They include the tableheads cells of booking, reddit and robinhood, which the gate passed as no-ops on its captured pages, and amazon tableheads, which differs from clean through the shared sources. Booking alt failed the gate and is not played. The `none` sham is played last in each env, as a late clean control judged like a variant.
- **Controls.**
  - do-nothing (CTL-1 of Chen2026a): the start page is opened and evaluated with no input.
  - `pc_break`: the known-answer break of `click_effect.py`, built and played like a kind.
- **Same artefacts as the earlier gates (observed).** Every clean, variant, sham and `pc_break` bundle built here has the same hash as the build of the same cell in the function-equivalence run (`/tmp/amt-syn/bw-fx/final/<env>/builds.json`) [`bundles`]. `pc_break` was built there only for lms and patient portal; both match.
- **How it could be wrong.**
  - The gate is per path. One recorded path per task shows that a solution exists. It does not show that every route a model might take still works (section 5).
  - Timing. The replay runs at machine speed, with 2 workers per env and 7 envs in parallel on 16 cores. A page that is slow under load can fail a play. The sham estimates this (section 3).

## 2. Reference set (observed, n = 374 sampled tasks)

The sample is every task Gemini-3.1-Pro solved clean (`evaluation.success`, 374 of 519), all 7 envs.

| env | sampled | input-pure | compile run passes | clean 3/3 | clean 1/3 or 2/3 | reference |
|---|---|---|---|---|---|---|
| amazon | 60 | 48 | 45 | 42 | 0 | 42 |
| booking | 61 | 36 | 29 | 29 | 0 | 29 |
| gmail | 42 | 42 | 39 | 39 | 0 | 39 |
| lms | 36 | 28 | 11 | 11 | 0 | 11 |
| patient portal | 54 | 47 | 18 | 18 | 0 | 18 |
| reddit | 69 | 68 | 34 | 34 | 0 | 34 |
| robinhood | 52 | 41 | 23 | 22 | 0 | 22 |
| all | 374 | 310 | 199 | 195 | 0 | **195** |

- **Determinism (observed).** Of the 310 input-pure tasks, 195 pass 3/3 and 115 pass 0/3; none passes 1 or 2 of 3. Every clean play of every reference task followed the compile run's path and click hits exactly (0 of 195 tasks diverged) [`ref_tasks_with_clean_divergence`].
- **Why tasks drop out (observed)** [`envs.*.classes`]:
  - Not input-pure, 64 tasks. Most often a recorded target is not found on our build (`missing`). Next, amazon's "Added to Cart" bar covers the search box, so a mouse cannot reach the field that browser-use typed into through the DOM (12 actions in 8 tasks).
  - Input-pure but the evaluator fails on replay, 114 tasks: 44 of them hardened after the published runs, and 70 drift or replay limits.
  - Compile passes but every play fails, 1 task: `amazon_return_and_upgrade_cycle`. The faster play reaches the search box while the cart bar still covers it.
- **Against the earlier replay** (`path_replay.py`, element-based, [2026-10-30-on-path-dose.md](2026-10-30-on-path-dose.md)): of its 205 passes, 190 are in the reference set; the other 15 are 12 not input-pure, 2 evaluator failures and 1 timing case. 5 reference tasks failed there and pass here. Of the 57 hardened tasks, 2 are in the reference set (lms) and 55 are excluded.
- **What the reference paths contain** [`ops_reference`]: 2,336 clicks, 546 fills, 152 selects, 350 wheel scrolls, 65 waits for a covering element, 8 key presses, 5 history backs. All 2,336 clicks hit the element itself; none goes through a `<label>` [`hit_via_reference`]. 19 clicks land on an `<h3>` (reddit post titles, 18 tasks) and 6 on an `<img>` inside a link (amazon).
- **What would change a decision.** The reference set is small in lms (11) and the patient portal (18), mostly because of hardened tasks. If those two envs are needed for a cell, the hardened tasks need new reference solutions (another model's successful run, or a recorded human run) passed through the same compile and 3/3 gate.

## 3. Feasibility matrix (observed; n = 195 reference tasks; first play, re-plays for failures)

Each cell counts reference tasks: feasible on first play / unstable / infeasible. "ident." means the bundle is byte-identical to clean (alt in an env with no `<img>`).

| env (n) | landmarks | headings | names | labels | alt | tableheads | none (sham) |
|---|---|---|---|---|---|---|---|
| amazon (42) | 42/0/0 | 42/0/0 | 42/0/0 | 42/0/0 | 42/0/0 | 42/0/0 | 42/0/0 |
| booking (29) | 28/1/0 | 28/1/0 | 28/1/0 | 28/1/0 | not run (gate FAIL) | 28/1/0 | 28/1/0 |
| gmail (39) | 39/0/0 | 39/0/0 | 39/0/0 | 39/0/0 | ident. | 39/0/0 | 39/0/0 |
| lms (11) | 11/0/0 | 11/0/0 | 11/0/0 | 11/0/0 | ident. | 11/0/0 | 11/0/0 |
| patient portal (18) | 18/0/0 | 18/0/0 | 18/0/0 | 18/0/0 | ident. | 18/0/0 | 18/0/0 |
| reddit (34) | 34/0/0 | 34/0/0 | 34/0/0 | 34/0/0 | ident. | 34/0/0 | 34/0/0 |
| robinhood (22) | 22/0/0 | 22/0/0 | 22/0/0 | 22/0/0 | ident. | 22/0/0 | 22/0/0 |

- **Totals** [`matrix`]: 1,336 task x cell entries. 1,206 feasible on first play, 124 identical bundle, 6 unstable (one task), 0 infeasible. 3,330 replays in all: 374 compile, 930 clean plays, 1,424 variant and sham plays, 407 `pc_break` plays and 195 do-nothing runs.
- **The one failure under a variant: `booking_profile_update_suite`, a replay artefact.**
  - Observed: the first play failed in every booking defect cell and in the sham, and both re-plays passed in every cell. In each failed play, the "Account" click reached `/account`, but at the next click point (the "Edit" button, box 737,324,48x32 on clean) the hit test returned the app's root `div` covering the whole page, so the page had not finished rendering. The evaluator then reports "Display name updated" as failed. The re-plays, which run with no other task in parallel, hit the same elements as clean.
  - Inferred: the sham is the clean source rebuilt, and it fails the same way, so the cause is timing under parallel load, not a defect. The task passed its 3 clean plays, so the 3/3 gate does not catch every timing-sensitive task. Sham false-failure rate: 1 of 195 tasks on first play.
- **Which reference paths carry the defect** (primary on-path flag of `on_path_dose.py`, from the clean element-based replay of the same runs) [`on_path_reference`]:
  - landmarks: 195 of 195;
  - headings: 192;
  - names: 162 (an acted-on control loses part of its name);
  - labels: 135;
  - alt: 42 of 42 in amazon (booking alt not run);
  - tableheads: 44 (patient portal 17, gmail 10, lms 10, booking 4, robinhood 3).

  So "feasible" holds on paths that pass through the removed information, not only on paths that avoid it. The 19 reddit `<h3>` clicks still work when headings become `div`s.
- **Passed, but with a different click hit somewhere** [`cells.*.passed_with_divergence`]: 6 task-cells. In every one, the element under the point has the same tag and text as on clean and only its box differs. The cases are amazon headings and names (the "Go to Cart" link of the sliding cart bar) and `pp_schedule_new_specialist` under patient portal landmarks, headings, labels and the sham (a `<select>`). The patient portal case also occurs in the sham, so it is timing.
- **What would change a decision.** An infeasible task-cell would have removed that task from that cell (DQ-tasks F13: fixed rule, logged). None did. If a confirmatory agent run fails a task under a variant, page function on the reference path is not the cause. The failure belongs to how the agent used the remaining information (or to a different route, section 5).

## 4. Controls (observed)

| env | do-nothing passes / n | pc_break infeasible / n |
|---|---|---|
| amazon | 0 / 42 | 33 / 42 |
| booking | 0 / 29 | 18 / 29 |
| gmail | 0 / 39 | 18 / 39 |
| lms | 0 / 11 | 11 / 11 |
| patient portal | 0 / 18 | 3 / 18 |
| reddit | 0 / 34 | 19 / 34 |
| robinhood | 0 / 22 | 4 / 22 |
| all | 0 / 195 | 106 / 195 |

- **Do-nothing.** The evaluator rejects an empty run on every reference task (CTL-1 of [Chen2026a](../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md)). With CTL-2 (3/3), this is the brief's task gate.
- **pc_break.** All 106 failures fail 3 of 3. The break hits every second button in source order, so some paths never need a broken button; inferred, not checked per path, that this is why 89 pass. This shows the replay plus the evaluator detects a functional break that leaves markup and look unchanged.
  - The step diagnostic located the first divergence in 83 of the 106. In the other 23, a click that does nothing leaves the URL and the next hit elements unchanged. That is why the evaluator, not the diagnostic, decides.
- **What would change a decision.** A do-nothing pass would make that task's evaluator unusable for the cell gate. A `pc_break` pass rate near 100% would have meant the replay was blind. Neither happened.

## 5. Threats

- One path per task. Feasibility is shown for Gemini's path. A model that takes another route can meet a change this path never touches. Example: the labels variant stops a click on label text from focusing its control (37 labels, [2026-10-30-function-equivalence.md](2026-10-30-function-equivalence.md)), and no reference click goes through a label. The cell gate therefore says "a solution survives", not "every solution survives". This is the *functional feasibility* half of DQ-tasks ("Where they disagree"). *Informational feasibility* (can the agent still find its target from the ablated observation) is not tested here.
- The task set is selected twice: by Gemini solving the task, and by the task replaying 3/3 on our build. 195 of 519 tasks, with lms and the patient portal thin. DQ-tasks F9 warns that selection on one model's success biases the set. The `on_path_dose.py` pool and its headroom numbers apply to choosing within it.
- Tables, alt and headings are on the path as page content (the agent sees them), not as click targets. For tableheads, no reference action clicks a `th` (the hit tags in section 2 contain none), so "feasible" for tableheads means "nothing on the path broke".
- Fill and select bypass keystrokes and the native popup (1.1). Wheel scrolling and clicks are real input events.
- Timing. Replays run at machine speed under parallel load. One reference task proved timing-sensitive in the sham (section 3). A lower load or a longer settle could rescue some of the 115 input-pure 0/3 tasks; it would not change any verdict above, because no cell failed.
- Remote requests are aborted in both arms, so Unsplash photos never load. The booking alt cell, which failed the gate on dead remote images, stays out.
- Date is fixed at 2026-10-30T09:00Z in the page. The backend keeps its own clock. The pages are verified for Chromium 125 (Playwright 1.44, as the gate).
- The step diagnostic summarises a state by path, hit text and box. The verdict does not depend on it.

## 6. State left behind

- Sources restored: the main clone `~/.workspace/_refsrc/BreakingWeb` and the 7 private copies show only the 4 allowed bind-fix diffs (app.py and 3 scripts). Each copy's env was rebuilt clean at the end of its drive.
- No server or browser is left running.
- No LLM (Gemini or other) was called.
- Prototype outputs from script development are in `/tmp/amt-syn/bw-replay-test/` and superseded by `/tmp/amt-syn/bw-replay/final/`. All numbers above come from the final run.
