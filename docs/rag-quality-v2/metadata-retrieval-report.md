# P0 Step 3: metadata and retrieval routing report

Branch: `fix/rag-p0-dialogue-v2`
Audit detail: [metadata-audit.csv](metadata-audit.csv)

## Coverage and metadata

Audited **269 of 269** Markdown documents under `data/knowledge`. `DocumentLoader` successfully loaded all 269 unique documents. The current status inventory is **269 draft, 0 approved**.

After the targeted metadata additions, explicit front matter is present on 19 documents for `service`, 6 for `software`, 24 for `task_category`, 24 for `operations`, 10 for `search_fields`, and 8 for `evidence_coverage`. The audit also records conservative content/path classifications separately from explicit metadata and includes a basis for each inferred service, software, and task category. Action hints for untagged documents are kept out of the confirmed `operations` field.

**269 documents are marked `needs_review`** in the audit because every source card is still a draft and cannot be promoted for production use. The audit identifies **24 priority documents** drawn from the P0 regressions, DirectBank and account follow-ups, OFD/cash workflows, and aQsi/АТОЛ integration needs. It classifies instruction completeness as 28 complete, 190 partial, and 51 insufficient using visible evidence/limitation sections and procedural structure; these are triage estimates, not approval decisions. Each remaining row has a recommendation and review reason.

Metadata-only edits were made to ten cards: the DirectBank multi-account, schedule, intermediary-bank and file-import cards; Evотор 6 fiscal-document copy; aQsi password reset and 1C setup; ATOL cash reports and 1C integration catalog; and Platforma ОФД receipt search. The named edit-user and create-role cards already had explicit task and operation metadata; their existing partial evidence limits were retained. No instruction body or `status=draft` value was changed.

## Routing changes

- 1С:ДиректБанк statements now resolve to `bank_statement`; software routing recognizes the `1С` token and can match `1С:Бухгалтерия 8`. A list request can select a card that actually describes the statement list.
- aQsi/АТОЛ 1С integration requests resolve to `integration` and check the active service and software separately. An aQsi query cannot select the ATOL procedure (or vice versa) because the short software token `1С` is no longer dropped during comparison.
- Receipt copy/reprint is a distinct `receipt_print` task. `repeat_print` is a supported operation alias.
- `operation=unknown` no longer rejects an otherwise strongly relevant document by itself. A known operation still rejects an explicit conflicting `operations` label. Missing task labels require a strong lexical match (at least 0.60 overlap) plus the selected service match; weaker unlabeled candidates are rejected.
- RetrievalPipeline now independently requires `status=approved` before admitting a candidate to answer context. Explicit task/operation/service conflicts remain hard rejections. This supplements the existing approved-only filter in the production Retriever.

## Same-query before/after comparison

The comparisons use identical DialogueState v2 inputs and deterministic in-memory candidates. The “before” behavior describes the pre-Step-3 routing/filter logic captured by the reported regressions; “after” is exercised by the new tests. For positive-path tests, a copy of the candidate metadata is marked approved **in memory only** to model the state after human approval. Source cards remain draft.

| Query / case | Before | After |
|---|---|---|
| “А где посмотреть список выписок?” after a 1С:ДиректБанк task | No bank-statement task mapping; 1С was not available as a typed software route, so the DirectBank card could be rejected as unlabeled for the active route. | Resolves to `bank_statement/list`; exact `batch-20261013-bank-directbank-all-accounts` can be selected when the candidate status is approved. |
| “aQsi Online, как подключить к 1С:УНФ?” | Integration category/software scope were absent; generic 1С and other cloud-service instructions lacked a separate typed scope. | Resolves to `integration`; selects `aqsi-online-integration-1c-setup`, rejects the ATOL integration card on service mismatch. |
| “Эвотор 6, распечатать копию чека по ФД 123” with operation unresolved | The pipeline could reject on `operation_unconfirmed`. | Resolves to receipt-print relevance; unknown operation alone does not reject the exact Evотор 6 copy instruction. |
| Same relevant request, source status `draft` or missing | Status depended on the source adapter’s approved filter. | Rejected by the pipeline with `status_unapproved`; no draft text enters answer context. |

These are local routing comparisons, not a Qdrant CURRENT-vs-STAGING evaluation. **All repository cards are draft**, so production retrieval must currently abstain from using them. The local metadata changes have not been indexed. When publication review is complete, validate a reindex and end-to-end ranking only in a new, separate STAGING collection; this step did not access or modify Qdrant.

## Verification

- `DocumentLoader.load_all()`: 269 unique source documents loaded; all remain `draft`.
- Focused retrieval, metadata and replay tests: **23 passed**.
- Full `python -m pytest -q`: **167 passed**.
- `git diff --check`: no whitespace errors.

No user data, SQLite data, response validator, chunking behavior, embeddings, LLM configuration, or working vector collection was changed. No reset, commit, or push was performed.

## Follow-up

1. Human-review priority cards, especially source freshness, current screen names, and the boundaries recorded in `evidence_coverage`; keep draft status until that review is complete.
2. Add metadata only where the cited content supports it. The audit leaves unconfirmed actions/search fields blank and records hints separately.
3. After explicit approval, reindex only to a new STAGING collection and compare the same support cases against CURRENT read-only; inspect selected and rejected document IDs before any later rollout.
4. Continue classifying the remaining documents marked `needs_review`; this pass does not claim that a YAML label alone validates every step or permission.
