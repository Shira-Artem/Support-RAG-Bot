# Conversational Understanding & Decision Engine — implementation gate

Дата: 2026-10-25. Этап V1.2-C авторизован прямым запросом пользователя и реализован в локальном Source-first пути. **Runtime gate FAILED: новый код не переключён на Telegram worker.**

## Гипотеза и архитектура

Гипотеза: отдельный typed Understanding до записи нового turn позволит выбирать conversational route до retrieval, а сохранённое evidence-bound наблюдение можно детерминированно применить один раз через существующий `DialogueManager`.

Порядок для allowlisted Source-first: получить прежний `DialogueState` и историю → вызвать Groq GPT-OSS 20B с JSON Schema → проверить типы, vocabulary и точные цитаты только из текущей реплики → сохранить контракт вместе с user message → reducer применяет его при SQLite replay → `SourceFirstService` делает greeting/feedback/escalation decision или строит запрос и вызывает имеющийся Hybrid Search → planner и source verifier сохраняют прежнюю approved/provenance/applicability/order границу. Legacy user и экспертный путь сохраняют старый `begin`/`DialogueManager`.

Модель не меняет task state и не является источником технических инструкций. Неизвестные client facts записываются в TaskContext и учитываются при повторных scope gates. Ошибка Understanding сохраняет trace, не запускает retrieval и не вызывает lexical fallback.

## Семь сценариев — локальная проверка

| Сценарий | Результат | Проверенное свойство |
|---|---|---|
| Greeting | PASS | typed greeting, пустой task state, Source-first не вызывает retrieval |
| Информационный вопрос «Что такое ОФД?» | PASS | `general/explain`, не подменяется процедурной диагностикой; service retrieval достигается |
| Диагностика с Эвотор и симптомом отправки чеков | PASS | производитель и симптом сохранены по цитатам клиента |
| Продолжение после вопроса о производителе | PASS | `answer_to_clarification`, задача сохраняет операцию; lexical analyzer не вызывается |
| Новая тема о добавлении сотрудника | PASS | новый `task_id`, старые параметры не переходят |
| Клиент не знает модель | PASS | unknown slot сохраняется; повторная модельная scope-уточнялка блокируется, вместо неё fail-closed escalation |
| Прямая просьба позвать специалиста | PASS | прямой позитивный span ведёт к существующей заявке без retrieval; отрицание «специалист не нужен» отклоняется |

Дополнительно: неподтверждённая сущность и перепутанный слот производителя/ОФД отвергаются; SQLite event replay применяет наблюдение однократно; повторное чтение состояния не меняет revision; повреждённый persisted contract оставляет state неизменным без lexical fallback. Targeted suite: 55 passed. Полный `python -m pytest -q`: **346 passed**, 13 прежних dependency deprecation warnings. `py_compile` прошёл.

Эти результаты проверяют контракт, переходы, replay и решения на doubles; они **не доказывают качество ответов модели в Telegram**.

## Реальный Groq gate — не пройден

Выполнена одна последовательная серия из семи синтетических сообщений с Groq GPT-OSS 20B / medium, без Telegram, Qdrant writes или пользовательской SQLite. Первый успешный HTTP response был отклонён локальным validator из-за пустой optional evidence quote; parser исправлен: пустые nullable spans трактуются как отсутствие, а обязательные claims без evidence по-прежнему отклоняются. В следующей серии до завершения проверки получено: greeting 429, information 429, diagnosis 429, continuation 429, topic change 429, unknown model 400, specialist 429. Ответ 400 выявил неверно сформированную nullable JSON Schema; порядок ключей исправлен, `max_completion_tokens` увеличен до 4096. После исправления schema новый успешный model response не получен из-за HTTP 429. Usage tokens отсутствовали у отказавших provider requests; у первого локально отклонённого ответа runner не сохранил итоговый usage receipt. Полные raw client texts и provider bodies в отчёт не копировались.

Результат реальной модели по семи сценариям: **0 валидированных / 7 завершённых**, поскольку запросы были throttled или schema rejected; это инфраструктурный блокер, а не пройденная оценка понимания. Повторить ровно семь синтетических проверок после восстановления Groq quota и оценить все transition/state expectations до переключения worker.

## Runtime / rollback

Worker не переключался. Read-only process check нашёл единственный `python.exe -u bot.py`, PID 1508. [.local/bot-runtime.json](../../.local/bot-runtime.json) фиксирует старый source snapshot: `source_first`, `knowledge_stage3_retrieval_20261022` (934 points), Groq `openai/gpt-oss-20b` / medium; его 26 SHA не включают `app/dialogue_understanding.py`. Process PID жив и использует исходно загруженный код. Действий остановки/старта, SQLite backup/write, Qdrant write, Telegram сообщений и пользовательских LLM calls от worker не выполнялось.

