# Support-RAG-Bot — пошаговый план реализации и проверки AI-помощника

**Версия:** 0.3 · 26 октября 2026 г. · обновлено по трём параллельным результатам A/C/D и проверке опубликованных GitHub-веток.

**Статус:** D2, handoff, evidence eligibility, frozen retrieval audit и Stage 4B B+ route/applicability repair проверены офлайн. Интеграция fast-forward merged в `main` на `5a8f9929fced459a6dbbc13c386d2bd74b70b687`; Stage 4 live quality остаётся NO-GO, B2 default-off, worker unchanged, production NO-GO. B+ exact saved-Understanding replay через `bot.handle_message` + temporary SQLite завершён; full pytest **454 passed, 4 xfailed, 13 warnings**. Подтверждённые applicability и safety gates сохранены. Live следующий gate только предложен, вызовы не выполнялись. Не команда выполнять все этапы сразу. `docs/RAG_MASTER_PLAN.md` остаётся **единственным каноническим планом репозитория**. Этот файл — операционная детализация. Старый `experiments/architecture_recovery_audit/implementation_plan.md` существует как историческая последовательная программа; его этапы не являются отдельной дорожной картой и синхронизированы ссылкой на это продолжение. После согласования Codex вносит в master только изменения статусов и ссылки, не создавая конкурирующую дорожную карту.

## 1. Продуктовая цель

Бот поддержки на русском языке по ОФД, ККТ, Эвотор, АТОЛ, aQsi, ФН, маркировке, 1С и смежным вопросам должен:

- естественно отвечать на приветствие, благодарность и завершение разговора;
- понимать цель клиента и сохранять контекст обращения через SQLite restart;
- объяснять факты на основании подтверждённых документов;
- помогать пошагово: выбирать следующий **применимый** шаг и помнить результаты уже выполненных проверок;
- по прямому запросу или при невозможности безопасно помочь **действительно доставлять** обращение в утверждённый канал специалиста, не притворяясь, что доставка состоялась;
- не выдумывать технические меню, роли, правовые требования и фискальные действия.

Целевой контрольный диалог: «Привет» → «Закончился ОФД, как продлить?» → уточнение оператора → подтверждённая инструкция → «Оплатил, но не работает» → новая проверка → «Позови специалиста» → реальное уведомление сотрудника с минимальным контекстом.

## 2. Целевая архитектура B+ (решение по направлению, не доказанная реализация)

```text
Пользователь + история
    ↓
Groq Understanding (что означает реплика, связь с задачей, exact spans клиента)
    ↓
Reducer + Coordinator (подтверждённые факты, риск и допустимый маршрут)
    ├─ conversation → приветствие / благодарность / завершение без RAG
    ├─ handoff → заявка оператору, проверенный статус доставки
    └─ grounded_information / technical_action
          ↓
       Qdrant Dense + BM25 + RRF → применимые approved-документы
          ↓
       Groq Evidence Decision [экспериментальный B2]
       → ID фактов/неделимых шагов, либо clarify / no_evidence
          ↓
       Независимые проверки approved/SHA/scope/предусловий/safety
          ↓
       Код воспроизводит разрешённые единицы из документов и условия
          ↓
       Ответ / нужное уточнение / handoff
          ↓
       ProgressLedger хранит показанные проверки и результаты клиента
```

**Модель предлагает; код решает, что разрешено.** `ConversationStore`, `DialogueState` и reducer владеют подтверждёнными фактами. Бот не получает разрешение исполнять произвольные инструменты или генерировать новые технические утверждения вне evidence.

Сохраняем имеющиеся SQLite, hybrid retrieval, Qdrant, KB, approved/SHA, safety, трассы, Telegram, старый Source-first A и lexical B1 под флагами. Ничего не удаляем до сравнительных проверок. Два LLM-вызова на предметный ход (Understanding + Decision) — **цель по упрощению**, не гарантия; технические и аварийные ветки измеряются отдельно.

## 3. Факты и текущее состояние на 26.10.2026

