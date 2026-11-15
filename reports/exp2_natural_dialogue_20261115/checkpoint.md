# Experiment 2 checkpoint — 2026-11-15

## Status

**Experiment 2 — PAUSED / PARTIAL LIVE / NOT ACCEPTED YET.** Development is stopped on the owner’s instruction. Current `main` checkpoint: `ddedc9527d03d0536d7b5e959c5994449bdd11ba`. Runtime code checkpoint: `1cb0aadc76a52e12cedda8708327ebd2614c5e38`; subsequent commits are documentation only. `origin/main` matched local HEAD when checkpointed. Tracked working tree is clean. The pre-existing untracked `.worktrees/` directory is preserved and was not read, changed, or deleted.

## Experiment setup

- Baseline: `a006ea65e835e070f183ac25ccd39305c1a0e79d`, the integrated Experiment 1 main baseline. Its tree includes Experiment 1 merge `12a0a9d` and the Exp1 source commit `36c24a4` in history.
- First candidate A1: `7cb82ed92ebff8dacf9bbb1beecaafade62cb02c`; full-pipeline paired with baseline on five frozen cases, 13 turns each.
- Candidate A2: `7d7ad8505120f59e7c728716a5d4b012149c8112`; candidate-only 13-turn follow-up, not a fresh paired baseline.
- D07 candidates: A3 `cb974bce5e6ca914425eb473ea396add8ba072a0` and A3b `6728d57c3e50a49f8bf9659387bccd58ed6e9462`.
- Current offline candidates: D03 follow-up in `4902706ca31c6dda1dc9eb8163cc186687059f5d`; D01 partial-network acknowledgement in `1cb0aadc76a52e12cedda8708327ebd2614c5e38`.
- Full pipeline: `bot.handle_message`, real Groq `openai/gpt-oss-20b`, reasoning effort `medium`, read-only Stage3 Qdrant collection `knowledge_stage3_retrieval_20261022` (green, 934 points at the recorded checks), per-run isolated SQLite, synthetic bounded dialogues. No Telegram traffic, Qdrant mutation, approved-KB change, provider/model/config change, or production rollout.
- Full-pipeline JSON, HTTP traces, Understanding traces, and SQLite files remain local under ignored `.local/`. No trace/SQLite artifact was staged or published. Retry3’s interrupted local run folder is also preserved; it contains SQLite files but no result JSON/HTTP trace.

## What Part A implemented

1. **A1 — search readiness:** Coordinator permits evidence retrieval for reducer-owned semantic task/symptom plus confirmed subject, even when the symptom is too short for the old lexical threshold. Source applicability and safety remain later gates.
2. **A2 — useful scope questions:** asks bounded questions for typed searches missing scope and for document searches missing document type; retains the legacy receipt/date fallback.
3. **A3 — transmission task family:** recognizes colloquial `не уходят` with receipt/document wording as transmission failure; explicit fiscal-error classification retains precedence.
4. **A3b — cross-phrase source match:** recognizes the shared receipt/document object and failed-delivery predicate so “не уходят чеки” can match approved “неотправленные документы” guidance. Existing category, scope, operation and safety gates remain.
5. **A4 — unknown-code continuation (offline only):** when a device symptom is present, code is unconfirmed, and Planner cannot choose a safe source, asks a focused observable-result question rather than immediately escalating. Repeated unknown-code clarification changes its wording; it never attributes a source’s error code to the customer.
6. **A5 — partial network result (offline only):** prevents generic network wording such as “интернет касса” from being treated as an exact equipment model. Model clarification acknowledges the reported internet access while leaving the compound ProgressLedger check `asked`.

**Part B was not implemented or separately evaluated.** The D07 live response did return one existing approved first diagnostic step after A3b selected its exact source; this single output is not a Part B acceptance result.

## Observed behavior by frozen case

| Case | Real live evidence | Offline-only/current unresolved |
|---|---|---|
| **D01 — internet works** | Baseline/A1/A2 presented the approved composite model + paid-period check. Ledger did not falsely mark the whole check complete. A1/A2 did not acknowledge the separate “internet works” fact; later turns escalated or failed scope matching. | A5 now rejects “интернет касса” as a model and acknowledges the network result while preserving ledger `asked`. Full-pipeline live validation was blocked. |
| **D03 — unknown error code** | Baseline did not progress the task. A1/A2 avoided attributing FN 231/-3975, but repeated the same question; A2 escalated on T03 after the user supplied model/intermittency and Planner could not safely select a source. | A4 focused follow-up and repeat-suppression regressions pass offline. The A4/A5 candidate has no live D03 result. |
| **D05 — old aQsi sale** | A1 did not ask a useful scope question. A2 asked whether the user needed one sale or a period summary, plus the date. The repeated request still fell back to the missing approved-source path; no UI controls were invented. | Full A3b/A4/A5 continuation never reached D05. |
| **D07 — receipts not transmitted** | Baseline/A1/A2 returned an unrelated time-mismatch/FN 235 procedure. A3 corrected task-family classification but selected a broader OFD article. A3b live selected the exact approved Evotor 7.3 source and returned its first read-only diagnostic-report step. | This is a one-turn slice only. It does not establish complete multi-turn quality or acceptance of Part B. |
| **D08 — Diadok to 1C** | A1 did not resolve the evidence gap. A2 asked what document was expected; after “it displays in Diadok,” the later turn selected an approved 1C-EPD/EDO distinction, but did not solve visibility in 1C. | No A3b/A4/A5 live rerun reached D08. |

