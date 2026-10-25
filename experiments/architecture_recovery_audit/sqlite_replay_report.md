# P0.1: сквозной SQLite replay шести Telegram-реплик

> Исторический baseline до P0.2. Текущие offline результаты и причинная матрица: [отчёт P0.2](p02_report.md).

Дата: 2026-10-25. Это **offline интеграционный тест текущего рабочего дерева**, а не новый Telegram/Groq/Qdrant прогон. Код production не менялся. Тест: [`tests/test_telegram_pilot_sqlite_replay.py`](../../tests/test_telegram_pilot_sqlite_replay.py); обезличенные provider fixtures: [`telegram_pilot_20261025_provider.json`](../../tests/fixtures/telegram_pilot_20261025_provider.json); полный sanitized [trace](sqlite_bot_replay_20261025.json) содержит шесть raw fixture payload, validated route/state, terminal reason и точные offline ответы без user/chat/message IDs, API-ключей и токенов.

## Что действительно проверено

`bot.handle_message` вызывается шесть раз через fake Telegram update. До импорта `bot.py` подменяются только внешние границы: конфигурация тестового allowlist, startup Qdrant check, candidate source, Groq Understanding/Planner/Composer/Judge, Telegram I/O и экспертная SQLite. `ConversationStore`, его `begin/history/_sync_state`, `validate_response`, `observation_from_dict`, `DialogueManager`, `RetrievalPipeline`, `SourceFirstService`, локальное чтение approved Markdown и source scope проверки исполняются настоящим кодом. На каждом ходе `ConversationStore` открывается вновь из `tmp_path/isolated_pilot.sqlite3`; два повторных чтения состояния совпадают, факты в нём имеют exact spans только пользовательских строк, а SQLite содержит ровно шесть complete user и шесть complete assistant events. Рабочая `data/conversations.sqlite3` не открывалась тестом.

Фикстуры отражают **сохранённые validated значения** из прежнего ручного пилота. Raw JSON провайдера для тех шести ходов не сохранён; payload в тесте синтетический. Fake candidate source отдаёт только три существующие approved статьи: определение ОФД, диагностика Эвотор и поиск чека Платформы ОФД. Он не измеряет реальный Stage3 recall/rank. Fake Planner выбирает доступную содержательную секцию, поэтому тест диагностирует state/gate/replay и финальную сборку при фиксированном выборе, а не качество выбора модели. Composer возвращает предложение из источника, Judge выбирает ID реального evidence fragment. Нулевые token counts фикстуры не являются оценкой стоимости.

## Наблюдения

| Ход | Route / reason | Итог при фиксированных внешних ответах |
|---|---|---|
| 1. Широкая просьба | `clarify / dialogue_state_task_incomplete` | Clarify до retrieval. |
| 2. «Что такое ОФД?» | `answer / source_first_grounded_information_summary` | Approved определение, 1 Planner + 1 Composer + 1 Judge. |
| 3. Эвотор и непереданные чеки | `answer / source_first_exact_section` | Целая approved секция «Безопасные проверки»; Planner выбран фикстурой. |
| 4. Где проверить связь | `answer / source_first_exact_section` | Дословно повторил ответ хода 3, не ответил на конкретное «где». |
| 5. Интернет работает | `answer / source_first_exact_section` | Снова тот же полный раздел, не использовал новый факт для следующего шага. |
| 6. Поиск чека по ФН | `clarify / source_scope_context_missing` | Ограничение из scoped approved статьи всё ещё блокируется требованием сервиса. |

Отрицательный результат: **quality gate остаётся открытым** из-за ходов 4–6. Тест помечает его `xfail` после проверки SQLite/фактов и записи trace. Это не `pass` качества и не разрешение worker switch. При изменении route тест должен перейти в обычный `pass` только после устранения всех указанных quality failures. Из этих шести ходов нельзя вывести полную безопасность технической ветки: отдельные негативные S1–S6 пока не запускались.

## Проверки и границы

- `python -m pytest tests/test_telegram_pilot_sqlite_replay.py -q -rx`: **1 xfailed**, точные причины: два повторных ответа, блокировка FN limitation.
- `python -m pytest -q --disable-warnings`: **376 passed, 5 failed, 1 xfailed, 13 warnings**. Пять прежних падений не исправлялись в этой задаче; см. [failure_matrix](failure_matrix.md).
- `PILOT_REPLAY_OUTPUT=.../experiments/architecture_recovery_audit/sqlite_bot_replay_20261025.json` задан только при зафиксированном прогоне; обычный тест пишет trace лишь во временный каталог. Длина/содержимое JSON проверены на отсутствие ID/секретных ключей.
- Telegram worker PID 46544, `.env`, пользовательская SQLite, Qdrant, embeddings, approved knowledge и production-код не изменялись. Commit/push не выполнялись.

**Следующий шаг P0.2:** исправить общие механизмы task/expected/route, чтобы продолжения отвечали на новую информацию, а ограничение поиска по ФН можно было сообщить с явной областью источника без выдачи чужой процедуры. После этого повторить тот же SQLite replay и отдельные негативные safety cases; не подгонять ответ под формулировки шести fixture реплик.
