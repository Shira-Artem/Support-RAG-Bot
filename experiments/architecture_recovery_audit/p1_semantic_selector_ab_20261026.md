# P1 experimental LLM Evidence Selector — bounded live A/B

Дата: 2026-10-26. **Итог: semantic selector показал улучшение на 2 успешных парных ходах, но полный quality gate — NO-GO / незавершён из-за двух ошибок Groq.** Лимит исчерпан; повторов не было.

## Вопрос и заранее заданная оценка

Проверялось, может ли один ID-only Decision после Understanding и Hybrid Retrieval выбирать evidence по смыслу текущего хода, сохраняя точное цитирование и независимые проверки. Критерии полезности зафиксированы отдельно от safety:

- D1.2: объяснить роль оператора, не повторять только заголовок-вопрос.
- D1.3: объяснить назначение ОФД для получения/передачи фискальных документов; договор и тариф сами по себе не отвечают.
- D3.1: объяснить, где искать чек в указанной Платформе ОФД.
- D3.2: сохранить поиск чека и объяснить настройку периода прошлого месяца.

Сами по себе различие ответов, точная цитата и успешная safety-проверка не засчитываются как полезность. Ручная семантическая оценка отделена от автоматических provenance/applicability/safety gates.

## Реализация

- Добавлен [semantic_evidence_selector.py](../../app/semantic_evidence_selector.py), активируемый отдельным `SEMANTIC_EVIDENCE_SELECTOR_ENABLED`, default off. При включённом coordinator и grounded-information решение ID-only selector заменяет lexical sentence ranking; default lexical path и прежний Source-first остаются.
- IDs детерминированно зависят от SHA источника, `document_id`, раздела, позиции и типа unit. Процедурный раздел подаётся целым упорядоченным блоком, не отдельными шагами.
- В запрос входят текущий вопрос, reducer-owned state, недавняя история и ограниченные approved-кандидаты с разделами. Evidence budget — **3,000 оценочных токенов на целые разделы**, task/history budget — 1,000 оценочных токенов; оценка консервативная, 3 символа/токен. Реальные usage берутся из ответа Groq.
- Модель возвращает только `select` с ID, `clarify` с ограниченным slot или `no_evidence`; свободный текст ответа/инструкций схема не принимает. Локальный строгий парсер отклоняет unknown/duplicate IDs и недопустимые поля.
- Независимая проверка повторно читает локальный approved source и SHA, сверяет exact section/text, проверяет scope для technical route, запрещённый prompt-injection текст, dangerous operations, инструкционные safety правила и несовпадающие коды ошибок. Facts/state не меняются. Финальный ответ собирается только из выбранного исходного текста и добавляет область источника.
- Предыдущие Planner/Composer/Repair/Semantic Judge и Source-first остаются для прежних маршрутов; selector не удаляет их и не переключает worker.

Текущая live A/B runner использовала один настоящий Understanding и один retrieval на ход; lexical и semantic варианты получили одинаковый сохранённый evidence snapshot и одну и ту же предшествующую историю (включая lexical assistant response), чтобы сравнение не меняло вход между arms. Исторический Source-first 9 calls / 13,352 tokens — только ориентир, не парный контроль.

## Offline проверки

Команда: `python -m pytest -q tests/test_semantic_evidence_selector.py tests/test_source_first_dialogue_contract.py` — **36 passed**. Дополнительно `py_compile` прошёл для selector, service, config и A/B runner.

Отрицательные проверки: forged/unknown ID; неверная форма no-evidence; подмена сервиса; prompt injection в evidence; ошибочный код ФН 234 при task code 235; SHA mutation; draft evidence. Также проверены стабильность ID, неделимый procedural block, typed no-evidence/clarification и feature-flagged renderer с атрибуцией области источника.

## Live A/B и исходы

Фактическая конфигурация: Groq `openai/gpt-oss-20b`, Qdrant read-only facade, `knowledge_stage3_retrieval_20261022`, 934 points, process-only Source-first/Coordinator flags, temporary SQLite. `.env`, production SQLite, Qdrant writes, KB, worker/Telegram не затронуты.

| Ход | Lexical на том же evidence | Semantic ID selector | Ручная оценка |
|---|---|---|---|
| D1.2 «Что такое ОФД?» | «ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.» | Тот же approved sentence | Оба полезны; улучшения качества здесь нет |
| D1.3 «А зачем он нужен кассе?» | «Для обычных сценариев облачной кассы требуется корректно оформленный договор и действующий тариф ОФД.» | Groq Decision завершился `GenerationError`; результата нет. Первоначальный runner не сохранил HTTP статус, восстановить его нельзя | Lexical не отвечает; semantic ход не оценён |
| D3.1 «Найти чек в Платформе ОФД.» | «Период задаётся датами пробития, а не поступления в ОФД.» — не показывает путь поиска | «Маршрут: „Чеки“ → „Поиск чеков“. Период задаётся датами пробития, а не поступления в ОФД. Для прошлого месяца выберите календарные границы нужного месяца. Основные параметры: тип документа, магазин, касса по названию или РНМ; отдельно доступны ФД и ФП из чека.» | Semantic полезен и сохраняет порядок; lexical не отвечает на «где искать» |
| D3.2 «А за прошлый месяц?» | «Для прошлого месяца выберите календарные границы нужного месяца.» | HTTP 429 `Too Many Requests`, `Retry-After: 11s`; результата нет | Lexical полезен; semantic ход не оценён |

