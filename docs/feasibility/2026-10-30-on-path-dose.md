# On-path dose of each accessibility kind in the BreakingWeb tasks (2026-10-30)

> **Summary:** We replayed 1,717 successful clean runs from 6 browser-use models on a private clean build. At every step we read, from the live page, what each defect kind would remove. Element kinds sit on the agent's path in most tasks. In 285 of 330 Gemini-3.1-Pro paths a control the agent acts on loses part of its name when aria-labels go, and in 239 of 330 a form control loses part of its name when label associations go. The removal makes the name empty or ambiguous in 164 and 149 of them. Page kinds are on almost every path: landmarks in 330 of 330, headings in 326, table headers in 101 (mostly patient portal and LMS), alt text in 77 (Amazon and Booking only). So headings and landmarks have no natural off-path tasks. For names, the on-path/off-path split nearly coincides with the environment. Three findings change other work. First, `codemod.py` misses aria-labels on any tag whose attributes hold an arrow function: the names variant left the aria-label on 90 of 601 acted-on buttons and links, and the labels variant on 246 of 376 controls; a one-character fix cuts this to 8 and 50. Second, 57 tasks (LMS and patient portal) were hardened after the published runs, so their published clean outcomes describe an older task. Third, the stock browser-use observation shows no heading, landmark or table-header semantics at all. The recommended pool has 203 tasks: solved by Gemini, the recorded solution re-passes the evaluator on our build, and the task was not hardened. Of its 160 most-solved tasks, between 24 (table headers) and 160 (landmarks) are on-path and between 0 (landmarks) and 135 (table headers) are off-path.

Question served: DQ-dose Option D (on-path and off-path cells, `../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-dose.md`) and DQ-tasks F9-F11 (task selection, baseline headroom, noise; `2026-10-29-DQ-tasks.md`). It follows the open item "Dose on the task path from trajectories" of [2026-10-29-breakingweb.md](2026-10-29-breakingweb.md).

Scripts (in `scripts/probe/breakingweb/`, each with a docstring giving inputs, outputs and how to run): `path_replay.py` (replay and measurement), `on_path_dose.py` (analysis), `variant_check.py` (comparison with real codemod variants). Large outputs: `/tmp/amt-syn/bw-path/` (one JSON per replayed run, `analysis/task_kind.csv`, `analysis/actions.csv`, `analysis/runs.csv`); all regenerable. Summary next to this record: [2026-10-30-on-path-dose.json](2026-10-30-on-path-dose.json) (keys named below in brackets; `tasks` is the per-task x kind table).

## 1. Data: clean runs and baseline headroom (observed)

Clean trajectories were downloaded from `BreakingWeb/breakingweb-results-v2` and `-v3` (trajectory.json, run_manifest.json and summary.json only, no screenshots) into `~/.hf-stage-bw/`. A run counts as valid if it has at least one step and no API error (`runs_success`).

| model (harness) | valid runs | solved | hit the time wall |
|---|---|---|---|
| Gemini-3.1-Pro (browser-use, v2) | 513 | 374 | 18 |
| Gemini-3-Flash (browser-use, v2) | 510 | 328 | 5 |
| GPT-5.4 (browser-use, v2) | 512 | 318 | 0 |
| GPT-5.4-mini (browser-use, v2) | 515 | 172 | 1 |
| Opus-4.7 (browser-use, v2; 40 steps, 600 s) | 516 | 264 | 199 |
| Opus-4.7 (browser-use, v3 retries; 60 steps, 1,200 s) | 296 | 35 | 103 |
| Sonnet-4.6 (browser-use, v3) | 518 | 261 | 152 |
| Qwen3-VL-235B (browser-use, v2) | 24 | 12 | 6 |
| Gemini-3.1-Pro, GPT-5.4, Opus-4.7 (screenshot-only, v3, incl. retry shards) | 1,784 | 381 | 46 |

Clean runs per task (`headroom`): all harnesses median 10 (IQR 9-11, max 13); browser-use median 6 (IQR 6-7); screenshot-only median 3 (IQR 3-4). Every task has at least one run of each harness.

