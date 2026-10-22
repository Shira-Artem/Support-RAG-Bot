# Knowledge Quality Sprint v1 — 21.10.2026

Бот готов к ручному тесту **текущей knowledge_demo**. Обновлённые карточки находятся только в STAGING; переключения Telegram на них не было. Результаты не дают основания продвигать STAGING в рабочую коллекцию: ниже зафиксированы остающиеся ошибки retrieval.

## Baseline и сохранность

HEAD и удалённый `main`, проверенный через `git ls-remote`: `d720ab3ee445a6d4abe87d668ddc4a0a510b5a0b`. До работы дерево было чистым. Commit/push не выполнялись.

CURRENT: `knowledge_demo`, **264 документа / 928 чанков**, все draft, Qdrant green. Embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 измерения, Cosine. Генератор: Groq `openai/gpt-oss-20b`, `reasoning_effort=medium`. `RAG_BACKEND=qdrant`, `RAG_DEMO_MODE=1`.

Полная исходная схема payload и fingerprint: [baseline.json](baseline.json). Поля: document_id, title, category, manufacturer, model, version, source_url, source_type, published_at, verified_at, collected_at, status, content_hash, source, section, page, chunk_id, text. В CURRENT нет записанных service/task_category/operations/search_fields.

Payload fingerprint CURRENT до/после: `377cd65951920917153040e7687a66f057ec68ada6d5e6b03fccec919596df37`. Значения совпали. Скрипт сравнения не индексирует CURRENT. Проверка в тесте также подтверждает неизменность его векторов при клонировании и наложении правок.

## Проверенные карточки и источники

Проверены 10 существующих карточек; добавлено 5 отдельных карточек по тем же приоритетным темам. Ниже — все 15 карточек. Отдельно исследован пробел по доступам АТОЛ Онлайн. Контрольные ФН 234/235 использованы без редактирования и без нового source review.

