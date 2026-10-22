# STAGING RAG Quality Gate — 22.10.2026

**A/B/C исправлены и проверены на реальном Qdrant. Для полного ручного LLM-теста всех 15 сценариев STAGING пока не готова: остаются ровно два блокера состояния задачи, перечисленные в конце.** Для ограниченной проверки A/B/C подготовлена отдельная коллекция, но запусков Groq и переключения бота не было.

## Данные и границы проверки

- CURRENT: `knowledge_demo`, 264 документа / 928 чанков. Оригинальная STAGING: `knowledge_sprint_v1_20261021_final`, 269 / 927. Их payload и векторы до/после совпали побитово по хешам.
- Новая STAGING: `knowledge_sprint_v1_20261022_quality_gate`, также 269 / 927. Она клонирует исходную STAGING; наложены только 4 правки метаданных, без новых статей и без удаления чанков (`indexed=4`, `removed=0`). Создание: [creation.json](creation.json).
- Сравнены точно те же 15 запросов и последовательности клиентских реплик из `docs/knowledge-sprint-v1/cases.json`. Embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384, Cosine. Реальные dense + BM25 + RRF; без символьной подмены поиска и без LLM.
- Колонки «после» в обоих корпусах получены новым кодом Quality Gate. Это отдельный read-only runner; работающий Telegram продолжает использовать загруженный ранее код и CURRENT. Бот не перезапускался.
- SQLite диалогов и оценок не открывались для записи: файлы до/после байтово идентичны. PID и время старта worker/launcher остались 11176/26976, 21.10.2026 19:18. [safety.json](safety.json).

## A. Релевантность не равна полноте

Корневая причина: раньше достаточность была `bool(docs) && relevance.score >= 0.62`. Совпадение service/task/operation не проверяло поля формы, завершение процедуры или полномочия. Более того, статья повторно нормализовалась с `operations=[]`, поэтому явный список операций терялся и слова из ограничений могли снова классифицировать создание пользователя как изменение прав.

Дополнительная обнаруженная причина потери полезного partial: dense мог выбрать раздел «Граница подтверждения», а expansion отбрасывал отдельный chunk «Открыть редактирование»: в нём есть «Пользователи», но нет буквального слова «пользователь» из списка lexical evidence. Теперь явная операция подтверждённого документа также допускает его соседний фрагмент; service/task-проверки сохранены.

Изменение: `RetrievalResult` отдельно хранит `evidence_status`, `missing_evidence` и `supported_steps`. Для access `full` требует source-reviewed coverage нужной операции, URL/даты и полного подтверждённого предложения в реально отправляемом контексте. Coverage общей операции не подтверждает названную клиентом роль, его цели и запреты: они дают partial. Отсутствующая coverage в старой карточке не становится full автоматически.

Явные operations теперь сохраняются при сборке статьи. `edit_user` является релевантной частичной инструкцией для change_permissions, но не доказательством полного изменения прав. Текст границ/ограничений не служит положительным шагом. Создание нового пользователя не подставляется в ответ о редактировании существующего.

При partial AnswerService возвращает только подтверждённые предложения с названием их раздела и понятным описанием пробела. Это полезный ответ без генерации. При отсутствии подтверждённых шагов остаётся прежний отказ. Для остальных task families `evidence_status=relevance_only`: здесь новая проверка source coverage не заявляется, а существующий sufficient остаётся прежним task-gate. Это явно видно, в частности, в запросе 61.

Реальный пример №51 (без LLM):

> Открыть редактирование:
> В списке «Пользователи» найдите существующую запись.
> Её меню с троеточием позволяет выбрать изменение или удаление.
>
> Полный порядок изменения прав существующего пользователя в источнике не подтверждён.

Для №53 дополнительно указывается, что конкретная роль и её полномочия для требований клиента не подтверждены. `sufficient=False` здесь не приводит к потере полезной части инструкции.

## B. АТОЛ Онлайн / Первый ОФД

State верно содержал АТОЛ Онлайн. Ошибка возникала после RRF: service выводился из `atol_online/` (издатель/связанный продукт), а task_category=cash_list — из вложенного шага «проверьте список касс» в статье **активации**. В результате релевантная по словам инструкция другого кабинета проходила gate и становилась первой. Это не ошибка dense, фильтра Qdrant или состояния клиента.

