# Source-first в существующем Telegram runtime

Дата: 2026-10-25
Базовый опубликованный commit: `86a86404ddd50efa88ba2b7ba69c8cc6fdef26a7`
Статус: прежний Telegram worker запущен; Source-first работает только для прежнего allowlist.

## Гипотеза и границы

Гипотеза: существующий approved Hybrid Search и `RetrievalPipeline` могут оставить применимость и отбраковку на прежней проверенной границе, а Source-first Planner сможет выбрать только целый раздел из уже отобранного approved источника. Ответ пользователю должен копировать этот раздел дословно, чтобы не терять условия, предупреждения и порядок шагов.

Используются прежний `bot.py`, меню, `ConversationStore`, `DialogueState`, callback обработчики, `AnswerService` для всех остальных пользователей и экспертного режима, Groq GPT-OSS 20B, Qdrant Stage2 и существующая SQLite. Нового Telegram-бота, токена, DB, polling worker, Qdrant коллекции и обработчика Telegram не создано. Source-first включается через процессную переменную `RAG_ENGINE=source_first` и только для уже имеющегося списка ID `EXPERT_TELEGRAM_IDS` (пользователь прямо распорядился взять прежние ID). Сами ID не выводятся и не копируются в код или отчёты.

Это ограниченный ручной пилот, а не результат quality gate V1.2-B и не переход к V1.2-C. Качество не оценивалось.

## Изменения

- `app/config.py`: `RAG_ENGINE`, отдельный allowlist-предикат; при включённом движке ID берутся из явного `SOURCE_FIRST_TELEGRAM_IDS` или, по прямому указанию пользователя, из существующего `EXPERT_TELEGRAM_IDS`.
- `bot.py`: до построения Qdrant runtime выполняется проверка, что заданная коллекция существует и непуста; это предотвращает создание новой пустой коллекции `QdrantStore`. В свободном режиме только allowlisted ID маршрутизируется в Source-first сервис. Меню, память, экспертный режим и callback специалиста сохранены.
- `app/source_first_service.py`: использует `RetrieverRAGAdapter.search_for_state` (BM25 + Dense + RRF, approved-only и существующие task/service/equipment/operation/applicability gates). Planner получает только отобранные разделы и обязан вернуть `applicability_confirmed=true` и `order_confirmed=true`; пропуск любого признака ведёт к эскалации. Applicability независимо перепроверяется сравнением Qdrant metadata с approved YAML по статусу и scope полям. Выбор проверяется по ID раздела, точному заголовку и SHA-256 непосредственно перед ответом. Ответ дословно копирует полный раздел, сохраняя условия, предупреждения и порядок, и добавляет источник. Опасный запрос или опасное содержимое выбранного раздела эскалируется. При отсутствующем контексте задаётся уточнение максимум один раз на слот, максимум два разных уточнения; потом эскалация. Ошибка Qdrant/Groq, невалидный выбор или расхождение источника ведут к безопасному отказу без генерации технических шагов.
- `app/answer_service.py`, `app/bot_runtime.py`: маркировка движка в сохранённой трассе и process receipt. Receipt хранит PID, commit, SHA-256 исходников, модель, коллекцию, число allowlisted ID и хеш списка без раскрытия ID.
- `experiments/telegram_source_first_integration/preflight.py`: read-only inventory/embedding/hybrid smoke без LLM и записей в Qdrant.
- `experiments/telegram_source_first_integration/smoke.py`: локальная проверка allowlist, legacy fallback, approved exact-section resolution и SHA без Telegram/Qdrant/Groq.
- `experiments/telegram_source_first_integration/export_anonymized.py`: read-only экспорт Source-first ходов из прежней DB; ID Telegram не включаются, email/телефоны и распространённые явно подписанные поля / ввод имени маскируются. Автоматическая маскировка эвристическая и не гарантирует обнаружение несообщённых явно личных данных; перед передачей внешним лицам экспорт следует просмотреть.

## Проверки до запуска

