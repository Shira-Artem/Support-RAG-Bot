from pathlib import Path

from app.ai_coordinator import coordinate
from app.config import Settings, should_use_ai_coordinator
from app.dialogue_state import DialogueManager, DialogueState
from app.dialogue_understanding import validate_response


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
