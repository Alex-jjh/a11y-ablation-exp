# Real-world exemplar kit: capture route, offline detector, and known-answer tests (2026-11-02)

> **Summary:** A kit for showing that each v2 defect kind exists on real sites in the form our variants produce. Alex saves real pages in his own Chrome with a DevTools snippet: rendered DOM, cleaned of personal data, as one JSON file, or MHTML for logged-out pages. `analyze.py` opens the saved pages in headless Chromium with scripts and network off. It computes the AX tree and the BrowserGym text and reports, per kind, instances, examples and a verdict against the codemod's form. On 13 fixture pages in both formats every expectation holds. The JSON keeps none of 14 planted secrets, while MHTML keeps 10. Two hostile pages reached a loopback beacon 0 times and ran no script. On 532 saved BreakingWeb pages (76 pages x clean + 6 variants), every new instance in a variant sits on or next to an element the codemod changed. The two formats agree on every count. Detection: alt 206/206, tableheads 13/13, labels 138/173 (the rest are still labelled), landmarks on every page (page verdict) and 227/279 containers. For names, the detector reports exactly the rungs it is built for: 152 empty, 162 glyph-only and 307 of 340 shared names. Headings 879/1002 with two tiers, 208 with the strict tier alone. Clean BreakingWeb is not defect-free. It contains the names form naturally (booking: "See deal" x20, "Property" x577; reddit: aria-label "Upvote" on all 81 posts), and reddit has no `<main>`. All heading and landmark thresholds were set on these same BreakingWeb pages, so how precise they are on real sites is still open. No real site was fetched.

Serves: Alex's request of 2026-11-02 (real-world exemplars of each violation, captured by him in Chrome); DQ-form findings 1 to 6 and 8 (`../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-form.md`); D-008 (the source-level variants are the reference form).

Files (`scripts/realworld/`): `CAPTURE.md` (instructions), `capture_snippet.js` (the DevTools snippet), `TARGETS.md` (sites), `analyze.py` (the detector), `harness.py` (saves pages we serve ourselves the way Alex saves real ones), `selftest.py` (fixtures, privacy, isolation), `fixtures/` (13 pages and one stylesheet), `bw_kit_test.py` (BreakingWeb capture, analysis, evaluation, strip check). Compact results: [`2026-11-02-realworld-kit.json`](2026-11-02-realworld-kit.json). Raw outputs (regenerable): `/tmp/amt-syn/rwk/selftest/`, `/tmp/amt-syn/rwk/bw/{captures,analysis,evaluation.json,stripcheck.json}`.

## (a) The capture route

| rule | what | grounded in | how it could be wrong | what would change a decision |
|---|---|---|---|---|
| rendered DOM | The snippet saves the DOM after scripts ran, open shadow roots included (`getHTML` with `<template shadowrootmode>`) | WebAIM measures "the rendered DOM ... after scripting and styles were applied" ([WebAIM2026](../../../ai-accessibility-paper/literature/papers/L_WebAIM2026.md)); DQ-form finding 8 | Closed shadow roots and iframe contents are not saved | Many pages whose content sits in iframes or closed roots: add per-frame capture |
| Alex's own browser | Pages are saved by hand in Chrome, never fetched by us | Our 2026-10 automated scan got block or redirect pages for 31 of 102 pages (DQ-form, evidence A) | A hand-saved page reflects one session, one A/B arm and one viewport | If two captures of one page differ widely, capture each page twice |
| cleaning before download | Scripts, noscript, comments, handlers, token-like meta removed; input values, textarea text and contenteditable content cleared; e-mail, 6+ digit runs and 32+ character tokens masked; URL query values and fragments become hashes with a random salt for each capture | ours (privacy); tested in (c) | Names and street addresses in page text are not recognised; CAPTURE.md therefore asks for logged-out pages or test accounts and a grep for one's own name | Any real personal datum found in a saved file: stop and widen the masks |
| hashed, not dropped, query values | Links to `search?category=Books` and `search?category=Office` stay different | Observed: the first version dropped query strings. Amazon's category links then all read `/search`, the ambiguous-link test lost them, and JSON and MHTML disagreed on 21 of 119 amazon pages for names (first run, `/tmp/amt-syn/rwk/bw-run1-querystripped`) | A 32-bit hash can collide (negligible within one page) | — |
| style stamps | For each element: display:none, visibility, font size, weight, display and alignment of text, and boxes of images, tables and layout containers, as `data-rwk-*` attributes | Cross-origin CSS cannot be read by a script; without these facts the offline render would show hidden menus and lose heading styles (ours) | Stamps reflect the moment of capture: an open menu is captured open | — |
| MHTML fallback | Chrome "Save as > Webpage, Single File": full CSS and images, scripts dropped by Blink | ours | Not cleaned: see (c) | Use only on logged-out pages (CAPTURE.md) |