Новый receipt не создавался. Runtime rollback plan при успешном gate: сохранить текущий receipt и проверить единственный PID; сделать SQLite online backup; остановить только проверенный worker; стартовать тот же bot с process-only `RAG_ENGINE=source_first` и существующей Stage3 collection; сверить загруженные SHA, model, collection, allowlist hash и `Application started`; при любом mismatch не допускать сообщения и вернуть предыдущий process-only runtime. Точный PowerShell launch/stop script ещё не подготовлен, так как gate не прошёл.

## Изменённые файлы

- `app/dialogue_understanding.py` — компактная strict JSON Schema, exact-span/schema validation, Groq call и сериализация наблюдения.
- `app/dialogue_state.py` — semantic observation reducer path, неизвестные slots, сохранение clarification transition/task isolation.
- `app/conversation_store.py` — precomputed typed event хранится в существующем `diagnostics_json`, revalidated и применяется ровно один раз при replay.
- `bot.py` — Understanding выполняется до `ConversationStore.begin` только для allowlist Source-first.
- `app/source_first_service.py`, `app/answer_service.py` — semantic routing, direct specialist, understanding trace, отказ от retrieval при ошибке модели.
- `tests/test_dialogue_understanding.py` — 12 targeted tests.
- Ранее начатые `app/source_first_service.py`, `docs/PROJECT_STATE.md`, `docs/RAG_MASTER_PLAN.md`, диагностика/тесты Source-first сохранены без отката.

## Ограничения и следующий шаг

- Live Groq JSON Schema acceptance и реальное поведение 20B не подтверждены из-за 429 после исправления обнаруженного schema дефекта.
- Stage2 metadata и версия Qdrant client/server остаются прежними operational limitations; текущий worker на Stage3.
- Specialist flow сохраняет заявку только после нажатия пользователем существующих кнопок; доставка сотруднику не настроена.
- Нужен финальный review edge cases persisted contract/unknown scopes и повторный семисценарный Groq gate.

Единственный следующий шаг: после снятия Groq throttling повторить семисценарную synthetic understanding проверку; worker оставить неизменным, пока каждый сценарий не даст валидный контракт и ожидаемый state transition.

## 2026-10-25 — причинный разбор ручного Telegram-провала

Проверка была read-only: SQLite открыт с `mode=ro`; локальная JSONL-трасса и runtime receipt сопоставлены по UTC timestamps; секреты, user/chat IDs и сырые сообщения в этот журнал не переносятся. В окне 15:01–15:02 MSK найдено шесть ходов в трёх разговорах одного чата. Для всех шести Groq вернул успешный HTTP и структурно допустимый JSON; provider/schema ошибок в этих ходах нет.

| Группа хода | Сохранённый structured result | Где оборвался путь | Подтверждённая причина |
|---|---|---|---|
| Смешанное приветствие + определение ОФД | `request_type=explanation`, `intent=explain`, `operation=explain` | local Understanding validation; reducer/retrieval не запущены | Алиас `explanation` отсутствовал в request type словаре. |
| Продолжение «зачем он нужен кассе» | `request_type=explain_operation`, `relation=continuation` | local Understanding validation; state остался пустым | Алиас объяснительной классификации отсутствовал, поэтому валидная relation не дошла до state. |
| Повтор определения | `request_type=explanation`, `relation=new_task` | local Understanding validation | То же чрезмерно закрытое перечисление request type. |
| Диагностика Эвотора | `request_type=diagnosis`, `operation=diagnosis`; exact symptom/goal spans | reducer и Stage3 retrieval; до planner/render остановлен source scope gate | `request_help` сброшен в `unknown`; производитель «Эвотор» пришёл как `object` вместо `entities`, и object-vocabulary его отклонил. Поиск выбрал частичный approved document `evotor/fn/fn-210.md` через `unresolved_task_fallback`; procedure scope не подтверждён, поэтому запрос оператора был fail-closed уточнением. |
| Ответ «Платформа ОФД» | `relation=clarification_answer`, `operation=diagnose`, service alias exact-spanned | local Understanding validation; pending service slot остался | Validator считал request type `information` несовместимым с `diagnose`, хотя turn был ответом на уточнение. Из-за раннего aggregate throw entity field diagnostics потерялись. |
| Найти чек по ФД в Платформе ОФД | `request_type=information`, `intent=information_request`, `operation=find_receipt`; goal span присутствует | local fields частично приняты; replay validator затем no-op; early task gate до retrieval | `information_request` и `find_receipt` отсутствовали в нормализации; независимые значения стали `unknown`. Replay требовал `information => general/explain`, отбросил записанный semantic observation, сохранил пустой state, после чего `dialogue_state_task_incomplete` спросил повторно о задаче. В этом direct-query turn model не вернул entity candidate для явно написанного сервиса, хотя local alias vocabulary его знает. |

