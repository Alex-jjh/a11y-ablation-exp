# v2 pilot: defect register

> **Summary:** One entry per rewrite rule in `codemod.py` (sha256 `02b3190ff81d153f`) and per control. Each entry gives what the rule changes in the markup, the accessibility tree and the two agent observations; the real-world defect it reproduces, with the WCAG failure or criterion and the prevalence numbers from the close-reads; whether removing every instance is a real page state or our ablation choice; every side effect beyond the removed information; a plausibility verdict; and the pattern that finds the defect on a real rendered page. Headings, alt, tableheads and the empty-name part of `names` reproduce documented real defects (F2, F65, F91, F68). For each, removing every instance is either the tail of the real distribution or our ablation choice. Landmark absence is a common real page state, but no WCAG failure technique covers it. Five rules need a fix or a narrower description before Stage 0 freezes the codemod. (1) `landmarks` leaves every named `<section>` and named `<form>` as a landmark: 128 `region` and 6 `form` lines remain on the gate pages. (2) `labels` leaves wrapping labels and placeholders in place, so 206 of the 279 control lines on the gate pages still carry a name. (3) `names` leaves aria-labels on 35 `role=button` elements. (4) `fmt_wrap` inserts a line form that the H1 serializer never prints. (5) `alt` also strips `alt=""` without changing any observation. Nothing in `codemod.py` was changed.

## How to read an entry

- **Fields.** (1) change: markup, accessibility tree (Chromium 125), H1 BrowserGym text, H2 browser-use text. (2) real-world defect and sources. (3) dose. (4) side effects beyond the removed information. (5) verdict. (6) search pattern for the exemplar kit. Each kind closes with how the entry could be wrong and what result would change the verdict.
- **Verdicts.** *Real-world form*: the produced markup state and its tree are documented as a defect (W3C failure technique or a prevalence source) and we have seen it on a real deployed site. *Plausible but unmeasured*: real sites can produce it, but no source measures it. *Ablation-only*: no real page is expected to be in this state; it exists to isolate a mechanism.
- **Sources.** Close-read keys link to `literature/papers/`. The WCAG failure numbers F2, F65, F68 and F91 come from the Ma11y operator table, which maps each mutation operator to one failure technique ([Tafreshipour2024], Table 1, p. 102). The W3C technique pages are not in the library. So the other technique numbers (F59, F89, ARIA11, ARIA14, ARIA16, H37, H42, H44, H51, H63) and the axe rule ids are marked [unverified]. Prevalence numbers name their unit; WebAIM page shares are pages with at least one instance, not shares of elements ([WebAIM2026], Limits).
- **Observed data.** Gate counts come from the variant gate's full-page BrowserGym observations and DOM dumps, `/tmp/amt-syn/bw-gate/final/<env>/<build>/*.all.txt` and `*.dom.json` (76 pages, 7 apps; regenerable with the reproduce block of [variant gate]). Counts marked *(gate captures, read 2026-11-02)* were computed from those files for this register. Browser-use counts are from [browser-use footprint] (Amazon, Gmail, patient portal; 34 pages). Real-site forms are from [DQ-form] Our own evidence A (60 real public pages, axe and tag counts) and B (unmodified WebArena observations, `data/smoker-shard-{a,b}`). GitLab, Magento and Postmill are deployed open-source software, so their forms are real-world forms, not constructs.
- **H1 line grammar** (`.venv/lib/python3.12/site-packages/browsergym/utils/obs.py` in the BreakingWeb clone). A line is `[bid] role 'name'`, then flags (`clickable`, `visible`), then properties. A `generic` node without properties is not printed, and its children move up one tab (l. 350). A node without a bid is skipped, except StaticText (l. 237-240). A StaticText whose text is contained in its parent's name is hidden (l. 356-360). `level` is never printed (l. 21-29). H1 calls it with `with_clickable=True, with_visible=True, filter_visible_only=True, filter_with_bid_only=True` (`breakingweb/agent.py:375-381`).

## Shared machinery (all kinds)

| item | what it is | grounded in | how it could be wrong | what would change a decision |
|---|---|---|---|---|
| Source-level rewrite | Rules run on `src/**/*.tsx` of the env and of `shared/src`, before the build, so React renders the defect as if the developer had written it | D-008 (source-level variants are the reference); [BreakingWeb record] (observation-layer emulation of headings drops the text a real div heading keeps) | A component that builds attributes at run time (`{...props}`, computed names) escapes a text rewrite | A residual count above 0 for the kind (gate residual check; Stage 0 widening for `names`) |
| Tag matching | A start tag is matched to its own `>`, with brace groups (3 deep) and quoted strings consumed whole (`TAG_BODY`, codemod.py:88-90) | On-path record §1: the 2026-10-29 pattern stopped at `=>` and missed 90 of 601 acted-on aria-labels | Brace nesting deeper than 3 levels inside a start tag | Any aria-label left on a target tag in a built variant |
| Look-keeping CSS | `T` becomes `:is(T, R:where([data-amt="T"]))`; `R` becomes `R:not(:where([data-amt]))`; the replaced tag's UA defaults go into `@layer amt-ua`; Chromium's sectioned h1 sizes are reproduced (codemod.py:190-222) | ua_delta: 0 of 49 fixture elements differ under four author-CSS cases, except a `th` in a row with inherited `text-align` ([variant gate] (a)) | States not captured at rest (hover, focus, open menus) | Any pixel, box or size change on a task-path state (M2) |
| `data-amt` marker | Each replaced element carries `data-amt="<original tag>"` | Needed by the CSS rewrite | An agent that reads raw HTML would see it. Neither harness prints `data-*` attributes (gate observation rule: no unexplained diff line; footprint: no `data-amt` line) | A harness that serialises HTML attributes would need the marker removed after the CSS is compiled |
| Risk scan | Refuses CSS with `@layer`; counts `*-of-type` selectors, attribute selectors on removed attributes, and script queries of replaced tags (codemod.py:225-244) | ours | Selectors built in JS strings are not scanned | Reddit's one `*-of-type` selector changed no pixel ([variant gate] "Codemod risks") |