- Первичная реализация Coordinator D1 существует за `AI_COORDINATOR_ENABLED` (по умолчанию off). Он пока маршрутизирует детерминированно на основании validated Groq Understanding и reducer state, но не ведёт полноценную пошаговую диагностику.
- D1 offline: ранее `404 passed, 6 xfailed`. Это не подтверждение полезности. Первый настоящий D1 Groq/Qdrant: **2 Groq calls, 3572 tokens, 1/2 полезных ответов**, safety PASS; lexical `_focused_approved_sentence` выбрал договор/тариф вместо функции ОФД.
- Qdrant Stage3 после восстановления остановленного Docker-контейнера: `knowledge_stage3_retrieval_20261022`, **934 points**, **672 approved points / 206 approved документов**; всего **269 Markdown-документов**, из них 63 draft по последнему аудиту. Read-only hash/scope сверка approved прошла. Эти цифры не доказывают покрытие реальных вопросов.
- Экспериментальный Semantic ID Selector B2 добавлен за `SEMANTIC_EVIDENCE_SELECTOR_ENABLED` (по умолчанию off), не развёрнут на Telegram. Первый A/B: **8 Groq attempts / 4 retrieval turns**, завершились лишь **2/4 Decision**; в этих двух парах B2 полезен 2/2, B1 — 1/2; остальных ответов не было из-за `GenerationError` и HTTP 429. Этот результат — исторический baseline, не победа B2.
- **A, диагностическое продолжение завершено (2026-10-26):** дополнительные **4 Groq Decision attempts** на сохранённых Understanding/evidence; 3/4 вернули ответ, 1/4 HTTP 429 `rate_limit_exceeded`, Retry-After 12 сек.; повторов не было. D1.2, D1.3, D3.2 полезны по основному смыслу, но D1.3 включает лишний вопросный фрагмент из approved FAQ; D3.1 заблокирован 429, не оценён. Известные tokens: **7 129 prompt + 941 completion = 8 070** для трёх ответов, usage ошибки неизвестен. Полный suite на `main`: **420 passed, 6 xfailed, 13 warnings**. **B2 по-прежнему NO-GO, флаг выключен.** Дальше нужны universal evidence eligibility (заголовки/вопросы ≠ ответ) и новый честный holdout; не бесконечные повторные DEV-вызовы.
- **C, read-only retrieval-аудит завершён:** 54 обезличенные реальные реплики / 45 уникальных; gold: 35 с approved answer-bearing документом, 19 без доступного approved evidence. Все 35 gold-документов присутствовали в raw top-100. Recall@5: raw hybrid 80,0%, действующие фильтры 88,6%, теневой soft-ranking 97,1%; на Recall@1 мягкий вариант хуже действующего (68,6% против 74,3%). Действующие task/operation отсекли **4 верных документа**. ФН 234/235 различаются правильно на rank 1; 999 не даёт approved ответа. Массовые изменения retrieval/KB пока **не разрешены**. Отчёт находится вне Git checkout: `C:\Users\Shira.codex\experiments\support-rag-retrieval-audit-20261026\` — необходимо безопасно скопировать обезличенные артефакты в репозиторий/приложить к плану.
- **D, handoff MVP завершён только offline** в отдельном `codex/support-rag-handoff-mvp`: реальный транспорт Telegram реализован, но **`HANDOFF_ENABLED` default off**, реального чата и отправок нет. 16 targeted tests passed. Полный suite в worktree: 413 passed / 6 xfailed / 2 failed из-за отсутствующих локальных fixture и optional `langgraph` — нужны проверки в одинаковом окружении, а не вывод о функциональной регрессии. Handoff не слит с `main`; реальное уведомление сотрудников остаётся **NO-GO**. Sidecar `.local/handoff_outbox.json` хранит payload: до включения нужна отдельная проверка минимизации PII, прав доступа и срока хранения.
- Исторический старый Source-first ответил на двухходовый D1 через 9 Groq calls / 13 352 tokens; этот старый запуск — ориентир, не синхронное сравнение.
- **Проверено в GitHub:** `main` на **`54ea1b9`** (селектор: `5f80bab`), отдельная handoff-ветка на **`f257ab5`** (MVP: `6ed4015`). Оба набора Git-изменений опубликованы по отчёту пользователя; публикация ветки не означает merge/deploy. Реальный runtime, локальный Qdrant и приватные трассы по GitHub не проверяются. При новом задании всегда проверять локальное дерево до редактирования.


### 3.1. Три параллельных трека — итог и статус решения (26.10.2026)

| Трек | Что подтверждено | Что **не** подтверждено | Статус / следующий шаг |
|---|---|---|---|
| **A: Semantic Selector** | 420 passed / 6 xfailed на main, валидные ID/порядок и защитные проверки; на 3 успешных Decision есть полезный смысл | Одна из 4 попыток заблокирована 429; D1.3 содержит question-only unit; выборка мала и не независимый holdout; нет полноценного production E2E | **OFFLINE implementation DONE; product GO = NO**. Feature flag off. После B — ограниченный общий E2E на новых holdout, только если исправлена eligibility. |
| **C: Retrieval** | 54 реальных реплики, 35 answerable gold, 19 no-evidence; 4 источника теряются фильтрами; code 234/235 различается | Нет доказательства, что soft-ranking целиком лучше: Recall@1 снижается, selection section может ухудшиться; нет репрезентативного покрытия всех тем | **READ-ONLY AUDIT DONE; tuning не начат**. Перенести внепроектные безопасные artifacts, спланировать парный scope-aware rerank эксперимент после B. |
| **D: Handoff** | Branch MVP, fake transport, проверка confirmed receipt, pending/delivered/failed, 16 passed | Реальный staff-chat и доставку не тестировали, branch не слита, старый контур main не имеет этих возможностей; 2 environment-specific failures в чистом worktree | **BRANCH MVP DONE; merge/live = NO-GO**. Интеграционный review и полный suite на одинаковой среде, затем одобрение чата и отдельный разрешённый send. |

### 3.2. Важные методологические замечания

1. Сохранённые `p1_semantic_selector_holdout_cassettes_20261026.json` включают известные D1.3 и D3.2: они названы HOLDOUT в диагностическом эксперименте, но **не являются новым независимым holdout относительно истории разработки**. Для честной product-приёмки создать новый blind набор из неиспользованных реальных/специально написанных независимых вопросов; сначала запечатать условия и рубрику, потом запускать. Не называть `3/3` полным успехом при `3/4` завершённых Decision.
2. Retrieval-метрики по 35 answerable кейсам — **набор аудита**, а не показатель всего покрытия клиентов. `19 no_approved_evidence` не означает, что 35% всех клиентских вопросов не имеют ответа. Не использовать gold-набор C одновременно и как DEV для тюнинга, и как финальный HOLDOUT.
3. API 429, schema error, отсутствующее evidence, нерелевантный ответ и неподтверждённое опасное действие — **разные классы отказа**. Успех ценой отклонения по safety неприемлем; provider availability нельзя подменять quality.
4. Handoff основан на `b99348a`, а main уже ушёл до `54ea1b9`. Не fast-forward объявлением и не заменять `docs/RAG_MASTER_PLAN.md` файлом из старой ветки: требуется review/cherry-pick/merge с сохранением обеих историй.
5. Три параллельных результата ещё **не образуют совместную рабочую сборку**. Не включать handoff и B2 в worker, пока нет интеграционных E2E и явного разрешения.

## 4. Незыблемые принципы тестирования

1. Разделить наборы: **DEV** (D1, D2, D3 и известные провалы) — для отладки; **HOLDOUT** (новые независимые вопросы из разных сервисов) — для приёмки. Holdout не использовать для выбора промпта и параметров. Если после оценки кейс подробно изучили и использовали для исправления, перенести его в DEV и заменить свежим holdout.
2. «Содержание совпадает с approved источником» и «ответил на текущий вопрос» — **разные оценки**. Два разных текста не обязательны: один точный факт может отвечать на два вопроса. Но повтор, не раскрывающий новую подцель, — UX-дефект. **Основной критерий**: выбрать одну или несколько совместимых единиц, дающих *достаточный* ответ; обязательные условия, предупреждения и последовательность не терять.
3. Для необходимого уточнения обязателен **конкретный недостающий слот**, без которого нельзя безопасно продолжить, и вопрос не должен повторяться без новых фактов. Полезные ответы, обоснованные уточнения, тупики и ненужные эскалации считать **раздельно**. Никакой общий процент без знаменателей и доверительной неопределённости не объявлять качеством продукта.
4. Любая неподтверждённая опасная инструкция — немедленный safety FAIL вне зависимости от общей полезности. Сервис/модель/код ошибки не подменяются и не угадываются.
5. В каждом bounded live запуске учитывать provider attempts, реально завершившиеся calls, provider HTTP status, response latency, strict-schema ошибки (`json_validate_failed`), 429/timeout, `Retry-After`, prompt/completion tokens и неизвестный usage при ошибке. **BLOCKED / PROVIDER ERROR / QUALITY FAIL / SAFETY FAIL** разделять. Без неограниченных retry и скрытых сетевых вызовов.
6. Cassettes записываются из обезличенных настоящих Groq результатов и фиксированных evidence с hash промпта/модели/кода; они позволяют повторять тесты без затрат. Ручная оценка нужна сверх автоматических тестов. Нельзя объявлять PASS на основе удачных подмножеств при ошибках остальных.
7. Параллельный Codex — **только при изоляции рабочих деревьев**, с независимыми путями артефактов и без одновременного редактирования одних модулей/`RAG_MASTER_PLAN.md`. Работу в одном грязном дереве вести последовательно.

## 5. Рабочие треки и очередность

### A. Семантический выбор evidence [ЭКСПЕРИМЕНТ ВЫПОЛНЕН, B2 NO-GO]

**Сделано:** ID-only selector за выключенным флагом; проверка SHA/approved/safety; сохранение порядка нескольких ID; детальная диагностика HTTP/status/429; полный pytest 420 passed / 6 xfailed на `main`; 3 содержательно полезных ответа из 4 Decision attempts в диагностическом прогоне. На D1.3 LLM выбрала и factual evidence, и соседний FAQ-вопрос: происхождение source подтверждено, но вопрос не является answer-bearing unit. D3.1 остался без ответа из-за 429.

**Offline eligibility correction (2026-10-26):** универсально отсекаются question/header units; context labels нельзя выбрать без answer-bearing fact; Source-first lexical путь использует ту же eligibility; целый procedural block сохраняет порядок/предупреждения. Frozen D1.3 replay подтверждает механизм исправления, но не считается независимым holdout. См. [отчёт](../experiments/architecture_recovery_audit/p1_semantic_eligibility_20261026.md). B2 остаётся OFF/NO-GO.

**Следующий A-шаг не раньше согласованного общего E2E после B:**

1. Ввести общую eligibility-модель единиц источника: `question/header/context` не могут сами быть ответом, `fact` и целый procedural block проходят применимость, предусловия и safety. Это не частное правило под ОФД.
2. Ретестировать DEV/cassettes, затем **новый** blind HOLDOUT; существующие D1/D3 cassettes служат regression/DEV, даже если файл называется `holdout`.
3. Проверить semantic relevance и полноту одного/нескольких выбранных единиц, а не требовать искусственно разные строки в последовательных ответах.
4. В bounded live тестах разделить ошибки Groq (429/schema/timeout), semantic quality, retrieval и safety; считать все attempted cases, а не только successful subset. Включать B2 в worker **только после доказанного выигрыша** над A и отдельного разрешения.

### B. ProgressLedger и завершение диалога [СЕЙЧАС; ОСНОВНОЙ КОДЕКС, ТОЛЬКО OFFLINE]

В существующем `TaskContext` под управлением reducer: `procedure_id`, `shown_units`, `checks: {unit_id, status: asked|passed|failed|unknown|not_done, result_span}`, `open_question`, `current_subgoal`, счётчик повторов по слоту. Только exact-span клиента переводит проверку в `passed/failed/unknown`; ответ бота не подтверждает выполнение действия.

Технический сценарий D2: «Эвотор, чеки не отправляются» → «Интернет работает» → «Оплату проверил» → «Что дальше?». Шаги берутся лишь из approved evidence с проверенными предусловиями, не из выдуманного дерева. Не повторять выполненный шаг; для model-specific инструкций спрашивать модель. Закрытие: «Спасибо, всё решено» → короткое завершение задачи, **не** повторная диагностика и не «что осталось нерешённым?». Проверить отдельный `closing/resolved` turn type или эквивалентную подтверждаемую семантику без специальных regex на фразы.

**Тесты:** SQLite close/reopen и legacy state, продолжение/смена задачи, unknown, отрицание, противоречие, смена сервиса, отказ от проверки, repeated clarification, UI/safety, ограниченный Groq understanding с замороженным набором и позднее bounded live после offline. Изменения `dialogue_state.py`, `dialogue_understanding.py`, `source_first_service.py` не совмещать в одном дереве с A.

### C. Retrieval audit [ЗАВЕРШЁН; ДОРАБОТКА ПО РЕЗУЛЬТАТАМ ПОЗЖЕ]

Read-only Stage3 аудит выполнен на **54 реальных обезличенных репликах (45 уникальных)**. Gold-разметка: **35 с approved answer-bearing источником**, 19 `no_approved_evidence`. Из 35 все присутствуют в raw top-100. Значения Recall по gold answerable:

| Режим | Recall@1 | Recall@3 | Recall@5 |
|---|---:|---:|---:|
| Raw hybrid + approved/identifier guards | 45,7% | 77,1% | 80,0% |
| Текущие hard filters | **74,3%** | 85,7% | 88,6% |
| Аналитический soft-ranking | 68,6% | **94,3%** | **97,1%** |

**Причины:** четыре верных документа исключены `task_category`/`operation` filters, в том числе ложное `connect` вместо операций загрузки/просмотра выписок 1С. Soft-ranking возвращает их в top-5, но ухудшает Recall@1 и некоторые выборы конкретного раздела. Контрольные FN 234/235 разделяются верно на rank 1; неподдержанный 999 не дал approved документа. **Решение: аудит DONE, никаких изменений retrieval по одним этим цифрам.**

**Следующее:** перенести и безопасно закрепить зафиксированные артефакты из внешнего каталога; на 4 потерянных источниках построить минимальный парный эксперимент hard/soft с контролем ranking и scope, не ослаблять approved, явные сервисно-модельные противоречия, точные коды и safety. Отдельная оценка покрытия KB по реальному трафику — трек E.

### D. Handoff MVP [РЕАЛИЗОВАН В ОТДЕЛЬНОЙ ВЕТКЕ; ЕЩЁ НЕ ИНТЕГРИРОВАН]

Без LLM: существующая заявка + минимальный адаптер транспорта для **заранее утверждённого** Telegram-чата операторов, пакет контекста (task ID, подтверждённые факты, shown_units/check results, причина, краткая обезличенная сводка). Idempotency при двойном клике, ошибки канала, статусы `pending/delivered/failed`, и запрет говорить «доставлено», если Telegram API не подтвердил. Явная просьба пользователя о человеке не должна зависеть от качества RAG.

Это уже реализовано в отдельной ветке и проверено с **fake transport (16 passed)**. Пока ID целевого чата/согласованный канал не получены, `HANDOFF_ENABLED` остаётся выключенным. Не было реальных отправок, изменения рабочего worker и согласования обработки клиентских данных. Существующая CRM-интеграция и подтверждение сотрудником — позднее. Следующее техническое решение: ревью/интеграция ветки на свежий main и выравнивание тестового окружения; реальная отправка — отдельное разрешение.

### E. KB coverage [ПАРАЛЛЕЛЬНЫЙ АНАЛИТИЧЕСКИЙ ТРЕК]

50–100 обезличенных реальных обращений или независимо составленных типовых вопросов (не генерировать тесты только по тексту KB). Каждый кейс: `fully_answerable / partially_answerable / no_approved_evidence / wrong_retrieval / wrong_answer_selection`, gold refs и приоритет темы. Найти кластеры нехватки знаний в ФН, маркировке и иных направлениях. Не редактировать 269 документов до результатов анализа. Не путать недостаток знаний с retrieval/selection bug.

### F. Сопоставимый E2E quality/safety gate [ПОСЛЕ ОСНОВНЫХ ВЕРТИКАЛЕЙ]

A/B на одинаковых версиях KB и source SHA, с одинаковым состоянием и вопросами. DEV отдельно от независимого HOLDOUT. Применять 0 safety breaches, качественные ручные метки relevance/answer completeness/progress/necessary clarifications; отдельно provider availability/schema errors, latency, Groq calls/tokens и стоимость. Предварительные **70% useful + necessary clarification** допустимы только при явном раздельном подсчёте и знаменателе; критерий допуска — **парное улучшение над A без потери safety**, а не одна доля на малом наборе. Интеграция реальной Groq и read-only Qdrant обязательна, но ограничена утверждёнными бюджетами.

### G. Telegram allowlist pilot [ПОСЛЕ GO ПО СРАВНИМЫМ GATES]

Перед ручными сообщениями: `git HEAD` + статус незакоммиченных файлов; снимок рабочих SHA; `RAG_ENGINE=source_first`, `AI_COORDINATOR_ENABLED=1`, выбранный и проверенный `SEMANTIC_EVIDENCE_SELECTOR_ENABLED` (не включать B2 без GO), Groq model/reasoning, `QDRANT_COLLECTION=knowledge_stage3_retrieval_20261022` после read-only verification, allowlist count/hash, runtime receipt, единственность worker, реальный PID/start time/cmdline. **Нельзя останавливать PID из устаревшего receipt наугад**: прежний 46544 мог принадлежать AMD. Сохранить rollback. Только после подтверждения загруженного кода тестер начинает ручные диалоги. Сразу при unsafe final output stop и rollback. Не выдавать ограниченный пилот за production release.

### H. Упрощение и стоимость [ПОЗЖЕ]

Только по измеренному качеству убрать дубли Planner/Composer/Repair/Judge/validator и повторные scope passes; сравнить дополнительный Groq Decision с прошлым 9-call path. Отдельно оценить объединение Understanding + Decision (ablation). Измерять schema-failure, HTTP 429/5xx, p50/p95 latency, calls/tokens per turn и handoff success. Не менять MiniLM, embeddings/reindex, модель или KB массово без отдельной метрики и эксперимента.

## 6. Организация параллельной работы без конфликтов

| Трек | Режим | Общие файлы/конфликты | Можно одновременно |
|---|---|---|---|
| A: selector reliability | Завершённый диагностический эксперимент; code flag off | `source_first_service.py`, runner, флаги, master docs | Да, с C; не с B в том же дереве |
| B: ProgressLedger | Отдельный следующий рабочий этап | `dialogue_state.py`, `dialogue_understanding.py`, `source_first_service.py`, `bot.py` | Только изолированный worktree или после A |
| C: retrieval audit | Завершён read-only; отчёт вне Git | Код не меняет, Qdrant только читает | Да, сразу |
| D: handoff MVP | Код в отдельной ветке; ожидает review/merge | `bot.py`, `conversation_store.py` | Да, при worktree и без live send |
| E: coverage | Аналитика / документы без редактирования KB | Нужны обезличенные кейсы | Да, если данные доступны |

**Интеграция:** после A/B каждого трека — тесты на своей ветке. Объединяет изменения один ответственный последовательно с full suite и документацией. Ни одной параллельной задачи, пишущей в одни и те же рабочие файлы, и никаких параллельных `git push` или изменений `docs/RAG_MASTER_PLAN.md`.

## 7. Порядок ближайших решений и критерии остановки — актуально после A/C/D

**Решение 2026-10-26:** три параллельных задачи завершили свои **ограниченные области**, но не создали готовую production систему. Нельзя воспринимать опубликованную handoff-ветку как внедрённую в `main`; нельзя считать B2 принятым, потому что 3/4 provider attempts дали полезный текст. Переходим к следующему доказуемому продуктовым поведением шагу.

### Шаг 1 — B / ProgressLedger OFFLINE — DONE (2026-10-26)

- `main` на опубликованном SHA, чистота и актуальность локальных файлов до изменений. Не трогать branch handoff.
- Новый reducer-owned журнал `shown_units`, проверок (asked/passed/failed/unknown/not_done) с client exact-spans; только проверенные факты из сообщений; SQLite backwards-compatible, reopen/restart.
- Многоходовые технические примеры D2 Эвотор и продление ОФД; одна подтверждённая следующая проверка, а не повторная уже выполненная; точная применимость по model/service.
- «Спасибо, всё решено» закрывает задачу без повторной диагностики; новый технический вопрос после закрытия открывает новую задачу; явная просьба специалиста не зависит от LLM.
- Сначала офлайн E2E и negative gates, полный suite. **Никаких новых живых Groq/Telegram вызовов в этом этапе, без отдельного разрешения.**
- **Результат:** SQLite-backed OLD vs LEDGER E2E, [report](../experiments/architecture_recovery_audit/p1_progress_ledger_20261026.md) и [trace](../experiments/architecture_recovery_audit/p1_progress_ledger_trace_20261026.json). Полный suite 428 passed / 5 xfailed / 13 warnings. «Оплату проверил» = `unknown`, отдельное «Оплата прошла» = `passed`; инструкция бота не считается выполнением. **Offline DONE; live BLOCKED (не запускался); production NO-GO.** Published Git SHA: `4cdc21f5fb8699a937981e19695705e510de4933`.

### Шаг 2 — D / Handoff integration readiness — OFFLINE DONE, fast-forward merged

- От `main` SHA `a606121f518cc5ffd1d3d3a0e860799df8ae2c49` создан отдельный worktree/ветка `codex/support-rag-handoff-integration`; источник MVP — `origin/codex/support-rag-handoff-mvp` SHA `f257ab56697cf98d73da8a74889bf4bce2272d8d`, реализация `6ed4015edbf33dc43948ee9aa474bb9075bde604`.
- Handoff интегрирован с ProgressLedger через read-only snapshot provider, проверяющий conversation/task boundary и возвращающий только procedure/check label/status/client quote. Существующие SQLite tables и schemas не менялись; актуальные master/state/v0.3 взяты с `main`, старые handoff docs не подменяли их.
- Fake transport подтверждает receipt/destination; direct specialist request проходит до LLM; duplicate confirmation не повторяет доставку; failed delivery требует явного retry; без одобренного chat ID transport не вызывается. Payload очищает email/телефоны из summary/facts/messages/progress, не содержит user/chat/conversation IDs; checks ограничены активной задачей.
- Контрактная перепроверка D2: обнаружено, что shortcut `progress_ledger_next_approved_check` выбирал первый непоказанный пункт раздела без проверки scope этого пункта. Прежняя combined test-последовательность уже содержала явное «Модель Эвотор 5i», поэтому не доказывала unknown-model поведение. Добавлены generic model-scope gate и applicability matching; неподдерживаемая модель блокируется, смена модели меняет scoped unit identity, старые результаты не применяются к новому оборудованию. Общий missing-model/safety gate сохранён.
- Combined E2E через реальный `bot.handle_message` + временную SQLite + fake transport: Эвотор → интернет (`passed`) → оплата (`passed`) → «Что дальше?» при неизвестной модели (инструкция скрыта, вопрос задан один раз) → повтор без зацикливания → подтверждение «Эвотор 5i» → exact applicable пункт 2. SQLite close/reopen проверяется между ходами; также проверены неподдерживаемый `X500` и переключение `5i → X500`, после которого пункт больше не выдаётся. Direct request без Groq, fake delivery/repeat, topic change и closure проходят.
- Проверки после исправления среды: targeted bot/handoff suite **42 passed, 5 xfailed**; полный suite **443 passed, 5 xfailed, 0 failed** на Python 3.12.2 из основного checkout, с ignored fixture через временный junction (без копирования/чтения содержимого) и `langgraph` из временной изолированной dependency directory. Предыдущие два failures — environment-only; в сопоставимом окружении не воспроизводятся. `git diff --check` и `py_compile` — passed. D2.3 strict xfail оставлен; S2 safety gate перепроверен после того, как промежуточное сужение model gate ошибочно пропустило ответ.
- Privacy/safety follow-up: обязательная независимая сверка `TELEGRAM_SPECIALIST_CHAT_ID == HANDOFF_APPROVED_CHAT_ID` перед transport; mismatch блокирует вызов. Sidecar хранит sanitized payload для `pending`/`delivered`, receipt для `delivered`, только код ошибки для `failed`; process restart не запускает автоматическую отправку. Ticket ID включает request id и hash conversation/task binding. Контакты email/phone маскируются; сообщения новой/иной задачи отсекаются по reducer task ID. Произвольные имена/адреса не проходят универсальную деидентификацию — сохранять только нужную задаче информацию и не включать live до отдельного review retention/access.
- **Статус решения:** offline integration DONE; live BLOCKED/not run; production NO-GO. Commit `5a8f9929fced459a6dbbc13c386d2bd74b70b687` опубликован в `origin/codex/support-rag-handoff-integration` и fast-forward merged в локальный `main`; push `origin/main` выполняется после синхронизации итоговых документов. Техническая готовность к отдельному commit/push review: **GO**; offline merge-candidate readiness после scope review: **GO**; пользователь явно разрешил Stage 1 commit/push/merge при выполнении safety и regression gates; merge выполнен fast-forward. Telegram `sendMessage` не имеет server-side idempotency key: после timeout результат неоднозначен; `pending`/`failed` требует ручной сверки с сотрудниками по ticket ID до явного retry. Sidecar рассчитан на один процесс; retention/permissions и согласованный чат остаются live gate. Подробности и trace: [integration report](../experiments/architecture_recovery_audit/p1_handoff_integration_20261026.md).

### Шаг 3 — frozen retrieval audit C (DONE в заданной области)

- Внешний audit C скопирован в [`experiments/retrieval_audit_20261026/`](../experiments/retrieval_audit_20261026/) после проверки на PII/secrets. Сохранены исходные gold labels, baseline hashes и все материалы; повторного широкого аудита не было.
- Набор: 54 retrieval-eligible turns, 45 distinct exact questions, 35 approved answerable golds, 19 no-evidence; все gold документы есть в raw top-100. Четыре approved gold исключены task/operation filters: m0113 `receipt_search != cash_search`; m0119/m0121 operation `connect`; m0125 `tspiot != model_features`.
- Current hard baseline doc Recall@1/3/5: 74.3/85.7/88.6%; gold-section hit@1/3/5: 45.7/68.6/77.1%. Существующий soft shadow: document 68.6/94.3/97.1%; section 51.4/65.7/65.7%. Повышение глубокой document recall сопровождается потерей rank-1 и section hits @3/@5; soft ranking остаётся analysis-only/NO-GO для production. Task/operation filters не менялись. См. [Stage 3 report](../experiments/architecture_recovery_audit/p1_retrieval_shadow_ranking_20261026.md).

### Шаг 4 — bounded live quality gate (NO-GO после первого batch)

- Замороженная рубрика и новый holdout сохранены в [rubric](../experiments/architecture_recovery_audit/p1_unified_live_gate_rubric_20261026.md). Stage3 `knowledge_stage3_retrieval_20261022`: green, 934 points, read-only facade. `.env` не менялся; Stage3 collection выбрана временным process override.
- Первый batch остановлен на 4/12 Groq HTTP attempts, 2 retrieval turns; automatic retry = 0. Первый OFD Evidence Decision выбрал валидный approved ID/SHA, но трехфразовый/325-character unit был отвергнут лимитом informational renderer; полезный lexical comparator показывает, что источник содержит ответ. Следующий ход продолжил задачу, retrieval прошёл, Evidence Decision получил HTTP 429 (Retry-After 3s). Provider usage: 4,169 prompt + 2,296 completion tokens. До offline unitization fix: full suite **449 passed, 5 xfailed** (Python 3.12.2); после fix полный suite **450 passed, 5 xfailed**, `py_compile`/`git diff --check`/privacy scan passed. Overall live gate **NO-GO**; незаконченные сценарии остаются BLOCKED. После batch offline исправлена общая unitization: informational mode выдаёт sentence IDs для фактов/ограничений, исключает procedure/interface из информационных единиц; technical procedure blocks остаются цельными. Targeted 19 passed, полный suite после fix **450 passed, 5 xfailed**. Старую трассу не переигрывали; live quality не доказано, новый holdout batch нужно отдельно ограничить после снятия rate limit. Полный [отчёт](../experiments/architecture_recovery_audit/p1_unified_live_gate_20261026.md) и [трасса](../experiments/architecture_recovery_audit/p1_unified_live_gate_20261026.json).
- Offline fix выполнен: answer-bearing informational sentence IDs при сохранении ordered procedure blocks и всех approved/SHA/scope/claim/safety/length gates. Повторный live run — только отдельный bounded batch, с новым holdout после восстановления лимита. Не подгонять prompt под первые вопросы.

- Устранить `question-only` evidence eligibility общей ролью единицы (answer-bearing vs FAQ question/header), без специальных regex по ОФД; B2 пока default-off.
- Создать **новые, ранее неиспользованные** пользовательские сценарии, скрытые от настройки промптов; тестировать на разных сервисах (продление ОФД, Эвотор, чек, 1С, ФН, маркировка), включая завершение и handoff.
- Измерить Retrieval doc + section selection, meaningful answer, technical progress, provider availability, токены, latency, safety **раздельно**. Проводить только ограниченные Groq + read-only Qdrant вызовы с заранее установленным бюджетом.
- Критерий GO — парное преимущество над Source-first A на целостном наборе без safety breach, достаточная доступность API и настоящий handoff contract. При API 429 — BLOCKED, а не победа по успешной подвыборке.

### Шаг 5 — ручной Telegram пилот, только после отдельного GO

- Проверить точный Git SHA/SHA файлов + process env (`AI_COORDINATOR_ENABLED`, `SEMANTIC_EVIDENCE_SELECTOR_ENABLED`, `HANDOFF_ENABLED` по их отдельным GO), Qdrant Stage3, Groq model/reasoning, allowlist; PID/start-time/cmdline, единственность worker, rollback и runtime receipt.
- Только после разрешения переключить реально запущенный worker на согласованный проверенный код; тестер вручную пишет свободные сообщения, результаты сравниваются с журналом.
- Нельзя говорить клиенту, что специалист уведомлён до подтверждённого receipt; если staff chat не согласован — handoff остаётся отключённым с честным сообщением.

**После каждого Codex-отчёта:** фиксируем реальные изменения, tests, отдельно provider attempts и завершённые решения, raw/validated Understanding, retrieved documents и selected sections, полезность/unsafe, стоимость, SHA/conflicts, GO/NO-GO, links. Обновляем `docs/PROJECT_STATE.md` и `docs/RAG_MASTER_PLAN.md` только из интегрирующего checkout, не затирая историю других веток. Фиксируем отрицательные результаты. Конечный ориентир — один безопасный диалог от приветствия через решение задачи до реального handoff.


## Журнал выполнения этапов

### 2026-10-26 — P1 D2 ProgressLedger

- **Статус:** OFFLINE DONE в указанной тестовой вертикали; LIVE BLOCKED/не запускался; PRODUCTION NO-GO.
- **Проверки:** targeted replay 8 passed; полный suite 428 passed, 5 xfailed, 13 warnings, 0 failed. Groq live: 0 вызовов; Qdrant network/write: 0; Telegram/worker: 0. P1 D2 опубликован в `main`, commit `4cdc21f5fb8699a937981e19695705e510de4933`. SHA approved evidence: `f60e847bb28c5ee63346fd2fc1b5aa7ca4b19bce2eb478a8826db8dd02c5d651`.
- **Смысловая коррекция:** «Оплату проверил» не доказывает успех оплаты и остаётся `unknown`; «Оплата прошла» даёт `passed`. Не включать рекомендацию ассистента в клиентские результаты.
- **Следующий шаг (выполнен, см. запись Handoff integration candidate ниже):** подготовить отдельный integration worktree от опубликованного main, подключить read-only ProgressLedger provider, проверить доставку/PII с fake transport. Live, production, merge и push интеграции остаются запрещены без отдельного разрешения.

### 2026-10-26 — Handoff integration candidate (итоговая сверка)

- **Статус:** OFFLINE DONE на временной SQLite + fake transport; LIVE BLOCKED/не запускался; PRODUCTION NO-GO; commit/push readiness GO по результатам offline review, но действие не выполнялось; merge в main NO-GO без отдельного разрешения.
- **Исходные SHA:** main `a606121f518cc5ffd1d3d3a0e860799df8ae2c49`; handoff MVP source `6ed4015edbf33dc43948ee9aa474bb9075bde604` / branch publication `f257ab56697cf98d73da8a74889bf4bce2272d8d`; integration branch is local and unpublished.
- **Результат/изменения:** read-only ProgressLedger provider bound to exact `conversation_id` + `task_id`; package includes only check step/status and exact client quote. Сообщения других задач исключены. Независимый `HANDOFF_APPROVED_CHAT_ID` allowlist guard блокирует recipient mismatch. Ticket ID связан с request + conversation/task; email/phone редактируются. Main ProgressLedger/source-first/flags preserved; no SQLite schema, KB, Qdrant, `.env`, production database, or worker changes.
- **Tests:** 21 targeted passed / 24 deselected; full suite **441 passed, 5 xfailed, 0 failed**. Python 3.12.2 main venv; ignored fixture доступна через временный junction, `langgraph` из временной изолированной dependency directory; fixture не читалась/не копировалась. `git diff --check`, py_compile passed. E2E trace and privacy review are in [integration report](../experiments/architecture_recovery_audit/p1_handoff_integration_20261026.md).
- **Exact E2E replies/trace:** «Сохранить заявку специалисту по последнему вопросу и ответу?» → подтверждение «Заявка SR-0000001-26BA740F: Telegram подтвердил отправку специалистам.» (ticket hash from the combined test SQLite). Client results Internet `passed`, payment «Оплата прошла» `passed`; payment status derived only from client quote. After reopen, next exact approved check: «2. На модели 5, 5i, 7.2, 7.3, 10 или Power под администратором откройте „Настройки → Обслуживание кассы → Диагностика → Диагностический отчёт“.» Repeated confirm sent once; topic change creates a new empty task; “Спасибо, всё решено” closes it. See report for failure/no-chat/restart traces.
- **Риски/next:** timeout ambiguity remains; manual staff-side ticket reconciliation before explicit retry. `pending` persists across crash and never auto-sends. Single-process outbox; live access/retention still needs approval. Stage 1 merge gates passed. Live/production gates remain separate; следующая работа по этому запросу — общая eligibility Semantic Evidence Selector. No live chat configuration, Telegram send, or worker switch.


### 2026-10-26 — P1 B+ route/applicability repair (offline)

- **Статус:** offline code + SQLite replay DONE; next live gate proposed but not run; live/production NO-GO; B2 default-off. Этот результат продолжает этапы B+; он не начинает общий аудит и не меняет B2.
- **Stage 4B trace correction:** saved trace доказывает локальный Qdrant retrieval в двух Evotor turns (по два candidate, все отклонены по ошибочной категории `receipt_search`) и в quota-blocked receipt-period turn (73 candidate, один выбран); OFD turn вернулся до поиска. Все четыре Groq HTTP calls были Understanding; Evidence Decision/planner/composer Groq requests и source SHA checks отсутствовали. Начальное описание «0 retrieval» смешало локальный поиск и отсутствие отдельных Groq calls; исправлены [master](RAG_MASTER_PLAN.md), [journal](PROJECT_STATE.md) и [Stage 4B report](../experiments/architecture_recovery_audit/p1_unified_live_gate_20261026b.md).
- **Root causes / repair:** (1) coordinator `grounded_information` против SourceFirst expected-task/readiness recheck; (2) Understanding enum отвергал `procedure`/`diagnosis`, а model-as-slot терял точную модель; (3) reducer/search fallback породил `receipt_search`, после чего applicability корректно, но неверно по категории, исключила `receipt_transmission`; повтор на follow-up. Coordinator-selected retrieval теперь не блокируется повторной readiness оценкой. Semantic aliases normalized; модель восстанавливается только по точному текущему evidence span и общему brand alias registry; transmission/status category определяется из подтверждённого manufacturer + receipt + operator cabinet + absence. Общие approved/applicability/source SHA/safety gates не ослаблены.
- **Progress flow:** запрос определения проходит без ненужного service/model label; в тех.диагностике сохраняется подтверждённая модель, на первой реплике показывается один complete approved check, затем ожидается exact client result, и после его подтверждения выбирается следующий применимый approved check. Для нетипографированных source paragraphs создан generic sentence-level check unit с сохранением полного source sentence и порядка.
- **Offline OLD/FIXED:** см. [B+ report](../experiments/architecture_recovery_audit/p1_bplus_offline_replay_20261026.md) и [replay trace](../experiments/architecture_recovery_audit/p1_bplus_offline_replay_20261026.json). Сохранённые raw Understanding payloads прошли через реальный `bot.handle_message`, temporary SQLite и штатный reducer; fake retrieval использовал локальные approved статьи. Groq/Qdrant network/Telegram/worker/production writes = 0. Три QUALITY FAIL переведены из преждевременной clarification/escalation в evidence-backed answer или точное ожидание результата шага. Синтетический отчёт результата дополнительно доказывает переход к следующей approved проверке.
- **Тесты:** B+ replay и ProgressLedger E2E targeted PASS; полный `python -m pytest -q`: **454 passed, 4 xfailed, 13 warnings, 0 failed**. Набор включает unknown/confirmed/changed model, topic change, contradiction, closure, missing required data, handoff and independent safety stops.
- **Groq accounting:** 3,757 prompt + 4,546 completion = 8,303. Captured usage не раскрывает историю/schema/reasoning/structured-output subcomponents; actual request тела не сохранились. Сейчас low reasoning effort, recent history до 12 сообщений, `max_completion_tokens=4096`. План оптимизации: offline per-component size logging, history trimming по active task с тестами continuity, structured-output unchanged, и только после paired quality/truncation evidence рассмотреть cap 2,048 (observed max completion 1,465). Новых provider вызовов не было.
- **Следующий шаг:** один маленький serial live gate: OFD read-only information + Evotor initial check, Stage3 Qdrant read-only; TPM preflight before each stage, не более 4 HTTP attempts total, no retries or concurrency, stop before a request unless its conservative token estimate plus reserve fits remaining quota; wait for reset and recheck otherwise. Это предложение, не разрешение на запуск. Live NO-GO до независимого scoring и подтверждения safety/source integrity. Commit/push не выполнялись.


### 2026-10-26 — P1 B+ Stage A control and live C preparation

- **Статус:** offline regression/safety gate GO; publication readiness GO, but no commit/push made. Stage B is prepared and has not made a Groq call.
- **Working tree:** HEAD remains `3fac0d17bd5f51df7c4a128b0e42f28c519edba9`; existing local changes/artifacts were reviewed and kept. `.env` unchanged.
- **Neighbor routes:** cabinet lookup → `receipt_search`; absent transmission to OFD → `receipt_transmission`; cash-register failure → `error_diagnosis`; information explanation → no technical task category.
- **Procedure unit safety:** unnumbered sentence bundling was strengthened after review showed prior extraction could omit adjacent preconditions/warnings. Regression now verifies source order, preceding conditions/warnings attached to the next action, and trailing caveat attached to the last action.
- **Tests:** full pytest **456 passed, 4 xfailed, 13 warnings**; `git diff --check` and live runner `py_compile` pass.
- **Frozen independent holdout C:** [JSON](../experiments/architecture_recovery_audit/p1_bplus_live_holdout_20261026c.json), [rubric](../experiments/architecture_recovery_audit/p1_bplus_live_holdout_20261026c.md), SHA-256 `42bd32d26c080997b5b253a702ebac21bc62768dedf2ce7bfc7afe53b86fc760`, fixed before provider calls. The earlier three failures remain DEV regressions.
- **Read-only preflight:** Groq configured; Source-first coordinator on; B2 off; Stage3 collection green, 934 points. This preflight made no Groq call and no writes.
- **Attempt constraint:** four total HTTP attempts include a current quota-header probe. Two required turns fit as probe + information Understanding + diagnostic Understanding + one SourceFirst planner. The optional continuation needs two further provider requests and therefore will be marked BLOCKED if the cap is reached. Per-stage TPM estimate must fit remaining quota with a 1,000-token reserve. No retries.
- **Next:** execute only the bounded current Source-first gate. B2 A/B remains a separate proposal on frozen retrieval; no B2 activation or manual Telegram smoke test until live usefulness and a complete multi-turn dialogue are demonstrated.

### Stage B result — quota gate BLOCKED (2026-10-26)

- C holdout and rubric are still frozen and unscored; hash remains `42bd32d26c080997b5b253a702ebac21bc62768dedf2ce7bfc7afe53b86fc760`. Known prior failures remain DEV regressions.
- Stage3 read-only preflight passed for `knowledge_stage3_retrieval_20261022` (934 points, green), with Source-first/coordinator enabled and B2 off.
- Exactly one of four allowed HTTP attempts was used for authenticated Groq `GET /models`: HTTP 200, 776 ms, no rate-limit/TPM headers, zero usage tokens. With no reliable value for remaining TPM, the harness correctly stopped before Understanding or any chat completion. No retrieval query, source selection, answer, retry, or simulated result occurred. C1/C2 and optional continuation C3 remain unrun. Evidence: [trace](../experiments/architecture_recovery_audit/p1_bplus_live_trace_20261026c.json).
- Stage A is GO for offline publication readiness (456 passed, 4 xfailed, 13 warnings), but Stage B is BLOCKED and does not establish live route or usefulness. B2 frozen-retrieval A/B is **NO-GO** until the current Source-first live path is validated. Manual Telegram smoke test is **NO-GO**. Next step is to identify supported account TPM telemetry, then seek a new bounded run authorization; preserve B2 off and Stage3 read-only. No commit/push.

### User-authorized closed Telegram pilot — preparation (2026-10-26)

The user explicitly authorized checked code publication and one controlled pilot worker. This is a diagnostic exception to the earlier manual-test gate, limited to the verified three-ID Source-first allowlist; it is not a production quality pass. The C holdout remains unrun/unscored and B2 stays off.

The failed quota preflight came from demanding TPM headers on `GET /models`. The application now uses a shared bounded rate limiter for real Groq Understanding and generation calls: an unknown first quota permits one paced request, then actual TPM/RPD/reset/Retry-After headers and usage guide further calls; maximum local wait is 8 seconds, without HTTP retry loops. A deferred request produces a clear saved-context reply. Model `openai/gpt-oss-20b`, `medium` reasoning and structured Understanding output remain unchanged. See [Groq's rate-limit contract](https://console.groq.com/docs/rate-limits). The historical C script was corrected for future use; no fresh C calls were made.

Pre-publication full pytest: **463 passed, 4 xfailed, 13 warnings**; safety/model-scope negatives passed. Read-only Stage3 is green, 934 points, with 206 local approved documents and a matching Qdrant approved sample. No active bot worker or webhook was found. Existing allowlist count/hash are 3 / `a769696dc284d3ca09ef096a08f59a838bbe09f23f671ab794d1cb573910b7e7`; process overrides will use this exact existing list while all other IDs keep legacy behavior. Production SQLite has a verified private SQLite backup under `.local/backups/`. Three stale pending Telegram messages belonged to allowlisted users; acknowledge only those before starting polling to avoid answering old inputs. Next is explicit commit/push, one hidden worker start, runtime hash and polling verification, then user-authored manual scenarios. Specialist delivery stays disabled.
