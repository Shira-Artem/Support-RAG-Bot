# P1 handoff + ProgressLedger integration readiness

Date: 2026-10-26. Local integration worktree: `C:\Users\Shira\.codex\worktrees\support-rag-handoff-integration\Rag`, branch `codex/support-rag-handoff-integration`, based on current `main` SHA `a606121f518cc5ffd1d3d3a0e860799df8ae2c49`. `origin/main` and merge-base were the same SHA at inspection. No merge, commit or push was performed. The source MVP is `codex/support-rag-handoff-mvp`, implementation SHA `6ed4015edbf33dc43948ee9aa474bb9075bde604`, source branch tip `f257ab56697cf98d73da8a74889bf4bce2272d8d`.

## Final exact E2E trace

All turns ran through real `bot.handle_message` in a temporary SQLite database. The test closes/reopens the persisted dialogue state between turns and injects only a fake Telegram transport.

| Turn | Client input | Result in reducer / route |
|---|---|---|
| 1 | «Эвотор, чеки не уходят» | New technical task; approved source selected and a verified initial check is shown. |
| 2 | «Интернет работает» | Exact client quote recorded; check = `passed`. |
| 3 | «Оплата прошла» | Exact client quote recorded; payment check = `passed`. The separate negative test still proves «Оплату проверил» without an outcome remains `unknown`. |
| 4 | «Что дальше?» with no equipment model in reducer state | Route `progress_ledger_waiting_for_model`; results remain persisted, and the model-specific menu is not emitted. |
| 5 | «Что дальше?» again, still no model | Progress remains saved; no repeated model question or model-dependent UI instruction is sent. |
| 6 | «Модель Эвотор 5i» | Reducer records the explicit equipment fact; task and prior check results survive SQLite reopen. |
| 7 | «Что дальше?» | Route `progress_ledger_next_approved_check`; exact next answer: «2. На модели 5, 5i, 7.2, 7.3, 10 или Power под администратором откройте „Настройки → Обслуживание кассы → Диагностика → Диагностический отчёт“.\n\nИсточник: data/knowledge/evotor/ofd/ofd-unable-to-connect.md — Безопасные проверки». Step 3 is not exposed yet. |
| 8 | «Позови специалиста» | Routed before Understanding/Groq. Exact prompt: «Сохранить заявку специалисту по последнему вопросу и ответу?» |
| 9 | Confirm callback | Fake transport returns matching chat/message receipt. Exact client reply: «Заявка SR-0000001-26BA740F: Telegram подтвердил отправку специалистам.» A second confirm produces no second send. |
| 10 | «Другой вопрос: где найти банковскую выписку в 1С?» | New task ID, empty checks; old task results remain attached to the prior task. Old task handoff does not include later-task messages. |
| 11 | «Спасибо, всё решено» | Current task is marked closed; no diagnostic restart. |

Further E2E branches: with missing specialist chat ID, callback reports the chat is not configured and fake transport call count stays zero. A failure persists across service restart, does not auto-send, and only an explicit retry callback with a transport can deliver. A service with no transport also fails honestly. Mismatched approved/chat IDs are blocked before transport.

## Exact changes in this worktree

- `app/handoff.py` (new): default-off handoff service; independently approved destination check (`HANDOFF_APPROVED_CHAT_ID` must match `TELEGRAM_SPECIALIST_CHAT_ID`); receipt verification; single-process serialized outbox; no silent retry; email/phone masking across outgoing fields.
- `app/conversation_store.py`: read-only `progress_summary(conversation_id, task_id)` with strict persisted task check; ticket ID includes request ID and short hash of conversation/task; packet history limited to answer snapshots with the same reducer task ID. No SQLite schema or production DB change.
- `bot.py`: direct specialist request before model calls; confirmation/retry callback; ProgressLedger provider wiring; honest delivery and recipient error replies. Existing semantic/source-first flags and routing remain intact.
- `app/source_first_service.py`: chooses the next not-yet-shown numbered item only from the exact reverified approved section when the latest shown step was `passed`; generic source-derived model scope must match reducer-confirmed equipment. Unknown scope asks once; mismatch fails closed. Check identity is bound to the model, and shown never means performed.
- `app/dialogue_state.py` and `app/conversation_store.py`: model-specific check results are ignored after a model switch and excluded from the handoff projection for a different current model; general results remain.
- `tests/test_handoff.py`: task isolation, contact redaction with diagnostic context preserved, recipient allowlist, pending crash/restart, timeout/manual retry, delivery receipt, duplicate, task-bound read-only provider.
- `tests/test_telegram_pilot_sqlite_replay.py`: combined real bot/SQLite E2E, reopen, next approved check, direct no-Groq request, fake delivery, repeat, topic transition/close, no-chat/no-transport failures.
- `docs/handoff_mvp.md`, this report, and current v0.3/master/state docs updated in place. No new plan version was created.

`git diff --check` passed. `py_compile` for `app/handoff.py`, `app/conversation_store.py`, `app/source_first_service.py`, and `bot.py` passed.

## Final model-scope review

The earlier integration E2E version was insufficient evidence for the unknown-model claim: its fixture explicitly sent `Модель Эвотор 5i` before requesting the next step. That run demonstrated the suitable-model path only. Separately, review found a real contract gap in the shortcut: after seeing a prior `passed` check it selected the first unseen unit from the entire approved section, without checking `state.expected`, confirmed equipment, or that unit's own model applicability. The D2 waiting path usually intercepted the four-turn unknown-model replay, but the shortcut had no independent fail-closed guard.