**Whole-page dose, for every kind.** Real defects sit in components: one repair in a shared component file fixed three unnamed SVG icons ([Huang2026], Section 3.2.2, p. 3). One template omission therefore removes the information from every instance of that component on every page, so total removal *within one component* is a real state (ours, from Huang2026). Removing the kind from *every component of the app* is our ablation choice (DQ-dose Option A; DESIGN.md §4.1). `names50` is the one dose point below total.

**The sighted-user constraint.** "The page stays the same for a sighted mouse user" is the counterfactual that defines a cell, not a property of real defective pages. A real developer who writes `<div>` for a heading styles it with a class, not with UA defaults. The look-keeping CSS stands in for that styling, so it is not a side effect of the defect. It is how the comparison holds the look fixed (ours).

## K1. `landmarks`

**Rules.**
- **L1** (codemod.py:139-141): `<header|nav|main|footer|aside` becomes `<div data-amt="…">`, and each closing tag becomes `</div>`. Attributes are kept, including the landmark's `aria-label`.
- **L2** (l. 142): `role="banner|navigation|main|contentinfo|complementary|search|region"` is removed from any tag. There are 9 such attributes in the app sources (grep, 2026-11-02), for example `role="search"` on the search forms.
- **L3** (l. 211-217): look-keeping. `display:block` goes into the layer. Chromium's smaller h1 sizes are kept for a real h1 inside a replaced `nav` or `aside`.

**(1) Change.**
- Tree: the div maps to `generic`, so banner, navigation, main, contentinfo, complementary and search nodes disappear. The landmark's aria-label stays on a node that the tree does not name.
- H1: the landmark line is gone and its subtree moves up one tab. On LMS calendar, `[11] banner ''` and `[13] navigation 'Main navigation'` disappear and 29 of 32 lines are re-indented (gate captures). Viewport lines changed: Amazon 1,807, Booking 472, Gmail 1,769, LMS 692, patient portal 1,218, Reddit 930, Robinhood 777 ([variant gate] table).
- H2: browser-use never prints landmark elements. Its footprint is 18, 9 and 4 lines on Amazon, Gmail and the patient portal: `role=search` dropped from the indexed search form, and scrollable `main`/`aside` printed as `<div …>` ([browser-use footprint] §3).
- **Residual (observed, gate captures, read 2026-11-02).** In the landmarks variant's full observations these remain:

| env | Amazon | Booking | Gmail | LMS | patient portal | Reddit | Robinhood |
|---|---|---|---|---|---|---|---|
| `region` lines | 17 | 5 | 24 | 10 | 22 | 33 | 17 |
| `form` lines | 0 | 1 | 3 | 0 | 2 | 0 | 0 |

  They come from `<section aria-label=…>`: 93 in the sources, 2 of them in `shared/src` (the shared `Modal` and `EmptyState`). They also come from `<form aria-label=…>` (4 in the sources). Chromium exposes a named `section` as `region` and a named `form` as `form`, and neither is in L1 or L2. The codemod docstring, DESIGN.md §4.1 ("landmark roles dropped") and the gate's residual check (tags and explicit roles only) do not report them.

**(2) Real-world defect.**
- A page laid out with divs where `header`, `nav`, `main`, `footer` and `aside` would be ([DQ-form] finding 4).
- No W3C failure technique covers missing landmarks. Landmarks are one sufficient technique (ARIA11) for SC 1.3.1 and 2.4.1 [unverified], and no close-read counts their absence as a defect ([DQ-defects] finding 2).
- Prevalence: at least one landmark or region on 84.3% of home pages and a main landmark on 46.1% ([WebAIM2026], Regions). By subtraction, no landmark at all on 15.7% and no main on 53.9%. A `<main>` element on 37% of desktop pages, role=main on 17%, either on 44% ([HTTPArchive2024], Fig. 8.11).
- Our real-site scan: 5 of 60 real public pages have no landmark element or role, 12 have no main, and 3 have main only as role=main ([DQ-form] evidence A).
- WebArena has a main landmark on every page ([DQ-form] evidence B), so this form must come from other sites.
- Which sites (ours, unmeasured): layouts written before HTML5 sectioning elements (`div#header`, `div.nav`) and app scaffolds that render into a bare `div#root`.

**(3) Dose.** No landmark at all is itself a common page state (15.7% of home pages), unlike the totals of other kinds. The state the variant produces now is different: no banner, navigation, main, contentinfo, complementary or search, but every named region and form kept. No source measures that combination.

**(4) Side effects.**
- Function: 2,220 trials act inside a changed landmark, and 0 mismatches were confirmed ([function equivalence]).
- Landmark jumps are lost. They belong to the real defect, and neither harness has a landmark action (ours).
- A real h1 inside a former `nav` or `aside` keeps its smaller size. A developer who swapped the tag would see a larger h1 unless the CSS set its size; we hold the look (sighted-user constraint).
- `data-amt` is printed by neither harness.

