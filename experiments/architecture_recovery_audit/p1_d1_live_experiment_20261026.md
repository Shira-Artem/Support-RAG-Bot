# P1 D1 bounded live experiment — semantic quality NO-GO

Дата: 2026-10-26. Цель: один ограниченный live `D1.2 → D1.3` с реальными Groq Understanding и Qdrant Hybrid Retrieval, максимум 2 Groq calls и 2 retrieval turns, без автоматических повторов. Первая попытка остановилась до Groq; после безопасного восстановления существующего Qdrant выполнен один gate run. Полные raw/validated traces: [run 1 BLOCKED](p1_d1_live_trace_20261026.json), [run 2 completed](p1_d1_live_trace_20261026_run2.json).

## Причина остановки первой попытки и восстановление

Docker Desktop был запущен, активный контекст — `desktop-linux`. Существующий `rag-qdrant-1` (`qdrant/qdrant:v1.15.4`) завершился с кодом 255 в `2026-10-26T05:34:19Z`; `OOMKilled=false`, состояние ошибки пустое, restart policy — `no`. Docker Desktop processes стартовали около `05:34:05Z`; это согласуется с перезапуском Docker Desktop, но прямой записи причины завершения нет. Исходный compose публикует `127.0.0.1:6333`; WSL Ubuntu остановлен, Docker Desktop WSL2 distro работает. И active `desktop-linux`, и `default` context видят тот же контейнер, поэтому это не несовпадение контекстов приложения и CLI.

У контейнера сохранён mount `rag_qdrant_storage → /qdrant/storage`; labels указывают на `docker-compose.yml` этого репозитория. Контейнер запущен командой `docker start rag-qdrant-1`, без удаления, compose recreate, новой коллекции или индексации. Причина первоначального connection refused — остановленный контейнер и отсутствующий listener на loopback port 6333.

**Erratum к trace первой попытки:** там ранее было записано `knowledge_v1` по default из кода runner. Это было неверное предположение. `scripts/p1_d1_live_gate.py` импортирует `app.config`, который загружает `.env` до чтения `QDRANT_COLLECTION`; эффективная `.env` коллекция — `knowledge_organized_stage2_[redacted-number]`. Первый запрос не прошёл соединение, поэтому Qdrant не подтвердил существование ни одной коллекции. Runner теперь fail-closed, если `QDRANT_COLLECTION` не задан.

## Проверка хранилища и фактическая конфигурация

Последние успешные live E2E-тесты проекта (2026-10-25, зафиксированные в [`PROJECT_STATE.md`](../../docs/PROJECT_STATE.md)) использовали `knowledge_stage3_retrieval_20261022`. Для текущего теста её выбрали явным process-only `QDRANT_COLLECTION`, чтобы использовать проверенную конфигурацию последних рабочих тестов, а `.env` оставить неизменённым.

- Docker Desktop 29.6.1, context `desktop-linux`; Qdrant image 1.15.4.
- Effective URL: `http://127.0.0.1:6333`; gate collection: `knowledge_stage3_retrieval_20261022`.
- Inventory: **934 points**, 384 dimensions; **672 approved**, 262 draft, 269 документов.
- Approved set: 206 уникальных approved documents; все 206 присутствуют как локальные approved документы, content hash совпадает, scope совпадает; все 672 Qdrant approved chunk texts совпали с локальным `Chunker`.
- На время gate заданы `AI_COORDINATOR_ENABLED=1`, `RAG_ENGINE=source_first`, `RAG_BACKEND=qdrant`, `RAG_DEMO_MODE=0`; dummy non-empty `SOURCE_FIRST_TELEGRAM_IDS` нужен только для Settings validation. `bot.py` не импортируется, Telegram ID не используется для routing. `.env` не изменён.

В runner разрешены только Qdrant read methods `collection_exists/get_collection/scroll/query_points`; create/upsert/delete недоступны. За gate в Docker logs наблюдаются **18 успешных read-only HTTP requests**: 2 existence reads, 2 metadata reads, 12 scroll pages и 2 dense queries; write routes — 0. Qdrant SDK выдал совместимость warning (client 1.19.1 / server 1.15.4), но все прочитанные endpoints ответили 200.

