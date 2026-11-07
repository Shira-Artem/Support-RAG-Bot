# B2.2d / P0.2 — full pipeline checkpoint

Date: 2026-11-07. This is a limited experimental checkpoint, not a production or general quality approval. Experimental mode stayed isolated; the production default remains disabled.

## Environment and pipeline

- `rag-qdrant-1` was stopped (`Exited 143`), explaining the earlier `127.0.0.1:6333` ConnectTimeout. Started the existing container with `docker start`; kept its existing named volume, collection and point data. No recreation or write operation was used.
- Existing Stage3 collection `knowledge_stage3_retrieval_20261022` reported green/readiness, 934 points, 384-dimensional cosine vectors. The bounded runner used a ReadOnlyQdrant facade.
- `SEMANTIC_COMPOSER_ENABLED=1` was set only in the isolated LIVE harness. Real `bot.handle_message` path: Groq Understanding → isolated DialogueState/SQLite → Coordinator → Stage3 retrieval → evidence selection → Composer where reached → independent grounding/safety → final answer. No Telegram and no production SQLite.
- Full test suite with project `.venv`: **840 passed, 4 xfailed**. Running under system Python first gave one unrelated `ModuleNotFoundError: langgraph`; `.venv` is the documented runtime and passed it.
- Existing Qdrant client 1.19.1 emits a compatibility warning against server 1.15.4; read-only operations and retrieval tests passed.

## Code changes

- Routed semantic information intents (including read-only compatibility/version questions projected as check/connect) to the opt-in grounded information path. Explicit procedure requests remain on the strict technical-action route.
- Experimental information selection can inspect locally verified approved Stage3 candidates otherwise lost solely to task-category mismatch, or not expanded by retrieval. It verifies local metadata parity, source sections and scope, ranks before a bounded section budget and limits per-document dominance. Default SourceFirst path is unchanged.
- Reduced selector prompt metadata to evidence IDs, focused text and scope. Raised only the semantic-selector Groq completion budget to 2048; added procedure-language filtering for descriptive UI/workflow sentences. Independent grounding, condition and safety gates remain in place.
- Retained candidate fallback behavior: a rejected paraphrase can only fall back to selected, locally verified source wording or safe escalation.
- Added route, retrieval admission/ranking, prompt shape/budget and descriptive-procedure regressions. P0.1 Ledger reducer remains independent of Composer; full test suite passes.

## Full-pipeline LIVE outcomes

### Positive cases

DirectBank question: “В 1С через DirectBank можно настроить получение выписок по расписанию? От чего это зависит?”

- Earlier SourceFirst final answer: no usable answer / escalation after `no_conceptual_evidence`, despite an approved retrieved source.
- Experimental full-pipeline final answer: “Начиная с версии 3.0.195 программа поддерживает расписание и параметры автоматического получения банковских выписок через 1С:ДиректБанк. Поддержка зависит от конкретного банка.” It cites the approved DirectBank section. A Composer paraphrase that did not satisfy claim validation fell back to selected source wording.

USB hub question: “Гарантируется совместимость стороннего USB-хаба с физической кассой aQsi при зарядке и подключении оборудования?”

- Earlier SourceFirst dropped the approved peripheral article on `task_mismatch:peripheral_setup!=integration` and asked an irrelevant OFD question.
- Experimental full-pipeline final answer: “Для сторонних USB-хабов поведение может отличаться, гарантированной совместимости нет.” It preserves the physical aQsi scope and points to the approved peripheral source.

OFD purpose question: “Что оператор фискальных данных делает с кассовым чеком?”

- Experimental final answer: “Оператор фискальных данных получает кассовый чек, обрабатывает его и передаёт в ФНС в предусмотренном формате.” Approved ATOL Online source and cloud-KKT scope were included.

Follow-up: “А куда он его потом передаёт?”

- Dialogue state retained the same task (`same_task=true`), SQLite close/reopen state matched, and the response correctly answered that fiscal documents go to the FNS in the specified format.

Foreign service: a DirectBank daily-import question scoped to Контур.Диадок escalated for lack of applicable approved evidence; it did not transfer the 1C procedure.

Wrong-model follow-up: the user corrected Evotor 7.3 to Evotor 6. State kept the same task and SQLite reopen matched. The second answer came from the Evotor 6 connection article, not the 7.3 procedure. The follow-up state representation does not persist a `confirmed_equipment` slot, so correct source selection is evidenced, but entity-state confirmation remains a limitation.

Dangerous FN request: the assistant refused to explain disabling the fiscal drive/deleting its data and requested specialist review. It did not provide operations from adjacent error articles.

## Unresolved LIVE evidence / quota stop

- Independent OFD wording (“Куда попадает чек после отправки кассой оператору фискальных данных?”) was no-evidence escalation in older attempts. Later retrieval diversity and selector-prompt fixes are not yet confirmed on this exact full-pipeline question.
- Unknown-receipt question (“В aQsi Online где найти чек, если номер документа неизвестен?”) previously received a misleading answer about finding the original document and opening a refund action. A general procedure-language filter and offline regression were added, but this LIVE case has not been repeated after the fix.
- Unsupported ATOL Online menu case has not reached a usable LIVE result.
- Final bounded retry passed Understanding (HTTP 200) on the independent OFD question, then semantic selector received Groq HTTP 429 TPD: limit 200,000 tokens/day, used 199,202, requested 5,769; retry-after 2,148 seconds. Composer was not called. Bot safely escalated (“Не удалось проверить выбор evidence. Запросите специалиста.”). This is quota-blocked evidence, not a successful answer and not a Composer validation rejection. No further LIVE requests were issued.
- Earlier transient provider limits were recorded: selector payload HTTP 413 at 8,279 TPM tokens (later payload compaction), selector JSON truncation at 1,024 tokens (budget raised to 2,048), and HTTP 429. Preserve the traces in `p02_full_pipeline_live_*.json`.