## (b) The detector

`analyze.py` takes each file as bytes. It serves the document to a new Chromium profile (an empty temporary directory, deleted afterwards) through a route handler, with JavaScript off for the page, service workers blocked and `Content-Security-Policy: script-src 'none'`. Every other request is aborted. DNS maps to NOTFOUND and a dead proxy is set. Meta refresh is stripped before serving, and `<noscript>` is removed after load. The DOM is not shown to the user with scripts on, so it is removed. The tree is BrowserGym's: `extract_merged_axtree` and `flatten_axtree_to_str` with the arguments of BreakingWeb's agent. Its marking script is patched in one place: it waits on a timer, and timers do not run with scripts off. The patched copy computes the same visibility ratio from boxes, without ancestor clipping. The full tree is the primary output, and the viewport tree is approximate.

Signatures (exact definitions in the `analyze.py` docstring). Verdict `exact` = the markup codemod.py writes; `equivalent` = other markup, same tree outcome; `kind-only` = kind present, other form.

| kind | signature | grounded in | how it could be wrong | what would change a decision |
|---|---|---|---|---|
| names | button/link with empty name (icon-only subtype); name with no letter or digit (glyph-only, e.g. `▲`); same name on >= 2 controls of one role, for links only with >= 2 different hrefs (ambiguous) | WebAIM2026: empty buttons 30.6%, empty links 46.3% of home pages; SC 2.4.4; glyph names on WebArena admin (DQ-form evidence B: `link ''`); on-path dose ladder (2026-10-30-on-path-dose.md) | Same-name buttons with the same effect (two "u/name" author buttons of one user) count as ambiguous; context in the row is not considered | If Alex's pages show mostly harmless duplicates, add a same-container context rule |
| labels | control with no `<label>` (for or wrapping), aria-label, resolving aria-labelledby or title; exact if an unassociated `<label>` is in its container or no visible label text exists; equivalent if other short text is in the container | WebAIM's four labelling routes (WebAIM2026, Form Labeling); F68; Postmill `URL` text next to `textbox ''` (DQ-form evidence B) | Placeholder-only fields count as unlabelled (WebAIM's rule); HTTP Archive counts placeholder as a name | — |
| alt | rendered `<img>` without alt attribute, no other name, not presentational, larger than 2x2 px | WebAIM2026: 45% of missing-alt images are linked; alt="" is decorative | Lazy images still unloaded at capture have a box only if CSS sizes them | — |
| headings | non-heading block element with short text (2-120 characters, <= 15 words, >= 50% letters, no ':' lead-in), no interactive element inside or around it. Tier 1, heading-styled: text >= 1.25 x the page's dominant size, or weight >= 600 and >= 1.1 x with <= 8 words. Tier 2, bold-short-text: weight >= 600, >= 0.85 x, <= 8 words, block tag | F2; "visual title as non-heading" (DQ-form finding 5: Yu2025 interviews, our WebArena scan) | Thresholds set on the BreakingWeb pages of (d) (see (e)); tier 2 fires on bold block labels | If tier 1 shows false alarms on GOV.UK/NHS.uk captures, raise HEAD_R1; if tier 2 does, drop tier 2 from counts |
| landmarks | page: which of banner, navigation, main, contentinfo, complementary exist; instances: non-landmark containers whose aria-label or class/id names a region, outermost, region-sized | WebAIM2026: main on 46.1% of home pages; WebAIM2020a equivalences; Chrome's header/footer scoping | A region whose markup names nothing (`<div class="page">`) is invisible to the instance test; the page verdict still counts it | — |
| tableheads | `<table>` with >= 2 rows and >= 2 cells in a row and no th/columnheader/rowheader; exact if the first row is a styled header row (thead, bolder, aligned or larger); kind-only if no header row; ARIA grid without header cells = equivalent | F91; WebAIM: 19% of tables have valid data-table markup (2026); DQ-form finding 6 (real form open) | A layout table with a bold first row would count | If real pages show many layout tables flagged, require Chrome's data-table role |

