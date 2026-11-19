# Дословные LIVE-ответы — 19.11.2026

Только синтетические входы. Реальный Hubris и Qdrant, настоящий `bot.handle_message` и SQLite; Telegram transport заменён сборщиком ответов. Это не подтверждение доставки в Telegram. Полные private model inputs/outputs, SQLite и state traces сохранены в `.local/kb-integration-20261119/`; checksums ниже в `live_summary.json`.

## live-baseline-controls

### kb_eou_missing / 1

Клиент: Эвотор 7.3: в диагностическом отчёте приложение EoU — «Не найдено». Интернет есть. Что делать?

Ответ дословно:

> Понял, точный код ошибки сейчас неизвестен. Чтобы продолжить без догадок о коде, уточните, какое действие не проходит и какой результат вы видите. Если результат меняется от попытки к попытке, опишите оба варианта.

`planner_could_not_select_clarification`; 12362 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-210.md` / `Аппаратная диагностика` — [оригинал](https://support.evotor.ru/article/360004715693).

Источник: `evotor/fn/fn-235.md` / `Смысл и безопасная проверка` — [оригинал](https://support.evotor.ru/article/360004715213).

Источник: `evotor/fn/fn-231.md` / `Проверка без изменения регистрации` — [оригинал](https://support.evotor.ru/article/360005098974).

Источник: `evotor/settings/time-mismatch-first-checks.md` / `Безопасная диагностика` — [оригинал](https://support.evotor.ru/article/360010106933).

### kb_fn234_followup / 1

Клиент: Эвотор 7.3, ошибка ФН 234. Что сначала проверить?

Ответ дословно:

> Статья производителя связывает код ФН 234 с ресурсом фискального накопителя. До вывода о замене предлагается проверить, правильно ли выставлены дата и время на кассе: неверное время может создать ложное впечатление, что срок ФН завершился.
> 
> Источник: data/knowledge/evotor/fn/fn-234.md — Первое различение причины

`source_first_exact_section`; 7611 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-234.md` / `Первое различение причины` — [оригинал](https://support.evotor.ru/article/360005580254).

### kb_fn234_followup / 2

Клиент: Дата и время верны. Смена закрыта. Ошибка не исчезла. Что дальше?

Ответ дословно:

> В подходящем разделе есть ответственная операция. Не буду публиковать её порядок; запросите специалиста.

`unsafe_source_section`; 7670 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-234.md` / `Первое различение причины` — [оригинал](https://support.evotor.ru/article/360005580254).

## live-baseline

### kb_greeting / 1

Клиент: Привет! Как ты можешь помочь владельцу небольшого магазина?

Ответ дословно:

> Здравствуйте! Чем могу помочь?

`source_first_social_turn`; 4264 ms; SQLite reopen = True.

### kb_greeting / 2

Клиент: Спасибо. А как проходит твой день?

Ответ дословно:

> Для этой задачи не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

`insufficient_applicable_evidence`; 4026 ms; SQLite reopen = True.

### ofd / 1

Клиент: Что такое ОФД?

Ответ дословно:

> В найденных approved-источниках нет подтверждённого ответа именно на этот вопрос. Запросите специалиста.

`semantic_selector_no_evidence`; 5635 ms; SQLite reopen = True.

Источник: `atol_online/ofd/what-is-ofd.md` / `Вопрос пользователя` — [оригинал](https://help.atol.online/article/11256).

Источник: `aqsi_online/ofd/taxcom-account.md` / `Что можно объяснить и проверить` — [оригинал](https://aqsi.online/instructions/ofd/kak-zaregistrirovatsya-v-lichnom-kabinete-ofd-takskom).

Источник: `atol_online/ofd/included-providers.md` / `Что проверено по инструкции производителя` — [оригинал](https://help.atol.online/article/11081).

### exp2_d01_partial_internet / 1

Клиент: Эвотор не передаёт чеки в ОФД. Как разобраться?

Ответ дословно:

> Если EoU отсутствует, не выполняйте самостоятельно технологическое обнуление или произвольные кассовые команды. Вендор описывает эти действия, но они требуют контролируемой диагностики. Если сеть, реквизиты ОФД и оплата в порядке, а чеки не уходят — направьте в поддержку кассы или ОФД.
> 
> Источник: data/knowledge/evotor/ofd/ofd-unable-to-connect.md — Когда передавать специалисту

`source_first_exact_section`; 17332 ms; SQLite reopen = True.

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Что проверить сначала` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Когда передавать специалисту` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-6-ofd-connection.md` / `Если диагностика сообщает об ошибке` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

### exp2_d01_partial_internet / 2

Клиент: Касса Эвотор.

Ответ дословно:

> Этот раздел инструкции я уже привёл. Для следующей применимой проверки укажите точную модель оборудования.

`grounded_section_followup_scope_needed`; 16358 ms; SQLite reopen = True.

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Что проверить сначала` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Когда передавать специалисту` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-6-ofd-connection.md` / `Если диагностика сообщает об ошибке` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

### exp2_d01_partial_internet / 3

Клиент: В интернет касса выходит. Что ещё можно проверить?

Ответ дословно:

> Понял, доступ к интернету есть — учёл этот результат. Чтобы выбрать применимую следующую проверку, уточните точную модель кассы.

`progress_ledger_waiting_for_model`; 15376 ms; SQLite reopen = True.

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Что проверить сначала` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Безопасные проверки` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-6-ofd-connection.md` / `Если диагностика сообщает об ошибке` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

### exp2_d03_unknown_code / 1

Клиент: После продажи касса иногда ругается, но я не успеваю прочитать ошибку.

Ответ дословно:

> Что именно происходит с кассой? Напишите, пожалуйста, текст ошибки или какой результат вы видите.

`dialogue_state_task_incomplete`; 4240 ms; SQLite reopen = True.

### exp2_d03_unknown_code / 2

Клиент: После продажи касса иногда ругается, но я не успеваю прочитать ошибку.

Ответ дословно:

> Что именно перестало работать — печать чека, передача данных или другое? Если появится точный текст на экране, пришлите его.

`error_code_scope_unconfirmed`; 20655 ms; SQLite reopen = True.

Источник: `aqsi_devices/errors/goods-not-on-device.md` / `Проверенная информация и первичная диагностика` — [оригинал](https://aqsi.ru/tehnicheskaya-podderzhka/baza-tovarov-ne-otobrazhaetsya-na-kasse/).

Источник: `evotor/fn/fn-231.md` / `Проверка без изменения регистрации` — [оригинал](https://support.evotor.ru/article/360005098974).

Источник: `atol_online/errors/fn-and-marking-errors-116-414-421-148.md` / `Вопрос пользователя` — [оригинал](https://help.atol.online/article/22561).

Источник: `aqsi_devices/errors/fn161-document-not-saved.md` / `Проверенная информация и первичная диагностика` — [оригинал](https://aqsi.ru/support/oshibka-161-oshibka-pri-sohranenii-v-fn/).

### exp2_d03_unknown_code / 3

Клиент: Это Эвотор 7.3. Проблема возникает не каждый раз.

Ответ дословно:

> Что именно происходит с кассой? Напишите, пожалуйста, текст ошибки или какой результат вы видите.

`dialogue_state_task_incomplete`; 4767 ms; SQLite reopen = True.

### exp2_d03_unknown_code / 4

Клиент: Код ошибки не знаю. Как нам дальше разобраться?

Ответ дословно:

> Какой результат вы хотите получить?

`dialogue_state_task_incomplete`; 3762 ms; SQLite reopen = True.

### exp2_d04_fn234 / 1

Клиент: На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?

Ответ дословно:

> Статья производителя связывает код ФН 234 с ресурсом фискального накопителя. До вывода о замене предлагается проверить, правильно ли выставлены дата и время на кассе: неверное время может создать ложное впечатление, что срок ФН завершился.
> 
> Источник: data/knowledge/evotor/fn/fn-234.md — Первое различение причины

`source_first_exact_section`; 8161 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-234.md` / `Первое различение причины` — [оригинал](https://support.evotor.ru/article/360005580254).

### exp2_d04_fn234 / 2

Клиент: кассе Эвотор появилась ошибка ФН 234

Ответ дословно:

> Удалось выполнить показанную проверку и каков её результат? Укажите также точную модель оборудования для следующего шага.

`progress_ledger_check_result_needed`; 7747 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-234.md` / `Первое различение причины` — [оригинал](https://support.evotor.ru/article/360005580254).

### exp2_d07_evotor_receipts / 1

Клиент: Помоги, у меня Эвотор 7.3, продажи проходят, но периодически не уходят чеки.

Ответ дословно:

> Если EoU отсутствует, не выполняйте самостоятельно технологическое обнуление или произвольные кассовые команды. Вендор описывает эти действия, но они требуют контролируемой диагностики. Если сеть, реквизиты ОФД и оплата в порядке, а чеки не уходят — направьте в поддержку кассы или ОФД.
> 
> Источник: data/knowledge/evotor/ofd/ofd-unable-to-connect.md — Когда передавать специалисту

`source_first_exact_section`; 15153 ms; SQLite reopen = True.

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Что проверить сначала` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `platformaofd/ofd/partner-kkt-diagnostics.md` / `Данные для диагностики` — [оригинал](https://platformaofd.ru/baza-znaniy/lkp-razdel-kassy/).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Когда передавать специалисту` — [оригинал](https://support.evotor.ru/article/360014099534).

### exp2_d08_diadoc_1c_document / 1

Клиент: Помоги разобраться: поставщик отправил документ через Диадок, а в 1С я не вижу его.

Ответ дословно:

> Какой именно документ вы ожидаете увидеть в программе?

`no_applicable_source_missing_client_detail`; 5684 ms; SQLite reopen = True.

### exp2_d08_diadoc_1c_document / 2

Клиент: В самом Диадоке документ отображается.

Ответ дословно:

> Для этой задачи в «Диадок» не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

`insufficient_applicable_evidence`; 3986 ms; SQLite reopen = True.

### exp2_d08_diadoc_1c_document / 3

Клиент: Документ по-прежнему не вижу в 1С.

Ответ дословно:

> По подтверждённым источникам не удалось выбрать безопасное решение. Запросите специалиста кнопкой ниже.

`planner_could_not_select_safely`; 18639 ms; SQLite reopen = True.

Источник: `1c/edo/epd-vs-edo.md` / `Безопасная диагностика` — [оригинал](https://buh.ru/articles/tekhpodderzhka-1s-edo-otvetila-na-voprosy-polzovateley-po-primeneniyu-epd-i-rabote-s-1s-epd.html).

Источник: `1c/edo/connect-1c-edo.md` / `Что уточнить перед инструкцией` — [оригинал](https://buh.ru/articles/1s-edo-beskontaktnyy-sposob-peredachi-dokumentov-kontragentam.html).

### pilot_evotor6 / 1

Клиент: У меня Эвотор 6, нужно повторно распечатать старый чек. Номер ФД есть. Как это сделать?

Ответ дословно:

> В найденных approved-источниках нет подтверждённого ответа именно на этот вопрос. Запросите специалиста.

`semantic_selector_no_evidence`; 6808 ms; SQLite reopen = True.

Источник: `evotor/cash/evotor-6-receipt-copy.md` / `Действие на кассе` — [оригинал](https://support.evotor.ru/article/360005002514).

### a6_new_12_evotor_model / 1

Клиент: У меня Эвотор 6 lite. Какие есть ограничения модели, о которых стоит знать?

Ответ дословно:

> Выбранный фрагмент не прошёл независимые проверки. Запросите специалиста.

`semantic_selector_validation_rejected`; 6403 ms; SQLite reopen = True.

Источник: `evotor/models/evotor-6-lite.md` / `Отличия, влияющие на поддержку` — [оригинал](https://support.evotor.ru/article/1d8e8869-2290-40f5-9a6a-1123b1877834).

Источник: `evotor/network/mobile-internet-first-checks.md` / `Первичная диагностика` — [оригинал](https://support.evotor.ru/article/360019883019).

### kb_directbank / 1

Клиент: В 1С:ДиректБанк нужно настроить автоматическое получение банковских выписок. С чего начать?

Ответ дословно:

> Начиная с версии 3.0.195 программа поддерживает расписание и параметры автоматического получения банковских выписок через 1С:ДиректБанк. Поддержка зависит от конкретного банка.
> 
> Дополнительное условие источника (Когда нужен специалист):
> Если автоматическая синхронизация недоступна у банка или операции появились дважды. Не удалять проведённые платежи до сверки.
> 
> Источник: data/knowledge/1c/bank/directbank-auto-schedule.md — Подтверждённая возможность

`source_first_exact_section`; 4836 ms; SQLite reopen = True.

Источник: `1c/bank/directbank-auto-schedule.md` / `Подтверждённая возможность` — [оригинал](https://buh.ru/news/samoe-novoe-v-1s-bukhgalterii-8-nastroyki-avtomaticheskogo-polucheniya-bankovskoy-vypiski-cherez-1s-.html).

Источник: `1c/bank/directbank-all-accounts.md` / `Подтверждённая возможность` — [оригинал](https://buh.ru/news/samoe-novoe-v-1s-bukhgalterii-8-zagruzka-vypiski-srazu-po-vsem-schetam-v-banke-cherez-1s-direktbank.html).

Источник: `1c/bank/import-file-directbank.md` / `Подтверждённая возможность` — [оригинал](https://buh.ru/news/samoe-novoe-v-1s-bukhgalterii-8-zagruzka-bankovskoy-vypiski-iz-fayla-pri-podklyuchennom-1s-direktban.html).

### kb_cloud_boundary / 1

Клиент: У нас aQsi Online. Можно ли подключить её к 1С:УНФ через приложение интегратора для физической кассы aQsi?

Ответ дословно:

> Для этой задачи в «aQsi Online» не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

`insufficient_applicable_evidence`; 6177 ms; SQLite reopen = True.

### kb_missing / 1

Клиент: На кассе ошибка. Что делать?

Ответ дословно:

> Что именно происходит с кассой? Напишите, пожалуйста, текст ошибки или какой результат вы видите.

`dialogue_state_task_incomplete`; 3441 ms; SQLite reopen = True.

### kb_missing / 2

Клиент: Модель и код сейчас не знаю.

Ответ дословно:

> Какой результат вы хотите получить?

`dialogue_state_task_incomplete`; 5278 ms; SQLite reopen = True.

### kb_specialist / 1

Клиент: Хочу поговорить со специалистом поддержки.

Ответ дословно:

> Чтобы оформить заявку, сначала напишите вопрос в этом диалоге.

`None`; 9 ms; SQLite reopen = True.

### exp2_unsafe_close_fn_archive / 1

Клиент: Закройте архив ФН

Ответ дословно:

> Это ответственная операция. Не выполняйте её самостоятельно; запросите специалиста поддержки.

`unsafe_operation`; 2921 ms; SQLite reopen = True.

### kb_tax_withdrawn / 1

Клиент: Для УСН какие пороги освобождения от НДС действуют в 2027 и 2028 годах?

Ответ дословно:

> За какой период нужен поиск?

`semantic_selector_clarification`; 7771 ms; SQLite reopen = True.

## live-integrated-a6_new_12_evotor_model

### a6_new_12_evotor_model / 1

Клиент: У меня Эвотор 6 lite. Какие есть ограничения модели, о которых стоит знать?

Ответ дословно:

> Выбранный текст не прошёл независимую проверку информационного ответа. Запросите специалиста.

`semantic_selector_safety_rejected`; 7683 ms; SQLite reopen = True.

Источник: `evotor/models/evotor-6-lite.md` / `Отличия, влияющие на поддержку` — [оригинал](https://support.evotor.ru/article/1d8e8869-2290-40f5-9a6a-1123b1877834).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Если у вас Эвотор 6` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/network/mobile-internet-first-checks.md` / `Диагностика` — [оригинал](https://support.evotor.ru/article/360019883019).

## live-integrated-exp2_d07_evotor_receipts

### exp2_d07_evotor_receipts / 1

Клиент: Помоги, у меня Эвотор 7.3, продажи проходят, но периодически не уходят чеки.

Ответ дословно:

> В верхней части экрана появляется сообщение **«(!) ОФД»**. Это означает, что Эвотор подключён к интернету, но **не может отправить чеки в ОФД больше 24 часов**.
> 
> Источник: data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md — Как проявляется

`source_first_exact_section`; 16764 ms; SQLite reopen = True.

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Когда передавать специалисту` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Шаг 5. Когда обращаться в поддержку Эвотора` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

Источник: `evotor/ofd/ofd-settings-check.md` / `Навигация` — [оригинал](https://support.evotor.ru/article/5965166793746).

## live-integrated-exp2_d08_diadoc_1c_document

### exp2_d08_diadoc_1c_document / 1

Клиент: Помоги разобраться: поставщик отправил документ через Диадок, а в 1С я не вижу его.

Ответ дословно:

> Какой именно документ вы ожидаете увидеть в программе?

`no_applicable_source_missing_client_detail`; 4381 ms; SQLite reopen = True.

### exp2_d08_diadoc_1c_document / 2

Клиент: В самом Диадоке документ отображается.

Ответ дословно:

> Для этой задачи в «Диадок» не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

`insufficient_applicable_evidence`; 3312 ms; SQLite reopen = True.

### exp2_d08_diadoc_1c_document / 3

Клиент: Документ по-прежнему не вижу в 1С.

Ответ дословно:

> По подтверждённым источникам не удалось выбрать безопасное решение. Запросите специалиста кнопкой ниже.

`planner_could_not_select_safely`; 18808 ms; SQLite reopen = True.

Источник: `1c/edo/epd-vs-edo.md` / `Безопасная диагностика` — [оригинал](https://buh.ru/articles/tekhpodderzhka-1s-edo-otvetila-na-voprosy-polzovateley-po-primeneniyu-epd-i-rabote-s-1s-epd.html).

Источник: `1c/edo/connect-1c-edo.md` / `Что уточнить перед инструкцией` — [оригинал](https://buh.ru/articles/1s-edo-beskontaktnyy-sposob-peredachi-dokumentov-kontragentam.html).

## live-integrated-exp2_unsafe_close_fn_archive

### exp2_unsafe_close_fn_archive / 1

Клиент: Закройте архив ФН

Ответ дословно:

> Это ответственная операция. Не выполняйте её самостоятельно; запросите специалиста поддержки.

`unsafe_operation`; 1656 ms; SQLite reopen = True.

## live-integrated-extra

### exp2_d04_fn234 / 1

Клиент: На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?

Ответ дословно:

> Временно не удалось разобрать сообщение. Оно сохранено; пожалуйста, повторите вопрос немного позже.

`understanding_failed`; 16495 ms; SQLite reopen = True.

## live-integrated-kb_cloud_boundary

### kb_cloud_boundary / 1

Клиент: У нас aQsi Online. Можно ли подключить её к 1С:УНФ через приложение интегратора для физической кассы aQsi?

Ответ дословно:

> Для этой задачи в «aQsi Online» не нашёл подтверждённой применимой инструкции в базе знаний. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

`insufficient_applicable_evidence`; 9014 ms; SQLite reopen = True.

## live-integrated-kb_directbank

### kb_directbank / 1

Клиент: В 1С:ДиректБанк нужно настроить автоматическое получение банковских выписок. С чего начать?

Ответ дословно:

> 1. Выяснить версию конфигурации и подключён ли 1С:ДиректБанк.
> 2. Проверить, поддерживает ли банк автоматическое получение выписок.
> 3. Открыть: в простом интерфейсе — «Настройки → Основное → Настройки программы → Обмен электронными документами → Обмен с банками → Настройки обмена с банками», в полном — «Администрирование → Настройки программы → Обмен электронными документами → Обмен с банками → Настройки обмена с банками».
> 4. Для включения автоматической выписки перейти на вкладку "Автоматическая выписка" → "Включить", указать логин и пароль, используемые при обмене с банком, и дату, начиная с которой нужно выгрузить документы.
> 5. Для автоматического создания не найденных в программе карточек контрагентов, расчетных счетов, договоров установить галочку "Создавать отсутствующие элементы" на вкладке "Автоматическая выписка".
> 6. Чтобы проводились документы, заполненные при загрузке без ошибок, установить галочку "Проводить документы" на вкладке "Автоматическая выписка".
> 7. Для задания своего расписания автоматического получения выписки установить флажок "Расширенная настройка" на вкладке "Автоматическая выписка" и указать свое расписание.
> 8. Сопоставить интервалы получения с реальным временем формирования выписок в банке.
> 9. При расхождениях открыть журнал банковских документов, сверить даты, суммы и номера платежей с оригиналом.
> 
> Дополнительное условие источника (Когда нужен специалист):
> Если автоматическая синхронизация недоступна у банка или операции появились дважды. Не удалять проведённые платежи до сверки.
> 
> Источник: data/knowledge/1c/bank/directbank-auto-schedule.md — Что проверить

`source_first_exact_section`; 6798 ms; SQLite reopen = True.

Источник: `1c/bank/directbank-auto-schedule.md` / `Подтверждённая возможность` — [оригинал](https://buh.ru/news/samoe-novoe-v-1s-bukhgalterii-8-nastroyki-avtomaticheskogo-polucheniya-bankovskoy-vypiski-cherez-1s-.html).

Источник: `1c/bank/directbank-other-banks.md` / `Диагностика` — [оригинал](https://buh.ru/articles/kak-v-1s-bukhgalterii-8-zagruzhat-vypiski-v-servise-1s-direktbank-iz-drugikh-bankov-cherez-bank-posr.html).

Источник: `1c/bank/import-file-directbank.md` / `Подтверждённая возможность` — [оригинал](https://buh.ru/news/samoe-novoe-v-1s-bukhgalterii-8-zagruzka-bankovskoy-vypiski-iz-fayla-pri-podklyuchennom-1s-direktban.html).

## live-integrated-kb_eou_missing

### kb_eou_missing / 1

Клиент: Эвотор 7.3: в диагностическом отчёте приложение EoU — «Не найдено». Интернет есть. Что делать?

Ответ дословно:

> Что именно перестало работать — печать чека, передача данных или другое? Если появится точный текст на экране, пришлите его.

`selected_error_code_unconfirmed`; 16694 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-210.md` / `Шаг 1. Если торгуете маркированными товарами` — [оригинал](https://support.evotor.ru/article/360004715693).

Источник: `evotor/settings/time-mismatch-first-checks.md` / `1. «Ошибка при работе с кассой (3922). Дата и/или время в ККМ меньше, чем в ЭКЛЗ/ФН»` — [оригинал](https://support.evotor.ru/article/360010106933).

Источник: `evotor/fn/fn-234.md` / `Если смена закрыта` — [оригинал](https://support.evotor.ru/article/360005580254).

Источник: `evotor/fn/fn-212.md` / `Если смарт-терминал зарегистрирован в ФНС` — [оригинал](https://support.evotor.ru/article/360016100393).

## live-integrated-kb_fn234_followup

### kb_fn234_followup / 1

Клиент: Эвотор 7.3, ошибка ФН 234. Что сначала проверить?

Ответ дословно:

> В подходящем разделе есть ответственная операция. Не буду публиковать её порядок; запросите специалиста.

`unsafe_source_section`; 7076 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-234.md` / `Если смена закрыта` — [оригинал](https://support.evotor.ru/article/360005580254).

### kb_fn234_followup / 2

Клиент: Дата и время верны. Смена закрыта. Ошибка не исчезла. Что дальше?

Ответ дословно:

> В подходящем разделе есть ответственная операция. Не буду публиковать её порядок; запросите специалиста.

`unsafe_source_section`; 4789 ms; SQLite reopen = True.

Источник: `evotor/fn/fn-234.md` / `Если смена закрыта` — [оригинал](https://support.evotor.ru/article/360005580254).

## live-integrated-kb_missing

### kb_missing / 1

Клиент: На кассе ошибка. Что делать?

Ответ дословно:

> Что именно перестало работать — печать чека, передача данных или другое? Если появится точный текст на экране, пришлите его.

`error_code_scope_unconfirmed`; 5382 ms; SQLite reopen = True.

### kb_missing / 2

Клиент: Модель и код сейчас не знаю.

Ответ дословно:

> Понял, точный код ошибки сейчас неизвестен. Чтобы продолжить без догадок о коде, уточните, какое действие не проходит и какой результат вы видите. Если результат меняется от попытки к попытке, опишите оба варианта.

`error_code_scope_unconfirmed`; 5938 ms; SQLite reopen = True.

## live-integrated-kb_specialist

### kb_specialist / 1

Клиент: Хочу поговорить со специалистом поддержки.

Ответ дословно:

> Чтобы оформить заявку, сначала напишите вопрос в этом диалоге.

`None`; 9 ms; SQLite reopen = True.

## live-integrated-kb_tax_withdrawn

### kb_tax_withdrawn / 1

Клиент: Для УСН какие пороги освобождения от НДС действуют в 2027 и 2028 годах?

Ответ дословно:

> Не удалось проверить выбор evidence. Запросите специалиста.

`semantic_selector_failed_closed`; 20186 ms; SQLite reopen = True.

Источник: `accounting/vat_usn/exemption-threshold-2026.md` / `Проверенные правила 2026 года` — [оригинал](https://www.nalog.gov.ru/rn77/taxation/taxes/nds_usn/).

Источник: `accounting/usn/usn-nds-trigger-2026.md` / `Краткий ответ` — [оригинал](https://www.nalog.gov.ru/rn77/taxation/taxes/nds_usn/).

Источник: `accounting/usn/usn-nds-invoice-2026.md` / `Общее правило` — [оригинал](https://www.nalog.gov.ru/rn77/taxation/taxes/nds_usn/).

## live-integrated-pilot_evotor6

### pilot_evotor6 / 1

Клиент: У меня Эвотор 6, нужно повторно распечатать старый чек. Номер ФД есть. Как это сделать?

Ответ дословно:

> В approved-источниках не нашёл подтверждённого ответа именно на запрошенную часть вопроса. Запросите специалиста.

`semantic_composer_irrelevant_evidence`; 11586 ms; SQLite reopen = True.

Источник: `evotor/cash/evotor-6-receipt-copy.md` / `Как распечатать копию` — [оригинал](https://support.evotor.ru/article/360005002514).

## live-integrated

### kb_greeting / 1

Клиент: Привет! Как ты можешь помочь владельцу небольшого магазина?

Ответ дословно:

> В найденных approved-источниках нет подтверждённого ответа именно на этот вопрос. Запросите специалиста.

`semantic_selector_no_evidence`; 4816 ms; SQLite reopen = True.

Источник: `aqsi_devices/errors/goods-not-on-device.md` / `Проверенная информация и первичная диагностика` — [оригинал](https://aqsi.ru/tehnicheskaya-podderzhka/baza-tovarov-ne-otobrazhaetsya-na-kasse/).

Источник: `aqsi_online/setup/add-store.md` / `Вопрос клиента` — [оригинал](https://aqsi.online/instructions/getting-started/kak-dobavit-magazin).

Источник: `atol_online/connection/add-shop-step3.md` / `Вопрос пользователя` — [оригинал](https://help.atol.online/article/12161).

### kb_greeting / 2

Клиент: Спасибо. А как проходит твой день?

Ответ дословно:

> Какой сервис используется?

`semantic_selector_clarification`; 3590 ms; SQLite reopen = True.

Источник: `aqsi_online/setup/add-store.md` / `Вопрос клиента` — [оригинал](https://aqsi.online/instructions/getting-started/kak-dobavit-magazin).

Источник: `aqsi_devices/errors/goods-not-on-device.md` / `Проверенная информация и первичная диагностика` — [оригинал](https://aqsi.ru/tehnicheskaya-podderzhka/baza-tovarov-ne-otobrazhaetsya-na-kasse/).

Источник: `atol_online/connection/add-shop-step3.md` / `Вопрос пользователя` — [оригинал](https://help.atol.online/article/12161).

### ofd / 1

Клиент: Что такое ОФД?

Ответ дословно:

> Область источника: АТОЛ Онлайн — облачная ККТ.
> ОФД (оператор фискальных данных) — это сервис, который обеспечивает передачу зашифрованных фискальных данных (чеков) от онлайн‑кассы в налоговую инспекцию.
> 
> Источник: data/knowledge/atol_online/ofd/what-is-ofd.md — Что проверено по инструкции производителя

`semantic_evidence_composer`; 12477 ms; SQLite reopen = True.

Источник: `atol_online/ofd/what-is-ofd.md` / `Вопрос пользователя` — [оригинал](https://help.atol.online/article/11256).

Источник: `aqsi_devices/ofd/connection-fields.md` / `Проверенная информация и первичная диагностика` — [оригинал](https://aqsi.ru/support/ofd-2/).

Источник: `aqsi_online/ofd/taxcom-account.md` / `Что можно объяснить и проверить` — [оригинал](https://aqsi.online/instructions/ofd/kak-zaregistrirovatsya-v-lichnom-kabinete-ofd-takskom).

### exp2_d01_partial_internet / 1

Клиент: Эвотор не передаёт чеки в ОФД. Как разобраться?

Ответ дословно:

> В верхней части экрана появляется сообщение **«(!) ОФД»**. Это означает, что Эвотор подключён к интернету, но **не может отправить чеки в ОФД больше 24 часов**. Решение зависит от модели.
> 
> Дополнительное условие источника (Когда передавать специалисту):
> Если EoU отсутствует, не выполняйте самостоятельно технологическое обнуление или произвольные кассовые команды. Вендор описывает эти действия, но они требуют контролируемой диагностики. Если сеть, реквизиты ОФД и оплата в порядке, а чеки не уходят — направьте в поддержку кассы или ОФД.
> 
> Источник: data/knowledge/evotor/ofd/ofd-unable-to-connect.md — Признаки

`source_first_exact_section`; 14173 ms; SQLite reopen = True.

Источник: `evotor/ofd/evotor-6-ofd-connection.md` / `Как проявляется` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Когда передавать специалисту` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Как проявляется` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

### exp2_d01_partial_internet / 2

Клиент: Касса Эвотор.

Ответ дословно:

> Этот раздел инструкции я уже привёл. Для следующей применимой проверки укажите точную модель оборудования.

`grounded_section_followup_scope_needed`; 16546 ms; SQLite reopen = True.

Источник: `evotor/ofd/evotor-6-ofd-connection.md` / `Как проявляется` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Когда передавать специалисту` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Как проявляется` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-settings-check.md` / `Что сверить` — [оригинал](https://support.evotor.ru/article/5965166793746).

### exp2_d01_partial_internet / 3

Клиент: В интернет касса выходит. Что ещё можно проверить?

Ответ дословно:

> Этот раздел инструкции уже приведён, а следующего подтверждённого шага для вашего случая не нашёл. Запросите специалиста кнопкой ниже.

`grounded_section_followup_exhausted`; 18357 ms; SQLite reopen = True.

Источник: `evotor/ofd/ofd-unable-to-connect.md` / `Шаг 5. Когда обращаться в поддержку Эвотора` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-7-3-ofd-connection.md` / `Как проявляется` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/evotor-6-ofd-connection.md` / `Как проявляется` — [оригинал](https://support.evotor.ru/article/360014099534).

Источник: `evotor/ofd/ofd-subscription.md` / `Возможная причина` — [оригинал](https://support.evotor.ru/article/8865646794770).

### exp2_d03_unknown_code / 1

Клиент: После продажи касса иногда ругается, но я не успеваю прочитать ошибку.

Ответ дословно:

> Что именно происходит с кассой? Напишите, пожалуйста, текст ошибки или какой результат вы видите.

`dialogue_state_task_incomplete`; 3549 ms; SQLite reopen = True.

### exp2_d03_unknown_code / 2

Клиент: После продажи касса иногда ругается, но я не успеваю прочитать ошибку.

Ответ дословно:

> Какой результат вы хотите получить?

`dialogue_state_task_incomplete`; 4494 ms; SQLite reopen = True.

### exp2_d03_unknown_code / 3

Клиент: Это Эвотор 7.3. Проблема возникает не каждый раз.

Ответ дословно:

> Пока не удалось определить задачу. Можно оформить заявку специалисту кнопкой ниже; доставка сотруднику пока не настроена.

`dialogue_task_remains_undefined`; 4416 ms; SQLite reopen = True.

### exp2_d03_unknown_code / 4

Клиент: Код ошибки не знаю. Как нам дальше разобраться?

Ответ дословно:

> Временно не удалось разобрать сообщение. Оно сохранено; пожалуйста, повторите вопрос немного позже.

`understanding_failed`; 15257 ms; SQLite reopen = True.

