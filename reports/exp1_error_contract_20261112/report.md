# Experiment 1 — unified incident error-code contract

**Status: offline PASS; real A/B incomplete and blocked by Stage3 availability.** This report describes the isolated `codex/exp1-error-contract` worktree based on `fce09b4`. It does not approve production or a merge.

## Defect and implementation

The semantic Understanding schema had no error-code evidence field. A provider could return `error_code=ФН 234`, but `_find_span` rejected a casing difference in its proposed quote; validation then did not copy an error into `Observation`, and the reducer therefore left `DialogueState.error` empty. A parallel lexically extracted number was not used by the semantic path. The gate consequently treated a confirmed code as unconfirmed.

The opposite defect was a split applicability contract: code-specific article checks ran after the technical Planner, but the informational Composer path and its exact-evidence fallback could return a source-specific code without a client-confirmed code. The insufficiency fallback could also exit before those checks.

The fix is limited to the existing paths:

- `app/dialogue_understanding.py` extracts only positive incident-code mentions from the current client message, stores the exact numeric `Fact` span and `message_id`, and serializes/revalidates that typed observation. Candidate spans come from the client text, not a model quote; the model quote may differ in casing. Standalone definition questions, negated/corrected mentions, bot-attributed mentions, and unrelated model/version numbers are excluded.
- `app/dialogue_state.py` keeps all current-task error-code facts, refreshes their span when the same code is reconfirmed, supersedes prior codes after a correction, and clears them on a new task. The existing single `error` projection remains for older consumers. The additive SQLite field is optional on read; legacy snapshots containing only `error` still load.
- `app/rag_query.py`, `app/source_first_service.py`, and `app/semantic_evidence_selector.py` pass and check all confirmed codes. The same `_source_error_matches_client` contract now applies before insufficiency fallback, before informational composition/exact fallback, and after technical Planner selection. A standalone “Что означает ФН 231?” remains an explanation request.
- No Qdrant data, approved KB, main branch, or production defaults were changed. Existing dangerous-operation and source safety gates remain in place.

## Frozen final-answer comparison

The A text and live metrics below are the **archived 2026-11-09 run** on the code baseline, not newly generated controls. The frozen inputs and answers are recorded in the audit reconstruction at [commit `1e21920`](https://github.com/Shira-Artem/Support-RAG-Bot/blob/1e21920d3569d9dd9e007812e1a8bd6349c21b5a/reports/architecture_investigation_20261112/turn_reconstruction.md). B below is the offline full SourceFirst answer path with local approved articles and a deterministic offline Planner response; it is not a Groq/Qdrant live result.

| Case | A — archived `fce09b4` final answer | B — frozen offline final answer | Offline finding |
|---|---|---|---|
| D04-T01: “На моей кассе Эвотор появилась ошибка ФН 234. Обязательно менять накопитель?” | “Нашёл инструкцию для другого конкретного кода ошибки, поэтому не буду переносить её на ваш случай. Какой текст или код ошибки отображается на кассе?” Source: approved FN 234 was retrieved, then rejected because `state.error` was empty. Groq: 4,890 successful tokens; 2,293 ms. | “Статья производителя связывает код ФН 234 с ресурсом фискального накопителя. До вывода о замене предлагается проверить, правильно ли выставлены дата и время на кассе: неверное время может создать ложное впечатление, что срок ФН завершился.\n\nИсточник: data/knowledge/evotor/fn/fn-234.md — Первое различение причины” | Correct approved article admitted. No replacement recommendation; source leaves archive closure and replacement to a trained specialist. |
| D04-T02: “кассе Эвотор появилась ошибка ФН 234” | Same false “другого конкретного кода” clarification. Source: `fn-234.md`. Groq: 4,320 successful tokens; 2,636 ms. | Same approved first-distinction answer as T01. The code survives the follow-up turn with the new exact client span. | No false unknown-code rejection after continuation. |
| D03-T02: “После продажи касса иногда ругается, но я не успеваю прочитать ошибку.” | “Область источника: Эвотор.\nКод на чеке — ФН 231; на экране может появляться -3975.\n\nИсточник: data/knowledge/evotor/fn/fn-231.md — Контекст ошибки” Groq: 5,741 successful tokens; 20,569 ms. | “Что именно перестало работать — печать чека, передача данных или другое? Если появится точный текст на экране, пришлите его.” | No unsupported FN 231/-3975 diagnosis. The answer asks a useful symptom question. |

The archived A rows are real historical end-user responses. B rows are reproducible offline replay tests; they do **not** constitute the requested paired real A/B. Live latency, token usage, and provider checks for B are not available.

**Offline comparison:** B is more useful on both target failures: D04 gets the approved first check and avoids a premature replacement; D03 avoids assigning FN 231 to the client and asks about the failed function. No worse final answer was observed in these frozen offline cases. “Equal” is not claimed, and broad equivalence is not measured.

## Additional formulations and negative controls

Offline regression coverage includes:

- New positive wording: “Касса Эвотор пишет ошибку ФН 234…”, “Касса показывает ошибку ФН 231, а не 234”, “Не ФН 231, а ФН 234 — касса пишет именно его”, and “Нет, я ошибся: не ФН 231, а 234”. The corrected/positive code is the only code retained.
- Multiple client-reported codes remain individually typed and task-bound; a repeated code gets the latest exact span. A new Диадок task does not inherit the prior cash-register code.
- Negative controls: another code in the approved article; negated FN 231; a bot-attributed FN 231 quotation; version `3.234`; model `7.3`; standalone “Что означает ФН 231?”; and a new topic.
- SQLite reopen preserves value and source message identity. A legacy schema-v2 snapshot with only `error` remains readable.
- Dangerous fiscal-data requests still hit the existing independent safety gate. Existing source integrity, applicability, procedure, and unsafe-operation tests remain in the regression set.

## Verification and live A/B status

Offline targeted suites passed: **179 passed** across Understanding/state/SQLite, semantic evidence selection, SourceFirst final-answer paths, Coordinator, and scope policy. `py_compile` and `git diff --check` passed. Frozen D04-T01/T02 and D03 SourceFirst answer replays pass.

One wider task-lifecycle suite had **6 passed / 1 environment failure** when a pre-existing test imported `bot.py` and attempted the default Qdrant collection at `127.0.0.1:6333`; the connection was refused. Docker Desktop was not running and failed to start (`Docker Desktop is unable to start`). The existing `.env` points Stage3 at that local endpoint; no current collection health or point count could be verified. The audit’s 934-point receipt is historical and was not treated as current evidence.

As a result, **no Groq question calls were made** and there are no new A or B live end-user responses, source checks, latency numbers, or token counts. This was deliberate: a model-only call or replacement/empty Qdrant would not meet the requested full pipeline and would not produce a real comparison. Groq key/model configuration is present (`openai/gpt-oss-20b`), but the real Stage3 dependency is unavailable. No 429 was observed; A/B is still incomplete for the Qdrant failure.

## Remaining risks and decision

The local phrase grammar is intentionally small. Broader natural-language code forms and incidence rates remain unmeasured. This change repairs the reproduced D04 loss and closes the D03 source-specific information/fallback bypass, but the D03 full live trace has not been rerun. Other false refusals and unsupported claims outside error-code applicability are not assessed here.

**Recommendation: keep the change experimental and complete the identical live full-pipeline A/B before accepting it.** Once the existing Stage3 runtime is available, run A from `fce09b4` and B from this branch with the same approved KB, Groq GPT-OSS 20B parameters, and separate SQLite/work directories. Do not merge to main or declare production GO from the offline result.
