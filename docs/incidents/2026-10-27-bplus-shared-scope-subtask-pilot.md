# B+ shared scope policy and subtask coverage — frozen replay and Telegram pilot

**Дата:** 27.10.2026. **Статус:** offline GO; limited Telegram worker pilot started; waiting for the user's manual messages. No messages were sent by the agent.

## Краткий итог

- SourceFirst и экспериментальный ID-only selector теперь используют одну typed scope policy. Проверенные entity kinds (manufacturer, service, model/equipment, software/integration and OFD) stay distinct; missing facts stay distinguishable from confirmed conflicts. The selector flag remains **OFF** and its validator is not presented as the technical-path improvement.
- The retrieval subtask gate now treats `integration` and `peripheral_setup` as broad task families. In those families it requires a candidate-local subject anchor or at least two FAQ/evidence anchors; a confirmed named software integration is already a concrete subject fact. The gate does not use the first hit to infer the task or service.
- Frozen replay: **5/13 useful first answers in A-grade attempts**, unchanged from Resolver+Gate baseline; no useful A answer was lost. Scanner case #9 now returns scanner evidence (previously scales); API case #22 now safely escalates (previously returned a general integration catalog). Both historical irrelevant answers are gone. The scanner improvement is a useful B-grade first step, not an increase to the A-grade count.
- Full suite: **515 passed, 4 xfailed, 0 failed**. Stage3 read-only E2E: **15/15**. No new approved/SHA/scope/safety failure was observed in the frozen replay, negative controls, or E2E.
- Pilot: old worker PID **32988** stopped; single worker PID **23004** started. Runtime receipt contains **33/33** source hashes matching the running checkout, Stage3 green/934 points, SourceFirst and Coordinator enabled, Groq `openai/gpt-oss-20b` / medium, allowlist count 3 with the same preflight SHA-256, and selector/handoff disabled. Startup log has `Application started`, no polling conflict, traceback, or `ERROR -` line. SQLite source and backup both pass `quick_check`.

## Причины и минимальное изменение

### Общая scope policy

`app/scope_policy.py` now owns the shared scope comparison used by `source_first_service.py` and `semantic_evidence_selector.validate_selected_units()`. `procedure_policy.py` uses the same value matcher for its existing service applicability check. The source's approved metadata remains authoritative. A confirmed physical aQsi manufacturer cannot establish aQsi Online; ATOL Online/cloud cannot establish physical ATOL; manufacturer cannot fill a model slot. A missing value produces an unconfirmed/missing result; a different confirmed value produces a mismatch. Existing approval, source SHA, exact-section, grounding, procedure and safety checks were retained.

The selector validator itself is still not the live technical route: the experimental ID-only selector remains disabled. The production-path change is the candidate-level subtask gate in `RetrievalPipeline`, which runs before SourceFirst renders technical answers, plus shared applicability evaluation inside SourceFirst.

### Повторяющиеся ошибки

| Механизм | Доказательство | Изменение |
|---|---|---|
| Shared task family too broad | `peripheral_setup` admitted a higher-ranked weights article for a scanner request; `integration` admitted a general catalog for an API/receipt-delivery failure. The renderer copied the selected approved section accurately, so it was not a renderer hallucination. | For broad `peripheral_setup` and `integration` categories, require strong, candidate-local subject coverage. Other families retain their previous any-anchor behavior to avoid rejecting correct OFD connection and transmission evidence. |
| Competing scope checks | SourceFirst could accept a physical aQsi source from confirmed manufacturer context, while the selector validator demanded an independent `service` fact. | One evaluator returns separate missing and mismatch facts and preserves typed slots. |
| Evidence absence versus uncertainty | aQsi Online + 1C has a confirmed `software` subject; that exact software match must not be blocked by a generic lexical threshold. | A confirmed named software integration serves as a subject anchor; a catalog cannot establish an unmentioned API mode. |

No words, brands, model names, or test question strings were added as exceptions. No Understanding, DialogueState, Coordinator, KB or Qdrant changes were made. `SEMANTIC_EVIDENCE_SELECTOR_ENABLED=0` was preserved.

## Frozen 24-attempt replay

