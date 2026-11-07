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