- `py_compile` изменённых runtime и вспомогательных файлов — PASS.
- Локальный `smoke.py` — PASS: Source-first маршрутизируется только по opt-in и ID из allowlist; другие ID и legacy остаются на старом пути; exact approved section и hash сверяются. Внешних вызовов нет.
- Локальный smoke включает редактирование типичных персональных данных. Первая проверка ожидала маркер `[EMAIL]` для поля с явной меткой `email`; redactor заменил целиком всё подписанное поле на более строгий `[REDACTED]`. Ожидание smoke скорректировано, итоговая проверка проходит. PowerShell не раскрывает `*.py` для аргумента `py_compile`; после `Invalid argument` повторная проверка с явным списком файлов прошла.
- `preflight.py` — PASS: Telegram token и Groq key доступны (секреты не печатались); provider `groq`; модель `openai/gpt-oss-20b`; коллекция `knowledge_organized_stage2_20261022`, 934 points / 672 approved / 262 draft; embedding `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, dimension 384; retrieval smoke 5/5 результатов approved. LLM calls = 0, Qdrant writes = 0.
- Дополнительная read-only проверка синхронизации Qdrant → локальные approved source sections: все 672/672 approved chunks совпали по `document_id`, точному heading и нормализованному body; отсутствующих approved документов/секций и content mismatches — 0.
- Предыдущая task-aware проба для обобщённой кассовой проблемы не выбрала раздел и вернула `applicability_context_missing` (71 кандидат отклонён). Это отрицательный результат поиска, не оценка качества: нет сервисной/оборудовательной привязки, и новый сервис должен уточнить контекст или эскалировать.
- Qdrant клиент 1.19.1 предупреждает о сервере 1.15.4; read-only Hybrid Search завершился успешно. Клиент/сервер не обновлялись.
- На момент проверки Windows Python worker отсутствовал, прошлый receipt указывал на PID 39420 и commit `b798461d...` от 2026-10-23; PID не активен. WSL running list содержит только `docker-desktop`. Docker показывает существующий `rag-qdrant-1` и сервисы `event-foundry`; посторонние сервисы не изменялись. Тот же Qdrant контейнер ранее был запущен командой `docker start` с прежним volume `rag_qdrant_storage`; коллекции не создавались и не менялись.

## Запуск и runtime receipt

Перед запуском активного прежнего Python worker не было; запущен один процесс `python -u bot.py`, `Application started`.

**Runtime receipt:** `.local/bot-runtime.json` — PID `35844`, engine `source_first`, allowlist count 3 и SHA-256 списка (ID не сохраняются в receipt), commit `86a86404ddd50efa88ba2b7ba69c8cc6fdef26a7`, Groq / `openai/gpt-oss-20b` / reasoning effort `medium`, Qdrant `knowledge_organized_stage2_20261022`, 934 points. Receipt покрывает 26 файлов `bot.py` и `app/*.py`; после запуска проверено, что текущие SHA совпадают, PID активен, в Windows работает один Python процесс, а commit совпадает с HEAD. Qdrant REST status `green`. Worker ждёт обращений; живых пользовательских LLM вызовов пока нет. Команды запуска/остановки/rollback и экспорта — в [README](README.md).

## Остающиеся ограничения

- Исторический Source-first V1.2-B quality gate провален; интерактивный пилот собирает случаи, но сам по себе не доказывает улучшение.
- Секция целиком сохраняет предупреждения/порядок, однако полнота последовательности всё ещё зависит от качества исходного approved-раздела и отбора pipeline.
- Planner использует LLM только для выбора раздела/уточнения/эскалации; оценки причины модели диагностические, технический текст Planner пользователю не показывается.
- Кнопка специалиста сохраняет запрос в существующей локальной очереди; подтверждённой реальной доставки сотрудникам нет. Интерфейс старого callback явно сообщает, что доставка не настроена.
- Пилот сохраняет трассы в прежней SQLite, где уже есть история, а экспорт делает отдельный локальный обезличенный JSONL. Не включайте сырой файл базы или исходные логи в Git.
- Текущие незакоммиченные изменения включают подготовленный ранее `experiments/telegram_source_first_pilot/`; он не запускается и не используется как runtime. Commit/push не выполнялись.
