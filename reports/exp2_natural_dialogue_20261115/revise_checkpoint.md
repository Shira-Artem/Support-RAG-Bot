# Experiment 2 Part A — targeted REVISE checkpoint

Date: 2026-11-15. This is the outcome of the owner-authorized correction iteration on local `main`, starting at `0661cc8357a9f50152b388a593d653ede68adb7f`. The tracked tree was clean at start; the pre-existing untracked `.worktrees/` directory was left untouched. No KB files, Qdrant data, production worker, or Part B/Experiment 3 work were changed.

## Evidence reviewed and overlapping causes

Read in full: [Hubris Part A checkpoint](hubris_checkpoint.md), [parallel LIVE QA report](../../.local/exp2_parallel_qa/report.md), its `summary.json`, and all four UTF-8 batch records plus `hubris_http_trace.jsonl`.

The independent QA and A/B symptoms overlap; they do not represent separate root causes:

1. **Evidence eligibility and final selection were not bound tightly enough to the customer's current task.** In D08, the reducer held the task as `general/diagnose`, with a document-not-visible symptom, and retrieval ranked several `edo` candidates. Planner selected `epd-vs-edo.md`; the former technical relevance check did not cover the `edo` category and relied on `state.object`, which was empty. A neighboring article could pass the last subject check. Related QA traces also show false refusals when approved candidates were surfaced only after rephrasing; these are upstream retrieval/eligibility issues and not multiple independent defects.
2. **Planner's section identifier was an ambiguous reference contract.** D07 had the correct approved Evotor 7.3 article among already-verified candidates, but an earlier Planner response returned its document ID without `::section`. Exact membership then conservatively refused it. This was separate from cases where Understanding/DialogueState did not establish a retrieval-ready task at all.
3. **Clarification state was persisted but not enforced at the final response boundary.** D03 traces show `ExpectedClarification` and `clarification_repeats` survived SQLite reopen, while a generic incomplete-task path could repeat the exact prompt. On later turns the task remained unresolved because the current Understanding/reducer state did not retain a usable symptom; after bounded clarifications, escalation is appropriate.

## Changes and measured outcomes

### 1. D07 section reference

Added `_resolve_planner_section_reference` in `app/source_first_service.py`. It accepts an exact candidate section ID, the existing exact eligible-unit/source-section identity, or a document ID only when exactly one Planner candidate section belongs to it. Zero or multiple matches remain rejected. All candidates were already passed through approved status, source hash, customer scope and retrieval checks; downstream membership, source order, and safety gates are unchanged.

Offline positive/negative regressions cover unique document-ID resolution, ambiguous multi-section rejection, unvetted references, and exact IDs. In real Hubris LIVE, seven distinct D07 inputs were run: five returned the same safe first step from `evotor/ofd/evotor-7-3-ofd-connection.md` / “Что проверить сначала”; two paraphrases were stopped earlier by incomplete task/scope clarification before Planner selection. Thus the section path is confirmed useful, while paraphrase robustness before retrieval is not complete. No arbitrary section was selected.

### 2. D08 evidence relevance

Expanded `_technical_section_covers_observed_subject` to use reducer-owned object, symptom, task fact, object reference and goals. Confirmed service/software/entity names and generic domain terms do not by themselves count as evidence that a section covers the user's target. The check is a negative relevance gate; it does not prove an overlapping article solves the task. No product-specific regex or new model call was added.

In the final D08 LIVE run, the former `epd-vs-edo` selection was rejected with `observed_subject_absent_from_selected_evidence`; the existing bounded reselection chose `connect-1c-edo::Что уточнить перед инструкцией`, but Planner did not confirm source-order completeness, so the bot escalated. Similar LIVE wording returned an honest approved-KB gap. The previously observed EPD-vs-EDO customer answer was not emitted in these revised runs. This removes the irrelevant answer; it does not establish that the KB contains the missing document-visibility procedure.

### 3. D03 clarification loop