## (c) Self-test: fixtures, privacy, isolation (`selftest.py`, observed)

**Fixtures.** There are 13 pages: one positive and one negative per kind, plus a privacy page, with one stylesheet. They are rendered with scripts on and saved by `harness.save()` in both formats. That is 26 analyses. All expectations hold, and both formats give the same counts.

| page | expected and observed |
|---|---|
| names_pos | 8 exact: 2 empty icon buttons (one inside an open shadow root, created by a script) + 3 "Add to Cart" + 3 "Details" to 3 hrefs |
| labels_pos | 4: 2 unassociated `<label>` (exact), 1 placeholder-only (exact), 1 `<span>` text (equivalent) |
| alt_pos | 2 exact (one the sole content of a link; that link is not also counted under names) |
| headings_pos | 5 exact (2 section titles, 3 card titles as styled divs) |
| landmarks_pos | 4 exact containers; page verdict exact |
| tableheads_pos | 1 exact (bold, centred first row of td) |
| every positive, other kinds | 0 |
| every negative | 0 of every kind (they include a 1x1 pixel without alt, alt="", role=presentation, a big price, inline bold text, `<div class="card-header">` inside `<main>`, a wrapping label, aria-labelledby, two identical links to the same href, a role=presentation table) |

**Privacy** (privacy.html, 14 planted secrets). The JSON keeps 0 of 14. The e-mail shows as `Signed in as [email]`. "Save changes" on the submit input and `href="#help"` are kept. The query string reads `/orders?session=h…&u=h…`. The Blink MHTML of the same page keeps 10 of 14: the e-mail, the prefilled value, the textarea text, the draft, the CSRF meta, the session query value, two long digit runs, the data-user-id and the base64 session. It lacks the typed value, the hidden-input CSRF value and the inline-script state. That is why CAPTURE.md limits MHTML to logged-out pages.

**Isolation.** Two hand-made hostile inputs, one JSON and one MHTML with an extra script part. They carry an inline script, an onerror handler, a `javascript:` link, meta refresh, `@import`, a background URL, an external stylesheet, an image, an iframe, a prefetch, a preconnect and a video poster, all pointing at a beacon HTTP server on 127.0.0.1. Loopback bypasses the proxy and the DNS rule, so only the route handler stands between the page and the beacon.

| | JSON | MHTML |
|---|---|---|
| beacon hits | 0 | 0 |
| page script ran (inline, onerror, script part) | no | no |
| final URL is the served URL (refresh stripped) | yes | yes |
| requests served / aborted | 1 / 7 | 1 / 7 |
| noscript content in the tree | no (removed) | no (removed) |

## (d) Known-answer test on BreakingWeb (`bw_kit_test.py`, observed)

