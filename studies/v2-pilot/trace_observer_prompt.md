# v2 pilot: trace observer prompt and output schema

> **Summary:** The exact text given to one observer agent per trace, in two passes: pass A codes behaviour without the evaluator verdict, and pass B codes the end-of-run codes with it. The observer reads one packet file, writes one JSON object that matches the schema below, and reads nothing else. Code definitions are those of [`TRACE-CODING.md`](TRACE-CODING.md) §4, restated in neutral words. The prompt does not say that pages were altered, and it does not name the conditions. The observer's guess about the page comes last. A checker validates the JSON against the schema and every quote against the packet.

How it is used:
- Packet: `h1_wrapper.py packet TRACE_DIR OUT.json --key-file KEY.jsonl` for pass A, with `--with-outcome` for pass B. The key file stays with the operator and is never given to an observer.
- Placeholders: `{PACKET_PATH}`, `{OUT_PATH}` and `{CODEBOOK_SHA}` (sha256 of `TRACE-CODING.md`, first 16 hex) are filled per packet. Nothing else in the text changes.
- One fresh agent per packet and pass, with no memory of other packets. The agent may use only a file reader on `{PACKET_PATH}` and a file writer on `{OUT_PATH}`.
- After the agent finishes, a checker validates `{OUT_PATH}` against the schema (§3), checks that every `quote` is an exact substring of the named field at the named step, and re-requests once on failure (TRACE-CODING §3).

## 1. Pass A prompt (exact text)

