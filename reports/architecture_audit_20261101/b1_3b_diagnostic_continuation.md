# B1.3b — Diagnostic Continuation

## Scope and current-state audit

Only B1.3b was evaluated. Baseline repository: `02e604f` (B1.3a GO); working tree clean at start. Reviewed `AGENTS.md`, current plan/state, [B1.3a report](b1_3a_progress_memory.md), and the live JSON/SQLite checkpoints referenced there.

Path inspected: `_reduce_progress` writes `TaskContext.checks`; `task_frame` projects checks and task facts; deterministic `coordinate()` creates `current_subgoal` from the current validated goal and routes technical tasks to retrieval; `ConversationStore.progress_summary()` exports eligible/shown unit labels and statuses; SourceFirst uses `_verified_continuation_section()` to let the planner prefer the same source; planner sees task state and may select/clarify/escalate; renderer either emits a next approved unit or renders the selected section. `procedure_id` is the document ID; `shown_units` are actually published instructions; `eligible_units` are units extracted from the approved section; `checks` are outcome records.

The real B1.3a traces prove a concrete renderer defect. In [S1 negative](b1_3a_live_s1_negative_20261103.json), the queue unit `7ecc73b5ecb8e7125d80` becomes `failed`, while the first unit remains `passed`. SourceFirst continuation considered any status other than `passed` pending and selected the same approved section. The next-unit fast path only ran when the last shown unit was `passed`; a `failed` unit fell through to the normal renderer, which printed the whole section again. The [partial result trace](b1_3a_live_s1_partial_20261103.json) likewise returned the full section after a useful partial result left the compound unit `unknown`. The stored progress was available; answer selection failed to turn it into a focused question.

This is distinct from source coverage. The approved Evotor 7.3 article contains initial diagnosis, conditional internet/settings/queue checks, and a support boundary; it does not specify a new diagnostic action after those baseline checks fail to identify the cause. Inventing such a step would cross the evidence gate (B2). `current_subgoal` captures “What next?” but does not add source evidence.

## Independent matrix and baseline

Cases use the actual verified units and real B1.3a SQLite snapshots. Before the fix, the saved traces and source flow establish the baseline for cases 1, 3, 4, 6 and 8; the remaining status/model controls are existing ProgressLedger regression cases, not fabricated sources.

| Case | Snapshot/state | Expected continuation |
|---|---|---|
| 1. Action proposed, result unknown | `P=asked` | Ask for the result; do not advance or repeat instructions |
| 2. Action completed successfully | `P=passed` | Choose the next ordered applicable unit from the same verified source |
| 3. Negative result | `P=passed, C=failed` | Preserve negative evidence; do not replay section; request missing conditional outcomes or select an explicitly supported branch |
| 4. Partial compound result | `C=unknown` with client quote | Ask only for unresolved outcomes; do not mark whole unit passed or reprint its actions |
| 5. Client correction | `P observations=[passed,failed]`, current `failed` | Use latest outcome while retaining contradiction history |
| 6. All available units checked, symptom remains | All source units non-asked with outcomes | Use an explicit approved terminal path, otherwise state source boundary / specialist; invent no step |
| 7. Model changed | New confirmed model differs from model-scoped units | Reject/defer incompatible units and retrieve only source applicable to current confirmed model |
| 8. Selected article has no next step | Current section exhausted or scope mismatch | Clarify within supported facts or escalate; no unsupported action |

## Minimal fix and deterministic verification

Changed only SourceFirst's handling of a verified failed compound unit: keep its `failed` outcome and quote, then ask for the remaining outcomes from that same check before choosing the source's conditional branch. The reply names the already reported negative result and does not repeat the source section or claim that a new action is approved. It does not alter retrieval, evidence admission, the planner, KB, TaskFrame schema, reducer, or any earlier B1 stage.

Targeted replay before live: `python -m pytest -q tests/test_telegram_pilot_sqlite_replay.py -k 'progress_ledger or compound_results or source_order'` — **12 passed, 30 deselected**. Existing tests verify asked vs passed, ordered next units, compound unknown/conditional boundary, source hash/context receipt and SQLite reopen. The new live result below adds an end-to-end check of the failed-composite question.

## Real Groq E2E and stop condition

Used real `bot.handle_message`, current Groq model `openai/gpt-oss-20b` / medium, current settings, read-only Stage3 and isolated SQLite resumed from the B1.3a real post-report checkpoint. No instructions were injected. [Full trace](b1_3b_live_s1_20261103.json) records HTTP attempts, raw and validated Understanding, frame/state before and after, selected source/unit diagnostics, actual answer, and SQLite reopen. Sequence began from a real checkpoint where P was already `passed` and C was `asked`, then sent the two requested final turns:

| Turn | Client message | State/result | Actual answer / HTTP |
|---|---|---|---|
| 1 | «Очередь неотправленных документов не уменьшается.» | `task:1`; P remains `passed`; C becomes `failed` with exact client quote; SQLite equal. Raw/validated Understanding continues the same Evotor task. | «Зафиксировал отрицательный результат („Очередь неотправленных документов не уменьшается“). Какие результаты показал отчёт по остальным пунктам этой проверки? После этого выберу следующую применимую ветку инструкции.» No repeated section. 2×HTTP 200. |
| 2 | «Что делать дальше?» | State remains persisted; no new check is marked shown. Raw/validated Understanding remained within task. | Planner request returned HTTP **429** (`rate_limit_exceeded`, `tokens`). Pipeline stopped without retry; safe provider error answer: «Не удалось проверить источник из-за внутренней ошибки. Повторите позже или запросите специалиста.» Trace records 2 additional HTTP attempts, last 429. |

Total live budget consumed: **4/24 HTTP attempts: 3×200, 1×429**. Stop-on-429 was followed. Both turns have `sqlite_roundtrip_equal=true`. Scenario 2 (ambiguous “Проверил” → explicit positive result → next action) was not sent after the 429; there is no live evidence for it in this run. Prior B1.3a scenario 2 is not a substitute because it tested memory correction, not next-step selection.

## Decision

**B1.3b NO-GO / LIVE INCOMPLETE.** A real regression is fixed and live-confirmed: a failed composite check now prompts for missing outcomes rather than replaying the full section. The full continuation contract is not proven: provider quota stopped the first scenario at the “what next” planner decision, and the second scenario was not run. The source itself also has no later action after its conditional support boundary; that remains a B2 coverage limitation and is not bypassed. Full `python -m pytest -q`: **628 passed, 4 xfailed, 14 warnings, 0 failed**; targeted ProgressLedger/source-order replay: **12 passed, 30 deselected**. B1.4/B1.5/B2 were not started. No commit/push/pull/reset was run.

## Follow-up on the final local B1.3b code — 2026-11-03

This section supersedes the earlier live summary above for the current local snapshot. The initial follow-up Groq trace below was run before the last local corrections; it remains evidence about the quota stop and the bug it exposed, not a live verification of the final local code.

### Local diagnosis and correction

The initial failed-result branch used a broad status check and could ask about “other points” even for a single check. The final implementation gates that question on source-derived `components` from exact, hash-verified approved instructions. The structural metadata is persisted with the existing shown/eligible/check records in `TaskContext`; no new memory store or schema was added. Atomic checks continue to the next ordered approved step, or escalate honestly when the verified source has no next step.

Reviewing the follow-up trace exposed two more defects in the legacy SQLite path. First, a component backfill attached to a clarifying answer was discarded because `ConversationStore` persisted progress only for generated answers. Second, a short token in “в нём” falsely matched the component about EoU/internet/address/port, which hid that unresolved component. A later settings result could also be attributed to an earlier check because that earlier unit contained the word “Настройки” in its menu path.

The correction persists only metadata and component observations for exact, already-shown checks from the same task and verified source; it does not add new shown checks. Component matching considers only published checks, filters out short accidental tokens, retains source clause coverage as `unknown` when the client has reported only part of that clause, and does not assign the same client result to an unrelated earlier unit. This was exercised by removing the new fields from an isolated SQLite snapshot before the negative-result turn, then checking the clarification, result attribution and SQLite reopen.

### Automatic verification on the final local snapshot

- `tests/test_b1_3b_diagnostic_continuation.py`: **6 passed**. Coverage includes failed composite and atomic checks, missing quote, exact quotes across SQLite reopen, legacy-checkpoint metadata backfill, approved conditional boundary, and task/model isolation.
- Focused regression command covering the B1.3b cases and existing source-order, saved-live replay, payment, handoff and model-switch cases: **11 passed, 37 deselected**.
- Final `python -m pytest -q`: **634 passed, 4 xfailed, 14 warnings, 0 failed**. This includes B1.1, B1.2 and B1.3a regression coverage. Warnings remain the existing Qdrant client/server version warning and LangSmith deprecations.

### Bounded Groq follow-up and stop

Used the real `bot.handle_message`, Groq `openai/gpt-oss-20b` / medium, read-only Stage3 (`knowledge_stage3_retrieval_20261022`, 934 points), and an isolated SQLite backup from the saved B1.3a checkpoint (`P=passed`, `C=asked`). No production worker or production SQLite was used. [Raw follow-up trace](b1_3b_live_s2_20261103.json) records the actual user inputs, responses, checks, provider status and SQLite round trips.