Исправлены два узких места. Основная тема заголовка «Активация…» имеет приоритет перед упоминанием списка в теле. Кроме того, `procedure_service` отдельно задаёт кабинет выполнения действий, независимо от издателя. Для этой статьи он равен «Первый ОФД». Gate и expansion проверяют активные клиентские сущности: чужой кабинет не подставляется вместо текущего. Если клиент прямо установил этот кабинет как текущий либо активную интеграционную задачу с ним, документ разрешён — это проверено отдельным тестом.

Основание метаданных: [официальная инструкция АТОЛ](https://help.atol.online/article/23349) начинает действия с входа в кабинет Первого ОФД. Названия UI и новые права не добавлялись. На `atol-list` теперь выбран `atol-online-18126-monitoring`; `atol-online-23349-activate-first-ofd` отклонён как другая задача, а в новой STAGING также как другая область выполнения.

## C. Путь ФН 235

До исправления `evotor-fn-235-360004715213` уже был правильным top-1. Dense=0.5329839, BM25=23.46359, RRF=0.045528. Затем normalize_metadata выбирал receipt_transmission по объяснению причины (нет передачи в ОФД), раньше, чем проверял тему статьи об ошибке ФН. Штатный pipeline отклонял единственный подходящий документ: `task_mismatch:receipt_transmission!=error_diagnosis`. Поэтому expansion и финальный контекст его не получали.

Теперь для документов category=fn/kkt явная диагностика ошибки в заголовке имеет приоритет над упоминаниями передачи в теле. Тот же документ и те же scores получают task_category=error_diagnosis и operation=diagnose_error; оба раздела («Признаки», «Смысл и безопасная проверка») находятся в финальном контексте. Карточка ФН 235 не менялась.

Защита от расширения допуска: общая инструкция ОФД, лишь упоминающая ФН 235 в теле, всё ещё отклоняется; другой производитель не проходит. Фильтры точного кода, производителя и модели не ослаблены; существующие тесты точных кодов также прошли. Контроль ФН 234 не ухудшился.

## Реальный retrieval: до / после

«До» — сохранённый прошлый sprint; «после» — новый код на CURRENT и новой STAGING. В ячейках указаны первый выбранный документ и sufficient. T/F — true/false. Все выбранные документы, все отказы с причинами, top-10 со scores и контекст — в [retrieval.json](retrieval.json). У каждой пары есть `change_from_previous`, включая added/removed selected и изменение причин отказа.

| ID | Запрос | CURRENT до → после | STAGING до → после | Результат |
|---|---|---|---|---|
| 49 | Как завести учётку для сотрудника в aQsi Online? | aQsi/add-user (T) → aQsi/add-user (F) | aQsi/add-user (T) → aQsi/add-user (T) | см. разбор |
| 51 | Он уже есть, мне нужно изменить ему права. | aQsi/add-user (T) → aQsi/add-user (F) | aQsi/edit-user (T) → aQsi/edit-user (F) | A: partial |
| 53 | Хочу, чтобы он мог смотреть кассы и отчёты, но не менять настройки. | aQsi/add-user (T) → aQsi/add-user (F) | aQsi/edit-user (T) → aQsi/create-role (F) | A: partial |
| 55 | А если у нас АТОЛ Онлайн — там это делается так же? | — (F) → — (F) | — (F) → — (F) | см. разбор |
| 57 | Как посмотреть список моих касс в личном кабинете Платформы ОФД? | Платформа/cash-monitoring (T) → Платформа/cash-monitoring (T) | Платформа/cash-monitoring (T) → Платформа/cash-monitoring (T) | см. разбор |
| 59 | А теперь мне нужно найти чек за прошлый месяц. | Платформа/receipt-search (T) → Платформа/receipt-search (T) | Платформа/receipt-search (T) → Платформа/receipt-search (T) | см. разбор |
| 61 | И можно найти его по номеру ФН? | Платформа/receipt-search (T) → Платформа/receipt-search (T) | Платформа/receipt-search (T) → Платформа/receipt-search (T) | см. разбор |
| fd | Как найти чек по номеру ФД в Платформе ОФД? | Платформа/receipt-search (T) → Платформа/receipt-search (T) | Платформа/receipt-search (T) → Платформа/receipt-search (T) | см. разбор |
| fp | Как найти чек по ФП в Платформе ОФД? | Платформа/receipt-search (T) → Платформа/receipt-search (T) | Платформа/receipt-search (T) → Платформа/receipt-search (T) | см. разбор |
| role | Как создать новую роль в aQsi Online? | aQsi/add-user (T) → aQsi/add-user (F) | aQsi/add-user (T) → aQsi/add-user (F) | partial; блокер state |
| aqsi-list | Где посмотреть список касс в aQsi Online? | — (F) → — (F) | aQsi/monitoring (T) → aQsi/monitoring (T) | см. разбор |
| atol-list | Как посмотреть список касс в АТОЛ Онлайн? | АТОЛ/Первый ОФД (T) → АТОЛ/monitoring (T) | АТОЛ/Первый ОФД (T) → АТОЛ/monitoring (T) | B: свой кабинет |
| atol-report | Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн? | АТОЛ/monitoring (T) → АТОЛ/monitoring (T) | АТОЛ/blocked-FN (T) → АТОЛ/blocked-FN (T) | блокер |
| fn234 | Эвотор ошибка ФН 234 | Эвотор/FN234 (T) → Эвотор/FN234 (T) | Эвотор/FN234 (T) → Эвотор/FN234 (T) | см. разбор |
| fn235 | Эвотор ошибка ФН 235 | — (F) → Эвотор/FN235 (T) | — (F) → Эвотор/FN235 (T) | C: выбран |

### Разбор каждого запроса и причин отбора

**49. Как завести учётку для сотрудника в aQsi Online?**

Query: `сервис: aQsi Online — добавление сотрудника`

Создание пользователя в новой STAGING остаётся full: проверены конкретные шаги, URL и дата source review. CURRENT без coverage теперь даёт полезный partial, а не заявляет полную проверку.

CURRENT: выбраны `aqsi-online-account-add-user`; sufficient=False, evidence_status=partial.

- `aqsi-online-account-add-user`: gate пройден; RRF=0.05, dense=0.76872003, BM25=15.90328.
- `atol-online-12148-company-registration`: service_mismatch_or_unlabeled, task_unconfirmed; RRF=0.045688, dense=0.67914355, BM25=8.92116.
- `aqsi-online-account-register-account`: operation_mismatch:add_employee; RRF=0.039527, dense=0.6074325, BM25=6.35271.

STAGING: выбраны `aqsi-online-account-add-user`; sufficient=True, evidence_status=full.

- `atol-online-12148-company-registration`: service_mismatch_or_unlabeled, task_unconfirmed; RRF=0.047371, dense=0.67914355, BM25=9.01637.
- `atol-online-14749-incoming-documents`: service_mismatch_or_unlabeled, task_mismatch:edo!=access; RRF=0.040598, dense=0.6078621, BM25=6.73898.
- `aqsi-online-account-register-account`: operation_mismatch:add_employee; RRF=0.039325, dense=0.6074325, BM25=6.41669.

**51. Он уже есть, мне нужно изменить ему права.**

Query: `сервис: aQsi Online — изменение прав существующего сотрудника`

A исправлен: edit-user релевантен, sufficient=False/partial. В supported_steps сохранены выбор существующей записи и меню с троеточием; поля смены роли и завершение операции не придуманы.

CURRENT: выбраны `aqsi-online-account-add-user`; sufficient=False, evidence_status=partial.

- `aqsi-online-account-add-user`: gate пройден; RRF=0.048925, dense=0.7406114, BM25=11.2259.
- `aqsi-online-account-register-account`: operation_mismatch:change_permissions; RRF=0.04152, dense=0.61718655, BM25=6.35271.
- `atol-online-12790-catalog-cms-banks`: service_mismatch_or_unlabeled, task_unconfirmed; RRF=0.034568, dense=0.57760596, BM25=5.14667.

STAGING: выбраны `aqsi-online-account-edit-user`, `aqsi-online-account-create-role`; sufficient=False, evidence_status=partial.

- `atol-online-14749-incoming-documents`: service_mismatch_or_unlabeled, task_mismatch:edo!=access; RRF=0.045652, dense=0.6578746, BM25=6.73898.
- `aqsi-online-account-register-account`: operation_mismatch:change_permissions; RRF=0.04152, dense=0.61718655, BM25=6.41669.
- `atol-online-12790-catalog-cms-banks`: service_mismatch_or_unlabeled, task_unconfirmed; RRF=0.034085, dense=0.57760596, BM25=5.098.

Пробелы: `permission_change_workflow_unverified`.

**53. Хочу, чтобы он мог смотреть кассы и отчёты, но не менять настройки.**

Query: `сервис: aQsi Online — изменение прав существующего сотрудника — цель: чтобы он мог смотреть кассы и отчёты — ограничения: но не менять настройки`

A исправлен: sufficient=False/partial, отмечены и неполный workflow, и непроверенные полномочия. Create-role выше по relevance, однако безопасный частичный ответ использует подтверждённые шаги edit-user, а не предлагает создавать новую запись.

CURRENT: выбраны `aqsi-online-account-add-user`; sufficient=False, evidence_status=partial.

- `aqsi-online-account-add-user`: gate пройден; RRF=0.046517, dense=0.7434541, BM25=11.2259.
- `aqsi-online-account-settings`: operation_mismatch:change_permissions; RRF=0.042143, dense=0.6372303, BM25=10.77136.
- `atol-online-22060-change-parameters`: service_mismatch_or_unlabeled, task_unconfirmed; RRF=0.039777, dense=0.5906749, BM25=13.97829.

STAGING: выбраны `aqsi-online-account-create-role`, `aqsi-online-account-edit-user`; sufficient=False, evidence_status=partial.

- `atol-online-14749-incoming-documents`: service_mismatch_or_unlabeled, task_mismatch:edo!=access; RRF=0.041667, dense=0.71365696, BM25=9.44567.
- `atol-online-22060-change-parameters`: service_mismatch_or_unlabeled, task_unconfirmed; RRF=0.038403, dense=0.5906749, BM25=14.00405.
- `aqsi-online-account-register-account`: operation_mismatch:change_permissions; RRF=0.036748, dense=0.68969756, BM25=8.39702.

Пробелы: `permission_change_workflow_unverified`, `requested_role_or_permissions_unverified`.

**55. А если у нас АТОЛ Онлайн — там это делается так же?**

Query: `сервис: АТОЛ Онлайн — изменение прав существующего сотрудника — цель: чтобы он мог смотреть кассы и отчёты — ограничения: но не менять настройки`

Отказ сохранён: инструкции доступа АТОЛ нет. ЭДО не выбирается вместо управления сотрудниками.

CURRENT: выбраны нет; sufficient=False, evidence_status=none.

- `atol-online-25850-contacts`: task_unconfirmed; RRF=0.041558, dense=0.6427861, BM25=10.50575.
- `atol-online-22060-change-parameters`: task_unconfirmed; RRF=0.040426, dense=0.5765892, BM25=17.40277.
- `atol-online-11251-replacement-reasons`: task_unconfirmed; RRF=0.040258, dense=0.5858873, BM25=13.36566.

STAGING: выбраны нет; sufficient=False, evidence_status=none.

- `atol-online-14749-incoming-documents`: task_mismatch:edo!=access; RRF=0.048925, dense=0.7326081, BM25=13.39137.
- `atol-online-25850-contacts`: task_unconfirmed; RRF=0.040765, dense=0.6427861, BM25=10.46382.
- `atol-online-22060-change-parameters`: task_unconfirmed; RRF=0.040686, dense=0.5765892, BM25=17.44016.

**57. Как посмотреть список моих касс в личном кабинете Платформы ОФД?**

Query: `ОФД: Платформа ОФД — просмотр списка касс`

Без изменения: выбрана инструкция списка и мониторинга касс Платформы ОФД.

CURRENT: выбраны `platformaofd-lkk-cash-monitoring`; sufficient=True, evidence_status=relevance_only.

- `atol-online-23349-activate-first-ofd`: service_mismatch_or_unlabeled, task_mismatch:equipment_setup!=cash_list; RRF=0.044859, dense=0.6323555, BM25=9.77779.
- `platformaofd-connect-kkt-to-lkk`: task_mismatch:equipment_setup!=cash_list; RRF=0.044023, dense=0.53941846, BM25=11.77582.
- `evotor-ofd-settings-reference-20261019`: service_mismatch_or_unlabeled, task_mismatch:equipment_setup!=cash_list; RRF=0.043817, dense=0.5682174, BM25=10.61663.

STAGING: выбраны `platformaofd-lkk-cash-monitoring`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-cash-monitoring`: gate пройден; RRF=0.047032, dense=0.57774144, BM25=21.82242.
- `atol-online-23349-activate-first-ofd`: service_mismatch_or_unlabeled, procedure_service_mismatch:Первый ОФД, task_mismatch:equipment_setup!=cash_list; RRF=0.044859, dense=0.6323555, BM25=9.51444.
- `platformaofd-connect-kkt-to-lkk`: task_mismatch:equipment_setup!=cash_list; RRF=0.043494, dense=0.53941846, BM25=11.29288.

**59. А теперь мне нужно найти чек за прошлый месяц.**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: за прошлый месяц`

Без изменения: выбран поиск чеков с периодом.

CURRENT: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `atol-online-22560-receipt-journal-export`: service_mismatch_or_unlabeled; RRF=0.048958, dense=0.60895544, BM25=28.22798.
- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.048916, dense=0.62546, BM25=24.50881.
- `atol-online-23415-activate-taxcom`: service_mismatch_or_unlabeled, task_mismatch:equipment_setup!=receipt_search; RRF=0.039129, dense=0.6137723, BM25=9.36676.

STAGING: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.05, dense=0.71329564, BM25=35.50271.
- `atol-online-22560-receipt-journal-export`: service_mismatch_or_unlabeled; RRF=0.04866, dense=0.60895544, BM25=27.16937.
- `platformaofd-lkk-cash-search`: task_mismatch:cash_search!=receipt_search; RRF=0.039611, dense=0.52026695, BM25=22.68608.

**61. И можно найти его по номеру ФН?**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: за прошлый месяц; по номеру ФН`

Поведение сохранено. Источник явно не подтверждает прямое поле ФН для чеков; новый access gate не является проверкой поисковых полей. sufficient здесь остаётся старым task-gate, evidence_status=relevance_only.

CURRENT: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.048039, dense=0.6198511, BM25=28.76591.
- `atol-online-23415-activate-taxcom`: service_mismatch_or_unlabeled, task_mismatch:equipment_setup!=receipt_search; RRF=0.046244, dense=0.65119404, BM25=14.21213.
- `atol-online-22560-receipt-journal-export`: service_mismatch_or_unlabeled; RRF=0.045774, dense=0.6006239, BM25=28.22798.

STAGING: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.05, dense=0.7248143, BM25=35.50271.
- `atol-online-22560-receipt-journal-export`: service_mismatch_or_unlabeled; RRF=0.045079, dense=0.6006239, BM25=27.16937.
- `atol-online-23415-activate-taxcom`: service_mismatch_or_unlabeled, task_mismatch:equipment_setup!=receipt_search; RRF=0.044562, dense=0.65119404, BM25=13.99751.

**fd. Как найти чек по номеру ФД в Платформе ОФД?**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: по номеру ФД в Платформе ОФД`

Без изменения: ФД подтверждён карточкой поиска чеков.

CURRENT: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.049727, dense=0.6541854, BM25=36.41868.
- `platformaofd-fn-number-in-lkk`: task_unconfirmed; RRF=0.047183, dense=0.6276852, BM25=24.80321.
- `platformaofd-atol-transmission-checks`: task_mismatch:receipt_transmission!=receipt_search; RRF=0.042641, dense=0.65864944, BM25=13.40592.

STAGING: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.047826, dense=0.6207849, BM25=34.49938.
- `platformaofd-fn-number-in-lkk`: task_unconfirmed; RRF=0.046402, dense=0.6276852, BM25=23.63491.
- `platformaofd-lkk-cash-search`: task_mismatch:cash_search!=receipt_search; RRF=0.045079, dense=0.60256433, BM25=28.49885.

**fp. Как найти чек по ФП в Платформе ОФД?**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: по ФП в Платформе ОФД`

Без изменения: выбран поиск чеков; карточка поиска ККТ отклоняется как другая операция.

CURRENT: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.047619, dense=0.62596, BM25=27.75949.
- `platformaofd-fn-number-in-lkk`: task_unconfirmed; RRF=0.044023, dense=0.5923232, BM25=20.02212.
- `platformaofd-atol-transmission-checks`: task_mismatch:receipt_transmission!=receipt_search; RRF=0.04068, dense=0.63055617, BM25=11.57631.

STAGING: выбраны `platformaofd-lkk-receipt-search`; sufficient=True, evidence_status=relevance_only.

- `platformaofd-lkk-cash-search`: task_mismatch:cash_search!=receipt_search; RRF=0.045591, dense=0.60661876, BM25=25.61578.
- `platformaofd-lkk-receipt-search`: gate пройден; RRF=0.045528, dense=0.60095847, BM25=35.79893.
- `platformaofd-fn-number-in-lkk`: task_unconfirmed; RRF=0.042005, dense=0.5923232, BM25=18.92634.

**role. Как создать новую роль в aQsi Online?**

Query: `сервис: aQsi Online — назначение роли сотруднику`

Ложная полнота снята: sufficient=False/partial. Однако исходное «создать роль» по-прежнему превращается в assign_role. Это остающийся блокер состояния задачи, а не недостаток reranking.

CURRENT: выбраны `aqsi-online-account-add-user`; sufficient=False, evidence_status=none.

- `aqsi-online-account-add-user`: gate пройден; RRF=0.049454, dense=0.7627919, BM25=11.2259.
- `aqsi-online-account-register-account`: operation_mismatch:assign_role; RRF=0.041291, dense=0.6197816, BM25=6.35271.
- `atol-online-26852-payment-object-ffd12`: service_mismatch_or_unlabeled, task_mismatch:receipt_search!=access; RRF=0.036502, dense=0.539454, BM25=6.38925.

STAGING: выбраны `aqsi-online-account-add-user`, `aqsi-online-account-create-role`; sufficient=False, evidence_status=partial.

- `atol-online-14749-incoming-documents`: service_mismatch_or_unlabeled, task_mismatch:edo!=access; RRF=0.044776, dense=0.63634765, BM25=8.59492.
- `aqsi-online-account-register-account`: operation_mismatch:assign_role; RRF=0.039829, dense=0.6197816, BM25=6.41669.
- `atol-online-26852-payment-object-ffd12`: service_mismatch_or_unlabeled, task_mismatch:receipt_search!=access; RRF=0.034337, dense=0.539454, BM25=6.0033.

Пробелы: `access_workflow_unverified`.

**aqsi-list. Где посмотреть список касс в aQsi Online?**

Query: `сервис: aQsi Online — просмотр списка касс`

Без изменения относительно прошлой STAGING: мониторинг первый, Мои кассы также в контексте. CURRENT без нормализованной категории по-прежнему не проходит.

CURRENT: выбраны нет; sufficient=False, evidence_status=none.

- `aqsi-online-account-register-account`: task_mismatch:access!=cash_list; RRF=0.04324, dense=0.5836979, BM25=6.35271.
- `aqsi-online-usecase-retail-physical-vs-cloud`: task_unconfirmed; RRF=0.040962, dense=0.5743123, BM25=5.89264.
- `atol-online-21114-mass-correction`: service_mismatch_or_unlabeled, task_mismatch:receipt_search!=cash_list; RRF=0.040258, dense=0.5282433, BM25=6.81221.

STAGING: выбраны `aqsi-online-account-monitoring`, `aqsi-online-account-my-cash-registers`; sufficient=True, evidence_status=relevance_only.

- `aqsi-online-account-register-account`: task_mismatch:access!=cash_list; RRF=0.040476, dense=0.5836979, BM25=6.41669.
- `aqsi-online-usecase-retail-physical-vs-cloud`: task_unconfirmed; RRF=0.038632, dense=0.6017777, BM25=5.67725.
- `atol-online-21114-mass-correction`: service_mismatch_or_unlabeled, task_mismatch:receipt_search!=cash_list; RRF=0.03746, dense=0.5282433, BM25=6.63987.

**atol-list. Как посмотреть список касс в АТОЛ Онлайн?**

Query: `сервис: АТОЛ Онлайн — просмотр списка касс`

B исправлен в обоих корпусах: выбран мониторинг АТОЛ; статья активации Первого ОФД отклонена. В новой STAGING срабатывает также явный procedure_service gate.

CURRENT: выбраны `atol-online-18126-monitoring`; sufficient=True, evidence_status=relevance_only.

- `atol-online-12790-catalog-cms-banks`: task_unconfirmed; RRF=0.044965, dense=0.7017635, BM25=6.18488.
- `atol-online-23349-activate-first-ofd`: task_mismatch:equipment_setup!=cash_list; RRF=0.044692, dense=0.59364355, BM25=9.14153.
- `atol-online-21114-mass-correction`: task_mismatch:receipt_search!=cash_list; RRF=0.041146, dense=0.5366008, BM25=10.38004.

STAGING: выбраны `atol-online-18126-monitoring`; sufficient=True, evidence_status=relevance_only.

- `atol-online-23349-activate-first-ofd`: service_mismatch_or_unlabeled, procedure_service_mismatch:Первый ОФД, task_mismatch:equipment_setup!=cash_list; RRF=0.044453, dense=0.59364355, BM25=9.0381.
- `atol-online-12790-catalog-cms-banks`: task_unconfirmed; RRF=0.044171, dense=0.7017635, BM25=6.1719.
- `atol-online-21114-mass-correction`: task_mismatch:receipt_search!=cash_list; RRF=0.041463, dense=0.5366008, BM25=10.21935.

**atol-report. Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн?**

Query: `сервис: АТОЛ Онлайн — проверка ФН`

Не исправлялось вне A/B/C: запрос отчётов до retrieval сжимается до «проверка ФН»; STAGING всё ещё выбирает блокировку ФН. Это остающийся блокер.

CURRENT: выбраны `atol-online-18126-monitoring`, `atol-online-18220-blocked`, `atol-online-20054-replacement-process`, `atol-online-11254-test-cashier`, `atol-online-23349-activate-first-ofd`; sufficient=True, evidence_status=relevance_only.

- `atol-online-18126-monitoring`: gate пройден; RRF=0.049727, dense=0.6956766, BM25=8.76267.
- `atol-online-18220-blocked`: gate пройден; RRF=0.04728, dense=0.66916513, BM25=8.31749.
- `atol-online-20054-replacement-process`: gate пройден; RRF=0.047131, dense=0.6833223, BM25=8.23048.

STAGING: выбраны `atol-online-18220-blocked`, `atol-online-20054-replacement-process`, `atol-online-11254-test-cashier`, `atol-online-16568-step7-fn-activation`, `atol-online-11251-replacement-reasons`; sufficient=True, evidence_status=relevance_only.

- `atol-online-18220-blocked`: gate пройден; RRF=0.048039, dense=0.66916513, BM25=8.31112.
- `atol-online-20054-replacement-process`: gate пройден; RRF=0.047883, dense=0.6833223, BM25=8.21319.
- `atol-online-11254-test-cashier`: gate пройден; RRF=0.044002, dense=0.6614718, BM25=7.73102.

**fn234. Эвотор ошибка ФН 234**

Query: `производитель: Эвотор — диагностика ошибки ФН — код ошибки 234`

Контроль: правильная ФН 234 остаётся выбранной в обоих корпусах.

CURRENT: выбраны `evotor-fn-234-360005580254`; sufficient=True, evidence_status=relevance_only.

- `evotor-fn-234-360005580254`: gate пройден; RRF=0.046154, dense=0.5319169, BM25=23.36056.

STAGING: выбраны `evotor-fn-234-360005580254`; sufficient=True, evidence_status=relevance_only.

- `evotor-fn-234-360005580254`: gate пройден; RRF=0.046154, dense=0.5319169, BM25=23.36919.

**fn235. Эвотор ошибка ФН 235**

Query: `производитель: Эвотор — диагностика ошибки ФН — код ошибки 235`

C исправлен в обоих корпусах: тот же правильный top-1 проходит classification, operation gate, expansion и попадает в финальный контекст.

CURRENT: выбраны `evotor-fn-235-360004715213`; sufficient=True, evidence_status=relevance_only.

- `evotor-fn-235-360004715213`: gate пройден; RRF=0.045528, dense=0.5329839, BM25=23.47287.

STAGING: выбраны `evotor-fn-235-360004715213`; sufficient=True, evidence_status=relevance_only.

- `evotor-fn-235-360004715213`: gate пройден; RRF=0.045528, dense=0.5329839, BM25=23.46359.

## Изменённые файлы и минимальный knowledge diff

- `app/retrieval_pipeline.py`: разделение relevance/coverage для access; сохранение явных операций; scope gate для кабинета; приоритет темы статьи; сохранение подтверждённых соседних chunks.
- `app/answer_service.py`: детерминированный полезный partial с явными пробелами, без платного вызова.
- `app/knowledge.py`: два необязательных поля `procedure_service` и `evidence_coverage`, валидация и передача в chunk payload. Старые документы читаются.
- `scripts/compare_knowledge_staging.py`: клонирование исходной STAGING и per-case сравнение с предыдущим отчётом.
- `tests/test_staging_quality_gate.py`: 7 адресных регрессий A/B/C и передачи новых полей. Изменены ожидания в двух существующих тестах (`test_retrieval_pipeline.py`, `test_incident_context.py`): неполный workflow теперь partial, без вызова генератора.

Только четыре Markdown-карточки получили правки front matter, тело не переписывалось. В aQsi add-user отмечено full для создания и partial для назначения роли в рамках создания; edit-user — partial для редактирования/изменения прав; create-role — partial, без обещания непоказанных вложенных полномочий или сохранения. Для активации АТОЛ указаны procedure_service и основная операция активации. Источники проверены 22.10.2026; `status=draft`, verified_at не выставлен.

Официальные основания: [пользователь aQsi](https://aqsi.online/instructions/account/kak-sozdat-novogo-polzovatelya), [роль aQsi](https://aqsi.online/instructions/account/kak-sozdat-novuyu-rol), [активация в Первом ОФД](https://help.atol.online/article/23349). Пробелы в форме изменения и точных правах эти страницы не закрывают; новые кнопки или разрешения не додумывались. Для роли повторно прочитан прямой HTML, поскольку веб-экстрактор показывает только заголовок. URL/status/hash: [sources.json](sources.json).

**Diff относительно рабочего дерева в начале этого Quality Gate**, включая незакоммиченные изменения прошлого sprint: [changes.diff](changes.diff). Отдельный минимальный diff карточек: [knowledge.diff](knowledge.diff). Это позволяет проверить именно этот этап, а не смешивать его с прошлой работой.

## Проверки и воспроизведение

`python -m pytest -q`: **120 passed**. Адресные тесты проверяют частичный ответ без генерации; полный общий workflow против конкретных прав/имени роли; запрет выводить операции из текста ограничения; scope gate вместе с expansion и разрешение явного стороннего кабинета; тему статьи активации; проход ФН 235 при сохранении отказов для общей инструкции и другого производителя; передачу metadata в chunks.

Исходные коллекции и SQLite проверены отдельно по хешам. Telegram не перезапускался и не переключался. Платных Groq-вызовов — **0**; web fallback и reranker не подключены; commit/push не выполнялись.

Повторить read-only comparison из корня проекта:

```powershell
$env:HF_HUB_OFFLINE = "1"
.venv/Scripts/python.exe -m scripts.compare_knowledge_staging --staging-collection knowledge_sprint_v1_20261022_quality_gate --manifest docs/staging-quality-gate/manifest.json --baseline-report docs/knowledge-sprint-v1/retrieval.json --output .local/staging-quality-gate/recheck.json
```

Создать ещё одну копию с новым уникальным именем: добавить `--create-staging --clone-collection knowledge_sprint_v1_20261021_final` и заменить staging-collection, например на `knowledge_sprint_v1_20261022_recheck`. Существующая коллекция никогда не перезаписывается. Исходная STAGING и CURRENT остаются источниками только для чтения.

## Оставшиеся знания и решение о LLM-тесте

Знания по-прежнему требуют специалиста: точная смена роли и завершение изменения существующего пользователя aQsi; вложенная матрица разрешений на конкретные отчёты/настройки; пользователи/сотрудники/роли АТОЛ; прямой поиск чека по ФН. Их отсутствие само по себе не блокирует ограниченный тест: по доступам теперь возвращается полезный partial или честный отказ. Полнота поисковых полей отдельно не реализовывалась в этом этапе.

**Полный ручной LLM-тест всех 15 сценариев пока не допущен. Ровно два блокера:**

1. **`atol-report`**: фраза о просмотре отчётов по кассам после замены ФН в DialogueState/query builder превращается в `fiscal_drive/check` → «проверка ФН». Правильная карточка отчётов уже есть в STAGING, но до отбора теряется запрошенная операция; выбирается `atol-online-18220-blocked`.
2. **`role`**: создание новой роли превращается в `assign_role` → «назначение роли сотруднику». Новый gate убирает ложное sufficient=True, но полезный partial о назначении ещё не выполняет исходную задачу создания роли.

Это ранее наблюдавшиеся дефекты представления задачи. Их исправление не входило в три точечных A/B/C; DialogueState и query builder в этом этапе не менялись. Для ограниченного ручного теста A/B/C коллекция и код подготовлены; фактическое качество свежей генерации GPT-OSS ещё не измерено, вызовов без отдельного согласования не выполнялось.
