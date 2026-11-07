param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 9223372036854775807)]
    [long]$TelegramUserId
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$alphaToken = $env:PRIVATE_ALPHA_TELEGRAM_BOT_TOKEN
if ([string]::IsNullOrWhiteSpace($alphaToken)) {
    throw 'Set PRIVATE_ALPHA_TELEGRAM_BOT_TOKEN to a dedicated private-alpha bot token before launch.'
}

$envPath = Join-Path $repo '.env'
$primaryToken = $null
if (Test-Path -LiteralPath $envPath) {
    foreach ($line in [System.IO.File]::ReadLines($envPath)) {
        if ($line -match '^\s*TELEGRAM_BOT_TOKEN\s*=\s*(.*)\s*$') {
            $primaryToken = $Matches[1].Trim().Trim('"').Trim("'")
            break
        }
    }
}
if ($primaryToken -and $primaryToken -ceq $alphaToken) {
    throw 'The private-alpha token must belong to a separate test bot, not the bot configured in .env.'
}

$runtime = Join-Path $repo '.local/private-alpha'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$env:TELEGRAM_BOT_TOKEN = $alphaToken
$env:LLM_PROVIDER = 'groq'
$env:RAG_ENGINE = 'source_first'
$env:SOURCE_FIRST_TELEGRAM_IDS = [string]$TelegramUserId
$env:EXPERT_TELEGRAM_IDS = ''
$env:AI_COORDINATOR_ENABLED = '1'
$env:SEMANTIC_COMPOSER_ENABLED = '1'
$env:SEMANTIC_EVIDENCE_SELECTOR_ENABLED = '0'
$env:RAG_BACKEND = 'qdrant'
$env:RAG_DEMO_MODE = '0'
$env:QDRANT_URL = if ($env:QDRANT_URL) { $env:QDRANT_URL } else { 'http://127.0.0.1:6333' }
$env:QDRANT_COLLECTION = 'knowledge_stage3_retrieval_20261022'
$env:CONVERSATION_DB_PATH = Join-Path $runtime 'conversations.sqlite3'
$env:EXPERT_DB_PATH = Join-Path $runtime 'expert_reviews.sqlite3'
$env:HANDOFF_ENABLED = '0'
$env:HANDOFF_STATE_PATH = Join-Path $runtime 'handoff_outbox.json'
$env:TELEGRAM_SPECIALIST_CHAT_ID = ''
$env:HANDOFF_APPROVED_CHAT_ID = ''
$env:BOT_RUNTIME_RECEIPT_PATH = Join-Path $runtime 'runtime.json'
$env:BOT_INSTANCE_LOCK_PATH = Join-Path $runtime 'bot.lock'
$env:HF_HUB_OFFLINE = '1'

$python = Join-Path $repo '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Project virtual environment is missing at .venv/Scripts/python.exe.'
}
Write-Host 'Starting isolated Private Alpha: SourceFirst + Coordinator + Semantic Composer; Stage3 read-only; handoff send disabled.'
Write-Host 'Only the supplied Telegram user ID is routed through SourceFirst. Runtime SQLite and outbox are under .local/private-alpha.'
& $python (Join-Path $repo 'bot.py')
exit $LASTEXITCODE
