# P1 B+ — offline replay and route contract repair (2026-10-26)

## Decision

The three Stage 4B QUALITY FAIL paths now reach a useful, safe next action in an offline `bot.handle_message` replay with temporary SQLite and the saved raw Groq Understanding payloads. The replay makes no Groq calls and performs no network Qdrant, Telegram, worker, KB, or production database operations. It uses the existing approved local articles through the test retrieval fixture; it does not prove live Qdrant ranking or live provider quality.

The code and regression suite are ready for a small, separately authorized live gate. Live and production remain **NO-GO** until that gate independently confirms useful evidence selection, source integrity, and safety. B2 remains default-off.

## Trace interpretation correction

Stage 4B did not make any Groq HTTP calls for Evidence Decision, planner, or composer: all four provider calls were Understanding. However, the saved trace does show local Qdrant retrieval on the two Evotor turns (two candidates each) and on the quota-blocked receipt-period turn (73 candidates, one selected). The OFD turn returned before retrieval. The Evotor candidates were all rejected by task/operation applicability (`receipt_transmission != receipt_search`), so those turns had no selected evidence. No source SHA validation occurred. The previous Stage 4B summary that reported zero retrievals was too broad; it conflated the absence of a retrieval-stage Groq call with the local Qdrant search. See the per-turn `retrieval_diagnostics` in [the original trace](p1_unified_live_gate_trace_20261026b.json).

## Causal chains for the three QUALITY FAIL turns

### 1. OFD information question

**User:** «После регистрации продажи что происходит с фискальным документом у оператора ОФД до передачи сведений в налоговую?»

1. **Raw Understanding:** `question`, `new_task`, `intent=explain`, `operation=explain`, object `фискальный документ`, goal `что происходит`, entity slot `оператор ОФД` with value `ОФД`.
2. **Validated Understanding:** correctly normalized to `information/general/explain`. The object value was rejected as unsupported, and the entity was rejected because `оператор ОФД` is not a typed entity slot. Its exact object quote and goal remained in the observation. These lost optional fields did not make the question unanswerable.
3. **DialogueState before → after:** before: no active task, intent/operation/object/entities absent. After: task `task:1`, `general/explain`, no object or entities, subgoal `что происходит`, and ledger `open_question=task`. The saved trace does not show `analysis_required` or a typed expected clarification as the early-return cause.
4. **Coordinator:** `grounded_information`, action `retrieve_and_quote_focused_approved_evidence`.
5. **SourceFirst branch:** its `broad_explanation` heuristic did not recognize «что происходит» as an explicit definition phrase, so it marked the task incomplete and returned `dialogue_state_task_incomplete` before search. `analysis_required`, `turn_kind`, missing typed expected clarification, and Coordinator route mismatch were not the trigger; the Coordinator correctly said retrieve, and the independent SourceFirst regex re-check contradicted it.
6. **Old final:** «Что именно нужно сделать или что сейчас не работает?» No retrieval, answer, or safety issue.

**Cause:** contradictory readiness authorities. The coordinator selected grounded retrieval; SourceFirst overrode that decision using a legacy phrase heuristic, even though the optional object/entity had been lost and the exact current question was sufficient for a read-only definition lookup.

### 2. Initial Evotor diagnostic

**User:** «На Эвотор 7.3 после переезда на другой роутер чек печатается, но в кабинете ОФД его пока нет. Какую безопасную проверку начать первой?»

1. **Raw Understanding:** `diagnosis/procedure`, exact model value `Evotor 7.3` incorrectly supplied as the entity slot, plus router/receipt/cabinet entities. The symptom/goal correctly stated that a printed receipt was absent from the OFD cabinet.
2. **Validated Understanding:** unsupported `diagnosis` intent and `procedure` operation became `unknown`, then safe grounded-goal fallback produced `general/search`. Every provider entity slot was rejected; the known manufacturer alias «Эвотор» was independently recovered, but model `7.3` was lost. The exact symptom/goal remained.
3. **DialogueState before → after:** before: no active task or confirmed entities. After: `general/search`, manufacturer `Эвотор`, no confirmed equipment/model, symptom and subgoal «чек печатается, но в кабинете ОФД его пока нет».
4. **Coordinator:** `technical_action` because the reducer operation was non-unknown (`search`), with action to retrieve and then apply independent gates. The route did not preserve the task semantics that had been collapsed into generic search.
5. **SourceFirst/retrieval:** local Qdrant search ran and returned the approved Evotor 7.3 transmission article. `_state_task_category` classified the task as `receipt_search`; the article was `receipt_transmission` with operation `check_transmission`. The independent applicability filter rejected it as `task_mismatch:receipt_transmission!=receipt_search`. No evidence was selected and no source SHA gate ran.
6. **Old final:** «Не нашёл подтверждённую применимую инструкцию для этой задачи. Не буду предлагать неподтверждённые шаги; запросите специалиста кнопкой ниже.»

