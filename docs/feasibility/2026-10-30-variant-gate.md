# Variant QA gate for the BreakingWeb source-level variants (2026-10-30)

> **Summary:** The booking headings variant now keeps page height and look: the 2026-10-29 look-keeping CSS added heading margins that beat the app's `* { margin: 0 }` reset, and missed Chromium's smaller h1 inside sectioning elements. The fix is general (cascade layer below all author CSS, same-specificity selector rewrite, sectioning rules) and holds on all 7 apps. A new gate, `variant_gate.py`, judges each env x kind variant against clean on build, console, page size, pixels against a measured clean-vs-clean floor, element boxes, DOM changes and a per-kind observation rule. On the 7 envs x 7 kinds (6 kinds plus the `none` sham), 48 of 49 cells pass. Booking `alt` fails: two seeded hotel photos return 404, so the clean page shows their alt text and the variant shows a broken-image icon. Of the 48 passes, 7 are the sham and 9 are no-ops (the kind changes nothing on the captured pages). That leaves 32 usable defect cells, all with changed observations and no other change found.

Serves: DQ-verify (findings 1, 2, 4, 5, 7, 12 and 15 of `../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-verify.md`) and D-008 (source-level variants are the reference). Follows the open items of [`2026-10-29-breakingweb.md`](2026-10-29-breakingweb.md) ("fix the booking headings variant"; pixel check not perceptual).

Scripts (`scripts/probe/breakingweb/`): `codemod.py` (revised), `variant_gate.py` (new), `ua_delta.py` (new, CSS check). Outputs: `/tmp/amt-syn/bw-gate/final/<env>/{clean0,clean1,clean2,<kind>}/` (captures, regenerable) and `/tmp/amt-syn/bw-gate/final/<env>/gate.json`. Copied here: [`2026-10-30-variant-gate.json`](2026-10-30-variant-gate.json) (per env x kind verdict, reasons, dose, codemod counts, specificity control) and [`2026-10-30-variant-gate-ua-delta.json`](2026-10-30-variant-gate-ua-delta.json).

## (a) The booking headings variant

**Question.** Why did booking `headings` change page height on 11 of 12 pages (feasibility batch of 2026-10-29), and can the fix be general rather than booking-specific?

**Cause (observed).** Two rules of the 2026-10-29 `codemod.py` (git `8b66c92`) differ from what a real heading gets:

1. It appended the headings' UA defaults (`margin-block: 0.67em` and so on) as unlayered author rules of zero specificity, after the app's CSS. Unlayered author rules beat each other by order when specificity ties, so these defaults beat booking's `* { box-sizing: border-box; margin: 0; padding: 0; }` (`breakingweb/environments/booking/src/booking.css:27`). A real `h1` gets its margin from the UA stylesheet, which every author rule beats, so in clean the reset wins and margins are 0. In the variant the replaced `div`s got margins back.
2. It gave every replaced `h1` `font-size: 2em`. Chromium's UA sheet makes an `h1` nested inside `article/aside/nav/section` smaller (1.5em at one level, down to 0.67em at five).

The shared stylesheet `shared/src/styles/base.css:23` only sets `box-sizing` on `*`, and amazon's `*` rule is the same (`amazon.css:29`), so only booking's reset carries margins. That is why booking alone changed height.

**Fix (in `codemod.py`, applies to headings, landmarks and tableheads alike).**

- The replaced tag's UA defaults go into `@layer amt-ua`. Any unlayered author rule beats a layered one whatever its specificity, which is the relation the UA stylesheet has to author CSS. The script refuses apps that already use `@layer`; none do.
- An author type selector `T` becomes `:is(T, R:where([data-amt="T"]))`, and `R` becomes `R:not(:where([data-amt]))`, where `R` is the replacement tag (`div` or `td`). Specificity stays (0,0,1), so the cascade order among the app's own rules is kept, and rules for `td` or `div` do not start to match converted `th` or headings.
- Chromium's h1 sectioning sizes are reproduced for replaced h1, and for real h1 inside a replaced `nav` or `aside`.
- The rewrite runs on the env's sources and on `shared/src` (shared components such as `FormField`, `SearchBar` and headers).

**Check 1: computed styles (`ua_delta.py`, Chromium 125.0.6422.26, the browser BrowserGym launches here).** It renders a fixture with headings at every level, h1 nested 1 to 6 sectioning levels deep, landmarks containing h1, and a table with `th`, under four kinds of author CSS. It then compares every computed property and box of all 49 elements between the real tags and the variant.

