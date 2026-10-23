# RAG vNext: isolated CLI experiment, 23.10.2026

## Setup and scope

- LangGraph graph: `understand → retrieve → respond`, with a shortcut to one clarification. `MemorySaver` keeps exact user turns, the original active problem, confirmed user quotes and questions already asked. Assistant guesses are absent from `confirmed_quotes`.
- Groq `openai/gpt-oss-20b`, reasoning `medium`; Qdrant `knowledge_stage3_retrieval_20261022` (934 points, 672 approved); embedding `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Both algorithms ran with this same collection, approved status, model and effort.
- vNext reads Qdrant directly, selects broad dense candidates, then reads sibling chunks. No production task/operation gate, LexicalAnalyzer, Telegram integration, index write or worker change. Exact source quotes, service/model scope, grounding and dangerous fiscal operation checks guard final claims.
- The baseline is the **current local production algorithm replayed offline** with the same seven ordered scenarios and a separate `.local` SQLite file. It is not the historical Telegram worker binary. Historical Telegram observations come from `docs/PROJECT_STATE.md` and read-only conversation inspection.
- The original live OFD case had one new user message after a prior DirectBank conversation. The main seven-scenario suite includes that exact OFD message followed by an explicitly synthetic clarification about the paid period. A separate exact-user-turn replay of the prior DirectBank messages and OFD switch is in `scenario-ofd-live-history.json`.

## Scorecard

| Measure, 15 turns / 7 scenarios | vNext | Current pipeline, offline Stage3 |
|---|---:|---:|
| Groq calls | 20 | 6 |
| Provider tokens reported | 30,316 | 11,295 |
| Median response time, including deliberate rate pacing | 18.3 s | 0.38 s |
| 90th-percentile observed response time | 67.7 s | 18.2 s |
| Original five support problems resolved | 0/5 | 0/5 |
| Positive controls with at least one useful documented step | 0/2 | 2/2, both with errors or omissions |

**Human review:** vNext preserved the active user problem and handled the explicit topic switch. It did not improve the client outcome. DirectBank received a partial, tangential check only after the second message. The unspecified FN request remained free of a dangerous procedure, but the first response was in English and the second asked about OFD instead of the FN action/equipment. Both positive controls failed despite applicable approved articles. The current pipeline returned useful source-backed steps on those controls, but its first Platforma receipt answer incorrectly said the FD filter was unconfirmed, and its Platforma contract answer switched to unrelated fiscal-document amounts. Neither algorithm is ready for a Telegram pilot.

## Retrieval diagnosis without additional Groq calls

| Direct approved control document | Dense rank among approved chunks | Current hybrid rank |
|---|---:|---:|
| `platformaofd-lkk-receipt-search` for a direct FD receipt question | 49 | 7 |
| `aqsi-online-account-add-user` for adding an aQsi user | 51 | 3 |
| `batch-20261013-bank-directbank-all-accounts` for DirectBank | 2 | 2 |

The vNext broad dense stage kept six top documents, so it excluded both positive-control articles before applicability or grounding could evaluate them. DirectBank shows a different bottleneck: the article was retrieved and marked usable, but the first generated claim failed exact quote grounding. After the service clarification, the model answered with a partially relevant automatic/multi-account check and asked whether DirectBank was enabled although the user had confirmed the connection. The contract-expiration question has no directly matching approved instruction in a read-only scan; `platformaofd-tariff-activation` supports checking a tariff for a KKT, not the contract's legal end date.

## Relation to the actual Telegram test

| Problem | Live Telegram 23.10 | vNext in this experiment | Blocking stage |
|---|---|---|---|
| Paid OFD period | Generic ambiguity with stale DirectBank state; no RAG/LLM | New problem retained, but generic limitation and no actionable paid-period check | Knowledge gap, poor next question; exact-history replay below |
| DirectBank outage | Wrong list operation, then no context after service clarification | Applicable approved article found; first claim rejected by grounding, second answer only partial | Claim/evidence generation and goal selection |
| Unspecified FN change | First reply suggested registration-related steps, repeat refused | No dangerous procedure, but English answer with speculative examples, then unrelated service question | Clarification quality and language control |
| Switch to restricted employee access | Failed to carry the restriction into a useful service clarification | Topic switch and restriction retained in state; no service-specific answer | Answer/clarification choice with unknown service |
| Platforma OFD contract term | No context after service given | No invented contract navigation; repeated generic limitation | Direct approved knowledge gap; retrieval also poor |

The historical Telegram run preceded the later verified Stage3 worker switch and its exact source snapshot could not be fully attested at the time. The offline baseline above is the controlled same-collection comparison; the live outcomes are operational context, not a paired same-configuration measurement.

The controlled diagnostic work made **44 Groq attempts** in total across an initial failed run, one interrupted iteration, the completed main comparison and exact-history replay; one attempt returned HTTP 429. The saved turn receipts account for at least 74,665 tokens. One successful understanding call in the failed run has no persisted usage receipt. The 20-vs-6 call comparison above refers only to the completed main suite.

## Turn-by-turn evidence

For every turn below, `documents` are approved candidates, **not** automatically applicable. `usable`, `partial`, `incompatible`, and `unassessed` refer to the model's applicability evaluation after the local service/model check. The complete candidate-level data, times, token usage, decisions, and memory are in `results.json`; the paired current-pipeline traces are in `baseline-results.json`.

### 1. Окончание оплаченного периода ОФД

**1.1 Клиент:** у меня проблема кончился офд

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?

**Подобранные approved-документы / применимость:**

- `atol-online-11075-fn-invoice` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `batch-20261013-closing-error-first-diagnostics` — incompatible; разделы: Безопасная диагностика без изменения базы, Запрещённое автоматическое действие, Передать специалисту.
- `aqsi-device-paper-print-retry` — incompatible; разделы: Когда передавать специалисту, Ограничения, Проверенная информация и первичная диагностика.
- `aqsi-kkt-error-115` — incompatible; разделы: Безопасная проверка, Возможные причины по базе aQsi, Эскалация.
- `evotor-fn-231-360005098974` — incompatible; разделы: Контекст ошибки, Проверка без изменения регистрации.
- `atol-online-22561-gateway-errors-timeout-128-protocol` — incompatible; разделы: Важно / когда передать специалисту, Подтверждённые сведения.

**LLM:** да, 1 выз.; 577 токенов; 1491 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — у меня проблема кончился офд; текущие реплики — у меня проблема кончился офд; подтверждённые цитаты — кончился офд; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Какое сообщение об ошибке вы видите при работе с ОФД? (2150 мс; LLM да).
**Ручная оценка:** Безопасное ограничение, но вопрос о сервисе не уточняет, что именно «кончилось».

**1.2 Клиент:** Уточняю: закончился оплаченный период ОФД. Что проверить сначала?

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи.

**Подобранные approved-документы / применимость:**

- `evotor-fn-235-360004715213` — incompatible; разделы: Признаки, Смысл и безопасная проверка.
- `platformaofd-lkk-cash-monitoring` — incompatible; разделы: Значение показателей, Ограничения, Просмотр списка касс.
- `atol-online-11075-fn-invoice` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `aqsi-online-setup-fiscalize` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `atol-online-11251-replacement-reasons` — incompatible; разделы: Важно / когда передать специалисту, Подтверждённые сведения.
- `atol-online-26774-advance-closing` — incompatible; разделы: Важно / когда передать специалисту, Подтверждённые сведения.

**LLM:** да, 1 выз.; 888 токенов; 24719 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — у меня проблема кончился офд; текущие реплики — у меня проблема кончился офд / Уточняю: закончился оплаченный период ОФД. Что проверить сначала?; подтверждённые цитаты — кончился офд / кончился оплаченный период ОФД; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Уточните, пожалуйста, какую именно операцию нужно выполнить и в каком сервисе. (376 мс; LLM нет).
**Ручная оценка:** Оплаченный период известен, однако клиент не получил ни проверки, ни нового осмысленного вопроса.

### 2. Не загружаются выписки DirectBank

**2.1 Клиент:** В 1С перестали загружаться банковские выписки. Как разобраться?

**vNext:** По найденным approved-фрагментам не подтверждается инструкция именно для вашей задачи.

**Подобранные approved-документы / применимость:**

- `batch-20261013-bank-directbank-other-banks` — incompatible, partial, usable; разделы: Диагностика, Ограничение, Подтверждённая возможность.
- `batch-20261013-bank-directbank-all-accounts` — usable; разделы: Безопасная диагностика, Передать специалисту, Подтверждённая возможность.
- `batch-20261013-taxes-ens-menu-2026` — unassessed; разделы: Подтверждённое изменение, Проверка, Эскалация.
- `batch-20261013-bank-acquiring-returns` — unassessed; разделы: Диагностика, Передать бухгалтеру, Подтверждённое изменение.
- `aqsi-device-fn-close-safety` — incompatible; разделы: Когда передавать специалисту, Ограничения, Проверенная информация и первичная диагностика.
- `aqsi-device-fn161-document-not-saved` — incompatible; разделы: Когда передавать специалисту, Ограничения, Проверенная информация и первичная диагностика.

**LLM:** да, 2 выз.; 6738 токенов; 33171 мс. **Выбор:** limitation: model_assessment.
**Grounding отклонил:** missing_usable_exact_evidence.
**Память:** исходная проблема — В 1С перестали загружаться банковские выписки. Как разобраться?; текущие реплики — В 1С перестали загружаться банковские выписки. Как разобраться?; подтверждённые цитаты — В 1С перестали загружаться банковские выписки. Как разобраться?; заданные вопросы — нет.
**Текущий pipeline на Stage3:** Для 1С не нашёл подтверждённых сведений по этому действию.  Не буду дополнять инструкцию неподтверждёнными шагами; при необходимости запросите специалиста. (357 мс; LLM нет).
**Ручная оценка:** Подходящая статья найдена; модель не выдала валидную цитату, поэтому полезный ответ потерян.

**2.2 Клиент:** У нас 1С:Бухгалтерия 3.0, подключение к банку через DirectBank.

**vNext:** Проверьте, включена ли функция загрузки выписок сразу по всем счетам в настройках 1С:ДиректБанк. Убедитесь, что ваш банк поддерживает автоматическое получение выписок через 1С:ДиректБанк. Неизвестно, включена ли функция загрузки по нескольким счетам и поддерживает ли банк автоматическое получение выписок. Какая версия 1С:Бухгалтерии 8 и включён ли 1С:ДиректБанк для вашего банка?

**Подобранные approved-документы / применимость:**

- `batch-20261013-bank-directbank-other-banks` — incompatible; разделы: Диагностика, Ограничение, Подтверждённая возможность.
- `batch-20261013-bank-directbank-all-accounts` — usable; разделы: Безопасная диагностика, Передать специалисту, Подтверждённая возможность.
- `batch-20261013-bank-directbank-auto-schedule` — usable; разделы: Когда нужен специалист, Подтверждённая возможность, Что проверить.
- `batch-20261013-bank-import-file-directbank` — incompatible; разделы: Безопасный порядок проверки, Когда нужен специалист, Подтверждённая возможность.
- `batch-20261013-bank-acquiring-returns` — incompatible; разделы: Диагностика, Передать бухгалтеру, Подтверждённое изменение.
- `aqsi-device-standard-refund` — incompatible; разделы: Когда передавать специалисту, Ограничения, Проверенная информация и первичная диагностика.

**LLM:** да, 2 выз.; 6894 токенов; 88130 мс. **Выбор:** partial_answer: Ответ основан на доступных фрагментах, но не подтверждён конкретными данными о конфигурации..
**Память:** исходная проблема — В 1С перестали загружаться банковские выписки. Как разобраться?; текущие реплики — В 1С перестали загружаться банковские выписки. Как разобраться? / У нас 1С:Бухгалтерия 3.0, подключение к банку через DirectBank.; подтверждённые цитаты — В 1С перестали загружаться банковские выписки. Как разобраться? / У нас 1С:Бухгалтерия 3.0, подключение к банку через DirectBank.; заданные вопросы — Какая версия 1С:Бухгалтерии 8 и включён ли 1С:ДиректБанк для вашего банка?.
**Текущий pipeline на Stage3:** Для 1С не нашёл подтверждённых сведений по этому действию.  Не буду дополнять инструкцию неподтверждёнными шагами; при необходимости запросите специалиста. (364 мс; LLM нет).
**Ручная оценка:** Есть частичная проверка, но она смещена к загрузке по всем счетам и расписанию; уточнение повторно спрашивает про включённый DirectBank.

### 3. Неопределённое изменение ФН

**3.1 Клиент:** Нужно изменить настройки фискального накопителя. Подскажите порядок действий.

**vNext:** No evidence on fiscal storage settings change procedures. Could you specify which settings of the fiscal storage you wish to modify (e.g., fiscal data retention period, server address, etc.)?

**Подобранные approved-документы / применимость:**

- `aqsi-online-fns-finish-reg` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-receipts-incorrect-105` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `batch-20261013-vat-usn-invoice-on-exempt` — incompatible; разделы: Для диагностики, Подтверждённое правило, Эскалация.
- `aqsi-online-setup-fiscalize` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `evotor-correction-receipt-scope-20261019` — incompatible; разделы: Безопасная рекомендация, Почему нельзя давать универсальную команду, Сначала уточните.
- `aqsi-kkt-error-126` — incompatible; разделы: Безопасная диагностика, Варианты возникновения в базе aQsi, Симптом.

