# Организация базы знаний Support-RAG-Bot — этап 1

Дата сверки источников: **22.10.2026**. Область изменения: `data/knowledge/**/*.md` и этот отчёт. Работа выполнена в ветке `fix/rag-p0-dialogue-v2` без переноса файлов и без переиндексации.

## Итог и принцип организации

- Учтены все **269** исходных документов. Все `document_id` остались прежними и уникальны; URL источников и исходные пути сохранены.
- Статусы: **206 approved**, **63 draft**.
- Физические папки оставлены на месте: загрузчик включает относительный путь в `source`, а перемещение поменяло бы существующие ссылки на документ. Тематическая иерархия задана полями `service` → `task_category` → `operations`. Существующее `category` сохранено для совместимости.
- Для каждого файла заполнены `document_id`, `title`, `service`, `task_category`, `operations`, `source_url`, `status`; `software`, `manufacturer`, `model` оставлены или добавлены там, где они относятся к предмету. У каждого `draft` есть `review_note` с причиной. Для `approved` указаны реальные `source_checked_at` и `verified_at` 22.10.2026; для `draft` фиктивной даты подтверждения нет.
- `approved` означает, что материал можно использовать как статью с указанными условиями и ограничениями по проверенному источнику. Это не подтверждение конкретного налогового расчёта, оборудования клиента или будущего состояния сервиса.
- Проверены все 227 уникальных `source_url`: 224 открылись на дату проверки, 3 вернули HTTP 404. Для статуса оценивались содержание статьи, предмет источника, условия и ограничения; одна лишь доступность URL не служила основанием для `approved`.

## Тематическая структура

| Сервис / направление | Всего | approved | draft | Подтемы (`task_category`: число) |
| --- | ---: | ---: | ---: | --- |
| АТОЛ Онлайн | 96 | 75 | 21 | `billing` 16, `kkt_rules` 15, `service_connection` 13, `fiscal_drive` 7, `integration` 7, `receipt_issue` 6, `error_diagnosis` 4, `ofd_connection` 4, `settings` 4, `correction_receipt` 3, `fns_registration` 3, `contract` 2, `vat_usn` 2, `cash_list` 1, `cash_reports` 1, `edo` 1, `equipment_replacement` 1, `equipment_setup` 1, `partner_program` 1, `receipt_search` 1, `refund` 1, `shift_management` 1, `support` 1 |
| aQsi | 36 | 32 | 4 | `error_diagnosis` 10, `sales` 5, `shift_management` 4, `peripheral_setup` 3, `product_catalog` 3, `correction_receipt` 2, `equipment_setup` 2, `marking` 2, `ofd_connection` 2, `fiscal_drive` 1, `settings` 1, `vat_settings` 1 |
| aQsi Online | 36 | 23 | 13 | `applicability` 9, `access` 5, `service_connection` 5, `fns_registration` 4, `correction_receipt` 3, `cash_list` 2, `integration` 2, `refund` 2, `account_settings` 1, `ofd_connection` 1, `receipt_issue` 1, `support` 1 |
| Эвотор | 25 | 23 | 2 | `error_diagnosis` 6, `receipt_transmission` 5, `model_features` 3, `marking` 2, `tspiot` 2, `cash_operations` 1, `fiscal_format` 1, `kkt_rules` 1, `network_diagnostics` 1, `receipt_print` 1, `settings` 1, `vat_settings` 1 |
| 1С:Бухгалтерия 8 | 24 | 24 | 0 | `bank_statement` 6, `ens` 5, `vat_accounting` 5, `period_close` 3, `edo` 2, `reconciliation` 2, `goods_receipt` 1 |
| Налоги и бухгалтерский учёт | 18 | 11 | 7 | `vat_usn` 15, `ens` 2, `insurance_contributions` 1 |
| Платформа ОФД | 18 | 18 | 0 | `ofd_connection` 7, `fiscal_drive` 3, `fiscal_document_control` 2, `cash_list` 1, `cash_search` 1, `fns_monitoring` 1, `marking` 1, `receipt_search` 1, `receipt_status` 1 |
| ТС ПиОТ | 4 | 0 | 4 | `tspiot` 4 |
| ЭДО | 4 | 0 | 4 | `edo` 4 |
| Регистрация бизнеса | 3 | 0 | 3 | `business_registration` 3 |
| ККТ и законодательство | 2 | 0 | 2 | `kkt_rules` 2 |
| Маркировка и Честный ЗНАК | 2 | 0 | 2 | `marking` 2 |
| 1С | 1 | 0 | 1 | `reference_directory` 1 |

Фактическое дерево охватывает 1С (банк, закрытие месяца, ЕНС, НДС, ЭДО и товары), налоговый учёт, физические кассы aQsi, aQsi Online, АТОЛ Онлайн, Эвотор, Платформу ОФД, маркировку, ТС ПиОТ, ЭДО, регистрацию бизнеса и законодательство о ККТ. Разделение aQsi / aQsi Online и касса / кабинет ОФД отражает разные процедуры и условия.

## Что осталось draft

Причина записана и в `review_note` каждого файла. Список ниже исчерпывающий; нахождение статьи в `draft` не означает недостоверность собранного владельцем материала.

### 22 — Правовой вывод требует проверки действующей нормы и условий клиента по официальному первоисточнику.

- [`atol_online/law/54fz-before-connecting.md`](../data/knowledge/atol_online/law/54fz-before-connecting.md)
- [`atol_online/law/54fz-exemptions-diagnostics.md`](../data/knowledge/atol_online/law/54fz-exemptions-diagnostics.md)
- [`atol_online/law/54fz-when-kkt-needed.md`](../data/knowledge/atol_online/law/54fz-when-kkt-needed.md)
- [`atol_online/law/advance-vs-prepayment.md`](../data/knowledge/atol_online/law/advance-vs-prepayment.md)
- [`atol_online/law/agent-contract-kkt.md`](../data/knowledge/atol_online/law/agent-contract-kkt.md)
- [`atol_online/law/cloud-kkt-applicability.md`](../data/knowledge/atol_online/law/cloud-kkt-applicability.md)
- [`atol_online/law/ffd-105-vs-12-basics.md`](../data/knowledge/atol_online/law/ffd-105-vs-12-basics.md)
- [`atol_online/law/fiscal-doc-types-overview.md`](../data/knowledge/atol_online/law/fiscal-doc-types-overview.md)
- [`atol_online/law/fns-receipts-compliance.md`](../data/knowledge/atol_online/law/fns-receipts-compliance.md)
- [`atol_online/law/housing-utility-payments.md`](../data/knowledge/atol_online/law/housing-utility-payments.md)
- [`atol_online/law/internet-store-kkt.md`](../data/knowledge/atol_online/law/internet-store-kkt.md)
- [`atol_online/law/npd-receipts.md`](../data/knowledge/atol_online/law/npd-receipts.md)
- [`atol_online/law/patent-kkt-eligibility.md`](../data/knowledge/atol_online/law/patent-kkt-eligibility.md)
- [`atol_online/law/sugary-drinks-classification.md`](../data/knowledge/atol_online/law/sugary-drinks-classification.md)
- [`atol_online/law/sugary-drinks-kkt-preparation.md`](../data/knowledge/atol_online/law/sugary-drinks-kkt-preparation.md)
- [`atol_online/taxes/tax-2026-business-prep.md`](../data/knowledge/atol_online/taxes/tax-2026-business-prep.md)
- [`atol_online/taxes/tax-2026-vat-changes.md`](../data/knowledge/atol_online/taxes/tax-2026-vat-changes.md)
- [`business/registration/ip-ooo-ao-differences.md`](../data/knowledge/business/registration/ip-ooo-ao-differences.md)
- [`business/registration/register-ip-fns.md`](../data/knowledge/business/registration/register-ip-fns.md)
- [`business/registration/register-ooo-fns.md`](../data/knowledge/business/registration/register-ooo-fns.md)
- [`compliance/kkt-correction-receipt.md`](../data/knowledge/compliance/kkt-correction-receipt.md)
- [`compliance/kkt-fns-2026-risk.md`](../data/knowledge/compliance/kkt-fns-2026-risk.md)

### 9 — Источник описывает типовой сценарий; конкретная интеграция и применимость для клиента требуют подтверждения у сервиса.

- [`aqsi_online/use_cases/couriers-fiscalization.md`](../data/knowledge/aqsi_online/use_cases/couriers-fiscalization.md)
- [`aqsi_online/use_cases/housing-krasinform-gorod.md`](../data/knowledge/aqsi_online/use_cases/housing-krasinform-gorod.md)
- [`aqsi_online/use_cases/housing-register-payments.md`](../data/knowledge/aqsi_online/use_cases/housing-register-payments.md)
- [`aqsi_online/use_cases/internet-store-cms-aggregator.md`](../data/knowledge/aqsi_online/use_cases/internet-store-cms-aggregator.md)
- [`aqsi_online/use_cases/retail-physical-vs-cloud.md`](../data/knowledge/aqsi_online/use_cases/retail-physical-vs-cloud.md)
- [`aqsi_online/use_cases/taxi-aggregator.md`](../data/knowledge/aqsi_online/use_cases/taxi-aggregator.md)
- [`aqsi_online/use_cases/taxi-cloud-or-terminal.md`](../data/knowledge/aqsi_online/use_cases/taxi-cloud-or-terminal.md)
- [`aqsi_online/use_cases/transport-operator.md`](../data/knowledge/aqsi_online/use_cases/transport-operator.md)
- [`aqsi_online/use_cases/vending-telemetry.md`](../data/knowledge/aqsi_online/use_cases/vending-telemetry.md)