В двух успешных парных ходах semantic ID selection дал **2/2 полезных ответа**, lexical — **1/2**: D1.2 был одинаково полезен в обоих вариантах; в D3.1 semantic выбрал маршрут поиска вместе с правилами периода, а lexical оставил только правило периода. По всем четырём запланированным ходам semantic завершён в **2/4**, lexical полезен в **2/4**. Результат показывает преимущество на одном из двух завершённых парных ходов, но не решает проверяемый D1.3 follow-up.

**Исправление evaluation harness:** первоначальный live harness не применил существующий `SourceFirstService` question-only filter к lexical control и поэтому временно записал заголовок-вопрос для D1.2. После прогона lexical результаты были пересчитаны офлайн на тех же сохранённых approved sections с существующим фильтром; D1.2 lexical стал тем же полезным предложением, что semantic. Это изменение только в оценке трассы и runner; Groq/Qdrant не вызывались повторно.

## Calls, цена и latency

- Ровно **8 Groq attempts / максимум 8**: 4 Understanding + 4 Selector decisions; 4 Hybrid retrieval turns / максимум 4; automatic retries — 0.
- Два Selector завершились успешно: D1.2 — **2,575 tokens**, 986 ms (2,236 prompt / 339 completion); D3.1 — **2,750 tokens**, 872 ms (2,501 / 249). Это дополнительная цена против lexical, для которого post-Understanding Groq call равен 0: одна попытка и примерно 2.6k tokens на успешный ход.
- Два selector запроса не дали ответа. D3.2 — HTTP 429, retry-after 11 sec. Для D1.3 HTTP status не сохранился из-за первоначальной ошибки instrumentation. Их token usage неизвестен и не входит в provider-reported total.
- Сумма usage успешных ответов — **8,410 prompt + 4,529 completion = 12,939 tokens**. Нельзя считать её полной стоимостью восьми попыток: usage двух rejected HTTP requests неизвестен. Денежная стоимость не рассчитывалась.
- Historical old Source-first pair: 9 calls / 13,352 tokens, согласно исходному экспериментальному ориентиру пользователя. Это другой запуск без paired retrieval/state; разницу нельзя объявлять доказанной экономией.

## Safety, ограничения и решение

В двух успешных semantic ответах ID принадлежали exact approved fragments, SHA проверен, состояние не изменялось; на D3 service `Платформа ОФД` подтверждён пользовательской репликой. Выбранный procedural evidence оставлен полным ordered section. Успешные автоматические safety/provenance gates прошли. На ошибочных Decision ответ не публиковался. Общий safety результат не компенсирует отсутствие двух финальных ответов.

Run trace: [p1_semantic_selector_ab_20261026.json](p1_semantic_selector_ab_20261026.json) хранит raw/validated Understanding, reducer state, CoordinatorDecision, retrieval candidates/sections, source hashes, IDs, raw Decision JSON, текст обеих arms, safety, tokens, latency и ошибки. Пропущенные Understanding/state/lexical fields на двух исключениях восстановлены офлайн из локального sanitized Understanding trace, сохранённых candidate units и reducer replay; никакие Groq/Qdrant запросы при восстановлении не выполнялись. Для D1.3 потеряны provider status и selector latency; для D3.2 сохранён HTTP 429 и latency. Usage двух rejected HTTP requests неизвестен.

**Решение:** feature flag оставить выключенным по умолчанию. Selector — более содержательный выбор, чем overlap, на обоих завершённых парных примерах; цена — один дополнительный Groq request и ~2.6k видимых tokens на ход. **NO-GO** расширению grounded-information и утверждению, что он заменяет старый pipeline: оба ключевых follow-up не получили semantic решения, второй из-за rate limit, первый с неполной диагностики. Не повторять live gate сверх исчерпанного лимита.

**Следующий этап:** **GO для offline P1 D2 с ProgressLedger** независимо от selector rollout: это отдельный technical-action сценарий, а experimental selector не должен менять state ownership или safety gates. В D2 проверить прогресс/check results и следующий полезный шаг на настоящем reducer/SQLite replay, затем отдельно решать live gate. P0 остаётся NO-GO.
