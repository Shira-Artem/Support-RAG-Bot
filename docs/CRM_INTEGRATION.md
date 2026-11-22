# CRM + Smart Navigation v4 + Support RAG

## Актуальный UX: естественное общение, 21.11.2026

Этот раздел заменяет прежние рекомендации обязательного «Вернуться к ИИ» и
открытия Mini App перед обычным вопросом. Клиент сразу пишет в бот; короткий ответ
приходит текстом. «Не помогло» продолжает диагностику. Явный запрос специалиста
и подтверждённая необходимость сохраняют handoff; принятого человека автоматический
ответ не перебивает. Новый объяснительный вопрос после handoff отделяется внутри,
без ручного создания вопроса. API/генерация failure не запирает консультацию.
Служебные номера/режимы/ИИ/пилот скрыты из обычных controls. Mini App — доступная
из меню переписка с общей историей. Явный вход /chat использует force_new, а не
редактирование старой карточки выше ленты; финальный visual replay этой правки
ещё нужен. Legacy resume endpoint сохранён для совместимости, не для основного UX.

153 full MySQL PASS;426 units PASS и2 прежних Windows errors; Telegram A/B
answered/sent8.999s/7.997s. Прод остаётся не принят: свежий полный TG↔Mini App,
HTTPS/телефон, MAX/staff и фактическое качество ещё требуют проверки.

[Полный отчёт](../reports/crm_natural_chat_20261121/report.md).

Локальный пилот, 20.11.2026. Production NO-GO сохраняется: интеграционный
транспорт проверен, общая полезность/фактология прежнего RAG ещё не принята.
Полный [отчёт с отрицательными результатами](../reports/crm_integration_20261120/report.md),
[дословные ответы](../reports/crm_integration_20261120/answers.md).

## Архитектура и границы

Telegram/MAX CRM → существующий Smart Navigation v4 → support_v2 MySQL attempt
→ authenticated RAG API → общий `support_turn` → Understanding/DialogueState/
TaskFrame/Coordinator → approved Qdrant/SourceFirst/Composer/Grounding →
RAG receipt → CRM native assistant message + delivery outbox → клиент.

CRM владеет каталогом, корзиной, заказами и очередью специалистов. RAG не имеет
доступа к платёжным/заказным методам. Флаг `SUPPORT_RAG_ENABLED=0` по умолчанию;
включение выбирает полный RAG adapter вместо старого local-KB AIWorker gate.
Нет второго магазина, маршрутизатора или отдельной копии RAG. В пилоте
`RAG_PILOT_MODE=1` дополнительно ограничивает доступ прежними тестерами и
блокирует checkout. Production defaults от этого режима не меняются.

## Контракт

Все service endpoints требуют `Authorization: Bearer <RAG_SERVICE_TOKEN>`
(не менее 32 символов; одинаковый private key в CRM `SUPPORT_RAG_TOKEN`).

`POST /v1/support/reply`:

```json
{
  "contract_version": "1",
  "ticket_id": "installation:case:123",
  "message_id": "message:456",
  "text": "Исходный вопрос клиента",
  "expected_revision": 0,
  "context": {
    "channel": "telegram",
    "route": "technical_support",
    "router_version": "smart-navigation-v4"
  }
}
```

Response: version, ticket/message/reply IDs, incremented revision, `answer`,
`status=answered|clarify|escalate|error`, confirmed document `sources`, nullable
`escalation_reason`, bounded diagnostics. HTTP200 is an envelope, not proof of
quality or successful generation: always inspect `status`. Ordinary model-only
conversation legitimately has empty sources. Sources are final approved cited
documents, deduplicated; raw retrieval candidates are not confirmations.

`GET /v1/support/state/{ticket}` returns revision; full state is never supplied
by CRM or exposed as a client-editable blob. It persists in existing SQLite
ConversationStore. CRM namespace must be stable and unique for its database:
never reuse a namespace when replacing a DB with reset case IDs.

Same ticket/message/text/context replays the same immutable response, even
after restart. A changed payload returns409. Expected revision is checked for
new inputs; an old retry is recognized before that check. Concurrent requests,
unacknowledged previous replies and stale revisions return409. A crash after
paid generation but before receipt is an explicit interrupted error, not an
implicit regeneration. State/user events remain durable.

After durable native CRM publication, CRM calls
`POST /v1/support/ack/{ticket}` with `{"reply_id":"...","accepted":true}`.
It completes the assistant event and memory snapshot atomically. A stale,
unpublished answer is acknowledged with `accepted=false`; it cannot become a
shown check. Acceptance means publication to CRM history/outbox, not proof that
Telegram has delivered it. The native delivery receipt separately records sent,
cancelled or uncertain. Ambiguous Telegram delivery is not blindly repeated.

