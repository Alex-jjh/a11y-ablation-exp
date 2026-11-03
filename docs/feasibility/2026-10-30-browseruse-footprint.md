# Footprint of the source-level variants in the stock browser-use observation (2026-10-30)

> **Summary:** We captured the exact page text that stock browser-use 0.13.14 sends its LLM, without calling an LLM. Captures cover clean builds and every gate-passing variant on Amazon (17 pages), Gmail (8) and the patient portal (9). Browser-use prints a tag only for elements it judges interactive or scrollable. It prints aria-label, role, alt (as `image_alt`) and AX states as attributes. It never prints accessible names, label associations, heading levels of ordinary headings, landmark elements or `th`. So the variants leave a very different footprint than in BrowserGym. `names` is the one strong kind: 133, 255 and 142 element lines lose their aria-label, and 34 (Amazon) and 85 (Gmail) controls are left with nothing printed. `labels` and `alt` are smaller: 40/21/13 control aria-labels; 66 `image_alt`, of which 51 repeat the link text. `headings` changes 3 lines on 1 of 34 pages. `landmarks` changes 31 lines, nearly all a `role=search` attribute or the tag of a scrollable `main`/`aside`. `tableheads` turns header text into `[N]<td />` elements like the data cells (18 and 60 lines). Two variants add structure instead of removing it: a `<label>` without `for` becomes an indexed element that groups its text and control. The screenshot the stock agent also receives is unchanged outside image rasters. The captures match the published runs: 86 of 93 recorded first-step clicks find their element (tag, text, aria-label) on our captured start page.

Serves: DQ-verify open question "which attributes, states and roles each harness actually serializes" (`../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-verify.md`, l.352), DQ-predict F12 (predictions rest on how the harness observes and acts), and the pending harness choice in [2026-10-30-on-path-dose.md](2026-10-30-on-path-dose.md) §4.3, which reasoned from the serializer's code; this record measures it. It follows the open item "Browser-use serialisation of the same variants" of [2026-10-29-breakingweb.md](2026-10-29-breakingweb.md) and the gate's "What this does not show" ([2026-10-30-variant-gate.md](2026-10-30-variant-gate.md)).

Script: `scripts/probe/breakingweb/browseruse_capture.py` (docstring gives inputs, outputs, how to run). Outputs: `/tmp/amt-syn/bw-bu/<env>/<build>/<page>.bu.{txt,json,png}`, `<env>/bu_diff.json`, `validate/<env>/validate.json` (regenerable). Small summary next to this record: [2026-10-30-browseruse-footprint.json](2026-10-30-browseruse-footprint.json) (per env × build: change counts by type, removed-value fate, gate verdict and BrowserGym dose, codemod counts, validation). No LLM was called; no Gemini run.

## 1. What browser-use serialises (observed in code, browser-use 0.13.14 in the BreakingWeb venv; pinned by `uv.lock`)

- Question: what part of the page reaches the stock agent's LLM as text?
- Grounds: the stock harness `breakingweb/stock_browseruse_eval.py` `run_episode` (Browser: headless, `highlight_elements=False`, viewport 1280×720 for Gemini, 1024×768 for Claude, 1600×900 for GPT; Agent: `use_vision=True`, `flash_mode=False`, default `include_attributes`). Library code: `browser_use/dom/serializer/serializer.py` (`serialize_tree`, `_build_attributes_string`), `dom/serializer/clickable_elements.py` (`is_interactive`), `dom/views.py` (`DEFAULT_INCLUDE_ATTRIBUTES`), `agent/prompts.py` (`_get_browser_state_description`).
- The rules that decide the footprint:
  - An element line `[index]<tag attrs />` is printed only if the element is interactive, scrollable or a frame. Other elements print nothing; their text nodes print as plain lines. Text nodes of one character are dropped.
  - Interactive (in order of the checks): JS click listener; `<label>` **with** `for` → never; `<label>` without `for` that holds a form control → yes; AX properties focusable/editable/checked/expanded/…; tags button, input, select, textarea, a, summary, option; attributes onclick or tabindex; role attribute or AX role in {button, link, menuitem, option, radio, checkbox, tab, textbox, combobox, slider, spinbutton, **search**, searchbox, **row, cell, gridcell**}; icon-sized boxes with an aria-label or class; `cursor: pointer`.
  - Printed attributes: HTML attributes from a fixed list (title, type, id, name, role, value, placeholder, alt, aria-label, aria-expanded, …) and AX properties from the same list (checked, expanded, disabled, required, `level`, …). An interactive element also gets `image_alt=`, `image_src=` (file name) and `image_label=` from images inside it. The AX name (`ax_name` is in the list but no AX property has that name) and the label association are never printed.
  - Indices are CDP backend node ids, not a counter. Index values differed between two identical clean builds here (e.g. `[3]<form role=search />` vs `[4]<form …>`), so diffs below compare with indices masked.
