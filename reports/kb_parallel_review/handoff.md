# Handoff: KB Review B2

## Latest offline verification — 18 Nov 2026

- Main KB: 269/269 documents loaded, 1,168 chunks; 204 approved / 65 draft; 57 mechanical signals, with no loader/schema failure. Six are heuristic `operations`-missing warnings on intentionally empty operation lists; policy compatibility remains unknown.
- Candidate registry: all 52 candidate Markdown files represented and mechanically refreshed against `DocumentLoader`/`Chunker`; 209 chunks, unique IDs/hashes, 0 errors/warnings.
- Targeted schema/index/quality-contract tests: 25 passed. Chunk boundary checker: 19 possible mid-word cuts in 19 cards, routed to runtime owner; source Markdown remains intact.
- Current worktree KB delta: 24 files (six body/list diffs, 18 metadata-only); hand-authored 1C UI/body steps, including the “Расширенная настройка” checkbox wording, were not edited. Report CSV integrity: 29 files / 3,838 rows / 0 malformed widths; baseline/current paths and IDs match; coverage source IDs resolve; `git diff --check` clean.
- Full semantic/SME gate remains open: 269 card-review rows are warning and 231/235 branch-delta rows remain partial, with four owner/SME dispositions still open. This is a review queue, not proof that every listed card has a defect.

## Scope and guardrails

Audit artifacts for `feature/kb-review-b2`. This handoff does not approve candidates or release KB changes. No Groq/LIVE call, production Qdrant/SQLite access, reindexing, runtime change, or `.env` change was made. Current uncommitted KB diff has 24 paths: six have body/list diffs (five substantive draft corrections and the 1C import list numbering only); 18 are front-matter metadata-only. Seven existing draft cards received `requires_sme_review: true` where their review_note already required applicability/tax/integration review; two tax drafts remain in draft and two acquiring cards have the unsupported operation token removed. Approved changes remain source/operation metadata or formatting only. P0-01/P0-02 tax corrections preserve path/ID, clear `verified_at`, set `requires_sme_review=true`, and await tax SME/owner review. Approved metadata/formatting changes cover DirectBank source dates/list numbering; removal of false `load_bank_statements` tokens from two acquiring cards, leaving `operations: []`; and four verified source publication dates (three 1C articles and one archived FNS page), plus refreshed `source_checked_at` for the ATOL FFD source reread and the aQsi Online email-registration source reread. All manually written 1C body/UI wording and checkbox wording remain unchanged. Common `PROJECT_STATE.md` and `RAG_MASTER_PLAN.md` were not edited.

## Evidence snapshot

Текущие числа этого снимка сверены 18.11.2026; более ранние dated notes ниже являются историей итераций.

- Corpus: 269 Markdown cards, 204 approved / 65 draft; all 269 loaded by real `DocumentLoader`/`Chunker` into 1,168 chunks. Frozen baseline has the same paths and IDs; provenance is recorded in `reports/kb_review_b2_quality/baseline_manifest.json`. All 269 baseline hashes match source commit `7d2ac5fc2f84659115f875449f5b3dedc899cb52`; 69 current card hashes differ and two statuses changed approved→draft for P0-01/P0-02. Current approved worktree changes comprise eleven metadata-only paths plus one list-numbering-only 1C edit.
- Branch delta vs local merge-base: 235 KB paths; `branch_changes.csv` has 235 rows and exactly matches the diff. 231 rows remain partial; four have explicit open owner/SME dispositions. The two aQsi page diffs on contact/reset and five other account pages were rechecked: source pages expose headings/navigation, not procedures, so those steps remain unverified and were not treated as false. Registration-by-email is now directly confirmed from the official text (P1-83 closed without body rewrite); exact form fields and other registration modes remain outside the card's scope. Current 18.11 worktree diff is 24 paths: two corrected tax drafts with body/status changes; three other draft content edits; one approved 1C file with list-numbering-only formatting; seven draft SME-marker metadata edits; and eleven approved metadata-only edits. This classification is by local worktree diff. Five supplied B2 drafts and review candidates remain outside the approved corpus.
- GitHub state checked read-only on 17.11.2026: existing PR #4 is open/draft to `main`, remote head `f12ad8200ba6fd7170d7bf3d06d75f278c42801b`, 138 commits / 298 changed files. Its description contains older totals. Local HEAD is `489f13d3540685957791b657f14ea628bbedb72f` and is not the published head; no push/merge or PR mutation was performed during this pass.
- `card_review.csv`: 269 rows (all conservatively `warning` overall; SME assessment is 267 true / 2 false / 0 unverified; other individual criteria include pass/fail/unverified). `audit_issues.csv`: 254 (17 P0, 137 P1, 100 P2, 0 P3). These are audit findings, not proven defects; open, partial and SME-gated dispositions remain in the issue ledger.
- Source evidence (latest 18.11.2026): `source_review.csv` has 416 unique URLs, all with a dated read/attempt; many readable pages confirm only bounded claims. `source_register.csv`: 393 records / 376 unique URLs; `claim_evidence.csv`: 662 rows, including 18 reconstructed source-scoped rows for previously unrepresented S378–S397 sources and four later source-specific evidence rows; the exact 39 rows from the earlier uncommitted snapshot remain unavailable.
- Mechanical signals: 57 warnings; no loader/schema failure. Six are `missing_metadata: operations` on two acquiring cards, two 1C form-reference cards, `usn-max-limit.md` and `edo/edi-operator-choice.md`; the empty lists are schema/policy-accepted and compatibility remains unknown. These are non-blocking metadata signals, not loader failures. Semantic overlap registry has 16 pairs; heuristic results do not prove full semantic equivalence.
- Candidate validation (latest run): 52 drafts / 209 chunks, unique IDs and content hashes, no loader errors or warnings. The registry was refreshed against every candidate file; all 52 paths are represented and all mechanical columns are populated. The five initial B2 drafts remain external and unapproved; see `reports/kb_parallel_review/draft_review.md`.
- Coverage: six narrow approved-coverage gaps are confirmed (G1–G5 and U2). G6/G7 BIFIT remain partial/version questions. DirectBank import and schedule have approved partial coverage; do not duplicate. Physical Evotor 6 coverage does not establish Evotor 7.3/Power model instructions.
- Current source snapshot is through S397 / 393 records / 376 unique URLs; claim_evidence currently has 658 rows after adding 18 source-scoped records for S378–S397; the prior 39-row worktree content remains unrecovered and these new rows are not represented as exact replacements. `source_review.csv` has 416 unique URLs with dated attempts. Readability remains bounded or partial for many claims; access limits are not treated as falsehood. See `reports/kb_review_b2_quality/validation.md` and `source_review.csv`.

