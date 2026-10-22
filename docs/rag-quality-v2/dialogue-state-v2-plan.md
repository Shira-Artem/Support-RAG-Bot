# DialogueState v2 migration and implementation status

Core state, reducer, query projection, and additive SQLite migration are implemented in this branch. This document retains the broader rollout plan; items outside the Step 2 scope remain follow-up work. See [implementation.md](implementation.md) for the implemented behavior and verification results.

## Proposed state model

```text
DialogueState (schema_version = 2, revision, active_task_id)
├── SessionContext
│   ├── entities: map[slot, list[Fact]]
│   └── session metadata (conversation identity / timestamps as needed)
└── TaskContext | null
    ├── task_id, status (active | pending | complete | cancelled)
    ├── active_route: {slot, value, source_fact_id}
    ├── intent, operation, object, task statement
    ├── parameters, goals, constraints, details, errors, object references
    ├── expected_clarification
    └── last_relation and provenance
```

Keep a compatibility facade for current `state.intent`, `state.operation`, `state.entities`, `state.parameters`, `state.routing_service`, `state.task_id`, `state.expected`, and `state.analysis_required` reads during staged adoption. New internal code should use explicit `session` and `task` properties. A missing active task is valid; do not fill it from session facts without a user message grounding that assignment.

Every `Fact` should preserve its original `message_id`, exact `quote`, `start`, `end`, and normalized typed value. Add an origin/actor field for client, system import, or assistant metadata only if needed for non-fact metadata. Assistant output must never be promoted to a confirmed user fact. Facts imported from v1 must be marked with migration provenance and retain the original v1 snapshot reference; inferred facts must not be fabricated to fill new slots.

## Message relation and reducer

Classify each incoming user message to one of:

`new_task`, `continue`, `parameter_update`, `constraint_update`, `contradiction`, `answer_to_clarification`, `unknown`.

The analyzer returns a proposed relation plus typed facts and cited spans from the current user message. A deterministic reducer validates provenance, then applies relation-specific behavior:

- `new_task`: allocate a new task ID; mark/close the prior task by policy; clear task-local parameters, constraints, goals, details, errors, references and expected clarification. Preserve session entities only in `SessionContext`.
- `continue`: keep the task and route; attach only explicitly grounded facts.
- `parameter_update` / `constraint_update`: update only the corresponding task field; retain the action, object, requirements and task ID.
- `contradiction`: retain the task and source claim, record the user correction as a new cited fact, mark incompatible old assertion as superseded rather than silently deleting it, and permit diagnostic/escalation retrieval.
- `answer_to_clarification`: accept a value only if it cites the current user turn and matches the expected slot; close that clarification. A non-answer does not silently satisfy the slot.
- `unknown`: preserve the prior task without mutating its facts, then ask a relation question. Do not route retrieval on a guessed task.

Represent clarification lifecycle explicitly (`open`, `answered`, `cancelled`, `expired`) and bind it to `task_id`, slot, and originating assistant message. On a new task, cancel old open clarifications. A late answer to a cancelled task must not mutate the active task; ask which task it refers to or reopen it explicitly.

## Active route and product boundaries

Make `active_route` an explicit task-owned choice with its supporting fact. Keep all service/manufacturer/equipment/OFD/software facts available in session context, but choose retrieval filters only from the active task's route and route-compatible facts. A route switch updates that task's active route and retains task goals and restrictions. Query construction must not include the previous route's name merely because it appears in the original task text; compose from typed fields and selected cited facts.

Build typed intent/operation coverage incrementally from measured regressions. At minimum add statement-list and repeat-print operations, document transmission/search cases, and receipt-search argument handling. Do not solve missing coverage by changing KB metadata, retrieval ranking, chunking, embeddings, prompts, validator, or knowledge documents in this task.

## Compatibility consumers

