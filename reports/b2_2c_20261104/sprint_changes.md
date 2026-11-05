# B2.2c — доказанные причины и изменения

Изменения начаты **после** полного baseline24/30 на одном неизменённом runtime SHA. [Merged baseline](baseline_complete.json), [ручная оценка](baseline_evaluation_complete.json), полные trace-файлы связаны из каждой строки. Основные 24: A2 / B2 / C0 / D3 / E3 / F12 / G2 / H0; одна дополнительная попытка m04 HTTP400 сохранена отдельно, повтор на прежнем коде завершён.

## R1. Разные проверки document model scope расходились

**Evidence:** k01/k04 теряли manufacturer-wide источники до pipeline; k02 нашёл paper-print, но модель класса физической ККТ не прошла exact entity matcher. k03 облачный мониторинг отвергнут из-за модели клиентского оборудования. [Предыдущая изоляция](fallback_predicate_isolation.json) и [контрфактический raw retrieval](retrieval_counterfactual_extended.json) — только offline; новое подтверждение в полном LIVE baseline.

**Изменение:** общая направленная проверка `matches_model_scope` и распознавание явно указанного физического класса в `scope_policy.py`. Отсутствие модели в metadata означает отсутствие модельного требования, а не автоматическую применимость: независимые manufacturer/service/operation/SHA/safety gates сохранены. Generic physical class требует правильный manufacturer и не совместим с Online/cloud. Конкретные обозначения, числовые версии и suffix `lite`/`Ф` остаются конкретными, даже при соседней категории sales. Облачный документ требует подтверждённый сервис, а не модель физического аппарата. Ранний retrieval, unresolved fallback, техническая применимость и финальный model guard используют согласованный смысл.

**Отрицательные результаты:** первый вариант subset-сравнения ошибочно сближал 6 и 6 lite; полный pytest это выявил. Исправлено на сравнение полного нормализованного обозначения с реестровыми aliases производителя. Первый вариант расширения hardware scope нарушил unknown-vs-conflict taxonomy облачных сервисов; различие восстановлено, физический производитель по-прежнему не подтверждает Online. Безусловный model=True не внедрён. Роли equipment/reference/peripheral не менялись, B2.2b.3 OPEN.

## R2. Грубая категория подавляла более точное evidence предмета/операции

**Evidence:** k03 gold cash_list содержит явную inspect_fiscal_drive, но был отвергнут как другая категория; o01 namespace ФЛК проиграл общему receipt/OFD diagnosis; b01 отражение банковского возврата в 1С стало выдачей возврата покупателю; e02 подключение ЭДО проиграло generic 1С integration; s02 check+упоминание чека без передачи стало receipt_transmission.

**Изменение:** категория может согласоваться через **явный reviewed operation match**, без допуска unknown/mismatch. Этот контракт одинаков на admission, sibling expansion и coherent evidence selection. Точные product/model/service и safety gates независимы. Типизированный namespace ФЛК имеет приоритет над общим словарём ОФД. Accounting-return domain и ЭДО connection имеют приоритет перед общими refund/integration rules. Сам receipt+check без положительного признака передачи больше не означает transmission failure.

**Отрицательный результат:** слишком ранний общий accounting guard лишил старый случай пропавшего банковского счёта diagnose. Guard ограничен реальным пересечением предметов — accounting return; остальные банковские диагностические правила сохранены. Операция архивации, general HTTP fallback и другие неподтверждённые mappings не исправлялись точными фразами под baseline.

## R3. Частичное evidence и пошаговый diagnostic режим скрывали полезную инструкцию

**Evidence:** e01/2 reset-password имеет approved безопасный порядок, но partial metadata блокировала весь ответ. s01/1 add-user имеет full reviewed coverage, однако само наличие generic goal ошибочно объявлялось требованием неизвестных прав. В промежуточном AFTER k02 нужная статья вернулась, но был выдан только первый описательный пункт без допечатки и предупреждения о дубле.

**Изменение:** generic goal не означает named-role/privilege requirement; реальные permission clauses и change_permissions остаются отдельными ограничителями. Bounded partial access допускается к существующему Planner только при coherent approved access evidence и исключительно workflow-level неполноте; права/именная роль не обходятся. Передаются coverage/missing flags; ответ явно помечает неполноту. Полный проверенный порядок how-to не обрезается до первого diagnostic unit; диагностические turns, preflight при неизвестной модели и несовместимые per-unit model branches сохраняют одношаговый режим. Полный текст всё равно проходит SHA, section, scope, source-order и safety gates. Progress записывает только реально показанные units и не приписывает выполнение клиенту.

**Проверки:** новые общие positive/negative contracts в `tests/test_b2_2c_quality_contracts.py`; существующие model/scope, operation, memory/source-order тесты. Промежуточные неудачные результаты не удалены: `profile_after_initial.log`, `profile_after_v2.log`, `full_pytest_after.log`, `b22c_after_live.json`. [Профильная коррекция](profile_after_v3.log):170 passed; финальный полный suite и реальные AFTER/holdout оцениваются отдельно.

## Сохраняемые ограничения

B2.2b.3 роли; потеря route при смене подзадачи; отсутствие прямого доказательства relevance у соседнего точного факта; Planner может отказать из-за интерпретации order; общие объяснения с HTTP могут ложно считаться именованным сервисом; известные KB gaps и реальные 400. Эти механизмы не объявлены закрытыми. Замороженный holdout не использовался для выбора или правки кандидатов.


## Финал 05.11.2026

Основной AFTER11/17 завершён; k03 остался F из-за fallback raw model comparison при raw intent=device. Общая ScopeAssessment с исключением подтверждённого cloud service исправила этот путь. Последующий полный тест выявил известный wrong-model metadata случай без category/manufacturer: одна только assessment.mismatches была недостаточной. Добавлен explicit model conflict guard с cloud exception. Это исправление основано на существующем отрицательном тесте, не на holdout вопросах; holdout не использовался для настройки ответов. Неудачный `full_pytest_release.log` сохранён.

Финальный `full_pytest_final_security.log`:702 passed/4 xfailed/14 warnings; `profile_final_security.log`:180 passed. Финальный holdout12/13 и controls3 используют одинаковые release hashes34 source файлов. k03=A записан отдельно; первичный F не заменён. Оба негативных controls дали безопасные отказы. Holdout A3/B1/E1/F5/G2, с раскрытой ошибкой h03-rubric; вывод NO-GO. Исторический первый holdout не дополнительная независимая выборка. Детали: [итог](final_report.md), [оценки](quality_final_summary.json), [integrity](release_integrity_20261105.json). Дальнейших runtime изменений после финальных проверок нет.