```text
You are a careful observer in a study of how LLM web agents act on structured page text. You will read ONE
record of a web agent doing ONE task and code what the agent did. You are not grading the agent and you
are not told whether it succeeded.

Read the file {PACKET_PATH}. It is JSON with: the task goal; and for each step the page URL, the exact text
the agent was shown (`observation_text`: an accessibility-tree listing, one element per line as
`[id] role 'name'`, children indented), any summary of earlier steps (`summary_marker_text`), a summary of
the agent's reasoning when one was returned (`reasoning_text`; it is a summary written by the model
provider, not the full chain of thought, and it may be empty), the agent's raw reply (`model_text`), the
action it took (`action`), and any error the browser returned (`action_error`). It also gives how the run
ended (`end_reason`) and the step limit. Read only this file. Do not open, search or list any other file
or folder, and do not use the web.

Code every code below once for the whole record:
- "present" with the step numbers where it occurs and at least one piece of evidence;
- "absent";
- "na" with a reason, when the record cannot show it.
Evidence is a verbatim quote copied exactly from one field of one step (field is one of observation_text,
reasoning_text, model_text, action, action_error, summary_marker_text). Quotes are checked by a program;
a quote that is not an exact substring is rejected. Keep quotes short (under 200 characters).

Rules:
1. Judge each code against what the agent was shown at that step, not against what you think the page
   should contain.
2. Reasoning summaries leave things out. For codes marked [R], you may code "present" from reasoning_text
   or model_text, but do not code "absent" only because the reasoning is silent: code "absent" only when
   reasoning_text is present on most steps and nothing in it, the model text or the actions shows the code.
   If fewer than half of the steps have reasoning_text, code [R] codes "na" with reason "little reasoning
   text", unless the model text or actions show them.
3. One step may carry several codes. Use the narrowest code that fits; the definitions say which code to
   prefer.
4. Do not guess at anything not in the record.

Codes:
N1 [R] UNCLEAR_NAME. The reasoning or reply refers to a target or candidate element whose printed name is
   empty (''), a symbol, or does not say what it does. Not: missing page content (empty list, no results).
N2 [R] SAME_NAME. The agent says two or more elements share a name, or that it cannot tell which of several
   same-named elements is the one it needs. Not: choosing among differently named options.
N3 [R] STRUCTURE_REMARK. The agent remarks that page structure is absent or odd: no headings or sections, a
   table without header cells, a field without a label, flat indentation. Not: ordinary use of structure the
   page has ("under the heading Billing").
N4 [R] MARKUP_TALK. The reasoning or reply talks about the page's markup or labelling quality, e.g. words
   like aria-label, accessible name, alt text, landmark, screen reader, WCAG, "poorly labeled", "broken
   markup". Not: the role words printed on every line (button, link, textbox, heading) used as identifiers.
S1 VISIBLE_TEXT_ROUTE. The agent picks an element by visible text that is not that element's own printed
   name: a nearby StaticText line, the text of its row or card. Not: an element whose own name matches.
S2 POSITION_ROUTE. The agent picks an element by its place: order among same-named elements, nearness in id
   or line order, indentation ("the second one", "the button after the title"). Not: an element unique by
   name that is also nearby.
S3 PROBE. The agent acts on an unclear element to find out what it is (hover, or click and then undo or go
   back), and says so or plainly does so. Not: an unintended wrong click (E1).
S4 DETOUR. The agent leaves the visible route: uses the site's search or a filter, or tries to go to a URL
   directly, when the task does not require search. Not: tasks that ask for a search.
S5 SCROLL_HUNT. Three or more consecutive scroll or hover actions with no other action between, while
   looking for something. Not: scrolling to read content the task asks about, when the reasoning says so.
E1 WRONG_ELEMENT. The agent acts on an element that is not the one the task needs at that point, and the
   next observation or the goal shows it (wrong post, wrong email, wrong row). Not: S3 probes; on-route
   clicks.
E2 PHANTOM_ELEMENT. The action uses an id that is not in that step's observation_text, or the reasoning
   relies on an element or name that observation_text does not contain. Not: ids from an earlier step
   that are still shown.
E3 ACTION_ERROR. action_error is non-empty at some step. Give sub_value: "recovered" (a later step achieves
   the same intent), "repeated" (the same failing action again), or "abandoned" (intent dropped).
E4 LOOP. The same action, or the same cycle of two or three actions, three or more times with no change
   that matters to the goal; or the same URL revisited three or more times without new progress. Not:
   repetition the task requires (deleting three items); scroll hunts (S5).
E5 FORM_VALUE_ERROR. A value goes into the wrong field, or a wrong or altered value into the right field
   (compare with the exact text in the goal).
E6 STRUCTURE_MISREAD. The agent assigns a value, element or region to the wrong part of the page: wrong row
   or column, a header row read as data, a button taken to belong to the wrong card or section.
F2 GAVE_UP. The agent calls report_infeasible, or says it cannot complete the task and then stops trying
   (only waits or repeats a no-progress action to the end).
F4 STOPPED_ON_ROUTE. end_reason is step_cap or wall_cap and the last steps were making progress toward the
   goal (on the right page or form, filling the required fields). Not: ended in a loop or a scroll hunt
   with no progress.
H1 [R] LOST_TRACK_AFTER_SUMMARY. Right after a summary_marker_text appears, or after an observation
   contains "[... content truncated ...]", the agent shows it lost track: repeats finished work or treats
   the summary as the page.
H2 FORMAT_FAILURE. model_text is not one valid action call: two or more calls, prose with no call, or a
   malformed call. Not: a valid call with prose before it.
H3 REFUSAL. The model refuses or stops for a safety or policy reason (stop_reason "refusal" or
   "content_filtered", or a statement that it will not do the task).

Then write a narrative of at most 80 words: what the agent tried, where it went off course if it did, and
how the run ended. Plain sentences, no speculation about why the page looks as it does.

Last, after all codes and the narrative: condition_guess. Was anything about the pages in this record
unusual for a website? Answer "yes", "no" or "unsure", say what in at most 30 words, and give a
confidence from 0 to 1. This question is asked of every record; there is no right answer you should aim
for.

Write exactly one JSON object to {OUT_PATH}, matching the schema you are given below, with
"pass": "A" and "codebook": "{CODEBOOK_SHA}". Codes not listed above must not appear. Then reply "done".

SCHEMA:
{SCHEMA_A}
```

## 2. Pass B prompt (exact text)

Pass B is a separate fresh agent. It reads the pass-B packet (the same steps plus `evaluator`: success, score, the required checks and negative checks with pass or fail, and the final URL). It does not see the pass-A coding.

```text
You are a careful observer in a study of how LLM web agents act on structured page text. You will read ONE
record of a web agent doing ONE task, including the verdict of the website's automatic checker, and code
how the run ended.

Read the file {PACKET_PATH}. It is JSON with the task goal; for each step the page URL, the exact text the
agent was shown (observation_text), any summary of earlier steps (summary_marker_text), a summary of the
agent's reasoning when one was returned (reasoning_text), the agent's raw reply (model_text), its action
and any action_error; how the run ended (end_reason); and `evaluator`: whether the checker counted the task
as done (success, score), each required check and each negative check (things the agent must not do) with
passed true or false, and the final URL. Read only this file. Do not open, search or list any other file
or folder, and do not use the web.

Code each code below once for the whole record, as "present" (with step numbers and evidence), "absent", or
"na" (with a reason). Evidence is a verbatim quote copied exactly from one field of one step (field is one of
observation_text, reasoning_text, model_text, action, action_error, summary_marker_text), or the exact
"desc" text of one evaluator check with field "evaluator". Quotes are checked by a program. Keep them under
200 characters.

F1 CLAIMED_DONE_BUT_NOT. The agent declares the task done (send_msg_to_user with a claim of completion, or
   a final message saying it is done) while at least one required check failed. Not: a correct claim with
   only a negative check failed (that is F3); a run that ended without a claim.
F3 OVERREACH. The agent changed something the task did not ask for: a negative check failed, or the
   actions show an extra change (another item deleted, another field edited). Not: navigating or opening
   views.
J1 CHECKER_DOUBT. From the record, the checker's verdict may be wrong: the last observations show the task
   done but a required check failed, or a check passed though the actions never did the required work.
   Not: disagreement about what the task means; F1 cases where the agent is wrong and the checker right.
J2 FINAL_STATE. Exactly one value: "complete" (every required check passed), "partial" (some required
   checks passed, or the record shows part of the work done), "wrong_target" (the work was done on the wrong
   object, e.g. the wrong email or post), "none" (no required change made), "unclear". Give evidence.

Write exactly one JSON object to {OUT_PATH}, matching the schema you are given below, with
"pass": "B" and "codebook": "{CODEBOOK_SHA}". Then reply "done".

SCHEMA:
{SCHEMA_B}
```