CRM migration0008 stores each exact API input/result/ack. Case revision and
attempt lease are checked again under the chat lock before message publication.
Timeout: API90s, client95s, native attempt lease120s. Unavailable calls are bounded
and replay the same durable key; final failure routes the case to its native
queue. Files go to a human. Recovery must use one API process with the same state
volume. No multi-host SQLite or horizontal scaling is claimed.

Emails, obvious long personal numbers and recognizable credentials in free text
are masked before Understanding/LLM and RAG persistence. CRM IDs/profile fields
are not model context. This is not universal free-text PII detection. Private raw
traces/state stay ignored; API access logging is disabled. No real client data
was used by the synthetic integration series.

## Текущая установка

- RAG checkout: `C:/Users/Shira/.codex/worktrees/crm-rag-api/Rag`.
- CRM checkout: `C:/Users/Shira/Documents/ChatGPT/CRM_AI/crm-rag-integration`.
- API: `http://127.0.0.1:8091`; `/healthz` is liveness, authenticated `/readyz`
  verifies configuration, SQLite and the nonempty green reviewed index.
- CRM support: `http://127.0.0.1:8092`, native `/support` WebApp.
- Existing `rag-qdrant-1`: reviewed B2, green/833, exact full payload comparison.
- `crm-rag-mysql`: new isolated Docker MySQL on127.0.0.1:3307. Runtime schema
  `crm_rag_demo`; CI schema `crm_rag_ci`. Bootstrap failure schemas retained.
- API state: RAG `.local/crm-state.sqlite3`. Original48-message RAG SQLite and
  expert SQLite preserved and backed up under `.local/legacy-backup`.
  Legacy history is archived, not silently assigned to new CRM case IDs.
- Per owner's later explicit instruction, the same previous RAG Telegram token
  is read from its original `.env` directly into process environment. The old
  poller3232/13568 was stopped with zero pending turns before CRM polling.
  No token was copied into Git, command arguments or a new config file.
- Native Telegram pilot uses existing private tester allowlist. Synthetic local
  equipment is clearly labelled, price1; checkout is blocked. `/start` shows the
  pilot menu without inventing registration/consent records. Local HTTP WebApp
  URLs are omitted from mobile buttons; full answers still arrive natively.

## Запуск подготовленного стенда одной командой

Из RAG integration checkout в PowerShell:

```powershell
./scripts/start_crm_integration.ps1 -Pilot -CrmRoot 'C:/Users/Shira/Documents/ChatGPT/CRM_AI/crm-rag-integration' -RagPython 'C:/Users/Shira/Documents/ChatGPT/Rag/.venv/Scripts/python.exe' -RagEnvFile 'C:/Users/Shira/Documents/ChatGPT/Rag/.env'
```

Скрипт использует подготовленные private `.local/integration.env` и CRM
`.local/crm.env`, возобновляет подготовленные MySQL и прежний Qdrant, поднимает API/CRM и один pilot
poller. Старый RAG poller должен быть остановлен. Existing unrelated listeners
не завершаются. После запуска проверить health/logs; сами secret values не
выводить. Telegram: тот же бот → `/start` → свободный текст, `/shop`, `/chat`.
Старые кнопки прежнего RAG меню к CRM не относятся; откройте `/start` заново.

Для локального браузера обновить одночасовую ссылку:

```powershell
& 'C:/Users/Shira/Documents/ChatGPT/CRM_AI/crm-rag-integration/.venv/Scripts/python.exe' -X utf8 'C:/Users/Shira/Documents/ChatGPT/CRM_AI/crm-rag-integration/tools/create_rag_demo.py' --env-file 'C:/Users/Shira/Documents/ChatGPT/CRM_AI/crm-rag-integration/.local/crm.env'
```

Ссылка с локальным bearer credential находится в CRM `.local/manual-url.txt`;
не публиковать её. Это отдельный synthetic account, не аккаунт владельца.

## Production preparation / fresh installation

Separate API process/container; CRM remains the entry point. See
`support-api.env.example`, CRM `rag.env.example`, `Dockerfile.support` and
`compose.integration.yml`. Private env files must be outside build contexts.
Compose publishes only loopback CRM8092; Qdrant/MySQL/API have no published
ports. Backend network is internal; API/CRM have separate outbound connectivity
for Hubris/platform APIs. Persistent state, DB, files and embedding cache volumes,
health checks and restart policies are configured. Existing reviewed Qdrant
volume is explicitly required; there is no auto-reindex/create fallback.
Use a source-matched restored snapshot on the destination host. Never attach a
volume already being written by another running Qdrant process to a second one.

