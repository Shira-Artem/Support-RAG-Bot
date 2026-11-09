# Ручной Telegram-тест Support-RAG-Bot — 09.11.2026

## Назначение и границы

Пакет фиксирует ручной тест существующего Telegram-аккаунта с 08:09:25 до 08:29:40 МСК. Экспорт получен из фактической SQLite, указанной в окружении работающего процесса как `CONVERSATION_DB_PATH`, через согласованный read-only SQLite backup. В целевом временном окне база содержит один distinct user ID/chat ID; сами значения удалены. В snapshot попали **9 отдельных диалогов, 25 ходов и 50 сохранённых сообщений**. Включены повторы, пустые/квотно-заблокированные ответы, а также созданная и подтверждённая заявка специалисту. Записи не объединялись между conversation ID.

По локальному Groq rate trace за окно: **61 HTTP попытка** (49×200, 11×429, 1×400), **111119 успешных токенов**; отдельно записаны 6 bounded retry events и одна local quota deferral. Повторные retry events не считаются HTTP попытками.
Это доказательная база для двух независимых исследований, а не отчёт о причинах и не оценка новой архитектуры. Наблюдения отделены от гипотез. Ничего не восстановлено из памяти или новых model calls; отсутствующие поля отмечены `not_recorded`.

## Baseline и runtime

- Кодовый checkpoint: [`fce09b45f1264fe3ece56214c127de71365bfb0f`](https://github.com/Shira-Artem/Support-RAG-Bot/commit/fce09b45f1264fe3ece56214c127de71365bfb0f).
- Документационный/runtime HEAD на старте ручного теста: [`79ee5597bcc7e13b3e1ba6228073571aa5cb6f22`](https://github.com/Shira-Artem/Support-RAG-Bot/commit/79ee5597bcc7e13b3e1ba6228073571aa5cb6f22). Receipt работающего процесса указывает этот SHA; SHA-256 всех 35 файлов receipt совпали с checkout. Между `fce09b4` и `79ee559` нет изменений `bot.py`/`app/`.
- Фактический процесс стартовал в 08:04:26 МСК 09.11.2026; polling поднялся без startup error или конфликта. Receipt и источник процесса подтверждают Groq `openai/gpt-oss-20b`, reasoning `medium`, SourceFirst, Coordinator и Semantic Composer включены. Отдельный `SEMANTIC_EVIDENCE_SELECTOR_ENABLED` flag был `false`; при включённом experimental Composer selection-stage всё же присутствует в diagnostics у 8 ходов. Handoff отправка выключена. Stage3 collection `knowledge_stage3_retrieval_20261022`, 934 points; demo mode false. At final read-only process check no `bot.py` process was present; termination time/reason were not recorded, and the process was not restarted.
- Подробности конфигурации, проверки кода и локального snapshot: [`runtime_manifest.json`](runtime_manifest.json). Секреты, Telegram ID, chat ID и allowlist hash не экспортированы.

## Файлы пакета

- [`conversations.md`](conversations.md) — полная переписка по каждому диалогу в точной последовательности, с временем MSK и UTC.
- [`pipeline_traces.md`](pipeline_traces.md) — ход за ходом Understanding, DialogueState, Coordinator, RAG query, retrieval/candidates, сохранённые ответы стадий, проверки, финальный текст, latency/usage и ошибки. Кандидаты перечислены с их сохранёнными score и причинами.
- [`turns.jsonl`](turns.jsonl) — одна запись на ход; включает обезличенные diagnostics, retrieval candidates/results, состояния `dialogue_turns` и `dialogue_states_v2`, заявку и статус эскалации. Все внутренние ссылки на сообщения заменены на `Dxx-Txx`. It also includes sanitized Understanding prompts/results and per-turn Groq HTTP attempts with statuses, latency, token usage, 429/400 errors, and retry scheduling.
- [`failure_catalog.md`](failure_catalog.md) — индекс наблюдаемых проблем по тем же ID; без приписывания виновного компонента.
- [`investigation_guide.md`](investigation_guide.md) — общий протокол двух независимых исследований и предлагаемые изолированные ветки/worktree.

## Как читать

`D01`–`D09` — отдельные диалоги; `Dxx-Tnn` — ходы внутри диалога. `continuation=true` и статусы сообщений взяты из SQLite. Время базы сохранено в UTC и дополнено московским временем (UTC+03:00). В JSONL вложенный объект `pipeline` содержит исходные сохранённые диагностические поля после удаления пользовательских идентификаторов и API request ID. `not_recorded` означает, что данных не было в снимке; это не следует трактовать как отсутствие соответствующего этапа в runtime.

Полный исходный SQLite snapshot и генератор экспорта оставлены только локально в ignored-папке `.local/manual-test/evidence_20261109_0809/`. В Git попадает только обезличенный диагностический экспорт и документационные ссылки. Публикация не включает raw logs, `.env`, пользовательские/чатовые ID, секреты или private messages других пользователей.
The original local Understanding and Groq rate traces also remain under ignored `.local/`; the repository contains only the recursively scrubbed per-turn export.

## Статус расследования

Пакет фиксирует baseline для гипотез A (Python-гейты, SourceFirst, Planner/fallback) и B (Understanding, состояние задачи, retrieval, промпты и выбор evidence). Эти гипотезы ещё не проверялись в рамках этого пакета. См. [`investigation_guide.md`](investigation_guide.md).
