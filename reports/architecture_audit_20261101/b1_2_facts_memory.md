# B1.2 — Confirmed Facts & Context Memory

Дата: 03.11.2026. Область: только память фактов активной задачи Variant B. Основа: `b02e1ab` (`300ba7d` — код B1.1). Production worker, SQLite, Qdrant index, approved KB, CRM, Smart Navigation и `.env` не менялись. Commit/push/pull/reset не выполнялись.

## Контракт и независимая матрица до исправления

Источник истины — `TaskContext` в `DialogueState`, сохранённый `ConversationStore`. `Fact` содержит value, точную quote, message_id и span. Активные entities/symptom/parameters/details имеют статус подтверждённых клиентской цитатой; `unknown_facts` и `unknown_evidence` содержат явно неизвестный слот и его цитату; `superseded_facts` хранит заменённые значения. `TaskFrame` — проекция той же задачи, не отдельная память. Текущий статус противоречия определяется relation текущего хода и историей замен; отдельный статус на каждом `Fact` не вводился.

| Независимый переход | Ожидание | Отрицательный контроль |
|---|---|---|
| Диагностическая реплика с raw `symptom=null` | Сохранить точную реплику как неклассифицированный `detail`; не выдумывать symptom | Социальное «Что дальше?» не добавляет факт |
| Новое наблюдение той же неисправности | Первый symptom остаётся; второй в details; один task ID | Действительно новый предмет «ФН не активируется» создаёт новый task |
| Модель 7.3 → клиент исправляет на 6 | В active equipment только 6; 7.3 в `superseded_facts` | Упоминание старой модели как ошибочной не подтверждает её снова |
| Явное «номер не знаю» → уточнение | Unknown с цитатой, затем удаляется при подтверждении | Неизвестный номер не становится подтверждённым параметром |
| Эвотор → отдельный Saby | Новый task без старого оборудования и symptom | Session history не маршрутизирует новый task |
| Повторная разговорная фраза | Не растит details; RAG query ограничен бюджетом | Семантически разные детали не удаляются по догадке |

## Baseline, причины и минимальные исправления

1. `tests/test_b1_2_facts_memory.py` до правки: **2 failed, 1 passed**. При raw diagnostic `symptom=null` reducer терял явную жалобу в `details`; `TaskFrame` не имел `parameters` и `superseded_facts`. Исторический C1 в [B1.1 trace](b1_1_task_lifecycle_live_20261102.json) подтверждает сырой `symptom=null` при фразе «Эвотор 7.3 не передаёт чеки в ОФД». Validator не отвергал симптом, Groq его пропустил. Reducer теперь сохраняет полный exact client turn как `detail` только для diagnostic `operation=diagnose` без symptom/unknown; это **неклассифицированная** цитата, а не восстановленный симптом. TaskFrame проецирует существующие parameters/details/superseded и evidence неизвестного слота.
2. Первый реальный batch ниже выявил **B1.1 boundary regression**: Groq на дополнении об очереди выдал raw `continue` и ошибочный `intent=fiscal_drive`, reducer создал новый task только по смене классификатора. Клиент не называл новый предмет. Универсальный `independent_domain` теперь требует упоминания корня предмета заявленного нового домена в текущем тексте. Ранее покрытый «ФН не активируется» по-прежнему переключает задачу. Это единственное изменение границы, основанное на доказанном live дефекте.
3. Groq передал `unknown_facts: document_number` с точной цитатой «Номер документа сейчас не знаю», но Validation отвергла незарегистрированный slot. Названия неизвестных номеров нормализуются к общему `parameter`, `model` — к `equipment`; исходная цитата остаётся в `TaskContext.unknown_evidence`. Неизвестный факт не добавляется в confirmed parameters. Это нормализация структурного типа, без regex по тестовой фразе.

Исправления не меняют ProgressLedger. Неудачный baseline и первый live batch сохранены как отрицательные результаты. [Профильные тесты](../../tests/test_b1_2_facts_memory.py) выполняют deterministic replay, включая SQLite reopen; [B1.1 regression suite](../../tests/test_b1_1_final_verification.py) проверяет реальную смену предмета/операции/сервиса.

Финальный `python -m pytest -q`: **615 passed, 4 xfailed, 14 warnings, 0 failed**. Профильный B1.2 suite: **7 passed**; B1.1 final verification + B1.2: **14 passed** до добавления последнего SQLite replay теста, затем полный suite охватил его.

## Реальные Groq E2E

Harness: [run_b1_memory_live.py](run_b1_memory_live.py), настоящий `bot.handle_message`, `openai/gpt-oss-20b` с текущим `medium`, изолированная SQLite, read-only Stage3 `green/934`, fake Telegram. Три новых естественных многоходовых сценария выполнялись последовательно. Артефакты содержат после **каждого** хода raw/validated Understanding и field decisions accepted/rejected, TaskFrame до/после, все факты с quote/message_id, superseded/unknown, task ID, полное состояние после SQLite reopen, фактический ответ и число HTTP-вызовов: [baseline batch](b1_2_facts_live_20261103.json), [post-fix batch](b1_2_facts_live_retest_20261103.json). Ни один provider response или ключ не изменялся.

