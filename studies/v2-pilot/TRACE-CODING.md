# v2 pilot: trace codebook

> **Summary:** One observer agent reads each H1 trace and codes what the web agent did, with step numbers and verbatim quotes as evidence. There are 24 codes in six groups: what the agent noticed, how it compensated, its errors, how the run ended, harness artefacts, and what the observer thinks of the final state. Each code has a definition, include and exclude rules, an example, and the prediction or threat it serves. The observer does not see the cell, build, run id, repeat, date or model, and sees the evaluator verdict only in a second pass that codes the end-of-run codes. The defect itself cannot be hidden, because the observation shows it; codes are therefore defined on behaviour relative to what the agent was shown, and the observer's guess about the condition is recorded last as a blinding check. Agreement: two independent observers code a stratified 20% sample (at least 120 traces); a code enters a result only at Cohen's kappa of at least 0.70. In the pilot these codes are exploratory (DESIGN §4.6); none is a registered outcome.

Scope: H1 traces (BrowserGym text harness, written by `h1_wrapper.py`). The H2 browser-use traces have another format and are not covered yet.

Files: the observer prompt and output schema are in [`trace_observer_prompt.md`](trace_observer_prompt.md). Packets come from `scripts/probe/breakingweb/h1_wrapper.py packet` (pass A without the verdict, pass B with it). Traces are written by `h1_wrapper.py run` to `/tmp/amt-syn/traces/<run_id>/`. Close-reads are cited by key from `../../../ai-accessibility-paper/literature/papers/L_<key>.md`; "ours" marks our own inference.

## 1. What the codes are for

The primary outcome is the backend evaluator's verdict (DESIGN §4.6). A verdict says whether a run failed, not how. The codes answer three questions the verdict cannot:

1. **Did the treatment reach the agent's decision?** The variant gate shows the defect is in the observation. The codes show whether the agent's reasoning or choices responded to it (N codes, S codes). A drop with no sign of this is suspect; so is a large sign of it with no drop.
2. **Through which route does a drop happen?** The predictions name where the information survives: visible text, sibling StaticText, tree position (PREDICTIONS.md, PC1-PC2 "Where the information survives"). S1 and S2 measure whether agents use these routes; E1, E5 and E6 measure the errors the mechanisms predict.
3. **Is a failure about the defect at all?** Loops, scroll hunts, budget exhaustion, action errors, harness artefacts and evaluator disagreements (E2-E4, F4, H codes, J1) are failure routes the defect does not cause. If they differ between cells, they are confounds or threats (DESIGN §9).

**Grounds.** BreakingWeb's own failure analysis classes failed runs as belief failures (the agent ends the run while a required change is missing), action failures and overreach. For text agents the shares were 75%, 7% and 18% ([Yin2026](../../../ai-accessibility-paper/literature/papers/L_Yin2026.md)). F1, E1/E5 and F3 carry these three classes. Coding a trace's validity before its failure cause follows [Dong2026](../../../ai-accessibility-paper/literature/papers/L_Dong2026.md): 15.3% of the 150 FAIL verdicts it audited were wrong. That is why J1 (evaluator disagreement) is coded in pass B, after the behaviour codes.

## 2. What the observer sees, what is hidden, and what cannot be hidden