**Setup.** This uses a private copy (`/tmp/amt-syn/rwk/bw-src/BreakingWeb`, backend on 127.0.0.1:8113). For each of the 7 envs it makes 1 clean build and 1 build per kind (codemod on env and shared sources). Each page is saved with the same snippet and as MHTML. The pages are those of the variant gate: the start pages of the first 2 tasks plus the env's routes, 76 per build (amazon 17, booking 12, gmail 8, lms 7, patient portal 9, reddit 9, robinhood 14). That makes 532 pages x 2 formats = 1,064 analyses, about 2 minutes on 10 workers. Elements are aligned by the gate's BrowserGym bid, which clean and variant share (gate dom check). JSON pages are analysed with the codemod's `data-amt` markers stripped. `analyze.py` never reads them, and the capture stamps carry the variant's look.

**Measures.** `new` = variant instances whose element, or whose signature on that element, is not an instance in clean. `unexplained` = new instances with no codemod change on the element, an ancestor or a descendant. `strict` = new instances whose own element did not change (kind-specific reach in the `bw_kit_test.py` docstring). `targets` = changed, rendered elements of the kind. For headings and landmarks only elements whose clean AX role was heading or a landmark count.

Cells: clean / variant / new (unexplained | strict) / targets detected of targets; JSON format.

| env | names | labels | alt | headings tier 1 | headings tiers 1+2 | landmarks | tableheads |
|---|---|---|---|---|---|---|---|
| amazon | 52 / 93 / +41 (0\|0) / 41 of 147 | 0 / 39 / +39 (0\|0) / 39 of 42 | 0 / 162 / +162 (0\|0) / 162 of 162 | 17 / 73 / +56 (0\|0) / 56 of 184 | 17 / 118 / +101 (0\|0) / 101 of 184 | 0 / 51 / +51 (0\|0) / 51 of 71 | none in env |
| booking | 631 / 668 / +39 (0\|0) / 39 of 55 | 0 / 26 / +26 (0\|0) / 26 of 26 | 0 / 44 / +44 (0\|0) / 44 of 44 | 2 / 66 / +64 (0\|0) / 64 of 662 | 8 / 651 / +643 (0\|0) / 643 of 662 | 0 / 46 / +46 (0\|0) / 46 of 50 | not on pages |
| gmail | 44 / 109 / +109 (0\|0) / 109 of 258 | 0 / 14 / +14 (0\|0) / 14 of 32 | no img | 8 / 11 / +3 (0\|0) / 3 of 14 | 8 / 15 / +7 (0\|0) / 7 of 14 | 0 / 24 / +24 (0\|8) / 16 of 33 | 0 / 2 / +2 / 2 of 2 |
| lms | 4 / 4 / +0 / 4 of 74 | 0 / 2 / +2 / 2 of 2 | no img | 0 / 16 / +16 / 16 of 16 | 0 / 16 / +16 / 16 of 16 | 0 / 21 / +21 / 21 of 22 | 0 / 3 / +3 / 3 of 3 |
| patient portal | 32 / 56 / +24 (0\|0) / 56 of 142 | 0 / 13 / +13 / 13 of 13 | no img | 0 / 36 / +36 / 36 of 36 | 0 / 36 / +36 / 36 of 36 | 0 / 28 / +28 / 28 of 29 | 0 / 8 / +8 / 8 of 8 |
| reddit | 610 / 596 / +162 (0\|0) / 544 of 779 | 0 / 19 / +19 / 19 of 33 | no img | 3 / 9 / +6 / 6 of 54 | 3 / 46 / +43 / 43 of 54 | 9 / 30 / +21 / 21 of 30 | none in env |
| robinhood | 2 / 44 / +42 (0\|0) / 44 of 111 | 0 / 25 / +25 / 25 of 25 | no img | 0 / 27 / +27 / 27 of 36 | 0 / 33 / +33 / 33 of 36 | 0 / 44 / +44 / 44 of 44 | not on pages |
| **all** | 1,375 / 1,570 / +417 (0\|0) / 837 of 1,566 | 0 / 138 / +138 (0\|0) / 138 of 173 | 0 / 206 / +206 (0\|0) / 206 of 206 | 30 / 238 / +208 (0\|0) / 208 of 1,002 | 36 / 915 / +879 (0\|0) / 879 of 1,002 | 9 / 244 / +235 (0\|8) / 227 of 279 | 0 / 13 / +13 (0\|0) / 13 of 13 |