- The text is the `<browser_state>` block: page_stats, tabs, page_info, then the element tree, cut at 40,000 characters (no capture reached 13,000). The stock agent also gets the viewport screenshot and the previous action results, e.g. `Clicked button "Hello, Jordan…" aria-label=…` (`tools/utils.py`), which repeat the tag, 30 characters of text and 20 of the aria-label.

Consequence (ours): a kind reaches the browser-use text only through attributes on printed elements and through what makes an element printed. Heading, landmark and `th` semantics reach it only where such an element happens to be interactive or scrollable.

## 2. Capture and its checks

- Question: is `browseruse_capture.py`'s text what the stock agent receives?
- Method: the library's own path. `BrowserSession.get_browser_state_summary(include_screenshot=True)` (the call in `Agent._prepare_context`), then `AgentMessagePrompt._get_browser_state_description()` with the Agent defaults, on a Browser configured as in `run_episode` at 1280×720. Pages are those of `variant_run.py` and the gate: the start pages of the first 2 tasks and the env's static routes (Amazon: the fixed list). Each page is captured repeatedly, 0.8 s apart, until two normalised texts agree.
- Builds: private copies of the clean checkout (`/tmp/amt-syn/bw-bu-src{,2,3}`, backend on 127.0.0.1:8099–8101), 2 clean builds plus the `none` sham and each kind, with the codemod on env and shared sources. Codemod change counts equal the gate's in all 19 variant cells, so these are the gate's variants.
- Noise floor (observed): clean0 vs clean1 and clean0 vs `none`: 0 changed lines on all 34 pages once indices, `*` new-markers and session ids are masked. Raw index numbers differ.
- Fidelity against published runs (observed, `validate`): on the clean start pages of the first 30 tasks per env with a Gemini-3.1-Pro clean run, the recorded first-step clicks were looked up by tag, leading text and aria-label prefix. Matches: Amazon 25/30, Gmail 34/34, patient portal 27/29, i.e. 86/93. The 5 Amazon misses are category tiles recorded as `"E Electronics"` that now show an image instead of a letter (the same aria-label `Browse Electronics` is present). The runs were recorded on older app revisions ([2026-10-30-on-path-dose.md](2026-10-30-on-path-dose.md) §4.2). Index equality is 13/93, as expected for backend node ids.
- Serializer version of the published runs [unverified]: their manifests do not record it. The 5 element lines quoted in Gemini thoughts (`[15]<a aria-label=Labels />`, `[2007]<button aria-label=Unsave comment by DataWizard42 />`, `[276]<input type=checkbox checked=true />`, …) have the 0.13 format and large backend-node indices.
- How it could be wrong: (i) captures are at rest, at the top of the page; menus, open forms and scrolled states are not covered. (ii) `*[` markers depend on the previous state; they are masked in diffs. (iii) The stock Browser downloads three default extensions (uBlock Origin Lite, "I still don't care about cookies", Force Background Tab). We kept them because the harness does; we assume they do nothing on these local pages (ours). (iv) Only the 1280×720 viewport was captured. At 1024×768 (Claude) the element set within viewport + 1,000 px differs.
- What would change a decision: a capture/run mismatch on more than a few percent of recorded clicks would mean the published runs saw a different serialisation, and the footprint below would not describe them.

