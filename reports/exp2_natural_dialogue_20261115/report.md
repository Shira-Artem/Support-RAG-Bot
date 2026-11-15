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

**Решение по A1:** принять A1 только как ограниченное изменение допуска поиска, но **part A остаётся IN PROGRESS / не принят целиком**. Первый A/B показал отсутствие ложного завершения Ledger на D01 и защищённое уточнение на D03/D07; D05/D08 остались без полезного первого уточнения. Следующий шаг на тот момент — ограниченные вопросы A2, source/task matching D07, повторный вопрос D03 и явное acknowledgement D01. B, quality gate и production GO оставались закрытыми.

Историческая note: сначала предполагался commit/push A2 и повтор A/B. A2 уже прошёл offline и candidate-only full pipeline; актуальный следующий шаг зафиксирован ниже как A3 source/task mapping.

## A2 offline checkpoint — targeted source-gap questions

`_missing_support_detail` теперь возвращает ограниченный missing-detail question для typed search без parameters, когда подтверждён task entity: спрашивает, нужна ли конкретная запись/документ или сводка за период, и дату записи. Для технической задачи с симптомом, типом «документ», подтверждёнными service+software и отсутствующим object задаётся один вопрос только о типе документа. Имена конкретных систем в production logic не используются. Существующий receipt-only fallback «за какой период или дату» сохранён; первая регрессия в тесте `receipt/search` без entities поймала его случайное сужение, после восстановления regression suite прошёл.

Проверки после A2: `tests/test_ai_coordinator.py` + `tests/test_source_first_dialogue_contract.py` — **62 passed**. Расширенный набор с `tests/test_b1_3b_diagnostic_continuation.py` и `tests/test_telegram_pilot_sqlite_replay.py` — **131 passed / 4 historical xfailed**. Эти тесты подтверждают структурный допуск вопроса, ограничение повторного intake и сохранение legacy receipt/date path.

## A2 full-pipeline candidate follow-up

Candidate `7d7ad8505120f59e7c728716a5d4b012149c8112` повторил те же 13 synthetic turns, Groq model и Stage3; изолированные DB/traces. 19/19 HTTP 200, 0 provider errors/429, **53,944 reported tokens**, суммарная per-turn latency **110.927 s**. Прямое сравнение A1 candidate `7cb82ed` → A2: D05 на первом ходу задал фокусный вопрос «документ по одной продаже или сводный отчёт за период»; после непопадания следующего ответа ограниченно вернулся к отсутствию approved-инструкции. D08 на первом ходе задал один вопрос о типе документа; последующий ответ «в Диадок отображается» не разрешил evidence gap, и следующий ход выбрал безопасный уточняющий раздел 1С-ЭПД/ЭДО; это не решает пользовательскую задачу и остаётся за пределами подтверждённого источника. D01 остался без явного подтверждения факта «интернет работает» и безопасно не завершил составную проверку. D03 не приписывал клиенту код, но один запуск потерял task continuity на T02, эскалировал на T03 и вновь задал тот же уточняющий вопрос на T04; генерация Understanding изменчива. D07 снова выбрал `evotor/settings/time-mismatch-first-checks.md` и показал сообщения/условия для кода 3922, хотя запрос касается непередаваемых чеков. В diagnostics ожидаемая категория была `error_diagnosis`, из-за чего подходящий `receipt_transmission` документ `evotor-7-3-ofd-connection` был отклонён с `task_mismatch`; это прямой evidence о дефекте source/task classification. A2 не менял retrieval matching и не устранил его.

**Решение:** A2 улучшает первичное missing-detail clarification на D05/D08, но part A остаётся открыта. D07 mismatched source — блокирующий пункт до принятия A2 в целом. Следующий шаг A3: исправить общий task-family mapping для задачи о непередающихся чеках и проверить hard negative для error-diagnosis задач; сохранить существующую source/scope/code/safety границу. Затем targeted regressions + повтор того же live case набора. Part B не запускать.

## A3 offline checkpoint — colloquial receipt-transmission category

