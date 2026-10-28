# Ограниченное исправление семи Telegram-обращений — 28.10.2026

## Граница и метод

Основание — [диагностический аудит семи живых диалогов](2026-10-28-telegram-quality-audit.md). На входе checkout `main`/`114b8101a2ad6bb90631e463804e62eff1e65a7f` был чистым, работал один worker PID 39560. Его receipt относился к прежнему B+ runtime и имел 33 source hashes. Утверждённые статьи KB, Qdrant, `.env` и пользовательские строки SQLite не редактировались. Изменены только SourceFirst, retrieval, scope/task resolver, тесты, read-only replay-скрипт и документация. Commit/push не выполнялись.

Семь запросов воспроизведены из сохранённых 28.10 `DialogueState` и Coordinator decisions. Поиск и embedding — настоящие, коллекция Stage3 `knowledge_stage3_retrieval_20261022` read-only; Planner подменён детерминированным локальным выбором section ID, поэтому это **не повторный живой ответ Groq**. Для кейса статуса fixture намеренно возвращает наблюдавшееся `order_confirmed=false`. Raw Understanding не переигрывался: входное состояние взято из runtime-трассы. Приватный полный вывод: `.local/telegram-quality-replay-20261028.json`; публичный отчёт не содержит идентификаторов пользователей.

## Причины и изменения

1. **Предмет объяснения.** Раньше `_conceptually_answering_sentence` принимал любое пересечение слов: факт о переносе ФН побеждал запрос «что такое ОФД» за счёт «кассы/простыми». Теперь для определения извлекается названный предмет; factual sentence должна назвать его в начальной части и содержать следующее за ним утверждение. Обстоятельства вроде «для API сначала…» не являются определением. При отсутствии такого approved-факта сохраняется маркированный general knowledge fallback. Для `general/explain` retrieval берёт до трёх approved кандидатов и SourceFirst просматривает до 12 их разделов вместо одного документа/четырёх разделов. Это вернуло уже имевшийся `atol_online/ofd/what-is-ofd.md`; vendor scope явно указан в ответе. Исключений под ОФД, ФН, API или АТОЛ нет.
2. **Наблюдаемый объект технической поломки.** В широких `integration`/`peripheral_setup` выбранный Planner раздел с симптомом проверяется на присутствие предмета, указанного в DialogueState. Раздел `api-test.md::Подтверждённые сведения` вообще не говорит об отсутствующем чеке и теперь отклоняется после Planner. При наличии другого уже найденного и прошедшего approved/SHA/scope раздела допускается ровно один повторный Planner selection; если его нет, задаётся диагностический вопрос о статусе/ошибке и наличии документа в журнале. В текущем семикейсовом replay альтернативы для АТОЛ нет, дополнительных Planner calls — 0. Это отрицательная проверка релевантности, а не доказательство полноты выбранной статьи; единый incident flow по-прежнему нужен в KB.
3. **Типизированный scope.** `equipment` может подтвердить manufacturer только если это ровно зарегистрированный alias производителя либо alias с однозначной числовой моделью. Cloud service, отдельный номер модели и конфликт с явно названным manufacturer не проходят. Модельные ограничения не ослаблены. Для `equipment=Эвотор` разрешена безопасная диагностическая секция `fn-231.md`, ранее недоступная из-за пустого manufacturer.
4. **Чтение статуса против операции.** Для `operation=status` полностью factual, безопасный раздел с подтверждённой применимостью допускается при `order_confirmed=false`; запрос на изменение/отправку и процедурный текст по-прежнему требуют прежнего gate. Слово «отправки» (существительное в вопросе о статусе) не считается командой «отправить». После трактовки значения бот спрашивает точную отметку или код ошибки.
5. **Банковский task.** Resolver распознаёт сочетание банковского контекста, объекта (счёт/выписка) и признака отсутствия/сбоя как `bank_statement/diagnose`; подключение счёта без сбоя остаётся `integration/connect`. DirectBank article больше не теряется как `bank_statement!=integration`. Ни банк, ни релиз 1С не выводятся из статьи: первый шаг их уточняет.

Дифф: `app/source_first_service.py`, `app/retrieval_pipeline.py`, `app/scope_policy.py`, `app/task_operation_resolver.py`; тесты `tests/test_source_first_dialogue_contract.py`, `tests/test_scope_policy.py`, `tests/test_task_operation_resolver.py`; новый `scripts/replay_telegram_quality_20261028.py` и обновлённый `scripts/source_scope_offline_e2e.py`.

