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
- Groq/Qdrant full-pipeline A/B — **ещё не запускался** для Experiment 2.

## Доказательства, ограничения и следующий шаг

Текущее изменение — ограниченный offline checkpoint. В реальном full pipeline ещё надо проверить, что Understanding приводит D08-like input к reducer state, который использует допуск `semantic_task_ready`; также нужны frozen baseline/candidate сценарии D01, D03-T03, D05, D07 и D08, SQLite reopen, источники, quality/safety, provider usage и latency. Уточнение D01 обязано учитывать «интернет работает» как частичное наблюдение и не помечать составную проверку завершённой. Для D03 неизвестный код должен оставаться неизвестным. Для D05 нельзя выдумывать элементы интерфейса. D07 требует сначала проверить source/task matching. Part B не начинать до измерения/решения по part A.

Следующий шаг: добавить недостающие bounded synthetic scenarios в существующий live harness, не менять модель/коллекцию; затем выполнить последовательные frozen baseline/candidate прогоны с изолированными SQLite и теми же параметрами Groq/Stage3. Результаты и следующий кодовый checkpoint будут добавлены в этот отчёт после проверки.
