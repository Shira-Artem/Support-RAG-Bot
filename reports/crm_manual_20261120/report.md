# First owner CRM pilot review — 20.11.2026

## Status and capture

Owner's Telegram test around15:40–15:45 Moscow: **manual acceptance FAIL**.
Running baseline: RAG4e16bcc code, CRMd5f4c70, same authorized Telegram token,
one poller and isolated crm_rag_demo. Prior successful transport checks did not
establish useful conversations or clean UI. Existing overall production NO-GO
is unchanged. This step captures and diagnoses; no routing/answer/menu repair is
claimed or deployed by this evidence step.

Private consistent MySQL read-only snapshots, SQLite backup and copied files:

- `.local/manual-review-20261120-first/`: first pre-change capture,50 files,
  relevant native support tables, RAG SQLite, original Understanding traces,
  receipts, logs and bot persistence. Manifest stores byte lengths/SHA256.
- `.local/manual-review-20261120-with-ui/`: expanded capture,51 files plus19
  `bot_events` metadata records after identifying that analytics table. First
  capture did not include bot_events; it is retained, not overwritten.
- `crm/tables.json`, `rag-state.sqlite3` and `manifest.json` contain private IDs
  and are not exported to Git. No env files, bearer tokens or attachments were
  intentionally copied. Logs/persistence are treated as private sensitive data.
- Components were captured separately; no distributed atomic snapshot is claimed.
  Per-file changed-during-read flags and capture times remain in the manifests.
- Reproducer: `scripts/capture_crm_manual_review.py`, run with CRM Python,
  explicit CRM/RAG roots and a new output directory. It refuses other DBs and
  performs no provider/Telegram calls, schema changes or message deletions.

The snapshot holds15 native support messages in total, of which4 are from this
owner test: two client inputs and two assistant responses. It also contains the
two API receipts and two successful native delivery mappings for those answers.
Other rows are the earlier explicitly synthetic smoke, not additional owner
turns. Shopping/UI messages are not all native support messages.

## Findings: facts, boundaries and hypotheses

| ID | Observation and evidence | Proven cause / remaining uncertainty |
|---|---|---|
| R1 | Owner reported «привет помоги с офд» → two OFD products. Route log15:41:55: product_search/multiple_verified_products/.90. Exact read-only replay reproduces search_results. Independent «Помоги разобраться с ОФД» also does. | Catalog-name matching outranks an unrecognized help request. This input did not produce an observed RAG API turn; it is not evidence of poor KB retrieval. Exact original input survives in the owner's report, not a stored ingress-text event. |
| R2 | «Интернет работает, подписка ОФД активна, очередь не уменьшается» → same product results at15:42:51. Replay returns search_results and support_shop_exit=True. | Active support accepts a high-confidence product match as a shop exit without requiring a client request to shop. User's result/facts never reach RAG in this case. Both source logic and replay confirm the boundary failure. |
| A1 | First actual RAG turn «Эвотор не отправляет чеки» → «Что именно происходит с кассой?..». Raw Hubris Understanding omits object, manufacturer and symptom; alias validation restores receipt/manufacturer, operation resolver recognizes receipt transmission, but symptom stays null. Exact task text survives in task_fact/details. | Coordinator requires symptom/goal/error and selects ask_for_missing_problem_detail. SourceFirst incomplete-task branch emits a template before retrieval. retrieval_diagnostics=null; KB/Planner/Composer were not exercised. The client did state a failure, so repeated intake is not justified by absence of text. |
| A2 | Second identical native input → «Какой результат вы хотите получить?». Understanding labels information/continue with symptom=null. Same task survives; template chooser selects another unasked question. | Intent/operation normalization and symptom completeness disagree. Changing templates does not resolve the already stated task. Model extraction and the deterministic readiness gate both participate; no broader causal fix is claimed yet. |
| D1 | Two different incoming native message IDs, approximately8 seconds apart; two different AI attempts/API keys; each answer stored and delivered once. First reply was committed just after the second input arrived. | No duplicate delivery of one input demonstrated. Two identical user rows legitimately reappear in the later history card. We do not infer whether this was a deliberate repeat, double tap, or a retry caused by unclear waiting feedback. |
| U1 | Existing TelegramUIFlow and safe edit/delete utilities provide menu lifecycle management. However product search calls send_or_edit with its default use_ui_flow=False. Text-driven equipment cards send directly; with no callback they neither delete the preceding card nor register the new message as the active screen. | Cleanup was provided, but these paths bypass it. The missing integration is code-confirmed; it is not evidence that a colleague ignored UI management generally. |
| U2 | support_v2 sends new answers via its durable outbox independently of the bot UI. ClientBotController.card embeds the last five chat messages again. | Independent delivery/history renderers add visible repetition and are outside the active-menu pointer. Which particular historical buttons remained in the client cannot be fully reconstructed from the old endpoint/status-only log. |
| U3 | Several deleteMessage calls returned400, while other deletes/edits returned200. Old log retained neither target message IDs nor provider error descriptions. Persistent reply-keyboard message is intentionally protected from deletion. | Do not equate all400s with stale inline menus. Missing targets vs protected keyboard vs redundant deletion require next-run detailed IDs/descriptions. The protected bottom navigation and orphan inline cards are distinct issues. |

