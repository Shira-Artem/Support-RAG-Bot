# Support-RAG-Bot — техническое состояние проекта

Обновлено: 2026-10-23. Этот файл — актуальная техническая память проекта. Факты, выводы диагностики и планы помечены отдельно. В журнал не включаются ключи, персональные данные, приватные идентификаторы диалогов и содержимое production SQLite.

## 1. Текущее состояние проекта

### Архитектура

- Telegram-бот (`bot.py`) принимает сообщения; `app/conversation_store.py` хранит сообщения и состояние диалога.
- `app/dialogue_state.py::LexicalAnalyzer` формирует типизированные наблюдения; `DialogueManager` редуцирует их в `DialogueState` с историей диалога и контекстом активной задачи. Отдельного `app/message_analyzer.py` файла нет; `MessageAnalyzer` — Protocol в `app/dialogue_state.py`.
- `app/rag_query.py` строит запрос; `app/retrieval_pipeline.py` выполняет retrieval, проверяет статус/совместимость и выбирает контекст.
- `app/answer_service.py` управляет уточнениями, retrieval, ответом и валидацией; `app/response_grounding.py` проверяет соответствие ответа evidence.
- `app/runtime.py` собирает runtime-конфигурацию и RAG-компоненты.
- Экспериментальный A/B CLI `scripts/compare_dialogue_analyzers.py` изолирован от Telegram/RAG; A и B используют отдельные `DialogueManager`/состояния, B — Groq structured JSON.

### Ветка и версия

- Ветка: `main`.
- Предыдущий подтверждённый commit: `a026dd2de40f192329049aec2b26ba5940f7d664` (`Add safe procedural evidence applicability checks`); локальная `main` и `origin/main` были синхронизированы перед текущей публикацией.
- DialogueState v2.1 и изолированный A/B стенд включены в текущую публикацию на `main` по явному запросу пользователя от 2026-10-23. Финальный commit SHA будет внесён в журнал после создания commit.

### Конфигурация (подтверждённые defaults/receipt, секреты опущены)

- RAG использует локальный Qdrant endpoint и коллекцию `knowledge_stage3_retrieval_20261022`; при диагностике receipt указывал 934 points.
- Embedding default: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Runtime receipt указывал provider Groq, model `openai/gpt-oss-20b`, reasoning effort `medium`, `demo=false`.
- Эти сведения описывают конфигурацию зафиксированного receipt, а не подтверждают состояние работающего worker сейчас.
- Код и проверки этой P1-задачи не запускали Groq и не писали в Qdrant.

### Последние подтверждённые проверки

- Полный pytest после A/B стенда: **288 passed** (включая тесты схемы/span validation); до стенда после v2.1 было 278 passed.
- Targeted state/P0/P1 регрессии: **143 passed**.
- Retrieval benchmark: 100 вопросов, 83 approved; expected context **81/83**, те же два baseline false rejections, новых отказов нет. Метрики: top1=55, top5=74, top10=78, top30=83; это retrieval rank, не точность ответов.
- `git diff --check`: пройден после финальных изменений.
- Первые ручные A/B последовательности: 7 пользовательских реплик, 7 Groq вызовов; 3 результата прошли исходную local validation, 3 ответа отвергнуты validation и 1 HTTP 400 из-за строгой object enum. Текущий cross-field audit дополнительно выявил 1 из этих 3 как intent-object mismatch. Для 3 прошедших исходную проверку ответов receipt сообщил 8,457 токенов. Всего за задачу было 17 запросов Groq, включая 10 предварительных/отладочных вызовов; известный usage по полученным usage receipts составил 16,649 токенов, usage остальных ответов не восстановим. Runner теперь сохраняет usage до validation для будущих запусков.
- Sanitized A/B артефакт: `docs/experiments/dialogue_analyzer_ab_2026-10-23-final.jsonl`; тексты реплик и произвольные evidence quotes в файл не записываются.
- Benchmark использовал read-only retrieval из локальной коллекции `knowledge_stage3_retrieval_20261022`; без индексации и Groq. Локальная embedding-модель загрузилась; HF Hub вывел предупреждение об anonymous rate limits.

