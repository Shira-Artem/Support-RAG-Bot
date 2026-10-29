# Восстановление живого диалога — 28–29 октября 2026

Итог после продолжения 29.10: **NO-GO для Telegram-worker**. Память подтверждённого порядка восстановлена; один трёхходовый Groq-прогон прошёл, но полный контроль финального кода не завершился из-за TPD. Отдельно воспроизведён malformed JSON от Understanding при strict:true; retry не помог и откачен. Актуальные результаты, 545 passed / 4 xfailed и 125 HTTP / 80 turns — в [отчёте продолжения](continuation_20261029.md). Qdrant работает, Telegram-worker не запущен; commit/push нет.

## Основание и baseline

Изучены дорожная карта и хронологический журнал, KB Sprint 1–3, routing repair, incident-аудиты 27/28 октября, Oracle/Architecture Recovery/P0/P1/ProgressLedger и последние Telegram-пилоты. Первичный полный текст исследования прочитан из `C:/Users/Shira/Downloads/deep-research-report (1).md`, SHA256 `aec74d94be8049d99d4615e20e213bc804e5cef96091a8c23d4bd7abdfd42388`. Сокращённый sprint report не использовался вместо него.

- [Sprint 1](../kb_quality_sprint_20261028/report.md), [Sprint 2 review](../kb_quality_sprint_20261028/sprint2_review.md), [Sprint 3](../kb_quality_sprint_20261028/sprint3_report.md), [Routing step 1](../kb_quality_sprint_20261028/routing_repair_report.md).
- [24 попытки Telegram](../../docs/incidents/2026-10-27-bplus-24-attempt-causal-audit.md), [аудит 28 октября](../../docs/incidents/2026-10-28-telegram-quality-audit.md), [Architecture Recovery](../../experiments/architecture_recovery_audit/).
- Использованы существующие 51 scenario, 10 Sprint 2 и 8 Sprint 3 многоходовых сценариев. Их ожидаемые ответы — проектные критерии, а не доказательство наличия approved KB. В частности, Saby/Диадок/BIFIT drafts не разрешены для production.

Начало: чистый `main`, HEAD `292d9cb`; единственный worker PID 49068, runtime receipt `eda47bb`, 33/33 SHA исходников совпадали с checkout. Stage3 `knowledge_stage3_retrieval_20261022`, green/934; SourceFirst+Coordinator; Groq `openai/gpt-oss-20b`, medium; selector/handoff off; allowlist 3. Разница HEAD и receipt была документационной, не runtime-дефектом.

Read-only аудит production SQLite и локальных raw Understanding traces сопоставил шесть ответов 28.10, 17:18–17:24 МСК, по пяти темам. В трёх случаях retrieval даже не запускался: цель была в raw JSON, но операция терялась при нормализации. В Saby маршрут уже сохранялся и чужие документы отклонялись. ОФД уже отвечал правильно. Приватная трасса оставлена только в `.local/live_recovery_20261028_baseline.json`.

## Причины: что уже было исправлено, что найдено сейчас

Статус относится к конкретной причине и указанной границе доказательства.

