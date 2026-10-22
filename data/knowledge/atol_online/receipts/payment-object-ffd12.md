---
document_id: "atol-online-26852-payment-object-ffd12"
title: "Тег 1212 (payment_object) в ФФД 1.2"
category: "atol_online"
service: "АТОЛ Онлайн"
task_category: receipt_issue
operations: [issue_receipt]
manufacturer: "АТОЛ"
model: "АТОЛ Онлайн — облачная ККТ"
version: "ФФД 1.2"
source_url: "https://help.atol.online/article/26852"
source_type: "vendor_support_article"
published_at: null
collected_at: "2026-10-19"
verified_at: 2026-10-22
source_checked_at: 2026-10-22
status: approved
---

# Тег 1212 (payment_object) в ФФД 1.2

## Вопрос пользователя
Что такое payment_object в чеке ФФД 1.2?

## Подтверждённые сведения
Тег 1212 обозначает предмет расчёта. Для обычного товара, услуги, подакцизного или маркированного товара используются разные значения; в API это поле называется payment_object. При ошибках в нём проверяют тип номенклатуры, наличие маркировки и признаки регистрации кассы. Значения для маркированного товара с кодом и без кода различаются.

## Важно / когда передать специалисту
Не назначайте код признака без информации о товаре, ФФД и юридическом статусе сделки.

> Материал относится к облачному сервису «АТОЛ Онлайн», а не ко всем физическим моделям АТОЛ.
