# P1 Semantic Evidence eligibility correction

Date: 2026-10-26. Scope: offline correction to the shared answer-bearing eligibility boundary for B2 and Source-first lexical selection. B2 remains default-off and is not accepted for live use.

## Confirmed issue and correction

The saved D1.3 selector decision chose both a factual sentence and a neighboring FAQ question as separate evidence IDs. The previous Source-first sentence ranker could also choose the contract/tariff sentence for the same follow-up because it matched lexical terms while missing the requested purpose.

`evidence_role` now classifies generic document structure and sentence form:

- question-shaped sentences and Markdown headings are not selectable answer units;
- short context labels are typed `context` and local validation rejects them unless a fact or whole procedure accompanies them;
- ordinary answer-bearing sentences are typed `fact`;
- a procedural/interface section remains one complete ordered `procedure_block`, including conditions and warnings.

The selector prompt only permits answer-bearing facts and whole blocks, while local validation rejects any question/header role and rejects context-only selections. Source-first lexical selection uses the same role function and cannot return question/header/context fragments as the answer. The offline A/B runner uses the shared section eligibility filter. Approved status, exact SHA, applicability, error-code, order, and safety gates remain independent and unchanged.

## Frozen-input comparison

Replayed the saved, previously known D1.3 DEV cassette and its matching diagnostic trace without provider calls. The frozen semantic choice contained two IDs: one generic FAQ question and one answer-bearing fact. The corrected candidate set excludes the question ID; the old decision then fails typed ID membership, while selecting the retained fact passes exact-source/SHA checks. On the same saved lexical section and follow-up, the old Source-first lexical result was the contract/tariff sentence; the saved semantic fact answers the operator-purpose question.

This is a regression demonstration on a known case, **not an independent quality holdout**. It does not establish a product-level win rate or justify enabling B2. The existing D3 cassette still selects its complete route/period procedure; partial lexical period-only output remains the historical baseline. Conditions, ordering, and warnings were not stripped from procedure blocks.

## Verification and boundaries

- Targeted selector + Source-first dialogue contract tests: **44 passed**.
- Full suite on Python 3.12.2: **449 passed, 5 xfailed, 0 failed**. The ignored `.local/vnext-deps` Python 3.14 package collision was isolated with a temporary import shim pointing the test process at the temporary Python 3.12 dependency directory; no repository or ignored runtime dependency directory was modified.
- Full suite retains the five existing xfails. No Groq calls, Qdrant access, Telegram send, worker action, KB edit, production SQLite write, or `.env` access/change occurred.
- B2 remains **NO-GO / default-off** pending an independent holdout and bounded end-to-end quality/safety gate.

Next requested work: the bounded retrieval correction based on the existing C audit, without a new broad audit or weakening hard applicability/safety constraints.
