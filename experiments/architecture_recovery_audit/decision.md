# Архитектурное решение: вариант B

Дата решения: 2026-10-25. Статус: **принято как направление восстановления в текущем этапе V1.2/V3**, реализация и смена Telegram runtime отдельным заданием. Не меняет статусы V1.3/V1.4/V2 и не обходит P0.5 из [RAG_MASTER_PLAN](../../docs/RAG_MASTER_PLAN.md).

## Решение

Построить **разговорный координатор с тремя явными маршрутами**:

1. `conversation`: приветствия, благодарность, формулировка задачи, уточнение уже открытого слота, признание новой детали. Здесь не требуется RAG, если ответ не содержит доменного факта/действия. Deterministic social ответ разрешён; при смысловой неоднозначности координатор получает историю/активную задачу.
2. `grounded_information`: определения и ограничения, поиск факта. Координатор решает, нужен ли источник; технические определения, реквизиты, правовые и продуктовые утверждения опираются на approved evidence. Если источник scoped, ответ явно ограничивает область; отсутствие сервиса не блокирует сам ответ о границе знания. Подтверждённые независимые фразы можно сохранить с condition guards.
3. `technical_action`: диагностика, пункты меню, настройка, права, фискальные операции. Требуются approved/applicable source, подтверждённые факты клиента и проверка каждого действия/предусловия. Для высокого риска сохраняется явный stop/escalation. Без нужной модели/сервиса допускается лишь общая безопасная проверка, подтверждённая источником для этой области, либо полезное одно уточнение.

Координатор предлагает `task_relation`, `answer_route`, `missing_slot`, `risk_class` и факты с exact span текущей пользовательской реплики. Детерминированный reducer владеет task state и подтверждением фактов; модель не может вписать service/model из собственного ответа. При неизвестном/некорректном выводе допустим bounded clarify или safe escalation, но не генерация процедуры. `expected` закрывается только при факте соответствующего слота или явном ответе «не знаю»; повтор того же вопроса ограничен. Новый task не наследует чужие task facts, но может видеть session context без автоматического применения.

## Почему именно этот вариант

Пилот выявил ошибки **до** Planner/Composer — routing и scope лишили пользователя даже безопасного ответа. Одна лишь настройка Grounding их не устранит. Oracle подтвердил, что модель понимает разговор лучше жёсткого набора категорий, но пишет неподтверждённые действия. Поэтому смысловой coordinator полезен только вместе с независимыми границами фактов и действий. Exact-source техническая ветка уже реализована и снижает риск, поэтому её разумно сохранить. Legacy partial answer и coverage notice показывают полезный механизм, который можно перенести без возвращения свободной технической генерации.

Сначала P0 устраняет подтверждённые ошибки нынешнего пути и обеспечивает репродукцию в SQLite. Затем P1 вводит маршрутный контракт под feature flag и сравнивает с A на одних сценариях. Если B не повышает полезность при неизменной safety, остановиться и не переключать runtime. Полный план — [implementation_plan.md](implementation_plan.md).

## Инварианты safety и quality

**Safety gate (обязателен):** ноль неподтверждённых технических действий/точных UI названий/прав/правовых требований; ноль инструкций по необратимым операциям без явного одобренного protocol; approved + scope + source integrity; неизвестный слот не выдумывается; личные данные/ключи не попадают в отчёты. Провал safety останавливает пилот даже при улучшении полезности.

**Quality gate (диагностический):** содержательный ответ/полезная частичная помощь, отсутствие третьего повторения вопроса, сохранение task при продолжении, переключение при новой теме, понятное ограничение области знания. Отказ может быть допустим на ограниченном пилоте только если он безопасен и его причина/доля записаны; 0/6 полезных ответов недопустимо считать успешным quality gate.

## Не доказано и не принято

- Не доказано, что вариант B сократит задержку/стоимость до целевых значений; требуется замер per-stage и на последовательности диалогов.
- Не доказано, что текущий `claim_supported` имеет достаточный recall/precision для всех русских парафразов; у V1.1 есть опасные FP, у Typed replay — чрезмерные FN. Нельзя просто удалить Judge или Grounding.
- Не доказана актуальность всех внешних статей или полнота approved KB. Этот аудит их не менял и Qdrant не переиндексировал.
- Не принято переключение живого worker PID 46544: его receipt SHA отличается от рабочего файла. Новый runtime допускается только после ворот в плане и отдельного разрешённого задания.