The A1/A2 paired run improved selected clarifications but did not establish an accepted Experiment 2 result. A2 was a follow-up candidate run, not a newly paired A/B. A1 candidate D03 end-to-end latency summed to 47.825s in its scenario; the traces show individual Understanding requests around 1.4–2.7s and no 429 in that run. The evidence suggests local token pacing contributed to the delay, but exact wait time per request was not recorded, so that cause remains an inference.

## Verification

- Full UTF-8 pytest on the current runtime code checkpoint: **878 passed, 4 historical xfailed** in 245.51s. It ran at `980f9c1611e3ca8ec97739000e6ca922c3c4b209`; later commits through checkpoint HEAD were docs-only.
- Focused affected suites after A5: **119 passed, 4 historical xfailed** (`test_source_first_dialogue_contract.py`, `test_ai_coordinator.py`, `test_retrieval_pipeline.py`, `test_metadata_retrieval_routing_v3.py`, `test_telegram_pilot_sqlite_replay.py`). No final failing tests.
- Earlier offline checks: A1 59 passed; A2 62 passed and a wider 131 passed / 4 xfailed; A3 six suites 121 passed; A3b retrieval/routing 60 passed.
- One newly authored fixture test initially failed because synthetic source metadata did not match the approved local source; the fixture was corrected and the final focused/full suites passed. This was a test-fixture issue, not a product regression.
- SQLite was isolated per run and multi-turn state was saved. The JSON artifacts do not record an explicit close/reopen equality assertion for these Experiment 2 live runs. A deterministic SQLite reopen check remains required before acceptance.

## Recorded Groq usage and interruptions

Aggregation over the preserved Experiment 2 HTTP-trace JSON files, including baseline, candidate runs and interrupted quota-limited attempts:

| Recorded outcome | Count |
|---|---:|
| HTTP 200 | 67 |
| HTTP 400 (`json_validate_failed`, recovered in baseline) | 1 |
| HTTP 429 (TPD) | 4 |
| `ConnectTimeout` with no HTTP status | 1 |
| **Recorded HTTP/API attempts** | **73** |
| Reported token usage from responses with usage fields | **188,187 tokens** |

Failed 429/timeout requests did not provide token usage; this sum is reported accepted usage, not provider billing. Baseline A: 49,727 tokens, 18×200 + 1×400, 75.591s summed turn latency. Candidate A1: 56,294 tokens, 19×200, 112.047s. A2: 53,944 tokens, 19×200, 110.927s. A3 D07: 5,505 tokens, 2×200, 9.351s. A3b D07: 5,708 tokens, 2×200, 9.657s. The remaining traces account for the other 4×429 attempts and one Planner timeout. After the provider retry estimates, bounded attempts continued to fail at D01 T01/T02 due TPD 429; one later Planner request timed out. The harness saved each completed partial result and stopped on provider/runtime error.

A live command was in progress when the owner’s STOP instruction arrived. It was interrupted immediately while local model weights were loading. No retry3 JSON/HTTP trace was created; an isolated SQLite directory remains preserved. Because that interrupted process has no HTTP artifact, its provider-side request status is unknown and it is excluded from the 73 recorded attempts above.

## Remaining work

### To complete Part A

- After a replacement/available LLM provider can support a complete turn, run the same frozen D01/D03/D05/D07/D08 candidate suite from runtime `1cb0aadc76a52e12cedda8708327ebd2614c5e38` with the fixed baseline `a006ea65e835e070f183ac25ccd39305c1a0e79d`; use equal configuration, separate SQLite, and explicit close/reopen equality checks.
- Capture final answers, source/section, task continuity, ledger states, provider attempts, reported tokens, and latency; stop on errors. Verify D03/D04 Experiment 1 negatives and unsafe requests.
- Decide from the paired evidence whether A1–A5 should be accepted experimentally, revised, or reverted. Experiment 2 is not accepted yet and is not production GO.

### Part B — not started

Only after Part A is reviewed and accepted, separately evaluate one independent read-only step from an applicable approved source. Preserve model applicability, confirmed facts, prerequisites, source integrity and all existing unsafe-operation gates. Do not permit fiscal clock changes, archive closure or fiscal-drive replacement based on Planner language alone. Compare with Part A so the contribution of B is measurable.

After Part A and B, continue the approved sequence to Experiment 3 and the common Quality Gate only by owner decision. No Hubris integration, Part B, Experiment 3, merge/rebase/branch creation, or production rollout was started as part of this checkpoint.

## Recovery pointer

Start from clean tracked `main` at **`ddedc9527d03d0536d7b5e959c5994449bdd11ba`**. The runtime candidate is at **`1cb0aadc76a52e12cedda8708327ebd2614c5e38`**. Keep the existing ignored `.local` artifacts and `.worktrees/` directory. The next action after LLM-provider recovery is a controlled full-pipeline A/B of D01/D03/D05/D07/D08 with SQLite reopen verification—not Part B.