**Cause:** loss of the typed operation and model at validation, followed by a generic search-derived task category that contradicted the actual transmission-status problem. Retrieval itself worked; the applicability classifier rejected the matching approved article under the wrong task category.

### 3. Evotor follow-up

**User:** «Сайты теперь открываются, тестовая продажа прошла, чек распечатался, но в кабинете он не появился. Что проверить следующим, не создавая ещё одну продажу?»

1. **Raw Understanding:** `continuation`, `intent=procedure`, `operation=procedure`; goal asks for the next check without creating another sale; symptom says the receipt is absent from the cabinet.
2. **Validated Understanding:** `procedure` again failed the operation enum and fell back to `general/search`; continuation and the current symptom/goal were retained. The first turn had already lost the model, so there was no confirmed model to carry forward.
3. **DialogueState before → after:** before: task `task:1`, `general/search`, manufacturer `Эвотор`, no equipment/model, no shown units or checks; previous subgoal was the missing receipt symptom. After: the same task continued, still `general/search` and manufacturer-only, with the current symptom and “what to check next” subgoal preserved. No check result existed to advance.
4. **Coordinator:** `technical_action`, again from the fallback operation rather than the original diagnostic meaning.
5. **SourceFirst/retrieval:** local search again found the approved Evotor transmission candidate and rejected it as `receipt_transmission != receipt_search`. Since no applicable evidence was selected, the ProgressLedger had no source-derived next check or shown unit to advance. The service escalated rather than asking for the result of an already shown step (there was no such step in this failing path).
6. **Old final:** same “no applicable instruction” escalation as the first Evotor turn.

**Cause:** same typed-operation/category mismatch as turn 2, compounded by the lost model fact from turn 1. The follow-up's new report did not repair that earlier semantic loss.

## Architecture changes

- Normalize semantic aliases `diagnosis`, `procedure`, and `procedural` to the existing `diagnose` operation. Keep request type (`question`) independent from operation.
- Accept a provider's model-as-slot claim only when its value is grounded in the exact current-message evidence. Recover a transliterated model from the known shared manufacturer alias registry and a model-shaped suffix; no brand-specific branch or inference from prior/assistant text. Approved metadata applicability still decides whether the article applies.
- Make Coordinator the readiness authority when it selects `grounded_information` or `technical_action`; SourceFirst no longer re-runs conflicting broad-explanation, expected-slot, analysis-required, or unknown-operation checks on that route. Conversation routes still ask for reducer-owned missing information. Safety, approved status, source integrity, applicability, and unsafe-operation gates remain independent.
- Treat general/explain as a read-only evidence query that needs no service/model/task-category label. If its parsed focus is too short to retrieve relevant facts, use the exact current user message as focus. Informational candidate acceptance remains evidence- and scope-checked.
- Classify a diagnostic absence in an operator cabinet as transmission/status when the reducer confirms a manufacturer plus receipt, operator context, and absence. This shared task-family rule prevents generic `receipt_search` fallback from excluding transmission guides.
- Remove redundant overlapping detail facts from the retrieval query so accumulated state cannot overflow the query budget. For procedures without numbered lists, group exact source sentences into ordered units: preceding conditions and warnings travel with the next imperative; trailing caveats remain with the last imperative. Show one approved unit, record it, and require its client result before moving to the next applicable unit.
- Positive client-result parsing recognizes explicit “подтверждено” language. It still requires an exact current-client span; assistant suggestions never become client results.

These changes repair semantic handoff between Understanding, reducer, coordinator, and retriever. They do not special-case any holdout sentence or service, and do not weaken model scope, source checks, or safety stops.

## OLD / FIXED comparison