## Реализация P1 D1 — 2026-10-26

### Bounded live gate — 2026-10-26

Одна ограниченная execute-попытка остановилась на read-only Qdrant `collection_exists` (`127.0.0.1:6333`, connection refused / WinError 10061), до Groq, временной SQLite, retrieval и ответа. Фактические calls: 1 неуспешная Qdrant readiness read; Groq 0, tokens 0, retrieval turns 0, writes 0, retry 0. Live semantic answer quality не измерена. Предыдущая offline trace подтверждает generic-overlap mismatch: для D1.3 выбрана grounded фраза про договор/тариф вместо объяснения роли ОФД. **NO-GO расширению grounded-information; GO только к P1 D2 offline; NO-GO live/worker.** Полный [отчёт](p1_d1_live_experiment_20261026.md) и [trace](p1_d1_live_trace_20261026.json).

#### Erratum и восстановленный bounded run — 2026-10-26

Контейнер Qdrant `rag-qdrant-1` принадлежит текущему compose проекту и использует существующий volume `rag_qdrant_storage`; он был остановлен без restart policy, поэтому localhost port отказал. Контейнер безопасно запущен без пересоздания данных. Erratum: первая trace ошибочно записала `knowledge_v1`; это был fallback из исходного кода, не фактическая коллекция. Импорт `app.config` загружает `.env`; эффективная `.env` collection была `knowledge_organized_stage2_[redacted-number]`. Последние успешные live тесты проекта реально использовали Stage3 `knowledge_stage3_retrieval_20261022`; она установлена для run2 process-only.

Preflight подтвердил 934 points/384 dimensions, 672 approved chunks, согласование всех 206 approved documents по локальным content hashes и scopes, и совпадение всех chunk texts с текущим локальным indexer output. Run2: 2 Groq Understanding calls, 3,572 tokens, 2 retrieval turns, 18 успешных Qdrant read requests, zero writes/retries. Первый ответ объясняет роль ОФД. Второй повторяет лишь договор/тариф и не отвечает зачем оператор нужен кассе. Top retrieval candidate на обоих ходах — правильный approved OFD документ; generic overlap выбрал неправильное предложение внутри него. Safety pass, semantic quality **NO-GO**. **NO-GO для расширения grounded-information; GO только для P1 D2 offline.** См. [полный отчёт](p1_d1_live_experiment_20261026.md) и [run2 trace](p1_d1_live_trace_20261026_run2.json).

Первая opt-in реализация варианта B находится в [`p1_d1_implementation_20261026.md`](p1_d1_implementation_20261026.md): typed coordinator поверх validated Understanding/reducer state, route-флаг за текущей Source-first allowlist, точный approved-information slice и serialized decision diagnostics. D1 offline проходит на реальном application path; Source-first A остаётся при флаге off. Это не меняет NO-GO P0 quality gate и не разрешает production/live/worker switch. Следующий разработческий slice — D2 task progress и безопасный следующий технический шаг.

### Решение: ограниченный ID-only evidence selector — 2026-10-26

Добавить selector допустимо только как отдельный experiment flag, default off, сохраняя lexical default и прежний Source-first. В двух завершённых live A/B парах на одинаковых evidence semantic selection был полезен 2/2 раз, lexical — 1/2: D1.2 одинаково полезен в обеих arms, D3.1 semantic дополнительно указал маршрут поиска. После исключения question-only section из lexical control ошибка harness исправлена офлайн на тех же snapshots. Оба follow-up решения сорвались: один provider status не сохранился, второй ответил HTTP 429. При 8/8 Groq attempts и 4/4 retrieval turns качество полного D1/D3 не установлено; дополнительная стоимость успешного selector — один call и 2.6k tokens на ход. **NO-GO** grounded-information rollout и признанию selector заменой Planner/Composer/Judge; **GO** только к offline P1 D2 с ProgressLedger, не связанному с selector. Не вызывать live повтор сверх лимита. Подробности: [A/B report](p1_semantic_selector_ab_20261026.md) и [trace](p1_semantic_selector_ab_20261026.json).
