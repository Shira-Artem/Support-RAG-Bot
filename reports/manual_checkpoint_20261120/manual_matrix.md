# Матрица ручных диалогов 19–20.11.2026

PASS: полезный ответ/необходимое уточнение; PARTIAL: продвижение с неполнотой; FAIL: отказ, потеря цели, повтор известного или неподтверждённое существенное утверждение. Это редакционная оценка наблюдаемого ответа, не независимая сертификация фактов.

| Ход | MSK | Оценка | Компонент | Подтверждённая причина / ограничение |
|---|---|---|---|---|
| M01 | 2026-11-19 15:09:49 | FAIL | Transport | Empty pending answer; telegram_delivery_failed. Delivery timing is not recoverable. |
| M02 | 2026-11-19 15:17:28 | FAIL | Selector | semantic_selector_failed_closed; SelectorDecisionError. No useful answer. |
| M03 | 2026-11-19 16:02:40 | PARTIAL | General conversation | Core explanation useful, but unsupported onboarding sufficiency claim (all that is needed) and unsolicited connection advice. |
| M04 | 2026-11-19 17:22:04 | PASS | General conversation | Direct explanation of cash register/FN/OFD; no technical procedure. |
| M05 | 2026-11-19 17:22:59 | FAIL | Conversation context/output validation | Useful raw explanation rejected by current-turn lexical relevance; active subject absent from model prompt. |
| M06 | 2026-11-19 17:24:18 | PASS | General conversation | Explains OFD and payment purpose. Additional generic service claims are not independently verified. |
| M07 | 2026-11-19 17:24:33 | PARTIAL | General conversation | Answers the repeated user message; guarantees about avoiding accounting errors are unsupported. |
| M08 | 2026-11-19 17:25:14 | FAIL | General knowledge grounding | Published unsupported claim that receipts lose legal force. One sentence removed but equivalent claim retained. |
| M09 | 2026-11-19 17:25:56 | FAIL | Planner/source order | Approved diagnostic section found; Planner source_order_complete=False; fail-closed refusal. |
| M10 | 2026-11-19 17:26:53 | FAIL | Task/retrieval projection | Payment-mentioned receipt incident projected to billing; receipt/integration evidence rejected as task mismatch. |
| M11 | 2026-11-19 17:30:37 | FAIL | Task/retrieval projection | Same request still projected to billing; no_task_matched_candidates. |
| M12 | 2026-11-20 10:22:05 | FAIL | Understanding/resolver | Raw operation=status; resolver reported_error from bare FN number overrides to diagnose; no symptom triggers clarification. |
| M13 | 2026-11-20 10:24:38 | FAIL | DialogueState/readiness | Expiry question does not advance; equipment clarification, prior goal not fulfilled. |
| M14 | 2026-11-20 10:24:58 | PARTIAL | Scope clarification | Manufacturer/model clarification is safe, but no explanation of expiry. |
| M15 | 2026-11-20 10:25:11 | FAIL | Selector/scope | Asks service for FN expiry conversation; semantic_selector_clarification. |
| M16 | 2026-11-20 10:26:20 | FAIL | Composer/relevance | Approved bank evidence retrieved; composer unsupported_information_claim, exact fallback then semantic relevance rejected. |
| M17 | 2026-11-20 10:26:49 | PARTIAL | SourceFirst unit rendering | Only menu path emitted; diagnostic report action in following numbered item withheld. |
| M18 | 2026-11-20 10:27:27 | FAIL | Progress ledger | Unrelated reported checks retained but expected result of menu-navigation unit unresolved; asks for completion. |
| M19 | 2026-11-20 10:27:52 | FAIL | Continuation/intake | Request to explain current action becomes progress_result_unresolved escalation; no helpful re-explanation. |
| M20 | 2026-11-20 10:28:28 | PARTIAL | General conversation | Core OFD explanation present; wording that OFD takes documents from FN is imprecise; no source validation. |
| M21 | 2026-11-20 10:28:47 | FAIL | General knowledge grounding | Published unsupported equivalence: unpaid OFD makes receipts nonfiscal; unsupported penalty claim. |
| M22 | 2026-11-20 10:29:08 | PASS | Intake | Reasonable manufacturer clarification for vague register malfunction; no invented instruction. |
| M23 | 2026-11-20 10:29:17 | PARTIAL | Intake | Asks model/error safely; references missing service despite unresolved symptom. |
| M24 | 2026-11-20 10:29:30 | FAIL | Error-code applicability/intake | Explicit printing symptom saved, but unknown-code template asks again whether printing or transmission failed. |