The corrected flow tags explicitly model-restricted units using generic source wording and requires a match to reducer-confirmed equipment before rendering. Unknown models retain the existing manufacturer/model gate and results; repeated follow-up does not ask again. Unsupported models receive a safe not-applicable response. Model-specific check IDs include the confirmed model, and reducer/handoff projections ignore old model-scoped checks after a model switch. The prior general missing-model gate remains as an additional safety condition; removing it during an intermediate attempt caused safety case S2 to return an answer from the FN 234 document for a different error context. Restoring that gate made S2 pass again.

New real `bot.handle_message` + SQLite close/reopen coverage verifies unknown model, suitable `5i`, unsupported `X500`, model switch `5i → X500`, result retention, and one-time model clarification. The previous combined test did not demonstrate the reported unknown-model violation, but the shortcut lacked the required defense. D2.3 remains strict xfail; no D2 contract or safety gate was relaxed.

## Environment and regression results

The initial suite in the clean integration worktree reported `436 passed, 5 xfailed, 2 failed`. The two failures were reproduced as environment blockers: the ignored fixture `data/evaluations/ab_candidate_2026-10-23.jsonl` was absent in this worktree, and system Python 3.14 could not import the existing local LangGraph dependency because of a Pydantic core ABI mismatch. Neither failure was hidden, skipped or xfailed.

For the comparable run, used the existing Python 3.12.2 virtualenv from the main checkout, the already-present ignored fixture through a temporary junction to its directory, and `langgraph` plus dependencies in an isolated temporary dependency directory via `PYTHONPATH`. The fixture contents were not read or copied. The junction and environment override were removed/restored in `finally`.

- Targeted final suite: `python -m pytest -q --tb=short tests/test_telegram_pilot_sqlite_replay.py tests/test_handoff.py` — **42 passed, 5 xfailed**.
- Full regression after final code and test changes: `python -m pytest -q` — **443 passed, 5 xfailed, 0 failed in 50.40s**.
- Environment failures remaining: **0**. Product regressions: **0 observed**. The earlier environment setup failures are resolved for this run.
- No live Groq or Telegram call, Qdrant access, KB edit, `.env` access/change, worker action, or production SQLite access/write.

## Privacy and delivery review

**Sent to specialist:** ticket ID; escalation reason; task operation/description; reducer-confirmed facts only when accompanied by a client quote; ProgressLedger procedure/check label/status and client quote; and up to eight messages whose persisted answer has the exact task ID, plus the request Q/A. The bot’s instructions are not reducer evidence. The packet does not include raw Telegram user ID, chat ID, conversation ID or task ID. Common emails and phone numbers are masked before send.

**Stored in sidecar:** `pending` and `delivered` entries contain the already-rendered sanitized outgoing payload; `delivered` also stores Telegram message ID. `failed` stores only status and error code, dropping payload. Ticket ID binds request ID to a short conversation/task hash. The sidecar is atomic-write JSON but only guarded within one process and has no retention/access policy enforcement.

**Failure/restart behavior:** before transport call, `pending` is persisted. A normal exception becomes `failed` without payload and never retries automatically; a process crash after remote acceptance but before receipt persistence leaves `pending`. Restart does not resend `pending`. Explicit retry is required. Telegram `sendMessage` has no idempotency key, so when timeout outcome is ambiguous, staff must first reconcile by ticket ID; a manual retry can duplicate a message if Telegram accepted the first send. This policy is documented and simulated offline.

**Recipient protection:** sending is blocked unless destination is numeric and exactly equals an independent numeric `HANDOFF_APPROVED_CHAT_ID`; delivery receipt must also confirm that same destination. No real staff chat was configured or contacted.

**Remaining privacy boundary:** email/phone patterns are masked; arbitrary names, street addresses and other unique details are not generally identifiable by this deterministic masker. Task-bound history filtering prevents cross-topic leakage and preserves useful diagnostic context, but before a live pilot the allowed content, sidecar filesystem permissions and retention period still need explicit review. The offline packet is minimal for the demonstrated case, not a general anonymization guarantee.

## A/B/C/D and gate status

The shared operational plan v0.3 remains the canonical working sequence and preserves earlier evidence: A diagnostic work and provider attempts, B2 `NO-GO` / default-off, C retrieval audit showing four correct documents lost to task/operation filters, and D handoff MVP only offline. This integration does not alter those results, the source plan, selector, retrieval filters, KB or Qdrant.

- Integration offline: **DONE** (443 passed / 5 xfailed / 0 failed; fake transport only; D2 model scope gates reverified).
- Live Telegram: **BLOCKED / not run** (no approved operational recipient/retention decision and no authorization for a real send).
- Production / worker: **NO-GO / unchanged**.
- Commit/push readiness: **GO** based on comparable full suite and safety checks. The user's 2026-10-26 request explicitly authorizes commit/push/merge when these gates pass; the repeated Python 3.12.2 full suite again passed with 443 passed / 5 xfailed / 0 failed.
- Offline merge-candidate readiness: **GO**; no remaining offline test blocker. Stage 1 commit/push/merge is now authorized conditionally by the user request and is pending execution. Main and origin/main remain at `a606121f518cc5ffd1d3d3a0e860799df8ae2c49` at this checkpoint.

Next step: complete the authorized Stage 1 publication/integration gates. Live Telegram and production/worker actions remain separate NO-GO gates.
