# P0.2 — безопасная диагностика DirectBank

Дата: 2026-10-23. Область: `app/procedure_policy.py` и `app/retrieval_pipeline.py`. HEAD до правки: `ce4231906368c4c6c872ec175c6eabca55026040`; уже существовавшие незакоммиченные P0.0/P0.1 файлы сохранены. Groq, индексация, production SQLite, Telegram worker и запись в Qdrant не применялись.

## Причина и минимальная правка

Для вопроса «В 1С перестали загружаться банковские выписки. Как разобраться?» `DialogueManager` правильно определял `bank_statement/diagnose`. Approved-статья [`directbank-all-accounts.md`](../data/knowledge/1c/bank/directbank-all-accounts.md) явно декларирует `load_bank_statements/list_bank_statements`, поэтому `operation_compatibility` отвергал каждый её chunk с `operation_mismatch:diagnose`, включая отдельный раздел «Безопасная диагностика». В [offline replay до правки](p02-directbank-before.json) три банковские статьи были отклонены, контекст и evidence пусты; [read-only Stage3 до правки](p02-qdrant-before.json) подтвердил то же на реальном retrieval.

Новый `reviewed_safe_diagnostic_section` разрешает `diagnose` **только** для approved-фрагмента задачи `bank_statement` с явными проверенными bank operations и точным заголовком «Безопасная диагностика». Это правило не добавляет `diagnose` в metadata документа и не делает `load`, `list` или `import` диагностическими действиями. `_expand` для такого запроса оставляет в model context лишь разрешённый диагностический fragment, а не соседние разделы статьи. При явно указанной версии 1С ниже минимальной версии статьи применяется `version_below_reviewed_minimum`; для all-accounts это `3.0.148`. Другие явные operation mismatches и service gates не менялись.

## Парный результат

Оба [offline replay после](p02-directbank-after.json) и [read-only Stage3 после](p02-qdrant-after.json) дали одинаковую границу evidence. Сводка машинной проверки: [p02-comparison.json](p02-comparison.json).

| Сценарий | До | После |
|---|---|---|
| Исходный вопрос о пропавших выписках | 0 документов, `operation_mismatch:diagnose`, evidence `none` | `batch-20261013-bank-directbank-all-accounts`, только «Безопасная диагностика», evidence `partial`, 3 шага |
| Две независимые переформулировки | 0 документов, evidence `none` | та же статья и раздел, evidence `partial`, 2 и 3 шага |
| Чужой сервис aQsi Online | 0 документов | 0; `service_mismatch_or_unlabeled` сохраняется |
| Версия 1С `3.0.147` | 0 документов | 0; `version_below_reviewed_minimum` и `operation_mismatch:diagnose` |
| Изменение ФН | см. оговорку ниже | без изменений |
| Перерегистрация ККТ | 0 документов, `unsafe` | 0, `unsafe` |

Подтверждённые передаваемые проверки: уточнить версию 1С и наличие DirectBank для нужного банка; открыть список «Банковские выписки» в соответствующем интерфейсе; сверить счета с настройкой обмена. Раздел о самой загрузке не передаётся. `claim_supported` подтвердил фразу об открытии списка и отверг позитивные команды «Повторно импортируйте», «Переподключите» и «Измените настройки». Другие банковские статьи без точного безопасного раздела по-прежнему получают `operation_mismatch:diagnose`.

**Оговорка по ФН:** отдельный raw retrieval при вопросе об изменении ФН как **до**, так и **после** P0.2 выбирает `platformaofd-reregistration-kkt` и помечает evidence как `partial`. Это предсуществующее поведение не вызвано P0.2. Нормальный `AnswerService` останавливает этот случай *до retrieval* через `fiscal_drive_change_scope_missing` и спрашивает действие и модель кассы; соответствующий gate и тест сохранены. P0.2 не расширял эту границу и не заявляет исправления сырого FN retrieval.

## Регрессии и ограничения

- Профильные тесты: **32 passed**; новые тесты проверяют три формулировки, точную границу раздела, grounding безопасной проверки, отклонение загрузки/импорта/переподключения/настроек, draft, чужой сервис, старую версию и фискальные hard gates.
- Полный `pytest`: **301 passed** на проверенной версии.
- Существующий `scripts.compare_retrieval_stage3` запущен на Stage3 для текущего кода и для двух baseline-модулей из HEAD, загруженных только в память. В обоих случаях 100 вопросов, 83 approved, expected context **81/83**. Все 100 строк совпали по `context_document_ids`, `selected_documents`, причинам отказа ожидаемой статьи, evidence status и insufficiency reason. Два прежних false rejections остались; новых false accept/false reject в этом benchmark **0**. Отчёты: [до](p02-benchmark-before.json), [после](p02-benchmark-after.json).
- Qdrant receipt до выполнения подтверждал существующую коллекцию; read-only replay после подтвердил 934 points и 672 approved. Это не тест клиентского ответа: Groq и generation не запускались. Текущие 15-turn и actual LLM `search_query` не переоценивались в P0.2.

P0.2 завершён в рамках локальной policy и read-only проверки. P0.3 не начат. Если дальнейший holdout обнаружит новый допуск несовместимой/опасной процедуры или новый отказ полезной статьи, следует откатить только P0.2 rule и оставить диагностическую трассу.
