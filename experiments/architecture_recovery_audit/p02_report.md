# P0.2 — контракт диалога и маршрутизации

Дата: 2026-10-25. Область: offline рабочее дерево. [Шестиходовая трасса после исправления](sqlite_bot_replay_20261025.json), [тест Telegram/SQLite](../../tests/test_telegram_pilot_sqlite_replay.py), [исходная матрица падений](failure_matrix.md). Provider JSON для исходного ручного пилота не сохранился: replay использует синтетические payload по сохранённым validated полям. Qdrant-кандидаты, Groq и Telegram I/O подменены; reducer, SQLite, retrieval, source-first, approved Markdown и safety gates настоящие.

## Причинная матрица: до → после

Шесть ходов после P0.2 (состояние `expected` указано **после** ответа бота):

| Ход | Raw fixture `relation / intent / operation` | Проверенное состояние и маршрут | Причина |
|---|---|---|---|
| 1 | `new_task / unknown / explain` | `new_task / general / explain`, `expected=task`, `clarify` | Определён speech act, но широкая просьба не задаёт предметной задачи; readiness gate остановил retrieval. |
| 2 | `new_task / unknown / explain` | `new_task / general / explain`, без slot, `answer` | Явный вопрос об определении ОФД — отдельная задача; `explain` обоснованно переводит unknown intent в general. |
| 3 | `new_task / unknown / diagnose` | `new_task / receipt / diagnose`, без slot, `answer` | Прямой объект «чеки» подтверждён span; намерение receipt согласовано с ним, симптом и Эвотор сохранены в новой задаче. |
| 4 | `answer_to_clarification / unknown / diagnose` | `continue / receipt / diagnose`, `expected=equipment`, `clarify` | На входе открытого slot не было: raw relation неверен. Операция диагностики наследуется; повторный exact-раздел заменён уточнением модели. |
| 5 | `continue / unknown / diagnose` | `continue / receipt / diagnose`, без slot после `escalate` | Новое утверждение «Интернет работает» сохранено, модель всё ещё не подтверждена. Источник снова даёт тот же section ID, поэтому второй повторный вывод блокируется. |
| 6 | `new_task / unknown / search` | `new_task / receipt / search`, `expected=service`, `clarify` | Новый прямой объект «чек» и поиск не относятся к предыдущей диагностике. Ожидание service добавляет source-scope gate, не reducer. |

`request_type=information` в фикстурах ходов 1–6 описывает форму обращения и не переопределяет task operation. В частности, информационный вопрос может требовать поиска, а диагностика не превращается в `explain`.

| Случай | Подтверждённая причина до P0.2 | Изменение и проверяемый итог |
|---|---|---|
| Пилот, ход 4: вопрос «где проверить связь» | Provider fixture пометил `answer_to_clarification`, хотя `expected=None`. Reducer принимал эту связь и снова передал тот же task/source Planner. Source-first без учёта уже выданного ответа копировал целую секцию. | Без открытого слота связь нормализуется к продолжению. При выборе уже выданного exact-раздела ответ теперь не повторяется: одно уточнение модели оборудования для manufacturer-routed диагностики. `relation=continue`, `clarify/grounded_section_followup_scope_needed`, `expected=equipment`. |
| Пилот, ход 5: «Интернет работает» | Provider выделил только цель «что ещё проверить»; отдельное утверждение клиента отсутствовало в state.details. Тот же section ID копировался третьим разом. | Reducer сохраняет неохваченную цель/сущности часть сообщения точным клиентским span; после открытия SQLite факт «Интернет работает» присутствует. Повтор section ID при уже заданном уточнении даёт ограниченную эскалацию `grounded_section_followup_exhausted`, без новой инструкции и без повторного текста. |
| Пилот, ход 6: поиск чека по ФН | Новый task был распознан правильно; source-first остановился на `source_scope_context_missing` до сообщения ограничения из approved статьи. | Grounded объект «чек» с операцией `search` теперь согласован с `intent=receipt`; задача остаётся новой. Scope gate всё ещё блокирует ответ. Это **P0.3 source applicability**, а не оставшаяся ошибка task relation. Strict xfail сохраняет открытый quality gate. |
| Ожидаемый service/model | Lexical и semantic ветви расходились: короткое «Мой ОФД?» закрывало service без названия; semantic provider мог назвать любой ход ответом на clarification. | Общий reducer сохраняет entity slot до подтверждённой сущности либо явного `unknown_facts`. Самостоятельный вопрос с новым объектом/действием открывает новый task. `unknown` не становится моделью; после ответа aQsi слот закрывается. |
| `request_type / intent / operation` | `request_type=information` описывает форму реплики, но поисковый task мог оставаться `intent=unknown`; лексический `check` перекрывал слово «список». | Тип реплики не подменяет операцию. Уникальная категория выводится только из подтверждённого прямого объекта при конкретной операции; `список` переводит generic `check` в `list`. `general/explain` остаётся определением. |