| kind | no author CSS | `*` margin/padding reset | tag rules | `tr {text-align:right}` |
|---|---|---|---|---|
| headings (new) | 0 / 49 differ | 0 | 0 | 0 |
| landmarks (new) | 0 | 0 | 0 | 0 |
| tableheads (new) | 0 | 0 | 0 | 1 (the `th`: `text-align` right vs center) |
| headings (2026-10-29, control) | 48 | 48 | 47 | 48 |
| landmarks (2026-10-29) | 48 | 48 | 49 | 48 |
| tableheads (2026-10-29) | 4 | 4 | 18 | 3 |

The one remaining difference is known. A real `th` uses `text-align: -internal-center`, which author CSS cannot write. It differs from `center` only when the row inherits a non-initial `text-align`. No app has such a row: the gate finds no pixel change in any tableheads cell.

**Check 2: the apps (gate, below).** Booking `headings` now passes on all 12 pages: page sizes are equal, 0 changed pixels, 0 box changes, and the observation diff matches the headings rule. The 2026-10-29 codemod rerun as a positive control (`headings@old`) fails on every page, as it should. 11 of 12 pages change height (home 2,367 → 2,466 px; reviews 109,230 → 117,321 px), 12 have box changes, and on 10 the observation also changes outside the heading lines. The diffs read on those pages are lines that enter or leave the viewport and `visible` flags that flip, which fits the taller page (ours). So the gate detects the original defect.

**How it could be wrong.** The CSS check covers Chromium 125 only. A run on another browser or version would need `ua_delta.py` rerun. The gate captures every page at rest. Hover, focus and open-menu states are not captured, and [Huang2026](../../../ai-accessibility-paper/literature/papers/L_Huang2026.md) found five of six silent CSS regressions in such states. A state-only change caused by a replaced tag would pass unseen.

## (b) The gate

`variant_gate.py capture ENV OUT` builds the env clean 3 times, then once per kind (codemod on env and shared sources), and restores the sources after each build. It captures the same pages as `variant_run.py`: 2 task start pages plus the env's static routes from `App.tsx` (7 to 17 pages). Per page it writes the BrowserGym viewport observation, the full observation (`filter_visible_only=False`), a DOM dump (tag, attributes, page box, own text, image-loaded flag, overflow) and a full-page screenshot. `evaluate` judges every variant page against `clean0`. A cell passes only if every page passes every check. Pages whose clean builds disagree count as unresolved and fail the cell (fail closed). None occurred.

| check | question | grounded in | how it could come out wrong | result that would change a decision |
|---|---|---|---|---|
| build | Does the variant compile, and did the look-keeping CSS survive minification? | ours | A build that passes but drops the `amt-ua` layer; checked by searching the built CSS | Any build failure or missing layer: the cell cannot be run |
| console | Does the variant add errors? | ours; DQ-verify finding 8 (function) | Errors that only appear after interaction are not captured | A new error: inspect, likely a codemod break of a component |
| size | Same page width and height (screenshot and `scrollWidth/scrollHeight`)? | 2026-10-29 batch (booking headings) | none known; exact equality | Any difference fails the page |
| pixels | Do changed pixels stay within what identical rebuilds produce? | [Jain2026](../../../ai-accessibility-paper/literature/papers/L_Jain2026.md) (exact RGB equality); [Zhang2026](../../../ai-accessibility-paper/literature/papers/L_Zhang2026.md), [Zheng2026](../../../ai-accessibility-paper/literature/papers/L_Zheng2026.md) (fixed similarity thresholds are uncalibrated, so the floor is measured) | Pixels inside loaded `<img>` boxes are excluded, so a change confined to a photo's raster would be missed (covered by same `src`, same box and load flag in the DOM check) | Share above the env floor, or any changed 8x8 block outside the clean-vs-clean noise region |
| layout | Same page box for every element? | ours | Boxes that differ between clean builds are exempt; 0 such elements found | Any box or overflow change fails |
| dom | Do the only element changes belong to the kind? | [Fiedler2021](../../../ai-accessibility-paper/literature/papers/L_Fiedler2021.md) (intended change present, unintended changes ruled out); [Jain2026](../../../ai-accessibility-paper/literature/papers/L_Jain2026.md) (invariants verified per mutant) | It compares element by element in document order. A codemod that adds or removes elements fails at once, which is correct but gives a coarse reason | Any other tag, attribute or text change fails |
| obs | Does the agent's observation change only as the kind allows? | DQ-verify finding 3 (check what the agent receives); [Chen2026a](../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md), [Covert2021a](../../../ai-accessibility-paper/literature/papers/L_Covert2021a.md) (a check must not find targets through the removed information) | The rules allow some secondary changes (below). A rule that is too loose would pass other kinds; tested by the specificity control | Any diff block the rule does not explain fails the page |

