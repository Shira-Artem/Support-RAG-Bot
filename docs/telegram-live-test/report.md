# Подготовка живого Telegram-теста — 22.10.2026

**Готов к 5 ручным диалогам через Telegram. Два блокера исправлены. После явного разрешения пользователя бот переключён и перезапущен на knowledge_sprint_v1_20261022_quality_gate. Проверка завершена 22.10.2026 в 10:49 МСК.**

## Исправления и трассировка

`atol-report`: приоритет объектов отдавал ФН, даже когда пользователь просил посмотреть отчёты, а замена ФН была условием. Добавлен самостоятельный объект report и операция view_reports. Основной объект связывается с запрошенным действием перед обстоятельствами «после/до/при»; поддержан и вынесенный перед глаголом объект. Query сохраняет последний явный запрос клиента с видом отчёта, а routing использует активный кабинет. Поэтому смена сервиса не оставляет прежний кабинет в query.

`role`: прежнее правило безусловно назначало assign_role при слове «роль». Теперь учитываются действие и его объект: создать роль → create_role; назначить → assign_role; изменить права/роль пользователя → change_permissions; создать пользователя с ролью → add_employee. Новое create_role добавлено в query builder, operation gate и проверку частичных доказательств. Нет полной процедуры — остаются правильная задача и полезный partial; создание пользователя её не подменяет.

Обобщённые правила проверены вариантами с перестановкой обстоятельства, разными глаголами и назначением роли новому пользователю. Regex под один текст вопроса не добавлялся. Карточки и Qdrant не переиндексировались.

Состояние, сервис, query, кандидаты, все отказы и итоговый контекст до/после: [retrieval-before.json](retrieval-before.json), [retrieval-after.json](retrieval-after.json). Полный diff относительно HEAD: [changes.diff](changes.diff).

| Сценарий | До | После на STAGING |
|---|---|---|
| A: права существующего сотрудника | change_permissions / aqsi-online-account-edit-user | change_permissions / aqsi-online-account-edit-user; sufficient=False, evidence=partial |
| B: список касс АТОЛ | list / atol-online-18126-monitoring | list / atol-online-18126-monitoring; sufficient=True, evidence=relevance_only |
| C: ФН 235 | diagnose / evotor-fn-235-360004715213 | diagnose / evotor-fn-235-360004715213; sufficient=True, evidence=relevance_only |
| D: отчёты АТОЛ | check / atol-online-18220-blocked | view_reports / atol-online-account-cash-reports; sufficient=True, evidence=relevance_only |
| E: создание роли | assign_role / aqsi-online-account-add-user | create_role / aqsi-online-account-create-role; sufficient=False, evidence=partial |

Повторены прежние 15 запросов на реальных dense/BM25/RRF, а также все 20 подготовленных реплик с последовательным состоянием пяти диалогов. Проверены ожидаемые операция, сервис, выбранная карточка или честное отсутствие знаний: **20/20**. Подробности: [dialogs-retrieval.json](dialogs-retrieval.json). Вызовов Groq — **0**. Partial для прав и создания роли сохраняется; это ограничение источника, не ошибка маршрутизации.

## Фактическое состояние

HEAD: `9bf892be3880b015f1bdaeb76ce9f63385ee3c75`. В начале этапа рабочее дерево было чистым, сейчас исправления не закоммичены. Commit/push не выполнялись. Файлы: шесть изменённых (`app/dialogue_state.py`, `app/rag_query.py`, `app/retrieval_pipeline.py`, `app/response_grounding.py`, `app/answer_service.py`, `bot.py`), плюс runtime receipt, read-only exporter и адресные тесты.

До переключения: worker PID **11176**, venv launcher **26976**, CURRENT knowledge_demo. После разрешения «Переключить и перезапустить» эта idle-пара остановлена. Новый единственный polling worker — PID **28228**, его venv launcher — **26284** (launcher не является вторым polling worker). Startup 22.10.2026 10:48 МСК, Application started подтверждён. Instance-lock занят. Новый runtime receipt подтверждает фактический store.collection, 927 чанков, Groq/openai/gpt-oss-20b/medium; SHA-256 загруженных исходников совпадают с подготовленным кодом. Секреты не сохранялись. Доказательства: [switch-verification.json](switch-verification.json).