Configure `CRM_SOURCE_DIR`, `RAG_ENV_FILE`, `CRM_ENV_FILE`, `MYSQL_ENV_FILE`,
`QDRANT_VOLUME_NAME` in a private Compose env, then
`docker compose --env-file <private-compose-env> -f compose.integration.yml up -d --build`.
Deploy the native CRM schema/support migrations0001..0007 and explicit
`tools/apply_rag_schema.py --env-file <private-db-env>` before enabling the AI.
The local schema importer requires UTF-8 (`python -X utf8`) and an empty isolated
schema; do not point it at production. On the new local MySQL, trigger creation
required `log_bin_trust_function_creators=1`. Production migration privileges and
backup policy must be configured separately. Compose syntax is checked; the
GPU/CPU Docker image build and remote server rollout are not claimed as tested.

Rollback: set `SUPPORT_RAG_ENABLED=0` for the existing native CRM behavior. For
the same Telegram token, stop the CRM pilot first, preserve MySQL/API volumes,
then start the original `.local/kb-authoritative/start_bot.py` from the original
RAG checkout using its existing Python/profile. Never run both polling loops.
The original main app/env/SQLite are retained, so rollback does not need checkout
rewrites, index changes, force pushes or data deletion.

## Ручная матрица (14 сообщений)

| Сообщение | Что проверить |
|---|---|
| `/start` | Новый CRM pilot menu |
| Хочу купить ОФД | Штатная витрина, без автоматической покупки |
| Покажи кассы Эвотор | Каталог/тестовая карточка |
| Что такое ОФД? | Свободный ответ через support_v2 |
| А чем он отличается от ФН? | Продолжение; известный quality defect может воспроизвестись |
| Эвотор не отправляет чеки | RAG support, не товарный поиск |
| У меня Эвотор 7.3 | Сохранение модели в том же кейсе |
| Интернет работает, подписка ОФД активна, очередь не уменьшается | Сохранение результатов; оценить полезность следующего шага |
| Купил ОФД, код не работает | Поддержка покупки, не новая покупка |
| Спасибо, теперь хочу купить ФН | Выход из active support в магазин, кейс не удаляется |
| `/chat` | Возврат/выбор предыдущего обращения |
| Нужен специалист | Native support_v2 queue, без LLM/новой дублирующей заявки |
| Как закрыть архив ФН? | Безопасный отказ от инструкции и очередь |
| Где в Платформе ОФД найти чек по номеру ФД? | Approved KB либо содержательное уточнение |

Повторите одно сообщение с тем же native event только через harness, не через
новую ручную отправку: новая отправка имеет новый message ID и законно считается
новым ходом. Specialist queue проверена; реальный приём/уведомление сотруднику
и end-to-end MAX delivery пока не подтверждены.

## 20.11 — локальный интерфейс и заглушка специалиста

По уточнению владельца используется готовый native support_chat UI, без нового
интерфейса/второй системы обращений. Локальный /chat даёт обычную loopback ссылку
на тот же client account; Telegram Desktop на этом ПК открывает её в браузере.
HTTPS WebApp сохраняется для настоящего deployment. Пилотные controls включены
только с isolated crm_rag_demo. Новые состояния/названия/прокрутка и AI/client
operator stubs описаны в reports/crm_manual_20261120/local_pilot.md; real operator
notifications и звонки в этом режиме отключены. После передачи можно явно нажать «Вернуться к ИИ» в том же вопросе.
Старые queued сообщения автоматически не проигрываются; напишите следующий ход. Telegram owner replay новых кнопок/cleanup ещё
нужен; общий quality gate не объявлен пройденным.


## 21.11 — один бот, возврат к ИИ и актуальный личный тест

Текущий приоритет — подключение/меню/чат/native ответы/Mini App, без расширения
CRM и без улучшения модели/KB. После тестового handoff queue приостанавливает
ИИ; теперь «Вернуться к ИИ» доступно в том же unclaimed case. Настоящий human
этой кнопкой не прерывается. Отображение состояний опирается на actual attempts;
native не перепечатывает историю и не удаляет реплики разговора. Ошибка API
публикует одну status notification через существующий durable outbox.

137 MySQL +2 long/socket timeout PASS;422 units/2 прежних Windows failures.
LIVE Mini App→RAG4.837s/accepted,18/18messages. Native synthetic TGdelivery
cancelled из-за fake ID; свежий owner парный Telegram/MiniApp replay ещё нужен.
Полный длинный native ответ частями не реализован; весь текст доступен в feed.
Общий production gate не объявлен пройденным; commit/push нет.

[Полный отчёт, runtime, state table и пошаговый личный тест](../reports/crm_hybrid_20261121/report.md).