## 2. Принятые архитектурные решения

### Совместимость операции — единая проверяемая политика

- Решение: сравнивать запрошенную операцию и операцию документа общим механизмом со статусами `match`, `unknown`, `mismatch` (`app/procedure_policy.py`). Явное несовпадение запрещает выбор и не может быть обойдено unresolved-task fallback.
- Причина: до P1 fallback пропускал approved-документ при `operation_match=False`, что позволило использовать перерегистрацию ККТ для неопределённого запроса об изменении настроек ФН.
- Ограничение: неизвестная операция не равна доказанному совпадению; она может пройти только применимые существующие safety gates и достаточную проверку контекста/evidence.

### Применимость отдельно от тематической релевантности

- Решение: отдельно проверять status/operation и применимость инструкции к известным оборудованию, модели, сервису и семейству задачи (`document_applicability`).
- Причина: тематически похожий специализированный документ нельзя подавать как универсальный для неизвестного устройства.
- Ограничение: не додумывать vendor/model/service; применимость может быть подтверждена только теми metadata и evidence, которые реально есть.

### Изменение фискальных настроек требует уточнения

- Решение: неопределённое изменение ФН/фискальных настроек уточняет конкретное действие и оборудование до выдачи процедуры; безопасная информационная проверка ресурса/состояния ФН не блокируется автоматически.
- Причина: изменение без параметров может привести к выдаче опасной процедуры перерегистрации.
- Ограничение: не превращать всю категорию `fiscal_drive` в отказ; не ослаблять существующие safety gates.

### Grounding без дополнительного LLM

- Решение: шаг/действие подтверждается отдельным исходным evidence clause, без сборки процедуры из несвязанных фрагментов. Repair не может восстановить документ с явным несовпадением операции.
- Причина: частичная релевантность документа не доказывает каждую часть предложенной процедуры.
- Ограничение: validator остаётся включённым; сохраняются безопасные частичные ответы и ограничения сервиса/модели.

## 3. Выполненные этапы

### P0 — routing и диагностика

- Подтверждённый локальный commit `0754352` содержит изменения в `app/answer_service.py`, `app/llm_client.py`, `app/retrieval_pipeline.py` и тестах P0 (`tests/test_p0_candidate_routing.py`, `tests/test_response_grounding.py`). Пользователь сообщил, что commit запушен.
- По доступному Git и отчётам цель этапа — безопаснее маршрутизировать операции и улучшить диагностику ответов/grounding. Подробные причинно-следственные детали для этого commit в текущем аудите не переустанавливались; см. ниже известные остатки после P0.
- Пять ручных Telegram-диалогов от 23.10.2026 показали, что P0 не устранил stale DialogueState, небезопасный unresolved fallback, слабую применимость специализированного документа и широкую неоднозначность операций.

### P1 — граница между релевантностью и разрешённым evidence (выполнен, commit в main)

- `app/procedure_policy.py`: общий `operation_compatibility` и `document_applicability`.
- `app/retrieval_pipeline.py`: fallback допускает неизвестную операцию, но блокирует подтверждённый mismatch; applicability для оборудования/сервиса и семейства задачи; generic OFD-запрос не получает vendor-specific процедуру без подтверждения.
- `app/answer_service.py`: предметное уточнение для неопределённого изменения фискальных настроек с вопросом о действии и оборудовании; зазор применимости приводит к уточнению с сохранением текущей задачи.
- `app/response_grounding.py`: запрет составлять одно предлагаемое действие из частично подтверждённых разных clauses; mismatch фильтруется также на repair пути.
- `tests/test_procedure_applicability.py`: позитивные и негативные проверки vague fiscal change/resource lookup, operation mismatch, equipment/service applicability и неподтверждённых составных claims.
- Commit `a026dd2` включён в `main`. На момент завершения P1: 269 pytest passed; benchmark 81/83 и те же 2 старых отказа, новых false rejection не было. Текущий полный набор повторно пройден после DialogueState v2.1: 278 passed, benchmark снова 81/83.
- Остаточный риск: проверяемая политика намеренно не решает понимание произвольных разговорных формулировок, сложную смену темы и общую семантику DialogueState.