## Семь обращений: baseline → ограниченный replay

| № | До | После и оценка пользы | Task / итоговый evidence | Остаток |
|---|---|---|---|---|
| 1. aQsi scanner | Частично полезный ответ | **Без изменений**, безопасный первый факт о совместимости и интерфейсе | `peripheral_setup/check`; `aqsi_devices/peripherals/scanner.md` | Нет пошагового подключения под подтверждённую модель сканера |
| 2. aQsi Online partial refund | Полезный краткий порядок | **Без изменений**, возврат исходного чека с одной позицией | `refund/return`; `aqsi_online/receipts/partial-refund.md` | Нужны согласованные финансовые условия и expected result |
| 3. АТОЛ Online API, оплаты есть/чеков нет | Нерелевантные версии API/ФФД | **Лучше как диагностический вопрос**, но задача ещё не решена; ответ больше не выдаёт сведения о версии за диагностику | `integration/check`; `atol_online/integration/api-test.md::Подтверждённые сведения` отклонён проверкой предмета, иной approved альтернативы нет | Нужна целевая инструкция absent receipt flow |
| 4. Эвотор ФН 231 | Только код ошибки | **Предметная безопасная проверка** отчёта и вида позиции | `error_diagnosis/diagnose`; `evotor/fn/fn-231.md::Проверка без изменения регистрации` | Замена/перерегистрация остаются у специалиста; модель ФН/условия требуют уточнения |
| 5. Платформа ОФД, статус ФНС | Ложная эскалация | **Значения статусов + уточнение конкретной отметки** | `receipt_status/status`; `platformaofd/ofd/lkk-receipt-fns-status.md::Результат контроля` | Путь дан как «поиск чеков»; точная навигация есть в соседней статье, но не попала в выбранный evidence |
| 6. DirectBank, один счёт не виден | Ложная эскалация | **Первый применимый шаг**, уточнение релиза/банка; продолжение нужно для сверки счетов | `bank_statement/diagnose`; `1c/bank/directbank-all-accounts.md::Безопасная диагностика` | Точные действия зависят от релиза 1С и банка |
| 7. Что такое ОФД | Критический ответ про перенос ФН | **Прямое объяснение роли ОФД** с атрибуцией vendor scope | `general/explain`; `atol_online/ofd/what-is-ofd.md::Что проверено по инструкции производителя` | Для общего знания полезен нейтральный approved-источник ФНС |

