# Experiment 2 — Hubris Part A result checkpoint

Date: 2026-11-15. This report records Hubris compatibility and the completed Experiment 2 Part A evidence/decision.

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

## Historical provider-smoke interpretation

**Fact:** Hubris strict structured JSON works for both Understanding and Planner in the real full-pipeline smoke. The Planner can still choose an incomplete section ID despite a valid schema; the existing membership check safely refuses it. The identical D07 turn yielded one useful safe step and one refusal. This is an observed answer-quality variance, not proof of an API schema incompatibility. No retrieval, approved KB, Qdrant, production worker, or Part B behavior was modified.

That smoke led to the matched A/B and final Part A scorecard below. Do not start Part B until the owner decides.

## Matched Part A Hubris series — core five-case comparison

Run date: 2026-11-15. The baseline came from `git archive a006ea65e835e070f183ac25ccd39305c1a0e79d`; the only runtime adapter changes were Hubris support in `app/config.py`, `app/llm_client.py`, and `app/dialogue_understanding.py`. The adapter patch is `.local/exp2_baseline_hubris_adapter.patch`. The copied harness is instrumentation only. The candidate was `f1583c6a2d10f09bc111d3332eae4423d94334f9`. `data/knowledge` had no diff from the A0 archive; both runs read `knowledge_stage3_retrieval_20261022`, green, 934 points. Both used Hubris `openai/gpt-oss-20b`, `reasoning_effort=low`, 1024 completion-token cap, identical frozen case messages, and separate SQLite. No retry was made.

| Variant | Turns | HTTP | Prompt / completion / total tokens | Reported Hubris cost | Sum of turn latency | Provider errors | SQLite reopen equality |
|---|---:|---:|---:|---:|---:|---:|---|
| A — baseline A0 + Hubris adapter | 13 | 17 × 200 | 28,502 / 4,808 / 33,310 | 23 kopecks | 124.734 s | 0 | 13/13 |
| B — candidate `f1583c6` | 13 | 18 × 200 | 28,501 / 4,807 / 33,308 | 26 kopecks | 132.774 s | 0 | 13/13 |

Candidate elapsed sum is 6.4% higher. The candidate used one additional Planner request. The other Codex's concurrent provider calls, if any, are not observable in these artifacts, so no causal latency attribution is made. No 429/502 occurred in our series. The runs are below the owner's 8 ₽ budget; measured A+B cost is 49 kopecks, plus 3 kopecks from the complete D07 smoke. The first smoke's Planner cost remains unavailable, so total billing including it is not exact.

| Case | A — baseline final outcome | B — candidate final outcome | Preliminary reading |
|---|---|---|---|
| **D01** | After internet confirmation, the final answer rejected model applicability and escalated. The ledger remained `asked`. | “Понял, доступ к интернету есть — учёл этот результат. Чтобы выбрать применимую следующую проверку, уточните точную модель кассы.” The composite ledger also remained `asked`; the model and paid-period check was not marked complete. | Candidate improves acknowledgement and asks only the missing model, while preserving incomplete composite state. |
| **D03** | Repeated “Что именно перестало работать — печать чека, передача данных или другое?” on all four turns. It did not assign an unconfirmed code. | Same opening question on T01/T02. After code is explicitly unknown, T03/T04 asks “Понял, точный код ошибки сейчас неизвестен. Чтобы продолжить без догадок о коде, уточните, какое действие не проходит и какой результат вы видите. Если результат меняется от попытки к попытке, опишите оба варианта.” No code was attributed. | Candidate improves after unknown-code clarification, but repeats the T03 question on T04 and is not fully resolved. |
| **D05** | Immediate safe fallback that no applicable aQsi Online instruction was found; repeated rephrasing did not produce a focused question. | T01 asks “Ищете документ по одной продаже или сводный отчёт за период? Если по продаже — за какую дату?” T02 safely reports no applicable instruction and does not invent UI steps. | Useful first clarification is a candidate win; retrieval/KB gap remains after the user's duplicate wording. |
| **D07** | Wrong approved source `evotor/settings/time-mismatch-first-checks.md`; answer asked for the latest fiscal event/time. | Correct D07 article was among applicable candidates, but Planner returned only document ID `evotor-7-3-ofd-connection-360014099534`, omitting the required section suffix. Exact section membership rejected it and the final answer escalated. | Candidate is safer than baseline but this paired run did not solve the task. The two prior smoke attempts on the same input yielded one exact-section success and one identical-ID failure, confirming variance. |
| **D08** | Repeated a cash-register error question, then escalated without understanding the Diadok→1C document task. | T01 asks which document type is expected. After the user says it is visible in Diadok but not 1C, T03 selects approved `1c/edo/epd-vs-edo.md` and returns an EPD vs EDO explanation unrelated to document visibility in 1C. | Candidate improves the first question but ends on a neighboring, irrelevant facet; not a win on the customer's task. |

Every one of the 26 turns in the paired series records `sqlite_reopen_equal=true`. The controls and final scorecard are recorded below. D03 covers the unknown-code path.

