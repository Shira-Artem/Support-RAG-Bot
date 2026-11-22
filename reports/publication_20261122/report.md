# Публикация интеграции — 22.11.2026

Владелец явно разрешил объединение и push подготовленной интеграции в main
обоих репозиториев. Предыдущие записи без commit/push датированы21.11.

- CRM: main709a318433a0b653dc78cd47fc646bd33eda641d, подтверждён git ls-remote.
- RAG: прежние integration commits4e16bcc/bedeca2 плюс conceptual context repair
  и текущие отчёты объединяются с локальным main. Candidate из manual review
  не переносится.
- Повтор RAG profile:59 PASS; CRM:78 PASS/17subtests. Логи рядом.
- Прежний full MySQL153 PASS; остальные ограничения общих suites не скрыты.
- Все семь dirty файлов исходного CRM checkout исключены; private hash receipt
  позволяет проверить их сохранность. .env/.local/БД не публикуются.
- Скан207 исходников/артефактов против известных private credentials:0 совпадений.
- Это Git publication, не production deployment: сервисы не перезапускались.

Объединение RAG:4 конфликта только в документации/placeholder reports разрешены
полными integration reports. Проверка SequenceMatcher:0 непустых строк исходного
main журнала потеряно. После объединения RAG profile вместе с support API:67 PASS
([лог](merged-rag-profile.txt)). Код не конфликтовал. Raw test logs и дословные
ответы сохранены с исходными пробелами; source/docs diff-check PASS.

Итог: RAG main merge1e75e63 и CRM main709a318 приняты GitHub и подтверждены
ls-remote. Все7 dirty файлов исходного CRM сохранены побайтно; эта старая локальная
main остаётся нетронутой. Force push не использовался. Публикация завершена;
следующий шаг — прежняя пользовательская приёмка.
Пользовательская приёмка TG↔Mini App, /chat visual, настоящий staff/MAX/HTTPS
и прежние factual/ProgressLedger ограничения остаются открытыми.

[Итог поведения и реальные проверки](../crm_natural_chat_20261121/report.md).
