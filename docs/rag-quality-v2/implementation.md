# DialogueState v2 implementation report

Branch: `fix/rag-p0-dialogue-v2`
Scope: Step 2 state model, reducer transitions, standalone RAG query projection, and additive SQLite snapshot migration. Regression wording is synthetic as documented in [regressions.md](regressions.md); the before-state is recorded in [baseline.md](baseline.md).

## State model and reducer

`DialogueState` now serializes schema version 2 with `session` and `task_context`. Session facts remain available across tasks, while task facts, active route, requirements, parameters, and expected clarification belong to the current task. Existing flat state attributes remain as a compatibility facade. Incoming turns are classified into `new_task`, `continue`, `parameter_update`, `constraint_update`, `contradiction`, `answer_to_clarification`, or `unknown`; current-turn fact citations are checked before they are applied.

An explicit new topic starts a new task and cancels the old expected clarification. A generic “ОФД” mention does not guess a specific vendor. An implicitly related follow-up can reuse a compatible explicit route from session context; an explicit new topic cannot. This compatibility rule preserves the existing status-follow-up behavior while preventing automatic route binding to an independent task.

## Regression output after implementation

The following values and queries are the actual offline output from the seven baseline cases (empty `expected` and `analysis_required=false` for each):

| Case | State | Generated query |
|---|---|---|
| A | `task:1`, `parameter_update`, `receipt/search`, route `Платформа ОФД` | `ОФД: Платформа ОФД — поиск чека — ограничения: только номер ФН кассы — параметры текущего поиска: номер ФН кассы` |
| B | `task:1`, `constraint_update`, `credentials/reset_password`, route `aQsi Online` | `сервис: aQsi Online — восстановление пароля учётной записи — ограничения: К старой почте доступа нет; А если к телефону тоже доступа нет — уточнение клиента: К старой почте доступа нет, но номер телефона остался. Через него можно?; А если к телефону тоже доступа нет, как теперь войти?` |
| C | `task:1`, `contradiction`, `report/view_reports`, route `АТОЛ Онлайн` | `сервис: АТОЛ Онлайн — просмотр отчётов — запрос клиента: АТОЛ Онлайн, где посмотреть отчёты? — уточнение клиента: В кабинете этого раздела у меня нет. Что делать?` |
| D | `task:2`, `new_task`, `receipt/transmit`, route unset | `поиск документов, не переданных оператору ОФД — уточнение клиента: Где посмотреть документы, которые не отправились оператору ОФД?` |
| E | `task:1`, `continue`, `bank_statement/list`, route `1С` | `ПО: 1С — просмотр списка банковских выписок` |
| F | `task:1`, `new_task`, `receipt/repeat_print`, route `Эвотор` | `оборудование: Эвотор 6 — производитель: Эвотор — повторная печать ранее выданного чека — параметры клиента: номеру ФД` |
| G | `task:1`, `parameter_update`, `access/add_employee`, route `АТОЛ Онлайн`; task goal and restriction retained | `сервис: АТОЛ Онлайн — добавление сотрудника — цель: добавить сотрудника для просмотра касс — ограничения: без права менять настройки` |

## SQLite migration

The migration is additive. It creates `dialogue_states_v2` and `dialogue_state_migration_archive`, copies valid snapshots, and retains exact legacy JSON plus a SHA-256 source identity. Legacy `dialogue_states`, conversations, and messages are not rewritten. Re-running migration is idempotent. Unknown schema versions and invalid payloads are archived with blocked status; reads raise an explicit error instead of silently initializing an empty state. These checks use temporary SQLite files only. The test also verifies that an archived unknown-version payload remains byte-for-byte unchanged and that SQLite `integrity_check` passes.

## Verification

- `python -m pytest -q tests/test_dialogue_regressions_v2.py`: **21 passed**.
- `python -m pytest -q`: **160 passed**.
- `python -m scripts.trace_dialogue_state`: five-turn offline trace retains task ID, goal and constraint across follow-ups; switching from aQsi Online to ATOL Online changes the generated route while retaining the requirements.
- Incident replay is covered by the full suite's offline replay test, using local data and a generator stub.

No commit or push was made. No live bot, default application database, Qdrant, external model, or Telegram UI was exercised. The retrieval pipeline still has its existing session-entity consumer; task-scoped filtering there is a follow-up outside this scoped patch.