The full final answer, scenario/reason, route, selected document IDs, local latency, and provider counters for every anonymized attempt are in the [final replay JSON](../../experiments/architecture_recovery_audit/bplus_shared_scope_subtask_24_final_20261027.json). Prior production / Resolver / Resolver+Gate outcomes remain in the [three-way frozen matrix](../../experiments/architecture_recovery_audit/bplus_evidence_relevance_24_three_way_20261027.json). Case #11 remains unreplayable because its raw Understanding call returned HTTP 400; its recorded production response was not reconstructed.

| # | KB grade | Итог финального replay | Evidence / результат |
|---:|:---:|---|---|
| 1 | A | Useful answer | Evotor 7.3 approved diagnostic report section |
| 2 | A | Partial answer | FN 231 approved article; applicability remains bounded to described FN-M case |
| 3 | B | Clarify | Equipment model missing |
| 4 | B | Safety stop | Closing FN archive remains blocked |
| 5 | A | Clarify | Model needed before marking instructions |
| 6 | A | Clarify | Model needed before marking instructions |
| 7 | A | Clarify | Physical aQsi model missing |
| 8 | A | Clarify | Physical aQsi model missing |
| 9 | B | Useful first step | Scanner article selected; no weights instructions in final answer |
| 10 | B | Clarify | Equipment model missing |
| 11 | A | Not replayable | Raw Understanding HTTP 400; recorded response retained |
| 12 | A | Useful answer | aQsi Online fiscalization article |
| 13 | B | Escalate | Selected add-user evidence does not cover the requested role operation sufficiently |
| 14 | A | Useful answer | aQsi Online partial-refund article |
| 15 | C | Confirmed knowledge gap | No approved applicable evidence |
| 16 | C | Confirmed knowledge gap | No approved applicable evidence |
| 17 | B | Clarify | Model/context needed for ATOL Online error 128 |
| 18 | A | Safety stop | FN blocking/replacement procedure not exposed |
| 19 | A | Useful answer | ATOL Online receipt journal article |
| 20 | A | Useful first step | ATOL Online debt/payment article |
| 21 | B | Clarify | Manufacturer/service missing for FFD scope |
| 22 | B | Escalate | General integration catalog rejected for API delivery failure; no invented API steps |
| 23 | B | Clarify | Producer/model scope remains unresolved |
| 24 | A | Partial answer | Platforma OFD status meanings; no correction/reissue action |

