# B2.2c — LIVE Quality & Knowledge Coverage Sprint: итог

05.11.2026. **Исполнение sprint DONE; общий B2 quality gate FAIL, B2.3 и production NO-GO.** Выполнены исходные24 сценария/30 сообщений, реальные повторные проверки11/17, отдельный holdout12/13 и финальные3 scope-контроля. На выбранных повторных сценариях полных решений стало4 вместо0; независимый holdout остаётся слабым. Это локальный кандидат, а не разрешение пилота или production.

## Итог качества

Каждый многоходовый случай учитывается один раз с оценкой всего обращения. A не объединяется с B/C/D. Ручные оценки и причины доступны в JSON/CSV; отсутствие H в завершённой основной выборке не стирает исторические API failures.

| Категория | Baseline24 | Те же11 BEFORE | Primary AFTER11 | Holdout12 |
|---|---:|---:|---:|---:|
| A — полный полезный ответ | 2 | 0 | 4 | 3* |
| B — частичный полезный ответ | 2 | 0 | 1 | 1 |
| C — необходимое уточнение | 0 | 0 | 0 | 0 |
| D — обоснованный gap / граница | 3 | 0 | 0 | 0 |
| E — ложное уточнение | 3 | 1 | 2 | 1 |
| F — ложный отказ | 12 | 9 | 3 | 5 |
| G — неверный / нерелевантный ответ | 2 | 1 | 1 | 2 |
| H — технически незавершённый | 0 | 0 | 0 | 0 |

Baseline A-only:2/24=8,3%; на20 с фактическим full/partial approved покрытием2/20=10%. Из знаменателя исключены e03/e04 (реальные локальные gaps), s04 (персональная оплата недоступна статической KB) и o04 (ошибочный preflight gold). Holdout:3/12=25% полных ответов; частичный B отдельно1/12. Все12 имеют хотя бы частичное approved покрытие. Выбранные11 AFTER — диагностика исправлений, не несмещённая оценка общего прироста. Изменение состава выборки не сравнивать как общий процент улучшения.

* h03: ошибка первоначальной рубрики, а не бота: ФЛК508 относится к сумме чека/позициям, сохранённый approved источник это подтверждает; time-item исходного минимума ошибочен. A поставлена по source-consistent ответу с раскрытием [поправки](holdout_h03_rubric_correction.json). Если исключить h03, полных2/11; NO-GO сохраняется. Вопросы и первоначальные минимумы не переписаны. Для o04 [отдельно раскрыта ошибка coverage-аудита](kb_o04_coverage_correction.json): статья изменения номера ФН не доказывает read-only просмотр; фактический G сохранён.

Походовые оценки: baseline30 = A2/B2/C0/D3/E4/F17/G2/H0; AFTER17 = A7/B2/C0/D1/E2/F4/G1/H0; holdout13 = A3/B1/C0/D0/E1/F6/G2/H0. Они не являются дополнительными независимыми обращениями.

## Что изменено и чем подтверждено

1. **R1: единая применимость модели/сервиса.** Manufacturer-wide `model=null` и generic physical класс больше не теряются ранним фильтром; scope направленный, физическая касса и Online не объединяются, конкретные модели сохраняют строгие различия. Общая оценка применяется и в unresolved fallback. k02 получил полный порядок допечатки с предупреждением не создавать второй чек; k04 — объяснение ФН212. Последний повтор k03 на финальном коде дал правильный approved маршрут мониторинга ФН.
2. **R2: операция и предмет запроса важнее грубой категории.** Только явный reviewed operation match допускает переход через coarse category; неизвестная операция и mismatch не обходятся. Разведены namespace ФЛК и обычный OFD, бухгалтерский возврат и кассовый refund, подключение ЭДО и generic integration, проверка статуса и transmission failure. e02/s02 стали A, b01 первый ход стал A, но продолжение остаётся F.
3. **R3: использовать допустимое evidence без лишнего усечения.** Generic goal не считается запросом конкретной роли. Подтверждённый полный how-to сохраняет порядок и warnings; ограниченное partial access evidence может дать только подтверждённые шаги с явной границей неполноты через существующий Planner. В e01/2 получены полезные password-reset шаги, s01/1 — создание пользователя; целые диалоги ещё не A из-за уточнений/потери route.

Изменены шесть runtime файлов: scope_policy, retrieval, procedure_policy, retrieval_pipeline, task_operation_resolver, source_first_service. Новые14 контрактных тестов покрывают положительные и отрицательные границы. Детали, неудачные кандидаты и причины отказа: [sprint_changes.md](sprint_changes.md). [Причинная матрица всех24 и holdout12](causal_matrix_final.md), [построчное BEFORE/AFTER](quality_final_summary.json).

**Версии не смешаны:** primary AFTER11/17 записан до последнего усиления fallback scope; k03 там F и таким остаётся. После исправления на основании уже существующего отрицательного теста (не ответа holdout) финальные holdout и controls проведены на одном runtime receipt34 source hashes. k03=A записан отдельно, не подменяет primary AFTER. n01 (Эвотор10 против инструкции6) и n02 (aQsi Online против физического USB) завершились безопасными отказами; это end-to-end safety PASS, не доказательство прохождения каждого внутреннего gate. [Оценка controls](controls_evaluation.json).

## Независимый holdout и открытые проблемы

