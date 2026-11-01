# Variant B, B1 — TaskFrame и восстановление задачи

Дата: 01.11.2026. Базовый HEAD: `0910615709edc147ac8a8c07489787f23e6b032a`. На момент offline gate изменения B1 были локальными; позднее пользователь отдельно разрешил commit/push. Работающий Telegram worker не перезапускался. Stage3 Qdrant `knowledge_stage3_retrieval_20261022` прочитан только на чтение (`green`, 934 points); production SQLite, `.env` и approved KB не изменялись. Реальных Groq/Telegram вызовов в B1 нет.

## Причины и граница изменения

Сохранённая [трасса семи production ходов](production_trace_redacted.json) и [аудит](report.md) показывали три независимых потери. В 557/559 raw `general/diagnose` и непризнанный предмет «оператор фискальных данных» проецировались в `error_diagnosis`, поэтому правильная approved статья Эвотор 7.3 отбрасывалась по task mismatch. В 563→565 validated `receipt/diagnose` уже был получен, но reducer сохранял `general/unknown`: `answer_to_clarification` без `expected` принудительно становился `continue`, а новый intent не повышался. В 569 объект ОФД отбрасывался на закрытом словаре; вслед за этим отдельный conceptual evidence gate выбрал нерелевантную aQsi цитату. Последний gate относится к B2 и **в B1 не изменён**.

Изменены `app/dialogue_state.py`, `app/dialogue_understanding.py`, `app/task_operation_resolver.py`, `app/ai_coordinator.py`, `app/rag_query.py`, `app/retrieval_pipeline.py`. Добавлены [детерминированные тесты](../../tests/test_stage_b1_task_frame.py), [replay сохранённых ходов](run_stage_b1_replay.py) и отдельный выход для [holdout runner](run_holdout.py). В двух прежних SQLite replay тестах обновлено ожидаемое имя relation с `continue`/`parameter_update` на сохраняемое `answer_to_clarification`; остальные утверждения по их состоянию и ответам оставлены.

## Контракт до и после

| Ось | До B1 | После B1 |
|---|---|---|
| Тип просьбы | Validated `Understanding.request_type` использовался Coordinator, но не хранился как отдельный признак задачи | `TaskContext.request_type`; `TaskFrame.request_type` принимает validated значение. Старые snapshot получают `unknown`. |
| Предмет, операция, симптом | `intent` нередко трактовался как предмет и task family одновременно; `object` мог быть потерян | `TaskFrame.intent` явно остаётся **legacy domain label**, `subject` берётся из grounded `object`, `operation` и exact-span `symptom` независимы. |
| Сервис/модель и факты | Факты были в `TaskContext`, но service-route facade мог скрыть модель от RAG query | `TaskFrame.entities`, `goals`, `constraints`, `details`, `checks`, `task_fact`, `unknown_facts` — проекция существующего `TaskContext`. Query берёт активные task entities; session history не становится scope новой задачи. |
| Связь и жизнь задачи | `relation=answer_to_clarification` без expected терялась | `TaskFrame` показывает relation, transition, expected slot, `task_id`, closed, analysis_required, revision; reducer сохраняет relation независимо от expected. |

`TaskFrame` — вычисляемое read-only представление, **не второй store**. Единственный mutable источник истины остаётся `TaskContext`; schema version 2 и старые сериализованные диалоги совместимы. `legacy task_category` не сохраняется в TaskFrame: retrieval выводит её из клиентских task facts, `intent`, `operation`, `subject`. Это вспомогательная проекция для ранжирования/старого gate и не доказывает применимость источника. B1 не меняет hard category/evidence admission, approved/SHA, exact identifiers, model/product/safety gates.

## State transitions

| Вход | До | После |
|---|---|---|
| Новый пустой диалог → неполное описание (563) | `task:563/general/unknown`, уточнение | То же; неопределённость честно остаётся. |
| Конкретное validated уточнение (565), expected отсутствует | `continue`, прежний `general/unknown`, root query из 563 | `answer_to_clarification`, тот же `task_id`, `receipt/diagnose`, root task заменён конкретным сообщением, подтверждённые факты и результаты проверок сохранены. |
| Явная новая независимая задача | Новый `task_id` | Новый `task_id` без task-scope прежнего обращения; session history остаётся историей, но не маршрутом. |
| Смена уже подтверждённого service/OFD/software маршрута | Query скрывал часть старого scope через facade, хотя TaskContext мог его удерживать | Устаревшие task-scope entity facts помечаются superseded и удаляются из активной задачи, если не подтверждены в текущем сообщении; session history остаётся. Уточнение маршрута и совместное указание производителя/модели сохраняют их. |
| Неизвестный факт в уточнении | Не должен подтверждать значение | Не перезаписывает точный подтверждённый факт; slot остаётся unknown без выдуманного значения. |

