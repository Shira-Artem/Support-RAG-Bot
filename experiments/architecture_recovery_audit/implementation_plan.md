# Последовательная программа восстановления

Дата: 2026-10-25; историческая программа с результатами продолжений до 2026-10-26. Этот документ не является отдельной дорожной картой: статусы и следующий шаг задаются [RAG_MASTER_PLAN](../../docs/RAG_MASTER_PLAN.md), а операционные условия P1 — существующим [v0.3 планом](../../docs/Support_RAG_AI_Coordinator_Plan_v0_3_2026-10-26.md). Порядок: P0 → ограниченный diagnostic gate → P1 → P2 → P3. Для каждого шага хранить raw/final ответ, stage route/reason, токены и SHA без персональных данных. Сравнивать одинаковые диалоги, а не отдельную фразу об ОФД.

> **Обновление 2026-10-26:** после P1.0 ниже прежний P1 план заменён окончательным зависимым планом варианта B. Секции P0/P2/P3 выше сохранены как историческое планирование; актуальные P1 границы, задачи, тесты и критерии — в [P1.0 causal experiment and final P1 plan](p1_0_causal_experiment_20261026.md).

**Обновление 2026-10-25:** P0.1 выполнен как диагностика; [P0.2](p02_report.md) завершён offline, два повтора устранены; [P0.3](p03_report.md) завершён offline, источник-атрибутированное ограничение ФН и безопасный preflight Эвотор проходят. Полный suite 390 passed / 0 failed. Live worker и ручной Telegram gate не переоценивались; P0.5 не начат.

## P0 — разблокировать полезный разговор в нынешнем пути

**Проблема / evidence.** Telegram 0/6: широкая просьба дошла до retrieval; определение/диагностика/поиск границы по ФН остановились на scope; `expected` потерян и вопрос повторился. Полный suite 376/5. PID 46544 содержит старый snapshot.

**Решение / компоненты.** (1) Единый контракт `request_type/operation/intent` и readiness до retrieval, без узкой regex под одну формулировку. (2) `ConversationStore`/`DialogueManager`: слот закрывать по подтверждённому факту либо явному unknown; сохранять новые симптомы, не отвечая повторно тем же вопросом. (3) `RetrievalPipeline`/`SourceFirstService`: классифицировать ответ как определение, ограничение или действие; применять service/model scope к **действию**, разрешать source-attributed ограничение и нейтральную безопасную проверку при недостающем service. Не допускать product-specific menu без подтверждённой области. Классифицировать четыре настоящих падения и пересмотреть устаревшее ожидание, не исправляя тесты автоматически.

**Риск.** Чрезмерное ослабление applicability может открыть чужую процедуру; слишком широкое explain → general может скрыть действие. **Приёмка.** Один и тот же fake Telegram → real SQLite путь проходит диалоги D1–D3 из [acceptance_scenarios](acceptance_scenarios.md), не повторяет сервисный вопрос и даёт минимум безопасный частичный ответ, если источник его поддерживает. Полный offline suite зелёный или каждая оставшаяся non-safety проблема явно согласована; safety negatives 100% blocked. **Тесты.** Unit на переходы, search scope, exact source; SQLite-backed `bot.handle_message`; один bounded live-path прогон только после offline gate, затем отдельный ручной allowlist пилот после проверенного worker switch. **Остановка.** Любое неподтверждённое действие, потеря обязательного условия, неверное наследование сервиса или runtime SHA mismatch останавливает switch; без useful progress на тех же диалогах прекратить косметические fixes и перейти к P1 проектированию без пилота.

## P1 — минимальная разговорная архитектура B

**Проблема / evidence.** Пять разных классификаций и два scope gate связывают общение с источником; Oracle показывает сильное понимание модели, но слабую техническую точность.

**Решение / компоненты.** Feature-flagged coordinator и typed route contract `conversation|grounded_information|technical_action`; reducer владеет task/slot; safe social route без KB; information route с approved evidence и claim ledger; technical route с существующим exact-section renderer, applicability и risk policy. Объединить дублирующиеся scope решения в один источник истины. Для уточнения хранить slot, причину, число повторов и какое новое evidence было получено. Legacy partial-answer/coverage notice перенести только после safety проверки.