| Проверяемая причина | Статус и доказательство | Изменение / граница |
|---|---|---|
| 1. Потеря операции после Understanding | **Уже исправлена для подтверждённых случаев.** `procedure/information` Эвотора, `status_query/lookup` Диадока, `test` БИФИТ превращались в unknown. Baseline live воспроизвёл три общих вопроса вместо поиска. | Использован существующий словарь операций, точный объект поиска и grounded goal. Нераспознанная операция больше не уничтожает понятную задачу. Эвотор 6 получил approved-инструкцию в двух последующих прогонах. |
| 2. Ложный Coordinator task_not_ready | **Уже исправлена для подтверждённых случаев.** Raw goal и product сохранялись, но unknown operation блокировала retrieval. | Coordinator допускает поиск при reducer-owned цели/симптоме и предмете/сервисе. Это не разрешает техническую процедуру без evidence. |
| 2а. DialogueState unresolved как причина последних пяти обращений | **Не подтверждена.** У проверенных реальных обращений `analysis_required=false`. | Старый lexical staging-дефект не объявлен причиной текущих Telegram-ответов. |
| 3. EDO task/operation против правильного документа | **Уже исправлена в локальном контроле.** Статус УПД отделён от фискального чека; coarse `exchange_edo_documents` больше не означает запрет read-only статуса/поиска. | Совместимость coarse metadata = unknown, не match/full. В повторе Sprint 3 Диадок и Saby draft доходят до partial evidence. В approved Stage3 этих знаний нет. Подпись/переотправка не разрешены. |
| 4. Чужой сервис как full/sufficient | **Уже исправлена до этой работы** в explicit-service Step 1 для Saby/Диадок/БИФИТ. Реальные traces это подтверждают. | Сохранён точный service gate. Новые aliases под тестовые фразы не добавлялись. |
| 4а. False relevance / sufficient для недостаточно определённой задачи | **Всё ещё существует.** Старый lexical terminal prompt в Sprint 3 по-прежнему получает нерелевантные error-кандидаты; draft BIFIT tables остаётся partial без доказательства POS scope. | Общая sufficiency policy не ослаблялась и не объявлена исправленной. Approved-статус или partial/full сами по себе не доказывают полезность ответа. |
| 4б. Полезный раздел отвергается Planner | **Уже исправлена потеря подтверждения порядка при продолжении; общий ложный отказ всё ещё существует.** Подтверждение привязано к task/scope/SHA, текущая applicability проверяется заново. | Один трёхходовый live прошёл; финальный повтор после сохранения связанных conditions остановлен TPD. Первичный выбор нового раздела этим не решается. [Подробности](continuation_20261029.md). |
| 4в. Ограничение о ФН вместо ответа о ФД | **Уже исправлена в проверенном live-сценарии.** Общее слово «фискальный» совпадало с FN в relevance shortcut. | Финальный scope turn 1 задаёт правильный вопрос о сервисе; после ответа выдаёт поиск по ФД в Платформе ОФД. В выборе ограничения нормализуется полный предмет ФН/ФД/ФП. Массовая смена grounding vocabulary отклонена. |
| 5. Потеря памяти и прогресса | **Сохранение фактов исправлено; полезное compound-продолжение подтверждено в ограниченном live-прогоне.** Итоговые результаты приводят к точной условной ветке поддержки без повторного вопроса. | Compound остаётся unknown, а не принудительно passed. Финальный runtime не прошёл весь повтор из-за provider quota; универсальное завершение любых процедур не доказано. |
| 6. Повторные уточнения / ранняя эскалация | **Исправлены подтверждённые known-goal, unknown-model и продолжение начатого Evotor раздела; другие отказы всё ещё существуют.** | aQsi получил только справочный факт. HTTP400 Understanding остаётся самостоятельным blocker до полезного ответа; ошибочный provider JSON не принимается за факты клиента. |
| 7. Telegram pipeline против прежнего offline E2E | **Разница подтверждена и устранена в новом harness.** Старый `run_routing_repair_live_e2e.py` проверял AnswerService, не полный Telegram SourceFirst+Coordinator. | Новый harness вызывает настоящий `bot.handle_message`, real Understanding/Coordinator/reducer/Stage3/Planner/Composer, когда соответствующая ветвь нужна. Подменены только Telegram transport и пути локальных store; SQLite переоткрывается между репликами. |

## Клиентские ответы и реальный эффект

Все ответы целиком, вместе с причиной, latency и состоянием: [answers.md](answers.md). Исходные JSON сохраняют raw Understanding, validation, state before/after, retrieval diagnostics, входы/ответы генерации и SHA исходников.

| Случай | До | Подтверждённый результат после |
|---|---|---|
| Эвотор 6, копия чека по ФД | «Что именно нужно сделать или что сейчас не работает?»; retrieval отсутствовал | Точный approved-путь «Настройки → Обслуживание кассы → Дополнительные операции → Печать документа по номеру», ограничения QR/ФД и атрибуция `evotor-6-receipt-copy.md`. |
| Диадок, статус отправленного УПД | Тот же общий вопрос | Сохранена задача EDO/status; честное отсутствие применимой approved-инструкции для Диадока, без совета по кассовому чеку. Это устранение программного отказа, не закрытый KB gap. |
| БИФИТ Общепит, столы | Тот же общий вопрос | Сохранены root request и маршрут БИФИТ; нет подмены Эвотором или web-booking-инструкцией. Approved coverage отсутствует. |
| Saby, входящий документ | Маршрут уже правильный, полезного evidence нет | Понятное ограничение для Saby; нет фискальной инструкции, нет обещания реально подключённого специалиста. |
| Что такое ОФД | Уже правильное approved-определение | Определение сохранено также после перерыва, новой задачи и сброса диалога. |