## Findings to route

- P1-06 ATOL Online: the approved setup card still states “at any time/without restrictions”, while #22555 requires prior integration readiness and warns that rollback to FFD 1.05 needs FN replacement. A scoped external candidate is available at `reports/kb_review_b2_quality/candidates/atol-online-ffd12-transition-preconditions-review.md`; approved body remains unchanged pending integration/KKT SME and owner review.

- Diadoc pending-annulment status is an explanation gap (G2). Signed UPD cancellation is separately scoped to web workflow, document state, signature/roaming constraints and SME legal review (G3); the Evotor marked-goods approved card is not a Diadoc substitute.
- Saby's “incorrect handling” remains ambiguous. For an item actually deleted in Saby Docs, the official guide provides a bounded restore path to the previous folder; its icon assets were unavailable (HTTP 404), so icon controls are omitted. This does not undo rejection, signature or exchange, and does not establish restore of the same incoming EDI instance/ID. Clarify ordinary EDO rejection vs internal task/EGAIS; ask operator/SME about the specific status before promising recovery (G4).
- DirectBank definition is a real missing explanation (G5). File import (`batch-20261013-bank-import-file-directbank`) and schedule (`batch-20261013-bank-directbank-auto-schedule`) already have scoped approved cards; further material is an SME-reviewed supplement, not a new article. Preserve the manually authored checkbox wording in 1C steps.
- BIFIT Desktop has bounded official evidence for some narrow 3.0x/plugin operations, but current map-editing workflow and compatibility are unverified; do not describe these as universally unsupported or invent menus.
- Diadoc G3 candidate refreshed on 18.11 from official Kontur web help: request scope and roaming limitation were reread; a non-cancellable request warning/status restoration is supported only by the help branch for natural-person signatures. The draft labels that boundary and still needs EDO/accounting SME review before any approval.
- P1-134: TSPiOT drafts were narrowed to the source-bounded 500/514 paths; 453, compatibility and vendor-specific causes remain unverified and are queued for an engineer/provider.
- P1-01/02: false `load_bank_statements` tokens were removed from the two acquiring articles after official-source review; empty `operations` now produces compatibility `unknown` in the isolated schema check, not end-to-end retrieval evidence. P1-116/117 remain taxonomy-owner questions; do not substitute `issue_refund`, `load_bank_statements` or `configure_vat_accounting` for the observed 1C information/accounting actions.
- P1-58 Evotor 6: official help supports direct lookup via Evotor account/OFD and documents the +/-1 adjacent-receipt suggestion; risk from intervening fiscal documents is an inference, not a source-proven sequence for a specific check. A section-only review candidate is staged, requires KKT SME and is not applied to approved.
- Two metadata/routing test assertions still fail because their fixture treats the physical-aQsi integration draft as aQsi Online/approved; see P1-127 and `validation.md`. This is not a reproduced live/runtime failure. Existing R1/R2 are retrieval follow-ups where approved evidence exists; they must not be counted as missing KB articles.

## Validation

- `../../.venv/bin/python scripts/audit_kb_quality.py` (18.11.2026): 269/269 loaded, 1,168 chunks, 55 mechanical signals; statuses 204 approved / 65 draft. Two `missing_metadata: operations` warnings are expected after removal of false tokens from P1-01/02; they preserve unknown compatibility and are not loader errors.
- `../../.venv/bin/python scripts/review_kb_chunk_boundaries.py`: boundary ledger contains 19 confirmed mid-word chunk cuts across 19 cards (18 approved, 1 draft). Source Markdown itself is intact; refer these retrieval-fragment cases to the runtime chunker owner. No source text was changed by the checker.
- `../../.venv/bin/python scripts/validate_kb_review_candidates.py` (18.11.2026): 50/50, 195 chunks, 0 errors/warnings; unique IDs and content hashes.
- `../../.venv/bin/python -m pytest -q tests/test_knowledge.py tests/test_index_documents.py`: 11 passed. The latest run of `tests/test_metadata_retrieval_routing_v3.py tests/test_retrieval_pipeline.py` yielded 15 passed, 2 scope-fixture failures described above.
- Cross-reference check: all coverage source IDs exist; all listed approved path/document_id pairs match the current inventory; all 229 unique card `source_url` values are represented in source review; all P0/P1 issues have a detailed `issues.md` section.
- CSV integrity (18.11.2026): rerun after current changes before handoff. Core registers: 269 card-review rows, 254 issues, 50 coverage rows, 50 candidate rows, 673 claim-evidence rows, 413 source-review rows and 222 branch-change rows. Structural validation does not replace claim-level source review or SME approval.