The raw delivery/API diagnostics label template model as `openrouter/auto`, but
`answer_used_model=0` and the saved Understanding records identify real Hubris
`openai/gpt-oss-20b`. This legacy diagnostic label does not prove a provider/model
switch. Both saved Understandings validated structurally; empty symptom extraction
remains a quality failure, not a successful understanding of the problem.

## Minimal mechanism replay (read-only, no LLM calls)

| Input | Current action | Active support exits? |
|---|---|---|
| привет помоги с офд | search_results | Yes — FAIL |
| Помоги разобраться с ОФД | search_results | Yes — FAIL |
| Интернет работает, подписка ОФД активна, очередь не уменьшается | search_results | Yes — FAIL |
| Нужна помощь с оператором фискальных данных | clarify / operation_missing | No; useful consultation not established |
| Касса не передаёт чеки, подписка ОФД оплачена | support handoff | No — correct control |
| Хочу купить ОФД | catalog | Yes — correct control |
| Спасибо, теперь хочу купить ФН | product card | Yes — correct control |

Private replay rows are preserved alongside the first capture. They are not LIVE
LLM evidence. Route behavior also matches the observed logs/product screen hash.

## Next-run observability, not a quality fix

Added private opt-in `services/support/pilot_trace.py` and instrumentation for
native ingress, callback, pre-handler UI state, route choice, active-support shop
exit candidate, Telegram send/edit/delete target and response IDs, error
description, button labels, and native outbox completion. ContextVar carries
update/message correlation across normal async handlers. Outbox IDs link its
independent worker. Files: CRM `.local/pilot-events.jsonl`; older lightweight
`.local/pilot-http.jsonl` remains. Emails, long personal numbers, recognizable
credentials and URLs are masked; access links/headers are omitted. Native IDs
are private and necessary for correlation. This is not universal PII detection.

The journal is disabled outside explicit pilot flags, best-effort, and must not
break a request on write failure. Logging does not add model calls, alter route
choices, change user-facing answers or remove menus. Unit profile118 passed;
full Windows413 passed /same2 platform failures /38 subtests. Real MySQL delivery
profile6 passed. Full application startup construction passed before restart.
No new paid Hubris replay was run in this step.

After both captures, with no in-flight AI request, only the CRM bot/support
processes were restarted for instrumentation. API/Qdrant/index/KB/old RAG state
were untouched. New source receipts:73 files each, no mismatches; baseline Git
commit plus an explicit local uncommitted tracing delta. One polling process,
getUpdates200 and CRM health200 confirmed. Current process IDs are in private
`tracing_runtime_final.json`; do not use the previous runtime_final.json as current.

## Next controlled owner test

[Eight test messages and UI check](probes.md). Send one at a time and wait for
the answer; do not chain a repeated message while the previous one is processing.
The same weak baseline remains deliberately available with complete next-run
ingress/UI correlation. Next implementation priorities: affirmative shop exits
and consultation precedence in the existing router; shared menu lifecycle and
reduced history repetition; then symptom extraction/readiness on the same saved
case with independent paraphrases. Do not reindex KB or change the model based
on these pre-retrieval failures. Candidate/production quality remains NO-GO.


Verification artifacts: [trace profile](trace_tests.txt), [full Windows units](crm_unit.txt),
[native MySQL delivery](delivery_tests.txt). Final seven privacy/pilot tests also
passed after adding completion timestamps/defensive response parsing. Final
tracing runtime: CRM support6844, one bot15364;73/73 hashes match, health200,
getUpdates200. Base commitd5f4c70 plus local tracing delta; no commit/push in this
step. RAG API remains its earlier process/code/state. Routing/answer/UI behavior
remains the captured failing baseline for the controlled comparison.