Первый batch до двух последних исправлений: **8/8 ходов, 10×HTTP 200, 8/8 SQLite equal**. Эвотор: `task:1, task:1, task:5` — на третьем ходе исходный symptom был утрачен из активной задачи. Correction: `task:7` на обоих ходах, 7.3 заменён на 6, старое значение в superseded. Saby: `task:11` на трёх ходах без Эвотор, но raw `document_number` был отвергнут и не сохранился как unknown. Все три отрицательных наблюдения видны в [baseline JSON](b1_2_facts_live_20261103.json), включая field diagnostics и точные ответы.

Post-fix batch на итоговом коде: **7 ходов, 12×HTTP 200, 7/7 SQLite equal**. В таблице `raw → validated` показывает relation/intent; `task_id` окончательно выбирает reducer. Все упомянутые значения имеют точные quote и message_id в [per-turn JSON](b1_2_facts_live_retest_20261103.json).

| Сценарий/ход | Изменение фактов после хода | raw → validated; task ID | Ответ / HTTP |
|---|---|---|---|
| Эвотор 1 | `symptom=«оператор ОФД их не получает»` (m1); manufacturer Эвотор | `new_task/general → new_task/receipt`; `task:1` | Проверить модель и оплаченный период; 2×200 |
| Эвотор 2 | model `Эвотор 7.3` (m3); первый symptom сохранён | `continue/general → continue/general`; `task:1` | Диагностический отчёт из approved статьи 7.3; 2×200 |
| Эвотор 3 | `details=«очередь фискальных документов не сокращается»` (m5); первый symptom и модель сохранены; короткий остаток «Заодно заметил, что» тоже попал в details | `continue/fiscal_drive → continue/fiscal_drive`; reducer удержал `task:1` | Вопрос о результате уже показанной проверки; 2×200 |
| Исправление 1 | symptom `«не доходят до оператора»` (m7), model `Эвотор 7.3` | `new_task/general → new_task/receipt`; `task:7` | Шаг с отчётом 7.3; 2×200 |
| Исправление 2 | active model `Эвотор 6` (m9); `Эвотор 7.3` (m7) в superseded; исходный symptom сохранён; одновременно активной 7.3 нет | `answer_to_clarification/receipt → answer_to_clarification/unknown`; `task:7` | Проверка периода обслуживания из approved статьи 6; 2×200 |
| Saby 1 | service `Saby`, symptom `«не появился входящий УПД»` (m11); нет фактов Эвотор | `new_task/fiscal_drive → new_task/delivery_document`; `task:11` | Approved инструкции не найдено; 1×200 |
| Saby 2 | unknown `parameter=«Номер документа сейчас не знаю»` (m13); confirmed parameters пусты, Saby и symptom сохранены | `continue/delivery_document → continue/delivery_document`; `task:11` | Попросил новую деталь либо специалиста; 1×200 |

У третьего Saby хода исходного сценария есть живой raw/validated trace **только до** последних исправлений. В post-fix batch он **не выполнялся**: жёсткий общий бюджет 10+12 = **22/22 HTTP**, 22×200, без 429 и без дополнительных попыток. Поэтому полноценного третьего live сценария на окончательном коде нет; saved-Groq/deterministic SQLite controls не подменяют этот факт.

## Negative controls и ограничения

- Старый symptom и модель не переносятся в самостоятельный Saby task: проверяется в B1.1 regression и в отдельных SQLite сценариях. Новая неизвестность имеет статус unknown и свою цитату; `parameters` остаётся пустым до подтверждения.
- Повтор «Что дальше?» не добавляет `detail`; `_append_unique` удерживает точные дубли, а RAG query имеет 500-символьный fail-closed бюджет. В живом Эвотор появился короткий остаточный фрагмент «Заодно заметил, что» после выделения узкого symptom; это не критический факт, но редакционное загрязнение details и ограничение текущего фильтра.
- Сохранённый exact turn при пропуске Groq symptom не даёт оснований автоматически заполнить поле `symptom`: система сохраняет текст для downstream и последующего уточнения. Это сознательная граница доказанного смысла.
- Повторные диагностические действия, подбор источника и практическая полезность ответа оцениваются отдельно в B1.3/B2; эта работа их не ремонтирует.

## Решение

**B1.2 NO-GO / LIVE INCOMPLETE; production NO-GO.** На итоговом коде подтверждены сохранение исходного и дополнительного симптомов Эвотор, исправление модели без двух активных значений, явная неизвестность с цитатой и отсутствие переноса Эвотор в Saby; SQLite 7/7 equal. Обязательная приёмка требует все три законченных Groq-сценария на итоговом коде; Saby остановлен после второго хода по лимиту 22/22. Кроме того, остаточный разговорный fragment в details требует отдельной оценки риска роста RAG query, хотя дубли и 500-символьный fail-closed budget ограничивают его сейчас. Следующий конкретный шаг внутри B1.2: отдельным разрешённым бюджетом завершить третий Saby ход на итоговом коде (изолированная SQLite с состоянием после post-fix Saby 2), затем повторить полный pytest и решить gate. B1.3/B2 автоматически не начинать.
