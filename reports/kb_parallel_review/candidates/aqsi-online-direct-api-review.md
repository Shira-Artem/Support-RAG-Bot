---
document_id: aqsi-online-direct-api-sme-candidate
title: 'aQsi Online: подготовка прямой API-интеграции'
category: integration
service: aQsi Online
task_category: integration
operations: [configure_integration]
evidence_coverage:
  configure_integration: partial
manufacturer: aQsi
model: aQsi Online (облачная касса)
version: null
source_url: https://aqsi.online/instructions/getting-started/kak-nastroit-pryamoe-podklyuchenie-k-servisu
source_type: vendor_support_article
published_at: null
collected_at: '2026-11-14'
source_checked_at: '2026-11-14'
verified_at: null
status: draft
requires_sme_review: true
review_note: 'Предложение по P0-19 для замены существующей карточки. Вид передаваемого материала и актуальные интеграции должен подтвердить оператор.'
---

# aQsi Online: подготовка прямой API-интеграции

## Применимость
Облачный сервис aQsi Online. Для подключения сайта производитель описывает API и готовые модули CMS. Для прямого API запросите у поддержки доступ к тестовой среде и согласуйте проверку обмена, затем порядок перехода в рабочую среду со специалистом интеграции.

## Ключи и сертификат
Производитель сообщает, что для рабочего контура нужны ключи подписи запросов и сертификат, но в краткой инструкции не уточняет вид передаваемого ключевого материала. До передачи любых файлов уточните в официальной технической поддержке точный формат запроса сертификата и адресата. Закрытый ключ, пароли и секреты не передавайте в поддержку или чат. Разработчик должен самостоятельно проверить официальную документацию и безопасный канал обмена.

## Границы
Список модулей CMS, версии API, алгоритмы подписи и содержимое файлов нуждаются в проверке у оператора. Не отправляйте реальные чеки для проверки интеграции без согласованного сценария. Этот draft предназначен для экспертной оценки как возможная замена `aqsi-online-integration-direct-api`; он не утверждён для индексации.

[Инструкция aQsi Online](https://aqsi.online/instructions/getting-started/kak-nastroit-pryamoe-podklyuchenie-k-servisu) описывает тестовую среду, ключи и сертификат; какой именно материал передаётся, она не уточняет.