**Pixel tolerance and floor.** A pixel counts as changed if its summed RGB difference exceeds 30, the threshold used on 2026-10-29. The floor is the largest changed share over all clean-vs-clean pairs and pages (3 builds, 3 pairs per page). Each page also gets a noise region: the 8x8 blocks that changed in any clean pair, grown by one block. Also reported, but not gating: the share with images included and the rule applied to it, the exact (tolerance 0) share, and a block SSIM (8x8 grey blocks; mean and the minimum over 64x64-px tiles). The SSIM code first used float32 and gave SSIM(A,A) = 0.99996. It now uses float64 and gives 1.0 on identical images; all numbers below come from the corrected code.

**Observation rules per kind.** Targets are the elements whose DOM changed as the kind prescribes, matched by bid. The rule never searches for the removed role or name.

- `none`: identical text.
- `headings`: a target `heading` line disappears and its children move up one level; `StaticText` lines may appear in its place if their text is part of the heading's name (a real `div` heading keeps its text as `StaticText`; 2026-10-29 record).
- `landmarks`: the same for target lines with a landmark role; a target may also remain as a neutral line (`generic`, `Section`, `group`) with the same bid.
- `names`, `labels`, `alt`: only the name of a target line may change, together with the name of its ancestors whose role takes its name from content (ARIA accname). `StaticText` children of those lines may appear or vanish, because BrowserGym hides StaticText contained in the parent's name. For `labels`, a control whose `<label for>` was removed is a target, and the label may lose BrowserGym's `clickable` flag. For `alt`, target image lines may appear or vanish.
- `tableheads`: target `columnheader`/`rowheader` lines become `gridcell`/`cell` with the same bid and name.

**Controls.**

- Sham: `none` rebuilds without any change, judged like a defect.
- Positive control: `headings@old`, the 2026-10-29 codemod on booking. It must fail, and it fails on all 12 pages.
- Specificity control: each variant is judged by every other kind's DOM and observation rule. It must fail on every page where it changed anything. If a variant passed under another kind's rule, the rules would be too loose to tell the kinds apart.

## (c) Results: 7 envs x 7 kinds

Noise floor (observed): 3 clean builds per env, 228 clean-vs-clean page pairs in total. Outside image boxes the floor is 0 changed pixels on every env. Clean builds also produced identical observations and DOM structure on every page, with no attribute or box noise. With images included, only amazon has noise: product-photo rasters differ between identical builds, up to 0.18% of page pixels (`env_floor_share_with_images`; the sham reaches 1.6% of image pixels).

Verdicts. Cell entries: verdict; observation lines changed in the viewport / in the full observation; pages changed / pages captured. "no-op" = no observation change on any captured page.

| env (pages) | none | landmarks | headings | names | labels | alt | tableheads |
|---|---|---|---|---|---|---|---|
| amazon (17) | PASS, sham | PASS 1807/6947, 17/17 | PASS 114/368, 17/17 | PASS 197/325, 17/17 | PASS 46/46, 17/17 | PASS 28/340, 8/17 | PASS no-op (0 `th` in env source) |
| booking (12) | PASS, sham | PASS 472/27146, 12/12 | PASS 109/1337, 12/12 | PASS 17/132, 6/12 | PASS 16/52, 6/12 | **FAIL** pixels + layout on 3 pages | PASS no-op (6 `th`, not on captured pages) |
| gmail (8) | PASS, sham | PASS 1769/2723, 8/8 | PASS 20/28, 4/8 | PASS 316/537, 8/8 | PASS 22/48, 4/8 | PASS no-op (no `<img>` in source) | PASS 0/36, 2/8 |
| lms (7) | PASS, sham | PASS 692/886, 7/7 | PASS 34/44, 7/7 | PASS 84/108, 7/7 | PASS 4/4, 1/7 | PASS no-op (no `<img>`) | PASS 24/24, 3/7 |
| patient portal (9) | PASS, sham | PASS 1218/1927, 9/9 | PASS 64/78, 9/9 | PASS 136/209, 7/9 | PASS 34/48, 3/9 | PASS no-op (no `<img>`) | PASS 96/144, 6/9 |
| reddit (9) | PASS, sham | PASS 930/1272, 9/9 | PASS 84/108, 9/9 | PASS 232/1071, 9/9 | PASS 22/28, 3/9 | PASS no-op (no `<img>`) | PASS no-op (0 `th` in env source) |
| robinhood (14) | PASS, sham | PASS 777/1094, 14/14 | PASS 56/74, 13/14 | PASS 186/186, 14/14 | PASS 56/56, 14/14 | PASS no-op (no `<img>`) | PASS no-op (41 `th`, not on captured pages) |

