# B2.2d — Answer Relevance & Dialogue Continuation, 05.11.2026

IN_PROGRESS; B2.3/production NO-GO. Входной HEAD fcb3489d6085e7b37774a27089af3fe5f9f2a4b1, рабочее дерево было чистым. Commit/push, production, основной Qdrant, `.env` и approved KB не изменяются.

## Протокол

[18 frozen baseline /24 turns](baseline_frozen.json), SHA256 `6a165b6827cc6be8da4402c0d0188ea61e52764569595c856bb068e02b04f091`: шесть многоходовых, ККТ/ФН, ОФД, 1С, ЭДО, маркировка, API/доступ. Заморозка до LIVE и runtime изменений. Expected minimum и snapshots approved источников сохранены. Lexical novelty по прежним JSON дополнена ручным выбором новых ситуаций; это prospective cohort, не статистическая репрезентативность. Общий механизм может повторяться. Старые h/b/s/m — только регрессии.

Preflight отклонил `edo/edi-operator-choice.md` как draft до frozen и LIVE. d10 заменён; `edo/marked-goods-acceptance.md` тоже draft, поэтому d15 сохранён как no-approved-coverage boundary. Источники не утверждались. Первый harness остановился до Groq из-за исторического private каталога `baseline_live`; лог сохранён, выбран `b22d_baseline_live`.

Реальный bot.handle_message, Groq openai/gpt-oss-20b, Stage3 read-only934, отдельная SQLite и reopen equality. Полные ответы/Understanding/TaskFrame/evidence/Planner/HTTP/usage сохраняются. Вопросы не содержат значений секретов.

## Историческое evidence

[13 ходов](regression_diagnostics.json) из опубликованных B2.2c traces; это не новое воспроизведение.

- h10: general/explain → grounded_information → один focused sentence; выбрана фраза3 о месте ввода токена. Фразы1–2 prerequisites и4 запрет передачи секрета в том же approved разделе пропущены.
- h06: «с чего начать» превращено в general/explain; single-fact маршрут отдаёт соседний факт из эскалации вместо начальных проверок.
- h07: факт о возможности и версии отклонён conceptual gate, требующим формы определения. Это не gap.
- h01: Planner получил четыре раздела ФН210/235, которые действительно не отвечают мобильной связи. Ограничитель source_sections(...,4) может скрывать другие выбранные статьи; конкретное network evidence требует raw retrieval проверки.
- h05/h08 остановлены до Planner как insufficient_applicable_evidence. Проверить operation/domain compatibility, не ослаблять scope.
- b01/2: Understanding continue bank_statement/check после bank_statement/explain; reducer new_task, entities потеряны. s01/2: continue access/configure после credentials/add_employee; reducer new_task, aQsi Online потерян. m01/2: continue general/explain после general/diagnose; reducer new_task и потеря Эвотора. Первая подтверждённая потеря — reducer считает различие coarse operation независимой задачей даже при continue.

## Следующий шаг

Завершить baseline на неизменённом runtime; затем минимальные общие исправления, профиль/full pytest, реальные регрессии и отдельные 12 новых holdout. Невыполненное не считать успешным. Сохранить отрицательные эксперименты и cooldown.

## Промежуточные эксперименты и отрицательные результаты

TPD остановил первый baseline на d10/1: HTTP429, Used198133/200000, Retry-After268с от05:09:31 UTC. 12 завершённых ходов, один H. Владелец затем сообщил о доступности и внешне обновил `.env`; агент файл не редактировал. Повтор после cooldown продолжил d10–d18. Все18/24 завершены на исходных34 SHA: [первый trace](b22d_baseline_live.json), [resume](b22d_baseline_resume1_live.json), [snapshot receipt](before_runtime_snapshot_receipt.json). Код для продолжения сохранён до первых runtime правок, хеши совпали; оставшиеся baseline вызовы физически выполнялись после локальной работы над кандидатом, но импортировали исходный snapshot. Это раскрытое отклонение хронологии из-за квоты, не baseline нового runtime.

Первый reducer-кандидат слишком широко доверял continue и обновлял intent. Полный Python3.12 pytest:6 failed/703 passed/4xfail; пять содержательных failures выявили потерю независимых задач печати и drift домена, шестой — ABI-зависимость ormsgpack для Python3.14 в существующей .local/vnext-deps. Код сужен: same task только для coarse explain/check/status/diagnose и связанного access/credentials, при независимой операции/новом scope/new topic — reset; произвольное изменение intent отклонено. Python3.14 targeted66 passed. Логи initial/profile сохранены. Это не доказательство LIVE памяти, которое проверяется отдельно.

h01 raw target отвергнут до Planner task_mismatch network_diagnostics!=error_diagnosis; гипотеза про truncation4 не была первопричиной и не внедрена. h05 raw import-file отвергнут как bank_statement!=integration; исправлена предметная проекция импорта. h07 regex evidence_kind считал `3.0.188` нумерованным шагом из-за необязательного пробела после точки; исправлено отделение версии от списка. Capability fact допускается только с capability predicate и общим предметом; definition/comparison/safety gates сохраняются.

