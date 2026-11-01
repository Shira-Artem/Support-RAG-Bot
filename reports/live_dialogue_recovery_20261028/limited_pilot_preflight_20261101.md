# Ограниченный Telegram-пилот — preflight 2026-11-01

## Решение

**LIMITED_PILOT_GO. Production GO не выдан.** Запущен один Telegram worker после полного pytest, двух коротких реальных контрольных E2E и подготовки откатного backup. Telegram-сообщения от имени владельца не отправлялись.

## Preflight

- **A — АТОЛ Онлайн, API-чек после оплаты.** Один изолированный реальный E2E. Understanding закрепил `receipt/diagnose`, `analysis_required=false`; Coordinator направил в технический retrieval. Поиск прошёл по read-only Stage3; применимого approved evidence не найдено (`no_task_matched_candidates`). Бот честно сообщил об отсутствии подтверждённой инструкции. Ложной остановки до retrieval нет.
- **B — комбинированная оплата Эвотор.** Один изолированный реальный E2E. Understanding закрепил `general/explain`, Coordinator выбрал grounded-information и запустил поиск. Approved статьи по точному вопросу в индексе нет; выбранные частичные материалы об ОФД не использованы как подтверждение. Ответ отмечен как общее объяснение модели, не по approved-документации; full evidence не заявлено. Требуется ручная оценка корректности ответа.
- **C — чужие сервисы / достаточность.** Ноябрьский real trace сохранил явные Saby, Диадок и БИФИТ и вернул для них ответ «нет подтверждённой применимой инструкции» без чужих инструкций. Тесты metadata/source-scope и unresolved fallback проходят, в том числе запрет generic БИФИТ на evidence БИФИТ Касса и approved-only gates. Эти три сценария остаются KB gaps.
- **D — Groq HTTP 400.** Локальный воспроизводимый тест искусственно поднимает `UnderstandingError(400)`: исходное сообщение сохранено, старый task state не меняется, Coordinator/retrieval не запускаются, SQLite после reopen имеет `quick_check=ok`; следующая валидная реплика проходит обычный путь. Аналогично покрыт HTTP 429. Редкий provider 400 не объявлен устранённым; необработанного исключения/порчи состояния нет.
- **Сохранённые positive controls.** В последнем E2E от 1 ноября Эвотор 6 выдал approved-инструкцию; Эвотор 7.3 завершил последовательность из трёх ходов с сохранением результатов пользователя. Их повторно не расходовали.
- **Полный pytest после исправления:** Python 3.14 — `547 passed, 4 xfailed, 13 warnings`. Python 3.12 в окружении `.venv` использует несовместимый CPython 3.14 optional `ormsgpack` из `.local/vnext-deps`; поэтому полный итоговый прогон зафиксирован на Python 3.14, где optional extension совместима.

## Ограничение live preflight

Groq controls: один запрос АТОЛ Онлайн и один комбинированной оплаты; оба завершились без provider error. Это проверка двух сценариев, не доказательство отсутствия intermittent HTTP 400. В B база не содержит подтверждённой статьи о комбинированной оплате; полученное общее объяснение явно маркировано как не основанное на approved-документации. Не одобрять его как инструкцию и не расширять KB в рамках этого пилота.

## Worker и runtime

- PID **13292**, ровно один `bot.py` worker; startup log содержит `Application started`.
- Python **3.14**, Source-first и Coordinator включены только переменными окружения дочернего процесса; используется прежний allowlist из трёх Telegram ID. Список ID и секреты в отчёте не раскрываются.
- Groq `openai/gpt-oss-20b`, reasoning `medium`; selector и handoff выключены.
- Qdrant `knowledge_stage3_retrieval_20261022`, green/934, demo=false, прежний volume `rag_qdrant_storage`; только чтение.
- Runtime receipt `.local/bot-runtime.json`: 33/33 актуальных `bot.py` + `app/*.py` SHA совпали с диском; allowlist count/hash и `.env` SHA совпали с предыдущим gate.
- `.env`, approved KB, Qdrant index, модель и allowlist не изменялись. Запуск использовал process-only overrides для Source-first/Coordinator и существующей Stage3 collection.
- Перед запуском создан backup `.local/backups/limited-pilot-20261101T125226Z/`: обе SQLite (`quick_check=ok`, conversations pending=0), runtime source snapshot и 269 KB markdown-файлов.
- Startup log: `.local/limited-pilot-20261101/stdout.log`; stderr: `.local/limited-pilot-20261101/stderr.log`. Runtime receipt: `.local/bot-runtime.json`.

## Ручной пилот

Проверить обычный вопрос об ОФД; Эвотор 6; триходовый Эвотор 7.3; входящий документ Saby; статус УПД Диадок; столы/терминал БИФИТ; DirectBank-выписки; физический aQsi и aQsi Online; АТОЛ Онлайн API-чек после оплаты; свободную формулировку по каждому доступному вопросу; продолжение диалога, ответ «не знаю» и смену темы. Подробные формулировки переданы владельцу в итоговом сообщении.

Для каждого ответа диагностика сохраняет raw validated Understanding, DialogueState до/после SQLite, Coordinator decision, сформированный retrieval query, candidate rejection/selected sources, source scope, Planner/Composer calls, итоговый ответ и ошибки. Артефакт двух новых E2E: `preflight_atol_evotor_20261101.json`.