**Риск.** Ошибка координатора направит технический запрос в обычный диалог; исключить технические факты/действия из conversation route детерминированным output guard. **Приёмка.** На замороженных D1–D5 и safety S1–S6: ни одного safety breach, task continuity/new task/unknown slot проходят, не менее 70% из 21 пользовательской реплики получают полезный ответ либо содержательное необходимое уточнение; повтор одинакового слота максимум один без новых фактов. Это предварительный локальный порог, не production SLA. **Тесты.** Парное A/B offline E2E на одинаковом raw Understanding и KB snapshot; shadow replay без отправки в Telegram; ручная оценка полезности слепо к варианту; provider/SQLite/restart fault cases. **Остановка.** Если B не превосходит A по полезности при тех же safety limits или даёт хоть одно неподтверждённое действие, не переключать runtime.

## P2 — RAG, grounding, меньше лишних эскалаций

**Проблема / evidence.** Stage3 selected reference 40/83, 31 reference случаев `task_unresolved` в историческом срезе; approved статьи имеют vendor scope и question-only sections. Q2 Repair содержал поддержанную и неподдержанную фразы, но ответ был потерян. Одна выбранная секция ограничивает ответ.

**Решение / компоненты.** Небольшой приоритетный набор approved карточек для общих определений и безопасной диагностики по source review; отдельная метка applicability каждого факта/шага; rerank answer-bearing sections и проверка связанных предупреждений, а не слепой top section. Claim ledger: supported/unsupported/conditional с provenance, аккуратная частичная выдача только независимых утверждений. Judge оставить как quality check релевантности там, где измеренная польза покрывает ошибки/стоимость; failure должен давать fallback на следующий допустимый source либо честное ограничение, не цикл Repair.

**Риск.** Неполный KB и парафразный false accept/false reject; частичный ответ может потерять условие. **Приёмка.** На независимом holdout растёт доля полезных grounded ответов и падает доля неуместных эскалаций при 0 dangerous false accepts; по каждому реальному отказу известен stage/reason. **Тесты.** Source-level разметка секций, claim/step проверки с отрицательными парами, retrieval recall и applicability отдельно, ручная оценка новых обращений. **Остановка.** При первом опасном false accept остановить расширение и восстановить safety; при отсутствии достаточного approved evidence не компенсировать выдумкой или переиндексацией без отдельного решения.

## P3 — токены, задержка, расширяемость

**Проблема / evidence.** Успешный двухходовый ограниченный live прогон: 9 вызовов, 13 352 токена; отдельные прогоны имели provider 429. Результат не является средней стоимостью трафика.

**Решение / компоненты.** На основе per-stage traces убрать дублирующие вызовы Judge/Repair, где их marginal quality доказанно нулевая, кэшировать только immutable approved sections и безопасные общие определения по source SHA, ограничить history/section payload без потери условий. Сформировать обобщённые metadata contracts для новых тем вместо роста regex. Инструментировать p50/p95 latency, calls/turn, prompt/completion, отказ по стадии.

**Риск.** Кэш устаревает, truncation отбрасывает условия, уменьшение проверок повышает false accept. **Приёмка.** На том же holdout и safety наборе calls/tokens и p95 уменьшаются относительно P1 baseline без снижения usefulness/grounding и без safety breach. **Тесты.** Парные трассы до/после, invalidation по source SHA, rate-limit/failure injection. **Остановка.** Если экономия достигается ценой неподтверждённого шага или падения качества, откатить оптимизацию.

## Первые три конкретные задачи

1. Создать изолированный SQLite-backed тест, вызывающий `bot.handle_message` на всех шести обезличенных репликах с provider fixtures и restart/replay; записать exact route/reason/raw/final без ключей и IDs. Не передавать вручную state в сервис.
2. Исправить контракт task/expected/route и классифицировать пять падений согласно [failure_matrix](failure_matrix.md), сохраняя отрицательные тесты на подмену сервиса и опасные действия. Добиться прохождения offline safety и principal dialogue routes.
3. Разделить `information limitation` и `technical procedure` в applicability: дать ответ с явной областью источника и безопасную частичную диагностику Эвотор, не выдавая настройки или модели без подтверждения. Сравнить тот же набор до/после.