The follow-up run was capped at 8 HTTP attempts. It used **4 actual HTTP attempts: 3×200 and 1×429**. On the first negative result, Groq kept the same `task:1`; the queue failure and exact user quote survived SQLite reopen, and the answer did not repeat the whole section. That intermediate response asked only about the address/port/INN clause. The saved state did not yet contain component metadata. The next input reported the address/port/INN result; Understanding returned 200, then the Planner returned HTTP **429** (`rate_limit_exceeded`, `tokens`). The request guard stopped the SDK retry before another network request. There were no further HTTP calls and no key switching.

Inspection of that trace found the legacy-backfill and attribution defects described above. They were corrected locally and covered by the final offline suite, but the 429 stop rule prevented any further live request in this run. Therefore the trace does **not** verify the final component question or attribution. Scenario A did not reach the “Что делать дальше?” answer, and scenario B (“Проверил.” → explicit positive outcome → next approved action) was not run. The initial trace [b1_3b_live_s1](b1_3b_live_s1_20261103.json) is also historical; it cannot substitute for either scenario on the final code.

### Current decision and next step

**B1.3b remains NO-GO / LIVE INCOMPLETE.** The final local behavior and regression coverage pass, but neither required full Groq scenario is complete on the final local code. The approved Evotor source still ends at a support boundary and adds no later diagnostic action; the bot must retain that boundary rather than invent a step. After quota is available under a separate budget, resume only B1.3b from the clean B1.3a checkpoint after P passed/C asked and the separate “Проверил” checkpoint; do not resume the intermediate follow-up SQLite state that exposed the old false attribution. Keep the combined cap at 12–16 actual HTTP attempts and stop at the first 429. Do not start B1.4, B1.5 or B2.

### Offline audit of source action boundaries and conditional branches — 2026-11-03

No Groq/API request was made for this offline audit. Review covered `source_first_service.py`, `dialogue_state.py`, `response_grounding.py`, the B1.3b tests, and the exact approved sections in the three requested aQsi/Evotor articles.

The source-unit actionable regex and the diagnostic-component regex previously used different verb lists. Approved text uses «убедитесь» and «сравните», so units could be extracted without a matching component. A shared vocabulary now covers «проверьте», «сверьте», «сопоставьте», «посмотрите», «убедитесь» and «сравните» forms across unit extraction, component extraction, progress terms, source-component backfill and response grounding. Other procedure verbs such as «откройте», «нажмите» and «передайте» still make a source sentence actionable but do not themselves form a diagnostic component. Component labels begin at the verification action, stop before the next source action, and do not include a neighboring instruction. Tests use the actual approved goods, FN7 and FN235 sources; they check repeatable component IDs, bounded labels, singleton checks and SQLite reopen.

Result attribution had a separate neighboring-unit risk: broad terms such as «касса» or «магазин» could match several source checks. The reducer now prefers the most specific matching shown check. It may attach a volunteered result to an unshown eligible check only when no shown check matches and the quote uniquely identifies that source unit. Equal/ambiguous matches are left unresolved; broad procedure records retain partial status without duplicating the result onto a narrower check. Offline regressions cover both an explicit later Evotor internet result and an aQsi reply that must remain on its shown check.

The deterministic Evotor 7.3 matrix runs through `bot.handle_message` and SQLite reopen: internet absent selects only the approved network branch; internet present does not select network recovery; EoU failure with working internet does not select that recovery branch; unknown/contradictory internet status asks; explicit address/port/INN mismatch reports that the source has no corrective step and offers a specialist without repeating a question or claiming the conditional support boundary; and a failed queue after successful base checks reaches the exact approved support boundary. Planner remains in the path. Old SQLite metadata backfill and task/model isolation are also covered.

The first combined regression run caught a false attribution when the same client phrase contained generic terms from neighboring aQsi checks. That attempt failed; the matching rule was narrowed to shown-first, most-specific matching with a unique eligible fallback. A full regression run also caught a source-unit boundary regression where a precondition beginning «Перед… убедитесь» became a standalone unit; preconditions now stay attached to the next action. The focused B1.3b/source-contract replay after that correction passed (**17 passed**). Final `python -m pytest -q`: **644 passed, 4 xfailed, 14 warnings, 0 failed**. The warnings are the existing Qdrant client/server compatibility warning and LangSmith deprecations. `py_compile` and `git diff --check` passed. This offline evidence does not replace live Groq continuation.

**Decision remains B1.3b NO-GO / LIVE INCOMPLETE.** The next step is still the two bounded Groq continuation scenarios on the final code after quota is available; stop on the first 429. Do not start B1.4, B1.5 or B2.