В `task_operation_resolver.resolve_task_operation` добавлен общий вариант `не уход*` для запросов, которые также подтверждают чек или документ. Явный code/error classification находится раньше и остаётся приоритетным; продуктовые имена не участвуют. Такой пробел объяснял D07: state имел `intent=device`, `operation=diagnose`, но пользовательское «не уходят чеки» не совпадало с передачными синонимами, поэтому retrieval проецировал `error_diagnosis`; подходящий Evotor 7.3 `receipt_transmission` source отклонялся как category mismatch.

Добавлен positive regression для colloquial receipt delivery symptom в resolver и state task-category projection и hard negative: явная ошибка ФН 235 по-прежнему остаётся `error_diagnosis`. Проверки: `test_task_operation_resolver.py`, `test_b2_2c_quality_contracts.py`, `test_retrieval_pipeline.py`, `test_metadata_retrieval_routing_v3.py`, `test_ai_coordinator.py`, `test_source_first_dialogue_contract.py` — **121 passed**. A3 live-повтор ещё не выполнен; подходящий source, selected source и клиентский ответ нужно подтвердить на Stage3 после публикации.

## A3 live D07 slice and A3b offline checkpoint

One-turn candidate `cb974bce5e6ca914425eb473ea396add8ba072a0` confirmed the new expected category `receipt_transmission`, but the exact 7.3 source still failed `subtask_anchor_uncovered`; a broader OFD article was selected and asked for model/paid-period. One turn: 5,505 reported tokens, 9.351 s, provider errors/429=0.

A3b keeps the existing category/scope/operation checks and adds one cross-phrase semantic anchor when both the query and a candidate contain a receipt/document object and a failed-delivery predicate. It maps “не уходят чеки” to approved-source wording such as “неотправленные документы”; it does not relax the task-family mismatch, exact model, or error-code gates. Added an end-to-end synthetic retrieval regression: the exact Evotor 7.3 transmission article is eligible while the clock-mismatch article remains rejected. Four retrieval/routing suites — **60 passed**. A3b live validation is pending; do not treat this test as proof that the real D07 candidate is now selected.


## 2026-11-15 — Experiment 2 part A: A3b live D07 and provider-limit interruption

The bounded one-turn full-pipeline D07 run on `6728d57c3e50a49f8bf9659387bccd58ed6e9462` selected the exact approved `data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md` section “Что проверить сначала”. The answer gave the source-backed first diagnostic step: under the administrator role, open “Настройки → Обслуживание кассы → Диагностика” and print the diagnostic report. The run used synthetic input, `bot.handle_message`, Groq `openai/gpt-oss-20b`, read-only Stage3 collection `knowledge_stage3_retrieval_20261022` (934 points), and isolated SQLite. Both HTTP calls returned 200; 5,708 reported tokens; no provider errors. This confirms exact source retrieval and the existing runtime’s first-step answer for this one D07 turn. It does **not** count as a separate implementation or completion of Experiment 2 part B.

A subsequent bounded continuation of the remaining frozen cases saved D01 T01 and T02, then stopped on Groq HTTP 429 at D01 T02. The artifact records 3 successful HTTP calls and 1 rate-limit response; 8,286 successful reported tokens; provider message: daily token budget reached, retry after approximately 7m29s. The harness preserved the two turns and stopped on the provider error. No further live calls were made. D01’s first answer was the broader OFD model/paid-period check; the second answer correctly reported the model limit. D03, D05, and D08 were not run on A3b in this continuation. The prior A1/A2 outcomes remain historical and are not evidence of A3b behavior.

**Status/next step:** A3b exact-source D07 slice is live-confirmed, but Experiment 2 part A remains IN PROGRESS. D01 acknowledgement/follow-up and D03 repeated clarification remain unresolved; the remaining A3b frozen cases are untested because of the provider limit. Part B remains NOT STARTED; overall quality/production remains NO-GO. Continue useful offline review and regressions while the provider budget resets; resume only a bounded live continuation after the provider’s stated retry window, stop again on any 429, then update this record with actual outcomes. No live traces or private artifacts are tracked.


