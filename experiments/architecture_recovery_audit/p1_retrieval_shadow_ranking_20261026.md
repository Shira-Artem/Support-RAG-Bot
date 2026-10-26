# P1 retrieval shadow ranking — 2026-10-26

## Scope and provenance

This is a bounded analysis of the existing frozen audit C at `experiments/retrieval_audit_20261026/`; it is not a new corpus audit. The audit contains 54 retrieval-eligible turns, 45 distinct exact question strings, 35 answerable approved golds, and 19 turns with no approved evidence. All 35 gold documents occur in the raw top-100. No KB, Qdrant collection, application retrieval code, or production data was changed.

All files from the original audit directory were copied into the repository after a privacy scan. Question text and artifact content were checked for email/API credential patterns; none were found. Numeric phone-pattern matches were document IDs, not question text. The inventory contains approved metadata and hashes, not source body text.

## Task/operation filter findings

The four approved golds are present in raw retrieval candidates but absent from the eligible result because the audit classified them as explicit task/operation mismatches:

| Query | Gold document | Raw rank | Audit exclusion |
|---|---|---:|---|
| m0113 | `platformaofd-lkk-receipt-search` | 8 | `receipt_search != cash_search` |
| m0119 | `batch-20261013-bank-directbank-all-accounts` | 2 | operation mismatch: `connect` |
| m0121 | `batch-20261013-bank-directbank-all-accounts` | 2 | operation mismatch: `connect` |
| m0125 | `evotor-tspiot-localmodule-20261019` | 2 | `tspiot != model_features` |

These findings verify where approved evidence is lost. They do not establish that the filters are wrong: the frozen labels alone do not justify weakening applicability constraints. No filter or metadata changes were made.

## Frozen metrics

The audit's production-pipeline baseline is the `filtered` method. The `soft` method is an existing analytic shadow using the frozen formula in `soft_ranking_formula.json`; it does not run in production.

| Method | Document R@1 | Document R@3 | Document R@5 | Gold-section hit @1 | @3 | @5 |
|---|---:|---:|---:|---:|---:|---:|
| Raw retrieval | 45.7% (16/35) | 77.1% (27/35) | 80.0% (28/35) | 34.3% (12/35) | 71.4% (25/35) | 74.3% (26/35) |
| Current hard pipeline | 74.3% (26/35) | 85.7% (30/35) | 88.6% (31/35) | 45.7% (16/35) | 68.6% (24/35) | 77.1% (27/35) |
| Existing soft shadow | 68.6% (24/35) | 94.3% (33/35) | 97.1% (34/35) | 51.4% (18/35) | 65.7% (23/35) | 65.7% (23/35) |

The soft shadow gains 3 documents at R@3 and 3 at R@5 versus the current pipeline, while losing 2 at R@1. Exact gold-section hits improve by 2 at @1 and fall by 1 at @3 and 4 at @5. This is a depth tradeoff, not an overall win. The experimental candidate is therefore **NO-GO for production** and remains an analysis-only comparator.

## Safety and exact-match controls

- Frozen exact identifier cases FN 234/235 retain the expected rank-1 match in the compared methods.
- Query 999 has no approved candidates and remains empty; the shadow does not manufacture evidence.
- The audit's hard gates remain documented: approved status, unsafe-query rejection, explicit service/manufacturer/model/procedure conflicts, and exact code/version conflicts. No such gate was relaxed in this work.
- Four task/operation exclusions remain excluded in the production baseline. The audit's soft shadow is reported separately because it does not preserve those exclusions as hard task/operation gates.

## Decision

Stage 3 audit transfer and bounded comparison are complete. Keep the current hard pipeline unchanged. Do not enable soft ranking or modify task/operation filters based on this audit alone. A separate, labeled applicability review would be needed to determine whether any of the four gold annotations or metadata are incorrect. Next, proceed to the already-authorized bounded Stage 4 quality gate; keep B2 default-off and do not switch the worker.

## Audit artifacts

See [`retrieval_audit_20261026/`](../retrieval_audit_20261026/), especially `report.md`, `metrics.json`, `questions_gold.jsonl`, `retrieval_results.jsonl`, `loss_reasons.csv`, `approved_document_inventory.jsonl`, and `soft_ranking_formula.json`.