- **Every new instance is accounted for.** Unexplained is 0 in every cell. Under the strict rule, 8 remain (gmail landmarks, one per page). Each is `<div class="gmail-main-column">`, the wrapper of the converted `<main class="gmail-page" aria-label="Inbox">`. The converted main itself names no region, so its wrapper becomes the outermost main-like container. It is the variant's change, seen one level up.
- **Agreement and independence.** JSON and MHTML give the same count for every kind on all 532 page pairs. On the 228 variant pages of the tag-replacing kinds, the JSON analysis with `data-amt` kept gives the same counts as with it stripped: 0 differences.
- **Pages.** The variant adds at least one instance on every page with a target for labels (58/58), alt (12/12), landmarks (76/76) and tableheads (11/11). It does so for headings (69/71) and names (51/70). The landmarks page verdict goes from none to exact on all 67 pages of 6 envs. On reddit's 9 pages it goes from partial to exact.
- **names, by name-loss rung** (targets = changed, rendered buttons and links, n = 1,566):

  | rung | n | detected |
  |---|---|---|
  | empty | 152 | 152 |
  | glyph-only | 162 | 162 |
  | shared | 340 | 307 |
  | unique, changed | 346 | 0 |
  | kept | 566 | 216 |

  The detector reports exactly the rungs that a real page can show by itself. An empty, glyph-only or ambiguous name needs no comparison. A word lost from a still-unique name ("Add 23Pcs Resistance Bands…" becoming "Add to Cart") cannot be seen on a single real page.
  - The 33 shared names not reported are links that share a name and an href. These are image and title links to the same product.
  - The 216 kept-and-detected are reddit controls whose aria-label equalled a name that was already ambiguous ("Hide", "Share").
  - The lms variant produces only unique-changed or kept names (0 new on 74 targets). Its names cell has no real-world exemplar form at all.
- **labels.** The 35 targets not reported keep a programmatic label in the variant: a wrapping `<label>` or a title. The name stays (15) or changes (20). Of the 138 new instances, 94 are exact: 51 with an unassociated `<label>` beside the control and 43 with no visible label left. The other 44 are equivalent (visible text in the container).
- **headings.** Of the 1,002 converted headings, 579 are on booking's reviews page. The 123 misses (tiers 1+2) are:
  - 50 titles longer than 15 words or 120 characters (amazon product titles);
  - 42 headings inside a link (product, property and list cards);
  - 19 headings that look like body text or smaller: amazon search-filter titles "Department" and "Price" at 14.4 px against 18 px body text; reddit sidebar labels at 12.5 px against 16 px; gmail titles at body size and weight 500;
  - 10 inside a `role=button` card (reddit notifications);
  - 2 numeric headings ("$4,256.40").

  These are limits of a visual test: such headings have no visual signature that body text lacks.
- **landmarks.** The 52 missed containers name no region (`<main class="gmail-page">`, `<aside aria-label="Sent Messages">`) or sit inside a container of the same region (gmail's and reddit's `nav > aside "… navigation"`).

**Clean BreakingWeb is not defect-free (observed, JSON, 76 clean pages).**

| kind | clean instances | what they are | reading |
|---|---|---|---|
| names | 1,375 on 36 pages | booking: "Property" x577 (reviews), "See deal" x20, "View details" x15, "See availability" x10, "Edit" x7, all content names; reddit: aria-label "Upvote"/"Downvote"/"Hide"/"Share" on every post (x81 each); amazon "Today's Deals" x34; patient portal "Cancel appointment with Dr. Lisa Patel" x8 (several appointments with one doctor); gmail "Star <subject>" on repeated subjects | Natural instances of the ambiguous form, real by the rule. The 2026-10-29 record calls the clean apps over-annotated; that holds for unique names on several apps, but booking and reddit already carry the generic-name form |
| landmarks | 9 (reddit, every page) | `<div class="reddit-main-column">`: reddit has no `<main>` | Natural partial-landmark page, the WebAIM 46.1% form |
| headings tier 1 | 30 on 29 pages | brand wordmarks (amazon footer "amazon" x16, gmail topbar "Gmail" x8), reddit "Premium" badge x3, booking 2, an amazon order status 1 | False alarms: wordmarks and badges are not section titles |
| headings tier 2 only | 6 more | booking status badges and result count | False alarms |
| labels, alt, tableheads | 0 | — | — |

