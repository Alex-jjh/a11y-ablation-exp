# Function equivalence of the BreakingWeb source-level variants on the gate pages (2026-10-30)

> **Summary:** On the 76 gate pages of the 7 apps, every click on a clickable element, every Enter and Space on a button, and the Tab order have the same effect on every variant that passed the gate as on the clean build, with one exception the defect implies: under `labels`, clicking 37 label texts (42 trials) no longer focuses their control. The effect of each action is its URL, backend requests, DOM mutations, dialogs, focus, element count, console errors and the screenshot after the action. 24,419 trials ran on 59 builds. Two clean builds per app set the noise floor and the `none` sham tested it. 30 trials were flagged across the sham and the defect cells; all 30 were cleared when rerun 3 times on fresh builds. A known-answer control that silently breaks handlers and Tab stops was flagged and confirmed on 98 of 98 flagged trials. Decision per cell: function is preserved in all 41 cells run or byte-identical, with `labels` preserved except the label click (F68). The evidence is strong for `names`, `landmarks`, `labels` and amazon `alt`, because the trials act on changed elements. It is weak for `headings` (72 of 2,426 targets touch a changed element) and empty for `tableheads` (0 targets), so for those two kinds it only shows that nothing else broke.

Serves: DQ-verify finding 8 (functional equivalence by replaying the same actions on both versions) and finding 18 (read against an empirical noise floor), in `../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-verify.md`; D-008 ("page function is kept"). Follows the gate record [`2026-10-30-variant-gate.md`](2026-10-30-variant-gate.md) ("Function beyond the label click is not tested").

Scripts (`scripts/probe/breakingweb/`): `click_effect.py` (new: enumerate, run, evaluate, recheck, summary; `pc_break` control), `click_treated.py` (new: which targets the kind changed). Outputs: `/tmp/amt-syn/bw-fx/final/<env>/` (targets, per-build `trials.jsonl`, clean0 reference screenshots, clean1 masks, recheck runs, `function.json`, `treated.json`; 454 MB, regenerable). Copied here: [`2026-10-30-function-equivalence.json`](2026-10-30-function-equivalence.json) (per env: trial counts, calibration, coverage, treated targets, per-cell verdicts with counts and examples; label clicks by control type).

## Method

**Question.** When a sighted user clicks, presses Enter or Space, or tabs on a variant page, does the same thing happen as on the clean page?

**Pages and targets (observed counts).** The pages are the gate's pages: 2 task start pages per app plus its static routes, 76 pages. One page differs from the gate. On amazon, the product page reached from the first task page is `product_345`, while the gate captured `product_36` from the search page. The two use the same template. On the clean0 build, `click_effect.py` lists every element that has an interactive role in Chrome's accessibility tree, a React click or pointer handler, a non-inherited `cursor: pointer`, or is a `<label>`. It keeps an element only if a hit test at its click point lands on it. Elements whose click points hit the same element are merged. Of 3,771 clickable elements, 2,112 are kept (cap 40 per page; 3/4 of the cap for the first viewport; 488 kept targets lie below the fold). Pages under the cap keep all their elements: lms, patient portal and robinhood keep 100%, amazon 78%, gmail 76%, booking 37%, reddit 31% (its feed pages have 252 each). 361 focusable buttons get Enter and Space trials (cap 8 per page). Each page also gets one Tab trial: up to min(focusable + 2, 60) presses, 2,546 presses per build. 10 pages on amazon, booking and reddit have more than 58 focusable elements, so their Tab trial covers only the first 60 stops.

**Isolation.** Each trial opens its page in a new backend session (the seed BrowserGym uses) and a new browser context, so no server or browser state carries over. The page's `Date` starts at the same instant on every load and then runs. Navigations to other hosts are blocked and recorded. Each build is served on 127.0.0.1.

**Do the trials act on anything? (observed, clean0).** Of the 2,112 clicks, 1,785 (85%) mutate the DOM, 1,485 make backend requests, and 239 send a POST, PUT, PATCH or DELETE. 320 (15%) do nothing visible: no mutation and no request.

**Measurements.**