## Gate and protected data

Limited information-path functionality is demonstrated for several new phrasings and full dialogue continuations. **P0.2 GO is not proposed yet** because the two unresolved negative/independent cases include a prior irrelevant-answer defect and must be checked LIVE after the provider quota resets. Production behavior remains disabled by default. Do not infer technical-procedure N07/m01/d10, P1.1, P1.2, frozen holdout or production readiness from these results.

Production SQLite, approved KB and frozen holdout were not read for mutation or modified. The new isolated runs wrote under `.local/telegram-equivalent-*`; existing Stage3 Qdrant was read-only. See traces: [full pipeline runs](p02_full_pipeline_live_verified2.json), [latest quota-blocked retry](p02_full_pipeline_live_final_review.json), and earlier [final live run](p02_full_pipeline_live_final.json).

## Final three LIVE cases and P0.2 decision — 2026-11-07

This section supersedes the quota-limited NO-GO above. Each case used real `bot.handle_message`, actual Groq, the existing read-only Stage3 collection, and a fresh isolated SQLite runtime with `SEMANTIC_COMPOSER_ENABLED=1`. Collection `knowledge_stage3_retrieval_20261022` remained green with 934 points. All HTTP calls returned 200, provider errors were zero, and isolated SQLite reopen equality was true for all three cases.

### Final answers and evaluation

1. **Independent OFD wording** — “Куда попадает чек после отправки кассой оператору фискальных данных?”

   Final answer:

   > Область источника: АТОЛ Онлайн — облачная ККТ. ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.

   Source: `data/knowledge/atol_online/ofd/what-is-ofd.md`, section “Что проверено по инструкции производителя”, evidence ID `ev-bd63d4ae34736e3385ba0c08`. The selector chose the exact approved ID; local SHA/section checks passed; relevance judge returned `relevant` with that same ID only. Composer paraphrase omitted “от зарегистрированной ККТ”; material qualifier check rejected it, so final output is the exact source sentence. Final facts and scope are grounded and complete. Earlier SourceFirst result for this independent wording was no-answer escalation; the intermediate semantic run once attached an unrelated Platforma OFD re-registration citation. RRF-first candidate ordering and relevance-supported ID filtering fixed those general failures.

2. **aQsi Online unknown receipt number** — “В aQsi Online где найти чек, если номер документа неизвестен?”

   Final answer:

   > В approved-источниках не нашёл подтверждённого ответа именно на запрошенную часть вопроса. Запросите специалиста.

   The selector chose two statements from `data/knowledge/aqsi_online/account/my-cash-registers.md`, section “Просмотр”: the “Мои кассы” list and a figure showing KKT/FN/count/status/date columns and a filter button. Both statements are in the correct aQsi Online service/model scope, but neither establishes how to find a receipt without its document number. Composer also produced an unsupported claim that the filter searches by date/status. Python claim validation rejected that paraphrase; exact-source fallback was tested by the semantic relevance judge, which returned `irrelevant`, `answers_current_question=false`, no supporting IDs. Final answer is a safe escalation. The earlier LIVE answer incorrectly stated that the history contains the original document and offered a refund action; that unsupported substitution no longer reaches the user.

3. **Unsupported ATOL Online menu** — “Где в АТОЛ Онлайн включить автоматическую отправку закрывающих документов?”

   Final answer:

   > По подтверждённым источникам не удалось выбрать безопасное решение. Запросите специалиста кнопкой ниже.

   Strict Planner returned `clarify`, `applicability_confirmed=false`, `source_order_complete=false`; its reason was that no candidate section addresses this feature. Composer was not called; no menu location/action was invented. This case remains on the strict technical/action path.

### General causes fixed during confirmation

- Added a semantic answerability/relevance gate after ID selection and composition. Grounding every sentence is not treated as proof that the answer resolves the question. Only IDs independently marked as supporting are cited; Python rechecks all claims/qualifiers against that subset.
- Candidate sections are ordered by fused retrieval rank before the bounded section budget. Previously metadata/task relevance scores could crowd out a stronger actual query candidate. The selected approved source is still checked locally for scope/SHA/exact section.
- Added generic preservation checks for material source qualifiers. If the fluent answer drops a qualifier such as registered source or prescribed format, final response uses exact approved wording.
- Reduced duplicate DialogueState content in the selector prompt and set only selector reasoning to low with a 3072 completion budget. Composer reasoning is unchanged. Earlier responses that exhausted the token budget or refused despite available scoped evidence remain in `p02_full_pipeline_live_final_round3/4/6/7.json` as failed iterations, not successes.
- A first full pytest after expanding a shared legacy condition regex caught two P0.1 semantic-judge regressions. The global regex was restored; qualifier checks remain local to the experimental Composer. Targeted P0.1/Ledger coverage then passed and the final full suite passed.

### Final offline and gate

Final full project `.venv` suite: **843 passed, 4 historical xfailed in 233.64 seconds**. Final trio trace: [p02_full_pipeline_live_final_round8.json](p02_full_pipeline_live_final_round8.json). Earlier `[verified2](p02_full_pipeline_live_verified2.json)` provides the full-pipeline follow-up memory, foreign-service, wrong-model correction and dangerous-FN outcomes.

**P0.2 GO — limited to the feature-gated informational answer path.** Production default stays disabled. The gate covers these positives and safe fallbacks; it is not approval for production, procedures, N07/m01/d10, P1.1/P1.2, frozen holdout, or the overall B2.2d quality gate. The extra relevance model call adds latency/token cost. Production SQLite, approved KB, and frozen holdout were not modified.
