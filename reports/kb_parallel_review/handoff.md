# Handoff: KB Review B2

## Scope and guardrails

Audit artifacts for `feature/kb-review-b2`. This handoff does not approve candidates or release KB changes. No Groq/LIVE call, production Qdrant/SQLite access, reindexing, runtime change, `.env` change, or approved-card working-tree edit was made during this continuation. Manual 1C interface descriptions remain untouched. Common `PROJECT_STATE.md` and `RAG_MASTER_PLAN.md` were not edited.

## Evidence snapshot

- Corpus: 269 Markdown cards, 206 approved / 63 draft; all 269 loaded by real `DocumentLoader`/`Chunker` into 1,166 chunks. Frozen baseline has the same paths, IDs and statuses; 48 content hashes changed since the frozen baseline, all from draft cards.
- Branch delta vs local merge-base: 222 KB paths; `branch_changes.csv` has 222 reconciled rows. Two branch changes remain `branch_diff_semantic_unverified`. Current branch KB edits are limited to five draft cards.
- `card_review.csv`: 269 rows (all conservatively `warning` overall; individual criteria include pass/fail/unverified). `audit_issues.csv`: 249 (17 P0, 135 P1, 97 P2, 0 P3). By explicit status grouping, 27 are closed/verified/corrected; 222 remain open, partially verified, or gated. 210 rows require SME review. These are audit findings, not 249 proven KB defects.
- Source evidence: `source_review.csv` has 397 distinct URL rows: 259 have a dated review/attempt and 138 have `checked_at=unverified`. This field count is not a claim-verification count; many dated rows are only partial, so accessibility does not establish all claims. `source_register.csv`: 320 records / 306 unique URLs through S323; `claim_evidence.csv`: 639 rows.
- Mechanical signals: 52 warnings (43 long-paragraph inspection signals, 7 line-reference signals, 2 missing-metadata signals); no mechanical failure. Semantic overlap registry has 16 current pairs, all reviewed; the heuristic does not prove full semantic equivalence.
- Candidate validation: 44 drafts / 169 chunks, unique IDs and content hashes, no loader errors or warnings. The five initial B2 drafts remain external and unapproved; see `reports/kb_parallel_review/draft_review.md`.
- Coverage: six narrow approved-coverage gaps are confirmed (G1–G5 and U2). G6/G7 BIFIT remain partial/version questions. DirectBank import and schedule have approved partial coverage; do not duplicate. Physical Evotor 6 coverage does not establish Evotor 7.3/Power model instructions.

## Findings to route

- Diadoc pending-annulment status is an explanation gap (G2). Signed UPD cancellation is separately scoped to web workflow, document state, signature/roaming constraints and SME legal review (G3); the Evotor marked-goods approved card is not a Diadoc substitute.
- Saby's “incorrect handling” remains ambiguous. Official materials support rejection/re-send boundaries but do not establish rollback/restoration of the same incoming document ID. Clarify ordinary EDO rejection vs deletion, internal task or EGAIS before drafting a procedure (G4).
- DirectBank definition is a real missing explanation (G5). File import (`batch-20261013-bank-import-file-directbank`) and schedule (`batch-20261013-bank-directbank-auto-schedule`) already have scoped approved cards; further material is an SME-reviewed supplement, not a new article. Preserve the manually authored checkbox wording in 1C steps.
- BIFIT Desktop has bounded official evidence for some narrow 3.0x/plugin operations, but current map-editing workflow and compatibility are unverified; do not describe these as universally unsupported or invent menus.
- P1-134: TSPiOT drafts were narrowed to the source-bounded 500/514 paths; 453, compatibility and vendor-specific causes remain unverified and are queued for an engineer/provider.
- P1-01/02 and P1-116/117 are supported `operations` mismatches. No exact safe token was selected; remove/replace only after taxonomy-owner decision. `issue_refund`, `load_bank_statements` and `configure_vat_accounting` are not semantic substitutes for the observed 1C information/accounting actions.
- P1-58 Evotor 6: official help supports direct lookup via Evotor account/OFD and documents the +/-1 adjacent-receipt suggestion; risk from intervening fiscal documents is an inference, not a source-proven sequence for a specific check. A section-only review candidate is staged, requires KKT SME and is not applied to approved.
- Two metadata/routing test assertions still fail because their fixture treats the physical-aQsi integration draft as aQsi Online/approved; see P1-127 and `validation.md`. This is not a reproduced live/runtime failure. Existing R1/R2 are retrieval follow-ups where approved evidence exists; they must not be counted as missing KB articles.

## Validation