**LLM:** да, 2 выз.; 2445 токенов; 86378 мс. **Выбор:** limitation: None of the provided fragments address fiscal storage configuration..
**Память:** исходная проблема — Нужно изменить настройки фискального накопителя. Подскажите порядок действий.; текущие реплики — Нужно изменить настройки фискального накопителя. Подскажите порядок действий.; подтверждённые цитаты — Нужно изменить настройки фискального накопителя. Подскажите порядок действий.; заданные вопросы — Could you specify which settings of the fiscal storage you wish to modify (e.g., fiscal data retention period, server address, etc.)?.
**Текущий pipeline на Stage3:** Что именно нужно изменить и какая касса используется? Укажите производителя и модель. (12 мс; LLM нет).
**Ручная оценка:** Процедура не выдана, но ответ на английском и содержит неподтверждённые примеры параметров.

**3.2 Клиент:** Нужно изменить настройки фискального накопителя. Подскажите порядок действий.

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?

**Подобранные approved-документы / применимость:**

- `aqsi-online-fns-finish-reg` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-device-fn-close-safety` — incompatible; разделы: Когда передавать специалисту, Ограничения, Проверенная информация и первичная диагностика.
- `aqsi-online-setup-fiscalize` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-receipts-incorrect-105` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `evotor-correction-receipt-scope-20261019` — incompatible; разделы: Безопасная рекомендация, Почему нельзя давать универсальную команду, Сначала уточните.
- `aqsi-kkt-error-126` — incompatible; разделы: Безопасная диагностика, Варианты возникновения в базе aQsi, Симптом.

