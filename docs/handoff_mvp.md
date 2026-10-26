# Support-RAG-Bot: isolated specialist handoff MVP

Date: 2026-10-26. Scope: isolated branch/worktree `codex/support-rag-handoff-mvp`, based on `b99348a`. This is an offline integration prototype. The real Telegram adapter is present but no staff chat is approved, no production environment was configured, and no Telegram message was sent.

## Flow

1. The existing `sp:ask:<answer_id>` callback or a bounded model-free direct request such as “Позови специалиста” asks for confirmation. The direct request route runs before Understanding/LLM and is available in free dialogue.
2. Existing `ConversationStore.support_request()` creates/reuses the existing local request. Only its `saved`/`delivered` states can be packaged; cancellation and pending confirmation cannot be sent.
3. `ConversationStore.handoff_bundle()` builds a read-only packet bound to the request owner and conversation. `ticket_id` is derived from the existing request row (`SR-0000001` style), not from a new sequence or external system.
4. `HandoffService` renders the packet and writes `pending` to the isolated `.local/handoff_outbox.json` sidecar. It calls the injected transport only when `HANDOFF_ENABLED=true`, a Telegram bot token is present, and a numeric `TELEGRAM_SPECIALIST_CHAT_ID` is explicitly configured.
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

Facts are included only when existing reducer state supplies a client quote. Message history is bounded to the last eight task messages plus the question/answer attached to the request. No Telegram user ID or chat ID is included in the staff message. When a future ProgressLedger is injected via `progress_provider(conversation_id, task_id)`, its returned check/result summary is added under “Результаты проверок”; the current base revision has no ProgressLedger, so integration with its concrete API remains pending.

## Settings required for a separately approved connection

| Setting | Requirement |
|---|---|
| `HANDOFF_ENABLED` | `true` only after the staff chat and operating procedure are agreed; otherwise unset/false. |
| `TELEGRAM_BOT_TOKEN` | Existing bot token supplied by secret management; never commit it. |
| `TELEGRAM_SPECIALIST_CHAT_ID` | Numeric ID of the specifically approved staff group; do not guess or substitute an example ID. |
| `HANDOFF_STATE_PATH` | Optional durable sidecar location, default `.local/handoff_outbox.json`; writable and backed up under the approved retention policy. |

Before enabling: approve the destination chat and recipient membership; test the bot's permission to post there; agree what conversation content can be shared and its retention; choose and protect the outbox path; verify only one bot worker uses the same outbox; then run a user-approved, bounded acceptance send. Those actions are not part of this MVP.

## Status and retry limits

The existing SQLite request/event tables are unchanged. Handoff states `pending`, `delivered`, and `failed` live in the sidecar and do not rewrite existing `support_requests.status` or `escalation_events`. The sidecar is ignored by Git. This avoids migrating or altering the current production SQLite schema.

The outbox serializes calls within one bot process and persists ticket status across restarts. It is not a multi-process lock. Telegram Bot API does not provide an idempotency key for `sendMessage`; if Telegram accepted a message but the response was lost, the status is `failed` and an explicit retry may produce a duplicate. The adapter does not auto-retry. Keep a single worker and have staff deduplicate by `ticket_id` until a transport with server-side idempotency is available. A `pending` entry after a hard process crash must be reviewed before explicit retry.

Direct-request recognition is a small bounded Russian phrase matcher (for example, “Позови специалиста” or “Хочу поговорить со специалистом”), not a general intent classifier; button confirmation remains available. It binds the new request to the latest completed answer in the active free conversation. No request is created if the conversation has no completed answer.

## Verification in this worktree

- `python -m pytest -q tests/test_handoff.py tests/test_support_feedback.py tests/test_telegram_pilot_sqlite_replay.py::test_p0_gate_d1_d3_through_bot_sqlite`: 16 passed.
- `python -m py_compile app/handoff.py app/conversation_store.py bot.py`: passed.
- Full `python -m pytest -q`: 413 passed, 6 xfailed, 2 failed because this clean worktree lacks the ignored private fixture `data/evaluations/ab_candidate_2026-10-23.jsonl` and the optional `langgraph` package under `.local/vnext-deps`. These are environment-dependent existing tests; no fixture or dependency was copied/installed as part of handoff work.
- All transport tests use a fake transport and temporary sidecars. No network requests, real Telegram sends, worker restart, production SQLite access, `.env`, Qdrant, or KB writes were made.

## Readiness

**Offline MVP: ready for code review. Safe Telegram connection: not ready.** Remaining gate is explicit staff-chat approval plus destination/token/permissions and retention decisions, followed by an authorized bounded acceptance send and operational verification. P1 remains in progress and is not changed by this parallel isolated work.