## 3. Footprint per kind: browser-use vs BrowserGym

Browser-use: element-tree lines changed on the captured pages (removed + added + changed, indices masked), pages changed, and lines that only moved in depth. BrowserGym: the gate's dose for the same cell (full observation lines changed / viewport lines changed, pages; `2026-10-30-variant-gate.json`). Line counts are within-harness measures. They are not comparable across harnesses: browser-use covers the viewport plus 1,000 px, the BrowserGym full observation covers the whole page. Clean element-tree lines: Amazon 2,376, Gmail 1,547, patient portal 1,117.

| env | kind | browser-use lines (pages) | what changed in browser-use | BrowserGym full / viewport (pages) |
|---|---|---|---|---|
| amazon | landmarks | 18 (17/17) | `role=search` dropped from the indexed search `<form>` 17; `<aside aria-label=Search filters>` → `<div …>` 1 | 6,947 / 1,807 (17) |
| amazon | headings | 3 (1/17) | 3 indexed `<h3 level=3 />` in the search filter sidebar → `<div />` | 368 / 114 (17) |
| amazon | names | 133 (17/17) | aria-label dropped: 99 partial, 34 empty | 325 / 197 (17) |
| amazon | labels | 40 (17/17) | control aria-label dropped: 18 full, 3 partial, 2 none, 17 empty | 46 / 46 (17) |
| amazon | alt | 66 (6/17) | `image_alt` dropped: 51 full, 6 partial, 9 empty | 340 / 28 (8) |
| gmail | landmarks | 9 (8/8) | `role=search` dropped 8; `<main aria-label=Search>` → `<div …>` 1 | 2,723 / 1,769 (8) |
| gmail | headings | 0 (0/8) | none | 28 / 20 (4) |
| gmail | names | 255 (8/8) | aria-label dropped: 84 full, 85 partial, 85 empty, 1 none | 537 / 316 (8) |
| gmail | labels | 30 (8/8), +9 depth | control aria-label dropped 21 (12 full, 3 partial, 2 none, 4 empty) + 1 textarea; 8 new `[N]<label />` lines | 48 / 22 (4) |
| gmail | tableheads | 18 (2/8), +14 depth | 18 new `[N]<td />` lines around former header text | 36 / 0 (2) |
| patient portal | landmarks | 4 (4/9) | `\|scroll element\|<main />` → `<div />` 4 | 1,927 / 1,218 (9) |
| patient portal | headings | 0 (0/9) | none | 78 / 64 (9) |
| patient portal | names | 142 (9/9) | aria-label dropped: 82 full, 60 partial | 209 / 136 (7) |
| patient portal | labels | 13 (3/9) | control aria-label dropped: 11 partial, 1 empty, 1 none | 48 / 34 (3) |
| patient portal | tableheads | 60 (6/9), +60 depth | 60 new `[N]<td />` lines | 144 / 96 (6) |

Removed-value fate (for aria-label and `image_alt` removals). We count how many words of the removed value are still printed on the element line (other attributes such as placeholder, id, title, value) or in its subtree (text and child attributes):

- full: every word.
- partial: some words.
- none: no word, but something is still printed.
- empty: nothing is printed for the element at all.

This is a word-overlap measure (ours). For example, "Amazon Home" → text "amazon" counts as partial. Words in the 3 lines around the element are counted separately; they change at most 3 cases per cell. Examples are in the JSON (`removed_value_fate_examples`).

What each agent loses, per kind (observed; readings marked ours):