**(5) Verdict.** As built: *plausible but unmeasured*, because of the residual regions. With the fix in the flags table (F-1): *real-world form*, and the total dose is an observed page state.

**(6) Search pattern.**
- DOM: no element matches `header, nav, main, footer, aside, [role=banner], [role=navigation], [role=main], [role=contentinfo], [role=complementary], [role=search], [role=region], [role=form], section[aria-label], section[aria-labelledby], form[aria-label], form[aria-labelledby]`, while divs with `id` or `class` matching `/header|nav|menu|footer|main|content|sidebar/i` exist.
- Tree: `Accessibility.getFullAXTree` has no node with role in {banner, navigation, main, contentinfo, complementary, search, region, form}.
- Partial form: no `main` node.
- axe [unverified]: `landmark-one-main`, `region` (best-practice rules).

**How it could be wrong; what would change it.** Chromium's context rules (when a `header` counts as banner) are not in any close-read ([DQ-form] Gaps), but the gate observes the tree directly. If a fixed variant still shows any landmark line on a replay state, the verdict stays at plausible.

## K2. `headings`

**Rules.**
- **H1** (l. 144-146): `h1`…`h6` become `<div data-amt="hN">`.
- **H2** (l. 147): `role="heading"` is removed. There are 0 in the sources, so on these apps the rule does nothing.
- **H3** (l. 209-217): look-keeping. UA font size, margins and weight per level, and Chromium's sectioned h1 sizes, go into `@layer amt-ua`.

**(1) Change.**
- Tree: a heading node, which carries a level, becomes `generic`, and its text becomes a StaticText child.
- H1: `[25] heading 'Calendar', visible` becomes `StaticText 'Calendar'` (LMS calendar, gate captures). The text stays; the role word and the bid go.
- Heading lines in the full observations go to 0 on every app: Amazon 184, Booking 662, Gmail 14, LMS 16, patient portal 36, Reddit 54, Robinhood 36 (gate captures, read 2026-11-02).
- Level was never printed (`level` is ignored), so only "heading or not" is lost.
- H2: headings are printed as plain text in clean and variant alike. The only change is 3 indexed `<h3 level=3 />` in Amazon's filter sidebar ([browser-use footprint] §3).

**(2) Real-world defect.**
- W3C failure F2: text styled to look like a heading without heading markup (Ma11y RHP, heading to paragraph; [Tafreshipour2024], Table 1). SC 1.3.1.
- Prevalence: 7.5% of home pages have no headings (9.8% in 2025, 11.3% in 2024, 12.4% in 2020) ([WebAIM2026], [WebAIM2025], [WebAIM2024], [WebAIM2020]).
- Seen on real sites:
  - Magento (WebArena shopping) writes section titles as `strong ''` plus `StaticText 'Account Information'` ([DQ-form] evidence B).
  - On 24 of 60 real public pages, div, span and p elements with a heading or title class outnumber the real headings ([DQ-form] evidence A; a class heuristic).
  - Six screen-reader users report product titles without heading markup ([Yu2025], Section 4.4.1).
- Which sites: e-commerce templates (Magento, observed). Component libraries whose text components render div or span by default (ours, unmeasured).

**(3) Dose.** Removing every heading is the tail of the real distribution (7.5% of home pages). The commoner real state is some titles written as divs beside real headings (24 of 60 pages by heuristic). Whole-app removal is our ablation choice.

**(4) Side effects.**
- The heading's bid disappears with its line, so an agent cannot target a heading by bid. No heading in the sources is interactive (0 h-tags with `onClick`, `tabIndex` or `role`; grep, 2026-11-02), so no control is lost. Function evidence is weak: 7 treated targets are headings and 65 are links containing a heading, with 0 mismatches ([function equivalence]).
- The UA layer reproduces Chromium 125 values exactly (ua_delta 0/49) and loses to the app's own resets as UA CSS would. This is the fix for the 2026-10-29 Booking height change ([variant gate] (a)).

**(5) Verdict.** *Real-world form* (F2, seen on Magento). The total dose is a real but tail state.

**(6) Search pattern.**
- DOM: an element that is not h1-h6 and has no `role=heading`, with block display, computed font size at least 1.17 times the body font size or `font-weight` at least 600, text of at most 80 characters, and content after it. A class matching `/title|heading|header|hd\b/i` raises confidence.
- Page level: no element matches `h1, h2, h3, h4, h5, h6, [role=heading]`.
- Tree: StaticText under `generic`, `strong` or `paragraph` with heading-like style; the count of `heading` nodes on the page.
- axe [unverified]: `page-has-heading-one`.

**How it could be wrong; what would change it.** The class heuristic for the 24/60 figure is untested against hand labels. A hand-labelled sample showing that heading-styled divs are rare would move the partial state to *plausible but unmeasured*. It would not change the total-dose reading.

## K3. `names`

**Rule N1** (l. 148-153): `aria-label` and `aria-labelledby` are removed from the start tags of `button`, `a`, `Link`, `NavLink`, `Button` and `IconButton`. Where the name lands depends on the control:

| class | what happens | example (H1) | counts |
|---|---|---|---|
| N1a icon-only | name becomes empty | `button 'Submit search'` → `button ''` | Empty button, link, tab and menuitem lines go from 0 in clean to: Amazon 17, Gmail 93, Robinhood 42; Booking, LMS, patient portal, Reddit 0 (gate captures, read 2026-11-02). H2: element lines left with nothing printed: Amazon 34, Gmail 85, patient portal 0 ([browser-use footprint] §3) |
| N1b richer aria-label | name falls back to the visible text, which is shorter, generic or repeated | `link 'Shopping cart, 0 items'` → `link '0 Cart'`; "Add to Cart" on every product | 164 of 330 Gemini paths have an acted-on control that becomes empty or ambiguous; 285 of 330 lose at least one content word ([on-path dose] summary) |
| N1c aria-label equals the visible text | no change in H1; H2 loses a duplicate attribute | `aria-label=Inbox` on "Inbox" | Gmail 84 of 255, patient portal 82 of 142 H2 lines ([browser-use footprint]) |

