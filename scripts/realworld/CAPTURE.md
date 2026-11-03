# Capturing real pages for the defect exemplar kit

> **Summary:** How to save a real page in Chrome after its scripts have run, so that `analyze.py` can look for the six defect kinds of the v2 variants in the form `codemod.py` writes them. The main route is a DevTools snippet (`capture_snippet.js`). It downloads one JSON file with the rendered DOM, URL, viewport, timestamp and user agent. Before the download it removes input values and scripts and masks e-mail addresses, long numbers, tokens and URL query values. The fallback is Chrome's "Save page as > Webpage, Single File" (MHTML). MHTML is not cleaned, so use it only on logged-out pages. This file also covers what to capture per site, how to name files, and how to run the analyser.

## Why the rendered page

The reference form of a defect is the DOM after scripts and styles have run, not the HTML the server sends. WebAIM's prevalence figures are measured on that DOM: "The WAVE accessibility engine was used to analyze the rendered DOM ... after scripting and styles were applied" ([WebAIM2026](../../../ai-accessibility-paper/literature/papers/L_WebAIM2026.md); DQ-form finding 8). BreakingWeb's apps are React apps, so their defects also exist only after rendering. "View source" or `curl` would miss both.

The page has to be saved from your own browser. Our 2026-10 automated scan got block, captcha or redirect pages instead of the site for 31 of 102 pages; etsy, reddit and medium are among them (DQ-form, "Our own evidence" A).

## One-time setup

1. Create a separate Chrome profile named "AMT capture": Chrome menu > Profiles > Add, continue without an account. Keep real logins out of it. Sign in there only with the test accounts that `TARGETS.md` asks for.
2. Set the window to the agents' viewport, 1280 x 720. Open DevTools (F12), switch on the device toolbar (Ctrl+Shift+M, Cmd+Shift+M on a Mac), choose "Responsive" and type 1280 x 720. BreakingWeb's agent runs at this size, and `analyze.py` renders at the size the file records. Pages that change layout with width (hamburger menus) differ at other sizes. If you capture at another size, add `__w<width>` to the file name.
3. Store the snippet as a DevTools Snippet: DevTools > Sources > Snippets (in the `>>` menu if hidden) > "+ New snippet". Name it `rwk-capture`, paste the whole of `capture_snippet.js` and save with Ctrl+S. You can then run it on any page with Ctrl+Enter (Cmd+Enter) in the snippet editor, or with Ctrl+P (Cmd+P) and typing `!rwk-capture`.
   - Pasting into the Console tab works too. The first time, Chrome asks you to type `allow pasting`.
4. Make a folder outside every git repository, for example `~/amt-realworld/raw/`. Saved pages are third-party content: they stay out of our repositories. Our records quote only short snippets and counts.

## Per page

1. Open the page in the capture profile. Wait until it has finished loading, then 3 more seconds.
2. Lazy loading: many sites load images and list items only when they scroll into view. The snippet scrolls the page down in viewport-sized steps (at most 40, so endless feeds stop), returns to the top and then captures; this takes up to about 20 s. On pages where scrolling changes the state (a feed that keeps loading, a page that hides the header), type `window.RWK_AUTOSCROLL = false` in the console first, scroll by hand, and run the snippet. If a section still loads only on hover or click (tabs, "show more"), open it by mouse before running.
3. Close cookie banners and pop-ups the way a user would: "Reject all" or the close button. Note in the file name if a banner is still open (`__banner`).
4. Run the snippet. A prompt asks for the file name stem. It suggests `CATEGORY__<host>__PAGETYPE`; replace both upper-case parts. See "File names" below. Chrome then downloads `<stem>__<YYYYMMDD-HHMM>.rwk.json`. The console prints the file name and counts of what was removed.
5. Optional second state: open the main menu, a filter panel or the account menu by mouse, and run the snippet again with `__menu-open` (or `__filters-open`) appended. The variant gate captures pages at rest only (2026-10-30-variant-gate.md, "What this does not show"). Open states are where several defects sit.
6. Do not type anything personal into forms before you capture. The snippet clears input values, but a typed name in a search box can also show up as page text elsewhere ("Results for ...").

### What the snippet removes (and what it cannot)

Removed or masked in the saved copy. The open page keeps everything except `data-rwk-*` attributes, which exist for a few milliseconds while the snippet reads styles.

- Every `<script>`, `<noscript>` and `<base>` element, all HTML comments, `on*` handler attributes, `nonce`, `integrity`, `srcdoc`.
- `<meta>` elements whose name, property or http-equiv mentions csrf, token, nonce, session, user, account, email or refresh.
- Values of all inputs (the visible text of submit, reset and button inputs is kept), textarea text, contenteditable content.
- Query values and fragments of every URL become salted hashes (`?category=h1x9k2`). Two links to different destinations stay different within the file, which the ambiguous-link test needs. The salt is random for each capture and is not saved, so the values cannot be recovered or matched across files. Parameter names and in-page anchors such as `href="#main"` are kept.
- In page text and in text or URL attributes: e-mail addresses become `[email]`, runs of 6 or more digits become zeros (order, account, phone and card numbers), token-like strings of 32 or more letters and digits become `[token]`.
- The snippet does not read cookies, localStorage, sessionStorage or IndexedDB, and it sends nothing over the network.