Первые три сообщения принадлежат одной conversation: после ошибки state не изменился, поэтому продолжение не стало evidence для reducer. Эвотор и ответ про оператора принадлежат другой conversation: после successful diagnostic turn state сохранил `operation=diagnose`, `intent=unknown`, и pending `service` clarification; ошибочный validator не записал подтверждённую платформу. Поиск чека — третий новый task; state в нём и должен начинаться заново, но должен быть заполнен текущим ходом.

Runtime receipt при read-only проверке показывал PID `19552`, `source_first`, Groq `openai/gpt-oss-20b` / `medium`, Stage3 `knowledge_stage3_retrieval_20261022` / 934 points, allowlist count 3. Receipt hash snapshot указывает на старый кодовый commit `367e5db`; процесс активен, автоматическое переключение запрещено до успешного повторного gate. Текущий `.env` не используется для вывода о фактически унаследованном process environment.

## Локальная коррекция и сохранённый-output replay

В `app/dialogue_understanding.py` расширены общие aliases request type/intent/operation; turn type и операция больше не обязаны быть одним классом, а незнакомая операция в вопросе с exact goal получает только read-only `search`. Exact known entity aliases, пропущенные моделью, восстанавливаются из текущего текста по зарегистрированному alias + проверяемому span; отрицание/неуверенность и слоты проверяются. `app/dialogue_state.py` сохраняет relation/transition ответа на уточнение при route update. `app/conversation_store.py` и `bot.py` сохраняют фазу и стабильный код ошибки для distinction provider/transport/decode/shape/semantic/replay.

Шесть raw outputs из локальной приватной трассы прогнаны без API и без записи в production SQLite: 6/6 прошли typed validation, evidence replay и изолированное state replay. Состояния: объяснение `general/explain`; зависимое продолжение оставило ту же задачу; явный повтор создал новую задачу; Эвотор подтвердил только exact manufacturer + symptom/goal и остался в diagnose; ответ назвал exact зарегистрированный OFD alias и снял service clarification, сохранив операцию; поиск чека стал `general/search` с route `Платформа ОФД`, прежнее раннее уточнение задачи не срабатывает. Approved retrieval/planner и качество ответа этими локальными проверками пока не подтверждены.

Targeted checks: `python -m py_compile ...` passed; `python -m pytest tests/test_dialogue_understanding.py tests/test_source_first_dialogue_contract.py -q` → **35 passed**; `git diff --check` passed. Следующий шаг — небольшая контролируемая real Groq серия и фактический approved Stage3 retrieval/planner path; runtime не переключать до прохождения каждого сценария.

## Остановка real gate: локальный exception и rate limit

Первый запуск controlled natural-turn smoke выявил ошибку в новом fallback ordering: `request_type` fallback прочитал normalized operation до её присваивания (`UnboundLocalError`). Попытки с этим внутренним дефектом не считаются successful API/Understanding результатами; provider content пяти таких ответов не попал в local trace из-за неперехваченного exception. Путь теперь исправлен: semantic labels нормализуются до fallback; неожиданные internal exceptions проходят через trace с `phase=internal` и без публикации текста в общие отчёты. `py_compile`, targeted suite **35 passed**, saved-output replay **6/6**.

Следующий вызов Groq получил HTTP 429, `rate_limit_exceeded`: on-demand GPT-OSS 20B bucket — **8,000 tokens/minute**, **6,753 used**, **2,117 requested**, reset/retry in **6.525 seconds**. Другие лимиты этим response не раскрыты. Точное provider body/request без Authorization сохранены локально; organization identifier не публикуется. Массовых повторов не было; серия остановлена.

Существующий Telegram PID 19552 продолжает работать на старом receipt snapshot. Ни SQLite production, ни Qdrant, ни worker не менялись. Live route/usefulness gate не пройден; перед следующим одиночным вызовом нужен освобождённый rolling TPM window, а worker запрещено переключать до полного успешного gate.

## Исправление topic-object retrieval

Первый действительный natural follow-up сохранил `task:1`, `general/explain`, но Stage3 выбрал partial approved FN-basics candidate. Planner сформулировал, что section будто отвечает на вопрос о нужности ОФД, хотя candidate был о фискальном накопителе; безопасно завершил `planner_could_not_select_safely` без технических шагов.

Root cause: `ОФД` отсутствовал в supported object vocabulary и был отброшен на первом сообщении. На follow-up точное client span «он» было принято как evidence для model object `ОФД`, хотя эти значения не совпадают. Поскольку state не содержал object, task category осталась неоднозначной и retrieval применил `unresolved_task_fallback`.