## Owner / SME decisions

1. Tax/legal/KKT SMEs must resolve all P0 items and specific P1 source/scope questions in `sme_queue.md`; candidates remain `draft`, `verified_at: null`, outside approved KB.
2. EDO SME clarifies the intended Saby state and legal handling; Diadoc expert confirms applicability per document type/roaming/operator.
3. Metadata/taxonomy owner decides operation labels for 1C informational/accounting articles; no runtime token was added.
4. Runtime owner reviews the 19 chunk boundaries and R1/R2 retrieval scenarios separately.
5. Source owner/SMEs must review source rows marked unverified or partial, and unresolved claims in `claim_evidence.csv`, before claiming exhaustive substantive confirmation. All 413 current `source_review.csv` rows have a dated check/attempt; this does not mean all claims were verified.

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


### Current continuation — 17.11.2026

- Re-read official Честный ЗНАК pages for milk (03.08.2026) and selected canned goods (02.12.2025). Their product-specific dates differ; source records S358–S359 and two scoped claim-evidence rows added. `gtin-vs-item-tracking.md` remains draft; only its source metadata now points to the directly read milk page and explicitly limits that source to the milk example. No approved text changed.
- Re-read three BUKH.1C pages on USN advances (3.0.198), ENS operation naming (3.0.191) and ENS accounting settings (3.0.194). Updated S76/S78 and added S360. UI wording was not rewritten. The separate “close multiple months” URL returned HTTP 403 and remains source-unverified.
- Current source-review count is 397 URLs, 383 dated reads/attempts and 14 without a dated attempt; source register has 358 records / 344 URL keys; claim evidence has 641 rows.
- Offline after the current KB metadata change: candidate validator 44/44 (170 chunks, zero errors/warnings); `test_knowledge.py` + `test_index_documents.py`: 11 passed; whole KB Loader/Chunker 269/269, 1,166 chunks, 52 mechanical signals; `git diff --check` clean.
- Full claim-level and SME review is still incomplete. The two branch semantic findings and 40 source URLs without a direct date remain in scope; historical/partial evidence is not promoted to complete verification.

### Current continuation — 17.11.2026 (source rechecks)

- FNS current KKT page directly supports the general rule and refers to Art. 2 for exceptions; it does not support a full exception list. FNS 2025 archived pages and hosted copy of its letter describe limits to simplified KKT re-registration, including marked-goods indicators; current individual route still needs legal/engineer confirmation.
- Official FNS FFD 1.2 protocol version 1.32 was opened. Use only exact table/field references; it is not a universal implementation guide. FNS roaming page was opened and directly defines exchange between two operators; linked attachments were not reviewed. The direct official 54-FZ text link (`kremlin.ru/acts/bank/19505`) timed out again; no claim from that statute is treated as verified by this attempt.
- S361 was added for the protocol PDF; 1C source records S109/S110/S112/S114 were refreshed. Source-review count is 397 URLs, 370 dated attempts/reads and 27 without dated attempt. No approved content or 1C UI wording changed.

### 1C article source rechecks — 17.11.2026

Read four BUKH.1C pages: 2013 month-close expert article (not a current official user manual), 3.0.188 multiple-warehouse receipt (with EnterpriseData and KORP conditions), 3.0.189 ENP cash-flow item and release 3.0.168.19 reconciliation monitor. Scoped facts/limitations are recorded in S109/S110/S112/S114. Preserve owner-authored 1C UI descriptions exactly; no card instructions were edited.

### Marking source scope — 17.11.2026

- Official article on lost/damaged codes (2023) is about product recoding and does not supply scanner/KKT troubleshooting.
- Current operator article on beer/low-alcohol HoReCa distinguishes own/production consumption, cabinet withdrawal, separate retail-KKT scenario and partial keg withdrawal; group/date scope must be preserved.
- A page labeled “Статья от Партнера” was directly read and is not a primary operator source. Its broad OSU/retail assertions are unsuitable as rules; its link was removed from the draft. Updated existing S22/S74, added S363 and updated P2-83.
- Current source-review count is 370 dated reads/attempts of 397 URLs (27 without a dated attempt); source register 367 records / 353 unique URLs.

### Marking draft final offline pass — 17.11.2026

The unreadable 2024 retail-exceptions URL no longer supplies specific claims in `gtin-vs-item-tracking.md`; only the safe direction to check current group/operation/date-specific rules remains. Partner article link was removed. Candidate validator 44/44 (170 chunks); real corpus Loader/Chunker 269/269 (1,166 chunks); `test_knowledge.py` and `test_index_documents.py` 11 passed; `git diff --check` clean. Source counts: 397 URL rows (370 dated, 27 no date), source register 359 rows/345 URLs through S363.