Incomplete-task clarification now selects a saved generic prompt not already present in clarification history and excludes the retained `ExpectedClarification.question`. A final response-boundary guard applies the same rule if a caller supplies incomplete history. If no new safe prompt remains, it escalates. This uses `ExpectedClarification`, history and existing `clarification_repeats`; it adds no domain-specific rules.

Offline coverage verifies choosing a different prompt and stopping after candidates are exhausted, plus a final-boundary regression. In final Hubris LIVE D03, turn 2 changed from the turn-1 question to “Какой результат вы хотите получить?”; turns 3–4 escalated without asking either prompt again. SQLite reopen equality held on all 4 turns. The underlying task was still not extracted reliably, so this repairs the repeated question but does not turn the dialogue into a resolved technical answer.

## Reopened 12-scenario QA and controls

The earlier QA was used to choose fixes, so it is **not** an independent holdout here. Its 12 scenarios (25 user turns) were replayed against the revised runtime with the original messages. New D07/D08 paraphrases and D01/D03/D04/D05/high-risk controls were also run.

| Measure | Earlier QA | Revised 12-scenario replay | Assessment |
|---|---:|---:|---|
| Useful self-contained answers | 3 | 3 | No increase on this QA set |
| False-refusal turns | 5 | 5 | No measured reduction |
| Problematic/wrong articles | 6 | 2 | Improved; OFD→FN and FN→FN18 carry-over remain |
| Unjustified clarification turns | 7 | 5 | Improved, but task-understanding cases remain |
| Dangerous answers | 0 | 0 | Safety preserved |
| HTTP provider errors | 0 | 0 | All captured HTTP calls returned 200 |
| Provider calls / tokens | 27 / 32,851 | 27 / 33,822 | Revised: 24,916 prompt + 8,906 completion |
| Hubris reported cost | 36 kop | 42 kop | Revised QA only |
| Summed turn latency | 138.621 s / 25 | 151.147 s / 25 | Mean 6.046 s vs 5.545 s |
| SQLite reopen equality | 25/25 | 25/25 | Preserved |

The counts use the same turn-level categories as the earlier report and manual review of saved final answers. The revised set includes repeated OFD explanation instead of the FN answer, and an unrelated aQsi FN18 answer to the general FN question. The FN235/Oracle control again gave no reset/menu instructions or invented phone number; the high-risk archive-close control escalated safely. D01 acknowledged the confirmed internet result and asked only for exact model on the final turn, but an earlier turn mentioned EoU without the customer reporting it. This remains an unsupported neighboring detail.

Three LIVE calls ended in local `ConnectError` before any HTTP response; those attempts have zero recorded provider usage. The harness stopped each affected batch, no automatic retry was made. Subsequent bounded runs completed; the final 12 QA scenarios completed all 25 turns. The additional D01 run completed all three turns. Across all saved LIVE artifacts for this correction iteration: **198 kopecks reported (1.98 ₽), 128 HTTP 200 calls, 198,923 total reported tokens, 0 HTTP errors, and 3 pre-HTTP transport errors**. The failed attempts are not billed according to captured usage; no hidden provider charge is inferred.

All raw new answers, usage and per-turn traces remain in ignored `.local/exp2_revise_*.json`; the two D07 target batches are `exp2_revise_target_live_retry.json` and `exp2_revise_core_live2.json`. No secrets are included.

## Decision

**REVISE — Part A is not accepted.** The targeted changes reduce irrelevant evidence selection and question repetition while preserving the tested safety controls. The reopened QA did not increase useful answers or reduce false refusals, and D07 remains uneven before Planner selection. The remaining variability spans Understanding/reducer readiness, retrieval eligibility and source relevance. Resolving it fully would need a broader contract/evaluation change; this iteration does not mask it with more phrase-specific rules. Part B and Experiment 3 remain unstarted.

Next step: owner review of this Part A revision scorecard. Keep production quality status NO-GO; do not start Part B or Experiment 3 without separate approval.
