"""Small regressions from saved provider shapes, not ideal prebuilt state."""
import pytest

from app.ai_coordinator import coordinate
from app.dialogue_state import DialogueManager, DialogueState, Fact, Observation
from app.dialogue_understanding import Understanding, understanding_to_dict, validate_response
from app.procedure_policy import operation_compatibility
from app.rag_query import build_rag_query


@pytest.mark.parametrize("text,intent,operation,obj,goal,expected_op,expected_intent", [
    ("Как на Эвотор 6 напечатать копию чека по номеру ФД?", "information", "procedure",
     "Evotor 6", "напечатать копию чека по номеру ФД", "repeat_print", "receipt"),
    ("Диадок: контрагент не видит отправленный УПД, хочу проверить статус.", "status_query", "lookup",
     "УПД", "хочу проверить статус", "status", "delivery_document"),
    ("Нужно протестировать в БИФИТ Общепит работу со столами.", "test", "test",
     "столами", "Нужно протестировать", "unknown", "unknown"),
])
def test_provider_action_label_loss_does_not_erase_a_grounded_task(
        text, intent, operation, obj, goal, expected_op, expected_intent):
    raw = {"request_type": "request", "relation": "new_task", "intent": intent,
        "operation": operation, "object": obj, "object_evidence": None,
        "goal": {"quote": goal}, "symptom": None, "entities": [],
        "unknown_facts": [], "specialist_requested": False, "specialist_evidence": None,
        "confidence": .9}
    kind, specialist, unknown, obs = validate_response(raw, text, 1)
    state = DialogueManager().advance(DialogueState(), text, 1, observation=obs,
                                     unknown_facts=list(unknown))
    payload = understanding_to_dict(Understanding(kind, specialist, unknown, obs, {}, "frozen", 0))
    assert state.operation == expected_op
    assert state.intent == expected_intent
    assert coordinate(payload, state).route == "technical_action"
    assert text in build_rag_query(state)


def test_unknown_action_without_grounded_goal_still_needs_clarification():
    state = DialogueManager().advance(DialogueState(), "Здравствуйте", 1)
    assert coordinate({"request_type": "unknown"}, state).route == "conversation"


def test_coarse_edo_metadata_does_not_prove_a_read_only_or_mutating_action():
    metadata = {"status": "approved", "task_category": "edo", "operations": ["exchange_edo_documents"]}
    assert operation_compatibility("status", metadata, task_category="edo") == "unknown"
    assert operation_compatibility("search", metadata, task_category="edo") == "unknown"
    assert operation_compatibility("reconcile", metadata, task_category="edo") == "mismatch"
    assert operation_compatibility("status", {**metadata, "operations": ["sign_document"]},
                                   task_category="edo") == "mismatch"


def test_search_subject_wins_over_fiscal_number_parameter():
    text = "Как найти чек по номеру фискального документа?"
    raw = {"request_type": "question", "relation": "new_task", "intent": "fiscal_drive",
        "operation": "search", "object": "чек", "object_evidence": {"quote": "чек"},
        "goal": {"quote": text}, "symptom": None, "entities": [], "unknown_facts": [],
        "specialist_requested": False, "specialist_evidence": None, "confidence": .9}
    _, _, _, obs = validate_response(raw, text, 1)
    assert (obs.intent, obs.operation, obs.object) == ("receipt", "search", "чек")


def test_multiple_client_results_keep_their_own_quote_and_do_not_complete_a_compound_check():
    manager = DialogueManager()
    state = manager.advance(DialogueState(), "Эвотор 7.3 не передаёт чеки в ОФД", 1)
    state = manager.observe_answer(state, scenario="answer", reason="source_first_exact_section",
        question="Проверьте интернет и оплату", progress_update={"procedure_id": "test",
            "shown_units": [
                {"unit_id": "internet", "label": "Проверьте интернет.", "source_verified": True},
                {"unit_id": "payment", "label": "Проверьте оплату.", "source_verified": True},
                {"unit_id": "compound", "label": "Проверьте интернет. Сопоставьте адрес и порт ОФД.", "source_verified": True}]})
    text = "Интернет работает. Оплата не прошла."
    observation = Observation(entities={}, intent="unknown", operation="unknown", object=None,
        evidence=Fact.span(text, 3), relation="continue", confidence=.9)
    state = manager.advance(state, text, 3, observation=observation)
    checks = {item["unit_id"]: item for item in state.task_context.checks}
    assert checks["internet"]["status"] == "passed"
    assert checks["internet"]["result_span"]["quote"] == "Интернет работает"
    assert checks["payment"]["status"] == "failed"
    assert checks["payment"]["result_span"]["quote"] == "Оплата не прошла"
    assert checks["compound"]["status"] == "unknown"
