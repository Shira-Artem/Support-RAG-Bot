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