- **names.** Both agents lose the same information. In BrowserGym the accessible name falls back to the visible text (`link 'Shopping cart, 0 items'` → `link '0 Cart'`). In browser-use the `aria-label=` attribute goes and the visible text that was always printed under the element stays (`[N]<a aria-label=Shopping cart, 0 items />` → `[N]<a />` + `Cart`). Two differences:
  - When the aria-label equals the visible text (Gmail 84 of 255, patient portal 82 of 142, e.g. `aria-label=Inbox` on the link "Inbox"), BrowserGym shows no change and browser-use loses a duplicate. That is no information loss (ours).
  - Browser-use drops one-character text. So `Notifications, 1 unread` leaves an empty `[N]<a />` in browser-use but `link '1'` in BrowserGym.
  - Empty controls after the variant: Amazon 34 (submit search, notifications), Gmail 85 (star buttons, previous/next page), patient portal 0.
- **labels.** BrowserGym loses the label association (`combobox 'Language'` → `combobox ''`). Browser-use never showed the association, so removing `htmlFor` has no direct footprint. Its footprint is the control aria-labels the codemod also removes. Placeholder and id often carry the same words: `Search Amazon` placeholder, ids such as `settings-order-updates` and `profile-dob`. 17 of Amazon's 40 removals leave the department `<select>` with only its option list. One footprint goes the other way. In Gmail's compose and contacts forms, the `<label>` that wraps a control loses `for` and becomes an indexed `[N]<label />` (8 lines). Its text and its control are then nested under one element, and page_stats shows 4 more interactive elements on compose. The browser-use text then shows the association more explicitly than in clean (ours).
- **alt.** Browser-use shows alt only as `image_alt=` on an interactive ancestor. 51 of 66 removals repeat the product title that the link also prints as text. The 9 empty cases are image-only product links, which keep only a hashed file name (`image_src=71au2ZYDWuL._AC_UL320_.jpg`). Category tiles keep a meaningful file name (`image_src=kitchen-cookware.svg`, `electronics-audio.svg`), which carries the category whatever the alt. BrowserGym has no file names.
- **headings.** BrowserGym loses the heading role on every page (`heading 'X'` → `StaticText 'X'`). Browser-use prints heading text as plain text in clean and in the variant alike. The only footprint is 3 sidebar `h3` that the serializer happens to index, where `level=3` and the tag go. Gmail and the patient portal: no change on any page.
- **landmarks.** BrowserGym loses banner, navigation, main and contentinfo lines and re-indents their subtrees. Browser-use never prints landmark elements. Two things change:
  - The search form loses `role=search`: it is indexed because `search` is in browser-use's interactive role list, and it stays indexed afterwards.
  - Scrollable or interactive `main`/`aside` containers change their tag to `div`.

  Landmark aria-labels stay (`<div aria-label=Search filters />`).
- **tableheads.** BrowserGym turns `columnheader` into `gridcell`/`cell` and keeps the name. Browser-use never prints `th`. In clean, header cells print as bare text inside an indexed `[N]<tr />`, while data cells print as `[N]<td />`, because the AX role `cell` counts as interactive. In the variant, header cells also become `[N]<td />` (18 and 60 lines), so the header row looks like a data row. The interactive count rises: Gmail contacts 115 → 124, patient portal appointments 110 → 121. The header text and its position are unchanged. The loss is an implicit cue: text without `td` marked the header. Reading that cue requires the model to notice the absence (ours).

Neutralisers (observed):

- The viewport screenshot is unchanged outside image rasters. Gmail and patient portal: 0 changed pixels on every page and variant. Amazon: at most 0.24% of viewport pixels; all but at most 19 pixels per page lie inside image boxes, and those 19 lie within 6 px of an image box edge. The clean-vs-clean floor is 0.04%, all inside images. The stock agent runs with `use_vision=True`, so headings, landmarks and table headers stay fully visible to it as layout.
- Visible text is printed for every element, so any name made of visible text survives.
- Placeholder, id and image file names often repeat the removed words.
- The action result after a click repeats the tag, the visible text and the aria-label. A variant shortens it by the aria-label only.

