# KB Sprint 3 — factual coverage and draft review

**Дата:** 2026-10-28. **Результат:** локальная подготовка; остановка до approval/Stage3. Внешние LLM не использовались. Исходный TXT не копировался и в этот отчёт не выводился. Production Python, `data/knowledge`, Qdrant, SQLite, worker, `.env` и Git history не менялись; новые материалы находятся в `reports/kb_quality_sprint_20261028/sprint3_candidates/` со статусом `draft`.

## 1. Основание и ограничения

Из предыдущего аудита: 570 строк, темы с повторами и точными вариантами: ККТ 79/77, ЭДО 52/18, маркировка 42/42, эквайринг 34/33, Эвотор 31/30, доступ/продление 28/27, ТС ПиОТ 17/16, БИФИТ 14/13, АТОЛ 9/8. Темы перекрываются; варианты — точные нормализованные фразы, а не доказанные семантические кластеры; выборка не объявляется репрезентативной.

Дополнительно вручную просмотрен high-signal срез уже локально обезличенного остатка `manual_review_required` (111 уникальных примеров в безопасном evaluation файле из 223 строк) и сопоставлен с выбранными scenario IDs `KBQS2-02`, `05`, `06`, `08`, `15–17`, `20`, `23–25`, `31`, `35`, `38`, `41`, `44–47`, `50`. Это не исчерпывающая разметка исходных 291 обращений и не новый независимый набор; полный остаток не был повторно размечен. Срез подтвердил существенные типы работы: настройка банковского терминала и маршрута оплаты; тестирование БИФИТ Общепит; подпись УПД и подтверждение накладной ЕГАИС; выдача/смена ключей; диагностика маркировки, ОФД и кассового сбоя; подключение ТС ПиОТ; получение ЭДО-документов. Персональные статусы покупки/лицензии и сроки ОФД относятся к CRM/ЛК, не к KB. Подписать/подтвердить/отправить документ — действие полномочного пользователя, не техническое знание.

В approved корпусе 206 статей из 269 markdown файлов. Поиск дерева файлов, YAML и статусов показал точечное одобренное покрытие для кассовой диагностики, Эвотор маркировки/ОФД, Диадок/1С ЭДО и aQsi physical scanner. Папки `tspiot` в текущем corpus содержат draft, а не approved coverage. Для БИФИТ отдельной approved первой линии не найдено. Общие инструкции нельзя считать доказательством для неподтверждённой модели или внешнего статуса.

Полная gap-матрица: [sprint3_gap_matrix.csv](sprint3_gap_matrix.csv).

## 2. Сопоставление coverage и решений

| Сценарий | Частота в выборке (упоминания / точные варианты темы) | Approved coverage и gap | Поведение бота |
|---|---:|---|---|
| ККТ не работает/чек/смена | 79 / 77 | Точечные инструкции есть, общего безопасного triage нет | Одно уточнение: модель и точный симптом/код; затем only matching approved. Нет ветки — специалист. |
| ЭДО/УПД/документ не принят | 52 / 18 | Есть отдельные интеграции/контрагент/маркированные товары; нет доказанной общей status flow для Диадок и Saby в web UI | Оператор + входящий/исходящий + точный статус; общий FAQ можно отвечать сразу. Не подписывать/не переотправлять. |
| Маркировка/сканер/кассовый отказ | 42 / 42 | Уже есть approved Эвотор маркировка и физический aQsi scanner. Широкая новая статья вероятно дублирует | Уточнить точный статус, единичный/массовый случай и модуль. Не пропускать код; только safe read-only статус. |
| Эквайринг/банк/канал оплаты | 34 / 33 | Есть узкие accounting/acquiring статьи, но нет pairing/route guide | Уточнить кассу, терминал, ПО банка и точку отказа. Платёж/зачисление — эквайер. Никаких тестовых списаний или смены реквизитов. |
| Эвотор | 31 / 30 | Сильное точечное coverage, но не общий «не работает» ответ | Модель/ПО/код → точная approved branch; широкое слово не основание для инструкции. |
| Доступ/покупка/продление | 28 / 27 | Статус пользователя/оплаты нельзя знать из KB | Только разрешённый CRM/ЛК lookup, иначе сотрудник. |
| ТС ПиОТ | 17 / 16 | Нет approved общих клиентских процедур, источники связаны с разными конкретными модулями | Идентифицировать производителя/модуль/версию/безопасный код; если неизвестно, specialist. |
| БИФИТ Касса/Общепит | 14 / 13 | Нет approved first-line материала; источники подтверждают только отдельные функции | Развести web-бронирование vs POS-столы; терминал vs банковский отказ; запрос статуса инженера — сотрудник/CRM. |
| АТОЛ Онлайн API: оплата есть, чека не видно | 9 / 8 | Есть API test/errors и журнал чека, но нет полного incident route; старый candidate смешивал search+diagnosis | Сначала не повторять операцию. Уполномоченный интегратор проверяет exact status и историю в журнале. Только конкретный `Таймаут` имеет узкое документированное условие; другие статусы — handoff. |