По содержанию **5 из 7 стали полезнее**: четыре содержательных ответа (#4–7) и один уместный диагностический вопрос (#3); два прежних полезных ответа сохранены. В этих семи baseline было 2 ложных отказа (#5–6) и 2 ответа не по вопросу (#3, #7); в ограниченном replay новых ложных отказов и ответов не по вопросу нет. Опасных рекомендаций в сравнении не найдено. Это оценка **offline с fixture Planner**, окончательное качество живого Planner подтвердят ручные Telegram-тесты.

### Подробные трассы исправленных случаев и полный фактический offline-ответ

**3. АТОЛ Онлайн.** Сохранённое Understanding/State: `unknown/check/чек`, symptom «Оплаты проходят, а чеки не появляются», service `АТОЛ Онлайн`; новый resolver по query: `integration/check`. Top candidate `atol_online/integration/api-test.md`; `atol_online/receipts/advance-closing.md`, `mass-correction.md`, `payment-object-ffd105.md` отклонены как другой task, `switch-ffd12.md` — `subtask_anchor_uncovered`. Planner fixture выбрал `api-test.md::Подтверждённые сведения`, applicability/order `true/true`. Postselection gate отверг раздел: observed object «чек» отсутствует в его тексте; альтернативных прошедших разделов 0, повторного вызова нет. Composer не применялся. Полный ответ:

> Какой статус или текст ошибки вернул запрос интеграции? Виден ли документ в журнале сервиса?

**4. Эвотор ФН 231.** Сохранённое State: `unknown/diagnose/ФН`, symptom «ошибка ФН 231», `equipment=Эвотор`; resolver: `error_diagnosis/diagnose`. Единственный selected `evotor/fn/fn-231.md`, rejected нет. Typed scope разрешил `manufacturer=Эвотор` из однозначного equipment; модель из этого не выведена. Planner fixture выбрал `Проверка без изменения регистрации`, applicability/order `true/true`. ProgressLedger зафиксировал один показанный и один eligible unit. SourceFirst exact-section renderer проверил SHA; отдельный LLM Composer не вызывался. Ответ:

> Посмотрите в отчёте «Итог регистрации ККТ», указан ли признак расчётов за услуги. Если фактически продаётся услуга, проверьте вид позиции в карточке товара: она должна быть оформлена как услуга. Если есть продажи товаров при неподходящей конфигурации ФН, источник указывает на необходимость другого накопителя; решение о замене и перерегистрации требует специалиста.
>
> Источник: data/knowledge/evotor/fn/fn-231.md — Проверка без изменения регистрации

**5. Платформа ОФД.** Сохранённое State: `receipt/status`, symptom «непонятный статус отправки в ФНС», ofd `Платформа ОФД`; resolver: `receipt_status/status`. Selected `platformaofd/ofd/lkk-receipt-fns-status.md`; чужой `atol_online/ofd/what-is-ofd.md` отклонён service/task, другие FN/connection статьи отклонены task. Planner fixture: `Результат контроля`, applicability `true`, order `false`; локальный factual read-only gate разрешил только справочные утверждения. ProgressLedger/LLM Composer не вызывались; SHA/exact source copy проверены. Полный ответ:

> В поиске чеков статус отражает результат форматно-логического контроля ФНС. Успешный приём означает отсутствие ошибок; предупреждение — приём с обнаруженными ошибками; карантин — передачу при незавершённой регистрации, когда проверка на сайте ФНС недоступна; отказ — отклонение документа из-за ошибок. Подсказка иконки показывает статус.
>
> Дополнительное условие источника (Ограничения):
> Порядок исправления зависит от конкретной ошибки и регистрации. Одна отметка не заменяет диагностику специалистом.
>
> Источник: data/knowledge/platformaofd/ofd/lkk-receipt-fns-status.md — Результат контроля
>
> Для разбора конкретного документа уточните точную надпись статуса или код ошибки.

**6. DirectBank.** Сохранённое State: `unknown/diagnose`, symptom «не отображается один из банковских счетов», integration `DirectBank`, software `1С`; resolver: `bank_statement/diagnose`. Selected `1c/bank/directbank-all-accounts.md`, где раньше был `bank_statement!=integration`; `directbank-other-banks.md`, `import-file-directbank.md`, `directbank-auto-schedule.md` теперь отвергнуты по операции. Planner fixture: `Безопасная диагностика`, applicability/order `true/true`. ProgressLedger зафиксировал один показанный из четырёх eligible units; отдельный LLM Composer не вызывался. SourceFirst exact source copy:

> 1. Уточнить версию «1С:Бухгалтерии» и включён ли 1С:ДиректБанк для соответствующего банка.
>
> Источник: data/knowledge/1c/bank/directbank-all-accounts.md — Безопасная диагностика

**7. Объяснение ОФД.** Сохранённое Understanding/State: `general/explain/ОФД`; resolver не навязывает технический task. Selected среди прочего `atol_online/fn/fn-basics.md` и `atol_online/ofd/what-is-ofd.md`; FN оставлен кандидатом, но его предложения не называют предмет определения. Coordinator выбрал точный factual sentence из второй статьи; Planner и ProgressLedger не вызывались, Groq fallback не требовался. Exact quote/SHA и явный scope подтверждены. Полный ответ:

> ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.
>
> Область источника: АТОЛ Онлайн, АТОЛ, АТОЛ Онлайн — облачная ККТ.
> Источник: data/knowledge/atol_online/ofd/what-is-ofd.md — Что проверено по инструкции производителя

## Gate и стоимость

- `python -m pytest -q`: **523 passed, 4 xfailed, 13 warnings**. На первом запуске изолированное `tests/test_vnext_retrieval.py` не импортировалось из-за старых бинарных wheels Python 3.12 в игнорируемом `.local/vnext-deps` при текущем Python 3.14. Локально обновлены только три пакета в `.local` (`ormsgpack`, `xxhash`, `orjson`); после этого полный suite прошёл. Production dependencies и код vnext не менялись.
- `python scripts/source_scope_offline_e2e.py`: **15/15**, реальный Stage3 read-only, 0 provider calls. Проверены FN 234, DirectBank, Эвотор 7.3, ТС ПИоТ, general definitions/comparison, wrong model/manufacturer и опасная операция с архивом ФН. Результат `.local/source-scope-offline-e2e.json`.
- `python scripts/replay_telegram_quality_20261028.py`: **7/7 quality assertions**, полный текст ответов проверен вручную на полезность и опасные действия; 0 provider calls. Один Planner fixture вызов в каждом техническом кейсе, 0 для #7; #3 не имел допустимой альтернативы, дополнительный Planner вызов не понадобился. Результат `.local/telegram-quality-replay-20261028.json`.
- Предыдущий frozen replay 24/24 через `.local/replay_task_resolver_full_20261028.py`: ответ/сценарий изменён только в #24 — к трактовке статуса добавлен вопрос о точной отметке. **0 новых эскалаций и 0 переходов answer→clarify**. #11 остаётся исходным unreplayable HTTP 400 Understanding и не объявляется восстановленным. Результат `.local/task_resolver_full_20261028_resolver_plus_gate.json`.
- `tests/test_llm_client_diagnostics.py`, `tests/test_dialogue_understanding.py`, `tests/test_groq_rate_limit.py` покрывают 400, 429, bounded retry и diagnostic usage. Дополнительный живой контроль Groq перед switch: один вызов `openai/gpt-oss-20b`, **174 tokens**, **1258 ms**, retry 0, без 400/429. Это проверка доступности провайдера, не проверка качества семи живых Planner ответов. Offline latency (примерно 0.6–0.9 с на кейс) включает локальный embedding/fixture и не сравнима с Telegram latency. Реальная прибавка latency при условном повторном Planner выборе ещё не измерена; код ограничивает её одним дополнительным вызовом только при найденной альтернативе.

## Backup, переключение и текущий runtime

До остановки PID 39560 созданы backup обеих SQLite через read-only source API, `quick_check=ok`, старый receipt и исходные/new версии четырёх изменённых runtime файлов: `.local/backups/limited-repair-20261028T101850Z/manifest.json`. Backup `conversations.sqlite3` SHA-256 `01d7954792f4dd399ed669071bf0f98a047e26b92621fd95f7dcab872731ef91`; backup `expert_reviews.sqlite3` SHA-256 `73ed6dd27d0421f4be1b962b0b684978d4fd1873c7d6369`. Секреты `.env` не копировались.

Первый штатный restart остановил старый PID и запустил PID 39632, но Windows вернул `PermissionError [WinError 5]` на atomic replace `.local/bot-runtime.tmp` → `.local/bot-runtime.json`; бот не дошёл до polling. Процесс 39632 завершён. При отсутствии активного worker временный receipt был успешно заменён вручную и сохранён в backup; перед повторным запуском receipt перенесён в backup, чтобы исключить блокировку target. Вторая попытка запустила **единственный worker PID 37460**. Проверка после запуска: 33/33 runtime source hashes совпали с текущими файлами; Stage3 `green`/934, SourceFirst/Coordinator ON, selector/handoff OFF, Groq `openai/gpt-oss-20b`/medium, allowlist 3 с неизменным hash; `Application started`, critical log matches 0, polling conflicts 0. Receipt `.local/bot-runtime.json`, лог `.local/limited-repair-worker-20261028.log`, сводка `.local/backups/limited-repair-20261028T101850Z/worker-switch-result.json`. Telegram-сообщения агент не отправлял.

## Оставшиеся границы и следующий шаг

Кейс #3 требует согласованной incident-статьи «оплата есть, API-чек не появился»: статусы запроса/callback, журнал чеков, признаки блокировки и безопасная последовательность проверки. Для #1 нужны модель/интерфейс сканера и approved пошаговое подключение; для #2 — финансовые условия частичного возврата. Для #6 нужен релиз/конфигурация 1С и банк, чтобы проверить видимость счёта и настройки обмена; для #5 полезно объединить путь `platformaofd/ofd/lkk-receipt-search.md` со статусами. Эти материалы перечислены с официальными URL в [первом аудите](2026-10-28-telegram-quality-audit.md); ни один новый источник не утверждался как approved.

**Следующий шаг только ручной Telegram-пилот пользователя** на семи сценариях с продолжением #3/#5/#6. Проверить, что живой Planner сохраняет полезность и не создаёт лишние 400/429/задержку; при неудаче снять обезличенные runtime diagnostics и решать отдельно. Не начинать новый архитектурный этап, не менять KB/Qdrant и не делать commit/push до решения пользователя.