## 4. Ручное Telegram-тестирование — 23.10.2026

### Контекст и достоверность runtime

- Пять ручных сценариев шли примерно в 15:39–15:41 МСК. В БД они соответствуют пяти `conversation_id`; `chat_id` общий. В таблице нет отдельного универсального `session_id`: runtime-состояние привязано к conversation.
- Сценарий 1 использовал уже существовавший conversation со старым состоянием задачи про банковские выписки/DirectBank. Сценарии 2–5 начались в новых conversations. Поэтому сценарии 1–4 не делили один общий `DialogueState`; загрязнён был только сценарий 1 своей предыдущей историей. Повторы вопроса в сценарии 3 и уточнения в сценарии 4/5 делили состояние внутри соответствующего разговора.
- Доступный runtime receipt сообщал PID/start, collection, число точек, провайдера, модель и reasoning. Однако время старта receipt (`12:38:09Z`) раньше P0 HEAD commit (`12:38:49Z` local +03), а сохранённые SHA-256 исходников не совпали с этим HEAD. Поэтому по имеющимся артефактам нельзя подтвердить, что worker загрузил именно точную версию локальных P0 исходников. Это ограничение доказательств, а не утверждение, что worker точно работал на старом коде.
- Идентификаторы и тексты приватных сообщений здесь намеренно не сохраняются; детали ниже обобщены.

### Сценарии и подтверждённые причины

| Сценарий | Наблюдение | Подтверждённый этап/причина | Статус после P1 |
|---|---|---|---|
| «Закончился ОФД» | `message_ambiguous`, без RAG/LLM | В исходном state сохранялась старая банковская задача; анализатор не выделил новую тему и оставил relation unknown. `DialogueState`/`MessageAnalyzer` не отделили новую жалобу от прежнего контекста. Конкретная причина — stale task плюс классификация неоднозначности; понимание сроков договора/оплаты/тарифа остаётся нерешённым. | P1 не менял analyzer/DialogueState. Требуется отдельный этап semantic understanding и разговорных вариантов «истёк договор/тариф/оплата ОФД» с безопасным уточнением. |
| Перестали загружаться банковские выписки; затем подтверждён DirectBank | Первый запрос классифицирован как просмотр списка (`bank_statement/list`), был выбран approved документ о загрузке всех счетов; LLM ответил о смежной операции, validator сообщил `unsupported_technical_claim`. После подтверждения сервис state/query стал `1С — подключение соединение`, retrieval дал `no_context` (`no_task_matched_candidates`). | `MessageAnalyzer`/task operation mapping превратили неисправность загрузки в list; подтверждение сервиса потеряло операцию диагностики выписок и переключило задачу на общее подключение. Ошибка в классификации плюс переходе состояния, а не отсутствие DirectBank вообще. | P1 общий operation mismatch gate помогает не выбирать явное несоответствие, но не реализует новый semantic analyzer/DialogueState переход. Нужен повтор Telegram после отдельной работы над state. |
| Неопределённое изменение настроек ФН; повтор того же текста | Первая попытка выбрала approved `platformaofd-reregistration-kkt`; ответ содержал перерегистрацию/ФНС; validator пометил `procedural_details_not_grounded`, но итог всё равно сгенерирован. Повтор того же текста вернул `no_context` / `unresolved_task_ambiguous`. | `_unresolved_task_fallback` мог обходить отрицательное operation match; validator не блокировал самостоятельную процедуру после частичной grounding. Разные candidate/order/state traces дали нестабильный ответ на повтор. | P1 уточняет действие+оборудование, блокирует явный operation mismatch на retrieval/repair и требует clause-level support. Безопасный запрос состояния/ресурса ФН остаётся допустимым при применимом источнике. |
| Как узнать подключённый ОФД; затем добавить сотрудника с правом только просмотра | Для generic OFD-запроса выбрана инструкция aQsi/OISM; ответ сделал вывод, что по IP/порту можно узнать фактически подключённый OFД. Validator снял неподдержанное название интерфейса, но не устранил весь неподтверждённый вывод. Новая тема сотрудника попросила service; сообщение о просмотре документов/запрете менять настройки не разрешило service ambiguity и осталось в прежнем pending clarification. | Перепутаны релевантность темы и применимость процедуры; evidence о таблице IP/port не подтверждало действие определения реально подключённого оператора. DialogueState оставил ожидаемое поле сервиса главнее новой цели/ограничения. | P1 ограничивает vendor/model instructions и проверяет clause-level claims; generic вопрос требует недостающий контекст. Смена темы и перенос ограничений в DialogueState остаются открытыми. |
| Срок договора с ОФД; затем уточнён сервис Платформа ОФД | После service clarification retrieval дал `no_context` / `unresolved_task_ambiguous`; в candidate list были approved документы Платформа ОФД, но ни один не выбран. LLM не вызывался. | Данные не подтверждают отсутствие approved-документа. Наблюдаемая точка отказа — resolver/retrieval operation ambiguity: договорный срок не сопоставился с операциями кандидатов (в том числе проверка передачи/регистрация/мониторинг). Это не validator и не LLM отказ. Более узкая причина требует отдельного trace сопоставления metadata/operation. | P1 создаёт общий gate, но не добавляет отсутствующую операцию «срок договора» и не расширяет понимание запроса. Повторить после semantic/task taxonomy этапа. |