| Turn | OLD route and final | FIXED offline route and final | Retrieval | Usefulness / safety |
|---|---|---|---|---|
| OFD definition | Coordinator chose `grounded_information`; SourceFirst returned `dialogue_state_task_incomplete`: «Что именно нужно сделать или что сейчас не работает?» | Approved-source answer: «ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.» It identifies the source scope as АТОЛ Онлайн. | OLD: not reached. FIXED: reached; approved local fact selected. | OLD: not useful. FIXED: useful, read-only, source-attributed. |
| Evotor first check | `technical_action`; local candidate rejected by `receipt_transmission != receipt_search`; escalated: «Не нашёл подтверждённую применимую инструкцию…» | Exact approved first check: «Под ролью администратора откройте „Настройки → Обслуживание кассы → Диагностика“ и напечатайте диагностический отчёт.» | OLD: Qdrant candidates returned, none selected. FIXED: approved source selected in offline fixture. | OLD: safe but not useful. FIXED: useful first check; exact approved text; model matched. |
| Evotor follow-up | Same task mismatch and same escalation; no ledger step had been shown. | Retrieval succeeds; because the first check's client result is not yet known, asks: «…удалось ли выполнить показанную проверку и каков её результат.» After a synthetic, exact client report «В диагностическом отчёте доступ в интернет подтверждён», replay advances to the next approved check: «В нём проверьте состояние приложения EoU, доступ в интернет, адрес и порт ОФД.» | OLD: candidates returned, none selected. FIXED: retrieval reached for the follow-up and result turn. | OLD: safe but unhelpful/repetitive escalation. FIXED: useful progress; does not repeat the step or create a sale; requires client confirmation. |

The exact saved Understanding payloads were replayed through the real `bot.handle_message` handler with temporary SQLite; no state was injected. The synthetic report-result turn is an additional progression assertion, not a claim about the three live holdout turns. Full trace: [offline replay JSON](p1_bplus_offline_replay_20261026.json). Regression coverage is in [the Understanding tests](../../tests/test_dialogue_understanding.py) and [the SQLite bot replay tests](../../tests/test_telegram_pilot_sqlite_replay.py).

## Stage A neighbor-route and procedure-order regression (added after initial B+ replay)

The independent route checks preserve four distinct categories: personal-cabinet receipt lookup → `receipt_search`; receipt absent from OFD → `receipt_transmission`; cash register not powering/printing → `error_diagnosis`; general explanation → no technical task category. The no-list procedure regression verifies that a source precondition and warning stay attached to the first action, the next action remains second, and a trailing caveat stays attached to it. Exact source sentence order is asserted.

## Groq Understanding token accounting

The four Stage 4B calls used 3,757 prompt tokens (939 average) and 4,546 completion tokens (1,137 average; range 930–1,465), 8,303 total. Prompt was 45.3% and completion 54.7% of reported tokens. The trace exposes only aggregate prompt/completion/total counts. It does not retain the request prompt bodies or `prompt_tokens_details` / `completion_tokens_details`; it has no history/schema split and no reasoning-token split. The implementation sets `reasoning_effort=low`, JSON-schema structured output, and `max_completion_tokens=4096`; the `completion_tokens` count does not tell us how much was reasoning versus structured JSON. Therefore no component-specific contribution can be measured from this trace. No provider calls were made to measure it.

Safe follow-up cost work: add offline per-request byte/character accounting for fixed rules, active-state summary, recent-history messages (currently up to 12), current message, and JSON schema; log provider token detail fields when returned; and compare a prompt that includes only task-relevant recent turns against current full history while replaying all continuity/change/contradiction tests. After output-length and quality evidence, trial a 2,048-token completion ceiling (highest observed was 1,465, leaving 583 tokens of headroom), with explicit truncation detection and rollback. Keep reasoning effort at `low` until a paired quality test supports changing it. Do not remove structured output or safety semantics.

## Verification and next gate

- Targeted saved-understanding B+ replay: **1 passed**. ProgressLedger E2E: **1 passed**. Additional combined handoff, safety, unknown/changed model and topic/closure checks: **7 passed**. Full pytest after the final code change: **454 passed, 4 xfailed, 13 warnings, 0 failed**.
- The suite includes topic changes, contradiction, closure, missing required data, unknown/confirmed/changed model, handoff with ProgressLedger, and independent safety stops. No live calls were made.
- The trace reports a Groq TPM limit of 8,000, 1,324 remaining at stop, and 50.07s token reset; the next Understanding request was estimated at 3,092. Propose one small serial live gate with just the OFD information turn and one initial Evotor diagnostic turn, no follow-up. Hard cap four HTTP attempts total, no retries/concurrency. Start only after a fresh quota read; before every stage compare the provider's remaining TPM with that stage's conservative estimate plus 1,000-token reserve. If it is insufficient, stop and wait for the reported reset before continuing; do not start a request that would exceed the bucket. Use read-only Stage3 Qdrant, keep B2 default-off, and score answer usefulness/source/safety separately. The live gate is not authorized by this offline work.
- **GO:** offline implementation and full tests. **NO-GO:** live gate, B2 activation, Telegram, worker, or production changes until separately authorized and independently scored.