| measurement | question | grounded in | how it could come out wrong | result that would change a decision |
|---|---|---|---|---|
| click at the clean element's centre, same page coordinates on the variant | Does a mouse user's click do the same? | [Mirshokraie2014](../../../ai-accessibility-paper/literature/papers/L_Mirshokraie2014.md) (replay the same events on both versions and compare the observable state); gate: boxes identical, so the same point hits the same element | The target list misses handlers bound outside React (`addEventListener`) on elements with no role and no pointer cursor | A confirmed mismatch on any target fails the cell |
| Enter and Space on focused buttons; Tab sequence | Does a keyboard user get the same activation and order? | ours: none of the six kinds changes focusability, so any change is damage | `element.focus()` reaches buttons that Tab would not; the Tab trial stops at 60 presses on 10 pages | Any confirmed change in the Tab sequence or key effect fails the cell |
| effect signature: URL, `/api/` requests (method, path, status), mutation count, visible dialogs/menus/popovers, `position:fixed` count, focused element, element count, console errors, scroll, popups and blocked navigations | What did the action do? | [Salehnamadi2023](../../../ai-accessibility-paper/literature/papers/L_Salehnamadi2023.md) (compare states around each action, flag an action without effect); [Huang2026](../../../ai-accessibility-paper/literature/papers/L_Huang2026.md) (no new console errors is a weak check alone) | Fields are counts and identities, not full DOM states: a change that keeps all counts equal and changes no pixel in the viewport passes | — |
| viewport screenshot after the action vs clean0 | Does the state after one action look the same? | gate pixel rule (tolerance 30); [Huang2026](../../../ai-accessibility-paper/literature/papers/L_Huang2026.md) (most silent CSS regressions show only in hover, focus or open states) | Viewport only; loaded-image boxes excluded (amazon rasters vary between identical builds, gate record) | A confirmed pixel change fails the cell |
| clean1 vs clean0, per trial and field | How much does an identical rebuild differ? | DQ-verify finding 18 | Two clean runs can miss rare noise; the sham is a third run made later | Noise fields of a trial are not held against the variant |
| `none` sham, judged like a variant | Does the comparison flag an unchanged build? | DQ-verify finding 9 (sham control) | The rules were revised after the first sham results (below), so the sham is not held out for those revisions | Any sham flag that survives recheck means the comparison is not usable |
| `recheck`: each flagged trial 3 times on a fresh clean build and 3 times on a fresh variant build, with a longer settle (network idle 1 s, cap 15 s, scroll position stable) | Is a flag a real difference or timing? | DQ-verify finding 16 (fail closed: an unresolved case is not counted as equivalent) | 3 runs per arm can still miss rare timing; a real difference that appears in only some runs is cleared | A confirmed trial fails the cell |
| `pc_break`, a known-answer control: every 2nd `<button>` with `onClick` gets `onDoubleClick` instead, every 2nd link gets `tabIndex={-1}`; same markup and look | Can the comparison detect broken function at all? | DQ-verify finding 12 (positive controls through the same analysis) | Run on lms and patient portal only | If it were missed, the preserved verdicts would be uninformative |

**Comparison rules.** A field that agrees between clean0 and clean1 must agree in the variant. A field that does not agree may take either clean value. Rules revised during the run, in order (observed causes):

1. gmail and reddit search add `_t=<Date.now()>` to the URL. Epoch-millisecond values are replaced by `{ts}`.
2. Mutation counts differ between identical builds by up to 1.67× (robinhood 35 vs 21, gmail 349 vs 241). Counts agree if they differ by at most max(5, half the larger count). With exact buckets, the sham was flagged on 10 robinhood trials.
3. Small pixel differences of 1 to 3 px recur at fixed places, for example amazon's header at (860, 47). Pixels are also allowed in an app-wide noise region: blocks that changed in any clean1 trial with ≤ 921 px (0.1% of the viewport).
4. Amazon's "Back to top" button scrolls smoothly, so the screenshot catches the scroll at different points (scroll position 807 vs 908). A trial whose action scrolls, and differs only in scroll position and pixels, is marked unresolved and goes to recheck.
5. The recheck's pixel test first did not exclude image boxes. On the amazon sham it confirmed 1 trial (deals page, 1,329 vs 198 changed px, all inside product photos). Image boxes are now excluded, as in the main comparison, and the verdicts were recomputed from the saved runs.

`labels` mismatches on a `<label>` whose `for` was removed are classed as expected when they consist only of focus and what follows from it: the focus ring's pixels, mutations, and the scroll that brings a focused control into view.

## Results (observed)

Noise floor (clean1 vs clean0, per build of an app): 0 unstable trials on gmail, lms, patient portal, reddit and robinhood after rules 1 and 2. Booking has 7 of 581 unstable trials; for example, Enter on a notification sent `POST …/read` in one build and not in the other. Amazon has 60 of 786, all pixel-only.

Cells (Tab, click and key trials per build: amazon 786, booking 581, gmail 390, lms 87, patient portal 266, reddit 438, robinhood 362). Entry: verdict; trials flagged before recheck, of which confirmed; expected label clicks.

