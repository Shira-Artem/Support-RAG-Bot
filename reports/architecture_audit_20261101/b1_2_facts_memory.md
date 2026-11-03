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

## Final Gate 03.11.2026 — завершение Saby на опубликованном snapshot

Предыдущий раздел сохраняет исторический NO-GO до этого хода. Перед запуском сверены `main=7e795e5`, чистый Git, `source_hashes` предыдущего post-fix trace с текущими `bot.py` и `app/*.py`, а также точное равенство состояния [post-fix Saby 2](b1_2_facts_live_retest_20261103.json) и изолированной `.local/telegram-equivalent-b1_2_facts_live_retest_20261103/conversations.sqlite3`. Продолжение запущено из SQLite backup в **новой** изолированной базе через прежний [harness](run_b1_memory_live.py); добавлен только case с третьей исходной репликой. Pipeline: настоящий `bot.handle_message`, Groq `openai/gpt-oss-20b`/`medium`, read-only Stage3 `green/934`, fake Telegram. [Полный новый per-turn trace](b1_2_facts_final_gate_20261103.json) хранит raw/validated Understanding, field decisions, TaskFrame до/после, факты, обе SQLite стороны, ответ и HTTP. Ключи не сохранялись.

### Новый реальный ход Saby 3

Клиент: «Уточнил у поставщика: он отправил УПД, но у меня во входящих его всё ещё нет.»

- **Raw Understanding:** `request_type=diagnosis`, `relation=continue`, `intent=delivery_document`, `operation=check`, `object=УПД` с exact `object_evidence=«УПД»`; `goal=«у меня во входящих его всё ещё нет»`; `symptom=null`, `entities=[]`, `unknown_facts=[]`. **Validated:** те же relation/intent/operation/object/goal; object и goal приняты с точными span текущего сообщения, новых entity/unknown/symptom не заявлено, отклонённых claims нет. Отсутствие нового symptom не позволило Groq заменить первоначальную жалобу.
- **TaskFrame до:** `task:11`, `delivery_document/check`, subject `УПД`, symptom `«не появился входящий УПД»` (m11), service `Saby` (m11), goal `«подскажите, где проверить получение»` (m11), unknown `parameter=«Номер документа сейчас не знаю»` (m13), confirmed parameters `[]`, details `[]`, revision 2. **После:** тот же `task:11`, subject/service/symptom/unknown без изменений; добавлены goal `«у меня во входящих его всё ещё нет»` (m15) и detail `«Уточнил у поставщика: он отправил УПД, но»` (m15), revision 3. Подтверждённого номера и фактов Эвотор нет. `TaskFrame` после совпал с нормализованной проекцией `TaskContext`.
- **Persistence и ответ:** та же conversation ID и точное равенство `state_before` последнему post-fix Saby 2; полный `DialogueState.to_dict()` после SQLite reopen равен сохранённому состоянию. **1×HTTP 200 из нового бюджета максимум 12**, без 429 и дополнительных попыток. Реальный ответ: «Для этой задачи в «Saby» не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.» Неполезность ответа относится к отдельному quality/source gate, не к сохранности фактов.

### Проверки и решение

Финальные real Groq сценарии на одном snapshot теперь полны: Эвотор **3/3**, исправление модели **2/2**, Saby **3/3** (первые два хода в post-fix trace и третий из точного SQLite backup). Все **8/8** post-fix хода совпали после SQLite reopen. Эвотор сохранил исходный symptom и дополнительную очередь; correction держит только актуальную модель 6 с 7.3 в superseded; Saby не унаследовал Эвотор и сохранил явно неизвестный номер как unknown. Новая deterministic [проверка исправления производителя и модели](../../tests/test_b1_2_facts_memory.py) удержала task ID, заменила оба активных значения и сохранила прежние в superseded. B1.1 lifecycle/final verification + B1.2 targeted suite: **22 passed** до добавления этого одного теста; B1.2 suite после него: **8 passed**. Полный `python -m pytest -q`: **616 passed, 4 xfailed, 14 warnings, 0 failed**. Ни промпт, ни модель, ни reasoning effort, ни app runtime для экономии HTTP не менялись.

**B1.2 GO** по критериям памяти фактов в границе этого подэтапа. Ранее отмеченный короткий остаток «Заодно заметил, что» в Эвотор details остаётся ограничением качества извлечения: он цитирует клиента, но не несёт самостоятельного факта; дубли подавляются, а RAG query имеет fail-closed бюджет. Повтор шага, подбор источника и полезность Saby ответа остаются для B1.3/B2 без начала этих этапов. Общий исторический B1 memory gate и production readiness этим узким решением автоматически не повышаются. Следующий шаг — остановиться после B1.2 и представить владельцу результаты; B1.3/B2, worker и production окружение не трогать.
