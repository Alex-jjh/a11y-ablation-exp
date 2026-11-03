# Target sites for the defect exemplar kit

> **Summary:** Real public sites to capture with `CAPTURE.md`, grouped by BreakingWeb's seven apps, logged-out pages first. Each row says which pages need no login, which need a test account, and which BreakingWeb clone the site corresponds to. Two reference sites with strong accessibility practice (GOV.UK, NHS.uk) serve as low-defect controls for false alarms. We have not visited any of these sites for this list. URLs, page layouts and login requirements come from general knowledge as of 2026 and are [unverified] until Alex captures them.

## How the list was chosen

- **Category = BreakingWeb clone.** BreakingWeb's seven environments are named after real products: Gmail, Amazon, Reddit, Robinhood, Booking, an LMS and a patient portal (BreakingWeb `README.md`, line 9). The first site in each category is the one the clone imitates. The others give other markup traditions (a template-era site, a React or web-component site, an open-source product).
- **Logged out first.** Logged-out pages carry no personal data, and the MHTML fallback is safe only there (`CAPTURE.md`). Where the clone's main pages exist only behind a login (inbox, portfolio, patient messages), the row names a test-account route or a public demo.
- **Contrast within a category.** Old and new versions of the same site (old.reddit.com and reddit.com) and table-era sites (Hacker News) are included on purpose. If a kind occurs on real sites, it should occur in more than one front-end generation.
- **Low-defect controls.** GOV.UK and NHS.uk follow the GOV.UK / NHS design systems, which are built for accessibility ([GDSWay2026](../../../ai-accessibility-paper/literature/papers/L_GDSWay2026.md) is the GDS guidance close-read). Many instances flagged there would point to false alarms in `analyze.py`.

## Shopping (BreakingWeb `amazon`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| amazon.com | home, search (`/s?k=headphones`), product page, cart (add one item while logged out) | orders, account (test account only) | The clone's model. Product grids repeat "Add to cart" and use image-only links. |
| ebay.com | home, search results, item page | cart needs no login [unverified] | Older templating next to newer React pages. |
| walmart.com | home, search, product, cart | — | May show a bot check; if so, note it and skip. |
| etsy.com | search, listing page | — | Our 2026-10 automated scan got a 9-element page here (DQ-form, evidence A); in a real browser it should load. |
| ikea.com | category page, product page | — | Large icon-button use (wishlist, compare). |

## Email (BreakingWeb `gmail`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| mail.google.com (Gmail) | — | inbox, one opened message, compose (empty), settings | The clone's model. Create a fresh Google test account that has received only Google's welcome mails, or 1-2 mails you send it from another test account. |
| outlook.live.com | — | inbox, message, compose | Microsoft test account. |
| proton.me/mail | — | inbox, compose | Proton test account (free). |
| Roundcube (open-source webmail) | demo instance if one is public [unverified] | inbox, compose | Template-era webmail; useful contrast. Skip if there is no public demo. |

Capture e-mail pages with the JSON snippet only, never MHTML. Even a test inbox shows the account's own address, which the snippet masks.

## Forums (BreakingWeb `reddit`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| reddit.com | front page or a community (`/r/AskHistorians`), one post with comments, search | submit (new-post form) | The clone's model. Uses web components with shadow DOM; the snippet captures open shadow roots. |
| old.reddit.com | same pages | — | Old markup of the same site: a likely place for the kinds in pre-ARIA form. |
| news.ycombinator.com (Hacker News) | front page, one item with comments | submit | Layout built from nested tables. Expected to have no landmarks and no th; a test of whether the analyser keeps layout tables apart from data tables. |
| stackoverflow.com | question list, one question | ask form | Design-system site (Stacks). |
| meta.discourse.org | latest topics, one topic | reply editor | Discourse, open-source forum software that is used on many sites. |

## Finance (BreakingWeb `robinhood`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| robinhood.com | public stock page (`/us/en/stocks/AAPL/`) [unverified path] | portfolio, order ticket, history | The clone's model. Logged-in pages need a funded account, so use only the public pages. |
| finance.yahoo.com | quote page (`/quote/AAPL`), historical data (`/quote/AAPL/history`), a screener | portfolio (test account) | Historical-data and screener tables: a tableheads target. |
| google.com/finance | quote page, market overview | watchlist | |
| nasdaq.com | quote page, historical data | — | Data tables. |
| a paper-trading account (TradingView or Webull paper trading) [unverified] | — | portfolio, order ticket, order history | The only way to see order forms and positions without real money. Test account. |

## Travel (BreakingWeb `booking`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| booking.com | home, search results (one city, dates a month ahead), property page, the guest-details step (stop before payment) | trips, saved lists | The clone's model. Dense filters with checkboxes; date pickers. |
| expedia.com | home, hotel search, hotel page | trips | |
| airbnb.com | home, search, listing page | trips, wishlists | React; many icon-only buttons (save, share). |
| kayak.com | flight search results | — | Result cards repeat "View deal". |

## LMS (BreakingWeb `lms`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| Canvas (canvas.instructure.com, free teacher account) [unverified that free accounts still exist] | public course pages if a course is set public | dashboard, course home, assignment, grades, calendar | The clone imitates a Canvas-like LMS (routes `courses/:id/assignments`, `grades`, `peer-reviews`). A course of your own with no students carries no personal data. |
| Moodle demo (moodle.org demo site) [unverified] | — | dashboard, course, assignment, grades (with the demo's published student login) | Demo accounts are shared and reset; nothing personal. |
| ocw.mit.edu | course home, an assignments page, a calendar page | — | Public, static course pages. |
| learn.xjtlu.edu.cn (your own LMS) | — | only pages that show no other person's name or work (course home, an assignment brief) | Optional. Skip any page with classmates, grades or messages. |

## Patient portals (BreakingWeb `patient_portal`)

| site | pages without login | pages needing an account | notes |
|---|---|---|---|
| zocdoc.com | doctor search results, one doctor profile with the appointment picker | — | Public scheduling flow: appointment lists and booking forms without a portal login. Stop before booking. |
| mychart.org / a hospital's MyChart login and "schedule an appointment" public pages [unverified] | login page, public scheduling or "find a doctor" pages | — | Never your own portal: it holds real health data. |
| mayoclinic.org | "request an appointment" form, find-a-doctor results | — | Forms with many fields: a labels target. |
| nhs.uk | "book a GP appointment" information pages, a service finder | — | Low-defect control (NHS design system). |

## Low-defect controls

| site | pages | why |
|---|---|---|
| gov.uk | home, a search results page, a start page of a service (for example "Renew your passport") with its first form step | GOV.UK Design System. Expect few or no instances. Instances found here are the first place to look for analyser false alarms. |
| nhs.uk | as in the patient table | NHS design system. |

## Which kinds we expect where, and what would change a decision

- These expectations are ours, from the known build tradition of each site, not observations. The kit's purpose is to replace them with counts.
- The kind we most need real exemplars for is **tableheads**. DQ-form finding 6 says the sources give rates but not the real form of a table defect. Finance history tables, LMS grades and Hacker News are the main chances.
  - If no data table without th turns up on any captured page, the paper says the tableheads variant has no real-world exemplar in our sample. It then rests on F91 and the rate figures alone.
- If a kind shows up only as `kind-only` (present, but not in the form the codemod writes), the variant stays. The paper then states that its form is one of several real forms, and names which.
- If the controls (GOV.UK, NHS.uk) show more than a handful of instances of a kind, read them by hand before counting that kind on other sites.