### 8 — Материал является отраслевым объяснением; для точных требований нужна актуальная инструкция оператора или регулятора.

- [`edo/counterparty-no-edo.md`](../data/knowledge/edo/counterparty-no-edo.md)
- [`edo/edi-operator-choice.md`](../data/knowledge/edo/edi-operator-choice.md)
- [`edo/marked-goods-acceptance.md`](../data/knowledge/edo/marked-goods-acceptance.md)
- [`edo/upd-discrepancy.md`](../data/knowledge/edo/upd-discrepancy.md)
- [`tspiot/astral-codes.md`](../data/knowledge/tspiot/astral-codes.md)
- [`tspiot/astral-diagnostics.md`](../data/knowledge/tspiot/astral-diagnostics.md)
- [`tspiot/tspiot-initial-diagnostics-2026.md`](../data/knowledge/tspiot/tspiot-initial-diagnostics-2026.md)
- [`tspiot/tspiot-licence-and-sale-checks-2026.md`](../data/knowledge/tspiot/tspiot-licence-and-sale-checks-2026.md)

### 7 — Для налогового вывода требуется сверить конкретное правило и применимость с актуальным первоисточником ФНС/НК РФ.

- [`accounting/ens/balance-and-reconciliation.md`](../data/knowledge/accounting/ens/balance-and-reconciliation.md)
- [`accounting/ens/notification-errors.md`](../data/knowledge/accounting/ens/notification-errors.md)
- [`accounting/ip/insurance-fixed-2026.md`](../data/knowledge/accounting/ip/insurance-fixed-2026.md)
- [`accounting/usn/usn-income-acquiring-2026.md`](../data/knowledge/accounting/usn/usn-income-acquiring-2026.md)
- [`accounting/usn/usn-max-limit.md`](../data/knowledge/accounting/usn/usn-max-limit.md)
- [`accounting/vat_usn/agent-revenue.md`](../data/knowledge/accounting/vat_usn/agent-revenue.md)
- [`accounting/vat_usn/combine-usn-psn.md`](../data/knowledge/accounting/vat_usn/combine-usn-psn.md)

### 6 — Версии, тарифы или требования привязаны к 2026 году; нужна проверка актуального релиза и условий применения.

- [`aqsi_devices/vat/vat22-configuration.md`](../data/knowledge/aqsi_devices/vat/vat22-configuration.md)
- [`atol_online/billing/closing-docs-april-2026.md`](../data/knowledge/atol_online/billing/closing-docs-april-2026.md)
- [`atol_online/billing/vat22-supplement.md`](../data/knowledge/atol_online/billing/vat22-supplement.md)
- [`atol_online/integration/vat22-api.md`](../data/knowledge/atol_online/integration/vat22-api.md)
- [`evotor/vat/vat-22-compatibility.md`](../data/knowledge/evotor/vat/vat-22-compatibility.md)
- [`marking/canned-goods-edo-oct-2026.md`](../data/knowledge/marking/canned-goods-edo-oct-2026.md)

### 3 — Первоисточник сейчас возвращает 404; требуется актуальная ссылка и сверка процедуры.

- [`aqsi_online/fns/reregister-fn.md`](../data/knowledge/aqsi_online/fns/reregister-fn.md)
- [`aqsi_online/integration/1c-setup.md`](../data/knowledge/aqsi_online/integration/1c-setup.md)
- [`aqsi_online/receipts/correction-12.md`](../data/knowledge/aqsi_online/receipts/correction-12.md)

### 3 — Сценарий чека коррекции зависит от ФФД и фискальных обстоятельств; требуется сверка первоисточника и специалиста.

- [`aqsi_devices/correction/ffd105-check.md`](../data/knowledge/aqsi_devices/correction/ffd105-check.md)
- [`aqsi_devices/correction/ffd12-check.md`](../data/knowledge/aqsi_devices/correction/ffd12-check.md)
- [`aqsi_online/receipts/correction-105.md`](../data/knowledge/aqsi_online/receipts/correction-105.md)

### 1 — Причина ошибки ФН 20 зависит от состояния и версии ФН; нужна проверка диагностики конкретной кассы.

- [`aqsi/aqsi-error-20-fn.md`](../data/knowledge/aqsi/aqsi-error-20-fn.md)

### 1 — Режим учёта зависит от товарной группы и даты; требуется сверка действующих правил Честного ЗНАКа.

- [`marking/gtin-vs-item-tracking.md`](../data/knowledge/marking/gtin-vs-item-tracking.md)

### 1 — Сверка 22.10.2026 обнаружила устаревшие минимальные версии в исходном конспекте; приведены текущие значения страницы Эвотора, но перед применением требуется повторная проверка для модели клиента.

- [`evotor/tspiot/minimum-versions-2026.md`](../data/knowledge/evotor/tspiot/minimum-versions-2026.md)

### 1 — Справочник охватывает разные конфигурации; нужно подтвердить актуальные ссылки для каждой из них.

- [`software/1c/1c-faq-directory.md`](../data/knowledge/software/1c/1c-faq-directory.md)

### 1 — Условия партнёрской программы могут меняться; требуется сверка актуальной оферты и правил участия у АТОЛ Онлайн.

- [`atol_online/partners/referral-program-guide.md`](../data/knowledge/atol_online/partners/referral-program-guide.md)

## Дубликаты, пересечения и проблемы