### FNS dynamic and archived sources — 17.11.2026

Directly read the IP-registration page, archived pandemic-era online-commerce page, FNS EDO operator selection/list pages, FNS ENS topic page and archived FFD 1.05 correction article. Their evidentiary boundaries were recorded: online-commerce source is historic, operator pages are dynamic, and FFD advice is explicitly archived. Updated S25/S62/S157/S213 and added S364–S366. Current source-review count is 376 dated reads/attempts of 397 URLs (21 no date); source register has 367 rows / 353 unique URLs.

### FNS threshold/notice/correction scope — 17.11.2026

- Directly read archival FNS pages on the 2025→2026 22% transition, notices, 2020 UTII→new SNO, 2025 briefing on 2026 tax changes and correction checks. They are scoped to their dates and scenarios.
- The Novgorod FNS 2025 overview repeats future 15/10m VAT thresholds that conflict with later Federal Law 228-FZ; do not use it for current VAT thresholds.
- FNS letter S371 concerns VAT-exempt cultural tickets/BSO, not PSN KKT relief; P1-70 records the source mismatch.
- Updated S188/S156 and added S367–S371. Source review: 383 dated attempts/reads / 397 URLs, 14 without date; register 367 records / 353 unique URLs through S371.


### P1-131 follow-up — 17.11.2026

The 54-FZ draft has several specific scope/wording mismatches against the displayed consolidated Art. 2: food requiring special storage/sales conditions is missing from the door-to-door trade caveat; school meal scope is overbroad; the B2B cash-register statement uses “no direct interaction” instead of the presented electronic payment instrument condition; and the excise caveat is universal although p.8 enumerates limited clauses. The tanker examples omit vegetable oil. Official FNS law landing page is available but its link to the full official text times out. The official Buryatia FNS article is archived and supports only the p.9 wording. A narrow, legal-SME-gated section candidate is at `reports/kb_review_b2_quality/candidates/54fz-exemptions-scope-review.md`; do not use it as legal advice or promote it. Full list/current official law remains unverified.


### P1-136 — файловое расписание 1С, уточнение 18.11.2026

Официальное видео БУХ.1С для «Бухгалтерии» 3.0.162.17 говорит оставить приложение открытым в запланированное время для файловой базы. Прочитанная методика 1С по платформе 8.1 (18.01.2007) описывает выделенный клиент-планировщик с обработчиком ожидания для автоматических регламентных заданий. Она слишком старая и общая, чтобы подтвердить современную прикладную конфигурацию или достаточность открытого окна. Supplemental candidate предлагает только ограниченное предупреждение и требует проверки администратора; действующие UI-шаги не тронуты.


### P1-137 — срок ФН для подакцизной торговли, уточнение 18.11.2026

