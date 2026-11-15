# Hubris provider setup

The bot can use Hubris as a separate OpenAI-compatible chat-completions provider. The existing `groq` and `openrouter` providers remain available. Select a provider with `LLM_PROVIDER` in the repository's local `.env`.

For Hubris, set:

```dotenv
LLM_PROVIDER=hubris
HUBRIS_API_KEY=
HUBRIS_BASE_URL=https://api.hubris.pw/v1
HUBRIS_MODEL=openai/gpt-oss-20b
HUBRIS_REASONING_EFFORT=low
```

Put the key directly into the local `.env`; do not commit it or send it in chat. The client posts to `{HUBRIS_BASE_URL}/chat/completions` with Bearer authorization. Requests use the OpenAI-compatible message format, bounded `max_completion_tokens`, and the configured reasoning effort. The Planner's structured JSON schema is sent to Hubris as `response_format: json_schema`.

Hubris does not use the Groq-specific quota limiter or its automatic retry. The client preserves the actual response model, token usage, reasoning token detail when present, and Hubris `usage.cost` as integer kopecks (`Generation.cost_kopecks`). Missing optional provider fields remain `None`. Provider error bodies are not surfaced because they can contain prompt text or other sensitive data; bounded status/type/code diagnostics are retained.

Configuration and mock-client tests are offline. Do not treat them as proof of authenticated service availability; a live request is a separate, explicitly controlled step.

## First live smoke check (2026-11-15)

One explicitly authorized request was sent with a 256-token completion budget. Hubris returned HTTP 200 and model `openai/gpt-oss-20b`. The response text was non-empty, but printing it to a Windows CP1251 console raised `UnicodeEncodeError` on U+202F before the answer and usage details could be recorded. No second request was made; token counts, reasoning usage, cost and duration are therefore unavailable from this run.

References: [Hubris quickstart](https://hubris.pw/docs/quickstart), [Chat Completions API](https://hubris.pw/docs/api/chat-completions).

## Experiment 2 compatibility checkpoint (2026-11-15)

The capture issue was reproduced offline with a strict CP1251 stream containing U+202F and fixed in the bounded LIVE harness: report JSON is UTF-8 and terminal progress is ASCII-safe. Source-first Understanding now uses Hubris with the existing strict JSON Schema; both Understanding and Planner returned HTTP 200 with structured output in the full-pipeline D07 smoke. One run produced the exact approved section and first safe diagnostic step, while a repeat returned an incomplete section ID and was correctly refused. See the [Experiment 2 Hubris checkpoint](../reports/exp2_natural_dialogue_20261115/hubris_checkpoint.md) for exact answers, usage, costs, limitations and next steps. This is not Part A acceptance.