Headroom is measured on a panel: the six browser-use models that ran all 519 tasks (both Geminis, both GPT-5.4s, Opus-4.7 v2, Sonnet-4.6). Number of panel models solving a task (n = 519 tasks): 0: 98, 1: 51, 2: 42, 3: 50, 4: 73, 5: 90, 6: 115. Among the 374 tasks Gemini solved: 1: 26, 2: 33, 3: 45, 4: 68, 5: 87, 6: 115. Per-task browser-use success rate over all valid runs: quartiles 0.14, 0.67, 0.83; 96 tasks never solved, 124 always solved. Per env, mean panel success rate: Amazon 0.73, patient portal 0.62, Reddit 0.62, Booking 0.56, Robinhood 0.53, LMS 0.53, Gmail 0.35 (`headroom.per_env`).

- Question: is a task solvable in the clean condition, and by how many models? We select on outcome, so we need this number (DQ-tasks F9, F10).
- Grounds: Wei2026 (single-run outcomes flip; tasks that some modes solve flip 48-52%), Gardner2020 (contrast sets should be built without a model in the loop), Enomoto2026 (the effect of an observation change flips sign between models).
- How it could be wrong:
  - Opus-4.7 v2 hit the 600 s wall in 199 of 516 runs and Sonnet-4.6 in 152 of 518, so their failures partly measure the budget, not ability. Sonnet's manifest covers only its last invocation, so its settings for the bulk of runs are [unverified].
  - The 57 hardened tasks (section 4.2) make the published outcomes of those tasks refer to an older task version.
- What would change a decision: the study's own clean runs on the local build replace these numbers. They are a prior for which tasks to run, not the baseline.

## 2. Method

### 2.1 Replay on the clean build (observed procedure)

`path_replay.py` takes each successful clean run and repeats its actions on a fresh seeded session. A run's path is the sequence of page states it passes through. At each step, before the action, it records the DOM and AX-tree counts of every instance the codemod would change, and, for the element acted on, its attributes and its accessible name read from Chrome's AX tree three times: clean, with aria-label and aria-labelledby removed (the `names` kind), and with those and `label[for]` removed (the `labels` kind). The attributes are removed only for the measurement and restored at once. It also records how many other visible controls of the same kind share the element's name before and after the removal (a DOM approximation). At the end it asks the backend evaluator whether the replayed end state passes.

- Question: which page states and which elements does a successful path actually touch?
- Grounds:
  - ours: trajectories record actions and aria-labels, but not the headings, landmarks, tables or label associations of the pages.
  - CTL-2 of Chen2026a, the reference solution must be graded as solved (DQ-tasks): a recorded success that re-passes the evaluator on our build is that reference solution.
- Isolation (observed): another workflow step rebuilt variant bundles inside the shared checkout while our first replays ran. A `variant_gate.py` process was rebuilding Booking at 05:16. All results here therefore come from a private copy, `/tmp/amt-syn/bw-clean`: `git archive HEAD` plus the 127.0.0.1 bind fix, rebuilt clean. The first, possibly contaminated, replays were discarded. The shared checkout's `git status` shows only the four allowed diffs.
- Replay fidelity (`replay_fidelity`):

| model | replayed | evaluator passes | path followed (measured) | targets located |
|---|---|---|---|---|
| Gemini-3.1-Pro | 374 | 205 | 330 | 97.2% of 5,445 |
| Gemini-3-Flash | 328 | 165 | 288 | 95.6% of 4,377 |
| GPT-5.4 | 318 | 167 | 269 | 94.2% of 3,926 |
| GPT-5.4-mini | 172 | 90 | 147 | 93.9% of 1,372 |
| Opus-4.7 | 264 | 120 | 206 | 90.6% of 2,326 |
| Sonnet-4.6 | 261 | 138 | 206 | 95.2% of 2,852 |

- "Measured" means the replay passed, or at least 90% of steps were on the recorded URL path and at least 90% of targets were found (ours). Exposure numbers below come only from measured paths. Each replay uses the model's own viewport (Claude 1024x768, GPT 1600x900, Gemini 1280x720, as in `stock_browseruse_eval.py`).
- Repeatability (observed): a second full replay of the 374 Gemini runs gave the same evaluator outcome for 373, and identical on-path flags for all kinds in 373-374 of 374.
- Why replays fail (observed, Gemini, 169 failures):
  - 55 are hardened tasks (section 4.2).
  - Of the other 114, 58 executed every action and the evaluator still disagrees, which points to task or seed drift.
  - The other 56 had at least one action not found or failed, which is a replay limitation or drift.
  - Setting the backend clock to the run date (2026-05-01) recovered 1 of 40 failures, so the current date is not the main cause.