### Runtime hashes

- Receipt существовал, но hash mismatch с подтверждённым P0 HEAD не позволяет верифицировать текущую версию worker. Для будущего ручного теста нужно перед тестом получать receipt, где commit и SHA-256 фактически загруженных исходников совпадают с запланированным snapshot; после запуска проверить polling/start отдельно.
- Не делать вывод о runtime версиях только из `HEAD` или факта наличия receipt.

## 5. Открытые проблемы и технический долг

| Приоритет | Проблема и основание | Состояние | Следующее действие |
|---|---|---|---|
| P1 | DialogueState lifecycle: stale task/clarification, потеря symptom и query root. | Исправлено в DialogueState v2.1, включённом в текущую публикацию; sequence tests и full suite проходят. Live Telegram не повторялся. | После публикации получить hash-bound worker receipt и провести ручные sequence tests. |
| P1 | Семантическое понимание «закончился ОФД», payment/renewal, outage vs list/connect. | Улучшено ограниченным lexical contract; экспериментальный Groq analyzer есть только в A/B CLI. В 2 коротких диалогах 4/7 ответов B не прошли исходную validation, плюс post-run audit выявил один inconsistent intent/object; непроверенные парафразы остаются риском. | Расширять independent paraphrase/state coverage; не подключать semantic analyzer к production до стабильного typed evidence contract. |
| P1 | Определить, стоит ли развивать semantic analyzer после A/B эксперимента. | Из 7 Groq ответов в двух последовательностях только 3 прошли проверку; 3 отбракованы из-за отсутствующего claim evidence / несовпадения entity evidence, 1 отклонён Groq Structured Outputs по object enum. Небольшая выборка не доказывает преимущество B; production подключения нет. | Разобрать сохранённые turn-level результаты; улучшать общий контракт/schema/prompt только на новых независимых примерах, затем повторить сравнение с telemetry токенов для каждого ответа. Не подключать к Telegram без отдельного решения. |
| P1 | Доказательство runtime-кода пяти ручных диалогов не совпадает по сохранённым hashes с HEAD P0. | Неразрешённая неопределённость артефакта. | До следующего Telegram-теста обеспечить hash-bound runtime receipt и сохранить source snapshot, не меняя данных клиента. |
| P1 | Coverage approved evidence по проверке срока/продлению/оплате Платформа ОФД. | Лексическая задача теперь определяет `billing/check` для явного запроса о сроке; retrieval coverage/content для этой узкой операции не подтверждались этим benchmark. | Отдельно проверить approved source metadata/evidence и offline retrieval cases; не считать исторический no_context доказательством отсутствия статьи. |
| P2 | 2 erroneous rejections в benchmark из baseline (`integration!=error_diagnosis`, `fns_registration!=receipt_transmission`). | Не являются новой регрессией P1; присутствовали до изменений. | Разбирать отдельно с ожидаемым намерением, не ослабляя hard mismatch gate. |
| P2 | В ходе P1 настройки временно выросли false rejections до 7 на 83 approved. Итоговый scope tuning убрал добавочные отказы. | Итоговый benchmark вернулся к baseline. | Повторять benchmark при изменениях operation/applicability; отслеживать абсолютные пары вопрос/отказ, а не только aggregate. |