## 3. Output schemas

`{SCHEMA_A}` and `{SCHEMA_B}` are replaced by the schemas of §3.2 and §3.3 (JSON Schema draft 2020-12), each with its `"$defs"` string replaced by the `$defs` object of §3.1. The operator script assembles them once and pastes the result verbatim.

### 3.1 Shared definitions

```json
{
  "$defs": {
    "evidence": {
      "type": "object",
      "additionalProperties": false,
      "required": ["step", "field", "quote"],
      "properties": {
        "step": {"type": ["integer", "null"], "minimum": 1, "description": "null only for field evaluator"},
        "field": {"enum": ["observation_text", "reasoning_text", "model_text", "action", "action_error",
                           "summary_marker_text", "evaluator"]},
        "quote": {"type": "string", "minLength": 1, "maxLength": 200}
      }
    },
    "code": {
      "type": "object",
      "additionalProperties": false,
      "required": ["value", "steps", "evidence", "na_reason", "note"],
      "properties": {
        "value": {"enum": ["present", "absent", "na"]},
        "steps": {"type": "array", "items": {"type": "integer", "minimum": 1}, "uniqueItems": true},
        "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}, "maxItems": 6},
        "na_reason": {"type": ["string", "null"], "maxLength": 120},
        "note": {"type": ["string", "null"], "maxLength": 240}
      },
      "allOf": [
        {"if": {"properties": {"value": {"const": "present"}}},
         "then": {"properties": {"steps": {"minItems": 1}, "evidence": {"minItems": 1}}}},
        {"if": {"properties": {"value": {"const": "na"}}},
         "then": {"properties": {"na_reason": {"type": "string", "minLength": 3}}}}
      ]
    },
    "e3": {
      "type": "object",
      "additionalProperties": false,
      "required": ["value", "steps", "evidence", "na_reason", "note", "sub_value"],
      "properties": {
        "value": {"enum": ["present", "absent", "na"]},
        "steps": {"type": "array", "items": {"type": "integer", "minimum": 1}, "uniqueItems": true},
        "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}, "maxItems": 6},
        "na_reason": {"type": ["string", "null"], "maxLength": 120},
        "note": {"type": ["string", "null"], "maxLength": 240},
        "sub_value": {"enum": ["recovered", "repeated", "abandoned", null]}
      },
      "allOf": [
        {"if": {"properties": {"value": {"const": "present"}}},
         "then": {"properties": {"steps": {"minItems": 1}, "evidence": {"minItems": 1},
                                 "sub_value": {"enum": ["recovered", "repeated", "abandoned"]}}}},
        {"if": {"properties": {"value": {"const": "na"}}},
         "then": {"properties": {"na_reason": {"type": "string", "minLength": 3}}}}
      ]
    }
  }
}
```

`e3` is the code object plus `sub_value`, which must be set when E3 is present.

