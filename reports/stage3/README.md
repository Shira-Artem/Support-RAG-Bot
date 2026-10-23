# Stage 3 retrieval report — 2026-10-22

Scope: 100 questions from `data/evaluation_questions.jsonl`; 83 have an
approved reference document.  The comparison invokes retrieval only (zero LLM,
Telegram and SQLite calls).

Collections:

- CURRENT: `knowledge_organized_stage2_20261022` (934 points, not modified)
- STAGING: `knowledge_stage3_retrieval_20261022` (934 points)

## Results

| Metric | Before Stage 3 | Final STAGING | Change |
|---|---:|---:|---:|
| Reference document in top-1 | 36 / 83 | 38 / 83 | +2 |
| Reference document in top-5 | 57 / 83 | 61 / 83 | +4 |
| Pipeline selected reference | 29 / 83 | 40 / 83 | +11 |
| Reference rejected by pipeline | 46 | 38 | -8 |
| Extra selected documents | 98 | 87 | -11 |
| Selected service mismatches | 15* | 0 | fixed |

`*` The original service counter treated manufacturer routes as services.  The
final comparison checks only an explicitly stated service/OFD; the runtime fix
also separates `aQsi` from `aQsi Online` and `АТОЛ` from `АТОЛ Онлайн`.

With the final code on both collections, metadata-only CURRENT → STAGING deltas
are: selected reference 39 → 40, erroneous rejections 39 → 38, extra documents
90 → 87.  Raw top-1/top-5 stay 38/61 because text and vectors are deliberately
unchanged.

Newly selected reference cases versus the pre-Stage-3 baseline: Q001, Q016,
Q019, Q043, Q066, Q067, Q068, Q094, Q095, Q096 and Q100.  No case lost a
previously selected reference.  The only raw-rank regression is Q072 (30 → 31),
outside top-5 and without changing the pipeline result.

## Chunk order

Among 201 approved multi-chunk documents, CURRENT reconstructs 168 out of
order.  It has 667 chunks without `chunk_index` and 932 missing adjacency links.
STAGING reconstructs all 201 in source order, with zero missing indexes or
links.  Metadata records `chunk_index`, `section_index`, `section_chunk_index`,
`previous_chunk_id`, `next_chunk_id`, `chunk_role` and the relation to the
previous chunk.

## Numeric guard

Quantities, sums, dates and document numbers now remain ranking terms but are
not mandatory identifiers.  In the isolated draft check, the number-free UPD
procedure ranks third for “В УПД 12 упаковок, а привезли 10”.  Normal retrieval
still excludes it because its status is `draft`.  Error codes remain exact:
queries for ФН 234 and ФН 235 return only their respective articles; ФЛК codes
in article titles are inherited by their sections.

## Remaining limits

- 31 approved reference cases still reach `task_unresolved`; expanding the
  reviewed category vocabulary is the next general improvement area.
- Draft sources remain available only through an explicit isolated/demo check.
- CURRENT still lacks the new ordering metadata; no production switch was made.

Machine-readable details are in `baseline-current.json` and
`current-vs-staging.json` in this directory.
