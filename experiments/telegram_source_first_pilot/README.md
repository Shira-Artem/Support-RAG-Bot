# Isolated Source-first Telegram pilot

Status: prepared and locally smoke-tested; **not running**. This is a bounded interactive experiment authorized on 2026-10-25. It does not promote V1.2-B to a release gate, start V1.2-C, or modify production runtime.

## Isolation and safety boundaries

- Requires `PILOT_TELEGRAM_BOT_TOKEN`; the production `TELEGRAM_BOT_TOKEN` is never read. Create a different bot in `@BotFather`. Never run two polling workers with the pilot token.
- Requires a numeric `PILOT_TELEGRAM_USER_IDS` allowlist. `/id` returns the caller's Telegram ID so the operator can obtain it; all dialogue actions are allowlisted.
- Requires a separate `PILOT_GROQ_API_KEY`; no production Groq key fallback is used. The configured model is `openai/gpt-oss-20b`.
- Reads optional pilot-only settings from `experiments/telegram_source_first_pilot/.env.pilot`; it never reads the repository `.env`.
- Uses the verified read-only collection `knowledge_stage3_retrieval_20261022` at `http://127.0.0.1:6333`. The retrieval client verifies the expected inventory, and its code path performs searches/counts/scrolls only. It does not create, index, update, or delete points. Pilot startup stops if the endpoint differs.
- Conversation messages, traces, and the test specialist queue live in `experiments/telegram_source_first_pilot/data/pilot.sqlite3` and `traces/`. They do not use `data/conversations.sqlite3`, `ExpertStore`, or the production bot.
- Responses contain whole exact approved source sections, preserving source wording, conditions, warnings, and order. The local SHA, approval status, service/model applicability and high-risk stop gate are checked before rendering. If applicability cannot be established, the system escalates. One clarification at most is allowed in a conversation; a repeat or model/Qdrant failure escalates without invented troubleshooting.
- “Позвать специалиста” and automatic escalation create a local test-queue item only. No employee is contacted.
- Export is a separate operator command. It omits Telegram IDs and exact timestamps, and masks email addresses, phone-like strings, and long numeric identifiers. Review the exported text before sharing; regular expressions cannot identify every personal detail.

## Local checks (no network calls)

From the repository root, in PowerShell:

```powershell
python -m experiments.telegram_source_first_pilot.pilot preflight
python -m experiments.telegram_source_first_pilot.pilot smoke
```

`preflight` records the current commit and SHA-256 hashes, model, collection, worker state, and missing pilot configuration; it does not contact Qdrant, Telegram, or Groq. `smoke` checks local approved-document indexing/section parsing, the high-risk stop gate, PII masking, and a temporary isolated SQLite conversation/queue. It makes zero network or LLM calls.

Optional read-only inventory check before launch:

```powershell
python -m experiments.telegram_source_first_pilot.pilot preflight-qdrant
```

It connects only to the pinned local Qdrant endpoint, verifies the collection inventory and embedding dimension expected by the already tested retriever, and makes no search, write, Telegram, or LLM calls. Run it only while the local Qdrant service is available.

## Manual launch on Windows

1. Create a new Telegram bot in `@BotFather`; keep its token separate from the production token.
2. Obtain a dedicated Groq key for the pilot. Do not reuse or paste either key into chat.
3. In PowerShell, from the repo root, enter the pilot token without echo, start the temporary ID-only polling mode, send `/id` to the bot, then stop it with Ctrl+C:

```powershell
$token = Read-Host "Pilot Telegram token" -AsSecureString
$env:PILOT_TELEGRAM_BOT_TOKEN = [Net.NetworkCredential]::new("", $token).Password
python -m experiments.telegram_source_first_pilot.pilot identify
```

The `identify` process handles only `/id`; it does not require an allowlist, open Qdrant, or call Groq. Stop it before proceeding. Then set your returned numeric ID and a dedicated Groq key and run the read-only preflight and pilot:

```powershell
$groq = Read-Host "Pilot Groq API key" -AsSecureString
$env:PILOT_GROQ_API_KEY = [Net.NetworkCredential]::new("", $groq).Password
$env:PILOT_TELEGRAM_USER_IDS = "YOUR_NUMERIC_TELEGRAM_USER_ID"
python -m experiments.telegram_source_first_pilot.pilot preflight
python -m experiments.telegram_source_first_pilot.pilot preflight-qdrant
python -m experiments.telegram_source_first_pilot.pilot
```

Use an environment with `requirements.txt` and `requirements-embeddings.txt` installed, and with the already configured local Qdrant service available. The first startup may download/load the existing embedding model. Startup writes `preflight-receipt.json` with the code hashes and actual Qdrant inventory before polling. The user ID is not written in the preflight receipt.

If dependencies are not installed in that Python environment, install them from the repository root with `python -m pip install -r requirements.txt -r requirements-embeddings.txt`.

## Manual launch on WSL

Use the same repository from WSL and ensure the dependencies and read-only Qdrant endpoint are reachable. First set the dedicated bot token and start the ID-only worker, send `/id`, then stop it with Ctrl+C:

```bash
read -rsp 'Pilot Telegram token: ' PILOT_TELEGRAM_BOT_TOKEN; export PILOT_TELEGRAM_BOT_TOKEN; echo
python -m experiments.telegram_source_first_pilot.pilot identify
```

After stopping that worker, set the dedicated Groq key and allowlist, run both preflights, then launch the pilot:

```bash
read -rsp 'Pilot Groq API key: ' PILOT_GROQ_API_KEY; export PILOT_GROQ_API_KEY; echo
export PILOT_TELEGRAM_USER_IDS='YOUR_NUMERIC_TELEGRAM_USER_ID'
python -m experiments.telegram_source_first_pilot.pilot preflight
python -m experiments.telegram_source_first_pilot.pilot preflight-qdrant
python -m experiments.telegram_source_first_pilot.pilot
```

Never start the same token from Windows and WSL at the same time. Stop with Ctrl+C.

## Dialogue, queue, traces, export

- `/start` or `Новый диалог` creates an independent conversation; free-form text is accepted after that.
- Each turn records the messages, active user task, retrieval trace and candidate rejection reasons, whole source sections, proposal, applicability/safety result, final answer or escalation reason, elapsed times, token usage when returned, and errors. Full turn traces are private local files under `traces/<conversation-id>/`.
- The inline specialist button writes a test queue item with status `open`; automatic escalation also records an item. Nothing is delivered outside this workspace.
- Export anonymized JSONL after stopping the bot:

```powershell
python -m experiments.telegram_source_first_pilot.pilot export
```

An explicit output path can be supplied as the second argument. Manually inspect and redact the export before sending it anywhere.

## Stop and cleanup

Press Ctrl+C in the terminal running the pilot. A token-specific OS lock in the pilot data directory rejects a second worker in the same shared workspace. Confirm no second process uses the pilot token, including on another machine or workspace. The pilot has no background service or restart registration. Local records remain for analysis. Deleting them is a separate operator action; never point cleanup at the production conversation database.

## Current preflight receipt

See [`preflight-report.md`](preflight-report.md). It confirms only local preflight/smoke; the Qdrant inventory check, Telegram token validation, and any live LLM call remain unrun until the user starts the isolated pilot.
