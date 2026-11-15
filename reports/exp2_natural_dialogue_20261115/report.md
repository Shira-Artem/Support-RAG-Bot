# Experiment 2 — Natural Dialogue & Next Safe Step

Дата: 2026-11-15
Статус: part A in progress; part B not started; общий quality/production gate остаётся NO-GO.

## Цель и ограничения

Проверить, может ли бот продолжить от reducer-owned подтверждённых фактов, неизвестных значений, наблюдений и результатов ProgressLedger, отдельно оценивая готовность искать evidence и достаточность сведений для конкретного технического действия. Part A не должен разрешать действие без утверждённого применимого источника и существующих scope/safety checks. Part B — отдельная последующая проверка одного безопасного read-only шага и в этом checkpoint не включался.

Не менялись approved KB, Qdrant, модель/provider settings, Telegram/production runtime или SQLite. Исключений и regex для названий Диадок/1С не добавляли. Работа выполняется в локальном `main`; feature branch/worktree для разработки не создавались.

## Принятое изменение A1

В `app/ai_coordinator.py` diagnosis gate ранее блокировал retrieval всякий раз, когда короткое описание симптома не удовлетворяло лексическому порогу `specific_enough`, даже если reducer уже держал задачу, наблюдаемую цель/симптом и подтверждённый subject. Теперь `semantic_task_ready` снимает только этот ранний запрет поиска. Маршрут остаётся `technical_action` с обязательным дальнейшим `retrieve_then_apply_independent_scope_and_safety_gates`; изменение не считается подтверждением диагноза, доказательством применимости найденного текста или разрешением выполнять процедуру.

Добавлены две чистые проверки координатора: short symptom + подтверждённая тема допускает evidence search; symptom без подтверждённого subject по-прежнему вызывает уточнение. Текстированные project states не изменяются координатором.

## Проверки

- `.venv\\Scripts\\python.exe -m pytest tests/test_ai_coordinator.py -q` — **10 passed**.
- `.venv\\Scripts\\python.exe -m pytest tests/test_ai_coordinator.py tests/test_source_first_dialogue_contract.py -q` — **59 passed**.
- `scripts/run_telegram_equivalent_live.py`: `py_compile` и `--help` прошли.
- В harness добавлены frozen synthetic scenarios: D01 (3 turns), D03 unknown code (4), D05 aQsi old sale (2), D07 Evotor 7.3 receipt transmission (1), D08 Diadok→1C document visibility (3).
- Добавлен явный `--revision`, чтобы при запуске распакованного baseline снимка результат записывал его реальную source revision, а не SHA родительского checkout. Повторные `py_compile` и `--help` прошли.
- Groq/Qdrant full-pipeline A/B — **ещё не запускался** для Experiment 2.

## Доказательства, ограничения и следующий шаг

### Full-pipeline A/B: A1 baseline vs candidate

Оба прогона были последовательными, синтетическими и прошли через `bot.handle_message` + real Groq GPT-OSS 20B (`openai/gpt-oss-20b`), Stage3 Qdrant `knowledge_stage3_retrieval_20261022` green/934 points, `source_first`, Coordinator enabled и отдельные SQLite. A=`a006ea65e835e070f183ac25ccd39305c1a0e79d`; B=`7cb82ed92ebff8dacf9bbb1beecaafade62cb02c` (A1). Пять сценариев, 13 user turns на вариант. Outputs, SQLite и HTTP traces остались в ignored `.local` и не добавлялись в Git.

| Метрика | A — baseline | B — A1 |
|---|---:|---:|
| HTTP attempts | 19 (18×200, 1×400) | 19 (19×200) |
| Восстановленные/невосстановленные ошибки | один Understanding 400 `json_validate_failed`, автоматическое продолжение | 0 |
| 429 | 0 | 0 |
| Успешные reported tokens, все stages | 49,727 | 56,294 |
| Сумма end-to-end per-turn latency | 75.591 s | 112.047 s |
| Groq Understanding calls | 14 | 13 |
| Planner/Composer calls | 5 | 6 |

Latency включает локальный TPM pacing внутри `handle_message`, а не только сетевой request. Для D03 кандидат занял 47.825 s суммарно при HTTP-попытках без 429; HTTP вызовы Understanding по отдельным ходам заняли примерно 1.4–2.7 s каждый. Это сильно указывает на локальное token pacing, но trace не записывает точное ожидание каждого вызова; считать эти 47.8 s модельным/поисковым latency нельзя.

**Сценарии:** D01 обе версии показали только approved composite check (модель + оплаченный период); после сообщения, что интернет работает, Ledger сохранил статус `asked` — ни одна версия ошибочно не отметила полный check выполненным. A спрашивал результат вместе с точной моделью; B задавал только модель и затем безопасно отклонил неприменимый источник, когда `интернет касса` попало в equipment. Явное подтверждение факта и вопрос о недостающем условии остаются желательны. D03 candidate спрашивал, что не работает (печать/передача данных), и не приписал FN 231/-3975; в отличие от baseline не ушёл в раннюю общую эскалацию на T03/T04. Однако на четырёх ходах повторял один и тот же вопрос, поэтому улучшение ограниченное. D05 не изменился: после повторного поиска старой продажи в aQsi Online бот не предложил уточнить, ищется ли чек одной продажи или отчёт за период; подтверждённой procedure/UI не выдумано. D07 baseline выдал шаг про неверные дату/время, не соответствующий известной проблеме передачи чеков; candidate безопасно задал вопрос вместо такого шага, но вопрос повторял уже известную проблему и не продвинул диагностику. D08 остался пробелом в evidence: обе версии сначала отказывали без focused question; на третьем turn A выбрал соседнюю статью 1С-ЭПД/ЭДО, candidate эскалировал. A1 не изменил D08 outcome: в этих live traces symptom уже был достаточно длинным для прежнего gate; это не опровержение нового короткого-symptom unit contract, а сигнал, что D08 требует другого generic gap-recovery mechanism.

**Решение:** принять A1 только как ограниченное изменение допуска поиска, но **part A остаётся IN PROGRESS / не принят целиком**. Источники/состояния показали полезные безопасные изменения на D03 и D07, отсутствие ложного завершения Ledger на D01, но парный результат не улучшил все ключевые случаи. Следующий кодовый шаг — generic, one-time targeted missing-detail question for typed search tasks such as D05, plus source-gap follow-up grounded in currently known facts for D08; одновременно проверить source/task matching для D07, не разрешая действия. Для D03 устранить повтор вопроса, не принимать неизвестный error code за факт. B, quality gate и production GO остаются закрытыми.

Следующий шаг: внедрить/протестировать вопросы и matching как отдельный A2 checkpoint, затем повторить тот же bounded A/B на том же baseline, модели и Stage3. Не менять KB/Qdrant/provider settings, не включать Part B до измерения A2.