**LLM:** да, 1 выз.; 739 токенов; 17055 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — Нужно изменить настройки фискального накопителя. Подскажите порядок действий.; текущие реплики — Нужно изменить настройки фискального накопителя. Подскажите порядок действий. / Нужно изменить настройки фискального накопителя. Подскажите порядок действий.; подтверждённые цитаты — Нужно изменить настройки фискального накопителя. Подскажите порядок действий.; заданные вопросы — Could you specify which settings of the fiscal storage you wish to modify (e.g., fiscal data retention period, server address, etc.)? / Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Что именно нужно изменить и какая касса используется? Укажите производителя и модель. (78 мс; LLM нет).
**Ручная оценка:** Повтор не вызывает опасной процедуры, однако вопрос об ОФД не уточняет действие с ФН и оборудование.

### 4. Смена темы на сотрудника с ограниченными правами

**4.1 Клиент:** Как узнать, какой ОФД подключён к моей кассе?

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?

**Подобранные approved-документы / применимость:**

- `platformaofd-atol-transmission-checks` — incompatible; разделы: Проверки из раздела «Неполадки и их устранение».
- `aqsi-device-connection-fields` — incompatible; разделы: Когда передавать специалисту, Ограничения, Проверенная информация и первичная диагностика.
- `aqsi-online-ofd-taxcom-account` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `atol-online-12473-integrator-settings` — incompatible; разделы: Важно / когда передать специалисту, Подтверждённые сведения.
- `platformaofd-fn-number-in-lkk` — incompatible; разделы: Где проверить, Граница операции.
- `platformaofd-shtrih-connection-checks` — incompatible; разделы: Базовая сверка, Граница инструкции.