## 6. Следующий этап

### DialogueState v2.1 — сделано локально; A/B стенд — экспериментальный и локальный

- `TaskContext` владеет исходной задачей, отдельным symptom, operation evidence/confidence и superseded facts; новые сообщения не меняют историю, а reducer обновляет только active task.
- `LexicalAnalyzer` отделяет объект, запрошенное действие и symptom; failure language больше не превращается в `list`. Явное действие и symptom остаются отдельными свидетельствами. Причинный вывод не создаётся.
- Подтверждение сервиса/оборудования/интеграции продолжает ожидаемую задачу и сохраняет её operation/symptom. `DirectBank` хранится как `integration`, не как service, чтобы не конфликтовать с metadata 1С.
- Явная смена темы создаёт новый `task_id`, очищает expected clarification и task facts старой задачи; сообщения остаются в ConversationStore. Новая тема распознаётся и после вводного «А теперь…».
- Повтор вопроса сохраняет текущие intent/operation и исходный запрос. Query builder включает root request по жизненному циклу задачи, редактируя superseded service/model/error/parameters и не смешивая разные задачи.
- Billing-парафразы без ясного действия остаются `unknown`/`analysis_required`; запрос «проверить срок договора» распознаёт `billing/check` и нормализуется отдельно от сверки контрагентов.
- Контракт `Observation` принимает типизированные relation, confidence и source spans; reducer проверяет spans текущего сообщения. Отдельный semantic analyzer реализован только в A/B CLI, не в production runtime.
- A/B CLI использует строгую schema из фактических vocabularies; post-validation проверяет типы, словари, intent-object пары, topic/relation согласованность, уникальные точные spans и привязку entity value к alias в span. Invalid B не заменяется результатом A и не меняет B state.
- `/new` начинает независимую пару диалогов; `/expect SLOT` моделирует ответ-уточнение бота для обоих state branches. A/B видят одну и ту же реплику и каждый свою копию ранее накопленного состояния; после расхождения их state не склеиваются.
- Прогнаны два заданных диалога (7 пользовательских сообщений): A распознал первый сбой как `bank_statement/diagnose` и сохранил операцию при уточнении DirectBank; реплика про банк Точка продолжила эту задачу. В billing диалоге A оставил неоднозначное «кончился ОФД» неразрешённым, затем на «закончился оплаченный период. Как продлить?» начал новую billing-задачу с `operation=unknown`; явная смена темы дала `access/add_employee`.
- B прошёл три реплики (третья в банковском диалоге, первая в billing, новая тема про сотрудника). На трёх других HTTP-ответах validation отклонил intent без evidence или entity claim с неподходящим evidence; один HTTP 400 возник, когда object не входил в enum. Ошибки не применены к состоянию; поэтому поздние state B сравниваются на его оставшемся/неполном контексте и не являются чистой оценкой семантического качества.
- Тест ресурса ФН в `tests/test_procedure_applicability.py` использует реальный approved-документ Платформа ОФД `platformaofd-lkk-cash-monitoring`, metadata `cash_list/list_cash_registers` и подтверждённый сервис; synthetic несовпадающую фикстуру заменили.

### Таблица переходов, проверенная в sequence tests