Память оценивается отдельно от удержания topic. `memory1`–`memory4` — **отрицательные/промежуточные результаты**, а не успешный gate. [Final resume](final_resume_20261029_live.json) дал следующие результаты:

| Проверка | Фактический результат |
|---|---|
| Продолжение Эвотор 7.3 | Task/model сохраняются; напечатанный отчёт отмечается passed; следующий approved-блок показан. |
| Уже выполненная составная проверка | **FAIL:** все точные факты сохранены, но последний block остаётся unknown и renderer повторяет вопрос о результате. Повтор после узкой правки получает более ранний order=false. |
| Ответ на уточнение сервиса | Платформа ОФД учтена, дан применимый маршрут поиска и параметры ФД/ФП. |
| Платформа ОФД → АТОЛ Онлайн | Task сохраняется, retrieved/final source меняется на ATOL; старая область не выдаётся за текущую. Полнота поиска именно по ФД в ATOL не доказана этим общим журнальным разделом. |
| Новый вопрос об ОФД | Новая task, без переноса проверок прежней диагностики. |
| «Модель не знаю» | Учитывается explicit unknown; вместо повторного вопроса — конкретная граница продолжения. |
| «Новый диалог» | Новый conversation/task; затем правильное определение ОФД. |

Платформа ОФД status и DirectBank сохраняют прежние полезные ответы. Физическая aQsi scanner остаётся без полезной инструкции из-за order=false при найденном релевантном разделе. Дополнительный aQsi Online receipt-search не нашёл применимого evidence; это не названо регрессией ранее успешного случая. Повтор отдельного старого aQsi scanner control в последнем batch не состоялся: batch остановлен на Understanding HTTP400.

## Проверки и отрицательные результаты

- Полный suite на момент первоначального gate: **543 passed, 4 xfailed, 13 warnings**. Добавлено восемь небольших регрессионных примеров, последний — из реального synthetic provider JSON. Прежние safety/model/SQLite/handoff проверки сохранены. В старых mocks добавлен stage; один progress-тест ожидает конкретное ожидание модели вместо общего task_not_ready. Финальный код побайтно совпадает с source hashes `terminal_boundary_20261029_live.json` после отката неподтверждённого переименования.
- Существующий source-scope контроль: **15/15**, read-only Stage3, offline Planner; это не live-метрика.
- Frozen 24: повторён сохранённый raw Understanding + реальный Stage3 + deterministic local Planner; исходные scenario/reason сохранились, case 11 с историческим HTTP 400 не выдан за успешный replay. Изменения ranking после дедупликации query сохранены отдельно.
- [51-case контроль](evaluation51_control.json): 51/51 прежних intent/operation/object/route/analysis_required/query-error; 26 сокращений query только за счёт дублей. Это локальный lexical control, **не 51 успешный LLM-ответ**.
- Повтор Sprint 3 с теми же 206 approved + 8 временными in-memory overlays: положительных final-evidence попаданий 5/6 разрешённых state против исторических 3/6. Диадок/Saby = partial; индекс и approved KB не изменены. Два «cross candidate» в общей метрике относятся к другому кандидату указанного сервиса; запрещённый target final = 0. Сохранённые semantic/KB дефекты перечислены выше.
- `memory2`: HTTP 429 при лимите 8000 TPM; ответ о лимите сохранён, batch остановлен. Пауза harness теперь учитывает фактические rate-limit headers; runtime limiter не отключён.
- `memory3`: HTTP 200 с невалидным JSON Planner и путаница section/unit ID. Strict Planner format добавлен после этого результата.
- `final_live`: HTTP 400 Understanding на БИФИТ; повтор без изменения runtime-кода прошёл. Причина именно этого 400 **не установлена**. В `source_order_contract_20261029_live.json` новый 400 уже диагностирован как **json_validate_failed** в Understanding. Invalid generation не принят за клиентские факты. Стабильность provider не доказана; переименование поля Planner откачено, поскольку его live-вызова не было.
- `terminal_boundary`: ещё два HTTP429 Planner, штатные retries завершились ответом; максимальная latency turn — 21.827 s. Автотесты не подменяют этот отрицательный эксплуатационный результат.
- Попытка глобально нормализовать «фискальный документ» в grounding vocabulary дала регрессии информационного composer и **отклонена**. Оставлена узкая проверка предмета в limitation shortcut.
- Финальное продолжение 28 октября остановилось после БИФИТ и Эвотора 6 из-за выключения компьютера пользователем. 29 октября существующий контейнер Qdrant поднят с прежним volume по прямому разрешению пользователя; Stage3 green/934. Worker до итогового gate не запускался.