Фактическая коллекция бота: **knowledge_sprint_v1_20261022_quality_gate, 269 / 927**. CURRENT **knowledge_demo, 264 / 928** сохранена. Model/effort сохранены. Обе SQLite до/после перезапуска байтово идентичны; незавершённых генераций при preflight — 0. Резервные копии: `.local/backups/telegram-live-20261022T074745Z/`. `.env` не менялся. [readiness.json](readiness.json).

## Конкретный план переключения и отката

План доступен в `.local/telegram-live-test/switch.ps1`; вызов без -Execute печатает план и ничего не переключает. Исполнять -Execute только после подтверждения пользователя в этом чате. Работающий бот до разрешения не останавливался.

1. Повторно проверить backend, medium/20B и наличие целевой коллекции; убедиться в отсутствии pending-запросов. Сделать обе согласованные резервные копии SQLite через backup API в `.local/backups/telegram-live-<UTC>/`. Исходные базы не очищать и не мигрировать вручную.
2. Проверить единственный worker и его launcher по полному пути этого checkout. Остановить только эту idle-пару. Старый worker не имеет graceful-control endpoint; остановка применяется только после проверки pending=0, в согласованное окно без сообщений пользователя.
3. Запустить скрыто с process-only QDRANT_COLLECTION=knowledge_sprint_v1_20261022_quality_gate и локальным кэшем embeddings. `.env` не меняется; модель и reasoning не переопределяются.
4. Проверить новый worker/launcher, instance-lock и новый `Application started`. Новый `.local/bot-runtime.json` берёт collection из фактического `rag.retriever.store`, а model/effort — из Settings. Receipt содержит PID, точный HEAD и SHA-256 исходников незакоммиченной версии. Phase receipt означает инициализацию до polling: сам факт старта polling проверяется отдельно по журналу/процессу.
5. После успешной проверки записать marker read-only exporter и только затем дать сигнал к ручным сообщениям. Никаких автоматических пробных Groq-запросов.

Переключение после разрешения:

```powershell
& .local/telegram-live-test/switch.ps1 -Target staging -Execute
```

Быстрый откат к CURRENT после проверки отсутствия pending (в согласованное окно):

```powershell
& .local/telegram-live-test/switch.ps1 -Target current -Execute
```

Откат возвращает коллекцию knowledge_demo; текущие исправления кода на диске сохраняются. Данные обеих коллекций остаются нетронутыми. Если новый процесс ещё стартует, второй worker не запускается; сначала проверяется состояние первого.

## Сохранение 20 сообщений

После одобренного переключения и проверки polling выполнить:

```powershell
.venv/Scripts/python.exe -m scripts.capture_telegram_manual_test mark
```

Это сохраняет только маркер последнего id, план и runtime receipt. После пяти диалогов:

```powershell
.venv/Scripts/python.exe -m scripts.capture_telegram_manual_test capture
```

Экспорт — `.local/telegram-live-test/diagnostics-20.json`. Сохраняются 20 клиентских сообщений и 20 ответов со всеми исходными diagnostics: state, service, operation, query, selected/rejected, причины, контекст, raw_model_text, validation/repair, usage/model/effort. Новый `Answer.retrieval_collection` фиксирует фактическую коллекцию в каждом ответе без изменения схемы SQLite.

complete=True выставляется только при пяти диалогах по четыре вопроса, 20 завершённых ответах, целевой коллекции во всех 20 diagnostics и model/provider/effort=GPT-OSS 20B/Groq/medium. Неполный экспорт сохраняется как incomplete, без выдуманных ответов. Записи пользователя не перезаписываются; SQLite открывается в mode=ro.

**135 тестов прошли.** Новые проверки: варианты обоих дефектов, сохранение последнего запроса при смене кабинета, partial без LLM, receipt из фактического store вместо env и read-only capture всех 20 пар. Web fallback/reranker не подключались. Новых знаний или approved-статусов не добавлялось.

## Следующий шаг

Переключение разрешено и выполнено, операционных блокеров нет. Marker создан после проверки polling: after_message_id=62. Можно отправлять подготовленные 20 вопросов. После сообщения пользователя о завершении сохранить диагностику через capture; автоматических Groq-запросов не выполнялось. Полнота процедуры создания роли и конкретных полномочий остаётся ограничением базы: ожидается честный partial, это проверяется живым тестом.

Подготовленные вопросы: [dialogs.md](dialogs.md).