- `../../.venv/bin/python scripts/audit_kb_quality.py`: 269/269 loaded, 1,166 chunks, 52 mechanical signals.
- `../../.venv/bin/python scripts/review_kb_chunk_boundaries.py`: 19 potential word-boundary cases recorded for review; no source text was changed by this checker.
- `../../.venv/bin/python scripts/validate_kb_review_candidates.py`: 44/44, 169 chunks, 0 errors/warnings.
- `../../.venv/bin/python -m pytest -q tests/test_knowledge.py tests/test_index_documents.py`: 11 passed. The latest run of `tests/test_metadata_retrieval_routing_v3.py tests/test_retrieval_pipeline.py` yielded 15 passed, 2 scope-fixture failures described above.
- Cross-reference check: all coverage source IDs exist; all listed approved path/document_id pairs match the current inventory; all 229 unique card `source_url` values are represented in source review; all P0/P1 issues have a detailed `issues.md` section.
- CSV integrity: all 29 CSV files under `reports/` parse without malformed-width rows; the core registers have 269 card-review rows, 249 issues, 47 coverage rows, 44 candidate rows, and 19 boundary-review rows. `git diff --check` passes.

## Owner / SME decisions

1. Tax/legal/KKT SMEs must resolve all P0 items and specific P1 source/scope questions in `sme_queue.md`; candidates remain `draft`, `verified_at: null`, outside approved KB.
2. EDO SME clarifies the intended Saby state and legal handling; Diadoc expert confirms applicability per document type/roaming/operator.
3. Metadata/taxonomy owner decides operation labels for 1C informational/accounting articles; no runtime token was added.
4. Runtime owner reviews the 19 chunk boundaries and R1/R2 retrieval scenarios separately.
5. Source owner/SMEs must review source rows marked unverified or partial, and unresolved claims in `claim_evidence.csv`, before claiming exhaustive substantive confirmation. Current `source_review.csv` specifically has 138 rows without a dated check/attempt; do not treat that number as the total unresolved-claim count.

The audit stage has produced reviewable artifacts, but the full semantic/SME gate is not passed. During the latest follow-up, a duplicated section in the TSPiOT draft `astral-diagnostics.md` was removed because it reintroduced unsupported generic checks and a shared restart instruction for 453/500/514; the source-bounded 500/514 paths remain and the card stays draft. Offline revalidation after this edit: 269/269 documents, 1,166 chunks; 11 schema tests passed; 15 retrieval/metadata tests passed and 2 failed on the known fixture/service-scope mismatch; candidate validation 44/44, 169 chunks, 0 errors/warnings; boundary checker reports 19 potential cuts for runtime review.

Remote PR #4 remains open as Draft at head `0e5cfb59ca5756e73f1fabada5f1702b3c77b6f9`; its body still has earlier audit counts. A read-only fetch refreshed `origin/feature/kb-review-b2`. Local HEAD is `4e350552e196fa575d6a9f7eb7a060893d87bd6a`; the two histories share base `35c8a8ab5cceb0322e472ffbf64848cefc62da2a`, with the remote 125 commits ahead and local 2 commits ahead. A read-only `git merge-tree` reports content conflicts in `kb_audit.md`, `source_register.csv`, `README.md`, `claim_evidence.csv`, `source_review.csv`, and `validation.md`; the uncommitted worktree adds more overlap. Therefore do not force-push or overwrite the parallel branch. The current local handoff is not yet reflected in PR #4. No main merge or production change was made.

### Read-only ledger comparison against remote PR head

- Local `source_register.csv` has 306 unique URLs versus 294 remotely; all remote URL keys exist locally, and 7 shared rows have locally refreshed/expanded evidence notes.
- Local `claim_evidence.csv` has 638 keyed rows versus 612 remotely; all remote composite keys (`path`, `claim`, `source_url`) exist locally, and 12 shared records have updated evidence/scope assessments.
- Local `source_review.csv` has 397 URLs versus 388 remotely; all remote URL keys exist locally, and 14 shared rows have updated access or content-review classification.
- Markdown ledgers are not simple supersets: `validation.md` has unique material on both sides (remote 1,090 lines, local 778), as do `kb_audit.md` and README. The extracted remote-only sections are retained in [remote_unique_history_0e5cfb5.md](remote_unique_history_0e5cfb5.md); current reports remain authoritative for counts, while the archive preserves distinct historic evidence from the remote snapshot.

### aQsi Online source-access follow-up