[Offline replay](offline_replay.json) использует сохранённый provider JSON, новый validator/reducer и настоящий Stage3; это не LIVE AFTER. Первое исполнение replay выявило невалидный intent reconciliation в новом resolver: исправлен на существующий general, категория остаётся reconciliation. h05 raw diagnose не должен превращать существующее подключение в операцию подключения: import subject уточнён при отсутствии loading failure. h08 остаётся task/operation mismatch; gate не ослаблялся. b01 сохраняет 1С, но check не соответствует reviewed load_bank_statements; OPEN. s01 generic view/edit flags отличены от прав на конкретный раздел; metadata partial остаётся partial и не обещает конкретную матрицу.

Первые9 регрессий выполняются на кандидате v2. h10 предупреждение гарантированно появилось, но prerequisites опять пропущены: provider вовсе не передал optional goal. Новая доказанная причина: procedure-context readiness зависела от наличия этого необязательного поля. Кандидат v3 читает подтверждённый span всего сообщения, направляет запрос условий в существующий полный Planner/SourceFirst, не добавляя факты или LLM-слой. v2 trace остаётся primary experiment, v3 будет отдельным release repeat; результаты не заменяются молча.

[12 holdout/15 ходов](holdout_frozen.json), SHA256 `5e8fe9b380b0f86f565e22e2aae52d24500cb8d332a88f8550c1af198b3b2e3f`, заморожены до первого holdout LIVE. В поле protocol сохранён baseline boilerplate: слова «до runtime changes» и «6 multi-turn» относятся к baseline. Для holdout фактические counts12/15 и три multi-turn; заморозка после начального кандидата и до holdout вызовов. Questions, minimum и source snapshots не изменены. До holdout outputs новые правила по его формулировкам не добавлялись.

[Пять B2.2c drafts](draft_readiness.json) прошли настоящий Loader/Chunker, status=draft/verified_at=null. Они сохранены без изменения и требуют SME review; утверждения/index нет.

## Дополнение: m01 и повторные квоты

В v2 m01/2 найден отдельный общий механизм: procedure continuity оставлял Planner только активный диагностический раздел. Approved «Передать инженеру» с запретом обхода проверки не попадал в выбор; старый regex заголовков также не распознавал «инженер/эскалация». Кандидат сохраняет активную процедуру плюс ограничения/предупреждения того же document_id/source, уже прошедшие scope/SHA. Другие процедуры не добавляются. [Реальная сохранённая state fixture](../../tests/fixtures/b22d_warning_continuation.json) воспроизводит вопрос о продаже без проверки; test проходит через полный SourceFirst с детерминированным Planner и проверяет exact approved предупреждение без повторного progress вопроса. Это offline, не LIVE m01 AFTER.

Первый полный pytest после этой правки дал1 failed/713 passed/4xfail: mutation safety fixture по-прежнему fail-closed, но причина стала source_section_changed вместо source_context_section_changed, потому что warning теперь может быть выбран. Контракт теста уточнён: оба integrity отказа допустимы, обязательны scenario=escalate и отсутствие mutated text в ответе. Защитный runtime gate не ослаблялся. [Профиль](warning_context_hardened_profile.log):94 passed/4xfail; финальный full выполняется отдельно.

h10 v3 после23с cooldown получил реальный полный ответ: [trace](b22d_h10_v3_retry_live.json), [оценка A](h10_v3_evaluation.json). Следующий holdout u01 получил TPD429 Used199043/200000, Retry-After670с (05:31:31 UTC). После явного обновления доступа владельцем отдельная минимальная проверка текущего `.env` дала HTTP200/99tokens и headers7797/8000 TPM,999/1000 RPD — [receipt](current_access_quota_probe.json). Эти headers не показывают остаток TPD. По официальной [документации Groq](https://console.groq.com/docs/rate-limits) лимиты относятся к организации, token headers всегда TPM.

На следующем полноценном release run h10 снова A на текущем warning-context коде, затем h01 Understanding200, Planner TPD429 Used199997/200000, Requested2600, Retry-After1122с от05:36:44 UTC; earliest08:55:26 МСК. [Trace](b22d_release_regressions_live.json). Наблюдавшийся остаток TPD3 не смешивается с TPM. Старое diagnostics provider_limit_dimension=tpm — ограничение телеметрии: redacted provider body однозначно TPD, Retry-After соблюдается независимо от dimension. Проверена и отвергнута гипотеза inherited env override: [receipt](credential_precedence_diagnostic.json), ключ настроек совпал с текущим GROQ_API_KEY файла, inherited отсутствовал. Самих значений ключей нет в traces/отчётах, credential-shape scan новых артефактов0.

Владелец повторно явно обновил ключ в `.env` и поручил полноценный LIVE/проверку исчерпания. Новый отдельный u01 вызов запущен; результат на момент этой записи ещё неизвестен. Владелец сам управляет доступом; агент не меняет `.env`, модель, allowance или provider tier. Holdout пока не имеет завершённых семантических результатов; независимость frozen вопросов сохранена, H-попытки не считаются полезностью.
