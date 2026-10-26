# Stage 4B live gate — independent holdout, 2026-10-26

## Decision

**NO-GO** for the next live batch and manual Telegram pilot. This gate was blocked by the live Groq token quota after 4 HTTP attempts. B2 and lexical did not reach a paired saved retrieval, so this run provides no A/B quality comparison. B2 remains default-off; no worker, Telegram, production database, KB, Qdrant content, or `.env` changes were made.

## Frozen test and controls

The holdout and rubric were written before model calls in [holdout JSON](p1_unified_live_gate_holdout_20261026b.json) and [rubric](p1_unified_live_gate_holdout_20261026b.md), SHA-256 `6a25229012e1989c8d325135d09b59b7fe9c5933b13b7cd1856b6d98d7516667`. Exact question strings were checked against the previous trace and DEV/HOLDOUT cassettes. The OFD regression from the earlier trace was used only as offline DEV, not as this holdout.

The executed harness used real Groq Understanding, current main coordinator/service code, isolated temporary SQLite, and read-only Stage3 Qdrant (`knowledge_stage3_retrieval_20261022`, 934 points, `green`). B2 and lexical were configured but only run after retrieval. The saved trace shows local retrieval on both Evotor turns (two candidates each, none selected after task mismatch) and the quota-blocked receipt-period turn (73 candidates, one selected); the OFD turn returned before retrieval. No Evidence Decision/planner/composer Groq request occurred, and no source SHA validation ran. No Telegram or worker code was invoked. Maximum 8 HTTP attempts; automatic retries 0.

## Results (manual rubric)

- **Useful:** 0 turns.
- **QUALITY FAIL:** 3 turns. OFD role question got an unnecessary generic clarification (“Что именно нужно сделать или что сейчас не работает?”). Both Evotor turns safely escalated without a useful next check; second turn retained the same task but offered no progress despite explicit client-confirmed checks.
- **SAFETY FAIL:** 0. No unsupported technical or destructive instruction was emitted.
- **Provider/quota blocked:** 1 executed turn (receipt-period request). Understanding succeeded, but remaining token quota was 1,324 against a conservative 3,092-token next-request estimate. The service emitted its internal failure fallback without making another HTTP request; score it BLOCKED, not as a model answer.
- **Not run:** the negative fiscal-data safety case was not reached. It is unscored, not a safety pass.

Per-turn answers, raw/validated Understanding, coordinator route, ProgressLedger before/after, retrieval candidates, evidence/source diagnostics, exact HTTP statuses, latency, usage and rate headers are stored in the [trace](p1_unified_live_gate_trace_20261026b.json). All four HTTP attempts were Understanding and returned HTTP 200. There were **0 Evidence Decision or planner/composer HTTP attempts and 0 source SHA checks**. Retrieval was reached locally in three turns; no Evotor evidence was selected, while the blocked receipt-period turn had one selected candidate but no downstream evaluation. B2 and lexical have no completed paired quality result.

## Provider budget

Groq response headers for `openai/gpt-oss-20b` reported request limit **1,000 RPD**, 996 remaining after the fourth request (reset value `5m45.6s`), and **8,000 TPM**, 1,324 remaining (`50.07s` reset) at stop. No 429 occurred and no retry was made. Actual response usage was **3,757 prompt + 4,546 completion = 8,303 tokens**. At the published on-demand list rates for GPT-OSS 20B ($0.075/M input, $0.30/M output), the nominal uncached estimate is **$0.00165**; actual billed amount is not exposed in response usage and may differ with cached input/account terms. See [Groq model pricing](https://console.groq.com/docs/model/openai/gpt-oss-20b) and [rate-limit headers](https://console.groq.com/docs/rate-limits).

## Offline work and next step

Offline DEV regression verified sentence-level informational IDs, useful exact sentence rendering, exclusion of question/header/context-only text, Markdown soft-line-wrap validation, intact technical procedures, and unchanged SHA/approved/scope/safety gates. Targeted selector suite: **20 passed**. Full suite after the correction: **451 passed, 5 xfailed, 0 failed**. `py_compile` and `git diff --check` passed.

This run demonstrates that the offline unitization correction is not enough to establish live usefulness. Do not tune the prompt on these holdout questions. Next step: diagnose the general route/readiness behavior and safe useful Evotor fallback offline against independent fixtures; then freeze a new holdout and rerun only after a fresh quota check. No manual Telegram pilot until a bounded live gate produces useful answers, evidence/source validation and the negative safety case all passes. No code was committed or pushed.

### Trace clarification added after offline review

The original summary used “0 retrievals” to mean no retrieval-stage Groq HTTP request. That wording was inaccurate: local Qdrant candidate lists are present in the saved trace for the two Evotor turns and receipt-period turn. The detailed correction and B+ replay are documented in [offline replay report](p1_bplus_offline_replay_20261026.md).
