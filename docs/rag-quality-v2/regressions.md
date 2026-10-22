# DialogueState v2 regression matrix

All new messages in the fixture are synthetic reconstructions from the task brief. They are not represented as historical user messages. No live API, Telegram bot, production database, or Qdrant collection is touched.

## Current status

`python -m pytest -q tests/test_dialogue_regressions_v2.py`: **21 passed**. No expected failures remain. The full suite: **160 passed**. The prior XFAIL state is preserved in [baseline.md](baseline.md).

| ID | Message and previous context | Target relation / state | Query requirement | Current result |
|---|---|---|---|---|
| A | “У меня есть только номер ФН кассы. Получится найти чек напрямую по нему?” after Platforma OFD receipt search | `parameter_update`; retain receipt/search and Platforma OFD; add FN as parameter | Query retains receipt search and FN | PASS: same `task:1`, receipt/search, Platforma OFD, FN parameter |
| B | Email unavailable with phone remaining; then “А если к телефону тоже доступа нет, как теперь войти?” after aQsi password recovery and expected details | Continue credentials/reset-password; close answered stale slot | Follow-up remains retrievable | PASS: same `task:1`, expected slot cleared, access restriction retained |
| C | “В кабинете этого раздела у меня нет. Что делать?” after ATOL reports and expected details | `contradiction`; keep report task and allow diagnosis/escalation | Query retains ATOL report context | PASS: report task retained; no unresolved relation gate |
| D | “Где посмотреть документы, которые не отправились оператору ОФД?” while old TS PiOT task waits for equipment | `new_task`; clear old clarification and task facts | Query contains OFD-document intent; no TS PiOT equipment/service | PASS: `task:2`, no vendor guessed, stale slot cleared |
| E | “А где посмотреть список выписок?” after bank statements in 1C:DirectBank | `continue`; bank statement intent and operation/object retained | Query points to statement list | PASS: `bank_statement/list`, prior 1C route retained |
| F | “Эвотор 6, как повторно распечатать старый чек по номеру ФД?” | New task with `receipt` and `repeat_print` | Query retains repeat-print action and FD argument | PASS: `receipt/repeat_print`, Evотор route and FD parameter |
| G | `АТОЛ Онлайн` during aQsi employee-access task with viewing goal and no-settings limit | `parameter_update` or explicit service switch; same task, preserve requirements, route ATOL | New active product only; no aQsi product source mixed into query | PASS: same task and requirements retained; query uses ATOL only |

## Additional invariants

| Invariant | Offline check | Result |
|---|---|---|
| New independent question resets task facts | New task ID; prior goals, constraints, parameters cleared | PASS |
| Session entity remains available | Entity remains in session state when task resets | PASS |
| Session fact is not auto-bound to a new task | New password-recovery task after an aQsi employee task should have no active route absent a new product fact | PASS |
| Bot clarification does not become a user fact | Only the `expected` clarification changes | PASS |
| New conversation has no prior task | Separate conversation ID in a temporary SQLite file | PASS |
| Save/load and pending recovery | Reload snapshot; recover pending answer; task replayed | PASS |
| Fact provenance | Message ID and exact quote span checked | PASS |
| Ambiguous products do not invent a service | Two competing named products result in no singular service and `analysis_required` | PASS |

`pending/recover/complete` and state round-trip are also covered by existing `tests/test_dialogue_state.py` and `tests/test_conversations.py`. Migration tests use temporary SQLite databases and verify source snapshots/messages remain unchanged, migration is idempotent, unknown versions are archived without rewriting the source, and `PRAGMA integrity_check` returns `ok`. No fixture or test writes to the default application database.

## Fixture provenance and extension rule

`tests/fixtures/dialogue_regressions_v2.json` declares provenance as synthetic. The already available `tests/fixtures/telegram-2026-10-21.json` is used by the pre-existing offline replay test; its existing contents were not copied into this regression fixture. If historical cases are added later, add a clear source reference and verify redaction first. Keep assertions against desired v2 behavior and add new regression cases as ordinary assertions.