Временное расхождение ниже 410 дней следует описывать как более консервативную рекомендацию АТОЛ (#14419) относительно архивной формулировки ФНС «можно не менять до предела», а не как доказанное правовое противоречие. Техническая дата футера архивной публикации ФНС не подтверждает обновление содержания. Draft не выбирает один путь; специалист должен установить актуальную норму, применимость процедуры АТОЛ и состояние конкретного ФН.


### P1-132 — детализация коррекции Эвотора по ФФД, 18.11.2026

Полный официальный текст доступен по ссылке статьи со slug; numeric-only вариант в этом обращении timeout. Пары исправления ошибочного чека коррекции подтверждены для ФФД 1.05/1.2, однако у публикации нет явного номера версии/даты. Candidate — дополнение к существующему документу, не новая KB-тема; без SME нельзя включать фискальную последовательность в approved.

### BIFIT follow-up, 18.11.2026

Официальные BIFIT release notes от 25.08.2026 и 06.10.2026 показывают, что «Карта столов» упоминалась среди поддерживаемых плагинов/исправлений Desktop 2026.08.1 и 2026.09.1. Центр загрузок на дату проверки указывает текущий Desktop 2026.09.1-906844. Это обновляет прежний вывод: продукт и плагин нельзя назвать заброшенными на основании старой инструкции. В то же время эти источники не дают отсутствующую процедуру редактирования карты и не подтверждают совместимость плагина эквайринга Сбербанка 1.0.4 с текущим релизом. Таблица прав относится к отдельному плагину «Бронирование»; её настройки не перенесены на «Карту столов». Подробности и новые source IDs S392–S395 — в `coverage_matrix.csv`, `source_register.csv`, `claim_evidence.csv`; кандидаты остаются draft/SME-gated.

Последняя offline-проверка после уточнения двух BIFIT candidates: `../../.venv/bin/python scripts/validate_kb_review_candidates.py` → 50/50 candidates, 269 main KB docs, 194 candidate chunks, unique IDs and hashes, 0 errors/warnings. Структурная проверка не означает предметного утверждения.

### Финальный offline прогон этого прохода — 18.11.2026

`audit_kb_quality.py`: 269/269 documents, 1,166 chunks, 53 mechanical signals (previous snapshot 52; one new long-paragraph warning is in the draft `atol_online/law/sugary-drinks-classification.md`, 1,160 chars). `review_kb_chunk_boundaries.py`: 19 confirmed mid-word cuts; no extra confirmed cut for that new warning. Target schema/index tests: 11 passed. Candidate loader: 50/50 candidates, 195 chunks, no errors/warnings. CSV sweep: 29 files, consistent widths; source references in coverage rows all resolve. Current ledgers: 391 source-register records / 374 unique URLs (through S395), 413 source-review rows, 673 claim-evidence rows, 49 coverage rows. The new paragraph warning is a mechanical signal, not proof of a content defect; card remains draft and no approved content changed.


18.11.2026: новый механический warning `long_paragraph` зарегистрирован как M-061 и проверен через реальный DocumentLoader/Chunker: критерии 1–5 целиком размещены в одном 651-символьном чанке. Это подтверждённый случай без дефекта чанкинга; lint signal не приравнивать к KB gap. P1-129 остаётся на legal SME review. Audit issue ledger теперь 254 строки (17 P0, 137 P1, 100 P2); card_review остаётся 269 строк.


### Source review date reconciliation — 18.11.2026

Rechecked the current `source_review.csv`: 413 rows, 413 unique URL keys and 0 blank `checked_at` values. This supersedes the historical owner-decision note above that referred to 40 undated rows at an earlier snapshot. A dated attempt/read does not mean the linked claims are fully verified; partial scopes and access errors remain classified in the row.

### Workspace guardrail check — 18.11.2026

Five KB paths are modified: three draft cards with `verified_at: null` and two approved DirectBank cards. The file-import article has a list-numbering-only correction; both approved articles have `source_checked_at` refreshed after direct source reread. No status, ID or verified_at changed; manual 1C UI wording and the “установить флажок "Расширенная настройка"” phrase remain intact. Shared `docs/PROJECT_STATE.md` / `docs/RAG_MASTER_PLAN.md` remain unchanged. Full `git diff --check` passes. No commit or push was performed under the TZ restriction.

Final acceptance cross-check (18.11.2026): current and frozen inventory each contain 269 Markdown paths; path sets match, with zero added/removed paths or `document_id` changes. Exactly two status changes are the targeted P0-01/P0-02 demotions (206/63 baseline → 204/65 current). `card_review.csv` has 269 rows and branch delta ledger 222. All 154 P0/P1 IDs have detailed entries in `issues.md`; all 229 current KB source URLs are represented in source review, and all 413 source-review URL rows carry a dated attempt.

### P0 tax source recheck — 18.11.2026

For P0-01/P0-02, the current official FNS threshold page and its archived 20m notice were reread. The full amendment text of FZ 228-FZ Articles 1–2 and displayed Article 145 were read in ConsultantPlus. Evidence now explicitly separates prior-year thresholds (20m for 2025–2028, 15m for 2029, 10m for 2030) and current-year thresholds (20m for 2026–2029, 15m for 2030, 10m for 2031), plus combined USN+PSN income only where the Article 145 wording applies. FNS’s direct link to official publication №0001202607040017 was followed again but timed out; its primary publication body is still not claimed as read. Two replacement candidates have `source_checked_at: 2026-11-18`, `verified_at: null`, and remain tax SME/owner-gated. After this historical note, the existing cards were corrected in the worktree and demoted to `draft`; see the current scope section above. They are not approved or indexed pending owner/SME review.

### Дополнение 18.11.2026 — retrieval fixture mismatch

Изолированный запуск `../../.venv/bin/python -m pytest tests/test_retrieval_pipeline.py tests/test_procedure_applicability.py tests/test_metadata_retrieval_routing_v3.py tests/test_stage3_retrieval.py -q` дал **26 passed, 2 failed**. Оба отказа — `test_integration_1c_search_is_scoped_to_selected_cloud_service` и `test_chunker_preserves_explicit_software_and_routing_metadata` в `test_metadata_retrieval_routing_v3.py`. Текущая карточка `aqsi_online/integration/1c-setup.md` по официальному источнику документирует физическую кассу aQsi и имеет `service/procedure_service: aQsi`; тесты используют её как облачный `aQsi Online`. Это устаревшее fixture expectation, как уже отмечено в P1-127; runtime defect не доказан. Передать retrieval owner для выбора корректного cloud-документа или обновления fixture; тесты/runtime в KB-аудите не редактировались.

### Coverage matrix reconciliation — 18.11.2026

В `coverage_matrix.csv` добавлена ранее пропущенная строка G8: частичный охват aQsi Online + 1С через API, связанная approved-карточка общего API, официальный evidence S45/S47/S197 и вопросы к производителю/1С-разработчику. Строка отделяет общий cloud API от физической интеграции ККТ aQsi через ККМ Offline и не объявляет 1С:УНФ connector поддержанным. Matrix теперь содержит 50 строк; подтверждённых точных coverage absences — шесть (G1–G5, U2), G8 остаётся partial, G6/G7 — scope/compatibility unknown.

### DirectBank definition source recheck — 18.11.2026

Официальная страница сервиса 1С перечитана полностью. Она подтверждает прямой обмен, отправку платежей и получение выписок без отдельной программы «Клиент-Банк», договор ДБО с банком и текущую формулировку 1С об отсутствии дополнительной платы за сам сервис. Draft source date, S5, source review and claim evidence обновлены. Approved определение отсутствует; G5 остаётся точным knowledge gap, а не runtime проблемой. Доступность по банку/конфигурации, ДБО и будущую стоимость следует проверять индивидуально; draft требует SME.

### DirectBank source review — file import and schedule, 18.11.2026

Два официальных текста БУХ.1С непосредственно перечитаны. Они подтверждают только version-bounded feature scopes: .txt импорт в 3.0.117+ без отключения сервиса при предусмотренных сценариях и расписание в 3.0.195+ с зависимостью от банка. Существующие approved-инструкции дают partial coverage, дубли не нужны. В file-import исправлена лишь Markdown-нумерация списка 1,2,3,3,4 → 1,2,3,4,5; текст действий не менялся. Расписание, все ручные формулировки 1С и checkbox «установить флажок “Расширенная настройка”» сохранены. Скриншотные controls, права, bank support и эффекты автопроведения требуют SME/client check. Сверка файлов с `HEAD` после нормализации только дат источника и номеров списка подтвердила тождество остального текста шагов 1С.

### Evotor 7.3 source recheck — 18.11.2026

Официальное руководство именно физической модели 7.3 перечитано полностью и подтверждает повторную печать по известному номеру ФД. Указаны путь меню, поиск номера на прежнем чеке/в ОФД, ввод номера и ОК. Версия прошивки, права, вид копии и поведение после замены ФН не установлены. External candidate, source date, S1, source review и claim evidence обновлены. Existing approved инструкция ограничена Эвотор 6; G1 остаётся реальным пробелом для модели 7.3 до SME review.
### Audit consistency correction — aQsi refund limits, 18.11.2026

- The approved `aqsi-device-standard-refund` article still has an unfinished step 6; prior report wording that said this was fixed was inaccurate. The approved file was left untouched.
- Official aQsi page directly reopened: https://aqsi.ru/support/vozvrat-oplatyi-po-karte/ . It confirms the three blocked cases only for its described refund operation; model/release and acquirer-specific exceptions remain unspecified.
- P2-69/P2-96, `card_review.csv`, source register/review and claim evidence now consistently record a proposed wording, not an applied fix. The duplicate issue records are retained to preserve history.

### ATOL Online blocked-service P0 review — 18.11.2026

- Official pages [#11077](https://help.atol.online/article/11077) and [#21114](https://help.atol.online/article/21114) were reopened. They confirm that blocked service disables the register/API and receipts are not formed/sent; correction follows only if real operations occurred; the generic correction article does not decide an individual case. The >30-day overdue clause about FN removal without archive closure is also present.
- Refreshed the external candidate and S87/S137, source-review, claim-evidence and P0-07 records. Candidate remains draft/SME-gated; approved `service-blocked.md` still contains its false receipt-formation claim and was not changed.
- Earlier `changes.md` wording that said the approved error was fixed has been corrected; the remaining P0 is explicit in the handoff.

### 1C acquiring operations metadata — 18.11.2026

- BUKH.1C and official ITS sources confirm `acquiring-returns.md` is a bank debit on an acquiring refund from 3.0.207, and `acquiring-patent-tax.md` is advance tax-regime selection from 3.0.174. Neither describes statement import.
- Removed only `load_bank_statements` from both approved metadata records, leaving `operations: []` and `task_category: bank_statement`; refreshed `source_checked_at`. No text, 1C UI labels, status, ID or `verified_at` changed. No new runtime token was introduced.
- An isolated real DocumentLoader/Chunker/normalizer check accepts empty operations; task category remains bank_statement and operation compatibility becomes `unknown`, avoiding the false explicit mismatch. This is a metadata-gate result, not evidence of successful end-to-end retrieval. Accountant/tax SME must verify article scope.

### Итоговое дополнение к текущему handoff — 18.11.2026

- Актуальные offline-прогоны после P1-43 candidate: main KB **269/269**, **1,168** chunks, 55 mechanical signals, 204 approved / 65 draft; candidate validator **51/51**, 199 chunks, unique IDs/hashes, 0 errors/warnings; schema/index pytest **11 passed**. CSV structural sweep: 29 files, 3,837 data rows, 0 malformed widths; `git diff --check` clean.
- Реестры: source review **414** unique URL keys, все с датой прямой попытки/чтения; source register **392** records / **375** unique URLs through S396; claim evidence **675** rows. Датированная проверка не равна полному подтверждению claim. 28 URL остаются с ограничением прямого доступа/прочтения.
- P1-43: отдельный replacement candidate `reports/kb_review_b2_quality/candidates/aqsi-paper-print-retry-review.md` подтверждает только отображаемую производителем метку «Оформить» и не утверждает состояние ФН/ОФД. Verified alias «Продолжить печать» не найден; модель и release не указаны. Approved source card не изменена; нужно решение инженера ККТ и владельца KB.
- P0-01/P0-02: полная читаемая правовая копия ФЗ №228-ФЗ из Контур открыта и фиксирует точные замены в ст.145 (S396). Это corroborating secondary source, не официальный портал публикации; первичная публикация остаётся не подтверждена. Оба документа локально corrected, `draft`, `verified_at: null`, `requires_sme_review=true`; до tax SME/owner signoff не утверждать и не индексировать.
- Общий semantic/SME gate **не пройден**: 218/222 branch-delta paths имеют partial review; 15 P0 ожидают SME/owner решения; нет доказательств полного claim-level семантического review для всех 269 карточек. Поэтому эта передача показывает конкретные локальные corrections/candidates и исчерпывает доступную автономную проверку, но не является одобрением KB для production.


### EDO draft/source follow-up — 18.11.2026

- Reopened Diadoc status article and Saby rejection/annulment materials. The Diadoc status facts are bounded to the 2022 vendor article; the Saby current public article distinguishes rejected unsigned documents from bilateral annulment after signing. Saby Docs recovery remains deletion-only. A new Saby official help record S397 covers the bilateral request boundary.
- Updated the B2 Saby draft to cite currently readable sources and distinguish rejection, signed annulment, and deleted-item recovery. Its earlier exact source remains `open_pending_source` and is not used as proof. The B2 draft overlaps the consolidated `saby-incoming-rejected-document` candidate; do not submit both as two KB additions.
- Four EDO explanation/revocation drafts/candidates now have empty operation declarations pending taxonomy owner decision, because the current policy lacks `explain_document_status` and `request_document_revocation`. This preserves unknown compatibility and avoids inventing runtime vocabulary. No runtime code changed.

Current candidate total after the EDO metadata/content review: 51 / 203 chunks, all loader/schema-clean; external source-date and tax SME gates remain as recorded.


### Structural ledger reconciliation — 18.11.2026

After the Saby/Diadoc updates, all 29 report CSVs contain 3,837 data rows with consistent widths; 393 source-register IDs are unique and all source IDs referenced by the 50 coverage rows resolve. Branch-delta inventory still has 222 KB paths and `branch_changes.csv` has exactly the same 222 paths, with no missing or extra entries. This validates register integrity/coverage of the diff, not semantic completion: 218 branch paths are still partial and expert review remains open.


- Evidence-register integrity note (18.11.2026): a CSV write failed during a metadata refresh and truncated the working `claim_evidence.csv`. It was restored from `HEAD` (639 rows), then 18 fresh evidence rows were built from source-register entries S378–S397 that had no claim-ledger representation. The earlier 678-row worktree version is not available in this workspace; its 39 uncommitted records are still not recovered. The new 18 rows are source-traced additions, not claimed restoration of the old rows. Do not treat the older count as current or claim full evidence completeness.


- Source/claim follow-up 18.11.2026: S359 was directly reopened for canned-goods commission/agency returns. The scoped reverse-UPD method and date window were recorded for the existing draft; this does not establish current EDO/1C screen steps, product eligibility or accounting treatment. Source review now has 416 dated URLs and claim evidence 658 rows.

## Offline verification addendum — 18.11.2026

Rerun from the current worktree: `audit_kb_quality.py` loaded 269/269 cards into 1,168 chunks (204 approved / 65 draft; 57 mechanical warnings); candidate validator loaded 52/52 external drafts into 207 chunks with unique IDs/content hashes and 0 errors/warnings; `test_knowledge.py`, `test_index_documents.py`, and `test_b2_2c_quality_contracts.py` passed (25 tests). All 29 report CSVs parsed uniformly (3,821 data rows); all 50 coverage rows' 93 unique source IDs resolve; baseline/current path and ID sets match (269 each; no ID changes); `git diff --check` is clean. All 289 unique source URLs across current KB cards and all URLs in the 658 claim-evidence rows appear in `source_review.csv`; all 416 source-review URLs have dated checks/attempts.

This validates document structure/contracts only. The stage is **not semantically complete**: all 269 `card_review.csv` rows remain overall `warning`, 218/222 branch-delta paths remain partial, and SME/owner decisions are still required for high-risk legal/accounting/fiscal and operation-taxonomy questions. No Groq/LIVE, production Qdrant/SQLite, reindexing, or runtime changes were made. Per the supplied TZ, no commit/push/merge or PR publication was performed; existing remote PR #4 remains on its previously observed head and does not include this worktree.

### Related offline fixture result

A broader local run of `tests/test_procedure_applicability.py tests/test_metadata_retrieval_routing_v3.py tests/test_task_operation_resolver.py tests/test_retrieval_pipeline.py` produced **48 passed, 2 failed**. Both failures assert that `aqsi-online-integration-1c-setup` is a cloud `aQsi Online` document. Its current draft scope is physical aQsi + ККМ Оффлайн, confirmed by the manufacturer guide; the tests force the draft into their approved fixture but cannot change its product scope. This is recorded as stale test fixture/assertion, not a KB gap or established runtime bug. Pass the fixture correction to the runtime/test owner; no test or runtime file was edited.

### Source-mismatch reread — 18.11.2026

Reopened the full official aQsi scanner article, Platforma OFD cash-section guide, and ATOL Online reconciliation-acts article. They reconfirm (1) different guidance for aQsi FN error 02h vs. unreadable code, (2) separate Platforma OFD statuses «Снята с рег.» vs. «ФН+РНМ» plus the guide's unresolved 72/48-hour filter contradiction, and (3) quarterly ATOL reconciliation-act delivery after quarter-end. Source/evidence dates and two isolated external candidates were refreshed; no approved bodies changed and these are existing-card corrections, not new coverage gaps. All remain owner/SME gated.

### Original B2 source reread — 18.11.2026

All five supplied B2 source URLs were directly reopened. The model-specific Evotor 7.3 reprint-by-FD procedure is confirmed; Diadoc’s two pending-revocation statuses are distinguished; Saby distinguishes rejection from bilateral annulment and directs to a corrected new document, with no old-ID restoration claim; 1C defines DirectBank as direct bank exchange without separate Client-Bank and states DBO dependency; BUKH.1C confirms scheduled statements from 3.0.195 subject to bank support and posting/reference automation options. All five remain external `draft` / SME-gated. The schedule supplement is not a duplicate of the approved DirectBank schedule article; hand-authored 1C interface labels were not reinterpreted or changed. Existing claim evidence scope/date annotations were updated only, no new rows added.

### SME-assessment closure for two old approved cards — 18.11.2026

Direct reread of the aQsi Online «Мои кассы» page confirms only its section title/navigation and an image, not the figure columns stated in the approved card. That claim remains unverified and the card is routed to aQsi/KB SME; no approved text or metadata was changed. Direct reread of Evotor's OFD-payment guide confirms the bounded, low-risk advice already in its card; SME review is not required for this generic check. The matrix is now 268 `true`, 1 `false`, 0 `unverified` for SME requirement, while all 269 overall card results remain `warning`.

### 1C invoice/UPD operation metadata follow-up — 18.11.2026

Two confirmed wrong `configure_vat_accounting` tags were removed from approved 1C invoice/UPD reference cards and left as empty operation lists pending taxonomy owner/SME selection. This is metadata-only; every UI/body string, document ID, status and verification date is unchanged. `operation_compatibility` resolves to `unknown`, not a wrong match.


### Priority P0 source rereads — 18.11.2026

Directly reread official sources for P0-05–P0-11 and P0-15–P0-18. Findings are deliberately bounded: aQsi error 18 requires a zero unsent-FD count before FN closure; ATOL block #11077 says no receipts are formed and only actual intervening transactions require correction after unblock; ATOL #16669 describes a physical KKT/FN in the provider data center; archived FNS pages on KKT registration, electronic receipt delivery, and special VAT-rate transition were refreshed with their archival status and SME limits; ATOL #26774 API fields were confirmed only for its described scenario; FNS correction guidance distinguishes document states only for its stated transition scenario; archived FNS jewelry notice does not prove a universal 36-month FN rule; FNS correction PDF has no visible publication/version in the inspected front matter; direct PDF reopen for P0-14 timed out, but ATOL help #22561 was reread and confirms technical `ism_optional` behavior without legal/product-group authorization. Evidence and source dates are synchronized in source review, claim evidence, source register and P0 issue notes. All approved cards remain unchanged in these follow-ups; candidates remain draft and SME-gated. See `reports/kb_review_b2_quality/issues.md` and `validation.md` for claim-level boundaries.

## Current reconcile after follow-up — 18.11.2026

The previous 222-path/207-candidate-chunk counts above are historical and are superseded by this snapshot. Reconciliation against the common-base Git diff now matches 235/235 changed KB paths to 235 unique ledger rows; 13 previously absent paths were added with path-specific diff notes, baseline IDs/statuses, and partial dispositions. Review is still not semantically closed: 231 rows remain partial and four have open owner/SME dispositions. The BIFIT S317 follow-up adds three source-scoped claim records (661 total) and narrows G6: the manufacturer documents order, split-check/pay, discount, and delete actions, but not Table Map creation/editing; UI version, icon names, deletion recovery and current build compatibility remain unresolved. The external candidate is updated and remains SME-gated.

Repeatable offline state: 269/269 KB docs, 1,168 KB chunks; 52/52 external candidates, 209 chunks, unique IDs/hashes, zero validator errors/warnings; 25 targeted pytest passed; 93/93 referenced source IDs resolve across 50 coverage rows; all 29 report CSVs parse uniformly (3,837 data rows); baseline provenance verifier passes. `git diff --check` is clean. No runtime/LIVE, production data/index, commit, push or merge operations were performed. The standalone pytest launcher has a stale interpreter shebang; use `../../.venv/bin/python -m pytest`.

## Final offline reconciliation before owner review — 18.11.2026

This snapshot supersedes the earlier counts above: 24 current KB-file changes (6 body/list; 18 front matter), 200 unchanged / 69 changed current card hashes against the frozen baseline, and 662 claim-evidence rows. All 29 report CSVs parse with consistent widths (3,838 data rows). `card_review.csv` remains 269 rows / all overall `warning`; SME requirement is 267 true / 2 false / 0 unverified. P1-83 is closed without article rewrite after direct confirmation of the email-only registration flow; its source check date was updated and `verified_at` preserved. P1-80/81/82/84/85 remain source-unverified because their pages show only headings/navigation.

Final offline checks: real DocumentLoader/Chunker 269/269 / 1,168 chunks; candidate validator 52/52 / 209 chunks / unique IDs and hashes / zero errors or warnings; baseline verifier 269/269 historical hashes; coverage references 93/93 resolve; targeted pytest 25 passed; `git diff --check` clean. No runtime, LIVE, production data/index, `.env`, main branch, or common project-state files changed.

Publication state: existing draft PR #4 still points to remote head `f12ad8200ba6fd7170d7bf3d06d75f278c42801b`, not the local worktree. GitHub compare returned 404 for local HEAD, and `git fetch origin feature/kb-review-b2` could not resolve `github.com` in this environment. The draft PR was not modified or falsely presented as containing these local changes. Current worktree/report artifacts are prepared for review; remote publication remains pending restored network access and a branch-history check.