## (e) How the rules were set, and what that means

The heading and landmark rules were revised against these BreakingWeb pages, and so was part of the names rule. So (d) is a development set, not an independent test. The revisions, each triggered by an observed case:

1. Headings: half the element's text must be heading-styled (lms `<p><strong>Status:</strong> active</p>`).
2. Headings: a text run ending in ':' disqualifies (lms "Student ID:").
3. Headings: weight dropped from the size rule (gmail 22 px at weight 400).
4. Headings: tier 2 added for small bold labels (reddit 12.5 px at weight 700), limited to block tags (gmail sender names in `<strong>` were blockified by a flex parent).
5. Headings: legend, caption, th, td and dt excluded (patient portal `<legend>`).
6. Landmarks: aria-label words first, then the last region word of the class (lms `topbar__nav`, gmail `aria-label="Gmail navigation"`); BEM modifiers ignored (reddit `feed-page--with-sidebar`).
7. Names: ambiguity counted whatever the name source, plus the glyph-only signature (reddit "Upvote" x25 is ambiguous in clean and `▲` in the variant).
8. From the fixtures, not BreakingWeb: links named only by an image without alt are reported under alt, not names (alt_pos); a link or button is never itself a heading candidate (the fixture logo link).

The fixtures were written before these revisions and still pass, but they were written by the same author. Precision on real pages is unknown until Alex's captures are read. The low-defect controls in TARGETS.md (GOV.UK, NHS.uk) and the 5 examples per kind and page are there for that reading.

## What this does not show

- No real site was captured. The kit is ready; the exemplars are not collected.
- The capture snippet was run in Chromium 125 under Playwright, not in Alex's Chrome. `getHTML`, `parseHTMLUnsafe` and the console prompt are standard in current Chrome, but they have not been run there. The first capture should be checked: the console prints the counts of what it removed.
- The analyser counts signatures. It does not show that an agent fails on them; that is the pilot's question.
- Only pages at rest are covered, as in the gate. Open menus and dialogs need a second capture (`__menu-open`).
- The names rungs "lost a word" and "changed" are invisible on a single real page. For those rungs the real-world claim rests on the WCAG 2.4.4 form and the on-path dose record, not on this kit.

## Reproduce

```bash
P=~/.workspace/_refsrc/BreakingWeb/.venv/bin/python; T=~/.workspace/ai-agent-accessibility/scripts/realworld
$P -I $T/selftest.py /tmp/amt-syn/rwk/selftest                      # fixtures, privacy, isolation (about 1 min)
cp -a ~/.workspace/_refsrc/BreakingWeb /tmp/amt-syn/rwk/bw-src/ && cd /tmp/amt-syn/rwk/bw-src/BreakingWeb
export BW_ROOT=$PWD BW_PORT=8113 PATH=$HOME/.local/share/mise/installs/node/24.20.0/bin:$HOME/.local/bin:$PATH BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
for e in lms gmail reddit robinhood booking patient_portal amazon; do $P -I $T/bw_kit_test.py capture $e /tmp/amt-syn/rwk/bw; done   # about 30 min
$P -I $T/bw_kit_test.py analyze /tmp/amt-syn/rwk/bw --workers 10
$P -I $T/bw_kit_test.py evaluate /tmp/amt-syn/rwk/bw
$P -I $T/bw_kit_test.py stripcheck /tmp/amt-syn/rwk/bw --workers 8
git status --short    # only the four allowed bind-fix diffs remain
```
