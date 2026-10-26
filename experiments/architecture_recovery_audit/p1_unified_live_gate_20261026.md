# P1 unified live quality gate — 2026-10-26

## Frozen protocol

The rubric and new holdout questions were saved before calls in [p1_unified_live_gate_rubric_20261026.md](p1_unified_live_gate_rubric_20261026.md). The batch used the current unified main checkout, real Groq Understanding and Evidence Decision, the Source-first coordinator and retrieval path, local offline embeddings, and a read-only Qdrant facade over Stage3 `knowledge_stage3_retrieval_20261022`. Stage3 was `green` with 934 points. `.env`, Qdrant contents, SQLite production data, KB and worker were not modified. A temporary process override selected the verified Stage3 collection because the `.env` default points elsewhere; the override was cleared when the subprocess exited.

The hard cap was 12 Groq HTTP attempts, 6 retrieval turns, and zero automatic retries. This run stopped on the first provider 429; no request was retried. The attempt count for this batch was **4/12** (2 Understanding + 2 Evidence Decision), covering 2/6 retrieval turns. Successful provider usage was **4,169 prompt + 2,296 completion = 6,465 tokens**. Qdrant writes: 0 by design; only collection read checks, scroll/query methods were exposed to the runner.

## Results

| Holdout turn | Understanding / coordinator | Retrieval and evidence | Answer quality | Result |
|---|---|---|---|---|
| OFD role | Raw Understanding: question/explain, object OFD. Coordinator routed `grounded_information`, `new_task`. | Approved `atol-online-11256-what-is-ofd`, section “Что проверено по инструкции производителя”; source SHA verified. Semantic decision selected one valid evidence ID. | The semantic output was rejected as `answer_exceeds_information_budget`; selected unit had 3 sentences / 325 characters while the generic informational renderer permits at most 2 sentences / 520 chars. The lexical comparator returned the focused approved sentence: “ОФД получает фискальные документы от зарегистрированной ККТ, обрабатывает и передаёт их в ФНС в предусмотренном формате.” Manual usefulness PASS for lexical / FAIL for semantic (no answer). | **QUALITY FAIL** for B2 path; provenance gate passed, no unsafe action emitted. |
| OFD follow-up | Raw Understanding represented continuation/clarification; coordinator retained the same task and routed `grounded_information`, `continue`. | Qdrant retrieval succeeded and returned approved OFD/operator sources. | Evidence Decision failed with HTTP **429**, `rate_limit_exceeded`, `Retry-After: 3s`; provider usage was unavailable. No retry was made. | **BLOCKED**; follow-up usefulness not measured. |

Full sanitized raw/validated Understanding, before/after state, coordinator decisions, retrieval candidates, evidence IDs, source hashes, output/error, usage and latency are retained in [the live trace](p1_unified_live_gate_20261026.json). Latencies: turn 1 Understanding 2,324 ms, retrieval 636 ms, selector 1,048 ms; turn 2 Understanding 1,677 ms, retrieval 330 ms, failed selector 362 ms.

## Gate decision

Overall **NO-GO**. The first semantic answer was grounded but did not answer because composition rejected a broad evidence unit; the second answer could not be evaluated due to 429. A rate-limited subset is not evidence of a passing quality gate. The batch stopped at 4 attempts and left 8 unspent; no unbounded retry or follow-up run was made.

Minimal general correction to validate offline before any next live batch: build a bounded, answer-bearing sentence unit for informational sections when the selected paragraph contains multiple facts, while preserving whole ordered `procedure_block` units and the same approved/SHA/scope, claim-support, safety, and answer-length gates. This is a unitization/render-boundary issue, not a reason to loosen safety or applicability filters. Do not tune prompts using these holdout questions. After offline regression and independent holdout review, any next live run must be a separately bounded batch and account for Groq rate limits.

## Not reached / blocked

The batch stopped before OFD service renewal, Evotor's full internet → confirmed payment → next safe check sequence, unknown-then-confirmed model progression, receipt search and period follow-up, and live FN 234/235 comparison. Greeting/thanks boundary and fake Telegram transport remain offline-only checks from the existing integration suite; no real Telegram message was sent. These scenarios are **BLOCKED/not evaluated live**.

No production rollout is authorized by this result. B2 remains default-off. The Telegram worker was not switched; no real specialist chat or operator recipient was used.