**(1) Change.**
- Tree: the name falls back to the content.
- H1: StaticText children that were hidden because the parent's name contained them can appear or vanish. Gmail: `[20] button 'Run search'` + `StaticText 'Search'` becomes `[20] button 'Search'` (gate captures). Bids and roles stay.
- H2: the `aria-label=` attribute goes and the visible text printed under the element stays. One-character text is dropped, so `Notifications, 1 unread` leaves an empty `[N]<a />` ([browser-use footprint] §3).
- **Residual (observed, gate captures, read 2026-11-02).** 35 elements with an interactive role keep their aria-label: Booking 26 `div role=button` (notification items such as "Welcome! Your reservation is confirmed"), Reddit 5 `div role=button`, Amazon 4 `article role=button`. `title` on `button` or `a`: 0 in the sources. Screen-reader-only text: 1 use in the sources.

**(2) Real-world defect.**
- **N1a** is the empty button or link:
  - Empty buttons on 30.6% and empty links on 46.3% of home pages ([WebAIM2026]; page shares, no element rate).
  - 9-12% of buttons have no accessible name ([HTTPArchive2022], [HTTPArchive2024]).
  - Link names fail on 52% of pages ([Martins2023], Table 2).
  - Failure: SC 4.1.2. F68 covers user interface controls without a programmatic name ([Tafreshipour2024], Table 1, mapped there to input names); F89 covers an image that is the only content of a link [unverified].
  - Seen on real sites: GitLab icon-only menu buttons, `[80] button '', hasPopup='menu'`, with 5,866 unnamed buttons and 8,497 unnamed links in its WebArena observations ([DQ-form] evidence B).
  - Which sites: icon-button components. One shared component produced three unnamed SVG icons in [Huang2026] (Section 3.2.2).
- **N1b** is not a WCAG failure when the visible text plus its context gives the purpose (SC 2.4.4 is "in context"; ours). Ambiguous link text appears on 13.2-13.7% of pages ([WebAIM2024], [WebAIM2025]). On the web, buttons take their name from content in 58-61% of cases and from aria-label in 20-24% ([HTTPArchive2022], [HTTPArchive2024]). A control without an aria-label is therefore the common state of the web, not a defect. The clean apps carry aria-labels on most acted-on controls, richer than typical real sites ([BreakingWeb record], "The clean apps are richly labelled").

**(3) Dose.** For N1a, every icon button of one component being unnamed is a real state (Huang2026). App-wide removal of every aria-label is our ablation choice. Real sites keep some aria-labels (20-24% of button names), so the variant is less annotated than the average real site.

**(4) Side effects.**
- None on function: 1,082 treated targets, 0 mismatches ([function equivalence]).
- None on look: aria-label is not rendered, and no CSS selects on it (risk scan 0).
- The form change, StaticText exposure, is a consequence of the real defect: a real unlabelled button exposes its text the same way. The pilot separates it from the lost words with `names+`.
- H2's action-result echo loses the aria-label part.

**(5) Verdict.** N1a: *real-world form* (seen on GitLab; WebAIM). N1b: *plausible real state*, but not a defect; it is the ordinary web. N1c: no change. For the kind as a whole, the defect is carried by the strict on-path tasks (empty or ambiguous), and the primary flag also counts lost words that the ordinary web lacks too. Reports must keep the two apart.

**(6) Search pattern.**
- N1a, DOM: `button, a[href], [role=button], [role=link], [role=tab], [role=menuitem]` with no `aria-label`, `aria-labelledby` or `title`, whose `textContent.trim()` is empty and whose only children are `svg`, `i`, `span` with an icon-font class, or an `img` with a missing or empty `alt`.
- N1a, tree: role button or link with name `''`.
- N1a, axe [unverified]: `button-name`, `link-name`.
- N1b: at least two links or buttons on a page with the same AX name and different `href` or handler targets.

**How it could be wrong; what would change it.** The 35 residual role=button elements mean that the "every interactive role" claim in DESIGN.md §4.1 does not hold yet; the Stage 0 widening is planned there. If N1a controls are on no strict task path in an env, that env's names cell tests only N1b.

## K4. `labels`