Useful first answers among A-grade attempts remain **5/13** (#1, #12, #14, #19, #20), matching Resolver+Gate. Case #9 is an additional useful B-grade outcome but does not change the A-grade numerator. The count is based on final answer quality, not retrieval rank. Cases #15/#16 remain gaps and #18 remains a safety stop.

The deterministic local planner replay used no Groq calls/tokens. Median local replay latency was **638 ms** across 23 replayable requests versus **608 ms** in the previous Resolver+Gate replay (+30 ms, about 5%; local fixture timing, not live latency). Actual provider latency/tokens are not inferable from this offline difference.

### Negative checks and regression calibration

- Tests/E2E retain physical aQsi vs aQsi Online and cloud ATOL vs physical equipment separation; no unmentioned equipment model is filled in; explicit software/1C, manufacturer and model remain distinct.
- FN archive closure, FN error correction/registration and technical configuration without applicable evidence remain blocked or limited to a source-attributed fact. Wrong model/manufacturer, draft/unapproved scope, and selector source hash/section checks remain rejected by their independent gates.
- During calibration, requiring two anchors inside one individual title/FAQ/body segment rejected the scanner/API/transmission fixture positives. Requiring strict matching across every task family also rejected a named 1C integration and two OFD candidate-routing positives. Those negative results are retained here; expectations were not changed. The final rule scopes stronger matching to the two broad categories above and lets a confirmed named software match satisfy integration subject coverage; the full suite passes.
- Stage3 E2E's deterministic `generate` fixture substitutes local general-answer/planner output; its app-level `llm_call_attempted` flag describes fixture invocation, not a network request. No Groq request was made by pytest, replay, E2E, or worker startup.

## Telegram pilot and rollback materials

- Preflight recorded old PID 32988, HEAD `525b1b38cd20e1cf907f77862f2b1d729ad7ee6e`, Python 3.14, SourceFirst/Coordinator enabled, Stage3 `knowledge_stage3_retrieval_20261022` with 934 points, Groq configured, selector/handoff disabled, and allowlist count/hash. Raw Telegram IDs and secrets are not in the report.
- The old runtime receipt named commit `d1e68b1b...` while its 31 source hashes did not match that Git commit. To retain an independently bootable rollback target without overwriting the working tree, a private checkout of HEAD 525b1b38 and a `data` junction were saved under the backup folder. SQLite backup and source snapshots are ignored under `.local`.
- Production SQLite backup: `.local/backups/scope-policy-pilot-20261027T171206/conversations.sqlite3`; both source and backup `PRAGMA quick_check` returned `ok`. The `.env` copy in the private rollback tree byte-matches the active file; no `.env` edit occurred.
- New runtime: PID 23004, one worker only, Python 3.14, **33/33 source hashes match**, `Application started`, zero polling conflicts / tracebacks / `ERROR -` lines. Stage3 remained green/934. Runtime logs contain a Qdrant client/server version compatibility warning and an unauthenticated Hugging Face Hub warning; startup completed. The worker is now waiting for user-originated manual checks.
- No Telegram messages were sent by the agent. No KB, Qdrant, SQLite source, or `.env` content was modified; no commit/push was made.

## Вопросы для ручной проверки

Send these from an allowlisted Telegram account and compare the first reply with the expected boundary below. Do not treat an answer as proven until it is observed in the live conversation.

1. **Физическая aQsi, сканер:** «На физической кассе aQsi внешний сканер не считывает DataMatrix. Как проверить подключение?» Expected: stay in physical aQsi scope; ask for scanner model/interface if absent; cite that compatibility depends on scanner model and the USB-C adapter or aQsi Hub. No scales article.
2. **aQsi Online, partial refund:** «Нужно вернуть две позиции из чека aQsi Online. Что проверить перед частичным возвратом?» Expected: find the original receipt, keep only returned items, verify quantities/prices and the total; do not switch to reprinting or a physical aQsi flow.
3. **АТОЛ Онлайн, API/integration:** «Сайт отправляет запросы в АТОЛ Онлайн, но чеки не появляются. Что проверять?» Expected: clarify the direct API/CMS integration and its error/status evidence or escalate if the applicable API troubleshooting is not in approved KB. Do not answer with only a compatible-services catalog.
4. **Эвотор, FN 231:** «На Эвотор ошибка ФН 231 при продаже. Что безопасно посмотреть?» Expected: for the article's FN-M/36-month context, inspect the “Итог регистрации ККТ” report and position type; do not instruct archive closure, FN replacement or re-registration. Ask for missing context where necessary.
5. **Платформа ОФД, status in FNS:** «У конкретного чека в кабинете Платформы ОФД статус “Предупреждение”. Что это означает?» Expected: explain the status as receipt of the document with detected errors; ask for exact check/error if next action is requested. No correction, new receipt or reissue inferred.
6. **Control, Эвотор 7.3:** «Чеки пробиваются на Эвотор 7.3, но не уходят в ОФД. С чего начать?» Expected: administrator opens “Настройки → Обслуживание кассы → Диагностика”, prints the report, checks EoU, internet, address/port and queue. No low-level commands or reset.
7. **Control, DirectBank:** «В 1С перестали загружаться банковские выписки через DirectBank. С чего начать?» Expected: confirm 1C version and bank exchange setup; inspect the bank-statement list and matching account configuration. Do not recommend duplicate import.
8. **Negative scope pair:** repeat the scanner question once for aQsi Online and once for a physical aQsi device. Expected: ask which product was meant when unclear; never carry physical scanner steps into aQsi Online or cloud setup into a physical terminal.

**Остановка этапа:** ждать только эти ручные результаты. Не подключать selector globally, не начинать следующий архитектурный этап, не отправлять сообщения за пользователя и не делать commit/push до отдельной команды.


## Post-shutdown recovery (2026-10-28)

The computer shutdown removed worker PID 23004 and Docker Desktop stopped the existing Qdrant container; no code was lost. The existing container was started without recreation. The process-only SourceFirst/Coordinator/Stage3 environment was rehydrated without editing `.env`. The fresh sole worker is PID **39560**, runtime receipt 33/33 hashes match local HEAD `525b1b38cd20e1cf907f77862f2b1d729ad7ee6e`, and startup/polling checks are clean. Stage3 remains green/934; SQLite read-only quick checks passed; read-only Stage3 E2E passed 15/15; one direct Groq control response used 233 tokens. Full recovery evidence is in [2026-10-28 post-reboot report](2026-10-28-bplus-post-reboot-recovery.md). No Telegram messages were sent; manual testing is still pending.