### 3.2 Pass A

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "amt-v2-trace-observer-A",
  "type": "object",
  "additionalProperties": false,
  "required": ["packet_id", "pass", "codebook", "reasoning_coverage", "codes", "narrative", "condition_guess"],
  "properties": {
    "packet_id": {"type": "string", "pattern": "^P[0-9a-f]{10}$"},
    "pass": {"const": "A"},
    "codebook": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
    "reasoning_coverage": {
      "type": "object", "additionalProperties": false, "required": ["steps_with_reasoning_text", "steps_total"],
      "properties": {"steps_with_reasoning_text": {"type": "integer", "minimum": 0},
                     "steps_total": {"type": "integer", "minimum": 0}}
    },
    "codes": {
      "type": "object",
      "additionalProperties": false,
      "required": ["N1", "N2", "N3", "N4", "S1", "S2", "S3", "S4", "S5", "E1", "E2", "E3", "E4", "E5", "E6",
                   "F2", "F4", "H1", "H2", "H3"],
      "properties": {
        "N1": {"$ref": "#/$defs/code"}, "N2": {"$ref": "#/$defs/code"}, "N3": {"$ref": "#/$defs/code"},
        "N4": {"$ref": "#/$defs/code"}, "S1": {"$ref": "#/$defs/code"}, "S2": {"$ref": "#/$defs/code"},
        "S3": {"$ref": "#/$defs/code"}, "S4": {"$ref": "#/$defs/code"}, "S5": {"$ref": "#/$defs/code"},
        "E1": {"$ref": "#/$defs/code"}, "E2": {"$ref": "#/$defs/code"}, "E3": {"$ref": "#/$defs/e3"},
        "E4": {"$ref": "#/$defs/code"}, "E5": {"$ref": "#/$defs/code"}, "E6": {"$ref": "#/$defs/code"},
        "F2": {"$ref": "#/$defs/code"}, "F4": {"$ref": "#/$defs/code"}, "H1": {"$ref": "#/$defs/code"},
        "H2": {"$ref": "#/$defs/code"}, "H3": {"$ref": "#/$defs/code"}
      }
    },
    "narrative": {"type": "string", "minLength": 1, "maxLength": 600},
    "condition_guess": {
      "type": "object", "additionalProperties": false, "required": ["page_unusual", "what", "confidence"],
      "properties": {"page_unusual": {"enum": ["yes", "no", "unsure"]},
                     "what": {"type": "string", "maxLength": 220},
                     "confidence": {"type": "number", "minimum": 0, "maximum": 1}}
    }
  },
  "$defs": "<the shared definitions of §3.1>"
}
```

### 3.3 Pass B

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "amt-v2-trace-observer-B",
  "type": "object",
  "additionalProperties": false,
  "required": ["packet_id", "pass", "codebook", "codes"],
  "properties": {
    "packet_id": {"type": "string", "pattern": "^P[0-9a-f]{10}$"},
    "pass": {"const": "B"},
    "codebook": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
    "codes": {
      "type": "object",
      "additionalProperties": false,
      "required": ["F1", "F3", "J1", "J2"],
      "properties": {
        "F1": {"$ref": "#/$defs/code"}, "F3": {"$ref": "#/$defs/code"}, "J1": {"$ref": "#/$defs/code"},
        "J2": {
          "type": "object", "additionalProperties": false, "required": ["value", "evidence", "note"],
          "properties": {
            "value": {"enum": ["complete", "partial", "wrong_target", "none", "unclear"]},
            "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}, "minItems": 1, "maxItems": 6},
            "note": {"type": ["string", "null"], "maxLength": 240}
          }
        }
      }
    }
  },
  "$defs": "<the shared definitions of §3.1>"
}
```

## 4. Why each choice

| Choice | Grounds | How it could be wrong | What would change it |
|---|---|---|---|
| Two passes, verdict in B only | Outcome knowledge colours process codes (ours); [Dong2026](../../../ai-accessibility-paper/literature/papers/L_Dong2026.md) labels verdict validity first, then cause | Pass A coders infer the outcome from the last steps anyway | If pass-A codes predict the outcome no better than chance after controlling for end_reason, the split is unneeded; if they predict it strongly, it is not hiding much either way |
| Neutral study framing; no mention that pages were altered | Blinding (TRACE-CODING §2) | The N-code definitions name page features, which points at the study's interest | If condition_guess accuracy is far above chance (TRACE-CODING §2 rule 3), report all N codes as unblinded and lean on the mechanical measures |
| Neutral code labels (UNCLEAR_NAME, not "removed aria-label") | Same | Same | Same |
| Verbatim quotes checked by program | The same rule the literature system uses; it catches made-up evidence (ours) | A true quote can still be cited for the wrong code | Agreement (TRACE-CODING §6) measures this |
| [R] codes never "absent" from silent reasoning | Reasoning is a provider-written summary (claude-api reference; probe 2026-11-02) | Observers may still treat silence as absence | O1-O2 disagreement concentrated in [R] codes would show it; then [R] codes become present-only |
| Guess question last | It must not prime the codes (ours) | The JSON field order may not equal the order of thought | Compare code rates of packets whose guess is right and wrong (TRACE-CODING §2) |
| One fresh agent per packet, file access limited to the packet | Prevents comparing a task's cells side by side | A workflow agent with wider tools could read other files | The workflow gives the observer only the packet path; any read outside it is logged and the coding discarded |
