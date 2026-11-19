---
document_id: platformaofd-test-endpoint-conflict-review-draft
title: 'Платформа ОФД: расхождение тестового IP в карточках АТОЛ и Штрих'
category: ofd
service: Платформа ОФД
task_category: ofd_connection
operations: [check_transmission]
manufacturer: Платформа ОФД
model: 'АТОЛ / Штрих-М; применять только после проверки модели'
version: 'Страницы оператора без даты/версии'
source_url: https://platformaofd.ru/baza-znaniy/nastrojka-kkt-atol/
source_type: ofd_knowledge_base
published_at: null
collected_at: '2026-11-17'
verified_at: null
source_checked_at: '2026-11-17'
status: draft
requires_sme_review: true
evidence_coverage:
  check_transmission: partial
review_note: 'Section-level review candidate for P1-39/P1-40, not a standalone article. Official pages conflict with approved test-server IP; DNS, network reachability and actual endpoint were not tested. Do not advise changing any value before confirmation by the OFD/KKТ engineer.'
---

# Расхождение в адресе тестового сервера Платформы ОФД

## Что обнаружено

Две страницы официальной базы Платформы ОФД — [настройка АТОЛ](https://platformaofd.ru/baza-znaniy/nastrojka-kkt-atol/) и [настройка Штрих](https://platformaofd.ru/baza-znaniy/nastroika-kkt-shtrih/) — при прямом чтении 17.11.2026 указывают тестовый hostname `ofdt.platformaofd.ru`, IP `195.3.180.5` и порт `19081`. В текущих карточках АТОЛ и Штрих указан тот же hostname и порт, но IP `185.170.204.85`.

В документации оператора также приведён отдельный рабочий адрес `ofdp.platformaofd.ru`, IP `185.170.204.91`, порт `21101`. Рабочие и тестовые параметры нельзя смешивать.

## Безопасный порядок

1. Не менять IP, hostname, порт или таблицы ККТ только по этому расхождению.
2. Уточнить у Платформы ОФД и инженера, какой endpoint действует для конкретной модели, драйвера и контура; подтвердить, нужен ли вообще тестовый сервер для задачи клиента.
3. Перед изменениями сверить резервируемые текущие параметры и фактическое состояние обмена. Не переносить тестовый endpoint в production.
4. Если оператор подтверждает значение, обновление существующих статей выполнять отдельным review и SME-переутверждением; не создавать дублирующие инструкции.

## Что не установлено

Страницы не показывают дату/номер ревизии. DNS-разрешение, сетевую доступность и фактический endpoint тестовой среды не проверяли. Поэтому этот кандидат фиксирует конфликт источника и ограничивает совет, но не утверждает, какое из двух IP сейчас рабочее.

## Передача

Предложение предназначено только для согласования фрагментов `platformaofd/atol/ofd-transmission-checks.md` и `platformaofd/shtrih/ofd-connection-checks.md`. Требуется подтверждение оператора/инженера ККТ. Не индексировать как отдельную статью.
