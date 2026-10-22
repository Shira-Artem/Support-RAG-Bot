---
document_id: platformaofd-lkk-receipt-search
title: 'Платформа ОФД: поиск чеков и фильтры'
category: ofd
manufacturer: null
model: null
version: null
source_url: https://platformaofd.ru/baza-znaniy/lkk-razdel-cheki/
source_type: ofd_knowledge_base
published_at: null
collected_at: 2026-10-12
verified_at: 2026-10-22
evidence_coverage:
  search_receipt: full
status: approved
service: Платформа ОФД
task_category: receipt_search
operations:
- search_receipt
search_fields:
- receipt_period
- document_type
- store
- cash_name
- registration_number
- fiscal_document_number
- fiscal_sign
- tag
- tag_value
- shift_number
- amount
- cashier
- payment_type
- calculation_sign
- fns_status
- marking
source_checked_at: 2026-10-22
---

# Платформа ОФД: поиск чеков и фильтры

## Поиск чеков
Маршрут: «Чеки» → «Поиск чеков». Период задаётся датами пробития, а не поступления в ОФД. Для прошлого месяца выберите календарные границы нужного месяца. Основные параметры: тип документа, магазин, касса по названию или РНМ; отдельно доступны ФД и ФП из чека.

## Дополнительные условия
Можно отбирать по номеру смены, диапазону суммы, полному или частичному имени кассира, способу оплаты, признаку расчёта и статусу ФНС. Для дополнительного тега задаётся его значение; пустое значение отбирает документы с заполненным выбранным тегом. Проверка маркировки доступна при активном тарифе УМ.

## Ограничения
ФН не подтверждён как прямой фильтр чеков. Не подменяйте ФН номером ФД или ФП. Поиск кассы по ФН описан отдельно. Отсутствие поля в статье не доказывает отсутствие функции в сервисе.