The exact official pages for [password recovery](https://aqsi.online/instructions/faq/zabyl-parol-ot-lichnogo-kabineta-chto-delat) and [contacting support](https://aqsi.online/instructions/account/kak-svyazatsya-s-tekhnicheskoj-podderzhkoj) were reopened. Their visible text confirms the aQsi Online help-center topic/title and footer, but exposes no procedure body; the linked image resolves to the generic `/images/logo.svg` and could not be fetched. This does not establish that the approved steps are false and does not prove a new missing-coverage case. The official cloud-support contact `help@aqsi.online` is a safe fallback already recorded in the issue ledger; password-reset channels/codes and the cabinet form fields remain unverified. Keep P1-80/P1-84 SME-gated; do not invent UI steps or borrow physical-aQsi workflows.


### Additional source checks — 17 Nov 2026

- Reopened the official 1C/БУХ.1С DirectBank schedule article. It confirms the feature from 1C:Accounting 3.0.195, bank support dependency, schedule/type/date options, and optional directory creation and posting. Screenshot labels, user rights, customer bank/configuration behavior remain outside the verified scope.
- Read the official Honest Sign community page on TS PIoT (dated 30 Sep 2026). It describes the retail scope, phased X-API-KEY cutoff and possible POS-software behavior; item-specific exceptions, rollout state and device/software compatibility still require current regulation and provider review. Registered as S323.
- Re-read three FNS regional pages. The 2026 registration/FD-change page supports the OFD-report/registration-card flow but is labeled archival; the 2024 30-day article is also archival; the Jan 2026 VAT correction page is limited to 2025 transactions corrected from 2026 and is archival. Do not generalize these examples beyond their stated scope.
- A direct open of the canned-goods marking article returned an internal tool error. The previous bounded evidence remains historical; the latest attempt is not treated as confirmation.
- After these direct reads/attempts, source review has 249 dated entries and 148 with `checked_at=unverified`; this counts dated attempts, not fully validated claims. Source register is 320 rows / 306 unique URLs through S323.


### Additional source checks — 17 Nov 2026

- DirectBank schedule source: the BUKH.1C article confirms the feature from 1C:Accounting 3.0.195, bank support dependency, schedule/type/date options, and optional directory creation and posting. Screenshot labels and client-specific effects remain unverified.
- Honest Sign TS PIoT article (30.09.2026): read directly; confirms broad retail scope, phased X-API-KEY transition and possible POS-software behavior. Item exceptions and model/firmware compatibility require current regulations and provider review. Registered as S323.
- FNS sources on FD registration/replacement and transition VAT corrections were re-read; the pages are archival and are kept limited to the described scenarios. ConsultantPlus article 4.2 is a secondary consolidated edition from 24.06.2025, not proof of the current legal text.
- ATOL Online #12161 and #16576 were read directly; #12161 has no publication/version date and its FFD/FN guidance is not independently established as current; #16576 confirms only the published freeze conditions, not an individual customer tariff.
- aQsi's «Интеграция с 1С» URL is a help navigation page, not a procedure. The exact official installer guide confirms KKM Offline 3.1 and Aqsi.Integrator-3.9.0.73 for aQsi's software-hardware complex; cloud 1C is a hosting form with offline-equipment exchange, not aQsi Online. Release currency remains unverified. Manual 1C UI descriptions were left unchanged.
- The canned-goods marking article's direct open returned Internal Error; the previous bounded evidence is not treated as re-confirmed.
- Updated source ledger count: 397 review URLs, 254 dated attempts/reads and 143 `checked_at=unverified`; this does not count claim completeness. Source register remains 320 rows / 306 unique URLs through S323.


### FNS source follow-up — 17 Nov 2026

- Read the current FNS announcement about Order № ЕД-1-20/658@: it says changes start 01.03.2027 and FFD 1.05/1.1 leave circulation 01.09.2027. The linked order itself and model-specific transition procedure were not independently read; retain those as unverified.
- Re-read FNS articles on the 2025 simplified FN replacement exceptions and unilateral KKT deregistration. Both carry an archival notice; their summaries are limited to the stated exception list, 60-day document handoff and registration-card evidence, not applied as current individualized legal advice.
- Source-review count is now 397 URLs, 257 with dated attempts/reads and 140 with `checked_at=unverified`. These are attempt-date counts, not claim-completeness counts.


### Public endpoint source context — 17.11.2026

Reopened aQsi’s public «Данные ОФД и ОИСМ» help page. The IP/port values flagged by the GitHub payload review are printed by aQsi in its public configuration table alongside named provider endpoints and DNS alternatives. This source check supports classifying them as public service endpoints rather than private/customer network data; it does not prove the values are still operational, so the report retains provider-confirmation warnings. No customer-specific host, credential, secret or local network details are included.


### DirectBank source rechecks — 17.11.2026

Read the official BUKH.1C articles on file import (publication 11.08.2022) and all-bank-account loading (19.02.2024). They bound features to 3.0.117 and 3.0.148, respectively, and describe conditions at a high level. Exact screen labels are embedded in screenshots and were not transcribed or modified; bank support, user rights and client-specific configuration remain unverified.
