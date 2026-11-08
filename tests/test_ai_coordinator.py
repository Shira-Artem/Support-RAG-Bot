from pathlib import Path

from app.ai_coordinator import coordinate
from app.config import Settings, should_use_ai_coordinator
from app.dialogue_state import DialogueManager, DialogueState, Fact
from app.dialogue_understanding import validate_response
from app.source_first_service import (_bounded_support_intake,
    _source_error_matches_client)


def _state(text: str, raw: dict):
    kind, _specialist, unknown, observation = validate_response(raw, text, 1)
    state = DialogueManager().advance(
        DialogueState(), text, 1, observation=observation, unknown_facts=list(unknown))
    return kind, state


def test_coordinator_returns_typed_route_and_leaves_facts_to_reducer():
    text = "Что такое ОФД?"
    raw = {
        "request_type": "information", "relation": "new_task", "intent": "general",
        "operation": "explain", "object": "ОФД", "object_evidence": {"quote": "ОФД"},
        "goal": {"quote": "Что такое ОФД?"}, "symptom": None, "entities": [],
        "unknown_facts": [], "specialist_requested": False, "specialist_evidence": None,
        "confidence": 0.9,
    }
    kind, state = _state(text, raw)
    before = state.to_dict()
    decision = coordinate({"request_type": kind, "observation": {"goals": [
        {"value": "Что такое ОФД?"}]}}, state)
    assert decision.route == "grounded_information"
    assert decision.request_type == "information"
    assert decision.task_relation == "new_task"
    assert decision.current_subgoal == "Что такое ОФД?"
    assert decision.required_action == "retrieve_and_quote_focused_approved_evidence"
    assert decision.rationale
    assert state.to_dict() == before


def test_coordinator_feature_flag_is_opt_in_and_keeps_existing_allowlist():
    base = Settings("", "", "", "", "", False, Path("."), rag_engine="source_first",
                    source_first_telegram_ids=frozenset({42}))
    assert not should_use_ai_coordinator(base, 42)
    enabled = Settings("", "", "", "", "", False, Path("."), rag_engine="source_first",
                       source_first_telegram_ids=frozenset({42}), ai_coordinator_enabled=True)
    assert should_use_ai_coordinator(enabled, 42)
    assert not should_use_ai_coordinator(enabled, 43)
    legacy = Settings("", "", "", "", "", False, Path("."), rag_engine="legacy",
                      source_first_telegram_ids=frozenset({42}), ai_coordinator_enabled=True)
    assert not should_use_ai_coordinator(legacy, 42)


def test_coordinator_routes_diagnostic_check_requests_to_strict_technical_path():
    text = "Касса aQsi не видит USB-сканер. Что проверить?"
    raw = {
        "request_type": "information", "relation": "new_task", "intent": "device",
        "operation": "check", "object": "USB-сканер", "object_evidence": {"quote": "USB-сканер"},
        "goal": {"quote": text}, "symptom": {"quote": "не видит USB-сканер"},
        "entities": [{"slot": "manufacturer", "value": "aQsi", "evidence": {"quote": "aQsi"}}],
        "unknown_facts": [], "specialist_requested": False, "specialist_evidence": None,
        "confidence": 0.9,
    }
    kind, state = _state(text, raw)
    decision = coordinate({"request_type": kind, "observation": {"goals": [{"value": text}]}}, state)
    assert decision.route == "technical_action"
    assert decision.rationale == "procedure_context_requires_complete_scoped_section"


def test_coordinator_asks_for_observable_symptom_before_diagnosing_a_broad_report():
    state = DialogueState()
    state.task_id = "task:1"
    state.operation = "diagnose"
    decision = coordinate({"request_type": "diagnosis", "observation": {}}, state)
    assert decision.route == "conversation"
    assert decision.required_action == "ask_for_missing_problem_detail"
    assert decision.rationale == "diagnosis_has_no_observed_symptom_or_goal"


def test_generic_error_word_does_not_count_as_a_diagnostic_symptom():
    state = DialogueState()
    state.task_id = "task:1"
    state.operation = "diagnose"
    state.symptom = Fact.span("ошибка", 1)
    state.goals = [Fact.span("помоги", 1)]
    decision = coordinate({"request_type": "diagnosis", "observation": {}}, state)
    assert decision.route == "conversation"
    assert decision.required_action == "ask_for_missing_problem_detail"


def test_clarification_reply_keeps_the_active_technical_route():
    state = DialogueState()
    state.task_id = "task:1"
    state.operation = "check"
    state.goals = [Fact.span("подключить сканер к кассе", 1)]
    state.relation = "answer_to_clarification"
    decision = coordinate({"request_type": "information", "observation": {}}, state)
    assert decision.route == "technical_action"
    assert decision.rationale == "clarification_reply_keeps_active_technical_route"


def test_scoped_error_article_requires_a_client_confirmed_code():
    state = DialogueState()
    state.error = Fact.span("234", 1, 0, 3)
    selected = {"title": "Эвотор: ошибка ФН 210 / -3910"}
    assert not _source_error_matches_client(state, selected)
    assert _source_error_matches_client(state, {"title": "Эвотор: ошибка ФН 234"})


def test_missing_support_detail_is_typed_and_bounded():
    state = DialogueState()
    state.intent = "receipt"
    state.operation = "search"
    assert _bounded_support_intake(state, []) == (
        "period", "За какой период или дату нужно найти запись?")
    assert _bounded_support_intake(state, [{"role": "assistant",
        "scenario_reason": "no_applicable_source_missing_client_detail"}]) is None
