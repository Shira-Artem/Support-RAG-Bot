# Source-first Telegram: разбор первых живых обращений

Дата: 2026-10-25. Статус: исправления реализованы в рабочем дереве; до завершения проверок и подтверждения обновлённого Telegram worker ручной тест пока не объявляется готовым.

## Фактический runtime и сохранённые данные

- SQLite трассы прочитаны только через `mode=ro`; обезличенная выборка — [live_traces_anonymized.jsonl](live_traces_anonymized.jsonl). Telegram/chat/message/task IDs удалены. Внутренние тексты и токены не выводились.
- Перед остановкой проверен процесс: PID `35844`, `python.exe -u bot.py`, единственный `bot.py` polling worker. Runtime receipt сохранён в [runtime_receipt_before_restart.json](runtime_receipt_before_restart.json), SHA-256 receipt: `9575D3EA7F8CD9A971E17D62D8E1B54D3D80EAB611295ABD7352384DDBE49A84`.
- Receipt фиксировал `source_first`, Groq `openai/gpt-oss-20b` / medium, коллекцию `knowledge_organized_stage2_20261022`, 934 points, три разрешённых ID (только count/hash), базовый commit `86a86404ddd50efa88ba2b7ba69c8cc6fdef26a7`.
- Никаких SQLite/Qdrant write, индексации или LLM вызовов для диагностики не было.

## Полный путь и точные причины

### 1. «Привет! Помоги с ОФД»

Путь: Telegram свободный текст → `DialogueManager` сохранил активную задачу с `intent=unknown`, `operation=unknown`, `expected.slot=task`, `reason=task_not_specific` → `SourceFirstService.answer` вызвал узкий `classify_user_turn`, который классифицировал фразу как `task` → `build_rag_query` построил query из испорченного root span «ПРивет помоги купить офд» и исходного уточнения → Hybrid Search → все близкие документы получили `task_unresolved` (в том числе документ Эвотор, не выбран) → Planner и source verification не запускались → renderer ответа не запускался → runtime эскалировал как `insufficient_applicable_evidence` через 424 ms, 0 токенов.

Точная причина: `app/source_first_service.py::SourceFirstService.answer` переходил к поиску, не проверяя `state.expected`, `analysis_required` и неразрешённую `operation`; затем ветка отсутствия применимых результатов эскалировала вместо уточнения. `DialogueState` уже содержал безопасный вопрос, но сервис его игнорировал. Исправление: общий gate незавершённой задачи использует `DialogueState` и не вызывает retrieval; неразрешённая задача уточняется и прекращает цикл после двух повторных уточнений.

### 2. «Что такое ОФД?»

Путь: Telegram → `DialogueState(intent=general, operation=explain)` → query «Что такое ОФД» → Stage2 Hybrid Search выбрал approved `atol-online-11256-what-is-ofd`, heading «Вопрос пользователя» → `_source_sections` нашёл локальный approved-файл, но отбросил секцию до Planner → точный ответный renderer не запускался → эскалация `source_integrity_mismatch` через 604 ms, 0 токенов.

Точная причина — несовпадающая retrieval-метаинформация, а не изменённый approved Markdown или SHA: локальный YAML задаёт `task_category=ofd_connection`, `operations=[explain_ofd]`; Stage2 хранит stale `operations=[check_transmission]`, а диагностика pipeline нормализует категорию в `receipt_transmission`. Сверка `app/source_first_service.py::_source_sections` сравнивала нормализованное поле Qdrant с сырым YAML. Одновременно старый operation в Stage2 действительно противоречит approved-источнику. Проверки SHA/status/heading отключать нельзя; для исправления используется существующая V1.2-B коллекция Stage3, чьи reviewed metadata согласуются с approved front matter. Код сравнивает одинаковую нормализованную проекцию локального источника и Qdrant.

Дополнительный контрактный дефект: retrieval расширил найденный документ тремя sibling sections, но `_source_sections` оставил только heading из первичного ranked candidate — «Вопрос пользователя». Содержательная секция «Что проверено по инструкции производителя» и секция области применения «Важное ограничение / передача специалисту» не доходили до Planner. `app/source_first_service.py::_source_sections` теперь проверяет каждую exact section, возвращённую для уже выбранного документа, сверяет её Qdrant metadata с локальным approved источником и передаёт эти секции в Planner. Информационные вопросы не требуют процедурной секции; ответ по вендорскому материалу атрибутируется к подтверждённой области применения.

### 3. «ОФД как проверить срок» (в SQLite сохранено: «ОФД как проверит срок»)

Путь: Telegram → `DialogueState(intent=unknown, operation=check)`, сервис/производитель не подтверждены → Stage2 Hybrid Search через `_unresolved_task_fallback` выбрал approved `evotor-ofd-subscription-8865646794770`, heading «Возможная причина» → Planner выбрал его и выставил `applicability_confirmed=true`, `order_confirmed=true` → old code сверил идентичные Stage2/local metadata для этого документа, но не проверил известную клиенту область действия → renderer дословно выдал инструкцию Эвотор как общий ответ (1 195 токенов, около 1.8 s).

Точная причина: `app/retrieval_pipeline.py` разрешал lexical `unresolved_task_fallback`; `app/source_first_service.py::answer` считал `Planner` подтверждение достаточным, хотя источник задавал `service=Эвотор`, а клиент не называл сервис. Отсутствие client scope факта фактически трактовалось как совпадение. Исправление: общий gate сравнивает service/manufacturer/model из approved source с подтверждёнными сущностями именно активной `DialogueState`; если необходимого факта нет — задаёт уточнение, если он противоречит источнику — не публикует процедуру. Planner не может переопределить этот gate. Полный точный раздел и его условия остаются обязательными.