| env | none (sham) | landmarks | headings | names | labels | alt | tableheads |
|---|---|---|---|---|---|---|---|
| amazon | preserved; 6 flagged, 0 confirmed | preserved; 3, 0 | preserved; 5, 0 | preserved; 3, 0 | preserved except label click; 4, 0; 4 label clicks | preserved; 2, 0 | preserved; 1, 0 |
| booking | preserved; 0 | preserved; 2, 0 | preserved; 2, 0 | preserved; 1, 0 | preserved except label click; 1, 0; 9 | not run (gate FAIL) | preserved; 0 |
| gmail | preserved; 0 | preserved; 0 | preserved; 0 | preserved; 0 | preserved; 0; 0 | identical bundle | preserved; 0 |
| lms | preserved; 0 | preserved; 0 | preserved; 0 | preserved; 0 | preserved except label click; 0; 2 | identical bundle | preserved; 0 |
| patient portal | preserved; 0 | preserved; 0 | preserved; 0 | preserved; 0 | preserved except label click; 0; 12 | identical bundle | preserved; 0 |
| reddit | preserved; 0 | preserved; 0 | preserved; 0 | preserved; 0 | preserved except label click; 0; 7 | identical bundle | preserved; 0 |
| robinhood | preserved; 0 | preserved; 0 | preserved; 0 | preserved; 0 | preserved except label click; 0; 8 | identical bundle | preserved; 0 |

- **All flags were timing.** 30 trials were flagged in total: 6 in the amazon sham and 24 in defect cells (amazon 18, booking 6). All 24 amazon flags are "Back to top" (smooth scroll still running). With the scroll allowed to stop, every clean and variant run ended at scroll 0 with the same screenshot. Booking's flagged account-page search sent `POST /properties/search` in clean0 and clean1 but not within 5 s in the landmarks and headings runs. Those trials took 6.3 s against 1.8 s, and in all 3 rechecks on each arm the POST was sent. The other 4 booking flags were 2 changed pixels on the messages page (3 trials) and one scroll position after Enter on the page-2 button. 0 of 30 were confirmed.
- **Keyboard.** The Tab sequence was identical in every cell and on every page: 2,546 presses per build. Enter and Space matched on all 361 buttons per build.
- **Label clicks (expected, F68).** On 37 labels whose `for` was removed (42 trials on 6 apps), a click on the label text leaves focus on the body instead of the control. On patient portal and booking, the clean page then also scrolls the control into view. By control type: 22 `select`, 18 text-like inputs (text, tel, email, number, one without a type), 1 `textarea`, 1 whose control id was not found in the gate dump. The gate counted 18 such labels, only text-type inputs at rest, and missed the selects. On gmail no label click changed: its `FormField` label wraps the control, so the label still focuses it without `for`.
- **Positive control.** `pc_break` renamed 16 handlers and 7 Tab stops on lms, and 21 handlers and 5 Tab stops on patient portal. On lms all 7 Tab trials were flagged, because the sequence changed on every page. On patient portal 91 trials were flagged: 39 clicks, 26 Enter, 26 Space, for example "Cancel" opens no dialog (element count 176 vs 168), and "Show past appointments" shows nothing (236 vs 168, 2.2% of pixels). The recheck confirmed all 98. Patient portal's Tab sequences did not change, so its changed links are not on the captured pages (inferred); the Tab side of the control was tested on lms only.

**Treated targets (`click_treated.py`; observed).** These counts show which trials act on an element the kind changed. They exclude amazon's product page, which the gate did not capture. Clicks and keys together, n = 2,426:

| kind | the element itself changed | a descendant changed | an ancestor changed | untouched |
|---|---|---|---|---|
| landmarks | 0 | 0 | 2,220 | 206 |
| headings | 7 (reddit post titles) | 65 (links that contain a heading) | 0 | 2,354 |
| names | 1,082 | 26 | 2 | 1,316 |
| labels | 155 (labels and inputs) | 15 | 0 | 2,256 |
| alt (amazon only) | 0 | 85 (product links with an image) | 0 | 556 on amazon |
| tableheads | 0 | 0 | 0 | 2,426 |

## Decisions per cell

**Function preserved (observed).** All 41 cells that passed the gate:

- 36 cells were run and are preserved: 6 kinds on amazon, 5 on each other app.
- 5 `alt` cells on gmail, lms, patient portal, reddit and robinhood built byte-identical to clean, so they are preserved by construction.
- The 7 sham cells are preserved.

How much a cell says depends on the treated counts above (ours):

