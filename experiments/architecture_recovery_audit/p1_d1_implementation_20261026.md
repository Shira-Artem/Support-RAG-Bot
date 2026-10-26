# P1 D1 — AI Coordinator: реализация первого vertical slice

Дата: 2026-10-26. Статус: **offline vertical slice PASS; follow-up live run выполнен, semantic quality NO-GO**. Подробная хронология — в [live experiment report](p1_d1_live_experiment_20261026.md).

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
- На момент подготовки исходного implementation report был выполнен только `preflight_only`; этот статус заменён последующим ограниченным live run ниже. Бюджет и stop conditions — [`p1_d1_live_gate_20261026.md`](p1_d1_live_gate_20261026.md).

## Риски и следующий шаг

- Live gate проверил настоящее понимание Groq и Qdrant ranking в пределах двух ходов; он выявил семантический сбой sentence ranker на D1.3. Это не доказывает качество остальных grounded-information запросов.
- Exact quote renderer полезен для атомарных facts, но ограничивает связные объяснения и несколько зависимых evidence-фрагментов. Прогресс процедурной задачи и next-action selection пока не реализованы — это следующий P1 D2 slice.
- Generic overlap ranker может выбрать лексически совпадающее, но нерелевантное предложение даже из правильного документа. Не добавлять локальные правила под ОФД; исправление требует общего решения о фокусе/релевантности и regression coverage.
- **GO:** продолжить P1 offline к D2 technical-action progress/next step с текущими независимыми gates. **NO-GO:** live/Telegram/worker rollout и заявление о production usefulness. P1 D1 не закрывает общий P0 dialogue quality gate.

Production SQLite, Qdrant, KB, `.env`, worker и Telegram polling не изменялись. Commit/push не выполнялись.

## Follow-up: limited live D1 gate — 2026-10-26

После безопасного старта существующего Qdrant container с тем же volume выполнен один bounded run на последней успешно использовавшейся `knowledge_stage3_retrieval_20261022`: 2 Groq Understanding calls, 2 retrieval turns, 3,572 tokens, без retries. Approved source hashes/scope согласованы; оба exact-quote ответы прошли independent safety. D1.2 корректно объяснил роль ОФД. D1.3 выбрал точную tariff/contract фразу из правильной top-ranked approved статьи, но не объяснил назначение ОФД для передачи фискальных документов. **Семантический quality gate NO-GO**, несмотря на mechanical PASS в runner. Причина — общий generic sentence overlap, не retrieval miss. См. [run 2 trace](p1_d1_live_trace_20261026_run2.json), [отчёт](p1_d1_live_experiment_20261026.md); первоначальная остановка до Groq и erratum `knowledge_v1` — в [run 1 trace](p1_d1_live_trace_20261026.json).

Решение: **NO-GO расширению grounded-information; GO только к offline P1 D2** под неизменными safety/applicability gates. Live D2, worker/Telegram и production rollout остаются NO-GO.

## Follow-up: LLM Evidence Selector A/B

После этого отчёта отдельным выключенным по умолчанию feature flag добавлен ID-only semantic selector. Он не переписывает прежний D1 путь и сохраняет lexical и Source-first варианты. Bounded A/B использовал одинаковые Understanding/state/retrieval snapshots и исчерпал лимит 8 Groq attempts / 4 retrieval turns. Две завершённые пары после офлайн-коррекции lexical harness показали semantic 2/2 полезных и lexical 1/2; D1.2 arms совпали, D3.1 semantic лучше показал маршрут поиска. Оба follow-up решения не завершились из-за ошибок API; gate остаётся **NO-GO/incomplete**. Решение и стоимость подробно записаны в [selector A/B report](p1_semantic_selector_ab_20261026.md), трасса — [JSON](p1_semantic_selector_ab_20261026.json). Следующий разрешённый этап — **offline P1 D2 с ProgressLedger**, без grounded-information rollout.