**LLM:** да, 1 выз.; 631 токенов; 17924 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — Как узнать, какой ОФД подключён к моей кассе?; текущие реплики — Как узнать, какой ОФД подключён к моей кассе?; подтверждённые цитаты — Как узнать, какой ОФД подключён к моей кассе; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** В каком приложении или на какой кассе нужно это проверить? Укажите сервис, производителя и модель. (310 мс; LLM нет).
**Ручная оценка:** Без модели/сервиса кассы конкретный путь не подтверждён; вопрос об ОФД бесполезен клиенту, который пытается его определить.

**4.2 Клиент:** А теперь другой вопрос. Нужно добавить сотрудника в личный кабинет.

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?

**Подобранные approved-документы / применимость:**

- `aqsi-online-setup-company-details` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-account-add-user` — incompatible; разделы: Ограничения, Создать пользователя.
- `aqsi-online-receipts-incorrect-105` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-setup-sign-contract` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-fns-register-ooo` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-setup-order-cash-register` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.

**LLM:** да, 1 выз.; 1056 токенов; 18261 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — А теперь другой вопрос. Нужно добавить сотрудника в личный кабинет.; текущие реплики — А теперь другой вопрос. Нужно добавить сотрудника в личный кабинет.; подтверждённые цитаты — Нужно добавить сотрудника в личный кабинет; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** В каком сервисе вы используете личный кабинет? (73 мс; LLM нет).
**Ручная оценка:** Явная смена темы обнаружена; вопрос о сервисе уместен.

**4.3 Клиент:** Хочу, чтобы он мог просматривать документы, но не менять настройки.

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи.

**Подобранные approved-документы / применимость:**

- `aqsi-online-account-settings` — incompatible; разделы: Настройки, Ограничения.
- `atol-online-16568-step7-fn-activation` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `aqsi-online-account-add-user` — incompatible; разделы: Ограничения, Создать пользователя.
- `aqsi-online-account-monitoring` — incompatible; разделы: Ограничения, Просмотр статистики.
- `aqsi-online-account-create-role` — incompatible; разделы: Ограничения, Полномочия, Создать и назначить роль.
- `platformaofd-partner-kkt-diagnostics` — incompatible; разделы: Граница доступа, Данные для диагностики.

**LLM:** да, 1 выз.; 1049 токенов; 19265 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — А теперь другой вопрос. Нужно добавить сотрудника в личный кабинет.; текущие реплики — А теперь другой вопрос. Нужно добавить сотрудника в личный кабинет. / Хочу, чтобы он мог просматривать документы, но не менять настройки.; подтверждённые цитаты — Нужно добавить сотрудника в личный кабинет / Хочу, чтобы он мог просматривать документы, но не менять настройки.; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Уточните, пожалуйста, полное название ОФД или кассового сервиса. (111 мс; LLM нет).
**Ручная оценка:** Ограничение просмотра сохранено в памяти, но ответ не использует его и не задаёт следующего вопроса.

### 5. Срок договора Платформа ОФД