| Диалоговый ход | До | После | Проверенное свойство |
|---|---|---|---|
| Банковские выписки перестали загружаться | Новая задача | `bank_statement/diagnose`, symptom сохранён | Не превращается в `list` |
| Уточнение «1С, DirectBank» после вопроса о сервисе | `bank_statement/diagnose`, pending service | Тот же `task_id`, `diagnose`, software 1С + integration DirectBank, pending очищен | Не теряет исходную неисправность и не маршрутизирует на connect |
| Повтор исходного вопроса | Та же задача | Тот же смысл и тот же RAG query | Revision не сокращает root request |
| Право просмотра и запрет настроек | `access/add_employee`, pending service | Та же задача, service, цель и constraint | Уточнение сохраняет требования |
| Смена темы при pending clarification | Старая задача | Новый `task_id`, `expected=None` | Старый active task не попадает в новый query, transcript остаётся |
| Истёк договор/тариф или не проходит оплата | Billing неизвестного действия | `billing/unknown`, clarification-required | Не выбирает оплату/продление наугад |
| Проверить срок договора | Явная операция | `billing/check` | Не сводится к сверке контрагентов |
| Неопределённое изменение ФН | `fiscal_drive/change` | Запрос точного действия и оборудования до retrieval | Сохраняется P1-фискальный safety gate |

### Остаточные ограничения и следующий шаг

- `LexicalAnalyzer` остаётся ограниченным лексическим анализатором, не семантическим парсером. Новые парафразы, сложные вложенные задачи и случаи без явного relation требуют уточнения; возможный будущий analyzer должен реализовать typed `Observation`, confidence и evidence spans.
- Для неоднозначного срока договора и оплаты система безопасно уточняет цель; полнота approved knowledge/retrieval по этим операциям отдельно не подтверждалась.
- Полный pytest **287 passed**; retrieval benchmark по-прежнему **81/83**, без новых false rejections, и не запускался повторно в A/B задаче. A/B результаты — только 2 коротких диалога; B пока не заслуживает статуса победителя, но демонстрирует полезные hypotheses и нуждается в дальнейшем независимом тестировании после устранения ошибок evidence/schema. Production runtime не затронут.

Дальше: проанализировать `docs/experiments/dialogue_analyzer_ab_2026-10-23-final.jsonl`; расширить независимую выборку и зафиксировать scorecard для evidence validity, task linking, operation/symptom separation и state retention. После публикации подтвердить receipt на запущенной версии и провести ручной acceptance для v2.1. Semantic analyzer не включать в Telegram без отдельного разрешения.

### Ограничения текущей авторизации

Не менять Qdrant, production SQLite, `.env`, Telegram worker и пользовательские данные; не запускать индексацию или Groq; не добавлять правила под буквальные AB-ID/тестовые тексты; не реализовывать semantic LLM analyzer. Commit/push выполнять только по явному разрешению пользователя.

## 7. История работ

### 2026-10-23 — read-only диагностика 5 Telegram-сценариев и P1 safe evidence boundary

- **Цель:** определить причины пяти первых ручных Telegram-ошибок и сделать процедурный retrieval/evidence применимым к заявленному service/equipment/operation.
- **Изменения:** `app/procedure_policy.py` (новый), `app/retrieval_pipeline.py`, `app/answer_service.py`, `app/response_grounding.py`, `tests/test_procedure_applicability.py` (новый). Commit `a026dd2` в `main`; push подтверждён.
- **Причина:** fallback обходил operation mismatch; specialized документ становился универсальным; частичные clauses позволяли procedural claims; неопределённая фискальная задача могла получить опасную процедуру.
- **Проверки:** полный pytest на завершении P1 **269 passed**; targeted grounding/applicability набор **38 passed**; benchmark 83 approved: expected context **81/83**, те же 2 baseline rejections, новых нет; `git diff --check` passed. Retrieval benchmark выполнен без Groq и без записи/индексации Qdrant.
- **Ручные тесты:** только исторические пять диалогов прочитаны из `data/conversations.sqlite3` через SQLite URI `mode=ro` и `PRAGMA query_only=ON`; новые Telegram-сообщения не отправлялись. Установленные причины сведены в разделе 4. Runtime receipt/hash не доказывает точный source snapshot worker.
- **Регрессии:** первая настройка applicability создала 7 новых отказов на 83 approved; после сужения области применения итоговые проверки вернулись к baseline 81/83 без новых отказов. Оставшиеся 2 ошибочных отказа были и до P1.
- **Открыто:** DialogueState/semantic transitions; распознавание договора/срока ОФД; проверка runtime hash до следующего ручного теста; coverage approved evidence для срока договора.
- **Следующий шаг:** проверить P1 diff и спланировать отдельный узкий DialogueState этап; затем повторить offline проверки и ручной тест на точно аттестованной версии worker.