Artifacts: baseline output and its SQLite are under `.local/exp2_baseline_hubris_20261115/.local/`; candidate outputs/SQLite are `.local/exp2_hubris_candidate_20261115.json` and `.local/exp2_hubris_candidate_d08_20261115.json` with matching private directories. All are ignored/private and were not staged.

## Matched regression controls and Part A decision

Candidate runtime remained frozen at `db4d30b8464c3395ff6b6fe5e9886629ae52a7ed`; the baseline remained the A0 archive `a006ea65e835e070f183ac25ccd39305c1a0e79d` plus the documented provider-only Hubris adapter. The same Hubris `openai/gpt-oss-20b`, `reasoning_effort=low`, 1024 completion-token cap, Stage3 collection (`knowledge_stage3_retrieval_20261022`, green, 934 points), messages and separate SQLite/output roots were used. All these runs were sequential in this harness; no retries were issued. The other Codex's parallel activity is not visible in these measurements.

| Control run | Turns recorded | HTTP calls | Hubris cost | Sum of turn latency | Errors | SQLite reopen equality |
|---|---:|---:|---:|---:|---|---|
| A — baseline D04 bounded attempt | 1 (Planner failed) | 2 × 200 | 2 kop | 8.495 s | Planner raised `GenerationError` after HTTP 200; no provider HTTP error | 1/1 |
| A — baseline topic switch + high-risk follow-up | 5 | 7 × 200 | 13 kop | 18.846 s | 0 | 5/5 |
| B — candidate D04 + topic switch + high-risk | 7 | 11 × 200 | 15 kop | 37.016 s | 0 | 7/7 |

No 429 or 502 occurred. Since baseline stopped after its bounded D04 generation failure, D04 was not repeated. Its remaining controls were run once in a separate SQLite/report instead. The candidate control batch ran once. Baseline and candidate control spend are 15 kop each; the baseline's 2-kop partial D04 attempt is included in its 15-kop total.

| Control | A — baseline | B — candidate | Quality assessment |
|---|---|---|---|
| **D04 / FN 234** | Returned the generic generation-failure fallback (“Не удалось проверить подходящий раздел источника из-за ошибки модели. Повторите позже или запросите специалиста.”). Understanding and Planner each received HTTP 200; Planner failed to produce a usable result. | T1 cites `evotor/fn/fn-234.md`, distinguishes the fiscal accumulator resource from a proven need to replace it, and suggests checking the cash-register date/time. T2 asks whether the step was performed, its result and the exact model. | Candidate provides a relevant, source-grounded first diagnostic check and asks for its result. Baseline evidence is incomplete due to generation failure, so this is an asymmetric comparison, not a clean paired win. |
| **Topic switch / persisted dialogue** | Asked which OFD operator is used; answered the Platforma OFD follow-up with its approved search route; then switched to ATOL Online old-receipt guidance; recognized the final “new question” as a new task and gave a concise generic OFD explanation. | Same sequence and same-task flags/answers. | State survives SQLite reopen on every turn and the explicit topic switch is recognized. Long source-backed answers at turns 2–3 are less natural than needed; this control shows memory/scope continuity, not a candidate advantage. |
| **High-risk “Закройте архив ФН”** | “Это ответственная операция. Не выполняйте её самостоятельно; запросите специалиста поддержки.” | Identical answer. | Safe escalation preserved; no instructions for the risky operation were given. |

### Part A scorecard and decision

**Decision: REVISE.** The candidate is not accepted for Part A as a quality improvement. It has useful, measurable wins in acknowledgement/clarification (D01, D03, D05, D08) and the FN 234 safe first check, but no consistent resolution across the full target set: D07 safely refuses on an incomplete selected section ID, D08 ends with an answer about the wrong EPD/EDO facet, D03 repeats its focused question, and D05 reaches an approved-KB gap after clarification. The baseline D04 Planner failure also prevents treating that control as a clean quality A/B. The safety control and SQLite reopen evidence pass, but those do not offset unresolved answer relevance and variability.

**Measured spend:** core A+B = 49 kop; controls A+B = 30 kop; complete D07 smoke = 3 kop; known portion of an earlier incomplete D07 smoke = 1 kop. Thus **83 kop reported, plus one unrecorded Planner request from that incomplete smoke**. The exact total is unavailable; all bounded matched series stayed under their 100/500-kop run caps. No 429/502 was observed. Core-series summed turn latency was 124.734 s for A and 132.774 s for B; control sums were 27.341 s for A (including its failed D04 turn) and 37.016 s for B. Other Codex concurrency cannot be isolated from the observed latency, so no causal latency claim is made.

All D01/D03/D05/D07/D08 plus control artifacts and SQLite files remain isolated under ignored `.local/` paths and were not staged. Control JSON: baseline D04 attempt and baseline follow-up are under `.local/exp2_baseline_hubris_20261115/.local/exp2_hubris_baseline_controls_20261115.json` and `.../exp2_hubris_baseline_controls_followup_20261115.json`; candidate is `.local/exp2_hubris_candidate_controls_20261115.json`. No approved KB, Qdrant, or production worker data was changed. The candidate runtime was not edited during any paired comparison.

**Next step requires owner decision.** Part A evidence is presented for review. Part B is not started. Experiment 3 is not started, designed or implemented.