## 2026-11-15 — Experiment 2 part A: D03 follow-up candidate and continued Groq limit

The A3b frozen-suite retry was attempted after the provider’s first retry estimate. At 12:22:20 UTC Groq returned HTTP 429 on the Planner during D01 T01, again for the daily token limit; the new estimate was approximately 10m02s. The harness saved the turn and stopped. No D03/D05/D08 turns ran on this attempt, and no more model requests were made. The earlier A3b D07 exact-source slice remains the only successful live check on that revision.

Offline review of A1/A2 D03 traces isolated a continuation defect: after the user supplied model and intermittency, Planner returned `clarify` with no safe source, but SourceFirst immediately escalated despite a known symptom and no confirmed error code. The same initial “what stopped working?” question also recurred after the user said the code was unknown. The current candidate changes the existing clarification path to ask one generic observable-result question in that case (which action fails and what result the user sees); it does not select an unsupported source or attribute an error code. Repeated unknown-code clarification uses that focused follow-up instead of the initial wording.

**Offline verification:** the targeted D03 planner-clarification regression and repeat-question regression pass. Broader `test_source_first_dialogue_contract.py`, `test_ai_coordinator.py`, `test_retrieval_pipeline.py`, `test_metadata_retrieval_routing_v3.py`, and `test_telegram_pilot_sqlite_replay.py`: **118 passed, 4 historical xfailed**. Live candidate validation remains pending because the provider returned another 429. Part A remains IN PROGRESS; part B remains NOT STARTED; overall quality/production remains NO-GO.


## 2026-11-15 — Experiment 2 part A: D01 partial network result and third Groq limit

The next frozen-suite attempt started after the second retry estimate. At 12:33:41 UTC Groq again returned HTTP 429 during D01 T01 (daily-token dimension; retry estimate approximately 5m23s). The harness saved that turn and stopped; D03/D05/D08 were not reached. No additional live calls have been made. The three post-A3b attempts show this is still a provider quota block, not a behavioral result for the candidate.

A1/A2 D01 trace review showed that “В интернет касса выходит” was incorrectly projected as equipment model `интернет касса`; that then caused a false model-scope mismatch. The offline candidate now treats generic connection wording as not an exact equipment model. When a positive network-access fact is already present in the reducer’s details and a model clarification is needed, the existing model-clarification response acknowledges the result and asks for the model. This does not mark the compound source check passed: the test confirms its ProgressLedger status remains `asked`. The change is generic and does not introduce service-name exceptions.

**Offline verification:** targeted D01 and D03 clarification tests pass. The affected dialogue, coordinator, retrieval, routing, and SQLite replay suites: **119 passed, 4 historical xfailed**. A3b D07 exact-source live slice remains confirmed; this D01/D03 candidate is offline-only until Groq quota permits the bounded frozen continuation. Part A IN PROGRESS; part B NOT STARTED; overall quality/production NO-GO.


## 2026-11-15 — Experiment 2 part A: fourth bounded retry remains quota-limited

The next bounded A5 continuation ran at 12:39 UTC after the provider’s preceding retry estimate. Groq accepted Understanding (2,041 reported tokens) and rejected Planner with HTTP 429, TPD used 197,340 of 200,000 and 2,857 tokens requested; retry estimate 1m25s. The harness saved D01 T01 and stopped. This leaves less available budget than a full pipeline turn requires (the observed turn had a 2,041-token Understanding call plus the rejected Planner request), so no immediate retry is planned. D03/D05/D08 remain untested on the D01/D03 offline candidate. No additional live calls were made after this response.

The current offline candidate has D01 and D03 targeted regressions and the five affected suites pass: **119 passed, 4 historical xfailed**. This does not substitute for full-pipeline live validation. The most recent successful live validation remains the isolated A3b D07 exact-source turn. Part A IN PROGRESS; part B NOT STARTED; overall quality/production NO-GO. Resume the frozen suite only when the provider has enough available daily tokens for a complete Understanding + Planner turn, and stop again on any 429.
