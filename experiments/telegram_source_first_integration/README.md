# Запуск Source-first в существующем Telegram-боте

Новый бот не создаётся. Используются прежний `.env`, токен, Qdrant, Groq и `data/conversations.sqlite3`. `RAG_ENGINE` задаётся только в процессе запуска; `.env` и хранилище не меняются. По прямому указанию владельца Source-first allowlist наследуется из прежнего `EXPERT_TELEGRAM_IDS` (только текущие ID; значения не печатаются).

## Проверка перед запуском

Из PowerShell в корне репозитория:

```powershell
python experiments/telegram_source_first_integration/preflight.py
python experiments/telegram_source_first_integration/smoke.py
```

Остановите прежний worker, если он появился. Lock `.local/bot.lock` и PID receipt `.local/bot-runtime.json` относятся к этому же checkout; перед стартом сверьте, что PID receipt не работает. Не стартуйте второй polling процесс.

## Windows PowerShell

```powershell
Set-Location C:\Users\Shira\Documents\ChatGPT\Rag
$env:RAG_ENGINE = 'source_first'
python bot.py
```

Оставьте это окно открытым во время ручного диалога с прежним ботом. В Telegram выберите «Свободный диалог». Source-first активен только для старого allowlist; остальные пользователи идут по legacy `AnswerService`.

## Запуск из WSL через установленный Windows Python

Для этой машины обнаружен только `docker-desktop`, пользовательского WSL дистрибутива пока нет. Если запускать команду из уже установленного WSL, можно вызвать тот же Windows runtime:

```bash
cd /mnt/c/Users/Shira/Documents/ChatGPT/Rag
cmd.exe /c "cd /d C:\Users\Shira\Documents\ChatGPT\Rag && set RAG_ENGINE=source_first && C:\Python314\python.exe bot.py"
```

Так сохраняются Windows Python и его установленные зависимости. Альтернатива для настроенного Linux Python/dependencies:

```bash
cd /mnt/c/Users/Shira/Documents/ChatGPT/Rag
export RAG_ENGINE=source_first
export WSLENV="${WSLENV:+$WSLENV:}RAG_ENGINE/u"
python3 bot.py
```

## Остановка и откат

- Остановка: нажмите `Ctrl+C` в окне единственного polling worker и дождитесь завершения процесса.
- Откат: после остановки запустите прежний движок в этом же checkout:

```powershell
Set-Location C:\Users\Shira\Documents\ChatGPT\Rag
$env:RAG_ENGINE = 'legacy'
python bot.py
```

Rollback не трогает историю диалогов, отзывы, очередь обращений, Qdrant и `.env`.

## Трассы и обезличенный экспорт

Каждый ответ сохраняется существующим `ConversationStore`; `rag_engine` отличает Source-first, а диагностика содержит состояние задачи, retrieval candidates/reasons, Planner proposal, выбранный источник/секцию и SHA, статус финальной проверки, полный ответ, provider/model, токены, задержки и ошибку (если была). После ручной проверки экспортируйте только Source-first ходы в локальный JSONL:

```powershell
python experiments/telegram_source_first_integration/export_anonymized.py --output .local/source-first-export.jsonl
```

Экспорт не включает Telegram user/chat IDs, заменяет email/телефоны и распространённые явно подписанные поля с персональными данными. Автоматическая маскировка эвристическая; проверьте файл вручную перед передачей кому-либо. Сырая история остаётся в прежней локальной SQLite.

## Ограничения

- Проверен локальный preflight без LLM; реальные Groq-вызовы начнутся только на сообщениях в Telegram.
- Source-first V1.2-B не прошёл offline quality gate. После самостоятельных диалогов сначала разберите трассы; не считать успешный запуск оценкой качества.
- Кнопка специалиста сохраняет обращение в текущем локальном хранилище и прямо сообщает, что доставка реальному сотруднику не настроена.
- В preflight есть предупреждение несовпадения версий Qdrant Python client 1.19.1 и server 1.15.4; текущий read-only поиск прошёл.