Object vocabulary теперь включает ОФД; validator проверяет exact alias/value в quoted span. Неподтверждённый объект на местоимении не добавляется, но существующий object остается в state при continuation. Retrieval task-category выбирает `ofd_connection` по grounded object + explain operation. Saved-output read-only replay на прежнем Q2 output теперь выбрал approved `atol-online-11256-what-is-ofd` и совместимые OFD-кандидаты, а `atol-online-11253-fn-basics` отклонил с task mismatch. Targeted tests — **36 passed**. Planner и реальный follow-up ещё не повторялись после этого исправления; quality gate открыт, Telegram worker PID 19552 не переключался.

## 2026-10-25 — один readiness-вызов после schema correction

- Локальная проверка JSON Schema: strict object; все required fields покрыты; nullable `goal` и `specialist_evidence` имеют `type=[object,null]`.
- Выполнен ровно один реальный вызов `understand_message("Что такое ОФД?")`, модель `openai/gpt-oss-20b`, reasoning `medium`. Provider request прошёл и вернул JSON (не HTTP 429/400), но локальная typed validation остановила его: **`intent lacks user evidence`**. Следовательно typed результата для reducer не было; reducer smoke, retrieval smoke и Telegram integration smoke не выполнялись.
- Usage: prompt 997, completion 997, total 1994 tokens; duration 1743 ms. Ошибка связана не с rate limit, а с тем, что модель выдала `intent` claim без обязательной source quote. Доступные provider rate/quota limits из этого response не сообщались; в рамках единственного вызова не запрашивались.
- Текущий runtime read-only: ровно один `python.exe -u bot.py`, PID 1508; receipt PID совпадает. Receipt подтверждает прежний Source-first process, Stage3 `knowledge_stage3_retrieval_20261022`, Groq GPT-OSS 20B / medium, allowlist count 3, но не содержит SHA `app/dialogue_understanding.py`; `phase=runtime_initialized_before_polling`. Процесс не останавливался и не перезапускался.
- Вывод: модельный readiness gate всё ещё FAILED. Новых LLM запросов, user DB writes, Qdrant writes, конфигурационных изменений и runtime switch не было. Перед повтором нужно решить минимально, как довести missing-evidence claim до валидного результата; затем сделать один ограниченный повторный вызов.

## 2026-10-25 — семантические labels без citation spans, factual claims со spans

- **Raw предыдущего ответа:** последний вызов с ошибкой `intent lacks user evidence` выполнился в одноразовом runner-е, который напечатал только исключение/usage и не сохранил parsed JSON. Ни локальные stdout/stderr, ни `.local/bot-runtime.json` raw provider content не содержат. Поэтому нельзя задним числом установить текст `intent`/цитаты; установленный по коду root cause — валидатор требовал необязательный span для semantic intent label.
- **Изменение общего контракта:** schema больше не просит `intent_evidence`, `operation_evidence` или `relation_evidence`; prompt прямо обозначает `request_type`/intent/operation/relation как semantic classifications. Concrete claims по-прежнему требуют точных цитат из текущей реплики: named entity и canonical alias, object, goal, symptom, явное «не знаю» для unknown slot, прямой specialist request. `Observation` хранит exact span каждого unknown slot; replay проверяет его message id/text и соответствие набору unknown slots. `DialogueManager` получает labels без искусственных evidence fields, но отклоняет неподтверждённые facts.
- **Локальная проверка:** `py_compile` прошёл. Целевой набор understanding/state/source-first: **58 passed**. Независимые информационные переформулировки проходят без intent citation; ошибочная OFD/provider entity и unknown fact со span вне текущей реплики отклоняются. Полный suite после этого последнего contract delta не запускался.
- **Один реальный Groq-вызов:** новый single call по тому же синтетическому информационному запросу прошёл provider response/JSON decode, но validator отклонил его с `entity value is not grounded by its evidence`. Значит предыдущая intent citation ошибка устранена, но новый typed result не прошёл entity alias grounding. Runner не сериализовал raw structured response/error details или usage; изменить код для будущих validation failures — такие parsed response теперь добавляются в `UnderstandingError` и сохраняются в turn diagnostics. Для этого failed call точное entity slot/value без raw payload неизвестно.
- **Непройденный путь и runtime:** typed `Understanding` не вернулся; `DialogueState`, SQLite replay, Qdrant route и интеграционный smoke по этой попытке не выполнялись. Read-only проверка нашла один прежний worker PID **1508**, receipt PID совпадает; receipt: старый Source-first snapshot, Stage3 `knowledge_stage3_retrieval_20261022`, GPT-OSS 20B / medium, allowlist 3, без SHA `app/dialogue_understanding.py`. Worker не остановлен, SQLite/Qdrant/config не менялись.
- **Решение:** gate FAILED по factual entity grounding; не запускать интеграционный smoke с недостоверным Observation и не переключать worker. Следующий один минимальный прогон должен сохранить raw structured JSON при fail и различить generic category term от named client entity без ослабления exact-span/alias validation. Если пройти validator — применить reducer и выполнить только read-only retrieval routing smoke; затем controlled restart существующего worker.
## 2026-10-25 — field-level validation instead of all-or-nothing rejection

