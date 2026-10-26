# P1 Semantic Evidence Selector: диагностическое продолжение

Дата: 2026-10-26. **B2: NO-GO, feature flag остаётся выключенным.** Этот эксперимент оценивает следующий bounded Selector pass на сохранённых Understanding и Qdrant evidence после незавершённого A/B. Prompt не менялся.

## Проверяемые критерии

Полезность оценивалась человеком отдельно от provenance и safety:

- D1.2 должен объяснить роль ОФД как оператора.
- D1.3 должен объяснить назначение ОФД для приёма/обработки/передачи фискальных документов, а не договор/тариф.
- D3.1 должен показать маршрут поиска чека в подтверждённой Платформе ОФД.
- D3.2 должен сохранить задачу поиска и объяснить период прошлого месяца через даты пробития.

Полный успех означает полезный ответ на каждый ход, корректную привязку к evidence и прохождение локальных проверок. Разные ответы и буквальная цитата отдельно не засчитываются.

## Изменения диагностики и regression

`GenerationError`/`Generation` теперь сохраняют latency и фазу; HTTP failures дополнительно сохраняют status, bounded provider type/code/param, Retry-After, schema-error category, request id и provider-reported usage. Полный response body не сохраняется, секреты и prompt в diagnostic поля не копируются. Error usage остаётся `null`, если провайдер не сообщил токены; он не превращается в ноль. Никаких автоматических повторов нет. Selector response schema error отличим от provider HTTP error.

Трассировщик [p1_semantic_selector_diagnostic.py](../../scripts/p1_semantic_selector_diagnostic.py) использует только сохранённые Understanding, task state и evidence units; делает read-only `get_collection`, не вызывает Understanding/retrieval и жёстко ограничивает Decision calls четырьмя. Сохранённые [DEV cassette](p1_semantic_selector_dev_cassettes_20261026.json) и [HOLDOUT cassette](p1_semantic_selector_holdout_cassettes_20261026.json) разнесены до нового live pass. HOLDOUT прошёл оценку без prompt tuning; prompt остался прежним.

Регрессия на сохранённом D3 evidence выбирает несколько совместимых sentence IDs, отдаёт их в исходном section/position порядке даже при четырёх перестановках массива units и при обратном порядке IDs от селектора. Stable ID не зависит от позиции кандидата в входном массиве. Для procedural/interface evidence сохраняется цельный блок с порядком/условиями; комбинация такого блока с detached sentence отвергается.

## Предыдущий `GenerationError`

Причину **D1.3 GenerationError в исходном A/B восстановить нельзя**. Первоначальная трасса содержит только общий текст исключения; provider status/body, latency и usage были потеряны. Они не выводятся из того, что другой запрос той же сессии получил 429. Диагностика была улучшена для последующих вызовов.

## Live diagnostic

Фактический evidence набор — сохранённые approved sections/units предыдущего read-only Stage3 A/B; новых hybrid retrieval turns — **0**, новых Understanding calls — **0**. Read-only `get_collection` проверил ту же коллекцию `knowledge_stage3_retrieval_20261022`: **934 points**, `green`. Qdrant writes — **0**. Временное значение `QDRANT_COLLECTION` было передано одному процессу из сохранённого trace; `.env` не изменялся. Qdrant client показал version-skew warning (client 1.19.1 / server 1.15.4), но read-only preflight завершился успешно.

Всего совершено **4 Decision attempts** (лимит 4): три последовательных в первом запуске, затем один отдельный оставшийся case после Retry-After. D3.1 не повторялся. Automatic retries — **0**.

