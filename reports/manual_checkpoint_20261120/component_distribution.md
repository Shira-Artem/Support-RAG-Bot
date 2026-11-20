# Распределение ошибок по компонентам

Подтверждённые первичные причины 15 FAIL ручной сессии; PARTIAL отдельно в матрице.

| Компонент | FAIL | Ходы |
|---|---:|---|
| Transport | 1 | M01 |
| Selector | 2 | M02, M15 |
| General relevance/grounding | 3 | M05, M08, M21 |
| Planner/source order | 1 | M09 |
| Retrieval/task projection | 2 | M10, M11 |
| Understanding/resolver | 1 | M12 |
| DialogueState/readiness | 1 | M13 |
| Composer/relevance | 1 | M16 |
| Ledger/continuation | 2 | M18, M19 |
| Intake | 1 | M24 |

У Coordinator в этих 15 ручных FAIL самостоятельная первичная причина не доказана. В новых социальных LIVE выявлено сочетание routing/eligibility: information/general/unknown отправляется в grounded_information, model-only допускает только explain; greeting вместо информации даёт пустое по смыслу приветствие. [Точные три варианта](social_routing_failure.json). Это не отсутствие KB.

Для LIVE ниже подсчитано **место финального отказа**, а не автоматически установленная первопричина:

| Вариант | Отказ / reason | Число FAIL |
|---|---|---:|
| baseline | selected_error_code_unconfirmed | 2 |
| baseline | unsafe_operation | 1 |
| baseline | source_first_exact_section | 3 |
| baseline | dialogue_state_task_incomplete | 8 |
| baseline | no_applicable_source_missing_client_detail | 1 |
| baseline | semantic_composer_irrelevant_evidence | 4 |
| baseline | insufficient_applicable_evidence | 4 |
| baseline | general_knowledge_fallback | 2 |
| baseline | applicability_context_missing | 1 |
| baseline | progress_ledger_check_result_needed | 1 |
| baseline | progress_result_unresolved | 1 |
| baseline | source_scope_context_still_missing | 1 |
| baseline | understanding_failed | 2 |
| baseline | progress_ledger_conditional_context_unknown | 1 |
| baseline | error_code_scope_unconfirmed | 1 |
| candidate_pre_safety | dialogue_state_task_incomplete | 3 |
| candidate_pre_safety | selected_error_code_unconfirmed | 1 |
| candidate_pre_safety | unsafe_operation | 1 |
| candidate_pre_safety | source_first_exact_section | 3 |
| candidate_pre_safety | semantic_composer_relevance_grounding_failed | 3 |
| candidate_pre_safety | insufficient_applicable_evidence | 3 |
| candidate_pre_safety | semantic_selector_failed_closed | 2 |
| candidate_pre_safety | source_first_social_turn | 2 |
| candidate_pre_safety | general_knowledge_fallback | 5 |
| candidate_pre_safety | planner_could_not_select_safely | 1 |
| candidate_pre_safety | error_code_scope_unconfirmed | 2 |
| candidate_pre_safety | applicability_context_missing | 1 |
| candidate_pre_safety | progress_ledger_check_result_needed | 1 |
| candidate_pre_safety | progress_result_unresolved | 1 |
| candidate_pre_safety | understanding_failed | 1 |
| candidate_pre_safety | progress_ledger_conditional_context_unknown | 1 |
| candidate_pre_safety | semantic_selector_no_evidence | 1 |
| old_kb_pre_safety | dialogue_state_task_incomplete | 5 |
| old_kb_pre_safety | selected_error_code_unconfirmed | 2 |
| old_kb_pre_safety | unsafe_operation | 1 |
| old_kb_pre_safety | no_applicable_source_missing_client_detail | 1 |
| old_kb_pre_safety | semantic_selector_no_evidence | 2 |
| old_kb_pre_safety | insufficient_applicable_evidence | 4 |
| old_kb_pre_safety | progress_ledger_waiting_for_model | 1 |
| old_kb_pre_safety | semantic_selector_clarification | 1 |
| old_kb_pre_safety | planner_could_not_select_safely | 1 |
| old_kb_pre_safety | semantic_selector_validation_rejected | 1 |
| old_kb_pre_safety | source_first_exact_section | 3 |
| old_kb_pre_safety | applicability_context_missing | 1 |
| old_kb_pre_safety | semantic_composer_irrelevant_evidence | 3 |
| old_kb_pre_safety | grounded_section_followup_exhausted | 1 |
| old_kb_pre_safety | selected_evidence_does_not_cover_symptom | 1 |
| old_kb_pre_safety | source_scope_context_missing | 1 |
| old_kb_pre_safety | general_knowledge_fallback | 1 |
| safety_patch_round1 | applicability_context_missing | 1 |
| safety_patch_round1 | insufficient_applicable_evidence | 2 |
| safety_patch_round1 | semantic_composer_irrelevant_evidence | 1 |
| safety_patch_round1 | dialogue_state_task_incomplete | 2 |
| safety_patch_round1 | dialogue_task_remains_undefined | 1 |
| safety_patch_round1 | source_scope_mismatch | 2 |
| safety_patch_round1 | general_knowledge_fallback | 1 |