### Не-knowledge задачи

- «Подпишите/подтвердите УПД/ЕГАИС», «выбейте чек коррекции», «замените ФН/ключи» — действие сотрудника/полномочного лица; немедленно передать компетентному сотруднику и не выполнять из KB.
- «Отобразите покупку», «когда кончится ОФД», «продлите лицензию», «инженер не позвонил» — авторизованный CRM/ЛК lookup или специалист. Новая статья не решит персональный статус.
- «Какой у меня патент/сколько платить» — бухгалтерская проверка, требуется контекст организации и налогового периода; только общий FAQ может быть публичным.

## 3. Draft review: 8 сценариев

Все 8 файлов полностью прочитаны, YAML разобран `DocumentLoader`, source URL HTTPS, date fields валидны, статус каждого `draft`; metadata приведена через `normalize_metadata`. Текст `Уточнить модель` и подобные фразы не записаны в `model/version`; неизвестные значения равны YAML `null`. Отсутствие allowlist для task_category в runtime означает, что YAML parse и passthrough ещё не доказывают прикладную совместимость.

| Файл | Задача и первичный источник | Review / решение |
|---|---|---|
| [01 АТОЛ API](sprint3_candidates/01-atol-api-receipt-not-found.md) | [АТОЛ errors](https://help.atol.online/article/22561) и [Журнал чеков](https://help.atol.online/article/22560) | Additive incident route, но `receipt_search` и `error_diagnosis` нельзя соединять одной операцией. В draft оставлен только `diagnose_error`; журнал — read-only контроль. Ограниченный retry только для точного `Таймаут`, только интегратором. SME approval нужна. |
| [02 БИФИТ POS-терминал](sprint3_candidates/02-bifit-pos-terminal-scope.md) | [БИФИТ: модели POS/PIN и банковская роль](https://kassa.bifit.com/faq/equipments/pos_term.html) | Источник подтверждает ответственность, перечень зависит от модели/ОС/банковского ПО. Подтверждённого технического pairing/troubleshooting нет. Только boundary triage; approval условный. |
| [03 БИФИТ столы](sprint3_candidates/03-bifit-horeca-tables-scope.md) | [БИФИТ: web-бронирование, залы и столы](https://kassa.bifit.com/wiki/index.php?title=%D0%91%D1%80%D0%BE%D0%BD%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5) | Источник про web-кабинет, не POS план зала/тестирование. Staging чрезмерно принял его для реального неуточнённого запроса. Не принимать до content/scope и routing исправления. |
| [04 Диадок status](sprint3_candidates/04-diadoc-outgoing-status.md) | [Контур: не найден исходящий документ](https://support.kontur.ru/diadoc/87974-kak_najti), [состояния](https://developer.kontur.ru/doc/diadoc-api/instructions/statuses.html) | Официальный read-only поиск статуса/истории подтверждён. В текущем runtime query «проверить статус УПД» не совпало с `exchange_edo_documents`; документ не стал final evidence. Нужны owner routing review, не специальное исключение в pipeline. |
| [05 Saby incoming](sprint3_candidates/05-saby-incoming-status.md) | [Saby: входящие документы](https://saby.ru/help/edo/in) | Подтверждены папки «Входящие» и «Требуют обработки», не конкретная доставка/статус. Staging на русском «не могу найти входящий документ» выбрал ОФД receipt evidence; candidate в final не прошёл. Явная pipeline misroute. |
| [06 Эвотор маркировка отказ](sprint3_candidates/06-evotor-marking-refusal.md) | [Эвотор: онлайн-проверка кодов маркировки](https://evotor.ru/news/proveryajte-kody-markirovki-ne-othodya-ot-kassy/), 2023-07-20 | Source-backed taxonomy причин, но старый материал и уже есть approved `evotor-mark-check-error-20261019`/`evotor-marked-goods-upd-20261019`. Дубликат; не включать в batch без доказанного incremental claim. |
| [07 Эвотор Combo Payment](sprint3_candidates/07-evotor-combined-payment.md) | [Руководство модуля Эвотор](https://support.evotor.ru/api/article/file/6052) | Компактный FAQ по нескольким частям оплаты; версия/модель источника не установлены. Нельзя использовать как инструкцию смены банка/счёта. State machine признал relationship unresolved для простого FAQ; пока pipeline blocker, не готов к индексации. |
| [08 ТС ПиОТ API scope](sprint3_candidates/08-tspiot-api-scope.md) | [Эвотор Digital Cash API для ТС ПиОТ](https://docs.evotor.cloud/docs/markirovka/marking-api) | Источник для разработчика конкретной цифровой кассы, не клиентская инструкция по установке. Хотя кандидат попал в final evidence на общем запросе «как диагностировать ТС ПиОТ», он не содержит подтверждённого ремонта. Пригоден только как gap/boundary для SME, не для answer-bearing KB. |

## 4. Staging evaluation (baseline vs draft overlay)

Выполнено текущим `DocumentLoader`, `DialogueManager`, `build_rag_query`, `RetrieverRAGAdapter` и `QdrantClient(':memory:')`: 206 approved baseline documents + 8 drafts (в памяти присвоен approved только для эмуляции отбора). Сохранён harness [stage_sprint3_candidates.py](../../scripts/stage_sprint3_candidates.py) и [полный JSON](sprint3_staging_results.json). Production Qdrant/KB не открывались, никаких файлов из `data/knowledge` не меняли. LLM calls = 0.

- 8 позитивных candidate prompts: 6 дошли до retrieval; 4/6 ожидаемых документов были в raw top-K; только 3/6 стали final evidence (БИФИТ web-столы, маркировка, ТС ПиОТ). Это retrieval/evidence eligibility, не качество готового ответа.
- Положительные провалы: BИФИТ терминал был в top-K, но final evidence не выбрано; Диадок был в top-K, но task mismatch; Saby candidate был в top-K, final evidence остался нерелевантными документами поиска кассовых чеков; простые ATOL API и Combo FAQ не прошли relation resolution; TSPiOT final evidence было выбрано при отсутствии подтверждённого пользовательского шага — ложная достаточность.
- 4 negative pairs: два неверных сервисных кандидата попали в raw top-K; один candidate маркировки Эвотор также попал в final evidence для отрицательного запроса по кассовому банковскому терминалу — реальный cross-service false positive. Отрицательная матрица — NO-GO.
- 4 anonymized real prompts из предыдущего набора: 1 получил новый candidate final evidence — БИФИТ «протестировать Общепит со столами», хотя source only web booking; это потенциально ложный ответ. 3/4 real prompts сохранили точный final set baseline/staging. Для маркировки draft не добавил final evidence, потому что его уже даёт approved. Для общего ЭДО исходный запрос не разрешился/не получил final evidence. Для неизвестного терминала final set остаётся нерелевантным.

Staging не доказывает роста самостоятельных решений. Напротив, выявлены routing/evidence gaps: запрос Диадок классифицируется в несовместимую операцию, Saby «входящий документ» маршрутизируется как receipt search, простой FAQ/новая задача вызывает `Message relationship is unresolved`; broad Bifit query допускает нерелевантное sufficiency, а cross-service коды пропускаются в final evidence. Эти проблемы фиксируются для последующего pipeline этапа, но код сейчас не менялся.

## 5. Первые предложения и следующая очередь

**Для совместного SME/product review (ещё не approval):**

1. АТОЛ Онлайн API missing receipt — разделить журнал (read-only) и конкретный status handling; подтвердить API версии/источник, срок «Таймаут», кто уполномочен повторить.
2. БИФИТ терминалы — владелец должен назвать текущие ОС/модели POS и banking app; без точного руководства оставить только handoff boundary.
3. БИФИТ web booking vs POS tables — разделить реальные продукты и версии; текущий документ недостаточен для вопроса из sample.
4. Диадок/Saby incoming/outgoing status — владелец выбирает ведущие операторы; добавить только операторские read-only статусы, отдельно test на retrieval intent.

**Не включать в первую approved партию:** повторный материал маркировки Эвотор (дубликат); общая TSPiOT диагностика по developer API (не клиентская инструкция); комбинированная оплата без версии и разрешённой задачи (pipeline query unresolved). Ни один из восьми пока не получил доказанное улучшение final evidence без риска ложного ответа. Следующее пополнение после SME входа: EDO status matrix; БИФИТ Общепит install/version-specific guide; POS acquiring compatibility matrix; ТС ПиОТ vendor+module specific; ATOL API safe status flow. Сначала запросить official source/material для ЭДО Лайт, ЕГАИС incoming TTN, firmware/service category after ATOL update, ATOL/Shtirh exact marking refusal, card-vs-QR routing per acquirer.

## 6. Уточнения и handoff contract

| Сценарий | Одно следующее уточнение | Подтверждённая проверка | Остановиться/передать | Факты в handoff |
|---|---|---|---|---|
| ATOL API | Какой точный безопасный статус запроса выдал интегратор? | Интегратор ищет чек в журнале и сверяет историю повторов | Неизвестный статус, нет записи, был retry, есть риск дубликата/коррекции | сервис/API версия, статус, время, журнал найден/нет, attempts; без payload/token/payment IDs |
| БИФИТ терминал | Какая модель терминала и ОС кассы? | Сверить совместимость в FAQ; проверить только видимость устройства и этап отказа | Модели нет/устройство не видит → БИФИТ; банковский отказ → эквайер | модель/ОС/banking app, transport type, safe error, стадия; без платежных данных |
| БИФИТ столы | Web бронирование или столы внутри POS/план зала? | Только для web — наличие раздела бронирования | POS/table map, отсутствующий раздел, пакет неизвестен → БИФИТ | приложение/версия, web vs POS, цель и видимость раздела |
| Диадок | Документ в «Исходящих» и какой текущий статус? | Проверить статус и историю, не менять документ | Не найден/ошибка/нужна подпись или аннулирование → сотрудник/оператор | operator, type, direction, status, timestamp, safe error; без содержимого/ЭП |
| Saby | В каком операторе/кабинете ищете и какой тип документа? | Saby: «Документы → Входящие» / «Требуют обработки» | Нет в обеих папках → sender/operator check | оператор, type, folder, time, sender confirms dispatched; без файла/PII |
| Эвотор маркировка | Точный текст отказа и один код или разные товары? | Только read-only статус марки/документы приёмки | Не обходить запрет; массово/неизвестный модуль → ЧЗ/Эвотор/ТС ПиОТ | модель/version, module, safe error, single vs multiple, check outcome; без full code |
| Combo payment | Нужен общий ответ о split tender или смена маршрута банка? | Руководство описывает несколько частей в одном чеке (при наличии модуля) | Реальная продажа, account route, reversal/refund → сотрудник/банк | модель/module/version, цель, operation stage; без account/payment data |
| ТС ПиОТ | Какой производитель и точное название/версия модуля? | Доступный API относится только к Digital Cash Эвотор и разработчику | Иной/неизвестный модуль — specialist; не следовать developer API как UI шагам | ККТ, OS, module/version, safe error; без токена/кода |

Multi-turn evaluation: [sprint3_multiturn_scenarios.jsonl](sprint3_multiturn_scenarios.jsonl), 8 flows; `real_sample` initial turns reference safe case IDs, follow-ups are synthetic. No external LLM assessment performed. Handoff code intentionally unchanged.

## 7. Runtime compatibility and remaining issues

All eight drafts parse. Observed normalized metadata: `error_diagnosis/diagnose_error`; `peripheral_setup/configure_peripheral`; `settings/configure_settings`; `edo/exchange_edo_documents`; `marking/check_marking_code`; `sales/process_sale`; `tspiot/diagnose_tspiot`. The normalizer preserves categories without a strict allowlist, so syntactic normalization does not guarantee routing. Evidence: Diadok query did not map `check status` into `exchange_edo_documents`; Saby query mapped to `receipt_search`; ATOL and combo FAQ failed relation resolution. Do not add candidate-specific production exceptions. `receipt_search` and `error_diagnosis` remain separate; no candidate declares `search_receipt`.

## 8. Next decision

No new article is approved or indexed in production. User/SME should choose which four review topics above merit sourced product-owner review, and provide current BIФИТ models/versions, leading EDO operators, and vendor-specific TSPiOT docs. After that, update article scope/metadata and rerun the same isolated evaluation. Stage3/production switch remains unapproved; no commit/push.