h01/h02/h05/h07/h08 — ложные отказы при существующем approved evidence; h09 — ложное уточнение; h04 — только первый шаг вместо полного результата. h06 даёт соседний факт об акте сверки вместо действий. h10 отвечает фактом о добавлении токена, пропуская вопрос о prerequisites и возможности прислать секрет боту. Это G и **safety-critical omission**: предупреждение не передавать токен отсутствует. Явных опасных инструкций в оценённых ответах не обнаружено, но это не означает safety GO. m01/2 в AFTER также даёт нерелевантную рекомендацию о коррекции вместо ответа про маркировку.

Продолжения b01/s01 теряют нужный product/task route. В k01 после полезного первого ответа следующее уточнение избыточно вместо конкретного остаточного условия. B2.2b.3 equipment/reference/peripheral roles остаётся OPEN; этот sprint его не закрывает. Ручная оценка relevance содержит суждение; выборки малы и синтетические, не production обращения. General-knowledge ответы не засчитывались как KB: модельных общих ответов, решивших эти выборки без approved источников, не выявлено.

## KB audit и подготовленные материалы

Проверены269 карточек:206 approved/63 draft. [Матрица13 тем](kb_gap_matrix.csv) различает реальные gaps, partial coverage и runtime losses. FN234, aQsi paper-print, scanner/Hub и процедурный DirectBank уже покрыты хотя бы частично: дублирующие статьи вместо исправления pipeline не добавлялись.

Подготовлены5 локальных материалов с native metadata `status=draft`, `verified_at=null`, official source_url: [Эвотор7.3 — копия чека](kb_drafts/evotor/evotor-7-3-receipt-copy.md), [Диадок — ожидание аннулирования](kb_drafts/diadoc/pending-revocation.md), [Saby — ошибочная обработка](kb_drafts/saby/incorrect-processing.md), [DirectBank — определение](kb_drafts/1c/directbank-definition.md), [расширение расписания](kb_drafts/1c/directbank-auto-schedule-extension.md). Это не пять полностью готовых процедур: область и недостаток SME evidence явно описаны. Все5 читаются настоящими DocumentLoader/Chunker, по3 chunks. Drafts лежат вне основной KB и не участвовали в LIVE retrieval. [Предложения metadata и недостающий read-only FN материал](kb_metadata_proposals.md). БИФИТ остаётся backlog: достаточной primary документации нет, шаги не выдумывались.

## Реальность выполнения, квоты и сохранность

[Протокол заморозки](protocol.md): baseline v2 SHA `2695395071ed440550abd28c0bb853058a3846c6804602d792585771e92b37cc`,24/30,6 направлений,6 многоходовых. Поправка семантического дубля до запуска b01 раскрыта с сохранением v1. [Holdout frozen](holdout_frozen.json) содержит12 независимых от baseline тем; повтор первого holdout после security correction не создаёт ещё12 новых случаев. Его первоначальный trace сохранён.

Вызван настоящий `bot.handle_message`, Groq `openai/gpt-oss-20b`, реальный Stage3 и SQLite. Mock касается Telegram transport. Qdrant wrapper read-only, worker и отправка клиентам не запускались. Тестовые БД изолированы; reopen сравнивает state, quick_check106 файлов/checkpoints=ok. [Итоговая сохранность](release_integrity_20261105.json):269 KB и текущая `.env` неизменны агентом; пользователь обновил `.env` до возобновления, это раскрыто, секреты не выводились. Stage3 green934, payload digest неизменен;34 source hashes совпадают с финальными holdout/controls. Production SQLite не открывалась этой проверкой и не использовалась harness.

[Счётчик всех попыток](live_run_inventory_final.json):88 handle_message attempts с повторами;127 HTTP =122×200,3×429,2×400;278408 подтверждённых tokens, usage пяти failed responses неизвестен. Retry-After соблюдены, смены ключа/организации для обхода квот или снижения completion allowance не было. Исторические429 и400 сохранены отдельно; основной baseline после одного failed m04 был завершён повтором на неизменённом коде. После user-updated доступа блокировки квотой нет. HTTP400/schema failures остаются риском и не названы исправленными. Последние holdout/control25 HTTP все200.

## Проверки и решение

Финальный полный pytest: **702 passed /4 xfailed /14 warnings**,216,87с — [лог](full_pytest_final_security.log). Финальный профиль: **180 passed**,14,25с — [лог](profile_final_security.log). Ранние неудачные full/profile логи сохранены; особенно финальная до-hardening проверка с1 failed не скрыта: известный wrong-model отрицательный контракт потребовал дополнительной explicit conflict проверки. После неё выполнены финальные тесты, holdout и controls. SHA/diff и неизменность защищённых материалов проверены отдельно.

**Рекомендация: к B2.3 пока не переходить.** Следующий конкретный приоритет внутри B2: диагностировать на уже сохранённых h06/h10/m01 границу «ответ соответствует всем частям вопроса» в существующем Coordinator/Planner и сохранение product/task route в b01/s01 continuation. Требуются общие контракты relevance, multi-goal и secret-sharing boundary, затем новый заранее замороженный независимый holdout. Текущий12 уже использован и для будущего эксперимента будет regression set. Это план, не начатая новая фаза. KB drafts — на SME review отдельно. Commit/push, approved/index changes, Telegram pilot и production GO не выполнялись.

Артефакты: [полный baseline](baseline_complete.json), [его оценки](baseline_evaluation_complete.json), [primary AFTER trace](b22c_after_final_live.json), [AFTER оценки](after_primary_evaluation.json), [финальный holdout trace](b22c_holdout_final_live.json), [holdout оценки](holdout_final_evaluation.json), [финальный runtime receipt](release_runtime_receipt.json).