**5.1 Клиент:** Мне нужно проверить срок действия договора с ОФД. Как это сделать?

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?

**Подобранные approved-документы / применимость:**

- `evotor-fn-235-360004715213` — incompatible; разделы: Признаки, Смысл и безопасная проверка.
- `batch-20261013-counterparty-reconciliation-act` — incompatible; разделы: Первичная проверка, Суть, Эскалация.
- `batch-20261013-vat-usn-advances-2026` — incompatible; разделы: Подтверждённое изменение, Что проверить, Эскалация.
- `atol-online-11075-fn-invoice` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `evotor-time-mismatch-check-20261019` — incompatible; разделы: Безопасная диагностика, Признаки, Эскалация.
- `batch-20261013-closing-close-several-months` — incompatible; разделы: Подтверждённая возможность, Проверка перед действием, Эскалация.

**LLM:** да, 1 выз.; 548 токенов; 16375 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — Мне нужно проверить срок действия договора с ОФД. Как это сделать?; текущие реплики — Мне нужно проверить срок действия договора с ОФД. Как это сделать?; подтверждённые цитаты — проверить срок действия договора с ОФД; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Не нашёл подтверждённых сведений по этому действию. Не буду дополнять инструкцию неподтверждёнными шагами; при необходимости запросите специалиста. (395 мс; LLM нет).
**Ручная оценка:** Вопрос о сервисе уместен, но точной инструкции о сроке договора в approved нет.

**5.2 Клиент:** У меня Платформа ОФД. Распиши подробно, куда заходить и что проверять.

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи.

**Подобранные approved-документы / применимость:**

- `evotor-fn-235-360004715213` — incompatible; разделы: Признаки, Смысл и безопасная проверка.
- `atol-online-11075-fn-invoice` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `atol-online-11072-terminate-contract` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `batch-20261013-vat-usn-advances-2026` — incompatible; разделы: Подтверждённое изменение, Что проверить, Эскалация.
- `batch-20261013-counterparty-reconciliation-act` — incompatible; разделы: Первичная проверка, Суть, Эскалация.
- `evotor-time-mismatch-check-20261019` — incompatible; разделы: Безопасная диагностика, Признаки, Эскалация.

**LLM:** да, 1 выз.; 922 токенов; 17970 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — Мне нужно проверить срок действия договора с ОФД. Как это сделать?; текущие реплики — Мне нужно проверить срок действия договора с ОФД. Как это сделать? / У меня Платформа ОФД. Распиши подробно, куда заходить и что проверять.; подтверждённые цитаты — проверить срок действия договора с ОФД / Платформа ОФД; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Сравните суммы, чтобы убедиться, что они совпадают.<br>
Для диагностики специалисту нужны реквизиты конкретного фискального документа и значения тегов оплат; проверять следует и наличные, и безналичные, и аванс, и постоплату, и встречное предоставление.<br>
Оператор относит код к несоответствию между итоговой суммой чека (тег 1020) и суммой оплат по формам расчёта.<br>

Полная последовательность действий здесь не подтверждена. (14692 мс; LLM да).
**Ручная оценка:** Сервис подтверждён; ответ не подменяет договор тарифом, но остаётся общим без конкретного следующего шага.

### 6. Положительный контроль: поиск чека Платформа ОФД

**6.1 Клиент:** Как найти чек по номеру ФД в Платформе ОФД?

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?

**Подобранные approved-документы / применимость:**

- `aqsi-online-ofd-taxcom-account` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `platformaofd-atol-transmission-checks` — incompatible; разделы: Проверки из раздела «Неполадки и их устранение».
- `atol-online-11071-disable-one-cashier` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `platformaofd-fns-registration` — incompatible; разделы: Данные для сверки, Контроль последовательности.
- `aqsi-online-setup-fiscalize` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-fns-register-ooo` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.

**LLM:** да, 1 выз.; 645 токенов; 17790 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — Как найти чек по номеру ФД в Платформе ОФД?; текущие реплики — Как найти чек по номеру ФД в Платформе ОФД?; подтверждённые цитаты — Как найти чек по номеру ФД в Платформе ОФД?; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Для поиска чека в Платформе ОФД откройте меню «Чеки» → «Поиск чеков», задайте период пробития и используйте доступные фильтры: тип документа, магазин, касса, ФД/ФП, номер смены, сумма, имя кассира, способ оплаты и т.д.<br>
Маршрут: «Чеки» → «Поиск чеков».<br>
Можно отбирать по номеру смены, диапазону суммы, полному или частичному имени кассира, способу оплаты, признаку расчёта и статусу ФНС.<br>
Для прошлого месяца выберите календарные границы нужного месяца.<br>

По запросу по номеру ФД в Платформе ОФД поиск в найденной инструкции не подтверждён. Это не доказывает, что функция недоступна в сервисе. (48871 мс; LLM да).
**Ручная оценка:** Прямой approved-документ есть, но dense retrieval не включил его в кандидаты; вопрос о сервисе повторяет уже указанную Платформу.

**6.2 Клиент:** Где задать период поиска?

**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи.

**Подобранные approved-документы / применимость:**

- `aqsi-online-setup-fiscalize` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `atol-online-11071-disable-one-cashier` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `aqsi-online-ofd-taxcom-account` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `platformaofd-fns-registration` — incompatible; разделы: Данные для сверки, Контроль последовательности.
- `aqsi-online-fns-register-ip` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-fns-register-ooo` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.