### 2026-10-23 — DialogueState v2.1 lifecycle, operation/symptom и stable query

- **Цель:** исправить жизненный цикл активной задачи, связь ответа с уточнением, сохранение симптомов/ограничений и стабильность RAG query; не внедрять LLM analyzer.
- **Установленные причины:** исходный request добавлялся только при общем `revision <= 1`, поэтому позднее уточнение теряло опорный запрос; `bank_statement` принудительно становился `list` от слова «выписка»; ролевой slot service мог принять техническое уточнение как новую операцию; operation vocabulary смешивала существительное/причастие с действием; в старом P1-тесте ресурса ФН были synthetic metadata.
- **Изменения:** `app/dialogue_state.py` (`TaskContext`, `Observation`, `LexicalAnalyzer.analyze`, `_failure_span`, `DialogueManager.advance`, `observe_answer`); `app/rag_query.py::build_rag_query`; `app/procedure_policy.py::query_operation_hints` и billing check normalization; `app/retrieval_pipeline.py::_state_task_category`; `app/answer_service.py` уточнение для неоднозначного billing lifecycle; `tests/test_dialogue_state_v21.py` (новые sequence tests); `tests/test_procedure_applicability.py` (реальный approved источник).
- **Принципы:** `TaskContext` остаётся единственным active-task state; session history не теряется; new task сбрасывает expected и task facts; clarification response дополняет task; явно подтверждённые операции не наследуются; object noun не объявляет operation; symptom имеет собственный evidence span; superseded facts удаляются только из retrieval root query, transcript остаётся неизменным.
- **Проверки:** targeted sequence/P0/P1 suites **143 passed**; полный pytest **278 passed**; финальный benchmark 100 вопросов/83 approved: selected/context **81/83**, те же две baseline rejection, новые false rejections **0**; top1=55, top5=74, top10=78, top30=83; сервисные ошибки 0; chunks order/index/link проблемы 0. `git diff --check` пройден после финальных изменений.
- **Эксперименты/регрессии:** промежуточный benchmark временно показал 79/83 и затем 77/83. Item-level разбор выявил ошибочный override явного `check` symptom detector, причастие `подключён` как `connect`, и техническое «сверить адрес/порт» как accounting reconcile. Корректировки operation/symptom separation и категории задачи вернули результат к 81/83; Q022/Q057 и сопутствующие cases повторно проверены. Итоговые новые false rejections отсутствуют.
- **Безопасность/среда:** Qdrant использован только для read-only retrieval; Groq и индексация не запускались; production SQLite, `.env`, worker и пользовательские данные не менялись. Benchmark/json/csv артефакты записаны в TEMP.
- **Открыто:** лексический analyzer ограничен и не понимает произвольную семантику; неоднозначный договор/платёж безопасно уточняется; ручной acceptance ещё не запускался на hash-bound worker receipt.
- **Следующий шаг на момент завершения v2.1:** review изменений, затем после пользовательского commit/push проверить runtime receipt и повторить ручные Telegram-последовательности. Эти изменения опубликованы в рамках последующего явного запроса пользователя.


### 2026-10-23 — Изолированный Dialogue Analyzer A/B стенд

