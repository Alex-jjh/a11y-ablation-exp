# Feasibility record: BreakingWeb as the main environment (2026-10-29)

> **Summary:** BreakingWeb runs locally on this machine; source-level accessibility defects can be written into its React apps with the page's look and function intact, and their footprint in the agent's observation matches real-world defect forms. A naive observation-layer emulation does not (it drops heading text), so observation edits must be calibrated against source-level variants. The clean apps carry much richer aria-labels than typical real sites. Opus 5.5, Sonnet 5 and GPT-5.6 answer through the managed Bedrock profile.

Research question it serves: the redesign's DQ-layer, DQ-form, DQ-dose, DQ-env and DQ-verify (`../../../ai-accessibility-paper/literature/papers/README.md`). Scripts: `scripts/probe/breakingweb/` (copied from `/tmp/amt-syn/bw-probe/` on 2026-10-29); outputs: `/tmp/amt-syn/bw-variants/`.

## Setup (observed)

- Code: `github.com/Arvid-pku/BreakingWeb` (paper: Yin2026, NeurIPS 2026 D&B), shallow clone at `~/.workspace/_refsrc/BreakingWeb`. **No LICENSE file**: local research use only; redistributing modified environments needs the authors' permission.
- Installed with uv (Python 3.12.15, `--extra browser-use`), pnpm 10.15.0 (the version the repo pins; corepack's default 12.x fails), Node 24. All 7 frontends build.
- Security: the repo's launch script and `app.py` bind the backend to `0.0.0.0`; changed in the local clone to `127.0.0.1` (`app.py` default, `scripts/breakingweb.sh`, `_sweep_common.sh`, `run_gmail_sweep.sh`) and verified the listener on `127.0.0.1` only. No server is left running between probes.
- Run probes with `BREAKINGWEB_AUTO_BUILD_FRONTENDS=0` and Node 24 + pnpm on PATH; otherwise the backend's own auto-build fails at startup.
- LLM access: AWS profile `codex-DO-NOT-DELETE` (credential process, Bedrock invocation only; `~/.aws/config` has only the profile line). Smoke test: `us.anthropic.claude-opus-5-5` (us-west-2) MODEL_OK, `us.anthropic.claude-sonnet-5` MODEL_OK, `us.openai.gpt-5.6-sol` (us-east-2) MODEL_OK; `us.anthropic.claude-opus-5` returned empty text.

## What the agent observes

- The leaderboard's "text (a11y tree)" agents run the **stock browser-use** harness, not BrowserGym (all 519 clean trajectories of Gemini-3.1-Pro in `BreakingWeb/breakingweb-results-v2`: harness `stock-browser-use`). Browser-use serialises the DOM with attributes such as `aria-label=…`. The repo also ships a BrowserGym harness (`breakingweb/agent.py`: `axtree_object` → `flatten_axtree_to_str(..., filter_visible_only=True, filter_with_bid_only=True)`), which this record measures.
- `filter_visible_only=True`: the BrowserGym observation contains only what is in the viewport (e.g. Amazon home: 95 visible lines of 439).
- Heading level is in the tree (`level` property on every heading) but never in the observation text: 0 heading lines with a level on all 7 start pages. Same as in the old WebArena data.

## The clean apps are richly labelled (observed)

Start pages, BrowserGym tree: every app has banner, navigation and main or equivalent landmarks, several named (`navigation 'Main navigation'`); no unnamed button, link or textbox; headings on 6 of 7; tables only on LMS and the patient portal.

On the task path (Gemini-3.1-Pro clean trajectories, 7,473 steps; targets the agent acted on): most buttons and links carry an aria-label that is more specific than their visible text, e.g. visible "Add to Cart" with aria-label "Add 23Pcs Resistance Bands Set…", visible "Sports" with aria-label "Browse Sports & Outdoors". Per env, acted-on links/buttons with an aria-label vs text only:

| env | link aria / text | button aria / text | aria-only (icon) buttons |
|---|---|---|---|
| amazon | 175 / 126 | 338 / 88 | 99 |
| booking | 10 / 248 | 54 / 601 | 0 |
| gmail | 336 / 0 | 929 / 51 | 324 |
| lms | 328 / 0 | 503 / 0 | 0 |
| patient portal | 154 / 0 | 287 / 0 | 0 |
| reddit | 178 / 0 | 526 / 96 | 0 |
| robinhood | 73 / 359 | 397 / 118 | 0 (22 aria-only links) |

Reading (ours): typical real sites repeat generic control text ("Add to Cart", "Read more"; WCAG 2.4.4) and leave icon buttons empty (WebAIM2026: empty buttons on 30.6% of home pages); these apps are labelled more richly than that, plausibly because they were generated. The clean condition is therefore an over-annotated web, and removing aria-labels moves the page toward the common real state rather than away from it. This is a grounding for the `names` ablation and a scope statement for the paper.

## Source-level defects (codemod) vs observation-layer emulation

`codemod.py` rewrites the app's JSX the way a developer who omitted the semantics would have written it, keeps every class and handler, and rewrites CSS type selectors to `:is(tag,[data-amt=tag])` plus UA-like defaults with zero specificity, so the look is kept. Kinds: landmarks (header/nav/main/footer/aside → div, landmark roles dropped), headings (h1–h6 → div; failure F2), names (aria-label off buttons/links), labels (htmlFor and control aria-labels off; visible text kept; F68), alt (img alt off), tableheads (th → td; F91).

Amazon, 2 task start pages + 15 routes, clean vs variant (BrowserGym text; full-page screenshots):

- Noise floor: clean rebuild vs clean, 0 observation lines changed, pixels differ on 0–0.1%.
- headings: on the home page 5 lines `heading 'X'` become `StaticText 'X'`; text kept, role and bid gone. Pixels 0.13–0.27%.
- names: `button 'Submit search'` → `button ''`, `link 'Notifications, 1 unread'` → `link '1'`, `link 'Shopping cart, 0 items'` → `link '0 Cart'`, `link 'Open <product title>'` → `link '<product title>'`, `link 'Browse subcategory Earbuds'` → `link 'Earbuds'`; 4–11 of 48–128 visible lines per page. Pixels within the noise floor.
- labels: only the settings page among the 15 routes has form controls in view (`combobox 'Language'` → `combobox ''`, `textbox 'Currency'` → `textbox ''`); address and checkout forms open in flows not reached by route.
- landmarks: the banner line disappears and its subtree is re-indented (38 of 95 visible lines change on the home page).

Observation-layer emulation (editing `axtree_object` before flattening) on the same page:

- role `heading` → `generic` makes BrowserGym drop the whole line, **text included**, whereas the source-level variant keeps `StaticText 'X'`. Naive emulation therefore removes information a real defect keeps.
- clearing names on buttons/links reproduces `link ''`; the source-level variant instead falls back to visible text (`link 'amazon'`), so emulation must compute the fallback name, not blank it.
- the page is untouched, so every bid stays actionable (click on an emptied link: no error).

Consequence for the design (ours): source-level variants are the ground truth for each kind; any observation-layer edit is used only where its output matches the source-level variant line by line. Source-level variants also apply unchanged to every harness (BrowserGym tree, browser-use DOM, screenshots), while observation edits must be rebuilt and recalibrated per harness.

## All environments × all kinds (observed, batch of 2026-10-29)

`scripts/probe/breakingweb/batch.sh`: per env, 2 task start pages plus the env's static routes from `App.tsx` (8–17 pages); per kind, a source-level variant built, captured and compared with the clean build; sources restored after each run (49 runs, none failed). "visible" = lines of the BrowserGym observation (viewport only) that the variant removed or changed; "pages" = pages with any change.

| env | landmarks | headings | names | labels | alt | tableheads | noise (pixels) |
|---|---|---|---|---|---|---|---|
| amazon (17 pages) | 17 pages | 17 pages, 57 lines | 17 pages, 87 lines | 1 page, 3 lines | 8 pages, 14 lines | 0 | ≤0.08% |
| booking (12) | 12 | 12, 123 | 1, 2 | 3, 0 visible | 3, 6 | 0 | 0 |
| gmail (8) | 8 | 4, 10 | 8, 165 | 0 | 0 | 2, 0 visible | 0 |
| lms (7) | 7 | 7, 17 | 7, 42 | 0 | 0 | 3, 12 | 0 |
| patient portal (9) | 9 | 9, 29 | 7, 71 | 1, 11 | 0 | 6, 48 | 0 |
| reddit (9) | 9 | 9, 42 | 9, 44 | 2, 6 | 0 | 0 | 0 |
| robinhood (14) | 14 | 13, 27 | 14, 86 | 14, 26 | 0 | 0 (41 `th` in source, none on these pages) | 0 |

- landmarks change most observation lines on every page, but mostly by re-indentation; the removed content is the landmark lines themselves.
- Dose differs by more than an order of magnitude between apps for the same kind (names: gmail 165 visible lines, booking 2). Task choice must put each kind on the task path (the brief's on-path / off-path cells).
- Labels and table heads are rare on routes: forms open inside task flows, so their dose has to be measured on trajectories, not routes.
- Visual equivalence: every variant is within 0.3% changed pixels (the clean-vs-clean noise floor is 0–0.1%) **except booking headings**: 11 of 12 pages change height, up to 1.24% of pixels. The heading look-preserving CSS does not cover booking's styles; this variant is not usable until fixed.
- Per-run JSON reports: `2026-10-29-breakingweb-batch/<env>__<kind>.report.json` (copied from `/tmp/amt-syn/bw-variants/`; captures and screenshots stay in /tmp and are regenerable with `batch.sh`).

## Open

- Fix the booking headings variant (page height changes).
- Function check (mouse and keyboard) for each variant on the task path; full-page pixel equivalence uses a 30-level per-pixel threshold, not perceptual.
- Dose on the task path from trajectories (by role and name of acted-on elements) rather than from routes.
- Browser-use serialisation of the same variants.