### Follow-up: compact Planner input, unresolved checks, and live quota — 2026-11-03

- **Planner prompt size.** The full serialized `DialogueState` duplicated session/task facts, spans, source-order receipts, and long eligible-unit copies. Planner now receives a read-only compact projection containing task scope, route, source-unit IDs, bounded labels, component IDs, and exact check observations/outcomes; SQLite and reducer storage remain complete. Reconstructing the prior rejected request gives **9,212 → 5,999 conservative estimated tokens**. The successful live Planner request was estimated at **6,168** including its configured completion allowance; Groq reported 3,018 prompt and 324 completion tokens.
- **Live evidence.** [The compact-input follow-up](b1_3b_live_final6_s1_20261103.json), resumed from an isolated B1.3b SQLite snapshot on `GROQ_API_KEY_2`, completed Understanding and Planner (**2×HTTP 200**), kept the same task and round-tripped SQLite exactly. Its response issued the next conditional check while a previously shown check remained `unknown`. This trace predates the local unresolved-check clarification added immediately afterwards; it does not verify that clarification.
- **Final local behavior.** When a shown check remains `asked`/`unknown`/`not_done`, the renderer now retains that check as active before issuing a later conditional action. Source-condition and missing-model questions keep their more specific handling. A new SQLite replay reproduces an unknown shown check with a known internet condition and verifies the later instruction is held. Related regression suite: **118 passed, 4 xfailed**; full `python -m pytest -q`: **651 passed, 4 xfailed, 14 warnings**; `compileall` and `git diff --check` passed.
- **Provider rate limit.** Starting the bounded continuation from the clean B1.3a checkpoint, the primary profile received `429 rate_limit_exceeded` / `type=tokens` on the first Understanding request with `Retry-After: 165`; after the owner asked to try the other configured organization, its first Understanding request also received 429 with `Retry-After: 139`. The responses still exposed 8,000 TPM remaining and a 1 ms TPM reset, so the exact limiting window is not identified by those headers. The failed attempts are preserved in [primary trace](b1_3b_live_final7_s1_20261103.json) and [second-profile trace](b1_3b_live_final8_s1_20261103.json). Across the B1.3b continuation files, the observed total is **16 HTTP attempts**; no request was sent after either 429 in its run.
- **Quota handling and gate.** Groq documents multiple limit dimensions and organization-level enforcement; its current acceptable-use policy explicitly prohibits coordinating usage across organizations to evade published limits. Therefore the user's requested cross-organization fallback is not used after 429. Any future live continuation must wait for the selected organization's `Retry-After` and resume on that same organization; no further calls are made while the cooldown is active. [Rate-limit documentation](https://console.groq.com/docs/rate-limits), [acceptable-use policy](https://console.groq.com/docs/legal/ai-policy).

**B1.3b remains NO-GO / LIVE INCOMPLETE.** The compact Planner request has live 200 evidence, but the required final S1 and S2 continuations have not both completed on the final code. The last two attempts stopped at Understanding before Planner. Continue only B1.3b after the selected organization's cooldown; do not start B1.4, B1.5, or B2.

### Single-organization retry after `Retry-After` — 2026-11-03

After waiting the first primary profile's 165-second `Retry-After`, a same-profile S1 retry reached Understanding (HTTP 200; usage 2,245 prompt / 487 completion) and then Planner returned HTTP 429 `type=tokens`, `Retry-After: 1046`. Headers showed 5,605 TPM remaining and an 18-second TPM reset. The local conservative request estimate did not pre-block it; no further request followed the 429. [Full trace](b1_3b_live_final9_s1_20261103.json). Across all continuation attempt files, the count is now **18 HTTP attempts**; no retry was sent after any 429.

The Planner's previous `max_completion_tokens=1024` reserved more room than its strict short JSON output needs. The local Groq client now reserves **512** for `call_stage="planner"` and keeps 1,024 for other stages. The exact failed Planner input estimates 5,012 tokens with a 1,024 completion allowance and 4,499 with 512; this is a local estimate, not proof of which provider quota caused the 1046-second cooldown. Regression coverage verifies the stage-specific reservation. After this change, full `python -m pytest -q`: **652 passed, 4 xfailed, 14 warnings**; `compileall` and `git diff --check` passed. The 1046-second cooldown applies to the primary profile; no other organization is used to evade it. Wait for this exact `Retry-After` before any further request on this profile.

**Gate remains NO-GO / LIVE INCOMPLETE.** Scenario A was still stopped before a Planner decision in this latest retry; scenario B remains unrun on the final local snapshot. Offline evidence is complete for this code revision, but the final live gate cannot proceed until the selected profile's provider cooldown expires. Continue only within B1.3b.
