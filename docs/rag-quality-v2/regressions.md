# DialogueState v2 regression matrix

All new messages in the fixture are synthetic reconstructions from the task brief. They are not represented as historical user messages. No live API, Telegram bot, production database, or Qdrant collection is touched.

## Baseline status

`python -m pytest -q tests/test_dialogue_regressions_v2.py`: **5 passed, 7 xfailed, 0 xpassed**. The xfails use `pytest.mark.xfail(strict=True)` and are narrow to A–F plus the session-to-task leakage invariant. The full suite: **144 passed, 7 xfailed, 0 failed, 0 skipped, 0 xpassed**.

| ID | Message and previous context | Target relation / state | Query requirement | Current result |
|---|---|---|---|---|
| A | “У меня есть только номер ФН кассы. Получится найти чек напрямую по нему?” after Platforma OFD receipt search | `parameter_update`; retain receipt/search and Platforma OFD; add FN as parameter | Standalone query still says receipt search and includes FN; never route as fiscal-drive search | XFAIL: new fiscal_drive task, prior task lost |
| B | Email unavailable with phone remaining; then “А если к телефону тоже доступа нет, как теперь войти?” after aQsi password recovery and expected details | `continue` / `answer_to_clarification`; one credentials/reset-password task; close answered stale slot | Each user follow-up gets a retrieval query | XFAIL: state marked `analysis_required`, query rejected |
| C | “В кабинете этого раздела у меня нет. Что делать?” after ATOL reports and expected details | `contradiction`; keep report task and allow diagnosis/escalation | Query retains ATOL report context | XFAIL: unresolved ambiguity gate blocks retrieval |
| D | “Где посмотреть документы, которые не отправились оператору ОФД?” while old TS PiOT task waits for equipment | `new_task`; clear old clarification and task facts | Query contains OFD-document intent; no TS PiOT equipment/service | XFAIL: transition is `clarification`, old task/slot persist; query remains `сервис: ТС ПиОТ — ТС ПиОТ, какая модель оборудования?` |
| E | “А где посмотреть список выписок?” after bank statements in 1C:DirectBank | `continue`; bank statement intent and operation/object retained | Query points to statement list | XFAIL: unknown/check classification, then ambiguity |
| F | “Эвотор 6, как повторно распечатать старый чек по номеру ФД?” | new task with `receipt` and `repeat_print` | Query retains repeat-print action and FD argument | XFAIL: receipt recognized, operation unknown; query falls back to original text |
| G | `АТОЛ Онлайн` during aQsi employee-access task with viewing goal and no-settings limit | `parameter_update` or explicit service switch; same task, preserve requirements, route ATOL | New active product only; no aQsi product source mixed into query | PASS: `change_service`, goal and constraint retained; query uses ATOL only |

## Additional invariants

| Invariant | Offline check | Result |
|---|---|---|
| New independent question resets task facts | New task ID; prior goals, constraints, parameters cleared | PASS |
| Session entity remains available | Entity remains in session state when task resets | PASS |
| Session fact is not auto-bound to a new task | New password-recovery task after an aQsi employee task should have no active route absent a new product fact | XFAIL: v1 reuses aQsi as `routing_service` |
| Bot clarification does not become a user fact | Only the `expected` clarification changes | PASS |
| New conversation has no prior task | Separate conversation ID in a temporary SQLite file | PASS |
| Save/load and pending recovery | Reload snapshot; recover pending answer; task replayed | PASS |
| Fact provenance | Message ID and exact quote span checked | PASS |
| Ambiguous products do not invent a service | Two competing named products result in no singular service and `analysis_required` | PASS |

`pending/recover/complete` and state round-trip are also covered by existing `tests/test_dialogue_state.py` and `tests/test_conversations.py`. No fixture or test writes to the default application database.

## Fixture provenance and extension rule

`tests/fixtures/dialogue_regressions_v2.json` declares provenance as synthetic. The already available `tests/fixtures/telegram-2026-10-21.json` is used by the pre-existing offline replay test; its existing contents were not copied into this regression fixture. If historical cases are added later, add a clear source reference and verify redaction first. Keep assertions against desired v2 behavior; remove each strict xfail only after the corresponding behavior is implemented and re-run the full suite.
