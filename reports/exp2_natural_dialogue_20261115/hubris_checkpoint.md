# Experiment 2 — Hubris provider and capture checkpoint

Date: 2026-11-15. This is a provider compatibility checkpoint, not an Experiment 2 Part A decision.

## Provider preparation

- Current `main` and `origin/main` were both `c2a483177ec5a093ef14c67739c569dbbb642c0d` before these local changes; remote was checked with `git ls-remote`.
- Hubris was the configured provider (`openai/gpt-oss-20b`, reasoning `low`). The API key was checked for presence only; it was not printed or copied into this report.
- Stage3 Qdrant `knowledge_stage3_retrieval_20261022` was green with 934 points. The smoke wrapper only uses collection reads/queries and isolated SQLite.
- Hubris official API documentation lists `response_format: json_schema`, strict structured output and `usage.cost` in kopecks: [Chat Completions](https://hubris.pw/docs/api/chat-completions), [Structured output](https://hubris.pw/docs/features/structured-output). The model page lists `openai/gpt-oss-20b` and per-token pricing: [model page](https://hubris.pw/models/openai/gpt-oss-20b).
- `app.dialogue_understanding` now supports Hubris at the existing provider boundary, sending the existing strict JSON schema, using Hubris settings and not invoking Groq-only quota controls/retries. The source-first understanding completion budget is 1024 tokens for Hubris. Planner structured JSON continues through the shared client.
- The LIVE harness writes result JSON as UTF-8 atomically and emits ASCII-escaped JSON lines to stdout. The ASCII console record survives CP1251 even when the answer contains U+202F. The full Unicode answer remains in the UTF-8 result/SQLite.

## Offline evidence

- `.venv\Scripts\python.exe -m pytest tests/test_dialogue_understanding.py tests/test_llm_client_diagnostics.py tests/test_exp2_utf8_capture.py -q` — **92 passed**.
- `py_compile` for `app/dialogue_understanding.py` and `scripts/run_telegram_equivalent_live.py` passed; harness `--help` passed.
- The CP1251 regression writes a Russian answer containing U+202F through a strict CP1251 stream, reads it back and verifies the exact Unicode string.
- Mock tests verify Hubris Understanding's `json_schema` request, Planner's `json_schema` request, parsed token/cost metadata, and no use of Groq-only limiting.

## Bounded D07 full-pipeline smoke

Synthetic input: “Помоги, у меня Эвотор 7.3, продажи проходят, но периодически не уходят чеки.” The run used `bot.handle_message`, Hubris, read-only Stage3 and a new isolated SQLite database.

Two bounded executions exposed response variance:

| Attempt | Provider result | Retrieved/selected source | Final Telegram-equivalent answer | Evidence |
|---|---|---|---|---|
| 1 | Understanding and Planner completed HTTP 200. Saved SQLite diagnostics report 3,246 total tokens and 14.1 s; the aggregate capture was interrupted before its JSON report was saved, so per-call cost/usage is incomplete. | Approved `data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md`, section “Что проверить сначала”; exact-source-copy validation passed. | “Статья производителя относит Эвотор 7.3 к группе моделей с диагностикой через отчёт. Под ролью администратора откройте «Настройки → Обслуживание кассы → Диагностика» и напечатайте диагностический отчёт.” | `.local/telegram-equivalent-exp2_hubris_smoke_20261115/conversations.sqlite3` and `understanding.jsonl` (ignored/private). Understanding usage: 1,592 tokens, 1 kopeck, HTTP 200. Planner cost was not captured. |
| 2 | Understanding 200: 1,066 tokens / 1 kopeck / 4.5 s. Planner 200: 3,140 tokens / 2 kopecks / 8.96 s. Total reported cost **3 kopecks**; no provider errors. | The same approved source/section was retrieved. Planner returned the document ID without its required `::Что проверить сначала` section suffix; the deterministic ID membership check rejected the selection. | “По подтверждённым источникам не удалось выбрать безопасное решение. Запросите специалиста кнопкой ниже.” | `.local/exp2_hubris_smoke_d07_retry_20261115.json` and its isolated SQLite under `.local/` (ignored/private). |

The completed second artifact records the accepted request schemas, stage token/cost/latency, response, source candidates, validation status and SQLite before/after state. The first execution's SQLite confirms the exact approved section and answer survived, but its missing Planner usage prevents claiming a complete first-run bill. Both runs were within the 500-kopeck smoke ceiling; that ceiling was checked before any subsequent request after reported spend.

## Interpretation and next step

**Fact:** Hubris strict structured JSON works for both Understanding and Planner in the real full-pipeline smoke. The Planner can still choose an incomplete section ID despite a valid schema; the existing membership check safely refuses it. The identical D07 turn yielded one useful safe step and one refusal. This is an observed answer-quality variance, not proof of an API schema incompatibility. No retrieval, approved KB, Qdrant, production worker, or Part B behavior was modified.

Next: create the fixed baseline from the checkpoint SHA using `git archive` and a minimal provider-only Hubris adapter; verify that adapter diff excludes Experiment 2 changes. Then run equal-configuration, separately stored Hubris A/B for D01/D03/D05/D07/D08 with SQLite close/reopen checks. Do not start Part B until the Part A comparison is presented and the owner decides.