- `names`, `landmarks`, `labels`: preserved, with direct evidence. Most trials act on a changed element or inside a changed landmark.
- `labels`: preserved except the label click. The decision to make is whether a label that no longer focuses its control fits "the page stays the same for a sighted mouse user". It is the defect itself (F68), so removing it would remove the defect. Recommendation (ours): keep `labels` and report the label-click change as part of the treatment. 42 of the 2,910 `labels` trials are affected, all on label texts.
- amazon `alt`: preserved. 85 clicks are on links that contain an image whose alt was removed.
- `headings`: preserved, with weak evidence: only 72 targets touch a changed heading.
- `tableheads`: no function evidence. No target is in or near a converted `th`. Converted header cells appear on captured pages of 3 apps (gmail, lms, patient portal; gate record), and none of them is clickable. For tableheads, the check shows only that nothing else broke.
- booking `alt`: not run (gate FAIL on dead images).

**What would change these decisions.** A confirmed mismatch in a recheck on task-path states. Also any sortable or clickable table header (`th` with a handler) on a task path: the task path is where tableheads would get function evidence.

## What this does not show

- **One action deep, at rest.** Each trial is one action from a page at rest. It does not cover sequences: typing into a field and submitting, filters followed by a sort, a menu item inside an opened menu. Those are the states the gate also did not cover. The next step is to replay recorded task paths (`path_replay.py`) on clean and variant and compare per step.
- **Caps.** 1,659 clickable elements were not clicked (cap 40 per page; reddit feeds, booking, amazon). Tab covers only the first 60 stops on 10 pages. Enter and Space cover 361 of the buttons (cap 8 per page).
- **Signature fields are summaries.** Two states with the same URL, requests, counts, focus and viewport pixels count as equal even if off-screen content differs in text. The mutation tolerance (factor 2 above 10) would miss a change that only alters how many nodes update. The positive control shows that broken handlers and Tab stops are caught. It does not show that subtler changes are caught.
- **Rules were tuned on the data.** Rules 1 to 5 were set after seeing clean1 and sham results, so the sham is not a held-out test of them. The known-answer control was judged with the final rules and still caught all 98 flagged trials. The recheck gives an independent test of every flag.
- **Raw data.** Booking's recheck clean runs for landmarks, headings and names were overwritten by the next recheck's clean run before the directory layout was fixed. Their verdicts (all cleared) were computed before the overwrite and are in `recheck_<kind>.json`.
- **No LLM was called.** No Gemini and no other model.

## Reproduce

```bash
# 7 private copies (one per app) so builds never touch a served checkout; binds stay on 127.0.0.1
for i in 1 2 3 4 5 6 7; do mkdir -p /tmp/amt-syn/bw-fx-src$i && cp -a /tmp/amt-syn/bw-gate-src/BreakingWeb /tmp/amt-syn/bw-fx-src$i/; done
# drive + evaluate per app (amazon on copy 1 ... robinhood on copy 7; booking without alt), 2 workers each, ~2.5 h for amazon
/tmp/amt-syn/bw-fx/run_env.sh /tmp/amt-syn/bw-fx-src1/BreakingWeb 8111 /tmp/amt-syn/bw-fx/final amazon none,landmarks,headings,names,labels,alt,tableheads --max-clicks 40 --max-keys 8 --workers 2
# known-answer control
/tmp/amt-syn/bw-fx/run_env.sh /tmp/amt-syn/bw-fx-src4/BreakingWeb 8114 /tmp/amt-syn/bw-fx/final lms pc_break --max-clicks 40 --max-keys 8 --workers 2
# retest flagged trials (3 runs per arm), then evaluate again and summarise
/tmp/amt-syn/bw-fx/recheck_env.sh /tmp/amt-syn/bw-fx-src2/BreakingWeb 8112 /tmp/amt-syn/bw-fx/final booking none landmarks headings names labels tableheads
python click_effect.py summary /tmp/amt-syn/bw-fx/final
# treated targets (clean build in BW_ROOT)
python click_treated.py /tmp/amt-syn/bw-fx/final /tmp/amt-syn/bw-gate/final amazon
```

The run of 2026-10-30 started at 08:07 and the last recheck ended at 10:10. Script hashes at launch and at the end are in `/tmp/amt-syn/bw-fx/final/script_hashes*.txt`. The edits to `click_effect.py` during the run changed the evaluation, the recheck, `pc_break` and an opt-in long settle; the trial code used by every main run did not change. After the run, the main clone, `bw-gate-src` and all 7 copies showed only the 4 allowed bind-fix diffs, and no server or browser was left running.