**Rules.**
- **B1** (l. 155): every `htmlFor` is removed.
- **B2** (l. 156-159): `aria-label` and `aria-labelledby` are removed from `input`, `textarea` and `select` start tags.
- **B3** (l. 160): the same keys are removed from object literals passed as `inputProps`, `textareaProps` or `selectProps` (Gmail's shared field component).

**(1) Change.**
- Tree: a control named by `<label for>` or by its own aria-label falls back to `placeholder`, `title` or `''`. A `<label>` that wraps its control still names it, because B1-B3 do not touch implicit labels.
- H1 examples (patient portal, gate captures): `[32] textbox 'Patient name (read only)'` → `[32] textbox ''`; `[31] combobox 'Sort lab results'` → `combobox ''`. The orphaned `LabelText` loses `clickable`: `[31] LabelText '', clickable, visible` → `LabelText '', visible`.
- **What the 279 control lines in the labels variant carry** (full observations, 7 apps; gate captures, read 2026-11-02; clean has 0 empty):
  - empty: 73 (Amazon 21, Booking 19, patient portal 13, Robinhood 7, Reddit 6, Gmail 5, LMS 2);
  - named from the placeholder: 71;
  - named with no naming attribute on the element, from a wrapping `<label>`: 129 (89 checkboxes, 34 radios, 6 text inputs). For example, Gmail's VIP checkbox loses `aria-label="Mark as VIP contact"` and keeps the name "VIP contact" from its wrapping label;
  - date sub-field spinbuttons that Chromium names itself: 6.
- H2: browser-use never printed the association. Its footprint is the control aria-labels: 40, 30 and 13 lines. On Gmail, a wrapping `<label>` without `for` becomes an indexed `[N]<label />` that groups its text and control (8 lines), so H2 shows the association more explicitly than clean ([browser-use footprint] §3).

**(2) Real-world defect.**
- W3C failure F68: a control without a programmatic name. Ma11y's RIN deletes `<label for>` exactly as B1 does ([Tafreshipour2024], Table 1, Figure 5). SC 1.3.1, 3.3.2, 4.1.2.
- Prevalence:
  - 33.1% of home-page form inputs are not labelled through `label`, aria-label, aria-labelledby or `title`, and 51% of pages have at least one ([WebAIM2026], Form Labeling).
  - No accessible name on 38% of inputs; placeholder is the largest single source of input names (24-26%) and the label element is next (19-20%) ([HTTPArchive2022], Fig. 11.16).
- Seen on real sites:
  - Postmill's submission form prints the visible label `URL` as StaticText next to `[127] textbox ''`, which is exactly the unassociated-label form ([DQ-form] evidence B).
  - Magento's admin grid has 118,910 lines of `checkbox ''` beside `LabelText ''`.
- Which sites (ours, unmeasured): form components that render label and input as siblings without wiring an `id`.
- The placeholder fallback is itself the commonest real naming route, which no guideline accepts as a label ([GDSWay2026]).

**(3) Dose.** Every explicit association in the app is removed; implicit labels are not. One shared form component can drop `for` on every field, so the state is real within one component. App-wide is our ablation choice. Checkbox and radio controls are mostly untouched, because their labels wrap them.

**(4) Side effects.**
- Clicking the label text no longer focuses its control: 37 labels, 42 trials, on 22 `select`, 18 text-like inputs and 1 `textarea` ([function equivalence]). An unassociated label in a real page behaves the same way, so this is part of the defect, and it is kept. `labels~` measures it separately.
- BrowserGym's dropped `clickable` flag on the label follows from the same change.
- No reference path clicks a label: 0 of 2,336 replayed clicks ([PREDICTIONS] E-L3; replay record §2).
- H2 can gain structure (the indexed `<label>`), which is the serializer's response to the real form.

**(5) Verdict.** *Real-world form* (F68, seen on Postmill), scoped to explicit associations and control aria-labels. The description "removes the control's computed name from both sources" (DESIGN.md §4.1, `design.yaml: kinds.labels.note`) overstates it: 206 of 279 control lines keep a name.

**(6) Search pattern.**
- DOM: `input:not([type=hidden],[type=submit],[type=button],[type=reset],[type=image]), select, textarea` with no `aria-label`, `aria-labelledby` or `title`, no `label[for=<id>]`, and no `label` ancestor.
  - Unassociated visible label: a `label` without `for`, or a short div or span, within one sibling or parent step.
  - Placeholder-only: `placeholder` set and nothing else.
- Tree: textbox, combobox, checkbox, radio or spinbutton with name `''`, or a name equal to the placeholder.
- axe [unverified]: `label`, `select-name`, `label-title-only`.

**How it could be wrong; what would change it.** Implicit labels are left in place, so labels on-path flags for checkbox- or radio-heavy tasks may overstate exposure. The on-path measurement removed the same sources ([on-path dose] §2.1), so flag and variant agree. If Stage 0's real-variant flags (M2b) show a task's acted-on controls all keep a wrapping-label name, that task is off-path for `labels`.

## K5. `alt`

**Rule A1** (l. 161-165): `alt` is removed from every `<img>` start tag, including `alt=""`.

**(1) Change.**
- Tree: `image 'X'` becomes `image ''`. A linked image's alt no longer contributes to the link name.
- H1, Amazon home (gate captures): `[200] link 'Double-Wall … Set of 4 Double-Wall … Ironstone Home …'` + `[202] image 'Double-Wall … Set of 4'` becomes `[200] link 'Double-Wall … Ironstone Home …'` + `[202] image ''`.
- Chromium already prints `alt=""` images as `image ''` (Amazon home bids 77-79), so stripping `alt=""` changes no line: Amazon image lines stay at 221, and empty ones go from 124 to 221 (gate captures, read 2026-11-02).
- H2: `image_alt` dropped on 66 lines. 51 of them repeat the link's own text. 9 image-only product links keep only a hashed file name ([browser-use footprint] §3).
- The kind exists only on Amazon. The other apps have no `<img>`, and Booking failed the gate.

**(2) Real-world defect.**
- W3C failure F65: `img` without `alt` (Ma11y RIA; [Tafreshipour2024], Table 1). SC 1.1.1.
- Prevalence: 16.2% of home-page images lack alt (10.8 per page), 53.1% of pages have at least one, and 45% of the images missing alt are linked images ([WebAIM2026], Images and Alternative Text). 59-69% of sites pass the image-alt audit ([HTTPArchive2022], [HTTPArchive2024]).
- Our scan: missing alt on 18 of 60 real public pages, 112 nodes, 51 on taobao home ([DQ-form] evidence A).
- Which sites (ours, unmeasured): product grids and CMS uploads where alt is optional.

**(3) Dose.** A product-card template without `alt` produces every card without alt, so this is real within one component. All images, decorative ones included, is our ablation choice.

**(4) Side effects.**
- When an image fails to load, Chromium draws the alt text; without alt it draws a broken-image icon. On Booking, two seeded photos return 404, so the variant changes what a sighted user sees ([variant gate], "Booking alt"). That is part of the real defect, but it breaks the sighted-user constraint, so the Booking cell is excluded.
- Stripping `alt=""` adds this broken-icon risk and no information change in either harness.
- Function: 85 product links that contain an image, 0 mismatches ([function equivalence]).

**(5) Verdict.** *Real-world form* (F65; WebAIM; our scan). Amazon only; descriptive.

**(6) Search pattern.**
- DOM: visible `img:not([alt])` (box at least 16 px, `naturalWidth` above 1, not `aria-hidden`, not `role=presentation`).
- Linked-image form: an `a` whose only content is such an `img`.
- Tree: role image with name `''`, and the parent link's name `''`.
- axe [unverified]: `image-alt`.

**How it could be wrong; what would change it.** The effect is likely redundant: 51 of 66 H2 removals repeat the link text, and [Chi2024] found alt removal within noise for one model. A large alt drop on Amazon would call for an `alt~` sham (DESIGN.md §4.5, "Not in the pilot").

## K6. `tableheads`

**Rules.**
- **T1** (l. 166-168): `<th` becomes `<td data-amt="th"`, and `</th>` becomes `</td>`.
- **T2** (l. 196): author `td` selectors become `td:not(:where([data-amt]))`, so data-cell rules do not start to style the former headers.
- **T3** (l. 218-219): `font-weight:bold; text-align:center` go into the layer.

**(1) Change.**
- Tree: `columnheader` and `rowheader` become `gridcell` or `cell`, with the same name. Data cells lose their header relation, which H1 never printed.
- H1: `[32] columnheader 'ACTIONS', visible` → `[32] gridcell 'ACTIONS', visible` (patient portal appointments, gate captures). Header lines go to 0: Gmail 18, LMS 12, patient portal 72 (gate captures, read 2026-11-02).
- H2: browser-use never prints `th`. Header cells now print as `[N]<td />` like data cells (18 and 60 lines), and the interactive count rises (Gmail contacts 115 → 124, patient portal 110 → 121) ([browser-use footprint] §3).

**(2) Real-world defect.**
- W3C failure F91: table headers not marked up (Ma11y RHD, th to td; [Tafreshipour2024], Table 1). SC 1.3.1.
- Prevalence: 19% of tables have "valid data table markup" (6.8% in 2020). The unit is tables, "valid" is not defined, and layout tables are not separated out ([WebAIM2026], [WebAIM2020]). No source gives the share of data tables without `th` ([DQ-form] finding 6).
- Seen on real sites: GitLab has 25 observations with rows but no header cells ([DQ-form] evidence B).
- A likely commoner real form is not produced here: the div grid. 25 of 60 real pages have table- or grid-class divs and no table element ([DQ-form] evidence A, heuristic).
- Which sites (ours, unmeasured): hand-built tables, and CMS editor tables whose first row is only bolded.

**(3) Dose.** All header cells. The real share is unknown. Our ablation choice.

**(4) Side effects.**
- A real `th` uses `text-align: -internal-center`, which differs from the layer's `center` only in a row with inherited non-initial alignment. No app has one: 0 pixel changes ([variant gate] (a)).
- No `th` in the studied apps has a handler. Sortable headers exist only in `demo-site`, which is not studied.
- H2's added indexed cells are how browser-use serialises a real td-header table (ours).
- No function evidence: 0 treated targets ([function equivalence]).

**(5) Verdict.** *Real-world form* (F91, seen on GitLab). The dose is unmeasured, and the commoner div-grid form is out of scope.

**(6) Search pattern.**
- DOM: a `table` with at least 2 rows and 2 columns, no `th`, and no `[role=columnheader]` or `[role=rowheader]`, where the first row or first column has computed `font-weight` of at least 600 or sits in a `thead`.
- Exclude layout tables: Chrome gives them the role `LayoutTable` ([DQ-form] evidence B), so require role `table` or `grid` in the tree.
- Tree: `table` with `row` nodes and no `columnheader` or `rowheader`.
- Div-grid form: role=`generic` rows of aligned cells under a class matching `/table|grid|row|cell/i` and no `table`.
- axe [unverified]: `td-has-header`, `th-has-data-cells`.

**How it could be wrong; what would change it.** Table headers are visible on 3 apps' gate pages and need task-path capture on Booking and Robinhood (M2). If the agent reads tables from StaticText position alone, the kind is a predicted null. A drop would point at the role word in H1 or the extra indexed cells in H2.

## Controls

| control | what it is | what it rules out | why it is built this way | grounded in | how it could be wrong | status |
|---|---|---|---|---|---|---|
| `none` | `codemod.py ENV none`: the full pipeline with no rewrite (l. 169-170), so a byte-identical bundle, served from its own checkout, backend process and port on the variant schedule | That serving, uptime, database growth, port or schedule moves success | Shares every step with a variant except the rewrite; identical bytes mean any difference is serving or run noise | [Fiedler2021], [Gorgen2018] (negative controls through the same analysis) | Being identical, it cannot show build-time nondeterminism. The gate's 3 clean builds cover that (0 observation and DOM noise; [variant gate] (c)) | Gate PASS on 7 apps; function: 6 flags, 0 confirmed; H2: 0 changed lines |
| `names+` | Runs on `names_tagged` (the names build with each removed value kept as `data-amt-label(ledby)`). The H1 wrapper sets each such line's name to the clean value and keeps every other line of the variant | That the names drop is a form effect (StaticText exposure, line structure) rather than lost words | Holds the variant's own form and restores only the words. The `names~` paraphrase sham was dropped because its form differs from the variant's (DESIGN.md §11, R1 major 7) | [Yang2025] (an information-keeping rewrite moved GitLab success 35.0 → 26.7); DQ-verify C2 | A restored name beside an exposed StaticText that it now contains is a pair that clean hides (redundant StaticText is removed in clean, obs.py:358). That pair is the variant's form held on purpose; M3 checks the restored names | Not built (Stage 0) |
| `names50` | `names+` on a seeded half of the changed elements | Gives a dose point between 0% and 100% | Seeded hash per task and bid, so the half is fixed in advance | [Enomoto2026a]; D-005 | A half chosen without regard to the path may miss the 1-2 elements a task hinges on | Not built |
| `labels~` | Source sham: `htmlFor` removed as in B1; controls without an aria-label get `aria-labelledby` pointing at their label; control aria-labels kept | That the label-click change or the lost `clickable` flag explains a labels drop | Removes exactly the function part of B1 and keeps every computed name. A label referenced through `aria-labelledby` is a valid real naming pattern (ARIA16 [unverified]) | [function equivalence] (37 labels); DQ-verify C2 | `aria-labelledby` and `label for` compute the name through different accname steps. M3 checks that every target name equals clean | Not built; `codemod.py` has no `labels_sham` kind |
| machinery shams | Headings to `div role=heading aria-level=n`; landmarks to `div` with the same role and label; `th` to `td role=columnheader/rowheader`, through the same CSS machinery | That the tag rewrite and look-keeping CSS change anything the agent receives beyond the role | Same rewrite and CSS as the kind, with the role put back, so the only remaining difference is the machinery | [variant gate]; [Huang2026] | The landmark sham must add `role=banner` or `contentinfo` only where Chromium computes them (a `header` inside article, aside, main, nav or section is not banner). Otherwise it adds landmarks clean lacks; MH5 (byte-identical H1) would catch that | Checked, not run; not built |
| `fmt_wrap` | Observation edit of the clean H1 text: under each landmark line that the variant removes on the same state, insert one nameless `generic` line without bid and indent the landmark's subtree one more level | That the re-indentation which makes up most of the landmarks diff moves success | Same lines re-indented and the same line count changed (+k for −k), with landmark lines and containment kept. `fmt_indent` was dropped because it destroyed containment (DESIGN.md §11, R1 major 9) | [Enomoto2026] (format alone moved success up to 12.8 points on HTML, 4.2 on the tree) | **The inserted line has a form H1 never prints.** On the 76 clean gate pages' viewport observations, all 17,624 bid-less lines are StaticText and there are 0 `generic` lines of any kind (gate captures, read 2026-11-02). A drop could be novelty, not indentation (flag F-4) | Not built |
| `pos_info` | Observation edit of clean H1: interactive elements keep role and bid, lose name and their StaticText | That the harness, analysis and sample can detect an information loss known to matter | A pipeline control, not a defect, so its form is not required to be real | Brief D9; DQ-verify C3; [Gorgen2018] | A line edit can produce a state no page produces ([DQ-form] Option 2 risks); that does not matter for a positive control | Not built |
| `pc_break` | Every second `<button>` with `onClick` gets `onDoubleClick` instead; every second `a`/`Link`/`NavLink` gets `tabIndex={-1}` (`click_effect.py:589-621`) | In the function check: that the comparison is blind to broken function (98 of 98 flagged trials confirmed). In agent runs: how agents adapt to a functional break (exploratory) | React handler props are not DOM attributes, so markup and look stay; `tabIndex=-1` keeps the element focusable, which H1 does not print anyway | [function equivalence]; [Chen2026a] CTL-2 | Agents act by bid click, not Tab, so only the double-click half bites in agent runs (ours). Whether H1's `clickable` flag changes for a button with only `onDoubleClick` is not checked [unverified] | Built; replay: 106 of 195 tasks fail 3/3 under it |
| do-nothing | Start page evaluated with no action, per task and build | That the evaluator credits a cell without work | No LLM; evaluator only | [Chen2026a] CTL-1 | — | 0 of 195 pass on clean (replay record) |

## Flags and proposed fixes

| id | rule | problem (observed) | proposed fix | what it changes |
|---|---|---|---|---|
| F-1 | L1/L2 `landmarks` | Named `<section>` (93 in the sources) and named `<form>` (4) stay landmarks: 128 `region` and 6 `form` lines on the gate pages. The docstring, DESIGN.md §4.1 and the gate's residual check say landmarks are removed | Add `section` to L1 (to `div data-amt="section"`, with `div[data-amt="section"]` added to the sectioning list for the h1 sizes). Remove `aria-label`/`aria-labelledby` from `<form>` and add `form` to `LANDMARK_ROLES`. Make the gate's residual check use computed tree roles, not tags. An unnamed `section` is already `generic`, so the change touches only named ones | Landmarks becomes the real div-only layout (verdict: real-world form). Every landmarks bundle, its on-path flags (M2b) and the gate must be rerun |
| F-2 | B1-B3 `labels` | 129 controls keep a wrapping-label name and 71 a placeholder name; DESIGN.md and `design.yaml` say both sources are removed | Keep the rules: placeholder fallback is the commonest real form, and unwrapping labels would change click-to-toggle on 123 checkboxes and radios. Restate the scope as "explicit `for` association and control aria-labels; wrapping labels and placeholders kept" in DESIGN.md §4.1 and `design.yaml` | Description only; report the residual per task |
| F-3 | N1 `names` | 35 `role=button` divs and articles keep their aria-label | The planned Stage 0 widening: any element with an interactive role attribute (button, link, tab, menuitem, option, switch), not `input`/`select`/`textarea` (they belong to `labels`, so the kinds stay disjoint) | Booking and Reddit notification items become empty or text-named; re-gate |
| F-4 | `fmt_wrap` | The inserted bid-less `generic` line has no precedent in H1 output (0 of 17,624 bid-less lines) | Build it as designed, but register the reading in PREDICTIONS.md E-F1. A null rules out indentation and line count (novelty did not matter either). A drop cannot be read as an indentation effect, because the control also adds a novel token, and would need an indentation-only follow-up | Interpretation of E-F1 only |
| F-5 | A1 `alt` | Removing `alt=""` changes no observation line (Amazon 221 image lines either way) but adds the broken-icon visual risk that failed Booking | Remove only non-empty `alt`. Missing alt on decorative images is also F65, but it carries no information an agent loses | Smaller visual risk; information effect unchanged; re-gate Amazon `alt` |
| F-6 | docstring | "WebAIM2026: 46.1% of home pages have `<main>`": the source says a main landmark (element or role) | Reword to "a main landmark on 46.1% of home pages; `<main>` element on 37% of pages (HTTPArchive2024)" | Text only |
| F-7 | N1 `names` (grounding) | The docstring grounds the whole kind in empty-button and empty-link rates, which cover only N1a (Amazon 17, Gmail 93, Robinhood 42 empty lines; 0 on four apps) | State in DESIGN.md §4.1 that the defect is N1a and that N1b is the ordinary web; keep the strict flag as the defect-bearing contrast | Text; how the names result is described |

No rule was found ungrounded. Every kind reproduces a documented real form, except that `landmarks` currently stops short of its form (F-1) and `tableheads` covers only the narrower of two real forms.

## Exemplar kit: what to collect from real pages

For each kind, open the rendered page in Chrome (after scripts, as all prevalence sources measure; [DQ-form] finding 8). Save the DOM, `Accessibility.getFullAXTree`, the BrowserGym flattening with the H1 flags, and a screenshot. Run the search pattern in field (6). Known real carriers to start from: GitLab (N1a icon buttons, rows without header cells), Magento (headings as `strong`, admin checkboxes `checkbox ''`), Postmill (unassociated `URL` label). The real public pages of the 60-page scan are the other source: 5 with no landmark, 18 with missing alt, 24 with title-class divs ([DQ-form] evidence A). The scan kept no markup, so it must be re-run with node HTML kept ([DQ-form] Gaps).

[BreakingWeb record]: ../../docs/feasibility/2026-10-29-breakingweb.md
[variant gate]: ../../docs/feasibility/2026-10-30-variant-gate.md
[function equivalence]: ../../docs/feasibility/2026-10-30-function-equivalence.md
[browser-use footprint]: ../../docs/feasibility/2026-10-30-browseruse-footprint.md
[on-path dose]: ../../docs/feasibility/2026-10-30-on-path-dose.md
[PREDICTIONS]: PREDICTIONS.md
[DQ-form]: ../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-form.md
[DQ-defects]: ../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-defects.md
[WebAIM2020]: ../../../ai-accessibility-paper/literature/papers/L_WebAIM2020.md
[WebAIM2024]: ../../../ai-accessibility-paper/literature/papers/L_WebAIM2024.md
[WebAIM2025]: ../../../ai-accessibility-paper/literature/papers/L_WebAIM2025.md
[WebAIM2026]: ../../../ai-accessibility-paper/literature/papers/L_WebAIM2026.md
[HTTPArchive2022]: ../../../ai-accessibility-paper/literature/papers/L_HTTPArchive2022.md
[HTTPArchive2024]: ../../../ai-accessibility-paper/literature/papers/L_HTTPArchive2024.md
[Martins2023]: ../../../ai-accessibility-paper/literature/papers/L_Martins2023.md
[Tafreshipour2024]: ../../../ai-accessibility-paper/literature/papers/L_Tafreshipour2024.md
[Huang2026]: ../../../ai-accessibility-paper/literature/papers/L_Huang2026.md
[Yu2025]: ../../../ai-accessibility-paper/literature/papers/L_Yu2025.md
[GDSWay2026]: ../../../ai-accessibility-paper/literature/papers/L_GDSWay2026.md
[Chi2024]: ../../../ai-accessibility-paper/literature/papers/L_Chi2024.md
[Yang2025]: ../../../ai-accessibility-paper/literature/papers/L_Yang2025.md
[Enomoto2026]: ../../../ai-accessibility-paper/literature/papers/L_Enomoto2026.md
[Enomoto2026a]: ../../../ai-accessibility-paper/literature/papers/L_Enomoto2026a.md
[Fiedler2021]: ../../../ai-accessibility-paper/literature/papers/L_Fiedler2021.md
[Gorgen2018]: ../../../ai-accessibility-paper/literature/papers/L_Gorgen2018.md
[Chen2026a]: ../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md
