# P1 D1 — AI Coordinator: реализация первого vertical slice

Дата: 2026-10-26. Статус: **offline vertical slice PASS; limited live gate подготовлен, не запускался**.

## Что изменено

- [`app/ai_coordinator.py`](../../app/ai_coordinator.py): typed `CoordinatorDecision` содержит исходный `request_type`, route (`conversation`, `grounded_information`, `technical_action`), relation reducer (`new_task`, `continue`, уточнение/параметр/противоречие), подцель текущего хода, `required_action` и rationale code. Координатор строит решение из уже проверенного Understanding и DialogueState; факты в state не записывает.
- [`app/config.py`](../../app/config.py) и [`bot.py`](../../bot.py): opt-in `AI_COORDINATOR_ENABLED`, default off; B доступен только существующим Source-first allowlisted users. A продолжает вызывать прежний Source-first без coordinator decision. Решение B сохраняется в diagnostics assistant-строки SQLite; пользовательская схема таблиц не менялась.
- [`app/source_first_service.py`](../../app/source_first_service.py): для grounded-information route существующий RetrievalPipeline выбирает approved-кандидатов; B ранжирует точные предложения универсальным content-term overlap текущей подцели, повторно проверяет локальный source SHA/status, точную цитату, claim grounding, applicability и финальный safety. Возвращается одно точное предложение с областью источника и ссылкой. После Understanding нет Planner/Composer/Repair/Judge вызова. Для technical-action остаётся существующая Source-first цепочка, к planner payload добавляется typed decision; safety gates не передаются координатору.
- [`app/answer_service.py`](../../app/answer_service.py): к сериализуемому ответу добавлено поле decision diagnostics. Миграция SQLite не нужна.
- Offline сценарий [`tests/test_telegram_pilot_sqlite_replay.py`](../../tests/test_telegram_pilot_sqlite_replay.py) проходит через настоящий `bot.handle_message`, `ConversationStore`, reducer, SQLite close/reopen, `RetrievalPipeline`, `SourceFirstService` и exact evidence renderer. Provider understanding подан сохранённой fixture; Planner/Composer/Judge outputs не подменялись: B их не вызывает.

## D1.2 → D1.3: наблюдаемые ответы

1. `Что такое ОФД?` → «ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.» Источник ограничен АТОЛ Онлайн / облачной ККТ.
2. `А зачем он нужен кассе?` → «Для обычных сценариев облачной кассы требуется корректно оформленный договор и действующий тариф ОФД.» Источник остаётся тем же approved документом; новый вопрос стал `current_subgoal`, reducer relation — `continue`.

Ответы различаются, оба представляют точные предложения из одной approved секции; второй не расширяет evidence до утверждения о всех кассах или универсальной блокировке продаж. Полная sanitized трасса: [`p1_d1_offline_trace_20261026.json`](p1_d1_offline_trace_20261026.json).

## Проверки и calls

- Целевой набор: **104 passed, 6 xfailed** по coordinator/config, SQLite replay, Source-first dialogue contracts, Understanding и reducer tests.
- Полный suite: **404 passed, 6 xfailed, 13 warnings**.
- Отдельный offline trace test: **1 passed**; SQLite reopened between both turns and round-tripped state. Exact SHA/status/sentence gates passed; source stayed `atol_online/ofd/what-is-ofd.md`.
- В offline E2E: **0 реальных Groq calls / 0 tokens; 0 реальных Qdrant requests/writes**. Два Understanding вызова были saved fixtures; два retrieval прохода использовали локально загруженный approved документ через настоящую RetrievalPipeline. B провёл **0 Planner/Composer/Repair/Judge calls**.
- Negative safety: coordinator-enabled S1 (опасное закрытие архива ФН) и S5 (retrieved instruction injection) остановлены до retrieval; S4 (чужая aQsi IP-инструкция для Эвотор) остановлена applicability gate. **Ни одного ослабления source-first safety gate.**
- Live gate runner `scripts/p1_d1_live_gate.py` прошёл только `preflight_only` с placeholders: `will_make_network_calls=false`, лимит 2 Groq calls. Сам live gate **не запускался**. Бюджет и stop conditions — [`p1_d1_live_gate_20261026.md`](p1_d1_live_gate_20261026.md).

## Риски и следующий шаг

- Это не проверяет фактическое понимание Groq, Qdrant ranking или межмодельную полезность; для этого подготовлен, но не запущен отдельный ограниченный gate.
- Exact quote renderer полезен для атомарных facts, но ограничивает связные объяснения и несколько зависимых evidence-фрагментов. Прогресс процедурной задачи и next-action selection пока не реализованы — это следующий P1 D2 slice.
- Generic overlap ranker может ошибиться на парафразе с низким lexical overlap; в таком случае он закрывает ответ, не генерируя догадку. Не добавлять локальные правила под ОФД.
- **GO:** продолжить P1 offline к D2 technical-action progress/next step с текущими независимыми gates. **NO-GO:** live/Telegram/worker rollout и заявление о production usefulness. P1 D1 не закрывает общий P0 dialogue quality gate.

Production SQLite, Qdrant, KB, `.env`, worker и Telegram polling не изменялись. Commit/push не выполнялись.
