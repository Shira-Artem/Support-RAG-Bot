# Support-RAG-Bot: isolated specialist handoff MVP

Date: 2026-10-26. Scope: isolated branch/worktree `codex/support-rag-handoff-mvp`, based on `b99348a`. This is an offline integration prototype. The real Telegram adapter is present but no staff chat is approved, no production environment was configured, and no Telegram message was sent.

## Flow

1. The existing `sp:ask:<answer_id>` callback or a bounded model-free direct request such as “Позови специалиста” asks for confirmation. The direct request route runs before Understanding/LLM and is available in free dialogue.
2. Existing `ConversationStore.support_request()` creates/reuses the existing local request. Only its `saved`/`delivered` states can be packaged; cancellation and pending confirmation cannot be sent.
3. `ConversationStore.handoff_bundle()` builds a read-only packet bound to the request owner, conversation, and reducer task. `ticket_id` includes the existing request id plus a short conversation/task binding hash.
4. `HandoffService` renders the packet and writes `pending` to the isolated `.local/handoff_outbox.json` sidecar. It calls the injected transport only when `HANDOFF_ENABLED=true`, a Telegram bot token is present, and numeric `TELEGRAM_SPECIALIST_CHAT_ID` exactly matches the independently configured numeric `HANDOFF_APPROVED_CHAT_ID`.
5. Delivery becomes `delivered` only after the transport returns a Telegram message receipt with a message ID and the configured destination chat ID. API exceptions, non-confirming receipts, or missing configuration become `failed`. The bot tells the requester that the specialist is not notified unless the send is confirmed.
6. A repeated confirm is idempotent. Failed delivery does not resend on another confirm; the explicit “Повторить отправку” callback retries only when handoff settings are ready.

```text
user confirm → existing saved support request → handoff bundle → sidecar pending
                                                     ↓ configured + enabled
                                            Telegram Bot API send
                                  ┌──────────────────┴─────────────────┐
                           verified receipt                       error / unclear
                             delivered                               failed
```

## Handoff packet

```json
{
  "ticket_id": "SR-0000001",
  "task": {"task_id": "...", "intent": "...", "operation": "...", "object": "...", "task": "..."},
  "confirmed_facts": [{"scope": "task", "slot": "manufacturer", "value": "...", "quote": "..."}],
  "messages": [{"role": "user", "text": "..."}, {"role": "assistant", "text": "..."}],
  "escalation_reason": "insufficient_knowledge",
  "diagnostic_summary": {"scenario": "...", "reason": "..."}
}
```

Facts are included only when existing reducer state supplies a client quote. Message history is bounded to the last eight messages whose persisted answer snapshot has the same reducer task ID, plus the question/answer attached to the request. A later or unrelated task in the same conversation is excluded. No Telegram user ID, chat ID, conversation ID or task ID is included in the staff message. `ConversationStore.progress_summary(conversation_id, task_id)` is injected read-only; it validates both IDs against the persisted snapshot and returns only procedure/check label/status/client result quote; it does not replay or write reducer state. Common email/phone patterns are redacted from task, facts, results and the bounded message tail. This is limited contact masking, not general anonymization of names/addresses. See the [P1 integration report](../experiments/architecture_recovery_audit/p1_handoff_integration_20261026.md). Candidate remains local/unpublished; no live Telegram send or worker change occurred.

## Settings required for a separately approved connection

| Setting | Requirement |
|---|---|
| `HANDOFF_ENABLED` | `true` only after the staff chat and operating procedure are agreed; otherwise unset/false. |
| `TELEGRAM_BOT_TOKEN` | Existing bot token supplied by secret management; never commit it. |
| `TELEGRAM_SPECIALIST_CHAT_ID` | Numeric ID of the specifically approved staff group; do not guess or substitute an example ID. |
| `HANDOFF_APPROVED_CHAT_ID` | Numeric independently approved destination. Must exactly match `TELEGRAM_SPECIALIST_CHAT_ID`; mismatch blocks transport. |
| `HANDOFF_STATE_PATH` | Optional durable sidecar location, default `.local/handoff_outbox.json`; writable and backed up under the approved retention policy. |

Before enabling: approve the destination chat and recipient membership; test the bot's permission to post there; agree what conversation content can be shared and its retention; choose and protect the outbox path; verify only one bot worker uses the same outbox; then run a user-approved, bounded acceptance send. Those actions are not part of this MVP.

## Status and retry limits

The existing SQLite request/event tables are unchanged. Handoff states `pending`, `delivered`, and `failed` live in the sidecar and do not rewrite existing `support_requests.status` or `escalation_events`. The sidecar is ignored by Git. This avoids migrating or altering the current production SQLite schema.

The outbox serializes calls within one bot process and persists ticket status across restarts. It is not a multi-process lock. Telegram Bot API does not provide an idempotency key for `sendMessage`; if Telegram accepted a message but the response was lost, the status is `failed` and an explicit retry may produce a duplicate. The adapter does not auto-retry. Keep a single worker and have staff deduplicate by `ticket_id` until a transport with server-side idempotency is available. A `pending` entry after a hard process crash must be reviewed before explicit retry.

Direct-request recognition is a small bounded Russian phrase matcher (for example, “Позови специалиста” or “Хочу поговорить со специалистом”), not a general intent classifier; button confirmation remains available. It binds the new request to the latest completed answer in the active free conversation. No request is created if the conversation has no completed answer.

## Verification in this worktree

- `python -m pytest -q tests/test_handoff.py tests/test_support_feedback.py tests/test_telegram_pilot_sqlite_replay.py::test_p0_gate_d1_d3_through_bot_sqlite`: 16 passed.
- `python -m py_compile app/handoff.py app/conversation_store.py bot.py`: passed.
- Original MVP full-suite run: 413 passed, 6 xfailed, 2 failed because that worktree lacked the ignored private fixture and optional `langgraph`; this historical result is superseded for integration readiness by the comparable-environment full suite in the [P1 integration report](../experiments/architecture_recovery_audit/p1_handoff_integration_20261026.md).
- All transport tests use a fake transport and temporary sidecars. No network requests, real Telegram sends, worker restart, production SQLite access, `.env`, Qdrant, or KB writes were made.

## Readiness

**Offline MVP and integrated ProgressLedger candidate: offline tests pass. Safe Telegram connection: not ready.** After the final D2 model-scope audit, the comparable-environment suite is 443 passed / 5 xfailed / 0 failed. The combined E2E now blocks unknown and unsupported models and rechecks applicability after a model switch. Remaining live gates are explicit staff-chat approval, destination/token/permissions and retention decisions, followed by separately authorized bounded acceptance send and operational verification. P1 remains in progress; main is unchanged by this local integration candidate. See the [final model-scope audit](../experiments/architecture_recovery_audit/p1_handoff_integration_20261026.md).
