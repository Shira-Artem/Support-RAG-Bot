# Regression baseline: DialogueState v1

Date: 2026-10-22. Branch: `fix/rag-p0-dialogue-v2`.

## Scope and reproducibility

- Starting commit: `9bf892be3880b015f1bdaeb76ce9f63385ee3c75` (`main`).
- Python: `3.14.3`; pytest: `9.1.1`.
- The working tree was already dirty before this task. It contained 9 modified tracked files (including DialogueState, query, persistence, answer, retrieval and Telegram runtime code) and additional untracked audit/support artifacts. They were preserved. The branch was created at the starting commit with those existing changes carried into it.
- Therefore measurements below describe the **existing working tree**, not a clean checkout of the starting commit. No pre-existing runtime change was made for this baseline.
- No Groq/OpenRouter API, Telegram, or live SQLite database was used. The new regression fixtures are marked synthetic. Existing offline tests also replay an available seven-turn recorded fixture with a stubbed generator and local knowledge cards.

## Test results

| Command | Result |
|---|---:|
| `python -m pytest -q` before adding this baseline's tests | 139 passed, 0 failed, 0 skipped |
| `python -m pytest -q tests/test_dialogue_state.py tests/test_incident_context.py` | 26 passed, 0 failed, 0 skipped |
| `python -m scripts.trace_dialogue_state` | Completed for all 5 built-in turns; no network or database access |
| `python -m pytest -q tests/test_dialogue_regressions_v2.py` | 5 passed, 7 strict xfailed, 0 unexpected xpass |
| `python -m pytest -q` after adding the regressions | 144 passed, 7 strict xfailed, 0 failed, 0 skipped, 0 unexpected xpass |

The seven expected failures are A–F and the session-to-task leakage invariant in H. G and the other four H checks pass. `strict=True` makes a repaired case fail as XPASS until its marker is intentionally removed. The existing suite's 139 tests all continued to pass.

## Current implementation verified in source

1. `app/dialogue_state.py` has `SCHEMA_VERSION = 1`. `LexicalAnalyzer` creates typed observations using bounded word/phrase vocabularies and source spans. `DialogueManager.advance()` chooses task boundaries with a small set of rules: known intent/operation changes, explicit new-topic prefixes, entity-only updates, requirement refinements, and expected clarification. It has no explicit message-to-task relation enum. Its `different_task` comparison depends on inferred intent/operation; an unknown intent can consequently remain attached to an old task.
2. `DialogueState.entities` are session-level facts. `parameters`, `goals`, `constraints`, `details`, error and object references are stored on the same object and mostly retained until a new task. `task_entities` and `routing_slot` form a projection used to select the active retrieval route; they do not create a distinct `TaskContext` object.
3. Expected clarification is a slot/question/reason written by `observe_answer()` only when the answer scenario is `clarify`. The next user message clears it only when the expected slot is matched (or a known task, entity, goal or constraint arrives). An unrelated message can leave the stale clarification attached.
4. `analysis_required` is set when a non-new message cannot be classified as a known task, entity update, requirement refinement, feedback or reference, or when analyzer marks multiple/uncertain entities. A previous unresolved state can also keep the flag set. `build_rag_query()` rejects this flag; `AnswerService` converts that rejection to an ambiguity clarification, so retrieval does not run.
5. `ConversationStore` stores full JSON snapshots in `dialogue_states` and per-user-turn snapshots in `dialogue_turns`. `_sync_state()` processes complete messages after a cursor and updates snapshots inside the same SQLite write transaction used by `begin()`/`complete()`. It replays legacy complete messages once when no snapshot exists. Assistant messages may establish expected clarification but are not added as client facts. Unknown snapshot versions raise `ValueError` without overwriting the stored JSON.
6. Consumers include Telegram `bot.py` (SQLite state passed to `AnswerService`), `cli_test.py` (one in-memory manager/state), `AnswerService` plus stateless `history=` compatibility, retrieval filters in `retrieval_pipeline.py`, query building in `rag_query.py`, diagnostics in `scripts/trace_dialogue_state.py` and `scripts/replay_incident.py`, and answer diagnostics persisted by `ConversationStore`. The expert workflow has its own `ExpertStore`; isolated expert requests do not use the free-chat state.
7. On restart, `ConversationStore.dialogue_state()` loads the latest JSON snapshot, replays only complete unseen messages after `processed_message_id`, and stores the updated snapshot. Pending assistant messages stop advancement; `recover_pending()` completes them with an interruption answer. A new conversation gets a new ID and no state snapshot.

## Reproduced target cases

The added fixtures are **synthetic reconstructions of the task's examples**, not historical customer quotations. The available recorded seven-turn fixture was already exercised by `test_incident_context.py`; its message text is not copied into this report.