In every passing defect cell: 0 changed pixels outside image boxes, equal sizes, 0 box changes, 0 new console errors. 0 target elements remain in the variant DOM (residual check: no `h1`-`h6`, no landmark tag or role, no aria-label on `a`/`button`, no `label[for]` or control aria-label, no `img[alt]`, no `th`). The `th` counts in the source come from the codemod's change counts. Each env also gets one `th` template from the shared `DataTable.tsx`, which the tableheads codemod rewrites too.

**Booking alt (FAIL, observed).** The seeded data (`breakingweb/backend/seeders/booking.py`) uses two Unsplash photos, `photo-1590490360182-c33d955e0bbf` and `photo-1549294413-26f195471c9c`. Both return HTTP 404, checked on 2026-10-30. On home (3 images), deals (5) and search (1), Chromium therefore draws the clean page's alt text ("Bob Hotel", "Mondrian London", …) inside the empty image box. Without alt it draws only a broken-image icon. Pixels change in 0.16 to 0.42% of the page, all outside the noise region, and the minimum SSIM tile falls to 0.46. The images also gain a vertical overflow. This difference is real for a sighted user. The cause is the environment's dead assets, not the codemod. For a sighted user, alt text is visible content whenever an image fails to load. Possible remedies: replace the two dead URLs in the seed data for both arms, or keep booking `alt` out of the alt cell. Choosing one is a design decision; this record does not take it.

**Labels: what the gate allows.** On 18 labels, all for text, number, tel or email inputs (amazon settings 1, patient portal profile 11, reddit submit 3, robinhood alerts and transfers 3), clicking the label text no longer focuses the input once its `for` is removed. BrowserGym drops the label's `clickable` flag accordingly. This is part of the real defect (F68: a visible text not associated with its control), and the gate allows it. But it is a change in mouse function, not only in information. No checkbox or radio label is affected on the captured pages; there the click would toggle the control.

**Specificity control (observed).** Every defect variant with a change failed under all 6 other rules on exactly the pages where its DOM changed: amazon 17/17/17/17/9 pages for landmarks/headings/names/labels/alt; booking 12/12/6/6/3; and likewise on the other envs. No variant passed under another kind's rule.

**Codemod risks reported.** Reddit's CSS has one `*-of-type` selector. Replacing a tag changes the sibling type count it depends on, which could change styling, but pixels show no change on reddit's 9 pages for landmarks, headings or tableheads. No env has attribute selectors on removed attributes, and no script queries the replaced tags.

## What this does not show

- Pages are captured at rest. Hover, focus, open menus and states reached only inside a task (forms opened by a flow, table views behind filters) are not covered. Labels and table heads are mostly in such states (2026-10-29 record). The gate has to be rerun on task-path states, for example on the replay states of `path_replay.py`, before a cell's PASS covers the task.
- The 9 no-op cells pass trivially. `alt` exists only in amazon (17 `img` in source) and booking (5); it cannot be studied on the other five apps. Tableheads in booking and robinhood are in source but on no captured page, so they need task-path capture before any claim.
- The pixel check excludes loaded-image boxes, so its zero floor holds outside images only. On amazon, the rule with images included would fail several variants on pages where the sham passes (landmarks 5, names 1, labels 6, alt 5 pages). That is image raster noise: the sham's own image-pixel changes reach 1.6%, and the DOM shows the same `src` and box.
- Function beyond the label click is not tested: no actions are replayed on both versions (DQ-verify finding 8). That is the next check.
- The observation is the BrowserGym flattening only. The leaderboard's browser-use serialisation is not gated here.

## Reproduce

```bash
# private copy so builds do not touch a served checkout; binds stay on 127.0.0.1
cp -a ~/.workspace/_refsrc/BreakingWeb /tmp/amt-syn/bw-gate-src/
/tmp/amt-syn/bw-gate/run_final.sh /tmp/amt-syn/bw-gate-src/BreakingWeb 8097 /tmp/amt-syn/bw-gate/final booking amazon gmail lms patient_portal reddit robinhood
~/.workspace/_refsrc/BreakingWeb/.venv/bin/python scripts/probe/breakingweb/variant_gate.py summary /tmp/amt-syn/bw-gate/final
~/.workspace/_refsrc/BreakingWeb/.venv/bin/python scripts/probe/breakingweb/ua_delta.py /tmp/amt-syn/bw-gate/final/ua_delta.json
```

`run_final.sh` runs `capture` (3 clean builds and every kind; booking also `headings@old`, which needs the 2026-10-29 codemod at `/tmp/amt-syn/bw-gate/codemod_2026-10-29.py`, i.e. `git show 8b66c92:scripts/probe/breakingweb/codemod.py`) and `evaluate` per env. The run of 2026-10-30 used two copies in parallel (ports 8097, 8098) and took 31 minutes. After the run, all three checkouts had only the four allowed bind-fix diffs.
