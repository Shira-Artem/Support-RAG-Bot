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
