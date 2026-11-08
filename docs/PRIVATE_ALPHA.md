# Private Alpha: локальный Telegram-runtime

**Обновление 2026-11-08:** владелец выбрал ручной тест на существующем Telegram-боте и токене из `.env`; прежний вариант с отдельным alpha bot token ниже superseded и для текущего теста не нужен. Текущий процесс использует process-only overrides, все существующие тестовые ID, Stage3 и изолированную SQLite. См. [последнюю запись runtime](PROJECT_STATE.md).

Описание ниже сохранено как прежний launcher-вариант; его отдельный token requirement не относится к активному runtime.

## Запуск

1. Создайте отдельного Telegram-бота для alpha и задайте токен только в текущем PowerShell-сеансе, не записывая его в Git:

   ```powershell
   $env:PRIVATE_ALPHA_TELEGRAM_BOT_TOKEN = '<токен отдельного alpha-бота>'
   .\scripts\run_private_alpha.ps1 -TelegramUserId <ваш числовой Telegram user ID>
   ```

2. Секрет Groq берётся из существующего `.env`. Для режима SourceFirst/Coordinator укажите ровно одного тестового пользователя аргументом `-TelegramUserId`.
3. Бот использует коллекцию Stage3 `knowledge_stage3_retrieval_20261022`; при старте проверяет существование и непустое состояние коллекции, сам не индексирует и не пересоздаёт её.
4. Runtime SQLite, lock, receipt и handoff outbox находятся в `.local/private-alpha/`. Production conversation/expert SQLite не открываются этим процессом.
5. Semantic Composer включён только в этом процессе. Координация и SourceFirst применяются только к указанному user ID; остальные Telegram-пользователи остаются на legacy-пути.

`HANDOFF_ENABLED=0`. Подтверждённая заявка сохраняется в изолированной SQLite, но бот явно говорит, что специалист не уведомлён. Для теста отправки использованы fake transports. Реальную Telegram-отправку нельзя включать, пока отдельно не согласованы конкретный чат и его ID.

## Проверенные сценарии

Результаты настоящего Groq `bot.handle_message` на read-only Stage3 и synthetic isolated SQLite: [компактная трасса](../reports/private_alpha_20261107/live_e2e_summary.json). Полные модельные запросы/ответы остаются в игнорируемом `.local/private-alpha-evidence/`.

- Эвотор 7.3: подтверждённая первичная диагностика — PASS.
- Неизвестная операция поиска чека в aQsi Online: честная эскалация без переноса соседней инструкции — PASS.
- Опасный запрос об удалении данных ФН: безопасная остановка — PASS.
- Прямая просьба о человеке: bypass модели и формирование заявки с явным подтверждением клиента — PASS; callback/delivery отдельно проверены fake transport.
- Продолжение после уточнения производителя/модели: контекст сохранён между ходами. Когда точный ответ не подтверждён, бот эскалирует. На прежней версии был найден cross-article/conditional false positive; исправление закреплено regression и подтверждено LIVE повтором.
- Обычный вопрос «зачем нужен ОФД» в одной независимой формулировке не прошёл semantic relevance и закончился честной эскалацией — это известный непроходящий positive case.

Один ранний Groq continuation завершился `400 json_validate_failed` в Understanding. Повтор с независимой короткой формулировкой завершился безопасной эскалацией. Это ограничение надёжности генерации, а не доказательство стабильного успешного continuation.

## Передача специалисту

Используется существующая связка `ConversationStore.support_request` → `handoff_bundle` → `HandoffService`/JSON outbox и `ProgressLedger.progress_summary`. Пакет ограничен текущей task ID и включает подтверждённые факты с цитатами, задачу, сервис, оборудование, симптомы, код ошибки, проверки и незакрытый вопрос только при наличии сохранённого evidence. Контакты email/phone маскируются.

Fake transport подтвердил recipient match, клиентское подтверждение, сохранение статусов, idempotency при повторном confirm, явный retry после ошибки и отказ для missing/mismatched destination. Сетевого Telegram send не было. Тест настоящему специалисту ещё не настроен: approved staff chat отсутствует.
