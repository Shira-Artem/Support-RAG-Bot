# Ручной тест полного Telegram pipeline с Hubris

Инструкция для владельца стенда на Windows / PowerShell. Запускает обычный [bot.py](../bot.py) на опубликованном `e004725b3da72fcbaa356b73ef8a84ba680b8f74`: Telegram polling → `handle_message` → Hubris Understanding → SQLite/reducer → Coordinator → Stage3 → действующие Planner/Composer по необходимости → ответ, кнопки, оценки и локальная заявка. Настройки действуют только в этом процессе. Это свободный ручной тест текущего бота, с известными ограничениями [A6](../reports/exp2_natural_dialogue_20261115/a6_checkpoint.md), без кандидата, A/B, A7, Part B и Experiment 3. Исторический `run_private_alpha.ps1` выставляет Groq; здесь его не вызывать. Harness `run_telegram_equivalent_live.py` не поднимает polling.

## 1. Подготовка

- Используйте отдельный **тестовый Telegram token**, который не используется ни одним другим poller или webhook. Prod worker оставьте как есть. Работайте с ботом в личном чате тестового аккаунта, не публикуйте имя бота и не добавляйте его в группы. Allowlist `SOURCE_FIRST_TELEGRAM_IDS` выбирает тракт ответа, а не ограничивает доступ к боту: чужой ID может попасть на legacy. Если нужен закрытый доступ на уровне самого приложения, этот checkpoint такой гарантии не даёт; для такого режима запуск не подходит.
- Возьмите ключ Hubris для теста и числовой Telegram **user ID** владельца (не token и не chat ID группы). Не вставляйте секреты в командный текст, Git, отзывы или отчёты. Используйте обезличенные/синтетические обращения. Тексты и история уходят в Hubris, а локальные диагностические файлы могут содержать полное обращение и ответ. У текущего polling нет лимита расходов harness: заранее ограничьте длительность сессии и контролируйте тестовую квоту Hubris.
- Нужны существующая `.venv` проекта с зависимостями из `requirements-embeddings.txt`, локально закешированная модель `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` и **тестовый** Qdrant на `127.0.0.1:6333` с уже подготовленной Stage3 `knowledge_stage3_retrieval_20261022` (green / 934). Используется существующий отдельный тестовый индекс; SQLite будет чистая. Если по этому адресу production или общий неизвестный инстанс — не использовать его; нужен отдельный тестовый Qdrant с подтверждённым Stage3 snapshot. Сверка green / 934 — проверка доступности и ожидаемого размера, а не доказательство изоляции или идентичности содержимого. Не выполнять compose up/down, индексирование, удаление, пересоздание или подмену коллекции. Если подтверждено, что остановлен именно существующий тестовый `rag-qdrant-1`, его можно возобновить `docker start rag-qdrant-1` с тем же volume и снова сделать GET. Иначе выяснить, где тестовый snapshot, прежде чем запускать бота.

В новом **отдельном окне PowerShell** из корня основного репозитория выполните первый блок. Он делает read-only проверку Qdrant и создаёт checkout для диагностики, которую runtime пишет в собственный `.local`. Исходный checkout и его `.env` не копируются и не редактируются. При повторной сессии допускается тот же подготовленный checkout, если никто в нём уже не запускает бота и проверки ниже проходят.

```powershell
$ErrorActionPreference = 'Stop'
$repo = (Get-Location).Path
$sha = 'e004725b3da72fcbaa356b73ef8a84ba680b8f74'
$python = Join-Path $repo '.venv/Scripts/python.exe'
$test = Join-Path $repo '.local/manual-hubris-e004725'
$qdrant = 'http://127.0.0.1:6333'
$collection = 'knowledge_stage3_retrieval_20261022'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Use the project root with its prepared .venv.'
}
$index = (Invoke-RestMethod -Method Get -Uri "$qdrant/collections/$collection" -TimeoutSec 5).result
if ($index.status -ne 'green' -or $index.points_count -ne 934) {
    throw 'Expected the existing test Stage3: green, 934 points.'
}
if (-not (Test-Path -LiteralPath $test)) {
    New-Item -Type Directory -Force (Split-Path -Parent $test) | Out-Null
    git -C $repo worktree add --detach $test $sha
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the test checkout.' }
}
$testHead = git -C $test rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or "$testHead" -ne $sha) { throw 'Unexpected test SHA.' }
$trackedChanges = git -C $test status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $trackedChanges) { throw 'Test checkout has tracked changes.' }
if (Test-Path -LiteralPath (Join-Path $test '.env')) {
    throw 'Test checkout must not contain a .env file.'
}
Set-Location -LiteralPath $test
```

## 2. Настроить процесс и запустить

В том же окне, после первого блока. Ввод ключей через `Read-Host -AsSecureString` не попадает в историю команд; программе секреты передаются в окружении. Проверка перед запуском читает прежний token только для сравнения и ничего из исходного `.env` не выводит и не загружает в настройки. Новый каталог `run-*` получает две чистые SQLite, outbox и receipt. Lock один для этого checkout; он не блокирует запуск с тем же token из другого checkout или с другой машины, это проверяется владельцем.

