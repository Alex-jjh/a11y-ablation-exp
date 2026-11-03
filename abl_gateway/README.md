# abl_gateway: the only code that calls AWS

> **Summary:** A client object with a `converse()` method that both harnesses receive in place of their boto3 client. It enforces the model rule by allowlist, sends Bedrock native tool definitions for every model (D-013), returns every reasoning block or an explicit `none`, and never logs credentials. Empty skeleton: the client code is still inside `scripts/probe/breakingweb/h1_wrapper.py`.

## Single job

Turn the AWS profile `codex-DO-NOT-DELETE` into model calls under the model rule. One reason to change: a model, region or parameter.

## Contract

| Item | Rule |
|---|---|
| Allowlist | exactly `us.anthropic.claude-sonnet-5-5` (us-west-2, pilot primary), `us.openai.gpt-5.6-sol` (us-east-2, pilot second family); held out for the main study: `us.anthropic.claude-opus-5-5`, `us.anthropic.claude-sonnet-5`, `us.openai.gpt-5.6-terra`, `us.openai.gpt-5.6-luna` (D-011, D-012). Any other id is refused before a request is built |
| Actions | Converse `toolConfig` with the harness's action tools; the action is read from `toolUse` blocks, never parsed from text (D-013; grounds: Sonnet 5.5 wrote tool-call XML on 51% of smoke steps, `docs/feasibility/2026-11-02-wrapper-smoke.md`) |
| Reasoning | Claude: adaptive thinking, `display: "summarized"`, `output_config.effort`; GPT-5.6: `reasoning.effort`, `reasoning.summary: detailed` (READINESS D-3). No temperature on any call. maxTokens 16,384 (D-4) |
| Returned per call | text, tool uses, every reasoning block (text, summary or redacted marker) or `reasoning_visibility: none`, `stopReason`, usage, parameters sent, request sha256, latency, attempts — the `response` object of [`schemas/step.schema.json`](../schemas/step.schema.json) |
| Errors | throttled, transient, credential, invalid, access_denied, model_unavailable, timeout. `credential` stops all LLM work (Midway expired); it is never retried silently |
| Logging | never credentials, never request bodies with secrets; content is written only by `abl_traces` |
| Fake | a scripted fake with the same interface, for tests (as `h1_selftest.py` does today) |

Why not Echo's HTTP gateway: it handles text only and has no tool use, and its allowlist contains providers the v2 model rule forbids (platform-split proposal §3). An HTTP front can be added behind this interface if a run must be shared across machines.

## Depends on / must not know about

- Depends on: boto3, the profile `codex-DO-NOT-DELETE`.
- Must not know about: harnesses, cells, traces, Hugging Face.