| Split / ход | Выбранное evidence / результат | Полезность | Проверки и цена |
|---|---|---|---|
| DEV D1.2 — «Что такое ОФД?» | ID `ev-bd63d4ae34736e3385ba0c08`: «ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.» | Полезно: объясняет роль оператора и передачу документов. | Approved/SHA/exact-section/safety PASS; 1,325 ms; 2,233 prompt + 486 completion = 2,719 tokens. |
| HOLDOUT D1.3 — «А зачем он нужен кассе?» | IDs `ev-60f3062ca335287d2e522747` + `ev-bd63d4ae34736e3385ba0c08`: повтор вопроса «Что такое ОФД и почему без него касса не передаёт чеки в ФНС?» + тот же фактический ответ о приёме, обработке и передаче. | Полезно по основному критерию: функция передачи раскрыта. Ответ шумнее нужного, потому что как evidence выбран interrogative snippet; сам вопрос не является доказательством факта. | Локальные ID/provenance/safety checks PASS; quality caveat; 1,205 ms; 2,366 + 252 = 2,618 tokens. |
| DEV D3.1 — «Найти чек в Платформе ОФД.» | Decision не получен: HTTP 429. | Не оценивался, ответа нет. | Phase `http_status`; status 429; provider type `tokens`; code `rate_limit_exceeded`; Retry-After 12 s; 360 ms; provider usage не сообщён. |
| HOLDOUT D3.2 — «А за прошлый месяц?» | ID `ev-fb137281c08dcb924aca7d5f`, цельный approved block: «Маршрут: „Чеки“ → „Поиск чеков“. Период задаётся датами пробития, а не поступления в ОФД. Для прошлого месяца выберите календарные границы нужного месяца. Основные параметры: тип документа, магазин, касса по названию или РНМ; отдельно доступны ФД и ФП из чека.» | Полезно: продолжает текущую задачу и объясняет границы месяца. | Approved/SHA/applicability/safety PASS; 976 ms; 2,530 + 203 = 2,733 tokens. |

Три полученных ответа по ручной рубрике полезны; один ход не получил ответа из-за provider error. Это **не 4/4 quality pass**. На D1.3 обнаружена общая проблема пригодности evidence: детерминированные локальные проверки подтверждают происхождение и safety, но допускают текст вопроса из approved FAQ как ответный фрагмент. Ее нужно устранять общей политикой eligibility/evidence-role, не частным regex и не prompt tuning на HOLDOUT.

## Usage, provider errors и status

Успешный provider-reported usage: **7,129 prompt + 941 completion = 8,070 total tokens**. Token usage по HTTP 429 неизвестен; итог не включает его. Деньги не оценивались, поскольку тарификация не сохранена в эксперименте. Латентности Decision: 1,325, 1,205, 360 (429), 976 ms.

Первый запуск получил `BLOCKED` на третьем case и остановился. После 12-second Retry-After был отправлен только следующий D3.2 cassette case, не повтор D3.1; этот единственный дополнительный вызов завершился. Поэтому диагностическая серия завершена по лимиту, но **полный matched quality gate заблокирован 429**. Trace files: [first run](p1_semantic_selector_diagnostic_20261026.json), [D3.2 continuation](p1_semantic_selector_diagnostic_20261026_resume.json), [combined quality/cost summary](p1_semantic_selector_diagnostic_summary_20261026.json).

## Offline результаты

- До правок полный pytest baseline: **414 passed, 6 xfailed, 13 warnings**.
- После изменений полный pytest: **420 passed, 6 xfailed, 13 warnings**. Существующие xfail остались видимыми.
- Новые targeted тесты provider diagnostics + selector cassette: **16 passed**.
- `py_compile` для изменённых runtime files и diagnostic runner прошёл.

## Решение

**B2 — NO-GO; flag off.** Сигнал качества хороший на полученных D1.2, D1.3 и D3.2; однако набор неполон, на D1.3 evidence содержит лишний вопросный фрагмент, а D3.1 заблокирован rate limit. Safety-проверки не обнаружили обхода, но текущая выборка не оправдывает расширение маршрута.

**P1 D2 / ProgressLedger: GO только для offline реализации** через прежний Source-first путь и независимые safety gates. **Полные технические сценарии под semantic selector, live D2 и worker rollout — NO-GO.** До технической оценки нужны универсальная eligibility проверка для factual vs interrogative evidence и регрессии на порядок шагов, предусловия, service/model applicability и error-code consistency. Это не требует переписывать retrieval или менять базу знаний.

Ограничения соблюдены: KB, production SQLite, Qdrant contents, `.env`, worker/Telegram не менялись. Commit/push не выполнялись.