```powershell
$run = Join-Path $test ('.local/run-' + [guid]::NewGuid().ToString('N'))
New-Item -Type Directory -Path $run | Out-Null
$userId = (Read-Host 'Telegram numeric user ID of the tester').Trim()
if ($userId -notmatch '^[1-9][0-9]{0,17}$') { throw 'Expected a numeric Telegram user ID.' }
function Read-ProcessSecret([string]$label) {
    $secure = Read-Host $label -AsSecureString
    try {
        return [System.Net.NetworkCredential]::new('', $secure).Password
    } finally {
        $secure.Dispose()
    }
}

try {
    $env:TELEGRAM_BOT_TOKEN = Read-ProcessSecret 'Dedicated test Telegram bot token'
    $env:HUBRIS_API_KEY = Read-ProcessSecret 'Hubris test API key'
    $env:LLM_PROVIDER = 'hubris'
    $env:HUBRIS_BASE_URL = 'https://api.hubris.pw/v1'
    $env:HUBRIS_MODEL = 'openai/gpt-oss-20b'
    $env:HUBRIS_REASONING_EFFORT = 'low'
    $env:RAG_ENGINE = 'source_first'
    $env:SOURCE_FIRST_TELEGRAM_IDS = $userId
    Remove-Item Env:EXPERT_TELEGRAM_IDS, Env:TELEGRAM_SPECIALIST_CHAT_ID, Env:HANDOFF_APPROVED_CHAT_ID -ErrorAction SilentlyContinue
    $env:AI_COORDINATOR_ENABLED = '1'
    $env:SEMANTIC_COMPOSER_ENABLED = '1'
    $env:SEMANTIC_EVIDENCE_SELECTOR_ENABLED = '0'
    $env:RAG_BACKEND = 'qdrant'
    $env:RAG_DEMO_MODE = '0'
    $env:SHOW_SOURCES = '1'
    $env:QDRANT_URL = $qdrant
    $env:QDRANT_COLLECTION = $collection
    $env:EMBEDDING_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    $env:HF_HUB_OFFLINE = '1'
    $env:PYTHONUTF8 = '1'
    $env:CONVERSATION_DB_PATH = Join-Path $run 'conversations.sqlite3'
    $env:EXPERT_DB_PATH = Join-Path $run 'expert_reviews.sqlite3'
    $env:HANDOFF_ENABLED = '0'
    $env:HANDOFF_STATE_PATH = Join-Path $run 'handoff_outbox.json'
    $env:BOT_RUNTIME_RECEIPT_PATH = Join-Path $run 'runtime.json'
    $env:BOT_INSTANCE_LOCK_PATH = Join-Path $test '.local/manual-hubris.lock'

    @'
import sys
from pathlib import Path
from dotenv import dotenv_values
from app.config import get_settings, should_use_ai_coordinator
from app.handoff import HandoffSettings

s = get_settings()
original_env = Path(sys.argv[1])
original_token = (dotenv_values(original_env).get("TELEGRAM_BOT_TOKEN") or "").strip() if original_env.is_file() else ""
if not s.telegram_bot_token or not s.hubris_api_key:
    raise SystemExit("Both test credentials are required.")
if s.telegram_bot_token == original_token:
    raise SystemExit("Use the dedicated test token, not the original .env token.")
if (s.llm_provider, s.hubris_model, s.hubris_reasoning_effort) != ("hubris", "openai/gpt-oss-20b", "low"):
    raise SystemExit("Unexpected Hubris settings.")
if len(s.source_first_telegram_ids) != 1 or not should_use_ai_coordinator(s, int(sys.argv[2])):
    raise SystemExit("Unexpected SourceFirst/Coordinator scope.")
if not s.semantic_composer_enabled or s.semantic_evidence_selector_enabled or HandoffSettings.from_env().ready:
    raise SystemExit("Unexpected Composer/Selector or handoff settings.")
print("Preflight OK: hubris / openai/gpt-oss-20b / low; SourceFirst + Coordinator + Composer.")
'@ | & $python -X utf8 - (Join-Path $repo '.env') $userId
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; bot was not started.' }

    Write-Host "Test data directory: $run"
    & $python -X utf8 -B (Join-Path $test 'bot.py')
    if ($LASTEXITCODE -ne 0) { throw 'Bot exited with an error. Check the local console.' }
} finally {
    Remove-Item Env:TELEGRAM_BOT_TOKEN, Env:HUBRIS_API_KEY -ErrorAction SilentlyContinue
}
```

Выключенный отдельный флаг Selector соответствует профилю A6: информационная ветка Semantic Composer при необходимости сама вызывает существующий Selector. `HANDOFF_ENABLED=0` и пустые получатели означают, что подтверждение сохраняется локально, без отправки специалисту. Основной токен, SQLite, outbox и startup receipt основного бота этим процессом не используются. Штатный runtime читает существующий Qdrant; клиент бота технически не является read-only ACL. Не администрируйте коллекцию параллельно тесту.

## 3. Проверить полный тракт и собирать отзывы