## Stage2 и V1.2-B Stage3

Сравнение только read-only, результаты: [collection_comparison.json](collection_comparison.json). `.env` указывал Stage2, а `experiments/vnext/stage3_retrieval.py` V1.2-B использовал `knowledge_stage3_retrieval_20261022`.

| Проверка | Stage2 | Stage3 | Итог |
|---|---:|---:|---|
| Points | 934 | 934 | одинаково |
| Vector size | 384 | 384 | одинаково |
| Approved / draft points | 672 / 262 | 672 / 262 | одинаково |
| Document IDs | 269 | 269 | одинаково |
| Совпавшие point IDs | 934 | 934 | идентичны |
| Документы с различием metadata/chunk inventory | — | — | 10 |

Изменения затрагивают operation/task metadata, среди документов есть `atol-online-11256-what-is-ofd`: Stage2 `check_transmission`, Stage3 `explain_ofd`. Тексты/идентификаторы в этих коллекциях не пересоздавались. Stage2 и Stage3 не считаются взаимозаменяемыми, даже при одинаковых point IDs. После исправления runtime должен явно запускаться с существующей Stage3 коллекцией через process env; `.env` и содержимое обоих индексов не меняются.

## Исправления и проверки

- `app/source_first_service.py`: проверка незавершённой задачи до retrieval; ограничение повторных уточнений; local/Qdrant metadata сравниваются после одной нормализации; scoped procedures требуют совпадения с фактами клиента; определения могут брать не-процедурный approved материал и сопровождаются attribution к service/manufacturer/model; exact SHA/status/section checks сохранены.
- `tests/test_source_first_dialogue_contract.py`: 10 regression cases на неполную задачу, независимый перефраз, прекращение цикла, Stage3 integrity, fail-closed Stage2 stale operation, все sibling sections определения, сохранение атрибуции/ограничения, уточнение vendor-specific service, Qdrant failure и high-risk stop.
- Целевые тесты: `python -m pytest tests/test_source_first_dialogue_contract.py tests/test_dialogue_state.py tests/test_dialogue_state_v21.py tests/test_pre_retrieval_intent.py tests/test_retrieval_pipeline.py -q` → **53 passed**. Полный набор: `python -m compileall -q app bot.py tests/test_source_first_dialogue_contract.py` passed; `python -m pytest -q` → **333 passed, 13 dependency deprecation warnings**.
- Read-only Qdrant smoke на Stage3 (0 LLM calls): свободный вопрос определения выбрал approved `atol-online-11256-what-is-ofd`; все три exact sections («Вопрос пользователя», «Что проверено по инструкции производителя», «Важное ограничение / передача специалисту») прошли локальную approved/SHA/heading/metadata сверку. Процедурный вопрос без сервиса выбрал `evotor-ofd-subscription-8865646794770`; обе exact sections прошли verifier, а новый scope gate требует уточнить сервис/ОФД прежде чем Planner/rendering опубликуют процедуру.
- Первый smoke-скрипт завершился собственной ошибкой вывода (`SearchResult.document_id` вместо `SearchResult.metadata.document_id`); скрипт поправлен, повторный read-only smoke прошёл. Это не было изменением runtime и не приводило к записям.
- Qdrant client 1.19.1 предупредил, что сервер 1.15.4 отличается по версии; read-only search работал. Это остаётся эксплуатационным предупреждением.
- Полных ручных оценок качества, live Telegram разговоров после исправления и новых LLM вызовов не было. Успех pytest не является допуском к оценке качества.

## Оставшиеся шаги/ограничения

## Обновлённый worker

- Перед остановкой PID `35844` проверен как единственный `python.exe -u bot.py`, его receipt сохранён. После Ctrl+C процесс отсутствовал.
- Первый запуск с process-only коллекцией корректно выбрал Stage3, но запустил legacy режим из-за отсутствовавшего в новой оболочке `RAG_ENGINE`. Его receipt отдельно сохранён как [runtime_receipt_wrong_engine_stopped.json](runtime_receipt_wrong_engine_stopped.json); процесс сразу остановлен, повторный запуск не перекрывался.
- Второй запуск выполнен одним процессом с `RAG_ENGINE=source_first` и `QDRANT_COLLECTION=knowledge_stage3_retrieval_20261022`. Telegram application сообщил `Application started`.
- Актуальный receipt: [runtime_receipt_after_restart.json](runtime_receipt_after_restart.json), SHA-256 `A436617E3DD69E487D6AF158689D5ED1E5215B0F151185948479AEA8CDD2C696`. PID `1508`; одна команда `python -u bot.py`; engine `source_first`; Stage3, 934 points; Groq GPT-OSS 20B / medium; allowlist count 3 (ID сохранены только как hash); 26 runtime file hashes, расхождений SHA = 0; commit snapshot `367e5dbf884c42f47953b4b1959731b7d8714a50` (изменения этого задания не закоммичены).
- Не выполнялись реальные Groq-вызовы после изменений и не отправлялся synthetic Telegram turn. Worker готов принимать самостоятельный ручной тест пользователя. Полезность по произвольным вопросам и multi-turn после исправления ещё не установлена.

## Оставшиеся ограничения

1. Следующий Telegram ручной тест обязателен; проверить свободный диалог, уточнение задачи и области, definition, multi-turn и specialist button. Качество по произвольной базе пока не оценено.
2. Не исправлены возможные ошибки самого `DialogueManager` нормализации текста (root span «купить»), старые stale metadata в Stage2 и предупреждение о разнице версий Qdrant клиента/сервера. Worker использует Stage3 и проверки целостности не обходит.
3. Кнопка специалиста использует прежнюю локальную очередь/feedback flow; реальная передача сотрудникам не подключена.

Коммитов и push не было.