| Карточка | Действие | Подтверждённый источник |
|---|---|---|
| [aqsi-online-account-add-user](../../data/knowledge/aqsi_online/account/add-user.md) | updated | [Официальная статья](https://aqsi.online/instructions/account/kak-sozdat-novogo-polzovatelya) |
| [aqsi-online-account-edit-user](../../data/knowledge/aqsi_online/account/edit-user.md) | created | [Официальная статья](https://aqsi.online/instructions/account/kak-sozdat-novogo-polzovatelya) |
| [aqsi-online-account-create-role](../../data/knowledge/aqsi_online/account/create-role.md) | created | [Официальная статья](https://aqsi.online/instructions/account/kak-sozdat-novuyu-rol) |
| [aqsi-online-account-my-cash-registers](../../data/knowledge/aqsi_online/account/my-cash-registers.md) | updated | [Официальная статья](https://aqsi.online/instructions/account/moi-kassy) |
| [aqsi-online-account-monitoring](../../data/knowledge/aqsi_online/account/monitoring.md) | updated | [Официальная статья](https://aqsi.online/instructions/account/monitoring) |
| [aqsi-online-account-settings](../../data/knowledge/aqsi_online/account/settings.md) | updated | [Официальная статья](https://aqsi.online/instructions/account/nastrojki) |
| [platformaofd-lkk-cash-monitoring](../../data/knowledge/platformaofd/ofd/lkk-cash-monitoring.md) | updated | [Официальная статья](https://platformaofd.ru/baza-znaniy/lkk-razdel-kassy/) |
| [platformaofd-lkk-cash-search](../../data/knowledge/platformaofd/ofd/lkk-cash-search.md) | created | [Официальная статья](https://platformaofd.ru/baza-znaniy/lkk-razdel-kassy/) |
| [platformaofd-lkk-receipt-search](../../data/knowledge/platformaofd/ofd/lkk-receipt-search.md) | updated | [Официальная статья](https://platformaofd.ru/baza-znaniy/lkk-razdel-cheki/) |
| [platformaofd-lkk-receipt-fns-status](../../data/knowledge/platformaofd/ofd/lkk-receipt-fns-status.md) | created | [Официальная статья](https://platformaofd.ru/baza-znaniy/lkk-razdel-cheki/) |
| [platformaofd-fns-indicators](../../data/knowledge/platformaofd/ofd/fns-indicators.md) | updated | [Официальная статья](https://platformaofd.ru/baza-znaniy/kn-razdel-fns/) |
| [atol-online-14749-incoming-documents](../../data/knowledge/atol_online/edo/incoming-documents.md) | updated | [Официальная статья](https://help.atol.online/article/14749) |
| [atol-online-18126-monitoring](../../data/knowledge/atol_online/fn/monitoring.md) | updated | [Официальная статья](https://help.atol.online/article/18126) |
| [atol-online-11069-fns-after-fn-swap](../../data/knowledge/atol_online/fn/fns-after-fn-swap.md) | updated | [Официальная статья](https://help.atol.online/article/11069) |
| [atol-online-account-cash-reports](../../data/knowledge/atol_online/account/cash-reports.md) | created | [Официальная статья](https://help.atol.online/article/11069) |

[manifest.json](manifest.json) содержит для каждой карточки URL, source_type, source_checked_at, сохранённые и изменённые факты, потери старого конспекта, неподтверждённые утверждения, применимость, UI, разделение операций, remaining_gaps и proposed_status. Проверка источников: **21.10.2026**, proposed_status везде **draft**. Проверка сайта не равна одобрению специалистом; verified_at не выставлялся.

[sources.json](sources.json) хранит URL/HTTP-status/SHA-256 полученных официальных страниц и иллюстраций; локальные снимки — `.local/knowledge-sprint-v1/sources/`. Веб-экстрактор пропустил содержимое ряда страниц aQsi, поэтому проверен исходный HTML и официальные рисунки 27/30/31. UTF-8 HTML корректен; первоначальная гипотеза о неверной кодировке сайта не подтвердилась.

## Что было потеряно или не подтверждено

- aQsi: сокращены конкретное действие добавления и сохранение; отсутствовала карточка создания роли. Теперь отдельно описаны создание пользователя, изменение записи и настройка роли. [Текст и рисунки роли](https://aqsi.online/instructions/account/kak-sozdat-novuyu-rol) подтверждают выбор просмотра/редактирования и назначение пользователей. В тексте блок назван «Расширения», на рисунке — «Разрешения»; расхождение сохранено явно. Пример роли не превращён в обязательную матрицу прав.
- [Создание пользователя aQsi](https://aqsi.online/instructions/account/kak-sozdat-novogo-polzovatelya) подтверждает меню изменения существующей записи, но не поля смены роли в этой форме. Обязательная роль с названием «Администратор», пароль, письмо-приглашение и вымышленные роли не подтверждены. Их нельзя выводить из прошлых ответов модели.
- [Поиск чеков Платформы ОФД](https://platformaofd.ru/baza-znaniy/lkk-razdel-cheki/): возвращены дополнительные фильтры, дата пробития, условия тегов и маркировки. Статусы вынесены в отдельное знание. Прямой фильтр ФН по этой статье не установлен; это не утверждение об отсутствии функции.
- [Кассы Платформы ОФД](https://platformaofd.ru/baza-znaniy/lkk-razdel-kassy/): восстановлен маршрут мониторинга, выделен поиск ранее добавленной ККТ по реквизитам с рисунка 6. Источник сам противоречит себе в пороге 72/48 часов; спорная часть не выдана за точное правило.
- АТОЛ: восстановлены точный виджет [мониторинга ФН](https://help.atol.online/article/18126), критерии обращения 90%/два месяца, маршрут [отчётов после замены ФН](https://help.atol.online/article/11069) и условие оплаченного ОФД. Тематика [ЭДО](https://help.atol.online/article/14749) явно отделена от пользователей ЛК.

## Метаданные и границы изменения кода

В Document добавлены `service`, `task_category`, `operations`, `search_fields`, `source_checked_at`. Существующие manufacturer/model/status/source_url сохранены. Списки нормализуются (скалярная строка допускается как один элемент, пробелы/дубликаты убираются), типы и ISO-дата проверяются. Неизвестные значения сервисов и операций не привязаны к производителю.

Chunker уже использует `asdict(Document)`: новые поля попадают в каждый payload. Идентификаторы чанков не меняются от одной правки метаданных. QdrantStore сравнивает весь payload, поэтому metadata-only изменение переиндексируется при неизменном content_hash; это проверено тестом. Все 269 локальных документов читаются. В фактическом STAGING проверены метаданные всех 15 изменённых/новых документов.

DialogueState, query builder, operation rules, retrieval gates, response grounding и validator не изменялись. Из прикладного кода изменён только `app/knowledge.py`; добавлен операторский runner. Новые search_fields сохраняются, но текущий pipeline ещё не использует их как проверку полноты конкретного поискового поля. При анализе статьи pipeline также пересчитывает operations из текста вместо безусловного доверия явному списку — это существующее поведение, показанное в trace.

## CURRENT vs STAGING

Итоговая коллекция: `knowledge_sprint_v1_20261021_final`, **269 документов / 927 чанков**. Это копия 264 исходных документов с прежними векторами плюс наложение 15 карточек: 10 заменённых и 5 новых. Число чанков уменьшилось из-за пересборки разделов. `removed=15` в overlay_stats означает удалённые старые chunk-id **только внутри STAGING**, не удаление документов CURRENT. Все остальные документы сохранены. Промежуточная `knowledge_sprint_v1_20261021` также оставлена для воспроизводимости первой итерации.

Небольшая выборка: 7 реальных клиентских реплик из сохранённой обезличенной fixture + 8 запрошенных probes. Реплики одной беседы последовательно проходят неизменённый DialogueManager; ответы ассистента здесь не синтезируются. ФД/ФП — отдельные probes. Полный state/query, top-10 уникальных документов, dense/BM25/RRF, причины отклонения, выбранные документы и контекст: [retrieval.json](retrieval.json).

`sufficient_evidence` ниже — именно флаг существующего RetrievalPipeline. Он не является оценкой человека или доказательством всех условий запроса. Итоговая ручная оценка и недостающее знание записаны для каждого случая в `human_review`.

| Запрос | CURRENT: первый выбранный | STAGING: первый выбранный | sufficient C/S |
|---|---|---|---|
| 49: Как завести учётку для сотрудника в aQsi Online? | aqsi-online-account-add-user | aqsi-online-account-add-user | True/True |
| 51: Он уже есть, мне нужно изменить ему права. | aqsi-online-account-add-user | aqsi-online-account-edit-user | True/True |
| 53: Хочу, чтобы он мог смотреть кассы и отчёты, но не менять настройки. | aqsi-online-account-add-user | aqsi-online-account-edit-user | True/True |
| 55: А если у нас АТОЛ Онлайн — там это делается так же? | — | — | False/False |
| 57: Как посмотреть список моих касс в личном кабинете Платформы ОФД? | platformaofd-lkk-cash-monitoring | platformaofd-lkk-cash-monitoring | True/True |
| 59: А теперь мне нужно найти чек за прошлый месяц. | platformaofd-lkk-receipt-search | platformaofd-lkk-receipt-search | True/True |
| 61: И можно найти его по номеру ФН? | platformaofd-lkk-receipt-search | platformaofd-lkk-receipt-search | True/True |
| fd: Как найти чек по номеру ФД в Платформе ОФД? | platformaofd-lkk-receipt-search | platformaofd-lkk-receipt-search | True/True |
| fp: Как найти чек по ФП в Платформе ОФД? | platformaofd-lkk-receipt-search | platformaofd-lkk-receipt-search | True/True |
| role: Как создать новую роль в aQsi Online? | aqsi-online-account-add-user | aqsi-online-account-add-user | True/True |
| aqsi-list: Где посмотреть список касс в aQsi Online? | — | aqsi-online-account-monitoring | False/True |
| atol-list: Как посмотреть список касс в АТОЛ Онлайн? | atol-online-23349-activate-first-ofd | atol-online-23349-activate-first-ofd | True/True |
| atol-report: Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн? | atol-online-18126-monitoring | atol-online-18220-blocked | True/True |
| fn234: Эвотор ошибка ФН 234 | evotor-fn-234-360005580254 | evotor-fn-234-360005580254 | True/True |
| fn235: Эвотор ошибка ФН 235 | — | — | False/False |

### Кандидаты, причины и пробелы по каждому запросу

**49. Как завести учётку для сотрудника в aQsi Online?**

Query: `сервис: aQsi Online — добавление сотрудника`

CURRENT, top-3 до gate:

- `aqsi-online-account-add-user`: RRF=0.05, dense=0.7687, BM25=15.90328; gate не отклонил.
- `atol-online-12148-company-registration`: RRF=0.045688, dense=0.6791, BM25=8.92116; service_mismatch_or_unlabeled, task_unconfirmed.
- `aqsi-online-account-register-account`: RRF=0.039527, dense=0.6074, BM25=6.35271; operation_mismatch:add_employee.

Выбраны: `aqsi-online-account-add-user`.

STAGING, top-3 до gate:

- `atol-online-12148-company-registration`: RRF=0.047371, dense=0.6791, BM25=9.01637; service_mismatch_or_unlabeled, task_unconfirmed.
- `atol-online-14749-incoming-documents`: RRF=0.040598, dense=0.6079, BM25=6.73898; service_mismatch_or_unlabeled, task_mismatch:edo!=access.
- `aqsi-online-account-register-account`: RRF=0.039325, dense=0.6074, BM25=6.41669; operation_mismatch:add_employee.

Выбраны: `aqsi-online-account-add-user`.

Достаточно для создания с известной ролью; матрица прав — отдельный вопрос.

Недостающее знание/условие: для ограниченного действия нового пробела не установлено.

**51. Он уже есть, мне нужно изменить ему права.**

Query: `сервис: aQsi Online — изменение прав существующего сотрудника`

CURRENT, top-3 до gate:

- `aqsi-online-account-add-user`: RRF=0.048925, dense=0.7406, BM25=11.2259; gate не отклонил.
- `aqsi-online-account-register-account`: RRF=0.04152, dense=0.6172, BM25=6.35271; operation_mismatch:change_permissions.
- `atol-online-12790-catalog-cms-banks`: RRF=0.034568, dense=0.5776, BM25=5.14667; service_mismatch_or_unlabeled, task_unconfirmed.

Выбраны: `aqsi-online-account-add-user`.

STAGING, top-3 до gate:

- `atol-online-14749-incoming-documents`: RRF=0.045652, dense=0.6579, BM25=6.73898; service_mismatch_or_unlabeled, task_mismatch:edo!=access.
- `aqsi-online-account-register-account`: RRF=0.04152, dense=0.6172, BM25=6.41669; operation_mismatch:change_permissions.
- `atol-online-12790-catalog-cms-banks`: RRF=0.034085, dense=0.5776, BM25=5.098; service_mismatch_or_unlabeled, task_unconfirmed.

Выбраны: `aqsi-online-account-edit-user`, `aqsi-online-account-add-user`.

STAGING выбирает отдельную запись редактирования, но sufficient завышает полноту.

Недостающее знание/условие: Поля формы изменения и подтверждённое сохранение новой роли у существующей записи.

**53. Хочу, чтобы он мог смотреть кассы и отчёты, но не менять настройки.**

Query: `сервис: aQsi Online — изменение прав существующего сотрудника — цель: чтобы он мог смотреть кассы и отчёты — ограничения: но не менять настройки`

CURRENT, top-3 до gate:

- `aqsi-online-account-add-user`: RRF=0.046517, dense=0.7435, BM25=11.2259; gate не отклонил.
- `aqsi-online-account-settings`: RRF=0.042143, dense=0.6372, BM25=10.77136; operation_mismatch:change_permissions.
- `atol-online-22060-change-parameters`: RRF=0.039777, dense=0.5907, BM25=13.97829; service_mismatch_or_unlabeled, task_unconfirmed.

Выбраны: `aqsi-online-account-add-user`.

STAGING, top-3 до gate:

- `atol-online-14749-incoming-documents`: RRF=0.041667, dense=0.7137, BM25=9.44567; service_mismatch_or_unlabeled, task_mismatch:edo!=access.
- `atol-online-22060-change-parameters`: RRF=0.038403, dense=0.5907, BM25=14.00405; service_mismatch_or_unlabeled, task_unconfirmed.
- `aqsi-online-account-register-account`: RRF=0.036748, dense=0.6897, BM25=8.39702; operation_mismatch:change_permissions.

Выбраны: `aqsi-online-account-edit-user`, `aqsi-online-account-add-user`.

Операция остаётся change_permissions; новая карточка роли не попадает в выбранные. Конкретный набор прав не установлен.

Недостающее знание/условие: Доступ к конкретным отчётам и запрет изменения настроек; матрица вложенных разрешений.

**55. А если у нас АТОЛ Онлайн — там это делается так же?**

Query: `сервис: АТОЛ Онлайн — изменение прав существующего сотрудника — цель: чтобы он мог смотреть кассы и отчёты — ограничения: но не менять настройки`

CURRENT, top-3 до gate:

- `atol-online-25850-contacts`: RRF=0.041558, dense=0.6428, BM25=10.50575; task_unconfirmed.
- `atol-online-22060-change-parameters`: RRF=0.040426, dense=0.5766, BM25=17.40277; task_unconfirmed.
- `atol-online-11251-replacement-reasons`: RRF=0.040258, dense=0.5859, BM25=13.36566; task_unconfirmed.

Выбраны: нет.

STAGING, top-3 до gate:

- `atol-online-14749-incoming-documents`: RRF=0.048925, dense=0.7326, BM25=13.39137; task_mismatch:edo!=access.
- `atol-online-25850-contacts`: RRF=0.040765, dense=0.6428, BM25=10.46382; task_unconfirmed.
- `atol-online-22060-change-parameters`: RRF=0.040686, dense=0.5766, BM25=17.44016; task_unconfirmed.

Выбраны: нет.

Оба варианта честно отклоняют запрос. ЭДО не принимается за управление доступом.

Недостающее знание/условие: Официальная инструкция о пользователях/сотрудниках/ролях АТОЛ Онлайн и смене их прав.

**57. Как посмотреть список моих касс в личном кабинете Платформы ОФД?**

Query: `ОФД: Платформа ОФД — просмотр списка касс`

CURRENT, top-3 до gate:

- `atol-online-23349-activate-first-ofd`: RRF=0.044859, dense=0.6324, BM25=9.77779; service_mismatch_or_unlabeled.
- `platformaofd-connect-kkt-to-lkk`: RRF=0.044023, dense=0.5394, BM25=11.77582; task_mismatch:equipment_setup!=cash_list.
- `evotor-ofd-settings-reference-20261019`: RRF=0.043817, dense=0.5682, BM25=10.61663; service_mismatch_or_unlabeled, task_mismatch:equipment_setup!=cash_list.

Выбраны: `platformaofd-lkk-cash-monitoring`.

STAGING, top-3 до gate:

- `platformaofd-lkk-cash-monitoring`: RRF=0.047032, dense=0.5777, BM25=21.82242; gate не отклонил.
- `atol-online-23349-activate-first-ofd`: RRF=0.044859, dense=0.6324, BM25=9.51444; service_mismatch_or_unlabeled.
- `platformaofd-connect-kkt-to-lkk`: RRF=0.043494, dense=0.5394, BM25=11.29288; task_mismatch:equipment_setup!=cash_list.

Выбраны: `platformaofd-lkk-cash-monitoring`.

Правильная карточка мониторинга выбрана в обоих вариантах; STAGING восстанавливает маршрут и фильтры.

Недостающее знание/условие: В источнике противоречие порога 72/48 часов; не мешает самому просмотру списка.

**59. А теперь мне нужно найти чек за прошлый месяц.**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: за прошлый месяц`

CURRENT, top-3 до gate:

- `atol-online-22560-receipt-journal-export`: RRF=0.048958, dense=0.6090, BM25=28.22798; service_mismatch_or_unlabeled.
- `platformaofd-lkk-receipt-search`: RRF=0.048916, dense=0.6255, BM25=24.50881; gate не отклонил.
- `atol-online-23415-activate-taxcom`: RRF=0.039129, dense=0.6138, BM25=9.36676; service_mismatch_or_unlabeled, task_mismatch:receipt_transmission!=receipt_search.

Выбраны: `platformaofd-lkk-receipt-search`.

STAGING, top-3 до gate:

- `platformaofd-lkk-receipt-search`: RRF=0.05, dense=0.7133, BM25=35.50271; gate не отклонил.
- `atol-online-22560-receipt-journal-export`: RRF=0.04866, dense=0.6090, BM25=27.16937; service_mismatch_or_unlabeled.
- `platformaofd-lkk-cash-search`: RRF=0.039611, dense=0.5203, BM25=22.68608; task_mismatch:cash_search!=receipt_search.

Выбраны: `platformaofd-lkk-receipt-search`.

Выбрана инструкция поиска чеков. В STAGING восстановлены потерянные фильтры и дата пробития.

Недостающее знание/условие: для ограниченного действия нового пробела не установлено.

**61. И можно найти его по номеру ФН?**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: за прошлый месяц; по номеру ФН`

CURRENT, top-3 до gate:

- `platformaofd-lkk-receipt-search`: RRF=0.048039, dense=0.6199, BM25=28.76591; gate не отклонил.
- `atol-online-23415-activate-taxcom`: RRF=0.046244, dense=0.6512, BM25=14.21213; service_mismatch_or_unlabeled, task_mismatch:receipt_transmission!=receipt_search.
- `atol-online-22560-receipt-journal-export`: RRF=0.045774, dense=0.6006, BM25=28.22798; service_mismatch_or_unlabeled.

Выбраны: `platformaofd-lkk-receipt-search`.

STAGING, top-3 до gate:

- `platformaofd-lkk-receipt-search`: RRF=0.05, dense=0.7248, BM25=35.50271; gate не отклонил.
- `atol-online-22560-receipt-journal-export`: RRF=0.045079, dense=0.6006, BM25=27.16937; service_mismatch_or_unlabeled.
- `atol-online-23415-activate-taxcom`: RRF=0.044562, dense=0.6512, BM25=13.99751; service_mismatch_or_unlabeled, task_mismatch:receipt_transmission!=receipt_search.

Выбраны: `platformaofd-lkk-receipt-search`.

sufficient=True не подтверждает прямой фильтр ФН. В STAGING граница явно описана; карточка поиска ККТ по ФН отклонена как cash_search!=receipt_search.

Недостающее знание/условие: Наличие прямого поля ФН для чеков; переход от найденной ККТ к чекам в актуальном ЛК.

**fd. Как найти чек по номеру ФД в Платформе ОФД?**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: по номеру ФД в Платформе ОФД`

CURRENT, top-3 до gate:

- `platformaofd-lkk-receipt-search`: RRF=0.049727, dense=0.6542, BM25=36.41868; gate не отклонил.
- `platformaofd-fn-number-in-lkk`: RRF=0.047183, dense=0.6277, BM25=24.80321; task_unconfirmed.
- `platformaofd-atol-transmission-checks`: RRF=0.042641, dense=0.6586, BM25=13.40592; task_mismatch:receipt_transmission!=receipt_search.

Выбраны: `platformaofd-lkk-receipt-search`.

STAGING, top-3 до gate:

- `platformaofd-lkk-receipt-search`: RRF=0.047826, dense=0.6208, BM25=34.49938; gate не отклонил.
- `platformaofd-fn-number-in-lkk`: RRF=0.046402, dense=0.6277, BM25=23.63491; task_unconfirmed.
- `platformaofd-lkk-cash-search`: RRF=0.045079, dense=0.6026, BM25=28.49885; task_mismatch:cash_search!=receipt_search.

Выбраны: `platformaofd-lkk-receipt-search`.

Выбрана карточка поиска чеков с подтверждённым ФД.

Недостающее знание/условие: для ограниченного действия нового пробела не установлено.

**fp. Как найти чек по ФП в Платформе ОФД?**

Query: `ОФД: Платформа ОФД — поиск чек — параметры текущего поиска: по ФП в Платформе ОФД`

CURRENT, top-3 до gate:

- `platformaofd-lkk-receipt-search`: RRF=0.047619, dense=0.6260, BM25=27.75949; gate не отклонил.
- `platformaofd-fn-number-in-lkk`: RRF=0.044023, dense=0.5923, BM25=20.02212; task_unconfirmed.
- `platformaofd-atol-transmission-checks`: RRF=0.04068, dense=0.6306, BM25=11.57631; task_mismatch:receipt_transmission!=receipt_search.

Выбраны: `platformaofd-lkk-receipt-search`.

STAGING, top-3 до gate:

- `platformaofd-lkk-cash-search`: RRF=0.045591, dense=0.6066, BM25=25.61578; task_mismatch:cash_search!=receipt_search.
- `platformaofd-lkk-receipt-search`: RRF=0.045528, dense=0.6010, BM25=35.79893; gate не отклонил.
- `platformaofd-fn-number-in-lkk`: RRF=0.042005, dense=0.5923, BM25=18.92634; task_unconfirmed.

Выбраны: `platformaofd-lkk-receipt-search`.

STAGING сначала ранжирует поиск ККТ, но gate отклоняет его и выбирает чек. Нужное поле ФП подтверждено.

Недостающее знание/условие: для ограниченного действия нового пробела не установлено.

**role. Как создать новую роль в aQsi Online?**

Query: `сервис: aQsi Online — назначение роли сотруднику`

CURRENT, top-3 до gate:

- `aqsi-online-account-add-user`: RRF=0.049454, dense=0.7628, BM25=11.2259; gate не отклонил.
- `aqsi-online-account-register-account`: RRF=0.041291, dense=0.6198, BM25=6.35271; operation_mismatch:assign_role.
- `atol-online-26852-payment-object-ffd12`: RRF=0.036502, dense=0.5395, BM25=6.38925; service_mismatch_or_unlabeled, task_mismatch:receipt_search!=access.

Выбраны: `aqsi-online-account-add-user`.

STAGING, top-3 до gate:

- `atol-online-14749-incoming-documents`: RRF=0.044776, dense=0.6363, BM25=8.59492; service_mismatch_or_unlabeled, task_mismatch:edo!=access.
- `aqsi-online-account-register-account`: RRF=0.039829, dense=0.6198, BM25=6.41669; operation_mismatch:assign_role.
- `atol-online-26852-payment-object-ffd12`: RRF=0.034337, dense=0.5395, BM25=6.0033; service_mismatch_or_unlabeled, task_mismatch:receipt_search!=access.

Выбраны: `aqsi-online-account-add-user`, `aqsi-online-account-create-role`, `aqsi-online-account-edit-user`.

Запрос создания роли преобразован текущим анализатором в assign_role. В STAGING карточка создания роли есть среди выбранных, но первая — add-user.

Недостающее знание/условие: Создание и назначение роли ещё не различаются в состоянии задачи; вложенные права не проверены.

**aqsi-list. Где посмотреть список касс в aQsi Online?**

Query: `сервис: aQsi Online — просмотр списка касс`

CURRENT, top-3 до gate:

- `aqsi-online-account-register-account`: RRF=0.04324, dense=0.5837, BM25=6.35271; task_mismatch:access!=cash_list.
- `aqsi-online-usecase-retail-physical-vs-cloud`: RRF=0.040962, dense=0.5743, BM25=5.89264; task_unconfirmed.
- `atol-online-21114-mass-correction`: RRF=0.040258, dense=0.5282, BM25=6.81221; service_mismatch_or_unlabeled, task_mismatch:receipt_search!=cash_list.

Выбраны: нет.

STAGING, top-3 до gate:

- `aqsi-online-account-register-account`: RRF=0.040476, dense=0.5837, BM25=6.41669; task_mismatch:access!=cash_list.
- `aqsi-online-usecase-retail-physical-vs-cloud`: RRF=0.038632, dense=0.6018, BM25=5.67725; task_unconfirmed.
- `atol-online-21114-mass-correction`: RRF=0.03746, dense=0.5282, BM25=6.63987; service_mismatch_or_unlabeled, task_mismatch:receipt_search!=cash_list.

Выбраны: `aqsi-online-account-monitoring`, `aqsi-online-account-my-cash-registers`.

CURRENT ошибочно размечает account как access и не выбирает документ. STAGING допускает мониторинг и Мои кассы; мониторинг стоит первым, поэтому ранжирование ещё требует проверки.

Недостающее знание/условие: Права конкретной роли; состав фильтра на актуальном экране.

**atol-list. Как посмотреть список касс в АТОЛ Онлайн?**

Query: `сервис: АТОЛ Онлайн — просмотр списка касс`

CURRENT, top-3 до gate:

- `atol-online-12790-catalog-cms-banks`: RRF=0.044965, dense=0.7018, BM25=6.18488; task_unconfirmed.
- `atol-online-23349-activate-first-ofd`: RRF=0.044692, dense=0.5936, BM25=9.14153; gate не отклонил.
- `atol-online-21114-mass-correction`: RRF=0.041146, dense=0.5366, BM25=10.38004; task_mismatch:receipt_search!=cash_list.

Выбраны: `atol-online-23349-activate-first-ofd`, `atol-online-18126-monitoring`.

STAGING, top-3 до gate:

- `atol-online-23349-activate-first-ofd`: RRF=0.044453, dense=0.5936, BM25=9.0381; gate не отклонил.
- `atol-online-12790-catalog-cms-banks`: RRF=0.044171, dense=0.7018, BM25=6.1719; task_unconfirmed.
- `atol-online-21114-mass-correction`: RRF=0.041463, dense=0.5366, BM25=10.21935; task_mismatch:receipt_search!=cash_list.

Выбраны: `atol-online-23349-activate-first-ofd`, `atol-online-18126-monitoring`.

Оба варианта первым выбирают активацию кассы в Первом ОФД. Карточка мониторинга АТОЛ тоже выбрана. Это смешение кабинетов внутри статьи того же производителя.

Недостающее знание/условие: Надёжная область применимости для инструкций о стороннем кабинете ОФД.

**atol-report. Где посмотреть отчёты по кассам после замены ФН в АТОЛ Онлайн?**

Query: `сервис: АТОЛ Онлайн — проверка ФН`

CURRENT, top-3 до gate:

- `atol-online-18126-monitoring`: RRF=0.049727, dense=0.6957, BM25=8.76267; gate не отклонил.
- `atol-online-18220-blocked`: RRF=0.04728, dense=0.6692, BM25=8.31749; gate не отклонил.
- `atol-online-20054-replacement-process`: RRF=0.047131, dense=0.6833, BM25=8.23048; gate не отклонил.

Выбраны: `atol-online-18126-monitoring`, `atol-online-18220-blocked`, `atol-online-20054-replacement-process`, `atol-online-11254-test-cashier`, `atol-online-23349-activate-first-ofd`.

STAGING, top-3 до gate:

- `atol-online-18220-blocked`: RRF=0.048039, dense=0.6692, BM25=8.31112; gate не отклонил.
- `atol-online-20054-replacement-process`: RRF=0.047883, dense=0.6833, BM25=8.21319; gate не отклонил.
- `atol-online-11254-test-cashier`: RRF=0.044002, dense=0.6615, BM25=7.73102; gate не отклонил.

Выбраны: `atol-online-18220-blocked`, `atol-online-20054-replacement-process`, `atol-online-11254-test-cashier`, `atol-online-23349-activate-first-ofd`, `atol-online-16568-step7-fn-activation`.

Запрос отчётов после замены ФН превращается в «проверка ФН». CURRENT выбирает мониторинг, STAGING — блокировку ФН. Сведения об отчётах в STAGING есть, но исходная задача потеряна до retrieval.

Недостающее знание/условие: Распознавание операции просмотра отчётов; права сотрудников на неё.

**fn234. Эвотор ошибка ФН 234**

Query: `производитель: Эвотор — диагностика ошибки ФН — код ошибки 234`

CURRENT, top-3 до gate:

- `evotor-fn-234-360005580254`: RRF=0.046154, dense=0.5319, BM25=23.36056; gate не отклонил.

Выбраны: `evotor-fn-234-360005580254`.

STAGING, top-3 до gate:

- `evotor-fn-234-360005580254`: RRF=0.046154, dense=0.5319, BM25=23.36919; gate не отклонил.

Выбраны: `evotor-fn-234-360005580254`.

Правильная существующая карточка ФН 234 выбрана в обоих вариантах; контрольный документ не редактировался.

Недостающее знание/условие: для ограниченного действия нового пробела не установлено.

**fn235. Эвотор ошибка ФН 235**

Query: `производитель: Эвотор — диагностика ошибки ФН — код ошибки 235`

CURRENT, top-3 до gate:

- `evotor-fn-235-360004715213`: RRF=0.045528, dense=0.5330, BM25=23.47287; task_mismatch:receipt_transmission!=error_diagnosis.

Выбраны: нет.

STAGING, top-3 до gate:

- `evotor-fn-235-360004715213`: RRF=0.045528, dense=0.5330, BM25=23.46359; task_mismatch:receipt_transmission!=error_diagnosis.

Выбраны: нет.

Правильный документ найден top-1 dense/BM25, но отклонён как receipt_transmission!=error_diagnosis. Это ошибка производной категории, а не отсутствие статьи.

Недостающее знание/условие: Для этой проверки нового знания не требуется; нужна проверка классификации документа.

## Что относится к базе, а что к retrieval

База: неполные поля изменения пользователя, вложенные разрешения aQsi, права на отчёты, публичная инструкция сотрудников/ролей АТОЛ, подтверждение прямого фильтра ФН. Недостающие факты нельзя получить перестановкой кандидатов. Утраченную конкретику официальных инструкций возвращают карточки этого sprint.

Retrieval/состояние: ложное достаточное свидетельство для конкретных прав/полей; повторная классификация access по словам ограничения; смешение АТОЛ с кабинетом Первого ОФД; неверная категория ФН 235; преобразование создания роли в назначение; потеря просмотра отчётов при построении запроса. У aQsi список касс теперь допускается, но мониторинг ранжируется выше прямого списка. Это измеренные ограничения; STAGING не объявлена улучшением по всем запросам.

Reranker не установлен. Сначала нужен отдельный ограниченный эксперимент с применением явных operations/search_fields и областью кабинета, плюс сохранением операции отчётов в запросе. Для aQsi-list и АТОЛ-list можно затем сравнить reranker на замороженных **одинаковых** кандидатах и состояниях: первый документ, релевантность кабинету/операции, доля корректных отказов, задержка. Поиск ФН 235 уже нашёл правильный top-1 — reranker не исправит его отклонение gate. Потерю задачи в запросе он также не решит.

## Проверка человеком

1. aQsi: показать актуальную форму существующего пользователя, смену роли и сохранение; раскрыть вложенные разрешения роли для касс и конкретных отчётов; проверить только просмотр и невозможность менять настройки тестовым сотрудником.
2. Платформа ОФД: сверить прямой фильтр ФН для чеков, переход через поиск ККТ и фактический порог спорного индикатора 72/48 часов.
3. АТОЛ: получить официальную инструкцию либо подтверждение поддержки о пользователях/сотрудниках/ролях, смене прав и доступе к мониторингу и отчётам. Проверен публичный [каталог сервиса](https://help.atol.online/category/3716) и site-search; отсутствие найденной статьи не доказывает отсутствие функции.
4. Повторить реальные диалоги в Telegram на CURRENT, нажимая «Новый диалог» между независимыми сценариями. Сначала — 7 исходных реплик, затем ФД/ФП и ФН 234/235. Сверять фактический ответ и сохранённые diagnostics; новый автоматический LLM-прогон не запускался.

## Запуск и проверка

Перед остановкой worker незавершённых сообщений и экспертных генераций было 0. Обе базы скопированы через SQLite backup API в `.local/backups/knowledge-sprint-v1-20261021-191816/`; quick_check=ok. После перезапуска число записей всех таблиц сохранилось, включая 62 сообщения и 31 человеческую оценку. SQLite и оценки не очищались.

21.10.2026 в 19:18 МСК запущен worker PID 11176, launcher виртуального окружения PID 26976. Оба относятся только к этому checkout; polling worker ровно один, instance-lock удерживается. В журнале есть `Application started`, конфликтов polling не зафиксировано. `getMe`, отключённый webhook и каталог моделей Groq проверены без отправки сообщений и без completions. Безопасные результаты: [runtime.json](runtime.json). Фактическая генерация GPT-OSS проверяется пользователем вручную.

`python -m pytest -q`: **113 passed**. Проверены сохранение метаданных через sidecar/chunk/Qdrant, metadata-only обновление, изоляция staging и неизменность векторов CURRENT. Старый текст d720ab3 сохранён отдельной fixture для регрессий grounding; ожидания офлайн-повтора обновлены под разделённые карточки без изменения validator. Платных LLM-вызовов в проверке — **0**.

### Воспроизводимые команды (PowerShell из корня проекта)

Создать новую коллекцию с тем же baseline и текущими карточками (имя должно быть новым):

```powershell
$env:HF_HUB_OFFLINE = "1"
.venv\Scripts\python.exe -m scripts.compare_knowledge_staging --create-staging --staging-collection knowledge_sprint_v1_20261021_recheck --output .local/knowledge-sprint-v1/recreated-comparison.json
```

Повторить только сравнение существующей итоговой коллекции:

```powershell
.venv\Scripts\python.exe -m scripts.compare_knowledge_staging --staging-collection knowledge_sprint_v1_20261021_final --output .local/knowledge-sprint-v1/recheck.json
```

Runner отказывается создавать уже существующую STAGING или использовать имя рабочей коллекции. Не передавайте этим draft-данным команду перезаписи knowledge_demo. `HF_HUB_OFFLINE=1` применим, когда embedding-модель уже есть в локальном кэше (здесь она есть).

Для просмотра ручного диалога без LLM: `.venv\Scripts\python.exe scripts/show_last_conversation.py --turns 7 --context`. Вывод может содержать личную переписку; сохранять его следует в `.local/`, а не в публичном отчёте.

## Web fallback

[Текущая документация Groq Browser Search](https://console.groq.com/docs/tool-use/built-in-tools/browser-search) по-прежнему подтверждает GPT-OSS 20B/120B, инструмент browser_search и несовместимость со structured outputs. Также перечислен safeguard-20b. Рекомендация low относится к отдельному поисковому эксперименту; рабочий бот оставлен medium. Жёсткое ограничение доменов и цена инструмента не установлены этой проверкой.

Существующий [web-fallback-plan](../incidents/2026-10-21/web-fallback-plan.md) пригоден как план отдельного эксперимента после выяснения тарифа, формата provenance и ограничений доменов. Это не готовая интеграция. Browser Search и reranker в Telegram не подключены; интернет использован только оператором для проверки официальных знаний.