1. В Telegram отправьте `/start`, выберите **Свободный диалог**, затем **Новый диалог**. При сомнении проверьте аккаунт через `/whoami`. Не выбирайте «Экспертное тестирование»: это другой вход.
2. Сначала задайте справочный вопрос с известной approved опорой и отдельный технический вопрос про первый безопасный шаг на точной модели. Например, спросите, как найти чек в личном кабинете «Платформа ОФД», а затем в новом диалоге — что первым проверить, если продажи на Эвоторе 7.3 есть, а чеков в кабинете ОФД нет. Это контроль фактического тракта, не обещание конкретного ответа: повтор D07 исторически варьировал. Receipt подтверждает инициализацию перед polling, поэтому факт работы Telegram проверяется входящим сообщением и ответом.
3. Дальше говорите свободно: меняйте цель и тему, сообщайте результаты частями, поправляйте модель и проверяйте, не спрашивает ли бот то, что уже знает. Для разделения независимых кейсов используйте «Новый диалог»; предыдущая переписка остаётся в тестовой SQLite. Технические шаги оценивайте по применимости, не выполняя опасные действия на реальной кассе.
4. Нажимайте **👍 Помогло** или **👎 Не помогло**. После 👎 выберите **Оставить комментарий** и отправьте замечание следующим сообщением: оно сохранится без вызова модели. Удобный формат: ожидаемое продвижение → что ответил бот → что переспросил, потерял или предложил зря; укажите номер хода и источник, если виден. Тест handoff: **Позвать специалиста** → **Подтвердить**. Ожидаем: «Заявка … сохранена. Специалист не уведомлён…». Если появится обещание доставки, остановите тест и сохраните пример.

**Как подтвердить Hubris.** В `runtime.json` сверяйте `commit`, `provider=hubris`, `rag_engine=source_first`, Coordinator/Composer, `source_first_user_count=1`, `collection` и `points=934`. На этом SHA `app/bot_runtime.py` для Hubris берёт `model` из поля OpenRouter, а effort пишет null; стартовый лог повторяет эти значения. В ветках ошибок `bot.py` также возможны унаследованные ярлыки Groq/OpenRouter. Поэтому проверьте успешный ход: SQLite должен показать `source_first`, `provider=hubris`, Coordinator route и для retrieval-хода коллекцию/диагностику. В `.local/conversational-understanding.jsonl` этого checkout для успешного вызова проверьте `model`, статус, поля `request_payload.model` и `request_payload.reasoning_effort` по времени сессии. Не выводите весь trace в чат. Планирование/Composer могут не вызываться на всех ходах; отсутствие источника в одном ответе не означает, что бот использует legacy. Если нет подтверждённого модельного/retrieval хода, зафиксируйте сбой вместо подтверждения полного тракта.

Если polling сообщает `Conflict`/409 или webhook conflict, остановите только запущенный здесь тест. Проверьте выделенность тестового token и его использования; не выключайте production и не удаляйте существующие webhook без проверки. Если недоступен Qdrant/embedding, восстановите тестовый индекс или локальный cache без переиндексации. Hubris 401/403, 429, transport и semantic отказ записывайте отдельно; не запускайте автоматический цикл повторов.

## 4. Остановить и выгрузить

В том же окне нажмите **Ctrl+C** и дождитесь завершения polling. SQLite и diagnostics сохраняются. Проверьте receipt/последние статусы и выгрузите только явно указанный тестовый DB:

```powershell
$testDb = Join-Path $run 'conversations.sqlite3'
if (-not (Test-Path -LiteralPath $testDb -PathType Leaf)) { throw 'Test SQLite was not created.' }
@'
import json
import sqlite3
import sys
from pathlib import Path

with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True) as db:
    rows = db.execute(
        "SELECT id, diagnostics_json FROM messages WHERE role='assistant' "
        "AND status='complete' ORDER BY id DESC LIMIT 15"
    )
    for row_id, raw in rows:
        d = json.loads(raw or "{}")
        print(row_id, d.get("rag_engine"), d.get("provider"), d.get("model"),
              (d.get("coordinator_decision") or {}).get("route"),
              d.get("retrieval_collection"), d.get("generation_status"), d.get("scenario_reason"))
'@ | & $python -X utf8 - $testDb
if ($LASTEXITCODE -ne 0) { throw 'Could not read the test diagnostics.' }
& $python -X utf8 -m scripts.export_support_feedback --database $testDb --output-dir (Join-Path $run 'feedback')
if ($LASTEXITCODE -ne 0) { throw 'Feedback export failed.' }
```

Сохраните `runtime.json`, SQLite и feedback export локально; привязывайте реальные замечания к ID ответа и времени сессии. Экспорт включает тексты вопросов/ответов и комментарии, публиковать его целиком не нужно. После выгрузки закройте выделенное окно PowerShell, чтобы убрать process-only настройки. Для следующего прогона снова выполните шаги подготовки и запуска: они создают новый каталог базы и используют тот же тестовый checkout, старые строки диагностик отличайте по времени. Ручные отзывы — dev evidence и не входят в будущий слепой holdout.