| Item | Observer sees | Why |
|---|---|---|
| Task goal, env, task id | yes | Needed to judge whether an action serves the goal. The task id says nothing about the cell: every task runs in clean and in its kinds (`cells_by_task.json`) |
| Per step: URL, the exact observation text, summary marker, reasoning text, model text, action, action error, stop reason | yes | The behaviour to be coded |
| End reason, steps used, step cap | yes | F2 and F4 need them |
| Evaluator verdict, checks, negative checks, final URL | **pass B only** | Codes in pass A are made without the outcome, so the outcome cannot colour them (ours; the two-stage order follows [Dong2026](../../../ai-accessibility-paper/literature/papers/L_Dong2026.md)) |
| Cell, build, bundle hash, codemod, run id, repeat, date | **no** | The condition |
| Model id | **no** | The reasoning style can still suggest the model family. Hiding the id removes an easy cross-packet comparison. Model is a crossed factor, so the analysis does not need the observer to be blind to it, but nothing is lost by hiding it |
| Other traces of the same task | **no** | Each packet goes to a fresh observer with no memory. With two packets of one task side by side, the defect would show as a diff against clean |
| The study's purpose and the list of defect kinds | **no** | The prompt says the study is about how web agents act on structured page text. It does not say that pages were altered, and it does not name the kinds or the cells. The code definitions must name page features (names, labels, headings, tables), because that is what the codes are about; neutral code labels (UNCLEAR_NAME, STRUCTURE_REMARK, MARKUP_TALK) keep that to a minimum |

**What cannot be hidden.** The observation is the treatment. A names trace shows `button ''` where clean shows `button 'Star'`; a headings trace shows `StaticText 'Inbox'` where clean shows `heading 'Inbox'`. An observer who knows accessibility markup can infer the cell from one observation. Four rules limit the damage:

