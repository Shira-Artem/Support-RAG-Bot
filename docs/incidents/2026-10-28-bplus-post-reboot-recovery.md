# B+ pilot recovery after host shutdown — 2026-10-28

**Status:** restored; one Telegram polling worker is running for the user's manual test. No Telegram message was sent by the agent.

## Git and local version

- Checkout remains on `main`, HEAD `525b1b38cd20e1cf907f77862f2b1d729ad7ee6e`; `origin/main` had the same SHA at recovery. No reset, checkout, pull, or overwrite was performed.
- The uncommitted Shared Scope/Subtask code, tests, replay matrix, and incident documentation from 2026-10-27 were present. Runtime source hashes matched the local checkout after restart. They are the version running and are being committed/pushed only after the user's explicit follow-up request.
- Local Python: `C:\Python314\python.exe` = 3.14.3, matching yesterday's pilot. `.venv` uses Python 3.12.2. Python 3.14 imports for Telegram 21.10, sentence-transformers 5.7.0, Qdrant client 1.19.1 and project modules succeeded. `pip check` reports one unrelated global package issue: `lab01-fsm-bt` requires missing `pygame`; it did not affect the bot. No dependencies were installed or changed.

## Recovery cause and actions

- No `bot.py` worker existed after the computer shutdown; the old PID 23004 was treated only as stale receipt data.
- Docker Desktop service was stopped, and local Qdrant port 6333 was closed. Existing container `rag-qdrant-1` and image `qdrant/qdrant:v1.15.4` were present; the container had exited with code 255 during host shutdown. Docker Desktop was started and that existing container was started without recreation or volume replacement.
- After reboot, the process-only B+ switches were absent from the shell environment. `.env` itself has Groq and Telegram credentials, but `RAG_ENGINE` defaulted to `legacy`, `AI_COORDINATOR_ENABLED` defaulted false, and its collection value pointed to `knowledge_organized_stage2_20261022`. No `.env` edits were made. The worker was launched with the previously verified process-only settings: SourceFirst + Coordinator on, `knowledge_stage3_retrieval_20261022`, demo off, Groq `openai/gpt-oss-20b`/medium, selector and handoff off. Source-first IDs were derived in memory from the existing expert allowlist; count/hash match yesterday's receipt. No IDs or secrets were printed or saved in the report.
- One initial recovery preflight aborted before process creation because its own settings check read the parent shell environment instead of the proposed child environment. That check was corrected to validate the child configuration; it caused no production or runtime change.

## Checks

- Qdrant `rag-qdrant-1`: running; Stage3 collection `knowledge_stage3_retrieval_20261022` **green / 934 points**. Other existing collections were left untouched.
- Local KB: 269 Markdown files under `data/knowledge`; application startup reports 672 legacy docs chunks. No KB content was changed.
- Production `data/conversations.sqlite3` and `data/evaluations/expert_reviews.sqlite3`: read-only `PRAGMA quick_check=ok`; zero pending rows. No SQLite writes were made.
- Read-only Stage3 E2E: **15/15 passed** using real local embeddings/retrieval and the existing deterministic planner/general-answer fixture. No provider call from E2E.
- One direct, non-Telegram Groq control request (“Что означает ОФД в контексте онлайн-кассы?”): HTTP success, model `openai/gpt-oss-20b`, 107 prompt + 126 completion = **233 tokens**, 927 ms, zero retries. No SQLite or Telegram message was involved.

## Restored worker

- Sole worker PID **39560**, executable Python 3.14.3, launched from the current checkout. Fresh runtime receipt: HEAD `525b1b38cd20e1cf907f77862f2b1d729ad7ee6e`; **33/33** source hashes match disk; Stage3/934; SourceFirst and Coordinator on; selector/handoff off; Groq model/reasoning and allowlist count/hash match yesterday.
- `Application started`; no `Conflict:`, `TelegramConflictError`, `Unauthorized`, `NetworkError`, traceback, or `ERROR -` in the new worker log. Post-start process inspection still found exactly one `bot.py` worker.
- Startup warnings: installed Qdrant Python client 1.19.1 is newer than server 1.15.4; connectivity and Stage3 reads succeeded. Hugging Face emitted its unauthenticated Hub warning while loading the cached embedding model; loading completed. Neither warning prevented startup.
- Docker Desktop auto-started other containers with their existing restart policy; they were not modified by this recovery. The recovery command explicitly started only the pre-existing Qdrant container.

**Next step:** the bot is ready for the user's manual Telegram conversations. Do not perform another architecture change or send test messages on the user's behalf. Runtime process-only B+ flags will need to be supplied again after a future host reboot; this recovery deliberately did not persist them in `.env`.