**Предел доказательства о повторах.** Fake Planner в ходах 3–5 выбирает один и тот же существующий section ID, но не содержит и не возвращает итоговый текст. Для технического маршрута Composer/Judge не вызываются. Итоговые дословные копии целого раздела создавались `SourceFirstService` из локального approved Markdown при каждом ходе. Следовательно, постоянный *текст* не был provider fixture; фиксированный выбор секции был условием воспроизведения. Реальное качество выбора Planner без Groq этим тестом не измерено. Исправление гарантирует отсутствие одинакового конечного текста при этом повторном выборе, не обещая новый доказанный технический шаг.

## Пять исходных падений

| Исходный тест | До | После / основание |
|---|---|---|
| `test_expected_slot_short_replies_and_no_assistant_facts` | `expected=None` после «Мой ОФД?» | Pass: неподтверждённый service остаётся ожидаемым. |
| `test_only_client_history_confirms_service_and_is_used_in_search` | Legacy ответ `rejected` на «Мой ОФД» | Pass: остаётся `service_ambiguous`; нерешённый ответ не попадает в RAG query, подтверждённый aQsi попадает. |
| `test_seven_real_turns_keep_context_gate_knowledge_and_repair_recorded_output` | `check` вместо `list` | Pass: generic запрос списка сохраняет `list`, без специального правила для Платформы ОФД. |
| `test_contextual_fact_keeps_task_and_root` (billing) | Уточнение сервиса и способа проверки начинало новый task | Pass: старый договорный task/root сохраняются, новое полное сообщение входит в query. |
| `test_specialized_aqsi_procedure_needs_confirmed_applicability` | Ожидание `ofd_connection` от общего `general/check` | Исправлено устаревшее ожидание на category `None` и `no_task_matched_candidates`. Проверено, что aQsi IP/port документ не выбирается; `document_applicability` всё ещё требует equipment, а явное подтверждение aQsi сохраняет применимость. Это изменение теста **не ослабило** gate. |

## Replay и отрицательные проверки

- Исходные шесть ходов: 1 `clarify`, 2 `answer`, 3 `answer`, 4 `clarify` с новым slot, 5 `escalate`, 6 `clarify/source_scope_context_missing`. Прежние дословные повторы ходов 4–5 устранены. Каждый ход проходит `bot.handle_message`, новое открытие временной SQLite, двукратное восстановление состояния и exact-span provenance. Трасса содержит planner section ID и стадии, поэтому причина ответа проверяема.
- Три независимых сценария через тот же bot/SQLite путь: aQsi access → контекстный service → новая receipt-задача без наследования aQsi; поиск чека в Платформе ОФД → местоименная ссылка «его» с сохранением задачи; закрытие архива ФН → `unsafe_operation` до retrieval/LLM. В основной трассе неподтверждённая модель остаётся `None`; явный unknown проверен отдельным semantic тестом.
- Существующие отрицательные тесты: foreign service и draft (`test_unresolved_task_does_not_mix_foreign_service_or_draft`), aQsi model applicability (`test_specialized_aqsi_procedure_needs_confirmed_applicability`), смена темы при ожидаемой модели (`test_d_new_topic_paraphrase_clears_stale_equipment_slot`), SQLite reopen (`test_h_new_conversation_reload_and_pending_recovery_are_isolated`), безопасная техническая ветка (`test_source_first_dialogue_contract.py`). Все входят в полный suite.
- До: **376 passed, 5 failed, 1 xfailed, 13 warnings**. После: **385 passed, 0 failed, 1 strict xfailed, 13 warnings** (`python -m pytest -q -rx --disable-warnings`). Профильный E2E-набор: **109 passed, 1 strict xfailed**. Никакого Groq/live Telegram вызова не было.

## Решение и остаток

**P0.2 DONE в offline области; GO к отдельной P0.3 работе по source scope, только после согласования этапа.** Не достигнут GO для worker switch или ручного Telegram-пилота: вопрос по ФН остаётся strict xfail, fake candidates не измеряют live Stage3, а безопасная эскалация хода 5 ещё не даёт полезный следующий шаг. P0.3 должен разрешить source-attributed ограничение поиска по ФН и безопасную частичную диагностику без product-specific действий при неподтверждённой области. Approved evidence, локальный SHA, applicability и unsafe gates сохранены. Рабочие SQLite/Qdrant/KB/.env, worker PID 46544 и модель не изменялись; commit/push не выполнялись.