- How it could be wrong:
  - Only the state before each step is recorded. A step with several actions can pass through a state we never record, for example a modal opened and closed within one step.
  - Loose matching can pick a wrong element when several look alike: 530 of 5,445 Gemini actions had more than one candidate, chosen by recorded click position, with a retry when the next recorded page was not reached.
- What would change a decision: if the study's own clean runs take paths whose kind flags agree with these less than about 0.9, derive exposure from those runs instead.

### 2.2 What "on path" means for each kind

Each kind gets a count, a binary flag (primary) and a stricter flag. The table says what is counted and why.

| kind | counted on the path | primary flag | strict flag |
|---|---|---|---|
| names | acted-on `button`/`a` with aria-label(ledby) whose AX name changes when it is removed | any acted-on control whose name becomes empty, ambiguous or loses a content word | empty or ambiguous |
| labels | acted-on input/textarea/select named through aria-label(ledby) or `label[for]` | as names | as names |
| headings | rendered h1-h6 and role=heading, max over visited states | present in any visited state (whole document) | present in the viewport of a visited state |
| landmarks | header, nav, main, footer, aside and landmark roles (the codemod's selector), max over states | as headings | as headings |
| tableheads | rendered `th`, max over states | as headings | as headings |
| alt | rendered `img` with non-empty alt, max over states | as headings | alt is the only name of a control |

- Name-loss ladder (ours): **empty** (no name left), **ambiguous** (the new name is shared with another visible control of the same kind while the clean name was unique), **lost** (a content word of the clean name is missing, but the element is still unique), **changed** (form only, for example "Place your simulated order" becomes "Place Simulated Order"), **kept**.
  - Grounds:
    - DQ-dose F9: Enomoto2026a finds that a failure step usually hinges on one or two elements, so what matters is whether the element acted on loses its information.
    - WCAG 2.4.4 (link purpose): repeated generic text such as "Add to Cart" is the real-world form of the defect ([2026-10-29-breakingweb.md](2026-10-29-breakingweb.md)).
  - "Changed" is excluded from the primary flag because no information is lost (ours).
  - How it could be wrong:
    - "lost" is a word rule and over-counts harmless losses, for example "Open X product page" becoming "X".
    - "ambiguous" uses a DOM approximation of names. Section 3.1 gives counts on each rung, so a reader can draw the line elsewhere.
- Page kinds count presence on the page, not use, and whether the agent sees them depends on the harness (section 4.3).
- Grounds for counting the whole document as primary: the agent can scroll (ours). The viewport is the strict version because the BrowserGym observation keeps only visible nodes ([2026-10-29-breakingweb.md](2026-10-29-breakingweb.md)).
- What would change a decision: if the study's harness is browser-use, the page-kind flags below say nothing about what the agent receives, and section 4.3 applies.

### 2.3 Static and route-based estimates, and how far they can be trusted

For runs that were not measured, `on_path_dose.py` falls back on what the trajectory alone shows.

- **Names from the trajectory** (observed agreement). `targets.name` is the full aria-label (BreakingWeb's `dom_element_to_target`: aria-label, then placeholder, then text), and `extracted_content` gives the visible text, truncated at about 30 characters. On 3,195 Gemini button and link actions, the trajectory-only class agrees with the replay class in 3,193. The 199 cases where truncation made "lost" uncertain were all "lost" in the replay (`names_static_vs_replay_gemini`). The names estimate is therefore usable for every run of every model without a replay.
- **Labels** cannot be estimated from the trajectory: `targets.name` of a text box is the aria-label or the placeholder, and the label association is not recorded.
- **Page kinds from routes** (`route_inference`). Visited URL paths were matched to the route captures of the 2026-10-29 batch: 2,039 of 3,640 path visits matched a static route, 192 a start page and 416 only an example of a parameter route; 993 (27%) had no capture. Against the replay's AX-role presence on the 330 measured Gemini paths:
  - Landmarks agree on 330 of 330.
  - Headings: the route is unknown or negative for 19 tasks, 15 of which have headings in the replay.
  - Table headers: the route misses 39 of 101 tasks that have them, because tables sit behind tabs and parameter routes.
  - Alt: the route misses 8 of 123. This comparison counts named image nodes in the AX tree, which include icons named by aria-label, so its 123 is larger than the 77 tasks with an `img alt` in 3.2.

  The route inference is good enough for landmarks and headings and not for table headers.

## 3. Results on the Gemini-3.1-Pro paths (observed, n = 330 measured paths)

### 3.1 Element kinds: what the defect does to the elements the agent acts on

Names, per acted-on button or link (n = 3,195 actions). The env columns count actions, `ambiguous` counts sit under "amb".

| class | all | amazon | booking | gmail | lms | pp | reddit | rh |
|---|---|---|---|---|---|---|---|---|
| no aria-label (unaffected) | 941 | 151 | 498 | 6 | 0 | 0 | 76 | 210 |
| kept | 543 | 40 | 4 | 80 | 147 | 134 | 130 | 8 |
| changed (form only) | 151 | 45 | 0 | 24 | 4 | 1 | 77 | 0 |
| lost a word, still unique | 1,005 | 108 | 4 | 183 | 132 | 74 | 313 | 191 |
| amb (shared with another control) | 318 | 164 | 24 | 6 | 12 | 33 | 40 | 39 |
| empty (icon-only) | 237 | 95 | 0 | 130 | 0 | 0 | 0 | 12 |

Labels, per acted-on form control (n = 2,028 actions):

- The AX name after removing aria-label(ledby) and `label[for]`: none of either source 332, kept 283, changed 112, lost a word 655, empty 646, ambiguous 0. Empty is concentrated in the patient portal (298 of 366 control actions there), where controls carry both aria-label and `label[for]` and no placeholder.
- Name sources of the same controls (`label_sources_gemini`): aria-label present on 1,306 (64%), `label[for]` on 1,023 (50%), placeholder on 1,037, wrapping label on 240. No source at all on 210, all in Booking. These are a natural labelling defect in the clean app: for example, the date inputs on the Booking property page have a `<label>` with no `htmlFor`.

Per task (`distribution_gemini_replay`): on-path tasks / measured tasks, and the median dose (instances on the path) among all measured tasks.

| kind | amazon | booking | gmail | lms | pp | reddit | rh | all |
|---|---|---|---|---|---|---|---|---|
| names, primary | 53/56 | 10/42 | 40/42 | 26/26 | 49/50 | 65/69 | 42/45 | 285/330 (med 3, p75 6, max 34) |
| names, strict | 53 | 7 | 28 | 4 | 16 | 31 | 25 | 164 |
| labels, primary | 32/56 | 23/42 | 37/42 | 15/26 | 41/50 | 52/69 | 39/45 | 239/330 (med 2, p75 5, max 30) |
| labels, strict | 16 | 20 | 4 | 7 | 39 | 29 | 34 | 149 |

### 3.2 Page kinds: what is on the pages the path visits

| kind | amazon | booking | gmail | lms | pp | reddit | rh | all |
|---|---|---|---|---|---|---|---|---|
| headings present (med max-per-state) | 56/56 (27) | 42/42 (20) | 38/42 (2) | 26/26 (4) | 50/50 (5) | 69/69 (30) | 45/45 (12) | 326/330 |
| headings in viewport (med) | 5 | 6 | 1 | 3 | 5 | 7 | 3 | 326/330 |
| landmarks present (med) | 56/56 (6) | 42/42 (4) | 42/42 (8) | 26/26 (3) | 50/50 (3) | 69/69 (5) | 45/45 (6) | 330/330 |
| table headers present (med) | 0/56 | 14/42 (0) | 12/42 (0) | 19/26 (8) | 44/50 (12) | 0/69 | 12/45 (0) | 101/330 |
| table headers in viewport | 0 | 14 | 9 | 19 | 43 | 0 | 12 | 97/330 |
| img alt present (med) | 56/56 (16) | 21/42 (1.5) | 0/42 | 0/26 | 0/50 | 0/69 | 0/45 | 77/330 |
| alt = only name of a control | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/330 |

- Targets inside a landmark: the median share of a path's acted-on targets is 1.0 in six apps and 0.27 in Reddit, so Reddit is the only app where an in-region versus out-of-region split of targets exists.
- Targets preceded by a heading: median share 0.67 to 1.0.
- Targets inside a table: up to 0.6 of a path in LMS and up to 1.0 in the patient portal; 0 in Amazon and Reddit (`page_detail_gemini_replay`).

### 3.3 Agreement between models

For 1,011 pairs of a measured Gemini path and a measured path of another model on the same task, the primary flags agree for names 99.1% (Cohen's kappa 0.97), labels 98.7% (0.97), headings 99.7% (0.91), landmarks 100%, table headers 98.4% (0.96), alt 100% (1.00) (`cross_model_agreement`).

The on-path flag is therefore a property of the task, not of the model that solved it, for the five models we checked. The other models' replays have no ambiguity measure for Flash, Sonnet and Opus (they ran before it was added), so for names and labels they use the empty and lost rungs.

## 4. Findings that change other work

### 4.1 The codemod misses aria-labels on tags with arrow-function attributes (observed)

- Question: does the source-level variant (D-008's reference) remove what the replay predicts?
- Method: replay a stratified sample (10 solved Gemini tasks per env, n = 70) on three real variant builds: names, labels, and headings+landmarks+tableheads+alt applied together. Then compare each acted-on element's AX name in the variant with the clean replay's prediction (`variant_check.py`; `codemod.py` sha256 71a8d729a8eac09d).
- Page kinds: no instance is left in any of 872 variant states (the clean sample has 9,972 heading, 3,839 landmark, 2,543 `th` and 675 img-alt instance-states). The DOM counts used for page kinds are therefore exactly what the codemod removes.
- names: the prediction matches the variant for 531 of 601 aligned buttons and links. In the variant, 90 acted-on buttons and links still carry an aria-label.
- labels: the prediction matches for 141 of 376 controls. 246 controls still carry an aria-label and 3 a `label[for]`.
- Cause: in `TAG_BODY = r'(?:[^<>]|\{...\})*>'`, the first alternative matches `{` as a plain character. In `<button onClick={() => f(x)} aria-label="Reply to message">` the tag match therefore ends at the `>` of `=>`, and the aria-label after it is never seen (reddit `Messages.tsx:181`, booking `Home.tsx:141`).
- Fix checked: changing the first alternative to `[^<>{}]` raises the match to 588 of 600 for names (8 aria-labels left) and to 316 of 376 for labels (50 left). The fixed copy is `/tmp/amt-syn/bw-path/codemod_fixed.py`; `codemod.py` itself was not edited, because another workflow step is revising it.
- The 50 labels misses that remain have two causes:
  - The aria-label is passed inside a props object (`inputProps={{"aria-label": "Email subject", ...}}` to Gmail's `FormField`).
  - The braces nest three levels deep (LMS `PeerReviews.tsx:172-179`).

  Both need a different rewrite, for example JSX parsing.
- Consequence: until the fix lands, the labels variant removes the aria-label from only about a third of the controls agents use, and the names variant misses about one in seven. A null result for labels would then be an artefact. The names and labels line counts of the 2026-10-29 batch are undercounts for the same reason: the batch's codemod had the same regex.
- What would change a decision: re-run `variant_check.py` after any codemod change. Agreement of at least 98% on both element kinds is our gate before an agent run (ours).

### 4.2 57 tasks changed after the published runs (observed)

- The public release has 57 solvability tests named `test_<task>_upgrade.py`, whose docstrings say "hardened (v2)" or "upgraded" (LMS 27, patient portal 30).
- Gemini's recorded successes on these replay to a passing state in 2 of 57 cases, against 203 of 317 for the other tasks. For example, the recorded run of `pp_file_claim_appeal` appealed one claim; the current evaluator requires "exactly the two most-urgent eligible claims".
- The published runs record four older code revisions (`git_sha` e3d33cd and 829b47b in v2, af41aa2 and c0ba550 in v3); the local clone is the squashed release 052f0f0.
- Consequence: published clean success for these 57 tasks describes another task. They are excluded from the pool until the study's own clean runs exist. Another 58 tasks fail although every action executed (Reddit 24, Robinhood 19 and others), which suggests further unflagged changes [unverified].

### 4.3 What the browser-use text observation carries (observed in code; inferred for the runs)

- browser-use 0.13.14 is installed in BreakingWeb's venv; its `DOMTreeSerializer.serialize_tree` emits a tag only for interactive, scrollable or iframe elements.
- Headings, landmarks and `th` reach the text only as their text nodes. Alt appears only as `image_alt=` on images inside interactive elements. Accessible names computed from `label[for]` are not printed; aria-label and placeholder are printed as attributes.
- The runs used the same family: the action-result format (`Clicked button "X" aria-label=…`, `checkbox-state=`) matches this version, and agents' thoughts quote lines such as `[7709]<button>See availability` and `[10]<a aria-label=Notifications />`. No run's thoughts quote a `<h2>`, `<nav>` or `<th>`. The runs' browser-use version is not in their manifests [unverified].
- This contradicts the Yin2026 close-read, whose Table 6 shows landmark and heading roles in the text agents' observation; the paper's own Appendix D.4 says the text observation "is not the raw accessibility tree".
- In browser-use runs, the page kinds reach the agent only through `find_elements` CSS selectors, `extract` (markdown keeps `#` headings and table header rows), and the screenshot, which the codemod keeps unchanged by design.

| | Gemini-3.1-Pro | Gemini-3-Flash | GPT-5.4 | GPT-5.4-mini | Opus-4.7 | Sonnet-4.6 |
|---|---|---|---|---|---|---|
| runs (valid) | 513 | 510 | 512 | 515 | 812 | 518 |
| `find_elements` naming a landmark tag or role | 0 | 2 | 3 | 1 | 29 | 19 |
| naming a heading | 2 | 1 | 4 | 2 | 3 | 0 |
| naming `th` | 0 | 0 | 3 | 0 | 1 | 0 |
| naming aria-label (names) | 7 | 15 | 23 | 7 | 54 | 43 |
| runs with any `extract` | 1 | 29 | 10 | 12 | 176 | 19 |

- Consequence (ours):
  - Under the stock browser-use harness, the headings, landmarks and tableheads variants are near-null by construction. Their effect would come from a few selector queries and `extract` calls, mostly by Claude models.
  - The labels variant reaches the agent only through aria-labels: 1,306 of 2,028 Gemini control actions have one.
  - Under the BrowserGym AXTree harness, all six kinds reach the agent, and the viewport flags of 3.2 are the relevant ones.
  - The harness choice therefore decides whether four of the six kinds can show an effect. It belongs in `STATUS.md` as a pending decision; this record does not decide it.

## 5. Candidate pools per kind

- Eligibility (n = 203 tasks): Gemini solved the task clean, the recorded run re-passes the evaluator on our build (a verified reference solution), and the task is not hardened.
- Tiers by how many of the six panel models solved the task: A = 4-6 (n = 160), B = 2-3 (n = 39), C = 1 (n = 4). Per env, eligible tasks: Amazon 52, Gmail 39, Booking 31, Reddit 31, Robinhood 23, patient portal 18, LMS 9.
- On-path: the flag is set on the Gemini path and on at least half of the other measured paths. Off-path: the flag is clear on the Gemini path and on every other measured path. Task lists are under `pools.<primary|strict>/<kind>` in the JSON. Tier-A counts:

| kind (definition) | on-path A (B) | off-path A (B) | envs with both, tier A | on-path dose, median | on vs off: mean Gemini steps, mean panel k |
|---|---|---|---|---|---|
| names (primary) | 128 (38) | 31 (1) | amazon, booking, gmail, reddit, rh | 3 | 8.8 vs 4.9 steps; 5.0 vs 5.5 |
| names (strict) | 74 (22) | 76 (15)* | 6 envs | 4 | 8.9 vs 7.2; 5.2 vs 5.1 |
| labels (primary) | 100 (36) | 55 (3) | all 7 | 2 | 9.2 vs 5.4; 4.9 vs 5.6 |
| labels (strict) | 50 (15) | 100 (22)* | 6 envs | 3 | 9.2 vs 6.9; 4.9 vs 5.3 |
| headings | 157 (39) | 2 (0) | gmail | 12 | — |
| landmarks | 160 (39) | 0 | none | 5 | — |
| tableheads | 24 (16) | 135 (22) | booking, gmail, pp, rh | 10.5 | 10.8 vs 7.5; 4.5 vs 5.2 |
| alt | 58 (6) | 102 (33) | booking | 16 | 9.7 vs 7.0; 5.2 vs 5.1 |

\* "Off" under the strict definition includes tasks with only weak loss.

Names in tier A by rung (`ladder_tierA`), none / weak / strong:

| env | none | weak | strong |
|---|---|---|---|
| all | 32 | 48 | 80 |
| Booking | 22 | 3 | 5 |
| Amazon | 3 | 0 | 43 |
| Gmail | 2 | 9 | 13 |
| Reddit | 3 | 13 | 9 |
| Robinhood | 2 | 9 | 8 |
| patient portal | 0 | 11 | 2 |
| LMS | 0 | 3 | 0 |

Labels in tier A, none / weak / strong: 58 / 47 / 55. Amazon 21/12/13, Booking 17/2/11, Reddit 10/9/6 and Robinhood 4/4/11 have all three rungs.

What the pools allow (ours):

- **Labels and table headers** have natural on-path and off-path tasks within the same env, so the contrast can be within env. For labels: Amazon, Booking, Reddit, Robinhood. For table headers: Booking (5 vs 25), Gmail (2 vs 21), Robinhood (2 vs 17). In the patient portal, 12 tasks are on-path and 1 is off-path.
- **Names**: the off-path tasks are mostly Booking, 22 of 31, while Booking supplies 8 of the 128 on-path tasks. Off-path tasks are also shorter (4.9 against 8.8 Gemini steps), so a task-level on/off contrast for names would mostly compare Booking with the rest. Two designs avoid this:
  - DQ-dose Option D within the same task: remove the kind only on the path's elements versus only off them. This needs instance-level targeting, which D-008 allows as an observation edit checked line by line against the source variant.
  - A within-env regression on dose: the primary dose ranges from 0 to 34 controls per path.
- **Headings and landmarks** are on nearly every path (157 of 160 and 160 of 160 tier-A tasks), so no off-path cell exists. Their contrast can only come from harness (browser-use carries none of it), from target region (Reddit, median 0.27 of targets inside a landmark), or from Option D.
- **Alt** is never the only name of a control on any path (0 of 330), and is present only in Amazon and Booking. Under AXTree it changes image nodes; under browser-use it changes the `image_alt` context of about 16 product images per Amazon path. It is a weak kind in this environment, with one within-env contrast (Booking, 12 vs 18).
- **Balance**: in every kind, on-path tasks are longer than off-path tasks, and for names and labels slightly less often solved. Any on/off comparison needs path length and panel success as covariates or matching (Miller2024: clustered errors; DQ-analysis).

## 6. Threats

- **Paths of older models stand in for the study's models.** The five checked models agree closely (3.3), but Opus-5.5, Sonnet-5 and GPT-5.6 may take other paths. Pilot clean runs of the study models should be checked against these flags, with agreement of at least 0.9 required (ours).
- **The selection uses outcomes.** The pool needs Gemini's success and a re-passing replay. Selection on one noisy run invites regression to the mean (Wei2026; DQ-tasks F10). Using panel tiers and models that are not the study's models reduces this but does not remove it.
- **Task drift.** Hardened tasks are excluded. Other changes are possible for the 58 tasks that fail with every action executed (4.2). The pool contains only tasks whose recorded solution passes on today's build.
- **The codemod is changing.** All variant checks used sha 71a8d729a8eac09d. Another workflow step is editing `codemod.py` (its README now lists `variant_gate.py` and `ua_delta.py`).
- **Date-dependent seeds.** The Robinhood, LMS and patient portal seeders call `datetime.now`, so the data differ by day. The page structure measured here does not depend on the data; element names that embed data (claim ids, prices) do.
- **The replay is not the agent.** Exposure counts what was on the page, not what the agent read or used. Whether an exposure matters is what the ablation measures.

## 7. Decisions this informs (proposals; for `STATUS.md`, not decided here)

- **Fix `codemod.py`'s `TAG_BODY` before any names or labels run.** Make the first alternative `[^<>{}]`, and handle props objects and deep nesting. Then re-run `variant_check.py` and require at least 98% agreement on both element kinds.
- **Choose the harness before freezing the kinds.** Under stock browser-use, headings, landmarks and tableheads carry almost no signal (4.3).
- **Use within-env on/off cells for labels and tableheads, and Option D (instance-targeted) or a dose regression for names.** Headings and landmarks have no off-path cell in BreakingWeb.
- **Re-run clean baselines on the local build for the pool tasks before predictions are committed**, and drop the 57 hardened tasks from any use of published outcomes.