- **Цель:** сравнить действующий `LexicalAnalyzer` + `DialogueManager` v2.1 с изолированным Groq `openai/gpt-oss-20b`, `reasoning_effort=medium`; не подключать эксперимент к production.
- **Изменения:** добавлены `scripts/compare_dialogue_analyzers.py`, `tests/test_compare_dialogue_analyzers.py`, sanitized результаты `docs/experiments/dialogue_analyzer_ab_2026-10-23-final.jsonl`. Скрипт поддерживает последовательные сообщения, `/new`, `/expect SLOT`, независимые состояния A/B, подробный console output и безопасную JSONL проекцию без исходных пользовательских текстов/evidence quotes.
- **Контракт B:** strict Groq JSON Schema строится из `OBJECTS`, `OPERATIONS`, `RELATIONS`, `ENTITY_NAMES`; код валидирует точные уникальные spans, типы, vocabulary, intent-object coherence, relation/new-topic consistency и подтверждение entity alias. Ошибка не заменяется A и не редуцируется в B state. Groq structured outputs поддерживают strict schema для GPT-OSS 20B согласно [документации Groq Structured Outputs](https://console.groq.com/docs/structured-outputs); модель принимает `reasoning_effort=medium`.
- **Результат заданных sequence cases:** 7 пользовательских реплик, 7 вызовов B. Три прошли исходную validation: tokens `2890`, `2919`, `2648` (итого **8457**). Три HTTP-200 ответа отклонены локальной проверкой: в двух intent claim не имел evidence, в одном entity value не подтверждалось его quote. Один HTTP 400 от строгой schema: сгенерированный object не был в enum. На отклонённых ответах первоначальный runner не перенёс provider usage в сохранённую строку; исправлена обработка для будущих запусков, прошлые числа не восстанавливались. Запрос с HTTP 400 usage не сообщил. Кроме семи вызовов финального прогона, выполнены 10 предварительных/отладочных запросов; всего за задачу 17, известное usage receipts суммарно 16,649 tokens.
- **Сравнение A/B:** A в первом диалоге установил `bank_statement/diagnose`, service clarification не сменил операцию; фраза о банке Точка сохранила task/operation/symptom, но relation стал `unknown` и `analysis_required=true`. В OFD диалоге A не распознал intent/operation для «кончился ОФД» (`analysis_required=false`); «Платформа ОФД» принято как clarification/route, но intent/operation остались unknown; явная оплаченная-периодная реплика создала `billing/unknown`, `analysis_required=true`. Новая тема стала `access/add_employee`. B отработал три реплики без исходной schema/span ошибки: первая banking follow-up закончилась unknown state; OFD first turn unknown + symptom; новая тема выбрана как `general/add_employee`. Ещё три HTTP-200 ответа были отвергнуты (2×intent claim без evidence, 1×entity-value/evidence mismatch), один HTTP 400 — generated object вне enum; при ошибках state B оставался прежним. Post-run cross-field audit обнаружил, что `general/add_employee` с object `сотрудник` не соответствует intent-object vocabulary; текущая validation теперь отвергает такую комбинацию. Поэтому из трёх первоначально прошедших результатов только два согласуются с последним cross-field gate; это exploratory evidence, не победа B.
- **Проверки:** `python -m py_compile scripts/compare_dialogue_analyzers.py`; полный `python -m pytest -q`: **288 passed**; `git diff --check` прошёл с существующими предупреждениями line endings в двух P1-файлах. Groq: ровно 7 вызовов финального прогона; Qdrant, базы, индексация и Telegram worker не использовались. Cross-field intent/object guard и evidence validation оборудования добавлены после сохранённого прогона и покрыты локальными unit tests; сам A/B run после них не повторялся.
- **Ограничения/вывод:** B показал, что строгая schema и span validation выявляют неподкреплённые claims, но текущий prompt/model не проходят 4 из 7 реплик. Следует тестировать на новой независимой выборке и улучшать общий evidence контракт; не подключать B в production и не объявлять его точнее на 2 коротких диалогах. A/B branches diverged after validation errors, что явно отмечено в сохранённом turn-level отчёте.
- **Открыто/следующий шаг:** решить по scorecard, какие общие schema/prompt улучшения дают пользу; повторить небольшой A/B run с учётом usage всех ответов. На момент этой записи изменения были локальными; они включены в последующую публикацию по явному запросу пользователя.