It cannot recognise personal names, street addresses or photos of people in page text. So capture logged out wherever possible. Where `TARGETS.md` says a test account is needed, use one that holds no real personal data. Before you move a file anywhere, search it for your name and your real e-mail:

```bash
grep -il -e "yourname" -e "you@realmail" ~/amt-realworld/raw/*/*.rwk.json   # prints files that still contain them
```

Not captured: closed shadow roots, iframe contents (payment widgets, embedded editors), canvas pixels, and stylesheets that the site does not let scripts read (CSS from another domain). The `data-rwk-*` facts stand in for the missing CSS. They record, per element, display:none, visibility, the font size, weight and alignment of text, and boxes of images, tables and layout containers.

### Fallback: MHTML

Use it when the snippet fails (it prints an error), or as a second copy of a logged-out page.

1. Ctrl+S (Cmd+S) > "Save as type": **Webpage, Single File** > name the file with the same stem plus `.mhtml`.
2. MHTML is Chrome's own serialisation of the current DOM. It drops scripts and keeps the page's CSS and images, and it renders more faithfully than the JSON. It is **not cleaned**. Our test page kept its e-mail address, a prefilled input value, a textarea text, a draft, a CSRF meta token, a session query string and the long digit runs (`docs/feasibility/2026-11-02-realworld-kit.md`, privacy test). Do not use MHTML on any logged-in page.

## File names

`<category>__<site>__<pagetype>[__<state>]__<YYYYMMDD-HHMM>.rwk.json` (the snippet adds the time stamp)

- `category`: one of `shopping`, `email`, `forum`, `finance`, `travel`, `lms`, `patient`. These are the seven BreakingWeb apps; `TARGETS.md` gives the mapping.
- `site`: short host, for example `amazon`, `oldreddit`, `ycombinator`, `booking`.
- `pagetype`: from the table below, for example `product`, `search`, `cart`.
- `state` (optional): `menu-open`, `filters-open`, `banner`, `loggedin`, `w1440`.

Example: `shopping__amazon__search__20261103-1412.rwk.json`.

## What to capture per site

The page types are those that the BreakingWeb clone of the category models, from the app's routes (`breakingweb/environments/<env>/src/App.tsx`) and the gate's route list (`variant_gate.ROUTES`). Two to four pages per site are enough. Several sites per category matter more than many pages of one site.

| category | BreakingWeb env | page types (BreakingWeb routes they correspond to) | kinds most likely to show up (our guess, to check) |
|---|---|---|---|
| shopping | `amazon` | `home`, `search` (results for a query), `product` (one product page), `cart` (after adding one item), `category` | names (repeated "Add to cart", icon buttons), alt (product images in links), headings (titles as styled divs) |
| email | `gmail` | `inbox`, `message` (one opened mail), `compose` (empty new message), `settings` | names (icon-only toolbar buttons), labels (compose fields), landmarks |
| forum | `reddit` | `feed` (front page or a community), `post` (one post with comments), `submit` (new-post form, logged in), `search` | names (vote, share and "reply" buttons repeated per comment), landmarks, tableheads (old table layouts) |
| finance | `robinhood` | `quote` (a stock page), `portfolio`, `order` (order ticket), `history` (transactions table) | tableheads (holdings and history tables), names, labels (order form) |
| travel | `booking` | `home`, `search` (results with filters), `property` (hotel page), `booking` (the guest-details step, stopped before payment) | labels (date and guest fields), names ("See availability" repeated), headings, alt |
| lms | `lms` | `dashboard`, `course` (course home), `assignment` (one assignment), `grades`, `calendar` | headings, tableheads (grades table), landmarks |
| patient | `patient_portal` | `appointments` (list or the booking flow), `messages`, `labs` (results table), `billing` | labels (scheduling forms), tableheads (results), landmarks |

Before payment or any final submit step, stop. Never place an order, send a message to a real person or book a real appointment.

## Moving files and running the analyser

Downloaded pages are untrusted data. On the dev machine, put each batch in its own new, empty directory. Run the analyser from elsewhere, with Python's isolated mode, and pass the paths as arguments:

```bash
mkdir -p /tmp/amt-syn/rwk/real/20261103 && cp ~/Downloads/*.rwk.json ~/Downloads/*.mhtml /tmp/amt-syn/rwk/real/20261103/   # or scp/rclone
cd ~/.workspace/ai-agent-accessibility
~/.workspace/_refsrc/BreakingWeb/.venv/bin/python -I scripts/realworld/analyze.py /tmp/amt-syn/rwk/real-out/20261103 /tmp/amt-syn/rwk/real/20261103
```

Output, per page: `<file>.analysis.json` (per kind: count, verdict, up to 5 examples with trimmed HTML, accessible name and tree line), `<file>.tree.txt` (BrowserGym-style tree, all nodes) and `<file>.viewport.txt` (viewport only; approximate, see `analyze.py`). For all pages together: `summary.md` and `summary.json`. Add `--examples 20 --all-items` for every instance.

The analyser never runs the page's scripts and blocks all network. Each page gets a new, empty browser profile. `analyze.py`'s docstring lists the measures, and the record lists the tests.