- Полных дублей тела и повторяющихся `document_id` не обнаружено. Один URL может служить источником нескольких разных задач: 269 документов ссылаются на 227 уникальных URL. Одинаковый URL сам по себе не считался дубликатом.
- Сильное содержательное пересечение: `accounting/usn/usn-nds-exemption-2026.md` ↔ `accounting/vat_usn/exemption-threshold-2026.md`. Оба описывают освобождение от НДС при УСН в 2026 году; ID сохранены, дальнейшая консолидация требует решения о канонической статье.
- Другие пересекающиеся пары: `accounting/usn/usn-nds-invoice-2026.md` ↔ `accounting/vat_usn/invoice-on-exempt.md`; `accounting/usn/usn-nds-rates-2026.md` ↔ `accounting/vat_usn/rates-2026.md`; `accounting/usn/usn-nds-trigger-2026.md` ↔ `accounting/vat_usn/when-tax-starts.md`. Темы близки, но условия и диагностические вопросы различаются.
- `aqsi_online/receipts/correction-105.md` и `correction-12.md` похожи по назначению, но относятся к разным ФФД и не должны сливаться без отдельной проверки. Аналогично `atol_online/receipts/correct-ffd105.md` и `correct-ffd12.md`.
- Три URL aQsi Online возвращали HTTP 404 при проверке 22.10.2026: `aqsi_online/fns/reregister-fn.md`, `aqsi_online/integration/1c-setup.md`, `aqsi_online/receipts/correction-12.md`. Найденные поиском копии страниц не заменяют доступный первоисточник; файлы оставлены `draft`.
- В `evotor/tspiot/minimum-versions-2026.md` исходные минимумы KkmDriver 4.7.0 и UTM Manager 2.7.1 больше не совпадали с [текущей статьёй Эвотора](https://support.evotor.ru/article/6a713998-a0af-4b0d-9373-20a539f7f6a6). Текст обновлён по странице на 22.10.2026 (5.6.0, 2.7.3 и ЕСМ 1.4.2.3), статус оставлен `draft` из-за зависимости от модели и новых релизов.
- Прямых взаимоисключающих утверждений между остальными статьями при тематической сверке не выявлено. Отдельные правовые, налоговые, тарифные и маркетинговые сценарии оставлены `draft`, поскольку актуальность и условия не подтверждены до уровня конкретного случая.

## Изменённые и перемещённые файлы

- Перемещённых файлов: **0**. Удалённых документов: **0**.
- Изменены метаданные всех **269** Markdown-файлов в `data/knowledge`. В подтверждённых статьях удалены устаревшие служебные пометки о черновике; в четырёх кратких статьях добавлены смысловые заголовки без изменения шагов; уточнены версии Эвотора. Полный реестр ниже фиксирует каждый изменённый файл, ID, тему и итоговый статус.
- Создан `docs/knowledge-base-organization.md`. Иные файлы проекта в рамках этого этапа не изменялись; ранее существовавшие незакоммиченные изменения не затронуты.

## Проверка результата

- `DocumentLoader(data/knowledge).load_all()` загружает 269 документов: 206 `approved`, 63 `draft`. Основные поля непусты, в `approved` заполнен `verified_at`, у `draft` указан `review_note`.
- Сравнение с `HEAD` подтвердило неизменность всех 269 `document_id`, `title` и `source_url`. Это проверка структуры документов; индексация, коллекция Qdrant и тестирование модели не запускались.

## Полный реестр документов

| Файл | document_id | Тема | Статус |
| --- | --- | --- | --- |
| [`1c/bank/acquiring-patent-tax.md`](../data/knowledge/1c/bank/acquiring-patent-tax.md) | `batch-20261013-bank-acquiring-patent-tax` | 1С:Бухгалтерия 8 / `bank_statement` | `approved` |
| [`1c/bank/acquiring-returns.md`](../data/knowledge/1c/bank/acquiring-returns.md) | `batch-20261013-bank-acquiring-returns` | 1С:Бухгалтерия 8 / `bank_statement` | `approved` |
| [`1c/bank/directbank-all-accounts.md`](../data/knowledge/1c/bank/directbank-all-accounts.md) | `batch-20261013-bank-directbank-all-accounts` | 1С:Бухгалтерия 8 / `bank_statement` | `approved` |
| [`1c/bank/directbank-auto-schedule.md`](../data/knowledge/1c/bank/directbank-auto-schedule.md) | `batch-20261013-bank-directbank-auto-schedule` | 1С:Бухгалтерия 8 / `bank_statement` | `approved` |
| [`1c/bank/directbank-other-banks.md`](../data/knowledge/1c/bank/directbank-other-banks.md) | `batch-20261013-bank-directbank-other-banks` | 1С:Бухгалтерия 8 / `bank_statement` | `approved` |
| [`1c/bank/import-file-directbank.md`](../data/knowledge/1c/bank/import-file-directbank.md) | `batch-20261013-bank-import-file-directbank` | 1С:Бухгалтерия 8 / `bank_statement` | `approved` |
| [`1c/closing/close-several-months.md`](../data/knowledge/1c/closing/close-several-months.md) | `batch-20261013-closing-close-several-months` | 1С:Бухгалтерия 8 / `period_close` | `approved` |
| [`1c/closing/error-first-diagnostics.md`](../data/knowledge/1c/closing/error-first-diagnostics.md) | `batch-20261013-closing-error-first-diagnostics` | 1С:Бухгалтерия 8 / `period_close` | `approved` |
| [`1c/closing/monthly-schedule.md`](../data/knowledge/1c/closing/monthly-schedule.md) | `batch-20261013-closing-monthly-schedule` | 1С:Бухгалтерия 8 / `period_close` | `approved` |
| [`1c/counterparty/reconciliation-act.md`](../data/knowledge/1c/counterparty/reconciliation-act.md) | `batch-20261013-counterparty-reconciliation-act` | 1С:Бухгалтерия 8 / `reconciliation` | `approved` |
| [`1c/counterparty/reconciliation-monitor.md`](../data/knowledge/1c/counterparty/reconciliation-monitor.md) | `batch-20261013-counterparty-reconciliation-monitor` | 1С:Бухгалтерия 8 / `reconciliation` | `approved` |
| [`1c/edo/connect-1c-edo.md`](../data/knowledge/1c/edo/connect-1c-edo.md) | `batch-20261013-edo-connect-1c-edo` | 1С:Бухгалтерия 8 / `edo` | `approved` |
| [`1c/edo/epd-vs-edo.md`](../data/knowledge/1c/edo/epd-vs-edo.md) | `batch-20261013-edo-epd-vs-edo` | 1С:Бухгалтерия 8 / `edo` | `approved` |
| [`1c/goods/single-upd-many-warehouses.md`](../data/knowledge/1c/goods/single-upd-many-warehouses.md) | `batch-20261013-goods-single-upd-many-warehouses` | 1С:Бухгалтерия 8 / `goods_receipt` | `approved` |
| [`1c/taxes/ens-accounting-settings.md`](../data/knowledge/1c/taxes/ens-accounting-settings.md) | `batch-20261013-taxes-ens-accounting-settings` | 1С:Бухгалтерия 8 / `ens` | `approved` |
| [`1c/taxes/ens-automatic-data.md`](../data/knowledge/1c/taxes/ens-automatic-data.md) | `batch-20261013-taxes-ens-automatic-data` | 1С:Бухгалтерия 8 / `ens` | `approved` |
| [`1c/taxes/ens-cashflow-article.md`](../data/knowledge/1c/taxes/ens-cashflow-article.md) | `batch-20261013-taxes-ens-cashflow-article` | 1С:Бухгалтерия 8 / `ens` | `approved` |
| [`1c/taxes/ens-menu-2026.md`](../data/knowledge/1c/taxes/ens-menu-2026.md) | `batch-20261013-taxes-ens-menu-2026` | 1С:Бухгалтерия 8 / `ens` | `approved` |
| [`1c/taxes/ens-operations-name.md`](../data/knowledge/1c/taxes/ens-operations-name.md) | `batch-20261013-taxes-ens-operations-name` | 1С:Бухгалтерия 8 / `ens` | `approved` |
| [`1c/vat/electronic-upd-2026.md`](../data/knowledge/1c/vat/electronic-upd-2026.md) | `batch-20261013-vat-electronic-upd-2026` | 1С:Бухгалтерия 8 / `vat_accounting` | `approved` |
| [`1c/vat/invoice-forms-april.md`](../data/knowledge/1c/vat/invoice-forms-april.md) | `batch-20261013-vat-invoice-forms-april` | 1С:Бухгалтерия 8 / `vat_accounting` | `approved` |
| [`1c/vat/usn-advances-2026.md`](../data/knowledge/1c/vat/usn-advances-2026.md) | `batch-20261013-vat-usn-advances-2026` | 1С:Бухгалтерия 8 / `vat_accounting` | `approved` |
| [`1c/vat/usn-to-osno-2026.md`](../data/knowledge/1c/vat/usn-to-osno-2026.md) | `batch-20261013-vat-usn-to-osno-2026` | 1С:Бухгалтерия 8 / `vat_accounting` | `approved` |
| [`1c/vat/vat-usn-settings.md`](../data/knowledge/1c/vat/vat-usn-settings.md) | `batch-20261013-vat-vat-usn-settings` | 1С:Бухгалтерия 8 / `vat_accounting` | `approved` |
| [`accounting/ens/balance-and-reconciliation.md`](../data/knowledge/accounting/ens/balance-and-reconciliation.md) | `batch-20261013-ens-balance-and-reconciliation` | Налоги и бухгалтерский учёт / `ens` | `draft` |
| [`accounting/ens/notification-errors.md`](../data/knowledge/accounting/ens/notification-errors.md) | `batch-20261013-ens-notification-errors` | Налоги и бухгалтерский учёт / `ens` | `draft` |
| [`accounting/ip/insurance-fixed-2026.md`](../data/knowledge/accounting/ip/insurance-fixed-2026.md) | `batch-20261013-ip-insurance-fixed-2026` | Налоги и бухгалтерский учёт / `insurance_contributions` | `draft` |
| [`accounting/usn/usn-income-acquiring-2026.md`](../data/knowledge/accounting/usn/usn-income-acquiring-2026.md) | `acc-usn-income-acquiring-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `draft` |
| [`accounting/usn/usn-max-limit.md`](../data/knowledge/accounting/usn/usn-max-limit.md) | `batch-20261013-usn-usn-max-limit` | Налоги и бухгалтерский учёт / `vat_usn` | `draft` |
| [`accounting/usn/usn-nds-exemption-2026.md`](../data/knowledge/accounting/usn/usn-nds-exemption-2026.md) | `acc-usn-nds-exemption-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/usn/usn-nds-invoice-2026.md`](../data/knowledge/accounting/usn/usn-nds-invoice-2026.md) | `acc-usn-nds-invoice-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/usn/usn-nds-rates-2026.md`](../data/knowledge/accounting/usn/usn-nds-rates-2026.md) | `acc-usn-nds-rates-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/usn/usn-nds-trigger-2026.md`](../data/knowledge/accounting/usn/usn-nds-trigger-2026.md) | `acc-usn-nds-trigger-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/usn/usn-psn-income-2026.md`](../data/knowledge/accounting/usn/usn-psn-income-2026.md) | `acc-usn-psn-income-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/usn/usn-special-vat-switch-2026.md`](../data/knowledge/accounting/usn/usn-special-vat-switch-2026.md) | `acc-usn-special-vat-switch-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/vat_usn/advance-invoice.md`](../data/knowledge/accounting/vat_usn/advance-invoice.md) | `batch-20261013-vat-usn-advance-invoice` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/vat_usn/agent-revenue.md`](../data/knowledge/accounting/vat_usn/agent-revenue.md) | `batch-20261013-vat-usn-agent-revenue` | Налоги и бухгалтерский учёт / `vat_usn` | `draft` |
| [`accounting/vat_usn/combine-usn-psn.md`](../data/knowledge/accounting/vat_usn/combine-usn-psn.md) | `batch-20261013-vat-usn-combine-usn-psn` | Налоги и бухгалтерский учёт / `vat_usn` | `draft` |
| [`accounting/vat_usn/exemption-threshold-2026.md`](../data/knowledge/accounting/vat_usn/exemption-threshold-2026.md) | `batch-20261013-vat-usn-exemption-threshold-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/vat_usn/invoice-on-exempt.md`](../data/knowledge/accounting/vat_usn/invoice-on-exempt.md) | `batch-20261013-vat-usn-invoice-on-exempt` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/vat_usn/rates-2026.md`](../data/knowledge/accounting/vat_usn/rates-2026.md) | `batch-20261013-vat-usn-rates-2026` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`accounting/vat_usn/when-tax-starts.md`](../data/knowledge/accounting/vat_usn/when-tax-starts.md) | `batch-20261013-vat-usn-when-tax-starts` | Налоги и бухгалтерский учёт / `vat_usn` | `approved` |
| [`aqsi/aqsi-error-115.md`](../data/knowledge/aqsi/aqsi-error-115.md) | `aqsi-kkt-error-115` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi/aqsi-error-126.md`](../data/knowledge/aqsi/aqsi-error-126.md) | `aqsi-kkt-error-126` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi/aqsi-error-20-fn.md`](../data/knowledge/aqsi/aqsi-error-20-fn.md) | `aqsi-fn-error-20` | aQsi / `error_diagnosis` | `draft` |
| [`aqsi_devices/catalog/create-product.md`](../data/knowledge/aqsi_devices/catalog/create-product.md) | `aqsi-device-create-product` | aQsi / `product_catalog` | `approved` |
| [`aqsi_devices/catalog/excel-import.md`](../data/knowledge/aqsi_devices/catalog/excel-import.md) | `aqsi-device-excel-import` | aQsi / `product_catalog` | `approved` |
| [`aqsi_devices/catalog/shop-assignment.md`](../data/knowledge/aqsi_devices/catalog/shop-assignment.md) | `aqsi-device-shop-assignment` | aQsi / `product_catalog` | `approved` |
| [`aqsi_devices/correction/ffd105-check.md`](../data/knowledge/aqsi_devices/correction/ffd105-check.md) | `aqsi-device-ffd105-check` | aQsi / `correction_receipt` | `draft` |
| [`aqsi_devices/correction/ffd12-check.md`](../data/knowledge/aqsi_devices/correction/ffd12-check.md) | `aqsi-device-ffd12-check` | aQsi / `correction_receipt` | `draft` |
| [`aqsi_devices/errors/fn161-document-not-saved.md`](../data/knowledge/aqsi_devices/errors/fn161-document-not-saved.md) | `aqsi-device-fn161-document-not-saved` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/errors/fn18-expired.md`](../data/knowledge/aqsi_devices/errors/fn18-expired.md) | `aqsi-device-fn18-expired` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/errors/fn7-date.md`](../data/knowledge/aqsi_devices/errors/fn7-date.md) | `aqsi-device-fn7-date` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/errors/goods-not-on-device.md`](../data/knowledge/aqsi_devices/errors/goods-not-on-device.md) | `aqsi-device-goods-not-on-device` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/errors/marking-178.md`](../data/knowledge/aqsi_devices/errors/marking-178.md) | `aqsi-device-marking-178` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/errors/paper-print-retry.md`](../data/knowledge/aqsi_devices/errors/paper-print-retry.md) | `aqsi-device-paper-print-retry` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/errors/red-blinking-battery.md`](../data/knowledge/aqsi_devices/errors/red-blinking-battery.md) | `aqsi-device-red-blinking-battery` | aQsi / `error_diagnosis` | `approved` |
| [`aqsi_devices/fn/fn-close-safety.md`](../data/knowledge/aqsi_devices/fn/fn-close-safety.md) | `aqsi-device-fn-close-safety` | aQsi / `fiscal_drive` | `approved` |
| [`aqsi_devices/marking/permission-diagnostics.md`](../data/knowledge/aqsi_devices/marking/permission-diagnostics.md) | `aqsi-device-permission-diagnostics` | aQsi / `marking` | `approved` |
| [`aqsi_devices/marking/permission-setup.md`](../data/knowledge/aqsi_devices/marking/permission-setup.md) | `aqsi-device-permission-setup` | aQsi / `marking` | `approved` |
| [`aqsi_devices/ofd/connection-fields.md`](../data/knowledge/aqsi_devices/ofd/connection-fields.md) | `aqsi-device-connection-fields` | aQsi / `ofd_connection` | `approved` |
| [`aqsi_devices/ofd/ofd-oism-current-credentials.md`](../data/knowledge/aqsi_devices/ofd/ofd-oism-current-credentials.md) | `aqsi-device-ofd-oism-current-credentials` | aQsi / `ofd_connection` | `approved` |
| [`aqsi_devices/peripherals/scales.md`](../data/knowledge/aqsi_devices/peripherals/scales.md) | `aqsi-device-scales` | aQsi / `peripheral_setup` | `approved` |
| [`aqsi_devices/peripherals/scanner-hub-power.md`](../data/knowledge/aqsi_devices/peripherals/scanner-hub-power.md) | `aqsi-device-scanner-hub-power` | aQsi / `peripheral_setup` | `approved` |
| [`aqsi_devices/peripherals/scanner.md`](../data/knowledge/aqsi_devices/peripherals/scanner.md) | `aqsi-device-scanner` | aQsi / `peripheral_setup` | `approved` |
| [`aqsi_devices/sales/deferred-order-refund.md`](../data/knowledge/aqsi_devices/sales/deferred-order-refund.md) | `aqsi-device-deferred-order-refund` | aQsi / `sales` | `approved` |
| [`aqsi_devices/sales/deferred-order.md`](../data/knowledge/aqsi_devices/sales/deferred-order.md) | `aqsi-device-deferred-order` | aQsi / `sales` | `approved` |
| [`aqsi_devices/sales/marked-beer.md`](../data/knowledge/aqsi_devices/sales/marked-beer.md) | `aqsi-device-marked-beer` | aQsi / `sales` | `approved` |
| [`aqsi_devices/sales/marked-product.md`](../data/knowledge/aqsi_devices/sales/marked-product.md) | `aqsi-device-marked-product` | aQsi / `sales` | `approved` |
| [`aqsi_devices/sales/standard-refund.md`](../data/knowledge/aqsi_devices/sales/standard-refund.md) | `aqsi-device-standard-refund` | aQsi / `sales` | `approved` |
| [`aqsi_devices/settings/android-clock.md`](../data/knowledge/aqsi_devices/settings/android-clock.md) | `aqsi-device-android-clock` | aQsi / `settings` | `approved` |
| [`aqsi_devices/shifts/cash-in-out.md`](../data/knowledge/aqsi_devices/shifts/cash-in-out.md) | `aqsi-device-cash-in-out` | aQsi / `shift_management` | `approved` |
| [`aqsi_devices/shifts/fiscal-status-report.md`](../data/knowledge/aqsi_devices/shifts/fiscal-status-report.md) | `aqsi-device-fiscal-status-report` | aQsi / `shift_management` | `approved` |
| [`aqsi_devices/shifts/opening-closing.md`](../data/knowledge/aqsi_devices/shifts/opening-closing.md) | `aqsi-device-opening-closing` | aQsi / `shift_management` | `approved` |
| [`aqsi_devices/shifts/x-report.md`](../data/knowledge/aqsi_devices/shifts/x-report.md) | `aqsi-device-x-report` | aQsi / `shift_management` | `approved` |
| [`aqsi_devices/start/first-start-internet.md`](../data/knowledge/aqsi_devices/start/first-start-internet.md) | `aqsi-device-first-start-internet` | aQsi / `equipment_setup` | `approved` |
| [`aqsi_devices/start/unbox-hardware.md`](../data/knowledge/aqsi_devices/start/unbox-hardware.md) | `aqsi-device-unbox-hardware` | aQsi / `equipment_setup` | `approved` |
| [`aqsi_devices/vat/vat22-configuration.md`](../data/knowledge/aqsi_devices/vat/vat22-configuration.md) | `aqsi-device-vat22-configuration` | aQsi / `vat_settings` | `draft` |
| [`aqsi_online/account/add-user.md`](../data/knowledge/aqsi_online/account/add-user.md) | `aqsi-online-account-add-user` | aQsi Online / `access` | `approved` |
| [`aqsi_online/account/contact-support.md`](../data/knowledge/aqsi_online/account/contact-support.md) | `aqsi-online-account-contact-support` | aQsi Online / `support` | `approved` |
| [`aqsi_online/account/create-role.md`](../data/knowledge/aqsi_online/account/create-role.md) | `aqsi-online-account-create-role` | aQsi Online / `access` | `approved` |
| [`aqsi_online/account/edit-user.md`](../data/knowledge/aqsi_online/account/edit-user.md) | `aqsi-online-account-edit-user` | aQsi Online / `access` | `approved` |
| [`aqsi_online/account/monitoring.md`](../data/knowledge/aqsi_online/account/monitoring.md) | `aqsi-online-account-monitoring` | aQsi Online / `cash_list` | `approved` |
| [`aqsi_online/account/my-cash-registers.md`](../data/knowledge/aqsi_online/account/my-cash-registers.md) | `aqsi-online-account-my-cash-registers` | aQsi Online / `cash_list` | `approved` |
| [`aqsi_online/account/register-account.md`](../data/knowledge/aqsi_online/account/register-account.md) | `aqsi-online-account-register-account` | aQsi Online / `access` | `approved` |
| [`aqsi_online/account/reset-password.md`](../data/knowledge/aqsi_online/account/reset-password.md) | `aqsi-online-account-reset-password` | aQsi Online / `access` | `approved` |
| [`aqsi_online/account/settings.md`](../data/knowledge/aqsi_online/account/settings.md) | `aqsi-online-account-settings` | aQsi Online / `account_settings` | `approved` |
| [`aqsi_online/fns/finish-reg.md`](../data/knowledge/aqsi_online/fns/finish-reg.md) | `aqsi-online-fns-finish-reg` | aQsi Online / `fns_registration` | `approved` |
| [`aqsi_online/fns/register-ip.md`](../data/knowledge/aqsi_online/fns/register-ip.md) | `aqsi-online-fns-register-ip` | aQsi Online / `fns_registration` | `approved` |
| [`aqsi_online/fns/register-ooo.md`](../data/knowledge/aqsi_online/fns/register-ooo.md) | `aqsi-online-fns-register-ooo` | aQsi Online / `fns_registration` | `approved` |
| [`aqsi_online/fns/reregister-fn.md`](../data/knowledge/aqsi_online/fns/reregister-fn.md) | `aqsi-online-fns-reregister-fn` | aQsi Online / `fns_registration` | `draft` |
| [`aqsi_online/integration/1c-setup.md`](../data/knowledge/aqsi_online/integration/1c-setup.md) | `aqsi-online-integration-1c-setup` | aQsi Online / `integration` | `draft` |
| [`aqsi_online/integration/direct-api.md`](../data/knowledge/aqsi_online/integration/direct-api.md) | `aqsi-online-integration-direct-api` | aQsi Online / `integration` | `approved` |
| [`aqsi_online/ofd/taxcom-account.md`](../data/knowledge/aqsi_online/ofd/taxcom-account.md) | `aqsi-online-ofd-taxcom-account` | aQsi Online / `ofd_connection` | `approved` |
| [`aqsi_online/receipts/correction-105.md`](../data/knowledge/aqsi_online/receipts/correction-105.md) | `aqsi-online-receipts-correction-105` | aQsi Online / `correction_receipt` | `draft` |
| [`aqsi_online/receipts/correction-12.md`](../data/knowledge/aqsi_online/receipts/correction-12.md) | `aqsi-online-receipts-correction-12` | aQsi Online / `correction_receipt` | `draft` |
| [`aqsi_online/receipts/enable-manual-receipt.md`](../data/knowledge/aqsi_online/receipts/enable-manual-receipt.md) | `aqsi-online-receipts-enable-manual-receipt` | aQsi Online / `receipt_issue` | `approved` |
| [`aqsi_online/receipts/full-refund.md`](../data/knowledge/aqsi_online/receipts/full-refund.md) | `aqsi-online-receipts-full-refund` | aQsi Online / `refund` | `approved` |
| [`aqsi_online/receipts/incorrect-105.md`](../data/knowledge/aqsi_online/receipts/incorrect-105.md) | `aqsi-online-receipts-incorrect-105` | aQsi Online / `correction_receipt` | `approved` |
| [`aqsi_online/receipts/partial-refund.md`](../data/knowledge/aqsi_online/receipts/partial-refund.md) | `aqsi-online-receipts-partial-refund` | aQsi Online / `refund` | `approved` |
| [`aqsi_online/setup/add-store.md`](../data/knowledge/aqsi_online/setup/add-store.md) | `aqsi-online-setup-add-store` | aQsi Online / `service_connection` | `approved` |
| [`aqsi_online/setup/company-details.md`](../data/knowledge/aqsi_online/setup/company-details.md) | `aqsi-online-setup-company-details` | aQsi Online / `service_connection` | `approved` |
| [`aqsi_online/setup/fiscalize.md`](../data/knowledge/aqsi_online/setup/fiscalize.md) | `aqsi-online-setup-fiscalize` | aQsi Online / `service_connection` | `approved` |
| [`aqsi_online/setup/order-cash-register.md`](../data/knowledge/aqsi_online/setup/order-cash-register.md) | `aqsi-online-setup-order-cash-register` | aQsi Online / `service_connection` | `approved` |
| [`aqsi_online/setup/sign-contract.md`](../data/knowledge/aqsi_online/setup/sign-contract.md) | `aqsi-online-setup-sign-contract` | aQsi Online / `service_connection` | `approved` |
| [`aqsi_online/use_cases/couriers-fiscalization.md`](../data/knowledge/aqsi_online/use_cases/couriers-fiscalization.md) | `aqsi-online-usecase-couriers-fiscalization` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/housing-krasinform-gorod.md`](../data/knowledge/aqsi_online/use_cases/housing-krasinform-gorod.md) | `aqsi-online-usecase-housing-krasinform-gorod` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/housing-register-payments.md`](../data/knowledge/aqsi_online/use_cases/housing-register-payments.md) | `aqsi-online-usecase-housing-register-payments` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/internet-store-cms-aggregator.md`](../data/knowledge/aqsi_online/use_cases/internet-store-cms-aggregator.md) | `aqsi-online-usecase-internet-store-cms-aggregator` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/retail-physical-vs-cloud.md`](../data/knowledge/aqsi_online/use_cases/retail-physical-vs-cloud.md) | `aqsi-online-usecase-retail-physical-vs-cloud` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/taxi-aggregator.md`](../data/knowledge/aqsi_online/use_cases/taxi-aggregator.md) | `aqsi-online-usecase-taxi-aggregator` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/taxi-cloud-or-terminal.md`](../data/knowledge/aqsi_online/use_cases/taxi-cloud-or-terminal.md) | `aqsi-online-usecase-taxi-cloud-or-terminal` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/transport-operator.md`](../data/knowledge/aqsi_online/use_cases/transport-operator.md) | `aqsi-online-usecase-transport-operator` | aQsi Online / `applicability` | `draft` |
| [`aqsi_online/use_cases/vending-telemetry.md`](../data/knowledge/aqsi_online/use_cases/vending-telemetry.md) | `aqsi-online-usecase-vending-telemetry` | aQsi Online / `applicability` | `draft` |
| [`atol_online/account/cash-reports.md`](../data/knowledge/atol_online/account/cash-reports.md) | `atol-online-account-cash-reports` | АТОЛ Онлайн / `cash_reports` | `approved` |
| [`atol_online/atol_pay/refund-full-partial.md`](../data/knowledge/atol_online/atol_pay/refund-full-partial.md) | `atol-online-22853-refund-full-partial` | АТОЛ Онлайн / `refund` | `approved` |
| [`atol_online/billing/balance-operations.md`](../data/knowledge/atol_online/billing/balance-operations.md) | `atol-online-11053-balance-operations` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/change-plan.md`](../data/knowledge/atol_online/billing/change-plan.md) | `atol-online-11078-change-plan` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/closing-docs-april-2026.md`](../data/knowledge/atol_online/billing/closing-docs-april-2026.md) | `atol-online-14145-closing-docs-april-2026` | АТОЛ Онлайн / `billing` | `draft` |
| [`atol_online/billing/closing-docs.md`](../data/knowledge/atol_online/billing/closing-docs.md) | `atol-online-14145-closing-docs` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/debt-payment.md`](../data/knowledge/atol_online/billing/debt-payment.md) | `atol-online-14133-debt-payment` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/documents-operations.md`](../data/knowledge/atol_online/billing/documents-operations.md) | `atol-online-14134-documents-operations` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/find-offer.md`](../data/knowledge/atol_online/billing/find-offer.md) | `atol-online-11059-find-offer` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/fn-invoice.md`](../data/knowledge/atol_online/billing/fn-invoice.md) | `atol-online-11075-fn-invoice` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/freeze-service.md`](../data/knowledge/atol_online/billing/freeze-service.md) | `atol-online-16576-freeze-service` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/invoice-composition.md`](../data/knowledge/atol_online/billing/invoice-composition.md) | `atol-online-17627-invoice-composition` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/reconciliation-acts.md`](../data/knowledge/atol_online/billing/reconciliation-acts.md) | `atol-online-11052-reconciliation-acts` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/refund-unused-funds.md`](../data/knowledge/atol_online/billing/refund-unused-funds.md) | `atol-online-11058-refund-unused-funds` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/renewal-invoice.md`](../data/knowledge/atol_online/billing/renewal-invoice.md) | `atol-online-11073-renewal-invoice` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/renewal-payment.md`](../data/knowledge/atol_online/billing/renewal-payment.md) | `atol-online-14144-renewal-payment` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/service-blocked.md`](../data/knowledge/atol_online/billing/service-blocked.md) | `atol-online-11077-service-blocked` | АТОЛ Онлайн / `billing` | `approved` |
| [`atol_online/billing/vat22-supplement.md`](../data/knowledge/atol_online/billing/vat22-supplement.md) | `atol-online-27074-vat22-supplement` | АТОЛ Онлайн / `billing` | `draft` |
| [`atol_online/connection/add-shop-step3.md`](../data/knowledge/atol_online/connection/add-shop-step3.md) | `atol-online-12161-add-shop-step3` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/company-registration.md`](../data/knowledge/atol_online/connection/company-registration.md) | `atol-online-12148-company-registration` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/enter-rnm.md`](../data/knowledge/atol_online/connection/enter-rnm.md) | `atol-online-12472-enter-rnm` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/ffd-accept-disabled.md`](../data/knowledge/atol_online/connection/ffd-accept-disabled.md) | `atol-online-11236-ffd-accept-disabled` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/ffd-choice-step3.md`](../data/knowledge/atol_online/connection/ffd-choice-step3.md) | `atol-online-12161-ffd-choice-step3` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/fns-preparation.md`](../data/knowledge/atol_online/connection/fns-preparation.md) | `atol-online-21944-fns-preparation` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/integrator-settings.md`](../data/knowledge/atol_online/connection/integrator-settings.md) | `atol-online-12473-integrator-settings` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/select-ofd.md`](../data/knowledge/atol_online/connection/select-ofd.md) | `atol-online-12149-select-ofd` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/sender-email.md`](../data/knowledge/atol_online/connection/sender-email.md) | `atol-online-11255-sender-email` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/shop-without-url.md`](../data/knowledge/atol_online/connection/shop-without-url.md) | `atol-online-11247-shop-without-url` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/step4-invoice.md`](../data/knowledge/atol_online/connection/step4-invoice.md) | `atol-online-12178-step4-invoice` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/step5-fns-data.md`](../data/knowledge/atol_online/connection/step5-fns-data.md) | `atol-online-12385-step5-fns-data` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/connection/step7-fn-activation.md`](../data/knowledge/atol_online/connection/step7-fn-activation.md) | `atol-online-16568-step7-fn-activation` | АТОЛ Онлайн / `service_connection` | `approved` |
| [`atol_online/contracts/disable-one-cashier.md`](../data/knowledge/atol_online/contracts/disable-one-cashier.md) | `atol-online-11071-disable-one-cashier` | АТОЛ Онлайн / `contract` | `approved` |
| [`atol_online/contracts/terminate-contract.md`](../data/knowledge/atol_online/contracts/terminate-contract.md) | `atol-online-11072-terminate-contract` | АТОЛ Онлайн / `contract` | `approved` |
| [`atol_online/edo/incoming-documents.md`](../data/knowledge/atol_online/edo/incoming-documents.md) | `atol-online-14749-incoming-documents` | АТОЛ Онлайн / `edo` | `approved` |
| [`atol_online/equipment/replace-kaznachey.md`](../data/knowledge/atol_online/equipment/replace-kaznachey.md) | `atol-online-24147-replace-kaznachey` | АТОЛ Онлайн / `equipment_replacement` | `approved` |
| [`atol_online/errors/amount-errors-16-23.md`](../data/knowledge/atol_online/errors/amount-errors-16-23.md) | `atol-online-22561-amount-errors-16-23` | АТОЛ Онлайн / `error_diagnosis` | `approved` |
| [`atol_online/errors/fn-and-marking-errors-116-414-421-148.md`](../data/knowledge/atol_online/errors/fn-and-marking-errors-116-414-421-148.md) | `atol-online-22561-fn-and-marking-errors-116-414-421-148` | АТОЛ Онлайн / `error_diagnosis` | `approved` |
| [`atol_online/errors/gateway-errors-timeout-128-protocol.md`](../data/knowledge/atol_online/errors/gateway-errors-timeout-128-protocol.md) | `atol-online-22561-gateway-errors-timeout-128-protocol` | АТОЛ Онлайн / `error_diagnosis` | `approved` |
| [`atol_online/errors/request-errors-26-1008.md`](../data/knowledge/atol_online/errors/request-errors-26-1008.md) | `atol-online-22561-request-errors-26-1008` | АТОЛ Онлайн / `error_diagnosis` | `approved` |
| [`atol_online/fn/blocked.md`](../data/knowledge/atol_online/fn/blocked.md) | `atol-online-18220-blocked` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fn/bring-own-fn.md`](../data/knowledge/atol_online/fn/bring-own-fn.md) | `atol-online-12789-bring-own-fn` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fn/choose-fn-with-excise.md`](../data/knowledge/atol_online/fn/choose-fn-with-excise.md) | `atol-online-22553-choose-fn-with-excise` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fn/fn-basics.md`](../data/knowledge/atol_online/fn/fn-basics.md) | `atol-online-11253-fn-basics` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fn/fns-after-fn-swap.md`](../data/knowledge/atol_online/fn/fns-after-fn-swap.md) | `atol-online-11069-fns-after-fn-swap` | АТОЛ Онлайн / `fns_registration` | `approved` |
| [`atol_online/fn/monitoring.md`](../data/knowledge/atol_online/fn/monitoring.md) | `atol-online-18126-monitoring` | АТОЛ Онлайн / `cash_list` | `approved` |
| [`atol_online/fn/receive-old-fn.md`](../data/knowledge/atol_online/fn/receive-old-fn.md) | `atol-online-20691-receive-old-fn` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fn/replacement-process.md`](../data/knowledge/atol_online/fn/replacement-process.md) | `atol-online-20054-replacement-process` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fn/replacement-reasons.md`](../data/knowledge/atol_online/fn/replacement-reasons.md) | `atol-online-11251-replacement-reasons` | АТОЛ Онлайн / `fiscal_drive` | `approved` |
| [`atol_online/fns/deregister-kkt.md`](../data/knowledge/atol_online/fns/deregister-kkt.md) | `atol-online-18251-deregister-kkt` | АТОЛ Онлайн / `fns_registration` | `approved` |
| [`atol_online/fns/removed-from-register.md`](../data/knowledge/atol_online/fns/removed-from-register.md) | `atol-online-18227-removed-from-register` | АТОЛ Онлайн / `fns_registration` | `approved` |
| [`atol_online/integration/api-test.md`](../data/knowledge/atol_online/integration/api-test.md) | `atol-online-11244-api-test` | АТОЛ Онлайн / `integration` | `approved` |
| [`atol_online/integration/cashier-throughput.md`](../data/knowledge/atol_online/integration/cashier-throughput.md) | `atol-online-22552-cashier-throughput` | АТОЛ Онлайн / `integration` | `approved` |
| [`atol_online/integration/catalog-cms-banks.md`](../data/knowledge/atol_online/integration/catalog-cms-banks.md) | `atol-online-12790-catalog-cms-banks` | АТОЛ Онлайн / `integration` | `approved` |
| [`atol_online/integration/integration-1c-versions.md`](../data/knowledge/atol_online/integration/integration-1c-versions.md) | `atol-online-12790-integration-1c-versions` | АТОЛ Онлайн / `integration` | `approved` |
| [`atol_online/integration/switch-ffd12.md`](../data/knowledge/atol_online/integration/switch-ffd12.md) | `atol-online-22555-switch-ffd12` | АТОЛ Онлайн / `integration` | `approved` |
| [`atol_online/integration/test-cashier.md`](../data/knowledge/atol_online/integration/test-cashier.md) | `atol-online-11254-test-cashier` | АТОЛ Онлайн / `integration` | `approved` |
| [`atol_online/integration/vat22-api.md`](../data/knowledge/atol_online/integration/vat22-api.md) | `atol-online-26152-vat22-api` | АТОЛ Онлайн / `integration` | `draft` |
| [`atol_online/law/54fz-before-connecting.md`](../data/knowledge/atol_online/law/54fz-before-connecting.md) | `atol-online-18537-54fz-before-connecting` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/54fz-exemptions-diagnostics.md`](../data/knowledge/atol_online/law/54fz-exemptions-diagnostics.md) | `atol-online-18536-54fz-exemptions-diagnostics` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/54fz-when-kkt-needed.md`](../data/knowledge/atol_online/law/54fz-when-kkt-needed.md) | `atol-online-16652-54fz-when-kkt-needed` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/advance-vs-prepayment.md`](../data/knowledge/atol_online/law/advance-vs-prepayment.md) | `atol-online-22554-advance-vs-prepayment` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/agent-contract-kkt.md`](../data/knowledge/atol_online/law/agent-contract-kkt.md) | `atol-online-16654-agent-contract-kkt` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/cloud-kkt-applicability.md`](../data/knowledge/atol_online/law/cloud-kkt-applicability.md) | `atol-online-16669-cloud-kkt-applicability` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/ffd-105-vs-12-basics.md`](../data/knowledge/atol_online/law/ffd-105-vs-12-basics.md) | `atol-online-16667-ffd-105-vs-12-basics` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/fiscal-doc-types-overview.md`](../data/knowledge/atol_online/law/fiscal-doc-types-overview.md) | `atol-online-16667-fiscal-doc-types-overview` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/fns-receipts-compliance.md`](../data/knowledge/atol_online/law/fns-receipts-compliance.md) | `atol-online-16668-fns-receipts-compliance` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/housing-utility-payments.md`](../data/knowledge/atol_online/law/housing-utility-payments.md) | `atol-online-16655-housing-utility-payments` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/internet-store-kkt.md`](../data/knowledge/atol_online/law/internet-store-kkt.md) | `atol-online-16653-internet-store-kkt` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/npd-receipts.md`](../data/knowledge/atol_online/law/npd-receipts.md) | `atol-online-16656-npd-receipts` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/patent-kkt-eligibility.md`](../data/knowledge/atol_online/law/patent-kkt-eligibility.md) | `atol-online-16656-patent-kkt-eligibility` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/sugary-drinks-classification.md`](../data/knowledge/atol_online/law/sugary-drinks-classification.md) | `atol-online-14414-sugary-drinks-classification` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/law/sugary-drinks-kkt-preparation.md`](../data/knowledge/atol_online/law/sugary-drinks-kkt-preparation.md) | `atol-online-14419-sugary-drinks-kkt-preparation` | АТОЛ Онлайн / `kkt_rules` | `draft` |
| [`atol_online/ofd/activate-first-ofd.md`](../data/knowledge/atol_online/ofd/activate-first-ofd.md) | `atol-online-23349-activate-first-ofd` | АТОЛ Онлайн / `equipment_setup` | `approved` |
| [`atol_online/ofd/activate-taxcom.md`](../data/knowledge/atol_online/ofd/activate-taxcom.md) | `atol-online-23415-activate-taxcom` | АТОЛ Онлайн / `ofd_connection` | `approved` |
| [`atol_online/ofd/change-provider.md`](../data/knowledge/atol_online/ofd/change-provider.md) | `atol-online-11239-change-provider` | АТОЛ Онлайн / `ofd_connection` | `approved` |
| [`atol_online/ofd/included-providers.md`](../data/knowledge/atol_online/ofd/included-providers.md) | `atol-online-11081-included-providers` | АТОЛ Онлайн / `ofd_connection` | `approved` |
| [`atol_online/ofd/what-is-ofd.md`](../data/knowledge/atol_online/ofd/what-is-ofd.md) | `atol-online-11256-what-is-ofd` | АТОЛ Онлайн / `ofd_connection` | `approved` |
| [`atol_online/partners/referral-program-guide.md`](../data/knowledge/atol_online/partners/referral-program-guide.md) | `atol-online-25514-referral-program-guide` | АТОЛ Онлайн / `partner_program` | `draft` |
| [`atol_online/receipts/advance-closing.md`](../data/knowledge/atol_online/receipts/advance-closing.md) | `atol-online-26774-advance-closing` | АТОЛ Онлайн / `receipt_issue` | `approved` |
| [`atol_online/receipts/automatic-shifts.md`](../data/knowledge/atol_online/receipts/automatic-shifts.md) | `atol-online-11257-automatic-shifts` | АТОЛ Онлайн / `shift_management` | `approved` |
| [`atol_online/receipts/correct-ffd105.md`](../data/knowledge/atol_online/receipts/correct-ffd105.md) | `atol-online-11243-correct-ffd105` | АТОЛ Онлайн / `correction_receipt` | `approved` |
| [`atol_online/receipts/correct-ffd12.md`](../data/knowledge/atol_online/receipts/correct-ffd12.md) | `atol-online-11243-correct-ffd12` | АТОЛ Онлайн / `correction_receipt` | `approved` |
| [`atol_online/receipts/mass-correction.md`](../data/knowledge/atol_online/receipts/mass-correction.md) | `atol-online-21114-mass-correction` | АТОЛ Онлайн / `correction_receipt` | `approved` |
| [`atol_online/receipts/payment-object-ffd105.md`](../data/knowledge/atol_online/receipts/payment-object-ffd105.md) | `atol-online-26773-payment-object-ffd105` | АТОЛ Онлайн / `receipt_issue` | `approved` |
| [`atol_online/receipts/payment-object-ffd12.md`](../data/knowledge/atol_online/receipts/payment-object-ffd12.md) | `atol-online-26852-payment-object-ffd12` | АТОЛ Онлайн / `receipt_issue` | `approved` |
| [`atol_online/receipts/receipt-creation-modes.md`](../data/knowledge/atol_online/receipts/receipt-creation-modes.md) | `atol-online-11242-receipt-creation-modes` | АТОЛ Онлайн / `receipt_issue` | `approved` |
| [`atol_online/receipts/receipt-journal-export.md`](../data/knowledge/atol_online/receipts/receipt-journal-export.md) | `atol-online-22560-receipt-journal-export` | АТОЛ Онлайн / `receipt_search` | `approved` |
| [`atol_online/receipts/receipt-location.md`](../data/knowledge/atol_online/receipts/receipt-location.md) | `atol-online-11258-receipt-location` | АТОЛ Онлайн / `receipt_issue` | `approved` |
| [`atol_online/receipts/xml-import.md`](../data/knowledge/atol_online/receipts/xml-import.md) | `atol-online-11250-xml-import` | АТОЛ Онлайн / `receipt_issue` | `approved` |
| [`atol_online/settings/add-more-shop-urls.md`](../data/knowledge/atol_online/settings/add-more-shop-urls.md) | `atol-online-11238-add-more-shop-urls` | АТОЛ Онлайн / `settings` | `approved` |
| [`atol_online/settings/agent-status.md`](../data/knowledge/atol_online/settings/agent-status.md) | `atol-online-22559-agent-status` | АТОЛ Онлайн / `settings` | `approved` |
| [`atol_online/settings/bso-feature.md`](../data/knowledge/atol_online/settings/bso-feature.md) | `atol-online-11248-bso-feature` | АТОЛ Онлайн / `settings` | `approved` |
| [`atol_online/settings/change-parameters.md`](../data/knowledge/atol_online/settings/change-parameters.md) | `atol-online-22060-change-parameters` | АТОЛ Онлайн / `settings` | `approved` |
| [`atol_online/support/contacts.md`](../data/knowledge/atol_online/support/contacts.md) | `atol-online-25850-contacts` | АТОЛ Онлайн / `support` | `approved` |
| [`atol_online/taxes/tax-2026-business-prep.md`](../data/knowledge/atol_online/taxes/tax-2026-business-prep.md) | `atol-online-26409-tax-2026-business-prep` | АТОЛ Онлайн / `vat_usn` | `draft` |
| [`atol_online/taxes/tax-2026-vat-changes.md`](../data/knowledge/atol_online/taxes/tax-2026-vat-changes.md) | `atol-online-26409-tax-2026-vat-changes` | АТОЛ Онлайн / `vat_usn` | `draft` |
| [`business/registration/ip-ooo-ao-differences.md`](../data/knowledge/business/registration/ip-ooo-ao-differences.md) | `biz-ip-ooo-ao-differences` | Регистрация бизнеса / `business_registration` | `draft` |
| [`business/registration/register-ip-fns.md`](../data/knowledge/business/registration/register-ip-fns.md) | `biz-register-ip-fns` | Регистрация бизнеса / `business_registration` | `draft` |
| [`business/registration/register-ooo-fns.md`](../data/knowledge/business/registration/register-ooo-fns.md) | `biz-register-ooo-fns` | Регистрация бизнеса / `business_registration` | `draft` |
| [`compliance/kkt-correction-receipt.md`](../data/knowledge/compliance/kkt-correction-receipt.md) | `kkt-correction-receipt-2026` | ККТ и законодательство / `kkt_rules` | `draft` |
| [`compliance/kkt-fns-2026-risk.md`](../data/knowledge/compliance/kkt-fns-2026-risk.md) | `kkt-fns-controls-2026` | ККТ и законодательство / `kkt_rules` | `draft` |
| [`edo/counterparty-no-edo.md`](../data/knowledge/edo/counterparty-no-edo.md) | `edo-counterparty-no-edi-2026` | ЭДО / `edo` | `draft` |
| [`edo/edi-operator-choice.md`](../data/knowledge/edo/edi-operator-choice.md) | `edo-operator-choice-criteria-2026` | ЭДО / `edo` | `draft` |
| [`edo/marked-goods-acceptance.md`](../data/knowledge/edo/marked-goods-acceptance.md) | `edo-marked-acceptance-2026` | ЭДО / `edo` | `draft` |
| [`edo/upd-discrepancy.md`](../data/knowledge/edo/upd-discrepancy.md) | `edo-upd-discrepancy-2026` | ЭДО / `edo` | `draft` |
| [`evotor/cash/evotor-6-receipt-copy.md`](../data/knowledge/evotor/cash/evotor-6-receipt-copy.md) | `evotor-6-receipt-copy-360005002514` | Эвотор / `receipt_print` | `approved` |
| [`evotor/cash/evotor-6-shift.md`](../data/knowledge/evotor/cash/evotor-6-shift.md) | `evotor-6-shift-360006708093` | Эвотор / `cash_operations` | `approved` |
| [`evotor/compliance/correction-receipt-scenarios.md`](../data/knowledge/evotor/compliance/correction-receipt-scenarios.md) | `evotor-correction-receipt-scope-20261019` | Эвотор / `kkt_rules` | `approved` |
| [`evotor/ffd/how-to-check-ffd.md`](../data/knowledge/evotor/ffd/how-to-check-ffd.md) | `evotor-ffd-version-check-20261019` | Эвотор / `fiscal_format` | `approved` |
| [`evotor/fn/fn-210.md`](../data/knowledge/evotor/fn/fn-210.md) | `evotor-fn-210-360004715693` | Эвотор / `error_diagnosis` | `approved` |
| [`evotor/fn/fn-212.md`](../data/knowledge/evotor/fn/fn-212.md) | `evotor-fn-212-360016100393` | Эвотор / `error_diagnosis` | `approved` |
| [`evotor/fn/fn-217.md`](../data/knowledge/evotor/fn/fn-217.md) | `evotor-fn-217-89e20cf4` | Эвотор / `error_diagnosis` | `approved` |
| [`evotor/fn/fn-231.md`](../data/knowledge/evotor/fn/fn-231.md) | `evotor-fn-231-360005098974` | Эвотор / `error_diagnosis` | `approved` |
| [`evotor/fn/fn-234.md`](../data/knowledge/evotor/fn/fn-234.md) | `evotor-fn-234-360005580254` | Эвотор / `error_diagnosis` | `approved` |
| [`evotor/fn/fn-235.md`](../data/knowledge/evotor/fn/fn-235.md) | `evotor-fn-235-360004715213` | Эвотор / `error_diagnosis` | `approved` |
| [`evotor/marking/code-check-error-first-steps.md`](../data/knowledge/evotor/marking/code-check-error-first-steps.md) | `evotor-mark-check-error-20261019` | Эвотор / `marking` | `approved` |
| [`evotor/marking/receive-marked-upd-prereqs.md`](../data/knowledge/evotor/marking/receive-marked-upd-prereqs.md) | `evotor-marked-goods-upd-20261019` | Эвотор / `marking` | `approved` |
| [`evotor/models/evotor-6-lite.md`](../data/knowledge/evotor/models/evotor-6-lite.md) | `evotor-model-6-lite-1d8e8869` | Эвотор / `model_features` | `approved` |
| [`evotor/models/evotor-7-2.md`](../data/knowledge/evotor/models/evotor-7-2.md) | `evotor-model-7-2-360002718353` | Эвотор / `model_features` | `approved` |
| [`evotor/models/evotor-7-3.md`](../data/knowledge/evotor/models/evotor-7-3.md) | `evotor-model-7-3-360002760513` | Эвотор / `model_features` | `approved` |
| [`evotor/network/mobile-internet-first-checks.md`](../data/knowledge/evotor/network/mobile-internet-first-checks.md) | `evotor-mobile-network-check-20261019` | Эвотор / `network_diagnostics` | `approved` |
| [`evotor/ofd/evotor-6-ofd-connection.md`](../data/knowledge/evotor/ofd/evotor-6-ofd-connection.md) | `evotor-6-ofd-connection-360014099534` | Эвотор / `receipt_transmission` | `approved` |
| [`evotor/ofd/evotor-7-3-ofd-connection.md`](../data/knowledge/evotor/ofd/evotor-7-3-ofd-connection.md) | `evotor-7-3-ofd-connection-360014099534` | Эвотор / `receipt_transmission` | `approved` |
| [`evotor/ofd/ofd-settings-check.md`](../data/knowledge/evotor/ofd/ofd-settings-check.md) | `evotor-ofd-settings-reference-20261019` | Эвотор / `receipt_transmission` | `approved` |
| [`evotor/ofd/ofd-subscription.md`](../data/knowledge/evotor/ofd/ofd-subscription.md) | `evotor-ofd-subscription-8865646794770` | Эвотор / `receipt_transmission` | `approved` |
| [`evotor/ofd/ofd-unable-to-connect.md`](../data/knowledge/evotor/ofd/ofd-unable-to-connect.md) | `evotor-ofd-error-not-connected-20261019` | Эвотор / `receipt_transmission` | `approved` |
| [`evotor/settings/time-mismatch-first-checks.md`](../data/knowledge/evotor/settings/time-mismatch-first-checks.md) | `evotor-time-mismatch-check-20261019` | Эвотор / `settings` | `approved` |
| [`evotor/tspiot/local-module-startup.md`](../data/knowledge/evotor/tspiot/local-module-startup.md) | `evotor-tspiot-localmodule-20261019` | Эвотор / `tspiot` | `approved` |
| [`evotor/tspiot/minimum-versions-2026.md`](../data/knowledge/evotor/tspiot/minimum-versions-2026.md) | `evotor-tspiot-requirements-20261019` | Эвотор / `tspiot` | `draft` |
| [`evotor/vat/vat-22-compatibility.md`](../data/knowledge/evotor/vat/vat-22-compatibility.md) | `evotor-vat22-components-20261019` | Эвотор / `vat_settings` | `draft` |
| [`marking/canned-goods-edo-oct-2026.md`](../data/knowledge/marking/canned-goods-edo-oct-2026.md) | `marking-canned-goods-edo-osu-202610` | Маркировка и Честный ЗНАК / `marking` | `draft` |
| [`marking/gtin-vs-item-tracking.md`](../data/knowledge/marking/gtin-vs-item-tracking.md) | `marking-gtin-vs-item-2026` | Маркировка и Честный ЗНАК / `marking` | `draft` |
| [`platformaofd/atol/ofd-transmission-checks.md`](../data/knowledge/platformaofd/atol/ofd-transmission-checks.md) | `platformaofd-atol-transmission-checks` | Платформа ОФД / `ofd_connection` | `approved` |
| [`platformaofd/flk/flk-507.md`](../data/knowledge/platformaofd/flk/flk-507.md) | `platformaofd-flk-507` | Платформа ОФД / `fiscal_document_control` | `approved` |
| [`platformaofd/flk/flk-508.md`](../data/knowledge/platformaofd/flk/flk-508.md) | `platformaofd-flk-508` | Платформа ОФД / `fiscal_document_control` | `approved` |
| [`platformaofd/fn/fn-number-in-lkk.md`](../data/knowledge/platformaofd/fn/fn-number-in-lkk.md) | `platformaofd-fn-number-in-lkk` | Платформа ОФД / `fiscal_drive` | `approved` |
| [`platformaofd/fn/registration-status.md`](../data/knowledge/platformaofd/fn/registration-status.md) | `platformaofd-registration-status` | Платформа ОФД / `fiscal_drive` | `approved` |
| [`platformaofd/fn/reregistration-kkt.md`](../data/knowledge/platformaofd/fn/reregistration-kkt.md) | `platformaofd-reregistration-kkt` | Платформа ОФД / `fiscal_drive` | `approved` |
| [`platformaofd/marking/crpt-indicators.md`](../data/knowledge/platformaofd/marking/crpt-indicators.md) | `platformaofd-crpt-indicators` | Платформа ОФД / `marking` | `approved` |
| [`platformaofd/ofd/archive-kkt.md`](../data/knowledge/platformaofd/ofd/archive-kkt.md) | `platformaofd-archive-kkt` | Платформа ОФД / `ofd_connection` | `approved` |
| [`platformaofd/ofd/connect-kkt.md`](../data/knowledge/platformaofd/ofd/connect-kkt.md) | `platformaofd-connect-kkt-to-lkk` | Платформа ОФД / `ofd_connection` | `approved` |
| [`platformaofd/ofd/fns-indicators.md`](../data/knowledge/platformaofd/ofd/fns-indicators.md) | `platformaofd-fns-indicators` | Платформа ОФД / `fns_monitoring` | `approved` |
| [`platformaofd/ofd/fns-registration.md`](../data/knowledge/platformaofd/ofd/fns-registration.md) | `platformaofd-fns-registration` | Платформа ОФД / `ofd_connection` | `approved` |
| [`platformaofd/ofd/lkk-cash-monitoring.md`](../data/knowledge/platformaofd/ofd/lkk-cash-monitoring.md) | `platformaofd-lkk-cash-monitoring` | Платформа ОФД / `cash_list` | `approved` |
| [`platformaofd/ofd/lkk-cash-search.md`](../data/knowledge/platformaofd/ofd/lkk-cash-search.md) | `platformaofd-lkk-cash-search` | Платформа ОФД / `cash_search` | `approved` |
| [`platformaofd/ofd/lkk-receipt-fns-status.md`](../data/knowledge/platformaofd/ofd/lkk-receipt-fns-status.md) | `platformaofd-lkk-receipt-fns-status` | Платформа ОФД / `receipt_status` | `approved` |
| [`platformaofd/ofd/lkk-receipt-search.md`](../data/knowledge/platformaofd/ofd/lkk-receipt-search.md) | `platformaofd-lkk-receipt-search` | Платформа ОФД / `receipt_search` | `approved` |
| [`platformaofd/ofd/partner-kkt-diagnostics.md`](../data/knowledge/platformaofd/ofd/partner-kkt-diagnostics.md) | `platformaofd-partner-kkt-diagnostics` | Платформа ОФД / `ofd_connection` | `approved` |
| [`platformaofd/ofd/tariff-activation.md`](../data/knowledge/platformaofd/ofd/tariff-activation.md) | `platformaofd-tariff-activation` | Платформа ОФД / `ofd_connection` | `approved` |
| [`platformaofd/shtrih/ofd-connection-checks.md`](../data/knowledge/platformaofd/shtrih/ofd-connection-checks.md) | `platformaofd-shtrih-connection-checks` | Платформа ОФД / `ofd_connection` | `approved` |
| [`software/1c/1c-faq-directory.md`](../data/knowledge/software/1c/1c-faq-directory.md) | `sw-1c-faq-directory` | 1С / `reference_directory` | `draft` |
| [`tspiot/astral-codes.md`](../data/knowledge/tspiot/astral-codes.md) | `astral-tspiot-errors-453-500-514` | ТС ПиОТ / `tspiot` | `draft` |
| [`tspiot/astral-diagnostics.md`](../data/knowledge/tspiot/astral-diagnostics.md) | `astral-tspiot-diagnostics-2026` | ТС ПиОТ / `tspiot` | `draft` |
| [`tspiot/tspiot-initial-diagnostics-2026.md`](../data/knowledge/tspiot/tspiot-initial-diagnostics-2026.md) | `tspiot-initial-diagnostics-astral-2026` | ТС ПиОТ / `tspiot` | `draft` |
| [`tspiot/tspiot-licence-and-sale-checks-2026.md`](../data/knowledge/tspiot/tspiot-licence-and-sale-checks-2026.md) | `tspiot-licence-and-sale-checks-astral-2026` | ТС ПиОТ / `tspiot` | `draft` |