- **Root cause:** `validate_response` raised from the entity loop when one claim failed alias grounding. Since the outer Understanding handler treated every validator exception as fatal, independent valid classifications/facts were discarded too.
- **Contract update:** each factual field is now checked independently against a unique exact current-message span. Known entities canonicalize from the source quote through `ENTITY_NAMES`; an unsupported entity is rejected and omitted, while unrelated valid fields survive. Invalid intent/operation/relation defaults to `unknown` with a field-level reason, allowing deterministic clarification. Invalid request type, contradictory task classifications, and malformed overall structure remain fatal.
- **Trace:** every parsed provider JSON is appended to ignored `.local/conversational-understanding.jsonl`, with model, usage, latency, output hash, per-field accepted/rejected/omitted reasons and raw structured output. The trace contains customer quote fragments and stays local; no tokens or API keys are included. Public artifacts only describe synthetic test inputs.
- **Safety:** rejected entities are never added to `Observation`; the existing Source-first source applicability/scope checks remain unchanged. A missing confirmed product/service cannot be filled by the rejected claim, so retrieval can clarify or escalate.
- **Local evidence:** `py_compile` passed; targeted test set passed **62/62**; no provider calls were made in this implementation step. Next is one controlled Groq Understanding call plus persisted reducer/routing verification. Worker is not restarted until that and a small deterministic continuation/new-topic smoke pass.

## 2026-10-25 — единственный live call вернул HTTP 400

- После реализации field-level validation выполнен один `understand_message("Что такое ОФД?")` на настроенном Groq. Provider вернул HTTP **400** до structured output; валидатор, DialogueState, Qdrant routing и smoke не запускались.
- Тело ошибки вызова не сохранилось: до этого HTTP error path записывал status, но не body. Точная причина 400 неизвестна, это нельзя приписать schema или модели без исходного сообщения. После обнаружения добавлена запись provider error body в приватный `.local/conversational-understanding.jsonl` для следующего разрешённого вызова; ключ и Authorization в trace не пишутся. Дополнительного Groq-запроса не было.
- Успешного typed result нет — worker оставить как есть. Read-only состояние до запуска: один старый PID 1508 и прежний receipt, collection `knowledge_stage3_retrieval_20261022` / 934 points, model `openai/gpt-oss-20b`, allowlist count 3; новый Understanding в фактически запущенном процессе отсутствует.

## 2026-10-25 — причина HTTP 400 найдена, provider schema упрощена

