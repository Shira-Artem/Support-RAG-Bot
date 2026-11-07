# B2.2d P0.2 — implementation checkpoint, 07.11.2026

## Реализация

- Добавлен `SEMANTIC_COMPOSER_ENABLED`; по умолчанию выключен. Включённый режим действует только при Coordinator route `grounded_information`. Route `technical_action` остался в действующей строгой ветке.
- Переиспользованы `semantic_evidence_selector`, `build_evidence_units`, существующие approved source/SHA/scope checks, SourceFirst safety helpers и Composer validation. Selector может выбрать несколько конкретных evidence IDs. В информационный Composer передаются только informational units; procedures и UI instructions не становятся его evidence.
- Для экспериментальной ветки отменено применение старого lexical conceptual gate до и после semantic ID selection. Подтверждённые service/manufacturer/model conflicts остаются локально отклонёнными. При отсутствии знаний, опасном фискальном запросе или провале проверки ответ завершается escalation или точным выбранным source evidence; соседняя статья и неподтверждённая процедура не используются.
- Composer может вернуть JSON `{"answer": ...}`; принимается только объект с единственным строковым ключом `answer`. Python проверяет каждое предложение на grounding, действия, опасные операции и обязательные condition/warning sentences. При отказе Composer fallback проходит повторную проверку exact selected text.
- Исправлен component-state reducer: если источник содержит совместную проверку даты и времени и пользователь сообщает только неверное время, state хранит `time=failed`, `date=unknown`; unknown не получает клиентскую цитату. Более позднее подтверждение даты заменяет unknown. Composer не пишет в Ledger и не меняет результаты.

## Offline результаты

Профильный набор включает semantic selector, P0.1, multi-component Ledger, SourceFirst dialogue и SQLite replay: **211 passed / 4 historical xfailed**.

Дополнительно: в experimental `grounded_information` route approved candidate, отвергнутый только по `task_mismatch:*`, разрешается по локально сверенным approved article sections и может пройти ранний sufficiency gate только при наличии такой секции; любой дополнительный rejection reason блокирует его. Без опции поведение `_source_sections` и SourceFirst остаётся прежним. Регрессионный helper-тест проходит.

Отрицательные offline проверки: foreign service, wrong model, draft evidence, question-only/no evidence, dangerous FN disable/delete request, unsupported menu instruction. Отдельно проверено, что Composer с выдуманным пунктом меню отклоняется и используется только выбранная точная approved sentence. Multi-component regression подтверждает `date=unknown`, `time=failed` при частичном сообщении.

Stage3 endpoint `127.0.0.1:6333` не ответил (ConnectTimeout). Поэтому полный `bot.handle_message → Retrieval/Stage3 → semantic selection → Composer` offline E2E не запускался; admission bridge проверен unit-level, runtime retrieval — нет; замены Stage3 либо записи в рабочую базу не делались.

## Groq LIVE на новых вопросах

Изолированный live runner использовал real Groq selector и Composer, локальную approved section с её SHA и новый `DialogueState`. Не открывались SQLite, Qdrant, Telegram, production worker или frozen holdout. Это проверяет selector/Composer, но не retrieval.

| Вопрос | BEFORE SourceFirst | AFTER | Проверка |
|---|---|---|---|
| В каких условиях 1С:Бухгалтерия сможет автоматически получать выписки через DirectBank? | «В approved-источниках нет подходящего концептуального объяснения; не буду подменять его технической инструкцией. Запросите специалиста.» | Точный выбранный ответ: с версии 3.0.195 поддерживаются расписание и параметры автоматического получения через 1С:ДиректБанк; поддержка зависит от банка. | Composer предложил близкую перефразировку, claim gate отклонил её; exact selected evidence прошёл проверку. |
| Для стороннего USB-хаба производитель подтверждает работу одновременно с зарядкой кассы? | «Какой сервис или оператор ОФД используется?» | «Для сторонних USB-хабов поведение может отличаться, гарантированной совместимости нет.» | Естественный Composer ответ принят; source, scope и safety прошли. |
| Что происходит с фискальным документом после отправки ОФД? | Краткое дословное определение из инструкции АТОЛ Онлайн. | Тот же exact approved факт: ОФД получает документы от зарегистрированной ККТ, обрабатывает и передаёт в ФНС в предусмотренном формате. | Composer paraphrase отклонена, точный выбранный ID безопасно принят. |

Полный JSON с кандидатами, ID, SHA, дословными Composer output, validation, token usage и итоговыми ответами: [p02_selected_live.json](p02_selected_live.json). Предшествующие отрицательные результаты сохранены в журнале; первая попытка остановилась до HTTP из-за YAML `date` serialization в harness. Следующий LIVE показал JSON envelope и причину claim rejection; schema parsing исправлен и повторён.

## Итог и открытое

P0.2 остаётся **NO-GO** как общий quality gate: новый путь полезно отвечает на USB вопрос, DirectBank и OFД безопасно отвечают fallback source text, но два естественных paraphrase не прошли независимый claim validator; полный RAG `bot.handle_message` путь и live negative set не проверены из-за отсутствующего Stage3 endpoint. Production defaults не менялись. Frozen holdout, approved KB и production SQLite не тронуты.

Следующий шаг: поднять доступный read-only Stage3, прогнать offline E2E через `bot.handle_message` с actual retrieval кандидатов и negative controls, затем ограниченный Groq LIVE через тот же путь. Только после этого пересмотреть P0.2 GO.