1. **Codes are defined against what the agent was shown, not against clean.** N1 is "the reasoning refers to an element whose printed name is empty or uninformative", not "the agent noticed the removed name". An observer applies it the same way to a clean page with a natively unnamed icon. Clean BreakingWeb pages have such elements: 1,375 ambiguous name instances on 36 clean pages, booking's 'See deal' x20, reddit's aria-label 'Upvote' on all 81 posts (`docs/feasibility/2026-11-02-realworld-kit.md`).
2. **The N codes are manipulation-check codes, not outcome codes.** They are expected to differ by cell. They are reported as evidence that the treatment reached the agent, never as an effect.
3. **Blinding is measured.** The observer's last field is a guess at whether the page was unusual and how (`condition_guess`). It is written after every code. Two numbers are reported: the guess accuracy against the true cell, and every code's rate split by whether the guess was right. Grounds: ours; an unblinded coder can drift toward the expected pattern, and recording the guess is the usual check for this (Bang's blinding index [unverified]: not in the library).
4. **Mechanical measures back the codes that matter most.** Bid not in the observation, repeated actions, same-name wrong targets and the first step that reaches the goal page are computed by script from the trace (§5). Agreement between an observer's E2 or E4 and the script's measure is a validity check on the observer.

## 3. Coding rules common to all codes

- **Unit.** Every code is coded once per trace: `present`, `absent`, or `na` (cannot be judged; the reason is stated). A `present` code lists the steps where it occurs.
- **Evidence.** Every `present` needs at least one verbatim quote from the packet, with the step and field (`observation_text`, `reasoning_text`, `model_text`, `action`, `action_error`). A script rejects any coding whose quote is not an exact substring of the named field. The same rule is used for the literature quote checker (paper repo `literature/`). A rejected coding is re-requested once; if it fails again, the code is set to `na` with reason `evidence_invalid`.
- **Reasoning is a summary, and silence is not absence.** For Claude models the reasoning text is a summary written by the API (`thinking.display: "summarized"`); the raw chain of thought is never returned (claude-api reference, cached 2026-10-06). GPT-5.6 returns a summary only when `reasoning.summary` is sent (probe 2026-11-02, `/tmp/amt-syn/h1/probe-20261102b.json`). A thought the summary leaves out cannot be seen. So the codes that need reasoning (N1-N4, S3, H3) can be coded `present` from reasoning or model text, but never `absent` because the reasoning is silent. When a step has `reasoning_visibility` `none`, `encrypted` or `empty_text`, they are `absent` only if the model text and the actions also show no sign. For a trace with no reasoning text on more than half its steps, they are `na`.
- **Action-based codes do not need reasoning.** S1, S2, S4, S5, E1-E6 and the F codes are judged from actions, observations and their effects. Reasoning can support them but is not required.
- **One step can carry several codes.**
- **The observer does not judge whether a run "should" have succeeded.** That is the evaluator's job (pass B J1 is the one exception, and it is an audit flag, not a re-score).

## 4. Codes

Format per code: definition; include; exclude; example (constructed from BreakingWeb observation forms; bids and names are of the kind the traces contain); serves.

### N: what the agent noticed (manipulation-check codes, need reasoning or model text)

**N1 NOTICE_UNNAMED.** The reasoning or model text refers to a target or candidate element whose printed name is empty, a glyph, or does not say what it does.
- Include: "the button has no label", "an unnamed link", "button '' next to the title", "the icon button (☆)".
- Exclude: complaints about missing *content* (an empty inbox, no search results); an element the agent simply has not found.
- Example: step 4 reasoning "There are three `button ''` entries in the toolbar; the second one is probably star." → present, step 4.
- Serves: PC1/PC2 mechanism (strict names tasks: the acted-on control becomes `''`); E-N1, E-N3. Manipulation check for names and labels.

**N2 NOTICE_AMBIGUOUS.** The agent says that two or more elements share a name, or that it cannot tell which of several same-named elements is the target.
- Include: "there are several 'Add to Cart' buttons", "multiple 'Delete message' buttons; I need the one for the spam email".
- Exclude: choosing among options that differ in name (that is ordinary selection).
- Example: "Each post has 'Upvote'; I need the r/technology post's one." → present.
- Serves: PC1/PC2 ("shares its new name with another control"); E-N2. Clean pages also carry this form (§2, rule 1), so its clean rate is the baseline.

**N3 NOTICE_STRUCTURE.** The agent comments on page structure being absent or odd: no headings, no sections or regions, a table without header cells, a form field without a label, flat indentation.
- Include: "the field has no label but the text above says 'Date of birth'", "the first row looks like column titles", "there's no main section".
- Exclude: statements that use structure the page has ("under the heading 'Billing'"), which is ordinary use.
- Example: "The table rows have no column headers; row 1 seems to be 'Date, Amount, Status'." → present.
- Serves: manipulation check for labels, tableheads, headings and landmarks; mechanism of E-T1, E-L1, E-L2; PC3-PC6 (a structure note with no drop supports the equivalence reading).

**N4 A11Y_VOCABULARY.** The reasoning or text uses accessibility or markup vocabulary, or calls the page broken or badly built.
- Include: "aria-label", "accessible name", "screen reader", "alt text", "landmark", "WCAG", "the markup is broken", "the page seems poorly labeled".
- Exclude: the role words BrowserGym prints on every line (button, link, textbox, heading) used as plain identifiers.
- Example: "This button lacks an aria-label, so I'll infer it from context." → present.
- Serves: threat of evaluation awareness (the agent treats the page as a test of markup rather than a task; ours). Also answers Alex's question whether an agent can recognise a real defect when it meets one.

### S: how the agent compensated (action-based, reasoning optional)

**S1 VISIBLE_TEXT_ROUTE.** The agent picks an element by visible text that is not the element's own printed name: a neighbouring StaticText, a row's text, a card's title.
- Include: clicking `button ''` because the StaticText 'Star' sits inside or beside it; picking the 'Delete' button in the row whose StaticText is the target email subject.
- Exclude: clicking an element whose own name matches the task word (ordinary matching).
- Example: obs `[341] button ''` then `StaticText '☆ Save'` on the next line; action `click('341')`; reasoning "the save button is the one with ☆ Save" → present, step N.
- Serves: PREDICTIONS PC1/PC2 and E-N1 column "Where the information survives: visible text, sibling StaticText". If S1 is common and the names drop is small, the information survived. If S1 is common and the drop is large, the route exists but fails.

**S2 POSITION_ROUTE.** The agent picks an element by its place: order among same-named elements, nearness in bid number or line order, indentation, "the second one", "the button after the title".
- Include: "the third 'Upvote' corresponds to the third post", choosing a bid because it follows the target text.
- Exclude: an element unique by name that also happens to be near (code S1 or nothing).
- Example: "Upvote buttons appear in post order; r/technology is the 2nd post, so bid 255." → present.
- Serves: PC1/PC2 ("tree position"); E-F1 (indentation as a cue: if agents never use depth, the fmt_wrap control is expected null).

**S3 PROBE_ACTION.** The agent does an action to find out what an unclear element is: hovers it, clicks it and checks the result, then backs out.
- Include: reasoning "let me click it to see what it does"; a click followed by `go_back`/close on the next step, with reasoning about testing.
- Exclude: a wrong click the agent did not intend as a test (that is E1).
- Example: step 6 `hover('88')` "to see the tooltip", step 7 click → present, steps 6-7.
- Serves: cost mechanism of names (steps spent); secondary outcome "steps to success" (DESIGN §4.6).

**S4 SEARCH_OR_URL_DETOUR.** The agent leaves the visible route and uses the site's search box, a filter, or tries to go to a URL directly.
- Include: typing the target into 'Search Reddit' when a link to it exists in another region; calling `goto(...)`, which the H1 action set does not include (it returns an action error, so also code E3).
- Exclude: tasks whose goal requires search ("search for X and star it").
- Example: smoke clean run, step 4: `fill("19", "QuantumPanda")` into the search box ('Search Reddit') of a task that says "Go to Messages" (`/tmp/amt-syn/bw-smoke/out/reddit_compose_message__clean/episode.json`) → present.
- Serves: route analysis of every kind (a lost name or heading may push the agent to search); threat that failures come from viewport-only exploration, not the defect (smoke record §4.6).

**S5 SCROLL_HUNT.** Three or more consecutive scroll or hover actions with no other action between, while the agent is looking for something.
- Include: `scroll`, `scroll`, `scroll` reading "still don't see Messages"; alternating hover and scroll.
- Exclude: scrolling to read content the task asks about (reading a long article), when reasoning says so.
- Example: smoke labels run, steps 6-9: `scroll(0, 400)`, `hover("22")`, `scroll(0, 1000)`, `scroll(0, -2000)` → present.
- Serves: budget threat P6 (the step cap was derived with an orientation allowance of 10 steps, `h1_budget.py`); landmarks and headings mechanism (a page without regions may cost more search). Also computed mechanically (§5).

### E: errors (action-based)

**E1 WRONG_ELEMENT.** The agent acts on an element that is not the one the task needs at that point, and the next observation or the goal shows it.
- Include: opens the wrong post, stars the wrong email, clicks 'Delete' on the wrong row, opens a menu other than the one it meant (reasoning names one target, the result shows another).
- Exclude: exploratory clicks the reasoning frames as tests (S3); clicks that are on route but early.
- Example: reasoning "star the Q4 Budget email", action `click('412')`, next observation shows 'Project Update' starred → present.
- Serves: DESIGN §4.6 secondary outcome (wrong-target clicks among same-name elements, also scored mechanically on strict names tasks); Yin2026 action failure; PC1/PC2 mechanism.

**E2 PHANTOM_ELEMENT.** The action uses a bid that is not in that step's observation, or the reasoning describes an element or name that the observation does not contain and acts on that belief.
- Include: `click('523')` when no line has `[523]`; "I'll click the 'Compose' button" when no such name is printed, then a click on some other bid.
- Exclude: bids from an earlier observation that are still on the page (BrowserGym keeps bids stable); BrowserGym errors from elements that became hidden after the observation.
- Example: step 9 reasoning "click Send", obs has no 'Send' line, action `click('713')` where 713 is 'Save draft' → present.
- Serves: threat that failures come from model error unrelated to the defect; a names or labels cell could raise it (the agent guesses a name). The bid part is computed mechanically (§5).

**E3 ACTION_ERROR.** An action returned an error (`action_error` non-empty). Record a sub-value: `recovered` (a later step succeeds at the same intent), `repeated` (the same failing action again at least once), `abandoned` (the intent is dropped).
- Include: every non-empty action error.
- Exclude: none; this code is near-mechanical, the observer adds the sub-value.
- Example: `fill('19', ...)` error "element is not an input" then `click('19')` then fill works → present, recovered.
- Serves: Yin2026 action-failure class; DESIGN M10 (a bid lost by a variant shows as an error the agent must route around).

**E4 LOOP.** The same action, or the same cycle of two or three actions, is repeated three or more times with no change in the observation that matters to the goal; or the agent returns to the same URL three or more times without new progress.
- Include: `click('72')` five times; open, back, open, back, open.
- Exclude: required repetition (deleting three messages one by one); S5 (scrolling to find something, coded there).
- Example: steps 11-22 of a run all `noop()` → present.
- Serves: budget threat; failure-route accounting (a loop is a failure the defect may or may not cause; compare its rate across cells).

**E5 FORM_VALUE_ERROR.** A value goes into the wrong field, or a wrong or partly wrong value goes into the right field.
- Include: the subject typed into the recipient box; a date typed into 'Last name'; a body with words changed from the task's exact text.
- Exclude: correct text in the correct field that the app rejects (code E3 if an error shows).
- Example: obs `[1565] textbox ''`, `[1566] textbox ''`; action `fill('1565', 'Question about your AskReddit post')` where 1565 is the recipient field → present.
- Serves: E-L1, E-L2 (labels: controls become `textbox ''`, the agent must place values by position or visible label text); Yin2026 action failure.

**E6 STRUCTURE_MISREAD.** The agent attributes a value, element or region to the wrong part of the page: the wrong row or column of a table, a header row read as data, a control assigned to the wrong section or card.
- Include: reading the 'Amount' column value as 'Status'; "the first row (Date, Amount) is the most recent transaction"; acting on a card's button believing it belongs to the next card.
- Exclude: E1 cases where the agent never formed a belief about structure (just a wrong click).
- Example: reasoning "the latest lab result is 'Result' (row 1)" where row 1 is the header row → present.
- Serves: E-T1 (tableheads: "the header row reads as the first data row"); PC3-PC6 (headings and landmarks: a misread that does not lead to failure supports equivalence; a failing misread argues against it); E-H1.

### F: how the run ended

**F1 PREMATURE_SUCCESS** (pass B). The agent declares completion (`send_msg_to_user` with a claim of success, or a final message saying the task is done) while the evaluator shows at least one required check failed.
- Include: "Done, message sent" when the check 'Compose a new message ...' failed.
- Exclude: a declaration that is correct but has a failed *negative* check (that is F3); a run that ended at the cap without a claim.
- Example: action `send_msg_to_user('The email has been starred.')`; evaluator check 'Starred Q4 Budget Summary' failed → present.
- Serves: Yin2026 belief failure (75% of text-agent failures there); PC1/PC2 (a names cell may raise false success when the agent acts on a guessed control and believes it worked).

**F2 GAVE_UP.** The agent calls `report_infeasible`, or says it cannot complete the task and then stops trying (only noop, or the same no-progress action, until the end).
- Include: `report_infeasible('Cannot find the compose button')`; "I could not find X" followed by noop to the cap.
- Exclude: a run that keeps trying different things until the cap (F4 or nothing).
- Example: `report_infeasible('The form has no labeled fields')` → present.
- Serves: the predictions' failure routes (a removed carrier may lead to giving up instead of guessing); threat of refusals (M7).

**F3 OVERREACH** (pass B). The agent changes state the task did not ask for: a negative check failed, or the actions show extra changes (deleted another message, edited another field).
- Include: every failed negative check; visible extra changes the evaluator does not check (note them).
- Exclude: navigation and opening views, which change no state.
- Example: negative check 'Agent did not reply to any existing messages' failed → present.
- Serves: Yin2026 overreach (18% of text-agent failures); E1 consequence analysis.

**F4 BUDGET_ON_ROUTE.** The run ended by the step cap or wall cap while the agent's last steps were making progress toward the goal: it had reached the right page or form, or was filling the required fields.
- Include: cap reached with two of three required fields filled.
- Exclude: cap reached in a loop (E4) or a scroll hunt with no progress (S5 only).
- Example: smoke clean run: cap 15 reached during the fill of the subject on the compose form (pipeline smoke record §4.6) → present.
- Serves: P6, the step budget (`h1_budget.py`): F4 on more than 5% of clean runs means the budget is too low; DESIGN §4.5 "2x step cap sensitivity arm" decision.

### H: harness artefacts (need text or reasoning)

**H1 TRUNCATION_OR_SUMMARY_CONFUSION.** The agent's behaviour changes right after a history summary or a truncated observation, and the reasoning shows that it lost track (repeats finished work, refers to the summary text as the page).
- Include: re-filling a field that the summary says is done; "the observation says '[... content truncated ...]', I can't see the rest".
- Exclude: steps after a summary with no sign of confusion.
- Example: step 12 marker `[Summary of steps 1-5]`, step 12 action repeats step 3's fill → present.
- Serves: DESIGN §4.5 length covariate; the smoke finding that before the fix the trim fell back to the regex summary (pipeline smoke record §4.1).

**H2 FORMAT_FAILURE.** The model's text is not one valid action: several calls, prose only, a malformed call; the harness's extraction picked something.
- Include: `model_text` with two function calls; `model_text` with no call (the clone then sends the cleaned text, usually an error).
- Exclude: a valid call with prose before it (the clone extracts it as designed).
- Example: model text "I'll click 12 then fill 13: click('12') fill('13','x')" → present.
- Serves: M7 call integrity; threat that a cell changes output format (ours).

**H3 REFUSAL.** The model refuses or stops for a safety or policy reason (stop reason `refusal` or `content_filtered`, or text saying it will not do the task).
- Include: any such stop reason or statement.
- Exclude: report_infeasible for a practical reason (F2).
- Example: stop_reason `content_filtered` at step 3 → present.
- Serves: M7 (refusals are agent behaviour, counted as failures, reported per cell).

### J: final state and evaluator audit (pass B)

**J1 EVALUATOR_DOUBT.** The observer judges, from the trajectory, that the evaluator's verdict may be wrong: the final observation shows the task done but a check failed, or the reverse.
- Include: the final page shows the message in Sent with the exact subject and body while the check failed; the check passed though the agent never reached the form.
- Exclude: disagreements about the task's intent; F1 (the agent is wrong, the evaluator right).
- Example: final observation `StaticText 'Message sent to u/QuantumPanda'`, check failed 'no candidate satisfied predicates' → present, with the quote.
- Serves: DESIGN §9 evaluator audit (blinded hand audit of about 120 runs); J1 traces go first into that audit. Grounds: [Dong2026](../../../ai-accessibility-paper/literature/papers/L_Dong2026.md) (15.3% of audited FAIL verdicts wrong), [Zhu2025](../../../ai-accessibility-paper/literature/papers/L_Zhu2025.md).

**J2 FINAL_STATE** (categorical, always coded in pass B). One of: `complete` (every required check passed), `partial` (some required checks passed, or the trajectory shows part of the work done), `wrong_target` (the work was done on the wrong object: wrong email, wrong post), `none` (no required change made), `unclear`.
- Grounds: the evaluator's checks list, read with the last observations. `wrong_target` is the case the verdict alone cannot separate from `none`.
- Serves: names mechanism (wrong target under ambiguity); E1 consequence; analysis of partial credit (ANALYSIS.md does not use partial credit; this is descriptive).

### Summary table

| Code | Pass | Needs reasoning | Mechanical check (§5) | Serves |
|---|---|---|---|---|
| N1 NOTICE_UNNAMED | A | yes | | PC1-PC2, E-N1, E-N3 (manipulation check) |
| N2 NOTICE_AMBIGUOUS | A | yes | | PC1-PC2, E-N2 |
| N3 NOTICE_STRUCTURE | A | yes | | E-L1, E-L2, E-T1, PC3-PC6 |
| N4 A11Y_VOCABULARY | A | yes | keyword count | evaluation awareness |
| S1 VISIBLE_TEXT_ROUTE | A | no | | PC1-PC2 survival route |
| S2 POSITION_ROUTE | A | no | | PC1-PC2, E-F1 |
| S3 PROBE_ACTION | A | partly | | steps to success |
| S4 SEARCH_OR_URL_DETOUR | A | no | search-box fills | route analysis, viewport threat |
| S5 SCROLL_HUNT | A | no | yes | budget P6, landmarks/headings |
| E1 WRONG_ELEMENT | A | no | same-name wrong target (strict names) | DESIGN §4.6, Yin2026 action |
| E2 PHANTOM_ELEMENT | A | partly | bid not in observation | model-error threat |
| E3 ACTION_ERROR | A | no | yes (presence) | M10, Yin2026 action |
| E4 LOOP | A | no | yes | budget, failure routes |
| E5 FORM_VALUE_ERROR | A | no | | E-L1, E-L2 |
| E6 STRUCTURE_MISREAD | A | yes | | E-T1, PC3-PC6, E-H1 |
| F1 PREMATURE_SUCCESS | B | no | | Yin2026 belief |
| F2 GAVE_UP | A | no | report_infeasible | failure routes, M7 |
| F3 OVERREACH | B | no | failed negative checks | Yin2026 overreach |
| F4 BUDGET_ON_ROUTE | A | no | cap + goal page reached | P6 step budget |
| H1 TRUNCATION_OR_SUMMARY_CONFUSION | A | yes | marker step | §4.5 length covariate |
| H2 FORMAT_FAILURE | A | no | yes | M7 |
| H3 REFUSAL | A | no | stop reason | M7 |
| J1 EVALUATOR_DOUBT | B | no | | §9 evaluator audit |
| J2 FINAL_STATE | B | no | checks list | names mechanism, description |

## 5. Mechanical measures computed beside the codes

These come from the trace by script, with no observer. They are the reference for the observer's E2, E3, E4, S5 and H2 codes and are reported on their own.

| Measure | Rule | Grounds |
|---|---|---|
| Bid not in observation | The action's bid has no `[bid]` line in that step's `observation_text` | BrowserGym bids are stable; an absent bid is a guess or a stale reference (ours) |
| Repeated action | Same `action` string 3+ times in a row, or a 2-3 step cycle 3+ times | E4 definition |
| Scroll hunt | 3+ consecutive scroll/hover actions | S5 definition |
| First step on the goal page | First step whose URL path equals the URL path of the reference replay's last state | Pipeline smoke record §4.6 asked for it per task |
| Same-name wrong target | On strict names tasks, a click on an element that shares the target's variant name but is not the reference target | DESIGN §4.6 |
| Format failure | `model_text` holds 0 or 2+ action calls | `_extract_action` behaviour |
| Accessibility words | Count of N4 keywords in reasoning and model text | N4 |

## 6. Agreement

**Design.** Every trace gets observer O1. A stratified 20% sample also gets observer O2, coding blind to O1's output: strata are cell x outcome (success or failure), with at least 4 traces per stratum and at least 120 traces in all. Packets with at least one O1 `present` on a code rarer than 5% are over-sampled so that each code has at least 10 positive cases in the sample. Grounds: [Zhang2026](../../../ai-accessibility-paper/literature/papers/L_Zhang2026.md) over-sampled the rare class in its 100-sample agreement check (kappa 0.722); the minimum of 10 positives is ours. Kappa on a code with almost no positives is unstable.

**Who the observers are.** O1 and O2 are fresh workflow agents, one per packet, with the prompt in `trace_observer_prompt.md`. O2 uses a different model from O1, so agreement is not two runs of the same model's habits (ours). Alex codes 30 traces from the agreement sample as the human reference.

**Statistics, per code.** Cohen's kappa between O1 and O2 with a bootstrap 95% interval over traces; raw agreement; prevalence; and Gwet's AC1 when prevalence is below 10% (kappa falls at low prevalence even with high raw agreement [unverified]: the kappa paradox is not in the library). For J2 (categorical), unweighted kappa. For step lists, the share of O1 steps that O2 also lists (step-level agreement), reported but not gated.

**Thresholds (ours).** No close-read sets one. The two close-reads that report agreement got kappa 0.8 ([Wang2025](../../../ai-accessibility-paper/literature/papers/L_Wang2025.md)) and 0.722 ([Zhang2026](../../../ai-accessibility-paper/literature/papers/L_Zhang2026.md)).
- Kappa of at least 0.70 and agreement with Alex's 30 traces of at least 0.60: the code is used in results.
- 0.60 to 0.70: the code is reported as exploratory, with its kappa beside every number.
- Below 0.60: the code is not used. Its definition is revised, and it is recoded on a fresh sample before any later use (numbered revision).
- Disagreements in the sample are settled by a third observer reading both codings, for the record. The kappa is computed before that and is the one reported.

**How it could be wrong.** Two LLM observers can agree on the same mistake, so high kappa does not prove they are right. Alex's 30 traces are the check on that. They are too few to tell 0.6 from 0.8 reliably: at n = 30 the kappa interval is about ±0.2 (ours, binomial approximation). LLM judges also vary from run to run ([Vaghasiya2026](../../../ai-accessibility-paper/literature/papers/L_Vaghasiya2026.md)). So O1 is run twice on 30 packets as a test-retest check. A code whose O1-O1 kappa is below 0.70 is treated like a code below threshold.

**What would change a decision.** If N1-N3 fall below 0.60, the manipulation-check reading moves entirely to the mechanical measures and the variant gate. If E1 or E5 fall below threshold, the names and labels mechanism analysis uses only the mechanical same-name wrong-target measure. If J1 flags more than 10% of failed runs in any cell, that cell's evaluator audit is extended to all its runs (DESIGN §9 rule).

## 7. When coding happens, and versions

- The codebook is frozen with a sha256 before the first pilot trace is coded. Stage 0s smoke traces (32 runs, not analysed) are used to try it. The changes made after that trial are listed with the frozen version.
- Each coding records `codebook_sha256`, the observer model and the prompt sha256 (output schema in `trace_observer_prompt.md`).
- Codes are read only after Stage 2 ends, with the outcome analysis (DESIGN §7: no variant result is looked at before Stage 3). An observer pass can run during Stage 2 for infrastructure checks (H2, H3, call integrity), but only pooled counts are looked at, as for the M7/M8 stopping rules.
- Cost, estimated (ours): a mean H1 packet holds about 16 steps of 2,000-2,500 tokens of observation, about 40,000 input tokens, and a coding is about 2,000 output tokens. One pass over all 4,020 H1 traces at Sonnet 5.5 list price ($2 / $10 per million) is about $400. Pass B reads the same packet, so both passes cost about $800; the 20% second observer adds about $160 and the 30-packet retest under $10. The Bedrock price is [unverified].

## 8. Decisions for Alex

1. Code every H1 trace (about $950 at list price for both passes and the second observer) or a stratified sample. The agreement design in §6 works for either.
2. Which models are O1 and O2. Proposed: two different Claude models through the workflow, for example Sonnet 5.5 as O1 and Opus 5.5 as O2. Risk: Claude observers coding Claude agents may share habits (ours). GPT-5.6 as O2 would avoid that but needs a Bedrock observer harness.
3. Whether you code the 30 human-reference traces yourself or name someone.