1. **ConversationStore / SQLite:** versioned serializer/deserializer, snapshot cursor, per-turn snapshots, pending recovery, and history replay.
2. **Telegram:** keep `begin → state → AnswerService → complete` semantics; pass a typed TaskContext-derived query/routing projection. Ensure new-chat/reset obtains a new conversation ID and never inherits the previous task.
3. **CLI:** use the same analyzer/reducer, observe assistant clarifications as metadata, expose explicit new-task behavior.
4. **AnswerService and stateless `history=` adapter:** accept v2 state and provide a v1-compatible facade while older callers remain. Clarification/gating must distinguish unresolved relation from missing retrieval context.
5. **RetrievalPipeline:** consume only the explicit task route and task facts; no implicit merge of every session entity.
6. **Expert mode:** retain its isolated workflow and do not attach a free-chat TaskContext unless intentionally requested.
7. **Diagnostics, exports, tests:** version their JSON output, redact user data, and retain traceability to source message IDs.

Before changing each consumer, add adapter contract tests. Avoid changing Telegram UI in the state migration itself.

## SQLite migration with preservation guarantees

Old SQLite data must never be dropped, overwritten, or silently reset. Use an additive, resumable migration:

1. **Inventory and backup.** On a closed/stopped writer, use SQLite's online backup API (or a verified filesystem backup when the app is stopped). Record DB path, SQLite version, schema, table/row counts and a backup checksum. Never use a lossy export as the only backup.
2. **Add v2 tables/columns.** Create a migration journal and a new v2 snapshot table (or a versioned snapshot table) with conversation ID, v2 JSON, processed-message cursor, source version, migration status and timestamp. Keep `messages`, `dialogue_states` v1 JSON and `dialogue_turns` unchanged.
3. **Copy, do not mutate.** For each conversation, read the raw v1 payload and preserve it verbatim in a backup/archive table or durable migration record. Convert only recognized schema 1 payloads. Store the v2 snapshot alongside it. Do not delete the v1 record after success.
4. **Unknown or corrupt payloads.** Leave their raw bytes untouched, record migration status `blocked_unknown_version` / `blocked_invalid_payload`, and prevent writes to that conversation until explicit recovery. Never substitute an empty state. Unknown versions remain inspectable and exportable.
5. **Idempotent batches.** Migrate in bounded batches with a transaction per batch, source payload hash and cursor. Re-running a completed batch must be a no-op. Keep write transactions short; never call a network LLM or retrieval provider from inside a SQLite transaction.
6. **Validate before activation.** Compare source/migrated conversation counts, cursor positions, message IDs, fact provenance and task identifiers where representable; run `PRAGMA integrity_check` and foreign-key checks; preserve a migration report. Any mismatch blocks cutover and keeps v1 reads available.
7. **Read switch and rollback.** Initially read v2 only for conversations whose migration status is validated; otherwise use v1 compatibility read or show an explicit blocked state. Do not dual-write transformed facts back into v1. Keep a feature flag/rollback window and retain backups and raw snapshots across at least one release cycle.

For any future semantic/LLM analyzer, compute a proposed observation outside the DB transaction using a snapshot revision. Inside a short transaction, compare the current revision/cursor; apply the observation only if still current. On conflict, re-analyze or request clarification. Never hold the SQLite write lock across a network request.

## Implementation sequence and status

1. **Implemented:** relation semantics and explicit session/task state, with a legacy flat-property facade.
2. **Implemented:** v1-to-v2 serialization, additive migration, temporary-DB tests for unknown/corrupt payloads and preservation of source snapshots.
3. **Implemented:** reducer transitions for the synthetic regression matrix and paraphrases; all seven baseline failures now pass.
4. **Partially implemented:** compatibility facade supports current Python consumers and CLI/stateless state paths; broader consumer-by-consumer adapter contracts remain follow-up work.
5. **Implemented in code/tests:** additive SQLite migration and restart/pending recovery coverage. A production backup/restore drill has not run.
6. **Follow-up:** rollout flags and shadow-state deployment validation have not been added here. This change set does not modify Qdrant, retrieval ranking/metadata, Telegram UI, prompts, validation, or knowledge content.
7. **Follow-up:** compare production reports and enable a controlled cohort only after operational backup/rollback procedures are defined.

The implementation does add SQLite tables at runtime but has only been exercised against temporary test databases; it does not rewrite legacy `dialogue_states` rows. No production database, Telegram UI, Qdrant, knowledge, or LLM configuration was changed.