## Live run 2: результаты

Groq `openai/gpt-oss-20b` выполнил **2 Understanding calls из лимита 2**, без retries. Hybrid Retrieval выполнен **2 раза из лимита 2**. Composer/Planner/Repair/Judge вызовов после Understanding не было. Provider usage: **1,894 prompt + 1,678 completion = 3,572 tokens** (по 1,786 на ход).

1. `Что такое ОФД?` → «ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.»
2. `А зачем он нужен кассе?` → «Для обычных сценариев облачной кассы требуется корректно оформленный договор и действующий тариф ОФД.»

Первый ответ полезен и объясняет роль оператора. Второй семантически **не отвечает** на вопрос о назначении ОФД для передачи фискальных документов; он сообщает о договоре и тарифе. Отличие ответов не засчитывается как качество.

На обоих ходах Qdrant/retrieval выбрал сверху правильный approved документ `atol_online/ofd/what-is-ofd.md` (`atol-online-11256-what-is-ofd`). Значит, live ошибка не в отсутствии релевантного документа: `generic_content_term_overlap` на уровне предложения выбрал внутри него тарифную фразу, формально grounded, но нерелевантную текущему subgoal. Это **прямое live подтверждение** риска, ранее замеченного на offline trace. Частный regex или вопросно-специфичное правило не добавлялись.

Latency:

| Ход | Understanding | Retrieval (Qdrant pipeline) | Answer pipeline |
|---|---:|---:|---:|
| D1.2 | 1,685 ms | 468 ms | 968 ms |
| D1.3 | 1,399 ms | 282 ms | 703 ms |

Общее wall time команды — около 56.8 s, включая загрузку локальных embedding weights; это не latency ответа. Отдельная точная стоимость в деньгах не рассчитывалась; Groq token usage сохранён.

## Safety и ограничения наблюдения

- Оба ответа прошли `exact_approved_sentence`, локальный source SHA был verified, использована только approved evidence; после Understanding генерация не вызывалась. Safety — PASS, семантический quality — NO-GO.
- В trace записаны raw structured и validated Understanding, reducer state/reopen, CoordinatorDecision, все selected Qdrant candidates, chosen evidence, финальный ответ, token usage и latency. Секреты/headers не сериализуются.
- Runner сообщил `UnicodeEncodeError` при печати Unicode JSON в PowerShell `cp1251` **после** записи полного UTF-8 trace. Trace прочитан и разобран; повторный live run не выполнялся. Печать runner исправлена на ASCII-escaped JSON для следующих запусков.
- Во время инициализации embedding было предупреждение HF Hub о unauthenticated request. Cache snapshot проверялся заранее и веса загрузились; точное число возможных Hub metadata requests не инструментировалось. Для будущих запусков runner теперь включает process-local `HF_HUB_OFFLINE=1` до загрузки модели. Этот непредусмотренный warning указан отдельно и не включён в Groq/Qdrant budgets.
- Временная SQLite использовалась только для диалога gate. Production SQLite, KB, Qdrant contents, `.env`, Telegram worker не менялись; indexing и service restart не выполнялись.

## Решение

- **NO-GO:** расширять или включать grounded-information route для пользователей. Live прогон подтвердил: retrieval находит правильный документ, но общий sentence overlap выбирает нерелевантный факт.
- **GO только offline:** продолжить P1 D2 как отдельный technical-action vertical slice на временной SQLite, сохраняя reducer-owned checks/progress и независимые safety/applicability gates. Это разрешение не включает live D2, worker или production.
- Для расширения grounded-information сначала нужен общий критерий фокуса/семантической релевантности и bounded regression, который считает tariff-only ответ неуспехом. Не добавлять правило для конкретного вопроса об ОФД.

**Итог:** механический runner gate отметил 2 различных safe answers как `PASS`; применённый пользователем semantic quality gate — **NO-GO** из-за ответа D1.3. Общий P0 quality gate также остаётся NO-GO. Commit/push не выполнялись.