**Кратчайший безопасный путь к следующему ручному Telegram-пилоту:** эти три задачи в P0 → полный offline suite + SQLite E2E + отрицательные safety cases → ровно один bounded live-path прогон с лимитом вызовов/токенов → сверка PID/receipt/source SHA/allowlist/коллекции и единственный switch worker только по отдельному разрешённому заданию → ручной пилот на D1–D3 с записью usefulness и safety отдельно. При безопасном, но малополезном результате не заявлять успех; P1 уже выбран как дальнейшее направление.


### Stage 4B continuation — result and decision (2026-10-26)

This existing v0.3 plan remains the working plan; no new plan was created. Stage 4B used a new frozen independent holdout plus rubric before model calls, real Groq Understanding, and read-only Stage3 Qdrant. It stopped at 4/8 HTTP attempts due to live TPM quota (1,324 remaining vs 3,092 estimated for the next request). Four Understanding HTTP 200; no decision/planner Groq calls. The trace has local retrieval candidates on two Evotor turns and one selected candidate on the quota-blocked receipt-period turn; Useful 0; QUALITY FAIL 3; SAFETY FAIL 0; provider-blocked 1; destructive safety case unrun. B2/lexical paired quality comparison was incomplete: the Evotor turns had no selected evidence, and the quota-blocked receipt-period turn did not complete downstream evaluation. Usage 3,757 prompt + 4,546 completion = 8,303 tokens; nominal uncached published-rate estimate $0.00165. No retries or 429. Full suite **451 passed, 5 xfailed**. B2 remains off and Telegram pilot NO-GO. Report, trace, rubric and exact next step are in [Stage 4B report](p1_unified_live_gate_20261026b.md), [trace](p1_unified_live_gate_trace_20261026b.json), and [rubric](p1_unified_live_gate_holdout_20261026b.md).

Next work stays within P1: offline diagnose Understanding/coordinator readiness for general information and applicable Evotor next-check behavior on independent fixtures; keep procedures whole and all provenance/safety gates strict. Freeze a new holdout only after offline changes settle; repeat a bounded live gate only with sufficient verified Groq capacity. No B2 production activation, worker switch, or manual Telegram pilot until live usefulness, source checks, and negative safety case pass.


### B+ offline continuation synchronized with v0.3 (2026-10-26)

This existing file remains a historical execution program and is subordinate to the canonical master and v0.3; it is not a competing implementation plan. The Stage 4B sentence above was corrected from “no retrieval”: saved `retrieval_diagnostics` confirm local Qdrant search in three turns, but no Evidence Decision/planner/composer Groq request or source SHA validation.

The approved v0.3 continuation [records the B+ route/applicability repair](../../docs/Support_RAG_AI_Coordinator_Plan_v0_3_2026-10-26.md). Root causes: SourceFirst overrode a coordinator-selected information route; Understanding rejected generic diagnosis/procedure aliases and model-as-slot evidence; receipt-search fallback then excluded transmission articles. Fixes make Coordinator the readiness authority on retrieval routes, normalize generic operation aliases, recover models only from exact current-message evidence using the shared brand alias registry, map confirmed missing-receipt operator-cabinet diagnostics to transmission/status, and preserve exact ordered ProgressLedger procedure steps. Independent safety, approved-source, source-integrity and applicability gates remain active.

Saved raw Understanding payloads replayed through `bot.handle_message` and temporary SQLite without Groq. B+ report: [OLD/FIXED causal analysis](p1_bplus_offline_replay_20261026.md); JSON: [fixed replay](p1_bplus_offline_replay_20261026.json). Full suite after final code change: **454 passed, 4 xfailed, 13 warnings**. Live calls remain unrun and unauthorized; B2 remains default-off; live/worker/production NO-GO. Next live proposal and TPM stop rule are in v0.3.