| Case | Preceding task / expected clarification | Actual v1 result | Transition, route, ID, analysis | RAG query / target | Baseline |
|---|---|---|---|---|---|
| A: Platforma OFD receipt search; “only FN number” | `receipt/search`; no expected slot | Follow-up is classified `fiscal_drive/search`; FN mention becomes a parameter. The receipt object is lost. | `new_task`; route becomes null; task ID changes from `task:1` to `task:2`; `analysis_required=false`. | Query becomes a fiscal-drive search with “по нему”, not a receipt search. Target keeps receipt search, OFD service and FN parameter. | XFAIL |
| B: aQsi password recovery; email unavailable, then phone unavailable | `credentials/reset_password`; synthetic `details` clarification | Both turns retain `credentials/reset_password` and the original task ID, but relation is unresolved. | `continue_task`; aQsi route and ID stay; `analysis_required=true`; expected details is not satisfied by grounded facts. | `build_rag_query()` raises `QueryNeedsClarification`; retrieval is blocked. Target continues recovery and retrieves on both turns. | XFAIL |
| C: ATOL reports; requested section absent | `report/view_reports`; synthetic `details` clarification | Task fields and ID are retained, but no contradiction relation is modeled. | `continue_task`; ATOL route and ID stay; `analysis_required=true`. | Query builder raises and retrieval is blocked. Target retains report task as a contradiction and enables diagnosis/escalation. | XFAIL |
| D: TS PiOT equipment clarification, then missing documents to OFD | Old task has expected `equipment` | New message does not classify as a new task; old task and expected equipment slot remain. | `clarification`; old task ID and stale expected slot; `analysis_required=false`. | Query remains “service: ТС ПиОТ — ТС ПиОТ, какая модель оборудования?”. Target creates an OFD-document task and clears old TS PiOT context. | XFAIL |
| E: 1C bank statements, then list of statements | `unknown/check`; no expected slot | Neither message gets a bank-statement intent; second turn is unresolved. | `continue_task`; same ID; `analysis_required=true`; route sees 1C as software. | Query builder raises. Target recognizes and continues bank-statement task. | XFAIL |
| F: Evotor 6 reprint an old receipt by FD | No prior task | Receipt is extracted, but “повторно распечатать” is not a supported operation. | `new_task`; Evotor route; operation `unknown`; `analysis_required=false`. | Query falls back to original text; target operation `repeat_print` must be typed and represented for retrieval. | XFAIL |
| G: switch employee-access task from aQsi to ATOL | `access/add_employee`, with viewing goal and no-settings constraint | Goals and constraints remain, task ID is stable, active route changes to ATOL. | `change_service`; same `task:1`; `analysis_required=false`. | Query uses ATOL and does not include aQsi. This switch is already working in the current tree. | PASS |

The exact assertions and strict xfail reasons are in `tests/test_dialogue_regressions_v2.py`; the synthetic inputs and desired outcomes are in `tests/fixtures/dialogue_regressions_v2.json`.

Exact final-turn query/state trace from the current worktree:

| Case | Intent / operation; transition; route; task ID; analysis / expected | Actual RAG query |
|---|---|---|
| A | `fiscal_drive/search`; `new_task`; route none; `task:2`; false / none | `ОФД: Платформа ОФД — поиск ФН — ограничения: только номер ФН кассы — параметры текущего поиска: по нему` |
| B | `credentials/reset_password`; `continue_task`; aQsi; `task:1`; true / none | blocked: `Message relationship is unresolved` |
| C | `report/view_reports`; `continue_task`; ATOL; `task:1`; true / none | blocked: `Message relationship is unresolved` |
| D | `unknown/unknown`; `clarification`; TS PiOT; `task:1`; false / equipment | `сервис: ТС ПиОТ — ТС ПиОТ, какая модель оборудования?` |
| E | `unknown/check`; `continue_task`; 1C; `task:1`; true / none | blocked: `Message relationship is unresolved` |
| F | `receipt/unknown`; `new_task`; Evotor; `task:1`; false / none | `оборудование: Эвотор 6 — производитель: Эвотор — Эвотор 6, как повторно распечатать старый чек по номеру ФД?` |
| G | `access/add_employee`; `change_service`; ATOL; `task:1`; false / none | `сервис: АТОЛ Онлайн — добавление сотрудника — цель: добавить сотрудника для просмотра касс — ограничения: без права менять настройки` |

## Main failure locations

- Task relation and task boundary: `app/dialogue_state.py`, `LexicalAnalyzer.analyze()` and `DialogueManager.advance()`. In particular, operation/object vocabulary and `different_task`/`new` rules cannot express contradiction, answer-to-clarification or a confidently new subject with unknown intent.
- Clarification and ambiguity gate: `DialogueManager.advance()` and `observe_answer()` in `app/dialogue_state.py`; `build_rag_query()` rejects every `analysis_required` state in `app/rag_query.py`; `AnswerService.answer()` turns that into a clarification before retrieval.
- Task parameters and route projection: `DialogueState.task_entities`, `routing_service`, `routing_slot` and `task_entities` in `app/dialogue_state.py`; query construction in `app/rag_query.py`; scoped service selection in `app/retrieval_pipeline.py`.
- Persistence is functioning for the tested v1 paths. The risk for v2 is compatibility: `DialogueState.from_dict()` rejects all versions other than 1, while `ConversationStore._sync_state()` assumes it can deserialize the current snapshot before processing unseen messages.

## Diagnostic limits

The lexical trace measures deterministic state and query construction. The offline replay uses local cards, a lexical candidate search and recorded/stubbed generation. Neither proves semantic classification quality, current production SQLite health, dense retrieval quality, or response quality from a live model. No secrets or personal identifiers were added to the new fixtures or report.
