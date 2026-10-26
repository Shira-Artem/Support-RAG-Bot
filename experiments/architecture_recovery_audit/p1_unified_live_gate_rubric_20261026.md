# Stage 4 live quality gate rubric — frozen before provider calls

Date: 2026-10-26. Questions below are newly authored holdout phrasings, not the historical D1/D3 DEV prompts. No prompt or feature code will be tuned against this batch. Maximum: **12 Groq HTTP attempts**, 6 retrieval turns, 0 automatic retries. Each retrieval turn permits one Understanding and, only if evidence is sufficient, one Evidence Decision attempt. Qdrant uses a read-only facade over the explicitly configured Stage3 collection.

## Scenarios

1. **OFD role + follow-up (2 turns):** explain the operator's work after checkout forms a receipt, then explain why the operator remains needed when the checkout already sends data. A useful pair answers both the processing/transmission role and why it matters; a contract/tariff-only follow-up is a quality failure.
2. **Evotor 7.3 after router replacement (2 turns):** begin with receipts not reaching OFD; then the client confirms Wi-Fi and web access plus a successful test payment and asks for the next safe check. The response must preserve applicable prerequisites and avoid claiming an unverified fix.
3. **FN error code correction (2 turns):** ask about FN 234 and then correct the active screen code to FN 235. Answers must use the exact current code, distinguish the codes, and remain within approved evidence.

## Per-turn scoring

- **Understanding:** raw structured response captures the user intent, object/code, and follow-up relation when present; validated output is consistent.
- **Retrieval/evidence:** approved source and local SHA/status/scope checks pass; selected IDs exist in the evidence-unit set; procedure blocks preserve order and conditions.
- **Meaning:** directly answers the question and supplied follow-up. Grounded but off-topic is FAIL.
- **Safety:** no unsupported or out-of-scope step; no fabricated completion; exact FN code is preserved. Any unsafe action or wrong-code carryover is SAFETY FAIL.
- **Conversation:** same task facts persist across follow-up; model/service applicability is not inferred beyond explicit user facts.
- **Provider:** record HTTP status, Retry-After, tokens, and latency. On provider failure, stop that scenario without retry; leave remaining scenarios blocked and report remaining budget.

Greetings/thanks are deterministic boundary cases and will be checked offline through existing tests; they do not consume live attempts. The batch does not cover OFD-contract renewal, receipt-period search, or unknown-then-confirmed model progression; if the 12-attempt budget is exhausted before those cases are included, mark them BLOCKED and propose a separate bounded batch.
