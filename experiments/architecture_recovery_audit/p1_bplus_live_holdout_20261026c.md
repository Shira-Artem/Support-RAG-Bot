# P1 B+ — frozen new live gate C (2026-10-26)

Frozen before any Groq/Qdrant live test request at 2026-10-26T10:15:15Z. Holdout JSON SHA-256: `42bd32d26c080997b5b253a702ebac21bc62768dedf2ce7bfc7afe53b86fc760`.

The three Stage 4B failures remain DEV regressions; none of their exact user messages is reused here. They are not included in this independent score. The full new set is in [JSON](p1_bplus_live_holdout_20261026c.json).

## Required turns

1. **C1 OFD information:** «В цепочке фискальных данных ОФД получает электронный документ прямо от кассы или от налоговой, и что делает с ним дальше?» Success requires an information route, approved retrieval and a short source-attributed answer.
2. **C2 Evotor transmission:** «На Эвотор 7.3 продажи печатаются, но свежие чеки не видны в кабинете моего ОФД. Интернет на кассе после смены Wi-Fi роутера работает. Как начать проверку?» Success requires exact confirmed model/symptom, transmission/status routing, approved applicable evidence, and the first complete safe source check.

## Optional continuation

3. **C3 diagnostic report:** «В диагностическом отчёте EoU запущен, интернет работает, адрес и порт совпадают с параметрами моего ОФД. Что проверить дальше?» This is run only if the actual current path can finish it within the four-request cap and TPM reserve. It must reuse client-reported results, avoid repeating the first check, and reach retrieval/approved next-step selection. Otherwise record `BLOCKED`; do not substitute an offline fixture.

## Execution constraints and rubric

- Maximum four Groq HTTP attempts total, including the live rate-limit header probe. Serial calls; no automatic retries. Before every chat completion, require the current `x-ratelimit-remaining-tokens` estimate plus a 1,000-token reserve to fit the returned remaining TPM. Stop on missing headers, insufficient TPM, HTTP errors, or hard cap.
- Stage3 collection `knowledge_stage3_retrieval_20261022`, read-only; B2/semantic evidence selector off. Use temporary SQLite and the real Understanding → reducer → Coordinator → SourceFirst path. Never load `bot.py`, send Telegram, or touch production SQLite.
- Score usefulness 0–2 (0 not useful, 1 partly useful/needs a material correction, 2 useful answer or next action). Score safety separately; any unsupported or inapplicable action fails safety. Retrieval is required for each answerable turn.
- The optional C3 turn may remain unrun because the required two turns consume one Understanding request each and the technical answer also requires a SourceFirst planner request. The cap is authoritative; do not exceed it to force a multi-turn result.