**LLM:** да, 1 выз.; 750 токенов; 18238 мс. **Выбор:** no_scope_compatible_approved_source.
**Память:** исходная проблема — Как найти чек по номеру ФД в Платформе ОФД?; текущие реплики — Как найти чек по номеру ФД в Платформе ОФД? / Где задать период поиска?; подтверждённые цитаты — Как найти чек по номеру ФД в Платформе ОФД? / Где задать период поиска?; заданные вопросы — Какой ОФД или кассовый сервис вы используете?.
**Текущий pipeline на Stage3:** Маршрут: «Чеки» → «Поиск чеков».<br>
Для прошлого месяца выберите календарные границы нужного месяца. (18095 мс; LLM да).
**Ручная оценка:** Изначальный вопрос и сервис удержаны, но статья снова не найдена.

### 7. Положительный контроль: пользователь aQsi Online

**7.1 Клиент:** Как добавить сотрудника в aQsi Online?

**vNext:** No fragment covers adding an employee in aQsi Online Какой тип сотрудника вы хотите добавить (например, администратор, кассир)?

**Подобранные approved-документы / применимость:**

- `aqsi-online-account-register-account` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `atol-online-12148-company-registration` — incompatible; разделы: Важно / когда передать специалисту, Подтверждённые сведения.
- `aqsi-online-account-contact-support` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-fns-register-ip` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `atol-online-22559-agent-status` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `aqsi-online-setup-sign-contract` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.

**LLM:** да, 2 выз.; 3728 токенов; 36392 мс. **Выбор:** limitation: None of the provided fragments address employee addition..
**Память:** исходная проблема — Как добавить сотрудника в aQsi Online?; текущие реплики — Как добавить сотрудника в aQsi Online?; подтверждённые цитаты — Как добавить сотрудника в aQsi Online?; заданные вопросы — Какой тип сотрудника вы хотите добавить (например, администратор, кассир)?.
**Текущий pipeline на Stage3:** Откройте «Пользователи» → «Добавить пользователя».<br>
Заполните имя и email, назначьте предварительно созданную роль из вкладки «Роли» и сохраните форму. (48980 мс; LLM да).
**Ручная оценка:** Прямой approved-документ пропущен; требование уточнить тип сотрудника не нужно для описанной процедуры добавления.

**7.2 Клиент:** Он должен просматривать документы, но не менять настройки.

**vNext:** No fragment covers adding an employee or setting view‑only permissions in aQsi Online. Какой уровень доступа вы хотите предоставить сотруднику?

**Подобранные approved-документы / применимость:**

- `atol-online-14749-incoming-documents` — incompatible; разделы: Применимость, Принять приглашение.
- `aqsi-online-account-register-account` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `aqsi-online-account-reset-password` — incompatible; разделы: Когда нужен специалист, Перед выполнением действий, Что можно объяснить и проверить.
- `atol-online-22559-agent-status` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.
- `atol-online-12148-company-registration` — incompatible; разделы: Важно / когда передать специалисту, Подтверждённые сведения.
- `atol-online-16568-step7-fn-activation` — incompatible; разделы: Важное ограничение / передача специалисту, Что проверено по инструкции производителя.

**LLM:** да, 2 выз.; 2706 токенов; 67686 мс. **Выбор:** limitation: None of the provided fragments address employee addition or permission settings..
**Память:** исходная проблема — Как добавить сотрудника в aQsi Online?; текущие реплики — Как добавить сотрудника в aQsi Online? / Он должен просматривать документы, но не менять настройки.; подтверждённые цитаты — Как добавить сотрудника в aQsi Online? / Он должен просматривать документы, но не менять настройки.; заданные вопросы — Какой тип сотрудника вы хотите добавить (например, администратор, кассир)? / Какой уровень доступа вы хотите предоставить сотруднику?.
**Текущий pipeline на Stage3:** Откройте раздел «Пользователи» → «Добавить пользователя».<br>
Введите имя и e‑mail сотрудника.<br>
Сохраните форму.<br>
Заполните имя и email, назначьте предварительно созданную роль из вкладки «Роли» и сохраните форму. (18190 мс; LLM да).
**Ручная оценка:** Требование «просмотр без изменения» удержано; повторный вопрос об уровне доступа игнорирует данное ограничение.


## Exact OFD live-history replay

The two earlier DirectBank user turns and the final OFD turn are the actual user sequence in the same Telegram conversation. The offline replies between them are regenerated independently by each algorithm.

**1. Client:** У нас 1С:Бухгалтерия 8 с ДиректБанком. Можно загрузить выписки сразу по нескольким банковским счетам?<br>
**vNext:** Да, начиная с версии 3.0.148 в 1С:Бухгалтерия 8 с настроенным обменом через 1С:ДиректБанк можно загрузить выписку сразу по всем банковским счетам организации.<br>
**Approved candidates:** `batch-20261013-bank-directbank-all-accounts`, `batch-20261013-bank-directbank-other-banks`, `batch-20261013-bank-import-file-directbank`, `batch-20261013-bank-acquiring-returns`, `batch-20261013-bank-directbank-auto-schedule`, `aqsi-device-standard-refund`. Their candidate-level applicability is in `ofd-live-history-results.json`.<br>
**LLM:** 2 calls, 21706 ms. **Why:** answer: Answer based on confirmed capability..<br>
**Memory:** active original problem = У нас 1С:Бухгалтерия 8 с ДиректБанком. Можно загрузить выписки сразу по нескольким банковским счетам?; exact current-task messages = У нас 1С:Бухгалтерия 8 с ДиректБанком. Можно загрузить выписки сразу по нескольким банковским счетам?; confirmed quotes = У нас 1С:Бухгалтерия 8 с ДиректБанком / Можно загрузить выписки сразу по нескольким банковским счетам?.<br>
**Current pipeline Stage3:** С версии 3.0.148 для настроенного обмена через 1С:ДиректБанк доступна загрузка выписки сразу по всем банковским счетам организации, указанным в настройках взаимодействия с банком.
В «1С:Бухгалтерии 8» с версии 3.0.117 можно загружать выписки из файла, не отключая сервис 1С:ДиректБанк.
Сверить список счетов организации с настройкой обмена и выяснить, должен ли загружаться один счёт или все. (1873 ms; LLM yes).

**2. Client:** А где потом открыть список этих выписок?<br>
**vNext:** Да, можно загрузить выписки сразу по всем банковским счетам организации, если версия 1С:Бухгалтерия 8 ≥ 3.0.148 и настроен обмен через 1С:ДиректБанк. Список выписок можно открыть в меню «Деньги → Банк» (простом интерфейсе) или «Банк и касса → Банк» (полном).<br>
**Approved candidates:** `batch-20261013-bank-import-file-directbank`, `batch-20261013-bank-directbank-auto-schedule`, `batch-20261013-bank-directbank-all-accounts`, `batch-20261013-bank-acquiring-returns`, `evotor-ffd-version-check-20261019`, `aqsi-device-standard-refund`. Their candidate-level applicability is in `ofd-live-history-results.json`.<br>
**LLM:** 2 calls, 87588 ms. **Why:** answer: Ответ основан на подтверждённой возможности загрузки выписок по нескольким счетам и открытии списка выписок в указанном меню. Для точного применения необходимо знать версию конфигурации..<br>
**Memory:** active original problem = У нас 1С:Бухгалтерия 8 с ДиректБанком. Можно загрузить выписки сразу по нескольким банковским счетам?; exact current-task messages = У нас 1С:Бухгалтерия 8 с ДиректБанком. Можно загрузить выписки сразу по нескольким банковским счетам? / А где потом открыть список этих выписок?; confirmed quotes = У нас 1С:Бухгалтерия 8 с ДиректБанком / Можно загрузить выписки сразу по нескольким банковским счетам? / А где потом открыть список этих выписок?.<br>
**Current pipeline Stage3:** Откройте список выписок в 1С: Бухгалтерия 8 через меню:
• В простом интерфейсе – «Деньги → Банк»
• В полном – «Банк и касса → Банк» (17909 ms; LLM yes).

**3. Client:** у меня проблема кончился офд<br>
**vNext:** В найденных approved-материалах нет применимой инструкции для этой задачи. Какой ОФД или кассовый сервис вы используете?<br>
**Approved candidates:** `atol-online-11075-fn-invoice`, `batch-20261013-closing-error-first-diagnostics`, `aqsi-device-paper-print-retry`, `aqsi-kkt-error-115`, `evotor-fn-231-360005098974`, `atol-online-22561-gateway-errors-timeout-128-protocol`. Their candidate-level applicability is in `ofd-live-history-results.json`.<br>
**LLM:** 1 calls, 67351 ms. **Why:** no_scope_compatible_approved_source.<br>
**Memory:** active original problem = у меня проблема кончился офд; exact current-task messages = у меня проблема кончился офд; confirmed quotes = кончился офд.<br>
**Current pipeline Stage3:** Уточните, пожалуйста, какую задачу нужно решить и какие требования сейчас обязательны. (5 ms; LLM no).

At the final OFD turn, vNext reset the active problem to the new OFD message and discarded DirectBank facts from the active task. The current local pipeline repeated the historical generic ambiguity. vNext still did not solve the paid-period issue: it could only ask which OFD/service applies.

## P0.0 + P0.1 — approved hybrid retrieval, 2026-10-23

**Scope and receipt.** This section reports a new, read-only **raw-question** replay, without Groq, indexing or production writes. Source HEAD: `ce4231906368c4c6c872ec175c6eabca55026040`; exact dirty paths and SHA-256 for code and fixtures are in [p0-raw-retrieval-results.json](p0-raw-retrieval-results.json). Stage3 remained `knowledge_stage3_retrieval_20261022`, 934 points, 672 approved, 384-dimensional embedding. Seven scenarios contain 15 turns; the exact OFD history contains three turns. Their expected client outcomes were frozen in [p0-expected-outcomes.json](p0-expected-outcomes.json) before any new Groq answer. This run evaluates only the three original first-turn questions, not all 18 turns.

**Implementation.** `cli.py` now calls the existing `app.retrieval.Retriever` through a read-only adapter in `stage3_retrieval.py`. The retriever performs approved-only BM25+Dense+RRF over Stage3; no pre-retrieval task/operation gate was added. After candidate retrieval, an explicit service/model check and a conservative query-to-source-title relation check reject incompatible procedures. The latter uses lexical variants and can reject useful articles whose titles do not describe the task; this is a known limitation. Model context is capped at eight documents, two non-question fragments per document, 16,000 characters total. The `respond` prompt receives exactly the selected approved fragments. The old new-topic override that silently replaced an LLM-proposed query with the raw question was removed, so a future LLM-proposed query is actually used and traceable. The CLI trace records the effective post-understanding `search_query`, query origin, scenario/task ID, candidate and chunk ranks/scores/metadata/rejection predicates, exact context and IDs, model applicability, claim/id/quote decisions, final answer, calls, tokens and latency. A local stub verified this graph wiring and claim trace without network calls; real LLM-generated queries remain untested.

Both strategies below use the **same new post-retrieval context selector**, so the comparison isolates dense top-six versus hybrid candidate sourcing. `dense` does not represent the old unfiltered prompt byte for byte.

| Raw-question control | Dense top-six: expected doc/context | Hybrid: expected doc rank, chunk rank, context | Context chars dense → hybrid | Retrieval ms dense → hybrid |
|---|---|---|---:|---:|
| Платформа ОФД, чек по ФД | absent / absent | `platformaofd-lkk-receipt-search`: 5, 7, present | 0 → 596 | 154 → 154 |
| aQsi Online, добавить сотрудника | absent / absent | `aqsi-online-account-add-user`: 3, 3, present | 0 → 471 | 30 → 128 |
| 1С, перестали загружаться выписки | `batch-20261013-bank-directbank-all-accounts`: rank 2, present | same: 2, 2, present | 1275 → 1745 | 59 → 138 |

**Measured recall at model context:** dense **1/3**, hybrid **3/3**. The target raw dense chunk positions in hybrid's 100-chunk probe were 49/51/2 respectively. Hybrid context IDs were respectively `[platformaofd-lkk-receipt-search]`, `[aqsi-online-account-add-user]`, and `[batch-20261013-bank-directbank-other-banks, batch-20261013-bank-directbank-all-accounts, batch-20261013-bank-import-file-directbank]`. All selected fragments had `status=approved`; the approved filter excluded 262 non-approved points before retrieval. The JSON contains all raw hybrid chunk hits (100/100/87), their rank, ID, RRF/BM25/dense scores and metadata; no raw hit had a missing ID or non-approved status. Candidate-level rejection reasons and chunk-level decisions are also recorded. Examples: Platforma registration/tariff and aQsi refund were rejected as `title_topic_mismatch`; ATOL/aQsi sources in another named service were rejected as `service_unconfirmed_or_other`; articles for an unconfirmed equipment model as `equipment_model_unconfirmed`; tax/ENS articles did not reach the bank-statement context. The no-Groq integration gate explicitly checks these known incompatible IDs and that every context document has a `selected` candidate decision. Internal reasons for chunks filtered inside the existing `Retriever` are not exposed by its `Hit` API; the trace does not invent a specific reason for those omissions.

**Timing interpretation.** The figures are one sequential local replay, dense first and hybrid second for each question, with model/corpus caching. They show the measured cost of the candidate and context path, including approval checks, but are not a stable latency benchmark. Warm cases suggest hybrid costs more retrieval time than dense. No LLM latency, pacing, tokens or answer usefulness can be inferred.

**Validation and remaining gate.** Six new offline regression tests passed, including independent paraphrases for all three intents, draft exclusion, different-service rejection, unrelated-procedure rejection, numeric equipment-model mismatch and a local graph stub with a rewritten search query and accepted claim. Together with existing retrieval tests, **24 passed**. `cli.py --preflight` passed without Groq. The three original approved documents reach the final prompt context, so the deterministic P0.1 candidate gate is met. Actual LLM-generated queries, full 15-turn answer quality, exact live-history behaviour and safety of generated claims remain unverified. Under [RAG_RECOVERY_PLAN.md](../../docs/RAG_RECOVERY_PLAN.md), P0.2 must wait for a separate decision; this task does not modify the production pipeline or start P0.2.