- Следующий контролируемый запрос сохранил локально точное тело API, request payload без Authorization и `response_format`. Ошибка: `invalid_request_error`, code `json_validate_failed`, поле `/object` не прошло `/properties/object/enum`; `failed_generation` содержит `object: "ОФД"`. API ожидаемо отклонил это значение до локального typed validator.
- Endpoint и внешний request format корректны: `/chat/completions`, `response_format.type=json_schema`, `json_schema.strict=true`, model `openai/gpt-oss-20b`. По актуальной [официальной документации Groq Structured Outputs](https://console.groq.com/docs/structured-outputs) эта модель указана среди strict-compatible; strict режим требует required fields и `additionalProperties:false`. Schema имела их, но словарь object enum был уже реального языка клиента.
- Сняты enum-перечни с provider-facing semantic fields/object/slots; точные vocabulary правила остались в локальной field-level validation. Сохранены строгая JSON структура/типы, source spans, alias grounding, per-field reject, fail-closed contradiction checks и Source-first scope gates.
- Локально после изменения: `py_compile` прошёл, 62 targeted tests passed. Следующий шаг: один исправленный Groq call; при валидном output — SQLite replay, Qdrant/Source-first route и компактный deterministic continuation/topic-switch smoke. Никакой runtime switch пока не делать.

## 2026-10-25 — исправленный live call и полный route smoke

- После `json_schema` enum removal Groq вывел `information_request`, `definition`, `explain`, `object=ОФД` с quote `ОФД`. Local validator канонизировал первые два labels, сохранил explain, отклонил только object как unsupported vocabulary. Valider result passed. Usage 778/669/1447; 1530 ms; модель `openai/gpt-oss-20b`. Точный raw structured response и API body находятся только в `.local/conversational-understanding.jsonl`.
- Persisted SQLite replay восстановил `general/explain`, без факта `ОФД` как task object и без service route. Использован read-only Qdrant Stage3 `knowledge_stage3_retrieval_20261022` (934 points) из process environment прежнего worker; retrieval 3 результата; Source-first planner вызван и завершился `source_first_exact_section`, status `generated`, generation error отсутствует.
- Локальный deterministic multi-turn smoke: уточняющий запрос сохранил task ID `task:1`; смена темы сформировала новый task `access/add_employee` и route `aQsi Online`. Дополнительных Understanding calls в этом smoke не было.
- Targeted suite после schema/alias changes: **63 passed**.
- Pre-restart: один worker PID 1508; read-only проверка показала ноль pending turns/attempts в обеих SQLite. `.env` сейчас отличается от живого процесса (`legacy`, Stage2, пустой source allowlist); worker restart должен унаследовать точный environment старого PID (`source_first`, Stage3, allowlist count 3), не редактируя `.env`. Restart и новый runtime receipt ещё не подтверждены.

## 2026-10-25 — существующий Telegram worker перезапущен

- После read-only preflight (0 pending conversation messages; 0 pending expert attempts) остановлен старый PID **1508**. Новый worker запущен из того же checkout и с environment snapshot прежнего процесса; `.env`, токен, SQLite и Qdrant не переписывались. Активен ровно один `python.exe -u bot.py`, PID **19552**; log содержит `Application started`.
- Runtime receipt [`../../.local/bot-runtime.json`](../../.local/bot-runtime.json): `source_first`, Groq `openai/gpt-oss-20b` / `medium`, Qdrant `knowledge_stage3_retrieval_20261022` / 934 points, allowlist count 3 и hash прежнего allowlist. Receipt includes current SHA for every `bot.py` and `app/*.py`. Verified core hashes: bot.py `867e8ae048a7e15d2aa2e065ef6a73e49c9d5cf3ff8555e6acd96eb17a97224d`; dialogue_understanding.py `b44ea42ecb269b967104627c497c819352aa06a769b2f88f0dbfc8cfa57ed22a`; dialogue_state.py `f05459f8275463738fbd3632244002ee7080460484b3dfd9818d99819a96f416`; source_first_service.py `b49952948b1c5ca60f173d5b056b3f409bf74e9499d67c63bfa464c393f9d5e9`; conversation_store.py `871b7740f2f62804bb350eed51fc6af6fcecf892319d4be39518e775aacec9f7`.
- Все operational gates пройдены. Автоматические проверки остановлены; следующие реальные диалоги в Telegram пользователь тестирует вручную. Commit/push не выполнялись.

## 2026-10-25 — manual pilot failure replay and search routing correction

### Сохранённые реальные ответы: локальный повтор

Raw Groq structured outputs из фактических Telegram turns повторно прогнаны без API. Шесть typed results проходят независимо; reducer state показывает OFD continuation, новый task на повторе, diagnosis+manufacturer для Эвотора, подтверждённый оператор Platforma OFD и direct receipt lookup с `receipt/search`. Полевая причина direct lookup: Groq не дал object evidence для `receipt`, а реплика содержит несколько зарегистрированных сущностей, так что all-message uniqueness была слишком строгой. Search intent теперь выбирает unique registered object в exact goal span перед параметрным `по`/`за`; `чек` остаётся exact quote, `ФД` не становится объектом поиска. Источники/aliases без exact text по-прежнему отвергаются.

Stage3 read-only retrieval replay после коррекции выбирает approved Platforma OFD receipt-search source и отклоняет `fiscal_drive`, `cash_search`, `ofd_connection` кандидатов как category mismatch. OFD follow-up держит `object=ОФД` и отклоняет FN article. Targeted tests: **39 passed**.

### Один новый natural live turn

Новый mixed greeting + request for a simple OFD definition дал valid Understanding на `openai/gpt-oss-20b` (1,322 tokens). DialogueState сохранил `general/explain`, object ОФД. Stage3 retrieval и planner дали `source_first_exact_section`, generated, approved definition source. Ответ верно объяснил передачу фискальных документов в ФНС, однако также упомянул тариф/договор и очередь передачи, что не требовалось в вопросе. Это подтверждает работающий маршрут, но не достаточное качество. Отдельных массовых прогонов не было.

Рабочий Telegram process не тронут: единственный PID 19552 совпадает с receipt; локальные SHA новее receipt. Следующий gate — живые естественные continuation, diagnosis/operator clarification и receipt lookup с проверкой полной полезности/безопасности; при любом fail runtime не переключать.

## Итог после limited live natural smoke

Проверены Q1 mixed greeting/OFD, Q2 continuation, Evotor diagnosis + оператор clarification, и прямой FD lookup. Q1, Q2, diagnosis/operator, и direct lookup имеют valid provider output; direct lookup потребовал одного retry после подтверждённого общего alias gap (`question`, `information`, `lookup`). Повтор после исправления успешен и даёт ответ из 3 approved Platforma OFD sections. Ни один отказ не дал неподтверждённых технических действий.

Gate остаётся FAILED: продолжение повторяет исходный статический ответ, а Evotor + Platforma OFD diagnosis не имеет применимого approved source и безопасно эскалируется. Единственный прежний worker PID 19552 не остановлен и не обновлён; его receipt hashes показывают старую загруженную версию. Новая версия не заявляется в runtime. Для следующего этапа требуется отдельное согласование source-grounded compositional answering и approved Evotor coverage.

`.env` не считается источником работающей конфигурации: он не задаёт `RAG_ENGINE`, указывает Stage2 collection и пустой Source-first allowlist; PID 19552 использует `source_first`, Stage3 collection и allowlist count 3 из process environment. Запуска из `.env` не делали; текущий worker не тронут.

## 2026-10-25 — локальная проверка информационного composer

Путь до изменения: planner выбирал approved section, далее `exact_render` возвращал весь текст секции, не адаптируя его к текущей реплике. Для `general/explain` добавлен отдельный короткий композиционный проход (текущий вопрос + active task + недавний диалог + точный выбранный approved fragment); каждое предложение независимо проверяется `claim_supported`. Ограничены длина/число предложений, блокируются неподтверждённые assertions, процедура, опасное действие и unresolved question; при провале — безопасная эскалация. Остальные task types и их renderer не менялись.

Локальный двухходовый smoke (`Что такое ОФД?` → `А зачем он нужен кассе?`) сохранил task/object и сформулировал вторую реплику как отдельное объяснение роли ОФД. Негативные кейсы неподтверждённого продления тарифа и технической проверки очереди отвергнуты. `tests/test_dialogue_understanding.py` + `tests/test_source_first_dialogue_contract.py`: **41 passed**. Это пока тестовый/локальный результат; один live smoke необходим перед runtime switch.

### Live gate diagnosis update

Первый live Q2 smoke выбрал 15 approved retrieval results, но planner вернул безопасную эскалацию до composer. Причина в чрезмерно общем planner prompt: требовал customer service/model applicability и для чистого explanation без действий. Исправлен только prompt distinction: general/explain может использовать общий факт scoped vendor section при явной атрибуции; техническая инструкция требует подтверждённого service/model, как и раньше. Другие applicability gates и Source-first safety не менялись. После этого исправления сделан один live retry.

Второй live retry показал planner `mode=select` с объяснением релевантности, но `applicability/order` flags не подтвердили техническое действие и блокировали informational flow до composer. Код теперь разводит action gate и информационный выбор: для `general/explain` нужен approved candidate и последующая sentence-level claim validation; для диагностики/процедур оба planner flags строго обязательны. Локальный тест проверяет информационный `select` при false flags и ранее существующий procedure scope test остаётся строгим. Targeted suite **41 passed**.

### Итог ограниченного live follow-up gate — 2026-10-25

Повторно использованы сохранённые и заново typed-validated Understanding-результаты двух фактических реплик: `general/explain` → `information/continue`; DialogueState сохранил один task и `object=ОФД`. Один Source-first route к Stage3 Qdrant дал 15 retrieval результатов; planner выбрал approved раздел `Что проверено по инструкции производителя` из `what-is-ofd.md`. Composer `openai/gpt-oss-20b` был вызван один раз и независимая проверка отклонила его результат с точной причиной `unsupported_information_claim`. Финальный route остался безопасным `information_composition_unverified`; пользовательский Telegram worker PID 19552 не переключался.

Локальный артефакт [`../../.local/ofd-followup-composer-smoke.json`](../../.local/ofd-followup-composer-smoke.json) сохраняет route, выбор источника, validator reason и SHA composer output. Текущий production diagnostic не записал raw text или причину по каждому предложению, поэтому конкретная неподтверждённая формулировка не установлена. Не делать предположение или ослаблять `claim_supported`; следующий контролируемый повтор должен сохранять исходный composer JSON только локально и добавлять reason по каждой sentence validation. Worker gate остаётся FAILED, runtime receipt прежний.

### Диагностический повтор только OFD Composer — 2026-10-25

Read-only поиск прежнего SHA `f63494628a93729b7ff9d781fd51132f6e0f1ac69696945ca9e1ab1f7835eb7b` нашёл только [прежний smoke](../../.local/ofd-followup-composer-smoke.json); raw text прежнего отказа отсутствует. Для одного контролируемого live replay добавлен приватный [harness](../../.local/diagnose_ofd_composer.py), сохраняющий raw Composer text и результаты неизменённого validator по каждому предложению. Сохранённые Groq Understanding outputs двух фактических OFD turns применены без новых Understanding вызовов.

Результат [трассы](../../.local/ofd-followup-composer-diagnostic.json): DialogueState сохранил один task и `object=ОФД`; retrieval — 15 результатов Stage3, planner — approved `what-is-ofd.md` / `Что проверено по инструкции производителя`. Composer выдал: «ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает их и передаёт в ФНС в предусмотренном формате. Поэтому он нужен, чтобы касса могла отправлять чеки в налоговую.» Текущий `claim_supported` принял оба предложения; первый почти дословно соответствует источнику, второй является смысловым выводом из подтверждённой передачи ККТ → ОФД → ФНС. Output SHA `047c26a6a9fb8376eb9fbbfc0a2e999a227701ad5c455737b53d44b65ecb4c1d`, отличен от прежнего. Итог route — `source_first_grounded_information_summary`.

**Отрицательный результат:** старый `unsupported_information_claim` не воспроизведён и его текст не восстановлен. Этот эксперимент не доказывает, был ли прошлый отказ неподтверждённым утверждением LLM или ошибкой Grounding. Валидатор/production код не исправлялись. Минимальный вариант последующего решения: сохранять закрытый raw Composer trace при отказе с per-sentence evidence/decision, затем изменить только установленную причину. Telegram worker, пользовательские SQLite, Qdrant и `.env` не менялись; commit/push не выполнялись.

### 2026-10-25 — автоматическая локальная диагностика Composer refusals

Изменён только диагностический код в `app/source_first_service.py`, в точке уже существующего отказа Composer. Каждый отказ теперь append-ится в `.local/source_grounded_composer_rejections.jsonl` с ответом Composer, statement segmentation, per-sentence checks/decision/reason, точным approved excerpt и overall grounding result. Существующая validation-функция и её критерии не менялись. Known runtime secrets и типичные API/bearer/JWT/Telegram token strings маскируются; prompt/history/IDs не записываются. Возможные PII в ответе/источнике остаются локально, отмечены в каждой записи и не должны экспортироваться. `.local/` уже в `.gitignore`.

Без API проверены два примера: paraphrase, подтверждённый approved OFD section, принят; выдуманное утверждение о возврате комиссии отклонено как `unsupported_information_claim`. Проверено обратное чтение synthetic trace из JSONL с полным evidence, sentence reason и overall rejection; временный trace удалён. Исторический отказ не запрашивался повторно и его cause не выводится из этого теста. Worker, retrieval configuration, DialogueState, SQLite пользователей и Qdrant не затронуты.

### 2026-10-25 — deterministic fix for concept-definition misrouting

- **Saved-output replay / cause:** private live Q1 raw Groq fields were `request_type=question`, `intent=information`, `operation=lookup`, object `OFD`. Existing alias normalization maps `information → general` and `lookup → search`; DialogueState reducer receives and retains `general/search`. The E2E state is in-memory, so SQLite or a later state mutation did not originate this value. Raw Groq chose the wrong operation; normalization faithfully passed it as search.
- **Narrow generic rule:** [`app/dialogue_understanding.py`](../../app/dialogue_understanding.py) recognizes explicit definition wording independent of the named concept. For an information turn whose normalized operation is `search/unknown`, it resolves to `general/explain` unless the same message contains an explicit lookup verb. No OFD/FN/KKT-specific branches. `Как найти чек по ФД?` remains `receipt/search`.
- **Offline coverage:** [`test_dialogue_understanding.py`](../../tests/test_dialogue_understanding.py) replays the saved labels and covers `Что такое ОФД?`, `Что такое ФН?`, `Объясни, что такое ККТ`; [`test_source_first_dialogue_contract.py`](../../tests/test_source_first_dialogue_contract.py) sends the saved raw OFD shape through Source-first. Targeted verification: **5 passed**.
- **Read-only route replay:** [private artifact](../../.local/ofd-definition-route-replay-20261025.json), Stage3 collection `knowledge_stage3_retrieval_20261022`; Qdrant was read-only, Planner/Composer generation stubbed, no Groq request. OFD reached retrieval (15 results), Planner, Composer and passed existing answer validation without service clarification. FN reached retrieval (3) and Composer, but its deterministic stub emitted an unresolved question; unchanged validation rejected it as `answer_contains_unresolved_question`. KKT reached retrieval (3) and Composer; selected evidence had no direct definition, so the stub produced no supported answer and existing validation failed closed as `empty_or_no_supported_answer`. Routing is fixed locally; these answer quality outcomes were not changed.
- **Scope/status:** no Relevance Gate, Grounding, Retrieval code/config, Qdrant data, knowledge base, SQLite users, `.env`, or Telegram process change. A live Groq call was unnecessary because the exact saved provider output deterministically reproduced the fault. No worker restart, commit, or push. Full natural live E2E remains unverified; known next Composer blocker is `answer_does_not_address_current_question_terms`. Stop at this route fix.