## 4. What this means for the design (ours)

- Question: which kinds can show an effect on the stock browser-use agent?
- Reading:
  - names: a clear footprint on every captured page of all three apps, with tens of controls left unnamed in Amazon and Gmail. It is testable under browser-use.
  - labels, alt: a small footprint, mostly words that are also printed nearby. Expected effect small.
  - headings, landmarks, tableheads: near-null in the text (3, 31 and 78 lines over 34 pages, none of them removing visible text). Under browser-use these kinds also reach the agent through `find_elements` selectors and `extract` markdown ([2026-10-30-on-path-dose.md](2026-10-30-on-path-dose.md) §4.3; not captured here). The screenshot shows them unchanged.
  - This confirms the code reading of the on-path record with measured counts. It contradicts the description of the text observation in [Yin2026](../../../ai-accessibility-paper/literature/papers/L_Yin2026.md) Table 6 (landmark and heading roles reach the text agents) for the installed browser-use. Yin2026 Appendix D.4 itself says the text observation "is not the raw accessibility tree".
- How it could be wrong: task-path states (open forms, filtered tables, menus) may index more headings or landmarks than resting pages. For example, a clickable section heading would print `level=`. The on-path replays ([2026-10-30-on-path-dose.md](2026-10-30-on-path-dose.md)) can be captured with this script's state function to check. Other browser-use versions serialise differently.
- What would change a decision:
  - If a study wants all six kinds to reach the agent, the main harness must be BrowserGym's AXTree text, or a browser-use with a tree-preserving serializer, not stock browser-use.
  - If stock browser-use stays, report it as the leaderboard harness. Run headings, landmarks and tableheads as predicted near-nulls: this record's counts are the mechanism-only prediction for DQ-predict Phase 0b.
  - A browser-use effect for headings or landmarks larger than for names would point to the non-text channels (screenshot, `extract`, selectors), not to the serialisation.

## Reproduce

```bash
C=~/.workspace/_refsrc/BreakingWeb; S=~/.workspace/ai-agent-accessibility/scripts/probe/breakingweb/browseruse_capture.py
for i in "" 2 3; do mkdir -p /tmp/amt-syn/bw-bu-src$i && cp -a $C /tmp/amt-syn/bw-bu-src$i/; done
export PATH=$HOME/.local/share/mise/installs/node/24.20.0/bin:$HOME/.local/bin:$PATH BREAKINGWEB_AUTO_BUILD_FRONTENDS=0 ANONYMIZED_TELEMETRY=false
run() { cd /tmp/amt-syn/bw-bu-src$1/BreakingWeb && BW_ROOT=$PWD BW_PORT=$2 PYTHONPATH=$PWD $C/.venv/bin/python $S "${@:3}"; }
run "" 8099 drive amazon /tmp/amt-syn/bw-bu --kinds none,landmarks,headings,names,labels,alt &
run 2 8100 drive gmail /tmp/amt-syn/bw-bu --kinds none,landmarks,headings,names,labels,tableheads &
run 3 8101 drive patient_portal /tmp/amt-syn/bw-bu --kinds none,landmarks,headings,names,labels,tableheads &
wait
for e in amazon gmail patient_portal; do $C/.venv/bin/python $S diff $e /tmp/amt-syn/bw-bu; done   # BrowserGym side from /tmp/amt-syn/bw-gate/final
$C/.venv/bin/python $S summary /tmp/amt-syn/bw-bu amazon gmail patient_portal
run "" 8099 validate amazon /tmp/amt-syn/bw-bu/validate/amazon --tasks 30   # likewise gmail, patient_portal
```

The three drives took about 7 minutes in parallel; validation took about 2 minutes per env. Each drive restores the env and shared sources with `git checkout` and rebuilds clean at the end. Afterwards all three copies and `~/.workspace/_refsrc/BreakingWeb` showed only the four allowed bind-fix diffs, and no backend or browser process was left running.