Исторический срез до дополнительного продолжения 29.10. Метрики по каждому прогону: [live_metrics.json](live_metrics.json). Всего **104 реальные HTTP попытки, 67 Telegram-equivalent turns**, известный usage **260497 tokens**: 99 HTTP200, 2 HTTP400, 3 HTTP429; среди HTTP200 был один невалидный JSON Planner до strict format. Токены ошибочных ответов неизвестны, а не «бесплатны». Latency отдельных прого́нов указана в JSON; паузы harness/ночной перерыв исключены. 64 HTTP попытки относятся к Understanding, 40 — к Planner/generation, включая retries. Отдельный Composer не требовался достигнутым ветвям: технические шаги копировались из approved source, определения ОФД проходили существующую exact-fact ветку.

Strict JSON format Planner опирается на [официальный контракт Groq Structured Outputs](https://console.groq.com/docs/structured-outputs); валидная JSON-форма не доказывает правильность смысловых флагов, что и показали live-ответы.

## Изменённые файлы и эксплуатационная граница

Runtime: `dialogue_understanding.py`, `dialogue_state.py`, `ai_coordinator.py`, `task_operation_resolver.py`, `procedure_policy.py`, `rag_query.py`, `source_first_service.py`, `llm_client.py`. Повторяемый live harness: [run_telegram_equivalent_live.py](../../scripts/run_telegram_equivalent_live.py). Новых хранилищ, parallel classifier, CRM/handoff delivery или замены архитектуры нет.

Backups обеих SQLite с quick_check=ok, pending=0 и точных 33 файлов прежнего runtime подготовлены в `.local/backups/live-dialogue-recovery-20261028T173151Z/`. SHA сверены с receipt; при восстановлении Git-blob учтён CRLF, а не сделано предположение о совпадении байтов. `.env` SHA сохранён, сам `.env` не менялся/не копировался в отчёт. Есть отдельный snapshot candidate. Production conversations использовались только read-only, тесты пишут только изолированные SQLite. Нет Telegram-отправок агентом, изменения approved KB/Qdrant index, commit/push.

**Промежуточное решение до продолжения 29.10: NO-GO. Новый worker не запущен, активного Telegram PID нет.** Причины: нестабильный переход по результатам составной проверки и сохраняющийся ложный order=false; дополнительно подтверждён provider JSON validation failure Understanding. Следующий конкретный шаг — доказать контракт source order отдельно от client completion и результата составной проверки на сохранённых raw JSON/approved секциях; затем повторить тот же трёхходовый real Groq dialogue. Не обходить gate выставлением passed/true и не продолжать повторы до случайного успеха.

Отсутствующие Saby/Диадок/БИФИТ approved-материалы остаются отдельной редакторской задачей. Эта работа не разрешает автоматически индексировать Sprint 3 drafts. Условный скрипт запуска защищён `pilot_gate.json`; решение NO_GO не допускает его запуска. Этап остановлен с сохранёнными исправлениями, отрицательными результатами и готовыми rollback sources.

## Актуализация после продолжения 29 октября

См. [итог продолжения](continuation_20261029.md) и [воспроизводимый synthetic HTTP400](understanding_provider_repro.json). Сохранены предыдущие неуспехи, полный ход эксперимента с retry и различие между успешным промежуточным прогоном и не завершённым финальным E2E. Текущий gate остаётся NO_GO.