Имя «оператор фискальных данных» и его падежи нормализуются через общий registry `OBJECTS` и единый matcher для именованных существительных. Короткие идентификаторы `ФН`, `ОФД`, `УПД`, `ККТ` и налоговые аббревиатуры требуют точного токена; `ФД` не становится ФН. Отдельный предмет `ОФД` не означает «чек»: прежняя широкая alias `оператор → чек` удалена. Resolver определяет диагностическую передачу в ОФД из grounded предмета ОФД, контекста кассы/продаж и неисправности, исключая печать/возврат и простое чтение списка. Он не утверждает vendor/model и не разрешает процедуру.

## Replay и отрицательные контроли

[Production replay](stage_b1_production_replay.json) заново валидирует сохранённый raw Understanding, применяет reducer, сохраняет **полный TaskFrame и RAG query**, затем сравнивает retrieval на том же исходном query и фиксированном read-only списке Stage3 hits. Это проверка маршрута/выбора кандидата, **не финального ответа**.

| Ход | Baseline на том же запросе | B1 на тех же hits |
|---|---|---|
| 557 | `error_diagnosis`, gold отвергнут | `receipt_transmission`, gold selected, `partial/sufficient=true` |
| 559 | `error_diagnosis`, gold отвергнут | `receipt_transmission`, gold selected, `partial/sufficient=true` |
| 561 | Gold selected | Gold selected, успешная ветка сохранена |
| 563→565 | 563 уточняет; 565 `general/unknown`, gold `task_unresolved` | 563 остаётся неопределённым; 565 повышается до `receipt/diagnose`, gold selected, `partial/sufficient=true` |
| 569 | `object=null` | `subject=ОФД`, category `ofd_connection`; финальный conceptual gate не проверялся как решённый |

[Замороженный независимый holdout](holdout_cases.jsonl) содержит 48 случаев, из них 24 с approved gold. [Baseline](holdout_metrics.json) → [B1](stage_b1_holdout_metrics.json): query **48/48 → 48/48**, gold raw **24/24 → 24/24**, gold selected **18/24 → 18/24**, у gaps/negative любой selected **5/24 → 4/24**. У EV01 lexical `intent` стал `unknown` после удаления широкого `оператор → чек`, однако gold всё равно selected. AQ06 перестал выбирать соседний источник; это selection-only, не оценка ответа. Шесть потерь gold остаются за B2 gate/operation coverage. Сорок восемь случаев не являются репрезентативной оценкой трафика и не проверяют генерацию.

Независимые state/reducer контроли проверили падежи ОФД, отдельные ФН/ФД/чек/кассу, две новые формулировки диагностической передачи, печать и возврат как другую операцию, Эвотор 6, смену сервиса/модели, новый диалог, неизвестный факт, несколько последовательных проверок, загрузку старого snapshot и полный query. Существующие source-scope и SQLite replay тесты прошли. Исправление применимо ко всем направлениям: promotion использует общие оси `intent/operation/relation` и grounded Facts без имени бренда; route reset работает по слотам сервиса, ОФД, ПО и модели; object matcher использует общий словарь, а не список test sentences. Специфическое правило ОФД ограничено только доменной классификацией передачи, не reducer и не evidence gate.

## Проверка, ограничения и решение

Полный `python -m pytest -q`: **577 passed, 4 xfailed, 13 warnings** на Python 3.14. Промежуточный прогон выявил регрессии от слишком широкого применения resolver к lexical analyzer и ошибочного исключения краткого слова «чек» из морфологии; оба механизма сужены, повторные профильные проверки прошли. Исторические relation assertions обновлены согласно явному B1 контракту. Финальный полный прогон выполнен после этих исправлений.

**B1 offline GO** по критериям задачи: concrete clarification больше не застревает, факты и границы новой задачи сохранены, имена ОФД нормализуются, frozen replay выбирает gold, отрицательные контроли и полный suite проходят. Это **не** quality GO для Telegram/production. B1 не устраняет нерелевантный финальный выбор секции 569, шесть holdout gold losses, provider HTTP 400/429 и KB gaps. Для B2 требуется отдельное решение владельца; worker и approved KB до него остаются прежними.
